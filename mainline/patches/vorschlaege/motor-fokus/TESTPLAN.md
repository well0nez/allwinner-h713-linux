# Testplan: Endschalter und Fokusmotor am Gerät

Diesen Test führt die Hauptsitzung unter Aufsicht aus, nicht der Agent, der die Patches
geschrieben hat.

Begründung und Belege zu jedem Schritt stehen in `BEFUND.md`.

---

## 0. Wo der Motor Schaden nehmen kann

Ein Wort vorweg, weil es der Grund für die Reihenfolge unten ist.

Die Mechanik hat einen **mechanischen Anschlag**. Der Endschalter PH14 ist ein
**Bereichsschalter**: er liest über den erlaubten Fahrweg *aktiv* und wird *inaktiv*, bevor der
Anschlag erreicht ist. Er ist damit das einzige Signal, das den Motor rechtzeitig umkehren
lässt. Solange nicht bewiesen ist, dass dieses Signal ankommt, ist **jede** längere Fahrt eine
Fahrt gegen den Anschlag.

Konkret gefährlich sind:

* **Das Homing beim Probe.** Es fährt bis zu 100 msteps hoch und danach bis zu 150 msteps
  runter — bei 2 Zyklen × 8 Halbschritten sind das bis zu 5600 Halbschritte in eine Richtung.
  Deshalb wird der Treiber unten erst mit `no_limit`-Prüfung und Einzelschritten getestet und
  nicht einfach geladen und laufen gelassen.
* **`motor_ctrl_no_limit = 1`.** Schaltet die Bereichsprüfung ab. In diesem Testplan wird das
  nie eingeschaltet. Wer es zum Freifahren braucht, macht das mit **einzelnen** msteps und
  Sichtkontrolle.
* **Ein Motor, der brummt statt zu drehen.** Wenn die Phasenreihenfolge nicht zur Verdrahtung
  passt, steht er und zieht Strom. Bei jedem Bewegungsschritt unten mit dem Ohr am Gerät prüfen:
  Drehgeräusch, nicht nur Summen. Bei Summen sofort abbrechen und `rmmod`.

**Abbruchkriterium für den ganzen Test:** unerwartetes Geräusch, spürbare Erwärmung des
Motortreibers, oder eine Fahrt, die den Anschlag hörbar erreicht → sofort
`echo 768 > .../motor_ctrl` (cmd 3, Queue leeren) und `rmmod hy310_keystone_motor`. Das
Entfernen des Moduls schaltet die Phasen ab (`motor_set_stop()` in `motor_remove`).

---

## 1. Vorbereitung

Kernel mit den Patches 0001–0005 bauen, wie in `doku/50-befehle.md`. Der Treiber ist nach 0005
ein **Modul** und wird beim Boot **nicht** automatisch geladen — das ist Absicht: das Probe
startet 500 ms später ein Homing.

Vor dem ersten Laden sicherstellen, dass nichts anderes den Motor bewegt.

**Erwartet:** Das System bootet, `lsmod` zeigt `hy310_keystone_motor` **nicht**,
`/sys/devices/platform/motor_ctr/` existiert **nicht**.

---

## 2. Schritt 1 — die Stromschiene, bevor irgendetwas fährt

Das ist die erste Prüfung, weil sie nichts bewegt und weil sie die wahrscheinlichste
elektrische Differenz zum Stock-System abdeckt (`BEFUND.md` 1.6).

```bash
cat /sys/kernel/debug/gpio | grep -E "gpio-(37|228|229|230|231|238)"
```

**Erwartet:** `gpio-37 … out hi` — PB5, die gemeinsame Freigabe für Lüfter und Panel-Backlight,
liegt high. Stock hält sie high (`re/captures/HY310-DEV/stock_gpio_debug.txt`).

Nach Prüfung des aktuellen Baums (07.09.2026) sollte das jetzt zutreffen: der
`fan_power_hog` hat seit Patch 0030 die richtige Zellenzahl und hängt korrekt unter `&pio`,
und U-Boot fährt PB5 zusätzlich in `h713_poweron_lines()` hoch. Beides ist statisch geprüft,
aber noch nie zur Laufzeit gemessen — deshalb steht der Schritt trotzdem hier.

**Wenn `gpio-37` fehlt oder `lo` ist:** hier aufhören und das zuerst reparieren. Zum Zeitpunkt
des einzigen bisherigen Motorlaufs (2026-03-21) war diese Schiene aus. Ohne sie ist ein Test des
Endschalters wertlos, weil dann offen bleibt, ob der Sensor überhaupt Spannung hatte.

Zusätzlich, ebenfalls ohne Bewegung — läuft der Lüfter? Dreht das Gebläse hörbar, ist die
Schiene mit Sicherheit an.

---

## 3. Schritt 2 — Treiber laden, Pin-Zustand prüfen, noch nichts fahren

Damit das Homing nicht sofort losläuft, den Motor zunächst mit gezogener Mechanik-Verantwortung
laden und **innerhalb der ersten 500 ms** nichts erwarten: das Homing ist eine `delayed_work`
mit 500 ms Vorlauf. In der Praxis heißt das: laden, sofort danach die Ausgaben lesen.

```bash
modprobe hy310_keystone_motor
dmesg | tail -20
```

**Erwartet (Probe-Ausgabe):**

```
hy310-keystone-motor motor_ctr: limiter-up-gpio: gpio 238, input, bias pull-down, active high
hy310-keystone-motor motor_ctr: limiter_num = 1
hy310-keystone-motor motor_ctr: phases=4 steps=8 cycle=2 type=0 phase_udelay=1 step_mdelay=1 active_level=1
hy310-keystone-motor motor_ctr: probed: 4 phases, 1 limiters, 800 steps
```

**Wenn stattdessen `gpio 238 cannot be made an input` kommt:** das Probe schlägt jetzt
absichtlich fehl statt weiterzumachen. Dann ist der Pinctrl-Pfad das Problem, nicht der Schalter.
Nicht weitermachen.

Jetzt der eigentliche Messpunkt, sofort:

```bash
cat /sys/kernel/debug/gpio | grep 238
cat /sys/kernel/debug/pinctrl/2000000.pinctrl/pinconf-pins | grep "pin 238"
cat /sys/kernel/debug/pinctrl/2000000.pinctrl/pinmux-pins | grep "pin 238"
```

**Erwartet:**

```
 gpio-238 (                    |limiter-up-gpio     ) in  hi
pin 238 (PH14): input bias pull down, output drive strength (20 mA)
pin 238 (PH14): GPIO 2000000.pinctrl:238
```

Drei Dinge zählen hier, und sie sind der Kern des ganzen Auftrags:

* **`in`** und nicht `out` — die Leitung wird nicht mehr getrieben. Vor dem Fix stand hier
  potenziell `out lo`.
* **`input bias pull down`** — derselbe Pad-Zustand wie im Stock-Mitschnitt
  (`re/captures/HY310-DEV/stock_pinconf_pio.txt`).
* **`hi`** — **das ist der Beweis, den wir suchen.** Stock liest den Pin bei 0,475 s aktiv
  (`BEFUND.md` 1.2). Wenn er hier ebenfalls `hi` ist, ist der Schalter in Ordnung und der Fehler
  war ausschließlich unserer.

**Wenn `lo`:** Mechanik von Hand ein Stück verfahren (Fokusring am Objektiv) und erneut lesen.
Ändert sich der Wert nie, ist die Frage aus `BEFUND.md` 1.6 offen — dann ist der nächste Schritt
eine Messung mit dem Multimeter an PH14 gegen Masse, **ohne** geladenen Treiber, und **nicht**
ein weiterer Fahrversuch.

---

## 4. Schritt 3 — das Homing beobachten (die erste Bewegung überhaupt)

Das Homing ist zu diesem Zeitpunkt schon gelaufen (500 ms nach dem Probe). Ausgabe lesen:

```bash
dmesg | grep -E "homing|limiter"
```

**Erwartet, wenn der Schalter aktiv liest (Normalfall):**

```
hy310-keystone-motor motor_ctr: homing: starting
hy310-keystone-motor motor_ctr: limiter in range — nothing to do
hy310-keystone-motor motor_ctr: homing: complete
```

Und der Motor hat sich **nicht bewegt**. Genau so verhält sich Stock im Bootlog.

**Erwartet, wenn der Schalter beim Start inaktiv liest:** eine kurze Fahrt und

```
hy310-keystone-motor motor_ctr: limiter out of range — walking back
hy310-keystone-motor motor_ctr: back in range after N UP msteps
```

mit **kleinem N**. Ein kleines N ist das eigentliche Erfolgssignal: der Schalter hat die Fahrt
beendet, nicht die Schrittzahl-Obergrenze.

**Fehlschlag:**

```
hy310-keystone-motor motor_ctr: limiter never read active (100 UP + 150 DN msteps) — motor left uncalibrated
```

Dann hat der Motor 250 msteps blind gefahren. Das ist der Fall, den es zu vermeiden gilt.
`rmmod` und zurück zu Schritt 2. **Nicht** wiederholt laden, um „zu sehen ob es beim zweiten Mal
klappt" — jeder Versuch ist eine weitere Anschlagfahrt.

---

## 5. Schritt 4 — ein einzelner manueller Schritt

Erst wenn Schritt 3 erfolgreich war.

```bash
M=/sys/devices/platform/motor_ctr/motor_ctrl
cat $M                       # Ausgangswert merken: "pos inc in_range"
echo $(( (8 << 8) | 1 )) > $M    # genau 1 mstep hoch, manuelle Zeitgebung
sleep 1
cat $M
cat /sys/devices/platform/motor_ctr/motor_limit
```

**Erwartet:** Der Motor macht ein kurzes, hörbares Drehgeräusch. Die erste Zahl in `motor_ctrl`
ist um 1 gestiegen. Die dritte Zahl (`in_range`) ist 1.

**Zu prüfen ist hier vor allem, ob überhaupt eine Bewegung stattfindet** — der Altbefund
„sysfs-Kommandos bewegen den Motor nach dem Boot nicht" sollte durch den wiederhergestellten
Arbeits-Nachlauf (`BEFUND.md`, Tabelle in 3) behoben sein.

Dann derselbe Schritt zurück:

```bash
echo $(( (9 << 8) | 1 )) > $M
sleep 1
cat $M                       # erste Zahl wieder auf dem Ausgangswert
```

---

## 6. Schritt 5 — Fokus scharfstellen (der eigentliche Nutzen)

Erst wenn Schritt 4 in beide Richtungen sauber war. Bild auf die Wand, dann in **kleinen**
Portionen:

```bash
M=/sys/devices/platform/motor_ctr/motor_ctrl
echo $(( (8 << 8) | 5 )) > $M     # 5 msteps hoch
sleep 2; cat $M
```

wiederholen, bis das Bild schärfer bzw. wieder unschärfer wird, dann mit cmd 9 zurück. Nach
jeder Portion `cat $M` und auf die dritte Zahl schauen.

**Erwartet:** Die Schärfe ändert sich sichtbar. Das ist die Bestätigung, dass `motor_ctr`
tatsächlich der Fokusantrieb ist (`BEFUND.md` 2.1) und nicht irgendetwas anderes.

**Sobald `in_range` auf 0 springt oder die erste Zahl stehenbleibt:** der Treiber hat die
Bereichsgrenze erkannt und den Edge gesetzt. Das ist **richtiges** Verhalten, kein Fehler. Dann
in die Gegenrichtung weiterfahren. Zum erneuten Freigeben:

```bash
echo 1 > /sys/devices/platform/motor_ctr/motor_limit    # löscht beide Edge-Flags
```

Das ist eine Bench-Hilfe und keine Stock-Funktion — vor jedem Freigeben prüfen, dass man nicht
gerade wieder in denselben Anschlag fährt.

---

## 7. Schritt 6 — die Gegenprobe zur Bedeutung des Schalters

Diese Prüfung belegt, dass der Schalter tatsächlich ein Bereichsschalter ist und dass der
Rückzug an „inaktiv" hängt. Sie fährt bewusst an die Bereichsgrenze und ist deshalb der
**letzte** Schritt.

```bash
watch -n0.2 'cat /sys/devices/platform/motor_ctr/motor_limit'
```

In einem zweiten Terminal in Einzelschritten (`(8 << 8) | 1`) in die Richtung fahren, in der die
Schärfe am Anschlag ist, und die erste Zahl in `motor_limit` beobachten.

**Erwartet:** Die Zahl bleibt eine ganze Weile 1 und kippt kurz vor dem mechanischen Ende auf 0.
Im selben Moment fährt der Treiber von sich aus ein Stück zurück und `dmesg` zeigt **keine**
`limiter did not return in range within 40 msteps`-Warnung.

**Wenn stattdessen diese Warnung kommt:** der Rückzug hat den Bereich nicht wiedergefunden.
Sofort aufhören, `rmmod`, und den Fall in `BEFUND.md` nachtragen — dann stimmt entweder
`back_step` nicht oder der Schalter hat eine andere Kennlinie als angenommen.

---

## 8. Aufräumen

```bash
echo 768 > /sys/devices/platform/motor_ctr/motor_ctrl   # cmd 3: Queue leeren
rmmod hy310_keystone_motor
dmesg | tail -3                                          # "removed"
```

`motor_remove()` schaltet die Phasen ab. Der Motor bleibt danach stromlos stehen.

---

## 9. Was der Test entscheidet

| Ergebnis | Bedeutung |
|---|---|
| Schritt 2 zeigt `in hi` | Der Schalter ist intakt; der Fehler war vollständig unserer. `re/notes/motor.md` und `re/notes/known-issues.md:134` gehören korrigiert. |
| Schritt 2 zeigt `in lo`, aber PB5 war in Schritt 1 `lo` | Erst die Schiene reparieren, dann alles ab Schritt 1 wiederholen. Der Motortest davor war ungültig. |
| Schritt 2 zeigt dauerhaft `in lo` bei korrekt gesetztem Pull-down und high PB5 | Jetzt erst ist ein Hardwareverdacht berechtigt — und dann als Multimetermessung an PH14, nicht als weiterer Fahrversuch. |
| Schritt 3 endet mit `never read active` | Wie oben, plus: der Motor hat 250 msteps blind gefahren. Nicht wiederholen. |
| Schritt 4 bewegt nichts, obwohl Schritt 3 sauber war | Der Weckruf-Fehler ist doch nicht die Ursache des Altbefunds. In `BEFUND.md` 6.6 nachtragen. |
| Schritt 6 zeigt den Umschlag 1 → 0 kurz vor dem Anschlag | Die Bereichsschalter-Deutung aus `motor_run_up_control` @ `0xc05d6ea0` ist am Gerät bestätigt. |
