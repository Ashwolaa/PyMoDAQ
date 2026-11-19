#!/usr/bin/env python3
"""Branch/PR registry. Usage:

  registry.py add --run-id R --scope S --specialty hygiene --branch agent/S/hygiene/2026-11-18 \
      [--pr N] --risk low|medium|high [--task-id T] [--status open]
  registry.py set-status --branch B --status merged|reverted|closed|open [--pr N]
  registry.py list [--status open]
Branch names must follow agent/<scope>/<specialty>/<date>, agent-tool/<name> or agent-rd/<topic>.
"""
import argparse
import json
import re

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import AGENTS_DIR, append_jsonl, fail, read_jsonl, require_state_branch, today

BRANCH_RE = re.compile(r"^(agent/[\w.-]+/[\w-]+/\d{4}-\d{2}-\d{2}|agent-tool/[\w.-]+|agent-rd/[\w.-]+)$")
STATUSES = ("open", "merged", "reverted", "closed")


def cmd_add(a):
    require_state_branch()
    if not BRANCH_RE.match(a.branch):
        fail(f"invalid branch name: {a.branch}")
    if any(r["branch"] == a.branch for r in read_jsonl("registry.jsonl")):
        fail(f"branch already registered: {a.branch}")
    append_jsonl("registry.jsonl", {
        "run_id": a.run_id, "date": today(), "scope": a.scope, "specialty": a.specialty, "branch": a.branch,
        "pr": a.pr, "status": a.status, "risk": a.risk, "task_id": a.task_id,
    })
    print(f"registry: added {a.branch}")


def cmd_set_status(a):
    require_state_branch()
    rows = read_jsonl("registry.jsonl")
    hit = [r for r in rows if r["branch"] == a.branch]
    if not hit:
        fail(f"unknown branch: {a.branch}")
    for r in hit:
        r["status"] = a.status
        if a.pr is not None:
            r["pr"] = a.pr
    (AGENTS_DIR / "registry.jsonl").write_text("".join(json.dumps(r, sort_keys=True) + "\n" for r in rows))
    print(f"registry: {a.branch} -> {a.status}")


def cmd_list(a):
    for r in read_jsonl("registry.jsonl"):
        if a.status is None or r["status"] == a.status:
            print(f"{r['status']:9} {r['risk']:6} pr={r['pr']} {r['branch']} (run {r['run_id']})")


def main():
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="cmd", required=True)
    add = sub.add_parser("add")
    for name in ("run-id", "scope", "specialty", "branch"):
        add.add_argument(f"--{name}", required=True)
    add.add_argument("--pr", type=int, default=None)
    add.add_argument("--risk", choices=("low", "medium", "high"), required=True)
    add.add_argument("--task-id", default=None)
    add.add_argument("--status", choices=STATUSES, default="open")
    add.set_defaults(fn=cmd_add)
    st = sub.add_parser("set-status")
    st.add_argument("--branch", required=True)
    st.add_argument("--status", choices=STATUSES, required=True)
    st.add_argument("--pr", type=int, default=None)
    st.set_defaults(fn=cmd_set_status)
    ls = sub.add_parser("list")
    ls.add_argument("--status", choices=STATUSES, default=None)
    ls.set_defaults(fn=cmd_list)
    a = p.parse_args()
    a.fn(a)


if __name__ == "__main__":
    main()
