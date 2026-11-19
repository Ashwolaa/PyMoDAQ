Plugin tools
************

Tools to develop and maintain PyMoDAQ instrument plugins (see :ref:`instrument_plugin_doc` in the
developer documentation).

.. automodule:: pymodaq_utils.plugin_tools
   :no-index:

Contract
--------

.. automodule:: pymodaq_utils.plugin_tools.contract
   :no-index:
   :members: PluginMethod, methods_of, mandatory_methods, recommended_methods, legacy_names

Rules
-----

.. automodule:: pymodaq_utils.plugin_tools.rules
   :no-index:
   :members: Finding

Checks
------

.. automodule:: pymodaq_utils.plugin_tools.checks
   :no-index:
   :members: PluginModule, CheckResult, PluginReport, find_plugin_modules, check_plugin_package, check_plugin_file

Scaffold
--------

.. automodule:: pymodaq_utils.plugin_tools.scaffold
   :no-index:
   :members: create_instrument, find_package_folder

Platforms
---------

.. automodule:: pymodaq_utils.plugin_tools.platforms
   :no-index:
   :members: normalize_architecture, describe, unsupported_reason, classifiers_for, python_classifiers
