# MIPS: the display coprocessor

A dedicated MIPS32 core runs the vendor firmware `display.bin` and owns everything downstream of
the video input - capture, the window chain, the scaler, panel output (the chain itself is in
[display.md](display.md)). Without it running correctly the imager shows nothing: the ARM can read
and even write the registers it owns, but only the firmware's own recalculation makes a write do
anything. U-Boot starts the core at boot; since 09.10.2026 Linux can park it for a standby and start
it again ([Restarting it from Linux](#restarting-it-from-linux)).

## Artifacts it needs

Our U-Boot loads these before it releases the core; which partition they come from depends on the
board (below). None of them are computed; all come straight from the vendor.

| File | Role |
|---|---|
| `display.bin` | the firmware image itself, 1,256,216 B on this unit (sha256 `16c74a28…`) |
| `display_cfg.xml` | runtime configuration the firmware re-reads at start (elog level, ELOG_ASYNC, panel selection) |
| `database.TSE` | shared picture-quality database |
| `pq_custom.TSE`, `projecttable.TSE` | picture-quality and per-project tables |
| `ProjectID_0x*.TSE` (13 files) | one panel/timing profile per known board; the **declared project id** picks the file - `h713_project` in U-Boot's environment, else `panel_config.ini` (below) |
| `LogoRegData.bin` | the register records replayed before the panel comes up (HY310: 113 in three groups of 32 + 26 + 55, with pulses and delays). The group boundaries are read out of the container since 16.09.2026 - another board's file has a different descriptor count, and fixed HY310 offsets ran past its end (HY300 Pro, issue #1) - and since 22.09.2026 out of the container's own class table rather than inferred from the block numbering, the way the vendor kernel reads it (`docs/uboot/commands.md`) |

**None of this ships in the repo or the release image.** It is vendor material - the same files on every
device of this model, but not ours to redistribute; `h713-extract` pulls them from the user's own device
dump during installation (`doku/108`,
proven at the device 10.09.2026: files extracted, compared byte-for-byte against the source
partition, and booted from the extracted copy).

### They live in one of two places

There is no single vendor location; which one a device uses follows its U-Boot - read out of the
three stock images and out of the vendor U-Boot's own loader (`doku/121` §2, finding 2):

- **`bootloader_a` / `bootloader_b`** - a FAT16 partition with a `mips/` directory. The HY310's case,
  and the HY300 Pro's: their U-Boot reads the files itself, addressing the partition by **name plus
  the A/B slot out of `misc`**, never by index. A device this port was installed on keeps the same
  files on `hy310-boot`.
- **`/vendor/etc/display/mips/`** - inside the `vendor` logical partition of `super`. The HY300 T08's
  case and the HY350's: their U-Boot contains none of the loading code at all, so the 19 files are
  uploaded from Android after `/vendor` is mounted. On such a board, "no `mips/` in the bootloader
  partition" is the normal state and not a fault.

A dump therefore takes `Reserve0` and `media_data` (`/oem`) as well: a device can carry per-unit
overrides of the TSE group and of `panel_config.ini` there, and both the vendor's U-Boot and its
userspace read those **before** the bootloader partition.

### One `display.bin`, two panels

The firmware image does not name a board. `22a7df11…` is the firmware of the 720p HY300 T08 *and* of
the 1080p HY350 (`doku/121` §2, finding 3). What a digest does pin down is a revision - its size and
the address of the HDCP key-wait loop inside it - and that is all our firmware table claims.

The panel comes from the **declared project id**: `ProjectID = 48` (0x30) or `52` (0x34), written in
decimal in `panel_config.ini`, which the vendor keeps on `Reserve0` and mirrors to `media_data`. Our
U-Boot resolves it the same way - `h713_project` from the environment, which the installer writes at
install time from the device's own file, otherwise the file itself, found by partition name. 0x30 is
1920×1080 dual-port, 0x34 is 1280×720 single-port. An id fixes the resolution and not the blanking:
the HY350 declares 0x30 like the HY310 and asks for a different raster, which is why a board nobody
has driven gets a profile and not a panel row.

## Starting it

`h713_disp init <project-id> [elog=<0-5>] [logo [file.bmp]]` does the rest: apply clocks and panel routing, write the
panel configuration (22 register fields, 12 of them behind a record mask), replay the logo records,
sequence panel power (550 ms lead-in, then two GPIOs), verify the firmware's identity, defuse an
HDCP wait loop that would otherwise hang forever this early in boot (interrupts aren't live yet),
build the shared-memory structures `cpu_comm` needs (spinlocks, call table, semaphores), and release
the coprocessor through four reset stages. A boot that got this far reports
`CPU_COMM magic=deadbeef/deadbeef ARM=00000005 MIPS=00000005` and `application readiness proven`
(`doku/40`, device log). **`init` only runs once per power cycle** - a warm restart reaches the
prompt again but leaves the display blocks gated and the coprocessor dead. That is U-Boot's command;
once Linux runs, the core is started again by the driver described next.

## What the vendor's own stack does at runtime

Read off the vendor kernel, not measured on our build: `sunxi-mipsloader` in the HY310's stock kernel
5.4.99 (`drivers/misc/sunxi-tvutils/mipsloader.c`, disassembled offline together with `libmips.so`
and `/vendor/bin/loadmips`).

- **The kernel driver never loads firmware.** `mipsloader_probe()` has no `request_firmware`, no file
  access and no DMA of an image. It maps the reserved window, claims the three reset lines and the
  two clocks, and then assumes the core is already running - which on an HY310 it is, because U-Boot
  started it during the boot logo.
- **Uploading is `mmap` on `/dev/mipsloader`**, followed by one ioctl pair: `0x10648` with
  `{type, offset}`, where type 0 stops the core, 1 starts it at `offset`, 2 powers it down. The other
  ioctl, `0x648`, the driver refuses itself with "use mmap instead".
- **Resume leaves the core paused.** `mipsloader_resume()` runs the reset ladder and restores the two
  share-memory registers from the driver's own copy, and stops there: clocks on, soft reset asserted,
  boot address not rewritten. Userspace has to issue the start ioctl afterwards. The kernel does not
  re-upload the image either, but the vendor restarts the display firmware, reloaded, on every
  screen-on, standby included (`doku/133`, 27.09.2026). *Superseded:* the earlier reading here that
  a power-down and up needs no reload at all, because Linux never writes into the reserved window.
  Our restart always loads `display.bin` again; whether the reset ladder alone would do is not
  measured.

None of this runs on our build: our kernel drives the panel through its own KMS driver, and the
vendor's halt and start are repeated, write for write, by `sun50i-h713-mips` (below). It still
matters for anyone who boots a vendor kernel with our U-Boot.

## Restarting it from Linux

Until 08.10.2026 only U-Boot could start the core, so a standby would have cost a reboot. The driver
`sun50i-h713-mips` (patches `0231`, `0232`) loads `display.bin` into the window U-Boot used and starts
the core again, from a running core or out of the standby park. It is the one owner of the core's
clock `0x02001600` and reset word `0x0200160c`, written raw as U-Boot does (no clock-framework
consumer exists), and [cpu_comm](cpu-comm.md) parks the core for a standby through it. The node
`mips@3061000` has the MIPS block, the clock and reset words, the TV top (`0x06e00000`) and, since `0245`, the
power gate's word (RTC GP5, `0x07090114`, below) as its four regs, and the reserved window `mips-firmware@4b100000`. It is disabled in the dtsi and enabled
on the HY310 and, since `0246`, on the HY200 QZ713DF A1 (HY300PRO-G-EU), where the restart was measured;
the HY300 Pro tree switches it off again (`0232`).

**A board with an LCD panel needs the panel's supply cycled after a restart.** On the HY300PRO-G-EU every
reload ended black - firmware ready, picture path up, lamp on, wall dark (03.10.2026, `doku/138`; again on
09.10.2026 with this driver, seven of seven). The board's LCD panel has its own timing controller; when the
firmware starts again, the panel loses its LVDS lock and takes it again only after a power cycle. A reset
pulse alone does not bring it back; the HY310's DLP bridge locks again on its own (`doku/182`). So the
driver takes two optional GPIOs from the node, `panel-power-gpios` and `panel-reset-gpios`, requested as
U-Boot left them, and after every start that reports ready it switches the panel off for 300 ms and on
again, waits 20 ms and pulses the reset for 2 ms - what U-Boot does at boot (`0248`; dmesg `panel supply
cycled (300 ms off), reset pulsed`). Only boards whose tree names the pins get it: the HY200 QZ713DF A1
names PF6 (supply, active high) and PH16 (reset, active low). PF6 was missing from the H713 pin table
(bank F knew PF0-PF5 only, `0247`); without it the probe waits with -517 and the driver does not bind at
all. Measured on 10.10.2026: three reloads, three after a standby, picture back 3.4 s after each reload
(`doku/184`).

**Interface.** In `/sys/bus/platform/drivers/sun50i-h713-mips/<device>/`:

- `state` (read): `running`, `halted` (core held), `parked` (reset word 0) or `failed` on the
  first line, derived from the registers; the second line has the two CCU words, and the MIPS block's
  status and boot address only when its gate is on and the bus reset released (`not-read` otherwise).
- `restart` (write): the path of a `display.bin`, `-` or nothing for `/boot/mips/display.bin`. It
  returns 0 or the error; a failure leaves `halted` or `failed` with a warning, and the next write
  starts over from there. The driver does not touch the HDMI receiver, which has to be unbound around
  the write: [h713-mips-restart](../tools/h713-mips-restart.md) does that, and `h713-power` runs it
  after every standby.

| Started from | before the load | the start |
| --- | --- | --- |
| `running` | the vendor's `mips_reset()`: bus, soft and cold resets go, the bus reset returns, the gate is off around the cold reset, 20 us steps, soft reset held (ends `0x00030001`) | vendor: boot address, 20 us, `0x00070001` |
| `parked` | nothing | U-Boot's: TV top step (below), clock `0x80000002`, resets `0`, `0x10000`, `0x30000`, `0x30001` at 12 ms each, boot address, `0x00070001` |
| `halted` | nothing | vendor start |
| `failed` | park first (reset 0, 12 ms, clock 0, 12 ms) | as `parked` |

Without a halt or park the start type follows the registers, not what the driver remembers (`0235`).
The load is the vendor's: the file is read whole (64 KiB to 5 MiB, a multiple of 4), the HDCP 1.4 key
wait defused as U-Boot does at boot (exactly one loop bound, or the file is refused), the soft reset
checked held, the code block up to `0xd01000` zeroed, the image copied and compared back; what U-Boot
put behind it stays. `cpu_comm` rebuilds its shared region with the core held, and after the release
the driver waits up to 10 s, U-Boot's budget, for the firmware's READY: about 300 ms in practice.

**The TV top.** A standby powers the TVFE and TVCAP domains off and on, and the TV top's three words
at `0x06e00000` come back as `0x10, 0, 0` instead of U-Boot's `0x00111111`, `0x01111117`, `0x404`.
U-Boot writes them before it starts the core (`h713_disp_clocks()`). A core started without them
stalled the whole SoC within 200 ms - no heartbeat, no RCU report, the watchdog reset the box 14 s
later - in 3 of 3 restarts after a real standby; a park without a sleep and a running core never
showed it (`doku/172` §1, §2, §4; `0239`). The start out of the park therefore repeats U-Boot's step
when the words are not U-Boot's - +4, +8, +0, all three 0, the three again, 12 ms apart - and logs
"TV top in place" when they are (`0239`). Without the third reg the start is refused and the core
stays `parked` (`0242`), a refusal being better than a stalled bus. The HDMI receiver's LINK window
lies in the same TV blocks, which fits the hang of every LINK read after a standby seen on
08.10.2026 (`doku/176` §2, `doku/172` §2).

**The gate word.** From the start of a standby until the core runs again, the driver keeps the power gate's
word at "STBY" instead of U-Boot's "RUN1" (`0245`): a PM notifier turns "RUN1" into "STBY" at
PM_SUSPEND_PREPARE, a start that ends ready turns it back, and so does the end of a sleep that parked nothing
and a `reboot` from Linux. A reset in between - a hang going to sleep or waking up, or a core that stalls the bus
at its start - lands in U-Boot's gate, dark, instead of booting with the lamp on ([power-gate.md](../uboot/power-gate.md),
`doku/179`). Without the fourth reg the driver says so at probe and leaves the word alone.

Measured on the HY310: a test bench with the same sequences brought the picture back on 08.10.2026
from a running core and from the park register state set by hand (V3, V8; `doku/176` §1 - the commit text
of `0231` also names three runs in a row, V10, which no capture backs); the TV top step by hand, then the restart: ready after 290 ms, picture back after
3955 ms; the driver, six standbys with a restart each in one boot, 6 of 6 with the picture back
(`doku/172` §2, §4), and 30 of 30 in a fast loop (`doku/173` §4). Not measured: HDCP 2.2 from a
source after a restart (`doku/172` §5, `doku/174` §3).

## The onboard log (elog)

The firmware keeps its own log, and it does not reach a UART: every mode writes into a ring buffer
in DRAM, and the mode is one byte at `0x8B48BE9B`. Mode 1, the one this firmware uses, is a 100 KiB ring;
nothing overwrites old entries - once it fills, the firmware simply stops writing. Reading it needs
a consumer that advances the read pointer (`tools/mipslog.c`: `dump` for the boot history without
moving the pointer, `tail` for a live, destructive read) - **run `dump` before `tail`**.

A one-byte global level gates verbosity; the release image ships the boot default, level 1 (errors
only, about 1.9 KB in a typical run). Raising it - `elog=<level>` at `init`, or writing the level byte at
`0x4b48bd9c` from Linux at runtime - only makes sense with a consumer already running
(`tools/mipslog.c` in this repository builds one): without one, a higher level fills the ring in seconds and the log
goes dead exactly when a fault would need it (`doku/63`, measured 01.09. and 06.09.2026). **Mode 2
must stay off** - turning it on is recorded as breaking MIPS init, a note from the working
knowledge base, unverified beyond that note itself.

## Its own debug shell

The same firmware runs a command shell on two threads: one on UART4, whose pins this board does not
expose, and one over a ring buffer in DRAM that the ARM side can reach - verified at the device
07.09.2026 with a helper that is not part of this repository (`doku/98` describes the protocol). The command scaffolding (`help`, the
prompt) answers over that ring; the body of most commands - `win wm`, `hal dump_src`, `app
dump_cfg` - prints into the elog instead, so both channels have to be read together. Command groups
include `app`, `win`, `crtc`, `hal`, `tcd3`, `dtv`, `memory_agent`, `pq`, plus raw `regr`/`regw` for
the firmware's own view of the register bus.

Read-only subcommands (`dump_*`, `wi`, `wm`) are safe to run at any time. `set_*`, `*_on`/`*_off`
and `regw` change what is on screen right now - use them only with eyes on the projector and a way
back: a source switch, or, if that alone does not clear it, a full power cycle followed by one.

Details: `doku/63-mips-elog.md`, `doku/98-mips-shell.md`, `doku/96-anzeigekette.md`,
`doku/108-plan-vendordaten.md`, `doku/40-display.md`; the restart in `doku/172` - `doku/174`,
the park in [cpu-comm.md](cpu-comm.md) and [standby.md](standby.md).
