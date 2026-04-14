# HY310 ARM-MIPS CPU Communication

## Status: WORKING — MIPS APP_READY=0x5 autonomous

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

## SharedMem Init Timing

sunxi-mipsloader is now built-in (`CONFIG_SUNXI_MIPSLOADER=y`). At T+0.9s it
writes the SharedMem base address into the share registers. MIPS reads the
address, initializes cpu_comm, and reaches APP_READY=0x5 on its own — no ARM
polling or handshake nudging required.

**CCU bus clock register fix**: The share register offset was 0x604 (wrong);
corrected to 0x60c. Without this fix MIPS never sees the SharedMem address.

## BUG() Elimination

All 34 `BUG()` calls removed from cpu_comm (across dev.c, mem.c, hw.c,
channel.c, proto.c, rpc.c). Replaced with error returns. The `memset_io` wipe
that destroyed MIPS state on driver load was also removed.

## Reboot Fix

`cancel_delayed_work_sync` replaced with `cancel_delayed_work` (non-sync
variant) to avoid a deadlock that caused reboot hangs.

## MIPS elog

Mode 1 ring buffer dump available in dmesg at 0x4B272D9C.

## ioctl Test Results

25 of 27 ioctl tests PASS. TSE/PQ pipeline errors resolved — MIPS reads TSE
data successfully.

## Key IDA Addresses

`display.bin` is loaded at `0x8B100000` in IDA.
See the HANDOFF notes for the full function address list.

## Driver Location

- **Current module**: `drivers/soc/sunxi/cpu_comm/` (8 source files)
- **Superseded**: `drivers/misc/sunxi-cpu-comm.c` (older shift-repo approach, do not use)

## Next Steps

1. Route MIPS Msgbox IRQ for true bidirectional interrupt-driven communication
2. Stress-test IPC under sustained TSE/PQ workloads
