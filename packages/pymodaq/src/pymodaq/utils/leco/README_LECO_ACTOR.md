# LECO Actor/Director — Quick-Start Guide

This guide covers the **new actor API** (`use_legacy_actor = False`).
For the legacy API (default, `use_legacy_actor = True`) see the existing LECO documentation.

---

## Concepts in one sentence

| Component | Role |
|-----------|------|
| **Coordinator** | Central message router (one per network) |
| **Data Proxy** | Routes ZMQ PUB → SUB for data results |
| **Actor** | Owns and drives a hardware device; exposes RPC methods |
| **Director** | Lives inside a DAQ_Move / DAQ_Viewer; sends RPC to the actor |

---

## Understanding the two communication channels

The system uses **two completely separate transport mechanisms**. Confusing them is the
most common source of bugs.

```
CHANNEL 1 — LECO Control (RPC / request-response)
──────────────────────────────────────────────────
Director ──── TCP ──── Coordinator ──── TCP ──── Actor
           (request)                       (response / None)

• Bidirectional, one request → one response
• Used for: commands (change_to), queries (get_capabilities, query_data),
            settings updates (set_info)
• Blocking on the caller: the director waits until the actor replies
• The reply payload is always small JSON (None, dict, …) — never DataToExport
• Port: 12300 (coordinator default)


CHANNEL 2 — ZMQ Data (PUB/SUB / broadcast)
──────────────────────────────────────────────────
Actor ──── TCP ──── Proxy ──── TCP ──── Director(s)
        (publish)          (subscribe)

• One-way, one publisher → many subscribers
• Used for: DataToExport payloads (positions, detector frames, …)
• Non-blocking on the publisher: the actor does not wait for subscribers
• Received asynchronously in a background thread → Qt signal → GUI update
• Port actor → proxy:      11100 (PROXY_RECEIVING_PORT)
  Port proxy → subscriber: 11099 (PROXY_SENDING_PORT)
```

### The golden rule

> **Commands and queries go over RPC.  Data comes back over ZMQ.**

When a director calls `query_data()` or `change_to()`, the RPC reply is a **hex
conversation ID** (32-char string). The actual `DataToExport` payload arrives
asynchronously on the ZMQ channel, carrying the same ID in the frame header.

### Correlating an RPC call to its ZMQ frame

```python
# Director side (inside get_actuator_value or grab_data):
cid = controller.query_data(fresh=True)   # RPC → returns hex CID, e.g. '019c...'

# When the ZMQ frame arrives via _on_actor_data:
def _on_actor_data(self, cmd):
    cid  = cmd.attribute['cid']   # same hex string
    dte  = cmd.attribute['dte']   # the DataToExport
    # If cid matches the one returned by your last query_data call, this is your frame.
```

This is the foundation for a future synchronous `wait_for_frame(cid, timeout)` helper
that would let `get_actuator_value` block until *its specific* ZMQ reply arrives,
eliminating the one-cycle latency entirely.

### Proxy scalability and multiple proxies

One proxy handles typical lab loads easily. The bottleneck is:
**N subscribers × frame size × frame rate** of total forwarded data.

| Setup | Load | OK? |
|---|---|---|
| 5 directors × 1 KB position @ 10 Hz | 50 KB/s total | trivially fine |
| 5 directors × 2 MB camera frame @ 10 Hz | 100 MB/s total | fine on GbE |
| 20 directors × 10 MB hyperspectral @ 50 Hz | 10 GB/s | proxy is the wall |

**Solution — use a second proxy for high-bandwidth actors:**

Each proxy runs on its own port pair. Point heavy actors at the second proxy:

```bash
# Proxy 1 (default, for control/position actors)
python -m pyleco.coordinators.proxy_server
# → listens on 11100 (publishers) / 11099 (subscribers)

# Proxy 2 (for heavy camera data)
python -m pyleco.coordinators.proxy_server --port 11102
# → listens on 11102 (publishers) / 11101 (subscribers)
```

Then start the camera actor pointing at proxy 2:

```python
actor = PymodaqActor('cam', MyCameraDevice, port=11102)   # publishes to proxy 2
```

And the camera director subscribes from proxy 2:

```python
# In DAQ_xDViewer_LECODirector settings:
# Coordinator Host: localhost   (unchanged)
# Data Port: 11101              (proxy 2 subscriber port)
```

> **Note:** `data_port` is not yet exposed in the `leco_parameters` settings tree —
> it is currently hardcoded to `PROXY_SENDING_PORT` (11099).  Adding it as a setting
> is a straightforward extension when needed.

### Why two channels?

| | RPC | ZMQ PUB/SUB |
|---|---|---|
| Direction | bidirectional | one-way |
| Latency | bounded (timeout enforced) | unbounded (fire-and-forget) |
| Receivers | exactly one | any number (broadcast) |
| Payload | small JSON | large binary (numpy arrays etc.) |
| Use case | control flow | streaming data |

A single RPC channel for data would force the director to poll the actor for every
frame, creating unnecessary load. The ZMQ channel lets the actor push data to all
interested parties simultaneously.

### How a move works end-to-end

```
GUI thread                Listener thread (ZMQ)     Actor process
──────────────            ─────────────────────     ─────────────
move_abs(5.0 mm)
 ↓
change_to('position', 5.0) ──RPC──────────────────► device.write('position', 5.0)
                                                     device.read()   ← auto-publish
                                                     send ZMQ PUB ──►
                           ◄─ None (RPC reply) ─────
                                    ◄── ZMQ frame ───
                                    deserialize DTE
                                    emit Qt signal ──►
                                                     _on_actor_data()
                                                     _current_value = DataActuator(5.0)
 ↓
get_actuator_value()       ──RPC──────────────────► device.read()
                                                     send ZMQ PUB ──►
                           ◄─ None ─────────────────
 return _current_value     ← already 5.0 from above
 → MOVE_DONE
```

`get_actuator_value` returns the **cached** `_current_value` — which was updated by the
ZMQ callback from the previous `change_to` auto-publish. This is why MOVE_DONE fires on
the first polling tick after a move.

---

## 1 — Prerequisites

Install dependencies (once):

```bash
pip install pyleco serializall
```

---

## 2 — Startup order (important)

Always start in this order:

```
1. coordinator
2. proxy_server          ← only needed with use_legacy_actor = False
3. actor script
4. PyMoDAQ dashboard
```

### 2a — Start the coordinator

```bash
python -m pyleco.coordinators.coordinator
```

Leave this terminal open.  The coordinator prints the node name it is
using (e.g. `localhost`).

### 2b — Start the data proxy  *(mandatory)*

```bash
python -m pyleco.coordinators.proxy_server
```

This forwards ZMQ PUB messages from the actor to the director's ZMQ SUB socket.
**Without it, position updates and data frames never reach the director**, even
on the same machine.  The actor will appear to accept commands (the hardware
moves) but the GUI will hang waiting for a MOVE_DONE / data signal that never
arrives.

### 2c — Start the actor

Create a small script (e.g. `run_stage_actor.py`):

```python
from pymodaq.utils.leco.actor import PymodaqActor
from pymodaq.examples.mock_plugins import MockStageDevice  # swap for real hardware

actor = PymodaqActor('stage', MockStageDevice)   # component name only — no dots!
actor.connect()
print("Actor ready — Ctrl+C to stop")
actor.listen()   # blocking; handles RPC until interrupted
```

Run it:

```bash
python run_stage_actor.py
```

> **Important — component name vs full address:**
>
> Pass only the **component name** (no dots) to `PymodaqActor`.
> The coordinator assigns the node prefix upon sign-in.
> If the coordinator's node is `localhost`, the actor's full address becomes
> `localhost.stage` — use that full address in the director's `Actor name` setting.
>
> The coordinator prints its node name on startup (look for `Node: ...`).
> If you want a specific node name start the coordinator with:
> ```bash
> python -m pyleco.coordinators.coordinator --node lab
> ```
> Then the actor's full address is `lab.stage`.

For a detector replace `MockStageDevice` with `MockCameraDevice` and change the component name:

```python
actor = PymodaqActor('cam', MockCameraDevice)
```

---

## 3 — Dashboard / plugin setup

Open the PyMoDAQ dashboard and load a preset that contains
`DAQ_Move_LECODirector` (actuator) or `DAQ_xDViewer_LECODirector` (detector).

In the plugin settings panel set:

| Parameter | Value |
|-----------|-------|
| `Actor name` | `localhost.stage` — full address: coordinator node + `.` + component name |
| `Coordinator Host` | `localhost` |
| `Coordinator Port` | `12300` (default) |
| `Use legacy actor` | **False** |

Click **Initialize**.  The director will:
1. Connect to the coordinator
2. Fetch capabilities from the actor (`get_capabilities`)
3. Subscribe to settings and data broadcasts

---

## 4 — What happens when you click Move / Grab

### Actuator (DAQ_Move_LECODirector)

```
move_abs(10.0 mm)
  → change_to('position', 10.0)   — LECO RPC to actor
  → actor: device.write('position', 10.0)
  → actor: device.read()          — triggered by query_data
  → actor: publish DataToExport   — ZMQ PUB via Data Proxy
  → director: _on_actor_data()    — ZMQ SUB callback
  → emit GET_ACTUATOR_VALUE       — updates displayed value
```

### Detector (DAQ_xDViewer_LECODirector)

**Snap** (single acquisition):

```
grab_data(live=False)
  → query_data(fresh=True)        — LECO RPC to actor
  → actor: device.read()
  → actor: publish DataToExport   — ZMQ PUB via Data Proxy
  → director: _on_actor_data()    — ZMQ SUB callback
  → dte_signal.emit(dte)          — updates viewer once
```

**Live** (continuous acquisition — ping-pong loop):

```
grab_data(live=True)
  → _live_mode = True
  → query_data(fresh=True) ──────────────────────────────► device.read()
                                                            publish ZMQ ──►
                            ◄── ZMQ frame ─────────────────
  _on_actor_data() → dte_signal.emit(dte)     ← viewer update
  → query_data(fresh=True) ──────────────────────────────► device.read()
                                                            publish ZMQ ──►
  ... (loop continues until stop() is called)

stop()
  → _live_mode = False            — next _on_actor_data call skips re-request
```

The loop provides natural backpressure: the next acquisition is only requested after the previous
`DataToExport` arrives, so the rate is bounded by `device.read()` latency.

---

## 5 — Stopping components

### Stop the actor script

Press **Ctrl+C** in the actor terminal.

### Stop the data proxy

Press **Ctrl+C** in the proxy terminal.

### Stop the coordinator

Press **Ctrl+C** in the coordinator terminal.

Alternatively send a shutdown RPC (e.g. from a Python shell):

```python
from pyleco.communicators.zmq_communicator import ZmqCommunicator

c = ZmqCommunicator('admin')
c.sign_in()
c.ask_rpc(receiver=b'COORDINATOR', method='shut_down')
c.sign_out()
```

> **Note:** `shut_down` terminates the coordinator process.
> All actors and directors connected to it will lose their connection.

---

## 6 — Headless smoke test (no coordinator, no Qt)

Runs entirely in-process with fake sockets — useful for CI or quick checks:

```bash
# Full actor + director round-trip demo
python packages/pymodaq/src/pymodaq/examples/leco_actor_mock.py

# Mock device self-test (stage + camera)
python packages/pymodaq/src/pymodaq/examples/mock_plugins.py
```

---

## 7 — Writing your own actor device

Any class that implements the following interface can be passed to `PymodaqActor`:

```python
from pymodaq.control_modules.capabilities import Capabilities, ContinuousVariable

class MyStage:
    # Optional but recommended — enables get_capabilities()
    capabilities = Capabilities(
        variables=[ContinuousVariable('position', units='mm', lo=-50.0, hi=50.0)]
    )

    def read(self, names=None):
        """Return current state as DataToExport."""
        from pymodaq_data.data import DataToExport, DataRaw
        import numpy as np
        return DataToExport('my_stage',
            data=[DataRaw('position', data=[np.array([self._pos])])])

    def write(self, name: str, value) -> None:
        """Write a variable value to hardware."""
        if name == 'position':
            self._pos = float(value)
            # ... send command to hardware ...
```

If `capabilities` is omitted, `PymodaqActor` will try to infer it from
`_controller_units`, `_axis_names`, and `_epsilons` attributes (legacy plugin style).

---

## 8 — Troubleshooting

| Symptom | Likely cause | Fix |
|---------|-------------|-----|
| `RecursionError: maximum recursion depth exceeded` | Coordinator not running **or** node name mismatch | Start coordinator first; check node name |
| Repeated `Updating heartbeat … not signed in` then `RecursionError` | Dot in actor component name, or coordinator not running | Pass only the component name (no dots) to `PymodaqActor`: `PymodaqActor('stage', ...)` |
| `ConnectionError: LECO coordinator not reachable` | Coordinator not running | Start coordinator first |
| Hardware moves but GUI hangs / position never updates | Proxy not running | Start `proxy_server` — it is always required |
| Director initialises but no data arrives | Proxy not running | Start `proxy_server` |
| `TimeoutError` on `get_capabilities` | Actor not connected / wrong name | Check actor name matches exactly |
| Director shows old value / never updates | ZMQ subscription failed | Check proxy is running; check actor name |
| `RECEIVER_UNKNOWN` in logs | Actor signed out or crashed | Restart actor script |
