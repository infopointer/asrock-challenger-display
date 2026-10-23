#!/bin/sh
# Remove the ASRock Challenger display service, its files, the udev rule and the group. Run as root.
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
# Put the plugged-in display back to the defaults. Replaying "add" re-runs udev's default rules
# for the raw USB node, but no rule resets hidraw nodes, so set the kernel default by hand.
for d in /sys/bus/usb/devices/*; do
    [ -f "$d/idVendor" ] || continue
    if [ "$(cat "$d/idVendor"):$(cat "$d/idProduct")" = "26ce:0a13" ]; then
        udevadm trigger --action=add --parent-match="$d"
    fi
done
udevadm settle
for h in /sys/class/hidraw/hidraw*; do
    if grep -q "HID_ID=0003:000026CE:00000A13" "$h/device/uevent" 2>/dev/null; then
        chown root:root "/dev/${h##*/}"
        chmod 0600 "/dev/${h##*/}"
    fi
done
rm -f /etc/sysusers.d/asrock-challenger.conf
groupdel asrock-challenger 2>/dev/null || true
echo "removed; the display goes dark until something else drives it"
