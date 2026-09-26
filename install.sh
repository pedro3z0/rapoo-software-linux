#!/usr/bin/env bash
# Rapoo Linux installer - two things, nothing else:
#
#   1. udev rule  -> grants unprivileged access to Rapoo /dev/hidraw* nodes.
#      This is what unlocks BOTH Rapoo's official web driver
#      (https://hub.rapoo.cn) and this repo's CLI.
#   2. `rapoo` command -> symlink into ~/.local/bin so the CLI works from
#      any directory. The CLI is pure-stdlib Python 3 (>= 3.9): no venv,
#      no pip, no uv, no packages.
#
# Optional: `./install.sh --dev` also creates .venv with pytest for running
# the test suite.
#
# Usage:
#   ./install.sh          # normal install (udev rule + rapoo command)
#   ./install.sh --dev    # + pytest dev environment
set -euo pipefail

HERE="$(cd "$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")" && pwd)"

echo "=== Installing Rapoo Linux Support ==="

# 1. udev rule (the only step needing root)
UDEV_DST="/etc/udev/rules.d/99-rapoo.rules"
if [[ -d "/etc/udev/rules.d" ]]; then
    if [[ -f "$UDEV_DST" ]] && cmp -s "$HERE/packaging/udev/99-rapoo.rules" "$UDEV_DST"; then
        echo "[1/2] udev rule already installed and up to date."
    else
        echo "[1/2] Installing udev rule for Rapoo devices (sudo)..."
        if sudo cp "$HERE/packaging/udev/99-rapoo.rules" "$UDEV_DST" \
            && sudo udevadm control --reload-rules \
            && sudo udevadm trigger; then
            echo "       done. Unplug and replug your dongle (or reboot) to apply."
        else
            echo "       could not install automatically. Run manually:" >&2
            echo "         sudo cp packaging/udev/99-rapoo.rules /etc/udev/rules.d/" >&2
            echo "         sudo udevadm control --reload-rules && sudo udevadm trigger" >&2
        fi
    fi
fi

# 2. `rapoo` command (no root needed)
echo "[2/2] Installing 'rapoo' command into ~/.local/bin ..."
mkdir -p "$HOME/.local/bin"
ln -sfn "$HERE/rapoo" "$HOME/.local/bin/rapoo"
case ":$PATH:" in
    *":$HOME/.local/bin:"*) ;;
    *) echo "       NOTE: add ~/.local/bin to PATH (e.g. in ~/.bashrc):" \
           "export PATH=\"\$HOME/.local/bin:\$PATH\"" ;;
esac

# Optional dev extras
if [[ "${1:-}" == "--dev" ]]; then
    echo "[dev] Setting up pytest environment..."
    if command -v uv >/dev/null 2>&1; then
        uv venv "$HERE/.venv" --quiet
        uv pip install --python "$HERE/.venv/bin/python" pytest --quiet
    else
        python3 -m venv "$HERE/.venv"
        "$HERE/.venv/bin/pip" install -q pytest
    fi
    echo "       run tests: .venv/bin/python -m pytest backend/tests/"
fi

echo ""
echo "=== Setup Complete! ==="
echo ""
echo "1) Recommended UI - Rapoo's official web driver:"
echo "     https://hub.rapoo.cn  (or https://hub.rapoo.com)"
echo "   Open it in Chrome/Edge/Chromium and click 'Connect Device'."
echo ""
echo "2) CLI (scripting / backups / diagnostics):"
echo "  rapoo list"
echo "  rapoo get"
echo "  rapoo set --polling 8000Hz --lod 1.1"
echo "  rapoo backup my-settings.json"
echo "  rapoo status          # battery, connection, live DPI/polling"
