#!/usr/bin/env bash
# Rapoo Linux support: udev rule + Python CLI setup
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "=== Installing Rapoo Linux Support ==="

# 1. Install udev rule (grants access to /dev/hidraw* for Rapoo devices)
#    This also enables Rapoo's official WebHID driver (https://hub.rapoo.cn)
#    and this project's CLI for unprivileged users.
UDEV_DST="/etc/udev/rules.d/99-rapoo.rules"
if [[ -d "/etc/udev/rules.d" ]]; then
    echo "Installing udev rule for Rapoo devices..."
    if sudo cp "$HERE/packaging/udev/99-rapoo.rules" "$UDEV_DST"; then
        sudo udevadm control --reload-rules && sudo udevadm trigger
        echo "udev rule installed and reloaded."
        echo "Unplug and replug your Rapoo dongle (or reboot) to apply permissions."
    else
        echo "Note: could not install udev rule automatically. Run manually:"
        echo "  sudo cp packaging/udev/99-rapoo.rules /etc/udev/rules.d/"
        echo "  sudo udevadm control --reload-rules && sudo udevadm trigger"
    fi
fi

# 2. Python environment (library + CLI + tests only; no web server needed:
#    the primary UI is Rapoo's official WebHID driver at https://hub.rapoo.cn)
echo "Setting up Python virtual environment..."
uv venv "$HERE/.venv" --quiet
uv pip install --python "$HERE/.venv/bin/python" pytest --quiet

echo ""
echo "=== Setup Complete! ==="
echo ""
echo "1) Recommended UI - Rapoo's official web driver:"
echo "     https://hub.rapoo.cn  (or https://hub.rapoo.com)"
echo "   Open it in Chrome/Edge/Chromium and click 'Connect Device'."
echo ""
echo "2) CLI (scripting / backups / diagnostics):"
echo "  .venv/bin/python -m backend.rapoo.cli list"
echo "  .venv/bin/python -m backend.rapoo.cli get"
echo "  .venv/bin/python -m backend.rapoo.cli set --polling 8000Hz --lod 1.1"
echo "  .venv/bin/python -m backend.rapoo.cli backup my-settings.json"
