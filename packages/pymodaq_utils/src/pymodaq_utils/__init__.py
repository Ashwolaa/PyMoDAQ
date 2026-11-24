"""Utilities shared by all PyMoDAQ packages.

Importing this package has side effects:

* ``__version__`` is read from the installed ``pymodaq_utils`` distribution
  (fallback ``'0.0.0dev'`` if it is not installed).
* The ``pymodaq`` base logger is created with a handler
  (``set_logger('pymodaq', add_handler=True, base_logger=True)``).
* ``pymodaq_utils.serialize.serializer`` is imported; it re-exports
  ``SerializableFactory`` (whose registry receives the classes decorated with
  ``SerializableFactory.register_decorator()``) and the ``SERIALIZABLE`` type alias
  from ``serializall``.
* ``CONFIG = GlobalConfig()`` is instantiated. Importing ``pymodaq_utils.config``
  registers the ``utils`` config, which loads its toml files and creates them
  (and their folders) if they are missing: the system file from the template,
  the user file from ``dict_to_add_to_user()``.

A failure in the logger/serializer step prints a message and the import goes on.
Any other failure is logged (printed if the logger does not exist) and the names
defined after it are then missing.
"""

try:
    from pymodaq_utils.logger import set_logger
    from pymodaq_utils.utils import get_version, PackageNotFoundError
    try:
        __version__ = get_version('pymodaq_utils')
    except PackageNotFoundError:
        __version__ = '0.0.0dev'
    try:
        logger_var = set_logger('pymodaq', add_handler=True, base_logger=True)
        logger_var.info('')
        logger_var.info('')
        logger_var.info('************************')
        logger_var.info("Registering Serializables...")
        from pymodaq_utils.serialize.serializer import SerializableFactory, SERIALIZABLE
        logger_var.info("Done")
        logger_var.info('************************')
    except Exception:
        print("Couldn't create the local folder to store logs , experiments...")

    from pymodaq_utils.config import GlobalConfig as Config

    CONFIG = Config()  # to ckeck for config file existence, otherwise create one


except Exception as e:
    try:
        logger_var.exception(e)
    except Exception:
        print(e)
