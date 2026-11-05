# Clean-room bench, HY320 (03.-05.11.2026)

The scripts, tools and input tables of the bench in `doku/231`. Their output - the bench and standby logs, `dmesg`
captures, program output (`*.txt`), the `*.vpb`/`*.rxtime`/`*.vp` captures and `replay-client.json`, 954 files,
52 MB - is not in this tree since 05.11.2026. It is unchanged at commit `738a2ae9` of minpeter/allwinner-h713-linux,
in this same directory:

https://github.com/minpeter/allwinner-h713-linux/tree/738a2ae9ad06bf482437c0b00f9cb556c054f5d9/analyse/cleanroom-bench-20261103

The scripts reach the board through a jump host: set `H713_JUMP` to it (`referenz/geraete.md`); unset, they stop.
What they write here again (`*.log`, `*.txt`, ...) is ignored (`.gitignore`).
