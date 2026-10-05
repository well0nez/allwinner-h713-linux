# Plan 141 - Fable-Welle nach main, Kleinkram, Boards, dann Release (03.10.2026)

Grundlage: Marcos Entscheidungen 03.10. abends (doku/61 "Gesamtliste 03.10.2026"), Stand doku/134 (Tests), doku/140
(Handoff), Tiefenpruefung umbau/reviews/deep-review-20260927.md (Integrationsreihenfolge). main lokal = 64f78a2
(GEU1, 0168 Backlight per Adresse, LVDS/Gamma, Fernbedienung per BT, kernel 0169 hid-h713-remote, Warp-Kalibrierbild).

Leitregeln (Memory): Subagenten ohne Rueckfrage, Opus fuer schwere Aufgaben (RE, Analysen, Merges), Sonnet fuer einfache (Skripte, Doku); vor jeder Stufe und jedem Geraeteschritt ansagen und auf Go warten; wo Marco handeln muss, Zug
beenden; vor jedem Schreiben aufs Geraet das Projektlayout lesen; ein Befehl pro Geraeteschritt; laute Tests nach
Absprache; Agenten schreiben nur in umbau/work/<paket>/, integriert wird nur von mir; nichts gepusht ohne Marcos Wort.

## Stufe 0 - Restliche Geraetetests der Welle (jetzt, HY310 laeuft auf dem Stufe-B-Kernel)
| Schritt | Inhalt | Dauer | Marco |
|---|---|---|---|
| 0.1 | C3 HDCP 1.4 ueber EL3: h713-ce mit el3=1, KAT, RSSK ueber den SiP-Dienst (BL31 hat HDCP14b 0001/0001a), Transfer in den Key-Sink, ReloadHdcp14Key; Pruefung von aussen: Bksv am DDC des Laptops gueltig (20 Einsen), `xrandr ... Content Protection Desired` -> Enabled | 20 min, 0 Zyklen | hinsehen |
| 0.2 | C4 1.4-Tor: geschuetzte 1.4-Quelle zeigt Bild = der Laptop mit Content Protection Enabled zeigt weiter Bild | 5 min | hinsehen |
| 0.3 | ERGEBNIS 03.10.: C3 durchgefallen (CE_S bedient Key-Select 3 auch aus EL3 nicht, ESR 0x11) -> HDCP14/14b bleiben DRAUSSEN. FB-HDCP14c (Opus, fertig 04.10. 00:xx): Vendor-Task byteidentisch, keine Key-Ladder-Freigabe; der RSSK liegt nicht am Key-Eingang der Engine = Boot-Vorbedingung (SID-Sense durch BROM/boot0/Stock-BL31, bei uns ersetzt) ODER eFuse nicht gebrannt. EL3-PRCTL-Lesung 04.10. 02:10 (FB-HDCP14d, 3 warme Reboots): Kontrollwort liest korrekt, Flag-Wort 0 -> RSSK NICHT gebrannt, HDCP 1.4 auf diesem HY310 hardwareseitig zu. HDCP14/14b bleiben draussen (fuer andere Einheiten aufgehoben), known-issues sagt es | - | - |
| 0.4 | C1 `commdev`/`elog` am U-Boot-Prompt: bootdelay per fw_setenv auf 5, UART-Mitschnitt, Prompt per Enter, beide Befehle, `boot`, bootdelay zurueck auf 1 | 10 min, 1 Zyklus | Taste |
| 0.5 | HY310 danach zurueck auf main (64f78a2): FIT, Moduldir .main, h713-tv aus /root/integ | 3 min, Reboot | - |
HDCP 2.2 (Session-Beweis) ist auf Marcos Wort nach hinten geschoben: kein 2.2-Geraet da, haelt das Release nicht auf.

## Stufe 1 - Integration der Welle nach main (ich, offline, Zweig `fable-main` von 64f78a2)
Nummerierung ab 0170 (0167/0168 GEU, 0169 hid-h713-remote sind vergeben). Basis der Pakete war c289bb3; main hat seitdem
GEU1, 0168, LVDS/Gamma (h713-tv), Fernbedienung, Warp-Kalibrierbild - daher erwartete Handarbeit:
- hdmirx.c: GEU-0168 (Backlight per Adresse, Init-Schritt) gegen EDIDb 0136z-zc, HDCP22b 0168, HDCP14 0167b, HDCP14b
  0168, AUDIO 0169 - die Init-Sequenz-Liste und der Step-enum sind die Konfliktstellen.
- h713-tv/main.c: Drei-Kanal-Gamma (bf72eb3) gegen EDIDb 0001-0003a, HDCP22b 0001-0003, AUDIO 0001, AUDIOb 0004/0005,
  DSPVOL 0002/0003 (der A3-Stapel lag auf c289bb3; umbau/work/_deepreview/builds/tv-stack als Vorlage).
- h713-warp gl.c/loop.c: Kalibrierbild (f84c17c) gegen EDGEBLEND 0001-0004 + MIRROR 0001-0003 (kombinierter Diff
  umbau/work/_deepreview/geometry/out/).
- Board-defconfig: H713_CE, UHID (schon da), HID_H713_REMOTE (schon da).
Reihenfolge und Inhalt (Commits je Paket, jeder mit `patch --fuzz=0` oder ausgewiesener Handmischung):
| Bereich | REIN | Quelle |
|---|---|---|
| Kernel | EDIDb 0136z/za/zb/zc; HDCP22b 0168/0168a; AUDIO 0169/0169a/0170 (Bruecken-PCM, istream=2); HDCP14 0167/0167a/0167b + HDCP14b 0168/0168a (nur wenn Stufe 0 besteht) | Paketordner, Handmischungen in _deepreview/builds/merged |
| TF-A | HDCP14b 0001/0001a (SiP-Dienst) - nur wenn Stufe 0 besteht | FB-HDCP14b |
| U-Boot | UBOOTDBG 0001/0002 (commdev/elog), SAFETY 0004 (panic=10 in der Env) | FB-UBOOTDBG, FB-SAFETY |
| Userspace | KSREF 0001-0004 + KSREFb 0005/0006; AFWAIT; AFSEARCH 0001-0004; EDGEBLEND+MIRROR (+EDGEBLEND 0004); h713-tv-Stapel; HDCP14 0001-0003 + HDCP14b 0002/0004/0004a/0005 (h713-hdcp-key, nur mit Stufe 0); SAFETY 0003 (Keystone-Watch) | Pakete, A3-Stapel |
| Rootfs | AUDIOb 0003/0003a (H713-MSP.conf, asound.conf), DSPVOL-README, HDCP-Key-Dienst | Pakete |
| Werkzeuge/Bau | INSTALL 0001-0005 (restore-stock-Pruefung, ohne Argumente, zstd, Python 3.9, zweite Installation), REPRO 0001-0005 (SOURCE_DATE_EPOCH, Stempel) | Pakete |
| Doku | DOKU 0001-0007, Paket-Doku der Welle, kernel-patches.md fortschreiben | Pakete |
| RAUS | siehe Tabelle unten | doku/61 |

**Was RAUS bleibt (je eine Zeile in doku/61 "Geparkt", mit Ort und Bedingung fuer die Wiederaufnahme):**
| Paket | Warum | Liegt in | Kommt rein, wenn |
|---|---|---|---|
| FB-STANDBY (Kernel 0167-0172, tfa-0001/0003, Parameterbaum) | Wecken geht nicht (C2, doku/139); tfa-0001 bietet "mem" an, ein Suspend haengt das Geraet | umbau/work/FB-STANDBY, standby-local | ein Standby-Weg mit Wecken bewiesen ist |
| FB-STANDBYc 0167c (ARISC-Byte-Lanes) | gehoert zum Parameterbaum (ohne Baum unnoetig); am Geraet bestanden (B0) | umbau/work/FB-STANDBYc, reviews/FB-STANDBYc.md | mit Standby |
| FB-STANDBYd | Brief durch doku/139 ueberholt, nie gestartet | umbau/plan/briefs | - |
| FB-CRUST | geparkt (Marco 03.10.) | umbau/work/FB-CRUST | nach Standby |
| FB-MIPSRELOAD/b (0167-0167d) | Oopses weg, Bild nach Reload schwarz (doku/138) | umbau/work/FB-MIPSRELOAD*, mipsreload-local | Bildfehler verstanden |
| FB-REMOTEb 0001-0003a + fd02-Keymap (IR) | Maus/Mikrofon per IR bitgleich 0x66 (doku/134) | ir-local/ready, FB-REMOTEb | IR-Ursache geklaert |
| FB-SAFETY 0001/0002 (Luefter-Backstop) | am Geraet ungetestet (B7, Stecker unzugaenglich) | umbau/work/FB-SAFETY | B7 bestanden |
| FB-HDCP14/14b (Kernel 0167/a/b + 0168/a, TF-A 0001/0001a, h713-hdcp-key 1.4-Teil, h713-ce) | C3 durchgefallen: Key-Select 3 wird auch aus EL3 verweigert (ESR 0x11); der BL31-SiP-Dienst ist im C0-BL31 drin und harmlos (ungenutzt) | Pakete, doku/134 C3 | FB-HDCP14c klaert 7.2 (SPC/Key-Ladder) und eine Probe besteht |
| FB-HDCP22c, FB-BTFW, FB-GE2D | Analysepakete ohne Lieferpatch | Pakete | - |

Pruefung je Commit: Bau im Container (Kernel, bl31, U-Boot, Userspace cross), Tests der Werkzeuge (Python-unittest,
Warp T1a/T1b/T2), Identitaets-grep, nur "-" als Strich. Dauer: ein bis zwei Sitzungen.

**Stand Stufe 1 (04.10. 02:30):** Zweig `fable-main` (Worktree umbau/work/_fable-main/src), 8 Commits ueber main 64f78a2:
kernel 0170-0178; h713-tv-Stapel; Geometrie (Keystone/Panel/Warp, Kalibrierbild mit Spiegelmodi von Hand gemischt, SAFETY
0003 durch KSREFb 0006 abgedeckt und entfallen); Autofokus; Rootfs/Installer/REPRO; U-Boot-Fork a830902 (UBOOTDBG +
SAFETY 0004); Docs/Doku. Tests gruen: Keystone, Panel, Autofokus, Fokus, Installer 357, Warp T1-T3. Gebaut: Kernel (FIT
d0f4b129, Module modules-fable.tgz), U-Boot 978.944 B. NICHT drin: Standby, 0167c, Crust, MIPSRELOAD, IR, SAFETY 0001/0002,
HDCP14/14b, HDCP22b 0002 (Serie), AUDIO/EDIDb Doku-Reste mit alten Nummern. Offen vor dem Merge nach main: Stufe 2
Kleinkram auf demselben Zweig, dann Geraetetest (Stufe 4) - der HY310 traegt heute main ohne die Welle.
Nebenbefund: ein `git checkout` im falschen Verzeichnis hat den Arbeitsbaum des Worktrees kurz durch den U-Boot-Baum
ersetzt (Zweig unberuehrt, wiederhergestellt); U-Boot-Objekte liegen jetzt zusaetzlich im Objektspeicher von umbau/src.

**Stand 23:15:** Stufe 1 fertig (9 Commits, 031dd6c). Stufe 2 gesichtet, nichts geaendert; Fundstellen je Punkt in
doku/140 "Stand 03.10. 23:15". Punkt 7 ist durch Stufe 1 erledigt; Punkte 3, 4, 8 brauchen das Geraet (Stufe 4).
Neuer Punkt 12: FB-BTRESET-Patches 0001/0002 uebernehmen (Fix bewiesen, Report umbau/work/FB-BTRESET/REPORT.txt).
**Stand 23:50 Stufe 2 (Zweig fable-main):** ERLEDIGT 1+2 (af449cc Keystone SIGTERM=0 mit Test, measure --timeout 10),
12 (9971078 BTRESET 0001/0002, 8 Tests), 11 (f5a25d4 README/hardware/known-issues/wifi.md Abschnitt "Bluetooth" inkl.
0x0c03; 4f607d3 ROADMAP-Zeile), 9 (0179 hdmirx: 0x6d als Connect-Event-Flag benannt, Objekt kompiliert, h713-tv README
Beispiel), 7 (durch Stufe 1). LAUFEN als Sonnet-Agenten: 5a Rootfs-Werkzeuge englisch + 6 country-Regel (Paket
FB-KLEIN-en: h713-wifi, wifi.env, aic8800.conf, h713-hdcp-key(.conf), hy310-zram-swap -> Patch 0001), 5b Kernel-
Treiberzeilen englisch (Paket FB-KLEIN-kernel-en -> Patch 0180 ueber 8 Dateien, ohne hdmirx; ich kompiliere danach
im Container). Punkt 10 ERLEDIGT: der Treiber mit 0171 loggt "source WxH at R Hz: <Grund> -- no lock" (Baum Zeile 3805); B1 am 02.10. hat genau diese Zeile gesehen, die Review-Bemerkung stammt von davor. 00:50: FB-KLEIN-en 0002 drin (2eee31d). 01:05: 0180 drin (Treiberzeilen englisch, 8 Objekte kompiliert) -> Stufe 2 offline KOMPLETT; Kernel vor Stufe 4 neu bauen. Stufe 3: ST3-BOARDMERGE + ST3-FEATURES als Opus-Agenten gestartet 00:55. Punkte
3, 4, 8 nur am Geraet (Stufe 4). Kernel-FIT d0f4b129 ist damit VERALTET (0179/0180 fehlen) - vor Stufe 4 neu bauen.

## Stufe 2 - Kleinkram (ich, auf demselben Zweig, eigene kleine Commits)
1. Keystone-Watch: Stop ohne Exit 130 (systemd "failed"); 2. `h713-autofocus measure` mit Zeitlimit; 3. Fokus-Metrik
flach (+11 %) - Belichtung pruefen, ggf. Testbild-Kontrast; 4. Interlace-VICs (5/6/7/20/21) in die Modusliste des
Treibers (0136zc); 5. deutsche Treiber-/Werkzeugzeilen nach Englisch (MSP "Patch geladen", arisc "EDID uebernommen",
"EDID/HPD-Sequenz", hy310-board-mgr NTC-Zeilen u.a.); 6. h713-wifi: leeres country -> Warnung + Vorgabe statt Abbruch;
7. h713-warp `make test`: tests/ ins Repo (aus WARP-CALIBRATION-DRAFT); 8. Warp bei 120-Hz-Quelle 19 fps: Ursache
(busy=dropped) klaeren oder als bekannt dokumentieren; 9. HDCP22b LINK 0x6d deuten oder die Zeile ehrlich benennen;
10. EDID-Statuswortlaut; 11. B6-Nebenbefund: hci0 "Opcode 0x0c03 failed" beim Stoppen dokumentieren (Ursache: FB-BTRESET Fehler B);
12. FB-BTRESET 0001/0002 (h713-bt-reset + Unit) + docs/subsystems/wifi.md BT-Abschnitt; Geraetetest REPORT 8 in Stufe 4.
Nicht mehr verfolgt: eMMC "data error cmd18" (einmalig, Marco: nur wenn es wieder auftritt).

## Stufe 3 - Boards und Hardware (Agenten nach FB-common + ich; Briefs vorher mit Marco)
| Punkt | Inhalt | Wer |
|---|---|---|
| 3.1 Board zusammenfuehren | hy300pro-g-eu und hy200-qz713df-a1 sind dieselbe Platine (HY200 QZ713DF A1): ein Board-Verzeichnis, Varianten fuer Firmware/DRAM/eMMC/Projekt-ID, Installer-Erkennung, ein DTS mit Variantenteilen. ERGEBNIS 04.10. 04:10: ST3-BOARDMERGE (Opus, 6 Patches + U-Boot-Fork-Patch) von mir nachgeprueft (Scratch: Installer 361, Validator, boards/check, Varianten-Tests; DTB-Beweis selbst gebaut: hy310 und hy300-pro byteidentisch vor/nach 0181, neuer hy200-Baum = GEU-Baum bis auf model/compatible; Fork-Patch apply --check) und als 4 Commits integriert (0e26943 Installer, 97b30a1 Boards/Build/Rootfs + Fork 6fb736c, 970a7a5 Kernel 0181 + h713-tv, 75a0169 Docs). FEATURES je Variante (Agent-Entscheidung, akzeptiert: 09-22-Einheit ungemessen) - damit sind ST3-FEATURES 0002/0003 ERSETZT (variant.env + README-Tabelle), 3.2 vollstaendig. Offen: U-Boot-Bau der Basis hy200 mit Variante (laeuft), Geraetetest GEU (REPORT 6: TEST-Image --variant projector05061226, 1 FEL, 1 Stromzyklus), Fragen des Agenten: cstengers altes Flash-Layout entfaellt (er hat seinen eigenen Baum), lange Image-Namen bleiben | Agent (Opus) + Review |
| 3.2 Hardware optional | Kamera, Beschleunigungssensor, Fokusmotor je Board in board.env/DTS; Dienste mit Bedingung, "nicht vorhanden" statt Fehler (GEU: keine Kamera). ERGEBNIS 04.10. 03:10: Paket ST3-FEATURES (Opus, 18 Patches) von mir in Scratch-Kopie nachgeprueft (Suiten 176/44/6/28/2/8, boards/check gruen, Paket-Test 3, udev/systemd verify) und als 4 Commits auf fable-main integriert - OHNE 0002/0003 (GEU board.env/README: nach ST3-BOARDMERGE von Hand FEATURES=accelerometer). Offen: echter Rootfs-Bau mit --board (Stufe 4), Geraetetest REPORT 5 (HY310 1 Boot, HY300 1 Boot), Fragen 1-4 des Reports (FEATURES je Variante?, GEU-Sensor WhoAmI, Kameraname 'HD camera' fest, keystone-auto Restart bei exit 3/5) | Agent (Opus) + Review |
| 3.3 Keystone-Auto | fehlender oder spaet verfuegbarer Sensor ruhig behandeln, voruebergehende Lesefehler nicht dauerhaft stilllegen (Patch 0009 neu aufsetzen) | Agent oder ich |
| 3.4 HY300 Lampe | Lampen-PWM-Block unprogrammiert, Stock-Handover `bl_power 4->0` (doku/61, doku/137) | ich, am HY300 |
| 3.5 restore-stock | weitere eMMC-Groessen (HY300 Pro 15273600 Sektoren u.a.) | Agent |
| 3.6 Fremdgeraete | Profil fuer Issue #1 (HY300 Pro des Melders, 636 MHz), LPDDR3-Board hy200-qz713-v2 (tpr0..2) | Agent + Review |
Geraetetests von 3.1/3.2/3.4 am HY300 (Marco), 3.3 am HY310.

## Stufe 4 - Grosstest
Protokoll mit Befehlen, Erwartungen, Dauer und Stromzyklen: doku/142 (Entwurf 04.10. 00:20).
1. Image aus `fable-main` + Stufe 2/3, Bau von vorn (Memory "Release-Bauten immer von vorn").
2. HY310 (FEL + ums, Testabbild): Stufe-A-Kurzlauf (Keystone, Warp, Autofokus), EDID, Audio-Kurztest (D1/D2 je eine
   Messung, laut nach Absprache), Fernbedienung (16 Tasten, Maus, Koexistenz), HDCP 1.4 (falls drin), Kalibrierbild,
   20 Kaltstarte (Gate, Logo, Konsole, HDMI). Ca. 1,5 h, 20 Zyklen.
3. HY300PRO-G-EU: Boot, Bild (LVDS 8 Bit, Gamma), Lampe, Fernbedienung, BT-Kaltstart-Stand, keine Kamera-Fehler.

## Stufe 5 - Release (Stufe E)
E1 Doppelbau bitgleich (REPRO), E2 Testabbild zweimal ueber unser Layout installieren (INSTALL 0004), Release-Seite
aus Fremdensicht pruefen, Identitaetspruefung aller Repos inkl. U-Boot-Fork (2de0cc8 und Nachfolger nach GitHub), Push
und Release nur auf Marcos Wort. Offene Punkte aus doku/61 Abschnitt A: Beta-Warnung, Werkzeuge englisch, GPT-
Gegenprobe, Installer liest .zst, Recovery von einer zweiten Person.

## Danach (nicht release-relevant)
HDCP-1.4-Fuse-Lesung am HY300 Pro (Marco 04.10.: GEU-Proper mit FB-HDCP14d-BL31 + ko fuer den GEU-Kernel; bestaetigt die Bit-Deutung), HDCP-2.2-Session, Webpanel gemeinsam, Konsole durch den Warp, Schein-Standby wie Stock, Abschalt-Plopp,
Geraetetoene als Funktion, GEU-BT-Kaltstart, BT-Firmware-Lizenz, Standby/Crust/MIPS-Reload/IR (geparkt), Abschnitt 8
der Gesamtliste.

**Stand 04.10. 11:15 Stufe 3:** 3.1, 3.2 fertig (04:10); 3.3 ERGEBNIS: RestartSteps/RestartMaxDelaySec in
h713-keystone-auto.service (da862d9), Patch 0009 ueberholt; 3.5 ERGEBNIS: ST3-RESTORE integriert (dd726eb);
3.6 ERGEBNIS: ST3-FOREIGN integriert (5588787, 9c81acc, 5c8da0f), hy300-pro bleibt eigenes Board, V2 "not testable
yet"; 3.4 OFFEN (Geraet). fable-main = dd726eb, 30 Commits. Geraetetests der Stufe 3 in doku/142 Nachtrag.
Naechster Schritt: Stufe 4 (Bau von vorn), Eingaben von Marco siehe doku/143 Abschnitt 11.
