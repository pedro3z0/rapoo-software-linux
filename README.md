# Rapoo Linux

Linux support for **Rapoo** gaming mice (primary target: **VT0 Air Max**,
dongle `24ae:14a1`) - a `udev` rule that unlocks Rapoo's **official web
driver** on Linux, plus a reverse-engineered Python CLI for scripting,
backups and diagnostics.

> Protocol reverse engineering based on the official Windows driver
> ("A HUB" v1.0.19), the official WebHID driver at `hub.rapoo.cn`, and
> this machine's live VT3 Air dongle. See `docs/` for findings.

## Recommended: use Rapoo's official web driver (main UI)

Rapoo ships a full WebHID configurator that runs **natively in the
browser** - no installers, no Windows:

1. Install this project's udev rule (one command, see below).
2. Unplug/replug your dongle (or reboot).
3. Open **https://hub.rapoo.cn/** (international: https://hub.rapoo.com/)
   in **Chrome, Edge, or Chromium** and click *Connect Device*.

The udev rule is the only missing piece on Linux - without it the browser
cannot open `/dev/hidraw*`. Features in the official web UI include DPI
stages, polling rate, performance presets, button remapping, macros,
lighting, battery info and firmware updates. It supports 100+ Rapoo models
(extracted device table: `analysis/manifests/official_web_models.json`).

Because the official UI is the primary experience, this repository does
**not** ship its own web UI anymore.

## CLI (this repository): scripting, backups, diagnostics

```bash
./install.sh    # udev rule + Python venv (uses uv)

.venv/bin/python -m backend.rapoo.cli list      # enumerate Rapoo HID endpoints
.venv/bin/python -m backend.rapoo.cli get       # read all settings (human or --json)
.venv/bin/python -m backend.rapoo.cli status    # live report: battery, DPI, polling
```

### Battery level & connection type

Battery percentage and the active connection (2.4GHz receiver / Bluetooth /
USB wired) are only available in the live periodic status report, not in
EEPROM. Print them with:

```bash
.venv/bin/python -m backend.rapoo.cli status --json
```

If nothing arrives within the timeout, move the mouse first (it sleeps) and
raise the timeout: `status --timeout 5`. Example output:

```
connect_type     2.4GHz receiver
battery_status   valid
battery_percent  87
dpi_stage        2
dpi_x/dpi_y      3200 / 3200
polling_24g      1000Hz
profile          0
raw              07 20 02 80 0C 80 0C 01 57 00 01 01 00 ...
```

Change settings (always writes an automatic backup to
`analysis/backups/auto_backup_latest.json` first):

```bash
# DPI
... cli set --dpi 3200 --stage 1        # set stage 1 to 3200 DPI
... cli set --stage 2                   # switch active stage to 2

# Performance (see docs/PROTOCOL.md for the numeric encodings)
... cli set --polling 8000Hz            # 125..8000 Hz
... cli set --sensor-mode frenzy        # preset for the current polling rate
... cli set --sensor-mode hyperCore --sensor-mode-at 4000Hz
... cli set --key-scan 4000Hz           # key scan pipeline: 1000/2000/4000/8000 Hz

# Sensor & tracking
... cli set --lod 1.1                   # lift-off distance in mm (model scale)
... cli set --angle -3                  # sensor angle -30..+30 degrees
... cli set --motion-sync on --glass off

# Wireless / RF
... cli set --rf-boost maximum          # RF strategy: adaptive | maximum
... cli set --rf-protocol turbo         # communication protocol: turbo | initial

# Power & alerts
... cli set --sleep 10                  # wireless sleep timeout (minutes)
... cli set --low-battery-light on
```

Backup & restore:

```bash
... cli backup before-gaming.json
... cli restore before-gaming.json
```

## Repository layout

```
A HUB_Game_Win_V1.0.19.exe   Original Windows driver installer (read-only, hash-pinned)
docs/                        PROTOCOL.md, DEVICES.md, ORIGINAL_ARTIFACT.md
tools/                       IFW payload extractor, PE analysis helpers, verifiers
analysis/                    Local-only extracted payloads (git-ignored)
analysis/manifests/          Committed manifests (device table, payload hashes)
backend/rapoo/               Protocol library + CLI (pure Python, no native deps)
packaging/udev/              99-rapoo.rules (enables official web UI + CLI)
```

## Setup details

```bash
# What install.sh does (manual steps):
sudo cp packaging/udev/99-rapoo.rules /etc/udev/rules.d/
sudo udevadm control --reload-rules && sudo udevadm trigger
# then unplug/replug the dongle
uv venv .venv && uv pip install --python .venv/bin/python pytest
```

Troubleshooting:

- `Permission denied on /dev/hidraw1` - udev rule not installed or dongle
  not re-plugged. The CLI prints the fix; the official web UI will show a
  device-picker error for the same reason.
- `status` shows nothing - wake the mouse by moving it, then retry with
  `--timeout 5`.
- **Values look wrong** (e.g. linear/ripple show enabled while the official
  web UI shows them disabled): the CLI auto-calibrates the response payload
  offset on the first read by checking known-value registers (polling code,
  key-scan index, DPI stage). If calibration ever fails or picks the wrong
  layout, force it: `RAPOO_DATA_OFFSET=5 .venv/bin/python -m backend.rapoo.cli get`
  (try 5, then 4, then 6), and inspect the raw bytes of any register with:

  ```bash
  .venv/bin/python -m backend.rapoo.cli raw --offset 704 --length 8 --json
  ```

  The `raw` output shows the response buffer plus what each candidate
  payload offset (`payload@4`, `@5`, `@6`) would yield.

## Safety policy

- The original installer is **never modified**; verify with
  `./tools/verify_original.sh`.
- Extracted Rapoo binaries stay local (`analysis/` is git-ignored) and are
  never committed or redistributed.
- CLI writes are guarded: automatic JSON backup before the first change,
  ACK-checked protocol with retries, and `restore` to roll back.
- Firmware flashing is out of scope on purpose (use the official web UI).

## Documentation

- `docs/PROTOCOL.md` - full HID protocol spec + **numeric encodings**
  (polling codes, presets, LOD scales, RF values, status report layout)
- `docs/DEVICES.md` - supported device matrix (100+ models)
- `docs/ORIGINAL_ARTIFACT.md` - provenance and hashes of the reference driver

## License
MIT
