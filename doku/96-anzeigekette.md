# Die Anzeigekette des H713 - wie sie wirklich funktioniert

Stand 08.09.2026. Zusammenfassung dessen, was in der Sitzung vom 07.09. gemessen, reversed und am
Gerät bestätigt wurde. Ersetzt keine der Detaildokumente, sondern verbindet sie:
[`63`](63-mips-elog.md) elog · [`76`](76-plan-ch0-de.md) DE-Kette · [`86`](86-video-plane-nv16.md)
Video-Plane · [`89`](89-composition-block.md) Composition · [`98`](98-mips-shell.md) Firmware-Shell.

---

## 1. Wer besitzt was

Der SoC hat zwei Rechner für die Anzeige:

- **ARM** (unser Linux) besitzt den **AFBD** bei `0x05600000` - er füttert die Video-Plane aus dem
  Capture-Ring und schreibt den VidDec-Descriptor.
- **MIPS** (`display.bin`) besitzt **alles dahinter**: Aufnahme (INCAP `0x06940000`), die
  Fensterkette, den Scaler und die Panelausgabe. Er programmiert diese Register **selbst**, sobald
  er einen Grund dazu sieht.

Der ARM kann diese Register lesen und sogar beschreiben - aber ohne die firmware-eigene Neuberechnung
bleibt das wirkungslos oder schädlich. **Am Gerät belegt:** ein PROC-Zielfenster von 960×540 bei
1080p ändert am Bild nichts, und der Scaler-Handreset nach einem Firmware-Neubau holt das
Doppelbild nicht zurück. Der einzige Weg, der wirkt, ist die Firmware dazu zu bringen, neu zu rechnen.

---

## 2. Die Registerblöcke

| Block | Adresse | Eigentümer | Inhalt |
|---|---|---|---|
| AFBD | `0x05600000` | **ARM** | Video-Plane, Stride, Crop, Flip-Zeiger, **VidDec-Descriptor-Zeiger** `+0x098…0A4` |
| Composition / NR | `0x05000000` | MIPS | NRWinNode; Fenster und Pitch |
| PROC | `0x05140000` | MIPS | ProcWinNode: Quell-/Zielfenster, Chroma-Gain `+0x508` |
| Scaler | `0x05180000` | MIPS | **Skalierverhältnisse und Phasen** |
| Panel | `0x051C0000` | MIPS | PanelWinNode, Selektor `+0x06C` |
| INCAP | `0x06940000` | MIPS | Aufnahme: aktive Geometrie, Totale, rowbyte, Freigabe |

### Der Scaler im Einzelnen

| Register | Bedeutung |
|---|---|
| `0x05180008` [21:0] | waagerechtes Verhältnis, **16.16-Festkomma** |
| `0x05180008` [30:28] / [26:24] | Modusfelder waagerecht / senkrecht |
| `0x0518003C` [21:0] | senkrechtes Verhältnis |
| `0x05180014` Bit 27 | „keine Skalierung", gesetzt wenn beide genau `0x10000` |
| `0x05180000` / `0x05180038` [15:0] | Anfangsphasen |

Die Firmware rechnet sie in `CalcScaleRatio` (`sub_8B1A56B8`), im elog als solche benannt:

```c
ratio = in < out ? (in << 16) / out : (out << 16) / in;   /* stets klein/gross */
mode_h = 3; mode_v = 2;
phase_h = (ratio_h + 0x10000) >> 2;
phase_v = (ratio_v + 0x10000) >> 1;
if (phase_h >= 0x8000)  { mode_h++; if (phase_h >= 0x10000) phase_h = 0; }
if (phase_v >= 0x10000) { mode_v++; phase_v = 0; }
```

Dreifach bestätigt: gegen den gelesenen 1:1-Zustand (`0x43010000`), gegen Stock-Zahlen aus dem elog
(720×480 → 1920×1080 ergibt `ratio [24576 x 29127]`), und gegen die Firmware selbst, die bei
1280×720 → 1920×1080 `ratio [43690 x 43690]` = `0xAAAA` rechnet - genau der vorhergesagte Wert.

### INCAP, gemessen

| Register | 1920×1080 | 1280×720 (korrekter Neubau) |
|---|---|---|
| `0x06940874` aktiv | `0x07800438` | `0x050002D0` |
| `0x06940548` total | `0x04650898` (1125×2200) | `0x02EE0672` (750×1650) |
| `0x06940924` rowbyte | `0x78` = 120 | `0x50` = 80 |
| `0x06940928` | `0xE0020438`, Bit 31 = Freigabe | `0xE00202D0` |

`rowbyte = Breite / 16`. **`0x06940928` Bit 31 ist die Aufnahmefreigabe** - ist sie gelöscht, zählt
`+0x104` weiter, aber es wird nichts geschrieben: die Wand zeigt einen Standrahmen.

---

## 3. Der VidDec-Descriptor - die Signalquelle der Firmware

144 Byte, vom ARM geschrieben, Zeiger in `0x05600098…0A4` (vier Slots). Inhalt (Wortindex):

| Wort | Wert | Bedeutung |
|---|---|---|
| 0 | `0x61770000` | Magic; die Firmware prüft ihn |
| 1 | `2` | Typ: Videodecoder-Rahmen |
| 2-5 | `w, h, w, h` | Quell- und Zielgröße |
| 6-9 | `0, h, 0, w` | Fenster |
| 13/14 | `30000` | Bildrate |
| 22 | stride | |
| 28/30/32/34 | `w*16, h*16, w*16, h*16` | Fenster in 1/16 Pixel |

**Er ist nicht bloß unsere Eingabe für den AFBD, sondern die Signalquelle der Firmware.**
`GetFrameInfo` folgt dem Zeiger, `ConvertFrameInfo2SignalInfo` prüft das Magic und baut daraus die
Signal-Info. **Jede Änderung ist ein Signalereignis** und löst den Fensterneubau aus.

Der Signaldetektor führt zwei Kopien: eine Arbeitskopie bei `+0xb0` und einen Latch bei `+0x140`
(Objekt über den Singleton bei ARM `0x4b27266c` → Instanz → `+0x5a8`). Sind beide gleich, schließt
die Firmware „nichts geändert" und tut nichts.

**Das war die Ursache des Scaler-Problems:** unser Treiber schrieb den Descriptor nur **einmal pro
Boot**, also blieb die Geometrie des ersten Enable stehen, beide Kopien waren gleich, und die
Firmware baute nie neu.

---

## 4. Der Neubau: was tatsächlich passiert

Die Kette bei einem Signalereignis, aus dem elog auf Stufe 5 mitgeschnitten:

```
SetSignalInfo -> SetCaptureCfg -> SetDisplayCfg -> UpdateWce
  UpdateWce  (window_manager.cpp:255)
    GetDisplayCfgByAfd -> kAFDMapTable[afd][quelle][ziel]   (Proportionstabelle)
    CalcPropRect        (windows_manager_util.c)            Ergebnis = Teil x (Basis/Proportion)
    WCETop::SetWindow (WCETop.cpp:1019)
      CapWinNode   CalcWindow + WriteReg   -> INCAP
      NRWinNode    CalcWindow + WriteReg   -> 0x05000000
      DETNWinNode  CalcWindow
      ProcWinNode  CalcWindow + WriteReg   -> 0x05140000 + Scaler 0x05180000
      PanelWinNode CalcWindow + WriteReg   -> 0x051C0000
```

Ein **korrekter** Durchlauf für 1280×720 → 1920×1080 sieht so aus:

```
capture_cfg  [1280,720][1280,720]      display_cfg [1920,1080][1920,1080]
CapWinNode   in [260,25,1280,720]  out [0,0,1280,720]  ratio 1:1
             rowbyte 80, line_num 720      Y[0x50, 0x50, 0x2d0]
NRWinNode    in [0,0,1280,720]     out [104,25,1280,720]
ProcWinNode  in_win_size [1280,720]  out_win_size [1920,1080]  ratio [43690 x 43690]
PanelWinNode out [0,0,1920,1080]
```

**Wichtig für das Lesen der Logs:** `SetCaptureCfg` druckt seine beiden Rechtecke in *umgekehrter*
Reihenfolge - `[a2[4..7]][a2[0..3]]`, also `[Quelle][Anzeige]`. Wer das als `[Quelle][Ziel]` liest,
zieht falsche Schlüsse (so geschehen, siehe `nachtlog/S7`).

---

## 5. Was den Neubau auslöst - und was nicht

| Weg | Wirkung |
|---|---|
| **Descriptor mit neuer Geometrie veröffentlichen** | **löst den Neubau aus** ✓ |
| `Wce_SetWindow` (RPC) | **wirkungslos** - endet MIPS-seitig in einem Stub |
| `SetSource` weg und zurück | löst `SetSignalInfo`/`SetCaptureCfg` aus - und damit einen **zweiten**, fehlerhaften Neubau |
| `win rn 2` (Shell) | setzt nur das Flag, löst nichts aus |
| `dtv get_fb` (Shell) | liest den Descriptor in einen Stack-Puffer, ändert die Detektorkopien nicht |
| Modul-Neuladen / Rebind | Probe läuft, aber ohne Geometrieänderung kein Neubau |

Stock ruft `UpdateWce` in sechs Minuten Laufzeit **genau zweimal auf, beide bei Zeitstempel 0** -
der Fensteraufbau ist bei Stock eine Init-Zeit-Sache, kein Laufzeitvorgang.

---

## 6. Der Stand: die Skalierung läuft

Mit `0117` + `0120` + `0121` + `0122` wird 720p korrekt aufs Panel hochskaliert, mit Bildbeleg:

```
PROC    Quelle 1280x720  ->  Ziel 1920x1080
Scaler  0x05180008 = 0x3200AAAA   0x0518003C = 0x0000AAAA   0x05180014 Bit27 = 0
INCAP   aktiv 1280x720, rowbyte 0x50 = 80, Freigabe Bit 31 gesetzt
```

Was die vier Patches tun:

- **`0117`** veröffentlicht den Descriptor bei Geometriewechsel neu. Ohne ihn skaliert die Firmware
  nie - gemessen.
- **`0120`** hält die vier Fensterwörter (rec 28/30/32/34) auf **Panelgröße**. Sie sind die
  Konfiguration des Fenstermanagers, nicht die Bildgeometrie; mit Quellmaßen darin staucht
  `CalcPropRect` die Aufnahme auf 853×480.
- **`0121`** gibt die Aufnahme direkt frei (Bit 31 in `0x06940928` **und** `0x06940968`) statt über
  einen Quellenwechsel - der löste einen zweiten, fehlerhaften Neubau aus.
- **`0122`** setzt nach, bis die Freigabe hält (gemessen 159-223 ms).

## 7. Was daran noch nicht stimmte - und seit 08.09. gelöst ist

**Grünstich (gelöst, `0123`).** Der Neubau über den VidDec-Descriptor schaltet den Eingangs-Farbwandler der
Aufnahme ab (`MP_ICSC_VINCAP`, INCAP `0x06940824` Bit 31 = Bypass), weil der Descriptor `yuv420_888` sagt und
die Firmware für YUV-Signale keinen Wandler braucht - für die HDMI-Aufnahme, die RGB bekommt, aber schon. Das
RGB landete ungewandelt im NV16-Ring (Grau: Cb ≈ Cr ≈ Y statt 128). Rückweg ohne Quellenwechsel:
`THal_Vp_SetVideoRange` mit geändertem Wert (2, dann 0) - die Firmware wertet dann VidDec- und HDMI-Cache neu
aus, der HDMI-Cache gewinnt (BT709). `0123` macht das nach dem Neubau und **vor** der Freigabe der Aufnahme,
so dass kein grüner Rahmen entsteht. Regel und Register: [`nachtlog/S9`](nachtlog/S9-re-tfd-vincap-icsc.md);
Messung und Abnahme: [`nachtlog/S11`](nachtlog/S11-gruenstich-ursache-und-callback-slots.md).

**Kippen nach vier bis fünf Wechseln (gelöst, `0124`).** Kein Anzeigefehler, sondern ein Slot-Leck im
`cpu_comm`: der Kernel gab die Slots der MIPS→ARM-Rückrufe nie zurück; nach 19 Rückrufen (≈ 6 Wechsel) blieb
der MIPS-Sender in `fifo_isNearlyFull` stehen - Tick steht, Shell tot, jeder RPC `-110`. `0124` gibt den Slot
nach dem ACK frei; `watch` zeigt den eingehenden Pool (`ungelesen 0`, `frei 20`). Abgenommen mit 27 Rückrufen
in einem Boot. Firmware-Seite: [`nachtlog/S10`](nachtlog/S10-re-cpucomm-callback-slots.md).

Ein Diagnosewerkzeug, das beides sichtbar macht: `analyse/hdmi-seq/ringstat.py` liest Y/Cb/Cr direkt aus dem
Capture-Ring - vor der Anzeige, unabhängig von der Kamera.

## 8. Betriebswissen, teuer bezahlt

- **Bilder ansehen, nicht Zahlen lesen.** Ein Doppelbild hat dieselbe Streuung wie ein gutes Bild;
  `wandcheck.py std` allein hat mehrfach in die Irre geführt.
- **Die Quelle prüfen, nicht nur den Modus.** Ein `xrandr --mode 1280x720` bei einem X-Schirm von
  1920×1080 liefert nur einen Ausschnitt - mehrere Fotos waren dadurch wertlos. Sauber ist
  `--output eDP-1 --mode WxH --output HDMI-2 --mode WxH --same-as eDP-1`, danach `xrandr | grep ^Screen`.
- **Register nicht im laufenden Betrieb durchprobieren.** Zweimal hat es die Firmware hängen lassen
  (leerer Signalsatz, RPCs von <10 ms auf 537 ms), nur ein Netboot-Neustart half.
- **Ohne laufenden Player kommen keine Firmware-Ereignisse an** - die Callback-Registrierung hängt
  seit `0100` am ersten `open()` von `/dev/video1`.
- **`/dev/mem` auf den MIPS-Carveout ist DEVICE-Speicher**: nur ausgerichtete 32-Bit-Zugriffe,
  Pythons `mmap`-Slicing stirbt mit SIGBUS, nichtdeterministisch nach Länge.
