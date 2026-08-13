"""Gantry (XYZ motion platform) instrument wrapper."""

from __future__ import annotations

import yaml as _yaml
from sila2.client import SilaClient

from ._util import _once, _snapshot


def _well_labels(rows: int, cols: int) -> list[str]:
    return [f"{chr(65 + r)}{c + 1}" for r in range(rows) for c in range(cols)]


class Gantry:
    """XYZ motion platform. Attach via bench.connect("gantry", Gantry, server=...).

    Examples::

        bench.connect("gantry", Gantry, server="rxn-bench-gantry")

        bench.gantry.mount_toolhead("ph_probe")
        bench.gantry.move_to_well("plate1/A3")
        bench.gantry.engage_tool()
        bench.gantry.disengage_tool()

        wells = bench.gantry.get_workspace_wells("plate1")

    ``save_and_park()`` moves to the home corner and persists homing state for
    next session; ``RxnBenchClient.close()`` calls it automatically whenever a
    connected gantry's session ends (script finished, stopped, or raised), so
    scripts don't need to call it directly.
    """

    def __init__(self, sila: SilaClient) -> None:
        """
        Args:
            sila: Connected SilaClient pointed at the gantry server.
        """
        self._g = sila
        self._token = ""  # experiment lock token; set by acquire_experiment_lock()

    def get_workspace_yaml(self) -> str:
        """Return raw YAML of the active workspace."""
        return self._g.Gantry.GetWorkspaceYaml()[0]

    def load_workspace_yaml(
        self,
        content: str | None = None,
        *,
        if_empty: bool = False,
    ) -> None:
        """Load a workspace from a YAML string.

        Pass ``None`` to use whatever workspace is already active on the server
        (raises if none is loaded). Pass ``if_empty=True`` to load only when
        the server has nothing loaded yet.
        """
        if content is None:
            if not self.get_workspace_yaml():
                raise RuntimeError(
                    "No workspace is loaded on the gantry server. "
                    "Load one in the UI or pass a YAML string."
                )
            return
        if if_empty and self.get_workspace_yaml():
            return
        self._g.Gantry.LoadWorkspaceYaml(Content=content, Token=self._token)

    def load_workspace(self, name: str) -> None:
        """Load a named workspace from the server's bundled definitions."""
        self._g.Gantry.SetWorkspace(Name=name, Token=self._token)

    def list_workspaces(self) -> list[str]:
        text = self._g.Gantry.ListWorkspaces()[0]
        return [w for w in text.splitlines() if w]

    def get_labware(self) -> dict:
        """Return the server's labware definitions as ``{plate_type: geometry dict}``.

        The gantry server is the single source of truth for plate geometry
        (rows, columns, spacing_mm, a1 offsets, footprint).
        """
        return _yaml.safe_load(self._g.Gantry.GetLabware()[0]) or {}

    def get_workspace_wells(
        self,
        plate_id: str | None = None,
        *,
        plate_grids: dict[str, tuple[int, int]] | None = None,
    ) -> list[str]:
        """Return every well in the loaded workspace as ``'plate_id/well'`` strings.

        Plate dimensions come from the server's labware definitions
        (see :meth:`get_labware`), so any plate type installed on the server
        works without client-side registration.

        Args:
            plate_id:    Limit results to one plate (e.g. ``"plate1"``).
            plate_grids: Optional ``{plate_type: (rows, cols)}`` overrides.

        Raises:
            RuntimeError: No workspace is loaded.
            ValueError:   Unknown plate type.
        """
        grids = {name: (spec["rows"], spec["columns"]) for name, spec in self.get_labware().items()}
        grids.update(plate_grids or {})
        raw = self.get_workspace_yaml()
        if not raw:
            raise RuntimeError(
                "No workspace is loaded. Load one in the UI or call load_workspace_yaml()."
            )
        data = _yaml.safe_load(raw)
        wells: list[str] = []
        for plate in data.get("plates", []):
            pid = plate["id"]
            ptype = plate["plate_type"]
            if plate_id is not None and pid != plate_id:
                continue
            if ptype not in grids:
                raise ValueError(
                    f"Unknown plate type {ptype!r} on plate {pid!r}. "
                    f"Pass plate_grids={{'{ptype}': (rows, cols)}} to register it."
                )
            rows, cols = grids[ptype]
            wells.extend(f"{pid}/{lbl}" for lbl in _well_labels(rows, cols))
        return wells

    def set_toolhead(self, name: str) -> None:
        """Switch the active toolhead - a pure software change.

        Mount confirmations are per-head and survive switching, so alternating
        between two heads that were each confirmed once (mount_toolhead, or the
        UI at setup) needs no operator interaction mid-script::

            bench.gantry.mount_toolhead("ph_probe")   # confirm once at setup
            bench.gantry.mount_toolhead("pipette")    # confirm once at setup
            ...
            bench.gantry.set_toolhead("ph_probe")     # switch freely mid-run
            bench.gantry.set_toolhead("pipette")
        """
        self._g.Gantry.SetToolhead(Name=name, Token=self._token)

    def confirm_toolhead_mounted(self) -> None:
        """Confirm the *active* toolhead is physically mounted (idempotent)."""
        self._g.Gantry.ConfirmToolheadMounted(Token=self._token)

    def mount_toolhead(self, name: str) -> None:
        """Activate a toolhead and confirm it is physically mounted.

        Idempotent: re-confirming an already-confirmed head is a no-op on the
        server (and does not invalidate homing), so calling this at script
        startup for heads the operator already confirmed is safe.
        """
        self._g.Gantry.SetToolhead(Name=name, Token=self._token)
        self._g.Gantry.ConfirmToolheadMounted(Token=self._token)

    def clear_toolhead_mounted(self) -> None:
        self._g.Gantry.ClearToolheadMounted(Token=self._token)

    def list_toolheads(self) -> list[tuple[str, str]]:
        text = self._g.Gantry.ListToolheads()[0]
        return [
            (p[0].strip(), p[1].strip())
            for line in text.splitlines()
            if len(p := line.split("|", 1)) == 2
        ]

    def move_to(self, x: float, y: float, z: float) -> None:
        self._g.Gantry.MoveTo(X=x, Y=y, Z=z, Token=self._token)

    def move_to_well(self, label: str, override_unvalidated: bool = False) -> None:
        self._g.Gantry.MoveToWell(
            Label=label, OverrideUnvalidated=override_unvalidated, Token=self._token
        )
        _snapshot(self, "move_to_well")

    def jog(self, dx: float = 0.0, dy: float = 0.0, dz: float = 0.0) -> None:
        self._g.Gantry.Jog(Dx=dx, Dy=dy, Dz=dz, Token=self._token)

    def shake(
        self,
        *,
        amplitude: float = 1.5,
        cycles: int = 12,
        axis: str = "xy",
    ) -> None:
        """Jitter the toolhead to fling off droplets on toolheads.

        Jogs +/- *amplitude* mm for *cycles* round trips, cycling through each
        axis in *axis* in turn (round-robin) rather than oscillating along a
        single axis, and ends back at the starting position. Handy after
        lifting the pH probe clear of a well to shake loose water before the
        next reading, cutting carryover.

        Short, frequent bursts across more than one axis shake harder than one
        long oscillation on a single axis of the same total travel: each jog
        is its own accel/decel burst, so more (shorter) jogs pack more
        direction reversals into the same envelope, and alternating axes flings
        droplets in more than one direction instead of just back and forth.

        The tip must already be clear of labware: the shake happens at the
        current position, so raise or disengage the tool first.

        Args:
            amplitude: Half-stroke of each burst in mm (> 0).
            cycles:    Number of back-and-forth bursts (>= 1), split round-robin
                       across the axes in *axis*.
            axis:      Axis or axes to shake along, any combination of "x", "y",
                       "z" - e.g. "y" for a single axis (the old default) or
                       "xy"/"xyz" to alternate between them each cycle.
        """
        if amplitude <= 0.0:
            raise ValueError("amplitude must be positive")
        if cycles < 1:
            raise ValueError("cycles must be at least 1")
        unit = {
            "x": (1.0, 0.0, 0.0),
            "y": (0.0, 1.0, 0.0),
            "z": (0.0, 0.0, 1.0),
        }
        axis = axis.lower()
        if not axis or any(a not in unit for a in axis):
            raise ValueError(f"axis must only contain 'x', 'y', or 'z', got {axis!r}")
        for i in range(cycles):
            ux, uy, uz = unit[axis[i % len(axis)]]
            dx, dy, dz = ux * amplitude, uy * amplitude, uz * amplitude
            self.jog(dx=dx, dy=dy, dz=dz)
            self.jog(dx=-dx, dy=-dy, dz=-dz)

    def engage_tool(self, depth: float | None = None) -> None:
        if depth is None:
            depth = _once(self._g.Gantry.ToolheadInfo).ZEngage
        self._g.Gantry.EngageTool(Depth=depth, Token=self._token)
        _snapshot(self, "engage_tool")

    def disengage_tool(self, depth: float | None = None) -> None:
        if depth is None:
            depth = _once(self._g.Gantry.ToolheadInfo).ZEngage
        self._g.Gantry.DisengageTool(Depth=depth, Token=self._token)
        _snapshot(self, "disengage_tool")

    def get_position(self) -> tuple[float, float, float]:
        pos = _once(self._g.Gantry.Position)
        return pos.X, pos.Y, pos.Z

    def get_limits(self) -> str:
        return self._g.Gantry.GetLimits()[0]

    def save_and_park(self) -> None:
        self._g.Gantry.SaveAndPark(Token=self._token)

    def acquire_experiment_lock(self) -> None:
        """Claim the experiment lock; all other clients' motion commands are rejected.

        The lock is acquired automatically by :class:`RxnBenchClient` on connect and
        released when the session closes. Only one client can hold the lock at a time.
        The server returns a secret token, which this instrument attaches to every
        subsequent motion/toolhead/workspace command so they pass the backend's
        lock gate; manual UI commands (no token) are rejected until release.
        """
        self._token = self._g.Gantry.AcquireExperimentLock()[0]

    def release_experiment_lock(self) -> None:
        """Release the experiment lock so another client may connect."""
        self._g.Gantry.ReleaseExperimentLock(Token=self._token)
        self._token = ""

    def force_release_experiment_lock(self) -> None:
        """Forcibly clear a stranded experiment lock (no token required).

        Recovery for when a previous script died without releasing - e.g. a
        killed process. Only use when you are sure no script is running.
        """
        self._g.Gantry.ForceReleaseExperimentLock()
        self._token = ""

    def get_experiment_state(self) -> str:
        """Return the current experiment state string (e.g. ``'running'``, ``'paused'``, ``'stop_requested'``)."""
        return self._g.Gantry.GetExperimentState()[0]
