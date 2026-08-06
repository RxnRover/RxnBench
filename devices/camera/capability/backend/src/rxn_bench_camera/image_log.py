"""Append-only image archive - one file per capture, auto-cleaned after max_days.

Mirrors session_log.py's rotate-and-prune shape but for binary frames instead
of JSONL text. Images are much larger than a log line, so the default
retention window is shorter - tune max_days (or the capture interval) to fit
the host's actual storage budget.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path

_IMAGE_DIR = Path(__file__).resolve().parents[2] / "logs" / "images"
_MAX_DAYS  = 7


class ImageLog:
    """Writes each captured frame to its own timestamped file under logs/images/."""

    def __init__(
        self,
        prefix:    str  = "camera",
        max_days:  int  = _MAX_DAYS,
        image_dir: Path = _IMAGE_DIR,
    ) -> None:
        self._prefix = prefix
        self._dir    = Path(image_dir)
        self._dir.mkdir(parents=True, exist_ok=True)
        self._prune(max_days)

    def save(self, image: bytes, ext: str = "jpg") -> Path:
        """Write one captured frame to disk and return its path."""
        ts = datetime.now().strftime("%Y-%m-%d_%H-%M-%S_%f")
        path = self._dir / f"{self._prefix}_{ts}.{ext}"
        path.write_bytes(image)
        return path

    def _prune(self, max_days: int) -> None:
        cutoff = datetime.now() - timedelta(days=max_days)
        for f in self._dir.glob(f"{self._prefix}_*"):
            try:
                if datetime.fromtimestamp(f.stat().st_mtime) < cutoff:
                    f.unlink()
            except OSError:
                pass
