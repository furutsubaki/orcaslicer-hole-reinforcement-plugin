"""CHANGELOG.mdから指定バージョンの節を抜き出す。

GitHub Releaseの本文へそのまま流し込むため、見出し行と参照リンク定義は落とす。
"""

import argparse
import re
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
HEADING = re.compile(r"^## \[(?P<version>[^\]]+)\]")
LINK_DEFINITION = re.compile(r"^\[[^\]]+\]: \S+$")


def extract(text: str, version: str) -> str | None:
    lines = text.splitlines()
    start = None
    for index, line in enumerate(lines):
        match = HEADING.match(line)
        if match is None:
            continue
        if start is None and match.group("version") == version:
            start = index + 1
            continue
        if start is not None:
            return _clean(lines[start:index])
    if start is None:
        return None
    return _clean(lines[start:])


def _clean(lines: list[str]) -> str:
    kept = [line for line in lines if not LINK_DEFINITION.match(line)]
    return "\n".join(kept).strip() + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("version", help="抜き出すバージョン（例: 1.0.0）")
    parser.add_argument(
        "--changelog", type=Path, default=PROJECT_ROOT / "CHANGELOG.md"
    )
    args = parser.parse_args()

    section = extract(args.changelog.read_text(encoding="utf-8"), args.version)
    if section is None:
        print(f"{args.version}の節がCHANGELOGにありません", file=sys.stderr)
        return 1

    sys.stdout.write(section)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
