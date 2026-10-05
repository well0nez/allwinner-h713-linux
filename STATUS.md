# Status

Snapshot of **2026-10-04**. "Works" means *verified on the projector*, with the date and the log named -
not "compiles". Where a row says **unverified**, nobody has proven it on this hardware, and you should
treat it as a claim, not a fact.

The image on the test device is `v0.96-beta`, installed over FEL the way a stranger would, from the release
files: the 206-patch series with U-Boot `6fb736c`, mesa for the GPU, Bluetooth and the stock remote.
Installed from the release files on 2026-10-04 and run through the device test of `doku/142`: ten cold starts,
Bluetooth after two warm reboots, the remote, the mixed device sound, 1080p120 under the warp.
The last release is `v0.96-beta`; the last test image for the HY300 Pro of issue #1 is `hy300-pro-test9`
(25.09.). What the numbers mean: [RELEASES.md](RELEASES.md).

## Summary

- **Works:** standalone boot from eMMC with the device's own boot logo two seconds after the power key,
  projector image, HDMI input with picture controls and hot plug, HDMI audio, Wi-Fi as an access point
  and as a station, focus motor, internal camera (without a bootloader crutch since 15.09.), fan tacho and
  thermals (reporting only), power key, FEL recovery, installer including restore-to-stock. The fan-stall
  poweroff is armed since 12.09. Since `v0.95-beta` (23.09.) also the **Mali GPU** and the **keystone** on it - by
  hand and following the projector's own tilt - the settings page and the autofocus. Since `v0.96-beta` also
  **Bluetooth** with the stock remote, the box's own sounds mixed into HDMI, the projection modes, EDID block 1
  with 1080p100/120, and the optional hardware of other boards (the rows below say where and when).
- **Missing:** AV1 decode, the IR receiver, a standby below 4 W, any desktop -
  and nothing acts on the remote's keys yet except Power.
- **Not re-tested by us:** hardware video decode and the IOMMU - these come from cstenger's tree. The Mali GPU
  did too; since 22.09. it is measured here and since `v0.95-beta` it is in the image, under the keystone.

## Boards

One board is tested; the others are described. Since 15.09. the two HY200 boards have installer
profiles too, read out of the two 2025 "HY300 Pro+" vendor images - a profile describes the stock
firmware and tests nothing, so it changes no row's state. The rule behind that, from `doku/121` §5 and enforced
by `release/build-all.sh --board`: **no image for a board nobody has tested.** A row below
*verified* is a description, not a claim that anything runs on it.

| Board | State | Who ran it, and when | What exists for it |
|---|---|---|---|
| **HY310** (silkscreen `HY260_QZ713_V3.1`) | **verified** | the owner (well0nez), on his HY310, `v0.9-beta`, 22.09.2026; `v0.95-beta` installed from its release files on 23.09.2026; every part of `v0.96-beta` in the device tests of 02. to 04.10.2026 (`doku/134`) | everything else on this page. The only board a *release* image is built for; `hy300-pro` gets TEST images only |
| **HY200 QZ713_V2** | profile-only, not testable yet | nobody | cstenger's LPDDR3 defconfig and device tree, marked untested on hardware in his tree too, and neither in our layout yet (`boards/hy200-qz713-v2`), plus the installer profile `hy200_qz713_v2` - its stock firmware is the 2025-07-10 "HY300 Pro+" LPDDR3 image (720 MHz, `display.bin` `4628cbaf...`, HDCP wait site `0x4b13d538`) |
| **HY300 T08** | profile-only | nobody | installer profile and DRAM fragment, both read out of its stock image (`doku/121` §2). No device tree of ours |
| **HY350** | profile-only | nobody | as above. It ships the same `display.bin` as the T08 and a different panel - which is why the panel comes from the declared project id, never from the firmware image |
| **HY300 Pro** | partial | its owner, [issue #1](https://github.com/well0nez/allwinner-h713-linux/issues/1): probe and dump 13.09., then the TEST images. `hy300-pro-test2` (16.09.) brought U-Boot up and hung in the display bring-up; `hy300-pro-test3` booted the kernel, with Wi-Fi as access point and station and HDCP 2.2 reported working, but no boot logo, no HDMI input and green stripes; test4 brought the ARISC fix and the first panel A/B. `hy300-pro-test9` (25.09.) is the last: its boots stopped at random because the lamp's PWM words reached the display firmware as six parameters (fixed by kernel `0168`), and its U-Boot ran project 0x30 instead of 0x34. `test10` follows after `v0.96-beta` ([boards/hy300-pro](boards/hy300-pro/README.md)). No green run yet | installer profile with gaps - layout from his log, DRAM clock 636 MHz, HDCP wait site unknown |
| **HY200 QZ713DF A1** (HY300PRO-G-EU, "HY300 Pro+" 2025 DDR3, cstenger's bench) | profile-only, both variants | `projector05061226`: the maintainer's own HY300PRO-G-EU has run TEST images (doku/136, doku/137), no green run reported yet; `projector09220931`: nobody. cstenger ran his own tree on his own bench board - kernel 6.18.38 boot-good (`mainline/config/versions.env`); that is his run, not ours | `boards/hy200-qz713df-a1` with two variants, installer profile `hy200_qz713df_a1` (the HY300PRO-G-EU's eMMC dump of 02.10.2026, the 2025-09-22 image), device tree `sun50i-h713-hy200-qz713df-a1` (0181), U-Boot base `hy200_qz713df_a1_defconfig` with the variant's DRAM clock; a TEST image per variant is one build away |
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
| HDMI input | works | `sun50i-h713-hdmirx`, node found by name (it was `/dev/video3` on 12.09., not `video1` - the camera enumerated first) | 1080p60/50/24, 720p50, 576p50, 1366x768, 1024x768 and 4K30, colour-correct from the firmware's own record, 22.09. (six modes at 60 Hz since 08.09.); hot plug after boot, a boot with the source plugged in and unplug/replug verified 16.09. after the first-publication source switch was removed (kernel 0136a/0136c); a source outside the firmware's mode table is refused since 22.09. (0136r-0136w), and named at once since `0171` (02.10.: `1600x1200p60, 162.0 MHz not in the firmware's table`); 1080p120 locks with block 1 of the device's EDID published (`h713-tv ctl edid block1`, 02.10., a laptop, `doku/134` B1) |
| Picture path userspace | works | `h713-tv` service, `h713-tv ctl …` | 08.09.; presets, gamma, aspect, controls |
| Keystone, by hand and automatic | works, beta, since `v0.95-beta` | `h713-warp` (the warp on the GPU) and `h713-keystone` (the accelerometer), with `h713-tv` committing | 23.09.: the tearing measured and removed (a slot is drawn one vsync late), the warp draws NV12 on the video plane so the picture controls reach it, the projection area is `h713-warp ctl zoom`. 22.09.: a corner set by hand moves that corner of the picture on the wall, and the automatic answers a 25-degree nose-up tilt by pulling the top edge in. The caveats are in [docs/known-issues.md](docs/known-issues.md). 26.09.: the sensor's mounting offset measured at about 0 degrees (18.9 on the sensor, 18.9 on a phone laid on the housing), so the ideal pose is the reference since `v0.96-beta` (02.10.: `status` says `ideal`, a taken reference refines it). 02.10.: the projection modes rear, ceiling and rear-ceiling and the soft edge judged on the wall (the projector upright on the bench, not on a ceiling); 03.10.: the calibration picture readable at 1080p and 720p (`doku/134` A1, A2) |
| Settings page | works, beta, since `v0.95-beta` | `h713-panel`, port 8080, no authentication | 23.09.: the corners dragged, a preset and the zoom set from the page (Marco), [docs/guides/settings-page.md](docs/guides/settings-page.md); 02.10.: the level reference and "Auto now" from the page (`doku/134` A1). Controls of absent hardware are hidden since `v0.96-beta` |
| HDMI audio | works | codec-I2S + MSP DSP driver, one volume control | 08.09. 22:05, lip-sync judged by ear; 03.10.: the box's own sounds through `hw:hy310hdmi,0` mixed into HDMI by the DSP (`0176` - `0178`), HDMI and device sounds within 0.07 dB of each other over 20 rounds, the volume within 0.8 dB of the stock curve (`doku/134` D1 - D3) |
| ARM ↔ MIPS IPC | works | `cpu_comm` in-kernel API | callback slot leak fixed; [docs/subsystems/cpu-comm.md](docs/subsystems/cpu-comm.md) |
| ARISC (PMU, HPD, EDID) | works | `sun50i-h713-arisc` | 17.65 s to hot-plug ready |
| Wi-Fi AIC8800D80 | works | out-of-tree modules + `h713-wifi` | 12.09.: access point (−50 dBm, 5.7 MB/s, DHCP, SSH) and station against a real network (DHCP address, internet through `wlan0`) |
| Focus motor | works | `hy310_focus_motor` + `h713-focus` | range watcher measured 12.09. (lower edge) and 23.09. (upper edge, the pad's pull-up, homing walks 110 msteps back), `analyse/boot/motor-bereichswaechter-20260912.txt`, working journal `keystone-20260922` |
| Autofocus | works, beta, since `v0.95-beta` | `h713-autofocus` + `h713-afmetric` | 23.09.: the search turns round at an edge and found a peak on the bench; 02.10. with the `v0.96-beta` tool (waits for its pattern, reversal fix): two runs `stopped: peak`, then a run against the wall ended sharp at the same motor position as the run before (`doku/134` A4). Open: the metric's span was only +11 % that day (exposure) |
| Internal camera | works | `uvcvideo` + `h713-cam`; the USB PHYs are powered by the kernel since 15.09. (SIDDQ, patch 0005a), no `usb start` in the boot loader | 12.09.: grab of the lit wall, mean brightness Y = 88.7, 3.2 s (`analyse/beamer-cam/p6-wand-20260912.png`) |
| Fan, tacho, stall protection | works | `hy310-board-mgr` | 4860 RPM measured 11.09.; **the fan-stall poweroff is armed and was triggered on the device** 12.09.: rail cut, device shut itself down, next boot mounted the filesystem clean (`analyse/boot/p6-notaus-luefter-20260912.txt`). No NTC on this unit, so the tacho is the protection |
| Power / standby | partial | standby is 4 W; deep sleep is designed, built for a test and parked | plan `doku/104`; 03.10.: a suspend reached the DRAM entry and the CPU reset, the wake-up never came (`doku/139`), so it is not in the image |
| Crypto engine | present, unused | measurement module loads, crypto disabled | `doku/114` |
| Mali-G31 GPU (Panfrost) | works, in `v0.95-beta` | `panfrost.ko` plus our own mesa under `/usr/local` (panfrost driver only, 15 MiB), operating points from kernel `0024e` | 22.09.: `h713-gpu-probe render 3000` - 0 CRC mismatches, 236 fps, GPU zone 58 C, runtime-PM suspended afterwards; ten minutes of load with devfreq - 16,089 frames at 26.8 fps, 0 mismatches, 58.4 C, `dmesg` clean (working journal `keystone-20260922`) |
| Video decode, IOMMU | unverified here | cstenger's patches, in our series | verified in his tree, not in this image |
| Bluetooth and the stock remote | works, since `v0.96-beta` | `h713-bluetooth` (hciattach + bluez on UART1), `h713-bt-reset`, `h713-remote-pair`, kernel `0169` | 03.10.: 16 keys and the mouse as input events, 97 of 97 pings beside it, cold start and reconnect; three warm reboots in a row with `hci0` UP at 10.1 - 10.7 s ([docs/subsystems/wifi.md](docs/subsystems/wifi.md#bluetooth)). Nothing acts on the keys yet except Power (shuts down). The IR receiver is parked |
| HDCP 1.4 | works, device-local, since 05.10. | the boot loader reads the 288-byte key set out of *your* device's secure storage; our own EL3 service lets the crypto engine put it into the receiver's sink. No vendor code in the image | the open question of 03./04.10. is answered: the engine refuses key-select 3 towards readable memory **by design** (`ESR 0x11`) and accepts it only with the sink as destination **and** the DMA source inside the protected window - which is why it looked refused, and why the eFuse flag was never what it went by. Proven at the picture with a cleared sink as the control: `Desired` -> push -> `Enabled`, three times ([`docs/subsystems/hdcp.md`](docs/subsystems/hdcp.md)) |
| HDCP 2.2 | works, device-local; session unproven | key read from *your* device at boot, never shipped. Unlike the 1.4 set this one **differs per device** (measured on two boards), so a foreign secure-storage region must never be restored onto a device | `h713-hdcp-key.service`; 02.10.: `h713-tv ctl hdcp` shows the key handed over and advertised; no 2.2 source has been on the input |

## Changes since v0.95-beta (in v0.96-beta)

Device tests on the HY310 from 02. to 04.10.2026, each named in `doku/134`; the list of what came in and what
stayed out is the `v0.96-beta` section of [RELEASES.md](RELEASES.md). In short: Bluetooth and the stock remote
(`0169`, `h713-bluetooth`, `h713-remote-pair`, `h713-bt-reset`); the EDID's second half and the firmware's
mode table as the mode list (`0170` - `0173`); the HDCP state in `h713-tv ctl hdcp` (`0174`, `0175`, `0179`);
the device sounds mixed into HDMI and the stock volume curve (`0176` - `0178`); the ideal keystone reference,
the projection modes, the soft edge and the calibration picture; the autofocus's wait and reversal; optional
hardware per board (`h713-features`, exit 7); the HY200 QZ713DF A1 as one board with two firmware variants
(`0167`, `0168`, `0181`, U-Boot `2de0cc8` and `6fb736c`); the HY300 Pro's own focus tables (`0182`); the
drivers' log lines in English (`0180`); `restore-stock` for both known eMMC sizes; reproducible builds;
`panic=10` in the HY310's environment. The series stands at **206 patches**.

## Changes since v0.9-beta (in v0.95-beta)

In `v0.95-beta` (23.09.2026). A night of device slots on the HY310 on 22.09.2026 stands behind this list -
from "no GPU has ever run in this image" to a picture that follows the projector's own tilt. Every reading quoted
here is in working journal `keystone-20260922`.

- **The keystone exists - by hand and automatically.** [`h713-warp`](docs/tools/h713-warp.md) bends the HDMI
  picture into a quadrilateral on the GPU: the vendor's own projective homography, eight corner insets in
  per-mille, ported from `system_a_libkeystone.so` and tested against it. `h713-tv` stays the only DRM master and
  commits the warped frame as NV12 on the **video** plane with the daemon's fence and the ring off (23.09.; until then RGB on the primary plane, which the firmware's picture controls never reached). On the wall, `ctl keystone set tl x
  150` moved the **top left corner of the projected picture** inward, so the corner names are the wall's and not
  the vendor's contradictory slot order. [`h713-keystone`](docs/tools/h713-keystone.md) reads the SC7A20
  accelerometer, turns the tilt into the vendor's two angles, runs the vendor's corner geometry and pushes the
  eight values in: a 25-degree nose-up tilt pulled the top edge in (`tl 107,74 tr 126,24 bl 13,151 br 0,216`), and
  a lifted left side left the picture level once the roll sign was `-x`.
- **The identity costs nothing.** With all eight values at 0 - what a fresh image comes up in - the daemon never
  opens the render node, and the picture path is v0.9-beta's, bit for bit. The warp is entered by a value, left by
  `ctl keystone reset` or `ctl off`, and the CMA it took came back within 3 MB.
- **The Mali-G31 renders in this image**, for the first time: `h713-gpu-probe info` reports Mali-G31 (Panfrost)
  and OpenGL ES 3.1 Mesa 25.0.7 with all four extensions the warp needs, and `render 3000` drew 3,000 textured
  1080p frames with **0 CRC mismatches** at 236 fps, GPU zone 58 C, back to runtime-suspended afterwards.
- **The GPU has operating points and a cooling map** (kernel `0024e`). It used to sit at the PLL's boot rate of
  864 MHz, fixed - 23 per cent above the stock table's ceiling - because our device tree had no OPP table and
  Panfrost's devfreq left with `-ENODEV`. Now: 288, 432, 600 and 696 MHz with `simple_ondemand`, a passive trip at
  85 C and a critical one at 105 C with the GPU as its own cooling device. `CONFIG_DRM_LIMA` (Utgard only, binds
  nothing here) and `CONFIG_SUN50I_IOMMU` (dead with the node disabled; Panfrost uses its own MMU) are off. Ten
  minutes of load: 16,089 frames, 26.8 fps, 0 mismatches, 201 frequency transitions, 58.4 C at most, back at
  288 MHz and suspended, `dmesg` clean.
- **The capture slots can be handed to the GPU** (kernel `0136y`): `VIDIOC_EXPBUF` on the HDMI receiver wraps one
  slot plane as a `dma-buf` - a one-entry scatterlist over `dma_map_resource`, because the ring is a no-map
  reservation with no `struct page` behind it. Three buffers with both their planes export and map on the device,
  and with a laptop's 1080p60 on the input the exported luma plane reads mean 124.9 over 16..235: a real picture,
  read by the GPU without a copy. It is not a fence - the firmware reuses a slot every third frame, and the
  header says so in one sentence.
- **mesa is in the image** - 25.0.7, cross-built with clang, the panfrost driver, EGL, GLES2 and GBM and nothing
  else: **15 MiB** under `/usr/local` against the 187 MiB Debian's packages cost, where even `libgbm1` pulls
  `mesa-libgallium` and `libllvm19`. `build-rootfs.sh --mesa` lays the tarball in, `--mesa none` leaves the GPU
  userspace out, and a rootfs built with it is 266 MiB.
- **The accelerometer is on the bus again** (kernel `0162`): `twi1` with one child, the SC7A20 at 0x18
  (`silan,sc7a20`), in place of the stock tree's four candidates, and `st_accel` as a module. It probes as
  `iio:device2` named `sc7a20`. There is deliberately **no `mount-matrix`**: three poses on the bench say pitch is
  raw y, roll is raw x and z is vertical - the identity, not the swap the vendor's own driver does - so the
  transform lives in `keystone.conf` as a configuration key rather than in the device tree as a claim about the
  hardware.
- **`h713-tv` has a third display mode.** Beside plane-on and console there is now *warped*: `ctl status` says
  `picture warped (h713-warp draws on the video plane)`, `ctl warp status` gives the commit counters, and
  `ctl zoom` is refused while the warp is on (the video plane is off, and the zoom is the firmware's). One bug
  came out of the device run and is fixed: the audio automaton took "plane on" for "there is a picture", so a
  source event during a warp - a player switching 48 to 44.1 kHz - re-evaluated the audio as *no picture* and
  muted it with a pop. All five call sites take "plane on **or** warped" now.
- **Not done then, and named as such** (the projection modes and the edge blend came with `v0.96-beta`):
  the projection-mode mirror RPC (ceiling, rear), the vendor's edge-blend pass,
  and the write-back self-test as a second opinion on the identity warp (the ordinary check is `h713-warp ctl check N`). The
  hour-long soak has no result yet; the long run that exists is the one the audio bug came out of. The throw
  ratio is still the optics' own 0.8176 out of `camprjspe.ini` and not a tape measure. None of this has been
  near the HY300 Pro.
- With `0024e`, `0136y`, `0162`, `0163`, `0164` and `0165` the series stands at **188 patches**
  ([docs/kernel-patches.md](docs/kernel-patches.md)).

## Changes since v0.8-beta (in v0.9-beta)

In `v0.9-beta` (22.09.2026). Three device runs on the HY310 on 22.09.2026 stand behind this list -
`v0.8-dev20` (169 patches), `v0.8-dev21` (177) and `v0.8-dev22` (182); what was read out on the device is in
working journal `dev20-20260922`, `dev21-20260922` and `dev22-20260922`.

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
- **`h713-tv ctl zoom` has two verbs** - `in F` and `off`. `out` was retired on 23.09.2026: the DE scaler only
  enlarges, so a smaller destination window cropped instead of shrinking (measured at 0x05180008); the projection
  area is `h713-warp ctl zoom`, the GPU, as the vendor does it. The display firmware does the enlarging,
  two plane properties carry its source and destination window, and the plane places the result; nothing on
  the ARM side scales. Both directions were **bench-tested with a test pattern** (`v0.8-dev22`): `in 2` puts
  the centre quarter on the whole panel, `out 80` the whole picture at 80 per cent, centred, with a border.
  The model and every measurement behind it: [docs/subsystems/display.md](docs/subsystems/display.md).
- **`h713-autofocus` is new** - the vendor's own search rebuilt: a chessboard on the panel, frames from the
  internal camera, the vendor's cubed-gradient metric (also as a C helper, `h713-afmetric`). On the device
  the search runs, moves the motor and visibly sharpens the pattern, 4.3 s from 80 msteps out of focus.
  **Convergence against a wall is not proven:** the search turns round at an edge since 23.09. and reached a
  peak on the bench (positions -2 to +31, 440 msteps from the lower edge); a surface too close has its sharp
  point beyond the watched range. A run against a wall at
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

Device runs on the HY310 on 16.09.2026 (`v0.8-dev13` to `v0.8-dev15`; German account in working journal `P1`,
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
  Its picture data are the device's own now: `h713-pq` takes the presets out of `tvpq.db` where a
  firmware ships no `pq_picturemode.ini` (his does not), `h713-tv` loads the panel's measured gamma
  curve out of that board's `ProjectID_0x0034.TSE` instead of the synthetic 2.2 one, and the
  installer writes `/etc/h713/board` so the device knows which of the 13 TSE files is its own.
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
- the keystone warp over an hour with a live source, with `h713-warp ctl check` running - the longest clean
  measurement so far is 900 frames with the settings page polling; likewise a source that changes its resolution while the warp draws
- the throw ratio with a tape measure, against the 0.8176 the optics data implies, which is what the automatic
  keystone computes with today
- the auto keystone standing still for ten minutes at rest, and both of them on any board but the HY310
- an HDCP 2.2 session with a protected 2.2 source. For HDCP 1.4 the question is closed: the DMA source has to lie inside the protected window ([`docs/subsystems/hdcp.md`](docs/subsystems/hdcp.md))
- the interlaced modes VIC 6, 7 and 21 in the driver's mode list (the status line names them; 04.10.); two
  autofocus runs ended sharp at two different positions (51 and 93, 04.10.)
- the ceiling modes with the projector really upside down, and the calibration cards in the mirrored modes
- the fan backstop of the wave (a stalled fan with a live tacho), parked: the fan connector was out of reach
- Bluetooth after a cold start on the HY300PRO-G-EU comes up on the unit's second start, about 17 s later (04.10.)

## Reading the German journal

Every row above has a longer story in `doku/`. Start at `doku/00-STATUS.md`; it is the same map in German,
with the measurements attached. Nothing in the English documentation claims anything that is not written
down there with a date.
