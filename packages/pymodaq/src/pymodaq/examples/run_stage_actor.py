from pymodaq.utils.leco.actor import PymodaqActor
from pymodaq.examples.mock_plugins import MockStageDevice, MockCameraDevice  # or your real plugin
from pymodaq.utils.leco.daq_move_LECODirector import LECODirector

# actor = PymodaqActor('stage', MockStageDevice)
# actor.connect()
# print(f"Actor full name: {actor.full_name}")   # ← shows e.g. "MYPC.stage"
# print("Actor ready — Ctrl+C to stop")
# actor.listen()


actor = PymodaqActor('viewer', MockCameraDevice)
actor.connect()
print(f"Actor full name: {actor.full_name}")   # ← shows e.g. "MYPC.stage"
print("Actor ready — Ctrl+C to stop")
actor.listen()


