# Grill: config-reconcile

## Decision
Existing config files freeze the template on first start and only gain missing keys, so retyped, renamed or re-defaulted keys survive branch switches (evidence: `.agents/research/config-schema.md`, prototype `agent-rd/config-schema` @272b75d0e). Should `BaseConfig.load` rewrite the user's files to match the template (retype reset, migrations, backup, snapshot), or only report drift? Rewriting changes user data and public plugin behaviour, and the two answers lead to different work.

## Questions
1. Should `BaseConfig.load` rewrite user config files (reset retyped keys, apply migrations, take new defaults for untouched keys), or only log a warning listing drifted keys?
   Recommended: rewrite, but only with a `<file>.<stamp>.bak` backup and one warning; drift that is only reported leaves the branch-switch breakage in place.
2. List -> scalar change: the prototype keeps the first element and drops the others. Accept, or reset to the template default?
   Recommended: reset to the default with backup (no silent partial value).
3. `.bak` files grow on every branch switch: cap them (keep last N), or keep all?
   Recommended: keep the last 3 per file.
4. Template snapshot (`config/.template_snapshots/<name>.toml`) is overwritten at each load: acceptable, or version it?
   Recommended: overwrite only when the template changed.
5. Cross-process safety: add a file lock around rewrite, or accept the race (rewrite is rare, atomic via temp file + replace)?
   Recommended: atomic replace, no lock.
6. Plugins: new behaviour resets a plugin value whose type differs from its template. Accept for plugins, or limit reconcile to core configs first?
   Recommended: core configs first, plugins opt in via `config_schema_version`.
7. Upstream timing (grill config-isolation: fork first, one clean week)?
   Recommended: same, after isolation (K1/K2) is merged.

## Answers
Owner 2026-11-26: accepted the recommended answer to every question.
1. Rewrite user config files (retype reset, migrations, new default for untouched keys) with a `<file>.<stamp>.bak` backup and one warning. Reason: reporting only leaves the branch-switch breakage in place.
2. List -> scalar: reset to the template default, with backup. Reason: no silent partial value.
3. Keep the last 3 `.bak` files per config file.
4. Overwrite the template snapshot only when the template changed.
5. Atomic replace (temp file + replace), no file lock.
6. Core configs first; plugins opt in via `config_schema_version`.
7. Fork first, upstream only after config-isolation (K1/K2) is merged, as in grill config-isolation.

## Direction
Build reconcile-on-load for the core configs only: `BaseConfig.load` rewrites a drifted user file to match the template (retyped keys reset, migrations applied, untouched keys follow a new default), always after a backup (last 3 kept) and with one warning, written atomically without a lock; the template snapshot is rewritten only when the template changed. Lists that became scalars reset to the default. Plugin configs are not touched until a plugin declares `config_schema_version`. Fork only until config-isolation is merged. Ruled out: warn-only reporting, keeping the first element of a list, a file lock, versioned snapshots, reconciling plugin configs by default.
