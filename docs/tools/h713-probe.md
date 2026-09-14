# `h713_probe` — what is this board?

A U-Boot build that answers one question about an H713 device nobody here has ever seen, and writes nothing
while doing it. It is meant for people whose projector is not the HY310 this port was built on.

Everything the port needs to know about a new board is one table row: the size and SHA-256 of its
`display.bin`, the display project ID, the panel, and the DRAM settings the vendor uses. All of that is
readable off the device. None of it needs a write, and none of it needs the device to be in our hands — which
is the whole point, because the table can only ever describe boards someone has held.

## What it does not do

- **No write to the eMMC.** Not the partition table, not the environment — the build has no writable
  environment at all (`CONFIG_ENV_IS_NOWHERE`), so even a stray `saveenv` has nowhere to go.
- **The coprocessor stays in reset.** The display firmware is read and hashed, never started.
- **The panel is never driven.** On an unidentified board the panel timing is unknown, and the register
  patches, the OSD geometry and the boot logo are all sized from it. So the probe refuses instead of
  guessing.

The fan and the lamp *do* come on, because one GPIO powers both (see
[power-gate](../uboot/power-gate.md)) and U-Boot raises it at start-up. That is the same behaviour as the
installer build. Don't leave it running unattended.

## Running it

The device has to be in FEL. Hold the reset button while applying power, or — if Linux is already running —
use [`h713-fel`](h713-fel.md).

```
sunxi-fel uboot u-boot-h713-probe.bin
```

Use the `sunxi-fel` from the release: the H713's SoC ID is `0x1860` and older builds do not know the trap
door it needs. Watch the serial console; the probe runs by itself and stops at a prompt. Typing `h713_probe`
runs it again, and `ums 0 mmc 1` still offers the eMMC as a USB disk if you want a backup in the same
session.

## What it prints

```
-- partitions (mmc 1) --          the GPT as U-Boot reads it
-- vendor boot0 (mmc 1, LBA 16) --
   dram_clk    0x0000027c   MHz: 636
   dram_type   0x00000003
   ...                            24 words, the vendor's own DRAM settings
-- display artifacts --
   H713 MIPS: display.bin SHA-256 ...
   H713 MIPS: firmware identity accepted (HY310 QZ713 V3.1)   or: unknown -- new revision
   H713 MIPS: HDCP wait site at 0x4b13d0a4 (not patched -- probe writes nothing)
   H713 probe: panel 1920x1080, project 0x30                  or: panel unknown for this image
   H713 disp: project  prologue  timing  de                   the project descriptors the firmware carries
```

Paste all of it into an issue. Between the DRAM block, the digest and the project list, that is enough to
write the table row — and to build a U-Boot with the right DRAM clock for the board.

### About the DRAM block

It comes from the boot0 header on the eMMC, not from a firmware image: the flashing tool patches `para2` and
`tpr13` on the way in, so the copy on the device is the one that describes the running board.

What our builds ship is not identical to it either — `tpr0`–`tpr2` are computed from the clock by the DDR3
timing code, and `para2`/`tpr13` are the patched values. But `zq`, `para1`, the mode registers and
`tpr3`–`tpr12` are taken verbatim, and `tpr11`/`tpr12` in particular are per-board PHY tuning that cannot be
derived from anything. Those are the numbers a new board has to supply.

## Which DRAM clock the probe itself runs at

624 MHz. The two boards this port knows share one DRAM value set and differ only in the clock — 624 on the
bench board, 792 on the HY310 — so 624 is the conservative end of the range and the branch of the DRAM code
a low-clock board takes. It is a starting value, not a claim about your board: what your board actually uses
is in the output.

If it does not train at all, the board is far enough from these two that the numbers in the boot0 block are
the place to start, and those can also be read out of a dump without running anything
([`h713-extract`](h713-extract.md)).

## Where the vendor files are

The display artefacts live in a FAT partition the vendor calls `bootloader_a`, with a byte-identical copy in
`bootloader_b`; on a device already running this port they are on `hy310-boot`. The probe tries the
environment's `h713_mips_dev` first, then `1:2`, then `1:1`, and puts the environment back. If none of them
has the files, set `h713_mips_dev` to the right partition and run `h713_probe` again.

## Building it

```
mainline/build/uboot-build.sh <output-dir> h713_probe_defconfig
```

`release/build-all.sh` builds it as step 2b2 and drops `u-boot-h713-probe.bin` next to
`u-boot-installer.bin`.
