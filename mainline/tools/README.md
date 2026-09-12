# Hardware tools

`serial/` — talk to the board over the console and load images:
- `acm.py CMD [--port <tty>]` — run one U-Boot command, print reply.
- `load_fit.py FILE [--port <tty>]` — single-fd `loady` + YMODEM (big FITs).
- `ymodem_send.py` — standalone YMODEM sender.
- `boot_kernel.py` — setenv + bootm + capture kernel console.

The CDC tools default to `--port auto`, resolving the board by USB vendor ID
`1f3a`; pass `/dev/ttyUSB0` explicitly for the hardwired UART. Historical
destructive and local-artifact-dependent runners live under ignored `local/`,
not in the supported tool set. See ../README.md gotchas.

`flash-standalone.sh` — flash the kernel FIT to the `boot_a` partition (via
fastboot) and print the U-Boot `bootcmd` for power-on → Debian. See
[../docs/standalone-boot.md](../docs/standalone-boot.md).

`cpufreq-thermal-validate.sh` — runs **on the target** to validate the
voltage-scaling CPU OPP table and its thermal cooling-device binding. It sweeps
every OPP in both directions while reporting VDD-CPU, restores the original
frequency and governor on every exit, and can run a bounded maximum-frequency
stress test with an 85 C default stop threshold. It changes voltage only via
cpufreq and never writes a regulator or thermal trip point directly. See
[../docs/status.md](../docs/status.md).

`rootfs/` — `build.sh --ssh-key FILE` builds the signed Debian arm64 rootfs,
installs matching kernel modules, validates the ext4 image, and emits an
Android-sparse fastboot image. `customize.sh` performs target customization
without executing target binaries. Full recipe in [../docs/rootfs.md](../docs/rootfs.md).
