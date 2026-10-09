# 177 - R2 abgenommen und in `main`: Abnahmereihe V4 auf r2test4, Ton nach dem Standby, Aufräumen (09.10.2026, 16:45)

**Kurz:** Marco gab um 15:53 frei: R2 nach `main`, wenn es abgenommen ist und die Pfade stimmen, ohne Push. Gebaut wurde
r2test4 aus dem Merge `c4a3924` (Zweig `integration/r2-main`: `versuch/r2-standby` in `main` b57fd01), eingespielt am
HY310 und mit der Reihe V4 gemessen: 6 von 6 Standbys mit Bild und Audio-DSP zurück, Marco hörte den Ton. Danach `main`
per Fast-Forward auf `c4a3924`, Worktrees entfernt, ein Referenzabbild behalten. Nichts gepusht. Protokoll:
`arbeit/crust-20261007/STATE.md` 15:53-16:58.

## 1 Was in `main` kam

- Kernel `0225`-`0244`: MIPS-Neustart aus Linux (`0225`-`0235`), kein LINK-Lesen nach dem Park (`0236`, `0237`,
  `doku/176`), Display-Takte über den Schlaf aus (`0238`, `0241`, `doku/171`), TV-Top vor dem Start aus dem Park (`0239`,
  `0242`, `doku/172`), Aufnahme-Stopp vor dem Standby (`0240`, `doku/173`), msp-Insel nach jedem Standby verloren (`0243`),
  PPU-Meldungen (`0244`). Serie 268 Patches.
- crust `ecf2ddc` (eigener Fork, noch kein Submodul: der HY310-Bau braucht `CRUST_SRC`, TODO 5.15), TF-A `175c6948f`,
  U-Boot `87b2a44`; Userspace `h713-power` mit Standby-Haken und `h713-mips-restart` mit dem DSP-Neuaufbau; Zeitschalter
  16 s (`70edea5`).
- Patchspiegel nachgezogen und am Baum-Hash geprüft: `uboot-h713` 96 Patches, Kopf `87b2a44`; `tfa-h713` 27 Patches, Kopf
  `175c6948f`; `crust-h713` 80 Patches, Kopf `ecf2ddc`.
- Konflikte beim Merge nur in `TODO.md` (2.26/2.27 aus `main` behalten, der VSDB-Punkt aus R2 wurde 2.28) und
  `doku/INDEX.md` (neu erzeugt). Tore grün: `release/tor.sh`, 427 Installer-Tests, 56 h713-power-Tests.

## 2 Abnahmereihe V4 (r2test4)

r2test4: `build-all.sh` mit Ausgang 0, 268 Patches, Kernelbaum gleich r2test3 (`76289cdd`), "reproducible: yes"; andere
Hashes nur bei U-Boot, FIT, Mesa und rootfs (Quellzeitstempel, neues `h713-mips-restart`). Eingespielt 16:34, Kernel aus
`c4a3924`, Host-Schlüssel gleich, MIPS und msp "running".

| Reihe | Ablauf | Ergebnis |
|---|---|---|
| V4 (v4-1 bis v4-6) | je ein Standby über den h713-power-Pfad, RTC 20 s | 6 von 6: Bildpfad 4,1-5,3 s nach dem Wecken, "audio DSP rebuilt (attempt 1)" jedes Mal, Boxkamera live |
| Hörtest | Laptop-Ton über HDMI nach den sechs Standbys | Marco: gehört |
| 7. Standby (`doku/175` §3) | RTC 20 s | Bild und Audio-DSP zurück (attempt 1), HDCP 1.4 Enabled nach 2 s |

Zwischendurch starteten vier Läufe nicht. Das war mein Fehler: zuerst habe ich den Mitschnitt nicht abgewartet, dann traf
`pgrep -f` die eigene Befehlszeile. Die Läufe wurden mit einem Skript (`v4-rest.sh`) nachgeholt.

## 3 Der DSP-Neuaufbau, alle Zählungen

| Wo | Weg | Neuaufbauten | im 1. Versuch | im 2. Versuch | gescheitert |
|---|---|---|---|---|---|
| `doku/174` §2, r2test3 | `echo 1 > reset` von Hand | 4 | 3 | 1 (erst Mailbox-Timeout) | 0 |
| `doku/174` §2, r2test3 | `h713-mips-restart` | 1 | 1 | 0 | 0 |
| V4, r2test4 | `h713-mips-restart` | 6 | 6 | 0 | 0 |
| 7. Standby, r2test4 | `h713-mips-restart` | 1 | 1 | 0 | 0 |
| **zusammen** | | **12** | **11** | **1** | **0** |

Mit dem Skript (bis drei Versuche) 8 von 8 im ersten Versuch. Vormittags auf r2test2 (ohne `0243`) war ein einzelner
Versuch von Hand gescheitert (`doku/174` §2); ob `0243` oder der Zeitpunkt den Unterschied macht, ist nicht getrennt
gemessen.

## 4 Danach

- `/etc/h713/power.conf` auf der Box zurück auf `refused = poweroff` (16:46, Marco; Sicherung
  `/root/sicherung-power/power.conf.log`), wie der Abbild-Standard.
- Worktrees entfernt (16:56): `arbeit/crust-release-20261007/wp8-bau/repo`, `arbeit/r2-20261009/repo`,
  `arbeit/r2-20261009/main-int`. Die Zweige `versuch/crust-release`, `versuch/r2-standby` und `integration/r2-main`
  bleiben als Beleg. Das Abbild, das auf der Box läuft, liegt als Referenz in `arbeit/r2-20261009/abbild-r2test4/`
  (sha256 geprüft, mit Installer-U-Boot und sunxi-fel).
- Gepusht ist nichts. Reihenfolge, wenn Marco ja sagt: erst die Forks (U-Boot `h713-hy310` auf `87b2a44`, TF-A
  `sun50i-h713` auf `175c6948f`, der crust-Fork neu auf GitHub), dann `main`.

## 5 Offen

2.29 (Standby oder Ausschalten im Release, mit Marco besprechen), 5.14 (Reste der Durchsicht), 5.15 (crust als Submodul),
der Text der msp-Meldung in `0243` ("until a reboot"), die Leistung im Standby, HDCP 2.2 von einer Quelle nach dem
Neustart (nicht gemessen), 9.0 (schneller ans Bild, nach dem Release).
