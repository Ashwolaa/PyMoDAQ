# Plan: pymodaq_data — 2026-11-22
base commit: a33731c4f   mode: run

Scan: .agents/scans/pymodaq_data-984e3312136d.md (sha256 f5b3d7e2930606113866580120ef3d41cb90a461c8bf8a200d5f5c1173d67bdd). No scanner missing. Open findings (step 3b): none.
Advisors: quality, performance (no threading findings, no profile: perf items need a pyinstrument run first), docs, compat. advisor-uxui not run (scope not UI).
Arbiter (binding): K1 and K2 touched the same files, so they are one task; apply the import cleanup first, then the exception edits (line numbers shift).

## T-pymodaq_data-001 Imports and exception-handling hygiene
- scope: pymodaq_data   specialty: hygiene   risk: low
- files (under packages/pymodaq_data/src/pymodaq_data/):
  - imports: data.py:9 (ABCMeta), :16 (Type), :41 (ureg); h5modules/data_saving.py:26 (duplicate F811), unused `time`, `Tuple`; h5modules/browsing.py, exporter.py, h5modules/utils.py, plotting/plotter/plotter.py, plotting/plotter/plotters/matplotlib_plotters.py, process_to_scalar.py, slicing.py; h5modules/exporters/hyperspy.py:16 (remove only get_h5_data_from_node, keep extract_axis and verify_axis_data_uniformity)
  - exceptions: F841 data.py:1100,2108,3267, h5modules/data_saving.py:513; E722 -> `except Exception` at h5modules/exporters/hyperspy.py:142, numpy_func.py:46; B904 `from err` (add `as err` where missing) data.py:1017,3303,3402,4265,4296, h5modules/backends.py:980, exporters/hyperspy.py:89; B012 move return out of finally at data.py:2111 and plotting/plotter/plotter.py:37
- do not touch: numpy_func.py:6 HANDLED_UFUNCS (re-exported, data.py:40 imports it), saving.py:24-32, all __init__.py re-exports, backends.py:12/1313, h5modules/utils.py:34 (return in finally keeps exporter discovery alive), numpy_func.py:47 (returns NotImplementedError instead of raising: out of scope, file a finding)
- note: ~100 changed lines; if over 300, split by file group. Check re-importers by grep before each import removal. Tests: cd packages/pymodaq_data && pytest under PYTEST_QT_API=pyqt6 and pyside6, plus layering_test.
- verdicts: decider-compat-risk: approve (K1 round 1; K2 vetoed numpy_func.py:6, approved in round 2 on amended scope); decider-triage (fresh instance): approve (K1 with conditions; K2 with numpy_func.py:6 dropped)
- status: approved

## Dropped / deferred (no task)
- B012 h5modules/utils.py:34: return in finally is intentional; leave or noqa.
- B028 stacklevel (7 in data.py): needs pytest.warns check. B006 mutable defaults (data.py 2146, 3506, 3537, 3567, 3612; saving.py 298, 310): behaviour change on public signatures.
- Public re-exports (__init__.py F401, saving.py:29-32), vulture 60-79%, vulture exc_* args, B027 bases: public API, compat-protected. `__all__` in pymodaq_data/__init__.py deferred (needs compat review).
- Radon C/D (data.py _slicer D24, from_xarray D21), jscpd 3.68%, UP/SIM/F541/I001: exceed cap or break hard rule 5.
- Perf items: unmeasured. Docs: data_management.rst heading unverified.
