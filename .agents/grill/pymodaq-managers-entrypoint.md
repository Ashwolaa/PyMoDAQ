# Grill: pymodaq-managers-entrypoint

## Decision
`pymodaq` reads the entry-point group `pymodaq.managers` (`packages/pymodaq/src/pymodaq/utils/managers/extra_managers.py:23`, `dashboard.py:172`), and `pymodaq_ontology` declares it (advisor-compat, 2026-11-28). The plugin tooling does not know it: it is absent from `pymodaq_utils/plugin_tools/checks.py:46-48` (`ENTRYPOINT_GROUPS` / `OPTIONAL_ENTRYPOINT_GROUPS`) and from the generators `hatch_build_plugins.py` and `setup_plugin.py`. So a plugin cannot be scaffolded with it and `check_plugin` does not validate it. Supporting it means work in pymodaq_utils' tooling; deprecating it means a shim + `deprecation_msg` in pymodaq. The two lead to different PRs.

## Questions
1. Is `pymodaq.managers` an official plugin extension point (support it in `check_plugin` and the generators), or an internal/experimental hook to deprecate?
   Recommended: support it. It is live in the dashboard and at least one org package (`pymodaq_ontology`) registers under it.
2. If supported: should it be an optional group (`OPTIONAL_ENTRYPOINT_GROUPS`, like other non-instrument groups) rather than a required one?
   Recommended: optional; a plugin without managers must still pass `check_plugin`.
3. Should the plugin template (`pymodaq_plugins_template`) gain a `managers` example, or only the checks/generators?
   Recommended: checks and generators only now; a template example later, outside this fork.
4. Should `entrypoint_groups_sync_test.py` (T-pymodaq_utils-M12) cover this group too?
   Recommended: yes, once the group is added; it is what that test is for.
