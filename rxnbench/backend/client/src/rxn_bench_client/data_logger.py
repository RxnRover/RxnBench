"""CSV data logger for experiment scripts."""
from __future__ import annotations

import csv
import datetime
import pathlib
from typing import Any


class DataLogger:
    """Write experiment readings to a CSV file with timestamps.

    Each device or measurement type gets its own column.  Every call to
    :meth:`record` appends one row with the current ISO timestamp plus any
    keyword arguments you pass.

    Usage::

        from rxn_bench_client import DataLogger

        with DataLogger("ph_scan.csv", columns=["well", "ph"]) as log:
            for well in wells:
                bench.move_to_well(well)
                ph = bench.read_ph()
                log.record(well=well, ph=ph)

    The resulting CSV looks like::

        timestamp,well,ph
        2026-06-30T14:23:01.042,plate1/A1,7.21
        2026-06-30T14:23:07.318,plate1/A2,6.88

    Columns not declared in *columns* but passed to :meth:`record` are
    silently ignored (``extrasaction="ignore"``).  Columns declared but
    not passed default to an empty cell.
    """

    def __init__(
        self,
        path: str | pathlib.Path,
        columns: list[str] | None = None,
    ) -> None:
        """
        Args:
            path:    Destination CSV file. Parent directories are created on enter.
            columns: Ordered column names (excluding ``timestamp``, which is always first).
                     Columns not listed are silently ignored when passed to :meth:`record`.
        """
        self._path    = pathlib.Path(path)
        self._columns = list(columns or [])
        self._file    = None
        self._writer  = None

    def __enter__(self) -> "DataLogger":
        """Open the output file and write the CSV header."""
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._file = open(self._path, "w", newline="", encoding="utf-8")
        self._writer = csv.DictWriter(
            self._file,
            fieldnames=["timestamp"] + self._columns,
            extrasaction="ignore",
        )
        self._writer.writeheader()
        self._file.flush()
        return self

    def __exit__(self, *_: Any) -> None:
        """Close the file."""
        if self._file:
            self._file.close()
            self._file = None
            self._writer = None

    def record(self, **kwargs: Any) -> None:
        """Append one row.  Pass measurement names as keyword arguments."""
        if self._writer is None:
            raise RuntimeError("DataLogger must be used as a context manager (with DataLogger(...) as log:)")
        row: dict[str, Any] = {
            "timestamp": datetime.datetime.now().isoformat(timespec="milliseconds"),
        }
        row.update(kwargs)
        self._writer.writerow(row)
        self._file.flush()
