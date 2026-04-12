# drivers/Archived — Pre-Refactor Reference Drivers

This directory contains read-only reference copies of drivers that were
refactored in commit `91ce2c6` (2026-04-10). They are **not compiled**, not
linked into any Makefile, and must not be used as-is.

## Why these exist

Before the refactor, `cpu_comm`, `tvtop`, and `decd` lived as kernel patches
in `patches/` and were applied at compile time. Their source existed only in
patch-diff form. The files here are the last state of those patch-embedded
implementations, extracted as plain source for reference — for example when
comparing against the current out-of-tree modules or tracing back a specific
implementation decision.

`sunxi-mipsloader.c` and `sunxi-nsi.c` are earlier reverse-engineered
monolithic files that preceded the modular approach entirely.

## Contents

| Directory / File         | Origin Patch                              | Date       | Description                          |
|--------------------------|-------------------------------------------|------------|--------------------------------------|
| `cpu_comm/`              | `0014-soc-sunxi-add-cpu-comm-ipc.patch`   | 2026-04-09 | ARM↔MIPS IPC (channel, FIFO, RPC)   |
| `tvtop/`                 | `0012-misc-add-sunxi-tvtop.patch`         | 2026-04-03 | TV subsystem top (clocks, power)     |
| `decd/`                  | `0013-misc-add-sunxi-decd.patch`          | 2026-04-03 | Display engine codec                 |
| `sunxi-mipsloader.c`     | `0010-misc-add-sunxi-mipsloader.patch`    | 2026-04-01 | MIPS coprocessor loader (monolithic) |
| `sunxi-nsi.c`            | `0011-misc-add-sunxi-nsi.patch`           | 2026-04-01 | ARM↔MIPS NSI interface (monolithic)  |

## Current modules

The actively maintained out-of-tree modules are at:

- [`drivers/display/tvtop/`](../display/tvtop/)
- [`drivers/display/decd/`](../display/decd/)
- [`drivers/cpu_comm/`](../cpu_comm/)

See [`docs/CPU_COMM.md`](../../docs/CPU_COMM.md) and
[`docs/DISPLAY.md`](../../docs/DISPLAY.md) for subsystem documentation.
