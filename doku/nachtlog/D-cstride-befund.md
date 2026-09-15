# D - der C-Stride greift nicht aus jedem Vorzustand (Board-Agent, 07.09. 06:50-07:05)

## Was reproduzierbar ist

Die KMS-Plane (`0093`, Plane 38, NV16) schreibt `0x05600044` beim Enable - **aber nicht aus jedem
Vorzustand**. Sechs Läufe, dieselbe Frage, drei Ausgänge:

| Vorzustand von `0x05600044` | wie er entstand | nach dem Plane-Enable |
|---|---|---|
| `0x0780` | Kaltstart, Firmware-Vorgabe | **bleibt `0x0780`** ❌ |
| `0x0780` | `afbd_source0.py off` | **bleibt `0x0780`** ❌ (zweimal) |
| `0x0780` | **von Hand** per `/dev/mem` gesetzt | wird **`0x0F00`** ✓ |
| `0x00000044` | von Hand (Marke) | wird **`0x0F00`** ✓ |
| `0x0F00` | voriger Plane-Zyklus | bleibt `0x0F00` ✓ (vier Zyklen in Folge) |

**Der Wert `0x0780` ist also nicht das Problem** - von Hand gesetzt greift der Schreibvorgang. Es ist der
**Zustand, den `afbd_source0.py off` hinterlässt**, und derselbe Zustand nach einem Kaltstart.

## Warum das ernst ist

Die Folge ist sichtbar: mit `0x0780` statt `0x0F00` ist der Chroma-Zeilenabstand halbiert, die Farbe wird
vertikal 2× gedehnt und quillt aus ihren Kanten (Foto `D/D-10-erstenable-cstride-falsch.jpg`, Gegenprobe
`D/D-08-farbreiz.jpg`). Das ist das Fehlerbild aus Nachtplan A.5.

**Und es entwertet einen Teil der D-Abnahme von 06:10.** Die farbrichtigen Aufnahmen von heute früh liefen
über einen Zustand, in dem `0x0F00` schon stand - gesetzt vom **Skript**, nicht vom Treiber. Auf einem
frischen Kaltstart kommt die Plane heute mit falschem Chroma-Stride hoch.

## Was `afbd_source0.py off` tut (Nachtplan A.3)

Vier Y/C/Info-Slots auf 0, Aux 0, **C-Stride zurück auf `0x780`**, **Dirty `0x0560006C` auf 0**, Gain
`0x04000000`, RGB-Kanal `0x03001901` + Latch `1`, Selektor `0x29000000`. Der Verdacht liegt auf dem
Dirty-Latch bzw. dem Video-Gate: aus diesem Zustand landen offenbar nicht alle Schreibvorgänge der Plane
im Latch, während Selektor, Geometrie, Descriptor-Zeiger und `0x10` nachweislich ankommen.

## Zwei Zwischenschlüsse, die falsch waren - beide durch Messung widerlegt

1. **„Die Firmware überschreibt den C-Stride."** Widerlegt: Sekundentakt über 22 s zeigt `0x0780`
   durchgehend, kein Wechsel (D-abnahme-board.md, Nachtrag 06:15).
2. **„Der Treiber schreibt den C-Stride gar nicht."** Widerlegt durch den Markentest: mit `0x00000044`
   als Vorzustand wird daraus `0x0F00`, und `0x40`/`0x4c` werden ebenfalls beschrieben.

Beide Male hat erst die nächste Messung den Fehler gezeigt. Die Lehre ist dieselbe wie in der Nacht:
eine Hypothese, die nur *einen* Lauf erklärt, ist keine.

## Nebenbefund: das Abschalten stellt den Stride nicht zurück

Nach `plane is off, console restored` bleibt `0x05600044` auf `0x0F00` stehen. Das Skript setzt beim
`off` auf `0x0780` zurück, die Plane nicht. Für die RGB-Konsole ist das folgenlos (sie liest den
Video-C-Stride nicht), aber es ist ein Rest, der den nächsten Lauf verfälscht - genau so ist mir die
D-Abnahme heute früh durchgerutscht.

## Reproduktion (kopierbar)

```bash
ssh root@192.168.8.141 'python3 /root/afbd_source0.py off; sleep 1; busybox devmem 0x05600044'   # 0x780
ssh root@192.168.8.141 'cd /root && setsid sh -c "nohup ./hdmi_plane_test -t 15 >/root/x.out 2>&1 &"; sleep 4; busybox devmem 0x05600044'
#   FEHLER, wenn 0x780 -- erwartet waere 0xF00
```
