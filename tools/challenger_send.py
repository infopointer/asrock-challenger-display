#!/usr/bin/env python3
"""ASRock Challenger 360 Digital pump display: packet encoder + one-shot sender.

Implements exactly the five feature reports ASRock's Windows "Challenger Driver"
sends each second (see protocol.md). Standard library only.

One-shot test:  python3 challenger_send.py --cpu-temp 42 --mhz 4500 --page temp
"""
import argparse
import fcntl
import glob
import os
import time

VID, PID = 0x26CE, 0x0A13
REPORT_ID = 0x07
REPORT_LEN = 64  # report ID + 63 data bytes

# Page selector in packet 04, byte 6 (app's device_type 0/1/2 -> 1/4/2).
PAGES = {"mhz": 1, "rpm": 2, "temp": 4}

CPU_TEMP_STEPS = (50, 100, 150, 200, 250, 300, 350, 400, 450, 500,
                  550, 600, 650, 700, 750, 800, 850, 900, 1000)
MHZ_STEPS = (500, 1000, 1200, 1400, 1600, 1800, 2000, 2100, 2300, 2500,
             3000, 3500, 4000, 4500, 5000, 5500, 6000, 6500, 7000)
RPM_STEPS = (50, 100, 150, 200, 300, 450, 600, 800, 1000, 1200,
             1400, 1600, 1800, 2000, 2200, 2400, 2600, 2800, 3000)


def _hidioc(nr, size):
    # _IOC(_IOC_READ | _IOC_WRITE, 'H', nr, size)
    return (3 << 30) | (size << 16) | (ord("H") << 8) | nr


HIDIOCSFEATURE = _hidioc(0x06, REPORT_LEN)


def _step_level(v, steps, zero=0):
    return zero if v <= 0 else 1 + sum(v > t for t in steps)


def _ten_level(v, div):
    return 0 if v <= 0 else min(v // div + 1, 10)


def _digits(v, n):
    v = max(0, int(v))
    return [(v // 10 ** i) % 10 for i in range(n - 1, -1, -1)]


def _packed(gpu, cpu, n):
    return [(g << 4) | c for g, c in zip(_digits(gpu, n), _digits(cpu, n))]


def _packet(index, body):
    buf = bytearray(REPORT_LEN)
    buf[0], buf[1] = REPORT_ID, index
    buf[2:2 + len(body)] = bytes(body)
    return buf


def build_frame(cpu_temp=0.0, cpu_mhz=0, cpu_usage=0, cpu_power=0,
                gpu_temp=0.0, gpu_mhz=0, gpu_usage=0, gpu_power=0,
                rpm=0, page="temp", fahrenheit=False):
    """Return the five 64-byte packets for one tick. Temps in °C."""
    # Bars use °C x10; the digits are converted to °F afterwards (0 stays 0).
    ct, gt = int(round(cpu_temp * 10)), int(round(gpu_temp * 10))

    def shown(v):
        return min(int(v * 1.8 + 320) if fahrenheit and v else v, 9999)

    cu = min(int(cpu_usage), 100)
    if ct > 0:
        cu = max(cu, 1)
    gu = min(int(gpu_usage), 100)
    cp, gp = min(int(cpu_power), 998), int(gpu_power)
    cm, gm = min(int(cpu_mhz), 9999), int(gpu_mhz)
    rpm = int(rpm)

    ct_bar = _step_level(ct, CPU_TEMP_STEPS, zero=1)
    gt_bar = _ten_level(gt, 100)
    page_bar = {"mhz": _step_level(cm, MHZ_STEPS),
                "temp": ct_bar,
                "rpm": _step_level(rpm, RPM_STEPS)}[page]

    return [
        _packet(0, _packed(shown(gt), shown(ct), 4) +[int(fahrenheit), (gt_bar << 4) | (ct_bar & 0x0F)]),
        _packet(1, _packed(gu, cu, 3) + [0, (_ten_level(gu, 10) << 4) | _ten_level(cu, 10), 1]),
        _packet(2, _packed(gp, cp, 3) + [0, 0, 0]),
        _packet(3, _packed(gm, cm, 4) + [0, 0]),
        _packet(4, _digits(rpm, 4) + [PAGES[page], page_bar]),
    ]


def find_device():
    """Return /dev/hidrawN for the display's vendor (0xFF01) interface, or None."""
    want = "HID_ID=0003:%08X:%08X" % (VID, PID)
    for node in sorted(glob.glob("/sys/class/hidraw/hidraw*")):
        try:
            with open(os.path.join(node, "device/uevent")) as f:
                if want not in f.read().upper():
                    continue
            with open(os.path.join(node, "device/report_descriptor"), "rb") as f:
                if b"\x06\x01\xff" in f.read():
                    return "/dev/" + os.path.basename(node)
        except OSError:
            continue
    return None


class Display:
    def __init__(self, path):
        self.path = path
        self.fd = os.open(path, os.O_RDWR)

    def send(self, packets, gap=0.010):
        for p in packets:
            fcntl.ioctl(self.fd, HIDIOCSFEATURE, bytearray(p), True)
            time.sleep(gap)

    def close(self):
        os.close(self.fd)


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--device", help="hidraw node (default: auto-detect)")
    ap.add_argument("--cpu-temp", type=float, default=42.0)
    ap.add_argument("--mhz", type=int, default=4500)
    ap.add_argument("--usage", type=int, default=10)
    ap.add_argument("--rpm", type=int, default=0)
    ap.add_argument("--page", choices=sorted(PAGES), default="temp")
    ap.add_argument("--fahrenheit", action="store_true")
    ap.add_argument("--dry-run", action="store_true", help="print packets, send nothing")
    a = ap.parse_args()

    frame = build_frame(cpu_temp=a.cpu_temp, cpu_mhz=a.mhz, cpu_usage=a.usage,
                        rpm=a.rpm, page=a.page, fahrenheit=a.fahrenheit)
    for p in frame:
        print(p[:8].hex(" "))
    if a.dry_run:
        return
    path = a.device or find_device()
    if not path:
        raise SystemExit("display not found (no hidraw with %04x:%04x + vendor page FF01)" % (VID, PID))
    d = Display(path)
    try:
        d.send(frame)
    finally:
        d.close()
    print("sent to", path)


if __name__ == "__main__":
    main()
