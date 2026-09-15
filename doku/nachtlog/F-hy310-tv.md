# Paket F - `hy310-tv` (offline: Entwurf + Gerüst)

**Agent:** Unteragent F (offline). **Kein Board angefasst:** kein `ssh root@192.168.8.141`, kein
`ssh user@192.168.8.162`, kein `sonoff_ctl`, kein `wandcheck.py`, kein `tio`, kein `scp`, nichts nach
`tftp/`. Kein `sudo`, kein `git commit`/`push`. **`patches/kernel/series` nicht angefasst**,
`build/build.sh` nicht aufgerufen, **kein Kernel-Patch** (F ist Userspace, nichts unter
`mainline/patches/`). `/srv/h713-rootfs` nur **gelesen**. Uhrzeiten vom Arbeitsrechner
(`date '+%H:%M'`), 06./07.09.2026.

## Ergebnisdateien

| Datei | sha256 |
|---|---|
| `userspace/hy310-tv/main.c` | `20f334224cd2c974d34bdcdca17ec124bc685646faf4e8d5f9f79daa7a0437b0` |
| `userspace/hy310-tv/Makefile` | `214eddf74262b5cff1ea6779bb99b36657d9981f4c4dd1f4c2bf556c6fec2792` |
| `userspace/hy310-tv/hy310-tv.service` | `8cebe4aa046f087c06ce45b525941f964ff9711a5a02e7e09cb843783fe7a8cc` |
| `userspace/hy310-tv/99-hy310-tv.rules` | `08ea07ce63de2df18508b4618a5f2f49dc483022cbf71f1e6d8205a9c2c92ea3` |
| `userspace/hy310-tv/README.md` | `526ddf9ff08bb419a711f6d82d9385d1ab8c11d1643ab57bee879325f5c01397` |

---

## 1. Ablauf

| Zeit | Schritt |
|---|---|
| 22:45 | Nachtplan 78 **vollständig** gelesen (§0, §0a, §0b, §3 „F", **Anhang A ab Z. 440**, A.3/A.4/A.5/A.6); `nachtlog/00-koordination.md` inkl. Nachtrag 22:57, `nachtlog/D-plane.md`, `nachtlog/E-v4l2.md`, `doku/88`, `doku/86` |
| 22:48 | `analyse/kms/hdmi_plane_test.c` + `README-hdmi-plane.md` (Paket D) als Vorlage gelesen; `legacy/userspace/hy310-hdmird/README.md` gelesen (Zustandsübergänge, **nicht portiert**) |
| 22:49 | Board-Root `/srv/h713-rootfs` inventarisiert (Werkzeuge, libdrm, systemd/udev-Regeln) - **Korrektur einer Auftragsannahme, siehe §3** |
| 22:50 | Patch **0093** gelesen (`atomic_check`-Bedingungen, Eigenschaften `hdmi-ring`/`saturation`), Patch **0094**-Quelle `analyse/hdmirx-drv/sun50i-h713-hdmirx.c` (Treibername, `QUERY_DV_TIMINGS`, `SOURCE_CHANGE`, kein `EXPBUF`) |
| 22:51 | Kernelquelle `drm_file.c`/`drm_ioctl.c` geprüft: `drm_client_dev_restore()` hängt am **letzten Schließen**, nicht am Master-Wechsel; von den benutzten ioctls verlangt nur `MODE_ATOMIC` `DRM_MASTER` |
| 22:52 | **Entscheidung C-Programm** (§2) |
| 22:53-22:57 | `main.c` geschrieben, Prüfbau, zwei Befunde behoben (fehlendes `crtc_index`; Commit-Fehlerpfad mit veraltetem `errno`), `fail()`/`usage()` als `_Noreturn` markiert |
| 22:57 | Prüfbau grün, `clang --analyze` ohne Befund (§4) |
| 22:58 | `Makefile`, `hy310-tv.service`, `99-hy310-tv.rules`; `systemd-analyze verify` und `udevadm verify` grün |
| 23:00 | `README.md` (deutsch) und dieses Teillog |

---

## 2. Die Entscheidung: C-Programm statt `gst-launch-1.0 v4l2src ! kmssink`

**Entschieden: C-Programm.** Der Nachtplan erlaubt beides (§3 „F"), also gehört die Begründung ins Log.

Sie stützt sich **nicht** auf „GStreamer fehlt auf dem Board" - dieser Satz aus meinem Auftrag stimmt
nicht (§3). Die Gründe sind inhaltlich:

1. **Eine GStreamer-Kette müsste jedes Bild kopieren.** 0094 gibt die drei Ring-Slots als
   `VB2_MEMORY_MMAP` mit eigenen `mem_ops` heraus und hat **kein `VIDIOC_EXPBUF`**
   (doku/88 §4 und §8 Punkt 2, ausdrücklich „nicht gebaut"). Ohne dma-buf importiert `kmssink` nichts,
   sondern kopiert in seinen eigenen Dumb-Puffer: 2 × 2 073 600 B je Bild, 60-mal je Sekunde, ≈ 250 MB/s
- für Daten, die die Plane sich selbst holt. Der Auftrag sagt ausdrücklich „kein Kopieren der Frames".
2. **Die Plane lässt sich so gar nicht fahren.** Der Ringbetrieb hängt an der treibereigenen
   Plane-Eigenschaft `hdmi-ring` (und optional `saturation`); `kmssink` kennt keine Treiber-Properties.
   Ohne `hdmi-ring` zeigte die Plane die **Kopie** statt des Rings - also der lange Weg zum selben Bild.
3. **Der Kern von F ist die Zustandsmaschine, nicht der Datenpfad.** Bei Signalverlust friert der Ring
   ein und die Wand zeigt den letzten Rahmen (K4, 21:50:56) - sie wird **nicht** schwarz. Eine Pipeline,
   die einfach stehenbleibt, erzeugt exakt das Fehlerbild, das F verhindern soll. Der Verlust muss aus
   `V4L2_EVENT_SOURCE_CHANGE` erkannt werden, und dann muss jemand die Plane abschalten.
4. **Sauberes Beenden** (Plane aus, Konsole zurück, DRM-Master abgeben, bevor der Prozess endet) ist mit
   `gst-launch` nicht zu haben - und genau das verlangt Auftragspunkt 3.
5. Nebenbei: eine Kette bräuchte die GStreamer-Registry (260 Plugins) auf einem NFS-Root; das Programm
   braucht `libdrm` und sonst nichts.

**Was die Entscheidung kostet:** ~560 Codezeilen (806 Zeilen Datei, davon 139 Kommentar, 107 leer) statt
einer Kommandozeile. Der Nachtplan nennt „~300 Zeilen"; der Mehraufwand steckt nicht in der Logik,
sondern in Gerätesuche über den **Treibernamen** (statt `/dev/video0` zu raten) und der
KMS-Eigenschaftsverwaltung - beides übernommen aus `analyse/kms/hdmi_plane_test.c`, damit D und F
dieselbe Sprache sprechen.

### Was das Programm tut

```
BEREITSCHAFT  --- SOURCE_CHANGE, Signal da ---> BILD
Plane aus, DRM-Master abgegeben                 Plane an (hdmi-ring=1), Master gehalten
(Konsole hat das Panel)     <--- SOURCE_CHANGE, kein Signal ---
```

* Gerätesuche über `VIDIOC_QUERYCAP.driver == "sun50i-h713-hdmirx"` bzw. `drmGetVersion()->name ==
  "sun50i-h713-afbd"`; keine geratenen Nummern (0094 probt asynchron, die Nummer steht nicht fest).
* Einmal `VIDIOC_S_INPUT(0)` als Zustandsansage (Stufe 5; Nullwechsel ist normal, deshalb nur eine
  Journalzeile, wenn er scheitert), einmal `VIDIOC_SUBSCRIBE_EVENT(SOURCE_CHANGE)`.
* Danach hängt der Prozess in `poll()` auf **zwei** Deskriptoren: dem Aufnahmegerät (`POLLPRI`) und
  einem `signalfd` für `SIGTERM`/`SIGINT`/`SIGHUP`. **Keine Zeitschleife, kein `sleep`, keine
  Wiederholung ohne Ursache.**
* Pro Ereignis: `VIDIOC_QUERY_DV_TIMINGS` (in 0094 eine 20-ms-Messung an den Flip-Zeigern, `-ENOLINK`
  wenn sie stehen) → Plane an oder aus.
* Plane an = ein Atomic-Commit mit `FB_ID/CRTC_ID/SRC_*/CRTC_*` + `hdmi-ring=1` (+ `saturation`, wenn
  `-s` angegeben). Der Dumb-Framebuffer trägt **nur** Format, Geometrie und Zeilenabstand; sein Inhalt
  wird im Ringbetrieb nie gelesen.
* Plane aus = Commit mit `FB_ID=0, CRTC_ID=0`; 0093 stellt dabei RGB-Kanal und Encoder-Selektor zurück.

### Zwei Entwurfsentscheidungen, die nicht offensichtlich sind

**DRM-Master nur, solange das Bild steht.** Solange ein Userspace-Master existiert, malt der
kerneleigene Konsolen-Client nicht mehr (`drm_master_internal_acquire`) - die Konsole wäre sichtbar,
aber eingefroren. Deshalb gibt das Programm den Master in der Bereitschaft zurück und holt ihn beim
Einschalten. Nachgesehen statt geglaubt: `drm_client_dev_restore()` wird in 6.18.38 **nur** aus
`drm_lastclose()` gerufen (`drivers/gpu/drm/drm_file.c:408`), hängt also am letzten Schließen und nicht
am Master-Wechsel; nötig ist er nicht, weil 0093 die Hardware beim Disable selbst zurückstellt. Von den
benutzten ioctls verlangt nur `DRM_IOCTL_MODE_ATOMIC` `DRM_MASTER` (`drm_ioctl.c:695`) -
`CREATE_DUMB`/`ADDFB2` nicht.

**Eine Rückschau nach dem Einschalten, keine Reparatur.** Der erste Plane-Enable veröffentlicht den
VidDec-Descriptor, und der schaltet die Capture ab (A.5, Korrektur 22:35). Das Programm fragt deshalb
nach dem Einschalten die Signalerkennung **einmal** erneut und schreibt bei stehendem Ring eine
Warnung mit Ursache und Verweis ins Journal. Es behebt nichts: beide belegten Wege zurück
(Quellenwechsel, `B2-quellenwechsel.md`; HPD-Zyklus 0,3 s, `M4-hpd-dauer.md`) sind Firmware-Aufrufe
hinter den Treibern, und über V4L2 ist heute keiner davon auslösbar (0094 hat einen Eingang,
`S_INPUT(0)` ist ein Nullwechsel). Siehe §6 „Anfragen".

---

## 3. Korrektur einer Annahme aus dem Auftrag (und aus `E-v4l2.md`)

Mein Auftrag sagte, `v4l2-ctl`, `modetest` „und vermutlich auch GStreamer" seien auf dem Board-Rootfs
nicht installiert; `nachtlog/E-v4l2.md` §6 schreibt „auf dem Board sind beide Werkzeuge nicht
installiert". Nachgesehen im exportierten NFS-Root (`/etc/exports`: `/srv/h713-rootfs
192.168.8.0/24(rw,…)`, also **das** Board-Root, nur gelesen):

| Werkzeug | Stand | Beleg |
|---|---|---|
| `v4l2-ctl`, `v4l2-compliance` | **vorhanden** | `/srv/h713-rootfs/usr/bin/v4l2-ctl` (aarch64), dpkg-Paket `v4l-utils` |
| `gst-launch-1.0` + 260 Plugins, darunter `libgstvideo4linux2.so` und **`libgstkms.so`** | **vorhanden** | `usr/bin/gst-launch-1.0`, `gstreamer1.0-tools`, `-plugins-good`, `-plugins-bad` |
| `modetest` | **fehlt** | kein `libdrm-tests`; deckt sich mit `A-abnahme-board.md` Punkt 3 |
| `gcc-14`, `pkg-config`, libdrm-Header + `libdrm.so.2` | vorhanden | Grundlage des nativen Baus |

Für Paket E heißt das: die Abnahme kann `v4l2-ctl --query-dv-timings`, `--all` und
`--stream-mmap` benutzen; die debugfs-Statusseite bleibt trotzdem der bessere Beleg, weil sie Zähler
und Rohwörter zeigt. Für F ändert es an der Entscheidung nichts (§2) - nur an ihrer Begründung.

---

## 4. Prüfbau - **ausdrücklich ein Prüfbau, kein Serienartefakt**

Querbau auf dem Arbeitsrechner gegen das Board-Root als Sysroot, genau der Weg, den Paket D für
`hdmi_plane_test.c` beschreibt (`analyse/kms/README-hdmi-plane.md`):

```bash
make -C userspace/hy310-tv cross
# clang --target=aarch64-linux-gnu --sysroot=/srv/h713-rootfs -fuse-ld=lld \
#     -O2 -g -Wall -Wextra -Wshadow -Wvla -isystem /srv/h713-rootfs/usr/include/libdrm \
#     -L/srv/h713-rootfs/usr/lib/aarch64-linux-gnu -o hy310-tv.aarch64-linux-gnu main.c -ldrm
```

| Prüfung | Ergebnis |
|---|---|
| Querbau, `-Wall -Wextra -Wshadow -Wvla`, clang 18.1.3 | **grün, keine Warnung**; `ELF 64-bit LSB pie executable, ARM aarch64`, dynamisch gegen `libdrm.so.2` |
| `clang --analyze` (core, unix, deadcode) | **kein Befund** (der eine Fund - `props_get()`, wenn `calloc` scheitert - war echt und ist behoben, indem `fail()`/`usage()` jetzt `_Noreturn` sind) |
| `systemd-analyze verify hy310-tv.service` | grün (einziger Hinweis: `/usr/local/sbin/hy310-tv` existiert auf **diesem** Rechner nicht - erwartet) |
| `udevadm verify 99-hy310-tv.rules` | `Success: 1, Fail: 0` |
| `make clean` | Baum bleibt sauber, kein Binärartefakt im Repo |

**Warum der Prüfbau nicht im Container `h713-build` läuft** (der Auftrag nannte den Container): der
Container sieht `/srv` nicht - er hat genau einen Mount, `/opt/Projekte/h713 → /work` (mit
`podman inspect` geprüft) - und hat weder libdrm noch einen arm64-Sysroot (`/usr/include/xf86drm.h`
fehlt, kein `libdrm`-Paket, kein `/usr/aarch64-linux-gnu`). Ihn dafür zu erweitern hieße, `apt` in einer
laufenden Welt zu benutzen oder Board-Root-Dateien ins Repo zu kopieren - beides ist ausgeschlossen.
Regel 2 des Nachtplans gilt dem **Kernel** („nur über `build/build.sh`"); für das Userspace-Werkzeug ist
der Host-Clang der von Paket D bereits beschriebene Weg. **Nicht improvisiert, sondern benannt.**

**Nicht geprüft, weil offline nicht prüfbar:** ein Lauf. Das Programm braucht `/dev/dri/cardN` mit 0093
und `/dev/videoN` mit 0094; beides gibt es nur am Board. Auch ein `qemu-aarch64-static`-Anlauf für die
Argumentbehandlung scheidet aus: qemu-user liegt im Container, und der sieht den Sysroot nicht, gegen
den das Binärprogramm dynamisch gebunden ist.

---

## 5. Angenommene Schnittstellen aus D und E - und wo sie abweichen könnten

Gegen die **Patches** geprüft, nicht gegen Prosa (§0a: „was am Gerät wirkt, steht in der Patch-Serie").

### Aus Paket D (`0093-drm-h713-afbd-nv16-hdmi-ring.patch`)

| Angenommen | Beleg im Patch | Bruchstelle |
|---|---|---|
| DRM-Treibername `sun50i-h713-afbd` | bestehender Treiber, `A-abnahme-board.md` Punkt 2 | ändert sich nur, wenn der Treiber umbenannt wird |
| Overlay-Plane `video-0` (auf unserem Board **ID 38**), Typ Overlay, `DRM_FORMAT_NV16` in der Formatliste | `+DRM_FORMAT_NV16` in der Formattabelle; `A-abnahme-board.md` Punkt 3 (`plane[38]: video-0`) | die ID wird **nicht** verdrahtet: gesucht wird nach Typ + NV16 + `hdmi-ring` |
| Plane-Eigenschaft **`hdmi-ring`** (0..1) und **`saturation`** (0..255) | `drm_property_create_range(…, "hdmi-ring", 0, 1)` / `("saturation", 0, 255)` | fehlt `hdmi-ring`, bricht das Programm mit klarer Meldung ab („laeuft der Kernel mit Patch 0093?") |
| `atomic_check`: FB-Geometrie = Modus, linear, `pitches[1] == pitches[0]`, Breite durch 16, Höhe gerade, `SRC_*` = Modus ≪ 16, `CRTC_*` = Modus | Hunk `h713_afbd_video_atomic_check` | das Programm erfüllt alle sechs Bedingungen; `EINVAL` wird im Journal genau so gedeutet |
| `hdmi-ring` verlangt **keine** gültigen FB-Adressen, aber einen FB (Format/Geometrie) | `if (…hdmi_ring) { if (!h->ring_size) return -EOPNOTSUPP; return 0; }` | `EOPNOTSUPP` = `memory-region-names` fehlt am Display-Knoten; steht als Deutung im Journal |
| Disable stellt RGB-Kanal und Selektor zurück, **Info-Slots bleiben** | doku/86 §6 und der Kommentar im Disable-Hunk | wenn D das ändert, muss F die Konsolenrückgabe neu bewerten |

### Aus Paket E (`0094-media-sun50i-h713-hdmirx.patch`, Quelle `analyse/hdmirx-drv/`)

| Angenommen | Beleg | Bruchstelle |
|---|---|---|
| `VIDIOC_QUERYCAP.driver == "sun50i-h713-hdmirx"` | `strscpy(cap->driver, H713_HDMIRX_NAME, …)` | Namensänderung bricht die Suche (Meldung nennt den erwarteten Namen) |
| `QUERY_DV_TIMINGS` = Signalmessung, **`-ENOLINK`** ohne Signal | `if (!h713_hdmirx_signal_present(rx)) return -ENOLINK;` | F akzeptiert zusätzlich `ENOLCK`/`ENODATA` als „kein Signal"; jeder **andere** Fehler wird als Gerätefehler behandelt (Plane aus) |
| `SUBSCRIBE_EVENT(SOURCE_CHANGE)` wird angenommen, Ereignis kommt aus dem `SignalChange`-Callback | `v4l2_src_change_event_subscribe()`, `h713_hdmirx_src_change()` | ohne Ereignisse gäbe es nur Pollen - das Programm scheitert dann bewusst beim Start |
| `S_INPUT(0)` = `SetSource(3)`, Nullwechsel ist normal | `h713_hdmirx_set_source()` | Ablehnung ist eine Journalzeile, kein Abbruch |
| **kein `VIDIOC_EXPBUF`** → kein dma-buf-Pfad | doku/88 §4/§8 Punkt 2 | sobald es ihn gibt, kommt die zweite Betriebsart dazu (§6) |
| `V4L2_CAP_VIDEO_CAPTURE_MPLANE`, `NV16M`, 3 Puffer | `vdev.device_caps`, `h713_hdmirx_fill_fmt()` | für F ohne Belang: es streamt nicht (siehe unten) |

**Bewusst nicht getan: `REQBUFS`/`STREAMON`/`DQBUF`.** Anhang A.4 zeichnet „pro Frame: DQBUF →
Plane-Flip"; das setzt den dma-buf-Export voraus. Ohne ihn wäre jedes dequeuete Bild entweder ungenutzt
(Arbeit ohne Zweck, dazu der 120-Hz-Abtasttakt in 0094) oder müsste kopiert werden. Die Plane folgt dem
Ring heute selbst, phasenrichtig im Vsync - das ist der bessere Weg, solange er da ist, und er ändert
an der Zustandsmaschine nichts. **Sobald 0094 `EXPBUF` hat, kommt der Streaming-Pfad als zweite
Betriebsart in `display_show()` dazu.**

---

## 6. Anfragen (keine Board-Zeit nötig)

1. **An D (0093) - die Capture-Freigabe gehört dorthin, wo die Ursache sitzt.** Der Plane-Enable
   veröffentlicht den Descriptor und schaltet damit die Capture ab. Nach `B2-quellenwechsel.md` genügt
   ein Quellenwechsel (`SetSource` weg und zurück, 22:53 gemessen, null strukturelle
   Registerunterschiede), nach `M4-hpd-dauer.md` ein 0,3-s-HPD-Zyklus. Beides sind Stock-RPCs. Solange
   das keiner der Treiber tut, zeigt der erste Kaltstartlauf ein **Standbild**, und F kann nur warnen.
2. **An E (0094) - `VIDIOC_EXPBUF`.** Erst damit ist der `DQBUF`→Plane-Weg aus A.4 überhaupt baubar.
   Bis dahin ist `hdmi-ring` der Datenpfad; das ist in D §7 Punkt 6 ohnehin als Übergang angelegt.
3. **An die Hauptsitzung:** `nachtlog/E-v4l2.md` §6 und `doku/88` behaupten, `v4l2-ctl` sei auf dem Board
   nicht installiert. Es ist installiert (§3). Bitte beim Zusammenführen richtigstellen.

---

## 7. Abnahmevorschrift (kopierbar, für die Hauptsitzung)

**Voraussetzungen:** 0091 (B), 0092 (C), 0093 (D) und 0094 (E) stehen in der `series`,
`build/build.sh kernel` ist grün, die Netboot-FIT liegt in `tftp/`, Module und Firmware-Dateien
(`hy310-edid.bin`, `hy310-hdcp22.bin`) sind auf dem Board. Sperre halten. **Echtes Stecken kann nur
Marco** - die Vorschrift benutzt ersatzweise den Zuspieler-Ausgang; der Unterschied ist in Schritt 4
benannt.

```bash
# --- 0. Programm bauen und installieren (Arbeitsrechner) ---------------------
make -C /opt/Projekte/h713/userspace/hy310-tv cross          # Pruefbau, muss gruen sein
install -D -m 0755 /opt/Projekte/h713/userspace/hy310-tv/hy310-tv.aarch64-linux-gnu \
        /srv/h713-rootfs/usr/local/sbin/hy310-tv
install -D -m 0644 /opt/Projekte/h713/userspace/hy310-tv/hy310-tv.service \
        /srv/h713-rootfs/etc/systemd/system/hy310-tv.service
install -D -m 0644 /opt/Projekte/h713/userspace/hy310-tv/99-hy310-tv.rules \
        /srv/h713-rootfs/etc/udev/rules.d/99-hy310-tv.rules
# (Alternative: nativ auf dem Board bauen -- gcc-14 und libdrm-Header liegen dort:
#  make -C /root/hy310-tv  nach dem Kopieren von main.c und Makefile)

# --- 1. Kaltstart ------------------------------------------------------------
ss -ulnp | grep -w :69 || { echo "TFTP laeuft nicht -- STOPP, Nachtlog, nicht reparieren"; exit 1; }
sonoff_ctl restart --host 192.168.8.179                      # ~40 s bis SSH
for i in $(seq 30); do ssh -o BatchMode=yes -o ConnectTimeout=3 root@192.168.8.141 uptime && break; sleep 4; done
ssh root@192.168.8.141 'cut -d" " -f1 /proc/uptime'          # < 60 = echter Kaltstart

# --- 2. Kam alles hoch? KEIN prep_after_boot.sh, KEIN hdmi_seq.py ------------
ssh root@192.168.8.141 'dmesg | grep -E "h713-arisc|cpu_comm|hdmirx|afbd" | tail -30'
ssh root@192.168.8.141 'ls -l /dev/video* /dev/dri/*'
ssh root@192.168.8.141 'systemctl status hy310-tv --no-pager -l | head -20'
# erwartet: active (running), gestartet von der udev-Regel, ohne Handgriff.

# --- 3. Stecker rein: Bild ohne Handgriff ------------------------------------
#  Ersatz fuer das Stecken (echtes Stecken kann nur Marco):
ssh user@192.168.8.162 'DISPLAY=:0 xrandr --output HDMI-2 --auto'
sleep 8
ssh root@192.168.8.141 'journalctl -u hy310-tv -n 15 --no-pager'
python3 /opt/Projekte/h713/analyse/hdmi-seq/wandcheck.py shot F-bild
#  Und weil Standbild nicht Stillstand ist -- LEBENDIGKEIT mit Reiz pruefen:
ssh user@192.168.8.162 'DISPLAY=:0 xrandr --output HDMI-2 --gamma 1:0.2:0.2'; sleep 3
python3 /opt/Projekte/h713/analyse/hdmi-seq/wandcheck.py shot F-bild-reiz
ssh user@192.168.8.162 'DISPLAY=:0 xrandr --output HDMI-2 --gamma 1:1:1'; sleep 3
python3 /opt/Projekte/h713/analyse/hdmi-seq/wandcheck.py shot F-bild-zurueck
python3 /opt/Projekte/h713/analyse/hdmi-seq/wandcheck.py diff F-bild F-bild-reiz
python3 /opt/Projekte/h713/analyse/hdmi-seq/wandcheck.py diff F-bild F-bild-zurueck

# --- 4. Stecker raus: Konsole ------------------------------------------------
ssh user@192.168.8.162 'DISPLAY=:0 xrandr --output HDMI-2 --off'
sleep 8
ssh root@192.168.8.141 'journalctl -u hy310-tv -n 10 --no-pager'
python3 /opt/Projekte/h713/analyse/hdmi-seq/wandcheck.py shot F-konsole

# --- 5. Und wieder rein (Wiederholbarkeit) -----------------------------------
ssh user@192.168.8.162 'DISPLAY=:0 xrandr --output HDMI-2 --auto'; sleep 10
python3 /opt/Projekte/h713/analyse/hdmi-seq/wandcheck.py shot F-bild2

# --- 6. Sauberes Beenden -----------------------------------------------------
ssh root@192.168.8.141 'systemctl stop hy310-tv'; sleep 3
python3 /opt/Projekte/h713/analyse/hdmi-seq/wandcheck.py shot F-nach-stop
```

**Erwartet**

| Schritt | Erwartung |
|---|---|
| 2 | `/dev/videoN` da, `hy310-tv` läuft, im Journal `aufnahme …`, `anzeige …`, `crtc …`, `plane 38, NV16, Betriebsart hdmi-ring` |
| 3 | Journal `signal 1920x1080p …` und `bild Plane 38 an …`; **`F-bild`**: Zuspielerbild in Farbe, Geometrie richtig; **`diff F-bild F-bild-reiz`** zeigt eine deutliche Änderung (Größenordnung 5-10 % der Bildpunkte, vgl. B2: 4,65 %), **`diff F-bild F-bild-zurueck`** ≈ 0,00 % - das ist der Beweis, dass das Bild *läuft* und nicht steht |
| 4 | Journal `ereignis SOURCE_CHANGE …`, `signal kein Signal (Flip-Zeiger stehen)`, `konsole Plane aus …`; **`F-konsole`**: Konsolentext auf der Wand, **kein** Standbild der Quelle |
| 5 | Bild kommt von selbst zurück, gleiche Qualität wie in Schritt 3 |
| 6 | `F-nach-stop`: Konsole. **Kein Standbild.** Journal: `ende Signal 15 erhalten`, dann `konsole …` |

**Fotos ansehen (Read), nicht nur die Kennzahlen** - und vor jeder Negativaussage die Positivkontrolle
`ssh root@… 'timeout 40 /root/hdmi_plane_test --pattern -t 30'` (Paket D): kommen die acht Farbbalken,
liegt der Fehler auf der Capture-Seite, nicht in Plane, Mux oder Panel. Ergebnisse nach
`re/captures/weltneuheit/ours-20260907-nacht/F/`.

**Wenn etwas schiefgeht**

| Beobachtung im Journal | Bedeutung | Nächster Schritt |
|---|---|---|
| `kein V4L2-Geraet mit dem Treiber "sun50i-h713-hdmirx"` | 0094 nicht im Kernel oder Probe nicht durch | `dmesg \| grep hdmirx`, Abnahme von E |
| `keine Overlay-Plane mit NV16 und der Eigenschaft "hdmi-ring"` | 0093 nicht im laufenden Kernel | `cat /sys/kernel/debug/dri/*/state` |
| Commit `EOPNOTSUPP` | `memory-region-names = "hdmi-ring", "viddec-info"` fehlt am Display-Knoten | DTB prüfen (D §3) |
| Commit `EINVAL` | Geometrie ≠ Modus, Modifier, Zeilenabstände oder Breite | D §5 |
| `SET_MASTER: … ein anderer Client haelt die Anzeige` | jemand anders ist DRM-Master (X, ein hängendes `hdmi_plane_test`) | den anderen Client beenden |
| **`der Ring steht seit dem Einschalten der Plane still`** | **der erwartete Descriptor-Effekt** (A.5) - die Wand zeigt ein Standbild | einmal von Hand freigeben, dann Schritt 3 wiederholen: `ssh root@192.168.8.141 'cd /root; python3 arisc_hdmi.py --no-probe raw --sub-cmd 0x0211 --arg1 0 --arg2 2 --settle 0.6; sleep 1; python3 arisc_hdmi.py --no-probe hotplug --port 0 --value 1 --settle 1.0'` (0,3 s reichen, M4). **Das ist ein Befund für D/E (§6 Punkt 1), kein Fehler von F** |
| `Quellgeometrie … passt nicht zum Panel-Modus …` | Quelle liefert nicht 1920×1080 | K3/A.6 Punkt 4; Zuspieler auf 1080p60 stellen |

**Marcos Handgriff, wenn er da ist:** dasselbe wie Schritt 3-5, aber mit dem **echten** Kabel am Beamer
(HDMI ziehen, 10 s warten, stecken). Damit ist zugleich K4 Punkt 3 beantwortet - ob die ARISC auf
5-V-Detect von selbst reagiert - , wenn dabei `elog_tail` auf Stufe 5 mitläuft.

---

## 8. Dateien

| Datei | Was |
|---|---|
| `userspace/hy310-tv/main.c` | das Programm (C, Kommentare englisch wie im Rest des Baums) |
| `userspace/hy310-tv/Makefile` | nativer Bau auf dem Board, Querbau gegen `/srv/h713-rootfs`, `install` |
| `userspace/hy310-tv/hy310-tv.service` | systemd-Unit; **kein `[Install]`**, Start über udev |
| `userspace/hy310-tv/99-hy310-tv.rules` | udev-Regel: startet die Unit, sobald `sun50i-h713-hdmirx` sein Gerät anlegt (Alternative zur Warteschleife, weil 0094 asynchron probt) |
| `userspace/hy310-tv/README.md` | deutsch: Rolle, Entscheidung, Konsolenrückgabe, „Standbild ist nicht Stillstand", Bauen, Betrieb, Stolperstelle, Grenzen |
