# Rapoo Gaming Mouse Protocol Specification

This document describes the native USB/Wireless HID communication protocol used by modern
**Rapoo VT and gaming devices** (e.g. VT3 Air, VT0 Air MAX, VT3 Pro, VT9, etc.),
reverse-engineered from the official Windows driver ("A HUB" v1.0.19) and the official Rapoo
Web Driver ("RAPOO HUB 2.0" at `hub.rapoo.cn`).

---

## 1. Physical & HID Layer

Rapoo 2.4GHz USB receivers present multiple HID interfaces:
- **Interface 0 (Boot Mouse)**: Standard 8-byte mouse input reports for OS cursor motion.
- **Interface 1 (System / Custom Control)**:
  - Report ID 6: **Output Report** (32 bytes) — Host-to-Device command packets.
  - Report ID 8: **Feature Report** (32 bytes) — Device-to-Host response packets.
  - Report ID 7: Periodic device status / battery input report.
  - Usage Page: `0xFF00` (Vendor-defined), Usage: `0x02` (Configuration Interface) or `0x0E`.
- **Interface 2 (Firmware / Bulk)**: 512-byte raw vendor frames (OTA updates; avoid in regular config).

---

## 2. Memory Architecture

Settings on the mouse microcontroller are mapped as a virtual EEPROM space organized into
up to 8 profiles (default active profile is profile 0):

```
Base Address for Profile 0: 1536 (0x0600)
Base Address for Profile 1: 2560 (0x0A00)
Base Address for Profile 2: 3584 (0x0E00)
...
Step: +1024 bytes per profile
```

### Memory Offsets (relative to profile base)

| Offset | Size (Bytes) | Field Name | Description |
|---|---|---|---|
| 0 | 4 | `MOUSE_LEFT` | Left mouse button action mapping |
| 4 | 4 | `MOUSE_MID` | Middle button action mapping |
| 8 | 4 | `MOUSE_RIGHT` | Right button action mapping |
| 12 | 4 | `MOUSE_CPIADD` | DPI Up button action mapping |
| 16 | 4 | `MOUSE_CPIREDUCE` | DPI Down button action mapping |
| 20 | 4 | `MOUSE_FORWARD` | Forward side button action mapping |
| 24 | 4 | `MOUSE_BACK` | Back side button action mapping |
| 640 | 1 | `MOUSE_REPORT` | Polling rate code (see below) |
| 641 | 1 | `MOUSE_SCAN_RATE` | Key scan rate |
| 644 | 1 | `MOUSE_SLIGHT` | Silent height / Lift-Off Distance (LOD) |
| 645 | 1 | `MOUSE_MOTION` | Motion Sync switch (`1` = on, `0` = off) |
| 648 | 14 | `MOUSE_DPI_X_LIST` | 7 stages * 2 bytes LE (DPI value X-axis) |
| 662 | 1 | `MOUSE_DPI_ENABLE_GEAR` | Number of enabled stages minus 1 |
| 664 | 1 | `MOUSE_DPI_CUR` | Currently active stage index (`0` to `6`) |
| 704 | 1 | `MOUSE_DOWNDELAY` | Key press debounce delay (ms) |
| 705 | 1 | `MOUSE_LIFTDELAY` | Key release debounce delay (ms) |
| 706 | 1 | `MOUSE_SLEEPTIME` | Wireless sleep timeout (minutes) |
| 707 | 1 | `MOUSE_LINEAR_RIPPLE` | Bit 0: linear correction, Bit 1: ripple correction |
| 708 | 1 | `MOUSE_SENSORANGLE` | Sensor angle offset (signed 8-bit, -30° to +30°) |
| 709 | 1 | `MOUSE_GLASS` | Glass tracking surface mode (`1` = on, `0` = off) |
| 712 | 14 | `MOUSE_DPI_Y_LIST` | 7 stages * 2 bytes LE (DPI value Y-axis) |

---

## 3. Packet Structure

All host commands are sent via **Output Report 6** (32 bytes payload + 1 byte report ID):

### 3.1 Memory Read Request (`CMD_READ_EEPROM` = `0xA4`)
```
Byte 0:  Connection Type (0xA5 for 2.4GHz Wireless, 0xFF for Wired USB)
Byte 1:  Command ID: 0xA4 (Read EEPROM)
Byte 2:  Length to read (in bytes)
Byte 3:  Address Byte 0 (LE)
Byte 4:  Address Byte 1 (LE)
Byte 5:  Address Byte 2 (LE)
Byte 6:  Address Byte 3 (LE)
Byte 7..31: 0x00 padding
```

### 3.2 Memory Write Request (`CMD_WRITE_EEPROM` = `0xA5`)
```
Byte 0:  Connection Type (0xA5 for 2.4GHz Wireless, 0xFF for Wired USB)
Byte 1:  Command ID: 0xA5 (Write EEPROM)
Byte 2:  Length of data payload (in bytes)
Byte 3:  Address Byte 0 (LE)
Byte 4:  Address Byte 1 (LE)
Byte 5:  Address Byte 2 (LE)
Byte 6:  Address Byte 3 (LE)
Byte 7..7+N-1: Data payload bytes
Rest: 0x00 padding
```

### 3.3 Response Packet (Feature Report 8)

Responses are retrieved with `HIDIOCGFEATURE` on Report ID 8. Two layouts
exist depending on whether the kernel keeps the report ID byte in the
returned buffer; `backend/rapoo/transport.py::parse_feature_response`
detects which one and slices consistently (override: `RAPOO_DATA_OFFSET=4|5`):

```
Layout A (report ID stripped - matches the official WebHID driver's view):
Byte 0:  Status ACK (0x01 = OK, 0x02 = Device Busy / Retry)
Byte 1-3: Echo (length/cmd/address fields)
Byte 4..: Requested Data payload

Layout B (report ID present, typical Linux HIDIOCGFEATURE):
Byte 0:  Report ID (0x08)
Byte 1:  Status ACK (0x01 = OK, 0x02 = Busy)
Byte 2-4: Echo
Byte 5..: Requested Data payload
```

The official WebHID driver validates `byte0 === 1` after every read and
write, which is how Layout A was determined to be its reference view.

Because Linux kernels differ in this behaviour, `RapooMouse` **auto-calibrates**
the payload offset on the first read by validating known-value registers
(polling code at 640, key-scan index at 641, lift-off index at 644, motion
flag at 645, active DPI stage at 664). A wrong offset silently misreads
neighbouring registers - e.g. reading the sleep timeout (0x0F) where the
linear/ripple byte was expected makes both corrections appear enabled.
Override with `RAPOO_DATA_OFFSET=4|5|6` and inspect with
`rapoo.cli raw --offset <reg> --length <n>`.

---

## 4. Polling Rate Values

Modern nRF54L family retail devices map polling rates to hardware codes as follows:

| Hardware Code | Polling Rate |
|---|---|
| `8` | 125 Hz |
| `4` | 250 Hz |
| `2` | 500 Hz |
| `1` | 1000 Hz |
| `132` (0x84) | 2000 Hz |
| `130` (0x82) | 4000 Hz |
| `129` (0x81) | 8000 Hz |


## 5. Performance Subsystem (from reference `software3_small.jpg`)

The official desktop driver exposes a **Performance panel** with three interlocking controls:

### 5.1 Global Polling Rate (`MOUSE_REPORT`, offset 640)

One byte per profile; raw hardware codes:
`8=125Hz`, `4=250Hz`, `2=500Hz`, `1=1000Hz`, `132=2000Hz`, `130=4000Hz`, `129=8000Hz`.
The reference UI highlights these steps: 125 / 250 / 500 / 1000 / 2000 / 4000 / 8000 Hz.

### 5.2 Performance presets / "sensor mode" (profile base + 732, 7 bytes)

Each of the 7 polling-rate slots keeps its own preset value (the official
`MOUSE_REPORT_SENSOR_MODE` address builder adds profile base **and** the
slot index, so this region is profile-relative, not global). Slot order
equals `POLLING_RATE_SLOTS` = `[125, 250, 500, 1000, 2000, 4000, 8000 Hz]`.

Preset values for `sensorScanRateLabel:"13K"` retail devices (official EV
table; this covers VT0 Air MAX / VT3 Air and 65 other models):

| Value | Preset |
|---|---|
| `0` | office |
| `1` | balanced |
| `2` | firepower |
| `3` | hyperCore |
| `4` | competitive |
| `5` | frenzy |

Official UI copies: frenzy = ">= 20K engine rate", competitive = full-speed
racing, hyperCore = esports microsecond response, firepower = gaming,
balanced = low power, office = daily use.

Which presets are legal at which polling rate (official VV table):

| Polling code | Allowed preset values |
|---|---|
| `8` (125Hz) | `[1, 0]` - balanced/office only |
| `4` (250Hz) | `[1, 0]` |
| `2` (500Hz) | `[2, 1, 0]` |
| `1` (1000Hz) | `[5, 4, 3, 2, 1]` |
| `132` (2000Hz) | `[5, 4, 3, 2]` |
| `130` (4000Hz) | `[5, 4, 3]` - performance presets only |
| `129` (8000Hz) | `[5, 4, 3]` - frenzy/competitive/hyperCore only |

(`set_sensor_mode()` validates against this table before writing.)

### 5.3 Key Scan Rate (profile offset 641)

Buttons are scanned independently of the motion pipeline. The stored value
is a plain UI index into the official `dd` label array:

| Stored index | Label |
|---|---|
| `0` / `1` / `2` | 125 / 250 / 500 Hz (not offered on retail) |
| `3` | **1000 Hz** (default) |
| `4` | **2000 Hz** |
| `5` | **4000 Hz** |
| `6` | **8000 Hz** |

The official `keyScanRates` capability only allows indices 3..6 on retail
devices, and the CLI enforces the same set.

### 5.4 Wireless RF strategy & communication protocol

| Setting | Address | Values |
|---|---|---|
| RF strategy (`RF_STRENGTHEN_SWITCH`) | profile base + 728 | `0` = Adaptive (signal-based power saving), `1` = Maximum RF (full power, better interference immunity) |
| Low-battery light (`LOW_POWE_WARN_SWITCH`) | profile base + 729 | `0` off, `1` on (LED flash alert) |
| DC switch (`LOW_DC_SWITCH`) | profile base + 730 | `0`/`1` - purpose undocumented |
| Communication protocol (`RF_PROTOCOL_SETTING`) | **global** offset 96 | `0` = Turbo ("efficient protocol", default), `2` = Initial; `1` undocumented |

### 5.5 Lift-off distance / "silent height" (profile offset 644)

Stores a **1-based** index into a model-specific millimetre scale (the
official UI validates `>= 1` and computes `silentHeight-1`):

| Scale | Values (mm) | Used by |
|---|---|---|
| LV (capability `l1`) | 0.7, 0.8, ... 1.7 | 65 models incl. **VT0 Air MAX / VT3 Air** (PAW3950U/3955U) |
| MV (capability `co`) | 1.0, 1.1, ... 2.0 | PAW3398 legacy models (VT0/VT1/VT2/VT3/VT3S/VT6/VT7/VT9, ESM*PRO) |

---

## 6. Numeric decoding cheat sheet

Every magic number the firmware stores, decoded:

### Polling / report rate (offset 640)

`8`=125Hz, `4`=250Hz, `2`=500Hz, `1`=1000Hz, `132`=2000Hz, `130`=4000Hz,
`129`=8000Hz. (Paw3311-tier devices instead use plain indices 0..3 =
125/250/500/1000Hz.)

### Key scan rate (offset 641)

Plain UI index: `3`=1000Hz, `4`=2000Hz, `5`=4000Hz, `6`=8000Hz
(default `3`). Retail devices only accept 3..6.

### Performance preset per polling slot (profile+732, 7 bytes)

`0`=office, `1`=balanced, `2`=firepower, `3`=hyperCore,
`4`=competitive, `5`=frenzy - one value per polling rate (slot order
125..8000Hz), restricted by the VV table in 5.2.

### Sensor scan-rate marketing labels

`"13K"` (67 official models, incl. VT3 Air) and `"10K"` (13 models) are the
optical engine's **frames-per-second** scan-rate class, not a Hz setting.
The `frenzy` preset is advertised as ">= 20K engine rate" in official copy.
The per-mode advertised scan values shown with `{scanRate}` in the UI are
engine measurements displayed next to the key scan rate.

### Sensor model IDs

The live status report's high nibble of byte 1 (`sensorTypeModel`) and the
manifest field `sensor` carry the PixArt model:
`PAW3311`, `PAW3398`, `PAW3950U`, `PAW3955U`. **The nibble -> model mapping
is not yet decoded** (needs one live capture of report 7 next to the known
manifest sensor - listed under Open items below).

### DPI limits by sensor tier (official capability tables)

| Capability | Range | Step | Typical sensors |
|---|---|---|---|
| `pt` | 10 - 45 000 | 10 (<=10050), 50 above | PAW3950U / PAW3955U |
| `P1` | 1 - 60 000 | 1 | high-end |
| `Lo` | 50 - 26 000 | 50 | PAW3398 |

The CLI currently hard-validates 50..30000 for compatibility; tighten per
model once verified live.

### Lift-off distance (offset 644)

`1..11` (1-based) into the LV scale (0.7..1.7mm, VT3 Air) or MV scale
(1.0..2.0mm, PAW3398 family) - see 5.5.

### RF / wireless bytes

- RF strategy (profile+728): `0`=Adaptive, `1`=Maximum RF
- Communication protocol (global 96): `0`=Turbo, `2`=Initial (`1` unknown)
- Low-battery light (profile+729): `0`/`1`; DC switch (profile+730): `0`/`1`
- Sensor angle (profile+708): signed, -30..+30 degrees
- Sleep timeout (profile+706): minutes (1..60 valid in CLI)
- Linear/ripple byte (profile+707): bit0 = angle snapping, bit1 = ripple
  correction; motion sync (profile+645) and glass tracking (profile+709):
  0/1

### Live status report (input report ID 7, experimental)

Sent periodically by the dongle/mouse (~3s heartbeat, measured on both
links); parsed by `RapooMouse.read_status()`. NOTE: byte numbers below
include the report-ID byte (hidraw view). The official WebHID parser sees
the payload WITHOUT the ID, so its indices are one less (o[0] == byte 1).

| Byte | Meaning |
|---|---|
| 0 | report id `0x07` |
| 1 | low nibble conProtocol: `0`=wireless (2.4G link active), `2`=wired (verified vs official bundle: `getDefaultConnectionProtocol` returns 0 for tracked-wireless(165), 2 for tracked-wired(255)); high nibble = sensor class |
| 2 | active DPI stage (0..6) |
| 3-4 | DPI X (u16 LE) |
| 5-6 | DPI Y (u16 LE) |
| 7 | battery level-validity flag: `0`=level valid; other values shown raw (retail parser defines no charging enum here) |
| 8 | battery percent 0..100 (wired: last-known cell level; ~1% right after replug is normal) |
| 9 | backlight mode |
| 10 | key scan-rate index |
| 11 | polling-rate raw code (single active rate; agrees with EEPROM `get` on both links) |
| 12 | active profile index |
| 13-14 | USB PID (u16 LE) |
| 15 | key/wheel type nibbles |
| 16 | RF type |
| 17 | sensor-mode preset |
| 18 | bit7 = RF connected, bits0-6 = RF RSSI |

### Open items (need one live capture each)

- `sensorTypeModel` nibble -> PAW model mapping
- Confirmation of both response layouts (RAPOO_DATA_OFFSET default) once the
  auto-calibration has run on hardware
- DC switch purpose; echo-byte semantics in feature responses
- Trailing status-report bytes 13..18 on nRF54L devices (parsed from the
  Telink path: usbPid, key/wheel type, rfType, sensorMode, rfConnected|rssi)

### Features still to adapt (roadmap)

- Button remapping and macros (EEPROM at `MACRO_*` addresses 64768+/65536+)
- Lighting / RGB (`MOUSE_LIGHTMOD` 665, `MOUSE_LIGHTRGB` 696) where present
- Profile management UI (8 profiles, names at 1004+offset)
- Battery history via status report (battery % already parsed)
- Dongle pairing/re-pairing (`code_match_mode` command) - higher risk

