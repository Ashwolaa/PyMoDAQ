verdict: approve
public_api: no
behaviour_change: no
fails_without_fix: n/a

# PR review T-pymodaq_utils-M12 r1 (branch agent/pymodaq/test-quality/2026-11-22)

Run id: 2026-11-24-merge-T-pymodaq_utils-M12-r1. No previous report.

## 1. Task match and drift
- Diff: one new file, packages/pymodaq/tests/utils/entrypoint_groups_sync_test.py (+10 lines). No other file touched.
- Task asks for a new test in packages/pymodaq/tests/ comparing checks.py:46-48 (ENTRYPOINT_GROUPS + OPTIONAL_ENTRYPOINT_GROUPS)
  with daq_utils.py:35-36 (PLUGIN_ENTRYPOINT_GROUPS): this is what the test does. Placed in the tests/utils subfolder, which is inside the asked folder.
- Test-only, no behaviour change: in scope for test-quality.
- `merge_gate.py lint --branch agent/pymodaq/test-quality/2026-11-22 --task-id T-pymodaq_utils-M12`: LINT OK (10 changed lines, product files only, trailers present).

## 2. Correctness
- packages/pymodaq/tests/utils/entrypoint_groups_sync_test.py:8 concatenates the two checks.py tuples (both tuples, verified at checks.py:46-48), so `+` is valid.
- :9 asserts no group appears in both checks.py lists; :10 asserts set equality with daq_utils.PLUGIN_ENTRYPOINT_GROUPS (verified at daq_utils.py:35-36).
  Adding, removing or renaming a group on one side only makes :10 fail. Ordering is not compared, which is right: the two lists use different orders on purpose (mandatory vs optional split).
- Duplicates inside PLUGIN_ENTRYPOINT_GROUPS itself are not detected (set comparison); harmless for get_plugin_packages, which deduplicates packages. Not a finding.
- Layering: a pymodaq test importing pymodaq_utils is allowed by the dependency order.

## 3. Behaviour and API
- No product code changed; no public name, default, return value or exception changes.

## 4. Tests
- Not a bug fix: fails_without_fix n/a. Ran the branch file as entrypoint_groups_sync_review_tmp_test.py against dev_agent code under [tools].env, QT_QPA_PLATFORM=offscreen: 1 passed (expected, the lists agree today). Temp file deleted, git status clean.
- Assertions are exact (set equality, length equality), not "no exception".
- Caller reports lint, layering, pyqt6 and pyside6 green on the head (pyside6 rerun after a known-flaky segfault): unverified by me.

## 5. Docs and docstrings
- Module docstring (line 1): "listed twice (plugin checker and daq_utils)" matches the code. The hatch_build_plugins/setup_plugin templates name the groups too, but as per-type conditionals, not as a list; the claim stands.

## Findings
None.

Note for the coordinator: the plan status of T-pymodaq_utils-M12 still reads "blocked — CI red ..."; update it through plan.py set-status after merge.

summary: Adds a test that fails when the plugin entry point group lists in pymodaq_utils.plugin_tools.checks and pymodaq.utils.daq_utils drift apart; test only, no behaviour change.
