# B6 — renames old → new

`M` = `analyse/release/arbeit/r0-fel/hy310-mkimage.py` (1193 lines),
`I` = `…/r0-fel/hy310-install.py`, `X` = `…/r2-extract/h713-extract`.
Names fixed by `umbau/plan/api-h713.md` are marked **api**; the rest are B6's
choice and free for the reviewer to change.

## `h713/layout.py` (from M:77–204, M:261–293)

| old (M) | new | line |
|---|---|---|
| `SECT` | `SECTOR` | M:77 |
| `DISK_SEKTOREN` | `DISK_SECTORS` **api** | M:78 |
| `FIRST_USABLE` | `FIRST_USABLE` **api** (unchanged) | M:79 |
| `LAST_USABLE` | `LAST_USABLE` **api** (unchanged) | M:80 |
| `NENT` | `GPT_ENTRY_COUNT` | M:81 |
| `ENTSZ` | `GPT_ENTRY_SIZE` | M:81 |
| `ARR_SEKT` | `GPT_ARRAY_SECTORS` | M:82 |
| `TYP_GUID` | `TYPE_GUID` **api** | M:83 |
| `DISK_GUID` | `DISK_GUID` **api** (unchanged) | M:84 |
| `PARTITIONEN` | `PARTITIONS` **api** | M:87 |
| `SPERRE_ERSTER` | `LOCK_FIRST`, imported from `h713.blockdev` **api** | M:98 = I:104 |
| `SPERRE_LETZTER` | `LOCK_LAST`, imported from `h713.blockdev` **api** | M:99 = I:105 |
| `LBA_SPL/UBOOT/ENV/BOOT/ROOTFS` | unchanged **api** | M:101–106 |
| `ENV_BYTES` | `ENV_BYTES` **api** (unchanged) | M:104 |
| `TEIL_A_LBA` | `PART_A_LBA` | M:109 |
| `TEIL_A_SEKT` | `PART_A_SECTORS` | M:109 |
| `TEIL_B_LBA` | `PART_B_LBA` **api** | M:110 |
| `TEIL_C_LBA` | `PART_C_LBA` **api** | M:111 |
| `TEIL_C_SEKT` | `PART_C_SECTORS` **api** | M:112 |
| `PLATZHALTER` | `PLACEHOLDERS` **api** | M:120 |
| `PLATZHALTER_NUTZER` | `USER_PLACEHOLDERS` **api** | M:182 |
| `VERZEICHNISSE_NUTZER` | `USER_DIRECTORIES` **api** | M:186 |
| `RECHTE_ROOTFS` | `ROOTFS_PERMISSIONS` **api** | M:194 |
| `KERNEL_FIT` | `KERNEL_FIT` **api** (unchanged) | M:204 |
| `muster(name, laenge)` | `pattern(name, length)` **api** | M:261 |
| `muster`: local `kern` | `core` | M:269 |
| `ist_nutzer_platzhalter(name)` | `is_user_placeholder(name)` **api** | M:274 |
| `fuellung(name, laenge)` | `filling(name, length)` **api** | M:278 |

## `h713/mkimage.py` (from M:408–1152)

| old (M) | new | line |
|---|---|---|
| `baum_boot(verz, fit, log)` | `tree_boot(directory, fit, log)` **api** | M:408 |
| `baum_rootfs(verz, log)` | `tree_rootfs(directory, log)` **api** | M:437 |
| `_extraktor_laden(pfad)` | **deleted** **api** — `Ext4`/`FileSource` are imported | M:473 |
| `ext4_offsets(datei, pfade, extraktor, log)` | `ext4_offsets(image, paths, log)` **api** | M:494 |
| `ext4_rechte_pruefen(datei, erwartung, extraktor, log)` | `ext4_check_permissions(image, expectation, log)` **api** | M:545 |
| `_kopiere(ziel_f, quelle, log)` | `_copy(target_f, source, log)` **api** | M:582 |
| `uboot_version(pfad)` | `uboot_version(path)` **api** (unchanged) | M:594 |
| `bauen(args)` | `build(args)` **api** | M:612 |
| `pruefen(tabelle_datei, log)` | `check(table_file, log)` **api** | M:894 |
| `BETA_WARNUNG` | `BETA_WARNING` **api** | M:1019 |
| `liesmich_text(d)` | `readme_text(d)` **api** | M:1040 |
| `VERSION` | `VERSION` (unchanged, "0.1") | M:70 |
| class `K` | `h713.log.console` **api** — see REPORT.md, finding 1 | M:213 |
| `mib` | `h713.util.mib` **api** | M:209 |
| `_rel` | `h713.util.relpath_or_abs` **api** | M:241 |
| `sha256_datei` | `h713.util.sha256_file` **api** | M:250 |
| `gpt_bauen` | `h713.gpt.build_layout_gpt` **api** | M:294 |
| `gpt_pruefen` | `h713.gpt.check_gpt` **api** | M:344 |
| (new) | `_block_map(fs, ino, inode)` — wrapper around `Ext4._karte`, REPORT.md finding 2 | — |

### local names inside the moved functions

`verz`→`directory`, `ziel`→`target`, `quelle`→`source`, `kopf`→`head`,
`groesse`→`size`, `teil`→`part`, `pfad`→`path`, `laenge`→`length`,
`karte`→`block_map`, `gesehen`→`seen`, `erw_p`→`expected_p`, `roh`→`raw`,
`probleme`→`problems`, `ist`→`actual`, `erwartung`→`expectation`,
`hier`→`here`, `wurzel`→`project_root`, `vorgabe`→`under_root`,
`baustein`→`building_block`, `stamm`→`stem`, `basis`→`base`,
`a_datei/b_datei/c_datei/t_datei`→`a_file/b_file/c_file/t_file`,
`was`→`what`, `ver`→`version`, `env_roh`→`env_raw`,
`env_eintraege`→`env_entries`, `soll_b`→`want_b`, `teile`→`pieces`,
`teil_liste`→`piece_list`, `daten`→`data`, `tabelle`→`table`,
`nutzer`→`user`, `alle`→`all_entries`, `basis_boot/basis_root`→
`base_boot/base_root`, `liesmich`→`readme`, `gesamt`→`total`,
`tabelle_datei`→`table_file`, `schlecht`→`bad`, `erster/letzter`→`first/last`,
`beruehrt`→`touched`, `beide`→`both`, `offen`→`unfilled`,
`gefuellt`→`filled`, `kaputt`→`broken`, `sperre_von/sperre_bis`→
`lock_from/lock_to`, `ende`→`end`, `z`→`lines` (in `readme_text`).

### NOT renamed (deliberately)

* every printed string, the wording of every `SystemExit`, `BETA_WARNING` and
  the whole of `readme_text` — stage-1 rule, compared byte for byte by the
  golden tests;
* the keys of the table/manifest JSON (`teile`, `datei`, `sektoren`, `loch`,
  `bausteine`, `platzhalter`, `platzhalter_datei`, `platzhalter_nutzer`,
  `platzhalter_info`, `ziel`, `laenge`, `quelle`, `fuellung`,
  `sha256_muster`, `werkzeug`, `abbild`, `erzeugt`, `sektorgroesse`,
  `disk_sektoren`, `warum`, `partitionen`, `eintraege`) — `hy310-install`
  reads them and the released v0.5-beta table carries them;
* `inode["groesse"]` in `ext4_offsets` — B3's brief says the dicts of
  `h713.fs.ext4` keep their keys (REPORT.md, finding 2);
* `fs._karte` as the fallback spelling in `_block_map` (same finding).
