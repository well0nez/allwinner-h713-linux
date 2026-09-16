# ARISC: the second coprocessor

A small OR1K core lives in the SoC's power-management domain and owns the `R_` peripheral block -
the HDMI hot-plug pin, the EDID store, and the DDC RAM behind it. The ARM cannot reach any of that
hardware on its own: reading `0x07091014` before the ARISC's firmware has initialized it hangs the
SoC hard - no oops, no console, nothing but a power cycle. That happened four times in one session
on 2026-09-06 before the rule was understood; the hardware survived every one of them
(`doku/75` run 103a-d, `doku/82` §9).

## Firmware and driver

The firmware (`h713-arisc.bin`, the vendor's `scp.bin`) never ships either - like the MIPS
artifacts in [mips.md](mips.md), it comes from the user's own device dump via `h713-extract`. The
driver, `sun50i-h713-arisc`, loads it into SRAM, releases the core's reset, and then must complete
a startup handshake before the firmware services anything at all - a notification on one channel,
an acknowledgement expected back on another, both checked by type and result code, not assumed
(`doku/82` §4, measured across six boots).

The driver also reads and writes a handful of the firmware's own variables in that SRAM: the
hot-plug counters, the two EDID flags, the port map, the buffer the firmware's receive pump takes
commands out of. Those addresses are not fixed. The firmware keeps its state wherever its own build
happened to put it, and every board's dump carries a different build - the HY300 Pro's is seven
months older than the HY310's and has the same data 0x340 bytes lower. So the driver reads the eight
addresses it needs out of the image at probe time: two signatures over the firmware's own code give
two anchors, the other six are fixed distances from them, two more signatures cross-check the
arithmetic against the firmware's own layout, and the image's BSS clear loop and stack-pointer init
give the bound above which nothing may be written. An image whose layout cannot be established that
way is not loaded at all - the probe refuses and names the step that failed, because an ARISC
started with a guessed address set writes into its own stack and answers nothing but a timeout
(`doku/126`, issue #1). The image's version string and the resolved addresses appear in the debugfs
status file, and `tools/arisc-fw-addrs.py` prints the same table for a dump on the host.

Once that handshake is done, the driver exposes the firmware's HDMI subcommands as a small kernel
API: reset the EDID module, set the port map, write or read back an EDID block, pulse hot-plug
up/down/reset, and two commands (5 V flag, audio mode) that this firmware accepts but does not act
on. The same operations are reachable from `/sys/kernel/debug/h713-arisc/` in a **debug build**;
the release image has debugfs compiled out.

## Timing

| Step | Measured |
|---|---|
| Full EDID + hot-plug sequence, cold firmware to `connected` | **17.65 s** (`doku/82` §8, device-verified 07.09.2026) |
| Hot-plug low pulse | 200 ms, matching the vendor's own `SetHPDTimeInterval 0xC8` |

The handshake has to finish before anything touches the `R_` block, and the driver enforces this
structurally rather than by convention: it maps none of `0x0709xxxx` itself, and every other entry
point returns `-EAGAIN` until a successful reset has set an internal "module ready" flag.

## What it does not do

Everything here is polled, not interrupt-driven - the firmware's main loop checks its inbound
channels itself, so the driver sends no doorbell. Boot0 gates the core's clocks on the way up, but
nothing here drives real power management: our TF-A does not speak the vendor's SCPI protocol to
it (`doku/68`), and an ARISC-backed deep-sleep stage is a parked, low-priority plan, not built
(`doku/00-STATUS.md`, plan `104`). HDCP key handling is a separate path through secure storage and
the MIPS, unrelated to this core. And `remove()` deliberately leaves the reset alone - pulling it
would drop the hot-plug pin under a live HDMI input - so recovering from a bad module load means
reloading the firmware, not just unbinding it.

Details: `doku/82-arisc-treiber.md`, `doku/68-stock-extraktion-arisc-hdcp.md`,
`doku/00-STATUS.md`.
