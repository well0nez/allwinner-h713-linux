# Plan: `SetSource` tötet den ARM — Sezierung und Angriff (Handoff, 06.09.2026)

> **Historisch (Stand 08.09.2026):** Ursache gefunden und gelöst am 07.09.; der aktuelle Stand steht in [`00-STATUS.md`](00-STATUS.md), das Betriebswissen in [`97-handoff-20260908.md`](97-handoff-20260908.md). Die Bedienhinweise in diesem Dokument sind überholt (Prep-Skripte, altes cpu_comm-Modul).

**Nach einer Compaction zuerst lesen:** dieses Dokument, dann doku/72 ab „Läufe 23/24"
(Ende der Datei), doku/69 (Riegel/Regeln). Dann `sonoff_ctl status` und Board-Zustand
prüfen, Listener auf dem Host prüfen (`pgrep -f udp_listen`).

> **07.09.2026, 10:55 — Ursache gefunden und am Gerät bewiesen: siehe [74-setsource-ursache-nullzeiger.md](74-setsource-ursache-nullzeiger.md).** `sgp_hal_signal_info` ist NULL (toter SMM-Heap); mit gültigem Puffer überlebt `SetSource(HDMI)`. Die Hypothesen unten sind damit weitgehend erledigt.

## 1. Gerät bedienen und erreichen

| Was | Wie |
|---|---|
| Board | HY310, `ssh root@192.168.8.141` (BatchMode, Key liegt vor). NFS-Root auf diesem Host (`/srv/h713-rootfs`, root-owned, **kein sudo** → Dateien per `scp` nach `/root/`). |
| Strom | `sonoff_ctl status\|on\|off\|restart` (Steckdose; `restart` = aus, 5 s, ein). Board hat **keinen Watchdog**, kein Hänger erholt sich von selbst. Nach `restart` ~30–60 s bis ssh. |
| Restore nach jedem Boot | `bash /root/prep_after_boot.sh > /root/prep.log` (ARISC laden, `cpu_comm`-Modul `/root/hy310-cpu-comm-callwq-test.ko` (aktuell = Modul mit Landezone + Deref-Prüfung, sha `9cb19fe3…`), Module, elog-Level 5, Tail, IRQ-Pinning, Phase 2+3). Dauer ~2 min. Endet mit „SetSource dann mit: …". |
| UART | gehört dem Nutzer (tio). **Nie selbst öffnen.** Konsole zeigt Oops nur bei `printk ≥ 4 4 1 7`. |
| MIPS-Log | `elog_tail.py` (Board, CPU 2) → UDP an Host `192.168.8.104:5555`; Kernel-kmsg → `kmsg_udp.py` (CPU 3) → Port 5556. Host-Listener: `python3 analyse/hdmi-seq/udp_listen.py 5555 <log>` (Scratchpad wird bei Compaction **geleert** → Mitschnitte sofort nach `analyse/hdmi-seq/elog-udp-runNN-*.txt`). |
| Tail-Optionen | `--udp H:P --hb ms --mmio a,b,… --mmio-ms 1 --mmio-force-ms 10 --canary START,LEN --canary-ms 10 --kmsg-exclude '.' --kmsg-level 6`. Änderungen gehen auch als `<4>` nach kmsg. Prozesse per Pidfile beenden; `pkill -f` nur mit `'^python3 /root/…'` (sonst killt es die eigene ssh-Sitzung). |
| RPC | `python3 /root/rpc_test.py call 0xID` (harmlos: GetSource `0x24efc7c9`); Sequenz: `taskset -c 1 python3 /root/hdmi_seq.py run --phase 4 --i-mean-it --only setsource --source N --portmap stock --gap 500 --pre-source-wait 1 --listen-after 5`. Quellen: 0 Dummy, 1 VideoDec, 2 Image, 3 HDMI_1, 4–6 HDMI_2–4, 7–9 CVBS, 10 ATV. |
| Vorbereitungen vor einem HDMI-Lauf | `tvfe_enable.py --do` (TVFE-Takte + bus-demod), `elog_uncached_patch.py --do` (greift nur bei I-Cache-Refetch), `smm_init.py --do` (Heap), `landing_zone.py` (Kontrolle). |
| Modul bauen | Quellen `analyse/cpu-comm-arm64/*.c,h` → nach `mainline/build/linux-6.18.38-102233d4…/drivers/soc/sunxi/cpu_comm/` kopieren, `make -C <Baum> ARCH=arm64 LLVM=1 M=drivers/soc/sunxi/cpu_comm modules -j8`, `.ko` als `/root/hy310-cpu-comm-callwq-test.ko` deployen (prep lädt diesen Namen; Original `.bak`). |
| Firmware-RE | `tools/mips-dis.py dis\|refs\|words\|callers` gegen `re/ida/IDA_hy310/display.bin.bak` (Basis 0x8B100000; ARM-phys = VA − 0x40000000). Vendor-Kernel `/opt/archive/HY310/extracted/vmlinux.elf`, Vendor-DT `/opt/archive/HY310/hy310_factory.dts`, Legacy-arm32-Baum `legacy/` (Treiber, DTS, Patches). |
| Riegel (doku/69) | nie `0x07091000–0x07092000` vom ARM lesen; `0x068B0000` nur mit bus-demod; nie `0x0152f134` rufen; msgbox user2 gehört `cpu_comm`; `SetSource` nur mit Ansage — **die hat der Nutzer für diese Sezierung erteilt** (Steckdose übergeben). |

## 2. Stand des Wissens (bewiesen am Gerät)

* `SetSource(3)`/`(4)` (HDMI, mit und ohne Kabel) tötet den ARM ~100–170 ms nach dem CALL; CALL_ACK kommt, `ack_action` läuft mit korrekter Referenz durch, dann Stille. Ein Oops (Level-0-Translation-Fault) bricht mitten im Druck ab. Der MIPS loggt (uncached) bis „AV mute", danach nichts.
* `SetSource(0)` (Dummy) läuft komplett durch (Lauf 31). 45 harmlose RPCs hintereinander: kein Problem (Zähl-Test). → **Es ist die HDMI-RX-Initialisierung des MIPS**, nicht der RPC-Mechanismus.
* Ausgeschlossen (Experiment): Kernel-Callback, AFBD-KMS, SMM-Heap, lokale Refs/BL31 (Landezone), ungeprüfte Derefs (Bereichsprüfung), TVFE-Takte, SYS_CFG-Bit, TV-IOMMU, PPU (nur Maske), CCU/DRAM-Controller-Zugriffe der Firmware (lui-Scan mit Kontrollen), Aufrufanzahl.
* Unterschiede zum funktionierenden arm32-Aufbau: **Korrektur (Agent 2):** auch im Legacy-Aufbau startete Stock-U-Boot (Fastlogo) den MIPS, der `sunxi-mipsloader` schaltete nur Takt/Gate (legacy/patches/0010:1362-1409); **Legacy-HDMI-RX-Modul** (patch 0023: kennt `0x068008F1` Port-Select und `0x068008FC` PHY-Reset-Ctrl, Wrapper `0x06840000`, HPD-Fenster, Synopsys `0x050C0000`) und **Legacy-tvtop** (alle TV-Takte + Resets) waren vor `SetSource` geladen; Stock-Bootloader statt unser U-Boot (das u. a. den HDCP-Key-Wait im MIPS-Code wegpatcht).

## 3. Hypothesen (geordnet) und Tests

| # | Hypothese | Test | Erwartung |
|---|---|---|---|
| H1 | Der MIPS pokt beim PHY-Reset/PD-Toggle Register in `0x06800000…` (tvcap-Block), deren Takt/Reset/Power in unserem Aufbau fehlt → Bus-Hänger, ARM stirbt sekundär. | Schreibungen der Firmware (0x8b13e36c PHY_Reset: `0x068008FC` Bits 0xC0/0x10, `0x06800210/220/221/230/240/2C0/137/202`, `0x068008F3`; PD-Toggle 0x8b13f580: base+0x1b Bits 0x14; PD_IDCLK 0x8b140310: Bit 0x80) **vom ARM einzeln nachspielen** (Marker, Steckdose). Vorher Lesetest. | Ein Schritt tötet den ARM identisch → Block/Takt identifiziert; dann Vendor-Takt/Reset dafür finden (Agent 2). |
| H2 | Legacy-HDMI-RX-Modul setzte eine Vorbedingung (Reset/Takt/PD/Register), die fehlt. | Agent 2 liefert Diff Legacy-Bringup ↔ heute; fehlende Schritte als Skript nachfahren, dann `SetSource(4)`. | Überlebt → Ursache. |
| H3 | Unser U-Boot lässt den MIPS in einem Zustand (HDCP-Wait-Patch, TSE-Gruppe, Fabric), in dem die HDMI-Init anders läuft als unter Stock. | Vergleich U-Boot-`h713_disp init` ↔ Stock-Kernel-Init (Agent), gezielt: HDCP-Wait-Patch weglassen ist nicht möglich ohne Key → prüfen, ob `Rx_HDCP14_LoadKey` im SetSource-Pfad liegt. | |
| H4 | Portierungsfehler im arm64-`cpu_comm` (Feldbreiten/Offsets), der nur bei einem RPC mit langer Laufzeit zuschlägt. | Agent 1 (läuft) auditiert; Test: Dummy überlebt spricht dagegen, aber lange Calls (Warten auf RETURN > 100 ms) nur mit SetSource. Gegenprobe: harmloser RPC mit langer MIPS-Laufzeit (falls vorhanden). | |

| H5 (neu, Agent 1) | Im Adopt-Pfad bleiben Component-Pool (Shmem+0x240E8) und Messager-Pool (+0x2C068) null (Legacy: `InitComponentPool`/`InitMessagerPool`). Postet der MIPS beim Signalwechsel (HDMI, auch ohne Kabel → `SetSignal`/`CallbackOfSignalChange`) Events über diese Pools, rechnet er mit Null-Feldern → wilde Zeiger. Passt zu Dummy-lebt/HDMI-stirbt. | Pools am Board sind null (gemessen). Firmware: keine direkten Konstanten-Refs (Zeigerzugriff möglich). Test: Pools wie Legacy initialisieren (Treiber, Adopt-Pfad, nur wenn null), dann `SetSource(4)`. | Überlebt → Ursache; Pool-Inhalt zeigt die Events. |
| H7 (neu) | Der MIPS ruft nach `CallbackOfSignalChange` die vom ARM registrierten Routinen (`MipsHalCallback_SignalChange` 0x3E7FBC46, `HdmiHotPlugByPortHandler` …) per CALL; der ARM stirbt im ISR/Work des ersten MIPS→ARM-CALL. Indiz: in keinem kmsg-Mitschnitt erscheint nach `ack_action` ein `msgbox rx … (CALL)`, und der kmsg-Weiterleiter läuft auf CPU 3 = msgbox-IRQ-CPU. Lauf 18 (`--no-callbacks` nur in Phase 4) hatte die Registrierung aus prep Phase 3 noch drin → nicht sauber. | Boot mit `prep_nocb.sh` (Phase 3 `--no-callbacks`), Kontrolle `routines --grep MipsHal` = 0, dann `SetSource(4) --no-callbacks` (Lauf 33). | Überlebt → Callback-CALL-Pfad ist der Killer (dann dort reparieren, der Callback muss laut Nutzer funktionieren). |
| **H8 (neu, 21:45)** | **Adresskollision Kernel ↔ Vendor-Speicherkarte:** Vendor-DT reserviert `bl31 @0x48000000 (0x180000)` und `optee @0x48600000 (0x100000)`; unser Kernel liegt bei **0x48000000–0x4918FFFF** (`swapper_pg_dir` 0x48E91000). Die Firmware hat genau **eine** Referenz in diesen Bereich: `lui 0x8827` (ARM 0x4827xxxx) in der HDCP-Funktion 0x8b13e074 („read pkf"). Schreibt der HDMI-Pfad (HDCP-Schlüssel/TEE) an feste Vendor-Adressen, trifft er bei uns Kernel-Image und oberste Seitentabelle → Level-0-Fault; nur HDMI, nie Dummy. Registerzustände sind identisch mit Stock (Lauf 36), die Speicherkarte nicht. | (a) Disassembly 0x8b13e074: lesen oder schreiben, welche Adresse; (b) Kernel per FIT an andere Adresse laden (z. B. 0x50000000) **und** 0x48000000–0x48700000 als `no-map` reservieren, `SetSource(4)`. | Überlebt → Ursache; Kanarie in 0x48000000-0x48700000 zeigt die Schreibstelle. |
| H8a (Test, 21:55) | Kernel liegt bei 0x48000000, wo Vendor BL31/OP-TEE erwartet; Vendor-Shmem ist 16 MiB (bis 0x4F318000, mips.xml @0x4F308000), unserer 5 MiB — dahinter Kernel-RAM. | FIT `analyse/hdmi-seq/fit-relocated/h713-kernel-reloc.fit`: Kernel `load/entry 0x50000000`, DTB mit `no-map` `0x48000000+0x700000` und `0x4E800000+0xB18000`; ins TFTP als `h713-kernel-netboot.fit` (Backup `.bak-vor-reloc-20260906`). Nach Boot: iomem prüfen, beide Bereiche mit Kanarie füllen, `SetSource(4)`, Kanarie scannen. **Rückbau:** Backup zurückkopieren. | Überlebt → Speicherkarte ist die Ursache, Kanarie zeigt die Schreibstelle; stirbt → Speicherkarte (diese Bereiche) ausgeschlossen. |
| H9 (22:00) | `memory_agent_onoff(alle, AUS)` läuft nur im HDMI-Pfad (Dummy: nein) und schreibt `0x068C00B8/C4/D0/DC/E8/F4` Bit 0, `0x068C038C` Bit 18 (Demod-Bus) sowie — aus 0x8b144d74 — `0x068C0014` Feld 26:24 := 4. Bedeutung des Blocks unbekannt (nicht im Vendor-DT; vermutlich TV-Fabric/MBUS-Ports). | Repliken vom ARM mit Marker (bus-demod an), vorher Lesetest des Blocks. | Tod → Register gefunden. |
| H10 (22:00) | AFBD `0x05600014 |= 1` (einzige effektive memory_agent-Schreibung; Register in Treiber/U-Boot unbekannt). | Replik vom ARM mit Marker. | Tod → Register gefunden. |
| H6 (Agent 1) | Linux-Zustand vs. Protokoll: `SetSource(3)` direkt aus U-Boot (`h713_comm_call`, ID in Tabelle bei h713_mips.c:9171). | Braucht die U-Boot-Konsole = UART des Nutzers; Nutzer tippt, ich gebe die Kommandos vor. | Überlebt U-Boot → Linux-Zustand (Takt-Gating, Treiber); stirbt U-Boot → Protokoll/Shmem-Init/Hardware. |

**H1-Ergebnis (21:06):** Port-Select, PHY-Reset-Ctrl (`0x068008FC`, spiegelt ein Byte über das Wort), Wrapper-Nullungen und PD-Toggle vom ARM nachgespielt (`hdmirx_phy_steps.py`): alles überlebt, Register antworten. Die reinen Schreibzugriffe hängen den Bus nicht. Offen aus dieser Gruppe: PD_IDCLK (Offset unbekannt), die Lesezugriffe der Audio-PLL (0xFF), „send HPD event" (Software-Event, 0x8b135290).

**H6-Rezept (für den Nutzer am tio, U-Boot-Prompt):** Autoboot unterbrechen, dann
`h713_disp init 0x30` (wie in bootcmd; lädt display.bin, richtet Shmem ein), warten bis
„ready", dann `h713_disp commcall 24efc7c9` (GetSource, harmlos, muss RETURN liefern),
danach `h713_disp commcall eaf13de5 3` (SetSource HDMI_1) bzw. `… eaf13de5 4` (HDMI_2 ohne
Kabel). Optional `chan=`/`pid=` wie `commdev` meldet. Stirbt U-Boot ebenfalls (kein Prompt
mehr, kein RETURN), liegt es nicht am Linux-Zustand; kommt RETURN, ist es der Linux-Zustand
(Takt-Gating durch Treiber/Module, IOMMU, CMA/DRAM-Belegung). U-Boot kann danach mit
`h713_mips status` und den Diag-Feldern zeigen, ob der MIPS excepted hat.

## 4. Vorgehen

1. Agent 1 (Treiber-Audit) und Agent 2 (HDMI-RX-Vorbedingungen Legacy↔heute) auswerten, Verdachtsstellen **selbst verifizieren** (Firmware/Code nachlesen, am Gerät messen).
2. H1: Replik-Skript `hdmirx_phy_steps.py` (ein Schritt pro Aufruf, Marker, Lesetest zuerst), pro Schritt ein Boot, falls tödlich.
3. H2: fehlende Vorbedingungen nachfahren, `SetSource(4)` (ohne Kabel = ohne Signal-Nebenwirkungen), dann `SetSource(3)`.
4. Ergebnis in doku/72 anhängen; dieses Dokument bei jeder Planänderung aktualisieren (mit Begründung).

## 5. Abweichungen vom Plan (mit Begründung)

* 03:45 — Bisektion abgeschlossen: Killer-Paar 0x8b108170/0x8b10711c (Fensterprogrammierung). Nutzer: Fix nicht im MIPS. Nächste Phase: Registerziele der Fensterprogrammierung messen, ARM-seitig beheben.
* 00:20 — Lauf 41 (ohne ARISC) negativ → ARISC ausgeschlossen. Plan: Firmware-Bisektion per Live-Stub aus Linux (kalter Code, kein U-Boot-Neubau nötig); CVBS/Image danach.
* 00:10 — H11 widerlegt (Lauf 40: Takte waren an, Lesen hängt trotzdem → Block ARM-seitig unerreichbar, ARISC-privat). Nächster Schritt: ARISC-Gegenprobe (Lauf 41), dann CVBS/Image.
* 22:55 — H11 (RTC/rtc-spi) mit Registern aus dem Vendor-vmlinux vor CVBS/Image gestellt: billig, Positivtest über den bekannten Riegel möglich, erklärt Stock/Legacy-vs-heute und Dummy-vs-HDMI.
* 22:30 — H9/H10 negativ, TV-IOMMU (Lauf 39) negativ; Gerät durch toten TFTP-Server blockiert → Handoff §6, Plan auf CVBS/Image-Bisektion, H6 (Nutzer) und Firmware-Bisektion (U-Boot-Patchpfad) umgestellt.
* 22:00 — H8a (Kernel verschoben + Reservierungen) negativ (Lauf 37); DRAM-Sonde/-Controller sauber (Lauf 38). Neue Spur aus der Zeitachse: NIC-TX-Queue von CPU 2 staut ~100 ms vor dem Ende → DMA-Master zuerst; H9/H10 als billige ARM-Repliken vorgezogen.
* 21:55 — Firmware-Konstante 0x8827 entpuppte sich als Offset-Basis (Ziel 0x8B2722BE, MIPS-RAM); H8 wird trotzdem als Experiment gefahren (H8a), weil Register identisch mit Stock sind und nur die Speicherkarte abweicht.
* 21:45 — Nach Lauf 36 (Register identisch mit Stock) Schwerpunkt auf H8 (Speicherkarte), weil sie als einzige den HDMI-Pfad, den Level-0-Fault und die Vendor-Reservierung bei 0x48000000 zusammen erklärt.
* 21:25 — H7 durch Lauf 34 ausgeschlossen (sauber, 0 Routinen). Schwerpunkt jetzt H2 (Agent 2) und H6 (U-Boot-RPC über den Nutzer), plus H3 (HDCP-Wait-Patch im Pfad?).
* 21:20 — H5 zurückgestuft (Firmware kennt keine Messager/Component-Pools; Events intern über THDMIRx_Event), H7 vorgezogen (Lauf 33), weil Lauf 18 die Registrierung aus prep nicht ausschloss.
* 21:10 — H1 nach dem Replik-Test zurückgestuft; H5 (Pools) vorgezogen, weil sie den Dummy/HDMI-Unterschied erklärt und billig zu testen ist (Agent-1-Befund, selbst geprüft: Pools null, Adopt-Pfad überspringt die Init).

## 12. Stand 07.09.2026, 06:40 — DEFINITIV: kaskadierender MIPS-Exception-Handler ist die Todesursache (hier zuerst weiterlesen)

**Verifiziert (Läufe 70–76, post mortem über Rettungs-FIT/DRAM-Persistenz + Firmware-Disassembly):**

Der SoC-Tod nach `SetSource(HDMI)` ist **nicht** ein ARM-Fehler und **nicht** eine Adresskollision, sondern ein
**kaskadierender Absturz im Exception-Handler der MIPS-Firmware**:

1. Bei der Fensterprogrammierung nimmt der MIPS **eine Exception** (Adressfehler). 
2. Der Exception-Handler (F=0x8b15b448 bzw. der zweite Vektor 0x8b15b504) ruft `save_stack` 0x8b15b2f8 (Magic
   „crashreg" @0x8ba99db4). `save_stack` enthält `sw k1,0x8a(k0)` (0x8b15b390) — ein **fehlausgerichteter Store** →
   eigener Address-Error **im Handler** → Endlos-Rekursion. Der 32-Byte-Stack-Rahmen des Handlers (s0=0x8baa0000,
   ra=0x8b15b464) füllt das DRAM **von 0x4ba99db4 abwärts** durch BL31 (0x40000000) und den Kernel (0x48000000).
3. Ergebnis: ARM-Kernel-Image und BL31 zerstört → stiller Hänger (kein Oops möglich, der ARM ist nur Opfer),
   kein Reboot (nur Watchdog holt zurück). Passt zu allem Beobachteten (kein Oops im späteren tio, Tod ~100 ms nach
   CALL_ACK, unabhängig von der Kernel-Lage).

**Beweise:** post-mortem-DRAM lückenlos voll mit dem Handler-Rahmen (589 822 Treffer 0x48000000–0x491fffff, 30 653
in BL31; `pm-logbuf-run70.bin`); Handler-Disassembly endet in Endlosschleife (0x8b15b4fc/0x8b15b588) mit Formatstrings
„Exception happened at the address 0x%X code 0x%X", „s_pCrashStackBuf == 0"; Diagnose-Patch 0x8b15b390 stoppt das
DRAM-Fressen (Lauf 71: 0 Muster-Treffer) und lässt `SetSource` bis `thal_display_source.cpp` (YUV420_888, BT601)
laufen (Läufe 73/76, tiefer als je zuvor).

**Widerlegt:** H8 (Kernel@0x48000000-Kollision) als alleiniger Fix — Rettungskernel @0x50000000 stirbt ohne Patch
genauso (Lauf 74), weil die Rekursion auch BL31@0x40000000 frisst.

**Noch offen (Handoff-Punkt, chirurgische MIPS-RE):** die **erste** Exception (EPC/BadVAddr der eigentlichen
Fault-Instruktion in der Fensterprogrammierung). Der Crash-Record ist nicht sauber zu fangen, weil der Handler beim
Loggen **weitere** Faults nimmt (Null-`s_pCrashStackBuf`, memcpy 0x8b1bc7ac) und seinen eigenen Record überschreibt
(Lauf 76 fing nur den Folgefault: EPC 0x8b1bc7ac im Handler-memcpy). Nötig: `save_stack` so patchen, dass es nur beim
**ersten** Eintritt schreibt (Record-Schutz), oder den ersten Fault vor dem Handler abfangen. Verdacht bleibt der
Null-Handle-Pfad der Fensterprogrammierung (`*(0x8b4a9da8)=0`, doku/72 04:10).

**ARM-/Umgebungs-Fix (Richtung, kein MIPS-Patch):** die Vorbedingung herstellen, unter der der MIPS diese erste
Exception NICHT nimmt — d. h. das fehlende Objekt/den fehlenden Init-Schritt der Fensterprogrammierung liefern, den
Stock vor `SetSource` setzt (Kandidaten: Vp_Init-Sequenz wie cstenger, TFD/Fenster-Handle-Anlage, fehlende
Stock-tvtop-Init). Der Firmware-Handler-Bug (misaligned store + Null-Crash-Puffer) ist ein **Firmware-Defekt**, der
jede MIPS-Exception tödlich macht; gehört an cstenger/Hersteller gemeldet (macht die Umgebung nur robuster, ist aber
nicht unser Fix).

**Werkzeuge/Methoden dieser Runde:** `wdt_ping.py`/`wdt_arm.py` (Vendor-WDT-Layout CTRL 0x0C/CFG 0x10/MODE 0x14 +
Schlüssel 0x16aa; autonomer Reset, DRAM überlebt), Rettungs-FIT `analyse/hdmi-seq/fit-rescue/` (Kernel 0x50000000,
alter Bereich no-map) + `pm_read.py` (post mortem `__log_buf`/elog/Shmem), `hb_dram.py` (ARM-Herzschlag), `mips_patch.py`
(+ `crashrec`), `tvtop_stock_clks.py` (Stock-TV-Taktzustand), vollständige Vendor-CCU-Tabelle
`analyse/hdmi-seq/vendor-ccu-table.txt`, DTS-Vergleich `analyse/hdmi-seq/dts-vergleich-20260907.md`, cstenger-Commits
`analyse/hdmi-seq/cstenger-commits-20260905.txt`.

## 11. Stand 07.09.2026, 06:20 — MECHANISMUS GEFUNDEN: rekursiver MIPS-Exception-Handler frisst das DRAM (hier zuerst weiterlesen)

**Post mortem (Lauf 70, Rettungskernel + DRAM-Persistenz):** Ab DRAM-Basis 0x40000000 bis mindestens 0x49200000
liegt in jedem 32-Byte-Block der Stack-Rahmen des Firmware-Exception-Handlers F=0x8b15b448 (s0=0x8baa0000,
ra=0x8b15b464). Der Handler (Register-Sicherung 0x8b15b2f8 → Crash-Record 0x8ba99db4 „crashreg") enthält `sw
k1,0x8a(k0)` (0x8b15b390) an eine **unausgerichtete** Adresse → Address-Error im Handler → endlose Rekursion → Stack
zerstört BL31 und Kernel-Code → stiller Tod des ARM (kein Oops möglich). **Jede MIPS-Exception wird so zum SoC-Tod.**
Der Herzschlag zeigte den ARM ~0,4 s nach dem CALL noch lebend.

**Was wir noch nicht wissen:** welche Exception der MIPS bei der Fensterprogrammierung nimmt (erwartet: Null-Handle
`*(0x8b4a9da8)`). **Lauf 71 (Diagnose-Patch, kein Fix):** 0x8b15b390 `af5b008a → af5b008c`, dann `SetSource(4)`;
Crash-Record live lesen (`mips_patch.py crashrec`): EPC, BadVAddr, Cause, alle Register → exakte Stelle.

**ARM-/Umgebungs-Fix danach:** die Bedingung herstellen, unter der der MIPS die Exception nicht nimmt (fehlendes
Objekt/Handle aus Stock-Boot-Sequenz/Konfiguration). Zusätzlich sinnvoll (Robustheit, ohne MIPS-Patch): Speicher
unterhalb der Firmware ist nicht schützbar — der Firmware-Handler-Bug bleibt eine Gefahr, sobald der MIPS je eine
Exception nimmt; dokumentieren, ggf. an cstenger/Hersteller-Kontext melden.

**Nebenbefunde dieser Runde:** Watchdog-Layout (§10-Korrektur, `wdt_ping.py`), DRAM überlebt Warm-Reset, Rettungs-FIT +
`pm_read.py` als Standard-Post-mortem, Stock-tvtop-Takte (`tvtop_stock_clks.py`) noch **nicht** gegen SetSource
getestet (Lauf 68 kam nicht bis zum CALL).

## 10. Stand 07.09.2026, 05:30 — Bus-Hänger statt Software-Fehler; Watchdog als Messinstrument (hier zuerst weiterlesen)

**Neu bewertet:** Lauf 64 (Vendor-`mips_memory` bis 0x4E300000 als `no-map` reserviert) stirbt; Lauf 65 (kmsg-
Weiterleiter auf CPU1 mit SCHED_FIFO, weg von der Msgbox-IRQ-CPU3) zeigt **keinen Oops**. Nutzer: am UART kommt in
späteren Läufen ebenfalls kein Oops (der eine gesehene war ein Kernel-Datenabort, Level-0-Translation-Fault, nach `ISS2`
abgeschnitten); „es gibt kein reboot — nur hang“. cstenger (05.09.) sieht dieselbe Signatur („Network and serial both
dead“, „a bad address is fatal“). → **Arbeitshypothese H13: SoC-/Bus-Hänger durch einen Zugriff der Firmware während
der Fensterprogrammierung** (Zwei-Master-Konflikt auf einer Registerdatei, die U-Boot/unser Treiber angefasst hat, oder
Zugriff auf einen Block ohne Takt/Reset/Power-Domain in unserer Umgebung; die WCE-Knoten schreiben AFBD/LVDS/DE aus
Code, nicht aus TSE-Daten — unsere TSE-Replik hat das nicht abgedeckt). Kernel-Oops-Jagd (Netconsole) ist damit
zweitrangig und mit r8152 ohnehin unzuverlässig.

**Watchdog-Stand (Läufe 66–68):** Mainline-Treiber wirkungslos (kein 0x16aa-Schlüssel); mit Schlüssel per devmem
scharf → Reset nach 16 s **auch im SetSource-Hänger** (Lauf 68). Jeder weitere Schreibzugriff auf den WDT-Block hängt
den SoC → nur Einmal-Timer (`wdt_arm.py`). **DRAM überlebt den Reset** (Kanarie intakt außer U-Boot-Logo ab
0x4e000000). H13-Takte (Stock-tvtop-Zustand, `tvtop_stock_clks.py`) allein: kein Fix (Lauf 68). Post-mortem-Ablauf:
Rettungs-FIT vor dem Scharfschalten einspielen, `pm_read.py` liest `__log_buf`/elog-Ring/Shmem (Lauf 69).

**Messinstrument (Lauf 66, ursprünglich):** Hardware-Watchdog (`/dev/watchdog`, sunxi_wdt, 16 s) per `wdt_ping.py` scharf →
nach dem Hänger Warm-Reset ohne Steckdose. Kanarie im no-map-Schwanz 0x4d961000+0x99f000 vor `SetSource(4)`; nach der
Rückkehr prüfen, ob DRAM den Reset überlebt. Wenn ja: post-mortem-Lesen von Kernel-`__log_buf` (Rettungs-FIT mit
Kernel bei 0x50000000 und `no-map` 0x48000000+0x1200000 nötig), MIPS-elog-Ring und weiteren Kanarien; damit wird die
letzte Firmware-Aktion vor dem Hänger sichtbar.

**Parallel (Agent, Nutzerauftrag):** systematischer DTS-Vergleich Kernel/U-Boot ↔ Legacy (Marco) ↔ Stock
(Speicherkarte, TV-Blöcke mit Takten/Resets/Power-Domains, IOMMU-Master) → `analyse/hdmi-seq/dts-vergleich-20260907.md`.

**Danach:** (a) fehlende Takte/Resets/PDs der Blöcke, die die WCE-Knoten schreiben (AFBD 0x05600000, LVDS/TCON
0x051c0xxx inkl. 0x051c0200/204, DE, INCAP, TVTOP), vom ARM setzen und `SetSource(4)` wiederholen; (b) innere
Bisektion mit Stubs nur der Winmgr-Methoden 0x8b183ae8 / 0x8b183c8c / 0x8b183a60 / 0x8b1583d0 (je ein frischer Boot),
um die tödliche Registergruppe einzugrenzen; (c) Zwei-Master-These: vor `SetSource` AFBD/DE/TCON in den Zustand
bringen, den Stock vor der Fensterprogrammierung hat (KMS-Treiber nicht laden **und** Fetch-Engine still legen).

## 9. Stand 07.09.2026, 04:35 — TSE-datengetriebene Fensterprogrammierung (hier zuerst weiterlesen)

Die tödliche Fensterprogrammierung (0x8b108170 direkt / Callback aus 0x8b10711c) läuft über den
**TFD-Handler** (Unterobjekt 0x8b49b4f8, vtable 0x8b202ea8, `TFDHandler.cpp`: WriteModule 0x8b186d28,
WriteModules 0x8b186ebc/0x8b186f94, WriteModulesByUI 0x8b18709c, GetStateID). Er schreibt
**Registermodule aus der TSE-Datenbank** (database.TSE + ProjectID_0x0030.TSE, von U-Boot nach
0x4BE41000ff geladen; ProjectID 0x30 ist für den HY310 korrekt, doku/40). Der Schreibhelfer erlaubt
Blöcke 0x02… (PIO, IOMMU 0x02010000), 0x03… (SYS_CFG, Msgbox/Spinlock, SID, **GIC 0x0301/0x0302**,
MIPS-Ctrl), 0x05…, 0x06…. Ausgeschlossen als Einzeltrigger: DE-Fensterfreigabe 0x0500103C Bit 2,
Framebuffer-Basis 0x05001528/2C (= 0x4BF41000, reserviert). Handle `*(0x8b4a9da8)`=0 ist kein
ARM-Problem (MIPS-seitiger Null-Deref, nur bei a1≠0).

**Nächste Schritte:** (1) TSE-Modulformat aus dem TFD-Loader rekonstruieren (Agent 6), Module des
HDMI-Zustands dumpen; jede Adresse außerhalb 0x05/0x06 und jeder speicherartige Wert (0x4…–0x7…)
ist Kandidat. (2) Kandidaten am Gerät lesend prüfen, dann als ARM-Replik (Marker) testen.
(3) ARM-seitiger Fix: betroffene Register/Bereiche schützen bzw. Konfiguration (display_cfg.xml
sys:*, TSE-Daten) an unsere Umgebung anpassen. Board-TSE-Dateien: `analyse/tse/board/`.

## 8. Stand 07.09.2026, 03:45 — MIPS-seitig gefunden, ARM-seitiger Fix offen (hier zuerst weiterlesen)

**Befund (Läufe 51–61, frische Boots solide):** Der ARM stirbt, wenn der MIPS nach `SetSource(HDMI)`
das Anzeige-Fenster/Layer für die Quelle programmiert: direkt in 0x8b108170 oder über den in
0x8b10711c (`AppRegisterCallbackOfSignalChange`) registrierten Signalwechsel-Callback. Beide
gestubbt → SetSource(4) lebt dauerhaft; je einer → Tod. **Stubs sind nur Diagnose, kein Fix.**
Regeln: frische Boots, eine Variable je Lauf, 45–60 s Nachbeobachtung (Same-Boot-Läufe und
„lebt nach 5 s" haben zweimal getäuscht: 57/59). Werkzeug `mips_stub.py` (stub/restore/show).

**Neuer Anhaltspunkt (03:55):** Das Geräte-/Kanalobjekt der Fensterprogrammierung ist bei uns
**null** (`*(0x8b4a9da8)=0`, Flag 0x8b4a9afc=0); Window-Manager `*(0x8bac1a60)` (vtable 0x8b202210,
Methoden +0x10=0x8b183ae8, +0x14=0x8b183c8c). Zu klären: wer dieses Objekt im Stock anlegt (MIPS-Init
vs. ARM-seitige Konfiguration/CPU_COMM) und welches Ziel die Programmierung mit Null-Handle trifft.
Agent 5 (statisch) angesetzt; Ergebnis am Gerät verifizieren (Lesetests, dann Messlauf).

**Fix-Richtung (ARM/Umgebung):** herausfinden, was die Fensterprogrammierung an Hardware setzt
(Layer-vtable-Methoden +0x10/+0x14/+0x18 der `%s_Top/%s_Bottom`-Objekte, Worker 0x8b1080a8,
Kommando 0x12E in 0x8b1583d0) und welches Ziel dabei in ARM-RAM zeigt. Kandidaten: DE-Write-back/
Scaler-Frame-Speicher, AFBD-Kanäle (ARM-KMS-Treiber belegt 0x05600000), Konfigurationswerte aus
der TSE-Datenbank/XML (`sys:frame_buf_addr`, 0x8b19c9d4), INCAP-Ziele. Messung: mit **nur 0x8b10711c
gestubbt** (direkter Weg bleibt) die Registerblöcke DE 0x05000000/0x05140000/0x051C0000/0x05200000,
AFBD 0x05600000, INCAP 0x06940000, TVTOP-B 0x068C0000 im 1-ms-Raster abtasten und Änderungen per
kmsg `<4>` (UART) sichern; alternativ statisch die Layer-vtable live lesen (Objekt aus 0x8b184084)
und die Methoden auf RMW32-Helfer-Adressen scannen. Danach die betroffene Region auf ARM-Seite
reservieren/konfigurieren oder den Treiberkonflikt (AFBD-KMS) auflösen.

## 7. Stand 07.09.2026, 01:45 — scharf lokalisiert (hier zuerst weiterlesen)

**Methode gefunden:** MIPS-Funktionen live aus Linux stubben (`analyse/hdmi-seq/mips_stub.py`,
`stub VA` schreibt `jr ra; move v0,zero`, nur bei Prolog `addiu sp`; ARM-phys = VA − 0x40000000).
Greift für Code, den der MIPS seit Boot noch nicht ausgeführt hat (Handler/Worker sind kalt).
`restore` setzt zurück. **Bisektion (Läufe 42–49):** Handler THal_Vp_SetSource 0x8b14ab68 gestubbt →
lebt; App-Worker 0x8b1091f4 gestubbt → stirbt; AppTopSetSource 0x8b109174 gestubbt → **lebt**.
Alle HDMI-RX-Funktionen einzeln (13) und + update_onoff/memory_agent_onoff + HDMI-Slot 0x8b130aa8
gestubbt → stirbt. Folgerung: der Tod entsteht als Folge des Enqueue in AppTopSetSource
(`obj=*(0x8b253578)`, vt+0xC=0x8b107574 → `jal 0x8b15bb80`), dispatcht in der App-Thread-Schleife an
einen per-Quelle-Callback ≠ 0x8b1091f4. **Nächster Schritt:** diesen Konsumenten/Callback per Agent
statisch bestimmen, dann mit `mips_stub.py` verifizieren. Danach: was dieser Callback bei HDMI tut,
das ARM-RAM/Seitentabelle trifft (der eigentliche Fix).

## 6. Stand 06.09.2026, 22:30 (Handoff — hier weiterlesen)

**Blocker:** Der TFTP-Server (`sudo dnsmasq --port=0 --enable-tftp --tftp-root=/opt/Projekte/h713/tftp --no-daemon --log-queries`) lief ab ~22:05 nicht mehr (Port 69 zu). Das Board hängt nach jedem Steckdosen-Neustart in U-Boot (kein Ping, ARP incomplete). **Nur der Nutzer kann dnsmasq neu starten** (kein sudo). Vorher immer `ss -ulnp | grep ':69 '` prüfen. Das FIT im TFTP ist wieder das **Original** (`h713-kernel-netboot.fit`, Kernel @0x48000000); das verschobene FIT liegt in `analyse/hdmi-seq/fit-relocated/` (neutral, Lauf 37).

**UDP-Regel (Nutzer):** Sonden haben das Netz blockiert. `elog_tail.py` ohne `--mmio-force-ms`, `--hb ≥ 500`, nur Änderungen senden; cpucomm-Zeilen nicht per UDP. Host-Listener: `python3 analyse/hdmi-seq/udp_listen.py 5555 <log>` / `5556`. Achtung: `pgrep -f udp_listen.py` matcht die eigene Shell — Listener immer direkt starten.

**Bewiesen (Läufe 31–39, H9/H10):**
* HDMI-`SetSource` (3 und 4, mit/ohne Kabel) tötet den ARM ~100–170 ms nach dem CALL; Dummy (0) läuft sauber durch; 45 harmlose RPCs kein Problem.
* ARM-seitig ausgeschlossen: Callback-Pfad (Lauf 34, 0 Routinen), Landezone/BL31 (28), Deref-Bereichsprüfung (30), SMM-Heap (24), Pools (Firmware kennt sie nicht), Kernel-Verschiebung + Vendor-Reservierungen 0x48000000/0x4E800000 (37).
* Hardware-seitig ausgeschlossen: alle einzeln vom ARM nachgespielten HDMI-RX-Schreibungen (Port-Select, PHY-Reset-Ctrl, Wrapper-Nullen, PD-Toggle; H1), `memory_agent`-Ziele 0x068C…/AFBD-Commit (H9/H10), SYS_CFG-Bit, TVFE-Takte, Synopsys-Init mit 0x203B01 (35), 0x05000058 (36), TV-IOMMU-Register unverändert (39), DRAM-Controller/PLL unverändert und DRAM-Sonde fehlerfrei bis kurz vor dem Ende (38/39). Registerblöcke HDMI-RX_ctrl/port, INCAP, DETN sind **identisch mit Stock-pre-HDMI** (`re/captures/weltneuheit/`).
* TF-A: keine Group-0-IRQs, kein EL3-Exception-Handling → EL3-Umweg unwahrscheinlich; BL31 ist Release ohne Konsole.

**Was den Tod erklären muss:** ein Level-0-Translation-Fault an gültiger Kernel-VA (oberste Tabelle bzw. TTBR), nicht abhängig von der physischen Kernel-Lage, nur im HDMI-Init-Pfad des MIPS, unabhängig vom ARM-Treiber. Kandidaten, die nur noch per Bisektion **auf MIPS-Seite** zu klären sind: die Lesezugriffe/Programmierung des HDMI-PHY (Audio-PLL, TMDS), `PD_IDCLK` (Offset unbekannt), `SendHPDEvent` (0x8b135290, Software-Event), `SetSignal`/`AfterEnable`-Folgen, Reihenfolge/Timing (Dinge, die einzeln harmlos sind, in Kombination nicht).

**H11 (22:40, statisch, noch ungetestet):** Der HPD-Pin liegt im **RTC-Block `0x07090000`**
(Vendor: `rtc@7090000`, Takte `r-ahb-rtc`/`rtc-1k`/`rtc-spi` aus `r_ccu@7010000`, Reset 8; Stock-Capture
„HPD-pin @0x07091000" zeigt Pin-Cfg/Data/Drive/Pull). Bei uns hängt ein ARM-Lesezugriff auf
`0x07091014` den SoC (Riegel doku/69) — das Verhalten eines Blocks ohne Bus-Takt/Reset. Stock und
Legacy hatten den RTC-Treiber gebunden (Gate an; Legacy-Treiber schrieb HPD direkt). Im HDMI-Pfad
treibt die ARISC (`scp.bin`: 59× `l.movhi 0x0709`) den HPD-Pin; Dummy fasst HPD nie an.
**Vorbehalt:** laut früherer Zusammenfassung starb `SetSource` auch mit ARISC im Reset, und die
MIPS-Firmware hat keine 0x0709-Referenzen — H11 erklärt sicher den ARM-Hänger beim Lesen, nicht
sicher den SetSource-Tod. Test (billig, wenn das Gerät wieder bootet): (a) `r-ahb-rtc`-Gate/Reset im
R_CCU (`0x07010000`, Register des Vendor-`sun50iw12-r-ccu` für Index 0x14/Reset 8 — per Agent aus
dem Vendor-vmlinux ermitteln; unser Baum hat **keinen** R-CCU-Treiber für H713) einschalten,
(b) dann mit Marker `0x07091014` lesen — geht das jetzt, war das Gate der Grund für den Riegel,
(c) dann `SetSource(4)`; zusätzlich Gegenprobe `SetSource(4)` mit ARISC im Reset (prep ohne
`arisc_load.py`), um die ARISC-Beteiligung sauber zu klären.

**H11 präzisiert (Agent 3, selbst gegen D1-Treiber geprüft, 22:55):** Vendor-R-CCU `sun50iw12-r-ccu`
(Layout = D1): `bus-r-rtc` Gate **`0x0701020C` Bit 0**, Reset **Bit 16**; Vendor-RTC-CCU: **`rtc-spi` =
`0x07090310` Bit 31** (Parent r-ahb, im Stock-`clk_summary` an mit 200 MHz). Mainline: `rtc-sun6i`
kennt 0x310 nicht, unser RTC-Knoten referenziert weder Gate noch Reset. Vendor-RTC-Probe:
Reset → Gate → rtc-spi → Kontrolle GP0 (0x07090100). Die ARISC-HPD-Routine (`scp.bin` 0x10fac–0x1137c)
liest/schreibt 0x07091014 **ohne** eigenes Gate — sie setzt voraus, dass der Kernel den Takt an hat.
Kein Vendor-Linux-Code fasst 0x07091xxx an. Testskript `analyse/hdmi-seq/rtc_hpd_enable.py`
(read-only / `--do`: setzt 0x20C b16+b0, 0x310 b31, GP0-Kontrolle, dann Lesetest 0x07091010/14 mit
Marker — Riegel-Positivtest, nur mit Steckdose). Parser des Agenten: `tools/vendor_ccu_parse.py`.

**Nächste Schritte, in dieser Reihenfolge:**
1. Nutzer: dnsmasq neu starten (Kommando oben). Dann `sonoff_ctl off`/`on`, ssh, `bash /root/prep_after_boot.sh`.
2. Lauf 40 (H11): `python3 /root/rtc_hpd_enable.py` (lesen), dann `--do` (Marker!). Liest 0x07091014 jetzt
   (Stock: 6) → Riegel war der fehlende Takt; danach `SetSource(4)`. Stirbt es trotzdem: Gegenprobe
   `SetSource(4)` mit ARISC im Reset (prep ohne `arisc_load.py`), um die ARISC-Beteiligung zu klären.
3. Lauf 41/42: `SetSource(7)` (CVBS, analoger Videopfad mit memory_agent/VPROC) und Lauf 41: `SetSource(2)` (Image). Überlebt beides → strikt HDMI-RX-Init; stirbt CVBS → gemeinsamer Videopfad (dann Bisektion dort). Kommandos: `taskset -c 1 python3 /root/hdmi_seq.py run --phase 4 --i-mean-it --only setsource --source 7 --portmap stock --gap 500 --pre-source-wait 1 --listen-after 5`.
4. H6 (Nutzer am tio): `h713_disp commcall eaf13de5 4` nach `h713_disp init 0x30` in U-Boot — stirbt U-Boot auch, liegt es nicht am Linux-Zustand.
5. Firmware-Bisektion (Delegation an Agent, ich verifiziere): im U-Boot-Ladepfad (`h713_mips_release_raw`, wo schon der HDCP-Wait gepatcht wird) gezielt einzelne Aufrufe im HDMI-Init-Pfad durch `nop`/`jr ra` ersetzen (PHY_Reset 0x8b13e36c, PD-Toggle 0x8b13f580, PD_IDCLK 0x8b140310, SendHPDEvent 0x8b1383a0, Audio-PLL 0x8b13b1dc, AV-mute 0x8b134690) und je einen `SetSource(4)` fahren. Das ist die einzige verbleibende systematische Methode; sie braucht einen U-Boot-Neubau (build.sh, `uboot_make`) und das Einspielen von `uboot-proper.bin` (liegt in `/srv/tftp` — root-owned, **Nutzer**) oder den FEL-/Host-USB-Weg.
6. Parallel statisch: Offset von `PD_IDCLK` (Aufrufer von 0x8b140310) und das Ziel von `0x8b135290` bestimmen.

**Rückbau-Hinweise:** Modul am Board = Landezone+Deref-Prüfung (`/root/hy310-cpu-comm-callwq-test.ko`, Original `.bak`); `hdmirx_ctrl_enable.py` schreibt jetzt 0x203B01; `prep_nocb.sh` existiert für Läufe ohne Callback-Registrierung.
