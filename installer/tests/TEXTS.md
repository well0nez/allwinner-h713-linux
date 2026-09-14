# TEXTS.md -- German -> English, stage 3 (doku/121 §4, stage 3)

Every user-visible string of the installer package, translated once by package D1.
**Translated, not rewritten**: same content, same numbers, same order, same line breaks.
The golden tests that froze these texts were re-frozen in the same pass, reason
"stage 3 texts", with the old value kept in a comment (see REPORT.txt).

Not in this table, because they belong to D2's tools and are translated with them:
`h713/mkimage.py`, `h713/extract.py`, `h713/layout.py`, `h713/vendorfiles.py`,
`h713/imagewty.py`, `h713/fex.py`, `h713/gpt.py`, `h713/source.py`, `h713/fs/*`,
`h713/util.py`, and the `"mkimage"` style markers of `h713/log.py` (`OK  `, `HM  `, `FEHL`).

## 1. Command line

| old (v0.5-beta) | new | note |
|---|---|---|
| `hy310-install.py` | `h713-install <subcommand>` | the old name forwards for one release |
| `--abbild TABELLE` | `install TABLE` | a RELEASE-DIR is found by itself |
| `--tabelle` | `--table` |  |
| `--authorized-key` | `--ssh-key` |  |
| `--arbeitskopie` | `--work-copy` |  |
| `--sicherung DIR` | `--dump DIR` / `dump -o DIR` |  |
| `--abzug klein\|voll` | `dump --small\|--full` | `install` keeps both as well |
| `--nur-abzug` | `dump` |  |
| `--restore ABZUG` | `restore DUMP.img` |  |
| `--restore-stock IMG` | `restore-stock UPDATE.img` |  |
| `--extraktor PFAD` | -- (ignored, hint) | the package brings its own reader |
| `--env-neu` | `--fresh-env` | `--keep-env` is the default |
| `--ohne-erkennung` | `--skip-identify` |  |
| `--dry-run` | `--no-write` | one word for "rehearse" |
| `--vendor`, `--device`, `--uboot`, `--sunxi-fel` | unchanged |  |
| -- (new) | `identify [SOURCE] [--json]` | the profile row for any input |
| -- (new) | `extract INPUT -o DIR` | = h713-extract |
| -- (new) | `--yes` | the YES in advance, for scripts |
| -- (new) | `dump --with-vendor` | h713-extract right after the full dump |

## 2. Prompts and answers

| old | new | file:line |
|---|---|---|
| `  Zum Fortfahren JA eintippen: ` | `  Type YES to continue: ` | `h713/install.py:462` |
| answer `ja` | answer `yes` (`ja` still accepted) | `h713/install.py:462` |
| `  Welchen Abzug? [klein/voll] ` | `  Which dump? [small/full] ` | `h713/dump.py:443` |
| answer `voll` | answer `full` (`voll` still accepted) | `h713/dump.py:444` |
| `  Nochmal versuchen? [J/n] ` | `  Try again? [Y/n] ` | `h713/fel.py:112` |

## 3. Markers, manifest keys and file names

| old | new | file:line |
|---|---|---|
| `FEHLER:` (console, install style) | `ERROR:` | `h713/log.py:95` |
| `  WARNUNG: ` (Log) | `  WARNING: ` | `h713/log.py:39` |
| `  FEHLER: ` (Log) | `  ERROR: ` | `h713/log.py:42` |
| manifest `erzeugt` | `created` | `h713/dump.py:368` |
| manifest `werkzeug` | `tool` | `h713/dump.py:369` |
| manifest `geraet` | `device` | `h713/dump.py:370` |
| manifest `sektoren` | `sectors` | `h713/dump.py:371` |
| manifest `teile` | `regions` | `h713/dump.py:372` |
| manifest row `sektoren`/`zweck` | `sectors`/`purpose` | `h713/dump.py:372` |
| manifest `werkzeug` value `hy310-install 0.1 (Entwurf, doku/110)` | `h713-install 0.1 (draft, doku/110)` | `h713/dump.py:37` |
| dump file `LIESMICH.txt` | `README.txt` (no LIESMICH.txt any more) | `h713/dump.py:382` |

Unchanged on purpose (file and directory names inside a dump, read by other tools and
named in FLASHING.md): `emmc-voll.img`, `abbild-gefuellt.img`, `uboot-env.bin`, `extrakt/`,
`secure-storage.bin`, `private.bin`, `reserve0-a.bin`, `reserve0-b.bin`, `mips/`, the default
dump directory `hy310-sicherung`, and every key of the release table (`teile`, `datei`,
`loch`, `platzhalter`, ... -- api-stufe3.md: they stay until the release format changes).

## 4. Messages

One row per source line; a message that spans several lines has one row per line,
so the line numbers point straight at the string.

### `h713/log.py`

| old | new | line |
|---|---|---|
| `  WARNUNG: ` | `  WARNING: ` | 39 |
| `  FEHLER: ` | `  ERROR: ` | 42 |

### `h713/fel.py`

| old | new | line |
|---|---|---|
| `--sunxi-fel %s nicht gefunden` | `--sunxi-fel %s not found` | 31 |
| `sunxi-fel nicht gefunden. Es gehoert neben dieses Skript oder in den PATH.` | `sunxi-fel not found. It belongs next to this script or in the PATH.` | 41 |
| `So kommt das Geraet in den FEL-Modus:` | `This is how the device gets into FEL mode:` | 57 |
| `  1. Strom abziehen.` | `  1. Unplug the power.` | 58 |
| `  2. Die Reset-Taste gedrueckt halten.` | `  2. Hold the reset button down.` | 59 |
| `  3. Strom einstecken, Taste noch zwei Sekunden halten, loslassen.` | `  3. Plug the power in, keep the button down two more seconds, let go.` | 60 |
| `Das Geraet bleibt dabei dunkel -- das ist richtig so.` | `The device stays dark while it does -- that is how it should be.` | 62 |
| `Es braucht ein USB-A-auf-A-Kabel, dessen Stromader getrennt ist.` | `It takes a USB A-to-A cable whose power wire is cut.` | 63 |
| `Kein Gehaeuse oeffnen, kein Pad, kein Loeten.` | `No opening the case, no pad, no soldering.` | 64 |

### `h713/env.py`

| old | new | line |
|---|---|---|
| `Umgebung zu gross: %d Byte, Platz fuer %d` | `environment too big: %d bytes, room for %d` | 56 |

### `h713/verify.py`

| old | new | line |
|---|---|---|
| `Abbild (%.1f MiB ab LBA %d) ist groesser als die eMMC` | `image (%.1f MiB from LBA %d) is bigger than the eMMC` | 28 |
| `  %5.1f%%  %6.1f MiB/s  noch %s` | `  %5.1f%%  %6.1f MiB/s  %s left` | 50 |
| `Abweichung bei LBA %d` | `mismatch at LBA %d` | 78 |

### `h713/facts.py`

| old | new | line |
|---|---|---|
| `negativer Lesezugriff` | `negative read` | 76 |

### `h713/blockdev.py`

| old | new | line |
|---|---|---|
| `Der Desktop hat Partitionen eingehaengt: %s` | `The desktop has mounted partitions: %s` | 58 |
| `Von %s ist noch etwas eingehaengt und laesst sich nicht ` | `Something of %s is still mounted and will not come ` | 70 |
| `loesen: %s. Dort arbeitet noch jemand -- schliesse das ` | `loose: %s. Somebody is still working there -- close the ` | 71 |
| `Programm oder haenge von Hand aus ('udisksctl unmount -b ` | `program or unmount by hand ('udisksctl unmount -b ` | 72 |
| `...'), sonst ueberschreibt das laufende Dateisystem, was ` | `...'), otherwise the running filesystem overwrites what ` | 73 |
| `wir schreiben.` | `we write.` | 74 |
| `  %s ist noch belegt (der Desktop untersucht es) -- ` | `  %s is still busy (the desktop is examining it) -- ` | 95 |
| `ich warte` | `I am waiting` | 96 |
| `%s ist nach 5 s immer noch belegt%s. Schliesse das Programm, ` | `%s is still busy after 5 s%s. Close the program that is ` | 102 |
| `das darauf zugreift (Dateimanager, Datentraegerverwaltung), ` | `using it (file manager, disk management) and try again.` | 103 |
| `und versuche es erneut.` | `` | 104 |
| ` (eingehaengt: %s)` | ` (mounted: %s)` | 105 |
| `Groesse des Laufwerks nicht lesbar` | `drive size not readable` | 118 |
| `nur zum Lesen geoeffnet` | `opened read-only` | 155 |
| `Schreibversuch auf LBA %d..%d beruehrt den Secure Storage ` | `Write attempt on LBA %d..%d touches the Secure Storage ` | 159 |
| `(%d..%d). Dort stehen HDCP-Schluessel, die MAC-Adressen und ` | `(%d..%d). The HDCP keys, the MAC addresses and the serial ` | 160 |
| `die Seriennummer dieses Geraets -- nicht wiederherstellbar.` | `number of this device stand there -- not restorable.` | 161 |
| `%s auf %s` | `%s on %s` | 208 |
| `  %s ausgehaengt` | `  %s unmounted` | 238 |
| `keine GPT` | `no GPT` | 259 |
| `GPT unplausibel` | `GPT implausible` | 262 |
| `unser Layout (%s)` | `our layout (%s)` | 273 |
| `Stock-Layout, %d Partitionen` | `stock layout, %d partitions` | 275 |
| `Nicht unterstuetztes System: %s` | `unsupported system: %s` | 309 |

### `h713/dump.py`

| old | new | line |
|---|---|---|
| `0.1 (Entwurf, doku/110)` | `0.1 (draft, doku/110)` | 37 |
| `HDCP-Schluessel, WLAN-/BT-MAC-Adressen, Seriennummer` | `HDCP keys, WLAN/BT MAC addresses, serial number` | 46 |
| `Android Secure-Storage-Partition` | `Android secure storage partition` | 47 |
| ` [leer]` | ` [empty]` | 142 |
| `gesichert (Hash im Manifest)` | `saved (hash in the manifest)` | 150 |
| `  (leer)` | `  (empty)` | 151 |
| `Leer und damit ohne Inhalt: %s.` | `Empty and therefore without content: %s.` | 153 |
| `  Auf einem unangetasteten Geraet stuende dort etwas. Entweder wurde` | `  On an untouched device something would stand there. Either this` | 154 |
| `  dieses Geraet schon einmal umgebaut, oder diese Firmware nutzt die` | `  device has been converted once already, or this firmware does not` | 155 |
| `  Bereiche nicht. Der Secure Storage ist davon unabhaengig.` | `  use the regions. The Secure Storage is independent of that.` | 156 |
| `keine Absichts-Schluessel` | `no intent keys` | 169 |
| `U-Boot-Umgebung, %d Eintraege (%s)` | `U-Boot environment, %d entries (%s)` | 171 |
| `%-16s LBA %-8d %5.1f MiB  %s  (%d Eintraege; %s)` | `%-16s LBA %-8d %5.1f MiB  %s  (%d entries; %s)` | 172 |
| `uboot-env: unser Layout, aber bei LBA %d liegt keine gueltige Umgebung ` | `uboot-env: our layout, but no valid environment lies at LBA %d ` | 175 |
| `(leer oder ohne CRC) -- nichts zu sichern, nichts zu uebernehmen` | `(empty or without CRC) -- nothing to save, nothing to carry over` | 176 |
| `nur %d von %d Byte gelesen bei %d` | `only %d of %d bytes read at %d` | 329 |
| `  %5.1f%%  %6.1f MiB/s  noch %s` | `  %5.1f%%  %6.1f MiB/s  %s left` | 336 |

### `h713/stock.py`

| old | new | line |
|---|---|---|
| `%s ist kein IMAGEWTY-Container` | `%s is no IMAGEWTY container` | 150 |
| `%d Partitionen laut sys_partition.fex` | `%d partitions according to sys_partition.fex` | 159 |
| `%-22s -> GPT (Schutz-MBR, Kopf, Tabelle, Sicherungskopien)` | `%-22s -> GPT (protective MBR, header, table, backup copies)` | 174 |
| `%s entpackt %.1f MiB, %s fasst nur %.1f MiB` | `%s unpacks to %.1f MiB, %s only holds %.1f MiB` | 211 |
| `%-22s -> %-16s LBA %-8d %7.2f MiB entpackt (Sparse, Datei %.0f MiB)` | `%-22s -> %-16s LBA %-8d %7.2f MiB unpacked (sparse, file %.0f MiB)` | 214 |
| `%s (%.1f MiB) passt nicht in %s (%.1f MiB)` | `%s (%.1f MiB) does not fit into %s (%.1f MiB)` | 219 |
| `%-22s -> %-16s LBA %-8d %7.2f MiB genullt%s` | `%-22s -> %-16s LBA %-8d %7.2f MiB zeroed%s` | 265 |
| `(kein Abbild)` | `(no image)` | 266 |
| ` (Kopf)` | ` (head)` | 267 |
| `%s fehlt -- %s bleibt ohne Dateisystem, Android startet ` | `%s is missing -- %s stays without a filesystem, Android ` | 298 |
| `dann nicht durch` | `then does not boot through` | 299 |
| `%s (%.1f MiB) passt nicht in %s` | `%s (%.1f MiB) does not fit into %s` | 304 |
| `%-22s -> %-16s LBA %-8d %7.2f MiB leeres ext4` | `%-22s -> %-16s LBA %-8d %7.2f MiB empty ext4` | 309 |
| `nicht im Image und daher ausgelassen: %s` | `not in the image and therefore left out: %s` | 313 |

### `h713/identify.py`

| old | new | line |
|---|---|---|
| `HY310 update.img (Stock)` | `HY310 update.img (stock)` | 60 |
| `HY310 update_rooted.img (Stock + Root, gleiche Firmware)` | `HY310 update_rooted.img (stock + root, same firmware)` | 61 |
| `L018 update.img (Stock)` | `L018 update.img (stock)` | 62 |
| `HY310 Dev-Gerät, roher eMMC-Dump LBA 0..614399 (300 MiB)` | `HY310 dev device, raw eMMC dump LBA 0..614399 (300 MiB)` | 63 |
| `Geraeteerkennung: keine Partition 'super'` | `Device identification: no partition 'super'` | 307 |
| `Geraeteerkennung: keine LP-Partition 'vendor' (gefunden: %s)` | `Device identification: no LP partition 'vendor' (found: %s)` | 321 |
| `keine` | `none` | 322 |
| `Geraeteerkennung: /build.prop fehlt in vendor` | `Device identification: /build.prop is missing in vendor` | 326 |
| `Geraeteerkennung abgebrochen: %s` | `Device identification aborted: %s` | 330 |
| `Geraeteerkennung: kein ro.vendor.build.fingerprint in build.prop` | `Device identification: no ro.vendor.build.fingerprint in build.prop` | 335 |
| `%s.%s., %s:%s Uhr (%s)` | `%s.%s., %s:%s (%s)` | 394 |
| `%s -- kein Android mehr, nur der Abzug ist sinnvoll` | `%s -- no Android any more, only the dump makes sense` | 438 |
| `Das Laufwerk sieht nach nichts Bekanntem aus.` | `The drive looks like nothing known.` | 441 |
| `Die Firmware liess sich nicht bestimmen.` | `The firmware could not be determined.` | 444 |
| `  Kennung   %s` | `  fingerprint   %s` | 447 |
| `%s erkannt -- Android %s, Stand %s` | `%s recognised -- Android %s, build %s` | 449 |
| `Unbekannte Firmware: Android %s, Stand %s -- es wird nur ` | `Unknown firmware: Android %s, build %s -- only reading, ` | 452 |
| `gelesen, nichts geschrieben.` | `nothing is written.` | 453 |
| `  Bitte die Kennungszeile oben melden, dann kommt das Geraet` | `  Please report the fingerprint line above, then the device goes` | 454 |
| `  in die Tabelle (github.com/well0nez/allwinner-h713-linux).` | `  into the table (github.com/well0nez/allwinner-h713-linux).` | 455 |
| `Unbekannte Firmware: Android %s, Stand %s -- kein Schreiben.` | `Unknown firmware: Android %s, build %s -- no writing.` | 457 |
| `  Die Fundstellen einer fremden Version zu raten, kostet im` | `  Guessing the places of a foreign version costs the Secure Storage` | 458 |
| `  schlimmsten Fall den Secure Storage -- deshalb kein Weiter.` | `  in the worst case -- so no going on.` | 459 |
| `  Bitte die Kennungszeile oben melden, dann kommt sie in die Tabelle.` | `  Please report the fingerprint line above, then it goes into the table.` | 460 |

### `h713/install.py`

| old | new | line |
|---|---|---|
| `keine Quelle fuer: %s` | `no source for: %s` | 44 |
| `%s ist %d Byte gross, der Platzhalter fasst nur %d` | `%s is %d bytes, the placeholder only holds %d` | 51 |
| `%-28s %7d Byte an Offset 0x%x` | `%-28s %7d bytes at offset 0x%x` | 57 |
| `--authorized-key %s: %s` | `--ssh-key %s: %s` | 84 |
| `--authorized-key %s ist ein PRIVATER Schluessel -- gemeint ist ` | `--ssh-key %s is a PRIVATE key -- what is meant is ` | 86 |
| `die .pub-Datei. Nichts geschrieben.` | `the .pub file. Nothing written.` | 87 |
| `--authorized-key %s enthaelt Nullbytes -- keine Schluesseldatei` | `--ssh-key %s contains NUL bytes -- no key file` | 89 |
| `--authorized-key %s: keine Zeile sieht wie ein oeffentlicher ` | `--ssh-key %s: no line looks like a public ` | 96 |
| `OpenSSH-Schluessel aus (%s ...)` | `OpenSSH key (%s ...)` | 97 |
| `--authorized-key %s: %d Byte, der Platzhalter fasst %d -- weniger ` | `--ssh-key %s: %d bytes, the placeholder holds %d -- fewer ` | 101 |
| `Schluessel oder kuerzere Kommentare` | `keys or shorter comments` | 102 |
| `authorized_keys: %d Schluessel aus %s, %d Byte, mit Zeilenumbruechen auf %d aufgefuellt` | `authorized_keys: %d key(s) from %s, %d bytes, padded with newlines to %d` | 116 |
| `kein --authorized-key: /root/.ssh/authorized_keys bleibt leer -- auf das ` | `no --ssh-key: /root/.ssh/authorized_keys stays empty -- the device ` | 119 |
| `Geraet kommt man dann nur ueber die serielle Konsole` | `is then reachable only over the serial console` | 120 |
| `--authorized-key: dieses Abbild hat keinen Platzhalter fuer ` | `--ssh-key: this image has no placeholder for ` | 122 |
| `authorized_keys (Tabelle ohne platzhalter_nutzer, aelter als ` | `authorized_keys (table without platzhalter_nutzer, older than ` | 123 |
| `11.09.2026) -- der Schluessel kaeme nicht an. Abbruch.` | `11.09.2026) -- the key would not arrive. Aborted.` | 124 |
| `die Tabelle nennt Nutzer-Platzhalter, die dieses Skript nicht ` | `the table names user placeholders this script does not ` | 127 |
| `kennt: %s -- neueres hy310-install noetig` | `know: %s -- a newer h713-install is needed` | 128 |
| `in %s liegen %d Dateien *.tabelle.json -- bitte die richtige ` | `%s holds %d files *.tabelle.json -- please name the right one ` | 295 |
| `direkt angeben` | `directly` | 296 |
| `%s ist keine Abbild-Tabelle von hy310-mkimage` | `%s is no image table of h713-mkimage` | 302 |
| `%s fehlt -- das Abbild ist unvollstaendig` | `%s is missing -- the image is incomplete` | 312 |
| `%s ist %d Byte, erwartet %d` | `%s is %d bytes, expected %d` | 314 |
| `%s: sha256 stimmt nicht -- Uebertragung kaputt?` | `%s: sha256 does not match -- broken transfer?` | 324 |
| `%-34s LBA %-9d %11d Byte  %s` | `%-34s LBA %-9d %11d bytes  %s` | 325 |
| `die Tabelle sperrt LBA %d..%d, dieses Skript %d..%d -- ` | `the table locks LBA %d..%d, this script %d..%d -- ` | 330 |
| `nicht zusammengehoerig` | `they do not belong together` | 331 |
| `die Tabelle ist fuer %s Sektoren gebaut, hier sind %d erwartet` | `the table is built for %s sectors, %d are expected here` | 335 |
| `%s: keine der %d Dateien im Abzug -- dieses Geraet hat den Chip ` | `%s: none of the %d files in the dump -- this device probably ` | 367 |
| `wohl nicht. Die Platzhalter bleiben genullt, WLAN bleibt aus.` | `does not have the chip. The placeholders stay zeroed, WLAN stays off.` | 368 |
| `in %s fehlen %d Datei(en), z. B. %s` | `in %s %d file(s) are missing, e.g. %s` | 374 |
| `passt nicht in den Platzhalter: %s` | `does not fit into the placeholder: %s` | 377 |
| `%d Datei(en) sind kleiner als ihr Platzhalter (%s) -- der Rest ` | `%d file(s) are smaller than their placeholder (%s) -- the rest ` | 383 |
| `wird genullt. Andere Firmware als beim Bau des Abbilds?` | `is zeroed. Other firmware than when the image was built?` | 384 |
| `h713-extract nicht gefunden -- es gehoert neben dieses Skript.` | `h713-extract not found -- it belongs next to this script.` | 402 |
| `Extraktion vollstaendig und gegen die Referenz geprueft` | `extraction complete and checked against the reference` | 417 |
| `h713-extract meldet Abweichungen (unbekannter Stand oder ` | `h713-extract reports differences (unknown build or missing ` | 419 |
| `fehlende Teile) -- die Ausgabe liegt trotzdem in %s` | `parts) -- the output lies in %s all the same` | 420 |
| `h713-extract ist mit Fehler %d ausgestiegen` | `h713-extract exited with error %d` | 422 |
| `\nAbgebrochen.` | `\nAborted.` | 441 |
| `  Das hier ist eine Beta. Wenn waehrend des Schreibens etwas` | `  This here is a beta. If something goes wrong while it writes:` | 451 |
| `  schiefgeht: NICHT den Strom ziehen und neu starten. Das Geraet` | `  do NOT pull the power and reboot. Put the device into FEL mode` | 452 |
| `  in den FEL-Modus bringen (Reset halten, Strom einstecken) und` | `  (hold reset, plug the power in) and start from the beginning --` | 453 |
| `  von vorn anfangen -- die Boot-Kette ist von dort immer erreichbar.` | `  the boot chain is always reachable from there.` | 454 |
| `  Zum Fortfahren JA eintippen: ` | `  Type YES to continue: ` | 459 |
| `Umgebung liegt nicht im Teil mit den Platzhaltern -- Uebernahme uebersprungen` | `the environment does not lie in the part with the placeholders -- carry-over skipped` | 474 |
| `Umgebung im Abbild bei Offset 0x%x hat keinen gueltigen CRC` | `the environment in the image at offset 0x%x has no valid CRC` | 481 |
| `Umgebung nach dem Schreiben nicht wie erwartet` | `the environment is not as expected after writing` | 494 |
| `Umgebung: dieses Abbild bringt keine mit (aelter als 12.09.) -- nichts zu uebernehmen` | `Environment: this image brings none along (older than 12.09.) -- nothing to carry over` | 538 |
| `%s=%s (Abbild: %s)` | `%s=%s (image: %s)` | 561 |
| `Umgebung: %s stimmen mit der Vorgabe des Abbilds ueberein -- nichts zu uebernehmen` | `Environment: %s agree with the image's default -- nothing to carry over` | 564 |
| `Umgebung: aus der alten uebernommen: %s` | `Environment: carried over from the old one: %s` | 575 |
| `  Alles andere kommt vom U-Boot des Abbilds. Die alte liegt in %s.` | `  Everything else comes from the image's U-Boot. The old one lies in %s.` | 576 |
| `Abbild pruefen (%s, %s)` | `Check the image (%s, %s)` | 588 |
| `Loch bei LBA %d..%d (%s) -- bleibt unberuehrt` | `Hole at LBA %d..%d (%s) -- stays untouched` | 590 |
| `Platzhalter uebersprungen: %s wird bei diesem Lauf nicht geschrieben` | `placeholders skipped: %s is not written in this run` | 606 |
| `--authorized-key bleibt damit ohne Wirkung` | `--ssh-key therefore has no effect` | 609 |
| `Die geraeteeigenen Dateien einsetzen (%d Platzhalter)` | `Put the device's own files in (%d placeholders)` | 614 |
| `Es gibt weder --vendor noch einen Vollabzug in %s.` | `There is neither --vendor nor a full dump in %s.` | 623 |
| `  Die 43 Dateien (Anzeige-Artefakte, Firmware, PQ, WLAN) stehen nur` | `  The 43 files (display artefacts, firmware, PQ, WLAN) stand only` | 625 |
| `  auf deinem eigenen Geraet. Ohne sie bleibt das Bild schwarz.` | `  on your own device. Without them the picture stays black.` | 626 |
| `  Also: den VOLLEN Abzug ziehen (--abzug voll) oder ein` | `  So: take the FULL dump (dump --full) or name a directory` | 627 |
| `  Verzeichnis von h713-extract mit --vendor angeben.` | `  from h713-extract with --vendor.` | 628 |
| `%d Dateien aus %s` | `%d files from %s` | 631 |
| `Den eigenen SSH-Schluessel einsetzen` | `Put your own SSH key in` | 638 |
| `WUERDE: %s nach %s kopieren und %d Platzhalter fuellen` | `WOULD: copy %s to %s and fill %d placeholders` | 650 |
| `Arbeitskopie: %s (%.0f MiB)` | `Working copy: %s (%.0f MiB)` | 653 |
| `nach dem Fuellen weichen ab: %s` | `differ after filling: %s` | 658 |
| `%d Platzhalter gefuellt und zurueckgelesen -- alle gleich` | `%d placeholders filled and read back -- all equal` | 660 |
| `Auf die eMMC schreiben` | `Write onto the eMMC` | 668 |
| `  %-34s ab LBA %-9d %11d Byte` | `  %-34s from LBA %-9d %11d bytes` | 670 |
| `Trockenlauf -- nichts geschrieben.` | `No-write run -- nothing written.` | 672 |
| `Das ueberschreibt die eMMC.` | `This overwrites the eMMC.` | 674 |
| `%s geschrieben` | `%s written` | 680 |
| `alles geschrieben in %s` | `everything written in %s` | 681 |
| `Zurueckvergleichen` | `Compare back` | 683 |
| `%d Stichprobe(n) weichen ab -- nicht neu starten, nachfragen.` | `%d sample(s) differ -- do not reboot, ask.` | 689 |
| `Stichproben stimmen` | `samples match` | 691 |
| `Secure Storage unveraendert (byteweise gegen den Abzug verglichen)` | `Secure Storage unchanged (compared byte for byte against the dump)` | 700 |
| `DER SECURE STORAGE HAT SICH GEAENDERT -- bitte melden, ` | `THE SECURE STORAGE HAS CHANGED -- please report it, do ` | 702 |
| `nichts weiter tun, %s aufheben.` | `nothing further, keep %s.` | 703 |
| `Fertig. Strom abziehen und wieder einstecken.` | `Done. Unplug the power and plug it in again.` | 706 |

178 translated message lines in 10 modules. Everything the user sees in a run of
`h713-install` is in this table or in sections 1 to 3.
