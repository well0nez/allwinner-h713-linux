# E6 — Auflösungswechsel: Erkennung steht, DE-Scaler ist der offene Rest

07.09.2026, 19:45–20:15 · Board-Sitzung · Punkt 2 des Plans (`doku/91`), Patch `0107`

## Was jetzt funktioniert (belegt am Gerät)

**Die Erkennung ist vollständig und ehrlich.** `QUERY_DV_TIMINGS` liefert keine
Übersetzungszeit-Konstante mehr, sondern die gemessene Geometrie:

| Quelle | `timings:` | `incap:` | Record (`signal-info`) |
|---|---|---|---|
| 1920x1080 | 1920x1080p, 148500000 Hz | aktiv 1920x1080, total 2200x1125 | `signal_id 21, 60.00 Hz, 1920x1080` |
| 1280x720 | 1280x720p, 74250000 Hz | aktiv 1280x720, total 1650x750 | `signal_id 19, 60.00 Hz, 1280x720` |

Belegt damit:
- **M1** (`E5`): der `SignalChange`-Callback feuert bei reinem Geometriewechsel.
- **M5:** das Signal-Info-Layout stimmt — Wort 5/6 (`0x780/0x438` bzw. `0x500/0x2d0`) = INCAP exakt.
  Der `args[1]`-statt-`args[2]`-Bug ist behoben, `signal-info` zeigt den Record dekodiert.
- Totale aus INCAP `+0x548`, Pixeltakt gerechnet (`h_total × v_total × Rate`).
- **M3:** die Plane liest 720p korrekt — **Y-Stride `0x500` = 1280, C-Stride `0x0A00` = 2560**
  (NV16-Doppel, keine Chroma-Streckung). Der Descriptor wird nicht neu geschrieben (`published=false`).

**Ein Fehler des Vorschlags gefunden und behoben:** `mode_config.min_width/min_height` standen auf
der Panelgröße, also wies der DRM-Kern jeden kleineren Framebuffer mit `AddFB2: Invalid argument` ab.
Gesenkt auf `H713_VIDEO_BLOCK`/2; seither kommt die 720p-Plane hoch.

## Was NICHT funktioniert — M2, der DE-Scaler

Die Plane liest 1280×720 richtig, aber die **DE-Composition skaliert nicht**: `0x05000174`
bleibt `0x00600060` (1:1), Pitch `0x05000844` high `0x780` (1920). Das Bild erscheint deshalb
1280 breit links oben, horizontal 1,5-fach umgebrochen (1920/1280), darunter Müll — Foto
`re/captures/weltneuheit/wand-aktuell/p2b-720.jpg`.

**Damit ist M2 beantwortet, und zwar mit „Beweislast bei uns":** Stock zieht die Composition über
`UpdateWce → PanelWinNode` mit; unsere mainline-Kette adoptiert die DE-Konfiguration beim Probe
(„adopting 1920x1080, stride 7680") und fasst den Scaler nie an. Für einen Quellwechsel unter Panel
müssen **wir** den DE-Scaler programmieren (`0x05000174` Verhältnis, `0x05000224` Eingangsgeometrie,
`0x05000844` Pitch, dazu die Koeffizientenbänke `0x05000600…0x05000a98`). Das ist RE-Arbeit an
`doku/89`, nicht gemessen, nicht geraten.

## Der Endzustand — korrekt und definiert

Bis der DE-Scaler steht, fällt `hy310-tv` bei **jeder** Quelle ≠ Panel auf die Konsole zurück, mit
einer klaren Zeile, statt ein verzerrtes Bild zu zeigen. Am Gerät:

| | Wand (std) | Log |
|---|---|---|
| 1080p | 48,7 (Bild) | `bild Plane 38 an` |
| 720p | 10,5 (Konsole) | `Quellgeometrie 1280x720 != Panel … Konsole bleibt` |
| zurück 1080p | 47,6 (Bild) | `bild Plane 38 an` |

Der RPC-Pfad bleibt dabei durchweg `0 ohne Antwort` (Punkt-1-Fix trägt durch den ganzen Wechsel).

## Was der Kernel schon kann und der Scaler nur noch braucht

`0107` ist so gebaut, dass der Rebuild-Pfad (Plane nimmt Quellgeometrie an, `min_width` gesenkt,
`atomic_check` mit `min_scale=1`, Y/C-Stride korrekt) **bereitsteht**; es fehlt allein die
DE-Scaler-Programmierung und, in `hy310-tv`, das Entfernen der Konsolen-Sperre. Der teure Teil —
Erkennung, Format, Stride, Framebuffer — ist erledigt und abgenommen.

## Offen (der eine nächste Schritt)

DE-Scaler 1280×720 → 1920×1080 (und allgemein Quelle→Panel) programmieren. Messvorschrift: bei
laufender 720p-Plane die Register `0x05000174/0x224/0x844` und die Koeffizientenbänke von Stock
abschauen (A/B-Umschalter, `doku/90`), da Stock genau diese Skalierung fährt. Erst dann die
Konsolen-Sperre in `hy310-tv` entfernen.
