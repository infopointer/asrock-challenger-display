# asrock-challenger-display

Linux driver for the pump-head display on the **ASRock Challenger Digital** AIO liquid cooler.

On Windows, ASRock's "Challenger Driver" app pushes CPU readings to the display over USB. The display has no readings of its own, so on Linux it stays dark. This project replaces that app with a small Python daemon run as a systemd service. It sends the same USB messages, reverse-engineered from ASRock's driver (see [protocol.md](protocol.md)).

What the display shows, switching every 8 s:
- **CPU temperature**, with one decimal and a bar.
- **CPU clock (MHz)**: the fastest core, averaged over 5 s.

CPU load is also sent every second.

## Hardware

| | |
|---|---|
| Cooler | ASRock Challenger 360 Digital (tested). Other Challenger Digital models probably work, untested |
| USB ID | `26ce:0a13` "SEMICO Challenger Driver" (`lsusb \| grep 26ce`) |
| Tested on | Ubuntu 24.04.5, kernel 7.0, Ryzen 7 9700X, Gigabyte B850 AI TOP |

ASRock's app also accepts USB ID `1a2c:4c86`. This project doesn't support that ID yet.

## Requirements

- Linux with systemd and `python3`. Only the standard library is used; no pip packages.
- CPU temperature from the `k10temp` (AMD) or `coretemp` (Intel) hwmon driver. The Intel path is untested.

## Install

Ubuntu Desktop doesn't include git, so install it first; Server already has it. Without git, use **Code → Download ZIP** on GitHub, unzip it, and run `sudo ./install.sh` in that folder.

```bash
sudo apt install git
git clone https://github.com/infopointer/asrock-challenger-display.git && cd asrock-challenger-display
sudo ./install.sh
```

The installer puts files in four places:
- The udev rule in `/etc/udev/rules.d/`, applied to the plugged-in device straight away.
- The scripts in `/opt/asrock-challenger/`.
- The unit in `/etc/systemd/system/`.
- The service itself, enabled and started.

To update after a `git pull`, run `sudo ./install.sh` again.

Check it:

```bash
systemctl status asrock-challenger-display
journalctl -u asrock-challenger-display -f   # logs the values sent once a minute
```

The service runs as an unprivileged dynamic user with no network access. It finds the display by USB ID and HID descriptor, so the `hidrawN` number doesn't matter. It also reconnects by itself after an unplug, USB reset or suspend.

## Options

| option | default | |
|---|---|---|
| `--pages` | `temp,mhz` | pages to cycle through, in order: `temp`, `mhz`, `rpm` |
| `--switch-seconds` | `8` | seconds per page (ASRock's default) |
| `--mhz-window` | `5` | average the clock over N seconds (`1` = raw, flickers at idle) |
| `--rpm-hwmon` | – | a `fanN_input` file to show as RPM; also adds the `rpm` page |
| `--fahrenheit` | off | show °F |
| `--device` | auto | force a `/dev/hidrawN` |
| `--log-every` | `60` | log the values sent every N seconds (`0` = never) |

To change them, add a drop-in with `sudo systemctl edit asrock-challenger-display`:

```ini
[Service]
ExecStart=
ExecStart=/usr/bin/python3 -u /opt/asrock-challenger/challenger_display.py --fahrenheit --switch-seconds 5
```

## Testing without the service

`tools/challenger_send.py` sends a single frame of fixed values. Stop the service first so the two don't fight over the display:

```bash
sudo systemctl stop asrock-challenger-display
python3 tools/challenger_send.py --cpu-temp 42 --mhz 4500 --page temp
python3 tools/challenger_send.py --dry-run --cpu-temp 71.5   # print the packets only
sudo systemctl start asrock-challenger-display
```

The display goes dark a few seconds after the last frame. That's normal, and the reason a daemon is needed.

`sudo tools/replug-test.sh` simulates unplugging the display for 3 s and shows that the service reconnects.

## Uninstall

```bash
sudo ./uninstall.sh
```

## Not supported yet

- **Pump/fan RPM**: the field is sent as 0. Many boards' fan chips (for example ITE IT8696E on Gigabyte B850) need the out-of-tree [frankcrawford/it87](https://github.com/frankcrawford/it87) driver. With Secure Boot on, that module also needs MOK signing. Once a `fanN_input` exists, pass it with `--rpm-hwmon`.
- **CPU power**: sent as 0. RAPL energy counters are root-only.
- **GPU values**: sent as 0. The protocol has GPU fields, but so far only the temp, clock and RPM pages have been seen on this display.

## Troubleshooting

| symptom | check |
|---|---|
| display dark, log says `display not found` | `lsusb \| grep 26ce`. Is the cooler's USB header connected? |
| `cannot open /dev/hidrawN: Permission denied` | `ls -l /dev/hidraw*`. The node should be `crw-rw-rw-`. Re-run `sudo ./install.sh` |
| temperature shows 0 | `sensors` / `ls /sys/class/hwmon/*/name`. Needs `k10temp` or `coretemp` |
| clock jumps around | raise `--mhz-window` |

## How it works / safety

See [protocol.md](protocol.md) for the full packet layout. In short: every second the service sends five 64-byte HID feature reports (report ID 7) to the display's vendor interface. They carry temperature, load, power, clock, and RPM plus the page to show.

The service sends **only** the packets ASRock's app sends during normal use. The display's controller also accepts firmware-update commands, and nothing here touches them.

The udev rule makes the display's device nodes readable and writable by every local user (`MODE="0666"`), so the service can run unprivileged.

## Disclaimer

Not affiliated with or endorsed by ASRock. I worked out the protocol by static analysis of ASRock's freely downloadable Windows driver, for interoperability. No ASRock code or files are included in this repository. Use at your own risk.

## License

Apache License 2.0, see [LICENSE](LICENSE).
