# Provenance

Who made what, where it comes from, and what is deliberately absent.

## The kernel series

`mainline/` is a **git subtree** of [cstenger/allwinner-h713-mainline](https://github.com/cstenger/allwinner-h713-mainline)
at commit `8860991`, with full history - you can `git log` any of his commits here. On top of it,
`mainline/patches/kernel/series` carries 180 patches in fifteen sections:

| Origin | Patches | Note |
|---|---|---|
| well0nez, via cstenger's `main` | 20 (`0001` - `0022`; `0011` withdrawn 22.09.2026, the file stays in `patches/kernel/`) | **the H713 driver series** - CCU, pinctrl, MMC, USB PHY, PWM, LRADC, board manager, cpu_comm, tvtop, decd. Written here, carried in his tree with attribution, six of them adapted from 6.16 to the pinned kernel. Byte-identical to his tree |
| cstenger, `main` | 24 (`0023` - `0048`; `0040` retired 15.09., see `zurueckgenommen/`) | the arm64 side built around that series: DTS, defconfig, boot chain, cpufreq. Byte-identical, verified by comparison |
| cstenger, branch `h713-display-video-path` | 17 (`0051` - `0086`) | byte-identical; scanout, DECD, IOMMU, MMC, video plane |
| well0nez | `0049`, `0091` - `0161` | ARISC, cpu_comm, HDMI input, audio, motor, board manager, Wi-Fi, one DTB name per board |
| well0nez, follow-ups | `0005a`, `0013a`, `0014a` - `0014f`, `0024a` - `0024d`, `0078a`, `0091a` - `0091f`, `0093a`, `0096a`, `0092a`, `0133a` - `0133e`, `0135b`, `0136a` - `0136v`, `0101a`, `0154a`, `0159a`, `0161a`, `0161b` | small fixes placed directly after the original they touch, so the original stays byte-identical. `0096a` carries the TVFE/TVCAP driver, which is cstenger's EXPERIMENT patch 0087 from `h713-display-video-path` (measured on his board 02.09.2026), turned into a module and translated - his code, our wiring. `0013a` carries three decd corrections from cstenger's branch; `0005a` (USB PHY SIDDQ), `0136a` and `0136c` (HDMI hot plug) are ours, 15./16.09.; `0014b`, `0014c` and `0024d` are the msgbox's three interrupt lines and the decision that `cpu_comm` requests only its own bank's line, 16.09.; `0091a` resolves the ARISC firmware's SRAM addresses from the loaded image, 17.09.; `0096a` (the TVFE/TVCAP driver, built in), `0093a`, `0136d` (the vsync enable held while the receiver is bound) and `0091b`, `0136e` (a second hotplug pulse at the end of the bring-up) are the warm-receiver fix for issue #1, 19.09.; `0136f` (the receiver derives the capture ring's geometry from INCAP's rowbyte and active window, so the format is the ring and not the source on a panel smaller than the source) and `0136g` (the DE picture-scaler syscon it reads as an optional cross-check) let a 1920x1080 source play on the HY300 Pro's 1280x720 panel, issue #1, 20.09.; `0161a` disables the dtsi's pwm-backlight on the HY300 Pro, whose PB5 is the LED-boost and fan-rail enable as a plain GPIO (A14), 20.09.; `0159a` requests the board manager's fan-power line with GPIOF_OUT_INIT_HIGH instead of flags 0 and logs the first RPM reading after SYSTEM_RUNNING, so a foreign owner's journal proves his tacho (A14), and `0133a` lets a board declare the AFBD handoff state it hands over in `allwinner,handoff-state` instead of meeting three literals, with all six words in the refusal (A11); `0092a` and `0161b` do the same for the display firmware's two elog addresses, which the HY300 Pro's image keeps 0xC00 lower than the HY310's (A12), 21.09.; `0136h` - `0136k` (T2, 21.09.) take the display firmware's own mode table - the TFD module `THDMI_ModeDetect` in `database.TSE`, 152 records, the same in both firmwares - as the list the receiver matches a measured timing against, keep a detection made with a genuine firmware record alive through our own descriptor republish, withhold a timing the firmware's own picture window contradicts, and let the source cap follow that table instead of the panel. The table is read out of the window `allwinner,firmware-tse` names and is optional in every one of those senses: without the property the kernel's preset list decides, as before. `0014d` - `0014f` (Q1, 22.09.) come out of the vendor kernel's own msgbox backend: `0014d` sends one doorbell per message instead of two and states the argument order our send path diverges on, `0014e` puts the vendor's own two whitelist words back (they are the hardware spinlock's, not the message box's), and `0014f` refuses to write into a full TX FIFO, where a word would be lost without a trace. Withdrawn in the same pass: `0011`, a driver that would have written a DMA address into the CPU master's MBUS priority register; `0133b` (Q4, 22.09.) writes the video plane's destination rectangle into descriptor words 31..34, the window the firmware's own hardware composer fills for its video layer, so a zoom or a crop is the plane's ordinary CRTC_X/Y/W/H and a plane that covers its CRTC publishes the record 0120 wrote, word for word; `0154a` (Q6, 22.09.) adds a read-only `motor_state` in the stock driver's own packed read-back layout, so a vendor-side caller can read the motor's state at all, while `motor_ctrl` and `motor_limit` keep their output byte for byte; `0136l` - `0136q` and `0101a` (Q3, 22.09.) follow it - the driver's remaining German messages in English, a source the table does not carry answering `-ERANGE` with its measured timing instead of `-ENOLCK` for ever, colour space, quantisation, YCbCr encoding and the CE flag taken from the firmware's 44 byte record instead of a hardcoded BT.709 limited, three more of the vendor's picture settings as V4L2 controls, the own-record test asking whether a descriptor was ever published, a slot check in `S_DV_TIMINGS`, and the table's real module name. `0101a` carries 0101's number and sits behind `0136n`, because 0126, 0132 and 0136 grew the control table it extends. `0091d` (Q12, 22.09.) is comment only: the device showed that `SetEDIDVersion` alone republishes no port, so the mask is applied where fragment 7 publishes and a mask change needs the upload behind it - 0091c's order is right, one sentence of its reasoning was not. `0091e` (Q14, 22.09.) answers the 0x0f that byte read back: the mask handler re-reads its argument from the scratch after a log call, while the driver's wait is over as soon as the classifier copied it, so the next command's probe pattern replaced the argument - the sub-commands whose handler does that now wait for the handler's own effect, and a changed mask ends with the hotplug pulse `0091b` exports; `0133c` (Q10, 22.09.) is its other half, from the first bench run of that window: the firmware answers it by scaling ITS picture into the capture ring, by the window's share of the panel and without re-laying the ring out (DE scaler 0x05180034 and Proc node followed to 1536x864, INCAP rowbyte stayed 1920), so the fresh picture sits in the ring's top left corner, the plane reads that source rectangle and no more, and the record keeps the ring's own geometry, which the second bench run then corrected again - the ring goes on receiving the whole picture, so `0133d` (the window words are fractions of the firmware's fixed 30720x17280 space, which is the same number on a 1920x1080 panel and two thirds of a 1280x720 one) and `0133e` (Q15, 22.09.: the descriptor's source and destination window as two module parameters, driven independently of the plane, empty = the record of before word for word, a write republishes on the spot) exist to settle on a bench which of the two windows a zoom really is; `0154a` (Q6, 22.09.) adds a read-only `motor_state` in the stock driver's own packed read-back layout, so a vendor-side caller can read the motor's state at all, while `motor_ctrl` and `motor_limit` keep their output byte for byte; `0136l` - `0136q` and `0101a` (Q3, 22.09.) follow it - the driver's remaining German messages in English, a source the table does not carry answering `-ERANGE` with its measured timing instead of `-ENOLCK` for ever, colour space, quantisation, YCbCr encoding and the CE flag taken from the firmware's 44 byte record instead of a hardcoded BT.709 limited, three more of the vendor's picture settings as V4L2 controls, the own-record test asking whether a descriptor was ever published, a slot check in `S_DV_TIMINGS`, and the table's real module name. `0101a` carries 0101's number and sits behind `0136n`, because 0126, 0132 and 0136 grew the control table it extends; `0136r` - `0136t` (Q9, 22.09.) look a raster up in the firmware's table before the stale-record test, mark the own record in the status file and finish the driver's English; `0091f` (Q16, 22.09.) waits for every EDID fragment's copy (bEdidDataReady written by the handler's delay slot) before the next command, so a fast probe cannot corrupt the DDC block |

cstenger says the same in his own `PROVENANCE.md`: "the bulk of the H713 driver support … originates
from well0nez". The direction of the debt runs both ways - his arm64 work is what made the 6.18 line
possible here - which is why this repository vendors his tree with its full history instead of copying
files out of it. The follow-ups marked as pull-request candidates in `doku/116` are meant to go back to
him.

The Wi-Fi driver is a second series, `mainline/patches/aic8800/`: nine patches on Radxa's `aic8800` tree
(commit `df4c783b`, vendor release `2026_0123`). `0008` - `0010` are cstenger's `0007` - `0009` from the same
branch, renumbered and byte-identical but for the phantom `CONFIG_DEBUG_FS_AIC` that `0010` compiles in; the
rest is ours. That directory's README names each patch and its origin.

## Firmware components

Three git submodules under `mainline/external/`, pinned to forks under the same account:

| Component | Branch | Why a fork |
|---|---|---|
| `u-boot` | `h713-hy310` | 82 commits on top of cstenger's `h713` (base `8fe568c`): CCU tables, USB PHY, the MIPS display bring-up with the boot logo, the power gate, the boot paths, the eMMC at HS200 with DMA in U-Boot and in the SPL, and the LogoRegData container read by its own group boundaries |
| `arm-trusted-firmware` | `sun50i-h713` | BL31 for this SoC, plus entering the boot gate on `SYSTEM_OFF` |
| `sunxi-tools` | `h713` | `sunxi-fel` with the EL3 trap door the H713 needs to return to FEL |

`uboot-h713/` mirrors the U-Boot commits as patch files (`git format-patch` from the fork, `SERIES.txt`
names base, head and count; last regenerated 17.09.2026 at the fork head `da74b89`, 82 patches), for
reading without cloning. It is regenerated by hand, so `SERIES.txt` is the only place that says which
fork commit it stands on. The build uses the submodule, not the mirror.

## What is *not* in this repository, on purpose

**No vendor firmware, no keys, no dumps.** The display firmware (`display.bin`), the ARISC firmware, the
Wi-Fi firmware and the picture tables are the vendor's, not ours to redistribute - they are the same files
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

**Code: GPL-2.0** ([LICENSE](LICENSE)) - the kernel patches, the U-Boot changes and the drivers inherit it
from their upstreams and could not be anything else; the tools in `installer/`, `rootfs/`, `userspace/` and
`release/` are under it by choice, so the whole tree answers to one licence.

**Documentation: CC BY-SA 4.0** ([LICENSE.docs](LICENSE.docs)) - `docs/`, `doku/` and the Markdown at the
top level: share it, adapt it, credit **well0nez**, keep the same licence.

No file here is derived from vendor source code. The drivers were written from measurements, disassembly
of the shipping firmware, and the behaviour of the hardware.

## Reading the history

- `legacy` branch and tag `legacy-arm32-2026-08`: the 32-bit BSP era of this project, frozen. Different
  kernel, different approach; kept because the reverse-engineering notes in it are still valid.
- `doku/`: the German working journal, dated. Nothing in the English documentation claims anything that
  is not written down there with a date and a measurement.
