"""OrcaSlicerのsandbox化された設定frameへ渡すHTML。"""

import json
from html import escape

from .config import default_config_dict


def render_config_ui(
    language: object = "",
    initial: object = None,
    stale_override_keys: object = (),
) -> str:
    language_code = language if isinstance(language, str) else ""
    locale = "ja" if language_code.lower().replace("-", "_").startswith("ja") else "en"
    texts = _TRANSLATIONS[locale]
    default_config = default_config_dict()
    defaults = _embed(default_config)
    # ホストは保存済み設定を読み終えてからget_config_ui()を呼ぶため、引き継いだ値は
    # HTMLへ載せる以外に初回表示へ届かない。
    initial_config = _embed(initial if isinstance(initial, dict) else default_config)
    validation_texts = _embed(texts["validation"])
    stale_keys = [key for key in (stale_override_keys or ()) if isinstance(key, str)]
    stale_notice = texts["ui"]["stale_override"] if stale_keys else ""
    html = (
        _HTML.replace("__DEFAULT_CONFIG__", defaults)
        .replace("__INITIAL_CONFIG__", initial_config)
        .replace("__VALIDATION_TEXTS__", validation_texts)
    )
    html = html.replace("__LANG__", locale)
    html = html.replace("__STALE_OVERRIDE__", escape(stale_notice))
    html = html.replace("__STALE_HIDDEN__", "" if stale_keys else " hidden")
    html = html.replace("__STALE_KEYS__", escape("/ ".join(stale_keys)))
    for key, value in texts["ui"].items():
        html = html.replace(f"__{key.upper()}__", escape(value))
    return html


def _embed(value: object) -> str:
    return json.dumps(value, ensure_ascii=False).replace("<", "\\u003c")


_TRANSLATIONS = {
    "en": {
        "ui": {
            "title": "Hole reinforcement settings",
            "intro": "Configure which holes to detect and how their surroundings are solidified.",
            "format_label": "Configuration format:",
            "format_help": "v2 (managed automatically by the plugin for compatibility checks)",
            "stale_override": (
                "This preset still holds settings saved for an older version of this plugin. "
                "OrcaSlicer keys preset overrides by plugin version, and the plugin cannot restore "
                "them. Set the values again here, or in the preset's plugin settings."
            ),
            "dimensions": "Target dimensions",
            "min_diameter": "Minimum hole diameter",
            "min_diameter_help": "Holes smaller than this are ignored. Must not exceed the maximum diameter.",
            "max_diameter": "Maximum hole diameter",
            "max_diameter_help": "Holes larger than this are ignored.",
            "width": "Reinforcement width",
            "width_help": "Distance solidified outward from the hole contour.",
            "depth": "Minimum hole depth",
            "depth_help": "Holes shallower than this are ignored.",
            "shapes": "Target shapes",
            "hole_shape": "Hole shape",
            "circle": "Circle",
            "hexagon": "Hexagon",
            "octagon": "Octagon",
            "regular_polygon": "Regular polygon",
            "min_polygon_sides": "Minimum polygon sides",
            "min_polygon_sides_help": "Smallest regular polygon detected by the generic polygon option.",
            "max_polygon_sides": "Maximum polygon sides",
            "max_polygon_sides_help": "Largest regular polygon detected by the generic polygon option.",
            "choose_one": "Select at least one option.",
            "hole_end": "Hole end",
            "through": "Through hole",
            "blind": "Blind hole",
            "tolerances": "Detection tolerances",
            "radial_tolerance": "Circle radial tolerance",
            "radial_tolerance_help": "Maximum allowed variation in the radius of cylindrical faces.",
            "edge_tolerance": "Polygon edge length tolerance",
            "edge_tolerance_help": "Maximum allowed variation in polygon edge lengths.",
            "angle_tolerance": "Polygon angle tolerance",
            "angle_tolerance_help": "Maximum allowed angular deviation between adjacent faces.",
            "axis_tolerance": "Axis tolerance",
            "axis_tolerance_help": "Maximum allowed axial deviation among faces forming a hole.",
            "processing": "Processing",
            "solid": "Enable solid reinforcement",
            "solid_help": "Solidify the internal infill surrounding detected holes.",
            "diagnostics": "Enable diagnostics",
            "diagnostics_help": "Report detection results and exclusion reasons in diagnostics.",
            "restore": "Restore defaults",
            "auto_save": "Valid changes are saved automatically.",
        },
        "validation": {
            "auto_save": "Valid changes are saved automatically.",
            "range": "{label} must be between {min} and {max}.",
            "diameter_relation": "Minimum hole diameter must not exceed maximum hole diameter.",
            "polygon_sides_relation": "Minimum polygon sides must not exceed maximum polygon sides.",
            "shape_required": "Select at least one hole shape.",
            "end_required": "Select at least one hole end.",
            "saving": "Saving automatically…",
            "saved": "Saved automatically.",
            "invalid_not_saved": "Invalid changes have not been saved.",
            "unconfirmed": "The save could not be confirmed. Change a value to retry.",
        },
    },
    "ja": {
        "ui": {
            "title": "穴補強設定",
            "intro": "対象にする穴と、穴周辺をソリッド化する条件を設定します。",
            "format_label": "設定形式:",
            "format_help": "v2（互換性判定のためプラグインが自動管理します）",
            "stale_override": (
                "このプリセットに、旧バージョン向けに保存された設定が残っています。"
                "OrcaSlicerはプリセット側の設定をプラグインのバージョンごとに保持するため、"
                "プラグインからは復元できません。この画面かプリセットの設定で入力し直してください。"
            ),
            "dimensions": "対象寸法",
            "min_diameter": "最小穴径",
            "min_diameter_help": "これより小さい穴は補強しません。最大穴径以下にしてください。",
            "max_diameter": "最大穴径",
            "max_diameter_help": "これより大きい穴は補強しません。",
            "width": "補強幅",
            "width_help": "穴の輪郭から外側へソリッド化する幅です。",
            "depth": "最小穴深さ",
            "depth_help": "これより浅い穴は補強しません。",
            "shapes": "対象形状",
            "hole_shape": "穴形状",
            "circle": "円",
            "hexagon": "六角形",
            "octagon": "八角形",
            "regular_polygon": "正多角形",
            "min_polygon_sides": "正多角形の最小辺数",
            "min_polygon_sides_help": "正多角形として検出する最小の辺数です。",
            "max_polygon_sides": "正多角形の最大辺数",
            "max_polygon_sides_help": "正多角形として検出する最大の辺数です。",
            "choose_one": "1つ以上選択してください。",
            "hole_end": "穴の終端",
            "through": "貫通穴",
            "blind": "止まり穴",
            "tolerances": "検出許容差",
            "radial_tolerance": "円の半径許容差",
            "radial_tolerance_help": "円柱面の半径ばらつきを許容する上限です。",
            "edge_tolerance": "多角形の辺長許容差",
            "edge_tolerance_help": "各辺の長さのばらつきを許容する上限です。",
            "angle_tolerance": "多角形の角度許容差",
            "angle_tolerance_help": "隣接面の角度のずれを許容する上限です。",
            "axis_tolerance": "軸許容差",
            "axis_tolerance_help": "穴を構成する面の軸方向のずれを許容する上限です。",
            "processing": "処理",
            "solid": "ソリッド補強を有効にする",
            "solid_help": "検出した穴周辺の内部インフィルをソリッド化します。",
            "diagnostics": "診断出力を有効にする",
            "diagnostics_help": "検出結果と除外理由を診断情報へ出力します。",
            "restore": "既定値に戻す",
            "auto_save": "有効な変更は自動的に保存されます。",
        },
        "validation": {
            "auto_save": "有効な変更は自動的に保存されます。",
            "range": "{label}を{min}〜{max}の範囲で入力してください。",
            "diameter_relation": "最小穴径は最大穴径以下にしてください。",
            "polygon_sides_relation": "正多角形の最小辺数は最大辺数以下にしてください。",
            "shape_required": "穴形状を1つ以上選択してください。",
            "end_required": "穴の終端を1つ以上選択してください。",
            "saving": "自動保存しています…",
            "saved": "自動保存しました。",
            "invalid_not_saved": "不正な変更は保存されていません。",
            "unconfirmed": "保存を確認できませんでした。値を変更すると再試行します。",
        },
    },
}


_HTML = r"""
<style>
  :root {
    color-scheme: light dark;
    font-family: var(--orca-font, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif);
    color: var(--orca-fg, #252525);
    background: var(--orca-bg, #f7f7f7);
  }
  * { box-sizing: border-box; }
  body { margin: 0; padding: 18px; }
  form { max-width: 920px; margin: 0 auto; }
  h1 { margin: 0 0 6px; font-size: 20px; }
  .intro, .help { color: var(--orca-muted, #666); }
  .intro { margin: 0 0 18px; font-size: 13px; }
  fieldset {
    margin: 0 0 14px;
    padding: 14px;
    border: 1px solid var(--orca-border, #c9c9c9);
    border-radius: 6px;
    background: var(--orca-bg, #fff);
  }
  legend { padding: 0 6px; font-weight: 650; }
  .grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
    gap: 14px 18px;
  }
  .field { min-width: 0; }
  label, .group-label { display: block; margin-bottom: 5px; font-weight: 600; }
  .input-unit { display: flex; align-items: center; gap: 8px; }
  input[type="number"] {
    width: 100%;
    min-width: 0;
    padding: 7px 9px;
    border: 1px solid var(--orca-border, #aaa);
    border-radius: 4px;
    color: inherit;
    background: var(--orca-bg, #fff);
  }
  input:focus-visible, button:focus-visible {
    outline: 2px solid var(--orca-accent, #0066cc);
    outline-offset: 2px;
  }
  .unit { min-width: 28px; color: var(--orca-muted, #666); }
  .help { margin: 5px 0 0; font-size: 12px; line-height: 1.4; }
  .choices { display: flex; flex-wrap: wrap; gap: 8px 16px; }
  .choice { display: inline-flex; align-items: center; min-height: 44px; gap: 6px; font-weight: 400; }
  .toggles { display: grid; gap: 10px; }
  .toggle { display: grid; grid-template-columns: auto 1fr; min-height: 44px; gap: 3px 8px; }
  .toggle input { grid-row: 1 / span 2; align-self: start; margin-top: 3px; }
  .toggle label { margin: 0; }
  .toggle .help { margin: 0; }
  .error {
    margin: 0 0 12px;
    padding: 9px 11px;
    border: 1px solid #b3261e;
    border-radius: 4px;
    color: #b3261e;
    background: color-mix(in srgb, #b3261e 8%, transparent);
  }
  [data-orca-theme="dark"] .error { color: #ffb4ab; border-color: #ffb4ab; }
  .notice {
    margin: 0 0 14px;
    padding: 9px 11px;
    border: 1px solid #8a6d00;
    border-radius: 4px;
    color: #6b5400;
    background: color-mix(in srgb, #8a6d00 8%, transparent);
    font-size: 13px;
    line-height: 1.5;
  }
  .notice code { word-break: break-all; }
  [data-orca-theme="dark"] .notice { color: #ffd479; border-color: #ffd479; }
  .actions { display: flex; align-items: center; justify-content: space-between; gap: 10px; padding-top: 2px; }
  .save-status { color: var(--orca-muted, #666); font-size: 12px; }
  button { min-height: 44px; padding: 8px 16px; border: 1px solid var(--orca-border, #999); border-radius: 4px; color: inherit; background: var(--orca-bg, #eee); cursor: pointer; }
  button[type="submit"] { color: var(--orca-accent-fg, #fff); background: var(--orca-accent, #0066cc); border-color: transparent; }
  button:disabled { cursor: not-allowed; opacity: .55; }
  @media (max-width: 560px) {
    body { padding: 12px; }
    .grid { grid-template-columns: 1fr; }
    .actions { align-items: stretch; flex-direction: column; }
  }
</style>

<form id="config-form" novalidate lang="__LANG__">
  <h1>__TITLE__</h1>
  <p class="intro">__INTRO__</p>
  <p class="intro"><strong>__FORMAT_LABEL__</strong> __FORMAT_HELP__</p>
  <p id="stale-override" class="notice" role="status"__STALE_HIDDEN__>__STALE_OVERRIDE__<br><code>__STALE_KEYS__</code></p>
  <div id="errors" class="error" role="alert" aria-live="assertive" hidden></div>

  <fieldset>
    <legend>__DIMENSIONS__</legend>
    <div class="grid">
      <div class="field"><label for="min_hole_diameter_mm">__MIN_DIAMETER__</label><div class="input-unit"><input id="min_hole_diameter_mm" type="number" min="0.1" max="100" step="0.1" required aria-describedby="min_hole_diameter_mm_help"><span class="unit">mm</span></div><p id="min_hole_diameter_mm_help" class="help">__MIN_DIAMETER_HELP__</p></div>
      <div class="field"><label for="max_hole_diameter_mm">__MAX_DIAMETER__</label><div class="input-unit"><input id="max_hole_diameter_mm" type="number" min="0.1" max="100" step="0.1" required aria-describedby="max_hole_diameter_mm_help"><span class="unit">mm</span></div><p id="max_hole_diameter_mm_help" class="help">__MAX_DIAMETER_HELP__</p></div>
      <div class="field"><label for="reinforcement_width_mm">__WIDTH__</label><div class="input-unit"><input id="reinforcement_width_mm" type="number" min="0.1" max="20" step="0.1" required aria-describedby="reinforcement_width_mm_help"><span class="unit">mm</span></div><p id="reinforcement_width_mm_help" class="help">__WIDTH_HELP__</p></div>
      <div class="field"><label for="min_hole_depth_mm">__DEPTH__</label><div class="input-unit"><input id="min_hole_depth_mm" type="number" min="0.1" max="1000" step="0.1" required aria-describedby="min_hole_depth_mm_help"><span class="unit">mm</span></div><p id="min_hole_depth_mm_help" class="help">__DEPTH_HELP__</p></div>
    </div>
  </fieldset>

  <fieldset><legend>__SHAPES__</legend><div class="grid">
    <div class="field"><span id="shapes-label" class="group-label">__HOLE_SHAPE__</span><div class="choices" role="group" aria-labelledby="shapes-label" aria-describedby="shapes-help"><label class="choice"><input type="checkbox" name="enabled_shapes" value="circle">__CIRCLE__</label><label class="choice"><input type="checkbox" name="enabled_shapes" value="hexagon">__HEXAGON__</label><label class="choice"><input type="checkbox" name="enabled_shapes" value="octagon">__OCTAGON__</label><label class="choice"><input type="checkbox" name="enabled_shapes" value="regular_polygon">__REGULAR_POLYGON__</label></div><p id="shapes-help" class="help">__CHOOSE_ONE__</p></div>
    <div class="field"><span id="ends-label" class="group-label">__HOLE_END__</span><div class="choices" role="group" aria-labelledby="ends-label" aria-describedby="ends-help"><label class="choice"><input type="checkbox" name="enabled_end_kinds" value="through">__THROUGH__</label><label class="choice"><input type="checkbox" name="enabled_end_kinds" value="blind">__BLIND__</label></div><p id="ends-help" class="help">__CHOOSE_ONE__</p></div>
    <div class="field"><label for="min_polygon_sides">__MIN_POLYGON_SIDES__</label><input id="min_polygon_sides" type="number" min="3" max="64" step="1" required aria-describedby="min_polygon_sides_help"><p id="min_polygon_sides_help" class="help">__MIN_POLYGON_SIDES_HELP__</p></div>
    <div class="field"><label for="max_polygon_sides">__MAX_POLYGON_SIDES__</label><input id="max_polygon_sides" type="number" min="3" max="64" step="1" required aria-describedby="max_polygon_sides_help"><p id="max_polygon_sides_help" class="help">__MAX_POLYGON_SIDES_HELP__</p></div>
  </div></fieldset>

  <fieldset><legend>__TOLERANCES__</legend><div class="grid">
    <div class="field"><label for="circle_radial_tolerance_mm">__RADIAL_TOLERANCE__</label><div class="input-unit"><input id="circle_radial_tolerance_mm" type="number" min="0" max="1" step="0.01" required aria-describedby="circle_radial_tolerance_mm_help"><span class="unit">mm</span></div><p id="circle_radial_tolerance_mm_help" class="help">__RADIAL_TOLERANCE_HELP__</p></div>
    <div class="field"><label for="polygon_edge_length_tolerance_percent">__EDGE_TOLERANCE__</label><div class="input-unit"><input id="polygon_edge_length_tolerance_percent" type="number" min="0" max="25" step="0.1" required aria-describedby="polygon_edge_length_tolerance_percent_help"><span class="unit">%</span></div><p id="polygon_edge_length_tolerance_percent_help" class="help">__EDGE_TOLERANCE_HELP__</p></div>
    <div class="field"><label for="polygon_angle_tolerance_deg">__ANGLE_TOLERANCE__</label><div class="input-unit"><input id="polygon_angle_tolerance_deg" type="number" min="0" max="15" step="0.1" required aria-describedby="polygon_angle_tolerance_deg_help"><span class="unit">°</span></div><p id="polygon_angle_tolerance_deg_help" class="help">__ANGLE_TOLERANCE_HELP__</p></div>
    <div class="field"><label for="axis_tolerance_deg">__AXIS_TOLERANCE__</label><div class="input-unit"><input id="axis_tolerance_deg" type="number" min="0" max="15" step="0.1" required aria-describedby="axis_tolerance_deg_help"><span class="unit">°</span></div><p id="axis_tolerance_deg_help" class="help">__AXIS_TOLERANCE_HELP__</p></div>
  </div></fieldset>

  <fieldset><legend>__PROCESSING__</legend><div class="toggles">
    <div class="toggle"><input id="solid_reinforcement" type="checkbox"><label for="solid_reinforcement">__SOLID__</label><p class="help">__SOLID_HELP__</p></div>
    <div class="toggle"><input id="diagnostics_enabled" type="checkbox"><label for="diagnostics_enabled">__DIAGNOSTICS__</label><p class="help">__DIAGNOSTICS_HELP__</p></div>
  </div></fieldset>

  <div class="actions"><span id="save-status" class="save-status" role="status" aria-live="polite">__AUTO_SAVE__</span><button id="restore" type="button">__RESTORE__</button></div>
</form>

<script>
(function () {
  "use strict";
  document.documentElement.lang = "__LANG__";
  var defaults = __DEFAULT_CONFIG__;
  var initial = __INITIAL_CONFIG__;
  var texts = __VALIDATION_TEXTS__;
  var numericKeys = ["min_hole_diameter_mm", "max_hole_diameter_mm", "reinforcement_width_mm", "min_hole_depth_mm", "min_polygon_sides", "max_polygon_sides", "circle_radial_tolerance_mm", "polygon_edge_length_tolerance_percent", "polygon_angle_tolerance_deg", "axis_tolerance_deg"];
  var booleanKeys = ["solid_reinforcement", "diagnostics_enabled"];
  var form = document.getElementById("config-form");
  var errors = document.getElementById("errors");
  var saveStatus = document.getElementById("save-status");
  var initialized = false;
  var restorePending = false;
  var confirmationTimer;

  function populate(config) {
    var value = Object.assign({}, defaults, config || {});
    numericKeys.forEach(function (key) { document.getElementById(key).value = value[key]; });
    booleanKeys.forEach(function (key) { document.getElementById(key).checked = value[key] === true; });
    ["enabled_shapes", "enabled_end_kinds"].forEach(function (key) {
      var selected = Array.isArray(value[key]) ? value[key] : defaults[key];
      document.querySelectorAll('[name="' + key + '"]').forEach(function (input) { input.checked = selected.indexOf(input.value) !== -1; });
    });
    return validate();
  }

  function selected(name) {
    return Array.from(document.querySelectorAll('[name="' + name + '"]:checked')).map(function (input) { return input.value; });
  }

  function readConfig() {
    var config = { schema_version: defaults.schema_version };
    numericKeys.forEach(function (key) { config[key] = Number(document.getElementById(key).value); });
    booleanKeys.forEach(function (key) { config[key] = document.getElementById(key).checked; });
    config.enabled_shapes = selected("enabled_shapes");
    config.enabled_end_kinds = selected("enabled_end_kinds");
    return config;
  }

  function comparable(config) {
    var value = Object.assign({}, defaults, config || {});
    var normalized = { schema_version: defaults.schema_version };
    numericKeys.forEach(function (key) { normalized[key] = Number(value[key]); });
    booleanKeys.forEach(function (key) { normalized[key] = value[key] === true; });
    normalized.enabled_shapes = Array.isArray(value.enabled_shapes) ? value.enabled_shapes : defaults.enabled_shapes;
    normalized.enabled_end_kinds = Array.isArray(value.enabled_end_kinds) ? value.enabled_end_kinds : defaults.enabled_end_kinds;
    return JSON.stringify(normalized);
  }

  function setSaveStatus(message) {
    saveStatus.textContent = message;
  }

  function persistIfValid() {
    if (!validate()) {
      setSaveStatus(texts.invalid_not_saved);
      return;
    }
    var config = readConfig();
    setSaveStatus(texts.saving);
    window.orca.saveConfig(config);
    window.clearTimeout(confirmationTimer);
    confirmationTimer = window.setTimeout(function () {
      if (saveStatus.textContent === texts.saving) setSaveStatus(texts.unconfirmed);
    }, 5000);
  }

  function hasValues(config) {
    return !!config && Object.keys(config).length > 0;
  }

  function receiveConfig(config) {
    if (!initialized) {
      var initialValid = populate(hasValues(config) ? config : initial);
      initialized = true;
      setSaveStatus(initialValid ? texts.auto_save : texts.invalid_not_saved);
      return;
    }
    if (restorePending) {
      populate(config);
      restorePending = false;
      window.clearTimeout(confirmationTimer);
      setSaveStatus(texts.saved);
      return;
    }
    if (comparable(config) === comparable(readConfig())) {
      window.clearTimeout(confirmationTimer);
      setSaveStatus(texts.saved);
    } else if (validate()) {
      persistIfValid();
    }
  }

  function validate() {
    var messages = [];
    Array.from(form.querySelectorAll('input[type="number"]')).forEach(function (input) {
      input.removeAttribute("aria-invalid");
      if (!input.validity.valid) {
        input.setAttribute("aria-invalid", "true");
        messages.push(texts.range.replace("{label}", document.querySelector('label[for="' + input.id + '"]').textContent).replace("{min}", input.min).replace("{max}", input.max));
      }
    });
    var config = readConfig();
    if (Number.isFinite(config.min_hole_diameter_mm) && Number.isFinite(config.max_hole_diameter_mm) && config.min_hole_diameter_mm > config.max_hole_diameter_mm) messages.push(texts.diameter_relation);
    if (Number.isFinite(config.min_polygon_sides) && Number.isFinite(config.max_polygon_sides) && config.min_polygon_sides > config.max_polygon_sides) messages.push(texts.polygon_sides_relation);
    if (config.enabled_shapes.length === 0) messages.push(texts.shape_required);
    if (config.enabled_end_kinds.length === 0) messages.push(texts.end_required);
    errors.replaceChildren();
    messages.forEach(function (message) { var line = document.createElement("div"); line.textContent = message; errors.appendChild(line); });
    errors.hidden = messages.length === 0;
    return messages.length === 0;
  }

  form.addEventListener("input", persistIfValid);
  form.addEventListener("submit", function (event) { event.preventDefault(); });
  document.getElementById("restore").addEventListener("click", function () { restorePending = true; window.orca.restoreDefaults(); });
  if (window.orca.onConfig) window.orca.onConfig(receiveConfig); else { receiveConfig(window.orca.getConfig()); }
})();
</script>
"""
