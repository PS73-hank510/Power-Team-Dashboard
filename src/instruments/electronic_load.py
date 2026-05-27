"""SCPI Electronic Load instrument driver.

Standard SCPI commands are used. Override CMD_* class attributes if your
instrument uses non-standard command names (e.g. some loads use "MODE" instead
of "FUNCtion").

Load modes:
    CC — Constant Current
    CV — Constant Voltage
    CR — Constant Resistance
    CP — Constant Power
"""

from __future__ import annotations

from src.instruments.base import BaseInstrument, CommunicationError

# Valid load modes
LOAD_MODES = ("CC", "CV", "CR", "CP")


class ElectronicLoad(BaseInstrument):
    """SCPI-compliant programmable electronic load driver.

    Select operating mode (CC/CV/CR/CP), set the mode value, and measure
    the actual voltage and current drawn. Input state control (on/off) is
    also provided.

    All command strings are class attributes — override for non-standard instruments.
    """

    # Mode selection command prefix
    CMD_SET_MODE = "FUNCtion"

    # Per-mode value commands (follow with space + value)
    CMD_SET_CURRENT = "CURRent"       # CC mode
    CMD_SET_VOLTAGE = "VOLTage"       # CV mode
    CMD_SET_RESISTANCE = "RESistance" # CR mode
    CMD_SET_POWER = "POWer"           # CP mode

    # Input (load) state
    CMD_INPUT_ON = "INPut ON"
    CMD_INPUT_OFF = "INPut OFF"
    CMD_QUERY_INPUT = "INPut?"

    # Measurement queries
    CMD_MEASURE_VOLTAGE = "MEASure:VOLTage?"
    CMD_MEASURE_CURRENT = "MEASure:CURRent?"

    # Query current mode
    CMD_QUERY_MODE = "FUNCtion?"

    # Mapping from mode string to its set-value command
    _MODE_CMD_MAP = {
        "CC": "CURRent",
        "CV": "VOLTage",
        "CR": "RESistance",
        "CP": "POWer",
    }

    # Unit for each mode (for telemetry labelling)
    MODE_UNITS = {
        "CC": "A",
        "CV": "V",
        "CR": "Ω",
        "CP": "W",
    }

    # ------------------------------------------------------------------
    # Mode control
    # ------------------------------------------------------------------

    def set_mode(self, mode: str) -> None:
        """Set the operating mode. mode must be one of CC, CV, CR, CP.

        Raises ValueError for invalid mode.
        Raises CommunicationError on VISA failure.
        """
        mode = mode.upper()
        if mode not in LOAD_MODES:
            raise ValueError(
                f"Invalid load mode: {mode!r}. Must be one of {LOAD_MODES}."
            )
        self._write(f"{self.CMD_SET_MODE} {mode}")

    def set_value(self, mode: str, value: float) -> None:
        """Set the setpoint value for the given mode.

        Automatically selects the correct SCPI command for the mode.

        Args:
            mode:  Operating mode (CC/CV/CR/CP).
            value: Setpoint value in the mode's native unit (A/V/Ω/W).

        Raises ValueError for invalid mode.
        Raises CommunicationError on VISA failure.
        """
        mode = mode.upper()
        if mode not in LOAD_MODES:
            raise ValueError(f"Invalid load mode: {mode!r}.")
        cmd = self._MODE_CMD_MAP[mode]
        self._write(f"{cmd} {value:.6g}")

    def get_mode(self) -> str:
        """Query and return the current operating mode (CC/CV/CR/CP).

        Raises CommunicationError on VISA failure.
        """
        return self._query(self.CMD_QUERY_MODE).upper()

    # ------------------------------------------------------------------
    # Measurement
    # ------------------------------------------------------------------

    def measure_voltage(self) -> float:
        """Return the measured terminal voltage in volts.

        Raises CommunicationError on VISA failure.
        """
        return self._query_float(self.CMD_MEASURE_VOLTAGE)

    def measure_current(self) -> float:
        """Return the measured load current in amperes.

        Raises CommunicationError on VISA failure.
        """
        return self._query_float(self.CMD_MEASURE_CURRENT)

    # ------------------------------------------------------------------
    # Input state
    # ------------------------------------------------------------------

    def input_on(self) -> None:
        """Enable the load input (start drawing current).

        Raises CommunicationError on VISA failure.
        """
        self._write(self.CMD_INPUT_ON)

    def input_off(self) -> None:
        """Disable the load input (stop drawing current).

        Raises CommunicationError on VISA failure.
        """
        self._write(self.CMD_INPUT_OFF)
