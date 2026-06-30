"""
SiLA2 feature definition for this device.

This is what the SiLA protocol exposes to clients (frontend, experiment scripts).
It depends only on MyDeviceProtocol - never on a concrete driver class.

CDK decorator reference:
    @sila.ObservableProperty()   - streaming value, clients subscribe and receive updates
    @sila.UnobservableProperty() - one-shot read on demand
    @sila.ObservableCommand()    - long-running command with progress/status stream
    @sila.UnobservableCommand()  - fire-and-forget command, returns when done

TODO: rename MyDevice (the class) to match your device, e.g. ConductivitySensor.
      The class name becomes the SiLA feature identifier on the wire.
"""
import asyncio

from unitelabs.cdk import sila

from chem_bench_template.interfaces import MyDeviceProtocol


class MyDevice(sila.Feature):
    """
    TODO: rename class and update originator/category if needed.
          originator = reverse-domain identifier for your organisation
          category   = logical grouping (e.g. "rxnbench", "fluidics")
          version    = semantic version string
    """

    def __init__(self, device: MyDeviceProtocol) -> None:
        super().__init__(
            originator="edu.iastate.ames",
            category="rxnbench",
            version="1.0",
            maturity_level="Draft",
        )
        self._device = device

    @sila.ObservableProperty()
    async def measurement(self) -> sila.Stream[float]:
        """
        TODO: rename (e.g. `conductivity`, `temperature`, `level`).
              Update the docstring - the Returns: field becomes the SiLA
              display name clients see.

        Returns:
            Measurement: Current reading from the device.
        """
        while True:
            yield self._device.read()
            await asyncio.sleep(1.0)  # TODO: adjust polling interval as needed

    @sila.UnobservableCommand()
    async def perform_action(self, parameter: float) -> None:
        """
        TODO: rename (e.g. `dispense`, `set_flow_rate`, `move_to`).
              Args: and Returns: fields become SiLA parameter/response names.

        Args:
            Parameter: TODO - describe what this value controls and its units.
        """
        await asyncio.to_thread(self._device.do_action, parameter)
