# Plugin Migration Guide

Moving from the legacy `DAQ_Move_base` / `DAQ_Viewer_base` interface to the
new unified plugin interface.

---

## Why migrate?

The legacy model creates one hardware thread per GUI module.  Two `DAQ_Move`
instances sharing the same physical controller each run their own thread and
pass a raw Python reference to the SDK object — no mutex, no queue.

The new model assigns **one `ControllerThread` per physical device**.  All
hardware I/O is serialised through that thread's Qt event loop.  `DAQ_Move`
and `DAQ_Viewer` become lightweight GUI subscribers that never touch the SDK
directly.

Benefits for plugin authors:
- No threading knowledge required — write synchronous Python, Qt handles
  serialisation.
- No `controller` / master-slave boilerplate.
- `Capabilities` replaces the hand-crafted parameter subtree for controller
  grouping.

---

## New-style plugin interface

```python
class MyStagePlugin:

    # ── Lifecycle ────────────────────────────────────────────────────────────

    def open(self, settings) -> None:
        """Open hardware.

        *settings* is the shared ``Parameter`` model (GUI thread).  Read
        connection details (port, address, …) from it.  Raise on failure —
        ``ControllerThread`` will catch the exception and emit
        ``hardware_status(False, reason)``.
        """
        port = settings['connection', 'port']
        self._sdk = MySDK(port)
        self._sdk.connect()

    def close(self) -> None:
        """Close hardware gracefully."""
        self._sdk.disconnect()

    # ── Data interface ───────────────────────────────────────────────────────

    def query_data(self, names: list[str] | None = None, fresh: bool = True):
        """Read one or more channels; return a DataToExport.

        *names* lists the requested channel names.  If None, return all.
        *fresh* = True means actually poll the hardware; False may use cache.
        """
        position = self._sdk.get_position()
        return DataToExport(
            name='MyStage',
            data=[DataRaw('axis_x', data=[np.array([position])])],
        )

    def change_to(self, name: str, value) -> None:
        """Write *value* to channel *name*."""
        if name == 'axis_x':
            self._sdk.move_absolute(value)
            # Block until move complete (ControllerThread runs this in the
            # hardware thread, so blocking here is safe for callers).
            self._sdk.wait_for_idle()

    # ── Capabilities ─────────────────────────────────────────────────────────

    @property
    def capabilities(self):
        from pymodaq.utils.leco.capabilities import (
            Capabilities, ContinuousVariable
        )
        return Capabilities(variables=[
            ContinuousVariable(name='axis_x', lo=-100.0, hi=100.0, epsilon=0.001),
        ])

    # ── Settings relay (optional) ────────────────────────────────────────────

    def commit_settings(self, path: list, data, change: str) -> None:
        """Called when the user edits a parameter in the GUI."""
        if path == ['connection', 'speed']:
            self._sdk.set_speed(data)
```

---

## Migration examples

### 1 — Simple actuator (`DAQ_Move_base` → new-style)

**Before**

```python
class DAQ_Move_MyStage(DAQ_Move_base):
    params = [{'name': 'port', 'type': 'str', 'value': 'COM1'}]

    def ini_stage(self, controller=None):
        self.controller = controller or MySDK(self.settings['port'])
        return True, self.controller

    def move_abs(self, value):
        self.controller.move_absolute(value)

    def get_actuator_value(self):
        return self.controller.get_position()

    def stop_motion(self):
        self.controller.stop()

    def close(self):
        self.controller.disconnect()
```

**After**

```python
class MyStagePlugin:
    """Hardware class — declare this as hardware_class on any wrapper."""

    def open(self, settings) -> None:
        self._sdk = MySDK(settings['port'])
        self._sdk.connect()

    def close(self) -> None:
        self._sdk.disconnect()

    def query_data(self, names=None, fresh=True):
        pos = self._sdk.get_position()
        return DataToExport('MyStage', data=[DataRaw('axis_x', data=[np.array([pos])])])

    def change_to(self, name, value) -> None:
        self._sdk.move_absolute(value)
        self._sdk.wait_for_idle()

    @property
    def capabilities(self):
        return Capabilities(variables=[
            ContinuousVariable('axis_x', lo=-100.0, hi=100.0, epsilon=0.001)
        ])
```

---

### 2 — Simple detector (`DAQ_Viewer_base` → new-style)

**Before**

```python
class DAQ_0DViewer_MyThermometer(DAQ_Viewer_base):
    params = [{'name': 'address', 'type': 'int', 'value': 1}]

    def ini_detector(self, controller=None):
        self.controller = controller or MyThermometerSDK(self.settings['address'])
        return True, self.controller

    def grab_data(self, Naverage=1, **kwargs):
        temp = self.controller.read_temperature()
        self.dte_signal.emit(
            DataToExport('Thermometer', data=[DataRaw('temperature', data=[np.array([temp])])])
        )

    def close(self):
        self.controller.close()
```

**After**

```python
class MyThermometerPlugin:

    def open(self, settings) -> None:
        self._sdk = MyThermometerSDK(settings['address'])

    def close(self) -> None:
        self._sdk.close()

    def query_data(self, names=None, fresh=True):
        temp = self._sdk.read_temperature()
        return DataToExport('Thermometer', data=[DataRaw('temperature', data=[np.array([temp])])])

    def change_to(self, name, value) -> None:
        pass  # read-only device

    @property
    def capabilities(self):
        return Capabilities(observables=[Observable('temperature')])
```

---

### 3 — Split hardware: one device, two legacy plugin classes

**The legacy pattern** — one physical stage exposed as both a mover and a
temperature reader:

```
DAQ_Move_MyStage      (master: opens hardware, owns SDK)
DAQ_0DViewer_MyStage  (slave: receives SDK reference via controller=)
```

**After migration** — one unified plugin, two GUI subscribers auto-created
from `Capabilities`:

```python
class MyStagePlugin:

    def open(self, settings) -> None:
        self._sdk = MySDK(settings['port'])
        self._sdk.connect()

    def close(self) -> None:
        self._sdk.disconnect()

    def query_data(self, names=None, fresh=True):
        pos  = self._sdk.get_position()
        temp = self._sdk.get_temperature()
        return DataToExport('MyStage', data=[
            DataRaw('axis_x',     data=[np.array([pos])]),
            DataRaw('temperature', data=[np.array([temp])]),
        ])

    def change_to(self, name, value) -> None:
        if name == 'axis_x':
            self._sdk.move_absolute(value)
            self._sdk.wait_for_idle()

    @property
    def capabilities(self):
        return Capabilities(
            variables=[ContinuousVariable('axis_x', lo=-100.0, hi=100.0, epsilon=0.001)],
            observables=[Observable('temperature')],
        )
```

The dashboard sees `Capabilities` and auto-creates:
- one `DAQ_Move` subscribed to channel `'axis_x'`
- one `DAQ_Viewer` subscribed to channel `'temperature'`

Both share the single `ControllerThread` that owns `MyStagePlugin`.

---

## Plugin registration

Register the hardware plugin class (not the DAQ wrapper) as a
`pymodaq.hardware` entry point:

```toml
# pyproject.toml of your plugin package
[project.entry-points."pymodaq.hardware"]
MyStage = "my_package.my_stage:MyStagePlugin"
```

The dashboard discovers it via `importlib.metadata.entry_points()` and creates
a `ControllerThread` directly from the hardware class.

---

## Compatibility timeline

| Phase | Status | Notes |
|---|---|---|
| Legacy `DAQ_Move_base` / `DAQ_Viewer_base` | **Working** | Unchanged; master/slave still functions |
| `hardware_class` declaration on legacy plugins | Optional | Prepares key for future registry lookup |
| New-style plugin interface | **Available now** | `open` / `close` / `query_data` / `change_to` / `capabilities` |
| Legacy master/slave removal | **Phase 5** | One release deprecation cycle; migration tool provided |

You do not need to migrate immediately.  Legacy plugins continue to work
unchanged until Phase 5.
