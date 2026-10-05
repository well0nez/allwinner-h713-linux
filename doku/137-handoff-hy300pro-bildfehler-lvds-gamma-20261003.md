# 137 – Handoff: HY300PRO-G-EU, Bildfehler durch falsche LVDS-Farbtiefe

Stand: 03.10.2026, nach dem erfolgreichen 8-Bit-Test. Einstieg fuer die
Fortsetzung ist diese Datei; [136](136-handoff-hy300pro-g-eu-20261003.md)
enthaelt Geraeteaufnahme, Dump, Erstinstallation und die vorherigen Tests.

**Paralleler Folge-Stand, 03.10.:** RGB und 8-Bit-LVDS sind inzwischen in
`main` mit `bf72eb3` integriert; U-Boot-Commit `2de0cc8`. Die untenstehende
Aufnahme beschreibt den vorherigen Testzeitpunkt. Aussagen "noch nicht
uebernommen" und die damaligen HEADs sind historisch, keine offenen
Integrationsauftraege. Neues Image/Flash/Kaltstart hier nicht erneut
verifiziert. Pipeline- und Gestaltungsnotiz:
`umbau/work/WARP-CALIBRATION-DRAFT/HANDOFF.md`.

## 1 Ergebnis und aktueller Geraetestand

Das Bild war trotz hellem Lichtkegel sehr schwach, Schwarz aufgehellt,
Farben ohne Tiefe. Der entscheidende isolierte Test war **LVDS von 6 auf
Stock-8 Bit**: unmittelbar danach kam eine eindeutige positive Rueckmeldung
am Bild. Vorher hatte der RGB-Gamma-Vergleich keinen nennenswerten sichtbaren
Unterschied gebracht. Die Wirkung der beiden Aenderungen nicht vermischen.

Aktuell, am Geraet nochmals lesend bestaetigt:

| Bestandteil | Zustand |
|---|---|
| LVDS-Control `0x05800000` | `0x01e0a40c`, Bits 4:3 = 1 = 8 Bit |
| TV-Programm | RGB-Testversion unter `/usr/local/sbin/h713-tv` |
| TSE-LUT | `/run/h713-tv/gamma-tse.bin`, **6144 Bytes**, R/G/B getrennt |
| Dienst | `h713-tv@video0.service`, active |
| HDMI | 1920x1080p60; NV16-Capture 1280x720, Plane aktiv |
| Bildregler | standard, unveraendert beim Gamma- und LVDS-Test |
| U-Boot / Flash | fuer diese beiden Tests nicht geaendert |

**Wichtig: Die 8 Bit sind bisher nur zur Laufzeit gesetzt. Ein Neustart
laedt noch den alten U-Boot-Code und damit wieder die falschen 6 Bit.**
Die neue TV-Programmdatei liegt dagegen dauerhaft auf dem Rootfs; ihr
Laufzeit-LUT wird beim Dienststart erneut erzeugt.

Ein Fotovergleich gegen Stock und ein kalter Boot mit dauerhaft korrigiertem
U-Boot stehen noch aus. Der Fix ist auf diesem Geraet sichtbar bestaetigt,
noch nicht auf dem Geraet des Issue-#1-Melders.

## 2 Geraet und Zugriff

- Verpackung: HY300PRO-G-EU. Vom Nutzer abgelesene Platine: **HY200 QZ713DF A1**.
- Eigenes Stock-Android 11; Projekt 0x34, Panel 1280x720, VESA, ColorDepth 8.
- SSH: Alias `hy300pro`, derzeit `192.168.8.246`, root, vorhandener SSH-Key.
  Adresse ist DHCP. Keine Passwoerter oder WLAN-Zugangsdaten in diesem Handoff.
- UART: `nc 192.168.8.180 2000`, Orange-Pi-ser2net, aktuell **HY300**, nicht HY310.
  Nur ein Client; eigener Capture blockiert sonst den Nutzer. Kein UART-Client
  wurde fuer die Gamma-/LVDS-Tests gestartet.
- Vollstaendiger Dump und Extraktion: geschlossener Bereich
  `re/device-dumps/hy300pro-plus-marco/`; Umgangsregeln aus 136 beachten.
- Ausgewaehltes Analyse-Material: `umbau/work/GEU1/material/`.
- FEL-A-A-Kabel speist phantom; vor echtem Stromzyklus abziehen.

Die vorherigen Fable-/HY310-Verifikationsaufgaben ruhen auf Nutzerwunsch.
Keine weiteren Agenten starten. Geraeteschritte vorher ansagen; kein Push
oder Release ohne ausdrueckliches Wort. Hauptcheckout nicht ungefragt integrieren.

## 3 Git: exakte Checkouts und Commits

Am Ende dieses Handoffs geprueft, beide Testcheckouts und main ohne
uncommittierte Aenderungen. **Die hier neuen Gamma-/LVDS-Fixes sind noch
nicht in diesen Git-Checkouts angewendet oder committet.**

| Checkout | Branch | HEAD |
|---|---|---|
| `umbau/src` | `main` | `c289bb3fc73cf549d097a2c20e66fc5658f6b3d3` |
| `umbau/work/_geu1-build/src` | `hy300pro-g-eu` | `90796322707275bfd159cbd465a982c2cc8e639f` |
| `umbau/work/_geu1-build/src/mainline/external/u-boot` | `hy300pro-g-eu` | `c459ea7b31ddd004bf53b8e1cb63866c29debbde` |

Integration-Testzweig seit main:

1. `8579024`: GEU1-Profil, Board, Kernel 0167, Installer-Groessen/Checks.
2. `bc90909`: U-Boot-Gitlink auf GEU1-Testzweig.
3. `47609ea`: abgelesene Platinenbezeichnung HY200 QZ713DF A1.
4. `9079632`: Kernel 0168, PWM-RPC nimmt einen Zeiger auf sechs Woerter.

U-Boot-Testzweig seit Basis `4cecddd5561`:

- `bed99d1afe1`: eigener `hy300pro_g_eu_defconfig`.
- `c459ea7b31d`: eigener U-Boot-Device-Tree.

`/opt/Projekte/h713` selbst ist **kein Git-Repository**. Die Doku liegt hier,
die genannten Git-Repositories liegen darunter. In dieser Untersuchung
kein neuer Git-Commit und kein Push; `umbau/src` blieb unveraendert.

## 4 Erster Fix dieser Untersuchung: getrennte RGB-Gamma

Vorher: `h713-tv` liess `h713-pq` die rote TSE-Gammabank erzeugen
(2048 Bytes), las diese Bank und setzte jedes Sample fuer R, G und B gleich.
Die Originalkurven der eigenen Firmware sind aber verschieden:

| Sample | Stock R | Stock G | Stock B | Vorher R/G/B |
|---|---:|---:|---:|---|
| 0 | 0 | 0 | 0 | 0 / 0 / 0 |
| 256 | 1191 | 879 | 1123 | 1191 / 1191 / 1191 |
| 512 | 2483 | 1903 | 2364 | 2483 / 2483 / 2483 |
| 768 | 3386 | 2847 | 3356 | 3386 / 3386 / 3386 |
| 1023 | 4092 | 4092 | 4092 | 4092 / 4092 / 4092 |

Quelle: eigenes `/boot/mips/ProjectID_0x0034.TSE`, state normal, Gamma-Level
2.2 (= neutraler Exponent 1 fuer die gemessene Kurve).

Korrektur in separater Kopie `umbau/work/GEU1-image-analysis/h713-tv-rgb/`:

- TSE-Aufruf mit `--channel all`; Ergebnis muss 6144 Bytes haben.
- Loader uebernimmt R/G/B getrennt. Synthetische alte 2048-Byte-Dateien
  bleiben unterstuetzt und werden weiterhin auf alle Farben gelegt.
- Loader prueft Dateilaenge; zwei Baenke, unvollstaendige Daten und
  ueberzaehlige Bytes werden abgewiesen. Der alte Loader las nur die erste
  Bank und bemerkte ueberzaehlige Daten nicht.
- Samples sind zwei benachbarte **12-Bit-Werte** pro u32, der zweite bei
  Bit 12, nicht Bit 16. KMS bekommt entsprechend skalierte 16-Bit-Werte.

Validierung: ARM64-Cross-Build gegen `/srv/h713-rootfs`, ohne neue Warnung.
`test_gamma_loader.py` verwendet die echte C-Loaderfunktion und faengt den
DRM-Property-Blob ab; alle Samples getrennt geprueft, plus Dateilaengen.
Fuenf Faelle bestanden. Gegen den Originalcode scheitern RGB, zwei Baenke
und ueberzaehlige Bytes. Das beweist Dateiverarbeitung, nicht Hardware-Gamma.

Geraet: Original gesichert, Testdatei per SHA256 geprueft, atomarer
Programmaustausch, nur TV-Dienst neu gestartet. Anschliessend auf Nutzerwunsch
alt / zehn Sekunden / neu. Ergebnis: **kein nennenswerter Unterschied**,
vielleicht etwas Kontrast. Der Nutzer akzeptierte die korrekten Stock-Werte;
RGB-Fix bleibt im Testprogramm. Er war nicht die Loesung des Hauptbildfehlers.

## 5 Entscheidender Fix: LVDS-Farbtiefe 6 statt 8 Bit

| Quelle/Zustand | Wert/Ergebnis |
|---|---|
| eigenes `panel_config.ini` | `Mapping=0`, `ColorDepth=8` |
| eigenes LogoRegData, Projekt 0x34 | `0x05800000 = 0x01e0a40c` |
| unser U-Boot `h713_panel_cfg_board_b` | `lvds_bitsel=0` |
| Bootprotokoll | `01e0a40c -> 01e0a404`, shift 3, mask 3 |
| live vor Test | `0x01e0a404`, selector 0 = 6 Bit |
| live nach Test | `0x01e0a40c`, selector 1 = 8 Bit |

Beweis fuer die Bedeutung des Feldes: Stock-ARM-`libpq.so`,
`lvds_set_bitwidth` bei 0x387c. Assembler loescht Maske 0x18, laesst fuer
Argument 6 das Feld leer, setzt fuer 8 den Wert 0x08 und fuer 10 den Wert
0x10. Entsprechend 6/8/10 Bit -> selector 0/1/2. Die Bibliothek ist das
vorhandene HY310-Stock-Material; kein neuer Hashvergleich gegen GEU-Library.
Das stimmt mit eigenem INI und eigenem Original-Registerwort ueberein.

Fundstellen: `umbau/work/AP3/bin/vendor_a_libpq.so.asm`,
`umbau/work/AP3d/excerpts/panel-lvds-path.txt`. Hash der analysierten Library:
`12b1d910936604b11557ed6a93746f3ff4d4a43d065e80ade03342a34d324a0c`.

Die fruehere U-Boot-Annahme, das Feld sei ungeklaert und fuer Board B
muesse der bereits getestete Wert 0 erhalten bleiben, war falsch.
Das XML-Enum `lvds_format` ist ein anderes Schema; es darf nicht direkt als
Registerwert eingesetzt werden. Im eigenen XML steht ausserdem -1,
also kein expliziter Override.

Nach Nutzer-Go: `lvds_depth_test.py stock8` pruefte das exakte Ausgangswort,
aenderte **nur Bit 3**, las den neuen Wert zurueck. Kein Dienstneustart,
keine neue Gamma, kein Regler, keine PLL-/Timing-/PWM-Aenderung in diesem
Schritt. Unmittelbare deutlich positive Rueckmeldung. Finales rein lesendes
Auslesen bestaetigt weiterhin selector 1 / 8 Bit.

## 6 Dateien, Nachweise und Sicherungen

Neue Arbeit komplett unter **`umbau/work/GEU1-image-analysis/`**:

| Datei | Zweck |
|---|---|
| `FINDINGS.md` | fortgeschriebene Befunde und Grenzen |
| `0001-h713-tv-preserve-tse-rgb-gamma.patch` | Gamma-Fix gegen Integration-Testzweig, Pfade ab Repo-Wurzel |
| `0002-uboot-project34-restore-stock-8bit-lvds.patch` | dauerhafter LVDS-Fix gegen U-Boot-Testzweig, Pfade ab U-Boot-Wurzel |
| `h713-tv-rgb/main.c`, `h713-tv-rgb/h713-tv.aarch64-linux-gnu` | tatsaechlich gebauter und installierter Gamma-Test |
| `test_gamma_loader.py`, `loader-fixed-test.txt`, `loader-original-control.txt` | C-Loader-Tests und Gegenprobe |
| `live-tv-state.txt`, `live-tse-gamma-description.txt` | urspruenglicher Dienst und eigene RGB-Stock-Kurven |
| `live-rgb-test.txt`, `live-after-lvds8.txt` | Dienst nach jeweiligem Test |
| `lvds-stock8-result.json`, `live-lvds-final.json` | Ausgang, Schreib-/Rueckleseergebnis, abschliessender 8-Bit-Nachweis |
| `live-handoff-state.txt` | abschliessende Programmhashes, 6144-Byte-LUT, Dienst active |
| `logoreg-stock-and-overrides.txt` | eigenes Stock-LogoRegData und modellierte Boot-Aenderungen |
| `lvds_depth_test.py`, `read_lvds_depth.py` | begrenzter Farbtiefentest und rein lesender Nachweis |
| `ida_lvds.py`, `firmware-lvds-decompile.txt`, `display.bin.i64` | Firmwareanalyse auf einer DB-Kopie |

Auf dem Geraet:

- altes TV-Programm: `/root/h713-tv.before-rgb-gamma-20261003`, SHA256
  `d6e294f62c43d6610aa78e18f3987d61bdc50f17fcd07dba314445e702fcab0b`.
- RGB-Test: `/root/h713-tv.rgb-gamma-test` und installiert
  `/usr/local/sbin/h713-tv`, jeweils SHA256
  `ad5c5defb22a754b61da3059289c2a9c561bbd29804c0ed233819f37ca3f9ece`.

Vorheriger Kernel/PWM-Teststand aus 136: FIT mit PWM-Property, live HDMIRX-Modul
mit Kernel 0168; altes Modul `/root/sun50i-h713-hdmirx.ko.orig`.
Kernel 0168 behebt den Firmwareaufruf: ein physischer Zeiger auf sechs
Woerter statt sechs skalarer RPC-Argumente. Das beseitigte den Bootabsturz,
nicht das anschliessende schwache Bild. Kein erneuter Versuch mit dem
bekannt abstuerzenden Originalmodul. Release-Dateien koennen noch den alten
Modulstand enthalten; fuer neues Image alle Komponenten gezielt neu bauen.

## 7 Korrigierte Fehlannahmen und Messgrenzen

- Die mittlere rote Gammazahl `39737/65535` allein prueft weder die anderen
  Kanaele noch die physische Ausgabe. Die Statuszeile zeigt weiterhin nur
  Rot. `LUT 2048 bytes` im allgemeinen PQ-Status meint die separate
  synthetische Kurve; die wirklich gewaehlte TSE-Datei hat 6144 Bytes.
- `live-display-registers.json` enthaelt auch einen ersten MMIO-Leserversuch
  an Gamma-Baenken. **Diese Werte sind kein LUT-Nachweis:** Kernel 0095
  beschreibt die Adressen als Schreibports, ohne belegte Ruecklesbarkeit.
  Zusaetzlich hatte der erste Hilfsdecoder Bit 16 statt Bit 12 verwendet;
  `read_display.py` ist korrigiert. Alte Gamma-Werte/Hashes dort ignorieren.
- Leere PWM-Register bewiesen nicht, dass fehlende Lampen-PWM die Ursache
  war. Heller Kegel bei schwachem Nutzbild passt nicht als Beweis fuer diese
  Vermutung. Kein PWM-Eingriff in den hier erfolgreichen Test.
- Keine belegte DLP-/DLPC-Diagnose: die dokumentierte Schnittstelle ist LVDS.
- Keine belegte doppelte Gamma oder RGB/YUV-Pegelursache. Der isolierte
  Farbtiefenwechsel ist der entscheidende bisherige Bildnachweis.
- Die IDA-Originaldatenbank blieb unveraendert; nur Kopie hier benutzt.
- Kein neuer Agent, kein Push, kein Release, keine Integration nach main.

## 8 Naechste Schritte und Rueckweg

1. Dauerhaften LVDS-Patch im **isolierten U-Boot-Testzweig** anwenden und
   bauen. `git apply --check` gegen diesen Checkout ist bestanden; noch
   nicht angewendet oder gebaut. Gamma-Patch entsprechend in den
   Integration-Testzweig uebernehmen, nicht ungefragt nach main.
2. Neues TEST-Image mit aktuellem Kernel 0168, RGB-Programm und korrigiertem
   U-Boot zusammenstellen. Bestehendes Release nicht fuer korrigiert halten.
3. Vor Flash/Stromzyklus ansagen und Go; danach kalter Boot, UART-Log,
   Registerwert 8 Bit, HDMI-Bild und Stock-Referenzfoto vergleichen.
4. Erst nach dem eigenen bestaetigten dauerhaften Test den Issue-#1-Fix
   vorbereiten. Meldergeraet ist nicht identisch; dort noch kein Test.

Keine automatische Rueckstellung des erfolgreichen 8-Bit-Werts.
Falls gezielter Rueckvergleich gewuenscht ist: `lvds_depth_test.py restore6`
akzeptiert nur `0x01e0a40c` und setzt `0x01e0a404`; `stock8` schaltet wieder
zurueck. Skript vom Host ueber `ssh hy300pro python3 - ACTION < SCRIPT`
ausfuehren, nur nach Ansage/Go. Kein allgemeines Register-Schreibwerkzeug.

Rueckweg TV-Programm: Sicherung zuerst an neuem Zielnamen mit Modus 0755
bereitstellen, atomar ueber `/usr/local/sbin/h713-tv` umbenennen, danach
`systemctl restart h713-tv@video0.service`. Nicht direkt die laufende Datei
ueberschreiben (ETXTBSY). Die LVDS-Farbtiefe bleibt dabei separat.
