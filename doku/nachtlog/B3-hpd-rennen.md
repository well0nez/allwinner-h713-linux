# B3 - Der Hotplug-Zähler ist ein Rennen, kein Zustand

07.09.2026, 10:35 · Board-Sitzung · Paket B (`0091`)

## Was passiert ist

Nach dem chirurgischen Rückweg (`0098`, nimmt nur die Callback-Anmeldung zurück) probte E
weiterhin nicht - aber an einer **anderen** Stelle als vorher:

```
[   16.663604] sun50i-h713-hdmirx hdmi-rx: Init-Sequenz vollstaendig (22 Aufrufe)
[   16.672861] sun50i-h713-arisc 100000.arisc: HostHDMIMAP: Hotplug-Zaehler Port 0 steht auf 5
               -- ein Puls ist noch unterwegs, die Karte wird nicht angefasst
[   16.686778] sun50i-h713-hdmirx hdmi-rx: error -EBUSY: EDID/HPD-Sequenz fehlgeschlagen
```

Die Init-Sequenz war **vollständig** - der Callback-Umbau ist also sauber zurückgenommen.
Gescheitert ist die Stufe danach, und zwar in `0091`, nicht in `0094`.

## Der Beweis, dass es ein Rennen ist

Der vollständige Quellvergleich des gebauten Baums gegen den guten Baum `e39777bf` zeigt genau
**eine** abweichende Quelldatei: `drivers/gpu/drm/tiny/sun50i-h713-afbd.c` (die Regel-1-Korrekturen).
`sun50i-h713-arisc.c` ist in beiden Bäumen byte-identisch. Der Wächter, der hier zuschlägt, stand
also im guten Lauf wortgleich drin und hat dort **nicht** ausgelöst.

Und der Zähler bleibt nicht stehen. Wenige Minuten später, ohne Zutun:

```
portmap: 16,32,48
hpd_counter: 0 0 0
last_command: portmap 0,1,2 rc=-16
```

Dreimal im Abstand von 2 s gelesen, jedes Mal `0 0 0`.

## Was der Zähler wirklich ist

Ein **Countdown**, den die Firmware herunterzählt; sie treibt den Pin, wenn er 1 erreicht.
Die Frist dafür steht seit der Nacht im selben Treiber, eine Funktion tiefer:

```c
#define HPD_RESET_COUNTER	84	/* ticks the RESET case loads */
#define HPD_SETTLE_TIMEOUT_MS	2000	/* 84 ticks at ~10 ms plus reserve */
```

~10 ms pro Tick. Ein Stand von **5** heißt also: in etwa **50 ms** ist der Puls gelandet.

## Der Fehler

Der Wächter verwechselt zwei verschiedene Dinge:

| Beobachtung | Bedeutung | richtige Antwort |
|---|---|---|
| Zähler läuft noch | ein Puls ist unterwegs - vorübergehend, ~50 ms | warten |
| Zähler läuft nach 2 s noch | die Firmware hängt | `-EBUSY` |

Er hat beides mit `-EBUSY` beantwortet. Sein eigener Kommentar sagt es besser als sein Code:
„…die Karte in Ruhe zu lassen, **bis er gelandet ist**". *Bis* heißt warten, nicht aufgeben.

Beim Kaltstart ist regelmäßig einer unterwegs, weil die Firmware die angeschlossene Quelle
gerade erst gesehen hat - deshalb traf es ausgerechnet die Probe.

## Die Korrektur

`arisc_wait_hpd_idle()` in `0091`: wartet auf alle drei Ports, mit der bereits **gemessenen**
Frist `HPD_SETTLE_TIMEOUT_MS`, und meldet `-EBUSY` erst danach. Ein Warten wird mit Dauer
protokolliert (`dev_info`) - das ist der einzige sichtbare Beweis, dass das Rennen stattfand.

Keine neue Frist erfunden: es ist dieselbe, die für denselben Zähler schon gilt.

## Warum das die drei Fehlversuche erklärt

Es gab **zwei** unabhängige Ursachen, deshalb drei verschiedene Bruchstellen:

| Lauf | Bruch | Ursache |
|---|---|---|
| 1 | Schritt 15 `SetPortMap` `-110` | Callback-Anmeldung |
| 2 | EDID-Folge `-EBUSY` | **dieses Rennen** |
| 3 | Schritt 17 `THal_Vp_DisableBlackScreen` `-110` | Callback-Anmeldung |
| 4 (nach Rückweg) | EDID-Folge `-EBUSY`, Init vollständig | **dieses Rennen** |

Lauf 2 war schon dieses Rennen und wurde damals dem Callback zugeschrieben - falsch. Der Rückweg
hat die Callback-Ursache beseitigt; übrig blieb das Rennen, das es die ganze Zeit auch gab.

## Offen

Die Callback-Lücke selbst (`CALLBACK-luecke.md`) bleibt offen und unberührt. Diese Korrektur
macht sie weder besser noch schlechter - sie räumt nur die zweite, unabhängige Ursache weg.
