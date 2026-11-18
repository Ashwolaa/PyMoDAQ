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
  (executive), `/optimize-status`, `/optimize-revert <run-id>`, `/optimize-research <topic>`, `/optimize-review`
  (committee). All take `--explain` (dry run). Later: `/optimize-init` (drafts a project profile, marking each
  field detected vs assumed, human confirms before anything is written).
- Branches on the fork: `dev` mirrors `upstream/dev` (fast-forward only, never agent commits); `dev_agent` is the
  integration branch, `dev` merged into it daily; work branches `agent/<scope>/<specialty>/<date>`, tool branches
  `agent-tool/<name>`, research `agent-rd/<topic>`. Every agent branch: label `agent-made`, commit trailer
  `Agent-Run: <run-id>`, line in `.agents/registry.jsonl`. PRs are drafts against `dev_agent`. NEVER open a PR or
  push upstream automatically.
- Merging into `dev_agent`: low-risk tasks that two decisioners both approved may auto-merge; anything touching
  tests, UI or public API waits for the human.
- Execution is flat (main session = coordinator, adopts a co-coordinator role per scope, launches specialists);
  nested sub-agents are not assumed to work (unverified).
- Layers: advisory board (5 advisors: quality, uxui, performance, docs, compat -> decider-triage; decisioners
  compat-risk (veto), test-change (veto), arbiter (binding)); executive (cocoordinator, specialists hygiene,
  test-quality, refactor, uiux, docs; one test-agent instance per test folder, 12 today); audit (scripts + auditor);
  R&D (rd-researcher, best-practice); committee (efficiency, outcomes, governance; reads only ledger, registry,
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

## State
Step 1 (skeleton) is built: 6 commands, 22 agents, `.agents/` core docs, `profile.toml`, `budget.toml`, scripts
`ledger.py`, `registry.py`, `budget.py`, `sync_branches.sh`, plan/handoff templates. The three Python scripts were
tested; commands and agents have never been run. `sync_branches.sh` only had a syntax check.
Nothing has been pushed: the original session could not push (403, no GitHub App access on `PyMoDAQ/PyMoDAQ`, and
the fork could not be attached because a repo with the same name was already checked out).

## Next (in order)
1. Make sure this work is on `Ashwolaa/PyMoDAQ` (apply the patch, or re-create from this briefing), on a branch
   based on `dev`, then create `dev_agent` and the `agent-made` label.
2. Pilot: `/optimize-plan pymodaq_utils --explain`; install missing scanners first (`vulture`, `jscpd`, `radon`,
   `mutmut`, `import-linter`; ruff/coverage may exist). Record tokens in the ledger only if known.
3. Review the pilot with the owner, set caps in `budget.toml` (real reset time), then one real hygiene run, then
   scheduling.
4. Add API/compat, perf/threading, backport specialists; tool-building track; R&D; committee runs.
5. Extract the plugin and build `/optimize-init`.

## Open (ask the owner)
- Real reset time and desired daily caps (`budget.toml`; the daily `runs = 1` cap prevents a plan and a run on the
  same day).
- Confirm the assumed fields in `profile.toml` (fork name, `dev_agent`, 300-line cap).
- Whether sub-agents can spawn sub-agents here (unverified; flat execution is the baseline).
