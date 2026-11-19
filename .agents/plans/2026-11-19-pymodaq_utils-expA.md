# Plan: pymodaq_utils — 2026-11-19 (Experiment A, advisors on haiku)
base commit: f0656d94c   mode: run   run-id: 2026-11-19-utils-plan-expA

Fresh full deliberation: ruff (196), vulture, radon, jscpd (1.81% dup) -> 4 advisors -> decider-triage -> compat-risk + fresh triage (+ test-change for T3, arbiter for T1/T2). No scanner missing.
Deferred (not tasks): typing modernisation UP006/UP035/UP045; radon refactors (_literal_value F42, check_extension_source F65, update_pyproject_classifiers D21) need a staged plan; whitespace/I001/UP009 only inside files a task already touches.
Never touch: abstract.py:12 abstractmethod (imported by pymodaq h5modules/module_saving.py:16), __init__.py:15, serialize/factory.py:3 and serializer.py:3 re-exports, serializer_legacy.py:13, safe_pickle.py:53 pid (parameter of persistent_load, not an import).

## T-pymodaq_utils-001 Remove unused imports (internal modules)
- scope: pymodaq_utils   specialty: hygiene
- risk: low
- files: `config.py:3,11,13,23,118`, `environment.py:3`, `mysocket.py:8`, `serialize/mysocket.py:1`, `math_utils.py:7`
- verdicts: decider-compat-risk: approve in round 1, VETO in round 2 — duplicates draft PR #3 (same concern, same lines), nothing new once safe_pickle and config.py:118 are dropped; decider-triage (fresh): veto in round 1 (same reason), approve narrowed in round 2 — items still present in current source, overlap is no reason to veto in a fresh run
- status: blocked — decisioners still split after round 2; human decides: fold any leftovers into PR #3 (arbiter's suggestion) or drop

## T-pymodaq_utils-002 Bare excepts and exception chaining
- scope: pymodaq_utils   specialty: hygiene
- risk: low
- files: `environment.py:153`, `packages.py:96` (except: -> except Exception:), `config.py:325-326` (raise ... from e; also clears F841 at :118/:325)
- verdicts: decider-compat-risk: approve — both bare excepts only pass; same ConfigError and message; decider-triage (fresh): approve — claims confirmed in source
- arbiter: T1 and T2 touch config.py/environment.py; run T1/PR #3 first, T2 branches from dev_agent after #3 merges and re-finds its lines.
- status: approved

## T-pymodaq_utils-003 Mutable default arguments
- scope: pymodaq_utils   specialty: refactor
- risk: medium
- files: `utils.py:444,458,475` (paths=[] -> None; recursive calls must keep passing paths), `utils.py:459,476,511` (filters -> tuple), `array_manipulation.py:151` (window -> tuple), `math_utils.py:616` (center -> tuple); update docstrings at utils.py:447,463,482
- tests: add a regression test under packages/pymodaq_utils/tests only; existing tests array_manipulation_test.py:82-97 and utils_test.py:209-220 must stay unchanged
- verdicts: decider-compat-risk: approve — public signatures keep working, defaults only read; decider-triage (fresh): approve — confirmed in source; decider-test-change: approve — only adds a test, veto if any existing test line is edited
- status: proposed (public functions, touches tests)
