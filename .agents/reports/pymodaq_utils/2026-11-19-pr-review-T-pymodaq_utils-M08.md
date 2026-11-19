verdict: changes
public_api: no
behaviour_change: no
fails_without_fix: n/a

# PR review T-pymodaq_utils-M08 (branch agent/pymodaq_utils/docs-api-pages/2026-11-19, commit b152eefe2)

## Task match
- Diff is 5 docs files, +65 lines (cap 300): 4 new pages under docs/src/api/utility_api/ and 4 toctree entries in
  docs/src/api/API_Utility_Library.rst:17-20. No product or test files touched (`git diff dev_agent <b> -- packages` empty),
  legacy_to_current.rst not touched, no reformatting of untouched lines. In scope.
- Style matches the existing pages (automodule + :no-index: + explicit :members:, as in mathematical.rst / utility_classes.rst).

## Correctness (verified by import and by a local sphinx 9.2 build of the 4 pages with the branch conf.py;
## extensions missing locally were filtered out: sphinx_qt_documentation, sphinx_autodoc_typehints and a few others, so a full CI docs build is unverified)
- All 33 listed members exist in the named modules (checked with getattr); the `instrument_plugin_doc` label exists
  (docs/src/developer_folder/instrument_plugins.rst:1). Build: no warning from the new pages.
- Problem: autodoc silently drops explicitly listed members that have no docstring (conf.py sets no undoc-members).
  Six listed names never render:
  - docs/src/api/utility_api/config.rst:6: GlobalConfig (config.py:445), ConfigError (config.py:272), get_config_file (config.py:152) have no docstring, absent from the page.
  - docs/src/api/utility_api/enums.rst:6: StrEnum (enums.py:12) has no docstring, absent from the page (only BaseEnum, enum_checker render).
  - docs/src/api/utility_api/logger.rst:6: get_base_logger (logger.py:85) has no docstring, absent from the page.
  - docs/src/api/utility_api/plugin_tools.rst:22: Severity (plugin_tools/rules.py:116) has no docstring, absent from the page.
- Minor (no change required): with :no-index: no module targets are created, so the :mod: links in the
  plugin_tools/__init__.py docstring rendered on plugin_tools.rst:7 do not resolve to the sections below (same convention as existing pages).

## Behaviour and API
- Docs only; no public name, signature, default or exception changes.

## Tests
- n/a: no code or test change, nothing to fail without a fix. Test-file copy step not applicable.

## Docs
- Every listed name is real; the only mismatch is the six names above that the .rst promises but the build omits.

## Required changes
1. Remove GlobalConfig, ConfigError, get_config_file (config.rst), StrEnum (enums.rst), get_base_logger (logger.rst) and
   Severity (plugin_tools.rst) from the :members: lists, so the pages list exactly what renders; adding docstrings to
   those objects is product-source work for a separate task. (Do not add :undoc-members: globally: it would also pull in
   every undocumented method of the listed classes.)

summary: Adds API reference pages for pymodaq_utils config, logger, enums and plugin_tools; six listed members without docstrings are silently dropped by autodoc and should be removed from the :members: lists.
