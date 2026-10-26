#!/usr/bin/env python3
"""Check repository documentation hygiene.

* Every relative link in README.md and docs/**/*.md points at an existing
  file or directory. External links (any URI scheme, e.g. http:, https:,
  mailto:), protocol-relative links and pure #anchors are ignored; #fragments
  and ?queries are stripped before resolving. Links inside fenced code blocks
  and inline code spans are ignored. docs/archive/ holds verbatim copies of
  source material whose hashes are recorded in docs/research/source-audit.md,
  so it cannot be edited; it is skipped unless --include-archive is given.
* Every file in docs/decisions/ is named ADR-NNNN-<slug>.md.

Exit status is 1 if any problem is found. Standard library only.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from urllib.parse import unquote

ROOT = Path(__file__).resolve().parent.parent
DECISIONS = ROOT / "docs" / "decisions"
ARCHIVE = ROOT / "docs" / "archive"
ADR_NAME = re.compile(r"^ADR-\d{4}-[^/\\]+\.md$")

FENCE = re.compile(r"^ {0,3}(`{3,}|~{3,})")
CODE_SPAN = re.compile(r"(`+)(?:(?!\1).)+?\1")
# [text](target "title") and ![alt](target); text may contain one level of brackets.
INLINE_LINK = re.compile(r"!?\[(?:[^\[\]]|\[[^\[\]]*\])*\]\(\s*(<[^>]*>|[^)\s]+)(?:\s+(?:\"[^\"]*\"|'[^']*'|\([^)]*\)))?\s*\)")
# [label]: target "title"
REF_DEF = re.compile(r"^ {0,3}\[[^\]]+\]:\s*(<[^>]*>|\S+)")
HTML_ATTR = re.compile(r"""<(?:a|img|source)\b[^>]*?\b(?:href|src)\s*=\s*["']([^"']+)["']""", re.IGNORECASE)
SCHEME = re.compile(r"^[A-Za-z][A-Za-z0-9+.-]*:")


def markdown_files(include_archive: bool) -> list[Path]:
    files = []
    readme = ROOT / "README.md"
    if readme.is_file():
        files.append(readme)
    docs = ROOT / "docs"
    if docs.is_dir():
        for p in sorted(docs.rglob("*.md")):
            if p.is_file() and (include_archive or ARCHIVE not in p.parents):
                files.append(p)
    return files


def link_targets(text: str):
    """Yield (line_number, raw_target) for every link outside code."""
    fence: str | None = None
    for lineno, line in enumerate(text.splitlines(), start=1):
        m = FENCE.match(line)
        if fence is not None:
            if m and m.group(1)[0] == fence[0] and len(m.group(1)) >= len(fence):
                fence = None
            continue
        if m:
            fence = m.group(1)
            continue
        stripped = CODE_SPAN.sub("", line)
        for rx in (INLINE_LINK, HTML_ATTR):
            for match in rx.finditer(stripped):
                yield lineno, match.group(1)
        ref = REF_DEF.match(stripped)
        if ref:
            yield lineno, ref.group(1)


def check_links(path: Path) -> list[str]:
    problems = []
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        return [f"{rel(path)}: cannot read: {exc}"]
    for lineno, raw in link_targets(text):
        target = raw.strip()
        if target.startswith("<") and target.endswith(">"):
            target = target[1:-1].strip()
        if not target or target.startswith("#") or target.startswith("//") or SCHEME.match(target):
            continue
        target = target.split("#", 1)[0].split("?", 1)[0]
        if not target:
            continue
        target = unquote(target)
        resolved = (ROOT / target.lstrip("/")) if target.startswith("/") else (path.parent / target)
        if not resolved.exists():
            problems.append(f"{rel(path)}:{lineno}: broken link {raw!r} (resolved to {rel(resolved)})")
    return problems


def check_decisions() -> list[str]:
    if not DECISIONS.is_dir():
        return []
    problems = []
    for p in sorted(DECISIONS.iterdir()):
        if p.is_dir():
            problems.append(f"{rel(p)}: unexpected directory in docs/decisions/")
        elif not ADR_NAME.match(p.name):
            problems.append(f"{rel(p)}: decision record must be named ADR-NNNN-<slug>.md")
    return problems


def rel(path: Path) -> str:
    try:
        return path.resolve().relative_to(ROOT).as_posix()
    except ValueError:
        return str(path)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--include-archive", action="store_true", help="also check docs/archive/ (verbatim, not editable)")
    args = ap.parse_args(argv)
    files = markdown_files(args.include_archive)
    problems: list[str] = []
    for f in files:
        problems.extend(check_links(f))
    problems.extend(check_decisions())
    for p in problems:
        print(f"FAIL {p}")
    adrs = len(list(DECISIONS.glob("*.md"))) if DECISIONS.is_dir() else 0
    summary = f"check_docs: {len(files)} Markdown file(s), {adrs} decision record(s), {len(problems)} problem(s)"
    print(summary)
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
