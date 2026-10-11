# 193 - Einblendungen über dem Bild: die Tasten per IR und Bluetooth, h713-osd vorverzerrt über dem Warp (11.10.2026)

**Kurz:** Die Fernbedienung wirkt jetzt per IR und Bluetooth: Lautstärke, Stumm und Fokus tun, was sie sollen, und jede
Aktion erscheint als Einblendung über dem HDMI-Bild - eine dunkle, durchscheinende Pille unten mittig, bei Trapez mit
derselben Matrix vorverzerrt wie das Bild, das Stumm-Zeichen oben rechts in der Bildecke, das Fokus-Ende rot. IR dekodierte
nie, weil der Gerätebaum dem Empfänger 24 MHz gab (Kernel 0252-0254). Neu: `h713-keys`, `h713-osd`, die Bibliotheken
`libh713osd` (Zeichnen) und `libh713geom` (die Trapez-Rechnung, aus h713-warp herausgelöst, bitgleiches Binary), ein
Einblendungs-Kanal in `h713-tv`. Am HY310 gemessen: alle 14 IR-Tasten, 7-15 ms je Einblendung, kein verlorenes Warp-Bild,
Signalverlust und Standby. TODO 2.35, 2.43-2.46, 3.4, Teile von 2.48. Plan `doku/192` §5; Paket
`arbeit/einblendungen-20261011/` (PLAN, BERICHT mit jeder Messung, Werkzeuge, Mitschnitte).

## 1 Marcos Entscheidungen

| Frage | Marco |
|---|---|
| Einblendung ohne Signal (über der Konsole) | erst ja; dann **gestrichen** ("zu viel Kopfschmerzen") - ohne Bild wartet die Einblendung |
| Optik | nach Mock-ups: **Pille** (runde Enden, dunkel durchscheinend), **unten mittig**; die eckige Karte in der Mitte nein |
| Stumm | Zeichen bleibt stehen, solange stumm; Lauter **und** Leiser heben Stumm auf |
| Fokus | 20 Schritte je Druck statt 3 ("deutlich höher"); das Fokus-Zeichen größer; am Ende der gedrückte Pfeil **rot** |
| IR-Power | ein und aus wie die Taste (bleibt bei h713-power/logind) |
| Record als Eingangstaste | die Fernbedienung hat keine Record-Taste - Eingangsumschaltung ohne Taste, bis eine gewählt ist |
| Stumm über den Standby retten | optional, nach dem Release |

## 2 IR (Kernel 0252-0254)

`clock-frequency = <24000000>` ließ sunxi-cir `rx_resolution` ganzzahlig zu 2 us statt 2,667 us rechnen: jeder Puls kam mit
0,75 seiner Länge an, NEC dekodierte nie (gemessen 02.10.: Vorspann 6752/3348 us statt 9000/4500, `doku/138`). 0252 nimmt die
Eigenschaft heraus - 8 MHz, exakt 8 us (R_CCU `0x1c0 = 0x81000002`, dcxo24M / 3, nachgelesen). 0253 entfernt die
Herstellerwerte aus 0021. 0254: Keymap `rc-h713-fd02` (die Tabelle aus `customer_ir_fd02.kl` des Herstellers, NEC 0xfd02,
eingebaut, im HY310-Baum benannt, den der G-EU-Baum einbindet). Der PL9-Schlafzustand des IR-Pakets vom 03.10. kam nicht mit:
er antwortete auf die Hersteller-ARISC-Firmware; mit crust PL9 Funktion 3 (gemessen).

Am HY310, 11.10.: alle **14 Tasten** kommen an, dekodieren und wirken (Journal von h713-keys). **Maus und Mikrofon senden
per IR beide `0x0266`** (`PRJ_BRC_PAIR`), saubere Rahmen; eine Sekunde danach bot sich die Fernbedienung zum Koppeln an - per
IR fragen beide Tasten nur nach Bluetooth. `0x0266` war erst `KEY_BLUETOOTH`: der Kernel hängte den IR-Eingang an den
rfkill-Handler (ein Druck hätte wohl Bluetooth abgeschaltet, nicht ausprobiert); jetzt `KEY_F6`. Der Rauschfilter des
Herstellers (NTHR ~100 us) wurde probiert und ist **nicht nötig** (5/5 mit beiden; erste Deutung widerlegt).
Vorsicht beim Messen: eine Fernbedienung, die per Bluetooth an einer anderen Box hängt, sendet kein IR (Runde 1, ungültig).

## 3 Bluetooth: Mikrofon und Maus

Mitschnitt `btmon` beim Halten der Mikro-Taste: Usage `0x0c00cf` (`KEY_VOICECOMMAND`) beim Drücken und Loslassen, dazu
**470 Benachrichtigungen zu 60 Byte auf einem HID-Report-Kanal, ~63/s, ~3,8 kB/s - der Ton**. Format unbestimmt: als
IMA-ADPCM nur Rauschen, Entropie 7,99 Bit/Byte, kein fester Kopf - ein komprimierender Codec (TODO, Codec aus der
Stock-Firmware). Die Maus-Taste hat keinen eigenen Code; danach kommen gewöhnliche Mausberichte (450 in 5 s).

## 4 Aufbau

Siehe `docs/architecture.md` "The display stack". `h713-keys` (Python) liest nur die Stock-Fernbedienung (BLE `1d5a:c081`
und `sunxi-ir`), spricht h713-tv (Lautstärke, Stumm), `h713-focus` und `h713-osd`. `h713-osd` (C) zeichnet mit
`libh713osd` (SDF, keine Schriftdatei), verzerrt über dem Warp mit `libh713geom` vor (Rückwärts-Abbildung, neu) und übergibt
an h713-tv: `osd claim` (zwei ARGB8888-Puffer per SCM_RIGHTS), `osd show N`, `osd picture` (warped/ring/none). h713-tv legt
die Primär-Ebene mit zpos 2 darüber (Kernel 0251), gibt der Konsole vor jeder Master-Abgabe ihren Puffer zurück, und über dem
Warp reist die Änderung im nächsten Warp-Commit mit. Die Abbildung von `matrix.c`/`config.c` nach `libh713geom`: Code und
Daten von h713-warp bitgleich (`.text`, `.rodata`, `.data`, `.data.rel.ro`; nur die Build-ID unterscheidet sich).

## 5 Messungen am HY310 (Warp an, starkes Trapez, ThinkPad als Quelle)

| Was | Ergebnis |
|---|---|
| Einblendungs-Kanal ohne Signal | Claim (Primär-Ebene 34, Konsolen-Puffer 46), `ok waiting`, Wand unverändert |
| über dem Warp, `ctl off`/`ctl auto` | Konsole ohne Einblendung; zurück: Einblendung von selbst wieder |
| 81 Wechsel in ~5 s (20/s) | Warp +324 Bilder, **0 verworfen, 0 busy**, keine Verzögerung > 10 ms in h713-tv |
| ohne Warp (Rohbild) | Kopie ohne Vorverzerrung 0,1 ms, Anzeige 0,2 ms |
| Signal weg (ThinkPad HDMI aus) und zurück, Stumm-Zeichen steht | Konsole ohne Zeichen; nach 2 s Bild, Zeichen von selbst wieder |
| h713-osd-Neustart bei echtem Stumm | Zeichen sofort (h713-osd fragt h713-tv "mute" beim Start und vor jedem Claim) |
| Standby (h713-powers Weg, RTC 30 s) | wach, Bild nach 4,5 s, h713-osd neu verbunden; Stumm danach aus - h713-tv vergisst es beim Neustart (bisher so) |
| Alpha-Art | 25-%-Weiß ("grau") ≠ deckendes Weiß: die Anzeige mischt **gerades Alpha**, unsere Kodierung stimmt (Marcos Augen, zweiter Test) |

Die Kamera der Box sah die Wand nicht (Y = 4 bei Belichtung 5000, Gain 255); was an der Wand stand, sagte Marco.

## 6 Geschwindigkeit

Gemessen je Schritt (`h713-osd ctl status`, Messbau mit `-DOSD_PROFILE`), jeder Schritt gegen die Bilder davor geprüft
(bitgleich, oder höchstens eine Stufe Rundung):

| | erster Entwurf | jetzt |
|---|---|---|
| Lautstärke | 209 ms (Zeichnen), 49 ms mit der ersten Vorverzerrung | **13 ms** (Zeichnen 6,5 + Vorverzerren 6,4) |
| Stumm mit Zeichen | 220 ms | **15 ms** |
| Fokus am Ende | 61 ms | **8 ms** |

Was es brachte: Formen nur in ihrem Rechteck; ein vormultiplizierter Mischdurchgang statt drei Divisionen je Ebene; `sqrt`
statt `hypot`, Kreuzprodukte statt `atan2`; je Zeile die Spanne, in der die Pille voll oder leer ist; Einblendung und
Zeichen als getrennte Bereiche; die Homographie schrittweise je Zeile über die genaue Spanne; Ganzzahl-Abtastung einer
vormultiplizierten Kopie, Kurzweg für vier gleiche Nachbarn. `-O3 -mcpu=cortex-a53` gegen `-O2`: kein messbarer Gewinn. Der
Takt war nicht die Ursache (`schedutil`, 1,2 GHz). Eine GPU-Fassung bewusst nicht (EGL-Abhängigkeit, teilt die GPU mit dem
Warp, Arbeit nur je Tastendruck).

## 7 Offen, nicht gemessen

- Welche Richtung "Fokus hoch" an der Wand fährt (beide Lesarten gesehen, 02./03.10.); ob die BLE-Fernbedienung beim Halten
  wiederholt (dann fährt der Fokus durch, wie per IR).
- Welche Taste die Eingangsumschaltung bekommt; das Mikrofon hörbar machen (Codec); Stumm über den Standby (optional).
- Die Einblendungen am HY300PRO-G-EU (720p; am Rechner bei 1280x720 gerendert, gleiche Proportionen) - nicht am Gerät.
- Ein Ausblenden in Stufen statt schlagartig; das Stumm-Zeichen in stark gestauchten Ecken schärfer (Mehrfachabtastung).
- Das Abbild mit h713-keys/h713-osd ist gebaut beschrieben (`install-projekt.sh` 5i, `build-all.sh` Schritt 6), aber noch
  nicht als Ganzes gebaut und installiert.

## 8 Belege

Commits auf `versuch/einblendungen` (in `main` übernommen): `3bfdfa3` (P0: 0252-0254, h713-keys), `97fb873`/`3fa46b7`/
`58f3fe2` (libh713osd, Optik), `56e3f9e` (libh713geom), `8acd2ce` (Kanal in h713-tv), `a1c63ce` (h713-osd, Geschwindigkeit),
`b814671` (Stumm von h713-tv), `0561a4a` (Abbild). Paket `arbeit/einblendungen-20261011/`: `BERICHT.md` (jede Messung mit
Zeit), `laeufe/` (Mitschnitte IR, Bluetooth, Bauprotokolle), `bilder/mockup/`, `werkzeuge/` (Mitschnitt-, Nachstell- und
Messprogramme).
