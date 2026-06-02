"""Abstract base class for SCPI instruments over VISA.

All SCPI command strings are class-level attributes so subclasses or users
can override them without subclassing the full implementation.

Communication errors are wrapped in CommunicationError so callers never
need to import pyvisa directly.

Transport selection
-------------------
* ASRL resources (RS-232 / USB-CDC virtual COM port): handled by
  ``_SerialAdapter``, a thin pyserial wrapper.  pyvisa-py is **not** used
  for serial ports because its internal ``SetCommState`` call drives DTR
  low, which USB-CDC instruments (e.g. TDK-Lambda Z+ via USB-B) interpret
  as "host offline", causing all queries to time out.

* All other resources (USB-TMC, GPIB, LAN/VXI-11): handled by pyvisa
  with the ``@py`` pure-Python backend to avoid the NI-VISA library
  dependency (``VI_ERROR_LIBRARY_NFOUND``).
"""

from __future__ import annotations

import re
import sys
from abc import ABC
from typing import Any, Optional

import pyvisa


class CommunicationError(Exception):
    """Raised when a VISA/SCPI communication error occurs."""


# ---------------------------------------------------------------------------
# Internal serial adapter — pyserial wrapped in a pyvisa-compatible interface
# ---------------------------------------------------------------------------

class _SerialAdapter:
    """Wraps pyserial as a minimal VISA-compatible resource for ASRL ports.

    Provides the same ``write`` / ``read`` / ``query`` / ``close`` interface
    that ``BaseInstrument`` expects from a pyvisa resource, but uses pyserial
    directly so that DTR is never disturbed.

    ``inter_byte_timeout`` (50 ms) allows ``read_until`` to return after a
    brief silence even when the response does not end with the configured
    read terminator — handles instruments that terminate with ``\\r`` instead
    of ``\\r\\n``.
    """

    _INTER_BYTE_TIMEOUT_S: float = 0.05  # 50 ms between-byte silence → return early

    def __init__(
        self,
        port: str,
        baud_rate: int,
        timeout_ms: int,
        write_termination: str,
        read_termination: str,
    ) -> None:
        import serial as _pyserial  # type: ignore[import]

        self._write_term: bytes = (
            write_termination.encode("ascii") if write_termination else b""
        )
        self._read_term: bytes = (
            read_termination.encode("ascii") if read_termination else b"\n"
        )
        self._timeout_s: float = timeout_ms / 1000.0

        self._ser = _pyserial.Serial(
            port,
            baudrate=baud_rate,
            bytesize=8,
            parity="N",
            stopbits=1,
            timeout=self._timeout_s,
            write_timeout=self._timeout_s,
            inter_byte_timeout=self._INTER_BYTE_TIMEOUT_S,
        )

        # pyvisa-compatible attribute aliases (used by tests / type checkers)
        self.write_termination: str = write_termination
        self.read_termination: str = read_termination
        self.timeout: int = timeout_ms

    # ------------------------------------------------------------------
    # Minimal pyvisa resource interface
    # ------------------------------------------------------------------

    def write(self, data: str) -> None:
        """Send *data* followed by the configured write terminator."""
        raw = data.encode("ascii") + self._write_term
        try:
            self._ser.write(raw)
        except Exception as exc:
            raise pyvisa.errors.VisaIOError(
                pyvisa.constants.StatusCode.error_io
            ) from exc

    def read(self) -> str:
        """Read until terminator or inter-byte timeout.

        Returns an empty string when nothing is received (does not raise).
        """
        raw: bytes = self._ser.read_until(self._read_term)
        if raw.endswith(self._read_term):
            raw = raw[: -len(self._read_term)]
        return raw.decode("ascii", errors="replace").strip()

    def query(self, data: str) -> str:
        """write + read.  Raises ``pyvisa.VisaIOError`` on empty response."""
        self._ser.reset_input_buffer()
        self.write(data)
        result = self.read()
        if not result:
            raise pyvisa.errors.VisaIOError(
                pyvisa.constants.StatusCode.error_timeout
            )
        return result

    def close(self) -> None:
        """Close the serial port. Safe to call multiple times."""
        try:
            self._ser.close()
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _asrl_to_port(resource_string: str) -> str:
    """Convert an ASRL VISA resource string to a platform COM/tty port.

    Examples:
        Windows: ``ASRL4::INSTR``  →  ``COM4``
        Linux:   ``ASRL4::INSTR``  →  ``/dev/ttyS3``
    """
    m = re.match(r"ASRL(\d+)::INSTR", resource_string, re.IGNORECASE)
    if not m:
        raise CommunicationError(
            f"Cannot parse ASRL resource string: {resource_string!r}. "
            "Expected format: ASRL<n>::INSTR"
        )
    n = int(m.group(1))
    if sys.platform == "win32":
        return f"COM{n}"
    return f"/dev/ttyS{n - 1}"


# ---------------------------------------------------------------------------
# Abstract base
# ---------------------------------------------------------------------------

class BaseInstrument(ABC):
    """Abstract VISA instrument base.

    Subclass and override CMD_* attributes for non-standard instruments.
    """

    # Standard IEEE 488.2 identity command (common to all SCPI instruments)
    CMD_IDN   = "*IDN?"
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
        self._resource_string    = resource_string
        self._baud_rate          = baud_rate
        self._write_termination  = write_termination
        self._read_termination   = read_termination
        self._timeout_ms         = timeout_ms
        self._connect_preamble   = connect_preamble
        self._resource: Optional[Any] = None  # _SerialAdapter or pyvisa Resource

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
        """Open the resource and apply session settings.

        * ASRL resources → pyserial via ``_SerialAdapter`` (avoids DTR issue)
        * All other resources → pyvisa ``@py`` backend

        Raises ``CommunicationError`` if the resource cannot be opened.
        """
        try:
            if self._resource_string.upper().startswith("ASRL"):
                port = _asrl_to_port(self._resource_string)
                self._resource = _SerialAdapter(
                    port,
                    baud_rate=self._baud_rate,
                    timeout_ms=self._timeout_ms,
                    write_termination=self._write_termination,
                    read_termination=self._read_termination,
                )
            else:
                # '@py' forces pure-Python backend — avoids VI_ERROR_LIBRARY_NFOUND
                rm = pyvisa.ResourceManager("@py")
                res = rm.open_resource(self._resource_string)
                res.timeout           = self._timeout_ms
                res.write_termination = self._write_termination
                res.read_termination  = self._read_termination
                self._resource = res

            # Optional preamble — sent once on connect, before any SCPI query.
            # Required by RS-232 multi-drop instruments (e.g. TDK-Lambda GEN/
            # GENESYS: "ADR <n>") to select the unit.  Leave blank for USB.
            if self._connect_preamble:
                self._resource.write(self._connect_preamble)
                try:
                    self._resource.read()   # consume ack (e.g. "OK")
                except Exception:
                    pass                    # no ack — that's fine, carry on

        except CommunicationError:
            raise
        except Exception as exc:
            self._resource = None
            raise CommunicationError(
                f"Failed to connect to {self._resource_string}: {exc}"
            ) from exc

    def disconnect(self) -> None:
        """Close the resource. Safe to call even if not connected."""
        if self._resource is not None:
            try:
                self._resource.close()
            except Exception:
                pass
            finally:
                self._resource = None

    def identify(self) -> str:
        """Send *IDN? and return the instrument identification string.

        Raises ``CommunicationError`` on failure.
        """
        return self._query(self.CMD_IDN)

    # ------------------------------------------------------------------
    # Protected SCPI helpers
    # ------------------------------------------------------------------

    def _ensure_connected(self) -> None:
        """Raise ``CommunicationError`` if no resource is open."""
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
