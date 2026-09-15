# C3 - Der RPC-Verlust ist reproduziert, und die Ursachenkette ist geschlossen

07.09.2026, 14:15-14:45 · Board-Sitzung · Paket C

## Der Anlass

Die ganze Untersuchung wartete auf einen **Reproduktionsweg**. Drei Vorfälle, keine dmesg, und
`C2-rpc-verlust-messung.md` hatte im Ruhezustand 500 von 500 Rufen fehlerfrei gemessen. Die
Aufarbeitung setzte deshalb eine Hypothese an die Spitze, die eine Größenordnung nannte: *unsere
eigene Instrumentierung frisst die Frist, die wir selbst erfunden haben.*

Die vorgeschlagene Messung war, die drei Routinen im Ruhezustand zu vermessen - einmal mit und
einmal ohne Konsolenausgabe. Sie ist gefahren worden. Sie hat nicht bestätigt, was sie sollte; sie
hat etwas Besseres geliefert.

## Der erste Ruf zeigt es schon

Ein einzelner `THal_Vp_GetSource` bei eingeschalteter Konsole, Zeitmarken aus dem Kernel-Log:

```
8609.573800  TX nach Doorbell            Ruf raus
8609.579882  msgbox rx (RETURN)          Firmware hat nach  6,1 ms geantwortet
8609.640244  IPC[dispatch] type=1        unsere Zustellung, 60,4 ms später
8609.667326  Ergebnis beim Aufrufer      87,4 ms nach der Antwort
```

**Die Firmware braucht 6 ms. Unsere Zustellung der bereits vorliegenden Antwort braucht 87.**
Der Abstand zwischen zwei aufeinanderfolgenden `IPC[dispatch]`-Zeilen ist 8,4 ms - bei 115200 8N1
sind das rund 95 Byte, also genau eine Logzeile auf der seriellen Konsole.

## Die Messung

Auf dem Stand `381eef47`, eingeschwungen, `hy310-tv` läuft, Bild steht. Rufe über
`/sys/kernel/debug/cpu_comm/call`, Zeitnahme im Aufrufer, Konsole zur Laufzeit über
`/proc/sys/kernel/printk` stumm geschaltet (der kmsg-Puffer bleibt dabei unberührt).

| | n | Median | p95 | max | Fehler |
|---|---|---|---|---|---|
| **Konsole an**, ohne Pause | 40 | 94,0 ms | 160,1 ms | 202,1 ms | **0** |
| **Konsole stumm**, ohne Pause | 100 | **0,6 ms** | 509,3 ms | 527,5 ms | **32 (32 %)** |
| Konsole stumm, 10 ms Pause | 100 | 0,3 ms | 0,5 ms | 1,2 ms | 100 (100 %) |
| Konsole stumm, 120 ms Pause | 60 | 0,4 ms | 0,5 ms | 0,6 ms | 60 (100 %) |

Und im Log steht die Zeile, die im ganzen Projekt bisher fehlte:

```
cpu_comm: call comp=0x24efc7c9 session=0x278: no RETURN (wait timed out)
```

## Die Kette, und sie schließt sich

1. **Unsere Konsolenausgabe kostet ~120 ms je RPC.** Median 94-124 ms mit, 0,6 ms ohne. Über
   99 % des Umlaufs ist unsere eigene Protokollierung, nicht die Firmware. Damit war die Konsole
   eine **unbeabsichtigte Drossel**.
2. **Ohne sie laufen die Rufe dicht - und 32 % scheitern** mit `-110` nach ~500 ms, also am
   Fristablauf. Das ist die erste erzeugte, nicht bloß beobachtete Ausprägung des Fehlers.
3. **Jeder verlorene RETURN leckt einen FreeCall-Slot.** `Comm_ReleaseFreeCall()` steht im
   `if (return_entry)`-Zweig - ohne Antwort kein Slot zurück.
4. **Nach etwa 21 Verlusten ist der Pool leer.** Ab da scheitert **jeder** Ruf sofort, und der
   Treiber benennt es selbst:

```
DBG2: no free slot >100 spins (FreeCall FIFO drain - see SLOT-RELEASE-WAIT TODO)
TX FreeCall rd=0 wr=0
comp=0x24efc7c9 nargs=0 -> error -16
```

Das erklärt die letzten beiden Zeilen der Tabelle: die 100 % in den Serien mit Pause sind **keine**
Fristabläufe (Median 0,3 ms), sondern der erschöpfte Pool aus der Serie davor. Der Zustand ist für
den Rest des Boots dauerhaft; ein Kaltstart stellt ihn her.

## Das ist genau das, wovor das Legacy-Werkzeug sich geschützt hat

`hy310-hdmird` drosselte auf `CALL_GAP_MS = 500`, und `doku/77:153` nennt den Grund wörtlich:
**„Symptom des FreeCall-Pools"**. Alle Board-Skripte fuhren `--gap 500`. Die Drossel des
Legacy-Daemons und unsere Konsolenlatenz sind dasselbe Mittel gegen dasselbe Problem - nur haben
wir es nicht gewusst.

**Unsere Init-Sequenz feuert 22 RPCs ohne jede Pause.** Zwei der drei Vorfälle sitzen darin.

## Was das **nicht** zeigt

* **Nicht**, dass die drei Vorfälle vom 07.09. diese Ursache hatten. Ihre dmesg existiert nicht;
  bei eingeschalteter Konsole liegen die Rufe ~120 ms auseinander, und in 40 Rufen ist dabei
  nichts gescheitert. Die Vorfälle liegen im Hochlauf, wo die Firmware zusätzlich beschäftigt ist -
  das ist plausibel, aber nicht gemessen.
* **Nicht**, warum ein dicht folgender Ruf die Antwort verliert. Ob der MIPS sie gar nicht ablegt,
  ob sie zu spät kommt, oder ob unser Empfang sie verliert, trennt diese Messung nicht.
* **Nicht**, dass 32 % die Rate im Betrieb ist. Sie gilt für Rufe im Abstand von unter einer
  Millisekunde - ein Betriebszustand, den es heute nur in dieser Messung gibt.

## Zwei unbequeme Folgerungen

1. **Unsere Fehlersuchausgabe ist tragend.** Wer die `pr_info`-Zeilen aus `cpu_comm` entfernt -
   und für einen fertigen Treiber will man das - , nimmt dem System die Drossel weg, die es heute
   am Leben hält. Das ist keine Nebensache, das ist eine Abhängigkeit, die niemand entworfen hat.
2. **Die 500-ms-Frist ist eine Erfindung dieses Ports.** `CPU_COMM_CALL_TIMEOUT_MS 500` trägt
   keinen Kommentar, keine Herkunft, keine Messung. Stock hat auf diesem Pfad überhaupt keine
   RETURN-Frist; die arm32-Vorlage wartete mit `down_interruptible`, und Stocks einzige
   dokumentierte Frist gilt dem ACK. Ein Fristablauf ist bei uns also kein Fehler der Firmware,
   sondern eine Entscheidung von uns - mit einer Nebenwirkung, die den Kanal dauerhaft zerstört.

## Ein Messfehler im ersten Anlauf, damit er nicht weiterlebt

Der erste Durchgang zählte die Fehler falsch: `open(...).write(...)` puffert, der Fehler fällt erst
beim Schließen an und landete in `Exception ignored`. Die Zahlen oben stammen aus dem korrigierten
Durchgang mit `os.open`/`os.write`/`os.close` im `try`. Wer die Messung wiederholt, muss das so
machen - sonst meldet sie 0 Fehler, während sieben davon im Log stehen.
