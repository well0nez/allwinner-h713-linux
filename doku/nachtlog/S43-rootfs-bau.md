# S43 - Bauskript für das schlanke Release-Rootfs

**Auftrag:** Plan [`107`](../107-plan-rootfs.md) (vollständig, einschließlich §8 „Entschieden"), Ziel-Layout
[`109`](../109-plan-layout-v3.md) §2.2/§4. Vorbild, ausdrücklich **nicht** Vorlage: `mainline/tools/rootfs/build.sh`.
**Regeln eingehalten:** geschrieben nur in `analyse/release/arbeit/rootfs/` und in diesen Bericht. Kein Gerät, kein Commit,
nichts in `mainline/`, `userspace/`, `re/` oder `/srv/` verändert (`/srv/h713-rootfs` nur gelesen).
**Stand:** Skripte liegen, `bash -n` sauber, `--dry-run` läuft ohne Netz und ohne `mmdebstrap` durch.

Lieferung:

| Datei | Zweck |
|---|---|
| `analyse/release/arbeit/rootfs/build-rootfs.sh` | Bootstrap + Overlay + Nacharbeit + Abnahme + tar/ext4 |
| `analyse/release/arbeit/rootfs/install-projekt.sh` | die Projektteile (hy310-tv, Kernelmodule, hy310-pq) samt **Blob-Sperre**; auch allein aufrufbar |
| `analyse/release/arbeit/rootfs/packages.txt` | 17 Pakete über `minbase` hinaus, jedes mit Begründung, dazu die Liste des bewusst Weggelassenen |
| `analyse/release/arbeit/rootfs/overlay/` | 15 Dateien + `/etc/hy310/tvconfig/` (leer) |
| dieser Bericht | Aufbau, Entscheidungen, Voraussetzungen, Größe, Lücken |

---

## 1. Aufbau

Zwei Skripte statt eines, und das ist keine Formsache: nach [`109`](../109-plan-layout-v3.md) §4.2 wird **ein Bau an zwei Orte**
gelegt - `hy310-rootfs` auf der eMMC und die NFS-Wurzel auf dem Host. Wenn `hy310-tv` oder die Kernelmodule neu gebaut werden,
soll man sie in einen bestehenden Baum nachziehen können, ohne ein Debian neu zu bootstrappen. Deshalb ist der Projektteil ein
eigenes, allein aufrufbares Skript:

```
./install-projekt.sh /srv/h713-rootfs-neu        # nur die Projektteile nachziehen
./install-projekt.sh --dry-run /pfad/zum/baum    # zeigen, was es täte
```

`build-rootfs.sh` läuft in sechs Schritten:

| # | Schritt | was dabei passiert |
|---|---|---|
| 1 | `mmdebstrap --variant=minbase` | Debian trixie/arm64, signiert gegen `debian-archive-keyring`, `--include` aus `packages.txt` |
| 2 | auspacken | `tar --numeric-owner --xattrs --acls` |
| 3 | Overlay | `overlay/` über den Baum, danach `chown 0:0` auf jede eingespielte Datei |
| 4 | Nacharbeit | machine-id, Host-Schlüssel, Root-Passwort, Unit-Symlinks, `/data`, apt-Listen (§3) |
| 5 | Projektteile | `install-projekt.sh` (§4) |
| 6 | Abnahme, tar, ext4 | 22 Prüfungen, `hy310-rootfs.tar`, optional `hy310-rootfs.ext4`, Manifest, SHA-256 |

`--dry-run` zeigt alle sechs Schritte, den vollständigen `mmdebstrap`-Aufruf, die Overlay-Dateiliste und den Trockenlauf des
Projektteils - **ohne Netz, ohne `mmdebstrap`, ohne einen einzigen Schreibzugriff**.

## 2. Entscheidungen

### 2.1 Was aus cstengers Skript *nicht* übernommen wurde - und warum

`mainline/tools/rootfs/build.sh` ist als Vorbild gelesen worden; übernommen sind die *Techniken* (mmdebstrap mit Keyring,
`--aptopt=Acquire::Languages "none"`, `mke2fs -d` statt Loop-Mount, Abnahmeprüfungen gegen die tatsächlich gelinkten Dateien,
Manifest + Prüfsummen). Nicht übernommen sind drei Entscheidungen:

| dort | hier | Begründung |
|---|---|---|
| `VIDEO_RUNTIME_PACKAGES` fest im Grundsatz („this is a projector") | draußen | 107 §1: das ist der größte Einzelposten des heutigen Netboot-Roots (`libllvm19` 118 MiB, `mesa-libgallium` 33 MiB, `libgtk-3-common` 30 MiB, dazu GStreamer/ONNX/ffmpeg). `hy310-tv` ist gegen **drei** Bibliotheken gelinkt - `libdrm.so.2`, `libasound.so.2`, `libc.so.6` - , es decodiert nichts. |
| `--profile dev` mit `build-essential` und Headern | draußen | 107 §3: gebaut wird quer (`userspace/hy310-tv/Makefile`, Ziel `install-cross`), das Gerät compiliert nichts |
| `--ssh-key FILE` ist **Pflicht**, Schlüssel wird eingebaut, `PasswordAuthentication no` | **kein** Schlüssel im Abbild | 107 §3: für ein Release muss der Schlüssel vom Nutzer kommen. `--authorized-key` gibt es hier nur als Wahl für eigene Bauten, und das Skript warnt dann laut. |
| aic8800-Module + Firmware fest eingebaut | draußen | 107 §3: WLAN/BT ungeprüft, die aic8800-Firmware hat keine Lizenzangabe (S42) |

### 2.2 Der Weg herein, wenn kein Schlüssel im Abbild liegt

Das ist die Kette, die aus „kein eingebauter Schlüssel" folgt, und sie muss zusammenpassen, sonst ist das Abbild zu:

- **Root-Passwort gesperrt** (`root:*:` in `/etc/shadow`, vom Skript erzwungen und geprüft). Kein Vorgabepasswort, das in einer
  Anleitung stehen und für immer dort bleiben würde.
- **Autologin auf `ttyS0`**, wörtlich wie heute im Netboot-Root
  (`/srv/h713-rootfs/etc/systemd/system/serial-getty@ttyS0.service.d/autologin.conf`:
  `ExecStart=-/sbin/agetty --autologin root --noclear %I $TERM`). `agetty --autologin` ruft `login -f` und fragt kein Passwort -
  das gesperrte Passwort steht dem also **nicht** im Weg.
- **`sshd` mit `PermitRootLogin prohibit-password`**, `PasswordAuthentication no`. Erreichbar, aber bis der Installer einen
  Schlüssel legt, nicht benutzbar. Das ist Absicht.
- **Host-Schlüssel werden gelöscht.** Das Postinst von `openssh-server` erzeugt sie *im Chroot*, also beim Bau - ohne diesen
  Schritt trügen alle aus demselben Abbild bespielten Geräte dieselben Host-Schlüssel. `hy310-ssh-host-keys.service`
  (`ssh-keygen -A`, `Before=ssh.service`) legt sie beim ersten Start an; Vorbild ist `h713-ssh-host-keys.service` aus dem
  Netboot-Root.

### 2.3 zram: eigene Unit statt `zram-tools`

107 §6 ließ die Wahl. Genommen: **eigene Unit** (`hy310-zram-swap.service` + `/usr/local/sbin/hy310-zram-swap`, 2,3 KiB).
`zram-tools` brächte ein init-Skript, eine Konfigurationsdatei und eine Abhängigkeitskette mit, um drei Werte zu setzen - und die
drei Werte stehen hier im Klartext: `zstd`, halber RAM (`MemTotal/2`), Priorität 100. `vm.swappiness=180` und `vm.page-cluster=0`
liegen getrennt in `/etc/sysctl.d/99-hy310-zram.conf`: ein Wert, ein Ort.

**Der Kernel kann das heute noch nicht** (107 §4.2: im Defconfig fehlen `CONFIG_ZRAM`, `CONFIG_ZSMALLOC`,
`CONFIG_ZRAM_BACKEND_ZSTD`, `CONFIG_ZRAM_DEF_COMP_ZSTD`). Die Unit ist deshalb so gebaut, dass sie **nicht scheitert**:
`ConditionPathExists=/sys/class/zram-control` lässt sie gar nicht erst anlaufen, und wenn `modprobe zram` fehlschlägt, meldet das
Skript das und endet mit 0. Ein Gerät soll wegen eines fehlenden Kernel-Schalters nicht „degraded" hochkommen.

### 2.4 `/etc/fstab`: zwei Zeilen, PARTLABEL, `growfs`

```
PARTLABEL=hy310-rootfs  /      ext4  defaults,noatime,x-systemd.growfs        0  1
PARTLABEL=hy310-boot    /boot  ext4  defaults,noatime,nofail,x-systemd.device-timeout=10s  0  2
```

- **PARTLABEL statt `/dev/mmcblk0pN`:** die Nummer hängt daran, wie viele Partitionen die GPT gerade führt (das heutige
  Netboot-Root trägt noch `/dev/mmcblk0p26`), das Etikett nicht. Der Kernel kann es auch für die Wurzel - S41 §1 belegt
  `block/early-lookup.c:248`, `strncmp(name, "PARTLABEL=", 10)`.
- **Keine dritte Zeile:** `/data` ist seit Layout v3 ein **Verzeichnis im Rootfs**, `hy310-data` ist ersatzlos entfallen
  (109 §2.2). Das Skript legt `/data` an; eine Abnahmeprüfung zählt die `PARTLABEL=`-Zeilen und besteht nur bei genau zwei.
- **`nofail` auf `/boot`:** ein per NFS gestartetes Gerät oder eines mit leerer Bootpartition soll trotzdem hochkommen und nicht
  in die Notfall-Shell fallen. Das ist der Preis dafür, dass derselbe Baum beide Ziele bedient (109 §4.2).
- **`x-systemd.growfs`:** das ext4-Abbild wird klein gebaut (Vorgabe 1 GiB) und wächst beim ersten Start auf die 7,15 GiB der
  Partition. Ein 7,15-GiB-Abbild zu bauen und zu übertragen wäre reine Verschwendung.

### 2.5 `/etc/fw_env.config` auf Layout v3

```
/dev/mmcblk0	0x500000	0x10000
```

LBA 10240 × 512 = `0x500000`, 128 Sektoren = 64 KiB (109 §2.1). Der Wert des Netboot-Roots (`0x93d80000`) ist damit überholt -
und war der Auslöser des `int`-Fehlers aus `doku/30` §16, den 109 §2.1 als willkommene Nebenwirkung des neuen Orts nennt: bei
5 MiB kann er gar nicht mehr auftreten.

### 2.6 apt benutzbar, Listen draußen

107 §8 wörtlich umgesetzt: `debian.sources` (deb822) mit `Signed-By: /usr/share/keyrings/debian-archive-keyring.gpg`,
`ca-certificates` und `debian-archive-keyring` in der Paketliste - aber **kein `apt update` beim Bau**. Das Skript räumt
`/var/lib/apt/lists` und `/var/cache/apt/archives` und prüft in der Abnahme, dass dort nichts liegt und nirgends `trusted=yes`
steht. Kosten laut Plan: rund 10 MiB. Ersparnis: rund 40 MiB Listen, die am ersten Tag veraltet wären.

Dazu gehört `systemd-timesyncd` (107 §8): ohne gepufferte RTC startet das System 1970, und dann scheitert genau dieser
`apt update` an der Signaturprüfung. Ohne Netz bleibt es beim Startwert - dann weiterhin `date -u -s`.

### 2.7 Journal flüchtig, und ein Fallstrick dazu

`/etc/systemd/journald.conf.d/10-hy310.conf`: `Storage=volatile`, `RuntimeMaxUse=32M` (107 §4.1). Der Grund ist nicht der Platz,
sondern die eMMC - sie hat unter paralleler Last Datenfehler gezeigt, danach hingen alle Leser im D-Zustand.

**Der Fallstrick, den das Skript ausdrücklich behandelt:** existiert `/var/log/journal` als Verzeichnis, schaltet `journald`
trotz `Storage=volatile` auf persistent um. Das Skript löscht es (`rm -rf`) und prüft in der Abnahme, dass es nicht da ist.

`hy310-logs persistent|volatile|status` liegt unter `/usr/local/sbin/`. `persistent` legt `/data/log` an, kopiert die
vorhandenen Logs hinüber (`cp -a -n`, damit der Bind-Mount sie nicht verdeckt), schreibt eine `var-log.mount`-Unit
(`What=/data/log`, `Type=none`, `Options=bind`) und setzt `Storage=persistent` mit `SystemMaxUse=128M`. `volatile` nimmt alles
zurück und lässt `/data/log` liegen, statt es stillschweigend zu löschen. Beide sagen „jetzt: reboot" - journald liest seine
Konfiguration beim Start, und ein Bind-Mount unter einem laufenden journald ließe offene Dateien ins Leere zeigen.

### 2.8 `/etc/hy310/tvconfig` bleibt leer - und wird geprüft

107 §8 trennt die beiden Bedeutungen: `tvconfig` ist **nur** das Verzeichnis mit den extrahierten PQ-Dateien, die
Dienstkonfiguration bekommt `/etc/hy310/tv.conf`. Im Abbild ist `tvconfig` leer; ohne Extraktion fällt `hy310-tv` auf seine
eingebauten Vorgaben zurück. Das Verzeichnis liegt im Overlay **und** wird vom Skript noch einmal ausdrücklich angelegt - ein
leeres Verzeichnis überlebt kein `git`. Eine Abnahmeprüfung besteht nur, wenn es leer ist.

## 3. Nacharbeit am Baum (Schritt 4)

| Handgriff | warum |
|---|---|
| `/etc/machine-id` leeren | sonst hätten alle Geräte dieselbe ID |
| `/etc/ssh/ssh_host_*` löschen | sonst dieselben Host-Schlüssel auf jedem Gerät (§2.2) |
| `root:*:` erzwingen und prüfen | kein Vorgabepasswort (§2.2) |
| Unit-Symlinks von Hand | ohne laufendes systemd im Chroot gibt es kein `systemctl enable`: `getty.target.wants/serial-getty@ttyS0.service`, `swap.target.wants/hy310-zram-swap.service`, `ssh.service.wants/hy310-ssh-host-keys.service` |
| `/etc/resolv.conf` als echte Datei | kein `systemd-resolved` im Abbild; `isc-dhcp-client` schreibt selbst hinein - so läuft es heute (S41 §1) |
| `/var/lib/apt/lists`, `/var/cache/apt` räumen | 107 §8 (§2.6) |
| `/var/log/journal` löschen | §2.7 |
| `/data`, `/boot`, `/etc/hy310/tvconfig` anlegen | 109 §2.2, §2.8 |

`hy310-tv@.service` wird bewusst **nicht** enabled: die Unit hat keinen `[Install]`-Abschnitt, weil der Probe von
`sun50i-h713-hdmirx` asynchron läuft und allein für die EDID/HPD-Sequenz über zehn Sekunden anhält. Gestartet wird sie von
`99-hy310-tv.rules` über `ENV{SYSTEMD_WANTS}+="hy310-tv@%k.service"`. Das steht so im Kopf der Unit und wird hier nicht
umgebogen.

## 4. Projektteile und die Blob-Sperre

| Teil | Quelle | Ziel |
|---|---|---|
| `hy310-tv` (quer gebaut) | `userspace/hy310-tv/hy310-tv.aarch64-linux-gnu` (197 KiB) | `/usr/local/sbin/hy310-tv`, 0755 |
| Unit | `userspace/hy310-tv/hy310-tv@.service` | `/etc/systemd/system/` |
| udev-Regel | `userspace/hy310-tv/99-hy310-tv.rules` | `/etc/udev/rules.d/` |
| Gamma-Vorgabe | `gamma-standard.bin` (2 KiB) | `/usr/local/share/hy310-tv/` |
| Kernelmodule | `mainline/build/modroot.GUT-bad2f16b/lib/modules/6.18.38` - **28 Module, 2,4 MiB** | `/lib/modules/6.18.38`, danach `depmod -b` |
| `hy310-pq` | `userspace/hy310-pq/{hy310-pq,hy310_pq/}` | `/usr/local/lib/hy310-pq/`, Symlink `/usr/local/bin/hy310-pq` |

Zielpfade und Rechte sind die des Makefile-Ziels `install-cross` (`SBINDIR=$(PREFIX)/sbin`, `UNITDIR=/etc/systemd/system`,
`UDEVDIR=/etc/udev/rules.d`, `DATADIR=$(PREFIX)/share/hy310-tv`); aufgerufen wird `make` aber **nicht** - im Container gibt es
weder `pkg-config` noch einen arm64-Sysroot, und `install-cross` würde `hy310-tv.$(TARGET)` neu bauen wollen. Kopiert wird das
fertige Binärprogramm, dessen Architektur mit `file(1)` geprüft wird; fehlt es, nennt das Skript den Bauweg
(`make -C userspace/hy310-tv cross`).

**Zwei Fallen bei den Modulen, beide behandelt:**

1. `lib/modules/6.18.38/build` ist ein Symlink nach `/work/mainline/build/linux-6.18.38-bad2f16b…` - im Abbild ein toter
   Verweis, und der Weg, über den versehentlich ein halber Kernelbaum mitwandert. Er wird beim Kopieren ausgeschlossen und
   danach noch einmal gelöscht.
2. `modules.dep` aus dem Bau nennt Pfade des Bauorts. `depmod -b "$TREE" 6.18.38` rechnet sie neu.

**Die Blob-Sperre** (107 §5) ist keine Zeile im Plan, sondern eine Prüfung, die den Lauf abbricht. Sie sucht im fertigen Baum
nach:

| Name | was es ist |
|---|---|
| **`hy310-hdcp22.bin`** | **HDCP-2.2-Schlüsselmaterial. Liegt heute in `/srv/h713-rootfs/lib/firmware/` (912 B) und darf das Abbild nie erreichen.** |
| `hdcp_v22.bin` | dasselbe unter dem Vendor-Namen (960 B, ebenfalls im Netboot-Root) |
| `h713-arisc.bin` | ARISC-Firmware, Vendor (108 §2) → Installer |
| `hy310-edid.bin`, `hy310-edid-nodc.bin` | aus dem Stock ausgelesen → Installer |
| `msp-patch.bin` | MSP-DSP-Patch, Vendor → Installer |
| `fmacfw*`, `fmacfwbt*` | aic8800 WLAN/BT - draußen (107 §3, S42: keine Lizenzangabe) |

dazu die Verzeichnisse `lib/firmware/h713`, `lib/firmware/aic8800_fw`, `usr/lib/firmware/h713`, und die Bedingung, dass
`/etc/hy310/tvconfig` leer ist. Findet sie etwas, endet der Lauf mit Fehler - es entsteht kein Abbild. Zusätzlich zählt sie die
Dateien in `/lib/firmware` und listet sie auf, falls dort überhaupt etwas liegt.

Der Grund für den Aufwand: genau diese Dateien liegen im Arbeitsbaum und im Netboot-Root herum, ein versehentliches
Mitkopieren ist der wahrscheinlichste Fehler dieses Bauwegs.

## 5. Was das Skript voraussetzt

| Voraussetzung | Prüfung im Skript | Zustand 10.09.2026 |
|---|---|---|
| Container `h713-build`, Projekt als `/work` | - (das Skript findet seinen Projektbaum über den eigenen Pfad) | vorhanden, ein Mount: `/opt/Projekte/h713 → /work` |
| `mmdebstrap` | `check_tools`, nennt den `apt`-Befehl | **fehlte**, nachinstalliert (§6) |
| `debian-archive-keyring` | `find_keyring` über drei Kandidatenpfade; ohne Keyring **Abbruch**, kein unsignierter Notweg | fehlte, nachinstalliert |
| `qemu-user-static` **oder** `binfmt_misc` des Hosts | `check_tools` akzeptiert beides | Host hat `qemu-aarch64` mit Flag `F` registriert (Interpreter im Kernel geladen, Pfad im Container egal) |
| `tar`, `mke2fs`, `e2fsck`, `depmod`, `install`, `sha256sum`, `du`, `find` | `check_tools` | alle da |
| Netz | - | nur für Schritt 1 |
| quer gebautes `hy310-tv` | `quellen_pruefen` + `file(1)` | `userspace/hy310-tv/hy310-tv.aarch64-linux-gnu`, 08.09. |
| Modulbaum | `quellen_pruefen` | `modroot.GUT-bad2f16b`, 28 Module |

**Der `apt`-Befehl, der ins Rezept in `doku/50-befehle.md` gehört** (diese Datei wurde auftragsgemäß *nicht* angefasst):

```bash
podman exec -u root h713-build apt-get update
podman exec -u root h713-build env DEBIAN_FRONTEND=noninteractive \
    apt-get install -y mmdebstrap debian-archive-keyring qemu-user-static
```

`mmdebstrap` zieht `fakeroot`, `fakechroot`, `arch-test` und `gpg` mit. `debian-archive-keyring` liefert
`/usr/share/keyrings/debian-archive-keyring.gpg` - ohne das kann `mmdebstrap` die Debian-Signaturen nicht prüfen.
`qemu-user-static` braucht es für die Wartungsskripte der arm64-Pakete, sofern man sich nicht auf das `binfmt_misc` des Hosts
verlässt. Das Skript nennt genau diesen Befehl, wenn etwas fehlt.

<!-- ABSCHNITT 6 UND 7 FOLGEN -->
