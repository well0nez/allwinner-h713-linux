# Paket F - `RING_SETTLE_MS` raus, Ringbeobachtung rein (offline, 07.09. ab 08:4x)

**Agent:** Unteragent F-korrektur (offline). **Kein Board angefasst:** kein `ssh root@192.168.8.141`,
kein `ssh user@192.168.8.162`, kein `sonoff_ctl`, kein `wandcheck.py`, kein `scp`, nichts nach
`tftp/`. Kein `sudo`, kein `git commit`/`push`, **kein Kernel-Patch angefasst** (F ist Userspace),
`patches/kernel/series` und `build/build.sh` nicht berührt, `0091` nicht angesehen (dort arbeitet ein
zweiter Agent). `/srv/h713-rootfs` nur **gelesen**.

Anlass: die adversarische Gegenprüfung von [F-startklar.md](F-startklar.md). Ihr Kernsatz -
„handwerklich sauber, aber der tragende Beleg für die einzige inhaltliche Codeänderung ist falsch
gelesen" - trifft zu. Dieses Log sagt, was deshalb raus ist, was an seiner Stelle steht, und wie das
abzunehmen ist.

| Datei | sha256 | Zustand |
|---|---|---|
| `userspace/hy310-tv/main.c` | `da5cc50fbdab3805a42bda19f87d9a80f5d91d7c95b63feff2d8af9b66aa1653` | geändert |
| `userspace/hy310-tv/README.md` | `f42ea4d1bb87f730db0385339ecc1058265baf9daafcc6dfab40ce268ac31af5` | §1, §2, §6, §7, §8, §9 nachgezogen |
| `userspace/hy310-tv/Makefile` | `dc15136178848ffcb791957eb373da8b3dd39b10a24f1cdba2f81c9749fe38bb` | **unverändert** |
| `userspace/hy310-tv/hy310-tv.service` | `8cebe4aa046f087c06ce45b525941f964ff9711a5a02e7e09cb843783fe7a8cc` | **unverändert** |
| `userspace/hy310-tv/99-hy310-tv.rules` | `08ea07ce63de2df18508b4618a5f2f49dc483022cbf71f1e6d8205a9c2c92ea3` | **unverändert** |

In `F-startklar.md` stehen jetzt Nachträge an §2.2, §2.4, §5 und §7, die auf dieses Log zeigen. Der
Rest jenes Logs - Prüfbau, Gerätesuche über den Namen, §2.3, §2.5 - §2.8, die Board-Anfragen - bleibt
gültig.

---

## 1. Was raus ist und warum

```c
#define RING_SETTLE_MS	3000
```

Die Konstante ist **ersatzlos gelöscht**, mitsamt `settle_arm()`, `settle_disarm()` und
`settle_report()`.

**Der Beleg trug sie nicht.** Der Kommentar an der Konstante berief sich auf die Tabelle in
[D-abnahme-board.md](D-abnahme-board.md), Nachtrag 06:15, und las sie als „der Ring läuft noch eine
Sekunde nach dem Enable, bei +2 s ist er weg - also sind 3 s die gemessenen +2 s mit Reserve".
Dieselbe Tabelle, vollständig gelesen:

| t | `0x05600044` | `0x05600098` | `0x06940928` | **`0x05600010`** |
|---|---|---|---|---|
| +1 s | `0x0780` | `0x00000000` | `0xE0020438` | **`0x03000010`** |
| +2 s | `0x0780` | `0x4D95F000` | `0x60020438` | **`0x03000013`** |

`0x05600010` ist CTRL von Source 0. Bei +1 s steht dort `0x03000010` - **Source 0 war noch gar nicht
eingeschaltet.** Der Treiber hat also irgendwo *innerhalb* dieses Fensters überhaupt erst geschrieben.
Die Zeile belegt damit **den Schreibzeitpunkt des Treibers**, nicht die Reaktionszeit der Firmware.
Aus ihr folgt genau eine Schranke, und die ist grob: **die Firmware reagierte irgendwo innerhalb
dieser einen Sekunde.** Zwei Sekunden „gemessen" waren nie da; drei Sekunden „mit Reserve" erst recht
nicht.

[D-cstride-fix.md](D-cstride-fix.md) §1 wertet dieselbe Tabelle unabhängig genauso aus („es lag
vollständig zwischen den Abtastungen +1 s und +2 s, in denen der Treiber überhaupt erst geschrieben
hat"). Der Widerspruch stand also seit gestern früh im Baum und ist der Fassung von 07:5x nur nicht
aufgefallen.

**Warum das ein Regel-1-Verstoß war und nicht bloß eine unscharfe Zahl:** die Zahl wurde nicht
gewartet, sie wurde **ausgegeben**. „Der Ring läuft 3000 ms nach dem Einschalten weiter" ist eine
Messaussage, und die Abnahme in `F-startklar.md` §5 Schritt 4 machte sie zum Kriterium („GENAU EINE
dieser beiden Zeilen"). Eine geratene Zahl, die als Messwert im Journal steht und in einer
Abnahmevorschrift als Kriterium auftaucht, ist genau der Fall, den Nachtplan-Regel 1 verbietet -
und sie ist schlimmer als eine geratene Wartezeit, weil sie sich als Befund tarnt.

---

## 2. Der zweite widerlegte Satz: „nur der erste Enable eines Boots"

`F-startklar.md` §2.4 und README §7 behaupteten, der Descriptor-Effekt träte nur beim **ersten**
Einschalten in einem Boot auf, weil `h713_afbd_publish_video_info()` den Descriptor-**Inhalt**
vergleicht (`memcmp` + `video_info_published`) und ihn nicht zweimal schreibt.

**Widerlegt.** Das Firmware-Ereignis hängt nicht am Inhalt, sondern am **Zeiger**:

* `h713_afbd_publish_video_info()` meldet „neu" bei neuem Datensatz **oder** neuem Zeiger
  (`new_ptr = readl(h->regs + AFBD_VIDEO_INFO0) != ptr`), und der Zeiger ist nach einem Kaltstart
  **null**.
* `analyse/hdmi-seq/afbd_source0.py off` **nullt die vier Info-Slots** (`w(AFBD, 0x98 + 4*i, 0)`).
  Der nächste Enable **im selben Boot** löst den Effekt deshalb erneut aus - am Gerät reproduziert,
  [D-cstride-befund.md](D-cstride-befund.md) (zweimal, Zeile „`0x0780` nach `afbd_source0.py off`"),
  ausgewertet in [D-cstride-fix.md](D-cstride-fix.md) §1.
* Der **Disable des Treibers** lässt den Zeiger absichtlich stehen (0093, Kommentar im
  `atomic_disable`: „The VideoInfo pointers stay"). Ein reines Aus/Ein von `hy310-tv` ist deshalb
  tatsächlich still - aber das ist eine Aussage über den Zeiger, keine über den Boot.

Der `memcmp` schützt vor einem zweiten **Publish desselben Datensatzes** - das ist das, was die
Hardware nicht überlebt. Er schützt **nicht** vor einem zweiten VideoDec-Ereignis.

**Folge für F, und sie ist konstruktiv:** aus dem Userspace ist `0x05600098` nicht zu sehen. Die
Voraussetzung, unter der man sich das Nachsehen sparen könnte, ist von hier aus nicht prüfbar -
**also wird nach jedem Einschalten beobachtet**, nicht nur nach dem ersten. Genau deshalb passt eine
Reihe hier besser als ein Termin: sie kostet, wenn nichts passiert, zehn Registerabfragen und eine
Journalzeile.

---

## 3. Wie die Erkennung jetzt läuft

### 3.1 Eine begrenzte Abtastreihe statt eines Termins

Am `poll()` hängt weiterhin ein `timerfd`, aber **periodisch** statt einmalig, und nur solange
beobachtet wird:

| | |
|---|---|
| **Start** | beim echten Übergang „aus → an" der Plane. Ein `SOURCE_CHANGE`, das eintrifft, während das Bild schon steht, startet **keine** neue Reihe - es hat nichts veröffentlicht, also gibt es nichts zu datieren. |
| **Raster** | `RING_WATCH_PERIOD_MS = 200` - alle 200 ms eine `QUERY_DV_TIMINGS` |
| **Frist** | `RING_WATCH_LIMIT_MS = 2000` |
| **Ende** | Stillstand erkannt, Gerät antwortet nicht mehr, oder Frist erreicht - in **jedem** Fall wird der Timer entschärft |
| **Wirkung auf die Anzeige** | **keine.** Die Plane bleibt in allen drei Fällen, wie sie ist |

Gemessen wird gegen `CLOCK_MONOTONIC` (dieselbe Uhr, an der das `timerfd` hängt). Zwei Zeitpunkte
werden mitgeführt:

* `t_on` - der Moment, in dem der Atomic-Commit zurückkam,
* `t_running` - der letzte Moment, zu dem die Flip-Zeiger **nachweislich** wanderten.

`t_running` startet **vor** `t_on`: es ist der Zeitpunkt der `QUERY_DV_TIMINGS`, die unmittelbar vor
dem Einschalten „Signal vorhanden" ergab. Deshalb ist die erste Zahl im Journal negativ. Das ist
Absicht - der Anfang des Fensters ist die letzte Messung, die etwas belegt hat, nicht der Moment, ab
dem es bequem zu zählen wäre.

### 3.2 Die drei Ausgänge, und jeder sagt, welcher er ist

**Stillstand** - der Übergang mit Zeitstempel:

```
warnung: der Ring steht still -- die Flip-Zeiger wanderten zuletzt bei -6 ms und stehen bei
+412 ms, gemessen ab dem Einschalten der Plane (Abtastung 3, Raster 200 ms). Das ist der
Descriptor-Effekt (Nachtplan A.5, doku/nachtlog/D-cstride-fix.md). Die Wand zeigt jetzt ein
Standbild, bis die Capture wieder freigegeben wird (Quellenwechsel B2 oder HPD-Zyklus M4, 0,3 s).
```

Beide Zahlen sind Messwerte. Das Fenster endet beim **Beginn** der Abtastung, nicht an ihrem Ende:
`h713_hdmirx_signal_present()` sieht die Zeiger über die vollen 20 ms dieser Abfrage an und meldet
Stillstand nur, wenn sie sich in der ganzen Zeit nicht bewegt haben - der Übergang ist also vor dem
Beginn der Abfrage passiert.

**Abbruch** - das Gerät antwortet nicht mehr:

```
warnung: beobachtung abgebrochen bei +812 ms (Abtastung 5): das Aufnahmegeraet antwortet nicht mehr
```

**Frist** - und sie sagt, dass sie gerissen wurde:

```
ring        laeuft: 10 Abtastungen bis +2022 ms nach dem Einschalten, jede hat wandernde
            Flip-Zeiger gesehen. Beobachtungsfrist von 2000 ms erreicht, Beobachtung beendet --
            ueber die Zeit danach sagt diese Zeile nichts.
```

Der letzte Halbsatz ist der Punkt. „Kein Stillstand gesehen" ist eine Aussage über diese zwei
Sekunden. Die alte Zeile („der Ring läuft 3000 ms nach dem Einschalten weiter - kein
Descriptor-Effekt in diesem Lauf") behauptete mehr, als sie wusste, in beide Richtungen.

### 3.3 Warum die zwei verbliebenen Zahlen keine Kriterien sind

Es bleiben zwei Konstanten. Beide sind benannt, beide entscheiden nichts:

* **`RING_WATCH_PERIOD_MS = 200` ist die Auflösung der Aussage.** Sie sagt, wie eng das Journal den
  Moment benennen kann, und sonst nichts; ein anderer Wert ändert kein Ergebnis, nur die Breite des
  gemeldeten Fensters. Nach unten begrenzt sie die Messung selbst: jede `QUERY_DV_TIMINGS` kostet den
  Treiber 20-25 ms Zeigerbeobachtung (0094, `h713_hdmirx_signal_present()`), 200 ms hält das bei
  rund einem Zehntel der Zeit.
* **`RING_WATCH_LIMIT_MS = 2000` ist ein Abbruchkriterium.** Beobachten kann nicht ewig laufen. Der
  Wert ist das Doppelte der einzigen gemessenen Schranke (§1: „innerhalb dieser einen Sekunde"), und
  er wird **als Frist gemeldet**, nicht als Freispruch.

Der Unterschied zu vorher in einem Satz: **die 3 s standen zwischen der Messung und dem Ergebnis
(„ist es nach 3 s noch gut?"), die 200 ms/2000 ms stehen daneben („wie genau und wie lange sehe ich
hin?").**

### 3.4 Der Auflösungswechsel - benannt, im Log, und ehrlich ohne zweites Kriterium

[A6-4-aufloesungswechsel.md](A6-4-aufloesungswechsel.md) ist am Gerät gemessen: wechselt die Quelle
bei stehendem Signal die Auflösung, feuert **kein** `SignalChange` und damit **kein**
`SOURCE_CHANGE`; die Flip-Zeiger wandern weiter, Bilder werden weiter geliefert, und
`QUERY_DV_TIMINGS` antwortet **unverändert** die alte Geometrie. Der Ring enthält dann zerrissenen
Inhalt. Ein Umschalter, der nur auf `SOURCE_CHANGE` hört, zeigt das stillschweigend.

Das Programm sagt das jetzt **beim Start ins Journal**, einmal, mit Fundstelle:

```
offen       ein Aufloesungswechsel der Quelle erzeugt kein SOURCE_CHANGE und laesst
            QUERY_DV_TIMINGS auf der alten Geometrie stehen (am Geraet gemessen,
            doku/nachtlog/A6-4-aufloesungswechsel.md). Dieses Programm bemerkt ihn deshalb
            nicht: die Wand zeigt dann zerrissenen Inhalt, ohne dass hier eine Zeile faellt.
            Ein zweites Kriterium dafuer gehoert in 0094, es ist ueber V4L2 heute nicht zu haben.
```

**Warum kein zweites Kriterium im Programm, obwohl der Auftrag es lieber sähe:** ich habe nach einem
gesucht und keines gefunden, das nicht gelogen wäre.

* Der naheliegende Griff - die Timings jeder Abtastung mit denen beim Einschalten vergleichen -
  **kann nie auslösen**: `h713_hdmirx_query_dv_timings()` in 0094 gibt die **Konstante**
  `h713_hdmirx_timings` zurück (die einzige Zeile aus `h713_hdmirx_timings_cap`, 1920×1080 bei
  148,5 MHz) und benutzt `signal_present()` nur als Torwächter. Zwei Abfragen zu vergleichen zeigt
  deshalb strukturell nichts. Eine Prüfung, die nie auslöst, sieht aus wie ein Kriterium, ist keins
  und macht die nächste Durchsicht blind - dieselbe Sorte Fehler wie die 3 s, nur andersherum.
* Die Kandidaten, die A6-4 selbst nennt (INCAP-Timing-Register, Composition-Block
  `0x05000224`/`0x05000844`), sind `/dev/mem`. Im Betriebspfad ist das ausgeschlossen (J-Fund W10),
  und ein zweiter Weg zur Hardware am Treiber vorbei ist genau der Workaround, den dieses Projekt
  nicht baut.
* Der Ringinhalt selbst wäre der dritte Weg - F dequeuet nicht und hat mangels `VIDIOC_EXPBUF` auch
  keinen Puffer.

Also: **benannter, im Log sichtbarer offener Punkt**, mit Adressat. Der Auslöser gehört in 0094; die
Messvorschrift dafür steht in A6-4 („vor und nach einem `xrandr --mode`-Wechsel `dump_state.py`
ziehen und die Blöcke `0x0694` und `0x0500` diffen"). Sobald 0094 ein Ereignis oder eine ehrliche
Geometrie liefert, greift der Vergleich in `evaluate()`, der heute schon dasteht
(`t.bt.width != d->width`), ohne dass an F etwas zu ändern wäre.

---

## 4. Abnahmevorschrift (kopierbar, Hauptsitzung) - **gültige Fassung**

Ersetzt `F-startklar.md` §5. Schritte 0-3 und 5-7 sind von dort übernommen und unverändert; neu bzw.
geändert sind **Schritt 4**, **Schritt 8** und der **Zusatzlauf B**.

**Voraussetzungen:** der Kernel mit der integrierten Serie läuft (0091-0095), die Wand zeigt die
Konsole, der Zuspieler `192.168.8.162` ist wach und auf 1080p60. Board-Sperre halten.
**Solange `hy310-tv` das Bild zeigt, hält es den DRM-Master** - vor jeder Positivkontrolle mit
`hdmi_plane_test`/`gamma_test` erst `systemctl stop hy310-tv`.

```bash
# --- 0. Bauen und installieren (Arbeitsrechner) ------------------------------
cd /opt/Projekte/h713/userspace/hy310-tv
make cross                                                     # Pruefbau, muss gruen sein
scp hy310-tv.aarch64-linux-gnu root@192.168.8.141:/usr/local/sbin/hy310-tv
scp hy310-tv.service            root@192.168.8.141:/etc/systemd/system/hy310-tv.service
scp 99-hy310-tv.rules           root@192.168.8.141:/etc/udev/rules.d/99-hy310-tv.rules
ssh root@192.168.8.141 'chmod 0755 /usr/local/sbin/hy310-tv'
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
ssh root@192.168.8.141 'journalctl -u hy310-tv -n 40 --no-pager'
#  erwartet: von der udev-Regel gestartet, ohne Handgriff; im Journal
#    aufnahme    /dev/video1 (sun50i-h713-hdmirx, ...)
#    anzeige     /dev/dri/card1 (sun50i-h713-afbd)
#    crtc        36, Modus 1920x1080
#    plane       38, NV16, Betriebsart hdmi-ring
#    offen       ein Aufloesungswechsel der Quelle erzeugt kein SOURCE_CHANGE ...
#  Die "offen"-Zeile MUSS da sein -- sie ist der im Log sichtbare blinde Fleck (§3.4).

# --- 3. Zustand vor dem ersten Bild ------------------------------------------
ssh root@192.168.8.141 'cat /sys/kernel/debug/sun50i-h713-hdmirx/status'
#  erwartet: signal: vorhanden (Flip-Zeiger wandern) -- sonst haengt es an B/E, nicht an F

# --- 4. Bild da, und was sagt die Abtastreihe? [GEAENDERT] -------------------
ssh root@192.168.8.141 'journalctl -u hy310-tv -n 20 --no-pager'
#  erwartet: signal 1920x1080p ...   bild Plane 38 an ...
#  und danach GENAU EINE dieser beiden Zeilen, mit MESSWERTEN statt einer festen Zahl:
#    ring        laeuft: N Abtastungen bis +X ms ... Beobachtungsfrist von 2000 ms erreicht
#    warnung: der Ring steht still -- ... zuletzt bei +A ms und stehen bei +B ms ...
#
#  PRUEFEN, nicht ueberfliegen -- das ist der Kern dieser Korrektur:
#   * Der Stillstandsfall MUSS zwei Zahlen nennen, A < B, A darf negativ sein (§3.1).
#   * Der Gutfall MUSS "Beobachtungsfrist ... erreicht" sagen. Fehlt der Halbsatz,
#     laeuft ein alter Stand auf dem Board.
#   * KEINE Zeile darf "3000 ms" enthalten:
ssh root@192.168.8.141 'journalctl -u hy310-tv --no-pager | grep -c "3000 ms"'   # MUSS 0 sein
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

# --- 6. Stecker raus: Konsole -- die eigentliche Aufgabe von F ---------------
ssh user@192.168.8.162 'DISPLAY=:0 xrandr --output HDMI-2 --off'; sleep 8
ssh root@192.168.8.141 'journalctl -u hy310-tv -n 10 --no-pager'
#  erwartet: ereignis SOURCE_CHANGE ... / signal kein Signal ... / konsole Plane aus ...
python3 /opt/Projekte/h713/analyse/hdmi-seq/wandcheck.py shot F-konsole
#  MUSS Konsolentext zeigen. Ein Standbild der Quelle hier ist der Durchfall schlechthin.

# --- 7. Nur falls Schritt 4 den Stillstand gemeldet hat ---------------------
#  Einmal von Hand freigeben (Stock-RPC, kein Poke), dann Schritt 4-5 wiederholen:
ssh root@192.168.8.141 'cd /root; python3 arisc_hdmi.py --no-probe raw --sub-cmd 0x0211 --arg1 0 --arg2 2 --settle 0.6; sleep 1; python3 arisc_hdmi.py --no-probe hotplug --port 0 --value 1 --settle 1.0'
ssh root@192.168.8.141 'cat /sys/kernel/debug/sun50i-h713-hdmirx/status | head -8'
#  Das ist ein Befund fuer D/E, KEIN Fehler von F.

# --- 8. Und wieder rein: Wiederholbarkeit [GEAENDERT] -----------------------
ssh user@192.168.8.162 'DISPLAY=:0 xrandr --output HDMI-2 --auto'; sleep 10
ssh root@192.168.8.141 'journalctl -u hy310-tv -n 15 --no-pager'
python3 /opt/Projekte/h713/analyse/hdmi-seq/wandcheck.py shot F-bild2
#  Erwartet die Frist-Zeile: der Treiber-Disable laesst den Descriptor-Zeiger stehen,
#  also loest dieser zweite Enable kein VideoDec-Ereignis aus.
#  ABER: "erster Enable eines Boots" ist NICHT das Kriterium (§2). Steht hier ein
#  Stillstand, erst den Zeiger lesen, bevor daraus ein Befund wird:
ssh root@192.168.8.141 'busybox devmem 0x05600098'
#    != 0  -> der Zeiger stand, das Ereignis kam anderswoher = NEUER BEFUND, ins Log
#    == 0  -> irgendetwas hat die Info-Slots genullt (Skript? Modul neu geladen?);
#             dann ist der Stillstand erwartetes Verhalten und kein Befund.
#  Und noch einmal den Reiz aus Schritt 5 -- ein zweites Bild ist auch nur ein Foto.

# --- 9. Sauberes Beenden -----------------------------------------------------
ssh root@192.168.8.141 'systemctl stop hy310-tv; echo rc=$?'; sleep 3
python3 /opt/Projekte/h713/analyse/hdmi-seq/wandcheck.py shot F-nach-stop
#  erwartet: Journal "ende Signal 15 erhalten" + "konsole Plane aus ...", rc=0,
#  Wand = Konsole. KEIN Standbild.
```

### Zusatzlauf B - der Descriptor-Effekt ein zweites Mal im selben Boot [NEU]

Belegt die Korrektur aus §2 **am Gerät** und prüft zugleich, ob die Abtastreihe den Übergang
wirklich datiert. Kein Kaltstart nötig, direkt im Anschluss an Schritt 8 zu fahren.

```bash
ssh root@192.168.8.141 'systemctl stop hy310-tv'; sleep 2
ssh root@192.168.8.141 'busybox devmem 0x05600098'          # erwartet: != 0, der Zeiger steht
ssh root@192.168.8.141 'python3 /root/afbd_source0.py off'  # nullt u.a. die vier Info-Slots
ssh root@192.168.8.141 'busybox devmem 0x05600098'          # MUSS jetzt 0x0 sein
ssh root@192.168.8.141 'systemctl start hy310-tv'; sleep 5
ssh root@192.168.8.141 'journalctl -u hy310-tv -n 15 --no-pager'
```

**Erwartung:** dieselbe Stillstandsmeldung wie beim Erst-Enable, mit zwei Messwerten - obwohl es
derselbe Boot ist. Genau das war mit „nur der erste Enable eines Boots" ausgeschlossen worden.

* Kommt sie, ist §2 am Gerät belegt **und** die Erkennung hat den Übergang datiert, statt ihn zu
  raten. Danach Schritt 7 (Freigabe) fahren.
* Kommt stattdessen die Frist-Zeile, ist §2 **nicht** bestätigt - dann ins Log, `0x06940928` und
  `0x05600098` dazu, und D/E fragen. Auch das ist ein gültiges Ergebnis.

Anschließend `python3 /root/afbd_source0.py off` **nicht** stehen lassen: den Zustand über Schritt 7
und einen weiteren Start wieder herstellen, sonst verfälscht der Rest die nächste Abnahme
(D-cstride-befund.md, Nebenbefund).

### Zusatzlauf C - der blinde Fleck, absichtlich vorgeführt [NEU, kein Durchfallkriterium]

Zeigt am Gerät, was §3.4 beschreibt. **Erwartet wird ein Fehlbild** - das ist der Sinn der Übung.

```bash
# Bild steht (Schritt 4 gruen)
ssh user@192.168.8.162 'DISPLAY=:0 xrandr --output HDMI-2 --mode 1280x720'; sleep 5
ssh root@192.168.8.141 'journalctl -u hy310-tv -n 5 --no-pager'   # erwartet: KEINE neue Zeile
python3 /opt/Projekte/h713/analyse/hdmi-seq/wandcheck.py shot F-720p-blind
ssh user@192.168.8.162 'DISPLAY=:0 xrandr --output HDMI-2 --mode 1920x1080'; sleep 5
python3 /opt/Projekte/h713/analyse/hdmi-seq/wandcheck.py shot F-1080p-zurueck
```

Erwartet: die Wand zeigt zerrissenen Inhalt (A6-4: 720p-Bild dreifach nebeneinander über dem alten
1080p-Rest), das Journal bleibt **still**, und der Rückweg auf 1080p ist wieder sauber. Das Foto
`F-720p-blind` ist der Beleg für den offenen Punkt an 0094 und gehört zur Board-Anfrage.

### Erwartungstabelle

| Schritt | Erwartung |
|---|---|
| 2 | `video1` trägt den Namen `sun50i-h713-hdmirx`; Unit `active (running)`, von udev gestartet; **`offen`-Zeile im Journal** |
| 3 | debugfs `signal: vorhanden (Flip-Zeiger wandern)` |
| 4 | `bild Plane 38 an …`; **genau eine** Ring-Zeile, mit Messwerten; `grep -c "3000 ms"` = 0 |
| 5 | Reiz ändert zweistellig viele Prozent. **Der einzige gültige Beweis, dass das Bild läuft** |
| 6 | Konsolentext auf der Wand, **kein** Standbild |
| 8 | Bild kommt von selbst zurück; Frist-Zeile - und bei Stillstand erst `0x05600098` lesen |
| 9 | Konsole, `rc=0`, kein Standbild |
| B | Stillstandsmeldung mit zwei Messwerten, **im selben Boot** |
| C | Fehlbild auf der Wand, Journal still - der belegte blinde Fleck |

### Wenn etwas schiefgeht

Die Tabelle aus `F-startklar.md` §5 gilt unverändert weiter, mit drei Änderungen:

| Beobachtung | Bedeutung | Nächster Schritt |
|---|---|---|
| Journalzeile enthält `3000 ms` | auf dem Board läuft ein **alter** Stand | Schritt 0 wiederholen, `sha256sum /usr/local/sbin/hy310-tv` gegen den Prüfbau halten |
| `der Ring steht still … zuletzt bei A … stehen bei B` | der Descriptor-Effekt, **datiert** | Schritt 7; Befund für D/E. A und B ins Log übernehmen - das sind die ersten echten Messwerte zu dieser Frage |
| `beobachtung abgebrochen … antwortet nicht mehr` | `QUERY_DV_TIMINGS` gibt einen anderen Fehler als `ENOLINK` zurück | `dmesg \| grep hdmirx`; das ist ein Befund für E, nicht für F |
| Bild zerrissen, Journal still | **Auflösungswechsel der Quelle** (§3.4) - kein Fehler von F | Zuspieler-Modus prüfen; offener Punkt an 0094 |

---

## 5. Prüfbau - **ausdrücklich ein Prüfbau, kein Serienartefakt**

```
clang --target=aarch64-linux-gnu --sysroot=/srv/h713-rootfs -fuse-ld=lld \
    -O2 -g -Wall -Wextra -Wshadow -Wvla -isystem /srv/h713-rootfs/usr/include/libdrm \
    -L/srv/h713-rootfs/usr/lib/aarch64-linux-gnu -o hy310-tv.aarch64-linux-gnu main.c -ldrm
```

| Prüfung | Ergebnis |
|---|---|
| `make -C userspace/hy310-tv cross`, clang 18.1.3 (Host), `-Wall -Wextra -Wshadow -Wvla` | **grün, null Warnungen** |
| Ergebnis | `ELF 64-bit LSB pie executable, ARM aarch64`, 60 976 B, `NEEDED libdrm.so.2`, `libc.so.6` - sonst nichts; sha256 `a8f63b2bbb79802e982800dce49849b3de475165ea271875cb4cbf972f1d9aa9` (aus diesem Prüfbau, mit demselben Clang und demselben Pfad wiederholbar) |
| `clang --analyze` (`core,unix,deadcode`) | **kein Befund** |
| `make install-cross DESTDIR=…` (Wegwerf-Wurzel) | legt `usr/local/sbin/hy310-tv` (arm64, 0755), Unit und Regel ab |
| `udevadm verify 99-hy310-tv.rules` | `Success: 1, Fail: 0` |
| `systemd-analyze verify ./hy310-tv.service` | grün (einziger Hinweis: `/usr/local/sbin/hy310-tv` gibt es auf **diesem** Rechner nicht - erwartet) |
| `grep -n "RING_SETTLE\|settle_" main.c` | leer |
| `make clean` | Baum wieder sauber, **kein Binärartefakt im Repo** (das `main.plist` des Analyzers räumt `clean` nicht mit weg - hier von Hand entfernt) |

`clock_gettime(CLOCK_MONOTONIC)` braucht auf dem Board-Root kein zusätzliches `-lrt` (glibc ≥ 2.17);
`NEEDED` bleibt bei `libdrm.so.2` und `libc.so.6`.

**Zeit- und Timer-Arithmetik getrennt geprüft.** Weil ein Lauf am Gerät aussteht, ist die neue
Mechanik als eigenständiges Programm nachgebaut worden (dieselbe Armierung, dieselben Offsets, die
`ioctl` durch ein `usleep(22 ms)` ersetzt) und auf dem Arbeitsrechner gelaufen - Wegwerfdatei im
Scratch-Verzeichnis, nicht im Baum:

```
  lauf 1: start +200 ms, ende +222 ms      <- Raster haelt, it_interval greift
  ...
  lauf 6: start +1200 ms, ende +1222 ms
STILLSTAND: zuletzt +1222 ms, steht +1400 ms (Abtastung 7)
STILLSTAND: zuletzt -6 ms, steht +200 ms (Abtastung 1)     <- erste Abtastung, negativer Anfang
FRIST: 10 Abtastungen bis +2022 ms                         <- Abbruchkriterium greift
```

Das prüft die Arithmetik und das periodische `timerfd`, **nicht** das Verhalten der Firmware. Was der
Ring wirklich tut, entscheidet Schritt 4 und Zusatzlauf B.

**Nicht gelaufen.** Ein Lauf braucht `/dev/dri/card1` mit 0093 und `/dev/video1` mit 0094; beides gibt
es nur am Board. Warum der Prüfbau nicht im Container `h713-build` läuft, steht unverändert in
`F-startklar.md` §1 (ein Mount, `/srv` im Container leer, kein libdrm, kein arm64-Sysroot).

---

## 6. Was offen bleibt

1. **Ein Lauf.** Das Programm ist gebaut und geprüft, aber nie gestartet worden. Alles in §4 ist
   Erwartung, kein Messwert. **Die erste echte Zahl zur Reaktionszeit der Firmware entsteht in
   Schritt 4** - bis dahin ist der einzige Beleg „innerhalb einer Sekunde" (§1).
2. **Der Auslöser für den Auflösungswechsel gehört in 0094** (§3.4). Solange er fehlt, ist die
   `offen`-Zeile im Journal alles, was F dazu tun kann. Messvorschrift steht in A6-4; Zusatzlauf C
   liefert das Foto dazu.
3. **Die Freigabe nach dem Descriptor gehört in 0093/0094** - unverändert offen seit
   `F-hy310-tv.md` §6 Punkt 1 und `F-startklar.md` §6 Punkt 1. Beide Wege sind Stock-RPCs (B2:
   `SetSource` weg und zurück; M4: HPD-Zyklus, 0,3 s). F warnt, F repariert nicht.
4. **Messung M-F1** (reicht ein wiederholtes `SetSource(3)`?) steht unverändert in
   `F-startklar.md` §6 Punkt 2.
5. **Ob die Frist von 2000 ms weit genug ist**, ist nach dem ersten Lauf zu prüfen: meldet Schritt 4
   die Frist-Zeile und friert die Wand **danach** doch ein, ist der Wert zu klein - dann steht die
   nächste Zahl auf einer echten Messung. Das ist der Punkt der Umstellung: der Wert kann jetzt
   **widerlegt** werden, weil das Log sagt, worüber er nichts aussagt.
