# -*- coding: utf-8 -*-
"""High-level Rapoo Mouse Controller.

Provides getters and setters for all mouse properties with safety checks,
automatic backup generation, and validation.
"""
from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass, asdict
from typing import Optional, List, Dict, Any
from pathlib import Path

from .protocol import (
    REPORT_ID_OUTPUT,
    REPORT_ID_FEATURE,
    OFFSET_MOUSE_DPI_CUR,
    OFFSET_MOUSE_DPI_X_LIST,
    OFFSET_MOUSE_DPI_Y_LIST,
    OFFSET_MOUSE_DPI_ENABLE_GEAR,
    OFFSET_MOUSE_REPORT,
    OFFSET_MOUSE_SLEEPTIME,
    OFFSET_MOUSE_SENSORANGLE,
    OFFSET_MOUSE_GLASS,
    OFFSET_MOUSE_MOTION,
    OFFSET_MOUSE_LINEAR_RIPPLE,
    OFFSET_MOUSE_DOWNDELAY,
    OFFSET_MOUSE_LIFTDELAY,
    OFFSET_MOUSE_SCAN_RATE,
    OFFSET_MOUSE_SLIGHT,
    OFFSET_RF_PROTOCOL_SETTING,
    OFFSET_RF_BOOST_SWITCH,
    OFFSET_LOW_BATTERY_LIGHT_SWITCH,
    OFFSET_DC_SWITCH,
    RF_PROTOCOL_TURBO,
    RF_PROTOCOL_INITIAL,
    RF_BOOST_SMART,
    RF_BOOST_FULL,
    LOD_SCALE_LV,
    LOD_SCALE_MV,
    LOD_SCALE_DEFAULT,
    SENSOR_MODE_OFFSET,
    SENSOR_MODE_VALUES,
    SENSOR_MODE_DEFAULT,
    POLLING_RATE_SLOTS,
    POLLING_SLOTS_FOR_SENSOR_MODE,
    KEY_SCAN_RATE_VALUES,
    KEY_SCAN_RATE_ALLOWED,
    KEY_SCAN_RATE_DEFAULT,
    POLLING_RATE_LABELS,
    LABEL_TO_POLLING_RATE,
    PAIR_SWITCH_WORK_MODE,
    PAIR_MODE_PAIRING,
    PAIR_MODE_NORMAL,
    PAIR_CLEAR_CODE,
    PAIR_CODE_MATCH,
    PAIR_STATUS,
    PAIR_READ_WORK_MODE,
    CONN_WIRELESS,
    CONN_WIRED,
    get_address,
    get_absolute_address,
    build_read_packet,
    build_write_packet
)
from .transport import (
    RapooTransport,
    DeviceEndpoint,
    enumerate_rapoo_endpoints,
    parse_feature_response,
    response_status_index,
    STATUS_REPORT_ID,
    PAYLOAD_OFFSET_CANDIDATES,
    RapooProtocolError,
)
from .device_registry import registry, DeviceModel


@dataclass
class MouseSettings:
    current_dpi_stage: int
    dpi_stages_x: List[int]
    dpi_stages_y: List[int]
    polling_rate_raw: int
    polling_rate_label: str
    sleep_time_minutes: int
    sensor_angle: int
    glass_tracking: bool
    motion_sync: bool
    linear_correction: bool
    ripple_correction: bool
    debounce_press_ms: int
    debounce_release_ms: int
    key_scan_rate_index: int
    key_scan_rate_label: str
    sensor_mode_slots: List[int]
    sensor_mode_preset: str
    # Performance / RF additions (safe-verified memory regions only)
    rf_protocol_raw: int
    rf_protocol_label: str
    rf_boost_enabled: bool
    low_battery_light_enabled: bool
    dc_switch_enabled: bool
    liftoff_index: int
    liftoff_label: str
    liftoff_scale: List[float]


class RapooMouse:
    def __init__(self, endpoint: Optional[DeviceEndpoint] = None):
        if endpoint is None:
            # Autodetect: find interface 1 (the configuration channel)
            endpoints = enumerate_rapoo_endpoints()
            config_endpoints = [e for e in endpoints if e.interface_num == 1]
            if not config_endpoints:
                raise RuntimeError("No Rapoo configuration interface (interface 1) found")
            endpoint = config_endpoints[0]

        self.endpoint = endpoint
        self.transport = RapooTransport(endpoint.path)
        self.model: Optional[DeviceModel] = registry.find_by_pid(endpoint.product_id)
        # Link type: official manifests list productId as
        # [wired-mouse-PID, dongle-PID] (e.g. VT0 Air MAX [18081, 5281]):
        # index 0 = the mouse itself on USB cable, index 1 = receiver.
        # Single-PID models are cable-only devices.
        pid = endpoint.product_id
        if self.model and len(self.model.pids) >= 2:
            self.connection_type = CONN_WIRED if pid == self.model.pids[0] else CONN_WIRELESS
        elif self.model and len(self.model.pids) == 1:
            self.connection_type = CONN_WIRED
        else:
            self.connection_type = CONN_WIRED if pid > 10000 else CONN_WIRELESS
        # Response payload offset: None = auto-calibrate on first read.
        env_offset = os.environ.get("RAPOO_DATA_OFFSET")
        self.payload_offset: Optional[int] = int(env_offset) if env_offset else None

    def open(self):
        self.transport.open()

    def close(self):
        self.transport.close()

    def __enter__(self):
        self.open()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

    def _probe_payload_offset(self, offset: int) -> bool:
        """True when slicing responses at *offset* yields known-sane values.

        Anchors: perf block at 640 (polling code + key-scan index + lift-off
        index + motion flag) and the DPI stage at 664 (0..6).
        """
        try:
            resp = self._raw_request(build_read_packet(self.connection_type, get_address(OFFSET_MOUSE_REPORT, 0), 8))
            perf = resp[offset:offset + 8]
            if len(perf) < 6:
                return False
            if perf[0] not in POLLING_RATE_LABELS:
                return False
            if not (0 <= perf[1] <= 6):
                return False
            if not (1 <= perf[4] <= 12):
                return False
            if perf[5] not in (0, 1):
                return False
            resp2 = self._raw_request(build_read_packet(self.connection_type, get_address(OFFSET_MOUSE_DPI_CUR, 0), 1))
            stage = resp2[offset]
            if not (0 <= stage <= 6):
                return False
        except Exception:
            return False
        return True

    def calibrate(self) -> int:
        """Detects the response payload offset (4, 5 or 6) for this kernel/device.

        The official WebHID driver sees responses as [status, echo.., data@4];
        Linux HIDIOCGFEATURE may include the report ID byte, shifting the
        payload. Wrong offsets silently misread neighbouring registers (that
        is why 'linear/ripple' could appear set while the official UI showed
        them off - the byte being read was the sleep timeout instead).
        """
        if self.payload_offset is not None:
            return self.payload_offset
        for candidate in PAYLOAD_OFFSET_CANDIDATES:
            if self._probe_payload_offset(candidate):
                self.payload_offset = candidate
                return candidate
        raise RapooProtocolError(
            "could not determine the response payload offset; run "
            "'python -m backend.rapoo.cli raw --offset 640 --length 8' "
            "and report the output, or set RAPOO_DATA_OFFSET=4|5|6"
        )

    def _slice(self, resp: bytes) -> tuple[int, bytes]:
        """Returns (status, payload) honouring the calibrated offset."""
        offset = self.calibrate()
        status = resp[response_status_index(resp)] if len(resp) > 1 else resp[0]
        if status != 1:
            raise RapooProtocolError(
                f"device returned ACK 0x{status:02X} (expected 0x01); raw="
                + " ".join(f"{b:02X}" for b in resp[:8])
            )
        return status, resp[offset:]

    def _raw_request(self, payload: bytes) -> bytes:
        """Sends a raw command and returns the raw response buffer."""
        return self.transport.request(payload)

    def raw_read(self, offset: int, length: int, profile: Optional[int] = None) -> dict:
        """Diagnostic: reads bytes and shows what each payload offset would yield."""
        if profile is None:
            # No calibration here on purpose: this command exists to debug it.
            addr = get_absolute_address(offset) if offset < 1024 else get_address(offset, 0)
        else:
            addr = get_address(offset, profile)
        resp = self._raw_request(build_read_packet(self.connection_type, addr, length))
        status = resp[response_status_index(resp)] if len(resp) > 1 else resp[0]
        out = {
            "address": " ".join(f"{b:02X}" for b in addr),
            "length": length,
            "status": f"0x{status:02X}",
            "raw": " ".join(f"{b:02X}" for b in resp),
        }
        for cand in (4, 5, 6):
            chunk = resp[cand:cand + length]
            out[f"payload@{cand}"] = " ".join(f"{b:02X}" for b in chunk)
        out["active_offset"] = self.payload_offset
        return out

    def read_memory(self, offset: int, length: int, profile: int = 0) -> bytes:
        """Reads `length` bytes from mouse memory at given profile offset."""
        addr = get_address(offset, profile)
        pkt = build_read_packet(self.connection_type, addr, length)
        resp = self.transport.request(pkt)
        _status, payload = self._slice(resp)
        return payload[:length]

    def write_memory(self, offset: int, data: bytes | List[int], profile: int = 0):
        """Writes data bytes to mouse memory at given profile offset."""
        addr = get_address(offset, profile)
        pkt = build_write_packet(self.connection_type, addr, data)
        self.transport.request(pkt)

    def read_absolute_memory(self, offset: int, length: int) -> bytes:
        """Reads `length` bytes from global EEPROM space (no profile base)."""
        addr = get_absolute_address(offset)
        pkt = build_read_packet(self.connection_type, addr, length)
        resp = self.transport.request(pkt)
        _status, payload = self._slice(resp)
        return payload[:length]

    def write_absolute_memory(self, offset: int, data: bytes | List[int]):
        """Writes data bytes to global EEPROM space (no profile base)."""
        addr = get_absolute_address(offset)
        pkt = build_write_packet(self.connection_type, addr, data)
        self.transport.request(pkt)

    def _lod_scale(self) -> List[float]:
        """Official liftoffHeight scale for this model (LV vs MV capability)."""
        sensor = self.model.sensor if self.model else ""
        # PAW3398 legacy family uses the 1.0-2.0 mm (MV) scale;
        # PAW3950U/PAW3955U and friends use the 0.7-1.7 mm (LV) scale.
        return LOD_SCALE_MV if sensor == "PAW3398" else LOD_SCALE_LV

    def get_settings(self, profile: int = 0) -> MouseSettings:
        """Reads complete snapshot of current mouse settings.

        Uses consolidated multi-byte reads wherever the official driver
        does, so the whole snapshot costs ~8 requests.
        """
        # 1. Current DPI stage
        cur_dpi_raw = self.read_memory(OFFSET_MOUSE_DPI_CUR, 1, profile)
        cur_dpi = cur_dpi_raw[0] if cur_dpi_raw else 0

        # 2. DPI stages X & Y (7 stages * 2 bytes each = 14 bytes)
        dpi_x_raw = self.read_memory(OFFSET_MOUSE_DPI_X_LIST, 14, profile)
        dpi_y_raw = self.read_memory(OFFSET_MOUSE_DPI_Y_LIST, 14, profile)
        stages_x = [dpi_x_raw[i*2] | (dpi_x_raw[i*2+1] << 8) for i in range(len(dpi_x_raw)//2)]
        stages_y = [dpi_y_raw[i*2] | (dpi_y_raw[i*2+1] << 8) for i in range(len(dpi_y_raw)//2)]

        # 3. Performance block at 640 (8 bytes, same as official getAllPerfCfg):
        #    [0]=polling [1]=key scan [4]=lift-off index [5]=motion sync
        perf = self.read_memory(OFFSET_MOUSE_REPORT, 8, profile)
        perf = perf + bytes(8)
        poll_val = perf[0]
        poll_label = POLLING_RATE_LABELS.get(poll_val, f"{poll_val} (Unknown)")
        scan_idx = perf[1]
        scan_hz = KEY_SCAN_RATE_VALUES.get(scan_idx)
        scan_label = f"{scan_hz}Hz" if scan_hz else f"index {scan_idx} (unknown)"
        lod_index = perf[4]                    # 1-based index into the model scale
        scale = self._lod_scale()
        if 1 <= lod_index <= len(scale):
            liftoff_label = f"{scale[lod_index - 1]:.1f} mm"
        else:
            liftoff_label = f"raw {lod_index}"
        motion = bool(perf[5])

        # 4. Settings block at 704 (6 bytes):
        #    [0]=debounce press [1]=debounce release [2]=sleep minutes
        #    [3]=linear/ripple bits [4]=sensor angle [5]=glass tracking
        blk = self.read_memory(OFFSET_MOUSE_DOWNDELAY, 6, profile)
        blk = blk + bytes(6)
        press_ms, release_ms, sleep_min = blk[0], blk[1], blk[2]
        corr_val = blk[3]
        linear = bool(corr_val & 0x01)
        ripple = bool((corr_val >> 1) & 0x01)
        angle = int.from_bytes(bytes([blk[4]]), "little", signed=True)
        glass = bool(blk[5])

        # 5. RF strategy block at 728 (4 bytes):
        #    [0]=RF boost (0=Adaptive,1=Maximum RF) [1]=low-battery light
        #    [2]=DC switch
        rf = self.read_memory(OFFSET_RF_BOOST_SWITCH, 4, profile)
        rf = rf + bytes(4)
        rf_boost = bool(rf[0])
        low_bat_light = bool(rf[1])
        dc_switch = bool(rf[2])

        # 6. Communication protocol (absolute offset 96; 0=turbo, 2=initial)
        rp_raw = self.read_absolute_memory(OFFSET_RF_PROTOCOL_SETTING, 1)
        rp_val = rp_raw[0] if rp_raw else RF_PROTOCOL_TURBO
        rp_label = {RF_PROTOCOL_TURBO: "turbo", RF_PROTOCOL_INITIAL: "initial"}.get(
            rp_val, f"raw {rp_val}"
        )

        # 7. Sensor-mode slots at profile base + 732 (7 bytes, one slot per
        #    polling-rate entry in POLLING_RATE_SLOTS). Preset shown for the
        #    currently configured polling rate.
        slots_raw = self.read_memory(SENSOR_MODE_OFFSET, 7, profile)
        slots = list(slots_raw[:7]) if len(slots_raw) >= 7 else list(SENSOR_MODE_DEFAULT)
        try:
            slot_idx = POLLING_RATE_SLOTS.index(poll_val)
        except ValueError:
            slot_idx = 0
        preset = SENSOR_MODE_VALUES.get(slots[slot_idx], f"raw {slots[slot_idx]}") if slots else "unknown"

        return MouseSettings(
            current_dpi_stage=cur_dpi,
            dpi_stages_x=stages_x,
            dpi_stages_y=stages_y,
            polling_rate_raw=poll_val,
            polling_rate_label=poll_label,
            sleep_time_minutes=sleep_min,
            sensor_angle=angle,
            glass_tracking=glass,
            motion_sync=motion,
            linear_correction=linear,
            ripple_correction=ripple,
            debounce_press_ms=press_ms,
            debounce_release_ms=release_ms,
            key_scan_rate_index=scan_idx,
            key_scan_rate_label=scan_label,
            sensor_mode_slots=slots,
            sensor_mode_preset=preset,
            rf_protocol_raw=rp_val,
            rf_protocol_label=rp_label,
            rf_boost_enabled=rf_boost,
            low_battery_light_enabled=low_bat_light,
            dc_switch_enabled=dc_switch,
            liftoff_index=lod_index,
            liftoff_label=liftoff_label,
            liftoff_scale=scale,
        )

    def set_dpi_stage(self, stage_index: int, profile: int = 0):
        if not (0 <= stage_index <= 6):
            raise ValueError(f"DPI stage must be 0-6, got {stage_index}")
        self.write_memory(OFFSET_MOUSE_DPI_CUR, [stage_index], profile)

    def set_stage_dpi(self, stage_index: int, dpi: int, profile: int = 0):
        if not (50 <= dpi <= 30000):
            raise ValueError(f"DPI must be between 50 and 30000, got {dpi}")
        offset_x = OFFSET_MOUSE_DPI_X_LIST + (stage_index * 2)
        offset_y = OFFSET_MOUSE_DPI_Y_LIST + (stage_index * 2)
        val = [dpi & 0xFF, (dpi >> 8) & 0xFF]
        self.write_memory(offset_x, val, profile)
        self.write_memory(offset_y, val, profile)

    def set_polling_rate(self, rate: int | str, profile: int = 0):
        if isinstance(rate, str):
            if rate not in LABEL_TO_POLLING_RATE:
                raise ValueError(f"Unknown polling rate label '{rate}'. Choose from: {list(LABEL_TO_POLLING_RATE.keys())}")
            raw = LABEL_TO_POLLING_RATE[rate]
        else:
            raw = rate
        self.write_memory(OFFSET_MOUSE_REPORT, [raw], profile)

    def set_sleep_time(self, minutes: int, profile: int = 0):
        if not (1 <= minutes <= 60):
            raise ValueError(f"Sleep time must be between 1 and 60 minutes, got {minutes}")
        self.write_memory(OFFSET_MOUSE_SLEEPTIME, [minutes], profile)

    def set_motion_sync(self, enabled: bool, profile: int = 0):
        self.write_memory(OFFSET_MOUSE_MOTION, [1 if enabled else 0], profile)

    def set_glass_tracking(self, enabled: bool, profile: int = 0):
        self.write_memory(OFFSET_MOUSE_GLASS, [1 if enabled else 0], profile)

    def set_angle(self, angle: int, profile: int = 0):
        if not (-30 <= angle <= 30):
            raise ValueError(f"Angle must be between -30 and +30 degrees, got {angle}")
        val = int(angle).to_bytes(1, byteorder="little", signed=True)
        self.write_memory(OFFSET_MOUSE_SENSORANGLE, val, profile)

    def set_corrections(self, linear: bool, ripple: bool, profile: int = 0):
        val = (1 if linear else 0) | ((1 if ripple else 0) << 1)
        self.write_memory(OFFSET_MOUSE_LINEAR_RIPPLE, [val], profile)

    def _resolve_polling(self, polling_rate: int | str | None, profile: int) -> int:
        """Resolves a polling rate (raw code or label) to its raw code,
        or reads the current one when None is given."""
        if polling_rate is None:
            cur = self.read_memory(OFFSET_MOUSE_REPORT, 1, profile)
            return cur[0] if cur else 1
        if isinstance(polling_rate, str):
            if polling_rate not in LABEL_TO_POLLING_RATE:
                raise ValueError(
                    f"Unknown polling rate '{polling_rate}'. "
                    f"Choose from: {list(LABEL_TO_POLLING_RATE.keys())}"
                )
            return LABEL_TO_POLLING_RATE[polling_rate]
        return polling_rate

    def set_sensor_mode(
        self,
        preset: int | str,
        polling_rate: int | str | None = None,
        profile: int = 0,
    ):
        """Sets the performance preset for one polling-rate slot.

        The device keeps one preset value per polling rate (7 slots at
        profile base + 732, slot order = POLLING_RATE_SLOTS). When
        polling_rate is None the currently configured rate's slot is used.
        preset: official 13K-tier value (0=office .. 5=frenzy) or its name.
        """
        if isinstance(preset, str):
            name = preset.strip().lower()
            matches = [v for v, n in SENSOR_MODE_VALUES.items() if n == name]
            if not matches:
                raise ValueError(
                    f"Unknown preset '{preset}'. Choose from: "
                    f"{sorted(set(SENSOR_MODE_VALUES.values()))}"
                )
            value = matches[0]
        else:
            value = preset
        if value not in SENSOR_MODE_VALUES:
            raise ValueError(
                f"Unknown preset value {value}. "
                f"Choose from: {sorted(SENSOR_MODE_VALUES.keys())}"
            )
        poll_raw = self._resolve_polling(polling_rate, profile)
        try:
            slot = POLLING_RATE_SLOTS.index(poll_raw)
        except ValueError:
            raise ValueError(
                f"Polling rate {poll_raw} is not one of "
                f"{POLLING_RATE_SLOTS}; cannot map to a sensor-mode slot"
            )
        allowed = POLLING_SLOTS_FOR_SENSOR_MODE.get(poll_raw)
        if allowed and value not in allowed:
            raise ValueError(
                f"Preset {SENSOR_MODE_VALUES[value]!r} is not allowed at "
                f"{POLLING_RATE_LABELS.get(poll_raw, poll_raw)} "
                f"(allowed: {[SENSOR_MODE_VALUES[v] for v in allowed if v in SENSOR_MODE_VALUES]})"
            )
        self.write_memory(SENSOR_MODE_OFFSET + slot, [value], profile)

    def set_sensor_mode_list(self, slots: List[int], profile: int = 0):
        """Writes the full 7-slot sensor-mode list (raw values)."""
        if len(slots) != 7:
            raise ValueError(f"Sensor mode list must have exactly 7 entries, got {len(slots)}")
        self.write_memory(SENSOR_MODE_OFFSET, list(slots), profile)

    def set_rf_protocol(self, protocol: int | str):
        """Communication protocol: 0/'turbo' (default) or 2/'initial'.

        Global EEPROM offset 96 (official RF_PROTOCOL_SETTING).
        """
        if isinstance(protocol, str):
            table = {"turbo": RF_PROTOCOL_TURBO, "initial": RF_PROTOCOL_INITIAL}
            key = protocol.strip().lower()
            if key not in table:
                raise ValueError(f"Unknown RF protocol '{protocol}'. Choose from: {list(table)}")
            raw = table[key]
        else:
            raw = protocol
        if raw not in (RF_PROTOCOL_TURBO, RF_PROTOCOL_INITIAL):
            raise ValueError(f"RF protocol must be {RF_PROTOCOL_TURBO} or {RF_PROTOCOL_INITIAL}, got {raw}")
        self.write_absolute_memory(OFFSET_RF_PROTOCOL_SETTING, [raw])

    def set_rf_boost(self, mode: int | bool | str, profile: int = 0):
        """Wireless RF strategy: 0/'adaptive' (signal-based power saving)
        or 1/'maximum' (full power, stronger interference immunity)."""
        if isinstance(mode, str):
            table = {"adaptive": RF_BOOST_SMART, "maximum": RF_BOOST_FULL}
            key = mode.strip().lower()
            if key not in table:
                raise ValueError(f"Unknown RF strategy '{mode}'. Choose from: {list(table)}")
            raw = table[key]
        elif isinstance(mode, bool):
            raw = RF_BOOST_FULL if mode else RF_BOOST_SMART
        else:
            raw = mode
        if raw not in (RF_BOOST_SMART, RF_BOOST_FULL):
            raise ValueError(f"RF strategy must be 0 or 1, got {raw}")
        self.write_memory(OFFSET_RF_BOOST_SWITCH, [raw], profile)

    def set_low_battery_light(self, enabled: bool, profile: int = 0):
        """Low-battery LED flash alert (LOW_POWE_WARN_SWITCH)."""
        self.write_memory(OFFSET_LOW_BATTERY_LIGHT_SWITCH, [1 if enabled else 0], profile)

    def set_dc_switch(self, enabled: bool, profile: int = 0):
        """DC switch (LOW_DC_SWITCH); purpose undocumented, official writes 0/1."""
        self.write_memory(OFFSET_DC_SWITCH, [1 if enabled else 0], profile)

    def set_liftoff(self, value: float | int, profile: int = 0):
        """Sets lift-off distance (silent height).

        Accepts a mm value from the model's official scale (e.g. 1.1) or a
        raw 1-based index (1..11). Stored as a 1-based index at offset 644.
        """
        scale = self._lod_scale()
        if isinstance(value, int) and not isinstance(value, bool):
            if not (1 <= value <= len(scale)):
                raise ValueError(f"Lift-off index must be 1..{len(scale)}, got {value}")
            index = value
        else:
            mm = float(value)
            matches = [i for i, v in enumerate(scale, start=1) if abs(v - mm) < 1e-6]
            if not matches:
                raise ValueError(
                    f"Lift-off {mm} mm is not on this model's scale "
                    f"({scale[0]:.1f}..{scale[-1]:.1f} mm)"
                )
            index = matches[0]
        self.write_memory(OFFSET_MOUSE_SLIGHT, [index], profile)

    def set_key_scan_rate(self, rate: int | str, profile: int = 0):
        """Sets the key scan-rate index (3=1000Hz, 4=2000Hz, 5=4000Hz, 6=8000Hz)."""
        if isinstance(rate, str):
            label = rate.strip().lower().replace(" ", "")
            table = {f"{hz}hz": idx for idx, hz in KEY_SCAN_RATE_VALUES.items()}
            if label not in table:
                raise ValueError(
                    f"Unknown key scan rate '{rate}'. Choose from: {list(table.keys())}"
                )
            raw = table[label]
        else:
            raw = rate
        if raw not in KEY_SCAN_RATE_ALLOWED:
            raise ValueError(
                f"Key scan rate index {raw} is not allowed for this device. "
                f"Choose from: {sorted(KEY_SCAN_RATE_ALLOWED)} "
                f"({[KEY_SCAN_RATE_VALUES[i] for i in KEY_SCAN_RATE_ALLOWED]})"
            )
        self.write_memory(OFFSET_MOUSE_SCAN_RATE, [raw], profile)

    def backup_to_file(self, filepath: Path) -> MouseSettings:
        settings = self.get_settings()
        filepath.parent.mkdir(parents=True, exist_ok=True)
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(asdict(settings), f, indent=2)
        return settings

    def restore_from_file(self, filepath: Path, profile: int = 0):
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)
        
        # Restore DPI
        self.set_dpi_stage(data["current_dpi_stage"], profile)
        for idx, (x, y) in enumerate(zip(data["dpi_stages_x"], data["dpi_stages_y"])):
            offset_x = OFFSET_MOUSE_DPI_X_LIST + (idx * 2)
            offset_y = OFFSET_MOUSE_DPI_Y_LIST + (idx * 2)
            self.write_memory(offset_x, [x & 0xFF, (x >> 8) & 0xFF], profile)
            self.write_memory(offset_y, [y & 0xFF, (y >> 8) & 0xFF], profile)
        
        # Restore others
        self.set_polling_rate(data["polling_rate_raw"], profile)
        self.set_sleep_time(data["sleep_time_minutes"], profile)
        self.set_motion_sync(data["motion_sync"], profile)
        self.set_glass_tracking(data["glass_tracking"], profile)
        self.set_angle(data["sensor_angle"], profile)
        self.set_corrections(data["linear_correction"], data["ripple_correction"], profile)
        if "key_scan_rate_index" in data:
            self.set_key_scan_rate(data["key_scan_rate_index"], profile)
        if "sensor_mode_slots" in data:
            self.set_sensor_mode_list(list(data["sensor_mode_slots"]), profile)
        # Performance / RF additions (older backups may not contain them)
        if "rf_protocol_raw" in data:
            self.set_rf_protocol(data["rf_protocol_raw"])
        if "rf_boost_enabled" in data:
            self.set_rf_boost(bool(data["rf_boost_enabled"]), profile)
        if "low_battery_light_enabled" in data:
            self.set_low_battery_light(bool(data["low_battery_light_enabled"]), profile)
        if "dc_switch_enabled" in data:
            self.set_dc_switch(bool(data["dc_switch_enabled"]), profile)
        if "liftoff_index" in data and data["liftoff_index"]:
            self.set_liftoff(int(data["liftoff_index"]), profile)

    def read_status(self, timeout_s: float = 10.0) -> Optional[dict]:
        """Waits for one live status input report (report ID 7).

        hidraw byte0 is the report ID; the official WebHID parser sees the
        payload AFTER that byte, so field indices below are payload-relative:
          o[0]: conProtocol (low nibble: 0 = wireless/2.4G link active,
                2 = wired — verified against official bundle 2026-09-26:
                getDefaultConnectionProtocol returns 0 when tracked type
                is wireless(165), 2 when wired(255); the "Line -> Wireless"
                transition fires on conProtocol==0, "Wireless -> Line" on
                conProtocol==2) | sensor class (high nibble)
          o[1]: active DPI stage index
          o[2..3]: DPI X (LE u16), o[4..5]: DPI Y (LE u16)
          o[6]: battery level-validity flag (0 = level valid/discharging;
                any other value shown raw — the retail parser defines no
                charging enum here, unlike the Telink path)
          o[7]: battery percent (wired: still reports last-known cell level;
                expect ~1% right after replug); o[8]: backlight mode
          o[9]: key scan-rate index; o[10]: polling-rate raw code
          o[11]: selected profile; o[12..13]: USB PID (LE u16)
          o[14]: key/wheel type; o[15]: RF type; o[16]: sensor-mode preset
          o[17]: bit7 = RF connected, bits0-6 = RF RSSI

        Push cadence (measured on wired VT0 Air MAX, 2026-09-25): the mouse
        pushes report 7 roughly every ~3s on the cable too — NOT only on
        connect/param-change as previously assumed. The earlier wired
        timeouts were a stale-queue race: a trigger read issued while a
        heartbeat was already queued could consume/split the delivery
        window. Fix: read WITHOUT the trigger first (up to ~4s); only if
        nothing arrives, send the harmless 1-byte EEPROM read and wait
        again. Default timeout 10s covers at least two heartbeat periods
        plus trigger latency.
        """
        raw = self.transport.wait_for_report(STATUS_REPORT_ID,
                                             timeout_s=min(4.0, timeout_s))
        if raw is None and timeout_s > 4.0:
            try:
                self.read_memory(OFFSET_MOUSE_DPI_CUR, 1, profile=0)
            except Exception:
                pass  # trigger is best-effort; fall through to second wait
            raw = self.transport.wait_for_report(
                STATUS_REPORT_ID, timeout_s=timeout_s - 4.0)
        if raw is None or len(raw) < 13:
            return None
        o = raw[1:]  # strip hidraw report-ID byte -> official payload view
        con = o[0] & 0x0F
        # conProtocol: 0 = wireless (2.4G link active), 2 = wired.
        conn = {0: "2.4GHz receiver", 2: "usb wired"}.get(con, f"unknown ({con})")
        bat_raw = o[6]
        out: Dict[str, Any] = {
            "connect_type": conn,
            "sensor_class": (o[0] >> 4) & 0x0F,
            "dpi_stage": o[1],
            "dpi_x": o[2] | (o[3] << 8),
            "dpi_y": o[4] | (o[5] << 8),
            "battery_status": "level valid" if bat_raw == 0 else f"raw {bat_raw}",
            "battery_percent": o[7],
            "backlight_mode": o[8],
            "key_scan_rate_index": o[9],
            "polling_raw": o[10],
            "polling_rate": POLLING_RATE_LABELS.get(o[10], f"raw {o[10]}"),
            "profile": o[11],
            "raw": " ".join(f"{b:02X}" for b in raw[:19]),
        }
        if len(o) > 13:
            out["usb_pid"] = f"0x{(o[12] | (o[13] << 8)):04x}"
        if len(o) > 14:
            out["key_wheel_type"] = o[14]
        if len(o) > 15:
            out["rf_type"] = o[15]
        if len(o) > 16:
            out["sensor_mode_raw"] = o[16]
            out["sensor_mode_preset"] = SENSOR_MODE_VALUES.get(o[16], f"raw {o[16]}")
        if len(o) > 17:
            out["rf_connected"] = bool((o[17] >> 7) & 1)
            out["rf_rssi"] = o[17] & 0x7F
        return out

    # ------------------------------------------------------------------
    # Dongle pairing (receiver re-link). EXPERIMENTAL / state-changing.
    # ------------------------------------------------------------------
    def _pair_cmd(self, payload: bytes | List[int], resp_len: int = 2) -> bytes:
        """One legacy pairing frame via report 6, result via feature 8.

        Empirically determined on wired VT0 Air MAX: pairing frames need
        the connection-type prefix (CONN_WIRED) like EEPROM frames, i.e.
        [0xFF, 161, 1] — the raw official WebHID bytes [161, 1] get no
        reply at all (all-zero feature report). Reply payload byte0 is
        the ACK (1 = ok); result value (if any) follows.
        """
        frame = [self.connection_type] + [int(b) for b in bytes(payload)]
        self.transport.send_output_report(REPORT_ID_OUTPUT, bytes(frame))
        time.sleep(0.010)
        resp = self.transport.get_feature_report(REPORT_ID_FEATURE, 33)
        status, data = parse_feature_response(resp, payload_offset=self.payload_offset)
        if status != 1:
            raise RapooProtocolError(f"pairing cmd {list(payload)} ACK={status}")
        if len(data) < resp_len:
            raise RapooProtocolError(
                f"pairing cmd {list(payload)} short reply ({len(data)}B)"
            )
        return data

    def pair_query_status(self) -> dict:
        """Read-only pairing/link state query. Safe, but HONEST ABOUT LIMITS.

        Measured on wired VT0 Air MAX (2026-09-25): the queries return
        ACK=1 with an all-zero payload, i.e. the wired firmware exposes
        NO link state here. We report exactly that (raw zeros) instead of
        pretending `paired: False` is a real link judgment.
        """
        out: Dict[str, Any] = {}
        try:
            data = self._pair_cmd(PAIR_STATUS)
            out["pairing_status_raw"] = data[1]
            out["paired"] = bool(data[1] == 1)
            if data[1] == 0 and all(b == 0 for b in data):
                out["note"] = "all-zero reply: wired fw exposes no link state here"
        except RapooProtocolError as e:
            out["pairing_status_error"] = str(e)
        try:
            data = self._pair_cmd([PAIR_READ_WORK_MODE])
            out["work_mode"] = data[1]
            out["in_pairing_mode"] = bool(data[1] == PAIR_MODE_PAIRING)
        except RapooProtocolError as e:
            out["work_mode_error"] = str(e)
        return out

    def pair_receiver(
        self,
        timeout_s: float = 40.0,
        poll_interval_s: float = 0.2,
        dry_run: bool = True,
    ) -> dict:
        """Re-pair the mouse to its 2.4GHz receiver. STATE-CHANGING.

        Official flow (WebHID VTNrf54L pairing). Prerequisites:
          1. Mouse on USB CABLE (wired interface) — pairing frames go
             to the mouse through the wired link.
          2. The 2.4GHz dongle ALSO plugged in and put in pairing mode
             from its side (official UI pairs the receiver object; on
             Linux use hub.rapoo.cn in Chrome, or the receiver button).
          3. Mouse sends: switch_work_mode(129) -> clear_code_status ->
             code_match_mode + 4 random RF-address bytes, then polls
             device_pairing_status until byte1 == 1 (or work mode back
             to 0 — the official client accepts either as success).

        dry_run=True (default) sends nothing; reports prerequisite
        checks and the exact frame sequence. dry_run=False performs
        the live handshake. Clearing the old RF pairing breaks the
        current wireless link until the receiver confirms — keep the
        cable plugged in so you can always retry afterwards.

        LIVE-PAIRING STATUS (tested on wired VT0 Air MAX, 2026-09-25):
        read-only queries ([FF,161,1] / [FF,167]) return ACK=1 but an
        all-zero payload — the wired firmware does not expose the link
        state this way. switch_work_mode(129) is NAKed (all-zero, then
        busy). The live path is therefore DISABLED below: --confirm
        refuses with an explanation instead of sending frames that
        cannot complete. Re-pair via hub.rapoo.cn (Chrome) or the
        Windows driver, which drive the RECEIVER-side handshake.
        """
        steps = [
            {"cmd": [PAIR_SWITCH_WORK_MODE, PAIR_MODE_PAIRING],
             "desc": "enter pairing mode"},
            {"cmd": list(PAIR_CLEAR_CODE), "desc": "clear current RF pairing"},
            {"cmd": list(PAIR_CODE_MATCH) + ["<rand>"] * 4,
             "desc": "offer new 4-byte RF address"},
            {"cmd": list(PAIR_STATUS),
             "desc": "poll pairing status until byte1 == 1"},
        ]
        wired = self.connection_type == CONN_WIRED
        result: Dict[str, Any] = {
            "dry_run": dry_run, "wired": wired,
            "connection_type": self.connection_type, "steps": steps,
        }
        if not wired:
            result["ok"] = False
            result["error"] = (
                "pairing requires the mouse on USB cable. "
                "Connect the cable, then retry."
            )
            return result
        result["pre_state"] = self.pair_query_status()
        if dry_run:
            result["ok"] = True
            result["note"] = (
                "dry run: no frames sent. Live pairing is currently "
                "disabled: the wired firmware NAKs switch_work_mode "
                "(see docstring). Use hub.rapoo.cn to re-pair."
            )
            return result
        result["ok"] = False
        result["error"] = (
            "live pairing is disabled: the wired VT0 Air MAX firmware NAKs "
            "switch_work_mode(129) (tested 2026-09-25), so the handshake "
            "cannot complete from the mouse side. Re-pair with the official "
            "web driver (hub.rapoo.cn in Chrome, dongle + mouse connected) "
            "or the Windows driver, which drive the receiver-side handshake."
        )
        return result

