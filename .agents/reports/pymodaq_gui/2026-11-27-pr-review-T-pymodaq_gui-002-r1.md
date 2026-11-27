verdict: approve
public_api: no
behaviour_change: yes
fails_without_fix: yes

# PR review T-pymodaq_gui-002 r1 (run 2026-11-27-merge-T-pymodaq_gui-002-r1)
Branch agent/pymodaq_gui/hygiene/2026-11-27, one commit 3c75ebf0e, diffed against dev_agent.

## Checks
1. Task match and drift: the diff deletes the local `from PyQt6.QtWidgets import QListView` (pattern_completer.py:188 on dev_agent) and adds one parametrized test, which is what the task block asks. No other lines touched. `merge_gate.py lint`: LINT OK, 13 changed lines, product files only, trailers present. The behaviour change is the bug fix the task asks for, not drift.
2. Correctness: on the branch, `QListView` resolves to the qtpy import at pattern_completer.py:8, so `isinstance(popup, QListView)` holds whichever binding is active. The only caller of `PatternCompleter.update_completer_config` is the test (Grep across packages/). `PatternDelegate.update_completer_config` (:582) does not take this code path. The file has no other direct PyQt6/PySide6 import.
3. Behaviour/API: no public name, signature or default changes. Under PySide6, `update_completer_config(word_wrap=...)` used to raise ImportError (seen in the run below). It now applies the setting. Under PyQt6, nothing changes.
4. Tests: pattern_completer_test.py:148-157 checks `popup.wordWrap() is` the exact value, for True and False, after add_completer and again after update_completer_config. Ran the branch test file against dev_agent code (temporary copy, since deleted; git status clean): under PyQt6 2 passed, under PySide6 2 failed with ImportError at pattern_completer.py:188. So it fails without the fix. On the branch head, both bindings pass, per the caller's local run (I did not re-run it).
5. Docs/docstrings: none changed. The commit message claim ("raised ImportError or made the isinstance check fail") matches the PySide6 ImportError I saw.

## Findings
none

summary: Use the qtpy QListView in PatternCompleter.update_completer_config so word_wrap works under PySide6 (it raised ImportError before), with a test for True/False that fails without the fix.
