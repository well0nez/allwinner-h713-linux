# S1 — Der Scaler ist gefunden, und `doku/89` lag zweifach falsch

07.09.2026, 18:45–19:40 · idalib auf `display.bin` + Messung am Gerät · Plan [`doku/92`](../92-plan-de-scaler.md)

## Werkzeug

idalib läuft (`~/.idapro/idalib-venv/bin/python`, `.pth` auf `/opt/ida-pro-9.1/idalib/python`
und `/opt/ida-pro-9.1/python`). Hexrays dekompiliert MIPS. Die brauchbare Datenbank ist
`re/ida/weltneuheit/re_chain/display.bin.i64` — dort sind die Pipeline-Knoten benannt.
Gearbeitet wurde auf **Kopien** im Scratch, nie auf den Originalen.

## Zwei widerlegte Annahmen aus `doku/89`

**1. Die 852×480-Spalte ist kein Stock-Abzug.** Sie ist cstengers *kaputter* Zustand — sein
DECD-Workaround (`ring_writes_max = 1`) hat die Firmware am Umprogrammieren gehindert. Der
Plan `doku/92` hatte sie als Referenzpunkt für die Formelprüfung eingeplant; dieser Punkt
entfällt ersatzlos. Meine daraus abgeleitete „Schrittweite in 1/96"-Formel war eine
Extrapolation aus einem Datenpunkt zweifelhafter Herkunft.

**2. Der Block `0x05000xxx` ist nicht der Scaler und gehört nicht der Firmware.** Vollständig
ausgezählt, welche SoC-Register `display.bin` überhaupt anfasst (die MIPS spricht sie über
`readl_checked(arm_phys)` / `writel_masked(arm_phys, …)` mit **ARM-Physadresse** an):

| Zugriff | Register |
|---|---|
| schreibt | `0x05000100`, `0x05000108…0x134` (Tabellenschreiber `sub_8B17D3CC`), `0x05000138`, `0x0500013C` |
| **liest nur** | `0x05000840`, `0x05000844` |

`0x05000174`, `0x224`, `0x844` werden von der Firmware **nie geschrieben**. `doku/89` Punkt 1
(„Die Firmware stellt ihn selbst ein") ist damit unbelegt. Auch kein Stock-ARM-Treiber schreibt
sie: der Stock-Kernel hat überhaupt keinen Display-Treiber (Display ist ganz Sache des MIPS),
und keins der Stock-Module enthält die Adressen.

Nebenbei fällt `sub_8B15DD08` an: es liest `0x05000840/844`, nimmt die **oberen 16 Bit** und
zieht 4 ab — also ist `0x05000844` high die **Breite** (1920), nicht der Pitch, wie `doku/89`
schreibt.

## Der Scaler — gefunden und verifiziert

`ProcWinNode__WriteReg` (0x8B1A6128) schreibt den PROC-Block `0x05140xxx` — denselben Block, in
dem der Chroma-Gain (`0x05140508`) sitzt. Das Feldlayout aus dem Dekompilat:

| Register | low 16 | high 16 |
|---|---|---|
| `0x05140104` | Quelle x | **Quellbreite**, auf gerade aufgerundet |
| `0x05140108` | Quelle y | **Quellhöhe**, auf gerade aufgerundet |
| `0x05140124` | Ziel x | **Zielbreite** |
| `0x05140128` | Ziel y | **Zielhöhe** |
| `0x0514011C` | ENABLE `0x8000` | Quellhöhe (ungerundet) |

Das Aufrunden nur auf der Quellseite passt zum Chroma-Subsampling. **Am Gerät bei 1080p
gegengelesen und exakt bestätigt:** `104 = 0x07800000` (1920), `108 = 0x04380000` (1080),
`124/128` ebenso, `011C = 0x04388002` (ENABLE gesetzt). Quelle = Ziel = 1:1.

## Warum bei 720p nichts skaliert — die Ursache

Bei 720p-Quelle gemessen:

| | Wert | heißt |
|---|---|---|
| INCAP `0x06940874` | `0x050002D0` | **1280×720** — die Aufnahme *wird* umgestellt |
| PROC `0x05140104` | `0x07800000` | **1920** — das Quellfenster des Scalers **nicht** |

Der Scaler bekommt „Quelle 1920×1080 → Ziel 1920×1080 = 1:1", während die Aufnahme 1280×720
liefert. Das Wandbild bestätigt das Muster exakt: Umbruch bei 2/3 der Breite (1280/1920), Inhalt
endet nach 44 % der Höhe (720·1280/1920/1080) — ein Leser mit Zeilenbreite 1920 auf 1280er Daten.

**Und der Schreiber dieses Wertes sind wir selbst.** In `0094-media-sun50i-h713-hdmirx.patch`:

```c
static const u32 window[4] = { 0, H713_HDMIRX_WIDTH, 0, H713_HDMIRX_HEIGHT };
for (i = 0; i < 4; i++) {
        writel(window[i], … H713_WCE_SRC + i * 4);   /* Quelle */
        writel(window[i], … H713_WCE_DST + i * 4);   /* Ziel -- dieselben Werte */
}
```

Quelle **und** Ziel fest 1920×1080, einmal beim Probe. Stock dagegen ruft `Wce_SetWindow` bei
**jedem Quellwechsel** neu (`HANDOFF-HDMI-RX-SESSION-20260501-V`: „12 source-switch calls:
SetSource(3), reapply picture-quality + Wce_SetWindow + DisableBlackScreen").

## Was der naheliegende Fix NICHT tut

`Wce_SetWindow` mit `src = {0,1280,0,720}`, `dst = {0,1920,0,1080}` neu aufgerufen: der Ruf
**gelingt** (`n=1`, 1,4–8,2 ms), die PROC-Register bleiben aber **unverändert** auf 1920×1080.
Sauberer Kontrollversuch: PROC vorher von Hand auf 1920 zurückgesetzt, danach der Ruf, danach
immer noch 1920. Der Ruf legt das Fenster also nur im WCE-Zustand ab; die Register schreibt erst
`UpdateWce`, und das taktet die Zustandsmaschine, die laut
[`re/notes/DEAD-ENDS.md`](../../re/notes/DEAD-ENDS.md) §81 nur per Hardware-IRQ
(`Vdd_TriggerInterruptTop`) läuft und über ~6 Sitzungen nie von außen auszulösen war.

Ebenfalls ohne Wirkung geblieben (jeweils zurückgesetzt): PROC-Register von Hand auf 1280×720,
`0x05000224` auf 1280×720, und beides mit angestoßener Video-Übernahme
(`AFBD_VIDEO_DIRTY`/`VIDEO_READY`). Die Handschreibzugriffe folgen allerdings **nicht** der
Reihenfolge aus `ProcWinNode__WriteReg` — dort werden vor dem Schreiben die Freigabebits
`0x05140114`/`0x05140134` (Bit 31) gelöscht und danach `0x0514011C` Bit 15 gesetzt, dazu zwei
Unterfunktionen (`sub_8B1A5DF0` Mixer, `sub_8B1A604C` Blend). Das ist der nächste Versuch,
nicht ein weiterer Blindschuss.

## Stand

Der Scaler ist **identifiziert, sein Feldlayout verifiziert und die Ursache der fehlenden
Skalierung belegt**. Offen ist allein, wie er programmiert wird: entweder den `UpdateWce`-Takt
doch erreichen, oder die Schreibfolge aus `ProcWinNode__WriteReg` exakt nachbilden. Das
Wandbild bleibt bis dahin bei 720p auf der Konsole (definierter Rückfall, `E6`).
