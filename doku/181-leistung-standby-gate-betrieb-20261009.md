# 181 - Leistung am HY310: Standby 2,4 W, Aus (Gate) 2,9 W, Betrieb ~24 W (TODO 2.31) (09.10.2026, 21:00)

**Kurz:** Marco hat mit einem Steckdosen-Wattmeter gemessen, ich habe die Zustände aus der Ferne hergestellt. Der Standby
über crust braucht **weniger** als "Aus": 2,4 gegen 2,9 W. Box r2test4 mit `0245` (wie `main`), `h713_gate=1`. Protokoll
`arbeit/crust-20261007/STATE.md` 20:5x-21:0x.

## 1 Aufbau

- Wattmeter an der Wand vor dem Netzteil der Box; das USB-Kabel vom PC zur Box **gezogen** (darüber speist der PC sonst
  mit, `referenz/geraete.md`). Die UART-Brücke blieb verbunden.
- Erste Runde mit der Sonoff-Steckdose zwischen Wattmeter und Box, zweite Runde ohne. Die Differenz in Standby und Gate
  ist beide Male 0,5 W: das ist der Eigenverbrauch der Sonoff.
- Keine HDMI-Quelle (das ThinkPad war nicht erreichbar; Marco: erst ohne HDMI). Die Anzeige des Wattmeters hat bei
  den kleinen Werten eine Nachkommastelle, beim Betrieb nicht.

## 2 Gemessen

| Zustand | wie hergestellt | mit Sonoff | Box allein |
|---|---|---|---|
| Betrieb ohne Signal (Konsole, Lampe und Lüfter an, 4500 U/min) | Boot | 24 W | ~24 W |
| Standby (ARM aus, DRAM im Self-Refresh, crust wacht) | h713-power-Pfad (`s3-act.py`, RTC 180 s), danach Bild in 3,8 s und Audio-DSP im 1. Versuch zurück | 2,9 W | **2,4 W** |
| Aus (Gate, U-Boot wartet auf die Taste, LED rot) | `systemctl poweroff`; zweite Runde: Netzteil neu eingesteckt (Kaltstart ins Gate) | 3,4 W | **2,9 W** |
| Sonoff selbst | Differenz | - | ~0,5 W |

Im Standby (erste Runde) hörte Marco ein leises Fiepen aus dem Netzteil, im Gate nicht - typisch für ein
Schaltnetzteil bei sehr kleiner Last. Ob es in der zweiten Runde auch fiepte, ist nicht notiert.

## 3 Einordnung

- Im Gate läuft U-Boot auf einem ARM-Kern in einer Schleife und fragt die Taste ab; im Standby sind die ARM-Kerne aus
  und nur crust auf dem ARISC wacht. Daher der Unterschied.
- Die Differenz mit/ohne Sonoff ist in Standby und Gate gleich (0,5 W), obwohl das Gate der ersten Runde nach
  `poweroff` (Warmstart) und das der zweiten nach dem Einstecken (Kaltstart) gemessen wurde: warm oder kalt macht im
  Gate keinen sichtbaren Unterschied.
- Am 09.09.2026 (`doku/103` M5, Marco, Steckdosen-Messgerät, vor crust) standen 4 W im Gate, nach Kaltstart wie nach
  `poweroff`, und **47 W im Betrieb mit HDMI-Bild 1080p**. Ob damals die Sonoff oder das USB-Kabel mitgemessen wurden,
  steht dort nicht; der Unterschied zu heute (2,9 W) ist nicht geklärt. Die 24 W heute sind Betrieb **ohne** Signal,
  mit der Konsole an der Wand - mit den 47 W mit Bild nicht vergleichbar, solange "mit Bild" nicht neu gemessen ist.
- Für TODO 2.29: Standby ist nicht nur schneller zurück (~11 s gegen ~28 s Boot), sondern auch sparsamer als Aus. Das
  stützt, Standby nach der Alltagsprobe zur Vorgabe zu machen.
- Nicht gemessen: Betrieb mit Bild von einer Quelle (heute), Standby mit angeschlossener HDMI-Quelle, die Leistung über Stunden.
