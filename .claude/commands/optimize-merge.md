---
description: Validate pushed agent branches (pr-reviewer), open their PRs, merge the low-risk ones into dev_agent
argument-hint: "[scope | task-id] [--explain]"
---

You are the merge coordinator. Arguments: `$ARGUMENTS`. Scope = package, a task id (`T-...`), or empty for every candidate.
A PR is opened only for a branch that pr-reviewer validated. Merges go into `dev_agent` only, never `dev`, never upstream.
Every step goes through `scripts/merge.py`, which does or verifies it; your own job is to launch `pr-reviewer` and to
report. Never do a step by hand that the script covers, never work around a refusal (rules.md 16), run everything in
the foreground (rules.md 17).

1. Read `.agents/core/rules.md`, `.agents/core/layers.md`, `.agents/profile.toml`. `budget.py disable-check`; stop on DISABLE.
   `git switch dev_agent`, `git pull --ff-only origin dev_agent`; the worktree must be clean.
2. `python3 .agents/scripts/merge.py sync` (PRs the human merged or closed). Then `merge.py candidates <argument>`.
   With `--explain` or `[pilot] mode = "explain"`: list the candidates, write `.agents/reports/<scope>/<date>-merge.md`, stop.
3. For each candidate, oldest first:
   a. `merge.py start --branch <branch>`: budget check, rebase on `dev_agent` (a conflict blocks the task: go to f),
      push if the head changed. It prints the run id and the review report path.
   b. Only if start says the head changed: `git switch <branch>`, `task.py checks <run-id>` and
      `task.py checks <run-id> --backend <b>` for each `[checks].qt_backends`, `git switch dev_agent`. A new failure:
      stop this candidate (the task needs `/optimize-run` again) and go to f.
   c. No CI before the review: the PR's checks are the one CI run (step e, `merge.py gate`), rules.md 20.
   d. Launch the agent of type `pr-reviewer` (`subagent_type: "pr-reviewer"`, Opus; never `general-purpose` briefed to review: `merge.py decide` checks the agent type and refuses otherwise) with the task id, its plan, the branch and the report path from start (and the previous
      report when start names one). Wait for it.
   e. `merge.py decide <run-id>`: refuses unless the review really happened for this head; acts on the verdict
      (changes / reject: task blocked or closed; approve: PR opened or the old draft marked ready, with a generated body).
      If it opened or readied a PR: `merge.py gate <run-id>` (exit 2: call again): PR checks, then `merge_gate.py`:
      auto-merge with a merge commit, or the PR stays open for the human with the reasons in the plan.
   f. `merge.py close <run-id>`: ledger line, STATUS.md, commit and push `dev_agent`. Next candidate.
4. Overwrite `.agents/handoff/<scope>.md` (<= 40 lines, `<scope>` = the package; Done = merged PRs, Blocked = review/
   conflict/CI blocks, Next step = the first PR waiting for the human), commit it on `dev_agent` with `[skip ci]` in the subject and push.
5. Report in <= 20 lines: one line per candidate (task, PR, verdict, merged / awaiting human with the reasons / blocked
   with the reason), then the paths of the files written.

Never stop the loop to ask the human: a blocked candidate is recorded and the loop goes on; questions go in the report.
A budget STOP from `merge.py start` ends the loop: write the handoff (step 4) and report.
Handle a rate-limit error by closing the current run if it has an outcome, writing the handoff and stopping.
