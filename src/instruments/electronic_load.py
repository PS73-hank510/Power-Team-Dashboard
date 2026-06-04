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

import time

from src.instruments.base import BaseInstrument, CommunicationError

# Valid load modes
LOAD_MODES = ("CC", "CV", "CR", "CP")

# Prodigit 3330F numeric MODE? response map.
# The 3330F firmware sometimes returns a digit code instead of the text
# abbreviation: 0 = CC, 1 = CR, 2 = CV, 3 = CP.
_PRODIGIT_MODE_NUM_MAP: dict[str, str] = {
    "0": "CC",
    "1": "CR",
    "2": "CV",
    "3": "CP",
}


# ---------------------------------------------------------------------------
# Profile registry  —  key must match SettingsManager.load_command_profile
# ---------------------------------------------------------------------------
# To add a new profile:
#   1. Subclass ElectronicLoad and override the CMD_* attributes you need.
#   2. Add an entry here.
#   3. Add a human-readable label to LOAD_PROFILE_LABELS in settings_manager.py.


class ElectronicLoad(BaseInstrument):
    """SCPI-compliant programmable electronic load driver.

    Select operating mode (CC/CV/CR/CP), set the mode value, and measure
    the actual voltage and current drawn. Input state control (on/off) is
    also provided.

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
        remote_enable_command: str = "",
    ) -> None:
        super().__init__(
            resource_string,
            baud_rate=baud_rate,
            write_termination=write_termination,
            read_termination=read_termination,
            timeout_ms=timeout_ms,
            connect_preamble=connect_preamble,
        )
        self._remote_enable_command = remote_enable_command

    def connect(self) -> None:
        """Connect, apply preamble, and send the remote-enable command if configured.

        The remote-enable command (e.g. ``SYST:REM``, ``REMOTE``) is sent
        once after connection is established.  A failure is silenced so that
        instruments which do not require it are not affected.
        """
        super().connect()
        if self._remote_enable_command:
            try:
                self._write(self._remote_enable_command)
            except CommunicationError:
                pass  # Non-fatal: carry on regardless

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

    # Optional error-queue query — set to e.g. "SYSTem:ERRor?" if supported
    CMD_QUERY_ERROR = ""

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

    def query_error(self) -> str:
        """Query the instrument error queue.

        Returns the raw response string, or ``''`` when the profile does not
        define ``CMD_QUERY_ERROR`` or when the query fails.

        Never raises — callers can safely call this as a best-effort check.
        """
        if not self.CMD_QUERY_ERROR:
            return ""
        try:
            return self._query(self.CMD_QUERY_ERROR)
        except CommunicationError:
            return ""

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


class ShortScpiElectronicLoad(ElectronicLoad):
    """Electronic load profile using abbreviated SCPI command forms.

    Use this for instruments whose firmware accepts short-form SCPI
    (e.g. 'MEAS:VOLT?' instead of 'MEASure:VOLTage?').

    Override further CMD_* attributes in a sub-subclass if your instrument
    deviates from these short forms.
    """
    CMD_MEASURE_VOLTAGE = "MEAS:VOLT?"
    CMD_MEASURE_CURRENT = "MEAS:CURR?"
    CMD_SET_MODE        = "FUNC"
    CMD_QUERY_MODE      = "FUNC?"
    CMD_INPUT_ON        = "INP ON"
    CMD_INPUT_OFF       = "INP OFF"
    CMD_QUERY_INPUT     = "INP?"


class ProdigitDualChannelLoad(ElectronicLoad):
    """Driver for one channel of a Prodigit 3330F module in a 3302G mainframe.

    The 3330F is a dual-channel DC electronic load.  The 3302G protocol uses
    a **select-then-command** pattern — a channel-select command is sent first,
    then bare commands (no per-command prefix) follow for that channel.

    Do not instantiate this class directly — use ``ProdigitCh1Load`` (channel 1)
    or ``ProdigitCh2Load`` (channel 2).

    Protocol sequence per operation
    --------------------------------
    1. ``CHAN{n}``           — select the channel (e.g. ``CHAN1``)
    2. ``CC 0.0``            — reset current setpoint to 0 before a mode change
                               (prevents residual setpoints blocking CP engagement)
    3. ``MODE {mode}``       — set the operating mode (CC / CV / CR / CP)
    4. ``{mode} {value}``    — set the mode setpoint (e.g. ``CC 5.0``, ``CV 12.0``)
    5. ``VOLT?`` / ``CURR?`` — measure terminal voltage / load current

    Command reference
    -----------------
        CHAN{n}                    select channel n (required before all others)
        CC 0.0                     reset to CC 0 (clears residual mode setpoint)
        MODE CC|CV|CR|CP           set operating mode
        CC <A>   CV <V>            CC / CV setpoint
        CR <Ω>   CP <W>            CR / CP setpoint
        MODE?                      query current operating mode
        VOLT?    CURR?             measure terminal voltage / load current
        LOAD ON  LOAD OFF          enable / disable load input
        *IDN?                      identify module (global — no channel select needed)

    Timing
    ------
    Mode switching requires brief delays after each write (the instrument needs
    time to process the transition).  These are applied in ``set_mode`` only;
    ``measure_voltage`` / ``measure_current`` add no delay.

    Note: ``set_mode`` and ``set_value`` run on the Qt main thread (called from
    the Apply button handler) and will pause the UI for ~350 ms during a mode
    change.  This is a hardware requirement and is unavoidable.
    """

    #: Channel number — override in subclasses (1 or 2).
    CHANNEL: int = 1

    #: Command sent to select this channel before every operation.
    #: Override if your firmware uses a different syntax (e.g. ``"@1"``).
    _CHAN_SELECT_CMD = "CHAN{ch}"

    #: Measurement query commands (sent after channel select).
    _MEAS_VOLT_CMD = "VOLT?"
    _MEAS_CURR_CMD = "CURR?"

    # Delay constants (seconds) — derived from the working reference driver.
    _MODE_SWITCH_RESET_DELAY  = 0.20   # after CC 0.0 reset
    _MODE_SWITCH_SETTLE_DELAY = 0.15   # after MODE {x} command
    _VALUE_WRITE_DELAY        = 0.05   # after setpoint write

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _select_channel(self) -> None:
        """Send the channel-select command for this instance's channel."""
        self._write(self._CHAN_SELECT_CMD.format(ch=self.CHANNEL))

    # ------------------------------------------------------------------
    # Mode control
    # ------------------------------------------------------------------

    def set_mode(self, mode: str) -> None:
        """Select channel, optionally reset to CC 0, then set the mode.

        The reset-to-CC-0 step only runs when the mode actually changes,
        so repeated calls with the same mode are efficient (one write).

        Timing delays (~350 ms total on a mode change) are necessary for
        the 3330F firmware to accept the new mode reliably.

        Raises ValueError for an unrecognised mode.
        Raises CommunicationError on VISA failure.
        """
        mode = mode.upper()
        if mode not in LOAD_MODES:
            raise ValueError(
                f"Invalid load mode: {mode!r}. Must be one of {LOAD_MODES}."
            )
        self._select_channel()
        if getattr(self, "_last_mode", None) == mode:
            return  # already in this mode — skip reset and re-announcement
        # Disable load input first, then hard-reset to CC 0.  The LOAD OFF
        # prevents the residual setpoint from stressing the DUT during the
        # mode transition.  CC 0.0 clears any non-zero setpoint left over from
        # the previous mode (required before engaging CP; harmless for CC/CV/CR).
        self._write("LOAD OFF")
        self._write("CC 0.0")
        time.sleep(self._MODE_SWITCH_RESET_DELAY)
        self._write(f"MODE {mode}")
        time.sleep(self._MODE_SWITCH_SETTLE_DELAY)
        self._last_mode = mode

    def set_value(self, mode: str, value: float) -> None:
        """Set mode (with CC-0 reset if mode changed) then write the setpoint.

        The setpoint command uses the mode name directly as the SCPI verb:
        ``CC <A>``, ``CV <V>``, ``CR <Ω>``, ``CP <W>``.

        Raises ValueError for an unrecognised mode.
        Raises CommunicationError on VISA failure.
        """
        mode = mode.upper()
        if mode not in LOAD_MODES:
            raise ValueError(f"Invalid load mode: {mode!r}.")
        self.set_mode(mode)  # No-op if already in this mode
        self._write(f"{mode} {value:.6g}")
        time.sleep(self._VALUE_WRITE_DELAY)

    def get_mode(self) -> str:
        """Select channel, query ``MODE?``, and return the mode name (e.g. ``'CC'``).

        The 3330F firmware may respond with a numeric code instead of a string:
        ``0`` → CC, ``1`` → CR, ``2`` → CV, ``3`` → CP.  Both numeric and
        string responses are normalised to the two-letter mode abbreviation.

        Raises CommunicationError on VISA failure.
        """
        self._select_channel()
        response = self._query("MODE?").strip().upper()
        return _PRODIGIT_MODE_NUM_MAP.get(response, response)

    def query_load_state(self) -> str:
        """Select channel and query whether the load input is active.

        Sends ``LOAD?`` after the channel-select command and returns the
        normalised response (e.g. ``'ON'``, ``'OFF'``, ``'1'``, ``'0'``).
        Returns ``''`` when the query fails.  Never raises.
        """
        try:
            self._select_channel()
            return self._query("LOAD?").strip().upper()
        except CommunicationError:
            return ""

    # ------------------------------------------------------------------
    # Measurement — select channel first, then query (no sleep needed)
    # ------------------------------------------------------------------

    def measure_voltage(self) -> float:
        """Select channel, send ``VOLT?``, return the terminal voltage in V.

        Raises CommunicationError on VISA failure.
        """
        self._select_channel()
        return self._query_float(self._MEAS_VOLT_CMD)

    def measure_current(self) -> float:
        """Select channel, send ``CURR?``, return the load current in A.

        Raises CommunicationError on VISA failure.
        """
        self._select_channel()
        return self._query_float(self._MEAS_CURR_CMD)

    # ------------------------------------------------------------------
    # Input state
    # ------------------------------------------------------------------

    def input_on(self) -> None:
        """Select channel and send ``LOAD ON``.

        Raises CommunicationError on VISA failure.
        """
        self._select_channel()
        self._write("LOAD ON")

    def input_off(self) -> None:
        """Select channel and send ``LOAD OFF``.

        Raises CommunicationError on VISA failure.
        """
        self._select_channel()
        self._write("LOAD OFF")


class ProdigitCh1Load(ProdigitDualChannelLoad):
    """Prodigit 3330F — Channel 1.  Sends ``CHAN1`` before every command."""
    CHANNEL = 1


class ProdigitCh2Load(ProdigitDualChannelLoad):
    """Prodigit 3330F — Channel 2.  Sends ``CHAN2`` before every command."""
    CHANNEL = 2


class ProdigitBothChannelsLoad(ProdigitDualChannelLoad):
    """Prodigit 3330F — both channels operated in lock-step.

    All mode/setpoint/input commands are applied to CH1 then CH2.
    Measurements poll CH2 first (caching the result) and then CH1
    (whose value is returned), so the instrument ends each poll cycle
    with CH1 selected — keeping bare subsequent commands on CH1 by default.

    CH2 readings are cached in ``_last_ch2_voltage`` / ``_last_ch2_current``
    and exposed via ``measure_voltage_ch2()`` / ``measure_current_ch2()``.
    The GUI calls these immediately after ``measure_voltage/current()`` to
    update the CH2 display without a second round-trip.

    Mode-change sequence per channel::

        CHANn → LOAD OFF → CC 0.0 → (200 ms) → MODE {x} → (150 ms)

    The sequence is skipped for any channel already in the target mode,
    so repeated calls with the same mode are cheap (one CHAN select each).

    Note: each full mode transition sleeps ≈ 700 ms total (2 × 350 ms);
    this is a hardware requirement and blocks the calling thread.
    """

    CHANNEL = 1  # Primary — used by inherited helpers where applicable

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._last_ch2_voltage: float = 0.0
        self._last_ch2_current: float = 0.0
        self._last_mode_ch2: str | None = None  # per-channel mode cache for CH2

    # ------------------------------------------------------------------
    # Internal helper — shared mode-transition logic for a single channel
    # ------------------------------------------------------------------

    def _apply_mode_ch(self, ch: int, mode: str, cache_attr: str) -> None:
        """Select *ch*, then apply the safe mode-change sequence if needed.

        If the cached mode for the channel already matches *mode* only the
        channel-select command is sent and the method returns immediately.
        """
        self._write(f"CHAN{ch}")
        if getattr(self, cache_attr, None) == mode:
            return  # already in this mode — channel selected, nothing else
        self._write("LOAD OFF")
        self._write("CC 0.0")
        time.sleep(self._MODE_SWITCH_RESET_DELAY)
        self._write(f"MODE {mode}")
        time.sleep(self._MODE_SWITCH_SETTLE_DELAY)
        setattr(self, cache_attr, mode)

    # ------------------------------------------------------------------
    # Mode control — CH1 then CH2
    # ------------------------------------------------------------------

    def set_mode(self, mode: str) -> None:
        """Apply mode-change sequence to CH1, then CH2.

        Each channel runs: LOAD OFF → CC 0.0 → (200 ms) → MODE {x} → (150 ms),
        but only when the target mode differs from the cached mode for that channel.

        Raises ValueError for an unrecognised mode.
        Raises CommunicationError on VISA failure.
        """
        mode = mode.upper()
        if mode not in LOAD_MODES:
            raise ValueError(
                f"Invalid load mode: {mode!r}. Must be one of {LOAD_MODES}."
            )
        self._apply_mode_ch(1, mode, "_last_mode")
        self._apply_mode_ch(2, mode, "_last_mode_ch2")

    def set_value(self, mode: str, value: float) -> None:
        """Set mode (if changed) then write setpoint to both channels.

        The setpoint command uses the mode name as the SCPI verb
        (e.g. ``CC 5``, ``CV 12``), consistent with the single-channel driver.

        Raises ValueError for an unrecognised mode.
        Raises CommunicationError on VISA failure.
        """
        mode = mode.upper()
        if mode not in LOAD_MODES:
            raise ValueError(f"Invalid load mode: {mode!r}.")
        self.set_mode(mode)  # applies to both channels; no-op if mode unchanged
        # CH1 setpoint
        self._write("CHAN1")
        self._write(f"{mode} {value:.6g}")
        time.sleep(self._VALUE_WRITE_DELAY)
        # CH2 setpoint
        self._write("CHAN2")
        self._write(f"{mode} {value:.6g}")
        time.sleep(self._VALUE_WRITE_DELAY)

    # ------------------------------------------------------------------
    # Measurement — CH2 polled first (cached), CH1 value returned
    # ------------------------------------------------------------------

    def measure_voltage(self) -> float:
        """Measure CH2 (cache result), then measure and return CH1 voltage.

        Raises CommunicationError on VISA failure.
        """
        self._write("CHAN2")
        self._last_ch2_voltage = self._query_float(self._MEAS_VOLT_CMD)
        self._write("CHAN1")
        return self._query_float(self._MEAS_VOLT_CMD)

    def measure_current(self) -> float:
        """Measure CH2 (cache result), then measure and return CH1 current.

        Raises CommunicationError on VISA failure.
        """
        self._write("CHAN2")
        self._last_ch2_current = self._query_float(self._MEAS_CURR_CMD)
        self._write("CHAN1")
        return self._query_float(self._MEAS_CURR_CMD)

    def measure_voltage_ch2(self) -> float:
        """Return the CH2 voltage cached by the most recent ``measure_voltage()`` call."""
        return self._last_ch2_voltage

    def measure_current_ch2(self) -> float:
        """Return the CH2 current cached by the most recent ``measure_current()`` call."""
        return self._last_ch2_current

    # ------------------------------------------------------------------
    # Input state — both channels
    # ------------------------------------------------------------------

    def input_on(self) -> None:
        """Enable the load input on both CH1 and CH2.

        Raises CommunicationError on VISA failure.
        """
        self._write("CHAN1")
        self._write("LOAD ON")
        self._write("CHAN2")
        self._write("LOAD ON")

    def input_off(self) -> None:
        """Disable the load input on both CH1 and CH2.

        Raises CommunicationError on VISA failure.
        """
        self._write("CHAN1")
        self._write("LOAD OFF")
        self._write("CHAN2")
        self._write("LOAD OFF")


LOAD_PROFILES: dict[str, type[ElectronicLoad]] = {
    "standard_scpi":       ElectronicLoad,
    "short_scpi":          ShortScpiElectronicLoad,
    "prodigit_3330f_ch1":  ProdigitCh1Load,
    "prodigit_3330f_ch2":  ProdigitCh2Load,
    "prodigit_3330f_both": ProdigitBothChannelsLoad,
}
