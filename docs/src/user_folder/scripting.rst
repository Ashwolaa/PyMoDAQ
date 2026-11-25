.. _scripting:

Scripting PyMoDAQ
=================

PyMoDAQ can be controlled from a plain Python script.
The :mod:`pymodaq_scripting` package provides a small, synchronous and asynchronous API
that lets you move actuators, acquire data, and manage experiments or states programmatically.

Communication between the script and the running PyMoDAQ application uses
`LECO`_.  Before running any script you must therefore have:

1. A LECO **Coordinator** running (``coordinator`` in a terminal, or the PyMoDAQ setting
   ``run_coordinator_at_startup`` enabled).
2. The PyMoDAQ components you want to control already **connected to LECO**
   (see :ref:`leco_communication`).

.. _LECO: https://leco-laboratory-experiment-control-protocol.readthedocs.io

Public Classes
--------------

Three classes are available directly from :mod:`pymodaq_scripting`:

.. list-table::
   :header-rows: 1
   :widths: 20 80

   * - Class
     - Purpose
   * - :class:`~pymodaq_scripting.devices.Dashboard`
     - Connect to a running Dashboard, apply experiments/states, retrieve
       the list of loaded modules.
   * - :class:`~pymodaq_scripting.devices.Actuator`
     - Move an actuator (absolute, relative, home), read its current position,
       stop a move.
   * - :class:`~pymodaq_scripting.devices.Detector`
     - Acquire a single frame (snap) or a continuous stream (grab), stop
       acquisition.

Most methods that communicate over the network return a
:class:`~concurrent.futures.Future`.  Calling ``.result()`` on it **blocks**
until the remote component replies and the result is set in the corresponding `Future`.
The exceptions are ``grab``, ``stop_grab``, ``set_settings`` and ``sign_out``, and
``snap``, which returns ``None`` while a continuous grab is running.

.. code-block:: python

   future = actuator.move_abs('90°')   # non-blocking — returns immediately
   position = future.result()           # blocks until the move is finished


Connecting to a Dashboard
--------------------------

A good starting point is a :class:`~pymodaq_scripting.devices.Dashboard`.
It lets you load an experiment (which starts the instrument modules), then retrieve
the corresponding :class:`~pymodaq_scripting.devices.Actuator` and
:class:`~pymodaq_scripting.devices.Detector` objects with a single call.

.. code-block:: python

   from pymodaq_scripting import Dashboard

   dashboard = Dashboard()

   # list available experiments and apply one
   print(dashboard.get_experiments().result())
   # >>> ['default']
   dashboard.apply_experiment('default').result()

   # list available states (instrument settings and actuator values) and apply one
   print(dashboard.get_states().result())
   # >>> ['default', 'my_custom_state']
   dashboard.apply_state('default').result()

   # retrieve all loaded modules by name
   print(dashboard.get_devices().result())
   # >>> {'actuators': ['Theta', 'Temperature'], 'detectors': ['Camera', 'Det0D']}

   # get ready-to-use Actuator / Detector objects
   devices = dashboard.get_scripting_devices()
   theta  = devices['actuators']['Theta']
   camera = devices['detectors']['Camera']


Controlling Actuators
----------------------

.. code-block:: python

   from pymodaq_scripting import Actuator
   from pymodaq_data import Q_

   theta = Actuator('Theta')

   # read current position
   pos = theta.get_actuator_value().result()

   # absolute move (accepts a DataActuator, a Quantity, a plain number, or a string)
   new_pos = theta.move_abs(Q_('90°')).result()

   # relative move
   theta.move_rel(Q_('10°')).result()

   # go to home position
   theta.move_home().result()

   # stop a running move
   theta.stop_move()


Acquiring Data with Detectors
------------------------------

.. code-block:: python

   import time

   from pymodaq_scripting import Detector

   camera = Detector('Camera')

   # single acquisition (blocking)
   data = camera.snap().result()   # returns a DataToExport

   # continuous acquisition: each call to grab() toggles, the first one starts it
   frames = camera.grab(keep=True)  # list, filled with each DataToExport received
   time.sleep(2)
   camera.grab()                    # second call: stops the grab, returns None
   print(len(frames))

``grab(keep=True)`` returns the list only from the call that starts the grab;
``keep`` is ignored by the call that stops it, and ``grab()`` without ``keep``
returns ``None``. :meth:`~pymodaq_scripting.devices.Detector.stop_grab` also
stops the grab. While grabbing, ``snap()`` sends nothing and returns ``None``.


A Complete Scan Script
-----------------------

The following script sweeps an actuator over a range, snaps two detectors at
each step, and saves the result to an HDF5 file.

.. code-block:: python

   from pathlib import Path

   from pymodaq_data import Q_
   from pymodaq_data.h5modules.backends import GroupType
   from pymodaq_data.h5modules.data_saving import DataToExportEnlargeableSaver
   from pymodaq_scripting import Actuator, Detector

   theta  = Actuator('Angle')
   det0d  = Detector('Det0D')
   det1d  = Detector('Det1D')

   base   = theta.get_actuator_value().result()
   target = base + Q_('90°')
   step   = Q_('10°')
   count  = int(((target - base) / step).quantities[0].m[0]) + 1

   filename = Path(r'C:\Data\2026\scripted_data.h5')

   with DataToExportEnlargeableSaver(
       filename,
       enl_axis_names=('count',),
       enl_axis_units=('',),
   ) as saver:

       group   = saver.add_group('Script', group_type=GroupType.data,
                                 where='/RawData/', title='scripted_data')
       group0d = saver.add_det_group(where=group, title=det0d.name)
       group1d = saver.add_det_group(where=group, title=det1d.name)

       for idx in range(count):
           value       = theta.move_abs(base + idx * step).result()
           dte0d_future = det0d.snap()   # fire both snaps concurrently …
           dte1d_future = det1d.snap()
           saver.add_data(group0d, dte0d_future.result(), (value.value(),))
           saver.add_data(group1d, dte1d_future.result(), (value.value(),))


.. seealso::

   :ref:`leco_communication` — how to start the Coordinator and connect
   PyMoDAQ modules as LECO Actors.

   :ref:`leco_component_mixin` — developer guide for exposing a new component
   over LECO and creating the corresponding scripting wrapper.
