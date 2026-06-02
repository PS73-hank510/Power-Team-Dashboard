"""Communication tests — SCPI command correctness for every profile.

Verifies that each PSU/Load profile sends exactly the right command strings
to the VISA resource, responses are parsed correctly, errors propagate as
CommunicationError, and the poller delegates correctly to instruments.

No real hardware required: pyvisa.ResourceManager is mocked in conftest.py.

Test categories
---------------
SC  Standard SCPI profile (PowerSupply) — long-form commands
ZP  TDK-Lambda Z+/Z profile (TDKLambdaZPlus) — short-form commands
LD  ElectronicLoad — standard SCPI commands
ER  Error handling — CommunicationError on pyvisa failures
PR  Connection preamble — written once on connect, response consumed
RG  Profile registry — PSU_PROFILES keys and class types
PO  PollWorker integration — correct measurement methods called
"""

from __future__ import annotations

import pytest
from unittest.mock import MagicMock, call, patch

import pyvisa

from src.instruments.base import CommunicationError
from src.instruments.electronic_load import ElectronicLoad
from src.instruments.power_supply import PSU_PROFILES, PowerSupply, TDKLambdaZPlus


# ======================================================================
# Helpers
# ======================================================================

def _make_connected(cls, resource_string="USB0::MOCK::INSTR", **kwargs):
    """Return (instrument, mock_resource) with the instrument connected."""
    mock_resource = MagicMock()
    mock_resource.timeout = 5000
    mock_resource.query.return_value = "0.0"
    mock_resource.write.return_value = None
    mock_resource.close.return_value = None

    mock_rm = MagicMock()
    mock_rm.open_resource.return_value = mock_resource

    with patch("pyvisa.ResourceManager", return_value=mock_rm):
        inst = cls(resource_string, **kwargs)
        inst.connect()

    return inst, mock_resource


# ======================================================================
# SC — Standard SCPI profile
# ======================================================================

class TestStandardSCPI:

    def test_measure_voltage_command(self):
        psu, res = _make_connected(PowerSupply)
        res.query.return_value = "12.500"
        v = psu.measure_voltage()
        res.query.assert_called_with("MEASure:VOLTage[:DC]?")
        assert abs(v - 12.5) < 1e-6

    def test_measure_current_command(self):
        psu, res = _make_connected(PowerSupply)
        res.query.return_value = "3.000"
        i = psu.measure_current()
        res.query.assert_called_with("MEASure:CURRent[:DC]?")
        assert abs(i - 3.0) < 1e-6

    def test_measure_power_command(self):
        psu, res = _make_connected(PowerSupply)
        res.query.return_value = "37.500"
        p = psu.measure_power()
        res.query.assert_called_with("MEASure:POWer?")
        assert abs(p - 37.5) < 1e-6

    def test_measure_power_vi_fallback_when_unsupported(self):
        """MEASure:POWer? not supported → fall back to V*I."""
        psu, res = _make_connected(PowerSupply)

        def _side(cmd):
            if "POWer" in cmd:
                raise pyvisa.Error("not supported")
            if "VOLTage" in cmd:
                return "12.0"
            if "CURRent" in cmd:
                return "3.0"
            return "0.0"

        res.query.side_effect = _side
        p = psu.measure_power()
        assert abs(p - 36.0) < 1e-6

    def test_set_voltage_command(self):
        psu, res = _make_connected(PowerSupply)
        psu.set_voltage(15.0)
        res.write.assert_called_with("VOLTage 15")

    def test_set_voltage_fractional(self):
        psu, res = _make_connected(PowerSupply)
        psu.set_voltage(12.345)
        res.write.assert_called_with("VOLTage 12.345")

    def test_set_current_command(self):
        psu, res = _make_connected(PowerSupply)
        psu.set_current(2.5)
        res.write.assert_called_with("CURRent 2.5")

    def test_output_on_command(self):
        psu, res = _make_connected(PowerSupply)
        psu.output_on()
        res.write.assert_called_with("OUTPut ON")

    def test_output_off_command(self):
        psu, res = _make_connected(PowerSupply)
        psu.output_off()
        res.write.assert_called_with("OUTPut OFF")

    def test_identify_sends_idn(self):
        psu, res = _make_connected(PowerSupply)
        res.query.return_value = "KEYSIGHT,E36312A,SN001,FW1.0"
        result = psu.identify()
        res.query.assert_called_with("*IDN?")
        assert "KEYSIGHT" in result


# ======================================================================
# ZP — TDK-Lambda Z+/Z profile
# ======================================================================

class TestTDKLambdaZPlus:

    def test_measure_voltage_command(self):
        psu, res = _make_connected(TDKLambdaZPlus)
        res.query.return_value = "20.000"
        v = psu.measure_voltage()
        res.query.assert_called_with("MV?")
        assert abs(v - 20.0) < 1e-6

    def test_measure_current_command(self):
        psu, res = _make_connected(TDKLambdaZPlus)
        res.query.return_value = "5.500"
        i = psu.measure_current()
        res.query.assert_called_with("MC?")
        assert abs(i - 5.5) < 1e-6

    def test_measure_power_command(self):
        psu, res = _make_connected(TDKLambdaZPlus)
        res.query.return_value = "110.000"
        p = psu.measure_power()
        res.query.assert_called_with("MP?")
        assert abs(p - 110.0) < 1e-6

    def test_measure_power_vi_fallback(self):
        """MP? not implemented on all firmware — fall back to V*I."""
        psu, res = _make_connected(TDKLambdaZPlus)

        def _side(cmd):
            if cmd == "MP?":
                raise pyvisa.Error("not supported")
            if cmd == "MV?":
                return "20.0"
            if cmd == "MC?":
                return "5.0"
            return "0.0"

        res.query.side_effect = _side
        p = psu.measure_power()
        assert abs(p - 100.0) < 1e-6

    def test_set_voltage_command(self):
        psu, res = _make_connected(TDKLambdaZPlus)
        psu.set_voltage(18.0)
        res.write.assert_called_with("PV 18")

    def test_set_voltage_fractional(self):
        psu, res = _make_connected(TDKLambdaZPlus)
        psu.set_voltage(12.345)
        res.write.assert_called_with("PV 12.345")

    def test_set_current_command(self):
        psu, res = _make_connected(TDKLambdaZPlus)
        psu.set_current(3.0)
        res.write.assert_called_with("PC 3")

    def test_output_on_command(self):
        psu, res = _make_connected(TDKLambdaZPlus)
        psu.output_on()
        res.write.assert_called_with("OUT 1")

    def test_output_off_command(self):
        psu, res = _make_connected(TDKLambdaZPlus)
        psu.output_off()
        res.write.assert_called_with("OUT 0")

    def test_identify_still_uses_idn(self):
        """*IDN? is IEEE 488.2 standard — Z+ supports it."""
        psu, res = _make_connected(TDKLambdaZPlus)
        res.query.return_value = "TDK-LAMBDA,Z20-10,635I288-0027,3.005"
        result = psu.identify()
        res.query.assert_called_with("*IDN?")
        assert "TDK-LAMBDA" in result

    def test_commands_differ_from_standard_scpi(self):
        """Guard: Z+ CMD_* must not equal standard SCPI CMD_*."""
        assert TDKLambdaZPlus.CMD_MEASURE_VOLTAGE != PowerSupply.CMD_MEASURE_VOLTAGE
        assert TDKLambdaZPlus.CMD_MEASURE_CURRENT != PowerSupply.CMD_MEASURE_CURRENT
        assert TDKLambdaZPlus.CMD_SET_VOLTAGE != PowerSupply.CMD_SET_VOLTAGE
        assert TDKLambdaZPlus.CMD_SET_CURRENT != PowerSupply.CMD_SET_CURRENT
        assert TDKLambdaZPlus.CMD_OUTPUT_ON != PowerSupply.CMD_OUTPUT_ON
        assert TDKLambdaZPlus.CMD_OUTPUT_OFF != PowerSupply.CMD_OUTPUT_OFF


# ======================================================================
# LD — ElectronicLoad (standard SCPI)
# ======================================================================

class TestElectronicLoadCommunication:

    def test_measure_voltage_command(self):
        load, res = _make_connected(ElectronicLoad)
        res.query.return_value = "11.980"
        v = load.measure_voltage()
        res.query.assert_called_with("MEASure:VOLTage?")
        assert abs(v - 11.98) < 1e-6

    def test_measure_current_command(self):
        load, res = _make_connected(ElectronicLoad)
        res.query.return_value = "2.290"
        i = load.measure_current()
        res.query.assert_called_with("MEASure:CURRent?")
        assert abs(i - 2.29) < 1e-6

    def test_set_mode_cc_command(self):
        load, res = _make_connected(ElectronicLoad)
        load.set_mode("CC")
        res.write.assert_called_with("FUNCtion CC")

    def test_set_mode_cv_command(self):
        load, res = _make_connected(ElectronicLoad)
        load.set_mode("CV")
        res.write.assert_called_with("FUNCtion CV")

    def test_set_mode_cr_command(self):
        load, res = _make_connected(ElectronicLoad)
        load.set_mode("CR")
        res.write.assert_called_with("FUNCtion CR")

    def test_set_mode_cp_command(self):
        load, res = _make_connected(ElectronicLoad)
        load.set_mode("CP")
        res.write.assert_called_with("FUNCtion CP")

    def test_set_value_cc_sends_current_cmd(self):
        load, res = _make_connected(ElectronicLoad)
        load.set_value("CC", 4.0)
        res.write.assert_called_with("CURRent 4")

    def test_set_value_cv_sends_voltage_cmd(self):
        load, res = _make_connected(ElectronicLoad)
        load.set_value("CV", 12.0)
        res.write.assert_called_with("VOLTage 12")

    def test_input_on_command(self):
        load, res = _make_connected(ElectronicLoad)
        load.input_on()
        res.write.assert_called_with("INPut ON")

    def test_input_off_command(self):
        load, res = _make_connected(ElectronicLoad)
        load.input_off()
        res.write.assert_called_with("INPut OFF")


# ======================================================================
# ER — Error handling
# ======================================================================

class TestCommunicationErrors:

    def test_visa_timeout_raises_communication_error_with_command(self):
        psu, res = _make_connected(PowerSupply)
        res.query.side_effect = pyvisa.Error("VI_ERROR_TMO: timeout")
        with pytest.raises(CommunicationError, match=r"MEASure:VOLTage\[:DC\]\?"):
            psu.measure_voltage()

    def test_zplus_visa_timeout_raises_communication_error_with_command(self):
        psu, res = _make_connected(TDKLambdaZPlus)
        res.query.side_effect = pyvisa.Error("VI_ERROR_TMO: timeout")
        with pytest.raises(CommunicationError, match="MV?"):
            psu.measure_voltage()

    def test_bad_float_response_raises_communication_error(self):
        psu, res = _make_connected(PowerSupply)
        res.query.return_value = "ERR"
        with pytest.raises(CommunicationError, match="Could not parse float"):
            psu.measure_voltage()

    def test_write_visa_error_raises_communication_error(self):
        psu, res = _make_connected(PowerSupply)
        res.write.side_effect = pyvisa.Error("write failed")
        with pytest.raises(CommunicationError, match="Write failed"):
            psu.set_voltage(12.0)

    def test_load_query_visa_error_raises_communication_error(self):
        load, res = _make_connected(ElectronicLoad)
        res.query.side_effect = pyvisa.Error("timeout")
        with pytest.raises(CommunicationError):
            load.measure_voltage()

    def test_query_before_connect_raises_communication_error(self):
        psu = PowerSupply("USB0::MOCK::INSTR")
        with pytest.raises(CommunicationError, match="Not connected"):
            psu.measure_voltage()

    def test_write_before_connect_raises_communication_error(self):
        psu = PowerSupply("USB0::MOCK::INSTR")
        with pytest.raises(CommunicationError, match="Not connected"):
            psu.set_voltage(12.0)

    def test_connect_visa_error_raises_communication_error(self):
        mock_rm = MagicMock()
        mock_rm.open_resource.side_effect = pyvisa.Error("resource not found")
        with patch("pyvisa.ResourceManager", return_value=mock_rm):
            psu = PowerSupply("BADRESOURCE")
            with pytest.raises(CommunicationError, match="Failed to connect"):
                psu.connect()


# ======================================================================
# PR — Connection preamble
# ======================================================================

class TestConnectionPreamble:

    def test_preamble_is_written_on_connect(self):
        psu, res = _make_connected(PowerSupply, connect_preamble="ADR 10")
        # preamble write happens inside connect(); check the write calls
        write_calls = [c.args[0] for c in res.write.call_args_list]
        assert "ADR 10" in write_calls

    def test_preamble_read_response_is_consumed(self):
        """After writing the preamble, one read() is called to consume the ack."""
        psu, res = _make_connected(PowerSupply, connect_preamble="ADR 10")
        res.read.assert_called()

    def test_empty_preamble_does_not_write(self):
        """No extra write when preamble is blank."""
        psu, res = _make_connected(PowerSupply, connect_preamble="")
        # Any write calls here would be from something else, but at connect
        # time with no preamble, write should not have been called at all.
        res.write.assert_not_called()

    def test_preamble_read_error_does_not_abort_connect(self):
        """A timeout reading the preamble ack is silently ignored.

        ASRL resources now use _SerialAdapter (pyserial), so we mock
        serial.Serial rather than pyvisa.ResourceManager.
        """
        mock_ser = MagicMock()
        # read_until returns b'' → no ack — must not raise
        mock_ser.read_until.return_value = b""
        mock_ser.in_waiting = 0

        with patch("serial.Serial", return_value=mock_ser):
            psu = PowerSupply("ASRL4::INSTR", connect_preamble="ADR 10")
            psu.connect()  # must not raise

        assert psu.is_connected


# ======================================================================
# RG — Profile registry
# ======================================================================

class TestProfileRegistry:

    def test_standard_scpi_in_registry(self):
        assert "standard_scpi" in PSU_PROFILES

    def test_tdklambda_zplus_in_registry(self):
        assert "tdklambda_zplus" in PSU_PROFILES

    def test_standard_scpi_maps_to_power_supply_class(self):
        assert PSU_PROFILES["standard_scpi"] is PowerSupply

    def test_tdklambda_zplus_maps_to_tdklambda_class(self):
        assert PSU_PROFILES["tdklambda_zplus"] is TDKLambdaZPlus

    def test_all_profile_classes_are_power_supply_subclasses(self):
        for key, cls in PSU_PROFILES.items():
            assert issubclass(cls, PowerSupply), (
                f"Profile '{key}' class {cls} must be a PowerSupply subclass"
            )

    def test_profile_instances_are_not_connected_by_default(self):
        for key, cls in PSU_PROFILES.items():
            inst = cls("USB0::MOCK::INSTR")
            assert not inst.is_connected, f"Profile '{key}': new instance should not be connected"


# ======================================================================
# PO — PollWorker integration
# ======================================================================

class TestPollerDelegation:
    """Verify PollWorker calls the right measurement methods on instruments."""

    def test_poller_calls_measure_voltage_on_psu(self, qtbot):
        from src.core.poller import PollWorker

        psu = MagicMock()
        psu.measure_voltage.return_value = 12.0
        psu.measure_current.return_value = 2.0
        psu.measure_power.return_value = 24.0

        worker = PollWorker(psus=[psu], loads=[], poll_rate_hz=20.0)
        worker.start()
        qtbot.waitUntil(lambda: psu.measure_voltage.call_count >= 3, timeout=2000)
        worker.stop_polling()
        worker.wait(2000)

        psu.measure_voltage.assert_called()
        psu.measure_current.assert_called()
        psu.measure_power.assert_called()

    def test_poller_calls_measure_on_load(self, qtbot):
        from src.core.poller import PollWorker

        psu = MagicMock()
        psu.measure_voltage.return_value = 12.0
        psu.measure_current.return_value = 2.0
        psu.measure_power.return_value = 24.0

        load = MagicMock()
        load.measure_voltage.return_value = 11.9
        load.measure_current.return_value = 1.95

        worker = PollWorker(psus=[psu], loads=[load], poll_rate_hz=20.0)
        worker.start()
        qtbot.waitUntil(lambda: load.measure_voltage.call_count >= 3, timeout=2000)
        worker.stop_polling()
        worker.wait(2000)

        load.measure_voltage.assert_called()
        load.measure_current.assert_called()

    def test_poller_emits_error_on_psu_comm_failure(self, qtbot):
        from src.core.poller import PollWorker

        failing_psu = MagicMock()
        failing_psu.measure_voltage.side_effect = CommunicationError("VI_ERROR_TMO")
        failing_psu.measure_current.side_effect = CommunicationError("VI_ERROR_TMO")
        failing_psu.measure_power.side_effect = CommunicationError("VI_ERROR_TMO")

        worker = PollWorker(psus=[failing_psu], loads=[], poll_rate_hz=20.0)
        errors = []
        worker.communication_error.connect(errors.append)
        worker.start()
        qtbot.waitUntil(lambda: len(errors) >= 1, timeout=2000)
        worker.stop_polling()
        worker.wait(2000)

        assert any("PSU" in e for e in errors)

    def test_poller_emits_error_on_load_comm_failure(self, qtbot):
        from src.core.poller import PollWorker

        psu = MagicMock()
        psu.measure_voltage.return_value = 12.0
        psu.measure_current.return_value = 2.0
        psu.measure_power.return_value = 24.0

        failing_load = MagicMock()
        failing_load.measure_voltage.side_effect = CommunicationError("VI_ERROR_TMO")
        failing_load.measure_current.side_effect = CommunicationError("VI_ERROR_TMO")

        worker = PollWorker(psus=[psu], loads=[failing_load], poll_rate_hz=20.0)
        errors = []
        worker.communication_error.connect(errors.append)
        worker.start()
        qtbot.waitUntil(lambda: len(errors) >= 1, timeout=2000)
        worker.stop_polling()
        worker.wait(2000)

        assert any("Load" in e or "LOAD" in e for e in errors)

    def test_poller_telemetry_values_match_instrument_readings(self, qtbot):
        """Values in TelemetrySample must match what the instrument returned."""
        from src.core.models import TelemetrySample
        from src.core.poller import PollWorker

        psu = MagicMock()
        psu.measure_voltage.return_value = 19.75
        psu.measure_current.return_value = 4.20
        psu.measure_power.return_value = 83.0

        worker = PollWorker(psus=[psu], loads=[], poll_rate_hz=20.0)
        samples: list[TelemetrySample] = []
        worker.telemetry_sample.connect(samples.append)
        worker.start()
        qtbot.waitUntil(lambda: len(samples) >= 3, timeout=2000)
        worker.stop_polling()
        worker.wait(2000)

        voltages = [s.value for s in samples if s.parameter == "voltage" and s.source == "PSU"]
        assert voltages and all(abs(v - 19.75) < 1e-6 for v in voltages)
