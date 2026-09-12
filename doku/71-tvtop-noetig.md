# Braucht der ARM `tvtop`? — Nein, der MIPS setzt die HDMI-RX-Seite selbst auf

Stand 05.09.2026. Diese Datei beantwortet die offene Frage aus
[69-handoff-20260905.md](69-handoff-20260905.md), Abschnitt „Woran ich zuletzt
saß": *braucht der ARM den `tvtop`-Treiber überhaupt, oder macht der MIPS die
HDMI-RX-Seite allein?* Alles hier ist am laufenden Board (`root@192.168.8.141`,
MIPS läuft, `0x0306101c = 1`) oder statisch am Stock-`display.bin`
(md5 `0d2191ca`) belegt.

## Antwort zuerst

**Der MIPS setzt die HDMI-RX-Aufnahmeseite selbst auf. Der ARM braucht den
`tvtop`-Treiber für den Eingangspfad nicht.** Die zwei Dinge, die `tvtop`
beitragen würde, liegen bereits woanders vor:

1. **TV-Energiebereiche + Takte** — an, aus U-Boot. `pd_tvfe` (`0x07001080`) und
   `pd_tvcap` (`0x07001100`) lesen am Board **`1`**; `pm_genpd_summary` zeigt
   TVFE/TVCAP „on". Das minimale `h713-tvcap`-Modul beansprucht sie namentlich
   und gibt 4 Takte frei; und schon `pd_ignore_unused` in den bootargs hält sie
   an. **Der MIPS programmiert die PPU nie** (Messung unten).
2. **TVTOP-Fabric-Routing (`0x05700000`, 7 Register)** — macht **U-Boot**
   (`h713_display_prepare`, `H713_DISPLAY_TOP_REG = 0x05700000`) bei jedem Start
   über die persistente `bootcmd` `h713_disp init 0x30`. Am Board jetzt live und
   Wort für Wort die 1080p-Sollwerte (Messung unten). `tvtop_tvdisp_enable`
   schriebe exakt dieselben 7 Werte — reine Dopplung.
3. **INCAP-Aufnahme (Power + Konfiguration)** — **MIPS-eigen.** Am Board läuft
   INCAP ohne jeden `tvtop`: Y-Ziel `0x06940900 = 0x04c7ed00` (`<<4` =
   `0x4c7ed000`), C-Ziele `0x930`/`0x938` gefüllt, `0x06940000 = 0x00003a7b`
   (**nicht** die nackte `1`, die `tvtop_tvcap_enable` schreibt). Der MIPS hat
   das getan, kein ARM-Treiber.

## Die Messung — und was sie sehen könnte

Verfahren: lui-Scan über das Stock-`display.bin` (MIPS BE, im File
little-endian abgelegt; MMIO-Basis `VA = phys + 0xB5000000`). **Positivkontrollen
feuern**, das Verfahren kann also einen Treffer sehen:

| Block | phys | erwartete lui | Treffer |
|---|---|---|---|
| DE2 | `0x05000000` | `0xBA00` | **45** |
| AFBD | `0x05600000` | `0xBA60` | **29** |
| Synopsys HDMI-RX | `0x050C0000` | `0xBA0C` | **22** |
| **INCAP** | `0x06940000` | `0xBB94` | **21** |
| CCU | `0x02001000` | `0xB700` | **1** |
| **PPU (Domains)** | `0x07001000` | `0xBC00` | **0** |
| TVTOP-Fabric | `0x05700000` | `0xBA70` | **0** |
| TVTOP-A | `0x068B0000` | `0xBB8B` | **0** |
| tvcap-top | `0x06700000`/`0x06e00000` | `0xBB70`/`0xBBE0` | **0** |

Der eine CCU-Treffer ist `lui r4, 0xb700; lw/sw 0x190c(r4)` — genau ein
Register, `0x0200190c` (liest am Board `0x00130013`). Der MIPS fasst die CCU
also praktisch nicht an, und **die PPU-Energiebereiche gar nicht** — das deckt
sich mit „alle Domains an aus U-Boot".

Gegenprobe, dass INCAP wirklich MIPS-eigen ist —
`VIncap_EnableCaptureOutput` (`0x8b19f7e8`):

```
0x8b19f7e8  3c02bb94  lui   r2, 0xbb94        r2 = 0xBB940000  (= phys 0x06940000)
0x8b19f7ec  8c430928  lw    r3, 0x928(r2)
0x8b19f7f4  7c83ffc4  (bit-set)               bit31
0x8b19f7f8  ac430928  sw    r3, 0x928(r2)     INCAP +0x928 |= bit31
0x8b19f7fc  8c430968  lw    r3, 0x968(r2)
0x8b19f804  ac430968  sw    r3, 0x968(r2)     INCAP +0x968 |= bit31
```

Direkter `lui`-Zugriff auf INCAP — der MIPS schaltet die Aufnahme selbst scharf.

### Die Grenze der Messung (ehrlich)

**0 lui-Treffer auf TVTOP-A (`0x068B0000`) beweisen nicht, dass der MIPS ihn
ignoriert.** `memory_agent_update_onoff` (`0x8b153140`) schreibt die
TVTOP-A-Register laut `re/notes/CURRENT-TRUTH.md` — aber **über eine vtable**,
nicht per `lui`:

```
0x8b15321c  8c420030  lw    r2, 0x30(r2)      Handler aus Struktur+0x30
0x8b153220  0040f809  jalr  r2                indirekt gerufen
```

Base+Offset über einen Strukturzeiger sieht ein lui-Scan nicht. **Schluss:**
TVTOP-A wird MIPS-seitig, aber über Zeiger bedient; der **ARM** schreibt ihn nie
(er steht ohnehin auf der harten Sperrliste — Lesen von `0x068B0000` vom ARM
wedgt den SoC). Die Aufnahme-Blöcke INCAP/DE2 dagegen werden direkt adressiert
und sind eindeutig MIPS-eigen.

## Das Fabric-Routing kommt aus U-Boot — am Board belegt

`0x05700000` live gelesen (nicht auf der Sperrliste, U-Boot schreibt es, die
Display-Sub-Blöcke werden darüber routiniert erreicht):

```
+0x00 = 0xfff11111   +0x40 = 0x00011111   +0x80 = 0x00001111
+0x04 = 0x00000001   +0x44 = 0x11111111   +0x84 = 0xfff000ef
                                            +0x88 = 0x11111111
```

Das ist **Wort für Wort** die 1080p-Tabelle aus `h713_display_prepare`
(`H713_DISPLAY_TOP_REG + 0x00/04/40/44/80/84/88`). `tvtop_tvdisp_enable` und
`sunxi_tvtop_data.c` tragen exakt dieselben sieben Werte. In Linux macht das
niemand neu — es steht aus U-Boot und bleibt stehen.

## Entscheidung: `CONFIG_SUNXI_TVTOP` nicht einschalten

Für den HDMI-**Eingangspfad** ist `tvtop` überflüssig: Power/Takt und
Fabric-Routing sind schon da, die Aufnahme-Engine gehört dem MIPS. Dazu die zwei
bekannten Riegel aus dem Handoff, jeder für sich hinreichend:

* Der Baum trägt die **`Archived/`-Fassung** mit `clk_set_rate` — dem
  dokumentierten SoC-Freeze (`legacy`-Commit `a4d1a65`, KNOW-20260413).
* Der Vendor-DT-Knoten trägt **`GIC_SPI 110`** (= AFBDs Interrupt, 615
  Auslösungen gemessen) und **`panel_bl_en = PB5`** (Hintergrundbeleuchtung +
  Lüfter). Beides würde beim Scharfmachen mitgerissen.

Und ein dritter, neu gefundener Riegel: **die `reg`-Reihenfolge des
`tvtop`-Knotens ist bei uns gegenüber dem Vendor vertauscht.**

| | Eintrag 0 | Eintrag 1 (`iomap_idx 1` = **tvcap**) | Eintrag 2 (`iomap_idx 2` = **tvfe**) |
|---|---|---|---|
| Vendor-DT (`analyse/arisc/dtb.bin`, `tvtop@5700000`) | `0x05700000` | **`0x06e00000`** | **`0x06700000`** |
| unser Baum (Patch 0024, ebenso `legacy/dts/…hy310.dts`) | `0x05700000` | **`0x06700000`** | **`0x06e00000`** |

Der Patch-Kommentar nennt sogar die richtige Stock-Reihenfolge
(„Stock registers: 0x05700000, 0x06e00000, 0x06700000") und listet sie darunter
falsch. `sunxi_tvtop_data.c` bindet `tvcap` fest an Index 1. Mit unserem Knoten
schriebe `tvtop_tvcap_enable` seine Magic-Sequenz in **`0x06700000`** — den
Demod-Block (`dtmb@6600000` hat ihn als zweiten `reg`), der am Board null liest —
und `tvtop_tvfe_enable` sein `0x003003FF` nach `0x06e00000`. Wer `tvtop` je
scharfmacht, muss zuerst die zwei Einträge tauschen.

`tvtop`s **Takt-Raten-Verwaltung** (die `legacy`-Fassung plus der
`pll-video2 = 258 MHz`-Fix) ist erst für die **Farb-Phase** interessant — der
VProc läuft heute auf Boot-Default-Raten (`re/notes/…ROOT-CAUSE-tvtop-clk-rate`).
Das gehört **nicht** in die Frage, ob eine Quelle das Board sieht.

## Was ich NICHT gezeigt habe

* **Kein Signal gesehen.** (Korrektur 06.09.: am Projektor hängt permanent
  eine Quelle; „keine Quelle" war meine Annahme.) Dass INCAP läuft, heißt nur:
  der MIPS ist bereit, nicht dass ein Signal verarbeitet wird. `0x06940928/968` lesen aktuell `0x600200f0` —
  Bit 31 (Capture-Output-Enable) **nicht** gesetzt, passend zu „noch kein
  Signal".
* **Den MIPS-Schreiber von TVTOP-A (`0x068B0000`) nicht zu Ende verfolgt** — nur
  belegt, dass er indirekt/zeigerbasiert ist (also per lui-Scan nicht
  widerlegbar) und vom ARM verboten. `0x068B0000` habe ich vom Board **nicht**
  gelesen (absolute Sperre).
* **`0x06e00000` ist unerklärt.** Es liest am Board routing-artige Werte
  (`+0 = 0x00111111`, `+4 = 0x01111117`, `+8 = 0x00000504`), gehört zu einem der
  drei `tvtop`-reg-Bereiche (Vendor-DT: `0x05700000`, `0x06e00000`, `0x06700000`;
  `0x06700000` liest null). Wer die Werte schrieb, ist offen: nicht U-Boots
  `TOP_REG` (= `0x05700000`), nicht unser Modul, nicht der MIPS per `lui`.
  Kandidat: MIPS per Zeiger, oder ein persistenter Wert. Nicht entschieden.

## Belege am Stück

| Behauptung | Beleg |
|---|---|
| PPU-Domains an aus U-Boot | Board: `0x07001080 = 1`, `0x07001100 = 1`; `pm_genpd_summary` TVFE/TVCAP „on" |
| MIPS fasst PPU nicht an | `display.bin` lui `0xBC00`: 0 Treffer (Positivkontrollen DE2/AFBD/INCAP feuern) |
| Fabric aus U-Boot | Board `0x05700000` = 1080p-Tabelle; `h713_mips.c:141` `TOP_REG=0x05700000`, `h713_display_prepare` schreibt die 7 Werte |
| INCAP MIPS-eigen | `VIncap_EnableCaptureOutput 0x8b19f7e8` (`lui 0xBB94`); Board `0x06940900 = 0x04c7ed00` |
| Aufnahme läuft, kein Signal | Board `0x06940928/968 = 0x600200f0` (Bit 31 aus) |
| tvtop im Baum = Archived-Freeze | [69-handoff](69-handoff-20260905.md); `legacy`-Commit `a4d1a65` |

Werkzeuge am Board: `/root/incap_read.py`, `/root/fabric_read.py` (beide rein
lesend, wortweise, mit `/dev/kmsg`-Markern vor jedem Zugriff).
