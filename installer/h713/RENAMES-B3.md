# B3 — rename map (old → new)

Sources: `X` = `analyse/release/arbeit/r2-extract/h713-extract`, `I` = `analyse/release/arbeit/r0-fel/hy310-install.py`.
Line numbers point at the **old** definition. Public names follow `umbau/plan/api-h713.md`; private helpers, parameters
and locals are translated freely. Every user-visible string and every **dict key** stays byte-identical (see the last
section) — only identifiers change.

## `h713/source.py` (X:338–546, X:1130–1136)

| old | new | old line |
|---|---|---|
| `Quelle` | `Source` | X:338 |
| `Quelle.backing` / `.sub` / `.read` / `.size` / `.name` | unchanged | X:341–350 |
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
| `KettenQuelle.teile` (attr, param) | `ChainSource.parts` | X:477–479 |
| `NullQuelle` | `NullSource` | X:1130 |
| `materialisiere(q, ziel, log)` | `materialize(q, target, log)` | X:508 |

## `h713/fs/fat16.py` (X:674–866)

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
| locals `basis`, `erw`, `kurz`, `lang`, `teil`, `groesse` | `base`, `ext`, `short`, `long_name`, `part`, `size` | X:812–825 |
| `verzeichnis(pfad)` | `directory(path)` | X:832 |
| locals `teil`, `treffer` | `part`, `hits` | X:835–836 |
| `lies(e)` | `read(e)` | X:842 |
| locals `noetig`, `teile`, `gelesen` | `needed`, `parts`, `got` | X:844–846 |

`ATTR_LFN`, `ATTR_VOLUME`, `ATTR_DIR`, `bps`, `spc`, `reserved`, `nfats`, `root_entries`, `total`, `fatsz`,
`root_cluster`, `fat_start`, `root_start`, `data_start`, `cluster_bytes`, `eoc`, `label`, `_fat`: unchanged.

## `h713/fs/lpsuper.py` (X:1024–1128)

| old | new | old line |
|---|---|---|
| `_lies_metadaten(moff, log, lage)` | `_read_metadata(moff, log, location)` | X:1062 |
| `self.lage` | `self.location` | X:1106 |
| `self.geraete` | `self.devices` | X:1107 |
| locals `basis`, `kandidaten`, `gefunden` | `base`, `candidates`, `found` | X:1050–1053 |
| locals `gruppen`, `geraete`, `groesse` | `groups`, `devices`, `size` | X:1090–1101 |
| local `teile` in `partition()` | `pieces` | X:1118 |
| `SEKTOR` (X:273, module level) | `SECTOR` (module level here) | X:273 |
| `partition(name, log)`, `self.parts`, `self.version`, `GEO_MAGIC`, `HDR_MAGIC` | unchanged | X:1024–1114 |

## `h713/fs/ext4.py` (X:1142–1673)

| old | new | old line |
|---|---|---|
| `Ext4Basis` | `Ext4Base` | X:1142 |
| `beschreibung` (class attr) | `description` | X:1150 |
| `lies(pfad, tmp)` | `read(path, tmp)` | X:1156, 1563, 1659 |
| `existiert(pfad)` | `exists(path)` | X:1159 |
| `gehe(wurzel, max_tiefe)` | `walk(root, max_depth)` | X:1166 |
| locals `offen`, `pfad`, `tiefe`, `voll` | `open_list`, `path`, `depth`, `full` | X:1168–1175 |
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
| locals `roh`, `typ`, `groesse` in `inode()` | `raw`, `ftype`, `size` | X:1343–1352 |
| `_extent_knoten(roh, ino, out, tiefe)` | `_extent_node(raw, ino, out, level)` | X:1371 |
| locals `belegt`, `laenge`, `kind` | `written`, `length`, `child` | X:1385–1394 |
| `_indirekt(nr, stufe, start, karte, grenze)` | `_indirect(nr, level, start, mapping, limit)` | X:1397 |
| locals `pro`, `spanne` | `per`, `span` | X:1399–1400 |
| `_karte(ino, inode)` | `_map(ino, inode)` | X:1415 |
| local `karte` | `mapping` | X:1424 |
| `_daten(ino, inode)` | `_data(ino, inode)` | X:1443 |
| locals `groesse`, `belegt` | `size`, `filled` | X:1444–1450 |
| `_ist_schneller_symlink` | `_is_fast_symlink` | X:1465 |
| `symlink_ziel(ino, inode)` | `symlink_target(ino, inode)` | X:1470 |
| local `roh` | `raw` | X:1473 |
| `_verzeichnis(ino)` | `_directory(ino)` | X:1481 |
| locals `daten`, `kind` | `data`, `child` | X:1486–1492 |
| `_kind(ino, name)` | `_child(ino, name)` | X:1509 |
| local `kino` | `child_ino` | X:1510 |
| `pfad_ino(pfad, folge_letzten)` | `path_inode(path, follow_last)` | X:1515 |
| locals `komp`, `kind`, `kinode`, `ziel` | `parts`, `child`, `child_inode`, `target` | X:1518–1535 |
| locals `eintraege`, `ki` in `ls()` | `entries`, `ci` | X:1549–1557 |
| `statistik()` | `stats()` | X:1572 |
| `Ext4Debugfs.datei` | `Ext4Debugfs.file` | X:1606 |
| `_roh(cmds)` | `_raw(cmds)` | X:1619 |
| local `akt` | `current` | X:1623 |
| locals `eintraege`, `ziel` | `entries`, `target` | X:1637, 1660 |
| `MAGIC`, `INCOMPAT_*`, `ROCOMPAT_*`, `FL_*`, `EXT_MAGIC`, `MAX_SYMLINK`, `BLOCK_CHUNK`, `ls`, `inode`, `stat`, `label_fs`, `dev`, `_cache`, `_dir_cache`, `_inode_cache` | unchanged | — |

## `h713/fs/sparse.py` (I:1656–1731)

| old | new | old line |
|---|---|---|
| `ist_sparse(kopf)` | `is_sparse(header)` | I:1661 |
| `sparse_schreiben(platte, d, plba, trocken=False)` | `write_sparse(disk, data, part_lba, dry_run=False)` | I:1666 |
| `platte.schreib(...)` (call) | `disk.write(...)` | I:1688 |
| inner `schreib_am(bl, daten)` | `write_at(bl, buf)` | I:1687 |
| locals `happen`, `pos`, `block`, `geschrieben` | `step`, `pos`, `block`, `written` | I:1684–1685 |
| locals `typ`, `quelle`, `laenge` | `ctype`, `src`, `length` | I:1691–1692 |
| locals `muster`, `gesamt`, `voll`, `null` | `pattern`, `total`, `full`, `zeros` | I:1701–1715 |
| `SECT` (I:44) | `SECTOR` (module level here) | I:44 |
| `SPARSE_MAGIC`, `_CHUNK_RAW`, `_CHUNK_FILL`, `_CHUNK_DONT_CARE`, `_CHUNK_CRC32` | unchanged | I:1656–1657 |

## Deliberately **not** renamed (stage 1)

* **Dict keys** — the extractor's JSON (`MANIFEST.json`) and `BERICHT.txt` are built from them:
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
