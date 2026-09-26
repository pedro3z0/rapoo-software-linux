# -*- coding: utf-8 -*-
"""Rapoo Gaming Device Protocol Engine (Reverse-Engineered from Rapoo AHUB 2.0 & Windows Driver).

Supports Rapoo VT series mice (e.g. VT3 Air / VT0 Air MAX, VT3 Pro, VT9, etc.)
and compatible wireless receivers.

Protocol summary:
- Report ID 6 (32 bytes) for sending commands (output report)
- Report ID 8 (32 bytes) for receiving feature report responses
- Reading memory:
    write report 6: [connection_type, 0xA4, length, ...address (4 bytes LE)]
    read feature report 8: [status, length, ...data] (offset 4 has response data)
- Writing memory:
    write report 6: [connection_type, 0xA5, length, ...address (4 bytes LE), ...data]
- Status bytes:
    0x01: OK / Ready
    0x02: Device Busy (retry)
"""
from __future__ import annotations

import struct
from dataclasses import dataclass
from typing import List, Tuple, Dict, Any, Optional

REPORT_ID_OUTPUT = 6
REPORT_ID_FEATURE = 8

ACK_OK = 1
ACK_BUSY = 2

CMD_READ_EEPROM = 0xA4
CMD_WRITE_EEPROM = 0xA5
CMD_RETURN_FACTORY = 0xAD
CMD_GET_WORK_MODE = 0xA7
CMD_GET_FIRMWARE = 0xB0

CONN_WIRED = 0xFF      # 255
CONN_WIRELESS = 0xA5   # 165

# Configuration profiles base addresses in EEPROM
PROFILE_BASE_ADDRESSES = [1536, 2560, 3584, 4608, 5632, 6656, 7680, 8704]

# EEPROM Offsets relative to profile base address
OFFSET_MOUSE_LEFT = 0
OFFSET_MOUSE_MID = 4
OFFSET_MOUSE_RIGHT = 8
OFFSET_MOUSE_CPIADD = 12
OFFSET_MOUSE_CPIREDUCE = 16
OFFSET_MOUSE_FORWARD = 20
OFFSET_MOUSE_BACK = 24
OFFSET_MOUSE_ROLLFORWARD = 36
OFFSET_MOUSE_ROLLBACK = 40
OFFSET_MOUSE_BOTTOM = 52

OFFSET_MOUSE_REPORT = 640        # Polling rate
OFFSET_MOUSE_SCAN_RATE = 641     # Key scan rate
OFFSET_MOUSE_SLIGHT = 644        # Silent height / LOD
OFFSET_MOUSE_MOTION = 645        # Motion sync switch
OFFSET_MOUSE_DPI_X_LIST = 648    # 7 stages * 2 bytes = 14 bytes
OFFSET_MOUSE_DPI_ENABLE_GEAR = 662  # Enabled DPI gear count - 1
OFFSET_MOUSE_DPI_CUR = 664       # Current active DPI gear index (0-based)
OFFSET_MOUSE_LIGHTMOD = 665      # Lighting mode
OFFSET_MOUSE_POWERSAVE = 684     # Power saving mode
OFFSET_MOUSE_LIGHTRGB = 696      # Lighting RGB
OFFSET_MOUSE_DOWNDELAY = 704     # Key press debounce ms
OFFSET_MOUSE_LIFTDELAY = 705     # Key release debounce ms
OFFSET_MOUSE_SCAN_RATE = 641     # Key scan-rate index (keyScanRates table)
OFFSET_MOUSE_SLEEPTIME = 706     # Sleep time (minutes)
OFFSET_MOUSE_LINEAR_RIPPLE = 707 # Bit 0: linear correction, Bit 1: ripple correction
OFFSET_MOUSE_SENSORANGLE = 708   # Sensor angle (-30 to +30 deg)
OFFSET_MOUSE_GLASS = 709         # Glass tracking switch (0/1)
OFFSET_MOUSE_LOWPOWER = 710      # Low power warning threshold
OFFSET_MOUSE_DPI_Y_LIST = 712    # 7 stages * 2 bytes = 14 bytes (Y axis)

# RF strategy / communication protocol (profile 0 only, absolute offset 96)
OFFSET_RF_PROTOCOL_SETTING = 96     # 0=turbo, 2=initial
RF_PROTOCOL_TURBO = 0
RF_PROTOCOL_INITIAL = 2

# RF Boost (wireless radio policy) + low-battery/DC switches
# 4-byte block base = profile base + 728
OFFSET_RF_BOOST_SWITCH = 728        # 0=smart adjust, 1=full RF
OFFSET_LOW_BATTERY_LIGHT_SWITCH = 729  # 0=off, 1=on (low-battery flash alert)
OFFSET_DC_SWITCH = 730              # 0=off, 1=on
RF_BOOST_SMART = 0
RF_BOOST_FULL = 1

# Lift-off distance: profile offset 644 stores a **1-based** index into the
# model-specific `liftoffHeight` scale (official UI validates >= 1 and does
# `silentHeight-1` to pick the entry). Two scales exist in official firmware:
#   LV scale [0.7..1.7 mm] - capability `l1`, 65 official models incl.
#                            VT0 Air MAX / VT3 Air (PAW3950U/PAW3955U family)
#   MV scale [1.0..2.0 mm]  - capability `co`, PAW3398 legacy models
#                            (VT0/VT1/VT2/VT3/VT3S/VT6/VT7/VT9, ESM*PRO)
LOD_SCALE_LV = [0.7, 0.8, 0.9, 1.0, 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 1.7]
LOD_SCALE_MV = [1.0, 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 1.7, 1.8, 1.9, 2.0]
LOD_SCALE_DEFAULT = LOD_SCALE_LV

# Polling rate lookup table for modern retail tier (nRF54L family)
POLLING_RATE_SLOTS = [8, 4, 2, 1, 132, 130, 129]
POLLING_RATE_LABELS = {
    8: "125Hz",
    4: "250Hz",
    2: "500Hz",
    1: "1000Hz",
    132: "2000Hz",
    130: "4000Hz",
    129: "8000Hz"
}
LABEL_TO_POLLING_RATE = {v: k for k, v in POLLING_RATE_LABELS.items()}

# Allowed polling-rate slot values per UI preset index (VV table).
# UI index: 5=office, 4=balanced, 3=firepower, 2=hyperCore,
# 1=competitive, 0=frenzy. Devices with `sensorScanRateLabel:\"13K\"`
# (EV array) use the inverted preset numbering:
# 5=frenzy, 4=competitive, 3=hyperCore, 2=firepower, 1=balanced, 0=office.
POLLING_SLOTS_FOR_SENSOR_MODE = {
    8: [1, 0],
    4: [1, 0],
    2: [2, 1, 0],
    1: [5, 4, 3, 2, 1],
    132: [5, 4, 3, 2],
    130: [5, 4, 3],
    129: [5, 4, 3],
}
# Sensor-mode presets for `sensorScanRateLabel:"13K"` mice (e.g. VT0 Air MAX).
SENSOR_MODE_VALUES_13K = {
    5: "frenzy",
    4: "competitive",
    3: "hyperCore",
    2: "firepower",
    1: "balanced",
    0: "office",
}
# Sensor-mode presets for legacy paw3311-tier devices.
SENSOR_MODE_VALUES_PAQ3311 = {
    5: "office",
    4: "balanced",
    3: "firepower",
    2: "hyperCore",
    0: "office",
}
# Default used by this project: "13K" tier matches VT0/VT3 Air hardware.
SENSOR_MODE_VALUES = SENSOR_MODE_VALUES_13K
SENSOR_MODE_OFFSET = 732          # profile-relative EEPROM offset of the 7-slot sensor-mode list
SENSOR_MODE_DEFAULT = [5, 5, 5, 5, 5, 5, 5]  # read-fallback only, factory value unverified

# Key (button) scan-rate labels from the official `dd` array: UI index -> Hz label.
# The device stores a plain index here; for `keyScanRate` capable retail devices
# the official capability table only allows indices 3..6.
KEY_SCAN_RATE_VALUES = {0: 125, 1: 250, 2: 500, 3: 1000, 4: 2000, 5: 4000, 6: 8000}
KEY_SCAN_RATE_ALLOWED = (3, 4, 5, 6)
KEY_SCAN_RATE_DEFAULT = 3

# Pairing / receiver link commands (legacy framing, from official WebHID
# VTNrf54L pairing classes + VT_nrf54L_Base command table).
# Payloads are sent as report-6 output reports; result read via feature 8.
#   switch_work_mode [160] + [mode]: 129 = pairing mode, 0 = normal
#   clear_code_status [161, 130]: clears current RF pairing on the mouse
#   code_match_mode [161, 143] + 4 random bytes: new RF address offer
#   device_pairing_status [161, 1]: response byte1 == 1 while paired/linked
#   read_work_mode [167]: response byte1 == 0 means normal (paired) mode
#   get_work_mode [162] (base/dongle table): response byte1 == 0 same sense
PAIR_SWITCH_WORK_MODE = 160
PAIR_MODE_PAIRING = 129
PAIR_MODE_NORMAL = 0
PAIR_CLEAR_CODE = [161, 130]
PAIR_CODE_MATCH = [161, 143]
PAIR_STATUS = [161, 1]
PAIR_READ_WORK_MODE = 167
PAIR_GET_WORK_MODE_BASE = 162


def get_address(offset: int, profile_index: int = 0) -> List[int]:
    """Calculates 4-byte LE address for a given profile offset."""
    base = PROFILE_BASE_ADDRESSES[profile_index % len(PROFILE_BASE_ADDRESSES)]
    addr = base + offset
    return [
        addr & 0xFF,
        (addr >> 8) & 0xFF,
        (addr >> 16) & 0xFF,
        (addr >> 24) & 0xFF,
    ]


def get_absolute_address(offset: int) -> List[int]:
    """Calculates 4-byte LE address for a global EEPROM offset (no profile)."""
    return [
        offset & 0xFF,
        (offset >> 8) & 0xFF,
        (offset >> 16) & 0xFF,
        (offset >> 24) & 0xFF,
    ]


def build_read_packet(connection_type: int, address: List[int], length: int) -> bytes:
    """Builds a 32-byte output report for reading EEPROM memory."""
    pkt = bytearray(32)
    pkt[0] = connection_type
    pkt[1] = CMD_READ_EEPROM
    pkt[2] = length
    for i in range(min(4, len(address))):
        pkt[3 + i] = address[i]
    return bytes(pkt)


def build_write_packet(connection_type: int, address: List[int], data: bytes | List[int]) -> bytes:
    """Builds a 32-byte output report for writing EEPROM memory."""
    pkt = bytearray(32)
    pkt[0] = connection_type
    pkt[1] = CMD_WRITE_EEPROM
    pkt[2] = len(data)
    for i in range(min(4, len(address))):
        pkt[3 + i] = address[i]
    for i in range(len(data)):
        if 7 + i < 32:
            pkt[7 + i] = data[i]
    return bytes(pkt)


def parse_connected_mouse_id(data: bytes) -> Optional[Tuple[int, int]]:
    """Parse vendor ID and product ID of mouse connected to receiver."""
    if len(data) < 6:
        return None
    # Offset 4 & 5 contain the 16-bit PID or VID
    val = data[4] | (data[5] << 8)
    return val

