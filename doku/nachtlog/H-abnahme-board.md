# H - Board-Abnahme Gamma/CTM (Hauptsitzung, 06:12-06:14) - **abgenommen**

Kaltstart 06:12:00, Kernel mit der integrierten Serie. Nur die Konsole nötig, kein HDMI, kein Descriptor.
Abzüge: `re/captures/weltneuheit/ours-20260907-nacht/H/`.

## Eigenschaftsprobe

```
CRTC 36: GAMMA_LUT_SIZE 1024, CTM vorhanden
```

`0095` ist im Kernel, beide Eigenschaften sind angemeldet. (Aufruf braucht `--karte /dev/dri/card1` -
`card0` ist Panfrost.)

## Invertierte LUT

| Aufnahme | mean | std | hell | dunkel |
|---|---|---|---|---|
| `H-vorher` (Konsole, schwarz) | 18,8 | 9,4 | 108 | 451 271 |
| `H-invertiert` | **197,4** | 47,3 | **420 780** | **280** |
| `H-nachher` | 18,9 | 9,5 | 146 | 451 270 |

| Vergleich | Ergebnis | Kriterium aus `H-gamma.md` |
|---|---|---|
| vorher → invertiert | mean 178,61; **100,00 %** der Bildpunkte > 25 | > 50 % |
| vorher → nachher | mean 0,99; **0,00 %** | < 10 % |

`mean` steigt um das Zehnfache, `dunkel` fällt von 451 271 auf 280 (weit mehr als halbiert), `hell` steigt
von 108 auf 420 780. Alle vier Kriterien erfüllt, drei davon deutlich übertroffen.

Auf dem Foto: die vorher schwarze Konsole mit ihrem kleinen Textblock ist ein **vollständig weißes
Rechteck**. Nach Ablauf der Haltezeit steht wieder exakt das Ausgangsbild.

**Nicht geprüft** (unverändert offen aus `H-gamma.md`): CTM gegen Stock - es gibt keinen Vendor-Fall zum
Vergleichen, weil `pq_colortemp.ini` und `White_Balance_Mode` durchgängig neutral sind. Und ob die Stufe
auch den **Video**-Pfad einfärbt: sie sitzt hinter dem Mux `0x051C006C`, gemessen ist es nicht. Beides
lässt sich jetzt aber leicht nachholen, weil D und H gleichzeitig laufen können.

---

## Nachtrag 06:20 - die Gamma-Stufe färbt auch den Video-Pfad

Das war in `H-gamma.md` als „ungetestet" benannt: „ob die Stufe auch den Video-Pfad (Source 0) einfärbt -
sie sitzt hinter dem Mux `0x051C006C`, gemessen ist es nicht."

**Erster Versuch scheiterte am Instrument, nicht an der Sache.** Mit laufender KMS-Plane meldet `gamma_test`:

```
kein DRM-Master (laeuft ein Compositor?): Permission denied
```

`hdmi_plane_test` hält den DRM-Master. Die daraufhin gemessenen **0,00 %** sind deshalb **keine Aussage** -
das Werkzeug ist gar nicht gelaufen. (Regel: erst prüfen, ob das Instrument einen Positivbefund zeigen kann.)

**Zweiter Versuch, Reihenfolge umgedreht:** Video über den Skriptpfad (`afbd_source0.py on` pokt Register
direkt und braucht keinen DRM-Master), dann `gamma_test`. Selektor blieb während der Messung durchgehend
auf `0x39000000` = Video.

| Aufnahme | mean | std | hell | dunkel |
|---|---|---|---|---|
| `HV-03` Video, normale LUT | 131,1 | 48,8 | 252 100 | 41 827 |
| `HV-04` Video, **invertierte LUT** | 88,5 | 69,4 | 103 286 | 254 773 |

**Unterschied: mean 68,33, `86,56 %` der Bildpunkte > 25.** Auf dem Foto ist es eindeutig dasselbe Bild als
Negativ: weiße Seite → schwarz, dunkle Bildkachel → weiß, rote Felder → türkis.

**Ergebnis: die Gamma-/CTM-Stufe wirkt auf beide Pfade** - Konsole (100,00 %) und Video (86,56 %).
Der Unterschied in der Prozentzahl ist Bildinhalt, kein Effekt: die Konsole ist fast einfarbig schwarz und
invertiert damit vollflächig, das Videobild hat helle wie dunkle Anteile.

**Rückkehr, mit einer Falle:** die Aufnahme unmittelbar nach `zurueckgesetzt.` (`HV-05`) wich um 96,93 % ab -
sie fiel **mitten in den Rücksetzvorgang**. Drei Sekunden später (`HV-06`, mean 132,1) ist das Ausgangsbild
wieder da; `HV-03` gegen `HV-06` siehe unten. Die Meldung `zurueckgesetzt.` kommt also, bevor die Wand es
zeigt - wer direkt danach misst, misst den Übergang. Für künftige Abnahmen: nach dem Zurücksetzen ein paar
Sekunden warten, sonst liest man einen Fehlschlag, wo keiner ist.

Für Paket **I** heißt das: Gamma und Weißabgleich sind für den HDMI-Eingang nutzbar, ohne dass dafür etwas
am Mux geändert werden muss.
