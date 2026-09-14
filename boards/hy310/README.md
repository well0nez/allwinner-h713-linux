# HY310

The board this repository is built and tested on. MagCubic HY310 projector, H713 with a DLP optical
engine, silkscreen **`HY260_QZ713_V3.1`** (`docs/hardware.md`). Two other names for "the projector
board" circulate in the base tree — `HY200_QZ713_V2` and `HY200_QZ713DF_A1` — and neither matches
this unit; see the two `hy200-*` directories.

| | |
|---|---|
| Status | **verified** |
| Verified by | well0nez, HY310, `v0.5-beta`, 13.09.2026 |
| Profile | `installer/h713/profiles/hy310.py` |
| Image | `h713-hy310-<version>-{a-bootkette,b-system,c-gptkopie}.img` |
| Kernel DTB | `sun50i-h713-hy310` |
| U-Boot base | `hy310_defconfig` (was `hy310_qz713_v3_1_defconfig`) |
| SoC | H713 (`sun50iw12p1`), SoC-ID `0x1860` |
| DRAM | DDR3, 1 GiB, 792 MHz — measured from four independent sources (`doku/10-hardware.md`) |
| Panel | 1920×1080, dual port, 143.0016 MHz pixel clock, declared project id `0x30` |
| eMMC | 7.28 GiB, 15 269 888 sectors, no SD slot; boot media is eMMC or FEL |

## What was measured

`STATUS.md` (snapshot 2026-09-12) is the long version; every row there names a date and a log. In
short, on this device:

- standalone boot from eMMC, power-on to a Debian login, 20/20 cold starts
  (`analyse/boot/r5-20-kaltstarts-20260910.txt`)
- the projector image (LVDS/DLP) and HDMI input with picture controls and audio, six display modes at
  60 Hz, colour-correct, 08.09.
- Wi-Fi as an access point and as a station against a real network, 12.09.
- focus motor, internal camera, fan tacho with the stall poweroff actually triggered on the device,
  11./12.09.
- FEL recovery and the installer including restore-to-stock, power key gate, standby at 4 W

Open on this board, and written down because they are *not* done: 20 gate cycles with the power key,
environment carry-over across a reinstall, a phone joining the access point. Missing entirely:
Bluetooth, AV1 decode, HDCP 1.4, any desktop.

**One caveat carried over from `STATUS.md`:** every image built before 2026-09-12 20:00 — including
the one on the device — shipped a BL31 from 10.09. with assertions enabled (49 260 bytes). A clean
build produces the intended release BL31 (45 164 bytes). Same source minus the assertions, but the
next image installed on this board has an EL3 firmware that has not been through a device acceptance
run yet.

## Where the numbers come from

- **DRAM** — `installer/h713/profiles/hy310.py`, `"dram"`: the 24 words at `boot0_sdcard.fex+0x38` of
  the stock `update.img`. `uboot.config` ships the DRAM block of the released U-Boot defconfig
  instead, which differs from that dump in five words; each one is marked in the file with the reason
  (`para2`/`tpr13` are patched by the flashing tool, `tpr0`–`tpr2` are unused on the DDR3 path).
- **Panel** — `profiles/hy310.py`, `"panel"`: `Reserve0.fex:panel_config.ini`, declared project id
  `0x30`, 1920×1080 dual port, htotal 2128, vtotal 1120, 143 001 600 Hz, hsync 44, vsync 5, hbp 88,
  vbp 20, PWM channel 2 at 25 kHz.
- **Partition layout, unique regions, firmware digests** — same profile, from
  `umbau/fixtures/images/hy310-update.img.json`.
- **Display firmware** — `display.bin` 1 256 216 bytes,
  `16c74a28187f342de657828fab65145b140ac9411c40cccc02eed25047472ee9`, HDCP wait site `0x4b13d0a4`
  (`profiles/hy310.py`, `"mips"`).
- **Verification date and version** — `profiles/hy310.py`, `"verified_by"`; `RELEASES.md` for what
  `v0.5-beta` means.

## Device tree

`KERNEL_DTB=sun50i-h713-hy310` and `CONFIG_DEFAULT_DEVICE_TREE="allwinner/sun50i-h713-hy310"` name a
DTS that is an include of the HY200 bench DTS plus this board's model and compatible
(`doku/121` §, stage 4). Until that patch is in the kernel series and in `arch/arm/dts/` of the
U-Boot fork, `BOARD=hy310 build/build.sh kernel` stops at the missing DTB — by design: the FIT must
not be built with a DTB named after a different board, which is what happened before stage 4.
