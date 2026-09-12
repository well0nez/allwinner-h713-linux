# Paket G — Korrektur der Sättigung: Registerwert → RPC-Argument

Agent: Paket G (Korrekturlauf, offline). **Kein Board angefasst** — kein `ssh`, kein `sonoff_ctl`, kein
`wandcheck.py`, kein `tio`, kein `scp`; kein `sudo`, kein `git commit`, kein `build.sh`, keine Änderung an
`mainline/patches/`. Vendor-Daten unter `re/vendor/` nur **gelesen**, nichts kopiert. Die parallel bearbeiteten
Patches `0091`, `0093`, `0094` wurden nicht berührt.

Auslöser: [`K5-board-verifikation.md`](K5-board-verifikation.md) Abschnitt f — die Messung am Gerät hat den
Rechenweg von Paket G widerlegt.

---

## 06:23 Ausgangslage

`userspace/hy310-pq/` rechnete `Benutzerwert → Werkskurve → Registerwert`:

```
Gain = round(0x4C × Kurve(u) / Kurve(50))     ->  0x05140508 [23:16]
```

Der Anker `0x4C ↔ Benutzerwert 50` stammte aus doku/77 §4: cstenger hatte am Stock-Gerät gefunden, dass `0x4C`
„richtig" aussieht, und weil alle Standardmodi Sättigung 50 führen, wurde das als Kalibrierpunkt genommen.
Das war eine **Annahme**, keine Messung des RPC.

## 06:24 Was die Messung sagt

Aus K5-Abnahme (f): ein einziger RPC schreibt **zwei** Register.

| `SetSaturation` | `0x05001238` (PQ-Block) | `0x05140508` (Chroma-Gain) | Gain |
|---|---|---|---|
| 0 | `0x00000000` | `0x14000000` | `0x00` |
| 50 | `0x00000032` | `0x14400000` | `0x40` |
| 59 | — | `0x144B0000` | `0x4B` |
| 60 | — | `0x144C0000` | `0x4C` |
| 100 | `0x00000064` | `0x14800000` | `0x80` |

Drei Befunde daraus, die den Umbau tragen:

1. **Der PQ-Block spiegelt das Argument 1:1** (`0` → 0, `50` → 0x32, `100` → 0x64). Genauso wie
   `SetContrast 20/80/100` → `0x14/0x50/0x64` (Abschnitt c) und `SetBrightness 100` → `0x64` (Abschnitt e).
   **In diesem Block gibt es keinen Umrechnungsfaktor — bei keiner der drei gemessenen Größen.**
2. **Der Faktor 1,28 sitzt auf dem zweiten, nachgelagerten Schreibzugriff** in den PROC-Block. Ein solcher ist
   bisher nur für die Sättigung bekannt.
3. **`floor`, nicht `round`** — und das ist nicht Geschmackssache, sondern gemessen: 59 × 1,28 = 75,52,
   kaufmännisch gerundet 76, gemessen `0x4B` = 75. Die beiden Nachbarpunkte 59/60 sind genau die Stelle, an der
   sich die beiden Rundungsarten unterscheiden.

Und der Widerspruch zur alten Fassung: `0x4C` gehört zu `SetSaturation 60`, nicht zu Benutzerwert 50.
`prep_after_boot.sh` ruft `SetSaturation` gar nicht auf — `0x4C` ist die Vorgabe der Firmware.

## 06:26 Wohin die Werkskurve gehört (und wohin nicht)

Der Auftrag beschreibt die Kette als `Benutzerwert → Werkskurve → RPC-Argument → (×1,28) → Register`. Beim
Nachrechnen an den Daten trägt die Kurvenstufe an dieser Stelle nicht:

* Die Kurvenwerte laufen bis **192** (Sättigung) und **3588** (Kontrast). Das RPC-Argument läuft nachweislich
  bis **100** (`SetContrast 100` → `0x64`).
* Die Kurve liegt auch nicht zwischen RPC und Register: `SetContrast 100` schreibt 100, nicht 2392 oder 3588.

Also: die Werkskurve liegt **nicht** auf diesem Weg. Was sie statt dessen bedient, ist **offen** und wird als
offen benannt (Werks-/Abgleichsanwendung? eine Tabelle innerhalb der MIPS-Firmware?) — nicht geraten.

Damit bleibt genau **eine ungemessene Stufe**: `Benutzerwert → RPC-Argument`. Belegt ist nur, was links und
rechts steht (Presets 0..100, RPC 0..100, Register = Argument). `hy310-pq` reicht den Benutzerwert 1:1 durch
und schreibt an jeder Ausgabestelle dazu, dass diese Stufe ungemessen ist.

**Warum das heute folgenlos ist** — und das ist nachgerechnet, nicht behauptet: legte man die Werkskurve doch
dazwischen (auf 0..100 normiert), wiche das Ergebnis im ganzen Bereich 0..100 an **genau einer** Stelle vom
Benutzerwert ab: 75 → 76. In den Vendor-Daten kommen als Sättigungswerte nur **45, 50 und 60** vor. Beide
Lesarten liefern für jeden real vorkommenden Wert dasselbe Argument. Ein Test hält das fest
(`test_offene_stufe_aendert_heute_nichts`) und schlägt an, sobald sich daran etwas ändert.

## 06:30 Geändert

**`userspace/hy310-pq/hy310_pq/modell.py`**

* `saettigungs_gain(kurve_u, kurve_50)` **entfernt** — das war die widerlegte Rechnung.
* Neu `rpc_argument(benutzerwert)`: die durchgereichte Stufe, mit der Begründung im Docstring.
* Neu `chroma_gain(argument)`: `argument × 128 // 100`, ganzzahlig, damit kein Gleitkommafehler die Messpunkte
  verfehlt. Ausdrücklich als **Kontrollrechnung** dokumentiert.
* Neu `kurve_als_argument(stuetzstellen, benutzerwert)`: die normierte Kurve als Gegenprobe zur offenen Stufe.
* Neu die Tabelle `PQ_ZIELE` (Helligkeit, Kontrast, Sättigung, Farbton, Schärfe) und `PQ_ZIELE_INDEX`
  (DCI, SNR) mit RPC-Name, Item-ID, Register, Maske, Stand und Wirkung; dazu `PQ_OHNE_REGISTER`
  (TNR, Schwarzdehnung — Adresse 0 in der UIMapping-Tabelle, schreiben nachweislich kein Register).
  Quellen: doku/85 §A.1/§A.4/§A.5 und K5-Abnahme b/c/e/f.
* `Zielwert` hat ein neues Feld `argument`; `Kette` ein neues Feld `saettigung_argument`. `gain` und
  `gain_register` bleiben, sind aber jetzt Kontrollwerte aus dem Argument.
* Registerkonstanten des PQ-Blocks ergänzt (`0x05001228/34/38/3C/48`, Betriebsart `0x0500121C`).
* `GAIN_BEI_BENUTZERWERT_50 = 0x4C` **entfernt** (widerlegter Kalibrierpunkt), dafür
  `ARGUMENT_DER_FIRMWARE_VORGABE = 60`.

**`hy310_pq/ausgabe.py`** — `show` bekommt die Spalte `RPC-Arg` (das Ergebnis) und eine Spalte
„Register — schreibt die Firmware"; die Kurve bleibt als Nebenspalte mit Fußnote. `saturation` druckt die Kette
stufenweise mit `[belegt]`/`[NICHT gemessen]` je Stufe. Der ausgegebene Schreibpfad ist jetzt der **RPC**
(`pq_probe.py rpc SetSaturation <arg>`), nicht mehr das Register-Poken.

**`hy310_pq/cli.py`** — `saturation` bricht nicht mehr ab, wenn es keine Werkskurve gibt (VGA1..3): das
Argument hängt seit der Korrektur nicht mehr an der Kurve. Dafür wird jetzt der Eingangsname geprüft.

**Nicht angefasst: die Gamma-LUT.** Sie läuft nicht über einen RPC, wird von Paket H im Kernel geschrieben und
ist unverändert bitgleich zum Legacy-Rechner — `TestGegenLegacy.test_bitgleich` läuft und ist grün.

## 06:33 Tests

`python3 tests/test_hy310_pq.py` — **33 Tests, alle grün** (vorher 25), einschließlich des byteweisen
Vergleichs gegen `legacy/userspace/hy310-pqd/src/pqgamma.cpp`.

Geänderte Erwartungswerte — **die Rechnung wurde nicht an die Tests angepasst, sondern die Tests an die
Messung**; die Begründung steht jeweils im Test:

| Test | vorher | jetzt | Begründung |
|---|---|---|---|
| `test_belegte_tabelle_doku77` → `test_gemessene_tabelle_k5_abschnitt_f` | cinema `0x44`, standard `0x4C`, vivid `0x5C` | die fünf gemessenen Punkte `0/50/59/60/100` → `0x00/0x40/0x4B/0x4C/0x80` | die alte Tabelle kam aus der Kurvenrechnung, nicht aus einer Messung des RPC |
| `test_registerwort` → `test_kontrollwerte_gain_und_registerwort` | standard `0x144C0000` | standard `0x14400000`, vivid `0x144C0000` | `0x4C` gehört zu Argument 60 = `vivid`, nicht zu 50 |
| `test_gegen_pq_saturation_py` | Bitgleichheit mit `pq_saturation.py` | **entfällt** | die Vorlage trägt die widerlegte Formel; Bitgleichheit mit ihr wäre jetzt ein Fehler |
| `test_offene_zielwerte_haben_kein_register` → `test_alle_kurvengroessen_haben_jetzt_ein_register` | Ziel `-`, Stand „offen (K5)" | Register je Größe, Stand `gemessen` bzw. `RE belegt, ungemessen` | doku/85 §A.1 hat die Register aufgelöst, K5-Abnahme c/e hat zwei davon nachgemessen |
| `test_vga_hat_keine_werkskurve` | `k.gain is None` | Argument 50, Gain `0x40`; Kurvenwert weiterhin `None` | das Argument hängt nicht mehr an der Kurve — VGA hat trotzdem keine Kurvengruppe, und das wird weiter ausgewiesen |

Neu dazugekommen: `test_floor_nicht_round`, `test_firmware_vorgabe_entspricht_argument_60`,
`test_bildmodi_liefern_rpc_argumente`, `test_gain_nur_aus_dem_argument_nicht_aus_der_kurve`,
`test_rpc_argument_ist_durchgereicht_und_begrenzt`, `test_offene_stufe_aendert_heute_nichts`,
`test_kurve_ist_keine_rpc_skala`, `test_ungemessene_felder_zeigen_keinen_wert`,
`test_indexgroessen_ohne_registerschreiben`.

## 06:38 Doku

* [`doku/81-pq-datenmodell.md`](../81-pq-datenmodell.md) auf Fassung 2 gezogen: §2 die Kette mit Stand je
  Stufe, §2.1 die eine ungemessene Stufe samt Messvorschrift, §3 die vollständige RPC→Register-Tabelle,
  §3.1 der Sonderfall Sättigung mit der Messtabelle und der Herkunft des Faktors, §3.2 „Wozu dient dann die
  Werkskurve?" (offen), §6 der Schreibpfad, §7 die neu sortierten offenen Punkte.
* `userspace/hy310-pq/README.md` entsprechend, mit Korrekturkasten oben.

---

## Ergebnisvergleich `hy310-pq show HDMI1 standard`

### vorher

```
Eingang HDMI1   Bildmodus standard   Kurvengruppe HDMI
Benutzerwerte aus: pq_picturemode.ini
Kreuzprobe       : tvpq.db Picture_Mode (name='standard', 5 Zeilen, tvin 0..4) stimmt Wert fuer Wert ueberein

Groesse            Benutzer  Kurve/Exponent  Zielwert                                      Stand                 Beleg / Hinweis
-----------------  --------  --------------  --------------------------------------------  --------------------  --------------------------------------------------------------------------------------
brightness         50        512             -                                             offen (K5)
contrast           50        2392            -                                             offen (K5)
saturation         50        96              0x05140508 [23:16] = 0x4C  (Wort 0x144C0000)  belegt                cstenger 5718e4c + Messung 06.09. (doku/77 Abschnitt 4)
hue                50        512             -                                             offen (K5)
sharpness          50        128             -                                             offen (K5)
tnr                2         -               -                                             RPC (Paket I)         MIPS-PQ-Aufruf, kein Register in unserem Pfad
snr                1         -               -                                             RPC (Paket I)         MIPS-PQ-Aufruf, kein Register in unserem Pfad
colortemperature   0         -               Weissabgleich (CTM, Paket H)                  neutral in den Daten  STANDARD: Gain 512/512/512, Offset 0/0/0
gamma              3         2.2             DE2-LUT 0x05208000/0x05208800/0x05209000      belegt                Exponent 2.2 (pqcontrol_config_setting.xml); Schreibsequenz BACKGROUND.md 5.3, Paket H
dci                2         -               -                                             RPC (Paket I)         MIPS-PQ-Aufruf, kein Register in unserem Pfad
blackextension     1         -               -                                             RPC (Paket I)         MIPS-PQ-Aufruf, kein Register in unserem Pfad
backlight          100       -               -                                             RPC (Paket I)         MIPS-PQ-Aufruf, kein Register in unserem Pfad
dynamic_backlight  0         -               -                                             RPC (Paket I)         MIPS-PQ-Aufruf, kein Register in unserem Pfad

Belegter Schreibpfad Saettigung (wird NICHT von hier geschrieben):
  ssh root@192.168.8.141 'python3 /root/pq_saturation.py standard'
  -> Register 0x05140508, Gain-Feld [23:16] = 0x4C
Belegter Schreibpfad Gamma: DE2-LUT, Paket H (Kernel, GAMMA_LUT).
  LUT erzeugen: hy310-pq gamma 2.2 --lut gamma.bin

Offen: Helligkeit, Kontrast, Farbton, Schaerfe -- Zielregister unbekannt (RE-Frage K5). Kein Register geraten.
```

### nachher

```
Eingang HDMI1   Bildmodus standard   Kurvengruppe HDMI
Benutzerwerte aus: pq_picturemode.ini
Kreuzprobe       : tvpq.db Picture_Mode (name='standard', 5 Zeilen, tvin 0..4) stimmt Wert fuer Wert ueberein

Groesse            Benutzer  RPC-Arg  Kurve/Exp  Register -- schreibt die Firmware                    Stand                   Beleg / Hinweis
-----------------  --------  -------  ---------  ---------------------------------------------------  ----------------------  ------------------------------------------------------------------------------------------
brightness         50        50       512        0x05001234 [15:0] = 50                               gemessen, ohne Wirkung  SetBrightness/Item 3; K5-Abnahme e: 100 -> 0x64
contrast           50        50       2392       0x05001234 [31:16] = 50                              gemessen, wirkt         SetContrast/Item 4; K5-Abnahme c: 20/80/100 -> 0x14/0x50/0x64
saturation         50        50       96         0x05001238 [15:0] = 50  + 0x05140508 [23:16] = 0x40  gemessen, wirkt         SetSaturation/Item 5; K5-Abnahme f: 0/50/100 -> 0x00/0x32/0x64
hue                50        50       512        0x05001238 [31:16] (Wert ungemessen)                 RE belegt, ungemessen   SetHue/Item 6; doku/85 A.1/A.4
sharpness          50        50       128        0x05001228 [23:8] (Wert ungemessen)                  RE belegt, ungemessen   SetSharpness/Item 7; doku/85 A.1/A.4
tnr                2         2        -          kein Register                                        kein Registerschreiben  SetTNR/Item 13; doku/85 A.1/A.5: Adresse 0, wirkt nur ueber das PQ-Treiberobjekt
snr                1         1        -          0x05001248 [7:0] = 1                                 gemessen                SetSNR/Item 12; K5-Abnahme b: prep SetSNR 1, gelesen 1
colortemperature   0         -        -          Weissabgleich (CTM, Paket H)                         neutral in den Daten    STANDARD: Gain 512/512/512, Offset 0/0/0
gamma              3         -        2.2        DE2-LUT 0x05208000/0x05208800/0x05209000             belegt (kein RPC)       Exponent 2.2 (pqcontrol_config_setting.xml); Schreibsequenz BACKGROUND.md 5.3, Paket H
dci                2         2        -          0x0500123C [7:0] = 2                                 gemessen                SetDCI/Item 9; K5-Abnahme b: prep SetDCI 2, gelesen 2
blackextension     1         1        -          kein Register                                        kein Registerschreiben  SetBlackExtension/Item 8; doku/85 A.1/A.5: Adresse 0, wirkt nur ueber das PQ-Treiberobjekt
backlight          100       100      -          -                                                    kein RPC-Ziel bekannt   doku/85 A.1 nennt keine Item-ID -- nicht geraten
dynamic_backlight  0         0        -          -                                                    kein RPC-Ziel bekannt   doku/85 A.1 nennt keine Item-ID -- nicht geraten

Spalte 'RPC-Arg' ist das Ergebnis: der Wert, den THal_Vp_Set<Groesse> bekommt.
Spalte 'Kurve' ist ein Vendor-Datum aus pq_factory_extern.ini; sie liegt NICHT
  auf diesem Weg (ihre Werte laufen bis 192 bzw. 3588, das Argument bis 100).
Der Schritt Benutzerwert -> RPC-Argument ist NICHT gemessen; hy310-pq reicht den
  Benutzerwert durch, weil beide Skalen 0..100 sind. Siehe doku/81 Abschnitt 3.2.

Schreibpfad Saettigung -- ueber den RPC, wie Stock (wird NICHT von hier geschrieben):
  ssh root@192.168.8.141 'python3 /root/pq_probe.py rpc SetSaturation 50'
  Kontrolle danach: 0x05001238 [15:0] = 50  und
                    0x05140508 [23:16] = 0x40 = floor(50 x 1,28)   (Wort 0x14400000)
  Das Gain-Byte selbst ins Register zu schreiben umgeht den PQ-Block und ist NICHT der Weg der Firmware.
Schreibpfad Gamma: DE2-LUT, Paket H (Kernel, GAMMA_LUT) -- kein RPC.
  LUT erzeugen: hy310-pq gamma 2.2 --lut gamma.bin

Offen: Farbton und Schaerfe sind statisch belegt, aber am Geraet nie gemessen;
  fuer Helligkeit ist das Register belegt, die Wand reagiert aber nicht (Modul nicht bestueckt).
```

Die drei Bildmodi im Überblick:

| Bildmodus | Benutzerwert | vorher: Registerwert | jetzt: RPC-Argument | jetzt: Gain (Kontrolle) |
|---|---|---|---|---|
| `cinema` | 45 | `0x44` | **45** | `0x39` |
| `standard` | 50 | `0x4C` | **50** | `0x40` |
| `vivid` | 60 | `0x5C` | **60** | `0x4C` |

`vivid` trifft damit genau die Firmware-Vorgabe `0x144C0000`.

---

## Was offen bleibt

1. **`Benutzerwert → RPC-Argument` ist ungemessen.** 1:1 durchgereicht und überall so gekennzeichnet. Heute
   folgenlos (siehe 06:26), aber nicht belegt. Messung: `THal_Vp_Set*`-Argumente am cpu-comm-Ring mitlesen
   oder den PQ-Block nach einem Moduswechsel am Stock abziehen.
2. **Hat Kontrast/Helligkeit ein nachgelagertes Register wie die Sättigung?** Ungemessen — die Abnahme (c)/(e)
   hat nur `0x05001xxx` abgezogen, nie den PROC-Block, und doku/85 §A.7 findet für `0x05140508` keinen
   statischen Schreiber (Zugriff registerindirekt). Messung: (c)/(e) wiederholen und dabei
   `pq_probe.py blocks 0x05140000 0x600` mit abziehen. **Solange das offen ist, steht in der Tabelle für
   Kontrast und Helligkeit kein zweites Register — auch kein vermutetes.**
3. **Farbton und Schärfe** sind statisch belegt (`0x05001238[31:16]`, `0x05001228[23:8]`), am Gerät nie
   gemessen. Je zwei Minuten mit `pq_probe.py probe SetHue …`.
4. **Wer verbraucht die Werkskurve?** Offen.
5. **`analyse/hdmi-seq/pq_saturation.py` trägt weiterhin die widerlegte Formel** und schreibt das Gain-Byte
   direkt ins Register (umgeht damit den PQ-Block). Für `standard` liegt es 12 Gain-Stufen daneben
   (`0x4C` statt `0x40`). Es gehört nicht zu Paket G, und eine Kopie liegt auf dem Board unter `/root/` —
   deshalb wurde es hier **nicht** angefasst, sondern nur in `README.md` und doku/81 §6 als überholt
   gekennzeichnet. Es sollte zurückgezogen oder auf den RPC-Weg umgestellt werden; das ist Sache dessen, der
   auch die Board-Kopie ersetzen kann.
6. **Für Paket I (V4L2-Controls)** heißt der Stand: `V4L2_CID_CONTRAST` und `V4L2_CID_SATURATION` sind belegt
   und wirken, `V4L2_CID_BRIGHTNESS` ist belegt und wirkt **nicht** (Modul nicht bestückt), `HUE` und
   `SHARPNESS` sind plausibel, aber ungemessen. Die Controls nehmen 0..100 und geben das unverändert an den
   RPC weiter — keine eigene Umrechnung im Treiber.
