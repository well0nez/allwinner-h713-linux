# H713 board bring-up: boot chain and state engines

What runs, in what order, and which state machine each stage advances. Written
from the recovery implementation in
`external/u-boot/arch/arm/mach-sunxi/h713_mips.c`, the stock binaries under
`local/`, and console transcripts from bench runs.

Claims are marked where they are inferred rather than proven, because several
earlier readings in this project were confidently wrong.

## 1. Boot chain

```
BROM  (mask ROM, on-die)
  |
  v
boot0 / SPL          eMMC boot area   32 KiB
  |                  local/h713-lab/captures/board-b/bench_bt0.img
  v
TOC1 container       4 MiB
  |                  local/mips-display/research/toc1.bin
  |                  items: MIE;u-boot  IIE;monitor  IIE;scp  IIE;optee  IIE;dtb
  v
BL31 (monitor) -> OP-TEE -> U-Boot proper @ 0x4a000000
  |
  v
Linux, or the h713_disp / h713_mips recovery commands
```

### What each stage touches

Established by scanning every stage binary for how it addresses MMIO -- 32-bit
literals on ARM, `lui` immediates on MIPS:

| stage | display registers | notes |
| --- | --- | --- |
| boot0 | **none** | two CCU references, no PIO, no display bases. Its recovered 272-access MMIO trace is SYSCFG, CCU and DRAM only. |
| TOC1 items (monitor, scp, optee, dtb) | **none** | no LVDS/TCON/PHY bases in any component |
| U-Boot proper | LVDS lane, TCON, display PLL | **data-driven only** -- no code literals; addresses come from `LogoRegData.bin` |
| `display.bin` (MIPS) | DE, display-route, LVDS PHY, vblender, mixer | direct `lui`-built addresses |

There is no SPL logo path on this board. Nothing before U-Boot programs the
display.

The ARM and MIPS sides address **disjoint** register sets. `lui 0x0580`,
`lui 0x0588` and `lui 0x058c` do not appear anywhere in the MIPS firmware, so
the coprocessor never immediate-addresses the LVDS lane, TCON or display-PLL
blocks. Conversely U-Boot holds no literals for them either -- it reaches them
only by matching record addresses out of the LogoRegData table.

## 2. Address maps

### ARM view

| region | base | size |
| --- | --- | --- |
| U-Boot proper | `0x4a000000` | -- |
| MIPS firmware window | `0x4b100000` | `0x00500000` |
| MIPS config / TSE windows | `0x4be01000` | `0x00040000` |
| LogoRegData | `0x4e000000` | -- |
| CPU_COMM shared memory | `0x4e300000` | `0x00500000` |
| OSD framebuffer | `0x6c100000` | 1280x720 ARGB8888 |

### MIPS view

Firmware text is linked at `0x8b100000`, which is the `0x4b100000` load address
plus `0x40000000`.

Display MMIO uses a different window. Both firmware accessors compute:

```
mips_va = arm_pa + 0xb5000000
mips_va |= 0x20000000
```

`0xb5000000` lands the result in KSEG1 (uncached). Masking KSEG1 down to
physical gives `arm_pa + 0x15000000`, so from the coprocessor's own bus the
display block sits `0x15000000` above where the ARM sees it. This is why ARM
cache maintenance cannot make firmware display state visible, and why `fwmd`
reads of cached KSEG0 globals are unreliable.

### Firmware register accessors

Every display register access in `display.bin` funnels through two helpers:

| helper | signature | behaviour |
| --- | --- | --- |
| `0x8b180550` | `read(addr)` | returns the mapped word in `$v0` |
| `0x8b180638` | `write(addr, mask, value)` | `(old & ~mask) \| (value & mask)` |

Both call `0x8b1801cc` first and **skip the access entirely if it returns
non-zero**. That gate has not been identified; treat any conclusion of the form
"the firmware writes X" as conditional on it.

Argument order is `(addr, mask, value)` -- mask in `$a1`, value in `$a2`.
Note MIPS delay slots: `$a0` is frequently set in the instruction *after* the
`jal`, so any tooling that resolves call arguments must execute the delay slot.

### Most register addresses are table-driven, not immediate

Only a minority of accesses build their address with `lui`. A static dataflow
pass over all 845 helper call sites resolves 311; the other 534 compute the
address at runtime as **base + byte offset**, where both come from firmware
globals in BSS above the loaded image:

```
lw    $v1, 0xc($s5)        ; s5 = 0x8bac4ac4 -> descriptor pointer @ 0x8bac4ad0
lw    $v0, 0x4ad8($s1)     ; s1 = 0x8bac0000 -> register base    @ 0x8bac4ad8
lbu   $a0, 4($v1)          ; a small byte offset out of the descriptor
addiu $a1, $zero, 0xff     ; mask
jal   0x8b180638
addu  $a0, $a0, $v0        ; addr = base + offset   (delay slot)
```

This has two consequences:

- **Static resolution has a hard ceiling.** No amount of dataflow analysis
  recovers these addresses; the values do not exist in the image.
- **Naive emulation does not reach them either.** Starting at a function entry
  with zeroed memory makes the early `lbu`/`beqz` on those globals branch away
  from the interesting path. Confirmed with a working Unicorn MIPS32LE harness:
  it executes the firmware correctly and simply takes the other branch.

The cheap way through is not more emulation -- it is to read the tables off a
live board, since `h713_disp fwmd` already dumps firmware memory from the ARM:

```
h713_disp mips-test 0x33
h713_disp fwmd 8bac4ac0 16
```

`0x8bac4ad8` yields the register base and `0x8bac4ad0` the descriptor pointer;
dumping the descriptor then resolves the byte offsets. With those two values,
the 534 unresolved sites become resolvable offline.

Note that `lui 0x8bac` is the third most common immediate in the firmware (854
sites), so this global block governs far more than the display registers.

## 3. Display bring-up sequence

The order below is the observed console sequence of
`h713_disp panel-test <project> ...`, which wraps `h713_disp_run()`.

```
 1. load vendor artifacts from mmc 1:2
      mips/display.bin        -> 0x4b100000
      mips/display_cfg.xml    -> 0x4be01000
      mips/database.TSE       -> 0x4be41000
      mips/projecttable.TSE   -> 0x4be85f60
      mips/ProjectID_0xNNNN.TSE
      mips/pq_custom.TSE
      mips/LogoRegData.bin    -> 0x4e000000
 2. publish the OSD surface at 0x6c100000
 3. select prologue / timing / DE record blocks by project id
 4. patch panel config fields into the record table    (section 4)
 5. apply prologue records, then timing records
 6. LVDS FIFO status check and reset
 7. apply the DE record block
 8. stock panel power: 550 ms pre-delay, then PF6 + PH16 asserted
 9. authenticate display.bin against its pinned SHA-256
10. defeat the HDCP key-load wait
11. prepare CPU_COMM shared memory                      (section 6)
12. release the MIPS                                    (section 5)
13. LVDS PHY tail
14. wait for MIPS READY, then application readiness
```

Steps 4-7 are the ARM's entire ownership of the LVDS lane / TCON / PLL
configuration. Step 12 hands the DE/PHY/route/mixer side to the firmware.

### The re-assert hazard

Diagnostic modes that quiesce the MIPS and then replay DE block 5 clear three
words the firmware had set, identically across consecutive boots:

| register | after firmware init | after DE replay |
| --- | --- | --- |
| `0x051c0014` | `18000005` | `18000000` |
| `0x051c0028` | `1f300030` | `00000030` |
| `0x05140054` | `40000080` | `40000000` |

All three fall inside the ranges the MIPS firmware addresses most heavily
(`lui 0x051c`, `lui 0x0514`). A fourth candidate, `0x0560030c`, moved
differently on each boot and is dynamic -- do not cite it.

**Not yet proven:** a static scan of resolved firmware helper calls does not
show writes to these three specific words. That scan resolved 311 of 845 call
sites; the remaining 534 hold their base in a callee-saved register across the
call and were not resolved. Absence from the resolved set is not evidence.

## 4. Panel config patching

Stock U-Boot's patch function is at `0x4a0290e0`; the single
`cmp.w r3, #0x05800000` in the whole image is at `0x4a02912e`. When a record's
address matches, it performs six bitfield inserts through the helper at
`0x4a029078`:

| config offset | shift | mask | field |
| --- | --- | --- | --- |
| `+0x00` | 6 | `0x3` | mapping / panel protocol |
| `+0x04` | 3 | `0x3` | bit width (distinct field from mapping) |
| `+0x08` | 14 | `0x1` | odd/even data swap |
| `+0x14` | 18 | `0x1` | DE invert |
| `+0x18` | 16 | `0x1` | HSync invert |
| `+0x20` | 24 | `0x1` | DCLK invert |

This is recovered from stock code and settles the bit positions that older
notes contradicted. Board B's `panel_config.ini` requests single-port, VESA
mapping, 8-bit colour, inverted DCLK, 1360x760 total, 1280x720 active, 62 MHz.

## 5. MIPS reset state engine

Control register `0x0200160c`; status register `0x0306101c`.

```
      0x00000000   RESET_ASSERTED     core held
           |
           v
      0x00010000   STAGE1
           |
           v
      0x00030000   STAGE2
           |
           v
      0x00030001   STAGE3
           |
           v
      0x00070001   RELEASED           status reads 0x00000001
```

Execution is proven independently of the status bit by seeding a witness word
at `0x4b100000 + <offset>` with `0x4d495053` (`"MIPS"`) and observing the
firmware overwrite it.

Quiescing for diagnostics asserts **only** the core reset and deliberately does
not gate the display clocks, so the raster keeps scanning and the prepared
display hardware survives the ownership handoff. Two samples of `0x05880000`
before and after confirm the raster is still live; if they are zero or equal,
no visual conclusion from that run is valid.

## 6. Readiness state engine

Shared memory at `0x4e300000`, magic `0xdeadbeef` at both `+0x90` and
`+0x75b8`.

| flag word | offset | meaning |
| --- | --- | --- |
| ARM | `+0x4cdc` | `BIT(0) \| BIT(2)` = ARM ready |
| MIPS | `+0x4ce0` | `BIT(0)` = MIPS READY, `BIT(2)` = application ready |

```
U-Boot clears shared memory and publishes valid magic
        |                         (InitCommMem then takes the slave path)
        v
MIPS released
        |
        v
witness overwritten          -> "firmware execution proven"
        |
        v
MIPS flag BIT(0)             -> "firmware readiness proven by MIPS READY"
        |
        v
MIPS flag BIT(2)             -> "application readiness proven"
        |
        v
header reads deadbeef/deadbeef, ARM state 5, MIPS state 5
```

Timeouts: 10 s for MIPS READY, 4 s for display readiness.

## 7. CPU_COMM transport state engine

Eight `share_seq` transports at `shared + 0x98`, indexed
`(cpu, dir, idx)` with strides 9760 / 4880 / 2440. Each holds twenty 104-byte
message slots, a 21-entry free ring, and a receive-side staging FIFO.

Rings used by the ARM master:

| ring | offset | owner |
| --- | --- | --- |
| FreeCall `share_seq(1,0,0)` | `+0x26b8` | MIPS |
| CallCmd ACK fields `share_seq(0,1,0)` | `+0x13a8` | ARM publishes, MIPS reads |
| FreeReturn `share_seq(0,1,1)` | `+0x1d30` | ARM |
| ReturnCmd ACK fields `share_seq(1,0,1)` | `+0x3040` | MIPS publishes, ARM reads |

Doorbell is `0x03003874`; the word written **is** the message type:
`0 = CALL, 1 = RETURN, 2 = CALL_ACK, 3 = RETURN_ACK`. Ringing it requires
pulsing `BIT(3)` in the msgbox TX IRQ enable (MIPS is port 1).

### Message lifecycle

```
ARM  allocate a FreeCall slot, fill it, set the sent flag at msg[+0x06] bit 2
ARM  ring doorbell 0
MIPS interrupt -> queueAction -> HISR -> command_action
MIPS SendAckLow publishes ACK metadata in share_seq(0,1,0) +0x68..+0x74,
     raises +0x69 bit 2, rings doorbell 2
ARM  MUST validate and clear that +0x69 bit -- draining the mailbox is not
     enough. The next SendAckLow assert-spins if the previous ACK is still
     outstanding.
MIPS worker runs the component handler, then SendComm2CPUEx
MIPS allocates FreeReturn, publishes RETURN, rings doorbell 1, waits
ARM  reads the reply, queues it into its own ReturnCmd staging FIFO,
     publishes RETURN_ACK metadata including the sender's 64-bit wait pointer,
     rings doorbell 3
MIPS interrupt clears the publication bit, then a deferred action posts the
     sender's wait semaphore; only then does SendComm2CPUEx resume
ARM  advances its ReturnCmd read index and recycles the FreeReturn slot
```

Two initialisation invariants cost several bench sessions each:

- The ARM must build its own `cpu=0` CallCmd/ReturnCmd staging FIFO headers
  with ARM-local backing rings. The MIPS cannot: their `base_addr` has to be
  meaningful to the ARM. An uninitialised header makes the sender spin forever
  in `fifo_isNearlyFull()`.
- Pre-populated free rings must publish `peak_count = 20`, matching the final
  state of the vendor algorithm, which pushes all twenty slots through
  `fifo_requestItemWr()` with tracking enabled. Leaving it zero trips
  `fifo_getCount`'s `count > peak + 1` assertion on the first recycle.

Status: 44 consecutive transactions on one boot, ring wrap crossed twice,
leak-free, reproduced without the diagnostic trace patches.

## 8. Ownership summary

| block | owner | reached via |
| --- | --- | --- |
| LVDS lane `0x05800000` | ARM / U-Boot | LogoRegData records |
| TCON `0x05880000` | ARM / U-Boot | LogoRegData records |
| display PLL `0x058c0000` | ARM / U-Boot | LogoRegData records |
| DE `0x0500`/`0x0504`/`0x050c` | MIPS firmware | `lui` + helper |
| display-route `0x05140000` | MIPS firmware | `lui` + helper |
| LVDS PHY `0x051c0000` | MIPS firmware | `lui` + helper |
| vblender `0x05200000` | MIPS firmware | `lui` + helper |
| panel power PF6 / PH16 | ARM / U-Boot | direct GPIO |

The TCON's own pattern generator is reachable from the ARM and bypasses
framebuffer, AFBD, OSD, DE and vblender entirely, which is why it is the
diagnostic of choice for link-level questions -- though see
`mips-display-recovery.md` for why its optical response is not currently
reproducible across boots.
