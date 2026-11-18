---
description: Executive: carry out approved tasks of the plan on agent branches within the budget
argument-hint: "[scope | task-id] [--explain]"
---

You are the coordinator of the executive. Arguments: `$ARGUMENTS`. Scope = package or `package/slice`, a task id (`T-...`), or empty to take the next scope with approved tasks in dependency order.

0. Note the start time first: `date -u +%FT%TZ` (START). The ledger measures this run's tokens from it.
1. Read `.agents/core/layers.md`, `.agents/core/rules.md`, `.agents/profile.toml`. Run `python3 .agents/scripts/budget.py check` and `budget.py disable-check`; stop on STOP/DISABLE after writing the handoff.
2. If `.agents/budget.toml` `[pilot] mode = "explain"` or `--explain` is given: list what you would do, write `.agents/reports/<scope>/<date>-run.md`, change nothing else.
3. Make sure you are on `dev_agent` (see `scripts/sync_branches.sh`); never touch `dev`.
4. Adopt the cocoordinator role (`.claude/agents/cocoordinator.md`) for the scope. Create one branch per task `agent/<scope>/<specialty>/<date>` and register it with `scripts/registry.py add`.
5. Launch the specialist for each approved task with a folder-level scope. For tests launch one `test-agent` instance per test folder. Check `budget.py check` between tasks.
6. Before any push run `[checks]` for the touched scope (and the layering test). If a check fails, fix or stop; never skip or weaken a test.
7. Open a **draft** PR on the fork against `dev_agent` with the `agent-made` label and the trailer `Agent-Run: <run-id>`. Never open a PR upstream.
8. Launch the `auditor`; overwrite `.agents/handoff/<scope>.md` (<= 40 lines, template in `handoff/_template.md`).
9. Log with `scripts/ledger.py add ... --session current --since <START>`, then report in <= 20 lines.

Handle a rate-limit error by writing the handoff, logging `--outcome limit --session current --since <START>` and stopping.
