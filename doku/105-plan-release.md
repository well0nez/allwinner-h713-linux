# Plan 105 — Release: den HY310-Stand für andere nutzbar machen

**Status: Plan, 10.09.2026 02:00 — Zuschnitt „Entwickler-Vorschau v0.1“ (Marco: der logischste Weg).** Freimachen **nur über FEL**
(Gehäuse auf, Pad, selbstgebautes A-auf-A-Kabel mit getrennter VBUS-Ader — mit Foto dokumentiert); Image-Neupacken, Stock-UI-Update und
arm32-Installer sind **Ausbaustufe v0.2** für Nutzer ohne Schraubendreher. Damit bleiben drei Arbeitspakete plus Doku: R1 Boot vom Gerät,
R2 Extraktion, R3/R4 Repo und README. Ziel: Freigabe, damit andere testen und profitieren. Voraussetzungen laut Marco:
Bootloader komplett von uns und vom Gerät bootend; Doku zu allem (läuft / portiert / fehlt / ungetestet); Extraktionsskripte für die
proprietären Teile aus dem Firmware-Image (kein ADB: nicht alle sind gerootet); der Env-Patcher als Freimach-Schritt. WLAN, Bluetooth, Cedrus sind nicht unsere Baustelle (ungetestet markieren).

**Entschieden (Marco 09.09.):** Repo = das alte **`well0nez/allwinner-h713-linux`** (dort folgen schon Leute; ein neues ginge unter). Offen: Sprache
der README/Matrix (Vorschlag Englisch, Tiefen-Doku bleibt Deutsch).

## 1. Ausgangslage, präzise

- **Boot-Kette am Gerät ist heute komplett unsere:** BootROM → **SPL an LBA 16** (unsere) → **BL31** (unser TF-A) → **U-Boot proper** an `0x49ac00`
  (unser, mit Gate). Env bei `0x49ec00` (Byte-Offset `0x93d80000`), SPL-Parkplatz `0x49cc00` — alles im `empty`-Bereich, keine Vendor-Partition
  wird beschrieben ([`20`](20-flashen-und-recovery.md)). Vendor-Kette bleibt als Rückweg liegen: boot0-Zweitkopie LBA 256, Vendor-U-Boot TOC1.
  **Was am Gerät bleiben muss:** `bootloader_b` (p2, 32 MB) — U-Boot liest daraus `mips/display.bin`, `mips/display_cfg.xml`, `mips/LogoRegData.bin`
  (`h713_mips.c:5980-6024`). Beide können jederzeit komplett neu geflasht werden (SPL + proper, Weg 4 in `20`).
- **Was noch nicht vom Gerät kommt:** Kernel (TFTP) und Rootfs (NFS). Das ist Paket R1.
- **Freimachen eines Stock-Geräts** existiert im Legacy-Repo: `legacy/tools/patch_env_usb.py` schreibt `env_a` (p3, CRC32) mit `usb start;` im
  `bootcmd`, `env_a` kommt per `adb shell dd` **ohne Root** (magcubic-root-Verfahren, `legacy/FLASHING.md:59-125`) oder aus `env.fex` eines
  Firmware-Images; danach bootet der Vendor-U-Boot vom USB-Stick (`FLASHING.md` Method 1) → von dort flashen wir unsere Kette (Method 2).
- **Proprietär, nicht ins Repo:** ARISC `scp.bin` (aus dem TOC1-Paket), `hy310-edid.bin` (= `HDMI_EDID_14.bin` + `HDMI_EDID_20.bin`),
  `msp-patch.bin` (aus `libmspsound.so`), PQ-Daten (`pq_picturemode.ini` u. a.), MIPS-Dateien (bleiben in `bootloader_b`). Referenz-Prüfsummen:
  scp `d41731fa…`, EDID `70d10294…`, MSP `235be48f…`. Marco hat zwei H713-Firmware-Images; welche weiteren Firmwares laufen, ist unbekannt.
- `mainline/` = `cstenger/allwinner-h713-mainline@8860991` (Kernel 6.18.38); seine 0001–0090 stammen überwiegend aus Marcos Legacy-Repo
  (`PROVENANCE.md`); unsere Serie `0091`–`0140`, U-Boot `0017`–`0020`, TF-A-Commits, Userspace, Doku. cstenger ist auf anderer Kernelversion
  und Display-Architektur ([`80`](80-vergleich-baeume.md)).

**Strategie:** Overlay-Release im alten Repo auf dem festen Commit — ehrlich benannt, reproduzierbar, kein Rebase. Generische Fixes zusätzlich
als kleine PRs an cstenger. Rebase auf seinen aktuellen Baum erst, wenn WLAN/BT/Cedrus von dort gewollt und sein Baum ruhig ist.

## 1.1 Inventar der proprietären Teile (Stand 10.09. 00:15, aus U-Boot, Kernel-Serie und Userspace gegriffen — zu vervollständigen in R2)

| Datei | Wer lädt sie | Woher im Stock | Umgang im Release |
|---|---|---|---|
| `mips/display.bin`, `display_cfg.xml`, `LogoRegData.bin`, `database.TSE`, `pq_custom.TSE`, `projecttable.TSE` | U-Boot `h713_disp` aus `mmc 1:2` = `bootloader_b` | Partition p2 (FAT), auf jedem Gerät | **bleiben am Gerät**, Partition unangetastet; Prüfsummen im Manifest |
| `h713-arisc.bin` (= Stock `scp.bin`) | Kernel `0091` (`/lib/firmware`) | TOC1-Bootpaket (Vendor-U-Boot-Bereich LBA 24576/32800) oder Firmware-Image | **extrahieren** (R2) |
| `hy310-edid.bin` (= `HDMI_EDID_14.bin` + `HDMI_EDID_20.bin`) | Kernel `0091` | Vendor-Dateisystem (`/vendor/etc/…`, Pfad in R2 festhalten) | **extrahieren**; proprietär, bleibt Stock (Marco) |
| `h713/msp-patch.bin` | Kernel `0137` | `libmspsound.so` (Vendor-Lib), Patchstrom mit MSPM-Blöcken | **extrahieren** mit Strukturprüfung |
| PQ-Daten (`pq_picturemode.ini`, Panel-/Gamma-Tabellen) | `h713-pq` offline → `gamma-standard.bin`, Presets in `h713-tv` | `/vendor/etc/` | Quelle **extrahieren**; die von `h713-pq` abgeleiteten Tabellen sind Rechenergebnisse aus Stock-Daten — Lizenzfrage klären (Vorschlag: zur Laufzeit aus den extrahierten INIs rechnen, nichts Abgeleitetes einchecken) |
| WLAN/BT-Firmware (aic8800) | cstengers Treiberpaket | AIC-Firmwarepaket (Vendor `/vendor/etc/firmware`) | ungetestet; Herkunft und Lizenz in R2 klären, sonst „nicht enthalten" |
| HDCP-Schlüssel, DRM-Keys | — (nicht genutzt) | Secure-Bereich | **nie** anfassen, nicht extrahieren |
| Vendor-Bootkette (boot0 LBA 16/256, TOC1) | — | roh auf dem eMMC | LBA 16 wird ersetzt (unsere SPL), LBA 256 und TOC1 bleiben als Rückweg |

Regel: Nichts davon ins Repo; `h713-extract` erzeugt alles mit Manifest (Pfad, Größe, SHA-256, Herkunft) auf dem Gerät des Nutzers.

## 1.2 Layout R1 — verbindlich (10.09. 21:45, aus der Live-GPT `analyse/boot/gpt-stock-20260910.txt`)

eMMC 15.269.888 Sektoren (7,28 GiB). Boot-Kette liest rohe LBAs: SPL LBA 16, U-Boot proper 4828160 (`0x49ac00`), SPL-Parkplatz 4836352, Env 4844544
(Byte `0x93d80000`). U-Boot liest die MIPS-Dateien aus **Partition 2**. Alles außer p1–p4 und dem U-Boot-Bereich wird neu vergeben.

| # | Name (PARTLABEL) | Start-LBA | Sektoren | Größe | Inhalt |
|---|---|---|---|---|---|
| 1 | `bootloader_a` | 73728 | 65536 | 32 MiB | Vendor, unverändert (GUIDs bleiben) |
| 2 | `bootloader_b` | 139264 | 65536 | 32 MiB | Vendor, **MIPS-Dateien**, unverändert |
| 3 | `env_a` | 204800 | 512 | 256 KiB | Vendor, unverändert (Freimachen v0.2) |
| 4 | `env_b` | 205312 | 512 | 256 KiB | Vendor, unverändert |
| 5 | `hy310-boot` | 205824 | 131072 | 64 MiB | ext4: `h713-kernel.fit` (Kernel+DTB), optional `h713-rescue.fit` |
| 6 | `hy310-data` | 336896 | 4491264 | 2,14 GiB | ext4: Nutzerdaten, Mitschnitte (`/data`) |
| 7 | `hy310-uboot` | 4828160 | 30720 | 15 MiB | **roh, kein Dateisystem** = altes `empty`: proper @+0, SPL-Parkplatz @+8192, Env @+16384 (64 KiB, `CONFIG_ENV_SIZE=0x10000`) |
| 8 | `hy310-rootfs` | 4858880 | 10410975 | 4,96 GiB (Ende = LastUsableLBA 15269854, S41) | ext4: Debian-Rootfs (Kopie des Netboot-Roots), `/lib/modules`, `/lib/firmware/h713` |

Partitionen p5–p26 des Stock (boot_a … UDISK) verschwinden. Rückweg: Stock-Image per FEL/Hersteller-Tool; der Installer sichert vorher
GPT-Header und p1–p4 (`hy310-backup-<datum>.tar`). Namen sind die Schnittstelle für Kernel-Cmdline und Installer.

**U-Boot-Env-Schnittstelle** (Vorgabe im Abbild: `board/sunxi/hy310.env` + `CONFIG_BOOTCOMMAND`, U-Boot-Commit 0021; der Installer setzt per
`fw_setenv` nur `h713_boot=emmc`, alles andere kommt aus der Vorgabe — eine gespeicherte Env überschreibt die Vorgabe):

```
h713_boot=emmc                      # emmc | net ; "net" erzwingt Netboot
h713_gate=1                         # Bereitschaft (nur mit Gate-Build wirksam)
bootfile=h713-kernel-netboot.fit
serverip=192.168.8.104
nfsroot=/srv/h713-rootfs
bootargs_base=console=ttyS0,115200 earlycon rootwait clk_ignore_unused pd_ignore_unused cma=128M
boot_emmc=if ext4load mmc 1:5 0x60000000 h713-kernel.fit; then setenv bootargs "${bootargs_base} root=PARTLABEL=hy310-rootfs rw"; bootm 0x60000000; fi
boot_net=dhcp; setenv bootargs "${bootargs_base} root=/dev/nfs rw nfsroot=${serverip}:${nfsroot},vers=3,tcp ip=dhcp"; tftpboot 0x60000000 ${serverip}:${bootfile}; bootm 0x60000000
bootcmd=h713_disp init 0x30; run boot_${h713_boot}; run boot_net
```

Hush expandiert nur eine Ebene, deshalb werden die Bootargs dort zusammengesetzt, wo sie benutzt werden.
**Env-Ort gilt nur mit U-Boot-Commit `0022`** (Env-Offset-Fix, [`30` §16](30-uboot-aenderungen.md)); der Installer setzt die Boot-Kette
(`bootcmd`, `boot_emmc`, `boot_net`, `bootargs_base`, `h713_boot`) immer, ergänzt Gerätewerte (`h713_gate`, `serverip`, …) nur, wenn sie fehlen.
Fällt der eMMC-Boot durch (keine Datei, kaputte FIT), läuft `boot_net` als Rückfall; ohne TFTP endet U-Boot am Prompt wie heute.
`fw_env.config` auf dem Rootfs: `/dev/mmcblk0 0x93d80000 0x10000`.

## 2. Pakete

| Paket | Inhalt | Hängt an |
|---|---|---|
| **R0 Freimachen per FEL (v0.1)** | ✓ **Der FEL-Boot läuft seit 10.09.** ([`S44`](nachtlog/S44-fel-boot.md)): ein einziger `sunxi-fel uboot`-Aufruf bringt das Gerät zum U-Boot-Prompt, drei Sekunden, kein Byte auf die eMMC. Bleibt: das PC-Skript `h713-fel-install` drumherum. Nutzer **hält die Reset-Taste gedrückt und steckt den Strom ein** (Marco, 10.09. — kein Pad, kein Gehäuse öffnen, kein Löten; die frühere Pad-Beschreibung war überholt), A-auf-A-Kabel (VBUS beidseitig offen, Foto in der Doku), `sunxi-fel version` muss `H713` melden; das Skript schiebt den **Restore-SPL mit eingebettetem Payload** (bewährt, `20` „Recovery über FEL") — Payload = unsere SPL nach LBA 16 — und danach bootet die Kette in unser U-Boot, das den Installer vom USB-Stick oder per TFTP lädt (R1). Rückweg identisch mit Vendor-boot0 als Payload (LBA-16-Dump liegt vor). Kein ADB, keine Env, kein arm32. **v0.2 (später):** Firmware-Image mit gepatchter Env neu packen (`awimg.py`/`sunxi-env-patcher`, Legacy-Path 1), Einspielen per Hersteller-Tool (FEL-basiert, Marcos Weg) oder Stock-UI (ungetestet), `bootcmd` bootet USB-Stick ohne UART, darauf ein arm32-Installer (Vendor-U-Boot ist 32-Bit). Test von R0 v0.1 geht am Dev-Gerät jederzeit (FEL ist stock-unabhängig). | — |
| **R1 Boot vom Gerät** | ⚠ **Layout überholt und bereits geschrieben: [`108`](108-plan-vendordaten.md) §4.3 und §7** (p1–p4 fallen weg, vier eigene Partitionen ab LBA 73728). Rootfs nach [`107`](107-plan-rootfs.md). SD-Karte als Alternative. U-Boot: `bootcmd` eMMC mit Netboot-Rückfall (`h713_boot=emmc|net`), Env-Vorgaben im Defconfig. Installer aus dem laufenden Linux (Netboot oder USB-Stick): schreibt SPL, proper, FIT, Rootfs, setzt Env. 20 Kaltstarts ohne Host. | — (größte Lücke) |
| **R2 Extraktion** | `h713-extract` (Python, plus `e2fsprogs` für ext4): Eingänge (a) Firmware-Image (Allwinner-Paket oder roher eMMC-Dump — beide Formate erkennen), (b) Partitions-Dumps per ADB (gerootet oder Einzelpartitionen ohne Root wie bei `env_a`). Ablauf: Image-Fingerabdruck (SHA-256) gegen die bekannten Images; TOC1 parsen → `scp.bin`; `vendor`/`system` ext4 lesen → `libmspsound.so` → MSP-Patchstrom extrahieren, EDID-Dateien, PQ-INIs; jede Datei strukturell prüfen (TOC1-Header, MSPM-Blöcke, EDID-Prüfsummen, INI-Parser) und gegen Referenz-Prüfsummen melden. **Unbekanntes Image:** ausdrücklich warnen, Best-Effort extrahieren, jede Abweichung als „hier drohen Probleme" benennen — Fehler fallen beim Extrahieren sofort auf. Ausgabe nach `/lib/firmware/h713/` + `hy310-edid.bin` + PQ-Ordner mit Manifest. | — |
| **R3 Repo = `well0nez/allwinner-h713-linux`** (Marco: behalten, Follower da) | **Historie bleibt, Inhalt wird umgebaut:** (1) heutigen Stand als Tag `legacy-arm32-2026-08` und Branch `legacy` sichern; (2) `main` neu aufsetzen mit dem Overlay: `patches/kernel/` (Serie + `series`), `uboot-h713/`, `tfa-h713/` (format-patch aus dem TF-A-Fork), `userspace/` (h713-tv, h713-pq), `tools/` (h713-extract, hy310-unlock, UART-Werkzeuge), `installer/` (arm32-Stick-Image, Skripte), `build/` (Container-Rezept aus `50`), `doku/` (deutsch, unverändert), `mainline/` als Submodul auf `cstenger/allwinner-h713-mainline@8860991` plus dessen U-Boot/TF-A-Submodule (oder Forks unter well0nez mit unseren Commits — Entscheidung: **Forks**, damit die Commits `0017`–`0020`/TF-A öffentlich referenzierbar sind); (3) die alte arm32-Arbeit (drivers/, dts/, mboot32-Bau) wandert nach `legacy/` **und** bleibt im Branch — der alte `Archived/`-Ordner verschwindet, README sagt klar, was aktuell ist; (4) `README.md` Englisch: Einstieg, Matrix, Installationsweg (R0), Bauen, Provenance/Lizenz, Link auf `doku/00-STATUS.md`; (5) `PROVENANCE.md` (Legacy → cstenger → hier), Lizenzen (GPL-2.0 Kernel/U-Boot, BSD-3 TF-A, MIT Werkzeuge), `.gitignore` gegen Blobs, kein `re/`, kein `h713-backups/`. Vorgehen: erst lokal als neues Git aus diesem Ordner aufbauen (Skript, reproduzierbar), Diff gegen das alte Repo, dann Push. | (b) Sprache |
| **R4 README + Matrix** | Was läuft (Display-Pfad, HDMI-Eingang mit Modustabelle, Audio, Einschalt-Gate, Ethernet, USB-Host, UART), was portiert wurde (`80`), was ungetestet ist (WLAN, BT, Cedrus, IR, Fokusmotor), bekannte Fehler (4K-Fall, EDID-Modi), Hardware (`10`), Freimachen/Flashen/Recovery (`20`, R0), Bedienung (`50`, h713-tv README). Jede Zeile mit Beleg in `doku/`. | R0–R2 |
| **R5 Qualität** | ✓ **20 Kaltstarts vom eMMC am 10.09.: 20/20 sauber** (`analyse/boot/r5-20-kaltstarts-20260910.txt`, Prüfstand `analyse/boot/kaltstart-serie.sh` — je Lauf Bootquelle, MIPS-Identität, Panel-Timing, Dienst). Offen: 20 Gate-Zyklen, HDMI-Modustabelle komplett, Audio 32/44,1/48, Recovery-Weg von zweiter Person gegangen, Stand gesichert. | R1 |
| **R6 PRs an cstenger** | 0140 EINT-Mux, 0134 CCU, 0124/0125 cpu_comm mit Messbelegen; Verweis auf das Repo. | R3 |

## 3. Reihenfolge

R1 zuerst (technisch), parallel R2 (Skripte, Agentenpaket mit den zwei Images als Testfälle); R0 v0.1 ist ein kleines Skript um den
bestehenden Restore-SPL (nach R1, weil der Installer daran hängt). R3 sobald R1/R2
stehen, dann R4, R5, zuletzt R6. Stufe 2 des Gates ([`104`](104-plan-standby-stufe2.md)) ist keine Release-Voraussetzung.

## 4. Regeln

Wie Plan 101 §4: Agenten schreiben nur in Kopien und liefern Patches; kein Blob ins Repo; jede Behauptung in der Matrix hat einen Beleg;
Netboot bleibt als Entwicklungsweg erhalten; Rückweg zum Stock bleibt immer dokumentiert und getestet.

## 5. Entscheidungen und Todos (Marco, 10.09. 00:25)

- Layout Variante B: ja, Partitionstabelle wird neu gebaut, Logo und MIPS-Dateien bleiben in `bootloader_b`; ARISC-Extraktion: ja.
- **Todo h713-pq:** Gamma/Presets zur Laufzeit aus den extrahierten INIs rechnen statt abgeleitete Tabellen einchecken; abgeleitet ist fürs Erste
  in Ordnung, wird nachgeliefert.
- **Todo aic8800:** Treiber wurde früher gehostet, Firmware vermutlich nicht — prüfen, was im Repo lag; **Lizenzstatus der AIC-Firmware klären**.
- **Todo HDCP:** läuft bei uns vermutlich nicht — Status prüfen (RX ohne HDCP-Aushandlung?) und festhalten; Schlüssel bleiben unangetastet.
- Plan bleibt schriftlich; Ausführung nach 104-Vorarbeit.

## 6. Verlauf

- **10.09. 21:30–22:15 R1 begonnen:** Live-GPT gesichert (`analyse/boot/gpt-stock-20260910.txt`), Layout und Env-Schnittstelle §1.2 festgelegt.
  U-Boot: `board/sunxi/hy310.env` + `CONFIG_BOOTCOMMAND` (Commit `ff262c56df0`, `uboot-h713/0021`), eMMC zuerst, Netboot als Rückfall;
  proper v3 = 0018 Gate + 0020 GP5-Meldungen + 0021 Env (`tftp/uboot-proper-gate-v3.bin`, CRC32 `9d485832`, 0x6c3 Sektoren) — Flash zusammen mit
  dem Installer-Test. Gate am Dev-Gerät per Env aus (`h713_gate=0`). Installer als Agentenpaket S41 (`analyse/release/arbeit/r1-installer/`).
- **Todo Rootfs (Marco 10.09. 22:25):** das heutige Netboot-Root (2,9 GB, Entwicklungswerkzeuge) ist als Basissystem zu groß — für v0.1 ein
  schlankes Rootfs bauen (debootstrap minimal + nur Beamer-Pakete: systemd, ssh, alsa, h713-tv-Abhängigkeiten), Ziel < 1 GB; Bauskript ins Repo.
  Detailgespräch mit Marco steht aus.
- **Risiko eMMC (10.09. 22:40, S41-Vorlauf):** Beim Durchlesen der ersten 2,5 GB (`dd bs=1M`) nach ~50 s `sunxi-mmc 4022000.mmc: data error cmd18
  RINT=0x00000020 … send stop command failed`; danach hängen alle Leser im D-Zustand, der Controller ist verklemmt (Bus: 8 Bit, **HS400, 200 MHz**).
  Kleine Lesungen (Proper 886 KiB, GPT) waren bisher unauffällig. **Vor dem Installer klären:** eMMC-Modus im DTS auf HS200 oder DDR52 begrenzen,
  Vollflächen-Lesetest (7 GB) ohne Fehler, Schreibtest, dann erst R1 scharf. Steckdosen-Neustart nötig (D-Prozesse blockieren `reboot`).
  **Nachtrag 22:05:** Nach Steckdosen-Neustart 2,5 GB sequenziell in 256-MiB-Schritten gelesen: 142 MB/s, 0 Fehler. Der Fehler trat unter
  gleichzeitigen Zugriffen auf (Streaming-`dd` durch `grep`-Pipe plus parallele Python-Leser). → Stresstest für R1: paralleles Lesen + Schreiben
  über die volle Fläche, dmesg beobachten; erst bei Wiederholung HS400 im DTS (`sun50i-h713.dtsi`, `mmc2`) auf HS200 begrenzen.
- **Env-Ort GELÖST (10.09. 22:25):** `saveenv` persistiert zuverlässig (Marker `SURVIVE9911` überlebte einen Steckdosen-Stromausfall). Die
  frühere Fehlsuche lag am Werkzeug: `grep` auf das rohe Blockgerät findet in binären Daten ohne Zeilenumbrüche **nichts** — nicht mal den
  Kontrollstring `eGON.BT0` bei LBA 16. Ein Python-Byte-Scanner (Chunks mit Überlappung) findet alles. Ergebnis: die gültige Env liegt bei
  **Byte 1.708.654.592 = LBA 3.337.216** (4-Byte-CRC `e10d1964`, kein Redund-Flag, 0x10000 groß), **nicht** bei `CONFIG_ENV_OFFSET=0x93d80000` der
  aktuellen Defconfig. D. h. der aktuell geflashte U-Boot wurde mit einem anderen Env-Offset gebaut als die jetzige Serie. eMMC läuft in U-Boot
  mit HS 52 MHz, unter Linux HS400 200 MHz. **Konsequenz für R1:** Env-Offset nie annehmen, immer verifizieren. Der Installer soll den Env-Block
  per CRC-Scan **selbst finden** (statt Hardcode) und `fw_env.config` daraus schreiben; für den Release-Build `CONFIG_ENV_OFFSET` fest in
  `hy310-uboot` p7 setzen und nach dem Flashen mit einem `saveenv`+Scan bestätigen. Reliabler Scanner: `analyse/release/arbeit/r1-installer/`.
- **Env-Ort, Ursache gefunden (10.09. 00:20):** die Defconfigs waren nie falsch — `env/mmc.c` schickt `CONFIG_ENV_OFFSET` durch ein `int`
  (`ofnode_conf_read_int`), `0x93d80000` wird negativ, „vom Ende" gerechnet und auf 32 Bit gekürzt = `0x65d80000`. Der Schluss von 22:25
  („anderer Env-Offset gebaut") ist damit hinfällig; v3 hätte denselben Fehler. **U-Boot `0022`** behebt es ([`30` §16](30-uboot-aenderungen.md)),
  `tftp/uboot-proper-gate-v4.bin` (CRC32 `56a6a77f`, im Container gebaut) = v3 + Fix, **noch nicht geflasht**. Installer 0.2: Env-Suche per CRC (`--env-scan`),
  `--uboot-bin` prüft den geflashten proper, `--env-migrate` übernimmt die Variablen vom Zwilling; Boot-Kette wird gesetzt statt ergänzt
  (die Dev-Env trägt das alte Netboot-`bootcmd`). Gegen Attrappe getestet (S41 §7). Das Zitat „aus der Config holen statt raten" zur
  `ENV_SIZE` stammte nicht aus S41; `0x10000` ist richtig und am Gerät per CRC bestätigt (Marco, 10.09.).
- **R2 gestartet (10.09. 00:25):** Agentenpaket `analyse/release/arbeit/r2-extract/` (`AUFTRAG.md`), Bericht S42. Testfälle: HY310
  `re/vendor/HY310/update.img` (`update_rooted.img` ist dasselbe Image mit Root, kein zweites Gerät — Marco), **L018**
  `/opt/Projekte/Beamer/L018/update.img` (zweites H713-Gerät, ohne Referenzwerte), Roh-Dump `re/device-dumps/emmc-first-300mb.bin`.
- **v4 geflasht (10.09. 00:55, über UART aus der Claude-Sitzung):** tftpboot von `192.168.8.123`, CRC `56a6a77f`, `mmc write`, Rücklesen,
  `cmp.b` 886.137 gleich; `reset` → v4 (`gfe1e801fa015`) kam mit der Vorgabe-Env (`h713_gate=1`, `serverip=.104`) → `h713_gate=0`,
  `serverip=192.168.8.123`, `saveenv`; Netboot über den v4-Rückfall `boot_net`. Aus Linux bestätigt (Installer-Precheck 0.2): proper byteidentisch,
  **gültige Env am Release-Ort `0x93d80000`** (75 Variablen), der alte Block bei `0x65d80000` liegt als Rest. GUT-Stand
  `tftp/uboot-proper.GUT-gate-v4-20260910.bin`, Vorgänger gesichert. **S41 §2.3 beantwortet:** Stock-GPT hat 26 Einträge à 128 Byte, Tabelle
  LBA 2–8, primäre Seite gültig → keine Kollision mit der SPL, `--gpt-primary auto` schreibt normal. Root belegt 3,0 GiB (`du -sx`).
- **R2 fertig (10.09. 00:50, [`S42`](nachtlog/S42-r2-extract.md)):** `analyse/release/arbeit/r2-extract/h713-extract` (Python 3 + `debugfs`).
  HY310: alle drei Referenz-Hashes; `update_rooted.img` byteidentische Ausgaben (Rooting änderte nur `boot.fex`); Roh-Dump → `scp.bin` aus
  LBA 24576 **und** 32800 (identisch). Formatbefunde: IMAGEWTY-Dateitabelle im Klartext ab 0x400 (nicht RC6), `sunxi-package` mit
  Additionsprüfsumme, `super` = Android-Sparse → LP → `vendor_a` ext4. Korrektur zu `analyse/arisc/BEFUND.md`: p1 `bootloader_a` ist FAT16,
  das Paket liegt roh bei LBA 24576/32800. aic8800-Firmware in `/vendor/etc/firmware/aic8800d80/` **ohne Lizenzangabe** → „nicht enthalten".
  HDCP: `hdcp_1.bin`/`hdcp_v22.bin` + `private`-Partition nur beobachtet, nicht angefasst; v0.1 = „kein HDCP".
- **L018 ist ein eigenes Gerät (Marco, 10.09. 00:40).** Der erste Lauf meldete L018 als „Abweichung" (Exit 1). Korrektur als Folgepaket:
  bekannter Fingerabdruck → Profil `l018` mit eigenen Referenzwerten (ARISC `d4b4a0b9…`, anderer Build derselben Version `00.00.00.09`;
  EDID/MSP/PQ identisch mit HY310; gleiches Referenzdesign `h713_tuna_p3`), Ausgabe je Gerät, Exit 0. „Abweichung" nur für unbekannte Images.
- **L018-Profil fertig (10.09. 01:10, S42 §8):** `h713-extract` 0.2 mit Geräteprofilen `hy310`/`l018` (je Referenz-Hashes und Stock-Sollwerte),
  Erkennung per sha256 oder inhaltlich (scp-/u-boot-/dtb-Hashes, U-Boot-/ARISC-Kennung, Vendor-Fingerprint), „Abweichung" nur für unbekannte
  Images, Ordnerschutz gegen Gerätemischung (Exit 2). Nachgeprüft: L018 Exit 0 (`d4b4a0b9…`), HY310 Exit 0 mit den drei Referenz-Hashes.
  Bewusst offen: der L018-`scp.bin` wurde nie am Gerät geladen.
- **Rootfs und Vendor-Daten als eigene Pläne (10.09. 01:40):** [`107`](107-plan-rootfs.md) Rootfs (schlankes Debian trixie/arm64 aus
  `mmdebstrap --variant=minbase`, 250–350 MiB erwartet, WLAN/BT draußen, kein `dev`-Profil, Autologin bleibt, Journal flüchtig + zram-Swap)
  und [`108`](108-plan-vendordaten.md) Vendor-Artefakte (p1–p4 werden **nicht** bewahrt, Marco: das vollständige Stock-Image ist der
  Rückweg; Layout v2 mit vier Partitionen, U-Boot `0023` bekommt `h713_mips_dev`/`h713_project` als Env, `h713-extract` 0.3 liest den
  FAT16 der Vendor-Partition). **§1.2 ist damit abgelöst.**
- **Zwei Todo aus der Bestandsaufnahme (Marco, 10.09.):** **HDCP** und **EDID 1.4/2.2** müssen noch gemacht werden — Einzelheiten in
  [`108`](108-plan-vendordaten.md) §6. `hy310-hdcp22.bin` bleibt draußen (der Treiber überspringt den Schritt mit einer Warnung).
- **FEL-Boot gelöst (10.09., zweite Session, [`S44`](nachtlog/S44-fel-boot.md)):** `sunxi-fel uboot` bringt ein H713 zum
  U-Boot-Prompt. Zwei Ursachen lagen dahinter: nach dem RMR-Wechsel des `boot0`-Stubs ist **EL3 AArch64**, die FEL-Schleife
  läuft per `eret` auf EL1 und erreicht das AArch32-RMR-Register nicht mehr (die CPSR-Modusbits sehen dabei unverändert aus —
  daher vier gescheiterte Vorgängerversuche); Lösung ist eine **EL3-Falltür per `smc`** mit Postfach bei `0x48000000`. Dazu
  fiel `env_get_location()` beim Bootgerät `BOOT_DEVICE_BOARD` nicht auf MMC zurück, `env_init()` blieb **still** stehen.
  Patches in `analyse/release/arbeit/r0-fel/patches/`. **Damit ist R0 fast fertig:** die ganze Sequenz ist ein Aufruf, es fehlt
  nur das Skript drumherum.
- **Nachgezogen (10.09.):** `CONFIG_ENV_MMC_DEVICE_INDEX=1` in `hy310_qz713_v3_1`, `hy310_netboot` und `hy310_host` — ohne den
  Wert laden diese Bauten im FEL-Boot die eingebaute statt der gespeicherten Umgebung. `hy310_felmmc` bleibt außen vor
  (Restore-SPL, eigener Zweck). [`20`](20-flashen-und-recovery.md) ist auf den funktionierenden Weg umgeschrieben.
- **Der Installationsweg ist neu zugeschnitten (Marco, 10.09.): [`110`](110-plan-installationsweg.md).** Der Installer läuft
  auf dem **PC**, nicht auf dem Gerät: FEL lädt U-Boot flüchtig, U-Boot gibt die eMMC als USB-Laufwerk frei, und alles Weitere
  passiert am PC. Damit entfällt die Auflage, dass der Nutzer sich ein Firmware-Image besorgt — **extrahiert wird aus einem
  Vollabzug seiner eigenen eMMC**, den das Skript als ersten Schritt zieht. Der Abzug ist **Pflicht und sein Failsafe**:
  vollständig, geprüft, beschrieben und mit getestetem Rückspielweg. `105` §1 („Nutzer besorgt sich das Firmware-Image selbst")
  und §2 R1 (Installer aus dem laufenden Linux) sind damit überholt.
