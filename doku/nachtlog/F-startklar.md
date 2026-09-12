# Paket F — `hy310-tv` startklar gemacht (offline, 07.09. ab 07:5x)

**Agent:** Unteragent F-startklar (offline). **Kein Board angefasst:** kein `ssh root@192.168.8.141`,
kein `ssh user@192.168.8.162`, kein `sonoff_ctl`, kein `wandcheck.py`, kein `tio`, kein `scp`, nichts
nach `tftp/`. Kein `sudo`, kein `git commit`/`push`. **`patches/kernel/series` nicht angefasst**,
`build/build.sh` nicht aufgerufen, **kein Kernel-Patch angefasst** (F ist Userspace).
`/srv/h713-rootfs` nur **gelesen**. Der Baubaum wurde nicht berührt; der Prüfbau lief in
`/tmp/claude-1000/wf-rest/F-startklar/` und in `userspace/hy310-tv/` mit anschließendem `make clean`.

Vorgänger: [F-hy310-tv.md](F-hy310-tv.md) (Entwurfsstand 06.09., 23:00). Was dort in §7 als
Abnahmevorschrift steht, ist **überholt** — sie benutzt `/dev/video0`, `v4l2-ctl` und eine
Reihenfolge, die von den Board-Messungen der Nacht überholt wurde.

> **Nachtrag 07.09., 09:xx — dieses Log ist an drei Stellen überholt.**
> Die Gegenprüfung hat den Beleg für `RING_SETTLE_MS = 3000` als **falsch gelesen** nachgewiesen, und
> die Aussage „nur der erste Enable eines Boots" ist **am Gerät widerlegt**. Betroffen sind §2.2,
> §2.4, §4 (letzte zwei Punkte), §5 (Abnahmevorschrift) und §7. Richtig ist
> [F-korrektur.md](F-korrektur.md); **die gültige Abnahmevorschrift steht dort in §4.** Der Rest
> dieses Logs — Prüfbau, Gerätesuche über den Namen, §2.3, §2.5–§2.8, die Board-Anfragen in §6 —
> steht unverändert.

## Ergebnisdateien

| Datei | sha256 | Zustand |
|---|---|---|
| `userspace/hy310-tv/main.c` | `1219db2766a6692a7052bf2245f53ab9302d9be3a3d79a04d4c41148fa0cccf7` | nachgezogen |
| `userspace/hy310-tv/Makefile` | `dc15136178848ffcb791957eb373da8b3dd39b10a24f1cdba2f81c9749fe38bb` | `install-cross` ergänzt |
| `userspace/hy310-tv/README.md` | `cba24670662f9000bd69909406526831b2890c748369ec54951c62610c207db8` | nachgezogen |
| `userspace/hy310-tv/hy310-tv.service` | `8cebe4aa046f087c06ce45b525941f964ff9711a5a02e7e09cb843783fe7a8cc` | **unverändert** |
| `userspace/hy310-tv/99-hy310-tv.rules` | `08ea07ce63de2df18508b4618a5f2f49dc483022cbf71f1e6d8205a9c2c92ea3` | **unverändert** |

Die udev-Regel trifft auf `ATTR{name}=="sun50i-h713-hdmirx"`, und 0094 setzt
`strscpy(rx->vdev.name, H713_HDMIRX_NAME, …)`. Sie passt also auf `/dev/video1` genauso wie auf
`video0` — an ihr war nichts zu korrigieren, und das ist der Grund, warum das Programm jetzt
**dieselbe** Zeichenkette aus `/sys/class/video4linux/videoN/name` liest.

---

## 1. Prüfbau — **ausdrücklich ein Prüfbau, kein Serienartefakt**

```
clang --target=aarch64-linux-gnu --sysroot=/srv/h713-rootfs -fuse-ld=lld \
    -O2 -g -Wall -Wextra -Wshadow -Wvla -isystem /srv/h713-rootfs/usr/include/libdrm \
    -L/srv/h713-rootfs/usr/lib/aarch64-linux-gnu -o hy310-tv.aarch64-linux-gnu main.c -ldrm
```

| Prüfung | Ergebnis |
|---|---|
| `make -C userspace/hy310-tv cross`, clang 18.1.3 (Host), `-Wall -Wextra -Wshadow -Wvla` | **grün, null Warnungen** |
| Ergebnis | `ELF 64-bit LSB pie executable, ARM aarch64`, 55 552 B, `NEEDED libdrm.so.2`, `libc.so.6` — sonst nichts |
| `clang --analyze` (`core,unix,deadcode`) | **kein Befund** |
| Gegenprobe: derselbe Bau mit dem **alten** `main.c` | ebenfalls grün — der Entwurf war baubar, nur inhaltlich überholt |
| `make install-cross DESTDIR=…` (Wegwerf-Wurzel) | legt `usr/local/sbin/hy310-tv` (arm64), Unit und Regel ab |
| `udevadm verify 99-hy310-tv.rules` | `Success: 1, Fail: 0` |
| `systemd-analyze verify ./hy310-tv.service` | grün (einziger Hinweis: `/usr/local/sbin/hy310-tv` gibt es auf **diesem** Rechner nicht — erwartet) |
| `make clean` | Baum wieder sauber, **kein Binärartefakt im Repo** |

**Nicht gelaufen.** Ein Lauf braucht `/dev/dri/card1` mit 0093 und `/dev/video1` mit 0094; beides gibt
es nur am Board. Das bleibt der Hauptsitzung.

### Warum der Prüfbau nicht im Container `h713-build` lief

Der Auftrag nannte den Container. Er kann es nicht, und das ist nachgesehen, nicht angenommen:

```
podman inspect h713-build --format '{{json .Mounts}}'
  -> genau ein Mount: /opt/Projekte/h713 (rbind) -> /work
podman exec h713-build bash -lc 'ls /srv'
  -> leer
```

Der Container sieht `/srv/h713-rootfs` also nicht, und er hat weder libdrm noch einen arm64-Sysroot.
Ihm den Board-Root zuzumounten hieße, die laufende Welt neu zu erzeugen; die Header stattdessen ins
Repo zu kopieren hieße, Board-Root-Dateien in den Baum zu legen. Beides ist ausgeschlossen. Regel 2 des
Nachtplans gilt dem **Kernel** („nur über `build/build.sh`"); für ein Userspace-Werkzeug ist der
Host-Clang gegen `/srv/h713-rootfs` genau der Weg, den Paket D für `analyse/kms/hdmi_plane_test.c`
bereits beschreibt (`analyse/kms/README-hdmi-plane.md`). **Benannt, nicht improvisiert.**

---

## 2. Die korrigierten Annahmen — das ist der Kern

### 2.1 „Die Nummern kann man raten" → Suche über den Namen

**Alte Annahme:** die Suche über `VIDIOC_QUERYCAP.driver` genügt, also werden `/dev/video0…15` der
Reihe nach geöffnet. **Widerlegt am Gerät:** `/dev/video0` ist cedrus, die Capture ist **`/dev/video1`**;
`card0` ist Panfrost, die Anzeige ist **`/dev/dri/card1`**.

Die Suche war schon vorher richtig (Nummern wurden nie verdrahtet), aber sie fasste fremde Geräte an.
Jetzt fragt das Programm **erst** `/sys/class/video4linux/videoN/name` — dieselbe Zeichenkette, auf die
die udev-Regel passt — und öffnet nur den Knoten, der antwortet; `QUERYCAP` bestätigt danach. Cedrus
wird gar nicht mehr geöffnet. Alle Doku-Beispiele stehen jetzt auf `video1`/`card1`/`crtc 36`/`plane 38`,
mit dem ausdrücklichen Satz, dass keine dieser Zahlen im Programm steht.

### 2.2 „Nach dem Einschalten sofort nachfragen" → **das war der eine echte Fehler**

> **Überholt (07.09., 09:xx).** Der Befund „sofort nachfragen ist falsch" bleibt richtig, die
> **Schlussfolgerung auf 3 s nicht**: die zitierte Tabelle zeigt bei +1 s `0x05600010 = 0x03000010`,
> also **Source 0 noch aus**. Sie belegt das Schreiben des Treibers, nicht die Reaktionszeit der
> Firmware. `RING_SETTLE_MS` ist ersatzlos raus, an seiner Stelle steht eine begrenzte Abtastreihe.
> Siehe [F-korrektur.md](F-korrektur.md) §1.

**Alte Annahme:** unmittelbar nach dem Atomic-Commit noch einmal `QUERY_DV_TIMINGS`, dann steht im
Journal, ob der Descriptor die Capture abgeschaltet hat.

**Widerlegt durch [D-abnahme-board.md](D-abnahme-board.md), Nachtrag 06:15.** Dort ist der Übergang im
Sekundentakt mitgeschrieben:

| t nach Plane-Start | `0x05600098` (Descriptor) | `0x06940928` (Capture-Freigabe) |
|---|---|---|
| +1 s | `0x00000000` | `0xE0020438` — **frei** |
| +2 s | `0x4D95F000` | `0x60020438` — **abgeschaltet** |

Die sofortige Nachfrage misst also den Ring, **während er noch läuft**, und schreibt „alles gut" —
eine Sekunde bevor die Wand einfriert. Das ist die schlechteste erreichbare Antwort: sie sieht aus wie
ein Befund und ist keiner.

**Jetzt:** am `poll()` hängt ein dritter Deskriptor, ein `timerfd`, das beim Einschalten **einmal** auf
`RING_SETTLE_MS = 3000` gestellt und beim Abschalten wieder entschärft wird. 3 s = die gemessenen +2 s
mit Reserve. Es ist ein **Messtermin**, keine Heilung, keine Wiederholung, keine Schleife: es hängt
nichts daran außer einer Journalzeile, und die Plane bleibt in beiden Fällen, wie sie ist.

Der Zahlenwert ist der einzige geratene Anteil, und er ist auf eine Messung gestützt. Wer ihn schärfer
haben will, liest `0x06940928` im 200-ms-Takt über die ersten 5 s nach dem Enable — das ist eine
Messung von ~5 min, kein Blocker.

### 2.3 „`S_INPUT(0)` ist ein Nullwechsel" → es ist ein **wiederholtes** `SetSource(3)`

**Alte Annahme** (im Code und im README): `VIDIOC_S_INPUT(0)` sei ein Nullwechsel und deshalb wirkungslos.

**Nachgesehen in 0094:** `h713_hdmirx_s_input()` ruft bei `i == 0` **immer**
`h713_hdmirx_set_source()`, und das schickt `SetSource(3)` an die Firmware. Es ist also kein
Nullwechsel, sondern eine Wiederholung — und damit **etwas anderes** als der Weg, der in
[B2-quellenwechsel.md](B2-quellenwechsel.md) gemessen wurde (`3 → 1 → 3`, VideoDec dazwischen).

Das ändert nichts an der Entscheidung, es schärft nur die Begründung: **ein wiederholtes `SetSource(3)`
ist nicht gemessen.** Es trotzdem zu rufen, in der Hoffnung, es könnte die Capture freigeben, wäre
geraten statt belegt. Der Kommentar im Code sagt das jetzt so. → Board-Anfrage §6.

### 2.4 „Der Descriptor-Effekt kommt bei jedem Einschalten" → nur beim **ersten** eines Boots

> **Widerlegt (07.09., 09:xx).** Das Ereignis hängt am **Zeiger** `0x05600098`, nicht am Inhalt:
> `afbd_source0.py off` nullt die vier Info-Slots, und der nächste Enable **im selben Boot** löst den
> Effekt erneut aus (`D-cstride-befund.md`, am Gerät reproduziert; `D-cstride-fix.md` §1). Der
> `memcmp` schützt vor einem zweiten **Publish desselben Datensatzes**, nicht vor einem zweiten
> VideoDec-Ereignis. Folge: `hy310-tv` beobachtet nach **jedem** Einschalten, und Schritt 8 der
> Abnahme darf die zweite `ring`-Zeile **nicht** als „muss langweilig sein" fordern. Siehe
> [F-korrektur.md](F-korrektur.md) §2.

**Nachgesehen in 0093:** `h713_afbd_publish_video_info()` vergleicht den Inhalt (`memcmp`) und schreibt
den Descriptor nicht noch einmal; ein zweiter Publish ist ausdrücklich das, was die Hardware nicht
überlebt. Nach Signalverlust und -rückkehr wird also **kein** VideoDec-Ereignis mehr ausgelöst und die
Capture bleibt scharf.

Folge für die Abnahme: die `ring`-Zeile ist nur beim **ersten** Einschalten nach dem Kaltstart
interessant. Beim zweiten und dritten Mal muss sie die langweilige sein. Steht sie dort auf „steht
still", ist das ein **neuer** Befund und gehört ins Log.

### 2.5 „E liefert NV16" → E liefert **NV16M**, und das ist kein Widerspruch

`V4L2_PIX_FMT_NV16M` = zwei **getrennte** Ebenen à 2 073 600 Byte (Y und C liegen `0x5FD000`
auseinander). Der KMS-Framebuffer ist `DRM_FORMAT_NV16` — ein Zweiebenen-Fourcc in **einem**
Pufferobjekt — und trägt in `hdmi-ring` ohnehin nur Format, Geometrie und Zeilenabstand. Zwischen beiden
wird nichts umgerechnet, weil zwischen beiden nichts fließt: die Plane holt sich die Ringadressen selbst.
0093 prüft `fb->format->format == DRM_FORMAT_NV16` — der Träger-FB ist richtig, wie er ist. Das steht
jetzt als eigener Absatz im Kopfkommentar und im README, damit die Frage nicht ein zweites Mal
aufkommt.

### 2.6 „Die ersten Puffer sind leer" → betrifft F heute **nicht**, morgen aber sehr wohl

Bild 0 und 1 nach `STREAMON` sind komplett null, ab Bild 29 voller Inhalt (am Gerät gemessen); sie gehen
in die Warteschlange, bevor der erste Flip sie füllt. **F streamt nicht** — kein `REQBUFS`, kein
`STREAMON`, kein `DQBUF` —, also erreicht ihn das über den Datenpfad nicht. Zwei Stellen, an denen es
trotzdem hängen bleibt, und beide stehen jetzt schwarz auf weiß:

1. **Der `DQBUF`-Pfad aus Anhang A.4**, sobald 0094 `VIDIOC_EXPBUF` hat, **muss die ersten Bilder
   verwerfen**, sonst zeigt er Grün. Das steht in den Grenzen des README und im Kopfkommentar dort, wo
   die zweite Betriebsart beschrieben ist.
2. **Ganz-Null-NV16 ist flaches Grün** — dieselbe Farbe, die die A-Abnahme mit leerem Ring auf der Wand
   hatte. Und 0093 fällt beim Einschalten auf die Adressen des **Träger-Framebuffers** zurück, wenn es
   kein gültiges Flip-Paar lesen kann (`if (!ring || !h713_afbd_read_ring(...))`). Dieser Puffer bleibt
   deshalb **absichtlich** so, wie der Kernel ihn liefert: null. Ihn auf legales Schwarz zu füllen wäre
   verlockend und wäre falsch — es machte aus einem eindeutigen Fingerabdruck („es hat nichts
   geschrieben") ein zweideutiges schwarzes Bild. Der Kommentar an `display_create_fb()` sagt genau das.

### 2.7 Zwei Stellen, an denen das Programm gelogen hätte

* **`display_hide()` meldete Erfolg, auch wenn der Commit scheiterte.** Es setzte `on = false` und gab
  den DRM-Master ab — bei stehender Plane. Das Ergebnis wäre ein Standbild auf der Wand plus die
  Journalzeile „Konsole zurück", also genau die Aussage, deren Gegenteil dieses Programm garantieren
  soll. Jetzt gibt `display_hide()` `false` zurück, **behält** Master und Zustand und sagt deutlich, dass
  die Konsole **nicht** zurück ist; beim Beenden wird daraus ein Rückgabewert ≠ 0.
* **`-s -5` wurde stillschweigend zu „Saettigung nicht setzen".** `atoi()` ohne Prüfung, und die
  Obergrenze wurde erst nach dem Parsen geprüft. Jetzt `strtol()` mit Bereichsprüfung 0…255 und
  klarer Fehlermeldung.

### 2.8 Kleinkram, der beim Nachziehen aufgefallen ist

* Der `pitch != width`-Abbruch in `display_create_fb()` sah nach Pedanterie aus und ist keine: 0093
  programmiert `Y_STRIDE` aus `fb->pitches[0]` und den Chroma-Stride als `2 * fb->pitches[1]`, und diese
  Strides beschreiben den **Ring**. Ein aufgefüllter Dumb-Zeilenabstand stellte die Hardware auf Daten
  ein, die dieser Puffer nicht besitzt. Die Meldung sagt das jetzt.
* `Makefile`: `install` legte auf dem Arbeitsrechner das **x86**-Programm ins Board-Root. Dafür gibt es
  jetzt `install-cross`; `install` bleibt der native Weg auf dem Board.
* Das README behauptete „~560 Zeilen"; es sind gut 600. Nebensache, aber falsch ist falsch.

---

## 3. Zwei Feststellungen für die Hauptsitzung (nicht von F verursacht)

1. **`v4l2-ctl` **ist** auf dem Board-Root installiert** (`/srv/h713-rootfs/usr/bin/v4l2-ctl`, Paket
   `v4l-utils`), ebenso GStreamer. **`modetest` fehlt** (kein `libdrm-tests`). Der Auftrag und
   `E-v4l2.md` §3a sagen bei beiden „nicht installiert"; bei `v4l2-ctl` stimmt das nicht. Das war schon
   die Bitte in `F-hy310-tv.md` §6 Punkt 3 und ist noch offen. **Die Abnahme in §5 kommt trotzdem ohne
   beide aus**, wie beauftragt — sie benutzt die debugfs-Seiten, und die sind ohnehin die besseren
   Belege.
2. **Der C-Stride-Befund aus `D-abnahme-board.md` (Nachtrag 06:15) passt nicht zum Code, den ich lese.**
   D schließt: „der Treiber schreibt den NV16-C-Stride beim ersten Enable gar nicht". In 0093 steht
   `writel(c_stride, h->regs + AFBD_VIDEO_C_STRIDE)` **unbedingt** in `atomic_update()`, nach
   `publish_video_info()` und ohne Zweig darum. Entweder überschreibt der Firmware-Übergang den Wert
   doch (Ds ursprüngliche, dann verworfene Hypothese — die Sekundenlesung kann ihn zwischen zwei
   Abtastungen verpasst haben), oder `h713_afbd_wait_ready()` im Publish-Pfad kehrt zurück, bevor die
   Registerbank übernommen hat. **Ich habe 0093 nicht angefasst.** Für die F-Abnahme heißt es nur:
   beim **ersten** Enable nach Kaltstart kann das Bild entsättigt und die Farbe nach rechts unten
   ausgelaufen sein (`D-10`). Das ist Ds offener Punkt, kein Fehler von F — bitte nicht F anlasten.

---

## 4. Was das Programm jetzt tut

```
BEREITSCHAFT  --- SOURCE_CHANGE, Signal da ---> BILD
Plane aus, DRM-Master abgegeben                 Plane an (hdmi-ring=1), Master gehalten
(Konsole hat das Panel)     <--- SOURCE_CHANGE, kein Signal ---
```

* Suche: `/sys/class/video4linux/*/name == "sun50i-h713-hdmirx"` (+ `QUERYCAP`),
  `drmGetVersion()->name == "sun50i-h713-afbd"`, Plane = Overlay + NV16 + `hdmi-ring`.
* Einmal `S_INPUT(0)`, einmal `SUBSCRIBE_EVENT(SOURCE_CHANGE)`, dann `poll()` auf **drei** Deskriptoren:
  Aufnahmegerät (`POLLPRI`), `signalfd` (TERM/INT/HUP), `timerfd` (die 3-s-Rückschau).
* Pro Ereignis: `QUERY_DV_TIMINGS` → Plane an oder aus. **Keine Zeitschleife, kein `sleep` als
  Heilmittel, keine Wiederholung ohne Ursache.**
* Plane an = ein Atomic-Commit (`FB_ID/CRTC_ID/SRC_*/CRTC_*` + `hdmi-ring=1`, optional `saturation`),
  danach der eine Messtermin nach 3 s.
* Plane aus = Commit mit `FB_ID=0, CRTC_ID=0`; scheitert er, sagt das Programm es und behält Master und
  Zustand, statt „Konsole zurück" zu behaupten.
* `SIGTERM`/`SIGINT`/`SIGHUP` nehmen denselben Ausgang wie ein Signalverlust.

---

## 5. Abnahmevorschrift (kopierbar, Hauptsitzung) — **ohne `v4l2-ctl`, ohne `modetest`**

> **ÜBERHOLT (07.09., 09:xx). Nicht mehr nach dieser Vorschrift abnehmen.** Schritt 4 und Schritt 8
> prüfen auf die `3000 ms`-Zeile, die es nicht mehr gibt, und Schritt 8 fordert eine Aussage, die
> widerlegt ist (§2.4). **Gültig ist [F-korrektur.md](F-korrektur.md) §4** — sie ist aus dieser hier
> hervorgegangen, Schritte 0–3 und 5–7 sind unverändert.

**Voraussetzungen:** der Kernel mit der integrierten Serie läuft (0091–0095), die Wand zeigt die
Konsole, der Zuspieler `192.168.8.162` ist wach und auf 1080p60. Board-Sperre halten.

**Instrumente statt Werkzeuge** — beide Statusseiten sind Teil der Patches, kein Zusatz:

| Frage | Instrument |
|---|---|
| Läuft die Capture, wandern die Flip-Zeiger? | `/sys/kernel/debug/sun50i-h713-hdmirx/status` (0094) |
| Steht die Plane, mit welchen Eigenschaften? | `/sys/kernel/debug/dri/1/state` (KMS-Kern) |
| Ist die Capture freigegeben? | `0x06940928` Bit 31 (`0xE0…` = frei, `0x60…` = abgeschaltet) |
| Lebt das Bild? | erzwungener Reiz am Zuspieler — **nie** ein Blick auf ein unverändertes Foto |

**Solange `hy310-tv` das Bild zeigt, hält es den DRM-Master.** `gamma_test`, `hdmi_plane_test` und jeder
andere KMS-Client bekommen dann `Permission denied` (H-Abnahme, Nachtrag 06:20). Vor jeder
Positivkontrolle also erst `systemctl stop hy310-tv`.

```bash
# --- 0. Bauen und installieren (Arbeitsrechner) ------------------------------
cd /opt/Projekte/h713/userspace/hy310-tv
make cross                                                     # Pruefbau, muss gruen sein
#  /srv/h713-rootfs gehoert root. Zwei Wege, einer davon ohne sudo am Arbeitsrechner:
#  (a) ueber das Board, das sein eigenes NFS-Root als root schreibt -- bevorzugt:
scp hy310-tv.aarch64-linux-gnu root@192.168.8.141:/usr/local/sbin/hy310-tv
scp hy310-tv.service            root@192.168.8.141:/etc/systemd/system/hy310-tv.service
scp 99-hy310-tv.rules           root@192.168.8.141:/etc/udev/rules.d/99-hy310-tv.rules
ssh root@192.168.8.141 'chmod 0755 /usr/local/sbin/hy310-tv'
#  (b) direkt ins Board-Root, braucht root am Arbeitsrechner:
#      sudo make install-cross DESTDIR=/srv/h713-rootfs
ssh root@192.168.8.141 'systemctl daemon-reload; udevadm control --reload'
make clean                                                     # kein Binaerartefakt im Repo

# --- 1. Kaltstart ------------------------------------------------------------
ss -ulnp | grep -w :69 || { echo "TFTP laeuft nicht -- STOPP, Nachtlog, nicht reparieren"; exit 1; }
sonoff_ctl restart --host 192.168.8.179                        # ~40 s bis SSH
for i in $(seq 30); do ssh -o BatchMode=yes -o ConnectTimeout=3 root@192.168.8.141 uptime && break; sleep 4; done
ssh root@192.168.8.141 'cut -d" " -f1 /proc/uptime'            # < 60 = echter Kaltstart

# --- 2. Kam alles von selbst hoch? KEIN prep-Skript, KEIN hdmi_seq.py --------
ssh root@192.168.8.141 'grep -H . /sys/class/video4linux/video*/name; ls -l /dev/dri/'
ssh root@192.168.8.141 'systemctl status hy310-tv --no-pager -l | head -25'
ssh root@192.168.8.141 'journalctl -u hy310-tv -n 30 --no-pager'
#  erwartet: von der udev-Regel gestartet, ohne Handgriff; im Journal
#    aufnahme    /dev/video1 (sun50i-h713-hdmirx, ...)
#    anzeige     /dev/dri/card1 (sun50i-h713-afbd)
#    crtc        36, Modus 1920x1080
#    plane       38, NV16, Betriebsart hdmi-ring

# --- 3. Zustand vor dem ersten Bild ------------------------------------------
ssh root@192.168.8.141 'cat /sys/kernel/debug/sun50i-h713-hdmirx/status'
#  erwartet: signal: vorhanden (Flip-Zeiger wandern) -- sonst haengt es an B/E, nicht an F

# --- 4. Bild da? -------------------------------------------------------------
ssh root@192.168.8.141 'journalctl -u hy310-tv -n 10 --no-pager'
#  erwartet: signal 1920x1080p ...   bild Plane 38 an ...
#  und 3 s spaeter GENAU EINE dieser beiden Zeilen:
#    ring        laeuft 3000 ms nach dem Einschalten weiter   <- Gutfall
#    warnung: der Ring steht 3000 ms nach dem Einschalten ... <- Descriptor-Effekt, siehe Schritt 7
ssh root@192.168.8.141 'cat /sys/kernel/debug/dri/1/state | sed -n "/plane\[38\]/,/^plane/p"'
#  erwartet: crtc=36, fb=<id>, NV16, hdmi-ring=1
python3 /opt/Projekte/h713/analyse/hdmi-seq/wandcheck.py shot F-bild

# --- 5. LEBENDIGKEITSBEWEIS: Standbild ist kein Stillstand ------------------
ssh user@192.168.8.162 'DISPLAY=:0 xrandr --output HDMI-2 --gamma 1:0.25:0.25'; sleep 3
python3 /opt/Projekte/h713/analyse/hdmi-seq/wandcheck.py shot F-bild-reiz
ssh user@192.168.8.162 'DISPLAY=:0 xrandr --output HDMI-2 --gamma 1:1:1'; sleep 3
python3 /opt/Projekte/h713/analyse/hdmi-seq/wandcheck.py shot F-bild-zurueck
python3 /opt/Projekte/h713/analyse/hdmi-seq/wandcheck.py diff F-bild F-bild-reiz
python3 /opt/Projekte/h713/analyse/hdmi-seq/wandcheck.py diff F-bild F-bild-zurueck
#  Kriterium: der Reiz aendert ZWEISTELLIG viele Prozent (D-Abnahme: 38,74 %).
#  Die Rueckkehr muss NICHT 0,00 % sein -- die Quelle driftet (D: 9,84 %, M4).
#  Nur der Sprung zaehlt. Ohne Sprung ist es ein Standbild, egal wie gut es aussieht.

# --- 6. Stecker raus: Konsole -- die eigentliche Aufgabe von F ---------------
ssh user@192.168.8.162 'DISPLAY=:0 xrandr --output HDMI-2 --off'; sleep 8
ssh root@192.168.8.141 'journalctl -u hy310-tv -n 10 --no-pager'
#  erwartet: ereignis SOURCE_CHANGE ... / signal kein Signal ... / konsole Plane aus ...
python3 /opt/Projekte/h713/analyse/hdmi-seq/wandcheck.py shot F-konsole
#  MUSS Konsolentext zeigen. Ein Standbild der Quelle hier ist der Durchfall schlechthin --
#  bei Signalverlust friert der Ring ein und die Wand wird NICHT von selbst schwarz (K4).

# --- 7. Nur falls Schritt 4 den Descriptor-Effekt gemeldet hat ---------------
#  Einmal von Hand freigeben (Stock-RPC, kein Poke), dann Schritt 4-5 wiederholen:
ssh root@192.168.8.141 'cd /root; python3 arisc_hdmi.py --no-probe raw --sub-cmd 0x0211 --arg1 0 --arg2 2 --settle 0.6; sleep 1; python3 arisc_hdmi.py --no-probe hotplug --port 0 --value 1 --settle 1.0'
ssh root@192.168.8.141 'cat /sys/kernel/debug/sun50i-h713-hdmirx/status | head -8'
#  Das ist ein Befund fuer D/E (§6), KEIN Fehler von F.

# --- 8. Und wieder rein: Wiederholbarkeit -----------------------------------
ssh user@192.168.8.162 'DISPLAY=:0 xrandr --output HDMI-2 --auto'; sleep 10
ssh root@192.168.8.141 'journalctl -u hy310-tv -n 10 --no-pager'
python3 /opt/Projekte/h713/analyse/hdmi-seq/wandcheck.py shot F-bild2
#  Hier MUSS die ring-Zeile die langweilige sein (0093 schreibt den Descriptor
#  nicht ein zweites Mal). Steht sie auf "steht still", ist das ein NEUER Befund.
#  Und noch einmal den Reiz aus Schritt 5 -- ein zweites Bild ist auch nur ein Foto.

# --- 9. Sauberes Beenden -----------------------------------------------------
ssh root@192.168.8.141 'systemctl stop hy310-tv; echo rc=$?'; sleep 3
python3 /opt/Projekte/h713/analyse/hdmi-seq/wandcheck.py shot F-nach-stop
#  erwartet: Journal "ende Signal 15 erhalten" + "konsole Plane aus ...", rc=0,
#  Wand = Konsole. KEIN Standbild.
```

**Erwartungstabelle**

| Schritt | Erwartung |
|---|---|
| 2 | `video1` trägt den Namen `sun50i-h713-hdmirx`; Unit `active (running)`, von udev gestartet, ohne Handgriff |
| 3 | debugfs `signal: vorhanden (Flip-Zeiger wandern)` |
| 4 | Journal `bild Plane 38 an …`; `dri/1/state` zeigt `hdmi-ring=1` an CRTC 36; `F-bild` = Zuspielerbild in Farbe, volle Breite |
| 5 | Reiz ändert zweistellig viele Prozent; Rückkehr deutlich kleiner. **Das ist der einzige gültige Beweis, dass das Bild läuft** |
| 6 | Konsolentext auf der Wand, **kein** Standbild |
| 8 | Bild kommt von selbst zurück; `ring`-Zeile unauffällig |
| 9 | Konsole, `rc=0`, kein Standbild |

**Fotos ansehen (Read), nicht nur Kennzahlen.** Vor jeder Negativaussage die Positivkontrolle —
**erst die Unit stoppen**, sonst misst man nur den gehaltenen DRM-Master:
`ssh root@192.168.8.141 'systemctl stop hy310-tv'` und dann
`setsid sh -c "nohup /root/hdmi_plane_test --pattern -t 30 > /root/pk.out 2>&1 &"` (die SSH-Sitzung
danach **nicht** abwürgen, sonst stirbt die Prozessgruppe mit — D-Nebenbefund). Kommen die acht
Farbbalken, liegt der Fehler auf der Capture-Seite, nicht in Plane, Mux oder Panel.

`wandcheck.py` schreibt ohne Angabe nach `re/captures/weltneuheit/wand-aktuell`. Für diese Abnahme
jedem Aufruf `--dir /opt/Projekte/h713/re/captures/weltneuheit/ours-20260907-nacht/F` anhängen (oder
`WAND_DIR=` setzen), damit die Abzüge dort landen, wo die anderen Pakete ihre haben.

**Wenn etwas schiefgeht**

| Beobachtung | Bedeutung | Nächster Schritt |
|---|---|---|
| `kein V4L2-Geraet mit dem Namen "sun50i-h713-hdmirx"` | 0094 nicht drin oder Probe nicht durch | `grep -H . /sys/class/video4linux/*/name`, `dmesg \| grep hdmirx` |
| `keine Overlay-Plane mit NV16 und der Eigenschaft "hdmi-ring"` | 0093 nicht im laufenden Kernel | `cat /sys/kernel/debug/dri/1/state` |
| Commit `EOPNOTSUPP` | `memory-region-names = "hdmi-ring", "viddec-info"` fehlt am Display-Knoten | DTB prüfen (D §3) |
| Commit `EINVAL` | Geometrie ≠ Modus, Modifier, Zeilenabstände oder Breite | D §5 |
| `SET_MASTER: … ein anderer Client haelt die Anzeige` | X, ein hängendes `hdmi_plane_test` oder `gamma_test` | den anderen Client beenden |
| **Wand ist flach grün** | **Ganz-Null-NV16 = es hat nichts geschrieben**: leerer Ring-Slot (A-Abnahme) oder 0093 ist auf den Träger-FB zurückgefallen | debugfs `flip:` und `slot N:` lesen; `0x06940928` prüfen |
| Bild entsättigt, Farbe quillt nach rechts unten | C-Stride steht auf `0x0780` statt `0x0F00` — **Ds offener Punkt** (D-Abnahme 06:15, Foto `D-10`) | Befund für 0093, **nicht** F |
| `der Ring steht 3000 ms nach dem Einschalten still` | der erwartete Descriptor-Effekt beim **ersten** Enable | Schritt 7; Befund für D/E (§6) |
| `die Plane laesst sich nicht abschalten … Konsole ist NICHT zurueck` | Disable-Commit abgelehnt — die Wand zeigt noch das Bild | Journal + `dri/1/state`, **nicht** neu starten, bevor das im Log steht |
| `Quellgeometrie … passt nicht zum Panel-Modus …` | Quelle liefert nicht 1920×1080 | K3/A.6 Punkt 4; Zuspieler auf 1080p60 stellen |

**Marcos Handgriff, wenn er da ist:** Schritt 4–8 mit dem **echten** Kabel am Beamer (ziehen, 10 s,
stecken). Damit ist zugleich K4 Punkt 3 beantwortet — ob die ARISC auf 5-V-Detect von selbst reagiert —,
wenn `elog_tail` auf Stufe 5 mitläuft.

---

## 6. Board-Anfragen (eine Messung, sonst nichts)

1. **An D (0093) — die Freigabe gehört in den Plane-Enable.** Wer den Descriptor schreibt, muss die
   Capture danach wieder scharf machen; beide Wege sind Stock-RPCs (B2: `SetSource` weg und zurück;
   M4: HPD-Zyklus, 0,3 s belegt). Solange das nicht dort steht, zeigt der erste Kaltstartlauf ein
   Standbild und F kann nur warnen. **Unverändert offen seit `F-hy310-tv.md` §6 Punkt 1.**
2. **Messung M-F1 (~3 min, kein Kaltstart nötig): Reicht ein wiederholtes `SetSource(3)`?**
   Wenn ja, könnte 0094 die Freigabe in `S_INPUT` legen und es bräuchte gar keinen Hot-Plug. Gemessen
   ist bisher nur `3 → 1 → 3` (B2).
   `VIDIOC_S_INPUT(0)` **ist** dieser Aufruf und sonst nichts — deshalb genügt `v4l2-ctl --set-input=0`,
   und das ist auf dem Board-Root installiert (§3 Punkt 1). Für **diese** Messung ist es das richtige
   Werkzeug; die Abnahme in §5 kommt weiterhin ohne es aus.
   ```bash
   # Ausgangslage: Bild steht, Ring frisch eingefroren (hy310-tv hat den Descriptor-Effekt gemeldet)
   ssh root@192.168.8.141 'python3 /root/dump_state.py mf1_vor'
   ssh root@192.168.8.141 'grep -m1 ^0x06940928: /root/dumps/mf1_vor.txt'    # erwartet 0x60020438

   ssh root@192.168.8.141 'v4l2-ctl -d /dev/video1 --set-input=0'            # NUR SetSource(3), kein Umweg
   sleep 2
   ssh root@192.168.8.141 'python3 /root/dump_state.py mf1_nach'
   ssh root@192.168.8.141 'grep -m1 ^0x06940928: /root/dumps/mf1_nach.txt'
   ssh root@192.168.8.141 'cat /sys/kernel/debug/sun50i-h713-hdmirx/status | head -8'
   ```
   Und dann **zwingend** der Reiz aus §5 Schritt 5: ein zurückgekehrtes Registerbit ist kein Beweis,
   dass wieder **geschrieben** wird — genau diese Verwechslung hat die Nacht eine Stunde gekostet.

   **`0xE0020438` + Reizantwort = ja** → die Freigabe kann in `S_INPUT` (0094), und es braucht keinen
   Hot-Plug.
   **`0x60020438` = nein** → es bleibt bei Quellenwechsel (`3 → 1 → 3`) oder HPD im Plane-Enable (0093).
   Beides ist ein gültiges Ergebnis; eine klar benannte Sackgasse zählt.
3. **An E (0094) — `VIDIOC_EXPBUF`.** Erst damit ist der `DQBUF`→Plane-Weg aus A.4 baubar. Wer ihn baut:
   die ersten ein bis zwei Bilder verwerfen (§2.6).
4. **An die Hauptsitzung:** `v4l2-ctl` ist installiert (§3 Punkt 1) — bitte `E-v4l2.md` §3a beim
   Zusammenführen richtigstellen.

---

## 7. Was offen bleibt

* **Ein Lauf.** Das Programm ist gebaut und geprüft, aber nie gestartet worden. Alles in §5 ist
  Erwartung, kein Messwert.
* ~~**Die 3 s** sind aus Ds Sekundenlesung abgeleitet, nicht selbst gemessen (§2.2).~~
  **Erledigt am 07.09., 09:xx: die 3 s sind raus** — die Ableitung war falsch (die Sekundenlesung
  belegt sie nicht), an ihrer Stelle steht eine begrenzte Abtastreihe mit Zeitstempel und einer
  ausdrücklich gemeldeten Frist. [F-korrektur.md](F-korrektur.md).
* **Der C-Stride-Widerspruch** in §3 Punkt 2 ist ungeklärt; 0093 wurde nicht angefasst.
* **Kein Audio, kein Overlay, eine Quellgeometrie pro Boot** — unverändert die Grenzen aus dem README.
