# E2 — Die Freigabe der Capture gehört in den Kernel

07.09.2026, 11:00–11:45 · Board-Sitzung · Pakete D/E (`0099`)

## Das Problem, in einem Satz

Das Schreiben des VidDec-Descriptors schaltet die Capture ab — und niemand schaltete sie wieder
scharf. Deshalb fror das Bild in dem Augenblick ein, in dem die Video-Plane hochkam, und der
einzige Rückweg war ein Quellenwechsel aus dem Userspace, den nur wusste, wer das Protokoll
gelesen hatte.

## Die Messkette

Alles am Gerät, alles mit Kriterien, die scheitern konnten.

### 1. Nach dem Booten steht die Capture

```
0x06940928 = 0x600200F0   (Bit 31 aus)
0x06940824 = 0x8000000B   (der abgeschaltete Zustand, vgl. B2)
0x06940400 = 0x00000061
0x06940104 : 0x00000000 -> 0x00000000   (der Zähler steht sogar ganz)
```

### 2. Ein einzelner `SetSource(HDMI-1)` reicht nicht

Genau **einmal** hat `VIDIOC_S_INPUT` funktioniert — unmittelbar nach dem Booten. Danach nie wieder:

| Versuch | Ergebnis |
|---|---|
| `v4l2-ctl --set-input=0` direkt nach dem Booten | `0x928` → **`0xE0020438`**, Zähler läuft |
| dasselbe später, dreimal | `0x928` bleibt `0x60020438` |
| HPD-Zyklus über debugfs | `0x928` bleibt `0x60020438` |
| `SetSource(1)` dann `SetSource(3)` | `0x928` → **`0xE0020438`**, jedes Mal |

Die Erklärung passt auf alle vier Zeilen: die Firmware führt ihre Gruppe `V_INCAP` bei einem
**Wechsel** der Quelle erneut aus. Beim ersten Mal war HDMI-1 nicht die aktive Quelle (der
Descriptor hatte auf VideoDec geschaltet), also war das Setzen ein echter Wechsel. Danach war
HDMI-1 schon aktiv — ein Nullbefehl.

Damit ist auch der Kommentar im Treiber widerlegt, der bis heute an `h713_hdmirx_set_source()`
stand: „a real change away and back does not make the capture run again by itself
(doku/78 appendix A.5)". Er stammt aus der Zeit vor `B2-quellenwechsel.md`.

### 3. Die Freigabe kommt ~540 ms nach der Antwort der Firmware

Drei Zyklen, gemessen vom Rücksprung des zweiten RPC bis `0x928` Bit 31 gesetzt war:

| Zyklus | 1 | 2 | 3 |
|---|---|---|---|
| Dauer | 539 ms | 536 ms | 544 ms |

Wer unmittelbar nach der Antwort liest, liest zu früh — mein erster Versuch tat genau das und
meldete dreimal „geht nicht", während es dreimal ging.

## Die Lösung: der Descriptor meldet sich selbst

`0099` legt im Anzeigetreiber eine **zweite** Benachrichtigungskette an, getrennt von der
Flip-Kette. Begründung für die Trennung: die Flip-Kette **ist** der Vsync-Interrupt, ihre
Mitglieder werden gezählt, und ein Mitglied hält den Interrupt offen. Wer vom Descriptor hören
will, will beides nicht — er will einmal Bescheid bekommen, wann immer es passiert, ob gerade
etwas läuft oder nicht.

Ablauf:

1. `h713_afbd_video_atomic_update()` veröffentlicht den Descriptor — **nur wenn er neu ist**.
2. Danach, mit der Plane fertig programmiert, ruft der Anzeigetreiber die Kette.
3. Der Aufnahmetreiber hängt die Arbeit an einen Werker (die Kette läuft im Commit-Tail).
4. Der Werker wechselt die Quelle weg und zurück und wartet auf wandernde Flip-Zeiger.

## Zwei Fälle, zwei Antworten

Die Wartezeit steht **nicht** in beiden Wegen, und das ist der Punkt, an dem die erste Fassung
falsch war:

| | was der Treiber weiß | Antwort |
|---|---|---|
| nach dem Descriptor | die Capture lief, und **er** hat sie gestoppt | warten und melden, wenn sie nicht wiederkommt |
| am Ende der Probe | gar nichts — der HPD-Puls eine Sekunde davor hat der Quelle gerade gesagt, sie soll neu aushandeln | nur wechseln, nicht warten |

Die erste Fassung wartete in beiden Fällen und schrieb deshalb in **jeden** normalen Kaltstart:

```
Freigabe: nach 2000 ms bewegen sich die Flip-Zeiger nicht; liegt ein Signal an?
```

— obwohl nichts kaputt war; die Quelle brauchte nur länger als das Budget. Eine Warnung, die
auftaucht, wenn alles in Ordnung ist, wird nicht mehr gelesen. Der zweite Bau trennt die Fälle.

## Abnahme, Kaltstart 11:42

```
[16.857751] hdmi-rx: Init-Sequenz vollstaendig (22 Aufrufe)
[17.068094] arisc: HostHDMIMAP: 202 ms auf das Landen eines Hotplug-Pulses gewartet
[17.891432] hdmi-rx: /dev/video1, Slot-Quelle: AFBD vsync notifier (GIC 142)
```

Keine falsche Warnung. `0x928 = 0xE0020438`, `v4l2-ctl --get-input` → `HDMI-1: ok`.
**Ohne einen einzigen Handgriff.**

Dann `hy310-tv` gestartet:

```
[41.779338] hdmi-rx: Freigabe: Capture laeuft wieder nach 25 ms
```

Und das Kriterium, das scheitern konnte — die Wand muss der Quelle folgen. Zuspieler von 1,0 auf
0,25 gedimmt:

| | mean | std | p95 |
|---|---|---|---|
| vorher | 156,3 | 47,1 | 248 |
| nachher | 138,6 | 18,4 | 174 |

**48,16 %** der Bildpunkte über 25 Graustufen Unterschied. Die Wand lebt.

## Was diese Messung nicht sagt

Die 25 ms trennen nicht sauber zwischen „läuft wieder" und „war noch nicht leergelaufen". Das
Kriterium beantwortet die Frage, die zählt — kommen Bilder an —, und es ist die einzige, die der
Aufnahmetreiber stellen kann, ohne einen Block abzubilden, der ihm nicht gehört. Im Kommentar
steht das so.

## Nebenbefund für Paket F

`hy310-tv` braucht jetzt **nichts** mehr zu wissen. Der Umweg über einen Quellenwechsel aus dem
Userspace ist ersatzlos weg — die Reihenfolge „Plane an, dann Freigabe" macht der Kernel.
