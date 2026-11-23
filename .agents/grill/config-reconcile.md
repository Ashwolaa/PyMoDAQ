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
