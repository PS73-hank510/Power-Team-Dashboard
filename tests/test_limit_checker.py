"""Tests for LimitChecker — breach detection, resolution, and rate limiting."""

from __future__ import annotations

import time
from unittest.mock import patch

import pytest

from src.core.limit_checker import LimitChecker, ALERT_RATE_LIMIT_SECONDS
from src.core.models import LimitPair, TelemetrySample


def _sample(source="PSU", parameter="voltage", value=12.0, unit="V"):
    return TelemetrySample(timestamp=time.time(), source=source,
                           parameter=parameter, value=value, unit=unit)


# ------------------------------------------------------------------
# Upper limit tests
# ------------------------------------------------------------------

def test_upper_breach_detected():
    checker = LimitChecker({"PSU_voltage": LimitPair(max=15.0)})
    alerts = checker.check(_sample(value=15.32))
    assert len(alerts) == 1
    assert "UPPER LIMIT BREACH" in alerts[0]
    assert "15.32" in alerts[0] or "15.3" in alerts[0]
    assert "15" in alerts[0]


def test_upper_breach_message_contains_direction():
    checker = LimitChecker({"PSU_voltage": LimitPair(max=15.0)})
    alerts = checker.check(_sample(value=16.0))
    assert ">" in alerts[0]


def test_upper_breach_no_alert_when_at_limit():
    checker = LimitChecker({"PSU_voltage": LimitPair(max=15.0)})
    alerts = checker.check(_sample(value=15.0))
    assert alerts == []


def test_upper_no_breach_below_limit():
    checker = LimitChecker({"PSU_voltage": LimitPair(max=15.0)})
    alerts = checker.check(_sample(value=14.99))
    assert alerts == []


# ------------------------------------------------------------------
# Lower limit tests
# ------------------------------------------------------------------

def test_lower_breach_detected():
    checker = LimitChecker({"PSU_voltage": LimitPair(min=9.0)})
    alerts = checker.check(_sample(value=8.5))
    assert len(alerts) == 1
    assert "LOWER LIMIT BREACH" in alerts[0]
    assert "<" in alerts[0]


def test_lower_no_breach_above_limit():
    checker = LimitChecker({"PSU_voltage": LimitPair(min=9.0)})
    alerts = checker.check(_sample(value=9.01))
    assert alerts == []


# ------------------------------------------------------------------
# Sustained breach — no duplicate alert
# ------------------------------------------------------------------

def test_no_duplicate_upper_alert_on_sustained_breach():
    checker = LimitChecker({"PSU_voltage": LimitPair(max=15.0)})
    checker.check(_sample(value=16.0))  # first breach
    alerts = checker.check(_sample(value=16.5))  # still breached
    assert alerts == []


def test_no_duplicate_lower_alert_on_sustained_breach():
    checker = LimitChecker({"PSU_voltage": LimitPair(min=9.0)})
    checker.check(_sample(value=8.0))
    alerts = checker.check(_sample(value=7.5))
    assert alerts == []


# ------------------------------------------------------------------
# Resolution
# ------------------------------------------------------------------

def test_resolution_alert_on_return_to_range():
    checker = LimitChecker({"PSU_voltage": LimitPair(max=15.0)})
    checker.check(_sample(value=16.0))  # breach
    alerts = checker.check(_sample(value=14.0))  # resolved
    assert len(alerts) == 1
    assert "RESOLVED" in alerts[0]
    assert "upper" in alerts[0].lower()


def test_no_resolution_alert_if_never_breached():
    checker = LimitChecker({"PSU_voltage": LimitPair(max=15.0)})
    alerts = checker.check(_sample(value=14.0))
    assert alerts == []


# ------------------------------------------------------------------
# Both upper and lower simultaneously
# ------------------------------------------------------------------

def test_both_sides_can_breach_simultaneously():
    """A pathological signal that is simultaneously above max and below min is impossible,
    but two separate parameters can each be in breach."""
    checker = LimitChecker({
        "PSU_voltage": LimitPair(min=9.0, max=15.0),
        "PSU_current": LimitPair(max=5.0),
    })
    alerts_v = checker.check(_sample(parameter="voltage", value=16.0))
    alerts_i = checker.check(_sample(parameter="current", value=6.0, unit="A"))
    assert len(alerts_v) == 1
    assert len(alerts_i) == 1


def test_upper_and_lower_both_on_same_param():
    """Both limits configured — only the relevant side fires."""
    checker = LimitChecker({"PSU_voltage": LimitPair(min=9.0, max=15.0)})
    # Only upper breach
    alerts = checker.check(_sample(value=16.0))
    assert len(alerts) == 1
    assert "UPPER" in alerts[0]
    assert "LOWER" not in alerts[0]


# ------------------------------------------------------------------
# None limits disabled
# ------------------------------------------------------------------

def test_none_max_means_no_upper_check():
    checker = LimitChecker({"PSU_voltage": LimitPair(min=9.0, max=None)})
    alerts = checker.check(_sample(value=999.0))  # huge value, no upper limit
    assert alerts == []


def test_none_min_means_no_lower_check():
    checker = LimitChecker({"PSU_voltage": LimitPair(min=None, max=15.0)})
    alerts = checker.check(_sample(value=-999.0))  # huge negative, no lower limit
    assert alerts == []


def test_unknown_parameter_ignored():
    checker = LimitChecker({"PSU_voltage": LimitPair(max=15.0)})
    alerts = checker.check(_sample(parameter="power", value=9999.0, unit="W"))
    assert alerts == []


# ------------------------------------------------------------------
# Rate limiting
# ------------------------------------------------------------------

def test_rate_limit_suppresses_second_alert_within_window():
    checker = LimitChecker({"PSU_voltage": LimitPair(max=15.0)})
    # Breach, then resolve, then breach again within 60s
    checker.check(_sample(value=16.0))   # breach → alert
    checker.check(_sample(value=14.0))   # resolve → resolved alert
    alerts = checker.check(_sample(value=16.0))  # second breach within window
    # Rate limit should suppress (last alert was just now)
    assert alerts == []


def test_rate_limit_allows_alert_after_window():
    checker = LimitChecker({"PSU_voltage": LimitPair(max=15.0)})
    checker.check(_sample(value=16.0))
    checker.check(_sample(value=14.0))

    # Fast-forward past the rate limit window
    with patch("src.core.limit_checker.time") as mock_time:
        mock_time.time.return_value = time.time() + ALERT_RATE_LIMIT_SECONDS + 1
        alerts = checker.check(_sample(value=16.0))
    assert len(alerts) == 1


# ------------------------------------------------------------------
# update_limits and reset
# ------------------------------------------------------------------

def test_update_limits_resets_state():
    checker = LimitChecker({"PSU_voltage": LimitPair(max=15.0)})
    checker.check(_sample(value=16.0))  # breach
    checker.update_limits({"PSU_voltage": LimitPair(max=20.0)})
    # Old breach state cleared — value 16 is now within new limit
    alerts = checker.check(_sample(value=16.0))
    assert alerts == []


def test_reset_clears_breach_state():
    checker = LimitChecker({"PSU_voltage": LimitPair(max=15.0)})
    checker.check(_sample(value=16.0))  # breach active
    checker.reset()
    # After reset, going back to 14 should NOT produce a "resolved" alert
    alerts = checker.check(_sample(value=14.0))
    assert alerts == []


# ------------------------------------------------------------------
# Multi-instrument breach-state isolation (source_index)
# ------------------------------------------------------------------

def test_independent_breach_state_per_source_index():
    """PSU-0 and PSU-1 breach states are tracked independently."""
    checker = LimitChecker({"PSU_voltage": LimitPair(max=15.0)})
    s0_breach = TelemetrySample(time.time(), "PSU", "voltage", 16.0, "V", source_index=0)
    s1_ok     = TelemetrySample(time.time(), "PSU", "voltage", 14.0, "V", source_index=1)
    s1_breach = TelemetrySample(time.time(), "PSU", "voltage", 16.0, "V", source_index=1)

    alerts0 = checker.check(s0_breach)       # PSU-0 breaches → alert
    assert len(alerts0) == 1
    assert "UPPER LIMIT BREACH" in alerts0[0]

    alerts1_ok = checker.check(s1_ok)        # PSU-1 in range → no alert
    assert alerts1_ok == []

    alerts1_breach = checker.check(s1_breach)  # PSU-1 breaches independently → alert
    assert len(alerts1_breach) == 1
    assert "UPPER LIMIT BREACH" in alerts1_breach[0]


def test_breach_state_not_shared_across_source_indices():
    """A breach on PSU-0 must not suppress the first breach alert on PSU-1."""
    checker = LimitChecker({"PSU_voltage": LimitPair(max=15.0)})
    s0_breach = TelemetrySample(time.time(), "PSU", "voltage", 16.0, "V", source_index=0)
    s1_breach = TelemetrySample(time.time(), "PSU", "voltage", 16.0, "V", source_index=1)

    checker.check(s0_breach)  # PSU-0 in breach — state_key "PSU_0_voltage_upper" = True

    # PSU-1 has never breached: its state_key "PSU_1_voltage_upper" is still False
    alerts = checker.check(s1_breach)
    assert len(alerts) == 1, (
        "PSU-1 must alert even though PSU-0 is already in breach; "
        "state keys must include source_index to prevent cross-instrument contamination."
    )
