"""pr-reviewer reports (`.agents/reports/<package>/<date>-pr-review-<task-id>[-r<N>].md`).

They start with the four header lines `verdict:`, `public_api:`, `behaviour_change:`, `fails_without_fix:`, end with
`summary: <one sentence>`, and list problems outside the reviewed change as `outside: <key> | <title>` lines, which
merge.py files as findings (rules.md 18).
"""
import re
from pathlib import Path

from _common import AGENTS_DIR

HEADER = ("verdict", "public_api", "behaviour_change", "fails_without_fix")


def header(path) -> dict:
    """The header fields; the first occurrence wins (a later 'verdict:' in the body must not override it)."""
    out = {}
    for m in re.finditer(r"^([a-z_]+):\s*(\S+)", Path(path).read_text(), re.M):
        if m.group(1) in HEADER:
            out.setdefault(m.group(1), m.group(2).strip("`*").lower())
    return out


def summary(path) -> str:
    m = re.search(r"^summary:\s*(.*)$", Path(path).read_text(), re.M)
    return m.group(1).strip() if m else ""


def notes(path, limit=8) -> list:
    """Finding lines that cite a path:line."""
    return [l for l in Path(path).read_text().splitlines() if re.match(r"^\s*[-*] .*:\d+", l)][:limit]


def outside(path) -> list:
    """[(key, title)] from `outside: <key> | <title>` lines."""
    out = []
    for m in re.finditer(r"^outside:\s*(.+?)\s+\|\s+(.+)$", Path(path).read_text(), re.M):  # keys may hold '|' 
        out.append((m.group(1).strip(), m.group(2).strip()))
    return out


def round_of(path) -> int:
    """Review round of a report: `-r<N>` in the name, 1 for the older names without it."""
    m = re.search(r"-r(\d+)\.md$", Path(path).name)
    return int(m.group(1)) if m else 1


def for_task(package, task_id) -> list:
    """The task's review reports, oldest round first. Not a plain sort: 'X-r2.md' sorts before 'X.md' ('-' < '.'),
    which made an r1 report look like the latest one."""
    found = (AGENTS_DIR / "reports" / package).glob(f"*-pr-review-{task_id}*.md")
    return sorted(found, key=lambda p: (round_of(p), p.name))


def changes_rounds(package, task_id) -> int:
    return sum(1 for p in for_task(package, task_id) if header(p).get("verdict") == "changes")
