# ARM ↔ MIPS communication (cpu_comm)

Linux and the MIPS display coprocessor share no memory model, no calling convention and no clock
domain of their own - `cpu_comm` is the RPC layer that bridges that gap. Nothing in normal use
calls it directly, but every HDMI source switch does, underneath `h713-tv`.

## Transport

A call travels through a shared 5 MiB DRAM region (mapped uncached, so neither side needs cache
maintenance) plus a doorbell in a small message box at `0x03003000`/`0x03003400`. Our driver
pulses `TX_IRQ_EN` after writing the message, on the reading that the H713 box is edge-triggered
rather than level-triggered like the H6 model this transport was adapted from (`doku/65`). The
vendor kernel does not do that: there `TX_IRQ_EN` is a level meaning "I have bytes to push", set
before the transfer and cleared by the interrupt handler when the buffer is drained, and the
receiver's doorbell is the FIFO write itself. Which of the two this chip needs is open; it takes
one device run, named in patch `0014f`. A call runs `CALL → CALL_ACK → RETURN → RETURN_ACK`; it
takes roughly 120 ms end to end on this board today. A comparable port elsewhere that polls
instead of using the interrupt measures 17-30 ms, and the gap is not yet explained (`doku/67`,
open item).

### The five registers the link is made of

Two blocks, both named by the board's own stock device tree: `msgbox@3003000` (three banks of
`0x400`, one inbox per core) and `hwspinlock@3004000` (32 locks, of which `cpu_comm` takes
hardware ids 8..21). Inside the message box the ARM ↔ MIPS pair uses five registers, derived from
the vendor driver's own address arithmetic and confirmed against the stock device tree:

| address | what it is |
| --- | --- |
| `0x03003830` | `TX_IRQ_EN`, `BIT(2 * port + 1)` - MIPS is port 1, so `BIT(3)` |
| `0x03003834` | TX interrupt status, write-one-to-clear; our driver never writes it back |
| `0x03003864` | TX FIFO count, ARM → MIPS. The vendor treats 8 as full; past it a word is lost |
| `0x03003874` | the doorbell: `MSG_DATA`, ARM → MIPS. Writing it is what the far side sees |
| `0x03003164` / `0x03003174` | RX count and RX data, MIPS → ARM; reading the data pops the FIFO |

The word on the wire is the bare message type, `0` `CALL`, `1` `RETURN`, `2` `CALL_ACK`, `3`
`RETURN_ACK`, and nothing else - the transport carries no framing, so both protocols on top of it
are software.

## The in-kernel API

`include/linux/soc/sunxi/h713-cpu-comm.h` exports four functions: `cpu_comm_call()` (blocking, up
to 10 32-bit words in and out, real error codes), `cpu_comm_register_callback()` /
`cpu_comm_unregister_callback()`, and `cpu_comm_name2id()`. A routine is addressed by a 32-bit id,
and the id is derivable from the name alone - it is `crc32_le()` with seed `0x00123456` over
`sprintf("%s_%1x_%3.3x", name, cpu, pid & 0xfff)`, LSB first, with no pre- and no post-inversion.
That is the vendor's own `Comm_Name2ID`, which ships a private copy of the `crc32_le` table rather
than calling the kernel's; the values are identical. In Python, where `zlib.crc32()` has both
inversions built in:

```python
import zlib

def crc32_le(seed, data):            # == Linux crc32_le(seed, data, len)
    return zlib.crc32(data, seed ^ 0xFFFFFFFF) ^ 0xFFFFFFFF

def routine_id(name, cpu=1, pid=0):
    return crc32_le(0x00123456, ("%s_%1x_%3.3x" % (name, cpu, pid & 0xfff)).encode())

routine_id("THal_Vp_GetImageBufferAddr")   # 0x2f02f7dd
```

Thirteen ids of `mainline/docs/reference/cpu-comm-call-table.md` reproduce this way byte for byte -
`THal_Vp_EnableBlackScreen` `a30d4c6b`, `THal_Vp_DisableBlackScreen` `b66041d8`,
`THal_Vp_EnableVideoFreeze` `2fdcdc6f`, `THal_Vp_DisableVideoFreeze` `3ab1d1dc`,
`THal_Vp_EnableScreenCover` `0152f134`, `THal_Vp_DisableScreenCover` `143ffc87`, `THal_Vp_Init`
`1c6ff747`, `THal_Vp_SetBacklightWorkMode` `4d80db0e`, `Thal_Vp_SetBacklightPwmInfo` `b46ce545`,
`Thal_Vp_SetBacklightLevel` `51ad877e`, `THal_Vp_SetSource` `eaf13de5`, `THal_Vp_GetSource`
`24efc7c9` and `THal_Vp_GetImageBufferAddr` `2f02f7dd`. The two `Thal_` entries are the vendor's
own lower-case typo and only resolve with it spelled that way. Arguments carry no type
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
