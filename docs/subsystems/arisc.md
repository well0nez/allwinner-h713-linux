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
API: reset the EDID module, set the port map, write or read back an EDID block, choose which of the
firmware's two EDID blocks each port is served, pulse hot-plug up/down/reset, and two commands (5 V
flag, audio mode) that this firmware accepts but does not act on. The same operations are reachable
from `/sys/kernel/debug/h713-arisc/` in a **debug build**; the release image has debugfs compiled out.
`edid-port0` there reads back all 256 bytes port 0 actually publishes, which is the only readback that
can tell the two blocks apart - they are identical for their first 130 bytes.

## The EDID it publishes, and the byte that chooses a block

`hy310-edid.bin` is two 256-byte EDIDs back to back, and the firmware keeps both: the driver uploads
all eight 64-byte fragments, 0-3 landing in the firmware's first block and 4-7 in its second. Only
fragment 7 sets the data-ready flag and publishes, so the two halves cannot be uploaded separately.

Which of the two a port serves is one byte of the firmware's own state, and that byte is a **per-port
bitmask, not a version number**: bit N set means port N is served the second block, bit N clear the
first. `SetEDIDVersion` masks the argument to four bits, stores it and republishes only the ports
whose bit changed - an unchanged value publishes nothing at all, so the command cannot serve as a
"publish again". `ResetEDIDModule` clears the byte, so after a reset every port is back on the first
block. The kernel API calls it what it is (`arisc_hdmi_edid_mask()`), and a board can set it on the
arisc node as `allwinner,edid-version-mask`; absent means 0, which is what both boards want.

**Block 0 is the right block on both boards, and not by default only.** Block 1 is not a newer or
better EDID, it is a different CEA extension: it adds 3840x2160p50/p60 and 4096x2160p50/p60 in 4:2:0,
1080p100/120 and a Dolby Vision block, and it *lowers* the HDMI vendor block's maximum TMDS clock from
340 MHz to 300 MHz. The four 4K50/60 modes it advertises are marked disabled in the display firmware's
own mode table, so the receiver can never lock one of them; block 0 stops exactly where that table
stops, at 4K30 / 297 MHz, which the HY310 does lock (`doku/128` §2). Advertising modes the chain
cannot carry is worse than advertising fewer. The panel is not the argument on either board - both
scale, and both firmwares lock 4K30.

Five paths publish, and it is worth knowing which: the firmware's own init, the tail of `HostHDMIMAP`
(writing the port map republishes all three ports as a side effect), `ResetEDIDModule`, `UpdateEDID`
fragment 7, and `SetEDIDVersion`. None of them moves the hot-plug pin - a publish rewrites the DDC RAM,
and making a source re-read it is the separate hot-plug pulse. The cheapest repeatable re-publish is
therefore `HostHDMIMAP`, which the driver already sends.

### Corrections

Four readings this page and `doku/82` carried that the firmware's own code contradicts
(`umbau/re-apps/AP3l/` §2):

- The register the publish routine moves around each block write is the **EDID/DDC output gate**, not
  a hot-plug pulse; the pin is a different register driven by a different routine. The gate moves only
  when the published mask contains the port whose pin number is 0, and then it moves all three ports.
- Reading the EDID back (`RequestEDID`) **closes that gate for the duration of the read**, on all
  three ports. Harmless inside the bring-up sequence, worth knowing for a read used as a check
  afterwards.
- The firmware does not blank EDID byte 168. It searches the CEA data block collection for the HDMI
  vendor block and writes the port's own physical-address byte, taken from that port's port map
  record, at the vendor block's fifth byte, then recomputes the extension checksum in byte 255. Those
  two bytes are the whole difference between the file and what a source reads.
- The "output EDID" sub-command is a debug dump of the DDC RAM into the firmware's own log, not a
  re-publish; it never reaches the publish routine.

One more the driver has to live with: the display co-processor has a message channel of its own into
this firmware and can trigger `ResetEDIDModule` behind the driver's back, which would clear the mask
and the published EDID. Nothing we load is known to send it; it is on the open list.

## Timing

| Step | Measured |
|---|---|
| Full EDID + hot-plug sequence, cold firmware to `connected` | **17.65 s** (`doku/82` §8, device-verified 07.09.2026) |
| Hot-plug low pulse | 200 ms, measured on the device (`doku/nachtlog/A2-hpd-dauer-edid.md`); the vendor's `SetHPDTimeInterval 0xC8` is **not** a second source for it - that call goes to the MIPS receiver over `cpu_comm`, not to this core |

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
