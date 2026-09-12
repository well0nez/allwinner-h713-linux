# S12 — Review `hy310-tv`: Programm, Konsolen-Cursor, Steuerschnittstelle, Dienst

08.09.2026 · reine Code- und Konzeptarbeit, **kein Board angefasst, keine Datei außer dieser geändert,
nichts gebaut**. Auftrag: `userspace/hy310-tv/` reviewen, den stehenden Konsolen-Cursor nach dem
Rückschalten erklären, eine Steuerschnittstelle „alles vom Userspace" entwerfen, Dienst/Installation prüfen.

**Grundlage.** `userspace/hy310-tv/main.c` (1192 Zeilen, Stand 08.09. 01:12), `README.md`, `Makefile`,
`hy310-tv.service`, `99-hy310-tv.rules`; Kernelbaum `mainline/build/linux-6.18.38-431a1f88…` mit
`sun50i-h713-hdmirx.c` (3220 Z.), `sun50i-h713-afbd.c` (1972 Z.), `drm_fb_helper.c`, `drm_fbdev_dma.c`,
`drm_auth.c`, `drm_file.c`, `drm_client_modeset.c`, `fbcon.c`, `vt.c`, `printk.c`; Patch-Kommentare 0100–0124;
doku 83/86/88/96/97, `nachtlog/S11`; Board-Root `/srv/h713-rootfs` (nur gelesen, soweit Rechte reichten).

**Legende.** *belegt* = im Code oder in einem Messprotokoll nachgelesen, Zeile genannt. *vermutet* = plausible
Ableitung, am Gerät noch zu prüfen; der Prüfschritt steht dabei. Zeilennummern ohne Datei meinen `main.c`;
`hdmirx N` / `afbd N` meinen die beiden Treiberdateien im Baubaum.

---

## 0. Das Wichtigste zuerst

1. **Das Programm ist im Kern richtig gebaut** (Gerätesuche über Namen, ereignisgetrieben, ein Ausgang für
   alle Wege, Master nur bei stehendem Bild). Drei Dinge sind falsch oder überholt und sollten vor allem
   anderen weg: der **implizite DRM-Master beim Öffnen wird nie abgegeben** (A3), **`-ENOLCK` wird als
   „kein Signal" gelesen** — das ist das Rennen zwischen `SOURCE_CHANGE` und Geometrie (A1), und die
   **Startzeile „offen …" behauptet etwas, das seit 0107/0124 nicht mehr stimmt** (A2).
2. **Der Cursor.** Nach dem Rückschalten ist am DRM nichts wiederherzustellen: das fbdev des afbd hat keinen
   Schattenpuffer, fbcon schreibt direkt in den Scanout-Speicher, und `drmDropMaster` gibt genau das frei,
   was fbcon braucht (B.1, belegt). Dass der Cursor trotzdem steht, erklärt eine Eigenheit von fbcon:
   `fb_flashcursor()` **setzt sich nicht neu auf, wenn `console_trylock()` fehlschlägt** (fbcon.c 385–387),
   und neu aufgesetzt wird er nur durch Tastatur- oder Ausgabeaktivität auf tty1 — die es bei Bedienung über
   SSH nie gibt. Auf diesem Kernel hält jeder `printk` die Konsolensperre für die Dauer der UART-Ausgabe
   (8250 ist Legacy-Konsole; printk.c 2425), und beim Umschalten schreibt der Kernel Zeilen (B.2, Mechanismus
   belegt, Auslöser vermutet; Messvorschrift B.3 kommt ohne Tastatur aus).
3. **Steuerung.** Ein Daemon bleibt nötig — seit 0100 hängen die Firmware-Callbacks am ersten `open()`, jemand
   muss den Knoten halten (hdmirx 2685–2725). Vorschlag: `hy310-tv` + `hy310-tv ctl …` über einen
   UNIX-Socket; Bildregler gehen heute schon über V4L2 (0101), Status/Plane/Betriebsart sind Daemon-Sache;
   Videobereich, Bildmodus und der Farbwandler-Zustand brauchen je eine kleine Kernel-Ergänzung (C).
4. **Dienst.** Unit und Regel sind stimmig, aber nicht installiert; für den Autostart fehlen Lebenszyklus-Bindung
   an das Gerät (Template-Unit), ein Einzelinstanz-Riegel, die README-Installation und zwei Zeilen Härtung (D).

---

## A. Review `main.c`

### A.1 Was das Programm heute tut (belegt)

`capture_open()` sucht `/dev/videoN` über `/sys/class/video4linux/videoN/name` und bestätigt mit QUERYCAP
(202–281); `display_open_card()` sucht `cardN` über `drmGetVersion()->name` (450–488), `display_find_crtc()`
nimmt den ersten CRTC mit Modus (496–523), `display_find_plane()` die Overlay-Plane mit NV16 und Eigenschaft
`hdmi-ring` (530–568). `evaluate()` (945–1022) fragt `QUERY_DV_TIMINGS`, baut bei neuer Quellgeometrie den
Träger-Framebuffer neu (995–1005) und schaltet die Plane per Atomic-Commit an (`display_show`, 687–745) oder
aus (`display_hide`, 752–783). Die Schleife (1141–1174) hängt in `poll()` auf `POLLPRI` des Aufnahmeknotens,
einem signalfd und einem timerfd für die Ringbeobachtung (804–938).

### A.2 Fundstellen nach Schwere

| Nr | Schwere | Zeilen | Befund | Beleg | Vorschlag |
|---|---|---|---|---|---|
| **A1** | **hoch** | 350–361, 957–962 | `capture_signal()` gibt für `ENOLINK`, `ENOLCK` **und** `ENODATA` gleichermaßen 0 = „kein Signal" zurück; `evaluate()` meldet dann „kein Signal (Flip-Zeiger stehen)" und schaltet auf Konsole. Seit 0107 heißt `-ENOLCK` aber „**Wechsel in flight**": Record und INCAP widersprechen sich, oder INCAP hat noch keine plausible Geometrie (hdmirx 2261–2299, Kommentar 2211–2219). Der `SignalChange`-Callback kommt bei `Set Valid Signal`, die INCAP-Register schreibt die Firmware erst danach (S11-elog: `Set Valid Signal` → `WriteModules V_INCAP`). Fragt `hy310-tv` genau dazwischen, landet es auf der Konsole und wartet auf ein Ereignis, das nicht kommen muss. Dass es am Gerät trotzdem läuft, liegt daran, dass ein Wechsel ~3 Callbacks kostet (S11 „jeder Auflösungswechsel kostet ~3") — der letzte trifft meist nach dem INCAP-Schreiben ein. `ENODATA` kommt aus `QUERY_DV_TIMINGS` gar nicht (nur aus `G_EDID`, hdmirx 2456). | belegt (Code); Rennen am Gerät nicht provoziert = vermutet | `ENOLCK` gesondert behandeln: begrenzte Nachfrage-Serie (z. B. 5 × 200 ms, der timerfd ist schon da) mit Journalzeile „Timing noch nicht eingerastet (ENOLCK)"; erst danach Konsole. Sauberer im Kernel: Ereignis erst senden, wenn Record und INCAP übereinstimmen (C.3 Punkt 2). |
| **A2** | **hoch** | 1118–1129 | Die Startzeile „offen …" sagt: ein Auflösungswechsel erzeugt kein `SOURCE_CHANGE`, `QUERY_DV_TIMINGS` antworte aus einer Konstante. Beides ist überholt: die Timings kommen aus Flip-Zeigern, Firmware-Record und INCAP (hdmirx 2228–2305), die Callbacks kommen an (0100/0124), und acht Wechsel 1080p↔720p sind abgenommen (S11-Tabelle). Das Programm druckt bei jedem Start eine widerlegte Aussage ins Journal. | belegt | Zeile und Kommentar streichen; die verbleibende Grenze (Auflösungen, die die Firmware nicht einrastet, A8) ist eine andere Aussage. |
| **A3** | **hoch** | 1062, 1104–1109, 678–685 | Der erste Öffner des Primary-Knotens **wird beim `open()` Master** (drm_auth.c 317–330: `if (!dev->master) ret = drm_new_set_master(dev, file_priv);`). `struct display d = { .fd = -1 }` startet mit `master = false`, also tut `display_release_master()` an 1109 **nichts** (`if (!d->master) return;`). Folge: in Bereitschaft **ohne** Bild (kein Signal beim Start, abgelehnte Geometrie, `-n`) hält `hy310-tv` den Master, bis zum ersten `display_show()`. Solange scheitert alles still mit `-EBUSY`, was `drm_master_internal_acquire()` braucht: Konsolen-Blank/DPMS, `set_par` (z. B. `chvt`), Panning, Palette (B.1). Der Kommentar an 1104–1108 beschreibt die Absicht richtig, der Code tut sie nicht. | belegt | Nach `display_open_card()` unbedingt `drmDropMaster(fd)` (Fehler `EINVAL` ignorieren) oder `d.master = drmIsMaster(fd)` — libdrm 2.4.124 am Board hat es (`xf86drm.h:771`). |
| **A4** | mittel | 97–147, 804–938 | Die **Ringbeobachtung** (≈ 200 Zeilen mit Kommentar) misst seit 0121 nichts Verwertbares mehr: (a) die Freigabe der Capture nach dem Descriptor ist Kernelsache (hdmirx 1703–1836) und wird dort geloggt („Freigabe: Capture direkt freigegeben … nach N ms", 1784–1786; „Farbwandler: wieder BT.709 …", 1690–1692); (b) die Flip-Zeiger sind **kein** Maß mehr für „Capture schreibt": 0121-Commit: *„The wait used h713_hdmirx_signal_present(), which watches the AFBD flip pointers. Those move from the plane side too, so the driver reported 'the firmware released it' 12 ms after a republication while the capture enable was still clear and the wall stayed black."* Genau dieses Instrument benutzt `watch_sample()` bei laufender Plane; (c) die Kosten stimmen nicht: `QUERY_DV_TIMINGS` beobachtet bis **150 ms / 4 Flips** (hdmirx 1416–1417, 2239–2240), nicht 20–25 ms (136–138) — bei 200-ms-Raster bis 75 % Tastverhältnis; (d) der Warntext 924 verweist auf überholte Wege („Nachtplan A.5", „Die Freigabe gehoert in 0093/0094" — sie ist dort). | belegt | Beobachtung streichen. Die Kernel-Zeilen sind die Wahrheit über die Freigabe; wer sie im Journal des Programms sehen will, braucht ein Ereignis aus dem Kernel (C.3). |
| **A5** | mittel | 995–1005, 693 | Beim Geometriewechsel wird der Rückgabewert von `display_hide()` (997) ignoriert. Schlägt das Abschalten fehl, bleibt `d->on = true`, `display_destroy_fb()` entfernt den noch angezeigten FB (`drmModeRmFB` schaltet die Plane kernelseitig hart ab), der neue FB wird gebaut, und `display_show()` kehrt an 693 mit `if (d->on) return true;` **ohne Commit** zurück: Zustand „Bild an", Wand zeigt Konsole — genau die Lüge, die der Kommentar 747–751 ausschließen will. | belegt (Code), Fall selten | Rückgabewert prüfen, bei `false` abbrechen und die Geometrie beim nächsten Ereignis erneut versuchen. |
| **A6** | mittel | 244–250, 279 | Seit 0100 kann `open()` von `/dev/video1` mit `-EBUSY` scheitern, wenn die Routinentabelle im Shmem gerade umkämpft ist — der Treiber sagt selbst „Wiederholung ist gefahrlos" (hdmirx 2694–2704). `capture_open()` wertet einen fehlgeschlagenen `open()` ohne `-d` als „nicht unser Gerät" (`continue`) und endet mit „kein V4L2-Geraet …"; mit `-d` sofort `fail()`. Unter systemd rettet das der Restart (D3), von Hand nicht. | belegt | Bei `EBUSY`/`EAGAIN` 3–5 Wiederholungen mit 100 ms; erst dann aufgeben. |
| **A7** | mittel | 1090–1101, 244 | **Jedes** Öffnen ohne laufenden Daemon meldet die beiden Firmware-Callbacks an und beim Schließen wieder ab (hdmirx 2685–2725: `cb_users`); das schreibt in die Shmem-Routinentabelle unter SW-Spinlock 2, auf den der MIPS wartet (0100-Commit, Punkt 2). `hy310-tv -n` und jedes `v4l2-ctl` ohne Daemon tun das. Solange der Daemon läuft, ist ein zweiter Öffner harmlos (`!rx->cb_users` ist dann falsch). | belegt | Dokumentieren; für C folgt daraus: der Daemon **ist** der dauerhafte Halter, die Bedienung läuft über ihn oder neben ihm, aber nie ohne ihn. |
| **A8** | mittel | 355–360, 976–983 | Fehlerabbildung bei nicht einrastenden Auflösungen: `-ERANGE` (Timing außerhalb Cap, z. B. > 1080 Zeilen, hdmirx 2301–2302), `-EFAULT`/`-ENOMEM` (Record nicht lesbar, 1219–1239) werden nur generisch gewarnt und wie „kein Signal" behandelt — als Ergebnis richtig (Konsole), aber die Journalzeile nennt nicht, was los ist. Für 1600×900 / 1280×1024 / 1024×768 ist die Antwort je nach Zustand `ENOLINK` (Zeiger stehen oder Record `NONE`) oder `ENOLCK` (INCAP ohne Geometrie, dazu ratelimitiert „INCAP meldet keine Geometrie …", hdmirx 2267–2269). „detect timing failed" steht **nicht** im Kernel (grep leer) — vermutlich eine Firmware-elog-Zeile. Die Treiber-Prüfung 976–977 (Breite % 16, Höhe % 2, ≤ Panel) deckt sich mit `atomic_check` (afbd 851–867). | belegt | errno-Namen ins Journal; `ENOLCK` → A1; Statusausgabe mit Record-Feldern (C.2 `status`). |
| A9 | niedrig | 47–52, 283–295, 336–347, 866–884, 974, 1125 | Veraltete Kommentare: 47–52 (der `DQBUF`-Zweitmodus: EXPBUF gibt es weiterhin nicht, hdmirx 2603–2609, `io_modes = VB2_MMAP` 3081 — Aussage stimmt, „second mode" ist Zukunftsmusik); 283–295 und 866–884 („Re-arm über V4L2 nicht erreichbar" — der Kernel macht es seit 0099/0121 selbst; `S_INPUT(0)` ist seit dem Probe-Quellenwechsel hdmirx 3167 ein reiner Nullwechsel); 336–347 (Messung „20 ms" — heute 60 ms für `signal_present`, 150 ms/4 Flips für `QUERY`, drei Quellen); 974 („doku/91 Punkt 2" — dort steht „DE-Scaler offen", seit 0117/0120 gelöst, richtige Stelle ist doku/96 §6); 1125 („constant" — falsch, s. A2). | belegt | Bereinigen; Verweise auf doku/96 und die Treiberfunktionen. |
| A10 | niedrig | 1024–1041, 1149–1155 | `SIGHUP` beendet das Programm. Blockierte Signale werden auch bei `SIG_IGN` zugestellt (deshalb funktioniert signalfd), d. h. ein `nohup hy310-tv &` **ohne** `setsid` stirbt beim SSH-Logout; der Handoff nutzt zum Glück `setsid`. | belegt | `SIGHUP` = Neubewertung/Reload (`evaluate()`), nicht Ende; Unit bekommt `ExecReload`. |
| A11 | niedrig | 235–278 | `capture_open()` mit `want_path` durchläuft die 64er-Schleife nur formal (erste Iteration endet in `return` oder `fail`). Funktioniert, liest sich aber als Suche, obwohl es keine ist. | belegt | Zwei Funktionen: `capture_open_path()` / `capture_find()`. |
| A12 | niedrig | 153–186 | Keine Zeitstempel (beim Handstart in eine Datei fehlen sie ganz), keine Stufen. Korrelation mit `dmesg` geht nur über Uhrenvergleich. | belegt | `CLOCK_MONOTONIC`- oder Wanduhr-Präfix, `-v`, `ctl log N` (C). |
| A13 | niedrig | README | README nennt eine Option `-s SAETTIGUNG` und die Plane-Eigenschaft `saturation` (README 82, 206–211) — beides seit 0104 weg, `usage()` (1043–1056) kennt kein `-s`; „noch nie am Gerät gelaufen" (8), „1168 Zeilen" (90), §8 „Eine Quellgeometrie pro Boot" und „Auflösungswechsel wird NICHT bemerkt" (340–359) sind überholt; §7 „Stolperstelle" macht der Kernel (0121–0123); §3 Master-Aussage ist nur halb richtig (B.1). Nebenbefund Kernel: afbd 238–239 und 1134 nennen ebenfalls noch `saturation`. | belegt | README auf Stand S11/S12 bringen; afbd-Kommentar bei der nächsten Patch-Runde. |
| A14 | niedrig | 296–303, 1111 | `S_INPUT(0)` beim Start ist ein `SetSource(3)` (hdmirx 2408–2416, 951–956), seit dem Quellenwechsel im Probe (3167) immer ein Nullwechsel. Schadet nicht, nützt nichts, ist eine RPC pro Start. | belegt | Streichen oder Kommentar auf „redundant seit 0099" ändern. |

**Was in Ordnung ist (belegt):** die QUERYCAP-Trunkierung 252–267 ist korrekt begründet; `props_get()`/`prop_id()` halten `NULL` aus; `display_show()` gibt den Master in jedem Fehlerpfad zurück (723, 736); Atomic-Commits laufen nur bei Übergängen (693, 758); `poll()` mit `POLLPRI` auf `vb2_fop_poll` (hdmirx 2740) ist richtig und im Betrieb bewiesen (S11: Konsolen-Rückfall und Wiederkehr); der Ausstieg (1181–1189) nimmt denselben Weg wie ein Signalverlust; ein Absturz oder `SIGKILL` lässt **kein** Standbild stehen, weil das letzte `close()` des Karten-fd `drm_lastclose()` → `drm_client_dev_restore()` auslöst (drm_file.c 406–408, 438–442) und der fbdev-Restore alle Nicht-Primary-Planes abschaltet — sofern kein zweiter DRM-Client die Karte offen hält.

### A.3 Robustheit je Szenario

| Szenario | Ablauf heute | Bewertung |
|---|---|---|
| Kabel ziehen | Firmware `SignalChange` → `SOURCE_CHANGE` (hdmirx 1147–1166) → `QUERY` = `ENOLINK` → Konsole | belegt (S11: „Konsolen-Rückfall … funktionieren") |
| Kabel zurück / Quelle an | Callback(s) → `QUERY` = ok **oder** `ENOLCK` (A1) → Bild bzw. Konsole bis zum nächsten Callback | A1 |
| 1080p ↔ 720p | `display_hide` → FB neu → `display_show` → Republish (afbd 429–460, nur im `!video_active`-Zweig 919–939) → Kernel-Freigabe | belegt (S11). Die Konsole **blitzt** dabei auf, weil die Plane aus muss, damit der Treiber neu veröffentlicht — vermeidbar per Kernel (C.3 Punkt 5). |
| 1600×900, 1280×1024, 1024×768 | Firmware rastet nicht ein → `ENOLINK`/`ENOLCK` → Konsole, Journal „kein Signal (Flip-Zeiger stehen)" auch dann, wenn sie laufen | A8 |
| 1366×768 | 976–979 lehnt ab (Breite % 16) → Konsole mit Warnung; die Plane würde es ebenso ablehnen (afbd 851–867) | richtig |
| > 1080 Zeilen | `ERANGE` → generische Warnung → Konsole | A8 |
| Daemon stirbt | letztes `close()` → fbdev-Restore → Konsole | belegt (Code) |
| zweiter KMS-Client | bei stehendem Bild `EACCES` (README §8, gemessen H-Abnahme); in Bereitschaft **heute ebenfalls** blockiert bis zum ersten Bild | A3 |
| zwei Instanzen | zweite öffnet, `SET_MASTER` scheitert mit `EBUSY` (669–671), beide reagieren auf Ereignisse | flattert; Einzelinstanz-Riegel fehlt (D9) |

---

## B. Die Konsole zurück: Master, fd, Cursor

### B.1 Wie die Kette wirklich ist (belegt)

* **fbdev des afbd:** `drm_client_setup(drm, NULL)` (afbd 1911) mit `DRM_FBDEV_DMA_DRIVER_OPS` (1555);
  `mode_config.funcs.fb_create = drm_gem_fb_create` **ohne** `dirty` (1543–1547). `drm_fbdev_dma.c` 314–317
  wählt deshalb den Pfad **ohne Schattenpuffer**: `info->screen_buffer` zeigt direkt auf den DMA-Scanout-Puffer,
  die Zeichen-Ops sind `sys_fillrect/copyarea/imageblit` ohne Damage-Aufruf. **fbcon schreibt Text und Cursor
  unmittelbar in den Speicher, den die Hardware abtastet** — auch während das Video steht.
* **Master wird nur hier geprüft** (`drm_master_internal_acquire`, drm_auth.c 433–442 — prüft allein
  `dev->master != NULL`): `drm_fb_helper.c` 1029 (`setcmap`), 1069 (`FBIO_WAITFORVSYNC`), 1435 (`pan_display`),
  1943 (Hotplug → aufgeschoben); und in `drm_client_modeset_commit()` / `drm_client_modeset_dpms()`
  (drm_client_modeset.c 1225–1232, 1276–1295), die hinter `set_par` (nicht-force) und `blank`/DPMS stehen.
  **Nicht** geprüft: `damage_work`/`fb_dirty`/`damage()` (drm_fb_helper.c 397–402, 361–395, 619–636). Die
  README-Aussage „solange ein Userspace-Master existiert, malt der Konsolen-Client nicht mehr" ist damit für
  *Text und Cursor* falsch und nur für *Modeset, Blank, Pan, Palette* richtig.
* **`drmDropMaster`** setzt nur `dev->master = NULL` (drm_auth.c 280–286, 288–315). **Kein** Restore, kein
  Hotplug-Replay. `drm_client_dev_restore()` läuft ausschließlich aus `drm_lastclose()` (drm_file.c 406–408),
  und das nur bei `open_count == 0` (438–442). Ein offener fd verhindert den Restore dauerhaft — braucht ihn
  aber auch nicht, solange Primary-Plane und CRTC unangetastet bleiben, und das tut `hy310-tv` (es setzt nie
  einen Modus, 490–495).
* **Video aus** (`h713_afbd_video_stop`, afbd 731–787): Source 0 auf Ruhewert, Adressen 0, C-Stride zurück,
  **RGB-Kanal an** (`AFBD_CTRL = rgb_ctrl_active`, `AFBD_READY = 1`, 781–784), **Selektor zurück** (785). Der
  Latch nimmt den aktuellen `AFBD_SRC`, den `set_source()` auch bei aktivem Video nachführt (713–719). Die
  Konsole ist danach sofort sichtbar und **inhaltlich aktuell**, weil fbcon die ganze Zeit in denselben Puffer
  geschrieben hat. Die Abnahme-dmesg enthält 0 × „READY did not clear".
* **Der Treiber blankt nie:** `pipe_disable` schaltet nur die Vblanks ab und lässt das letzte Bild stehen
  (afbd 1419–1427, mit Begründung). Ein DPMS-Blank sieht auf diesem Board also aus wie „Konsole steht,
  Cursor aus" — merken für B.2.

**Folgerung für `hy310-tv`:** „Plane aus, dann Master weg, fd offen halten" ist die richtige Reihenfolge und
reicht. `drmModeSetCrtc` auf die Konsolen-FB ist unnötig (und ohne Master `EACCES`); `FBIOPUT_VSCREENINFO`
hilft nur über den `FB_ACTIVATE_KD_TEXT|FORCE`-Pfad (`drm_fb_helper_set_par`, drm_fb_helper.c 1326–1357), den
X-Server beim VT-Wechsel benutzen — zu grob für den Normalfall. Das Einzige, was **wirklich** fehlt, ist A3:
in Bereitschaft ohne Bild hält das Programm heute den Master und sperrt damit Blank, `set_par`, Pan, Palette.

### B.2 Warum der Cursor trotzdem stehen bleibt

**Mechanismus (belegt).** Das Blinken ist die `delayed_work` `fb_flashcursor()` (fbcon.c 372–410). Sie setzt
sich am Ende selbst neu auf (407–409) — **außer** in zwei frühen Rücksprüngen: `console_trylock()` schlägt
fehl (385–387, mit dem Kommentar *„we just fail to flash the cursor if we can't get the lock"*), oder die
Konsole ist nicht sichtbar/`vc_deccm != 1` (395–400). Danach ist der Timer **tot**, bis jemand
`fbcon_add_cursor_work()` (412–419) ruft — und das geschieht nur über `fbcon_cursor()` (1336–1356), also aus
der VT-Schicht bei **Aktivität auf dieser Konsole** (`set_cursor()`, vt.c 859–871: bei `console_blanked`
oder `KD_GRAPHICS` gar nicht). Wer den Beamer über SSH bedient, erzeugt auf tty1 nie Aktivität; das getty
wartet. Ein einmal ausgefallener Blink bleibt aus.

**Auslöser (vermutet, mit Beleg für die Vorbedingung).** Wer hält beim Umschalten die Konsolensperre?
`printk`: die 8250-Konsole ist in diesem Baum eine **Legacy-Konsole** (kein `CON_NBCON` unter
`drivers/tty/serial/8250/`), `console=ttyS0,115200` (doku/95). Jeder `printk` läuft dann über
`console_trylock_spinning()` / `console_unlock()` (printk.c 2425–2426) und hält die Sperre, **während die
Zeile über die UART geht** — 115200 Bd ≈ 9 ms je 100 Zeichen. Beim Plane-Enable schreibt `hdmirx` mindestens
„Farbwandler: wieder BT.709 …" (1690–1692) und „Freigabe: Capture direkt freigegeben …" (1784–1786); mit dem
elog-Relais auf Stufe 5 sind es hunderte Zeilen. Blink-Takt `HZ/5` = 200 ms. Trifft der Blink-Work eine
gehaltene Sperre — pro Zeile ≈ 5 %, pro Umschaltung zweistellig, mit elog praktisch sicher —, ist er tot. Ob
der Cursor dann *steht* oder *fehlt*, hängt von der Phase ab, in der er starb (`cursor_state.enable`, 402).

**Zweiter Kandidat (unwahrscheinlich, aber genau der Pfad, den A3 scharf macht).** Ein Blank bei gehaltenem
Master: `fbcon_blank()` (fbcon.c 2247–2263) setzt `blank_state`, löscht den Cursor-Work, ruft `fb_blank()`;
`drm_fb_helper_blank()` gibt **immer 0** zurück und `drm_fb_helper_dpms()` (306–313) **verwirft** das
`-EBUSY` von `drm_client_modeset_dpms()` → kein `fbcon_generic_blank()`, Hardware ungeblankt, aber
`console_blanked` gesetzt (vt.c 4656–4658) → keine Ausgabe mehr (`con_should_update`, 284–287), Cursor aus,
entblankt **nur** durch Tastatur (`keyboard.c` 1539 → `poke_blanked_console`) oder die Escape-Sequenz
`\e[13]` (vt.c 2116–2118). Voraussetzung ist ein Blank-Auslöser: `consoleblank` ist per Default 0
(vt.c 180–181), die Bootargs setzen es nicht, im Root gibt es kein `/etc/kbd/config` und kein `setterm` →
heute kein automatisches Blank. Wenn jemals eines kommt (z. B. `setterm -blank`), tritt mit A3 genau dieser
eingefrorene Zustand auch in **Bereitschaft** ein, nicht nur bei stehendem Bild.

**Dritter Kandidat:** `vc_deccm = 0` — ein Programm hat auf tty1 `\e[?25l` geschrieben. Nur, falls dort je
etwas lief.

### B.3 Messvorschrift (per SSH, ohne Tastatur am Beamer)

1. Vorbedingungen: `cat /sys/class/graphics/fbcon/cursor_blink` (soll 1), `cat
   /sys/module/kernel/parameters/consoleblank` (soll 0), `cat /sys/class/tty/tty0/active` (soll tty1).
2. Zustand herstellen: Bild an → Quelle weg → Konsole zurück, Cursor steht. Dann
   `echo "S12 $(date +%T)" > /dev/tty1`. **Text erscheint und der Cursor blinkt danach** → der Timer war tot
   (B.2, erster Kandidat). **Text ja, Cursor nein** → `vc_deccm`/`cursor_blink`: `printf '\033[?25h' >
   /dev/tty1`. **Weder noch** → geblankt oder Scanout: weiter mit 3.
3. `python3 -c 'import fcntl,os; fd=os.open("/dev/tty0",os.O_RDWR);
   print(fcntl.ioctl(fd,0x541C,bytes([11])))'` (`TIOCL_BLANKEDSCREEN`, vt.c 3572: 0 = nicht geblankt,
   sonst Nummer der geblankten Konsole); `printf '\033[13]' > /dev/tty1` entblankt ohne Tastatur.
4. Gegenprobe ohne `hy310-tv`: elog auf Stufe 5 (viel `printk`), zehn Minuten warten — bleibt der Cursor
   stehen, ist es `printk`/fbcon, nicht das Umschalten.
5. `dmesg | grep -c "READY did not clear"` (soll 0).

### B.4 Was `hy310-tv` tun sollte

1. **A3 beheben** — der einzige echte Fehler auf der DRM-Seite.
2. **Am fd nichts ändern.** Offen halten ist korrekt. Optional als Gürtel und Hosenträger: in Bereitschaft
   den Karten-fd schließen — `drm_lastclose()` stellt dann den KMS-Zustand der Konsole in jedem Fall wieder
   her, auch nach einem fehlgeschlagenen `display_hide()` (A5); Kosten: ein `open()` beim nächsten Signal,
   gefolgt von sofortigem `drmDropMaster`. Für den Cursor bringt das nichts.
3. **Der Cursor ist ein fbcon-Thema, kein DRM-Thema.** Der kleinste saubere Fix ist ein Kernel-Patch von drei
   Zeilen in `fb_flashcursor()`: bei `console_trylock() == 0` den Work neu einreihen statt zurückzukehren
   (upstream-fähig; das FIXME steht seit Jahren dort). Ein Workaround im Programm (nach `display_hide()`
   `\e[?25h` oder `TIOCL_UNBLANKSCREEN` auf `/dev/tty0`) ginge, ist aber genau die Art Umgehung, die das Projekt
   nicht baut, solange die Ursache greifbar ist — erst messen (B.3), dann patchen.
4. Flankierend: die `printk`-Last beim Umschalten senken (elog nicht auf Stufe 5 relayen, `loglevel`); das
   senkt nur die Wahrscheinlichkeit.

---

## C. Konzept „alles vom Userspace steuern"

### C.1 Rollen und Form

**Kernel = Mechanik, `hy310-tv` = Politik und Bedienung.** Das passt zu doku/77 (keine Firmware-RPCs aus dem
Userspace im Betrieb; `/sys/kernel/debug/cpu_comm/call` bleibt Prüfstand). Ein **Daemon bleibt nötig**, aus
drei Gründen, alle belegt: (1) die Firmware-Callbacks hängen am ersten `open()` und fallen beim letzten
`close()` (hdmirx 2685–2725; doku/96 §8 „ohne laufenden Player kommen keine Firmware-Ereignisse an");
(2) Plane- und Master-Zustand gehören einem Prozess; (3) die Zustandsmaschine ist ereignisgetrieben.

**Form:** dasselbe Binary in zwei Betriebsarten — `hy310-tv` (Daemon, wie heute) und `hy310-tv ctl <befehl>`
(Client). Verbindung: UNIX-Socket `/run/hy310-tv/sock`, `SOCK_SEQPACKET`, Text: eine Zeile Befehl, Antwort als
`schlüssel=wert`-Zeilen, Abschluss `ok` oder `fehler <text>`. Rechte `0660 root:video`. Im Daemon ein vierter
`pollfd` (Listen-Socket) plus ein fd je Client; keine Threads, keine Warteschleifen. Alternativ ohne Daemon
geht nur, was V4L2 heute schon kann (Regler), und das kostet bei jedem Aufruf ein An-/Abmelden der Callbacks
(A7) — deshalb nicht.

### C.2 Befehlsumfang

| Befehl | Liefert / tut | Weg heute | Kernel-Ergänzung | Aufwand |
|---|---|---|---|---|
| `status` | `signal=` vorhanden / keins (`ENOLINK`) / nicht eingerastet (`ENOLCK`) / außerhalb (`ERANGE`); `timings=WxHp`, `fps=` (aus `pixelclock/(htotal·vtotal)`, hdmirx 2293–2295), `interlaced=`; `plane=an/aus`, `plane_id=`, `crtc=`, `fb=WxH`; `master=`; `mode=auto/console/picture`; `input=`; die neun Regler (`G_EXT_CTRLS`); `icsc=bt709/bypass` (Bit 31 von `0x06940824`, **nur lesend**); `cpu_comm=` die `eingehend …`-Zeile aus `/sys/kernel/debug/cpu_comm/watch`; `events=` Zähler und Zeit des letzten `SOURCE_CHANGE`; `status -v` hängt `/sys/kernel/debug/sun50i-h713-hdmirx/status` an (Record-Felder `signal_id`, `h_size`, `v_size`, `frame_rate_x100`, Callback-Zähler; Achtung: das Lesen blockiert 60 ms, hdmirx 2802). | V4L2 + debugfs (root) | **`icsc`:** die Treiberfunktion `h713_hdmirx_icsc_bypassed()` existiert (hdmirx 1619–1627); eine Zeile im debugfs-`status` genügt; schöner als Read-only-Volatile-Control `V4L2_CID_H713_COLOR_CONVERTER` (0/1). ≈ 20 Zeilen. | Daemon: 1 Tag; Kernel: 1 h |
| `show` / `hide` / `auto` | Betriebsart-Vorgabe über die Zustandsmaschine legen | — | keine | klein |
| `get <regler>` / `set <regler> <wert>` | `brightness contrast saturation hue sharpness` 0..100; `tnr snr dci black-extension` 0..3 (Menü Off/Low/Middle/High) | V4L2-Controls aus 0101 (hdmirx 636–697, IDs 547–555, `s_ctrl` 1035–1048: sofort per RPC, keine Umrechnung, **kein** Rücklesen); `v4l2-ctl -d /dev/video1 --set-ctrl=…` geht heute schon | keine; Hinweis: nach einem firmware-seitigen Preset (`SetPictureMode`) stimmen die Control-Werte nicht mehr (0101-Kommentar 523–528) | klein |
| `range auto\|limited\|full` | `THal_Vp_SetVideoRange 0/1/2` | nur debugfs-RPC; intern nutzt 0123 `2 → 0` als Trick (hdmirx 1674–1679) | privates Menü-Control `V4L2_CID_H713_VIDEO_RANGE`. Offen: Bedeutung von 1 ist ungemessen (0101-Kommentar 530–535 nennt genau das als Grund fürs Weglassen); jeder **geänderte** Wert lässt die Firmware den Farbpfad neu bewerten (S11) — `s_ctrl` muss danach `restore_icsc`-Kontrolle fahren. ≈ 40 Zeilen | klein + Messung am Ring (`ringstat.py`) |
| `picmode <name>` | `THal_Vp_SetPictureMode n` (Init setzt 1, hdmirx 404–407) | nur debugfs-RPC | Menü-Control `V4L2_CID_H713_PICTURE_MODE`, Namen aus `pq_picturemode.ini` (`hy310-pq list`). Preset überschreibt die fünf Regler in der Firmware → danach per Get-Routinen (existieren, 0101-Commit) zurücklesen und mit `__v4l2_ctrl_s_ctrl` nachziehen, oder die neun Regler `VOLATILE` machen. ≈ 80 Zeilen | mittel + Messung |
| `source <name>` | Firmware-Quelle setzen | `S_INPUT 0` = `SetSource(3)` (hdmirx 2408–2416); debugfs `THal_Vp_SetSource n` **umgeht** den Treiber und löst einen zweiten, fehlerhaften Neubau aus (0119, S11) — nicht im Betrieb | weitere Inputs in `ENUM_INPUT`/`S_INPUT` (IDs: 3 HDMI-1, 1 VideoDec, Rest RE); für den HY310 mit einem HDMI-Eingang geringer Nutzen | mittel, nachrangig |
| `replug` | HPD-Zyklus (Quelle neu verhandeln, z. B. bei einem Modus, der nicht einrastet) | `VIDIOC_S_EDID` mit `blocks = 0` zieht HPD nach unten (hdmirx 2477–2480), `S_EDID` mit EDID setzt ihn (2489); 0,3 s genügen (M4) | keine | klein |
| `edid get\|set <datei>` | 512 B lesen/schreiben | `G_EDID`/`S_EDID` (hdmirx 2426–2497) | keine | klein |
| `log <0..3>` / `events` | Stufe zur Laufzeit; `events` streamt Zustandswechsel an den Client | — | keine | klein |
| *nicht anbieten* | rohe RPCs (`call …`) | bleibt `debugfs`/`hdmi_seq.py` (Sperrliste, doku/83 §4) | — | — |

### C.3 Kleine Kernel-Ergänzungen, die das Konzept vollständig machen

1. **Farbwandler-Zustand lesbar** (debugfs-Zeile oder RO-Control) — 20 Zeilen, ½ h Bau.
2. **`ENOLCK`-Rennen im Treiber schließen**: `SOURCE_CHANGE` erst senden, wenn Record und INCAP übereinstimmen
   (kurze Nachprüfung in einer Work statt direkt im Callback), oder ein zweites Ereignis, sobald sie es tun —
   30 Zeilen; macht A1 im Userspace überflüssig.
3. **Video-Range-Control** — 40 Zeilen + Messung (Wert 1 am Ring prüfen).
4. **Picture-Mode-Control mit Rücklesen** — 80 Zeilen + Messung.
5. **Republish ohne Plane-Aus**: `h713_afbd_publish_video_info()` läuft heute nur im `!video_active`-Zweig
   (afbd 919–939); bei Geometriewechsel im aktiven Zustand ebenfalls veröffentlichen, dann entfällt das
   Konsolenblitzen beim Auflösungswechsel — 30 Zeilen + Abnahme (WCE-Wartezeit bis 1 s im Commit bleibt).
6. **fbcon-Trylock-Fix** (B.4) — 3 Zeilen, upstream.
7. Optional: weitere Inputs (RE der Quellen-IDs).

**Aufwand gesamt:** Socket + `ctl` mit `status/show/hide/auto/get/set/replug/log` ≈ 300–400 Zeilen C,
1–2 Tage einschließlich Test am Gerät; Kernel-Punkte 1, 2, 6 je ½ Tag mit Bau und Abnahme; 3–5 je 1 Tag.

---

## D. Dienst und Installation

| Nr | Befund | Beleg | Vorschlag |
|---|---|---|---|
| D1 | Nichts installiert: im NFS-Root fehlen `/etc/systemd/system/hy310-tv.service`, `/etc/udev/rules.d/99-hy310-tv.rules`, `/usr/local/sbin/hy310-tv`; Betrieb per Handstart `/root/hy310-tv` (doku/97 §1). `make install-cross` scheitert vom Host an Rechten (S11). | geprüft 08.09. | Vom Board aus installieren (`scp` + `install -m 0755`), danach `systemctl daemon-reload; udevadm control --reload; udevadm trigger -c add -s video4linux` — letzteres startet die Unit sofort, ohne Neustart. |
| D2 | Die udev-Regel ist stimmig (`ATTR{name}` = `video_device.name`, `TAG+="systemd"`, `SYSTEMD_WANTS`), greift auch beim Coldplug. Aber der **Lebenszyklus ist nicht gebunden**: verschwindet `/dev/video1` (rebind, rmmod), läuft die Unit bis `POLLERR` (1157–1162), endet mit rc 1, wird 3 × in 60 s neu gestartet, bleibt „failed"; beim Wiedererscheinen startet udev sie erst nach Ablauf des Intervalls neu. | belegt | Template-Unit: `ENV{SYSTEMD_WANTS}+="hy310-tv@%k.service"` in der Regel; `hy310-tv@.service` mit `BindsTo=dev-%i.device`, `After=dev-%i.device`, `ExecStart=/usr/local/sbin/hy310-tv -d /dev/%i`. Dann folgt die Unit dem Gerät in beide Richtungen. |
| D3 | `Type=exec` (systemd 257 am Board), `Restart=on-failure`, `RestartSec=5s`, `StartLimitBurst=3/60s`: sinnvoll. Ein `EBUSY`-`open()` (A6) wird heute nur vom Restart gerettet. | belegt | Wiederholung ins Programm (A6); Unit so lassen. |
| D4 | `Documentation=file:/usr/local/share/doc/hy310-tv/README.md` — das Makefile installiert die README nicht (`install-data`, Makefile 60–62). | belegt | README in `install-data` aufnehmen oder Zeile streichen. |
| D5 | Härtung: `ProtectSystem=strict` lässt `/dev`, `/proc`, `/sys` (und damit debugfs) schreib-/lesbar, `ProtectKernelTunables` ist nicht gesetzt — `status` über debugfs geht. Für den Socket aus C fehlt `RuntimeDirectory=hy310-tv` (sonst ist `/run` read-only). `DeviceAllow` fehlt ganz. | belegt | `RuntimeDirectory=hy310-tv`, `DeviceAllow=char-drm rw`, `DeviceAllow=char-video4linux rw`, `SyslogIdentifier=hy310-tv`. |
| D6 | Reihenfolge zur Anzeige: `display_find_crtc()` braucht einen CRTC mit Modus (520–521). Die Unit startet frühestens mit `/dev/video1`, also ≥ 17 s nach dem Kaltstart (EDID/HPD-Sequenz, doku/88 §0) — die Konsole steht dann längst. | belegt | keine Änderung. |
| D7 | Umgebungsvariablen: keine mehr (`H713_TV_SKALIERTEST` gestrichen). | belegt | Für C: `-v`/`ctl log N` statt Umgebung. |
| D8 | `KillSignal=SIGTERM`, `TimeoutStopSec=10s`: das Abschalten dauert Millisekunden; passt. `ExecReload` fehlt (nach A10: `ExecReload=/bin/kill -HUP $MAINPID`). | belegt | ergänzen. |
| D9 | **Einzelinstanz-Riegel fehlt.** Läuft der Handstart weiter, während die Unit startet, reagieren zwei Prozesse auf dieselben Ereignisse; die zweite bekommt `SET_MASTER: EBUSY` und bleibt in Bereitschaft, beim nächsten Ereignis kann es kippen. | belegt (Code 664–676) | Socket-Bind (C) oder `flock` auf `/run/hy310-tv/lock` als Riegel; Handstart aus dem Ablauf nehmen. |

---

## E. „So würde ich es umbauen" — priorisiert

| Prio | Was | Umfang | Aufwand |
|---|---|---|---|
| 1 | **A3:** Master direkt nach `display_open_card()` abgeben (`drmDropMaster` oder `drmIsMaster`) | 2 Zeilen | sofort |
| 2 | **A1/A8:** `ENOLCK` gesondert (Nachfrage-Serie über den vorhandenen timerfd, richtige Journalzeile, errno-Namen) | ≈ 40 Zeilen | ½ Tag inkl. Test: Kabel ziehen/stecken, Wechsel 1080p↔720p, 1024×768 |
| 3 | **A2/A4/A9/A13/A14:** Startzeile „offen" weg, Ringbeobachtung weg, Kommentare und README auf S11/S12-Stand, `S_INPUT` streichen | netto ≈ −200 Zeilen | 2 h |
| 4 | **A5/A6/A10:** Rückgabewert von `display_hide()`, `open()`-Wiederholung, `SIGHUP` = Neubewertung | ≈ 30 Zeilen | 2 h |
| 5 | **D2/D4/D5/D8/D9:** Template-Unit, README-Installation, `RuntimeDirectory`/`DeviceAllow`, `ExecReload`, Einzelinstanz-Riegel; Installation vom Board aus; Kaltstart **ohne** Handstart als Abnahme | Unit + Regel | 1 h + Abnahme |
| 6 | **C:** Socket + `ctl` mit `status/show/hide/auto/get/set/replug/edid/log/events`; Zeitstempel im Log | 300–400 Zeilen | 1–2 Tage |
| 7 | **Kernel klein:** ICSC-Bit lesbar; `ENOLCK`-Rennen im Treiber; fbcon-Trylock-Fix (nach B.3-Messung) | 3 × ≤ 30 Zeilen | je ½ Tag |
| 8 | **Kernel mittel:** Video-Range- und Picture-Mode-Controls, mit Ring-Messung | ≈ 120 Zeilen | 1–2 Tage |
| 9 | **Kernel optional:** Republish ohne Plane-Aus (kein Konsolenblitzen); weitere Inputs | ≈ 30 Zeilen + RE | 1 Tag |

**Nicht geprüft (kein Board):** das Laufzeitlog `/root/hy310-tv.out` (Rechte), die tatsächliche Häufigkeit des
`ENOLCK`-Falls, und ob der Cursor nach `echo … > /dev/tty1` wieder blinkt — das ist der erste Schritt von B.3.

---

## Umsetzung (Hauptsitzung, 08.09.2026, 01:45–02:00)

Aus diesem Bericht ist am selben Abend geworden:

| Fundstelle | Umsetzung |
|---|---|
| A1 impliziter DRM-Master nie abgegeben | `drmDropMaster()` direkt nach dem Öffnen der Karte; `master n` in der Konsole nachgemessen (`/sys/kernel/debug/dri/1/clients`) |
| A2 `-ENOLCK` als „kein Signal" | `capture_signal()` liefert 2 = „Wechsel im Gang"; `evaluate()` fragt über einen Einmal-Timer alle 50 ms nach, höchstens 2 s, und lässt die Wand in Ruhe (`struct retry`); nach Ablauf der Frist bleibt der aktuelle Zustand stehen (die erste Fassung ging auf die Konsole — zehn Sekunden Konsole bei korrektem Bild, S11 Abnahme 2) |
| A3 Startzeile „offen …" | entfernt |
| A4 Ringbeobachtung (~200 Zeilen) | entfernt; der Timer dient jetzt der ENOLCK-Wiederholung |
| A5 ignorierter `display_hide()`-Rückgabewert | geprüft, Abbruch bei Fehlschlag |
| A6 `open()` bei `EBUSY` | bis zu 20 × 100 ms wiederholt |
| A7 `SIGHUP` als Ende | `SIGHUP` bewertet den Zustand neu, beendet nicht |
| B Konsolen-Cursor | zweigleisig: `console_restore()` in `hy310-tv` (TIOCL_UNBLANKSCREEN, `ESC[?25h`, Blank-Timer 0, `fb0/blank` = 0) beim Start und bei jeder Rückgabe **und** Kernel-Patch `0127` (fbcon: `fb_flashcursor` reiht sich bei fehlgeschlagenem `console_trylock` neu ein). Gemessen: nach `hy310-tv ctl off` wechselt der Framebuffer-Hash im 0,45-s-Takt |
| C Steuerschnittstelle | `hy310-tv ctl …` über `/run/hy310-tv/ctl` (status, auto, off, console, list, get, set, resync, rpc, help); Kernel `0126`: `video_range` (Auto/Limited/Full) und `picture_mode` (0…7) als V4L2-Controls, `capture`/`farbwandler`-Zeilen im debugfs-Status; `0123` toggelt den Bereich jetzt um den eingestellten Wert |
| D Dienst | `RuntimeDirectory=hy310-tv`, Einzelinstanz-Riegel (`flock` auf `/run/hy310-tv/lock`), README nach `/usr/local/share/doc/hy310-tv/`; Unit + udev-Regel am Board installiert, Autostart nach Kaltstart per udev **bestätigt** (`Started hy310-tv.service` bei 19 s). Template-Unit mit `BindsTo` und `replug` (S_EDID blocks=0) bleiben offen |

Nicht umgesetzt: `replug`, Template-Unit, die Log-/Event-Befehle aus C.

**Neu gefunden durch den Autostart (und mit `0128` behoben):** startet `hy310-tv` bei 19 s, fällt die
Erstveröffentlichung in die HDMI-Neuverhandlung nach dem HPD; der Quellenwechsel des Treibers endet
ohne Signal („nach 2000 ms bewegen sich die Flip-Zeiger nicht"), und danach bleibt die Capture aus,
obwohl INCAP längst wieder 1920×1080 eingerastet hat (MemoryAgent bleibt „disable"). Ein Quellenwechsel
von Hand holt alles zurück. `0128` merkt sich den Fehlschlag und wiederholt den Wechsel, sobald der
`SignalChange`-Callback die HDMI-Quelle mit gültigem Signal meldet.

---

## Umsetzung 2 — Zweit-Review des fertigen Codes (08:10–08:25)

Ein zweiter Review-Durchgang (Agent, gegen den Endstand mit Steuerkanal) fand drei Fehler und eine Reihe
Robustheitspunkte; alle sind umgesetzt und am Gerät geprüft:

| Fund | Umsetzung | Prüfung |
|---|---|---|
| F1 SIGPIPE tötet den Daemon, wenn ein Client vor der Antwort auflegt | `signal(SIGPIPE, SIG_IGN)`, `send(…, MSG_NOSIGNAL)` | drei Clients senden und schließen ohne zu lesen → Dienst bleibt `active` |
| F2 Einzelinstanz-Riegel griff erst nach `capture_open`, `drmDropMaster`, `S_INPUT` | `control_lock()` als erstes nach der Optionsauswertung, `fail` ohne Riegel | zweite Instanz scheitert sofort, 0 neue Journalzeilen des Dienstes |
| F3 README nannte `-s SAETTIGUNG` | §6 neu, §7/§8 neu geschrieben (Ringbeobachtung raus, ENOLCK-Pfad rein), §6a ergänzt | — |
| R1 `client()`-Zeilenaufbau | Längenprüfung mit Abbruch statt `strcat` | — |
| R2 Hauptschleife blockierbar | eine Gesamtfrist von 500 ms je Client, `POLLOUT` bei `EAGAIN` | — |
| R4/R5 Nachfrage-Timer | `retry_stop` sobald ein Ergebnis da ist; nach der Frist bei Konsole alle 500 ms weiterfragen; Warnung zählt Nachfragen | — |
| R6 `-n` bei ENOLCK | „Wechsel im Gang", Rückgabe 1 | — |
| R7 `status` misst | berichtet die letzte Messung aus `evaluate()` („zuletzt gemessen") | ✓ |
| R8 `rpc` | Längenprüfung (158 Zeichen), `-> error`, Zeilenende | `rpc THal_Vp_GetSource` ✓ |
| R9 fehlende Argumente | eigene Meldung | `set foo` → „braucht Argumente" ✓ |
| R10 Pfadlängen | geprüft | — |
| R11 Unit | `ExecReload=/bin/kill -HUP $MAINPID`, Kommentar zu `ProtectKernelTunables` | `systemctl reload` ✓ |
| R12 INTEGER64 | `value64` | — |
| R13 Format-Attribute | `__attribute__((format(printf …)))` auf allen fünf | baut ohne Warnung |

Dazu Kernel `0129`: `QUERY_DV_TIMINGS` nimmt die Bildrate nicht mehr aus unserem eigenen VidDec-Datensatz
(yuv420_888, 30.00 Hz), sondern misst sie am Ring — nach einem Wechsel meldet `status` jetzt 148 500 000 Hz
für 1080p und 74 250 000 Hz für 720p (beides 60-Hz-Presets), während der Firmware-Datensatz weiter 30.00
sagt. Endstand: Serie 98, Baum `e2f6be7c`, `hy310-tv` md5 `3290f74d…`.
