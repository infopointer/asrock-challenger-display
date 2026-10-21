# ASRock Challenger 360 Digital: pump display protocol

Source: ASRock "Challenger Driver" v1.0.1.13, `DeviceDriver.exe` (native x86 MSVC, not .NET).
I reverse-engineered it statically with radare2/r2dec and never ran it. Addresses below refer to that binary.

## Device

| | |
|---|---|
| USB ID | `26ce:0a13` "SEMICO Challenger Driver" (the app also accepts `1a2c:4c86`) |
| Interface | 1. The app picks the HID collection with UsagePage `0xFF01`, Usage `1` (`fcn.004062a0`) |
| Linux node | `/dev/hidrawN` whose `report_descriptor` contains `06 01 FF`. Interface 0 is a plain boot keyboard; leave it alone |
| Transport | **Feature report**, report ID `0x07`, 63 data bytes, so 64 bytes with the ID (`HidD_SetFeature`, `fcn.0040eec0`). On Linux use `ioctl(HIDIOCSFEATURE(64))` |

There is no init or handshake packet. The app opens the device and starts streaming.

## Per-tick stream (`fcn.0040a840`, once per second)

Each packet is 64 bytes, zero-filled. `b0 = 0x07` (report ID) and `b1` = packet index.
The app sleeps 10 ms after each packet and `Sleep(1000)` at the end of the tick.
If every input is zero (temps, usage, MHz, power, RPM) the whole tick is skipped.

"Packed" bytes hold two decimal digits: the GPU digit in the high nibble and the CPU digit in the low nibble (`(gpu_digit << 4) | cpu_digit`).

| idx | value | b2 | b3 | b4 | b5 | b6 | b7 |
|---|---|---|---|---|---|---|---|
| `00` | temperature x10 | packed thousands | packed hundreds | packed tens | packed ones | unit: 0 = °C, 1 = °F | `(gpu_temp_bar << 4) \| (cpu_temp_bar & 0x0F)` |
| `01` | usage % | packed hundreds | packed tens | packed ones | 0 | `(gpu_usage_bar << 4) \| cpu_usage_bar` | 1 |
| `02` | power W | packed hundreds | packed tens | packed ones | 0 | 0 | 0 |
| `03` | clock MHz | packed thousands | packed hundreds | packed tens | packed ones | 0 | 0 |
| `04` | RPM + page | RPM thousands | RPM hundreds | RPM tens | RPM ones | page | page bar |

Notes on the table:
- In packet `04` the RPM digits are unpacked: one digit per byte.
- In packet `00`, °F is computed on the x10 value as `v * 1.8 + 320` (0 stays 0), then clamped to 9999. Bars always use the °C value.

### Page selector (packet `04`, b6/b7)
The app keeps `device_type` (0, 1, 2). A timer (id 400) advances it 0 → 1 → 2 → 0 every `switch_interval` seconds (config default **8**, clamped to 5–99). The display shows whichever page the host selects; the device itself does no cycling.

| device_type | b6 | page | b7 |
|---|---|---|---|
| 0 | `1` | CPU clock | MHz bar |
| 1 | `4` | CPU temp | CPU temp bar (unmasked, 1–20) |
| 2 | `2` | fan/pump RPM | RPM bar |

### Bar levels
For the threshold bars, the level is `1 + count(thresholds < v)`, which gives 1 to 20. A value of 0 gives 0 (MHz and RPM) or 1 (CPU temp).

| bar | thresholds |
|---|---|
| CPU temp (x10) | 50 100 150 200 250 300 350 400 450 500 550 600 650 700 750 800 850 900 1000 |
| MHz | 500 1000 1200 1400 1600 1800 2000 2100 2300 2500 3000 3500 4000 4500 5000 5500 6000 6500 7000 |
| RPM | 50 100 150 200 300 450 600 800 1000 1200 1400 1600 1800 2000 2200 2400 2600 2800 3000 |

The other bars are computed directly:
- GPU temp (x10): `min(v / 100 + 1, 10)`, or 0 when v = 0.
- Usage %: `min(u / 10 + 1, 10)`, or 0 when u = 0. CPU usage is forced to ≥ 1 whenever CPU temp > 0.

Clamps applied by the app:
- CPU power < 999 W.
- CPU clock ≤ 9999 MHz.
- Usage ≤ 100 %.

## Other traffic (not needed for the display)
- **Firmware version query** (`fcn.0040daa0`, called only by the updater): SetFeature `07 00 00…`, then `IOCTL_HID_GET_FEATURE` (`0xB0192`) for report 7. The reply gives `b1 << 8 | b2` as the version.
- The updater also writes firmware with `WriteFile` (`0x40c2a0`, `0x40c5b0`). **Never send anything except the five packets above.**

## Where the Windows values come from
The app reads a 0x62c-byte struct from shared memory filled by `api-ms-win-core-sysinfo-847-*.dll`:
- CPU block: power `+0x84`, MHz `+0x94`, temp `+0x98`, usage `+0x9c`.
- GPU block: `+0x120..+0x12c`.
- Fans: count `+0x380`, RPMs `+0x384…`.
- Pump RPM: `+0x2d8`.

Linux replacements:
- Temp: `k10temp` Tctl (AMD) or `coretemp` "Package id 0" (Intel).
- Clock: max `scaling_cur_freq`.
- Usage: `/proc/stat`.
- Power: none without root (RAPL `energy_uj` is 0400), so it sends 0.
- RPM: needs the out-of-tree `it87`, so it sends 0 for now.
