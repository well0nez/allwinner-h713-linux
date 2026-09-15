# I4 - Chroma-Gain: ein Eigentümer, Abnahme bestanden

07.09.2026, 18:05 · Board-Sitzung · Punkt 3 des Plans (`doku/91`), Patch `0104`

## Der Fix

- **Anzeigetreiber** (`sun50i-h713-afbd.c`): schreibt `PROC +0x508` nicht mehr - weder beim Einschalten
  (Vollwort `0x144C0000` mit `0x14` in `[31:26]`, das kein Stock-DCTI-Zustand kennt) noch beim
  Abschalten (`gain_idle`-Rückgabe). Die Plane-Eigenschaft `saturation` ist entfernt; bei Stock gab es
  sie nie.
- **Aufnahmetreiber** (`sun50i-h713-hdmirx.c`): nach dem Quellenwechsel im Rearm-Werker (der seit
  `0099` beim Plane-Einschalten läuft) wird der aktuelle Wert von `V4L2_CID_SATURATION` per
  `THal_Vp_SetSaturation` angewandt. Vorgabe **60** (`0x4C`, das am Stock-Gerät beobachtete Register,
  siehe I3). Weil Abschalten das Register nicht mehr zurücksetzt, überlebt der Wert Plane aus/an.
- **`hy310-tv`**: `-s` weg; Sättigung über `v4l2-ctl --set-ctrl=saturation`.

## Abnahme A4 aus `doku/91` - Kernel `a51f5cc7`, Kaltstart, `hy310-tv` gestartet

| Schritt | `0x05140508` | Gain | `G_CTRL` | Wand (angesehen) |
|---|---|---|---|---|
| Plane aus (nach Boot) | `0x04000000` | `0x00` | 60 | - (Konsole) |
| Plane an | **`0x044C0000`** | **`0x4C`** | 60 | **volle Farbe** - kein Grau |
| `saturation=30` | `0x04260000` | `0x26` = ⌊30·1,28⌋ | 30 | - |
| Signal weg (Zuspieler aus) | `0x04260000` | `0x26` | - | Konsole |
| Signal zurück | **`0x04260000`** | **`0x26`** | **30** | **sichtbar entsättigt** |

Register und Control stimmen nach Plane aus/an überein - gestern stand hier `0x4C` gegen `100`
(`I2`). Das obere Byte ist `0x04` geblieben: der MP-DCTI-Zustand 3 (`0x504`, `0x50c`, `0x508`) ist
jetzt in sich stimmig, wie bei Stock.

Fotos: `re/captures/weltneuheit/wand-aktuell/a4-plane-an.jpg`, `a4-sat30-zurueck.jpg`.

Im Log genau eine Freigabe (`Capture laeuft wieder nach 25 ms`), keine Warnung vom Sättigungs-RPC.

## Was **nicht** gemessen ist

- Ob `SetSource` den Gain anfasst. Falls ja, deckt die Anwendung nach dem Wechsel es; falls nein,
  ist sie ein harmloser RPC je Plane-Einschalten.
- Ob Kontrast und Helligkeit ein ebenso nachgelagertes Register haben (`doku/60-offen.md`). Ein
  PROC-Abzug bei gesetztem Kontrast würde es zeigen - nicht gefahren.

## Gegenprobe, die den Test prüft

Auf `GUT-5d504188` (vor `0104`) muss derselbe Ablauf den Verlust zeigen - I2 hat ihn dort gemessen.
