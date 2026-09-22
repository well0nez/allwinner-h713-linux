# Status

Snapshot of **2026-09-22**. "Works" means *verified on the projector*, with the date and the log named -
not "compiles". Where a row says **unverified**, nobody has proven it on this hardware, and you should
treat it as a claim, not a fact.

The image on the test device is `v0.9-beta`: the 182-patch series with U-Boot `4cecddd`, installed from the release files.
The last release is still `v0.8-beta`. What the numbers mean: [RELEASES.md](RELEASES.md).

## Summary

- **Works:** standalone boot from eMMC with the device's own boot logo two seconds after the power key,
  projector image, HDMI input with picture controls and hot plug, HDMI audio, Wi-Fi as an access point
  and as a station, focus motor, internal camera (without a bootloader crutch since 15.09.), fan tacho and
  thermals (reporting only), power key, FEL recovery, installer including restore-to-stock. The fan-stall
  poweroff is armed since 12.09.
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
| **HY310** (silkscreen `HY260_QZ713_V3.1`) | **verified** | well0nez, on his HY310, `v0.9-beta`, 22.09.2026; the development builds `v0.8-dev20` to `v0.8-dev22` on 22.09.2026 | everything else on this page. The only board a *release* image is built for; `hy300-pro` gets TEST images only |
| **HY200 QZ713DF_A1** | profile-only | nobody has run a build of *ours* on it. cstenger ran his own tree on his own bench board - kernel 6.18.38 boot-good (`mainline/config/versions.env`); that is his run, not ours | kernel and U-Boot defconfigs, device tree, and since 15.09. the installer profile `hy200_qz713df_a1` - its stock firmware is the 2025-09-22 "HY300 Pro+" DDR3 image (624 MHz, `display.bin` `4380f1b3…`) |
| **HY200 QZ713_V2** | profile-only | nobody | cstenger's LPDDR3 defconfig and device tree, marked untested on hardware in his tree too, plus the installer profile `hy200_qz713_v2` - its stock firmware is the 2025-07-10 "HY300 Pro+" LPDDR3 image (720 MHz, `display.bin` `4628cbaf…`, HDCP wait site `0x4b13d538`) |
| **HY300 T08** | profile-only | nobody | installer profile and DRAM fragment, both read out of its stock image (`doku/121` §2). No device tree of ours |
| **HY350** | profile-only | nobody | as above. It ships the same `display.bin` as the T08 and a different panel - which is why the panel comes from the declared project id, never from the firmware image |
| **HY300 Pro** | partial | its owner, [issue #1](https://github.com/well0nez/allwinner-h713-linux/issues/1): probe and dump 13.09., then the TEST images. `hy300-pro-test2` (16.09.) brought U-Boot up and hung in the display bring-up; `hy300-pro-test3` booted the kernel, with Wi-Fi as access point and station and HDCP 2.2 reported working, but no boot logo, no HDMI input and green stripes. `hy300-pro-test4` (kernel `0091a` for the ARISC, plus a first panel A/B) is built for him. No green run yet | installer profile with gaps - layout from his log, DRAM clock 636 MHz, HDCP wait site unknown |
| **L018** | profile-only | nobody | the installer profile `l018` alone, read out of one extractor run over a real device; no board directory, no DRAM data, no firmware image here |

`boards/<id>/board.env` carries these states machine-readably, and `bash boards/check.sh` holds each
one against the installer profile in `installer/h713/profiles/`. What a board below *verified* gets
instead of an image is the read-only probe, which writes nothing and runs from FEL on any H713:
[docs/tools/h713-probe.md](docs/tools/h713-probe.md). A row becomes *verified* when that board's
owner reports a green run of a build of ours, with a date - see [BUILDING.md](BUILDING.md), *Boards*.

## Subsystems

| Subsystem | State | Where it lives | Evidence |
|---|---|---|---|
| Boot chain | works | SPL → BL31 → U-Boot → FIT, all from source; the SPL reads the FIT with DMA, the eMMC runs at HS200 with DMA in U-Boot | 20/20 cold starts (`analyse/boot/r5-20-kaltstarts-20260910.txt`); 16.09.: power key to the boot logo 2.0 s, to the kernel 3.5 s (1 s of it is the autoboot countdown), release BL31 on the device since 15.09. |
| Power key gate | works | U-Boot `CONFIG_H713_POWER_GATE`, env `h713_gate` | 09.09.; standby 4 W, red LED, key starts |
| eMMC layout v4 | works | v3's six partitions, secure storage untouched by design; since 16.09. the files are copied in through a mount instead of into placeholders | 10.09. / 16.09., [docs/subsystems/emmc-layout.md](docs/subsystems/emmc-layout.md) |
| Debian 13 rootfs | works | `rootfs/`, 242 MiB, zram, ssh key-only | built by `build-all`, acceptance tests in the build log |
| Projector image (LVDS/DLP) | works | MIPS firmware + `sun50i-h713-afbd` KMS driver | continuous since 08.09. |
| HDMI input | works | `sun50i-h713-hdmirx`, node found by name (it was `/dev/video3` on 12.09., not `video1` - the camera enumerated first) | 1080p60/50/24, 720p50, 576p50, 1366x768, 1024x768 and 4K30, colour-correct from the firmware's own record, 22.09. (six modes at 60 Hz since 08.09.); hot plug after boot, a boot with the source plugged in and unplug/replug verified 16.09. after the first-publication source switch was removed (kernel 0136a/0136c); a source outside the firmware's mode table is refused by name since 22.09. (0136r-0136w) |
| Picture path userspace | works | `h713-tv` service, `h713-tv ctl …` | 08.09.; presets, gamma, aspect, controls |
| HDMI audio | works | codec-I2S + MSP DSP driver, one volume control | 08.09. 22:05, lip-sync judged by ear |
| ARM ↔ MIPS IPC | works | `cpu_comm` in-kernel API | callback slot leak fixed; [docs/subsystems/cpu-comm.md](docs/subsystems/cpu-comm.md) |
| ARISC (PMU, HPD, EDID) | works | `sun50i-h713-arisc` | 17.65 s to hot-plug ready |
| Wi-Fi AIC8800D80 | works | out-of-tree modules + `h713-wifi` | 12.09.: access point (−50 dBm, 5.7 MB/s, DHCP, SSH) and station against a real network (DHCP address, internet through `wlan0`) |
| Focus motor | works | `hy310_focus_motor` + `h713-focus` | range watcher measured 12.09., `analyse/boot/motor-bereichswaechter-20260912.txt` |
| Internal camera | works | `uvcvideo` + `h713-cam`; the USB PHYs are powered by the kernel since 15.09. (SIDDQ, patch 0005a), no `usb start` in the boot loader | 12.09.: grab of the lit wall, mean brightness Y = 88.7, 3.2 s (`analyse/beamer-cam/p6-wand-20260912.png`) |
| Fan, tacho, stall protection | works | `hy310-board-mgr` | 4860 RPM measured 11.09.; **the fan-stall poweroff is armed and was triggered on the device** 12.09.: rail cut, device shut itself down, next boot mounted the filesystem clean (`analyse/boot/p6-notaus-luefter-20260912.txt`). No NTC on this unit, so the tacho is the protection |
| Power / standby | partial | standby is 4 W; deep sleep is designed, not built | plan `doku/104` |
| Crypto engine | present, unused | measurement module loads, crypto disabled | `doku/114` |
| Video decode, IOMMU, GPU | unverified here | cstenger's patches, in our series | verified in his tree, not in this image |
| Bluetooth | missing | driver builds, firmware split not done | `rootfs/packages.txt` explains the choice |
| HDCP 1.4 | missing | path understood, one test costs a power cycle | `doku/112` |
| HDCP 2.2 | works, device-local | key read from *your* device at boot, never shipped | `h713-hdcp-key.service` |

## Changes since v0.8-beta

In the source, not in a release yet. Three device runs on the HY310 on 22.09.2026 stand behind this list -
`v0.8-dev20` (169 patches), `v0.8-dev21` (177) and `v0.8-dev22` (182); what was read out on the device is in
`umbau/test-20260915/dev20-20260922.md`, `dev21-20260922.md` and `dev22-20260922.md`.

- **The HDMI input locks on the firmware's own mode table.** The driver reads the display firmware's 152 mode
  records (129 enabled) out of `database.TSE` and uses them as the preset list instead of a built-in one. A
  source whose raster is in no record is now refused *by name*: `h713-tv` says `1600x900p75, 108.0 MHz not in
  the firmware's table` and shows the console, with exactly one journal line. Measured on `v0.8-dev22`:
  1080p60/50/24, 720p50, 576p50, 1366x768, 1024x768 and 4K30 all lock, no spurious lines. The firmware needs
  more than six seconds to write a record for a raster it does not carry, so the first read after plugging
  such a source in still says "change in flight".
- **The colour space comes from the firmware's record** instead of from the resolution: BT.709 for HD,
  BT.601 for 576p and 480p, full or limited range as the source declared it. Read back on eleven modes
  (`v0.8-dev20`), no colour shift on the wall.
- **The ARISC's EDID version byte is a per-port block mask**, with an in-kernel API, a device-tree property
  `allwinner,edid-version-mask` and a debugfs read-back of what is actually published. **The default does not
  move:** the mask stays 0, port 0 keeps block 0, and the 256 bytes the PC reads back are byte for byte the
  capture of 21.09. A changed mask takes effect with the next EDID upload, not when it is set.
- **`h713-tv ctl zoom` has three verbs** - `in F`, `out P`, `off`. The display firmware does the scaling,
  two plane properties carry its source and destination window, and the plane places the result; nothing on
  the ARM side scales. Both directions were **bench-tested with a test pattern** (`v0.8-dev22`): `in 2` puts
  the centre quarter on the whole panel, `out 80` the whole picture at 80 per cent, centred, with a border.
  The model and every measurement behind it: [docs/subsystems/display.md](docs/subsystems/display.md).
- **`h713-autofocus` is new** - the vendor's own search rebuilt: a chessboard on the panel, frames from the
  internal camera, the vendor's cubed-gradient metric (also as a C helper, `h713-afmetric`). On the device
  the search runs, moves the motor and visibly sharpens the pattern, 4.3 s from 80 msteps out of focus.
  **Convergence is not proven:** every run so far ended at the motor's range watcher, because the test
  surface stands about 30 cm away and its sharp point lies beyond the watched range. A run against a wall at
  one to three metres is the outstanding test.
- **`h713-pq` can read the firmware's own gamma and curves** (`--source tse`) beside the existing guess out
  of the ini. It is **off by default**, and on the HY310 it makes no visible difference: the board's own
  "normal" curve has the endpoints 4092/4092/4092, like the synthetic 2.2 ramp. It was built for the HY300
  Pro's white balance, which is where it has to prove itself.
- **`h713-extract` also takes `panel_config.ini` and `camprjspe.ini`** out of your dump, and
  `--profile <board>` writes a panel row from the board's own ini - every value names the ini line it came
  from, and the five fields that exist only as registers say "unknown". That file is a description, not a
  measurement, and its header says so.
- **Board-neutral kernel work.** All of it leaves the HY310 as it was and lets a second board carry its own
  numbers: the fan rail is driven high from the request on and the first RPM is logged (`0159a`); the display
  handoff words are a device-tree property and a refusal names all six (`0133a`); the display firmware's
  error-log addresses come from the board (`0092a`, `0161b`); `cpu_comm` sends one doorbell per message, its
  register whitelist is the hwspinlock's, and it refuses to write into a full TX FIFO (`0014d` - `0014f`);
  two races against the ARISC are closed by waiting for the handler's *effect* rather than its
  acknowledgement (`0091e` for the version byte, `0091f` for every EDID fragment); and a v4l2-core fix makes
  `VIDIOC_QUERY_DV_TIMINGS` copy its result at all (`0136w`), which is what lets a refused source be named.
- **U-Boot walks `LogoRegData` by its class table** instead of a fixed layout, so a logo container with other
  classes is read correctly. The new walker was proved to give the same bytes as the old one on all 15 HY310
  and 13 HY300 Pro projects before it was swapped in. U-Boot on the device: `4cecddd`.
- **Three more of the vendor's picture settings** are V4L2 controls: `low_latency`, `backlight_level` and
  `dynamic_backlight`. The last two are **accepted by the firmware and do nothing on the HY310** - at 60 and
  at 10 the lamp does not change, which is what [docs/dead-ends.md](docs/dead-ends.md) already records about
  this board's backlight path. They are there for a board that wires it up.
- **Not tested on a device:** the blanking that the refused source's timing now carries - the device printed
  `p75`, the rate computed over the active size, and the source should say `p60` since; the `h713-afmetric`
  cross-build in `release/build-all.sh`; and all of the above on any board but the HY310.
- The series stands at **182 patches** in fifteen sections
  ([docs/kernel-patches.md](docs/kernel-patches.md)).

## Changes since v0.7-beta

Device runs on the HY310 on 16.09.2026 (`v0.8-dev13` to `v0.8-dev15`; German account in `umbau/reviews/P1.md`,
`P2.md`, `N1.md`, `N2.md`, `E4.md` and `doku/61`):

- **`v0.7-beta` is superseded**: its layout v3 image is refused by the installer on `main`; take v0.8-beta.
- **The patch mirror `uboot-h713/`** was regenerated at the fork head `da74b89` (82 commits, 82 patch files),
  so it again matches the fork it is generated from. The build still uses the submodule, not the mirror.
- **Layout v4 - no placeholders.** The image carries only target directories; `h713-install` mounts its working copy's
  two file systems and copies the device's files in with their real size, mode and owner, and reads them back from an
  installed device the same way (read-only mount). A v0.7-beta image and the current installer refuse each other.
- **Reinstall over our layout** without a dump and without `--vendor`; the small dump only with `--dump`.
- **Optional groups:** Wi-Fi firmware and picture-preset files a firmware lacks are said and left out (issue #1).
- **Device tools in English:** `h713-tv`, `h713-pq`, `h713-fel`, `h713-focus`, `h713-cam`; old `tv.conf` words stay accepted.
- **The last German switches and keys:** `h713-pq --daten/--kanal` are `--data`/`--channel` now, `h713-tv`'s
  `--daten/--eingang/--rechner` are `--data`/`--input`/`--calculator`, and the `tv.conf` keys `zustand`, `daten`
  and `rechner` are `state`, `data` and `calculator`. Every old spelling is still accepted without a warning, so
  an existing `tv.conf`, unit file or script keeps working; they go out after `v0.9`.
- **Msgbox lines** 46/109/108 in the device tree, watchdog on 53, `cpu_comm` requests only its own line; the two
  `IRQ index not found` lines are gone. Sixteen kernel patches refreshed; `ping`, `curl`, `wget`, `nc` in the rootfs.
  The series stands at 182 patches in fifteen sections ([docs/kernel-patches.md](docs/kernel-patches.md)).

## Changes since v0.6-beta (in v0.7-beta)

All of these have been through device runs on the HY310 on 15./16.09.2026 (German account in `doku/125`,
`doku/124` and `doku/61`):

- **Boot logo:** U-Boot shows the device's own `bootlogo.bmp` with the display firmware left running
  (`h713_disp init <id> logo`); the installer carries the file from the stock bootloader partition to
  `/boot/bootlogo.bmp`. No hash gate, no white flash.
- **Boot time:** no `usb start` and no USB scan in the product boot, autoboot countdown 1 s, no logo
  hashing, the eMMC clock corrected (the driver assumed the H6's PLL layout and ran the eMMC at 33 MHz),
  IDMAC DMA and HS200 in U-Boot (87 MiB/s), the SPL reads the FIT images with DMA straight to their
  addresses (SPL to BL31 1.6 s -> 0.14 s). Power key to the logo 2.0 s, to the kernel 3.5 s.
- **USB:** the kernel clears the SIDDQ bit of the HCI PHYs itself (patch 0005a, as the vendor kernel
  does); the camera no longer depends on the boot loader. `usb start` stays in the installer U-Boot only.
- **HDMI hot plug:** the capture driver no longer switches the firmware's source away and back after the
  first publication (0136a) and reports a release in progress as a change in flight (0136c). A source
  plugged in after boot keeps its picture; `ctl replug` is no longer needed.
- **Hygiene from the review of cstenger's branch:** `0040` retired, decd corrections in `0013a` (dormant on
  this board), aic8800 `0008`-`0010`, `CONFIG_MAGIC_SYSRQ` in the shipping kernel.
- **HY300 Pro:** profile with the device's identity features from the owner's probe run (issue #1).
- **Release script:** refuses an SPL that outgrew its 32 KiB slot.

## Verified display modes

1920×1080, 1280×720, 1024×768, 1440×900, 1280×1024 (pillarboxed), 1366×768 - each at 60 Hz, colour-correct
(BT.709), across arbitrarily many source switches, HDMI unplug/replug, and a cold start with no operator.

Since the firmware's own mode table became the lock list (*Changes since v0.8-beta*) the list of modes that
lock is longer - 1080p50/30/24, 720p50, 576p50, 480p and 4K30 among them - but those were read back on the
device, not each judged on the wall, so they are not in the line above.

## Open device tests

These are written down because they are *not* done, not because they are expected to fail:

- phone joins the access point, `ssh root@h713` over Wi-Fi
- `mode=sta` with a second DHCP client on `eth0` - two default routes, metric undecided (station mode itself
  is verified, 12.09., see *Wi-Fi AIC8800D80* above)
- environment carry-over (`h713_gate`, `h713_boot`) across a reinstall - needs a changed value before the next install
- 20 gate cycles with the power key (dropped 16.09.; the gate has run on every device test since 09.09.)

## Reading the German journal

Every row above has a longer story in `doku/`. Start at `doku/00-STATUS.md`; it is the same map in German,
with the measurements attached. Nothing in the English documentation claims anything that is not written
down there with a date.
