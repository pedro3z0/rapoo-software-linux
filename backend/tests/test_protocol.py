# -*- coding: utf-8 -*-
import pytest
from backend.rapoo.protocol import (
    get_address,
    get_absolute_address,
    build_read_packet,
    build_write_packet,
    OFFSET_MOUSE_DPI_CUR,
    OFFSET_MOUSE_SCAN_RATE,
    OFFSET_RF_PROTOCOL_SETTING,
    OFFSET_RF_BOOST_SWITCH,
    SENSOR_MODE_OFFSET,
    SENSOR_MODE_VALUES,
    SENSOR_MODE_VALUES_13K,
    POLLING_RATE_SLOTS,
    POLLING_SLOTS_FOR_SENSOR_MODE,
    KEY_SCAN_RATE_VALUES,
    KEY_SCAN_RATE_ALLOWED,
    LOD_SCALE_LV,
    LOD_SCALE_MV,
    RF_PROTOCOL_TURBO,
    RF_PROTOCOL_INITIAL,
    RF_BOOST_SMART,
    RF_BOOST_FULL,
    CONN_WIRELESS,
    CMD_READ_EEPROM,
    CMD_WRITE_EEPROM,
    POLLING_RATE_LABELS,
    LABEL_TO_POLLING_RATE,
)
from backend.rapoo.transport import (
    parse_feature_response,
    response_status_index,
)


def test_profile_address_calculation():
    addr = get_address(OFFSET_MOUSE_DPI_CUR, profile_index=0)
    assert addr == [0x98, 0x08, 0x00, 0x00]  # 1536 + 664
    assert get_address(OFFSET_MOUSE_DPI_CUR, profile_index=1) == [0x98, 0x0C, 0x00, 0x00]


def test_absolute_address_calculation():
    # RF protocol lives at global offset 96
    assert get_absolute_address(OFFSET_RF_PROTOCOL_SETTING) == [0x60, 0x00, 0x00, 0x00]


def test_build_read_packet():
    pkt = build_read_packet(CONN_WIRELESS, [0x98, 0x08, 0, 0], length=1)
    assert len(pkt) == 32
    assert pkt[0] == CONN_WIRELESS
    assert pkt[1] == CMD_READ_EEPROM
    assert pkt[2] == 1
    assert pkt[3:7] == bytes([0x98, 0x08, 0, 0])


def test_build_write_packet():
    pkt = build_write_packet(CONN_WIRELESS, [0x98, 0x08, 0, 0], [2])
    assert pkt[1] == CMD_WRITE_EEPROM
    assert pkt[7] == 2


def test_polling_rate_mappings():
    assert POLLING_RATE_SLOTS == [8, 4, 2, 1, 132, 130, 129]
    assert POLLING_RATE_LABELS[1] == "1000Hz"
    assert POLLING_RATE_LABELS[130] == "4000Hz"
    assert LABEL_TO_POLLING_RATE["8000Hz"] == 129


def test_key_scan_rate_table():
    # official dd-index labels; retail devices allow 3..6 only
    assert KEY_SCAN_RATE_VALUES[3] == 1000
    assert KEY_SCAN_RATE_VALUES[4] == 2000
    assert KEY_SCAN_RATE_VALUES[5] == 4000
    assert KEY_SCAN_RATE_VALUES[6] == 8000
    assert KEY_SCAN_RATE_ALLOWED == (3, 4, 5, 6)


def test_sensor_mode_tables():
    # 13K retail tier (VT0/VT3 Air family): 0=office .. 5=frenzy
    assert SENSOR_MODE_VALUES_13K[0] == "office"
    assert SENSOR_MODE_VALUES_13K[5] == "frenzy"
    assert SENSOR_MODE_VALUES is SENSOR_MODE_VALUES_13K
    # 125Hz only allows low-power presets; 8000Hz only performance presets
    assert set(POLLING_SLOTS_FOR_SENSOR_MODE[8]) == {0, 1}
    assert set(POLLING_SLOTS_FOR_SENSOR_MODE[129]) == {3, 4, 5}


def test_lod_scales():
    assert LOD_SCALE_LV[0] == 0.7 and LOD_SCALE_LV[-1] == 1.7 and len(LOD_SCALE_LV) == 11
    assert LOD_SCALE_MV[0] == 1.0 and LOD_SCALE_MV[-1] == 2.0 and len(LOD_SCALE_MV) == 11


def test_rf_values():
    assert (RF_PROTOCOL_TURBO, RF_PROTOCOL_INITIAL) == (0, 2)
    assert (RF_BOOST_SMART, RF_BOOST_FULL) == (0, 1)
    assert OFFSET_RF_PROTOCOL_SETTING == 96
    assert OFFSET_RF_BOOST_SWITCH == 728
    assert SENSOR_MODE_OFFSET == 732


def test_response_layout_detection():
    # Layout A: report ID stripped -> status at 0, data at 4
    resp_a = bytes([1, 0xA4, 0x02, 0x00, 0xAE, 0x24])
    assert response_status_index(resp_a) == 0
    status, payload = parse_feature_response(resp_a, payload_offset=4)
    assert status == 1 and payload[:2] == bytes([0xAE, 0x24])

    # Layout B: report ID first -> status at 1, data at 5
    resp_b = bytes([0x08, 1, 0xA4, 0x02, 0x00, 0xAE, 0x24])
    assert response_status_index(resp_b) == 1
    status, payload = parse_feature_response(resp_b, payload_offset=5)
    assert status == 1 and payload[:2] == bytes([0xAE, 0x24])

    # Busy ACK on either layout is reported as 2
    assert parse_feature_response(bytes([2, 0, 0, 0, 0]), 4)[0] == 2
    assert parse_feature_response(bytes([0x08, 2, 0, 0, 0, 0]), 5)[0] == 2


def test_offset_shift_detection_helper():
    # A misaligned slice must NOT look like a valid perf block:
    # sleep timeout 0x0F at the 'corrections' position (bit0+bit1 set) is
    # exactly the bug that made linear/ripple appear enabled.
    perf = bytes([130, 3, 0, 0, 4, 1, 0, 0])          # real block: 4000Hz, scan 3, LOD 4, motion 1
    shifted = bytes([15]) + perf[:5]                    # off-by-one variant
    assert perf[0] in POLLING_RATE_LABELS
    assert not (shifted[0] in POLLING_RATE_LABELS)
