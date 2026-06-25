"""
Safe-travel motion execution.

Wraps MotionClientProtocol with the three-step clearance travel sequence
(raise → XY → lower).  Depends only on MotionClientProtocol — no toolhead
geometry, no axis limits, no homing state.

Author: John Brittain
Date: Jun 2026
"""
from chem_bench.io.interfaces.motion import MotionClientProtocol


class MotionEngine:

    def __init__(self, client: MotionClientProtocol) -> None:
        self._client = client

    def move_to(
        self,
        x: float | None,
        y: float | None,
        z: float | None,
        clearance_z: float,
        speed: float | None = None,
    ) -> None:
        """Safe clearance travel: raise to clearance_z → XY → lower to z.

        clearance_z is computed by the controller and passed in so this method
        has no dependency on toolhead geometry or axis limits.
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
        self._client.jog(dx, dy, dz, speed)

    def move(
        self,
        x: float | None = None,
        y: float | None = None,
        z: float | None = None,
        speed: float | None = None,
    ) -> None:
        self._client.move(x=x, y=y, z=z, speed=speed)

    def get_position(self) -> dict[str, float]:
        return self._client.get_position()

    def get_state(self) -> str:
        return self._client.get_state()
