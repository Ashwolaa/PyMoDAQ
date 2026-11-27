verdict: approve
public_api: no
behaviour_change: no
fails_without_fix: yes

# PR review T-pymodaq_gui-001 r1 — Fix mutable default arguments
Branch: agent/pymodaq_gui/hygiene/2026-11-26-fix-mutable-default (diff vs dev_agent, 7 files, +75/-6)

## Checks
1. Task match / drift: all six sites in the plan's files list changed (utils.py:245, ioxml.py:377, browsing.py:442,
   viewer1Dbasic.py:102 and :172, viewer.py:296), each `=[]`/`=dict(...)` -> `=None` + build in body. No other lines
   touched, no reformatting, roi.py untouched. `merge_gate.py lint`: LINT OK, 81 changed lines, product files only, trailers present.
2. Correctness: functions read whole. h5tree_to_QTree recursion still passes the same list down (utils.py:303);
   browsing.py:494 (omits pixmap_items) now gets a fresh list per file. walk_xml_to_parameter recursion passes
   `subparams` explicitly; in-repo callers (ioxml.py:527/535/544/557) pass params=[] and are unaffected.
   update_labels keeps `labels[:]`/`==` semantics with `[]` built in body; set_axis_label default dict unchanged
   (callers axes_viewer.py:49/52, viewer1Dbasic.py:195 always pass a dict). viewer.py change is inside `__main__` demo.
3. Behaviour / API: names, positions, keywords unchanged; only the default object changes to None. Only side
   effect: an explicit `None` argument, previously an error (AttributeError / TypeError logged), is now treated as
   the default. Not a contract change for any documented input.
4. Tests: two new files, no existing test edited. Copied as *_review_tmp_test.py and run against dev_agent code
   (PYTEST_QT_API=pyqt6 and pyside6, offscreen): both tests FAIL on dev_agent (shared list, len 2 on second call).
   Against branch code (git archive + PYTHONPATH, import path verified): new tests + tests/parameter_test
   132 passed / 3 skipped; tests/utils + h5module_test + plotting_test 514 passed / 1 xpassed, under both bindings.
   Temp files removed, `git status` clean. Assertions are exact (len == 1, identity).
   Minor (not blocking): the walk_xml test asserts `len == 1` for a root with one child; fine, exact.
5. Docs/docstrings: no docstring claims changed; walk_xml_to_parameter example (ioxml.py:398) now correct in repeated use.

## Findings
none

summary: Replace mutable default arguments in six pymodaq_gui functions with None, fixing shared pixmap_items in h5tree_to_QTree and shared params in walk_xml_to_parameter, with regression tests that fail on the old code.
