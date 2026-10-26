# 223 v0.97.1-beta: das Release-Abbild des L018 - Bau von vorn, Installation, Start - Protokoll

Datum: 26.10.2026 nachmittags. Gerät: L018 (Marcos eigener, Stock-Firmware `Projector05141211`), lief test3 (`doku/222`). Marco an
Kabel, Strom und Taste. Paket (lokal): `arbeit/l018-release-20261026/` (`bau-l018.log`, `install-rel.sh`, `stufe-*.log`,
`freigaben.txt`, `release/`). TODO 1.11, 4.9.

## 1 Warum ein Punkt-Release

Der L018 ist seit `doku/222` verified, `v0.97-beta` (Tag `43417440`) enthält ihn nicht. Marco wollte nicht alle drei Boards neu bauen
(„nur für den einen?"); entschieden: `v0.97.1-beta` mit **einem** Abbild, dem des L018. HY310 und HY300PRO-G-EU bleiben auf
`v0.97-beta`. `release/build-all.sh` ließ nur `vX.Y` und `vX.Y-beta` zu - eine Zeile erlaubt `vX.Y.Z-beta` (`2b872290`, Tore grün).

## 2 Bau

`release/build-all.sh --version v0.97.1-beta --board l018 --profile media,desktop --vendor <Auszug des Stock-Abbilds>` in einer frischen
Kopie von `main` (`46f87430` + `2b872290`), Submodule frisch, nur der Download-Cache übernommen: 29 min, alle Schritte gebaut („taken
over from their stamps none"), `reproducible: yes`, Selbsttest mit den Herstellerdateien ALL GREEN, HDCP-Tor grün. Die Quelle
unterscheidet sich vom abgenommenen test3 (`f1d2617f`) außerhalb der Doku nur in `boards/l018/board.env` und `profiles/l018.py`
(Status) und der Versionsprüfung.

Offline im Abbild gelesen (debugfs auf `hy310-rootfs`): `tv.conf` `volume_curve = vendor`, `keys.conf` `focus_steps = 13`,
`keystone.conf` `lsm6dsv_accel` +z/+y/-x 1.1501, `modprobe.d/h713-focus.conf` `homing=0`, `features` mit allen vier Merkmalen,
`h713-lamp` mit Unit; die Tabelle trägt kein `test_for` (Release-Abbild, kein Testabbild).

## 3 Installation über unser Layout

| Schritt | Ergebnis |
|---|---|
| Sicherung | 29 Besitzer-Dateien per ssh, nur lokal |
| Probelauf `--no-write` (FEL über `h713-fel`) | grün, 45 Herstellerdateien aus dem Vollabzug (Verweis), nichts geschrieben. Anders als beim Testabbild braucht ein Release-Abbild das Board nicht für die Entscheidung; der Probelauf meldet nur, dass er `/etc/h713/board` nicht schreibt |
| Schreiben (Marcos Ja) | 4 min; Board aus dem eigenen `/etc/h713/board` des Geräts (`l018`, `0x30`); zurückgelesen, Secure Storage byte-gleich, HDCP-1.4-Satz vorhanden; übernommen: `focus.conf`, `keystone.conf`, `lamp.conf`, `panel.env`, `warp.conf`, `wifi.env`, Hostschlüssel, BT-Kopplung, h713-tv-Zustand. `tv.conf` und `keys.conf` kommen diesmal aus dem Abbild |
| Start | Kabel raus, Strom aus/an, Power-Taste (Marco: „er startet") |

## 4 Nach dem Start (ssh, 2 min nach dem Start)

`is-system-running` = running, keine fehlgeschlagene Unit; `/usr/local/share/doc/h713-linux` nennt `h713-l018-v0.97.1-beta-media-desktop`
und `2b872290`; `h713-features`: Kamera, Neigungssensor (`lsm6dsv_accel`), Fokusmotor, Lampenstufen vorhanden; LED blau 1, rot 0;
`h713-lamp`: std, Lüfter 3180 U/min, NTC 26,1 °C; h713-tv: „the device's own curve" (50 = -12,5 dB); `h713-keystone once` pitch 18,85°;
Fokus `homing` N, `focus_steps = 13`; `h713_gate=1`; eine deckende Seite (der Launcher) über dem Bild; die Fernbedienung gekoppelt.

**Nicht wiederholt** (an test3 gemessen, gleicher Inhalt, `doku/222`): Ton, Hardware-Video, HDCP, Autofokus, Keystone von vorn.
**Nicht getestet / nicht gemessen** wie in `doku/222`: Kopfhörer, HDCP 2.2, Wärmemodus, Abschalten bei 51 °C.

## 5 Ergebnis

Das Abbild ist release-fertig. Doku auf `versuch/l018-release`: `RELEASES.md` (Abschnitt `v0.97.1-beta`, Punkt-Release-Regel),
README, STATUS, FLASHING, known-issues, Board-Seiten. Push von `main`, Tag `v0.97.1-beta` auf `2b872290` und die Release-Seite
warten auf Marcos Ja (TODO 1.11).

## 6 Veröffentlicht

Mit Marcos Ja („push main bis 18304a1e, Tag v0.97.1-beta auf 2b872290, Release-Seite als Vorabversion veröffentlichen"):
`main` `46f87430..18304a1e`, Tag `v0.97.1-beta` (annotiert) auf `2b872290`; Quellarchiv aus einem frischen Klon am Tag (alle vier
Submodule von GitHub aufgelöst), `SHA256SUMS`; Release-Seite erst als Entwurf, Prüfsummen der hochgeladenen Dateien gegen die lokalen
verglichen, die verlinkten Seiten auf `main` gelesen, dann als Vorabversion veröffentlicht und abgemeldet gelesen.

**Fund beim Veröffentlichen** (aus dem Code, nicht ausprobiert): `h713-install` prüft bei einem Release-Abbild nur die eMMC-Größe,
nicht das Board - L018 und HY310 teilen sie. Die Notizen warnen („Take the archive of your own board"), TODO 5.26.
