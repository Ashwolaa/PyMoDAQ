#!/usr/bin/env python3
"""Set the status of one task in a plan file (the only way runs change a plan).
Usage:
  plan.py set-status <plan.md> <task-id> "done — draft PR #5, CI green"
  plan.py show <plan.md> [--status [approved]]
The status text must start with one of: proposed, approved, done, blocked, expired (formats.md).
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import require_state_branch
from agentlib import plans

STATUSES = plans.STATUSES


def cmd_set_status(a):
    require_state_branch()
    plans.set_status(a.plan, a.task_id, a.status)
    print(f"plan: {a.task_id} -> {a.status}")


def cmd_show(a):
    for t in plans.parse(plans.resolve(a.plan)):
        if not a.status or t.status.startswith(a.status):
            print(f"{t.id:26} {t.status or '?'}")


def main():
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("set-status")
    s.add_argument("plan"); s.add_argument("task_id"); s.add_argument("status")
    s.set_defaults(fn=cmd_set_status)
    v = sub.add_parser("show")
    v.add_argument("plan"); v.add_argument("--status", nargs="?", const=None, default=None)
    v.set_defaults(fn=cmd_show)
    a = p.parse_args()
    a.fn(a)


if __name__ == "__main__":
    main()
