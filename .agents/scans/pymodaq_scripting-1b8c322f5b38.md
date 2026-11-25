# Scan: pymodaq_scripting
path: packages/pymodaq_scripting/src/pymodaq_scripting   tree: 1b8c322f5b38
tools: ruff 0.17.5, vulture 2.16, radon 6.0.1, jscpd 5.4.3

## ruff (19 findings, repo config)
### Bug risk (0)
- none
### Unused imports (5)
- packages/pymodaq_scripting/src/pymodaq_scripting/__init__.py:1 F401 `.devices.Actuator` imported but unused; consider removing, adding to `__all__`, or using a redundant alias
- packages/pymodaq_scripting/src/pymodaq_scripting/__init__.py:1 F401 `.devices.Dashboard` imported but unused; consider removing, adding to `__all__`, or using a redundant alias
- packages/pymodaq_scripting/src/pymodaq_scripting/__init__.py:1 F401 `.devices.Detector` imported but unused; consider removing, adding to `__all__`, or using a redundant alias
- packages/pymodaq_scripting/src/pymodaq_scripting/examples/dashboard_script.py:1 F401 `pymodaq_scripting.Actuator` imported but unused
- packages/pymodaq_scripting/src/pymodaq_scripting/examples/dashboard_script.py:1 F401 `pymodaq_scripting.Detector` imported but unused
### Simplifications (1)
- packages/pymodaq_scripting/src/pymodaq_scripting/utils.py:60 SIM118 Use `key in dict` instead of `key in dict.keys()`
### Style, counted only (13; per rule: findings / files)
- I001: 5 / 5
- UP037: 4 / 1
- W292: 4 / 4

## vulture (4 findings at >= 60% confidence)
### >= 80% confidence (3)
- packages/pymodaq_scripting/src/pymodaq_scripting/devices.py:13 unused import 'DataActuator' (90%)
- packages/pymodaq_scripting/src/pymodaq_scripting/utils.py:18 unused import 'DataActuator' (90%)
- packages/pymodaq_scripting/src/pymodaq_scripting/utils.py:167 unused variable 'parameter' (100%)
### 60-79% confidence, counted per file (mostly public API seen as unused)
- packages/pymodaq_scripting/src/pymodaq_scripting/examples/simple_script.py: 1

## radon cyclomatic complexity, rank C or worse (0)
- none

## jscpd duplication: 4.01% of lines, 2 clones
- packages/pymodaq_scripting/src/pymodaq_scripting/devices.py:99-120 = packages/pymodaq_scripting/src/pymodaq_scripting/devices.py:172-193 (22 lines)
- packages/pymodaq_scripting/src/pymodaq_scripting/utils.py:203-211 = packages/pymodaq_scripting/src/pymodaq_scripting/utils.py:215-223 (9 lines)
sha256: ec10854d1c2857fc
(scanned at commit ad00c6425; not part of the hash)
