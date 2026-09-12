# RE: INCAP-Felder, Ring-Folge und der zweite Descriptor-Anstoß (K1–K3)

**Stand 07.09.2026, Nacht.** Auftrag: Nachtplan [78](78-nachtplan-hdmi-switch.md) Abschnitt 3 „K", Fragen
**K1, K2, K3**. Reine statische Analyse — **kein Board angefasst**. Werkzeug: IDA 9.1/idalib gegen eine
**Kopie** der Datenbank (`analyse/ida/db-k1k3/display.bin.i64`, Original unberührt, siehe
`analyse/ida/README.md`), Skripte `analyse/ida/ida_q27.py … ida_q41.py`, Rohausgaben
`re/captures/weltneuheit/k1k3-*-20260907.*`.

Adressen wie im Nachtplan: MIPS-MMIO = ARM-phys + `0xB5000000`, SRAM/DRAM `0x8Bxxxxxx` = ARM `0x4Bxxxxxx`.

---

## Korrekturstand 07.09.2026 — was das Gerät widerlegt hat

*(Vorangestellt; die ursprüngliche Gliederung beginnt unverändert bei „0. Kurzfassung".)*

Diese Seite entstand **vor** den Messungen am Board. Drei ihrer Aussagen sind dort widerlegt worden. Sie
bleiben unten im Text stehen — durchgestrichen bzw. in einem Kasten „Widerrufen" —, damit sichtbar bleibt,
**was** korrigiert wurde und **woran** der Fehler lag.

| Aussage dieser Seite | Stand jetzt | Beleg | Abschnitt |
|---|---|---|---|
| „`0x21 → 0x61` und `0x824` Bit 31 gehören zur **normalen, richtigen** Sequenz" | **widerlegt.** Beide kennzeichnen den Zustand **nach** dem Descriptor — und in dem ist die Capture **abgeschaltet** | `nachtlog/A-abnahme-board.md` (vierter Lauf), `nachtlog/B2-quellenwechsel.md` | §2.0 |
| „`0x824` Bit 31 = 1 → ICSC rechnet, Bit 31 = 0 → Bypass" | **widerlegt.** Vor dem Descriptor, bei Bit 31 = **0**, misst `chroma_stat.py` bereits YUV (Cb 126,2 / Cr 133,2). Welche Polarität stattdessen gilt, ist **offen** | B1-Messung 23:16 in `nachtlog/A-abnahme-board.md` | §2.2 |
| „`0x928` Bit 31 = 0 ist der gewünschte Zustand" | widerrufen (Kasten steht seit dem 07.09. in §4.3); Bit 31 = **1** heißt „Capture schreibt" | vier unabhängige Läufe | §4.3 |

Beide ersten Zeilen haben **dieselbe** Wurzel wie die dritte: die Abzüge `02_desc` und `03_source0`, auf die
sich §2.0 und §2.2 stützen, sind **nach** dem Descriptor entstanden. In diesem Zustand steht die Capture, und
die Wand zeigt den zuletzt aufgenommenen Rahmen — sie sieht aus wie ein laufendes Bild. Der Etikettenfehler
im README des Abzugverzeichnisses („`03_source0` — Referenz *gut*") ist damit in diese Seite durchgereicht
worden. Nachprüfbar in den Abzügen selbst: `0x05600320/0x324` stehen in `02_desc` (19:41:34) und
`03_source0` (19:41:47) auf **demselben** Paar `0x4C7ED000`/`0x4CDEA000`, während sie in `01_lock`, `04` und
`05` wandern — bei laufender Capture wären das 780 Bilder Abstand. *(Für sich genommen ist das kein Beweis,
ein Dreier-Ring trifft dieselbe Adresse mit 1/3 Wahrscheinlichkeit; zusammen mit `0x928` Bit 31 = 0 und der
gemessenen Ursachenkette aus §4.1 ist es eindeutig.)*

**Bewährt hat sich dagegen:**

* **K2** („kein ARM-Capture-Interrupt, stattdessen Vsync-getaktetes Lesen der Flip-Zeiger") — genau so
  gebaut (`0093` Erzeuger, `0094` Verbraucher) und am Gerät gemessen: **287 Vsync-Ereignisse**,
  **60 von 60 Bildern**, rekonstruiertes Bild = pixelgenauer Screenshot der Quelle. Siehe §3.3.
* Der Vorschlag aus §4.4, ein **echter Quellenwechsel** sei der einzige firmware-eigene Neuanstoß:
  gemessen und tragfähig (`nachtlog/B2-quellenwechsel.md`). Siehe §4.4.
* Die Mechanik von **K3** (§4.1: MemoryAgent → `memory_agent_onoff` → `0x06940928` Bit 31) trägt die
  Erklärung — nur greift sie **früher** als hier vermutet: schon das **erste** Descriptor-Schreiben
  schaltet die Capture ab, nicht erst ein zweiter Anstoß. Siehe §4.3.

---

## 0. Kurzfassung

| Frage | Antwort in einem Satz | Belegt / vermutet |
|---|---|---|
| **K1** | Die drei Felder werden **nicht von Code**, sondern von der **TSE-Registertabelle** geschrieben: `0x06940400[6:5]` = MP-Pfad-Freigabe der Gruppe `FINAL` (`DBUS_MP_RST_TV/PROJECTOR`), `0x06940824` Bit 31 = Umschalter der INCAP-Eingangs-Farbraumstufe (Modul `MP_ICSC_VINCAP`), `0x0694084C` = zwei 2-Bit-Modusfelder des 4:2:2/4:4:4-Wandlers (Modul `CONVERT_422AND444`), ausgewählt über `input_format` (lo16) und `colorspace` (hi16). | belegt |
| **K2** | `0x05600320/0x324` werden von **keiner Firmware-Funktion und von keiner TSE-Tabelle** beschrieben; ein „Slot fertig"-Interrupt existiert nur **auf der MIPS-Seite** (INTC-Quellen `VIncap` 32, `VIncap_1` 25, `AFBD` 27) und ist auf dem ARM **nirgends** verdrahtet — im Stock-DTS hat weder INCAP noch TVTOP eine `interrupts`-Eigenschaft. | belegt |
| **K3** | Die TSE-Module sind **zustandsselektiert und ohne Rückfallzustand**: passt die neue Attributkombination zu keinem State, schreibt das Modul **gar nichts** und das Register behält den alten Wert; zusätzlich unterdrückt der Projektor-Zustandsautomat jeden Neuanstoß, dessen SignalInfo mit der zwischengespeicherten übereinstimmt. | belegt (Mechanik) / vermutet (welches Register im konkreten Fall vom 19:44-Versuch hängen blieb) |

*(Zu K1, nach den Messungen: **welche** Register die drei Felder tragen und **wer** sie schreibt, steht
unverändert. Widerlegt ist nur die Deutung der Stellungen — `0x824` Bit 31 = 1 und `0x400 = 0x61`
kennzeichnen den abgeschalteten Zustand, siehe Korrekturstand oben und §2.2. Zu K3: die Mechanik steht, der als „vermutet"
geführte Teil ist durch eine **andere**, gemessene Ursache ersetzt — §4.3.)*

**Für Paket E ausdrücklich: Polling, nicht Interrupt.** Genauer: **kein eigenes Polling** — der fertige Slot
wird im ohnehin vorhandenen AFBD-Vsync (`dec@5600000`, `interrupts = <0 0x6E 4>` → GIC 142) aus
`0x05600320/0x324` gelesen. Ein ARM-sichtbares Capture-Ereignis gibt es nicht und hat Stock auch nicht.
**Am Gerät bestätigt** (287 Vsync-Ereignisse, 60/60 Bilder) — §3.3.

---

## 1. Das methodische Fundament (gilt für alle drei Fragen)

Die frühere Notiz „register-indirekt, deshalb keine Xrefs" (README `analyse/ida/`) trifft zu, ist aber nur die
halbe Wahrheit. Die MIPS-Firmware erreicht MMIO auf **drei** Wegen:

1. **`lui`-basiert, direkt.** Der Decompiler zeigt das als `MEMORY[0xBB94084C]`. IDA legt dafür keine Xrefs an,
   weil die MMIO-Adressen in keinem Segment liegen — ein Textscan über alle Instruktionen findet sie trotzdem
   (`ida_q28.py`, Ausgabe `k1k3-q28-mmio-map-20260907.log`).
2. **Basiszeiger + Displacement.** `li $v0, 0xBB940800` … `lw $a0, 0x4C($v0)`. Dafür habe ich eine lineare
   Konstantenverfolgung über jede Funktion geschrieben (`ida_q31.py`, `k1k3-q31-basiszeiger-20260907.log`).
3. **Generische Zugriffsfunktionen mit ARM-physischer Adresse als Argument:** `readl_checked` (398 Xrefs),
   `writel_checked` (219), `writel_masked` (479), `MIPS_MMIO_ReadByte/WriteByte/WriteByte_Masked` (142/83/229).
   Die Adresse kommt als `$a0`; `ida_q32.py` verfolgt Konstanten **inklusive Delay-Slot** und löst die Argumente
   auf (`k1k3-q32-accessor-args-20260907.log`).

Damit ist die INCAP-Nutzung der Firmware **vollständig** (Vereinigung aus 1–3):

```
0x0694044C  sub_8B116370 "ClearModeChangeStatus"  (Bit-31-Puls)
0x06940440/0444/0448   CapWinNode__WriteReg       (Basis 0xBB940400)
0x06940444/0448        sub_8B17A244               (readl_checked)
0x06940464/0468        CapWinNode__WriteReg       (Capture-Fensterlage/-größe)
0x069404DF/04E7        sub_8B13F5F4               (MIPS_MMIO_ReadByte, HDMI-RX-Bytebereich)
0x06940540             sub_8B1161B0               (Statusbit 28)
0x06940548             sub_8B144D74/sub_8B14503C
0x06940800             VIncap_ConfigDownScaler, sub_8B161B30   (nur als Basis bzw. lesend)
0x06940858/085C        sub_8B191958               (writel_masked, Masken 0x2/0x10/0x20/0x20000/0x100000/0x200000)
0x06940858..0x0694087C VIncap_ConfigDownScaler    (Downscaler)
0x069408D0             sub_8B161B30               (lesend)
0x06940924/0928/0964/0968  CapWinNode__WriteReg, VIncap_EnableCaptureOutput, memory_agent_onoff
0x06940A0C             AppTopProjectorCallback    (lesend)
```

**`0x0694084C`, `0x06940400` und `0x06940824` sind in dieser Liste nicht enthalten** — und sie kommen im
gesamten Firmware-Abbild auch nicht als 32-Bit-Konstante vor (Byte-Suche über `display.bin`, alle sechs
Schreibweisen, null Treffer). Sie werden also überhaupt nicht von Code geschrieben.

### 1.1 Der eigentliche Schreiber: die TSE-Registertabellen

Die INCAP-Konfiguration liegt in der **TSE-Datenbank** (`analyse/tse/board/database.TSE`, geladen nach ARM
`0x4BE41000`). Das Werkzeug `tools/tse_dump.py` existierte bereits; der vollständige Auszug für die HDMI-Quelle
liegt in `analyse/tse/hdmi-source4.txt`, ein Auszug über **alle** Module in
`re/captures/weltneuheit/k1k3-tse-alle-module-20260907.txt`.

Ein TSE-Modul (`plugin=RegTableFW`) hat mehrere **States**; jeder State ist an eine Attributkombination
gebunden (`source`, `signal`, `input_format`, `colorspace`, `project/picmode`, `icsc_mode` …). Beim Ausführen
der Gruppe wird genau der passende State geschrieben.

Auslösekette (belegt, `ida_q37.py`/`ida_q40.py`):

```
VidDecSignalDetector_GetFrameInfo   liest AFBD 0x098..0x0A4 (Descriptor-Zeiger + Info)
  -> CallbackOfSignalChange -> Queue -> AppTopProjector_ThreadMain
     -> AppTopProjector_HandleSignalEvent (0x8b108644)
        -> sub_8B1085CC(alt, neu)            "Signal geändert?"  (vergleicht +0,+4,+8,+12,+16,+20,+24)
        -> sub_8B1078EC (0x8b1078ec)         TSE-Attribute aus der SignalInfo bilden
             sub_8B12C490(source)   -> attr 0x0001
             sub_8B12C098(sig+16)   -> attr 0x001d  (colorspace)   << entscheidend
             sub_8B12C510(sig+24), sub_8B12C4C0, sub_8B12C4EC, sub_8B12C4FC
        -> sub_8B107B04 (0x8b107b04)         führt die TSE-Gruppe **"V_INCAP"** aus
```

`sub_8B107B04` ist der einzige Nutzer des Strings `"V_INCAP"` (`0x8b1eb84c`). **Er ist der Schreiber aller drei
Register aus K1.**

Der Attribut-Mapper ist eindeutig lesbar (`ida_q40.py`):

```c
int sub_8B12C098(int a1) {           // SignalInfo+16  ->  colorspace-Attribut
  unsigned v1 = a1 - 1;
  if (v1 < 0xD) return dword_8B1F218C[v1];
  else          return 0x1D0009;
}
```

Tabelle `0x8B1F218C` (13 Einträge, **1-basiert**):

| SignalInfo+16 | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 | 9 | 10 | 11 | 12 | 13 | sonst |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Attribut `0x1d…` | 000a | 000a | 000b | 0006 | 0009 | 0000 | 0008 | 0003 | 0004 | 0005 | 0007 | 0001 | 0002 | 0009 |

`SignalInfo+16` ist der **`color_format`-Wert des VidDec-Descriptors plus 1** (die Enum-Namensliste steht in der
Zeigertabelle ab `0x8B1F516C`: `color_format_yuv420_888`=0, `…_1088`=1, `…_101010`=2, `…_121212`=3,
`yuv422_888`=4, `yuv422_1088`=5, `yuv422_101010`=6, `yuv422_121212`=7, `yuv444_888`=8, `…_101010`=9,
`…_121212`=10, `rgb_888`=11, `rgb_101010`=12, `rgb_121212`=13; Dump in `k1k3-q35-enums-20260907.log`).
Die Rechnung stimmt gegen drei unabhängige Register (Abschnitt 2.4) — und unabhängig davon gegen unser
eigenes Werkzeug: `analyse/hdmi-seq/viddec_descriptor.py` Zeile 30 schreibt `d[16] = 0  # yuv420_888`.

---

## 2. K1 — `0x0694084C`, `0x06940400`, `0x06940824`

### 2.0 Vorab: zwei der drei „Umstellungen" sind der Normalfall, nicht der Fehler — **widerlegt, siehe Kasten**

Die Fragestellung im Nachtplan schreibt alle drei Änderungen dem Descriptor-**Format-4**-Versuch zu. Die
Registerabzüge des **guten** Laufs vom 06.09. (`re/captures/weltneuheit/ours-20260906-source0/`) zeigen etwas
anderes:

| Register | `01_lock` (Signal steht, nichts geschrieben) | `02_desc` / `03_source0` (nach `viddec_descriptor.py set`, Bild korrekt) | `04_after_srcoff` / `05_after_hpd` |
|---|---|---|---|
| `0x06940400` | `0x00000021` | **`0x00000061`** | `0x00000021` |
| `0x06940824` | `0x0000000b` | **`0x8000000b`** | `0x0000000b` |
| `0x0694084C` | `0x04000c00` | `0x04000c00` (**unverändert**) | `0x04000c00` |
| `0x06940928`/`0968` | `0xe0020438` | **`0x60020438`** | `0xe0020438` |

> **Widerrufen am 07.09.2026 durch Messung.** Die Spaltenüberschrift „`02_desc` / `03_source0` … Bild
> korrekt" ist falsch, und mit ihr der Satz darunter. Diese beiden Abzüge stammen aus dem Zustand **nach**
> dem Descriptor — dem Zustand, in dem die Capture **abgeschaltet** ist (`0x06940928` = `0x60020438`,
> Bit 31 = 0) und die Wand nur den zuletzt aufgenommenen Rahmen stehen lässt. Der Schluss „also ist
> `0x61`/Bit 31 der gute Zustand" beruht damit auf einem Standbild, das für ein laufendes Bild gehalten
> wurde. Dieselbe Verwechslung noch einmal in §2.2 und §4.3.
>
> **Was stattdessen gemessen ist** (vierter Abnahmelauf 23:11–23:20, `nachtlog/A-abnahme-board.md`;
> Rundlauf in `nachtlog/B2-quellenwechsel.md`):
>
> | Zustand | `0x06940928` Bit 31 | `0x06940824` | `0x06940400` | Capture |
> |---|---|---|---|---|
> | Signal steht, **vor** dem Descriptor | 1 | `0x0000000B` | `0x21` | schreibt, YUV |
> | **nach** dem Descriptor | 0 | `0x8000000B` | `0x61` | steht |
> | nach der Freigabe (Quellenwechsel **oder** HPD-Zyklus) | 1 | `0x0000000B` | `0x21` | schreibt, YUV |
>
> **`0x21 → 0x61` und `0x824` Bit 31 = 1 kennzeichnen den abgeschalteten Zustand, nicht den guten.** Nach
> einem Quellenwechsel läuft das Bild bei `0x400 = 0x21` und `0x824 = 0x0000000B` einwandfrei (Gamma-Reiz
> 4,65 % der Bildpunkte, Rückkehr 0,00 %) — beide Werte sind für den Betrieb **nicht nötig**.
>
> **Als Abnahmekriterium taugen sie deshalb nicht.** Gut ist: `0x06940928` Bit 31 gesetzt, `0x06940104`
> zählt (~60/s), `0x05600320/0x324` wandern **und** ein Reiz an der Quelle verändert das Wandbild.

~~**Belegt:** `0x21 → 0x61` und `0x824` Bit 31 gehören zur **normalen, richtigen** Sequenz mit
`color_format = 0`.~~ **Was von diesem Absatz bleibt:** `0x0694084C` ändert sich beim Descriptor-Schreiben
mit `color_format = 0` **nicht** (in allen fünf Abzügen `0x04000c00`, und nach dem Modell aus §2.3/§2.4 kann
das Modul in diesem Fall gar nichts schreiben). Der Wert `0x0C000C00` aus doku/76 §12.4 stammt also nicht aus
dem regulären Descriptor-Schreiben (siehe 2.4 — mit `color_format` 0, 2 oder 4 kann die Firmware das Register
gar nicht anfassen). **Die Gegenprobe dazu (Board-Anfrage B3, Descriptor mit `color_format` 6) ist bis heute
nicht gefahren** — die Modellvorhersage `0x84C → 0x0C000C00` ist ungeprüft.

### 2.1 `0x06940400` — Freigabe/Reset des MP-Datenpfads im INCAP

Alle Schreiber (TSE, `hdmi-source4.txt`):

| Modul (Gruppe) | Zugriff |
|---|---|
| `INIT_VINCAP` (`SYSTEM_INIT_SVP`, handle 0x2001) | `WR32 0x06940400 = 0x00000040` |
| `MP_SYNCDATAMUX` (handle 0x5008, State 2 = HDMI-Quellen `0x10011/13/14/15`) | `RMW32 mask=0x0000007b val=0x00000021` |
| `DATASYNC_PROCESS` (0x5009) | `RMW32 mask=0x00000080 val=0` |
| `CROP_BS_DBGBORDER` (0x5010) | `RMW32 mask=0xffffff04 val=0` |
| **`DBUS_MP_RST_TV` (0x1c002) und `DBUS_MP_RST_PROJECTOR` (0x1c003), Gruppe `FINAL`** | erst `RMW32 mask=0x60 val=0x00`, später `RMW32 mask=0x60 val=0x60` |

`DBUS_MP_RST_*` ist eine **geschlossene Reset-Sequenz** über die ganze Kette. Erst die Abschaltung:
DE2 `0x050C0000` Bit 5 = 0, DE `0x05000020` Bit 3 = 0, **INCAP `0x06940400` Bits [6:5] = 0**,
PROC `0x05140004` Bit 31 = 0, LVDS `0x051C0010` Bit 25 = 1 (Blanking an). Dann dieselbe Liste umgekehrt:
DE2 Bit 5 = 1, DE Bit 3 = 1, **INCAP `0x06940400` Bits [6:5] = 1**, PROC Bit 31 = 1, LVDS Bit 25 = 0
(State 0; State 1 lässt das Blanking gesetzt). Genau diese Bits [6:5] sind unsere
`0x21 → 0x61`-Beobachtung.

**Antwort (belegt):** `0x06940400` Bits [6:5] sind die **Freigabe des Main-Picture-Datenpfads im INCAP**, die
die Firmware am Ende jeder Umkonfiguration (Gruppe `FINAL`) gemeinsam mit DE, DE2, PROC und LVDS aus- und
wieder einschaltet. ~~`0x21` = Pfad ruht (nur Bit 5 der `MP_SYNCDATAMUX`-Grundeinstellung), `0x61` = Pfad
läuft.~~ Bit 7 (`DATASYNC_PROCESS`) und Bits 2/8-31 (`CROP_BS_DBGBORDER`) sind konstant 0.

> **Der letzte Halbsatz ist am 07.09.2026 widerlegt — und der Rest wird dadurch zur offenen Frage.**
> Die TSE-Tabelle sagt eindeutig, was sie sagt: `FINAL` schreibt `mask=0x60` erst `0x00`, später `0x60`,
> also ist `0x60` in ihrer Sprache „freigegeben". **Gemessen schreibt die Capture aber bei `0x21`
> (Bit 6 = 0) und steht bei `0x61` (Bit 6 = 1)** — in beiden Richtungen und in mehreren Läufen (§2.0).
>
> Beides lässt sich nur vereinbaren, wenn diese Freigabe einen **anderen** Pfad meint als den, der den
> Capture-Ring füllt — die `FINAL`-Sequenz fasst DE, DE2, PROC und LVDS an, also die **Anzeigekette**,
> und die Capture hängt am eigenen Gate `0x06940928` Bit 31 (§4.1). Dass beide Register beim
> Descriptor-Ereignis gemeinsam umschlagen, hieße dann nur: dasselbe Ereignis stellt beides.
> **Belegen kann ich das nicht** — es ist die naheliegende Vereinbarung, keine Messung. Festzuhalten
> bleibt: `0x61` als Gutkriterium zu prüfen, prüft nachweislich das Falsche.

### 2.2 `0x06940824` — Eingangs-Farbraumstufe (VINCAP-ICSC)

Einziger Schreiber: Modul **`MP_ICSC_VINCAP`** (handle 0x500d), 4 States, `always=0`:

| State | Bedingung | `0x824` | Matrix `0x834/838/83C/840/844` |
|---|---|---|---|
| 0 | `colorspace` ∈ {`1d000a,1d000b,1d0009,1d0000,1d0008,1d0006,1d0004,1d0005,1d0003`}, `picmode` ∈ {`440000,440001,440002,440009`}, `icsc_mode=650000` | **`0x8000000b`** | `009405b9 / 0cd901b3 / 0f100417 / 0fa00c49 / 00000417` |
| 1 | `colorspace` ∈ {`1d0001,1d0002,1d0007`}, `picmode=440001`, `icsc_mode=650001` | `0x0000000b` | `00e904b2 / 0d4a0264 / 0e9f0417 / 0f560c93 / 00000417` |
| 2 | dieselben `colorspace`, `picmode=440000`, `icsc_mode=650002` | `0x0000000b` | **identisch zu State 0** |
| 3 | dieselben `colorspace`, `picmode=440002`, `icsc_mode=650003` | `0x0000000b` | `0079056d / 0d0d021a / 0edc0417 / 0fac0c3d / 00000417` |

Das Modul schreibt außerdem `0x800` (RMW `0x0000fffe` = `0x0c00`), `0x828/082C = 0`, `0x830 = 0x02000200`,
`0x848 = 0`.

**Antwort (belegt):** `0x06940824` Bit 31 ist der **Betriebsartschalter der INCAP-Eingangs-Farbraumstufe
(VINCAP_ICSC)**. Die unteren Bits (`0x0b`) sind in allen States gleich. Dass Bit 31 der Enable/Bypass-Schalter
und kein Nebeneffekt ist, folgt daraus, dass **State 0 und State 2 exakt dieselben Matrixkoeffizienten
schreiben und sich ausschließlich in Bit 31 unterscheiden**.

> **Widerrufen am 07.09.2026 durch Messung — und der Beleg war von vornherein keiner.**
>
> Der Absatz unten schließt aus einer Chroma-Messung *nach* dem Descriptor auf die Wirkung von Bit 31.
> Das kann er nicht: `chroma_stat.py` liest den **Ringinhalt**, und im Zustand `0x824 = 0x8000000b` ist die
> Capture abgeschaltet (`0x928` Bit 31 = 0, §2.0). Der Rahmen, der dort im Ring liegt, wurde also
> aufgenommen, **bevor** Bit 31 gesetzt wurde. Die Messung hätte gar nicht anders ausfallen können als der
> Zustand davor — sie prüft nichts.
>
> Die Messvorschrift B1 (`nachtlog/K1-K3-re.md`) hatte das selbst als Abbruchkriterium formuliert:
> „misst es dort **schon** YUV um 128, ist die Polarität umgekehrt und Abschnitt 2.2 von doku/84 muss
> korrigiert werden." **Gemessen am 07.09. um 23:16, vor dem Descriptor, bei Bit 31 = 0:
> Cb 126,2 / Cr 133,2 — bereits YUV** (`nachtlog/A-abnahme-board.md`). Bestätigt durch B2: nach dem
> Quellenwechsel steht `0x824` wieder auf `0x0000000b`, das Bild läuft, und der Ring trägt YUV
> (Y 118,5 / Cb 122,2 / Cr 140,4).
>
> **Stand jetzt:**
> * Der **strukturelle** Teil trägt weiter: Bit 31 ist der Betriebsartschalter der Stufe. Das folgt aus der
>   TSE-Tabelle allein (State 0 und State 2 schreiben identische Koeffizienten und unterscheiden sich
>   ausschließlich in Bit 31) und hängt an keiner Messung.
> * **Welche Stellung „Matrix rechnet" bedeutet, ist offen.** Belegt ist nur: bei Bit 31 = 0 liefert die
>   Capture aus einer RGB-Quelle YUV. Ob die Matrix in dieser Stellung rechnet oder ob die Wandlung
>   woanders in der Kette sitzt, ist mit unseren Messungen nicht zu trennen.
> * Der Satz zu doku/76 §12.5 („die ICSC ist schon eingeschaltet") ist damit ebenfalls unbelegt — er
>   stützte sich allein auf die widerrufene Polarität. Er ist deshalb **kein** Argument mehr gegen den
>   dortigen Weg 3, aber auch keines dafür.

~~**Polarität (belegt über Messung + Tabelle):** Unsere Abzüge zeigen die Koeffizienten von State 0/2. Vor dem
Descriptor steht `0x824 = 0x0000000b` (also State 2, Bit 31 = 0); danach `0x8000000b` (State 0, Bit 31 = 1) —
und genau in diesem Zustand misst `chroma_stat.py` **YUV mit Cb/Cr um 128** aus einer **RGB**-Quelle
(doku/76 §13). Die Matrix rechnet also, wenn Bit 31 gesetzt ist. **Bit 31 = 1 → ICSC aktiv (Matrix rechnet),
Bit 31 = 0 → Bypass.** Das korrigiert die Lesart aus doku/76 §12.5 („INCAP-ICSC einschalten" wäre Weg 3): die
ICSC **ist** in unserem guten Zustand schon eingeschaltet, und zwar von der Firmware selbst.~~

### 2.3 `0x0694084C` — 4:2:2/4:4:4-Wandler

Einziger Schreiber: Modul **`CONVERT_422AND444`** (handle 0x500e), `always=0`:

| State | `input_format` | `colorspace` | `0x84C` |
|---|---|---|---|
| 0 | `a0000, a0003, a000c, a0001` | `1d0000, 1d0008, 1d0006` | `0x0C000C00` |
| 1 | `a0000, a0003, a000c, a0001` | `1d0001, 1d0002, 1d0007, 1d0004, 1d0005, 1d0003` | `0x04000C00` |
| 2 | `a0007, a0004` | `1d0001, 1d0002, 1d0007, 1d0004, 1d0005, 1d0003` | `0x04000400` |
| 3 | `a0007, a0004` | `1d0000, 1d0008, 1d0006` | `0x0C000400` |

Dazu `0x850 = 0` und `0x854` RMW `0xfffffffe` = 0 in allen States; Bit 0 von `0x854` setzt
`MP_444TO422_SELECT` (0x500f) getrennt auf 0.

**Struktur (belegt):** Das Register besteht aus **zwei gleich aufgebauten 16-Bit-Hälften**; jede Hälfte trägt
ein 2-Bit-Feld in den Bits [11:10] bzw. [27:26] mit den Werten `1` (`0x0400`) oder `3` (`0x0C00`).
Dieselbe Feldstruktur benutzen die Nachbarregister `0x858`/`0x85C`: die TSE-Grundeinstellung `MP_SCALAR_BASE`
schreibt dort `0x04020000`/`0x04020402` (Feld = 1), und `VIncap_ConfigDownScaler` (`0x8b19ff1c`) setzt bei
aktiver Skalierung dieselben Felder auf 3:

```c
MEMORY[0xBB940858] = MEMORY[0xBB940858] & 0xF3FFFFFF | 0xC000000;   // [27:26] = 3
MEMORY[0xBB94085C] = MEMORY[0xBB94085C] & 0xFFFFF3FF | 0xC00;       // [11:10] = 3
MEMORY[0xBB94085C] = MEMORY[0xBB94085C] & 0xF3FFFFFF | 0xC000000;   // [27:26] = 3
```

Passend dazu stehen im laufenden System `0x858 = 0x0c020000` und `0x85C = 0x0c020c02` (Abzug `01_lock`).

**Antwort (belegt):** `0x0694084C` konfiguriert die **4:2:2/4:4:4-Wandlerstufe** des INCAP. Die **untere
Hälfte** (Bits [11:10]) hängt allein am `input_format` — Wert 3, solange das Eingangsformat **nicht** bereits
4:2:2 ist (also wandeln), Wert 1 bei den beiden 4:2:2-Eingangsformaten. Die **obere Hälfte** (Bits [27:26])
hängt allein am `colorspace`-Attribut, also am `color_format` des VidDec-Descriptors. In unserem korrekten
Betrieb steht das Register durchgehend auf `0x04000C00` (State 1): untere Wandlerhälfte an, obere aus.

### 2.4 Die Probe: drei Register, ein Modell

Aus den Abzügen lässt sich die Attributlage rückrechnen — und sie stimmt exakt:

* **`01_lock`** (vor dem Descriptor): `0x824 = 0x0b` mit den State-0/2-Koeffizienten ⇒ **`MP_ICSC_VINCAP`
  State 2** ⇒ `colorspace` ∈ {`1d0001, 1d0002, 1d0007`}, `picmode = 0x440000`.
  Gleichzeitig `0x84C = 0x04000C00` ⇒ **`CONVERT_422AND444` State 1** ⇒ `colorspace` in derselben Menge. ✔
  Mit der Mappertabelle heißt das `SignalInfo+16` ∈ {12, 13, 11}, also `color_format` ∈ {`rgb_888`,
  `rgb_101010`, `yuv444_121212`} — der ThinkPad speist **RGB** ein, `rgb_888` = 11 → `+16` = 12 → `0x1d0001`. ✔
* **`02_desc`** (nach `viddec_descriptor.py set`, `color_format = 0`): `+16` = 1 → Attribut **`0x1d000a`**.
  `0x1d000a` liegt in der State-0-Menge von `MP_ICSC_VINCAP` ⇒ `0x824 = 0x8000000b`. ✔ **gemessen.**
  `0x1d000a` liegt in **keiner** State-Menge von `CONVERT_422AND444` ⇒ das Modul schreibt **nichts** ⇒
  `0x84C` bleibt `0x04000C00`. ✔ **gemessen.**

Damit ist das Modell an drei Registern und zwei Zuständen unabhängig bestätigt.

**Dritte, unabhängige Bestätigung durch B2 (07.09., am Gerät).** Nach `SetSource(1) → SetSource(3)` — ohne
zweites Descriptor-Schreiben — steht `0x824` wieder auf `0x0000000b`. Das Modell verlangt genau das: der
Quellenwechsel löst `HandleSignalEvent` mit „geändert" aus, die Attribute werden aus der **realen**
SignalInfo neu gebildet (RGB-Quelle → `0x1d0001`), und `MP_ICSC_VINCAP` trifft wieder einen der States
1/2/3. Der Wert **hätte** auf `0x8000000b` stehenbleiben können — das ist die Bedingung, unter der diese
Beobachtung überhaupt etwas prüft. *(Nicht gemessen wurde das Attribut selbst; belegt ist nur das
Registerbild, das dazu passt.)*

**Folgerung, die Paket D/E direkt betrifft (belegt):** Das Descriptor-Wort 16 (`color_format`) ist **nicht nur**
ein Formathinweis für den AFBD-Leser. Es geht über `SignalInfo+16` → `sub_8B12C098` → TSE-Attribut `colorspace`
in die **INCAP-Konfiguration** ein und entscheidet dort über ICSC-Betriebsart und 4:2:2-Wandlung.

> **Korrektur 07.09.2026 am zweiten Halbsatz.** ~~Der Wert `0` (`yuv420_888`) ist derjenige, der die ICSC
> scharfstellt und den Wandler unverändert lässt — das ist der belegte Grund für die Regel
> „`color_format` bleibt 0" aus doku/76 §11.3.~~
>
> Richtig ist: `color_format = 0` schiebt `0x824` in **State 0** (`0x8000000b`) — also **weg** von der
> Stellung, in der die Capture nachweislich läuft (§2.0). „Scharfstellen" ist die falsche Beschreibung;
> welche Stellung was bedeutet, ist seit der B1-Messung offen (§2.2).
>
> Und die Regel „`color_format` bleibt 0" hat einen **anderen**, inzwischen gemessenen Grund: das
> Descriptor-Schreiben nimmt die Firmware als VideoDec-Ereignis, `memory_agent_onoff` löscht daraufhin die
> INCAP-Freigabe `0x06940928` Bit 31 und **schaltet die Capture ab** — unabhängig davon, welcher Wert in
> Wort 16 steht (§4.3). Was der Wert 0 zusätzlich bewirkt: der 4:2:2-Wandler `0x84C` bleibt unangetastet,
> weil `0x1d000a` in keiner State-Menge von `CONVERT_422AND444` liegt. Das gilt weiter.

**Und eine Korrektur (belegt):** `0x0694084C = 0x0C000C00` verlangt `CONVERT_422AND444` State 0, also
`colorspace` ∈ {`1d0000, 1d0008, 1d0006`}, also `SignalInfo+16` ∈ {6, 7, 4}, also Descriptor-`color_format`
∈ {**5** `yuv422_1088`, **6** `yuv422_101010`, **3** `yuv420_121212`}. Mit den am 06.09. tatsächlich
geschriebenen Werten 4 und 2 (doku/76 §11.3) **kann** die Firmware `0x84C` gar nicht beschrieben haben
(`+16` = 5 → `0x1d0009`, `+16` = 3 → `0x1d000b` — beide in keiner State-Menge des Moduls).
Die Zuschreibung in doku/76 §12.4 („den die Firmware beim Descriptor-Versuch mitgesetzt hat") ist damit
**nicht haltbar**; als Ursache bleibt das von Hand gesetzte Bit 31 in `0x06940928/0968`, das doku/76 §13
ohnehin schon als Auslöser der RGB-artigen Ebenen identifiziert hat. *(Diese Ursachenzuweisung ist eine
Schlussfolgerung aus der Tabelle, keine Messung — siehe Board-Anfrage B3.)*

### 2.5 Nebenbefunde zum INCAP-Registerplan

* `0x06940800`-Block = Write-Back/Format der MP-Capture (`MP_WB_VINCAP` 0x500c schreibt `0x800/0x804/0x808/
  0x80C/0x810/0x814/0x818/0x81C/0x820`; `MP_ICSC_VINCAP` `0x824–0x848`; `CONVERT_422AND444` `0x84C–0x854`;
  `MP_SCALAR_BASE`/`VIncap_ConfigDownScaler` `0x858–0x880`; `CROP_BS_DBGBORDER` `0x884–0x8A0`;
  `WAGT_CAPTURE` `0x8A4–0x8EC`; `V_INCAP_MP_FORMAT` `0x8C0/0x8C8` [2:0]; `MP_BUF_CMD` `0x8D0` [17:0] = `0x300`).
* `0x06940920/0x0940960`-Blöcke = die beiden **Ausgabekanäle** (Luma/Chroma) im Abstand `0x40`:
  Ringadressen `0x8F0…` bzw. `0x930…`, Größe `0x924`/`0x964`, Steuerwort `0x928`/`0x968`.
  `CapWinNode__WriteReg` baut `0x928` als `0x60020000 | Höhe` — im Abzug `0x60020438` (`0x438` = 1080). ✔
* `0x06940400`-Block = Capture-Fenster/Sync (`DATASYNC_PROCESS` 0x5009 schreibt `0x440–0x4E8`,
  `SYNC_GEN` 0x500a `0x44C`, `CapWinNode__WriteReg` `0x440/0444/0448/0464/0468`).
* `CAPTURE_RDBACK` (0x5014) schreibt `0x970 = 0x0c000000`, `0x974 = 0x01000100`, `0x978 = 3`.

---

## 3. K2 — Ring-Folge und „Slot fertig"

### 3.1 Wer schreibt `0x05600320/0x05600324`? Niemand in der Software.

Drei unabhängige Suchen, alle negativ:

1. **Direkte (`lui 0xBA60`) Zugriffe.** Genau sechs Funktionen bilden je eine AFBD-Basis:
   `NRWinNode_AfbdConfigure`, `NRWinNode_WriteAfbdBufStride`, `NRWinNode_WriteAfbdCropWin`,
   `VidDecSignalDetector_GetFrameInfo`, `memory_agent_onoff`, `sub_8B161B30`
   (`k1k3-q29-mmio-fenster-20260907.log`).
2. **Basiszeiger + Displacement** über alle 3318 Funktionen: die Firmware fasst im AFBD-Block **genau 14
   Offsets** an, alle in `0x000…0x0A4` (`k1k3-q31-basiszeiger-20260907.log`):
   `0x010, 0x014, 0x024, 0x02C, 0x030, 0x03C, 0x04C, 0x060, 0x064, 0x068, 0x098, 0x09C, 0x0A0, 0x0A4`
   (dazu aus dem Direktscan `0x020, 0x028, 0x040, 0x044, 0x048, 0x050, 0x054, 0x06C`).
   **Nichts ab `0x100`** — weder ch1 (`0x100`), noch ch2 (`0x140`), noch der `0x300`-Block.
3. **Zugriffsfunktionen mit aufgelöstem `$a0`:** kein einziger Aufruf im Bereich `0x0560xxxx`
   (`k1k3-q32-accessor-args-20260907.log`).
4. **TSE:** im vollständigen Auszug über alle Module (`k1k3-tse-alle-module-20260907.txt`) kommt
   **kein einziges** Register `0x0560xxxx` vor. Die TSE fasst den AFBD überhaupt nicht an.

Die verbleibende Lücke sind Aufrufe der Zugriffsfunktionen mit zur Laufzeit gebildeter Adresse (rund 40 %).
Sie fällt hier nicht ins Gewicht: die einzige Funktion, die **sowohl** eine AFBD-Basis bildet **als auch**
unaufgelöste Aufrufe hat, ist `sub_8B161B30`, und die ruft ausschließlich `readl_checked` — sie liest.

**Antwort (belegt):** `0x05600320/0x324` werden **von der MIPS-Firmware nicht geschrieben** und stehen auch in
keiner TSE-Tabelle. Sie sind ein **Hardware-Register-Paar**, das die Capture-/AFBD-Hardware selbst fortschaltet.
Das passt zu allen bisherigen Beobachtungen aus doku/64 §4 (geschriebene Werte werden „in Echtzeit"
überschrieben, `0x30C`/`0x310` wandern selbsttätig, ohne Quelle parkt der Ring) und zu der bereits
kommentierten Bedeutung von `0x05600010` Bit 31 („source-mode: nimm die globalen Page-Flip-Zeiger `0x320/324`
statt der kanaleigenen Adresse", gesetzt in `NRWinNode_AfbdConfigure`). Die Zeiger sind also die **Leseseite**:
die Hardware veröffentlicht dort das zuletzt fertige Slot-Paar, der AFBD-Kanal holt es sich.

**Korrektur einer alten Notiz:** Der IDB-Kommentar an `memory_agent_update_onoff` („THIS is the pool-2/+0x300
writer") ist falsch. Die dortige `0x300` ist ein **Maskenwert** (`0x200|0x100`) für `memory_agent_onoff` und
wählt die DE2-Registergruppen `0x050C0478/04F8/0578/05F8/0678` bzw. `0x050C07B8` aus — kein AFBD-Offset.
Der Kommentar in `memory_agent_onoff` sagt das selbst („prior '0x300' = 0x200|0x100").

### 3.2 Gibt es ein „Slot fertig"-Interrupt?

**Auf der MIPS-Seite: ja.** Die Firmware hat einen eigenen Interruptcontroller (`~0x0305FC00`) mit 63 Quellen;
`InterruptSources_Init` (`0x8b184244`) verdrahtet sie über `register_hw_interrupt` auf
`HwIrq_DispatchToSwInterrupt`. Die Quellentabelle `g_irq_to_swint_table` (`0x8B2319D4`, 63 × 44 B) trägt
Klartextnamen (`k1k3-q38`-Lauf, ASCII in den Einträgen):

| IRQ | Name | IRQ | Name | IRQ | Name |
|---|---|---|---|---|---|
| 0 | `PC` | 24 | `VMeter` | 32 | **`VIncap`** |
| 1/2 | `SW0`/`SW1` | 25 | **`VIncap_1`** | 33 | `VPanel` |
| 3–6 | `MsgBoxRead`, `MsgBoxWrite`, `…_1`, `…_2` | 26 | `VProc` | 34 | `VPanel_new` |
| 7 | `VideoDecoder` | 27 | **`AFBD`** | 35 | `HDMI_Rx` |
| 17/18 | `Timer5`/`Uart` | 28/29 | `VOSD`/`VDeint` | 61 | `SW1_Test` |

**Auf der ARM-Seite: nein.** Im Stock-DTS (`legacy/reference/stock_dts/hy310-board.dts`) hat

* `tvtop@5700000` (compatible `allwinner,sunxi-tvtop`) **keine** `interrupts`-Eigenschaft,
* `tvcap@6800000` ist nur ein IOMMU-Knoten, ebenfalls ohne `interrupts`,
* es gibt **keinen** Knoten, der `0x06940000` überhaupt abbildet,
* die einzige Unterbrechung im Displaybereich ist `dec@5600000`:
  `reg = <0x0 0x5700000 0x0 0x100  0x0 0x5600000 0x0 0x400>`, `interrupts = <0x0 0x6E 0x4>` — SPI 110,
  also **GIC 142**, genau die Leitung, die unser KMS-Treiber schon als Vsync benutzt.

Auch der RPC-Weg gibt nichts her: die Callback-Liste der cpu_comm-Tabelle
(`mainline/docs/reference/cpu-comm-call-table.md`) kennt nur `SignalChangeCallback`,
`HDMIHotPlugByPortCallback` und `CallbackOfDisplayLatencyChange` — **kein Frame-/Slot-Ereignis**.

Zur Vermutung „INCAP `+0x100`-Pulse": `0x06940100` und `0x06940104` werden von der Firmware **nirgends**
gelesen; die TSE setzt `0x06940104` nur beim Init und in `WAGT_CAPTURE` auf 0. In unseren Abzügen steht
`0x06940100` konstant (`0x00000427` bzw. `0x00000407`), während `0x06940104` als `Frame<<16 | Zeile` läuft.
`0x100` ist damit ein **Status-/Konfigurationswort, kein quittierbares Interruptstatusregister** — und selbst
wenn es Pulse zeigte, gäbe es keine Leitung zum ARM.

### 3.3 Antwort für Paket E: **Polling — genauer: Vsync-getaktetes Auslesen**

**Es gibt kein ARM-sichtbares „Slot fertig"-Ereignis, und Stock hat auch keines.** Die saubere Lösung ist
keine Schleife, sondern der schon vorhandene AFBD-Vsync:

```
GIC 142  (dec@5600000, interrupts = <0 0x6E 4>)   -- der KMS-Treiber hält ihn bereits
   |
   +-- lies 0x05600320 (Y) und 0x05600324 (C)
   +-- Paar != letztes Paar  ->  Slot i ist fertig  ->  vb2_buffer_done(i)
```

Das ist exakt der Weg, den doku/76 §11.1 schon als belegt führt, und er ist quirk-frei: kein Poke, keine
Drosselung, kein Timeout. Slot-Index aus der Adresse: Y `0x4C3EF000/0x4C5EE000/0x4C7ED000` (Abstand
`0x1FF000`), C = Y + `0x5FD000`; Y-Slot i gehört zu C-Slot i.

*(Vermutung, nicht belegt: da die Capture 60 Hz liefert und das Panel 60 Hz läuft, sollte pro Vsync höchstens
ein neuer Slot anfallen. Ein Zähler auf „Paar unverändert" bzw. „zwei Slots übersprungen" gehört trotzdem in
den Treiber, damit ein Ratenunterschied sichtbar wird statt still zu verschlucken.)*

> **Nachtrag 07.09.2026 — diese Antwort hat sich am Gerät bewährt.** Der Weg ist so gebaut worden:
> `0093` liest das Paar einmal je Vsync (dreifaches Lesen gegen Zerrissenheit, Grenzprüfung) und meldet
> echte Wechsel über eine atomare Notifier-Kette; `0094` hängt sich als Verbraucher ein, statt sich das
> Fenster ein zweites Mal abzubilden (`nachtlog/DE-vsync-notifier.md`). Gemessen in der E-Abnahme:
> **287 Vsync-Ereignisse**, **60 von 60 Bildern**, rekonstruiertes Bild = pixelgenauer Screenshot der
> Quelle. Die hier verlangten Zähler gibt es: `uebersprungen` und `unveraendert` in
> `/sys/kernel/debug/sun50i-h713-hdmirx/status`; ihre Werte sind noch nicht ausgewertet.
>
> **Was der Vsync-Weg nicht leistet — inzwischen gemessen:** ein reiner **Auflösungswechsel** der Quelle
> erzeugt kein Ereignis. Die Flip-Zeiger wandern weiter, es kommen formal 10 von 10 Bildern, und der Ring
> enthält zerrissenen Inhalt (`nachtlog/A6-4-aufloesungswechsel.md`). Der Vsync meldet „neuer Slot", nicht
> „neue Geometrie". Das ist keine Einschränkung dieser Antwort — ein Capture-Interrupt hätte es genauso
> wenig gemeldet —, aber die Lücke, die daneben offen bleibt.

### 3.4 Ein Widerspruch, den ich nicht aufgelöst habe (ehrlich benannt)

Der ARM-seitige Stock-Treiber `ge2d_dev.ko` (Dekompilat in `re/captures/weltneuheit/flip_re.log`) behandelt
`0x05600300` und `0x05600340` als die Registerblöcke **zweier OSD-AFBD-Instanzen**:
`osd_ready_for_update` schreibt `OSD_AFBD_REG_OFFSET[i] + 4` mit 1 (Commit), und `osd_afbd_irq` liest
`OSD_AFBD_REG_OFFSET[i] + 40`, also **`0x05600328` bzw. `0x05600368`**, prüft dort Bit 1 und schreibt den Wert
als W1C zurück. Nach dieser Lesart wären `0x320/0x324` die beiden Pufferadressen der OSD-0-Instanz
(Header + Nutzdaten eines AFBD-Puffers), nicht globale Flip-Zeiger.

Dagegen steht die Messung: in **unseren** Abzügen stehen dort die Y-/C-Adressen des Capture-Rings
(`0x4C3EF000`/`0x4C9EC000` → `0x4C7ED000`/`0x4CDEA000`), sie wandern im Gleichtakt durch die drei Slots, und
`0x05600328` ist bei uns durchgehend 0. Dazu passt der bereits vorhandene IDB-Kommentar an
`NRWinNode_AfbdConfigure` (Bit 31 in `0x05600010` = „nimm die globalen Page-Flip-Zeiger `+0x320/324`") und
doku/64 §6.

Beides lässt sich vereinbaren, wenn `0x300…0x33F` ein AFBD-Decoderblock ist, dessen Pufferzeiger-Paar von der
Capture-Hardware nachgeführt wird, sobald ein Kanal per Bit 31 auf „globales Paar" steht — belegen kann ich das
nicht. **Für Paket E ist es ohne Belang:** die Zeiger sind so oder so nur zu lesen, und ein ARM-Interrupt
existiert für sie nicht (`0x05600328` bleibt bei uns 0, und die Leitung GIC 142 hängt am `dec`-Knoten).

---

## 4. K3 — warum die Capture nach einem zweiten Descriptor-Anstoß nicht weiterläuft

### 4.1 Der Zustandsautomat (belegt)

`AppTopProjector`-Objekt (ARM `0x4B8C8D7C`): `+4` = Zustand, `+20` = Timer-Deadline, `+32` = **zwischen-
gespeicherte SignalInfo**, `+224` = Quelle, `+204/220/221/222` = Freigabeflags.

```
EnterIdle                 (0x8b108394)  Zustand := 0   PushSignalToMemoryAgent(sig)
EnterWaitingWindowsReady  (0x8b108474)  Zustand := 2   PushSignalToMemoryAgent(NULL)   -> signal_id 0x20003
EnterWaitingPipeLineReady (0x8b108518)  Zustand := 3   PushSignalToMemoryAgent(&this+32)
EnterSignalSteady         (0x8b107d5c)  Zustand := 4   (Frühausstieg, wenn schon 4)
```

`AppTopProjector_PushSignalToMemoryAgent` (`0x8b1082e0`) ist der **einzige** Schreiber von `MemoryAgent+8…`
(`MemoryAgent_SetSignalInfo`, vtable[5]) und ruft danach `update_onoff` (vtable[3]). Aufrufer sind
ausschließlich die drei Zustandseintritte oben — **kein ARM-Aufruf kann das Gate direkt bewegen.**

`memory_agent_update_onoff` (`0x8b153140`) entscheidet aus `MemoryAgent+12` (signal_id):
`0x20002/0x20003` = „kein Signal" → alles abschalten; ein echter Modus → Maske bauen und
`memory_agent_enable(maske|0x80)` / `memory_agent_disable(~maske)`.
`memory_agent_onoff` (`0x8b15349c`) übersetzt die Maske in Register; **Maskenbit `0x8` = INCAP `0x06940928`
und `0x06940968` Bit 31**, Bit `0x10` = AFBD `0x05600010` Bits 0+1 und `0x05600014` Bit 0.

### 4.2 Die zwei Sperren, die einen zweiten Anstoß verschlucken (belegt)

**Sperre 1 — der Gleichheitsfilter.** In `ThreadMain` läuft ein Signalereignis nur dann in einen
Zustandswechsel, wenn `sub_8B1087F8` → `sub_8B10881C` (`0x8b10881c`) einen Unterschied findet. Verglichen
werden `+8, +12, +16, +20, +24, +40, +80, +84, +88, +92, +96` sowie die Gültigkeit
(`signal_id − 0x20002 < 2`). Ist die neue SignalInfo gleich der zwischengespeicherten, passiert **nichts** —
kein `EnterWaitingWindowsReady`, kein `PushSignalToMemoryAgent`, kein `update_onoff`.
**Denselben Descriptor ein zweites Mal zu schreiben ist also per Konstruktion ein Nullereignis.**
Dieselbe Prüfung noch einmal in `HandleSignalEvent` über `sub_8B1085CC` (`0x8b1085cc`), das darüber
entscheidet, ob `sub_8B1078EC` (TSE-Attribute) und `sub_8B107B04` (Gruppe `V_INCAP`) überhaupt laufen.

**Sperre 2 — TSE-Module ohne Rückfallzustand.** Das ist der Kern der Frage „welcher Zustand wird nicht
zurückgesetzt". `RegTableFW`-Module sind **zustandsselektiert**; passt die Attributkombination zu keinem
State, schreibt das Modul **gar nichts** — es stellt keine Grundwerte her. Im Kopf jedes Moduls steht das
sichtbar als `always=`:

| Modul | `states` | `always` | Verhalten ohne Treffer |
|---|---|---|---|
| `INIT_VINCAP` (Gruppe `SYSTEM_INIT_SVP`) | 1 | **2** | läuft immer — aber nur beim MIPS-Start |
| `MP_SYNCDATAMUX` | 3 | 1 | ein unbedingter State vorhanden |
| `MP_ICSC_VINCAP` | 4 | **0** | **schreibt nichts** |
| `CONVERT_422AND444` | 5 | **0** | **schreibt nichts** |
| `MP_WB_VINCAP` | 4 | **0** | **schreibt nichts** |

Und `INIT_VINCAP` schreibt weder `0x824` noch `0x84C` (seine Liste: `0x06E00008`, `0x06940000`,
`0x06940400 = 0x40`, `0x06940104 = 0`, `0x06940800` Bit 0, `0x0928/0968`, `0x0924/0964`, `0x092C/096C`,
`0x0920/0960`, `0x06980028/2C/30`). **Für `0x0694084C` und `0x06940824` gibt es damit in der ganzen Firmware
keinen Pfad, der sie auf einen definierten Grundwert zurückstellt** — nur States, die zu bestimmten
Attributkombinationen passen, und den Reset-Wert der Hardware beim Kaltstart.

### 4.3 Was das für den 19:44-Vorfall heißt

Belegt: Der Rückweg `color_format 2 → 0` erzeugt Attribut `0x1d000a`. Damit trifft
`MP_ICSC_VINCAP` State 0 (schreibt `0x824` + Matrix — ~~also **wird** die ICSC wiederhergestellt~~
*„wiederhergestellt" ist nach der Polaritätskorrektur die falsche Beschreibung: State 0 ist die Stellung
`0x8000000b`, und die ist am Gerät nur im abgeschalteten Zustand gemessen worden, §2.2*), aber
`CONVERT_422AND444` und `MP_WB_VINCAP` treffen keinen State und **schreiben nichts**. Alles, was der
Zwischenzustand in `0x84C`, `0x850`, `0x800–0x820` hinterlassen hat, bleibt stehen.

~~Vermutet (nicht gemessen, weil dafür ein zweiter Descriptor-Schreibvorgang nötig wäre — verboten): genau
dieser Satz stehengebliebener Register aus dem `MP_WB_VINCAP`/`CONVERT`-Bereich ist es, der die Capture nach
dem zweiten Anstoß nicht mehr in den Ring schreiben lässt (Symptom „alle Slots identisch").~~ Die
Zustandsmaschine selbst läuft sauber durch — sie hat keinen klemmenden Merker; `EnterSignalSteady` und
`EnterIdle` haben zwar Frühausstiege, aber die betreffen nur den Zustand, nicht die Registerlage.

> **Überholt am 07.09.2026 — die Ursache ist gemessen, und sie ist eine andere.** Die Vermutung oben sucht
> den Fehler bei stehengebliebenen INCAP-Registern nach einem **zweiten** Anstoß. Gemessen wurde etwas
> Einfacheres: **schon das erste Descriptor-Schreiben schaltet die Capture ab.** Kaltstart-Gegenversuch ohne
> jeden Zusatzbefehl (`nachtlog/A-abnahme-board.md`, Korrektur 22:26): `0x06940928` steht davor auf
> `0xE0020438` und unmittelbar danach auf `0x60020438`. Der Weg ist genau der aus §4.1 — die Firmware nimmt
> das Descriptor-Schreiben als VideoDec-Ereignis, setzt MemoryAgent `+8` auf 1, und
> `memory_agent_update_onoff` legt Maskenbit `0x8` (INCAP `0x928`/`0x968` Bit 31) in die **disable**-Maske,
> weil die Capture nicht zur Maske der Quelle VideoDec gehört. `+0x104` zählt danach weiter, geschrieben
> wird nichts, die Wand zeigt den zuletzt aufgenommenen Rahmen.
>
> Damit ist die Mechanik dieses Abschnitts bestätigt (`memory_agent` ist der Schalter), aber die
> **Zuschreibung** an stehengebliebene `MP_WB_VINCAP`/`CONVERT`-Register wird für dieses Symptom nicht
> gebraucht — sie erklärt einen zweiten Anstoß, der Stillstand tritt schon beim ersten ein. Ob sie für den
> 19:44-Fall zusätzlich zutrifft, ist weiterhin ungemessen; der dafür nötige zweite Descriptor-Schreibvorgang
> ist nach wie vor nicht gefahren worden.
>
> **Zwei Wege geben die Capture wieder frei, beide Stock-RPCs, beide gemessen:** der **Quellenwechsel**
> (`nachtlog/B2-quellenwechsel.md`) und der **HPD-Zyklus** (0,3 s genügen, `nachtlog/M4-hpd-dauer.md`).
> In beiden Fällen geht `0x928` zurück auf `0xE0020438` — und `0x824`/`0x400` auf `0x0000000B`/`0x21`.
> Sie sind **verschieden stark belegt**: B2 hat den Reiz an der Quelle, M4 nur das Freigabebit (siehe §4.4).
> **Korrektur 07.09., 11:55:** die Gegenprobe zu M4 ist gefahren, und der HPD-Zyklus hat aus dem geprüften
> Zustand (aktive Quelle VideoDec) in 20 s **nicht** freigegeben, ein `SetSource(3)` danach sofort
> (`nachtlog/M4-nachpruefung.md`). „Zwei belegte Wege" ist damit nicht haltbar — belegt ist der
> **Quellenwechsel**; der HPD-Zyklus ist als Betriebsweg nicht zu verwenden.
>
> **Nachtrag 07.09., 11:42:** die Freigabe fährt jetzt der **Kernel** (`0099`, `nachtlog/E2-freigabe.md`) —
> der Anzeigetreiber meldet die Veröffentlichung des Descriptors auf einer eigenen Benachrichtigungskette,
> der Aufnahmetreiber antwortet mit einem Quellenwechsel weg **und zurück**. Dabei nachgemessen und für
> diese Seite wichtig: ein **einzelner** `SetSource(HDMI-1)` reicht nicht, wenn HDMI-1 schon aktiv ist
> (dreimal `0x60020438`) — die Firmware führt `V_INCAP` nur bei einem **Wechsel** erneut aus, genau wie
> §4.4 es vorhersagt. Und die Freigabe erscheint erst **536–544 ms** nach der Antwort der Firmware.

Zum Symptom „`0x928` Bit 31 bleibt 0":

> **Widerrufen am 07.09.2026 durch Messung.** Der folgende Absatz behauptete, Bit 31 = 0 sei der gute
> Zustand. Das Gegenteil ist der Fall, in vier unabhängigen Läufen gemessen:
>
> | Zustand | `0x06940928` | Ring |
> |---|---|---|
> | Signal steht, vor dem Descriptor | `0xE0020438` (Bit 31 = **1**) | schreibt, YUV |
> | nach dem Descriptor | `0x60020438` (Bit 31 = **0**) | **steht still** |
> | nach Freigabe (Quellenwechsel oder HPD-Zyklus) | `0xE0020438` (Bit 31 = **1**) | schreibt wieder |
>
> Beleg: `doku/nachtlog/A-abnahme-board.md` (vierter Lauf, Registertabelle),
> `doku/nachtlog/B2-quellenwechsel.md` (Rundlauf mit Gamma-Reiz: Ring folgt nur im Zustand Bit 31 = 1),
> Registerabzüge in `re/captures/weltneuheit/ours-20260907-nacht/`.
> Die Verwechslung erklärt sich vermutlich daraus, dass die hier zitierten Abzüge `02_desc` und
> `03_source0` **nach** dem Descriptor entstanden sind — also im abgeschalteten Zustand, in dem die Wand
> den zuletzt aufgenommenen Rahmen zeigt und deshalb wie ein laufendes Bild aussieht.
>
> Richtig bleibt der letzte Satz: aussagekräftig ist, ob `0x05600320/0x324` weiterwandern — und, noch
> besser, ob der Ringinhalt einem erzwungenen Reiz folgt.

~~Das ist **kein** Fehlerkennzeichen. Unsere eigenen Abzüge zeigen
Bit 31 = 1 im Ruhezustand (`01_lock`, `04`, `05`) und Bit 31 = **0** im laufenden, korrekten Betrieb
(`02_desc`, `03_source0` — Bild steht auf der Wand). `memory_agent_update_onoff` legt Maskenbit `0x8` im
gültigen HDMI-Fall in die **disable**-Maske (`v5 = v9|0x78`), nicht in die enable-Maske. Der Zustand
„Bit 31 = 0" ist also der gewünschte; er taugt nicht als Diagnose.~~ Aussagekräftig ist allein, ob
`0x05600320/0x324` weiterwandern.

### 4.4 Gibt es einen sauberen Neuanstoß ohne Kaltstart?

| Weg | Was er tut | Bewertung |
|---|---|---|
| Descriptor erneut schreiben | greift nur, wenn sich die SignalInfo unterscheidet; stellt genau die Module wieder, die einen passenden State haben | **kein vollständiger Reset**, und pro Boot verboten |
| Quelle wechseln (`THal_Vp_SetSource`) → `AppTopProjector_ApplyNewSource` (`0x8b108170`) | ruft `sub_8B107B04` (Gruppe `V_INCAP`) **nur beim allerersten Mal** (`obj+222 == 0`), danach nicht mehr; erzeugt aber einen echten Signalwechsel, der `HandleSignalEvent` mit „geändert" auslöst → Attribute neu → `V_INCAP` neu | **der einzige Firmware-eigene Weg**, der die Gruppe wieder ausführt; stellt aber nur States mit Treffer wieder her — **07.09. am Gerät gemessen: er trägt** (B2) |
| **HPD-Zyklus** (`PullHotPlug` DOWN → UP) — *07.09. nachgetragen* | in dieser Analyse nicht betrachtet; erzeugt über die Quelle denselben Signal-Neuaufbau ~~**gemessen**, 0,3 s genügen (`nachtlog/M4-hpd-dauer.md`)~~ → **hält der Nachprüfung nicht stand** (`nachtlog/M4-nachpruefung.md`, 11:55). M4 stützte sich allein auf das Freigabebit `0x06940928`; seine anderen zwei Spalten („Wand 0,00 % gegen Referenz", „INCAP zählt +61/s") können einen **Standrahmen nicht ausschließen** (`+0x104` zählt auch abgeschaltet weiter). Die Gegenprobe: aus dem Zustand „aktive Quelle ist VideoDec" gibt der HPD-Zyklus in **20 s nicht** frei, ein `SetSource(3)` danach sofort. M4s eigener Ausgangszustand ist seit `0099` nicht mehr herstellbar — **als Betriebsweg nicht verwenden** |
| `THal_Vp_Init` (Phase 2) | führt die `SYSTEM_INIT_*`-Gruppen (`always=2`) erneut aus — das ist die einzige **unbedingte** Registertabelle | setzt `0x400`, `0x104`, `0x800` Bit 0, `0x920–0x96C` zurück, **nicht** `0x824`/`0x84C` |
| Kaltstart | Hardware-Reset-Werte | **einziger vollständiger Weg** für `0x84C` & Co. |

**Antwort (belegt für die Mechanik, vermutet für die Praxistauglichkeit):** Einen Firmware-Pfad, der die
INCAP-Konfiguration vollständig auf Grundwerte zurückstellt, gibt es **nicht** — die zustandsselektierten
Module ohne `always`-State sind konstruktionsbedingt „einmal verstellt, bleibt verstellt".
Der beste verfügbare Teil-Reset ist ein **echter Quellenwechsel** (`SetSource` auf eine andere Quelle und
zurück), weil er über `HandleSignalEvent` die Gruppe `V_INCAP` erneut ausführt. ~~Ob das für den beobachteten
Klemmzustand reicht, ist **nicht belegt** (Board-Anfrage B2).~~

> **B2 ist gemessen (07.09., 22:52–22:56) — die Antwort ist ja.** `SetSource(1)` → `SetSource(3)`, ohne
> zweites Descriptor-Schreiben: `0x928` geht auf `0xE0020438` zurück, `+0x104` zählt wieder, und der
> **Ringinhalt folgt einem Reiz an der Quelle** (Gamma `1:0.2:0.2`: Y 118,5 → 61,5, Cr 140,4 → 177,2;
> auf der Wand 4,65 % der Bildpunkte, Rückkehr auf 0,00 %). Der Reiz ist hier der eigentliche Beleg —
> ein Registerbild allein könnte auch ein Standbild sein. Der Rundlauf ist strukturell folgenlos: der
> INCAP-Diff zwischen „gut" und „zurück" ergibt (ohne die frei laufenden Zähler) **null** Unterschiede.
>
> **Konsequenz für Paket D/E, korrigiert:** die Regel „Descriptor genau einmal pro Boot" bleibt richtig,
> aber sie ist keine Sackgasse mehr — für den Wiederanlauf gibt es zwei Stock-Wege, und `VIDIOC_S_INPUT`
> ist ohnehin einer davon. **Nicht gedeckt** ist der Fall, dass zwischendurch die **Geometrie** der Quelle
> wechselt (B2 sagt das ausdrücklich; wie sich das äußert, steht in `nachtlog/A6-4-aufloesungswechsel.md`).

**Konsequenz für Paket D/E, konservativ formuliert:** ~~Solange B2 nicht gemessen ist, gilt weiter~~
Es gilt weiter „Descriptor genau einmal pro Boot". Der Treiber sollte das **erzwingen**, nicht bloß
dokumentieren: Descriptor beim ersten Plane-Enable schreiben, Zeiger merken, beim Disable **nicht** löschen,
beim erneuten Enable **nicht** neu schreiben (doku/76 §13, Nachtplan Regel 6) — und für den Wiederanlauf den
Quellenwechsel oder einen kurzen HPD-Zyklus benutzen.

---

## 5. Offene Punkte

1. **Enum von `input_format` (Attribut `0x000a`).** Für `colorspace` ist der Mapper gefunden
   (`sub_8B12C098`, Tabelle `0x8B1F218C`); für `input_format` gibt es keine Mappertabelle im Abbild — der Wert
   wird gerechnet. Die Zuordnung `a0000/a0001/a0003/a0004/a0007/a000c` zu konkreten Eingangsformaten ist
   **unbelegt**. Für K1 nicht nötig (die untere Hälfte von `0x84C` ändert sich in unserem Betrieb nicht).
2. **Wer schreibt `0x069408F0…` / `0x06940930…` (die Ringadressen)?** Weder Code noch TSE — dieselbe Lage wie
   bei `0x05600320/0x324`. Auch das spricht für einen Hardware-Mechanismus, ist aber nicht mit derselben
   Sicherheit belegt (die Adressen stehen im Abzug korrekt, ohne dass eine Quelle gefunden wurde).
3. **`sub_8B191958`** schreibt `0x06940858/085C` mit Masken `0x2/0x10/0x20/0x20000/0x100000/0x200000` in einem
   `switch` über eine Kanal-/Port-Nummer (cases 16–21). Vermutlich eine Pfad-/Taktfreigabe pro Kanal; nicht
   weiter verfolgt, weil sie in unserem Betrieb nicht auftaucht.
4. ~~**Polarität von `0x06940824` Bit 31** ist über Tabelle + Farbmessung erschlossen, nicht direkt gemessen
   (Board-Anfrage B1).~~ **B1 ist gefahren (07.09., 23:16) und hat die hier angenommene Polarität
   widerlegt** (§2.2). Offen ist jetzt die Gegenrichtung: **welche** Stellung von Bit 31 die Matrix rechnen
   lässt — und ob die RGB→YUV-Wandlung überhaupt in dieser Stufe sitzt. Eine Messung dafür müsste den
   Ringinhalt bei **laufender** Capture in beiden Stellungen vergleichen; nach heutigem Stand ist die
   Stellung Bit 31 = 1 aber nur im abgeschalteten Zustand zu haben. Solange das so ist, ist die Frage mit
   dem Ring **nicht** entscheidbar.
5. **Deutung des Blocks `0x05600300…0x0560033F`** — OSD-AFBD-Instanz (ARM-Treibersicht) oder globales
   Flip-Zeigerpaar (Firmwaresicht)? Siehe 3.4; für Paket E folgenlos, aber offen. *(Der W1C-Status
   `0x05600328`/`0x05600368`, den `ge2d_dev.ko` bedient, ist in `dump_state.py` inzwischen enthalten —
   der AFBD-Block wird mit `0x1000` gelesen —, aber nie unter diesem Gesichtspunkt ausgewertet worden.)*
6. **Board-Anfrage B3 ist nicht gefahren.** Die Modellvorhersage aus §2.3/§2.4 — Descriptor-`color_format`
   ∈ {3, 5, 6} kippt `0x0694084C` auf `0x0C000C00` — ist die einzige Aussage dieser Seite, die eine
   **falsifizierende** Messung hätte und keine bekommen hat. Sie kostet einen Kaltstart und verbraucht den
   Descriptor (Vorschrift in `nachtlog/K1-K3-re.md`).
7. **Woran ein Geometriewechsel erkennbar wäre.** Weder der Vsync-Weg noch ein Capture-Interrupt meldet
   ihn; `SOURCE_CHANGE` feuert nicht (`nachtlog/A6-4-aufloesungswechsel.md`). Kandidaten sind die
   INCAP-Timing-Register und der Composition-Block `0x05000224`/`0x05000844` (doku/89).

---

## 6. Erzeugte Dateien

| Datei | Inhalt |
|---|---|
| `analyse/ida/ida_q27.py` | Displacement-Scan über alle Funktionen |
| `analyse/ida/ida_q28.py` | MMIO-Landkarte (Textscan, direkte `lui`-Zugriffe) |
| `analyse/ida/ida_q29.py` | Welche MMIO-Fenster die Firmware benutzt; Basiszeiger-Kandidaten |
| `analyse/ida/ida_q30.py` | ARM-physische Immediates im Peripheriebereich |
| `analyse/ida/ida_q31.py` | Konstantenverfolgung → aufgelöste Basiszeiger-Zugriffe (INCAP/AFBD/PROC/DE/LVDS) |
| `analyse/ida/ida_q32.py` | `$a0`-Auflösung an allen Aufrufen der MMIO-Zugriffsfunktionen (inkl. Delay-Slot) |
| `analyse/ida/ida_q33.py` | Registertabelle `0x8B1FE408` (DE-Schattenregister, Fehlspur) |
| `analyse/ida/ida_q34.py` | Dekompilate `sub_8B191958`, `memory_agent_*`, `EnterWaitingPipeLineReady`, `HandleSignalEvent` |
| `analyse/ida/ida_q35.py` | Farbraum-/Farbformat-Enums (`0x8B1F5154` ff.) |
| `analyse/ida/ida_q36.py` | Attribut-Mapper, Interrupt-Namensuche, Zustandsmaschine |
| `analyse/ida/ida_q37.py` | Zustandsübergänge, `memory_agent`-vtable, `InterruptSources_Init` |
| `analyse/ida/ida_q38.py` | `g_irq_to_swint_table` (63 MIPS-Interruptquellen mit Klartextnamen) |
| `analyse/ida/ida_q39.py` | MIPS-ISR-Umfeld |
| `analyse/ida/ida_q40.py` | Aufrufer der Zustandseintritte, `sub_8B12C098` |
| `analyse/ida/ida_q41.py` | `ApplyNewSource`, Nutzer der TSE-Gruppennamen |
| `re/captures/weltneuheit/k1k3-q27…q41-*-20260907.log` | Rohausgaben dazu (15 Dateien, Liste im Teillog) |
| `re/captures/weltneuheit/k1k3-tse-alle-module-20260907.txt` | `tools/tse_dump.py --all` über die Board-TSE |

Die Datenbankkopie liegt in `analyse/ida/db-k1k3/` (das Original in `re/ida/weltneuheit/re_chain/` wurde
nicht geöffnet).
