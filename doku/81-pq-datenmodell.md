# PQ-Datenmodell - von der Stock-Datei bis zum Register

**Stand 07.09.2026, 06:38 (Nachtlauf, Paket G - Fassung 2 nach der Board-Messung).** Diese Seite beschreibt,
welche Stock-Datei welchen Teil der Bildqualität (Picture Quality, PQ) enthält, wie die Kette
**Eingang → Bildmodus → Benutzerwert → RPC-Argument → Register** läuft, und welche Stufe wodurch belegt ist.
Werkzeug dazu: `userspace/h713-pq/` (ersetzt `analyse/hdmi-seq/pq_saturation.py`).
Vorlage: doku/77 §4, Nachtplan doku/78 Abschnitt 3 „G".

> **Was sich gegenüber Fassung 1 geändert hat.** Fassung 1 rechnete `Benutzerwert → Werkskurve → Registerwert`
> und gab für die Sättigung ein Gain-Byte aus. Die Messung am Gerät
> ([`nachtlog/K5-board-verifikation.md`](nachtlog/K5-board-verifikation.md) Abschnitt f) hat gezeigt, dass die
> Firmware anders arbeitet: sie bekommt ein **RPC-Argument 0..100** und rechnet den Registerwert selbst. Die
> Werkskurve liegt nicht auf diesem Weg. Hergang und Vorher/Nachher:
> [`nachtlog/G-korrektur-saettigung.md`](nachtlog/G-korrektur-saettigung.md).

Die Daten liegen unter `re/vendor/HY310/extracted/vendor_a/etc/tvconfig/` (aus `super.fex`, doku/77 §4). Aufs
Gerät gehören sie nach `/etc/hy310/tvconfig/`, **nicht** ins öffentliche Repo.

---

## 1. Welche Datei was enthält

| Datei | Inhalt | Für die Kette |
|---|---|---|
| `pq_picturemode.ini` | Bildmodus-Presets je **benanntem** Eingang: `[ATV] [DTV] [HDMI1] [HDMI2] [HDMI3] [VGA1] [VGA2] [VGA3] [CVBS] [VIDEODEC]`, je Modus 13 Werte in der Reihenfolge `brightness,contrast,saturation,hue,sharpness,tnr,snr,colortemperature,gamma,dci,blackextenstion,backlight,dynamic_backlight`. `[CONFIG]` nennt `picture_mode=standard,cinema,vivid,game,energy_saving` und `special_mode=computer,hdr,custom` | **Benutzerwerte 0..100** - Startpunkt der Kette |
| `pq_factory_extern.ini` (592 KB) | `[PQ_ENABLE]` Schalter; `[PICTURE_CURVE_HDMI/CVBS/ATV/DTV/VIDEODEC]` mit `PICTURE_CURVE_SETTINGS[1..5]` = Helligkeit, Kontrast, Sättigung, Farbton, Schärfe, je **fünf Stützstellen bei Benutzerwert 0/25/50/75/100**; dazu die großen Tabellen `NR_`, `CTI_`, `SSR_`, `LUMA_`, `CM_TYPE_` | **Werkskurve** - liegt *nicht* auf der Kette Benutzerwert → RPC → Register, Verbraucher offen (§3.2) |
| `pq_colortemp.ini` | `[COLOR_TEMP_*]` mit `STANDARD/COOL/WARM/USER` = `ROffset,GOffset,BOffset,RGain,GGain,BGain` | Weißabgleich (CTM, Paket H) |
| `tvpq.db` (SQLite) | `Picture_Mode` 25 Zeilen (`tvin`,`mode`,Werte,`name`), `White_Balance_Mode` 20 Zeilen, `Gamma_Point` 33 Zeilen | **Kreuzprobe** zur INI, siehe §5 |
| `pqcontrol_config_setting.xml` | `<default …>`; `<transform><item name="gamma" level0="1.8" … level4="2.4"/>` | **Gamma-Index → Exponent** |
| `pqcontrol_custom_setting.xml` | `current_source_type tvin="4"`, `current_data …`, `current_mode mode_videodec/mode_hdmi1/mode_hdmi2/mode_cvbs`, je Quelle ein `custom_*`-Block | zuletzt am Stock eingestellter Zustand |
| `portmap.cfg` | Port ↔ Source-ID ↔ Name: HDMI1=1, HDMI2=2, HDMI3=3, CVBS1=4, CVBS2=5, ATV=6 | Portumschaltung (`HDMI_SetPortMap`), **nicht** die `tvin`-Nummer der Datenbank |
| `pq_overscan_config.ini` | Crop je Auflösung und Seitenverhältnis | Geometrie - nicht Teil der PQ-Kette |
| `atsc_system.xml`, `dvb_system.xml`, `tv_scan_list.xml` | Demodulator-Parameter, Kanalliste | Tuner - nicht PQ |
| `panel_config/panel_config.ini`, `HDMI_EDID_14/20.bin` | Paneltiming, EDID | anderer Pfad (doku/75) |

**Was in den Daten leer ist** - wichtig, weil es sonst wie ein Fehler aussieht:

* `Gamma_Point` ist in allen 33 Zeilen **0**. Als Kurve unbrauchbar. Stock rechnet die Punkte zur Laufzeit
  (`CalculateGamma` in `libhaldisplay.so`, BACKGROUND.md §6.2); keine Vendor-Datei liefert eine fertige LUT.
* `White_Balance_Mode` und `pq_colortemp.ini` sind **durchgängig neutral** (Gain 512/512/512, Offset 0/0/0).
  Deshalb sind die drei Gamma-Bänke R/G/B identisch, und die Farbtemperatur ist in diesen Daten wirkungslos.
* Alle fünf `[PICTURE_CURVE_*]`-Gruppen sind **wertgleich**; die Werkskurve unterscheidet die Eingänge auf
  diesem Gerät nicht. Für `VGA1..3` gibt es **gar keine** Kurvengruppe - `h713-pq` meldet das, statt eine zu
  unterstellen. Seit Fassung 2 ist das kein Abbruchgrund mehr: das RPC-Argument hängt nicht an der Kurve.

---

## 2. Die Kette - und welche Stufe wodurch belegt ist

```
Eingang (HDMI1 …)  ×  Bildmodus (standard, cinema, vivid, game, computer, hdr, energy_saving, custom)
        │                pq_picturemode.ini - benennt die Eingänge            [belegt: Vendor-Datei]
        ▼
Benutzerwert 0..100  (z. B. vivid: Sättigung 60, Kontrast 55, Schärfe 60, Gamma-Index 3)
        │                1:1 durchgereicht                                     [NICHT gemessen, §2.1]
        ▼
RPC-Argument 0..100  THal_Vp_SetSaturation(60), THal_Vp_SetContrast(55), …
        │                die Firmware rechnet, nicht wir                       [gemessen, §3]
        ▼
Register             PQ-Block 0x05001xxx = Argument (1:1)  ·  bei der Sättigung zusätzlich
                     Chroma-Gain 0x05140508 [23:16] = floor(Argument × 1,28)
```

Daneben, **nicht** auf dieser Kette:

```
Werkskurve           pq_factory_extern.ini, [PICTURE_CURVE_<Gruppe>], 5 Stützstellen, linear dazwischen
                     (Sättigung 60 → 115,6; Kontrast 55 → 2515,6; Schärfe 60 → 154)
                     Verbraucher offen - §3.2

Gamma                Index → Exponent → 33 Stützpunkte → 1024 LUT → 512 u32 → DE2-Bänke (Paket H, Kernel)
                     kein RPC - §4
```

Die Größen `tnr`, `snr`, `dci`, `blackextenstion`, `backlight`, `dynamic_backlight` laufen **nicht** über eine
Werkskurve; sie sind Indizes für MIPS-RPCs (`SetTNR`, `SetSNR`, `SetDCI`, `SetBlackExtension`, …). Auch bei
ihnen ist der Registerinhalt das Argument (§3), und für `SetTNR`/`SetBlackExtension` ist statisch belegt, dass
sie **gar kein** Register schreiben (doku/85 §A.1/§A.5).

### 2.1 Die eine ungemessene Stufe: Benutzerwert → RPC-Argument

Diese Stufe ist **nicht gemessen** und wird deshalb hier benannt statt geraten. Belegt ist nur, was links und
rechts davon steht:

* Die Benutzerwerte der Vendor-Presets laufen **0..100** (Kommentarkopf `pq_picturemode.ini`).
* Der RPC nimmt ebenfalls **0..100** und der PQ-Block spiegelt das Argument 1:1 - gemessen für
  `SetContrast` (20/80/100), `SetBrightness` (100) und `SetSaturation` (0/50/100).

`h713-pq` reicht den Benutzerwert deshalb unverändert durch und schreibt an jeder Ausgabestelle dazu, dass
diese Stufe ungemessen ist. **Warum das heute folgenlos ist:** die einzige ernsthafte Alternative wäre, die
Werkskurve doch dazwischenzulegen (auf 0..100 normiert). Für die Sättigungskurve HDMI weicht das Ergebnis vom
Benutzerwert an **genau einer** Stelle ab - Benutzerwert 75 → 76 - und 75 kommt in keinem Preset dieser
Vendor-Daten vor (vorkommende Sättigungswerte: 45, 50, 60). Beide Lesarten liefern für jeden real
vorkommenden Wert dasselbe RPC-Argument. Ein Test in `userspace/h713-pq/tests/` sichert das ab
(`test_offene_stufe_aendert_heute_nichts`); wird die Stufe später gemessen, fällt er auf, wenn sich etwas
ändert.

**Wie man sie messen würde:** Stock in einen bekannten Bildmodus schalten und die
`THal_Vp_Set*`-Argumente am cpu-comm-Ring mitlesen (`pq_probe.py` liest heute nur die Wirkung, nicht das
Argument), oder - billiger - den PQ-Block nach einem Moduswechsel am Stock abziehen: steht dort der
Preset-Wert, ist die Stufe die Identität.

---

## 3. Vom RPC ins Register - was gemessen ist

Alle PQ-RPCs laufen über dieselbe Mechanik: `THal_Vp_Set<Größe>` legt eine Nachricht in die PQ-Warteschlange,
der PQ-Thread ruft `OnHalPq<Größe>Change`, und der ruft `UIvalueMapping(itemID, wert, …)`, das den Wert
maskiert und geschoben in ein Register des Blocks **ARM `0x05001000`…`0x050015FC`** schreibt (doku/85 §A.2).
Die Zuordnung Item-ID → Register kommt aus der statischen RE dieser Tabelle, die Werte aus der Board-Abnahme.

| Größe | RPC | Item | Register | Feld | Registerinhalt | Stand | Wirkung auf der Wand |
|---|---|---|---|---|---|---|---|
| **Helligkeit** | `SetBrightness` | 3 | `0x05001234` | `[15:0]` | **= Argument** | **am Gerät gemessen** (K5-Abnahme e: `100` → `0x64`) | **keine** - 0,00 % der Bildpunkte; Modul nicht bestückt |
| **Kontrast** | `SetContrast` | 4 | `0x05001234` | `[31:16]` | **= Argument** | **am Gerät gemessen** (K5-Abnahme c: `20/80/100` → `0x14/0x50/0x64`) | belegt: 0→100 ändert 12,16 % der Bildpunkte |
| **Sättigung** | `SetSaturation` | 5 | `0x05001238` | `[15:0]` | **= Argument** | **am Gerät gemessen** (K5-Abnahme f: `0/50/100` → `0x00/0x32/0x64`) | belegt: 60→100 ändert 0,56 % (Quelle überwiegend weiß) |
| Farbton | `SetHue` | 6 | `0x05001238` | `[31:16]` | - | statisch belegt (doku/85 §A.1/§A.4), **am Gerät nie gemessen** | ungemessen |
| Schärfe | `SetSharpness` | 7 | `0x05001228` | `[23:8]` | - | statisch belegt, **am Gerät nie gemessen** | ungemessen |
| DCI | `SetDCI` | 9 | `0x0500123C` | `[7:0]` | **= Argument** | **am Gerät gemessen** (K5-Abnahme b: `prep` setzt 2, gelesen 2) | ungemessen |
| SNR | `SetSNR` | 12 | `0x05001248` | `[7:0]` | **= Argument** | **am Gerät gemessen** (K5-Abnahme b: `prep` setzt 1, gelesen 1) | ungemessen |
| TNR | `SetTNR` | 13 | - | - | - | belegt: **kein Registerschreiben** (Adresse 0 in der Tabelle) | - |
| Schwarzdehnung | `SetBlackExtension` | 8 | - | - | - | belegt: **kein Registerschreiben** | - |
| Backlight, dyn. Backlight | - | - | - | - | - | doku/85 §A.1 nennt keine Item-ID - **nicht geraten** | - |
| Weißabgleich | `SetWhiteBalance` | 35-40 | `0x05001274/78/7C` | je 16 Bit | - | statisch belegt; Daten neutral, nichts zu setzen | - |
| **Gamma-LUT** | kein RPC | - | DE2-Bänke `0x05208000/0x05208800/0x05209000`, Steuerung `0x051C00E8`, Status `0x051C0174` | 512 × u32 | - | **belegt** (Format und Sequenz), Schreiben durch **Paket H** | §4 |

**Der eine Satz, auf den es ankommt:** *jedes* am Gerät gemessene Feld dieses Blocks enthält das RPC-Argument
**unverändert**. Es gibt in diesem Block keinen Umrechnungsfaktor - auch nicht bei der Sättigung.

Zwei Steuerworte im selben Block: `0x0500121C` ist die Betriebsart (untere vier Bit `0xA` ⇒ Schreibzugriffe
werden verworfen; am Gerät gemessen `0x00000000`, also frei), `0x050012DC` wird nur für Item-ID 0 nachgeführt.

### 3.1 Sättigung - der Sonderfall mit dem zweiten Register

`SetSaturation` ist der einzige der gemessenen RPCs, der **zwei** Register schreibt: zusätzlich zum PQ-Block
noch den Chroma-Gain `0x05140508` Bits [23:16] im PROC-/„route"-Block.

```
SetSaturation(N)  ->  0x05001238 [15:0]  = N                  (1:1, wie alle anderen)
                  ->  0x05140508 [23:16] = floor(N × 1,28)     (nachgelagert, PROC-Block)
```

Messung (K5-Abnahme f, 07.09.):

| `SetSaturation` | `0x05001238` | `0x05140508` | Gain | `floor(N × 1,28)` |
|---|---|---|---|---|
| 0 | `0x00000000` | `0x14000000` | `0x00` | 0 |
| 50 | `0x00000032` | `0x14400000` | `0x40` | 64 |
| **59** | - | `0x144B0000` | `0x4B` | **75** (nicht 76!) |
| **60** | - | `0x144C0000` | `0x4C` | 76 |
| 100 | `0x00000064` | `0x14800000` | `0x80` | 128 |

Die beiden Nachbarpunkte 59 und 60 entscheiden die Rundungsart: 59 × 1,28 = 75,52; kaufmännisch gerundet wäre
das 76, gemessen ist 75 - also **abrunden**. `h713-pq` rechnet das ganzzahlig als `N × 128 // 100`.

**Woher der Unterschied zu Kontrast und Helligkeit kommt.** Nicht daher, dass die Sättigung im PQ-Block anders
skaliert würde - dort ist sie genauso 1:1 wie Kontrast und Helligkeit. Der Faktor sitzt allein auf dem
**zweiten, nachgelagerten** Schreibzugriff in den PROC-Block, und ein solcher ist bisher nur für die Sättigung
bekannt. Die Firmware bildet dabei die RPC-Skala 0..100 auf den Feldbereich `0x00..0x80` ab; `0xFF` ist im Feld
darstellbar (cstenger `5718e4c`: übersättigt), über den RPC aber nicht erreichbar.

**Offen bleibt:** ob Kontrast und Helligkeit einen analogen nachgelagerten Registerzugriff mit eigenem Maßstab
haben. Das ist **nicht** gemessen - die Board-Abnahme (c)/(e) hat nur den PQ-Block `0x05001xxx` abgezogen, nie
den PROC-Block; und doku/85 §A.7 hält fest, dass für `0x05140508` im Abbild **kein statischer Schreiber**
existiert (der Zugriff ist registerindirekt, Basis + Offset). Messvorschrift: die Messung (c)/(e) wiederholen
und dabei `0x05140000…0x051405FC` mit abziehen (`pq_probe.py blocks 0x05140000 0x600`).

Der Ruhewert der Firmware `0x144C0000` (`0x4C` = 76) entspricht exakt `SetSaturation 60`; `prep_after_boot.sh`
ruft `SetSaturation` gar nicht auf. Nur die Bits [23:16] werden ersetzt, die übrigen Bits des Worts bleiben
stehen (`0x04000000` = Chroma aus, doku/76 §13).

**Was daraus für die Bildmodi folgt** (Fassung 2 - Ergebnis ist das RPC-Argument, der Gain nur Kontrolle):

| Bildmodus | Sättigung (Benutzerwert) | RPC-Argument | Kontrolle: `0x05001238` | Kontrolle: Gain | Registerwort |
|---|---|---|---|---|---|
| `cinema` | 45 | **45** | 45 | `0x39` | `0x14390000` |
| `standard`, `game`, `computer`, `hdr`, `energy_saving`, `custom` | 50 | **50** | 50 | `0x40` | `0x14400000` |
| `vivid` | 60 | **60** | 60 | `0x4C` | `0x144C0000` |

Zum Vergleich Fassung 1 (widerlegt): cinema `0x44`, standard `0x4C`, vivid `0x5C`. Der auffälligste Punkt der
Korrektur: `0x4C` gehört nicht zu `standard`, sondern zu `vivid` - und damit trifft `vivid` genau die
Firmware-Vorgabe.

### 3.2 Wozu dient dann die Werkskurve?

**Offen.** Fest steht nur, was sie *nicht* ist: sie liegt nicht zwischen Benutzerwert und RPC-Argument.

* Ihre Werte laufen bis 192 (Sättigung), 1023 (Helligkeit/Farbton), 255 (Schärfe) und **3588** (Kontrast).
  Das RPC-Argument läuft nachweislich bis 100 (`SetContrast 100` → `0x64`).
* Sie liegt auch nicht zwischen RPC und Register: `SetContrast 100` schreibt `0x64` = 100, nicht 2392 oder 3588.

Damit bleiben als Verbraucher: eine Werks-/Abgleichsanwendung (der Dateiname `pq_factory_extern.ini` legt das
nahe) oder eine Stufe innerhalb der MIPS-Firmware, die den Registerwert vor der Anwendung noch einmal durch
eine Tabelle schickt. **Beides ist nicht belegt, und es wird hier nichts davon behauptet.** `h713-pq` zeigt
den Kurvenwert weiterhin an - als Vendor-Datum mit dem Vermerk, dass er nicht auf der Kette liegt.

---

## 4. Gamma - zwei verschiedene LUT-Pfade nicht verwechseln

Das ist die häufigste Falle in den Legacy-Unterlagen:

1. **DE2-Gamma (unser Pfad, Paket H).** 1024 Abtastwerte à 12 Bit je Farbe, gepackt zu **512 u32**
   (`u32[i] = (lut[2i+1] << 12) | lut[2i]`), in die drei Bänke ab `0x05208000` geschrieben, danach die
   Aktivierungssequenz aus BACKGROUND.md §5.3 (LUT_WRITE_EN/CHAN_LATCH/COMMIT setzen, schreiben, COMMIT
   löschen, Bit 28 kippen, Bits 21/20/26 setzen). Das erzeugt `h713-pq gamma … --lut`.
2. **MIPS-Gamma (nicht unser Pfad).** Sechs 1024×int16-LUTs für die `dwGammaType` `0x30030000..0x30030005` in
   der reservierten DRAM-Region `0x4B48xxxx`, die die MIPS-Firmware **vor** ihrem Start erwartet
   (BACKGROUND.md §6). Dafür ist `legacy/.../src/pq_calculate_gamma.cpp` gedacht - und dessen Fassung enthält
   ausdrücklich **synthetische** Anteile (neun erfundene Basiskurven, weil die echte
   `factory_gamma_curve_table` in `.bss` liegt und zur Laufzeit gefüllt wird). Diese Datei ist deshalb **keine**
   Referenz für unsere LUT.

Der Bezug Gamma-Index → Exponent ist **dreifach** belegt und widerspruchsfrei:

| Index | 0 | 1 | 2 | 3 | 4 |
|---|---|---|---|---|---|
| `pqcontrol_config_setting.xml` `<transform>` | 1.8 | 2.0 | 2.1 | 2.2 | 2.4 |
| Kommentarkopf `pq_picturemode.ini` | 1.8 | 2.0 | 2.1 | 2.2 | 2.4 |
| `dword_4A50` in `libhaldisplay.so` (Gamma × 100) | 180 | 200 | 210 | 220 | 240 |

Alle Bildmodi aller Eingänge stehen in diesen Daten auf Index **3 = 2.2**.

Rechenweg (identisch zum Legacy-Rechner `legacy/userspace/hy310-pqd/src/pqgamma.cpp`, bitgleich verifiziert):

```
33 Stützpunkte   punkte[i] = lround(pow(i/32, exponent) × 4095)        GammaCurve::from_exponent
   -> 1024 LUT   stückweise linear, Q16-Segmentgrenzen ((1023<<16)/32), C-Ganzzahldivision,
                 Endpunkte hart gesetzt                                interpolate()
   -> 512 u32    u32[i] = (lut[2i+1] << 12) | lut[2i]                  pack_lut()
```

Kontrollzahlen (`CALCULATEGAMMA_RE_GUIDE.md` §11): Identität → `lut[0]=0`, `lut[512]≈2048`, `lut[1023]=4095`;
Gamma 2.2 → `lut[0]=0`, Mitte `891`, `lut[1023]=4095`. Der Guide-Wert 891 ist der **Stützpunkt bei t = 0,5**
(Punkt 16). Der LUT-Index 512 liegt bei t = 512/1023 = 0,5005 und ergibt darum **894** - kein Widerspruch,
sondern die Rasterverschiebung zwischen 33 Stützpunkten und 1024 Einträgen.

---

## 5. Die `tvin`-Nummerierung von `tvpq.db` ist nicht auflösbar

`pq_picturemode.ini` **benennt** die Eingänge, `tvpq.db` **nummeriert** sie (`tvin` 0..4). Keine ausgelieferte
Datei enthält die Übersetzung. Was die Daten hergeben - die Menge der Bildmodi je `tvin`:

| `tvin` | Modi der Zeilen | mögliche Eingänge |
|---|---|---|
| 0 | standard, cinema, vivid, game, computer, hdr, custom | HDMI1, HDMI2, HDMI3, VGA1, VGA2, VGA3 |
| 1 | standard, cinema, vivid, game | ATV, CVBS |
| 2 | standard, cinema, vivid, game | ATV, CVBS |
| 3 | standard, cinema, vivid, game, hdr | DTV, VIDEODEC |
| 4 | standard, cinema, vivid, game, hdr | DTV, VIDEODEC |

Damit ist nur die **Klasse** bestimmt, nicht die Nummer. Zwei Hinweise, die nicht ausreichen: `portmap.cfg` ist
eine andere Nummerierung (Port/Source-ID der Firmware, HDMI1=1 … ATV=6), und
`pqcontrol_custom_setting.xml` nennt `current_source_type tvin="4"` bei einer Stock-Sitzung, die als
`mode_videodec` geführt wird - das legt VIDEODEC = 4 nahe, belegt es aber nicht.

Die Enum-Fassung im Legacy-Code (`legacy/.../include/pqconfig.h`: `VIDEODEC=0, HDMI1=1, HDMI2=2, CVBS=3,
ATV=4, DTV=5`) **widerspricht den Daten**: `tvin` 0 führt `computer`, das die VIDEODEC-Sektion nicht kennt, und
`tvin` 3 führt `hdr`, das die CVBS-Sektion nicht kennt. Sie ist geraten und nicht zu übernehmen.

**Konsequenz für `h713-pq`:** Gerechnet wird über die benannten INI-Sektionen. Die Datenbank dient nur der
Kreuzprobe über die Spalte `name` - und die fällt sauber aus: für jeden Modusnamen sind die Werte über alle
`tvin` hinweg gleich und stimmen Wert für Wert mit der INI überein. Praktisch macht die Unklarheit deshalb
heute keinen Unterschied; sie darf nur nicht durch eine geratene Zuordnung verdeckt werden.

---

## 6. Das Werkzeug

`userspace/h713-pq/` (Python 3, nur Standardbibliothek, keine Installation nötig, kein Daemon).

```bash
./h713-pq list                                 # Eingänge, Modi, Werkskurven, Datenlage, tvin-Kandidaten
./h713-pq show HDMI1 vivid                     # ganze Kette, mit Stand je Stufe
./h713-pq show HDMI1 standard --lut gamma.bin  # dazu die LUT dieses Modus
./h713-pq saturation HDMI1 cinema              # bzw. ein Benutzerwert 0..100
./h713-pq gamma 2.2 --lut out.bin              # 2048 Byte = eine DE2-Bank
./h713-pq gamma 2.2 --kanal all --lut rgb.bin  # 6144 Byte = R, G, B hintereinander
```

Es **rechnet und druckt**; es öffnet kein `/dev/mem` und fasst kein Register an. Für die Sättigung gibt es das
**RPC-Argument** aus, dazu als Kontrolle den PQ-Registerinhalt und das Gain-Byte `floor(Argument × 1,28)`.
Der ausgegebene Schreibpfad ist der RPC:

```
ssh root@192.168.8.141 'python3 /root/pq_probe.py rpc SetSaturation 60'
```

**Nicht** mehr `pq_saturation.py`: dieses Ad-hoc-Skript schreibt das Gain-Byte direkt ins Register (umgeht damit
den PQ-Block und alles, was daran hängt) **und** trägt weiterhin die widerlegte Formel
`round(0x4C × Kurve(u) / Kurve(50))` - für `standard` liegt es damit 12 Gain-Stufen daneben. Es gehört nicht zu
Paket G und eine Kopie liegt auf dem Board unter `/root/`, deshalb wurde es in dieser Korrektur nicht angefasst;
es sollte zurückgezogen oder auf den RPC-Weg umgestellt werden.

Tests: `python3 tests/test_h713_pq.py` - 33 Tests gegen die echten Vendor-Dateien (überspringen sich, wenn das
Verzeichnis fehlt), darunter der byteweise Vergleich gegen den Legacy-Rechner (`tests/legacy_ref.cpp` baut
gegen `legacy/userspace/hy310-pqd/src/pqgamma.cpp`) und die fünf gemessenen Sättigungspunkte aus K5-Abnahme (f).

---

## 7. Offene Punkte

Sortiert nach dem, was zuerst zu messen ist:

1. **Benutzerwert → RPC-Argument** (§2.1). Ungemessen; `h713-pq` reicht 1:1 durch. Heute folgenlos, weil die
   einzige Alternative für alle vorkommenden Werte dasselbe liefert. Messung: `THal_Vp_Set*`-Argumente am
   cpu-comm-Ring mitlesen oder den PQ-Block nach einem Moduswechsel am Stock abziehen.
2. **Hat Kontrast/Helligkeit ein nachgelagertes Register wie die Sättigung?** (§3.1). Ungemessen, weil die
   Abnahme nur den PQ-Block abgezogen hat. Messung: (c)/(e) wiederholen und `0x05140000…0x051405FC` mit
   abziehen.
3. ~~**Farbton und Schärfe** sind statisch belegt, aber am Gerät nie gemessen.~~ **Erledigt am 11.09.2026.**
   Mit anliegendem 1080p-Signal Regler gesetzt und die Register über `/dev/mem` zurückgelesen: `hue` schreibt
   `0x05001238[31:16]`, `sharpness` schreibt `0x05001228[23:8]`, beide **eins zu eins über 0…100** (geprüft bei
   0/25/50/75/100). Die drei anderen ebenso: `brightness` `0x05001234[15:0]`, `contrast` `0x05001234[31:16]`,
   `saturation` `0x05001238[15:0]`. **Wirkung am Bild von Marco bestätigt:** `hue = 0` magenta, `hue = 100` grün.
   Ebenfalls bestätigt: der Sättigungs-Gain in `0x05140508[23:16]` folgt exakt `floor(Wert × 1,28)` - die Firmware
   rechnet ihn selbst, wie in der Korrektur vom 07.09. beschrieben.
4. ~~**Helligkeit wirkt nicht.**~~ **Erledigt am 07.09., 11:25 - Helligkeit wirkt, Stellbereich 0…100.**
   Hier stand: „Register belegt und beschrieben, Wand unverändert (0,00 % der Bildpunkte); passt zu den
   Stock-Meldungen `mp_dci_data is NULL` / `Can not get MP GAMMAModuleID`." Beides trägt nicht: die 0,00 %
   liefen gegen eine fast weiße Vorlage, auf der Helligkeit gar nicht anschlagen konnte, und die
   Stock-Meldungen nennen das DCI- und das Gamma-Modul, nicht die Helligkeit. Gegen dunkles Material
   gemessen: std 12,6 → 22,7, p95 151 → 185, monoton bis 100 und darüber flach
   ([`nachtlog/I0-helligkeit-nachgemessen.md`](nachtlog/I0-helligkeit-nachgemessen.md)). Für Paket I:
   `V4L2_CID_BRIGHTNESS` **anbieten, Bereich 0…100**.
5. **Wer verbraucht die Werkskurve?** (§3.2). Offen; nicht geraten.
6. **Wo kommen die 33 Gamma-Stützpunkte im Betrieb her?** In den Vendor-Daten sind sie 0; Stock rechnet sie.
   Für uns ist der Exponent aus dem Bildmodus die Quelle - solange niemand eine Werkskalibrierung findet.

Erledigt seit Fassung 1: *„Zielregister von Helligkeit/Kontrast/Farbton/Schärfe unbekannt"* (doku/85 §A.1 +
K5-Abnahme c/e) und *„wirken die MIPS-PQ-RPCs auf unseren AFBD-Source-0-Pfad?"* (K5-Abnahme d: Kontrast
0→100 ändert 12,16 % der Bildpunkte - **ja**).
