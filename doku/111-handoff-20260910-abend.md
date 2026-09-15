# Handoff 10.09.2026, Abend - Stand nach dem Umbau

Vorgänger: [`106`](106-handoff-20260910.md) (Vormittag desselben Tages). Einstieg immer über
[`00-STATUS.md`](00-STATUS.md), Offenes in [`60-offen.md`](60-offen.md).

**An diesem Tag haben zwei Sitzungen parallel gearbeitet.** Das erklärt, warum manche Dinge doppelt angefasst wurden;
die Ergebnisse sind zusammengeführt und geprüft. Wer hier weiterarbeitet, sollte vorher `git -C mainline/external/u-boot
log` und die Zeitstempel in `analyse/release/arbeit/` ansehen.

## 1. Das Gerät bootet vollständig von sich selbst

Kein Netzstart mehr, kein Host nötig. Die Kette: SPL (LBA 16) → U-Boot (LBA 2048) → Umgebung (Byte `0x700000`) →
Anzeige-Artefakte von `hy310-boot` → `ext4load` der Kernel-FIT → `root=PARTLABEL=hy310-rootfs` → Login.
**20 von 20 Kaltstarts sauber** (`analyse/boot/r5-20-kaltstarts-20260910.txt`, Prüfstand `analyse/boot/kaltstart-serie.sh`).

**Layout v3 am Gerät** ([`109`](109-plan-layout-v3.md) §2.2, Beleg `analyse/boot/gpt-layout-v3-final-20260910.txt`):

| # | PARTLABEL | Start-LBA | Größe | Inhalt |
|---|---|---|---|---|
| 1 | `hy310-spl` | 16 | 32 KiB | roh |
| 2 | `hy310-uboot` | 2048 | 5 MiB | roh, 890 KiB belegt |
| 3 | `hy310-keys` | 12288 | 1 MiB | **Secure Storage - nie beschreiben** |
| 4 | `hy310-env` | 14336 | 1 MiB | roh, Umgebung + SPL-Parkplatz |
| 5 | `hy310-boot` | 16384 | 128 MiB | ext4: `mips/` (19 Artefakte) + `h713-kernel.fit` |
| 6 | `hy310-rootfs` | 278528 | 7,15 GiB | ext4: Debian trixie, 237 MiB belegt |

**Zugang:** `ssh root@192.168.8.143` - **die Adresse hat sich geändert**, weil der Hostname jetzt `hy310` heißt (vorher
`.141`). Serielle Konsole mit Autologin. Der SSH-Schlüssel wurde von Hand eingetragen; das gebaute Rootfs bringt bewusst
keinen mit.

## 2. Was heute dazugekommen ist

| Bereich | Stand |
|---|---|
| **U-Boot** | **Stand 11.09.: alles committet, Arbeitsbaum sauber, Patches bis `0030`.** Vier Commits vom 10.09., exportiert als `uboot-h713/0022` - `0025`: Env-Offset ≥ 2 GiB (generischer Fix, PR-Kandidat), Artefakt-Ort per Env, **Boot-Kette an den Anfang der eMMC**, `net.ifnames=0`. Dazu am 11.09. fünf weitere als `0026` - `0030`: EL3-Falltür (`fel_utils.S`, [`S44`](nachtlog/S44-fel-boot.md)), ENVL_MMC-Rückfall (`board.c`), `ENV_MMC_DEVICE_INDEX=1`, das Installer-Defconfig, und `h713_mips_dev=1#hy310-boot`. |
| **Rootfs** | `analyse/release/arbeit/rootfs/`: **228 MiB**, 154 Pakete, 20 Abnahmeprüfungen grün. Journal flüchtig, zram-Swap (461,8 MiB, eigenes Kernel-Fragment `patches/kernel/board/zram.config`) - [`107`](107-plan-rootfs.md) §9, [`S43`](nachtlog/S43-rootfs-bau.md) |
| **Extraktor** | `hy310-extract` **0.4**: eigener ext4-Leser, **kein `debugfs` mehr** → läuft unter Windows. Profile für HY310 und L018, 19 MIPS-Artefakte, Projekt-ID dreifach im Manifest - [`S42`](nachtlog/S42-r2-extract.md), [`S45`](nachtlog/S45-ext4-leser.md) |
| **FEL** | `sunxi-fel uboot` bringt das Gerät zum U-Boot-Prompt, **drei Sekunden, kein Byte auf die eMMC**. Reset-Taste halten und Strom einstecken - kein Gehäuse, kein Pad (die alte Pad-Beschreibung war überholt) |
| **Laufwerksfreigabe** | `hy310_installer_defconfig`: FEL lädt es, die eMMC hängt als `/dev/sda` am PC. **Gemessen: 7,6 MB/s lesen, 7,7 MB/s schreiben**, blockgrößenunabhängig |
| **PC-Installer** | `analyse/release/arbeit/r0-fel/hy310-install.py`, plattformübergreifend, ~900 Zeilen. Abzug klein/voll, `--restore`, `--restore-stock` mit **byteidentisch nachgebauter Stock-GPT** |
| **Kritische Prüfung** | [`S46`](nachtlog/S46-kritische-pruefung.md): 5 kritische, 13 ernste Befunde. Sieben behoben (§5 dort), Rest bewusst offen |
| **Pläne** | [`107`](107-plan-rootfs.md) Rootfs, [`108`](108-plan-vendordaten.md) Vendor-Daten, [`109`](109-plan-layout-v3.md) Layout v3, [`110`](110-plan-installationsweg.md) **Installationsweg** - der letzte löst `105` R0/R1 ab |

## 3. Der Nutzerweg, wie er jetzt gedacht ist ([`110`](110-plan-installationsweg.md))

Marcos Vorgabe: **der Nutzer bekommt eine Abbild-Datei und spielt sie ein**, wie bei einem Einplatinenrechner. Kein
Firmware-Image aus dem Netz, kein USB-Stick, kein Netzstart, kein Linux auf dem Gerät.

1. Reset halten, Strom einstecken → FEL.
2. `hy310-install` lädt U-Boot flüchtig, die eMMC hängt als Laufwerk am PC.
3. **Abzug** - Pflicht. Wahl zwischen klein (49 MiB, 7 s: nur was nur auf diesem Gerät existiert) und voll (7,3 GB, 17 min).
4. Proprietäre Teile **aus dem Abzug** extrahieren (`hy310-extract` liest rohe eMMC-Abzüge).
5. Abbild schreiben. **Vorher** werden die Platzhalter in der lokalen Datei gefüllt - ein Schreibdurchlauf, nicht zwei.
6. Strom aus und an.

**Einspielen und Abziehen sind dasselbe**, nur mit vertauschten Seiten: `dd if=/dev/sda of=…` bzw. `dd if=… of=/dev/sda`.
Aus der Freigabe kommt man nur durch Stromabschalten heraus - das ist der natürliche Abschluss.

## 4. Was jetzt gerade läuft und was fehlt

- **Fertig geworden:** der **Abbild-Bauer** `analyse/release/arbeit/r0-fel/hy310-mkimage.py`
  ([`S47`](nachtlog/S47-abbild-bauer.md)). Das Abbild liegt in `r0-fel/out/`, 1,22 GB, mit 30 Platzhaltern und einer
  Offsettabelle. **Es sind drei Dateien, keine einzelne:** Teil A ab Sektor 0, Teil B ab Sektor 14336, Teil C ans
  Plattenende. Die Lücke dazwischen ist genau der Secure Storage - so kann ihn auch ein `dd` von Hand nicht nullen.
  Nachgeprüft: die Partitionstabelle in Teil A ist byteidentisch mit der auf dem Gerät, die Prüfsummen stimmen,
  `--pruefen` läuft grün, und der gesperrte Bereich wird von keinem Teil berührt.
- **Am selben Abend scharf gelaufen:** der Stock-Rückweg an Marcos Gerät. 1718 MiB in 4 Minuten, danach wieder die
  26 Android-Partitionen. Secure Storage vorher und nachher identisch (`cf2805fc…`), die ersten 56 KiB byteweise gleich
  mit der Sicherung vom Vormittag. Der Pflichtabzug liegt in `hy310-sicherung/` im Projektwurzelverzeichnis, root und
  Modus 600. **Dabei fielen drei Fehler auf, die kein Trockenlauf finden konnte** - siehe [`60-offen.md`](60-offen.md),
  Punkte 8 bis 10. Der schwerste: die getippte Bestätigung verglich gegen Großbuchstaben und bekam Kleinbuchstaben,
  lieferte also immer ein Nein. Jeder Schreibweg des Installers war damit unbenutzbar. Behoben.
- **Der Stock-Rückweg hat vier Anläufe gebraucht.** Die Fehler und ihre Belege stehen in
  [`60-offen.md`](60-offen.md). Der schwerste: **`super.fex` ist ein Android-Sparse-Abbild** (1538 MiB Datei,
  2048 MiB Inhalt, Kennung `0xed26ff3a`), das roh geschrieben wurde. Ohne gültiges `super` findet Android
  `system`, `vendor` und `product` nicht und startet stumm in den Bootloader zurück. Dazu: `metadata` braucht ein
  fertiges ext4 vom PC, weil die erste Stufe von `init` kein `mke2fs` hat; und alles ohne Quelldatei im Image muss
  genullt werden, weil das Werkzeug des Herstellers die eMMC vorher löscht.
- **Der komplette Nutzerweg ist am 11.09. um 00:23 einmal ganz durchgelaufen**, von stock Android aus:
  Vollabzug 7,3 GB in 17 min (Stichproben gegen das Gerät bestanden, sha256 `33e1ffc4…`, liegt in
  `re/device-dumps/stock-20260911/`), Extraktion der 30 gerätespezifischen Dateien **aus diesem Abzug**,
  Platzhalter am PC gefüllt und zurückgelesen, drei Teile in 3 min geschrieben, Rückvergleich bestanden,
  Secure Storage byteweise unverändert. **Das Gerät startet damit.**
- **Aber das Abbild taugt so noch nicht:** es trägt ein U-Boot von Patch 0023, es fehlen 0024 und 0025. Ohne
  `net.ifnames=0` heißt die Netzschnittstelle MAC-basiert, `allow-hotplug eth0` greift nie, das Gerät ist nicht
  im Netz. **Erste Aufgabe am nächsten Tag:** Abbild mit dem aktuellen U-Boot neu bauen. Ebenfalls offen und
  ungeklärt: die serielle Konsole meldet sich nicht, obwohl Autologin und `console=ttyS0,115200` eingerichtet sind.
- **Fehlt danach:** `sunxi-fel` als Windows-Programm (das Makefile kann es, gebaut ist es nicht); das Repo
  (`105` R3); README und Funktionsmatrix (`105` R4); der Scanner für geschützte Bereiche bei fremden Firmwares
  (`109` §9); die Geräteerkennung im Installer (`110` §8, braucht nur den fertigen ext4-Leser).
- **Nie ausgeführt:** der Windows-Pfad. Er steht als Entwurf im Code, `_get_osfhandle` liegt dort nicht in `kernel32`
  (Befund `S46`).

## 5. Teuer bezahltes Wissen (neu an diesem Tag)

1. **`env/mmc.c` verstümmelt jeden Env-Offset ≥ 2 GiB.** `ofnode_conf_read_int()` führt ihn durch ein `int`; der Wert
   wird negativ, „vom Ende" gerechnet und auf 32 Bit gekürzt. `0x93d80000` → `0x65d80000`. Nicht die Defconfig, der Code.
   Fix `0022`, generisch, PR-Kandidat.
2. **Eine gespeicherte Umgebung ersetzt die eingebaute Vorgabe vollständig.** U-Boot mischt nicht. Ist am Tag dreimal
   zugeschlagen: beim Installer, beim Layout-Wechsel, und beim Installer-U-Boot (dort gelöst mit `CONFIG_ENV_IS_NOWHERE=y`).
3. **`sys_partition.fex` hat CRLF.** Ein Ausdruck mit `[^"\n]+` zieht den Wagenrücklauf in jeden Wert - alle 26
   GPT-Namen trugen ein unsichtbares `U+000D`, Android hätte seine Partitionen nicht gefunden. Gefunden von der
   kritischen Prüfung, nicht vom Autor.
4. **Die Stock-GPT hat drei Eigenheiten**, die kein Standard vorschreibt: Attributbit 63 auf jeder Partition, zusätzlich
   Bit 47 auf `frp`, und das reservierte Feld bei Kopf-Offset 20 steht auf 1. Ohne sie weicht die nachgebaute Tabelle ab.
5. **Beim Schreiben auf ein Blockgerät: `O_EXCL` und Einhänge-Prüfung.** Ein eingehängtes Dateisystem schreibt seinen
   Zwischenspeicher über frisch geschriebene Daten zurück - und eine Rückleseprobe über denselben Zwischenspeicher meldet
   trotzdem „stimmt". Beim Prüflauf waren `sda5` und `sda6` tatsächlich eingehängt.
6. **`0x05000000` niemals lesen.** H616-UART-Adresse, auf dem H713 unbelegt; ein Lesezugriff hängt den Bus auf und kostet
   einen Stromzyklus.
7. **Nach `sunxi-fel spl` oder `uboot` ist der FEL-Zustand verbraucht.** Ein zweiter Aufruf ohne Stromzyklus endet in
   `usb_bulk_send ERROR -7` und hinterlässt das Gerät hängend. Immer Reset + Strom dazwischen.
8. **Der Secure Storage bei LBA 12288…14335 ist nicht nur HDCP.** Er enthält auch `wifiBleDatas` (WLAN-/BT-MACs) und
   `snum` (Seriennummer). Gerätespezifisch, in keinem Image, nicht wiederherstellbar. Kopie in
   `re/device-dumps/secure-storage-HY310-dev-20260910.bin`, Beschreibung daneben.
9. **`private` und `Reserve0_a/b` sind bei uns verloren.** Sie wurden beim Umbau überschrieben, keine Sicherung reichte
   so weit. `Reserve0.fex` im Firmware-Image ist leer - was dort auf einem Gerät steht, kommt durch kein Image zurück.
   **Todo:** Abzug dieser drei von einem unangetasteten Gerät (`109` §9.1).
10. **Der Vollabzug dieses Geräts liegt vor:** `re/device-dumps/emmc-voll-HY310-dev-20260910.img` (7.818.182.656 B,
    sha256 `3c159da13eb603aa…`). **Aber:** er ist **nach** dem Umbau gezogen, enthält also kein Android mehr.

## 6. Regeln, die weiter gelten

- **Bauen nur im Container `h713-build`**, nie auf dem Host (`doku/50` Abschnitt Bauen). Ein frischer Container braucht
  den LLVM-20-Schritt, `python3-setuptools` und `mmdebstrap`.
- **Dieser Rechner ist 192.168.8.123** (TFTP-Wurzel `tftp/`, NFS `/srv/h713-rootfs`). `.104` in älteren Notizen war der
  vorige Rechner.
- **UART gehört Marco.** `sudo python3 tools/uart-*.py` funktioniert, aber ein laufendes `tio` muss geschlossen sein -
  zwei Leser teilen sich sonst die Antworten.
- **Zwischen `tftpboot` und `mmc write` immer `crc32` gegen den Host-Wert vergleichen.** Ein fehlgeschlagenes `tftpboot`
  hinterlässt den alten Speicherinhalt.
- **Prüfungen ab jetzt vom eMMC**, nicht per Netzstart - nur das ist der Release-Zustand. TFTP und NFS laufen weiter,
  damit der Netz-Rückfall bei kaputtem Rootfs greift.
