# S41 — R1-Installer `hy310-install.sh` (Board-Seite)

**Auftrag:** `analyse/release/arbeit/r1-installer/AUFTRAG.md`, Plan [`105`](../105-plan-release.md) §1.2/§2 (R1), [`20`](../20-flashen-und-recovery.md).
**Regeln eingehalten:** kein Board, kein Netz, kein Bau; geschrieben nur in `analyse/release/arbeit/r1-installer/` und in diesen Bericht.
**Stand:** Skript liegt, `bash -n` sauber, `--dry-run` läuft ohne jeden Schreibzugriff durch (hinterlässt keine Spur). GPT- und Env-Schreiber
sind gegen Attrappen **wirklich getestet**, inklusive Positivkontrollen für die Schutzzonen.

Lieferung:

| Datei | Zweck |
|---|---|
| `analyse/release/arbeit/r1-installer/hy310-install.sh` | der Installer, ein Bash-Skript mit zwei eingebetteten Python-Werkzeugen (GPT-Schreiber, Env-Schreiber) |
| `analyse/release/arbeit/r1-installer/RUECKWEG.md` | warum es kein `hy310-uninstall.sh` gibt und welche Rückwege es wirklich gibt |
| dieser Bericht | Entscheidungen, Ablauf, Testrezept, Risiken |

**Wichtigster Befund vorab:** die Größe von p8 in Plan 105 §1.2 ist um 33 Sektoren zu groß, und die primäre GPT-Tabelle könnte auf diesem
Gerät gar nicht gültig sein, weil unsere SPL bei LBA 16 darin liegt. Beides ist im Skript behandelt, beides gehört in den Plan (§2.2, §2.3).

---

## 1. Belegte Vorbedingungen (am Host geprüft, ohne Board)

| Behauptung | Beleg |
|---|---|
| Kernel kann `root=PARTLABEL=…` | `mainline/build/linux-6.18.38-bad2f16b…/block/early-lookup.c:248` `strncmp(name, "PARTLABEL=", 10)` |
| ext4, GPT, SD/MMC fest im Kernel (kein initrd nötig) | `.config`: `CONFIG_EXT4_FS=y`, `CONFIG_EFI_PARTITION=y`, `CONFIG_MMC_SUNXI=y`, `CONFIG_MMC_BLOCK=y` |
| Env-Vorgabe enthält bereits `h713_boot=emmc`, `boot_emmc`, `bootcmd` | `mainline/external/u-boot/board/sunxi/hy310.env`; `CONFIG_ENV_OFFSET=0x93d80000`, `CONFIG_ENV_SOURCE_FILE="hy310"` in `configs/hy310_netboot_gate_defconfig` |
| Netboot-Root passt in p8 | `du -sx /srv/h713-rootfs` = 2,4 GiB gegen 4,96 GiB |
| Netz bleibt nach dem Umzug DHCP | `/srv/h713-rootfs/etc/network/interfaces`: `allow-hotplug eth0 / iface eth0 inet dhcp`; `ifupdown` + `isc-dhcp-client` installiert; `/etc/resolv.conf` ist eine echte Datei, kein Symlink |
| Werkzeuge im Netboot-Root **vorhanden** | `partx`, `blockdev`, `lsblk`, `blkid`, `wipefs`, `mkfs.ext4`, `e2label`, `tune2fs`, `tar`, `python3`, `flock`, `ssh`/`scp`, `udevadm`, `sha256sum` |
| Werkzeuge **nicht** vorhanden | `sfdisk`/`fdisk`, `parted`/`partprobe`, `gdisk`/`sgdisk`, `rsync`, `curl`, `wget`, `libubootenv-tool` |
| alte fstab im Netboot-Root zeigt auf `/dev/mmcblk0p26` | `/srv/h713-rootfs/etc/fstab` — muss ersetzt werden, sonst versucht das Ziel-System die (dann nicht mehr existierende) UDISK zu mounten |

## 2. Entscheidungen

### 2.1 GPT: eigener Python-Schreiber statt `sgdisk` — begründet

Gewählt: **eigener Schreiber**, eingebettet im Skript (kein zweites Deployment-Artefakt).

- `gdisk` ist auf dem Board **nicht** installiert. `sgdisk` würde `apt` verlangen, also Netz *und* eine gestellte Uhr — mitten in einem
  Schritt, der die Platte umschreibt. Der eigene Schreiber braucht nur `python3` (da).
- Die Auflage „p1–p4 identisch **inkl. GUIDs**" wird wörtlich erfüllt: die vier Einträge werden **byteweise aus der vorhandenen Tabelle
  übernommen**, nicht neu erzeugt. Ebenso bleiben DiskGUID, `FirstUsableLBA`, `NumberOfPartitionEntries` und `SizeOfPartitionEntry`
  unverändert. Die Unique-GUIDs von p1–p4 stehen nirgends im Projekt — sie *müssen* vom Gerät gelesen werden, egal welches Werkzeug schreibt.
- Der Schreiber kann etwas, das `sgdisk` nicht kann: **die SPL bei LBA 16 schützen** (§2.3) und **die Backup-Seite lesen, wenn die primäre
  kaputt ist** (§2.3). `sgdisk` würde in beiden Fällen das Falsche tun.
- Trockenlauf: `plan` rechnet alles inklusive der drei CRC32 aus und schreibt nichts. Nach dem Schreiben liest das Werkzeug die Tabelle
  zurück und vergleicht sie byteweise; Abweichung = Abbruch.

Reihenfolge beim Schreiben: erst Backup-Tabelle und Backup-Kopf, dann primäre Tabelle und Kopf. Bricht es dazwischen ab, ist der Stand
eindeutig (die Backup-Seite ist die neue) und beide Leser — Linux `block/partitions/efi.c` und U-Boot `part_efi.c` — fallen ohnehin auf die
gültige Seite zurück.

### 2.2 p8 ist im Plan 33 Sektoren zu groß — Skript rechnet selbst

Plan 105 §1.2 gibt p8 mit **10.411.008** Sektoren ab LBA 4.858.880 an. Das endet bei LBA 15.269.887 — das ist der **Backup-GPT-Kopf**.
Nach UEFI ist `LastUsableLBA` = Gesamtsektoren − 34 = **15.269.854** (die Stock-Tabelle bestätigt das: `UDISK` endet genau dort).
Richtig sind **10.410.975** Sektoren (4,964 GiB), Ende LBA 15.269.854.

Das Skript nimmt deshalb `"sectors": -1` für p8 und füllt **bis zum `LastUsableLBA` aus dem Kopf des Geräts**; eine fest verdrahtete Größe,
die zu weit reicht, würde es kürzen und das melden. **Bitte 105 §1.2 auf 10.410.975 korrigieren** (Zeile p8), sonst weichen Plan und Gerät
dauerhaft voneinander ab.

### 2.3 Die primäre GPT liegt möglicherweise unter unserer SPL — offen, im Skript abgefangen

Die Partitionstabelle einer GPT steht üblicherweise ab LBA 2. Bei 128 Einträgen à 128 Byte belegt sie LBA 2–33.
**Unsere SPL liegt bei LBA 16 und ist 64 Sektoren lang** (`doku/20`: `mmc write … 0x10 0x40`). Bei 128 Einträgen überschneiden sich beide —
dann ist die primäre Tabelle auf dem Gerät seit dem ersten SPL-Flash zerstört, und Kernel wie U-Boot lesen längst die **Backup-Seite**
(beide tun das automatisch und still). Bei ≤ 56 Einträgen (≤ 14 Sektoren, LBA 2–15) gibt es kein Problem; Allwinner-Tabellen sind oft so
zugeschnitten. **Welcher Fall hier vorliegt, steht in der Live-GPT nicht drin** — `lsblk` zeigt `NumberOfPartitionEntries` nicht.

Das Skript behandelt beide Fälle:

- `load()` liest wie der Kernel: erst primär, bei kaputter CRC die Backup-Seite, und **sagt es laut**.
- Vor jedem Schreiben wird geprüft, ob die primäre Tabelle in LBA 16–79 ragen würde.
  - `--gpt-primary auto` (Vorgabe): dann wird die **primäre Seite gar nicht geschrieben** — nur Backup-Tabelle und Backup-Kopf.
    Das ist exakt der Zustand, in dem das Gerät heute schon läuft, und es kann die SPL nicht beschädigen.
  - `--gpt-primary move`: legt die primäre Tabelle hinter die SPL (LBA 80) und hebt `FirstUsableLBA` auf 112 an. Danach ist auch die
    primäre Seite wieder gültig. Sauberer, aber eine Abweichung vom Stock-Kopf — deshalb nicht die Vorgabe.
- Eine `assert` unmittelbar vor dem Schreibaufruf sichert die Regel zusätzlich ab.

**Zu messen (eine Zeile, kein Risiko):** `sudo ./hy310-install.sh --dry-run --steps precheck --backup-dir /tmp` am Board — die Zeile
„… Einträge à … Byte ab LBA … (Tabelle LBA a..b)" und „gültige Seite: primär|backup" beantworten die Frage endgültig.

### 2.4 Env: eingebauter Schreiber statt `fw_setenv` — und die Falle dahinter

`libubootenv-tool` ist im Netboot-Root **nicht** installiert; `apt` mitten im Installationslauf wäre eine unnötige Abhängigkeit.
Die Env ist nicht redundant (drei Felder in `fw_env.config`), das Format ist trivial: 4 Byte CRC32 (LE) + `name=wert\0`-Liste + `\0`.

Die eigentliche Falle ist eine andere: **eine gültige gespeicherte Env ersetzt die eingebaute Vorgabe komplett** — U-Boot mischt nicht.
Ein naives `fw_setenv h713_boot emmc` auf einem Gerät ohne gespeicherte Env erzeugt eine Env, die **nur** `h713_boot` enthält; `bootcmd`,
`boot_emmc` und `boot_net` wären damit weg und das Gerät bliebe am Prompt stehen. Deshalb:

- Ist **keine** gültige Env gespeichert: **nichts tun**. Die Vorgabe aus `board/sunxi/hy310.env` sagt bereits `h713_boot=emmc`.
  Das Skript sagt das und macht weiter (`--force-env` erzwingt eine vollständig geschriebene Env).
- Ist eine gültige Env gespeichert: `h713_boot=emmc` setzen, **alle übrigen Variablen behalten** (getestet: `ethaddr` überlebt), und
  **fehlende Pflichtvariablen aus der Vorgabe ergänzen** (`bootcmd`, `boot_emmc`, `boot_net`, `bootargs_base`, `h713_gate` …) — nötig für
  Geräte, deren gespeicherte Env noch aus der Zeit vor U-Boot-Commit 0021 stammt.
- Danach wird zurückgelesen und verglichen. Ist die Env schon genau richtig, wird gar nicht geschrieben (idempotent).
- `--use-fw-setenv` benutzt trotzdem `fw_setenv`, falls vorhanden. `/etc/fw_env.config` (`/dev/mmcblk0 0x93d80000 0x10000`) wird im
  Ziel-Root **immer** angelegt; `libubootenv-tool` selbst nur mit `--apt` (braucht Netz und `date -u -s`, ist nicht kritisch).

### 2.5 Kleinere Festlegungen

- **Kopieren mit `tar --one-file-system`** statt `cp -ax` (kein `rsync` am Board). `--one-file-system` lässt `/proc`, `/sys`, `/dev`, `/run`
  und die eigenen Ziel-Einhängepunkte automatisch draußen; ausgeschlossen werden zusätzlich `tmp/*`, `var/tmp/*`, `.deb`-Cache, `.nfs*`-Leichen,
  `core` und `var/log/journal/*`. `--numeric-owner --xattrs --acls`, Pipe mit `pipefail`.
- **FIT-Quelle** kann ein Pfad, `user@host:/pfad` (scp) oder eine `http(s)`-URL sein — letztere über `python3 urllib`, weil `curl`/`wget` fehlen.
  Sie wird erst nach `.h713-kernel.fit.neu` geschrieben, auf die Kennung `d00dfeed` geprüft und dann umbenannt: ein abgebrochener Lauf
  hinterlässt keine halbe FIT.
- **`/boot` ist p5.** Die Kopie des Netboot-Roots bringt ein leeres `/boot` mit, das durch den Mount verdeckt wird — unkritisch.
- **`/etc/fstab`** wird komplett neu geschrieben (alte als `fstab.vor-hy310-install` gesichert), weil die vorhandene auf `/dev/mmcblk0p26` zeigt.
- **Idempotenz**: jeder Schritt prüft seinen Vorzustand — GPT (`state` meldet `stock`/`teil`/`ziel`), `mkfs` überspringt fertige ext4 mit
  passendem Label (`--force-mkfs` erzwingt), FIT wird per Prüfsumme ausgewiesen, Env vergleicht vor dem Schreiben. `--steps`/`--skip`
  erlauben den Wiedereinstieg an jeder Stelle.
- **Sicherungsziel** darf nicht auf `/dev/mmcblk0` liegen (wird geprüft), und der Installer verweigert den Dienst, wenn das laufende System
  selbst von `/dev/mmcblk0` kommt oder etwas davon eingehängt ist.

## 3. Ablauf des Skripts

```
hy310-install.sh --fit <pfad|user@host:pfad|url> --backup-dir <verz> [--dry-run] [--yes]
```

| # | Schritt | Was passiert | Schreibt auf den eMMC? |
|---|---|---|---|
| 1 | `precheck` | root, 15.269.888 Sektoren, Werkzeuge, läuft nicht vom Ziel, nichts eingehängt, GPT lesen und p1–p4 gegen den Sollwert prüfen, Layout-Plan mit CRCs, LBA 16 und LBA 4828160 nur *anzeigen*, Env anzeigen, FIT-Kennung, Platz für Rootfs und Sicherung | nein |
| — | Rückfrage | „tippe JA" (entfällt bei `--yes`/`--dry-run`) | — |
| 2 | `backup` | `gpt-primary.bin` (LBA 0–33), `gpt-backup.bin` (letzte 33), `lba0-16384.bin` (8 MiB), p1–p4 roh, `uboot-env.bin`, `INFO.txt`, `manifest.sha256` → `hy310-backup-<datum>.tar` (~72 MiB), optional per `scp` weg | nein (nur lesen) |
| 3 | `gpt` | neue Tabelle nach §1.2, p1–p4 byteidentisch, p5–p8 neu, Rest genullt; Rücklesung; `partx -u` / `blockdev --rereadpt` / `udevadm settle` | ja: LBA 1–33 (siehe §2.3) und die letzten 33 LBAs |
| 4 | `mkfs` | ext4 auf p5/p6/p8 mit Label = PARTLABEL, `-m 1 -E nodiscard`; **p7 bleibt roh** | ja: nur in p5/p6/p8 |
| 5 | `rootfs` | Mounts unter `/run/hy310-install/`, `tar`-Pipe vom laufenden Root nach p8, danach `proc sys dev run tmp mnt boot data` anlegen | ja: nur p8 |
| 6 | `kernel` | FIT holen, Kennung prüfen, als `h713-kernel.fit` auf p5 | ja: nur p5 |
| 7 | `config` | `/etc/fstab` (PARTLABEL), `/etc/fw_env.config`, NFS-Reste, `hostname`/`interfaces` prüfen, optional `--apt` | ja: nur p8 |
| 8 | `env` | Env bei Byte `0x93d80000` (LBA 4844544, in p7) nach §2.4 | ja: 64 KiB in p7 |
| 9 | `report` | Tabelle, Prüfsummen von FIT und Sicherung, Aushängen, „was jetzt zu tun ist", Rückweg | nein |

Ohne `--dry-run` läuft die gesamte Ausgabe zusätzlich nach `/var/log/hy310-install.log`.

## 4. Testrezept für die Hauptsitzung

Am Board, aus dem laufenden Netboot-Linux, **in kurzen Schritten** (Board-Regel):

```bash
# 0) Skript aufs Board bringen (vom Host)
scp analyse/release/arbeit/r1-installer/hy310-install.sh root@<board>:/root/
scp tftp/h713-kernel-netboot.fit root@<board>:/root/h713-kernel.fit

# 1) Nur die Vorprüfungen — beantwortet die offene Frage aus §2.3
./hy310-install.sh --dry-run --steps precheck --backup-dir /root
#    Achten auf:  "… Einträge à … Byte ab LBA … (Tabelle LBA a..b)"
#                 "gültige Seite: primär|backup"
#                 "p8 …: Größe auf 10410975 Sektoren gesetzt"
#                 die vier p1..p4-Zeilen mit den GUIDs

# 2) Vollständiger Trockenlauf, alle Schritte lesen
./hy310-install.sh --dry-run --fit /root/h713-kernel.fit --backup-dir /root

# 3) Sicherung zuerst und einzeln, aufs Host-NFS oder per scp weg
./hy310-install.sh --steps backup --backup-dir /srv-oder-usb --yes
sha256sum -c manifest  # aus dem tar

# 4) Scharf, mit Rückfrage
./hy310-install.sh --fit /root/h713-kernel.fit --backup-dir /srv-oder-usb
```

Danach **vor** dem Neustart prüfen:

```bash
lsblk -o NAME,SIZE,PARTLABEL,FSTYPE,LABEL /dev/mmcblk0    # p5 hy310-boot … p8 hy310-rootfs
blkid /dev/mmcblk0p5 /dev/mmcblk0p6 /dev/mmcblk0p8
dd if=/dev/mmcblk0 bs=512 skip=16 count=1 | head -c 16 | xxd   # eGON.BT0 muss stehen
```

Am U-Boot-Prompt (UART, `tools/uart-uboot.py`):

```
ext4ls mmc 1:5            -> h713-kernel.fit
ext4ls mmc 1:2            -> mips/display.bin, display_cfg.xml, LogoRegData.bin (MÜSSEN noch da sein)
printenv h713_boot        -> emmc
```

Dann `reset`. Erwartet: `h713_disp init`, `ext4load mmc 1:5`, `bootm`, Kernel mit
`root=PARTLABEL=hy310-rootfs`, Login ohne Host. Geht etwas schief, greift `boot_net` von selbst.
Wenn der eMMC-Boot steht: die 20 Kaltstarts aus Paket R5.

## 5. Risiken und offene Annahmen

| # | Punkt | Bewertung |
|---|---|---|
| R1 | **Primäre GPT vs. SPL bei LBA 16** (§2.3) | im Skript abgefangen, aber **ungemessen**. Erst Schritt 1 des Testrezepts, dann entscheiden, ob `--gpt-primary move` sinnvoll ist. |
| R2 | **p8-Größe im Plan falsch** (§2.2) | Skript rechnet richtig; Plan 105 §1.2 nachziehen. |
| R3 | Kopie eines **laufenden** Systems | `tar` sieht einen inkonsistenten Moment, wenn nebenher geschrieben wird. Vor Schritt 5 `systemctl stop hy310-tv@video1 dnsmasq hostapd` und keine Bauläufe. Journal wird ohnehin ausgelassen. |
| R4 | `partx -u` bringt p5–p8 evtl. nicht sofort | Das Skript meldet fehlende Knoten als Warnung. Notfalls `reboot` ins Netboot und mit `--steps mkfs,rootfs,kernel,config,env` weitermachen — dafür ist die Schrittwahl da. |
| R5 | **PARTLABEL-Auflösung im Kernel** | Code belegt (§1), am Gerät aber noch nie ausgeführt. Rückfall ist `boot_net`; notfalls in `boot_emmc` auf `root=/dev/mmcblk0p8` umstellen. |
| R6 | Kein `initrd` | ext4 und MMC sind fest im Kernel — geprüft. Bei einem anderen Kernel-Build erneut prüfen. |
| R7 | Uhr am Board | `--apt` (und jedes spätere `apt`) braucht `date -u -s "…"` vorher, sonst schlägt die Signaturprüfung fehl. Der Installer selbst braucht kein Netz. |
| R8 | Sicherung ≠ Stock-Restore | ausdrücklich in `RUECKWEG.md` und in `INFO.txt` im tar. Kein `hy310-uninstall.sh`. Wer den Stock behalten will, muss **vorher** den ganzen eMMC dumpen (7,3 GiB). |
| R9 | SD-Karte als Alternative (105 §2 R1) | **nicht enthalten.** Das Skript ist auf `/dev/mmcblk0` mit genau 15.269.888 Sektoren festgenagelt; `--device` allein reicht für eine SD-Karte nicht, weil Layout und Prüfungen daran hängen. |
| R10 | `hy310-fel-install` (R0) | nicht Teil dieses Pakets. |

## 6. Was noch fehlt (Restliste, nach Wichtigkeit)

1. **Messung am Board** nach §2.3 — eine Zeile, entscheidet über `--gpt-primary`.
2. **Plan 105 §1.2 korrigieren**: p8 = 10.410.975 Sektoren.
3. **Ersten scharfen Lauf** nach dem Testrezept, dann Bericht ergänzen.
4. SD-Karten-Variante (R9) und `hy310-fel-install` (R10), falls für v0.1 gewollt.
5. `h713-rescue.fit` auf p5 (in §1.2 als „optional" vorgesehen) — im Skript noch nicht vorgesehen.

## 7. Nachtrag 10.09.2026 00:20 — Version 0.2 (Hauptsitzung, nicht der Agent)

**Der Env-Ort war kein Rätsel, sondern ein U-Boot-Fehler.** `env/mmc.c` reicht `CONFIG_ENV_OFFSET` durch `ofnode_conf_read_int()` (int):
`0x93d80000` → negativ → plus Kapazität → auf 32 Bit gekürzt = `0x65d80000`. Fix U-Boot `0022`, proper v4 (`doku/30` §16). Änderungen am Skript:

| Was | Wie |
|---|---|
| Env-Ort nicht annehmen | `env_survey()`: Python-`scan` prüft Kandidaten (Release-Ort, Zwilling `0x65d80000`) und alle 64-KiB-Fenster von p7; `--env-scan full` die ganze eMMC (ein Leser, 16-MiB-Stücke; Attrappe 7,3 GiB sparse in 4 s, am Gerät ca. 1 min). Gültig = CRC stimmt **und** Variablennamen sind druckbares ASCII (Zufallsdaten: kein Treffer). |
| Geflashten U-Boot belegen | `--uboot-bin DATEI`: byteweiser Vergleich mit LBA 4828160 (`cmp -n`). Passt er nicht → `check_fail`. |
| Entscheidung im Env-Schritt | Env am Release-Ort → setzen. Env nur am Zwilling: mit geprüftem proper → `--env-migrate` übernimmt sie (Quelle bleibt), sonst nur Hinweis; ohne geprüften proper → `check_fail` („Env-Ort passt nicht zum Release-U-Boot"). Keine Env → Vorgabe greift, nichts schreiben (`--force-env` wie bisher). |
| Boot-Kette setzen statt ergänzen | `ENV_SET` (`h713_boot`, `bootcmd`, `boot_emmc`, `boot_net`, `bootargs_base`) wird immer gesetzt, `ENV_ADD` (`h713_gate`, `bootfile`, `serverip`, `nfsroot`) nur ergänzt. Grund: die gespeicherte Dev-Env trägt das alte reine Netboot-`bootcmd` von vor `0021`; bloßes Ergänzen hätte es stehen lassen und eMMC-Boot wäre nie gelaufen. |
| `fw_env.config` | Kommentarzeile mit Herkunft; Offset bleibt der Release-Ort. `--use-fw-setenv` warnt, dass es nur `h713_boot` setzt. |
| Root-Größe | `du -sxk /` statt `df` (NFS-Root zeigte die Host-Platte). |

**Test gegen Attrappe (sparse 15.269.888 Sektoren, alte Env bei `0x65d80000` mit `h713_gate=0`, `ethaddr`, altem `bootcmd`; 64 KiB Zufall bei
`0x12340000`; Release-Ort leer):** `scan quick` und `scan full` finden genau den Zwilling; `set --from` im Trockenlauf zeigt den Diff und
schreibt nichts; scharf: 12 Variablen am Release-Ort, `bootcmd` neu, `h713_gate=0`/`ethaddr` übernommen, Quelle unverändert; zweiter Lauf
„bereits genau so — nichts geschrieben"; `scan` danach meldet beide Orte. `bash -n` und `--dry-run --steps env` sauber.

**Am Gerät erledigt (10.09. 00:55):** v4 geflasht (`doku/20` Weg 4 über UART), `reset`, `h713_gate=0`, `serverip=192.168.8.123`, `saveenv`.
Precheck aus dem Netboot-Linux (`--dry-run --steps precheck --uboot-bin /root/hy310/uboot-proper-gate-v4.bin --no-backup --yes`):
„✓ U-Boot proper bei LBA 4828160 ist byteidentisch mit … (886137 Byte)", „✓ gültige Env am Release-Ort 0x93d80000 (75 Variablen:
h713_boot=emmc h713_gate=0 bootcmd=ja)", „! gültige Env am 2-GiB-Zwilling 0x65d80000 (80 Variablen …)" — der Rest des alten U-Boot, erwartet.
**§2.3 damit gemessen:** „26 Einträge à 128 Byte ab LBA 2 (Tabelle LBA 2..8)", „gültige Seite: primär" → keine Kollision mit der SPL,
`--gpt-primary auto` schreibt die primäre Seite normal. Root belegt 3.008.740 KiB, p8 fasst 5.205.488 KiB. Alle Prüfungen bestanden.
Nächster Schritt: scharfer Lauf nach §4, sobald die Rootfs-Entscheidung (schlank < 1 GB) gefallen ist.
