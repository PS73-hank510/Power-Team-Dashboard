"""Tests for PowerSupply and ElectronicLoad SCPI command formatting."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from src.instruments.base import CommunicationError
from src.instruments.electronic_load import ElectronicLoad, LOAD_MODES
from src.instruments.power_supply import PowerSupply


# ====================================================================
# BaseInstrument / connection
# ====================================================================

def test_connect_opens_visa_resource(mock_resource_manager):
    rm, resource = mock_resource_manager
    psu = PowerSupply("USB0::TEST::INSTR")
    psu.connect()
    rm.open_resource.assert_called_once_with("USB0::TEST::INSTR")
    assert psu.is_connected


def test_disconnect_closes_resource(connected_psu):
    psu, resource = connected_psu
    psu.disconnect()
    resource.close.assert_called_once()
    assert not psu.is_connected


def test_disconnect_safe_when_not_connected():
    psu = PowerSupply("USB0::TEST::INSTR")
    psu.disconnect()  # Should not raise


def test_connect_raises_communication_error_on_visa_failure(mock_resource_manager):
    import pyvisa
    rm, resource = mock_resource_manager
    rm.open_resource.side_effect = pyvisa.Error("no such resource")
    psu = PowerSupply("BADRESOURCE")
    with pytest.raises(CommunicationError):
        psu.connect()


def test_identify_sends_idn(connected_psu):
    psu, resource = connected_psu
    resource.query.return_value = "ACME,PSU-3000,SN12345,FW1.0"
    result = psu.identify()
    resource.query.assert_called_with("*IDN?")
    assert "ACME" in result


def test_query_without_connect_raises(mock_resource_manager):
    psu = PowerSupply("USB0::TEST::INSTR")
    with pytest.raises(CommunicationError, match="Not connected"):
        psu.identify()


# ====================================================================
# PowerSupply measurement
# ====================================================================

def test_measure_voltage_sends_correct_command(connected_psu):
    psu, resource = connected_psu
    resource.query.return_value = "12.045"
    v = psu.measure_voltage()
    resource.query.assert_called_with(PowerSupply.CMD_MEASURE_VOLTAGE)
    assert abs(v - 12.045) < 1e-6


def test_measure_current_sends_correct_command(connected_psu):
    psu, resource = connected_psu
    resource.query.return_value = "2.310"
    i = psu.measure_current()
    resource.query.assert_called_with(PowerSupply.CMD_MEASURE_CURRENT)
    assert abs(i - 2.310) < 1e-6


def test_measure_power_sends_correct_command(connected_psu):
    psu, resource = connected_psu
    resource.query.return_value = "27.81"
    p = psu.measure_power()
    resource.query.assert_called_with(PowerSupply.CMD_MEASURE_POWER)
    assert abs(p - 27.81) < 1e-6


def test_measure_power_falls_back_to_vi(connected_psu):
    """If MEASure:POWer? fails, fall back to V*I."""
    import pyvisa
    psu, resource = connected_psu

    call_count = [0]
    def query_side_effect(cmd):
        call_count[0] += 1
        if "POWer" in cmd:
            raise pyvisa.Error("not supported")
        if "VOLTage" in cmd:
            return "12.0"
        if "CURRent" in cmd:
            return "3.0"
        return "0.0"

    resource.query.side_effect = query_side_effect
    p = psu.measure_power()
    assert abs(p - 36.0) < 1e-6


def test_measure_voltage_raises_on_bad_response(connected_psu):
    psu, resource = connected_psu
    resource.query.return_value = "NOT_A_NUMBER"
    with pytest.raises(CommunicationError):
        psu.measure_voltage()


# ====================================================================
# PowerSupply setpoints
# ====================================================================

def test_set_voltage_sends_correct_command(connected_psu):
    psu, resource = connected_psu
    psu.set_voltage(12.0)
    resource.write.assert_called_with("VOLTage 12")


def test_set_current_sends_correct_command(connected_psu):
    psu, resource = connected_psu
    psu.set_current(3.5)
    resource.write.assert_called_with("CURRent 3.5")


# ====================================================================
# PowerSupply output control
# ====================================================================

def test_output_on_sends_correct_command(connected_psu):
    psu, resource = connected_psu
    psu.output_on()
    resource.write.assert_called_with("OUTPut ON")


def test_output_off_sends_correct_command(connected_psu):
    psu, resource = connected_psu
    psu.output_off()
    resource.write.assert_called_with("OUTPut OFF")


# ====================================================================
# ElectronicLoad mode control
# ====================================================================

def test_set_mode_cc(connected_load):
    load, resource = connected_load
    load.set_mode("CC")
    resource.write.assert_called_with("FUNCtion CC")


def test_set_mode_cv(connected_load):
    load, resource = connected_load
    load.set_mode("CV")
    resource.write.assert_called_with("FUNCtion CV")


def test_set_mode_cr(connected_load):
    load, resource = connected_load
    load.set_mode("CR")
    resource.write.assert_called_with("FUNCtion CR")


def test_set_mode_cp(connected_load):
    load, resource = connected_load
    load.set_mode("CP")
    resource.write.assert_called_with("FUNCtion CP")


def test_set_mode_case_insensitive(connected_load):
    load, resource = connected_load
    load.set_mode("cc")
    resource.write.assert_called_with("FUNCtion CC")


def test_set_mode_invalid_raises(connected_load):
    load, resource = connected_load
    with pytest.raises(ValueError, match="Invalid load mode"):
        load.set_mode("XX")


# ====================================================================
# ElectronicLoad set_value
# ====================================================================

def test_set_value_cc_sends_current_cmd(connected_load):
    load, resource = connected_load
    load.set_value("CC", 2.5)
    resource.write.assert_called_with("CURRent 2.5")


def test_set_value_cv_sends_voltage_cmd(connected_load):
    load, resource = connected_load
    load.set_value("CV", 12.0)
    resource.write.assert_called_with("VOLTage 12")


def test_set_value_cr_sends_resistance_cmd(connected_load):
    load, resource = connected_load
    load.set_value("CR", 5.0)
    resource.write.assert_called_with("RESistance 5")


def test_set_value_cp_sends_power_cmd(connected_load):
    load, resource = connected_load
    load.set_value("CP", 30.0)
    resource.write.assert_called_with("POWer 30")


def test_set_value_invalid_mode_raises(connected_load):
    load, resource = connected_load
    with pytest.raises(ValueError):
        load.set_value("XX", 1.0)


# ====================================================================
# ElectronicLoad measurement
# ====================================================================

def test_load_measure_voltage(connected_load):
    load, resource = connected_load
    resource.query.return_value = "11.98"
    v = load.measure_voltage()
    resource.query.assert_called_with(ElectronicLoad.CMD_MEASURE_VOLTAGE)
    assert abs(v - 11.98) < 1e-6


def test_load_measure_current(connected_load):
    load, resource = connected_load
    resource.query.return_value = "2.29"
    i = load.measure_current()
    resource.query.assert_called_with(ElectronicLoad.CMD_MEASURE_CURRENT)
    assert abs(i - 2.29) < 1e-6


# ====================================================================
# ElectronicLoad input control
# ====================================================================

def test_input_on_sends_correct_command(connected_load):
    load, resource = connected_load
    load.input_on()
    resource.write.assert_called_with("INPut ON")


def test_input_off_sends_correct_command(connected_load):
    load, resource = connected_load
    load.input_off()
    resource.write.assert_called_with("INPut OFF")


# ====================================================================
# CommunicationError propagation
# ====================================================================

def test_write_raises_communication_error_on_visa_error(connected_psu):
    import pyvisa
    psu, resource = connected_psu
    resource.write.side_effect = pyvisa.Error("write error")
    with pytest.raises(CommunicationError):
        psu.set_voltage(12.0)


def test_query_raises_communication_error_on_visa_error(connected_load):
    import pyvisa
    load, resource = connected_load
    resource.query.side_effect = pyvisa.Error("query error")
    with pytest.raises(CommunicationError):
        load.measure_voltage()
