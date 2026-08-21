"""旧バージョンのホスト設定エントリから設定を引き継ぐ。

OrcaSlicerは設定エントリをwheelファイル名由来の`plugin_key`で識別するため、
バージョンを上げると別エントリになり、プラグインAPIからは旧エントリを参照できない。
ホストの`config.json`を読み取り専用で辿ることが唯一の引き継ぎ手段になる。
"""

from collections.abc import Mapping
from dataclasses import dataclass
import json
from pathlib import Path

from .config import (
    ConfigValidation,
    HoleReinforcementConfig,
    default_config,
    parse_config,
    parse_json_config,
)

HOST_CONFIG_FILENAME = "config.json"
HOST_PLUGIN_DIR_NAME = "orca_plugins"
HOST_CAPABILITY_TYPE = "slicing-pipeline"

# Preset::plugin_overrides_key()が返すプリセット種別ごとのキー。
PRESET_OVERRIDE_KEYS = (
    "print_plugin_config_overrides",
    "printer_plugin_config_overrides",
    "filament_plugin_config_overrides",
)

_MAX_ANCESTORS = 12
# config.jsonは導入済みプラグイン全件が書き込む共有ファイルで、本プラグインは書式を保証できない。
MAX_HOST_CONFIG_BYTES = 4 * 1024 * 1024

REASON_MIGRATED = "migrated"
REASON_NO_HOST_CONFIG = "no_host_config"
REASON_NO_DONOR = "no_donor"
REASON_UNREADABLE = "unreadable"


@dataclass(frozen=True, slots=True)
class ConfigMigration:
    config: HoleReinforcementConfig
    reason: str
    source_plugin_key: str | None = None
    source_plugin_version: str | None = None
    rejected_count: int = 0


def parse_host_config(raw: object) -> ConfigValidation | None:
    """ホスト設定を1回だけ解釈する。未保存なら`None`を返す。

    ホストはインストール時に既定値を書き込まないため、空であることが未保存の証拠になる。
    空判定と検証を別々に行うと、設定UIとスライスで同じ値の解釈が食い違いうるため1つにまとめる。
    """
    if raw is None:
        return None
    if isinstance(raw, (str, bytes, bytearray)):
        text = raw.strip()
        if not text:
            return None
        try:
            supplied = json.loads(text)
        except (TypeError, ValueError):
            return parse_json_config(raw)
    else:
        supplied = raw
    if supplied is None or (isinstance(supplied, Mapping) and not supplied):
        return None
    return parse_config(supplied)


def host_config_is_empty(raw: object) -> bool:
    return parse_host_config(raw) is None


def find_host_config_path(start: Path) -> Path | None:
    """`start`の祖先にある`orca_plugins/config.json`を探す。

    `orca_plugins`を見つけた時点で遡上を打ち切る。監査フックが許可するのは
    `data_dir()`配下だけであり、それより上を探索する意味がない。
    """
    for directory in _ancestors(start):
        if directory.name != HOST_PLUGIN_DIR_NAME:
            continue
        candidate = directory / HOST_CONFIG_FILENAME
        return candidate if candidate.is_file() else None
    return None


def current_plugin_key(start: Path) -> str | None:
    """`start`を含むプラグインの`plugin_key`を導出する。

    ホストはインストール元ファイルのstemをキーにする（`assign_local_plugin_key`）。
    展開先は`orca_plugins/<file name>/`配下にあるため、その名前から復元できる。
    """
    previous: Path | None = None
    for directory in _ancestors(start):
        if directory.name == HOST_PLUGIN_DIR_NAME:
            if previous is None:
                return None
            return previous.name.removesuffix(".whl")
        previous = directory
    return None


def migrate_config(
    start: Path,
    capability_name: str,
    *,
    config_path: Path | None = None,
) -> ConfigMigration:
    """旧エントリから設定を引き継ぐ。失敗しても必ず既定値を返す。"""
    try:
        return _migrate_config(start, capability_name, config_path)
    except Exception:
        # 監査フックはPermissionError以外も送出しうる。引き継ぎの失敗でスライスを止めない。
        return ConfigMigration(default_config(), REASON_UNREADABLE)


def _migrate_config(
    start: Path,
    capability_name: str,
    config_path: Path | None,
) -> ConfigMigration:
    path = config_path if config_path is not None else find_host_config_path(start)
    if path is None or not path.is_file():
        return ConfigMigration(default_config(), REASON_NO_HOST_CONFIG)
    if path.stat().st_size > MAX_HOST_CONFIG_BYTES:
        return ConfigMigration(default_config(), REASON_UNREADABLE)

    document = json.loads(path.read_text(encoding="utf-8"))
    entries = document.get("config") if isinstance(document, Mapping) else None
    if not isinstance(entries, list):
        # ファイルはあるがホスト側のレイアウトが変わった場合。引き継ぎ元が無いのと同じ扱いにする。
        return ConfigMigration(default_config(), REASON_NO_DONOR)

    own_key = current_plugin_key(start)
    candidates = [
        entry
        for entry in entries
        if _is_donor_candidate(entry, capability_name, own_key)
    ]
    candidates.sort(key=lambda entry: _version_key(entry.get("plugin_version")), reverse=True)

    rejected = 0
    for entry in candidates:
        validation: ConfigValidation = parse_config(entry["cap_config"])
        if not validation.is_valid:
            rejected += 1
            continue
        assert validation.config is not None
        return ConfigMigration(
            validation.config,
            REASON_MIGRATED,
            source_plugin_key=_text(entry.get("plugin_key")),
            source_plugin_version=_text(entry.get("plugin_version")),
            rejected_count=rejected,
        )

    return ConfigMigration(
        default_config(), REASON_NO_DONOR, rejected_count=rejected
    )


def find_stale_preset_overrides(
    raw: object,
    capability_name: str,
    own_plugin_key: str | None,
) -> tuple[str, ...]:
    """プリセットに残った、別バージョン向けoverrideの`plugin_key`を返す。

    overrideも`plugin_key`込みで保持されるため、更新すると参照されなくなる。
    プラグインAPIからは読み取りしかできず、書き戻して復元する手段が無い。
    """
    entries = _parse_preset_option(raw)
    if not isinstance(entries, list):
        return ()

    stale = []
    for entry in entries:
        if not isinstance(entry, Mapping):
            continue
        if entry.get("capability") != capability_name:
            continue
        if entry.get("capability_type") not in (HOST_CAPABILITY_TYPE, None, ""):
            continue
        plugin_key = _text(entry.get("plugin_key"))
        if plugin_key is None or plugin_key == own_plugin_key:
            continue
        if not isinstance(entry.get("cap_config"), Mapping):
            continue
        stale.append(plugin_key)
    return tuple(stale)


def _parse_preset_option(raw: object) -> object:
    """プリセットのconfig値を読む。

    ホストは`ConfigOptionString::serialize()`を通して返すため、値は
    `escape_string_cstyle()`でエスケープされている（`"`→`\\"`、`\\`→`\\\\`、改行→`\\n`）。
    素のJSONで返るホストにも備えて、先にそのまま解釈してから解除を試す。
    """
    if not isinstance(raw, (str, bytes, bytearray)):
        return raw
    text = raw.decode("utf-8") if isinstance(raw, (bytes, bytearray)) else raw
    for candidate in (text, _unescape_cstyle(text)):
        try:
            return json.loads(candidate)
        except (TypeError, ValueError):
            continue
    return None


_CSTYLE_ESCAPES = {"n": "\n", "r": "\r", "\\": "\\", '"': '"'}


def _unescape_cstyle(text: str) -> str:
    out = []
    index = 0
    while index < len(text):
        character = text[index]
        if character == "\\" and index + 1 < len(text):
            replacement = _CSTYLE_ESCAPES.get(text[index + 1])
            if replacement is not None:
                out.append(replacement)
                index += 2
                continue
        out.append(character)
        index += 1
    return "".join(out)


def _is_donor_candidate(entry: object, capability_name: str, own_key: str | None) -> bool:
    if not isinstance(entry, Mapping):
        return False
    if entry.get("capability") != capability_name:
        return False
    # 型を持たないレガシーエントリはホスト側も名前だけで解決する（CapabilityConfigDocument::find）。
    capability_type = entry.get("capability_type")
    if capability_type not in (HOST_CAPABILITY_TYPE, None, ""):
        return False
    if own_key is not None and entry.get("plugin_key") == own_key:
        return False
    cap_config = entry.get("cap_config")
    return isinstance(cap_config, Mapping) and bool(cap_config)


def _ancestors(start: Path) -> list[Path]:
    resolved = start.resolve()
    directories = [resolved, *resolved.parents]
    return directories[:_MAX_ANCESTORS]


def _version_key(value: object) -> tuple[int, ...]:
    if not isinstance(value, str):
        return ()
    segments = []
    for chunk in value.split("."):
        digits = ""
        for character in chunk:
            if not character.isdigit():
                break
            digits += character
        segments.append(int(digits) if digits else -1)
    return tuple(segments)


def _text(value: object) -> str | None:
    return value if isinstance(value, str) and value else None
