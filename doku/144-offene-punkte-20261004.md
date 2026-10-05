# 144 - Alle offenen Punkte, Stand 04.10.2026 12:15 (fable-main 36 Commits, vor Stufe 4)

> **Überholt.** Der aktuelle Stand der HDCP-Kette steht in [`docs/subsystems/hdcp.md`](../docs/subsystems/hdcp.md), die Durchführung in `doku/148`. Dieser Eintrag bleibt unverändert stehen, weil er der Beleg dafür ist, wann was gemessen wurde — nicht, weil seine Schlussfolgerungen noch gelten.

> **Redigiert (05.10.2026).** Aus diesem Dokument sind die Kennungen und Adressen entfernt, mit denen man das **Trusted OS des Herstellers** direkt anspricht — SMC-Kennungen, Funktionsadressen und die Lage des Hardwareschlüssels im eFuse. Die Befunde bleiben: *dass* der HDCP-1.4-Satz chipgebundenes Chiffrat ist, dass nur die Crypto Engine den Hardwareschlüssel sieht und dass sie ihn nicht nach lesbarem Speicher schreibt. Das erklärt unseren eigenen Weg; der Rest war ein Rezept für fremde Geräte und gehört nicht veröffentlicht.

Marcos Wunsch (04.10. 12:05): alle noch offenen Punkte der Fable-Welle und generell alle offenen TODOs auf einer Seite.
Quellen: doku/61 Gesamtliste (Abschnitte 1-8, A.2, A.7), doku/141 RAUS-Tabelle, doku/142, doku/143 Abschnitte 4, 6, 7, 8,
11, doku/134 (offene Nits je Zeile), doku/131 (Zoom), die FOLLOW-UP-Listen der Pakete FB-BTRESET, ST3-FEATURES,
ST3-BOARDMERGE, ST3-RESTORE, ST3-FOREIGN, ST5-DOCAUDIT. Erledigtes steht hier nicht; was in den Quellen als erledigt
markiert ist, wurde geprueft (z. B. GPT-Gegenprobe = check_stock_gpt, Installer liest .zst, Python 3.9, measure --timeout).
Reihenfolge = Dringlichkeit. "[M]" = Marco entscheidet oder handelt.

## 1. Vor dem Release v0.96-beta (Stufe 4 und 5)
- Grosstest nach doku/142 (HY310 ca. 2 h, 22 Zyklen; HY300 Pro 5 Zyklen, ohne UART per ssh nach dem Boot). Darin die
  Geraete-Reste der Welle: Fokus-Metrik flach (+11 %, Belichtung), Interlace-VICs 5/6/7/20/21 in `h713-tv ctl status`,
  Warp bei 120-Hz-Quelle 19 fps (busy=dropped) klaeren oder als Grenze dokumentieren, FB-BTRESET Abnahme (Kaltstart,
  2 warme Reboots, Restart), ST3-FEATURES REPORT 5 (HY310 nichts geaendert; HY300 not-present-Pfade, Seite ohne
  Fokus), ST3-BOARDMERGE REPORT 6 (HY300 TEST-Image der Variante, DRAM 792, LVDS 8 Bit, Luefter, Fernbedienung,
  /etc/h713/features), restore-stock --no-write am GEU (Plan ansehen, nicht schreiben), 20 Kaltstarte mit Lampen-
  Pulsieren zaehlen, BT-Kaltstart am GEU (0x1003) mit h713-bt-reset.
- Danach die zwei STAGE4-Marker fuellen und loeschen (`git grep -n STAGE4`: RELEASES.md "Measured", STATUS.md Zeile 9).
- Stufe 5 nur auf Marcos Wort: Fast-Forward fable-main -> main (vorher `git log main..fable-main --stat` gegen die
  REIN-Tabelle doku/141), Identitaetspruefung in frischem Klon aller Repos inkl. Fork, Fork-Push h713-hy310 (Fast-
  Forward auf 6fb736c, sonst scheitert `git submodule update --init` bei Fremden), Push main, Tag, gh release mit
  a/b/c .zst + tabelle.json + sha256 + README.txt + BUILD.txt + u-boot-installer.bin + u-boot-h713-probe.bin + sunxi-fel,
  Release-Seite aus Fremdensicht (Checkliste ST5-DOCAUDIT REPORT Abschnitt 3).
- [M] Wortlaut Release-Seite: "nothing acts on the remote's keys yet except Power" so lassen oder erst eine
  Tastenbelegung (Lautstaerke)? [M] doku-Kopie im Repo: 8 saubere Dateien syncen; 00-STATUS/71/75/61-todo erst nach
  Scrub oder 61-todo aus der Kopie werfen. [M] STATUS-Historienabschnitte nach dem Release kuerzen?
- Kleine Code-Reste aus ST5-DOCAUDIT Abschnitt 5 (nach dem Release, nicht blockierend): identify.py druckt "our layout
  (v3, doku/109)" fuer v4; h713-install/dump.py melden VERSION "0.1 (draft, doku/110)"; `install --help` nennt bei
  --test-image nicht <profile>/<variant>; README.txt des Abbilds traegt Wanduhrzeit statt SOURCE_DATE_EPOCH.
- Aus doku/61 A.2 noch offen: Recovery durch eine zweite Person; HDMI-Modustabelle vollstaendig (Abschnitt B).

## 2. Fable-main - offen am Geraet oder in der Bedienung (keine Release-Blocker, Marco kennt sie)
- **Zoom** (Marco 04.10.: "bringt das Geraet durcheinander, weiterhin falsch"). Stand: `h713-tv ctl zoom out` ist seit
  23.09. abgeschafft (DE verkleinert nicht, schnitt nur ab; doku/131 Nachtrag Mittag), der Zoom ist `h713-warp ctl zoom
  PERCENT` auf der GPU, die Lupe `zoom in` bleibt. OFFEN: der gemeldete Bug der Seite (Button-Klicks verziehen/
  zerstoeren die Ansicht; "Zoom entspricht nicht der erwarteten Bedienung"; doku/61 Abschnitt 5 und Zeile 563ff), nicht
  reproduziert; die Keystone-Werte standen am 23.09. ploetzlich auf tl 0,0 tr 0,0 bl 8,16 br 0,0 - wer sie zurueck-
  setzte, ist offen (Seite? Reset?); Preset-Wahl auf der Seite soll die Einzelregler mitziehen; ausgeblendete Bloecke
  verschieben das Layout (ST3-FEATURES). -> Webpanel-Runde mit Marco: Klickfolge und Soll/Ist festhalten, dann
  Zoom-Gespraech (ein Zoom fuer beide Faelle, doku/131 "Offen").
- Fernbedienung: nichts im Abbild wertet die Tasten aus ausser Power (logind faehrt herunter - Marco: bleibt so);
  Tastenbelegung (Lautstaerke, Presets, Keystone) fehlt. Schein-Standby wie Stock (Lampe + Luefter aus, Wecken per BT).
- Bluetooth: FB-BTRESET 9.1 Ursache A (erster Befehl nach warmem Reboot verloren, der Fix wiederholt nur), 9.2 Kernel
  verliert seinen Close-Reset beim tty-Detach (hci_ldisc, upstream-wuerdig), 9.3 GEU: 245-Byte-Schreibvorgaenge kommen
  unvollstaendig (RTS/CTS?), 9.4 Stock lpm 1 / btmode 255 gegen unsere 0 / 5, 9.5 hciattach -s 1500000; GEU-BT-Kaltstart
  0x1003; BT-Firmware-Lizenzfrage (fmacfwbt_* nur im SDK-Satz).
- HDCP 1.4: offen, nicht geschlossen (Marco). Entscheidungstests: (a) dieselbe Fuse-Lesung am HY300 Pro (GEU-Proper
  mit 14d-BL31 + h713-ce.ko fuer den GEU-Kernel, 2 warme Reboots, LBA 2048; nach dem Grosstest, Marco einverstanden),
  (b) echte 1.4-Quelle am HY310 unter Stock-Android oder mit dem HDCP14b-Pfad. B1 Nachtrag: HDCP-DDC-Slave des
  Empfaengers antwortet dem Laptop "Bksv is invalid" - lebt er erst mit dem 1.4-Key oder fehlt ein Enable-RPC?
  HDCP-1.4-Warteschleifen-Patch bleibt, bis 1.4 geht oder aufgegeben ist.
- HDCP 2.2: Session-Beweis braucht eine 2.2-Quelle (Stick/Konsole).
- 3.4 HY300-Lampe: Testplan doku/143 Abschnitt 11 (Foto gegen Stock, PWM-Block lesen); dunkler -> Stock-Handover
  (bl_power 4->0, PanelControl::switchToMipsPWM, Vendor-Modul aus vendor_a) offline analysieren, nach Ansage.
- Audio: Abschalt-Plopp; Geraetetoene als Funktion gibt es nicht (Bruecke steht, nichts spielt einen Ton).
- Geometrie: ceiling-Beweis mit dem Beamer kopfueber; Kalibrierkarten in den gespiegelten Modi; Konsole durch den Warp.
- Autofokus: eine Wand, ein Abend; Metrik-Spanne +11 % (Kamera-Pegel 178909 gegen 70111 am 26.09., Belichtung).
- Standby: PSCI-Suspend erreicht DRAM-Eintritt, kein Wecken (doku/139) - geparkt; Schein-Standby s. o.
- eMMC "data error cmd18" am GEU (einmal): nicht verfolgt, erst bei Wiederauftreten.
- KEY_POWER-Politik und WLAN-Band der Koexistenzmessung nicht notiert (doku/134 Zeile 136).

## 3. Geparkt (mit Wiedereinstiegsbedingung, doku/141 RAUS)
- FB-STANDBY + 0167c (rein, wenn ein Standby-Weg mit Wecken bewiesen ist; BL31 ohne tfa-0001/0003 bis dahin).
- FB-CRUST (nach Standby). FB-MIPSRELOAD/b (rein, wenn der Bildfehler nach Reload verstanden ist, doku/138).
- IR FB-REMOTEb + fd02-Keymap (rein, wenn die IR-Ursache geklaert ist: rx_resolution-Trunkierung, ARISC schreibt
  0x222222ff nach PL_CFG1, Pull-up-Loescher unbekannt). FB-SAFETY 0001/0002 Luefter-Backstop (rein, wenn B7 bestanden -
  Luefterstecker). FB-HDCP14/14b (rein, wenn ein Entscheidungstest 1.4 oeffnet).

## 4. Boards und Fremdgeraete
- hy300-pro (Issue #1): test10 aus fable-main nach dem Release (0168, 0182, 2de0cc8, Gamma, h713_project=0x34);
  Issue-Antwort = Entwurf umbau/work/ST3-FOREIGN/drafts/issue1-reply.md [M posten]; Owner-Test REPORT Abschnitt 6;
  Q1 warum test9-Install h713_project auf 0x30 liess (Install-Ausgabe fehlt) -> Installer-Test "h713_project aus
  --dump" (ST3-FOREIGN Folge 1); Q2 nimmt seine display.bin cf9649bc das Argument als Adresse (nur gefolgert); Q3
  Einheit motor-phase-udelay/step-mdelay in seinem Treiber; Q4 Silkscreen; Panel-Dict in hy300_pro.py fuellen
  (sein panel_config.ini liegt vor); known-issues-Zeile und boards/hy300-pro nach seinem test10-Bericht;
  hy300_pro_defconfig-Kommentar im Fork ("include of the bench board's" -> hy310.dts).
- hy200-qz713-v2: Layout-v4-Defconfig und eigener Baum (hy310-Include + PWM-Woerter) VOR jedem TEST-Image; Q5 tREFI
  0,3 % ueber 3,9 us nur mit Registerdump eines laufenden Boards zu klaeren.
- hy200-qz713df-a1: 09-22-Einheit unbekannt (eMMC-Groesse, DRAM, Sensor, Kamera, Motor -> per-Variante-Baum/Overlay,
  BOARDMERGE Folge 4); build-all --skip-rootfs prueft nur "board =", nicht die Variante (Folge 5); boardneutraler
  Name fuer das gemeinsame Kernel-Defconfig (Folge 6); Elog-Adressen der 09-22 display.bin; PWM5-Pad, PB4, PH17.
- FEATURES der Boards ohne Besitzerbericht bleiben leer (hy300-pro, hy350, hy300-t08, hy200-*).
- boards/check.sh sollte die FEATURES-Namen pruefen (ST3-FEATURES Folge).

## 5. Installer und Werkzeuge
- ST3-RESTORE F1 Schema-Feld layout.disk_sectors_from = unit|image statt Heuristik (Marco: Heuristik jetzt, Feld danach);
  F2 Container-gegen-Board-Pruefung vor dem Schreiben (inkl. boot0-DRAM-Block gegen Profil); F3 GEU-eigenes update.img,
  wenn vorhanden, in fakedisk.IMAGES; F4 Disk.write Endpruefung (lba + sectors <= disk.sectors); F5 restore-stock auf
  profile-only-Board braucht --skip-identify und verliert den private-Lock -> Lock aus der Geraete-GPT; F6 FLASHING
  restore-stock-Zeile (von ST5-DOCAUDIT erledigt).
- Webpanel: Konzept Ecke/Kante, Seitenverhaeltnis, Undo/Redo, Vorschau = Warp-Geometrie (doku/61 Zeile 555ff).
- Verwaltungsoberflaeche (WLAN, Presets, Startmodus, Updates ohne SSH) - Zuschnitt offen.

## 6. Dokumentation und Repo
- ST5-DOCAUDIT Folgen: doku-Kopie-Sync nach Marcos Antwort (8 Dateien; 121/86 Links im Journal richten, dann kopieren);
  Anker-Pruefung und Alle-Dateien-Umfang in tools/check-links.py uebernehmen; Nicht-ASCII-Sweep ueber die
  veroeffentlichten Seiten (Pfeile, x, Mittelpunkte, Paragraphen; 35878 Zeichen in 270 Dateien, meist doku/);
  private umbau/...-Pfade auf veroeffentlichten Seiten (STATUS, display, video, arisc, warp, autofocus, wifi) durch
  doku-Nummern oder Worte ersetzen; rootfs/README.md nennt --board/--variant nicht; h713-cam README ohne Exit-Codes.
- known-issues Zeile 15 (HY300 Pro dunkel) nach test10-Foto; docs/known-issues nach HDCP-Entscheidung.
- Agenten-Scratch loeschen (Marco): umbau/work/FB-HDCP14d/build bleibt (Test-Proper fuer die HY300-Lesung).

## 7. Spaet (doku/61 Abschnitt 8)
- **[M, nach dem offiziellen Release] HDCP 1.4 ueber FEL/BL32 fertigstellen.** Handoff und
  Plan: doku/146. Der
  Lademechanismus ist seit 04.10. nachgebaut und am HY300 gemessen: Hersteller-OP-TEE als
  BL32 (args.arg0 = MODE_RW_32), Shared Memory per `<SMC des Hersteller-TEE, nicht abgedruckt>` mit einem /firmware/optee-Knoten,
  Keybox per op 1 mit dem Record bei Slot+0x64, dann op 5 -> a0 0x0, Schluessel in der
  Key-Senke. Ganze Kette und Nachbauplan: doku/145. Was noch fehlt: der Nachweis am Bild
  (Quelle, Bksv, "Enabled"), und dafuer muss unser System auf dem Geraet laufen, auf dem das
  HDMI-Kabel steckt - in U-Boot allein bedient niemand EDID und Hotplug der Eingangsseite.
  Dazu die Entscheidung, ob das Hersteller-OP-TEE dauerhaft als BL32 mitfaehrt (dann NICHT
  ausliefern, sondern bei der Installation aus dem Boot-Paket des Geraets ziehen wie die 44
  vorhandenen Vendor-Dateien) oder ob wir den Weg ohne den Blob nachbauen.
  Marco 04.10.: nicht release-blockierend, kommt nach dem offiziellen Release.

Wissensdatenbank englisch, Testskripte veroeffentlichen, Cedrus/GPU-Matrix, Verwaltungsoberflaeche, Windows-sunxi-fel,
ge2d (DOKU 0007: "not needed"), tvtop/tvfe/nsi, AV1, Presets/Gamma/CTM gegen Stock, Rueckmeldung an cstenger
(Composition-Befund, D1-CCU Port 1, SIDDQ, Doorbell, Archived-Falle), Reserve0/private von einem unberuehrten Geraet,
analyse/hdcp-keys nach re/ (Marcos Handgriff, Doku-Verweise ziehen mit).

## Nachtrag 13:25 - E1 Doppelbau
- Bausteine (SPL, Proper, Env, Installer-U-Boot, FIT, Module, h713-tv, mesa, rootfs.tar) BITGLEICH in Worktree und
  frischem Klon (nach dem -ffile-prefix-map-Fix, Commit 6602c9f). a-bootkette und c-gptkopie bitgleich. b-system nicht:
  die zwei ext4-Container tragen mke2fs-Zufalls-UUID/hash_seed, Wanduhr-Zeiten und die ctime des Entpackens. Fix bekannt
  (doku/143 13:25), offen: jetzt oder nach v0.96-beta.

## Nachtrag 04.10. 16:1x - nach dem Grosstest HY310 (Marcos Einordnung)
- **Webpanel: Seitenverhaeltnis nach einer Keystone-Anpassung** (Marco 03.10. und 04.10., doku/61 Zeile 543-566,
  doku/139 Zeile 98): ist das Bild einmal per Ecken angepasst, soll die Seite klug helfen, das Seitenverhaeltnis
  zu halten oder herzustellen - Ziel-Seitenverhaeltnis waehlbar und sperrbar (16:9, 4:3, Quelle), gefuehrte
  Korrekturen fuer seitliche oder vertikale Aufstellung AUF BASIS der aktuell gesetzten Geometrie (nicht erst
  zuruecksetzen), eine Kante bewegt beide Endpunkte gemeinsam und haelt deren Schraeglage, Undo/Redo je Geste
  mit allen acht Eckwerten und Zoom. Grenze, die das Konzept loesen muss: eine Bildform im Browser beweist kein
  richtiges Seitenverhaeltnis an der Wand - die Projektionsperspektive (Wurfverhaeltnis 0,8176, Neigung aus dem
  Sensor) oder eine Referenzmessung (Massband/Kamera) muss in die Rechnung. Zuerst Konzept mit Marco, dann Bau.
- **Kleinigkeiten:**
  - Drei Interlace-Modi (VIC 6, 7, 21) fehlen in der Modusliste des Treibers; die Statuszeile nennt sie.
  - Neuinstallation ueber eigenem Layout erhaelt die Fernbedienungs-Kopplung (/var/lib/bluetooth) und die
    eigenen Einstellungen (/etc/h713: Keystone-Ecken, warp.conf, tv.conf, /var/lib/h713-tv) nicht - der
    Installer koennte sie aus dem alten Rootfs uebernehmen, wie er es mit der U-Boot-Env tut.
  - Warp 21 fps im ersten Boot nach der Installation (nicht nachstellbar): egal (Marco).
  - Autofokus: zwei Laeufe, zwei Spitzen (51/93), Bild scharf: so ok (Marco).
- **Wird jetzt gefixt (Marco):** Installer schreibt /etc/h713/board bei Neuinstallation ueber eigenem Layout
  nicht. Ohne Geraete-Retest, mit Tests.
- Lampen-Pulsieren beim Boot: 0 in 10 Kaltstarten (erledigt).
- **Webpanel, Warp-Schalter** (Marco 04.10. am HY300): "Warp on" im Panel antwortet "ok on -- the identity needs no
  GPU: h713-tv is on the ring (M10)" und der Schalter zeigt danach weder an noch aus. Ohne Keystone und Zoom ist
  der Warp absichtlich im Bypass; die Seite muss den Zustand verstaendlich zeigen (an, aber nichts zu zeichnen)
  statt einer Entwicklermeldung. Zur Webpanel-Runde.
- **Installer:** die Board-Datei traegt seit 723e803 die Firmware-Variante; Geraete mit einer Board-Datei vom
  alten Namen (hy300pro-g-eu, vor der Zusammenfuehrung) werden nicht abgebildet - Marco: egal, Datei neu setzen.
- **Webpanel-Bugs vom HY300 (Marco 04.10. 15:2x), zur Webpanel-Runde:**
  - Preset-Wahl und Einzelregler (Helligkeit usw.): die Regler folgen dem Preset mal, mal nicht - verbuggt
    (Wunsch "Preset zieht die Einzelregler mit" seit 23.09., doku/131).
  - Aspect-Knoepfe komplett ohne Wirkung.
  - "After a move" wird am HY300 angeboten, obwohl es dort laut Marco kein Auto-Keystone gibt (Stock hat keines;
    der SC7A20 ist da). Entscheiden: ausblenden oder anbieten.
  - "Auto now" (Keystone): braucht keine Kamera, nur den Neigungssensor - laeuft also auch am HY300; ob es dort
    gewollt ist, gehoert zur Frage davor.
- **Spaet:** Keystone-Automatik-Algorithmus verbessern (HY310) - Marco: auf jeden Fall, aber nach den wichtigeren
  Punkten.
- **HY300 Bluetooth nach Kaltstart:** der erste Start von h713-bluetooth scheitert (hci0 nicht UP nach 10 s), der
  systemd-Neustart nach 5 s klappt (hci0 bei 26,7 s). Ursache vermutlich FB-BTRESET 9.3 (unvollstaendige 245-Byte-
  Schreibvorgaenge am GEU, RTS/CTS). Funktioniert, kostet ~17 s. Am HY310 klappt der erste Versuch.
- **Fernbedienung nach Kaltstart (beide Geraete):** h713-remote-pair versucht alle ~25 s zu verbinden und meldet
  "InProgress"/"no answer", bis eine Taste gedrueckt wird - dann ist sie da. Verhalten wie Stock (Taste weckt),
  die Fehlerzeilen im Journal sind aber laut; pruefen, ob der Waechter bluez' eigene Autoverbindung stoert.
- **Neu (Marco 04.10. 16:3x), groessere Ziele:**
  - **Desktop:** eine grafische Oberflaeche auf dem Beamer (heute: Konsole oder HDMI-Bild, kein Desktop).
  - **Media-Beschleunigung komplett:** Video-Dekoder (Cedrus/VPU, H.264/H.265/VP9, AV1 sofern die Hardware es kann)
    und die Mali-GPU (panfrost, laeuft schon fuer den Warp) als Matrix ueber alle Formate; Abgleich mit cstengers
    h713-display-video-path (doku/124: Dekodieren/Abspielen dort "spaeter").
  - **Kodi mit Beschleunigung:** Kodi auf GBM/DRM, Dekodierung ueber V4L2-request (Cedrus), Ausgabe auf die
    Video-Plane; haengt an den beiden Punkten davor.
- **HDCP 1.4, Stand 04.10. 16:5x:** Fuse-Lesung am HY300PRO-G-EU gemacht: RSSK und SSK NICHT gebrannt, HDCP-PKF
  (Bit 21) GEBRANNT; am HY310 alle drei nicht. Damit ist die Lesung bestaetigt (sie unterscheidet Geraete), und der
  RSSK-Weg ist auf beiden Geraeten nicht der Weg von Stock. Naechste Schritte: im Stock-Code (BL31/OP-TEE/
  libhdcp) nachsehen, was mit gesetztem HDCP-PKF passiert; Stock-Android am HY310 mit einer 1.4-Quelle (Marcos
  Erinnerung). Details doku/143 16:5x.
- **HY310 Secure Storage nicht unberuehrt? (Marco 04.10.):** Marco vermutet, die erste HY310-Sicherung vom 10.09.
  wurde zu spaet gezogen, nachdem etwas den Secure Storage schon neu erzeugt hatte. Dann sagt die HY310-Lesung
  nichts ueber den Werkszustand. Fuer den HY310 nur mit einem fremden, unberuehrten Abzug zu klaeren ->
  in einem Issue/Forum fragen, ob ein HY310-Besitzer vor jedem Eingriff einen Vollabzug (oder nur die
  Fuse-Flag-Lesung mit unserem Mess-Proper) beisteuern kann. Fokus HDCP 1.4 jetzt nur am HY300 (Marco).
- **HDCP 1.4, Stand 17:5x (FB-HDCP14e):** Bit 21 = HDCP-2.2-Flag, nicht 1.4; RSSK (Bit 17) auf beiden Geraeten 0; kein
  fehlender Software-Schritt. Offen ist nur noch der entscheidende Test: eine 1.4-Sitzung unter Stock-Firmware (Marcos
  Erinnerung). Am HY300 ginge das ueber den Vollabzug zurueck auf Stock, Test, danach Neuinstallation (Marcos Wort).
- **Aus Stock-Android am HY300 beobachtet (Marco 04.10. 17:xx), als Todos:**
  - Modus-Anpassung: Android stellte eine 2160p-Quelle selbst auf 1080p um (blauer Uebergang, Anzeige) - eine
    eigene Kompatibilitaetserkennung. Nachsehen, wie Stock das macht (EDID-Angebot, Wechsel bei Nicht-Rasten), und
    ob h713-tv das auch kann.
  - Standby unter Stock beobachten (was Android beim Einschlafen und Aufwachen tut) - Eingang fuer den geparkten Standby.
  - Tipp Marco: auf Stock gibt es per ADB ein Entwicklerwerkzeug zum Lesen von Registern (Name aehnlich "hidreg") -
    fuer Register-Vergleiche Stock gegen unser System.

## Nachtrag 04.10. 17:1x - HDCP 1.4 geht unter Stock, und drei neue Punkte von Marco
- **HDCP 1.4 (korrigiert, hohe Prioritaet):** Unter Stock-Android authentifiziert der HY300 in 3 s (i915 "Enabled",
  zweimal). Die Hardware kann es, der Schluessel ist da - der administrative Fuse-Flag (Bit 17) sagt 0 und ist
  trotzdem nicht das Kriterium. Offen: was den Schluessel unter Stock an die Engine bringt und unter unserer Kette
  nicht. Naechste Schritte am laufenden Stock-System (Geraet ist JETZT auf Stock): per adb die CE-/SID-Register
  waehrend und nach einer 1.4-Sitzung lesen und mit unserem Zustand vergleichen; das Zeitfenster BROM/boot0 (das
  unsere SPL belegt) ist der Hauptverdaechtige. Danach FB-HDCP14e weiterfuehren.
- **Registerlesen per adb unter Stock (Marcos Tipp):** der Hersteller hat ein Entwicklerwerkzeug im Android gelassen
  (Name ungefaehr "hidreg" oder aehnlich), mit dem sich MMIO-Register lesen lassen. Suchen (`adb shell ls /system/bin
  /vendor/bin | grep -i reg`) und fuer den HDCP-Vergleich oben nutzen - das ist der direkteste Weg an den
  Stock-Zustand.
- **Androids Aufloesungs-Rueckfall (Marco 04.10.):** Stock stellt erst 2160p ein, erkennt dass es nicht geht, und
  faellt selbstaendig auf 1080p zurueck - mit Anzeige. Unser System hat so etwas nicht (es nimmt, was die
  Firmware-Tabelle sagt, und meldet einen Raster ausserhalb). Ansehen, wie Android das macht (welche Quelle es
  prueft, woran es "geht nicht" erkennt), und ob wir eine aehnliche Kompatibilitaetspruefung wollen.
- **Androids Standby ansehen (Marco 04.10.):** solange das Geraet auf Stock laeuft, den Standby-Weg beobachten
  (was abgeschaltet wird, was weiterlaeuft, wie geweckt wird) - Material fuer das Schein-Standby und fuer den
  geparkten PSCI-Suspend (doku/139).
- **HDCP 1.4, Spur gefunden (04.10. 17:3x):** Unsere TF-A setzt in sunxi_security_setup() alle SPC-Ports auf
  nicht-sicher; Stock laesst mehrere Ports sicher. Verdacht: der CE-Port gehoert dazu, und der SID-Key-Bus liefert
  den RSSK nur an einen sicheren Master. Naechster Schritt: herausfinden, welcher Port/Bit die Crypto Engine ist
  (SPC unter unserer Firmware lesen und mit der Stock-Karte vergleichen), diesen Port im BL31 sicher lassen,
  BL31 bauen, RSSK-Probe am HY300 wiederholen. Belege: umbau/work/FB-HDCP14e/stock-live/.
- **Geraetezustand HY300:** laeuft auf Stock-Android mit Magisk-Root (boot_a gepatcht, vbmeta_a Pruefung aus).
  Rueckweg jederzeit: Vollabzug re/device-dumps/hy300pro-plus-marco/emmc-full.img, oder TEST-Abbild
  umbau/build/release-v0.96-beta-geu-TEST. FEL unter Android: `adb reboot efex`.
- **HDCP 1.4, Stand 04.10. 19:00 (Spur bis zum Ende verfolgt):** Die Hardware kann es (Stock authentifiziert in
  Sekunden, zweimal gemessen). Ausgeschlossen: eFuse-Lage, SPC, Takte, der ganze RSSK/Crypto-Engine-Weg, und
  Software zur Laufzeit (Stock macht beim Handshake KEINEN einzigen Aufruf). Uebrig: unser U-Boot patcht die
  Warteschleife der Laderoutine in der Display-Firmware auf Null, dadurch scheitert der Schluesselladevorgang beim
  MIPS-Start dreimal und niemand wiederholt ihn. ZU TUN: U-Boot ohne diesen Patch bauen und pruefen, ob die Ticks
  beim MIPS-Start inzwischen laufen (sonst Ursache dafuer suchen: Takt/Gate/Reihenfolge vor dem MIPS-Release),
  dann Quelle fragen. Treiber-Erweiterung THal_Vp_HDMI_ReloadHdcp14Key liegt als Diff bereit
  (umbau/work/FB-HDCP14e/0183-hdmirx-reload-hdcp14-key.diff), gehoert aber nicht in den Handshake.

## Nachtrag 04.10. 19:xx - HDCP 1.4 korrigiert, und ein Release-Nebenbefund
Der 19:00-Eintrag oben ("Uebrig: unser U-Boot patcht die Warteschleife ... ZU TUN: U-Boot ohne diesen Patch bauen")
ist UEBERHOLT. Vollstaendig in doku/143 Abschnitt 14, Belege in umbau/work/FB-HDCP14e/sink-test/REPORT.txt.
- **Stock laedt den 1.4-Schluessel doch, still und im Bootloader.** `keybox_list` der Stock-Env endet auf `hdcpkey`;
  die Keybox-Schleife ruft dafuer `push_hdcp_key()` auf, das SMC Op 2 und dann Op 5 macht (OP-TEE
  `sunxi_load_hdcp_key`: 288 Bytes, key-select 3, in die Senke 0x03041400). Der Pfad druckt auf Erfolg nichts;
  "down hdcp 1.4" gehoert zum Burn-Pfad. In Marcos HY300-Mitschnitt fehlt jede Fehlerzeile zu `hdcpkey`, und
  Fehlschlaege drucken auf Level 0 - Op 5 ist dort also gelungen. Zeitlich liegt das vor dem MIPS-Start
  (Keybox [02.17], display_bin [02.9-03.1]) - genau Marcos Erinnerung.
- **Der echte Senken-Lauf ist jetzt gemessen und scheitert auch.** Am HY310 mit einem Testbau, in dem das Gate in
  BL31 und Treiber geloest ist: `HDCP 1.4 transfer into the key sink: ESR 0x11, 13126 us`. Alle frueheren
  ESR-0x11-Messungen waren die DRAM-Probe (FB-HDCP14c Abschnitt 7: "none targets the key sink"); der echte Lauf
  war nie versucht worden. Das Ziel ist damit als Erklaerung ausgeschlossen. 2 warme Reboots, 0 Stromzyklen,
  Flaeche byteidentisch zurueckgebaut, Geraet wieder auf dem Release.
- **Das Item ist 320 Bytes, nicht 288** (288 Chiffretext + 32 Bytes SHA-256). Unser SiP und h713-ce weisen alles
  ausser 288 mit -EINVAL ab; mit dem vollen Item haette der Weg nie funktioniert. Beim naechsten Anlauf die ersten
  288 Bytes nehmen, wie Stocks `keybox_get` es tut.
- **Offen ist jetzt die sichere Welt**, nicht das U-Boot: Stocks Op 5 gelingt unter monitor.bin + OP-TEE, derselbe
  Vorgang aus unserem EL3 scheitert auf beiden Geraeten. OP-TEEs eigene Initialisierung wurde nie untersucht
  (Abschnitt D der Ranges-Datei hat nur den Lade-Pfad geprueft). Dazu unbeachtet: OP-TEE Op 7 ist ein zweiter,
  PKF-basierter Weg (Schluessel aus dem SID-Schatten, normales AES, kein Key-Bus); der Stock-U-Boot ruft ihn nicht.
- **Naechster Schritt, lesend und billig:** am HY300 im Stock-U-Boot-Prompt die Logstufe fluechtig hochsetzen (kein
  saveenv, kein eMMC-Schreibzugriff, UART haengt schon dort) und einmal booten - dann erscheint "load key hdcpkey
  with default cb" und der Zweig ist bewiesen.
- **[M] Release-Nebenbefund, vor dem Push zu entscheiden:** die a-Bootkette ist fuer Fremde nicht reproduzierbar.
  TF-A nimmt `BUILD_STRING ?= $(shell git describe ...)`; im Container scheitert `git describe` in Klon und
  Worktree (dort ist `.git` eine `gitdir:`-Datei), in umbau/src nicht. Das Release-BL31 traegt daher einen leeren
  BUILD_STRING, ein Bau aus einem GitHub-Klon traegt `dfa9fab44` - anderes bl31.bin, andere a-Bootkette. Der
  E1-Doppelbau konnte es nicht sehen, weil beide Baeume denselben kaputten Verweis hatten. RELEASES.md sagt
  "reproducible". Fix klein (BUILD_STRING in mainline/build/build.sh deterministisch setzen) - jetzt oder
  Folgearbeit mit einer ehrlichen Zeile. Details doku/143 Abschnitt 14.4.

## Nachtrag 05.10., 05:5x — zwei Punkte VOR dem Release (WLAN-Start)

**V1 — festes Start-Timeout für `h713-wifi` (gefixt, unverifiziert).**
`h713-wifi.service` ist `Type=oneshot`, und dafür ist systemds Standard
`TimeoutStartSec=infinity`. Weil das Unit `Before=network.target` steht, hält ein im Kernel
klemmendes Funkmodul den gesamten Netzpfad unbegrenzt auf: das Gerät bekommt keine Adresse
und ist nicht per ssh erreichbar. Gemessen am 05.10.: `Job h713-wifi.service/start running
(3min 58s / no limit)`, Gerät stumm im Netz, Linux ansonsten hochgelaufen.
Eingetragen in `rootfs/overlay/etc/systemd/system/h713-wifi.service`:

    TimeoutStartSec=60

Die Warteschleife im Skript selbst war nie das Problem (Interface-Wartezeit ist auf 30 s
begrenzt). **Zu tun vor dem Release:** Rootfs neu bauen und einmal mit absichtlich gestörtem
Funkmodul booten — das Gerät muss durchbooten und erreichbar sein, das Unit darf scheitern.

**V2 — `modprobe` des AIC8800 begrenzen (gefixt, unverifiziert).**
Der eigentliche Hänger sitzt unter dem Skript: `modprobe` des AIC-Treibers blockiert im
Kernel und ist von aussen nicht abbrechbar. Ursache war ein verklemmter SDIO-Zustand nach
mehreren harten Resets:

    aicbsp: sdio_err:<aicwf_sdio_hal_irqhandler,1891>: Interrupt but no data

Beide `modprobe`-Aufrufe in `rootfs/overlay/usr/local/sbin/h713-wifi` laufen jetzt unter
`timeout 30`. **Zu tun vor dem Release:** prüfen, ob der schlechte Interrupt eine eigene
Ursache hat (Taktung/Reset-Reihenfolge des Chips) oder nur Folge der Reset-Serie ist - und
ob ein `h713-bt-reset`-artiger Vorlauf den Zustand sauber aufräumt.

## Nachtrag 05.10., 06:0x — HDCP 1.4: der Installer muss den Wickelschlüssel ablegen

Die Kette ist entschlüsselt (FB-HDCP14h/REPORT.txt, „DIE KETTE IST ENTSCHLUESSELT"): das
Entpacken des gespeicherten `hdcpkey`-Datensatzes ist ein **gewöhnlicher key-select-0-Task**
mit einem festen 16-Byte-Schlüssel aus dem Trusted OS (`sym_ctl 0x100`), **nicht** mit dem
eFuse-Schlüssel. Nur der Push in die Senke braucht key-select 3, und der läuft aus unserem
BL31 (gemessen 05.10.: `HDCP 1.4 transfer into the key sink: 0x0`).

**Entscheidung, die so bleiben soll:** die 16 Byte kommen **nicht** in dieses Repository. Sie
sind ein DRM-Geheimnis des Herstellers; sie auszuliefern wäre Verbreitung von
Umgehungsmaterial und hilft niemandem, dessen Gerät einen anderen Schlüssel trägt. Unser
U-Boot liest sie zur Laufzeit gerätelokal:

1. `/boot/h713-keybox.key` (16 Byte) — der bevorzugte Weg
2. sonst das Trusted-OS-Abbild des Geraets an der gemessenen Stelle

**Zu tun vor dem Release:** der Installer hat beim Installieren das Stock-Abbild des Nutzers
in der Hand (`bootloader_a.bin`, Item `optee` bei `0x0dc000`, 275328 Byte). Er soll daraus die
die 16 Byte an der gemessenen Stelle lesen und als `/boot/h713-keybox.key` mit `0600` ablegen —
einmal, gerätelokal, nie in ein Abbild oder Release. Ohne die Datei fällt `h713_hdcp14`
sauber auf „kein Wickelschlüssel" zurück und das Gerät bootet normal, nur ohne HDCP 1.4.

## Nachtrag 05.10., 06:1x — VOR DEM RELEASE: Konfiguration der HDCP-Teile prüfen

Beim Nachtlauf ist aufgefallen, dass ein Bau aus dem **nackten `hy310_defconfig`** (ohne
Rollen-Fragment) **nicht bootet**: `bootm` bricht mit

    Uncompressing Kernel Image to 48000000
    Unable to allocate memory 0x48000000 for loading OS

ab, während derselbe BL31 im Baum `uboot-O-hy310dbg` (mit Fragment) durchläuft. Das Fragment
trägt also etwas, das für den Kernelstart nötig ist, und es ist **nicht** im Basis-defconfig.

**Zu tun vor dem Release, zwingend:**
1. Herausfinden, welche Option das ist (Verdacht: `CONFIG_SYS_BOOTM_LEN` oder eine
   lmb-/Reservierungsoption) und sie dort hinschreiben, wo sie hingehört — nicht nur ins
   Fragment. Ein Release-Bau darf nicht davon abhängen, aus welchem O-Verzeichnis er kommt.
2. Gegenprüfen, dass die neuen HDCP-Teile in **jeder** gebauten Rolle enthalten sind:
   * `arch/arm/mach-sunxi/h713_hdcp14.o` hängt jetzt an `CONFIG_H713_MIPS_BOOT`
     (vorher fälschlich an `CONFIG_SUNXI_TEE`, was ohne Secure Payload zu
     `undefined symbol: h713_hdcp14_install` führte)
   * `sunxi_h713_sip.c` in BL31 und `PLAT_XLAT_TABLES_DYNAMIC`
   * `-DBL32_BASE` nur wenn ein Secure Payload gebaut wird (`ifneq (${SPD},none)`)
3. Einen Bau je Rolle einmal bis Linux booten, nicht nur übersetzen.
