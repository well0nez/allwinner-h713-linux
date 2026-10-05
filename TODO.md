# TODO — die eine Liste

**Die einzige Todo-Liste dieses Projekts.** Neue Punkte hierher; erledigte nach §10 — nicht löschen.
Changelog ist [RELEASES.md](RELEASES.md). `known-issues.md` und `ROADMAP.md` beschreiben dem Leser,
was nicht geht und wohin es geht — sie führen keine Arbeit. Gestartet 05.10.2026 aus `doku/151`.

## 1 Release — in dieser Reihenfolge

- [ ] 1.1 Test-Images bauen (`release/build-all.sh`, Rolle release), `check-hdcp-artifacts.sh` grün
- [ ] 1.2 HY310-Großtest nach `doku/142` (22 Zyklen) + HDCP-Paar wipe→`Desired`, push→`Enabled`
- [ ] 1.3 **WLAN-Timeouts verifizieren** (`82cb57e`, ungeprüft): Rootfs neu, Funk absichtlich verklemmen
- [ ] 1.4 HY300 Pro G-EU (`boards/hy200-qz713df-a1`): Boot, Bild, HDCP 1.4 mit geteiltem Satz, 2.2
- [ ] 1.5 STAGE4-Marker füllen und löschen (`git grep -n STAGE4`)
- [ ] 1.6 Forks pushen: U-Boot `h713-hy310` +6, TF-A `sun50i-h713` +2 — **vor** `main`
- [ ] 1.7 `main` pushen (+72)
- [ ] 1.8 `RELEASES.md`: neuer Abschnitt; Release-Tag; Baustempel
- [ ] 1.9 `docs/known-issues.md` Zeile „HY300 Pro dunkel" nach test10-Foto

## 2 Am Gerät offen (keine Blocker, aus `144` §2 und known-issues)

- [ ] 2.1 **Zoom** (Marco 04.10.: „bringt das Gerät durcheinander") — `ctl zoom out` ist nur Lupe
- [ ] 2.2 Fernbedienung: 16 Tasten + Maus kommen als Events an, **nichts wertet sie aus** außer Power
- [ ] 2.3 Bluetooth nach warmem Reboot: erster HCI-Befehl verloren (2 von 5), Ursache offen (FB-BTRESET 9.1/9.2)
- [x] 2.4 HDCP 2.2 Session-Beweis: Fire-TV-Stick am HY310, 05.10. — `h713-tv ctl hdcp` meldet
      „2.2 (session stands), authenticated: yes", Firmware-Log zeigt SKE_SEND_EKS; über acht
      Moduswechsel (1080p60 ↔ 720p50/60) jedes Mal neu authentifiziert. Beide Schlüssel sitzen
      (1.4 aus U-Boot, LINK 0x93=0x45; 2.2 vom Kernel beim Probe)
- [ ] 2.4a **720p-Quelle + Warp: Bild doppelt und gestaucht** (Fire TV 720p60, 05.10.). Der
      Warp-Frame selbst ist sauber (`h713-warp ctl dump`), ohne Warp ist 720p sauber — also
      liest der Kompositionsblock der Firmware den 1920er Warp-Puffer weiter mit dem
      Ring-Stride 1280 (Patch 0107: „nothing behind the reader gets reprogrammed"; dort als
      „not yet measured on the wall" markiert — jetzt gemessen). Fix-Kandidaten: beim Wechsel
      Ring→FB den Descriptor mit FB-Geometrie publizieren und WCE abwarten (afbd), oder den
      Warp in Quellgröße rendern lassen. Vor dem Release entscheiden — trifft jede
      Nicht-1080p-Quelle mit Keystone
- [ ] 2.5 HY300-Lampe: Testplan `doku/143` §11 (Foto gegen Stock, PWM-Block lesen)
- [ ] 2.6 Audio: Abschalt-Plopp
- [ ] 2.7 Geometrie: Ceiling-Beweis kopfüber; Kalibrierkarten in gespiegelten Modi; Konsole durch den Warp
- [ ] 2.8 Autofokus: eine Wand, ein Abend; Metrik-Spanne nur +11 % (Belichtung)
- [ ] 2.9 Keystone ohne Langlauf; automatische Korrektur ohne `/etc/h713/keystone-ref` gegen Ideal-Pose
- [ ] 2.10 EDID: zwei Modi rasten nicht, 1080p100/120 hinter Schalter; 1600×900 und 120 Hz (aus `61`)
- [ ] 2.11 `backlight_level` / `dynamic_backlight` ohne Wirkung — Firmware nimmt den Aufruf, Lampe ändert nichts
- [ ] 2.12 AP-Latenzspitzen (3 ms ↔ 2 s bei −50 dBm, Durchsatz ok)
- [ ] 2.13 Settings-Seite Port 8080 **ohne Authentifizierung**
- [ ] 2.14 Reinstall setzt Einstellungen und Fernbedienungs-Pairing zurück
- [ ] 2.15 `afbd`-Modultausch zur Laufzeit bringt kein neues Fenster (Firmware nimmt Republikation nicht)
- [ ] 2.16 Frame während laufendem Commit wird verworfen (`ok busy`)
- [ ] 2.17 Presets `computer`/`game`/`hdr` nie geprüft; Gamma 2,2 Sichtprüfung gegen Stock; Weißabgleich/CTM ohne Stock-Vergleich (aus `61`)
- [ ] 2.18 `h713-pq brightness` sagt „ohne Wirkung" — widerlegt 07.09., Meldung korrigieren (aus `61`)
- [ ] 2.19 `h713-tv`: `replug` (S_EDID blocks=0) fehlt; Plane liest Ring direkt statt dma-buf (aus `61`)
- [ ] 2.20 Preset beim Start wählbar, Regler über Neustart merken; Startmodus `auto|manuell` merken (aus `61`)
- [ ] 2.21 Kamera mit hellem Bild nie geprüft; WLAN-Station zwei Ecken offen; Telefon am AP (aus `61`/known-issues)
- [ ] 2.22 eMMC `data error cmd18` am GEU (einmal) — erst bei Wiederauftreten
- [ ] 2.23 KEY_POWER-Politik und WLAN-Band der Koexistenzmessung nicht notiert (`doku/134` Z. 136)
- [ ] 2.24 Kleinkram aus `61`: `regulatory.db` load failed −2; `r8152` will `rtl8153b-2.fw`

## 3 Geparkt — mit Wiedereinstiegsbedingung

- [ ] 3.1 **Standby Stufe 2** (<1 W, ARISC, IR/CEC): PSCI-Suspend erreicht DRAM, **kein Wecken** (`doku/139`). FB-STANDBY + 0167c rein, wenn Wecken bewiesen
- [ ] 3.2 FB-CRUST — nach Standby
- [ ] 3.3 FB-MIPSRELOAD/b — rein, wenn der Bildfehler nach Reload verstanden ist (`doku/138`)
- [ ] 3.4 IR FB-REMOTEb + fd02-Keymap — rein, wenn rx_resolution-Trunkierung / ARISC-Schreibpfad geklärt
- [ ] 3.5 `Reserve0_a/b` und `private` von einem **unangetasteten** Gerät abziehen (bei uns überschrieben) (aus `61`)

## 4 Boards und Fremdgeräte

- [ ] 4.1 `hy300-pro` (Issue #1): test10 aus `main` nach dem Release (0168, 0182, 2de0cc8, Gamma, project 0x34)
- [ ] 4.2 `hy200-qz713-v2`: Layout-v4-Defconfig + eigener Baum **vor** jedem TEST-Image; Q5 tREFI
- [ ] 4.3 `hy200-qz713df-a1`: 09-22-Einheit unbekannt (eMMC, DRAM, Sensor, Kamera, Motor) → per-Variante-Overlay
- [ ] 4.4 FEATURES der Boards ohne Besitzerbericht bleiben leer; `boards/check.sh` soll FEATURES-Namen prüfen
- [ ] 4.5 `boards/README.md`: Tabelle „welcher Ordner ist mein Gerät" (im README drin, dort nicht)
- [ ] 4.6 An cstenger zurückmelden: Composition-Befund (`89`), D1-CCU Port 1, SIDDQ, Doorbell im MIPS-Sendepfad (aus `61`)

## 5 Installer und Werkzeuge

- [ ] 5.1 ST3-RESTORE F1: Schema-Feld `layout.disk_sectors_from = unit|image` statt Heuristik
- [ ] 5.2 `h713-hdcpkey` braucht eine `docs/tools/`-Seite
- [ ] 5.3 `hdcpitems.py` `KNOWN_SETS`: neue Geräte eintragen, sobald welche auftauchen
- [ ] 5.4 **`analyse/hdcp-keys/` nach `re/hdcp-keys/`** (entschieden 12.09., nie gemacht; jetzt 0700, aber falscher Ort) (aus `61`)
- [ ] 5.5 Netzwerkwerkzeuge im Rootfs prüfen: `ping`, `curl`, `wget`, `nc` (aus `61` — Stand unklar)
- [ ] 5.6 Kein Pflichtabzug, wenn Mainline drauf ist — prüfen, ob umgesetzt (aus `61`, zweimal gefordert)
- [ ] 5.7 Drei tote defconfig-Zeilen `CONFIG_SND_SOC_SUNXI_H713_{CODEC,CPUDAI,MACHINE}=m` (aus `61`)
- [ ] 5.8 19 Patches der Serie greifen mit Fuzz/Versatz (`.orig` im Baubaum) — neu aufsetzen (aus `61`)
- [ ] 5.9 `identify.py` druckt „our layout" — Code-Reste aus ST5-DOCAUDIT §5
- [ ] 5.10 Webpanel-Konzept (Ecke/Kante, Seitenverhältnis, Undo/Redo, Vorschau = Warp) (`61` Z. 555ff)

## 6 HDCP-Härtung — nach dem Release (`doku/144` TEE-1…5)

- [ ] 6.1 **TEE-2** EL3 liest den Schlüssel selbst; `push_from` ohne Aufrufer-Adresse ← zuerst
- [ ] 6.2 **TEE-3** Strukturprüfung nach EL3 spiegeln
- [ ] 6.3 TEE-1 S-EL1 nur, wenn eine zweite Nutzlast es lohnt (`tfa-h713/0007` liegt bereit)
- [ ] 6.4 TEE-4 die 32 Byte Anhang des 320-Byte-Datensatzes erklären
- [ ] 6.5 TEE-5 Watchdog über Treiber; `0x48a00000` und Fenster ableiten statt Konstante
- [ ] 6.6 `h713_hdcp14_wait`-Env ganz entfernen? (entschärft, existiert noch)
- [ ] 6.7 Warteschleifen-Patch (`0035`, Suche der Wait-Site) prüfen: noch nötig, seit die Senke rechtzeitig gefüllt ist? (Marco 14.09.: „muss am Ende weg")
- [ ] 6.8 BL32-Experiment (5 unversionierte Dateien in `FB-HDCP14h/uboot`): Branch oder löschen

## 7 Dokumentation und Repo

- [ ] 7.1 **`AGENTS.md` besprechen** (noch nicht geschehen); Erzwingbares in Hooks statt Prosa
- [ ] 7.2 OKF-Frontmatter + `stale`-Skript für `referenz/` (vorgeschlagen, nicht gebaut)
- [ ] 7.3 `doku/INDEX.md` §3: 122 unzitierte Einträge auf „Überholt"-Marker durchsehen
- [ ] 7.4 ST5-DOCAUDIT: doku-Kopie-Sync (8 Dateien; `121`/`86`-Links im Journal richten)
- [ ] 7.5 `hy310-logs` **und** `h713-logs` beide im Overlay — einen weg
- [ ] 7.6 Verweise auf am 05.10. gelöschte lokale Pfade prüfen (Bauausgaben, Vollklone, `tftp/`, Standalone-Kernelbaum) — in Skripten und Doku
- [ ] 7.7 Sicherungs-Tags nach Bestätigung löschen: `vor-main-umzug/*`, `hdcp14-auf-altem-main`
- [ ] 7.8 Branches entscheiden: `fable-main`, `von-src/*` (9), `hy300-pro-ab-lokal` (370 hinter), Arbeitsbranch
- [ ] 7.9 `referenz/artefakte.md`: drei Abzüge noch „(zu hashen)"
- [ ] 7.10 `doku/149` Stand nachtragen (Stufe 1+2 durch)
- [ ] 7.11 `SICHERUNG-tfa/-wifi/-tee-experiment` in `FB-HDCP14h/` nach Bestätigung weg
- [ ] 7.12 `referenz/irrwege.md`: „rchar zählt keinen Verzeichnis-Walk" nachtragen
- [ ] 7.13 `/home/user/AGENTS.md` dupliziert `~/.claude/CLAUDE.md` — eine Quelle
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
