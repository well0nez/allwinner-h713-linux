# 155 - Zoom: der Aspect "zoom" legt den Bildweg lahm, der Schieber kippte das Bild (06.10.2026)

**Kurz:** TODO 2.1 ("Zoom bringt das Gerät durcheinander", Marco 04.10. und 06.10.) waren zwei Fehler. Der
Aspect-Button "zoom" der Settings-Seite setzt den Firmware-Modus 5, mit dem die Display-Firmware die Plane
nicht mehr annimmt - das Bild kommt nicht wieder, auch nicht beim nächsten Start, wenn der Wert gespeichert ist.
Der Zoom-Schieber zog jede Trapezecke um denselben Betrag nach innen und kippte damit ein schiefes Trapez. Beides
behoben (`b8d2a05`, `ce69bce`), von Marco an der Wand abgenommen. Arbeitspaket lokal: `arbeit/zoom-20261006/`.

## 1 Aspect "zoom" (kHalDisplayAspectRatio_Zoom = 5)

0133 hat die sechs Modi des Firmware-Fenstermanagers als Plane-Enum `aspect` freigegeben; gemessen waren nur 0 und 1
(`nachtlog/S15`). Gemessen am HY310, Kernel 6.18.38, Quelle ThinkPad 1920x1080p60, Warp aus:

- Klick auf "zoom" (Journal 15:51:23 UTC): `signal change in flight` -> `no signal (the flip pointers stand still)`,
  Kernel `video disable READY did not clear (00000001)`. Die Quelle sendet weiter 1920x1080@60 (`xrandr` am
  ThinkPad), die Box zeigt nichts mehr.
- Mit `aspect = zoom` in `/var/lib/h713-tv/werte` (Panel "save") ein Kaltstart ohne jeden Klick: 13,14 s Signal,
  13,25 s Plane an, `video enable READY did not clear`, 13,60 s `no signal`. Ein einziges Einschalten der Plane mit
  Modus 5 reicht, schnelles Klicken ist nicht die Ursache.
- Mit Warp an lief das Bild trotz gespeichertem `zoom` (die Video-Plane trägt dann die NV12-Puffer des Warps).

Behoben: Kernel 0185 nimmt "zoom" aus der Enum-Liste (der DRM-Kern lehnt den Wert dann selbst ab); h713-tv lehnt
`aspect zoom` auch mit älterem Kernel ab und verwirft ein gespeichertes `zoom` beim Start mit einer Warnung; die
Seite bietet nur noch `auto proportional full 16:9 4:3`. Am Gerät nach dem Neustart: `ctl aspect zoom` ->
`error aspect zoom is refused`. Die afbd-Seite ist ein Modul (`sun50i-h713-afbd.ko`): neues `.ko`, Neustart.

Nicht gemessen: was die Firmware-Funktion für Modus 5 (`sub_8B19ECD8`) genau rechnet; ob ein Neustart von h713-tv
allein aus dem Hänger herausführt.

## 2 Zoom-Schieber

`warp_effective()` zählte `(100 - zoom) * 5` Promille auf alle acht Trapezwerte. Bei einem schiefen Trapez bleibt
der Höhenversatz jeder Kante gleich, während sie kürzer wird: das Bild kippt. Mit Marcos Trapez `tl 283,0 tr 112,263
bl 224,28 br 45,0` stieg die Oberkante im Panel von 14° (100 %) auf 26° (70 %); Fotos der Box-Kamera zeigen bei 70 %
ein deutlich schräges Bild, bei 100 % ein rechteckiges.

Jetzt wird das Panelquadrat, um seine Mitte auf zoom/100 verkleinert, durch die Homographie des Trapezes gerechnet
(Heckbert, geschlossene Form) - so schrumpft das Bild um seine eigene Mitte und bleibt mit dem Trapez an der Wand ein
Rechteck, wie Stocks "Digital scaling" (`AP2i`). Ohne Trapez sind die Werte die alten. Am Gerät bei 70 %: Ecken
`tl -0.212,-0.668 tr +0.648,-0.338 bl -0.250,+0.622 br +0.728,+0.728` (NDC), wie vorausgerechnet. `test_matrix`
prüft jede gezoomte Ecke gegen die Trapezmatrix; gegen die alte `matrix.c` schlägt er mit 72 Abweichungen an.

Der Schieber schaltet unter 100 % den Warp ein, wenn er aus ist (Marco: "der Schieber kann den Warp aktivieren") -
verkleinern kann nur die GPU. Bei 100 % bleibt der Warp, wie er ist.

Die Fotoreihe 100/90/70/50 % mit der neuen Rechnung ist ungültig (Marco zog währenddessen am Schieber); abgenommen
hat Marco an der Wand: "das ist perfekt so". Die Stufen bleiben 50..100 in 5er-Schritten.

## 3 Nebenbefund

Das Journal ist im Abbild flüchtig (`/etc/systemd/journald.conf.d/10-h713.conf`: `Storage=volatile`), der erste
Absturz-Boot war deshalb verloren (`journalctl --list-boots`: ein Boot). `152` und TODO 2.22 sagen "Journal ist
persistent": `/var/log/journal` existiert zwar (seit 05.10. 19:04 UTC), aber `Storage=volatile` in der Drop-in-Datei
hat Vorrang, journald schreibt nur nach `/run`. Gehört zu TODO 1.2a.
