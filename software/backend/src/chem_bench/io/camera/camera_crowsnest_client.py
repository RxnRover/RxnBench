"""
Client for the Crowsnest camera server running on the SV08.

Satisfies: CameraClientProtocol (io/interfaces/camera.py)

Author: John Brittain
Date: Jun 17 2026
"""


class CrowsnestClient:
    """Client for communicating with Crowsnest, the camera server hosted by the SV08.

    Satisfies CameraClientProtocol. Full HTTP implementation is a future task;
    get_snapshot and get_stream_url are stubs that return the correct types
    so the protocol surface is committed before the implementation is written.
    """

    def __init__(self, host: str, port: int = 8080):
        self.host = host
        self.port = port

    def get_snapshot(self) -> bytes:
        """Capture a single frame from Crowsnest and return it as JPEG bytes."""
        raise NotImplementedError("CrowsnestClient.get_snapshot not yet implemented")

    def get_stream_url(self) -> str:
        """Return the URL of the Crowsnest MJPEG stream."""
        return f"http://{self.host}:{self.port}/?action=stream"
