# `h713-focus` - den Fokusmotor bedienen, ohne ihn in den Anschlag zu fahren

`h713-focus` bedient den Fokusmotor des HY310 über die sysfs-Schnittstelle des Kernelmoduls
`hy310-focus-motor`. Es zeigt Position und Zustand, fährt relativ und auf einen Zählerstand, sucht die
Ränder des Fahrbereichs und bricht sicher ab.

**Stand 12.09.2026: am Gerät noch nicht gelaufen.** Gebaut wurde es an dem Tag, an dem der Bereichswächter
zum ersten Mal ansprach ([`analyse/boot/motor-bereichswaechter-20260912.txt`](../../../analyse/boot/motor-bereichswaechter-20260912.txt));
geprüft ist es bisher nur gegen eine Attrappe (Abschnitt „Tests"). Die Abnahme steht in
[`TESTANLEITUNG.md`](TESTANLEITUNG.md) und ist noch offen.

> **Das Ding bewegt echte Mechanik.** Bevor du irgendetwas fährst, lies Abschnitt 3.

Es braucht nur die Python-Standardbibliothek (entwickelt gegen 3.12, wie `h713-pq`), kein Paket, keine
Installation, keine neue Abhängigkeit im Rootfs.

**Zum Namen.** `h713-focus` folgt [`doku/60-offen.md`](../../../doku/60-offen.md) Abschnitt „Werkzeugnamen" und
[`doku/113`](../../../doku/113-plan-pq-laufzeit-und-speichern.md) Paket B: Werkzeuge heißen `h713-*`,
gerätespezifische Dinge behalten `hy310`. Der Treiber heißt deshalb weiterhin `hy310-focus-motor`, das Modul
`hy310_focus_motor`, der Gerätebaum-Knoten `motor-ctr` - **nichts davon wird umbenannt**, und `h713-focus`
tippt auch keinen dieser Namen als Pfad ein (Abschnitt 5).

---

## 1. Der Befund, auf dem das aufbaut

**PH14 ist ein Bereichswächter, kein Endschalter.** Er liest `active_level` (= HIGH), *solange* die Mechanik
im erlaubten Fahrbereich steht. Der Rand wird am **Wegfall** des Pegels erkannt - nicht daran, dass etwas
anspricht. Ein Pin, beide Richtungen.

Am Gerät gemessen (12.09.2026, abwärts, 2 msteps je Durchgang):

```
raw=1 ... step=-204
raw=0 ... step=-206      <== Bereichsrand
raw=1 ... edge_dn=1 step=-207    (Treiber kehrt um, merkt die Kante, hält)
```

Die Umkehr, das Zurückfahren um `back_step` und das Merken der Kante macht **der Treiber selbst**
(`motor_run_dn_control()`, Vorbild `motor_run_up_control @ c05d6ea0` im Herstellercode).
`h713-focus` baut das **nicht** nach. Es erkennt, dass es passiert ist, und hört dann auf.

Die vollständige Belegkette steht in
[`mainline/patches/vorschlaege/motor-limiter/README.md`](../../../mainline/patches/vorschlaege/motor-limiter/README.md).

---

## 2. Aufrufe

```bash
h713-focus status                     # Position und Zustand, menschenlesbar
h713-focus status --json              # derselbe Zustand als ein JSON-Objekt
h713-focus down 20                    # 20 msteps abwärts, in Häppchen zu 2
h713-focus up 6 --schritt 1           # 6 msteps aufwärts, einzeln
h713-focus down 20 --trocken          # nur zeigen, was geschrieben würde
h713-focus goto -150                  # auf den Zählerstand -150 fahren
h713-focus range                      # den UNTEREN Rand suchen und vermessen
h713-focus range --auch-oben --ja     # beide Ränder (Vorsicht, siehe unten)
h713-focus stop                       # Warteschlange leeren, Bewegung beenden
h713-focus flush                      # Zweitname für stop, wie im Vorläufer
```

Gemeinsame Schalter:

| Schalter | Was |
|---|---|
| `--sysfs PFAD` | Verzeichnis des Motorknotens vorgeben. Ohne Angabe wird **gesucht**, siehe Abschnitt 5. Auch der Weg, auf dem die Tests gegen eine Attrappe laufen. |
| `--trocken` | lesen ja, schreiben nein. Am Ende steht, was geschrieben worden wäre - `echo WORT > .../motor_ctrl`. Bewegt nichts. |
| `--schritt N` | msteps je Schreibvorgang, 1…18 (Vorgabe 2). Der Treiber kürzt alles über 18 **still** (`MOVE_CLAMP_MAX`), deshalb prüft das Werkzeug selbst. |
| `--max N` | harte Obergrenze für diesen einen Lauf. Höchstens 400, siehe Abschnitt 3. |

Rückgabewerte: `0` = getan, was verlangt war (ein gefundener Rand zählt bei `range` als Erfolg), `1` = Lauf
vorzeitig beendet (gesperrt, abgebrochen, Frist abgelaufen, Rand nicht gefunden), `2` = Bedienfehler oder
Gerät/Modul nicht gefunden.

### `status`

Zeigt den Zustand ausgelegt, **und** die rohe Zeile darunter - nicht als Ersatz für die Auslegung, sondern
als Beleg dafür:

```
Bereichswaechter -- PH14, ein Pin fuer beide Richtungen
  Rohpegel        1   (act=1 bedeutet 'im Bereich')
  Auslegung       im Fahrbereich
  Limiter         num=1  (angefordert)
  Kante aufwaerts frei
  Kante abwaerts  GEMERKT -- abwaerts gesperrt
  Pruefung        motor_ctrl_no_limit = 0  (Bereichspruefung aktiv)
...
Fahren
  aufwaerts       erlaubt
  abwaerts        GESPERRT
                  edge_dn=1 -- der Rand in Richtung 'ab' ist gemerkt. ...

motor_limit (roh)  1 up=1 dn=1 num=1 raw=1 act=1 edge_up=0 edge_dn=1 step=-207
```

### `range` - den Fahrweg vermessen

Fährt **zuerst abwärts**, immer. Abwärts ist die Richtung weg vom mechanischen Anschlag; wo die Mechanik
steht, weiß vorher niemand. Der **obere** Rand wird per Vorgabe **nicht** angefahren - dort liegt der
Anschlag, und er ist bis heute nie angefahren worden. `--auch-oben` schaltet ihn ausdrücklich zu.

`range` fragt vor der Fahrt nach; ohne Terminal ist `--ja` nötig.

---

## 3. Was gefährlich ist - und welche Sicherung was abfängt

> Der Motor fährt echte Mechanik gegen einen Anschlag. Ein Schrittmotor am Anschlag **rattert oder brummt**
> hörbar, statt gleichmäßig zu ticken. Beim ersten anderen Geräusch: **Strg-C**.

| Gefahr | Sicherung in `h713-focus` | Wo sie steht |
|---|---|---|
| Blind fahren | Vor **jedem** Häppchen wird `motor_limit` gelesen und geprüft, nach jedem noch einmal. | `fahren.lauf()` |
| `raw=0` / Kante in Fahrtrichtung | Beides beendet den Lauf sofort. Die Kante in der **Gegen**richtung ist kein Grund anzuhalten - von einem Rand weg zu fahren ist die Erholung, und der Treiber löscht die Gegenkante dabei selbst. | `zustand.pruefe()` |
| Der Wächter schweigt | **Harte Obergrenze 400 msteps je Lauf**, nicht überschreibbar. Der einzige gemessene Weg bis an einen Rand sind 206 msteps; der Gerätebaum behauptet 800 Gesamtweg, das ist **nie geprüft**. Wird in 400 msteps kein Rand gefunden, ist das ein Befund und kein Grund weiterzufahren. | `fahren.LAUF_MAX_HART` |
| `motor_ctrl_no_limit` | Wird **nie** geschrieben - die Sperre sitzt in der Schreibfunktion selbst, nicht in der Befehlszeile, damit auch ein künftiger Codepfad sie nicht umgehen kann. Steht der Wert auf 1, **fährt das Werkzeug gar nicht**: im Treiber hängt die Umkehr wörtlich an `if (!m->no_limit && ...)`. | `geraet.VERBOTEN_SCHREIBEN`, `zustand.pruefe()` |
| Kein Wächter angefordert (`num=0`) | Fahren gesperrt. `motor_limiter_status()` liefert ohne Pin **bedingungslos 1** („im Bereich") - das erste Feld der Zeile sieht dann genauso aus wie im gesunden Fall und ist gerade dann wertlos, wenn es darauf ankäme. | `zustand.pruefe()` Regel 1 |
| Zeile nicht auslegbar | Vor Patch `0154` gab `motor_limit` nur `N up=N dn=N num=N` aus - weder Pegel noch Position. Eine solche Zeile ist **unlesbar, nicht halb lesbar**: jeder Unterbefehl bricht mit einer Meldung ab, die `0154` nennt. Geraten wird nichts. | `zustand.lies_grenze()` |
| Kein Rohpegel in der Zeile | Fahren gesperrt (`status` geht weiter). Greift bei einem Treiber, der die übrigen Felder hat, aber kein `raw=` - ohne den Pegel ist nicht zu sehen, ob der Wächter überhaupt etwas liefert. | `zustand.pruefe()` Regel 3 |
| Zu große Sprünge | Häppchen zu 2 msteps (Vorgabe), eine Zwischenmeldung je Häppchen, sofort ausgegeben. Der Mensch liest mit und kann abbrechen. | `fahren.SCHRITT_VORGABE` |
| Strg-C mitten in der Fahrt | Wird abgefangen: die Warteschlange wird geleert (`cmd 3`), der Lauf endet geordnet. **Der mstep, der gerade läuft, läuft zu Ende** - der Treiber hat keinen Weg, ihn abzubrechen. | `fahren.Abbruch`, `fahren.stopp()` |
| Modul nicht geladen | `h713-focus` **lädt es nicht selbst**, sondern sagt, wie man es sicher lädt. Ohne `homing=0` fährt schon das Laden bis zu **100 msteps aufwärts** (`motor_initial_homing`, `HOMING_UP_MAX`) - steht die Mechanik oben, drückt das Laden selbst hinein. | `geraet.LADEHINWEIS` |

Zwei weitere Dinge, die das Werkzeug **nicht** tut:

* **Es schreibt nie `motor_limit`.** Ein Schreibvorgang dorthin löscht **beide** gemerkten Kanten - auch die,
  die gerade schützt. Das Werkzeug braucht das nicht: ein einziger mstep in die Gegenrichtung löscht genau
  die eine Kante, und zwar durch den Treiber selbst (`motor_run_up_control()` setzt `m->edge_dn = 0`).
* **Es schickt nie die Befehle 1/2.** Das sind dieselben Bewegungen mit der Autofokus-Zeitgebung: sie setzen
  `m->autofocus` und lassen den Treiber je Phase **busy-waiten** (`mdelay`) statt zu schlafen. Für Handbetrieb
  ist das falsch. `h713-focus` nimmt ausschließlich **8 = aufwärts** und **9 = abwärts**.
  (`legacy/tools/focus` nimmt 1/2 - das ist einer der Gründe, warum es hier ersetzt wird.)

---

## 4. Der Zählerstand ist **keine** Position

`step=` aus `motor_limit` ist `m->step_cur`, ein Zähler - kein Maß für die Mechanik. Der Bezugspunkt ist der
Stand beim Laden des Moduls (`step=0`), nicht der Rand.

Bei einem Randereignis laufen die beiden auseinander, und das ist im Treiber so angelegt:

```
motor_run_dn_control():
    ein mstep abwärts          -> physisch -1
    Pegel weg? dann: k msteps zurück (k >= 1, höchstens 40) + back_step weitere
                               -> physisch +k+back_step
    m->step_cur--              -> im Zähler -1, EINMAL, egal wie teuer die Erholung war
```

Also: **physisch `-1 + k + back_step`, im Zähler `-1`.** Mit den Vorgabewerten (`back_step = 5`, `k = 1`)
sind das rund **6 msteps Versatz je Randereignis**, höchstens 46. Die Messung vom 12.09. zeigt genau das:
`raw=0` bei `step=-206`, Ruhelage danach `step=-207` - ein mstep weniger im Zähler, physisch aber rund sechs
msteps in die andere Richtung.

Daraus folgt:

* `goto N` fährt auf einen **Zählerstand**, nicht auf eine Position. Solange kein Rand berührt wurde, ist das
  dasselbe; danach nicht mehr.
* Der von `range` gemeldete Fahrweg ist im **Zähler** gemessen. Der physische Weg ist größer.
* `range` meldet zwei Zahlen: **„Rand bei"** (Zählerstand im Moment des Randes) und **„Ruhelage"** (nach der
  Umkehr des Treibers). Die beiden können sich um **einen mstep** unterscheiden, je nachdem ob der
  Lesevorgang den Moment des Wegfalls oder erst die Ruhelage getroffen hat. Beides ist richtig; deshalb stehen
  beide da statt einer gemittelten Zahl.

`status` druckt diesen Versatz mit aus, damit niemand die Zahl für eine Position hält.

---

## 5. Die Schnittstelle - und warum kein Pfad eingetippt wird

Der Knoten heißt bei uns `motor-ctr` und bei Stock `motor_ctr`; er kann künftig anders heißen. Verlässlich ist
nur der **Treibername**, und der steht als `DRIVER_NAME` im Modul. Gesucht wird deshalb in dieser Reihenfolge:

1. `--sysfs PFAD`
2. `$H713_FOCUS_SYSFS`
3. `/sys/bus/platform/drivers/hy310-focus-motor/*` - **was an den Treiber gebunden ist**
4. `/sys/bus/platform/devices/*motor*`
5. `/sys/devices/platform/*/motor_limit`

Jeder Fund muss `motor_ctrl` **und** `motor_limit` haben, sonst zählt er nicht. `status` schreibt dazu, auf
welchem der Wege der Pfad gefunden wurde.

Am 12.09. sind in diesem Projekt zwei Fehler genau daran gescheitert, dass eine Nummer aus einem fremden
Zusammenhang übernommen wurde (eine GPIO-Nummer aus einem anderen System, eine Interrupt-Liste nach der
falschen Bank). Diese Suchkette ist die Lehre daraus.

Die Attribute:

| Datei | `h713-focus` … | Bedeutung |
|---|---|---|
| `motor_ctrl` | **schreibt** | `(cmd << 8) \| (msteps & 0x7f) \| (full_limit ? 0x80 : 0)`. Benutzt werden nur **8**, **9** und **3** - die vollständige Tabelle steht unten. |
| `motor_limit` | **liest** | `1 up=1 dn=1 num=1 raw=1 act=1 edge_up=0 edge_dn=1 step=-207`. Erstes Feld Stock-kompatibel, der Rest seit `0154`. |
| `motor_step_num`, `motor_cycle`, `motor_ctrl_time`, `motor_step_delay`, `motor_back_step` | **liest** | Zeitparameter und `back_step`. Daraus wird die Dauer eines msteps geschätzt (`cycle × step_num × ctrl_time`, obere Kante von `usleep_range(800·n, 1000·n)`) und daraus die Wartefrist je Häppchen. Fehlt ein Attribut, wird die Vorgabe aus dem Gerätebaum benutzt **und als solche gekennzeichnet**. |
| `motor_ctrl_no_limit` | **liest, schreibt nie** | Ist es 1, fährt das Werkzeug nicht. |
| `motor_ctrl` (lesen) | - | wird nicht gebraucht; `motor_limit` enthält alles, was `motor_ctrl` zeigt, und mehr. |

### Das Protokoll von `motor_ctrl` vollständig

```
wert = (cmd << 8) | (msteps & 0x7f) | (full_limit ? 0x80 : 0)
```

Rekonstruiert aus `motor_ctrl_store @ c05d7d14` (Herstellercode) und im Kopf von
`drivers/misc/hy310-focus-motor.c` dokumentiert:

| `cmd` | Bedeutung | benutzt `h713-focus` das? |
|---|---|---|
| 1 / 2 | auf/ab, **setzt** das Autofokus-Flag → `mdelay`, also busy-wait je Phase. Der Pfad des Stock-Autofokus; `legacy/tools/focus` nimmt diesen. | **nein** - für Handbetrieb falsch |
| 3 | Warteschlange leeren | ja (`stop` / `flush`, und bei Strg-C) |
| 4 | Schrittzähler setzen | nein |
| 6 | `step_low` setzen | nein |
| 7 | auf Schritt fahren | nein - **im Treiber nicht implementiert** (`-EOPNOTSUPP`); Stock speichert `g_goto_step` nur und verbraucht es nie. `goto` hier rechnet deshalb selbst und fährt relativ. |
| **8 / 9** | auf/ab, **löscht** das Autofokus-Flag → `usleep_range`, der Treiber schläft. Der Pfad für Handbedienung, und der, mit dem der Bereichswächter am 12.09. vermessen wurde. | **ja**, ausschließlich |

Zwei Grenzen, die nicht dasselbe sind:

* **`msteps` belegt 7 Bit**, läuft also 0…127 - das ist das *Protokoll*.
* **Der Treiber kürzt auf 18** (`MOVE_CLAMP_MAX` in `motor_run_up_dn`), und zwar **still**: wer 30 schreibt,
  bekommt 18 und merkt es nicht. Deshalb weist `h713-focus` `--schritt` über 18 selbst ab, statt sich kürzen
  zu lassen.

Bit `0x80` („full_limit") ist im Treiberkopf beschrieben, aber **bei keiner Messung je gesetzt worden -
ungeprüft**. `h713-focus` setzt es nicht, und zwar aus zwei Gründen: es ist eine Drossel, die Befehle
*verwirft*, sobald die Warteschlange länger als drei ist (hier immer leer, also wirkungslos), und ungeprüfte
Protokollbits blind zu benutzen ist genau die Sorte Annahme, die diesem Bauteil schon einmal teuer gekommen
ist.

Ein Schreibvorgang auf `motor_ctrl` **reiht nur ein** und stößt einen Workqueue-Handler an; er kehrt sofort
zurück, die Mechanik läuft danach noch. Wer sofort wieder schreibt, fährt in eine Bewegung hinein, die er
nicht gesehen hat. `h713-focus` wartet deshalb nach jedem Häppchen, bis der Zähler am Ziel ist, ein Rand
auftritt oder die Frist abläuft - und nach einem gesehenen `raw=0` zusätzlich, bis der Treiber seine
Erholungsfahrt beendet hat („Ruhelage").

---

## 6. Kein Autofokus - und warum nicht

Die Kamera läuft seit dem 11.09. ([`analyse/beamer-cam/`](../../../analyse/beamer-cam/)), und Stock benutzt sie
für den Autofokus. Trotzdem ist hier keiner drin, und das ist eine Entscheidung, keine Auslassung.

Ein Autofokus über die Kamera braucht zwei Dinge, die es heute beide nicht gibt:

1. **Einen vermessenen Fahrweg.** Bekannt ist genau ein Rand (`step = -206`, 12.09.). Der obere ist nie
   angefahren worden, und ob die 800 msteps aus dem Gerätebaum dem echten Weg entsprechen, ist offen. Ein
   Autofokus, der über einen unvermessenen Bereich sucht, fährt genau die blinden Fahrten, die dieses
   Werkzeug verhindern soll.
2. **Ein Schärfemaß, das nachweislich mit der Fokuslage zusammenhängt.** Es gibt Bilder von der Kamera, aber
   keine einzige Messreihe Schärfemaß gegen Motorposition. Ohne die wäre jede Bewertungsfunktion geraten -
   und „eine Beobachtung ist keine Absicht" ist in genau diesem Bauteil schon einmal teuer geworden.
3. **Ein Testbild.** Marco, 12.09.: *„autofokus darf eig nur mit sonem testbild gefahren werden glaube ich"* -
   und das trägt. Ein Autofokus misst die Schärfe an dem, was gerade projiziert wird. Auf einer dunklen Szene,
   einer unscharfen Vorlage oder einem Schwarzbild misst er Rauschen und verstellt den Fokus ins Leere; auf
   einem Bild mit harten Kanten misst dieselbe Funktion zuverlässig.

**Für ein künftiges Werkzeug heißt das:** eine automatische Regelung darf **nicht einfach loslaufen**.
Entweder sie verlangt ausdrücklich, dass ein geeignetes Testbild anliegt, oder sie stellt es selbst her
(Konsole/Standbild über `h713-tv`) **und stellt danach den vorherigen Zustand wieder her**. Die Handbedienung
in diesem Werkzeug ist davon nicht betroffen - sie misst nichts und braucht kein Bild.
*Ungeprüft:* welches Testbild Stock dafür benutzt und woher es kommt.

**Der Weg dahin führt über `range`.** Wenn `range --auch-oben` am Gerät beide Ränder geliefert hat, ist
Voraussetzung 1 erfüllt; danach reicht `h713-focus goto` plus `analyse/beamer-cam/camgrab.py`, um die
Messreihe für Voraussetzung 2 von Hand aufzunehmen - mit einem Testbild an der Wand, siehe 3. Erst dann lohnt
ein eigenes Werkzeug, und dann gehört es **getrennt** hierher, nicht in `up`/`down`/`goto` hinein.

Wenn eine Regelung gebaut wird, ist auch `cmd 1/2` wieder eine Überlegung wert (der Stock-Autofokus nimmt
diesen Pfad) - aber **bewusst und mit Begründung**, nicht nebenbei: es ist busy-wait-Zeitgebung.

---

## 7. Aufbau

Vier Module, streng getrennt - wie bei `h713-pq`:

| Datei | Rolle |
|---|---|
| `h713_focus/geraet.py` | die **einzige** Naht zum Dateisystem: sysfs suchen, lesen, schreiben. Hier sitzt auch die Schreibsperre. Legt nichts aus. |
| `h713_focus/zustand.py` | `motor_limit` auslegen und die **Sicherheitsregeln**. Kein I/O, kein Zustand - dadurch vollständig ohne Gerät prüfbar, und die Regeln stehen an *einer* Stelle statt verstreut. |
| `h713_focus/fahren.py` | der bewachte Fahrlauf: Häppchen, prüfen, warten, abbrechen. |
| `h713_focus/ausgabe.py` | druckt. Rechnet nicht, liest nichts, fährt nichts. |
| `h713_focus/cli.py` | Befehlszeile. |

---

## 8. Tests

```bash
python3 tests/test_h713_focus.py         # 65 Tests, rund 5 s, ohne Gerät
```

Zwei Ebenen:

* **rein** - `zustand.py` (Auslegen der Zeile, jede einzelne Sicherheitsregel) und `geraet.py` (Suche,
  Schreibsperre, Wortformat) werden direkt geprüft.
* **durchgehend** - `cli.main(["--sysfs", PFAD, …])` läuft gegen ein **echtes Verzeichnis**, das
  `tests/attrappe.py` füllt: derselbe Code, derselbe Weg durch `geraet.py`, nur ohne Motor. Zusätzlich läuft
  das Startskript `./h713-focus` einmal als Unterprozess.

`tests/attrappe.py` enthält ein **Modell der Bewegungslogik des Treibers**: Umkehr am Rand, `back_step`,
Kante merken, Gegenkante löschen, `MOVE_CLAMP_MAX`, das Zeilenformat ab `0154`. Ein Hintergrundfaden fährt
einen mstep je Takt - asynchron genug, dass die Wartelogik wirklich durchlaufen wird, aber deterministisch.
Der Zwischenzustand „Pegel weg, Zähler noch alt, Kante noch offen" - genau der, in dem am 12.09. `raw=0`
abgelesen wurde - lässt sich mit `rand_pause_ms` festhalten, sonst wäre er zu kurz, um ihn verlässlich zu
treffen.

**Das Modell ist kein Beweis über den Treiber.** Es ist aus dem Quelltext abgeschrieben, nicht am Gerät
gemessen. Was die Tests belegen, ist das Verhalten von `h713-focus`: dass es bei `raw=0` anhält, dass es eine
gemerkte Kante bemerkt, dass es seine Obergrenze einhält, dass es `motor_ctrl_no_limit` nicht schreibt und
nie ein anderes Kommando als 8, 9 oder 3 schickt. Ob der Treiber sich seinerseits so verhält, steht in
`analyse/boot/motor-bereichswaechter-20260912.txt` und nirgends in `tests/`.

Ein Test überspringt sich sauber: der Ladehinweis-Test läuft nur auf einem Rechner, auf dem der Treiber
**nicht** registriert ist (also auf dem Arbeitsrechner, nicht auf dem Board).

---

## 9. Was belegt ist und was nicht

**Belegt - am Gerät gemessen (12.09.2026):**

* PH14 liest HIGH im Fahrbereich, `active_level = 1`, `limiter_num = 1`.
* Der Rand wird am Wegfall des Pegels erkannt; der Treiber kehrt um, fährt `back_step` zurück und merkt die
  Kante.
* Der untere Rand liegt bei `step = -206`, gemessen von der Position, an der die Mechanik seit dem 07.09.
  stand.

**Belegt - aus dem Quelltext** (unserem Treiber bzw. dem Herstellercode mit DWARF): das Protokoll von
`motor_ctrl` (8/9/3, `0x80`, `MOVE_CLAMP_MAX = 18`), das Format von `motor_limit`, `RECOVERY_MAX = 40`,
`HOMING_UP_MAX = 100`, `DEFAULT_BACK_STEP = 5`, dass `motor_ctrl_no_limit` die Umkehr abschaltet, dass
`motor_limiter_status()` ohne Pin bedingungslos 1 liefert, und dass Fahren in eine Richtung die Gegenkante
löscht.

**Nicht belegt - und deshalb nicht behauptet:**

* **Ob `h713-focus` am Gerät tut, was es soll.** Es ist nie dort gelaufen. Alles in Abschnitt 3 ist gegen eine
  Attrappe geprüft, nicht gegen Mechanik.
* **Der obere Rand.** Nie angefahren.
* **Die 800 msteps Gesamtweg** aus dem Gerätebaum (`MOTOR_STEP_TOTAL`). Zahl aus dem Vendor-Baum, am Gerät
  nie geprüft. Sie geht deshalb in **keine** Rechnung dieses Werkzeugs ein - sie steht nur als Vergleichswert
  in der Ausgabe von `range`, ausdrücklich als ungeprüft markiert.
* **Die Dauer eines msteps.** Gerechnet wird `cycle × step_num × ctrl_time` = 16 ms als *obere* Schätzung;
  die Messung vom 12.09. nennt rund 14,4 ms. Nach oben zu schätzen ist hier richtig - die Zahl geht nur in
  Wartefristen ein, und eine zu kurze Frist wäre ein falscher Abbruch mitten in der Bewegung.
* **Ob der Geber hochohmig / Open-Drain ist.** Hypothese, erklärt alle Messwerte, steht nicht im
  Herstellercode. Für dieses Werkzeug ohne Belang - es liest den Pegel, es erklärt ihn nicht.
* **`k` in der Erholungsfahrt.** Dass typischerweise ein einziger mstep reicht, um wieder in den Bereich zu
  kommen, ist die Auslegung der Messung vom 12.09. (`-206` → `-207`), nicht mehr. Deshalb nennt `status`
  **beides**: den typischen Versatz und die Obergrenze 46.

---

## 10. Vorlage und Vorgaben

`legacy/tools/focus` (63 Zeilen `sh`) war der Vorläufer. Übernommen sind von dort die Unterbefehle
`up`/`down`/`status` und `flush` (hier `stop`, mit `flush` als Zweitname) sowie der Gedanke, den sysfs-Knoten
zu **suchen** statt ihn zu raten - nur sucht `h713-focus` über den Treiber statt über zwei fest eingetippte
Pfade. Nicht übernommen: `cmd 1/2` (Autofokus-Zeitgebung, siehe Abschnitt 5) und die Prüfung auf 0…127, die
zwar das Protokoll richtig abbildet, aber am eigentlichen Limit (18) vorbeigeht.

Die nachgereichten Vorgaben vom 12.09. stehen in [`VORGABEN.md`](VORGABEN.md); ihre Punkte sind in
Abschnitt 5 (vollständiges Protokoll, `0x80` ungeprüft, 0…127 gegen 18) und Abschnitt 6 (Testbild) eingebaut.

---

## 11. Am Gerät

Die Abnahme mit erwarteten Ausgaben und Abbruchkriterien steht in **[`TESTANLEITUNG.md`](TESTANLEITUNG.md)**.
Kurzfassung: Modul mit `homing=0` laden, `status` lesen, `down 4 --trocken`, `down 4`, dann `range`. Nie
zuerst aufwärts.
