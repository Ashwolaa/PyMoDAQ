# R&D prompts, ready to run (prepared 2026-11-19, not run yet)

Each block is the argument of `/optimize-research`: a one-line question, a stopping condition, then method, output and
limits. Run one at a time, from the `dev_agent` worktree, after `/clear`. Results go to `.agents/research/<topic>.md`
(<= 80 lines); anything worth doing becomes a finding or a task for `/optimize-plan`, never a merge.
Topic 1 of the first list (plugin API index) moved into `/optimize-plugins discover` + `assess`.

## R1 — pyside6-gc-crash
```
/optimize-research pyside6-gc-crash: Does collecting garbage in the main thread only (commit e2610fc56 on the owner's
local branch fix/tests-gc-main-thread) remove the PySide6 crashes of the pymodaq test suite ("QObject::killTimer:
Timers cannot be stopped from another thread", then Fatal Python error: Segmentation fault/Aborted)?
Stop when: the crash rate with and without the fix is measured on the same commit, or after 2 hours.
Method: prototype branch agent-rd/pyside6-gc-crash from dev_agent + cherry-pick e2610fc56 (register it).
First locally: `PYTEST_QT_API=pyside6 QT_QPA_PLATFORM=offscreen pytest packages/pymodaq/tests -x -q -p no:cacheprovider`,
10 runs without the fix (dev_agent) and 10 with it; count crashes and the test they happen in. Only if nothing crashes
locally: CI via `ci.py run --branch agent-rd/pyside6-gc-crash`, at most 4 dispatches per side (each dispatch runs the
full 16-job matrix). Baseline evidence: finding `tests-pymodaq.yml|tests (ubuntu-latest, pyside6)|crash` (9 of 11
recent upstream failures of that job are crashes).
Output: crash table (runs, crashes, where), the verdict (fixes / reduces / no effect / not reproducible), and, if it
fixes, a proposed task for /optimize-plan pymodaq referencing the finding key. Never touch the owner's branch.
```

## R2 — reviewer-on-sonnet
```
/optimize-research reviewer-on-sonnet: Does pr-reviewer on Sonnet reach the same verdicts and findings as on Opus for
the ten first-round reviews of 2026-11-19?
Stop when: all ten are replayed once on Sonnet and compared, or after 90 minutes.
Method: the ten r1 reports are `.agents/reports/pymodaq_utils/2026-11-19-pr-review-T-pymodaq_utils-*.md` without `-r2`
(T-001, M01-M05, M07-M10). For each, find the branch head that review saw (merged PRs: the merge commit's second
parent; reworked docs PRs: the PR's first-round head from `gh pr view <n> -R Ashwolaa/PyMoDAQ --json commits` or the
reflog), make a local branch agent-rd/replay-<task> at it, and launch pr-reviewer with model sonnet, writing to
`.agents/research/reviewer-on-sonnet/<task>.md` (never to reports/: merge_gate reads those). Compare per task: the
four header lines, findings matched by path:line and meaning, findings only one model found; and the tokens of each
replay (ledger `out_by_agent`). Delete the replay branches at the end.
Output: agreement table, the misses that matter (a wrong approve is worse than an extra finding), cost per review on
each model, and a recommendation (switch, keep Opus, or Sonnet for docs-only reviews).
```

## R3 — mutation-testing
```
/optimize-research mutation-testing: Which pymodaq_utils modules have the most surviving mutants, i.e. code the tests
execute but do not check?
Stop when: mutmut has run on utils.py, config.py and serialize/ (or 60 minutes of mutation time, whichever first).
Method: install mutmut into the [tools].env venv if missing (record the version); run it per module against
packages/pymodaq_utils/tests under PYTEST_QT_API=pyqt6 QT_QPA_PLATFORM=offscreen; exclude
tests/config_test.py::test_nested_update_from_user (known local failure, finding ...|local failure).
Output: per module killed/survived/timeout counts and the 10 most telling survivors (path:line, the mutation, why no
test sees it). File each cluster of survivors as `findings.py add --kind run --scope pymodaq_utils` so
/optimize-plan can turn them into spec-test-quality tasks. Change no product or test file.
```

## R4 — upstream-strategy
```
/optimize-research upstream-strategy: How should work merged into dev_agent reach PyMoDAQ/PyMoDAQ, in an order and a
grouping set by its relevance (bug fix, feature, docs, hygiene, tests, refactor, tooling), so that maintainers can
review it easily and the most useful changes land first?
Stop when: a written strategy plus a ranked, grouped list of the work merged so far is ready, or after 90 minutes.
Method (read-only on upstream: no PR, issue, comment or push there; the guard hook blocks it anyway):
1. How upstream merges today: `python3 .agents/scripts/pr_stats.py` (size vs time-to-merge), plus the last ~100 merged
   upstream PRs read with `gh` against the fork's mirror data or the PR pages: classify each by kind from its title,
   labels and files; per kind, median size, time to merge, who merged, review rounds, how often it was split or
   squashed. Which base branches are used (`dev`, the `5.3.x` stable line) and when a fix also goes to the stable
   line (backport PRs such as `backport/...`).
2. The project's own rules: AGENTS.md, the contribution guide in docs/, PR templates, changelog practice
   (docs/src/changelogs/), the legacy_to_current / deprecation rules for public API.
3. A relevance score per task, from data already in .agents/ (plan risk, kind, files, review summary, findings
   it closes): user impact (a bug a user can hit > docs > hygiene), risk, size, dependencies between tasks, and
   whether the fix also applies to the stable line.
4. Apply it to every task merged into dev_agent so far (registry `merged`): one line each with kind, score, target
   branch(es), proposed upstream PR group and order.
Output: `.agents/research/upstream-strategy.md` (<= 80 lines): the strategy per kind (one PR per bug fix, grouping
rules for docs and hygiene, backport rule, what waits for an issue first, size limit from the data), the ranked list,
and the design of an `/optimize-upstream` command that rebuilds a group on upstream/dev and shows the owner the
branch, the checks and the PR text before anything is opened (owner's standing rule). Propose the command and any
plan-format change (e.g. a `relevance:` field) as tasks for /optimize-plan; build nothing.
```

## R5 — config-schema
```
/optimize-research config-schema: How can a PyMoDAQ configuration survive schema changes (keys added, renamed or
removed, a changed type such as scalar -> list, a changed default) and switching between branches, without deleting
the file, and how can developers, tests and agents use an isolated config folder?
Stop when: the research note and a prototype that passes the branch-switch test below exist, or after 2 hours.
Facts to start from (verified 2026-11-20, pymodaq_utils/config.py): the system folder (/etc, /Library/Application
Support, %PROGRAMDATA%) falls back to ~/.pymodaq when it cannot be created (:109-120), so system and user files are
then one file; the folder comes from Path.home() and is cached (:125), with no override; load() copies the whole
template into the system file on first start (:427-428), so defaults are frozen; check_config only adds missing keys
(:203-225), never removes, retypes or updates; the user file is deep-merged over the system one (:289). The plural/
singular fallbacks in Config.__call__ (task T-pymodaq_utils-006) are hand-written compatibility for one such change.
Method:
1. List every config: the templates in all packages (`grep -rn config_template_path packages/`) and the plugins'
   BaseConfig subclasses (public API: plugins register their own). From `git log -p` of the templates, collect the
   real schema changes of the last years (renames, type changes, removals) as test cases.
2. Compare approaches, each with what breaks for users and for plugins: (a) store only the user's overrides (a sparse
   file) instead of a full template copy, so new defaults reach everyone; (b) a schema version in the template plus
   ordered migration functions; (c) on load, check each value's type against the template: back up the file, reset
   only the mismatching keys to the template, warn once; (d) an environment variable (e.g. PYMODAQ_CONFIG_DIR) or a
   per-environment folder, for developers switching branches, for tests (a pytest fixture) and for agents.
3. Prototype the most promising combination on agent-rd/config-schema (registered), with tests: a branch-switch
   test (a file written by the old template, loaded with a template that changed a type and renamed a key, loads
   without error, keeps the user's other values, leaves a backup); a test that a new default reaches a user who
   never changed it; an isolation test (two config dirs do not see each other).
Output: `.agents/research/config-schema.md` (<= 80 lines): current behaviour with file:line, the real schema changes
found, the comparison, the recommended design and its plugin-compatibility impact (hard rule 1), and proposed tasks
for /optimize-plan (expected `proposed`: public API). Also say whether running the agents' tests with HOME set to a
scratch folder isolates them from the owner's ~/.pymodaq, verified by a run. Never touch ~/.pymodaq itself: work in
temporary folders.
```
