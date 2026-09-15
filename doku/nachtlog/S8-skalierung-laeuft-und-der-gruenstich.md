# S8 - Die Skalierung läuft, und was sie mitbringt: der Grünstich

07./08.09.2026, 23:00-01:30 · Fortsetzung von [`S7`](S7-scaler-entschluesselt.md)

## Das Ergebnis zuerst

**720p wird korrekt aufs Panel hochskaliert.** Vollflächig, geometrisch richtig, mit Bildbeleg
(`re/captures/weltneuheit/wand-aktuell/ENDLICH.jpg`, `t3-1280x720-*.jpg`):

```
PROC    Quelle 1280x720  ->  Ziel 1920x1080
Scaler  0x05180008 = 0x3200AAAA   0x0518003C = 0x0000AAAA   0x05180014 Bit27 = 0
INCAP   aktiv 1280x720, rowbyte 0x50 = 80, Freigabe Bit 31 gesetzt
```

`0x3200AAAA` ist bitgenau der Wert, den die Herleitung aus `CalcScaleRatio` in
[`S3`](S3-scaler-gefunden-und-bewiesen.md) vorhergesagt hat. Die Firmware programmiert ihn selbst.

**Aber:** ab dem ersten Wechsel hat das Bild einen **Grünstich**, und nach vier bis fünf Wechseln
kippt der Zustand ganz. Damit ist der Stand *nicht* auslieferbar - wohl aber ein Durchbruch.

## Die vier Patches und was jeder tut

| Patch | Wirkung |
|---|---|
| **`0117`** | Veröffentlicht den VidDec-Descriptor neu, wenn sich die Quellgeometrie ändert. **Ohne ihn skaliert die Firmware nie** - gemessen: Scaler bleibt `0x43010000`, Bild bricht um. |
| **`0120`** | Hält die vier Fensterwörter (rec 28/30/32/34) auf der **Panelgröße**. Sie sind nicht die Bildgeometrie, sondern die Konfiguration des Fenstermanagers; standen dort Quellmaße, staucht `CalcPropRect` die Aufnahme proportional auf 853×480. |
| **`0121`** | Schaltet die Aufnahme nach der Veröffentlichung direkt frei (Bit 31 in `0x06940928` **und** `0x06940968`), statt über einen Quellenwechsel - der würde einen zweiten, fehlerhaften Neubau auslösen. |
| **`0122`** | Setzt dabei nach, bis die Freigabe hält: die Firmware löscht sie kurz nach unserem Schreibvorgang noch einmal. Gemessen 159-223 ms bis sie steht. |

Zurückgenommen und in `mainline/patches/zurueckgenommen/`: `0108` (Sentinel-Fehldeutung) und
`0118` (Ziel = Panel in den Wörtern 4/5, beruhte auf falsch gelesener Rechteckreihenfolge).

## Was gemessen wurde - Wechselreihe

Aus sauberem Kaltstart, Zuspieler gespiegelt auf die Testauflösung:

| Wechsel | Scaler | Freigabe | Bild |
|---|---|---|---|
| → 720p | `0x3200AAAA` | direkt, nach 159 ms | **vollflächig, geometrisch korrekt** |
| → 1080p | `0x43010000` | direkt, nach 221 ms | **korrekt** |
| → 720p | `0x3200AAAA` | direkt, nach 165 ms | korrekt |
| → 1080p | `0x43010000` | direkt, nach 223 ms | korrekt |
| → 720p (5.) | `0x3200AAAA` bleibt | direkt | **kippt: Signal weg, V4L2 0x0** |

Ab dem fünften Wechsel bleibt der Scaler auf dem 720p-Verhältnis hängen, obwohl 1080p anliegt, und
das Signal geht verloren.

### Rückwege, gemessen

| Weg | Signal zurück | Scaler zurück |
|---|---|---|
| `SetSource(1)` → `SetSource(3)` → `DisableBlackScreen` | manchmal | nein |
| HDMI am Zuspieler aus/an, danach Quellenwechsel | **ja** | nein |
| Scaler-Register von Hand zurückschreiben | - | **nein** (PROC-Fenster greifen nicht) |
| **Kaltstart (`sonoff_ctl restart`) + Quellenwechsel** | **ja** | **ja** |

Ein Neustart **allein** genügt nicht; der Quellenwechsel danach ist Pflicht. Und mehrfach ist das
Board nach einem `reboot -f` gar nicht wiedergekommen - dann hilft nur die Steckdose.

## Der Grünstich

**Symptom:** Ab dem ersten Auflösungswechsel liegt ein Grünstich über dem ganzen Bild, auch nach
Rückkehr auf 1080p. Er verschwindet erst mit einem Kaltstart.

**Wie man ihn sieht:** an der **Taskleiste**. Sie ist im sauberen Kaltstart neutral dunkelgrau und
danach deutlich grün. Ausschnitt vergleichen:

```python
from PIL import Image
Image.open("<foto>.jpg").convert('RGB').crop((200,470,1180,590)).resize((980,120))
```

**Ursache: unbekannt.** Geprüft und ausgeschlossen:

| geprüft | Ergebnis |
|---|---|
| Chroma-Gain `0x05140508` Bit 28 (kippt beim Neubau von 0 auf 1) | zurückgesetzt → **kein Effekt** |
| `0x05140120` (wird beim Neubau auf 0 gewischt, sauber `0x080C0800`) | zurückgeschrieben → **kein Effekt** |
| `0x05001028` / `0x05001030` (ebenfalls genullt) | **nicht beschreibbar** von der ARM-Seite |
| Vollständiger Bildeinstellungssatz: `SetVideoRange 0`, `SetPictureMode 1`, `SetTNR 2`, `SetSNR 1`, `SetDCI 2`, `SetBlackExtension 1`, Helligkeit/Kontrast/Sättigung/Farbton/Schärfe | alle elf RPCs laufen sauber (n=0), **kein Effekt** |

Ein angehobener Schwarzwert im Grünkanal ist ein **Versatz in der Farbkonvertierung**. Die
Kandidatenregister aus dem Differenzabzug sind oben durch; der nächste Schritt wäre ein Abzug im
**Stock-Zustand nach einem Auflösungswechsel** - den haben wir für diesen Fall nicht, und ohne ihn
ist alles Weitere geraten. Marcos Einwand dazu ist der Maßstab: **unter Stock passiert das nicht**,
also fehlt uns etwas, das Stock tut.

## Zwei Messfehler, die Zeit gekostet haben

**1. `wandcheck.py std` taugt nicht für Farbe.** Die Kamera macht automatischen Weißabgleich und
rechnet einen globalen Farbstich weg - die Messung zeigte sogar einen leichten *Rot*überschuss,
während die Taskleiste sichtbar grün war. Für Farbfragen hilft nur der direkte Bildvergleich eines
Ausschnitts mit bekanntem Sollwert (die Taskleiste), oder das Auge des Nutzers.

**2. `std` taugt auch für Geometrie nur bedingt.** Ein doppeltes Bild hat dieselbe Streuung wie ein
gutes; ein zerrissenes sogar mehr (81,8 gegen 48). **Fotos ansehen, nicht Zahlen lesen.** Diese
Sitzung hat mehrfach „sieht gut aus" gemeldet, wo das Bild doppelt oder gestaucht war.

**3. Falsches Wartekriterium.** `h713_hdmirx_signal_present()` prüft die AFBD-Flip-Zeiger - die
laufen auch von der Plane-Seite. Als Kriterium für „die Aufnahme läuft" ist es wertlos: der Treiber
meldete Erfolg nach 12 ms, während das Freigabebit aus und die Wand schwarz war. Richtig ist
`0x06940928` Bit 31.

## Was als Nächstes zu tun ist

1. **Den Grünstich klären.** Registerabzug unter Stock nach einem Auflösungswechsel, dann Differenz
   gegen unseren Zustand. Alles andere ist Raten.
2. **Das Kippen nach vier Wechseln klären.** Vermutung: die erzwungene Freigabe geht an der
   Zustandsmaschine der Firmware vorbei und häuft Fehlzustand an. Stock schließt jeden
   Quellenwechsel mit `DisableBlackScreen` ab - das haben wir im neuen Pfad nie mitgesendet.
3. **Erst danach** die Konsolen-Sperre in `userspace/hy310-tv/main.c` entfernen und den
   Testschalter `H713_TV_SKALIERTEST` streichen.
