# Start here (new session)
Read `.agents/README.md` first: how to start a session, the daily loop, the guards. Current state:
`.agents/STATUS.md`. Every command and agent: `.agents/COMMANDS.md`. This file keeps the design decisions and history.

# Briefing for the next agent (written at the end of the design session)

You are continuing a design that was agreed with the repository owner (GitHub: Ashwolaa, fork `Ashwolaa/PyMoDAQ`,
upstream `PyMoDAQ/PyMoDAQ`). The owner confirmed the design below before step 1 was built. Do not re-open settled
decisions; ask only about what is listed under "Open".

## Goal
A set of commands + agents that optimise the fork across the whole monorepo (`packages/pymodaq_utils`,
`pymodaq_data`, `pymodaq_scripting`, `pymodaq_gui`, `pymodaq`): code investigation (formatting, dead code, useless
tests, factorization), UI/UX, docs, plus R&D and an independent review committee. Later it is to become a reusable
plugin for any GitHub repository.

## Settled decisions
- Project commands in `.claude/commands/`, agents in `.claude/agents/`, state in `.agents/`. Core (generic) and
  profile (repo-specific: `profile.toml`, `budget.toml`) are kept in separate files.
- Commands: `/optimize-plan [scope]` (advisory board, never edits code), `/optimize-run [scope|task-id]`
  (executive, pushes branches, no PR), `/optimize-grill [topic]`, `/optimize-plugins discover|assess|port`, `/optimize-merge [scope|task-id]` (pr-reviewer validates, then PR + merge gate),
  `/optimize-status`, `/optimize-revert <run-id>`, `/optimize-research <topic>`, `/optimize-review`
  (committee). All take `--explain` (dry run). Later: `/optimize-init` (drafts a project profile, marking each
  field detected vs assumed, human confirms before anything is written).
- Branches on the fork: `dev` mirrors `upstream/dev` (fast-forward only, never agent commits); `dev_agent` is the
  integration branch, `dev` merged into it daily; work branches `agent/<scope>/<specialty>/<date>`, tool branches
  `agent-tool/<name>`, research `agent-rd/<topic>`. Every agent branch: label `agent-made`, commit trailer
  `Agent-Run: <run-id>`, line in `.agents/registry.jsonl`. PRs target `dev_agent` and are opened only after pr-reviewer approved the branch. NEVER open a PR or
  push upstream automatically.
- Merging into `dev_agent`: low-risk tasks that two decisioners both approved may auto-merge; anything touching
  tests, UI or public API waits for the human (2026-11-19: /optimize-merge + scripts/merge_gate.py; merge commits only,
  so /optimize-revert can `git revert -m 1`; fork CI without a PR via scripts/ci.py, as push triggers miss `agent/...`).
- Execution is flat (main session = coordinator, adopts a co-coordinator role per scope, launches specialists);
  nested sub-agents are not assumed to work (unverified).
- Layers: advisory board (5 advisors: quality, uxui, performance, docs, compat -> decider-triage; decisioners
  compat-risk (veto), test-change (veto), arbiter (binding)); executive (cocoordinator, specialists hygiene,
  test-quality, refactor, uiux, docs; one test-agent instance per test folder, 12 today); audit (scripts: merge_gate.py lint/check, ci.py; the auditor agent was removed 2026-11-19, pr-reviewer checks drift);
  R&D (rd-researcher, best-practice); plugin track (plugin-scout, spec-plugin-port); committee (efficiency, outcomes, governance; reads only ledger, registry,
  handoffs, reports; may recommend and pause a role, never edits agent definitions).
- Deliberation: two decisioners must both approve each finding, any single veto stops it; on disagreement each
  reads the other's reasoning and decides again; still split -> `blocked` for the human.
- Hard rules (from AGENTS.md, in `profile.toml [hard_rules]`): no public-name removal without shim, no test deletion
  without justification + coverage diff, no direct edits to generated files, push only to own agent branch, no
  reformatting of untouched files; plus tests and `packages/pymodaq/tests/layering_test.py` must pass before push.
- PR size: one concern, about 300 changed lines; tool-building tasks exempt (one tool per branch, no product source
  in the same branch). Agents may improve their own tools.
- Memory: `.agents/handoff/<package>.md` capped at 40 lines (Done, Open findings, Blocked, Next step, Evidence);
  plans in `.agents/plans/`, task statuses proposed/approved/done/blocked/expired (14 days; re-check against the
  current head before executing); reports and per-folder best-practice notes stay inside each project.
- Budget: nobody knows the cost yet. Pilot first, then set caps from the ledger. A session cannot read the plan
  quota or reset time; the human sets them in `budget.toml`. Runs stop cleanly on a limit error (handoff first), caps
  drop to 70% after a limit hit, schedule disables itself after 3 failures or a day over budget.
- Model tiers: haiku scanning, sonnet specialists/advisors, strongest model for decisioners/committee.
- Cloud for scheduled runs (daily); planning on demand during the pilot. R&D gets about 20% of the budget.
- Rotation (planning): dependency order utils, data, scripting, gui (6 slices), pymodaq (4 slices).

## State (refreshed 2026-11-25; live numbers are in `STATUS.md`, never copy them here)
- Built and running: step 1 (fork `dev` reset to `upstream/dev`, `dev_agent` pushed, label `agent-made`, README-bot
  workflow disabled) and the whole cycle: `/optimize-plan`, `-run`, `-merge`, `-status`, `-revert`, `-research`,
  `-review`, plus `/optimize-grill` (owner questions an agent could not settle, `scripts/grill.py`, at most
  `[grill].max_open` open) and `/optimize-plugins` (discover, assess, port; `plugin-scout`, `spec-plugin-port`).
  `runner/cycle.sh` turns the wheel unattended: `status.py next` picks the step, `runner/cost.py` checks it fits the
  plan quota, `runner/step.py` runs it headless. Start a session from `README.md`.
- Ledger (2026-11-25): 84 lines (39 run, 30 merge, 14 plan, 1 research); 25 branches in the registry; PRs #3-#26 on
  the fork are merged into `dev_agent` (#10 closed, replaced by #11); none is open. Scopes planned so far:
  `pymodaq_utils`, `pymodaq_data`; next is `pymodaq_scripting`. Plan files keep the text "PR open, awaiting the
  human" after the owner merges, so trust the registry or `gh pr list`, not the plan text.
- Never run yet: `/optimize-review` (committee) has no ledger line, nor has any `/optimize-plugins` step; `/optimize-init`
  and the plugin extraction (step 5) are not started.
- Caps: daily `[daily]` caps in `budget.toml` were set by the owner on 2026-11-19 from the pilot ("about one day of the
  wheel"); calibration data via `usage.py calibrate`. Weekly limit resets Sunday 00:00 Europe/Paris.
- Known blockers (details in `STATUS.md` "Open findings"): the `packages/pymodaq` suite hangs on
  `extension_loading_test::test_load[Scanner]` (task `M06`) and has flaky Qt tests (`state_manager_test`, random
  PySide6 abort); the agents have no notion of known-flaky tests; a merge run that ends blocked before the gate
  cannot be closed in the ledger.

## Next (in order)
1. Owner: answer the pending grill (`/optimize-grill config-reconcile`); merge future PRs with a merge commit,
   never squash.
2. Fix the agent tooling findings that stall the wheel (hung-test timeout, known-flaky tests, closing a blocked merge
   run, tool-task branch names vs `merge_gate` lint); then keep turning the wheel through the rotation.
3. First `/optimize-review` (committee) once enough runs exist; adjust caps from it.
4. Backport specialist, tool-building track, more R&D (`research/_prompts.md`).
5. Extract the plugin and build `/optimize-init`.

## Open (ask the owner)
- PR size cap: `pr_max_changed_lines = 300` is still an assumption. Upstream median 89 / p75 262 lines; the owner's own
  PRs merge in ~1 day below 150 lines and 3-12 days above. `pr_stats.py --label agent-made` matched no merged PR on
  2026-11-25: re-measure once the first agent PRs are merged.
- Whether sub-agents can spawn sub-agents here (unverified; flat execution is the baseline).
