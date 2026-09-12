# A2 — Wie lange muss HPD beim EDID-Upload unten liegen? **200 ms.** (Board-Agent, 07.09. 08:33–08:36)

Auftrag: Fund **A2** der Regel-1-Durchsicht (`REGEL1-durchsicht.md`). Der Treiber aus `0091` hielt HPD
**10 s** unten (`HPD_DOWN_MS 10000`, `msleep()` in `arisc_hdmi_edid_init()`), ohne Beleg für genau diese
Dauer. Der Wert stammte aus dem Diagnoseskript `arisc_edid_init.sh` (`sleep 10`) und ist in
`J-pflichtliste.md` als Fund **W8** verzeichnet: *kein Stock-Beleg*. Anders als im Skript stand er nun im
**Betriebspfad**: `arisc_hdmi_edid_init()` läuft im Probe, machte die Anbindung des Aufnahmegeräts zehn
Sekunden lang und war der einzige Grund für `PROBE_PREFER_ASYNCHRONOUS`.

Meine frühere Messung `M4-hpd-dauer.md` deckt diesen Fall **ausdrücklich nicht** — sie betraf den
Wiederanlauf-Zyklus, bei dem die Quelle das EDID schon hatte.

## Aufbau

Ein Mitschreiber auf dem **Zuspieler** (`/tmp/hpdwatch.sh`, 50-ms-Raster) protokolliert jede Änderung von
`/sys/class/drm/card0-HDMI-A-2/status` mit Zeitstempel — so werden echte Flanken sichtbar statt
SSH-Latenz. Dann fünf `PullHotPlug`-Zyklen mit steigender Senkendauer.

## Messwerte

| HPD unten | getrennt um | verbunden um | Trennung, wie der Zuspieler sie sieht |
|---|---|---|---|
| **0,2 s** | 08:33:29,299 | 08:33:31,053 | **1,75 s** |
| 0,5 s | 08:33:41,087 | 08:33:43,164 | 2,08 s |
| 1 s | 08:33:53,211 | 08:33:55,745 | 2,53 s |
| 2 s | 08:34:05,790 | 08:34:09,381 | 3,59 s |
| 5 s | 08:34:19,385 | 08:34:25,950 | 6,57 s |

**Jede** Dauer erzeugt eine saubere Flanke, auch die kürzeste. Die Trennung, die der Zuspieler sieht, ist
durchgehend ~1,5 s länger als die Senke — das ist sein eigenes Abtast- und Entprellverhalten, nicht unseres.

## Die Gegenprobe: wird dabei auch wirklich ein EDID gelesen?

Eine Flanke allein beweist noch nicht, dass die Quelle das EDID neu liest. Deshalb: Ausgang am Zuspieler
abgeschaltet (Modusliste weg), dann ein **0,2-s**-Zyklus, dann nachgesehen:

```
status : connected
EDID   : 00 ff ff ff ff ff ff 00 5e 78 43 48 21 03 00 00     <- gueltiger Kopf, Hersteller 5e 78
Modi   : 1920x1080 60.00*+ 50.00 59.94 30.00 ... / 4096x2160 ...
```

Vollständige Modusliste aus dem hochgeladenen EDID. **200 ms genügen.**

## Ergebnis und Änderung

`HPD_DOWN_MS` in `0091` von `10000` auf **`200`** gesetzt, mit dem Messbefund im Kommentar. Der Wert ist
doppelt gedeckt:

1. **gemessen** — kleinste geprüfte Dauer, die Flanke *und* EDID-Neulesung erzeugt;
2. **Stock-Wert** — `HDMI_SetHPDTimeInterval(0xC8)` = 200, im Stock-elog als
   `SetHPDTimeInterval from 200 to 200` (`re/captures/weltneuheit/elog-stock-LIVE.bin`).

Messminimum und Stock-Wert fallen zusammen; eine längere Dauer bräuchte einen eigenen Grund.
Serie danach geprüft: **71/71 sauber**, im erzeugten Baum steht `HPD_DOWN_MS 200`.

**Nebenwirkung, erwünscht:** der Probe des Aufnahmegeräts dauert jetzt statt gut zehn Sekunden knapp eine.

## Was das nicht sagt

Ob **unter** 200 ms noch etwas geht, ist nicht gemessen — und wäre auch uninteressant, weil HDMI selbst
mindestens 100 ms verlangt und Stock 200 nimmt. Ebenfalls offen bleibt, ob eine andere Quelle
(nicht dieser ThinkPad) längere Senken braucht; das Entprellverhalten ist Sache der Quelle.
