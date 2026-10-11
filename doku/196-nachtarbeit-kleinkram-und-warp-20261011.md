# 196 - Nachtarbeit 11.10.2026: Kleinkram (B) und der Warp mit dem CPU-Regler (A)

**Kurz:** Marco schlief, Auftrag: erst Dinge, die ich allein entscheiden kann (B), dann beim Warp "alles rausholen" und
klären, warum der CPU-Regler so hoch zieht (A). Ergebnis A: **die CPU-Last mit laufendem Warp halbiert** (alle vier Kerne
5,9 % → 2,9-3,1 %) durch zwei gemessene Änderungen - schedutil darf den Takt nur noch alle 20 ms ändern statt alle
462 µs, und h713-tv zählt verspätete Warp-Bilder, statt für jedes eine Journalzeile zu schreiben. Die fehlenden Bilder
(~30-41 statt 60 fps) sind **kein Fehler von Warp oder Treiber**: die Aufnahme selbst liefert bei einem stehenden Bild nur
so viele, direkt am Flip-Zeiger gemessen, auch ohne Warp; ein Kernel-Versuch dagegen ist widerlegt. Compilerflags bringen
nichts; der nächste echte Hebel ist ein einziger Render-Durchgang je Bild. B: fünf kleine Fixes, vier davon in `main`.
Pakete `arbeit/nacht-b-20261011/`, `arbeit/warp-sparsam-20261011/` (BERICHT mit jeder Messung, Messskripte).

## 1 B - Kleinkram (05:32-05:50)

- **h713-keys** (TODO 2.52): die Bluetooth-Fernbedienung wiederholt gehaltene Tasten jetzt wie der IR-Empfänger (`EVIOCSREP`
  500/125 ms; IR am Gerät gelesen: 500/125, Bluetooth war 250/33 → alle ~40 ms); OK per Bluetooth (`KEY_SELECT`, HID "Menu
  Pick") gilt als `KEY_OK`. Rechner-Tests 22/22 (die neuen scheitern mit dem alten Skript), `EVIOCSREP` am echten Gerät
  geprüft. **Im Zweig `versuch/nacht-b`, am G-EU aufgespielt, das Gefühl beim Halten misst Marco** - erst dann `main`.
- **h713-remote-pair** (2.54): stdout zeilengepuffert, "found"/"ok paired" kommen ins Journal (Test liest die Zeilen, während
  `watch` läuft). `main`.
- **build.sh** (5.21): ohne U-Boot-Submodul packt das `mkimage` des Systems den FIT - im echten Bau bestätigt (der Kernelbau für
  A lief ohne `MKIMAGE=` durch). `main`.
- **Patch 0011** nach `zurueckgenommen/`, Serien-Index 278 (5.22); **Doku-Reste** 720p+Warp (durch 0183 behoben, stand noch
  "fix pending"), Lüfterdrehzahl, ARISC-Größe (5.16). `main`.
- **2.55** (Sonderzeichen im Login): `sunxi-ir` (und die Bluetooth-Fernbedienung) hängen am Handler `kbd`, ihre Tasten gehen
  also an das VT - der Weg ins Login-Feld ist damit plausibel, aber ohne gedrückte Taste nicht gemessen.

## 2 A - der Warp (05:55-06:55)

Gerät HY300PRO-G-EU, Quelle ThinkPad 1080p60 mit **gesperrtem, stehendem Bildschirm** (DPMS ab 05:28, für die Messungen
geweckt), Trapez zum Test. Kein perf, kein strace, kein debugfs im Abbild: gemessen über `/proc` (CPU-Zeit je Prozess),
die Statuszeilen der Daemons, `h713-warp ctl trace` (Zeitstempel je Slot) und eine Mess-Fassung des Warps mit CPU-Zeit je
Abschnitt (nicht in `main`).

**Die Regler.** `cpufreq-dt`, schedutil für alle vier A53, `vdd-cpu` ein PWM-Regler (0,81-1,16 V, 2,5 mV/µs), angegebene
Wechselzeit 308 µs, daraus `rate_limit_us` 462 µs. Mit Warp pendelte der Takt im 60-Hz-Rhythmus zwischen 480 und 1296 MHz,
`sugov:0` kostete 8-10 % eines Kerns - so viel wie der Warp. Messreihe (20 s je Wert): 462 µs → 5,7 % aller Kerne, 10 ms →
3,5 %, 20 ms → 2,9 %. **Fix:** `rootfs/overlay/etc/tmpfiles.d/h713-cpufreq.conf` setzt 20 ms beim Booten (nach Neustart
zurückgelesen). Die GPU (`simple_ondemand`, einziger Regler) ist unauffällig.

**journald.** h713-tv schrieb je Warp-Bild, das mehr als 25 ms nach dem vorigen kam, eine Zeile - bei 30 echten Bildern/s
27 Zeilen pro Sekunde, journald 1,5 % eines Kerns (in meiner ersten Rechnung fälschlich 15 %). **Fix:** zählen, höchstens alle
10 s eine Zusammenfassung. journald danach 0,0 %.

**Die fehlenden Bilder.** Der Warp wacht 0,1 ms nach jedem Slot auf und ist nach 1,5 ms fertig; er bekam aber nur 30-41
Slots/s. Zuerst vermutet: afbd liest den Flip-Zeiger nur im Vsync der Anzeige und verpasst Bilder, deren Ende auf den Vsync
fällt. Versuch (Kernel, afbd-Modul im Baum mit identischem Eingabe-Hash - das unveränderte Modul war bitgleich mit dem am
Gerät): zerrissenes Lesen sofort wiederholen, zweites Lesen eine halbe Bildzeit nach dem Vsync. **Widerlegt:** keine
Besserung. Direkt am Register (`/dev/mem`, AFBD +0x320, alle 0,5 ms) wechselt der Zeiger nur **30-35-mal pro Sekunde** - mit
Warp, ohne Warp, mit neuem und altem Modul; die Slot-Folge pendelt (`2102121010…`). Die Aufnahme lässt die Bilder also selbst
aus, vor dem Warp. Gestern Nacht mit Desktop waren es 52-59. Verdacht: bei stehendem Bild fallen nur Wiederholungen weg -
**mit bewegtem Bild zu prüfen** (`zeiger.py` im Bypass und mit Warp). Modul zurückgebaut, Versuch als Beleg im Paket.

**Was ein Bild kostet** (Mess-Fassung, 1296 MHz): zeichnen 490 µs, Fence/Abschicken 180, Übergabe an h713-tv 64, Slot holen
und zurückgeben 37 - zusammen ~0,77 ms. Je Durchgang (zwei je Bild: Luma, Chroma) legt Mesa/Panfrost für ~125 µs einen
GPU-Auftrag an, gleich welcher Aufruf der erste ist (ohne `glClear` übernimmt das Zeichnen die Zeit). `-O3 -mcpu=cortex-a53
-flto` gegen `-O2`: gleiche CPU je Bild. **Nächster Hebel:** ein Durchgang je Bild - die NV12-Ziele sind zusammenhängend
(Chroma direkt hinter Luma), als ein R8-Bild Breite × 1,5 Höhe in einem Auftrag zu beschreiben; ~250 µs/Bild weniger. Nicht
nachts gebaut: braucht Augen an der Wand.

## 3 Nebenbefunde

- Der G-EU **startete um 04:57 (Host) neu, ohne mein Zutun**; der UART-ESP lief danach erst 45 min, startete also etwa
  gleichzeitig - spricht für Strom. Kein "R_WDOG found armed" (kein Aus über crust). Das Journal davor ist weg (flüchtig,
  TODO 1.2a). Frage an Marco.
- Der ThinkPad schaltet seinen Bildschirm nach einer Weile ab (Cinnamon); für Messungen über Nacht `xset dpms force on`.

## 4 Stand am G-EU

Kernel, afbd und h713-warp wie vor der Nacht; h713-tv mit gezählten timing-Zeilen (`9212dcd6…`), h713-keys und
h713-remote-pair aus den Fixes (`7dff057e…`, `4dee9a7b…`), `/etc/tmpfiles.d/h713-cpufreq.conf` (20 ms); `warp.conf` wieder
wie vorher (Bypass), Regler wieder schedutil, GPU-Mindesttakt wieder 288 MHz. Sicherungen `/root/sicherung-nacht-b/`,
`/root/sicherung-warp-sparsam/`.

## 5 Für den Morgen (mit Marco)

1. **Bluetooth halten** (2.52): Lauter per Bluetooth gedrückt halten - steigt die Lautstärke jetzt so ruhig wie per IR (etwa 8
   Schritte pro Sekunde nach einer halben Sekunde)? Journal: `listening on /dev/input/eventN, repeat 500/125 ms as over IR`.
   Dann `versuch/nacht-b` (`3f620ad`) nach `main`.
2. **Bewegtes Bild** (2.47 a): ein Video am ThinkPad, dann `zeiger.py 5 bypass` mit Warp aus und an
   (`arbeit/warp-sparsam-20261011/zeiger.py`, nach `/run` kopieren). 60 Wechsel/s mit Bewegung = die Aufnahme lässt bei
   stehendem Bild nur Wiederholungen weg, alles gut.
3. **Ein Render-Durchgang** (2.47 b): erst bauen, wenn jemand auf die Wand schaut.
4. **Frage:** Hat jemand den G-EU um 04:57 vom Strom genommen?
5. Danach wie geplant: Push-Entscheidung (1.6/1.7), Release-Neubau 1.1a.
