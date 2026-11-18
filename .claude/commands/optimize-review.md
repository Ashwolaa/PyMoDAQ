---
description: Independent committee reviews the use of agents and coordinator roles from the numbers
argument-hint: "[--explain]"
---

The committee reads only `.agents/ledger.jsonl`, `.agents/registry.jsonl`, `.agents/handoff/`, `.agents/reports/` and audit blocks. It never reads source and is never consulted by coordinators during a run.

0. Note the start time first: `date -u +%FT%TZ` (START). The ledger measures this run's tokens from it.
1. Launch `committee-efficiency`, `committee-outcomes` and `committee-governance` in parallel, then have each read the others' findings once and revise (they judge each other).
2. Metrics to compute from the files (state "no data" if absent): tokens per merged PR, merge rate, revert rate, share of tasks ending `blocked`, decisioner vetoes the human overruled, handoff length drift, runs stopped by a limit.
3. Write `.agents/reports/committee/<date>-review.md` (<= 60 lines): findings, ranked suggestions, and global tool ideas drawn from patterns across the reports.
4. Suggestions about agents, commands or roles become `proposed` tasks in a new plan file for the human to approve. The committee may recommend pausing a role; the human confirms. It never edits `.claude/`.
5. Log with `ledger.py add --command optimize-review --session current --since <START>` and report in <= 15 lines.
