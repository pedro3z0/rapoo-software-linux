# -*- coding: utf-8 -*-
"""Command-Line Interface for Rapoo Gaming Mouse Control."""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from pathlib import Path

from .transport import enumerate_rapoo_endpoints
from .device import RapooMouse
from .device_registry import registry
from .protocol import POLLING_RATE_LABELS, LABEL_TO_POLLING_RATE, CONN_WIRED


def cmd_list(args):
    endpoints = enumerate_rapoo_endpoints()
    if not endpoints:
        print("No Rapoo HID devices found on this system.")
        return 1

    print(f"Found {len(endpoints)} Rapoo HID endpoint(s):")
    for ep in endpoints:
        model = registry.find_by_pid(ep.product_id)
        model_name = model.model if model else "Unknown Rapoo Model"
        is_cfg = " [CONFIG INTERFACE]" if ep.interface_num == 1 else ""
        print(f"  - Node: {ep.path:<16} Interface: {ep.interface_num} (VID: 0x{ep.vendor_id:04x}, PID: 0x{ep.product_id:04x}) -> {model_name}{is_cfg}")
    return 0


def cmd_raw(args):
    """Diagnostic raw read: dump the response + all payload-offset candidates."""
    try:
        mouse = RapooMouse()
        with mouse:
            profile = args.profile if args.profile >= 0 else None
            result = mouse.raw_read(args.offset, args.length, profile)
        if args.json:
            print(json.dumps(result, indent=2))
        else:
            for k, v in result.items():
                print(f"  {k:16s} {v}")
        return 0
    except PermissionError:
        print("Permission denied opening hidraw device. Install the udev rule first:", file=sys.stderr)
        print("  ./install.sh", file=sys.stderr)
        return 2
    except Exception as e:
        print(f"Raw read failed: {e}", file=sys.stderr)
        return 1


def cmd_status(args):
    """Live status input report (report ID 7).

    Works on both links: the mouse pushes the report roughly every ~3s
    (measured on the cable too). The driver waits passively first and
    only sends a harmless 1-byte read as a fallback poke.
    """
    try:
        mouse = RapooMouse()
        with mouse:
            status = mouse.read_status(timeout_s=args.timeout)
        if status is None:
            print(
                "No status report received within "
                f"{args.timeout}s. The mouse may be asleep - move it first.",
                file=sys.stderr,
            )
            return 1
        if args.json:
            print(json.dumps(status, indent=2))
        else:
            print("=== Live Status (report 7, experimental) ===")
            for key, value in status.items():
                print(f"  {key:20s} {value}")
        return 0
    except PermissionError:
        print("Permission denied opening hidraw device. Install the udev rule first:", file=sys.stderr)
        print("  ./install.sh", file=sys.stderr)
        return 2
    except Exception as e:
        print(f"Error reading status: {e}", file=sys.stderr)
        return 1


def cmd_pair(args):
    """Dongle pairing: read-only state query, or live re-pair with --confirm."""
    try:
        mouse = RapooMouse()
        with mouse:
            if args.confirm:
                result = mouse.pair_receiver(timeout_s=args.timeout, dry_run=False)
            elif args.dry_run or not args.query:
                result = mouse.pair_receiver(dry_run=True)
            else:
                result = {"pre_state": mouse.pair_query_status(),
                          "wired": mouse.connection_type == CONN_WIRED,
                          "connection_type": mouse.connection_type}
        if args.json:
            print(json.dumps(result, indent=2))
        else:
            if "steps" in result:
                mode = "DRY RUN - no frames sent" if result.get("dry_run") else "LIVE"
                print(f"=== Dongle Pairing ({mode}) ===")
                link = "usb wired" if result.get("wired") else "NOT WIRED (pairing needs USB cable)"
                print(f"  Link: {link}")
                if "pre_state" in result:
                    print(f"  Pre-state: {result['pre_state']}")
                print("  Frame sequence:")
                for s in result["steps"]:
                    print(f"    {s['cmd']}  {s['desc']}")
            else:
                print(f"  Pairing state: {result['pre_state']}")
            for k in ("ok", "note", "error", "attempts", "via",
                        "rf_address_offer", "post_state"):
                if k in result:
                    print(f"  {k}: {result[k]}")
            if result.get("dry_run"):
                print("")
                print("  Live pairing is disabled (wired fw NAKs switch_work_mode);")
                print("  re-pair via hub.rapoo.cn with dongle + mouse connected.")
        return 0 if result.get("ok", True) else 1
    except PermissionError:
        print("Permission denied opening hidraw device. Install the udev rule first:", file=sys.stderr)
        print("  ./install.sh", file=sys.stderr)
        return 2
    except Exception as e:
        print(f"Pairing failed: {e}", file=sys.stderr)
        return 1


def cmd_get(args):
    try:
        mouse = RapooMouse()
        with mouse:
            settings = mouse.get_settings(profile=args.profile)
            if args.json:
                print(json.dumps(asdict(settings), indent=2))
            else:
                print(f"=== Rapoo Mouse Status ({mouse.model.model if mouse.model else 'Unknown'}) ===")
                print(f"  Current Active DPI Stage: {settings.current_dpi_stage + 1} (Stage index: {settings.current_dpi_stage})")
                print("  DPI Stages:")
                for i, (x, y) in enumerate(zip(settings.dpi_stages_x, settings.dpi_stages_y)):
                    marker = " [*]" if i == settings.current_dpi_stage else "    "
                    print(f"   {marker} Stage {i+1}: {x} DPI" + (f" (X: {x}, Y: {y})" if x != y else ""))
                print(f"  Polling Rate:       {settings.polling_rate_label} (raw: {settings.polling_rate_raw})")
                print(f"  Performance Mode:   {settings.sensor_mode_preset} (slots: {settings.sensor_mode_slots})")
                print(f"  Key Scan Rate:      {settings.key_scan_rate_label} (index: {settings.key_scan_rate_index})")
                print(f"  RF Strategy:        {'Maximum RF' if settings.rf_boost_enabled else 'Adaptive'}")
                print(f"  Comm Protocol:      {settings.rf_protocol_label}")
                print(f"  Lift-Off Distance:  {settings.liftoff_label} (index: {settings.liftoff_index})")
                print(f"  Sleep Time:         {settings.sleep_time_minutes} minutes")
                print(f"  Sensor Angle:       {settings.sensor_angle}°")
                print(f"  Glass Tracking:     {'Enabled' if settings.glass_tracking else 'Disabled'}")
                print(f"  Motion Sync:        {'Enabled' if settings.motion_sync else 'Disabled'}")
                print(f"  Linear Correction:  {'Enabled' if settings.linear_correction else 'Disabled'}")
                print(f"  Ripple Correction:  {'Enabled' if settings.ripple_correction else 'Disabled'}")
                print(f"  Debounce Delay:     {settings.debounce_press_ms}ms press, {settings.debounce_release_ms}ms release")
                print("")
                print("  Battery & connection type are live values - run:")
                print("    python -m backend.rapoo.cli status")
        return 0
    except PermissionError:
        print("Permission denied opening hidraw device. Please install udev rule:", file=sys.stderr)
        print("  sudo cp packaging/udev/99-rapoo.rules /etc/udev/rules.d/", file=sys.stderr)
        print("  sudo udevadm control --reload-rules && sudo udevadm trigger", file=sys.stderr)
        return 2
    except Exception as e:
        print(f"Error reading mouse settings: {e}", file=sys.stderr)
        return 1


def cmd_set(args):
    try:
        mouse = RapooMouse()
        with mouse:
            # Auto backup first
            backup_path = Path("analysis/backups/auto_backup_latest.json")
            mouse.backup_to_file(backup_path)

            if args.stage is not None:
                stage_idx = args.stage - 1
                mouse.set_dpi_stage(stage_idx, args.profile)
                print(f"Switched to DPI stage {args.stage}")

            if args.dpi is not None:
                if args.stage is None:
                    # set current active stage
                    cur = mouse.get_settings(args.profile).current_dpi_stage
                    mouse.set_stage_dpi(cur, args.dpi, args.profile)
                    print(f"Set current active DPI stage ({cur+1}) to {args.dpi} DPI")
                else:
                    mouse.set_stage_dpi(args.stage - 1, args.dpi, args.profile)
                    print(f"Set stage {args.stage} to {args.dpi} DPI")

            if args.polling is not None:
                mouse.set_polling_rate(args.polling, args.profile)
                print(f"Set polling rate to {args.polling}")

            if args.sleep is not None:
                mouse.set_sleep_time(args.sleep, args.profile)
                print(f"Set sleep time to {args.sleep} minutes")

            if args.motion_sync is not None:
                enable = args.motion_sync.lower() in ("true", "1", "yes", "on")
                mouse.set_motion_sync(enable, args.profile)
                print(f"Set motion sync to {enable}")

            if args.glass is not None:
                enable = args.glass.lower() in ("true", "1", "yes", "on")
                mouse.set_glass_tracking(enable, args.profile)
                print(f"Set glass tracking to {enable}")

            if args.angle is not None:
                mouse.set_angle(args.angle, args.profile)
                print(f"Set sensor angle to {args.angle}°")

            if args.key_scan is not None:
                raw = args.key_scan
                parsed = int(raw) if str(raw).isdigit() else raw
                mouse.set_key_scan_rate(parsed, args.profile)
                print(f"Set key scan rate to {args.key_scan}")

            if args.sensor_mode is not None:
                at = args.sensor_mode_at
                parsed_at = int(at) if at and at.isdigit() else at
                mouse.set_sensor_mode(args.sensor_mode, parsed_at, args.profile)
                print(
                    f"Set performance mode '{args.sensor_mode}' for "
                    f"{at or 'current polling rate'}"
                )

            if args.rf_protocol is not None:
                mouse.set_rf_protocol(args.rf_protocol)
                print(f"Set communication protocol to {args.rf_protocol}")

            if args.rf_boost is not None:
                mouse.set_rf_boost(args.rf_boost, args.profile)
                print(f"Set RF strategy to {args.rf_boost}")

            if args.lod is not None:
                lod_val: float | int
                if "." in args.lod:
                    lod_val = float(args.lod)
                else:
                    lod_val = int(args.lod)
                mouse.set_liftoff(lod_val, args.profile)
                print(f"Set lift-off distance to {lod_val}")

            if args.low_battery_light is not None:
                enable = args.low_battery_light.lower() in ("true", "1", "yes", "on")
                mouse.set_low_battery_light(enable, args.profile)
                print(f"Set low-battery light alert to {enable}")

            if args.dc_switch is not None:
                enable = args.dc_switch.lower() in ("true", "1", "yes", "on")
                mouse.set_dc_switch(enable, args.profile)
                print(f"Set DC switch to {enable}")

        return 0
    except PermissionError:
        print("Permission denied opening hidraw device. Run with sudo or install udev rules.", file=sys.stderr)
        return 2
    except Exception as e:
        print(f"Error writing mouse settings: {e}", file=sys.stderr)
        return 1


def cmd_backup(args):
    try:
        mouse = RapooMouse()
        out = Path(args.file)
        with mouse:
            mouse.backup_to_file(out)
        print(f"Settings successfully backed up to {out}")
        return 0
    except Exception as e:
        print(f"Backup failed: {e}", file=sys.stderr)
        return 1


def cmd_restore(args):
    try:
        mouse = RapooMouse()
        src = Path(args.file)
        if not src.is_file():
            print(f"Backup file not found: {src}", file=sys.stderr)
            return 1
        with mouse:
            mouse.restore_from_file(src)
        print(f"Settings successfully restored from {src}")
        return 0
    except Exception as e:
        print(f"Restore failed: {e}", file=sys.stderr)
        return 1


def main():
    parser = argparse.ArgumentParser(description="Rapoo Gaming Mouse Configuration Tool (Linux)")
    sub = parser.add_subparsers(dest="command", required=True)

    # list
    sub.add_parser("list", help="List detected Rapoo HID devices")

    # status: live input report (battery, DPI, polling, connection)
    p_status = sub.add_parser("status", help="Live status report: battery, DPI, polling, connection")
    p_status.add_argument("--json", action="store_true", help="Output as JSON")
    p_status.add_argument("--timeout", type=float, default=10.0, help="Seconds to wait for a report")

    # raw: diagnostic
    p_raw = sub.add_parser("raw", help="Diagnostic: raw memory read + payload-offset candidates")
    p_raw.add_argument("--offset", type=lambda s: int(s, 0), required=True, help="Register offset (dec or 0x..)")
    p_raw.add_argument("--length", type=int, default=8, help="Bytes to read")
    p_raw.add_argument(
        "--profile",
        type=int,
        default=-1,
        help="Profile base index; -1 (default) = auto (absolute for offsets < 1024)",
    )
    p_raw.add_argument("--json", action="store_true", help="Output as JSON")

    # get
    p_get = sub.add_parser("get", help="Get current mouse settings")
    p_get.add_argument("--json", action="store_true", help="Output as JSON")
    p_get.add_argument("--profile", type=int, default=0, help="Profile index (0-7, default 0)")

    # set
    p_set = sub.add_parser("set", help="Change mouse settings")
    p_set.add_argument("--profile", type=int, default=0, help="Profile index (0-7, default 0)")
    p_set.add_argument("--stage", type=int, help="Active DPI stage (1-7)")
    p_set.add_argument("--dpi", type=int, help="DPI value (50-30000)")
    p_set.add_argument("--polling", choices=list(LABEL_TO_POLLING_RATE.keys()), help="Polling rate (e.g. 1000Hz, 4000Hz, 8000Hz)")
    p_set.add_argument("--sleep", type=int, help="Sleep time in minutes (1-60)")
    p_set.add_argument("--motion-sync", choices=["on", "off", "true", "false"], help="Toggle motion sync")
    p_set.add_argument("--glass", choices=["on", "off", "true", "false"], help="Toggle glass tracking")
    p_set.add_argument("--angle", type=int, help="Sensor angle (-30 to +30 degrees)")
    p_set.add_argument("--key-scan", help="Key scan rate (1000Hz, 2000Hz, 4000Hz, 8000Hz)")
    p_set.add_argument(
        "--sensor-mode",
        help="Performance mode preset (office, balanced, firepower, hyperCore, competitive, frenzy)",
    )
    p_set.add_argument(
        "--sensor-mode-at",
        help="Optional polling rate the preset applies to (e.g. 8000Hz); default: current rate",
    )
    p_set.add_argument("--rf-protocol", choices=["turbo", "initial"], help="Communication protocol")
    p_set.add_argument("--rf-boost", choices=["adaptive", "maximum"], help="Wireless RF strategy")
    p_set.add_argument(
        "--lod",
        help="Lift-off distance: mm value from the model scale (e.g. 1.1) or raw 1-based index",
    )
    p_set.add_argument(
        "--low-battery-light", choices=["on", "off", "true", "false"], help="Low-battery LED flash alert"
    )
    p_set.add_argument("--dc-switch", choices=["on", "off", "true", "false"], help="DC switch (undocumented)")

    # backup & restore
    p_bak = sub.add_parser("backup", help="Save current settings to a JSON file")
    p_bak.add_argument("file", help="Destination JSON path")

    p_res = sub.add_parser("restore", help="Restore settings from a JSON file")
    p_res.add_argument("file", help="Source JSON path")

    # pair: dongle pairing (read-only query by default)
    p_pair = sub.add_parser("pair", help="Dongle pairing: query link state / re-pair receiver")
    p_pair.add_argument("--json", action="store_true", help="Output as JSON")
    p_pair.add_argument("--timeout", type=float, default=40.0, help="Live-pairing wait in seconds")
    p_pair.add_argument("--query", action="store_true", help="Read-only pairing/link state query")
    p_pair.add_argument("--dry-run", action="store_true", help="Show frame sequence without sending (default)")
    p_pair.add_argument("--confirm", action="store_true", help="Attempt live pairing (currently refused: wired fw NAKs it; use hub.rapoo.cn)")

    args = parser.parse_args()

    handlers = {
        "list": cmd_list,
        "raw": cmd_raw,
        "status": cmd_status,
        "get": cmd_get,
        "set": cmd_set,
        "backup": cmd_backup,
        "restore": cmd_restore,
        "pair": cmd_pair
    }
    sys.exit(handlers[args.command](args))


if __name__ == "__main__":
    main()
