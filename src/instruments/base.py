"""Abstract base class for SCPI instruments over VISA.

All SCPI command strings are class-level attributes so subclasses or users
can override them without subclassing the full implementation.

Communication errors are wrapped in CommunicationError so callers never
need to import pyvisa directly.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Optional

import pyvisa


class CommunicationError(Exception):
    """Raised when a VISA/SCPI communication error occurs."""


class BaseInstrument(ABC):
    """Abstract VISA instrument base.

    Subclass and override CMD_* attributes for non-standard instruments.
    """

    # Standard IEEE 488.2 identity command (common to all SCPI instruments)
    CMD_IDN = "*IDN?"
    CMD_RESET = "*RST"
    CMD_CLEAR = "*CLS"

    def __init__(
        self,
        resource_string: str,
        baud_rate: int = 9600,
        write_termination: str = "\n",
        read_termination: str = "\n",
        timeout_ms: int = 5000,
        connect_preamble: str = "",
    ) -> None:
        self._resource_string = resource_string
        self._baud_rate = baud_rate
        self._write_termination = write_termination
        self._read_termination = read_termination
        self._timeout_ms = timeout_ms
        self._connect_preamble = connect_preamble
        self._resource: Optional[pyvisa.resources.Resource] = None

    @property
    def resource_string(self) -> str:
        return self._resource_string

    @property
    def is_connected(self) -> bool:
        return self._resource is not None

    # ------------------------------------------------------------------
    # Connection management
    # ------------------------------------------------------------------

    def connect(self) -> None:
        """Open the VISA resource and apply session settings.

        Write/read termination and timeout are applied to every resource type.
        Baud rate and serial framing (8N1, no flow control) are applied only
        to ASRL (RS-232 / virtual COM port) resources — they are silently
        ignored for USB-TMC, GPIB, and TCP/IP resources.

        Raises CommunicationError if the resource cannot be opened.
        """
        try:
            # '@py' forces the pure-Python pyvisa-py backend — avoids
            # VI_ERROR_LIBRARY_NFOUND when NI-VISA is not installed.
            rm = pyvisa.ResourceManager("@py")
            self._resource = rm.open_resource(self._resource_string)
            self._resource.timeout = self._timeout_ms
            self._resource.write_termination = self._write_termination
            self._resource.read_termination = self._read_termination

            # Serial-specific settings — only meaningful for ASRL resources
            if self._resource_string.upper().startswith("ASRL"):
                import pyvisa.constants as vc
                self._resource.baud_rate = self._baud_rate
                self._resource.data_bits = 8
                self._resource.parity    = vc.Parity.none
                self._resource.stop_bits = vc.StopBits.one
                # NOTE: do NOT set flow_control here.
                # pyvisa-py maps ControlFlow.none → dsrdtr=False, which on
                # Windows causes SetCommState to set fDtrControl=
                # DTR_CONTROL_DISABLE — driving DTR low.  USB-CDC instruments
                # (TDK-Lambda Z+ via USB-B) interpret DTR=low as "host
                # offline" and stop responding to all queries.

                # After reconfiguring serial params, force DTR high.
                # Any of the assignments above (baud_rate, data_bits, …)
                # internally calls SetCommState which may reset DTR to the
                # dsrdtr-controlled default (low).  Explicitly asserting DTR
                # keeps both USB-CDC and real RS-232 instruments online.
                try:
                    _sess = self._resource.visalib.sessions.get(
                        self._resource.session
                    )
                    if _sess is not None and hasattr(_sess, "interface"):
                        _sess.interface.dtr = True
                except Exception:
                    pass  # non-pyvisa-py backend or no serial — safe to skip

            # Optional preamble — sent immediately after port open, before any
            # SCPI query. Required by some instruments (e.g. TDK-Lambda GEN/
            # GENESYS series expects "ADR <n>" to select the RS-232 address
            # before it will respond to any other command).
            if self._connect_preamble:
                self._resource.write(self._connect_preamble)
                try:
                    self._resource.read()  # consume acknowledgement (e.g. "OK")
                except pyvisa.Error:
                    pass  # no acknowledgement — that's fine, carry on

        except pyvisa.Error as exc:
            self._resource = None
            raise CommunicationError(
                f"Failed to connect to {self._resource_string}: {exc}"
            ) from exc

    def disconnect(self) -> None:
        """Close the VISA resource. Safe to call even if not connected."""
        if self._resource is not None:
            try:
                self._resource.close()
            except pyvisa.Error:
                pass
            finally:
                self._resource = None

    def identify(self) -> str:
        """Send *IDN? and return the instrument identification string.

        Raises CommunicationError on failure.
        """
        return self._query(self.CMD_IDN)

    # ------------------------------------------------------------------
    # Protected SCPI helpers
    # ------------------------------------------------------------------

    def _ensure_connected(self) -> None:
        """Raise CommunicationError if no VISA resource is open."""
        if self._resource is None:
            raise CommunicationError("Not connected. Call connect() first.")

    def _query(self, command: str) -> str:
        """Send a query and return the stripped response string."""
        self._ensure_connected()
        try:
            response = self._resource.query(command)
            return response.strip()
        except pyvisa.Error as exc:
            raise CommunicationError(
                f"Query failed [{command}]: {exc}"
            ) from exc

    def _query_float(self, command: str) -> float:
        """Send a query and return the response parsed as float."""
        raw = self._query(command)
        try:
            return float(raw)
        except ValueError as exc:
            raise CommunicationError(
                f"Could not parse float from [{command}] response: {raw!r}"
            ) from exc

    def _write(self, command: str) -> None:
        """Send a command with no response expected."""
        self._ensure_connected()
        try:
            self._resource.write(command)
        except pyvisa.Error as exc:
            raise CommunicationError(
                f"Write failed [{command}]: {exc}"
            ) from exc
