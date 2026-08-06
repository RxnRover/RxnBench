"""Safe-travel motion sequencer - raise, XY, lower."""
from rxn_bench_gantry.interfaces import MotionClientProtocol


class MotionEngine:
    """Translates high-level move requests into the raise->XY->lower clearance-travel sequence."""

    def __init__(self, client: MotionClientProtocol) -> None:
        """Initialise the engine with a motion client.

        Args:
            client: Low-level motion client that executes GCode moves.
        """
        self._client = client

    def move_to(
        self,
        x: float | None,
        y: float | None,
        z: float | None,
        clearance_z: float,
        speed: float | None = None,
    ) -> None:
        """Safe-travel move: raise to clearance_z, move XY, then lower to z.

        Args:
            x: Target X coordinate in mm, or None to skip.
            y: Target Y coordinate in mm, or None to skip.
            z: Target Z coordinate in mm, or None to leave at clearance height.
            clearance_z: Z height to rise to before lateral travel, in mm.
            speed: Travel speed in mm/min. Uses the client default if None.
        """
        self._client.move(z=clearance_z, speed=speed)
        self._client.move(x=x, y=y, speed=speed)
        self._client.move(z=z, speed=speed)

    def jog(
        self,
        dx: float = 0.0,
        dy: float = 0.0,
        dz: float = 0.0,
        speed: float | None = None,
    ) -> None:
        """Relative move with no clearance sequence.

        Args:
            dx: X displacement in mm.
            dy: Y displacement in mm.
            dz: Z displacement in mm.
            speed: Travel speed in mm/min. Uses the client default if None.
        """
        self._client.jog(dx, dy, dz, speed)

    def move(
        self,
        x: float | None = None,
        y: float | None = None,
        z: float | None = None,
        speed: float | None = None,
    ) -> None:
        """Single-axis or multi-axis absolute move.

        Args:
            x: Target X coordinate in mm, or None to skip.
            y: Target Y coordinate in mm, or None to skip.
            z: Target Z coordinate in mm, or None to skip.
            speed: Travel speed in mm/min. Uses the client default if None.
        """
        self._client.move(x=x, y=y, z=z, speed=speed)

    def get_position(self) -> dict[str, float]:
        """Return current XYZ position from the motion client."""
        return self._client.get_position()

    def get_state(self) -> str:
        """Return the motion client's state string."""
        return self._client.get_state()
