# B2 - Reicht ein Quellenwechsel als Neuanstoß? **Ja.** (Board-Agent, 22:52-22:56)

Auftrag: Board-Anfrage B2 aus `K1-K3-re.md`. Frage: Führt `SetSource` weg und zurück die Gruppe `V_INCAP`
erneut aus, so dass es einen **firmware-eigenen** Reset-Pfad gibt und Paket D/E nicht dauerhaft mit
„Descriptor genau einmal pro Boot" leben muss?

Ausgangslage: der gute Zustand nach der A-Abnahme (Descriptor bereits **einmal** geschrieben, HPD-Zyklus
gefahren, Bild live). **Zwischen den Schritten wurde der Descriptor nicht erneut geschrieben.**

## Ablauf und Messwerte

| Zeit | Schritt | `0x06940928` | `0x06940824` | `0x06940400` | AppTop-Quelle |
|---|---|---|---|---|---|
| 22:52 | guter Zustand | `0xE0020438` | - | - | 3 |
| 22:53:01 | `SetSource(1)` = VideoDec, RETURN 152 ms | `0x60020438` | `0x0000000B` | `0x21` | **0** |
| 22:53:18 | `SetSource(3)` zurück, RETURN 214 ms | **`0xE0020438`** | `0x0000000B` | `0x21` | **3** |

## Der Beweis ist der Reiz, nicht das Registerbild

Nach dem Rückwechsel zählte `0x06940104` wieder (+61/s). Entscheidend ist aber, ob **geschrieben** wird -
Standbild ist nicht Stillstand. Gamma-Reiz `1:0.2:0.2` am Zuspieler:

| | Y | Cb | Cr |
|---|---|---|---|
| vor dem Reiz | 118,5 | 122,2 | 140,4 |
| **mit Reiz** | **61,5** | **113,3** | **177,2** |

Der Ringinhalt folgt also. Auf der Wand: **4,65 %** der Bildpunkte > 25 verändert; nach `1:1:1` kehrt das Bild
auf **0,00 %** genau zurück.

Und: `diff` der INCAP-Register zwischen `b2_gut` und `b2_zurueck` (ohne die Zähler `+0x104`, `+0x544`, `+0x588`,
`+0x59c`, `+0x600…61c`) ergibt **null Unterschiede**. Der Rundlauf ist strukturell folgenlos.

## Ergebnis

**Ein echter Quellenwechsel macht die Capture wieder scharf.** Das ist ein Stock-Pfad - `THal_Vp_SetSource`,
zweimal gerufen - und braucht weder Kaltstart noch HPD-Zyklus noch ein zweites Descriptor-Schreiben.

Damit gibt es jetzt **zwei** belegte Wege, die vom Descriptor abgeschaltete Capture wieder freizugeben:
1. **HPD-Zyklus** (`PullHotPlug` DOWN → UP), Dauer 0,3 s belegt (siehe `M4-hpd-dauer.md`),
2. **Quellenwechsel** (`SetSource` weg und zurück) - dieser hier.

Für Paket **E** ist das die wichtigere Nachricht: `VIDIOC_S_INPUT` ist ohnehin ein Quellenwechsel. Der Treiber
muss also **nicht** auf einen Hot-Plug angewiesen sein, um im Betrieb wieder ein Bild zu bekommen.

## Zwei Korrekturen an bisherigen Annahmen

1. **`0x06940824` Bit 31 und `0x06940400 = 0x61` sind für den Betrieb nicht nötig.** Nach dem Rückwechsel
   stehen sie auf `0x0000000B` und `0x21` - den Werten *vor* dem Descriptor - und das Bild läuft trotzdem
   einwandfrei. Die Deutung aus doku/76 §12.4 und die Erwartung in B1 („`0x21 → 0x61` gehört zur guten
   Sequenz") tragen in dieser Form nicht.
2. Die Polarität ist damit auch geklärt: im **laufenden** Betrieb ist `0x824` = `0x0000000B` (Bit 31 **aus**),
   im abgeschalteten Zustand `0x8000000B`. Das deckt sich mit dem Vergleich 21:47 (Bild lief) gegen 22:22
   (eingefroren) und **widerspricht** der Erwartung in der B1-Vorschrift.

## Nicht gemessen

Ob der Quellenwechsel auch dann trägt, wenn zwischendurch die **Geometrie** der Quelle wechselt
(Auflösungswechsel, Nachtplan A.6 Punkt 4). Das bleibt offen.
