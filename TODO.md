# TODO — die eine Liste

**Die einzige Todo-Liste dieses Projekts.** Neue Punkte hierher; erledigte nach §10 — nicht löschen.
Changelog ist [RELEASES.md](RELEASES.md). `known-issues.md` und `ROADMAP.md` beschreiben dem Leser,
was nicht geht und wohin es geht — sie führen keine Arbeit. Gestartet 05.10.2026 aus `doku/151`.

## 1 Release — in dieser Reihenfolge

- [x] 1.1 Test-Images gebaut 05.10. 20:36: `installer/out/h713-hy310-v0.96-beta-{a,b,c}.img`, Check 10/11
      „everything in order" (inkl. `check-hdcp-artifacts.sh`). Drei Bau-Stolpersteine dabei behoben:
      0183 kompilierte nicht (`c5f2f5e`), Sysroot-Wiederverwendung ohne Paketprüfung, `doku-index`
      zählte Bauausgaben (`eebb33e`)
- [ ] 1.1a **Release-Neubau** mit allem seit dem v0.96-Bau vom 05.10. (Baustand `be4f8e1`; der alte Hash `819a09a` ist seit dem
      Identitäts-Rewrite unerreichbar): Kernel 0184/0185 und pwm-sun8i (`5e4475a`), Warp (Zoom, Moduswechsel,
      Stale-Schwelle, Import), EDID-Beschnitt, Panel (Auth, Zoom-Schieber), h713-tv (Aspect zoom), Installer-Texte, die neu
      erzeugte Kernel-Serie; vorher die zwei Patches aus `arbeit/hdcp-wait-env-20261007/patches/` (6.6: U-Boot in den Fork,
      Spiegel `uboot-h713/` neu, `check-hdcp-artifacts.sh`). In einer Kopie, Gerät vorher sichern, Bauverzeichnisse von vorn.
      Dazu das HDCP-Härtungspaket (6.1/6.2/6.5/6.9, `arbeit/hdcp-haertung-20261007/`, enthält 6.6 schon als `uboot/0001`):
      erst per FEL messen (Plan dort §8, BL31 vorher frisch bauen), TF-A und U-Boot nur zusammen; danach `referenz/messregeln.md`
      HDCP und `docs/subsystems/hdcp.md` (eine Schreibung pro Boot, keine Adresse)
- [x] 1.2 HY310: 5 Kaltstarte + HDCP-Paar mit dem v0.96-beta-Abbild (Marco: statt 22 Zyklen), 05.10. 20:50–21:07,
      Ergebnisse in `doku/142` (Abschnitt 05.10. abends): 5/5 gebootet, 0 failed, wipe→Desired, push→Enabled,
      WLAN ~9 s, 720p+Warp richtig, BT UP. Auffälligkeit Z4: ein zweiter Boot ohne Spur → 1.2a
- [ ] 1.2a **Z4 zweiter Boot** (~80 s nach Strom-an, Ursache unbekannt, Journal war flüchtig - **06.10.: ist es im
      Abbild weiter**, `10-h713.conf` `Storage=volatile` schlägt `/var/log/journal`, `doku/155` §3): Journal im
      Abbild persistent machen (`/var/log/journal`), ggf. pstore/ramoops, 5 weitere Kaltstarte beobachten
- [ ] 1.2b **Reinstall über unser Layout verwirft `/etc/h713`** (wifi.env → AP-Modus, warp.conf, keystone,
      tvconfig): der Installer soll die Nutzer-Einstellungen wie die 44 Herstellerdateien zurücklesen und
      übernehmen — oder `build-all.sh --wifi-env` ist Pflicht. Bis dahin: Sicherung vorher (`/root/pre-v096`)
- [ ] 1.3 **WLAN-Timeouts verifizieren** (`82cb57e`): im Abbild drin, 5 Boots je ~9 s bis Finished — der Hängefall
      (Funk absichtlich verklemmen) ist noch nicht provoziert
- [ ] 1.4 HY300 Pro G-EU (`boards/hy200-qz713df-a1`): Boot, Bild, HDCP 1.4 mit geteiltem Satz, 2.2 (Marco 06.10.:
      später). Dazu Bluetooth dort: erster Attach nach Kaltstart hängt an `0x1003`, 245-Byte-Schreibvorgänge kommen
      unvollständig an (FB-BTRESET 9.3, RTS/CTS?); `h713-bt-reset` auf dem Board noch nie probiert
- [ ] 1.5 STAGE4-Marker füllen und löschen (`git grep -n STAGE4`)
- [ ] 1.6 Forks pushen: U-Boot `h713-hy310` +6, TF-A `sun50i-h713` +1 (`4c1bd8c6`, der HDCP-1.4-Dienst), sunxi-tools gleich
      — **vor** `main` (06.10.: Submodul-Remotes per `git submodule sync` wieder auf GitHub - TF-A und sunxi-tools
      zeigten auf einen geloeschten lokalen Pfad; Identitaets-Hooks gelten jetzt auch in den Forks. Der S-EL1-Versuch
      `824eb0bd` ist aus Fork-Branch, Spiegel und Zeiger raus (Marco: "el1 weg, Hauptsache HDCP funktioniert");
      BL31 mit und ohne ihn bytegleich gebaut, `doku/153`; der Beleg-Branch ist seit 07.10. gelöscht - Marco: S-EL1 nicht
      gewollt, `doku/160`)
      Beim selben Push den alten GitHub-Branch `origin/hy300-pro-ab` loeschen (Marco 06.10.: ja; Inhalt ist in `main`, 7.8)
- [ ] 1.7 `main` pushen (06.10. +113; aktuell `git rev-list --count origin/main..main`)
- [ ] 1.8 `RELEASES.md`: neuer Abschnitt; Release-Tag; Baustempel
- [ ] 1.9 `docs/known-issues.md` Zeile „HY300 Pro dunkel" nach test10-Foto

## 2 Am Gerät offen (keine Blocker, aus `144` §2 und known-issues)

- [x] 2.1 **Zoom** (Marco 04.10.: „bringt das Gerät durcheinander") - 06.10. behoben, `doku/155`: der Aspect „zoom"
      (Firmware-Modus 5) legte den Bildweg lahm, auch gespeichert beim nächsten Start -> Kernel 0185, h713-tv lehnt ab,
      Panel ohne; der Zoom-Schieber kippte schiefe Trapeze -> rechnet jetzt durch die Trapez-Homographie und schaltet
      unter 100 % den Warp ein. Von Marco an der Wand abgenommen
- [x] 2.3 Bluetooth nach warmem Reboot: erster HCI-Befehl verloren (2 von 5 mit der alten Unit) - **abgefangen**
      (Marco 06.10.: vorerst schließen): seit `h713-bt-reset` vor dem Attach 0 Ausfälle in 7 warmen Reboots, jedes Mal
      Reset auf Versuch 1 und `hci0 UP after 0 ms` (`doku/156`). Die Ursache bleibt offen -> **9.12**, nach dem Release
- [x] 2.4 HDCP 2.2 Session-Beweis: Fire-TV-Stick am HY310, 05.10. — `h713-tv ctl hdcp` meldet
      „2.2 (session stands), authenticated: yes", Firmware-Log zeigt SKE_SEND_EKS; über acht
      Moduswechsel (1080p60 ↔ 720p50/60) jedes Mal neu authentifiziert. Beide Schlüssel sitzen
      (1.4 aus U-Boot, LINK 0x93=0x45; 2.2 vom Kernel beim Probe)
- [x] 2.4a **720p-Quelle + Warp: Bild doppelt und gestaucht** (Fire TV 720p60, 05.10.). Der
      Warp-Frame selbst ist sauber (`h713-warp ctl dump`), ohne Warp ist 720p sauber — also
      liest der Kompositionsblock der Firmware den 1920er Warp-Puffer weiter mit dem
      Ring-Stride 1280 (Patch 0107: „nothing behind the reader gets reprogrammed"; dort als
      „not yet measured on the wall" markiert — jetzt gemessen). Fix-Kandidaten: beim Wechsel
      Ring→FB den Descriptor mit FB-Geometrie publizieren und WCE abwarten (afbd), oder den
      Warp in Quellgröße rendern lassen. Vor dem Release entscheiden — trifft jede
      Nicht-1080p-Quelle mit Keystone
      → Prüfstand 05.10. (`/opt/Projekte/h713/arbeit/warp-pruefstand/BERICHT.md`): Ursache gemessen,
      der Kernel verweigert das Neuschreiben des VidDec-Descriptors außerhalb des Ring-Modus
      (`afbd.c:602`); Fix Kernel-Patch 0183. **Hardware-Test offen:** 720p + Warp, dann
      Signalereignisse erzwingen (HDCP-Neuverhandlung, Aussetzer) — übersteht die Capture das?
      Das war der Grund der alten Regel. Kamera als Auge: `kamera-gitter.py`
      **05.10. 20:30 am Gerät bestanden:** Kernel mit 0183 per Schnell-Deploy (FIT + Module +
      Daemons, Sicherung `/root/sicherung-vor-0183/`); Register folgen dem Puffer (Komposition
      0x05000444 = 1920x1080, Skalierer 1920x1080, Descriptor 1920 1080 … 1920), Kamera: ein Gitter;
      sechs Moduswechsel mit Signalabriss → neun saubere Republishes (Ring ↔ Framebuffer), kein
      „did not reprogram", 56 fps. Offen: HDMI-Stecker ziehen/stecken, 720p50/1366x768 als Quelle
- [ ] 2.4b **Warp kennt kein Seitenverhältnis:** zieht jede Quelle auf das Quad; 4:3-Quellen
      (1024×768, 1280×1024, 576p) werden mit Warp breitgezogen, ohne Warp pillarboxt die Firmware.
      Fix: Letter-/Pillarbox im Quad aus dem Capture-Format (h713-warp), noch nicht gemessen
- [x] 2.4e **Warp-Flackern bei Ringen mit Zeilenabstand ≠ 64er-Vielfaches** (480p, 576p, 1366×768, 1280×1024 …):
      Panfrost lehnt den Slot-Import ab, der Warp versuchte es jede Sekunde neu und nahm dabei jedes Mal den
      Plane (47 Republishes/min, Wand blinkt, erster Frame grün). Jetzt Import **vor** dem Claim und kein
      neuer Versuch bis zur nächsten Ring-Geometrie — gemessen 05.10. 22:02: 0 Republishes, Bypass still
      (Einzeltest `arbeit/edid-sweep-20261005/`). Offen: Keystone für diese Modi (CPU-Kopie in einen
      64-aligned Puffer, oder Firmware-Ring breiter) → 2.4f
- [ ] 2.4f Keystone für Ringe mit unausgerichtetem Pitch (SD- und PC-Modi): Warp braucht einen 64-aligned Import
- [x] 2.4g Warp bei 24/25-Hz-Quellen = schwarze Wand: der feste 28-ms-Stale-Schutz warf jeden gehaltenen Slot
      zurück (Slots kommen bei 24 Hz im 34/50-ms-Takt; 334 stale, 0 Frames). Schwelle folgt jetzt dem gemessenen
      Slot-Abstand (×1,25, nie unter 28 ms). 05.10. 22:12: 1080p24 → 24,0 fps, p25 → 25,0, p30 → 30,0, p60 → 59,4,
      0 Drops; Kamera: Bild da
- [x] 2.4c 1366×768 (Pitch 1376): gemessen 05.10. — rastet, Warp geht in den stillen Bypass; ist derselbe
      Ausrichtungsfall wie 2.4e/2.4f, kein eigener Punkt mehr
- [ ] 2.4d Prüfstand-Kleinfunde (BERICHT §2.2–2.12) — **erledigt 05.10.:** `ctl status` wirft den Warp ab
      (Frist 1000 ms), Journal-Spam ohne Signal, `test mask` markiert tl, Firmware-Zoom im Warp-Commit
      (h713-tv-0001 + 0183). **Offen:** laxe `atoi`-Prüfung bei zoom/edge, `check` halbiert fps
      (dokumentieren), Musterwechsel = Konsolenblitz, Client ohne Newline blockiert 500 ms,
      `evaluate()` gibt bei -ENOLCK sofort frei, Textreste „primary plane"
- [ ] 2.5 HY300-Lampe: Testplan `doku/143` §11 (Foto gegen Stock, PWM-Block lesen)
- [ ] 2.6 Audio: Abschalt-Plopp -> **9.11 (spaet)**, Messungen und widerlegte Hypothese dort
- [x] 2.7 Geometrie: Ceiling-Beweis kopfüber; Kalibrierkarten in gespiegelten Modi - 06.10., `doku/157`: Karten und
      Bild in allen vier Modi richtig (Fotos gedreht statt Beamer, Marco); beim Moduswechsel blieb das Trapez nicht am
      Gehäuse -> `ctl mode` sortiert die Ecken jetzt um wie Stocks `setKeystoneNormalXY`, Rahmen in allen Modi
      deckungsgleich. Nicht gemessen: die Automatik mit wirklich kopfüber liegendem Sensor
- [ ] 2.7a **Konsole durch den Warp** (aus 2.7, Marco 06.10.: bleibt offen): ohne Signal zeigt h713-tv die Konsole auf
      der primären Ebene, ohne Trapez und ohne Spiegelung - im ceiling-Modus steht sie auf dem Kopf. Wege: fbcon
      `rotate_all = 2` für ceiling (nur Drehung, kein Spiegeln), Firmware-Spiegel per RPC (FB-MIRROR 2.3/F3) oder der
      Warp liest `fb0` als Textur und zeichnet die Konsole mit (wie Stock, eigenes Paket)
- [x] 2.8 Autofokus: eine Wand, ein Abend; Metrik-Spanne nur +11 % (Belichtung) - **gestrichen 06.10. (Marco)**. Der Autofokus
      ist abgenommen (`doku/134` A4, Läufe enden scharf); weitere Wände und die Schärfekurve werden nicht gemessen.
      Ungeprüfte Deutung der +11 %: Läufe starten nahe am Fokus, das Optimum ist ein flaches Plateau
- [ ] 2.9 Keystone: Langlauf 05.10. ~8 h Warp an, 59 fps, RSS flach, 20× an/aus ohne Leck (Prüfstand) — der
      Langlauf-Teil ist erledigt; offen: automatische Korrektur ohne `/etc/h713/keystone-ref` gegen Ideal-Pose
- [ ] 2.10 EDID: 1080p100/120 weiter hinter `ctl edid block1` (Entscheidung offen). **Geklärt 05.10.:** 1600×900,
      1920×1200, 1600×1200, 2560×1600 und 1024×768i rasten nicht, weil die Firmware-Tabelle sie nicht kennt —
      unsere EDID bietet sie auch nicht an (der i915 generiert sie selbst); kein Fehler unsererseits
- [x] 2.10a Interlace-VICs 7, 6, 21 (480i/576i) aus unserer EDID, die die Firmware nicht rasten kann: h713-tv
      beschneidet jede veröffentlichte Hälfte um die SVDs ohne Tabelleneintrag (`edid_prune`) und veröffentlicht
      die servierte Hälfte beim Start einmal so, wenn nötig (ein HPD-Puls). Am Gerät 05.10. 21:30: 17 VICs offered,
      all in the firmware's table; ThinkPad bietet 720x480i/576i nicht mehr an; Programmneustart = kein zweiter
      Puls (`c33df12`). Offen: `1024x768i` (Established Timing im Basisblock, kein SVD) — rastet das?
- [x] 2.11 `backlight_level` / `dynamic_backlight` ohne Wirkung — Firmware nimmt den Aufruf, Lampe ändert nichts - **geschlossen
      06.10.: die Lampe ist auf HY310 und HY300 nicht dimmbar**, auch unter Stock nicht (Marco); der Stock-Devicetree nennt
      PWM2/PB4, aber dessen Tastgrad 100..0 % ändert nichts (gemessen, cstenger ebenso: Dimmer nicht verdrahtet). Die Regler
      bleiben für Boards mit Dimmer (L018: drei Stufen, Lüfter folgt)
- [x] 2.12 AP-Latenzspitzen (3 ms ↔ 2 s bei −50 dBm, Durchsatz ok) - **06.10. nicht nachvollziehbar** (`doku/158`): Box als
      AP mit der ausgelieferten `wifi.env`, dieser PC als Client bei −47 dBm, Stromsparen der Box an: 100 Pings à 0,2 s
      1,2-124 ms, 60 Pings à 1 s 2,6-14 ms (Median 3,4), keine Spitze. Station-Modus 1-59 ms
- [x] 2.13 Settings-Seite Port 8080: seit 05.10. HTTP Basic Auth, Passwort beim ersten Start erzeugt (`/etc/h713/panel.env`,
      0600), `h713-panel --show-password`; am Gerät geprüft (401/401/200), 33 Tests grün. PIN auf der Leinwand → 9.x
- [ ] 2.14 Reinstall setzt Einstellungen und Fernbedienungs-Pairing zurück — heute selbst erlebt (wifi.env → AP-Modus),
      Lösung in **1.2b** (Installer übernimmt `/etc/h713`); Pairing bleibt zusätzlich offen
- [x] 2.15 `afbd`-Modultausch zur Laufzeit bringt kein neues Fenster (Firmware nimmt Republikation nicht) - **geschlossen
      06.10. (Marco): kein Nutzerfehler**, Regel: afbd-Änderungen per Neustart testen (`known-issues.md` behält die Zeile,
      gemessen 22.09. am HY300 Pro, `doku/128`). Eine echte Lösung käme mit 3.3
- [ ] 2.16 Frame während laufendem Commit wird verworfen (`ok busy`) — Prüfstand 05.10.: normal 2–5 busy auf
      100–16 000 Commits, einmal 31/59 bei 50-Hz-Quelle (Schwebung 50↔60 Hz). Design mit drei Puffern; nur beobachten
- [x] 2.17 Presets `computer`/`game`/`hdr` nie geprüft; Gamma 2,2 Sichtprüfung gegen Stock; Weißabgleich/CTM ohne Stock-Vergleich (aus `61`)
      - 06.10., `doku/159`: die drei Presets setzen am Gerät exakt die Herstellerdaten der Box, Bild intakt; Gamma ist die
      eigene Kurve der Box. Stock-Vergleich (Gamma, Weißabgleich/CTM) gestrichen (Marco: wird nicht getestet)
- [x] 2.18 `h713-pq brightness` sagt angeblich ohne Wirkung - laengst korrigiert: `model.py` sagt seit 11.09. (Plan 113 A.6)
      measured, effective mit Verweis auf nachtlog/I0; der Punkt aus `61` war ueberholt (05.10.)
- [x] 2.19 `h713-tv ctl replug` gibt es längst (HPD-Puls, S_EDID); „Plane liest Ring direkt' ist seit 0107/0117
      das Design (hdmi-ring-Modus), kein Mangel — Punkt aus `61` überholt (05.10.)
- [x] 2.20 Preset beim Start wählbar, Regler über Neustart merken; Startmodus `auto|manuell` merken (aus `61`) - seit Plan 113
      (Mitte September) im Code (`tv.conf` `start`/`preset`, `ctl save`); 06.10. am Gerät gemessen (`doku/159`): cinema +
      Helligkeit 55 + Startmodus off überleben einen warmen Neustart
- [x] 2.21 Kamera mit hellem Bild nie geprüft; WLAN-Station zwei Ecken offen; Telefon am AP (aus `61`/known-issues) - 06.10.:
      **Kamera erledigt** - über zwanzig Wandfotos der projizierten Leinwand mit der Box-Kamera (Belichtung 5000 / Gain 255,
      Luma im Mittel 60-110, Spitzen 255, Text und Rahmen erkennbar; `doku/155`, `157`, `159`). **WLAN-Ecken und Telefon am AP
      gestrichen** (Marco: nie relevant) - Android und das DNS des AP, zwei Standardrouten mit LAN-Adapter
- [ ] 2.22 eMMC: `data error cmd18` am GEU (einmal); **05.10. 23:03 am HY310:** ~2 min nach dem Boot haengt jeder
      Plattenzugriff (ls /boot, dmesg ueber Shell, Konsolen-Login), ssh/uptime antworten - Kernel 0184 frisch gebootet,
      Ursache offen, nach Stromzyklus alles normal, keine mmc-Fehler im Log. Beobachten; Journal ist persistent
- [x] 2.23 KEY_POWER-Politik (poweroff ueber logind, auch die BT-Fernbedienung; kein Standby) steht in
      `docs/hardware.md`; WLAN-Band der Koexistenzmessung in `doku/134` nachgetragen: 2,4 GHz Kanal 4, 5 GHz ungemessen
- [ ] 2.24 Kleinkram aus `61`: `regulatory.db` load failed -2; `r8152` will `rtl8153b-2.fw` - Marco 05.10.: **nicht
      jetzt**, Pakete `wireless-regdb`/`firmware-realtek` erst, wenn jemand sie braucht
- [ ] 2.25 **Linux bindet den Watchdog mit dem falschen Registerlayout** (Gegenprüfung der HDCP-Härtung 07.10., aus dem Code;
      gemessen schon 07.09., `doku/72` Z. 1633 ff.: der Treiber schreibt ohne Schlüssel und trifft nichts, der DT-Fix steht dort
      als „noch nicht umgesetzt"). Kernel-DT `watchdog@2051000` sagt `sun50i-h6-wdt`/`sun6i-a31-wdt` (CTRL 0x10/CFG 0x14/MODE 0x18,
      kein Schlüssel); die Hardware hat CTRL 0x0C/CFG 0x10/MODE 0x14 mit Schlüssel 0x16aa - wie U-Boots DT (`sun55i-a523-wdt`).
      Folgen: `RebootWatchdogSec=16s` (`customize.sh`) schaltet nichts scharf, obwohl `mainline/docs/status.md` und `roadmap.md` es
      sagen; unter Linux gibt es kein Hängernetz. Mit dem richtigen Compatible und `RuntimeWatchdogSec` wäre ein Hänger aus der
      Ferne behebbar, auch mit gestecktem USB-Kabel (Reset im SoC, kein Stromschnitt) - wichtig für Crust-/Standby-Nächte.
      Messen: Compatible tauschen (Modul/DT, in einer Kopie), `wdctl`, dann gezielter Hänger -> Reset? Auch prüfen, ob ein Hänger
      am ARISC-Hilfsblock (`irrwege.md`, 0x07091014) vom Watchdog überhaupt zurückgesetzt wird. Erst danach `docs` richtigstellen (`doku/161` §3)
      - 07.10. (`doku/164`): von Hand gesetzt wirkt er und setzt die Box auch mit gestecktem USB-Kabel zurück; Füttern = `0x14AF`
        nach CTRL. **Dazu TF-A härten:** der Ausschalt-Reset (`sun50i_h713/sunxi_power.c`, MODE = `key|1`) scheitert, wenn der
        Watchdog schon läuft - vorher MODE aus und CTRL anpingen

## 3 Geparkt — mit Wiedereinstiegsbedingung

- [x] 3.1 **Standby Stufe 2** (<1 W, ARISC, IR/CEC): PSCI-Suspend erreicht DRAM, **kein Wecken** (`doku/139`). FB-STANDBY + 0167c rein, wenn Wecken bewiesen
      - **gestrichen 07.10. (Marco)**: mit der Hersteller-ARISC-Firmware ist das eine Blackbox (eine Nacht, ~15 Proben, kein
      Wecken); echter Tiefschlaf, wenn überhaupt, über Crust (3.2)
      - 07.10., statisch, nicht gemessen (`doku/162` §2): der Blob liest beim DRAM-Ausgang seine DRAM-Werte aus `arisc_para`, und
        unser Treiber füllt den Block mit Nullen - ein möglicher Mitgrund für „Aufwachen nie". Bleibt gestrichen
- [ ] 3.2 FB-CRUST — nach Standby. **Weg (Marco 07.10.):** nach dem Release; zuerst Crust nur im Normalbetrieb (HDMI, EDID, HPD,
      MIPS-Kanal wie die Hersteller-ARISC; Rückweg = Dateiname, kein Flash, Testplan `FB-CRUST/REPORT.txt` §2), erst dann Schlaf.
      Tiefschlaf braucht zusätzlich die DRAM-Selbstauffrischung (in Crust nur entworfen) und das MIPS-Neuladen (3.3)
      - **07.10. als Paket vorbereitet, nicht gemessen** (`doku/162`, `arbeit/crust-20261007/`): crust für Normalbetrieb und
        Standby, DRAM-Selbstauffrischung und Tiefschlaf aus dem Blob portiert (Spuren gleich), Kernel 0186-0191, TF-A 0001-0004,
        U-Boot 0001, vier FEL-Abbilder, zwei Prüfrunden (41 + 17 Funde) behoben. Nächster Schritt **mit Marco in Reichweite**
        (kein Hängernetz, TODO 2.25): Phase 1 `skripte/phase1.sh 0..9` (~1 h), dann FEL `release-crust`, dann Standby A/B/C nur
        mit Marco an der Box. Offen: HDCP 1.4 nach Tiefschlaf (eine Senken-Schreibung pro Boot mit `doku/161`), CEC-Wecken
      - **07.10. am Gerät** (`doku/163`): Phase 1 (Normalbetrieb) und Phase 2 (TF-A startet crust) bestanden; Standby Stufe A
        wacht auf (erstes Aufwachen überhaupt), crust 0029 (EDID-Gate) und 0030 (Startadressen der Nebenkerne) am Gerät bestätigt.
        **Offen:** Stillstand ~0,1-16 s nach dem Aufwachen an wanderndem Ort; nächste Schritte offline: crusts Schlafpfad Register
        für Register gegen den Blob, BL31 nach dem Aufwachen GIC/Takte auf die UART ausgeben lassen, Kernel mit `CONFIG_PM_DEBUG`.
        Physische Adresse Port 0 wie der Blob (0.0.0.0). Läufe nur mit Marco in Reichweite oder mit einem von Hand gesetzten Watchdog
      - **07.10. Vormittag** (`doku/164`): Stillstand eingegrenzt - Hotplug über TF-A in Ordnung, Nebenkerne nicht schuld,
        **ohne cpu_comm/afbd wacht die Box vollständig auf**. Nächster Lauf: cpu_comm/afbd aus `*-0191.ko` (MIPS parken),
        Power-Taste per `systemd-inhibit` sperren (Herunterfahren nach dem Aufwachen, vermutlich `KEY_POWER` aus PL4), Hand-Watchdog
        vor jedem Herunterfahren aus
      - **07.10. 12:08 erster vollständiger Standby-Zyklus** (`doku/165`): mit geparkter MIPS (0191-Module) und gesperrter
        Power-Taste wacht die Box auf und läuft stabil weiter, alle vier Kerne wieder online. Offen: falscher `KEY_POWER` beim
        Aufwachen (gemessen, crust 0031 hilft nicht), MIPS nach dem Aufwachen neu laden (3.3), dann Stufe B/C und Taste/IR
      - **07.10. 12:47 Stufe B bestanden** (`doku/166`): Standby mit DRAM-Selbstauffrischung (crust-Bau `self-refresh`,
        Takt und PLL_DDR aus), 5 s Schlaf, Linux läuft danach stabil auf allen vier Kernen; `/` war read-only. Offen wie oben
        (`KEY_POWER`, 3.3), dazu Stufe C, Taste/IR, Leistungsmessung, längere Schläfe
      - **07.10. 13:46 falscher `KEY_POWER` behoben** (`doku/167`): crust 0032 löscht die Flanke von PL4 erst nach den
        Debounce-Abtastungen; C2 und C3 (Self-Refresh) ohne Tasten-Ereignis und ohne Interrupt. Offen: Wecken per Taste gibt
        weiter `KEY_POWER` (Regel in Linux/logind, Messung mit Marco an der Taste), 3.3, Stufe C (zuerst LOSC/32-kHz-Quarz
        prüfen), Leistungsmessung
- [ ] 3.3 FB-MIPSRELOAD/b — rein, wenn der Bildfehler nach Reload verstanden ist (`doku/138`) - löst 2.15 mit (Firmware nimmt nach einem afbd-Reload keine neue Publikation an)
- [ ] 3.4 IR FB-REMOTEb + fd02-Keymap — rein, wenn rx_resolution-Trunkierung / ARISC-Schreibpfad geklärt
- [ ] 3.5 `Reserve0_a/b` und `private` von einem **unangetasteten** Gerät abziehen (bei uns überschrieben) (aus `61`)

## 4 Boards und Fremdgeräte

- [ ] 4.1 `hy300-pro` (Issue #1): test10 aus `main` nach dem Release (0168, 0182, 2de0cc8, Gamma, project 0x34)
- [x] 4.2 `hy200-qz713-v2`: Layout-v4-Defconfig + eigener Baum **vor** jedem TEST-Image; Q5 tREFI - **gestrichen 06.10.
      (Marco)**: nur auf Anfrage eines Besitzers per Issue; die Beschreibung in `boards/` bleibt
- [x] 4.3 `hy200-qz713df-a1`: 09-22-Einheit unbekannt (eMMC, DRAM, Sensor, Kamera, Motor) → per-Variante-Overlay - **gestrichen
      06.10. (Marco)**: nur auf Anfrage per Issue. Die Firmware hat dieselbe Produktkennung (`h713_tuna_p3`) wie die des
      HY300PRO-G-EU, aber einen Fokusmotor im Devicetree - wohl dieselbe Platine, andere Bestückung; Beschreibung bleibt
- [x] 4.4 FEATURES der Boards ohne Besitzerbericht bleiben leer; `boards/check.sh` soll FEATURES-Namen prüfen - **gestrichen
      06.10. (Marco)**: drei von uns gepflegte Einträge, `h713-features` warnt am Gerät ohnehin; die Regel „leer ohne
      Besitzerbericht" wird eingehalten
- [x] 4.5 `boards/README.md`: Tabelle „welcher Ordner ist mein Gerät" (im README drin, dort nicht) - 06.10.: Abschnitt
      „Which directory is my projector?" mit der Tabelle aus dem README
- [x] 4.6 An cstenger zurückmelden: Composition-Befund (`89`), D1-CCU Port 1, SIDDQ, Doorbell im MIPS-Sendepfad (aus `61`) -
      **gestrichen 06.10. (Marco)**: er nutzt GitHub nur zum Verfolgen

## 5 Installer und Werkzeuge

- [ ] 5.1 ST3-RESTORE F1: Schema-Feld `layout.disk_sectors_from = unit|image` statt Heuristik
- [x] 5.2 `h713-hdcpkey` braucht eine `docs/tools/`-Seite - 06.10.: `docs/tools/h713-hdcpkey.md` (Beispiel aus einer synthetischen
      Region der Tests), verlinkt in README und `docs/README.md`; das Werkzeug meldet eine nicht lesbare Datei jetzt mit einer Zeile
      statt eines Tracebacks
- [x] 5.3 `hdcpitems.py` `KNOWN_SETS`: neue Geräte eintragen, sobald welche auftauchen - **gestrichen 06.10. (Marco)**: ein
      Ablauf, keine Aufgabe; der Installer druckt den Fingerabdruck zum Einfügen
- [x] 5.4 **`analyse/hdcp-keys/` nach `re/hdcp-keys/`** (entschieden 12.09., nie gemacht; jetzt 0700, aber falscher Ort) (aus `61`)
      - 06.10. verschoben (Umbenennung, 7 Dateien, Hashes gleich, 0700/0600); `referenz/` nachgezogen, `sperr-scan` deckt `re/` ab
- [x] 5.5 Netzwerkwerkzeuge im Rootfs prüfen: `ping`, `curl`, `wget`, `nc` (aus `61` — Stand unklar) - 06.10. am HY310: alle da,
      dazu `ip` und `ss`
- [x] 5.6 Kein Pflichtabzug, wenn Mainline drauf ist — prüfen, ob umgesetzt (aus `61`, zweimal gefordert) - umgesetzt
      (`h713-install` Schritt 3, N2); am 05.10. bei der Neuinstallation gesehen: kein neuer Abzug
- [x] 5.7 Drei tote defconfig-Zeilen `CONFIG_SND_SOC_SUNXI_H713_{CODEC,CPUDAI,MACHINE}=m` (aus `61`) - 06.10.: längst weg,
      stehen nur noch im zurückgenommenen Patch 0050
- [x] 5.8 19 Patches der Serie greifen mit Fuzz/Versatz (`.orig` im Baubaum) — neu aufsetzen (aus `61`) - 06.10.: es waren
      **66** (drei Hunks mit Fuzz, in 0001 und 0067), aus je einem Commit pro Patch neu erzeugt; neue Serie auf frisches
      Vanilla 6.18.38: 0 Versatz-/Fuzz-Meldungen, Baum identisch (`339822a8…`). Werkzeug `arbeit/patches-fuzz-20261006/`
- [x] 5.9 `identify.py` druckt „our layout" — Code-Reste aus ST5-DOCAUDIT §5 - 06.10.: „v3, doku/109" -> v4 mit Verweis auf
      `docs/subsystems/emmc-layout.md`; Versionszeile von `h713-install`/`dump.py` „0.1 (draft, doku/110)" -> 0.2 (Paket)
- [x] 5.10 Webpanel-Konzept (Ecke/Kante, Seitenverhältnis, Undo/Redo, Vorschau = Warp) (`61` Z. 555ff) - verschoben nach **9.13**
      (Marco 06.10.)

## 6 HDCP-Härtung — nach dem Release (`doku/144` TEE-1…5)

- [ ] 6.1 **TEE-2** EL3 liest den Schlüssel selbst; `push_from` ohne Aufrufer-Adresse ← zuerst. Mit 6.2 und 6.5 ein Paket:
      reine Härtung, nichts ist kaputt (heute schlimmstenfalls ein falscher Schlüssel durch Root, auslesen geht nicht).
      Marco 07.10.: als Agentenpaket machen. **07.10. vorbereitet, nicht gemessen** (`doku/161`): 6.1, 6.2, 6.5 und 6.9 als
      ein Paket in `arbeit/hdcp-haertung-20261007/` (TF-A 2, U-Boot 3 - davon `0001` = 6.6 -, Repo 2 Patches), gebaut,
      gegengeprüft. Gewählt: BL31 nennt die Ablage (`HDCP14_STAGE`), eine Senken-Schreibung pro Boot (`HDCP14_ONCE`),
      danach zu; EL3 liest den Schlüssel nicht selbst (eigener MMC-Treiber in EL3 unverhältnismäßig). Einbau und Messung mit **1.1a**
- [ ] 6.2 **TEE-3** Strukturprüfung nach EL3 spiegeln - im Paket 6.1 (07.10.)
- [x] 6.3 TEE-1 S-EL1 nur, wenn eine zweite Nutzlast es lohnt (damals: `tfa-h713/0007`, gibt es seit 06.10. nicht mehr) - **gestrichen 07.10. (Marco: S-EL1
      nicht gewollt, weder in TF-A noch in U-Boot)**; der Testcode ist gelöscht, die Befunde stehen in `doku/153`, `irrwege.md`
- [x] 6.4 TEE-4 die 32 Byte Anhang des 320-Byte-Datensatzes erklären - **gestrichen 07.10. (Marco)**: Neugier, mit 288 Byte geht es
- [ ] 6.5 TEE-5 Watchdog über Treiber; `0x48a00000` und Fenster ableiten statt Konstante - im Paket 6.1 (07.10.): WDT-uclass,
      Fenster als `SUNXI_TEE_WINDOW_*` in BL31 mit Herkunft (aus dem DT nicht ableitbar)
- [ ] 6.6 `h713_hdcp14_wait`-Env ganz entfernen? (entschärft, existiert noch) - **07.10. vorbereitet**: U-Boot-Patch + Gegenstück für
      `check-hdcp-artifacts.sh` in `arbeit/hdcp-wait-env-20261007/patches/`, hy310/release gebaut (gleiche Warnungen wie vorher,
      Schalter weg aus dem Binary), passt auf die Linien; Einbau und Messung mit **1.1a** (Marco 07.10.: ja)
- [x] 6.7 Warteschleifen-Patch (`0035`, Suche der Wait-Site) prüfen: noch nötig, seit die Senke rechtzeitig gefüllt ist? (Marco 14.09.: „muss am Ende weg")
      - **beantwortet, bleibt**: am 05.10. gemessen hängt die Box mit scharfer Warteschleife auch mit Schlüssel in der Senke
- [x] 6.8 BL32-Experiment (5 unversionierte Dateien in `FB-HDCP14h/uboot`): Branch oder löschen - **gelöscht 07.10. (Marco)**
- [ ] 6.9 **BL32-/S-EL1-Gerüst aus dem TF-A-Fork** (Patch 0006, Kopf `4c1bd8c6`; Marco: kein S-EL1 in TF-A): TSP-Definitionen
      (`platform_def.h`), Hersteller-OP-TEE-Übergabe (`H713_BL32_AARCH32`), `optee@48600000`-Reservierung (`H713_WITH_BL32`),
      Schalter in `platform.mk`. **Zuerst klären:** `H713_WDOG_BRINGUP` ist immer gesetzt und schaltet bei jedem Boot den
      Watchdog „for the BL32 bring-up" scharf - **ja, das ist das Netz gegen Hänger beim Booten** (07.10. gelesen: ~11 s ab BL31,
      setzte am 05.10. einen Hänger zurück): er bleibt, raus aus dem BL32-Block, ehrlich benannt. `H713_VENDOR_SECURITY_SETUP` ist
      ebenfalls immer an und kein Gerüst (Sicherheitskonfiguration wie der Hersteller-BL31) - bleibt. Raus: TSP-Block,
      AArch32-Übergabe, optee-Reservierung, BL32-NOTICE, `H713_SKIP_SECURITY_SETUP`-Probe, die Schalter. Ändert das BL31 (der
      BL32-Eintrag wird heute immer befüllt) - also Boot-Test mit 1.1a.
      Nachweis wie `doku/153`: BL31 vorher/nachher vergleichen (gefunden von der Gegenprüfung 07.10., `doku/160` §3)
      - **07.10. im Paket 6.1** (`doku/161`): Gerüst raus, `SPD` ungleich `none` bricht den Bau ab, `H713_BOOT_WATCHDOG`;
        6.9 allein ändert nur `bl31_early_platform_setup2`, die Watchdog-Schreibzugriffe identisch. Gelernt: das Netz reicht
        nur bis U-Boots Watchdog-Init (`sunxi_wdt_probe()` stoppt ihn)

## 7 Dokumentation und Repo

- [x] 7.1 `AGENTS.md` besprochen (06.10.): die vollstaendigen Arbeitsregeln (Kopie, Lieferung mit Kompilat, tor.sh,
      Identitaet, Geraet, Subagenten, Projektordner-Karte) liegen **lokal** in `referenz/arbeitsregeln.md` und werden
      ueber `/opt/Projekte/h713/CLAUDE.md` (Symlink) und einen Block in `~/.claude/CLAUDE.md` in jede Sitzung und jeden
      Subagenten geladen; die veroeffentlichte `AGENTS.md` bleibt absichtlich unveraendert (Marco: nicht committen).
      Erzwingbares ist in Hooks: `.githooks/pre-commit`, `pre-push` (auch in den Forks), `release/tor.sh`
- [x] 7.2 OKF-Frontmatter (`verified`, `stale_after`) in allen `referenz/`-Seiten, `referenz/stale.py` listet Faelliges (06.10.)
- [x] 7.3 Unzitierte Journaleintraege: 25 Ueberholt-/Umgesetzt-Marker (alte Handoffs, erledigte Plaene); `doku-index`
      zaehlt Nachtlog-Belege nicht mehr als unzitiert, kennzeichnet Marker; Analysen 89/72/73 aus `display.md` zitiert.
      Rest: 95 netboot (gueltiges How-to ohne Heimat), 149/150/152 (aktuell) (06.10.)
- [x] 7.4 Journal: eine Quelle. Repo-Kopie war in allen 40 abweichenden Dateien die neuere (satzweise geprueft:
      Zeichensatz + Redaktion); drei Abschnitte aus `40-display.md` uebernommen; alter Master jetzt
      `/opt/Projekte/h713/doku-archiv-bis-20261005/` (0700, Originale). Links `121`/`86` waren in Ordnung (06.10.)
- [x] 7.5 `hy310-logs` war ein identisches Duplikat von `h713-logs` im Overlay; jetzt Symlink, wie `build-rootfs.sh` ihn prueft (06.10.)
- [x] 7.6 Verweise auf geloeschte Pfade: nichts Lebendes kaputt - die lokalen Fixture-, Arbeits- und Firmware-Pfade,
      die Skripte nennen, existieren; nur historische Briefe (`analyse/boot/arbeit/`, `mainline/docs/wifi-*`) nennen
      alte Kernelbaeume. Die Tore (sperr-scan Regel 7) finden Verweise auf den alten Arbeitsordner in Leserdoku (06.10.)
- [x] 7.7 Sicherungs-Tags `vor-main-umzug/*` (3) geloescht - alle in main (06.10.)
- [x] 7.8 Branches: `fable-main`, 9x `von-src/*`, `sicherung/main-vor-mailfix`, `arbeit/doku-7` geloescht (alle in
      main; 06.10.), Fork-Sicherungen ebenso. `hy300-pro-ab-lokal` (+145 Commits, Stand 20.09.) am 06.10. gemessen:
      561 geaenderte Dateien, 0 fehlen in main, Code zu 90-100 % enthalten, der Rest ist main's neuere Fassung
      (ST3-BOARDMERGE) - geloescht (Marco). Auf GitHub bleibt `origin/hy300-pro-ab` (aelterer Stand, loeschen = Push)
- [x] 7.9 Drei Abzuege gehasht (06.10.): stock emmc-voll `33e1ffc4…`, HY300-Pro emmc-full `af2deb6a…`,
      bootbereich-8mib `e16acad0…` - in `referenz/artefakte.md`
- [x] 7.10 `doku/149` §5 Stand 06.10. nachgetragen und in die Repo-Kopie uebernommen (lag nur im Master)
- [x] 7.11 `SICHERUNG-{tee-experiment,tfa,wifi}` in FB-HDCP14h geloescht (06.10.); Geraetesicherungen bleiben
- [x] 7.12 `referenz/irrwege.md`: rchar, OOM/ROOM-Regex, `ssh -n`, modroot ohne aic8800, `kill -9` auf MemPalace,
      Hypothese vor Messung, Agent ohne Kompilat (06.10.)
- [x] 7.13 `/home/user/AGENTS.md` ist seit 06.10. ein Symlink auf `~/.claude/CLAUDE.md` — eine Quelle
- [ ] 7.14 Deutsch in Code → Englisch: Kommentare in Modulen/Patches ab `0146` (aus `61`; Nutzer-Sichtbares ist durch)
- [ ] 7.15 Wissensdatenbank: `doku/` + `analyse/` je Teilsystem destillieren — **läuft** (referenz/, MemPalace, Graphify)
- [ ] 7.16 Testskripte veröffentlichen — Auswahl, was ohne unseren Tisch läuft (aus `61`)
- [ ] 7.17 Fotos: Standbilder der projizierten Bilder (ROADMAP „Pictures")
- [ ] 7.18 Release-Text: „nothing acts on the remote's keys yet except Power" so lassen? [M]

## 8 Lokale Werkzeuge

- [x] 8.1 MemPalace vollständig: Transkripte (~67 000 + 86 000 sweep), referenz/ (268),
      repo-neu ohne Submodule (20 373) — 175 798 Drawers, Endstand 05.10. 17:15.
      Lehre: `mine`/`sweep` nie laufen lassen, während Claude antwortet — der Stop-Hook
      sperrt den Palast und einzelne Dateien scheitern (dann erneut sweepen, idempotent)
- [ ] 8.2 **Bilanz 12.10.** für MemPalace *und* Graphify: findet eine neue Sitzung von selbst,
      was sie braucht? Sonst raus, bevor es Gewohnheit wird
- [x] 8.3 Graphify installiert, `--code-only` über `repo-neu/` (7 862 Knoten, 0 Token),
      Eintrag in `werkzeuge.md`, `.graphifyignore` + `graphify-out/` in `.gitignore` (05.10.)
- [ ] 8.4 Graphify-Doku-Extraktion nur bei Bedarf (geht an ein LLM) — Stand: nein, Doku bleibt
      bei referenz/ + MemPalace
- [ ] 8.5 Graphify-Gemeinschaften heißen „Community N" (ohne LLM keine Namen). Bei der Bilanz
      entscheiden, ob `graphify label --backend claude-cli` erlaubt ist (schickt nur Symbolnamen)
- [ ] 8.6 `settings.json.vor-mempalace-*` und `settings.json.vor-graphify-*` nach Probewoche löschen
- [ ] 8.7 cognee gestrichen — in der Recherche-Datei vermerken
- [ ] 8.8 HY310 läuft noch; Nachtregel „herunterfahren" offen. **Vor Sonoff-aus USB ziehen.**
- [ ] 8.9 L018 (`.127`) und HY350 (`.163`) heute nicht erreichbar

## 9 Spät / groß (aus `61` §8 und ROADMAP)

- [ ] 9.1 **AV1**: erst klären, ob RE-Stand oder lauffähig; H713 ist der erste Allwinner mit AV1
- [ ] 9.2 Cedrus/GPU Testmatrix Decoder × Auflösung × Ausgabe; der KASAN-Fall steht
- [ ] 9.3 Hardware-Video-Decode und IOMMU in **diesem** Image nachmessen (aus cstengers Baum übernommen)
- [ ] 9.4 Verwaltungsoberfläche (WLAN, Presets, Startmodus, Updates ohne SSH) — Zuschnitt offen
- [ ] 9.5 Windows: Installer nie dort gelaufen; `sunxi-fel.exe` nach Rückmeldungen
- [ ] 9.6 Zweites Augenpaar auf die Sicherheitspfade (Gate, Recovery, Installer-Verweigerungen)
- [ ] 9.7 Recovery-Weg **von einer zweiten Person** gegangen; 20 Gate-Zyklen; HDMI-Modustabelle vollständig (aus `61` A.2)
- [ ] 9.8 **Warp-Check: CPU-Last senken?** h713-warp hat heute 1 h 26 min CPU in ~10 h gebraucht (Prüfstand);
      messen, wo die Zeit hingeht (Readback/`check`, Fence-Warten, Poll-Takt), und ob der GPU-Pfad bei
      Identität ganz schlafen kann (Marco, 05.10.)
- [ ] 9.9 Fernbedienung auswerten (war 2.2): 16 Tasten + Maus kommen als Events an, nur Power wirkt — braucht
      einen Desktop/eine Oberfläche, die etwas damit anfängt (Marco 05.10.: spät)
- [ ] 9.10 Settings-Seite: PIN auf der Leinwand statt Passwort (wie Chromecast), Sitzungs-Cookie — braucht eine
      Einblendung im Warp/h713-tv (Marco 05.10.: später)
- [ ] 9.11 **Abschalt-Plopp beim Poweroff** (aus 2.6). Gemessen 05.10. mit dem ThinkPad-Mikro
      (`arbeit/edid-sweep-20261005/plopp/`): Plopp 1 beim Stream-Ende (DAPM nimmt PL2) -> behoben, Kernel 0184.
      Plopp 2 am Poweroff-Ende, 42-54x Grundrauschen, immer +10,96 s nach dem Befehl; harter Netz-Cut mit PL2 an
      nur 9x; PL2 von Hand fallen lassen ploppt, Mute davor (DAC, Line Out, beides, 1,5 s) aendert nichts.
      **Widerlegt:** TF-A nimmt PB5/PL3 vor dem Gate-Reset weg und wartet 600 ms (Fork-Branch
      `versuch/plopp-pb5-pl3-vor-reset` - am 07.10. gelöscht, Marco - in die eMMC geschrieben und gehoert: unveraendert laut) -> der
      Verstaerker haengt nicht (nur) an PB5/PL3, oder der Knall kommt nicht von PL2, sondern vom Zusammenbruch
      der Codec-Versorgung beim Reset. Naechster Schritt braucht Oszilloskop/Schaltplan: welche Schiene
      versorgt den Verstaerker, was tut der Reset mit ihr. Bis dahin: so lassen
- [ ] 9.12 **Bluetooth-Ursache A nach dem Release messen** (aus 2.3, Marco 06.10.): warum der erste HCI-Befehl nach
      einem warmen Reboot ohne den Reset vorab manchmal unbeantwortet bleibt (FB-BTRESET 9.1). Verdacht: `hciattach any`
      öffnet die UART erst mit 115200 und schaltet dann auf 1500000; seit dem Fix öffnet `h713-bt-reset` sie als Erster.
      Messung: 10 warme Reboots mit der alten Unit (Drop-in, btmon ab Boot), dann 10 mit `hciattach -s 1500000`.
      Dazu 9.2: der Kernel verliert seinen Close-Reset beim tty-Detach (`hci_ldisc.c`, upstream-würdig).
      **Früher wieder aufmachen,** sobald trotz Helfer `not UP` oder `no answer` im Journal von h713-bluetooth steht
- [ ] 9.13 Webpanel-Konzept (aus 5.10): Ecke/Kante, Seitenverhältnis, Undo/Redo, Vorschau = Warp (`61` Z. 555ff) - Marco 06.10.:
      erst einmal geschoben


## 10 Erledigt — aus `61` und `144` gestrichen, damit es nicht wieder auftaucht

HDCP 1.4 über die Crypto Engine (05.10.) · Beta-Warnung in README/Release/Installer · Alle
Werkzeuge ins Englische (Nutzer-Sichtbares) · Fremdgeräte-Profile HY300 Pro · Installer liest
`.zst` und findet Binaries neben der Tabelle · Kleiner Abzug aus der GPT statt Konstanten ·
Mitgelieferte GPT gegen errechnete prüfen (Test `stock_gpt_crosscheck`) · Gerätetöne mit HDMI
mischen (v0.96) · Bluetooth mit Stock-Fernbedienung (v0.96) · Bitgleiche Bauten
(`SOURCE_DATE_EPOCH`, v0.96) · Autofokus nur mit Testbild (v0.95) · `ge2d` — **nicht nötig**
(ROADMAP 26.09.) · `tvtop/tvfe/nsi` — **nicht nötig** (ROADMAP) · Platzhalter-Sonderfall —
Layout v4 hat keine Platzhalter · bl31 vom 10.09. in der Bootkette · U-Boot-Firmware-Debugging
per Board (`commdev`/`elog`) · Agenten-Scratch löschen (05.10., 74 Klone) · Wickelschlüssel im
Installer ablegen (`144` 06:0x) — **entfällt**, op 1 entschlüsselt nicht · Konfiguration der
HDCP-Teile prüfen (`144` 06:1x) — `check-hdcp-artifacts.sh`.
