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
from src.instruments.electronic_load import (
    LOAD_PROFILES,
    ElectronicLoad,
    ProdigitBothChannelsLoad,
    ProdigitCh1Load,
    ProdigitCh2Load,
    ProdigitDualChannelLoad,
    ShortScpiElectronicLoad,
)
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
        res.query.assert_called_with("MEASure:VOLTage?")
        assert abs(v - 12.5) < 1e-6

    def test_measure_current_command(self):
        psu, res = _make_connected(PowerSupply)
        res.query.return_value = "3.000"
        i = psu.measure_current()
        res.query.assert_called_with("MEASure:CURRent?")
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
# SS — ShortScpiElectronicLoad profile
# ======================================================================

class TestShortScpiLoad:

    def test_measure_voltage_command(self):
        load, res = _make_connected(ShortScpiElectronicLoad)
        res.query.return_value = "11.980"
        v = load.measure_voltage()
        res.query.assert_called_with("MEAS:VOLT?")
        assert abs(v - 11.98) < 1e-6

    def test_measure_current_command(self):
        load, res = _make_connected(ShortScpiElectronicLoad)
        res.query.return_value = "2.290"
        i = load.measure_current()
        res.query.assert_called_with("MEAS:CURR?")
        assert abs(i - 2.29) < 1e-6

    def test_set_mode_command(self):
        load, res = _make_connected(ShortScpiElectronicLoad)
        load.set_mode("CC")
        res.write.assert_called_with("FUNC CC")

    def test_input_on_command(self):
        load, res = _make_connected(ShortScpiElectronicLoad)
        load.input_on()
        res.write.assert_called_with("INP ON")

    def test_input_off_command(self):
        load, res = _make_connected(ShortScpiElectronicLoad)
        load.input_off()
        res.write.assert_called_with("INP OFF")

    def test_commands_differ_from_standard_scpi(self):
        assert ShortScpiElectronicLoad.CMD_MEASURE_VOLTAGE != ElectronicLoad.CMD_MEASURE_VOLTAGE
        assert ShortScpiElectronicLoad.CMD_MEASURE_CURRENT != ElectronicLoad.CMD_MEASURE_CURRENT
        assert ShortScpiElectronicLoad.CMD_SET_MODE != ElectronicLoad.CMD_SET_MODE


# ======================================================================
# LR — Load profile registry
# ======================================================================

class TestLoadProfileRegistry:

    def test_load_profile_registry_contains_all_profiles(self):
        assert "standard_scpi" in LOAD_PROFILES
        assert "short_scpi" in LOAD_PROFILES
        assert LOAD_PROFILES["standard_scpi"] is ElectronicLoad
        assert LOAD_PROFILES["short_scpi"] is ShortScpiElectronicLoad
        for key, cls in LOAD_PROFILES.items():
            assert issubclass(cls, ElectronicLoad), f"Profile '{key}' must subclass ElectronicLoad"


# ======================================================================
# ER — Error handling
# ======================================================================

class TestCommunicationErrors:

    def test_visa_timeout_raises_communication_error_with_command(self):
        psu, res = _make_connected(PowerSupply)
        res.query.side_effect = pyvisa.Error("VI_ERROR_TMO: timeout")
        with pytest.raises(CommunicationError, match=r"MEASure:VOLTage\?"):
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
        # read(1) returns b'' → no ack (instrument silent) — must not raise
        mock_ser.read.return_value = b""
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


# ======================================================================
# PD — Prodigit 3330F dual-channel load (3302G mainframe)
# ======================================================================

class TestProdigitDualChannelLoad:
    """Verify the Prodigit 3330F select-then-command protocol.

    Protocol: send CHAN{n} to select the channel, then send bare commands
    (MODE CC, CC 5.0, VOLT?, etc.) without any per-command prefix.
    """

    # Helper — extract write call args list
    @staticmethod
    def _writes(res) -> list[str]:
        return [c.args[0] for c in res.write.call_args_list]

    # ------------------------------------------------------------------
    # Channel selection appears before every operation
    # ------------------------------------------------------------------

    def test_ch1_set_mode_sends_chan1_select_first(self):
        load, res = _make_connected(ProdigitCh1Load)
        load.set_mode("CC")
        writes = self._writes(res)
        assert writes[0] == "CHAN1", f"Expected CHAN1 as first write; got {writes}"

    def test_ch2_set_mode_sends_chan2_select_first(self):
        load, res = _make_connected(ProdigitCh2Load)
        load.set_mode("CC")
        writes = self._writes(res)
        assert writes[0] == "CHAN2"

    def test_ch1_measure_voltage_selects_channel_first(self):
        load, res = _make_connected(ProdigitCh1Load)
        res.query.return_value = "12.0"
        load.measure_voltage()
        assert self._writes(res)[-1] == "CHAN1"

    def test_ch2_measure_voltage_selects_channel_first(self):
        load, res = _make_connected(ProdigitCh2Load)
        res.query.return_value = "12.0"
        load.measure_voltage()
        assert self._writes(res)[-1] == "CHAN2"

    # ------------------------------------------------------------------
    # Mode command — bare "MODE {x}", NOT "CHAN1:MODE {x}"
    # ------------------------------------------------------------------

    def test_ch1_set_mode_cc_sends_mode_cc(self):
        load, res = _make_connected(ProdigitCh1Load)
        load.set_mode("CC")
        writes = self._writes(res)
        assert "MODE CC" in writes

    def test_ch1_set_mode_cv(self):
        load, res = _make_connected(ProdigitCh1Load)
        load.set_mode("CV")
        assert "MODE CV" in self._writes(res)

    def test_ch1_set_mode_cr(self):
        load, res = _make_connected(ProdigitCh1Load)
        load.set_mode("CR")
        assert "MODE CR" in self._writes(res)

    def test_ch1_set_mode_cp(self):
        load, res = _make_connected(ProdigitCh1Load)
        load.set_mode("CP")
        assert "MODE CP" in self._writes(res)

    def test_ch2_set_mode_cc_sends_mode_cc(self):
        load, res = _make_connected(ProdigitCh2Load)
        load.set_mode("CC")
        assert "MODE CC" in self._writes(res)

    def test_set_mode_sends_cc_reset_before_mode_change(self):
        """Full safe sequence on a mode transition: LOAD OFF → CC 0.0 → MODE {x}."""
        load, res = _make_connected(ProdigitCh1Load)
        load.set_mode("CV")
        writes = self._writes(res)
        load_off_idx = writes.index("LOAD OFF")
        cc_idx       = writes.index("CC 0.0")
        mode_idx     = writes.index("MODE CV")
        assert load_off_idx < cc_idx < mode_idx, (
            f"Expected LOAD OFF < CC 0.0 < MODE CV; got {writes}"
        )

    def test_set_mode_same_mode_no_reset(self):
        """Calling set_mode twice with the same mode skips the full reset sequence."""
        load, res = _make_connected(ProdigitCh1Load)
        load.set_mode("CC")
        res.write.reset_mock()
        load.set_mode("CC")                   # second call — same mode
        writes = self._writes(res)
        assert "LOAD OFF" not in writes, "LOAD OFF must NOT be sent when mode unchanged"
        assert "CC 0.0"   not in writes, "CC 0.0 must NOT be sent when mode unchanged"
        assert "MODE CC"  not in writes, "MODE CC must NOT be re-sent when mode unchanged"

    def test_set_mode_case_insensitive(self):
        load, res = _make_connected(ProdigitCh1Load)
        load.set_mode("cc")
        assert "MODE CC" in self._writes(res)

    def test_set_mode_invalid_raises_value_error(self):
        load, res = _make_connected(ProdigitCh1Load)
        with pytest.raises(ValueError):
            load.set_mode("XX")

    # ------------------------------------------------------------------
    # Setpoint — bare "{MODE} {value}" (e.g. "CC 5", "CV 12")
    # ------------------------------------------------------------------

    def test_ch1_set_value_cc(self):
        load, res = _make_connected(ProdigitCh1Load)
        load.set_value("CC", 5.0)
        # Last write must be the value command
        res.write.assert_called_with("CC 5")

    def test_ch1_set_value_cc_fractional(self):
        load, res = _make_connected(ProdigitCh1Load)
        load.set_value("CC", 3.75)
        res.write.assert_called_with("CC 3.75")

    def test_ch1_set_value_cv(self):
        load, res = _make_connected(ProdigitCh1Load)
        load.set_value("CV", 12.0)
        res.write.assert_called_with("CV 12")

    def test_ch1_set_value_cr(self):
        load, res = _make_connected(ProdigitCh1Load)
        load.set_value("CR", 50.0)
        res.write.assert_called_with("CR 50")

    def test_ch1_set_value_cp(self):
        load, res = _make_connected(ProdigitCh1Load)
        load.set_value("CP", 25.0)
        res.write.assert_called_with("CP 25")

    def test_ch2_set_value_cc(self):
        """CH2 setpoint still uses bare "CC {v}", but CHAN2 was selected first."""
        load, res = _make_connected(ProdigitCh2Load)
        load.set_value("CC", 2.0)
        res.write.assert_called_with("CC 2")
        assert "CHAN2" in self._writes(res)

    def test_set_value_invalid_mode_raises_value_error(self):
        load, res = _make_connected(ProdigitCh1Load)
        with pytest.raises(ValueError):
            load.set_value("XX", 1.0)

    # ------------------------------------------------------------------
    # Mode query — bare "MODE?", not "CHAN1:MODE?"
    # ------------------------------------------------------------------

    def test_ch1_get_mode_queries_mode(self):
        load, res = _make_connected(ProdigitCh1Load)
        res.query.return_value = "CC"
        mode = load.get_mode()
        res.query.assert_called_with("MODE?")
        assert mode == "CC"

    def test_ch2_get_mode_queries_mode(self):
        load, res = _make_connected(ProdigitCh2Load)
        res.query.return_value = "CV"
        mode = load.get_mode()
        res.query.assert_called_with("MODE?")
        assert mode == "CV"

    # ------------------------------------------------------------------
    # Measurement — bare "VOLT?" / "CURR?", not "CHAN1:MEAS:VOLT?"
    # ------------------------------------------------------------------

    def test_ch1_measure_voltage_sends_volt_query(self):
        load, res = _make_connected(ProdigitCh1Load)
        res.query.return_value = "11.980"
        v = load.measure_voltage()
        res.query.assert_called_with("VOLT?")
        assert abs(v - 11.98) < 1e-6

    def test_ch1_measure_current_sends_curr_query(self):
        load, res = _make_connected(ProdigitCh1Load)
        res.query.return_value = "3.500"
        i = load.measure_current()
        res.query.assert_called_with("CURR?")
        assert abs(i - 3.5) < 1e-6

    def test_ch2_measure_voltage_sends_volt_query(self):
        """CH2 also uses bare VOLT? — channel select distinguishes it."""
        load, res = _make_connected(ProdigitCh2Load)
        res.query.return_value = "5.000"
        load.measure_voltage()
        res.query.assert_called_with("VOLT?")

    def test_ch2_measure_current_sends_curr_query(self):
        load, res = _make_connected(ProdigitCh2Load)
        res.query.return_value = "1.000"
        load.measure_current()
        res.query.assert_called_with("CURR?")

    # ------------------------------------------------------------------
    # Input state — "LOAD ON" / "LOAD OFF" after channel select
    # ------------------------------------------------------------------

    def test_ch1_input_on(self):
        load, res = _make_connected(ProdigitCh1Load)
        load.input_on()
        res.write.assert_called_with("LOAD ON")
        assert "CHAN1" in self._writes(res)

    def test_ch1_input_off(self):
        load, res = _make_connected(ProdigitCh1Load)
        load.input_off()
        res.write.assert_called_with("LOAD OFF")

    def test_ch2_input_on(self):
        load, res = _make_connected(ProdigitCh2Load)
        load.input_on()
        res.write.assert_called_with("LOAD ON")
        assert "CHAN2" in self._writes(res)

    def test_ch2_input_off(self):
        load, res = _make_connected(ProdigitCh2Load)
        load.input_off()
        res.write.assert_called_with("LOAD OFF")
        assert "CHAN2" in self._writes(res)

    # ------------------------------------------------------------------
    # Two instances use different channel selects for the same commands
    # ------------------------------------------------------------------

    def test_channels_select_independently(self):
        """CH1 and CH2 instances send CHAN1 / CHAN2 respectively."""
        ch1, res1 = _make_connected(ProdigitCh1Load)
        ch2, res2 = _make_connected(ProdigitCh2Load)
        ch1.set_mode("CC")
        ch2.set_mode("CV")
        assert "CHAN1" in self._writes(res1)
        assert "CHAN2" in self._writes(res2)
        assert "MODE CC" in self._writes(res1)
        assert "MODE CV" in self._writes(res2)

    # ------------------------------------------------------------------
    # Class hierarchy and profile registry
    # ------------------------------------------------------------------

    def test_both_channels_are_electronic_load_subclasses(self):
        assert issubclass(ProdigitCh1Load, ElectronicLoad)
        assert issubclass(ProdigitCh2Load, ElectronicLoad)
        assert issubclass(ProdigitCh1Load, ProdigitDualChannelLoad)
        assert issubclass(ProdigitCh2Load, ProdigitDualChannelLoad)

    def test_profile_registry_contains_both_channels(self):
        assert "prodigit_3330f_ch1"  in LOAD_PROFILES
        assert "prodigit_3330f_ch2"  in LOAD_PROFILES
        assert "prodigit_3330f_both" in LOAD_PROFILES
        assert LOAD_PROFILES["prodigit_3330f_ch1"]  is ProdigitCh1Load
        assert LOAD_PROFILES["prodigit_3330f_ch2"]  is ProdigitCh2Load
        assert LOAD_PROFILES["prodigit_3330f_both"] is ProdigitBothChannelsLoad

    def test_all_profiles_are_electronic_load_subclasses(self):
        for key, cls in LOAD_PROFILES.items():
            assert issubclass(cls, ElectronicLoad), (
                f"Profile '{key}' must subclass ElectronicLoad"
            )

    def test_remote_enable_inherited_by_prodigit(self):
        """Prodigit channels inherit remote-enable support from ElectronicLoad."""
        load, res = _make_connected(ProdigitCh1Load, remote_enable_command="SYST:REM")
        assert "SYST:REM" in self._writes(res)


# ======================================================================
# RE — Remote enable command
# ======================================================================

class TestRemoteEnable:

    def test_remote_enable_sent_on_connect(self):
        """When remote_enable_command is set, it is written once after connect."""
        load, res = _make_connected(ElectronicLoad, remote_enable_command="SYST:REM")
        write_calls = [c.args[0] for c in res.write.call_args_list]
        assert "SYST:REM" in write_calls

    def test_remote_enable_not_sent_when_empty(self):
        """When remote_enable_command is blank, no extra write is performed."""
        load, res = _make_connected(ElectronicLoad, remote_enable_command="")
        # No write should have occurred (no preamble either)
        res.write.assert_not_called()

    def test_remote_enable_failure_does_not_abort_connect(self):
        """A CommunicationError from the remote-enable write is silenced."""
        import pyvisa
        mock_resource = MagicMock()
        mock_resource.timeout = 5000
        mock_resource.query.return_value = "0.0"
        # First write (remote enable) raises; second+ writes must still work
        mock_resource.write.side_effect = [
            pyvisa.Error("not supported"),
            None,
        ]
        mock_resource.close.return_value = None

        mock_rm = MagicMock()
        mock_rm.open_resource.return_value = mock_resource

        with patch("pyvisa.ResourceManager", return_value=mock_rm):
            load = ElectronicLoad("USB0::MOCK::INSTR", remote_enable_command="REMOTE")
            load.connect()  # must not raise

        assert load.is_connected

    def test_query_error_returns_empty_when_no_cmd(self):
        """query_error() returns '' when CMD_QUERY_ERROR is blank."""
        load, res = _make_connected(ElectronicLoad)
        result = load.query_error()
        assert result == ""
        res.query.assert_not_called()

    def test_short_scpi_inherits_remote_enable_support(self):
        """ShortScpiElectronicLoad also accepts and sends remote_enable_command."""
        load, res = _make_connected(
            ShortScpiElectronicLoad, remote_enable_command="REMOTE"
        )
        write_calls = [c.args[0] for c in res.write.call_args_list]
        assert "REMOTE" in write_calls


# ======================================================================
# NR — Prodigit numeric MODE? response handling
# ======================================================================

class TestProdigitNumericModeResponse:
    """Verify that get_mode() maps numeric responses to mode abbreviations."""

    @staticmethod
    def _writes(res) -> list[str]:
        return [c.args[0] for c in res.write.call_args_list]

    def test_numeric_0_returns_cc(self):
        load, res = _make_connected(ProdigitCh1Load)
        res.query.return_value = "0"
        assert load.get_mode() == "CC"

    def test_numeric_1_returns_cr(self):
        load, res = _make_connected(ProdigitCh1Load)
        res.query.return_value = "1"
        assert load.get_mode() == "CR"

    def test_numeric_2_returns_cv(self):
        load, res = _make_connected(ProdigitCh1Load)
        res.query.return_value = "2"
        assert load.get_mode() == "CV"

    def test_numeric_3_returns_cp(self):
        load, res = _make_connected(ProdigitCh1Load)
        res.query.return_value = "3"
        assert load.get_mode() == "CP"

    def test_string_cc_passthrough(self):
        """String 'CC' response is returned unchanged."""
        load, res = _make_connected(ProdigitCh1Load)
        res.query.return_value = "CC"
        assert load.get_mode() == "CC"

    def test_string_cv_passthrough(self):
        load, res = _make_connected(ProdigitCh1Load)
        res.query.return_value = "CV"
        assert load.get_mode() == "CV"

    def test_get_mode_still_sends_chan1(self):
        """get_mode() must select the channel before querying."""
        load, res = _make_connected(ProdigitCh1Load)
        res.query.return_value = "CC"
        load.get_mode()
        assert "CHAN1" in self._writes(res)

    def test_get_mode_still_sends_chan2(self):
        load, res = _make_connected(ProdigitCh2Load)
        res.query.return_value = "0"
        load.get_mode()
        assert "CHAN2" in self._writes(res)


# ======================================================================
# QS — Prodigit query_load_state
# ======================================================================

class TestProdigitQueryLoadState:

    @staticmethod
    def _writes(res) -> list[str]:
        return [c.args[0] for c in res.write.call_args_list]

    def test_query_load_state_sends_load_query(self):
        load, res = _make_connected(ProdigitCh1Load)
        res.query.return_value = "ON"
        result = load.query_load_state()
        res.query.assert_called_with("LOAD?")
        assert result == "ON"

    def test_query_load_state_selects_channel_first(self):
        load, res = _make_connected(ProdigitCh2Load)
        res.query.return_value = "OFF"
        load.query_load_state()
        assert "CHAN2" in self._writes(res)

    def test_query_load_state_returns_empty_on_comm_error(self):
        """query_load_state() swallows CommunicationError and returns ''."""
        import pyvisa
        load, res = _make_connected(ProdigitCh1Load)
        res.query.side_effect = pyvisa.Error("timeout")
        result = load.query_load_state()
        assert result == ""

    def test_query_load_state_never_raises(self):
        """Verify no exception propagates even for unexpected errors."""
        load, res = _make_connected(ProdigitCh1Load)
        res.query.side_effect = RuntimeError("unexpected")
        # Should raise (RuntimeError is not CommunicationError) — this documents
        # that only CommunicationError is swallowed, not arbitrary exceptions.
        with pytest.raises(RuntimeError):
            load.query_load_state()


# ======================================================================
# BC — ProdigitBothChannelsLoad (both channels, lock-step)
# ======================================================================

class TestProdigitBothChannels:
    """Verify that ProdigitBothChannelsLoad applies commands to both CH1 and CH2."""

    @pytest.fixture(autouse=True)
    def _no_sleep(self, monkeypatch):
        """Skip real hardware delays so tests run in milliseconds."""
        monkeypatch.setattr("src.instruments.electronic_load.time.sleep", lambda _: None)

    @staticmethod
    def _writes(res) -> list[str]:
        return [c.args[0] for c in res.write.call_args_list]

    # ------------------------------------------------------------------
    # set_mode — applies to both channels with full safe sequence
    # ------------------------------------------------------------------

    def test_set_mode_sends_to_ch1_and_ch2(self):
        """Mode-change sequence must appear for both CHAN1 and CHAN2."""
        load, res = _make_connected(ProdigitBothChannelsLoad)
        load.set_mode("CC")
        writes = self._writes(res)
        assert "CHAN1" in writes
        assert "CHAN2" in writes
        assert "MODE CC" in writes
        # MODE CC should appear twice (once per channel)
        assert writes.count("MODE CC") == 2

    def test_set_mode_load_off_before_cc_reset_ch1(self):
        """LOAD OFF → CC 0.0 → MODE ordering must hold for CH1 block."""
        load, res = _make_connected(ProdigitBothChannelsLoad)
        load.set_mode("CV")
        writes = self._writes(res)
        # CH1 block begins at index of first CHAN1
        chan1_idx     = writes.index("CHAN1")
        load_off_idx  = writes.index("LOAD OFF", chan1_idx)
        cc_idx        = writes.index("CC 0.0",   chan1_idx)
        mode_idx      = writes.index("MODE CV",  chan1_idx)
        assert chan1_idx < load_off_idx < cc_idx < mode_idx

    def test_set_mode_load_off_before_cc_reset_ch2(self):
        """LOAD OFF → CC 0.0 → MODE ordering must also hold for CH2 block."""
        load, res = _make_connected(ProdigitBothChannelsLoad)
        load.set_mode("CV")
        writes = self._writes(res)
        # CH2 block begins after CH2 first appears
        chan2_idx    = writes.index("CHAN2")
        # Find the LOAD OFF that belongs to the CH2 block
        load_off_2   = writes.index("LOAD OFF", chan2_idx)
        cc_2         = writes.index("CC 0.0",   chan2_idx)
        # Second "MODE CV" occurrence belongs to CH2
        mode_cv_all  = [i for i, w in enumerate(writes) if w == "MODE CV"]
        assert len(mode_cv_all) == 2
        mode_2 = mode_cv_all[1]
        assert chan2_idx < load_off_2 < cc_2 < mode_2

    def test_set_mode_same_mode_no_reset_for_either_channel(self):
        """Second set_mode with same mode sends no LOAD OFF or CC 0.0."""
        load, res = _make_connected(ProdigitBothChannelsLoad)
        load.set_mode("CC")
        res.write.reset_mock()
        load.set_mode("CC")           # second call — same mode
        writes = self._writes(res)
        assert "LOAD OFF" not in writes
        assert "CC 0.0"   not in writes
        assert "MODE CC"  not in writes
        # Only channel-select writes remain
        assert "CHAN1" in writes
        assert "CHAN2" in writes

    def test_set_mode_invalid_raises(self):
        load, res = _make_connected(ProdigitBothChannelsLoad)
        with pytest.raises(ValueError):
            load.set_mode("XX")

    # ------------------------------------------------------------------
    # set_value — writes setpoint to both channels
    # ------------------------------------------------------------------

    def test_set_value_cc_writes_to_both_channels(self):
        load, res = _make_connected(ProdigitBothChannelsLoad)
        load.set_value("CC", 5.0)
        writes = self._writes(res)
        # Both channel selects must appear
        assert "CHAN1" in writes
        assert "CHAN2" in writes
        # Setpoint written to both (CC 5 appears twice)
        assert writes.count("CC 5") == 2

    def test_set_value_cv_writes_to_both_channels(self):
        load, res = _make_connected(ProdigitBothChannelsLoad)
        load.set_value("CV", 12.0)
        writes = self._writes(res)
        assert writes.count("CV 12") == 2

    def test_set_value_chan1_value_before_chan2_value(self):
        """CH1 setpoint must be written before CH2 setpoint."""
        load, res = _make_connected(ProdigitBothChannelsLoad)
        load.set_value("CC", 3.0)
        writes = self._writes(res)
        cc3_indices = [i for i, w in enumerate(writes) if w == "CC 3"]
        assert len(cc3_indices) == 2
        # Find the CHAN1 and CHAN2 immediately before each value write
        chan1_before = max(
            i for i, w in enumerate(writes) if w == "CHAN1" and i < cc3_indices[0]
        )
        chan2_before = max(
            i for i, w in enumerate(writes) if w == "CHAN2" and i < cc3_indices[1]
        )
        assert chan1_before < cc3_indices[0]
        assert chan2_before < cc3_indices[1]

    # ------------------------------------------------------------------
    # measure_voltage / measure_current — CH2 polled first, CH1 returned
    # ------------------------------------------------------------------

    def test_measure_voltage_returns_ch1_value(self):
        """measure_voltage() returns the CH1 reading, not CH2."""
        load, res = _make_connected(ProdigitBothChannelsLoad)
        call_count = [0]

        def _query(cmd):
            call_count[0] += 1
            # First VOLT? call is CH2 (= 5.0), second is CH1 (= 12.0)
            return "5.0" if call_count[0] == 1 else "12.0"

        res.query.side_effect = _query
        v = load.measure_voltage()
        assert abs(v - 12.0) < 1e-6, "measure_voltage() must return the CH1 value"

    def test_measure_voltage_caches_ch2(self):
        """CH2 voltage is cached in _last_ch2_voltage after measure_voltage()."""
        load, res = _make_connected(ProdigitBothChannelsLoad)
        call_count = [0]

        def _query(cmd):
            call_count[0] += 1
            return "7.5" if call_count[0] == 1 else "12.0"

        res.query.side_effect = _query
        load.measure_voltage()
        assert abs(load.measure_voltage_ch2() - 7.5) < 1e-6

    def test_measure_current_returns_ch1_value(self):
        load, res = _make_connected(ProdigitBothChannelsLoad)
        call_count = [0]

        def _query(cmd):
            call_count[0] += 1
            return "1.0" if call_count[0] == 1 else "3.0"

        res.query.side_effect = _query
        i = load.measure_current()
        assert abs(i - 3.0) < 1e-6

    def test_measure_current_caches_ch2(self):
        load, res = _make_connected(ProdigitBothChannelsLoad)
        call_count = [0]

        def _query(cmd):
            call_count[0] += 1
            return "2.5" if call_count[0] == 1 else "3.0"

        res.query.side_effect = _query
        load.measure_current()
        assert abs(load.measure_current_ch2() - 2.5) < 1e-6

    def test_measure_voltage_polls_ch2_first(self):
        """CHAN2 must appear before CHAN1 in the write sequence during measurement."""
        load, res = _make_connected(ProdigitBothChannelsLoad)
        res.query.return_value = "12.0"
        load.measure_voltage()
        writes = self._writes(res)
        chan1_idx = writes.index("CHAN1")
        chan2_idx = writes.index("CHAN2")
        assert chan2_idx < chan1_idx, "CH2 must be selected before CH1 during measurement"

    # ------------------------------------------------------------------
    # input_on / input_off — both channels
    # ------------------------------------------------------------------

    def test_input_on_both_channels(self):
        load, res = _make_connected(ProdigitBothChannelsLoad)
        load.input_on()
        writes = self._writes(res)
        assert "CHAN1" in writes
        assert "CHAN2" in writes
        assert writes.count("LOAD ON") == 2

    def test_input_off_both_channels(self):
        load, res = _make_connected(ProdigitBothChannelsLoad)
        load.input_off()
        writes = self._writes(res)
        assert "CHAN1" in writes
        assert "CHAN2" in writes
        assert writes.count("LOAD OFF") == 2

    def test_input_on_chan1_before_chan2(self):
        """LOAD ON must be sent to CH1 before CH2."""
        load, res = _make_connected(ProdigitBothChannelsLoad)
        load.input_on()
        writes = self._writes(res)
        chan1_idx = writes.index("CHAN1")
        chan2_idx = writes.index("CHAN2")
        assert chan1_idx < chan2_idx

    # ------------------------------------------------------------------
    # Class hierarchy and registry
    # ------------------------------------------------------------------

    def test_both_is_electronic_load_subclass(self):
        assert issubclass(ProdigitBothChannelsLoad, ElectronicLoad)
        assert issubclass(ProdigitBothChannelsLoad, ProdigitDualChannelLoad)

    def test_both_in_profile_registry(self):
        assert "prodigit_3330f_both" in LOAD_PROFILES
        assert LOAD_PROFILES["prodigit_3330f_both"] is ProdigitBothChannelsLoad


# ======================================================================
# SM — Settings: load_channel_mode field
# ======================================================================

class TestLoadChannelModeSetting:

    def test_load_channel_mode_default_is_ch1(self):
        from src.config.settings_manager import SettingsManager
        sm = SettingsManager()
        assert sm.load_channel_mode == "ch1"

    def test_load_channel_mode_survives_save_load_cycle(self, tmp_path, monkeypatch):
        """load_channel_mode is persisted to config.json and reloaded correctly."""
        from src.config.settings_manager import SettingsManager
        import src.config.settings_manager as sm_mod

        config_path = tmp_path / "config.json"
        monkeypatch.setattr(sm_mod, "CONFIG_FILE", config_path)
        monkeypatch.setattr(sm_mod, "LOGS_DIR", tmp_path / "logs")

        sm = SettingsManager()
        sm.load_channel_mode = "both"
        sm.save()

        sm2 = SettingsManager()
        sm2.load_channel_mode = "ch1"   # default — will be overwritten by load()
        sm2.load()
        assert sm2.load_channel_mode == "both"

    def test_load_channel_mode_applies_default_when_missing(self, tmp_path, monkeypatch):
        """Old config without load_channel_mode falls back to 'ch1'."""
        import json
        from src.config.settings_manager import SettingsManager
        import src.config.settings_manager as sm_mod

        config_path = tmp_path / "config.json"
        monkeypatch.setattr(sm_mod, "CONFIG_FILE", config_path)
        monkeypatch.setattr(sm_mod, "LOGS_DIR", tmp_path / "logs")

        # Write a minimal config without the new key
        config_path.write_text(
            json.dumps({"psu_visa_strings": [""], "load_visa_strings": [""]}),
            encoding="utf-8",
        )

        sm = SettingsManager()
        sm.load()
        assert sm.load_channel_mode == "ch1"
