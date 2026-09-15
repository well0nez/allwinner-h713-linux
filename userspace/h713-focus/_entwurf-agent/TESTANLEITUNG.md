# `h713-focus` am Gerät abnehmen

Für Marco. Stand 12.09.2026 - **`h713-focus` ist nie am Gerät gelaufen.** Alles unten ist gegen die Attrappe
geprüft, nicht gegen Mechanik. Die erwarteten Ausgaben stammen aus einem Lauf gegen `tests/attrappe.py`, der
mit den Werten des Geräts gefüttert wurde (`step_num=8`, `cycle=2`, `ctrl_time=1`, `back_step=5`,
unterer Rand bei `-206`, wie am 12.09. gemessen).

Dauer: ohne `range` rund fünf Minuten, mit `range` je nach Weg eine bis zwei Minuten mehr.
**Ein Stromzyklus reicht** - nichts hier verlangt einen Neustart.

---

## ⚠ Vorher lesen

> * **Ein Schrittmotor am Anschlag rattert oder brummt hörbar**, statt gleichmäßig zu ticken.
>   **Beim ersten anderen Geräusch: Strg-C.** Das ist das wichtigste Abbruchkriterium und es steht in keiner
>   Ausgabe - nur du hörst es.
> * **Nie zuerst aufwärts.** Wo die Mechanik steht, weiß niemand; aufwärts liegt der Anschlag.
> * **Modul nur mit `homing=0` laden.** Ohne das fährt schon das Laden bis zu 100 msteps aufwärts.
> * **`motor_ctrl_no_limit` niemals auf 1 setzen.** `h713-focus` schreibt es nicht; von Hand auch nicht.

---

## Schritt 0 - die Notbremse, vorher merken

```sh
h713-focus stop          # leert die Warteschlange, der laufende mstep läuft zu Ende
rmmod hy310_focus_motor  # härter: stoppt die Phasen und gibt die Pins frei
```

Strg-C während eines Laufs macht dasselbe wie `stop` und beendet den Lauf geordnet.

---

## Schritt 1 - ohne Modul: sagt es das Richtige?

Noch **bevor** das Modul geladen ist:

```sh
h713-focus status
```

**Erwartet** (Rückgabewert 2, Ausgabe auf stderr):

```
h713-focus: Der Treiber hy310-focus-motor ist im Kernel nicht registriert -- das Modul hy310_focus_motor ist nicht geladen.

So wird es sicher geladen -- homing=0 ist Pflicht:

    modprobe hy310_focus_motor homing=0
    ...
```

**Abbruchkriterium:** kommt hier etwas anderes - etwa ein Python-Traceback oder ein Pfad, den es nicht gibt -
nicht weitermachen. Dann stimmt die Suchkette nicht.

---

## Schritt 2 - Modul laden und nachsehen

```sh
modprobe hy310_focus_motor homing=0
h713-focus status
```

**Es darf sich dabei nichts bewegen.** `homing=0` sorgt dafür; `status` schreibt gar nichts.

**Erwartet** (Rückgabewert 0):

```
Fokusmotor
  sysfs           /sys/devices/platform/motor-ctr
                  (gebunden an den Treiber hy310-focus-motor)

Bereichswaechter -- PH14, ein Pin fuer beide Richtungen
  Rohpegel        1   (act=1 bedeutet 'im Bereich')
  Auslegung       im Fahrbereich
  Limiter         num=1  (angefordert)
  Kante aufwaerts frei
  Kante abwaerts  frei
  Pruefung        motor_ctrl_no_limit = 0  (Bereichspruefung aktiv)

Position
  Zaehlerstand    0 msteps
  ...
Fahren
  aufwaerts       erlaubt
  abwaerts        erlaubt

Parameter (aus sysfs gelesen, soweit vorhanden)
  motor_step_num     8     Phasenschritte je Folge
  motor_cycle        2     Folgen je mstep
  motor_ctrl_time    1     ms je Phasenwechsel
  motor_step_delay   1     ms je Schritt (nur bipolar)
  motor_back_step    5     msteps zurueck nach dem Rand
  ein mstep          ~16 ms   (2 x 8 x 1 ms, obere Schaetzung)

motor_limit (roh)  1 up=1 dn=1 num=1 raw=1 act=1 edge_up=0 edge_dn=0 step=0
```

**Die drei Zeilen, auf die es ankommt:**

| Zeile | erwartet | wenn anders |
|---|---|---|
| `sysfs` | `(gebunden an den Treiber …)` | Steht dort „Notweg" oder „vorgegeben", hat die Suche über den Treiber nicht getroffen - das ist ein Befund, notieren. |
| `Rohpegel` | `1` | `0` = die Mechanik steht **außerhalb**; `-1` = der Treiber kann den Pin nicht lesen. In beiden Fällen **abbrechen** und nachsehen, nicht fahren. |
| `Limiter` | `num=1` | `num=0` heißt: kein Wächter angefordert → `h713-focus` fährt gar nicht, und das ist richtig so. Dann stimmt der Gerätebaum-Knoten nicht. |

> Steht `Kante abwaerts GEMERKT` schon direkt nach dem Laden, ist die Mechanik noch in dem Zustand vom
> 12.09. - dann hat das Modul die Kante nicht neu geladen, sondern der Knoten war noch offen. Ein `rmmod`
> und erneutes Laden setzt sie zurück.

---

## Schritt 3 - der Trockenlauf: was **würde** geschrieben?

Bewegt nichts. Prüft, dass das Wortformat stimmt, bevor es zum ersten Mal ernst wird.

```sh
h713-focus down 4 --trocken
```

**Erwartet:**

```
-- Trockenlauf: es wird nichts geschrieben. --

Ergebnis: Trockenlauf
  Trockenlauf: es wuerde 4 msteps 'ab' fahren, in Haeppchen zu 2. Der
  erste Schreibvorgang waere '2306' nach motor_ctrl (= (9 << 8) | 2).
  Geschrieben wurde nichts.

Was geschrieben worden waere:
  echo 2306 > /sys/devices/platform/motor-ctr/motor_ctrl
```

**Abbruchkriterium:** steht dort ein anderes Wort als `2306` (`9 << 8 | 2`), oder ein Kommando 1 oder 2 -
nicht weitermachen. `2306` ist abwärts mit der Handbetrieb-Zeitgebung; 1/2 wären die Autofokus-Zeitgebung
(busy-wait) und hier falsch.

Gegenprobe aufwärts: `h713-focus up 4 --trocken` muss **`2050`** nennen (`8 << 8 | 2`).

---

## Schritt 4 - die ersten vier msteps, abwärts

**Jetzt bewegt sich etwas. Hinhören.**

```sh
h713-focus down 4
```

**Erwartet** (Rückgabewert 0, Dauer rund 0,1 s plus Wartetakt):

```
   ab  2 msteps -> step=-2     raw=1 edge_up=0 edge_dn=0
   ab  2 msteps -> step=-4     raw=1 edge_up=0 edge_dn=0

Ergebnis: fertig
  4 msteps gefahren.
  gefahren        4 von 4 msteps (im Zaehler)
  Zaehler         0 -> -4
```

**Abbruchkriterien:**

* Rattern/Brummen statt gleichmäßigem Ticken → Strg-C, dann `rmmod`, nicht weitermachen.
* `raw=` springt hier schon auf `0` → die Mechanik stand näher am Rand als gedacht. Kein Schaden, aber
  Schritt 6 (`range`) liefert dann eine viel kleinere Zahl als die 206 vom 12.09. - notieren.
* `[verworfen]` oder `gefahren 0 von 4` → der Treiber hat den Befehl geschluckt. Nicht wiederholen, sondern
  `h713-focus status` ansehen.
* Ausgabe steht still und nichts bewegt sich → Strg-C. Die Frist je Häppchen ist rund **1,4 s**
  (`(2 + 40 + 5) × 16 ms × 1,5 + 300 ms` = 1428 ms; die 40 sind `RECOVERY_MAX`, die 5 `back_step` - es wird
  der schlimmste Fall veranschlagt, den der Treiber selbst vorsieht). Das Werkzeug bricht danach selbst ab
  und meldet `Frist abgelaufen`.

---

## Schritt 5 - wieder hoch, und die Gegenprobe zur Kante

```sh
h713-focus up 4
```

**Erwartet:** zwei Häppchen, `Zaehler -4 -> 0`, davor die Warnzeile

```
Aufwaerts ist die Richtung, in der der mechanische Anschlag
liegt. Beim ersten anderen Geraeusch: Strg-C.
```

Damit ist der Ausgangsstand wieder erreicht **im Zähler** - solange kein Rand berührt wurde, ist das auch die
Ausgangslage der Mechanik.

---

## Schritt 6 - `range`: den unteren Rand suchen

Der eigentliche Test. Der obere Rand wird **nicht** angefahren.

```sh
h713-focus range --max 260
```

Es fragt nach; mit `ja` antworten. (Über ssh ohne Terminal: `--ja` anhängen.)

**Erwartet** - hier mit einem Start bei `step=-198`, damit die Ausgabe kurz bleibt; am Gerät stehen davor
entsprechend mehr Häppchenzeilen:

```
Fahrwegvermessung
  Start          step=-198, raw=1, im Bereich
  Zuerst         ABWAERTS, hoechstens 260 msteps in Haeppchen zu 2
  Dauer          bis zu ~4 s je Richtung (ein mstep ~16 ms)
  Danach         nichts. Der obere Rand wird NICHT
                 angefahren (--auch-oben schaltet ihn zu).
  Abbruch        Strg-C -- leert die Warteschlange.

Abwaerts:
   ab  2 msteps -> step=-200   raw=1 edge_up=0 edge_dn=0
   ab  2 msteps -> step=-202   raw=1 edge_up=0 edge_dn=0
   ab  2 msteps -> step=-204   raw=1 edge_up=0 edge_dn=0
   ab  2 msteps -> step=-206   raw=1 edge_up=0 edge_dn=0
   ab  2 msteps -> step=-207   raw=1 edge_up=0 edge_dn=1   [rand]

Ergebnis: RAND ERREICHT
  Rand in Richtung 'ab' erreicht: der Treiber hat umgekehrt und die Kante
  gemerkt (edge_dn=1).
  gefahren        9 von 260 msteps (im Zaehler)
  Zaehler         -198 -> -207
  Rand bei        step=-207
                  Zaehlerstand nach der Umkehr; der Wegfall des Pegels lag
                  einen mstep davor

Vermessung
  unterer Rand   step=-207
                 Zaehlerstand nach der Umkehr; der Wegfall des Pegels lag
                 einen mstep davor
  Ruhelage       step=-207  (nach der Umkehr des Treibers)
  oberer Rand    nicht angefahren (--auch-oben)

  Zurueck zum Ausgangsstand:  h713-focus goto -198
```

**Die Zahl, um die es geht:** `unterer Rand step=…`. Vom Ladepunkt aus gemessen sollte sie **nahe bei −206**
liegen, wenn die Mechanik nach dem 12.09. nicht bewegt wurde. **Sie muss es nicht** - die Ausgangslage kann
eine andere sein, und dann ist jede andere Zahl genauso richtig.

Ein Häppchen kann statt `[rand]` auch `[ausserhalb]` melden; dann folgt

```
  Der Treiber faehrt zurueck; warte auf die Ruhelage ...
```

Das ist **derselbe Befund**, nur eine Zehntelsekunde früher abgelesen: der Pegel ist weg, die Kante noch
nicht gesetzt. Der gemeldete Randstand ist dann **einen mstep kleiner**. Beide Fälle sind in Ordnung.

**Abbruchkriterien:**

* Geräuschänderung → Strg-C.
* `unterer Rand NICHT gefunden innerhalb von 260 msteps` → **kein Grund, mit größerem `--max` nachzulegen.**
  Das ist ein Befund: entweder liegt der Rand weiter weg als der bisher gemessene Weg, oder der Wächter
  liefert nichts mehr. Erst `status` ansehen (`raw=`), dann entscheiden.
* `Der Treiber ist NICHT in den Bereich zurueckgekehrt` → sofort aufhören, `rmmod`. Der Treiber hat nach 40
  vergeblichen Umkehrschritten die Kante nur noch **behauptet**.

---

## Schritt 7 - optional, und nur wenn Schritt 6 sauber lief: der obere Rand

**Das ist die Fahrt in Richtung Anschlag.** Sie ist bis heute nie gemacht worden.

```sh
h713-focus range --auch-oben --max 400 --schritt 1
```

`--schritt 1` macht die Fahrt langsamer und die Zwischenmeldungen dichter - je eine Zeile pro mstep, rund
16 ms auseinander. Die Hand am Strg-C, das Ohr am Gerät.

**Erwartet:** erst der Lauf aus Schritt 6, dann

```
Aufwaerts (Richtung Anschlag -- hinhoeren!):
  auf  1 msteps -> step=-206   raw=1 edge_up=0 edge_dn=0
  ...
```

und am Ende entweder ein `[rand]` mit `edge_up=1` und dem Block

```
  Fahrweg        rund N msteps zwischen den beiden
                 Randereignissen -- im ZAEHLER gemessen.
                 ...
                 Der Geraetebaum behauptet 800 msteps
                 (MOTOR_STEP_TOTAL) -- diese Zahl ist am
                 Geraet nie geprueft worden.
```

oder `oberer Rand NICHT gefunden innerhalb von 400 msteps`.

**Beides ist ein Ergebnis.** 400 msteps ist die harte Obergrenze und lässt sich nicht hochsetzen; findet sich
der obere Rand darin nicht, ist der Fahrweg länger als 400 msteps - und das allein widerlegt die 800 aus dem
Gerätebaum schon nicht, aber es grenzt sie ein.

**Abbruchkriterium, härter als sonst:** hier ist jedes untypische Geräusch ein sofortiges Strg-C. Aufwärts
ist die Richtung, in der in der Vergangenheit gegen den Anschlag gedrückt wurde.

---

## Schritt 8 - aufräumen

```sh
rmmod hy310_focus_motor
```

**Den Fokus nicht „zur Sicherheit" zurückfahren.** Er darf stehen bleiben, wo er steht; eine Fahrt ohne
Bezugspunkt wäre genau das, was dieses Werkzeug vermeiden soll. Wer den Ausgangsstand wiederhaben will,
nimmt das `h713-focus goto …`, das `range` am Ende ausgibt - und zwar **vor** dem `rmmod`, weil der Zähler
mit dem Modul verschwindet.

---

## Was danach notiert gehört

1. Die Zeile `motor_limit (roh)` aus Schritt 2 - der Zustand direkt nach dem Laden.
2. Der gemeldete **untere Rand** aus Schritt 6, und ob es `[rand]` oder `[ausserhalb]` war.
3. Falls Schritt 7 gelaufen ist: der **obere Rand** und der Fahrweg - das ist die erste Vermessung des
   gesamten Fahrwegs überhaupt und die Voraussetzung dafür, dass ein Autofokus über die Kamera überhaupt
   sinnvoll gebaut werden kann (README Abschnitt 6).
4. Jede Stelle, an der die Ausgabe **anders** aussah als hier. Die erwarteten Ausgaben kommen aus einer
   Attrappe; wo das Gerät abweicht, hat die Attrappe unrecht, nicht das Gerät.
