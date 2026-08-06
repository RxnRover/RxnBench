"""In-memory mock camera for development and testing without hardware.

Activated by: RXN_BENCH_MOCK=1 rxn-bench-camera
"""
from rxn_bench_camera.interfaces import CameraProtocol


def _placeholder_image(width: int = 64, height: int = 48, gray: int = 160) -> bytes:
    """Build a tiny solid-gray PPM image, no imaging library required.

    PPM (not JPEG) on purpose: it needs no encoder dependency and Qt decodes
    it natively, so the mock stays realistic-looking without pulling in
    Pillow just to fabricate a fake frame. The real CrowsnestCamera driver
    returns actual JPEG bytes fetched over HTTP.
    """
    header = f"P6\n{width} {height}\n255\n".encode("ascii")
    return header + bytes([gray, gray, gray]) * (width * height)


class MockCamera:
    """Returns a fixed placeholder frame instead of talking to real hardware."""

    def capture(self) -> bytes:
        return _placeholder_image()


# Verify the mock satisfies the protocol at import time (catches missing methods).
assert isinstance(MockCamera(), CameraProtocol), (
    "MockCamera does not satisfy CameraProtocol - add the missing methods."
)
