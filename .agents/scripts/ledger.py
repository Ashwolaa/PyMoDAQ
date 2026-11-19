#!/usr/bin/env python3
"""Run ledger. Usage:

  ledger.py add --run-id R --command optimize-plan --scope pymodaq_utils --mode explain \
      [--session current --since START] [--specialist-runs N] [--prs-opened N] [--reviews N] \
      --outcome ok|failed|limit|budget [--note TXT]
  ledger.py summary [--date YYYY-MM-DD]
With --session (an id, or `current` = $CLAUDE_CODE_SESSION_ID) and --since (the run's start, ISO UTC) the token
figures are measured from the transcripts by usage.py. Otherwise omit them rather than guess (stored as null);
--tokens-in/--tokens-out exist for runs measured elsewhere (cloud).
"""
import argparse
from collections import Counter, defaultdict

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import append_jsonl, read_jsonl, require_state_branch, today

OUTCOMES = ("ok", "failed", "limit", "budget")


def measured(session: str, since):
    """Token figures of this run, read from the session transcripts (main session + its sub-agents)."""
    import usage
    since = usage.parse_ts(since) if since else None
    rows = [r for r in usage.requests(usage.resolve_session(session), since) if not r["dup"] or r["tools"]]
    tot = usage.aggregate(rows).get("total")
    if not tot:
        return {}
    by_agent = usage.aggregate(rows, "agent")
    launches = Counter(agent for agent, _ in {(r["agent"], r["transcript"]) for r in rows if r["agent"] != "main"})
    return {
        "session_id": rows[0]["session"], "started": tot["first"], "ended": tot["last"], "minutes": tot["minutes"],
        "tokens_in": tot["input"] + tot["cache_write"], "tokens_cache_read": tot["cache_read"],
        "tokens_out": tot["output"], "requests": tot["requests"], "tool_calls": tot["tool_calls"],
        "out_by_agent": {k: g["output"] for k, g in by_agent.items()},
        "launches": dict(launches),  # sub-agent launches by type (one transcript each)
        "_specialists": sum(n for k, n in launches.items() if k.startswith("spec-") or k == "test-agent"),
        "_reviews": launches.get("pr-reviewer", 0),
    }


def cmd_add(a):
    require_state_branch()
    rec = {
        "run_id": a.run_id, "date": a.date or today(), "command": a.command, "scope": a.scope,
        "mode": a.mode, "model_tier": a.model_tier, "tokens_in": a.tokens_in, "tokens_out": a.tokens_out,
        "specialist_runs": a.specialist_runs, "prs_opened": a.prs_opened, "reviews": a.reviews, "outcome": a.outcome, "note": a.note,
    }
    if a.session:
        m = measured(a.session, a.since)
        if not m:
            print("ledger: no requests found for that session/window, token figures left null", file=sys.stderr)
        # counted, not reported: a run that forgets to pass --specialist-runs/--reviews still uses the budget
        rec["specialist_runs"] = max(rec["specialist_runs"] or 0, m.pop("_specialists", 0))
        rec["reviews"] = max(rec["reviews"] or 0, m.pop("_reviews", 0))
        for k, v in m.items():  # explicit --tokens-in/--tokens-out win over measured figures
            if rec.get(k) is None:
                rec[k] = v
    append_jsonl("ledger.jsonl", rec)
    print(f"ledger: recorded {a.run_id}" + (f" ({rec['tokens_out']} output tokens)" if rec["tokens_out"] else ""))


def cmd_summary(a):
    day = a.date or today()
    rows = [r for r in read_jsonl("ledger.jsonl") if r["date"] == day]
    tot = defaultdict(int)
    for r in rows:
        for k in ("tokens_in", "tokens_cache_read", "tokens_out", "specialist_runs", "prs_opened", "reviews", "minutes"):
            tot[k] += r.get(k) or 0
    unknown = sum(1 for r in rows if r.get("tokens_in") is None)
    print(f"{day}: {len(rows)} runs, specialist_runs={tot['specialist_runs']}, prs_opened={tot['prs_opened']}, reviews={tot['reviews']}, "
          f"tokens_in={tot['tokens_in']}, cache_read={tot['tokens_cache_read']}, tokens_out={tot['tokens_out']}, "
          f"minutes={round(tot['minutes'], 1)} ({unknown} runs without token figures)")
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
    add.add_argument("--reviews", type=int, default=0, help="pr-reviewer launches (/optimize-merge)")
    add.add_argument("--session", default=None, help="session id or 'current': measure tokens from transcripts")
    add.add_argument("--since", default=None, help="run start (ISO UTC), with --session")
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
