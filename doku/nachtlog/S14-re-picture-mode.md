# S14 - RE: `THal_Vp_SetPictureMode`, die `Get*`-Routinen und der Bildmodus-Zustand

**08.09.2026, statische Analyse** (idalib 9.1 auf der Arbeitskopie `analyse/ida/db-pq/`, Firmware-Abbild,
`database.TSE`, Vendor-Bibliotheken, Stock-elog). **Board und Zuspieler nicht angefasst, keine Patches geändert.**
Skripte `analyse/ida/ida_q80.py` … `ida_q92.py`, Rohausgaben `re/captures/weltneuheit/pq-q8*-20260908.log`,
`pq-q88-arm-20260908.log` (libhaldisplay/libvideo), `pq-q90-libvideo-20260908.log`.
Adressen sind MIPS-VAs (`0x8Bxxxxxx`), Register ARM-physisch. Auftrag: doku/99 §3.

---

## 0. Kurzfassung

| Frage | Antwort in einem Satz | Stand |
|---|---|---|
| A - Nummer ↔ Modus | Die Firmware zählt **0 Vivid, 1 Standard, 2 Mild, 3 Game, 4 Calibrated, 5 Calibrated_Dark, 6 Computer, 7 Cinema, 8 Home, 9 Sports, 10 Shop, 11 Animation, 12 HDR, 13 Graphic** (Tabelle `dword_8B1F2120` → TSE-Attribut `UI_PictureModes`); 14/15 werden angenommen und wie Standard behandelt, ≥ 16 gibt „picturemode not supported!" | belegt |
| A - was der Wechsel tut | **Kein Register des PQ-Blocks, keiner der fünf Regler.** Er setzt das TFD-Filterattribut `UI_PictureModes`, schreibt für HDMI die TSE-Gruppe `V_INCAP` neu (kein Modul darin hängt am Attribut), gibt die Nummer an den MemoryAgent (Feld +4, Sonderfall 6) und bei Wechseln von/zu 3 oder 6 an den WindowManager (`SetLowLatency`, `Refresh`) | belegt |
| A - woher die Preset-Werte | **Nicht aus der Firmware.** Im Abbild gibt es keine Werte-Tabelle; `pq_picturemode.ini` liest die ARM-Seite (`libvideo.so`, `std::map<string,PictureMode>`), die Einzel-RPCs wären dann von dort zu senden. Im Stock-elog werden Brightness/Contrast/Saturation/Hue/Sharpness **nie** gesendet | belegt (Abbild, elog); ARM-Pfad nur teilweise, PQControl-Bibliothek fehlt im Auszug |
| B - `Get*` | Alle fünf Regler-Gets und TNR/SNR/DCI/BlackExtension sind **Stubs: `return 0`** (nur ENTER/LEAVE-Log). Kein Firmware-Zustand, keine Registerlesung | belegt, deckt sich mit I1 |
| C - Treiber | Nach `SetPictureMode` gibt es **keinen neuen Stand** der fünf Controls - die Firmware ändert sie nicht; die Controls bleiben wahr. Wer INI-Presets will, sendet die neun Set-RPCs selbst (Tabelle in §4). `Picture Mode` kann ein Menü mit den Firmware-Namen 0…13 werden | Empfehlung |
| D - `GetPictureMode` / `GetVideoRange` | `GetPictureMode` liefert den **zuletzt gesetzten Wert** (Zelle `0x8B272974`, Startwert 1 bei `THal_Vp_Init`). `GetVideoRange` liefert **konstant 1**, unabhängig vom Set | belegt |

---

## 1. Frage A - `THal_Vp_SetPictureMode(N)`

### 1.1 Die Kette (belegt, `pq-q80/q81/q82/q92`)

```
THal_Vp_SetPictureMode  Handler 0x8B10A8C0            (*a2 = 0: kein Rückgabewort)
  └ sub_8B14A284  thal_display_pq.cpp:261
       if (MEMORY[0x8B272974] == N) → LEAVE (Zeile 266), sonst:
       sub_8B12BB68(&v, &N)          → Identität (v = N)
       sub_8B1098BC(v)               → "AppTopSetPictrueMode", elog "%s, pic mode:%d"
            └ Nachricht {8, N} an AppTop-Singleton MEMORY[0x8B253578], vtable+12 (Post)
       MEMORY[0x8B272974] = N        → das ist der Wert, den GetPictureMode zurückgibt
       LEAVE (Zeile 275)

AppTopProjector_OnCommonEvent 0x8B1089B4, Typ 8  (app_top_projector.cpp)
  old = this+216;  if (old == N) return 1
  need = IsNeedToUpdateTfdForNewPicMode(old, N)     = sub_8B10890C   (§1.3)
  this+216 = N
  MemoryAgent->vt[+16](N)                            = sub_8B1530B8: MemoryAgent+4 = N
  if (need) {
      if (this+221 /*tfd update an*/) sub_8B107B04(this, this+32 /*VidDec-Cache*/, 16)
                                       [+ sub_8B107B04(this, this+224 /*HDMI-Cache*/, 16), wenn HDMI-Signal gültig]
      WindowManager->vt[+40] SetLowLatency( this+208 == 2 ? (N != 3 && N != 6) : this+208 )
      WindowManager->vt[+48] Refresh(0)             → WindowManager__UpdateWce
  } else if (this+221) {
      sub_8B107B04(this, this+32, 2) [+ (this, this+224, 2)]
  }
  sub_8B1071B8()                                     → Nachricht {1} an Singleton 0x8B253574 (Window-Manager-Thread)
```

`sub_8B107B04(this, sig, type)` baut über `sub_8B1078EC` den TFD-Filter neu - darin
`filter->SetItem(sub_8B12C4C0(this+216))`, also **Attribut `0x3001 UI_PictureModes`** - und schreibt ihn in den
Basisfilter (`Apply`, TFDHandler +116). Danach je nach `DeviceManager->GetStatus(sig->source_id)`:
**HDMI (Status 1) → `WriteModules(filter, "V_INCAP")`** (TFDHandler +56, elog `group name[V_INCAP]`);
VidDec (Status 3) → `WriteModules(filter, type)` mit type 2 oder 16 (TFDHandler +52, elog `group type[%d]`).
Was `type` 2 gegenüber 16 auswählt (`TFDManager` +48 `sub_8B1910D4` → `sub_8B190F24`), ist **nicht** aufgelöst;
für HDMI spielt es keine Rolle, dort wird immer die eine Gruppe per Name geschrieben.

Der Rückkanal des RPC ist leer (`*a2 = 0`), der Rückgabewert der Handler-Funktion ist der von `elog_output`.
Es gibt **keinen Fehlerpfad**, der einen Modus ablehnt.

### 1.2 Nummer ↔ Modus (belegt)

`sub_8B12C4C0` (`pq-q82`): `if (N < 14) return dword_8B1F2120[N]; else return 0x30010001;`.
Die Tabelle (`pq-q84`) und die Namen der Werte aus `database.TSE` (Attribut `0x3001`, `tse_dict`-Scan):

| N | `dword_8B1F2120[N]` | TSE-Name | INI-Name (`pq_picturemode.ini`) |
|---|---|---|---|
| 0 | `0x30010000` | `UI_PictureModes_Vivid` | `vivid` |
| **1** | `0x30010001` | `UI_PictureModes_Standard` | `standard` |
| 2 | `0x30010002` | `UI_PictureModes_Mild` | - |
| 3 | `0x30010003` | `UI_PictureModes_Game` | `game` |
| 4 | `0x30010005` | `UI_PictureModes_Calibrated` | - |
| 5 | `0x30010006` | `UI_PictureModes_Calibrated_Dark` | - |
| 6 | `0x30010007` | `UI_PictureModes_Computer` | `computer` |
| 7 | `0x30010008` | `UI_PictureModes_Cinema` | `cinema` |
| 8 | `0x30010009` | `UI_PictureModes_Home` | - |
| 9 | `0x3001000a` | `UI_PictureModes_Sports` | - |
| 10 | `0x3001000b` | `UI_PictureModes_Shop` | - |
| 11 | `0x3001000c` | `UI_PictureModes_Animation` | - |
| 12 | `0x30010012` | `UI_PictureModes_HDR` | `hdr` |
| 13 | `0x30010013` | `UI_PictureModes_Graphic` | - |
| 14, 15 | → `0x30010001` Standard | (kein eigener Name) | - |
| ≥ 16 | - | „picturemode not supported!" | - |

Die Werte `0x30010004`, `0x3001000d…0x30010011`, `0x30010014/15` (Expert_1/2) kommen in der Tabelle nicht vor.
Im Abbild gibt es **keine** Enum-Strings (`kHalPictureMode_*`, `vivid`, `energy_saving` fehlen; das einzige
„cinema" ist `tse:group:pure_cinema_ctrl` @`0x8B1EC7B0`, ein TSE-Gruppenname). Die Namen kommen allein aus der
TSE-Datenbank.

**Was Stock sendet (erschlossen, nicht direkt belegt):** In beiden Bootläufen des Stock-elogs
(`elog-stock-LIVE.bin`) endet `THal_Vp_SetPictureMode() ENTER` sofort mit `LEAVE` **Zeile 266** - dem
„unverändert"-Pfad - und `pic mode:%d` erscheint nie. Der Firmware-Startwert ist 1 (§2.2), Stocks Zustand laut
`pqcontrol_custom_setting.xml` ist `mode_hdmi1="standard"`. Also schickt Stock für `standard` die **1**, was mit
der Tabelle übereinstimmt. Die ARM-Bibliothek, die den Namen in diese Nummer übersetzt (`PQControl`,
`_ZN9PQControl11getInstanceEv`, von `libvideo.so` importiert), liegt **nicht** im Auszug (`vendor_a/` enthält nur
`etc/`), deshalb bleibt das ein Schluss aus elog + XML. `libhaldisplay.so` selbst reicht die Nummer 1:1 durch
(`THal_Vp_SetPictureMode @0x70B4`: `v8[1] = a1; Trid_Util_CPUComm_Call(...)`, `pq-q88-arm`).

Drei Nummerierungen, die man nicht verwechseln darf:

| Ebene | Zählung | Quelle |
|---|---|---|
| **MIPS-Firmware (die zählt für den RPC)** | 0 Vivid, 1 Standard, 2 Mild, 3 Game, 4 Calibrated, 5 Calibrated_Dark, 6 Computer, 7 Cinema, 8 Home, 9 Sports, 10 Shop, 11 Animation, 12 HDR, 13 Graphic | `dword_8B1F2120` + TSE |
| ARM `libvideo.so` (`CDeviceControl`, `std::map<string,PictureMode>`) | 0 standard, 1 cinema, 2 vivid, 3 sports, 4 game, 5 bright, 6 soft, 7 computer, 8 hdr, 9 calibrated, 10 calibrateddark, 11 home, 12 shop, 13 animation, 14 monitor, 17 energy_saving, 21 custom, 22 dynamic *(aus dem Dekompilat der statischen Initialisierung gelesen, Reihenfolge belegt, einzelne Zahlen unsicher)* | `pq-q88-arm` |
| `tvpq.db` `Picture_Mode.mode` / Legacy `pqconfig.h` | 0 standard, 1 cinema, 2 vivid, 3 game, 4 computer, 5 hdr, 6 custom | Datenbank |

Der Treiber-Kommentar „welche Nummer welcher Modus ist, ist nicht zu ermitteln" ist damit überholt: für die
Firmware ist es die erste Zeile.

### 1.3 Wertebereich und Sonderfälle (belegt, `pq-q82` Disasm)

`IsNeedToUpdateTfdForNewPicMode(old, new)` = `sub_8B10890C`:

```
8b10890c  sltiu $v0, $a1, 0x10 ; beqz → default        new ≥ 16: elog W "picturemode not supported!", return 0
case 3:  return old != 3
case 6:  return old != 6
case 0,1,2,4,5,7…15:  return (old == 3 || old == 6)
```

- HAL-Handler und `sub_8B14A284` prüfen **nichts**; auch bei „not supported" wird `this+216 = N` gesetzt, der
  MemoryAgent informiert und der TFD-Pfad mit type 2 ausgeführt. Nur die Nummer im Filterattribut fällt auf
  Standard zurück (`sub_8B12C4C0`, N ≥ 14).
- **3 (Game) und 6 (Computer) sind die einzigen Modi mit Nebenwirkung** außerhalb des TFD-Attributs: jeder
  Wechsel von oder zu ihnen löst den vollen TFD-Lauf (type 16) und `WindowManager::SetLowLatency` +
  `WindowManager::Refresh(0)` → `WindowManager__UpdateWce` aus (`window_manager.cpp` 152/185, vtable
  `0x8B208D40`, Singleton `0x8BAC4BD8`).
- **Modus 6 wird im MemoryAgent gesondert behandelt:** `memory_agent_update_onoff` (`0x8B153140`) prüft zweimal
  `MemoryAgent+4 != 6`; dieses Feld ist genau das, was Typ 8 hineinschreibt (`sub_8B1530B8`, `pq-q87/q89`). Die
  ältere Beschriftung dieses Feldes als „source_type" in den K1-K3-Kommentaren ist damit korrigiert: es ist der
  **Bildmodus**. Was der Sonderfall bewirkt (vermutlich PC-Modus ohne Frame-Speicher), ist **nicht** verfolgt.
- `sub_8B1071B8()` (Nachricht 1 an den Window-Manager-Thread) läuft bei **jedem** wirksamen Moduswechsel.

Für unseren Capture-Pfad heißt das: ein Menü, das 3 oder 6 anbietet, fasst über `UpdateWce` und den
MemoryAgent dieselben Blöcke an, die `Wce_SetWindow`/`memory_agent` bedienen. Das ist vor einer Freigabe am Board
zu messen (§5).

### 1.4 Was der Preset-Wechsel schreibt - und was nicht (belegt)

**Nicht die fünf Regler, nicht den PQ-Block `0x05001xxx`.**

1. `UIvalueMapping` (`0x8B17F3F8`) hat genau elf Aufrufer (`pq-q84`): die acht `OnHalPq*Change`
   (`0x8B10C398…0x8B10C86C`, IDs 4…13), `THal_Vp_SetWhiteBalance` (`0x8B14A790`, 35…40) und
   `THal_Vp_SetGamma` (`0x8B14A9AC`, 0x2A/0x58). Kein Aufruf aus der Picture-Mode-Kette.
2. Die TSE-Namensschnittstelle (`TBrightness::Write` `0x8B17AE10`, Strings `mp_brightness` … `mp_sharpness`) hat
   nur Datenreferenzen aus der Tabelle `0x8B200ED0` - keinen Code-Aufrufer.
3. Im Abbild existiert **keine Werte-Tabelle**: die INI-Zeilen (`50,45,45,50,40`, `50,55,60,50,60`,
   `50,50,50,50,0`, …) kommen weder als Byte- noch als u16/u32-Folge vor (`display.bin` und `display.bin.bak`);
   die Strings `pq_picturemode`, `vivid`, `energy_saving` fehlen.
4. Die Firmware kann keine Dateien lesen; die INI wird von `libvideo.so` (`_GLOBAL__sub_I_CDeviceControl.cpp`
   @`0xAE14`, Map Name → `PictureMode`) und `PQControl` verarbeitet - auf der ARM-Seite.
5. Im Stock-elog (zwei Bootläufe) werden gesendet: `SetWhiteBalance` 2×, `SetTNR` 2×, `SetSNR` 2×, `SetDCI` 2×,
   `SetBlackExtension` 2×, `SetPictureMode` 2×, `SetVideoRange` 1×, `SetSource` 1×, `SetBacklightWorkMode` 2× -
   **`SetBrightness`/`SetContrast`/`SetSaturation`/`SetHue`/`SetSharpness` 0×**. Stock lässt die fünf Regler in
   diesen Fenstern im „nicht angewendet"-Zustand (Register 0, I1-Korrektur 13:05).

Was der Wechsel im TFD **auslösen kann** - die einzige Stelle, an der `UI_PictureModes` im Datenbestand vorkommt
(`tools/tse_dump.py --all`, Scratchpad-Auszug):

| Modul | Gruppe | States nach `0x3001` |
|---|---|---|
| `MP_CM_VPROC_0x0030` (ColorManagementFW, handle `0x49001`) | `ProjectID_0x0030` (type 2 project) | State 0/1 = {Vivid, Standard, Mild, Home, Sports, Shop, Animation, Graphic, Expert_1/2} je nach Farbraum-Attribut `0x44`; State 2 = {Game, Calibrated, Calibrated_Dark, Computer, Cinema, HDR} |

Kein Modul der Gruppe `V_INCAP` (22 Module) hängt an `0x3001`. Für **HDMI** schreibt der Moduswechsel aber nur
`V_INCAP` (§1.1) - statisch also **kein Registerwechsel** im HDMI-Betrieb. Ob die CM-Tabelle für VidDec über
type 2/16 nachgezogen wird, ist offen (§1.1). `Prepare` (`sub_8B1887A4`) leitet aus `0x3001` nichts ab (S9 §3).

Die weiteren UI-Attribute `0x3004 UI_SetPictures`, `0x3005 UI_SetPro`, `0x3008 UI_AdvPictures` werden von keinem
Code als `lui`-Konstante gebaut (`pq-q91`); nur `0x3013 UI_TNR` (in `sub_8B17D43C`, TNR-Treiber) und `0x3003
UI_ColorTemp` (`sub_8B152A5C`) kommen im Code vor. `UIvalueMapping` selbst vergleicht für Item-ID 0 gegen
`0x30010000/05/06` (k5-swreg-setter Z. 67-75) - Item 0 ist also der Bildmodus-Platz der UI-Tabelle
(Register `0x05001228[7:0]`, Nachführung `0x050012DC`), **aber niemand ruft `UIvalueMapping(0, …)`**.

**Antwort auf die Registerfrage:** `0x05001234/38/28` tragen nach `SetPictureMode` weiterhin das, was der letzte
Einzel-RPC hinterlassen hat (oder 0). Ein Preset-Wert kommt dort nur an, wenn ihn jemand per `SetBrightness` …
`SetSharpness` sendet.

---

## 2. Frage B - die `Get*`-Routinen (belegt, `pq-q80`)

| RPC | Handler | intern | Rückgabe | Quelle |
|---|---|---|---|---|
| `THal_Vp_GetBrightness` | `0x8B10A528` | `sub_8B149580` | **0** (konstant) | `thal_display_pq.cpp` 62/64, nur ENTER/LEAVE |
| `THal_Vp_GetContrast` | `0x8B10A584` | `sub_8B1496CC` | **0** | 82/84 |
| `THal_Vp_GetSaturation` | `0x8B10A5E0` | `sub_8B149818` | **0** | 102/104 |
| `THal_Vp_GetHue` | `0x8B10A63C` | `sub_8B149964` | **0** | 122/124 |
| `THal_Vp_GetSharpness` | `0x8B10A720` | `sub_8B149AB0` | **0** | 143/145 |
| `THal_Vp_GetDCI` | `0x8B10A77C` | `sub_8B149BFC` | **0** | 163/164 |
| `THal_Vp_GetBlackExtension` | `0x8B10A7D8` | `sub_8B149D48` | **0** | 182/183 |
| `THal_Vp_GetTNR` | `0x8B10A834` | `sub_8B149E94` | **0** | 201/202 |
| `THal_Vp_GetSNR` | `0x8B10A890` | `sub_8B149FE0` | **0** | 220/221 |
| `THal_Vp_GetPictureMode` | `0x8B10A8EC` | `sub_8B14A39C` | **`MEMORY[0x8B272974]`** - zuletzt gesetzter Modus | - |
| `THal_Vp_GetLowLatencyMode` | `0x8B10A978` | `sub_8B14A464` | **2** (konstant) | 299/300 |
| `THal_Vp_GetVideoRange` | `0x8B10AB88` | `sub_8B14A5A8` | **1** (konstant) | 317/318 |
| `THal_Vp_GetColorManagement` | `0x8B10A6AC` | `sub_8B14A150` | `memcpy(ziel, MEMORY[0x8B27296C], 12·n)`, n ≤ `MEMORY[0x8B272970]` | echter Zustand (vom Set-Pfad gefüllt) |
| `THal_Vp_GetSource` | `0x8B10A244` | `sub_8B14AC44` | **0** (konstant) | `thal_display_source.cpp` 41/42 |

Alle Handler setzen `*a2 = 1; a2[1] = result` - ein Rückgabewort, wie I1 es sah (`ok, 1 value(s)`). Die Null
kommt aus der Firmware, nicht aus der Übertragung; die Messung in I1 (SetContrast 80 → Register `0x50`,
GetContrast → 0) ist damit erklärt und **nicht** ein Fehler des Aufrufs.

Es gibt auch **nichts, was ein Get lesen könnte**: `THal_Vp_SetContrast` (`sub_8B149618`) legt nur die Nachricht
`{18, wert}` in die PQ-Warteschlange (`sub_8B106BEC`), `OnHalPqContrastChange` (`0x8B10C398`) ruft
`UIvalueMapping(4, wert)` und `PQ-Treiberobjekt->vt[+12](0, wert)` - keine Zustandsvariable in
`thal_display_pq.cpp`. Der einzige PQ-Zustand dieser Datei ist der Block `0x8B272948…0x8B27297F`, den
`sub_8B149490` bei `THal_Vp_Init` (Handler `sub_8B109F04`) nullt und in dem er `0x8B272974 = 1` setzt.

### 2.2 Folge für den Startwert

Nach jedem `THal_Vp_Init` meldet `GetPictureMode` **1** (Standard), und das erste `SetPictureMode 1` der
Init-Sequenz ist ein No-op (LEAVE Zeile 266) - genau wie bei Stock. `app dump_para → picture_mode:1`
(doku/98) zeigt dasselbe Feld `this+216`.

---

## 3. Frage D - `GetVideoRange` und `GetPictureMode`

- **`GetPictureMode`: ja, mit echter Semantik** - der zuletzt erfolgreich gesetzte Wert (auch 14/15 oder ein
  abgelehnter Wert ≥ 16 stehen dort, weil `sub_8B14A284` vor dem Speichern nicht prüft). Die ARM-Seite hat
  dasselbe noch einmal: `libhaldisplay.so` speichert `dword_11438` beim Set und liest es beim Get
  (`THal_Vp_GetPictureMode @0x71C8`), fragt die Firmware also nie.
- **`GetVideoRange`: nein.** Rückgabe konstant 1. `SetVideoRange` (`sub_8B14A4FC`) geht über `sub_8B12BB1C`
  (Identität) → `AppTopSetColorRange` (Nachricht 7) → `this+212` (Range-Override im Filter, S9 §2.1); diese Zelle
  liest kein Get zurück. Auch hier cached `libhaldisplay.so` (`dword_1143C`) lokal.

---

## 4. Frage C - Empfehlung für `h713_hdmirx`

**Kern:** Es gibt nach `SetPictureMode` **keinen neuen Stand der fünf Controls, den der Treiber nachziehen
müsste** - die Firmware ändert Helligkeit, Kontrast, Sättigung, Farbton, Schärfe, TNR, SNR, DCI und
Schwarzdehnung dabei nicht (§1.4). Die Sorge aus dem Treiberkommentar („SetPictureMode setzt die fünf Werte
hinter dem Rücken des Treibers neu") ist statisch widerlegt; die Controls bleiben nach einem Moduswechsel wahr.

Daraus:

1. **Keine Get-RPCs** für die neun Regler - sie liefern 0 (§2). Einzige brauchbare Rückfrage ist
   `GetPictureMode`, und die ist entbehrlich, weil der Treiber den Wert selbst gesetzt hat.
2. **`Picture Mode` als Menü mit den Firmware-Namen** (0…13, §1.2), Nummer 1:1 an `THal_Vp_SetPictureMode`.
   Vorgabe 1 (Standard) = Init-Sequenz = Firmware-Startwert. Wenn man nur die INI-Modi anbieten will:
   `Standard 1, Cinema 7, Vivid 0, Game 3, Computer 6, HDR 12`. Für `energy_saving` und `custom` gibt es
   **keinen** Firmware-Modus (die INI-Zeile `energy_saving` unterscheidet sich von `standard` nur im
   Backlight 80; `custom` ist nur eine Datenbankzeile).
3. **Wer die INI-Presets (Stock-Oberflächenverhalten) will, sendet sie selbst** - als Userspace-Regel in
   `hy310-tv`/`hy310-pq` (nach `set mode` die neun Controls aus der INI-Zeile setzen), nicht im Kernel. Damit
   bleibt der Treiber ein 1:1-RPC-Abbild ohne eigene Bildpolitik, und `ctl list` zeigt ohne Sync-Flag die
   Wahrheit. Falls es doch im Kernel sein soll: Tabelle unten, ohne erneutes Senden des Modus.
4. **Vor der Freigabe von 3 (Game) und 6 (Computer) am Board messen** (§5): beide lösen `UpdateWce` und den
   MemoryAgent-Sonderfall aus.

**Tabelle HDMI (Eingang `[HDMI1]` = `[HDMI2]` = `[HDMI3]` in der INI), Schlüssel = Firmware-Nummer:**

| Firmware-N | Modus | brightness | contrast | saturation | hue | sharpness | tnr | snr | dci | black_ext | (colortemp, gamma, backlight, dyn.) |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | standard | 50 | 50 | 50 | 50 | 50 | 2 | 1 | 2 | 1 | 0, 3, 100, 0 |
| 7 | cinema | 50 | 45 | 45 | 50 | 40 | 2 | 1 | 0 | 0 | 2, 3, 100, 0 |
| 0 | vivid | 50 | 55 | 60 | 50 | 60 | 2 | 1 | 3 | 1 | 1, 3, 100, 0 |
| 3 | game | 50 | 50 | 50 | 50 | 50 | 1 | 0 | 0 | 0 | 0, 3, 100, 0 |
| 6 | computer | 50 | 50 | 50 | 50 | **0** | 0 | 0 | 0 | 0 | 0, 3, 100, 0 |
| 12 | hdr | 50 | 50 | 50 | 50 | 50 | 1 | 1 | 0 | 0 | 2, 3, 100, 0 |
| (1) | energy_saving | 50 | 50 | 50 | 50 | 50 | 2 | 1 | 2 | 1 | 0, 3, **80**, 0 |
| (1) | custom (nur `tvpq.db`) | 50 | 50 | 50 | 50 | 50 | 0 | 0 | 0 | 0 | 0, 3, 100, 0 |

Herkunft der Werte: `re/vendor/HY310/extracted/vendor_a/etc/tvconfig/pq_picturemode.ini` (Zeilen `[HDMI1]`),
Kreuzprobe `tvpq.db Picture_Mode` (wertgleich, doku/81 §5). Herkunft der Nummern: §1.2 (Firmware-Tabelle +
TSE-Namen; Zuordnung INI-Name ↔ TSE-Name über Namensgleichheit, für `standard ↔ 1` zusätzlich elog + XML).
Nicht enthalten: Mild, Calibrated(_Dark), Home, Sports, Shop, Animation, Graphic - dafür hat der Hersteller
keine Werte hinterlegt. Die Stufe Benutzerwert → RPC-Argument bleibt wie in doku/81 §2.1 ungemessen (1:1
angenommen; für die vorkommenden Werte folgenlos).

---

## 5. Offen und Messvorschlag (Board, später)

1. **Registerprobe:** `SetPictureMode 0 / 7 / 3 / 6 / 1` mit Abzug `0x05001228…0x05001280` und
   `0x05140000…0x051405FC` davor/danach. Erwartung nach §1.4: PQ-Block unverändert; bei 3/6 evtl. Änderungen im
   WCE/Scaler-Bereich (Window-Manager) und beim MemoryAgent. elog Stufe 5: `pic mode:%d`,
   `group name[V_INCAP]`, `SetLowLatency low_latency:%d`, `Refresh b_by_vs :0`.
2. **Bild:** Foto je Modus. Erwartung: HDMI ohne sichtbare Änderung außer eventuell bei 3/6 (Latenz/WCE), da
   die CM-Tabelle für HDMI nicht neu geschrieben wird.
3. **`GetPictureMode`** nach jedem Set → muss den gesetzten Wert liefern (auch 15 und ein abgelehntes 16).
4. **Offen (statisch nicht aufgelöst):** Bedeutung von `WriteModules` type 2 vs. 16 für VidDec; Wirkung des
   MemoryAgent-Sonderfalls `+4 == 6`; die ARM-`PQControl`-Bibliothek (Name → Nummer) fehlt im Auszug.

---

## Anhang - erzeugte Dateien

| Datei | Inhalt |
|---|---|
| `analyse/ida/ida_q80.py` | Strings/Namen zu PictureMode, Kette `sub_8B14A284`/`sub_8B12BB68`/`sub_8B1098BC`, alle 14 `Get*`-Handler + interne Funktionen |
| `ida_q81.py` | `def_8B108928` („not supported"), `sub_8B149490` (PQ-Init, Modus 1), `DbgDumpPara`, AppTop-Wrapper 7/3/6, app-Shell-Tabelle |
| `ida_q82.py` | Funktionen um `IsNeedToUpdateTfdForNewPicMode` mit Rohdisassembly, Mapper `sub_8B12C4C0`/`sub_8B12C4EC`, `OnCommonEvent` |
| `ida_q83.py` | `sub_8B1ABD18` (WindowManager-Singleton), `sub_8B107B04`, `sub_8B1071B8` |
| `ida_q84.py` | **Tabelle `dword_8B1F2120`**, Aufrufer `UIvalueMapping`/`TBrightness::Write`, `THal_Vp_Init`-Handler |
| `ida_q85.py` | WindowManager-Ctor + vtable `0x8B208D40` (Slots +8…+48), MemoryAgent-Singleton |
| `ida_q86.py` | `MemoryAgent_GetOrCreate`, `TFDHandler::WriteModules(type)`/`(name)` |
| `ida_q87.py` | MemoryAgent-vtable `0x8B1FBC30`, Slot +16 |
| `ida_q88.py` | **ARM:** `libhaldisplay.so` (`THal_Vp_Set/GetPictureMode`, `Set/GetVideoRange`), `libvideo.so` (Map Name → PictureMode) - eigene idalib-DBs im Scratchpad |
| `ida_q89.py` | `SetVideoRange`/`SetLowLatencyMode` intern, Leser von MemoryAgent+4, `OnHalPqContrastChange` |
| `ida_q90.py` | `libvideo.so`: Importe (`THal_*`, `PQControl`), Nutzer der Map |
| `ida_q91.py` | `lui`-Scan nach den UI-Attributen `0x3001…0x3015` im Code, Datenwörter |
| `ida_q92.py` | Rohdisassembly `OnCommonEvent` Typ 8 (Argument von `SetLowLatency`), TFDHandler-vtable |
| `re/captures/weltneuheit/pq-q80…q92-20260908.log`, `pq-q88-arm-…`, `pq-q90-libvideo-…` | Rohausgaben |
