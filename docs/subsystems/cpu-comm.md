# ARM ↔ MIPS communication (cpu_comm)

Linux and the MIPS display coprocessor share no memory model, no calling convention and no clock
domain of their own - `cpu_comm` is the RPC layer that bridges that gap. Nothing in normal use
calls it directly, but every HDMI source switch does, underneath `h713-tv`.

## Transport

A call travels through a shared 5 MiB DRAM region (mapped uncached, so neither side needs cache
maintenance) plus a doorbell in a small message box at `0x03003000`/`0x03003400`. The H713's
message box is edge-triggered rather than level-triggered like the H6 model this transport was
adapted from, so the sender must pulse `TX_IRQ_EN` rather than only write the message - a step our
driver initially lacked, found by comparing against a transport that already worked (`doku/65`). A
call runs `CALL → CALL_ACK → RETURN → RETURN_ACK`; it takes roughly 120 ms end to end on this board
today. A comparable port elsewhere that polls instead of using the interrupt measures 17-30 ms, and
the gap is not yet explained (`doku/67`, open item).

## The in-kernel API

`include/linux/soc/sunxi/h713-cpu-comm.h` exports four functions: `cpu_comm_call()` (blocking, up
to 10 32-bit words in and out, real error codes), `cpu_comm_register_callback()` /
`cpu_comm_unregister_callback()`, and `cpu_comm_name2id()`. A routine is addressed by a 32-bit id -
not a lookup table, but a CRC-32 over its full name (`<name>_<cpu>_<pid>`) with a fixed seed; the
kernel computes it the same way the vendor's own name-to-id routine does, confirmed against every
named entry in the reference call table (`doku/83`, checked 07.09.2026). Arguments carry no type
information: a routine that expects a buffer takes its physical address as a plain 32-bit word, and
that address has to be one the MIPS can already see.

The character devices (`/dev/cpu_comm`) that predate this API keep working unchanged and share the
same call mutex, so a kernel caller and an ioctl caller cannot race each other on the wire.

## Callbacks

The MIPS calls back into the ARM for events such as a signal change; a registered handler receives
the raw argument words on a workqueue, in process context, and must return quickly - it delays the
acknowledgement the firmware is waiting for, and it must never itself call `cpu_comm_call()`,
because that would be the same path it needs to answer on. A debugfs pair,
`/sys/kernel/debug/cpu_comm/call` and `/watch`, lets a caller exercise a named routine or watch
callback traffic without any userspace program - **in a debug build only**: the release image has
debugfs compiled out, so nothing on a shipped device can poke the coprocessor this way. Build with
`board/debug.config` to get it back (`doku/83`).

## What went wrong once, and stays fixed

For four to five source switches in a row nothing looked wrong; then the projector locked up. The
cause was a leaked reply slot: the kernel never returned the slots that MIPS→ARM callbacks used,
and after 19 callbacks - about six switches - the MIPS sender stalled waiting for a free one. The
tick stopped, the debug shell stopped answering, and every RPC failed with `-110`. Fixed by
releasing the slot once its acknowledgement is seen; verified at the device with 27 callbacks in a
single boot (`doku/96` §7, patch `0124`, 08.09.2026). A second, subtler bug lived in the same
neighbourhood: an early version of the argument adapter wrote a stray value into what turned out to
be the third output parameter, capable of landing inside the secure BL31 region for some callers -
fixed before it shipped (`doku/67`, "Argument-ABI").

Details: `doku/83-cpu-comm-api.md`, `doku/65-cpu-comm-abgleich.md`,
`doku/66-cpu-comm-arm64-bringup.md`, `doku/67-cpu-comm-linux.md`.
