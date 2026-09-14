# B4 — renames (old → new)

Sources: `I` = `analyse/release/arbeit/r0-fel/hy310-install.py`, `X` = `analyse/release/arbeit/r2-extract/h713-extract`.
Line numbers are the **origin** line. Printed strings are not renamed — they are byte-identical (stage 1).

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
| `SECT` | I:44 | `SECT` (unchanged — see REPORT.md §4) |
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
