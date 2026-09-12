# AFBD: die Kanäle, das Latch-Orakel, und der Beweis bis zum Panel

Stand 01.09.2026, nachts. Alles am Gerät gemessen (`192.168.8.142`), mit
laufendem MIPS. Die Registerdeutungen sind aus `ge2d_dev.ko` disassembliert,
nicht geraten.

## 0. Das Wichtigste zuerst

**Unser DRAM erreicht das Panel.** Das ist heute Nacht bewiesen worden, und es
beendet die fünf Monate alte Erzählung von der „MIPS-Wand". Was fehlt, ist ein
Kanal, der planares NV12 liest — kein Tor, das jemand aufmachen müsste.

**Und es gibt ein Messgerät:** das Latch-Bit eines Kanals unterscheidet
„konfiguriert" von „bedient". Das beantwortet wörtlich cstengers offene Frage
(*„What gates a scanout channel being serviced as distinct from configured?"*)
— jedenfalls als Messverfahren.

## 1. Die Kanäle (aus dem Treiber, nicht geraten)

`__afbd_is_ch_en` (@0x11130) vergleicht seine ID gegen 0, 1 **und** 2. Der
id-0-Zweig lädt die Adresse zusammen:

```
mov  r1, #16          ; r1 = 0x00000010
movt r1, #0x560       ; r1 = 0x05600010
ands r0, r0, #3       ; Enable = Bits [1:0]
```

`__afbd_get_pixel_fmt` (@0x11288) holt aus demselben Wort `ubfx r0, r0, #8, #8`
= Format in Bits [15:8]. Daraus die Kanalstruktur, deckungsgleich mit der
vollständigen Registerliste, die der Treiber überhaupt anfasst:

| ID | ctrl | latch | Geometrie | extra | Rolle |
|---|---|---|---|---|---|
| **0** | `0x05600010` | `0x05600014` | `0x05600030` | `0x05600038` | **Video, planar** |
| 1 | `0x05600100` | `0x05600104` | `0x05600128` | `0x0560012c` | OSD |
| 2 | `0x05600140` | `0x05600144` | `0x05600168` | `0x0560016c` | OSD |

`OSD_AFBD_REG_OFFSET` (.rodata +0x280) = `0x05600100, 0x05600140` ist die
Tabelle der beiden **OSD**-Kanäle, nicht die Kanalliste. Wer daraus „es gibt
nur zwei Kanäle" schließt, liegt falsch — dieser Fehler wurde heute Nacht
einmal gemacht und wieder eingefangen.

Der Treiber fasst **pool-1** (`0x70`–`0xa4`), **pool-2** (`0x300`–`0x33c`),
den Commit (`0x6c`) und `0xc4` **nicht** an. Die gehören dem MIPS.

## 2. Das Latch-Orakel

Setzt man Bit 0 des Latch-Registers eines Kanals und liest sofort zurück:

- **gelöscht** → die Hardware hat es abgeholt: der Kanal wird **bedient**
- **steht noch** → niemand holt es ab: der Kanal ist tot, egal was in `ctrl` steht

Gemessen, reproduzierbar:

| Kanal | Latch | Ergebnis |
|---|---|---|
| 0 | `0x014` | **verbraucht** |
| 1 | `0x104` | **bleibt stehen** |
| 2 | `0x144` | **verbraucht** |

Im Stock-Dump steht `0x05600104 = 0` — dort wird ch1 also bedient. Bei uns
nicht, und zwar **auch dann nicht, wenn alle ch1-Register auf Stock stehen**
(`0x100=0x83001901`, `0x108=0x008000ff`, `0x10c=0x00ff0080`, `0x12c=0x21`),
die Engine an ist (`0xc4=1`) und der IRQ quittiert (`0xc0=0`). Das Tor für
ch1 liegt damit nachweislich **außerhalb der AFBD-Seite**.

Das Orakel braucht keinen Blick an die Wand, arbeitet pro Kanal und ist
unabhängig vom Bildinhalt. Es ist das erste belastbare Messmittel in diesem
Teil des Projekts.

## 3. Der Beweis: unser Speicher steht auf dem Panel

ch2 wird bedient und zeigt die Konsole. Zeigt man ihn auf einen unserer
gefüllten Ring-Slots und lässt den Inhalt zwischen `0xFF` und `0x00` blinken,
blinkt die Wand mit — in einem Muster, das sich vorher ausrechnen lässt.

ch2 liest mit Stride 7680 Byte/Zeile ab `0x4c7ed000`:

| Bereich | Bytes | Zeilen | erwartet | beobachtet |
|---|---|---|---|---|
| unsere Y-Ebene | 2.073.600 | 0 – 270 | blinkt | **blinkt** |
| unbeschrieben | 4.205.568 | 270 – 818 | schwarz | **schwarzer Balken** |
| unsere C-Ebene | 1.036.800 | 818 – 953 | blinkt | **blinkt** |
| Rest | — | 953 – 1080 | dunkel | dunkel |

Die Geometrie stimmt zeilengenau mit dem physischen Speicherlayout überein.
**Damit ist die Kette DRAM → Kanal → Blender → TCON → Panel lückenlos belegt.**

## 4. Der Ring: füllen, nicht umbiegen

Der Scanout liest einen festen Dreier-Ring, den der MIPS selbst rotiert:

```
Y:  0x4c3ef000   0x4c5ee000   0x4c7ed000     (Abstand 0x1FF000)
C:  0x4c9ec000   0x4cbeb000   0x4cdea000     (Y+0x5FD000)
```

`0x05600320`/`0x324` zeigen auf den aktuellen Slot. **Sie sind kein
Konfigurationsziel:** Pin-Versuche überschreibt der MIPS in Echtzeit
(Juni-Befund, heute bestätigt — auch `0x30c`/`0x310` halten geschriebene
Werte nicht und wandern selbsttätig weiter; wer sie diffed, misst ein
bewegliches Ziel, nicht eine Abweichung).

Ohne Quelle **rotiert der Ring nicht**, er parkt (20 Proben über 2 s: ein
einziges Slot-Paar). Das macht es für uns einfacher, nicht schwerer.

## 5. pool-1 enthält Offsets, keine Adressen

Stock, mit laufendem Video:

```
0x05600078: 0x00800000     Y
0x05600084: 0x009fa400     C      Differenz 0x1FA400 = 2.073.600 = eine Y-Ebene
```

`0x00800000` kann keine physische Adresse sein — DRAM beginnt auf diesem SoC
bei `0x40000000`. Es sind **Offsets auf eine Basis**, und C liegt genau eine
Y-Ebene hinter Y. In der Nacht des 31.08. wurden dort absolute Adressen
eingetragen; die Fetch-Engine armierte daraufhin (Zähler `0x58`/`0x5c` von 0
auf Stock-Niveau), las aber ins Leere. Die Basis ist noch nicht gefunden.

## 6. Stock-Referenz der Kanäle (Video läuft)

```
0x05600010: 0x03000013    ch0  Format 0x00 = planar, Enable = 3
0x05600030: 0x04380780    ch0  1920 x 1080
0x05600100: 0x83001901    ch1  Bit31, Format 0x19, aktiv   <- der Scanout
0x05600140: 0x83001900    ch2  Bit31, Format 0x19, Enable = 0 (aus)
```

Bit 31 auf ch1/ch2 = „nimm die Page-Flip-Zeiger `0x320`/`0x324`" statt der
kanaleigenen Adresse. **Format `0x00` ist der planare Videocode.** ch0 steht
bei uns bereits bit-identisch zu Stock.

Ein Diff der ganzen Seite gegen `stock-0x5600000-post.txt` ergibt aktuell noch
35 Abweichungen; nach Abzug der MIPS-Laufwerte (`0x30c`, `0x310`, `0xb8`,
`0xbc`) und unserer eigenen Puffer-Adressen bleiben keine offenen
Konfigurationsunterschiede mehr.

## 7. Widerlegt

- **`0x05600058`/`0x0560005c` sind kein Datenfluss-Indikator.** Weder inhalts-
  noch geometrieabhängig (Videoframe vs. leerer Speicher: `0x66`/`0x48` gegen
  `0x66`/`0x49`; halbe Breite: unverändert). Sie zeigen „Engine armiert", mehr
  nicht. Die Einstufung *„≠0 ⟺ die Engine hat Frames verarbeitet"* ist falsch.
- **`0x310` Bit 21 ist kein Fortschrittsmass** — siehe §4, das Register wandert
  von selbst. Im Stock ist das Bit übrigens **gesetzt**, nicht gelöscht.
- **Formatcode `0x01` ist nicht „1 Byte/Pixel".** Am Gerät geprüft: die
  Darstellung bleibt bei 4 Byte/Pixel. Die Tabelle „alles außerhalb
  {0x17,0x18,0x19,0x1a,0x1b,0x1d} ist 1 Byte/px" trägt nicht.
- **Kanal-0-Enable von Hand setzen bringt nichts.** `0x05600010 = 0x03000013`
  ist im Stock die **Folge** des memory_agent-Enables, nicht dessen Auslöser.

## 8. Wo es weitergeht

Die Frage ist nicht mehr „wie kommen Pixel aufs Panel" (§3), sondern:

1. **Die pool-1-Basis finden** (§5). Damit läge der planare Kanal 0 — der
   bedient wird — auf unseren Puffern. Das ist der direkteste Weg.
2. **Was bedient ch1?** Liegt außerhalb der AFBD-Seite (§2). Kandidaten:
   die Modul-Enables, die der MIPS-`memory_agent` über AFBD/DE/TVTOP/INCAP
   schreibt (`memory_agent_update_onoff`, MIPS `0x8b153140`).
3. **Den elog scharfstellen — aber NICHT mit `elog=3`.** Laut
   [66-cpu-comm-arm64-bringup.md](66-cpu-comm-arm64-bringup.md) verhindert
   `elog=3` die MIPS-Bereitschaft (dreimal belegt, in beide Richtungen:
   `MIPS=00000000`, Teardown, schwarzer Schirm). Nicht in `bootcmd` speichern.
   **Ringadresse:** aktiv ist **Mode 1**, phys `0x4B272D9C`, 102400 Bytes,
   Write-Ofs `0x4B48C2A8`, Read-Ofs `0x4B48C2A4`. Die Adresse `0x4B28BD9C` aus
   `mips_elog2.py` ist der **inaktive Mode-2-Puffer** — wer sie nimmt, liest
   ins Leere. Werkzeug `/root/mipslog state|dump|tail`.

**Der Commit ist inzwischen firmware-seitig aufgelöst** —
[../analyse/REPORT-ch0-wce-chain.md](../analyse/REPORT-ch0-wce-chain.md):
`0x0560006C` Bit 0 setzt allein `NRWinNode_AfbdConfigure` (`0x8b1a3c58`),
erreichbar nur über `WindowManager::Refresh → UpdateWce → SetWindow →
StepWceSTM(wce,1)`. Sie schreibt das Quartett `0x05600010` Bit31, `+0x14 |= 1`,
`+0x60 |= 1`, `+0x6C |= 1` — also genau das, was §2 als „bedient" misst.
Primärer Verdacht dort: `UpdateWce` bricht an `CalcPropRect` /
`CalcSignalActiveWin` ab, weil unser Deskriptor die Fenster-/Geometriefelder
nicht füllt. **Offen und ungeklärt:** wer dann ch0s Latch `0x014` verbraucht,
wenn die Kette `AfbdConfigure` nie erreicht (`0x6c` bleibt 0). Entweder holt
die Hardware das Bit unabhängig ab, oder das Orakel misst etwas Feineres als
gedacht. Das gehört als erstes geprüft.

Nicht noch einmal versuchen: pool-2 umbiegen (§4), `0x58/0x5c` als Orakel (§7),
Formatcodes einzeln am Bildschirm durchprobieren (§7 — dafür gibt es §2).

## 9. Panelgeometrie — nicht aus dem Stock-Diff übernehmen

`hy310-format-test.py` listet Stock-gegen-mainline-Differenzen in DE und Mixer.
**Die meisten davon sind Board Bs Panelgeometrie**, nicht funktionale
Unterschiede:

```
0x0528008c   Stock 0x73 (115)   wir 0x37 (55)    X-Ursprung: 55 ist UNSERER
0x05280088   Stock 0x11 (17)    wir 0x19 (25)    Y-Ursprung: 25 ist UNSERER
```

U-Boot setzt `0x0528008c` beim Start ausdrücklich von `0x73` auf `0x37`. Wer
hier „auf Stock" zieht, verschiebt das Bild auf Board Bs Panel.
