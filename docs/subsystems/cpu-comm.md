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

Thirteen worked examples; [the routine table](#the-routine-table) below lists all 82 known ids, and every one of
them reproduces this way byte for byte:
`THal_Vp_EnableBlackScreen` `a30d4c6b`, `THal_Vp_DisableBlackScreen` `b66041d8`,
`THal_Vp_EnableVideoFreeze` `2fdcdc6f`, `THal_Vp_DisableVideoFreeze` `3ab1d1dc`,
`THal_Vp_EnableScreenCover` `0152f134`, `THal_Vp_DisableScreenCover` `143ffc87`, `THal_Vp_Init`
`1c6ff747`, `THal_Vp_SetBacklightWorkMode` `4d80db0e`, `Thal_Vp_SetBacklightPwmInfo` `b46ce545`,
`Thal_Vp_SetBacklightLevel` `51ad877e`, `THal_Vp_SetSource` `eaf13de5`, `THal_Vp_GetSource`
`24efc7c9` and `THal_Vp_GetImageBufferAddr` `2f02f7dd`. The two `Thal_` entries are the vendor's
own lower-case typo and only resolve with it spelled that way (the table has a third one). Arguments carry no type
information: a routine that expects a buffer takes its physical address as a plain 32-bit word, and
that address has to be one the MIPS can already see.

The character devices (`/dev/cpu_comm`) that predate this API keep working unchanged and share the
same call mutex, so a kernel caller and an ioctl caller cannot race each other on the wire.

### The software spinlocks

Twelve 12-byte entries at the start of the shared region are one protocol on both processors - the vendor's
`tridspinlock.c`, compiled into the ARM driver and into `display.bin`: byte 0 says who is between
`enterCritical()` and `leaveCritical()`, byte 1 who holds the lock, bytes 4..7 the count, 8..11 the thread
(255 while free). Software lock N is guarded by hardware lock N + 2 (register id N + 10). Until `0259`
(12.10.2026) the port wrote byte 3 for "in the critical section", did not wait for the other side there and never
wrote byte 1, so a lock the ARM held looked free to the MIPS. On a warm start, while the freshly started MIPS
copied its routine table under lock 2 and Linux registered its routines, both sides changed the entry at once;
lock 2 stayed taken for ever, every open of the HDMI receiver was refused and the wall stayed dark (about two
warm starts in eleven). `0259` follows the vendor's sequence and, on a load that adopts the live region, releases
whatever an earlier Linux left held by the ARM. Measured: 22 warm starts clean on the HY300PRO-G-EU
(`doku/203`). As a net for whatever else could leave h713-tv without its device, `h713-tv-rescue.service`
reloads the MIPS once per boot when h713-tv gives up.

The thread word is not the bare tgid since `0261` (12.10.2026): both sides read a low byte of 0xff as "free",
and the process that registers first after a warm start - h713-tv - gets pid 255 in about one boot of twenty.
That lock then read "free" to its own unlock, stayed held by the ARM for ever, and the wall was dark until the
net reloaded the MIPS (one warm start in twenty, traced step by step in `doku/206`). The word is now
`tgid << 8 | 1`; 50 warm starts without the net since.

## The shared memory and the firmware's allocator

The 5 MiB region behind the transport (`0x4E300000` on the HY310) is two things. The first `0x2D000` bytes
are the transport's own structures: the software spinlocks at the start, the record lists, the routine table
at `0x75C0`, the component pool at `0x240E8` and the message pool at `0x2C068` (`cpu_comm.h`). Everything
above belongs to the display firmware's allocator, the vendor's `Trid_SMM`, which both processors use and
which our driver sets up when it loads (`Trid_SMM_Init`, `cpu_comm_mem.c`). The layout, with the offsets
from the region's base:

| Offset | What |
| --- | --- |
| `+0x2D000` | the allocator's header page (`SHMEM_OFF_SMM_HEAP`, `0x2CCF0`, rounded up to a page) |
| `+0x2E000` | its page table: 12 bytes per page of the heap, four pages here (1236 pages in all) |
| `+0x32000` | the first data page |
| `+0x36000` | the HDCP 2.2 key, 912 bytes (the HDMI receiver's driver) |
| `+0x37000` | the `Wce_SetWindow` structures, `0x48` bytes (the receiver's driver) |
| `+0x37100` | the six backlight PWM words, 24 bytes (the receiver's driver, only with `allwinner,backlight-pwm-info`) |
| `+0x37200`, `+0x37300` | the white balance block and the colour management block (`h713-tv`, [its page](../tools/h713-tv.md)) |
| `+0x400000` | the staging block of `THal_Vp_Init`, 55296 bytes (written by the firmware) |
| `+0x500000` | the end of the region |

The header words that matter are 45, 46 and 47 (a 32-bit word each, counted from the header): **47** is the
heap's start, the physical address of the header itself; **45** is the break, an offset from that start,
which begins at `4096 + page table` (`0x5000` here) and only ever moves up; **46** is the capacity the break
may not pass (`0x4D330F`, so the heap reaches the end of the region). The break as an address is word 47 plus
word 45. A request of more than 2048 bytes takes whole pages from the break. One of 8 to 2048 bytes comes from
a free list of its power-of-two class, and when that list is empty the allocator takes **one whole page**
from the break and cuts it into blocks of that class. So the break is always a multiple of 4 KiB, and the
smallest thing the firmware ever takes from it is a page. A free block keeps its list links in its own first
two words, which means a stray write into a page of small blocks does not damage one block, it damages the
list; the vendor's allocator checks the links and treats a bad one as a fault.

The places in the table above are fixed offsets. The stock userspace used addresses of the same kind (its
HDCP key at `0x4E336000`, which is our key's place; its white balance block at `0x4E333000`, the page our
allocator would give out next today), while our drivers and `h713-tv` take theirs without asking the
allocator. Nothing reserves them, and the allocator does not know they exist: a page it has reached may be
given out to the firmware at any moment.

Measured on the HY310 (18.10.2026, after a boot, a standby and a session of colour work): the allocator had
given out **one page**. Header `0x4E32D000`, page table `0x4E32E000`, data from `0x4E332000`, break at
`0x4E333000` (word 45 = `0x6000`); that page was a page of 64-byte blocks with one block in use (`0x40` bytes
given, `0xFC0` free), and the page table had a single entry. The pages of the places (`0x4E336000` to
`0x4E338000`) lay three pages above the break and were null in the table. Nothing in our Linux calls the
allocator (no `IOCTL_MALLOC`), so the firmware's own take of one page after the start is all there is. Not
measured: the break on the HY300PRO-G-EU, and whether any long run or any firmware feature moves it.

Both writers test the break before they write. `h713-tv` reads words 47 and 45 before every write of its
blocks and refuses once the break has reached the page of the block (`color.c`, `fwc_slot_free`: the break
offset against the block's page start, minus `0x2D000`). The HDMI receiver's driver (kernel `0326`) reads
the same two words before each of the three blocks it writes in its init sequence and, when the break stands
at or above the block's page, writes nothing there and leaves the step out with a warning in the kernel log
(`step N THal_Vp_... skipped: the firmware's allocator has reached the page of its block (break +..., block +...)`);
the `hdcp` attribute then reports the key as skipped for that reason, and the board runs without HDCP 2.2
that boot. The test is against the **page**, not the byte: a break standing exactly at the start of the
block's page means the very next allocation takes that page. While the break is below the places the driver
changes nothing; at every bind it logs where it is (`the firmware's allocator ends at +0x33000 of the shared
memory, the lowest place of this driver is at +0x36000`). THal_Vp_Init's staging block is not tested: the
driver writes nothing into it and it lies 4 MiB up. If the allocator's header is not where the transport
puts it, nothing can be tested and the driver writes as it always did, with one warning.

What would need to change if the break ever reached a place for real is the places, not the tests: the
blocks would have to come from the allocator (the vendor's own way, `IOCTL_MALLOC`), and since the firmware
keeps the pointer to the colour management block for good, that would have to be done for all of them at
once, in one mechanism.

## The routine table

The display firmware serves a call only for a routine that is in its table, and the table is filled late:
only once the firmware has proved itself ready for applications, so a dump taken earlier finds it empty.
What follows restates one live dump, taken on 4 August 2026 on Stenger's bench board (project `0x33`) with
`h713_disp calltable 0`, run after `h713_disp mips-test 0x33`. The dump and its first write-up are his (in his
repository, [`docs/reference/cpu-comm-call-table.md` at `8860991`](https://github.com/cstenger/allwinner-h713-mainline/blob/8860991a91ee973a45bb6f198bda896dd1e02c36/docs/reference/cpu-comm-call-table.md));
the grouping, the wording and the check of the ids are ours. 82 of the table's 1224 slots held a routine. A run
of `h713_disp test` is the wrong lead-in to a dump: it does not prove readiness and sets the source id to 2, on
which the firmware gives up its init.

A slot is `0x60` bytes:

| offset | holds |
| --- | --- |
| `+0x00` | the word `0x00010000`, a version or flags word |
| `+0x04` | the pid word: `0x8b8f32b0` in every slot of that dump, `0x8b8f3160` in the dump our U-Boot HDMI sequence was written against (`tools/uboot-hdmi-sequence.txt`), so read it from the firmware you call into |
| `+0x08` | the routine id, the number a call carries |
| `+0x0c` | the name, NUL-terminated, with the `_1_000` suffix that goes into the hash (`THal_Vp_Deinit_1_000`) |
| `+0x50` | the handler's address in the firmware's address space |
| `+0x5c` | the word `0xffffffff`, a marker |

From U-Boot a routine is called by its id, for instance `h713_disp commcall 2f02f7dd chan=0 pid=8b8f32b0` for
`GetImageBufferAddr` on that dump. The image also holds a static copy of the table, in `display.bin`: 81
entries of `0x68` bytes, the handler address in the last word (`doku/85` §A.2). The static count is one below the
live one; why was not looked into (not measured).

**Names and ids.** Every name starts with `THal_Vp_`, except three that the vendor spelled `Thal_Vp_`
(marked with a dagger below), and a lookup by string has to use the spelling as it is. The ids were not copied
but recomputed: all 82 reproduce from their names with `routine_id()` above (checked 13.10.2026, `doku/210` §5). The source gave
24 names in full and the other 58 without the prefix; for those the id decides, and with `THal_Vp_` in front
every one reproduces except `AtvIsFastSyncLock`, which only the lower-case spelling reproduces. The routine
column below omits the prefix.

**Handlers.** An address is as dumped, 19 of them only so. The six marked `*` are also what our own static
reading of `display.bin` gives (`doku/85` §A.2); `SetBrightness` is one of them and has no address in the dump.
Where the column says `-`, no address is recorded in the source: 57 of the 82.

| group | id | routine | handler |
| --- | --- | --- | --- |
| Start and stop | `1c6ff747` | `Init` | `8b109f04` |
|  | `eaaa24c9` | `Deinit` | `8b10a0e0` |
| Blanking the picture | `a30d4c6b` | `EnableBlackScreen` | `8b10a0e8` |
|  | `b66041d8` | `DisableBlackScreen` | `8b10a110` |
|  | `2fdcdc6f` | `EnableVideoFreeze` | `8b10a138` |
|  | `3ab1d1dc` | `DisableVideoFreeze` | `8b10a160` |
|  | `0152f134` | `EnableScreenCover` | `8b10a188` |
|  | `143ffc87` | `DisableScreenCover` | `8b10a1ec` |
| Input source and the capture buffer | `eaf13de5` | `SetSource` | `8b10a218`* |
|  | `24efc7c9` | `GetSource` | `8b10a244`* |
|  | `24b17fb7` | `GetSignalInfo` | `8b109b40`* |
|  | `396f16bf` | `SetImageBufferAddr` | `8b10ada8` |
|  | `2f02f7dd` | `GetImageBufferAddr` | `8b10adb0` |
| Window and seamless switching | `3356c54b` | `Wce_SetWindow` | `8b109d54`* |
|  | `fd483f67` | `Wce_GetWindow` | `8b109dc0` |
|  | `7bbd5772` | `Wce_GetActiveWindow` | `8b109e2c` |
|  | `09ffc6eb` | `Wce_SetMirrorMode` | `8b109d20` |
|  | `8f8a9581` | `Wce_EnablePixel2PixelMode` | `8b109e88` |
|  | `ea7ffef5` | `Wce_DisablePixel2PixelMode` | `8b109edc` |
|  | `cb6d765f` | `SeamlessEnable` | `8b109cd0` |
|  | `c5429d4a` | `SeamlessDisable` | `8b109cf8` |
| Backlight | `4d80db0e` | `SetBacklightWorkMode` | `8b10a410` |
|  | `b46ce545` | `SetBacklightPwmInfo`† | `8b10a444` |
|  | `51ad877e` | `SetBacklightLevel`† | `8b10a4c8`* |
| Picture settings | `7221d017` | `SetBrightness` | `8b10a4fc`* |
|  | `880be6ff` | `GetBrightness` | - |
|  | `023c4033` | `SetContrast` | - |
|  | `6665fe81` | `GetContrast` | - |
|  | `a84983c3` | `SetSaturation` | - |
|  | `5263b52b` | `GetSaturation` | - |
|  | `5b2c62d5` | `SetHue` | - |
|  | `5432b456` | `GetHue` | - |
|  | `7335ebb5` | `SetSharpness` | - |
|  | `563e60ab` | `GetSharpness` | - |
|  | `1a116843` | `SetGamma` | - |
|  | `f6a798d3` | `SetDCI` | - |
|  | `f9b94e50` | `GetDCI` | - |
|  | `c0da6a8e` | `SetSNR` | - |
|  | `cfc4bc0d` | `GetSNR` | - |
|  | `a4bb0747` | `SetTNR` | - |
|  | `aba5d1c4` | `GetTNR` | - |
|  | `5c135587` | `SetBlackExtension` | - |
|  | `5d3d7258` | `GetBlackExtension` | - |
|  | `fc42fe0c` | `SetWhiteBalance` | - |
|  | `f00ca77d` | `SetColorManagement` | - |
|  | `e661461f` | `GetColorManagement` | - |
|  | `83a878bf` | `SetPictureMode` | - |
|  | `2d8338c3` | `GetPictureMode` | - |
|  | `9817a1c1` | `SetVideoRange` | - |
|  | `623d9729` | `GetVideoRange` | - |
|  | `c201c220` | `SetLowLatencyMode` | - |
|  | `c32fe5ff` | `GetLowLatencyMode` | - |
|  | `434567b0` | `GetDisplayLatency` | - |
| HDMI input, HDCP and ARC | `9ce74c48` | `HDMI_SetPortMap` | - |
|  | `cbf83247` | `HDMI_GetPortStatus` | - |
|  | `6eb4c96a` | `HDMI_SetHPDTimeInterval` | - |
|  | `ba3e5a70` | `SetHDMIHotPlugByPortCallback` | - |
|  | `449effe8` | `HDMI_ReloadHdcp14Key` | - |
|  | `50817813` | `SetHDCP22Key` | - |
|  | `fa085aaa` | `SetHDCP22Pkf` | - |
|  | `93965d14` | `TurnOnARCAudioPath` | - |
|  | `e9b4464d` | `SwitchARCTXPath` | - |
| Analogue input (ATV, CVBS) | `a16b7c24` | `AtvSetRegion` | - |
|  | `80e56656` | `AtvSetSignalStd` | - |
|  | `a138c8fe` | `AtvChannelChange` | - |
|  | `39d6eec4` | `AtvChannelScanStart` | - |
|  | `9558d223` | `AtvChannelScanEnd` | - |
|  | `6e857547` | `AtvEnableSnowScreen` | - |
|  | `71a4c888` | `AtvIsFastSyncLock`† | - |
|  | `24f44438` | `CvbsSetPedestalMode` | - |
| Teletext and other VBI data | `0fe1790c` | `StartVBI` | - |
|  | `8a0d26cb` | `StopVBI` | - |
|  | `9c91450e` | `ResetVBI` | - |
|  | `f3772724` | `EnableVBILine` | - |
|  | `096b60b1` | `GetVBIData` | - |
|  | `ec2ca0b4` | `GetVBIOffset` | - |
|  | `8f5859c2` | `GetVBIAddr` | - |
|  | `96046e19` | `GetVBISize` | - |
| Registering for events | `671ceca6` | `RegisterSignalChangeCallback` | - |
|  | `2692bdbe` | `UnregisterSignalChangeCallback` | - |
|  | `87a96488` | `RegisterCallbackOfDisplayLatencyChange` | - |
|  | `72341984` | `UnregisterCallbackOfDisplayLatencyChange` | - |

All of these are calls from the ARM to the MIPS, addressed to cpu 1. The calls the other way, the MIPS into the
ARM (`MipsHalCallback_*`, cpu 0), are not in this table (`doku/83`). The four routines under "Registering for
events" are how the ARM asks to be called back later. The picture settings are used through the controls
described in [pq.md](pq.md), the HDMI group through the receiver driver ([hdmi-in.md](hdmi-in.md)).

**What the table lacks.** No routine for panel power: nothing for the panel supply, its reset or the GPIO lines
(PF6 is one of them). They stay on the ARM side, in U-Boot's `h713_disp_stock_panel_power` (`doku/182`), so
switching the panel off is done in two places, `Deinit` in the firmware and then the ARM's own power-down of those
lines, for which the vendor's `PanelOffTiming0..2` are 20, 250 and 75.

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
