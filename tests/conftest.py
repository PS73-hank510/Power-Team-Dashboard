"""Shared pytest fixtures for mock VISA instruments and notifiers."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture
def mock_visa_resource():
    """A mock pyvisa resource that returns configurable responses."""
    resource = MagicMock()
    resource.timeout = 5000
    resource.query.return_value = "0.0"
    resource.write.return_value = None
    resource.close.return_value = None
    return resource


@pytest.fixture
def mock_resource_manager(mock_visa_resource):
    """Patches pyvisa.ResourceManager so no real VISA hardware is needed."""
    with patch("pyvisa.ResourceManager") as MockRM:
        rm_instance = MagicMock()
        rm_instance.open_resource.return_value = mock_visa_resource
        rm_instance.list_resources.return_value = (
            "USB0::0x1234::0x5678::MY12345::INSTR",
            "GPIB0::22::INSTR",
        )
        MockRM.return_value = rm_instance
        yield rm_instance, mock_visa_resource


@pytest.fixture
def connected_psu(mock_resource_manager):
    """A PowerSupply instance connected to a mock VISA resource."""
    from src.instruments.power_supply import PowerSupply
    rm, resource = mock_resource_manager
    psu = PowerSupply("USB0::MOCK::INSTR")
    psu.connect()
    return psu, resource


@pytest.fixture
def connected_load(mock_resource_manager):
    """An ElectronicLoad instance connected to a mock VISA resource."""
    from src.instruments.electronic_load import ElectronicLoad
    rm, resource = mock_resource_manager
    load = ElectronicLoad("USB0::MOCK::INSTR")
    load.connect()
    return load, resource


@pytest.fixture
def mock_notifier():
    """A TeamsNotifier with send() mocked out."""
    from src.notifications.teams_notifier import TeamsNotifier
    notifier = TeamsNotifier("https://mock.example.com/webhook")
    notifier.send = MagicMock(return_value=True)
    notifier.send_alert = MagicMock(return_value=True)
    notifier.send_resolved = MagicMock(return_value=True)
    return notifier
