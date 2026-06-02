"""SCPI Power Supply instrument driver.

Standard SCPI commands are used. Override CMD_* class attributes if your
instrument uses non-standard command names.

Example:
    class AgilentE3631A(PowerSupply):
        CMD_SET_VOLTAGE = "VOLT"          # some instruments shorten names
"""

from __future__ import annotations

from src.instruments.base import BaseInstrument


class PowerSupply(BaseInstrument):
    """SCPI-compliant programmable power supply driver.

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
    CMD_MEASURE_VOLTAGE = "MEASure:VOLTage[:DC]?"
    CMD_MEASURE_CURRENT = "MEASure:CURRent[:DC]?"
    CMD_MEASURE_POWER = "MEASure:POWer?"

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
