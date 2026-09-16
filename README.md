# H713 Linux

Mainline Linux **6.18.38** and a fully open boot chain (U-Boot SPL, TF-A BL31, U-Boot, Linux) on projectors
built around the Allwinner **H713** (sun50iw12p1). It started on the MagCubic HY310 and that is still the one
board this system has been run on; the repository now knows several H713 boards, holds a profile for each
firmware it has seen, and builds images only for boards that somebody has actually tested. No vendor source
code, no vendor Android: the boards' own firmware was reverse-engineered until the display, the HDMI input,
the sound and the motor could be driven from Linux.

[![Ko-fi](https://ko-fi.com/img/githubbutton_sm.svg)](https://ko-fi.com/well0nez)

**See it running** - HDMI input on the projector, test pattern and audio in sync (2026-09-08):
https://github.com/user-attachments/assets/75bb0b88-038e-4703-a6f9-def8eb071986

The kernel series builds on [cstenger/allwinner-h713-mainline](https://github.com/cstenger/allwinner-h713-mainline)
(vendored here as `mainline/`, full history) - whose own driver base, patches `0001` - `0022`, came from
this repository's `legacy` branch in the first place (tag `legacy-arm32-2026-08`). Everything above
`0049` is new work for the projector.

> **Beta - read this before you flash.**
> Installing means overwriting Android. Make a **full dump of your device first** - that is the very first
> thing [FLASHING.md](FLASHING.md) does, and it needs nothing but the projector, a USB A-to-A cable and this
> repository - or have the matching vendor firmware image at hand. Without one, a failed install is not
> repairable: the display firmware, the ARISC firmware and the picture tables are proprietary and are not in
> this repository, and the keys and MAC addresses in your device's secure storage exist exactly once, on your
> device.

## What works

Verified on hardware, with the date and the log in [STATUS.md](STATUS.md).

| | |
|---|---|
| **Boots standalone** | power → U-Boot → Debian 13 (arm64) from eMMC, 20/20 cold starts, no host, no network |
| **The projector image** | LVDS panel driven through the MIPS display firmware; KMS device for anything that draws |
| **HDMI input** | a V4L2 capture device: signal detection, timings, source switch, picture controls, 1080p60 and five more modes |
| **HDMI audio** | HDMI sound out of the speaker, lip-sync verified, one volume control |
| **Wi-Fi** | AIC8800D80 as an access point or as a client on your network, configured in `/etc/h713/wifi.env` |
| **Focus motor** | manual focus with a range watcher that stops before the mechanical stop |
| **Camera** | the built-in camera works as a normal V4L2 device - probe, controls, still images ([`h713-cam`](docs/tools/h713-cam.md)) |
| **Fan and power key** | fan tacho by interrupt, and the device powers itself off if the fan stalls - this board has no temperature sensor, so the tacho is the protection ([details](docs/subsystems/board-mgr.md)) |
| **Recovery** | FEL from software (`h713-fel`), eMMC as a USB drive, stock Android restorable byte-for-byte |

Not there yet: **Bluetooth** (driver builds, the firmware split has not been done), **AV1 decode**,
**HDCP 1.4** for protected sources, and there is **no desktop** in the shipped image - it runs `h713-tv`,
not a compositor. Hardware video decode, the IOMMU and the Mali GPU come from cstenger's tree and are
verified there, not re-tested in this image. Details and honest limits: [docs/known-issues.md](docs/known-issues.md).

**These projectors have no HDMI output.** The projector itself is the only display. HDMI is an *input*.

## Read order

1. [STATUS.md](STATUS.md) - what works, per subsystem, with evidence. Sixty seconds.
2. [FLASHING.md](FLASHING.md) - get it onto a device: dump, extract, install, first boot.
3. [docs/usage/first-hour.md](docs/usage/first-hour.md) - the walk-through afterwards: get in, get a
   picture, set it up, know your way out.
4. [docs/hardware.md](docs/hardware.md) - what is on the board.
5. [docs/architecture.md](docs/architecture.md) - three processors (ARM, MIPS, ARISC) and who owns what.
   Read this before the subsystem pages; most surprises on this SoC come from the split.
6. [BUILDING.md](BUILDING.md) - build everything from a clean clone with one command.
7. [RELEASES.md](RELEASES.md) - what a version number means here, and what the build stamp is for.
8. [ROADMAP.md](ROADMAP.md) - what is missing, what is unproven, and what it would take. Read it before
   you plan anything around this port.

Working on the port rather than using it? Then also [BUILDING.md](BUILDING.md) with
[docs/build-container.md](docs/build-container.md), [docs/kernel-patches.md](docs/kernel-patches.md), and
[docs/dead-ends.md](docs/dead-ends.md) - the explanations we ruled out on hardware, so nobody spends a
week on them twice.

Per-area pages live in [`docs/subsystems/`](docs/subsystems/) - display, MIPS, HDMI input, audio, video,
picture quality, cpu_comm, ARISC, Wi-Fi, focus motor, board manager, crypto engine, eMMC layout. What we
added to U-Boot is in [`docs/uboot/`](docs/uboot/): the [boot chain and defconfig matrix](docs/uboot/README.md),
the [`h713_*` commands](docs/uboot/commands.md), [every environment variable](docs/uboot/environment.md),
and [the power-on gate](docs/uboot/power-gate.md).

## The tools

Everything here is ours and documented; nothing needs a vendor daemon.

| On the device | |
|---|---|
| [`h713-tv`](docs/tools/h713-tv.md) | the HDMI input as a service: picture on the wall, console back when the signal drops, one control channel for picture, volume, presets and aspect |
| [`h713-focus`](docs/tools/h713-focus.md) | move the focus motor by hand, with the range watcher read before and after every step |
| [`h713-cam`](docs/tools/h713-cam.md) | the built-in camera: probe, controls, still image |
| [`h713-wifi`](docs/tools/h713-wifi.md) | access point or station, from one file, `/etc/h713/wifi.env` |
| [`h713-pq`](docs/tools/h713-pq.md) | turn the vendor picture tables into register values and gamma curves |
| [`h713-fel`](docs/tools/h713-fel.md) | put the running device back into USB recovery mode, without the reset button |
| [everything else that runs](docs/services.md) | the services in the image, the journal switch, and the one security decision you should know about |
| **On your PC** | |
| [`h713-install`](docs/tools/h713-install.md) | dump, extract, install, verify - and the way back to stock, in one tool with subcommands |
| [`h713-extract`](docs/tools/h713-extract.md) | pull the device-specific firmware out of *your* dump |
| [`h713-mkimage`](docs/tools/h713-mkimage.md) | build the three-part image with the gap over secure storage |
| [`h713_probe`](docs/tools/h713-probe.md) | **a different H713 projector?** FEL-boot this and it says what your board is - DRAM, partitions, display firmware, panel. Writes nothing |
| [`release/build-all.sh`](BUILDING.md) | clean clone → flashable image, eleven steps, one command |

## Hardware at a glance

| Part | Detail |
|---|---|
| SoC | Allwinner H713 (sun50iw12p1), 4× Cortex-A53 |
| RAM / storage | 1 GiB DDR3 at 792 MHz on the HY310 (other boards: see Boards), 7.3 GB eMMC |
| Display out | LVDS → DLPC3435 → DLP imager. Driven by a **MIPS32 co-processor** running `display.bin` |
| Display in | HDMI 1.4, Synopsys DW-HDMI-RX, up to 1080p60 |
| Second co-processor | OR1K **ARISC**: power management, hot-plug detect, EDID |
| GPU | Mali-G31 (Panfrost) |
| Wi-Fi / BT | AIC8800D80 over SDIO / UART |
| Audio | internal codec, speaker |
| Boot media | eMMC or FEL only - there is no SD slot |

## Boards

One directory per board under [`boards/`](boards/README.md), one installer profile per firmware. The ladder a
new board climbs: **probe** (`u-boot-h713-probe.bin` over FEL, writes nothing, prints what the board is) ->
**profile** (the installer recognises it and dumps its own regions) -> **test image** (built for that board
alone, flashed only by its owner with a full dump as the way back) -> **verified** (the owner reports a green
run; from then on a release image exists for it). The rule behind it: no image for a board nobody has tested.

| Board id | Sold as | DRAM | Panel (project id) | State |
|---|---|---|---|---|
| `hy310` | MagCubic HY310, silkscreen HY260_QZ713_V3.1, Android 11 firmware of 2025-07 | DDR3, 792 MHz, 1 GiB | 1920x1080 dual-port (0x30) | **verified**: this system runs on it; install, boot, recovery and restore to stock were done on hardware for every release ([STATUS.md](STATUS.md), v0.6-beta, 2026-09-15) |
| `hy300-pro` | MagCubic HY300 Pro, 2024 board, Android 10 firmware | DDR3, 636 MHz, 1 GiB | 0x34; 1280x720 single-port expected, not measured on this board | **in test**: test image [`hy300-pro-test1`](https://github.com/well0nez/allwinner-h713-linux/releases/tag/hy300-pro-test1) with its owner ([issue #1](https://github.com/well0nez/allwinner-h713-linux/issues/1)); its DRAM block, partition table and display-firmware revision come from his probe run |
| `hy200-qz713df-a1` | sold as "HY300 Pro+" (2025, DDR3); cstenger's bench board HY200 QZ713DF_A1, Android 11 firmware of 2025-09 | DDR3, 624 MHz, 1 GiB | 1280x720 single-port (0x34) | **profile, testable**: cstenger verified the kernel of his tree on it; nobody has run this image there. Firmware, DRAM block and panel are known, a test image is one build away |
| `hy200-qz713-v2` | sold as "HY300 Pro+" (2025, LPDDR3); HY200 QZ713_V2, Android 11 firmware of 2025-07 | LPDDR3, 720 MHz, 1 GiB | 1280x720 single-port (0x34) | **profile, testable**: firmware and panel known; which LPDDR3 timing words are the board's (the image's or cstenger's defconfig's) is undecided, so a probe run on a real board comes first |
| `hy300-t08` | HY300 T08, 2024, Android 10 firmware | DDR3, 640 MHz, 1 GiB | 1280x720 single-port (0x34) | **profile only, testable**: everything known comes from the firmware image; a probe run by an owner would complete it |
| `hy350` | HY350, 2024, Android 10 firmware | DDR3, 792 MHz, 1 GiB | 1920x1080 (0x30), other blanking than the HY310 | **profile only, testable**: same as above; the panel timing differs from the HY310's although the project id is the same |
| `l018` | L018, Android 11 firmware of 2025-05 | unknown | unknown | **profile only, not yet testable**: known from one extractor run over a real device, no DRAM data, no firmware image here |

The values come from the boards' own firmware (`installer/h713/profiles/`, every number with its source) and
from probe runs on real devices. Feeding a board the wrong DRAM parameters trains "OK" and then hangs on
reads, so every result here says which board it came from. The system itself (display, HDMI input, audio,
Wi-Fi, focus motor, camera, recovery) is described below for the HY310, the board it was developed on.

## Getting it running

```bash
release/build-all.sh --version v0.6-beta --vendor <your extraction>   # image, from a clean clone
release/build-all.sh --version v0.6-beta --board hy300-pro --test-image  # a test image for a board in test
installer/h713-install --help                                         # identify, dump, install, restore
```

The image ships **no proprietary files**. Firmware for the display, the ARISC, Wi-Fi, the picture
tables and the boot logo are placeholders that [`h713-extract`](docs/tools/h713-extract.md) fills from **your own** device
dump during installation. That is why the installer wants a dump, and why nothing here needs a licence
you don't already have.

## Layout

```
mainline/        cstenger's tree as a git subtree + our kernel patch series (patches/kernel/series)
uboot-h713/      our U-Boot commits as patches, generated from the fork (read-only mirror)
installer/       h713-install, h713-mkimage, h713-extract and helpers
rootfs/          the Debian 13 recipe: package list, overlay, install script, tests
userspace/       h713-tv, h713-pq, h713-focus, h713-cam
release/         build-all.sh - clean clone to flashable image, --board picks the board
boards/          one directory per board: board.env, its U-Boot DRAM block, what is known about it
tools/           host-side helpers from the bring-up: UART capture, register diffs, disassembly aids
analyse/boot/    boot logs and acceptance records; analyse/beamer-cam/ camera findings
docs/            this documentation
doku/            the German working journal: every measurement, every wrong turn, dated
```

`doku/` is the long form and stays German. When an English page says "details: doku/88", that is where the
measurements are.

## Licence

Code **GPL-2.0** ([LICENSE](LICENSE)), documentation **CC BY-SA 4.0** ([LICENSE.docs](LICENSE.docs)).
Use it, change it, build on it - keep the notices and credit **well0nez**.

## Credit and provenance

The H713 driver series - CCU, pinctrl, MMC, USB PHY, PWM, board manager, cpu_comm and the rest of
`0001` - `0022` - is **well0nez**'s work; it started in this repository's `legacy` branch, and cstenger
carries it in his tree with attribution. **cstenger** built the arm64 side around it (`0023` - `0048`: DTS,
defconfig, boot chain, cpufreq) and the display and video branch. Everything from `0049` upwards - the
projector itself: ARISC, HDMI input, audio, focus motor, Wi-Fi, the installer and the userspace tools -
is well0nez again. Details in [PROVENANCE.md](PROVENANCE.md).
