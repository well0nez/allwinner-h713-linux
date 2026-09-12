# D — Board-Abnahme der NV16-Video-Plane (Hauptsitzung, 05:58–06:10)

Kernel mit der integrierten Serie (71 Patches, FIT `8ffceb0b…`), Kaltstart 05:58:42.
Abzüge und Fotos: `re/captures/weltneuheit/ours-20260907-nacht/D/`.

## Zwei Abweichungen von Ds Vorschrift, beide nötig

1. **`prep_ohne_arisc.sh` statt `prep_after_boot.sh`** — mit `0091` im Kernel bindet der ARISC-Treiber
   selbst; das alte Rezept lädt den Blob ein zweites Mal.
2. **Freigabe nach dem Descriptor.** Ds Vorschrift stammt von *vor* der Erkenntnis, dass der Descriptor die
   Capture abschaltet (`0x06940928` Bit 31 → 0). Ohne den HPD-Zyklus danach steht der Ring, und die Plane
   zeigt einen Standrahmen. Die Vorschrift in `D-plane.md` §5 ist an dieser Stelle **unvollständig**.

## Ergebnis: **abgenommen**

`hdmi_plane_test` meldet:

```
device      /dev/dri/card1 (sun50i-h713-afbd)
connector   33, crtc 36, mode 1920x1080
plane       38, format NV16, mode hdmi-ring (capture)
plane is up. Holding.
```

Registerbild bei laufender Plane — **ohne `viddec_descriptor.py`, ohne `afbd_source0.py`**:

| Register | Ist | Soll |
|---|---|---|
| `0x05600010` | `0x03000013` | ✓ |
| `0x05600040` | `0x00000780` | ✓ Y-Stride 1920 |
| **`0x05600044`** | **`0x00000F00`** | ✓ **C-Stride 3840 = NV16 im NV12-Leser** |
| `0x05600048` / `0x0560004C` | `0x04380780` / `0x021C0780` | ✓ |
| `0x05600020` / `0x05600024` | `0x043F077F` / `0x00420077` | ✓ gerechnete 1920×1080-Geometrie |
| `0x05600068` | `0x00000122` | ✓ Ring-Mux |
| `0x05600098` | `0x4D95F000` | ✓ Descriptor, vom **Treiber** gesetzt |
| `0x05140508` | `0x144C0000` | ✓ |
| `0x051C006C` | `0x39000000` | ✓ Video-Selektor |
| `0x06940928` | `0xE0020438` | ✓ Capture frei (nach der Freigabe) |

**Der Unterschied zum Skript:** `0x05600070` **wandert** — beobachtet `0x4C3EF000 → 0x4C5EE000`,
`0x4C7ED000 → 0x4C3EF000`. Das Skript nagelt alle vier Slots auf `0x4C3EF000` fest; die Plane folgt der
Ring-Folge, wie es Paket D gebaut hat.

**Bild:** volle Breite, richtige Geometrie, lesbar (`D-02`, `D-07`). Farbe **in ihren Kanten** — rote Felder
als klare Rechtecke, Bildkachel mit sauberen Rändern, **kein vertikales Verschmieren** (`D-08`, starker
Farbstich per `xrandr --gamma 1:0.25:0.25`). Genau das war der Zweck des C-Strides.

**Liveness, nicht nur ein Foto:** der Farbreiz ändert **38,74 %** der Bildpunkte im ROI (mean 26,08).
Die Rückkehr liegt bei 9,84 % — nicht 0,00 %, weil die Quellseite driftet (belegt in `M4-hpd-dauer.md`:
zwei Aufnahmen ohne jeden Eingriff unterscheiden sich über die Zeit).

## Ein Befund, der noch zu klären ist

Im **ersten** Lauf las `0x05600044` **`0x00000780`** statt `0x0F00`, in den beiden folgenden `0x0F00`.
Der Unterschied zwischen den Läufen: im ersten schrieb der Treiber den Descriptor **neu** (erster Enable
nach dem Kaltstart), danach war er schon vorhanden und wurde übersprungen.

**Hypothese (nicht belegt):** der Descriptor-Schreibvorgang stößt die Firmware an, und deren Übergang
überschreibt den gerade gesetzten C-Stride. Dann müsste die Plane ihre Register **nach** dem Firmware-
Übergang erneut anlegen — oder den Descriptor schreiben, *bevor* sie die Geometrie programmiert.

**Prüfung, die das entscheidet** (ein Kaltstart, ~5 min): Kaltstart → prep → SetSource → EDID → Plane
starten und `0x05600044` **im Sekundentakt** über die ersten 20 s lesen. Springt der Wert von `0x0F00`
auf `0x0780`, ist die Hypothese belegt und der Fix gehört in `0093`.

## Nebenbefund zum Werkzeug

`hdmi_plane_test` im Hintergrund starten und die SSH-Sitzung mit einem kurzen `timeout` umgeben killt die
ganze Prozessgruppe mit — trotz `setsid nohup`. Zweimal darauf hereingefallen (die Fotos `D-04`/`D-05`
zeigen deshalb die Konsole, nicht die Plane). Was funktioniert:
`setsid sh -c "nohup ./hdmi_plane_test -t 150 > /root/plane3.out 2>&1 &"`, und die Sitzung danach **nicht**
abwürgen.

---

## Nachtrag 06:15 — die offene Frage ist beantwortet, und meine Hypothese war falsch

Kaltstart 06:12, jungfräulicher Zustand vor der Plane: `0x06940928 = 0xE0020438` (Capture frei),
`0x05600044 = 0x00000780` (Firmware-Vorgabe), `0x05600098 = 0x00000000` (kein Descriptor).
Dann die Plane starten und `0x05600044` **im Sekundentakt** über 22 s lesen:

| t | `0x05600044` | `0x05600098` | `0x06940928` | `0x05600010` |
|---|---|---|---|---|
| +1 s | `0x0780` | `0x00000000` | `0xE0020438` | `0x03000010` |
| +2 s | `0x0780` | **`0x4D95F000`** | **`0x60020438`** | **`0x03000013`** |
| +3 … +22 s | `0x0780` | `0x4D95F000` | `0x60020438` | `0x03000013` |

**Meine Hypothese war falsch.** Die Firmware überschreibt den C-Stride **nicht** — er steht die ganze Zeit
auf `0x0780` und wechselt nie. Der Treiber setzt beim **ersten** Enable nach dem Kaltstart den Descriptor
(`0x98`) und Source 0 (`0x10`), **schreibt den NV16-C-Stride aber gar nicht**. Bei jedem folgenden Enable —
wenn der Descriptor schon steht und übersprungen wird — schreibt er ihn korrekt auf `0x0F00`.

**Das ist ein echter Fehler in `0093`, kein Firmware-Verhalten.** Der C-Stride-Schreibvorgang liegt
offenbar in einem Zweig, der übersprungen wird, wenn der Descriptor frisch geschrieben wird.

**Die Folge ist sichtbar** (`D-10-erstenable-cstride-falsch.jpg`, nach der HPD-Freigabe aufgenommen,
also mit laufender Capture): die Bildkachel ist **entsättigt**, der rote Block **quillt nach rechts unten
aus seiner Kante**, das Logo ist blaugrau statt rot. Genau das Fehlerbild aus Nachtplan A.5
(„Farben vertikal 2× gedehnt, Farbe quillt unter das Bild"). Gegenprobe: `D-08-farbreiz.jpg` mit
`0x0F00` — Farbe sauber in den Kanten.

**Damit ist auch die gestrige Abnahme einzuordnen:** sie lief über den *zweiten* Enable und war deshalb
farbrichtig. Auf einem frischen Kaltstart käme die Plane heute mit falschem Chroma-Stride hoch.

**Zu tun:** in `0093` sicherstellen, dass die vollständige Registerprogrammierung **auch** auf dem Pfad
läuft, der den Descriptor schreibt. Ich habe es nicht sofort geändert, weil ein Agent dieselbe Datei
gerade für den Vsync-Notifier bearbeitet — sonst kollidieren zwei Änderungen in `0093`.
Der Fix gehört zusammen mit dessen Ergebnis eingespielt und dann in einem Zug abgenommen.
