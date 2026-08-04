"""In-memory mock dosing pump for development without hardware.

Built on the real driver stack (:class:`MockEZOPumpUart` ->
:class:`AtlasScientificEZOPumpUart` -> :class:`AtlasDosingPump`) rather than
stubbing each Protocol method, so the mock server exercises the same command
encoding and response parsing the bench will use. Dispensing advances against
the wall clock, so a dose started through the SiLA feature really does progress
and complete over its requested duration.

Activated by: RXN_BENCH_MOCK=1 rxn-bench-dosing-pump
"""
from __future__ import annotations

from rxn_bench_dosing_pump.atlas_dosing_pump import AtlasDosingPump
from rxn_bench_dosing_pump.atlas_scientific_uart_driver import AtlasScientificEZOPumpUart
from rxn_bench_dosing_pump.interfaces import DosingPumpProtocol
from rxn_bench_dosing_pump.mock_uart import MockEZOPumpUart


class MockDosingPump(AtlasDosingPump):
    """Dosing pump backed by the EZO-PMP protocol emulator instead of a serial port."""

    display_name = "Mock Dosing Pump"
    description = "Simulated Atlas Scientific EZO-PMP for development without hardware."

    def __init__(self, **port_kwargs) -> None:
        """
        Args:
            **port_kwargs: Forwarded to :class:`MockEZOPumpUart` (e.g.
                ``max_flow_rate``, ``pump_voltage``, ``clock``).
        """
        self.port = MockEZOPumpUart(**port_kwargs)
        super().__init__(AtlasScientificEZOPumpUart(self.port))


# Verify the mock satisfies the protocol at import time (catches missing methods).
assert isinstance(MockDosingPump(), DosingPumpProtocol), (
    "MockDosingPump does not satisfy DosingPumpProtocol - add the missing methods."
)
