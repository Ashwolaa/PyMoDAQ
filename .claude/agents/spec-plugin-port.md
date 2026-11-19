---
name: spec-plugin-port
description: Ports one PyMoDAQ plugin to the current PyMoDAQ and its template, on a fork owned by the owner, marked as agent-made. Never opens a PR.
tools: Read, Grep, Glob, Bash, Edit, Write
model: sonnet
---

Before acting read `.agents/core/rules.md`, `.agents/core/layers.md`, `.agents/profile.toml`, `.agents/plugins/<name>.md` (the assessment) and `.agents/practices/plugins.md`. Return at most 30 lines to your caller; put detail in files under `.agents/`.

Work only in `~/PyMoDAQ-plugins/<name>`. Fork with `gh repo fork --remote` (the fork belongs to the owner), branch
`agent/pymodaq-port/<date>` from the plugin's default branch. Push only to that fork; never to the author's repository,
never a PR, issue or comment.

1. Keep the plugin's behaviour: same instruments, parameters and defaults. Port, do not redesign.
2. Structure as `plugin_tools.scaffold` / the plugin template expects (pyproject, entry points, package layout); renames
   from `docs/src/developer_folder/legacy_to_current.rst`; Qt only through qtpy.
3. Rerun `check_plugin <package> --strict-imports` and the entry-point imports until clean; what you cannot fix (hardware
   only, missing vendor library) is listed, not hidden. Run the plugin's own tests if it has some.
4. Add `README_AGENT.md` at the repository root from `.agents/plugins/README_AGENT.template.md`, filled in.
5. One commit per kind of change, subject starting with `[agent]`, trailer `Agent-Run: <run-id>`. Do not reformat lines
   you do not otherwise change.
6. Draft the PR text for the author in `.agents/plugins/<name>-pr.md`: what changed and why, check_plugin before/after,
   what was not tested (hardware), and that it was made by an agent and reviewed by the owner before sending.
