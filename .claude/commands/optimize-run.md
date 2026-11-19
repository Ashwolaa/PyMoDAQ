---
description: Executive: carry out approved tasks of the plan on agent branches within the budget
argument-hint: "[scope | task-id] [--explain]"
---

You are the coordinator of the executive. Arguments: `$ARGUMENTS`. Scope = package or `package/slice`, a task id (`T-...`), or empty to take the next scope with approved tasks in dependency order.

0. Note the start time first: `date -u +%FT%TZ` (START). The ledger measures this run's tokens from it.
1. Read `.agents/core/layers.md`, `.agents/core/rules.md`, `.agents/profile.toml`. Run `python3 .agents/scripts/budget.py check` and `budget.py disable-check`; stop on STOP/DISABLE after writing the handoff.
2. If `.agents/budget.toml` `[pilot] mode = "explain"` or `--explain` is given: list what you would do, write `.agents/reports/<scope>/<date>-run.md`, change nothing else.
3. Make sure you are on `dev_agent` (see `scripts/sync_branches.sh`); never touch `dev`.
4. Adopt the cocoordinator role (`.claude/agents/cocoordinator.md`) for the scope. Each task goes through `scripts/task.py`, which does or verifies every step; never do a step by hand that it covers, and never work around a refusal (rules.md 16). Per task (`budget.py check` between tasks):
   a. `python3 .agents/scripts/task.py start --task-id <id> --plan <plan>`: on `dev_agent`; it refuses a task that is neither `approved` nor `blocked — review` (rework, at most two rounds), computes the run id (`-r<N>` for a rework), and creates the branch or rebases the existing one. It prints the run id: use it below.
   b. Launch the task's specialist (for tests one `test-agent` per test folder) with a folder-level scope and the task block; for a rework also the latest review report, told to fix exactly its findings and nothing else. The specialist commits **product files only** with the trailer `Agent-Run: <run-id>`. Never edit product files yourself.
   c. `task.py checks <run-id>` (flake8 blocking set, layering test, `merge_gate.py lint`), then `task.py checks <run-id> --backend <b>` for each `[checks].qt_backends` entry. Tests that fail are rerun on the base commit by the script: failing there too = pre-existing. Any new failure: have the specialist fix it, then run the checks again. Never skip or weaken a test.
   d. `git push origin <branch>` (`--force-with-lease` for a rebased rework). **Open no PR**: `/optimize-merge` opens it once `pr-reviewer` has validated the branch. Never open a PR upstream.
   e. `task.py ci <run-id>`: runs CI on the pushed head (a push alone triggers nothing on the fork). Exit 2 = still running: call it again. Exit 1 = a failure upstream/dev does not have: read the `gh run view ... --log-failed` it prints, say whether code or infrastructure caused it, fix code failures through the specialist, then c-e again. Known upstream failures (`ci.py` exit 4) count as green; `finish` files them as findings.
   f. `task.py finish <run-id> [--note "<one line>"]`: refuses unless a specialist was launched, you edited no product file, checks, lint and CI are recorded for the pushed head. Then it switches to `dev_agent` and writes the registry row, the plan status, the findings and the ledger line itself.
   g. Overwrite `.agents/handoff/<scope>.md` (<= 40 lines, template `handoff/_template.md`; `<scope>` = the package). Problems outside the task go to `findings.py add --kind run` (rules.md 18).
   h. `task.py close <run-id>`: refuses unless the handoff was rewritten; commits and pushes `dev_agent`.
   To give up on a task: `task.py block <run-id> --reason "<why>"`, then g and h.
5. Report in <= 20 lines, ending with the branch, the CI result (with run URLs) and the paths of the files written. Next step for the human: `/optimize-merge <task-id>`.

Handle a rate-limit error by writing the handoff, logging `--outcome limit --session current --since <START>` and stopping.
