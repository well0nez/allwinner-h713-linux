# 85 — PQ-Register der MIPS-Firmware (K5) und Vorstudie Compositing (K6)

**Stand 07.09.2026, Nacht.** Reine statische Analyse (idalib, Firmware-Abbild, vorhandene Aufzeichnungen);
**kein Board angefasst**. Grundlage: `doku/78-nachtplan-hdmi-switch.md` Abschnitt 3 „K", Fragen 5 und 6.
Alle Skripte: `analyse/ida/ida_q40.py` … `ida_q58.py`, Rohausgaben in `re/captures/weltneuheit/k5-*-20260907.*`
und `k6-*-20260907.log`. Gearbeitet wurde auf einer **Kopie** der Datenbank (`analyse/ida/db-k5k6/`), das
Original wurde nie geöffnet.

Adressen sind, wo nicht anders gesagt, **ARM-physisch**. MIPS-Sicht = ARM + `0xB5000000`.

---

## 0. Korrekturstand 07.09.2026 — was das Gerät bestätigt und was es widerlegt hat

Diese Seite entstand aus **statischer** Analyse. Am selben Tag ist ihr Kern am Board nachgemessen worden
(`nachtlog/K5-board-verifikation.md`, 22:45–22:59). Die widerlegten Aussagen bleiben unten im Text stehen —
durchgestrichen und mit Kasten daneben —, damit sichtbar bleibt, **was** korrigiert wurde.

**Widerlegt:**

| Aussage dieser Seite | Stand jetzt | Beleg | Abschnitt |
|---|---|---|---|
| „`0x05140508` ist **nicht** das Register von `SetSaturation` — zwei verschiedene, zusätzliche Regler" | **falsch. Es ist derselbe Regler.** Ein einziger RPC schreibt beide Register; die Firmware bildet linear ab: `Gain = floor(Argument × 1,28)`. Die Vorgabe `0x4C` entspricht `SetSaturation 60` | `nachtlog/K5-board-verifikation.md` §f (fünf Messpunkte 0/50/59/60/100) | §A.7 |
| „Unsere Registerabzüge enden bei `0x050000FC`" | **falsch.** `dump_state.py` las `DE0` schon damals mit `0x400`, die Abzüge enden bei `0x050003FC` — die Hälfte des Composition-Blocks stand längst in jedem Abzug (heute `0x1000` plus PQ-Block) | `doku/89-composition-block.md`; nachzählbar in `ours-20260906-source0/01_lock.txt` und `ours-20260907-nacht/00-ausgangszustand/nacht-00-vor-A.txt` | §A.3 |
| „Die Umrechnung Benutzerwert → Registerwert macht die ARM-Seite mit den Kurven aus `pq_factory_extern.ini`" | **trägt nicht.** Das RPC-Argument läuft 0…100 und steht 1:1 im Register; die Werkskurven laufen bis 192 bzw. 3588. Wo die Kurve wirkt, ist **offen** | `nachtlog/G-korrektur-saettigung.md`, doku/81 §3.2 | §A.9 |

**Am Gerät bestätigt** — und zwar so, dass es hätte scheitern können:

| Befund | Messung |
|---|---|
| Der Block `0x05001000…` ist der, den die PQ-RPCs bedienen | `SetContrast 20/80/100` → `0x05001234` = `0x00140000`/`0x00500000`/`0x00640000`. Feldlage und Register genau wie vorhergesagt |
| Die PQ-Stufe liegt **im Weg unseres Source-0-Bildes** (§A.8 war „sehr wahrscheinlich") | Kontrast 0 → 100 verändert **12,16 %** der Bildpunkte auf der Wand (mean 11,27) |
| Die Schreibsperre `0x0500121C` steht offen | `0x00000000`, unterste vier Bit `0x0` — die Firmware verwirft PQ-Schreibzugriffe nicht |
| `SetBrightness` = ID 3 = `0x05001234[15:0]` (§A.6 war „vermutet") | `SetBrightness 100` → `0x00000064`, und es **wirkt aufs Bild**; der Stellbereich ist **0…100**. *(Korrektur 07.09., 11:25: hier stand „Aber: 0,00 % Bildwirkung". Diese Messung war **ungültig** — fast weiße Vorlage, siehe §A.6.)* |
| `UIvalueMapping` bildet identisch ab (§A.9) | Argument 20 → `0x14`, 50 → `0x32`, 100 → `0x64` bei Kontrast, Helligkeit und Sättigung |

*Zur Einordnung des vierten Belegs in `K5-board-verifikation.md` (b): dass `0x0500123C` = 2 und
`0x05001248` = 1 gerade die Werte sind, die `prep_after_boot.sh` per `SetDCI 2` / `SetSNR 1` gesetzt hat, ist
ein Indiz — aber ein schwaches, weil 1 und 2 auch zufällig dastehen könnten. Die tragende Messung ist die
Kontrastreihe mit drei verschiedenen Werten und der Negativkontrolle.*

**Nicht gemessen** (weiterhin nur statisch belegt): `SetHue`, `SetSharpness`, die sechs
Weißabgleich-Felder und `SetGamma` Teil 2.

---

## Teil A — K5: Wo landen Helligkeit und Kontrast im Register?

### A.1 Kurzantwort

Die PQ-RPCs schreiben **nicht** in das PROC-Fenster `0x05140xxx`, sondern in einen bisher nie ausgelesenen
Registerblock **ARM `0x05001000` … `0x050015FC`** (384 × 32 Bit) innerhalb des Fensters, das unsere Dumps
`DE2_NR_base @ 0x05000000` nennen.

Die Spalte „Beleg" meint **statisch aus dem Abbild belegt**. Welche Zeilen zusätzlich **am Gerät** gemessen
sind, steht in Abschnitt 0.

| RPC | Item-ID | Register (ARM) | Feld | Beleg |
|---|---|---|---|---|
| `SetBrightness` | 3 | `0x05001234` | `[15:0]` | ~~**vermutet** (siehe A.6)~~ → **am Gerät gemessen** (07.09.), schreibt sein Register ~~und wirkt nicht aufs Bild~~ → **und wirkt**, Stellbereich **0…100** (Korrektur 11:25, siehe A.6) |
| `SetContrast` | 4 | `0x05001234` | `[31:16]` | belegt — **am Gerät gemessen und wirksam** (12,16 %) |
| `SetSaturation` | 5 | `0x05001238` | `[15:0]` | belegt — **am Gerät gemessen**; derselbe RPC schreibt zusätzlich `0x05140508` (§A.7) |
| `SetHue` | 6 | `0x05001238` | `[31:16]` | belegt |
| `SetSharpness` | 7 | `0x05001228` | `[23:8]` | belegt |
| `SetBlackExtension` | 8 | — (Tabelleneintrag, Adresse 0) | `[31:24]` wäre `0x05001228` | belegt: kein Registerschreiben |
| `SetDCI` | 9 | `0x0500123C` | `[7:0]` | belegt — am Gerät steht dort die von `prep_after_boot.sh` gesetzte 2 (schwaches Indiz, Abschnitt 0) |
| `SetSNR` | 12 | `0x05001248` | `[7:0]` | belegt — ebenso, Wert 1 |
| `SetTNR` | 13 | — (Tabelleneintrag, Adresse 0) | `[15:8]` wäre `0x05001248` | belegt: kein Registerschreiben |
| `SetWhiteBalance[0] r_gain` | 35 | `0x05001274` | `[15:0]` | belegt |
| `SetWhiteBalance[1] g_gain` | 36 | `0x05001274` | `[31:16]` | belegt |
| `SetWhiteBalance[2] b_gain` | 37 | `0x05001278` | `[15:0]` | belegt |
| `SetWhiteBalance[3] r_offset` | 38 | `0x05001278` | `[31:16]` | belegt |
| `SetWhiteBalance[4] g_offset` | 39 | `0x0500127C` | `[15:0]` | belegt |
| `SetWhiteBalance[5] b_offset` | 40 | `0x0500127C` | `[31:16]` | belegt |
| `SetGamma` (Teil 2) | 0x58 = 88 | `0x05001280` | `[15:0]` | belegt |
| `SetGamma` (Teil 1) | 0x2A = 42 | — (Adresse 0) | `[31:16]` wäre `0x05001280` | belegt: kein Registerschreiben |
| `SetPictureMode` | — | kein UIMapping | — | lädt ein ganzes Preset (A.5) |
| `SetVideoRange` | — | kein UIMapping | — | eigener Pfad (A.5) |
| `SetLowLatencyMode` | — | kein UIMapping | — | Nachricht 27 an den PQ-Thread |
| `SetColorManagement` | — | kein UIMapping | — | Nachricht 21, Zeiger im Shmem |

Die vollständige Tabelle aller 89 Item-IDs mit Register, Maske, Bitlage und Shift liegt in
`re/captures/weltneuheit/k5-uimapping-tabelle-20260907.txt`.

### A.2 Der Weg vom RPC zum Register (belegt, Schritt für Schritt)

**1. Die Routinentabelle liegt statisch im Abbild.** In `display.bin` steht ab Datei-Offset `0x12CF70`
eine Tabelle mit 81 Einträgen à `0x68` Byte:

```
struct { char name[0x5C]; u32 null; u32 flag; u32 handler_va; }
```

Ladebasis ist `0x8B100000 + Datei-Offset` (das Segment der IDA-DB ist `0x8B100000 … 0x8B232B18`, exakt so
lang wie die Datei); die Tabelle liegt damit bei VA `0x8B22CF70`. Vollständiger Abzug:
`re/captures/weltneuheit/k5-calltable-static-20260907.log`.

Gegengeprüft am **Stock-elog** `re/captures/weltneuheit/elog-stock-LIVE.bin`:

```
THal_Vp_SetBrightness_1_000(), pRoutine:8B10A4FC, chan:0
THal_Vp_SetBrightness_1_000(), ..., FuncID:7221d017, ...
```

`0x8B10A4FC` ist genau der Wert, den die statische Tabelle liefert; `7221d017` ist die comp_id aus
`mainline/docs/reference/cpu-comm-call-table.md`. Auch `SetSource → 0x8B10A218`, `GetSource → 0x8B10A244`,
`GetSignalInfo → 0x8B109B40`, `Wce_SetWindow → 0x8B109D54`, `SetBacklightLevel → 0x8B10A4C8` stimmen mit
der Laufzeittabelle überein. Damit ist die Tabelle **ohne laufendes Gerät** lesbar.

**2. Der Handler legt eine Nachricht in eine Warteschlange.** `THal_Vp_SetBrightness` (`0x8B10A4FC`) ruft
`sub_8B1494CC` in `./thal_display_pq.cpp`:

```c
elog_output(4, ..., "THal_Vp_SetBrightness", 50, "%s() ENTER", ...);
v3[0] = 17;          // Kommando
v3[1] = a1;          // Wert
sub_8B106BEC(v3);    // -> Objekt bei MEMORY[0x8B253570], vtable +12
```

Kommandonummern (alle aus `thal_display_pq.cpp` dekompiliert,
`re/captures/weltneuheit/k5-pq-chain-20260907.log`):

| Kdo | RPC | Kdo | RPC |
|---|---|---|---|
| 17 | Brightness | 24 | BlackExtension |
| 18 | Contrast | 25 | TNR |
| 19 | Saturation | 26 | SNR |
| 20 | Hue | 27 | LowLatencyMode |
| 21 | ColorManagement | 28 | WhiteBalance |
| 22 | Sharpness | 29 | Gamma |
| 23 | DCI | | |

**3. Der PQ-Thread ruft den Rückruf in `hal_func.cpp`.** Belegt durch das Stock-elog, das die beiden Zeilen
unmittelbar nacheinander zeigt:

```
D/hal (./thal_display_pq.cpp 189)THal_Vp_SetTNR() ENTER
I/app (./hal_func.cpp 505)OnHalPqTNRChange
```

Die Rückrufe liegen bei `0x8B10C0A0` … `0x8B10C91C`
(`re/captures/weltneuheit/k5k6-onhalpq-afbd-lvds-20260907.log`).

**4. Der Rückruf ruft `UIvalueMapping`.** `sub_8B17F3F8`, `PQManage/UIMapping.cpp`, Signatur
`UIvalueMapping(u32 itemID, u32 inValue, u32 *pOut, int doMap)`. Kern:

```c
v11 = &dword_8B2313C0[3 * itemID];
v12 = *((BYTE *)v11 + 8);            // Shift
v13 = *v11;                          // Registeradresse (ARM-phys)
if ((v8 & 0x100) == 0)
    writel_masked(v13, v11[1], v6 << v12);     // v11[1] = Maske
```

`writel_masked(reg, mask, val)` (`0x8B17FD58`) ist der bekannte Read-Modify-Write mit
`ptr = (reg + 0xB5000000) | 0x20000000`, abgesichert durch `IsInvalidRegAddr` — Registeradresse 0 bedeutet
also **kein Schreibzugriff**.

Die Item-IDs stehen wörtlich in den Rückrufen:

```
OnHalPqContrastChange        -> UIvalueMapping(4u,  ...)
OnHalPqSaturationChange      -> UIvalueMapping(5u,  ...)
OnHalPqHueChange             -> UIvalueMapping(6u,  ...)
OnHalPqSharpnessChange       -> UIvalueMapping(7u,  ...)
OnHalPqBlackExtensionChange  -> UIvalueMapping(8u,  ...)
OnHalPqDCIChange             -> UIvalueMapping(9u,  ...)
OnHalPqSNRChange             -> UIvalueMapping(0xCu, ...)
OnHalPqTNRChange             -> UIvalueMapping(0xDu, ...)
```

(`re/captures/weltneuheit/k5-uimapping-caller-20260907.log`.) `THal_Vp_SetWhiteBalance` (`0x8B14A790`) ruft
`UIvalueMapping` in einer Schleife mit den IDs 35…40, `THal_Vp_SetGamma` (`0x8B14A9AC`) mit `0x2A` und `0x58`.

**5. Die Tabelle `dword_8B2313C0`.** 89 Einträge à 12 Byte, `{u32 reg; u32 mask; u8 shift;}`. Maske und Shift
stehen im Abbild, die **Registerspalte ist im Abbild 0** und wird beim Start von `sub_8B1024A4` gefüllt
(dessen Dekompilat, `re/captures/weltneuheit/k5-uimapping-init-20260907.log`, liefert die Adressen; die
Zusammenführung steht in `k5-uimapping-tabelle-20260907.txt`).

### A.3 Der Registerblock 0x05001000 … 0x050015FC

`sub_8B1024A4` lädt seine Adressen aus einem konstanten Feld ab VA `0x8B1FE408`. Dieses Feld ist über
**384 Einträge exakt linear**:

```
addr[i] = 0x05001000 + 4*i,  i = 0 … 383      (danach beginnen Strings)
```

Das ist die „NEST-SW-Register"-Datei der Firmware: 384 32-Bit-Register bei ARM `0x05001000 … 0x050015FF`.
Die zugehörigen Namen (`NEST_SW_REG_*`, 83 Stück im Abbild) hängen an einer zweiten Deskriptortabelle
(VA `0x8B23002C … 0x8B230F7C`, 197 Einträge à `0x14`, Layout aus `printRegAddressAndVal` @ `0x8B1786C0`
belegt); ihr Abzug liegt in `re/captures/weltneuheit/k5-nest-swreg-map-20260907.txt`. Auch dort ist die
Adressspalte für die `NEST_SW_REG_*`-Einträge zur Laufzeit gefüllt — die konkreten Adressen der PQ-Items
stammen deshalb aus `sub_8B1024A4`, nicht aus dieser Tabelle.

Zwei Steuerworte im selben Block, aus `UIvalueMapping` belegt:

| Register | Bedeutung |
|---|---|
| `0x0500121C` | PQ-Betriebsart. Wird bei **jedem** `UIvalueMapping` gelesen. `(wert & 0xF) == 0xA` → Registerschreiben wird **übersprungen**; `wert & 0x100` → statt zu schreiben wird gelesen; `wert < 0` (Bit 31) → ausführliches elog („`======= dwItemID: %d, inValue: %d …`") |
| `0x050012DC` | wird nur für Item-ID 0 nachgeführt |

**Dieser Block ist in keinem unserer Registerabzüge enthalten.** ~~`re/captures/weltneuheit/stock-post-hdmi.txt`
beginnt mit `=== DE2_NR_base @ 0x05000000 ===` und endet bei `0x050000FC`.~~ Deshalb ist er bisher nie
aufgefallen. Das ist die wichtigste einzelne Handlungsempfehlung aus K5 (Messvorschrift im Teillog).

> **Korrektur 07.09.2026.** Der **erste** Satz stimmt: der PQ-Block war in keinem Abzug, und der Fund
> steht. Die **Begründung** stimmt nicht. Der zitierte Abzug `stock-post-hdmi.txt` reicht tatsächlich nur
> bis `0x050000FC` — er stammt aber aus einem älteren Werkzeuglauf mit `0x100`-Fenster. **Unsere eigenen
> Abzüge** (`dump_state.py`, Block `DE0` = `(0x05000000, 0x400)`) enden bei `0x050003FC`; nachzählbar in
> `ours-20260906-source0/01_lock.txt` und `ours-20260907-nacht/00-ausgangszustand/nacht-00-vor-A.txt`
> (256 Zeilen im DE0-Block).
>
> **Warum das nicht folgenlos war:** aus dem falschen Endpunkt folgte der Eindruck, auch der
> Composition-Block bei `0x05000000` sei unerfasst. Er war zur Hälfte längst da — Skalierverhältnis
> `0x05000174`, Geometrie `0x05000224` und die DE-Schreibkanäle `0x05000278`/`0x050002B8` stehen in jedem
> Abzug. Gefehlt haben nur die Pitch-Register ab `0x05000444` und dieser PQ-Block
> ([doku/89](89-composition-block.md)).
>
> **Erledigt:** `dump_state.py` liest `DE0` jetzt mit `0x1000` und den PQ-Block `(0x05001000, 0x600)`
> zusätzlich; beides ist Teil des Standardabzugs und liegt im Repo, nicht nur auf dem Board.

### A.4 Was die IDs 0…13 sonst noch sagen

Aus der Tabelle (`k5-uimapping-tabelle-20260907.txt`), Auszug:

```
ID  Register     Maske       Bits
 0  0x05001228   0x000000ff  [ 7: 0]
 3  0x05001234   0x0000ffff  [15: 0]     <- Helligkeit (vermutet)
 4  0x05001234   0xffff0000  [31:16]     <- Kontrast   (belegt)
 5  0x05001238   0x0000ffff  [15: 0]     <- Sättigung  (belegt)
 6  0x05001238   0xffff0000  [31:16]     <- Farbton    (belegt)
 7  0x05001228   0x00ffff00  [23: 8]     <- Schärfe    (belegt)
 8  ----------   0xff000000  [31:24]     <- BlackExtension, nicht abgebildet
 9  0x0500123c   0x000000ff  [ 7: 0]     <- DCI        (belegt)
12  0x05001248   0x000000ff  [ 7: 0]     <- SNR        (belegt)
13  ----------   0x0000ff00  [15: 8]     <- TNR, nicht abgebildet
```

*(Die Klammern in diesem Auszug meinen „statisch belegt". Stand 07.09. **am Gerät**: ID 3 Helligkeit ist
nicht mehr „vermutet", sondern gemessen — schreibt **und wirkt** (Korrektur 11:25, §A.6); ID 4 Kontrast, ID 5 Sättigung, ID 9
DCI und ID 12 SNR sind am Gerät wiedergefunden; ID 6 Farbton und ID 7 Schärfe sind es nicht. Abschnitt 0.)*

Die IDs 17…26 bilden fünf `(lo, hi)`-Paare, bei denen jeweils nur die untere Hälfte eine Adresse hat
(`0x05001250`, `…54`, `…58`, `…5C`, `…60`); die obere Hälfte ist 0. Das deckt sich mit den Namenspaaren
`mp_*`/`pp_*` (Main Picture / Sub Picture) im Abbild und mit dem Stock-elog, das beim Start meldet:
`Can not get PP BlackExtensionModuleID`, `Can not get PP NRModuleID`, `Can not get PP MpegNRModuleID`.
**Auf diesem Gerät existiert nur die Hauptbild-Kette.**

### A.5 RPCs ohne Registerpfad

- `SetPictureMode` (`0x8B14A284`) schreibt kein Register, sondern vergleicht mit `MEMORY[0x8B272974]` und
  ruft bei Änderung `sub_8B12BB68` + `sub_8B1098BC` — ein Preset-Wechsel, der die Einzelwerte anschließend
  über die obigen Pfade neu setzt.
- `SetVideoRange` (`0x8B14A4FC`) → `sub_8B12BB1C` + `sub_8B1097B4`, eigener Pfad.
- `SetTNR`, `SetBlackExtension` haben eine Item-ID, aber **keine Registeradresse**: sie wirken nur über das
  PQ-Treiberobjekt (`vtable+44` bzw. `+16` auf dem Objekt aus `sub_8B15C5B4`), das die TSE-Module bedient.
  Das Stock-elog zeigt für Gamma und DCI beim Start `Can not get MP GAMMAModuleID` und `mp_dci_data is NULL`
  — auf diesem Gerät sind also nicht alle PQ-Module bestückt.
- Der zweite, parallele Weg für Helligkeit/Kontrast/Farbton/Sättigung/Schärfe/Weißabgleich ist die
  **TSE-Namensschnittstelle**: `TBrightness::Write` (`0x8B17AE10`) usw. rufen `(*(vtbl+36))(obj, "mp_brightness", wert)`
  mit der Namensliste bei `0x8B200ED8`
  (`mp_brightness, pp_brightness, mp_contrast, pp_contrast, mp_tint, pp_tint, mp_saturation, pp_saturation,
  mp_sharpness, pp_sharpness, wb_r_gain, wb_g_gain, wb_b_gain, wb_r_offset, wb_g_offset, wb_b_offset`).
  Auch diese Namen sind `NEST_SW_REG`-Namen und landen im selben Block `0x05001xxx`.

### A.6 Was an Helligkeit noch fehlt — ehrlich

`OnHalPqBrightnessChange` **existiert als Zeichenkette** (`0x8B1EBFB8`), aber es gibt in diesem Abbild
**keine Funktion, die sie lädt**: eine Dekompilat-Suche über `0x8B100000 … 0x8B125000` findet elf
`OnHal…`-Rückrufe (WhiteBalance, Gamma, Contrast, Saturation, Hue, Sharpness, DCI, BlackExtension, TNR,
SNR, LowLatencyMode) — Brightness ist nicht darunter, und `XrefsTo(0x8B1EBFB8)` ist leer.
Ebenso ruft **keine** Funktion `UIvalueMapping` mit ID 3.

Die Zuordnung *Helligkeit = ID 3 = `0x05001234[15:0]`* stützt sich deshalb auf drei Indizien, nicht auf
einen Aufruf:

1. Die belegten IDs sind lückenlos **4 Kontrast, 5 Sättigung, 6 Farbton, 7 Schärfe** — genau die Reihenfolge,
   in der der Hersteller seine Werte selbst führt (`pq_picturemode.ini`:
   `brightness, contrast, saturation, hue, sharpness, …`). ID 3 ist der freie Platz davor.
2. ID 3 und ID 4 teilen sich **dasselbe Register** `0x05001234` (untere/obere Hälfte) — Helligkeit und
   Kontrast liegen in solchen Blöcken üblicherweise paarweise, so wie Sättigung/Farbton in `0x05001238`.
3. Die Wertabbildung `sub_8B17EE80` hat für ID 3 einen eigenen vtable-Platz (`+12`), ist also ein real
   vorgesehenes Item und kein Loch.

~~**Bis zur Messung am Board gilt das als Vermutung.**~~ Die Messvorschrift steht im Teillog.

> **Gemessen am 07.09.2026 — die Zuordnung stimmt, die Wirkung fehlt.** *(Der zweite Halbsatz ist am
> selben Tag um 11:25 widerlegt worden; der Block bleibt als Protokoll stehen, die Korrektur steht
> darunter.)*
> `SetBrightness 100` → `0x05001234 = 0x00000064`; nach Abzug der frei laufenden Zähler ändern sich genau
> zwei Wörter (`0x05001234` und `0x05001038`). Helligkeit und Kontrast teilen sich das Register wie
> vorhergesagt, Helligkeit in `[15:0]`. Die drei Indizien oben haben getragen.
>
> **Aber die Wand ändert sich dabei nicht:** 0,00 % der Bildpunkte > 25 (mean 2,51) — bei genau dem
> Stellweg, der beim Kontrast 12,16 % ergibt. Der Wert wird geschrieben und kommt nicht an. Das ist ein
> Befund, kein Messfehler: der Vergleich mit dem Kontrast ist die Kontrolle, die zeigt, dass die Methode
> Wirkung überhaupt sieht.
>
> Vermutete Ursache (**nicht** belegt): das Helligkeitsmodul ist auf diesem Gerät nicht bestückt — dazu
> passen Stocks Startmeldungen `Can not get MP GAMMAModuleID` und `mp_dci_data is NULL`.
>
> **Und eine Frage, die die Messung neu aufwirft:** dieser Abschnitt zeigt statisch, dass **keine**
> Funktion `OnHalPqBrightnessChange` lädt und **keine** `UIvalueMapping` mit ID 3 ruft. Trotzdem schreibt
> `SetBrightness` das Register. Also fehlt der Weg dorthin in dieser Analyse. Der naheliegende Kandidat ist
> die **TSE-Namensschnittstelle** aus §A.5 (`TBrightness::Write` → `mp_brightness`, ebenfalls ein
> `NEST_SW_REG`-Name im selben Block) — geprüft ist das nicht. Offen bleibt: **wer** schreibt
> `0x05001234[15:0]`, und was ändert `0x05001038` dabei mit (bei Kontrast *und* Helligkeit
> `0xc003003c → 0xc06a003c`, Deutung offen)?
>
> ~~**Für Paket I:** `V4L2_CID_BRIGHTNESS` darf nicht als Control angeboten werden — es täte nichts.~~

**Korrektur 07.09.2026, 11:25 — die Helligkeit wirkt doch; die Messung oben war ungültig.**

Nachgemessen gegen **dunkles Material** (Zuspieler auf 20 % heruntergeregelt) statt gegen die fast weiße
Seite: std im ROI 12,6 → 22,7, p95 151 → 185, **monoton von 0 bis 100 und darüber exakt flach**; drei Werte
je zweimal angefahren, jedes Mal dieselben Kennzahlen ([`nachtlog/I0-helligkeit-nachgemessen.md`](nachtlog/I0-helligkeit-nachgemessen.md)).

Warum die alte Messung nichts zeigen konnte: Helligkeit verschiebt den **unteren** Teil der Kennlinie. Auf
einer Fläche nahe am oberen Anschlag ist da nichts zu verschieben — das Kriterium „0,00 % der Bildpunkte
über 25 Graustufen Unterschied" **konnte gar nicht anschlagen**. Dieselbe Quelle sagt das über sich selbst:
`K5-board-verifikation.md` (f) begründet die kleine Sättigungswirkung damit, dass „die Quellseite
überwiegend weiß und grau" sei. Der Kontrast-Gegenwert 12,16 % ist **kein** Gegenbeleg: er zeigt nur, dass
Kontrast auf weißem Material wirkt und Helligkeit dort nicht — genau das ist von beiden Reglern zu erwarten.
Das ist das Spiegelbild der Projektregel: ein Kriterium, das nicht **gelingen** konnte.

Damit fällt auch die vermutete Ursache: `Can not get MP GAMMAModuleID` und `mp_dci_data is NULL` nennen das
**Gamma-** und das **DCI-Modul** (dieselbe Seite sagt in §0 und weiter unten ausdrücklich, für
Helligkeit/Kontrast/Sättigung gebe es keine solche Meldung) — der Schluss „also ist das Helligkeitsmodul
nicht bestückt" war eine Analogie, keine Messung.

**Für Paket I:** `V4L2_CID_BRIGHTNESS` **anbieten, Bereich 0…100** (nicht 0…255 — über 100 ändert sich
nichts mehr, gemessen). Offen bleibt allein die Frage aus dem Absatz darüber: **wer** schreibt
`0x05001234[15:0]`, wenn keine Funktion `OnHalPqBrightnessChange` lädt — Kandidat ist die
TSE-Namensschnittstelle aus §A.5. Die Kennlinie selbst ist ungemessen (Tageslicht, Belichtungsautomatik) und
muss der Treiber nicht kennen.

### A.7 ~~Achtung: `0x05140508` ist *nicht* die PQ-Sättigung~~ — **widerlegt am Gerät**

> **Widerrufen am 07.09.2026 durch Messung** (`nachtlog/K5-board-verifikation.md` §f). Es ist **derselbe**
> Regler. Ein einziger RPC schreibt **beide** Register:
>
> | `SetSaturation` | `0x05001238` (PQ-Block) | `0x05140508` (Chroma-Gain) |
> |---|---|---|
> | 0 | `0x00000000` | `0x14000000` (Gain `0x00`) |
> | 50 | `0x00000032` | `0x14400000` (Gain `0x40` = 64) |
> | 59 | — | `0x144B0000` (Gain `0x4B` = 75) |
> | **60** | — | **`0x144C0000` (Gain `0x4C` = 76)** |
> | 100 | `0x00000064` | `0x14800000` (Gain `0x80` = 128) |
>
> Die Firmware bildet das Argument **linear** ab: `Gain = floor(Argument × 1,28)`. **`floor`, nicht
> `round`** — und das ist gemessen, nicht gewählt: 59 × 1,28 = 75,52, gemessen `0x4B` = 75. Die beiden
> Punkte 59/60 sind genau die Stelle, an der sich die beiden Rundungsarten unterscheiden; die Messreihe
> hätte hier scheitern können und tut es nicht.
>
> **Der Ruhewert `0x4C` ist keine Kalibriergröße, sondern die Firmware-Vorgabe** und entspricht exakt
> `SetSaturation 60` (`prep_after_boot.sh` ruft `SetSaturation` gar nicht auf). Die frühere Zuordnung
> „`0x4C` ↔ Benutzerwert 50" (doku/77 §4) ist damit ebenfalls hinfällig.
>
> **Wirkungsort:** der Gain sitzt **hinter** dem Ring — bei `SetSaturation` 60 → 100 bleibt der
> Ringinhalt unverändert (Cb 122,2 / Cr 140,4), auf der Wand ändern sich 0,56 % der Bildpunkte (mean 3,54;
> klein, weil die Quelle überwiegend weiß und grau ist).
>
> **Was von diesem Abschnitt stehen bleibt:** `0x05140508` hat wirklich **keinen** Eintrag in der
> UIMapping-Tabelle, und die statische Xref-Suche findet dafür wirklich **keinen** Schreiber. Das ist
> jetzt keine Trennung zweier Regler mehr, sondern ein Hinweis auf einen **zweiten, nachgelagerten
> Schreibzugriff** desselben RPC, der registerindirekt (Basis + Offset) erfolgt und deshalb statisch
> unsichtbar bleibt. **Welche Funktion ihn ausführt, ist offen.**

~~Der belegte Anker aus `analyse/hdmi-seq/pq_saturation.py` — Chroma-Gain `0x05140508[23:16]`, Stock `0x4C` —
liegt im Block, den unsere Abzüge `DE2_mixer_proc @ 0x05140000` nennen. Er hat **keinen Eintrag** in der
UIMapping-Tabelle, und `SetSaturation` schreibt ihn nicht: `SetSaturation` geht über Item-ID 5 nach
`0x05001238[15:0]` und zusätzlich über den TSE-Namen `mp_saturation`.~~ *(Der erste Teil gilt, der zweite
nicht — siehe Kasten.)*

Eine statische Xref-Suche über das ganze PROC-Fenster (`analyse/ida/ida_q40.py`,
`re/captures/weltneuheit/k5-pq-xrefs-20260907.log`) findet für `0x05140508` **keinen** Schreiber — das
Register wird registerindirekt gesetzt (Basis + Offset), ~~vermutlich beim Aufbau der Route~~ und zwar,
wie die Messung zeigt, auf dem Weg von `SetSaturation`.

~~Für Paket G heißt das: `pq_saturation.py` verstellt einen **anderen, zusätzlichen** Regler als die
Stock-PQ-RPC. Beide sind gültig, aber sie sind nicht dasselbe, und die Doku sollte das trennen.~~

**Für Paket G heißt es das Gegenteil** — und das ist am 07.09. umgesetzt worden
(`nachtlog/G-korrektur-saettigung.md`, [doku/81](81-pq-datenmodell.md) Fassung 2):

* `h713-pq` gibt jetzt das **RPC-Argument** aus statt eines selbst gerechneten Registerwerts; die
  Umrechnung bleibt der Firmware überlassen, wie bei Stock. `gain`/`gain_register` sind Kontrollwerte.
* `analyse/hdmi-seq/pq_saturation.py` ist **zurückgezogen** (liest nur noch): seine Formel
  `Register = 0x4C × Kurve(u) / 96` ist widerlegt — sie gab für `vivid` `0x5C` statt `0x4C` aus —, und der
  `/dev/mem`-Poke setzte nur die eine Hälfte des Reglers, während der RPC beide setzt.

### A.8 Wirken die MIPS-PQ-RPCs auf unseren AFBD-Source-0-Pfad?

~~**Antwort: sehr wahrscheinlich ja — mit belegten Teilstücken und einem offenen letzten Schritt.**~~

> **Am Gerät entschieden, 07.09.2026: ja.** Der offene letzte Schritt ist gemessen — `SetContrast` 0 → 100
> verändert **12,16 %** der Bildpunkte auf der Wand (mean 11,27, `hell` 254719 → 303360). Der kleinere
> Stellweg 20 → 80 ergibt 0,84 %; das ist kein Widerspruch, sondern der kleinere Weg. Damit liegt die
> MIPS-PQ-Stufe nachweislich im Weg unseres Source-0-Bildes, und Paket **I** hat seine Grundlage.
>
> Von den drei unten als „nicht belegt" benannten Punkten sind zwei erledigt: die Schreibsperre
> `0x0500121C` steht auf `0x00000000` (kein Verwerfen), und die Bestückung ist für den Kontrast durch die
> Wirkung selbst beantwortet. ~~**Offen bleibt sie für die Helligkeit** — dort wird geschrieben und nichts
> wirkt (§A.6).~~ **Auch für die Helligkeit erledigt** (Korrektur 11:25 in §A.6): sie wirkt, Stellbereich
> 0…100.

Belegt:

1. Unsere Kette ist HDMI-RX → INCAP → Ring → **AFBD Source 0** → … → PROC → Panel (doku/76 §10, live gemessen).
2. Der AFBD wird von **`NRWinNode_AfbdConfigure`** (`0x8B1A3C58`) programmiert. Der AFBD gehört damit zum
   **NR-Window-Node**, dessen Registerfenster bei `0x05000000` liegt — in unseren eigenen Abzügen
   `DE2_NR_base @ 0x05000000` benannt (`re/captures/weltneuheit/stock-post-hdmi.txt`, Zeile 1).
3. Der PQ-Registerblock `0x05001000 … 0x050015FC` liegt **innerhalb dieses Fensters**.

   > **Nachtrag 07.09.2026 — dasselbe Fenster trägt noch etwas Drittes.** `0x05000000` ist zugleich
   > cstengers **Composition-Block**, der das Panel dimensioniert (Commit `8f1aadd`). „DE2_NR_base",
   > „DE-Schreibkanäle" (Nachtplan §7) und „Composition" sind **dasselbe Registerfenster**, aus drei
   > Richtungen benannt. An unserem Board gelesen: `0x05000224 = 0x04380780` (1920 × 1080),
   > Skalierverhältnis `0x05000174 = 0x00600060` (1:1), Pitch `0x05000844 = 0x07800067` (1920) — bei
   > cstenger stand dort 852 × 480. Vollständig in [doku/89](89-composition-block.md).
   > Für diesen Abschnitt heißt das: die Kette AFBD → PQ → Panel wird in diesem einen Fenster
   > **konfiguriert**, nicht nur die PQ. Wer hier etwas schreibt, sollte wissen, welcher der drei
   > Bereiche es ist.
4. Alle wirksamen PQ-Items sind die `mp_`-Varianten (Hauptbild); die `pp_`-Varianten haben keine Adresse.
   Unsere Quelle 0 ist das Hauptbild — es gibt auf diesem Gerät kein zweites.
5. Dass die Stock-Videokette tatsächlich unsere ist, zeigt der Chroma-Gain: ohne `0x05140508 = 0x144C0000`
   ist unser Source-0-Bild grau (doku/76 §10, cstenger Commit `5718e4c`). Das PROC-Fenster liegt hinter dem
   NR-Fenster, also liegen die PQ-Register **vor** unserem Abgriff-Ende und nicht dahinter.

Nicht belegt (und deshalb Messsache):

- ob die betroffenen PQ-Module auf diesem Gerät überhaupt bestückt sind. Das Stock-elog meldet beim Start
  `Can not get MP GAMMAModuleID` und `mp_dci_data is NULL`; für Helligkeit/Kontrast/Sättigung gibt es keine
  solche Fehlermeldung, aber auch keinen Positivbeleg.
- ob `0x0500121C` bei uns einen Wert trägt, der Schreibzugriffe zulässt. Steht dort ein Wert mit
  `(wert & 0xF) == 0xA`, verwirft `UIvalueMapping` **jeden** Registerschreibzugriff — dann wäre jeder PQ-RPC
  wirkungslos, ohne dass ein Fehler zurückkäme. Das ist die erste Sache, die gemessen werden muss.
- Im Stock-elog dieser Aufzeichnung werden `SetBrightness`/`SetContrast`/`SetSaturation` **nie aufgerufen** —
  nur registriert. Aufgerufen werden beim Start `SetWhiteBalance`, `SetTNR`, `SetSNR`, `SetDCI`,
  `SetBlackExtension`, `SetPictureMode`, `SetVideoRange`. Stock stellt Helligkeit/Kontrast also über das
  Bildmodus-Preset ein, nicht über den einzelnen RPC.

### A.9 Was Paket G und Paket I daraus mitnehmen

- **Paket I (V4L2-Controls):** `V4L2_CID_CONTRAST`, `SATURATION`, `HUE`, `SHARPNESS` haben ein belegtes
  Zielregister; ~~`BRIGHTNESS` ein vermutetes~~ `BRIGHTNESS` inzwischen ein gemessenes — **aber ohne
  Bildwirkung, und deshalb ist es als Control nicht anzubieten** (§A.6, §0). Die Controls sollten die RPCs
  benutzen (nicht die Register direkt poken) — der Registerweg ist die **Kontrolle**, mit der man am Board
  nachweisen kann, dass der RPC angekommen ist. **Am Kontrast ist genau das vorgeführt worden** und
  zugleich die Warnung: Register geschrieben heißt nicht Bild geändert; die zweite Messung (Wand) gehört
  dazu. Custom-Controls TNR/BlackExtension haben keinen Registerpfad und lassen sich nur über das elog
  verifizieren.
- **Paket G (PQ-Werkzeug):** `UIvalueMapping` bildet in diesem Abbild **identisch** ab (die konkrete
  Abbildungsklasse bei `off_8B201B04` hat für die IDs 1…13 nur `return a2;` und für ID 0 einen leeren
  Rumpf, `re/captures/weltneuheit/k5-uimap-vtable-20260907.log`) — **am Gerät bestätigt**: Argument 20 →
  `0x14`, 50 → `0x32`, 100 → `0x64`.

  > **Korrektur 07.09.2026 am Rest dieses Punktes.** ~~Wertebereiche sind Registerbereiche, keine
  > 0…100-Skala … Die Umrechnung Benutzerwert → Registerwert macht also die ARM-Seite, mit den Kurven aus
  > `pq_factory_extern.ini`.~~
  >
  > Das trägt nicht. Gemessen läuft das **RPC-Argument 0…100** und steht **1:1** im Register; die
  > Werkskurven laufen bis **192** (Sättigung) und **3588** (Kontrast). Die Kurve liegt damit weder
  > zwischen Benutzerwert und RPC noch zwischen RPC und Register — `SetContrast 100` schreibt 100, nicht
  > 2392 oder 3588. **Wozu die Werkskurve dann dient, ist offen** und wird in
  > [doku/81](81-pq-datenmodell.md) §3.2 als offen geführt, nicht geraten.
  >
  > Ungemessen bleibt genau **eine** Stufe: Benutzerwert → RPC-Argument. `h713-pq` reicht sie heute 1:1
  > durch und schreibt an jeder Ausgabestelle dazu, dass sie ungemessen ist
  > (`nachtlog/G-korrektur-saettigung.md`).

  Der Ankerwert **Weißabgleich `dwUIVal = 512`** für alle sechs Indizes (elog,
  `PQManage/TWhiteBalance.cpp 17`) passt allerdings **nicht** zu einer 0…100-Skala. Entweder hat der
  Weißabgleich einen eigenen Wertebereich, oder die 1:1-Abbildung gilt nicht für alle Items. ~~512 ist der
  neutrale Wert eines 16-Bit-Gain-Feldes.~~ *(Das war eine Deutung, keine Messung; die sechs
  Weißabgleich-Felder sind am Gerät nie geprüft worden.)*
- Feldbreiten: Helligkeit/Kontrast/Sättigung/Farbton 16 Bit, Schärfe 16 Bit, DCI/SNR 8 Bit,
  Weißabgleich 16 Bit.

---

## Teil B — K6: Stocks Compositing (Vorstudie, kein Nachtziel)

### B.1 Ausgangslage

`0x051C006C` steht bei uns auf `0x39000000` (Video) **oder** `0x29000000` (RGB) — ein exklusiver Mux.
cstenger schreibt in Patch 0078 ausdrücklich: *„Hardware has only demonstrated an exclusive downstream mux,
not alpha blending."* Stock zeigt dagegen Menü und Video gleichzeitig, und der Chroma-Gain `0x05140508`
graut auf Stock **auch das Menü** (Commit `5718e4c`) — dort läuft das OSD also durch dieselbe YUV-Kette.

### B.2 Neu belegt: es gibt zwei Plane-Selektoren, nicht einen

Im Vendor-Treiber `ge2d_dev.ko` bildet `tgd_show_plane(osd_id, …)` (`0x000016A8`) je OSD-Ebene einen festen
Satz Registerbasen in die Gerätestruktur ein
(`re/captures/weltneuheit/k6-ge2d-plane-20260907.log`, `k6-ge2d-selector-20260907.log`):

| OSD-Ebene | AFBD-Kanal | Selektor | weitere Blöcke |
|---|---|---|---|
| 0 | `0x05600100` (AFBD ch1) | **`0x051C0060`** | `0x05248000`, `0x05280040`, `0x05288000`, `0x0520002C` |
| 1 | `0x05600140` (AFBD ch2) | **`0x051C006C`** | `0x0524C000`, `0x05280080`, `0x0529C000`, `0x05200034` |

`0x051C006C` ist also nicht *der* Selektor, sondern **der Selektor der OSD-Ebene 1** — genau der Kanal,
auf dem unsere Konsole liegt. Dass wir ihn umschalten müssen, ist eine Folge unserer Kanalwahl.

Bitbedeutungen, so weit belegbar:

- `init_osd_plane` setzt in diesem Register **Bit 24** (`| 0x01000000` nach `& 0xFEFFFFFF`).
- `free_fastlogo_func` setzt **Bit 28** (`| 0x10000000`).
- Bit 28 ist genau das Bit, in dem sich unsere beiden Werte unterscheiden: `0x29000000` ↔ `0x39000000`.

### B.3 Was Stock dort einstellt (aus unseren eigenen Abzügen)

`re/captures/weltneuheit/stock-post-hdmi.txt` und `stock-0x5600000-post.txt`, Stock im HDMI-Betrieb:

```
0x05600010: 0x03000013     AFBD ch0  Video, aktiv
0x05600100: 0x83001901     AFBD ch1  OSD-Ebene 0, aktiv   (Latch 0x104 = 0, wird bedient)
0x05600140: 0x83001900     AFBD ch2  OSD-Ebene 1, AUS
0x051c0060: 0x00000000     Selektor OSD-Ebene 0
0x051c006c: 0x39000000     Selektor OSD-Ebene 1
0x051c0070: 0x000000ff
```

*(Gegenprobe an unserem Board, 07.09.: bei laufendem, korrektem Bild steht `0x051C006C` ebenfalls auf
`0x39000000` — [doku/89](89-composition-block.md). Die Aussage unten ist damit auf beiden Seiten belegt.)*

Zwei Punkte, die das Bild ändern:

1. **Stock fährt denselben Wert `0x39000000` in `0x051C006C`, den wir für „Video" benutzen** — und zeigt
   trotzdem das Android-Menü. `0x39000000` bedeutet also **nicht** „Video statt OSD"; es ist Stocks
   Normalwert. Bei uns ist es der einzige Weg zum Bild, weil bei uns nichts anderes in diese Kette
   eingespeist wird.
2. **Stock hat OSD-Ebene 0 (AFBD ch1) aktiv und bedient**, wir nicht. Genau dieser Kanal ist der, dessen
   Latch bei uns nicht verbraucht wird — „das Tor für ch1 liegt außerhalb der AFBD-Seite" (doku/64 §2).

Daraus folgt die Deutung: **Stock mischt das OSD nicht am Selektor, sondern weiter vorn in die YUV-Kette
ein.** Das passt lückenlos zu cstengers Beobachtung, dass der Chroma-Gain im PROC das Menü mitgraut: das
OSD ist zu diesem Zeitpunkt bereits Teil des Bildes, das durch den PROC läuft.

### B.4 Was an Blend-Stufen in der Firmware wirklich gefunden wurde

Die Firmware kennt eine Stufe, die sie selbst „Blender" nennt — allerdings gegen eine **Konstantfarbe**,
nicht gegen eine zweite Ebene (`./blue_screen.cpp`, `re/captures/weltneuheit/k6-procblender-20260907.log`):

| Funktion | Register (ARM) | Wirkung |
|---|---|---|
| `EnableAutoBlueScreen` | `0x05140D4C` | Bit 31 = 0, Bit 30 = 1 |
| `DisableAutoBlueScreen` | `0x05140D4C` | Bit 30 = 0 |
| `CleanAutoBlueScreen` | `0x05140D4C` | Bit 31 = 1 |
| `SetHWBlueScreenColorOfProcOut` | `0x05140D4C`, `0x05140D50` | drei 10-Bit-Komponenten: `[29:20]`, `[19:10]`, `[9:0]` |
| `EnableHWBlueScreenProcBlender` | `0x05140D54` | Bit 6 = 1, `[2:0] = 7`, `[5:3] = 7` |
| `DisableHWBlueScreenProcBlender` | `0x05140D54` | `[2:0] = 0`, `[5:3] = 0` |
| `SetHWBlueScreenColorPanel` | `0x051C00B0`, `0x051C00B4` | dieselben drei 10-Bit-Felder |
| `EnableHWBlueScreenPanel` | `0x051C00B8` | Bit 6 = 1, `[2:0] = 7`, `[5:3] = 7` |
| `DisableHWBlueScreenPanel` | `0x051C00B8` | `[2:0] = 0`, `[5:3] = 0` |

Es gibt die Stufe also **zweimal**, mit identischem Registerbild: einmal am PROC-Ausgang
(`0x05140D4C/D50/D54`, in unseren Abzügen `DE2_mixer_proc`) und einmal am Panel-Ausgang
(`0x051C00B0/B4/B8`, `DE2_panel_out`). Beide sind Zwei-Eingang-Wähler mit Konstantfarbe
(zwei 3-Bit-Auswahlfelder + Freigabe), **kein Alpha-Compositor für zwei Bildebenen**.

Aktuelle Werte, Stock **und** wir identisch (`ours-20260906-source0/02_desc.txt`, `stock-post-hdmi.txt`):

```
0x05140d4c: 0x00000000    0x05140d50: 0x00000000    0x05140d54: 0x00000000
0x051c00b0: 0x00000200    0x051c00b4: 0x00000000    0x051c00b8: 0x00000038
```

`0x051C00B8 = 0x38` heißt: `[5:3] = 7`, `[2:0] = 0`, Freigabe (Bit 6) **aus** — die Panel-Stufe ist also
halb konfiguriert und abgeschaltet. Das ist auf beiden Seiten gleich und damit kein Unterschied, den wir
verursachen.

Zusätzlich hat der PanelWinNode ein **Rahmen-Overlay** (`WriteBorderOverlay1/2`, `sub_8B1A4CF8` /
`sub_8B1A4EE0` nach `0x051C0034` / `0x051C0038`, Feld `m_border_overlay_win`). Das ist ein Rechteck-Rand,
kein Bild-über-Bild.

### B.5 Antwort auf Marcos Frage, so weit sie heute geht

- **Wo sitzt die Blend-Stufe?** Zwei Kandidatenfenster sind belegt und benannt: `DE2_mixer_proc`
  (`0x05140D4C/D50/D54`) und `DE2_panel_out` (`0x051C00B0/B4/B8`). Beide sind aber nachweislich
  *Konstantfarb*-Blender (Blue Screen). Die Stufe, die auf Stock **OSD und Video zusammenführt**, ist
  damit **nicht gefunden**; sie liegt nach der Beweislage **vor** dem PROC, dort wo AFBD-Kanal 1 in die
  YUV-Kette eingespeist wird.
- **Ist unser exklusiver Mux Hardware oder Konfiguration?** Nach heutigem Stand **Konfiguration**:
  Stock fährt denselben Selektorwert `0x39000000` und zeigt trotzdem Menü *und* Video. Der Unterschied ist
  nicht der Selektor, sondern dass bei Stock **AFBD-Kanal 1 aktiv und bedient** ist und bei uns nicht.
  cstengers Satz „only an exclusive downstream mux has been demonstrated" bleibt trotzdem korrekt — er
  beschreibt, was *gemessen* wurde, nicht was die Hardware kann.
- **Offen (klar abgegrenzt):**
  1. Das Tor für AFBD-Kanal 1. Das ist dieselbe Frage wie in doku/64 §2 und derzeit der einzige harte
     Blocker für ein echtes Overlay.
  2. Die Bedeutung der Bits im Plane-Selektor jenseits von Bit 24 (Ebene an) und Bit 28.
  3. Die per-Ebene-Blöcke `0x05248000`/`0x0524C000`, `0x05280040`/`0x05280080`, `0x05288000`/`0x0529C000`,
     `0x0520002C`/`0x05200034`. Keiner davon ist je ausgelesen worden; dort ist die OSD→YUV-Wandlung und
     eine etwaige Alpha-Stufe am ehesten zu erwarten.
  4. Ob es in `0x05200000` (`DE2_panel_ctrl`) eine Ebenen-Reihenfolge gibt — das Fenster ist in unseren
     Abzügen enthalten, aber nie unter diesem Gesichtspunkt gelesen worden.

---

## Anhang — erzeugte Dateien

| Datei | Inhalt |
|---|---|
| `analyse/ida/ida_q40.py` … `ida_q58.py` | die Abfragen dieser Sitzung (Datenbank-Kopie `analyse/ida/db-k5k6/`) |
| `re/captures/weltneuheit/k5-calltable-static-20260907.log` | die 81 Routinen mit Handler-VA, statisch aus `display.bin` |
| `re/captures/weltneuheit/k5-uimapping-tabelle-20260907.txt` | **die Tabelle: Item-ID → Register, Maske, Bitlage, Shift** |
| `re/captures/weltneuheit/k5-uimapping-init-20260907.log` | `sub_8B1024A4`, füllt die Registerspalte |
| `re/captures/weltneuheit/k5-uimapping-caller-20260907.log` | die acht `OnHalPq*Change` mit ihren Item-IDs |
| `re/captures/weltneuheit/k5-swreg-setter-20260907.log` | `UIvalueMapping`, `writel_masked`, `readl_checked` |
| `re/captures/weltneuheit/k5-pq-chain-20260907.log` | `thal_display_pq.cpp`: RPC → Kommandonummer |
| `re/captures/weltneuheit/k5-pq-handler-20260907.log` | Dekompilate der 19 PQ-Handler |
| `re/captures/weltneuheit/k5-nest-swreg-map-20260907.txt` | 197 Registerdeskriptoren (Name, Adresse, Bitfeld) |
| `re/captures/weltneuheit/k5-pqblock-users-20260907.log` | Nachweis der linearen Adressliste `0x05001000 + 4*i` |
| `re/captures/weltneuheit/k5-uimap-vtable-20260907.log` | Wertabbildung ist in diesem Abbild die Identität |
| `re/captures/weltneuheit/k6-ge2d-plane-20260907.log` | `tgd_show_plane`, `init_svp`: Registerbasen je OSD-Ebene |
| `re/captures/weltneuheit/k6-ge2d-selector-20260907.log` | alle Nutzer der beiden Plane-Selektoren |
| `re/captures/weltneuheit/k6-procblender-20260907.log` | `blue_screen.cpp`: die beiden Blender-Registergruppen |
| `re/captures/weltneuheit/k6-blend2-20260907.log` | Xrefs auf die Blend-Strings, Border-Overlay |
