"""Safety limit checker for telemetry samples.

Evaluates each TelemetrySample against configured upper and lower limits.
Tracks breach state per parameter per side to produce alerts only on transitions
(IN_RANGE → BREACH or BREACH → IN_RANGE), not on every sample.

Rate-limiting: at most one alert per parameter+side per 60 seconds.
"""

from __future__ import annotations

import time
from typing import Optional

from src.core.models import LimitPair, TelemetrySample

# Rate-limit window in seconds: suppress repeat alerts within this window
ALERT_RATE_LIMIT_SECONDS: float = 60.0


class LimitChecker:
    """Checks telemetry samples against a dict of LimitPair configurations.

    Args:
        limits: Mapping from parameter key (e.g. "PSU_voltage") to LimitPair.
                Keys are formatted as "{source}_{parameter}" (e.g. "PSU_voltage",
                "LOAD_current").

    Example:
        checker = LimitChecker({
            "PSU_voltage": LimitPair(min=9.0, max=15.0),
            "PSU_current": LimitPair(max=5.0),
        })
        alerts = checker.check(sample)
        for msg in alerts:
            notifier.send(msg)
    """

    def __init__(self, limits: Optional[dict[str, LimitPair]] = None) -> None:
        self._limits: dict[str, LimitPair] = limits or {}
        # breach_state key: "{source}_{parameter}_upper" or "_lower"
        self._breach_state: dict[str, bool] = {}
        # last_alert_time key: same format — stores time.time() of last alert sent
        self._last_alert_time: dict[str, float] = {}

    def update_limits(self, limits: dict[str, LimitPair]) -> None:
        """Replace the full limits configuration and reset all breach state."""
        self._limits = limits
        self._breach_state.clear()
        self._last_alert_time.clear()

    def check(self, sample: TelemetrySample) -> list[str]:
        """Evaluate a sample against configured limits.

        Returns a list of alert message strings for any new breach or resolution
        events. Returns an empty list if nothing noteworthy happened.
        """
        key = f"{sample.source}_{sample.parameter}"
        pair = self._limits.get(key)
        if pair is None:
            return []

        alerts: list[str] = []

        if pair.max is not None:
            alerts.extend(
                self._check_side(sample, pair.max, "upper", sample.value > pair.max)
            )
        if pair.min is not None:
            alerts.extend(
                self._check_side(sample, pair.min, "lower", sample.value < pair.min)
            )

        return alerts

    def reset(self) -> None:
        """Clear all breach state and rate-limit timers (e.g. at test stop)."""
        self._breach_state.clear()
        self._last_alert_time.clear()

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _check_side(
        self,
        sample: TelemetrySample,
        limit: float,
        side: str,          # "upper" or "lower"
        in_breach: bool,
    ) -> list[str]:
        state_key = f"{sample.source}_{sample.source_index}_{sample.parameter}_{side}"
        was_in_breach = self._breach_state.get(state_key, False)
        self._breach_state[state_key] = in_breach

        if in_breach and not was_in_breach:
            # New breach — check rate limit before alerting
            now = time.time()
            last = self._last_alert_time.get(state_key, 0.0)
            if now - last >= ALERT_RATE_LIMIT_SECONDS:
                self._last_alert_time[state_key] = now
                direction = ">" if side == "upper" else "<"
                return [
                    f"{side.upper()} LIMIT BREACH: "
                    f"{sample.source} {sample.parameter} = "
                    f"{sample.value:.4g} {sample.unit} "
                    f"({direction} {limit:.4g} {sample.unit})"
                ]
            # Rate-limited — suppress this alert
            return []

        if not in_breach and was_in_breach:
            return [
                f"RESOLVED: {sample.source} {sample.parameter} "
                f"{side} limit back in range "
                f"(value: {sample.value:.4g} {sample.unit})"
            ]

        return []
