# Status

Snapshot of **23.10.2026**. "Works" means *verified on a projector*, with the date and the journal entry named - not
"compiles". Where a row says **not measured**, nobody has proven it on this hardware; treat it as a claim.

The release is **v0.97-beta**, built on 22.10.2026 from the commit the merge into `main` carries (`8da300c2`), for the
HY310 and for the HY300PRO-G-EU, each as a `media,desktop` image (Kodi, desktop, browser). Both boards run it since 22./23.10.2026:
installed over FEL with `h713-install`, the acceptance script with 25 of 25 cells passed on the HY300PRO-G-EU, the HY310
with the owner's eyes on the cells the camera could not judge (`doku/219` §5, TODO 1.0 (2)). The images are not published
yet; the tag follows the last build from `main` ([RELEASES.md](RELEASES.md)).

## Summary

- **Works:** boot from the eMMC with the device's own logo, off into U-Boot's gate and on again by the key or by either
  stock remote; the HDMI input with the display firmware's own mode table, picture controls, HDCP 1.4 and 2.2 with the
  device's keys, sound; the launcher, Kodi, a desktop and Firefox as modes; the settings page on the wall and the web page;
  the stock remote over Bluetooth and over infrared (both stock remotes); overlays over the picture; keystone by hand and
  from the tilt sensor, zoom, projection modes; autofocus and manual focus; Wi-Fi as access point and client; the camera;
  hardware video decode behind the IOMMU (H.264, HEVC, VP8, VP9); the RTC on the crystal; FEL recovery, installer, restore
  to stock.
- **Decided against, for now:** standby and crust's 0.3 W power-off - the power supply hums or whines with them (owner,
  22.10.2026, `doku/218`). The release runs the vendor's ARISC firmware; crust stays in the image as an experiment.
- **Open and visible:** the picture flickers faintly under load on the HY310 (the lamp follows the SoC's current; the cause
  of what the eye sees is a hypothesis, TODO 2.99, 9.3n); the HY300 (Pro) of issue #1 does not react to its infrared remote
  yet (TODO 2.134); AV1 decode is switched off; the installer carried `h713_gate=0` over from a dump (TODO 2.137). All of
  it in [docs/known-issues.md](docs/known-issues.md).

## Boards

The rule, from `doku/121` §5 and enforced by `release/build-all.sh`: **no image for a board nobody has tested.** A row
below *verified* describes the board; it does not claim anything runs on it.

| Board | State | Who ran it, and when | What exists for it |
|---|---|---|---|
| **HY310** (silkscreen `HY260_QZ713_V3.1`) | **verified** | the owner, on his HY310: `v0.9-beta` 22.09.2026, every release since; `v0.97-beta` installed 22.10. and 23.10.2026 (`doku/219` §5) | the release image `h713-hy310-vX.Y-media-desktop`; everything on this page unless a row says otherwise |
| **HY200 QZ713DF A1**, firmware `projector05061226` (HY300PRO-G-EU) | **verified** (this variant) | the owner, on his HY300PRO-G-EU: green run 11.10.2026 (`boards/hy200-qz713df-a1/variants/projector05061226/variant.env`); the media image since 20.10., `v0.97-beta` since 22.10.2026 with the acceptance script 25 of 25 (`doku/217`, `doku/219`) | the release image `h713-hy200-qz713df-a1-projector05061226-vX.Y-media-desktop`; no camera, no focus motor on this unit |
| **HY200 QZ713DF A1**, firmware `projector09220931` ("HY300 Pro+" 2025, DDR3) | profile only | nobody | the installer profile and the board's files; a test image is one build away (`--variant projector09220931 --test-image`) |
| **HY300 Pro** | partial, in test by its owner | [issue #1](https://github.com/well0nez/allwinner-h713-linux/issues/1): probe and dump 13.09., test images since 16.09.2026, `test11` of 22.10.2026 with the infrared retrofit; no green run | test images for its owner only; its board directory names what is known and what is not |
| **HY200 QZ713_V2** (LPDDR3) | profile only, not testable yet | nobody | cstenger's defconfig and device tree, marked untested in his tree too; not in our layout |
| **HY300 T08**, **HY350** | profile only | nobody | installer profile and DRAM fragment, read out of each stock image |
| **L018** | **verified** (26.10.2026) | its owner's unit (24.-26.10.2026, `doku/220`, `doku/222`) | its own board files in `main` since 26.10.2026: U-Boot (dark gate, lamp and fan off from the SPL, the key red/blue), kernel `0331`-`0334`, lamp modes, keystone with its own axes and optics, its own volume curve; measured on the owner's unit through a TEST image and quick deploys. Accepted with the test image `v0.97-test3` from `main` (`doku/222`); no release image yet, headphones and HDCP 2.2 not tested. *Superseded (25.10.2026):* "nothing of ours has booted on it" |

`boards/<id>/board.env` carries these states machine-readably; `bash boards/check.sh` holds each one against the
installer profile. A board below *verified* gets the read-only probe ([h713-probe](docs/tools/h713-probe.md)).

## Subsystems

| Subsystem | State | Where it lives | Evidence |
|---|---|---|---|
| Boot chain | works | SPL, BL31, U-Boot, FIT, all from source; the eMMC at HS200 with DMA | 20 of 20 cold starts (`analyse/boot/r5-20-kaltstarts-20260910.txt`); logo 2.0 s, kernel 3.5 s after the key |
| Power-on gate, remote wake | works | U-Boot `CONFIG_H713_POWER_GATE`, env `h713_gate`; `0102` decodes NEC in the gate | 2.9 W, silent (`doku/181`, `doku/218`); the power key of both stock remotes starts the board from the gate, HY300PRO-G-EU 22.10. and HY310 23.10.2026 (`doku/219` §3) |
| ARISC: the vendor firmware by default, crust experimental | works | `sun50i-h713-arisc`, `/etc/modprobe.d/h713-arisc.conf`, `h713-arisc` | HDMI, EDID, hot plug and the display MIPS's frames the same under both (`doku/218` §3); the infrared pin applied again after the firmware's start (`0328`, `doku/219` §2) |
| Standby | **not offered in the release** | an image built with `--standby` runs crust and suspends to RAM: 2.0 W on the HY300PRO-G-EU, 2.4 W on the HY310, picture back about 5 s after the wake | measured 07.-20.10.2026 (`doku/165` - `doku/174`, `doku/184`, `doku/212` §1); the power supply hums in standby and in crust's off (`doku/218`), so the owner decided against it on 22.10.2026 |
| eMMC layout v4 | works | six partitions, the secure storage untouched by design; files copied in through a mount | `docs/subsystems/emmc-layout.md`; a reinstall keeps the vendor files on the device (16.09.2026) |
| Debian 13 rootfs | works | `rootfs/`; the release is a `media,desktop` profile image with a 2 GiB root file system that grows at the first start | built by `build-all`, acceptance tests in the build log; `v0.97-beta` stamps in `doku/219` §5 |
| Projector image (LVDS/DLP) | works | MIPS firmware and the `sun50i-h713-afbd` KMS driver | continuous since 08.09.2026; 1080p60 from the three-slot capture ring with 59.7 of 60 frames shown since `0255` (`doku/200`) |
| HDMI input | works | `sun50i-h713-hdmirx`; the display firmware's own mode table is the list of what locks | 1080p60/50/24, 720p50, 576p50, 1366x768, 1024x768 and 4K30 (`doku/134`); hot plug after boot, a boot with the source plugged in; HDCP 1.4 and 2.2 (`doku/180`, `doku/152`) |
| Picture path userspace | works | `h713-tv` service and its `ctl` channel: presets, gamma level, colour temperature, white balance, aspect, zoom | `doku/212` §2, `doku/213` §1, the white balance measured at the registers 18.10.2026 |
| Launcher, settings page, overlays | works | `h713-keys`, `h713-osd`, `h713-settings`, `libh713osd`, `libh713geom` | HY310 15./16.10.2026: ten switches HDMI to Kodi and back, 35 of 35 standbys from every way in, every settings row set and set back (`doku/212` §1, §2); HY300PRO-G-EU 20.-22.10.2026 (`doku/217`, acceptance in `doku/219` §5) |
| Kodi, desktop, browser | works | profiles `media` and `desktop`: Kodi under cage, labwc with foot or Firefox, as Wayland clients of `h713-warp`, as system users | HY310 15./16.10.2026 (`doku/212` §1, §3); HY300PRO-G-EU 22.10.2026, three rounds of switches with the owner's eyes (TODO 1.0 (2)) |
| Hardware video decode, IOMMU | works | cstenger's cedrus series behind `CONFIG_SUN50I_IOMMU`, the VA-API driver; the VE at 600 MHz | bit-exact against ffmpeg over 33 clips, one hour of 4K HEVC in Kodi, 264 of 264 runs of a 127-minute loop (`doku/211` §3, §6, §8; `doku/212` §5). AV1: decoded bit-exact, switched off since `0310` |
| Keystone, by hand and automatic | works | `h713-warp` on the Mali, `h713-keystone` from the SC7A20 | corners, zoom, four projection modes, the soft edge judged on the wall (`doku/134` A2, `doku/157`); no frame of latency since `0255` (`doku/200`) |
| Web page | works | `h713-panel`, port 8080, one password | `doku/134` A1; the HY300PRO-G-EU without camera and focus hides those controls |
| HDMI audio and the box's own sounds | works | codec-I2S, the MSP DSP driver, `hw:hy310hdmi,0` as ALSA's default | lip-sync by ear 08.09.; device sounds within 0.07 dB of HDMI (`doku/134` D1 - D3); nothing in the image plays a sound of its own |
| ARM to MIPS IPC | works | `cpu_comm`, the in-kernel API, the software spinlocks as the vendor runs them (`0259`, `0261`) | 22 and 50 clean warm starts (`doku/203`, `doku/206`) |
| Wi-Fi AIC8800D80 | works | out-of-tree modules and `h713-wifi` | access point and client (`doku/60`); the client check after every install (`doku/219` §5) |
| Bluetooth and the stock remote | works | `h713-bluetooth`, `h713-bt-reset`, `h713-remote-pair`, kernel `0169`, `0321` | 16 keys and the mouse, 97 of 97 pings beside it (`doku/134`); a stale bond paired afresh by Left+Right (`doku/214`, TODO 2.92 done 20.10.2026) |
| Infrared and the keys | works | kernel `0252` - `0254`, `0328`, `0329`; `h713-keys` | all keys of both stock remotes decoded and acting, HY300PRO-G-EU 22.10. and HY310 23.10.2026 (`doku/219` §2) |
| Focus motor, autofocus | works | `hy310_focus_motor`, `h713-focus`, `h713-autofocus` | the range watcher (`doku/94`); autofocus sharp at a wall twice at the same position (`doku/134` A4); the motor can stay outside its range at the lower stop (`doku/213` §6, known issue) |
| Internal camera | works | `uvcvideo`, `h713-cam` | grab of the lit wall 12.09.2026 |
| Fan, tacho, stall protection | works | `hy310-board-mgr` | 4860 RPM; the stall power-off triggered on the device 12.09.2026 |
| RTC | works | `0320`: the 32 kHz from the 24 MHz crystal | rate 1.000 against system time, HY310 16.10. and HY300PRO-G-EU 20.10.2026 (`doku/213` §5) |
| Mali-G31 GPU | works | panfrost, our own mesa (panfrost only), the GPU's operating points at their true clocks since `0268` - `0270` | 150/200/300/600 MHz measured against the cycle counters 13.10.2026; ten minutes of load (`doku/211`) |
| CPU clock under the warp | works | `h713-cpufreq`: schedutil's rate limit, no real-time boost | 480 MHz under the warp with 59.7 fps (`doku/201`) |
| HDCP 1.4 | works, device-local | the boot loader reads the 288-byte key set out of the device's secure storage; our own EL3 service | the pair wipe, Desired, push, Enabled in one boot (`doku/180`) |
| HDCP 2.2 | works, device-local | key read from the device at boot, never shipped; differs per device | a Fire TV stick negotiated a 2.2 session (`doku/152` §2.2) |
| Crypto engine | present, unused | measurement module loads, crypto disabled | `doku/114` |

## Open device tests

Written down because they are *not* done, not because they are expected to fail:

- a release image on the HY310 and the HY300PRO-G-EU after the last build from `main` (TODO 1.0 (5b)): cold start from the
  gate and one infrared key on each board, the acceptance script
- the HY300 (Pro) of issue #1 with the infrared retrofit `test11`: the owner's report (TODO 2.134)
- the keystone warp over an hour with a live source; the throw ratio with a tape measure; the ceiling modes with the projector
  upside down
- a 2.2 source after a restart of the display firmware; the interlaced modes
- whether the CPU load is the cause of the visible flicker, with an oscilloscope at the lamp's supply (TODO 9.3n)
- the power draw in the gate with the infrared decoder, the Windows path of the installer

## Where the numbers come from

Every row above has a longer story in `doku/`, the dated German journal; `doku/INDEX.md` §1 lists the entries this page
rests on. What changed from release to release is in [RELEASES.md](RELEASES.md).
