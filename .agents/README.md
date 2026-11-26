# PyMoDAQ optimisation consortium — start here

Agents that plan, make and merge small improvements to PyMoDAQ on the fork `Ashwolaa/PyMoDAQ`, branch `dev_agent`,
measured and capped, never touching upstream. Nothing here is part of the PyMoDAQ distribution. This page is how to
work with them; the rest:

| file | what it is | kept up to date by |
|---|---|---|
| `.agents/STATUS.md` | the current state: what needs you, what is in flight, open findings, recent runs | `status.py --write` (every run and cycle step) |
| `.agents/COMMANDS.md` | every command, agent, script and hook, with its role | `docs.py --write` (generated; a test fails if stale) |
| `.agents/BRIEFING.md` | design decisions and history | by hand |
| `.agents/core/` | rules, layers, formats: the generic part, reusable on another repository | by hand |
| `.agents/profile.toml`, `budget.toml` | the only repository-specific settings (scopes, checks, hard rules; daily caps) | by hand |
| `.agents/research/_prompts.md` | R&D prompts ready to run (R1-R5) | by hand |

## Starting a new session

1. Open the session **in the agents' worktree**, not in your own clone: `cd ../PyMoDAQ-dev-agent && claude`.
   Commands (`/optimize-*`), agents and the upstream guard hook are loaded from the folder the session starts in.
2. First message, to pick up where things are:
   > Read .agents/README.md and .agents/STATUS.md, run `python3 .agents/scripts/status.py --write` and
   > `pytest .agents/tests -q` (after the `[tools].env` of `.agents/profile.toml`), then tell me what needs me.
3. One command per session, then `/clear` (each command starts cold by design). Or let the wheel do it (below).

## The daily loop

1. **Read `STATUS.md`, "Needs you"**: proposed tasks, PRs waiting for you, blocked tasks.
2. **Decide proposed tasks** (until an `/optimize-approve` command exists):
   `python3 .agents/scripts/plan.py set-status <plan> <task-id> "approved — owner, <date>"` (or `"expired — dropped by
   the owner: <why>"`), then `git commit -am "Owner approves <task-id> [skip ci]" && git push origin dev_agent`.
3. **Review and merge the PRs left for you** on GitHub, **with a merge commit** (never squash: `/optimize-revert`
   needs merge commits). The next merge step notices on its own.
4. **Turn the wheel**: `.agents/runner/cycle.sh --dry-run`, then `MAX_STEPS=3 .agents/runner/cycle.sh`.
   It syncs with upstream, then picks the next step itself: merge pending branches > run the next approved task >
   plan the next package > weekly committee review. It stops on any guard; logs go to
   `<main clone>/.git/agent-runs/cycles/<stamp>/`.
5. **Or run one command by hand** (after `/clear`): `/optimize-status`, `/optimize-plan <package>`,
   `/optimize-run <task-id>`, `/optimize-merge [task-id]`, `/optimize-research "<R prompt>"`, `/optimize-review`,
   `/optimize-plugins discover|assess|port`, `/optimize-revert <run-id>`. All take `--explain` (dry run).
   Roles: `COMMANDS.md`.

## How a change travels

`/optimize-plan` (scan, 5 advisors, triage, 2 decisioners, a plan with `approved`/`proposed` tasks) ->
`/optimize-run` (a specialist on a branch, local checks on PyQt6 and PySide6, pushed; no PR, no CI) ->
`/optimize-merge` (pr-reviewer on Opus; approve -> PR -> its CI, the only CI run -> merge gate: low risk, two
approving decisioners, no tests/UI/public API -> automatic merge; otherwise the PR waits for you; "changes" ->
`/optimize-run` reworks it: two free rounds, then only while each review has fewer findings than the one before, at most four). Problems found on the way become findings for the next plan.
Upstream: nothing goes there without you (R&D prompt R4 `upstream-strategy` prepares how).

## Guards (what keeps it safe and cheap)

- `.claude/settings.json` hook: blocks any push or `gh` command on upstream, pushes to `dev`, and direct
  `gh pr create/merge` by an agent (the scripts do those after their checks).
- `task.py` / `merge.py`: every step is done or verified by a script (specialist launched, no coordinator edits,
  checks recorded, review really run); prose rules alone were skipped under cost pressure.
- Quota: daily caps in `budget.toml`, a safety switch after two budget stops in a day, and `runner/cost.py`, which
  starts a cycle step only if its measured cost keeps the session window under 85% and the week under 90%.
- CI: state commits carry `[skip ci]`; each task gets one CI run, on its PR.

## Where things live

`plans/` tasks and statuses (`plans/experiments/`: raw results of the model experiments, never read by commands) ·
`registry.jsonl` branches and PRs · `ledger.jsonl` every run with measured tokens · `findings.jsonl` problems for the
next plan · `reports/<package>/` reviews · `handoff/<package>.md` notes for the next run · `scans/` scanner output ·
`practices/` what worked per folder · `<main clone>/.git/agent-runs/` run records and cycle logs (never committed).
The Python 3.14 environment is `~/.venvs/pymodaq-314` (PyQt6 and PySide6, PyMoDAQ editable from this worktree):
one worktree, so one branch at a time. Agents' tests currently write to your `~/.pymodaq` (R5 explores isolation).

## Changing the tooling

On an `agent-tool/<name>` branch in its own worktree; `pytest .agents/tests` before merging into `dev_agent`
(`--no-ff`, `[skip ci]`); shared logic goes in `scripts/agentlib/`; `docs.py --write` refreshes COMMANDS.md.
