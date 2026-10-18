# H713 Linux

Mainline Linux **6.18.38** and a fully open boot chain (U-Boot SPL, TF-A BL31, U-Boot, Linux) on projectors
built around the Allwinner **H713** (sun50iw12p1). It started on the MagCubic HY310, and that is still the one
board a release image is built for; the repository now knows several H713 boards, holds a profile for each
firmware it has seen, gives a board in test TEST images for its owner, and builds release images only for
boards that somebody has actually tested. No vendor source
code, no vendor Android: the boards' own firmware was reverse-engineered until the display, the HDMI input,
the sound and the motor could be driven from Linux.

> **Disclaimer:** this code was written mainly in collaboration with AI and needs a complete review and refactor.
> Please keep that in mind at this stage.

[![Ko-fi](https://ko-fi.com/img/githubbutton_sm.svg)](https://ko-fi.com/well0nez)

> **Working on this repository, as a person or as an agent?** Start at [AGENTS.md](AGENTS.md): where which kind of knowledge lives, which tools are mandatory, which gates have to be green, and what to do with a new finding.

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
| **Boots standalone** | power → U-Boot → Debian 13 (arm64) from eMMC, 20/20 cold starts, no host, no network; the device's own boot logo 2 s after the power key (v0.6-beta: 7 s), the kernel at 3.5 s (was 9 s) |
| **The projector image** | LVDS panel driven through the MIPS display firmware; KMS device for anything that draws |
| **HDMI input** | a V4L2 capture device: signal detection, timings, hot plug, source switch, picture controls, a magnifier (zoom in), and the display firmware's own mode table as the list of what locks - a source whose raster is in no record of it is named and refused instead of left hanging |
| **HDMI audio** | HDMI sound out of the speaker, lip-sync verified, one volume control on the stock curve; the box's own sounds are mixed into it by the DSP (`hw:hy310hdmi,0`, ALSA's default) |
| **Wi-Fi** | AIC8800D80 as an access point or as a client on your network, configured in `/etc/h713/wifi.env` |
| **Focus motor** | manual focus with a range watcher that stops before the mechanical stop; [`h713-autofocus`](docs/tools/h713-autofocus.md) is the vendor's own search rebuilt - on 02.10.2026 it ended sharp against a wall, twice at the same motor position; more walls and evenings are still to come |
| **Camera** | the built-in camera works as a normal V4L2 device - probe, controls, still images ([`h713-cam`](docs/tools/h713-cam.md)) |
| **Fan and power key** | fan tacho by interrupt, and the device powers itself off if the fan stalls - this board has no temperature sensor, so the tacho is the protection ([details](docs/subsystems/board-mgr.md)) |
| **Recovery** | FEL from software (`h713-fel`), eMMC as a USB drive, stock Android restorable byte-for-byte |
| **Keystone and zoom** | the picture squared up on the Mali GPU, by hand or from the projector's tilt sensor, and shrunk without cutting anything off; four projection modes (front, rear, ceiling, rear-ceiling) and the vendor's soft edge; the firmware's picture controls still act on the corrected picture ([guide](docs/guides/keystone.md)) |
| **Settings page** | `http://<the projector>:8080/` from a phone or a browser: keystone, zoom, focus and autofocus, picture presets and sliders, sound - no login ([guide](docs/guides/settings-page.md)) |
| **Autofocus** | the vendor's search rebuilt: chessboard on the wall, the built-in camera, the focus motor - one command or one button, turns round at the ends of the travel ([guide](docs/guides/autofocus.md)) |
| **Remote** | the stock Bluetooth remote: hold Left+Right to pair, all 16 keys and the mouse arrive as Linux input events, it reconnects on a key press after a reboot ([details](docs/subsystems/wifi.md#bluetooth)). Nothing in the image acts on the keys yet except Power, which shuts the projector down |

In `main`, for the next release: the **IR receiver**, the remote's keys acting (volume, mute, focus) and **overlays** over
the picture, pre-distorted under the keystone ([h713-osd](docs/tools/h713-osd.md), [h713-keys](docs/tools/h713-keys.md)).
Not there yet: **AV1 decode**,
and there is **no desktop** in the
shipped image - it runs `h713-tv`, not a compositor. Hardware video decode and the IOMMU come from cstenger's tree
and are verified there, not re-tested in this image. Details and honest limits:
[docs/known-issues.md](docs/known-issues.md).

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

Every documentation page is listed in one place: [docs/README.md](docs/README.md).

Per-area pages live in [`docs/subsystems/`](docs/subsystems/) - display, MIPS, HDMI input, audio, video,
picture quality, cpu_comm, ARISC, Wi-Fi, focus motor, board manager, crypto engine, eMMC layout. What we
added to U-Boot is in [`docs/uboot/`](docs/uboot/): the [boot chain and defconfig matrix](docs/uboot/README.md),
the [`h713_*` commands](docs/uboot/commands.md), [every environment variable](docs/uboot/environment.md),
and [the power-on gate](docs/uboot/power-gate.md).

## The tools

Everything here is ours and documented; nothing needs a vendor daemon.

| On the device | |
|---|---|
| [`h713-tv`](docs/tools/h713-tv.md) | the HDMI input as a service: picture on the wall, console back when the signal drops, one control channel for picture, volume, presets, aspect and zoom |
| [`h713-focus`](docs/tools/h713-focus.md) | move the focus motor by hand, with the range watcher read before and after every step |
| [`h713-autofocus`](docs/tools/h713-autofocus.md) | the vendor's autofocus rebuilt: chessboard on the panel, frames from the internal camera, the vendor's sharpness metric and its search. It runs and sharpens; convergence is still unproven |
| [`h713-cam`](docs/tools/h713-cam.md) | the built-in camera: probe, controls, still image |
| [`h713-wifi`](docs/tools/h713-wifi.md) | access point or station, from one file, `/etc/h713/wifi.env` |
| [`h713-pq`](docs/tools/h713-pq.md) | turn the vendor picture tables into register values and gamma curves |
| [`h713-fel`](docs/tools/h713-fel.md) | put the running device back into USB recovery mode, without the reset button |
| [`h713-warp`](docs/tools/h713-warp.md) | the keystone and the zoom, drawn on the GPU |
| [`h713-keystone`](docs/tools/h713-keystone.md) | the automatic keystone from the accelerometer, once after a move |
| [`h713-panel`](docs/tools/h713-panel.md) | the settings page in the browser, port 8080 ([guide](docs/guides/settings-page.md)) |
| [`h713-features`](docs/tools/h713-features.md) | which optional hardware - camera, accelerometer, focus motor - this board has |
| `h713-remote-pair` | pairs the stock Bluetooth remote and keeps it connected ([details](docs/subsystems/wifi.md#bluetooth)) |
| [`h713-arisc`](docs/tools/h713-arisc.md) | which firmware the power-management coprocessor runs - crust, ours, or the vendor's from your dump - and the switch between them for the next boot, no reinstall |
| [everything else that runs](docs/services.md) | the services in the image, the journal switch, and the one security decision you should know about |
| **On your PC** | |
| [`h713-install`](docs/tools/h713-install.md) | dump, extract, install, verify - and the way back to stock, in one tool with subcommands |
| [`h713-extract`](docs/tools/h713-extract.md) | pull the device-specific firmware out of *your* dump - now the panel and optics ini files too; `--profile <board>` writes a panel row out of them, every value naming the line it came from |
| [`h713-mkimage`](docs/tools/h713-mkimage.md) | build the three-part image with the gap over secure storage |
| [`h713-hdcpkey`](docs/tools/h713-hdcpkey.md) | which HDCP key material a dump holds and where - searched by structure, fingerprints only, never key bytes |
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

One directory per board under [`boards/`](boards/README.md), one installer profile per board, and a variant
per stock firmware where one board left the factory with several. The ladder a new board climbs: **probe**
(`u-boot-h713-probe.bin` over FEL, writes nothing, prints what the board is) ->
**profile** (the installer recognises it and dumps its own regions) -> **test image** (built for that board
alone, flashed only by its owner with a full dump as the way back) -> **verified** (the owner reports a green
run; from then on a release image exists for it). The rule behind it: no image for a board nobody has tested.

**Looking for your own projector?** Find it in the *Sold as* column, not in the board id — the
ids follow the **circuit board**, and one board is sold in several projectors. The HY300PRO-G-EU,
for instance, lives under `hy200-qz713df-a1`.

**Your projector, or its Android firmware, is not in the table?** Then the installer stops before it writes
anything and prints one row about the device (`installer/h713-install identify` prints the same row and writes
nothing). Please [open an issue](https://github.com/well0nez/allwinner-h713-linux/issues) with
that row: we add the profile, and from then on the installer knows your firmware. A firmware it does not
know is never guessed at - the places of a foreign version could cost the device's secure storage.

| Board id | Sold as | DRAM | Panel | State |
|---|---|---|---|---|
| [`hy310`](boards/hy310/) | MagCubic HY310 | DDR3 792 MHz | 1920×1080 dual (0x30) | **verified** |
| [`hy300-pro`](boards/hy300-pro/) | MagCubic HY300 Pro (2024) | DDR3 636 MHz | 1280×720 (0x34) | in test |
| [`hy200-qz713df-a1`](boards/hy200-qz713df-a1/) | HY300PRO-G-EU · "HY300 Pro+" (2025) · cstenger's bench board | DDR3 792 / 624 MHz | 1280×720 (0x34) | in test |
| [`hy200-qz713-v2`](boards/hy200-qz713-v2/) | "HY300 Pro+" (2025, LPDDR3) | LPDDR3 720 MHz | 1280×720 (0x34) | profile only |
| [`hy300-t08`](boards/hy300-t08/) | HY300 T08 (2024) | DDR3 640 MHz | 1280×720 (0x34) | profile only |
| [`hy350`](boards/hy350/) | HY350 (2024) | DDR3 792 MHz | 1920×1080 (0x30) | profile only |
| `l018` | L018 (2025) | unknown | unknown | profile only, no board directory |

### What the states mean, board by board

- **`hy310` — verified.** Silkscreen `HY260_QZ713_V3.1`, stock Android 11 of 2025-07. This system runs
  on it: install, boot, recovery and restore to stock were done on hardware for every release, and
  every part of `v0.96-beta` went through the device tests of 2026-10-02 to 10-04
  ([STATUS.md](STATUS.md)).
- **`hy300-pro` — in test**, for its owner ([issue #1](https://github.com/well0nez/allwinner-h713-linux/issues/1)).
  `hy300-pro-test9` (2026-09-25) is the last one: its boots stop at random places, because the lamp's PWM
  words reached the display firmware as six parameters instead of one address — fixed by kernel patch `0168`
  on the HY300PRO-G-EU — and its U-Boot ran project 0x30 instead of 0x34. `test10` follows after
  `v0.96-beta`. **No green run yet.** Its DRAM block, partition table and firmware revision come from its
  owner's probe run. Not the same device as `hy200-qz713df-a1`.
- **`hy200-qz713df-a1` — one board, two firmware variants.** The maintainer's own HY300PRO-G-EU
  (`projector05061226`, Android 11 of 2025-05) is **in test**: TEST images boot on it and the picture has
  been right since the 8-bit LVDS fix; the accelerometer is measured; it has no camera and no focus motor.
  No green run reported yet. The "HY300 Pro+" variant (`projector09220931`, 2025-09) is **profile only**
  and testable: firmware, DRAM block and panel are known from its image, a test image is one build away,
  but nobody has run one on that device.
- **`hy200-qz713-v2` — profile only, not yet testable.** Firmware and panel are known from its image, but
  the timing words are cstenger's (LPDDR3 at 720 MHz; the image's own are a DDR3 template its boot0 does
  not use), and its U-Boot base and kernel tree are still his bring-up ones, not our layout.
- **`hy300-t08`, `hy350` — profile only, testable.** Everything known comes from the firmware image; a
  probe run by an owner would complete it. The HY350's panel timing differs from the HY310's even though
  the project id is the same.
- **`l018` — profile only**, and the one entry without a board directory: known from a single extractor
  run over a real device, no DRAM data and no firmware image here.

The values come from the boards' own firmware (`installer/h713/profiles/`, every number with its source) and
from probe runs on real devices. Feeding a board the wrong DRAM parameters trains "OK" and then hangs on
reads, so every result here says which board it came from. The system itself (display, HDMI input, audio,
Wi-Fi, focus motor, camera, recovery) is described below for the HY310, the board it was developed on.

## Getting it running

```bash
release/build-all.sh --version v0.96-beta --vendor <your extraction>   # image, from a clean clone
release/build-all.sh --version v0.96-beta --board hy300-pro --test-image  # a test image for a board in test
release/build-all.sh --version v0.96-beta --board hy200-qz713df-a1 --variant projector05061226 --test-image
installer/h713-install --help                                          # identify, dump, install, restore
```

The image ships **no proprietary files**. Firmware for the display, the ARISC, Wi-Fi, the picture
tables and the boot logo come from **your own** device: [`h713-extract`](docs/tools/h713-extract.md) takes them out of
your dump and the installer copies them into the image while installing, as ordinary files of any size. That is
why the installer wants a dump, and why nothing here needs a licence you don't already have.

## Layout

```
mainline/        cstenger's tree as a git subtree + our kernel patch series (patches/kernel/series)
uboot-h713/      our U-Boot commits as patches, generated from the fork (read-only mirror)
tfa-h713/        our TF-A (BL31) commits the same way - the platform, and the HDCP 1.4 key path
installer/       h713-install, h713-mkimage, h713-extract and helpers
rootfs/          the Debian 13 recipe: package list, overlay, install script, tests (rootfs/README.md)
userspace/       h713-tv, h713-pq, h713-focus, h713-autofocus, h713-cam, h713-warp, h713-keystone, h713-panel,
                 h713-features, h713-remote-pair, h713-gpu-probe
release/         build-all.sh - clean clone to flashable image, --board picks the board (release/README.md)
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
