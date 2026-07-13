"""Camera connection - human-maintained layer on top of the generated base.

Stream registration, decoding, and the set_capture_interval command are all
generated (see generated_connection.py): the latest_image stream decodes via
the compiled protobuf stubs in proto/camera_pb2.py.
"""
from __future__ import annotations

from .generated_connection import CameraConnectionBase


class CameraConnection(CameraConnectionBase):
    """Human-owned Camera client.

    The generated base already provides the latest_image_updated signal and
    the set_capture_interval() command. Nothing else is needed yet.
    """
