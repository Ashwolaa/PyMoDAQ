# Rules (every agent reads this first)

## Universal
1. Never push to the default branch (`dev`) or to any branch that is not your own agent branch.
2. Never open a pull request against upstream. PRs target `dev_agent` on the fork and are opened only by `/optimize-merge`,
   after `pr-reviewer` approved the branch. Only `/optimize-merge` merges, with a merge commit, and only what
   `scripts/merge_gate.py` allows; everything else waits for the human.
3. Every agent branch is named `agent/<scope>/<specialty>/<YYYY-MM-DD>` (tools: `agent-tool/<name>`,
   research: `agent-rd/<topic>`), carries the `agent-made` label, an `Agent-Run: <run-id>` commit trailer,
   and a line in `registry.jsonl`.
4. One concern per PR, at most the size cap in `profile.toml` (tool tasks exempt: one tool per branch,
   no product-source changes in the same branch).
5. Do not state anything you did not verify in the code. Say "unverified" instead.
6. Return at most 30 lines to your caller. Put detail in files under `.agents/`.
7. Stop cleanly when the budget (`scripts/budget.py check`) or a rate limit says so: write the handoff first.
8. In `--explain` mode change nothing outside `.agents/reports/`.
9. Run shell tools after `profile.toml` `[tools].env` (scanners live outside the system PATH); call scripts with
   `python3`.
10. Log `--outcome failed` when the run produced nothing usable (no scan output, aborted setup), never `ok`.
11. End every command report with the absolute path of each file it wrote, so the human can open them.
12. State (`.agents/`: ledger, registry, plans, handoff, reports, scans) is committed only on `dev_agent`, never on an
    `agent/*` branch: a PR carries product files only. `ledger.py`, `registry.py`, `plan.py` and `findings.py` refuse other branches.
13. Task status in a plan changes only through `scripts/plan.py set-status`. An executed task becomes
    `done — branch <b>, CI <result>, awaiting review`; after /optimize-merge `done — PR #n merged (...)`,
    `done — PR #n open, awaiting the human: ...` or `blocked — <reason>`.
14. Every `gh` call names the fork: `-R <profile [project].fork>` (the clone's default repo may be upstream).
15. A CI failure that upstream/dev has too (`ci.py` exit 4, `KNOWN-UPSTREAM`) does not block a branch: it is filed with
    `findings.py` and becomes a task only through `/optimize-plan`. Any other failure blocks it.
16. Never skip a command step or do a sub-agent's job yourself to save quota: the caps in `budget.toml` do that.
    Product files are edited by specialists only, reworks included; `merge_gate.py lint` runs before every push.
17. Run every step in the foreground and wait for it. A Bash call lasts at most 10 minutes (`timeout` 600000), so call
    `ci.py` with `--timeout 540` and call it again on exit 2: it resumes the same runs, it never dispatches twice.
    A notification that arrives after your final report is not a new invocation: reply `already done (<run id>)`
    and change nothing.
18. A problem outside the task (seen by a specialist, the coordinator or pr-reviewer) is filed with
    `findings.py add --kind run|review`; a handoff note alone gets lost when the next run overwrites it.
19. `<scope>` in state paths (handoff, reports) is always the task's package, also when a command got a task id.
20. Every commit that changes only `.agents/` or `.claude/` ends its subject with `[skip ci]`: state commits must not
    start the fork's workflows (72 wasted docs builds on 2026-11-18/19). CI runs once per task, on its PR.

## Project hard rules
They are listed in `profile.toml` `[hard_rules]` and come from AGENTS.md. A violation is a veto, no exceptions
without the human.

## Before pushing
All commands in `profile.toml` `[checks]` pass on the touched scope. Never skip, quarantine or weaken a test
to get green.
