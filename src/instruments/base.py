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

    def __init__(self, resource_string: str) -> None:
        self._resource_string = resource_string
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
        """Open the VISA resource.

        Raises CommunicationError if the resource cannot be opened.
        """
        try:
            rm = pyvisa.ResourceManager()
            self._resource = rm.open_resource(self._resource_string)
            self._resource.timeout = 5000  # ms
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

    def _query(self, command: str) -> str:
        """Send a query and return the stripped response string."""
        if self._resource is None:
            raise CommunicationError("Not connected. Call connect() first.")
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
        if self._resource is None:
            raise CommunicationError("Not connected. Call connect() first.")
        try:
            self._resource.write(command)
        except pyvisa.Error as exc:
            raise CommunicationError(
                f"Write failed [{command}]: {exc}"
            ) from exc
