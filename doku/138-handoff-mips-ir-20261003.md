# Handoff: MIPS-Reload und IR am HY300PRO-G-EU
> **Ueberholt.** Stand und Todos leben in `TODO.md`, der letzte Handoff ist `152`; dieser Text bleibt als Beleg fuer den Tag, an dem er geschrieben wurde.

Stand 03.10.2026. Sitzungsauftrag: MIPS bis zum getesteten Ergebnis;
nach schwarzem Bild auf Nutzerwort geparkt, naechster Punkt B5/IR.
Keine Agenten, kein Commit/Push/Release. Main und GEU-Checkout zuletzt
beide bf72eb3. Nachfolgende Builds liegen ausschliesslich in eigenen
Arbeitsverzeichnissen, nicht in der Integrations-Pipeline.

## MIPS: Oopses behoben, Bildabnahme fehlgeschlagen

`umbau/work/_deepreview/mipsreload-local/STATE.md` zuerst lesen.
Eigenstaendige GEU-Kopie aus Kernel89ac4b87; nur MIPSRELOAD0167/a/b/c/d
angewendet, keine komplette Fable-Welle. Containerclang20 baut passende
Module; gelieferte cpu_comm.ko besteht Emulator und alle10Tests ohne Skip.
Gegenproben reproduzieren alle3altenOopses. Modellvergleich prueft
selektierte Shared-Memory-Bytes, kein Cache-/MIPS-/Notifier-Modell.

Neue Luecke im Pruefwerkzeug gefunden: WARNs wurden gesammelt, aber nicht
als Fehler gezaehlt. Eigene Kopie korrigiert und Gegenprobe ausgefuehrt;
`0001-gate-count-warnings.patch` liegt dort, Originalpaket unveraendert.

Drei Reloads liefen bis READY/Capture/video0/Planeon/Suspend0, ohne alte
Oopses/Spinlock-Timeouts. T1READY200ms, T2READY210ms. **Keine visuelle
Abnahme daraus ableiten:** Marco meldete nachT3 dauerhaft schwarzes Bild,
auch nach physischem HDMI-Replug. LVDS blieb8bit (01e0a40c), Ringzeiger
wechselten. Ursache unbekannt. Keine Regler-/Replug-/Reload-Proben mehr
durch uns nach dieser Meldung. Mitschnitte reload-T*, black-output-snapshot.json.
HDCP22-Datei bei Reprobe fehlte nach Boot-Keydienst; nur ungeschuetzte
Quelle getestet. Geschuetzter Reload ist nicht abgenommen.

Erster softwareseitiger Reboot zeigte eMMC `data error cmd18` und
`send stop command failed`, WLAN hing. Marcos erneuter Boot kam bisShell;
fehlendes HDMI war dort zunaechst der ausgeschaltete Laptop. Das ist
eine getrennte Beobachtung in doku/61, keine bewiesene MIPS-Ursache.

## IR: eigene Testbasis, Stand siehe STATE

`umbau/work/_deepreview/ir-local/STATE.md` zuerst lesen.
Basis urspruenglicher GEU-Kernel89ac4b87 ohne MIPSRELOAD. IR_SUNXI=y,
deshalb Image.gz/DTB neu im Container gebaut, .config unveraendert,
keine Compilerwarnungen. FB-REMOTEb0001/0002/0003/0003a sowie TEST0003t
angewendet. **TEST0003t ist Messinstrumentierung, nicht fuer Release.**

Installierter IR-FIT:
`e5a724648d10cafe5f5a36977d995064ad962c6eca3b8683f0dfeca0069957ec`.
Originale CPU/AFBD-Module und RGB-Gamma-TV aus dem MIPS-Backup
wiederhergestellt; MIPS-Testmodul aus /lib/modules nach /root verschoben
und depmod. Neuer Boot erfolgreich; Marco bestaetigt Bild wieder da.
Neue Bootmessung ohne vorherige eMMC-Lesefehler; keine Reboot-Dauerabnahme.
Kalibrierungs-Warp-Binary bleibt installiert und unveraendert.

PL9-Messung: Probe CFG1ffffff3f/PULL000041005; nach ARISC CFG1222222ff,
nach Re-Apply2222223f. Pull-up blieb00041005. Belegt: ARISC schaltet
den Mux ab, Fix stellt ihn zurueck; Pull-up in diesem Lauf nicht geloescht.
R_IR_RX81000002 ergibt8MHz, CIR7904, RXCTL4, RXINT1f13.

Kerneldekodierung OK0x020b gemessen. Menue0x021e/KEY_MENU139 und
Zurueck0x021f/KEY_BACK158 mit Druck/Loslassen gemessen. Volle NEC-Leader
8960/4528 und8992/4480us (Repeat-Leader etwa9000/2250 separat, normal).
Pfeiltastenaufnahme lieferte nur UP0x0209/KEY103 und beschaedigte
Rohframes mit136/200us Pulsen statt etwa563us. Nutzer bestaetigte
mehrfach alle Tasten direkt vor dem Geraet gedrueckt. IR nicht abgenommen;
Ursache im Empfangspfad offen, nicht als reines Keymap-Problem behandeln.

ir-keytable1.30.1-1 installiert (Apt-Indizes waren leer, zuerst update).
15Eintraege aus fd02-Keymap **ohne Power** als temporaere Testmap geladen.
Tabelle in /root/ir-local-20261003/keymap-test-no-power.toml. Original-
Readback keytable-before.txt gesichert. Noch keine persistente Bootmap;
KEY_POWER-Policy und Resume bleiben offen. LIRC-Pulse und rc-core-
Scancodes sind verschiedene Ebenen desselben Kernel-Empfangspfades,
LIRC umgeht Pinmux/Abtastung nicht.

## Zugriffe und Rueckweg

SSH `ssh hy300pro`, zuletzt *geschwärzt am 23.10.2026: Heimnetz-Adresse*, root/SSH-Key. UART-Bruecke
`nc <geschwaerzt 23.10.2026: Heimnetz-Adresse> 2000`, nur ein Client; Mitschnitt ausschliesslich lesend.
Keine Passwoerter/Keymaterial in diesem Handoff. WLAN-Zugang nicht abdrucken.

Geraetebackup /root/mipsreload-20261003:
- h713-kernel.fit: urspruengliche GEU-Version, SHA8c49206f4556269c...
- h713-tv: RGB-Gamma-Version, SHAad5c5defb22a754b...
- hy310-cpu-comm.ko: Original78c5944f7c6e67de...
- sun50i-h713-afbd.ko: Original45fd862b1a10bf7a...
- new/: komplette MIPS-Testdateien; sun50i-h713-mips.deployed.ko erhalten.

/root/ir-local-20261003/mips-test.fit sichert den zwischenzeitlichen
MIPS-Test-FIT. new/ enthaelt IR-FIT mit SHA256SUMS. Keine Daten geloescht.
Zur urspruenglichen GEU-Version reicht nach Abgleich die gesicherte
h713-kernel.fit aus dem MIPS-Backup; originale CPU/AFBD/TV sind schon
wiederhergestellt. Rueckwechsel immer ansagen, FIT atomar ersetzen/sync,
bei Problemen keinen unerklaerten haengenden Test abbrechen.

## Offene Punkte

- Pfeile/weitere Fernbedienungstasten vervollstaendigen; Power auslassen.
- IR-Messlog0003t vor Auslieferung entfernen; Boot-Keymap/Power-Policy klaeren.
- Resume0003a erst mit funktionierendem Standby pruefen.
- MIPS-Schwarzfehler separat analysieren; READY ist keine Bildabnahme.
- Einmaliger Reboot/eMMC-Fehler bleibt Beobachtung, nicht geloest.
- Webpanel ganz am Ende gemeinsam: Button-Klicks verziehen Ansicht,
  Zoom entspricht Erwartung nicht. Weitere UI-Ideen in doku/61.

## Wiederaufnahme: Diagnose vorbereitet, Zugriff aktuell gesperrt

Diagnose-FIT ir-local/ir-counter-test.fit fertig, SHA256
bc83412c2ac664ff723f6ba2f53582ced36c11ee9b9132bdb6284be1d6e4527b.
TEST0005 zaehlt IRQs, FIFO-Bytes/-Overflows, PacketEnd, maximalen
FIFO-Fuellstand, Clamps und rc-core-Store-Fehler. Patch mit fuzz=0
und Bytevergleich geprueft; counter-build-fixed.log dokumentiert Build.
Noch nicht installiert. capture-all-events.py erfasst auch MODE2-Overflow
(Typ4), den alte Aufnahmen ignorierten. Keine Dekodiertoleranz geaendert.

Nutzer hat Pause aufgehoben. SSH-Pruefung bei Wiederaufnahme scheitert
bereits lokal mit socket: Operation not permitted (Netzwerksandbox).
Keine Geraeteaenderungen. Letzten dokumentierten Laufzeitstand vor
Deployment neu verifizieren, sobald Netzwerkzugriff wieder moeglich ist.

IR-Aufnahme01 regulaer beendet (DONE). Endzaehler: irq=130 bytes=2320 overflow=0 packet_end=34 available_max=32 clamped=0 store_errors=0. Alle sieben getesteten Tasten mit Down/Up dekodiert; Links/Rechts/Hoch/Runter je2, OK3, Menue2, Zurueck1 Tastendruecke. Keine Hardware-/LIRC-Overflows, keine Clamps/Storefehler. Vorherige gestoerteFrames bleiben ungeklart; keine vollstaendige Zuverlaessigkeitsabnahme. Beleg: ir-local/counter-capture-01.log. Diagnosekernel bleibt installiert, Power weiterhin aus Testmap ausgeschlossen.

Gezaehlter IR-Bootvergleich: BootA Wiederholung31Down/Up (Links1, restje5), BootB28Down/Up (Links0,Zurueck3,restje5). Nutzer BootB done aber schnell, Bedeutung noch nicht geklaert. Rohframeanalyse bestaetigt dieselben Vollframes, keine kaputten Vollheader-Kandidaten; keine nachgewiesene Decoderverwerfung gueltigerFrames. BootB regulaer DONE, Zaehler irq=236 bytes=4106 overflow=0 packet_end=56 available_max=32 clamped=0 store_errors=0. Empfangsregister gleich. NICHT als bestandene35/35Abnahme behandeln; fehlende Links-Signale gezielt mit zeitlich erfasster Einzelbetaetigung pruefen. Analysewerkzeug analyze-counted.py; timestamped Reader vorbereitet, nicht deployed. Keine Empfangsparameter veraendert.

Gezielte Links/Rechts-Aufnahme regulaer DONE, Session34820 exit0. Links5/5 Rechts5/5 Down/Up, unabh. Rohcheck je5Vollframes und15Repeatheader, keine kaputtenVollheader. Endzaehler irq=322 bytes=5668 overflow=0 packet_end=82 available_max=32 clamped=0 store_errors=0. Nutzer drueckte gruppiert ca1sAbstand, alle zehn registriert. Fruehere arrows-combined-Rohdaten erneut analysiert: UP1Vollframe,3Repeatheader, ein ungueltigerVollheader bit0space936us; Fehler real in Rohdaten, Ursache weiter offen. Kein bewiesener Decoder-/Keymapfehler, kein Beweis fuer 100%Zuverlaessigkeit. Diagnoseinstrumentierung bleibt im Testkernel, Resume/Bootpersistenz/Power nicht abgenommen.

IR-Patchpaket fertig unter umbau/work/_deepreview/ir-local/ready/README.md. kernel/series:4funktionalePatches, diagnostics/series separat TEST ONLY. rootfs/series: eigenstaendige optionale fd02-Keymap15Bindings ohnePower, keine automatischeAktivierung/BT-Abhaengigkeit. Basis/Integrationshinweise/Hardwaregrenzen dokumentiert. GitapplyCheck+fuzz0 erfolgreich, DiagnoseStack bytegleich getesteten Quellen, TOML geprueft, SHA256SUMS. Kein neuer CleanKernelBuild, keine Main-/Geraeteaenderungen.

MIPS-Triage aktualisiert: umbau/work/_deepreview/mipsreload-local/triage-20261003/REPORT.md. Fehlendes TCON-Handover nach Firmwarestart staerkster Verdacht; kein Post-T3-TCON-Dump, daher unbewiesen. VP-Init-Antwort wird verworfen; Stock wartet auf1. Userspace-Exitstatusfehler reproduziert, Draftpatch+Gegenproben vorhanden. Aktuelle Originalmodule/IR-FIT read-only bestaetigt, Quelle momentan no signal. Kein neuerReload/Deployment; Report enthaelt naechsten kontrollierten Test.

MIPS-Diagnosestand gebaut und installiert: diagnostic-run/STATE.md. FITd894e800 (IR-KernelImage bytegleich), neue CPU/AFBD/MIPS/HDMIRX-Module; HDMIRX loggt VPInit-Antwort, TV propagiert Reloadfehler. Alle10OfflineTests bestanden. Backup /root/mips-diagnostic-20261003/backup. Reboot erfolgreich, VPInit Antwort1,HDMI1080p60,PanelTiming1280x720. NochKEINFirmwareReload: sichtbaresAusgangsbild aus Nutzerfrage ausstehend. UART300sSession17548 liefert bisher nurNUL; keineUART-Beobachtung behaupten.

MIPS EinzelReload wiederSchwarz nachRebind (Nutzerbestaetigt). InputCapture jetztvollstaendig gesichert/visuellgeprueft: MintLockscreen klar erkennbar. TCONWertebleibenkorrekt1280x720, VPInitAntwort1, alterTVnachUnbindinactive/MainPID0. Problem weiter downstream; keinblindesTimingfix. EinzelTCONLatchTest vorbereitet und read-onlygeprueft, NICHTgepulst. Details diagnostic-run/STATE.md, black-ring.png, display-diff.txt.

### MIPS-Diagnose: TCON-Gegenprobe und R3/R4

Arbeitsstand unter `umbau/work/_deepreview/mipsreload-local/diagnostic-run/STATE.md`. Keine Integration/Commits/Pushes. TCON-Test im Reload-Schwarzstand unsichtbar; identischer Test nach Reboot vom Nutzer als sichtbar bestaetigt. Beide Laeufe automatisch restauriert. R3/R4 wieder schwarzes Bild nach Reload, Recovery-Reboot stellt Bild her.

PIO B/F/H CFG/Pull/Drive unveraendert; Panel PF6/PH16 weiterhin Ausgang/High. PH13 Data aendert sich (Lueftertacho). 16 ausgewaehlte CCU-Worte inklusive Display-PLL/Gates/Reset identisch zwischen Schwarz und Recovery. Volle CFG-/TSE-Fenster-Hashes identisch vor/nach R4; TCON-Rasterzaehler laeuft in beiden Zustaenden (2770 Samples/3s, 1477/1469 verschiedene Werte). Keine konkrete Reparaturursache bewiesen.

Aktuell zeitbegrenzter LVDS-Farbquellentest (`lvds-colour.c`, Register051c00b0/b4/b8) mit gesicherten Originalwerten und automatischem Restore nach60s. Ergebnis und Restore im neuesten STATE/Log pruefen; keine offene visuelle Frage als Erfolg behandeln. Geraet kann bis Recovery im schwarzen R4-Zustand stehen.

LVDS-Farbquelle: valide Positivkontrolle jetzt ueber Konsole (HDMI abgezogen), Nutzer ROT SICHTBAR; aktive Register3ff00000/3ff00000/7f bestaetigt, danach RESTORED200/0/38. Erster Versuch nachRecovery war SSH-Timeout und NICHT gestartet. R5-Konsole nachReload NutzerSCHWARZ. GezieltPanel-PLL058c0014Bit31 gepulst, Ruecklesewertvor/nachb8002300; visuelleWirksamkeit noch offen. AktuellDetails `diagnostic-run/OUTPUT-TRIAGE.md` und STATE.

R5 Panel-PLL-Einzelpuls wirkungslos (Nutzer schwarz). Neuer TEST-ONLY Workspace-Preserve-Parameter gebaut/deployed: `0003-TEST-ONLY-mips-preserve-resident-workspace.patch`, Modulsha1c7c3d5290683a83801ceb29dab2e59ed08973608f7ffee47ca4ce1d753ab088. Original gesichert `/root/mips-diagnostic-20261003/backup/mips-before-preserve-test.ko` SHA cf35160c.... Reboot erfolgreich, Parameter N/defaultaus, noch kein Preserve-Restart; Konsolenbaseline visuell pending. FIT/Image/sonstige Module unveraendert. Das ist residenter Neustart ohne RAM-Ersatz, kein vollstaendigerFirmwareReload.

PreserveResident-Test durchgefallen: Nutzer schwarz, BereitschaftNOTready(-110), VP_INIT -19, CaptureRebindEAGAIN. test_preserve_workspace perTrap/verifiziertN. Kein weitererRestart imFehlerstand; vorherigesModulcf35160c...wiederhergestellt,depmod/sync/Reboot. Recovery-Bild nochbestaetigen. Hypothese nurRAM-Erhalt damitnichtbestaetigt; Stock10ms/SharedMemory-Verhalten nichtgleichgesetzt. Logs unterdiagnostic-run/preserve-*.log.

Neuester Stand: Recovery-Konsole bestaetigt. Kontrollprobe Captureunbind/rebind OHNEMIPSreset ebenfallsKonsole sichtbar, VPInit1, reloadstatusnever. Damit Capturewechselallein keinRepro. Stockcaller startSvp laedtFirmware VORlibmips_restart; nurdieeinzelneRestartfunktionohneCallerwarkeinvollstaendigerStockvergleich.

Offline neu dekompiliert aus KOPIE deroffenen AP3m/ge2d-DB: `diagnostic-run/panel-stock/sequences.txt`, `lvds-reset.txt`, `fifo.txt`. Stockge2d_suspend/resume schaltetPanelpower/generischePanelGPIOs undspieltDisplaytabellenneu; FIFOthread liest05880fe0alle300ms undpulst05700088Bit8 beiFault. LetzterFaultmonitorwar0; keineFIFOUrsachebehaupten.

Nächste konkrete Probe vorbereitet, NICHT ausgefuehrt: `panel-ph16-pulse.c`/ARM64Tool, guardedGPIOmux/data, PH16Low2ms/High5mswieUBoot, PF6/PB5/Systemgateunberuehrt. PH16 istStockDTpanel_gpio_0, genaueFunktionunbewiesen. NutzerfreigabefuererstmaligenGPIO-Schreibtestpending; ohneAntwortkeineDeployment/Ausfuehrung. Geraet aktuellfunktionierend,HDMIab/Konsole.

PH16Einzelprobe vomNutzerfreigegeben. R6normalReloadready0/Capturezurueck, NutzerSCHWARZ. PH16low2ms/high5msausgefuehrt, RuecklesePH16=1/PF6=1; PIOvor/nachgesichert. VisuelleWirksamkeitpending. KeinePF6/PB5/Systemgatewrites, keineFreigabefuerPanelrailcycleausdiesemJAableiten.

R6PH16-PulsNEGATIV: NutzerweiterhinkeineKonsole/schwarz. GPIO-Wertewiederhergestellt, keinFix. KeineweitereGPIO-/Panelrailprobe. RecoveryRebootangekuendigt.

Aktueller UNERWARTETER Zustand: Nach voruebergehendem elog-Level1->3 in `/boot/mips/display_cfg.xml` und Reboot istSSHnach140snicht erreichbar, ARPFAILED. Modus1/unveraenderteDisplaysettings; neueXMLsha11b47d7a23809402d0418a012a3946cadb89c85af29cef6b54bb27029aa9cedb. Original `/root/mips-diagnostic-20261003/backup/display_cfg.before-elog-info.xml` SHA b3e6e8f60d6f96ff458046af655f4b51e8e36ffc70f5107b0fef91badeca192a, ebenso lokaldiagnostic-run/display_cfg.before-elog-info.xml. Rueckrollen NOCHOFFEN. Testsangehalten, UARTread-only6s/nutzerstatusfrage. KeinINFOelogalsBelegvorhanden.

R7normalelogLevel1: NutzerSchwarz, alle90Stockregistervor/nachidentisch, TSE/PQFehlerauchimfunktionierendenBoot; keinDifferenzialbeweis. ROelogreaderSIGBUSmitaligned32-bitZugriffenbehoben; keineLesezeigerWrites. Volltexteelog-before/after.json/.txt.


## 03.10.2026 — MIPS-Reload HART GEPARKT (Nutzerauftrag)
Keine weiteren Reloads, Builds oder Liveversuche fuer MIPS-Reload ohne neuen Auftrag.
Letzter INFO-Versuch R8 endete mit -110/NOT ready, Capture war bereits vorher nicht gebunden; kein gueltiger Vergleich zum bisherigen ready/Schwarz-Fehler. Original display_cfg.xml nach physischem Neustart wiederhergestellt, SHA256 b3e6e8f60d6f96ff458046af655f4b51e8e36ffc70f5107b0fef91badeca192a. Aktuelle SSH-Pruefung bestaetigt Originalhash und laufendes Linux (*geschwärzt am 23.10.2026: Heimnetz-Adresse*). Nutzer meldet nach erneutem eigenem Reboot weiterhin SCHWARZ: Wiederherstellung des Bildes NICHT bestaetigt. Keine weiteren Geraeteschreibzugriffe nach diesem Auftrag.
Belege: diagnostic-run/elog-info-rollback.log, elog-info-failed-status.log, R8-elog-info-reload.log, elog-info-boot.json/txt. INFO-After leer und daher nicht als Ursachenbeweis verwenden. Fruehere Aussagen zur regelmaessig funktionierenden Reboot-Recovery gelten nicht fuer den jetzigen Zustand.

## Aktueller WLAN/BT-Abschluss (03.10.)

Der aktuelle geprüfte Stand mit erledigten/offenen Punkten, Zugriff, Build und Patchbasis steht in [WLAN/BT-Handoff](../umbau/work/_deepreview/wlan-bt-local/HANDOFF.md). Koexistenz im GEU-Warmtest, UHID, Maus und Wake/Reconnect positiv; HCI-Kaltstart, vollständige Tastencodes, Image-Integration und erneute HY310-Abnahme offen. [Issue #2](https://github.com/well0nez/allwinner-h713-linux/issues/2#issuecomment-5968711529) wurde auf Nutzerauftrag aktualisiert und geschlossen. Keine Commits.

## Standby-Abschluss / Parken (03.10.)

C2 am HY310 ohne erfolgreichen Wake auf Nutzerauftrag geparkt. Testfolge, Diagnosegrenzen, Original-Rückweg und Abschlusszustand: [Handoff 139](139-handoff-standby-geparkt-20261003.md). HY300-Gegenprobe nicht durchgeführt. MIPS bleibt hart geparkt; WLAN/BT-Abschluss und fremder IR-Integrationsauftrag bleiben unverändert.
