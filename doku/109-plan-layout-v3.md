# Plan 109 — Layout v3: die Boot-Kette an den Anfang

**Status: Plan, 10.09.2026.** Löst [`108`](108-plan-vendordaten.md) §4.3 ab, das seinerseits `105` §1.2 abgelöst hat.
**Anlass (Marco, 10.09.):** „wieso haben wir 2 GB mitten in der Partitionstabelle" und „U-Boot an den Anfang".
Beides trifft zu, und beides ist ein Erbe des Stock-Layouts, das seit dem Wegfall der Vendor-Partitionen keinen Grund mehr hat.

## 1. Was an v2 stört

| Ort | heute | warum es so ist |
|---|---|---|
| U-Boot proper | LBA 4828160 (2,3 GiB weit hinten) | dort lag im Stock die Partition `empty`; wir haben die Nische benutzt, weil sie frei war |
| `hy310-data` | 2,14 GiB zwischen Boot- und U-Boot-Bereich | reine Verlegenheit: der U-Boot-Bereich zerschneidet den Platz, das vordere Stück musste irgendwie vergeben werden |
| LBA 256 | Vendor-boot0, Zweitkopie | Fallback des BootROM auf den Original-Bootloader — der einzige Weg, auf dem das Gerät noch Android starten könnte |
| LBA 24576 / 32800 | zwei `sunxi-package`-Kopien, je 4 MiB | Vendor-Bootpaket; `scp.bin` kommt für das Release aus dem Firmware-Image, nicht vom Gerät |
| LBA 34…73727 | 16 MiB unbenutzt | Rest zwischen den Vendor-Blöcken und der ersten Partition |

**Genau ein Ort ist vorgeschrieben:** die SPL bei LBA 16, weil der BootROM dort nach `eGON.BT0` sucht. Alles andere ist frei wählbar.

## 2. Das Schema

### 2.1 Rohbereich, LBA 0 … 16383 (8 MiB) — **als Partitionen sichtbar** (§2.4)

| LBA | Sektoren | Inhalt |
|---|---|---|
| 0 | 1 | Protective MBR |
| 1 | 1 | GPT-Kopf |
| 2 … 8 | 7 | Partitionstabelle, 26 Einträge à 128 B |
| **16** | 64 | **SPL** (32 KiB, endet bei 79) — BootROM-Vorgabe |
| 80 … 2047 | 1968 | frei (984 KiB) |
| **2048 … 12287** | 10240 | **U-Boot proper**, **5 MiB Fenster**; belegt sind 1739 Sektoren (890.233 B) |
| **12288 … 14335** | 2048 | ⚠ **Secure Storage, 1 MiB reserviert (56 KiB belegt) — nicht anfassen** (§2.3) |
| **14336** | 128 | **Umgebung**, 64 KiB → Byte-Offset `0x700000` |
| **14464** | 64 | SPL-Parkplatz (`splstash`, Fastboot-Ziel) |
| 14528 … 16383 | 1856 | frei (928 KiB) |

**Warum die Umgebung hinter die Schlüssel wandert (Marco, 10.09.):** U-Boot ist noch nicht fertig, und ein Bootloader, der an
seiner eigenen Umgebung anstößt, ist ein vermeidbares Ärgernis. Die Schlüssel bei LBA 12288 lassen sich nicht verschieben, also
bekommt U-Boot alles davor: **5 MiB am Stück**, das **5,9-fache** der heutigen 890 KiB. Umgebung und Parkplatz liegen dahinter
und stehen dem Wachstum nicht im Weg.

**Warum nicht die sunxi-Vorgabe LBA 64:** unsere SPL ist 32 KiB groß und reicht bis LBA 79. Der übliche sunxi-Wert `0x40`
läge mittendrin. LBA 2048 ist auf 1 MiB ausgerichtet und lässt der SPL Luft, falls sie wächst.

**Nebenwirkung, willkommen:** die Umgebung liegt bei 7 MiB und damit weit unter 2 GiB — der `int`-Fehler aus
[`30` §16](30-uboot-aenderungen.md) kann dort gar nicht mehr auftreten. Der Fix `0022` bleibt trotzdem richtig und bleibt drin.

### 2.3 ⚠ Das Secure Storage liegt im Bootbereich (Fund 10.09.)

Beim Vermessen des Zielbereichs am Gerät zeigte sich, dass **LBA 12288 … 12399 belegt sind**: 112 Sektoren = 56 KiB in
**14 Blöcken à 4 KiB**, mit den Kennungen `hdcpkey`, `hdcpkeyV14_hash`, `hdcpkeyV22`, `hdcpkeyV22_hash` und einer Seriennummer.
Am 10.09. dekodiert: es ist das **sunxi Secure Storage** (Magic `0x17253948`, Struktur nach [`68`](68-stock-extraktion-arisc-hdcp.md)),
7 Items à 4 KiB, jedes doppelt abgelegt:

| Item | Länge | was es ist |
|---|---|---|
| Map | — | Verzeichnis |
| `hdcpkey`, `hdcpkeyV14_hash` | 396, 6 | HDCP 1.4 |
| `hdcpkeyV22`, `hdcpkeyV22_hash` | 988, 6 | HDCP 2.2 |
| **`wifiBleDatas`** | 240 | **WLAN- und Bluetooth-Daten, u. a. MAC-Adressen** |
| **`snum`** | 15 | **Seriennummer des Geräts** |

**Es geht also um mehr als HDCP.** Auch die Netzwerk-Identität und die Seriennummer stehen hier und in keinem Firmware-Image.
Die Stock-Partition `private` trägt den Namen, aber nicht die Daten (Korrektur zu [`S42`](nachtlog/S42-r2-extract.md) §2.5).

Ein Scan über die **ganze eMMC** (10.09.) nach `hdcpkey|HDCP|hdcp_|widevine|attestation|keybox` bestätigt: **dieser Block ist das
einzige Schlüsselmaterial**. Die übrigen Treffer sind Zeichenketten in Code und Konfiguration — OP-TEE im Vendor-Bootpaket
(LBA 25484 ff.: `core/crypto/sm4-ctr.c`, `tee_shm_phys_to_virt`), die alte Vendor-Umgebung (LBA 204800: `BOOTMODE=standby`),
sowie `display.bin` und Android-Reste.

**Regel:** dieser Bereich wird **nicht beschrieben und nicht ausgelesen**. Der Grund ist nicht Vorsicht vor dem Stock — den gibt es
nicht mehr — sondern dass die Schlüssel **gerätespezifisch und nicht wiederherstellbar** sind. Wer sie überschreibt, macht HDCP auf
genau diesem Gerät für immer unmöglich, auch mit Vendor-Firmware. Das Projekt fasst HDCP-Material grundsätzlich nicht an
([`105`](105-plan-release.md) §1.1), und hier kommt hinzu, dass ein Fehlgriff nicht rückgängig zu machen ist.

**Die Partition ist größer als der Inhalt, mit Absicht (Marco, 10.09.).** Belegt sind 56 KiB, reserviert ist **1 MiB**. Die Map
ist eine offene Namensliste ohne feste Obergrenze, und ein fremdes Gerät kann mehr Items führen — Widevine, Attestation, was auch
immer der Hersteller dort ablegt. 1 MiB fasst **128 Item-Paare** statt der heutigen sieben, also die 18-fache Menge, und reicht
genau bis zur Umgebung bei LBA 14336; der Bereich dazwischen war ohnehin leer (nachgemessen).

**Bewahrt wird auf zwei Wegen (Marco, 10.09.):** auf dem Gerät bleibt der Block unangetastet, und es liegt eine Kopie unter
`re/device-dumps/hdcp-keys-HY310-dev-20260910.bin` (56 KiB, sha256 `b83ce75d68ca59dd…`, Modus 600), dazu die ersten 8 MiB roh als
`bootbereich-8mib-HY310-dev-20260910.bin`. Beides nie ins Repo und nie ins Release — Regeln in
[`re/device-dumps/HDCP-SCHLUESSEL.md`](../re/device-dumps/HDCP-SCHLUESSEL.md).

Praktisch kostet das nichts: U-Boots Fenster endet bei LBA 12287, die Umgebung beginnt bei 14336, dazwischen liegt die
reservierte Partition. **Der Installer muss den Bereich trotzdem ausdrücklich sperren**, damit ihn
niemand später als „freie Reserve" benutzt.

### 2.2 Die Partitionstabelle

`FirstUsableLBA` wird auf **16** gesetzt, damit auch die Rohbereiche Einträge bekommen können (§2.4). Die Tabelle behält
**26 Einträge** (LBA 2 … 8); mehr würde in die SPL bei LBA 16 hineinreichen.

| # | PARTLABEL | Start-LBA | Sektoren | Größe | Inhalt |
|---|---|---|---|---|---|
| 1 | `hy310-spl` | 16 | 64 | 32 KiB | **roh**: SPL. Kein Dateisystem, nie `mkfs` |
| 2 | `hy310-uboot` | 2048 | 10240 | 5 MiB | **roh**: U-Boot proper. Kein Dateisystem, nie `mkfs` |
| 3 | `hy310-keys` | 12288 | 2048 | 1 MiB | ⚠ **Secure Storage: HDCP, WLAN/BT-MAC, Seriennummer — nie beschreiben** (§2.3) |
| 4 | `hy310-env` | 14336 | 2048 | 1 MiB | **roh**: Umgebung (14336) und SPL-Parkplatz (14464) |
| 5 | `hy310-boot` | 16384 | 262144 | 128 MiB | ext4: `mips/` (Vendor-Artefakte), `h713-kernel.fit` |
| 6 | `hy310-rootfs` | 278528 | 14991327 | **7,15 GiB** | ext4: Debian ([`107`](107-plan-rootfs.md)), einschließlich `/data`-Verzeichnis |

Frei bleiben zwei Lücken im Bootbereich: LBA 80 … 2047 (984 KiB) und 14528 … 16383 (928 KiB).

### 2.4 Warum die Rohbereiche Partitionen bekommen

Ein Bereich, den nur unsere Doku schützt, ist nicht geschützt. Ein fremdes Partitionierungswerkzeug, ein `dd` von Hand oder ein
Installer einer anderen Distribution sieht dort freien Platz — und der Schlüsselblock ist **das einzige auf diesem Gerät, das
niemand zurückholen kann** (§2.3).

Deshalb bekommt jeder belegte Rohbereich einen Eintrag in der Tabelle. Das kostet nichts: der BootROM liest die SPL roh und
kennt keine GPT, U-Boots SPL liest sein Abbild ebenso roh über `CONFIG_SYS_MMCSD_RAW_MODE_U_BOOT_SECTOR`. Der Gewinn ist, dass
`lsblk`, `fdisk`, `gparted` und jedes andere Werkzeug ab sofort **sehen**, dass die Bereiche belegt sind.

**`hy310-spl` und `hy310-uboot` tragen bewusst kein Dateisystem.** Der Installer legt dort keines an und weist das im Bericht aus.

**Für `hy310-keys` gilt zusätzlich eine harte Sperre im Installer**, unabhängig davon, was in der Tabelle steht: die Sektoren
12288 … 12399 werden nie beschrieben, auch nicht auf `--force`.

Ende = `LastUsableLBA` 15269854. **Kein Loch, keine dritte Partition, kein unbenutzter Bereich** außer den 3 MiB Reserve im
Bootbereich. `hy310-data` entfällt ersatzlos; wachsende Daten liegen als Verzeichnis im Rootfs, das dafür 7 GiB hat.

Was verschwindet: Vendor-boot0-Kopie (LBA 256), beide `sunxi-package`-Kopien, jede Spur der Stock-Partitionierung.

## 3. Was zu ändern ist

### 3.1 U-Boot (`0024`)

| Wert | heute | neu |
|---|---|---|
| `CONFIG_SYS_MMCSD_RAW_MODE_U_BOOT_SECTOR` | `0x49ac00` (4828160) | `0x800` (2048) |
| `CONFIG_ENV_OFFSET` | `0x93d80000` | `0x700000` (LBA 14336) |
| `fastboot_raw_partition_ubootp` | `0x49ac00 0x2000` | `0x800 0x2800` (5 MiB Fenster) |
| `fastboot_raw_partition_splstash` | `0x49cc00 0x40` | `0x3880 0x40` (LBA 14464, in `hy310-env`) |
| `fastboot_raw_partition_vboot0` | `0x100 0x40` | **entfällt** — es gibt keinen Vendor-boot0 mehr |

Der SPL-Parkplatz (`splstash`, 32 KiB) ist ein Fastboot-Ziel, um eine SPL abzulegen, ohne LBA 16 zu überschreiben. Er liegt in
`hy310-env`: **LBA 14464** (`0x3880`). Die Werte stehen in `include/configs/sunxi-common.h` (`H713_FASTBOOT_ENV_SETTINGS`)
und werden in `board/sunxi/board.c` gegen veraltete Vorgaben abgeglichen — beide Stellen ziehen mit.

`board/sunxi/hy310.env`: `boot_emmc` liest weiter über `mmc 1#hy310-boot`, `h713_mips_dev=1#hy310-boot` bleibt.
Neu ist nur, dass es keine dritte Partition mehr gibt.

### 3.2 Installer (0.4)

- `LAYOUT_JSON` nach §2.2, **sechs** Einträge, davon vier ohne Dateisystem (`hy310-spl`, `hy310-uboot`, `hy310-keys`, `hy310-env`).
- `LBA_GUARD` entfällt in der bisherigen Form: geschützt wird nicht mehr „alles unter X", sondern die benannten Bereiche.
  **Harte Sperre auf LBA 12288 … 12399**, die auch `--force` nicht aufhebt.
- Der GPT-Schreiber muss **`FirstUsableLBA` setzen können** — heute übernimmt er den Wert aus dem gelesenen Kopf. Neuer Parameter,
  Vorgabe „unverändert", für v3 auf **16**. Die Zahl der Einträge bleibt bei 26, damit die Tabelle nicht in die SPL reicht.
- Die Schritte `mkfs`, `rootfs`, `kernel`, `mips`, `config` auf zwei Partitionen umstellen; `/data` wird ein Verzeichnis im Rootfs,
  die `fstab` verliert die dritte Zeile.
- Neuer Schritt **`uboot`**: schreibt U-Boot proper an LBA 2048 und die SPL an LBA 16, jeweils mit Rücklesung und Prüfsummenvergleich.
  Damit kann der Installer eine Kette vollständig aufbauen, statt sie am Prompt zusammenzusetzen.

## 4. Netboot muss dazu passen

Der Netboot-Weg bleibt der Entwicklungsweg und darf durch v3 nicht schlechter werden. Drei Dinge gehören zusammengehalten:

1. **Die Anzeige-Artefakte liegen immer auf `hy310-boot`** — U-Boot lädt sie vor dem Kernel, unabhängig davon, ob danach per Netz
   oder von der eMMC gebootet wird. Ein Gerät ohne bespielte `hy310-boot` bootet also per Netz durch, zeigt aber kein Bild.
   Das ist der heutige Zustand und bleibt so. **Konsequenz:** `hy310-boot` wird auch dann bespielt, wenn nur Netboot geplant ist.
2. **Ein Rootfs-Bau, zwei Ziele.** Das schlanke Rootfs aus [`107`](107-plan-rootfs.md) wird sowohl nach `hy310-rootfs` geschrieben
   als auch als NFS-Wurzel auf dem Host ausgelegt. Damit finden Kernel und Dienste in beiden Fällen dieselben Pfade:
   `/lib/modules/<version>`, `/lib/firmware/h713-arisc.bin`, `/lib/firmware/hy310-edid.bin`, `/lib/firmware/h713/msp-patch.bin`,
   `/etc/hy310/tvconfig/` (PQ-Daten), `/usr/local/sbin/h713-tv`. Das heutige NFS-Root (2,9 GiB, Entwicklungswerkzeug) bleibt als
   getrennter Baum bestehen, solange es gebraucht wird.
3. **Die Umgebung kennt beide Wege.** `h713_boot=emmc|net` schaltet um, `boot_net` bleibt der Rückfall, wenn `boot_emmc` scheitert.
   Die Vorgabe im Abbild führt noch `serverip=192.168.8.104` — das ist der **vorige** Rechner; richtig ist **192.168.8.123**.
   Das gehört mit `0024` korrigiert, sonst muss es jedes Gerät per `saveenv` nachziehen.

**Option für später, nicht Teil dieses Plans:** die Artefakte per TFTP laden statt von der Partition. Das wäre für die Entwicklung
bequem (Tauschen ohne Flashen), verlangt aber einen zweiten Ladeweg in `h713_disp_read()`, der nicht über `fs_read` geht.

## 5. Ablauf am Gerät — **am 10.09. vollständig durchgeführt**

| # | Schritt | Ergebnis |
|---|---|---|
| 1 | U-Boot mit neuen Offsets bauen | ✓ Commit `0024`, im Disassemblat geprüft (`mov w4, #0x800`) |
| 2 | Umgebung nach `0x700000` kopieren, proper an LBA 2048 | ✓ zurückgelesen, byteidentisch |
| 3 | **SPL bei LBA 16 tauschen** | ✓ bestanden — der Neustart fand U-Boot am neuen Ort |
| 4 | GPT nach §2.2, sechs Einträge, `FirstUsableLBA=16` | ✓ `lsblk` zeigt alle sechs, Schlüsselblock als eigene Partition |
| 5 | `mkfs` auf p5/p6, Rootfs aus dem tar, Artefakte, Kernel-FIT | ✓ 229 MiB entpackt, 19 Artefakte, FIT auf `hy310-boot` |
| 6 | Firmware und PQ-Daten ins Rootfs | ✓ drei Firmware-Dateien, acht PQ-Dateien |
| 7 | **Kaltstart ohne Host** (TFTP und NFS abgeschaltet) | ✓ SPL → U-Boot → `ext4load` → `root=PARTLABEL=hy310-rootfs` → Login |
| 8 | Betrieb | ✓ ARISC, `cpu_comm`, HDMI-Init (22 Aufrufe), EDID, MSP-Patch, `h713-tv@video1` aktiv |

Belege: `analyse/boot/v3-spl-tausch-20260910.txt`, `analyse/boot/layout-v3-emmc-kaltstart-20260910.txt`,
`analyse/boot/gpt-layout-v3-20260910.txt`.

### 5.1 Der geplante Ablauf (Vorlage für ein fremdes Gerät)

Die Reihenfolge ist so gewählt, dass der einzige riskante Schritt so spät wie möglich kommt und alles davor überprüfbar ist.

| # | Schritt | Prüfung |
|---|---|---|
| 1 | U-Boot mit den neuen Offsets bauen (Container) | `strings` zeigt die neue Env-Vorgabe; Größe wie erwartet |
| 2 | proper an **LBA 2048** schreiben, alten bei 4828160 stehen lassen | `mmc read` + `crc32` gegen den Host-Wert, `cmp.b` |
| 3 | SPL bei **LBA 16** tauschen | **das Risiko** — danach entscheidet sich, ob das Gerät noch selbst bootet |
| 4 | Reset, Prompt fangen | Banner der neuen Version, `Loading Environment from MMC` |
| 5 | Umgebung neu setzen (`h713_gate=0`, `serverip=192.168.8.123`, `h713_project`, `h713_mips_dev`) | `printenv`, dann `saveenv` und Byte-Scan bei `0x700000` |
| 6 | GPT nach §2.2 schreiben, `FirstUsableLBA=16384` | `lsblk`, Rücklesung des Schreibers |
| 7 | `mkfs` auf beide, Artefakte nach `hy310-boot/mips` | byteweiser Vergleich |
| 8 | Rootfs nach `hy310-rootfs`, FIT nach `hy310-boot` | Kaltstart ohne Host |

**Zu Schritt 3:** die SPL ist 32 KiB und wird an einem Stück geschrieben. Schlägt der Start danach fehl, ist das Gerät nicht
selbst startfähig und braucht FEL — das ist nachgewiesen (Marco, 10.09.). Der alte U-Boot bei 4828160 nützt dann nichts mehr,
weil die neue SPL ihn nicht sucht; er bleibt trotzdem liegen, bis v3 steht, und wird erst mit der GPT in Schritt 6 überschrieben.

**Vor Schritt 3 sichern:** LBA 0…16383 als Rohdatei (8 MiB) auf den Host, dazu die aktuelle GPT. Das ist keine Rückkehr zum Stock,
sondern die Möglichkeit, den heutigen Zustand über FEL wiederherzustellen.

## 6. Was danach anders ist

- Zwei Partitionen statt vier, 7,15 GiB Rootfs statt 4,96 GiB plus einer leeren Datenpartition.
- Die gesamte Boot-Kette liegt in den ersten 8 MiB und ist am Stück sicherbar.
- `doku/20` bekommt eine neue Tabelle; die Flash-Rezepte nennen LBA 2048 statt `0x49ac00`.
- Der Installer kann eine Kette von Grund auf aufbauen, was Paket R0 (`h713-fel-install`) vereinfacht: FEL schiebt die SPL,
  die lädt U-Boot, das startet den Installer.

## 7. Entschieden (10.09., damit nichts offen bleibt)

**Die 3 MiB Reserve bleiben, ohne festgelegten Zweck.** Sie sind der Rest bis zur runden 8-MiB-Grenze, nicht eine Fläche, für die
erst eine Aufgabe gesucht wird. Der Bootbereich ließe sich auf 6 MiB kürzen, das brächte 1 MiB mehr Rootfs — 0,014 % der eMMC.
Eine merkbare Grenze und Platz für spätere Fälle (eine SPL, die wächst; ein zweiter U-Boot; eine Rettungs-Umgebung) sind mehr
wert. Belegt wird davon nur der SPL-Parkplatz bei LBA 10368.

**Die Reserve wird nicht angetastet, auch nicht später.** Der Fund aus §2.3 macht aus der Geschmacksfrage eine Regel: in der
Reserve liegt Material, dessen Verlust nicht heilbar ist. Wer dort etwas ablegen will, muss zuerst §2.3 lesen.

**Eine zweite U-Boot-Kopie kommt nicht.** Sie würde nichts retten: die SPL sucht an genau einer Stelle, ein automatischer Rückfall
entstünde erst mit eigenem SPL-Code. Und wer am U-Boot-Prompt steht, um von Hand eine Kopie zurückzuschreiben, hat ein laufendes
U-Boot und braucht sie nicht. Gegen die Fehler, die wirklich vorkommen — kaputte SPL, kaputte GPT — hilft FEL.

**`h713-rescue.fit` kommt nicht in v0.1.** Der Netboot-Rückfall ist der Rettungsweg und ist erprobt; ein zweiter Kernel auf
derselben Partition hilft gegen keinen der realen Fehlerfälle. Die 128 MiB von `hy310-boot` reichen für Kernel plus Rettungsabbild,
also lässt sich das jederzeit nachrüsten, ohne das Layout anzufassen.

**Die Fastboot-Ziele werden mitgezogen, obwohl Fastboot nicht Teil des Release ist.** Nicht aus Vollständigkeit, sondern weil ein
`fastboot flash ubootp` mit dem alten Wert `0x49ac00` mitten in das neue Rootfs schreiben würde. Ein Ziel, das auf eine falsche
Stelle zeigt, ist schlimmer als eines, das niemand benutzt.

## 9. Todo: geschützte Bereiche bei fremden Firmwares finden (Marco, 10.09.)

Unsere Zahlen stammen von **einem** Gerät mit **einer** Firmware. Eine andere Firmware kann die gerätespezifischen Blöcke
woanders ablegen — und wer sie überschreibt, macht sie unwiederbringlich kaputt. Deshalb bekommt der Installer ein eigenes
Programm, das **vor** dem ersten Schreibzugriff sucht statt anzunehmen.

**`hy310-scan-protected`** (Name vorläufig), Teil des Installers, läuft als erster Schritt:

0. **Erst sichern, dann suchen.** Bevor irgendein Schreibzugriff erfolgt, werden die Partitionen `private`, `Reserve0_a` und
   `Reserve0_b` roh gesichert, sofern die Stock-Tabelle sie noch nennt (§9.1). Sie sind ab Werk beschrieben und stehen in keinem
   Firmware-Image.
1. **Suchen statt annehmen.** Sequenzieller Scan über die eMMC (ein Leser, 16-MiB-Stücke — die eMMC verträgt keine parallelen
   Zugriffe, `105` Verlauf 10.09.) nach den bekannten Marken: `hdcpkey`, `hdcpkeyV14_hash`, `hdcpkeyV22`, `hdcpkeyV22_hash`,
   dazu `widevine`, `keybox`, `attestation`. Treffer in Code und Konfiguration sind auszusortieren — das Muster des echten
   Blocks ist bekannt: 14 Blöcke à 4 KiB, jeder Block beginnt mit einer der Marken, dazwischen Nullen (§2.3).
2. **Sichern.** Jeder gefundene Block wird roh nach `/data/hy310-geschuetzt/<lba>-<groesse>.bin` geschrieben, mit Manifest
   (LBA, Größe, sha256, gefundene Marken) und Rechten 600. **Auf dem Gerät**, nicht ins Netz und nicht ins Repo.
3. **Vergleichen.** Stimmen Ort und Größe mit dem bekannten Fall (LBA 12288, 112 Sektoren), läuft der Installer normal weiter.
4. **Abweichung ⇒ `NICHT UNTERSTÜTZT`.** Liegt der Block woanders, ist er größer, gibt es mehrere oder gar keinen, **bricht der
   Installer ab** und fordert den Nutzer auf, ein Issue zu eröffnen — mit dem Manifest, dem Firmware-Fingerabdruck und der
   Gerätebezeichnung, aber **ohne den Blockinhalt**. Erst wenn das Layout für diese Firmware nachgetragen ist, läuft es weiter.
   Ein `--ich-weiss-was-ich-tue` gibt es nicht: der Schaden ist nicht heilbar.

**Warum das nicht Beiwerk ist:** ein Firmware-Image bringt Bootloader und Partitionen zurück, aber **nicht** die
gerätespezifischen Schlüssel. Sie sind das Einzige auf dem Gerät, dessen Verlust auch ein vollständiger Stock-Restore nicht
heilt. Ein Nutzer, der später zurück zu Stock will, muss sie noch haben.

### 9.1 Was gerätespezifisch ist — und was davon gesichert ist (10.09., korrigiert)

**Die Netzwerk-Identität des Geräts ist nicht verloren.** Der geschützte Block bei LBA 12288 ist kein reiner HDCP-Block, sondern
der sunxi Secure Storage — neben den HDCP-Schlüsseln stehen dort **`wifiBleDatas`** (WLAN- und Bluetooth-MACs) und **`snum`**
(Seriennummer). Aufbau und Items: §2.3. Er liegt unverändert in `p3 hy310-keys`, ist vom Installer gesperrt und kopiert nach
`re/device-dumps/secure-storage-HY310-dev-20260910.bin`.

**Was tatsächlich ohne Sicherung überschrieben wurde:** die Partitionen `private` (LBA 4891648) und `Reserve0_a/b` (5489664 /
5522432). Keine unserer Roh-Sicherungen reicht so weit — der 300-MB-Dump endet bei LBA 614400. Wie schwer das wiegt, ist offen:
`Reserve0.fex` im Firmware-Image ist **leer** (16 MiB, 10 belegte Sektoren, nur ein FAT16-Kopf), und `private` ist bei Android
der Zugriffspfad auf den Secure Storage, dessen Inhalt roh bei LBA 12288 liegt und den wir haben. **Vermutlich** ging nichts
Einmaliges verloren — bewiesen ist es nicht.

**Todo (Marco, 10.09.):** von jemandem mit unangetastetem Gerät einen **Dump von `Reserve0_a`, `Reserve0_b` und `private`**
besorgen, um die Frage zu schließen. Bis dahin gilt: **der Scanner aus §9 sichert diese drei Partitionen mit**, nicht nur den
Secure-Storage-Block — es kostet 48 MiB und beantwortet die Frage für jedes fremde Gerät von selbst.


**Offen für die Umsetzung:** ob es außer HDCP und diesen drei Partitionen weitere gerätespezifische Blöcke gibt. Der Scan sucht
breit und meldet alles Verdächtige; die Bewertung kommt mit dem ersten fremden Gerät.

## 10. Zwei Stolpersteine aus dem Lauf vom 10.09.

- **Die Netzschnittstelle heißt im neuen Rootfs anders.** Im Netboot vergibt der Kernel die Adresse selbst (`ip=dhcp`); vom eMMC
  muss `ifupdown` ran, und dort hieß die USB-Schnittstelle `enx00e0fc6824cb` statt `eth0` — die Konfiguration griff nicht, das
  Gerät war ohne Netz. **Behoben mit `net.ifnames=0` in `bootargs_base`**, U-Boot-Commit `0025`. Ein MAC-abhängiger Name taugt
  nicht für ein Release; das Gerät hat genau einen Adapter, also sind die klassischen Namen richtig.
- **Das Gerät hat eine neue Adresse.** Mit dem Hostnamen `hy310` statt `h713-arm64` vergibt der DHCP-Server
  **192.168.8.143** statt `.141`. Wer nach dem Umbau `.141` anspricht, findet nichts.
- **Das Release-Abbild hat bewusst keinen SSH-Schlüssel** (`107` §3). Nach dem Umzug vom Netboot war das Gerät deshalb nur über
  die serielle Konsole erreichbar. Der Installer hat dafür bereits `--authorized-key` — die Option war beim Umbau nur nicht
  benutzt worden. **Beim scharfen Lauf mitgeben.**
- **zram brauchte einen Kernel-Neubau.** `CONFIG_ZRAM`, `CONFIG_ZSMALLOC` und die zstd-Rückseite fehlten im Defconfig; neues
  Fragment `patches/kernel/board/zram.config`, Bau mit `KERNEL_CONFIG=netboot,zram`. Danach am Gerät gemessen: **461,8 MiB
  zram-Swap mit zstd**, `vm.swappiness=180`, `vm.page-cluster=0`, Dienst aktiv.

## 11. Gegenprobe: bringt das Firmware-Image alles zurück? (10.09.)

Marcos Frage: wir lassen nur den Secure-Storage-Block stehen — ist alles andere, was wir überschreiben, wirklich im Image?
Geprüft gegen `sys_partition.fex` und die Dateitabelle von `re/vendor/HY310/update.img`, abgeglichen mit dem Stock-Layout
aus `analyse/boot/gpt-stock-20260910.txt`.

**Ja, mit einer klaren Ausnahmeliste.**

| überschriebener Bereich | Quelle im Image |
|---|---|
| boot0 (LBA 16) und die Kopie (LBA 256) | `boot0_sdcard.fex` |
| sunxi-package A/B (LBA 24576, 32800) | `boot_package.fex` |
| `bootloader_a`/`_b` — **die MIPS-Artefakte** | `boot-resource.fex` (21,7 MB) |
| `env_a` | `env.fex` |
| `boot_a`, `vendor_boot_a`, `super`, `misc`, `dtbo_a`, `media_data`, `Reserve0_a` | je eigene `.fex` |
| `vbmeta_a`, `vbmeta_system_a`, `vbmeta_vendor_a` | je eigene `.fex` |

**Nicht im Image, aber unkritisch:** die acht B-Slots des A/B-Update-Schemas (`env_b`, `boot_b`, `vendor_boot_b`, `vbmeta_*_b`,
`dtbo_b`, `Reserve0_b`) werden vom Flashtool angelegt und beim ersten Systemupdate gefüllt; `frp`, `metadata` und `UDISK` sind
Laufzeitdaten, die Android selbst erzeugt; `empty` war im Stock leer.

**`private` ist überschrieben und nicht im Image** — aber es ist auch nicht das Schutzgut. Der Name führt in die Irre: das echte
Secure Storage liegt bei LBA 12288 im Bootbereich (§2.3) und ist als `hy310-keys` geschützt. Was in `private` stand, ist
unbekannt; der Scan über die ganze eMMC vor dem Umbau fand dort keine Schlüsselmarken.

**Konsequenz für den Installer** (zusätzlich zu §9): vor dem Überschreiben werden **alle Partitionen ohne Image-Quelle** roh
gesichert, nicht nur der Secure-Storage-Block. Das kostet wenig (`frp` 512 KiB, `metadata` und `private` je 16 MiB) und schließt
die Lücke für Firmwares, die dort doch etwas ablegen.

## 12. Kompletter Lauf am 10.09. — und was er aufgedeckt hat

Marco: „den ganzen kompletten Lauf nochmal, erzeugen, flashen etc." Durchgeführt wie ein Nutzer es täte: Gerät per **Netboot**
gestartet (der Installer verweigert den Dienst auf dem laufenden Zielsystem), dann alle elf Schritte in einem Zug —
`precheck, gpt, uboot, mkfs, rootfs, mips, firmware, kernel, config, env, report` mit `--force-mkfs`.

**Alles grün**, einschließlich der beiden neuen Schritte:

| Schritt | Ergebnis |
|---|---|
| `uboot` (neu) | U-Boot proper an LBA 2048 und SPL an LBA 16 geschrieben, **beide zurückgelesen und byteidentisch** |
| `gpt` | `hy310-keys` von 112 auf **2048 Sektoren** vergrößert, alle anderen GUIDs unverändert |
| `rootfs` | 229 MiB aus `hy310-rootfs.tar` entpackt |
| `mips` / `firmware` | 19 Artefakte, 3 Firmware-Dateien, 8 PQ-Dateien, je byteweise verglichen |
| Kaltstart ohne Host | SPL → U-Boot → `ext4load` → `root=PARTLABEL=hy310-rootfs` → Login, ARISC und HDMI-Init vollständig |
| Secure Storage | sha256 **unverändert** (`b83ce75d68ca59dd…`) — die Sperre hält |

**Drei echte Fehler, die nur dieser Lauf gezeigt hat:**

1. **Der Installer überschrieb `bootargs_base` ohne `net.ifnames=0`.** Der Wert steht in `ENV_SET` und wird immer gesetzt — die
   am Gerät gepflegte Fassung war damit weg, die Schnittstelle hieß wieder `enx…`, das Gerät hatte kein Netz. **Behoben** in
   `ENV_SET` **und** in `board/sunxi/hy310.env`, damit beide Quellen dasselbe sagen.
2. **`do_config` synchronisierte nicht.** Bei einem Teillauf (`--steps config` ohne `report`, das aushängt) blieb alles im
   Puffer; ein harter Neustart über die Steckdose verwarf ihn, und `authorized_keys` lag mit **0 Byte** auf der Platte, obwohl
   das Protokoll den `cp` zeigte. **Behoben** mit `sync` am Ende des Schritts.
3. **Der SSH-Schlüssel fehlte im Ablauf.** Jetzt gibt es `--authorized-key` (Restpunkt aus §10 erledigt); ohne die Option sagt
   der Installer ausdrücklich, dass das Gerät nur über die serielle Konsole erreichbar sein wird.

**Nebenbefund:** das Gerät bekommt eine **andere DHCP-Adresse**, weil der Hostname jetzt `hy310` statt `h713-arm64` ist
(zuletzt `192.168.8.143`). Für Skripte, die die alte Adresse fest verdrahten, ist das eine Stolperstelle.
