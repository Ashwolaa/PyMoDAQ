verdict: approve
public_api: no
behaviour_change: yes
fails_without_fix: yes

# PR review T-pymodaq_gui-004 r1 (branch agent-tool/T-pymodaq_gui-004, head 250df0879, run 2026-11-28-merge-T-pymodaq_gui-004-r1)

No previous review report.

## Checks
1. Task match and drift: ok. The diff touches only `.agents/scripts/scan.py` (new `JSCPD_IGNORE` constant at :35-36,
   `--ignore JSCPD_IGNORE` added to the jscpd call at :128, the pattern named in both jscpd section headers at :131 and
   :137-138) and adds one test in `.agents/tests/test_scripts.py:220-238`. No product files, no edits to untouched lines.
   `merge_gate.py lint`: "LINT OK: 30 changed lines, tool code only, trailers present" (exit 0).
2. Correctness: checked by running it. `scope_path` (scan.py:62-68) hands jscpd an absolute path. jscpd 5.4.3 on
   `<repo>/packages/pymodaq_gui/src/pymodaq_gui`, as scan.py calls it: without the ignore 133 sources, 971 clones,
   24.22%, 917 clones in `material_icons/resources`; with the ignore 131 sources (icons_rounded_20.py, icons_rounded_40.py
   dropped), 54 clones, 1.72%, 0 in material_icons. The glob matches the generated files.
3. Behaviour and API: tool code only, no public product API. The scan output changes: the header text is new and the
   pymodaq_gui numbers drop. The plan expects this ("scan sha256 of all scopes changes"). No script reads the header text
   (grep across .agents/scripts, .agents/runner, .agents/tests, .claude); only the advisor agents read it.
4. Tests: the branch test copied as `test_scripts_review_tmp_test.py` and run against dev_agent code:
   `test_scan_jscpd_ignores_generated_icon_resources` fails (AttributeError: no `scan.JSCPD_IGNORE`), the other 36 pass.
   Temp file deleted, git status clean. The test checks the exact pattern, the `--ignore` argument right after the flag,
   and the header line. It mocks `run`, so the glob's real matching is covered only by the manual run in point 2.
5. Docs and docstrings: the comment at scan.py:35 says the files are compiled Qt resource modules. That matches the files
   (icons_rounded_*.py in a resources folder; the plan's verdict calls them rcc-generated). Whether the rcc header is
   present was not opened (unverified). The test docstring matches what it asserts.

## Findings
None.

summary: scan.py now passes `--ignore "**/resources/material_icons/resources/**"` to jscpd and names the pattern in the jscpd section header; verified on the real tree: pymodaq_gui duplication drops from 24.22% to 1.72% (917 generated-icon clones gone), with a test that fails without the change.
