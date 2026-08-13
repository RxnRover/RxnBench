"""Instrument wrapper classes for RxnBenchClient.

Each class wraps a single SiLA server and exposes the commands for one
instrument type. These four are auto-discovered via bench.devices.<name>
(see rxn_bench_client.devices) - bench.connect() also still works, and is
the only option for a custom instrument not in DEVICE_REGISTRY.

To support a new instrument, follow the same pattern: accept a SilaClient
in __init__ and expose methods that call it::

    from rxn_bench_client import RxnBenchClient, Spectrometer

    with RxnBenchClient() as bench:
        bench.connect("spectrometer", Spectrometer, server="rxn-bench-spec")

        bench.devices.gantry.mount_toolhead("ph_probe")
        for well in bench.devices.gantry.get_workspace_wells("plate1"):
            with bench.at_well(well, stabilize=3):
                bench.log(ph=bench.devices.ph.read())

Each wrapper lives in its own module (motion.py, ph.py, camera.py, pump.py) -
this package just re-exports the four public classes so
``from rxn_bench_client.instruments import Gantry`` (and
``from rxn_bench_client import Gantry``) keep working.
"""

from .camera import Camera
from .motion import Gantry
from .ph import PHProbe
from .pump import DosingPump

__all__ = ["Gantry", "PHProbe", "Camera", "DosingPump"]
