# MIPS: the display coprocessor

A dedicated MIPS32 core runs the vendor firmware `display.bin` and owns everything downstream of
the video input — capture, the window chain, the scaler, panel output (the chain itself is in
[display.md](display.md)). Without it running correctly the imager shows nothing: the ARM can read
and even write the registers it owns, but only the firmware's own recalculation makes a write do
anything.

## Artifacts it needs

Our U-Boot loads these before it releases the core; which partition they come from depends on the
board (below). None of them are computed; all come straight from the vendor.

| File | Role |
|---|---|
| `display.bin` | the firmware image itself, 1,256,216 B on this unit (sha256 `16c74a28…`) |
| `display_cfg.xml` | runtime configuration the firmware re-reads at start (elog level, ELOG_ASYNC, panel selection) |
| `database.TSE` | shared picture-quality database |
| `pq_custom.TSE`, `projecttable.TSE` | picture-quality and per-project tables |
| `ProjectID_0x*.TSE` (13 files) | one panel/timing profile per known board; the **declared project id** picks the file — `h713_project` in U-Boot's environment, else `panel_config.ini` (below) |
| `LogoRegData.bin` | 113 register records replayed before the panel comes up (32 + 26 + 55 entries, with pulses and delays) |

**None of this ships in the repo or the release image.** It is vendor material — the same files on every
device of this model, but not ours to redistribute; `h713-extract` pulls them from the user's own device
dump during installation (`doku/108`,
proven at the device 10.09.2026: files extracted, compared byte-for-byte against the source
partition, and booted from the extracted copy).

### They live in one of two places

There is no single vendor location; which one a device uses follows its U-Boot — read out of the
three stock images and out of the vendor U-Boot's own loader (`doku/121` §2, finding 2):

- **`bootloader_a` / `bootloader_b`** — a FAT16 partition with a `mips/` directory. The HY310's case,
  and the HY300 Pro's: their U-Boot reads the files itself, addressing the partition by **name plus
  the A/B slot out of `misc`**, never by index. A device this port was installed on keeps the same
  files on `hy310-boot`.
- **`/vendor/etc/display/mips/`** — inside the `vendor` logical partition of `super`. The HY300 T08's
  case and the HY350's: their U-Boot contains none of the loading code at all, so the 19 files are
  uploaded from Android after `/vendor` is mounted. On such a board, "no `mips/` in the bootloader
  partition" is the normal state and not a fault.

A dump therefore takes `Reserve0` and `media_data` (`/oem`) as well: a device can carry per-unit
overrides of the TSE group and of `panel_config.ini` there, and both the vendor's U-Boot and its
userspace read those **before** the bootloader partition.

### One `display.bin`, two panels

The firmware image does not name a board. `22a7df11…` is the firmware of the 720p HY300 T08 *and* of
the 1080p HY350 (`doku/121` §2, finding 3). What a digest does pin down is a revision — its size and
the address of the HDCP key-wait loop inside it — and that is all our firmware table claims.

The panel comes from the **declared project id**: `ProjectID = 48` (0x30) or `52` (0x34), written in
decimal in `panel_config.ini`, which the vendor keeps on `Reserve0` and mirrors to `media_data`. Our
U-Boot resolves it the same way — `h713_project` from the environment, which the installer writes at
install time from the device's own file, otherwise the file itself, found by partition name. 0x30 is
1920×1080 dual-port, 0x34 is 1280×720 single-port. An id fixes the resolution and not the blanking:
the HY350 declares 0x30 like the HY310 and asks for a different raster, which is why a board nobody
has driven gets a profile and not a panel row.

## Starting it

`h713_disp init <project-id> [elog=<0-5>]` does the rest: apply clocks and panel routing, write the
panel configuration (22 register fields, 12 of them behind a record mask), replay the logo records,
sequence panel power (550 ms lead-in, then two GPIOs), verify the firmware's identity, defuse an
HDCP wait loop that would otherwise hang forever this early in boot (interrupts aren't live yet),
build the shared-memory structures `cpu_comm` needs (spinlocks, call table, semaphores), and release
the coprocessor through four reset stages. A boot that got this far reports
`CPU_COMM magic=deadbeef/deadbeef ARM=00000005 MIPS=00000005` and `application readiness proven`
(`doku/40`, device log). **`init` only runs once per power cycle** — a warm restart reaches the
prompt again but leaves the display blocks gated and the coprocessor dead.

## What the vendor's own stack does at runtime

Read off the vendor kernel, not measured on our build: `sunxi-mipsloader` in the HY310's stock kernel
5.4.99 (`drivers/misc/sunxi-tvutils/mipsloader.c`, disassembled offline together with `libmips.so`
and `/vendor/bin/loadmips`).

- **The kernel driver never loads firmware.** `mipsloader_probe()` has no `request_firmware`, no file
  access and no DMA of an image. It maps the reserved window, claims the three reset lines and the
  two clocks, and then assumes the core is already running — which on an HY310 it is, because U-Boot
  started it during the boot logo.
- **Uploading is `mmap` on `/dev/mipsloader`**, followed by one ioctl pair: `0x10648` with
  `{type, offset}`, where type 0 stops the core, 1 starts it at `offset`, 2 powers it down. The other
  ioctl, `0x648`, the driver refuses itself with "use mmap instead".
- **Resume leaves the core paused.** `mipsloader_resume()` runs the reset ladder and restores the two
  share-memory registers from the driver's own copy, and stops there: clocks on, soft reset asserted,
  boot address not rewritten. Userspace has to issue the start ioctl afterwards. Nothing re-uploads
  the image — Linux never writes into the reserved window, which is why a power-down and up needs no
  reload at all.

None of this runs on our build: our kernel drives the panel through its own KMS driver, and U-Boot is
the only thing that ever starts the core. It matters for two roadmap items — reloading the firmware
at runtime and deep sleep — and for anyone who boots a vendor kernel with our U-Boot.

## The onboard log (elog)

The firmware keeps its own log, and it does not reach a UART: every mode writes into a ring buffer
in DRAM, and the mode is one byte at `0x8B48BE9B`. Mode 1, the one this firmware uses, is a 100 KiB ring;
nothing overwrites old entries — once it fills, the firmware simply stops writing. Reading it needs
a consumer that advances the read pointer (`tools/mipslog.c`: `dump` for the boot history without
moving the pointer, `tail` for a live, destructive read) — **run `dump` before `tail`**.

A one-byte global level gates verbosity; the release image ships the boot default, level 1 (errors
only, about 1.9 KB in a typical run). Raising it — `elog=<level>` at `init`, or writing the level byte at
`0x4b48bd9c` from Linux at runtime — only makes sense with a consumer already running
(the reader lives in the working tree, not in this repository: `tools/mipslog.c` builds one): without one, a higher level fills the ring in seconds and the log
goes dead exactly when a fault would need it (`doku/63`, measured 01.09. and 06.09.2026). **Mode 2
must stay off** — turning it on is recorded as breaking MIPS init, a note from the working
knowledge base, unverified beyond that note itself.

## Its own debug shell

The same firmware runs a command shell on two threads: one on UART4, whose pins this board does not
expose, and one over a ring buffer in DRAM that the ARM side can reach — verified at the device
07.09.2026 with a helper that is not part of this repository (`doku/98` describes the protocol). The command scaffolding (`help`, the
prompt) answers over that ring; the body of most commands — `win wm`, `hal dump_src`, `app
dump_cfg` — prints into the elog instead, so both channels have to be read together. Command groups
include `app`, `win`, `crtc`, `hal`, `tcd3`, `dtv`, `memory_agent`, `pq`, plus raw `regr`/`regw` for
the firmware's own view of the register bus.

Read-only subcommands (`dump_*`, `wi`, `wm`) are safe to run at any time. `set_*`, `*_on`/`*_off`
and `regw` change what is on screen right now — use them only with eyes on the projector and a way
back: a source switch, or, if that alone does not clear it, a full power cycle followed by one.

Details: `doku/63-mips-elog.md`, `doku/98-mips-shell.md`, `doku/96-anzeigekette.md`,
`doku/108-plan-vendordaten.md`, `doku/40-display.md`.
