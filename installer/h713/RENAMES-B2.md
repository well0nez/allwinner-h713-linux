# B2 — `h713/gpt.py`: renames old → new

Sources: `I` = `analyse/release/arbeit/r0-fel/hy310-install.py`, `M` = `…/r0-fel/hy310-mkimage.py`,
`X` = `…/r2-extract/h713-extract`.

## Public names

| old | file:line | new | note |
|---|---|---|---|
| `Gpt` | X:632 | `Gpt` | reader, unchanged behaviour |
| `Gpt.ist_gpt` | X:634 | `Gpt.is_gpt` | called at X:2196, X:2964 (B7) |
| `Gpt.tabelle_ok` | X:646 | `Gpt.table_ok` | attribute |
| `Gpt.header_ok`, `.disk_guid`, `.first`, `.last`, `.backup_lba`, `.parts` | X:643–655 | unchanged | `parts` stays per api-h713.md |
| `Gpt.partition` | X:660 | `Gpt.partition` | unchanged |
| `gpt_bauen` | M:294 | `build_layout_gpt` | thin wrapper over `build_gpt` |
| `stock_gpt_bauen` | I:1883 | `build_stock_gpt` | thin wrapper over `build_gpt` |
| — (new, unification of M:294 + I:1883) | — | `build_gpt` | the one builder |
| `gpt_pruefen` | M:344 | `check_gpt` | layout data now parameters, see REPORT.md |
| `SECT` | M:77, I:44 | `SECTOR` | |
| `ENTSZ` | M:81 | `GPT_ENTRY_SIZE` | |
| `NENT` | M:81 | `GPT_ENTRIES` | value 26, **not** 128 — see REPORT.md |
| — | M:337–338, I:1949–1950 | `GPT_HEADER_LBA` = 1, `GPT_ENTRIES_LBA` = 2 | were literals in the returned dict |
| `ARR_SEKT` | M:82 | local `array_sectors` in `build_gpt` | I:1937 computed it locally already |

## Parameters of `build_gpt` (old local names → new)

| old | file:line | new |
|---|---|---|
| `disk_sektoren` | M:294, I:1883 | `disk_sectors` |
| `partitionen` | M:294, I:1883 | `partitions` |
| `diskguid` | M:295, I:1884 | `disk_guid` |
| `typguid` / `TYP` | M:295, I:1899 | `type_guid` |
| `guid_basis` / `basis` / `basis_zahl` | I:1885, 1900, 1901 | `guid_base`, `base`, `base_number` |
| `first_usable`, `last_usable` | I:1903, 1904 | unchanged |
| `nent`, `entsz` | I:1902 | `entry_count`, `entry_size` |
| `entcrc` | M:314, I:1921 | `entry_crc` |
| `arr` | M:304, I:1906 | `arr` (unchanged) |
| `arr_sekt` | I:1937 | `array_sectors` |
| `back_arr` | M:327, I:1938 | `backup_table_lba` |
| `kopf(mylba, altlba, entlba)` | M:316, I:1923 | `header(my_lba, alt_lba, table_lba)` |
| `tab` | M:334 | `table` |
| `e`, `u`, `ende`, `attr`, `name`, `lba`, `sekt` | M:307–312, I:1909–1919 | `e`, `unique_of(...)`, `end`, `attributes_of(...)`, `name`, `lba`, `sectors` |
| — (new: the two builders' differing reserved field, M:320 vs I:1930) | — | `header_reserved` |

## Locals of `check_gpt` (M:344 `gpt_pruefen`)

| old | file:line | new |
|---|---|---|
| `mbr_kopf_tab` | M:344 | `mbr_header_table` |
| `teil_c` | M:344 | `part_c` |
| `hdr`, `p` | M:351, 346 | unchanged |
| `gespeichert` | M:356 | `stored` |
| `roh` | M:357 | `raw` |
| `mylba`, `altlba` | M:361 | `my_lba`, `alt_lba` |
| `entlba`, `nent`, `entsz`, `entcrc` | M:362 | `table_lba`, `nent`, `entsz`, `entry_crc` (the last three keep the header's own names) |
| `gefunden` | M:374 | `found` |
| `soll` | M:381 | `expected` |
| `bhdr`, `bmy`, `balt`, `bent`, `btab`, `bhsz`, `bges`, `broh` | M:386–399 (`bent` M:391) | `bhdr`, `bmy`, `balt`, `btable_lba`, `btab`, `bhsz`, `bstored`, `braw` |
| `TEIL_C_LBA` | M:111 | parameter `part_c_lba` |
| `FIRST_USABLE` | M:79 | parameter `first_usable` |
| `PARTITIONEN` | M:87 | parameter `partitions` |

## Not renamed
Every string that `check_gpt` returns and every string the reader logs is user-visible and stays
byte-identical (German, stage 3 translates them): `"Schutz-MBR ohne 55AA"`, `"CRC des primaeren
GPT-Kopfs stimmt nicht"`, `"GPT: Kopf-CRC …"`, `"Partitionen: …"`, `"Partition {name} (LBA {s},
{c} Sektoren)"`, and the rest.
