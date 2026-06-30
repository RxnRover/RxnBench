"""Append-only JSONL audit log — one file per server session, auto-cleaned after 30 days."""
from __future__ import annotations

import atexit
import json
from datetime import datetime, timedelta
from pathlib import Path

_LOG_DIR  = Path(__file__).resolve().parents[2] / "logs"
_MAX_DAYS = 30


class SessionLog:
    """
    Opens a new JSONL file each time the gantry server starts.
    On open, deletes any log files older than *max_days* so storage stays bounded.

    Each line is a JSON object with at minimum:
        {"ts": "<ISO timestamp>", "event": "<name>", ...}

    Empty/None keyword values are dropped to keep entries compact.
    """

    def __init__(
        self,
        prefix:   str  = "session",
        max_days: int  = _MAX_DAYS,
        log_dir:  Path = _LOG_DIR,
    ) -> None:
        self._prefix = prefix
        self._dir    = Path(log_dir)
        self._dir.mkdir(parents=True, exist_ok=True)
        self._prune(max_days)
        ts = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        self._path = self._dir / f"{prefix}_{ts}.jsonl"
        self._fh   = self._path.open("w", encoding="utf-8")
        self._append("server_start")
        atexit.register(self.close)

    # ------------------------------------------------------------------
    # Public log API
    # ------------------------------------------------------------------

    def log(self, event: str, **kwargs) -> None:
        """Append one event line. None and empty-string values are omitted."""
        self._append(event, **{k: v for k, v in kwargs.items() if v not in (None, "")})

    def close(self) -> None:
        if not self._fh.closed:
            self._append("server_stop")
            self._fh.close()

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _append(self, event: str, **kwargs) -> None:
        entry = {"ts": datetime.now().isoformat(timespec="milliseconds"), "event": event, **kwargs}
        self._fh.write(json.dumps(entry) + "\n")
        self._fh.flush()

    def _prune(self, max_days: int) -> None:
        cutoff = datetime.now() - timedelta(days=max_days)
        for f in self._dir.glob(f"{self._prefix}_*.jsonl"):
            try:
                if datetime.fromtimestamp(f.stat().st_mtime) < cutoff:
                    f.unlink()
            except OSError:
                pass
