# ARM ↔ MIPS communication (cpu_comm)

Linux and the MIPS display coprocessor share no memory model, no calling convention and no clock
domain of their own - `cpu_comm` is the RPC layer that bridges that gap. Nothing in normal use
calls it directly, but every HDMI source switch does, underneath `h713-tv`. The same driver parks
the coprocessor for a standby and keeps the books for starting it again (end of this page).

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
`cpu_comm_unregister_callback()`, and `cpu_comm_name2id()`; a restart interface comes on top of
them (below). A routine is addressed by a 32-bit id, and the id is derivable from the name alone -
it is `crc32_le()` with seed `0x00123456` over
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
`board/debug.config` to get it back (`doku/83`). Callback descriptors do not survive a restart of the
MIPS: the shared region is rebuilt, so a client registers again afterwards - for the HDMI receiver
that means unbinding it around the restart.

## Parking the MIPS for the standby

The MIPS cannot go through a DRAM self-refresh - left running, the box stops shortly after the wake
(`doku/165` §2) - and the vendor parks it before every standby (`doku/171` §2). So `cpu_comm` parks
it in `suspend_late`, **for suspend to RAM only, never s2idle** (`0208`, `0210`). The owner of the
MIPS clock and reset words (`0x02001600`, `0x0200160c`) is the driver `sun50i-h713-mips`
([mips.md](mips.md)): `cpu_comm` asks it whether a core is there and has it park, in U-Boot's
`h713_mips_stop()` order - reset word 0, 12 ms, clock word 0, 12 ms, both read back (`0230`). Without
that driver (module absent, node disabled as on the HY300 Pro) `cpu_comm` writes the same words
itself and nothing can restart the core. Before the writes it takes the call mutex, which waits out
a call in flight, and closes the call path. Three words keep the books (`0213`, `0216`, `0228`):

- `cpu_comm_suspend_flag`, the ioctl path's suspend count: an ioctl answers `-EFAULT` while it is above 0.
- `cpu_comm_fw_down`, "out of service": set by the park or a restart's stop, whichever comes first,
  taking exactly one count with it; the restart's start clears it and gives the count back.
- `cpu_comm_parked_since`, the number of the suspend to RAM that parked the core (0: not parked),
  counted per boot at `suspend_late`; it is not crust's cycle number.

`/proc/cpu_comm/status` shows them. If a written word does not read back 0, the suspend fails with
`-EIO` and the driver reopens the call path itself, since `resume_early` never runs then (`0217`;
not run on the device). After the park, kernel calls fail at once instead of costing a call slot and
a 2 s timeout each (`0213`): `-EBUSY` from the first check of `cpu_comm_call()`, `-ENODEV` for a
caller already waiting on the mutex (read from the code, not measured). `cpu_comm_firmware_up()` is
false from the park to a restart's start, from those words alone; the HDMI receiver asks it before
its LINK poll, because after the park a read of that block never answers and stops the bus (`0236`,
`doku/176` §2). The wake starts nothing: the restart reads `display.bin` from `/boot`, frozen until
the wake is through, and needs the receiver unbound, so it is userspace's
([h713-mips-restart](../tools/h713-mips-restart.md)). s2idle is refused in `.prepare` while the MIPS
runs, because genpd cuts TVFE and TVCAP under it (`0212`; read from the code, not measured).

```
suspend        hdmirx stops the capture (0240); afbd idles the scanout (0210)
suspend_late   cpu_comm parks the MIPS, then gates the display clocks (0238)
noirq          genpd powers TVFE and TVCAP off; PSCI SYSTEM_SUSPEND
resume_early   cpu_comm writes the display clock words back; later, userspace restarts the MIPS
```

### The display clocks

Parking stops the core, not the pipeline it set up. Left running through the self-refresh, that
pipeline cost every DMA master its way to the DRAM after about every second wake - the CPU was fine,
the USB camera got `-110`, Wi-Fi "cmd timed-out", the resume hung: 12 of 22 woken runs on
08.10.2026, 7 of 7 the next night without a remedy (`doku/171` §2). The vendor puts the display bus
in reset and stops the display clocks before every standby. So `cpu_comm` saves five CCU words at
`0x02001db0` - deint, panel, svp-dtl, afbd (bit 31 each) and bus-disp (bit 0) - clears the gates
right after the park, before genpd cuts TVCAP and TVFE, and writes the words back unchanged in
`resume_early` (`0238`). **No reset:** it would lose what the parked MIPS set up, and afbd's resume
then hangs the bus (`doku/171` §3). **Since `0241` whenever no core runs** at a suspend to RAM, not
only after an earlier park: a restart that fails past its park would otherwise leave the old
pipeline running through the next sleep (`doku/173` §1; checked offline only). Measured: 9 of 9
wakes good with the gating in the noirq phase, then 7 of 7 and 6 of 6 in `suspend_late` on two
stacks, and no camera or Wi-Fi error in 10 wakes of the R2 test image (`doku/171` §3); the place in
the bus where the fetch is lost is not measured (`doku/171` §4).

## Restarting the MIPS

The restart itself is `sun50i-h713-mips`; `cpu_comm` gives it three calls and a notifier chain,
shaped after what the vendor's `cpu_comm` does around each restart (read off `cpu_comm_dev.ko`,
`0225`). `cpu_comm_firmware_stop()` refuses new calls and lets one in flight finish; a parked core
counts as stopped. `cpu_comm_firmware_reset()`, with the core held, tells the chain
`CPU_COMM_FIRMWARE_HALTED`, releases the hardware locks the old core may hold, reads both
message-box FIFOs off undelivered (`0229`, `0234`) and rebuilds the region.
`cpu_comm_firmware_start()` ends the park, waits for the new firmware's READY flag alone
(`-ETIMEDOUT`), assumes "app ready" as the boot does, and tells the chain
`CPU_COMM_FIRMWARE_STARTED` (`0228`). Ready about 300 ms after the start (`doku/172` §4).

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
`doku/66-cpu-comm-arm64-bringup.md`, `doku/67-cpu-comm-linux.md`; the standby side in `doku/165`,
`doku/171` - `doku/174` and [standby.md](standby.md).
