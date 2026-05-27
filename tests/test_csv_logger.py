"""Tests for CsvLogger — file creation, row format, flush, and error handling."""

from __future__ import annotations

import csv
import time
from pathlib import Path

import pytest

from src.core.csv_logger import CsvLogger
from src.core.models import TelemetrySample


def _make_sample(source="PSU", parameter="voltage", value=12.0, unit="V"):
    return TelemetrySample(timestamp=time.time(), source=source,
                           parameter=parameter, value=value, unit=unit)


def test_start_creates_file(tmp_path):
    logger = CsvLogger(tmp_path)
    path = logger.start()
    assert path.exists()
    assert path.suffix == ".csv"
    assert "session_" in path.name
    logger.stop()


def test_start_creates_log_dir_if_absent(tmp_path):
    subdir = tmp_path / "new_subdir" / "logs"
    logger = CsvLogger(subdir)
    logger.start()
    assert subdir.is_dir()
    logger.stop()


def test_header_row(tmp_path):
    logger = CsvLogger(tmp_path)
    path = logger.start()
    logger.stop()
    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.reader(f)
        header = next(reader)
    assert header == ["timestamp", "source", "source_index", "parameter", "value", "unit"]


def test_write_appends_row(tmp_path):
    logger = CsvLogger(tmp_path)
    path = logger.start()
    sample = _make_sample(value=12.34)
    logger.write(sample)
    logger.stop()

    with open(path, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    assert len(rows) == 1
    assert rows[0]["source"] == "PSU"
    assert rows[0]["parameter"] == "voltage"
    assert rows[0]["unit"] == "V"
    assert "12.34" in rows[0]["value"]


def test_timestamp_is_iso8601(tmp_path):
    logger = CsvLogger(tmp_path)
    path = logger.start()
    logger.write(_make_sample())
    logger.stop()

    with open(path, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    ts = rows[0]["timestamp"]
    # ISO-8601 format: 2024-01-15T10:23:45.123
    assert "T" in ts
    assert len(ts) >= 19


def test_multiple_writes(tmp_path):
    logger = CsvLogger(tmp_path)
    path = logger.start()
    for i in range(5):
        logger.write(_make_sample(value=float(i)))
    logger.stop()

    with open(path, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    assert len(rows) == 5


def test_write_after_stop_raises(tmp_path):
    logger = CsvLogger(tmp_path)
    logger.start()
    logger.stop()
    with pytest.raises(RuntimeError):
        logger.write(_make_sample())


def test_double_start_raises(tmp_path):
    logger = CsvLogger(tmp_path)
    logger.start()
    with pytest.raises(RuntimeError):
        logger.start()
    logger.stop()


def test_stop_before_start_is_safe(tmp_path):
    logger = CsvLogger(tmp_path)
    logger.stop()  # Should not raise


def test_is_open_flag(tmp_path):
    logger = CsvLogger(tmp_path)
    assert not logger.is_open
    logger.start()
    assert logger.is_open
    logger.stop()
    assert not logger.is_open


def test_file_flushed_on_write(tmp_path):
    """File content is readable immediately after write (flush happened)."""
    logger = CsvLogger(tmp_path)
    path = logger.start()
    logger.write(_make_sample(value=99.9))
    # Read while logger is still open (file handle still open)
    with open(path, newline="", encoding="utf-8") as f:
        content = f.read()
    assert "99.9" in content
    logger.stop()
