# fixtures/device - bytes off our own HY310, with no secrets in them

Every file here comes from Marco's HY310 (board HY260_QZ713_V3.1) or from our release; none carries
secure-storage, `private` or `Reserve0` content. Origin per file (Fable, 14.09.2026, package A2):

| File | What | Where it came from |
|---|---|---|
| `hy310-stock-gpt-primary-20260831.bin` | LBA 0-33: protective MBR, GPT header, 26 entries (`bootloader_a` … `Reserve0_a`, `Reserve0_b`, `UDISK`) of the **stock** device | `re/device-dumps/emmc-first-300mb.bin` (31.08., stock Android 11), sectors 0-33 |
| `hy310-layout-v3-gpt-primary-v0.5-beta.bin` | LBA 0-33 of our layout (`hy310-spl … hy310-rootfs`), as in the release | first 17 408 B of `p7-assets/h713-hy310-v0.5-beta-a-bootkette.img` |
| `hy310-layout-v3-gpt-backup-v0.5-beta.bin` | the backup GPT (33 sectors from LBA 15269855) | `p7-assets/h713-hy310-v0.5-beta-c-gptkopie.img`, unchanged |
| `hy310-uboot-env-20260913-release.bin` | the device's U-Boot environment (64 KiB, CRC valid) after the release was installed | `hy310-sicherung-20260913-release/uboot-env.bin` |
| `../release/h713-hy310-v0.5-beta.tabelle.json`, `.BUILD.txt` | the release's offset table and build stamp | `p7-assets/` (public on GitHub) |

The GPT fixtures are layout v3 and stay valid under v4: v4 changed only how the proprietary files get
into the two ext4 partitions, not the partition table.

Local only (`fixtures-local/device/`, never in the repository): `emmc-voll-20260910-gpt-{primary,backup}.bin`
(full dump of 10.09., **layout v3**, not stock), `hy310-stock-bootloader_b-20260831.fat` (32 MiB FAT16
`Volumn` with `mips/`, vendor), `hy310-stock-env_a-20260831.bin` (stock U-Boot environment, 256 KiB), the
manifests of the small dumps of 12./13.09. (they carry hashes of the secret regions) and their readme.

A stock **full** dump does not exist. For tests that need stock partitions beyond 300 MiB (`misc`,
`private`, `Reserve0`), the golden tests build a fake disk out of the stock GPT plus the contents of the
vendor images (`~/Downloads/update.img`).
