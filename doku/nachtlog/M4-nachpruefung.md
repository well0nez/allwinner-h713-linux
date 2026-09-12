# M4 nachgeprüft — der HPD-Zyklus gibt die Capture *nicht* frei

07.09.2026, 11:55 · Board-Sitzung · Nachprüfung zu `M4-hpd-dauer.md`

## Anlass

`DOKU-ABGLEICH.md` Abschnitt 3.2 hält fest, dass zwei der drei Spalten in `M4-hpd-dauer.md` den
Fehlerfall gar nicht zeigen können, und verlangt eine Gegenprobe, die so stark ist wie die in
`B2-quellenwechsel.md`. Die Dokumente führen seither **zwei** Freigabewege: HPD-Zyklus und
Quellenwechsel.

Beim Arbeiten an `0099` sind mir heute zwei HPD-Zyklen begegnet, die nichts bewirkt haben. Das
ist nachgemessen worden, statt es stehen zu lassen.

## Messung

Ausgangszustand: Capture läuft (`0x06940928 = 0xE0020438`).

```
Start        0x928=0xE0020438
nach weg     0x928=0x60020438  (Bit31 AUS)     <- THal_Vp_SetSource(1)
HPD-Zyklus:  Bit31 nach 20 s immer noch AUS    <- hpd 0 down, 0,4 s, hpd 0 up
Ende         0x928=0x60020438
```

20 Sekunden bei 20 Abtastungen pro Sekunde. Danach hat ein `SetSource(3)` sofort wieder
freigegeben — der Zustand war also nicht kaputt, sondern der HPD-Zyklus wirkungslos.

## Was das heißt — und was es nicht heißt

**Belegt:** aus dem Zustand „aktive Quelle ist VideoDec" gibt ein HPD-Zyklus auf Port 0 die Capture
nicht frei.

**Nicht belegt:** dass M4 falsch gemessen hat. M4s Ausgangszustand war ein anderer — dort war die
Capture durch das **Descriptor-Schreiben** abgeschaltet worden, und dabei bleibt die aktive Quelle
möglicherweise HDMI-1, während sie hier ausdrücklich auf VideoDec stand. Beides ergibt `0x928`
Bit 31 = 0, muss aber nicht derselbe Zustand sein. Diese Unterscheidung ist bisher **nicht**
gemessen worden, und ich habe sie hier nicht messen können: seit `0099` gibt der Kernel die Capture
nach dem Descriptor selbst wieder frei, der Zustand steht also gar nicht mehr lange genug.

## Folge für die Dokumente

Die Formulierung „zwei belegte Wege, die Capture wieder freizugeben" ist so nicht haltbar. Richtig
ist:

1. **Quellenwechsel weg und zurück** — belegt in `B2-quellenwechsel.md`, heute in `E2-freigabe.md`
   dreimal nachgemessen, und seit `0099` das, was der Kernel selbst tut.
2. **HPD-Zyklus** — in M4 aus einem Zustand belegt, der nicht mehr herstellbar ist; aus dem hier
   geprüften Zustand widerlegt. Als Betriebsweg **nicht** verwenden.

Operativ ist der Punkt erledigt, weil ihn niemand mehr braucht: die Freigabe macht der Kernel.
