# HY310 ARM-MIPS CPU Communication

## Status: PARTIAL — ARM→MIPS one-way working, MIPS→ARM IRQ path blocked

## Architecture Overview

- **Shared memory**: 5 MB at `0x4E300000` (ARM/MIPS both have access)
- **Hardware mailbox**: `0x03003000` (H713 Msgbox)

## H713 Msgbox Layout

| User Page | Purpose          |
|-----------|------------------|
| User0     | ARM RX           |
| User1     | Data Pipe        |
| User2     | MIPS IRQ         |

- Port stride: `0x100`
- ARM TX: write to `+0x474` (User1 Port1); MIPS reads by polling

## Message Format

```c
raw = cpu & 0x3;   // MIPS expects plain values 0-3, no encoding
```

## Routing Table (Shared Memory)

- 1224 slots total: 1024 primary + 200 overflow
- Each slot: 96 bytes
- 18 MIPS VP routes auto-registered at POST-WAIT stage

## BLOCKER: MIPS IRQ Path

The MIPS co-processor never receives hardware interrupts from the Msgbox:

- Msgbox User2 IRQ Enable (`+0x820`) = `0x04`
- MIPS INTC slot 4 = HW IRQ 25
- **But**: INTC pending/raw registers read `0x00000000` — the HW interrupt line is not routed to MIPS INTC

**Consequence**: MIPS ISR never fires → no ACK → no bidirectional communication possible.

ARM→MIPS one-way messaging works via MIPS polling, but MIPS→ARM reply path is broken until the MIPS IRQ routing is resolved.

## Key IDA Addresses

`display.bin` is loaded at `0x8B100000` in IDA.
See the HANDOFF notes for the full function address list.

## Driver Location

- **Current module**: `drivers/soc/sunxi/cpu_comm/` (8 source files)
- **Superseded**: `drivers/misc/sunxi-cpu-comm.c` (older shift-repo approach, do not use)

## Next Steps

1. Trace HW IRQ 25 routing in H713 GIC / interrupt controller configuration
2. Determine if MIPS INTC requires a separate enable step not present in display.bin init
3. Consider polling-based fallback for MIPS→ARM ACK if IRQ path cannot be fixed
