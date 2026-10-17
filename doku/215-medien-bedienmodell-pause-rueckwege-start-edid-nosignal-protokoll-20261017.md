# 215 - Das Nebenprojekt Medien: das Bedienmodell - Rückwege, Pause unter Seiten, HDMI als Modus, Start ohne geraden Ring, EDID ohne Deep Colour, Seite ohne Signal (17.10.2026)

**Kurz:** Fortsetzung von `doku/214`. Nach der Installation von rend5 am HY310 (17.10. 11:30 UTC) fand Marco drei Planungsfehler: unter dem
Launcher und den Settings lief HDMI weiter und schien in Lücken durch, Zurück aus den Settings landete auf HDMI, und HDMI war Lückenfüller zwischen
Programmen. Mythos hat daraus ein Bedienmodell gemacht (Zustände, Regeln, Rückwege, Plan in Paketen; Marcos sechs Entscheidungen); umgesetzt in
sieben Paketen, jedes am HY310 gemessen und von Mythos gegengelesen. **Nur am HY310 gemessen** (Kernel 6.18.38, `medien` 9adb7fc bis c073aca); der
HY300PRO-G-EU ist in keinem Punkt nachgemessen. Rohdaten und Berichte liegen in den lokalen Paketordnern (nicht veröffentlicht); die Zahlen unten
sind daraus übernommen.

## 1 Was gemessen wurde, bevor etwas geändert wurde (Bedienmodell §1-§4)

- Unter Launcher und Settings zeichnete h713-warp 60 Bilder/s auf der GPU, h713-tv committete sie, die Videoebene blieb an: 0,19 Kerne bei 480 MHz,
  GPU 200-600 MHz; derselbe Ring ohne Warp kostete 0,03 Kerne bei schlafender GPU. Eine Pausenstufe gab es nicht.
- Zurück aus den Settings beendete nur das Programm; niemand öffnete den Launcher wieder (h713-keys schloss ihn beim OK).
- Unter `source auto` war der HDMI-Ring der Lückenfüller: sobald kein Client ein Bild lieferte, schaltete der Warp nach höchstens 2 s auf den Ring.
- Das "Grün" (Marco, TODO 2.93): kein Puffer voller Nullen (0 in 12 Claims), sondern genau ein farbfalsches Bild an jeder Kante, an der die
  Videoebene mit Formatwechsel NV16 <-> NV12 aus- und angeht (Box-Kamera 12 von 12, Marcos Handyvideo 2 von 6), dazu bei Start und Signalrückkehr
  0,12-1,2 s der gerade, unentzerrte Ring.

## 2 Rückwege und Start-Einstellung (P1, P4)

Back geht eine Ebene zurück (Settings -> Launcher mit "Settings" gewählt -> der Modus darunter), Home schließt alles bis zum Modus, das Ende eines
Programms (Kodi Quit, SIGKILL) öffnet den Launcher mit "HDMI input" gewählt; Settings > Input: die Zeile "Source" entfällt, "On start: Launcher |
HDMI input | Kodi | Last used". Gemessen per uhid und Kamera: alle Rückweg-Zellen bestanden, je ein Warmstart pro Startoption.

## 3 Pause unter Seiten und HDMI als Modus (P2, P2b, P2c)

Unter einer deckenden Seite zeichnet der Warp nicht (0 Bilder/s, GPU suspendiert, 0,006 Kerne), der HDMI-Ton ist stumm, die Videoebene ist aus;
zurück aus der Seite in 22-35 ms. Der Ring wird nur im Modus HDMI gezeichnet: zwischen zwei Programmen bleibt das letzte Bild, bis das neue
sein erstes gezeigt hat - 0 HDMI-Bilder in 6 von 6 Wechseln. Eine Seite übergibt an die nächste ohne Lücke: Launcher <-> Settings je 0 HDMI-Bilder
(vorher 5 und 4). Nicht gemessen: der Ton unter einer Seite mit einer Quelle, die Ton sendet.

## 4 Start und Rückkehr ohne geraden Ring (P3)

h713-warp sagt h713-tv, ob es den Ring zeichnen wird (`want ring|none`); mit "ring" wartet h713-tv auf den Claim statt den geraden Ring zu zeigen,
und der Claim schaltet die Ebene einmal mit dem ersten NV12-Bild an. `ctl off`/`auto` 8 von 8 mit 0 geraden und 0 getönten Bildern, entzerrt nach
0,28-0,31 s (vorher 1,35 s mit 26 geraden Bildern); DPMS der Quelle 3 von 3, Bild 0,20-0,22 s nach dem Signal; Warmstarts und Standby ohne
"plane 38 on". Rest: der Dienstschalter `warp ctl on` aus einem geraden Ring zeigt ein getöntes Bild (NV16 -> NV12, kein Nutzerweg). RSS von
h713-warp mit offenem EGL ohne Claim +1 076 kB gegenüber geschlossen (eine Messung).

## 5 EDID ohne Deep Colour (V2)

Nach einem Port-Neustart verhandelte der ThinkPad auf 12 bpc (222,8 MHz) und die Box zeigte die Konsole. h713-tv löscht beim Veröffentlichen die
Deep-Colour-Angaben (HDMI-VSDB Flags 0xb8 -> 0x80); danach 7 von 7 Neuverhandlungen mit 148,5 MHz und Bild, auch nach einem Warmstart.

## 6 Seite ohne Signal (P5)

Ohne Signal zeigt die Wand die deckende Seite "No signal on HDMI - HOME: menu" statt der Konsole; Launcher und Settings gehen darüber und zurück;
die Konsole bleibt die Dienstansicht unter `ctl off`. Signal zurück: entzerrtes Bild nach 0,22-0,24 s. Abnahme wechsel, settings, ps, seiten,
standby 48 von 48. Rest: nach dem Wecken etwa 9 s Konsole, weil h713-tv mit der Display-Firmware neu startet (seit es Standby gibt; TODO).

## 7 Die HDMI-Aufnahme der Firmware (P7, Teil 1 und 2) - nicht eingebaut

Das Stock-System hält die Aufnahme beim Verlassen des HDMI-Eingangs mit `THal_Vp_SetSource(1)` an und startet sie mit `(3)`. Am HY310 gemessen: die
Aufnahme steht nach ~100 ms (6 von 6), zurück entzerrt nach 1,09 s (davor 0,25 s gerader Ring); danach verhandelte der ThinkPad mit HDCP auf 12 bpc
(heute durch V2 abgefangen); kein Temperaturunterschied gegen die Pause messbar, gerechnet 249 MB/s weniger Schreiben. Entscheidung: verzögert
einbauen (nach 5 min ohne HDMI an der Wand, Rückweg mit "Switching to HDMI..."), vorher ein Zustand "geparkt" im hdmirx-Treiber (V1) - beides auf
Marcos Wunsch verschoben. Nebenbefund: jede Abfrage `xrandr --prop` am ThinkPad friert dessen HDMI-Ausgang ~0,6 s ein (`referenz/messregeln.md`).

## 8 Nicht gemessen

Alles am HY300PRO-G-EU; der Ton unter Seiten; HDCP 2.2 (Fire TV) nach den neuen Wegen; Marcos Augentests zu Startkante und Flackern vorher/nachher;
ein Kaltstart mit Kamera.
