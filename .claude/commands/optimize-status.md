---
description: Show today's budget use, task queue, blocked items and recent agent PRs
---

Read-only. First `python3 .agents/scripts/status.py` (the generated status page: needs-you, in flight, findings, recent runs) and show it. Then run, from the repository root:
- `python3 .agents/scripts/ledger.py summary`
- `python3 .agents/scripts/budget.py check` and `budget.py disable-check`
- `python3 .agents/scripts/registry.py list --status pushed` (branches awaiting /optimize-merge) and `--status open` (PRs awaiting the human)
- `python3 .agents/scripts/usage.py snapshots` (last 3 lines) and `usage.py calibrate`

Then count tasks by status in the newest files of `.agents/plans/`, list every `blocked` item with its one-line reason, and show the "Next step" line of each `.agents/handoff/*.md`. Report in <= 25 lines. State plainly any figure that is missing (for example token counts logged as null) instead of estimating it.
