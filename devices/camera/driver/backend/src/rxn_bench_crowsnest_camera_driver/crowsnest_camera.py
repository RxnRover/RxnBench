"""HTTP driver for a Crowsnest-managed webcam stream.

Crowsnest itself is a process supervisor for a real streamer backend
(ustreamer by default, sometimes mjpg-streamer) - it has no API of its own.
This talks straight to that streamer's plain HTTP snapshot route, matching
ustreamer's default `/snapshot` endpoint. If a bench's crowsnest.conf is
configured for mjpg-streamer instead, override snapshot_path accordingly
(e.g. "/webcam/?action=snapshot").
"""
import requests

# (connect, read) timeouts - a wedged webcam stream must not hang the whole
# server, same rationale as MoonrakerClient's HTTP calls.
_TIMEOUT = (3.05, 10.0)


class CrowsnestCamera:
    """Camera driver that fetches JPEG snapshots from a Crowsnest webcam stream."""

    def __init__(self, base_url: str, snapshot_path: str = "/snapshot") -> None:
        """
        Args:
            base_url: Crowsnest host, e.g. "http://sv08.local:8080".
            snapshot_path: HTTP path that returns one JPEG frame.
        """
        self._url = base_url.rstrip("/") + snapshot_path

    def capture(self) -> bytes:
        """Fetch and return one JPEG-encoded frame."""
        response = requests.get(self._url, timeout=_TIMEOUT)
        response.raise_for_status()
        return response.content
