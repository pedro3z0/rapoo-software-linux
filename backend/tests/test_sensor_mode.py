# -*- coding: utf-8 -*-
"""set_sensor_mode name matching + slot mapping (no hardware needed).

Regression: 'hyperCore' is mixed-case in SENSOR_MODE_VALUES; the matcher
used to lowercase only the input, so hyperCore could never be set while
all-lowercase names (frenzy/office/...) worked.
"""
import pytest
from backend.rapoo.device import RapooMouse
from backend.rapoo.protocol import (
    SENSOR_MODE_OFFSET,
    SENSOR_MODE_VALUES,
    POLLING_RATE_SLOTS,
)


class StubMouse:
    """Bare self: only the methods set_sensor_mode touches after matching."""

    set_sensor_mode = RapooMouse.set_sensor_mode

    def __init__(self, poll_raw=1):  # 1000Hz
        self.poll_raw = poll_raw
        self.write = None

    def _resolve_polling(self, polling_rate, profile):
        assert polling_rate is None
        return self.poll_raw

    def write_memory(self, offset, data, profile):
        self.write = (offset, data, profile)


def test_every_table_name_resolves_in_any_case():
    for value, name in SENSOR_MODE_VALUES.items():
        # Pick a polling rate whose VV list permits this value:
        # office (0) is only allowed at 125/250/500Hz, the rest at 1000Hz.
        poll_raw = 8 if value == 0 else 1
        m = StubMouse(poll_raw=poll_raw)
        m.set_sensor_mode(name)          # canonical spelling
        m.set_sensor_mode(name.upper())  # screaming case
        m.set_sensor_mode(name.swapcase())
        slot = POLLING_RATE_SLOTS.index(poll_raw)
        assert m.write == (SENSOR_MODE_OFFSET + slot, [value], 0)


def test_hypercore_regression():
    m = StubMouse()
    m.set_sensor_mode("hyperCore")
    slot = POLLING_RATE_SLOTS.index(1)
    assert m.write == (SENSOR_MODE_OFFSET + slot, [3], 0)


def test_unknown_name_still_rejected():
    m = StubMouse()
    with pytest.raises(ValueError, match="Unknown preset"):
        m.set_sensor_mode("not-a-preset")


def test_vv_table_enforced_with_name():
    # frenzy (5) is not allowed at 125Hz (raw 8): allowed = [1, 0]
    m = StubMouse(poll_raw=8)
    with pytest.raises(ValueError, match="not allowed"):
        m.set_sensor_mode("frenzy")
    # balanced (1) is allowed there
    m.set_sensor_mode("balanced")
    slot = POLLING_RATE_SLOTS.index(8)
    assert m.write == (SENSOR_MODE_OFFSET + slot, [1], 0)


from backend.rapoo.protocol import OFFSET_MOUSE_LINEAR_RIPPLE, OFFSET_MOUSE_DOWNDELAY


class CorrectionsStub:
    set_corrections = RapooMouse.set_corrections
    set_debounce = RapooMouse.set_debounce

    def __init__(self, cur_byte=0b11, cur_deb=(0, 0)):
        self.cur_byte = cur_byte
        self.cur_deb = cur_deb
        self.write = None
        self.read_calls = 0

    def read_memory(self, offset, length, profile):
        self.read_calls += 1
        if offset == OFFSET_MOUSE_LINEAR_RIPPLE:
            return [self.cur_byte]
        if offset == OFFSET_MOUSE_DOWNDELAY:
            return list(self.cur_deb[:length])
        raise AssertionError(f"unexpected read offset {offset}")

    def write_memory(self, offset, data, profile):
        self.write = (offset, data)
        # simulate the EEPROM so successive calls see the new state
        if offset == OFFSET_MOUSE_LINEAR_RIPPLE:
            self.cur_byte = data[0]
        elif offset == OFFSET_MOUSE_DOWNDELAY:
            self.cur_deb = (data[0], data[1] if len(data) > 1 else data[0])


def test_corrections_toggle_preserves_the_other_bit():
    m = CorrectionsStub(cur_byte=0b11)  # linear on, ripple on
    m.set_corrections(linear=False)  # ripple must stay on
    assert m.write == (OFFSET_MOUSE_LINEAR_RIPPLE, [0b10])
    m.set_corrections(ripple=False)  # linear stays off now
    assert m.write == (OFFSET_MOUSE_LINEAR_RIPPLE, [0b00])
    m.set_corrections(ripple=True)   # linear still off
    assert m.write == (OFFSET_MOUSE_LINEAR_RIPPLE, [0b10])
    m.set_corrections(linear=True)   # ripple stays on
    assert m.write == (OFFSET_MOUSE_LINEAR_RIPPLE, [0b11])


def test_debounce_preserve_and_range():
    m = CorrectionsStub(cur_deb=(3, 7))
    m.set_debounce(press_ms=0)
    assert m.write == (OFFSET_MOUSE_DOWNDELAY, [0, 7])  # release preserved
    m.set_debounce(release_ms=0)
    assert m.write == (OFFSET_MOUSE_DOWNDELAY, [0, 0])
    m.set_debounce(press_ms=32, release_ms=32)
    assert m.write == (OFFSET_MOUSE_DOWNDELAY, [32, 32])
    with pytest.raises(ValueError, match="0-32"):
        m.set_debounce(press_ms=33)


from backend.rapoo.device_registry import registry, SENSOR_SCAN_LABELS


def test_sensor_scan_label_table():
    # VT0 Air MAX wired+dongle PIDs (from official driver device table)
    assert SENSOR_SCAN_LABELS[18081] == "13K"
    assert SENSOR_SCAN_LABELS[5281] == "13K"
    # a legacy paw3398-tier model must be 10K
    assert SENSOR_SCAN_LABELS[17969] == "10K"


def test_registry_resolves_label_for_connected_model():
    m = registry.find_by_pid(18081)
    assert m is not None
    assert m.sensor_scan_label == "13K"
    # models without the capability get an empty label (UI falls back)
    kb = registry.find_by_pid(18452)
    if kb is not None:
        assert kb.sensor_scan_label == ""
