"""
In-memory mock for development and testing without hardware.

Must satisfy MyDeviceProtocol - one method per interface method.
Return realistic-looking fixed values so the SiLA feature and any
experiment scripts can run end-to-end without physical hardware.

Activated by: RXN_BENCH_MOCK=1 rxn-bench-mydevice

TODO: rename MockMyDevice and update return values to match your device's
      realistic output range.
"""
from rxn_bench_template.interfaces import MyDeviceProtocol


class MockMyDevice:
    """
    TODO: rename to e.g. MockConductivitySensor, MockLiquidHandler, etc.
    """

    def read(self) -> float:
        # TODO: return a realistic fixed value for your measurement.
        # e.g. for conductivity: return 1413.0  (µS/cm, mid-range standard)
        return 0.0

    def do_action(self, parameter: float) -> None:
        # TODO: no-op is fine. Optionally log or store the parameter for
        # assertions in tests: self._last_parameter = parameter
        pass


# Verify the mock satisfies the protocol at import time (catches missing methods).
assert isinstance(MockMyDevice(), MyDeviceProtocol), (
    "MockMyDevice does not satisfy MyDeviceProtocol - add the missing methods."
)
