# S15 - RE: Formatregel und Breitbildmodus der MIPS-Displayfirmware (5:4 wird gestreckt)

Datum 08.09.2026. Reine statische Analyse (idalib, Arbeitskopie `analyse/ida/db-aspect/display.bin.i64`)
plus vorhandene elog-Mitschnitte (`re/captures/weltneuheit/s11-20260908/elog-run{1,3,4}*.txt`). Board und
Zuspieler nicht angefasst, keine Änderung unter `mainline/patches/` oder `userspace/`.
Skripte `analyse/ida/ida_q90a.py` … `ida_q98a.py` (Suffix `a`, weil S14 parallel `ida_q90.py` ff. für
`libvideo.so` belegt hat), Rohausgaben `re/captures/weltneuheit/aspect-q9*-20260908.log`.

Adressen sind MIPS-Adressen der Firmware (`0x8B1xxxxx` Code, `0x8B2xxxxx` Daten).

## Kurzfassung

1. **Formatregel** (`windows_manager_util.c`): `GetSignalAspectCode` (`0x8b19e0f0`) klassifiziert das Signal
   nach `ratio = 1000·Breite/Höhe` in **vier Klassen**: 1:1, 4:3, 2.21:1 und **„sonst" = 16:9**. Ein Wert
   außerhalb aller Bereiche (5:4 = 1250, 16:10 = 1600, 720×576 = 1250) ist **kein Fehlerfall, sondern die
   Vorgabe 16:9**, und die landet mit `kAFDMapTable[8][1][1]` (`0x8b2059bc`) beim Vollbild → gestreckt.
2. **Breitbildmodus** existiert: `kHalDisplayAspectRatio_{Auto=0, KeepSourceAr=1, Full=2, 16_9=3, 4_3=4, Zoom=5}`
   (`g_aspect_ratio_names 0x8b1f511c`), ausgewertet in `WindowManager::UpdateWce` (`0x8b1aaf1c`).
   **`KeepSourceAr` (1) zeigt 1280×1024 proportional als 1350×1080 mittig mit Balken** - genau die
   Regel, die wir wollen; sie gilt für alle Nicht-16:9-Quellen und ist für 16:9 die Identität.
3. **Zugang:** `app set_wm N` (Shell) und der RPC `THal_Vp_Wce_SetWindow` enden **beide im selben Stub**
   `sub_8B1099C8` = `return 1` - wirkungslos. Es gibt **keinen** RPC `SetAspectRatio`/`SetWideMode`/
   `SetOverscan` (alle 64 `THal_*`-Namen geprüft); `Wce_EnablePixel2PixelMode` ist ein Log-Stub.
   **Der einzige lebende Weg ist Descriptor-Wort 35** (`display_properties.aspect_ratio`): es wandert
   `ConvertFrameInfo2SignalInfo` → `SignalInfo+168` → `sub_8B107770` (AppTop) → `WindowManager::SetAspectRatio`
   (`0x8b1aa9d4`, vtable-Slot +32) → `m_aspect_ratio` → `UpdateWce`. Unser Treiber schreibt dort heute 0 (Auto).
4. **Empfehlung:** `rec[35] = 1` im VidDec-Descriptor (Kernel `h713_afbd_build_video_info`, Patchlinie 0120),
   ggf. als Plane-Eigenschaft umschaltbar (`Full` = 2). Vorab-Test ohne Kernelbau: Wort 35 der **lebenden**
   Descriptor-Seite per `/dev/mem` auf 1 setzen - die Firmware vergleicht dieses Wort
   (`CompareFrameInfo 0x8b147440`) und baut neu. Offen: ob der Wert roh (1) oder ×16 (16) erwartet wird;
   die Verbraucherkette spricht für roh.

---

## A. Die Formatregel - `windows_manager_util.c`

### A.1 Zwei Klassifizierer, ein Tabellenzugriff

| Funktion | Adresse | elog-Zeilen | Aufgabe |
|---|---|---|---|
| `GetSignalAspectCode` | `0x8b19e0f0` | 516-529 | Klasse der **Quelle** |
| `GetCanvasAspectCode` | `0x8b19e504` | 577-580 | Klasse der **Leinwand** (aktives Anzeigefenster) |
| `GetDisplayCfgByAfd` | `0x8b19f064` | 634 | `kAFDMapTable[afd][signal][canvas]` |
| `sub_8B19F158` | `0x8b19f158` | - | AFD-Pfad: Tabellenzeile → `CalcPropRect` → capture_cfg/display_cfg |
| `CalcPropRect` / `CalcPropRect1` | `0x8b19eb1c` / `0x8b19e93c` | 819-859 | Proportionalrechteck: `Ergebnis = Basis + (Aktiv−Voll)·Basis/Voll` |
| `sub_8B19DFEC` | `0x8b19dfec` | - | Bildmaß der Quelle je Quellentyp |
| `sub_8B19E088` | `0x8b19e088` | - | wie DFEC, aber `par` statt Bildmaß, wenn `b_par_valid` |

**Die Zeile 577 (`ratio:%d`) ist die Leinwand, nicht die Quelle.** Sie zeigt immer 1777, weil sie
`1000·1920/1080` des aktiven Anzeigefensters ist. Die Quelle steht in Zeile 516 (`ratio :%d`).

### A.2 `GetSignalAspectCode` - belegt (Dekompilat, `aspect-q91-formatregel-20260908.log`)

```
ratio = b_par_valid ? 1000*par_horizontal/par_vertical : 1000*h_size/v_size
  991 ≤ ratio ≤ 1009  → 4   (kRatioSquare  990 < r < 1010)   1:1
 1301 ≤ ratio ≤ 1365  → 0   (kRatio4By3   1300 < r < 1366)   4:3
 2201 ≤ ratio ≤ 2219  → 2   (kRatio2p21By1 2200 < r < 2220)  2.21:1
 sonst                → 1   16:9 - der gedruckte Bereich 1776..1778 wird NIE geprüft, er ist die Vorgabe
```

`h_size/v_size` kommen aus `sub_8B19DFEC`: Quellentyp 1 (VidDec = unser Descriptor) und 2 → `SignalInfo`
Wort 13/15 (`pic_h_size`/`pic_v_size`, bei Interlace ×2); HDMI (Typ 3-6) und CVBS (7-9) → Wort 12/13
(`h_active`/`v_active`); unbekannt → 1920×1080. `par_horizontal/par_vertical` (Wort 22/23) werden
**als Anzeigeverhältnis** benutzt (1000·h/v), nicht als Pixelverhältnis.

Beispiele (gerechnet, mit S11-Bildbelegen wo vorhanden):

| Quelle | ratio | Klasse | Ergebnis (Auto) | Beleg |
|---|---|---|---|---|
| 1920×1080, 1280×720 | 1777 | 1 (16:9) | Vollbild | elog run1/run4 |
| 1024×768 | 1333 | 0 (4:3) | 1440×1080 mittig | S11 `r12-01`, Scaler `0x3200B60B` (= 1024/1440) |
| 1440×900 | 1600 | **1 (16:9)** | **gestreckt** (11 %) | S11 `r12-02` („korrekt" war Augenmaß) |
| 1280×1024 | 1250 | **1 (16:9)** | **gestreckt** (13 %) | S11 `r12-03` |
| 1366×768 | 1778 | 1 | Vollbild | - |
| 720×576 / 720×480 | 1250 / 1500 | 1 | gestreckt | - (Stock trägt hier AFD/par über den Decoder) |

### A.3 `GetCanvasAspectCode` - belegt

```
ratio = 1000*Breite/Höhe des aktiven Anzeigefensters (sub_8B19F008: CalcPropRect(dst_cfg, Panel))
 1321 ≤ r ≤ 1345 → 0 (4:3)      2311 ≤ r ≤ 2355 → 2 (21:9)      sonst → 1 (16:9)
```
(Der elog druckt „21:9 ratio range:2356, 2310" - Argumente vertauscht, kosmetisch.) Bei uns immer 1.

### A.4 `GetDisplayCfgByAfd` - belegt

```
afd  = (source_id == 1 && 1 ≤ SignalInfo.afd ≤ 15) ? SignalInfo.afd : 8      // 8 = AFD „full frame"
sig  = GetSignalAspectCode(sig);  can = GetCanvasAspectCode(w,h)
Zeile = kAFDMapTable + 64 * (2*(sig + 3*afd) + can)                          // [16][3][2] × 64 Byte
```
Bemerkung: Klasse 4 (1:1) sprengt die Dimension 3 und liest die Zeile `[afd+1][1][can]` - Firmware-Eigenart,
für uns ohne Belang. `SignalInfo.afd` ist bei VidDec **Descriptor-Wort 12** (`active_format_description`);
unser Treiber schreibt 0 → Zeile 8.

### A.5 Aspect-Klassen, die die Firmware kennt (Strings)

- Signalklassen ohne Namen (nur Konstanten `kRatioSquare/4By3/16By9/2p21By1_{Low,Hig}Range`, `0x8b2055b0…`).
- Breitbildmodi `kHalDisplayAspectRatio_Auto/KeepSourceAr/Full/16_9/4_3/Zoom/Max` (`0x8b1f4ccc…0x8b1f4d7c`,
  Tabelle `g_aspect_ratio_names 0x8b1f511c`, Werte 0…6). Kein `ARC_*`, kein `WM_*`, kein Panorama/JustScan.
- `display aspect ratio` (Fehlertext in `VidDec_dump_frame_info 0x8b12ea14`, Zeile 349).

---

## B. Breitbildmodus - Enum, Wirkung, Zugang

### B.1 Wirkung in `WindowManager::UpdateWce` (`0x8b1aaf1c`, `window_manager.cpp:255`) - belegt

`a6 = m_aspect_ratio` (Objekt +324). Reihenfolge: Ist `a6 == 0`, wird zuerst der AFD-Pfad `sub_8B19F158`
versucht (Tabelle, Abschnitt C). Sonst - oder wenn der AFD-Pfad scheitert - `display_cfg = CalcPropRect(dst_cfg,
Panel)`, `capture_cfg = CalcSignalActiveWin(sig, src_cfg)` (`0x8b19eb98`) und dann:

| Wert | Name | Funktion | Ergebnis für 1280×1024 auf 1920×1080 |
|---|---|---|---|
| 0 | Auto | AFD-Pfad; Rückfall `sub_8B19ED6C` | Tabelle `[8][1][1]` → **Vollbild (gestreckt)** |
| 1 | KeepSourceAr | `CalcDisplayActiveWinWithAspectRatioOfSignal 0x8b19ed6c` + `sub_8B19DEC0` | **[285, 0, 1350, 1080]** - proportional, mittig, Balken |
| 2 | Full | `default` | Vollbild |
| 3 | 16_9 | `sub_8B19EEAC` | erzwungen 16:9 = Vollbild |
| 4 | 4_3 | `sub_8B19EF5C` | erzwungen 4:3 → [240, 0, 1440, 1080] (5:4 um 6,7 % zu breit) |
| 5 | Zoom | `sub_8B19ECD8` | Breite voll, Höhe aus dem Verhältnis → beschnitten |
| 6 | Max | (Zähler) | - |

`sub_8B19ED6C` rechnet: `h,v = par (falls gültig) sonst pic_size`; wenn `h·PanelH ≥ PanelW·v` → Höhe =
`PanelW·v/h`, sonst Breite = `PanelH·h/v`, jeweils zentriert. Für 1280×1024: 1280·1080 < 1920·1024 → Breite
= 1080·1280/1024 = **1350**, x = 285. Für 1920×1080 und 1280×720 ist es die Identität, für 1024×768 dieselben
1440×1080 wie heute, für 1440×900 → 1728×1080, für 1366×768 → 1920×1079 (eine Zeile Rand, harmlos).
`sub_8B19DEC0` (`0x8b19dec0`) korrigiert danach um das Verhältnis Aktiv/Voll des `src_cfg`; mit Aktiv = Voll
(Patch 0120: Panel×16 in Wort 27-30) ist das neutral - nachgerechnet.

Erwartete Register (aus der belegten Formel `0x05180008[21:0] = in·65536/out`, doku/96): waagerecht
1280→1350 = **0xF2B9** (62137), senkrecht 1024→1080 = **0xF2B7** in `0x0518003C`; Rundung der Firmware
nicht geprüft (vermutet ±1).

**Pixeltreu (1280×1024 ungeskaliert mittig)** kennt die Firmware **nicht**: kein Modus liefert Skalierung 1:1
bei kleinerem Fenster; `THal_Vp_Wce_EnablePixel2PixelMode` (`0x8b14c6f0`) und `Disable…` (`0x8b14c784`)
drucken nur ENTER/LEAVE.

### B.2 Zugang (1): Shell `app set_wm N` - belegt, **wirkungslos**

Tabelle `0x8b1eb550` ({Handler, Name, Hilfe}, 12 Byte): `set_wm` → `sub_8B110724` (IDA hatte dort keine
Funktion; erzwungen disassembliert, `aspect-q95-…log`). Der Handler parst ein Argument, druckt
`dbg_cmd_app_set_wide_mode … aspect_ratio :%d` (`debug/app_dbg_cmd.cpp:110`) und ruft `sub_8B1099C8`
(`0x8b1099c8`) - **`return 1`**, nichts weiter. Zum Vergleich: `set_mm` → `sub_8B109944` → AppTop-Ereignis
Typ 5 → `WindowManager::SetMirrorMode` + `Refresh` (funktioniert), `set_pm` → `sub_8B1098BC`.
`win os N` (`0x8b1abd74`, 0-100) → `SetOverScanRatio` (Slot +16) + `Refresh`; der Overscan wird aber nur
angewandt, wenn `DeviceManager`-Typ der Quelle 0 ist (`sub_8B1AB9E8`, `0x8b1ab9e8`: Typ ≠ 0 → `m_src_cfg`
unverändert) - für unseren VidDec-Pfad (Typ 3, siehe B.4) **ohne Wirkung** (vermutet aus Dekompilat).

### B.3 Zugang (2): RPC über cpu_comm - belegt, **kein passender RPC**

Alle 64 registrierten `THal_*`-Namen (Liste in `aspect-q93-…log`): kein `SetAspectRatio`, `SetWideMode`,
`SetVideoWindow`, `SetOverscan`. Die `Wce`-Gruppe:

| RPC | Adapter → Handler | Verhalten |
|---|---|---|
| `THal_Vp_Wce_SetWindow` | `0x8b109d54` → `0x8b14c438` | drei Phys-Zeiger (src-Rect, dst-Rect, aspect u32; NULL erlaubt, `& 0x0FFFFFFF \| 0xA0000000`); speichert in `dword_8B22F3B8/8B22F3A8/8B22F3A4`, ruft **`sub_8B1099C8` = Stub** mit den Vorgaben 30720×17280 → wirkungslos (cstengers Befund, jetzt mit Mechanismus) |
| `THal_Vp_Wce_GetWindow` | `0x8b109dc0` → `0x8b14c610` | liefert **Konstanten** 0/30720/0/17280 und aspect 2 |
| `THal_Vp_Wce_GetActiveWindow` | `0x8b109e2c` → `0x8b14c684` | WM-Slot +36: aktive Fenster (lesend) |
| `THal_Vp_Wce_SetMirrorMode` | `0x8b109d20` → `0x8b14c384` | funktioniert (Ereignis Typ 5) |
| `THal_Vp_Wce_Enable/DisablePixel2PixelMode` | `0x8b109e88/0x8b109edc` | Log-Stubs |

Kommandonummern gibt es nicht als Tabelle: `cpu_comm` hasht den Namen (`cpu_comm_name2id`, doku/88);
`hy310-tv ctl rpc THal_Vp_Wce_SetWindow 0 0 <phys>` wäre formal absetzbar, **kann aber nichts bewirken**.

### B.4 Zugang (3): Descriptor - belegt, **der lebende Weg**

Strukturen aus der typeinfo (`aspect-q96-…log`):

| Descriptor `VidDec_FrameInfo` (36 Wörter) | → `VidDec_SignalInfo` (43 Wörter) | Verwendung |
|---|---|---|
| W10/11 `par_width/par_height` | +88/+92 `par_horizontal/vertical`, +84 `b_par_valid` (wenn beide ≠ 0) | Ratio in A.2 statt Bildmaß |
| W12 `active_format_description` | +96 `afd` | Zeile der `kAFDMapTable` (A.4) |
| W27-30 `src_*_x16` | +104: `{0,30720,0,17280}` fest + +120 unsere 4 Wörter | `SetCaptureCfg` (Slot +24) → `m_src_cfg` |
| W31-34 `dst_*_x16` | +136: `{0,30720,0,17280}` fest + +152 unsere 4 Wörter | `SetDisplayCfg` (Slot +28) → `m_dst_cfg` |
| **W35 `aspect_ratio`** | **+168 `aspect_ratio`**, +100 `b_display_props_valid = 1` (nur bei W1 == 2) | **`SetAspectRatio` (Slot +32) → `m_aspect_ratio`** |

`VidDecSignalDetector_ConvertFrameInfo2SignalInfo` (`0x8b1471b0`) kopiert W35 roh. `sub_8B107770`
(`0x8b107770`, aufgerufen aus `HandleSignalEvent 0x8b108644`, `ThreadMain`, Ctor) macht dann:

```
type = DeviceManager->slot16(sig.source_id)
WM->SetSignalInfo(sig)                                   // Slot +20
if (type == 3) {                                          // VidDec
    if (sig.b_display_props_valid) {                      // Descriptor W1 == 2
        WM->SetCaptureCfg(sig+104); WM->SetDisplayCfg(sig+136); WM->SetAspectRatio(sig.aspect_ratio /*+168*/);
    }
    WM->SetRefreshNode(1)
} else WM->SetRefreshNode(0)
WM->SetLowLatency(...); WM->Refresh(a3)                   // Slot +40, +48 → UpdateWce
```
Genau diese Folge steht im elog run4 (Zeilen 413-420): `SetSignalInfo → SetCaptureCfg m_src_cfg [0,0,30720,
17280][…] → SetDisplayCfg → aspect_ratio:0 → node:0x1 → low_latency:1 → b_by_vs → UpdateWce`. Damit ist
belegt, dass unser Descriptor den `type == 3`-Zweig nimmt und **Wort 35 jedes Mal in `m_aspect_ratio` landet**
(heute 0, weil `h713_afbd_build_video_info` das Wort nach `memset` nicht setzt; kein Patch in
`mainline/patches/kernel/` schreibt `rec[10]`, `rec[12]` oder `rec[35]`).

**Wer bestimmt das Panelfenster?** Beides, geschichtet: die Descriptor-Wörter 27-34 sind „Proportionsrahmen"
(Voll = 30720×17280 fest, Aktiv = unsere Wörter) - `CalcPropRect` bildet sie auf Signal bzw. Panel ab; mit
Panel×16 (Patch 0120) ist der Rahmen das ganze Panel. **In diesen Rahmen** setzt die Formatregel (Tabelle oder
Modus) das aktive Anzeigefenster. Die Firmware überschreibt also nicht das Fenster aus dem Descriptor, sie
passt das Bild darin ein. Daraus folgt eine zweite Descriptor-Variante (vermutet, nicht getestet): Wort 31-34
= `[285·16, 1350·16, 0, 1080·16]` bei `aspect = Auto` ergäbe über `sub_8B19F158` (`a5 = {0,hde,0,vde}` →
`CalcPropRect(dst_cfg, Panel)` → Zeile `[8][1][1]` = Identität) dasselbe 1350×1080 - dann rechnet aber der
Treiber, und die Wörter 27-30 müssen Panel×16 bleiben (die zurückgenommene 0118 hatte die Quellmaße in
27-30 gesetzt, daher das „Stauchen" aus doku/96).

---

## C. `kAFDMapTable` (`0x8b2059bc`, 6144 Byte) - belegt (Volldump `aspect-q93-…log`)

Aufbau `[afd 0..15][signal 0..2][canvas 0..1]`, je 64 Byte = 16 Wörter = **zwei Proportionspaare**:
`src{ voll[hs,hsz,vs,vsz], aktiv[…] } | dst{ voll[…], aktiv[…] }`. Die Einheiten sind beliebig
(1000-Promille, 720×576, 1600×900, 4000×3000, 7072×3978 …), weil `CalcPropRect1` nur `Aktiv/Voll` auf das
Basisrechteck abbildet. Signalklassen 0 = 4:3, 1 = 16:9, 2 = 2.21:1; Leinwand 0 = 4:3, 1 = 16:9. Die
AFD-Zeilen entsprechen SMPTE-2016-Codes (8 = Vollbild, 9 = 4:3 mittig, 10 = 16:9 mittig, 11 = 14:9,
13/14/15 = Shoot-and-Protect-Varianten).

Auszug (Zeilenadresse; `src aktiv` = Beschnitt der Quelle, `dst aktiv` = Fenster auf der Leinwand):

| Zeile | @ | src voll / aktiv | dst voll / aktiv | Bedeutung auf 1920×1080 |
|---|---|---|---|---|
| **[8][1][1]** (16:9 auf 16:9, **unser 5:4-Fall**) | `0x8b20667c` | 720×576 / voll | 1600×900 / voll | **Vollbild → Streckung** |
| [8][0][1] (4:3 auf 16:9) | `0x8b2065fc` | 720×576 / voll | 1600×900 / [200,1200,0,900] | Pillarbox **[240,0,1440,1080]** = S11 `r12-01` |
| [8][2][1] (2.21:1 auf 16:9) | `0x8b2066fc` | 720×576 / voll | 7072×3978 / [0,7072,289,3300] | Letterbox 7,3 % |
| [8][1][0] (16:9 auf 4:3) | `0x8b20663c` | 7200×5760 / voll | 4000×3000 / [0,4000,375,2250] | Letterbox |
| [9][1][1] (AFD 9 = 4:3 mittig) | `0x8b2067fc` | 720×576 / **[90,540,0,576]** | 1600×900 / [200,1200,0,900] | Quelle beschneiden, 4:3 zeigen |
| [10][0][1] (AFD 10 = 16:9 mittig) | `0x8b2068fc` | 720×576 / [0,720,72,432] | voll | Letterbox-Balken wegschneiden |
| [13][1][1] (4:3 S&P 14:9) | `0x8b206dfc` | [90,630,0,576] | [100,1400,−75,1050] | leichter Overscan |
| [0][0][0] | `0x8b2059bc` | 1000 / 1000 | 400×300 / voll | Identität (Promille) |

**Für ratio außerhalb aller Bereiche** greift Signalklasse 1 und damit `[afd][1][1]`; mit `afd = 8`
(kein AFD im Descriptor) ist das die Identitätszeile → `display_cfg` aktiv = ganzer Rahmen aus Wort 31-34
= Panel → gestreckt. Über Descriptor-Wort 12 (`afd`) ließe sich nur eine **Klassen**-Zeile wählen
(z. B. 9 beschneidet die Quelle auf 4:3 - falsch für 5:4); über Wort 10/11 (`par = 4:3`) käme man in Klasse 0
und die 1440×1080-Pillarbox (5:4 um 6,7 % zu breit). **Exakt 5:4 liefert nur `KeepSourceAr`.**

---

## D. Empfehlung - belegt / vermutet getrennt

**Belegt (statisch + elog run4):**
- `m_aspect_ratio` wird bei jedem Signalereignis aus Descriptor-Wort 35 gesetzt (`sub_8B107770` → Slot +32).
- `UpdateWce` wertet 0/1/3/4/5 aus; 1 (`KeepSourceAr`) ergibt für 1280×1024 das Fenster [285,0,1350,1080],
  für 16:9-Quellen die Identität, für 1024×768 dasselbe wie heute.
- `CompareFrameInfo` (`0x8b147440`) vergleicht Wort 35 (neben 0-18, 22-24, 27-34): eine Änderung **allein von
  Wort 35** gilt als neuer Rahmen → `Convert` → Signal-Info mit neuem `aspect_ratio`.
- Shell `set_wm`, RPC `Wce_SetWindow`, `Pixel2Pixel`-RPCs: tot. Kein RPC zum Testen vorhanden.

**Vermutet (am Board zu prüfen):**
- Kodierung: `dump_frame_info` druckt `names[W35 >> 4]` (also ×16), die Verbraucherkette (`Convert` roh →
  `SetAspectRatio` roh → `switch` auf 0…5) spricht für **roh = 1**. Mit 16 fiele der `switch` auf `default`
  = Vollbild (kein Schaden, keine Wirkung). Reihenfolge: erst 1, dann 16.
- Dass der Neubau nach dem Wort-35-Wechsel wie bei Geometriewechseln durchläuft (Capture-Freigabe wird
  gelöscht, hdmirx-Treiber re-armt, 0121/0128/0129) - derselbe Pfad wie jedes `publish_video_info`.

**Weg für Treiber/`hy310-tv` (ohne Shell):**
1. Kernel, `h713_afbd_build_video_info` (Patchlinie 0120): `rec[35] = aspect;` mit `aspect = 1`
   (`KeepSourceAr`) als Vorgabe; optional Plane-Eigenschaft (`aspect`: 1 = proportional, 2 = Vollbild,
   4 = 4:3), dann `hy310-tv ctl set aspect …` → neue Geometrie-Veröffentlichung → Neubau. Wort 27-30 bleiben
   Panel×16. Das ist der Weg, den Stock benutzt (Android schreibt `display_properties.aspect_ratio`).
2. **Vorab-Test ohne Kernelbau** (Board, nur mit Sichtkontakt): Descriptor-Seite finden
   (`AFBD 0x05600098` → Zeiger; ARM-phys = Wert & 0x0FFFFFFF | 0x40000000), Wort 35 (Offset 0x8C) mit einem
   ausgerichteten 32-Bit-Schreibzugriff über `/dev/mem` auf **1** setzen, während 1280×1024 anliegt.
   Erwartung im elog Stufe 5: `window_manager.cpp 158 aspect_ratio:1`, `UpdateWce 320 aspect_ratio : 1`,
   `324 display_cfg : [  285,     0,  1350,  1080][    0,     0,  1920,  1080]`,
   `windows_manager_util.c 906/907 horizontal:1280 vertical:1024`, ProcWinNode `ratio [62137 x 62135]` (±1),
   Scaler `0x05180008 ≈ 0x3200F2B9`, `0x0518003C ≈ 0xF2B7`; Wand: 5:4 mittig mit Balken. Danach `win wm`
   → `m_aspect_ratio 1`. Rückweg: Wort 35 wieder 0 oder Quellenwechsel (der Kernel schreibt beim nächsten
   Geometriewechsel sein eigenes Abbild mit 0 zurück). Bleibt es bei `aspect_ratio : 1` **und** Vollbild,
   dann 16 probieren.
3. Kein `hy310-tv ctl rpc`-Test nötig; wer den Negativbefund sehen will: `rpc THal_Vp_Wce_GetWindow 0 0 <phys>`
   liefert immer aspect 2, `rpc THal_Vp_Wce_SetWindow 0 0 <phys-mit-1>` ändert nichts an `win wm`.

Randnotizen: der WM-Konstruktor (`0x8b1ab528`) setzt `m_aspect_ratio = 2` (Full), der erste Descriptor
überschreibt das mit 0 - deshalb zeigt `win wm` 0. `THal_Vp_Wce_SetWindow` mit `aspect = 2` in unserer
Probe-Sequenz (doku/88 #12/#17) ist folgenlos und kann bleiben (Stock ruft es auch).

## Dateien

- Skripte: `analyse/ida/ida_q90a.py` … `ida_q98a.py`; README-Abschnitt S15 in `analyse/ida/README.md`.
- Logs: `re/captures/weltneuheit/aspect-q90-strings-namen-…`, `-q91-formatregel-`, `-q92-shell-afdtable-`,
  `-q93-afdtable-wm-rpc-`, `-q94-aspect-setter-`, `-q95-setwm-setwindow-kette-`, `-q96-structs-wm-slots-`,
  `-q97-threadmain-getwindow-`, `-q98-compareframeinfo-20260908.log`.
- Vtable `TWindowManager` (vptr `off_8B208D40`): +8 SetRefreshNode `0x8b1aa61c`, +12 SetMirrorMode
  `0x8b1aa684`, +16 SetOverScanRatio `0x8b1aa6ec`, +20 SetSignalInfo `0x8b1aa568`, +24 SetCaptureCfg
  `0x8b1aa754`, +28 SetDisplayCfg `0x8b1aa860`, **+32 SetAspectRatio `0x8b1aa9d4`**, +36 GetActiveWindow
  `0x8b1aaaa4`, +40 SetLowLatency `0x8b1aa96c`, +44 SetSeamless `0x8b1aaa3c`, +48 Refresh `0x8b1ab9e8`,
  +56 DbgDumpWindowConfig `0x8b1aab64`. Singleton `MEMORY[0x8BAC4BD8]` (Getter `0x8b1abd18`).
