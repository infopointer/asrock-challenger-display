#!/bin/sh
# Simulate unplugging the display for 3 s (USB de-authorize), then show the daemon log. Run with sudo.
set -eu
dev=
for d in /sys/bus/usb/devices/*; do
    [ -f "$d/idVendor" ] || continue
    if [ "$(cat "$d/idVendor"):$(cat "$d/idProduct")" = "26ce:0a13" ]; then dev=$d; fi
done
[ -n "$dev" ] || { echo "display not found"; exit 1; }
echo "de-authorizing $dev"
echo 0 > "$dev/authorized"
sleep 3
echo 1 > "$dev/authorized"
echo "re-authorized, waiting 8 s"
sleep 8
journalctl -u asrock-challenger-display --no-pager -o cat --since "-20s"
systemctl show asrock-challenger-display -p ActiveState -p NRestarts
