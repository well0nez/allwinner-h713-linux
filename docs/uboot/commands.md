# U-Boot commands: h713_disp, h713_mips, h713_logo, h713_i2c

> **Running the projector needs none of this.** The shipped `bootcmd` starts the display firmware and
> boots Linux on its own. Everything below is for bring-up, diagnosis and repair - reach for it when
> something does not come up, not before.

Four commands exist only in this fork, not in mainline U-Boot. `h713_disp` is the one that actually gets
a picture on the panel - it is what `bootcmd` calls - and its `init`/`auto`/`load` subcommands are the
ones worth knowing day to day. The other three, and most of `h713_disp`'s own subcommands beyond those,
are bring-up and diagnostic tools built while reverse-engineering the display path: they talk to the same
hardware more directly, for when `h713_disp` itself needs to be the suspect.

## h713_disp - bring the display up and run it

| Subcommand | What it does |
|---|---|
| `init <project-id> [elog=<0-5>] [logo [file.bmp]]` | bring the display up and stop: clocks, panel power sequencing, firmware handoff. This is what `bootcmd` runs before `boot_emmc`/`boot_net`, and since 15.09.2026 it runs it with `logo`. `logo` puts the boot logo on the panel with the firmware left running - proven on the HY310 on 15.09.2026, three runs: the OSD buffer is filled before the panel powers up, so the first frame the panel ever scans is the logo, and it is published again and re-armed after the firmware is ready, the way the KMS driver later shows its console. It reads `bootlogo.bmp` from the root of the partition the display artifacts come from - `/boot/bootlogo.bmp` on an installed device, which `h713-extract` and `h713-install` put there. A missing logo is a warning, not a failed boot; the panel then stays black until Linux. The file's SHA-256 is printed and looked up in the vendor table to name a stock asset in the log, nothing more: a logo that matches no row is shown all the same, so your own 24-bit BMP at the panel's size works |
| `auto <project-id> [nowait] [logo [file.bmp]]` | load the display artifacts from eMMC and run; `logo` also publishes a boot logo and leaves it on screen - but parks the coprocessor as its last act, so Linux cannot switch to HDMI afterwards (`doku/67`). Not the product boot path |
| `load <project-id>` | load the artifacts from eMMC without running them, so `display_cfg.xml` can be patched first |
| `list <blob-addr>` | list every project ID a staged artifacts blob knows about |
| `dump [force]` | dump the display register blocks |

```
=> h713_disp auto 0x30
```

`0x30` is this device's own project ID - the default of `h713_project` in the shipped environment (see
`environment.md`); the command's own source comment says `0x34`, but that is cstenger's bench board, not
this one (`doku/108-plan-vendordaten.md`).

Everything else under `h713_disp` - `test`, `mips-test`/`mips-trace`/`mips-comm-trace`/`mips-stability`,
`calltable`, `commstate`/`commtrace`/`commcall`, `comm-pq-test`, `clkfind`, `regscan`, `fwmd`, `teardown`,
`scanrate`, `bl-gpio`, and `panel-test` with around thirty pattern modes (`tcon-checker`, `fb-pitch`,
`vendor-logo`, …) - is a firmware bring-up diagnostic, not needed for normal use. `help h713_disp` at the
prompt lists all of them; `elog=<0-5>` on `init` turns on the coprocessor's own log ring, covered in
`docs/subsystems/mips.md`.

## h713_mips - manage the display coprocessor directly (diagnostic)

Below `h713_disp` sits the MIPS32 core that runs the vendor firmware `display.bin`; `h713_mips` talks to
it directly, without the panel power sequencing `h713_disp` wraps around it. Its own help text calls it
out as manual management - useful for telling whether the coprocessor or the ARM-side bring-up is at
fault, not for a normal boot.

| Subcommand | What it does |
|---|---|
| `status` | report whether the coprocessor is running |
| `verify` | check the loaded firmware's size and digest against the known-revision table |
| `log [start] [end]` | dump a range of the firmware's own log ring (default range covers its working set) |
| `stop` / `start` | halt the coprocessor, or clear its runtime tail and release it |
| `release` | release the coprocessor directly, without `start`'s BSS/heap clear first |
| `prepare` | bring up the display clock tree without releasing the coprocessor |
| `load`/`boot <interface> <dev[:part]> <path>` | load firmware from storage, optionally starting it |
| `probe-ready` / `probe-trace [tvcap\|no-wait]` | check, or trace, readiness before starting; `probe-trace tvcap` opts into a probe known to wedge the board |

```
=> h713_mips status
```

## h713_logo - replay the vendor boot-logo register table (diagnostic)

Stock U-Boot draws its own boot logo by walking `LogoRegData.bin`, a container of 16-byte
`{address, value, mask, type}` records - masked read-modify-write, bit pulses, microsecond delays.
`h713_logo` replays or inspects a chosen range of that table directly, to understand what stock does
before reproducing the effect through `h713_disp panel-test vendor-logo`.

| Subcommand | What it does |
|---|---|
| `dump <blob-addr> <start-off> <end-off>` | print what a range of records would do, without touching hardware |
| `apply <blob-addr> <start-off> <end-off>` | actually replay that range |

```
=> h713_logo dump 0x4a800000 0x10 0x40
```

### What is inside LogoRegData.bin

The container describes itself, and the vendor kernel's `ge2d_dev.ko` and our replay now read it the
same way (`umbau/re-apps/AP3m`, part A):

| Offset | What |
|---|---|
| `0x00` | magic `logo`, version, u16 descriptor-table bytes, u16 class-table bytes, u32 bytes behind both |
| `0x10` | descriptor table, `0x18` bytes per project: project id, version, then one u16 per class |
| `0x10 + tbl` | class table, 12 bytes per class: `{class id, offset from this table, length}` |
| behind it | per class a chain of blocks `{u32 index, u32 length}`, each payload 16-byte records |

The classes are replayed **in ascending id: 0 prologue, 1 timing, 2 DE**, one block per class, and
which block is the u16 the project's descriptor holds for that class. Class 0's index-0 block is
empty, which is why the prologue variant is 1-based where the other two are 0-based. The HY310's
project `0x30` selects 1/2/0: 45 + 34 + 55 records, 113 writes, one pulse, 20 delays.

**The plane gate is one record in the DE block**: `0x0524c01c <- 0x79860601`, bit 0 set. It is the
only write to a `0x0524x01c` in either file we have, and plane 0's twin `0x0524801c` is never written
at all - so the vendor boot logo runs on OSD plane 1, and replaying the DE block is itself what opens
the plane. No separate gate write is needed.

### How to verify a panel row on a device

The vendor kernel does not take the OSD origin from the file; it reads it back out of four registers
the MIPS/TCON publishes and that nothing in either file writes (AP3m part B). They are the check that
a `h713_panel_cfg` row matches the panel actually attached:

| Register | What it holds |
|---|---|
| `0x051c0180[31:16]` | horizontal origin minus one, so `h_start = value + 1` (res_type 2) |
| `0x051c0184[31:16]` | vertical origin (res_type 2) |
| `0x051c00bc[15:0]` | a back-porch-sized horizontal count, thresholds 49 and 300 (res_type 1/6/7/8) |
| `0x051c00c0` | vertical origin for those res_types |
| `0x05140050` | the vsync-delay register the derived origin is written back into |

`h713_disp dump` stops below them, so read them by hand once the display is up:

```
=> h713_disp init 0x30 logo
=> md 0x051c0180 4
=> md 0x051c00b0 6
=> md 0x05140050 1
```

The HY310's DE block presets `hsync+hbp = 84` and `vsync+vbp = 16`, which the panel patch table
rewrites to 132 and 25 from the row. A readback that disagrees with the row accuses the row, not
the panel.

## h713_i2c - bit-banged I2C bus scan (diagnostic)

Scans TWI1's pins (PH2/PH3 by default) by bit-banging rather than bringing up a real I2C driver for a
one-off probe. On this device, `0x18` (the STK8BA58 accelerometer) is the only address that answers -
proof the bus itself works, not that anything else is missing (`doku/70-sackgassen.md`; the DLPC3435 at
`0x1b` never answers on the live panel boot, on this device or cstenger's).

| Subcommand | What it does |
|---|---|
| `scan` | scan the default pins (PH2/PH3, the vendor TWI1 pair) |
| `scan <scl> <sda>` | scan a different pair of PH pins |
| `read <addr> <count>` | read `count` bytes from `addr` with no preceding register write |

```
=> h713_i2c scan
```

Details: `mainline/external/u-boot/arch/arm/mach-sunxi/h713_mips.c`, `doku/98-mips-shell.md`,
`doku/70-sackgassen.md`.
