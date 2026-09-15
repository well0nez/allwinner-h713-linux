# fixtures/device - Bytes von unserem eigenen HY310, ohne Geheimnisse

Alle Dateien stammen von Marcos HY310 (Board HY260_QZ713_V3.1) oder aus unserem Release; keine enthält
Secure-Storage-, `private`- oder `Reserve0`-Inhalte. Herkunft je Datei (Fable, 14.09.2026, Paket A2):

| Datei | Was | Herkunft |
|---|---|---|
| `hy310-stock-gpt-primary-20260831.bin` | LBA 0-33: Schutz-MBR, GPT-Kopf, 26 Einträge (`bootloader_a` … `Reserve0_a`, `Reserve0_b`, `UDISK`) des **Stock**-Geräts | `re/device-dumps/emmc-first-300mb.bin` (31.08., Stock Android 11), Sektoren 0-33 |
| `hy310-layout-v3-gpt-primary-v0.5-beta.bin` | LBA 0-33 unseres Layouts v3 (`hy310-spl … hy310-rootfs`), wie im Release | erste 17 408 B von `p7-assets/h713-hy310-v0.5-beta-a-bootkette.img` |
| `hy310-layout-v3-gpt-backup-v0.5-beta.bin` | die Backup-GPT (33 Sektoren ab LBA 15269855) | `p7-assets/h713-hy310-v0.5-beta-c-gptkopie.img`, unverändert |
| `hy310-uboot-env-20260913-release.bin` | U-Boot-Umgebung (64 KiB, CRC gültig) des Geräts nach dem Release-Einspielen | `hy310-sicherung-20260913-release/uboot-env.bin` |
| `../release/h713-hy310-v0.5-beta.tabelle.json`, `.BUILD.txt` | Offset-Tabelle und Baustempel des Release | `p7-assets/` (öffentlich auf GitHub) |

Nur lokal (`fixtures-local/device/`, nie ins Repo): `emmc-voll-20260910-gpt-{primary,backup}.bin` (Vollabzug vom
10.09., **Layout v3**, kein Stock), `hy310-stock-bootloader_b-20260831.fat` (32 MiB FAT16 `Volumn` mit `mips/`,
Vendor), `hy310-stock-env_a-20260831.bin` (Stock-U-Boot-Env, 256 KiB), die Manifeste der kleinen Abzüge vom
12./13.09. (enthalten Hashes der geheimen Regionen) und die LIESMICH.

Ein Stock-**Voll**abzug liegt nicht vor; für Tests, die Stock-Partitionen jenseits von 300 MiB brauchen (`misc`,
`private`, `Reserve0`), bauen die Golden-Tests eine Fake-Platte aus der Stock-GPT plus den Inhalten aus den
Herstellerimages (`~/Downloads/update.img`).
