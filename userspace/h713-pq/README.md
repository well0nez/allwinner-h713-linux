# h713-pq - Stock-PQ-Daten lesen und in Kernel-Schnittstellen umrechnen

`h713-pq` liest die Bildqualitäts-Daten der Stock-Firmware des HY310 und rechnet daraus die Werte, die unsere
Kernel-Schnittstellen brauchen: das **Argument der PQ-RPCs** (Sättigung, Kontrast, …) und die 512-Einträge-LUT
im DE2-Format für Gamma (Paket G des Nachtplans `doku/78-nachtplan-hdmi-switch.md`).

> **Korrektur vom 07.09.2026.** Die erste Fassung rechnete die Sättigung auf einen **Registerwert**
> (Benutzerwert → Werkskurve → Gain-Byte) und gab für `standard` `0x4C` aus. Die Messung am Gerät
> (`doku/nachtlog/K5-board-verifikation.md` Abschnitt f) hat das widerlegt: die Firmware nimmt ein
> **RPC-Argument 0..100** und rechnet den Gain selbst als `floor(Argument × 1,28)`; `0x4C` gehört zu
> `SetSaturation 60`, nicht zu 50. `h713-pq` gibt seitdem das RPC-Argument aus, der Registerwert ist nur noch
> Kontrollausgabe. Hergang: `doku/nachtlog/G-korrektur-saettigung.md`.

**Das Werkzeug rechnet und druckt.** Es öffnet kein `/dev/mem`, schreibt kein Register, spricht mit keinem Board
und startet keinen Dienst. Wo ein Schreibpfad sinnvoll ist, wird er als **Befehlszeile** oder als **Datei**
ausgegeben; das Schreiben ist Sache des Kernels (Paket H/I) oder eines Board-Skripts.

Datenmodell und Herleitung: [`doku/81-pq-datenmodell.md`](../../doku/81-pq-datenmodell.md).

## Aufrufe

```bash
./h713-pq list                                   # Eingänge, Modi, Werkskurven, Datenlage
./h713-pq show HDMI1 vivid                       # ganze Kette für einen Bildmodus
./h713-pq show HDMI1 standard --lut gamma.bin    # dazu die LUT dieses Modus schreiben
./h713-pq saturation HDMI1 cinema                # Sättigung eines Modus -> RPC-Argument
./h713-pq saturation HDMI1 72                    # Sättigung als Benutzerwert 0..100
./h713-pq gamma 2.2 --lut out.bin                # DE2-LUT aus einem Gamma-Exponenten
./h713-pq gamma 2.2 --kanal all --lut rgb.bin    # R-, G- und B-Bank hintereinander
./h713-pq show HDMI1 standard --json --lut g.bin # maschinenlesbar, für h713-tv (siehe unten)
```

`--daten VERZEICHNIS` setzt das tvconfig-Verzeichnis. Ohne Angabe wird der Reihe nach gesucht:
`$H713_TVCONFIG`, `/etc/h713/tvconfig`, dann `re/vendor/HY310/extracted/vendor_a/etc/tvconfig` im Arbeitsbaum.

Es braucht nur die Python-Standardbibliothek (getestet mit 3.12), kein Paket, keine Installation.

## Maschinenlesbare Ausgabe: `show … --json`

`h713-tv` ruft dieses Programm seit dem 11.09.2026 **beim Start** einmal auf und wendet an, was
zurückkommt (Plan 113 §A.3, Weg (a): eine Quelle der Wahrheit statt derselben Rechnung zweimal). Dafür gibt
es `--json`:

```bash
h713-pq --daten /etc/h713/tvconfig show HDMI1 standard --json --lut /run/h713-tv/gamma-laufzeit.bin
```

**Auf `stdout` steht dann genau ein JSON-Objekt und sonst nichts**; jede Meldung - auch die über die
geschriebene LUT - geht nach `stderr`. Der Exitcode ist 0 oder 2 wie sonst auch.

| Feld | Bedeutung |
|---|---|
| `version` | Fassung des Satzes (`1`). Der Leser verwirft, was er nicht kennt |
| `erzeuger`, `daten` | wer gerechnet hat und aus welchem Verzeichnis |
| `eingang`, `preset`, `quelle` | wonach gefragt wurde und aus welcher Datei die Zeile stammt |
| `modus`, `modus_eigen` | Bildmodusnummer für `THal_Vp_SetPictureMode`; `modus_eigen: false` heißt „die Firmware hat für diesen Namen keinen eigenen Modus" (`energy_saving`, `custom` → Standard) |
| `regler` | die neun Werte, die nach dem Modus gesendet werden, unter den Spaltennamen der Vendor-INI: `brightness contrast saturation hue sharpness tnr snr dci blackextension` |
| `weitere` | `colortemperature`, `gamma`, `backlight`, `dynamic_backlight` - die vier Spalten, für die es heute kein Control gibt |
| `gamma_index`, `gamma_exponent` | Stufe 0…4 und der Exponent dazu |
| `lut`, `lut_bytes`, `lut_sha256` | die mit `--lut` geschriebene Datei; ohne `--lut` alle drei `null`/`0` |
| `presets` | **alle** Bildmodi dieses Eingangs, jeder mit `name`, `modus`, `regler`, `weitere`, `gamma_*` |
| `fehlende_dateien` | was nicht gelesen wurde, mit Grund |

`presets` liegt bei, damit der Leser `ctl preset energy_saving` beantworten kann, ohne einen zweiten
Python-Prozess zu starten; die angeforderte Zeile steht zusätzlich flach im Satz. Beides kommt aus
`modell._preset_satz` und kann deshalb nicht auseinanderlaufen (Test
`test_flache_felder_und_liste_sind_dieselben`).

**Die Bildmodusnummer steht in keiner der acht Vendor-Dateien.** `tvpq.db` führt eine eigene Zählung
(0 standard, 1 cinema, 2 vivid …), die ARM-Bibliothek eine dritte; für den RPC zählt allein die
MIPS-Firmware (0 Vivid, 1 Standard, 3 Game, 6 Computer, 7 Cinema, 12 HDR). Die Tabelle steht mit ihrem Beleg
in `modell.FIRMWARE_MODUS`, Herkunft
[`doku/nachtlog/S14`](../../doku/nachtlog/S14-re-picture-mode.md) §1.2 - sie gehört hierher, weil sie die
letzte Größe war, die dem Satz „Eingang × Bildmodus → was zu senden ist" noch fehlte.

**`--json` liest weniger.** Für den Satz werden nur `pq_picturemode.ini`, `tvpq.db` und
`pqcontrol_config_setting.xml` gebraucht (`quellen.DATEIEN_FUER_SATZ`). `pq_factory_extern.ini` ist 592 kB
groß und allein 85 ms wert - am Gerät gemessen - und liegt seit der Korrektur vom 07.09. nicht mehr auf dem
Rechenweg. Jede andere Ausgabe zeigt alles und liest darum auch alles. Was übersprungen wurde, steht in
`fehlende_dateien` mit dem Vermerk „nicht angefordert"; keine Ausgabe tut so, als hätte sie die Datei
gesehen.

**Eine unlesbare Datei ist nicht tödlich.** Seit h713-tv beim Start mitliest, wäre ein Abbruch beim Lesen
ein Bild weniger: `quellen.lade` fängt Lesefehler je Datei ab und vermerkt sie. Eine zerschossene `tvpq.db`
kostet dann die Kreuzprobe und den Modus `custom`, nicht die Presets. Was danach wirklich fehlt, fällt beim
Rechnen auf - mit dem Namen, um den es geht.

## Datenquellen

Alle Dateien werden **nur gelesen und nie kopiert** - Vendor-Binärdaten bleiben unter `re/vendor/…`.

| Datei | Was daraus benutzt wird |
|---|---|
| `pq_picturemode.ini` | Bildmodus-Presets je **benanntem** Eingang (ATV, DTV, HDMI1-3, VGA1-3, CVBS, VIDEODEC): 13 Benutzerwerte je Modus |
| `pq_factory_extern.ini` | `[PICTURE_CURVE_<Gruppe>]` - Werkskurven Helligkeit/Kontrast/Sättigung/Farbton/Schärfe mit fünf Stützstellen bei 0/25/50/75/100; `[PQ_ENABLE]` - Schalter |
| `pq_colortemp.ini` | `[COLOR_TEMP_<Gruppe>]` - Weißabgleich (Gain 0..1023, Offset ±512) je Farbtemperatur |
| `tvpq.db` | `Picture_Mode` (25 Zeilen), `White_Balance_Mode` (20), `Gamma_Point` (33) - als **Kreuzprobe** zur INI |
| `pqcontrol_config_setting.xml` | `<transform name="gamma">` - Gamma-Index 0..4 → Exponent 1.8/2.0/2.1/2.2/2.4; Vorgabewerte |
| `pqcontrol_custom_setting.xml` | zuletzt am Stock eingestellte Werte, aktive Quelle und Modus je Eingang |
| `portmap.cfg` | Port ↔ Source-ID ↔ Name (HDMI1=1 … ATV=6) |

Nicht ausgewertet, weil nicht Teil der PQ-Kette: `pq_overscan_config.ini` (Geometrie/Overscan),
`atsc_system.xml`, `dvb_system.xml`, `tv_scan_list.xml` (Tuner/Demodulator, Kanalsuche),
`panel_config/panel_config.ini` (Paneltiming), `HDMI_EDID_14/20.bin`.

## Die Kette

```
Eingang × Bildmodus                     pq_picturemode.ini  (Namen), tvpq.db (Kreuzprobe)
   -> Benutzerwert 0..100               belegt: Vendor-Datei
   -> RPC-Argument 0..100               NICHT gemessen - 1:1 durchgereicht, siehe unten
   -> Register                          rechnet die Firmware, nicht wir
```

Die **Werkskurve** aus `pq_factory_extern.ini` steht bewusst *nicht* mehr in dieser Kette. Sie bleibt als
Vendor-Datum in der Ausgabe, ihr Verbraucher ist offen - siehe unten.

## Was belegt ist und was nicht

**Belegt - die Register der fünf PQ-Größen.** Aus der statischen RE der `UIvalueMapping`-Tabelle
(`doku/85-re-pq-register.md` §A.1) und der Board-Abnahme (`doku/nachtlog/K5-board-verifikation.md` c/e/f):

| Größe | RPC | Item | Register | Feld | Registerinhalt | Stand |
|---|---|---|---|---|---|---|
| Helligkeit | `SetBrightness` | 3 | `0x05001234` | `[15:0]` | = Argument | gemessen, wirkt (dunkles Material: std 12,6→22,7, `nachtlog/I0`) |
| Kontrast | `SetContrast` | 4 | `0x05001234` | `[31:16]` | = Argument | gemessen, wirkt (0→100 = 12,16 % der Bildpunkte) |
| Sättigung | `SetSaturation` | 5 | `0x05001238` | `[15:0]` | = Argument | gemessen, wirkt |
| Farbton | `SetHue` | 6 | `0x05001238` | `[31:16]` | = Argument | gemessen 11.09., wirkt (0 magenta, 100 grün) |
| Schärfe | `SetSharpness` | 7 | `0x05001228` | `[23:8]` | = Argument | gemessen 11.09.; Bildwirkung nicht einzeln vermessen |

**Alle fünf Felder dieses Blocks enthalten das RPC-Argument unverändert - 1:1, ohne Faktor.** Die drei
Nachträge vom 11.09.2026 (Helligkeit wirkt doch, Farbton und Schärfe gemessen) stehen mit ihrer Herkunft in
`doku/81-pq-datenmodell.md` §7 Punkte 3 und 4; Plan 113 §A.6 hat sie angefordert.

**Belegt - der Sonderfall Sättigung.** `SetSaturation` schreibt als einziger der drei gemessenen RPCs ein
**zweites** Register, den Chroma-Gain `0x05140508` Bits [23:16] im PROC-Block:

```
SetSaturation(N)  ->  0x05001238 [15:0]  = N
                  ->  0x05140508 [23:16] = floor(N × 1,28)
```

Gemessen bei `N` = 0 / 50 / 59 / 60 / 100 → `0x00` / `0x40` / `0x4B` / `0x4C` / `0x80`. Die Nachbarpunkte 59
und 60 entscheiden die Rundungsart: 59 × 1,28 = 75,52, gemessen ist 75 - also **abrunden**. Der Faktor sitzt
damit **nicht** zwischen RPC und PQ-Block (dort ist es 1:1), sondern auf diesem zweiten, nachgelagerten
Schreibzugriff. Der Ruhewert der Firmware `0x144C0000` (`0x4C` = 76) entspricht genau `SetSaturation 60`;
`prep_after_boot.sh` ruft `SetSaturation` gar nicht auf. Der Feldbereich, den die RPC-Skala 0..100 erreicht,
ist damit `0x00..0x80` - `0xFF` (cstenger: übersättigt) ist über den RPC nicht erreichbar.

**Offen - hat Kontrast/Helligkeit ein solches zweites Register auch?** Unbekannt, und nicht geraten. Die
Board-Abnahme hat für Kontrast und Helligkeit nur den PQ-Block `0x05001xxx` abgezogen, nicht den PROC-Block;
und `doku/85` §A.7 hält fest, dass für `0x05140508` im Abbild **kein** statischer Schreiber existiert (der
Zugriff ist registerindirekt). Messvorschrift: die Messung aus K5-Abnahme (c)/(e) wiederholen und dabei
`0x05140000…0x051405FC` mit abziehen.

**Offen - die Stufe Benutzerwert → RPC-Argument.** Sie ist nicht gemessen. Belegt ist nur, was links und
rechts davon steht: die Vendor-Presets laufen 0..100, und der RPC nimmt 0..100 (`SetContrast 20/80/100`,
`SetSaturation 0/50/100`). `h713-pq` reicht den Benutzerwert deshalb unverändert durch und schreibt das an
jeder Ausgabestelle dazu.

**Offen - wer verbraucht die Werkskurve?** Die Kurve kann diese Stufe **nicht** sein: ihre Werte laufen bis
192 (Sättigung) bzw. 3588 (Kontrast), das Argument nachweislich nur bis 100, und der Registerinhalt ist das
Argument, nicht der Kurvenwert. Legte man die Kurve trotzdem darüber (auf 0..100 normiert), wäre das Ergebnis
für **jeden** Sättigungswert dieser Vendor-Daten identisch: die einzige Abweichung im ganzen Bereich liegt bei
Benutzerwert 75 (→ 76), und 75 kommt in keinem Preset vor (vorkommende Werte: 45, 50, 60). Die offene Stufe
ändert heute also nichts - das ist der Grund, warum sie offen bleiben darf, statt geraten zu werden. Ein Test
sichert genau das ab (`test_offene_stufe_aendert_heute_nichts`).

**Belegt - Gamma-LUT-Format.** DE2-Bänke `0x05208000` (R), `0x05208800` (G), `0x05209000` (B), je 512 × u32 mit
`u32[i] = (lut[2i+1] << 12) | lut[2i]`; Steuerung `0x051C00E8`, Status `0x051C0174`, Schreibsequenz in
`legacy/userspace/hy310-pqd/BACKGROUND.md` §5.3. Die Sequenz führt **Paket H im Kernel** aus, nicht dieses
Werkzeug. Der Gamma-Index→Exponent-Bezug ist dreifach belegt: `pqcontrol_config_setting.xml`
(`level0..level4` = 1.8/2.0/2.1/2.2/2.4), der Kommentarkopf von `pq_picturemode.ini`
(`#gamma :0-1.8,1-2.0,2-2.1,3-2.2,4-2.4`) und die Tabelle `dword_4A50` (180/200/210/220/240) aus
`libhaldisplay.so`.

**Offen - die `tvin`-Nummerierung von `tvpq.db`.** Die INI benennt ihre Eingänge, die Datenbank nummeriert sie.
Aus den ausgelieferten Dateien lässt sich die Nummer nur eingrenzen (`list` zeigt die Kandidaten), nicht
auflösen. Deshalb rechnet `h713-pq` über die **benannten INI-Sektionen** und benutzt die Datenbank nur zur
Kreuzprobe über die Spalte `name`.

**Leer in den Daten.** `Gamma_Point` ist durchgängig 0 (als Kurve unbrauchbar - Stock rechnet die Punkte zur
Laufzeit, BACKGROUND.md §6.2), und der Weißabgleich ist überall neutral (Gain 512/512/512, Offset 0). Deshalb
sind die drei LUT-Bänke identisch, und `h713-pq gamma` geht vom Exponenten aus.

## Aufbau

Drei Module, streng getrennt - eins liest, eins rechnet, eins gibt aus:

| Datei | Rolle |
|---|---|
| `h713_pq/quellen.py` | liest SQLite, INI (eigener Parser), XML, `portmap.cfg`; rechnet nichts |
| `h713_pq/modell.py` | RPC-Argumente und ihre Zielregister (`PQ_ZIELE`), Chroma-Gain als Kontrollwert, Werkskurve, Gamma-Stützpunkte → LUT → DE2-Packung; liest keine Dateien |
| `h713_pq/ausgabe.py` | Tabellen, LUT-Datei, Board-Befehlszeilen |
| `h713_pq/cli.py` | Befehlszeile |

Der Vendor-INI-Dialekt (Werte mit Fortsetzungs-`\`, indizierte Schlüssel wie `PICTURE_CURVE_SETTINGS[3]`,
doppelte Schlüssel in einer Sektion) verträgt sich nicht mit `configparser`; `quellen.py` bringt deshalb einen
eigenen, sehr kleinen Leser mit.

## Tests

```bash
python3 tests/test_h713_pq.py            # 33 Tests
```

Die Tests lesen die **echten** Vendor-Dateien zur Laufzeit und überspringen sich sauber, wenn das
tvconfig-Verzeichnis fehlt. `tests/legacy_ref.cpp` ist der Vergleichsharness: er baut gegen
`legacy/userspace/hy310-pqd/src/pqgamma.cpp` und schreibt dieselbe DE2-Bank; der Test `TestGegenLegacy` vergleicht
sie byteweise für die Exponenten 1.0/1.8/2.0/2.1/2.2/2.4 (fehlt der Legacy-Baum oder `g++`, wird übersprungen).
Der Legacy-Rechner und `h713-pq` sind bitgleich.

Die Sättigungs-Tests prüfen die **gemessenen** Punkte aus K5-Abnahme (f) direkt (`0/50/59/60/100` →
`0x00/0x40/0x4B/0x4C/0x80`), nicht mehr eine Zwischenrechnung. Wo die Korrektur einen Erwartungswert geändert
hat, steht die Begründung im Test selbst.

## Schreiben - über den RPC, nicht ins Register

`h713-pq` schreibt nichts. Der ausgegebene Schreibpfad für die Sättigung ist seit der Korrektur der **RPC**,
so wie Stock ihn benutzt:

```
ssh root@192.168.8.141 'python3 /root/pq_probe.py rpc SetSaturation 60'
```

Das Gain-Byte von Hand ins Register zu schreiben (wie es `analyse/hdmi-seq/pq_saturation.py` tut) umgeht den
PQ-Block `0x05001238` und alles, was daran hängt. **`pq_saturation.py` trägt außerdem noch die widerlegte
Formel** `round(0x4C × Kurve(u) / Kurve(50))`; es ist damit für `standard` um 12 Gain-Stufen daneben. Das
Skript gehört nicht zu diesem Paket (und eine Kopie liegt auf dem Board unter `/root/`), deshalb wurde es hier
nicht angefasst - es sollte aber zurückgezogen oder auf den RPC-Weg umgestellt werden.
