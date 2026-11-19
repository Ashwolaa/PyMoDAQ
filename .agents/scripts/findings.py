#!/usr/bin/env python3
"""Findings that do not come from a scan (e.g. CI failures upstream/dev has too). /optimize-plan reads the open ones
of its scope and gives them to triage and the decisioners, so each becomes a task only through the deliberation.

  findings.py add --scope S --kind ci-upstream --key K --title T --evidence URL [--evidence URL] [--source RUN_ID]
      K identifies the problem (e.g. "tests-pymodaq.yml|tests (ubuntu-latest, pyside6)|crash"): adding the same key
      again only appends new evidence and bumps `seen`, so one problem stays one finding
  findings.py list [--scope S] [--status open|planned|closed]
  findings.py set-status --key K --status open|planned|closed [--task-id T] [--note TXT]
Stored in .agents/findings.jsonl (one JSON object per line), on dev_agent only.
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import AGENTS_DIR, fail, read_jsonl, require_state_branch, today

FILE = "findings.jsonl"
STATUSES = ("open", "planned", "closed")
KINDS = ("ci-upstream", "review", "run", "plugin")


def write(rows):
    (AGENTS_DIR / FILE).write_text("".join(json.dumps(r, sort_keys=True) + "\n" for r in rows))


def cmd_add(a):
    require_state_branch()
    rows = read_jsonl(FILE)
    hit = next((r for r in rows if r["key"] == a.key and r["status"] != "closed"), None)
    if hit:
        new = [e for e in a.evidence if e not in hit["evidence"]]
        hit["evidence"] += new
        hit["seen"] += 1
        hit["last_seen"] = today()
        if a.source and a.source not in hit["sources"]:
            hit["sources"].append(a.source)
        write(rows)
        print(f"findings: {a.key} seen again ({hit['seen']}x, status {hit['status']}, {len(new)} new evidence)")
        return
    rows.append({"key": a.key, "scope": a.scope, "kind": a.kind, "title": a.title, "evidence": a.evidence,
                 "sources": [a.source] if a.source else [], "first_seen": today(), "last_seen": today(),
                 "seen": 1, "status": "open", "task_id": None, "note": ""})
    write(rows)
    print(f"findings: added {a.key} ({a.scope})")


def cmd_list(a):
    for r in read_jsonl(FILE):
        if (a.scope is None or r["scope"] == a.scope) and (a.status is None or r["status"] == a.status):
            print(f"{r['status']:8} {r['scope']:18} seen {r['seen']}x  {r['title']}\n"
                  f"         key: {r['key']}\n         evidence: {', '.join(r['evidence'][:3])}"
                  + (f"\n         task: {r['task_id']}" if r["task_id"] else ""))


def cmd_set_status(a):
    require_state_branch()
    rows = read_jsonl(FILE)
    hit = [r for r in rows if r["key"] == a.key]
    if not hit:
        fail(f"unknown finding: {a.key}")
    for r in hit:
        r["status"] = a.status
        if a.task_id:
            r["task_id"] = a.task_id
        if a.note:
            r["note"] = a.note
    write(rows)
    print(f"findings: {a.key} -> {a.status}")


def main():
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="cmd", required=True)
    add = sub.add_parser("add")
    add.add_argument("--scope", required=True)
    add.add_argument("--kind", choices=KINDS, required=True)
    add.add_argument("--key", required=True)
    add.add_argument("--title", required=True)
    add.add_argument("--evidence", action="append", default=[])
    add.add_argument("--source", default=None, help="run id that saw it")
    add.set_defaults(fn=cmd_add)
    ls = sub.add_parser("list")
    ls.add_argument("--scope", default=None)
    ls.add_argument("--status", choices=STATUSES, default=None)
    ls.set_defaults(fn=cmd_list)
    st = sub.add_parser("set-status")
    st.add_argument("--key", required=True)
    st.add_argument("--status", choices=STATUSES, required=True)
    st.add_argument("--task-id", default=None)
    st.add_argument("--note", default="")
    st.set_defaults(fn=cmd_set_status)
    a = p.parse_args()
    a.fn(a)


if __name__ == "__main__":
    main()
