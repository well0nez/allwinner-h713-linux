# Teillog: RE-Fragen K1, K2, K3 (statische Analyse, kein Board)

Agent: RE (MIPS/IDA). Alle Uhrzeiten vom Arbeitsrechner, 06./07.09.2026.
Ergebnisdokument: **[doku/84-re-capture-ring.md](../84-re-capture-ring.md)**.

## Kurzantworten

**K1 — `0x0694084C`, `0x06940400`, `0x06940824`.** Keines der drei Register wird von Firmware-**Code**
geschrieben; sie stehen in den **TSE-Registertabellen** (`analyse/tse/board/database.TSE`), die
`AppTopProjector_HandleSignalEvent` → `sub_8B1078EC` (Attribute) → `sub_8B107B04` (Gruppe `"V_INCAP"`)
ausführt.
* `0x06940400` Bits [6:5] = **Freigabe des MP-Datenpfads im INCAP**; die Gruppe `FINAL`
  (`DBUS_MP_RST_TV`/`_PROJECTOR`) löscht und setzt sie zusammen mit DE `0x05000020` Bit 3,
  DE2 `0x050C0000` Bit 5, PROC `0x05140004` Bit 31, LVDS `0x051C0010` Bit 25. `0x21→0x61` = Pfad an.
* `0x06940824` Bit 31 = **Betriebsart der INCAP-Eingangs-Farbraumstufe** (Modul `MP_ICSC_VINCAP`; State 0 und
  State 2 schreiben identische Matrixkoeffizienten und unterscheiden sich **nur** in diesem Bit).
  Bit 31 = 1 → Matrix rechnet, Bit 31 = 0 → Bypass.
* `0x0694084C` = **4:2:2/4:4:4-Wandler** (Modul `CONVERT_422AND444`), zwei 16-Bit-Hälften mit je einem 2-Bit-Feld
  ([11:10] und [27:26], Werte 1 oder 3); untere Hälfte nach `input_format`, obere nach `colorspace`.

**Wichtige Korrektur:** `0x21→0x61` und `0x824` Bit 31 sind der **Normalfall** der guten Sequenz (Abzüge
`ours-20260906-source0/01_lock` vs `02_desc`), **nicht** Folge des Format-4-Versuchs. `0x0694084C` bleibt in
allen fünf Abzügen des guten Laufs auf `0x04000C00`. Der Wert `0x0C000C00` verlangt Descriptor-`color_format`
∈ {3, 5, 6}; mit den am 06.09. geschriebenen Werten 4 und 2 **kann** die Firmware das Register nicht
beschrieben haben — die Zuschreibung in doku/76 §12.4 trägt nicht.

**K2 — Ring-Folge.** `0x05600320/0x324` werden von **keiner** Firmware-Funktion und von **keiner** TSE-Tabelle
geschrieben (drei unabhängige, vollständige Suchen; die Firmware fasst im AFBD nur `0x000…0x0A4` an, nichts ab
`0x100`). Sie sind ein Hardware-Paar; `0x05600010` Bit 31 sagt dem Kanal, dass er sie lesen soll.
**Ein „Slot fertig"-Interrupt existiert nur MIPS-intern** (INTC `~0x0305FC00`, Quellen `VIncap` 32,
`VIncap_1` 25, `AFBD` 27 — Klartextnamen aus `g_irq_to_swint_table` `0x8B2319D4`). Auf dem ARM ist nichts
davon verdrahtet: im Stock-DTS haben weder `tvtop@5700000` noch `tvcap@6800000` eine `interrupts`-Eigenschaft,
`0x06940000` kommt als Knoten gar nicht vor, und die cpu_comm-Callback-Liste kennt kein Frame-Ereignis.
INCAP `+0x100` wird von der Firmware nie gelesen und steht bei uns konstant — kein Interruptstatus.

**K3 — zweiter Descriptor-Anstoß.** Zwei Sperren, beide belegt:
1. `sub_8B1087F8`/`sub_8B10881C` vergleicht die neue SignalInfo mit der zwischengespeicherten; bei Gleichheit
   findet **kein** Zustandswechsel statt → `PushSignalToMemoryAgent` und `update_onoff` laufen nicht.
   Denselben Descriptor zweimal zu schreiben ist per Konstruktion ein Nullereignis.
2. Die TSE-Module `MP_ICSC_VINCAP`, `CONVERT_422AND444`, `MP_WB_VINCAP` haben `always=0`: passt die neue
   Attributkombination zu keinem State, schreiben sie **gar nichts** und stellen **keine** Grundwerte her.
   `INIT_VINCAP` (der einzige unbedingte Reset) fasst `0x824`/`0x84C` nicht an.
   ⇒ Es gibt **keinen** Firmware-Pfad, der die INCAP-Konfiguration vollständig zurückstellt.
   Bester verfügbarer Teil-Reset: **echter Quellenwechsel** (`SetSource` auf eine andere Quelle und zurück),
   weil das über `HandleSignalEvent` die Gruppe `V_INCAP` erneut ausführt. Ob das reicht: **ungemessen** (B2).
   Bis dahin gilt „Descriptor genau einmal pro Boot" weiter — und der Treiber soll das erzwingen.
   *Nebenbei:* „`0x928` Bit 31 bleibt 0" ist **kein** Fehlerkennzeichen — im laufenden, korrekten Betrieb ist
   das Bit 0 (`02_desc`/`03_source0`), im Ruhezustand 1. Diagnosemerkmal ist allein, ob `0x320/0x324` wandern.

## Für Paket E: **Polling, nicht Interrupt**

Genauer: **kein eigenes Polling, sondern Vsync-getaktetes Auslesen.** Im vorhandenen AFBD-Vsync
(`dec@5600000`, `interrupts = <0 0x6E 4>` = GIC 142, der KMS-Treiber hält ihn bereits) `0x05600320` (Y) und
`0x05600324` (C) lesen; ändert sich das Paar, ist der zugehörige Slot fertig → `vb2_buffer_done`.
Slot-Index aus der Adresse: Y `0x4C3EF000/0x4C5EE000/0x4C7ED000` (Abstand `0x1FF000`), C = Y + `0x5FD000`,
gleiche Indizes. Ein ARM-sichtbares Capture-Ereignis gibt es nicht und Stock hat auch keines.
Empfehlung: Zähler für „Paar unverändert" und „mehr als ein Slot übersprungen" mitführen, damit ein
Ratenunterschied sichtbar wird statt still verschluckt zu werden.

## Zeitverlauf

* **21:46** Nachtplan §0/§0b/§1/§3K/§7, `doku/nachtlog/00-koordination.md` und `analyse/ida/README.md` gelesen.
  Eigene Datenbank**kopie** angelegt: `analyse/ida/db-k1k3/display.bin.i64` (Original in
  `re/ida/weltneuheit/re_chain/` **nicht geöffnet**). Kein Board, kein `sudo`, kein `git`.
* **21:50–22:00** `ida_q27`–`ida_q32`: vollständige MMIO-Landkarte der Firmware (direkte `lui`-Zugriffe,
  Basiszeiger-Konstantenverfolgung, `$a0`-Auflösung an den Zugriffsfunktionen inkl. Delay-Slot).
  Befund: die Firmware fasst nur 16 INCAP-Offsets an; `0x84C`, `0x400`, `0x824` sind nicht dabei und kommen
  im Abbild auch nicht als Konstante vor.
* **22:00** Wende: die INCAP-Konfiguration steht in den **TSE-Tabellen**. `tools/tse_dump.py --all` über
  `analyse/tse/board` ausgeführt; `analyse/tse/hdmi-source4.txt` liefert die Modul-/State-Zuordnung für alle
  drei Register. K1 damit belegt.
* **22:03** Gegenprobe mit den echten Abzügen `ours-20260906-source0/01_lock…05_after_hpd`: zwei der drei
  „Umstellungen" sind der Normalfall; `0x84C` ändert sich in der guten Sequenz nie.
* **22:05** Attribut-Mapper gefunden (`sub_8B12C098`, Tabelle `0x8B1F218C`, 1-basiert) — Modell an drei
  Registern und zwei Zuständen unabhängig bestätigt.
* **22:07** K2: `g_irq_to_swint_table` mit Klartextnamen (`VIncap`, `VIncap_1`, `AFBD`); Stock-DTS geprüft —
  ARM-seitig keine Capture-Unterbrechung.
* **22:09** K3: Zustandsautomat, `PushSignalToMemoryAgent`, `update_onoff`, `sub_8B10881C`,
  `ApplyNewSource` dekompiliert.
* **22:14** `doku/84-re-capture-ring.md` und dieses Teillog geschrieben.

## Erzeugte Dateien

Skripte (neu, fortlaufend ab `ida_q27`):
`analyse/ida/ida_q27.py`, `ida_q28.py`, `ida_q29.py`, `ida_q30.py`, `ida_q31.py`, `ida_q32.py`,
`ida_q33.py`, `ida_q34.py`, `ida_q35.py`, `ida_q36.py`, `ida_q37.py`, `ida_q38.py`, `ida_q39.py`,
`ida_q40.py`, `ida_q41.py`

Rohausgaben in `re/captures/weltneuheit/`:
`k1k3-q27-indirect-20260907.log`, `k1k3-q28-mmio-map-20260907.log`, `k1k3-q29-mmio-fenster-20260907.log`,
`k1k3-q30-phys-immediates-20260907.log`, `k1k3-q31-basiszeiger-20260907.log`,
`k1k3-q32-accessor-args-20260907.log`, `k1k3-q34-schluesselfunktionen-20260907.log`,
`k1k3-q35-enums-20260907.log`, `k1k3-q36-zustandsmaschine-20260907.log`,
`k1k3-q37-zustandsuebergaenge-20260907.log`, `k1k3-q39-mips-isr-20260907.log`,
`k1k3-q33-regtabelle-de-20260907.log`, `k1k3-q38-irq-quellen-20260907.log`,
`k1k3-q40-aufrufer-20260907.log`, `k1k3-q41-reset-pfad-20260907.log`,
`k1k3-tse-alle-module-20260907.txt`

Dokument: `doku/84-re-capture-ring.md`. Datenbankkopie: `analyse/ida/db-k1k3/` (kann gelöscht werden).

## Board-Anfrage

Alle drei Messungen sind **lesend** an den INCAP-Registern (Nachtplan Regel 6: `0x0694xxxx` nie schreiben)
und schreiben den Descriptor **höchstens einmal pro Boot**. Reihenfolge frei; B1 und B3 kosten je einen
Kaltstart, B2 zwei.

### B1 — Polarität von `0x06940824` Bit 31 gegen die Farbe prüfen (1 Kaltstart, ~4 min)

Belegt werden soll: Bit 31 = 1 heißt „ICSC rechnet" (Capture liefert YUV), Bit 31 = 0 heißt Bypass
(Capture liefert die RGB-artigen Ebenen aus doku/76 §12.2).

```bash
sonoff_ctl restart --host 192.168.8.179
for i in $(seq 30); do ssh -o BatchMode=yes -o ConnectTimeout=3 root@192.168.8.141 uptime && break; sleep 4; done
ssh root@192.168.8.141 'bash /root/prep_after_boot.sh'
ssh root@192.168.8.141 'taskset -c 1 python3 /root/hdmi_seq.py run --phase 4 --i-mean-it --only setsource \
     --source 3 --portmap stock --gap 500 --pre-source-wait 1 --listen-after 3'
ssh root@192.168.8.141 'bash /root/arisc_edid_init.sh'
sleep 6
# --- VORHER: ICSC laut Modell im Zustand "Matrix aus" (0x0b) ---
ssh root@192.168.8.141 'python3 /root/dump_state.py b1_vor'
ssh root@192.168.8.141 'python3 /root/chroma_stat.py'        # Erwartung: Cb/Cr NICHT um 128 (RGB-artig)
# --- Descriptor GENAU EINMAL ---
ssh root@192.168.8.141 'python3 /root/viddec_descriptor.py set'
sleep 2
ssh root@192.168.8.141 'python3 /root/dump_state.py b1_nach'
ssh root@192.168.8.141 'python3 /root/chroma_stat.py'        # Erwartung: Cb/Cr um 128 (YUV)
```

Auswertung: `grep -E '^0x0694(0824|084c|0400|0928|0968)' b1_vor.txt b1_nach.txt`.
Erwartet `0x824`: `0x0000000b → 0x8000000b`, `0x84C` unverändert `0x04000c00`, `0x400`: `0x21 → 0x61`.
**Die Aussage steht und fällt mit `chroma_stat.py` vor dem Descriptor** — misst es dort schon YUV um 128,
ist die Polarität umgekehrt und Abschnitt 2.2 von doku/84 muss korrigiert werden.

### B2 — Reicht ein Quellenwechsel als Neuanstoß? (2 Kaltstarts, ~10 min)

Belegt werden soll: ob `SetSource` auf eine andere Quelle und zurück die Gruppe `V_INCAP` erneut ausführt
(dann gäbe es einen Firmware-eigenen Reset-Pfad und Paket D/E müsste nicht mit „einmal pro Boot" leben).

```bash
# Lauf 1: guter Zustand herstellen (Sequenz aus Nachtplan Abschnitt 1, Descriptor EINMAL)
# ... bis einschliesslich: python3 /root/afbd_source0.py on ; wandcheck.py shot b2_bild1
ssh root@192.168.8.141 'python3 /root/dump_state.py b2_gut'
# Quellenwechsel: weg von HDMI und zurueck (KEIN Descriptor-Schreiben dazwischen!)
ssh root@192.168.8.141 'taskset -c 1 python3 /root/hdmi_seq.py run --phase 4 --i-mean-it --only setsource \
     --source 1 --portmap stock --gap 500 --listen-after 3'      # 1 = VideoDec
sleep 3
ssh root@192.168.8.141 'python3 /root/dump_state.py b2_src1'
ssh root@192.168.8.141 'taskset -c 1 python3 /root/hdmi_seq.py run --phase 4 --i-mean-it --only setsource \
     --source 3 --portmap stock --gap 500 --listen-after 3'      # zurueck auf HDMI-1
sleep 5
ssh root@192.168.8.141 'python3 /root/dump_state.py b2_zurueck'
ssh root@192.168.8.141 'python3 /root/elog_tail.py | tail -80'   # laeuft "V_INCAP" erneut?
python3 analyse/hdmi-seq/wandcheck.py shot b2_bild2
```

Auswertung:
1. `diff <(grep '^0x0694' b2_gut.txt) <(grep '^0x0694' b2_zurueck.txt)` — kehren `0x400`, `0x824`, `0x84C`,
   `0x8C0/8C8`, `0x800–0x820` auf die Werte von `b2_gut` zurück?
2. Wandern `0x05600320/0x324` in `b2_zurueck` noch (zweimal `dump_state.py` im Abstand von 2 s und die beiden
   Zeilen vergleichen)?
3. Zeigt das elog `EnterWaitingWindowsReady` / `EnterWaitingPipeLineReady` / `wce_cap ... WriteReg` erneut?

Ergebnis „ja" ⇒ Paket D/E darf den Descriptor beim Plane-Enable erneut anstoßen, wenn davor ein
Quellenwechsel steht. Ergebnis „nein" ⇒ die Regel „genau einmal pro Boot" bleibt und gehört als
Zustandsvariable in den Treiber.

### B3 — Kann `0x0694084C` überhaupt auf `0x0C000C00` kippen? (1 Kaltstart, ~5 min, **verbraucht** den Descriptor)

Belegt werden soll die Modellvorhersage: `0x0C000C00` verlangt Descriptor-`color_format` ∈ {3, 5, 6}.
**Nur ausführen, wenn ein Kaltstart-Slot übrig ist — der Descriptor wird dabei mit einem Wert ≠ 0
geschrieben, das Bild bleibt danach aus, und die Firmware ist bis zum nächsten Kaltstart verstellt.**
Der Lauf beantwortet zugleich, ob die 0x84C-Änderung aus doku/76 §12.4 wirklich vom Descriptor kam.

```bash
# Kaltstart + Prep + SetSource + EDID wie in Nachtplan Abschnitt 1, dann:
ssh root@192.168.8.141 'python3 /root/dump_state.py b3_vor'
# viddec_descriptor.py hat KEINEN Formatschalter (Zeile 30: d[16] = 0). Fuer diesen Lauf einmalig
# eine Kopie mit d[16] = 6 aufs Board legen -- die Originaldatei NICHT aendern:
#   sed 's/    d\[16\] = 0  /    d[16] = 6  /' /root/viddec_descriptor.py > /root/viddec_descriptor_fmt6.py
ssh root@192.168.8.141 'python3 /root/viddec_descriptor_fmt6.py set'   # GENAU EINMAL, Wort 16 = 6
sleep 3
ssh root@192.168.8.141 'python3 /root/dump_state.py b3_nach'
```

Erwartung (Modell): `0x0694084C` `0x04000c00 → 0x0C000C00`, `0x06940824` `0x0000000b → 0x8000000b`.
Bleibt `0x84C` stehen, ist die State-Auswahl in doku/84 §2.3/§2.4 falsch.
Am Descriptor darf **nur** Wort 16 abweichen (alles andere wie `viddec_descriptor.py set`), sonst ist die
Zuordnung nicht eindeutig.

### Nicht angefragt, aber nützlich, falls ohnehin ein Abzug entsteht

`dump_state.py` sollte den INCAP-Bereich `0x06940800–0x069409FF` und `0x06940400–0x069404FF` **vollständig**
enthalten (er tut es offenbar schon) und zusätzlich AFBD `0x05600300–0x0560036F` — dann lässt sich
`0x05600328`/`0x05600368` (der W1C-Interruptstatus, den `ge2d_dev.ko` bedient) mitbeobachten.
