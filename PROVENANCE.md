# Provenance

Who made what, where it comes from, and what is deliberately absent.

## The kernel series

`mainline/` began as a **git subtree** import (13.09.2026, commit `657ce79`) of
[cstenger/allwinner-h713-mainline](https://github.com/cstenger/allwinner-h713-mainline) at commit `8860991`. What of his tree
is still in the working tree, and what is not, is told in "Left out on purpose" below; his kernel patches are the part
that stayed. His commits up to `8860991` are still in this repository's git history. On top of them,
`mainline/patches/kernel/series` carries 351 patches:

| Origin | Patches | Note |
|---|---|---|
| well0nez, via cstenger's `main` | 20 (`0001` - `0022`; `0011` withdrawn 22.09.2026, the file stays in `patches/kernel/`) | **the H713 driver series** - CCU, pinctrl, MMC, USB PHY, PWM, LRADC, board manager, cpu_comm, tvtop, decd. Written here, carried in his tree with attribution, six of them adapted from 6.16 to the pinned kernel. Byte-identical to his tree |
| cstenger, `main` | 24 (`0023` - `0048`; `0040` retired 15.09., see `zurueckgenommen/`) | the arm64 side built around that series: DTS, defconfig, boot chain, cpufreq. Byte-identical, verified by comparison |
| cstenger, branch `h713-display-video-path` | 17 (`0051` - `0086`) | byte-identical; scanout, DECD, IOMMU, MMC, video plane |
| well0nez | `0049`, `0091` - `0182` | ARISC, cpu_comm, HDMI input, audio, motor, board manager, Wi-Fi, one DTB name per board; `0162` - `0165` (22./23.09.2026) the accelerometer, the video plane's fast flip, the focus motor's range gate and homing; `0166` - `0182` (23.09. - 04.10.2026) the lamp's PWM words, the HY200 QZ713DF A1's tree, the stock remote's HID fixup, the EDID, HDCP-state and audio-bridge work, the drivers' log lines in English and the HY300 Pro's own focus tables |
| well0nez, follow-ups | `0005a`, `0013a`, `0014a` - `0014f`, `0024a` - `0024e`, `0078a`, `0091a` - `0091f`, `0093a`, `0096a`, `0092a`, `0133a` - `0133f`, `0135b`, `0136a` - `0136y`, `0101a`, `0154a`, `0159a`, `0161a`, `0161b`, `0166a` | small fixes placed directly after the original they touch, so the original stays byte-identical. `0096a` carries the TVFE/TVCAP driver, which is cstenger's EXPERIMENT patch 0087 from `h713-display-video-path` (measured on his board 02.09.2026), turned into a module and translated - his code, our wiring. `0013a` carries three decd corrections from cstenger's branch; `0005a` (USB PHY SIDDQ), `0136a` and `0136c` (HDMI hot plug) are ours, 15./16.09.; `0014b`, `0014c` and `0024d` are the msgbox's three interrupt lines and the decision that `cpu_comm` requests only its own bank's line, 16.09.; `0091a` resolves the ARISC firmware's SRAM addresses from the loaded image, 17.09.; `0096a` (the TVFE/TVCAP driver, built in), `0093a`, `0136d` (the vsync enable held while the receiver is bound) and `0091b`, `0136e` (a second hotplug pulse at the end of the bring-up) are the warm-receiver fix for issue #1, 19.09.; `0136f` (the receiver derives the capture ring's geometry from INCAP's rowbyte and active window, so the format is the ring and not the source on a panel smaller than the source) and `0136g` (the DE picture-scaler syscon it reads as an optional cross-check) let a 1920x1080 source play on the HY300 Pro's 1280x720 panel, issue #1, 20.09.; `0161a` disables the dtsi's pwm-backlight on the HY300 Pro, whose PB5 is the LED-boost and fan-rail enable as a plain GPIO (A14), 20.09.; `0159a` requests the board manager's fan-power line with GPIOF_OUT_INIT_HIGH instead of flags 0 and logs the first RPM reading after SYSTEM_RUNNING, so a foreign owner's journal proves his tacho (A14), and `0133a` lets a board declare the AFBD handoff state it hands over in `allwinner,handoff-state` instead of meeting three literals, with all six words in the refusal (A11); `0092a` and `0161b` do the same for the display firmware's two elog addresses, which the HY300 Pro's image keeps 0xC00 lower than the HY310's (A12), 21.09.; `0136h` - `0136k` (T2, 21.09.) take the display firmware's own mode table - the TFD module `THDMI_ModeDetect` in `database.TSE`, 152 records, the same in both firmwares - as the list the receiver matches a measured timing against, keep a detection made with a genuine firmware record alive through our own descriptor republish, withhold a timing the firmware's own picture window contradicts, and let the source cap follow that table instead of the panel. The table is read out of the window `allwinner,firmware-tse` names and is optional in every one of those senses: without the property the kernel's preset list decides, as before. `0014d` - `0014f` (Q1, 22.09.) come out of the vendor kernel's own msgbox backend: `0014d` sends one doorbell per message instead of two and states the argument order our send path diverges on, `0014e` puts the vendor's own two whitelist words back (they are the hardware spinlock's, not the message box's), and `0014f` refuses to write into a full TX FIFO, where a word would be lost without a trace. Withdrawn in the same pass: `0011`, a driver that would have written a DMA address into the CPU master's MBUS priority register; `0133b` (Q4, 22.09.) writes the video plane's destination rectangle into descriptor words 31..34, the window the firmware's own hardware composer fills for its video layer, so a zoom or a crop is the plane's ordinary CRTC_X/Y/W/H and a plane that covers its CRTC publishes the record 0120 wrote, word for word; `0154a` (Q6, 22.09.) adds a read-only `motor_state` in the stock driver's own packed read-back layout, so a vendor-side caller can read the motor's state at all, while `motor_ctrl` and `motor_limit` keep their output byte for byte; `0136l` - `0136q` and `0101a` (Q3, 22.09.) follow it - the driver's remaining German messages in English, a source the table does not carry answering `-ERANGE` with its measured timing instead of `-ENOLCK` for ever, colour space, quantisation, YCbCr encoding and the CE flag taken from the firmware's 44 byte record instead of a hardcoded BT.709 limited, three more of the vendor's picture settings as V4L2 controls, the own-record test asking whether a descriptor was ever published, a slot check in `S_DV_TIMINGS`, and the table's real module name. `0101a` carries 0101's number and sits behind `0136n`, because 0126, 0132 and 0136 grew the control table it extends. `0091d` (Q12, 22.09.) is comment only: the device showed that `SetEDIDVersion` alone republishes no port, so the mask is applied where fragment 7 publishes and a mask change needs the upload behind it - 0091c's order is right, one sentence of its reasoning was not. `0091e` (Q14, 22.09.) answers the 0x0f that byte read back: the mask handler re-reads its argument from the scratch after a log call, while the driver's wait is over as soon as the classifier copied it, so the next command's probe pattern replaced the argument - the sub-commands whose handler does that now wait for the handler's own effect, and a changed mask ends with the hotplug pulse `0091b` exports; `0133c` (Q10, 22.09.) is its other half, from the first bench run of that window: the firmware answers it by scaling ITS picture into the capture ring, by the window's share of the panel and without re-laying the ring out (DE scaler 0x05180034 and Proc node followed to 1536x864, INCAP rowbyte stayed 1920), so the fresh picture sits in the ring's top left corner, the plane reads that source rectangle and no more, and the record keeps the ring's own geometry, which the second bench run then corrected again - the ring goes on receiving the whole picture, so `0133d` (the window words are fractions of the firmware's fixed 30720x17280 space, which is the same number on a 1920x1080 panel and two thirds of a 1280x720 one) and `0133e` (Q15, 22.09.: the descriptor's source and destination window as two module parameters, driven independently of the plane, empty = the record of before word for word, a write republishes on the spot) exist to settle on a bench which of the two windows a zoom really is - which that bench then did: the eight words are a transform INTO the capture ring, a smaller source window is a zoom in and a destination window at the ring's origin with the plane cropping it a zoom out, so `0133f` (Q17, 22.09.) makes them the plane properties `src-window` and `dst-window`, blobs of four numbers in panel pixels, absent = the record of before word for word, retires `0133b`'s mapping and `0133e`'s parameters with their sysfs republish path, and takes the plane's downscale bound back to 1:1 because the same bench showed this composition block does not downscale an NV16 ring; `0154a` (Q6, 22.09.) adds a read-only `motor_state` in the stock driver's own packed read-back layout, so a vendor-side caller can read the motor's state at all, while `motor_ctrl` and `motor_limit` keep their output byte for byte; `0136l` - `0136q` and `0101a` (Q3, 22.09.) follow it - the driver's remaining German messages in English, a source the table does not carry answering `-ERANGE` with its measured timing instead of `-ENOLCK` for ever, colour space, quantisation, YCbCr encoding and the CE flag taken from the firmware's 44 byte record instead of a hardcoded BT.709 limited, three more of the vendor's picture settings as V4L2 controls, the own-record test asking whether a descriptor was ever published, a slot check in `S_DV_TIMINGS`, and the table's real module name. `0101a` carries 0101's number and sits behind `0136n`, because 0126, 0132 and 0136 grew the control table it extends; `0136r` - `0136t` (Q9, 22.09.) look a raster up in the firmware's table before the stale-record test, mark the own record in the status file and finish the driver's English; `0091f` (Q16, 22.09.) waits for every EDID fragment's copy (bEdidDataReady written by the handler's delay slot) before the next command, so a fast probe cannot corrupt the DDC block; `0136w` (Q16, 22.09.) is the reason that work was invisible on the device: `video_get_user()` takes its read-only shortcut before it reads the ioctl's flags, so `INFO_FL_ALWAYS_COPY` never reached `video_usercopy()` and the timing `0136m`/`0136v` fill beside the -ERANGE was thrown away - `VIDIOC_QUERY_DV_TIMINGS` is the only `_IOR` in `v4l2_ioctls[]` that carries the flag, and h713-tv printed `0x0p?, 0.0 MHz` for a source the kernel had measured (dev21). v4l2 core, upstream material, one lookup moved |
| cstenger, branch `h713-av1-probe` (`0afbd66` 02.10.2026, `3ca3a5e` 29.09.2026) | 3 (`0268` - `0270`) | the GPU clock and its DVFS, and one MBUS gate. `0268` (his `0152`: PLL_GPU's output divide-by-two and the GPU clock's 2-bit M divider) and `0270` (his `0142`: `mbus-av1` is bit 3, not 4): message and diff byte-identical, the head gains `From:`, `Subject:` and `Origin:`. `0269` (his `0153`) is adapted: it does not apply on top of `0024e` (it declares `gpu_opp_table` a second time), so it replaces `0024e`'s table of 288/432/600/696 MHz by his four points 150/200/300/600, pins PLL_GPU at 600 MHz with `assigned-clock-rates`, and does not repeat his thermal trip and cooling map, which `0024e` already carries with the same temperatures. Measured on the HY310, 13.10.2026: before, the old points ran at half their name (144/216/300/348 MHz by the Panfrost cycle counters, the clock tree said 288..696); after, 150/200/300/600 MHz (ratio 1.000 at every point). The text of `0269` names the clk patch `0268` where his and the side project's copies say `0263`. His `From:` is kept in all three |
| cstenger, branch `h713-av1-probe` (`43b2cdd` 03.10.2026): the cedrus decoder series | 26 (`0271` - `0296`) | his `0099` (scale down into the capture buffer), `0101` - `0125` in his order (cedrus hardening, 10-bit buffer sizing, the polyphase scaler for H.265 and H.264, `enum_framesizes`, field-coded MPEG-2, capture pitch 32), `0143`/`0154`/`0155` (VP9 on the video engine), `0144` (engine clock), `0151` (bidirectional capture mappings, needed behind the IOMMU). Message and diff byte-identical to his files; the head gains `From:`, `Subject:` and `Origin:`. Two of them are other people's work that he back-ported, and the head says `From: Christopher Stenger` while the real author is named in the text: `0277` is Pengpeng Hou's linux-media patch "reject invalid active H.264 ref indices", `0278` is Samuel Holland's "Fix missing cleanup in error path" (v2 posted by Andrey Skvortsov). `0292` (VP9) was derived by him from the vendor library's behaviour; its quantiser tables are the VP9 specification's (section 8.6.1) and one tile-offset formula follows libvpx, both named in the comments. Not taken from his tree: `0126`/`0127` (IOVA reservation, only for a display inside the IOMMU group), `0052`/`0080` (display behind the IOMMU), `0092` (render node, only for mpv on bare DRM), `0149` (10-bit video plane), `0140`/`0141` (AV1 presence probe) |
| well0nez | `0297` - `0298` | `0297` corrects the IOMMU comment of `0024e` (the codecs are translated, the display is not); `0298` resets the video engine when a job of another codec starts - the fix for a fault that only shows next to his VP9 (H.265 next to VP9 failed every job). The defconfig turns the IOMMU on (an idea read from his defconfig, one configuration line) |
| cstenger, branch `h713-av1-probe`: the AV1 decoder | 5 (`0300` - `0304`) | his `0150` (the `PL10` pixel format and the DRM modifier, as `0300`), `0145` (hantro hooks for a variant without a post-processor), `0146` with the node from his `0140` (`0302`: his two patches do not apply to our tree, the node is created with his change in it, text and 50 lines of node his), `0147` (the H713 AV1 driver, `0303`), `0148` (binding). Byte-identical where stated, same head additions. `0303` is generated code on his side; its `sunxi_h713_av1_gen.c` is ported from Collabora's `rockchip_vpu981_hw_av1_dec.c` (Benjamin Gaignard, GPL-2.0-only), whose copyright line the file keeps. His generator and test rig were neither taken nor read here; we keep the generated code. The AV1 decoder is switched off by `0310` at present |
| well0nez | `0305` - `0310`, `0312` - `0320` | `0305` - `0307` a guard for the video engine's shared bus reset (cedrus and the AV1 core); `0308`/`0309` release the engine's IOMMU ports once it has stopped after a damaged H.265 stream, and refuse an H.265 reference that is not a picture decoded here; `0310` turns the AV1 decoder off; `0312`/`0313` the eMMC host (re-initialise the controller before the stop after a failed multi-block read; start a read block only when the FIFO has room, the card read threshold); `0314` afbd reads the capture index as the field [2:0] of its word; `0315` - `0319` (15.10.2026) the video engine at 600 MHz unless the AV1 decoder is on, the H.265 collocated index checked, the VP9 code without a 2 KiB stack frame, the dead AV1 node of `0024` and an outdated IOMMU comment removed; `0320` (16.10.2026) the RTC's 32 kHz from the 24 MHz crystal instead of the internal RC (the register values LOSC_CTRL 0x4002 and LOSC_OUT_GATING bit 16 were read from a running vendor system of the same SoC over adb, read-only, and from mainline's H616 clock driver; the sequence was then measured on the HY310, `doku/213` §5). Own work, no foreign material. What `0308` says about the vendor's IOMMU fault handler was read in the stock 5.4.99 kernel of the HY310 (disassembly of `sunxi_iommu_irq` and the TLB functions, for interoperability; nothing taken, register names from the public BSP header `sunxi-iommu.h`); `0311` is a diagnostic patch that is not in the series |
| cstenger, branch `h713-letterbox` (`a4d6d5f` 18.10.2026), deep review of 19.10.2026 | 3 (`0322` - `0324`) | his `0156` (the H.264 bit reader's skip-bits wait bounded, as H.265's), `0157` (64 CAPTURE buffers instead of vb2's 32) and `0159` (all 16 H.265 DPB slots written on every job). Message and diff byte-identical to his files; the head gains `From:`, `Subject:` and `Origin:`. Everything else of his kernel work since `a861df2` was checked patch by patch and is either here already or not taken; the table is in `arbeit/cstenger-letterbox-20261019/tief-kernel/BERICHT.md` (local) |
| well0nez | `0321` | the stock BLE remote's focus keys: usage 0x0de is focus down and 0x0df focus up, the other way round from `0169` (measured with the owner at the wall, 18.10.2026; the infrared table of `0254` was right). Own work |
| well0nez | `0325` | the R_PIO header comment and the power key note in the dtsi name the EINT function 0xe as `0140`'s table has it (the pinctrl comment is the same correction as in cstenger's `0171`, whose code part `0140` already carries); comments only |
| well0nez | `0326` | the hdmirx driver checks the break of the display firmware's allocator before it writes a block into the shared memory (the HDCP 2.2 key, the window structures, the backlight PWM words) and leaves the step out when the allocator has reached the block's page; two comments of `0094`/`0101` corrected (SetWhiteBalance's argument, white balance versus CTM). Own work, no foreign material; the layout of the allocator is read from our own `cpu_comm` port |
| well0nez | `0327` | the arisc driver loads the device tree's crust image when the module option asked for the vendor image and the file is missing - the image runs the vendor ARISC firmware by default since 22.10.2026, and its boot chain starts no crust that could be kept |
| well0nez | `0328`, `0329` | `0328` applies the IR pin PL9 again after the vendor ARISC firmware has started (its start switches PL8/PL9 off); the code is the IR package of 03.10.2026, which `0252` left out while crust was the default. `0329` adds the HY300's stock IR remote (NEC address 0x00) to `rc-h713-fd02`, from the vendor's key table and a measurement of 22.10.2026, and names the map for every board. Own work |

cstenger says the same in his own `PROVENANCE.md` (in his repository at `8860991`): "the bulk of the H713 driver support … originates
from well0nez". The direction of the debt runs both ways - his arm64 work is what made the 6.18 line
possible here - which is why his kernel patches stay in the series with their `From:` lines, byte for byte where the table says so.
The follow-ups marked as pull-request candidates in `doku/116` are meant to go back to him.

The Wi-Fi driver is a second series, `mainline/patches/aic8800/`: nine patches on Radxa's `aic8800` tree
(commit `df4c783b`, vendor release `2026_0123`). `0008` - `0010` are cstenger's `0007` - `0009` from the same
branch, renumbered and byte-identical but for the phantom `CONFIG_DEBUG_FS_AIC` that `0010` compiles in and,
since 21.10.2026, two MAC addresses in the commit texts of `0008` and `0010` masked as `xx:xx:xx:xx:xx:xx`; the
rest is ours. That directory's README names each patch and its origin.

## Firmware components

Three git submodules under `mainline/external/`, pinned to forks under the same account:

| Component | Branch | Why a fork |
|---|---|---|
| `u-boot` | `h713-hy310` | 102 commits on top of cstenger's `h713` (base `8fe568c`): CCU tables, USB PHY, the MIPS display bring-up with the boot logo, the power gate and its infrared decoder (`0102`, 22.10.2026), the boot paths, the eMMC at HS200 with DMA in U-Boot and in the SPL, the LogoRegData container read by its own group boundaries, the staging of crust for BL31 and the HDCP 1.4 key path |
| `arm-trusted-firmware` | `sun50i-h713` | 32 commits: BL31 for this SoC, entering the boot gate on `SYSTEM_OFF`, the EL3 service for the HDCP 1.4 key, starting a staged crust and PSCI `SYSTEM_SUSPEND` through it (built only with `--standby`) |
| `sunxi-tools` | `h713` | `sunxi-fel` with the EL3 trap door the H713 needs to return to FEL |

`uboot-h713/` and `tfa-h713/` mirror the U-Boot and TF-A commits as patch files (`git format-patch`
from the fork, `SERIES.txt` names base, head and count), for reading without cloning. Both are
regenerated by hand, so `SERIES.txt` is the only place that says which fork commit each one stands on,
and both are verified the same way: applying the whole series onto the base has to produce a tree with
the same hash as the fork head. The build uses the submodules, not the mirrors.

**crust**, the firmware for the SoC's small OR1K core, is the fourth source tree: upstream
[crust](https://github.com/crust-firmware/crust) at `499a362` (after v0.6), with our H713 port on a branch
`h713` of a fork that is published with the release (`TODO.md` 1.6), so there is no submodule yet;
`release/build-all.sh` takes the checkout as `CRUST_SRC`. `crust-h713/` mirrors the branch the same way (88 patches,
head `54e4a08ab9f3`, the tree hash of the fork head checked). The port keeps crust's licence, BSD-3-Clause or
GPL-2.0-only, and every file it adds says so in its SPDX line. It was written from the vendor ARISC firmware's
behaviour and disassembly - its message contract, its DRAM self-refresh sequence register by register - not from vendor
source. The compiler it needs is built from GNU source tarballs pinned by SHA-256 (`mainline/tools/or1k-toolchain/`).
Since 22.10.2026 an image runs the vendor's ARISC firmware by default and carries crust only as an experiment
([arisc](docs/subsystems/arisc.md)); crust is still built with every image of a board that names a `CRUST_DEFCONFIG`.

`tfa-h713/` exists only since 05.10.2026, and its absence had been actively misleading: U-Boot had a
mirror and the kernel had `mainline/patches/kernel/`, so TF-A looked covered. It was not - the EL3
service that makes HDCP 1.4 work was in no repository at all. All three source trees are treated alike
now.

The GPU's user side is upstream **Mesa 25.0.7**, fetched as Debian's `mesa_25.0.7.orig.tar.xz` and pinned by
its SHA-256 in `rootfs/mesa/build-mesa.sh`, built with the panfrost gallium driver alone (EGL, GLES2, GBM;
no patches of ours). The kernel side of the Mali-G31 is mainline panfrost, with cstenger's `0053` (imported
buffers not mapped cacheable) from his branch and our `0024e` (operating points, cooling map) on top;
nothing further was taken from his tree for the keystone work.

The launcher's text is **FreeType** and **Quicksand**, both Debian trixie, neither modified and
neither stored here. `userspace/libh713osd/text.c` draws glyphs with FreeType 2.13.3 (`libfreetype-dev`, in the build sysroot
through `release/build-all.sh`'s `SYSROOT_PACKAGES`); `h713-osd` links `libfreetype.a` and the archives it needs (libpng 1.6.48,
bzip2, brotli, zlib, all from the same sysroot) **statically**, so the base image carries no FreeType package. FreeType is dual
licensed (FreeType License or GPL-2.0-only); this program is GPL-2.0, which takes the second. The face is `fonts-quicksand`
0.2016-2.1 (Quicksand Medium, **SIL Open Font License 1.1**, copyright file `/usr/share/doc/fonts-quicksand/copyright`), a package
line of the `desktop` profile (`rootfs/packages-desktop.txt`); h713-osd opens it at run time from
`/usr/share/fonts/truetype/quicksand/`. The OFL allows use and redistribution with the licence kept - the package carries it -
and forbids selling the font by itself. The arrows of the launcher's hint line are drawn as shapes because the face has no U+25B2.
The settings page (package S, `userspace/h713-settings`) draws with the same `osd_text` and the same face; nothing else is added.

## The decoders, the VA-API driver and Mesa (`rootfs/`)

Hardware video decoding on the H713 has three user-space parts, none of them a Debian package as shipped.

- **VA-API driver** (`rootfs/libva/`): Ondrej Jirman's (megi) [libva-v4l2_request](https://xff.cz/git/libva-v4l2_request/),
  v1.2 plus one README commit, `cac6ece0e23ac1f944dd3af266680aff0c3184df`, **GPL-3.0-or-later** (`COPYING`, the licence line of
  every source file, his README). Fetched at build time and pinned by that commit; nothing of it is in this repository, but the
  tarball the image carries has his tree, the patches and the build script next to the licence text. `patches/0001` - `0009` are
  Christopher Stenger's, made on the same base: each keeps his `From:`, carries an `Origin:` line naming his file in
  [cstenger/allwinner-h713-mainline](https://github.com/cstenger/allwinner-h713-mainline) at `43b2cdd`, and is otherwise his
  file byte for byte (`0007` has the placeholder author `build` in his tree and was left as it is). They change a GPL-3.0 work and
  are distributed here as GPL-3.0-or-later. `0010` - `0017` are ours (`From: well0nez`, a `License: GPL-3.0-or-later` line),
  written against that base; `0016` reads the HEVC slice header after the syntax of H.265 (7.3.6.1, 7.3.6.3), and `0017`
  follows libvpx's quantiser arithmetic as knowledge, nothing copied. `rootfs/libva/` is therefore GPL-3.0-or-later; `build-libva.sh` and `rootfs/mesa/cross-aarch64.ini.in`
  are GPL-2.0-or-later so that they can be part of its Corresponding Source. Two things about the base are not checked: megi's
  `decode.c` says it was "ported from the FFmpeg v4l2-request hwaccel" (LGPL-2.1-or-later, so the licence is compatible; whether
  the FFmpeg authors' copyright lines belong in his files is for him), and a full comparison with bootlin's MIT-licensed
  libva-v4l2-request is outstanding (a sample of 542 long lines found 7 equal, all dictated by the API).
- **Mesa 25.0.7** (`rootfs/mesa/`): upstream, built with the panfrost driver alone, no patches; **MIT** for the most part (the
  tree also has Apache-2.0, BSL-1.0, SGI-B-2.0 and GPL texts for single files). The licence texts and `docs/license.rst` travel in
  the tarball (`usr/local/share/doc/mesa/`), as the MIT notice requires for every copy.
- **Players and compositors** (`rootfs/packages-media.txt`, `packages-desktop.txt`): Debian trixie's ffmpeg, mpv, GStreamer,
  PipeWire, Kodi, cage and labwc, unchanged, under their own licences; their `copyright` files stay in the image.

What we took from cstenger's tree besides patches is **knowledge**, put into our own words and our own files: how the 10-bit
HEVC output is laid out, the AV1 core's hardware rules, mpv's settings for a Mali-G31, the reference method for the bit-exact
tests (framemd5 against a software decoder). No file of his `tools/` or `docs/` was copied.

## Left out on purpose: the unlicensed part of cstenger's tree

His repository has no LICENSE file. Apart from his kernel patches (changes to Linux, so GPL-2.0; the table above lists
them) and nine C programs with a `SPDX-License-Identifier: GPL-2.0` line in the head, no file of it says under which
terms it may be copied or passed on, and nobody but him can say so. He has not answered so far. Without that statement we do not
redistribute his files: since 13.10.2026 they are no longer in the working tree, and what we needed from them was
written afresh or replaced.

- **Gone from the tree:** the documents and logs under `mainline/docs/` (bring-up notes, hand-overs, measurement logs,
  his plans), his helper programs and scripts under `mainline/tools/` (serial and flashing tools, his rootfs build, the
  display and video measuring scripts, Wi-Fi and boot helpers), his three libva patch files with their README (patches on
  bootlin's MIT-licensed code, not used in `main`), and his top-level README, PROVENANCE, `.gitmodules`, `.gitignore` and
  one measurement protocol. [`doku/210`](doku/210-entflechtung-unlizenzierte-dateien-aus-dem-subtree-20261013.md) lists every path.
- **Written afresh:** `mainline/README.md` and `mainline/tools/README.md`, the `.gitignore` lines in the top-level file, and
  the table of the display firmware's routines, now a section of [docs/subsystems/cpu-comm.md](docs/subsystems/cpu-comm.md)
  (the facts after his capture, the wording and the checking ours).
- **Still here from him:** the kernel patches the table above credits to him, `mainline/patches/aic8800/` `0008` - `0010`
  likewise, and these nine programs, each with his SPDX line: `mainline/tools/display/drm-flip.c` and, in
  `mainline/tools/video/`, `decd-client.c`, `gles-nv12.c`, `gles-play.c`, `gles-probe.c`, `gles-scanout.c`, `gles-tear.c`,
  `gputest.c` and `h713-present.c`. `LICENSE` names them as the parts that are his.
- **Started as his, written anew on 20.10.2026** (TODO 7.20 a, b, d), each from a description of what it has to do,
  without the text of the file before: `mainline/build/build.sh` and `mainline/build/uboot-build.sh` (the outputs
  byte for byte the same as with the old scripts), `mainline/config/versions.env` and `mainline/config/toolchain.md`,
  and in `mainline/patches/` the kernel `series`, `board/hy200_qz713df_a1_defconfig`, `kernel/README.md` and
  `aic8800/README.md` (the series the same entries in the same order, the defconfig the same options). The list
  `aic8800/series` is nine file names and nothing else, so the new one is the same bytes. His three diagnostic
  fragments `iommu`, `kasan` and `builtin-drivers` and the old copy of the AIC8800 driver under
  `mainline/modules/aic8800/` (vendor release `2024_0109` with his README; no build read it) were removed instead.
- **Where the removed files are:** in his repository at `8860991`, with the paths of `mainline/` minus that first directory
  (`mainline/docs/status.md` there is `docs/status.md`), and in this repository's history, for as long as it carries his
  commits (`git show 8860991:docs/status.md`). Older entries of the journal that name a path like `mainline/docs/...` or
  `mainline/tools/...` mean his tree as it was; they are not rewritten.

Kernel patches and the U-Boot mirrors keep comments that point at his documents (`docs/kernel-bump.md`, `docs/status.md`,
`docs/vaapi-scope.md` and others). The patches stay byte for byte as they are, so those pointers are origin notes, not links.

## What is *not* in this repository, on purpose

**No vendor firmware, no keys, no dumps.** The display firmware (`display.bin`), the vendor's ARISC
firmware (crust, which replaces it on the HY310, is ours and built with the image), the Wi-Fi firmware and
the picture tables are the vendor's, not ours to redistribute - they are the same files
on every device of this model, and every owner already has them. The image ships only the empty target
directories; `h713-install` mounts the image's two file systems and copies the files out of the user's own
dump (or off a device already running this layout) into them during installation. The material in secure storage -
HDCP keys, MAC addresses, serial number - is a different matter again: it exists once, per device, and
copying someone else's would be both illegal and useless.

The same applies to the reverse-engineering material - stock firmware images, disassembly databases,
captures. It exists, it is what this port was built from, and it stays on private disks. Every push is
preceded by `release/sperr-scan.py`, which fails the release if a vendor blob, a key, a dump or an image
has found its way into the tree.

## Licences

**Code: GPL-2.0, unless a file or directory says otherwise** ([LICENSE](LICENSE)) - the kernel patches, the U-Boot changes
and the drivers inherit it from their upstreams and could not be anything else; the tools in `installer/`, `rootfs/`,
`userspace/` and `release/` are under it by choice. The exceptions: a file's own `SPDX-License-Identifier` wins (`tfa-h713/`
BSD-3-Clause, `crust-h713/` BSD-3-Clause or GPL-2.0-only, `uboot-h713/` GPL-2.0+, some device-tree files dual-licensed, the GPL-2.0 lines of cstenger's nine programs);
`rootfs/libva/patches/` is GPL-3.0-or-later (changes to megi's GPL-3.0-or-later driver); `rootfs/libva/build-libva.sh` and
`rootfs/mesa/cross-aarch64.ini.in` are GPL-2.0-or-later; and the parts of cstenger's tree under `mainline/` carry what he put
on them (a file of his without a licence line is not covered by ours; since 20.10.2026 the ones there were are gone or
written anew, "Left out on purpose" above).

**In the image.** An image carries its licence notices under `/usr/local/share/doc/h713-linux/`: a README with every
part's licence and where the source of every part is, the revisions it was built from (`SOURCES`), the BSD notices of
TF-A's BL31 and of crust (the copyright lines of every source file built into them), the kernel's licence, the copyright
files of the libraries linked statically into `h713-osd` and `h713-settings`, and the list of Debian's source packages;
Debian's own copyright files stay in `/usr/share/doc/` ([rootfs/README.md](rootfs/README.md)). The source of this
project's own parts and of its patches is the repository at the commit `SOURCES` names, which the release tag points at
and which the release page carries as one archive with the submodules checked out; Linux and the aic8800 driver are in it
as patches, configuration and pinned revisions, their trees come from kernel.org and the pinned vendor tarball, and
Debian's source packages are on deb.debian.org and snapshot.debian.org (the owner's decision of 21.10.2026, `TODO.md` 2.128).

**Documentation: CC BY-SA 4.0** ([LICENSE.docs](LICENSE.docs)) - `docs/`, `doku/` and the Markdown at the
top level: share it, adapt it, credit **well0nez**, keep the same licence.

No file here is derived from vendor source code. The drivers were written from measurements, disassembly
of the shipping firmware, and the behaviour of the hardware.

## Reading the history

- `legacy` branch and tag `legacy-arm32-2026-08`: the 32-bit BSP era of this project, frozen. Different
  kernel, different approach; kept because the reverse-engineering notes in it are still valid.
- `doku/`: the German working journal, dated. Nothing in the English documentation claims anything that
  is not written down there with a date and a measurement. It is the evidence, not the manual, and its
  entries are never rewritten after the fact - [`doku/README.md`](doku/README.md) says why that rule is
  what makes the promise above worth anything, and [`doku/INDEX.md`](doku/INDEX.md) turns the citations
  around so you can look up what any statement in `docs/` rests on.
