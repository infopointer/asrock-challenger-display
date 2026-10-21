#!/bin/sh
# Install or update the ASRock Challenger display service. Run as root: sudo ./install.sh
set -eu
[ "$(id -u)" -eq 0 ] || { echo "run as root: sudo $0" >&2; exit 1; }
command -v python3 >/dev/null || { echo "python3 not found" >&2; exit 1; }

REPO=$(dirname "$(readlink -f "$0")")
PREFIX=/opt/asrock-challenger
UNIT=asrock-challenger-display.service
RULE=99-asrock-challenger-aio.rules

# udev rule: make the display's hidraw node accessible, then apply it to the plugged-in device.
install -m 0644 "$REPO/udev/$RULE" /etc/udev/rules.d/
udevadm control --reload
udevadm trigger --action=change --attr-match=idVendor=26ce --attr-match=idProduct=0a13
udevadm trigger --action=change --subsystem-match=hidraw
udevadm settle

install -d -m 0755 "$PREFIX"
install -m 0644 "$REPO/tools/challenger_send.py" "$REPO/tools/challenger_display.py" \
    "$REPO/protocol.md" "$PREFIX/"
install -m 0644 "$REPO/systemd/$UNIT" /etc/systemd/system/
systemctl daemon-reload
systemctl enable "$UNIT"
systemctl restart "$UNIT"  # restart, not just start, so re-running picks up new code
sleep 3
systemctl --no-pager status "$UNIT" || true
