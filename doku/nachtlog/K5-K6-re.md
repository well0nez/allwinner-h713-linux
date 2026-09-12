# Teillog K5 / K6 — RE: PQ-Register und Compositing

Agent: RE (statisch, idalib). **Board nicht angefasst** — kein `ssh`, kein `sonoff_ctl`, kein `wandcheck.py`,
kein `tio`, kein `sudo`. Gearbeitet wurde auf einer eigenen Datenbank-Kopie `analyse/ida/db-k5k6/`
(Original `re/ida/weltneuheit/re_chain/display.bin.i64` blieb ungeöffnet). Eigene Skripte: `ida_q40.py … ida_q58.py`.

Ergebnisdokument: **`doku/85-re-pq-register.md`**.

---

## Kurzantworten

**K5 — Wo landen Helligkeit und Kontrast im Register?**
In einem bisher **nie ausgelesenen** Registerblock **ARM `0x05001000` … `0x050015FC`** (384 × 32 Bit) im
Fenster `DE2_NR_base @ 0x05000000` — **nicht** im PROC-Fenster `0x05140xxx`.

| RPC | Item-ID | Register | Feld | Stand |
|---|---|---|---|---|
| SetBrightness | 3 | `0x05001234` | `[15:0]` | vermutet |
| SetContrast | 4 | `0x05001234` | `[31:16]` | belegt |
| SetSaturation | 5 | `0x05001238` | `[15:0]` | belegt |
| SetHue | 6 | `0x05001238` | `[31:16]` | belegt |
| SetSharpness | 7 | `0x05001228` | `[23:8]` | belegt |
| SetDCI | 9 | `0x0500123C` | `[7:0]` | belegt |
| SetSNR | 12 | `0x05001248` | `[7:0]` | belegt |
| SetTNR / SetBlackExtension | 13 / 8 | — | — | belegt: **kein** Registerschreiben |
| SetWhiteBalance 0…5 | 35…40 | `0x05001274/78/7C` | je `[15:0]` und `[31:16]` | belegt |
| SetGamma (Teil 2) | 88 | `0x05001280` | `[15:0]` | belegt |
| SetPictureMode / SetVideoRange / SetLowLatency / SetColorManagement | — | kein UIMapping-Pfad | — | belegt |

Weg: RPC → `thal_display_pq.cpp` (Kommando 17…29 in eine Warteschlange) → `hal_func.cpp`
`OnHalPq<X>Change` → `UIvalueMapping` (`PQManage/UIMapping.cpp`, `0x8B17F3F8`) →
`writel_masked(tab[id].reg, tab[id].mask, wert << tab[id].shift)` mit `tab = dword_8B2313C0`
(Maske/Shift im Abbild, Registeradressen zur Laufzeit von `sub_8B1024A4` gefüllt).

**Wirken die PQ-RPCs auf unseren AFBD-Source-0-Pfad?**
**Sehr wahrscheinlich ja.** Belegt: der AFBD wird von `NRWinNode_AfbdConfigure` programmiert, gehört also
zum NR-Window-Node mit Fenster `0x05000000`; der PQ-Block liegt in genau diesem Fenster; alle wirksamen
Items sind die `mp_`-Varianten (Hauptbild), und unsere Quelle 0 ist das Hauptbild (die `pp_`-Varianten
haben keine Registeradresse, das Stock-elog meldet „Can not get PP …ModuleID"). Dass die Stock-Videokette
unsere ist, zeigt der Chroma-Gain `0x05140508` (PROC liegt hinter NR).
**Nicht belegt** und deshalb Messsache: ob `0x0500121C` bei uns Schreibzugriffe zulässt — steht dort ein
Wert mit `(w & 0xF) == 0xA`, verwirft `UIvalueMapping` **jeden** Registerschreibzugriff, fehlerfrei und
still. Das ist die erste Messung.

**Nebenbefund für Paket G:** `0x05140508` (Chroma-Gain, `pq_saturation.py`) ist **nicht** das Register von
`SetSaturation`. Es hat keinen Eintrag in der UIMapping-Tabelle. Beides sind gültige Regler, aber
verschiedene. In der Doku trennen.

**K6 — Stocks Compositing (Vorstudie).**
Beantwortet:
- Es gibt **zwei** Plane-Selektoren, nicht einen: `0x051C0060` gehört zu OSD-Ebene 0 (AFBD ch1 `0x05600100`),
  `0x051C006C` zu OSD-Ebene 1 (AFBD ch2 `0x05600140`). Aus `tgd_show_plane` in `ge2d_dev.ko`.
- **Stock fährt in `0x051C006C` denselben Wert `0x39000000` wie wir für „Video"** — und zeigt trotzdem das
  Android-Menü (`stock-pre-hdmi.txt`, `stock-post-hdmi.txt`). Der Unterschied ist nicht der Selektor,
  sondern: Stock hat **AFBD-Kanal 1 aktiv und bedient** (`0x05600100 = 0x83001901`, Latch verbraucht), wir
  nicht. Das OSD wird bei Stock also **vor** dem PROC in die YUV-Kette gemischt, nicht am Selektor.
- Damit ist der exklusive Mux nach heutigem Stand eine Eigenschaft **unserer Konfiguration**, nicht der
  Hardware. cstengers Satz („only an exclusive downstream mux has been demonstrated") bleibt richtig — er
  beschreibt das Gemessene.
- Zwei „Blender" in der Firmware gefunden und benannt: PROC-Ausgang `0x05140D4C/D50/D54` und Panel-Ausgang
  `0x051C00B0/B4/B8` (`./blue_screen.cpp`, `EnableHWBlueScreenProcBlender` u. a.). Beide sind
  **Konstantfarb**-Blender (3 × 10-Bit-Farbe, zwei 3-Bit-Auswahlfelder, Freigabe Bit 6) — **kein**
  Alpha-Compositor für zwei Bildebenen.

Offen (klar abgegrenzt): die Stufe, die OSD und Video zusammenführt, ist **nicht** gefunden; sie liegt vor
dem PROC. Blocker bleibt das Tor für AFBD-Kanal 1 (doku/64 §2). Nie ausgelesen und für die nächste Runde
vorgemerkt: die Ebenen-Blöcke `0x05248000`/`0x0524C000`, `0x05280040`/`0x05280080`, `0x05288000`/`0x0529C000`,
`0x0520002C`/`0x05200034`.

---

## Verlauf

| Zeit | Was |
|---|---|
| 21:46 | Nachtplan, Koordinationslog und `analyse/ida/README.md` gelesen; Datenbank-Kopie nach `analyse/ida/db-k5k6/` (der K1–K3-Agent hat `db-k1k3`, keine Kollision) |
| 21:47 | `ida_q40.py`: Xrefs ins PROC-Fenster `0xBA140xxx`. Ergebnis: **kein** statischer Schreiber für `0x05140508`; nur `ProcWinNode__WriteReg` (`+0x104…0x134`) und `sub_8B1A604C` (`+0x148/14C/160/164/514/518/524/528`). Die Methode aus dem Nachtplan führt allein nicht ans Ziel |
| 21:49 | Statische Routinentabelle in `display.bin` gefunden (Datei-Offset `0x12CF70`, 81 Einträge à `0x68`, `char name[0x5C]; u32; u32 flag; u32 handler`). Gegengeprüft am Stock-elog: `SetBrightness → 0x8B10A4FC` stimmt |
| 21:50 | `ida_q41/42`: alle PQ-Handler dekompiliert. Sie schreiben kein Register, sondern legen `{Kommando, Wert}` in eine Warteschlange |
| 21:51 | `ida_q43`: `UIvalueMapping` (`0x8B17F3F8`) gefunden — der generische Setter mit Tabelle `{reg, mask, shift}` bei `dword_8B2313C0` |
| 21:53 | `ida_q44/45`: `sub_8B1024A4` füllt die Registerspalte. Adressen liegen bei `0x050012xx` und `0x050014xx/150x`, **nicht** bei `0x05140xxx` |
| 21:55 | `ida_q46`: die acht `OnHalPq*Change` nennen ihre Item-IDs im Klartext (4 Kontrast, 5 Sättigung, 6 Farbton, 7 Schärfe, 8 BlackExt, 9 DCI, 12 SNR, 13 TNR) |
| 21:56 | `ida_q47`: konstante Adressliste bei `0x8B1FE408` ist über 384 Einträge exakt `0x05001000 + 4*i` → Blockgrenzen belegt |
| 21:58–22:02 | `ida_q48/49/51/52`: Brightness-Rückruf gesucht. Ergebnis: die Zeichenkette `OnHalPqBrightnessChange` existiert, wird aber von **keiner** Funktion geladen; keine Funktion ruft `UIvalueMapping` mit ID 3. Brightness bleibt Vermutung (Begründung in doku/85 A.6) |
| 22:00 | Stock-elog gegengelesen: Stock ruft beim Start `SetWhiteBalance/TNR/SNR/DCI/BlackExtension/PictureMode/VideoRange`, aber **nie** `SetBrightness/SetContrast/SetSaturation`. `Can not get MP GAMMAModuleID`, `mp_dci_data is NULL` |
| 22:03–22:06 | K6: `ge2d_dev.ko`-Kopie geöffnet; `tgd_show_plane` liefert die Zuordnung Ebene → AFBD-Kanal → Selektor; `blue_screen.cpp` liefert die beiden Blender-Registergruppen |
| 22:07 | Stock- und eigene Registerabzüge verglichen: Stock hat `0x051C006C = 0x39000000` **und** sichtbares Menü; `0x05001xxx` ist in **keinem** Abzug enthalten (alle enden bei `0x050000FC`) |
| 22:11 | `doku/85-re-pq-register.md` geschrieben |
| 22:15 | `analyse/hdmi-seq/pq_probe.py` geschrieben (Messwerkzeug für die Hauptsitzung, schreibt nie ein Register direkt) |

## Erzeugte Dateien

**Dokumente**
- `doku/85-re-pq-register.md` — Ergebnisdokument K5 + K6
- `doku/nachtlog/K5-K6-re.md` — dieses Teillog

**Werkzeuge**
- `analyse/ida/ida_q40.py … ida_q58.py` — 13 idalib-Abfragen (Datenbank-Kopie `analyse/ida/db-k5k6/`)
- `analyse/hdmi-seq/pq_probe.py` — Board-Messwerkzeug für die PQ-Register (neu, kollidiert mit nichts)

**Rohausgaben** (alle in `re/captures/weltneuheit/`)
`k5-pq-xrefs-20260907.log`, `k5-calltable-static-20260907.log`, `k5-pq-handler-20260907.log`,
`k5-pq-chain-20260907.log`, `k5-swreg-setter-20260907.log`, `k5-uimapping-table-20260907.log`,
`k5-uimapping-init-20260907.log`, **`k5-uimapping-tabelle-20260907.txt`** (die Tabelle),
`k5-uimapping-caller-20260907.log`, `k5-pqblock-users-20260907.log`, `k5-nest-swreg-map-20260907.txt`,
`k5-nest-init-20260907.log`, `k5-brightness-dispatch-20260907.log`, `k5-uimap-values-20260907.log`,
`k5-uimap-vtable-20260907.log`, `k5k6-onhalpq-afbd-lvds-20260907.log`,
`k6-ge2d-afbd-20260907.log`, `k6-ge2d-plane-20260907.log`, `k6-ge2d-selector-20260907.log`,
`k6-blend-20260907.log`, `k6-blend2-20260907.log`, `k6-procblender-20260907.log`

---

## Board-Anfrage

**Kurz:** ein Board-Slot von ~10 Minuten, direkt im Anschluss an eine Sequenz aus Abschnitt 1 des
Nachtplans (Bild steht auf der Wand). Es wird **kein Register geschrieben** — die einzigen Schreibzugriffe
gehen als RPC an die MIPS-Firmware, so wie Stock es auch tut. INCAP (`0x0694xxxx`) wird nicht angefasst,
der Descriptor nicht erneut geschrieben.

**Was es beantwortet:** (a) ob die PQ-Schreibsperre `0x0500121C` offen ist, (b) ob `SetContrast` wirklich
`0x05001234[31:16]` stellt, (c) ob `SetBrightness` `0x05001234[15:0]` stellt (die einzige verbliebene
Vermutung aus K5), (d) ob die PQ-RPCs auf unserem Source-0-Bild überhaupt sichtbar wirken.

### Schritt 0 — Werkzeug aufs Board

```bash
scp /opt/Projekte/h713/analyse/hdmi-seq/pq_probe.py root@192.168.8.141:/root/
```

### Schritt 1 — Grundzustand lesen (nur lesen)

```bash
ssh root@192.168.8.141 'python3 /root/pq_probe.py show'
```

**Erwartung / Abbruchkriterium:** Die erste Zeile nennt `0x0500121C`. Steht dort ein Wert, dessen
**unterste vier Bit `0xA`** sind, dann verwirft die Firmware jeden PQ-Registerschreibzugriff — dann sind
die folgenden Schritte sinnlos und das ist selbst das Ergebnis (bitte im Nachtlog vermerken).
Sind alle 384 Wörter `0x00000000` oder alle `0xFFFFFFFF`, ist der Block nicht angebunden — ebenfalls ein
gültiges Ergebnis, bitte notieren.

### Schritt 2 — Kontrast: der belegte Fall zuerst

```bash
ssh root@192.168.8.141 'python3 /root/pq_probe.py dump /root/pq-a.txt'
python3 /opt/Projekte/h713/analyse/hdmi-seq/wandcheck.py shot pq_vorher
ssh root@192.168.8.141 'python3 /root/pq_probe.py rpc SetContrast 20'
sleep 1
ssh root@192.168.8.141 'python3 /root/pq_probe.py dump /root/pq-b.txt'
python3 /opt/Projekte/h713/analyse/hdmi-seq/wandcheck.py shot pq_contrast20
ssh root@192.168.8.141 'python3 /root/pq_probe.py diff /root/pq-a.txt /root/pq-b.txt'
```

**Erwartung:** `diff` meldet eine Änderung an `0x05001234` in den **oberen 16 Bit**. Das bestätigt die
Tabelle. Wandbild bitte **ansehen** (Read), nicht nur die Kennzahl.

### Schritt 3 — Helligkeit: die offene Vermutung

```bash
ssh root@192.168.8.141 'python3 /root/pq_probe.py probe SetBrightness 20'
python3 /opt/Projekte/h713/analyse/hdmi-seq/wandcheck.py shot pq_bright20
ssh root@192.168.8.141 'python3 /root/pq_probe.py rpc SetBrightness 50'
python3 /opt/Projekte/h713/analyse/hdmi-seq/wandcheck.py shot pq_bright50
```

**Erwartung, falls die Vermutung stimmt:** `probe` meldet genau eine Änderung, und zwar an `0x05001234`
in den **unteren 16 Bit**. Ändert sich stattdessen ein anderes Register, ist die Zuordnung falsch — dann
bitte die Adresse notieren, sie ist dann direkt die Antwort auf K5.
Ändert sich **gar nichts**, obwohl Schritt 2 funktioniert hat, dann geht Brightness nicht über
`UIvalueMapping` (das deckt sich mit dem Befund, dass es keinen `OnHalPqBrightnessChange`-Rückruf gibt).

### Schritt 4 — Wirkung auf Source 0 (die eigentliche Frage für Paket I)

```bash
ssh root@192.168.8.141 'python3 /root/pq_probe.py rpc SetSaturation 0'
python3 /opt/Projekte/h713/analyse/hdmi-seq/wandcheck.py shot pq_sat0
ssh root@192.168.8.141 'python3 /root/pq_probe.py rpc SetSaturation 50'
python3 /opt/Projekte/h713/analyse/hdmi-seq/wandcheck.py shot pq_sat50
python3 /opt/Projekte/h713/analyse/hdmi-seq/wandcheck.py diff pq_sat0 pq_sat50
```

Sättigung ist der beste Reiz, weil die Wirkung auch ohne Kalibrierung eindeutig sichtbar ist (grau ↔ bunt)
und weil es dafür einen zweiten, unabhängigen Regler gibt: `python3 /root/pq_saturation.py` liest
`0x05140508`. **Bleibt `0x05140508` unverändert, während sich `0x05001238[15:0]` ändert**, ist der Befund
aus doku/85 A.7 bestätigt: zwei getrennte Regler.

### Schritt 5 — zurückstellen

```bash
ssh root@192.168.8.141 'python3 /root/pq_probe.py rpc SetContrast 50'
ssh root@192.168.8.141 'python3 /root/pq_probe.py rpc SetBrightness 50'
ssh root@192.168.8.141 'python3 /root/pq_probe.py rpc SetSaturation 50'
ssh root@192.168.8.141 'python3 /root/pq_probe.py show'
```

### Optional, wenn noch Zeit ist (K6, reines Lesen)

Die Ebenen-Blöcke sind nie ausgelesen worden. Sie kosten nichts und beantworten die offene K6-Frage
vielleicht direkt:

```bash
mkdir -p /opt/Projekte/h713/re/captures/weltneuheit/ours-20260907-nacht
ssh root@192.168.8.141 "python3 /root/pq_probe.py blocks \
    0x05240000 0x200  0x0524C000 0x200 \
    0x05280000 0x200  0x05280080 0x200 \
    0x05288000 0x200  0x0529C000 0x200 \
    0x05200000 0x400" \
  > /opt/Projekte/h713/re/captures/weltneuheit/ours-20260907-nacht/k6-ebenenbloecke.txt
```

(`dump_blocks.py` reicht dafür nicht: es mappt genau 4 KiB je Block aus einer festen Liste und kommt
weder an `0x05001xxx` noch an diese Fenster heran. `pq_probe.py blocks` liest nur.)
Interessant ist, ob sich die beiden Ebenen-Sätze unterscheiden und ob dort etwas wie eine Alpha- oder
Reihenfolgeeinstellung steht.

**Nicht anfassen:** INCAP `0x0694xxxx` (nur lesen), `viddec_descriptor.py set` (genau einmal pro Boot),
Kamera-Belichtung.
