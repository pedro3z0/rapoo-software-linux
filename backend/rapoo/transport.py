# -*- coding: utf-8 -*-
"""Linux hidraw transport for Rapoo gaming devices.

Features:
- Pure python / ioctl implementation without requiring libhidapi C binaries
- Handles Report ID 6 output reports (write) and Report ID 8 feature reports (read)
- Robust retry loop with busy-ack detection (0x02 status)
- Response layout auto-detection: the official WebHID driver validates
  byte0 as the ACK status (1=ok, 2=busy), which means *its* view of a
  feature report starts with the status byte. On Linux HIDIOCGFEATURE the
  buffer may either mirror that layout (status at index 0) or contain the
  report ID first (status at index 1, payload at index 5). We detect which
  layout the kernel returns and slice consistently. Set RAPOO_DATA_OFFSET=4
  or =5 to force a layout while debugging.
"""
from __future__ import annotations

import os
import re
import fcntl
import glob
import select
import time
from dataclasses import dataclass
from typing import Optional, List, Tuple
from pathlib import Path

from .protocol import (
    REPORT_ID_OUTPUT,
    REPORT_ID_FEATURE,
    ACK_OK,
    ACK_BUSY,
    build_read_packet,
    build_write_packet,
    get_address,
    CONN_WIRELESS,
    CONN_WIRED
)

# Linux HIDRAW IOCTL definitions
IOC_WRITE = 1
IOC_READ = 2
IOC_NRSHIFT = 0
IOC_TYPESHIFT = 8
IOC_SIZESHIFT = 16
IOC_DIRSHIFT = 30


def _IOC(dir_: int, type_: str, nr: int, size: int) -> int:
    return (dir_ << IOC_DIRSHIFT) | (ord(type_) << IOC_TYPESHIFT) | (nr << IOC_NRSHIFT) | (size << IOC_SIZESHIFT)


def HIDIOCSFEATURE(length: int) -> int:
    return _IOC(IOC_WRITE | IOC_READ, 'H', 0x06, length)


def HIDIOCGFEATURE(length: int) -> int:
    return _IOC(IOC_WRITE | IOC_READ, 'H', 0x07, length)


@dataclass
class DeviceEndpoint:
    path: str
    vendor_id: int
    product_id: int
    interface_num: int
    name: str = ""


class RapooProtocolError(RuntimeError):
    """Raised when the device returned an unexpected/unparseable response."""


# Response payload offsets in a feature-report response buffer:
#   4 -> Layout A (report ID stripped, matches official WebHID view)
#   5 -> Layout B (report ID present: [0x08, status, echo x3, data...])
PAYLOAD_OFFSET_CANDIDATES = (5, 4, 6)

# Status input reports (report ID 7) arrive through hidraw with the report ID
# as byte 0. The official WebHID parser sees the payload WITHOUT that byte
# (reportId delivered separately), so every field index shifts by +1 here:
#   official o[0] (conProtocol|sensor) == hidraw raw[1], etc.
STATUS_REPORT_ID = 7


def response_status_index(resp: bytes) -> int:
    """Index of the ACK status byte for this response buffer."""
    if resp and resp[0] in (ACK_OK, ACK_BUSY):
        return 0
    return 1


def parse_feature_response(resp: bytes, payload_offset: int | None = None) -> tuple[int, bytes]:
    """Return (ack_status, payload) for a feature report response.

    payload_offset: explicit payload start (4, 5 or 6). When None, the
    layout is guessed from the buffer (env override RAPOO_DATA_OFFSET wins).
    Device code should prefer its calibrated offset via RapooMouse.
    """
    if not resp:
        raise RapooProtocolError("empty response from device")
    forced = os.environ.get("RAPOO_DATA_OFFSET")
    if payload_offset is None and forced:
        payload_offset = int(forced)
    status = resp[response_status_index(resp)] if len(resp) > 1 else resp[0]
    if payload_offset is None:
        # Layout A if the status byte sits at index 0, else assume report ID first.
        payload_offset = 4 if response_status_index(resp) == 0 else 5
    return status, resp[payload_offset:]


class RapooTransport:
    def __init__(self, hidraw_path: str):
        self.path = hidraw_path
        self._fd: Optional[int] = None

    def open(self):
        if self._fd is not None:
            return
        self._fd = os.open(self.path, os.O_RDWR)

    def close(self):
        if self._fd is not None:
            try:
                os.close(self._fd)
            except OSError:
                pass
            self._fd = None

    def __enter__(self):
        self.open()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

    def send_output_report(self, report_id: int, payload: bytes):
        """Sends an output report via standard POSIX write()."""
        if self._fd is None:
            raise RuntimeError("Device is not open")
        # report_id is the first byte followed by the payload
        buf = bytes([report_id]) + payload
        os.write(self._fd, buf)

    def get_feature_report(self, report_id: int, length: int = 33) -> bytes:
        """Retrieves a feature report via HIDIOCGFEATURE ioctl."""
        if self._fd is None:
            raise RuntimeError("Device is not open")
        # Prepare buffer with report_id at index 0
        buf = bytearray(length)
        buf[0] = report_id
        res = fcntl.ioctl(self._fd, HIDIOCGFEATURE(length), buf)
        # res returns the number of bytes read
        return bytes(buf)

    def read_input_report(self, timeout_s: float = 2.0) -> Optional[bytes]:
        """Blocks up to timeout_s for one input report (e.g. status report 7).

        NOTE: hidraw read() returns the report ID as byte 0 (unlike WebHID
        DataViews, where the ID is delivered separately). Callers must
        account for this 1-byte shift when comparing against the official
        WebHID parser layouts.
        """
        if self._fd is None:
            raise RuntimeError("Device is not open")
        r, _, _ = select.select([self._fd], [], [], timeout_s)
        if not r:
            return None
        return os.read(self._fd, 512)

    def wait_for_report(self, report_id: int, timeout_s: float = 2.0) -> Optional[bytes]:
        """Blocks up to timeout_s for one input report with the given ID.

        Keeps consuming and discarding non-matching reports until the wanted
        ID arrives or the deadline passes. Does NOT pre-flush: the device
        pushes status reports rarely (wired: only on connect/param change),
        so a queued report may be the only one we get.
        """
        if self._fd is None:
            raise RuntimeError("Device is not open")
        deadline = time.time() + timeout_s
        while time.time() < deadline:
            remaining = max(0.05, deadline - time.time())
            r, _, _ = select.select([self._fd], [], [], remaining)
            if not r:
                break
            try:
                chunk = os.read(self._fd, 512)
            except OSError:
                break
            if chunk and chunk[0] == report_id:
                return chunk
        return None

    def request(self, payload: bytes, timeout_ms: int = 2000, max_retries: int = 5) -> bytes:
        """Sends command via output report 6 and reads back response via feature report 8."""
        self.send_output_report(REPORT_ID_OUTPUT, payload)
        start = time.time()
        for attempt in range(max_retries):
            if (time.time() - start) * 1000 > timeout_ms:
                raise TimeoutError(f"Rapoo request timed out after {timeout_ms}ms")
            time.sleep(0.010)  # 10ms delay for wireless dongle
            resp = self.get_feature_report(REPORT_ID_FEATURE, 33)
            status = resp[response_status_index(resp)] if len(resp) > 1 else resp[0]
            if status != ACK_BUSY:
                return resp
            time.sleep(0.050)
        raise TimeoutError("Rapoo device busy after max retries")


def enumerate_rapoo_endpoints() -> List[DeviceEndpoint]:
    """Finds all connected Rapoo hidraw interfaces on Linux."""
    endpoints = []
    for uevent_path in glob.glob("/sys/class/hidraw/hidraw*/device/uevent"):
        try:
            with open(uevent_path, "r", encoding="utf-8") as f:
                content = f.read()
            props = {}
            for line in content.splitlines():
                if "=" in line:
                    k, v = line.split("=", 1)
                    props[k.strip()] = v.strip()
            
            # HID_ID format: 0003:000024AE:000014A1
            hid_id = props.get("HID_ID", "")
            parts = hid_id.split(":")
            if len(parts) >= 3:
                vid = int(parts[1], 16)
                pid = int(parts[2], 16)
                if vid == 0x24AE:
                    dev_name = props.get("HID_NAME", "Rapoo Device")
                    hidraw_node = "/dev/" + Path(uevent_path).parent.parent.name
                    # Parse interface from real sysfs parent directory, e.g. 1-7:1.1
                    real_parent = os.path.realpath(os.path.dirname(uevent_path))
                    # Match :1.<ifnum>/
                    # Find the USB interface number (e.g. 1-7:1.1 -> interface 1)
                    match = re.search(r'/\d+-\d+(?:\.\d+)*:\d+\.(\d+)/', real_parent)
                    ifnum = int(match.group(1)) if match else 0

                    endpoints.append(DeviceEndpoint(
                        path=hidraw_node,
                        vendor_id=vid,
                        product_id=pid,
                        interface_num=ifnum,
                        name=dev_name
                    ))
        except Exception:
            pass
    return sorted(endpoints, key=lambda ep: ep.interface_num)

