#!/usr/bin/env python3
"""Run ledger. Usage:

  ledger.py add --run-id R --command optimize-plan --scope pymodaq_utils --mode explain \
      [--tokens-in N --tokens-out N] [--specialist-runs N] [--prs-opened N] --outcome ok|failed|limit|budget [--note TXT]
  ledger.py summary [--date YYYY-MM-DD]
Token figures are optional: omit them rather than guess (stored as null).
"""
import argparse
from collections import defaultdict

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import append_jsonl, read_jsonl, today

OUTCOMES = ("ok", "failed", "limit", "budget")


def cmd_add(a):
    append_jsonl("ledger.jsonl", {
        "run_id": a.run_id, "date": a.date or today(), "command": a.command, "scope": a.scope,
        "mode": a.mode, "model_tier": a.model_tier, "tokens_in": a.tokens_in, "tokens_out": a.tokens_out,
        "specialist_runs": a.specialist_runs, "prs_opened": a.prs_opened, "outcome": a.outcome, "note": a.note,
    })
    print(f"ledger: recorded {a.run_id}")


def cmd_summary(a):
    day = a.date or today()
    rows = [r for r in read_jsonl("ledger.jsonl") if r["date"] == day]
    tot = defaultdict(int)
    for r in rows:
        for k in ("tokens_in", "tokens_out", "specialist_runs", "prs_opened"):
            tot[k] += r.get(k) or 0
    unknown = sum(1 for r in rows if r.get("tokens_in") is None)
    print(f"{day}: {len(rows)} runs, specialist_runs={tot['specialist_runs']}, prs_opened={tot['prs_opened']}, "
          f"tokens_in={tot['tokens_in']}, tokens_out={tot['tokens_out']} ({unknown} runs without token figures)")
    for o in OUTCOMES:
        n = sum(1 for r in rows if r["outcome"] == o)
        if n:
            print(f"  outcome {o}: {n}")


def main():
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="cmd", required=True)
    add = sub.add_parser("add")
    add.add_argument("--run-id", required=True)
    add.add_argument("--command", required=True)
    add.add_argument("--scope", default="all")
    add.add_argument("--mode", choices=("explain", "run"), default="run")
    add.add_argument("--model-tier", default=None)
    add.add_argument("--tokens-in", type=int, default=None)
    add.add_argument("--tokens-out", type=int, default=None)
    add.add_argument("--specialist-runs", type=int, default=0)
    add.add_argument("--prs-opened", type=int, default=0)
    add.add_argument("--outcome", choices=OUTCOMES, required=True)
    add.add_argument("--note", default="")
    add.add_argument("--date", default=None)
    add.set_defaults(fn=cmd_add)
    s = sub.add_parser("summary")
    s.add_argument("--date", default=None)
    s.set_defaults(fn=cmd_summary)
    a = p.parse_args()
    a.fn(a)


if __name__ == "__main__":
    main()
