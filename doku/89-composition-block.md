# Der Composition-Block bei `0x05000000` — gelesen am 07.09.2026

**Herkunft der Frage:** cstenger, Commit `8f1aadd` „display: the fetcher was never the problem —
composition is at 852x480" und der Handoff `74fa0f1` vom 06.09.2026. Sein Befund: **Composition treibt
das Panel, AFBD dimensioniert die Ausgabe nicht.** Sein Bild blieb korrupt, obwohl sein AFBD-Block
byteidentisch zu einem funktionierenden Abzug war — weil siebzehn Register bei `0x05000000` auf 852×480
standen, während AFBD 1280×720 holte. Das erklärt bei ihm auch, warum Änderungen an der AFBD-Geometrie
den Bildausschnitt nie bewegt haben.

**Wie weit unsere Abzüge wirklich reichen — mit einer Korrektur.** Paket K5 schreibt, alle unsere Abzüge
endeten bei `0x050000FC`. **Das stimmt nicht**: `dump_state.py` liest den Block `DE0` als
`(0x05000000, 0x400)`, der Abzug `nacht-00-vor-A.txt` enthält 256 Zeilen und endet bei `0x050003FC`.

Damit war die **Hälfte** des Composition-Blocks längst erfasst — Skalierverhältnis `0x05000174`, Geometrie
`0x05000224` und die beiden DE-Schreibkanäle `0x05000278`/`0x050002B8` stehen in jedem unserer Abzüge.
Nur zwei Dinge fehlten: die **Pitch-Register ab `0x05000444`** (jenseits von `0x400`) und der **PQ-Block
bei `0x05001000…0x050015FC`** aus doku/85. Beides ist unten nachgetragen und ab jetzt Teil des Abzugs.

## Gemessen bei laufendem, korrektem Bild

Zustand: Selektor `0x051C006C = 0x39000000` (Video), INCAP-Freigabe `0x06940928 = 0xE0020438`,
Bild vollflächig und farbrichtig auf der Wand.

| Register | unser Wert | Deutung | cstenger (kaputt) |
|---|---|---|---|
| `0x05000000` | `0xFFFFFFFF` | — | — |
| `0x05000030` | `0x00000C00` | | |
| `0x050000F0` | `0x63006060` | | |
| **`0x05000174`** | **`0x00600060`** | **96/96 = 1:1, keine Skalierung** | `0x002B002B` = 43/64 |
| `0x050001B4` | `0x00600060` | zweiter Kanal, ebenfalls 1:1 | |
| `0x05000210` | `0x63006060` | | |
| **`0x05000224`** | **`0x04380780`** | **1080 × 1920** | `0x01E00354` = 852×480 |
| `0x05000274` | `0x00600060` | 1:1 | |
| `0x05000278` | `0xE002021C` | = DE-Schreibkanal (Nachtplan §7), Bit 31 gesetzt | |
| `0x050002B4` | `0x00600060` | 1:1 | |
| `0x050002B8` | `0xE0020438` | = DE-Schreibkanal, Bit 31 gesetzt | |
| `0x05000444` | `0x04380780` | 1080 × 1920 | |
| `0x05000544` | `0x04380780` | 1080 × 1920 | |
| `0x05000804` | `0x00630780` | Breite 1920 | |
| `0x0500080C` | `0x00170438` | Höhe 1080 | |
| `0x05000840` | `0x04390018` | | |
| **`0x05000844`** | **`0x07800067`** | **Pitch 1920** | `0x03540030` = Pitch 852 |
| `0x05000858` | `0x04380018` | | |
| `0x0500085C` | `0x07800067` | Pitch 1920 | |

## Was das für uns heißt

1. **Unser Composition-Block steht richtig** — 1920×1080, Skalierung 1:1. Die Firmware stellt ihn für den
   HDMI-Eingang selbst ein; wir haben ihn nie angefasst und müssen es auch nicht. Das ist der Grund, warum
   unser Bild vollflächig kommt und cstengers nicht: bei ihm verhindert der DECD-Workaround
   (`ring_writes_max = 1`), dass die Firmware Composition je umprogrammiert.
2. **Für Paket D ist das die Adresse zum Nachsehen**, falls die Plane einmal die Geometrie ändert und sich
   am Bildausschnitt nichts tut. Dann liegt es **nicht** an AFBD. Die Werte oben sind die Referenz.
3. **`0x05000278` und `0x050002B8` sind zwei der vier DE-Schreibkanäle** aus Nachtplan §7
   (`0x05000178/1B8/278/2B8`). cstengers „Composition-Block" und unsere „DE-Schreibkanäle" sind also
   dasselbe Registerfenster, aus zwei Richtungen benannt. Beide Bezeichnungen meinen `0x05000000`.
4. **`dump_state.py` sollte erweitert werden.** Ein Fenster, das das Panel dimensioniert, gehört in den
   Standardabzug — sonst sucht der Nächste wieder am falschen Ende. Dasselbe gilt für den PQ-Block bei
   `0x05001000` (doku/85).

## Nicht geprüft

Ob sich die Werte bei einem **Auflösungswechsel** der Quelle mitbewegen (Nachtplan A.6 Punkt 4). Das wäre
die nächste Messung an dieser Stelle und ist für Paket E relevant, sobald `DV_TIMINGS` steht.
