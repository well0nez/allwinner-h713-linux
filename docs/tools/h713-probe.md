# `h713_probe` - what is this board?

A U-Boot build that answers one question about an H713 device nobody here has ever seen, and writes nothing
while doing it. It is meant for people whose projector is not the HY310 this port was built on.

Everything the port needs to know about a new board is one profile row: the size and SHA-256 of its
`display.bin`, the project ID it declares, the DRAM settings its own boot0 uses, how many partitions it has
and where its vendor files are. All of that is readable off the device. None of it needs a write, and none
of it needs the device to be in our hands - which is the whole point, because the table can only ever
describe boards someone has held.

## What it does not do

- **No write to the eMMC.** Not the partition table, not the environment - the build has no writable
  environment at all (`CONFIG_ENV_IS_NOWHERE`), so even a stray `saveenv` has nowhere to go.
- **The coprocessor stays in reset.** The display firmware is read and hashed, never started. Note
  that this is *not* what your device normally does: the vendor's own U-Boot loads `mips/` and
  releases the MIPS inside the boot-logo path, long before it loads a kernel. A probe run and a stock
  boot are therefore not comparable states, and a dark panel during a probe is the expected one.
- **The panel is never driven.** On an unidentified board the panel timing is unknown, and the register
  patches, the OSD geometry and the boot logo are all sized from it. So the probe refuses instead of
  guessing.

The fan and the lamp *do* come on, because one GPIO powers both (see
[power-gate](../uboot/power-gate.md)) and U-Boot raises it at start-up. That is the same behaviour as the
installer build. Don't leave it running unattended.

## Running it

The device has to be in FEL. Hold the reset button while applying power, or - if Linux is already running -
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
-- vendor boot0 (mmc 1) --
   dram_clk    0x0000027c   636 MHz
   dram_type   0x00000003
   ...                            24 words, the vendor's own DRAM settings
-- display artifacts --
   H713 probe: read from mmc 1#bootloader_b:mips
   H713 MIPS: display.bin SHA-256 ...
   H713 MIPS: firmware identity accepted (HY310 (QZ713 V3.1))  or: size ... is not in the table -- new revision
   H713 MIPS: HDCP 1.4 key-wait loop found at 0x4b13d0a4 (normal boot defuses it; the probe only locates it)
   H713 probe: project 0x30, panel 1920x1080 dual-port         or: ... not in this build's panel table
   H713 disp: project  prologue  timing  de                    the project descriptors the firmware carries
-- profile row --                 the same facts as data, see below
```

Paste all of it into an issue. Between the DRAM block, the digest and the project list, that is enough to
write the table row - and to build a U-Boot with the right DRAM clock for the board.

### The profile row

Everything above is written for a person watching a console; this block is written for the file that
comes out of it. One `key: value` line per field, named exactly as `h713-install identify` names it,
in the order a board profile is written - so `boards/<id>/` and `installer/h713/profiles/<id>.py` can
be filled in from a pasted log without anyone here ever holding the board.

```
-- profile row --
board: HY310 (QZ713 V3.1)         the firmware revision's own name, or "unknown"
dram_clk_mhz: 792                 or "unknown -- no vendor boot0 on this eMMC"
layout.entries: 26                partitions the GPT actually carries
mips.display_bin.size: 1256216
mips.display_bin.sha256: 16c74a28...
panel.declared_project_id: 0x30
hdcp_wait_va: 0x4b13d0a4          or "not found"
active_slot: _b                   the A/B slot misc declares (_a when there is no misc)
mips.source: mmc 1#bootloader_b   the partition the artifacts above were read from
mips.bootloader_a: <sha256> 1256216
mips.bootloader_b: <sha256> 1256216
mips.bootloader_a_equals_b: yes
panel_config.ini: mmc 1#Reserve0_b
secure_storage: sunxi at LBA 12288 (map lists 6 entries; item magic 0x17253948 at LBA 12304, first item "hdcpkey")
```

Three of those need a word.

**`panel.declared_project_id`, and where `panel_config.ini` was found.** The panel follows the id the
board declares, never the firmware image - one `display.bin` serves two panels
([mips.md](../subsystems/mips.md)). The probe resolves the id the way the boot path does:
`h713_project` from the environment first, which is what the installer writes, and then the
`panel_config.ini` line says the file was not read at all; otherwise the file itself, looked up **by
partition name** - `Reserve0_<slot>`, then `Reserve0`, then `media_data`. `ProjectID = 48` in that file
is decimal and means 0x30. If neither source exists, both lines say so instead of guessing - that
board's panel has to be measured.

**Both bootloader slots are hashed**, addressed by name (`1#bootloader_a`, `1#bootloader_b`) because
another layout numbers them differently. A stock device keeps `display.bin` twice and the two copies are
not always the same file, so "which one is live" and "do the two agree" are separate questions and a
restore needs both answered. `mips.bootloader_a_equals_b: no` is a fact about your device, not a fault.

**`secure_storage` reports presence and a name, never bytes.** LBA 12288 is the sunxi secure storage:
HDCP 1.4 and 2.2 keys, the WLAN and Bluetooth MAC addresses, the serial number - none of it in any
firmware image, none of it recoverable once lost. The row prints the shape only: how many entries the
map at LBA 12288 lists, that the item magic `0x17253948` is there sixteen sectors in (the map itself is a
plain `name:size` list without one), and what the first item calls itself. No contents, no digest, and
when the signature is absent, no bytes either. It is there so a board's profile can lock the region, not
so anything can be read out.

The row closes by saying that the stock boot chain starts the MIPS in its logo path and that this
probe never does. That is the one sentence in the output worth reading twice.

### About the DRAM block

It is read from the boot0 header on the eMMC, not from a firmware image: that is the copy the device boots.

What our builds ship is not identical to it. `tpr0` - `tpr2` are computed from the clock by the DDR3 timing
code and never reach the hardware on that path, and `para2`/`tpr13` differ too: ours are
`0x04000000`/`0xb4016103` where the HY310's own boot0 carries `0`/`0x34010100`, in the stock image and in a
full dump of the device alike, and why is not written down anywhere (`doku/120` §4.1). But `zq`, `para1`, the
mode registers and `tpr3` - `tpr12` are taken verbatim, and `tpr11`/`tpr12` in particular are per-board PHY
tuning that cannot be derived from anything. Those are the numbers a new board has to supply.

## Which DRAM clock the probe itself runs at

624 MHz. The two boards this port knows share one DRAM value set and differ only in the clock - 624 on the
bench board, 792 on the HY310 - so 624 is the conservative end of the range and the branch of the DRAM code
a low-clock board takes. It is a starting value, not a claim about your board: what your board actually uses
is in the output.

If it does not train at all, the board is far enough from these two that the numbers in the boot0 block are
the place to start, and those can also be read out of a dump without running anything
([`h713-extract`](h713-extract.md)).

## Where the vendor files are

On a stock device they live in a FAT partition the vendor calls `bootloader_a` or `bootloader_b` -
which of the two is live comes from the A/B slot byte in `misc`, resolved exactly as stock resolves
it; on a device already running this port they are on `hy310-boot`. The probe asks the GPT for those
**names**, not for an index, because an index is the one thing two layouts never share. The
environment's `h713_mips_dev` overrides all of it (`1#<partition>`, or `<dev>:<part>`) and the probe
puts the environment back when it is done; `1:2` and `1:1` remain as a last resort for a GPT it
cannot read. If nothing is found, set `h713_mips_dev` and run `h713_probe` again.

## Building it

```
mainline/build/uboot-build.sh <output-dir> h713_probe_defconfig
```

`release/build-all.sh` builds it as step 2b2 and drops `u-boot-h713-probe.bin` next to
`u-boot-installer.bin`.
