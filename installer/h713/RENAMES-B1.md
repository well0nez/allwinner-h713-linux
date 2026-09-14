# RENAMES — package B1 (`h713/util.py`, `h713/imagewty.py`, `h713/fex.py`)

Sources: `I` = `analyse/release/arbeit/r0-fel/hy310-install.py`, `M` = `…/r0-fel/hy310-mkimage.py`,
`X` = `…/r2-extract/h713-extract`. Line numbers are those of the source file.

## h713/util.py

| old | where | new |
|---|---|---|
| `mib(b)` | I:108, M:209 | `mib(b)` (unchanged) |
| `dauer(sekunden)` | I:112 | `duration(seconds)` |
| `_rel(p, basis)` | M:241 | `relpath_or_abs(p, base)` |
| `sha256_datei(pfad, stueck=8 << 20)` | M:250 | `sha256_file(path, chunk=8 << 20, log=None)` — one function |
| `sha256_datei(pfad, log=None)` | X:314 | `sha256_file(path, chunk=8 << 20, log=None)` — same function |
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
| locals `treffer`, `ueberlapp`, `ende` | X:925–927 | `hits`, `overlap`, `end` |
| `uboot_kennung(ub)` | X:941 | `uboot_version_string(ub)` |
| `fdt_wurzel(dtb)` | X:947 | `fdt_root(dtb)` |
| local `tiefe` | X:953 | `depth` |
| `pruefe_scp(scp, log)` | X:982 | `check_scp(scp, log)` |
| locals `befunde`, `ziel`, `kopf`, `gespiegelt` | X:984, 994, 999, 1005 | `findings`, `target`, `head`, `mirrored` |

## h713/fex.py

| old | where | new |
|---|---|---|
| `stock_plan(ex, image_q) -> (img, partitionen, roh)` | I:1621 | `stock_plan(image) -> (partitions, raw)` — no longer builds the Imagewty, no longer returns it |
| the `[partition]` loop inside `stock_plan` | I:1636–1650 | `parse_sys_partition(text)` (own function) |
| locals `partitionen`, `sekt`, `roh` | I:1634–1653 | `partitions`, `sect`, `raw` |
| (new, per brief) 24 u32 at boot0+0x38 | — | `dram_block(boot0)`, field names `DRAM_FIELDS` as in A1 `image_facts.py:39` = `fixtures-local/skripte/imgdump.py:38` |
| `lies_ini(text)` | X:1815 | `parse_ini(text)` |
| locals `sekt`, `akt`, `z` | X:1817–1819 | `sect`, `cur`, `line` |
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
