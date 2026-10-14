# Rapoo TUI (Rust ratatui frontend)

Terminal UI for Rapoo gaming mice — keyboard-driven, no memorized flags.
Backend is the `rapoo` Python CLI via `--json` subprocess bridge (zero
protocol duplication in v1; native hidraw port is a v2 task).

## Build

```bash
cd tui && cargo build --release   # -> tui/target/release/rapoo-tui (1.4MB)
```

Or launch through the CLI (uses `release` if present, else `debug`):

```bash
./rapoo tui                        # profile 0
./rapoo tui --profile 2            # another profile
rapoo tui                          # after ./install.sh
```

Direct:

```bash
./tui/target/release/rapoo-tui --profile 0 --timeout 10
```

## Layout

## Layout (monsgeek-style)

1-line centered title (`device - Rapoo Configuration Tool` + right
`Profile N/8` chip) | 1-line tab bar (`│` dividers, yellow-bold active,
right hint) | bordered content list (key hints in the block title) |
1-line status bar (`[Connected 100%█|1000Hz] msg | ?:Help q:Quit`).

Editable values render as `< value >`. `?` opens a help popup.

| Tab | Rows | Edit keys |
|---|---|---|
| Dashboard | endpoints, link/battery/RF, all settings (~25 rows) | `R` refresh |
| DPI | 7 stages X/Y + active | `←/→` ±50 DPI, `Enter` exact, `s` switch stage |
| Performance | polling 125-8000Hz, preset office..frenzy + slots[7], key-scan | `←/→` cycle (VV-guarded), `Enter` exact |
| Sensor | LOD mm/idx + scale, angle, motion/glass/linear/ripple, debounce press/release 0-32ms | `←/→` cycle/step, `Space` toggle, `Enter` exact |
| Wireless | rf-boost, rf-protocol, live rssi/link | `←/→`, `Space` |
| Power | sleep 1-60min, low-bat, DC (undoc), battery bar | `←/→` step, `Space` toggle |
| Presets | named JSON in `~/.config/rapoo/presets/` + 2 builtins | `Enter` apply (confirm), `p` save, `b` backup |
| Diag | device list, pair query (read-only), raw 640/8 | `Enter` run row, `w` raw |

Global: `Up/Down`/`j k` move, `Tab`/`Shift+Tab`/`1-8` tabs,
`R` refresh all (`list`+`get`+`status`), `q/Esc` quit.
**All single-value writes apply instantly** (no y/n): the device's own
reply lands in the status bar and the list updates. `y/n` popups remain
only for preset apply and restore.

## Safety

* The CLI auto-backs-up to `analysis/backups/auto_backup_latest.json`
  before the first write of a session; `b` writes a `/tmp` backup
  instantly, `X` restores it (confirm).
* `pair --confirm` stays refused (wired fw NAKs it) — TUI only exposes
  the read-only query.
* Permission errors show the `./install.sh` + replug fix inline.

## Numeric encodings (verified 2026-10-14)

WebHID bundle `index-3ShGzFuu.js` (from `https://hid.rapoo.cn`):

```
EV=[{5,frenzy},{4,competitive},{3,hyperCore},{2,firepower},{1,balanced},{0,office}]
PV=[8,4,2,1,132,130,129]
VV={8:[1,0],4:[1,0],2:[2,1,0],1:[5,4,3,2,1],132:[5,4,3,2],130:[5,4,3],129:[5,4,3]}
dd=["125Hz","250Hz","500Hz","1000Hz","2000Hz","4000Hz","8000Hz"]
```

Marketing copy: `frenzy=≥20K engine/Corded Gaming`,
`competitive=≥{scanRate}KFPS/Corded Gaming` (interpolated with the model's
`sensorScanRateLabel` from the official driver device table — 80 models /
152 PIDs in `device_registry.py`),
`hyperCore=microsecond/Corded Gaming`, `firepower=High Performance`,
`balanced=Low Power`, `office=Office`.

## Custom presets — what is possible

**Level 1 (this TUI, safe):** named JSON snapshots of all EEPROM knobs
(polling + 7 sensor slots + key-scan + LOD + RF + DPI + sleep + toggles).
Save/load/diff/apply in the Presets tab. Reversible, ACK-checked.

**Level 2 (blocked):** a new DSP value like `6=myTune` needs a firmware
patch (51-write sensor init table, banks `0x05/0x09`, regs `0x41-0x5B`)
in the SHA512-signed Nordic `v2.42` image. See `rapoo-flasher/README.md`:
HIGH brick risk, do not flash yet. The TUI enforces `0-5` + VV table.

Live baseline 2026-10-14 (VT0 Air MAX, dongle `24ae:14a1`, `sensorScanRateLabel` 13K):
`competitive [0,1,1,4,4,4,4] @1000Hz, key-scan 1000Hz, LOD 1.0mm,
linear/ripple on, debounce 0/0, motion/glass off, Maximum+initial,
100% battery, rf rssi 54` — matches `rapoo get/status`.
