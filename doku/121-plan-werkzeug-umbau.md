# Plan 121 — Umbau der PC-Werkzeuge: eine Bibliothek, Profile als Daten, ein Repo für mehrere Boards

Entschieden (Marco, 14.09.2026): Umbau in Stufen, Bibliothek zuerst, Werkzeuge auf Englisch, **keine Abbilder
für Geräte, die niemand getestet hat — niemals**. Ich (Fable) plane und orchestriere, Opus-Agenten arbeiten in
eigenen Ordnern, integriert wird nur von mir. Ziel: **ein einziger Zwischenschritt am HY310**, an dem alles auf
einmal geprüft wird.

Der lebende Stand steht in [`../umbau/STATUS.md`](../umbau/STATUS.md). Wer neu einsteigt: erst diese Seite,
dann `umbau/STATUS.md`, dann den Stufenplan, an dem gerade gearbeitet wird.

## 1. Warum überhaupt

Die Funktionalität des Installers ist gut und am Gerät bewiesen; die Struktur drumherum nicht. Vier Gründe,
alle am Code belegt:

1. **Layout-Wissen steht dreimal fest verdrahtet**: `hy310-install.py` (`SECTORS_EXPECTED`, `EINMALIG` mit
   HY310-LBAs, `ENV_LBA`), `hy310-mkimage.py` (`PARTITIONEN`, `DISK_SEKTOREN`, `LBA_*`), `h713-extract`
   (`GERAETE`). Ein zweites Gerät heißt: drei Dateien konsistent ändern. Der falsch beschriftete `reserve0` beim
   HY300 Pro (Issue #1, Plan 119 B2) ist das Symptom.
2. **Erkennung im Installer ist ein String-Vergleich** (`erwartung["build_fingerprint"]`, `hy310-install.py:1549`).
   Der Extraktor kennt neun Merkmale. Die neuen Images beweisen, dass der Fingerprint allein nichts trennt (§2).
3. **Bedienung**: 17 flache Schalter, vier Betriebsarten durch ein `_arbeiten()` mit frühen Returns, `--dry-run`
   und `--nur-abzug` heißen beide „nicht schreiben", der Pflichtabzug steht dreimal im Code
   (`:1107`, `:1134`, `:1153`), die Normalinstallation braucht sechs Schalter, obwohl alle Dateien in einem
   Ordner liegen.
4. **Die Bibliothek ist ein Skript**: IMAGEWTY, GPT, FAT16, ext4, Sparse, LP-super stecken in `h713-extract`
   (3138 Zeilen, ohne `.py`) und werden per `importlib.machinery` in Installer und mkimage geladen. Null
   Unit-Tests; es gibt `mkimage-selbsttest.py` und Gerätemitschnitte.

**Was bleibt und nicht verändert wird** (verschoben ja, verändert nein, vorher mit Golden-Tests eingefroren):
Schreibsperre über LBA 12288–14335 in `Platte.schreib()`, Füllen am PC und einmal schreiben, Stichproben,
Secure-Storage-Bytevergleich nach dem Schreiben, Erkennung vor dem ersten Schreibzugriff, `JA` tippen,
Dreiteiler mit Loch, Stock-GPT-Nachbau, Sparse-Schreiber, der ext4-/FAT16-/LP-Leser.

## 2. Was die drei Images vom 14.09. hergeben

`~/Downloads/update.img` ist unser HY310-Image (gleiche Größe, gleiches erstes MiB wie `re/vendor/HY310/`).
Neu: **HY300 T08** (`HY300_T08_OTA_2024-04-19-2028.img`, 2,6 GB) und **HY350**
(`HY350_user_public_en_F_chuangyihui_OTA_2024-10-25-1715_.img`, 1,6 GB). Trotz „OTA" im Namen sind beides
**volle PhoenixSuit-Images** (IMAGEWTY v3 mit boot0, boot_package, sys_partition, sunxi_gpt, super, boot,
vendor_boot, Reserve0); `auto_update.txt` ist das SD-Karten-Skript dazu. Rohdaten: `umbau/fixtures/`.

| | HY310 | HY300 T08 | HY350 | HY300 Pro (Issue #1) |
|---|---|---|---|---|
| Stock | Android 11, 64 bit, 2025-07-24 | Android 10, 32 bit, 2024-04-19 | Android 10, 32 bit, 2024-10-25 | Android 10, 32 bit, 2024-05-07 |
| Vendor-Fingerprint | Allwinner/h713_tuna_p3/… | ADT-3/adt3/adt3:10/…/6245789 | **derselbe** | **derselbe** |
| DRAM | 792 MHz, tpr11/12 `0x44340000`/`0x6666` | 640 MHz, `0x44440000`/`0x5555` | 792 MHz, `0x44440000`/`0x5555` | 636 MHz, tpr unbekannt |
| Partitionen | 26, `Reserve0_a/_b` | 25, `Reserve0` | 25, `Reserve0` | 25, `Reserve0` |
| super / media_data | 2 GiB / 272 MiB | 3 GiB / 16 MiB | 2,5 GiB / 16 MiB | 2 GiB / 208 MiB |
| deklarierte Projekt-ID | 48 (0x30) | 52 (0x34) | 48 (0x30) | 52 (0x34) |
| Panel laut `panel_config.ini` | 1920×1080 dual, DCLK 143,0 MHz | **1280×720 single, DCLK 62 MHz** | 1920×1080 dual, DCLK 148,5 MHz | (0x34 → 720p single, zu beweisen) |
| `display.bin` | 1 256 216 B `16c74a28…` | 1 252 128 B `22a7df11…` | **dieselbe** `22a7df11…` | 1 253 136 B `cf9649bc…` |
| `mips/` im Image | `boot-resource.fex/mips/` | `vendor:/etc/display/mips/` | `vendor:/etc/display/mips/` | auf dem Gerät in `bootloader_a` **und** `_b` |

Befunde, jeder offline geprüft (Skripte und Ausgaben in `umbau/fixtures-local/`):

1. **Der Fingerprint trennt die ADT-3-Familie nicht.** HY300 T08, HY350 und das HY300 Pro tragen denselben
   `ro.vendor.build.fingerprint`. Trennen tun `sunxi_version`, U-Boot-Kennung, scp-/u-boot-/dtb-Hash,
   DRAM-Block und Layout. Ein Installer, der nur den Fingerprint vergleicht, hielte ein HY350 für ein HY300 Pro.
2. **Die MIPS-Artefakte liegen bei ADT-3 im Android, nicht im boot-resource.** Erste Lesung am 14.09. war
   falsch („aus keinem Download"): `boot-resource.fex` hat dort kein `mips/`, aber `vendor:/etc/display/mips/`
   trägt alle 19 Dateien, dazu `/vendor/bin/loadmips`, `/vendor/lib/libmips.so` und ein `/dev/mipsloader`
   (Vendor-Kerneltreiber, DT-Knoten `mipsloader@…`). Android schreibt sie auf `bootloader_a/_b` — beim Melder
   lagen dort 19 identische Dateien. Für den Extraktor heißt das: eine zweite MIPS-Quelle je Profil. Für den
   Stock-Rückweg: `bootloader_b` ohne `downloadfile` (T08) darf nicht genullt werden.
3. **Eine `display.bin` bedient zwei Panels.** `22a7df11…` steckt im 720p-T08 und im 1080p-HY350. Das Panel
   darf also **nicht** aus dem Digest kommen (so hat es Fork-Commit `1e9daac` angelegt), sondern aus der
   deklarierten Projekt-ID plus `panel_config.ini`: 0x30 = 1920×1080 dual-port, 0x34 = 1280×720 single-port.
   Der Digest liefert nur Revisionsfakten (Größe, HDCP-Wartestelle). Das HY300 Pro deklariert 0x34 → 720p;
   „Stock rendert 1080p" in Plan 120 war das OSD, nicht das Panel. Beweis: Sondenlauf des Melders.
4. **Die `database.TSE` des Melders ist die der ADT-3-Images** (`6d43b85a…`), seine `display.bin` eine andere
   Revision (Build 24-5-7). Wir haben damit **drei** Firmware-Revisionen offline: HY310, ADT-3 2024-04/10, und
   seine als Größe+Hash.
5. **`stock_gpt_bauen` ist fast generisch**: Namen und LBAs stimmen für alle drei Images gegen deren
   `sunxi_gpt.fex`. Zwei Abweichungen: der Kopf schreibt fest 26 Einträge (25er-Layouts brauchen 25), und die
   Attribute (fex setzt Bit 45 auf allen, Bit 54 auf UDISK; wir nicht). Unser Nachbau entspricht dem **Gerät**
   (S46, byteidentisch zum HY310-Abzug), `sunxi_gpt.fex` ist also nicht das, was auf dem Gerät liegt.
6. **`sys_partition.fex` und `sunxi_gpt.fex` widersprechen sich nur beim HY310** (media_data 557056 vs
   524288 Sektoren; das Gerät folgt `sys_partition`). Bei HY300/HY350 stimmen beide. TODO 60/12 damit geklärt.
7. **Der DRAM-Block aus boot0 ist belastbar**: T08 liefert exakt die Werte des echten HY300 aus dem shift-Repo
   (`re/notes/H713_DRAM_REVERSE_ENGINEERING.md:72`). Ein U-Boot-defconfig je Board ist damit aus dem Image ableitbar.
8. **Der Vendor-DTB** (71 168 B im boot_package) dekompiliert sauber (3051 Zeilen): `fan`, `fan_ctrl`,
   `motor_ctr`, `mips*`, `leds`, `ir_receiver`, `pwm`, `twi`, `spi`, `tvtop/tvdisp/tvcap`. Eingabe für Board-DTS.

## 3. Zielbild

```
installer/
  h713/                      Python-Paket, nur Standardbibliothek, Python 3.9+, Windows-tauglich
    imagewty.py  fex.py  gpt.py  fs/{fat16,ext4,sparse,lpsuper}.py     <- aus h713-extract
    blockdev.py (Platte+Sperre)  env.py  console.py                      <- aus hy310-install
    dump.py  verify.py  stock.py  install.py                             <- aus hy310-install
    layout.py (Layout v3)  mkimage.py                                    <- aus hy310-mkimage
    extract.py  identify.py                                              <- aus h713-extract (Lauf, Kennung)
    profiles/  hy310.py  l018.py  hy300_t08.py  hy350.py  hy300_pro.py  <- Daten, kein Code
  h713-install  h713-mkimage  h713-extract                               <- dünne CLIs, englisch
  hy310-install.py  hy310-mkimage.py                                     <- Weiterleiter, ein Release lang
  tests/                                                                  <- unittest, Fixtures ohne Vendor-Bytes
boards/
  hy310/  hy300-t08/  hy350/  hy300-pro/     je: Profil, Kernel-DTS, Kernel-Config-Fragment, U-Boot-Fragment
```

Ein **Profil** ist genau die Zeile, die `h713_probe` ausgibt: Erkennungsmerkmale, Stock-Layout, DRAM-Block,
Firmware-Revisionen (Größe, SHA, HDCP-Wartestelle), deklarierte Projekt-ID → Panel, Regionen, die nur auf dem
Gerät existieren, MIPS-Quelle(n), Verhalten beim Stock-Rückweg. Ein Board kommt erst in die „unterstützt"-Liste,
wenn sein Besitzer einen grünen Durchlauf gemeldet hat; bis dahin heißt die Zeile „Profil, kein Abbild".

CLI (Englisch; die deutschen Schalter bleiben als Aliasse, Entscheidung 13.09.):

```
h713-install identify [DEVICE|DUMP|IMAGE]      what is this? prints the profile row
h713-install dump  --full|--small  -o DIR
h713-install install RELEASE-DIR [--ssh-key F] [--dump DIR]   finds table, u-boot-installer.bin, sunxi-fel
h713-install restore DUMP.img
h713-install restore-stock UPDATE.img
       ... [--no-write]  one word for "rehearse", instead of --dry-run and --nur-abzug
```

## 4. Die fünf Stufen

| Stufe | Inhalt | Plan | Gerät? |
|---|---|---|---|
| 0 | Fixtures aus Images und Abzügen, Profile als Daten, Golden-Tests gegen die **heutigen** Werkzeuge; keine Codeänderung an Auslieferung | [`umbau/plan/stufe-0.md`](../umbau/plan/stufe-0.md) | nein |
| 1 | Bibliothek herauslösen, Verhalten byteidentisch (Golden-Tests sind der Vertrag), Bezeichner englisch | [`stufe-1.md`](../umbau/plan/stufe-1.md) | nein |
| 2 | Verhalten ändern: Erkennung mit allen Merkmalen, Layout aus der GPT, kleiner Abzug mit `mips/`, Stock-Rückweg nach Profil, Pflichtabzug nur bei Stock, GPT-Kopf mit echter Zahl | [`stufe-2.md`](../umbau/plan/stufe-2.md) | nein |
| 3 | CLI-Umbau, Englisch, Dateien selbst finden, Doku und Transkript | [`stufe-3.md`](../umbau/plan/stufe-3.md) | nein |
| 4 | `boards/`, U-Boot-Fragmente, Firmware-Tabelle (Digest ≠ Panel), `build-all --board`, HY310 bekommt eigenen DTS-Namen | [`stufe-4.md`](../umbau/plan/stufe-4.md) | nein |
| **T** | **Ein** Gerätetest am HY310: Bau aus frischem Klon, install, identify, dump, restore-stock, restore, Abnahme wie P6 | [`geraetetest.md`](../umbau/plan/geraetetest.md) | **ja, einmal** |

Danach: Zweig `tools-refactor` nach `main`, Release `v0.6-beta`, Handoff.

**Stand 14.09. 21:45:** Alle Pakete der Stufen 0–4 sind integriert (`umbau/src`, Zweig tools-refactor); Suite 102 Tests grün mit dem eigenen v0.6-beta-Bau, Sperr-Scan leer, erster voller Release-Bau aus dem Integrationsbaum grün (Selbsttest ALL GREEN). Offen: letzter Bau von vorn nach D5, dann der Gerätetest (`umbau/plan/geraetetest.md`), dann Merge nach main, Push, Release, Handoff doku/122.

**Stand 14.09. 21:00:** Stufe 3 zur Hälfte, Stufe 4 bis auf die Doku integriert. Stufe 3: `h713-install` (sechs Unterbefehle, englisch, alte Schalter als Aliasse), `h713-mkimage`/`h713-extract` englisch, Suite 101 Tests grün (`umbau/reviews/D1.md`, `D2.md`); D4 (Doku) und D5 (Bauskripte, build-all englisch) laufen. Stufe 4: `boards/<id>/board.env` mit `check.sh`, Kernel-DTS `sun50i-h713-hy310` (Patch 0160), U-Boot-Fork mit Basis-Defconfig + Rollenfragmenten (Beweis auf .config- und Binärebene), Lader nach Board-Fakten (Projekt-ID, Partition nach Name + Slot, /oem) und Sonden-Profilzeile, `release/build-all.sh --board` mit Verweigerung ungetesteter Boards (`umbau/reviews/E1–E3b.md`); E6 (Doku) läuft, der volle Release-Bau aus `umbau/src` läuft im Container. Danach: Gerätetest nach `umbau/plan/geraetetest.md`. Offene Entscheidung für Marco: deutsche Dateinamen im Abzug (doku/61 Nachtrag).

**Stand 14.09. 20:00:** Stufe 0, 1 und 2 abgeschlossen (Stufe 2: Erkennung nach Merkmalen, Abzug aus der GPT mit `mips/` aus beiden Slots, Stock-Rückweg nach Profil, Extraktor mit Vendor-Quelle und Revisionstabelle, Projekt-ID in die Umgebung; Reviews `umbau/reviews/C*.md`). Stufe 3 und 4 laufen parallel. Ursprünglich:** Stufe 0 und 1 abgeschlossen (Belege: `umbau/reviews/A0–A7, B1–B7`, Golden-Suite in
`umbau/src/installer/tests`). Stufe 2 beginnt. Lebender Stand weiter in `umbau/STATUS.md`.

## 5. Arbeitsregeln (Marco, 14.09.)

- **Niemand schreibt in funktionierende Ordner.** Weder ich noch Agenten fassen `repo-neu/`, `mainline/`,
  `analyse/release/arbeit/`, `userspace/`, `release/` oder den U-Boot-Fork an. Ausnahmen für mich: `doku/`
  (Journal) und `umbau/`.
- **Agenten schreiben nur nach `umbau/work/<paket>/`.** Sie lesen das Projekt, aber nie `re/`,
  `analyse/hdcp-keys/`, `re/device-dumps/`, `hy310-sicherung-*/`. Regeln und Prüfliste:
  [`umbau/plan/agent-regeln.md`](../umbau/plan/agent-regeln.md).
- **Integriert wird nur von mir**, nach Prüfung, in `umbau/src/` (Klon von `repo-neu`, Zweig `tools-refactor`).
  Jede Prüfung steht in `umbau/reviews/`.
- **Jedes Agentenpaket hat einen Umfangsmaßstab** (`wc -l` der Quelle, Obergrenze im Brief) und einen
  fertigen Test, der grün werden muss.
- **Werkzeuge auf Englisch**: Bezeichner, Meldungen, Kommentare, Schalter. Deutsche Schalter bleiben Aliasse.
- **Kein Abbild für ein Gerät, das niemand getestet hat.** HY300 T08, HY350, HY300 Pro bekommen Profile.
- Vendor-Bytes (Firmware, DTB, boot0, `.fex`, `panel_config.ini`) bleiben in `umbau/fixtures-local/` und
  gehen nie in ein Repo; ins Repo gehen Zahlen, Hashes und unsere eigenen Tabellen.

## 6. Offen, mit Zeiger

- HDCP-Wartestelle der ADT-3-Revision `22a7df11…` offline suchen (Stufe 0, Paket A5); für `cf9649bc…` nur
  über das Sondenlog des Melders.
- Wie Android bei ADT-3 `bootloader_a/_b` befüllt (`loadmips`): nur Beobachtung, keine Voraussetzung. Der
  Stock-Rückweg lässt die Partitionen ohne `downloadfile` in Ruhe, dann ist es egal.
- Issue #1: die Panel-Aussage (0x34 → 720p) gehört in die nächste Antwort, sobald sein Sondenlog da ist.
- Plan 120 §4b–4c und Fork-Commit `1e9daac` müssen um Befund 3 korrigiert werden (Stufe 4, Paket E3).
