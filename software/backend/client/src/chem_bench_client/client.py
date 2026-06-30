"""
Blocking Python client for the Chem Bench SiLA servers.

Intended for use in experiment scripts run on the backend machine.

Usage::

    from chem_bench_client import ChemBenchClient

    with ChemBenchClient() as bench:
        bench.load_workspace_yaml(WORKSPACE_YAML)
        bench.set_toolhead("ph_probe")
        bench.confirm_toolhead_mounted()

        results = {}
        for well in ["plate1/A1", "plate1/B1"]:
            bench.move_to_well(well)
            bench.engage_tool()
            results[well] = bench.read_ph()
            bench.disengage_tool()
"""
from __future__ import annotations

from sila2.client import SilaClient

GANTRY_PORT = 50051
PH_PORT     = 50052


class ChemBenchClient:
    def __init__(
        self,
        host: str = "localhost",
        gantry_port: int = GANTRY_PORT,
        ph_port: int = PH_PORT,
        extra_servers: dict[str, tuple[str, int]] | None = None,
    ) -> None:
        self._g = SilaClient(host, gantry_port, insecure=True)
        self._p = SilaClient(host, ph_port,     insecure=True)
        self.sila: dict[str, SilaClient] = {"gantry": self._g, "ph": self._p}
        for name, (h, p) in (extra_servers or {}).items():
            self.sila[name] = SilaClient(h, p, insecure=True)

    def close(self) -> None:
        for c in self.sila.values():
            c.close()

    def __enter__(self) -> "ChemBenchClient":
        return self

    def __exit__(self, *_) -> None:
        self.close()

    def _once(self, prop) -> object:
        sub = prop.subscribe()
        try:
            return next(sub)
        finally:
            sub.cancel()

    # ------------------------------------------------------------------
    # Workspace
    # ------------------------------------------------------------------

    def load_workspace(self, name: str) -> None:
        self._g.Gantry.SetWorkspace(Name=name)

    def load_workspace_yaml(self, content: str) -> None:
        self._g.Gantry.LoadWorkspaceYaml(Content=content)

    def list_workspaces(self) -> list[str]:
        text = self._g.Gantry.ListWorkspaces()[0]
        return [w for w in text.splitlines() if w]

    # ------------------------------------------------------------------
    # Toolheads
    # ------------------------------------------------------------------

    def set_toolhead(self, name: str) -> None:
        self._g.Gantry.SetToolhead(Name=name)

    def confirm_toolhead_mounted(self) -> None:
        self._g.Gantry.ConfirmToolheadMounted()

    def clear_toolhead_mounted(self) -> None:
        self._g.Gantry.ClearToolheadMounted()

    def list_toolheads(self) -> list[tuple[str, str]]:
        text = self._g.Gantry.ListToolheads()[0]
        return [
            (p[0].strip(), p[1].strip())
            for line in text.splitlines()
            if len(p := line.split("|", 1)) == 2
        ]

    # ------------------------------------------------------------------
    # Motion
    # ------------------------------------------------------------------

    def move_to(self, x: float, y: float, z: float) -> None:
        self._g.Gantry.MoveTo(X=x, Y=y, Z=z)

    def move_to_well(self, label: str) -> None:
        self._g.Gantry.MoveToWell(Label=label)

    def jog(self, dx: float = 0.0, dy: float = 0.0, dz: float = 0.0) -> None:
        self._g.Gantry.Jog(Dx=dx, Dy=dy, Dz=dz)

    def engage_tool(self, depth: float | None = None) -> None:
        if depth is None:
            depth = self._once(self._g.Gantry.ToolheadInfo).ZEngage
        self._g.Gantry.EngageTool(Depth=depth)

    def disengage_tool(self, depth: float | None = None) -> None:
        if depth is None:
            depth = self._once(self._g.Gantry.ToolheadInfo).ZEngage
        self._g.Gantry.DisengageTool(Depth=depth)

    def get_position(self) -> tuple[float, float, float]:
        pos = self._once(self._g.Gantry.Position)
        return pos.X, pos.Y, pos.Z

    def save_and_park(self) -> None:
        self._g.Gantry.SaveAndPark()

    def get_limits(self) -> str:
        return self._g.Gantry.GetLimits()[0]

    # ------------------------------------------------------------------
    # pH sensor
    # ------------------------------------------------------------------

    def read_ph(self) -> float:
        return self._once(self._p.PHSensor.Ph)
