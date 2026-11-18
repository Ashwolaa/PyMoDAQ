#!/usr/bin/env python3
"""Budget gate. Usage:

  budget.py check [--kind executive|rd]   exit 0 = go, exit 1 = stop (reason printed), exit 2 = error
  budget.py disable-check                 exit 1 if the schedule should disable itself

Caps come from budget.toml. They are lowered to ceil(cap * 0.7) when the most recent run ended with
outcome=limit and [safety] lower_caps_after_limit_hit is true. Counts come from ledger.jsonl.
Real plan quota cannot be read from a session: this is a self-imposed ceiling only.
"""
import argparse
import math
import sys

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import load_toml, read_jsonl, today


def caps():
    cfg = load_toml("budget.toml")
    daily = dict(cfg["daily"])
    rows = read_jsonl("ledger.jsonl")
    if cfg["safety"].get("lower_caps_after_limit_hit") and rows and rows[-1]["outcome"] == "limit":
        for k in ("cocoordinators", "specialist_runs", "prs_opened", "runs"):
            daily[k] = max(1, math.ceil(daily[k] * 0.7))
        print("note: caps lowered after a limit hit", file=sys.stderr)
    return cfg, daily, rows


def cmd_check(a):
    cfg, daily, rows = caps()
    day = [r for r in rows if r["date"] == today() and (r["command"] == "optimize-research") == (a.kind == "rd")]
    if a.kind == "rd":
        # R&D draws on its own slice of the daily run budget
        allowed = max(1, math.floor(daily["runs"] * daily["rd_share"] * 5))
        if len(day) >= allowed:
            print(f"STOP: rd runs today {len(day)} >= {allowed}")
            sys.exit(1)
        print("GO")
        return
    used = {
        "runs": len(day),
        "specialist_runs": sum(r.get("specialist_runs") or 0 for r in day),
        "prs_opened": sum(r.get("prs_opened") or 0 for r in day),
    }
    for k, v in used.items():
        if v >= daily[k]:
            print(f"STOP: {k} {v} >= cap {daily[k]}")
            sys.exit(1)
    print(f"GO: used {used}, caps runs={daily['runs']} specialist_runs={daily['specialist_runs']} prs={daily['prs_opened']}")


def cmd_disable(a):
    cfg, daily, rows = caps()
    n = cfg["safety"]["disable_after_consecutive_failures"]
    tail = rows[-n:]
    if len(tail) == n and all(r["outcome"] == "failed" for r in tail):
        print(f"DISABLE: last {n} runs failed")
        sys.exit(1)
    if cfg["safety"]["disable_if_day_over_budget"] and any(
        r["date"] == today() and r["outcome"] == "budget" for r in rows
    ) and sum(1 for r in rows if r["date"] == today() and r["outcome"] == "budget") > 1:
        print("DISABLE: day over budget")
        sys.exit(1)
    print("OK")


def main():
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("check")
    c.add_argument("--kind", choices=("executive", "rd"), default="executive")
    c.set_defaults(fn=cmd_check)
    d = sub.add_parser("disable-check")
    d.set_defaults(fn=cmd_disable)
    a = p.parse_args()
    a.fn(a)


if __name__ == "__main__":
    main()
