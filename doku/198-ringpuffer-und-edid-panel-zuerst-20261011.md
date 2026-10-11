# 198 - Der Dreier-Ring der Aufnahme, und warum die EDID jetzt das Panel zuerst nennt (11.10.2026, mittags)

**Kurz:** Fortsetzung von `doku/197`. Marco: "das Ergebnis ist inakzeptabel", dann freie Hand. Gefunden: die Firmware/Hardware
schreibt die Aufnahme in einen Ring mit **drei** Plätzen; beim Verkleinern (1080p60 → 720p-Panel) schreibt der Schreiber zwei
Bilder nacheinander in denselben Platz und zerstört das erste - jedes vierte bis fünfte Bild. Das Ringmodell reproduziert die
Messung; vier Plätze wären verlustfrei, aber der Ring lässt sich von außen nicht vergrößern (drei Wege probiert, alle
widerlegt, §2). **Lösung im Produkt:** `h713-tv` nennt in der EDID das Timing des Panels zuerst (`edid_prefer = panel`,
Vorgabe) - eine Quelle, die der EDID folgt, sendet 720p und wird Bild für Bild gezeigt: **59,7 von 60** statt 35-57. In `main`.
Paket `arbeit/aufnahme-takt-20261011/` (BERICHT §7-11, Skripte, `sim-ring.py`, `tse/`, `edid/`, `ida/`).

## 1 Der Mechanismus (gemessen, modelliert)

Spur je Quellbild (`phase8.py`, alle Register nur gelesen): Quell-Bildgrenze (INCAP `+0x104`), Zeiger `+0x320`, Panel-Vsync,
und `AFBD +0x6c/+0x70..7c` - letztere sind **unsere** Register (`AFBD_VIDEO_DIRTY`, `AFBD_VIDEO_Y0..Y3`): unser Kernel übernimmt
3,1 ms nach jedem Panel-Vsync den Zeiger in die Ebene (das "Vormerken"). Rückgerechnet schreibt der Schreiber Bildpaare in
denselben Puffer (F162/F163 → B, F166/F167 → C, F171/F172 → B). Modell (`sim-ring.py`: Schreiber 60,00 Hz, Panel 59,71 Hz,
3 Puffer, angezeigter und vorgemerkter Puffer gesperrt): **43,3 gezeigte/s, 16,6 Doppelschreibungen/s** - gemessen 43 und
~16. Mit 30 Hz: 0 Verluste. Mit 4 Puffern: 59,7/s.

Aber: im **echten Warp** (GPU zeichnet, Y0..Y3 = GPU-Puffer) genauso 41 Wechsel/s bei 59 Ringschritten. Die Sperre kommt also
nicht von unserer Ebene; der Schreiber doppelt in Hardware/Firmware. Ohne Verkleinern (720p60) folgt die Anzeige dem Schreiber
im selben Puffer (Flip bei Zeile 340 von 750), der Schreiber rotiert sauber - kein Verlust.

## 2 Drei Wege zu mehr Puffern - alle widerlegt

| Weg | Befund |
|---|---|
| Tabelleneinträge 4 (INCAP `0x069408fc/93c`, NR `0x0500040c/50c`) und Zähler `0x069408c0/c8` live auf 4 | Register nehmen die Werte, Zeiger läuft weiter über A,B,C |
| TSE-Speicherplan: 6 verschiedene Puffer in den ungenutzten Slot-Enden (`database.TSE`, Modul `DynamicMemory_1024M_1024M_PROJECTOR`, Offsets 0x45e3.., Feld `c` = Offset<<8; Parser-Diff nur die 12 Einträge; keine Prüfsumme) | Firmware programmiert alle 6 Adressen; Hardware nutzt weiter 3; die **Rauschminderung liest die Einträge 4-6** → "komisches Bild" (Marco). Original zurück, Neustart 10:32 UTC, Bild normal |
| Zähler live auf 6, `0x069408d0`-Feld 0x600, `0x06940978` 6/4 | `8c0/8c8`, `978`: keine Wirkung; `8d0` ist ein Modusfeld: 0x600 zerstört das Bild (21/s) |

Dazu ohne Wirkung: Low Latency an; alle unsere Dienste aus (51-53/s); MIPS bekommt im Leerlauf 0 Aufrufe/s; elog-Ring leer.
Stock-HY350: Puffertabelle, AFBD `+0x10`, NSI (1024 Wörter), DRAM-Controller identisch. Der Weg "1080p-Ring + GPU verkleinert"
(Marco: nein, 11.10. mittags) und ein Firmware-Patch (Marco: allerletzte Option) blieben außen vor.

## 3 Die Lösung: EDID mit dem Panel-Timing zuerst

Die bediente EDID ist die Stock-Datei des G-EU (`/lib/firmware/hy310-edid.bin`, vom Installer aus dem Abzug): erstes Timing
1920x1080p60 - auf einem 720p-Gerät. Von Hand gebaut (`edid/geu-720p-first.bin`: DTD 1 = 1280x720p60 CTA VIC 4, DTD 2 =
1080p60, VIC-Liste unverändert, Prüfsummen neu), über `h713-tv ctl edid block0` veröffentlicht: der ThinkPad listet
`1280x720 60.00 +` (bevorzugt), nach `xrandr --auto` 720p60 → Box **59,73/59,67 Wechsel/s, Ringschritte 60,0**.

In `h713-tv` eingebaut (`edid_panel_first()`, Tabelle 1280x720/1920x1080; `edid_prefer = panel | file`, Vorgabe panel): jede
veröffentlichte Hälfte bekommt das Panel-Timing zuerst, wenn das erste Timing der Datei größer als das Panel ist; die Datei
bleibt unangetastet, gilt automatisch auf jedem 720p-Board. Kaltstart 10:46 UTC: Journal `block 0 ... is served -- 1280x720
first for the 1280x720 panel (the file puts 1920x1080 first): published again`, ThinkPad bevorzugt 720p; Dienst-Neustart
findet die EDID bedient und verhandelt nicht neu (`edid_half_served` vergleicht gegen die Hälfte, wie dieses Programm sie
veröffentlicht). Python-Nachrechnung der Regel = byteweise die verifizierte Datei. Grenze: X behält über einen Replug den
eingestellten Modus; ein frisch angesteckter Zuspieler nimmt den bevorzugten. Eine Quelle, die auf 1080p besteht, behält den
Verlust; 1080p**30** ist verlustfrei.

## 4 Gerätestand G-EU (Ende)

`/usr/local/sbin/h713-tv` = `d6134496` (neu; Sicherung `/root/sicherung-viddec-bildrate/h713-tv.9212dcd6`), EDID-Datei, TSE,
afbd-Modul, warp.conf Original. ThinkPad auf 1280x720 @ 60. Langzeit-Mitschnitt `h713-ratelog` beendet (`laeufe/ratelog.txt`:
bei 1080p60 von 59 auf 34/s gefallen in einer Stunde, bei 720p60 immer 59,7).

## 5 Offen

- Warum die Verlustrate bei 1080p60 über Stunden wächst und ein Moduswechsel sie zurücksetzt (Phase im Dreier-Ring?).
- Wie Stock auf einem 720p-Panel mit einer 1080p60-Quelle abschneidet (HY350 ist 1080p; 1600×1200 rastet dort nicht ein).
- Ob eine 1366×768- oder andere Panelgröße ein CTA-Timing bekommt (Tabelle in `edid_panel_timings[]` erweitern).
