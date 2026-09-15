# Paket G - PQ-Werkzeug `hy310-pq`

> **Überholt in einem Punkt (07.09., 06:38):** die Sättigungsrechnung dieses Laufs
> (`Benutzerwert → Werkskurve → Registerwert`, `standard` → `0x4C`) ist durch die Messung am Gerät widerlegt.
> Korrektur, Begründung und Vorher/Nachher: [`G-korrektur-saettigung.md`](G-korrektur-saettigung.md).
> Alles Übrige dieses Logs - Datenlage, `tvin`-Frage, Gamma-LUT - gilt unverändert.

Agent: Paket G (offline, komplett). **Kein Board angefasst** - kein `ssh root@192.168.8.141`, kein
`ssh user@192.168.8.162`, kein `sonoff_ctl`, kein `wandcheck.py`, kein `tio`, kein `/dev/ttyACM0`, kein `sudo`,
kein `git commit`, kein `build.sh`, keine Änderung an `mainline/patches/kernel/series`.
Vendor-Binärdaten wurden nur **gelesen**, nichts davon liegt in `userspace/`.

---

**21:46** Nachtplan (doku/78, Abschnitt 0 / 3 „G" / 3 „H") und `nachtlog/00-koordination.md` gelesen.
Anschließend die Eingaben: `re/vendor/HY310/extracted/vendor_a/etc/tvconfig/` (`ls -la`, `sqlite3 .schema`
und vollständiger Tabellenabzug), `legacy/userspace/hy310-pqd/CALCULATEGAMMA_RE_GUIDE.md`, `BACKGROUND.md` §5/§6,
`src/pqgamma.cpp`, `src/pq_calculate_gamma.cpp`, `include/pqconfig.h`, `tests/`,
`analyse/hdmi-seq/pq_saturation.py`, doku/77 §4, doku/76 §11/§13.

**21:47** Befunde aus den echten Daten (nicht aus dem Gedächtnis):

* `tvpq.db`: `Picture_Mode` 25 Zeilen (`tvin` 0..4, Modusnamen `standard/cinema/vivid/game/computer/hdr/custom`),
  `White_Balance_Mode` 20 Zeilen **durchgängig neutral** (512/512/512, Offset 0), `Gamma_Point` 33 Zeilen
  **durchgängig 0** - als Kurve unbrauchbar, Stock rechnet sie zur Laufzeit (BACKGROUND.md §6.2).
* `pqcontrol_config_setting.xml` enthält `<transform><item name="gamma" level0="1.8" … level4="2.4"/>`. Das ist
  **wertgleich** zur RE-Tabelle `dword_4A50` (180/200/210/220/240) aus `libhaldisplay.so` und zum Kommentarkopf
  von `pq_picturemode.ini` - drei unabhängige Belege für Gamma-Index → Exponent. Alle Presets stehen auf Index 3
  = 2.2.
* `pq_factory_extern.ini`: alle fünf `[PICTURE_CURVE_*]`-Gruppen sind wertgleich; für `VGA1..3` gibt es **keine**
  Gruppe. Sättigung HDMI `0,48,96,145,192` wie in doku/77 §4.
* **Die `tvin`-Nummerierung der Datenbank lässt sich aus den ausgelieferten Dateien nicht auflösen** (nur die
  Klasse: `tvin` 0 = HDMI/VGA-artig, 1/2 = ATV/CVBS, 3/4 = DTV/VIDEODEC). Die Enum-Fassung im Legacy-Code
  (`legacy/.../include/pqconfig.h`: `VIDEODEC=0, HDMI1=1, HDMI2=2, CVBS=3, ATV=4, DTV=5`) **widerspricht den
  Daten**: `tvin` 0 führt `computer`, das die VIDEODEC-Sektion nicht kennt, `tvin` 3 führt `hdr`, das die
  CVBS-Sektion nicht kennt. Sie ist geraten und wurde nicht übernommen. `hy310-pq` rechnet deshalb über die
  **benannten** INI-Sektionen und benutzt die Datenbank nur als Kreuzprobe über die Spalte `name`.
* Zwei verschiedene Gamma-LUT-Pfade in den Legacy-Unterlagen sauber getrennt: unser DE2-Pfad (512 u32 je Bank,
  `pqgamma.cpp`) gegen den MIPS-Pfad (6 × 1024 int16 nach `0x4B48xxxx`, `pq_calculate_gamma.cpp`). Letzterer
  enthält laut eigenem Kommentar **synthetische** Basiskurven und ist als Referenz für unsere LUT unbrauchbar.

**21:50** `userspace/hy310-pq/` gebaut: Python 3, nur Standardbibliothek, kein Daemon, kein `/dev/mem`.
Drei Module streng getrennt - `quellen.py` liest (SQLite, eigener INI-Leser für den Vendor-Dialekt, XML,
`portmap.cfg`), `modell.py` rechnet (Werkskurve, Sättigungs-Gain, Gamma-Stützpunkte → LUT → DE2-Packung),
`ausgabe.py` druckt/schreibt. Befehle: `list`, `show`, `saturation`, `gamma`.

**21:52** Vergleichsharness `tests/legacy_ref.cpp` gegen `legacy/userspace/hy310-pqd/src/pqgamma.cpp` gebaut
(`g++ -O2 -std=c++17`, kein `/dev/mem`, nur `GammaCurve::from_exponent` + `interpolate`). Erster Lauf:
**bitgleich**.

**21:55-21:56** Abnahme gefahren (siehe unten), 25 Tests grün, Doku geschrieben
(`doku/81-pq-datenmodell.md`, `userspace/hy310-pq/README.md`).

---

## Abnahme

### 1. `hy310-pq show HDMI1 vivid`

```
Eingang HDMI1   Bildmodus vivid   Kurvengruppe HDMI
Benutzerwerte aus: pq_picturemode.ini
Kreuzprobe       : tvpq.db Picture_Mode (name='vivid', 5 Zeilen, tvin 0..4) stimmt Wert fuer Wert ueberein

Groesse            Benutzer  Kurve/Exponent  Zielwert                                      Stand                 Beleg / Hinweis
-----------------  --------  --------------  --------------------------------------------  --------------------  --------------------------------------------------
brightness         50        512             -                                             offen (K5)
contrast           55        2515.6          -                                             offen (K5)
saturation         60        115.6           0x05140508 [23:16] = 0x5C  (Wort 0x145C0000)  belegt                cstenger 5718e4c + Messung 06.09. (doku/77 Absch. 4)
hue                50        512             -                                             offen (K5)
sharpness          60        154             -                                             offen (K5)
tnr                2         -               -                                             RPC (Paket I)         MIPS-PQ-Aufruf, kein Register in unserem Pfad
snr                1         -               -                                             RPC (Paket I)         MIPS-PQ-Aufruf, kein Register in unserem Pfad
colortemperature   1         -               Weissabgleich (CTM, Paket H)                  neutral in den Daten  COOL: Gain 512/512/512, Offset 0/0/0
gamma              3         2.2             DE2-LUT 0x05208000/0x05208800/0x05209000      belegt                Exponent 2.2; Schreibsequenz BACKGROUND.md 5.3, Pkt H
dci                3         -               -                                             RPC (Paket I)         MIPS-PQ-Aufruf, kein Register in unserem Pfad
blackextension     1         -               -                                             RPC (Paket I)         MIPS-PQ-Aufruf, kein Register in unserem Pfad
backlight          100       -               -                                             RPC (Paket I)         MIPS-PQ-Aufruf, kein Register in unserem Pfad
dynamic_backlight  0         -               -                                             RPC (Paket I)         MIPS-PQ-Aufruf, kein Register in unserem Pfad

Belegter Schreibpfad Saettigung (wird NICHT von hier geschrieben):
  ssh root@192.168.8.141 'python3 /root/pq_saturation.py vivid'
  -> Register 0x05140508, Gain-Feld [23:16] = 0x5C
Belegter Schreibpfad Gamma: DE2-LUT, Paket H (Kernel, GAMMA_LUT).
  LUT erzeugen: hy310-pq gamma 2.2 --lut gamma.bin

Offen: Helligkeit, Kontrast, Farbton, Schaerfe -- Zielregister unbekannt (RE-Frage K5). Kein Register geraten.
```

`standard` liefert `0x4C` (Wort `0x144C0000`), `cinema` `0x44` - genau die Tabelle aus doku/77 §4, die am
06.09. an der Wand gemessen wurde. **Grün.**

### 2. `hy310-pq gamma 2.2 --lut out.bin`

```
Gamma-Exponent 2.2
  Stuetzpunkte : 33 Werte, 12 Bit (Raster wie tvpq.db::Gamma_Point)
               : 0, 2, 9, 22, 42, 69, 103, 145, 194, ...
  LUT          : 1024 Eintraege, lut[0]=0  lut[512]=894  lut[1023]=4095
  DE2-Format   : 512 u32 je Bank, u32[i] = (lut[2i+1] << 12) | lut[2i]  (BACKGROUND.md 5.4)
    u32[0..3]: 0x00000000, 0x00000000, 0x00000000, 0x00000000
  u32[256..]: 0x0038237E, 0x0038A386, 0x0039238E, 0x0039A396
  Baenke       : R 0x05208000  G 0x05208800  B 0x05209000
  Steuerung    : 0x051C00E8 (Status 0x051C0174), Schreibsequenz BACKGROUND.md 5.3 -- ausgefuehrt von Paket H
  Kanal        : r
  Datei        : <scratchpad>/out.bin (2048 Byte)
```

(Die ersten vier Wörter sind echt 0: bei Gamma 2.2 sind `lut[0..7]` alle 0.)

### 3. Vergleich gegen den Legacy-Rechner - **bitgleich**

```
$ g++ -O2 -std=c++17 -I legacy/userspace/hy310-pqd/include \
      legacy/userspace/hy310-pqd/src/pqgamma.cpp \
      userspace/hy310-pq/tests/legacy_ref.cpp -o legacy_ref
$ ./legacy_ref 2.2 legacy.bin
exponent=2.2000 punkte[0]=0 punkte[16]=891 punkte[32]=4095 lut[0]=0 lut[512]=894 lut[1023]=4095 bytes=2048
$ cmp legacy.bin out.bin      # kein Unterschied
$ sha256sum out.bin legacy.bin
3bf0d7570400cf4d6d301276627a5e58bd0ddd65b561e4ac3d825b9f93a43d7f  out.bin
3bf0d7570400cf4d6d301276627a5e58bd0ddd65b561e4ac3d825b9f93a43d7f  legacy.bin
```

Nicht nur für 2.2: der Test `TestGegenLegacy` vergleicht 1.0/1.8/2.0/2.1/2.2/2.4 byteweise, alle bitgleich.
Bitgleichheit heißt hier: gleiche Rundung (C-`lround`, kaufmännisch von der Null weg), gleiche
Q16-Segmentgrenzen `((1023<<16)/32)`, gleiche C-Ganzzahldivision (Abschneiden Richtung Null), gleiche
Endpunktbehandlung, gleiche Packung `(lut[2i+1] << 12) | lut[2i]`, little-endian.

Zum Harness: `GammaWriter::pack_lut` ist privat, deshalb ruft `legacy_ref.cpp` die **öffentliche**
`interpolate()` aus dem Legacy-Code auf und packt mit der Formel, die in `pqgamma.cpp`, `pqgamma.h` und
BACKGROUND.md §5.4 wortgleich steht. Die Kurvenrechnung selbst stammt unverändert aus dem Legacy-Code.

### 4. Tests

```
$ python3 tests/test_hy310_pq.py
Ran 25 tests in 0.23s
OK
```

Darunter: Zeilenzahlen der Datenbank (25/20/33), Neutralität von Weißabgleich und Farbtemperatur,
Werkskurven-Stützstellen, Gamma-Stufen aus dem XML, Sättigung gegen die belegte Tabelle **und** gegen
`pq_saturation.py` für alle Benutzerwerte 0..100, die Kontrollzahlen aus `CALCULATEGAMMA_RE_GUIDE.md` §11,
Packformat, Dateigrößen (2048 / 6144 Byte) und der Bitvergleich gegen den Legacy-Rechner. Alle Tests lesen die
echten Vendor-Dateien zur Laufzeit und überspringen sich sauber, wenn der Pfad fehlt.

---

## Ein Wort zu den Kontrollzahlen aus dem RE-Guide

`CALCULATEGAMMA_RE_GUIDE.md` §11 nennt für Gamma 2.2 „`lut[512] ≈ 891`". Unser (und des Legacy-Rechners) Wert
ist **894**. Das ist kein Fehler: 891 ist der **Stützpunkt bei t = 0,5** (Punkt 16 von 33,
`pow(0.5, 2.2)*4095 = 891,4`), der LUT-Index 512 liegt aber bei t = 512/1023 = 0,5005. Der Stützpunkt 16 ist bei
uns exakt 891 - der Harness druckt ihn mit. Die Identitätsprobe (`lut[0]=0`, `lut[512]≈2048`, `lut[1023]=4095`)
stimmt ebenfalls.

## Ergebnisdateien

* `userspace/hy310-pq/` - `hy310-pq` (Einstieg), `hy310_pq/{quellen,modell,ausgabe,cli}.py`, `README.md`,
  `tests/test_hy310_pq.py`, `tests/legacy_ref.cpp`
* `doku/81-pq-datenmodell.md` - Seite „PQ-Datenmodell"
* LUT-Dateien der Abnahme liegen im Scratchpad, nicht im Repo (keine Binärdaten abgelegt).

## Für Paket H

* LUT-Datei: `hy310-pq gamma 2.2 --lut gamma.bin` → 2048 Byte = **eine** Bank (512 × u32, little-endian, direkt
  in der Schreibreihenfolge). `--kanal all` → 6144 Byte = R, G, B hintereinander. Weil der Weißabgleich in
  diesen Daten neutral ist, sind die drei Bänke identisch.
* Zielbänke `0x05208000` / `0x05208800` / `0x05209000`, Steuerung `0x051C00E8`, Status `0x051C0174`;
  Schreibsequenz **exakt** wie BACKGROUND.md §5.3 (11 Schritte).
* Für einen Bildmodus statt eines freien Exponenten: `hy310-pq show HDMI1 standard --lut gamma.bin` nimmt den
  Gamma-Index aus dem Preset (überall 3 = 2.2).

## Offen / Board-Anfrage

* **Keine Board-Anfrage.** Paket G ist vollständig offline abgeschlossen.
* **K5 bleibt offen** (Helligkeit/Kontrast/Farbton/Schärfe → Zielregister). `hy310-pq` gibt für diese vier
  Größen nur Benutzerwert und Kurvenwert aus und erfindet kein Register. Sobald K5 ein Register liefert, ist es
  eine Zeile in `modell.kette()`.
* Die `tvin`-Nummerierung von `tvpq.db` bleibt offen (siehe doku/81 §5); sie hat heute keine praktische Folge,
  weil alle Zeilen mit gleichem Modusnamen über alle `tvin` hinweg wertgleich sind.
