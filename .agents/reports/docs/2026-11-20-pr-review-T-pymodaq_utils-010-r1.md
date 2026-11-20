verdict: approve
public_api: no
behaviour_change: no
fails_without_fix: n/a

# PR review T-pymodaq_utils-010 r1 (branch agent/docs/docs/2026-11-20, run 2026-11-20-merge-T-pymodaq_utils-010-r1)

## 1. Task match and drift
- Diff: 3 added rows in docs/src/developer_folder/instrument_plugins.rst (PMQ100, PMQ200, PMQ300), nothing else.
  No range row split or repeated, legacy_to_current.rst untouched, no reformatting of other lines.
- `merge_gate.py lint`: `LINT OK: 3 changed lines, product files only, trailers present` (exit 0).
- Commit c0f11a0a carries `Agent-Run: 2026-11-20-run-T-pymodaq_utils-010`.

## 2. Correctness (claims checked against packages/pymodaq_utils/src/pymodaq_utils/plugin_tools/rules.py)
- instrument_plugins.rst:147 PMQ100: rules.py:312 (`pyproject.toml cannot be parsed`) and rules.py:811
  (`package {package} not found`, hint `install the plugin`). Matches.
- instrument_plugins.rst:155 PMQ200: rules.py:418 in check_leftovers, raised on SyntaxError of a .py file; the
  "other checks are skipped" wording is the hint of syntax_error_finding (rules.py:221). Note (not blocking): in
  check_leftovers the line-based PMQ201/PMQ203 checks of that file already ran before the parse; only PMQ202 is
  skipped. The row copies the tool's own hint, as the task constraint asks.
- instrument_plugins.rst:158 PMQ300: rules.py:514 (check_plugin_source, instrument modules) and rules.py:708
  (check_extension_source). Matches "instrument or extension module".
- RST: rows keep the 8-char code column; the last column overflowing the border is already the case for many
  existing rows (allowed in simple tables). docutils parse of the branch file reports no table error (only
  unresolved `include` paths, an artefact of parsing outside Sphinx). Full Sphinx build: unverified.

## 3. Behaviour and API
- Docs only, no code touched: no public name, signature, default or warning changed.

## 4. Tests
- n/a: docs task, no test expected.

## 5. Docs
- Every factual claim in the three rows matches rules.py (see 2).

## Findings
none

## Filed outside the diff
none

summary: Adds the three check_plugin codes PMQ100, PMQ200 and PMQ300 to the codes table of instrument_plugins.rst, wording checked against rules.py.
