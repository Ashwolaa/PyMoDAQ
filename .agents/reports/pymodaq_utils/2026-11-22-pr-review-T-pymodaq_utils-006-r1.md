verdict: approve
public_api: no
behaviour_change: no
fails_without_fix: n/a

# PR review T-pymodaq_utils-006 r1 (run 2026-11-22-merge-T-pymodaq_utils-006-r1)
Branch agent/pymodaq_utils/refactor/2026-11-22-delete-the-dead, 2 files, +34/-20 (54 changed lines).

## 1. Task match and drift
- packages/pymodaq_utils/src/pymodaq_utils/config.py:594 all three plural branches (backends, debug_levels, dynamics) deleted, as the task's delete option asks; ConfigError is not caught (constraint honoured).
- config.py:579-580 docstring rewritten to match the code after the deletion; no other line touched, no reformatting.
- tests/config_test.py: only additions (import of ConfigError, CustomPymodaqConfig fixture class, TestConfigPluralKeys); existing tests untouched.
- `merge_gate.py lint`: LINT OK (54 changed lines, product files only, trailers present).

## 2. Correctness
- BaseConfig.__call__ (config.py:337-343) catches KeyError from getitem_recursive and raises ConfigError (subclass of Exception, not KeyError, config.py:288), so the deleted `except KeyError` handlers could never run: dead code, verified.
- No caller in packages/ passes 'backends', 'debug_levels' or 'dynamics' as a key (grep), and no TOML template in packages/ has them as section names; only the test fixture has qtbackend.backends.
- Note (not blocking): a path holding both a plural key and a different singular key (e.g. ('backends', 'debug_level')) now goes to the singular branch instead of the plain lookup. No such path exists in any template or caller, so no reachable change.
- replace_item_in_list is still used (config.py:598, 607, 617), no unused import.

## 3. Behaviour and API
No public name, signature, default, return value or raised exception changes on any reachable path. Hard rule 1 not concerned.

## 4. Tests
- Branch test file run as tests/config_review_tmp_test.py against dev_agent code: TestConfigPluralKeys 5 passed. This is expected: the task is a dead-code deletion with a characterisation test pinning current behaviour, so there is no failing-without-fix case (n/a). Temp file deleted, git status clean.
- Assertions are exact (list equality, pytest.raises(ConfigError) on three missing plural paths).
- Pre-existing failure tests/config_test.py::test_nested_update_from_user (reported by the caller on both Qt backends) is task T-pymodaq_utils-008, not this branch.

## 5. Docs and docstrings
config.py:579-580 claim "plural spelling is forwarded unchanged, missing plural key raises ConfigError, no fallback to singular" matches the code (subject to the mixed-path note above).

summary: Removes the three unreachable `except KeyError` plural-key fallbacks in Config.__call__ (BaseConfig.__call__ only raises ConfigError), updates the docstring, and adds characterisation tests pinning plural-key lookups.
