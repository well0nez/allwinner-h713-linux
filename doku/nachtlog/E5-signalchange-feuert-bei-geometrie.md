# E5 — Der SignalChange-Callback feuert bei reinem Geometriewechsel (M1 bestanden)

07.09.2026, 19:45 · Board-Sitzung · Punkt 2, tragende Vorbedingung

## Die Frage

Der ganze ereignisgetriebene Weg für den Auflösungswechsel steht auf einer Annahme, die `A6-4`
mit „SignalChange: 0 mal" zu widerlegen schien: **feuert die Firmware ihren Callback bei einem
reinen Geometriewechsel** (gleiche Quelle, nur andere Auflösung)? `A6-4` hat um 07:55 gemessen —
**vor** `0100`, als die Callback-Anmeldung noch gar nicht am `open()` hing. Jetzt ist sie es.

## Messung (Kernel `8db27f9f`, `hy310-tv` läuft, Callback angemeldet)

`SignalChange`-Zähler notiert, Zuspieler per `xrandr --mode 1280x720` umgestellt — **ohne**
Quellenwechsel, ohne Kabel —, dann erneut gelesen, elog mit Pegel 5 mitgeschnitten.

```
vor dem Wechsel:   SignalChange: 3 mal
nach dem Wechsel:  SignalChange: 5 mal          <-- der Callback feuert
0x06940928 = 0xE00202D0   0x06940874 = 0x050002D0   (720 Zeilen, 1280x720)
```

elog, der volle Firmware-Umbau — Stocks Kette, ohne unser Zutun:

```
FrameBuffer.cpp: HSize 1280, ... rowbyte 64
FrameBuffer.cpp 325: ... Y[0x40, 0x40, 0x2d0], C[0x40, 0x40, 0x168]   (0x2d0 = 720)
hdmirx set AV mute:0 0
app_callback.cpp 66: NotifySignalChange
```

## Ergebnis

**Bestanden, und es konnte scheitern** (Zähler unverändert oder kein `NotifySignalChange` hätte den
ganzen Ansatz gekippt). Die Firmware erkennt den Geometriewechsel, baut Capture und Ring selbst um
(`FrameBuffer.cpp` rechnet den Zeilenabstand neu) und meldet nach außen — genau die Kette aus
`doku/91` Punkt 2. `A6-4`s „0 mal" war der fehlende Callback, nicht die fehlende Meldung.

Damit ist die Vorbedingung für den Auflösungswechsel-Patch belegt. Offen bleiben M2 (folgt die
Composition der Quelle) und M3 (lässt die Firmware unsere AFBD-Source-0-Register in Ruhe) — beide
erst **mit** dem Patch messbar, weil erst dann eine 720p-Plane committet wird.
