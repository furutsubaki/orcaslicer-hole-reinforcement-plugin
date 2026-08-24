"""Markdownの相対リンクが実在するファイルを指しているか検証する。

文書間の相互参照が多く、ファイルの移動や削除でリンクが切れやすいため。
"""

import re
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
LINK = re.compile(r"\[[^\]]*\]\(([^)]+)\)")
EXTERNAL = ("http://", "https://", "mailto:")


def documents() -> list[Path]:
    return sorted([*PROJECT_ROOT.glob("*.md"), *PROJECT_ROOT.glob("docs/**/*.md")])


def broken_links(document: Path) -> list[str]:
    broken = []
    for match in LINK.finditer(document.read_text(encoding="utf-8")):
        target = match.group(1).split("#")[0].strip()
        if not target or target.startswith(EXTERNAL):
            continue
        if not (document.parent / target).resolve().exists():
            broken.append(target)
    return broken


def main() -> int:
    failures = 0
    for document in documents():
        for target in broken_links(document):
            relative = document.relative_to(PROJECT_ROOT)
            print(f"{relative}: {target} は存在しません", file=sys.stderr)
            failures += 1

    if failures:
        print(f"{failures}件のリンクが切れています", file=sys.stderr)
        return 1

    print(f"{len(documents())}件の文書のリンクを検証しました")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
