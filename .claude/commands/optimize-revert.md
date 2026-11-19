---
description: Undo an agent run by reverting its merged PRs on dev_agent
argument-hint: "<run-id>"
---

Argument: `$ARGUMENTS` (a run id).

1. List the branches of that run: `python3 .agents/scripts/registry.py list` and filter on the run id. If none, stop.
2. Show the user the branches, PRs and their status, and **ask before reverting anything**.
3. For merged branches: on a new branch `agent/revert/<run-id>/<date>`, `git revert -m 1` their merge commits on `dev_agent` in reverse order; for open ones close the PR (`gh pr close -R <fork>`); for `pushed` ones there is no PR, just mark them closed. Run `[checks]` before pushing. Never touch `dev`.
4. Update `registry.py set-status --branch <b> --status reverted|closed`, add a ledger line, and note the reason in `.agents/handoff/<scope>.md`.
