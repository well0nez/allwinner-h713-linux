# 171 - Standby-Fehler B: DMA-Master verlieren den DRAM, weil die Display-Pipeline durch den Self-Refresh läuft; Behebung gemessen (09.10.2026, 04:30)

**Kurz:** Nach etwa jedem zweiten Aufwachen aus dem Standby to RAM antworteten USB-Kamera und WLAN nicht mehr, das Resume
hing, der Zeitschalter setzte die Box zurück (Fehler B, `doku/170` Folgearbeit, LAGE vom 08.10. nachts). Gemessen ist
jetzt: nicht die beiden Geräte versagen, sondern alle DMA-Master kommen nach einem solchen Aufwachen nicht mehr an den
DRAM, die CPU schon. Auslöser ist die Display- und Videopipeline, die die Anzeige-MIPS eingerichtet hat und die nach dem
rohen Park der MIPS durch den Self-Refresh weiterläuft. Werden ihre Takte über den Schlaf abgeschaltet, tritt B nicht
mehr auf: cpu_comm-Patch, am HY310 9 von 9 gut, die Form in suspend_late 7 von 7, auf dem r1test2-Stand 6 von 6, auf dem
R2-Testabbild in 10 von 10 Aufwachen. Alles in Kopien (Paket `arbeit/standby-display-20261009/`, Testmodul in `updates/`
der Box mit Sicherung; in der R2-Serie als 0238). Protokoll: `arbeit/crust-20261007/STATE.md` ab 00:55.

## 1 Der Mechanismus (gemessen)

Testmodul `h713-hangdump-test` (nur Test): 2, 2,05, 4, 8 und 12 s nach dem Aufwachen eine 4-KiB-Kopie über den
allgemeinen DMA-Controller, die EHCI1-Warteschlange über die Strukturen des Treibers, SMHC1 und die Pins. In einem
schlechten Aufwachen (Lauf h1, wiederholt in k3, v1, xn2, xn3):

- DMA-Kopie: vor dem Schlaf fertig nach 1,2 ms; danach bei allen fünf Blicken nicht fertig nach 222 ms, Ziel leer.
- EHCI1: die SETUP/IN/OUT-qTDs der Steueranfrage aktiv, Fehlerzähler unberührt, das QH-Overlay hat nie einen qTD geladen
  (`cur 00000000`): der Controller liest seinen Zeitplan nicht aus dem DRAM. Die Kamera ist unschuldig.
- SMHC1: CMD53 als Befehl abgeschlossen, die Daten-DMA steht in DESC_RD.

Das grüne Bild nach einem schlechten Aufwachen passt dazu: auch der Scanout bekommt nichts aus dem DRAM.

## 2 Eingrenzung (Reihen, je 5 s Schlaf, FEL-Testbild v1)

| Reihe | Aufbau | Ergebnis |
|---|---|---|
| A7 | Aufbau des 07.10. auf heutigem Stand (hdmirx nie geladen, drei Treiber per Hand) | 6/6 gut |
| P | Standard, Suspend unmittelbar vor PSCI abgebrochen (Park, genpd, Watchdog gelaufen) | 6/6 sauber |
| B7 | A7 plus hdmirx (Pipeline freigegeben) | b1 gut, b2 C2 |
| X | Display-Treiber abgemeldet; R mit Display-Bus-Reset über den Schlaf, N ohne | R 5/5 gut, N 1/3 |
| G | Standard, alle fünf Display-Takte über den Schlaf aus, ohne Reset | 6/6 gut |
| F | Standard mit der Behebung (Abschnitt 3) | 9/9 gut, dazu ein C1 vor dem Code der Behebung |

Widerlegt (je mindestens ein schlechter Lauf): HDMI-Quelle aus (q1), INCAP-Aufnahme im Suspend stoppen (Testpatch, k1-k3),
`THal_Vp_Deinit` vor dem Schlaf (v1), h713-tv und warp stoppen (s1), dazu vom 08.10. PB5-Schiene, DRAM-Inhalt, CPU-Zahl.
Der heutige Stand von U-Boot, BL31, crust und Kernel ist nicht die Ursache (A7). Grundrate im Standardaufbau: am 08.10.
12 von 22 aufgewachten Läufen B, dazu C2; in dieser Nacht ohne Abhilfe 7 von 7 schlecht.

Der Hersteller setzt vor jedem Standby den Display-Bus in Reset und schaltet die Display-Takte und die Display-PLL ab
(`ge2d_suspend`, nach `THal_Vp_Deinit` und dem MIPS-Halt). Linux tat bisher nichts davon.

## 3 Die Behebung

cpu_comm schaltet die fünf Display-Takte (deint, panel, svp-dtl, afbd, bus-disp) ab, solange die MIPS geparkt ist, und
schreibt die gesicherten Registerwörter beim Aufwachen zurück, bevor ein Resume den Block anfasst. Kein Reset: ein Reset
verliert, was die geparkte MIPS eingerichtet hat, und afbds Resume hängt dann den Bus (gemessen, Läufe dd1, dd2). Mit
den Takten stehen die Engines und laufen nach dem Aufwachen weiter.

Zuerst gemessen in der noirq-Fassung (Reihe F, 9 von 9). Die Form, die in die Serie geht (R2 `0238-soc-sunxi-cpu-comm-
the-display-clocks-go-off-with-the-parked-mips.patch`), schaltet schon in suspend_late direkt nach dem Park ab, vor genpds
TVCAP/TVFE-Abschaltung, und in resume_early wieder an: Reihe L 7 von 7 (kein C1), zwei Boots mit je zwei Schläfen ohne
MIPS-Neustart gut (Z), auf dem r1test2-Stand (crust ecf2ddc, TF-A 175c6948f) 6 von 6 (V2). Auf dem R2-Testabbild
(`doku/172`) in keinem von 10 Aufwachen Kamera -110 oder WLAN-Timeout.

## 4 Offen

- C1 (Hänger beim Einschlafen nach der arisc-Zeile im noirq-Fenster) bleibt: in dieser Nacht einmal im echten Schlaf
  (f2, mit der noirq-Fassung) und einmal im Abbruchpfad (p1); mit der suspend_late-Form auf den FEL-Abbildern 0 von 20,
  auf dem R2-Testabbild 3 von 13 (`doku/172`).
- C2 trat mit abgeschalteten Display-Takten nicht mehr auf, ist aber nicht gezielt gemessen.
- Die genaue Stelle im Bus (Port, Transaktion) ist nicht gemessen. Erklärung, nicht Messung: crust hält den
  DRAM-Controller im Schlaf im Reset; eine Anfrage in dieses Fenster kehrt nie zurück.
- Das Bild bleibt nach dem Aufwachen stehen, bis die MIPS neu gestartet wird (Stufe 3 des Standby-Hakens, `doku/172`).
