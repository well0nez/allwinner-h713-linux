# `tools/` - helper scripts from the bring-up (August/September 2026)

Not in daily use any more, but they work and are occasionally useful. Operation runs over `h713-tv`
and the scripts under `analyse/hdmi-seq/` (see `doku/50-befehle.md`).

| File | What for |
|---|---|
| `uart-capture.py`, `uart-watch.py`, `uart-send.py`, `uart-fixargs.py`, `uart-uboot.py`, `uart-mips-live.py` | UART capture, driving U-Boot remotely, the MIPS log live (careful: `/dev/ttyACM0` belongs to Marco) |
| `hdmi-sequence.py`, `uboot-hdmi-sequence.txt` | the early HDMI initialisation as a sequence (before the kernel drivers) |
| `mips-dis.py`, `or1k-disasm.py`, `mipslog.c` | small disassemblers for `display.bin` (MIPS32) and the ARISC (OpenRISC), and the MIPS log addresses |
| `arisc-fw-addrs.py` | resolves the SRAM addresses of an `h713-arisc.bin` the way the driver does (kernel patch 0091a) - for checking an unfamiliar dump before booting it |
| `tse_dump.py` | parser for the TSE register database of the MIPS firmware |
| `vendor_ccu_parse.py`, `regdiff.py` | read vendor CCU tables, compare register dumps |
| `oops_resolve.sh` | disassemble oops addresses in `vmlinux` |
