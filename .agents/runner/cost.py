#!/usr/bin/env python3
"""What a cycle step costs in plan quota, measured, so the wheel only starts a step that fits. Usage:

  cost.py estimate KIND [--units N]       expected `<session %> <week %>` for one step (merge: N candidates)
  cost.py record KIND UNITS S0 W0 S1 W1   append one measured step (readings before/after) to agent-runs/costs.jsonl
  cost.py fits KIND --units N --session S --week W --stop-at A --week-max B
                                          exit 0 if S + est <= A and W + est <= B, else 1 (reason printed)
The estimate is the median of the measured steps of that kind (per unit), or the seed below until three exist.
Seeds: /usage deltas of 2026-11-19 (docs runs 4-6 % session / ~0.5 % week each; merge 30 % / 2 % for 10 candidates;
plan 18 % / 2 %). The review seed is a guess (the committee never ran). /usage reports whole percents, so a single
week delta is coarse; the median over many steps is what counts.
"""
import argparse
import json
import statistics
import subprocess
import sys
from pathlib import Path

SEED = {"run": (6.0, 0.5), "merge": (3.5, 0.3), "plan": (18.0, 2.0), "review": (10.0, 1.0)}


def store() -> Path:
    common = subprocess.run(["git", "rev-parse", "--path-format=absolute", "--git-common-dir"],
                            capture_output=True, text=True, cwd=Path(__file__).parent).stdout.strip()
    return Path(common) / "agent-runs" / "costs.jsonl"


def estimate(kind, units=1):
    rows = [json.loads(l) for l in store().read_text().splitlines()] if store().exists() else []
    rows = [r for r in rows if r["kind"] == kind and r["units"] > 0]
    if len(rows) >= 3:
        s = statistics.median(r["session"] / r["units"] for r in rows)
        w = statistics.median(r["week"] / r["units"] for r in rows)
        src = f"median of {len(rows)} measured"
    else:
        s, w = SEED.get(kind, (10.0, 1.0))
        src = "seed"
    return s * units, w * units, src


def main():
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="cmd", required=True)
    e = sub.add_parser("estimate")
    e.add_argument("kind")
    e.add_argument("--units", type=int, default=1)
    r = sub.add_parser("record")
    r.add_argument("kind")
    for n in ("units", "s0", "w0", "s1", "w1"):
        r.add_argument(n, type=int)
    f = sub.add_parser("fits")
    f.add_argument("kind")
    for n in ("units", "session", "week", "stop_at", "week_max"):
        f.add_argument(f"--{n.replace('_', '-')}", dest=n, type=int, required=True)
    a = p.parse_args()
    if a.cmd == "estimate":
        s, w, src = estimate(a.kind, a.units)
        print(f"{s:.1f} {w:.1f} ({src})")
    elif a.cmd == "record":
        with open(store(), "a") as fh:
            fh.write(json.dumps({"kind": a.kind, "units": a.units, "session": a.s1 - a.s0, "week": a.w1 - a.w0,
                                 "s0": a.s0, "w0": a.w0}) + "\n")
    else:
        s, w, src = estimate(a.kind, a.units)
        if a.session + s > a.stop_at:
            print(f"does not fit: session {a.session}% + ~{s:.1f}% ({a.kind} x{a.units}, {src}) > {a.stop_at}%")
            sys.exit(1)
        if a.week + w > a.week_max:
            print(f"does not fit: week {a.week}% + ~{w:.1f}% ({a.kind} x{a.units}, {src}) > {a.week_max}%")
            sys.exit(1)
        print(f"fits: session {a.session}+{s:.1f} <= {a.stop_at}, week {a.week}+{w:.1f} <= {a.week_max} ({src})")


if __name__ == "__main__":
    main()
