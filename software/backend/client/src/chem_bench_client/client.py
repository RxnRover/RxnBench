"""
Blocking Python client for the Chem Bench SiLA servers.

Intended for use in experiment scripts run on the backend machine.

Usage::

    from chem_bench_client import ChemBenchClient

    with ChemBenchClient() as bench:
        bench.load_workspace("my_plates")
        bench.set_toolhead("ph_probe")

        results = {}
        for well in ["plate1/A1", "plate1/B1"]:
            bench.move_to_well(well)
            bench.engage_tool()
            results[well] = bench.read_ph()
            bench.disengage_tool()

Adding a new device (e.g. conductivity on port 50053)::

    with ChemBenchClient(extra_servers={"conductivity": ("localhost", 50053)}) as bench:
        bench.sila["conductivity"].ConductivitySensor.ReadConductivity()
"""
from __future__ import annotations

from sila2.client import SilaClient

GANTRY_PORT = 50051
PH_PORT     = 50052


class ChemBenchClient:
    """Blocking SiLA client for experiment scripts.

    Access any feature not yet wrapped here through ``bench.sila``::

        bench.sila["gantry"].Gantry.HomeAuto()
        bench.sila["ph"].PHSensor.Calibrate(Point="mid", Value=7.0)
    """

    def __init__(
        self,
        host: str = "localhost",
        gantry_port: int = GANTRY_PORT,
        ph_port: int = PH_PORT,
        extra_servers: dict[str, tuple[str, int]] | None = None,
    ) -> None:
        self.sila: dict[str, SilaClient] = {
            "gantry": SilaClient(host, gantry_port, insecure=True),
            "ph":     SilaClient(host, ph_port,     insecure=True),
        }
        for name, (h, p) in (extra_servers or {}).items():
            self.sila[name] = SilaClient(h, p, insecure=True)

    def close(self) -> None:
        for client in self.sila.values():
            client.close()

    def __enter__(self) -> "ChemBenchClient":
        return self

    def __exit__(self, *_) -> None:
        self.close()

    def _subscribe_once(self, prop):
        sub = prop.subscribe()
        try:
            return next(sub)
        finally:
            sub.cancel()

    def load_workspace(self, name: str) -> None:
        self.sila["gantry"].Gantry.SetWorkspace(Name=name)

    def load_workspace_yaml(self, content: str) -> None:
        self.sila["gantry"].Gantry.LoadWorkspaceYaml(Content=content)

    def list_workspaces(self) -> list[str]:
        result = self.sila["gantry"].Gantry.ListWorkspaces()
        return [w for w in result.Workspaces.splitlines() if w]

    def set_toolhead(self, name: str) -> None:
        self.sila["gantry"].Gantry.SetToolhead(Name=name)

    def confirm_toolhead_mounted(self) -> None:
        self.sila["gantry"].Gantry.ConfirmToolheadMounted()

    def clear_toolhead_mounted(self) -> None:
        self.sila["gantry"].Gantry.ClearToolheadMounted()

    def list_toolheads(self) -> list[tuple[str, str]]:
        result = self.sila["gantry"].Gantry.ListToolheads()
        return [
            (p[0].strip(), p[1].strip())
            for line in result.Toolheads.splitlines()
            if len(p := line.split("|", 1)) == 2
        ]

    def move_to(self, x: float, y: float, z: float) -> None:
        self.sila["gantry"].Gantry.MoveTo(X=x, Y=y, Z=z)

    def move_to_well(self, label: str) -> None:
        self.sila["gantry"].Gantry.MoveToWell(Label=label)

    def jog(self, dx: float = 0.0, dy: float = 0.0, dz: float = 0.0) -> None:
        self.sila["gantry"].Gantry.Jog(Dx=dx, Dy=dy, Dz=dz)

    def engage_tool(self, depth: float | None = None) -> None:
        if depth is None:
            depth = self._subscribe_once(self.sila["gantry"].Gantry.ToolheadInfo).ZEngage
        self.sila["gantry"].Gantry.EngageTool(Depth=depth)

    def disengage_tool(self, depth: float | None = None) -> None:
        if depth is None:
            depth = self._subscribe_once(self.sila["gantry"].Gantry.ToolheadInfo).ZEngage
        self.sila["gantry"].Gantry.DisengageTool(Depth=depth)

    def get_position(self) -> tuple[float, float, float]:
        pos = self._subscribe_once(self.sila["gantry"].Gantry.Position)
        return pos.X, pos.Y, pos.Z

    def save_and_park(self) -> None:
        self.sila["gantry"].Gantry.SaveAndPark()

    def read_ph(self) -> float:
        return self._subscribe_once(self.sila["ph"].PHSensor.Ph)
