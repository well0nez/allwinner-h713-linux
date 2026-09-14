# B5 — renames (old → new)

Source: `I` = `analyse/release/arbeit/r0-fel/hy310-install.py` (unchanged). Line numbers are the
**origin** line in `I`. Printed strings, prompts, manifest keys, file names and exit codes are not
renamed — they are byte-identical (stage 1). The attributes of `args` are argparse `dest` names and
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
| `EINMALIG` | I:95 | `UNIQUE_REGIONS` (with the orphaned comment I:48–50) |
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

## Names of B1–B4 this package calls

`K`→`console`, `_Still`→`Quiet` (`h713.log`); `Platte`→`Disk`, `lies`→`read`, `schreib`→`write`,
`sektoren`→`sectors`, `pfad`→`path`, `SPERRE_ERSTER`→`LOCK_FIRST`, `SPERRE_LETZTER`→`LOCK_LAST`,
`_um_sperre`→`_around_lock` (`h713.blockdev`); `env_lesen`→`env_read`, `env_schreiben`→`env_write`,
`ENV_SEKTOREN`→`ENV_SECTORS`, `ENV_UEBERNEHMEN`→`ENV_CARRY_OVER` (`h713.env`); `mib`, `dauer`→`duration`
(`h713.util`); `Konsole.fehler`→`Console.error`, `Konsole.schritt`→`Console.step` (`h713.log`).
