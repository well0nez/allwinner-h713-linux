# I3 - Gain 0x00 ist ein graues Bild. Der Ersatz muss vor dem Löschen stehen.

07.09.2026, 17:45 · Board-Sitzung · Punkt 3 des Plans (`doku/91`), Schritt 3.1

## Messung

Kernel `5d504188`, `hy310-tv` läuft (Plane an), Sättigung über `V4L2_CID_SATURATION`, Register
gelesen, **Bild angesehen** (nicht `wandcheck.py` - Graustufen, für Farbe blind; hier mean 132,2
gegen 131,5 bei völlig verschiedenem Bild):

| `saturation` | `0x05140508` | Gain `[23:16]` | `0x05001238` | Wand |
|---|---|---|---|---|
| Plane an, nichts gesetzt | `0x144C0000` | `0x4C` | - | Farbe |
| **0** | `0x14000000` | **`0x00`** | `0x00000000` | **grau** - Logo grau, Bild grau |
| 60 | `0x144C0000` | `0x4C` | `0x0000003C` | Farbe, wie Ausgang |
| 100 | `0x14800000` | `0x80` | `0x00000064` | Farbe |

`Gain = floor(x × 1,28)` bestätigt (60 → 76 = `0x4C`, 100 → 128 = `0x80`).

## Was das entscheidet

Die Eigentümerfrage war schon entschieden (`SetSaturation` schreibt beide Hälften, Stock hat keine
Plane-Eigenschaft). Offen war einzig, ob der Übergabe-Gain `0x00` ein farbiges Bild lässt. **Nein.**
Also:

1. Der Anzeigetreiber hört auf, `0x05140508` zu schreiben - beim Einschalten (Vollwort mit `0x14`
   in `[31:26]`, das keinem Stock-Zustand entspricht) **und** beim Abschalten (`gain_idle`-Rückgabe).
2. **Aber nicht ohne Ersatz.** Beim Einschalten der Plane muss die Sättigung über den RPC gesetzt
   werden, sonst ist das Bild grau. Der Ort existiert: der Descriptor-Notifier aus `0099` feuert im
   Aufnahmetreiber genau dann. Dort wird der aktuelle Wert von `V4L2_CID_SATURATION` per
   `THal_Vp_SetSaturation` erneut angewandt.
3. Damit hat das Register einen Eigentümer, der Wert überlebt Plane aus/an, und `G_CTRL` sagt die
   Wahrheit - die Abnahme aus `doku/91` (A4: `saturation=30`, echter Signalverlust, Register **und**
   `--get-ctrl` gleich) wird erfüllbar.

## Welcher Vorgabewert

Zwei Quellen widersprechen sich um 10: `pq_picturemode.ini` „standard" sagt **50** (→ `0x40`),
das am Stock-Gerät beobachtete Register (cstenger 5718e4c) sagt **`0x4C`** = **60**. Das Bild, das
heute den ganzen Tag als „das Bild" abgenommen wurde, lief mit `0x4C`. Der Treiber-Vorgabewert wird
deshalb 60 - das beobachtete Stock-Register wiegt schwerer als die Datei, und es ändert nichts an
dem, was Marco gesehen hat. `H713_VIDEO_SAT_DEFAULT 0x4c` war im Quelltext als „user saturation 50"
beschriftet; das ist der Fehler, den `doku/91` Punkt 3.4 nennt.
