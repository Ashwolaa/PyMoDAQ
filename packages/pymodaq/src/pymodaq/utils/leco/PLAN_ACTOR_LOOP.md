# Plan — Instruction-Queue Actor Architecture

## Motivation

The current `PymodaqActor` has three correctness problems:

1. **Thread safety**: `query_data` (RPC thread) and `_grab_loop` (background thread) both call
   `device.read()` concurrently without a lock.
2. **Stop-one-stops-all**: `stop_continuous()` removes the entire grab loop regardless of how many
   directors are subscribed.
3. **Late-join blindness**: a director that connects while the actor is already grabbing has no
   way to discover that state at `ini_detector` time.

The solution is to give the actor a **single hardware thread** that is the sole owner of the
device. All other threads (the pyleco listen loop, director RPC handlers) communicate with the
hardware thread exclusively through a thread-safe instruction queue.  No lock on
`device.read()` / `device.write()` is needed because only one thread ever calls them.

---

## Key conceptual distinctions

### Thread model

Two threads exist in the actor process:

| Thread | Owner | Responsibility |
|---|---|---|
| **Pyleco listen thread** | pyleco `Actor.listen()` | Receives RPC, enqueues instructions, returns `req_id` |
| **Hardware loop thread** | `PymodaqActor._hardware_loop()` | Sole caller of `device.read()` / `device.write()`, publishes ZMQ |

Communication between them is exclusively through `queue.Queue` (instruction queue) and a
`threading.Event` (wake signal).  No lock on hardware calls is needed because only one thread
ever touches the device.  This is not a mitigation — it is a structural guarantee.

The hardware loop thread is started in `connect()` and stopped (via the shared `_stop_event`)
in `disconnect()`.

### Acquisition rate vs refresh rate

| Concept | Owner | Meaning | UI element |
|---|---|---|---|
| **Acquisition rate** | Actor, global per observable | How often `device.read()` is called | `ActorGrabStatusWidget` (read-only, mirrored from `on_acquisition_status`) |
| **Refresh rate** | Director, per director | How often this director's display updates | `max_rate_hz` parameter (already exists) |

These must be visually distinct in the UI.  A user changing the acquisition rate affects all
connected directors; changing the refresh rate affects only their own display.

The acquisition rate is shared state: any director that changes it via `query_data(period=...)`
changes it for everyone.  The refresh rate is purely local: a director that wants to display at
1 Hz while the actor acquires at 10 Hz calls `query_data(count=1, fresh=False)` from its own
Qt timer at 1 Hz.  The actor publishes `_last_data` immediately without touching hardware.

### Subscription (ZMQ) vs acquisition control (RPC)

| Concept | Mechanism | What it means |
|---|---|---|
| **ZMQ subscription** | `listener.subscribe(topic)` | "I will receive frames published for this channel" |
| **Acquisition control** | `query_data` / `stop` RPC | "Start / stop the actor reading this observable" |

These are independent.  A spectator subscribes to ZMQ without ever sending an RPC.  A director
that only wants cached values calls `query_data(fresh=False)` without a persistent ZMQ
subscription.

### `fresh` flag

| Call | Effect |
|---|---|
| `query_data(names, count, fresh=True)` | Enqueue a `ReadRequest`; data arrives later on ZMQ |
| `query_data(names, count=1, fresh=False)` | Publish `_last_data` immediately from RPC handler; no hardware access, no queue |

`fresh=False` is answered synchronously in the RPC handler thread — the cid is returned and
the ZMQ frame is published before the RPC response even leaves the actor.  It is safe because
only the hardware thread writes `_last_data`, and the read here is a plain Python attribute
access (GIL-protected for the object reference).  If strict consistency is needed a
`threading.Lock` around `_last_data` can be added, but in practice the window is negligible.

### Stop semantics

`stop(names)` removes the named observables from the actor's `_read_list` **globally**.
Any director that was relying on those observables will stop receiving frames.  This is
intentional: the actor is a shared resource; its acquisition state is shared.  The Network
Manager GUI (PLAN_LECO_MANAGER.md) makes the current acquisition state visible to all
operators so accidental stops are immediately apparent.

---

## New data structures

```python
from __future__ import annotations
import math
from dataclasses import dataclass, field
from typing import Any, Optional

@dataclass
class ReadRequest:
    names: Optional[list[str]]  # None = all observables
    count: float                # 1 = snap; math.inf = continuous; N = N reads then stop
    period: float               # seconds between reads; 0 = as fast as hardware allows
    requester: str              # director full LECO name, e.g. "localhost.det_dir_1"
    req_id: bytes               # pre-generated conversation_id; used as ZMQ cid

@dataclass
class WriteInstruction:
    name: str | dict            # str + value = single write; dict = multi-write
    value: Any                  # ignored when name is a dict
    requester: str
    req_id: bytes               # used to correlate the auto-read-back ZMQ frame

@dataclass
class StopInstruction:
    names: Optional[list[str]]  # None = stop all
    requester: str
```

### `count` values

Only two values are supported in the initial implementation:

| Value | Meaning |
|---|---|
| `1` | Snap: one hardware read, then remove from `_read_list` |
| `math.inf` | Continuous: read indefinitely until `StopInstruction` |

N > 1 (e.g., for fast hardware averaging) is a documented future extension point.

### `_read_list` design

```python
# Maps a frozenset of names (or None sentinel) to the active ReadRequest.
# None key means "all observables".
_read_list: dict[frozenset | None, ReadRequest]
_last_read_time: dict[frozenset | None, float]  # monotonic timestamps
```

**Merge strategy when two directors request the same observable group:**
- `period`: take `min(existing, new)` — satisfy the fastest requester; slow directors
  drop excess frames client-side via their `_accepting_data` gate.
- `count`: `math.inf` wins over `1`.
- `req_id`: use the incoming request's id (most recent requester's correlation wins).

---

## Hardware loop

```
Hardware thread (sole owner of device):

while not _stop_event.is_set():
    # 1. Drain instruction queue (non-blocking)
    _process_pending_instructions()

    # 2. Execute all pending writes first
    for name, value in _write_pending.items():
        device.write(name, value)
        _schedule_readback(name)       # add one-shot ReadRequest if not already continuous
    _write_pending.clear()

    # 3. Execute reads that are due
    now = time.monotonic()
    for key, req in list(_read_list.items()):
        if now - _last_read_time.get(key, 0) >= req.period:
            try:
                dte = device.read(req.names)
            except Exception:
                _report_error(req.requester, req.req_id)
                continue
            if dte is not None:
                _last_data = dte
                _publish(dte, cid=req.req_id)
            _last_read_time[key] = now
            req.count -= 1
            if req.count <= 0:
                del _read_list[key]
                del _last_read_time[key]

    # 4. Broadcast status if read_list changed this tick
    _broadcast_acquisition_status_if_changed()

    # 5. Sleep until next read is due (interruptible by new instructions)
    sleep_time = _time_until_next_due()
    try:
        _instruction_queue.get(timeout=sleep_time)   # wakes on new instruction
        # put it back — actual draining happens in step 1 next iteration
        _instruction_queue.put_nowait(...)            # see implementation note below
    except queue.Empty:
        pass
```

**Implementation note on step 5**: use `queue.Queue.get(timeout=...)` as the sleep mechanism.
Because `get()` consumes the item, use a two-deque design: a `collections.deque` for the
pending batch and a `threading.Event` as the wake signal.  Alternatively use
`queue.Queue` and drain it entirely in step 1 with `get_nowait()` in a loop — the first
blocked `get(timeout=...)` in step 5 then serves purely as the timer.

Simpler alternative that avoids the double-get issue:

```python
# End of loop body
sleep_time = max(0.0, _time_until_next_due())
_new_instruction_event.wait(timeout=sleep_time)
_new_instruction_event.clear()
```

Where `_new_instruction_event = threading.Event()` is set by RPC handlers whenever they
enqueue an instruction.  This is clean and avoids any queue item duplication.

---

## `_publish` and `req_id`

`req_id` is generated at instruction-enqueue time (in the RPC handler) via
`generate_conversation_id()`.  The RPC handler returns `req_id.hex()` to the director
immediately — before the hardware read happens.  The hardware thread uses the same `req_id`
as the ZMQ `conversation_id` when it publishes.

```
Director              RPC handler (listen thread)     Hardware thread
   |---query_data(fresh=True)-->|                          |
   |                            | enqueue ReadRequest      |
   |                            | with req_id=X            |
   |<---returns req_id=X--------|                          |
   |                            |         device.read()  --|
   |                            |         publish(cid=X) --|
   |<---ZMQ frame (cid=X)-------|--------------------------|
```

The director already knows `X` before the frame arrives and can correlate them.

For `fresh=False`:
```
Director              RPC handler (listen thread)
   |---query_data(fresh=False)-->|
   |                             | publish(_last_data, cid=X)
   |<---returns req_id=X---------|
   |<---ZMQ frame (cid=X)--------|   (arrives almost simultaneously)
```

No hardware thread involvement; sub-millisecond round-trip.

---

## RPC API changes

### `actor.py` — new / changed methods

| Old method | New method | Change |
|---|---|---|
| `query_data(names, fresh)` | `query_data(names, count, fresh, period)` | `count` and `period` added; enqueues when `fresh=True`; publishes cached when `fresh=False` |
| `query_data_continuous(rate_hz)` | **deprecated** → alias for `query_data(count=inf, period=1/rate_hz)` | kept for one release cycle |
| `stop_continuous()` | `stop(names)` | global stop of named observables; `names=None` stops all |
| `change_to(name, value)` | unchanged signature | now enqueues `WriteInstruction` instead of calling device directly |
| `set_info(path, value)` | unchanged signature | enqueues a settings write (see open question §1) |
| `get_grabbed_names()` | `get_read_list()` | returns full `_read_list` state: names, count, period, requester |
| `set_published_names()` | **removed** | superseded by `_read_list`; no longer needed |
| `get_published_names()` | **removed** | idem |
| *(new)* | `get_acquisition_status()` | returns current `_read_list` + `_write_pending`; used by directors at `ini_*` time |

### `rpc_method_definitions.py` additions

```python
class PymodaqActorMethods(StrEnum):
    ...  # existing entries unchanged
    STOP                  = "stop"
    GET_READ_LIST         = "get_read_list"
    GET_ACQUISITION_STATUS = "get_acquisition_status"
    # deprecated (kept as aliases):
    QUERY_DATA_CONTINUOUS = "query_data_continuous"
    STOP_CONTINUOUS       = "stop_continuous"
    GET_GRABBED_NAMES     = "get_grabbed_names"
    SET_PUBLISHED_NAMES   = "set_published_names"
    GET_PUBLISHED_NAMES   = "get_published_names"
```

### `director_utils.py` additions

```python
class PymodaqDirector(GenericDirector):
    def query_data(self, names=None, count=1, fresh=True, period=0.0) -> Optional[str]: ...
    def stop(self, names=None) -> None: ...
    def get_acquisition_status(self) -> dict: ...
    def get_read_list(self) -> dict: ...
    # deprecated aliases:
    def query_data_continuous(self, rate_hz=0): ...  # → query_data(count=inf, period=...)
    def stop_continuous(self): ...                   # → stop(names=None)
```

---

## `on_acquisition_status` broadcast (replaces `on_grab_status`)

Broadcast payload (richer than current `on_grab_status`):

```python
{
  "read_list": {
      "frame":    {"count": math.inf, "period": 0.1, "requester": "localhost.det_dir_1"},
      "position": {"count": math.inf, "period": 0.05, "requester": "localhost.move_dir_1"},
  },
  "is_grabbing": True,   # True if read_list is non-empty
}
```

Directors register `on_acquisition_status` as an RPC handler (replaces `on_grab_status`).
The actor broadcasts on every tick where the `_read_list` changed.

Directors use the payload to:
- Update the `ActorGrabStatusWidget` (same state on every connected director).
- Pre-open `_accepting_data` at `ini_*` time if the actor is already acquiring the
  director's channel.

---

## Director-side changes

### `ini_detector` / `ini_stage`

```python
# After subscribing to ZMQ:
acq = self.controller.get_acquisition_status()
channel = self.settings['observable_name'] or 'data'
if channel in (acq.get('read_list') or {}) or acq.get('read_list') == {}:
    # Actor is already acquiring this channel — open gate immediately.
    self._accepting_data = True
    self._live_grab = True
```

### `grab_data(live=True)`  — viewer director

```python
if live:
    rate_hz = self.settings['max_rate_hz']
    period = 1.0 / rate_hz if rate_hz > 0 else 0.0
    self.controller.query_data(
        names=[obs_name] if obs_name else None,
        count=math.inf,
        fresh=True,
        period=period,
    )
else:
    # Snap: one fresh read.
    self.controller.query_data(names=[obs_name] if obs_name else None, count=1, fresh=True)
```

`_live_sequential` mode is removed.  It was only needed to pace the actor; with the
instruction-queue loop the actor paces itself via `period`.  Sequential behaviour (one frame
at a time driven by the director) can be approximated by a low `max_rate_hz`.

### `stop()` — viewer director

```python
self._accepting_data = False
self._live_grab = False
obs_name = self.settings['observable_name'] or None
self.controller.stop(names=[obs_name] if obs_name else None)
```

### `grab_data` / `close` — move director

The move director subscribes at `ini_stage` and keeps the subscription alive for the
lifetime of the plugin.  Position updates arrive continuously via ZMQ; no explicit
`grab_data` / `stop` cycle is needed for position readback.

```python
# ini_stage: subscribe with low-rate continuous read for position monitoring
self.controller.query_data(names=[var_name], count=math.inf, fresh=True, period=0.05)
# close: stop position readback
self.controller.stop(names=[var_name])
```

`get_actuator_value()` becomes a `fresh=False` query (returns cached position, no hardware
touch):

```python
def get_actuator_value(self):
    try:
        self.controller.query_data(names=[var_name], count=1, fresh=False)
    except Exception:
        pass
    return self._current_value
```

### `_accepting_data` gate — simplification

The gate logic simplifies to:

| State | Gate |
|---|---|
| Snap in flight (`count=1, fresh=True`) | Open; close after first ZMQ frame received |
| Continuous grab active | Open; stays open until `stop()` |
| `on_acquisition_status(is_grabbing=True)` received for our channel | Open |
| `on_acquisition_status(is_grabbing=False)` for our channel | Close |
| `ini_*`: actor already grabbing our channel | Pre-open |
| Idle | Closed |

The move director has no gate — position ZMQ frames are always welcome.

---

## `ActorGrabStatusWidget`

A compact read-only widget shown in every director's settings panel:

```
┌─ Actor acquisition state ─────────────────────────────┐
│  ● GRABBING                                           │
│  frame     @ 10 Hz  ← det_dir_1                      │
│  position  @ 20 Hz  ← move_dir_1                     │
└───────────────────────────────────────────────────────┘
```

Implementation: a `QGroupBox` with a `QFormLayout` of `QLabel` rows.  Updated by
`on_acquisition_status` RPC callback.  All directors connected to the same actor show
identical content because they all receive the same broadcast.

Widget file: `packages/pymodaq/src/pymodaq/utils/leco/actor_grab_status_widget.py`

---

## `change_to` and auto-read-back

After writing, the hardware loop should publish the updated value so all subscribed
directors see the change.  Strategy:

1. Hardware loop writes the variable.
2. Checks `_read_list`: if the written channel already has a `count=inf` entry, no action
   needed — the next loop iteration will read it naturally (within at most one period).
3. If the written channel is NOT in `_read_list` (e.g., a write-only setpoint), add a
   one-shot `ReadRequest(names=written_names, count=1, period=0)` so at least one frame
   is published.

This avoids double-reads when continuous acquisition is already running.

`change_to` RPC handler enqueues a `WriteInstruction` and returns `req_id.hex()`.  The
director can optionally wait for the ZMQ read-back frame using this id.

---

## Move-done detection

Move-done is already handled correctly by the existing `DAQ_Move_Hardware` / `DAQ_Move_base`
machinery — no changes to that layer are needed.

The existing call chain (from `daq_move.py`) is:

```
DAQ_Move.move_abs()
  → command_hardware.emit(MOVE_ABS)
    → DAQ_Move_Hardware.queue_command()
      → DAQ_Move_Hardware.move_abs(position)
          self.hardware.move_abs(position)   ← plugin's move_abs → calls change_to via RPC
          self.hardware.poll_moving()        ← started by DAQ_Move_Hardware, not the plugin
```

`poll_moving()` (in `DAQ_Move_base`) uses a QTimer that periodically calls
`check_move_done()`.  `check_move_done()` calls `get_actuator_value()` and compares the
returned value against the target within `_epsilon`.  When within epsilon it emits
`move_done_signal`.

For `DAQ_Move_LECODirector`, with the continuous position subscription active at `ini_stage`
time, `_current_value` is always kept up-to-date by ZMQ frames arriving on `_on_actor_data`.
Therefore `get_actuator_value()` should use `fresh=False` (return the cached value, which IS
fresh because the actor loop is continuously reading):

```python
def get_actuator_value(self):
    # _current_value is kept current by the continuous ZMQ stream.
    # A fresh=False query triggers a cached-value publish — fast, no RPC to hardware.
    try:
        self.controller.query_data(names=[var_name], count=1, fresh=False)
    except Exception:
        pass
    return self._current_value
```

**One addition**: set `_epsilon` from `ContinuousVariable.epsilon` in `Capabilities` at
`ini_stage` time so that move-done detection uses the instrument's native tolerance rather
than the hard-coded default of 1:

```python
var_caps = next((v for v in caps.variables if v.name == var_name), None)
if var_caps is not None and hasattr(var_caps, 'epsilon') and var_caps.epsilon > 0:
    self._epsilon = var_caps.epsilon
```

No actor-side knowledge of targets or epsilon is required.

---

## PyLECO components used

| Component | Role in new architecture |
|---|---|
| `queue.Queue` (stdlib) | Thread-safe instruction handoff: listen thread → hardware thread |
| `threading.Event` (`_new_instruction_event`) | Wake signal to replace `time.sleep()` in hardware loop |
| `threading.Event` (`_stop_event`) | Shared stop signal for both listen loop and hardware loop |
| `Actor.get_communicator()` | Hardware thread uses it to send `on_acquisition_status` RPCs to directors |
| `generate_conversation_id()` | Called at enqueue time; `req_id` travels with the instruction |
| `Actor.start_timer()` / `stop_timer()` | `stop_timer()` called in `connect()` — periodic timer is replaced entirely by the hardware loop |
| `DataPublisher` | Unchanged — hardware thread calls `_publish(dte)` as before |
| `Actor.listen()` | Runs the RPC dispatch loop in its own thread (unchanged) |

---

## Error propagation

When `device.read()` raises in the hardware loop:

```python
except Exception as exc:
    logger.exception("hardware loop: device.read() failed for %s", req.names)
    try:
        communicator = self.get_communicator()
        communicator.ask_rpc(
            receiver=req.requester,
            method='on_hardware_error',
            req_id=req.req_id.hex(),
            message=str(exc),
        )
    except Exception:
        pass
    # Remove the failing entry to avoid an infinite error loop.
    del _read_list[key]
```

Directors register `on_hardware_error` as an RPC handler and emit a status warning to
the GUI.

---

## Things we may have missed / open questions

### 1. `set_info` ordering — confirmed: through the queue

`set_info(path, value)` modifies a device setting (e.g., integration time).  It goes
through the instruction queue as a `WriteInstruction` with a `('settings', path)` sentinel
so that the change is guaranteed to be applied before the next `device.read()`.  A settings
change racing with a hardware read would produce one stale frame; routing through the queue
eliminates this.

### 2. `read_list` key for `names=None`

`names=None` means "read all observables".  The `frozenset` key cannot represent `None`.

**Recommendation**: use `None` itself as the key for the "all channels" entry.  The loop
checks `None` first; per-channel entries are checked afterward.  If both exist, the
`None` entry takes precedence for the tick where it fires (it reads everything anyway).

### 3. `count=N` semantics for N > 1

**Decision**: initial implementation supports only `count=1` and `count=math.inf`.
N > 1 is a documented future extension point (fast hardware averaging, burst acquisition).
Accumulating frames for averaging is a director-side concern for now.

### 4. Rate conflict resolution — confirmed: min period

If two directors request the same channel at different rates, use `min(period)` so the
fastest requester is satisfied.  Slow directors handle excess frames via their
`_accepting_data` gate or by using `fresh=False` polling at their own rate instead of a
persistent ZMQ subscription.

### 5. `periodic_reading` parameter — deprecated

The `periodic_reading` constructor parameter is superseded by `query_data(count=inf,
period=...)` instructions.  It should be deprecated and removed.  `stop_timer()` is
called unconditionally in `connect()`.

### 6. `use_legacy_actor` flag

The flag remains.  The entire new architecture is active only when `use_legacy_actor=False`.
Legacy path is unchanged.

### 7. Director name stability

The current `leco_director.py:69` uses `random.randrange` for director names.  The
`req.requester` field in instructions carries the full LECO name.  If a director
disconnects and reconnects with a different random name, the `_director_registry` entry
from the old name becomes stale.  The Network Manager plan (PLAN_LECO_MANAGER.md) already
proposes a UUID-based stable name — this should be implemented together with the hardware
loop plan.

### 8. Watchdog for hung `device.read()`

If `device.read()` blocks indefinitely (hardware crash, cable disconnect), the hardware
loop hangs and no new instructions are processed.  A watchdog thread that monitors
elapsed time since the last loop tick and logs/alerts after a configurable timeout is
recommended.  This is a quality-of-life addition, not a correctness requirement for the
initial implementation.

---

## Implementation phases with per-phase tests

Tests are written alongside the phase they verify.  All actor tests are headless
(no Qt required); director tests that instantiate the listener require Qt and use the
existing `pytestmark_qt` skip pattern from `conftest.py`.

---

### Phase 0 — Data structures
**Files**: `actor.py` (add dataclasses at top), `rpc_method_definitions.py`
No behavioral change.  Purely additive.

**Tests** (`test_pymodaq_actor.py` — new `TestInstructions` class):
- `test_read_request_fields`: construct `ReadRequest`; assert all fields accessible.
- `test_write_instruction_dict_form`: construct `WriteInstruction(name={'a': 1, 'b': 2})`; assert `name` is dict.
- `test_read_list_merge_min_period`: create two `ReadRequest`s for the same names key with different periods; apply merge logic; assert result period = min of both.
- `test_read_list_merge_inf_wins_over_1`: merge `count=1` with `count=inf`; assert result is `inf`.
- `test_names_none_key`: `ReadRequest(names=None, ...)` stored under `None` key; distinct from `frozenset({'frame'})` key.
- `test_rpc_enum_new_entries`: assert `PymodaqActorMethods.STOP`, `GET_READ_LIST`, `GET_ACQUISITION_STATUS` exist.

---

### Phase 1 — Hardware loop thread
**Files**: `actor.py`
Replace `_grab_loop` + pyleco timer with `_hardware_loop()`.  `stop_timer()` called in
`connect()`.  Add `_instruction_queue: queue.Queue`, `_new_instruction_event: threading.Event`.

**Tests** (`test_pymodaq_actor.py` — new `TestHardwareLoop` class, headless):
- `test_hardware_loop_thread_starts_on_connect`: after `connect()`, `_hw_thread.is_alive()` is True.
- `test_hardware_loop_thread_stops_on_disconnect`: after `disconnect()`, thread exits within 2 s.
- `test_loop_executes_read_request_and_publishes`: inject `ReadRequest(names=['x'], count=1, period=0)` into queue; set event; allow one tick; assert mock `device.read(['x'])` called once and `_publish` called.
- `test_loop_count_decrements_to_zero_removes_entry`: `count=1`; after one tick assert key removed from `_read_list`.
- `test_loop_count_inf_persists`: `count=inf`; after 3 ticks assert key still in `_read_list`.
- `test_loop_writes_before_reads_in_same_tick`: enqueue `WriteInstruction` + `ReadRequest` simultaneously; assert `device.write()` call index < `device.read()` call index (use `unittest.mock.call_args_list`).
- `test_loop_period_respected`: `period=0.05`; inject two wake events 0.02 s apart; assert `device.read()` called only once.
- `test_loop_set_info_write_before_next_read`: inject settings `WriteInstruction` then `ReadRequest`; assert `device.set_info()` called before `device.read()`.
- `test_new_instruction_event_wakes_sleeping_loop`: loop sleeping with long period; enqueue instruction + set event; assert loop processes it within 0.1 s.
- `test_stop_timer_called_on_connect`: mock `stop_timer`; call `connect()`; assert `stop_timer` was called.

---

### Phase 2 — RPC handler rewiring
**Files**: `actor.py`
`query_data(fresh=True)` enqueues `ReadRequest` and returns `req_id`.
`query_data(fresh=False)` publishes `_last_data` synchronously.
`change_to` enqueues `WriteInstruction`.
`stop(names)` enqueues `StopInstruction`.
`get_acquisition_status()` / `get_read_list()` return current state.
`on_acquisition_status` broadcast sent on every tick where `_read_list` changed.

**Tests** (`test_pymodaq_actor.py` — new `TestRPCRewiring` class):
- `test_query_data_fresh_true_enqueues_and_returns_req_id`: call RPC; assert `queue.qsize() == 1`; assert return value is a hex string matching the enqueued `req_id`.
- `test_query_data_fresh_false_publishes_immediately_no_queue`: set `_last_data`; call `query_data(fresh=False)`; assert `_publish` called; assert `queue.empty()`.
- `test_query_data_fresh_false_returns_none_when_no_cached_data`: `_last_data = None`; assert return is `None`.
- `test_change_to_str_enqueues_write_instruction`: `change_to('pos', 5.0)`; assert `WriteInstruction` in queue with correct name/value.
- `test_change_to_dict_enqueues_write_instruction`: `change_to({'a': 1, 'b': 2})`; assert single `WriteInstruction` with dict name.
- `test_stop_named_enqueues_stop_instruction`: `stop(['frame'])`; assert `StopInstruction(names=['frame'])` in queue.
- `test_stop_all_enqueues_stop_none`: `stop(names=None)`; assert `StopInstruction(names=None)` in queue.
- `test_get_acquisition_status_returns_read_list_snapshot`: populate `_read_list`; call `get_acquisition_status()`; assert returned dict matches.
- `test_on_acquisition_status_broadcast_when_read_list_changes`: register director; add entry to `_read_list`; run one tick; assert `on_acquisition_status` RPC sent with correct payload.
- `test_on_acquisition_status_not_broadcast_when_unchanged`: run two ticks with same `_read_list`; assert broadcast called only once (on first tick after change).
- `test_req_id_preserved_as_zmq_conversation_id`: inject `ReadRequest(req_id=X)`; run tick; assert `_publish` called with `cid=X`.

---

### Phase 3 — Director utils
**Files**: `director_utils.py`, `rpc_method_definitions.py`
Add `query_data(names, count, fresh, period)`, `stop()`, `get_acquisition_status()`,
`get_read_list()` to `PymodaqDirector`.  Keep deprecated aliases.

**Tests** (`test_pymodaq_directors.py` — extend existing class, headless):
- `test_query_data_new_signature_passes_count_and_period`: mock `ask_rpc`; call `query_data(names=['x'], count=math.inf, fresh=True, period=0.1)`; assert RPC called with all four params.
- `test_query_data_fresh_false_passes_fresh_param`: call `query_data(fresh=False)`; assert `ask_rpc` called with `fresh=False`.
- `test_stop_sends_stop_rpc`: `stop(['frame'])`; assert `ask_rpc(STOP, names=['frame'])`.
- `test_stop_all_sends_none`: `stop()`; assert `ask_rpc(STOP, names=None)`.
- `test_get_acquisition_status_calls_rpc`: `get_acquisition_status()`; assert `ask_rpc(GET_ACQUISITION_STATUS)`.
- `test_deprecated_query_data_continuous_maps_to_query_data`: call `query_data_continuous(rate_hz=10)`; assert internally calls `query_data(count=inf, period=0.1)`.
- `test_deprecated_stop_continuous_maps_to_stop`: call `stop_continuous()`; assert internally calls `stop(names=None)`.

---

### Phase 4 — Viewer director
**Files**: `daq_xDviewer_LECODirector.py`
Use new API in `grab_data` and `stop`.  Remove `_live_sequential`.
Add `on_acquisition_status` RPC handler.  Pre-open gate in `ini_detector`.

**Tests** (`test_daq_xDviewer_LECODirector.py`):
- `test_grab_live_continuous_calls_query_data_inf`: `grab_data(live=True)` in continuous mode → assert `controller.query_data(count=inf, period=1/rate_hz)`.
- `test_grab_snap_calls_query_data_count_1`: `grab_data(live=False)` → assert `controller.query_data(count=1, fresh=True)`.
- `test_stop_calls_controller_stop_with_obs_name`: `stop()` → assert `controller.stop(names=[obs_name])`.
- `test_stop_closes_gate`: `stop()` → assert `_accepting_data == False`.
- `test_ini_detector_pre_opens_gate_when_actor_already_grabbing`: mock `get_acquisition_status` returning `{'read_list': {'frame': {...}}}` for channel `'frame'`; after `ini_detector` assert `_accepting_data == True`.
- `test_ini_detector_gate_stays_closed_when_actor_idle`: mock `get_acquisition_status` returning empty `read_list`; assert `_accepting_data == False` after `ini_detector`.
- `test_on_acquisition_status_opens_gate_for_our_channel`: call `on_acquisition_status({'read_list': {'frame': {...}}, 'is_grabbing': True})`; assert `_accepting_data == True`.
- `test_on_acquisition_status_closes_gate_when_not_grabbing`: `is_grabbing=False`; assert `_accepting_data == False` and `_live_grab == False`.
- `test_on_actor_data_drops_frame_when_gate_closed`: `_accepting_data = False`; call `_on_actor_data`; assert `dte_signal` not emitted.
- `test_on_actor_data_closes_gate_after_snap`: `_accepting_data = True`, `_live_grab = False`; call `_on_actor_data`; assert `_accepting_data == False` after.
- `test_live_sequential_attribute_removed`: assert `not hasattr(director, '_live_sequential')`.
- `test_on_acquisition_status_registered_as_rpc`: assert `'on_acquisition_status'` in registered RPC method names; `'on_grab_status'` absent.

---

### Phase 5 — Move director
**Files**: `daq_move_LECODirector.py`
Continuous position subscription at `ini_stage`.  `get_actuator_value` uses `fresh=False`.
`_epsilon` set from capabilities.  `on_acquisition_status` handler.  `close` stops read.

**Tests** (`test_daq_move_LECODirector.py`):
- `test_ini_stage_subscribes_continuous_position`: mock controller; assert `query_data(names=[var_name], count=inf, fresh=True)` called during `ini_stage`.
- `test_ini_stage_sets_epsilon_from_capabilities`: mock caps with `ContinuousVariable(epsilon=0.01)`; after `ini_stage` assert `director._epsilon == 0.01`.
- `test_ini_stage_epsilon_unchanged_if_zero_in_caps`: `epsilon=0` in caps; assert `director._epsilon` keeps its default.
- `test_close_stops_position_read`: `close()` → assert `controller.stop(names=[var_name])`.
- `test_get_actuator_value_uses_fresh_false`: assert `controller.query_data(count=1, fresh=False)` called (not `fresh=True`).
- `test_get_actuator_value_returns_current_value`: set `_current_value`; call `get_actuator_value()`; assert return matches.
- `test_on_actor_data_updates_current_value`: inject DTE with position 42.0; assert `_current_value` updated.
- `test_on_actor_data_emits_get_actuator_value`: inject DTE; assert `GET_ACTUATOR_VALUE` ThreadCommand emitted.
- `test_on_acquisition_status_registered_as_rpc`: assert `'on_acquisition_status'` registered; `'on_grab_status'` absent.

---

### Phase 6 — GUI widget
**File**: `actor_grab_status_widget.py` (new)
`ActorGrabStatusWidget(QWidget)`.  Embedded in both director settings panels.

**Tests** (`test_actor_grab_status_widget.py` — Qt, skip headless):
- `test_widget_shows_idle_when_no_read_list`: construct widget; call `update({'read_list': {}, 'is_grabbing': False})`; assert label shows "IDLE".
- `test_widget_shows_grabbing_with_channel_list`: call `update({'read_list': {'frame': {'period': 0.1, 'requester': 'localhost.d1'}}, 'is_grabbing': True})`; assert "GRABBING" and "frame" visible.
- `test_widget_rate_displayed_as_hz`: period=0.1 → assert "10.0 Hz" displayed.
- `test_widget_updates_on_second_call`: first update idle, second update grabbing; assert label changed.
- `test_widget_clears_rows_on_idle`: after grabbing update, send idle update; assert channel rows removed.

---

### Phase 7 — Error propagation
**Files**: `actor.py`, `daq_xDviewer_LECODirector.py`, `daq_move_LECODirector.py`
`on_hardware_error` RPC callback.  Failing `_read_list` entry removed.

**Tests** (`test_pymodaq_actor.py` — extend `TestHardwareLoop`):
- `test_device_read_exception_removes_entry`: mock `device.read()` raising; run one tick; assert entry removed from `_read_list`.
- `test_device_read_exception_sends_error_rpc_to_requester`: mock communicator; assert `on_hardware_error` RPC sent to `req.requester` with `req_id` and message.
- `test_device_read_exception_does_not_crash_loop`: after exception tick, inject new `ReadRequest`; assert loop continues and processes it.
- `test_device_write_exception_removes_pending_write`: mock `device.write()` raising; assert `_write_pending` cleared for that entry.

**Tests** (directors — extend existing test classes):
- `test_on_hardware_error_emits_status_warning`: call `on_hardware_error(req_id='abc', message='timeout')`; assert `emit_status` called with warning ThreadCommand.
- `test_on_hardware_error_closes_accepting_gate` (viewer only): assert `_accepting_data == False` after error.

---

### Phase 8 — Cleanup
**Files**: `actor.py`, `director_utils.py`
Remove: `_grab_loop`, `_published_names`, `get_published_names`, `set_published_names`,
`query_data_continuous` (actor-side), `stop_continuous` (actor-side), `periodic_reading`
constructor param, `_live_sequential` (already removed in Phase 4).

**Tests** (regression — add to existing test classes):
- `test_grab_loop_attribute_removed`: assert `not hasattr(actor, '_grab_loop')`.
- `test_published_names_attribute_removed`: assert `not hasattr(actor, '_published_names')`.
- `test_periodic_reading_param_deprecated`: construct `PymodaqActor(periodic_reading=1.0)`; assert `DeprecationWarning` raised.
- `test_all_existing_tests_still_pass`: no new tests; confirm full suite green after cleanup.

---

### Deleted plan files

| File | Status | Reason |
|---|---|---|
| `PLAN_B_SUBTOPICS.md` | **Delete** | Fully absorbed: per-DWA sub-topics, `change_to` scope, `_accepting_data` gate, `_on_actor_data` simplification are all covered above |
| `PLAN_LECO_MANAGER.md` | **Keep** | Independent topic (Network Manager GUI); not covered here |
| `discussion.md` | Optional | Conceptual background; useful as reference but not a plan |
