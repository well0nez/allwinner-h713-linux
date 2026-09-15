# Vorgaben für `h713-focus` - vor dem Bauen lesen

Nachgereicht am 12.09.2026, nachdem der Auftrag schon lief. **Zwei Dinge, die im
ursprünglichen Auftrag fehlten oder verkürzt waren.**

## 1. Es gibt ein Vorbild: `legacy/tools/focus`

Ein `sh`-Skript, 63 Zeilen, aus dem alten Repo. Marco: *„es hieß focus … war ein
sh script, aber ist ja wurst, da austauschbar."* Also kein Zwang, es
fortzuschreiben - aber **ansehen lohnt**, besonders:

- Es sucht den sysfs-Knoten, statt ihn zu raten: erst `/sys/devices/platform/motor-ctr`,
  dann `/sys/devices/platform/motor_ctr` (Stock nennt ihn mit Unterstrich).
- Unterbefehle: `up <steps>`, `down <steps>`, `flush`, `status`.
- Es begrenzt `steps` auf 0…127 - das ist keine Willkür, sondern das Protokoll:
  die Schrittzahl belegt nur die unteren 7 Bit (`steps & 0x7f`).

## 2. Das sysfs-Protokoll ist größer als im Auftrag genannt

Im Auftrag standen nur `8/9`. Vollständig (aus dem Kopf von
`drivers/misc/hy310-focus-motor.c`, rekonstruiert aus `motor_ctrl_store` @ `c05d7d14`):

    value = (cmd << 8) | (steps & 0x7f) | (full_limit ? 0x80 : 0)

| cmd | Bedeutung |
|---|---|
| **1 / 2** | auf/ab, **setzt** das Autofokus-Flag → busy-wait-Timing. Das ist der Pfad, den der Stock-Autofokus nimmt. Das alte `focus`-Skript benutzt diesen. |
| 3 | Warteschlange leeren (`flush`) |
| 4 | aktuellen Schrittzähler setzen |
| 6 | `step_low` setzen |
| 7 | auf Schritt fahren - **im Treiber nicht implementiert** |
| **8 / 9** | auf/ab, **löscht** das Autofokus-Flag → schlafendes Timing. Der Pfad für Handbedienung. Damit wurde der Bereichswächter am 12.09. vermessen. |

**Für die Handbedienung 8/9 nehmen.** 1/2 nur, wenn wirklich eine automatische
Regelung gebaut wird - und dann bewusst, mit Begründung in der README.
Das Bit `0x80` (`full_limit`) ist im Treiberkopf beschrieben, aber bei unserem
Test nie gesetzt worden: **ungeprüft**, nicht blind verwenden.

## 3. Unverändert gilt

Sicherheit ist die Hauptanforderung: nie blind fahren, vor und nach jeder
Bewegung `motor_limit` lesen, harte Obergrenze je Lauf, `motor_ctrl_no_limit`
niemals schreiben, und bei nicht geladenem Modul **nicht** selbst laden, sondern
den sicheren Weg nennen (`homing=0`).

Messbeleg und Verhalten des Wächters: `analyse/boot/motor-bereichswaechter-20260912.txt`.

## 4. Nachtrag (Marco, 12.09.): Autofokus nur mit Testbild

> „autofokus darf eig nur mit sonem testbild gefahren werden glaube ich"

Nicht dringend, aber **einplanen, bevor eine automatische Regelung gebaut wird**:
Ein Autofokus misst die Schärfe an dem, was gerade projiziert wird. Auf einem
beliebigen Bild (dunkle Szene, unscharfe Vorlage, Schwarzbild) misst er Unsinn
und verstellt den Fokus ins Leere - auf einem Testbild mit harten Kanten
funktioniert dieselbe Messung zuverlaessig.

Fuer das Werkzeug heisst das: eine automatische Regelung darf **nicht** einfach
loslaufen. Entweder sie verlangt ausdruecklich, dass ein geeignetes Testbild
anliegt, oder sie stellt es selbst her (Konsole/Standbild ueber `h713-tv`) und
danach den vorherigen Zustand wieder. Die Handbedienung ist davon nicht
betroffen.

Ungeprueft: welches Testbild Stock dafuer benutzt und woher es kommt.
