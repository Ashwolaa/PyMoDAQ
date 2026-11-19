# .agents — optimization consortium

Agent-driven optimization of this fork. Nothing here is part of the PyMoDAQ distribution.

```
.agents/
  core/        generic part: rules, layers, formats (reusable on any repo)
  profile.toml project part: scopes, commands, hard rules, specialists
  budget.toml  daily caps and reset time (edited by a human)
  scripts/     ledger.py, registry.py, budget.py, usage.py (token metrics), scan.py (advisor input), plan.py (task status), pr_stats.py, sync_branches.sh
  plans/       one plan per planning run (advisory board output)
  handoff/     one capped file per package: how to resume
  reports/     readable reports per folder (runs, audits, reviews)
  practices/   what worked per folder (best-practice agent)
  research/    R&D notes
  registry.jsonl  every agent branch/PR   ledger.jsonl  every run and its cost
```

Commands (in `.claude/commands/`): `/optimize-plan`, `/optimize-run`, `/optimize-status`,
`/optimize-revert`, `/optimize-research`, `/optimize-review`. All take `--explain` (dry run, changes nothing).
Agents live in `.claude/agents/`.

Start with `/optimize-plan pymodaq_utils --explain`.

Core and profile are kept apart on purpose: only `profile.toml` and `budget.toml` are specific to this repo.
Read `core/layers.md` first, then `core/rules.md` and `core/formats.md`.
