# ARISC: the second coprocessor

A small OR1K core lives in the SoC's power-management domain and owns the `R_` peripheral block -
the HDMI hot-plug pin, the EDID store, and the DDC RAM behind it. The ARM cannot reach any of that
hardware on its own: reading `0x07091014` before the ARISC's firmware has initialized it hangs the
SoC hard - no oops, no console, nothing but a power cycle. That happened four times in one session
on 2026-09-06 before the rule was understood; the hardware survived every one of them
(`doku/75` run 103a-d, `doku/82` §9).

## Firmware and driver

**The choice, and the way back.** The device tree names the firmware, and the module option
`firmware=vendor|crust` of `sun50i-h713-arisc` overrides it (kernel patch `0267`): `h713-arisc set vendor`
writes it to `/etc/modprobe.d/h713-arisc.conf`, and from the next boot on the owner's `h713-arisc.bin` runs
instead of crust - no standby, a power-off through the gate - without a reinstall; `set crust` goes back.
`h713-arisc status` and the driver's state file (`firmware=`, `firmware_from=`) say which runs and why
([h713-arisc](../tools/h713-arisc.md), decision 1.1b of 10.10.2026, TODO 5.20).

Two firmwares can run here, and the board's device tree names which (`firmware-name`). On the HY310 and the
HY200 QZ713DF A1 (HY300PRO-G-EU, since kernel `0246`, measured 10.10.2026 in `doku/184`) it is **crust**, our own,
built with the image ("crust and the contract page" below). On every other board it is the vendor's (`h713-arisc.bin`, the vendor's `scp.bin`), which never ships - like the MIPS
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

Each fragment is acknowledged before the next goes out (`0091f`). The handler copies its 64 bytes out
of a scratch area the *next* command overwrites, and until `0091f` the driver waited only for the
firmware to have taken the payload, not for that copy to have finished; three module swaps in a row on
22.09.2026 were fast enough to land in the window, and the published block came out
`00 ff ff ff ff ff ff e1 fd c5 7f ...` - seven correct bytes of fragment 0, then the next command's
pattern - so the attached PC read no EDID at all. The driver now waits for the data-ready byte the
handler writes behind its copy loop. A block corrupted by an older kernel is repaired by one full
upload, which is also the first thing to check after a module swap:

```
sed -n '1p' /sys/kernel/debug/h713-arisc/edid-port0   # 000: 00 ff ff ff ff ff ff 00 5e 78 ...
echo edid > /sys/kernel/debug/h713-arisc/cmd          # if the header reads anything else
```

Which of the two a port serves is one byte of the firmware's own state, and that byte is a **per-port
bitmask, not a version number**: bit N set means port N is served the second block, bit N clear the
first. `SetEDIDVersion` masks the argument to four bits and stores it; it does not publish anything
itself (see below), so the command can serve neither as a "publish again" nor as a change that takes
effect on its own. `ResetEDIDModule` clears the byte, so after a reset every port is back on the first
block. The kernel API calls it what it is (`arisc_hdmi_edid_mask()`), and a board can set it on the
arisc node as `allwinner,edid-version-mask`; absent means 0, which is what both boards want.

**The command stores the byte, fragment 7 applies it** (HY310, 22.09.2026 -
working journal `dev20-20260922`, "Q5 mask semantics"). `edid-version 1` on its own leaves the
firmware holding 0x01 and port 0 still serving block 0: the PC reads byte 130 = 0x4c, unchanged across
a hot-plug reset too. The same value followed by a full EDID upload publishes block 1 - byte 130 =
0x54, and the source starts offering 1080p100/120. Mask 0 plus an upload brings block 0 back. So
AP3l section 1's "republishes only the ports whose bit changed" does not hold on the device: the mask
is read where fragment 7 publishes, and nowhere else.

For a bench that means a mask change needs the upload behind it, two writes to the same debugfs file:

```
echo "edid-version 1" > /sys/kernel/debug/h713-arisc/cmd
echo edid             > /sys/kernel/debug/h713-arisc/cmd
```

The same file decides whether the byte above is the firmware's answer or ours. With
`D=/sys/kernel/debug/h713-arisc`:

```
echo reset-edid       > $D/cmd; grep edid_version_mask $D/status   # 0x00 want 0x00
echo "edid-version 2" > $D/cmd; grep edid_version_mask $D/status   # 0x02 want 0x02
echo edid             > $D/cmd; grep edid_version_mask $D/status   # 0x0f want 0x02 <- the race
sed -n '9p' $D/edid-port0                                          # 128: 02 03 54 <- block 1
```

Only port 1's bit was asked for, so port 0 on block 1 (`02 03 54`) is the mask the firmware was left
holding, not the one that was sent. With `0091e` the last two lines must read `0x02 want 0x02` and
`128: 02 03 4c`.

The default 0 needs no second step - the bring-up's own fragment 7 publishes with it - which is why
the driver sends the command after fragment 7 rather than before (patch `0091c`, comment `0091d`).

One oddity is open: after the sequence with mask 1 the firmware's byte read back as 0x0f, all four
bits, where 0x01 had been asked for; with mask 0 it read 0x00. The status line carries both numbers
(`edid_version_mask: 0x0f want 0x01`), so the divergence is visible rather than silent. Whether the
handler ORs the bits or the publish path writes them is unanswered; it does not affect the default.
The disassembly says neither: the handler re-reads its argument after its own log line and the
driver's next command had already overwritten it, so the 0x0f is this driver's race and patch `0091e`
waits for the handler's effect instead - the second bench sequence above is the proof, and the
paragraph that opens this section is corrected after it, not before (Q13, working journal `Q13`).

**Block 0 is the right block on both boards, and not by default only.** Block 1 is not a newer or
better EDID, it is a different CEA extension: it adds 3840x2160p50/p60 and 4096x2160p50/p60 in 4:2:0,
1080p100/120 and a Dolby Vision block, and it *lowers* the HDMI vendor block's maximum TMDS clock from
340 MHz to 300 MHz. The four 4K50/60 modes it advertises are marked disabled in the display firmware's
own mode table, so the receiver can never lock one of them; block 0 stops exactly where that table
stops, at 4K30 / 297 MHz, which the HY310 does lock (`doku/128` §2). Advertising modes the chain
cannot carry is worse than advertising fewer. The panel is not the argument on either board - both
scale, and both firmwares lock 4K30. The mask therefore stays board policy; whoever wants block 1's
1080p100/120 in front of a source gets it without the mask, through the receiver's `S_EDID` with
that half alone (kernel `0170`, `h713-tv ctl edid block1`, [hdmi-in.md](hdmi-in.md)).

Four paths publish, and it is worth knowing which: the firmware's own init, the tail of `HostHDMIMAP`
(writing the port map republishes all three ports as a side effect), `ResetEDIDModule`, and
`UpdateEDID` fragment 7. `SetEDIDVersion` was read as a fifth out of the dispatcher and is not one on
the device (above). None of them moves the hot-plug pin - a publish rewrites the DDC RAM,
and making a source re-read it is the separate hot-plug pulse. The cheapest repeatable re-publish is
therefore `HostHDMIMAP`, which the driver already sends.

### Corrections

Four readings this page and `doku/82` carried that the firmware's own code contradicts
(working journal `AP3l` §2):

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

## crust and the contract page

[crust](https://github.com/crust-firmware/crust) is free firmware for this core; `crust-h713/` carries
our port. It speaks the vendor's message contract - the startup handshake, the HDMI subcommands, the
display MIPS's frames - so the kernel API above works the same with it, and it adds the standby
([standby.md](standby.md)). It ran on the HY310 on 07.10.2026: HDMI, EDID, hot plug and the MIPS's
frames as with the vendor's firmware, then started by BL31, then the first standby cycles (`doku/163` -
`doku/167`). Three things are different:

- **Who starts it.** BL31 starts crust at every boot from the FIT's `scp` image, before U-Boot proper.
  The driver finds it running and keeps it when the file its device tree names (`hy310-crust.bin`, our
  build, in `/lib/firmware` of the image) is the same image; a different or a vendor file is loaded over
  it, with a warning. FIT and file come from one build, and `release/check-crust.py` refuses an image
  where they differ.
- **The contract page.** 1 KiB in SRAM A2 (ARM `0x00123800`), in which crust, BL31 and Linux each own
  their words. Version 4 is what ran on the device; version 5 adds what a release needs and has not run
  yet. Its one table is crust's `platform/h713/include/platform/memory.h`; the kernel's and BL31's
  offsets are checked against it.

  | Range | Class | Written by |
  |---|---|---|
  | `+0x000` - `+0x1ff` | R: magic, version, status with heartbeat, wake word, the HDMI state | crust, cleared at its every start - after a restart the kernel acknowledged, except the HDMI state at `+0x010` - `+0x0ff` |
  | `+0x200` - `+0x23f` | D: diagnosis - starts, last step, last exception, sleep length, the build word at `+0x23c` | crust; kept across its restarts |
  | `+0x240` - `+0x25f` | S: what one start saw | crust |
  | `+0x260` - `+0x2bf` | K: compatibility, standby phase, cycle, budgets, error bits, counters, the wake word until the kernel has asked for it | crust only; kept across its restarts |
  | `+0x2c0` - `+0x2cf` | A: the kernel's standby request and confirm, BL31's last event | one ARM writer per word |
  | `+0x2d0` - `+0x38f` | P: BL31's or the kernel's copy of the record of crust's last run | the ARM only |

  A reader takes the page when the magic is right, the version is at least the one it needs and crust's
  compatibility word is not above the one it knows; else it refuses aloud instead of reading wrong.
- **What it is built as.** The build word says the variant: bit 24 DRAM self-refresh, 26 the IR wake
  codes, and 25, 27, 28, 31 for deep sleep and its steps, 29 the sleep net, 30 a test build. A release
  carries self-refresh (`h713_hy310_sr_defconfig`); the build gate refuses 25, 27, 28, 30 and 31, 29
  until its watchdog is measured, and the DRAM checksum of the test image (`h713_hy310_sr_test_defconfig`)
  until the device stages show it raises no false alarm. The driver's `state` file shows version, build word, standby phase,
  last wake and the error bits, read without disturbing the firmware.

## What it does not do

Everything here is polled, not interrupt-driven - the firmware's main loop checks its inbound
channels itself, so the driver sends no doorbell. Boot0 gates the core's clocks on the way up. Under
the vendor's firmware nothing here drives power management: our TF-A does not speak the vendor's SCPI
protocol to it (`doku/68`); the standby runs only with crust ([standby.md](standby.md)). HDCP key handling is a separate path through secure storage and
the MIPS, unrelated to this core. And `remove()` deliberately leaves the reset alone - pulling it
would drop the hot-plug pin under a live HDMI input - so recovering from a bad module load means
reloading the firmware, not just unbinding it.

Details: `doku/82-arisc-treiber.md`, `doku/68-stock-extraktion-arisc-hdcp.md`,
`doku/00-STATUS.md`.
