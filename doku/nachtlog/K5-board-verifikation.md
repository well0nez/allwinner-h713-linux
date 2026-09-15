# K5 am Gerät verifiziert (Board-Agent = Hauptsitzung, 22:45-22:50)

Board im Zustand nach der A-Abnahme (Bild live auf der Wand, `0x06940928 = 0xE0020438`).
Werkzeug `analyse/hdmi-seq/pq_probe.py` (von Paket K5 geschrieben), Abzüge in
`re/captures/weltneuheit/ours-20260907-nacht/K5/`.

## Korrektur am Werkzeug

`pq_probe.py` importierte `Session` aus `hdmi_seq` - diese Klasse gibt es nicht, sie heißt **`CpuComm`**
(die Signatur `call(name, params) -> (n, vals, ms)` passt unverändert). Der K5-Agent konnte das ohne Board
nicht bemerken. Korrigiert in Zeile 21 und 104, Fassung auch am Board unter `/root/pq_probe.py`.

## (a) Schreibsperre - offen

`0x0500121C = 0x00000000`, unterste vier Bit `0x0` → **die Firmware verwirft PQ-Schreibzugriffe nicht**.
K5s Abbruchkriterium (`0xA`) trifft nicht zu.

## (b) Der Block ist angebunden und trägt echte Werte

Sofortige Bestätigung von K5s Zuordnung, ohne dass dafür etwas geschrieben werden musste:
`DCI = 2` bei `0x0500123C` und `SNR = 1` bei `0x05001248` - **genau die Werte, die `prep_after_boot.sh`
in Phase 3 per `SetDCI 2` / `SetSNR 1` gesetzt hat**. Der Block ist also der, den die PQ-RPCs bedienen.

## (c) SetContrast → `0x05001234[31:16]` - belegt

| RPC | `0x05001234` danach |
|---|---|
| Ausgangszustand (nichts gesetzt) | `0x00000000` |
| `SetContrast 20` | `0x00140000` (= 20) |
| `SetContrast 80` | `0x00500000` (= 80) |
| `SetContrast 100` | `0x00640000` (= 100) |

**Feldlage und Register stimmen exakt mit K5s Vorhersage.**

**Negativkontrolle** (zwei Abzüge im Abstand von 3 s, **ohne** RPC): 16 Wörter ändern sich von allein -
`0x05001570…0x050015F8`. Das sind frei laufende Zähler; sie erklären, warum ein roher Diff nach einem RPC
zunächst nach „18 Unterschieden an der falschen Stelle" aussieht. Nach Abzug der Zähler bleiben genau zwei
echte Änderungen: `0x05001234` (der Kontrast) und `0x05001038` (`0xc003003c → 0xc06a003c`, Deutung offen).

## (d) Wirken die PQ-RPCs auf unseren Source-0-Pfad? - **Ja, messbar**

| Vergleich | Differenz im ROI |
|---|---|
| Kontrast 20 → 80 | mean 6,94; **0,84 %** der Bildpunkte > 25 |
| **Kontrast 0 → 100** | mean 11,27; **12,16 %** der Bildpunkte > 25; `hell` 254719 → 303360 |

Der kleine Wert bei 20→80 ist kein Widerspruch, sondern der kleinere Stellweg. Der Extremtest ist eindeutig.
Damit ist K5s Aussage „sehr wahrscheinlich ja" zu **belegt** geworden: die MIPS-PQ-Stufe liegt im Weg unseres
Source-0-Bildes. Paket **I** (V4L2-PQ-Controls) hat damit seine Grundlage.

## Zustand danach

Kontrast wieder auf den Ausgangswert `0` gesetzt (`0x05001234 = 0x00000000`). Bild unverändert live.

## (e) SetBrightness → `0x05001234[15:0]` - ebenfalls belegt, aber ohne Bildwirkung

`SetBrightness 100` → `0x05001234 = 0x00000064`. **K5s einzige verbliebene Vermutung ist damit belegt**:
Helligkeit und Kontrast teilen sich `0x05001234`, Helligkeit in `[15:0]`, Kontrast in `[31:16]`.
Nach Abzug der Zähler ändern sich wieder genau zwei Wörter: `0x05001234` und `0x05001038`.

**Aber:** die Wand ändert sich dabei **nicht** - Differenz zum Ausgangsbild mean 2,51, **0,00 %** der
Bildpunkte > 25, während derselbe Stellweg beim Kontrast 12,16 % ergab. Der Wert wird also geschrieben und
kommt nicht an. Das passt zu K5s Nebenbefund, dass Stock beim Start `mp_dci_data is NULL` und
`Can not get MP GAMMAModuleID` meldet - offenbar ist das Helligkeitsmodul bei uns nicht bestückt.
**Für Paket I heißt das:** `V4L2_CID_CONTRAST` ist belegt und wirkt, `V4L2_CID_BRIGHTNESS` ist belegt und
wirkt **nicht** - bitte nicht als Control anbieten, das nichts tut, sondern erst die Modulbestückung klären.

Beide Werte wurden nach der Messung auf den Ausgangszustand `0x00000000` zurückgesetzt.

## Nicht gemessen

`SetSaturation`, `SetHue`, `SetSharpness`, `SetDCI`, `SetSNR` und die Weißabgleich-Felder - die Methode ist
jetzt aber belegt und kostet je zwei Minuten. Wichtig für Paket G: `0x05140508` (Chroma-Gain, `pq_saturation.py`)
und `SetSaturation` (`0x05001238[15:0]`) sind laut K5 **zwei verschiedene Regler** - das ist noch nicht
gegeneinander gemessen.

## (f) Sättigung - K5 und Paket G müssen beide korrigiert werden (22:58)

K5 schreibt: „`0x05140508` (Chroma-Gain, `pq_saturation.py`) ist **nicht** das Register von `SetSaturation` -
zwei verschiedene Regler, für Paket G zu trennen." **Das stimmt nicht.** Ein einziger RPC schreibt beide:

| `SetSaturation` | `0x05001238` (PQ-Block) | `0x05140508` (Chroma-Gain) |
|---|---|---|
| 0 | `0x00000000` | `0x14000000` (Gain `0x00`) |
| 50 | `0x00000032` | `0x14400000` (Gain `0x40` = 64) |
| 59 | - | `0x144B0000` (Gain `0x4B` = 75) |
| **60** | - | **`0x144C0000` (Gain `0x4C` = 76)** |
| 100 | `0x00000064` | `0x14800000` (Gain `0x80` = 128) |

Die Firmware bildet das Argument **linear** ab: `Gain = floor(Wert × 1,28)`. Es ist derselbe Regler, einmal als
PQ-Wert und einmal als Registerwirkung.

**Der Ausgangswert `0x4C` entspricht exakt `SetSaturation 60`** - das ist der Vorgabewert der Firmware
(`prep_after_boot.sh` ruft `SetSaturation` gar nicht auf).

### Was das für Paket G heißt

`hy310-pq` rechnet heute Benutzerwert → Werkskurve → **Registerwert** und gibt für `standard` `0x4C` aus.
Der Weg der Firmware ist aber Benutzerwert → Werkskurve → **RPC-Argument** → (×1,28) → Register.
Beide Fassungen können nicht gleichzeitig stimmen: G bildet 60 auf `0x5C` ab, das Gerät bildet 60 auf `0x4C` ab.

**Empfehlung:** `hy310-pq` sollte das **RPC-Argument** ausgeben, nicht den Registerwert - dann bleibt die
lineare Umrechnung der Firmware überlassen, wie bei Stock. Der Registerwert bleibt als Kontrollausgabe nützlich,
ist aber `floor(Argument × 1,28)`, nicht das Ergebnis der Kurve. Das ist **nicht heute Nacht** zu ändern; es
gehört als benannter Punkt in `doku/81-pq-datenmodell.md`.

Wirkung auf der Wand bei `SetSaturation` 60 → 100: mean 3,54, **0,56 %** der Bildpunkte > 25 - klein, weil die
Quellseite überwiegend weiß und grau ist. Der Ringinhalt bleibt dabei unverändert (Cb 122,2 / Cr 140,4), wie es
sein muss: der Gain sitzt **hinter** dem Ring.
