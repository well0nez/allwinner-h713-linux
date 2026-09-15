# Plan 108 - die Vendor-Artefakte vom Stock-Layout lösen

> **Das Layout aus §4.3 ist am 10.09. umgesetzt und bereits wieder abgelöst:** es gilt [`109`](109-plan-layout-v3.md)
> (U-Boot an den Anfang, zwei Partitionen, kein Loch). Alles andere in diesem Plan - Artefakte, Env-Umschalter, Projekt-ID -
> bleibt gültig und ist am Gerät bewiesen (§7).

**Status: Plan, 10.09.2026.** Gehört zu [`105`](105-plan-release.md) R1/R2. **Entscheidung Marco, 10.09.:** die Vendor-Partitionen
werden **nicht** bewahrt. Das vollständige Stock-Image ist der Rückweg, nicht eine Partition auf dem Gerät. Damit fällt die Auflage
aus `105` §1.2 („p1-p4 bleiben byteidentisch") und das Layout wird unseres.

## 1. Was heute wo liegt (gemessen, nicht angenommen)

Aus `re/device-dumps/emmc-first-300mb.bin` (Dev-Gerät) gelesen:

| Ort | Inhalt | Status |
|---|---|---|
| LBA 16 | **unsere SPL** (`eGON.BT0`) | bleibt |
| LBA 256 | Vendor-boot0, Zweitkopie | bleibt (harmlos, außerhalb jeder Partition) |
| LBA 24576 / 32800 | `sunxi-package` A/B = TOC1, enthält `scp.bin` | **bleibt** - Rückweg und Quelle für `h713-extract` |
| p1 `bootloader_a`, LBA 73728, 32 MiB | FAT16 | Kopie von p2 |
| p2 `bootloader_b`, LBA 139264, 32 MiB | FAT16 | **die Dateien, die U-Boot liest** |
| p3/p4 `env_a`/`env_b`, je 256 KiB | Vendor-Env | nur für das Freimachen eines **Stock**-Geräts nötig (v0.2), danach tot |

Inhalt von p1/p2 (identisch), Langnamen gelesen:

| Datei | Größe | nutzt unsere Kette? |
|---|---|---|
| `MIPS/display.bin` | 1.256.216 B | **ja** |
| `MIPS/database.TSE` | 282.464 B | **ja** |
| `MIPS/pq_custom.TSE`, `projecttable.TSE`, `display_cfg.xml`, `LogoRegData.bin` | 36.818 B | **ja** |
| `MIPS/ProjectID_0x0001…0x0035.TSE`, 13 Stück | 19-48 kB je | **ja, genau eine davon** |
| `BOOTLOGO.BMP`, `FONT24/32.SFT`, `FASTBOOT.BMP`, `MAGIC.BIN`, `BAT/*.BMP`, `WAVEFILE/*.AWF` | ca. 18 MB | nein |

**Wir brauchen aus 64 MiB Vendor-Partitionen also rund 1,6 MB.**

## 2. Was unsere Kette insgesamt aus dem Stock zieht (vollständige Liste)

Aus dem Code erhoben, nicht aus dem Gedächtnis: `grep` über alle `request_firmware`-Namen der Serie `0091` - `0140`, über
`h713_disp_read()` in `arch/arm/mach-sunxi/h713_mips.c` und über die Dateipfade in `userspace/`.

| Artefakt | Wer lädt es | Woher heute | Stand |
|---|---|---|---|
| `h713-arisc.bin` (= `scp.bin`) | Kernel `0091`, `request_firmware` | TOC1 (roh, LBA 24576/32800) | extrahiert (S42) |
| `hy310-edid.bin` | Kernel `0091` | `vendor/etc/tvconfig/HDMI_EDID_14.bin` + `_20.bin` | extrahiert (S42) |
| `h713/msp-patch.bin` | Kernel `0137` | `libmspsound.so` | extrahiert (S42) |
| PQ-INIs (8 Dateien) | `h713-pq` | `vendor/etc/tvconfig/` | extrahiert (S42) |
| `mips/*` (6 Namen + 1 ProjectID) | **U-Boot** `h713_disp_load()` | `mmc 1:2` = p2 | **dieser Plan** |
| `hy310-hdcp22.bin` | Kernel `0094` (hdmirx) | Secure-Bereich | **bleibt weg**, siehe §6 |

Damit ist die Liste geschlossen. Weiteres Vendor-Material (Bootlogo, Fonts, Wavefiles, Batteriebilder, APKs, `system`/`product`)
berührt unsere Kette nicht.

## 3. Der Umbau ist klein

Der oft befürchtete „dann müssen wir alle Treiber umbauen" trifft nicht zu. **Kein Kerneltreiber fasst die MIPS-Dateien an** -
der Kernel spricht ausschließlich über `cpu_comm` mit der bereits laufenden Firmware. Alles hängt an einer Funktion:

```c
#define H713_DISP_FS_IF		"mmc"
#define H713_DISP_FS_DEV	"1:2"

static int h713_disp_read(const char *path, ulong addr, loff_t *len)
{
	ret = fs_set_blk_dev(H713_DISP_FS_IF, H713_DISP_FS_DEV, FS_TYPE_ANY);
	ret = fs_read(path, addr, 0, 0, len);
```

`FS_TYPE_ANY` liest ext4 genauso wie FAT. Zu ändern sind zwei Konstanten. Die **Projekt-ID** kommt heute als Argument aus dem
`bootcmd` (`h713_disp init 0x30`) und ist geräteabhängig - auf dem HY310 `0x30`, in der Partition liegen 15 Kandidaten.

**Eine Meldung im Bootlog führt hier in die Irre.** Der Kaltstart meldet:

```
H713 disp: project 0x30 is HY310 (QZ713 V3.1), panel 1920x1080
H713 disp: note: this board declares project 0x34 (panel_config.ini ProjectID = 52)
```

Das klingt nach einem Widerspruch, ist aber keiner: **die eigene `panel_config.ini` dieses Geräts sagt `ProjectID = 48` = `0x30`**,
an zwei byteidentischen Stellen (Vendor-Dateisystem und `Reserve0.fex`), und bei L018 ebenso. Die `0x34` in der Meldung ist die
einkompilierte Konstante `H713_DISP_BOARD_PROJECT_ID`, die aus der `panel_config.ini` von **Board B** (HY200) stammt (S42 §9).
Gerät, Datei und geladene TSE stimmen also überein. Offen ist nur, warum die Konstante in unserem U-Boot von Board B kommt - das
gehört zu §6, hat aber keine Wirkung auf den Betrieb.

## 4. Änderungen

### 4.1 U-Boot (`0023`)

- `h713_mips_dev` (Vorgabe `1:2`) und `h713_mips_path` (Vorgabe `mips`) als Env-Variablen, gelesen mit `env_get()` und Rückfall
  auf die heutigen Konstanten. U-Boot kennt `mmc 1#hy310-boot` (Partition per Name, `disk/part.c:749`), damit hängt nichts an
  Partitionsnummern.
- `h713_project` als Env-Variable, damit `bootcmd` `h713_disp init ${h713_project}` lauten kann statt `0x30`.
- Beide Vorgaben in `board/sunxi/hy310.env`, sodass ein Gerät ohne gespeicherte Env sich weiter verhält wie heute.

**Das ist der Umschalter, und er ist umkehrbar:** solange p2 noch steht, kann man zwischen alter und neuer Quelle hin- und
herschalten, ohne neu zu flashen. Erst wenn die neue Quelle nachgewiesen läuft, wird p2 überschrieben.

### 4.2 `h713-extract` (Version 0.3)

- FAT16-Leser für `bootloader_a`/`bootloader_b` mit Langnamen (die 8.3-Namen der `ProjectID`-Dateien sind unbrauchbar).
- Ausgabe nach `<out>/boot/mips/` mit denselben Namen, die U-Boot erwartet; Manifest wie gehabt (Pfad, Größe, sha256, Herkunft).
- **Projekt-ID: alle mitnehmen, die richtige benennen.** Siehe §4.5 - die 15 Dateien wiegen zusammen rund 400 kB, das Risiko einer
  falschen Auswahl ist damit null. Ins Manifest kommen: die benutzte ID, die deklarierte ID, und die Liste aller vorhandenen.
- Prüfungen: `display.bin` gegen die Revisionstabelle, TSE-Kopf, XML parsebar.

### 4.3 Layout v2 (löst `105` §1.2 ab)

eMMC 15.269.888 Sektoren, `LastUsableLBA` 15.269.854. Rohbereiche vor LBA 73728 bleiben unberührt.

| # | PARTLABEL | Start-LBA | Sektoren | Größe | Inhalt |
|---|---|---|---|---|---|
| 1 | `hy310-boot` | 73728 | 262144 | 128 MiB | ext4: `h713-kernel.fit`, `mips/` (Vendor-Artefakte), optional `h713-rescue.fit` |
| 2 | `hy310-data` | 335872 | 4492288 | 2,14 GiB | ext4: `/data` - Mitschnitte, optionale Logs |
| 3 | `hy310-uboot` | 4828160 | 30720 | 15 MiB | **roh**: proper @+0, SPL-Parkplatz @+8192, Env @+16384 |
| 4 | `hy310-rootfs` | 4858880 | 10410975 | 4,96 GiB | ext4: Debian ([`107`](107-plan-rootfs.md)) |

Vier Partitionen statt acht, `hy310-boot` von 64 auf 128 MiB (die Vendor-Artefakte liegen jetzt dort), Beginn bei 73728 statt
205824. Gewinn gegenüber `105` §1.2: 64,5 MiB und ein Layout ohne Fremdkörper. **Die Namen bleiben die Schnittstelle**, U-Boot und
Kernel adressieren über `PARTLABEL` beziehungsweise `mmc 1#name`.

### 4.4 Installer

- GPT nach §4.3, `--gpt-primary auto` schreibt die primäre Seite normal (gemessen: Stock-GPT hat 26 Einträge, Tabelle LBA 2-8,
  keine Kollision mit der SPL - S41 §7).
- Vendor-Artefakte aus dem `h713-extract`-Ausgabeordner nach `hy310-boot/mips/`, Prüfsummen gegen das Manifest.
- Env: `h713_mips_dev=1#hy310-boot`, `h713_project` aus dem Manifest.
- Die Sicherung vor dem Umbau umfasst weiterhin GPT, p1-p4 und den Bootbereich; sie ist **kein** Stock-Restore und heißt auch so
  (`RUECKWEG.md`).

### 4.5 Die Projekt-ID sicher bestimmen

Die Frage „woher wissen wir sicher, dass wir die richtige haben" hat drei Antworten, und zusammen schließen sie die Lücke.

**Erstens: die Datei sagt selbst, welche sie ist.** (13 Stück liegen in `mips/`, nicht 15 - die höhere Zahl im ersten Überschlag kam
von 8.3-Kurznamen ohne Langnamensauflösung.) Im 16-Byte-TSE-Kopf steht bei Offset 14 die ID als u16 little-endian -
am Gerät nachgemessen (10.09.):

```
ProjectID_0x0030.TSE   545345021a0001b09118844ef666 3000
ProjectID_0x0034.TSE   545345021a0002b091183843f666 3400
database.TSE           545345001a00cbc1901812cfe266 0000
```

Dateiname und Inhalt stimmen überein. Ein Extraktor kann also prüfen statt vertrauen.

**Zweitens: `display.bin` bestimmt die richtige.** `h713_mips_fw_revs[]` (`h713_mips.c:324-357`) ordnet der SHA-256 der Firmware
Board, Projekt-ID und Panel zu. Auf dem Dev-Gerät ergibt `16c74a28…` den Eintrag „HY310 (QZ713 V3.1)", Projekt `0x30`, Panel
1920×1080 - und genau diese TSE liefert das richtige Bild. Das ist der belastbare Weg für jedes Gerät, dessen Firmware wir kennen.

**Drittens: alle mitnehmen und die Wahl zur Laufzeit lassen.** Die 13 `ProjectID_*.TSE` wiegen zusammen rund 400 kB in einer
128-MiB-Partition. Sie alle zu installieren kostet nichts und macht die Frage für unbekannte Geräte harmlos: passt das Bild nicht,
ist `setenv h713_project 0x34; saveenv` die Korrektur, kein Neuflashen. Deshalb steht die ID in §4.1 als Env-Variable.

Die deklarierte ID aus `panel_config.ini` wird **gemeldet, aber nicht benutzt**. Auf beiden bekannten Geräten stimmt sie mit der
benutzten überein; belastbar ist trotzdem der Weg über die Firmware-Signatur, weil er auch dann trägt, wenn eine Datei fehlt.

## 5. Reihenfolge (wichtig)

1. U-Boot `0023` bauen, flashen, Vorgaben unverändert → Gerät verhält sich wie heute. **Prüfung:** `h713_disp init` lädt weiter aus `1:2`.
2. `h713-extract` 0.3, Vendor-Artefakte aus dem Image ziehen, gegen die Dateien in p2 byteweise vergleichen.
3. Artefakte in ein Verzeichnis auf **p5 des heutigen Layouts** legen (oder USB), `h713_mips_dev` umstellen, Kaltstart.
   **Erst wenn das Bild aus der neuen Quelle kommt**, ist der Weg bewiesen.
4. ~~FEL-Recovery nachweisen~~ - **erledigt, von Marco bestätigt (10.09.).** Der Rückweg steht, damit darf Layout v2 scharf
   geschrieben werden: ab da ist das Firmware-Image über FEL der einzige Weg zurück, weil p1-p4 nicht mehr existieren.
5. Layout v2, Rootfs nach [`107`](107-plan-rootfs.md), 20 Kaltstarts.

Die harte Bedingung des Plans (FEL) ist erfüllt. Es bleibt die Reihenfolge: Schritt 3 beweist die neue Quelle, **bevor** die alte
verschwindet. Solange p2 steht, ist ein Rückschalten eine Env-Zeile.

## 6. Arbeitspakete, die dabei aufgefallen sind

Das sind keine offenen Entscheidungen, sondern Arbeit, die noch getan werden muss. Wo eine Entscheidung nötig war, steht sie dabei.

- **HDCP fehlt und muss noch gemacht werden.** Der hdmirx-Treiber lädt `hy310-hdcp22.bin` über `request_firmware`; der Aufrufer
  wertet einen Fehler nur als `dev_warn` und überspringt den Schritt (`0094`, um Zeile 728). Das Release läuft also ohne, und der
  Schlüssel bleibt draußen - er ist Vendor-Material. **Offen bleibt der Zustand selbst:** ob HDCP-Quellen ohne Aushandlung
  überhaupt Bild liefern, ist nicht geprüft. **Entschieden:** der Schlüssel wird nicht ausgeliefert und v0.1 wirbt nicht mit HDCP.
  **Zu tun:** eine Messung mit einer geschützten Quelle, dann die Matrix-Zeile „HDCP nicht unterstützt" mit Beleg.
- **EDID 1.4 und 2.2 sind noch offen.** Heute wird ein 512-B-Block aus `HDMI_EDID_14.bin` + `HDMI_EDID_20.bin` unverändert
  durchgereicht. Was davon welche Modi freigibt und was bei 4K/HDR passiert, ist ungeklärt (bekannte Grenzen in
  [`60`](60-offen.md): 1600×900 und 120 Hz fehlen in `kHalSignalID_*`). **Entschieden:** der Stock-EDID-Block geht unverändert
  durch, es wird für v0.1 keiner gebaut. **Zu tun:** aufschreiben, welche Modi er freigibt und was bei 4K und HDR geschieht;
  Matrix-Zeile „eingeschränkt" mit dieser Tabelle.
- **`hy310-hdcp22.bin` liegt im heutigen Netboot-Root** unter `/lib/firmware` und darf beim Bauen des Release-Rootfs nicht
  mitkopiert werden ([`107`](107-plan-rootfs.md) §5).
- **Die HDCP-Schlüssel liegen roh im Bootbereich** (LBA 12288…12398, Fund 10.09., [`109`](109-plan-layout-v3.md) §2.3) - nicht nur
  in der Stock-Partition `private`. Sie sind gerätespezifisch und nicht wiederherstellbar; jedes Werkzeug, das den Bootbereich
  beschreibt, muss sie aussparen. **Todo:** der Installer bekommt einen Scan, der solche Blöcke auch bei fremden
  Firmwares findet, sichert und bei jeder Abweichung abbricht ([`109`](109-plan-layout-v3.md) §9).
- Bootlogo, Fonts und Wavefiles gehen mit p1/p2 verloren. Für einen späteren eigenen Startbildschirm wäre `LogoRegData.bin` plus
  ein eigenes BMP der Weg; nicht v0.1.

- **Projekt-ID - erledigt, ein Rest bleibt.** Die frühere Sorge („Gerät sagt 0x34, wir laden 0x30") hat sich aufgelöst: die eigene
  `panel_config.ini` sagt `0x30`, die `0x34` im Bootlog ist eine einkompilierte Konstante von Board B (§3, S42 §9).
  **Entschieden:** die benutzte ID kommt aus der Firmware-Signatur, die deklarierte wird nur gemeldet, alle 13 TSE-Dateien werden
  installiert (§4.5). **Bleibt zu tun:** herausfinden, warum `H713_DISP_BOARD_PROJECT_ID` in unserem U-Boot von Board B stammt -
  kosmetisch, ohne Wirkung auf den Betrieb.
- **PQ liegt heute halb abgeleitet vor.** `h713-pq` liest die Vendor-INIs zur Laufzeit und kopiert nichts (`quellen.py`, Suchpfad
  `$HY310_TVCONFIG` → `/etc/hy310/tvconfig` → Arbeitsbaum). **Aber** `gamma-standard.bin` (2 kB) ist als Rechenergebnis aus
  Stock-Daten in `userspace/h713-tv/` eingecheckt und wird mitinstalliert; `h713-tv` lädt es als Vorgabe. Für das Release gilt:
  `h713-extract` legt die acht PQ-Dateien nach `/etc/hy310/tvconfig`, `h713-pq` rechnet Gamma und Presets dort zur Laufzeit,
  und die abgeleitete Datei fliegt aus dem Repo. Bis dahin bleibt sie drin - dann aber mit dem Lizenzhinweis, dass sie aus
  Vendor-Daten gerechnet ist. Der Pfad `/etc/hy310/tvconfig` ist damit die Schnittstelle zwischen Extraktor und Userspace.

## 7. Was am Gerät schon bewiesen ist (10.09.)

| Schritt aus §5 | Stand |
|---|---|
| 1. U-Boot `0023` mit Env-Umschalter, Vorgaben unverändert | **erledigt.** `tftp/uboot-proper.GUT-gate-v5-20260910.bin` (890.233 B, CRC32 `be77a83a`), geflasht; Kaltstart lädt wie zuvor aus `mmc 1:2`, Meldung nennt jetzt Gerät und Pfad. |
| 2. Artefakte extrahieren und vergleichen | **erledigt** (`h713-extract` 0.3, S42 §9): 19 Dateien, Referenzgrößen und TSE-Köpfe stimmen. |
| 3. Aus der neuen Quelle laden | **erledigt.** p5 (`boot_a`, Android, 64 MiB) als ext4 formatiert, `mips/` hineinkopiert, `h713_mips_dev=1:5`, Kaltstart: `loading vendor artifacts from mmc 1:5:mips`, Firmware-Identität akzeptiert, Panel-Timing latched, Linux bis Login. Beleg `analyse/boot/v5-mips-aus-p5-20260910.txt`. |
| 4. FEL | von Marco bestätigt. |
| 5. Layout v2 scharf | **erledigt 10.09.** Installer 0.3 (`--steps gpt,mkfs,mips,env`) hat die GPT ersetzt: vier Partitionen, alle 26 Stock-Einträge weg. p1 trägt `mips/` mit 19 Artefakten, U-Boot lädt sie über **`h713_mips_dev=1#hy310-boot`** - die Adressierung per Partitionsname funktioniert jetzt, weil der GPT-Name stimmt. Kaltstart: Firmware-Identität akzeptiert, Panel latched, Linux bis Login. Belege `analyse/boot/gpt-layout-v2-20260910.txt` und `analyse/boot/layout-v2-kaltstart-20260910.txt`. |
| 6. Rootfs auf p4 | offen ([`107`](107-plan-rootfs.md)); bis dahin bootet das Gerät weiter per Netz, weil `boot_emmc` ohne FIT still scheitert. |

**Damit ist die Kernfrage dieses Plans beantwortet und umgesetzt:** die Vendor-Partitionen sind weg, die Artefakte liegen in unserer
eigenen ext4-Partition, und die Anzeige läuft daraus. Das Gerät hat kein Stock-Android mehr - was nach Marcos Entscheidung vom 10.09.
auch nie wieder gebraucht wird.

**Ist-Layout am Gerät (10.09.):**

| # | PARTLABEL | Start-LBA | Größe | Inhalt |
|---|---|---|---|---|
| 1 | `hy310-boot` | 73728 | 128 MiB | ext4, `mips/` (19 Artefakte, 2,0 MB); später auch `h713-kernel.fit` |
| 2 | `hy310-data` | 335872 | 2,14 GiB | ext4, leer |
| 3 | `hy310-uboot` | 4828160 | 15 MiB | roh: proper (v5), SPL-Parkplatz, Env |
| 4 | `hy310-rootfs` | 4858880 | 4,96 GiB | ext4, leer - wartet auf [`107`](107-plan-rootfs.md) |

Roh und außerhalb jeder Partition, unberührt: SPL (LBA 16), Vendor-boot0-Kopie (256), `sunxi-package` A/B (24576/32800).

**Zwei Befunde für den Installer:**

- **`1#partname` verlangt den GPT-Namen, nicht das Dateisystem-Label.** Ein Versuch mit `h713_mips_dev=1#hy310-boot` scheiterte
  (`cannot select mmc 1#hy310-boot`), weil p5 im GPT noch `boot_a` heißt und `hy310-boot` nur das ext4-Label war. Unter Layout v2
  trägt die Partition den richtigen GPT-Namen, dann greift die Adressierung per Name. Bis dahin die Nummer benutzen.
- **`bootloader_a` (p1) ist auf dem Dev-Gerät keine saubere Kopie von p2** - dort liegen `display-shifted.bin` und ein
  `display.bin.backup-20260528-2354`, unsere eigene Spur vom Mai, und `display.bin`/`display_cfg.xml` weichen ab. Extrahiert wird
  deshalb immer aus p2 (S42 §9).

## 8. Was der Installer 0.3 dafür bekommen hat

- `EXPECT_JSON` ist leer - es wird keine Vendor-Partition mehr bewahrt; der GPT-Planer nimmt die Zahl der zu erhaltenden Einträge
  jetzt aus der Liste statt aus einer festen `4`.
- `LAYOUT_JSON` = Layout v2, `LBA_GUARD` von 205824 auf **73728**.
- Neuer Schritt **`mips`** mit `--mips VERZ`: kopiert die Artefakte aus dem `h713-extract`-Ausgabeordner nach `hy310-boot/mips/`
  und vergleicht sie byteweise zurück.
- Env-Vorgaben: `boot_emmc` liest über `mmc 1#hy310-boot`, dazu `h713_mips_dev`, `h713_mips_path`, `h713_project`.
- Alle Schritte auf die neuen Nummern umgestellt (p1 boot, p2 data, p3 uboot, p4 rootfs).
