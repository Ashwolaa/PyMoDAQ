#!/usr/bin/env python3
"""Set the status of one task in a plan file (the only way runs change a plan).

  plan.py set-status <plan.md> <task-id> "done — draft PR #5, CI green"
  plan.py show <plan.md> [--status approved]

The status text must start with one of: proposed, approved, done, blocked, expired (formats.md).
Runs on the integration branch only, like the ledger and the registry.
"""
import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import AGENTS_DIR, fail, require_state_branch

STATUSES = ("proposed", "approved", "done", "blocked", "expired")


def plan_path(p: str) -> Path:
    path = Path(p)
    if not path.is_absolute() and not path.exists():
        path = AGENTS_DIR / "plans" / p
    if not path.exists():
        fail(f"plan not found: {p}")
    return path


def blocks(text: str):
    """Yield (task_id, start, end) for each '## T-...' block."""
    heads = [(m.group(1), m.start()) for m in re.finditer(r"^## (T-[\w.-]+)", text, re.M)]
    nxt = [m.start() for m in re.finditer(r"^## ", text, re.M)]
    for tid, start in heads:
        end = next((n for n in nxt if n > start), len(text))
        yield tid, start, end


def cmd_set_status(a):
    require_state_branch()
    if not a.status.split()[0].rstrip("—-:(") in STATUSES:
        fail(f"status must start with one of {STATUSES}")
    path = plan_path(a.plan)
    text = path.read_text()
    for tid, start, end in blocks(text):
        if tid == a.task_id:
            block = text[start:end]
            new, n = re.subn(r"^- status:.*$", f"- status: {a.status}", block, count=1, flags=re.M)
            if not n:
                fail(f"{tid} has no '- status:' line")
            path.write_text(text[:start] + new + text[end:])
            print(f"plan: {tid} -> {a.status}")
            return
    fail(f"{a.task_id} not found in {path.name}")


def cmd_show(a):
    text = plan_path(a.plan).read_text()
    for tid, start, end in blocks(text):
        m = re.search(r"^- status:\s*(.*)$", text[start:end], re.M)
        st = m.group(1) if m else "?"
        if not a.status or st.startswith(a.status):
            print(f"{tid:<26} {st}")


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("set-status")
    s.add_argument("plan"); s.add_argument("task_id"); s.add_argument("status")
    s.set_defaults(fn=cmd_set_status)
    v = sub.add_parser("show")
    v.add_argument("plan"); v.add_argument("--status", nargs="?", const=None, default=None)
    v.set_defaults(fn=cmd_show)
    a = ap.parse_args()
    a.fn(a)


if __name__ == "__main__":
    main()
