"""MyDevice connection - human-maintained layer on top of the generated base.

Stream registration, decoding, and simple commands are all generated (see
generated_connection.py): the measurement stream decodes via the compiled
protobuf stubs in proto/my_device_pb2.py and perform_action() is a generated
fire-and-forget command.

Add here only what the generator intentionally does not produce: blocking
fetches with responses, longer timeouts, convenience methods, and workflows -
see devices/ph_sensor/frontend/connection.py for a real example.

TODO: rename MyDeviceConnection to match your device.
"""
from __future__ import annotations

from .generated_connection import MyDeviceConnectionBase


class MyDeviceConnection(MyDeviceConnectionBase):
    """Human-owned MyDevice client.

    The generated base already provides the measurement_updated signal and
    the perform_action() command. Add convenience methods and higher-level
    workflows here.
    """
