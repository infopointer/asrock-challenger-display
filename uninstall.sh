#!/bin/sh
# Remove the ASRock Challenger display service, its files and the udev rule. Run as root.
set -eu
[ "$(id -u)" -eq 0 ] || { echo "run as root: sudo $0" >&2; exit 1; }

PREFIX=/opt/asrock-challenger
UNIT=asrock-challenger-display.service

systemctl disable --now "$UNIT" 2>/dev/null || true
rm -f "/etc/systemd/system/$UNIT"
systemctl daemon-reload
rm -f "$PREFIX/challenger_send.py" "$PREFIX/challenger_display.py" "$PREFIX/protocol.md"
rmdir "$PREFIX" 2>/dev/null || true
rm -f /etc/udev/rules.d/99-asrock-challenger-aio.rules
udevadm control --reload
echo "removed; the display goes dark until something else drives it"
