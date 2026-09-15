# Plan 113 - Bildwerte zur Laufzeit rechnen und dauerhaft merken

**Aufgestellt 11.09.2026** nach der Messreihe am Gerät (siehe [`60-offen.md`](60-offen.md) §Bildpfad). Zwei Pakete:
**A** die Bildaufbereitung, **B** die Umbenennung der Werkzeuge. Beide vor dem Release, B **vor** dem Repo-Umbau
(`105` R3), weil ein Namenswechsel danach an Nutzern hängt.

---

# Paket A - Presets aus den Gerätedaten, Nutzerwerte über den Neustart

## A.1 Wie es heute ist

| Was | Wo | Woher der Wert kommt |
|---|---|---|
| Sechs Presets, je neun Werte | `userspace/h713-tv/main.c`, `presets[]` | **einkompiliert**, einmal aus Herstellerdaten abgeleitet |
| Gammakurve | `userspace/h713-tv/gamma-standard.bin`, 2048 B | **eingecheckt**, gilt nur für Gamma 2.2 |
| Startpreset | `main.c`, `struct opts o = { .preset = "standard", … }` | fest |
| Regleränderung per `ctl set` | nur im Speicher | **wird nicht gemerkt** |
| Betriebsart auto/off | `/var/lib/h713-tv/modus` | seit 11.09. gemerkt |

Die Gerätedaten liegen längst da: `/etc/h713/tvconfig/` mit acht Dateien, vom Installer aus der Extraktion des
Nutzers gefüllt. `h713-pq` rechnet daraus, wird aber nur von Hand aufgerufen. In `packages.txt` steht `python3`
bereits mit der Begründung „h713-pq rechnet Gamma/Presets zur Laufzeit aus /etc/h713/tvconfig" - der Weg war
gedacht und nie verdrahtet.

**Am 11.09. gemessen und damit belastbar:** die eingecheckte Gammakurve ist **byteidentisch** mit dem, was aus den
Daten dieses Geräts gerechnet wird (sha256 gleich über alle 2048 B), und die Presets `standard`, `vivid`, `cinema`
setzen alle Register genau wie in `pq_picturemode.ini`. Die Ableitung war also richtig. **Das Problem ist nicht
Falschheit, sondern Herkunft:** ein anderes Panel bekäme dieselbe Tabelle aufgezwungen, es fehlen zwei der acht
Presets (`energy_saving`, `custom`), und von den fünf Gammastufen (1.8/2.0/2.1/2.2/2.4) gibt es nur eine.

## A.2 Was herauskommen soll

Drei Schichten, jede mit klarer Herkunft, in dieser Reihenfolge angewandt:

1. **Herstellerdaten** - beim Start aus `/etc/h713/tvconfig/` gerechnet, für das gewählte Preset.
2. **Wahl des Nutzers** - welches Preset, aus `/etc/h713/tv.conf`.
3. **Abweichungen des Nutzers** - einzelne Regler, gemerkt, obendrauf.

Fehlt eine Schicht, greift die darunter. Fehlt die Extraktion ganz, bleibt die einkompilierte Tabelle als letzter
Rückfall - ein Gerät ohne Vendor-Daten muss trotzdem ein Bild zeigen.

## A.3 Die Entscheidung, die alles andere bestimmt: wer rechnet

`h713-tv` ist C, `h713-pq` ist Python (1407 Zeilen, vier Module). Drei Wege:

| Weg | dafür | dagegen |
|---|---|---|
| **(a) `h713-tv` ruft `h713-pq` beim Start auf** | eine Quelle der Wahrheit, keine Doppelpflege; `python3` ist ohnehin im Abbild | ~200 ms Startzeit, Abhängigkeit zur Laufzeit |
| (b) INI-Auswertung nach C portieren | keine Abhängigkeit | dieselbe Rechnung zweimal gepflegt - die Falle, die zur Sättigungs-Korrektur vom 07.09. geführt hat |
| (c) beim Einspielen vorrechnen, Binärtabelle ins Abbild | schnellster Start | der Installer müsste rechnen; ein Nutzer, der `tvconfig` später ergänzt, bekommt nichts davon |

**Gewählt: (a).** Doppelte Rechenwege sind in diesem Projekt schon einmal teuer geworden. Die 200 ms fallen einmal
beim Start an, und zwar parallel zu Dingen, die ohnehin warten.

**Schnittstelle:** `h713-pq` bekommt eine maschinenlesbare Ausgabe (`--json`), die heute fehlt. Sie liefert für
einen Eingang und ein Preset die neun Regler, den Bildmodus, den Gamma-Exponenten und den Pfad einer geschriebenen
LUT. `h713-tv` ruft einmal auf, liest, wendet an. **Kein Dauerlauf, kein Dienst, keine Bibliothek.**

## A.4 Was gemerkt wird, und wann

- **Datei:** `/var/lib/h713-tv/werte` neben dem bestehenden `modus`. Format wie `tv.conf`, `schluessel = wert`.
- **Was:** die neun Preset-Größen plus `preset` (welches gerade gilt) und `aspect`.
- **Wann:** **nicht bei jeder Bewegung.** Ein neues `h713-tv ctl save` schreibt den aktuellen Stand. Grund: wer
  einen Regler sucht, fährt ihn durch - ohne `save` merkt sich das Gerät genau den Zwischenstand, bei dem der Strom
  ausfiel. `ctl save --aus` löscht die Datei wieder.
- **Ausnahme:** die Betriebsart auto/off wird weiter sofort gemerkt, wie seit 11.09.; sie ist eine Entscheidung,
  keine Suchbewegung.
- **Reihenfolge beim Start:** Preset aus `tv.conf` (oder `standard`), daraus die neun Werte, dann die gemerkten
  Abweichungen darüber. Ein Preset per `ctl preset` setzt alles neu und **verwirft** die gemerkten Abweichungen im
  Speicher; erst ein `save` schreibt das fest.
- **`tv.conf` bekommt:** `preset = NAME | zuletzt`. `zuletzt` nimmt das gemerkte Preset.

## A.5 Wenn Daten fehlen oder falsch sind

- `tvconfig` fehlt oder ist unvollständig → Meldung im Journal, einkompilierte Tabelle, **kein Abbruch**.
- `h713-pq` fehlt, stürzt ab, braucht zu lange (2 s Frist) → dasselbe.
- Ein Preset steht in den Daten, aber nicht in der Tabelle (`energy_saving`, `custom`) → wird angeboten, sobald die
  Daten da sind; ohne Daten nicht.
- Die gemerkten Werte liegen außerhalb des erlaubten Bereichs → einzeln verworfen, mit Zeilennummer gemeldet.

## A.6 Nebenarbeiten, die dazugehören

- **`h713-pq` Statustabelle korrigieren** (`h713_pq/modell.py`, `PQ_ZIELE`): `brightness` steht dort auf
  „gemessen, ohne Wirkung" - widerlegt am 07.09. ([`nachtlog/I0`](nachtlog/I0-helligkeit-nachgemessen.md)) und am
  11.09. mit dem Auge bestätigt. `hue` und `sharpness` stehen auf „RE belegt, ungemessen" - am 11.09. gemessen,
  eins zu eins über 0…100, Wirkung am Bild bestätigt (magenta bei 0, grün bei 100).
- **`computer`-Preset** (Schärfe 0) und die Frage, ob `game`/`hdr` sich außerhalb der fünf Regler unterscheiden,
  am Gerät nachziehen.

## A.7 Abnahme

1. `h713-tv ctl preset vivid; h713-tv ctl set sharpness 30; h713-tv ctl save`, Neustart → Preset `vivid` mit
   Schärfe 30, alle anderen Werte aus `vivid`. Register gegengelesen.
2. Ohne `save` neu starten → die Änderung ist weg, `vivid` steht unverändert.
3. `tvconfig` wegnehmen, Neustart → Journal sagt es, Bild kommt trotzdem, Werte wie heute.
4. Gegenprobe der Rechnung: die zur Laufzeit erzeugte LUT ist byteidentisch mit
   `h713-pq show HDMI1 standard --lut` von Hand und mit der heutigen `gamma-standard.bin`.
5. Startzeit von `h713-tv` vorher/nachher gemessen, im Bericht genannt.
5a. **Sichtprüfung über die Kamera** mit **stehender** Quelle (Video anhalten!), Automatik der Kamera vorher
   abgeschaltet (`analyse/hdmi-seq/camctl.py`): `cinema` gegen `vivid` muss sich in der Buntheit messbar
   unterscheiden, `saturation 0` muss die niedrigste Buntheit aller Messungen ergeben. Bei laufendem Video ist die
   Messung wertlos, siehe [`60-offen.md`](60-offen.md) §Kamera.
6. 20 Kaltstarts unverändert sauber (`analyse/boot/kaltstart-serie.sh`).

---

# Paket B - Werkzeuge umbenennen

## B.1 Entscheidung (Marco, 11.09.)

**Gerätespezifisch bleiben dürfen:** der Abbild-Bauer und das Abbild selbst - jede Firmware gilt ohnehin für ein
bestimmtes Gerät. **Umbenannt werden die Werkzeuge**, weil der Bildpfad eine Eigenschaft des **H713** ist und der
Extraktor schon ein zweites Gerät kennt (Profil `l018`).

## B.2 Was es betrifft

| Gruppe | heute | Vorschlag |
|---|---|---|
| Werkzeuge, gerätunabhängig | `h713-tv`, `h713-pq`, `h713-extract`, `h713-fel`, `h713-hdcp-key` | `h713-*` |
| Gerätespezifisch, bleibt | `hy310-mkimage`, `hy310-install`, die Abbilddateien | unverändert |
| Defconfigs | `hy310_qz713_v3_1_defconfig` u. a. | unverändert, board-spezifisch |
| Umgebungsvariablen | `h713_*` | schon richtig |
| **Partitionsnamen** | `hy310-spl`, `-uboot`, `-keys`, `-env`, `-boot`, `-rootfs` | **eigene Entscheidung, siehe B.3** |

## B.3 Die Partitionsnamen sind der heikle Teil

Sie stehen nicht nur in Dateinamen, sondern in Dingen, die zusammenpassen müssen:
`board/sunxi/hy310.env` (`h713_mips_dev=1#hy310-boot`), die Kernel-Befehlszeile (`root=PARTLABEL=hy310-rootfs`),
`hy310-mkimage` (GPT-Bau und Platzhaltertabelle), `hy310-install` (Schreibsperre, Erkennung, Stock-Rückweg), die
Abbildtabelle, `h713-hdcp-key` (sucht `/dev/disk/by-partlabel/hy310-keys`) und jede Doku, die ein Layout zeigt.

**Ein Wechsel dort muss in einem Zug gemacht und einmal am Gerät bewiesen werden** - ein Abbild mit neuen
Partitionsnamen und altem `bootargs` startet nicht. **Empfehlung:** die Partitionsnamen so lassen. Sie sind ein
Kennzeichen des Layouts dieses Geräts, nicht des Werkzeugs, und der Nutzen des Wechsels ist gering gegenüber dem
Risiko. Falls doch: eigener Durchgang **nach** Paket A, mit Kaltstartserie.

## B.4 Wie umbenannt wird

- **Ein Durchgang je Werkzeug**, nicht alles auf einmal: Dateien verschieben, Aufrufe nachziehen, Doku nachziehen,
  bauen, am Gerät prüfen, erst dann das nächste.
- **Aufrufer nicht vergessen:** `install-projekt.sh`, `build-rootfs.sh`, `overlay/` (Units, `modprobe.d`),
  `mkimage-eingaben.sh`, `hy310-install.py` (`--extraktor`), die Testskripte, `doku/50-befehle.md`.
- **Kompatibilität:** ein Symlink vom alten auf den neuen Namen kostet nichts und rettet jede Anleitung, die schon
  geschrieben ist. Für `h713-tv` zusätzlich die Unit-Namen bedenken (`h713-tv@video1`), dort hängt udev dran
  (`99-h713-tv.rules`).
- **Nicht anfassen:** alles unter `re/`, die Nachtlogs (sie sind Protokolle eines Zeitpunkts), und historische
  Pläne. Nur die lebenden Dokumente werden nachgezogen.

## B.5 Abnahme

Gerät startet, Bild kommt, Ton kommt, `ctl status` antwortet, HDCP-Schlüssel wird übergeben, 20 Kaltstarts sauber,
und ein `grep -rn "h713-tv\|h713-pq\|h713-extract\|h713-fel\|h713-hdcp-key"` findet außerhalb von `re/`,
`doku/nachtlog/` und den Symlinks nichts mehr.
