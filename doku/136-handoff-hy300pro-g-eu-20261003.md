# 136 - Handoff HY300PRO-G-EU (Marcos eigener HY300 Pro), Stand 03.10.2026 ~01:30

Einstieg fuer die naechste Sitzung. Alles hier ist entweder gemessen (mit Fundstelle) oder ausdruecklich als Vermutung markiert.

**Aktueller Folge-Handoff mit Git-Stand, beiden Korrekturen und erfolgreichem Bildtest: [137](137-handoff-hy300pro-bildfehler-lvds-gamma-20261003.md).**

**Nachtrag Bildfehler gefunden:** Der isolierte Wechsel von 6 auf Stock-8-Bit-LVDS brachte eine eindeutige positive Rueckmeldung am Bild. Der alte Bootcode setzt weiterhin 6 Bit; der erfolgreiche Wert ist bisher nur zur Laufzeit gesetzt. Details und aktueller Teststand in Abschnitt 8. Die vorherigen Vermutungen sind keine Diagnose.

## 1 Das Geraet

| | |
|---|---|
| Packung | **HY300PRO-G-EU** |
| Platine (Aufdruck, von Marco abgelesen) | **HY200 QZ713DF A1** - dieselbe Platine wie cstengers Bench-Board / Profil `hy200_qz713df_a1` |
| Stock | Android 11, Build `projector.20250506.122807` (06.05.2025), Fingerprint `Allwinner/h713_tuna_p3/h713-tuna_p3:11/RP1A.201005.006/projector05061226` |
| eMMC | 15273600 Sektoren (3712 mehr als HY310), 26 Partitionen (Reserve0_a/_b) |
| DRAM | boot0 792 MHz, Woerter = HY310 bis auf tpr13 (0xb4016103) |
| Display | `display.bin` = HY310-Revision (16c74a28...), Projekt **0x34**, Panel 1280x720 (1360x760, 62 MHz), `panel_config.ini` PWM Kanal 5 / low / 40 kHz |
| Gemessen am Geraet | Luefter-Tacho **PH13** zaehlt (5520-5610 RPM); Beschleunigungssensor **sc7a20 vorhanden** (IIO); **keine Kamera** (kein Capture-/USB-Geraet); ARISC-Resolver ok (g_Data 0x1724c) |
| Nicht das Board von Issue #1 | Melder: Android 10, 636 MHz, 25 Partitionen, eigene display.bin - aber dasselbe Panel/Projekt 0x34 und derselbe Absturz seit test8 |

## 2 Zugang

| Was | Wie |
|---|---|
| SSH | `ssh hy300pro` (root, `~/.ssh/id_ed25519`, WLAN STA im Heimnetz, DHCP **192.168.8.246**; Alias in `~/.ssh/config`) |
| UART | `nc 192.168.8.180 2000` (ser2net am Orange Pi). **Der Adapter haengt jetzt am HY300 Pro, nicht mehr am HY310.** Nur ein Client gleichzeitig - wer mitschneidet, blockiert Marco. Mitschnitte: `umbau/work/_geu1-build/uart/` |
| FEL | FEL-Taste halten, Strom an; A-auf-A-Kabel speist parallel (vor Stromzyklus ziehen). `sudo -n` ist auf dem Host passwortlos |
| Desktop-Automount | Cinnamon haengt die eMMC sofort schreibbar ein (am 02.10. Journal-Recovery auf zwei Android-Partitionen). Gegenmittel ohne Einstellungsaenderung: `umbau/work/_geu1-build/ro-guard2.sh` (setzt Platte + Partitionen sofort ro, haengt aus) |
| WLAN | Marco hat `/etc/h713/wifi.env` selbst auf STA gestellt (Passwort nie von Claude eingeben) |

## 3 Was gemacht wurde

1. **ADB-Abfrage** (nur lesend) und **voller Dump** per FEL+UMS mit `dd`: `re/device-dumps/hy300pro-plus-marco/emmc-full.img` (geschlossen, sha256 `af2deb6a...`), `h713-extract-out/`, Partitionskopien `partitions/`.
2. **Profil + Board** (Paket **GEU1**, `umbau/work/GEU1/`, Bericht `REPORT.txt`, Log `LOG.txt`): Profil `hy300pro_g_eu`, Board `boards/hy300pro-g-eu/`, U-Boot-Defconfig + DT, Kernel-DT 0167 (Tacho PH13, Motor aus, Backlight-Knoten aus, PWM-Woerter), Installer folgt der eMMC-Groesse des Profils, Waechter in `boards/check.sh`. Vier Runden, drei unabhaengige Reviews: `umbau/work/_deepreview/geu1/REPORT*.md`. 0009 (Keystone-Unit) **zurueckgestellt**.
3. **Stock-DT** aus `vendor_boot_a`: `umbau/work/GEU1/material/stock-dt/` (Diff gegen HY310: 68 Zeilen).
4. **Testzweig** `hy300pro-g-eu` (Worktree **`umbau/work/_geu1-build/src`**, `umbau/src` = main bleibt unberuehrt): Commits 8579024 (GEU1), bc90909 (U-Boot-Gitlink), 47609ea (Aufdruck), **9079632 (Kernel 0168)**. U-Boot-Fork-Zweig `hy300pro-g-eu` im Worktree `mainline/external/u-boot` (bed99d1, c459ea7). Nichts gepusht.
5. **Testbild** `h713-hy300pro-g-eu-v0.96-geu1-TEST` (Bau 02.10. 22:49, `release/build-all.sh --board hy300pro-g-eu --test-image`), Ordner **`umbau/build/release-hy300pro-g-eu-geu1/`**. Probe ohne Schreiben und Installation am Geraet ok, Secure Storage unveraendert.
6. **Erster Boot:** zwei Abstuerze um 5,5-5,9 s (PID 1 `el0_undef` / ext4-Zaehler im RAM) = Speicherbeschaedigung. Ohne `allwinner,backlight-pwm-info` Boot bis Login.
7. **Ursache gefunden und behoben (Kernel 0168):** 0166 schickte `Thal_Vp_SetBacklightPwmInfo` sechs Parameter; die Firmware nimmt **einen**, die Adresse einer 24-Byte-Struktur (display.bin 0x8B10A444, Stock `libhaldisplay` 0xA20C mit `CPUComm_Malloc`). Sie dereferenzierte die Kanalnummer 5 als Adresse. Fix: die sechs Woerter in den gemappten Shared-Memory-Slot +0x037100, Adresse als einziger Parameter. Am Geraet bestaetigt: Boot bis Login, `backlight PWM: channel 5 ...`, `init sequence complete (23 calls)`. **Betrifft auch den Melder (Issue #1), test8/test9** - noch nicht gemeldet.

## 4 Aktueller Zustand des Geraets

- Installiert: das Testbild; `/boot/h713-kernel.fit` = **Original mit PWM-Eigenschaft**, daneben `h713-kernel-nopwm.fit` und `h713-kernel.fit.orig`.
- Modul `sun50i-h713-hdmirx.ko` = **mit 0168** (handgebaut, md5 eb44ae20...), altes unter `/root/sun50i-h713-hdmirx.ko.orig`.
- Bootet stabil bis Login, HDMI-Eingang geht sofort (1920x1080p60), Konsole und Bild sichtbar.

## 5 Das offene Problem: Bild "schwach"

Marcos Beschreibung: **grosser, heller weisser Lichtkegel, aber der Bildinhalt schwach**; Kontrast 100 wirkt sofort "uebersteuert". Daraus (gemessen/gesehen):
- Die Lampe ist an; das Panel folgt den Bilddaten (Kontrast aendert das Bild sichtbar).
- PWM-Block 0x02000c00: alle 8 Kanaele 0 bei offenem Bus-Gate (CCU 0x7ac = 00010001) - niemand programmiert PWM5. s_pwm 0x07020c00: nur Kanal 1 aktiv (PPR 00770055).
- Gamma aus `ProjectID_0x0034.TSE`: normale Form (Mitte 2483/4092), aehnlich HY310 0x30 - erklaert es allein wohl nicht (nicht am Geraet A/B-getestet).
- Release-Kernel hat **kein debugfs** -> `h713-tv ctl rpc` geht nicht.

Vermutungen (nicht belegt): DLP-Controller-Einstellung fuer dieses Panel (Stock stellt ihn evtl. per I2C/Dienst ein), Bereich/Pegel, Stock-Handover `PanelControl::switchToMipsPWM` (`/sys/class/backlight/tv/bl_power` 4 -> 0, Treiber vermutlich Vendor-Modul in `vendor_a`).

**Naechste Schritte (offline zuerst):**
1. Stock-Kette fuer 0x34 lesen: Stock-DT-I2C-Geraete (DLPC?), Vendor-Module aus `vendor_a` (aus dem Dump ziehen), `libtvpq`/`PanelControl` (AP3-Material `umbau/work/AP3/`, `umbau/work/AP1/material/lib/`).
2. Abgleich mit Issue #1: der Melder hat bei test7 720p/1080p und Gamma als richtig bestaetigt, nur die Lampe war dunkel - was hat sich seither geaendert, was ist beim HY300PRO-G-EU anders?
3. Marco macht ein Wandfoto wie sein Stock-Referenzfoto (gleicher Abstand/Bild) als Vergleich.
4. Erst dann gezielt am Geraet testen; jeden Schritt vorher ansagen. Keine Regler-Raterei (Marco, 03.10.).

## 6 Weitere offene Punkte

- 0168 in `main` uebernehmen und dem Melder melden (Issue #1) - nur auf Marcos Wort.
- 0009 (Keystone-Auto ohne Sensor) zurueckgestellt; besserer Fix: Skript wartet still auf den Sensor (FOLLOW-UP in `umbau/work/GEU1/REPORT.txt`). Auf diesem Board ist der Sensor ohnehin da.
- Profile `hy300pro_g_eu` und `hy200_qz713df_a1` zusammenfuehren (gleiche Platine) - nach dem Geraetetest.
- Hardware-Merkmale pro Board optional machen (Kamera, Motor, Sensor) - `doku/61-todo.md`, noch nicht geplant.
- Installer: `restore-stock` kennt nur die HY310-eMMC-Groesse.
- Kosmetik: U-Boot/BL31-Versionsstring ohne Git-Hash (Worktree-.git im Container nicht aufloesbar); `fdtfile=allwinner/allwinner/...` doppelt (auch in test9, vorbestehend).

## 7 Fundstellen

| Was | Wo |
|---|---|
| Dump, Extraktion, Partitionen | `re/device-dumps/hy300pro-plus-marco/` (geschlossen) |
| Paket GEU1, Bericht, Log, Material | `umbau/work/GEU1/` |
| Reviews | `umbau/work/_deepreview/geu1/REPORT.md`, `REPORT-round2.md` (+ r2/, r3/ Skripte) |
| Briefs | `umbau/plan/briefs/GEU1.md`, `GEU1-review.md` |
| Testzweig-Worktree, Bau-Log, UART-Mitschnitte, Waechter | `umbau/work/_geu1-build/` (`src/`, `build-all.log`, `uart/`, `ro-guard2.sh`) |
| Testbild-Ordner | `umbau/build/release-hy300pro-g-eu-geu1/` |
| Test-FIT ohne PWM | `umbau/work/_geu1-build/nopwm/` |
| Kernel 0168 | Zweig `hy300pro-g-eu`, `mainline/patches/kernel/0168-media-hdmirx-backlight-pwm-info-by-address.patch` |
| IDA (display.bin, libhaldisplay) | Kopien im Scratchpad der Sitzung; Original-DB `re/ida/IDA_hy310/display.bin.i64` (byte-gleiche display.bin) |
| Issue #1 Volltext | `umbau/work/_deepreview/hy300pro-marco/issue1.txt` |
| Vergleich mit dem Melder | `umbau/work/HY300PROG/VERGLEICH-melder.md` |
| TODO | `doku/61-todo.md` (Eintraege 02./03.10.) |

## 8 Nachtrag: LVDS-Farbtiefe und RGB-Gamma

Die Stock-Tabelle fuer Projekt 0x34 schreibt `0x05800000 = 0x01e0a40c`.
Unser U-Boot aendert das auf `0x01e0a404` (`h713_panel_cfg_board_b.lvds_bitsel = 0`).
Die Stock-Funktion `libpq:lvds_set_bitwidth` bei 0x387c belegt die Bedeutung
von Bits 4:3: 6/8/10 Bit werden als 0/1/2 codiert. Das ist anhand des
Assemblercodes geprueft, nicht aus dem XML-Enum abgeleitet. Das eigene
`panel_config.ini` verlangt `ColorDepth=8`.

Nach ausdruecklichem Go wurde nur Bit 3 am laufenden Geraet auf den
Stock-Wert gesetzt, ohne Neustart oder andere Bildaenderungen. Ausgangswert
und Ruecklesen stimmen exakt (`lvds-stock8-result.json`). Die unmittelbare
Rueckmeldung am Bild war eindeutig positiv. Der TV-Dienst blieb aktiv,
HDMI 1080p60 und die Video-Plane laufen. Ein kalter Neustart mit korrigiertem
U-Boot sowie der Fotovergleich mit Stock stehen noch aus.

Zuvor wurde ein zweiter Fehler korrigiert: `h713-tv` legte nur die rote
Stock-Gammakurve auf alle drei Farben. Die Kurven des eigenen TSE unterscheiden
sich; die Testversion laedt alle drei (6144 Bytes). Cross-Build und ein
C-Loader-Test mit getrennten Kanaelen und Dateilaengen sind bestanden.
Der vom Nutzer gewuenschte Vergleich alt / zehn Sekunden / neu brachte
keinen nennenswerten sichtbaren Unterschied. Die RGB-Korrektur allein
loeste den Bildfehler also nicht; sie bleibt als sachlich korrekte
Farbdatenverarbeitung im laufenden Testprogramm.

Aktueller Geraetestand: RGB-Testprogramm in `/usr/local/sbin/h713-tv`,
Sicherung `/root/h713-tv.before-rgb-gamma-20261003`; LVDS zur Laufzeit auf 8 Bit.
**Neustart setzt momentan die falschen 6 Bit wieder.** Keine Flashdatei,
kein Bootartefakt und kein `umbau/src`-Main wurden fuer diese Tests geaendert.

Alle neuen Quellen, Nachweise, Testprogramme und Korrekturpatches:
`umbau/work/GEU1-image-analysis/`, Einstieg `FINDINGS.md`.
`0002-uboot-project34-restore-stock-8bit-lvds.patch` ist vorbereitet und
gegen den isolierten U-Boot-Testzweig mit `git apply --check` geprueft,
noch nicht angewendet oder gebaut. Der Nachweis gilt zunaechst fuer dieses
Geraet; auf dem Geraet des Issue-Melders ist die Korrektur noch nicht getestet.

## 8 Nachtrag 03.10. ~01:50 - Bild gefixt, auf main committet

- Ursache "schwaches Bild": U-Boot setzte fuer Projekt 0x34 `0x05800000[4:3] = 0` (6-Bit-LVDS) statt Stock 1 (8 Bit; libpq
  `lvds_set_bitwidth` 0x387c, dieselbe libpq.so in Marcos vendor-Partition, sha 12b1d910...). HY310-Zeile (0x30) war immer 1.
  Gefunden in der Analyse `umbau/work/GEU1-image-analysis/` (FINDINGS.md), dort live per /dev/mem bestaetigt.
- Dazu RGB-Gamma: h713-tv legte die rote TSE-Bank auf alle drei Kanaele (Weissabgleich verloren) - betrifft auch den HY310.
- Kaltstart mit neuem U-Boot (nur hy310-uboot/mmcblk0p2 geschrieben, Sicherung `/root/hy310-uboot-backup-20261003.bin`):
  Register `01e0a40c`, Marco: "sieht gefixt aus".
- **main** (umbau/src) per Fast-Forward auf `bf72eb3` (GEU1 + 0168 + RGB-Gamma + U-Boot-Gitlink); U-Boot-Fork `q-integration`
  auf `2de0cc8`. **Nicht gepusht.** Identitaetspruefung der neuen Commits: nur well0nez (noreply).
- Auf dem Geraet laufen h713-tv aus der anderen Sitzung (gleiche Aenderung) und das handgebaute hdmirx-Modul mit 0168; ein
  sauberes Testbild aus main ist noch zu bauen.
