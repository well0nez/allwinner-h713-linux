# Standby C2 — geparkt, 03.10.2026

Auf ausdrücklichen Nutzerauftrag geparkt. Kein Wake-Fix, keine weiteren Suspend-Proben, Builds oder Diagnosedeployments ohne neuen Auftrag. MIPS-Reload bleibt unabhängig davon hart geparkt. Keine Agenten, Commits, Integration, Pushes oder Releases durch diese Untersuchung.

## Ergebnis und Geräteabgrenzung

Diese Untersuchung fand am **HY310 / HY260_QZ713_V3.1** statt, nicht am HY300PRO-G-EU / HY200 QZ713DF A1. Suspend erreicht nachweislich den DRAM-Eintritt und den CPU-Reset; ein funktionierendes Aufwecken wurde nicht erreicht. Power-Taste ohne beobachteten Wake, programmierter Timer ohne beobachteten Resume. IR/CEC nicht abgenommen. Physischer Neustart ist Recovery, kein erfolgreicher Resume. HY300-Gegenprobe ausstehend.

## Abschlusszustand und Zugriff

SSH: `ssh hy310`, zuletzt 192.168.8.132, root/Keyauth. UART: `nc 192.168.8.180 2000`, Orange-Pi-ser2net, nur ein Client, ausschließlich lesend. UART ist derzeit dem HY310 zugeordnet. Keine Zugangsdaten in der Doku.

Beim Parken wurden die Originale mit dem begrenzten Rückrollwerkzeug wiederhergestellt und rückgelesen; normaler Reboot ausgelöst. Abschließende Bootprüfung siehe Abschlussnachtrag unten. Temporäre Clock-Hold-/Trace-Firmware ist kein zulässiger Dauerstand und kein Standby-Fix.

Originale und Rückweg:
- ARISC: `/usr/lib/firmware/h713-arisc.bin`, 176132 Bytes, SHA256 `d41731fa783dace3070264397064b28e2359a27b9e4708f3f7d40f1c3d876b7e`.
- U-Boot-proper/FIT: `/dev/mmcblk0p2`, Start-LBA 2048, geprüfte Länge 954368 Bytes, SHA256 `9059fd6b0ff58736d8dab3fca0a9a6bd8f1704125f2b24fa3bd3fa6570075c11`.
- Gerätebackups: `/root/standby-c2-hy310-arisc.before.bin`, `/root/standby-c2-hy310-uboot-proper.before.bin`.
- Gerätewerkzeug: `/root/standby-c2-restore-original.py`; lokale Quelle: `umbau/work/_deepreview/standby-local/tools/restore_hy310_original.py`. Prüft Board, Partition, Backuphashes und erlaubten Diagnose-Ausgangsstand, restauriert nur diese beiden Komponenten und verifiziert Readback. Reboot erforderlich, um Diagnose im SRAM zu entfernen.
- Sicherheitsstand während der Proben: `fan_stall_shutdown=Y`, `rails_off=N`; Power-Gate unverändert. Kernel 6.18.38, `mem_sleep` s2idle/[deep], PSCI 1.1.

## Durchgeführte Proben

Firmwarehash-Präfixe identifizieren Teststände; vollständige Hashes und Abläufe in STATE/REPORT und Belegen. Alle Varianten TEST ONLY, nicht zur Integration.

| Probe | Beobachtung / Grenze |
|---|---|
| Originalbaseline | PL4 als EINT4, beide Flanken, Linux-Wakeup aktiviert. BL31 nimmt Suspend-Frame 0x22 an. Kein Wake durch Power-Taste. |
| Vendor-Timer 0x26 | Korrigierter, ausgerichteter FIFO-Zugriff bestätigt Echo `[0x00260202,1,0xc0001388]` für 5000 ms; kein Resume. Echo beweist nicht, dass der Timer tatsächlich lief. |
| Früher BL31-Warmmarker W0, FIT 31b50457 | Kein W0 im gültigen Suspend-Mitschnitt. Ein früher abgelaufener Mitschnitt ist ausdrücklich keine negative Gegenprobe; UART-Zustand begrenzt auch den gültigen Befund. |
| Globale GP3/UART-Spur 67e74806 | Live 0x33003/04/05. 33004 nach Rückkehr aus DRAM-Eintritt 0x142dc, 33005 nach CPU-Reset 0x4b28. UART-Instrumentierung während Clock-Off kann selbst stören. |
| Gezielte Spur 6928ef49 + W0 | GP3-Routine bleibt original, nur ausgewählte Stellen gespiegelt. Wieder 33003/04/05, kein Timer-/Power-Wake, kein W0. |
| Clock-Hold 5dc40f0c | Speichert PLL-/Rootclockzustand, unterdrückt bestimmte Off-/LDO-Stores; CPU-Reset/DRAM/Wakepfad bleiben. Kein Wake. Kein Low-Power-Fix, Verbrauch damit nicht abnehmbar. |
| Rootclock-Save 24cf3e94 | Marker ER: Save-only 0xcdd8 tritt ein und kehrt zurück. |
| Erste Delay-Probe 8848d062 | Marker AB: Delay 0x6d04 am ersten untersuchten Aufruf kehrt zurück. |
| PLL-Save e20d88e5 | Marker CD: Save-only 0xcc2c kehrt zurück. |
| Restliche Delays 6c27531c | ERABCDFGHIJKLMN sichtbar; finales O fehlt. Fehlender UART-Marker allein ist kein Hängerbeweis. |
| Pfadauswahl 6ae86697 | NXYP sichtbar: Frequenzabfrage 0x59bc kehrt zurück, letzter Delay wählt Countdown 0x6e34, nicht ARM-Systemcounter 0x6c84. |
| Erste gepacete Wertausgabe cf2fb1bf | Nur 3/8 Bytes empfangen; unvollständig, keine Rücksprungadresse daraus ableiten. |
| Pacing je Byte 8cc8f72a | Vollständig `050b00002cef0100`: r3=2821, r9=0x1ef2c; weiterhin kein Wake. |
| Gepaceter Rückkehrmarker 49ae818b | Werte vollständig, kein O/T/Resume. UART-Timeoutpfad zusätzlich offline gegen dauerhaft busy geprüft. Kein Hardware-PC-Beweis. |
| Countdown-Klon mit Exitmarker 07dc485c | Werte vollständig, kein V/O/Wake. Auch das belegt ohne unabhängigen PC-/Hardwarezustandsnachweis keinen eindeutigen Schleifenhänger. |
| SRAM-Instruktionsvergleich nach Recovery | 0x6e34..0x6e4c und sämtliche Caves 0x1e000..0x20000 bytegleich installiertem 07dc485c, null Abweichungen. Gilt für diese Regionen, nicht beliebige Firmwaredaten. Kein weiterer Suspend danach. |

Ungepacte Wertausgabe a56996d9 wurde nur offline geprüft, nie deployed. Normalboots/Recovery zwischen den Proben sind dokumentiert, aber keine Wake-Erfolge.

## Methodik, Fehler und zurückgenommene Annahmen

- Erster FIFO-Versuch mit struct-Zugriff füllte den FIFO vor Suspend; auf native ausgerichtete uint32-Zugriffe korrigiert und vor gültiger Wiederholung neu gebootet. Kein Firmwarebug daraus ableiten.
- Mitschnitt teilweise vor Suspend abgelaufen; UART-Delivery teilweise unvollständig. Nur gültige, rechtzeitig laufende Mitschnitte als negative Beobachtung verwenden.
- RTC-Delay-Hypothese 0x6b68 nicht belegt; relevantes Flag war im normalen Ausgangszustand 0.
- Behauptung, das Modell übersehe den Delay-Pfadwechsel, zurückgenommen: STORE 0xdf10 setzt 0x16b00 während Suspend auf 1. Modell mit ursprünglichen Flags und eingefrorenem ARM-Counter erreicht dennoch den Wake-Wartepfad über Countdown. Kein bewiesener Systemcounter-Hänger.
- Modelle verwenden synthetische MMIO-Antworten; teilweise beschleunigten Countdown. Zusätzlich lokale unbeschleunigte Register-/Flag-Gegenproben, aber kein vollständiges Hardwaremodell. DRAM-ACK zunächst modelliert, später durch reale Rückkehrmarker gestützt.
- Falscher Tail-Anker 0xdddc wurde vor Deployment vom Generator abgelehnt; korrekt 0xdde4. Erste Wertmodell-Erwartung 2400 statt tatsächlicher 2821 korrigiert. Erstes Timeout-Testbudget zu kurz, mit ausreichendem Budget bestanden.
- Zwei SRAM-Leseversuche per Byte-Slicing lieferten SSH exit255 ohne Daten; auf native uint32-Leser korrigiert. Keine Ursache dieser Lesefehler behaupten, kein Firmwarebefund.
- Wiederholtes Fehlen von V/O engt die beobachtete Strecke ein, ersetzt aber keinen Nachweis des tatsächlichen ARISC-PC und keine kausale Reparatur.

## Quellen und Ablage

Alles unter `umbau/work/_deepreview/standby-local/`: `STATE.md` chronologische Zwischenstände, `REPORT.md` Analyse samt späteren Korrekturen, `tools/` Generatoren/Modelle/Rollback/Reader, `evidence/hy310/` Originale, JSON-Belege und UART-Rohdaten. Dieser Handoff ersetzt historische Aussagen zu aktivem Test und installierter Diagnose.

Wichtige Rohcaptures: `suspend-baseline-uart.log`, `suspend-timer-uart.log`, `arisc-trace-live-uart.bin`, `clock-hold-live-uart.bin`, `clock-entry-live-uart.bin`, `delay-path-live-uart.bin`, `countdown-exit-live-uart.bin`. Einige enthalten mehrere Varianten/Recoveryboots; READY-/Boot-/Hashbezüge aus JSON/STATE mitlesen. `countdown-exit-runtime-code.json` belegt den SRAM-Vergleich. Modelle und Probe-*proof.json sind keine Geräte-Wake-Abnahmen.

RE: `analyse/arisc-frame/full-disasm.txt`, `analyse/arisc/monitor.asm`, frühere Nachtlogs/Standby-Briefs; eigene TF-A-Kopie `standby-local/tfa-hy310`. Kernelbasis unter `_deepreview/stufeB/src/mainline/build/`; frühere TF-A-Basis `_deepreview/stufeC/tfa`. Geschützte Dumpbereiche bleiben geschlossen.

Crust-Vergleich: lokales `umbau/work/FB-CRUST/crust/crust/` enthält für H713 keinen vollständig implementierten Deep-Standby-/DRAM-Self-Refresh-/Clock-Gating-Pfad. Daher keine positive H713-Wake-Referenz. Upstream [H6 R-CCU](https://github.com/crust-firmware/crust/blob/master/drivers/clock/sun50i-h6-r-ccu.c) und [gemeinsamer R-CCU-Code](https://github.com/crust-firmware/crust/blob/master/drivers/clock/r_ccu_common.c) liefern Sequenzideen, keine Beweise für H713-Register oder einen fertigen Fix.

## Wiederaufnahme nur auf neuen Auftrag

Nicht die gleichen negativen Proben blind wiederholen. Zuerst aktuelle Hardware-/Firmwarebasis verifizieren und eine unabhängige Beobachtung des letzten Delay-/Wakepfads planen. HY310-Lösung und anschließende HY300-Abnahme getrennt protokollieren. Safety/Power-Gate nicht umgehen. Audio-Plopp beim Abschalten vor Lüfterstopp bleibt eine separate Nutzerbeobachtung, kein bewiesener Wake-Zusammenhang.

Übergreifender Stand: doku/138 und `wlan-bt-local/HANDOFF.md`; IR-Paket beim anderen Integrationsstrom, MIPS hart geparkt, WLAN/BT-Warmtest bestanden bei offenem HCI-Kaltstart.

## Verifizierter Abschluss

Normaler Reboot erfolgreich, anschließend SSH erreichbar (Uptime 122 s). Original-ARISC-Hash `d41731fa...` erneut bestätigt, Lüfter-Stallschutz `Y`. Original-FIT vorher per Readback bestätigt. Kein weiterer Suspend; keine visuelle Bildabnahme aus SSH abgeleitet. Das autonome Standby-Ziel ist pausiert, nicht erledigt.

## Übergreifende Aufgabenliste zum Parken

### Erledigt / getestete Ergebnisse
- HY300-Bildfehler: falsche LVDS-Farbtiefe korrigiert, sichtbare positive Abnahme; RGB-Gammakanäle separat korrigiert. Laut Integrationsnachtrag in doku/137 bereits parallel übernommen; vollständige Image-/Kaltstartabnahme nicht damit gleichsetzen.
- Neues Warp-Kalibrierbild deployed und vom Nutzer positiv beurteilt.
- IR: gezielte Links/Rechts-Abnahme 5/5 je Taste, weitere Tastenerfassung; funktionales Patchpaket und separate Diagnosepatches fertig. Keine vollständige Resume-/Power-/Zuverlässigkeitsabnahme.
- WLAN/BT am GEU: Koexistenz im Warmtest, UHID, echte Mausbewegungen und Disconnect/Wake/Reconnect getestet; Helper korrigiert. Issue #2 aktualisiert und geschlossen. Kein produktionsfähiger HCI-Kaltstart-Fix daraus ableiten.
- Standby-Triage dokumentiert und Diagnose beim Abschluss entfernt; Wakeproblem bleibt offen.

### Übergaben / Pipeline
- IR-Paket `ir-local/ready/README.md` zur Integration durch den zuständigen anderen Arbeitsstrom, nicht diese Sitzung. TEST-Instrumentierung nicht ausliefern.
- WLAN/BT-Patches aus `wlan-bt-local/` zusammenführen und im vollständigen Image prüfen; HCI-Kaltstart, vollständige Tastencodes, Neustarts und HY310-Gegenprobe offen.
- Parallele Commits/noch uncommittete Pipeline-Arbeiten vor Übernahme abgleichen; historische Handoff-HEADs sind keine aktuelle Vollinventur. In dieser Sitzung keine Integration/Commits.

### Offen
- HCI-Kaltstart separat beheben; KEY_POWER/logind-Verhalten entscheiden.
- Lampen-PWM und Stock-bl_power 4→0 untersuchen; nicht mehr als belegte Ursache des inzwischen korrigierten LVDS-Bildfehlers behandeln.
- Gleiche Platine HY200 QZ713DF A1 unter gemeinsamem Board führen, Firmware-/DRAM-/eMMC-Varianten erhalten.
- restore-stock für weitere eMMC-Größen; optionales Hardwareprofil ohne erzwungene Kamera-/Motor-/Sensor-Abhängigkeiten. Tatsächliche Hardware später auf Mainline prüfen.
- Keystone-Auto: fehlenden/spät verfügbaren Sensor ruhig behandeln, vorübergehende Lesefehler nicht dauerhaft stilllegen. Patch 0009 zurückgestellt, keine fertige Lösung.
- Webpanel am Ende gemeinsam prüfen: Button-Klicks verziehen Ansicht, Zoom; feinere Ecke/Kante-Bedienung, Seitenverhältnis/geführt korrigieren und Undo/Redo. Konsole durch Warp bleibt TODO.
- Audio-DSP-Abgleich, Abschalt-Plopp separat; laute Proben nur nach Vereinbarung tagsüber.
- Reboot-/eMMC-cmd18-Beobachtung separat triagieren.
- B8/HDCP1.4 EL3 in Stufe C; geschützte Quelle und reale Abnahme offen. Crust vorbereitet, vollständiger H713-Deep-Standby/Wake nicht abgenommen.
- Stufe E: reproduzierbare Doppelbuilds, zweite Installation, 20 Kaltstarts und spätere Releaseentscheidung.

### Geparkt / ungetestet
- MIPS-Reload hart geparkt: Oops-Gegenproben/Fixes vorhanden, Bild nach Reload nicht zuverlässig; kein gelöster Reload.
- C2/Standby geparkt: kein Wake, nur HY310-Triage dieser Sitzung; HY300-Gegenprobe offen.
- C1 UART-Brücke nach Stromzyklen geparkt.
- B7 SAFETY geparkt, Lüfterstecker unzugänglich; Schutz nicht deaktivieren.
