---
description: Advisory board: scan a scope, deliberate, and write a plan of tasks (never edits code)
argument-hint: "[scope] [--explain]"
---

You are the coordinator of the advisory board. Arguments: `$ARGUMENTS`. Scope = a package, `package/slice`, or empty for every package in `.agents/profile.toml` `[scopes].order`. Without `--explain` the plan is written; with it, only a report in `.agents/reports/`.

0. Note the start time first: `date -u +%FT%TZ` (START). The ledger measures this run's tokens from it.
1. Read `.agents/core/layers.md`, `.agents/core/rules.md`, `.agents/profile.toml`, `.agents/budget.toml`. Run `python3 .agents/scripts/budget.py check`; stop on STOP.
2. Read `.agents/handoff/<scope>.md` and `.agents/practices/<scope>.md` if they exist.
3. Scan with tools, not by reading the package: for the scope run the scanners from `[tools].scanners` that are installed (ruff, vulture, jscpd, radon; coverage/mutmut only on small slices). Report any missing scanner instead of imitating it; if none is available, write the report, log `--outcome failed` and stop. Keep ranked output to the top ~30 findings.
4. Launch the advisors in parallel, each with that scan output only: advisor-quality, -performance, -docs, -compat, plus advisor-uxui only when the scope is in `[scopes].ui`.
5. Launch decider-triage to keep findings worth a task, each fitting one PR.
6. For each kept finding launch decider-compat-risk and a second decisioner (decider-test-change for anything touching tests, else a fresh decider-triage) in parallel. Apply the deliberation rule in `.agents/core/layers.md` (second round on disagreement, then `blocked`). Use decider-arbiter for tasks touching the same file.
7. Write `.agents/plans/<date>-<scope>.md` following `plans/_template.md`: low-risk tasks both decisioners approved are `approved`; tests, UI and public API stay `proposed`.
8. Record the run: `python3 .agents/scripts/ledger.py add --run-id <id> --command optimize-plan --scope <scope> --mode <explain|run> --session current --since <START> --outcome ok` (tokens are measured, never typed in).
9. Report in <= 20 lines: tasks by status, blocked items needing the human, scanners that were missing.

Per `.agents/budget.toml` `[pilot]`, treat every run as `--explain` while `mode = "explain"`.
