"""Power Supply instrument drivers.

``PowerSupply`` uses standard IEEE 488.2 / SCPI long-form commands and works
with the vast majority of bench supplies (Keysight, Rigol, Aim-TTi, …).

Instrument-specific subclasses override the CMD_* class attributes for
manufacturers that deviate from the standard.  The active class is chosen by
the *PSU Command Profile* setting in the Settings dialog.

Profile registry (key → class):
    "standard_scpi"   → PowerSupply          (default)
    "tdklambda_zplus" → TDKLambdaZPlus       (Z20, Z60, Z100, Z+ series)

Adding a new profile:
    1. Subclass PowerSupply and override the CMD_* attributes you need.
    2. Add the new class to PSU_PROFILES at the bottom of this file.
    3. Add a human-readable label to _PSU_PROFILE_LABELS in settings_manager.py.
"""

from __future__ import annotations

from src.instruments.base import BaseInstrument


class PowerSupply(BaseInstrument):
    """Standard SCPI programmable power supply driver.

    Measure and set voltage/current, control output state.
    All command strings are class attributes — override for non-standard instruments.
    """

    def __init__(
        self,
        resource_string: str,
        baud_rate: int = 9600,
        write_termination: str = "\n",
        read_termination: str = "\n",
        timeout_ms: int = 5000,
        connect_preamble: str = "",
    ) -> None:
        super().__init__(
            resource_string,
            baud_rate=baud_rate,
            write_termination=write_termination,
            read_termination=read_termination,
            timeout_ms=timeout_ms,
            connect_preamble=connect_preamble,
        )

    # Measurement queries
    CMD_MEASURE_VOLTAGE = "MEASure:VOLTage?"
    CMD_MEASURE_CURRENT = "MEASure:CURRent?"
    CMD_MEASURE_POWER   = "MEASure:POWer?"

    # Setpoint commands (follow with space + value)
    CMD_SET_VOLTAGE = "VOLTage"
    CMD_SET_CURRENT = "CURRent"

    # Output control
    CMD_OUTPUT_ON = "OUTPut ON"
    CMD_OUTPUT_OFF = "OUTPut OFF"
    CMD_QUERY_OUTPUT = "OUTPut?"

    # ------------------------------------------------------------------
    # Measurement
    # ------------------------------------------------------------------

    def measure_voltage(self) -> float:
        """Return the measured output voltage in volts.

        Raises CommunicationError on VISA failure.
        """
        return self._query_float(self.CMD_MEASURE_VOLTAGE)

    def measure_current(self) -> float:
        """Return the measured output current in amperes.

        Raises CommunicationError on VISA failure.
        """
        return self._query_float(self.CMD_MEASURE_CURRENT)

    def measure_power(self) -> float:
        """Return the measured output power in watts.

        Falls back to V*I if the instrument does not support MEASure:POWer?.
        Raises CommunicationError on VISA failure.
        """
        try:
            return self._query_float(self.CMD_MEASURE_POWER)
        except Exception:
            # Fallback: compute from V and I
            v = self.measure_voltage()
            i = self.measure_current()
            return v * i

    # ------------------------------------------------------------------
    # Setpoints
    # ------------------------------------------------------------------

    def set_voltage(self, voltage: float) -> None:
        """Set the output voltage setpoint in volts.

        Raises CommunicationError on VISA failure.
        """
        self._write(f"{self.CMD_SET_VOLTAGE} {voltage:.6g}")

    def set_current(self, current: float) -> None:
        """Set the output current limit in amperes.

        Raises CommunicationError on VISA failure.
        """
        self._write(f"{self.CMD_SET_CURRENT} {current:.6g}")

    # ------------------------------------------------------------------
    # Output state
    # ------------------------------------------------------------------

    def output_on(self) -> None:
        """Enable the power supply output.

        Raises CommunicationError on VISA failure.
        """
        self._write(self.CMD_OUTPUT_ON)

    def output_off(self) -> None:
        """Disable the power supply output.

        Raises CommunicationError on VISA failure.
        """
        self._write(self.CMD_OUTPUT_OFF)


# ---------------------------------------------------------------------------
# TDK-Lambda Z+ / Z series
# ---------------------------------------------------------------------------

class TDKLambdaZPlus(PowerSupply):
    """TDK-Lambda Z+/Z series power supply (Z20-10, Z60-3.5, Z100-2, …).

    Uses TDK-Lambda's short-form command set instead of standard SCPI long-form.
    Connect via the rear-panel USB-B port (presents as a virtual COM port).
    No ADR preamble is required over USB; leave the Connection Preamble blank.

    Key differences from standard SCPI:
        MV? / MC?        — measure voltage / current  (replaces MEASure:…)
        PV <v> / PC <i>  — program voltage / current  (replaces VOLTage/CURRent)
        OUT 1 / OUT 0    — output on / off             (replaces OUTPut ON/OFF)
    """

    # Measurement
    CMD_MEASURE_VOLTAGE = "MV?"
    CMD_MEASURE_CURRENT = "MC?"
    CMD_MEASURE_POWER   = "MP?"   # not present on all firmware; falls back to V*I

    # Setpoints (write as "PV 12.5", "PC 3.0")
    CMD_SET_VOLTAGE = "PV"
    CMD_SET_CURRENT = "PC"

    # Output control
    CMD_OUTPUT_ON    = "OUT 1"
    CMD_OUTPUT_OFF   = "OUT 0"
    CMD_QUERY_OUTPUT = "OUT?"


# ---------------------------------------------------------------------------
# Profile registry  —  key must match SettingsManager.psu_command_profile
# ---------------------------------------------------------------------------

PSU_PROFILES: dict[str, type[PowerSupply]] = {
    "standard_scpi":   PowerSupply,
    "tdklambda_zplus": TDKLambdaZPlus,
}
