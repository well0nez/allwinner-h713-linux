# Status

Snapshot of **2026-09-12**. "Works" means *verified on the projector*, with the date and the log named -
not "compiles". Where a row says **unverified**, nobody has proven it on this hardware, and you should
treat it as a claim, not a fact.

The image on the test device is a development build from 10./12.09. (internally `v0.9`); the current
build from a clean clone is a week younger and differs in one thing that matters - see *Boot chain*
below. What the numbers mean: [RELEASES.md](RELEASES.md).

## Summary

- **Works:** standalone boot from eMMC, projector image, HDMI input with picture controls, HDMI audio,
  Wi-Fi as an access point, focus motor, internal camera, fan tacho and thermals (reporting only),
  power key, FEL recovery,
  installer including restore-to-stock. The fan-stall poweroff is armed again since 12.09.
- **Missing:** Bluetooth, AV1 decode, HDCP 1.4 for protected sources, any desktop.
- **Not re-tested by us:** hardware video decode, IOMMU, Mali GPU - these come from cstenger's tree.

## Boards

One board is tested; the others are described. Since 15.09. the two HY200 boards have installer
profiles too, read out of the two 2025 "HY300 Pro+" vendor images - a profile describes the stock
firmware and tests nothing, so it changes no row's state. The rule behind that, from `doku/121` §5 and enforced
by `release/build-all.sh --board`: **no image for a board nobody has tested.** A row below
*verified* is a description, not a claim that anything runs on it.

| Board | State | Who ran it, and when | What exists for it |
|---|---|---|---|
| **HY310** (silkscreen `HY260_QZ713_V3.1`) | **verified** | well0nez, on his HY310, `v0.5-beta`, 13.09.2026 | everything else on this page. The only board an image is built for |
| **HY200 QZ713DF_A1** | profile-only | nobody has run a build of *ours* on it. cstenger ran his own tree on his own bench board - kernel 6.18.38 boot-good (`mainline/config/versions.env`); that is his run, not ours | kernel and U-Boot defconfigs, device tree, and since 15.09. the installer profile `hy200_qz713df_a1` - its stock firmware is the 2025-09-22 "HY300 Pro+" DDR3 image (624 MHz, `display.bin` `4380f1b3…`) |
| **HY200 QZ713_V2** | profile-only | nobody | cstenger's LPDDR3 defconfig and device tree, marked untested on hardware in his tree too, plus the installer profile `hy200_qz713_v2` - its stock firmware is the 2025-07-10 "HY300 Pro+" LPDDR3 image (720 MHz, `display.bin` `4628cbaf…`, HDCP wait site `0x4b13d538`) |
| **HY300 T08** | profile-only | nobody | installer profile and DRAM fragment, both read out of its stock image (`doku/121` §2). No device tree of ours |
| **HY350** | profile-only | nobody | as above. It ships the same `display.bin` as the T08 and a different panel - which is why the panel comes from the declared project id, never from the firmware image |
| **HY300 Pro** | partial | nobody. One owner report, [issue #1](https://github.com/well0nez/allwinner-h713-linux/issues/1), 13.09.2026: a dump-only run, nothing written, no green run | installer profile with gaps - layout from his log, DRAM clock 636 MHz, HDCP wait site unknown |

`boards/<id>/board.env` carries these states machine-readably, and `bash boards/check.sh` holds each
one against the installer profile in `installer/h713/profiles/`. What a board below *verified* gets
instead of an image is the read-only probe, which writes nothing and runs from FEL on any H713:
[docs/tools/h713-probe.md](docs/tools/h713-probe.md). A row becomes *verified* when that board's
owner reports a green run of a build of ours, with a date - see [BUILDING.md](BUILDING.md), *Boards*.

## Subsystems

| Subsystem | State | Where it lives | Evidence |
|---|---|---|---|
| Boot chain | works, with one caveat | SPL → BL31 → U-Boot → FIT, all from source | 20/20 cold starts (`analyse/boot/r5-20-kaltstarts-20260910.txt`) - but a fresh build now ships a different BL31 than the one those runs used; see *Boot chain* below |
| Power key gate | works | U-Boot `CONFIG_H713_POWER_GATE`, env `h713_gate` | 09.09.; standby 4 W, red LED, key starts |
| eMMC layout v3 | works | six partitions, secure storage untouched by design | 10.09., [docs/subsystems/emmc-layout.md](docs/subsystems/emmc-layout.md) |
| Debian 13 rootfs | works | `rootfs/`, 242 MiB, zram, ssh key-only | built by `build-all`, acceptance tests in the build log |
| Projector image (LVDS/DLP) | works | MIPS firmware + `sun50i-h713-afbd` KMS driver | continuous since 08.09. |
| HDMI input | works, one rough edge | `sun50i-h713-hdmirx`, node found by name (it was `/dev/video3` on 12.09., not `video1` - the camera enumerated first) | six modes at 60 Hz, colour-correct, 08.09.; a freshly plugged source may need `h713-tv ctl replug` (12.09., [docs/known-issues.md](docs/known-issues.md)) |
| Picture path userspace | works | `h713-tv` service, `h713-tv ctl …` | 08.09.; presets, gamma, aspect, controls |
| HDMI audio | works | codec-I2S + MSP DSP driver, one volume control | 08.09. 22:05, lip-sync judged by ear |
| ARM ↔ MIPS IPC | works | `cpu_comm` in-kernel API | callback slot leak fixed; [docs/subsystems/cpu-comm.md](docs/subsystems/cpu-comm.md) |
| ARISC (PMU, HPD, EDID) | works | `sun50i-h713-arisc` | 17.65 s to hot-plug ready |
| Wi-Fi AIC8800D80 | works | out-of-tree modules + `h713-wifi` | 12.09.: access point (−50 dBm, 5.7 MB/s, DHCP, SSH) and station against a real network (DHCP address, internet through `wlan0`) |
| Focus motor | works | `hy310_focus_motor` + `h713-focus` | range watcher measured 12.09., `analyse/boot/motor-bereichswaechter-20260912.txt` |
| Internal camera | works | `uvcvideo` + `h713-cam` | 12.09.: grab of the lit wall, mean brightness Y = 88.7, 3.2 s (`analyse/beamer-cam/p6-wand-20260912.png`) |
| Fan, tacho, stall protection | works | `hy310-board-mgr` | 4860 RPM measured 11.09.; **the fan-stall poweroff is armed and was triggered on the device** 12.09.: rail cut, device shut itself down, next boot mounted the filesystem clean (`analyse/boot/p6-notaus-luefter-20260912.txt`). No NTC on this unit, so the tacho is the protection |
| Power / standby | partial | standby is 4 W; deep sleep is designed, not built | plan `doku/104` |
| Crypto engine | present, unused | measurement module loads, crypto disabled | `doku/114` |
| Video decode, IOMMU, GPU | unverified here | cstenger's patches, in our series | verified in his tree, not in this image |
| Bluetooth | missing | driver builds, firmware split not done | `rootfs/packages.txt` explains the choice |
| HDCP 1.4 | missing | path understood, one test costs a power cycle | `doku/112` |
| HDCP 2.2 | works, device-local | key read from *your* device at boot, never shipped | `h713-hdcp-key.service` |

## Boot chain: one change since the image on the device

Everything built before 2026-09-12 20:00 shipped a **BL31 from 10.09. with assertions enabled**
(49 260 bytes). `make` considered it current and kept copying it forward, so it sits in v0.8, v0.9 and
v0.10 - including the image on the device. A clean build produces the intended release BL31
(45 164 bytes). `release/build-all.sh` now wipes the TF-A and U-Boot build directories before building.

The next image you install therefore has a *different* EL3 firmware than anything tested so far.
Nothing about it is expected to behave differently - it is the same source, minus the assertions -
but it has not been through a device acceptance run yet. That run is the next thing on our list.

## Verified display modes

1920×1080, 1280×720, 1024×768, 1440×900, 1280×1024 (pillarboxed), 1366×768 - each at 60 Hz, colour-correct
(BT.709), across arbitrarily many source switches, HDMI unplug/replug, and a cold start with no operator.

## Open device tests

These are written down because they are *not* done, not because they are expected to fail:

- phone joins the access point, `ssh root@h713` over Wi-Fi
- `mode=sta` against a real network
- environment carry-over (`h713_gate`, `h713_boot`) across a reinstall - needs a changed value before the next install
- 20 gate cycles with the power key

## Reading the German journal

Every row above has a longer story in `doku/`. Start at `doku/00-STATUS.md`; it is the same map in German,
with the measurements attached. Nothing in the English documentation claims anything that is not written
down there with a date.
