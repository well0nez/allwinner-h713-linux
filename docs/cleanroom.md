# Clean-room process for the open display driver

The goal: a display path for the H713 (panel, RGB plane, then scaler, video plane and picture processing, then the
HDMI receiver without HDCP) that runs with the vendor display firmware (`display.bin`) never started, written in
Rust where the kernel's bindings allow it, and offerable to mainline Linux. The code already in this repository does
not qualify: much of the display and IPC code was written from disassembly and decompilation of vendor binaries
(audit of 02.11.2026: `h713_mips.c`, cpu_comm, decd and tvtop carry translated vendor code; afbd and hdmirx carry
register facts read from vendor binaries). So the new driver is written by people who have not seen that material.

## Two sides, one wall

| | spec side ("dirty") | wall | implementation side ("clean") |
|---|---|---|---|
| who | whoever has read this repository's `doku/`, `analyse/`, disassembly, decompiles or the existing display/IPC code - every session that worked here so far | the lead (the coordinating session) | fresh agent sessions started with only the spec workspace; never given this repository |
| reads | everything, and the device | every document that crosses | `cleanroom/spec/`, mainline Linux and its documentation, public datasheets of other SoCs, the device through the bench harness |
| writes | `cleanroom/spec/`: register maps, register state tables, measured sequences, test procedures | a log line per document handed over (`cleanroom/WALL.md`) | `cleanroom/drivers/`, its own notes and tests |

The clean workspace is a separate repository, `/srv/h713/cleanroom-h713` (not a subdirectory of this one), so a clean
session can be given that path alone.

## What may cross

- **Register maps**: address, width, field, reset value, meaning as observed ("bit 28 set: the panel shows the RGB
  channel alone").
- **Register state tables**: the values a block holds when a named, observable thing works (a picture of size W x H
  on the video plane), taken from the device. These are facts about the hardware state, not about anyone's code.
- **Measured sequences**: an order of writes proven necessary on the bench ("the commit bit only latches when written
  after the address"), with the experiment that showed it.
- **Data formats** of the owner's own vendor files the driver reads at run time (`LogoRegData.bin`, `database.TSE`),
  as layouts, not as code.
- **Test procedures** and expected results.

Every fact carries a source tag: `measured` (with the date and the measurement), `vendor-data` (read from a file on
the owner's device at run time), `public` (a document anyone can read), `binary-derived` (read out of a vendor
binary). A `binary-derived` fact crosses only after the spec side has measured it on the device and retagged it.

## What must not cross

Decompiled or disassembled code, vendor function names and addresses, the structure of vendor state machines and
call graphs, the existing driver sources of this repository, and coefficient tables copied wholesale out of a vendor
binary (a table the driver computes, or reads from the owner's own file at run time, is fine).

## The bench

The clean side does not get a shell on the device. It hands a build to the lead; the spec side installs it with the
bench harness (U-Boot `noboot`, the test FIT, the module blacklist of `doku/227` §2), runs the test procedure and hands
back the result: register reads, kernel log, and what the owner saw.

## Language

Rust where the kernel's bindings exist (platform, MMIO, clocks, IRQ, DMA, OF in 6.18). DRM/KMS and V4L2 have no Rust
bindings in 6.18; there a thin C shell registers the device and calls into the Rust hardware layer, until bindings
land upstream.

## Before anything goes upstream

The finished code is compared against the tainted sources for similarity (identifiers, structure, order of
operations beyond what the spec demands); the provenance statement says how it was made.
