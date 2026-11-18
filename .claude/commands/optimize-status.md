---
description: Show today's budget use, task queue, blocked items and recent agent PRs
---

Read-only. Run, from the repository root:
- `python .agents/scripts/ledger.py summary`
- `python .agents/scripts/budget.py check` and `budget.py disable-check`
- `python .agents/scripts/registry.py list --status open`
- `python .agents/scripts/usage.py snapshots` (last 3 lines) and `usage.py calibrate`

Then count tasks by status in the newest files of `.agents/plans/`, list every `blocked` item with its one-line reason, and show the "Next step" line of each `.agents/handoff/*.md`. Report in <= 25 lines. State plainly any figure that is missing (for example token counts logged as null) instead of estimating it.
