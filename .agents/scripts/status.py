#!/usr/bin/env python3
"""The consortium's state in one page, built from the state files only (never edited by hand). Usage:

  status.py [--write]      print STATUS.md (--write: also write .agents/STATUS.md)
  status.py queue          approved tasks, one `<task-id> <plan>` per line, in scope order (for runner/cycle.sh)
  status.py pending        branches waiting for /optimize-merge (registry `pushed`, or `open` drafts), one per line
  status.py next           the next step the cycle would take, one line: merge | run <task> <plan> | plan <scope> | review | idle
A new session starts from `.agents/BRIEFING.md` (design) and `.agents/STATUS.md` (state).
"""
import argparse
import json
import re
import subprocess
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import AGENTS_DIR, load_toml, read_jsonl, today
from agentlib import plans

PLANS = AGENTS_DIR / "plans"
RETRY = ("blocked — CI red", "blocked — conflicts")


def tasks():
    """(task_id, title, status, plan path, package) for every task of every plan in plans/*.md (not experiments/)."""
    return [(t.id, t.title, t.status or "?", t.plan_rel, plans.package_of(t)) for t in plans.all_tasks()]


def scope_rank(scope):
    order = load_toml("profile.toml")["scopes"]["order"]
    return order.index(scope) if scope in order else len(order)


def queue():
    q = [t for t in tasks() if t[2].startswith("approved") or t[2].startswith(RETRY)
         or t[2].startswith("blocked — review") and "for the human" not in t[2]]
    return sorted(q, key=lambda t: (scope_rank(t[4]), t[3], t[0]))


def pending():
    return [r for r in read_jsonl("registry.jsonl") if r["status"] == "pushed"]


def last_command(cmd):
    rows = [r for r in read_jsonl("ledger.jsonl") if r.get("command") == cmd and r.get("outcome") == "ok"]
    return rows[-1]["date"] if rows else None


def next_step():
    if pending():
        return "merge"
    q = [t for t in queue() if not t[2].startswith("blocked — review")]  # reworks come after fresh tasks
    q = q or queue()
    if q:
        return f"run {q[0][0]} {q[0][3]}"
    cutoff = (date.today() - timedelta(days=7)).isoformat()
    planned = {}
    for p in PLANS.glob("*.md"):
        m = re.match(r"(\d{4}-\d{2}-\d{2})-(\w+?)(?:-[\w-]+)?\.md$", p.name)
        if m:
            planned[m.group(2)] = max(planned.get(m.group(2), ""), m.group(1))
    for scope in load_toml("profile.toml")["scopes"]["order"]:
        if planned.get(scope, "") < cutoff:
            return f"plan {scope}"
    last = last_command("optimize-review")
    if not last or last < cutoff:
        return "review"
    return "idle"


def git(*a):
    return subprocess.run(["git", "-C", str(AGENTS_DIR), *a], capture_output=True, text=True).stdout.strip()


def render():
    L = [f"# Consortium status — generated {datetime.now().strftime('%Y-%m-%d %H:%M')} by `scripts/status.py`",
         "", "Do not edit: regenerate with `python3 .agents/scripts/status.py --write`. Design: `.agents/BRIEFING.md`.", ""]
    # now
    ledger = read_jsonl("ledger.jsonl")
    day = [r for r in ledger if r["date"] == today()]
    caps = load_toml("budget.toml")["daily"]
    used = {"runs": len(day), "specialist_runs": sum(r.get("specialist_runs") or 0 for r in day),
            "prs_opened": sum(r.get("prs_opened") or 0 for r in day), "reviews": sum(r.get("reviews") or 0 for r in day)}
    L += ["## Now", f"- `dev_agent` at `{git('rev-parse', '--short', 'dev_agent')}`; "
          f"{git('rev-list', '--count', 'upstream/dev..dev_agent')} commits ahead of upstream/dev "
          f"({git('diff', '--shortstat', 'upstream/dev', 'dev_agent', '--', ':/packages', ':/docs') or 'no product change'})",
          "- today: " + ", ".join(f"{k} {v}/{caps.get(k, '-')}" for k, v in used.items())
          + f"; outcomes: " + (", ".join(f"{o} {sum(1 for r in day if r['outcome'] == o)}"
                                        for o in ("ok", "failed", "budget", "limit") if any(r["outcome"] == o for r in day)) or "none")]
    snaps = subprocess.run([sys.executable, str(AGENTS_DIR / "scripts" / "usage.py"), "snapshots"],
                           capture_output=True, text=True).stdout.strip().splitlines()
    L += [f"- last /usage reading: {snaps[-1].strip() if snaps else 'none'}", f"- next cycle step: `{next_step()}`", ""]
    # needs you
    all_tasks = tasks()
    proposed = [t for t in all_tasks if t[2].startswith("proposed")]
    human = [t for t in all_tasks if "awaiting the human" in t[2] or "for the human" in t[2]]
    blocked = [t for t in all_tasks if t[2].startswith("blocked") and t not in human]
    L += ["## Needs you"]
    L += [f"- approve or drop **{t[0]}** {t[1]} — {t[2]} (`{t[3]}`)" for t in proposed]
    L += [f"- **{t[0]}** — {t[2]}" for t in human]
    L += [f"- blocked: **{t[0]}** — {t[2]}" for t in blocked if not t[2].startswith(RETRY)]
    if not (proposed or human or blocked):
        L += ["- nothing"]
    L += [""]
    # in flight
    L += ["## In flight"]
    L += [f"- `{r['branch']}` ({r['task_id']}, risk {r['risk']}): pushed, waiting for /optimize-merge" for r in pending()]
    L += [f"- {t[0]} {t[1]} — {t[2]}" for t in queue()]
    if not (pending() or queue()):
        L += ["- nothing queued"]
    L += [""]
    # findings
    open_f = [f for f in read_jsonl("findings.jsonl") if f["status"] == "open"]
    L += ["## Open findings (go to the next /optimize-plan of their scope)"]
    L += [f"- [{f['scope']}] {f['title'][:150]}" for f in open_f] or ["- none"]
    L += [""]
    # recent
    L += ["## Recent runs", "| run | command | outcome | min | out tok | note |", "|---|---|---|---|---|---|"]
    for r in ledger[-10:]:
        note = (r.get("note") or "").replace("|", "/")[:70]
        L.append(f"| {r['run_id']} | {r['command']} | {r['outcome']} | {r.get('minutes') or ''} | {r.get('tokens_out') or ''} | {note} |")
    L += ["", "## Done so far",
          f"- tasks done: {sum(1 for t in all_tasks if t[2].startswith('done'))}; PRs merged into dev_agent: "
          f"{sum(1 for r in read_jsonl('registry.jsonl') if r['status'] == 'merged')}"]
    return "\n".join(L) + "\n"


def main():
    p = argparse.ArgumentParser()
    p.add_argument("what", nargs="?", default="show", choices=("show", "queue", "pending", "next"))
    p.add_argument("--write", action="store_true")
    a = p.parse_args()
    if a.what == "queue":
        for t in queue():
            print(t[0], t[3])
    elif a.what == "pending":
        for r in pending():
            print(r["branch"], r["task_id"])
    elif a.what == "next":
        print(next_step())
    else:
        text = render()
        if a.write:
            (AGENTS_DIR / "STATUS.md").write_text(text)
            subprocess.run([sys.executable, str(AGENTS_DIR / "scripts" / "docs.py"), "--write"],
                           capture_output=True)  # COMMANDS.md follows the tooling
        print(text, end="")


if __name__ == "__main__":
    main()
