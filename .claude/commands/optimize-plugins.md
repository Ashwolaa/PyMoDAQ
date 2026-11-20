---
description: Plugin compatibility: discover PyMoDAQ plugins (PyPI and users' GitHub repos), assess them, port one to the current PyMoDAQ
argument-hint: "discover | assess <name|url> [--top N] | port <name|url> [--explain]"
---

You are the plugin coordinator. Arguments: `$ARGUMENTS`. Prepared 2026-11-19; the owner chose: ports go to a fork on
the owner's account (`[project].fork` owner), clearly marked as agent-made; a PR to the plugin author only after the
owner's explicit go. Never push to, open issues on, or comment in a repository you do not own.

0. Note the start time first: `date -u +%FT%TZ` (START). Run id: `<date>-plugins-<mode>[-<name>]`.
1. Read `.agents/core/rules.md`, `.agents/profile.toml`. Run `budget.py check --kind rd`; stop on STOP. On `dev_agent`, clean.
2. **discover**: launch `plugin-scout` in discover mode. It lists plugins from (a) PyPI, names `pymodaq_plugins_*` /
   `pymodaq-plugins-*`; (b) GitHub repositories named `pymodaq_plugins*` (`gh search repos pymodaq_plugins --limit 300`),
   users' repos included; (c) forks of `PyMoDAQ/pymodaq_plugins_template`. One line per plugin in
   `.agents/plugins/index.jsonl`: `name, source (pypi|github|fork), url, owner, license, last_commit, pymodaq_pin,
   entry_points, stars, downloads (pypi, if known), status (new|assessed|ported|skipped), note`. Same name and url = same
   line (update it). Also run `python3 packages/pymodaq/src/pymodaq/utils/plugin_testing/compliance_report.py --pypi
   --markdown` and keep its table in `.agents/plugins/compliance-<date>.md`.
3. **assess** (`--top N` = the N most used by downloads, then stars; default 30, one scout launch per 10 plugins):
   for each plugin `plugin-scout` makes a shallow clone under `~/PyMoDAQ-plugins/<name>` (outside every repo), installs it
   into a throwaway venv next to it against the editable PyMoDAQ of this worktree, and runs `check_plugin <package>
   --strict-imports -v`, an import of each entry point, and the legacy-name scan. It writes
   `.agents/plugins/<name>.md` (<= 40 lines) and appends every PyMoDAQ name the plugin imports to
   `.agents/plugins/api-usage.jsonl` (`module, name, plugin, file:line`). Then summarise: `.agents/plugins/api-usage.md`
   (names by number of plugins using them: decider-compat-risk reads it before any veto on public API) and
   `.agents/practices/plugins.md` (<= 40 lines: good and bad patterns, each with the count of plugins and two examples).
   Problems that are PyMoDAQ's (a shim missing, a template step that most plugins get wrong, a check_plugin false
   positive) are filed with `findings.py add --kind plugin --scope <package>`.
4. **port** `<name>` (one plugin per run; license must be OSI-approved, else stop and say so): launch
   `spec-plugin-port`. In `~/PyMoDAQ-plugins/<name>` it forks the repo to the owner's account (`gh repo fork --remote`),
   works on branch `agent/pymodaq-port/<date>`, applies the template structure and the `legacy_to_current` renames, fixes
   what `check_plugin` reports until it is clean (or lists what it could not fix), adds `README_AGENT.md` from
   `.agents/plugins/README_AGENT.template.md`, commits with `[agent]` in the subject and the trailer
   `Agent-Run: <run-id>`, and pushes to the fork only. It drafts the PR text for the author in
   `.agents/plugins/<name>-pr.md`. Do not open that PR: show it to the owner and wait for an explicit go.
5. Update the plugin's line in `index.jsonl` (`ported`, fork url, branch), log
   `ledger.py add --command optimize-plugins --session current --since <START> --outcome ok`, commit `.agents` on
   `dev_agent` (subject ending `[skip ci]`, rules.md 20) and push. Report in <= 20 lines with the paths written; for `port`, the fork branch URL and the PR draft path.

With `--explain`: list what each step would do and touch nothing outside `.agents/reports/plugins/`.
Every step runs in the foreground (rules.md 17); a notification after your report is not a new invocation.
