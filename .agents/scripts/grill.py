#!/usr/bin/env python3
"""Grill requests: an agent that cannot choose a direction writes the questions down for the owner instead of guessing.

  grill.py add --topic T --scope S --file .agents/grill/T.md [--source RUN_ID]
      registers a request after checking the file (a `## Decision` section, 3-7 numbered questions, each with a
      `Recommended:` line) and the cap `[grill].max_open` of budget.toml; refuses when either fails
  grill.py list [--status open|answered|dropped]
  grill.py answer --topic T [--status answered|dropped]   (after /optimize-grill recorded the answers in the file)
Stored in .agents/grill.jsonl, on dev_agent only. The agent writes `.agents/grill/<topic>.md`; the owner answers with
`/optimize-grill <topic>`; the next /optimize-plan or /optimize-research reads answered requests as constraints.
"""
import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import AGENTS_DIR, fail, load_toml, read_jsonl, require_state_branch, today
import json

FILE = "grill.jsonl"
STATUSES = ("open", "answered", "dropped")
MIN_Q, MAX_Q = 3, 7


def write(rows):
    (AGENTS_DIR / FILE).write_text("".join(json.dumps(r, sort_keys=True) + "\n" for r in rows))


def max_open() -> int:
    try:
        return int(load_toml("budget.toml").get("grill", {}).get("max_open", 2))
    except OSError:
        return 2


def check_file(text: str) -> list:
    """Problems that make a grill request unusable; empty means fine."""
    problems = []
    if not re.search(r"^## Decision\b", text, re.M):
        problems.append("missing a `## Decision` section (what you are stuck on, and why it changes the work)")
    questions = re.findall(r"^\d+\.\s", text, re.M)
    if not MIN_Q <= len(questions) <= MAX_Q:
        problems.append(f"{len(questions)} numbered questions, want {MIN_Q}-{MAX_Q}")
    if len(re.findall(r"^\s*-?\s*Recommended:", text, re.M)) < len(questions):
        problems.append("every question needs a `Recommended:` line")
    return problems


def cmd_add(a):
    require_state_branch()
    path = Path(a.file)
    if not path.is_absolute():
        path = AGENTS_DIR.parent / path
    if not path.exists():
        fail(f"grill: {a.file} does not exist")
    problems = check_file(path.read_text())
    if problems:
        fail("grill: request refused:\n- " + "\n- ".join(problems))
    rows = read_jsonl(FILE)
    if any(r["topic"] == a.topic and r["status"] == "open" for r in rows):
        print(f"grill: {a.topic} is already open")
        return
    n_open = sum(1 for r in rows if r["status"] == "open")
    if n_open >= max_open():
        fail(f"grill: {n_open} requests already open (cap {max_open()}): work without asking, "
             f"make the safest choice and note it in your report", 3)
    rows.append({"topic": a.topic, "scope": a.scope, "file": a.file, "source": a.source, "opened": today(),
                 "status": "open"})
    write(rows)
    print(f"grill: opened {a.topic}; the owner answers with /optimize-grill {a.topic}")


def cmd_list(a):
    for r in read_jsonl(FILE):
        if a.status is None or r["status"] == a.status:
            print(f"{r['status']:9} {r['scope']:18} {r['topic']}  ({r['file']}, opened {r['opened']})")


def cmd_answer(a):
    require_state_branch()
    rows = read_jsonl(FILE)
    hit = next((r for r in rows if r["topic"] == a.topic and r["status"] == "open"), None)
    if not hit:
        fail(f"grill: no open request for {a.topic}")
    hit["status"] = a.status
    hit["closed"] = today()
    write(rows)
    print(f"grill: {a.topic} -> {a.status}")


def main():
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="cmd", required=True)
    add = sub.add_parser("add")
    add.add_argument("--topic", required=True)
    add.add_argument("--scope", required=True)
    add.add_argument("--file", required=True)
    add.add_argument("--source", default=None)
    add.set_defaults(fn=cmd_add)
    ls = sub.add_parser("list")
    ls.add_argument("--status", choices=STATUSES)
    ls.set_defaults(fn=cmd_list)
    ans = sub.add_parser("answer")
    ans.add_argument("--topic", required=True)
    ans.add_argument("--status", choices=("answered", "dropped"), default="answered")
    ans.set_defaults(fn=cmd_answer)
    a = p.parse_args()
    a.fn(a)


if __name__ == "__main__":
    main()
