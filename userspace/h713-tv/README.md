# `h713-tv` - HDMI-Bild auf die Video-Plane, Konsole bei Signalverlust, Steuerung vom Userspace

Paket **F** aus [doku/78-nachtplan-hdmi-switch.md](../../doku/78-nachtplan-hdmi-switch.md), Anhang A.4.
Ein kleines Programm plus systemd-Unit: liegt am HDMI-Eingang ein Signal, zeigt der Beamer das Bild der
Quelle; verschwindet das Signal, gehört das Panel wieder der Konsole. Ohne Handgriff, in beide Richtungen.
Dazu ein Steuerkanal (`h713-tv ctl …`), über den sich Bild, Regler, Quelle und Firmware vom Userspace aus
bedienen lassen - Abschnitt 6a. Seit Paket E ([doku/101](../../doku/101-plan-audio-treiber.md)) folgt auch der
**Ton** dem Bild: HDMI-Audio läuft über den Audio-DSP in den Codec, sobald ein Bild steht und die Quelle PCM
sendet, und ist sonst stumm - Abschnitt 6b.

**Stand 08.09.2026:** läuft am Gerät mit Kernel-Serie 95 (`0117` - `0126`): 720p und 1080p werden von der
Firmware skaliert und farbrichtig gezeigt, über beliebig viele Wechsel
([doku/nachtlog/S11](../../doku/nachtlog/S11-gruenstich-ursache-und-callback-slots.md)). Die frühere
Konsolen-Sperre für Nicht-Panel-Auflösungen und der Testschalter `H713_TV_SKALIERTEST` sind weg. VESA-Modi
laufen mit 60 Hz (1024×768 mit 4:3-Balken, 1440×900, 1280×1024 gestreckt); 120-Hz-Varianten und 1600×900
kennt die Firmware-Tabelle nicht → Konsole.
Die Abnahmevorschrift steht in [doku/nachtlog/F-korrektur.md](../../doku/nachtlog/F-korrektur.md).
---

## 1. Was das Programm tut - und was ausdrücklich nicht

Zwei Geräte, zwei Rollen:

| Gerät | auf diesem Board | Treiber | Rolle |
|---|---|---|---|
| `/dev/videoN` | **`/dev/video1`** (`video0` ist cedrus) | `sun50i-h713-hdmirx` (0094) | sagt, **ob** ein Signal anliegt, und meldet **wann sich das ändert** |
| `/dev/dri/cardN` | **`/dev/dri/card1`** (`card0` ist Panfrost) | `sun50i-h713-afbd` (0093) | zeigt das Bild: Overlay-Plane `video-0` = **Plane 38** an **CRTC 36**/Connector 33, Betriebsart `hdmi-ring` |

Keine dieser Nummern steht im Programm. Das Aufnahmegerät wird über
`/sys/class/video4linux/videoN/name` gesucht - dieselbe Zeichenkette, auf die auch die udev-Regel passt -
und mit `VIDIOC_QUERYCAP` bestätigt; das DRM-Gerät über `drmGetVersion()->name`, die Plane über
Typ + NV16 + Eigenschaft `hdmi-ring`. Die Nummern stehen hier nur, damit man beim Nachsehen weiß, was
herauskommen muss.

**NV16 und NV16M sind kein Widerspruch.** Die Capture bietet `V4L2_PIX_FMT_NV16M` an: zwei *getrennte*
Ebenen à 2 073 600 Byte, weil Y und C im Ring `0x5FD000` auseinanderliegen. Der KMS-Framebuffer ist
`DRM_FORMAT_NV16` - ein Zweiebenen-Fourcc in **einem** Pufferobjekt - , und in `hdmi-ring` trägt er ohnehin
nur Format, Geometrie und Zeilenabstand. Es wird nichts umgerechnet.

Die Bildpunkte laufen **nicht** durch dieses Programm. Die Plane liest den Capture-Ring selbst: sie holt
sich in ihrem Vsync das Flip-Zeigerpaar der Firmware und übernimmt den zuletzt fertigen Ring-Slot
(doku/86 §5). Das Programm sagt ihr nur, dass sie das tun soll (Plane-Eigenschaft `hdmi-ring`), und wann
sie damit aufhören soll.

Die Zustandsmaschine ist entsprechend klein:

```
                 SOURCE_CHANGE, kein Signal
        +--------------------------------------------+
        v                                            |
   BEREITSCHAFT                                    BILD
   Plane aus, DRM-Master abgegeben                 Plane an, Master gehalten
   (die Konsole hat das Panel)                     (der Mux ist exklusiv:
        |                                           Konsole ist weg, solange
        +--------------------------------------------+  das Bild steht)
                 SOURCE_CHANGE, Signal da
```

`SIGTERM`/`SIGINT` nehmen denselben Ausgang wie ein Signalverlust: Plane aus, Konsole zurück, dann erst
beenden. Ein `systemctl stop` lässt also **kein Standbild** auf der Wand stehen.

**Entschieden** wird ausschließlich auf ein Ereignis hin. Es gibt keine Zeitschleife, kein `sleep` als
Heilmittel und keine Wiederholung ohne Ursache: die MIPS-Firmware feuert ihren `SignalChange`-Callback bei
Verlust **und** bei Rückkehr von selbst (gemessen, [doku/nachtlog/K4-hotplug.md](../../doku/nachtlog/K4-hotplug.md)),
und 0094 macht daraus `V4L2_EVENT_SOURCE_CHANGE`. Das Programm hängt in `poll()`.

Der einzige Timer, den es gibt, fragt **nach**, wenn der Treiber einen Wechsel als „noch nicht
eingerastet" meldet (`-ENOLCK`): alle 50 ms, höchstens vierzigmal; solange bleibt die Wand, wie sie ist.
Danach bleibt der aktuelle Zustand stehen - steht die Konsole, wird alle 500 ms weitergefragt (§7).

---

## 2. Warum ein C-Programm und nicht `gst-launch-1.0 v4l2src ! kmssink`

Der Nachtplan erlaubt beides. Entschieden wurde für das C-Programm, und zwar **nicht**, weil GStreamer
fehlte - es ist auf dem Board-Root installiert (`gst-launch-1.0`, `libgstvideo4linux2.so`, `libgstkms.so`;
`v4l2-ctl` übrigens auch, nur `modetest` fehlt). Die Gründe sind inhaltlich:

1. **Eine GStreamer-Kette müsste jedes Bild kopieren.** 0094 gibt die drei Ring-Slots als
   `VB2_MEMORY_MMAP` heraus und hat **kein** `VIDIOC_EXPBUF` (doku/88 §4 und §8 Punkt 2). Ohne dma-buf
   importiert `kmssink` nichts, sondern kopiert in seinen eigenen Dumb-Puffer: 4 MiB je Bild, 60-mal in
   der Sekunde, rund 250 MB/s - für Daten, die die Plane sich selbst holen kann. Der Auftrag sagt
   ausdrücklich: kein Kopieren.
2. **Die Plane lässt sich so gar nicht richtig fahren.** Der Betrieb aus dem Capture-Ring hängt an der
   Plane-Eigenschaft `hdmi-ring`; `kmssink` kennt keine treibereigenen Eigenschaften.
3. **Das Eigentliche an F ist die Zustandsmaschine, nicht der Datenpfad.** Bei Signalverlust **friert der
   Ring ein und die Wand zeigt den letzten Rahmen** - sie wird nicht schwarz (K4). Eine Kette, die
   einfach stehenbleibt, liefert genau das Fehlerbild, das wir verhindern wollen. Der Verlust muss aus dem
   V4L2-Ereignis erkannt werden, und dann muss jemand die Plane abschalten.
4. **Sauberes Beenden** (Plane aus, Konsole zurück, DRM-Master abgeben) ist mit `gst-launch` nicht zu haben.

Die Entscheidung kostet rund 1100 Zeilen C statt einer Kommandozeile (Stand 08.09.2026, ohne Kommentare
und Leerzeilen). Ein gutes Drittel davon ist der Steuerkanal (§6a); der Rest ist Gerätesuche über den
**Namen** (statt `/dev/video0` zu raten - dort sitzt cedrus), KMS-Eigenschaftsverwaltung und die
Zustandsmaschine.

---

## 3. Die Konsole zurückgeben: zwei Dinge, nicht eins

1. **Plane aus.** 0093 nimmt beim Disable den RGB-Kanal (`0x05600140`) wieder in Betrieb und stellt den
   Encoder-Selektor auf RGB zurück (doku/86 §6). Der Mux hinter AFBD Source 0 ist exklusiv - entweder
   Video **oder** RGB erreicht den Encoder - , also ist „Plane aus" wörtlich „Konsole an".
2. **DRM-Master abgeben.** Solange ein Userspace-Master existiert, malt der kerneleigene Konsolen-Client
   nicht mehr (`drm_master_internal_acquire`). Das Bild der Konsole bliebe stehen, wie es war, und jede
   neue Zeile ginge verloren. Deshalb hält das Programm den Master **nur**, solange das Bild steht, und
   gibt ihn in der Bereitschaft zurück. Der vollständige Restore des Kernel-Clients
   (`drm_client_dev_restore`) hängt am **letzten Schließen** des DRM-Geräts (`drm_lastclose`) - nicht am
   Master-Wechsel; nötig ist er nicht, weil 0093 die Hardware selbst zurückstellt.

Wenn auf dem Board später ein X-Server oder ein Wayland-Compositor läuft, ist der Master vergeben und
`h713-tv` bekommt ihn nicht (das Programm sagt das dann klar). Der Weg dorthin wäre eine DRM-Lease bzw.
der Start aus der Sitzung heraus - heute nicht nötig, das Panel gehört der Konsole (Patch 0064).

---

## 4. Standbild ist nicht Stillstand

Diese Zeile hat in der Nacht des 07.09. eine Stunde gekostet, deshalb steht sie hier:

> Ein **statischer Bildschirm** an der Quelle erzeugt **keine Änderung im Puffer**. Wer prüfen will, ob
> das Bild *lebt*, braucht einen **erzwungenen Reiz** - nicht den Blick auf ein unverändertes Foto.

Der Reiz der Wahl ist ein Gamma-Sprung am Zuspieler:

```bash
ssh user@192.168.8.162 'DISPLAY=:0 xrandr --output HDMI-2 --gamma 1:0.25:0.25'  # Reiz
ssh user@192.168.8.162 'DISPLAY=:0 xrandr --output HDMI-2 --gamma 1:1:1'        # zurueck
```

Größenordnung, damit man weiß, was ein Treffer ist: derselbe Reiz änderte bei der D-Abnahme **38,74 %**
der Bildpunkte im Messbereich (`D-abnahme-board.md`), bei B2 **4,65 %**. Die Rückkehr auf `1:1:1` muss
**nicht** exakt 0,00 % ergeben - die Quelle driftet über Minuten von selbst (D: 9,84 %; belegt in
`M4-hpd-dauer.md`). Bewertet wird der Sprung, nicht die Rückkehr auf die Nachkommastelle.

Umgekehrt gilt dasselbe für den Ring: die Flip-Zeiger drehen sich mit 60 Hz **unabhängig vom Inhalt**.
Genau darauf beruht die Signalerkennung in 0094 (`QUERY_DV_TIMINGS` misst 20 ms lang die Zeiger und
antwortet `-ENOLINK`, wenn sie stehen) - und deshalb ist „das Bild sieht gleich aus" **kein** Beleg für
Signalverlust und „der Ring läuft" **kein** Beleg dafür, dass sich am Inhalt etwas tut.

---

## 5. Bauen

**Abhängigkeiten:** `libdrm-dev` (KMS) und seit Paket E `libasound2-dev` (ALSA-Control-API für den Ton, Debian-Paket
`libasound2-dev`; zur Laufzeit `libasound2`, das ohnehin da ist). Beides gehört ins Board-Root - `ssh root@192.168.8.141
apt install libasound2-dev` - , denn auch der Querbau nimmt Header und Linkernamen von dort. Das Makefile fragt
`pkg-config --cflags --libs libdrm alsa` (nativ) bzw. linkt `-ldrm -lasound` (quer).

**Nativ auf dem Board** (das NFS-Root hat `gcc-14`, `pkg-config` und die libdrm-Header) - der einfachste Weg:

```bash
# vom Arbeitsrechner (macht die Hauptsitzung):
cp userspace/h713-tv/main.c userspace/h713-tv/Makefile /srv/h713-rootfs/root/h713-tv/
ssh root@192.168.8.141 'make -C /root/h713-tv'
```

**Quer auf dem Arbeitsrechner**, gegen das Board-Root als Sysroot (nur lesend):

```bash
make -C userspace/h713-tv cross          # -> h713-tv.aarch64-linux-gnu
```

Warum nicht im Container `h713-build`: der Container sieht `/srv` nicht (er hat nur
`/opt/Projekte/h713` → `/work`) und hat weder libdrm noch einen arm64-Sysroot. Regel 2 des Nachtplans
(„bauen nur im Container, nur über `build/build.sh`") gilt dem **Kernel**; für ein Userspace-Werkzeug ist
der Weg über den Host-Clang derselbe, den Paket D für `analyse/kms/hdmi_plane_test.c` beschreibt.

**Installieren** - vom Arbeitsrechner aus mit `install-cross`, denn `install` würde hier das *x86*-Programm
ins Board-Root legen:

```bash
sudo make -C userspace/h713-tv install-cross DESTDIR=/srv/h713-rootfs
# legt ab: /usr/local/sbin/h713-tv   (arm64, aus `make cross`)
#          /etc/systemd/system/h713-tv@.service   (Template; die alte h713-tv.service wird entfernt)
#          /etc/udev/rules.d/99-h713-tv.rules
ssh root@192.168.8.141 'systemctl daemon-reload; udevadm control --reload'
```

`/srv/h713-rootfs` gehört root, deshalb das `sudo`. Ohne `sudo` geht es über das Board, das sein eigenes
NFS-Root ohnehin als root schreibt - drei `scp` nach `root@192.168.8.141`, siehe
[F-startklar.md](../../doku/nachtlog/F-startklar.md) §5 Schritt 0.

Auf dem Board selbst gebaut heißt das Ziel weiterhin `make install`.

---

## 6. Betrieb

**Eine Template-Unit, kein `systemctl enable`.** Der Dienst heißt `h713-tv@videoN` - eine Instanz je
Aufnahmegerät, auf diesem Board `h713-tv@video1`. Die Unit hat absichtlich keinen `[Install]`-Abschnitt:
das Aufnahmegerät erscheint spät und mit unvorhersagbarer Nummer, weil der Probe von 0094 asynchron läuft
und allein die EDID/HPD-Sequenz über zehn Sekunden dauert. Gestartet wird deshalb aus der udev-Regel,
sobald das Gerät da ist, und der Kernelname des Geräts wird zum Instanznamen:

```
SUBSYSTEM=="video4linux", ACTION=="add", ATTR{name}=="sun50i-h713-hdmirx",
    TAG+="systemd", ENV{SYSTEMD_WANTS}+="h713-tv@%k.service"
```

Die Unit hängt mit `BindsTo=dev-%i.device` am Gerät, in beide Richtungen: verschwindet `/dev/video1`
(Treiber entladen, `unbind`), stoppt systemd die Instanz, statt sie gegen ein fehlendes Gerät in die
Neustartgrenze laufen zu lassen; kommt das Gerät wieder, startet udev sie neu. Geprüft 08.09.2026:
`udevadm trigger --action=add /sys/class/video4linux/video1` startet `h713-tv@video1`, `systemctl show`
zeigt `BindsTo=dev-video1.device` und das Gerät `plugged`.

Das ist die Alternative zu einer Warteschleife, nicht deren Verkleidung. Scheitert der Start dreimal in
einer Minute, bleibt die Instanz „failed" stehen, statt endlos zu starten.

Von Hand geht natürlich auch:

```bash
systemctl start h713-tv@video1     # bzw.
/usr/local/sbin/h713-tv            # im Vordergrund, Strg-C beendet sauber
```

**Aufrufoptionen**

```
h713-tv [-d /dev/videoN] [-c /dev/dri/cardN] [-s SOCKET] [-p PRESET] [-g LUT] [-a TON] [-t DB] [-C KONFIG] [-n]
h713-tv ctl [-s SOCKET] BEFEHL [ARG...]

  -d  Aufnahmegeraet (ohne Angabe: Suche nach dem Treiber "sun50i-h713-hdmirx")
  -c  DRM-Geraet     (ohne Angabe: Suche nach dem Treiber "sun50i-h713-afbd")
  -s  Steuer-Socket  (Vorgabe /run/h713-tv/ctl; daneben liegt der Einzelinstanz-Riegel "lock")
  -p  Bildvoreinstellung beim Start (standard cinema vivid game computer hdr | none); Vorgabe standard
  -g  Gammakurve fuer den CRTC, eine DE2-Bank aus h713-pq (2048 Byte) | none;
      Vorgabe /usr/local/share/h713-tv/gamma-standard.bin (Stock: Exponent 2.2)
  -a  Ton beim Start: auto (folgt dem Bild, Vorgabe) | on (erzwungen an) | off (erzwungen stumm) |
      none (keine ALSA-Karte anfassen -- fuer Boards ohne die Audiotreiber)
  -t  HDMI-Pegelabgleich im Audio-DSP in dB, 0 (Vorgabe) bis -100, Viertel-dB; auch --hdmi-trim DB.
      Das ist NICHT die Lautstaerke (die ist `ctl volume`), sondern der feste Abgleich HDMI gegen Geraetetoene
  -C  Konfigurationsdatei (Vorgabe /etc/h713/tv.conf): Startmodus und Ort des gemerkten Modus,
      Abschnitt 6c. Fehlt die Datei: start = auto, Modus gemerkt in /var/lib/h713-tv/modus
  -n  nur berichten, was gefunden wurde, und beenden -- die Anzeige bleibt unberuehrt, der Ton auch.
      Rueckgabewert 0 = Signal steht, 1 = kein Signal / Wechsel im Gang.
```

**Bildvoreinstellung und Gamma gehören zum Start.** Ohne sie läuft die Firmware mit dem, was ihre Register
nach dem Reset halten - und das ist nicht einmal „standard": Kontrast-/Helligkeitsregister leer, Sättigung 60
(gemessen 08.09.). Der Kernel sendet in seiner Init-Sequenz die vier Stufen und den Modus, die neun Werte
sendet dieses Programm einmal beim Start (`-p`, Vorgabe `standard` = Zeile `[HDMI1]` der Hersteller-INI).
Einmal genügt: die Firmware behält sie über Quellenwechsel, Auflösungswechsel und HDMI aus/an (gemessen:
PQ-Register hielten die Cinema-Werte durch alle drei). Eine Falle dabei: ein `Set` mit dem Wert, den die
Firmware intern schon hat (Start 50), schreibt kein Register; die fünf Regler werden deshalb um eine Stufe
angestupst und dann gesetzt, damit der Zustand belegt ist und nicht nur angenommen (Bild identisch, gemessen). Die Gammakurve (Stock: Exponent 2.2 in der
DE2-Stufe, die der MIPS selbst nie lädt) geht als `GAMMA_LUT` an den CRTC - einmal beim Start mit kurz
genommenem Master und bei jedem Bildaufbau; sie färbt Konsole wie Video, wie auf Stock. Die Datei
`gamma-standard.bin` stammt aus `h713-pq show HDMI1 standard --lut` (Paket G) und wird mit installiert.
Gegenprobe 08.09.: ein dunkles Hintergrundbild (Median 27/255) stand ohne LUT hellgrau an der Wand und mit
der Kurve dunkel - die Identität war das falsche Bild.

**Was im Journal steht** (`journalctl -u 'h713-tv@*' -f`):

```
aufnahme    /dev/video1 (sun50i-h713-hdm, H713 HDMI receiver)
anzeige     /dev/dri/card1 (sun50i-h713-afbd)
crtc        36, Modus 1920x1080
plane       38, NV16, Betriebsart hdmi-ring, Format proportional
gamma       /usr/local/share/h713-tv/gamma-standard.bin -> GAMMA_LUT (1024 Eintraege, Mitte 14307/65535)
preset      standard: mode=1 brightness=50 contrast=50 saturation=50 hue=50 sharpness=50 tnr=2 snr=1 dci=2 black=1
ton         hy310hdmi (card 1) + H713 Audio Codec (card 0), Ereignisse, Lautstaerke 100 (0,0 dB), HDMI-Abgleich 0,00 dB, Stummschalter Line Out Playback Switch, folgt dem Bild
steuerung   /run/h713-tv/ctl (h713-tv ctl help)
signal      1920x1080p, 148500000 Hz Pixeltakt
puffer      1920x1080 NV16, Zeilenabstand 1920 auf Panel 1920x1080
bild        Plane 38 an, 1920x1080 aus dem Capture-Ring
ton         Quelle da, 48000 Hz -- Pfad an, 100 ms Entprellung
ton         an, 48000 Hz, Lautstaerke 100 (0,0 dB), HDMI-Abgleich 0,00 dB
...
ereignis    SOURCE_CHANGE (changes 0x1, seq 1)
signal      kein Signal (Flip-Zeiger stehen)
konsole     Plane aus, RGB-Kanal und Selektor zurueck, Konsole entblankt
ton         stumm (kein Bild)
ereignis    SOURCE_CHANGE (changes 0x1, seq 2)
signal      1280x720p, 74250000 Hz Pixeltakt
puffer      1280x720 NV16, Zeilenabstand 1280 auf Panel 1920x1080
bild        Plane 38 an, 1920x1080 aus dem Capture-Ring
```

Bei einem Auflösungswechsel ist der kurze Konsolenmoment der echte Signalverlust der Quelle. Meldet der
Treiber den Wechsel als noch nicht eingerastet, steht `signal      Wechsel im Gang -- die Geometrie steht
noch nicht, warte`, und nach vierzig Nachfragen eine `warnung`, die sagt, was bleibt. `neu         SIGHUP --
Zustand neu bewertet` ist die Antwort auf `systemctl reload`.

---

## 6a. Steuerung: `h713-tv ctl`

Der Daemon hört auf dem UNIX-Socket `/run/h713-tv/ctl` (Option `-s PFAD`). Ein Befehl ist eine Zeile,
die Antwort beginnt mit `ok` oder `fehler`; `h713-tv ctl` gibt sie aus und liefert 0 bzw. 1 zurück.

```
h713-tv ctl status              Zustand: Betrieb, Signal, Plane/Konsole, Puffer, Ton (ton/ton-karten/ton-quelle/
                                 ton-msp/ton-pegel), dazu die Kernel-Zeilen incap/capture/farbwandler/signal/timings
                                 und die cpu_comm-Zeilen rx_calls/eingehend
h713-tv ctl auto                Bild folgt dem Signal (Vorgabe ohne tv.conf); `on` ist dasselbe
h713-tv ctl off                 Konsole erzwingen (Plane aus, Master weg, Konsole entblankt), bis "auto"
                                 auto/off werden über Neustarts gemerkt -- Abschnitt 6c
h713-tv ctl console             Konsole entblanken und Cursor einschalten, ohne die Plane anzufassen
h713-tv ctl list                alle Bildregler des Aufnahmeknotens mit Wert und Bereich
h713-tv ctl get REGLER          einen Regler lesen
h713-tv ctl set REGLER WERT     einen Regler setzen; Menüs auch per Text (set range full, set mode cinema)
h713-tv ctl preset NAME         Herstellervoreinstellung: Bildmodus + neun Regler aus pq_picturemode.ini
                                 (standard cinema vivid game computer hdr; mit den Gerätedaten zusätzlich
                                 energy_saving und custom). Verwirft die gemerkten Abweichungen im Speicher
h713-tv ctl save [--aus]        die neun Regler, das Preset und aspect merken (`/var/lib/h713-tv/werte`),
                                 `--aus` löscht die Datei. Nur hier wird geschrieben, nicht bei jedem `set`
h713-tv ctl aspect [NAME]       Einpassung der Quelle ins Panel (auto proportional full 16:9 4:3 zoom);
                                 ohne NAME anzeigen. Ein Wechsel baut das Bild neu auf (~0,5 s Konsole)
h713-tv ctl audio [on|off|auto] Ton erzwungen an / erzwungen stumm / dem Bild folgend (Vorgabe); ohne Wort anzeigen
h713-tv ctl volume [0..100]     Lautstärke des Codecs (`DAC Playback Volume`, wirkt auf HDMI- und Gerätetöne);
                                 0 = leiseste Stufe, 100 = 0 dB; ohne Zahl anzeigen (gelesen von der Karte)
h713-tv ctl mute [on|off]       Stummschaltung: DSP-Mute (HDMI) und der Schalter des Codecs; ohne Wort anzeigen
h713-tv ctl resync              Quelle neu wählen (S_INPUT 0 = THal_Vp_SetSource HDMI-1)
h713-tv ctl replug              der Quelle ein Aus- und Anstecken vorspielen: HPD 300 ms unten (S_EDID mit
                                 blocks=0), EDID neu laden (S_EDID, 4 Blöcke), HPD oben -- ~1 s, blockiert
h713-tv ctl rpc NAME [ARG…]     beliebiger RPC an die Firmware über /sys/kernel/debug/cpu_comm/call
```

Regler (Kurznamen → V4L2-Control): `brightness contrast saturation hue sharpness` (0…100),
`tnr snr dci black` (0…3: Off/Low/Middle/High), `range` (`auto|limited|full`, `THal_Vp_SetVideoRange`),
`mode` (`THal_Vp_SetPictureMode`, Menü mit den Namen der Firmware: 0 Vivid, 1 Standard, 2 Mild, 3 Game,
4 Calibrated, 5 Calibrated Dark, 6 Computer, 7 Cinema, 8 Home, 9 Sports, 10 Shop, 11 Animation, 12 HDR,
13 Graphic - Kernel 0132). Die Regler gehören dem Aufnahmeknoten (`0101`, `0126`); `v4l2-ctl
-d /dev/video1 --list-ctrls` zeigt dieselben.

**Die Presetwerte kommen seit dem 11.09.2026 aus den Gerätedaten**, nicht mehr aus einer Tabelle im
Programm - siehe Abschnitt 6d. Die Tabelle ist der Rückfall geblieben.

**Bildmodus und Voreinstellung sind zwei Dinge.** `set mode` schaltet nur den Modus der Firmware um; der
ändert **keinen** der neun Regler (statisch aus der Firmware gelesen, [S14](../../doku/nachtlog/S14-re-picture-mode.md)),
die `Get`-RPCs der Firmware sind Stubs, und `list` zeigt deshalb nach `set mode` zu Recht die alten Zahlen.
Was die Herstelleroberfläche bei „Kino" tut - Modus **und** die neun Werte aus `pq_picturemode.ini`
senden - macht `preset NAME`: erst `picture_mode`, dann `brightness … black` aus der `[HDMI1]`-Zeile
(standard 1, cinema 7, vivid 0, game 3, computer 6, hdr 12). `energy_saving` und `custom` haben keinen
eigenen Firmware-Modus. Game und Computer stoßen in der Firmware zusätzlich einen Fensterneubau an
(`SetLowLatency`/`Refresh`).

**`aspect`** ist Descriptor-Wort 35 über die Plane-Eigenschaft `aspect` (Kernel 0133): wie der
Fenstermanager der Firmware eine Quelle einpasst, die nicht 16:9 ist. `auto` ist die Regel der Firmware
(kennt 1:1, 4:3 und 2,21:1; alles andere wird auf das Panel gestreckt - 5:4 und 16:10 eingeschlossen),
`proportional` (Vorgabe) hält das Seitenverhältnis (16:9 unverändert, 4:3 wie bisher mit Balken, 1280×1024
als Fenster 285…1635 mit Balken, gemessen 08.09.), `full` streckt, `16:9`/`4:3` erzwingen, `zoom` schneidet.
Das Wort wird mit der nächsten Veröffentlichung gelesen; ein Wechsel am laufenden Bild nimmt die Plane
kurz herunter und wieder hoch ([S15](../../doku/nachtlog/S15-re-aspect-regel.md)).

**`replug`** ist der HPD-Zyklus aus S12 C: die Quelle soll glauben, das Kabel sei gezogen und wieder
gesteckt worden - für einen Modus, der nicht einrastet, oder eine Quelle, die auf einem Link schläft, den sie
für aufrecht hält. Der Weg ist der V4L2-Weg von doku/88 §3: `VIDIOC_G_EDID` liest die 512 B (HDMI-1.4- und
HDMI-2.0-Block hintereinander, für V4L2 ein EDID mit vier Blöcken) aus der Firmware, `VIDIOC_S_EDID` mit
`blocks = 0` legt den HPD-Pin (`ARISC_HDMI_HPD_DOWN`), nach 300 ms (die gemessene Untergrenze, M4) schreibt
`VIDIOC_S_EDID` dasselbe EDID zurück, was im ARISC-Treiber die komplette Stock-Sequenz fährt (EDID-Modul
zurücksetzen, hochladen, bestätigen, Audio-Modus, 5 V, HPD 200 ms unten, HPD oben). Vorher wird das Bild
abgeschaltet (sonst friert der Ring eine Sekunde auf dem letzten Rahmen ein), und **das gelesene EDID wird
geprüft, bevor der Pin angefasst wird**: beide Köpfe (`00 ff ff ff ff ff ff 00` bei Byte 0 und 256) und die
vier Blockprüfsummen. Fällt die Prüfung durch und es gibt keine frühere gute Lesung, passiert nichts
(`fehler … ohne lesbares EDID wird HPD nicht angefasst`); gibt es eine, geht die Kopie zurück. Das Programm
blockiert für die Dauer (~1 s, wie `rpc`). Danach kommt die Quelle über ihre eigenen `SOURCE_CHANGE`-Ereignisse
zurück - bei `ctl off` bleibt sie auf der Konsole. Schlägt das zweite `S_EDID` fehl, liegt HPD unten; das
sagt die Antwort ausdrücklich, und ein weiteres `replug` nimmt die Kopie.

**Woher das EDID kommt.** `VIDIOC_G_EDID` geht über `arisc_hdmi_get_edid()`, und das liefert **nach dem Start
nichts** (`ENODATA`) - doku/88 §8 führte das Rücklesen als ungemessen, am 11.09.2026 gemessen. Ohne EDID wird HPD
nicht angefasst, denn HPD unten ohne etwas zum Hochladen lässt die Quelle vor einem toten Anschluss stehen.
Deshalb gibt es drei Quellen in dieser Reihenfolge: das Rücklesen, sonst die Kopie der letzten guten Lesung in
diesem Lauf, sonst **`/lib/firmware/hy310-edid.bin`** (dieselben 512 B, die die Bootkette hochlädt, von
`h713-extract` aus dem Gerät gezogen). Jede Quelle wird gleich geprüft: Kopf und vier Prüfsummen.
Ist einmal etwas hochgeladen, **funktioniert das Rücklesen** - der erste `replug` nach dem Start nimmt also die
Datei, jeder weitere das Rücklesen. Die Antwort nennt die benutzte Quelle.

`rpc` ist bewusst roh: es gelten die Regeln der Firmware, und ein Aufruf, auf den die Treiber nicht
vorbereitet sind (etwa `THal_Vp_SetSource` mitten im Betrieb), kann das Bild kosten. Die Zeile darf
158 Zeichen lang sein, und das Programm blockiert für die Dauer des Aufrufs. Für alles, was einen Regler
hat, den Regler nehmen. Weitere Formalien: `status` (auch `st`) berichtet die **letzte Messung** aus dem
Ereignispfad, misst also nicht selbst; `on` ist ein Alias für `auto`; Reglernamen wie in `list`
(Unterstriche statt Leerzeichen, der Server trennt an Leerzeichen); der Socket gehört root (0660), ein
zweites `h713-tv` startet nicht (`/run/h713-tv/lock`).

**Konsole nach dem Rückschalten.** Beim Zurückgeben des Panels (Signalverlust, `off`, Programmende) und beim
Start entblankt das Programm die Konsole (`TIOCL_UNBLANKSCREEN`) und schaltet den Cursor ein (`ESC[?25h`);
am 08.09. stand die Konsole sonst eingefroren ohne Cursor da (`fb0/blank` = 4, Cursor per DECTCEM
versteckt - Verursacher nicht gefunden, `consoleblank` ist 0).

## 6b. Ton: der Tonpfad folgt dem Bild

Die Abtastwerte laufen so wenig durch dieses Programm wie die Bildpunkte. Der Weg ist
`HDMI-RX → MSP-DSP1 → I2SOUT1 → Codec-I2S-Fenster → DAC → Lautsprecher`, und drei Treiber besitzen ihn
([doku/101](../../doku/101-plan-audio-treiber.md) §1): der Aufnahmeknoten meldet den Zustand der Quelle als
schreibgeschützte V4L2-Regler `H713 Audio Present`/`H713 Audio Rate`/`H713 Audio Compressed` (Kernel 0136, mit
`V4L2_EVENT_CTRL` bei Änderung), der MSP-Treiber stellt die ALSA-Karte **`hy310hdmi`** ohne PCM, nur mit den Reglern
`HDMI Audio Switch`, `HDMI Playback Volume` (¼ dB, −100…0), `HDMI Mute Switch` und sysfs `state`/`levels` (0137), der
Codec auf der Karte **`H713 Audio Codec`** die Regler `DAC Source` {APB, I2S} und `I2S Rate` {32000, 44100, 48000}
(0135). Dieses Programm ist die einzige Stelle, die beide Hälften kennt - ob ein Bild steht und was die Quelle über
ihren Ton sagt - , und entscheidet deshalb nur, **wann** der Pfad geschaltet wird. Karten werden über ihren
Namen gesucht (die Nummern hängen von der Probe-Reihenfolge ab, wie bei `/dev/videoN`), höchstens 30 s lang im
Sekundentakt, weil der MSP-Treiber seine Insel und die DSP-Firmware nach eigenem Zeitplan hochfährt.

**Der Automat** (Regel aus doku/101 §1 E; „Bild" = Plane an):

| Zustand | Bedingung | was gesetzt wird | nächster Zustand |
|---|---|---|---|
| **stumm** | Bild ∧ Present ∧ ¬Compressed ∧ Rate ∈ {32000, 44100, 48000} (oder `audio on`) | `HDMI Mute Switch`:=1 (bleibt), `I2S Rate`:=Rate, `DAC Source`:=I2S, `HDMI Audio Switch`:=1, Timer 100 ms | **Entprellung** |
| **Entprellung** | nach 100 ms Bedingung erneut wahr | `DAC Playback Volume` unverändert, Codec-Schalter an (falls nicht `ctl mute on`), `HDMI Playback Volume`:=0 dB + Abgleich, `HDMI Mute Switch`:=0 | **an** |
| **Entprellung** | Bedingung inzwischen falsch (Quelle geflattert) | `HDMI Mute Switch`:=1, `HDMI Audio Switch`:=0, `DAC Source`:=APB | **stumm** |
| **an** | Bedingung falsch (kein Bild, kein Ton, Bitstrom, `audio off`, Programmende) | Mute:=1, Switch:=0, Source:=APB - sofort, ohne Entprellung | **stumm** |
| **an** | Rate der Quelle ≠ programmierte Rate | Mute:=1, `I2S Rate`:=neu, Source:=I2S, Switch:=1, Timer 100 ms | **Entprellung** |

Jede Änderung am Pfad geschieht **hinter dem DSP-Mute** (stumm → ändern → laut), weil der Master-Mute des DSP
innerhalb eines Abtastwerts still ist, Routen- und Ratenwechsel aber nicht (S16). Der Weg nach oben ist entprellt,
weil `Present` beim Moduswechsel flattert; der Weg nach unten nie. Die Codec-Rate **muss** der Quelle folgen - mit
48 kHz im Codec blieb eine 32-kHz-Quelle stumm (S16 20:45) - , deshalb ist ein Ratenwechsel ein kurzes Stummschalten
und kein Neuaufbau. Der Codec verweigert `I2S Rate` mit `-EBUSY`, wenn gerade ein PCM mit anderer Rate läuft
(S30 §4.3); das Programm meldet den Fehlschlag einmal im Journal und steht dann so, wie `ctl status` es zeigt.

**Lautstärke und Stummschaltung** (Entscheidung 08.09. 22:10): `ctl volume N` stellt die **Codec**-Lautstärke
`DAC Playback Volume` - sie sitzt hinter HDMI **und** Gerätetönen, eine Lautstärke, die mit der Quelle wechselte,
wären zwei. 0…100 wird linear auf den Wertebereich des Reglers abgebildet (0 = kleinster Wert, 100 = größter; auf
diesem Codec 63 Stufen zu 1,16 dB, also 50 ≈ −36 dB und 0 = −73 dB, leise, nicht aus). Die Antwort wird von der Karte
**gelesen**, nicht aus dem Gedächtnis wiederholt; ein `amixer` von anderswo erscheint deshalb in `ctl status`, statt
beim nächsten Ereignis überschrieben zu werden, und beim Start wird die Lautstärke nicht angefasst. Die DSP-Regler
bleiben dem Automaten: `HDMI Playback Volume` ist der feste Pegelabgleich HDMI gegen Gerätetöne (0 dB, S16-Referenz;
`-t`/`--hdmi-trim DB` senkt ihn), `HDMI Mute Switch` das Schweigen des Automaten. `ctl mute on` schaltet den DSP-Mute
(bei HDMI) und zusätzlich den Schalter des Codecs, falls er einen hat - der H713-Codec hat keine Mischstufe und
damit keinen `DAC Playback Switch`, sein `Line Out Playback Switch` (LINEOUT-Freigaben in `0x02030310`) ist der, den
es gibt; Reihenfolge: was stumm wird, wird zuerst stumm, was aufgeht, geht zuletzt auf. Ein `ctl mute` überlebt das
Programm auf dem Codec nicht (beim Beenden wird der Schalter zurückgesetzt), sonst wäre das nächste `aplay` aus
einem Grund still, den niemand mehr sieht.

**Ohne die Treiber** läuft alles wie bisher: fehlt eine der beiden Karten oder einer ihrer Regler, wird der Ton-Teil
nach 30 Versuchen mit einem klaren Satz abgeschaltet (`ton bleibt aus nach 31 Versuchen in 31 s: es fehlt die Karte
"hy310hdmi" …`), `ctl status` sagt es weiter, das Bild merkt nichts - kein ALSA-Aufruf liegt auf dem Weg zur Wand.
Fehlen nur die drei V4L2-Regler (Kernel ohne 0136), gibt es keinen Automaten, aber `ctl audio on` schaltet den Pfad
von Hand; fehlt `V4L2_EVENT_CTRL`, wird alle 250 ms gefragt. `-a none` öffnet gar keine Karte. `ctl status` zeigt
drei Zeilen, die übereinstimmen müssen: `ton` (was das Programm entschieden hat), `ton-karten` (was die Karten
wirklich halten, gelesen), `ton-quelle` (was der Aufnahmeknoten meldet), dazu `ton-msp state=…` und `ton-pegel …`
aus dem sysfs des MSP-Treibers.

## 6c. Startmodus und Merken: `/etc/h713/tv.conf`

Bis zum 11.09.2026 startete der Dienst immer in `auto` (doku/60, Marco 09.09.): weder ließ sich der Beamer
absichtlich auf der Konsole hochfahren und erst auf Zuruf auf HDMI schalten, noch überlebte ein `ctl off`
einen Neustart. Beides ist jetzt Einstellung - in **`/etc/h713/tv.conf`**, nicht in `/etc/h713/tvconfig`
(das ist das Verzeichnis der extrahierten PQ-Dateien, doku/107 §8). Gelesen wird die Datei einmal beim Start;
Option `-C` nennt eine andere.

```
# /etc/h713/tv.conf -- "schluessel = wert", # Kommentar
start = zuletzt          # auto | manuell | zuletzt
#zustand = /var/lib/h713-tv/modus   # oder none
```

| `start =` | beim Start | danach |
|---|---|---|
| `auto` | wie bisher: liegt ein Signal an, wird es gezeigt, sonst die Konsole | `ctl off` / `ctl on` wie gehabt |
| `manuell` | **Konsole**, egal ob ein Signal anliegt | `ctl on` (= `ctl auto`) schaltet auf HDMI, ab dann folgt das Bild dem Signal, bis `ctl off` |
| `zuletzt` | der Modus, der zuletzt per `ctl auto\|on\|off` gesetzt wurde - wie ein Fernseher, der seinen Eingang behält; noch nichts gemerkt: `auto` | wie `auto` |

**Fehlt die Datei, gilt `start = auto`** - das Verhalten vor dieser Datei. Das Overlay des Release-Rootfs
liefert sie mit `start = zuletzt` aus. Unbekannte Schlüssel oder Werte werden im Journal genannt (`warnung:
/etc/h713/tv.conf:12: start = "an" unbekannt …`) und ignoriert; ein Tippfehler wird nicht stumm zu `auto`.

**Gemerkt wird in `/var/lib/h713-tv/modus`**, ein Wort, `auto` oder `off`. Geschrieben wird **nur, wenn
sich der Modus ändert** (Wort in eine Nachbardatei, `fsync`, `rename` - nach einem Stromausfall steht das
alte oder das neue Wort, nie eine halbe Zeile). `/var/lib`, weil das Zustand ist und keine Konfiguration,
und weil das Journal auf diesem Gerät flüchtig ist (doku/107 §4). Die Unit gibt das Verzeichnis mit
`StateDirectory=h713-tv` frei - das ist unter `ProtectSystem=strict` der einzige beschreibbare Ort neben
`/run`. `zustand = none` schaltet das Merken ab, `zustand = /pfad` verlegt es. Der Modus wird auch bei
`start = auto` und `start = manuell` mitgeschrieben; gelesen wird er nur bei `zuletzt` - wer später auf
`zuletzt` umstellt, bekommt den tatsächlich letzten Stand.

Was gilt, steht im Journal beim Start und in `ctl status`:

```
konfig      /etc/h713/tv.conf: start = zuletzt, gemerkt -> Konsole, bis "h713-tv ctl on"; Modus wird gemerkt in /var/lib/h713-tv/modus
modus       auto -- gemerkt in /var/lib/h713-tv/modus          (nach einem ctl on, das etwas geaendert hat)
```

```
betrieb     aus (Konsole erzwungen)
konfig      /etc/h713/tv.conf: start=zuletzt; gemerkt=off in /var/lib/h713-tv/modus
```

Es gibt nur HDMI-1: „umschalten" heißt Konsole ↔ HDMI, und `on` erzwingt kein Bild ohne Signal - die Plane
braucht die Geometrie der Quelle. `on` ist deshalb `auto`: HDMI zeigen, sobald etwas da ist. Die Bindung des
manuellen Wechsels an Fernbedienung oder Taste (doku/60) ist damit vorbereitet, aber nicht Teil dieses Programms.

## 6d. Die Bildwerte: gerechnet, gewählt, gemerkt

Bis zum 11.09.2026 standen die sechs Presets als Zahlentabelle in `main.c` und die Gammakurve als
`gamma-standard.bin` im Repo - beide einmal aus den Herstellerdaten abgeleitet und seither eingefroren. Die
Werte waren richtig (am 11.09. nachgeprüft: die eingecheckte Kurve ist byteidentisch mit der, die aus den
Daten *dieses* Geräts gerechnet wird, und die Presets setzen alle Register wie `pq_picturemode.ini`).
Falsch war die **Herkunft**: ein anderes Panel hätte dieselbe Tabelle aufgezwungen bekommen, zwei der acht
Presets fehlten, und von den fünf Gammastufen gab es eine. Plan 113 §A hat das umgedreht.

**Drei Schichten, in dieser Reihenfolge angewandt:**

| # | Schicht | Woher | Wann |
|---|---|---|---|
| 1 | Herstellerdaten | `/etc/h713/tvconfig/`, gerechnet von `h713-pq` | bei jedem Start |
| 2 | Wahl des Nutzers | `preset =` in `/etc/h713/tv.conf` | bei jedem Start |
| 3 | Abweichungen des Nutzers | `/var/lib/h713-tv/werte` | bei jedem Start, **über** Schicht 1 |

Fehlt eine Schicht, greift die darunter. Fehlt alles, bleibt die einkompilierte Tabelle - **ein Gerät ohne
Extraktion zeigt trotzdem ein Bild.**

### Wer rechnet: `h713-pq`, einmal, als Kindprozess

`h713-pq` ist Python und liest die acht extrahierten Vendor-Dateien. Die Rechnung existiert damit **einmal**
und wird nicht in C nachgebaut - dieselbe Rechnung zweimal zu pflegen ist genau die Falle, aus der die
Sättigungskorrektur vom 07.09. kam (Plan 113 §A.3, Weg (a)).

```
h713-pq --daten /etc/h713/tvconfig show HDMI1 standard --json --lut /run/h713-tv/gamma-laufzeit.bin
```

Ein Satz JSON auf `stdout`, alles andere nach `stderr` (und damit ins Journal). Der Satz enthält die
Bildmodusnummer der Firmware, die neun Regler, den Gamma-Exponenten, den Pfad der geschriebenen LUT - und
**alle** Bildmodi dieses Eingangs mit ihren Werten, damit `ctl preset energy_saving` im Betrieb keinen
zweiten Python-Start braucht. Die Felder stehen in `h713-pq/README.md`.

Der Kindprozess wird **vor** dem Öffnen von Aufnahme- und DRM-Gerät gestartet und erst eingesammelt, wenn
die Kurve gebraucht wird; der Rest des Starts läuft daneben. Am Gerät gemessen (11.09.): `h713-pq`
braucht **430-530 ms**, die Geräte sind nach 25 ms offen - der Start bis „Plane an" geht damit von
**255-286 ms auf 650-680 ms**. Das ist der Preis der Herkunft, und er liegt weit innerhalb der Frist von
2 s, nach der abgebrochen wird.

### Wenn etwas fehlt

Jeder dieser Fälle endet in der einkompilierten Tabelle, einer Zeile im Journal und einem Bild - nie in
einem Abbruch:

```
warnung: bildwerte   rechner = none -- es gilt die einkompilierte Tabelle
warnung: bildwerte   /usr/local/bin/h713-pq: No such file or directory -- ...
warnung: bildwerte   Rueckgabe 2 (Datenverzeichnis unvollstaendig?) -- ...
warnung: bildwerte   laenger als 2000 ms -- abgebrochen -- ...
warnung: bildwerte   keine JSON-Ausgabe (47 Byte) -- ...
warnung: preset      "energy_saving" gibt es nicht (standard cinema vivid game computer hdr) -- standard
```

### Was gemerkt wird, und wann

`/var/lib/h713-tv/werte`, neben dem `modus` desselben Verzeichnisses, im Format von `tv.conf`:

```
preset      = vivid
brightness  = 50
…
sharpness   = 30
aspect      = proportional
```

Geschrieben **nur von `h713-tv ctl save`**, `ctl save --aus` löscht die Datei. Nicht bei jeder
Reglerbewegung: wer die richtige Schärfe sucht, fährt den Regler durch, und ohne diese Regel merkte sich das
Gerät genau den Zwischenstand, bei dem der Strom ausfiel - und schriebe für eine Entscheidung ein Dutzend
Mal auf die eMMC. Die Betriebsart `auto`/`off` bleibt die Ausnahme und wird weiter sofort gemerkt: sie ist
eine Entscheidung, keine Suchbewegung.

Geschrieben wird, was der **Treiber** hält, nicht eine mitgeführte Kopie - damit ist auch die Regel „ein
`ctl preset` verwirft die gemerkten Abweichungen" ohne Buchhaltung erfüllt: nach einem Preset hält der
Treiber die Presetwerte, und genau die schreibt ein späteres `save`. Die Datei geht über eine Nachbardatei
mit `fsync` und `rename` an ihren Platz.

**Die Zeile `preset =` entscheidet, ob die Werte passen.** Gemerkte Werte sind Abweichungen *von einem
Preset*; würde man die Zahlen von `vivid` über einen Start in `cinema` legen, wäre `cinema` still zu `vivid`
geworden. Deshalb werden sie angewandt, wenn sie zum gestarteten Preset gehören, und sonst im Journal
genannt und liegen gelassen:

```
warnung: gemerkt     gemerkt fuer Preset energy_saving, gestartet wird standard -- nicht angewandt
```

Mit `preset = zuletzt` in `tv.conf` - der Einstellung, für die das gebaut ist - stimmen beide immer überein.

Ein gemerkter Wert außerhalb des Reglerbereichs wird **einzeln** verworfen, mit seiner Zeilennummer; die
anderen acht gelten weiter. Der Bereich ist der des Treibers (`VIDIOC_QUERY_EXT_CTRL`), keine zweite Tabelle:

```
warnung: /var/lib/h713-tv/werte:12: sharpness = 500 liegt ausserhalb 0..100 -- verworfen
warnung: /var/lib/h713-tv/werte:15: dci = 9 liegt ausserhalb 0..3 -- verworfen
warnung: /var/lib/h713-tv/werte:17: aspect = "quetschen" kennt die Plane nicht (auto proportional full 16:9 4:3 zoom) -- verworfen
```

### Die Schlüssel in `tv.conf`

```
preset  = NAME | zuletzt     # NAME aus ctl help; zuletzt = das gemerkte Preset. Vorgabe standard
daten   = VERZ | none        # Vorgabe /etc/h713/tvconfig; none = Gerätedaten nicht benutzen
rechner = PFAD | none        # Vorgabe /usr/local/bin/h713-pq; none = nicht rechnen
```

Auf der Befehlszeile heißen sie `-p`, `--daten` und `--rechner`; dazu `--eingang` (Vorgabe `HDMI1`) und
`--lut` (Vorgabe `/run/h713-tv/gamma-laufzeit.bin`). Die Befehlszeile hat das letzte Wort, die Datei ist
die stehende Einstellung. `-g` gilt weiterhin als ausdrücklicher Befehl und schlägt die Kurve von
`h713-pq`.

Was gilt, sagt `ctl status`:

```
bildwerte   8 Presets aus /etc/h713/tvconfig (h713-pq, 433 ms), Gamma 2.20, LUT 2048 Byte
preset      vivid (aus den Geraetedaten)
gemerkt     /var/lib/h713-tv/werte: preset=vivid brightness=50 contrast=55 saturation=60 hue=50 sharpness=30 tnr=2 snr=1 dci=3 black=1 aspect=proportional
```

## 7. Der Descriptor, die Firmware und was das Programm davon sieht

Jedes Einschalten der Plane mit neuer Geometrie **veröffentlicht den VidDec-Descriptor neu** (Kernel 0117),
und die Firmware antwortet mit einem vollständigen Neubau ihrer Fensterkette: Scaler, Fenster, Farbwandler,
Capture-Freigabe. Die Capture geht dabei kurz aus, der Aufnahmetreiber setzt den Farbwandler zurück und
gibt sie wieder frei (0121-0123). Alles davon passiert im Kernel; dieses Programm sieht es nur als
`V4L2_EVENT_SOURCE_CHANGE` und fragt dann `QUERY_DV_TIMINGS`.

Diese Frage hat drei Antworten:

| Antwort | Bedeutung | Programm |
|---|---|---|
| Timing | Signal steht, Geometrie bekannt | Puffer bauen, Plane an |
| `-ENOLINK` / `-ENODATA` | kein Signal | Plane aus, Konsole |
| `-ENOLCK` | Wechsel im Gang: Firmware-Signalinfo und Capture-Block sagen noch Verschiedenes | nachfragen (50 ms × 40), Wand in Ruhe lassen |

Nach der vierzigsten Nachfrage bleibt, was steht: ein Bild ist echter HDMI-Inhalt und wird nicht wegen
einer unentschiedenen Frage abgeschaltet; steht die Konsole, wird alle 500 ms weitergefragt, weil dann
kein Ereignis mehr kommen muss. Die frühere Ringbeobachtung (Abtastreihe nach dem Einschalten) ist
entfallen: seit 0121 bewegen sich die Flip-Zeiger auch ohne laufende Capture, sie hat nichts mehr gemessen
([doku/nachtlog/S12](../../doku/nachtlog/S12-hy310-tv-review.md) A4).

**Konsole zurück heißt auch: Konsole benutzbar.** Beim Start und bei jeder Rückgabe entblankt das Programm
die Konsole (`TIOCL_UNBLANKSCREEN`, `fb0/blank` = 0) und schaltet den Cursor ein (`ESC[?25h`); der Kernel
hält seit 0127 den Cursor-Timer auch dann am Leben, wenn `console_trylock` gerade scheitert.

## 8. Grenzen

- **Ein Signal, eine Quelle.** HDMI-1 über `SetSource 3`; andere Eingänge der Firmware sind nicht angebunden.
- **Geometrie:** höchstens Panelgröße, Höhe durch 2 teilbar. Die Breite darf beliebig sein: der Ring hat
  Zeilen im Abstand `rowbyte·16` (INCAP `0x924`, Breite auf 16 aufgerundet), der Treiber meldet ihn als
  `bytesperline` (Kernel 0131) und das Programm baut den Puffer damit - 1366×768 läuft so mit 1376 Byte je
  Zeile (gemessen 08.09.). Was die HDMI-Firmware einrastet, steht in ihrer Tabelle (`kHalSignalID_*`):
  CEA-Modi und die üblichen VESA-Modi mit 60 Hz; 120-Hz-Varianten und 1600×900 nicht.
- **`rpc` ist roh.** Der Aufruf blockiert das Programm für seine Dauer, und die Firmware prüft nichts für uns.
- **`preset`** ist keine Firmwarefunktion, sondern Modus + neun `Set`-RPCs; wer andere Werte will, setzt sie
  einzeln und merkt sie mit `ctl save` (Abschnitt 6d).
- **Die Gammakurve wird einmal beim Start geladen.** Ein `ctl preset` auf einen Modus mit einer anderen
  Gammastufe setzt die neun Regler, nicht die Kurve - es sagt das in der Antwort. In den Daten dieses Geräts
  tritt der Fall nicht auf (alle acht Modi stehen auf Stufe 3 = 2,2).
- **Nur `HDMI1`.** `h713-pq` wird nach genau diesem Eingang gefragt (`--eingang`); die INI führt für
  `HDMI1`, `HDMI2` und `HDMI3` ohnehin dieselben Zeilen.
- **Ein Auflösungswechsel kostet ~1 s Konsole** - das ist der echte Signalverlust der Quelle beim Modewechsel.
- **Ton nur mit beiden Karten.** `hy310hdmi` und `H713 Audio Codec` werden zusammen genommen oder gar nicht - eine halbe
  Kette (Lautstärke ohne Route, Route ohne Mute) wird nicht angefasst; dann gibt es auch kein `ctl volume`.
- **Nicht-PCM bleibt stumm.** Bitströme (Dolby/DTS, `H713 Audio Compressed`) werden nicht dekodiert; der Automat schaltet
  den Pfad dafür ab. Raten außerhalb von 32/44,1/48 kHz kennt der Codec-Regler nicht → stumm mit Begründung.
- **Der Codec-Schalter ist ein Analogschalter.** `Line Out Playback Switch` hat auf H713 keinen Rampenregler (0x31c
  fehlt); ob das Schalten knackt, ist am Gerät zu hören. Knackt es, ist die Kandidatenliste `audio_codec_mutes[]` in
  `main.c` die eine Stelle, an der der Schalter wieder herausgenommen wird (dann ist `ctl mute` nur der DSP-Mute).

## 9. Verweise

* [doku/78](../../doku/78-nachtplan-hdmi-switch.md) Anhang A - der vollständige Ablauf, A.4 das Zielbild
* [doku/86](../../doku/86-video-plane-nv16.md) - die Video-Plane, Register für Register
* [doku/88](../../doku/88-v4l2-hdmirx.md) - der V4L2-Empfänger, Puffermodell und Ereignisse
* [doku/101](../../doku/101-plan-audio-treiber.md) - der Ton als Treiber: Pakete A-F, die verbindlichen Regler- und Kartennamen
* [doku/nachtlog/S32](../../doku/nachtlog/S32-treiber-e-hy310tv.md) - Paket E: der Automat als Tabelle, Testrezept
* [doku/nachtlog/S16](../../doku/nachtlog/S16-hdmi-audio.md) - die Messungen, aus denen die Reihenfolge stumm→ändern→laut stammt
* [doku/nachtlog/K4-hotplug.md](../../doku/nachtlog/K4-hotplug.md) - Signalverlust und -rückkehr am Gerät
* [doku/nachtlog/D-abnahme-board.md](../../doku/nachtlog/D-abnahme-board.md) - die Plane am Gerät, und der
  Sekundentakt, der **nicht** trägt, was ihm zugeschrieben wurde
* [doku/nachtlog/D-cstride-fix.md](../../doku/nachtlog/D-cstride-fix.md) - dieselbe Tabelle neu gelesen:
  der Zeiger löst das Firmware-Ereignis aus, nicht der Inhalt, und die einzige gemessene Schranke ist „< 1 s"
* [doku/nachtlog/A6-4-aufloesungswechsel.md](../../doku/nachtlog/A6-4-aufloesungswechsel.md) - der
  Auflösungswechsel ohne Ereignis (§8)
* [doku/nachtlog/F-korrektur.md](../../doku/nachtlog/F-korrektur.md) - **gültige Abnahmevorschrift**,
  Prüfbau, was an der 3-s-Konstante falsch war
* [doku/nachtlog/F-startklar.md](../../doku/nachtlog/F-startklar.md) - Prüfbau und korrigierte Annahmen
  vom 07.09. früh; §2.2, §2.4 und §5 sind durch `F-korrektur.md` überholt
* `analyse/kms/hdmi_plane_test.c` - dasselbe von Hand, für einen einzelnen Versuch
* `legacy/userspace/hy310-hdmird/` - der Vorgänger aus der Legacy-Welt (gelesen, nicht portiert:
  seine Aufgabe, die Firmware-Init, machen jetzt die Treiber 0091/0092/0094)
