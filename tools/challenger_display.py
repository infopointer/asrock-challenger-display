#!/usr/bin/env python3
"""Feed live CPU temp / clock / load to the ASRock Challenger 360 Digital display.

Linux replacement for ASRock's Windows "Challenger Driver": every second it
sends the same five feature reports the vendor app sends (see protocol.md).
The display goes dark a few seconds after updates stop, so this runs forever.
"""
import argparse
import collections
import glob
import os
import signal
import sys
import time

from challenger_send import PAGES, Display, build_frame, find_device


def log(msg):
    print(msg, flush=True)


def _read(path):
    with open(path) as f:
        return f.read().strip()


# hwmon driver -> label of the CPU temperature to show.
CPU_TEMP_SENSORS = {"k10temp": "Tctl", "coretemp": "Package id 0"}  # AMD, Intel


def find_cpu_temp():
    """CPU temperature input (millidegrees C), or None."""
    for hw in sorted(glob.glob("/sys/class/hwmon/hwmon*")):
        try:
            name = _read(os.path.join(hw, "name"))
        except OSError:
            continue
        if name not in CPU_TEMP_SENSORS:
            continue
        for label in sorted(glob.glob(os.path.join(hw, "temp*_label"))):
            try:
                if _read(label) == CPU_TEMP_SENSORS[name]:
                    return label[:-len("_label")] + "_input"
            except OSError:
                pass
        if os.path.exists(os.path.join(hw, "temp1_input")):
            return os.path.join(hw, "temp1_input")
    return None


class CpuLoad:
    """Busy % across all CPUs since the previous call, from /proc/stat."""

    def __init__(self):
        self.prev = self._sample()

    @staticmethod
    def _sample():
        with open("/proc/stat") as f:
            v = [int(x) for x in f.readline().split()[1:]]
        idle = v[3] + (v[4] if len(v) > 4 else 0)  # idle + iowait
        return idle, sum(v[:8])  # exclude guest columns (already in user)

    def read(self):
        idle, total = self._sample()
        d_idle, d_total = idle - self.prev[0], total - self.prev[1]
        self.prev = (idle, total)
        return 0 if d_total <= 0 else round(100 * (d_total - d_idle) / d_total)


def cpu_mhz():
    best = 0
    for p in glob.glob("/sys/devices/system/cpu/cpu[0-9]*/cpufreq/scaling_cur_freq"):
        try:
            best = max(best, int(_read(p)))
        except (OSError, ValueError):
            pass
    return best // 1000


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--pages", default=None,
                    help="comma list from %s, in display order "
                         "(default: temp,mhz; plus rpm when --rpm-hwmon is set)"
                         % ",".join(sorted(PAGES)))
    ap.add_argument("--switch-seconds", type=int, default=8,
                    help="seconds per page (vendor default 8)")
    ap.add_argument("--rpm-hwmon", help="fanN_input file to show as RPM (default: send 0)")
    ap.add_argument("--mhz-window", type=int, default=5,
                    help="average the max core clock over N seconds (1 = raw)")
    ap.add_argument("--fahrenheit", action="store_true")
    ap.add_argument("--device", help="hidraw node (default: auto-detect)")
    ap.add_argument("--log-every", type=int, default=60,
                    help="log the values sent every N seconds (0 = never)")
    a = ap.parse_args()

    pages = (a.pages or ("temp,mhz,rpm" if a.rpm_hwmon else "temp,mhz")).split(",")
    bad = [p for p in pages if p not in PAGES]
    if bad:
        ap.error("unknown page(s): %s" % ",".join(bad))
    switch = max(1, a.switch_seconds)

    temp_path = find_cpu_temp()
    if not temp_path:
        log("warning: no k10temp/coretemp sensor found, temperature will read 0")
    log("pages=%s switch=%ss temp=%s rpm=%s" % (",".join(pages), switch, temp_path, a.rpm_hwmon or "0"))

    running = True

    def stop(signum, _frame):
        nonlocal running
        running = False

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)

    load = CpuLoad()
    # Idle cores make the per-second max clock jump (e.g. 605 <-> 4266 MHz);
    # average the last few samples so the display doesn't flicker.
    mhz_hist = collections.deque(maxlen=max(1, a.mhz_window))
    disp = None
    waiting_logged = False
    start = time.monotonic()
    tick = 0
    next_t = start

    while running:
        next_t += 1.0
        if disp is None:
            path = a.device or find_device()
            if path:
                try:
                    disp = Display(path)
                    log("display opened: %s" % path)
                    waiting_logged = False
                except OSError as e:
                    if not waiting_logged:
                        log("cannot open %s: %s (retrying)" % (path, e))
                        waiting_logged = True
            elif not waiting_logged:
                log("display not found (retrying)")
                waiting_logged = True

        try:
            temp = int(_read(temp_path)) / 1000 if temp_path else 0.0
        except (OSError, ValueError):
            temp = 0.0
        rpm = 0
        if a.rpm_hwmon:
            try:
                rpm = int(_read(a.rpm_hwmon))
            except (OSError, ValueError):
                pass
        mhz_hist.append(cpu_mhz())
        mhz, usage = round(sum(mhz_hist) / len(mhz_hist)), load.read()
        page = pages[(int(time.monotonic() - start) // switch) % len(pages)]

        if disp is not None:
            try:
                disp.send(build_frame(cpu_temp=temp, cpu_mhz=mhz, cpu_usage=usage,
                                      rpm=rpm, page=page, fahrenheit=a.fahrenheit))
            except OSError as e:
                log("display write failed: %s (reconnecting)" % e)
                try:
                    disp.close()
                except OSError:
                    pass
                disp = None

        if a.log_every and tick % a.log_every == 0:
            log("temp=%.1fC mhz=%d load=%d%% rpm=%d page=%s%s"
                % (temp, mhz, usage, rpm, page, "" if disp else " (no display)"))
        tick += 1

        delay = next_t - time.monotonic()
        if delay > 0:
            time.sleep(delay)
        else:
            next_t = time.monotonic()

    if disp is not None:
        disp.close()
    log("stopped")
    return 0


if __name__ == "__main__":
    sys.exit(main())
