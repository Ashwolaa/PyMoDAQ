# Rules (every agent reads this first)

## Universal
1. Never push to the default branch (`dev`) or to any branch that is not your own agent branch.
2. Never open a pull request against upstream. PRs target `dev_agent` on the fork, as drafts.
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

## Project hard rules
They are listed in `profile.toml` `[hard_rules]` and come from AGENTS.md. A violation is a veto, no exceptions
without the human.

## Before pushing
All commands in `profile.toml` `[checks]` pass on the touched scope. Never skip, quarantine or weaken a test
to get green.
