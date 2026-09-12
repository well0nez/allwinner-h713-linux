# S9 — RE: TFD-Attribute, `VINCAP_ICSC` und der RGB-Ring nach dem VidDec-Neubau

Agent: RE (MIPS/IDA, rein statisch). 08.09.2026, 00:10–01:10. Board und Zuspieler nicht angefasst,
nichts unter `mainline/patches/` geändert.

Datenbank: Arbeitskopie `analyse/ida/db-tfd/display.bin.i64`. Skripte `analyse/ida/ida_q60.py` … `ida_q72.py`
plus drei TSE-Parser (`analyse/ida/tse_dict_s9.py`, `tse_cstab_s9.py`, `tse_twofilter_s9.py`, bauen auf
`tools/tse_dump.py` auf). Rohausgaben `re/captures/weltneuheit/tfd-*-20260908.log` (Liste in §9).
Beide idalib-Aufrufe funktionieren (`PYTHONPATH=/opt/ida-pro-9.1/idalib/python python3` und
`~/.idapro/idalib-venv/bin/python`); `ida_struct` gibt es in 9.1 nicht mehr, Strukturen über `ida_typeinf`.

Adressen: MIPS-Code `0x8Bxxxxxx`; MMIO ARM-physisch = MIPS − `0xB5000000`.

---

## 0. Kurzfassung

Die Hypothese trifft im Kern zu, mit einer Korrektur bei Attribut 1:

* **Der Auslöser des Fehlers ist der VidDec-Signalpfad selbst, nicht ein Fehler im Neubau.** Jedes
  Signalereignis, dessen erste sieben SignalInfo-Felder sich ändern, baut einen TFD-Filter **aus der
  SignalInfo dieses Ereignisses** (`sub_8B1078EC`), schreibt ihn in den persistenten Basisfilter des
  TFDManagers (letzter Schreiber gewinnt, ein Wert je Attribut) und führt die TSE-Module aus.
* Aus `Signal_Format` (Attr 29) und `Signal_ColorSpace` (Attr 68) leitet `GetColorSpaceConfig` über eine
  achtzeilige Tabelle in `database.TSE` die Attribute 101–104 ab: **YUV-Formate → `VINCAP_ICSC = BYPASS`,
  RGB-Formate → `VINCAP_ICSC = <Signal_ColorSpace>`.** Der VidDec-Descriptor mit `color_format = 0`
  (yuv420_888) ergibt zwangsläufig BYPASS; das Modul `MP_ICSC_VINCAP` schreibt dann `0x06940824 = 0x8000000B`
  (Bit 31 = **Bypass**), und die Aufnahme legt rohes RGB in den Ring.
* Stock endet bei BT709, weil dort **das HDMI-RX-Signalereignis (`Set Valid Signal … signal_format:11`) das
  letzte Ereignis ist**; es baut den Filter aus der HDMI-SignalInfo (`RGB_888`, `Full_Range`) und schreibt
  State 2 (`0x0000000B`, Matrix rechnet). Alle VidDec-Auswertungen davor haben BYPASS geschrieben —
  im Stock-LIVE-Log nachlesbar.
* Ein firmware-eigener Weg ohne Quellenwechsel existiert: `THal_Vp_SetVideoRange` mit einem **anderen** Wert
  als dem gespeicherten löst genau die Doppelauswertung „erst VidDec-Cache, dann HDMI-Cache" aus, deren
  letzter Schritt BT709 setzt. Details und Fallstricke in §6.

---

## 1. Die Bausteine (belegt)

### 1.1 Objekte und vtables

| Klasse | vtable | wichtige Slots (Offset → Funktion) |
|---|---|---|
| `TFDHandler` (typeinfo `_ZTI10TFDHandler`) | `0x8b202ea8` | +32 `sub_8B18737C` GetColorSpaceConfig · +48 `sub_8B186D28` WriteModule · +52 `sub_8B186EBC` WriteModules(type) · +56 `sub_8B186F94` WriteModules(name) · +104 `sub_8B186ACC` Filter aus Basisfilter kopieren · +108 `sub_8B186AE0` SetAttr → Basisfilter · +116 `sub_8B186B40` Apply(filter) · +120 `sub_8B1887A4` Prepare(filter) (leitet Attribute ab) · +140 `sub_8B18800C` `_LoadTFDColorSpaceTable` |
| `TTFDManager` | `0x8b203c3c` | +32 `sub_8B18FCD8` filter.CopyFrom(Basisfilter `mgr+92`) · +40 `sub_8B190028` **DumpFilter** (`TFDManager.cpp 261/267`) · +44 `sub_8B190E24` WriteGroup(name) · +48 `sub_8B1910D4` WriteGroup(type) · +80 `sub_8B190174` Gruppenmitgliedschaft · +84 `sub_8B18FFC0` SetAttr → `mgr+92`.SetItem |
| `TTFDFilter` | `0x8b204420` | +12 `sub_8B196C8C` SetItem(packed) · +16 `sub_8B196DD0` SetItem(type,val) · +20 `sub_8B196C20` GetValue(type) · +24 Count · +28 GetEntry(i) · +36 `sub_8B197014` CopyFrom |
| `TTFDAttrProp` | `0x8b20435c` | +12 `sub_8B19506C` Match(filter) |
| `TTFDModule` | `0x8b20494c` | +36 `sub_8B197D70` GetFilteredState · +44 `sub_8B1979E8` SendTo (`TFDModule.cpp 365/370/374/384`) |

### 1.2 Filter-Semantik: ein Wert je Attribut, Ersetzen statt Anhängen

`TTFDFilter::SetItem(type, val)` (`sub_8B196DD0`) hält eine sortierte Liste aus `(u16 type, u32 val)`.
Existiert der Typ, wird **ersetzt**:

```c
    v10 = *v7;                    // vorhandener type
    if ( v10 == a2 ) goto LABEL_17;
    ...
LABEL_17:
        *((_DWORD *)v7 + 1) = a3; // Wert ueberschreiben
```

`Match` (`sub_8B19506C`) fragt je Bedingung **einen** Wert ab (`filter->GetValue(type)`, Slot +20) und prüft,
ob er in der Werteliste des States liegt. `GetFilteredState` (`sub_8B197D70`) verlangt **genau einen**
passenden State; bei zweien: `"Conflict %s : %s between state 0x%04X and state 0x%04X"`, bei keinem:
`"Cannot find appropriate state in module:%s."` — in beiden Fällen bleiben die Register unverändert.
`SendTo` (`sub_8B1979E8`) überspringt einen State, der dem zuletzt gesendeten gleicht (`[IGNORED]`),
außer das Modul ist `always`.

Folge: Die Mehrfachwerte im sortierten Log `stock-live-norm.txt` (HDMI1 **und** MPEG1, RGB_888 **und**
YUV420_888 …) sind eine Vereinigung über viele Dumps, keine Eigenschaft eines Filters. Im chronologischen
Log (`stock-clean.txt`, LIVE-Rohdatei) hat jeder Dump je Attribut genau einen Wert.

### 1.3 Attribut-Wörterbuch (aus `database.TSE`)

Datensatzformat: Attributname `u16 attr, u8 len, name\0` (ab `0x39b00`), Wert `u16 val, u16 attr, u8 len,
name\0` (ab `0x3a200`); Bit 15 im Wert = Gruppe. Vollständig in `tfd-tse-woerterbuch-20260908.log`. Auszug:

| Attr | Name | Werte |
|---|---|---|
| 1 | Signal_Channel | `0x010000` MPEG1, `0x010011` HDMI1, `0x010013..15` HDMI2..4 |
| 29 (0x1d) | Signal_Format | `0x1d0000` YUV422_101010, `01` RGB_101010, `02` RGB_121212, `03` YUV444_888, `04` YUV444_101010, `05` YUV444_121212, `06` YUV422_888, `07` **RGB_888**, `08` YUV422_121212, `09` **YUV420_888**, `0a` YUV420_101010, `0b` YUV420_121212; Gruppen `0x1d8000` RGB, `8001` YUV444, `8002` YUV422, `8003` YUV420, `8004` YUV |
| 58 (0x3a) | Signal_Range | `0x3a0000` Limit_Range, `0x3a0001` Full_Range |
| 68 (0x44) | Signal_ColorSpace | `0x440000` BT709, `01` BT601, `02` BT2020_NCLYCC, `03` xvYCC, `04` RGB, `09` BT2020_CLYCC |
| 101–104 (0x65–0x68) | VINCAP_ICSC, VPROC_CSC1, VPROC_ICSC2, VPROC_CSC3 | je `..0000` **BYPASS**, `..0001` BT601, `..0002` **BT709**, `..0003` BT2020NCLYCC |

Damit korrigiert sich die Namensvergabe in `tools/tse_dump.py` (`0x1d` ist Signal_Format, nicht
„colorspace"; `0x44` ist Signal_ColorSpace, nicht „picmode").

---

## 2. Frage A — Wer setzt die Attribute 1, 29, 58, 68?

### 2.1 Die Funktion: `sub_8B1078EC(this, sig)` (belegt)

```c
int sub_8B1078EC(AppTopProjector *this, SignalInfo *sig)
{
  tfd->vt[+104](tfd, filter);                          // filter := Kopie des Basisfilters (mgr+92)
  src = this->hdmi_cache.source_id /* +224 */; if (!src) src = 3;
  filter->SetItem( sub_8B12C490(src) );                // Attr 1  Signal_Channel  (aus this+224, NICHT sig)
  filter->SetItem( sub_8B12C098(sig->color_format) );  // Attr 29 Signal_Format   (sig +16)
  filter->SetItem( sig->color_space );                 // Attr 68 Signal_ColorSpace (sig +20, schon 0x4400xx)
  filter->SetItem( sig->frame_rate );                  // Attr 3  Signal_Framerate  (sig +8)
  filter->SetItem( sub_8B12C510(sig->hdr_scheme) );    // Attr 63 EnhancedVideoMode (sig +24)
  filter->SetItem( sub_8B12C4C0(this->pic_mode /*+216*/) );   // Attr 0x3001 UI_PictureModes
  filter->SetItem( sub_8B12C4EC() );                   // Attr 53 LowLatency
  r = this->range_override /*+212*/; if (!r) r = sub_8B1076F4(sig);
  filter->SetItem( sub_8B12C4FC(r) );                  // Attr 58 Signal_Range (2 -> Full, sonst Limit)
  if (sig->source_id == 1) {                           // VidDec
      filter->SetItem( (!this->seamless /*+204*/ || sig->b_interlace) ? sig->signal_id : 0x2007c ); // Attr 2
      filter->SetItem( sig->compress_mode /* +40 */ ); // Attr 78 Signal_COM_Ratiio
  } else
      filter->SetItem( sig->signal_id );               // Attr 2 Signal_Mode
  return tfd->vt[+116](tfd, filter);                   // Apply: jeden Eintrag -> SetAttr -> Basisfilter
}
```

Mapper (Tabellen in `tfd-q61-mapper-20260908.log`):

* `sub_8B12C490` (Quelle → Attr 1, Tabelle `dword_8B1F2158`): 1→MPEG1 `0x010000`, 2→`0x010012`, **3→HDMI1
  `0x010011`**, 4..6→HDMI2..4, 7..9→CVBS1..3, 10→TV; sonst `0x010001` NONE.
* `sub_8B12C098` (kHalColorFormat → Attr 29, Tabelle `dword_8B1F218C`, 1-basiert, 13 Einträge):
  hal 1→`1d000a`, 2→`1d000a`, 3→`1d000b`, 4→`1d0006` YUV422_888, 5→`1d0009`, 6→`1d0000`, 7→`1d0008`,
  8→`1d0003`, 9→`1d0004`, 10→`1d0005`, **11→`1d0007` RGB_888**, 12→`1d0001`, 13→`1d0002`;
  **hal 0 und alles ≥ 14 → Default `0x1d0009` YUV420_888.**
* `sub_8B12C4FC` (Range → Attr 58): `2 → 0x3a0001 Full_Range`, sonst `0x3a0000 Limit_Range`.
* `sub_8B1076F4(sig)`: `DeviceManager->GetStatus(sig->source_id)`; Status 3 (VideoDec) → `sig+80`
  (`video_dec.b_full_range`), Status 1 (HDMI) → `sig+36` (`hdmi.b_full_range`, Union-Teil der SignalInfo —
  die Feldnamen stammen aus `VidDec_dump_signal_info`), Ergebnis 2 = voll, 1 = begrenzt.

### 2.2 Welche SignalInfo? Die des auslösenden Ereignisses (belegt auf Maschinenebene)

`AppTopProjector_HandleSignalEvent(this, cache, &sig)` (`0x8b108644`) wird aus `ThreadMain` zweimal gerufen:

```c
if ( sig.source_id == 1 ) { ... EnterWaitingWindowsReady(this,&sig);
    AppTopProjector_HandleSignalEvent(this, this+32  /* VidDec-Cache */, &sig); ... memcpy(this+32,&sig) }
else {
    AppTopProjector_HandleSignalEvent(this, this+224 /* HDMI-Cache  */, &sig);
    AppTopProjector_ConfigSourceRouting(this,&sig); ... memcpy(this+224,&sig) }
```

Hex-Rays zeigt dort `sub_8B1078EC(a1)` mit nur einem Argument; die Disassembly klärt es:

```
8b108650  move $s0, $a2        ; s0 = &sig (neu)
8b10867c  move $a1, $s0        ; a1 = &sig
8b108684  jal  sub_8B1085CC    ; Vergleich cache vs. sig  (schreibt $a1 nicht: nur $a2/$v0/$v1)
...
8b1086f8  jal  sub_8B1078EC    ; $a1 ist unveraendert = &sig   (Nicht-VidDec-Zweig)
8b1086fc  move $a0, $s2
...
8b108788  jal  sub_8B1078EC    ; ebenso im VidDec-Zweig
8b10878c  move $a0, $s2
```

GCC verlässt sich per IPA-RA darauf, dass der Blattaufruf `sub_8B1085CC` `$a1` nicht zerstört. **Der Filter
wird also aus der neuen SignalInfo des Ereignisses gebaut** — beim VidDec-Ereignis aus der VidDec-SignalInfo
(`source_id 1`, `color_format` aus Descriptor idx16), beim HDMI-Ereignis aus der HDMI-SignalInfo
(`source_id 3`, `color_format 11`). Die Hypothese stimmt für Attr 29/58/68.

**Korrektur zu Attr 1:** `Signal_Channel` kommt **nicht** aus `sig->source_id`, sondern aus dem ersten Wort des
HDMI-Caches `this+224` (das `source_id`-Feld der zuletzt gesehenen Nicht-VidDec-SignalInfo; `ThreadMain`
setzt es beim Quellenwechsel auf 0 bzw. die neue Quelle, `0 → 3`). Deshalb steht in allen Dumps nach
`AppTopSetSource(3)` `HDMI1`, auch bei VidDec-Ereignissen. Die frühen Dumps mit `MPEG1` (Stock, t = 0, sechs
Stück vor `WriteModules : group type[16]`) stammen aus einem anderen Aufbaupfad (Initialisierung/`tcd3`
`write_cvd_setting` `sub_8B1452A0` baut eigene Filter) — **vermutet**, nicht verfolgt.

### 2.3 Wo im Ablauf

1. `sub_8B1085CC(cache, sig)` vergleicht `source_id, signal_id, frame_rate, b_interlace, color_format,
   color_space, hdr_scheme`. Nur bei Änderung: `sub_8B1078EC` (Filter + Persistieren) und — wenn Flag
   `this+221` („tfd update", `app tfd_on/off`) gesetzt — `sub_8B107B04(this, &sig, 16)`.
2. `sub_8B107B04` ruft `sub_8B1078EC` **nochmals** und dann je nach `DeviceManager->GetStatus(sig->source_id)`:
   Status 1 (HDMI) → `WriteModules(filter, "V_INCAP")`; Status 0 → Gruppen `ADC`, `TCD`, `V_INCAP`; sonst
   (VidDec, Status 3) → `WriteModules(filter, type 16)`. Passt zum Log: HDMI-Ereignis `group name[V_INCAP]`,
   VidDec-Ereignis `group type[16]`.
3. `WriteModules` (Slot +52/+56): `Prepare(filter)` (Slot +120, leitet Attr 10/34/35/…, **101–104**, 63… ab
   und schreibt sie per `SetItem` in den Filter) → `DumpFilter` → `TFDManager::WriteGroup` → je Modul
   `GetFilteredState` → `SendTo` → RegTableFW-Blob schreibt Register.
4. `EnterWaitingWindowsReady` / `EnterWaitingPipeLineReady` / `EnterIdle` fassen TFD **nicht** an (nur
   Zustand, Timer, `PushSignalToMemoryAgent`). `UpdateWce` ist der Window-Manager-Thread (SignalInfo-Kopie
   per `sub_8B10711C` an Singleton `0x8B253574`), unabhängig von TFD.
5. Weitere Aufrufer von `sub_8B107B04`: `AppTopProjector_Ctor`, `ApplyNewSource` (Quellenwechsel, einmalig mit
   der Default-SignalInfo des DisplaySourceControllers), `OnCommonEvent` Typ 3/7/8 (siehe §6).

---

## 3. Frage B — Wie werden 101 `VINCAP_ICSC`, 102, 103, 104 bestimmt?

### 3.1 Regel (belegt): `GetColorSpaceConfig` `0x8b18737c` (`TFDHandler.cpp 322`)

Liest aus dem Filter **nur** Attr 29 (`v26[0] == 29 → v8`) und Attr 68 (`== 0x44 → v9`) und sucht in der
Tabelle `tse:table:colorspace_config_mp` / `tse:group:mp_color_space_config` (geladen von
`_LoadTFDColorSpaceTable` `0x8b18800c`, `TFDHandler.cpp 1105`, 24-Byte-Zeilen `[fmt, cs, 101, 102, 103, 104]`)
die erste Zeile, deren `fmt` und `cs` passen; Werte mit Bit 15 sind Gruppen und werden über
`TFDManager` Slot +80 (Mitgliedsliste) geprüft. Treffer → vier Werte werden per `SetItem` in den Filter
geschrieben (`Prepare`, `sub_8B1887A4`). Kein Treffer → `"Get the config of color space failed!"`, **Attribute
101–104 bleiben, wie sie im Basisfilter standen.**

Die Tabelle steht in `database.TSE` ab `0x40db2` (Rohsuche nach `0065xxxx 0066xxxx 0067xxxx 0068xxxx`,
`tfd-farbraumtabelle-20260908.log`), acht Zeilen:

| Signal_Format | Signal_ColorSpace | 101 VINCAP_ICSC | 102 VPROC_CSC1 | 103 VPROC_ICSC2 | 104 VPROC_CSC3 |
|---|---|---|---|---|---|
| YUV (`0x1d8004`) | BT601 | **BYPASS** | BT601 | BT709 | BT709 |
| YUV | BT709 | **BYPASS** | BT709 | BT709 | BT709 |
| YUV | BT2020_NCLYCC | **BYPASS** | BT2020NCLYCC | BT709 | BT709 |
| YUV | BT2020_CLYCC | **BYPASS** | BT2020NCLYCC | BT709 | BT709 |
| RGB (`0x1d8000`) | BT601 | BT601 | BT601 | BT709 | BT709 |
| RGB | BT709 | **BT709** | BT709 | BT709 | BT709 |
| RGB | BT2020_NCLYCC | BT2020NCLYCC | BT2020NCLYCC | BT709 | BT709 |
| RGB | BT2020_CLYCC | BT2020NCLYCC | BT2020NCLYCC | BT709 | BT709 |

Kurzregel: **YUV-Eingang → Eingangswandler aus, RGB-Eingang → Eingangswandler nach Signal_ColorSpace;
CSC1 folgt immer Signal_ColorSpace; ICSC2/CSC3 immer BT709.** `Signal_Range` und `Signal_Channel` spielen
für 101–104 keine Rolle. Für `Signal_ColorSpace = xvYCC` oder `RGB` gibt es keine Zeile.

### 3.2 Die Modulzustände (belegt, `hdmi-source4.txt`, Wörterbuch angewendet)

`MP_ICSC_VINCAP` (0x500d, Gruppe V_INCAP, 4 States, kein `always`):

| State | Signal_Format | Signal_ColorSpace | VINCAP_ICSC | `0x06940824` | Matrix `0x834/838/83C/840/844` |
|---|---|---|---|---|---|
| 0 | alle 9 YUV-Formate | BT709, BT601, BT2020_NCLYCC, BT2020_CLYCC | **BYPASS** | **`0x8000000B`** | BT709-Koeffizienten |
| 1 | RGB_888/101010/121212 | BT601 | BT601 | `0x0000000B` | BT601 |
| 2 | RGB_888/101010/121212 | BT709 | **BT709** | **`0x0000000B`** | BT709 (identisch zu State 0) |
| 3 | RGB_888/101010/121212 | BT2020_NCLYCC | BT2020NCLYCC | `0x0000000B` | BT2020 |

`MP_CSC1_VPROC` (0xf011) hängt nur an 102: BT709→State 0, BT601→1, BT2020→2, BYPASS→3 (`0x0514016C`
Bit 31 = 1 nur in State 3). `MP_ICSC2_VPROC` (0xf012) nur an 103: BT709→State 0, BYPASS→State 1
(`0x05140194` Bit 31). 104 wird von `MP_CSC_DPA` (0xf023) benutzt. Attribut-Nutzerliste in
`tfd-attribut-nutzer-20260908.log`.

---

## 4. Frage C — Welche Register schreibt `MP_ICSC_VINCAP`?

Alle Schreibziele liegen im INCAP-Block (ARM-physisch; MIPS = +`0xB5000000`, also `0xBB9408xx`). Kein
Register in `0x06E0xxxx` oder `0x068Bxxxx` gehört zu diesem Modul (die RegTable enthält nur `0x069408xx`).

| Register | State 0 (BYPASS) | State 2 (BT709) | Bemerkung |
|---|---|---|---|
| `0x06940824` | `0x8000000B` | `0x0000000B` | **Bit 31 = 1 → Bypass, Bit 31 = 0 → Matrix rechnet.** Belegt über das Wörterbuch: der State mit `icsc_mode = 0x650000 = BYPASS` schreibt Bit 31; das beantwortet die in doku/84 §2.2 offen gelassene Polarität. Konsistent mit der Messung vom 07.09. (Bit 31 = 0 → YUV im Ring). |
| `0x06940800` | RMW Maske `0x0000FFFE` → `0x0C00` | gleich | |
| `0x06940828/082C` | 0 | 0 | |
| `0x06940830` | `0x02000200` | gleich | Offsets |
| `0x06940834…0x06940844` | `009405B9 / 0CD901B3 / 0F100417 / 0FA00C49 / 00000417` | identisch | RGB→YCbCr-BT709-Matrix; **nicht** diagnostisch, weil State 0 und 2 dieselben Werte schreiben |
| `0x06940848` | 0 | 0 | |

Diagnose am Gerät (nur lesen): `0x06940824` Bit 31 sagt, welcher State zuletzt geschrieben wurde. Zusätzlich
unterscheidet `MP_WB_VINCAP` (0x500c, hängt an Signal_Format **und** Signal_Range) die beiden Auswertungen:

| Register | HDMI-Auswertung (RGB_888, Full_Range → State 3) | VidDec-Auswertung (YUV420_888, Limit_Range → State 0) |
|---|---|---|
| `0x06940804` (Maske `0xFFFF0000`) | `0x036D0000` | `0x04000000` |
| `0x06940808` | `0x036D036D` | `0x04000400` |
| `0x0694080C` | `0x00400040` | `0x00000000` |
| `0x06940810` | `0x00000040` | `0x00000000` |

`CONVERT_422AND444` (`0x0694084C`) hat für `YUV420_888` **keinen** passenden State (State 0 verlangt
YUV422-Formate, State 1/2 RGB/YUV444) → bleibt beim vorherigen Wert (`0x04000C00` aus der HDMI-Auswertung).
Das erklärt den in K1 festgehaltenen Befund, dass `0x84C` sich nie ändert.

Vollständiger Modulvergleich beider Filter (auch die `Signal_Mode`-abhängigen Module wie TNR, SAR, CDDET,
MOVIE, SSR, die zwischen `1920_1080/60` und `DTV_1920_1080_P/30` umschalten und das auch bei Stock tun):
`tfd-zweifilter-vergleich-20260908.log`.

---

## 5. Frage D — `ConvertFrameInfo2SignalInfo` (`0x8b1471b0`)

Struktur `VidDec_FrameInfo` (144 B) aus der Datenbank: idx16 `+0x40 color_format`, idx17 `+0x44 color_space`,
**idx18 `+0x48 b_full_range`**, idx19–21 `color_primaries/transfer_characteristics/matrix_coefficients`
(werden von der Firmware **nicht** in die SignalInfo übernommen), idx23 `b_compress_en`, idx24 `hdr_scheme`.
`VidDec_SignalInfo` (172 B): `+0x10 color_format`, `+0x14 color_space`, `+0x50 b_full_range`, `+0x28 compress_mode`.

```c
signal_info_out->source_id   = 1;
signal_info_out->color_format = VidDec_MapColorFormat(frame->color_format);       // 0x8b12d2f0
signal_info_out->color_space  = sub_8B12C148(VidDec_MapColorSpace(frame->color_space)); // 0x4400xx
LOBYTE(signal_info_out->b_full_range) = frame->b_full_range != 0;
```

`VidDec_MapColorFormat` (Tabelle `unk_8B1F1C38`, 17 Paare): 0..13 → identisch, **14 → 11**, 15 → 15,
16 → 14, sonst 0. Dann `sub_8B12C098` (§2.1). Ergebnis für Attr 29:

| Descriptor idx16 | Name (`off_8B1F516C`) | kHal | Attr 29 |
|---|---|---|---|
| 0 | yuv420_888 | 0 | YUV420_888 (Default-Zweig) |
| 1 / 2 / 3 | yuv420_1088 / _101010 / _121212 | 1/2/3 | YUV420_101010 / YUV420_101010 / YUV420_121212 |
| 4 | yuv422_888 | 4 | YUV422_888 |
| 5 | yuv422_1088 | 5 | YUV420_888 (Tabelleneintrag, kein 1088-Äquivalent) |
| 6 / 7 | yuv422_101010 / _121212 | 6/7 | YUV422_101010 / YUV422_121212 |
| 8 / 9 / 10 | yuv444_888 / _101010 / _121212 | 8/9/10 | YUV444_888 / _101010 / _121212 |
| **11** | **rgb_888** | 11 | **RGB_888 (`0x1d0007`)** |
| 12 / 13 | rgb_101010 / rgb_121212 | 12/13 | RGB_101010 / RGB_121212 |
| **14** | rgb_101010_p010_low | **11** | **RGB_888** |
| 15 / 16 / sonst | p010_high / detn_alpha / — | 15/14/0 | YUV420_888 (Default) |

`VidDec_MapColorSpace` (idx17): 0..5 → identisch (`bt601, bt709, bt2020_nclycc, bt2020_clycc, xvycc, rgb`),
sonst 0. `sub_8B12C148` (Tabelle `dword_8B1F2500`): 0→`0x440001` BT601, **1→`0x440000` BT709**, 2→`0x440002`,
3→`0x440009`, 4→`0x440003` xvYCC, 5→`0x440004` RGB, >5→`0x440001` BT601.

`b_full_range` (idx18) → `SignalInfo+0x50` → nur über `sub_8B1076F4` (Status 3) in Attr 58: `!= 0` → Full_Range.
Der Wert wird von `this+212` (SetVideoRange-Override, §6.1) übersteuert, sobald der ungleich 0 ist.
`compress_mode`: `b_compress_en == 0` → `0x4e0000` (Attr 78 `Signal_COM_Ratiio = PACK_1`).

Es gibt also einen Wert, der RGB_888 ergibt (idx16 = 11 oder 14) — mit den Nebenwirkungen aus §6.4.

---

## 6. Frage E — Wege zurück nach BT709 ohne Quellenwechsel

### 6.1 `THal_Vp_SetVideoRange` (RPC, FuncID `0x9817A1C1`) — der brauchbarste Weg (belegt, ungetestet)

Kette: `THal_Vp_SetVideoRange(a1)` `0x8b14a4fc` → `sub_8B12BB1C` (kopiert nur) → `AppTopSetColorRange`
`sub_8B1097B4` (Nachricht Typ 7, Wert `a1`) → `AppTopProjector_OnCommonEvent` `0x8b1089b4`:

```c
if ( v2 == 7 ) {
    v34 = a2[1];
    if ( *(_DWORD *)(a1 + 212) == v34 ) return 1;          // gleicher Wert: NICHTS passiert
    *(_DWORD *)(a1 + 212) = v34;
    if ( *(_BYTE *)(a1 + 221) ) {                            // tfd update an
        sub_8B107B04(a1, a1 + 32, 16);                       // 1. VidDec-Cache  -> YUV420_888 -> BYPASS
        if ( v5 >= 2 && *(_BYTE *)(a1 + 221) )               // v5 = HDMI-Cache.signal_id - 0x20002
            sub_8B107B04(a1, a1 + 224, 16);                  // 2. HDMI-Cache    -> RGB_888    -> BT709
    }
}
```

Die zweite Auswertung ist die letzte und schreibt `MP_ICSC_VINCAP` State 2 (`0x06940824 = 0x0000000B`),
dazu `MP_WB_VINCAP` State 3 und die anderen `V_INCAP`-Module nach HDMI-Filter (`sub_8B107B04` mit einer
Quelle vom Status 1 schreibt nur Gruppe `V_INCAP`).

Bedingungen und Nebenwirkungen:

* **Der Wert muss sich ändern.** `mainline/patches/kernel/0094` und `analyse/hdmi-seq` senden bereits
  `SetVideoRange 0`; ein erneutes `0` ist ein Leerlauf. Semantik von `this+212` in `sub_8B1078EC`:
  `0` = automatisch nach `b_full_range` der SignalInfo, `2` = Full_Range erzwingen, jeder andere Wert
  (z. B. `1`) = Limit_Range erzwingen. Ein Paar `2` → `0` stellt am Ende wieder Automatik her; jeder der
  beiden Aufrufe löst die Doppelauswertung aus.
* Der Override gilt für **beide** Auswertungen; solange er `2` ist, läuft auch die VidDec-Auswertung mit
  Full_Range (`MP_WB_VINCAP` State 1 statt 0 — für die INCAP unerheblich, weil die HDMI-Auswertung danach
  ohnehin State 3 schreibt).
* Voraussetzung `this+228 − 0x20002 ≥ 2`: der HDMI-Cache muss ein gültiges Signal tragen (nicht UNKNOW/NO_SIGNAL),
  d. h. es muss vorher ein HDMI-Signalereignis (`Set Valid Signal`) gegeben haben. Das ist nach Kaltstart der
  Fall (Ring ist dann YCbCr). `this+224` wird beim Quellenwechsel gelöscht.
* Der HDMI-Cache ist **alt**: nach einem Auflösungswechsel, den nur der Descriptor meldet, steht dort noch die
  frühere HDMI-Auflösung (`Signal_Mode`, `Signal_Framerate`). Für `MP_ICSC_VINCAP` egal (hängt nicht an
  Signal_Mode), aber die `Signal_Mode`-abhängigen `V_INCAP`-Module (`MODECHGCTRL` u. a., siehe Vergleichslog)
  werden mit den alten Werten geschrieben.
* Voraussetzung `this+221 != 0` (Default 1 aus dem Ctor; `app tfd_off` löscht es).
* Kein Fensterneubau, kein `SetSignalInfo`, kein Eingriff in Zustandsautomat oder MemoryAgent.

### 6.2 `app tfd_off` / `app tfd_on` (belegt)

Handler `sub_8B110834`/`sub_8B11084C` → `AppDbgEnableTfdUpate` `sub_8B1090CC(flag)` → setzt nur
`this+221`. Mit `tfd_off` überspringt `HandleSignalEvent` die Modulschreibvorgänge (`sub_8B107B04`), der
Filter wird aber weiter gebaut und persistiert. Das **verhindert** das Umschalten auf BYPASS beim nächsten
Descriptor-Ereignis (Register behalten den HDMI-Stand), **stellt aber nichts wieder her** und schaltet
zugleich alle signalabhängigen TSE-Module (Scaler-, NR-, Deinterlace-, Meter-States) bei Auflösungswechseln
ab. Außerdem greift jeder spätere PQ-Weg über `WriteModulesByUI` auf den Basisfilter zu, der nach dem
VidDec-Ereignis `YUV420_888` enthält, und schreibt dann doch BYPASS. Nicht empfohlen; höchstens als
Messhilfe („war es wirklich das VidDec-Ereignis?").

### 6.3 `app set_src` / `THal_Vp_SetSource` (belegt, bekannt)

`AppTopSetSource_wrapper` → Nachricht 0 → `ThreadMain`: `this+224 := 0/neu`, `this+228 := 0x20003`,
`ApplyNewSource` (einmal `sub_8B107B04` mit der Default-SignalInfo des DisplaySourceControllers), `EnterIdle`.
Löscht den HDMI-Cache, erzwingt neue Signalereignisse und den in doku/96 §5 beschriebenen zweiten,
fehlerhaften Neubau. Kein Weg „ohne Quellenwechsel".

### 6.4 Descriptor idx16 = 11 (rgb_888) oder 14 (belegt: nicht gangbar)

Ergibt zwar `Signal_Format = RGB_888` → `VINCAP_ICSC = BT709` → State 2, aber `color_format` läuft parallel
in die Fensterkette: `NRWinNode_ColorFormatConvert` (`0x8b1a2908`) bildet hal 11 auf AFBD-Format **4**
(gleich wie yuv444_888) und hal 14 auf Format 7 ab, nicht auf Format 2 (yuv422_888 = NV16). Der
AFBD-Leser würde also auf 4:4:4/RGB umgestellt, Strides und Geometrie folgen. Kein Descriptor-Wert liefert
gleichzeitig RGB für TFD und NV16 für den AFBD (NV16 gibt es nur über hal 4, und das ist YUV422_888 → BYPASS).
Zusätzlich würde `CONVERT_422AND444` mit RGB_888 zwei States (1 und 2) treffen, falls `V_INCAP_MP_Format`
nicht eindeutig ist. Passt zum Eintrag „Poke descriptor color_format" in `DEAD-ENDS.md`.

### 6.5 Descriptor idx17 = 5 (color_space_rgb) (vermutet, ungetestet)

`Signal_ColorSpace = RGB (0x440004)` hat keine Zeile in der Farbraumtabelle → `GetColorSpaceConfig` schlägt
fehl (`ERROR "Get the config of color space failed!"`), 101–104 bleiben auf den Werten der letzten
HDMI-Auswertung (BT709), und `MP_ICSC_VINCAP` findet **keinen** State (State 0 verlangt BT601/709/2020,
States 1–3 RGB-Formate) → `"Cannot find appropriate state"` → `0x06940824` bleibt `0x0000000B`.
Nebenwirkungen: `MP_CM_VPROC_0x0030`, `MP_DPA_VPROC_0X0030`, `MP_SSR_COLDEP` hängen ebenfalls an Attr 68 und
fänden ggf. keinen State; `SignalInfo.color_space` wird außerdem vom Window-Manager/HDR-Pfad gelesen (nicht
untersucht). Nur als Messidee notiert; ein Weg, der auf einem Tabellenfehltreffer beruht, ist kein
Stock-Verhalten.

### 6.6 Bildmodus (`app set_pm`, Nachricht 8) (belegt)

`OnCommonEvent` Typ 8 macht dieselbe Doppelauswertung (VidDec-Cache, dann HDMI-Cache) — aber nur, wenn
`sub_8B10890C(alt, neu)` einen „echten" Moduswechsel sieht, und mit allen PQ-Nebenwirkungen eines
Bildmoduswechsels. Typ 3 (`set_ll`, LowLatency) ebenso. Beide sind schlechtere Varianten von 6.1.

### 6.7 Der Stock-Weg: ein HDMI-Signalereignis nach dem Descriptor

Das, was Stock tatsächlich macht (§7): nach dem VidDec-Ereignis kommt vom MIPS-`hdmirx`-Modul
`THDMIRx_DisplayModuleCtx.cpp 927 Set Valid Signal` → `CallbackOfSignalChange` → HDMI-Auswertung. Wenn die
ARM-seitige Sequenz nach dem Veröffentlichen des neuen Descriptors die Schritte wiederholt, die dieses
Ereignis auslösen, ist die Reihenfolge wie bei Stock. Welcher RPC-Schritt aus `hdmi_seq`/`0094` das
`Set Valid Signal` erzeugt, war nicht Gegenstand dieser Analyse.

---

## 7. Frage F — Wie macht es Stock?

Aus der chronologischen LIVE-Rohdatei (`elog-stock-LIVE.bin`, Auszug `tfd-stock-live-chrono-tfd-20260908.log`,
Zeilennummern der entfärbten Datei):

| Zeile | Tick | Ereignis | Filter (Attr 1 / 29 / 58 / 68) | Ergebnis |
|---|---|---|---|---|
| 70–680 | 0 | sechs Init-Dumps | MPEG1 / YUV422_101010 / Limit / BT709 | 101 = BYPASS |
| 1045–1189 | 0 | `WriteModules : group type[16]` (VidDec-Ereignis) | HDMI1 / **YUV420_888** / Limit / BT709 | **`MP_ICSC_VINCAP State 0` gesendet** |
| 1582, 5174, 5381, 5678 | 1…17541 | `WriteModulesByUI` (PQ) | HDMI1 / YUV420_888 / Limit / BT709 | BYPASS (unverändert) |
| 5971–5973 | 17652 | `THal_Vp_SetVideoRange` → `AppTopSetColorRange` | — | keine neue Auswertung (Wert unverändert 0) |
| 6585–7071 | 24498 | `EnterWaitingWindowsReady`, VidDec `DTV_1920_1080_P` | HDMI1 / YUV420_888 / Limit / BT709 | BYPASS |
| 7991–8456 | 1157080 | `hal_source_id: 3`, `AppTopSetSource`, drei `WriteModulesByUI` | HDMI1 / YUV420_888 / Limit | BYPASS |
| 9332–9357 | 1157528…830 | `hdmirx` „new timing", `Conver signalID … 0x20057`, **`Set Valid Signal dwSignal:0x20057 signal_format:11 color_space:0x440000`**, `CallbackOfSignalChange` | | |
| 9379–9501 | 1157831…847 | **`WriteModules : group name[V_INCAP]`** | **HDMI1 / RGB_888 / Full_Range / BT709 → 101 = BT709** | **`MP_ICSC_VINCAP State 2` gesendet** |
| 9512–9547 | 1157847 | `SetSignalInfo`, `UpdateWce`, `CapWinNode color_format:4` | | |
| >9547 | | keine weitere TFD-Auswertung bis zum Ende des Mitschnitts | | |

Antwort: Stock endet bei BT709, **weil das HDMI-RX-Signalereignis die letzte Auswertung ist** und die
Firmware „letzter Schreiber gewinnt" spielt — nicht, weil Attribute aus der aktiven Quelle statt aus dem
Ereignis kämen (das gilt nur für Attr 1) und nicht durch einen eigenen HDMI-Pfad in der Tabelle: die
Regel ist für beide Quellen dieselbe, nur der Eingabewert `Signal_Format` unterscheidet sich (`11 → RGB_888`
gegen `0 → YUV420_888`). Zwischen dem VidDec-Ereignis (Tick 24498) und dem HDMI-Ereignis (Tick 1157830) lief
das Stock-Gerät lange mit BYPASS (~19 Minuten, falls die Ticks Millisekunden sind) — mit dem Bild des
Videodecoders, das YUV ist und keinen Wandler braucht. Der Descriptor blieb danach unverändert (`UpdateWce` bei Stock nur bei Init, doku/96 §5),
sodass BT709 stehen blieb.

**Nicht belegt:** wie Stock einen *Laufzeit*-Auflösungswechsel der HDMI-Quelle abwickelt (im Mitschnitt gibt
es keinen). Aus dem Code folgt nur: kämen dabei ein neuer Descriptor **und** ein neues `Set Valid Signal`,
entscheidet die Reihenfolge; das HDMI-Ereignis kommt vom `hdmirx`-Zustandsautomaten nach Timing-Erkennung
(`THDMIRx_Port.cpp 358/396` → `PortCtx` → `DisplayModuleCtx 927`), der Descriptor vom Decoder-Pfad.

---

## 8. Belegt / vermutet / offen

Belegt (Dekompilat + Disassembly + Datei): §1, §2.1–2.3 (bis auf den MPEG1-Ursprung), §3, §4, §5, §6.1–6.4,
§6.6, §7 (Chronologie).
Vermutet: Herkunft der sechs frühen `MPEG1`-Dumps (§2.2); Verhalten unter §6.5; Stock-Verhalten bei
Laufzeit-Auflösungswechsel (§7).
Nicht untersucht: der genaue RPC-Schritt, der `Set Valid Signal` auslöst (§6.7); die Nutzer von
`SignalInfo.color_space` außerhalb TFD; `special_format`-Ableitung (Slot +132/+28, Attr 10/34/35/69/70) —
die Stock-Dumps zeigen dafür bei beiden Ereignissen dieselben Werte (`V_INCAP_MP_Format = YUV422_888`).

Korrekturen an bestehender Doku, die sich ergeben:
* doku/84 §2.2: Polarität von `0x06940824` Bit 31 ist jetzt aus der Tabelle belegt: **1 = Bypass**.
* `tools/tse_dump.py` `ATTR_NAMES`: `0x1d` = Signal_Format, `0x44` = Signal_ColorSpace, `0x3a` = Signal_Range,
  `0x4e` = Signal_COM_Ratiio (die Werte aus dem Wörterbuch liegen in `tfd-tse-woerterbuch-20260908.log`).

---

## 9. Dateien

Skripte: `analyse/ida/ida_q60.py` (Entdeckung, Struct-Layouts), `q61` (Mapper-Tabellen, HandleSignalEvent),
`q62` (Aufrufstellen, ThreadMain, SetColorRange, set_src), `q63` (TFDHandler-vtable), `q64` (Disassembly
`$a1`-Nachweis), `q65` (app-Shell, OnCommonEvent, ApplyNewSource), `q66` (TFDFilter/TFDManager-vtables,
Prepare, AttrProp-Match), `q67` (SetItem, GetFilteredState, SendTo), `q68` (Slot +28, SetAttr-Store), `q69`
(tfd_on/off), `q70` (AppDbgEnableTfdUpate, EnterWaiting*), `q71` (SetVideoRange-Kette), `q72`
(Range-Mapping); `analyse/ida/tse_dict_s9.py`, `tse_cstab_s9.py`, `tse_twofilter_s9.py`.

Rohausgaben `re/captures/weltneuheit/`: `tfd-q60-discovery-…` bis `tfd-q72-videorange-20260908.log`,
`tfd-tse-woerterbuch-20260908.log`, `tfd-farbraumtabelle-20260908.log`, `tfd-zweifilter-vergleich-20260908.log`,
`tfd-attribut-nutzer-20260908.log`, `tfd-stock-live-chrono-tfd-20260908.log` (TFD-relevante Zeilen der
LIVE-Rohdatei, chronologisch mit Ticks).
