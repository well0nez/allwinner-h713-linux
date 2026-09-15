# Paket J - Pflichtliste `legacy/docs/known-issues.md`

**Agent:** J (Beleg-Recherche, offline). **Kein Board angefasst**, kein `sudo`, kein `git`, kein Bau,
`patches/kernel/series` nicht berührt.

| Uhrzeit | Schritt |
|---|---|
| 21:43 | Nachtplan 78 gelesen (Abschnitt 0 Regeln, Abschnitt 3 „J"), `doku/nachtlog/00-koordination.md` gelesen. |
| 21:45 | `legacy/docs/known-issues.md` (214 Z.) zerlegt: **17 Sachpunkte** + 5 Einträge unter „Keine Bugs". |
| 21:46-21:50 | Recherche je Punkt: doku/00, 60, 61, 62, 65, 67, 68, 70, 71, 74, 75, 76, 77, 95; `mainline/patches/kernel/`; aktueller Kernelbaum `build/linux-6.18.38-d9f9ca8…a037c1a7`; `analyse/arisc-frame/BEFUND.md`; `legacy/docs/re/`, `legacy/STATUS.md`; `re/captures/weltneuheit/elog-stock-LIVE.bin` (`strings -n 8`). |
| 21:51-21:58 | Workaround-Suche im Quelltext (Puls, `unstick`, `--gap`, Spin-/Timeout-Konstrukte, `/dev/mem`). |
| 21:58 | Tabelle in `legacy/docs/known-issues.md` eingesetzt, Altbestand (214 Z.) unverändert als Kontext erhalten. |
| 21:59-22:02 | Alle Datei-/Zeilenangaben in beiden Dateien gegen den Quelltext nachgezogen. |

---

## 1. Zahlen

**17 Punkte** (Freitext-Einträge der Pflichtliste), dazu 5 Einträge „Keine Bugs" als eigene Gruppe.

| Kategorie | Anzahl | Punkte |
|---|---|---|
| **gelöst** (Stelle im Quelltext/Patch benannt) | **6** | 1, 2a, 3, 5a, 6b, 8 |
| **Stock-Verhalten belegt** (Stock-elog / Firmware-Disassembly) | **2** | 6a, 17 (Teil „die ARISC pollt") |
| **beantwortet / widerlegt** (Altaussage stimmt nicht mehr) | **2** | 13, 15 |
| **offen - Ursache belegt, Umsetzung fehlt** | **5** | 5b, 10, 14, 16, 2b |
| **offen - unverändert, keine neue Erkenntnis** | **2** | 4, 12 |
| **gegenstandslos für den heutigen Stack** | **1** | 9 |
| **Hardware** | **1** | 11 |
| **nur durch Messung entscheidbar** | **2** | 6c, 7 |

Die Summe ist größer als 17, weil die Punkte 2, 5 und 6 in Teile zerfallen, die verschieden stehen
(2a/2b, 5a/5b, 6a/6b/6c); die Zuordnung je Punkt steht in der Tabelle in
`legacy/docs/known-issues.md`.

**Quer dazu liegt der Vermerk „nicht anfassen"** - er ist keine Kategorie, sondern eine Auflage
dieses Pakets: **4** (IR-NEC), **11** (Endschalter, Hardware) und **2b** (Compositor). Bei **2a** und
**3** (GPU, Cedrus) war der Auftrag ebenfalls nur „Stand feststellen"; der Stand ist erfreulich.

**Zwei Einträge unter „Keine Bugs" sind heute falsch** und in der Datei korrigiert:

1. „DTS-Einträge für die Msgbox-IRQs SPI 108/109 bringen nichts, mainline-GIC routet sie nicht,
   Stock braucht `wakeupgen`." → **widerlegt.** Die richtige Leitung ist `GIC_SPI 46` (GICv2 78); die
   Msgbox-IRQ trägt RX sauber, ohne Sturm, ohne Maskierung, der Treiber läuft interruptgetrieben
   (doku/67 Z. 35 `332: 12 0 0 0 GICv2 78 Level cpu_comm-msgbox`, Z. 337, Z. 458). Kein `wakeupgen`.
2. „`decd.ko` ist für HDMI-RX toter Code, Stock nutzt `ge2d_dev.ko`, fünf Sitzungen bestätigt." →
   **teilweise widerlegt.** Genau der ARM-seitige `decd`-Handgriff `dec_reg_set_address` (VidDec-Descriptor,
   Zeiger in AFBD `0x05600098`) ist die Stufe, die die Projektor-Zustandsmaschine der Firmware freigibt;
   ohne ihn bleibt sie auf Zustand 0 und die DE-Kanäle zu (doku/76 §6 und §10 Schluss, doku/77 §1 Zeile 9,
   `analyse/hdmi-seq/viddec_descriptor.py` Kopfkommentar).

Die anderen drei („Lock-Bits sind bei Stock auch 0", „snps-PHY-Init passt nicht", „die MIPS-Firmware
ist nicht kaputt") stehen unverändert und haben heute sogar eine bessere Begründung: die HDMI-RX-Seite
gehört dem MIPS, der ARM hat am Synopsys-PHY nichts zu suchen (doku/71 „Antwort zuerst").

---

## 2. Workaround-Funde (Regel 1) - **nichts davon geändert**

Sortiert nach Gewicht. „Verdeckt" heißt: was man nicht mehr sieht, solange der Behelf drin ist.

### W1 - Doorbell-Puls auf `TX_IRQ_EN` im ARISC-Pfad
*Wo:* `analyse/arisc-hdmi-drv/arisc_hdmi.c:178-188` (`doorbell()`, Kommentar „die Msgbox ist
flankengesteuert"), Aufrufe `:383`, `:471`; identisch in `mainline/patches/kernel/0090-soc-sunxi-add-arisc-hdmi-hpd.patch:233-239`;
Skripte `analyse/arisc-msg/arisc_hdmi.py:135-139`, `arisc_send.py:341/431-436`, `arisc_msg.py:655-662`.
*Verdeckt:* dass die ARISC-Empfangspumpe die Msgbox **pollt** - `0x7fd8` liest über `0x7e4c/0x7e88`
in einer Schleife ohne Zeitlimit (`analyse/arisc-frame/BEFUND.md` §2, §3, §6 „Poll-Schleife
`0x8064→0x8068→0x7e88`"), und der Poller `0x7bbc` weckt die Pumpe schon beim ersten Wort
(doku/68 „Die Falle: die Pumpe vergisst `length`").
*Sauber:* wohlgeformten Rahmen schreiben, kein Puls.
*Achtung - Abgrenzung:* der **gleichnamige** Puls im `cpu_comm`-Pfad (ARM→MIPS,
`drivers/soc/sunxi/cpu_comm/cpu_comm_hw.c:70-76`) ist **kein** Workaround: dort ist am Gerät gemessen,
dass ein reines `MSG_DATA` das Wort in der FIFO liegen lässt („count went 0 -> 1 and the MIPS never
drained it"). Das ist eine belegte Hardware-Eigenschaft, kein Behelf.
*Offen:* Der Satz „die ARISC pollt - kein Puls nötig (3/3 belegt)" (doku/77 Z. 61-62, doku/78 Z. 182)
hat **keine Fundstelle im Repo**. Der Mechanismus ist aus der Disassembly belegt, der Lauf nicht.
→ Messung M3.

### W2 - „einmal pulsen"/Rettung: `unstick`, `main_loop_alive`, `hpd_delay`
*Wo:* `analyse/arisc-hdmi-drv/arisc_hdmi.c:275` (`main_loop_alive`), `:343-352` (`ensure_alive`),
`:575-592` (`do_unstick`), `:537` (`do_hpd_delay`), debugfs-Knoten `:824`/`:827`; Patch 0090:327/627/833;
Skript `analyse/arisc-msg/arisc_hdmi.py:157-176` (`unstick`), `:141-155` (`main_loop_alive`).
*Verdeckt:* den **Startup-Handshake** der ARISC. Sie sendet nach dem Laden eine Notify auf ARM-RX ch3
und wartet bis zu 100 s auf die Quittung auf user1 Port 3; das alte `unstick()` schickte Nullwörter
auf Port 3 und traf damit zufällig genau diese Quittung (doku/75, Nachtrag 06.09. 15:25, Absatz
„Das erklärt die Vorgeschichte").
*Sauber:* Handshake im Probe (ist im Modul drin), Rettungspfade ersatzlos streichen -
so steht es auch in doku/77 §2.1 („Was **weg** kann").

### W3 - Nutzlast direkt in den ARISC-SRAM + Rahmen mit `length = 0`
*Wo:* `analyse/arisc-hdmi-drv/arisc_hdmi.c:365-378` (Kopfkommentar: „Die Länge 0 ist Absicht … Die
Nutzlast als weitere Msgbox-Wörter zu schicken funktioniert nur manchmal - deshalb nicht", = Patch
0090:416-430), Schreiben nach `RPM_BUF` `:405-408`; Skript `analyse/arisc-msg/arisc_hdmi.py:84-87, :186`; Rezept doku/68 Z. 1490-1497.
*Verdeckt:* nichts Unbekanntes - die Ursache ist sauber belegt (die Pumpe verliert `type`/`length`
zwischen zwei Wörtern, wenn der Poller sie zwischendrin neu startet, doku/68 „Die Falle"). **Aber:**
der ARM schreibt hier in den privaten SRAM eines anderen Kerns, und das tut Stock nicht - Stocks
`mcu_comm` legt BOP-Rahmen auf die Msgbox (BEFUND.md §8).
*Sauber:* wohlgeformter BOP-Rahmen - Marker `0xA5`, `type=0`, `length`, Pad-Wort, Nutzlast
little-endian gepackt, genau `2 + ceil(length/4)` Wörter (BEFUND.md §3 und §6) - in einem Rutsch
geschrieben, damit der Poller nicht dazwischenfährt. doku/75 (13:35) nennt genau das als nächsten
Schritt: „Rahmen mit Länge, Burst-Schreiben der Msgbox-Wörter".

### W4 - `--gap`-Drossel vor jedem RPC
*Wo:* `analyse/hdmi-seq/hdmi_seq.py:105-108` (`CALL_GAP_MS = 50`, Kommentar nennt den Grund),
`:895` (`time.sleep(opts.gap/1000)`), `:1258`; im Betriebsrezept mit `--gap 500`
(doku/78 Z. 88, doku/75 Z. 353); Legacy-Vorbild `hy310-hdmird` `CALL_GAP_MS = 500` (doku/65 Schluss
des FreeCall-Abschnitts).
*Verdeckt:* die Erschöpfung des 21-Platz-FreeCall-Pools, also W5.
*Sauber:* W5 lösen, dann fällt die Drossel weg.

### W5 - 100-Spin-Schleifen mit `-EBUSY` statt Semaphore (`TODO: SLOT-RELEASE-WAIT`)
*Wo:* aktueller Baum `drivers/soc/sunxi/cpu_comm/cpu_comm_proto.c:318-328` (FIFO nearly full) und
`:369-382` (Slot-Entnahme; der TODO-Block steht bei `:336-367` und beschreibt den sauberen Weg selbst).
*Verdeckt:* dass der Rückgabeweg des MIPS nicht abgewartet wird; nach ~19-21 Aufrufen kommt `-EBUSY`
und der Anwender denkt an einen Firmware-Fehler.
*Sauber:* `cpu_comm_sem_down_timeout` auf die Slot-Release-Semaphore
(`s_CommSockt[remote] + 235`, Stock-RE @ `0x3c40`), wie im TODO beschrieben.

### W6 - Semaphoren-Timeout 100 ms, danach „bypassing"
*Wo:* `cpu_comm_proto.c:296-303`: `cpu_comm_sem_down_timeout(sem_ptr, msecs_to_jiffies(100))` (Z. 299),
bei Fehlschlag `ret = 0` mit `pr_info_ratelimited("sem timeout, bypassing")` (Z. 301).
*Verdeckt:* genau den Fall, für den die Semaphore da ist (kein MIPS-ACK). Ein Fehler wird zu Erfolg
umgeschrieben - der Kommentar sagt selbst „DEBUG".
*Sauber:* Fehler nach oben geben oder die Ursache (fehlender ACK) beheben; nicht überspringen.

### W7 - ACK-Typen ohne Cache-Sync (= Pflichtliste #10)
*Wo:* `cpu_comm_proto.c:779-792` (`handle_CPU2_callACK` Z. 779, `…returnACK` Z. 788 - beide rufen
`queueAction` ohne `cpu_comm_sync_mips_cache`), Begründung im Kommentar `:781-783`. Der Stock-Offset
steht im Kommentar darüber (`:726-730`): CALL/RETURN nutzen `+8`, **CALL_ACK/RETURN_ACK `+105`**;
die Funktion selbst `:732-748`.
*Verdeckt:* möglicherweise nichts - aber unbelegt. Paket C soll es abhaken oder gleichziehen.

### W8 - `sleep 10` als HPD-Low-Dauer
*Wo:* `analyse/hdmi-seq/arisc_edid_init.sh:30` (`… PullHotPlug-DOWN; st; sleep 10`), so auch in der
Sequenzbeschreibung doku/75 Z. 222.
*Verdeckt:* nichts Bekanntes - aber der Wert hat **keinen Stock-Beleg**. Stock stellt das
HPD-Intervall auf 200: `HDMI_SetHPDTimeInterval(0xC8)`, im Stock-elog als
`SetHPDTimeInterval from 200 to 200` (elog-stock-LIVE.bin, tick 28823, `./THDMIRx.cpp 603`).
*Sauber:* Stock-Wert nehmen und die untere Grenze messen (Messung M4).

### W9 - fester Ring-Slot 0 statt Ring-Drehung
*Wo:* `analyse/hdmi-seq/afbd_source0.py:23` (`Y, C, INFO = 0x4C3EF000, 0x4C9EC000, 0x4D95F000`);
alle vier pool-1-Slots bekommen dieselbe Adresse.
*Verdeckt:* Tearing. Die Firmware dreht mit 60 Hz durch drei Slots (`0x05600320/324`, doku/76 §11.1).
*Sauber:* pro Vsync den fertigen Slot übernehmen - Paket D, Schritt 2.

### W10 - der gesamte Betriebspfad läuft über `/dev/mem`
*Wo:* alle fünf Skripte des Rezepts aus Nachtplan §1 schreiben über `/dev/mem` bzw. `busybox devmem`:
`prep_after_boot.sh`, `hdmi_seq.py`, `arisc_edid_init.sh`, `viddec_descriptor.py`, `afbd_source0.py`.
*Abgrenzung (gehört in die Tabelle):* **Diagnose ist erlaubt** - `analyse/`-Werkzeuge wie
`dump_state.py`, `chroma_stat.py`, `dump_blocks.py`, `arisc_probe.sh`, `elog_tail.py`,
`arisc_onset_sampler.py`, `wandcheck.py` lesen bzw. messen und sind ausdrücklich als Diagnose
gekennzeichnet. **Betrieb ist es nicht** - die fünf oben sind heute der einzige Weg zum Bild und
werden von B/C/D/E durch Treiber ersetzt. Nichts davon darf Endstand sein.
*Sonderfall:* `prep_after_boot.sh` Schritt 4 schreibt den MIPS-elog-Pegel (`0x4B48BD9C`) über
`/dev/mem` - reine **Diagnose**, steht aber im Betriebsrezept. Beim Umbau als Diagnoseschalter
kenntlich machen oder streichen.

### W11 - Reste, die nur noch dem Namen nach Workarounds sind (kein Handlungsbedarf, nur Kosmetik)
* `cpu_comm_mem.c:1019-1026` „WORKAROUND: MIPS never initializes its share_seq structures" - in der
  arm64-Fassung durch `if (cpu_id == 1 && !cpu_comm_shmem_adopted)` stillgelegt und mit dem Grund
  versehen (U-Boot baut die Strukturen; sie zu überschreiben nimmt die Routinen-Tabelle mit).
  Irreführend ist nur die Überschrift.
* `mainline/patches/kernel/0039-media-cedrus-add-runtime-dma-guard.patch` - ausdrücklich Diagnose,
  Vorgabe `dma_guard=0` = „byte-for-byte the previous behaviour". Erlaubt und richtig gekennzeichnet.

### W12 - außerhalb des HDMI-Pfads, der Vollständigkeit halber
`drivers/misc/hy310-board-mgr.c:116-121` und `:314-319`: Lüfter-Tachometer per hrtimer-Polling,
im Quelltext selbst als „workaround" plus „TODO (Prio 3)" markiert, weil die EINT auf PH11+ nicht
auslöst. Betrifft die Pflichtliste nicht, fällt aber unter Regel 1.

---

## 3. Board-Anfrage - was nur eine Messung klären kann

Vier Messungen. Alle nach dem Protokoll aus Nachtplan Abschnitt 6 (Sperre setzen, TFTP prüfen,
Kaltstart, `timeout` um jeden Board-Befehl). M1 ist die aus dem Nachtplan als K4 vorgesehene.

### M1 - Hot-Plug nach dem Boot (Pflichtliste #6, Nachtplan K4) - **braucht Marco am Kabel**

*Frage:* Reagiert das Gerät auf ein **Stecken nach dem Boot** von selbst, so wie Stock, oder nicht?

*Was Stock tut - das ist der Vergleichsmaßstab, Beleg `re/captures/weltneuheit/elog-stock-LIVE.bin`
(`strings -n 8`):*

```
[18078]   (./THDMIRx_Event.cpp 514)   port1 5V detect ret:1 !!!!!
[18078]   (THDMIRx_TV303_Driver.cpp 326) HdmiRx_SendHPDCMD port1 cmd=176 tick=18078
[18078]   (THDMIRx_TV303_Driver.cpp 320) port1 5VDetect bOn=1
…
[1157081] (./THDMIRx_Port.cpp 126)    port 1 send HPD event
[1157096] (./THDMIRx_Event.cpp 59)    port id=1 HDP_Req=1 HPDState=4 tick=1157096
[1157096] (THDMIRx_TV303_Driver.cpp 326) HdmiRx_SendHPDCMD port1 cmd=160 tick=1157096
[1157328] (THDMIRx_TV303_Driver.cpp 326) HdmiRx_SendHPDCMD port1 cmd=144 tick=1157328
[1157830] (./app_top_projector.cpp 919) CallbackOfSignalChange  → AI_SIGNAL_MODE_1920_1080, 60 Hz
```

Der zweite Block liegt **19 Minuten nach dem Boot**. Stock erkennt also nach dem Boot, treibt HPD
selbst und meldet es über `SignalChange` nach oben - **ohne ARM-Poller**. Der Auslöser ist die
5-V-Leitung der Quelle, erkannt vom MIPS, nicht von der ARISC.

*Gegenbefund von uns, der die Messung nötig macht:* bei `SetSource(3)` loggt unsere Firmware zwar
`HdmiRx_SendHPDCMD port1 cmd=176`, aber der **ARISC-HPD-Zähler `0x11722c` bleibt dabei 0**
(doku/75, Lauf 92, 10-ms-Raster über den ganzen SetSource). Die MIPS-HPD-Kommandos erreichen die
Fall-7-Stufe der ARISC also **nicht**. Wo sie landen, ist offen.

*Messvorschrift (ohne Rückfrage ausführbar):*

1. Kaltstart und die Sequenz aus Nachtplan Abschnitt 1 fahren, bis das Bild steht
   (`wandcheck.py shot m1-vorher`, Foto ansehen).
2. Mitschrift auf dem Board anlegen und **losgelöst** starten (nicht im selben Aufruf warten -
   Memory `pgrep-muster-trifft-eigene-shell`). Erst die Datei schreiben:
   ```
   ssh root@192.168.8.141 'cat > /root/m1-watch.sh' <<'EOF'
   #!/bin/sh
   i=0
   while [ $i -lt 180 ]; do
       echo "$(date +%T) hpd=$(busybox devmem 0x07091014) b04=$(busybox devmem 0x07091b04)"
       i=$((i+1)); sleep 1
   done
   EOF
   ```
   dann starten:
   ```
   timeout 20 ssh root@192.168.8.141 'setsid sh /root/m1-watch.sh > /root/m1-reg.txt 2>&1 < /dev/null &'
   ```
   (Die `0x0709xxxx` sind hier **lesbar**, weil `arisc_edid_init.sh` `ResetEDIDModule` schon
   verarbeitet hat - doku/75, Nachtrag 13:35. **Vor** der EDID-Sequenz wären sie tabu: der
   uninitialisierte Block hängt den SoC, doku/75 „Warum heute vier Boards starben".)
3. ARISC-Zähler vor dem Ereignis lesen, **nur lesend**:
   `timeout 20 ssh root@192.168.8.141 'python3 /root/arisc_hdmi.py --no-probe status'`
- `--no-probe` ist Pflicht, sonst schreibt die Lebensprüfung selbst den Zähler und löst HPD aus.
4. Marco bitten: **HDMI-Stecker am Beamer ziehen, 15 s warten, wieder stecken.** Uhrzeit von beidem
   notieren. (`xrandr --off/--auto` am Zuspieler ist als Ersatz **nicht** ausreichend - das lässt die
   5-V-Leitung stehen, und genau die ist der Stock-Auslöser; der `xrandr`-Fall ist ohnehin schon
   belegt, doku/76 §13.)
5. Direkt danach einsammeln:
   `/root/m1-reg.txt`, `/root/elog_tail.out`, `dmesg | grep -E 'elog:|arisc'`,
   `python3 /root/arisc_hdmi.py --no-probe status`, `python3 /root/dump_state.py m1-nach`,
   `wandcheck.py shot m1-nach` (Foto **ansehen**).
6. *Auswertung - drei Fälle:*
   * elog zeigt `5V detect` / `SendHPDCMD` und danach `SignalChange`, Bild kommt zurück →
     **Stock-Verhalten, Punkt 6 erledigt**; der Kernel muss nur den Callback auswerten (Paket E),
     kein Poller.
   * elog zeigt `5V detect`, aber kein `SignalChange` und kein Bild → die Erkennung läuft, die
     Zustellung zum ARM fehlt → Paket C.
   * elog zeigt gar nichts, `0x11722c` unverändert → die 5-V-Erkennung ist bei uns nicht scharf;
     dann ist der nächste Schritt die RE-Frage aus K4 (Handler `0x0411 SET5VFlag` in
     `analyse/arisc-frame/full-disasm.txt`).

### M2 - MIPS-Erstboot: Zähler statt Behauptung (Pflichtliste #7)

*Frage:* Der Legacy-Eintrag sagt „beim ersten Kaltstart kommt der MIPS nicht hoch, einmal neu
starten". doku/75 setzt dagegen „in >20 Kaltstarts nicht mehr gesehen", ohne Zähler.
Strukturell erklärt: im Legacy-Aufbau lud `sunxi-mipsloader` den MIPS **aus Linux**, bei uns startet
**U-Boot** die Firmware (doku/74, „Warum es bei Stock und im alten arm32-Aufbau funktioniert").

*Messvorschrift:* keine eigene Board-Zeit nötig - **bei jedem ohnehin anfallenden Kaltstart** dieser
Nacht eine Zeile anhängen:

```
timeout 30 ssh root@192.168.8.141 'printf "%s uptime=%s cpu_comm_ready=%s mips_run=%s\n" \
    "$(date +%F_%T)" "$(cut -d. -f1 /proc/uptime)" \
    "$(grep -c "Ready: 1" /proc/cpu_comm/status)" "$(busybox devmem 0x0306101c)" \
    >> /root/m2-kaltstarts.txt'
```

Sollwerte: `cpu_comm_ready = 4`, `mips_run = 0x1`. Am Morgen die Datei nach
`re/captures/weltneuheit/ours-20260907-nacht/J/` kopieren. **Zehn Kaltstarts ohne Fehlschlag**
reichen als Beleg, um den Punkt zu schließen; ein einziger Fehlschlag ist der Anfang der
Ursachensuche.

### M3 - Trägt der Doorbell-Puls überhaupt etwas bei? (Pflichtliste #5b/#17, Fund W1)

*Frage:* Die Behauptung „die ARISC pollt - kein Puls nötig, 3/3 belegt" (doku/77 Z. 61, doku/78 Z. 182)
hat keine Fundstelle. Der Mechanismus ist aus der Disassembly belegt (BEFUND.md §3/§6), der Lauf nicht.
Paket B will den Puls streichen - dafür braucht es die Messung.

*Messvorschrift* (nach Prep und ARISC-Handshake, **vor** `arisc_edid_init.sh`, harmlos, weil
`0x0215 CheckEDIDUpdateStatus` nur liest):

1. `timeout 20 ssh root@192.168.8.141 'python3 /root/arisc_hdmi.py --no-probe status'` - Ausgangslage.
2. Drei Läufe **mit** Puls (heutiger Stand):
   `for i in 1 2 3; do timeout 30 ssh root@192.168.8.141 'python3 /root/arisc_hdmi.py --no-probe raw --sub-cmd 0x0215 --arg1 0 --arg2 0 --settle 0.6'; done`
- je Lauf notieren: „classify/Handler gelaufen: ja/NEIN" und ob auf ARM-RX ch1 eine Antwort liegt
   (`bash /root/arisc_probe.sh` oder der `drain()`-Block aus `arisc_edid_init.sh`).
3. Dieselben drei Läufe **ohne** Puls. Dafür in `/root/arisc_hdmi.py` in der Funktion `doorbell()`
   (Z. 135-139) die drei Schreibzeilen einmalig auskommentieren - **Kopie unter
   `/root/arisc_hdmi_nodoorbell.py` anlegen und die Kopie aufrufen**, das Original nicht anfassen.
4. *Auswertung:* 3/3 „ja" mit Antwort auch ohne Puls → der Puls ist entbehrlich, Paket B darf ihn
   streichen, Pflichtliste #5b/#17 fällt. 0/3 oder wechselnd → der Puls bleibt und ist als gemessene
   Hardware-Eigenschaft zu dokumentieren, genau wie im `cpu_comm`-Pfad.
5. Danach Kaltstart, weil die Sonde die ARISC-Zählerlage verändert hat.

### M4 - HPD-Low-Dauer: 200 ms statt 10 s (Fund W8)

*Frage:* `arisc_edid_init.sh` hält HPD 10 s low. Stock arbeitet mit einem HPD-Intervall von 200
(`SetHPDTimeInterval from 200 to 200`, elog-stock-LIVE.bin). Ist die lange Wartezeit nötig?

*Messvorschrift:* im laufenden, guten Zustand (Bild steht) nur den Schlussteil wiederholen:

```
timeout 20 ssh root@192.168.8.141 'python3 /root/arisc_hdmi.py --no-probe hotplug --port 0 --value 2 --settle 1.0'
sleep 0.3        # statt 10 s
timeout 20 ssh root@192.168.8.141 'python3 /root/arisc_hdmi.py --no-probe hotplug --port 0 --value 1 --settle 1.0'
ssh user@192.168.8.162 'cat /sys/class/drm/card0-HDMI-A-2/status'
python3 analyse/hdmi-seq/wandcheck.py shot m4-300ms
```

Dann mit `sleep 1` und `sleep 3` wiederholen. Gesucht ist die **kleinste** Dauer, bei der der ThinkPad
wieder `connected` meldet und das Bild zurückkommt. Ergebnis in doku/75 und in
`analyse/hdmi-seq/arisc_edid_init.sh` als Kommentar festhalten; den Wert dann in Paket B übernehmen.
*Erwartung:* ≥ 100 ms genügt (HDMI-Spezifikation, und Stocks 200 passt dazu). Falls erst 10 s wirken,
ist das ein eigener Befund und gehört als solcher in die Pflichtliste.

---

## 4. Was ich **nicht** entscheiden konnte

* **Punkt 4 (IR-NEC)** - Auftrag war „Stand feststellen, nicht anfassen". Der Stand: Patch 0021
  bringt die Vendor-Sample-Konfiguration (`CIR_REG = 0x00200b2a`, `RXINT = 0x1313`,
  `RXSTA_CLEARALL = 0xef`), aber **nicht** die drei R_CCU-Takte, die der Legacy-Eintrag als Ursache
  nennt. Ob der NEC-Dekoder auf arm64 heute trifft, ist nirgends gemessen. Das ist eine eigene
  Sitzung, kein Nachtthema.
* **Punkt 12 (LRADC-Tasten)** - unverändert: Treiber vorhanden (Patch 0019), Ursache unbekannt,
  drei Hypothesen in `legacy/docs/subsystems/lradc.md` Z. 77-81, keine davon geprüft.
* **Punkt 2, Compositor-Teil** - die GPU läuft (Panfrost/Mali-G31, 59,41 fps zero-copy bei 1080p,
  doku/62), ein Wayland-Compositor ist auf dem arm64-Stack nie gestartet worden. Ob Punkt 9 (CMA für
  Weston) noch existiert, kann erst der erste Compositor-Start zeigen.
