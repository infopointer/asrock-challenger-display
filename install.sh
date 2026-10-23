#!/bin/sh
# Install or update the ASRock Challenger display service. Run as root: sudo ./install.sh
set -eu
[ "$(id -u)" -eq 0 ] || { echo "run as root: sudo $0" >&2; exit 1; }
command -v python3 >/dev/null || { echo "python3 not found" >&2; exit 1; }

REPO=$(dirname "$(readlink -f "$0")")
PREFIX=/opt/asrock-challenger
UNIT=asrock-challenger-display.service
RULE=99-asrock-challenger-aio.rules
SYSUSERS=asrock-challenger.conf

# Group first: udev ignores GROUP= for a group that doesn't exist yet.
install -D -m 0644 "$REPO/sysusers/$SYSUSERS" "/etc/sysusers.d/$SYSUSERS"
systemd-sysusers "/etc/sysusers.d/$SYSUSERS"

# udev rule: give that group the display's hidraw nodes, then apply it to the plugged-in display.
# Replay "add", not "change": udev's default permission rules only run on add, and they put the
# raw USB node back to 0664 where an older version of this rule had made it 0666.
install -m 0644 "$REPO/udev/$RULE" /etc/udev/rules.d/
udevadm control --reload
for d in /sys/bus/usb/devices/*; do
    [ -f "$d/idVendor" ] || continue
    if [ "$(cat "$d/idVendor"):$(cat "$d/idProduct")" = "26ce:0a13" ]; then
        udevadm trigger --action=add --parent-match="$d"
    fi
done
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
