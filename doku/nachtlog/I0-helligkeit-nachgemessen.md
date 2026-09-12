# I0 — Helligkeit wirkt doch. Nachgemessen, mit dunklem Material.

07.09.2026, 11:10–11:25 · Board-Sitzung · Vorarbeit für Paket I

## Warum überhaupt nochmal

`K5-board-verifikation.md` (e) hielt fest: `SetBrightness 100` schreibt `0x05001234 = 0x00000064`,
**„die Wand ändert sich dabei nicht"** — Differenz mean 2,51, 0,00 % der Bildpunkte > 25 — und schloss
daraus: „`V4L2_CID_BRIGHTNESS` … wirkt **nicht** — bitte nicht als Control anbieten".

Marco hat widersprochen: in seinen Tests hat es gewirkt. Er hatte recht, und der Fehler war die Messung,
nicht das Register.

## Was an der alten Messung falsch war

Sie lief gegen eine **fast weiße Seite**. Helligkeit verschiebt den unteren Teil der Kennlinie; auf einer
Fläche, die schon nahe am oberen Anschlag liegt, ist da nichts zu verschieben. Das Kriterium
„0,00 % der Bildpunkte über 25 Graustufen Unterschied" konnte unter diesen Umständen gar nicht anschlagen —
und ein Kriterium, das nicht scheitern kann, prüft nichts. Hier war es das Spiegelbild: eines, das nicht
**gelingen** konnte.

## Aufbau

- Zuspieler auf **20 %** heruntergeregelt (`xrandr --output HDMI-2 --brightness 0.20`), damit dunkles
  Material mit Struktur an der Wand steht statt einer hellen Seite. 6 % war zu wenig — dann verschwindet
  die Projektion im Raumlicht und die Belichtungsautomatik regelt nur noch auf die Wand.
- Bild an der Wand über `hy310-tv` (Paket F), Plane 38 aus dem Capture-Ring.
- **Tageslicht.** Deshalb liegt der ganze Bereich gestaucht (`dunkel 0`, mean um 140) — die absolute Lage
  der Zahlen sagt hier nichts, ihre **Reproduzierbarkeit** schon.
- Kamera unverändert auf Belichtungsautomatik, 30 Bilder Vorlauf (`wandcheck.py`).

## Durchlauf 0 → 255

| `SetBrightness` | 0 | 50 | 100 | 150 | 200 | 255 |
|---|---|---|---|---|---|---|
| `0x05001234` | `0x00` | `0x32` | `0x64` | `0x96` | `0xC8` | `0xFF` |
| std im ROI | 12,6 | 16,2 | **22,7** | 22,7 | 22,7 | 22,7 |
| p95 | 151 | 170 | **185** | 185 | 185 | 185 |

Monoton bis 100, darüber **exakt flach** — vier Aufnahmen mit denselben Zahlen.

## Die Gegenprobe, die scheitern konnte

Zurück und wieder hin, in vier Aufnahmen:

| gesetzt | 0 | 100 | 0 | 50 |
|---|---|---|---|---|
| std | 12,5 | 22,5 | 12,5 | 16,0 |
| p95 | 152 | 186 | 153 | 170 |

Jeder Wert trifft seine eigene Zeile aus dem Durchlauf wieder. Eine Belichtungsautomatik driftet, sie
rastet nicht dreimal auf `std 12,5` und zweimal auf `std 16,0` ein.

## Ergebnis

1. **`SetBrightness` wirkt.** Die Aussage in `K5-board-verifikation.md` (e) ist damit widerlegt; die
   Registerdeutung dort (`0x05001234[15:0]` Helligkeit, `[31:16]` Kontrast) bleibt richtig.
2. **Der Stellbereich ist 0…100.** Über 100 ändert sich nichts mehr — gemessen, nicht erschlossen.
   Für Paket I heißt das: `V4L2_CID_BRIGHTNESS` mit Bereich 0…100 anbieten, nicht 0…255.
3. Die Vermutung aus K5, das Helligkeitsmodul sei „bei uns nicht bestückt" (aus `mp_dci_data is NULL`),
   trägt nicht — jedenfalls nicht für diesen Regler.

## Was diese Messung **nicht** sagt

Wie die Kennlinie genau aussieht. p95 steigt (heller Teil geht hoch), p05 bleibt bei ~115 — im Tageslicht
und mit Belichtungsautomatik ist daraus keine Übertragungsfunktion abzuleiten. Für Paket I reicht es:
Bereich und Wirksamkeit sind belegt, die Kennlinie muss der Treiber nicht kennen.
