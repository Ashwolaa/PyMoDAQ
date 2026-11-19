# Scan: pymodaq_utils
path: packages/pymodaq_utils/src/pymodaq_utils   tree: 45ab1aceab89
tools: ruff 0.17.5, vulture 2.16, radon 6.0.1, jscpd 5.4.3

## ruff (176 findings, repo config)
### Bug risk (8)
- packages/pymodaq_utils/src/pymodaq_utils/array_manipulation.py:151 B006 Do not use mutable data structures for argument defaults
- packages/pymodaq_utils/src/pymodaq_utils/enums.py:86 B007 Loop control variable `ind` not used within loop body
- packages/pymodaq_utils/src/pymodaq_utils/factory.py:29 B024 `ObjectFactory` is an abstract base class, but it has no abstract methods or properties
- packages/pymodaq_utils/src/pymodaq_utils/math_utils.py:616 B006 Do not use mutable data structures for argument defaults
- packages/pymodaq_utils/src/pymodaq_utils/utils.py:464 B006 Do not use mutable data structures for argument defaults
- packages/pymodaq_utils/src/pymodaq_utils/utils.py:482 B006 Do not use mutable data structures for argument defaults
- packages/pymodaq_utils/src/pymodaq_utils/utils.py:518 B006 Do not use mutable data structures for argument defaults
- packages/pymodaq_utils/src/pymodaq_utils/utils.py:731 B007 Loop control variable `ind` not used within loop body
### Unused imports (9)
- packages/pymodaq_utils/src/pymodaq_utils/__init__.py:36 F401 `pymodaq_utils.serialize.serializer.SERIALIZABLE` imported but unused; consider removing, adding to `__all__`, or using a redundant alias
- packages/pymodaq_utils/src/pymodaq_utils/__init__.py:36 F401 `pymodaq_utils.serialize.serializer.SerializableFactory` imported but unused; consider removing, adding to `__all__`, or using a redundant alias
- packages/pymodaq_utils/src/pymodaq_utils/abstract.py:12 F401 `abc.abstractmethod` imported but unused
- packages/pymodaq_utils/src/pymodaq_utils/serialize/factory.py:3 F401 `serializall.factory.SERIALIZABLE` imported but unused
- packages/pymodaq_utils/src/pymodaq_utils/serialize/factory.py:3 F401 `serializall.factory.SerializableBase` imported but unused
- packages/pymodaq_utils/src/pymodaq_utils/serialize/factory.py:3 F401 `serializall.factory.SerializableFactory` imported but unused
- packages/pymodaq_utils/src/pymodaq_utils/serialize/serializer.py:3 F401 `serializall.factory.SERIALIZABLE` imported but unused
- packages/pymodaq_utils/src/pymodaq_utils/serialize/serializer.py:3 F401 `serializall.factory.SerializableBase` imported but unused
- packages/pymodaq_utils/src/pymodaq_utils/serialize/serializer.py:3 F401 `serializall.factory.SerializableFactory` imported but unused
### Simplifications (16)
- packages/pymodaq_utils/src/pymodaq_utils/__init__.py:35 F541 f-string without any placeholders
- packages/pymodaq_utils/src/pymodaq_utils/__init__.py:37 F541 f-string without any placeholders
- packages/pymodaq_utils/src/pymodaq_utils/array_manipulation.py:24 SIM103 Return the condition `result == set_size` directly
- packages/pymodaq_utils/src/pymodaq_utils/array_manipulation.py:143 E703 Statement ends with an unnecessary semicolon
- packages/pymodaq_utils/src/pymodaq_utils/array_manipulation.py:145 E703 Statement ends with an unnecessary semicolon
- packages/pymodaq_utils/src/pymodaq_utils/enums.py:56 SIM102 Use a single `if` statement instead of nested `if` statements
- packages/pymodaq_utils/src/pymodaq_utils/environment.py:96 F541 f-string without any placeholders
- packages/pymodaq_utils/src/pymodaq_utils/environment.py:100 F541 f-string without any placeholders
- packages/pymodaq_utils/src/pymodaq_utils/environment.py:192 E741 Ambiguous variable name: `l`
- packages/pymodaq_utils/src/pymodaq_utils/environment.py:193 E741 Ambiguous variable name: `l`
- packages/pymodaq_utils/src/pymodaq_utils/packages.py:156 F541 f-string without any placeholders
- packages/pymodaq_utils/src/pymodaq_utils/plugin_tools/checks.py:247 SIM102 Use a single `if` statement instead of nested `if` statements
- packages/pymodaq_utils/src/pymodaq_utils/plugin_tools/platforms.py:131 SIM105 Use `contextlib.suppress(ValueError, SyntaxError)` instead of `try`-`except`-`pass`
- packages/pymodaq_utils/src/pymodaq_utils/utils.py:475 SIM102 Use a single `if` statement instead of nested `if` statements
- packages/pymodaq_utils/src/pymodaq_utils/utils.py:649 SIM102 Use a single `if` statement instead of nested `if` statements
- packages/pymodaq_utils/src/pymodaq_utils/utils.py:711 SIM102 Use a single `if` statement instead of nested `if` statements
### Style, counted only (143; per rule: findings / files)
- I001: 24 / 21
- UP006: 28 / 8
- UP009: 6 / 6
- UP034: 1 / 1
- UP035: 18 / 11
- UP045: 30 / 5
- W291: 15 / 3
- W292: 3 / 3
- W293: 18 / 3

## vulture (139 findings at >= 60% confidence)
### >= 80% confidence (4)
- packages/pymodaq_utils/src/pymodaq_utils/safe_pickle.py:53 unused variable 'pid' (100%)
- packages/pymodaq_utils/src/pymodaq_utils/serialize/serializer_legacy.py:13 unused import 'Axis' (90%)
- packages/pymodaq_utils/src/pymodaq_utils/serialize/serializer_legacy.py:13 unused import 'DataToExport' (90%)
- packages/pymodaq_utils/src/pymodaq_utils/serialize/serializer_legacy.py:13 unused import 'DataWithAxes' (90%)
### 60-79% confidence, counted per file (mostly public API seen as unused)
- packages/pymodaq_utils/src/pymodaq_utils/__init__.py: 1
- packages/pymodaq_utils/src/pymodaq_utils/abstract.py: 1
- packages/pymodaq_utils/src/pymodaq_utils/array_manipulation.py: 7
- packages/pymodaq_utils/src/pymodaq_utils/categorizing.py: 3
- packages/pymodaq_utils/src/pymodaq_utils/config.py: 7
- packages/pymodaq_utils/src/pymodaq_utils/enums.py: 2
- packages/pymodaq_utils/src/pymodaq_utils/environment.py: 2
- packages/pymodaq_utils/src/pymodaq_utils/factory.py: 3
- packages/pymodaq_utils/src/pymodaq_utils/help.py: 1
- packages/pymodaq_utils/src/pymodaq_utils/logger.py: 1
- packages/pymodaq_utils/src/pymodaq_utils/math_utils.py: 21
- packages/pymodaq_utils/src/pymodaq_utils/mysocket.py: 1
- packages/pymodaq_utils/src/pymodaq_utils/packages.py: 5
- packages/pymodaq_utils/src/pymodaq_utils/plugin_testing.py: 1
- packages/pymodaq_utils/src/pymodaq_utils/plugin_tools/checks.py: 1
- packages/pymodaq_utils/src/pymodaq_utils/plugin_tools/contract.py: 2
- packages/pymodaq_utils/src/pymodaq_utils/plugin_tools/platforms.py: 1
- packages/pymodaq_utils/src/pymodaq_utils/plugin_tools/rules.py: 2
- packages/pymodaq_utils/src/pymodaq_utils/resources/hatch_build_plugins.py: 1
- packages/pymodaq_utils/src/pymodaq_utils/safe_pickle.py: 4
- packages/pymodaq_utils/src/pymodaq_utils/serialize/mysocket.py: 3
- packages/pymodaq_utils/src/pymodaq_utils/serialize/serializer_legacy.py: 24
- packages/pymodaq_utils/src/pymodaq_utils/serialize/utils.py: 5
- packages/pymodaq_utils/src/pymodaq_utils/singleton.py: 1
- packages/pymodaq_utils/src/pymodaq_utils/units.py: 10
- packages/pymodaq_utils/src/pymodaq_utils/utils.py: 25

## radon cyclomatic complexity, rank C or worse (29)
- packages/pymodaq_utils/src/pymodaq_utils/plugin_tools/rules.py:685 check_extension_source F(65)
- packages/pymodaq_utils/src/pymodaq_utils/utils.py:68 _literal_value F(42)
- packages/pymodaq_utils/src/pymodaq_utils/plugin_tools/rules.py:490 check_plugin_source E(38)
- packages/pymodaq_utils/src/pymodaq_utils/plugin_tools/rules.py:248 check_python_code D(28)
- packages/pymodaq_utils/src/pymodaq_utils/plugin_tools/rules.py:301 check_pyproject D(27)
- packages/pymodaq_utils/src/pymodaq_utils/plugin_tools/rules.py:601 _check_deprecated_api D(27)
- packages/pymodaq_utils/src/pymodaq_utils/plugin_tools/rules.py:388 check_leftovers D(24)
- packages/pymodaq_utils/src/pymodaq_utils/plugin_tools/platforms.py:160 update_pyproject_classifiers D(21)
- packages/pymodaq_utils/src/pymodaq_utils/plugin_tools/rules.py:564 _check_move_source D(21)
- packages/pymodaq_utils/src/pymodaq_utils/config.py:545 Config.__call__ C(19)
- packages/pymodaq_utils/src/pymodaq_utils/plugin_tools/checks.py:147 check_package_layout C(18)
- packages/pymodaq_utils/src/pymodaq_utils/plugin_tools/checks.py:221 check_move_class C(18)
- packages/pymodaq_utils/src/pymodaq_utils/plugin_tools/checks.py:443 PluginReport.format C(16)
- packages/pymodaq_utils/src/pymodaq_utils/plugin_tools/checks.py:579 resolve_file C(16)
- packages/pymodaq_utils/src/pymodaq_utils/plugin_tools/checks.py:631 main C(16)
- packages/pymodaq_utils/src/pymodaq_utils/plugin_tools/platforms.py:257 windows_only_files C(16)
- packages/pymodaq_utils/src/pymodaq_utils/plugin_tools/checks.py:380 check_plugin_module C(14)
- packages/pymodaq_utils/src/pymodaq_utils/plugin_tools/platforms.py:217 _imported_files C(14)
- packages/pymodaq_utils/src/pymodaq_utils/utils.py:135 _literal_array C(14)
- packages/pymodaq_utils/src/pymodaq_utils/plugin_tools/checks.py:290 _is_environmental C(13)
- packages/pymodaq_utils/src/pymodaq_utils/utils.py:481 recursive_find_expr_in_files C(13)
- packages/pymodaq_utils/src/pymodaq_utils/categorizing.py:9 categorize_items C(12)
- packages/pymodaq_utils/src/pymodaq_utils/plugin_tools/checks.py:493 check_plugin_package C(12)
- packages/pymodaq_utils/src/pymodaq_utils/config.py:535 Config C(11)
- packages/pymodaq_utils/src/pymodaq_utils/logger.py:18 set_logger C(11)
- packages/pymodaq_utils/src/pymodaq_utils/packages.py:100 get_pypi_pymodaq C(11)
- packages/pymodaq_utils/src/pymodaq_utils/plugin_tools/checks.py:537 resolve_target C(11)
- packages/pymodaq_utils/src/pymodaq_utils/plugin_tools/platforms.py:119 declared_in_class C(11)
- packages/pymodaq_utils/src/pymodaq_utils/plugin_tools/scaffold.py:319 create_instrument C(11)

## jscpd duplication: 1.90% of lines, 11 clones
- packages/pymodaq_utils/src/pymodaq_utils/math_utils.py:427-447 = packages/pymodaq_utils/src/pymodaq_utils/math_utils.py:457-477 (21 lines)
- packages/pymodaq_utils/src/pymodaq_utils/math_utils.py:376-394 = packages/pymodaq_utils/src/pymodaq_utils/math_utils.py:400-417 (19 lines)
- packages/pymodaq_utils/src/pymodaq_utils/plugin_tools/scaffold.py:112-126 = packages/pymodaq_utils/src/pymodaq_utils/plugin_tools/scaffold.py:242-256 (15 lines)
- packages/pymodaq_utils/src/pymodaq_utils/mysocket.py:54-67 = packages/pymodaq_utils/src/pymodaq_utils/serialize/mysocket.py:67-80 (14 lines)
- packages/pymodaq_utils/src/pymodaq_utils/math_utils.py:400-411 = packages/pymodaq_utils/src/pymodaq_utils/math_utils.py:423-434 (12 lines)
- packages/pymodaq_utils/src/pymodaq_utils/packages.py:159-169 = packages/pymodaq_utils/src/pymodaq_utils/utils.py:762-772 (11 lines)
- packages/pymodaq_utils/src/pymodaq_utils/array_manipulation.py:81-90 = packages/pymodaq_utils/src/pymodaq_utils/array_manipulation.py:104-114 (10 lines)
- packages/pymodaq_utils/src/pymodaq_utils/math_utils.py:326-335 = packages/pymodaq_utils/src/pymodaq_utils/math_utils.py:358-367 (10 lines)
- packages/pymodaq_utils/src/pymodaq_utils/utils.py:720-729 = packages/pymodaq_utils/src/pymodaq_utils/utils.py:740-749 (10 lines)
- packages/pymodaq_utils/src/pymodaq_utils/enums.py:13-21 = packages/pymodaq_utils/src/pymodaq_utils/enums.py:28-36 (9 lines)
- packages/pymodaq_utils/src/pymodaq_utils/plugin_tools/scaffold.py:57-63 = packages/pymodaq_utils/src/pymodaq_utils/plugin_tools/scaffold.py:204-210 (7 lines)
sha256: b5cacbf31fb260d7
(scanned at commit fff891935; not part of the hash)
