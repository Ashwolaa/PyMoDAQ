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
