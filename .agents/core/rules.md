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
16. Launch every sub-agent by its own type (`subagent_type: "<name>"` of `.claude/agents/`); a `general-purpose` agent given the same task does not count, the scripts check the type. If `merge.py decide` or `task.py finish` refuses for a missing launch, launch the right agent and retry; do not report it as a tooling fault.
    Never skip a command step or do a sub-agent's job yourself to save quota: the caps in `budget.toml` do that.
    Product files are edited by specialists only, reworks included; `merge_gate.py lint` runs before every push.
17. Run every step in the foreground and wait for it. A Bash call lasts at most 10 minutes (`timeout` 600000), so call
    `ci.py` with `--timeout 540` and call it again on exit 2: it resumes the same runs, it never dispatches twice.
    Sub-agents also run in the background: after launching them, call `Yield` and keep calling it until every one has
    reported. Never end your turn, and never write the final report, while a launched agent is still running: the
    headless runner (`step.py`) takes the first end of turn as the final result and kills the session (2026-11-22:
    `/optimize-plan pymodaq_data` died after launching its advisors, no plan written).
    A notification that arrives after your final report is not a new invocation: reply `already done (<run id>)`
    and change nothing.
18. A problem outside the task (seen by a specialist, the coordinator or pr-reviewer) is filed with
    `findings.py add --kind run|review`; a handoff note alone gets lost when the next run overwrites it.
19. `<scope>` in state paths (handoff, reports) is always the task's package, also when a command got a task id.
20. Every commit that changes only `.agents/` or `.claude/` ends its subject with `[skip ci]`: state commits must not
    start the fork's workflows (72 wasted docs builds on 2026-11-18/19). CI runs once per task, on its PR.

21. **Ask the owner only when the direction is genuinely open.** In R&D and for anything that adds a feature, before
    building or concluding, ask yourself: would two reasonable answers to an open question lead to different work?
    If yes, and the repository, `STATUS.md`, `handoff/` and earlier answers in `.agents/grill/` do not settle it,
    write `.agents/grill/<topic>.md` and register it with `python3 .agents/scripts/grill.py add`:
    `## Decision` (what you are stuck on and why it changes the work), then 3-7 numbered questions, most decisive
    first, each with a `Recommended:` line (your answer and its evidence). Then stop that line of work, deliver
    whatever part is clear, log the run `ok` with note `needs-direction`, and carry on with nothing else on that
    topic. Do not ask about details you can settle with a sensible default, nor to avoid a decision: state the
    default and go. At most `[grill].max_open` requests are open at once; `grill.py add` refuses beyond that (exit 3):
    then make the safest choice and say so in the report. Answered requests (`## Direction`) are constraints.

## Project hard rules
They are listed in `profile.toml` `[hard_rules]` and come from AGENTS.md. A violation is a veto, no exceptions
without the human.

## Before pushing
All commands in `profile.toml` `[checks]` pass on the touched scope. Never skip, quarantine or weaken a test
to get green.
