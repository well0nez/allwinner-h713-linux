# S3 — Der Scaler: Register gefunden, Formel hergeleitet, bitgenau gegengeprüft

07.09.2026, 20:40–22:15 · idalib + Board · Fortsetzung von [`S1`](S1-scaler-gefunden.md)/[`S2`](S2-scaler-anwenden-versuche.md)

## Die Register

`sub_8B1A5DF0` (aus `ProcWinNode__WriteReg`) schreibt den Block `0x05180000`. Dort steht die
Skalierung — **nicht** in den Fensterregistern, wie `S1` noch annahm, und **nicht** bei
`0x05000174`, wie `doku/89` nahelegte:

| Register | Bedeutung |
|---|---|
| `0x05180008` [21:0] | waagerechtes Verhältnis, 16.16-Festkomma |
| `0x05180008` [30:28] | Modusfeld waagerecht |
| `0x05180008` [26:24] | Modusfeld senkrecht |
| `0x0518003C` [21:0] | senkrechtes Verhältnis |
| `0x05180014` Bit 27 | „keine Skalierung" — gesetzt, wenn beide Verhältnisse genau 1:1 |
| `0x05180000` [15:0] | Anfangsphase waagerecht |
| `0x05180038` [15:0] | Anfangsphase senkrecht |

## Die Formel

`sub_8B1A56B8` heißt im elog `CalcScaleRatio`:

```c
*a5 = (in_w < out_w);            /* Richtung waagerecht */
*a6 = (in_h < out_h);            /* Richtung senkrecht  */
ratio_h = in_w < out_w ? (in_w<<16)/out_w : (out_w<<16)/in_w;   /* stets klein/gross */
ratio_v = in_h < out_h ? (in_h<<16)/out_h : (out_h<<16)/in_h;
```

Das Verhältnis ist also **immer ≤ 0x10000**; die Richtung steckt in den Flags. Dazu aus
`ProcWinNode__CalcWindow` die Modus- und Phasenfelder:

```c
mode_h = 3; mode_v = 2;
phase_h = (ratio_h + 0x10000) >> 2;
phase_v = (ratio_v + 0x10000) >> 1;
if (phase_h >= 0x8000)  { mode_h++; if (phase_h >= 0x10000) phase_h = 0; }
if (phase_v >= 0x10000) { mode_v++; phase_v = 0; }
```

Und `sub_8B1A58B0` (`ReCalcInOutWin`) rundet die Zielbreite auf gerade und rechnet die Quellbreite
aus Zielbreite und Verhältnis zurück:

```c
out_w += out_w % 2;
in_w = upscale ? (out_w * ratio + 0xFFFF) / 0x10000
                : ((out_w << 16) + ratio - 1) / ratio;
```

## Gegenprobe: bitgenau

Die Formel auf den **laufenden 1080p-Zustand** angewandt und mit den tatsächlich am Gerät
gelesenen Werten verglichen:

| | gerechnet | am Gerät gelesen |
|---|---|---|
| `0x05180008` | `0x43010000` | `0x43010000` ✓ |
| `0x0518003C` | `0x00010000` | `0x00010000` ✓ |
| `0x05180014` Bit 27 | 1 | 1 ✓ |
| Phase waagerecht | `0x8000` | `0x05180000` = `0x0F00`**`8000`** ✓ |
| Phase senkrecht | `0x0000` | `0x05180038` = `0x0010`**`0000`** ✓ |

Fünf von fünf, einschließlich der beiden Modusfelder (4 und 3), die sich aus den `++`-Zweigen
ergeben. **Damit ist die Herleitung verifiziert.**

Für 1280×720 → 1920×1080 folgt: Verhältnis `0xAAAA` waagerecht wie senkrecht, Modus 3/2, also
`0x05180008 = 0x3200AAAA`, `0x0518003C = 0x0000AAAA`, Bit 27 = 0, Phasen `0x6AAA`/`0xD555`.

## Am Gerät geschrieben: der Scaler reagiert

Mit `0xAAAA` und gelöschtem Bit 27 wurde das Bild **sichtbar vergrößert**; zurück auf `0x10000`
verschwand die Vergrößerung wieder. Die Register sind also von uns beschreibbar und wirksam.

**Das Bild wird davon aber noch nicht richtig.** Es fehlen die begleitenden Fenster- und
Randregister, die `ProcWinNode__WriteReg` im selben Durchgang schreibt: die PROC-Fenster
(`0x05140104/0108/0124/0128/011C`) mitsamt ihren Gates, und der Satz aus `sub_8B1A604C`
(`0x05140514/518/524/528/148/14C/160/164`), den ich **noch nicht gelesen und nie geschrieben
habe**. Einzelne Register zu setzen ersetzt die Folge nicht.

## Ein Messfehler, der die Bildbewertung entwertet hat

Marco hat ihn gefunden: der Zuspieler stand die ganze Zeit auf einem **X-Schirm von 1920×1080**
(interner Schirm `eDP-1`), während `HDMI-2` mit 1280×720 auf Position +0+0 nur den linken oberen
Ausschnitt zeigte. Der „doppelte Inhalt rechts" in meinen Fotos war also teilweise die Quelle
selbst. Behoben durch `xrandr --output eDP-1 --mode 1280x720 --output HDMI-2 --mode 1280x720
--same-as eDP-1` — X-Schirm exakt 1280×720, gespiegelt.

Mit sauberer Quelle nachgemessen: **der Umbruch bleibt**, die Diagnose aus `S2` steht also. Aber
jede Bildbewertung davor ist unzuverlässig, und die Lehre gilt allgemein — **vor jeder
Bildbeurteilung die Quelle prüfen**, nicht nur den gemeldeten Modus.

## Die Folge ist vollständig — und reicht trotzdem nicht

`sub_8B1A604C` nachgelesen: es schreibt `0x05140514/518/524/528/148/14C/160/164` aus einem
u16-Feld `{x0, _, x1, _, y0, _, y1, _}` bei `a1+92`. Gegengelesen am Gerät:
`0x0514014C = 0x00000780` → x0 = 0, x1 = 1920; `0x05140148 = 0x00000438` → y0 = 0, y1 = 1080.
Das ist das **Ausgabefenster** und bleibt bei Panelgröße — für einen Quellwechsel also nichts zu
tun. Damit war die Schreibfolge vollständig bekannt.

Sie wurde in einem Durchgang gesetzt (Gates gelöscht, PROC-Quellfenster `0x05140104/0108` auf
1280×720, Zielfenster auf 1920×1080, Verhältnisse und Phasen hergeleitet, `0x0514011C` mit
Freigabe) — **das Bild blieb falsch**, derselbe Umbruch.

Damit ist auch der letzte aus dem Disassemblat ableitbare Versuch aus dem Userspace gescheitert.
Bemerkenswert bleibt der Widerspruch: `0x05180008` **wirkt sofort** (die Vergrößerung war
sichtbar), die PROC-Fensterregister dagegen bewirken nichts — auch nicht das Zielfenster bei
1080p, wo ein 960×540-Wert das Bild hätte vierteln müssen. Das spricht dafür, dass die
PROC-Fensterstufe in unserer Kette **umgangen** ist und die Eingangsgeometrie des aktiven
Scalers (`0x05180000`-Block) aus einer Quelle kommt, die ich noch nicht gefunden habe.

## Nächster Schritt

Die offene Frage ist jetzt eng: **woher nimmt der aktive Scaler bei `0x05180000` seine
Eingangsgeometrie?** Alle Schreiber dieses Blocks in `display.bin` sind bekannt (`sub_8B1A5DF0`);
die Felder `a1+64/72/80/88` tragen dort die Panelmaße. Zu klären ist, welches Register die
*Eingangs*breite trägt — Kandidaten aus dem Abzug: `0x05180050` (`0x001E0438`), `0x0518002C`
(`0x006C0780`), `0x05180044` (`0x68`). Erst mit dieser Antwort ergibt ein Treiberpatch Sinn.
Kein weiteres devmem-Probieren: es hat die Firmware zweimal hängen lassen (leerer Signalsatz,
RPCs von <10 ms auf 537 ms; nur ein Netboot-Neustart half).

Gerät steht am Ende sauber auf 1080p mit Bild und `0 ohne Antwort`.
