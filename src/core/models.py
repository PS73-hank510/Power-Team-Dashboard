"""Shared data models used across all modules.

These dataclasses and enums are the single source of truth for data shapes.
Import from here — never redefine in other modules.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Optional


class TestState(Enum):
    """States of the test bench state machine."""

    DISCONNECTED = auto()
    CONNECTED = auto()
    RUNNING = auto()
    STOPPED = auto()


@dataclass
class TelemetrySample:
    """A single timestamped measurement from one instrument.

    Attributes:
        timestamp: Unix timestamp (time.time()) when the sample was taken.
        source:    Instrument identifier — "PSU" or "LOAD".
        parameter: Measurement name — "voltage", "current", "power".
        value:     The numeric measurement value.
        unit:      SI unit string — "V", "A", "W", "Ω".
    """

    timestamp: float
    source: str       # "PSU" or "LOAD"
    parameter: str    # "voltage", "current", "power"
    value: float
    unit: str         # "V", "A", "W", "Ω"

    @classmethod
    def now(cls, source: str, parameter: str, value: float, unit: str) -> "TelemetrySample":
        """Convenience constructor that stamps with the current time."""
        return cls(
            timestamp=time.time(),
            source=source,
            parameter=parameter,
            value=value,
            unit=unit,
        )


@dataclass
class LimitPair:
    """Upper and lower limits for a single telemetry parameter.

    Either bound may be None, meaning that side is disabled (no check performed).

    Attributes:
        min: Lower limit. Alert fires when value < min. None = disabled.
        max: Upper limit. Alert fires when value > max. None = disabled.
    """

    min: Optional[float] = None
    max: Optional[float] = None

    def has_any(self) -> bool:
        """Return True if at least one bound is configured."""
        return self.min is not None or self.max is not None

    def to_dict(self) -> dict:
        """Serialize to a JSON-compatible dict."""
        return {"min": self.min, "max": self.max}

    @classmethod
    def from_dict(cls, d: dict) -> "LimitPair":
        """Deserialize from a JSON-compatible dict."""
        return cls(min=d.get("min"), max=d.get("max"))
