"""CSV telemetry logger.

Opens a timestamped session CSV file and appends one row per TelemetrySample.
The file is flushed on every write so data survives an unexpected process kill.
"""

from __future__ import annotations

import csv
import os
from datetime import datetime
from pathlib import Path
from typing import Optional, TextIO

from src.core.models import TelemetrySample


class CsvLogger:
    """Write telemetry samples to a timestamped CSV file.

    Usage:
        logger = CsvLogger(log_dir=Path("logs"))
        logger.start()
        logger.write(sample)
        logger.stop()
    """

    COLUMNS = ("timestamp", "source", "source_index", "parameter", "value", "unit")

    def __init__(self, log_dir: Path) -> None:
        self._log_dir = log_dir
        self._file: Optional[TextIO] = None
        self._writer: Optional[csv.DictWriter] = None
        self._path: Optional[Path] = None

    @property
    def path(self) -> Optional[Path]:
        """Path to the current log file, or None if not started."""
        return self._path

    @property
    def is_open(self) -> bool:
        """True if the logger is currently active."""
        return self._file is not None

    def start(self) -> Path:
        """Open a new timestamped CSV file and write the header row.

        Returns the path to the created file.
        Raises RuntimeError if already started.
        """
        if self._file is not None:
            raise RuntimeError("CsvLogger is already running. Call stop() first.")

        self._log_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        self._path = self._log_dir / f"session_{timestamp}.csv"

        self._file = open(self._path, "w", newline="", encoding="utf-8")
        self._writer = csv.DictWriter(self._file, fieldnames=self.COLUMNS)
        self._writer.writeheader()
        self._file.flush()
        return self._path

    def write(self, sample: TelemetrySample) -> None:
        """Append one row for the given sample and flush immediately.

        Raises RuntimeError if start() has not been called or stop() was called.
        """
        if self._file is None or self._writer is None:
            raise RuntimeError(
                "CsvLogger is not running. Call start() before write()."
            )

        iso_ts = datetime.fromtimestamp(sample.timestamp).strftime(
            "%Y-%m-%dT%H:%M:%S.") + f"{int(sample.timestamp * 1000) % 1000:03d}"

        self._writer.writerow(
            {
                "timestamp": iso_ts,
                "source": sample.source,
                "source_index": sample.source_index,
                "parameter": sample.parameter,
                "value": f"{sample.value:.6g}",
                "unit": sample.unit,
            }
        )
        self._file.flush()

    def stop(self) -> None:
        """Close the log file. Subsequent write() calls will raise RuntimeError."""
        if self._file is not None:
            try:
                self._file.flush()
                self._file.close()
            except OSError:
                pass
            finally:
                self._file = None
                self._writer = None
