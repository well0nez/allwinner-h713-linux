# 228 - Messung Schritt 3: minpeters 0336 (DDC-Porttabelle), `h713-tv`-Tabelle und `h713-mode` an HY310 und HY300PRO-G-EU (03.11.2026)

Protokoll. Paket `arbeit/schritt3-messung-20261103/` (nicht im Repo): `BERICHT.md`, `vorher/`, `nachher/`, Logs. TODO 4.18 (3).

## 1 Frage

PR #6 (minpeter, HY320) sagt in Kernel `0336`: Die Hersteller-ARISC-Firmware liest die Tabelle ihres DDC-Schreibers mit Byte-Loads
und sieht sie unter dem Little-Endian-Fenster unserer Bootkette verdreht; Port 0 und 2 bekommen den Datensatz des anderen, Port 1
wird nie beschrieben. Gemessen hatte er das am HY320 (Buchse Port 1). Unsere Boards (Buchse Port 0) laufen mit derselben Firmware.
Vor `main`: vorher/nachher an HY310 und G-EU, dazu seine zwei Userspace-Änderungen, die auf jedem Board laufen.

## 2 Abbilder

`v0.97.2-mess0336` aus seinem PR-Kopf `98a82de6` (Zweig `versuch/schritt3-messung`, nur der U-Boot-Gitlink auf `26f974b8d6a`,
derselben Baum wie sein alter Hash), `release/build-all.sh --profile media,desktop`, ohne `--standby`, 371 Serienpatches, je ~37 min,
Prüfschritt grün. HY310 und `hy200-qz713df-a1/projector05061226`.

## 3 Verfahren

- DDC-RAMs `0x07091c00/1d00/1e00` über `/dev/mem`: mit offenem Gate `0x07091b04 = 0x7` lesen alle drei Null; Gate für ~10 ms auf 0
  (wie die Firmware beim RequestEDID), lesen, zurück auf 0x7. Eine laufende Quelle mit HDCP-2.2-Sitzung hat das ohne Folgen
  überstanden (G-EU vorher).
- Kernel-Log (`dmesg`), `h713-tv ctl status`, mit Quelle Signal/Ton/HDCP. Kein debugfs im Release-Kernel, kein UART (Proxy des
  HY310 tot), darum alles per ssh.
- Installation: Sicherung (`/etc/h713`, Hostschlüssel, `fw_printenv`), `h713-fel --yes`, `h713-install --small` mit dem kleinen
  Abzug der Erstinstallation, Sicherung zurück; Neustart von Hand (USB, Netz, Power-Taste). Secure Storage beide Male byteweise
  unverändert, Gate blieb 1 (der Fund 2.137 trat nicht auf).

## 4 Ergebnis

| | HY310 vorher (v0.97) | HY310 nachher | G-EU vorher (v0.97) | G-EU nachher |
|---|---|---|---|---|
| DDC-RAMs Port 0/1/2 | EDID / Zufall / EDID | EDID / EDID / EDID | EDID / Zufall / EDID | EDID / EDID / EDID |
| `DDC port table ... in the firmware's byte order` | - | ja, `0x15b6c` | - | ja, `0x15b7c` |
| HDMI 1080p60, Ton 48 kHz, HDCP 2.2 | Abnahme 22.10. | ja | ja | ja, `HDCP Process cost tick:643` |
| `HdmiRx_HDCP14_LoadKey time out` beim Start | 3 | 3 | 3 | 3 |
| EDID-Sequenzen Port 0 | 5,0 s und 8,5 s | 5,0 s und 9,8 s | 6,4 s und 10,3 s | 5,5 s und 10,5 s |
| `h713-tv` erkennt die Firmware (seine Tabelle) | - | `HY310 (QZ713 V3.1)` | - | `HY310 (QZ713 V3.1)` |

Port 0 und 2 hielten vorher je den Datensatz des anderen (Byte 166 des CEA-Blocks: 0 bzw. 2); nachher hat jeder Port seinen (0, 1, 2).
Die Tabelle liegt in drei Firmware-Builds an drei Adressen (HY320 `0x15838`, HY310 `0x15b6c`, G-EU `0x15b7c`); der Treiber fand sie
jedes Mal über die Befehlsfolge des Schreibers. **0336 bestätigt, keine Regression gesehen.** Alle drei Teile nach `main` (Marco, 03.11.).

## 5 Nicht gemessen, Nebenbefunde

- HDCP 1.4 nach Messregel (Nullen-Push -> Desired, Push -> Enabled): U-Boot-Kette, von 0336 nicht berührt; die Quelle verhandelt 2.2.
- `h713-mode` (WLAN-Neustart nach Schlaf): kein Standby in den Abbildern, Code läuft dort nie.
- Bild auf der Wand: Marcos Auge (HY310 Launcher und HDMI-Wahl, Ton gehört).
- **Ton unter dem Launcher** (HY310, Messabbild): Marco hörte den Stick im Launcher, `h713-tv` meldet dort "muted under an opaque
  page". Nicht aus seinem Zweig (Mute-Pfad unberührt), nie mit tönender Quelle gemessen -> TODO 2.150.
- G-EU-Boot mit steckender Quelle: 3x `source 1920x1080 at 43/36/45 Hz: ... no lock` zwischen HPD-Puls und zweiter EDID-Sequenz
  (7,3-8,5 s), dann Lock und Audio bei 12,7 s. Vorher nicht vergleichbar (Quelle kam nach dem Boot). Offen.
- UART-Proxy des HY310 (`.224`) ohne Strom oder andere Adresse; nichts auf 2000/2001 im Netz.
