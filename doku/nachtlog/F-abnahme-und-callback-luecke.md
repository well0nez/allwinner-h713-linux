# F am Gerät - und die Lücke, die dabei sichtbar wurde (Board-Agent, 09:07-09:13)

## F läuft, und zwei Fehler in F sind dabei aufgefallen

**Fehler 1 (im Bauverfahren, meiner):** `make cross` im Container aufgerufen - der sieht
`/srv/h713-rootfs` nicht, der Makefile sagt das ausdrücklich. Auf dem Arbeitsrechner baut es sauber.

**Fehler 2 (in F, echt und nur durch Ausführen zu finden):** die Bestätigung des gefundenen Geräts
verglich `vcap.driver` per `strcmp()` gegen `"sun50i-h713-hdmirx"`. `struct v4l2_capability` hat aber
`__u8 driver[16]` - der Kernel meldet höchstens 15 Zeichen, bei uns `sun50i-h713-hdm`. Der Vergleich
konnte auf **keinem** Board zutreffen; F brach mit „kein V4L2-Geraet mit dem Namen …" ab, obwohl
`/sys/class/video4linux/video1/name` genau diesen Namen trug.

Das ist das **Spiegelbild** des Fehlers, den die Gegenprüfung heute früh gefunden hat: dort ein
Kriterium, das nicht scheitern konnte, hier eines, das nicht gelingen konnte. Behoben durch
`strncmp(..., sizeof(vcap.driver) - 1)` mit Begründung im Quelltext; die volle Namensprüfung macht
ohnehin die sysfs-Zeile darüber.

**Danach im Trockenlauf:**

```
aufnahme    /dev/video1 (sun50i-h713-hdm, H713 HDMI receiver)
anzeige     /dev/dri/card1 (sun50i-h713-afbd)
crtc        36, Modus 1920x1080
plane       38, NV16, Betriebsart hdmi-ring
signal      vorhanden
```

**Im echten Lauf** kommt das Bild (Wand mean 131,2, std 48,6), und F protokolliert vorbildlich:
es benennt seinen blinden Fleck von sich aus, und die Ring-Beobachtung sagt, worüber sie **nichts**
aussagt („Beobachtungsfrist von 2000 ms erreicht … über die Zeit danach sagt diese Zeile nichts").

## Was F **nicht** kann - und warum das nicht an F liegt

**Signalverlust wird nicht bemerkt.** Quelle per `xrandr --off` abgeschaltet: die Wand zeigt weiter
das eingefrorene Bild (mean 130,4 gegen 131,2), der Selektor bleibt auf `0x39000000`, und F's Log
bekommt keine Zeile. F sitzt in `poll()` und wartet auf `V4L2_EVENT_SOURCE_CHANGE`.

**Die Ursache ist gemessen und liegt nicht in F.** Bei laufendem elog (Stufe 5), Quelle aus und wieder an:

```
W/hdmirx   [559018] (./THDMIRx_Port.cpp 299)      port1 invalid signal!!!
I/app      [559018] (./app_top_projector.cpp 919) CallbackOfSignalChange
I/app      [559019] (./app_callback.cpp 66)       NotifySignalChange
I/app      [566116] (./app_top_projector.cpp 919) CallbackOfSignalChange     <- Rueckkehr
```

zehn passende Zeilen insgesamt - und gleichzeitig im Treiber:

```
SignalChange: 0 mal, Para[]
HotPlug:      0 mal, Para[]
```

**Die Firmware feuert, der Treiber sieht nichts.** Der Bruch liegt in der Zustellung zwischen beiden.

## Was daran hängt

Dieselbe Lücke erklärt drei Beobachtungen, die bisher einzeln notiert waren:

1. **F fällt bei Signalverlust nicht auf die Konsole zurück** (dieser Abschnitt).
2. **`V4L2_EVENT_SOURCE_CHANGE` feuert nie** - in *allen* Läufen von `hdmirx_test` stand
   `0 SOURCE_CHANGE`, auch dort, wo das Signal nachweislich weg war. Das hätte mir früher auffallen
   müssen; ich habe es als Nebensache gelesen.
3. **Der Auflösungswechsel** (`A6-4-aufloesungswechsel.md`) ist über V4L2 heute nicht zu bemerken -
   auch deshalb, weil der einzige Ereignisweg tot ist.

## Der Ort ist eingegrenzt, die Ursache noch nicht

- **Firmware:** feuert. Gemessen, oben.
- **Treiber `0094`:** zählt null. Gemessen, oben.
- **Dazwischen:** die Registrierung (`RegisterSignalChangeCallback(11)` in der Probe-Tabelle von
  `0094`) und die Zustellung der eingehenden MIPS→ARM-CALLs an Kernel-Handler
  (`cpu_comm_register_callback` aus `0092`, Zustellpunkt in `command_action()`).

Bemerkenswert: der **HotPlug**-Callback zählt ebenfalls null - und der lief in der Nacht über den
Userspace-Pfad nachweislich (`prep`-Ausgabe: `<- CALLBACK MipsHalCallback_HdmiHotPlugByPortHandler`).
Beide Kernel-Handler bekommen also nichts, während der Char-Device-Pfad damals funktionierte. Das ist
der erste Ort zum Nachsehen.

## Zustand am Ende

F läuft weiter, Bild steht. Die Quelle ist wieder angeschaltet und verbunden.
