# Rapoo Linux

Linux support for **Rapoo** gaming mice (primary target: **VT3 Air**,
dongle `24ae:14a1`) - a `udev` rule that unlocks Rapoo's **official web
driver** on Linux, plus a reverse-engineered `rapoo` CLI for scripting,
backups and diagnostics.

> Protocol reverse engineering based on the official Windows driver
> ("A HUB" v1.0.19), the official WebHID driver at `hub.rapoo.cn`, and
> live VT3 Air / VT0 Air MAX hardware captures. See `docs/` for findings.

## Install

```bash
git clone git@github.com:pedro3z0/rapoo-software-linux.git
cd rapoo-software-linux
./install.sh
```

`./install.sh` does exactly two things:

1. **udev rule** (the only step needing `sudo`) - grants unprivileged
   access to Rapoo `/dev/hidraw*` nodes. This unlocks **both** Rapoo's
   official web driver **and** the `rapoo` CLI.
2. **`rapoo` command** - a symlink in `~/.local/bin` pointing at the
   bundled launcher. The CLI is pure-stdlib Python 3 (>= 3.9): no venv,
   no pip, no packages, works from any directory.

Optionally: `./install.sh --dev` also creates `.venv` with `pytest` for
running the test suite.

## Recommended: use Rapoo's official web driver (main UI)

Rapoo ships a full WebHID configurator that runs **natively in the
browser** - no installers, no Windows:

1. Run `./install.sh` (udev rule).
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

## `rapoo` CLI: scripting, backups, diagnostics

After `./install.sh` the command is on your PATH:

```bash
rapoo list                           # enumerate Rapoo HID endpoints
rapoo get                            # read all settings (add --json)
rapoo status                         # live report: battery, connection, DPI
```

No install needed to try it from a clone:

```bash
./rapoo get
```

### Battery level & connection type

Battery percentage and the active connection (2.4GHz receiver / USB wired)
are only available in the live status report (input report 7, ~3s
heartbeat), not in EEPROM:

```bash
rapoo status --json
```

Example output (wireless dongle):

```
connect_type     2.4GHz receiver
battery_status   raw 1
battery_percent  93
dpi_stage        2
dpi_x/dpi_y      1600 / 1600
polling_rate     2000Hz
rf_connected     True
rf_rssi          38
raw              07 20 01 40 06 40 06 01 5D ...
```

Change settings (always writes an automatic backup to
`analysis/backups/auto_backup_latest.json` first):

```bash
# DPI
rapoo set --dpi 3200 --stage 1        # set stage 1 to 3200 DPI
rapoo set --stage 2                   # switch active stage to 2

# Performance (see docs/PROTOCOL.md for the numeric encodings)
rapoo set --polling 8000Hz            # 125..8000 Hz
rapoo set --sensor-mode frenzy        # preset for the current polling rate
rapoo set --sensor-mode hyperCore --sensor-mode-at 4000Hz
rapoo set --key-scan 4000Hz           # key scan: 1000/2000/4000/8000 Hz

# Sensor & tracking
rapoo set --lod 1.1                   # lift-off distance in mm (model scale)
rapoo set --angle -3                  # sensor angle -30..+30 degrees
rapoo set --motion-sync on --glass off

# Wireless / RF
rapoo set --rf-boost maximum          # RF strategy: adaptive | maximum
rapoo set --rf-protocol turbo         # communication protocol: turbo | initial

# Power & alerts
rapoo set --sleep 10                  # wireless sleep timeout (minutes)
rapoo set --low-battery-light on
```

Backup & restore:

```bash
rapoo backup before-gaming.json
rapoo restore before-gaming.json
```

Also useful:

```bash
rapoo pair --query    # read-only dongle pairing state (live pairing is
                      # disabled on purpose; re-pair via hub.rapoo.cn)
```

## Repository layout

```
rapoo                        CLI launcher (symlinked to ~/.local/bin)
install.sh                   udev rule + `rapoo` command (+ optional --dev)
docs/                        PROTOCOL.md, DEVICES.md, ORIGINAL_ARTIFACT.md
tools/                       IFW payload extractor, PE helpers, verifiers
analysis/                    Local-only extracted payloads (git-ignored)
analysis/manifests/          Committed manifests (device table, payload hashes)
backend/rapoo/               Protocol library + CLI (pure stdlib, no deps)
backend/tests/               pytest suite (needs --dev install)
packaging/udev/              99-rapoo.rules (enables official web UI + CLI)
```

## Setup details

```bash
# What install.sh does (manual steps):
sudo cp packaging/udev/99-rapoo.rules /etc/udev/rules.d/
sudo udevadm control --reload-rules && sudo udevadm trigger
# then unplug/replug the dongle
ln -sfn "$PWD/rapoo" ~/.local/bin/rapoo

# Dev environment (tests only):
./install.sh --dev
.venv/bin/python -m pytest backend/tests/
```

Run the CLI without installing anything:

```bash
./rapoo get                # from the repo root, or
PYTHONPATH=. python3 -m backend.rapoo.cli get
```

Troubleshooting:

- `rapoo: command not found` - `~/.local/bin` not on PATH (the installer
  warns about this); add `export PATH="$HOME/.local/bin:$PATH"` to your
  shell profile, or run `./rapoo` from the repo.
- `Permission denied on /dev/hidraw1` - udev rule not installed or device
  not re-plugged. The CLI prints the fix; the official web UI will show a
  device-picker error for the same reason.
- `status` shows nothing - wake the mouse by moving it, then retry with
  `--timeout 15`.
- **Values look wrong** (e.g. linear/ripple show enabled while the official
  web UI shows them disabled): the CLI auto-calibrates the response payload
  offset on the first read by checking known-value registers (polling code,
  key-scan index, DPI stage). If calibration ever fails or picks the wrong
  layout, force it: `RAPOO_DATA_OFFSET=5 ./rapoo get` (try 5, then 4, then
  6), and inspect the raw bytes of any register with:

  ```bash
  ./rapoo raw --offset 704 --length 8 --json
  ```

  The `raw` output shows the response buffer plus what each candidate
  payload offset (`payload@4`, `@5`, `@6`) would yield.

## Safety policy

- The original installer is **never modified**; verify with
  `./tools/verify_original.sh /path/to/A HUB_Game_Win_V1.0.19.exe`
  (default location is the repo root; pass the path if you keep it
  elsewhere).
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

MIT - see [LICENSE](LICENSE).
The extracted Rapoo payload is not covered by this license and is not
distributed with this repository.
