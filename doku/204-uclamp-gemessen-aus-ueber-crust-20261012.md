# 204 - UCLAMP gemessen, 0257 und IR-Wecken aus dem Aus bestätigt (12.10.2026, vormittags)

**Kurz:** Nachmessungen zu `doku/203` am HY300PRO-G-EU mit dem Kernel aus `main` (FIT `5fc51625`). **(1) 2.60:** UCLAMP
(`sched_util_clamp_min_rt_default = 0`) hält den Takt bei laufendem Warp zu 86-87 % auf 480 MHz bei ~3 Wechseln/s, gegen 53 % und
35 Wechsel/s mit dem Zwangsboost; etwas ruhiger als die alte `chrt`-Lösung; unter echter Last geht er sofort auf 1296 MHz. **(2) 2.40:**
nach einem Aus über crust stehen beide Meldungen als Info im Log (`0257`). **(3) 2.65:** die IR-Fernbedienung weckt den G-EU aus dem
Aus über crust (Marco). Skripte und Rohdaten: `arbeit/standby-20261012/uclamp-reihe.sh`, `uclamp-reihe.txt`, `uclamp-reihe-video.txt`.

## 1 UCLAMP (2.60)

Warp an (`tl x 50`), Quelle ThinkPad 1080p60, je 20 s mit `messe-warp.py`, jede Variante zweimal im Wechsel; die zweite Reihe mit
bewegtem Testbild (`ffplay testsrc2` 1920x1080@60 auf dem ThinkPad, 60 Quellbilder/s, 59,8 gezeigt).

| Variante | 480 MHz | 1296 MHz | Wechsel/s | sugov | alle Kerne | Warp |
|---|---|---|---|---|---|---|
| U0: UCLAMP 0, IRQ-Threads FIFO (Vorgabe) | 86-87 % | 8-9 % | 3,0-3,4 | 0,1-0,2 % | 7,6-7,8 % | 59,7 fps, 0 verworfen |
| U1024: wirkungslos (Zwangsboost) | 53-54 % | 43-44 % | 35,0-35,6 | 2,3-2,4 % | 7,5-8,1 % | 59,7 |
| CHRT: 1024, IRQ-Threads SCHED_OTHER (alt) | 83-85 % | 11-14 % | 4,2-6,2 | 0,2-0,3 % | 8,0-8,3 % | 59,7 |
| U0 + ein Kern voll (python-Schleife) | 0 % | 100 % | 0 | 0 % | 31 % | 59,7 |

Bewegter Inhalt ändert nichts (der Warp zeichnet jedes Bild ohnehin). Die "alle Kerne" um 7,6 % gegenüber 4,4-4,6 % in `doku/201`
m30/m31 sind ein anderer Aufbau (0255, 0258, h713-osd, Bluetooth verbunden) - nicht verglichen.

## 2 Aus über crust (2.40, 2.65)

`systemctl poweroff` (h713-power status: "crust (rails off, about 0.3 W ...)"), Marco drückte Power auf der IR-Fernbedienung, frischer
Start. Im Kernel-Log danach:

```
previous run (record of TF-A): powered off through crust, back by the R_WDOG (0x00010001), cycle 0
TF-A: R_WDOG found armed after the power off through crust, as meant (word 0x03010001)
```

Beide als Info (vorher Warnungen). Nicht gemessen: IR-Wecken nach einem Kaltstart mit `h713_gate=1` (2.65, das war Marcos
eigentliche Frage) - der G-EU steht auf Gate 0.
