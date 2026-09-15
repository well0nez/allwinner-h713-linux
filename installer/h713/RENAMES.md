# Rename map of stage 1 (doku/121): old German name, source file:line -> new English name


## RENAMES-B1

# RENAMES - package B1 (`h713/util.py`, `h713/imagewty.py`, `h713/fex.py`)

Sources: `I` = `analyse/release/arbeit/r0-fel/hy310-install.py`, `M` = `…/r0-fel/hy310-mkimage.py`,
`X` = `…/r2-extract/h713-extract`. Line numbers are those of the source file.

## h713/util.py

| old | where | new |
|---|---|---|
| `mib(b)` | I:108, M:209 | `mib(b)` (unchanged) |
| `dauer(sekunden)` | I:112 | `duration(seconds)` |
| `_rel(p, basis)` | M:241 | `relpath_or_abs(p, base)` |
| `sha256_datei(pfad, stueck=8 << 20)` | M:250 | `sha256_file(path, chunk=8 << 20, log=None)` - one function |
| `sha256_datei(pfad, log=None)` | X:314 | `sha256_file(path, chunk=8 << 20, log=None)` - same function |
| `sha256_bytes(b)` | X:310 | `sha256_bytes(b)` (unchanged) |
| `hexdump_kurz(b, n=16)` | X:330 | `hexdump_short(b, n=16)` |
| `crc32(b)` | X:627 | `crc32(b)` (unchanged; `import zlib` moved to module level) |

## h713/imagewty.py

| old | where | new |
|---|---|---|
| `Imagewty` | X:547 | `Imagewty` (unchanged) |
| `Imagewty.ist_imagewty(q)` | X:551 | `Imagewty.is_imagewty(q)` |
| `Imagewty.eintraege` | X:584 | `Imagewty.entries` |
| `Imagewty.datei(name)` | X:616 | `Imagewty.file(name)` |
| local `ende` | X:608 | `end` |
| `SunxiPackage` | X:867 | `SunxiPackage` (unchanged) |
| `SunxiPackage.__init__(… herkunft)` / `self.herkunft` | X:871, X:873 | `… origin` / `self.origin` |
| `SunxiPackage.probleme` | X:879 | `SunxiPackage.problems` |
| local `summe` | X:891 | `total` |
| `SunxiPackage.summe_ok` | X:892 | `SunxiPackage.checksum_ok` |
| `SunxiPackage.item(name)` | X:916 | `SunxiPackage.item(name)` (unchanged) |
| `suche_sunxi_packages(q, log, max_bytes)` | X:923 | `find_sunxi_packages(q, log, max_bytes)` |
| locals `treffer`, `ueberlapp`, `ende` | X:925-927 | `hits`, `overlap`, `end` |
| `uboot_kennung(ub)` | X:941 | `uboot_version_string(ub)` |
| `fdt_wurzel(dtb)` | X:947 | `fdt_root(dtb)` |
| local `tiefe` | X:953 | `depth` |
| `pruefe_scp(scp, log)` | X:982 | `check_scp(scp, log)` |
| locals `befunde`, `ziel`, `kopf`, `gespiegelt` | X:984, 994, 999, 1005 | `findings`, `target`, `head`, `mirrored` |

## h713/fex.py

| old | where | new |
|---|---|---|
| `stock_plan(ex, image_q) -> (img, partitionen, roh)` | I:1621 | `stock_plan(image) -> (partitions, raw)` - no longer builds the Imagewty, no longer returns it |
| the `[partition]` loop inside `stock_plan` | I:1636-1650 | `parse_sys_partition(text)` (own function) |
| locals `partitionen`, `sekt`, `roh` | I:1634-1653 | `partitions`, `sect`, `raw` |
| (new, per brief) 24 u32 at boot0+0x38 | - | `dram_block(boot0)`, field names `DRAM_FIELDS` as in A1 `image_facts.py:39` = `fixtures-local/skripte/imgdump.py:38` |
| `lies_ini(text)` | X:1815 | `parse_ini(text)` |
| locals `sekt`, `akt`, `z` | X:1817-1819 | `sect`, `cur`, `line` |
| `zahlen(v)` | X:1832 | `ini_numbers(v)` |
| `panel_config_id(text)` | X:1987 | `panel_config_id(text)` (unchanged) |
| locals `_sekt`, `paare` | X:1989 | `_sect`, `pairs` |

## Names imported from packages that are not merged yet (stand-ins in `stub/h713/`)

| old (loaded by path from X) | where | new name used by B1 | owner |
|---|---|---|---|
| `Log` | X:280 | `h713.log.Log` | B4 |
| `Abbruch` | X:306 | `h713.log.Abort` | B4 |
| `Quelle` | X:338 | `h713.source.Source` | B3 |
| `DateiQuelle` | X:353 | `h713.source.FileSource` | B3 |
| `TeilQuelle` | X:370 | `h713.source.SliceSource` | B3 |
| `SparseQuelle` | X:389 | `h713.source.SparseSource` | B3 |
| `KettenQuelle` | X:475 | `h713.source.ChainSource` | B3 |
| `NullQuelle` | X:1130 | `h713.source.NullSource` | B3 |
| `materialisiere` | X:508 | `h713.source.materialize` | B3 |

## RENAMES-B2

# B2 - `h713/gpt.py`: renames old → new

Sources: `I` = `analyse/release/arbeit/r0-fel/hy310-install.py`, `M` = `…/r0-fel/hy310-mkimage.py`,
`X` = `…/r2-extract/h713-extract`.

## Public names

| old | file:line | new | note |
|---|---|---|---|
| `Gpt` | X:632 | `Gpt` | reader, unchanged behaviour |
| `Gpt.ist_gpt` | X:634 | `Gpt.is_gpt` | called at X:2196, X:2964 (B7) |
| `Gpt.tabelle_ok` | X:646 | `Gpt.table_ok` | attribute |
| `Gpt.header_ok`, `.disk_guid`, `.first`, `.last`, `.backup_lba`, `.parts` | X:643-655 | unchanged | `parts` stays per api-h713.md |
| `Gpt.partition` | X:660 | `Gpt.partition` | unchanged |
| `gpt_bauen` | M:294 | `build_layout_gpt` | thin wrapper over `build_gpt` |
| `stock_gpt_bauen` | I:1883 | `build_stock_gpt` | thin wrapper over `build_gpt` |
| - (new, unification of M:294 + I:1883) | - | `build_gpt` | the one builder |
| `gpt_pruefen` | M:344 | `check_gpt` | layout data now parameters, see REPORT.md |
| `SECT` | M:77, I:44 | `SECTOR` | |
| `ENTSZ` | M:81 | `GPT_ENTRY_SIZE` | |
| `NENT` | M:81 | `GPT_ENTRIES` | value 26, **not** 128 - see REPORT.md |
| - | M:337-338, I:1949-1950 | `GPT_HEADER_LBA` = 1, `GPT_ENTRIES_LBA` = 2 | were literals in the returned dict |
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
| `e`, `u`, `ende`, `attr`, `name`, `lba`, `sekt` | M:307-312, I:1909-1919 | `e`, `unique_of(...)`, `end`, `attributes_of(...)`, `name`, `lba`, `sectors` |
| - (new: the two builders' differing reserved field, M:320 vs I:1930) | - | `header_reserved` |

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
| `bhdr`, `bmy`, `balt`, `bent`, `btab`, `bhsz`, `bges`, `broh` | M:386-399 (`bent` M:391) | `bhdr`, `bmy`, `balt`, `btable_lba`, `btab`, `bhsz`, `bstored`, `braw` |
| `TEIL_C_LBA` | M:111 | parameter `part_c_lba` |
| `FIRST_USABLE` | M:79 | parameter `first_usable` |
| `PARTITIONEN` | M:87 | parameter `partitions` |

## Not renamed
Every string that `check_gpt` returns and every string the reader logs is user-visible and stays
byte-identical (German, stage 3 translates them): `"Schutz-MBR ohne 55AA"`, `"CRC des primaeren
GPT-Kopfs stimmt nicht"`, `"GPT: Kopf-CRC …"`, `"Partitionen: …"`, `"Partition {name} (LBA {s},
{c} Sektoren)"`, and the rest.

## RENAMES-B3

# B3 - rename map (old → new)

Sources: `X` = `analyse/release/arbeit/r2-extract/h713-extract`, `I` = `analyse/release/arbeit/r0-fel/hy310-install.py`.
Line numbers point at the **old** definition. Public names follow the package API of doku/121 §4 (stage 1); private helpers, parameters
and locals are translated freely. Every user-visible string and every **dict key** stays byte-identical (see the last
section) - only identifiers change.

## `h713/source.py` (X:338-546, X:1130-1136)

| old | new | old line |
|---|---|---|
| `Quelle` | `Source` | X:338 |
| `Quelle.backing` / `.sub` / `.read` / `.size` / `.name` | unchanged | X:341-350 |
| `DateiQuelle` | `FileSource` | X:353 |
| `DateiQuelle.pfad` (attr, param) | `FileSource.path` | X:354 |
| `TeilQuelle` | `SliceSource` | X:370 |
| `SparseQuelle` | `SparseSource` | X:389 |
| `SparseQuelle.ist_sparse` (static) | `SparseSource.is_sparse` | X:395 |
| `SparseQuelle.beschreibung` | `SparseSource.description` | X:433 |
| `SparseQuelle._finde` | `SparseSource._find` | X:437 |
| `SparseQuelle.bereiche` | `SparseSource.regions` | X:470 |
| local `typen` | `types` | X:410 |
| `KettenQuelle` | `ChainSource` | X:475 |
| `KettenQuelle.teile` (attr, param) | `ChainSource.parts` | X:477-479 |
| `NullQuelle` | `NullSource` | X:1130 |
| `materialisiere(q, ziel, log)` | `materialize(q, target, log)` | X:508 |

## `h713/fs/fat16.py` (X:674-866)

| old | new | old line |
|---|---|---|
| `Fat.ist_fat` (static) | `Fat.is_fat` | X:688 |
| `__init__(q, log, herkunft)` | `__init__(q, log, origin)` | X:695 |
| `self.herkunft` | `self.origin` | X:696 |
| `self.probleme` | `self.problems` | X:697 |
| `self.cluster_zahl` | `self.cluster_count` | X:719 |
| `self.typ` (FAT12/16/32) | `self.type` | X:721 |
| `self.beschreibung` | `self.description` | X:727 |
| local `hinweis` | `note` | X:735 |
| `_naechster` | `_next` | X:746 |
| `kette(c, max_cluster)` | `chain(c, max_cluster)` | X:761 |
| locals `gesehen` | `seen` | X:763 |
| `_cluster_offset` | unchanged | X:774 |
| `_lfn_teil` | `_lfn_part` | X:780 |
| local `roh` | `raw` | X:781 |
| `_roh_verzeichnis` | `_raw_directory` | X:789 |
| `eintraege(cluster=0)` | `entries(cluster=0)` | X:794 |
| locals `basis`, `erw`, `kurz`, `lang`, `teil`, `groesse` | `base`, `ext`, `short`, `long_name`, `part`, `size` | X:812-825 |
| `verzeichnis(pfad)` | `directory(path)` | X:832 |
| locals `teil`, `treffer` | `part`, `hits` | X:835-836 |
| `lies(e)` | `read(e)` | X:842 |
| locals `noetig`, `teile`, `gelesen` | `needed`, `parts`, `got` | X:844-846 |

`ATTR_LFN`, `ATTR_VOLUME`, `ATTR_DIR`, `bps`, `spc`, `reserved`, `nfats`, `root_entries`, `total`, `fatsz`,
`root_cluster`, `fat_start`, `root_start`, `data_start`, `cluster_bytes`, `eoc`, `label`, `_fat`: unchanged.

## `h713/fs/lpsuper.py` (X:1024-1128)

| old | new | old line |
|---|---|---|
| `_lies_metadaten(moff, log, lage)` | `_read_metadata(moff, log, location)` | X:1062 |
| `self.lage` | `self.location` | X:1106 |
| `self.geraete` | `self.devices` | X:1107 |
| locals `basis`, `kandidaten`, `gefunden` | `base`, `candidates`, `found` | X:1050-1053 |
| locals `gruppen`, `geraete`, `groesse` | `groups`, `devices`, `size` | X:1090-1101 |
| local `teile` in `partition()` | `pieces` | X:1118 |
| `SEKTOR` (X:273, module level) | `SECTOR` (module level here) | X:273 |
| `partition(name, log)`, `self.parts`, `self.version`, `GEO_MAGIC`, `HDR_MAGIC` | unchanged | X:1024-1114 |

## `h713/fs/ext4.py` (X:1142-1673)

| old | new | old line |
|---|---|---|
| `Ext4Basis` | `Ext4Base` | X:1142 |
| `beschreibung` (class attr) | `description` | X:1150 |
| `lies(pfad, tmp)` | `read(path, tmp)` | X:1156, 1563, 1659 |
| `existiert(pfad)` | `exists(path)` | X:1159 |
| `gehe(wurzel, max_tiefe)` | `walk(root, max_depth)` | X:1166 |
| locals `offen`, `pfad`, `tiefe`, `voll` | `open_list`, `path`, `depth`, `full` | X:1168-1175 |
| `Ext4.WURZEL` | `Ext4.ROOT` | X:1194 |
| `self.probleme` | `self.problems` | X:1223 |
| `self.beschreibung` | `self.description` | X:1251, 1599 |
| local `wie` (feature loop) | `what` | X:1262 |
| `self.hat_64bit` | `self.has_64bit` | X:1269 |
| `self.hat_filetype` | `self.has_filetype` | X:1273 |
| `self.gruppen` | `self.groups` | X:1274 |
| `self.inode_tabelle` | `self.inode_table` | X:1282 |
| `self.aufbau` | `self.structure` | X:1288 |
| `self._karten_cache` | `self._map_cache` | X:1295 |
| `_block(nr, anzahl)` | `_block(nr, count)` | X:1304 |
| local `hinweis` | `note` | X:1315 |
| `_typ(mode)` (static) | `_type(mode)` | X:1331 |
| locals `roh`, `typ`, `groesse` in `inode()` | `raw`, `ftype`, `size` | X:1343-1352 |
| `_extent_knoten(roh, ino, out, tiefe)` | `_extent_node(raw, ino, out, level)` | X:1371 |
| locals `belegt`, `laenge`, `kind` | `written`, `length`, `child` | X:1385-1394 |
| `_indirekt(nr, stufe, start, karte, grenze)` | `_indirect(nr, level, start, mapping, limit)` | X:1397 |
| locals `pro`, `spanne` | `per`, `span` | X:1399-1400 |
| `_karte(ino, inode)` | `_map(ino, inode)` | X:1415 |
| local `karte` | `mapping` | X:1424 |
| `_daten(ino, inode)` | `_data(ino, inode)` | X:1443 |
| locals `groesse`, `belegt` | `size`, `filled` | X:1444-1450 |
| `_ist_schneller_symlink` | `_is_fast_symlink` | X:1465 |
| `symlink_ziel(ino, inode)` | `symlink_target(ino, inode)` | X:1470 |
| local `roh` | `raw` | X:1473 |
| `_verzeichnis(ino)` | `_directory(ino)` | X:1481 |
| locals `daten`, `kind` | `data`, `child` | X:1486-1492 |
| `_kind(ino, name)` | `_child(ino, name)` | X:1509 |
| local `kino` | `child_ino` | X:1510 |
| `pfad_ino(pfad, folge_letzten)` | `path_inode(path, follow_last)` | X:1515 |
| locals `komp`, `kind`, `kinode`, `ziel` | `parts`, `child`, `child_inode`, `target` | X:1518-1535 |
| locals `eintraege`, `ki` in `ls()` | `entries`, `ci` | X:1549-1557 |
| `statistik()` | `stats()` | X:1572 |
| `Ext4Debugfs.datei` | `Ext4Debugfs.file` | X:1606 |
| `_roh(cmds)` | `_raw(cmds)` | X:1619 |
| local `akt` | `current` | X:1623 |
| locals `eintraege`, `ziel` | `entries`, `target` | X:1637, 1660 |
| `MAGIC`, `INCOMPAT_*`, `ROCOMPAT_*`, `FL_*`, `EXT_MAGIC`, `MAX_SYMLINK`, `BLOCK_CHUNK`, `ls`, `inode`, `stat`, `label_fs`, `dev`, `_cache`, `_dir_cache`, `_inode_cache` | unchanged | - |

## `h713/fs/sparse.py` (I:1656-1731)

| old | new | old line |
|---|---|---|
| `ist_sparse(kopf)` | `is_sparse(header)` | I:1661 |
| `sparse_schreiben(platte, d, plba, trocken=False)` | `write_sparse(disk, data, part_lba, dry_run=False)` | I:1666 |
| `platte.schreib(...)` (call) | `disk.write(...)` | I:1688 |
| inner `schreib_am(bl, daten)` | `write_at(bl, buf)` | I:1687 |
| locals `happen`, `pos`, `block`, `geschrieben` | `step`, `pos`, `block`, `written` | I:1684-1685 |
| locals `typ`, `quelle`, `laenge` | `ctype`, `src`, `length` | I:1691-1692 |
| locals `muster`, `gesamt`, `voll`, `null` | `pattern`, `total`, `full`, `zeros` | I:1701-1715 |
| `SECT` (I:44) | `SECTOR` (module level here) | I:44 |
| `SPARSE_MAGIC`, `_CHUNK_RAW`, `_CHUNK_FILL`, `_CHUNK_DONT_CARE`, `_CHUNK_CRC32` | unchanged | I:1656-1657 |

## Deliberately **not** renamed (stage 1)

* **Dict keys** - the extractor's JSON (`MANIFEST.json`) and `BERICHT.txt` are built from them:
  * `Fat.entries()`: `name`, `kurz`, `lang`, `verzeichnis`, `cluster`, `groesse`, `attr`
  * `LpSuper.parts[…]`: `attrs`, `extents`, `size`, `gruppe`
  * `Ext4.ls()` / `Ext4Debugfs.ls()`: `name`, `ino`, `mode`, `size`, `typ`
  * `Ext4.inode()`: `ino`, `mode`, `typ`, `uid`, `gid`, `links`, `flags`, `blocks_lo`, `file_acl`, `i_block`,
    `groesse`, `groesse_ls`
  * `Ext4.stat`: `inodes`, `extent_inodes`, `indirekt_inodes`, `extent_max_tiefe`, `extent_knoten`, `extents`,
    `unbelegte_extents`, `loecher`, `symlink_schnell`, `symlink_block`, `verzeichnisse`, `htree_verzeichnisse`,
    `gelesene_bytes` (they only feed the text of `stats()`, but they are frozen with the rest)
* **All user-visible strings** stay German and byte-identical: log lines, `Abort` messages, `description`
  (goes into `eingang.vendor_fs` / `eingang.super_sparse`), `structure`, `stats()`, the LP location values
  `"primär"`/`"backup"`, `RuntimeError` texts of the sparse writer.

## For the callers (package B7, `extract.py`)

`fs.typ` → `fs.type`, `fs.beschreibung` → `fs.description`, `fs.probleme` → `fs.problems`,
`fs.eintraege(0)` → `fs.entries(0)`, `fs.verzeichnis(…)` → `fs.directory(…)`, `fs.lies(e)` → `fs.read(e)`,
`sq.beschreibung` → `sq.description`, `lp.lage` → `lp.location`, `lp.geraete` → `lp.devices`,
`vendor.lies(p, tmp)` → `vendor.read(p, tmp)`, `vendor.existiert(p)` → `vendor.exists(p)`,
`vendor.gehe(p, n)` → `vendor.walk(p, n)`, `vendor.statistik()` → `vendor.stats()`,
`vendor.probleme` → `vendor.problems`, `Quelle`-typed annotations → `Source`.

## RENAMES-B4

# B4 - renames (old → new)

Sources: `I` = `analyse/release/arbeit/r0-fel/hy310-install.py`, `X` = `analyse/release/arbeit/r2-extract/h713-extract`.
Line numbers are the **origin** line. Printed strings are not renamed - they are byte-identical (stage 1).

## `h713/log.py`

| old | origin | new |
|---|---|---|
| `Log` | X:280 | `Log` |
| `Log.zeilen` | X:282 | `Log.lines` |
| `Log.warnungen` | X:283 | `Log.warnings` |
| `Log._p` | X:286 | `Log._p` |
| `Log.info` | X:291 | `Log.info` |
| `Log.kopf` | X:294 | `Log.heading` † |
| `Log.warn` | X:298 | `Log.warn` |
| `Log.fehler` | X:302 | `Log.error` |
| `Abbruch` | X:306 | `Abort` |
| `Konsole` | I:118 | `Console` |
| `Konsole.__init__(farbe=None)` | I:121 | `Console.__init__(color=None)` |
| `Konsole.f` (attribute) | I:124 | `Console.color` |
| `Konsole._c` | I:126 | `Console._c` |
| `Konsole.schritt` | I:129 | `Console.step` |
| `Konsole.ok` / `.warn` / `.info` | I:132/135/138 | `Console.ok` / `.warn` / `.info` |
| `Konsole.fehler` | I:141 | `Console.error` |
| `K` (module level) | I:145 | `console` |
| `_Still` | I:148 | `Quiet` |

† `kopf` is not fixed by `api-h713.md`; B4 chose `heading`. The other users of `Log` (B7 `extract.py`,
B1 `util.py`'s `sha256_file(log=…)`) must use that name.

## `h713/blockdev.py`

| old | origin | new |
|---|---|---|
| `SECT` | I:44 | `SECT` (unchanged - see REPORT.md §4) |
| `SECTORS_EXPECTED` | I:45 | `SECTORS_EXPECTED` |
| `SPERRE_ERSTER` | I:104 | `LOCK_FIRST` |
| `SPERRE_LETZTER` | I:105 | `LOCK_LAST` |
| `Platte` | I:167 | `Disk` |
| `Platte(pfad, schreiben, exklusiv)` | I:172 | `Disk(path, writable, exclusive)` |
| `.pfad` / `.schreiben` / `.sektoren` | I:173/174/236 | `.path` / `.writable` / `.sectors` |
| `_groesse` | I:238 | `_size` |
| `lies(lba, sektoren)` | I:252 | `read(lba, sectors)` |
| `schreib(lba, daten)` | I:264 | `write(lba, data)` |
| `sync` / `close` | I:280/286 | `sync` / `close` |
| `eingehaengt(pfad, roh=False)` | I:291 | `mounted(path, raw=False)` |
| `aushaengen(pfad, log=None)` | I:316 | `unmount(path, log=None)` |
| `ist_unser_geraet(pfad)` | I:347 | `device_kind(path)` |
| `finde_laufwerk(erwartet=…)` | I:384 | `find_drive(expected=…)` |
| `_um_sperre(lba, daten)` | I:613 | `_around_lock(lba, data)` |

Locals: `offen`→`open_ones`, `ruhig`→`calm`, `letzter`→`last`, `versuch`→`attempt`, `teile`→`parts`,
`blick`→`view`, `ende`→`end`, `treffer`→`hits`, `zeilen`→`lines`, `basis`→`base`, `quelle`→`source`,
`ausgehaengt`→`unmounted`, `geblieben`→`left`, `befehl`→`command`, `kopf`→`head`, `namen`→`names`,
`wechsel`→`removable`, `vor`→`before`, `nach_lba`→`after_lba`.

## `h713/env.py`

| old | origin | new |
|---|---|---|
| `ENV_LBA` | I:53 | `ENV_LBA` |
| `ENV_SEKTOREN` | I:54 | `ENV_SECTORS` |
| `ENV_BYTES` | I:55 | `ENV_BYTES` |
| `ENV_UEBERNEHMEN` | I:65 | `ENV_CARRY_OVER` |
| `env_lesen(roh)` | I:68 | `env_read(raw)` |
| `env_schreiben(d)` | I:87 | `env_write(d)` |

Locals: `aus`→`out`, `nutz`→`payload`.

## `h713/fel.py`

| old | origin | new |
|---|---|---|
| `FEL_VID_PID` | I:46 | `FEL_VID_PID` |
| `fel_werkzeug(vorgabe=None)` | I:420 | `fel_tool(given=None)` |
| `fel_da(fel)` | I:437 | `fel_present(fel)` |
| `fel_anleitung()` | I:448 | `fel_instructions()` |

Locals: `hier`→`here`, `gefunden`→`found`.

## RENAMES-B5

# B5 - renames (old → new)

Source: `I` = `analyse/release/arbeit/r0-fel/hy310-install.py` (unchanged). Line numbers are the
**origin** line in `I`. Printed strings, prompts, manifest keys, file names and exit codes are not
renamed - they are byte-identical (stage 1). The attributes of `args` are argparse `dest` names and
therefore the CLI contract of B8: `args.abzug`, `args.sicherung`, `args.vendor`, `args.extraktor`,
`args.arbeitskopie`, `args.env_neu`, `args._unser_layout`, `args.authorized_key`, `args.dry_run`
stay German. The same holds for the keys of the image table (`teile`, `datei`, `lba`, `bytes`,
`loch`, `platzhalter`, `platzhalter_nutzer`, `platzhalter_datei`, `bausteine`, `disk_sektoren`).

`tests/test_faithful.py` carries this map in machine-readable form and proves with it that the
abstract syntax trees of old and new are equal.

## `h713/dump.py`

| old | origin | new |
|---|---|---|
| `VERSION` | I:42 | `VERSION` (tool version, see REPORT.txt §4.1) |
| `EINMALIG` | I:95 | `UNIQUE_REGIONS` (with the orphaned comment I:48-50) |
| `abzug_klein(platte, ziel, log=K, unser_layout=False)` | I:462 | `dump_small(disk, target, log=console, our_layout=False)` |
| `abzug_voll(platte, datei, log=K)` | I:526 | `dump_full(disk, file, log=console)` |
| `pruefe_abzug(platte, datei, stichproben=8)` | I:554 | `verify_dump(disk, file, samples=8)` |
| `waehle_abzug(args)` | I:925 | `choose_dump(args)` |
| `_manifest_schreiben(verzeichnis, manifest, geraet)` | I:1405 | `write_manifest(directory, manifest, device)` |

Locals: `zweck`→`purpose`, `daten`→`data`, `pfad`→`path`, `leer`→`empty`, `ist_leer`→`is_empty`,
`geheim`→`secret`, `umg`→`raw_env`, `absicht`→`intent`, `gesamt`→`total`, `stueck`→`chunk`,
`getan`→`done`, `v`→`speed`, `rest`→`left`, `fest`→`fixed`, `stellen`→`places`, `soll`→`want`,
`schlecht`→`bad`, `a`→`answer`, `z`→`p` (the purpose in the manifest comprehension).

## `h713/verify.py`

| old | origin | new |
|---|---|---|
| `abbild_schreiben(platte, datei, log=K, lba0=0)` | I:575 | `write_image(disk, file, log=console, lba0=0)` |
| `pruefe_abbild(platte, datei, stichproben=6, log=K, lba0=0)` | I:627 | `verify_image(disk, file, samples=6, log=console, lba0=0)` |

Locals: `gesamt`→`total`, `stueck`→`chunk`, `getan`→`done`, `ende`→`end`, `teil_lba`→`part_lba`,
`teil`→`part`, `v`→`speed`, `stellen`→`places`, `soll`→`want`, `ist`→`got`, `fehler`→`errors`.
`_um_sperre` (I:613) is `blockdev._around_lock` (B4) and is imported, not copied.

## `h713/stock.py`

| old | origin | new |
|---|---|---|
| `stock_zurueck(platte, image_datei, extraktor=None, log=K, trocken=False)` | I:1732 | `restore_stock(disk, image_file, extractor=None, log=console, dry_run=False)` |

Locals: `partitionen`→`partitions`, `roh`→`raw`, `ziel_lba`→`target_lba`, `geschrieben`→`written`,
`fehlend`→`missing`, `daten`→`data`, `quelle`→`source`, `psekt`→`psect`, `DATEISYSTEME`→`FILESYSTEMS`,
`NICHT_NULLEN`→`DO_NOT_ZERO`, `KOPF_SEKT`→`HEAD_SECTORS`, `null`→`zeros`, `rest`→`left`, `sekt`→`sect`,
`getan`→`done`, `hier`→`here`, `pfad_blob`→`blob_path`.

Called instead of the runtime-loaded extractor (api-h713.md): `ex.DateiQuelle` → `source.FileSource`,
`ex.Imagewty.ist_imagewty` → `imagewty.Imagewty.is_imagewty`, `stock_plan(ex, q)` (I:1621) →
`fex.stock_plan(Imagewty(q, Log()))`, `stock_gpt_bauen` (I:1883) → `gpt.build_stock_gpt`,
`ist_sparse` (I:1661) → `fs.sparse.is_sparse`, `sparse_schreiben` (I:1666) → `fs.sparse.write_sparse`.

## `h713/install.py`

| old | origin | new |
|---|---|---|
| `platzhalter_fuellen(abbild, tabelle, quellen, log=K)` | I:656 | `fill_placeholders(image, table, sources, log=console)` |
| `SCHLUESSEL_ARTEN` | I:691 | `KEY_TYPES` |
| `schluessel_lesen(pfad, laenge)` | I:696 | `read_public_key(path, length)` |
| `nutzer_quellen(args, nutzer, log=K)` | I:733 | `user_sources(args, user, log=console)` |
| `platzhalter_pruefen(abbild, tabelle, quellen)` | I:759 | `check_placeholders(image, table, sources)` |
| `abbild_paket(pfad)` | I:772 | `image_package(path)` |
| `paket_pruefen(verz, d, log=K)` | I:799 | `check_package(directory, d, log=console)` |
| `OPTIONALE_GRUPPEN` | I:837 | `OPTIONAL_GROUPS` |
| `vendor_quellen(verz, tabelle, log=K)` | I:840 | `vendor_sources(directory, table, log=console)` |
| `extrahieren(abzug, ziel, extraktor=None, log=K)` | I:881 | `run_extractor(dump, target, extractor=None, log=console)` |
| `frage(text, vorgabe=None)` | I:899 | `ask(text, default=None)` |
| `bestaetigen(was)` | I:909 | `confirm(what)` |
| `env_uebernehmen(args, tab, arbeit, teil_datei, log=K)` | I:1222 | `carry_env(args, tab, work, part_file, log=console)` |
| `_paket_schreiben(args, platte, pfad, verz, tab)` | I:1277 | `write_package(args, disk, path, directory, tab)` |
| `_extraktor_laden(pfad=None)` | I:1436 | `_load_extractor(path=None)` (see REPORT.txt §4.2) |

Locals: `abbild`→`image`, `tabelle`→`table`, `quellen`→`sources`, `fehlend`→`missing`,
`laenge`→`length`, `daten`→`data`, `roh`→`raw`, `zeilen`→`lines`, `z`→`line`, `a`→`kind` (the key
type), `treffer`→`hits`, `inhalt`→`content`, `nutzer`→`user`, `fremd`→`unknown`, `schlecht`→`bad`,
`verz`→`directory`, `loch`→`hole`, `gross`→`too_big`, `klein`→`too_small`, `praefix`→`prefix`,
`gruppe`→`group`, `weg`→`gone`, `abzug`→`dump`, `ziel`→`target`, `vorgabe`→`default`, `a`→`answer`
(the answer in `ask`), `was`→`what`, `arbeit`→`work`, `teil_datei`→`part_file`, `baustein`→`block`,
`alt_pfad`→`old_path`, `alt`→`old`, `teil_lba`→`part_lba`, `neu`→`new`, `genommen`→`taken`,
`gewaehlt`→`chosen`, `voll`→`full`, `eigene`→`own`, `quelle_teil`→`source_part`, `datei`→`file`,
`fehler`→`errors`, `vorher`→`before`, `nachher`→`after`, `hier`→`here`, `kandidat`→`candidate`.

## Names of B1-B4 this package calls

`K`→`console`, `_Still`→`Quiet` (`h713.log`); `Platte`→`Disk`, `lies`→`read`, `schreib`→`write`,
`sektoren`→`sectors`, `pfad`→`path`, `SPERRE_ERSTER`→`LOCK_FIRST`, `SPERRE_LETZTER`→`LOCK_LAST`,
`_um_sperre`→`_around_lock` (`h713.blockdev`); `env_lesen`→`env_read`, `env_schreiben`→`env_write`,
`ENV_SEKTOREN`→`ENV_SECTORS`, `ENV_UEBERNEHMEN`→`ENV_CARRY_OVER` (`h713.env`); `mib`, `dauer`→`duration`
(`h713.util`); `Konsole.fehler`→`Console.error`, `Konsole.schritt`→`Console.step` (`h713.log`).

## RENAMES-B6

# B6 - renames old → new

`M` = `analyse/release/arbeit/r0-fel/hy310-mkimage.py` (1193 lines),
`I` = `…/r0-fel/hy310-install.py`, `X` = `…/r2-extract/h713-extract`.
Names fixed by the package API of doku/121 §4 (stage 1) are marked **api**; the rest are B6's
choice and free for the reviewer to change.

## `h713/layout.py` (from M:77-204, M:261-293)

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
| `LBA_SPL/UBOOT/ENV/BOOT/ROOTFS` | unchanged **api** | M:101-106 |
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

## `h713/mkimage.py` (from M:408-1152)

| old (M) | new | line |
|---|---|---|
| `baum_boot(verz, fit, log)` | `tree_boot(directory, fit, log)` **api** | M:408 |
| `baum_rootfs(verz, log)` | `tree_rootfs(directory, log)` **api** | M:437 |
| `_extraktor_laden(pfad)` | **deleted** **api** - `Ext4`/`FileSource` are imported | M:473 |
| `ext4_offsets(datei, pfade, extraktor, log)` | `ext4_offsets(image, paths, log)` **api** | M:494 |
| `ext4_rechte_pruefen(datei, erwartung, extraktor, log)` | `ext4_check_permissions(image, expectation, log)` **api** | M:545 |
| `_kopiere(ziel_f, quelle, log)` | `_copy(target_f, source, log)` **api** | M:582 |
| `uboot_version(pfad)` | `uboot_version(path)` **api** (unchanged) | M:594 |
| `bauen(args)` | `build(args)` **api** | M:612 |
| `pruefen(tabelle_datei, log)` | `check(table_file, log)` **api** | M:894 |
| `BETA_WARNUNG` | `BETA_WARNING` **api** | M:1019 |
| `liesmich_text(d)` | `readme_text(d)` **api** | M:1040 |
| `VERSION` | `VERSION` (unchanged, "0.1") | M:70 |
| class `K` | `h713.log.console` **api** - see REPORT.md, finding 1 | M:213 |
| `mib` | `h713.util.mib` **api** | M:209 |
| `_rel` | `h713.util.relpath_or_abs` **api** | M:241 |
| `sha256_datei` | `h713.util.sha256_file` **api** | M:250 |
| `gpt_bauen` | `h713.gpt.build_layout_gpt` **api** | M:294 |
| `gpt_pruefen` | `h713.gpt.check_gpt` **api** | M:344 |
| (new) | `_block_map(fs, ino, inode)` - wrapper around `Ext4._karte`, REPORT.md finding 2 | - |

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
  the whole of `readme_text` - stage-1 rule, compared byte for byte by the
  golden tests;
* the keys of the table/manifest JSON (`teile`, `datei`, `sektoren`, `loch`,
  `bausteine`, `platzhalter`, `platzhalter_datei`, `platzhalter_nutzer`,
  `platzhalter_info`, `ziel`, `laenge`, `quelle`, `fuellung`,
  `sha256_muster`, `werkzeug`, `abbild`, `erzeugt`, `sektorgroesse`,
  `disk_sektoren`, `warum`, `partitionen`, `eintraege`) - `hy310-install`
  reads them and the released v0.5-beta table carries them;
* `inode["groesse"]` in `ext4_offsets` - B3's brief says the dicts of
  `h713.fs.ext4` keep their keys (REPORT.md, finding 2);
* `fs._karte` as the fallback spelling in `_block_map` (same finding).

## RENAMES-B7

# RENAMES - package B7 (`h713/profiles/__init__.py`, `h713/identify.py`, `h713/vendorfiles.py`, `h713/extract.py`)

Sources: `X` = `analyse/release/arbeit/r2-extract/h713-extract` (3138 lines),
`I` = `analyse/release/arbeit/r0-fel/hy310-install.py` (1961 lines). Line numbers are those of the
source file. Public names follow the package API of doku/121 §4 (stage 1); locals are translated freely (the
equivalence test in `tests/test_faithful.py` alpha-renames them on both sides, so only the free
names and the attributes below are load-bearing). Every user-visible string and every dict key is
unchanged.

## `h713/profiles/__init__.py` (extends A3's registry)

| old | where | new |
|---|---|---|
| `PROFILES`, `get()`, `STATUS_VALUES` | A3 | unchanged (copied verbatim from `src/installer/h713/profiles/__init__.py`) |
| `H713_MIPS_FW_REVS` | X:266 | `UBOOT_FW_REVS` - the rows `h713_mips_fw_revs[]` declares, keys as in X |
| - (new, per brief) | X:266 + `installer/tests/fixtures/firmware-revisions.json` | `FIRMWARE_REVISIONS` - all four known display.bin revisions, plus `hdcp_wait_va`; `project_id`/`panel` are `None` where no U-Boot row declares them |
| `GERAETE` | X:98 | `legacy_devices()` - builds the old dict from `PROFILES[...]["reference"]` / `["expected"]` |
| `GERAETE[...]["beschreibung"]` | X:101, X:145 | `LEGACY_DESCRIPTIONS` (the German text; A3's profile carries an English `description`, and the extractor prints this one into `MANIFEST.json`/`BERICHT.txt`) |
| the order of `GERAETE` | X:98 | `LEGACY_DEVICE_IDS = ("hy310", "l018")` - `', '.join(GERAETE)` and the profile loops depend on it |
| `erwartung` key names | X:124 | `_LEGACY_EXPECTED_KEYS` - `paket_items` ↔ `package_items`, `paket_item_sha256` ↔ `package_item_sha256`, the other eight identical |

## `h713/identify.py`

| old | where | new |
|---|---|---|
| `KENNUNGS_MERKMALE` | X:178 | `ID_FEATURES` |
| `STARKE_MERKMALE` | X:181 | `STRONG_FEATURES` |
| `kennung(profil)` | X:185 | `features_of(profile)` |
| `merkmal_passt(name, ist, soll)` | X:194 | `feature_matches(name, actual, expected)` |
| `BEKANNTE_IMAGES` | X:201 | `KNOWN_IMAGES` |
| `fw_rev_zu(data)` | X:1961 | `firmware_revision_of(data)` (reads `profiles.UBOOT_FW_REVS`) |
| `_PlatteQuelle(platte, ex)` | I:1456 | `DiskSource(disk)` - the `ex` parameter is gone |
| `_PlatteQuelle._p` / `._TeilQuelle` | I:1459, I:1462 | `DiskSource._d` / dropped (`source.SliceSource` is imported) |
| locals `erst`, `vorn`, `sekt` | I:1466-1468 | `first`, `front`, `sectors` |
| `geraet_erkennen(platte, extraktor, log=K)` | I:1481 | `identify_device(disk, extractor=None, log=console)` - `extractor` is accepted and ignored (like B5's `restore_stock`) |
| `_extraktor_laden(pfad)` | I:1436 | **deleted** (api-h713.md) - with it the `try/except` around it, the `ex.` prefixes and `getattr(ex, "GERAETE", {})`/`hasattr(ex, "kennung")` |
| locals `aus`, `stumm`, `prof`, `z` | I:1493-1553 | `out`, `quiet`, `profile`, `line` |
| `_fingerprint_deuten(fp)` | I:1556 | `interpret_fingerprint(fp)` |
| locals `teile`, `datum`, `marke`, `ziffern`, `tt`, `ss` | I:1569-1580 | `parts`, `date`, `mark`, `digits`, `dd`, `hh` |
| `geraet_melden(erk, log, schreibt)` | I:1587 | `report_device(found, log=console, writing=True)` |
| `ist_unser_geraet` | I:347 | `blockdev.device_kind` (B4) |
| `K` | I:145 | `log.console` (B4) |

## `h713/vendorfiles.py`

| old | where | new |
|---|---|---|
| `PFLICHT` | X:208 | `REQUIRED_FILES` |
| `PQ_DATEIEN` | X:211 | `PQ_FILES` |
| `TVCONFIG`, `EDID_14`, `EDID_20` | X:221-223 | unchanged |
| `MSP_LIB_KANDIDATEN` | X:224 | `MSP_LIB_CANDIDATES` |
| `AIC_FW_VERZ` / `AIC_FW_ZIEL` | X:235, 236 | `AIC_FW_DIR` / `AIC_FW_TARGET` |
| `MIPS_QUELLVERZ` / `MIPS_AUSGABE` | X:245, 246 | `MIPS_SOURCE_DIR` / `MIPS_OUTPUT_DIR` |
| `MIPS_DATEIEN` | X:247 | `MIPS_FILES` |
| `MIPS_PROJECTID` | X:248 | unchanged |
| `MIPS_NICHT_UNSERE` | X:250 | `MIPS_NOT_OURS` |
| `MIPS_PART_NAMEN` / `MIPS_TEIL_SCHLUESSEL` | X:253, 254 | `MIPS_PART_NAMES` / `MIPS_PART_KEYS` |
| `MIPS_FEX`, `TSE_MAGIC`, `TSE_ID_OFFSET` | X:255-258 | unchanged |
| `PANEL_CONFIG_KANDIDATEN` | X:262 | `PANEL_CONFIG_CANDIDATES` |
| `elf_symbol` | X:1674 | unchanged; local `typ` → `sh_type` |
| `parse_mspm` | X:1731 | unchanged; locals `bloecke`→`blocks`, `probleme`→`problems`, `z`→`zero`, `ziel`→`target`, `laenge`→`length` (the returned dict keys `ziel`/`laenge`/`paare`/`offset` stay) |
| `suche_mspm_kette` | X:1757 | `find_mspm_chain` |
| `pruefe_edid_block(b, wer)` | X:1780 | `check_edid_block(b, who)`; local `p` → `findings` |
| `edid_hersteller` | X:1798 | `edid_vendor` |
| `edid_name` | X:1803 | unchanged |
| `pruefe_pq` | X:1836 | `check_pq`; locals `p`→`findings`, `modi`→`modes`, `eingang`→`input_name`, `tabellen`→`tables`, `zeilen`/`z`→`lines`/`line` |
| `lies_ini`, `zahlen` | X:1815, 1832 | imported from `h713.fex` as `parse_ini`, `ini_numbers` (B1) |
| `tse_kopf` | X:1933 | `tse_header` (returned keys `magic_ok`/`id`/`kopf` stay) |
| `pruefe_tse` | X:1942 | `check_tse`; locals `befunde`→`findings`, `aus_name`→`from_name` |
| `pruefe_display_cfg` | X:1970 | `check_display_cfg`; locals `hinweise`→`notes`, `roh`→`raw`, `wurzel`→`root`, `kinder`→`children` |
| `panel_config_id` | X:1987 | imported from `h713.fex` (B1) |
| `hexdump_kurz`, `Abbruch` | X:330, 306 | `util.hexdump_short`, `log.Abort` |

## `h713/extract.py`

`Lauf` (X:1999) → `Run`. `main` (X:3104) stays out (B8). `VERSION` (X:52) moved in with the class -
`write_manifest()` writes `f"h713-extract {VERSION}"` into `MANIFEST.json` and `BERICHT.txt`, and the
CLI needs it for `--version`; the package's own `h713.VERSION` ("0.2") is a different number.
`DEVICES = legacy_devices()` at module level replaces the `GERAETE` literal.

### methods (as fixed in api-h713.md)

| old | new | | old | new |
|---|---|---|---|---|
| `oeffne` | `open` | | `deklarierte_projekt_id` | `declared_project_id` |
| `fingerabdruck` | `fingerprint` | | `extrahiere_mips` | `extract_mips` |
| `eingang_imagewty` | `input_imagewty` | | `beobachte` | `observe` |
| `eingang_emmc` | `input_emmc` | | `lies_altes_manifest` | `read_old_manifest` |
| `eingang_teile` | `input_parts` | | `pruefe_ausgabeverzeichnis` | `check_output_dir` |
| `paket_aus_quelle` | `package_from_source` | | `setze_geraet` | `set_device` |
| `extrahiere_scp` | `extract_scp` | | `erkenne_geraet` | `detect_device` |
| `super_aus_quelle` | `super_from_source` | | `naechstes_profil` | `closest_profile` |
| `oeffne_vendor` | `open_vendor` | | `abweichungen_gegen` | `deviations_from` |
| `extrahiere_edid` | `extract_edid` | | `bewerte` | `grade` |
| `extrahiere_msp` | `extract_msp` | | `ablegen` | `store` |
| `extrahiere_pq` | `extract_pq` | | `lauf` | `run` |
| `extrahiere_wlan` | `extract_wlan` | | `aufraeumen` | `cleanup` |
| `mips_quelle` | `mips_source` | | `schreibe_manifest` | `write_manifest` |
| `_mips_lesen` | `_read_mips` | | | |

### attributes

| old | new | | old | new |
|---|---|---|---|---|
| `artefakte` | `artefacts` | | `altes_geraet` | `old_device` |
| `beobachtungen` | `observations` | | `out_gesperrt` | `out_locked` |
| `eingang` | `input_facts` | | `offen` | `not_extracted` |
| `geraet` | `device` | | `abweichungen` | `deviations` |
| `geraet_fix` | `device_fixed` | | `super_q` | `super_source` |
| `erkennung` | `detection` | | `vendor_q` | `vendor_source` |
| `merkmale` | `features` | | `quellen_offen` | `open_sources` |
| `referenzgeraet` | `reference_device` | | `mips_quellen` | `mips_sources` |

`args`, `log`, `out`, `tmp`, `package`, `packages`, `vendor`, `mips` unchanged.

### parameters of `store()` (ex `ablegen`)

`herkunft` → `origin`, `pruefung` → `checks`, `fehler` → `error`; `rel` and `data` unchanged.
`setze_geraet(gid, ueber, fix, merkmale)` → `set_device(gid, via, fix=False, features=None)`.

### calls into the wave-A package

`sha256_datei(q.pfad, self.log)` → `sha256_file(q.path, log=self.log)` (**keyword**, B1 review addendum:
the second positional parameter is `chunk` now) · `Log.kopf` → `Log.heading` · `Log.fehler` → `Log.error` ·
`Log.zeilen/warnungen` → `Log.lines/warnings` · `DateiQuelle` → `FileSource` (`.pfad` → `.path`) ·
`SparseQuelle(.ist_sparse/.beschreibung)` → `SparseSource(.is_sparse/.description)` ·
`Imagewty(.ist_imagewty/.eintraege/.datei)` → `Imagewty(.is_imagewty/.entries/.file)` ·
`SunxiPackage(.summe_ok/.probleme/.herkunft)` → `SunxiPackage(.checksum_ok/.problems/.origin)` ·
`suche_sunxi_packages/uboot_kennung/fdt_wurzel/pruefe_scp` → `find_sunxi_packages/uboot_version_string/fdt_root/check_scp` ·
`Fat(.ist_fat/.verzeichnis/.eintraege/.lies/.typ/.probleme/.beschreibung)` →
`Fat(.is_fat/.directory/.entries/.read/.type/.problems/.description)` · `LpSuper.lage` → `.location` ·
`Ext4Basis` → `Ext4Base`, `.existiert/.lies/.gehe/.statistik/.probleme/.beschreibung` →
`.exists/.read/.walk/.stats/.problems/.description` · `Gpt.ist_gpt` → `Gpt.is_gpt` · `SEKTOR` → `gpt.SECTOR` ·
`hexdump_kurz` → `hexdump_short` · `Abbruch` → `Abort`.

## Deliberately **not** renamed (stage 1)

* every dict key that reaches `MANIFEST.json`, `BERICHT.txt` or a caller: `pfad`, `groesse`, `sha256`,
  `md5`, `herkunft`, `pruefung`, `fehler`, `referenz_stimmt`, `referenzgeraet`, `ueber`, `merkmale`,
  `hinweise`, `stimmen`, `treffer`, `widerspruch`, `_gesehen`, `typ`, `teile`, `dateien`, `quelle`,
  `dateisystem`, `weitere_quellen`, `projekt_id_*`, `revisionstabelle`,
  `nicht_extrahiert_gleiche_partition`, `kurznamen`, `uebrig`, `sonst`, `probleme`, `ziel`, `laenge`,
  `paare`, `magic_ok`, `kopf`, `id`, `hinweis`, `eintraege`, `aic_eintraege`, `werkzeug`, `zeit`,
  `ergebnis`, `device_*`, `nicht_angefasst`, `bekannt_als`, `rolle`, `beschreibung`, `referenz`,
  `erwartung`, `paket_items`, `paket_item_sha256`, `name`, `geraet`, `bekannt`, `layout`,
  `fingerprint`, `lp_partition`
* every user-visible string: log lines, `Abort` texts, the `BERICHT.txt` headings, the exit-code
  sentences. They stay German until stage 3.
