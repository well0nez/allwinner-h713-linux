# 152 - Handoff 05.10.2026, Abend (15:00-23:50) - Stand, alles Getane, nächste Schritte

Fortsetzung von `150` (Nachmittag). Die eine Todo-Liste bleibt `TODO.md`; dieser Text ist der Zeiger
für die nächste Sitzung: was heute Abend passiert ist, mit Zahlen, und in welcher Reihenfolge es
weitergeht. Marco: "sei detailreich und lass nichts aus."

## 0 In einem Absatz

v0.96-beta ist gebaut, auf dem HY310 installiert und mit fünf Kaltstarten plus HDCP-Paar abgenommen.
Der Fire-TV-Stick hat zum ersten Mal HDCP 2.2 bewiesen. Dabei kamen drei Warp-Fehler ans Licht
(720p-Stride, Flackern bei SD/PC-Modi, Schwarzbild bei 24/25 Hz) - alle drei gemessen, behoben,
am Gerät bestätigt. Die EDID bietet keine Modi mehr an, die die Firmware nicht rasten kann. Die
Settings-Seite hat ein Passwort. Marcos private E-Mail-Adresse stand in 23 ungepushten Commits und
drei Spiegel-Patches, ein Arbeitgebername in Patch 0007 - beides raus, mit Hooks und Tor dagegen.
MemPalace und Graphify laufen (Probebetrieb bis 12.10.). Zwei Dinge gingen schief und sind
zurückgebaut: ein TF-A-Versuch gegen den Poweroff-Plopp (Hypothese widerlegt) und mein eigener
Hang, Versuche direkt in der echten Linie zu machen - dafür gibt es jetzt Regel 6.

## 1 Stand

| Was | Stand |
|---|---|
| Repo | `/opt/Projekte/h713/repo-neu`, `main @ f1315e7`, **103 Commits vor `origin/main`, nichts gepusht**, Working Tree sauber, Tore grün |
| Forks | U-Boot `h713-hy310 @ 4913742a9a1` (Spiegel `uboot-h713/` 95 Patches, Baum 3387c2bb9b00) · TF-A `sun50i-h713 @ 824eb0bd` (Spiegel `tfa-h713/` 7 Patches, Baum 67cf7997a540). Beide **nur lokal**, TF-A hat noch kein GitHub-Remote |
| Image | `installer/out/h713-hy310-v0.96-beta-{a-bootkette,b-system,c-gptkopie}.img` + Tabelle/sha256/README, Bau 20:36 aus `819a09a`. **Nicht drin:** Kernel 0184, Warp-Fixes `ec93ae1`/`bf3b72c`, EDID-Beschnitt `c33df12`, Panel-Auth `2903dfb` - alles danach. Nächster Bau nötig |
| HY310 | läuft v0.96-beta (installiert 20:47) **plus Schnell-Deploy**: Kernel-FIT mit 0183+0184 (`/boot/h713-kernel.fit`, Sicherung `/root/sicherung-vor-0184/`), `h713-warp` mit beiden Fixes, `h713-tv` mit EDID-Beschnitt, `h713-panel` mit Auth. `/etc/h713` aus der Sicherung zurück (wifi.env, warp.conf, keystone.conf, tvconfig, tv.conf, features). U-Boot-Block = Installer-Stand (`bbeda477`). IP heute `<geschwaerzt 23.10.2026: Heimnetz-Adresse>` (DHCP; Hostschlüssel neu seit Reinstall, in known_hosts für .131 und .132). ThinkPad hängt am HDMI (1080p60). Sonoff an, Journal persistent |
| MemPalace | 129 096 Drawers, nur H713; Hooks nur für `/opt/Projekte/h713` (`~/.local/bin/mempalace-hook`); MCP in neuen Sitzungen da |
| Graphify | Graph 7 874 Knoten, benannt, Post-Commit-Hook baut nach; `graphify-out/` ignoriert |
| Tore | `sperr-scan.py` (jetzt Regel 8: lokale Sperrbegriffe `~/.config/h713/sperrbegriffe`), `doku-index.py --pruefen` (nur getrackte Dateien), `installer/tests/run.sh` 412 Tests, `h713-panel` 33 Tests, `.githooks/pre-commit` + `pre-push` (`core.hooksPath=.githooks`) |

## 2 Was heute Abend gemacht wurde

### 2.1 Werkzeuge: MemPalace, Graphify
- MemPalace: Transkripte (~67 000 Themen-Drawers + 86 000 je Nachricht), referenz/ (268), repo-neu ohne
  Submodule (20 373; erster Lauf hatte 25 000 Submodul-Dateien mitgenommen -> `exclude_patterns` in
  `repo-neu/mempalace.yaml`, 35k Fremd-Drawers wieder raus). Index-Absturz (Segfault, Sitzungs-Neustart
  mitten im Stop-Hook) -> `repair rebuild-index`, 2,5 h. TIMbox/i96/Scratch (45 756 Drawers) entfernt.
  Hooks auf Erlaubnisliste `/opt/Projekte/h713` beschränkt. Palast als schlüsseltragend in
  `referenz/artefakte.md` (0700). Erste Bilanz: Messregel gefunden, VIC-Frage nicht - 1:1.
- Graphify 0.9.76: `--code-only` (0 Token), `.graphifyignore` (Submodule, Spiegel, doku, re), Gemeinschaften
  per `claude-cli` benannt (Marco hat die CLI eingeloggt), Post-Commit-Hook, `.gitattributes`-Merge-Treiber
  wieder entfernt (graph.json nicht getrackt). Vorschau-Server `localhost:8765` (launch.json `graphify-html`).
- `referenz/werkzeuge.md`: Abschnitte MemPalace (Config, Stolperfalle Stop-Hook/Lock, Rebuild-Dauer),
  Graphify, Schnell-Deploy, Identitäts-Tor. `referenz/geraete.md`: IP-Hinweis.

### 2.2 HDCP 2.2 bewiesen (TODO 2.4 ✓)
Fire-TV-Stick am HY310: `h713-tv ctl hdcp` "2.2 (session stands), authenticated: yes", Firmware-Log
`SKE_SEND_EKS`; acht Moduswechsel, acht Neu-Authentifizierungen. Beide Schlüssel sitzen (1.4 aus
U-Boot, LINK 0x93=0x45; 2.2 vom Kernel beim Probe). `docs/subsystems/hdcp.md` Abschnitt, `referenz/messregeln.md`.

### 2.3 Warp-Prüfstand (Fable-Agent, 108 Aufrufe, 42 min; Bericht `arbeit/warp-pruefstand/BERICHT.md`)
- **2.4a** 720p + Warp doppelt/gestaucht: Kernel verweigerte Descriptor-Neuschreiben außerhalb des Ring-Modus
  (`afbd.c`, Regel aus 0107) -> **Kernel 0183** (`f5003a2` + Compile-Fix `df053f0`: der Agent hatte `void *`
  indiziert und nicht gebaut). Am Gerät: Register folgen dem Puffer, Kamera ein Gitter, neun saubere
  Republishes bei Moduswechseln.
- **2.4e** Flackern/Grün bei 480p, 576p, 1366×768, 1280×1024 (Pitch ≠ 64er-Vielfaches, Panfrost lehnt Import
  ab, Warp versuchte sekündlich neu, 47 Republishes/min) -> `ec93ae1`: Import vor Claim, kein Retry bis
  Geometriewechsel. Gemessen: 0 Republishes, Bypass still.
- **2.4g** 24/25 Hz schwarz (Stale-Schutz 28 ms gegen 34/50-ms-Slots) -> `bf3b72c`: Schwelle folgt dem
  Slot-Abstand. 1080p24 24,0 fps, Kamera Y 54 statt 1,9.
- Agenten-Kleinfunde eingebaut (`13c7721`): `ctl status` warf den Warp ab (Frist 1000 ms), Journal-Spam,
  `test mask` markiert tl, Firmware-Zoom im Warp-Commit.
- **Kamera als Auge:** `/dev/video0` mit Belichtung 5000/Gain 255 sieht die Leinwand; `kamera-gitter.py`
  zählt Gitterlinien, `einzeln.py` fotografiert je Modus mit U/V-Statistik. Skripte in `arbeit/warp-pruefstand/`
  und `arbeit/edid-sweep-20261005/`.
- Offen: 2.4b Seitenverhältnis (4K-Ring 1920×1012 wird auf 1080 gezogen), 2.4f Keystone für SD/PC-Modi,
  2.4d Kosmetik-Rest, 9.8 CPU-Last.

### 2.4 EDID (2.10a ✓)
`h713-tv` beschneidet veröffentlichte EDID-Hälften um SVDs ohne Firmware-Eintrag (`edid_prune`), beim Start
einmal, falls nötig (`c33df12`). Gerät: 17 statt 20 VICs, ThinkPad bietet 720x480i/576i nicht mehr an.
Modus-Durchläufe (`arbeit/edid-sweep-20261005/ergebnis*.txt`, `einzeln.txt`): rastet alles außer 1600×900,
1920×1200, 1600×1200, 2560×1600 (nicht in der Firmware-Tabelle, Konsole) und 1024×768i ("1024×383").

### 2.5 Bau und Installer
- Vier Bau-Stolpersteine behoben: 0183 kompilierte nicht; Sysroot ohne libstdc++ wiederverwendet ->
  Paketlisten-Stempel (`be4f8e1`); `doku-index` zählte Bauausgaben -> nur getrackte Dateien (`0bbb0c5`);
  Vollbau nur zum BL31-Test gestartet (Marco: "übertreibst") -> gestoppt.
- v0.96-beta installiert über unser Layout (FEL per `h713-fel --yes`, `--device /dev/sda`): 44 Dateien
  zurückgelesen, Secure Storage byteidentisch, HDCP-1.4-Satz "known vendor set" (neue `hdcpitems`-Prüfung).
  **Reinstall verwirft `/etc/h713`** (wifi.env -> AP-Modus; per UART zurückgespielt) -> TODO 1.2b.
- Schnell-Deploy-Lehre: `modroot` = nur Kernel-Module, aic8800 fehlt -> kein WLAN (`werkzeuge.md`).

### 2.6 Fünf Kaltstarte + HDCP-Paar (TODO 1.1 ✓, 1.2 ✓; `doku/142` Abschnitt 05.10. abends)
5/5 gebootet, ssh nach ~23 s, 0 fehlgeschlagene Dienste, WLAN ~9 s, BT UP; Z2 wipe -> Quelle **Desired**
(0x93=0x41), Z3/Z1/Z5 -> **Enabled** (0x45), ThinkPad mit angeforderter Content Protection. Marco hat
mit Recht nachgefragt: Z2 war dünner (Anforderung gescheitert, nur stehender Zustand) - Wiederholung
Z6/Z7 mit UART-Mitschnitt steht aus. **Z4: zweiter Boot ohne Spur** (~80 s nach Strom-an) -> 1.2a.

### 2.7 Settings-Seite (2.13 ✓)
HTTP Basic Auth, Passwort beim ersten Start (`/etc/h713/panel.env`, 0600), `--show-password`, `--no-auth`;
33 Tests; Gerät 401/401/200 (`2903dfb`). PIN auf der Leinwand -> 9.10.

### 2.8 Kleine Punkte
2.18 war seit 11.09. gefixt; 2.23 Power-Politik in `docs/hardware.md`, WLAN-Band 2,4 GHz Kanal 4 in `doku/134`;
2.24 vertagt; 2.2 Fernbedienung -> 9.9; 2.19 überholt (replug gibt es); 2.10/2.9/2.14/2.16 annotiert.

### 2.9 Identität (Marcos Frage "welche Mail steht in den Pushes?")
- 23 ungepushte Commits (18 main, 1 U-Boot, 2 TF-A, alle von heute) und drei Spiegel-Patches trugen
  die private Adresse (Klartext nur in `arbeit/mail-pruefung/`); ein Arbeitgebername stand seit `b77ed10` (01.04.) in Patch 0007. Klarname in doku/128,
  140, 143 und in `~/.claude/CLAUDE.md`/`~/AGENTS.md`.
- Umgeschrieben (filter-branch, Inhalt identisch, Sicherungs-Branches `sicherung/*`), Spiegel neu, Zeiger neu
  (`03ae204`), Patch 0007 vorwärts auf `well0nez` (`5e4475a`), Klarname raus, Identitätsbegriffe aus den
  Handoff-Seiten raus (`f8064a1`).
- Dagegen: `.githooks/pre-commit`/`pre-push` (Identität + Begriffsliste), `sperr-scan` Regel 8 mit
  `~/.config/h713/sperrbegriffe` (**außerhalb des Repos**, 0600), Memory `git-identitaet-noreply`.
- Ursache: die Adresse kam aus dem Sitzungskontext (Desktop gibt sie mir zur Erkennung mit). Nicht aus Memories.
- Sonnet-Bericht `arbeit/mail-pruefung/BERICHT.md` (lokal; nennt die Adresse). Chris Stengers Gmail
  (266 Commits) und `root@<geschwaerzt 23.10.2026: Hostname eines fremden Servers>` sind schon öffentlich - seine Sache bzw. Hostname.

### 2.10 Abschalt-Plopp (2.6 -> teils ✓, Rest 9.11)
Gemessen mit dem ThinkPad-Mikro (`arbeit/edid-sweep-20261005/plopp/plopp1-4`): Plopp 1 beim Stream-Ende
(DAPM nimmt PL2; drei Mute-Reihenfolgen davor ändern nichts) -> **Kernel 0184** `allwinner,pa-stays-on`
(`a06473b`), am Gerät still. Plopp 2 am Poweroff-Ende, 42-54x Grundrauschen, immer +10,96 s; Netz-Cut mit
PL2 an nur 9x. **Hypothese widerlegt:** TF-A nimmt PB5/PL3 vor dem Gate-Reset weg (600 ms) - per dd in die
eMMC, unverändert laut. Zurückgebaut: eMMC-Block aus `/root/sicherung-vor-tfa0008/`, Fork auf `824eb0bd`,
Versuch als Branch `versuch/plopp-pb5-pl3-vor-reset`. Weiter nur mit Oszilloskop/Schaltplan.

### 2.11 eMMC-Hänger (2.22)
23:03, ~2 min nach einem Boot mit frischem 0184-FIT: jeder Plattenzugriff hing (auch Konsolen-Login),
ssh/`uptime` antworteten; nach Stromzyklus normal, keine mmc-Fehler, Lesen sauber. Journal seitdem persistent.

## 3 Fehler des Abends und Lehren (ehrlich)
1. UART-Brücke angefasst, während Marco dranhing (verträgt einen Client) - nie ohne Frage.
2. Schnell-Deploy ohne aic8800-Module -> kein WLAN. `modroot` ist nicht der ganze Modulsatz.
3. `wifi.env` nicht gesichert/zurückgespielt vor dem Reinstall; Marco musste mich erinnern.
4. HDCP-Zyklus 2 als "erfüllt" verkauft, obwohl die Anforderung gescheitert war.
5. Erstlauf MemPalace über **alle** Transkripte (TIMbox mit drin), Hooks global.
6. Monitor-Regex `OOM` traf `ROOM` (Fehlalarme); `ssh` in `while read` ohne `-n` fraß die Modusliste;
   `pkill -f` mit Muster aus der eigenen Kommandozeile (dreimal); `kill -9` eines Mines mitten im Schreiben.
7. **TF-A-Hypothese vor der Messung committet, gespiegelt, in die eMMC geschrieben** - Marco: "wir arbeiten
   immer in einer Kopie, deswegen gab es so viel Müll, das soll so." -> **Regel 6** in
   `~/.claude/AGENT-KONTEXT-VORLAGE.md`, Memory `immer-in-einer-kopie-arbeiten`.
8. Vollbau gestartet, um BL31 zu testen - `dd` des U-Boot-Blocks reichte.
9. Agenten-Patch nicht kompiliert geliefert -> **Regel 5** in der Vorlage ("kompilieren ist Teil der Lieferung").

## 4 Nächste Schritte, in dieser Reihenfolge (mit Marco abgestimmt 23:45)
1. **7.1 AGENTS.md besprechen** (zu zweit, ~20 min): Zweck/Rechtsrahmen bleibt; dazu Pflichten, die wir
   heute bewiesen haben - Identität nur noreply (Hooks), Regel 5 (kompilieren), Regel 6 (Kopie), wo Wissen
   liegt (`referenz/00-INDEX.md`, MemPalace, Graphify) und dass Agenten das lesen.
2. Mechanische §7-Punkte in einem Rutsch: 7.2 OKF+stale, 7.3 (122 unzitierte), 7.4 Kopie-Sync/Links,
   7.5 `hy310-logs`/`h713-logs`, 7.6 Verweise auf gelöschte Pfade, 7.9 drei Abzüge hashen, 7.10 doku/149,
   7.12 irrwege.md (rchar, OOM/ROOM, ssh -n, Hypothese-vor-Messung, modroot ohne aic8800).
3. Mit Marcos Ja: 7.7 Tags `vor-main-umzug/*`, 7.8 Branches (`fable-main`, `von-src/*` 9, `hy300-pro-ab-lokal`,
   `sicherung/*` 3 - nach ein paar Tagen), 7.11 SICHERUNG-Ordner, 7.13 eine Quelle für AGENTS/CLAUDE.
4. Dann Release-Pfad: Bau mit allen Fixes (0183, 0184, Warp, EDID, Panel), 1.2a (Z4-Boot beobachten, fünf
   Kaltstarte), 1.2b (Installer übernimmt `/etc/h713`), Z6/Z7 HDCP-Paar sauber, 1.3 WLAN-Hängefall,
   1.4 HY300 Pro G-EU, 1.5 STAGE4, **1.6 Forks pushen vor main** (TF-A braucht erst ein GitHub-Remote),
   *Nachtrag 06.10.: das GitHub-Repo fuer TF-A gab es laengst (seit 14.09.); nur das lokale Submodul zeigte auf einen
   geloeschten Pfad - behoben mit `git submodule sync`, siehe TODO 1.6.*
   1.7 main, 1.8 RELEASES.md.
5. Spät: 9.8 Warp-CPU, 9.9 Fernbedienung, 9.10 PIN, 9.11 Plopp 2, 2.4b/2.4f Warp-Aspekt und SD-Keystone.
6. 12.10.: Bilanz MemPalace + Graphify (8.2).

## 5 Wo was liegt (für die nächste Sitzung und jeden Agenten)
- Die eine Liste: `repo-neu/TODO.md`. Changelog: `RELEASES.md`. Handoffs: `doku/150` (Nachmittag), **`doku/152`** (dieser).
- Nachschlagen: `/opt/Projekte/h713/referenz/00-INDEX.md` -> geraete, werkzeuge, baeume, messregeln, irrwege,
  artefakte (Register, Rechte), protokolle/.
- Arbeitsordner heute (lokal, nicht im Repo): `/opt/Projekte/h713/arbeit/warp-pruefstand/` (Bericht, Patches,
  Skripte, Dumps), `arbeit/edid-sweep-20261005/` (Sweeps, Kamera, Plopp-Aufnahmen),
  `arbeit/mail-pruefung/` (Identitätsbericht), `arbeit/sicherung-vor-v096-install-20261005-2044/`
  (/etc/h713, Env, dump/, alte Module).
- Am Gerät: `/root/sicherung-vor-0184/` (FIT 0183), `/root/sicherung-vor-tfa0008/` (U-Boot-Block),
  `/root/pre-v096/`, `/etc/h713/panel.env`.
- Hooks/Regeln: `repo-neu/.githooks/`, `~/.config/h713/sperrbegriffe`, `~/.local/bin/mempalace-hook`,
  `~/.claude/AGENT-KONTEXT-VORLAGE.md` (Regeln 1-6), Memory `~/.claude/projects/-home-user/memory/`.
- Vorschau: `~/.claude/launch.json` -> `graphify-html` (localhost:8765).

## 6 Offene Fragen an Marco
- Z6/Z7 (HDCP-Paar sauber, mit UART-Mitschnitt) - wann, UART frei?
- 7.7/7.8/7.11: welche Tags, Branches, Sicherungsordner dürfen weg?
- Box über Nacht an oder aus (lief um 23:50 noch, ThinkPad dran)?
