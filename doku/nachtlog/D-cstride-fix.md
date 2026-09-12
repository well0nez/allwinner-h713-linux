# D — der C-Stride greift jetzt aus jedem Vorzustand (Offline-Agent, 07.09., 07:10–08:30)

Anschluss an [D-cstride-befund.md](D-cstride-befund.md). **Kein Board angefasst** — alles hier ist am
erzeugten Baum gelesen und geändert; die Abnahme steht am Ende als kopierbare Vorschrift.

---

## 1. Die Ursache

**Der Treiber erledigt zwei Geschäfte in einem Commit, und das zweite zerstört das Ergebnis des ersten.**

`h713_afbd_video_atomic_update()` schrieb bisher

1. den **Descriptor-Zeiger** `+0x098…+0x0A4` — für die MIPS ein **VideoDec-Signalereignis**, sobald der
   Zeiger vorher nicht schon stand —, und
2. den **Registersatz von Source 0**, darunter den absichtlich verdoppelten NV16-Chroma-Stride,

in derselben Folge. Auf das Signalereignis läuft die Firmware `HandleSignalEvent` → WCE und **programmiert
Stride- und Modusregister neu** — das ist nicht neu, das steht seit dem 06.09. in doku/76 §11.3 („sie
schrieb Stride- und Modusregister"), und die sichtbare Quittung desselben Ereignisses ist INCAP
`0x06940928` Bit 31 → 0 (doku/78 Stufe 7a, Korrektur vom 07.09. 22:35).

Die WCE rechnet dabei alles aus **dem Descriptor**. Der kennt genau **einen** Stride (Wort 22 = 1920):

| Register | Treiber will | WCE rechnet | |
|---|---|---|---|
| `+0x020` | `0x043F077F` | `0x043F077F` | gleich |
| `+0x024` | `0x00420077` | `0x00420077` | gleich |
| `+0x040` Y-Stride | `0x780` | `0x780` | gleich |
| `+0x048` / `+0x04C` | `0x04380780` / `0x021C0780` | dieselben | gleich |
| **`+0x044` C-Stride** | **`0x0F00`** | **`0x780`** | **verschieden** |

**Damit ist beantwortet, warum ausgerechnet der C-Stride betroffen ist** und Selektor, Geometrie, Crop und
Descriptor-Zeiger nicht: der C-Stride ist der einzige Wert des Satzes, mit dem der Treiber der Hardware
absichtlich etwas anderes sagt als dem Descriptor (Abschnitt 3 in doku/86 — NV16 durch einen NV12-Leser).
Alle anderen Register „kommen an", weil sie **ohnehin schon** oder **wieder** den Wert tragen, den der
Treiber schreiben wollte. Sie sind kein Gegenbeweis, sie sind ununterscheidbar.

### Der Beleg: eine Variable trennt alle sechs Läufe

`afbd_source0.py off` nullt `+0x098…+0x0A4` mit (`w(AFBD, 0x98 + 4*i, 0)`), der Kaltstart hat den Zeiger nie
gesetzt — im Messprotokoll vom 06:15 steht er bei +1 s ausdrücklich auf `0x00000000` und springt bei +2 s
auf `0x4D95F000`, im selben Takt, in dem `0x06940928` von `0xE0020438` auf `0x60020438` fällt. Der
Treiber-Disable dagegen lässt den Zeiger absichtlich stehen.

| Vorzustand `+0x044` | `+0x098` **vor** dem Enable | nach dem Enable |
|---|---|---|
| `0x0780` Kaltstart | **`0`** (belegt, 06:15-Tabelle) | `0x0780` ❌ |
| `0x0780` nach `afbd_source0.py off` | **`0`** (das Skript nullt es) | `0x0780` ❌, zweimal |
| `0x0780` von Hand gepokt | `0x4D95F000` (voriger Zyklus) | `0x0F00` ✓ |
| `0x00000044` Marke von Hand | `0x4D95F000` | `0x0F00` ✓ |
| `0x0F00` voriger Plane-Zyklus | `0x4D95F000` | `0x0F00` ✓, vier Zyklen |

Sechs Läufe, drei Ausgänge, **eine** Variable — und es ist nicht der Wert, sondern der Zeiger.

### Warum die beiden widerlegten Hypothesen davon unberührt bleiben

* „Die Firmware überschreibt den C-Stride" wurde als **dauerndes** Überschreiben widerlegt: 22 s im
  Sekundentakt, `0x0780` durchgehend. Das hier ist kein Dauerzustand, sondern **ein einziges Ereignis**,
  ausgelöst vom Zeigerwechsel — und es lag vollständig zwischen den Abtastungen +1 s und +2 s, in denen der
  Treiber überhaupt erst geschrieben hat (`+0x010` ging in genau diesem Fenster von `0x03000010` auf
  `0x03000013`). Die Sekundenreihe kann es gar nicht gesehen haben.
* „Der Treiber schreibt ihn gar nicht" bleibt widerlegt — er schreibt ihn, und er schrieb ihn auch in den
  Fehlläufen; nur wurde er danach wieder überschrieben.

### Die Abweichung vom belegten Skriptablauf

Das Rezept, das am Gerät seit dem 06.09. funktioniert, trennt beides in **zwei** Schritte:

* **Stufe 7a** `viddec_descriptor.py set` — Seite + Zeiger, das Signalereignis, danach der HPD-Zyklus.
* **Stufe 7b** `afbd_source0.py on` — der Registersatz, mit `0x044 = 0xF00` als Schritt 7 von 11.

Dort schreibt Schritt 5 den Zeiger noch einmal, aber **auf denselben Wert** — kein Ereignis. Der
C-Stride hat in diesem Ablauf nie gewackelt. Der Treiber hatte 7a und 7b in einen Zug gezogen; das ist die
Abweichung, und sie war nicht begründet. Alle übrigen Abweichungen bleiben begründet: der Treiber schreibt
zusätzlich Geometrie `+0x020/+0x024` und Crop `+0x048/+0x04C` (das Skript verlässt sich auf die
Firmware-Werte — „happened to be right on one board and is not a description", 0093), und er folgt dem Ring
statt alle vier Slots festzunageln.

---

## 2. Was geändert wurde (`0093`, nur Treiber)

1. **Die vier Zeigerworte wandern in die Veröffentlichung.** Sie standen im Rumpf des `atomic_update` und
   wurden bei **jedem** Commit geschrieben; damit konnte jeder Commit ein Signalereignis sein. Jetzt gehören
   sie zu `h713_afbd_publish_video_info()` und werden einmal beim Übergang „aus → an" geschrieben — dieselbe
   Lebensdauer, die der Disable-Pfad ihnen ohnehin schon gibt (er nullt sie bewusst nicht).
2. **`h713_afbd_publish_video_info()` meldet das Ereignis** (`bool`): neue Seite **oder** neuer Zeiger.
   Der „refusing to rewrite"-Zweig kehrte früher vorzeitig zurück; da der Zeiger jetzt in dieser Funktion
   liegt, wird die Warnung ausgegeben **und** der Zeiger trotzdem gesetzt.
3. **Der Enable klammert das Ereignis.** Vor der Veröffentlichung parkt er in `+0x044` eine Marke, die die
   WCE nicht erzeugen kann — `0` ist kein gültiger Stride —, und wartet danach in `h713_afbd_wait_wce()`
   (`readl_poll_timeout`, 100 µs, Frist 200 ms), bis die WCE sie ersetzt hat. Erst dann wird Source 0
   programmiert. Kein `msleep`, kein zweites Schreiben „zur Sicherheit": gewartet wird auf ein benanntes,
   beobachtetes Ereignis, und beim Fristablauf steht eine `drm_warn`-Zeile im Log statt eines stillen
   Fehlers.
4. **Nur für NV16.** Für NV12 rechnet die WCE denselben Chroma-Stride aus, den die Plane will — kein
   Verlust, nichts zu warten, keine Wartezeit und keine Warnung auf dem Cedrus-Pfad.
5. **Der Disable stellt `+0x044` zurück** auf den beim Probe gelesenen Wert (`video_c_stride_idle`).

Die 200 ms sind bewusst weit: die Firmware antwortet auf ihrer eigenen Capture-Schleife mit 60 Hz, und die
einzige gemessene Schranke ist „innerhalb einer Sekunde" (die Lücke zwischen den Abtastungen +1 s und +2 s).

### Die Entscheidung zum Disable-Pfad, begründet

**Ja, er soll zurückstellen — auf den beim Probe gelesenen Wert, auf unserem Board `0x0780`.**

* Jedes **andere** Stück Source-0-Zustand, das die Plane anfasst, wird im Disable schon aus einem gemerkten
  Wert zurückgestellt: CTRL `+0x010`, Chroma-Gain `route +0x508`, RGB-Kanal `+0x140`, Selektor
  `lvds +0x06C`. Der verdoppelte Stride war der einzige, der stehen blieb — das war keine Entscheidung,
  sondern eine Lücke.
* Der Rest ist nicht folgenlos, sondern **messverfälschend**: genau er hat die D-Abnahme vom 07.09. 06:10
  bestanden lassen, obwohl der Erst-Enable kaputt war — `0x0F00` stand noch vom Skript. Ein Treiber, der
  seinen eigenen Fehler durch seinen eigenen Rest verdeckt, ist die schlechteste Sorte.
* **Warum der gemerkte Wert und nicht `0x780` fest verdrahtet:** dieselbe Regel wie bei CTRL und Selektor —
  der Treiber übernimmt eine laufende Anzeige und stellt her, was er vorgefunden hat. Auf unserem Board ist
  das `0x780`, also derselbe Wert, den auch `afbd_source0.py off` schreibt (Nachtplan A.3). Anders als bei
  CTRL und Selektor wird er **nicht** gegen einen Sollwert geprüft: er ist ein Stride, also eine Eigenschaft
  der Quelle, die die Firmware zuletzt konfiguriert hat, nicht eine Eigenschaft der Übergabe, die dieser
  Treiber verlangt.
* Der **Y**-Stride `+0x040` braucht nichts: der Treiber schreibt dort `pitch` = `0x780`, also ohnehin den
  Ruhewert.

---

## 3. Belegt / erschlossen — sauber getrennt

**Belegt (Messung liegt vor):**

* Die Zustandstabelle in Abschnitt 1 — sechs Läufe, drei Ausgänge, `+0x098` trennt sie vollständig.
* `+0x098` ist beim Kaltstart `0` und wechselt im Enable auf `0x4D95F000` (06:15-Tabelle).
* `afbd_source0.py off` nullt `+0x098…+0x0A4` (Quelltext des Skripts).
* Der Treiber-Disable lässt den Zeiger stehen (Quelltext, ausdrücklich kommentiert).
* Der Zeigerwechsel ist ein Firmware-Ereignis: `0x06940928` Bit 31 fällt im selben Takt (06:15-Tabelle,
  doku/78 Stufe 7a).
* Ein Signalereignis lässt die Firmware **Stride- und Modusregister** schreiben (doku/76 §11.3, 06.09.).
* Der Treiber schreibt `+0x044` tatsächlich (Markentest `0x00000044` → `0x0F00`).

**Erschlossen (noch nicht einzeln gemessen):**

* Dass zu den „Stride-Registern" der WCE genau `+0x044` gehört und dass sie dort `pitch` = `0x780` hinein
  schreibt. Das ist die naheliegendste Lesart — sie erklärt alle sechs Läufe und verlangt keine weitere
  Annahme —, aber der Schreibvorgang selbst ist nie beobachtet worden, weil `0x780` vorher wie nachher
  dasteht.
* Dass die WCE das tut, **solange Source 0 noch aus ist**. Darauf wartet die Klammer.
* Dass sie innerhalb von 200 ms antwortet. Gemessen ist nur „< 1 s".

Trifft der erste Punkt nicht zu, läuft die Klammer in ihre Frist, schreibt
`firmware did not reprogram the chroma stride after the descriptor` ins Log und der Fehler bleibt — aber
er ist dann **diagnostiziert** statt still. Das ist der einzige Weg, den ich ohne Board gehen kann, ohne zu
raten.

**Die Messung, die es entscheidet** (Abschnitt 4, Teil C): eine Marke in `+0x044`, gesetzt im
*Fehler*-Vorzustand. Kommt am Ende `0x0780` heraus, hat **etwas geschrieben** — die Firmware; bleibt die
Marke stehen, wurde der Schreibvorgang des Treibers verworfen und die Ursache ist eine andere. Der bisherige
Markentest lief nur im *guten* Vorzustand und kann das nicht entscheiden.

---

## 4. Abnahmevorschrift (kopierbar)

Voraussetzung: Kaltstart, Bring-up bis Stufe 6 gefahren (`prep_ohne_arisc.sh`, SetSource, EDID/HPD), Signal
gelockt, **`viddec_descriptor.py` NICHT von Hand aufrufen** — der Descriptor gehört jetzt dem Treiber.
`hdmi_plane_test` immer so starten, dass die Sitzung ihn nicht mitreißt (D-abnahme-board.md, Nebenbefund).

```bash
B=root@192.168.8.141
plane_on()  { ssh $B 'cd /root && setsid sh -c "nohup ./hdmi_plane_test -t 60 >/root/plane.out 2>&1 &"'; }
plane_off() { ssh $B 'pkill -f hdmi_plane_test'; }
regs()      { ssh $B 'for r in 0x05600044 0x05600098 0x05600040 0x05600020 0x0560004c 0x051c006c; do \
                        printf "%s=%s " $r $(busybox devmem $r); done; echo'; }
```

### A — der Fehlerfall, ausdrücklich (Kaltstart, Erst-Enable)

```bash
regs                       # ERWARTET: 0x05600044=0x780  0x05600098=0x0   (jungfräulich)
plane_on; sleep 6
regs                       # SOLL: 0x05600044=0xF00   0x05600098=0x4D95F000   0x051C006C=0x39000000
ssh $B 'dmesg | tail -20'  # SOLL: KEINE Zeile "did not reprogram the chroma stride"
```

Danach die Capture wieder scharf machen (der Descriptor hat sie abgeschaltet — Nachtplan A.5, Zeile
„Bild steht still"), dann Foto:

```bash
ssh $B 'cd /root; python3 arisc_hdmi.py --no-probe raw --sub-cmd 0x0211 --arg1 0 --arg2 2 --settle 0.6; \
        sleep 8; python3 arisc_hdmi.py --no-probe hotplug --port 0 --value 1 --settle 1.0'
python3 analyse/hdmi-seq/wandcheck.py shot D-cstride-fix-A
```

Farbe **in ihren Kanten**, kein vertikales Quellen. Gegenprobe wie am 07.09.:
`xrandr --output HDMI-2 --gamma 1:0.25:0.25` am Zuspieler.

### B — der Fehlerfall aus dem Skriptzustand (der zweimal reproduzierte)

```bash
plane_off
ssh $B 'python3 /root/afbd_source0.py off'
regs                       # ERWARTET: 0x05600044=0x780  0x05600098=0x0   (das Skript nullt beides)
plane_on; sleep 6
regs                       # SOLL: 0x05600044=0xF00  0x05600098=0x4D95F000
```

**Das ist der Kern der Abnahme.** Vorher blieb hier `0x780`.

### C — die Messung, die „Firmware überschreibt" von „Schreibvorgang verworfen" trennt

```bash
plane_off
ssh $B 'python3 /root/afbd_source0.py off'
ssh $B 'busybox devmem 0x05600044 32 0x00000044'      # Marke, im FEHLER-Vorzustand
ssh $B 'busybox devmem 0x05600044'                    # ERWARTET: 0x44
plane_on; sleep 6
ssh $B 'busybox devmem 0x05600044'
```

* `0xF00` → die Klammer hat gegriffen, **Ursache bestätigt**, nichts weiter zu tun.
* `0x780` → die Firmware hat geschrieben (die Marke ist weg, `0x780` kam von außen): Ursache bestätigt, aber
  die Klammer hat zu früh oder zu spät gewartet — dann `dmesg` ansehen; steht dort die Warnung, muss die
  Frist hoch, steht sie nicht da, kommt die WCE **nach** dem Enable und der Fix muss ans Vsync statt in den
  Commit.
* `0x44` → **niemand** hat geschrieben; dann ist die Ursache nicht die WCE, sondern ein verworfener
  Schreibvorgang, und dieser Fix ist falsch. Genau dieser Ausgang ist mit den bisherigen Messungen noch
  nicht ausgeschlossen.

### D — Rückstellung beim Abschalten

```bash
plane_off; sleep 2
ssh $B 'busybox devmem 0x05600044'   # SOLL: 0x780   (der beim Probe gelesene Ruhewert)
ssh $B 'busybox devmem 0x05600098'   # SOLL: 0x4D95F000  -- der Zeiger BLEIBT, absichtlich
```

### E — Wiederholbarkeit (dass der Fix nichts kaputt macht)

```bash
for i in 1 2 3; do plane_on; sleep 5; regs; plane_off; sleep 2; \
  ssh $B 'busybox devmem 0x05600044'; done
```

Jeder Zyklus: an → `0xF00`, aus → `0x780`. Und `dmesg | grep -c "refusing to rewrite"` muss **0** sein —
der Descriptor wird nur einmal pro Boot geschrieben.

**Nicht anfassen:** INCAP `0x0694xxxx` nur lesen; `viddec_descriptor.py set` nicht mehr von Hand — beides
würde die Abnahme entwerten.

---

## 5. Prüfbau

* Baum erzeugt wie `build/build.sh` Z. 143–155: frischer Tarball aus
  `mainline/build/cache/linux-6.18.38.tar.xz`, alle 71 Zeilen der `series` mit `patch -p1`. Der so erzeugte
  Treiber ist **byteidentisch** mit dem im aktuell gebauten Baum — der Vergleichspunkt stimmt.
* `0093` neu erzeugt als `diff -ruN` gegen den Baum ohne `0093`; die unveränderte Fassung ließ sich auf
  diesem Weg **zeichengleich** reproduzieren, bevor etwas geändert wurde. Die volle `series` mit dem neuen
  `0093` läuft ohne Fuzz durch, und der Unterschied im Treiber gegenüber dem aktuell gebauten Baum sind
  ausschließlich die Änderungen aus Abschnitt 2. (`sun50i-h713-arisc.c` weicht ebenfalls ab — das ist
  `0091`, an dem parallel gearbeitet wird, und nicht Teil dieser Änderung.)
* Übersetzt in einer **Kopie** des gebauten Baums (Original unverändert, Kopie gelöscht):
  `make ARCH=arm64 LLVM=1 W=1 drivers/gpu/drm/tiny/sun50i-h713-afbd.o` — **fehlerfrei, keine Warnungen**.
* `checkpatch.pl --strict`: 0 Fehler; die eine Warnung und der eine `CHECK` sind **vorbestehend**
  (Zeilenlänge im Commit-Text, Klammer-Ausrichtung bei `drm_property_create_range`) und stammen nicht aus
  dieser Änderung.
* `patches/kernel/series` **nicht** angefasst, `build/build.sh` **nicht** aufgerufen, kein Board berührt.

---

## 6. Was offen bleibt

1. **Ob die WCE wirklich `+0x044` schreibt und wann.** Abschnitt 3, entschieden durch Abnahme C. Fällt sie
   auf „`0x44` bleibt stehen", ist dieser Fix zurückzunehmen und die Suche geht bei „warum wird ein
   `writel` verworfen" weiter (Kandidaten dann: `+0x060` Gate, Latch-Zustand `+0x06C`).
2. **Kein Handschlag.** Die Klammer ist eine Beobachtung, kein Protokoll: Die ARM-Seite hat kein
   „WCE fertig"-Signal. Kommt die WCE in mehreren Schüben, kann ein später Schub den Stride erneut
   einkassieren. Sichtbar wäre das als Fehlläufe **nach** einem grünen Abnahme-A. Der saubere Ausweg wäre
   ein echtes Fertig-Ereignis — dieselbe Lücke wie RE-Frage K2/K3.
3. **Der Erst-Enable braucht weiterhin den HPD-Zyklus danach**, weil der Descriptor die Capture abschaltet
   (Nachtplan A.5). Der Nachtplan hält die andere Reihenfolge für sauberer — Descriptor **vor** Stufe 4.
   Das hieße, ihn in den Probe zu ziehen, und widerspricht doku/86 §4.1 und Nachtplan A.4 („Der Descriptor
   gehört in den Plane-Enable"). Ich habe es **nicht** getan: es ist eine Architekturentscheidung, keine
   Fehlerbehebung, und ohne Board nicht zu belegen. Gehört auf die Liste für Marco.
