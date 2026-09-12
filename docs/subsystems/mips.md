# MIPS: the display coprocessor

A dedicated MIPS32 core runs the vendor firmware `display.bin` and owns everything downstream of
the video input — capture, the window chain, the scaler, panel output (the chain itself is in
[display.md](display.md)). Without it running correctly the imager shows nothing: the ARM can read
and even write the registers it owns, but only the firmware's own recalculation makes a write do
anything.

## Artifacts it needs

U-Boot loads these from the boot partition before it releases the core. None of them are computed;
all come straight from the vendor.

| File | Role |
|---|---|
| `display.bin` | the firmware image itself, 1,256,216 B on this unit (sha256 `16c74a28…`) |
| `display_cfg.xml` | runtime configuration the firmware re-reads at start (elog level, ELOG_ASYNC, panel selection) |
| `database.TSE` | shared picture-quality database |
| `pq_custom.TSE`, `projecttable.TSE` | picture-quality and per-project tables |
| `ProjectID_0x*.TSE` (13 files) | one panel/timing profile per known board; the firmware's own SHA-256 picks the right one, `h713_project` in U-Boot's environment can override it |
| `LogoRegData.bin` | 113 register records replayed before the panel comes up (32 + 26 + 55 entries, with pulses and delays) |

**None of this ships in the repo or the release image.** It is vendor material — the same files on every
device of this model, but not ours to redistribute; `h713-extract` pulls them from the user's own device
dump during installation (`doku/108`,
proven at the device 10.09.2026: files extracted, compared byte-for-byte against the source
partition, and booted from the extracted copy).

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
