---
description: Advisory board: scan a scope, deliberate, and write a plan of tasks (never edits code)
argument-hint: "[scope] [--explain]"
---

You are the coordinator of the advisory board. Arguments: `$ARGUMENTS`. Scope = a package, `package/slice`, or empty for every package in `.agents/profile.toml` `[scopes].order`. Without `--explain` the plan is written; with it, only a report in `.agents/reports/`.

0. Note the start time first: `date -u +%FT%TZ` (START). The ledger measures this run's tokens from it.
1. Read `.agents/core/layers.md`, `.agents/core/rules.md`, `.agents/profile.toml`, `.agents/budget.toml`. Run `python3 .agents/scripts/budget.py check`; stop on STOP.
2. Read `.agents/handoff/<scope>.md` and `.agents/practices/<scope>.md` if they exist.
3. Scan: `python3 .agents/scripts/scan.py <scope>`. It writes `.agents/scans/<scope>-<tree>.md` and prints the path; missing scanners are listed inside. Exit code 3 means nothing could be scanned: write the report, log `--outcome failed` and stop. Do not run scanners yourself, filter, rank or summarise the scan: the file is the advisors' whole input, identical for any run on the same source.
3b. Findings from outside the scan: `python3 .agents/scripts/findings.py list --scope <scope> --status open` (CI failures upstream/dev has too, filed by runs). Copy that output verbatim into the plan run's report; do not filter it.
4. Launch the advisors in parallel. Each prompt is only: the scope, the scan file path, and "read `.agents/core/rules.md` first". advisor-quality, -performance, -docs, -compat, plus advisor-uxui only when the scope is in `[scopes].ui`.
5. Launch decider-triage to keep findings worth a task, each fitting one PR. Its input is the advisors' opinions plus the open findings of step 3b (each with its key and evidence URLs); triage may merge a finding with a scan finding, or keep it apart, but must answer each one (kept, merged into T-..., or dropped with a reason).
6. For each kept finding launch decider-compat-risk and a second decisioner (decider-test-change for anything touching tests or CI, else a fresh decider-triage) in parallel. Apply the deliberation rule in `.agents/core/layers.md` (second round on disagreement, then `blocked`). Use decider-arbiter for tasks touching the same file.
7. Write `.agents/plans/<date>-<scope>.md` following `plans/_template.md`: low-risk tasks both decisioners approved are `approved`; tests, UI and public API stay `proposed`. A task born from a finding carries `- finding: <key>`; then `findings.py set-status --key <key> --status planned --task-id <task-id>`. A finding triage dropped: `findings.py set-status --key <key> --status closed --note "<reason>"`.
8. Record the run: `python3 .agents/scripts/ledger.py add --run-id <id> --command optimize-plan --scope <scope> --mode <explain|run> --session current --since <START> --outcome ok` (tokens are measured, never typed in).
9. Report in <= 20 lines: tasks by status, blocked items needing the human, scanners that were missing, the scan file and its sha256.

Per `.agents/budget.toml` `[pilot]`, treat every run as `--explain` while `mode = "explain"`.
