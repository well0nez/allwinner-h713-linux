# 143 - Gesamt-Handoff, Stand 04.10.2026 04:40 (Fable-Welle -> Release v0.96-beta)

> **Überholt.** Der aktuelle Stand der HDCP-Kette steht in [`docs/subsystems/hdcp.md`](../docs/subsystems/hdcp.md), die Durchführung in `doku/148`. Dieser Eintrag bleibt unverändert stehen, weil er der Beleg dafür ist, wann was gemessen wurde — nicht, weil seine Schlussfolgerungen noch gelten.

> **Redigiert (05.10.2026).** Aus diesem Dokument sind die Kennungen und Adressen entfernt, mit denen man das **Trusted OS des Herstellers** direkt anspricht — SMC-Kennungen, Funktionsadressen und die Lage des Hardwareschlüssels im eFuse. Die Befunde bleiben: *dass* der HDCP-1.4-Satz chipgebundenes Chiffrat ist, dass nur die Crypto Engine den Hardwareschlüssel sieht und dass sie ihn nicht nach lesbarem Speicher schreibt. Das erklärt unseren eigenen Weg; der Rest war ein Rezept für fremde Geräte und gehört nicht veröffentlicht.

Fuer eine neue Sitzung ohne Gespraechsverlauf. Leseordnung: diese Datei ganz, dann doku/141 (Plan mit Tabellen),
doku/142 (Grosstest-Protokoll), doku/61 oben ("Gesamtliste"), doku/134 (alle Testergebnisse der Welle), doku/140
(Zeitleiste der Nacht 03./04.10.). Memory-Dateien: ~/.claude/projects/-opt-Projekte-h713/memory/ (MEMORY.md).

## 0. Wer, was, Regeln (gelten weiter)
- Marco Onorati, Du-Form, deutsch; in veroeffentlichten Repos nur der GitHub-Name well0nez (vor jedem Push
  `git grep -i -E "onorati|bdg-solutions|inopuli"` ueber alle Repos, Zweige, Submodul-Commits).
- Projekt /opt/Projekte/h713 (kein Git im Wurzelordner). Repo umbau/src (= GitHub well0nez/allwinner-h713-linux,
  Zweig main). U-Boot-Fork als Submodul umbau/src/mainline/external/u-boot.
- NICHTS pushen, kein `gh release`, kein Merge nach main ohne Marcos ausdrueckliches Wort. Lokale Commits auf
  Zweigen sind erlaubt und gewollt.
- Nie dauerhaft loeschen (Marco bekommt den Befehl). Nie Passwoerter tippen. Bauen nur im Container h713-build
  (`podman exec h713-build bash -lc '...'`, Projekt = /work).
- Agenten: ohne Rueckfrage starten, wenn der Plan sie vorsieht; Opus fuer schwere Aufgaben (RE, Merges,
  Analysen), Sonnet fuer einfache (Uebersetzen, Doku, Skripte). Modellklasse "opus" = claude-opus-5-5. Briefs
  nach ~/.claude/AGENT-KONTEXT-VORLAGE.md + umbau/plan/briefs/FB-common.md; Agenten schreiben NUR nach
  umbau/work/<paket>/; Ergebnisse VOLLSTAENDIG selbst nachpruefen (Marco 04.10.: Tests selbst laufen lassen,
  Binaries selbst pruefen, Zahlen gegen Quellen, Geraeteskripte Zeile fuer Zeile) - Memory
  agentenergebnisse-selbst-nachpruefen.
- Geschlossene Ordner (nie lesen, nie an Agenten geben): analyse/hdcp-keys/, hy310-sicherung*, re/device-dumps/,
  umbau/fixtures-local/secure*, umbau/work/PQ1/material/. Keine Vendor-Bytes, kein Schluesselmaterial, keine
  MAC-Adressen in Repos oder Paketen. In Repo-Texten nur "-" als Gedankenstrich, ASCII, Englisch.
- Geraet: ein Befehl pro Schritt, kurze Timeouts, keine pgrep/pkill-Schleifen (Selbsttreffer), UART nur lesen
  waehrend Marcos Laeufen; wo Marco handeln muss (Stromzyklus, Taste, FEL-Kabel): Zug beenden und warten.
  Stromzyklen zaehlen und vorher ansagen. Power-Gate (h713_gate, Plan 103, PB5) nie anfassen.
- eMMC-Schreiben nur nach installer/h713/layout.py: SPL LBA 16, U-Boot-Proper LBA 2048 (FIT, 954.368 B im C0),
  Env LBA 14336; Secure Storage LBA 12288-14335 NIE schreiben (Installer laesst dort eine Luecke).
- Nie `echo mem > /sys/power/state` am HY310 (kein Wecken). Nie aic8800_* entladen oder h713-wifi stoppen ueber
  ssh (WLAN ist der einzige Weg). Bond der Fernbedienung erhalten.
- Laute Tests nur nach Ansage und Ja, nachts nie.

## 1. Zustand der Repos (04.10. 04:40)
| Ort | Zweig/Stand | Bedeutung |
|---|---|---|
| umbau/src | main 64f78a2 (sauber) | 14 lokale Commits vor origin/main (c289bb3..64f78a2: GEU-Board, Fernbedienung BT, Warp-Maske, Kernel 0169 hid-h713-remote, IR geparkt). NICHT gepusht. |
| umbau/work/_fable-main/src | Worktree, Zweig fable-main = 75a0169, 25 Commits ueber main, sauber | DIE ARBEITSKOPIE. Wird nach Stufe 4 per Fast-Forward main. Kommitliste: `git -C umbau/work/_fable-main/src log --oneline main..HEAD` |
| Submodul u-boot im Worktree | Zweig fable-main-uboot = 6fb736c (a830902 + Board-Merge) | fable-main zeigt auf 6fb736c. Im Submodul von umbau/src existiert dieser Zweig NICHT (dort HEAD 2de0cc8 losgeloest) - vor Stufe 5 abgleichen (`git -C umbau/src/mainline/external/u-boot fetch <worktree-submodul> fable-main-uboot`). Fork-Commits bed99d1, c459ea7, 2de0cc8, a830902, 6fb736c sind auf KEINEM GitHub-Zweig. |
| umbau/work/_integ-remote/src | remote-wlan-bt = main 64f78a2 | Integrations-Worktree der Fernbedienung, erledigt, sauber |
| umbau/work/_deepreview/stufeB/src | fb-stufeb auf c289bb3, 2 geaenderte + 6 unversionierte Dateien | Stufe-B-Testbaum; Reste = IR-Testpatches (Originale in FB-REMOTEb/patches), nichts verloren |
| umbau/work/_geu1-build/src | hy300pro-g-eu bf72eb3 (in main enthalten), sauber | alt |
| Zweig hy300-pro-ab | 2 Commits ausserhalb main (U-Boot-Zeiger Panel-A/B-Test 0x34) | pruefen, ob durch 2de0cc8 ueberholt, dann loeschen oder behalten (Marco) |
| doku/ (Projektwurzel) | kein Git | 134, 140, 141, 142, 143 sind die Quellen; umbau/src/doku ist eine getrackte Kopie aelterer Stuecke |
Identitaetspruefung fable-main 04.10. 00:12: 0 Treffer, alle Autoren well0nez. Nach jedem weiteren Commit wiederholen.
Gebaute Artefakte (VERALTET fuer Stufe 4, Bau von vorn noetig): FIT d0f4b129 (ohne 0179/0180/0181), Module
modules-fable.tgz, U-Boot hy310 978.944 B (uboot-hy310), U-Boot hy200-Basis mit DRAM 792 (build/uboot-hy200-geu, 978.944 B),
h713-tv cross 373.936 B (7a3406e0), Kernelbaum mainline/build/linux-6.18.38-421fd247* mit 0179-0181 angewendet.
Memory "Release-Bauten immer von vorn": vor dem Auslieferungsbau build/out, uboot-*, linux-*, rootfs/build loeschen.

## 2. Geraete
- HY310 (Marcos Hauptgeraet): ssh hy310 (192.168.8.132 ueber dem eigenen WLAN, DHCP, kann wechseln; ~/.ssh/config).
  Stand: main-Kernel 6.18.38 (FIT 2d9b6514), U-Boot 2026.07-rc5 = C0-Kette (SPL c0a53b5d, Proper 2eb0caf977e4 an
  LBA 2048), h713-tv d98e774f, Bluetooth UP mit FB-BTRESET-Unit und /usr/local/sbin/h713-bt-reset (vom Agenten
  gelassen; Original in /root/btreset/before/). Verzeichnisse /root/integ (to-stufeb.sh, to-main.sh, payload,
  before/), /root/btreset, /root/hdcp14d (C0-Backup lba2048-1864.bin, Test-Proper, Skripte), /root/b0..c0.
  Moduldirs /lib/modules/6.18.38 (main), .stufeB-c0, .prev, .old. Secure Storage byteidentisch mit der Sicherung
  vom 10.09. (sha256 cf2805fc...). Heute 5 warme Reboots, 0 Stromzyklen; der HY310 war 00:30-03:00 von selbst vom
  Netz (Ursache unbekannt, Marco hat ihn wieder eingeschaltet).
- HY300 Pro = HY300PRO-G-EU (Marcos zweites Geraet, Platine HY200 QZ713DF A1): ssh hy300pro (192.168.8.246),
  Zweig hy300pro-g-eu / TEST-Image, Einstieg doku/136, 137. Hat sc7a20, keine Kamera, keinen Motor, Luefter PH13,
  LVDS 8 Bit (U-Boot 2de0cc8), Lampe schwach (3.4 offen). BT-Kaltstart dort offen (0x1003).
- UART: nc 192.168.8.180 2000 (ser2net am Orange Pi), EIN Client, Bruecke haengt wahlweise am HY310 oder HY300
  (04.10. nachts am HY310). Lesen mit timeout; senden nur bei eigenen Tests. bootdelay 1: Prompt faengt man mit
  Leerzeichen alle 0,2 s ab (hat 04.10. geklappt).
- Laptop als HDMI-Quelle: mint-thinkpad 192.168.8.164 (ssh, xrandr, i915; kann nur HDCP 1.4).
- FEL: A-auf-A-Kabel speist parallel (Memory): erst Kabel ziehen, dann Steckdose, dann Taste.

## 3. Fable-Welle - was sie ist und was davon wo steht
Pakete umbau/work/FB-* (Briefs umbau/plan/briefs, Reviews umbau/reviews, Tiefenpruefung
umbau/work/_deepreview/deep-review-20260927.md). Verifikationsbuch doku/134 (Stufen A Userspace, B Kernel, C
Bootkette, D Audio, E Release). Ergebnis in einem Satz: A komplett bestanden, B bestanden ausser B3 (MIPS-Reload
durchgefallen), B7 (ungetestet, Stecker), B5-IR (geparkt); C0 Bootkette bestanden, C1 bestanden (04.10.), C2 Standby
durchgefallen (kein Wecken), C3 HDCP 1.4 durchgefallen (Key-Select 3 verweigert), C4/C5 entfallen; D1-D3 Audio
bestanden (Lautstaerkekurve 0,8 dB, HDMI vs Geraeteton 0,07 dB ueber 20 Runden).

### 3.1 REIN (auf fable-main, Stufe 1, Commits c192bc4..031dd6c)
Kernel 0170-0178 (EDIDb 0136z/za/zb/zc -> 0170-0173; HDCP22b 0168/0168a -> 0174/0175; AUDIO 0169/0169a/0170 ->
0176-0178); h713-tv-Stapel (EDIDb 0001-0003a, HDCP22b 0001/0003, AUDIO 0001, AUDIOb 0004/0005, DSPVOL 0002/0003);
Geometrie (KSREF/KSREFb, EDGEBLEND 0001-0004, MIRROR, Warp-Kalibrierbild, gl.c-Handmischung; SAFETY 0003 durch KSREFb
0006 abgedeckt); Autofokus (AFWAIT, AFSEARCH 0001-0004); Rootfs/Installer/Bau (AUDIOb 0003/0003a, INSTALL 0001-0005,
REPRO 0001-0005); U-Boot-Fork a830902 (UBOOTDBG 0001 commdev/elog, SAFETY 0004 panic=10); DOKU 0001-0007;
tools/check-py39.py. Tests gruen: Keystone, Panel, Autofokus, Fokus, Installer, Warp T1-T3.
### 3.2 RAUS / geparkt (mit "kommt rein, wenn") - Tabelle doku/141 "RAUS"
- FB-STANDBY (Kernel 0167-0172, tfa-0001/0003, Parameterbaum) + FB-STANDBYc 0167c: C2 Suspend erreicht, KEIN
  Wecken (doku/139). Rein, wenn ein Standby-Weg mit Wecken bewiesen ist. BL31 fuers Release OHNE tfa-0001/0003
  (sonst bietet der Kernel "mem" an und ein Suspend haengt das Geraet).
- FB-CRUST: geparkt (Marco 03.10.), nach Standby.
- FB-MIPSRELOAD/b: Oopses weg, Bild nach Reload schwarz (doku/138). Rein, wenn der Bildfehler verstanden ist.
- IR (FB-REMOTEb 0001-0003a, fd02-Keymap, ir-local/ready): geparkt als "broken" (Marco 03.10.): Maus und Mikrofon
  senden per IR denselben NEC-Code 0x66; Ursachen gefunden (rx_resolution-Ganzzahltrunkierung 2 statt 2,667 us;
  ARISC-Firmware schreibt blind 0x222222ff nach PL_CFG1). Rein, wenn die IR-Ursache geklaert ist. Bluetooth-
  Fernbedienung ersetzt IR vollstaendig (16 Tasten, Maus, Koexistenz, Kaltstart, Reconnect bestanden).
- FB-SAFETY 0001/0002 (Luefter-Backstop, Stall-Poweroff): am Geraet ungetestet (B7: Luefterstecker unzugaenglich).
  Rein, wenn B7 bestanden. SAFETY 0003/0004 sind drin.
- FB-HDCP14/14b (Kernel 0167/a/b + 0168/a, TF-A 0001/0001a SiP-Dienst, h713-hdcp-key 1.4-Teil, h713-ce): draussen,
  siehe Abschnitt 6. Der SiP-Dienst steckt im C0-BL31 (harmlos, ungenutzt).
- FB-HDCP22c, FB-BTFW, FB-GE2D: Analysepakete ohne Lieferpatch.
- HDCP22b 0002 (Serie), AUDIO/EDIDb-Dokureste mit alten Nummern: nicht uebernommen.
- KEY_POWER faehrt herunter: bleibt so (Marco).

## 4. Plan doku/141 - Stand je Stufe
- Stufe 0 (Resttests): C3/C4 durchgefallen bzw. entfallen, C1 bestanden 04.10. 02:25 (nach interaktivem
  `h713_disp init` IMMER `run boot_emmc`, nie `boot` - sonst zweiter Init, Handover kaputt, kein Bild bis zum
  naechsten Reboot; steht in doku/134 C1 und FB-UBOOTDBG/REPORT 6.5). HY310 zurueck auf main: ja.
- Stufe 1 (Integration): FERTIG (Abschnitt 3.1).
- Stufe 2 (Kleinkram 1-12): 1 Keystone SIGTERM=0 (af449cc), 2 measure --timeout (af449cc), 5 Treiberzeilen englisch
  (Kernel 0180, 9c5b773; Rootfs-Werkzeuge ba6c65f + 2eee31d), 6 country leer -> 00 mit Warnung (ba6c65f), 7 Warp
  tests/ (Stufe 1), 9 LINK 0x6d ehrlich benannt (Kernel 0179, 9382a23), 10 Rasterzeile (durch 0171 erfuellt, B1 sah sie),
  11 Doku Bluetooth/0x0c03 (f5a25d4, 4f607d3), 12 FB-BTRESET 0001/0002 (9971078). AM GERAET OFFEN (Stufe 4):
  3 Fokus-Metrik flach (+11 %, Belichtung), 4 Interlace-VICs 5/6/7/20/21 in der Modusliste (0172 hat Zwillinge,
  pruefen mit `h713-tv ctl status`), 8 Warp bei 120-Hz-Quelle 19 fps (busy=dropped) klaeren oder dokumentieren.
- Stufe 3 (Boards): 3.1 Board-Merge FERTIG (0e26943, 97b30a1, 970a7a5, 75a0169 + Fork 6fb736c), 3.2 Hardware optional
  FERTIG (7346c63, acd5127, e7c9448, 102b333; GEU-FEATURES via variant.env), 3.3 Keystone-Auto spaeter Sensor:
  durch 3.2 (udev-Regel startet die Unit, Condition statt Schleife) weitgehend erledigt - offen bleibt Restart bei
  exit 3/5 (Report-Frage 4) und Patch 0009 (RestartPreventExitStatus) ist damit ueberholt; 3.4 HY300-Lampe (Marco
  am HY300, doku/137: bl_power 4->0 Handover, PWM-Block unprogrammiert) OFFEN; 3.5 restore-stock weitere eMMC-Groessen
  (HY300 Pro 15273600 Sektoren) OFFEN, Agent (Sonnet reicht), setzt auf der Variantenstruktur auf; 3.6 Fremdgeraete-
  Profile (Issue #1 HY300 Pro des Melders 636 MHz; LPDDR3 hy200-qz713-v2 tpr0..2) OFFEN, Agent + Review.
  Geraetetests der Stufe 3: HY310 1 Boot (nichts darf sich aendern), HY300 1 FEL + 1 Stromzyklus (doku/142 4b).
- Stufe 4 (Grosstest): Protokoll doku/142 fertig (Befehle, Erwartungen, Dauer, Stromzyklen: HY310 ca. 2,5 h, 22
  Zyklen inkl. 20er-Block; HY300 5 Zyklen). Voraussetzung: Bau von vorn, E1 Doppelbau, Fremdensicht-Pruefung.
- Stufe 5 (Release): Fast-Forward fable-main -> main (vorher `git log main..fable-main --stat` gegen die REIN-Tabelle),
  RELEASES.md v0.96-beta, STATUS, Identitaetspruefung in frischem Klon aller Repos inkl. Fork, Push von main und Fork
  (Zweig fuer die Fork-Commits mit Marco festlegen), Tag, gh release mit Abbild + Installer-U-Boot + sunxi-fel +
  Pruefsummen, Release-Seite aus Fremdensicht. Offen aus doku/61 A: Beta-Warnung, GPT-Gegenprobe, Installer liest .zst,
  Recovery durch eine zweite Person, HDMI-Modustabelle vollstaendig.
- Danach (nicht release-relevant): HDCP-1.4-Fuse-Lesung am HY300 (Abschnitt 6), HDCP-2.2-Session (braucht 2.2-Quelle),
  Webpanel gemeinsam, Konsole durch den Warp, Schein-Standby wie Stock, Abschalt-Plopp, Geraetetoene als Funktion,
  GEU-BT-Kaltstart, BT-Firmware-Lizenz, Standby/Crust/MIPS-Reload/IR, Abschnitt 8 der Gesamtliste.

## 5. Agentenpakete dieser Nacht (alle fertig, alle nachgeprueft, Reports in umbau/work/<paket>/REPORT.txt)
| Paket | Modell | Ergebnis | Integriert | Offen aus dem Report |
|---|---|---|---|---|
| FB-HDCP22c | Opus | DDC-Probe korrigiert (Repeated-Start), Bksv/HDCP2Version, 0x6d-Deutung | 0179 | Session nur mit 2.2-Quelle |
| FB-REMOTEb | Opus | IR-Ursachen (Trunkierung, PL_CFG1), Patches 0001-0003t | nein (IR geparkt) | - |
| FB-HDCP14c | Opus | Vendor-Task byteidentisch, RSSK nicht am Key-Eingang: Boot-Vorbedingung ODER eFuse nicht gebrannt | Analyse | -> 14d |
| FB-HDCP14d | Opus | TF-A SiP 0x82000012 (nur 0xac02-Lesung, 1 ms Kappe), h713-ce efuse_flags, Kontrollvariante; von mir am HY310 gemessen (Abschnitt 6) | nein (Probe, nicht fuers Image) | HY300-Messung; Q2 boot0/BROM nur falls "gebrannt, ungesenst" |
| FB-BTRESET | Opus | zwei Fehler (erster Befehl nach warmem Reboot verloren; Close-Reset erreicht die Leitung nicht), Fix h713-bt-reset, 3 warme Reboots bewiesen | 9971078 | 9.1 Ursache A; 9.2 Kernel hci_ldisc-Fix (upstream-wuerdig); 9.3 GEU RTS/CTS; 9.4 lpm/btmode; 9.5 hciattach -s 1500000; wifi.md "Bluetooth is missing" ersetzt (erledigt) |
| FB-KLEIN-en (2 Runden) | Sonnet | Rootfs-Werkzeuge/Units/Tests/packages.txt englisch, country-Regel, 20 Wifi-Faelle | ba6c65f, 2eee31d | Testfaelle pruefen meist nur rc; `--pruefen` von h713-hdcp-key entfernt (nur --check) |
| FB-KLEIN-kernel-en | Sonnet | 8 Treiberdateien englisch, 790 Zeilenpaare, Spezifizierer-Selbsttest | 0180 (9c5b773) | "°C" -> " C" in zwei NTC-Zeilen (kosmetisch); arisc.c:2379 veralteter Kommentar (13 s/10 s) |
| ST3-FEATURES | Opus | 18 Patches: h713-features, Exit 7, udev-Regel, Panel blendet aus, /etc/h713/features | 4 Commits; 0002/0003 ERSETZT durch Merge (HELD-BACK.txt) | Q1 FEATURES je Variante (so gemacht), Q2 GEU-Sensor WhoAmI, Q3 Kameraname "HD camera" fest, Q4 keystone-auto Restart bei exit 3/5; echter Rootfs-Bau mit --board/--variant erst in Stufe 4 |
| ST3-BOARDMERGE | Opus | ein Board hy200-qz713df-a1, Varianten projector05061226 (GEU, 792) / projector09220931 (09-22, 624), Profil mit variants, Kernel 0181, --variant, Fork-Patch | 4 Commits + Fork 6fb736c | Q2 cstengers altes Flash-Layout entfaellt (eigener Baum), Q3 lange Image-Namen bleiben; boards/hy300-pro README veraltet (sagt "includes hy200") - Folgearbeit; tmp/ 2,6 GB loeschen (Marco) |
Agenten-Scratch zum Loeschen (nur Marco): umbau/work/ST3-BOARDMERGE/tmp (2,6 GB), umbau/work/FB-HDCP14d/build (128 MB),
/tmp/claude-1000/-opt-Projekte-h713/*/scratchpad/st3*.

## 6. HDCP - die ganze Geschichte (Stand 04.10.)
- HDCP 2.2: Key liegt im Secure Storage (hdcpkeyV22, 912 B, CRC ok), h713-hdcp-key uebergibt ihn, Firmware meldet
  "HDCP22_LoadKey ok", 0x41a[2]=1 beworben (B2 02.10. bestanden). Eine echte 2.2-Session braucht eine 2.2-Quelle
  (Stick/Konsole); der ThinkPad macht nur 1.4. `h713-tv ctl hdcp` zeigt fuenf Zeilen; 0x6d ist nur das Connect-
  Event-Flag der Firmware (0179).
- HDCP 1.4: Key-Blob (hdcpkey) liegt im Secure Storage, ist mit dem RSSK aus den eFuses verschluesselt; nur die
  Crypto Engine mit Key-Select 3 kann ihn in die Key-Senke entschluesseln. C3 (03.10.): Key-Select 3 wird aus Linux
  UND aus EL3 verweigert (ESR 0x11), Task byteidentisch zum Vendor (14c). 14d (04.10., 3 warme Reboots, Proper
  8108b20c / Kontrolle 017f04aa an LBA 2048, Stufe-B-Kernel, danach alles zurueck): PRCTL-Lesung des Flag-Worts
  0x240 = 0 (rssk/ssk/hdcppkf "not burned"), Schatten 0x240 = 0, Schatten 0x248 = 0x00400000, KONTROLLE
  prctl-0x248 = 0x00400000 = Schattenwert -> die Lesung funktioniert, die 0 ist echt: auf Marcos HY310 sind die Fuses
  laut Deutung (Bits 16/17/21 aus Stock-BL31) nicht gebrannt, HDCP 1.4 waere dort hardwareseitig zu.
  MARCO WIDERSPRICHT (04.10. 03:05: "nein das stimmt nicht", erinnert einen erfolgreichen 1.4-Test) -> Entscheidung
  am Geraet: (a) dieselbe Fuse-Lesung am HY300 Pro (GEU-Proper mit dem 14d-BL31, h713-ce.ko fuer den GEU-Kernel);
  (b) eine echte 1.4-Quelle am HY310 unter Stock-Android (Abzug zurueckspielen) oder unter unserem System mit dem
  HDCP14b-Pfad. Bis dahin: known-issues-Zeile (ae72dcc) sagt "gemessen, nicht gebrannt auf dieser Einheit".
- Secure Storage: nie von uns beschrieben; Geraet heute byteidentisch mit der ersten Sicherung vom 10.09. 23:53
  (hy310-sicherung/MANIFEST.json sha256 cf2805fc...). Items: hdcpkey, hdcpkeyV22, snum, wifiBleDatas (je 2x).
  `private` und Reserve0 wurden am 10.09. ohne Sicherung ueberschrieben (private war leer).

## 7. Offene Reste der Welle am Geraet (in doku/142 eingeplant)
Fokus-Metrik/Belichtung; Interlace-VICs; Warp 19 fps bei 120 Hz; FB-BTRESET-Abnahme (REPORT 8: Kaltstart, 2 warme
Reboots, Restart); ST3-FEATURES REPORT 5 (HY310: nichts aendert sich; HY300: not-present-Pfade, Seite ohne Fokus);
ST3-BOARDMERGE REPORT 6 (HY300: TEST-Image der Variante, DRAM 792 per tools/read_dram_pll.py, LVDS 8 Bit, Luefter,
Fernbedienung, /etc/h713/features); 20 Kaltstarte; Lampen-Pulsieren beim Boot zaehlen (doku/131).

## 8. Naechste Schritte (Vorschlag, Reihenfolge)
1. 3.5 restore-stock (Sonnet) und 3.6 Fremdgeraete-Profile (Opus + Review) als Agenten; beide auf der neuen
   Variantenstruktur (boards/hy200-qz713df-a1/variants, profiles "variants", --variant). Briefs neu schreiben
   (kein Entwurf vorhanden). Danach nachpruefen wie oben.
2. Stufe 4 vorbereiten: Submodul-Zweig in umbau/src nachziehen, Bauverzeichnisse loeschen, `release/build-all.sh
   --version v0.96-beta-rc1 --board hy310 --vendor <Abzug> --wifi-env <wifi.env>`; zweiter Bau im frischen Klon
   (E1); HY300-TEST-Image `--board hy200-qz713df-a1 --variant projector05061226 --test-image`.
3. Grosstest nach doku/142 mit Marco (Stromzyklen vorher ansagen; UART-Mitschnitt immer vor dem Einschalten).
4. Stufe 5 nur auf Marcos Wort.
Parallel, wenn Marco Zeit hat: 3.4 HY300-Lampe; HDCP-Entscheidungstests (Abschnitt 6).

## 9. Fallen, die diese Nacht gekostet haben
- `boot` am U-Boot-Prompt nach interaktivem init = zweiter Init -> kein Bild (04.10.); `run boot_emmc`.
- build/uboot-build.sh braucht einen ABSOLUTEN O-Pfad (make -C interpretiert O relativ zum U-Boot-Baum).
- `git checkout <sha>` im falschen Verzeichnis (Worktree-Wurzel statt Submodul) haengt den Worktree um (03.10.).
- `git add -A . ':!mainline/build'` schliesst die GETRACKTEN Bauskripte in mainline/build aus.
- Paket-Tests der Agenten haengen an deren tmp/scratch-Pfaden (ST3_SCRATCH-Umgebungsvariable in test_rootfs_features.py).
- pgrep/pkill-Schleifen treffen sich selbst; Warten auf Logzeilen (`until grep -q`), nie auf Prozessnamen.
- Bash-Aufrufe im Werkzeug verlieren das cwd ("Shell cwd was reset"): absolute Pfade.
- Der HY310 verschwindet gelegentlich vom WLAN (00:30-03:00 ohne unser Zutun): vor einem Flash immer frisch pruefen.

## 10. Nachtrag Vollstaendigkeit (Abgleich 04.10. 04:55 gegen doku/61, 134, 141, 142, Memory)
- Fruehere Handoffs: doku/135 (02.10., Stufe A/B), doku/136 (HY300PRO-G-EU Einstieg), doku/137 (HY300 Bildfehler:
  getrennte RGB-Gamma + LVDS 8 Bit = U-Boot 2de0cc8 und h713-tv bf72eb3, beides auf main), doku/138 (MIPS-Reload und
  IR am GEU, hart geparkt), doku/139 (Standby C2 geparkt), doku/140 (Zeitleiste 03./04.10.).
- Fernbedienung: Stock-BLE-Fernbedienung 1d5a:c081, Pairing mit Links+Rechts gedrueckt halten (h713-remote-pair,
  Unit h713-remote-pair.service), Kernel 0169 hid-h713-remote (Report 3 um ein Byte kuerzer; Home/Fokus-Tasten
  gemappt), Koexistenz-Fenster 96/16 in /etc/bluetooth/main.conf. Dieselbe Fernbedienung fuer HY310 und HY300.
- Installation: Release = Abbild-Datei; Weg FEL + ums (sunxi-fel uboot u-boot-installer.bin, dann h713-install
  ueber ums; docs/tools/h713-fel.md, h713-install.md). Keine Abbilder fuer ungetestete Geraete: nur TEST-Images
  (--test-image) fuer profile-only-Boards, "unterstuetzt" heisst gruener Besitzerbericht.
- Issue #1 (fremder HY300 Pro, 636 MHz, boards/hy300-pro): zuletzt hy300-pro-test9 fuer den Melder, test8 bootete
  nicht (PA12/pwm5); wartet auf seine Rueckmeldung; Board von ST3-BOARDMERGE nicht angefasst (README dort sagt noch
  "includes hy200" - Folgearbeit 3.6).
- HDCP-1.4-Warteschleifen-Patch (Kernel: LoadKey-Timeout wird abgewartet, doku/112): BLEIBT, weil 1.4 draussen ist
  (doku/141 0.3). Erst entfernen, wenn 1.4 funktioniert oder endgueltig aufgegeben ist.
- Python 3.9 im Installer: erledigt (INSTALL 0003, tools/check-py39.py).
- eMMC "data error cmd18" (einmal am GEU): nicht verfolgt (Marco 03.10.), erst bei Wiederauftreten.
- Gesamtliste Abschnitt 8 "Spaet" (unveraendert): Wissensdatenbank englisch, Testskripte veroeffentlichen,
  Cedrus/GPU-Matrix, Verwaltungsoberflaeche, Windows-sunxi-fel, ge2d (laut DOKU 0007 "not needed"), tvtop/tvfe/nsi,
  AV1, Presets/Gamma/CTM gegen Stock, Rueckmeldung an cstenger (sein Zweig h713-display-video-path geprueft,
  doku/124), Reserve0/private von einem unberuehrten Geraet, analyse/hdcp-keys nach re/.
- Fahrplan-Memory (plan-nach-q-welle, keystone-plan, werkzeug-umbau-stand, v0-7-beta-stand) sind historisch;
  massgeblich ist jetzt doku/141 + diese Datei.

## 11. Nachtrag Wiedereinstieg 04.10. 10:30 (neue Sitzung, nur gelesen und geprueft, nichts geaendert)
- Korrektur zu Abschnitt 1: der Zweig fable-main-uboot EXISTIERT auch im Submodul von umbau/src, zeigt dort aber auf
  a830902 (alt). Das Worktree-Submodul hat ein eigenes Git-Verzeichnis (.git/worktrees/src3/modules/...) und steht auf
  6fb736c. Vor Stufe 5 also nicht anlegen, sondern nachziehen (fetch aus dem Worktree-Submodul, Zweig auf 6fb736c setzen).
- fable-main = 75a0169, 25 Commits ueber main, sauber; umbau/src main 64f78a2 sauber, 14 vor origin/main. Nichts neuer als 143.
- HY310 10:28 erreichbar: 6.18.38, FIT 2d9b6514, hci0 UP, --failed leer (= main, wie Abschnitt 2). HY300 Pro 192.168.8.246
  NICHT erreichbar (wie schon 01:15), Orange Pi erreichbar, ThinkPad aus. Container h713-build laeuft (25 h).
- Issue #1: keine Rueckmeldung des Melders seit 27.09. (test9: /dev/video1 fehlt, Boot bleibt zufaellig haengen);
  Marco hat dort am 01.10. die Fernentwicklung pausiert -> 3.6 ist nicht eilig.
- Bauverzeichnisse im Worktree (mainline/build/out, uboot-hy310, uboot-hy200-geu, uboot-release, linux-6.18.38-421fd247*)
  sind noch da - vor dem Stufe-4-Bau loeschen (Marcos Befehl). Agenten-Scratch (2,6 GB + 130 MB) ebenfalls noch da.
- 10:40 Marco: "3.6 ist wichtig" (der Melder schweigt, weil er weiss, dass Marco jetzt ein aehnliches Geraet hat);
  Auftrag: Stufe 3 komplett machen. Briefs geschrieben und Agenten gestartet (ohne Rueckfrage, Plan sieht sie vor):
  ST3-RESTORE (Sonnet, umbau/plan/briefs/ST3-RESTORE.md, 3.5 restore-stock fuer alle bekannten eMMC-Groessen) und
  ST3-FOREIGN (Opus, umbau/plan/briefs/ST3-FOREIGN.md, 3.6: hy300-pro auf fable-main-Stand inkl. Diagnose test9 gegen
  Kernel 0168, Frage "gleiche Platine wie HY200 QZ713DF A1?", Issue-Antwort als Entwurf; hy200-qz713-v2 tpr0..2
  entscheiden). Eingabe fuer den Agenten: Issue-Thread als Text unter umbau/work/ST3-FOREIGN/input/.
  Befund vorab: hy300-pro-test9 = Commit 79afae3 = Kernel 0166a (PWM-Woerter als sechs Parameter, OHNE 0168) -> die
  zufaelligen Haenger des Melders sind der GEU-Absturz (doku/136 Punkt 6/7). sun50i-h713-hy300-pro.dts traegt die
  PWM-Woerter <5 1 40000 1 1 100> bereits (Zeile 71), ein 0182 ist dafuer nicht noetig.
- 11:05 3.3 ERLEDIGT: h713-keystone-auto.service bekommt RestartSteps=5 / RestartMaxDelaySec=60 (Exit 3 und 5 werden
  mit wachsendem Abstand 5 s -> 60 s wiederholt, nie aufgegeben; Exit 7 bleibt der Skip). Test, services.md,
  h713-keystone.md angepasst; Keystone-Suite 176/176; Commit da862d9 auf fable-main (jetzt 26 Commits ueber main).
  ST3-FEATURES Frage 4 damit beantwortet, Patch 0009 ueberholt.
- 11:05 Submodul-Zweig nachgezogen: in umbau/src/mainline/external/u-boot zeigt fable-main-uboot jetzt auf 6fb736c
  (Fast-Forward von a830902 per fetch aus dem Worktree-Submodul; HEAD dort weiter losgeloest 2de0cc8). Punkt
  "vor Stufe 5 abgleichen" aus Abschnitt 1 ist erledigt.
- 3.4 HY300-Lampe: OFFEN, braucht das Geraet - HY300 Pro ist seit 01:15 nicht erreichbar (10:28 und 11:05 geprueft).
  Offline-Vorarbeit laut doku/136 Abschnitt 5 (Stock-Kette 0x34: Vendor-Module aus vendor_a, PanelControl::
  switchToMipsPWM, bl_power 4->0) ist RE-Arbeit an Marcos eigenem Dump; erst nach Ansage.
- 11:15 STUFE 3 OFFLINE KOMPLETT (3.1, 3.2, 3.3, 3.5, 3.6); 3.4 braucht das Geraet. fable-main = dd726eb, 30 Commits
  ueber main, sauber, Identitaetspruefung 0 Treffer. Beide Agenten fertig und von mir nachgeprueft (Patches in
  frischem git-archive-Export angewendet, Suiten selbst gelaufen, DTB-Beweis mit eigenem cpp+dtc reproduziert,
  Motor-Tabellen gegen A14/material/owner-stock.dts und sein Stock-dmesg gelesen, U-Boot-Defconfig-Luecke des V2
  im Fork selbst gesehen):
  * ST3-FOREIGN (Opus, REPORT 281 Zeilen, 4 Patches) -> Commits 5588787 (Kernel 0182: Motor-Tabellen des Melders
    aus seinem Stock-Baum; DTB-Diff nur cw/ccw-Tabelle und die zwei Delays), 9c81acc (boards/hy300-pro: test9-
    Diagnose = 0168-Absturz UND zweiter Fehler: beide test9-Boots liefen Projekt 0x30 statt 0x34, Env-Default;
    test10-Inhalt; eigenes Board, nicht die A1-Platine: Tacho PH17 vs PH13, tpr11/12 = T08/HY350-Werte),
    5c8da0f (hy200-qz713-v2: tpr0..2 bleiben cstengers = LPDDR3-Timing bei 720 MHz, Image-Woerter sind die
    DDR3-792-Vorlage; ROT: TEST-Image fuer V2 waere heute nicht lauffaehig - Bring-up-Defconfig ohne Layout v4,
    Baum = nackter dtsi - README/Tabelle sagen "not testable yet"). Issue-Antwort als ENTWURF:
    umbau/work/ST3-FOREIGN/drafts/issue1-reply.md (nichts gepostet; Marcos Wort). Owner-Test fuer test10 in
    REPORT Abschnitt 6. Offen: warum test9-Install h713_project auf 0x30 liess (Install-Ausgabe nicht gepostet).
  * ST3-RESTORE (Sonnet, REPORT 150 Zeilen, 2 Patches) -> Commit dd726eb: restore-stock nimmt beide bekannten
    Groessen; Profilgroesse bindet nur, wenn von einer Einheit gelesen (letzte Tabellenzeile hat eine Groesse:
    hy300_pro, GEU-Variante), Image-Groesse = Warnung; neuer Fit-Check (beyond_the_disk, Exit 2); UDISK-Ende der
    Container-Tabelle keine Differenz mehr. Installer-Suite 361 -> 372 (53 skipped), py39 0, check.sh gruen.
    Offene Fragen an Marco: Heuristik statt Schema-Feld ok? HY310-Firmware auf 15273600-Chip = Warnung statt
    Verweigerung ok? Container wird nie gegen das erkannte Board geprueft (F2).
  * Scratch zum Loeschen (Marco): /tmp/claude-1000/-opt-Projekte-h713/st3-foreign (~1 GB), st3-restore.
  * Geraetetests der Stufe 3 (in doku/142 4b nachgetragen): GEU restore-stock --no-write (0 Zyklen), Features-Pfade,
    Variante; HY310: nichts darf sich aendern (4a Schritt 5).
- 3.4 HY300-Lampe, Testplan ohne UART (Marco kann den HY300 Pro ans Netz bringen): (1) Marco: Wandfoto wie sein
  Stock-Referenzfoto (gleicher Abstand, ISO 1000, 1/25) mit dem laufenden TEST-Image; (2) ich per ssh, nur lesend:
  dmesg "backlight PWM"/"init sequence", PWM-Block 0x02000c00 per devmem, /sys/class/backlight, Pinmux der
  Kandidatenpads. Gleich hell wie Stock -> 3.4 geschlossen (die "schwache" Bildwirkung war LVDS 6 Bit, doku/137).
  Dunkler -> die Firmware treibt PWM5 nach SetBacklightLevel 0x64 nicht; dann RE des Stock-Handovers (vendor_a-
  Modul, PanelControl::switchToMipsPWM) offline, erst nach Marcos Go.
- 11:35 Marcos Entscheidungen: hy300-pro-ab GELOESCHT (Inhalt = Fork fda5ce0, in fable-main-uboot enthalten);
  known-issues HDCP-1.4-Zeile: Messung bleibt, aber offen statt geschlossen (Marco erinnert einen 1.4-Test; zwei
  Entscheidungstests), Fuse-Lesung am HY300 Pro nach dem Grosstest (Marco einverstanden); ST3-RESTORE Fragen 1-3
  wie empfohlen: Heuristik jetzt + Schema-Feld nach dem Release (F1), HY310-Firmware auf 15273600-Chip = Warnung,
  Container-gegen-Board-Pruefung nach dem Release (F2) - "alles gewissenhaft". Audio im Grosstest gekuerzt (142 Schritt
  10). Release-Bau: OHNE --wifi-env (Datei wuerde fest ins Abbild), wifi.env des HY310 nach der Installation per ums
  zurueckkopieren (scp als Datei, nie lesen). Aufgeraeumt: ST3-BOARDMERGE/tmp, Scratch, Bauverzeichnisse;
  FB-HDCP14d/build BEHALTEN (Test-Proper + Kontroll-BL31 fuer die HY300-Lesung). Submodule TF-A dfa9fab und
  sunxi-tools 269dfa2 im Worktree nachgezogen (waren nicht ausgecheckt - erster Bauversuch brach in Schritt 1 ab).
  build-all nimmt nur vX.Y oder vX.Y-beta als --version: der Bau heisst v0.96-beta, kein -rc1.
- 11:50 Marco: vor dem Release prueft ein grosser Agent alle 45 ungepushten Commit-Nachrichten und ALLE 308 getrackten
  .md-Dateien mehrfach auf noetige Aktualisierungen -> Paket ST5-DOCAUDIT (Opus, Brief umbau/plan/briefs/ST5-DOCAUDIT.md,
  Ausgabe umbau/work/ST5-DOCAUDIT/: Dateitabelle, Patches fuer RELEASES/STATUS/ROADMAP/README/FLASHING/BUILDING/docs,
  Link-Checker, Nicht-ASCII-Zensus, drei protokollierte Durchgaenge). Laeuft parallel zum Release-Bau (gestartet 11:40
  aus d1cd828, Log umbau/build/logs/build-all-v0.96-beta.log). Nachpruefung und Integration durch mich, dann ist der
  Bau VERALTET (Docs im Abbild) -> vor Stufe 4 noch einmal von vorn bauen oder die Doc-Commits vor den Bau legen.
- 11:51 RELEASE-BAU 1 FERTIG (23 min 54 s, exit 0, Log umbau/build/logs/build-all-v0.96-beta.log): installer/out/
  h713-hy310-v0.96-beta-{a-bootkette 6 MiB, b-system 1153 MiB, c-gptkopie}.img + tabelle.json (disk 15269888) +
  BUILD.txt + README.txt + sha256. BUILD.txt: repo d1cd828 (0 local changes), Serie 206 Patches (0182 drin: hy300-pro.dts
  im Baum traegt die Motor-Tabellen), Kernel 415ddd8c, U-Boot 6fb736c, TF-A dfa9fab (45164 B = sauberer Stand), sunxi-tools
  269dfa2, reproducible: yes, SOURCE_DATE_EPOCH 1791106023; Selbsttest mit Vendor-Dateien ALL GREEN. Bausteine:
  spl 93e0cdc4, proper ab028136, env c3571430, installer-U-Boot 44ec8798, FIT 1ceacd9f, h713-tv 19f7efb9, rootfs 2ebdc1aa.
  Abbilder sha256: a 1aa349f8, b 3f2e12a1, c e085b681. Rootfs haengt am Spiegelstand (dpkg status 1cf7c226).
- 11:55 E1 DOPPELBAU gestartet: frischer Klon umbau/build/clone-v0.96-beta (fable-main d1cd828, Submodule aus dem Worktree
  referenziert), gleicher Befehl, Log build-all-v0.96-beta-E1.log. Danach cmp der drei Abbilder und der Bausteine.
  ACHTUNG: beide Bauten sind VERALTET, sobald ST5-DOCAUDIT Doku-Commits bringt (Docs liegen im Abbild) - dann Bau 3 + E1
  erneut; Reihenfolge fuer Stufe 4: erst Doc-Commits, dann Bau, dann Geraet.
- 12:10 ST5-DOCAUDIT (Opus, REPORT 317 Zeilen, 19 Patches, 37 Dateien, 308 .md geprueft: 38 veraltet, 41 aktuell, 22
  Entwuerfe, 207 nicht unsere = 181 doku-Kopien + 26 cstenger-Seiten) von mir nachgeprueft (alle 19 in frischem Export
  angewendet, tools/check-links.py gruen, Identitaet 0, known-issues ASCII, Zahlen gegen 134/140/143 gelesen: +18 Patches
  = 188 -> 206, 0.07 dB, 97/97, A4) und als 3 Commits integriert (Release-Seiten; docs/boards/kernel-README; userspace-
  READMEs). fable-main = 34 Commits. ZWEI STAGE4-Marker (`git grep -n STAGE4`: RELEASES.md "Measured", STATUS.md Zeile 9)
  werden nach dem Grosstest gefuellt und geloescht. Fragen an Marco: (1) Wortlaut "nothing acts on the remote's keys yet
  except Power" auf der Release-Seite ok, oder erst Tastenbelegung (Lautstaerke)? (2) Fork-Push nach h713-hy310 (Fast-
  Forward auf 6fb736c) - ja? (3) doku-Kopie im Repo: 8 saubere Dateien syncen, 00-STATUS/71/75/61-todo erst nach Scrub
  (Geraeteadressen, Namen) oder 61-todo aus der Kopie werfen? (5) STATUS-Historienabschnitte nach dem Release kuerzen?
  Code-Befunde (Abschnitt 5 des REPORT, nach dem Release): h713-tv help/status sagt "kernel 0169" und beschreibt zoom out;
  identify.py druckt "v3"; --test-image-Hilfe ohne /variant; uboot-h713/ Spiegel steht auf da74b89 statt 6fb736c
  (vor dem Push regenerieren!); README.txt des Abbilds traegt Wanduhrzeit.
  Folge: Bau 1 (d1cd828) ist VERALTET (drei READMEs im Abbild) -> Bau 3 + E1 aus dem neuen HEAD nach Ende des laufenden E1.
- 12:18 E1 (Klon, d1cd828) FERTIG, 25 min, ALL GREEN, reproducible yes. VERGLEICH gegen Bau 1: a-bootkette und
  c-gptkopie BYTEIDENTISCH, tabelle.json bis auf Zeitstempel/b-Hash gleich, b-system VERSCHIEDEN. Ursache gefunden:
  h713-tv, h713-afmetric, h713-warp werden mit -g cross-gebaut und tragen den absoluten Pfad des Baums und des Sysroots
  in der DWARF-Info (je 3 Pfad-Strings), damit auch der rootfs-Tar anders. Fix Commit (fable-main 37): -ffile-prefix-map
  fuer Verzeichnis, Sysroot, Mesa in den drei Makefiles; Beweis: h713-tv aus zwei verschieden benannten Verzeichnissen
  = ein sha256 (5d55aa5d), 0 Pfad-Strings; afmetric/warp 0 Pfad-Strings. Klon fuer E1 muss die Submodul-URLs lokal
  bekommen (`git -c protocol.file.allow=always submodule update` nach `git config submodule.<pfad>.url <lokal>`).
  Naechster Schritt: Bau 3 (Worktree, von vorn) + E1' (frischer Klon) aus dem neuen HEAD, dann cmp aller drei Abbilder.
- 13:15 BAU 3 (Worktree, 12:24-12:49) und E1b (frischer Klon, 12:49-13:14) aus 6602c9f: beide ALL GREEN, reproducible
  yes. VERGLEICH: a-bootkette und c-gptkopie BYTEIDENTISCH; BUILD.txt bis auf die Wanduhr-Zeile IDENTISCH - also ALLE
  Bausteine gleich, auch h713-tv (Fix wirkt) und hy310-rootfs.tar; b-system noch VERSCHIEDEN: 84025 Bytes in 87
  MiB-Bloecken, erste Abweichung bei 0x100430 = ext4-Superblock der hy310-boot-Partition (+0x30 wtime, +0x40 lastcheck,
  +0x68 UUID) -> die ext4-Container (hy310-boot, hy310-rootfs-platz) tragen Zufalls-UUID und Wanduhr-Zeiten des mke2fs/
  Kopierens, der Inhalt ist gleich. Entscheidung mit Marco: mke2fs mit fester UUID/hash_seed und E2FSPROGS_FAKE_TIME =
  SOURCE_DATE_EPOCH (dann Bau 4 + E1) oder fuer v0.96-beta dokumentieren "Bausteine bitgleich, Container-Metadaten nicht".
- 13:25 ext4-Ursache geprueft (mke2fs 1.47.0 im Container, Tests /tmp/e2repro*): mit E2FSPROGS_FAKE_TIME + -U + hash_seed
  werden Superblock-Zeiten/UUID/Seed gleich, es bleiben die Inode-ctime/crtime aus dem tar-Entpacken (18 Bytes bei 3
  Inodes; mke2fs -d kopiert st_ctime, SOURCE_DATE_EPOCH wird erst ab e2fsprogs 1.47.1 beachtet). Vollstaendiger Fix =
  mkimage-inputs.sh: FAKE_TIME + abgeleitete UUID/Seed aus SOURCE_DATE_EPOCH + debugfs-Nachlauf (set_inode_field ctime/
  crtime/atime/mtime aller Inodes auf SOURCE_DATE_EPOCH). Aufwand ~20 min + Bau 4 + E1 (50 min). Bausteine sind bereits
  bitgleich bewiesen; RELEASES sagt "image files differ between builds". Entscheidung Marco: jetzt (b-system bitgleich)
  oder Folgearbeit nach v0.96-beta und Grosstest mit Bau 3 (6602c9f).
- 15:5x STUFE 5 VORBEREITET, NICHT GEPUSHT (Marco: "1, 2, 3 aber nicht pushen"):
  * STAGE4-Platzhalter gefuellt, open tests/known-issues GEU-BT aktualisiert (b110ec1); MAC des HY310 aus
    analyse/boot/wlan-aic8800-messung-20260912.txt entfernt (a8c4bfa; seit 13.09. in der GitHub-History, bleibt dort).
  * Seit dem Abbild-Commit 6602c9f nur Installer (h713-install, h713/install.py, Tests), Doku und analyse/ - das Abbild
    traegt und nutzt keine davon (geprueft: build-all/mkimage/install-projekt importieren install.py nicht).
  * umbau/src main per Fast-Forward = a8c4bfa (42 Commits vor origin/main, 13 neue Kernel-Patches 0170-0182, keine RAUS-
    Pakete im Diff). Fork-Submodul in umbau/src: lokaler Zweig h713-hy310 per Fast-Forward auf 6fb736c, ausgecheckt
    (5 Commits vor origin/h713-hy310). Kein Tag gesetzt.
  * Identitaet im frischen Klon (main + Fork): 0 Treffer in Dateien und Commit-Metadaten, alle Autoren well0nez
    (noreply); MAC-artige Strings im Diff nur Testadressen (AA:BB:CC:DD:EE:0x, 11:22:33:..).
  * Upload-Ordner umbau/build/upload-v0.96-beta (68 MiB): a/b/c .img.zst, tabelle.json, sha256, README.txt, BUILD.txt,
    u-boot-installer.bin, u-boot-h713-probe.bin, sunxi-fel; frisch entpackt -> sha256sum -c OK. Release-Text
    umbau/build/release-notes-v0.96-beta.md (92 Zeilen, ASCII, absolute Links).
  * 16:2x Doku nach dem Audit nachgezogen (e77130f: reproduzierbar von jedem Pfad, Board-Datei bei Neuinstallation, Einstellungen und Kopplung gehen bei Neuinstallation verloren); main = e77130f. Tag dann auf e77130f.
  * PUSH-REIHENFOLGE (nur auf Marcos Wort): 1. Fork: `git -C umbau/src/mainline/external/u-boot push origin h713-hy310`;
    2. `git -C umbau/src push origin main`; 3. Tag v0.96-beta auf main 5ab6ec1, `git push origin v0.96-beta`;
    4. `gh release create v0.96-beta --prerelease --title v0.96-beta --notes-file umbau/build/release-notes-v0.96-beta.md
    umbau/build/upload-v0.96-beta/*`; 5. Release-Seite aus Fremdensicht lesen; 6. Issue-1-Antwort (Entwurf ST3-FOREIGN).
- 16:5x HDCP-1.4-FUSE-LESUNG AM HY300PRO-G-EU (Marco: "kannst du jetzt machen"), 2 warme Reboots, 0 Stromzyklen, UART
  mitgeschnitten (umbau/work/FB-HDCP14d/geu/). Aufbau: GEU-Proper exakt wie das Release gebaut (Konfiguration identisch,
  Gegenbau mit Release-BL31 = Release-Proper 3243687c bitgleich), nur mit dem 14d-Kontroll-BL31 (bfdb5fb5) -> 8104eda3;
  h713-ce.ko out-of-tree gegen den Release-Baum gebaut (= 3b0e9322, bitgleich zum HY310-Modul). Backup LBA 2048..3911
  (40c534b3, auch auf dem Host), guarded Flash-Skript geu-flash-proper.sh, Reboot, UART "BL31 Built 20:25:43 Oct 2" =
  Mess-BL31, insmod el3=1, SiP 1.0. ERGEBNIS: prctl-burned=0x200000 -> rssk=not-burned ssk=not-burned HDCPPKF=BURNED;
  shadow-0x240=0x00200000 (HY310: 0), Kontrolle prctl-0x248=0x00400000 = Schatten (wie HY310). Rueckbau: Release-Proper
  und dann die ganze gesicherte Flaeche zurueck (40c534b3 rueckgelesen), Reboot, UART "BL31 Built 10:23:24 Oct 4" =
  Release, Proper 3243687c, --failed 0, Bild an, h713_ce entladen.
  DEUTUNG: Die Lesung unterscheidet Geraete - Bit 21 ist am HY300 gesetzt, am HY310 nicht; damit traegt die Bit-Deutung
  (16 RSSK, 17 SSK, 21 HDCP-PKF aus dem Stock-BL31). RSSK ist auf BEIDEN Geraeten nicht gebrannt -> der Weg ueber den
  RSSK-verschluesselten hdcpkey-Blob kann auf keinem der beiden der Stock-Weg sein. Der HY300 hat stattdessen das
  HDCP-PKF-Flag: Kandidat fuer einen anderen Stock-Weg (Schluessel/Flag direkt in den eFuses). Marcos Erinnerung an
  einen funktionierenden 1.4-Test und diese Lesung widersprechen sich am HY310 weiter -> naechster Test: Stock mit
  einer 1.4-Quelle, und den Stock-Code lesen, der Bit 21 (HDCP-PKF) auswertet.
- 17:1x HDCP 1.4 HY300 weiter (Marco: "nur auf dem HY300, herausfinden wie er es macht"):
  * RSSK-Probe am HY300 (Mess-Proper, 2 warme Reboots, Rueckbau verifiziert 40c534b3 / BL31 10:23:24): KAT auf CE_S ok,
    key-select 3 verweigert ESR 0x11, BL31 "RSSK probe on CE_S not passed (0x111)" - wie HY310. Passt zu RSSK nicht gebrannt.
  * Fehler von mir: `h713-hdcp-key --help` startete den echten Lauf (kennt kein --help), stoppte h713-tv, scheiterte am
    modprobe -r; nichts geschrieben, der folgende Reboot hat es bereinigt. Merke: unbekannte Werkzeuge erst im Quelltext lesen.
  * Flag 0x06840093 (byteweise gelesen) = 0x41, Bit 0 = 1 ("HDCP1.4 key has been loaded" laut display.bin) - aber der
    ThinkPad liest ueber DDC (i2c-1, 0x74): Bksv = 0 (keine Einsen), Bcaps 0, Ri' 0; Content Protection bleibt Desired.
    Das Flag sagt also nichts; der 1.4-Schluesselspeicher des Empfaengers ist leer (wie B1 am HY310: "Bksv is invalid").
  * Spur aus doku/72: der Schluesselspeicher wird bei Stock vom BOOTLOADER gefuellt ("down hdcp 1.4",
    sunxi_smc_refresh_hdcp, sunxi_tvtop_complete), nicht vom MIPS und nicht von Linux. Mit HDCP-PKF gebrannt (nur HY300)
    ist der Kandidat: der Monitor (Stock-BL31) fuellt den Speicher aus der eFuse. -> RE-Paket FB-HDCP14e (Opus).
- 17:3x Marco: die Arbeit ist legitim (eigenes Geraet, Initialisierung nachstellen, keine Schluesseldaten) -> Paket
  FB-HDCP14e (Opus) gestartet, Brief umbau/plan/briefs/FB-HDCP14e.md: (1) die SID-Flag-Bits 0x03006240 im eigenen
  Stock-Bootpfad der Platine (firmware/hy200-qz713df-a1/2025-09-22 update.img: u-boot, monitor, optee) Bit fuer Bit
  gegen die 14c-Deutung pruefen; (2) der Initialisierungsschritt, den Stock (boot0/monitor/TEE) tut und unsere Kette
  nicht, damit key-select 3 angenommen wird; (3) was das fuer den HY300 (HDCP-PKF ja, RSSK nein) heisst; (4) ein
  lesender Geraeteplan. Ausdruecklich KEIN Schluesselmaterial, geschlossene Ordner bleiben zu, kein Geraet.
  Ausgabe umbau/work/FB-HDCP14e/. Der stock Ablauf selbst steht schon in doku/112 Abschnitt 2.
- 17:4x Marco: FB-HDCP14e darf den HY300 live nutzen (auslesen, U-Boot abfangen, Logs). Dem Agenten weitergegeben mit
  Grenzen: ssh mit Test-known_hosts, UART nc 192.168.8.180 2000 mit timeout, nur lesen (dmesg/sysfs/mmap-Reads),
  hoechstens 3 warme Reboots mit Begruendung, am U-Boot-Prompt nur lesende Befehle und Ausstieg per `run boot_emmc`
  (nie `boot`), KEIN eMMC-Schreiben/fw_setenv/saveenv, keine Schreibzugriffe auf SID/CE/Senke/SPC, kein Stromzyklus,
  kein h713-hdcp-key, kein Gate. Parallel test10-Bau (hy300-pro, v0.96-beta, aus e77130f).
- 16:17 test10 FERTIG (hy300-pro, aus e77130f, 25 min, reproducible yes, TEST IMAGE test_for=hy300_pro, disk 15269888;
  ohne --vendor = Strukturpruefung). Geprueft im Baum: hy300-pro.dts mit 0182-Motor-Tabellen und PWM-Woertern, hdmirx
  mit 0168 (Woerter per Adresse), U-Boot hy300_pro 636 MHz aus 6fb736c (enthaelt 2de0cc8 LVDS 8 Bit fuer 0x34).
  Upload-Ordner umbau/build/upload-hy300-pro-test10 (68 MiB, a/b/c .zst, Tabelle, sha256, README, BUILD, Installer-
  U-Boot, Probe, sunxi-fel), Kopie der Rohdateien umbau/build/release-hy300-pro-test10. Release-Text
  umbau/build/release-notes-hy300-pro-test10.md (test9-Text + Abschnitt test10), Issue-Antwort-Entwurf auf test10
  umgestellt (umbau/work/ST3-FOREIGN/drafts/issue1-reply.md). Push-Reihenfolge ergaenzt: nach v0.96-beta Tag
  hy300-pro-test10 auf 5ab6ec1, `gh release create hy300-pro-test10 --prerelease --notes-file ... upload-hy300-pro-test10/*`,
  dann Issue-Antwort - alles nur auf Marcos Wort.
- 17:5x FB-HDCP14e FERTIG (Opus, REPORT 175 Zeilen; Geraet nur gelesen, 0 Reboots). Von mir geprueft: monitor.bin und
  optee.bin der HY300-Platine und des HY310 sind sha256-gleich (95596d11 / 9b3addd5, facts.json); efuse_tables.py liest
  die Namenstabelle direkt aus dem BL31: rotpk Bit 15, ssk 16, rssk 17, hdcppkf 21 - die 14c-Deutung haelt. ERGEBNIS:
  Bit 21 (hdcppkf) ist der HDCP-2.2-Flag, nicht 1.4; fuer 1.4 zaehlt Bit 17 (RSSK), und das ist auf BEIDEN Geraeten 0.
  Kein Software-Schritt in boot0/BL31/OP-TEE/U-Boot aktiviert key-select 3 - der RSSK kommt per Hardware aus der eFuse.
  Es fehlt also kein Init, es fehlt der Schluessel an der Engine. Einziger entscheidender Test: eine 1.4-Sitzung unter
  Stock (ThinkPad liest Bksv). known-issues ergaenzt (5ab6ec1), main = 5ab6ec1 (lokal). Tag-Ziel damit 5ab6ec1.
- 16:4x HY300 ZURUECK AUF STOCK (Marco: "flashe das Backup von Android"): Vollabzug re/device-dumps/hy300pro-plus-marco/
  emmc-full.img (sha256 af2deb6a OK, 7820083200 B = 15273600 Sektoren) per h713-fel --yes + `h713-install restore`
  (vorher Pflicht-Kleinabzug nach hy300pro-sicherung-20261004-v096/dump-before-restore), 14 min, exit 0. Stichproben
  Geraet gegen Abzug an LBA 0, 16, 2048, 24576, 73728, 599040, 4858880, 4932608, 15273567: gleich; Secure Storage
  gleich dem Abzug vom 02.10. Zweck: HDCP-1.4-Sitzung unter Stock (ThinkPad liest Bksv ueber DDC). Rueckweg danach:
  TEST-Abbild umbau/build/release-v0.96-beta-geu-TEST mit --test-image (Erstinstallation ueber Stock, also mit Pflichtabzug).
- 17:0x HDCP 1.4 UNTER STOCK: FUNKTIONIERT - MARCO HATTE RECHT. HY300 auf Android (sein Abzug vom 02.10.), ThinkPad am
  HDMI, i915: `xrandr --output HDMI-2 --set "Content Protection" Desired` -> innerhalb 3 s "Enabled", zweimal
  wiederholt (aus/an), keine HDCP-Fehlzeile im i915-Log (nur das fehlende SRM-Revokationsfile, harmlos). i915 meldet
  "Enabled" erst NACH bestandener 1.4-Authentifizierung: es liest Bksv, prueft die 20 Einsen, schreibt An/Aksv, liest
  R0' und vergleicht - der Empfaenger hat unter Stock also einen gueltigen Schluessel. (Meine eigenen rohen DDC-Lesungen
  ueber i2c-1 schwanken, sie kollidieren mit dem i915-Verkehr auf derselben Leitung - nicht verwertbar, nur der
  Kernel-Befund zaehlt. Unter UNSERER Firmware blieb dieselbe Anforderung auf "Desired" und Bksv war stabil 0.)
  FOLGE: Der administrative Fuse-Flag Bit 17 (rssk) = 0 heisst NICHT, dass die RSSK-Zellen leer sind - genau die offene
  Frage aus FB-HDCP14e. Die Zellen bei einer nicht abgedruckten Stelle im SID sind offenbar programmiert, nur das Flag nicht gesetzt.
  Damit ist HDCP 1.4 auf diesem Geraet NICHT hardwareseitig zu, und die Frage lautet jetzt: warum nimmt die Crypto
  Engine key-select 3 unter unserer Bootkette nicht an, obwohl der Schluessel da ist? Kandidaten: der SID-Sense/Latch
  im BROM/boot0-Fenster, das unsere SPL belegt, oder ein Zustand, den Stock vor dem ersten CE-Task herstellt.
  known-issues und 144 sind entsprechend zu korrigieren (die Zeile sagt bisher "nicht gebrannt, gemessen").
- 17:3x ROOT AUF DEM HY300 UNTER STOCK und die erste harte Spur zu HDCP 1.4.
  Weg: mein erster Versuch (ro.debuggable im boot-Ramdisk) war FALSCH - das Ramdisk aus boot.img ist nur die erste
  Init-Phase, die echten Eigenschaften liegen in /system/etc/prop.default im verity-gepruften super. Marcos Anleitung
  (magcubic-root) hatte recht. Dann offizielles Magisk v30.7 von GitHub geladen (nur lokal, nichts hochgeladen),
  armeabi-v7a-Binaries + assets/boot_patch.sh per adb aufs Geraet, dort gepatcht (so macht es die Magisk-App auch),
  new-boot.img zurueckgeholt, geprueft (Kernel bitgleich, Magisk im Ramdisk, Original-Init gesichert) und per FEL+ums
  nach boot_a geschrieben, rueckgelesen identisch. vbmeta_a Flags = 2 (Pruefung aus). Android bootet, magiskd laeuft,
  `/debug_ramdisk/su` gibt nach Marcos Freigabe uid=0. FEL-Einstieg unter Android: `adb reboot efex` (kein Tastendruck).
  MESSUNGEN (umbau/work/FB-HDCP14e/stock-live/): SID-Flagwort unter Stock = 0x00200000, exakt wie unsere EL3-Lesung -
  die eFuse-Lage ist NICHT der Unterschied, und das rssk-Flag ist 0, obwohl Stock 1.4 authentifiziert.
  DIE SPUR: SPC (Secure Port Controller) unter Stock ist differenziert (Port 0 0xffffffff, Ports 1/2/5 komplett
  SICHER, 3/4/6 gemischt). Unsere TF-A schreibt in sunxi_security_setup() 0xffffffff in ALLE 14 Ports ("set all
  devices to non-secure"), dazu CCU 0x7, R_PRCM 0x1, alle DMA-Kanaele. Liegt die Crypto Engine in einem der Ports,
  die Stock sicher laesst, dann liefert der SID-Key-Bus den RSSK nicht an einen nicht-sicheren Master - genau das
  Symptom (key-select 3 verweigert aus Linux UND aus EL3, KAT mit key-select 0 besteht). TEST: in unserem BL31 den
  CE-Port sicher lassen, BL31 neu bauen, RSSK-Probe wiederholen.
- 18:0x HDCP 1.4, DER EIGENTLICHE BEFUND (Belege umbau/work/FB-HDCP14e/stock-live/): Stock laedt auf DIESER
  Firmware gar keinen 1.4-Schluessel. Der Bootloader tut es nicht (kein "down hdcp 1.4" im UART-Log, nur
  "secure os exist" und zwei Fehlschlaege fuer widevine/ec_key), und Android liest fuer 1.4 genau EINE Sache:
  `hdcpkeyV14_hash`, 6 Bytes (= eine KSV, kein Schluessel). Fuer 2.2 liest derselbe HAL die 912 Byte und uebergibt
  sie per RPC - wie unser h713-hdcp-key. => Der gesamte RSSK/key-select-3-Weg, an dem FB-HDCP14/14b/14c/14d
  gearbeitet haben, ist NICHT der Mechanismus. Darum ist das eFuse-Flag 0 und 1.4 geht trotzdem. Der Schluessel
  liegt schon im Schluesselspeicher des Empfaengers; die Software liest nur seine Kennung.
  Dazu: Byte 0x06840093 ("key has been loaded") ist 0x41 bei Stock UND unter unserer Firmware (HY310). Die Bank
  ist byteweise - ein 32-Bit-Read liefert das erste Byte vervielfacht (daher die fruehere 0x81818181-Lesung).
  OFFEN und naechster Schritt: mit unserer Firmware und Quelle am HDMI die Authentifizierung anfordern und dabei
  die Bank 0x06840000 beobachten, gegen denselben Lauf unter Stock. Dafuer muss das HDMI-Kabel an den HY310.
- 18:2x HDCP 1.4 - DIE LUECKE GEFUNDEN. Am HY310 mit Quelle unter UNSERER Firmware: Empfaengerregister
  0x06840090.. = 81 00 10 41 06 33 00 00 3b e4, byteweise identisch mit Stock. Trotzdem Bksv 0, Bcaps 0, keine
  Authentifizierung. Grund: der Hersteller hat fuer den 1.4-Schluessel einen EIGENEN Aufruf, den wir nie machen -
  tvserver `THal_Vp_HDMI_ReloadHdcp14Key` -> Firmware-Handler `OnHalHdmiRELOADHDCP14KEY` -> `HDMIRX_Hdcp14_ReloadKey`
  -> `HdmiRx_HDCP14_LoadKey` (die Routine aus doku/72). Unsere hdmirx-Init-Sequenz hat genau einen HDCP-Schritt,
  `THal_Vp_SetHDCP22Key`; `ReloadHdcp14Key` kommt im ganzen Baum nicht vor. Zweite Huerde: genau diese LoadKey-
  Routine ist die, deren Warteschleife unser U-Boot auf Null patcht ("HDCP key-load wait defeated") - der Ladevorgang
  wuerde also sofort in den Timeout laufen. UMSETZUNG (klein, kein neuer Mechanismus): (1) Schritt
  "THal_Vp_HDMI_ReloadHdcp14Key" in die Init-Sequenz (der Treiber hasht den Namen zur Laufzeit, es fehlen nur Name
  und Argumentzahl - die steht an der Aufrufstelle in vendor_a_tvserver), (2) den Warteschleifen-Patch bedingt
  machen oder entfernen (doku/112 sagt ohnehin, er muss weg sobald 1.4 geht), (3) Quelle fragen und Bksv lesen.
  Belege: umbau/work/FB-HDCP14e/stock-live/README.txt.
- 18:3x HDCP 1.4: Aufruf eingebaut und probiert - noch nicht genug. "THal_Vp_HDMI_ReloadHdcp14Key" (0 Argumente) in
  die hdmirx-Sequenz, Modul gebaut, installiert, Reboot: 24 statt 23 Aufrufe, die Firmware nimmt ihn an. Dazu die
  Warteschleife zur Laufzeit auf den Hersteller-Wert zurueckgeschrieben (0x4b13d0a4 = 0x2c630033 per /dev/mem,
  durch jeden Reboot wieder weg) und die Sequenz per Modul-Reload wiederholt: diesmal OHNE Timeout-Zeile. Trotzdem
  bleibt die Verbindung ungeschuetzt, Bksv und Bcaps 0. Aufruf und Warteschleife sind also noetig, aber nicht
  hinreichend. ENTSCHEIDENDE NAECHSTE MESSUNG: Quelle an den HY300 unter Stock, Schutz anfordern, logcat lesen -
  der tvserver druckt jeden RPC ("RPC call -- <name>()"), das nennt die genaue Folge. Braucht das HDMI-Kabel am
  HY310 abgezogen und am HY300 gesteckt, fuenf Minuten. Treiber-Diff gesichert als
  umbau/work/FB-HDCP14e/0183-hdmirx-reload-hdcp14-key.diff, NICHT committet, NICHT im Release; HY310 wieder auf
  dem Release-Modul (3ae43c3a) und neu gestartet, --failed 0, Signal da.
- 18:5x HDCP 1.4 - DIE ENTSCHEIDENDE MESSUNG: Am HY300 unter Stock, Eingang aktiv, Log geleert, Schutz angefordert ->
  "Enabled" in Sekunden, und im ganzen Fenster KEIN EINZIGER HDCP-Aufruf im Log (der tvserver druckt jeden RPC und
  war durchgehend aktiv). Die Authentifizierung laeuft also komplett zwischen Empfaenger und Display-Firmware,
  ohne Software. Damit ist klar: `THal_Vp_HDMI_ReloadHdcp14Key` gehoert nicht in den Handshake, und unser neuer
  Aufruf kann allein nichts bewirken (gemessen, siehe 18:3x).
  WAS BLEIBT, UND ES IST UNSERES: Die Firmware laedt den Schluessel beim MIPS-Start selbst (HdmiRx_HDCP14_LoadKey
  schreibt 0xc0 nach 0x06840093 und pollt Bit 0 fuer 0x33 Ticks). Unter UNSEREM Boot laeuft genau das dreimal in den
  Timeout, weil unser U-Boot die Schleifengrenze auf 0 patcht ("HDCP key-load wait defeated", h713_mips.c, doku/72).
  Unter Stock nicht. Danach wiederholt es niemand, und keine Software kann es spaeter heilen - genau das Bild, das
  wir sehen. NAECHSTER SCHRITT LIEGT IM U-BOOT: den Patch weglassen und klaeren, warum bei uns die Ticks beim
  MIPS-Start stehen (Takt/Gate/Reihenfolge vor dem Release des MIPS), oder die Firmware so starten wie Stock.
  doku/112 sagt ohnehin, der Patch muss weg, sobald 1.4 geht. Belege: umbau/work/FB-HDCP14e/stock-live/README.txt.

## 12. Stand beim Sitzungsende 04.10. 19:0x - was eine neue Sitzung zuerst wissen muss
- EINSTIEG: diese Datei ganz, dann doku/144 (alle offenen Punkte), doku/142 (Grosstest, durchgefuehrt), doku/141.
- CODE: Zweig fable-main = main (lokal) = 6b40a4b, sauber, 58 Commits vor origin/main; U-Boot-Fork h713-hy310
  lokal auf 6fb736c, 5 vor origin. NICHTS GEPUSHT, kein Tag. Push-Reihenfolge steht in Abschnitt 11 (17:5x-Eintrag
  und darueber); Tag-Ziel ist der dann aktuelle main-Commit.
- RELEASE v0.96-beta: fertig gebaut und geprueft. Abbild umbau/build/release-v0.96-beta, Upload-Ordner
  umbau/build/upload-v0.96-beta (68 MiB, 10 Dateien, frisch entpackt sha256 ok), Text
  umbau/build/release-notes-v0.96-beta.md. Grosstest auf HY310 und HY300 bestanden (doku/142).
- test10 fuer Issue #1: gebaut, Upload-Ordner umbau/build/upload-hy300-pro-test10, Text
  umbau/build/release-notes-hy300-pro-test10.md, Antwortentwurf umbau/work/ST3-FOREIGN/drafts/issue1-reply.md.
- GERAETE: HY310 auf v0.96-beta (Release-Modul wieder drauf, neu gestartet, --failed 0). HY300PRO-G-EU auf
  STOCK-Android mit Magisk-Root (boot_a gepatcht, vbmeta_a Pruefung aus), IP 192.168.8.198, Root ueber
  `/debug_ramdisk/su -c`, FEL per `adb reboot efex`. Rueckwege: Vollabzug re/device-dumps/hy300pro-plus-marco/
  emmc-full.img (geprueft) oder TEST-Abbild umbau/build/release-v0.96-beta-geu-TEST.
- HDMI-Kabel liegt am HY300; UART-Bruecke am HY300. ThinkPad 192.168.8.164 (Content Protection steht auf Undesired).
- HDCP 1.4: UEBERHOLT, siehe Abschnitt 14 (Korrektur 19:xx). Der naechste Schritt liegt NICHT im U-Boot:
  Stock laedt den Schluessel per SMC Op 5 still im Bootloader, und der echte Senken-Lauf ist inzwischen
  gemessen und scheitert ebenfalls mit ESR 0x11. Eintrag 18:5x und der 19:00-Nachtrag in doku/144 sind
  als Zwischenstand zu lesen.
- OFFENE ENTSCHEIDUNGEN FUER MARCO: pushen ja/nein; Wortlaut Fernbedienung auf der Release-Seite; doku-Kopie im
  Repo syncen; STATUS-Historie kuerzen; 3.6-Folgearbeiten.

## 13. Geplante Aktionen fuer die naechste Sitzung, mit Ansatz und Aufwand
Reihenfolge ist ein Vorschlag; Marco entscheidet, was zuerst kommt.

### A. HDCP 1.4 weiter (die Spur ist heiss, alles andere ist ausgeschlossen)
**UEBERHOLT durch Abschnitt 14 (04.10. 19:xx).** A1-A4 behandeln ein Symptom: der Warteschleifen-Patch
ist nicht die Ursache. Der gemessene Stand und der naechste Schritt stehen in 14.3.

A1 **U-Boot ohne den Warteschleifen-Patch bauen und booten.** In `mainline/external/u-boot`,
   `arch/arm/mach-sunxi/h713_mips.c`: die Stelle, die 0x4b13d0a4 auf `0x2c630000` setzt
   ("HDCP key-load wait defeated"), hinter eine Umgebungsvariable legen (z. B. `h713_hdcp14_wait=1`
   laesst die Hersteller-Schleife stehen), damit beides testbar bleibt und niemand im Dunkeln steht.
   Bauen mit `mainline/build/uboot-build.sh <O> hy310 release`, per FEL fluechtig laden (schreibt nichts)
   und das MIPS-Log lesen: verschwinden die drei "HdmiRx_HDCP14_LoadKey(), time out!", ist der Weg frei.
   Aufwand ~45 min, 0 Stromzyklen (FEL per `h713-fel --yes` bzw. `adb reboot efex`).
A2 **Falls die Timeouts bleiben:** die Ticks suchen, die die Schleife zaehlt. doku/112 sagt, sie laufen beim
   MIPS-Start bei uns nicht. Ansatz: im Stock-U-Boot (material in umbau/work/FB-HDCP14e/material/hy200)
   die Reihenfolge vor dem MIPS-Release vergleichen - welche Takte/Gates/Resets stehen dort schon, die bei uns
   erst spaeter kommen. Danach dieselbe Reihenfolge in h713_mips.c.
A3 **Nachweis:** Quelle am Geraet, `xrandr --set "Content Protection" Desired`, Bksv ueber DDC lesen
   (Skript /tmp/bksv2.py auf dem ThinkPad, 20 Einsen = gueltig) und "Enabled" abwarten. Gegenprobe: dasselbe
   unter Stock (geht, zweimal gemessen).
A4 Erst wenn 1.4 laeuft: den Warteschleifen-Patch ganz entfernen (doku/112 verlangt es), known-issues-Zeile
   umschreiben, und pruefen ob `THal_Vp_HDMI_ReloadHdcp14Key` (Diff liegt in umbau/work/FB-HDCP14e/) noch
   gebraucht wird - heute hat er nichts bewirkt.

### B. Release v0.96-beta herausgeben (alles fertig, wartet nur auf Marcos Wort)
B1 Entscheiden: mit oder ohne HDCP 1.4. Mit = A zuerst, dann neu bauen (Kernel/U-Boot aendern sich).
B2 Push in der Reihenfolge aus Abschnitt 11: Fork -> main -> Tag -> `gh release create` mit
   umbau/build/upload-v0.96-beta/* und release-notes-v0.96-beta.md -> Release-Seite aus Fremdensicht lesen.
B3 Danach test10 veroeffentlichen (upload-hy300-pro-test10, release-notes-hy300-pro-test10.md) und die
   Issue-Antwort posten (Entwurf umbau/work/ST3-FOREIGN/drafts/issue1-reply.md).
B4 Vor dem Push beantworten: Wortlaut Fernbedienung auf der Release-Seite, doku-Kopie im Repo syncen,
   STATUS-Historie kuerzen (alle drei in doku/144).

### C. Wenn das HY300 wieder unser System tragen soll
C1 TEST-Abbild zurueck: `h713-install install umbau/build/release-v0.96-beta-geu-TEST --test-image --dump <Ordner>`
   (Erstinstallation ueber Stock, also mit Pflichtabzug). Danach Fernbedienung neu koppeln, Einstellungen neu setzen.
C2 Solange es auf Stock laeuft, sind diese Messungen billig (Root ist da): Androids Aufloesungs-Rueckfall
   (doku/144), Androids Standby-Weg (doku/144), und was beim Eingangswechsel passiert.

### D. Kleinigkeiten, jederzeit und ohne Geraet
D1 Webpanel-Runde mit Marco (Aspect-Knoepfe ohne Wirkung, Preset/Regler, Warp-Schalter-Anzeige,
   Seitenverhaeltnis-Konzept) - doku/144 Abschnitt Webpanel.
D2 Installer-Folgearbeiten F1-F6 (doku/144), Interlace-VICs, rootfs/README, h713-cam Exit-Codes.
D3 Nicht-ASCII-Sweep ueber die veroeffentlichten Seiten; private umbau/-Pfade aus ihnen entfernen.

EINSTIEG FUER HDCP: doku/146 (Handoff und Plan), danach doku/145 (die ganze Kette).

## 14. KORREKTUR 04.10. 19:xx - HDCP 1.4: Abschnitt 11 (18:0x/18:5x), 12 und 13.A sind ueberholt
Belege vollstaendig in umbau/work/FB-HDCP14e/sink-test/REPORT.txt (123 Zeilen). Die alten Eintraege bleiben
stehen, damit die Kette nachvollziehbar ist; massgeblich ist dieser Abschnitt.

### 14.1 Was 18:0x/18:5x falsch geschlossen hat
Der Schluss "Stock laedt gar keinen 1.4-Schluessel, es gibt keinen Software-Schritt" stuetzte sich darauf, dass
"down hdcp 1.4" im Bootlog fehlt. Dieser String gehoert aber zum BURN-Pfad (Werksbereitstellung), nicht zum
LADE-Pfad - und der Lade-Pfad druckt auf Erfolg NICHTS. Im Stock-U-Boot dieser Platine (material/hy200/u-boot.bin,
ARM32/Thumb, Basis 0x4a000000) und in der Stock-Env steht:
- `keybox_list=widevine,ec_key,ec_cert1..3,rsa_key,rsa_cert1..3,hdcpkey` - die Keybox-Schleife (0x4a0052c4)
  laeuft JEDEN Boot ueber alle Namen.
- Fuer den Namen exakt `hdcpkey`: `strcmp` bei 0x4a005364, dann `bl push_hdcp_key` (0x4a007724). Das macht
  SMC Op 2 (gibt die Shared-Adresse zurueck) und danach SMC Op 5 mit Laenge 0x120 = 288.
- OP-TEE Op 5 = `sunxi_load_hdcp_key` (Adresse im Hersteller-TEE, nicht abgedruckt): `keybox_get("hdcpkey", buf, 288)`, dann
  `<Routine im Hersteller-TEE, nicht abgedruckt>`(dst=0x03041400, src=buf, 288, key=0, 0, sym_ctl=0x300000, decrypt=1)` - sym_ctl 0x300000 =
  key-select 3 (RSSK), Ziel ist die Key-Senke.
- Die Meldungen des Pfades liegen auf Level 6 (unterdrueckt); ein Fehlschlag druckt auf Level 0
  ("secure storage read %s fail with:%d" bzw. "key %s post install process failed"). Dass Level 0 gedruckt wird,
  beweist derselbe Mitschnitt (die widevine/ec_key-Zeilen). Fuer `hdcpkey` steht KEINE Fehlerzeile.
  => Stocks Op 5 ist auf dem HY300 GELUNGEN.
- Reihenfolge im Mitschnitt: Keybox [02.168-02.175], `display_bin ... copy 0x4b100000` [02.9-03.1],
  "Display fastlogo finish!" [03.912]. Der Schluessel liegt also in der Senke, BEVOR der MIPS startet - genau
  wie Marco es erinnert hat ("Stock schreibt einen Hash/Schluessel vor dem MIPS-Init").
Gueltig bleibt der getrennte Befund, dass waehrend des Handshakes kein einziger RPC faellt: das Laden passiert
beim Booten, nicht beim Authentifizieren.
Zum Hash: `install_hdcp_key` (0x4a007682, Keybox-Callback, nur Burn-Pfad) bildet SHA-256 ueber den Schluessel,
formatiert die LETZTEN 6 Bytes mit "%2x" zu 12 Zeichen und legt sie als `hdcpkeyV14_hash` ab. Das ist genau das
Item, das Android fuer 1.4 liest - eine Kennung, kein Schluessel. Die Deutung "6 Bytes = eine KSV" war falsch.

### 14.2 Unsere eigene Luecke - und was die Messung dazu ergab
Unser BL31 kann den Vorgang seit FB-HDCP14b/d: `sunxi_h713_sip.c:322` ist `ce_run(true, 3, 0x120, SUNXI_HDCP14_SINK)`,
zeichengleich mit Stocks Op 5. Er stand aber in `hdcp14_op()` hinter `ce_rssk_probe()` (16 Nullbytes, key-select 3,
nach DRAM) und wurde bei dessen Fehlschlag mit E_RSSK verweigert; der Linux-Treiber h713-ce hatte dasselbe Gate
(-EPERM). SAEMTLICHE ESR-0x11-Messungen (C3 03.10., 14c, 14d, beide Geraete) sind diese DRAM-Probe. FB-HDCP14c
sagt es in Abschnitt 7 selbst: "none targets the key sink".
MESSUNG 04.10. 19:xx am HY310 (Testbau mit geloestem Gate in beiden Schichten, 2 warme Reboots, 0 Stromzyklen,
Flaeche gesichert auf Geraet und Host und byteidentisch zurueckgebaut):
- Kontrollbau aus dem unveraenderten Release-TF-A: bl31 417e6828 / spl bcc73fc5 / proper 2329f44a - alle drei
  BITGLEICH zum Release (BUILD_STRING leer festgenagelt, siehe 14.4). Das Rezept ist damit bewiesen.
- Testbau: Release-TF-A + sunxi_h713_sip.c + 24 Zeilen in 5 Dateien, OHNE 14ds geparkte Standby-Arbeit.
  bl31 e39e488e (49276 B), spl bitgleich, proper 63f3e5d8 (+4096 B, nur das groessere BL31 im FIT).
- Am Geraet: "EL3 road: BL31 SiP service version 1.0" beweist, dass das Test-BL31 lief (ohne UART, die Bruecke
  haengt am HY300). KAT bestanden (key-select 0, ESR 0, 93 us). DRAM-Probe wie immer ESR 0x11, 13126 us.
- DAS ITEM IST 320 BYTES, nicht 288 (Offset 0x2000, CRC gut): 288 Chiffretext + 32 Bytes SHA-256. Stock fragt
  keybox_get nach 0x120, also sind die ersten 288 der Chiffretext. Unser SiP und h713-ce weisen alles ausser 288
  mit -EINVAL ab - mit dem vollen Item haette der Weg nie funktioniert. Das ist im ganzen FB-HDCP14-Strang
  nirgends aufgefallen, weil der Lauf immer vorher am Gate scheiterte.
- ERGEBNIS: `HDCP 1.4 transfer into the key sink: ESR 0x11 (algorithm-not-supported,unknown-bits), ISR 0, 13126 us`.
  Der Lauf hat stattgefunden (vorher stand dort "key sink refused ... RSSK probe failed" mit E_RSSK).
  HYPOTHESE WIDERLEGT: das Ziel ist nicht der Unterschied. key-select 3 ist unserem EL3 am HY310 verschlossen,
  egal ob die Ausgabe nach DRAM oder in die Senke geht, und auch mit dem echten Chiffretext des Geraets.

### 14.3 Was damit uebrig bleibt
Ausgeschlossen fuer die Verweigerung: das Ziel (neu), die eFuse-Flaglage, der SPC, die Takte, und Software zur
Authentifizierungszeit. Stocks Op 5 gelingt am HY300 unter Stocks eigener sicherer Welt; derselbe Vorgang aus
unserem EL3 scheitert auf beiden Geraeten. Der Unterschied liegt also in der sicheren Welt selbst: monitor.bin
plus OP-TEE gegen unsere TF-A ohne OP-TEE. Abschnitt D von FB-HDCP14e/excerpts/stock-chain-ranges.txt hat den
LADE-Pfad von OP-TEE geprueft (kein SID-Schreibzugriff, kein Zugriff auf die Key-Ladder 0x03041000) - OP-TEEs
eigene INITIALISIERUNG wurde nie angesehen. Dort weitersuchen.
Zweiter Weg, bisher unbeachtet: OP-TEE hat mit Op 7 einen PKF-Pfad (`<Routine im Hersteller-TEE, nicht abgedruckt>`: `<Routine im Hersteller-TEE, nicht abgedruckt>`(hdcppkf, key16)`
liest den PKF als 16 Bytes aus dem SID-Schatten, dann normales AES mit key-select 0 - ohne Key-Bus). Die
Werksbereitstellung schreibt im PKF-Zweig 0x140 = 320 Bytes, im RSSK-Zweig 0x120 = 288. Der Stock-U-Boot ruft
aber nur die Ops 0, 2 und 5 - Op 7 nie. Ob Android Op 7 nutzt, ist offen.
NAECHSTER SCHRITT, billig und lesend: im Stock-U-Boot des HY300 am Prompt die Logstufe fluechtig hochsetzen
(`setenv loglevel ...`, KEIN saveenv, kein eMMC-Schreibzugriff; die UART-Bruecke haengt schon dort) und einmal
booten, damit die Level-6-Zeile "load key hdcpkey with default cb" erscheint und der Default-cb-Zweig - und mit
ihm push_hdcp_key - bewiesen ist.
NICHT die Ursache: der Warteschleifen-Patch auf HdmiRx_HDCP14_LoadKey, also Plan A1 aus Abschnitt 13. Die
MIPS-Timeouts koennen ein zweites, unabhaengiges Problem sein, aber sie erklaeren nicht, warum eine Quelle
Bksv 0 sieht, wo Stocks eigener Lader diese Routine nie braucht.

### 14.4 Nebenbefund, betrifft das Release: die a-Bootkette ist fuer Fremde NICHT reproduzierbar
Beim Kontrollbau fiel auf: das Release-BL31 traegt einen LEEREN BUILD_STRING (`v2.15.0(release):`), ein Bau aus
umbau/src traegt `dfa9fab44`. Ursache: TF-As Makefile hat `BUILD_STRING ?= $(shell git describe --always --dirty
--tags)`, und IM CONTAINER scheitert `git describe` in Klon und Worktree, weil dort `.git` eine Datei mit
`gitdir:`-Verweis ist - in umbau/src (echtes .git-Verzeichnis) scheitert es nicht.
| Baum | `git describe` im Container | BUILD_STRING |
|---|---|---|
| umbau/build/clone-v0.96-beta (E1b) | scheitert | leer |
| umbau/work/_fable-main (Bau 3) | scheitert | leer |
| umbau/src | `dfa9fab44` | `dfa9fab44` |
Folge: wer das Repo von GitHub klont und baut, bekommt ein anderes bl31.bin und damit eine andere a-Bootkette als
die veroeffentlichte. Der E1-Doppelbau konnte das nicht sehen, weil BEIDE verglichenen Baeume den kaputten
gitdir-Verweis hatten. RELEASES.md sagt derzeit "reproducible". Fix ist klein: BUILD_STRING in
mainline/build/build.sh deterministisch setzen (z. B. der Submodul-Commit, auf dem Host ermittelt) statt es von
der Verfuegbarkeit von git im Container abhaengen zu lassen. Entscheidung Marco - vor dem Push oder als
Folgearbeit mit einer ehrlichen Zeile in RELEASES.md.
