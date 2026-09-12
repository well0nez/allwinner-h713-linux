# Plan 107 — das Rootfs für v0.1

**Status: Plan, 10.09.2026.** Gehört zu [`105`](105-plan-release.md) R1. Marcos Vorgabe vom 09.09.: das Netboot-Root ist als
Basissystem zu groß, für v0.1 ein schlankes Rootfs bauen, Bauskript ins Repo. Entscheidungen aus dem Gespräch vom 10.09. sind in §3
und §6 eingearbeitet. Das Layout, in das dieses Rootfs geschrieben wird, steht in [`109`](109-plan-layout-v3.md) — dort ist `hy310-rootfs` **7,15 GiB**
groß und es gibt keine getrennte Datenpartition mehr. Die Vorarbeit aus [`108`](108-plan-vendordaten.md) ist am Gerät bewiesen (§7).

## 1. Ausgangslage, gemessen

`/srv/h713-rootfs`, 10.09.2026, `du -sx`:

| Anteil | Größe |
|---|---|
| **gesamt** | **2.938 MiB** |
| Journal (`/var/log/journal`) | 840 MiB |
| Mitschnitte in `/root` (`*.nv16m`, Testmuster) | 469 MiB |
| apt-Cache (`/var/cache/apt`) | 153 MiB |
| 555 Pakete der Priorität *optional* | 1.094 MiB |
| Basis (*required*, *important*, *standard*, 59 Pakete) | 133 MiB |
| Kernelmodule (5 Bäume) + `/lib/firmware` | 20 MiB |

614 Pakete. Die größten: `libllvm19` 118 MiB, `gcc-14-aarch64-linux-gnu` 60 MiB, `libicu76` 37 MiB, `mesa-libgallium` 33 MiB,
`libgtk-3-common` 30 MiB, dazu GStreamer, ONNX, ffmpeg. Das ist cstengers Video-Runtime plus Entwicklerwerkzeug aus
`mainline/tools/rootfs/build.sh` (`VIDEO_RUNTIME_PACKAGES`, `DEV_PACKAGES`) — für den Beamer ohne Funktion.

**Zwei Drittel sind Ballast, ein Drittel ist fremder Zweck.** Das eigentliche Betriebssystem ist klein.

## 2. Was der Beamer wirklich braucht (aus dem Code, nicht geschätzt)

- **`h713-tv`** ist gegen genau drei Bibliotheken gelinkt: `libdrm.so.2`, `libasound.so.2`, `libc.so.6` (`readelf -d`).
  Dazu die Unit `h713-tv@.service`, die udev-Regel `99-h713-tv.rules`, `/usr/local/share/h713-tv/gamma-standard.bin` und
  optional `/etc/hy310/tvconfig`.
- **Kernelmodule** des GUT-Standes (3 MiB) und die Firmware aus [`108`](108-plan-vendordaten.md) §2 (2 MiB), die **nicht** im Abbild
  liegt, sondern der Installer aus `h713-extract` einspielt.
- **System:** systemd, udev, DHCP über `ifupdown` + `isc-dhcp-client` (das läuft heute so und überlebt den Umzug, S41 §1),
  `openssh-server`, `kmod`, `e2fsprogs`, `alsa-utils`.

**Gemessen am 10.09. (Bau gelaufen, [`S43`](nachtlog/S43-rootfs-bau.md)): 228 MiB** — 154 Pakete, 17 über `minbase` hinaus.
Das Netboot-Root ist 2.938 MiB groß, das Release-Rootfs also **knapp dreizehnmal kleiner**; das Ziel „unter 1 GB" ist weit
unterschritten. Ausgabe: `hy310-rootfs.tar` (223 MB) und ein ext4-Abbild von 1 GiB, das beim ersten Start auf die volle
Partition wächst.

## 3. Entscheidungen (Marco, 10.09.)

| Frage | Entscheidung |
|---|---|
| WLAN / Bluetooth | **draußen.** Beides ist auf dem aktuellen Kernel ungeprüft; die aic8800-Firmware hat obendrein keine Lizenzangabe (S42). Kein `wpasupplicant`, kein `bluez`, kein `hostapd`, kein `dnsmasq`. In der Matrix als „nicht enthalten, ungetestet". |
| Zweites Profil `dev` | **nein.** Gebaut wird hier per Cross-Compile (`userspace/h713-tv/Makefile`, Ziel `install-cross`), das Gerät compiliert nichts. Kein `build-essential`, keine `-dev`-Pakete im Abbild. |
| Zugang | **Autologin bleibt** wie heute auf der seriellen Konsole. `openssh-server` ist dabei; der Installer übernimmt einen Schlüssel, wenn einer angegeben wird. **Kein fest eingebauter Schlüssel im Abbild** — cstengers Skript verlangt `--ssh-key` und schaltet `PasswordAuthentication no`; für ein Release muss der Schlüssel vom Nutzer kommen. |
| Logs / Schreiblast | §4 |
| Ort des Bauskripts | egal, wird `installer/rootfs/` |

## 4. Logs, Schreiblast und zram

**Das Problem ist nicht der Platz, sondern die eMMC.** Sie hat unter paralleler Last Datenfehler gezeigt (HS400, 200 MHz;
`105` Verlauf 10.09. 22:40), danach hingen alle Leser im D-Zustand. Jedes vermiedene Schreiben ist gewonnen. 840 MiB Journal in
einem Netboot-Root über drei Wochen sind ein Vorgeschmack darauf, was ein Dauerbetrieb auf die eMMC schreiben würde.

**Armbians Weg** (zram-Blockgerät, ext4 darauf, `/var/log` dorthin, beim Herunterfahren nach `/var/log.hdd` sichern) löst das,
ist aber eine Konstruktion aus drei beweglichen Teilen. Für uns reicht weniger, und es ist zugleich strenger:

1. **Journal flüchtig.** `/etc/systemd/journald.conf.d/10-hy310.conf`: `Storage=volatile`, `RuntimeMaxUse=32M`.
   Das Journal liegt dann in `/run/log/journal`, also tmpfs — die eMMC sieht davon **nichts**. Kein Sicherungsdienst nötig,
   kein zweiter Speicherort, nichts, was beim Herunterfahren schiefgehen kann.
2. **zram als Swap**, nicht für Logs. `zram0`, zstd, Größe = halber RAM, `vm.swappiness=180`, `page-cluster=0` (die Werte, mit denen
   zram-Swap heute allgemein gefahren wird). Fängt den tmpfs-Druck ab und macht das Gerät bei knappem Speicher träge statt tot.
   **Erledigt 10.09.:** die vier Optionen fehlten im Defconfig; zunächst als Fragment `zram.config` nachgereicht,
   Bau mit `KERNEL_CONFIG=netboot,zram`. Am Gerät gemessen: 461,8 MiB Swap mit zstd, `swappiness=180`, `page-cluster=0`.
   **Korrigiert 11.09.:** die vier Optionen stehen jetzt **im Board-defconfig**, das Fragment ist weg. Als Fragment
   fehlte zram in jedem Bau ohne `KERNEL_CONFIG` — also ausgerechnet im Auslieferungskernel, während das
   Release-Rootfs die zram-Unit mitbringt. Siehe [`60-offen`](60-offen.md) „Welcher Bau ist der Auslieferungskernel".
3. **Ein Schalter für die Fehlersuche.** `hy310-logs persistent|volatile` legt `Storage=persistent` und einen Bind-Mount von
   `/var/log` nach `/data/log` (p6) an. Wer einen Fehler sucht, schaltet um, startet neu, hat Logs über Neustarts hinweg — und
   schreibt dabei auf die Datenpartition, nicht auf das Wurzeldateisystem.
4. **`/data` als Verzeichnis im Rootfs** für alles Wachsende: Mitschnitte, Aufnahmen, optionale Logs. Eine eigene Partition dafür ist
   mit [`109`](109-plan-layout-v3.md) entfallen — das Rootfs hat 7,15 GiB, davon braucht das System unter 350 MiB.
   `/tmp` und `/var/tmp` sind tmpfs.

Damit ist das Wurzeldateisystem im Betrieb **fast nur-lesend**: es ändern sich Konfiguration und Paketstand, sonst nichts.

## 5. Bauweg

Im Container `h713-build` (Regel: kein Bau auf dem Host), `mmdebstrap --variant=minbase`, Debian **trixie/arm64** wie das
heutige Root (13.6). `mmdebstrap` fehlt im Container und kommt in das Rezept in [`50`](50-befehle.md) mit dazu.

```
installer/rootfs/
├── build-rootfs.sh      mmdebstrap + Overlay + tar/ext4, reproduzierbar, ohne Netz am Gerät
├── packages.txt         die Paketliste aus §7, eine Zeile je Paket mit Begründung
└── overlay/             fstab-Vorlage, journald-Konfiguration, zram-Unit, h713-tv-Unit + udev-Regel
```

Erzeugt wird ein **tar** (der Installer entpackt es nach p8) und ergänzend ein `ext4`-Abbild. `--one-file-system`-Kopie des
laufenden Roots bleibt als Notweg im Installer, ist aber nicht mehr der Normalfall.

**Nicht im Abbild:** die extrahierten Vendor-Dateien, `hy310-hdcp22.bin` (liegt heute im Netboot-Root und darf nicht mitkopiert
werden), Kernelmodul-Bäume außer dem des mitgelieferten Kernels.

## 6. Paketliste (Entwurf)

`minbase` plus:

| Paket | wofür |
|---|---|
| `systemd-sysv`, `udev`, `dbus` | Init, Geräteerkennung, h713-tv-Start über udev |
| `ifupdown`, `isc-dhcp-client`, `iproute2` | Netz wie heute (S41 §1: `allow-hotplug eth0 / inet dhcp`) |
| `openssh-server` | Fernzugang; Schlüssel kommt vom Installer |
| `e2fsprogs`, `kmod`, `util-linux-extra` | Dateisysteme, Module, `fstrim`/`lsblk` |
| `alsa-utils` | `amixer`, `aplay` für den Audioweg |
| `libdrm2`, `libasound2t64` | die zwei Bibliotheken von `h713-tv` |
| `python3` (ohne `-dev`) | `h713-pq` rechnet Gamma und Presets zur Laufzeit aus `/etc/hy310/tvconfig` ([`108`](108-plan-vendordaten.md) §6) |
| `zram-tools` **oder** eigene Unit | §4.2; eigene Unit wahrscheinlich kleiner |
| `ca-certificates` | nur wenn `apt` am Gerät gewollt ist; sonst weg |

**Nicht enthalten:** Compiler, Header, GStreamer, Mesa, GTK, ffmpeg, `wpasupplicant`, `bluez`, `hostapd`, `dnsmasq`, `busybox`.

## 7. Prüfungen vor der Abnahme

1. Größe unter 500 MiB, gezählt mit `du -sx` auf dem entpackten Baum.
2. Kaltstart vom eMMC bis Login ohne Host, 20 Mal (Paket R5).
3. `h713-tv@video1` startet über udev, Bild und Ton wie im Netboot-Root.
4. Schreiblast im Leerlauf: `/proc/diskstats` über eine Stunde, Ziel nahe null Sektoren auf p8.
5. zram aktiv (`zramctl`), Swap wird bei Speicherdruck benutzt, Journal liegt in `/run`.
6. Netz kommt per DHCP hoch, `ssh` erreichbar, Uhr wie bisher ohne RTC (`date -u -s` bleibt nötig).

## 8. Entschieden (10.09., damit nichts offen bleibt)

**`systemd-timesyncd` kommt mit.** Ohne gepufferte RTC startet das System 1970. Das ist keine Kleinigkeit: `apt` scheitert an der
Signaturprüfung, Logs sind unbrauchbar, Dateizeiten lügen, und jede TLS-Verbindung bricht ab. Das Paket wiegt rund 1 MiB und
stellt die Uhr, sobald Netz da ist. Ohne Netz bleibt es beim Startwert — dann hilft weiterhin nur `date -u -s`.

**`apt` bleibt benutzbar:** Debian-Quellen eingetragen, `ca-certificates` dabei, aber **kein `apt update` beim Bau** (das würde
Paketlisten von rund 40 MiB einbacken, die am ersten Tag veraltet sind). Ein Beamer, auf dem eine Entwickler-Vorschau nichts
nachinstallieren kann, wäre für die Zielgruppe wertlos; die Kosten sind rund 10 MiB.
**Die beiden Bedeutungen von `/etc/hy310/tvconfig` werden getrennt.** Der Pfad bezeichnet ab sofort **nur** das Verzeichnis mit den
extrahierten PQ-Dateien, aus denen `h713-pq` rechnet; im Abbild ist es leer, ohne Extraktion fällt `h713-tv` auf seine
eingebauten Vorgaben zurück. Die Dienstkonfiguration („Startmodus merken", [`60`](60-offen.md)) bekommt **`/etc/hy310/tv.conf`**.
Ein Pfad, der je nach Leser zwei verschiedene Dinge meint, ist eine Falle, die sich jetzt für null Aufwand vermeiden lässt.

## 9. Stand 10.09.: gebaut und abgenommen

`analyse/release/arbeit/rootfs/` — `build-rootfs.sh`, `install-projekt.sh`, `packages.txt`, `overlay/` (15 Dateien).
Der Bau läuft im Container `h713-build` (`mmdebstrap` nachinstalliert, gehört ins Rezept in [`50`](50-befehle.md)).

| | |
|---|---|
| Baumgröße | **233.852 KiB = 228 MiB** |
| Pakete | 154 (17 über `minbase`) |
| Ausgabe | `hy310-rootfs.tar` 223 MB, `hy310-rootfs.ext4` 1 GiB (wächst per `x-systemd.growfs`), Manifest, Prüfsummen |
| Bootstrap-Dauer | rund 9 min (Netz) |

**20 Abnahmeprüfungen im Skript, alle grün:** systemd als Init, Autologin auf `ttyS0`, Journal flüchtig und kein
`/var/log/journal`, zram-Unit verlinkt mit `swappiness=180`, `fstab` mit genau zwei PARTLABEL-Zeilen, `fw_env.config` auf
`0x500000`, Netz per ifupdown/DHCP, `hy310-logs` ausführbar, `/etc/hy310/tvconfig` leer, `/data` vorhanden, keine
SSH-Host-Schlüssel und keine apt-Listen im Abbild, signierte Paketquelle — und die Gegenproben: kein Compiler, kein
GStreamer, kein `wpa_supplicant`.

**Zwei Dinge waren beim ersten Lauf zu reparieren:** das Auspacken scheiterte im rootless Container an `mknod` für `/dev/*`
(ausgelassen — der Kernel mountet devtmpfs vor init, und das finale tar schließt `./dev/*` ohnehin aus), und die Abnahme
„kein trusted=yes" stolperte über den eigenen Kommentar in der Paketquelle (prüft jetzt nur Nicht-Kommentarzeilen).
