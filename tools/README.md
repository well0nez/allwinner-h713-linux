# tools/ - Hilfsskripte (Bring-up-Phase, August/September 2026)

Nicht mehr im täglichen Gebrauch, aber funktionsfähig und gelegentlich nützlich. Der Betrieb läuft über
`h713-tv` und die Skripte unter `analyse/hdmi-seq/` (siehe `doku/50-befehle.md`).

| Datei | Zweck |
|---|---|
| `uart-capture.py`, `uart-watch.py`, `uart-send.py`, `uart-fixargs.py`, `uart-uboot.py`, `uart-mips-live.py` | UART-Mitschnitt, U-Boot fernsteuern, MIPS-Log live (Vorsicht: `/dev/ttyACM0` gehört Marco) |
| `hdmi-sequence.py`, `uboot-hdmi-sequence.txt` | die frühe HDMI-Initialisierung als Sequenz (vor den Kernel-Treibern) |
| `mips-dis.py`, `or1k-disasm.py`, `mipslog.c` | Mini-Disassembler für `display.bin` (MIPS32) und die ARISC (OpenRISC), MIPS-Log-Adressen |
| `arisc-fw-addrs.py` | resolves the SRAM addresses of an `h713-arisc.bin` the way the driver does (kernel patch 0091a) - for checking an unfamiliar dump before booting it |
| `tse_dump.py` | Parser für die TSE-Registerdatenbank der MIPS-Firmware |
| `vendor_ccu_parse.py`, `regdiff.py` | Vendor-CCU-Tabellen lesen, Registerabzüge vergleichen |
| `oops_resolve.sh` | Oops-Adressen im `vmlinux` disassemblieren |
