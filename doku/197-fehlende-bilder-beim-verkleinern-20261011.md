# 197 - Fehlende Bilder bei 1080p60 am 720p-Panel: was es nicht ist (11.10.2026, vormittags/mittags)

**Kurz:** Marcos Frage nach `doku/196`: "das kann doch nicht sein, dass MIPS zu lange braucht - ist das eher ein
Bedienungsfehler?" Am HY300PRO-G-EU (Panel 1280×720) mit einer 1080p60-Quelle zeigt das Panel nur einen Teil der Bilder.
Gemessen: **die Aufnahme liefert alle 60 Bilder/s**; die Anzeige gibt einen Teil davon zu spät frei (ein Bild wiederholt, das
nächste übersprungen). Das passiert **nur bei 60 Hz und Verkleinern** - 720p60, 1080p30 → 720 und 4K30 → 720 laufen ohne
einen einzigen Sprung. Die Menge schwankt stark: direkt nach einem Moduswechsel 1-4 Sprünge/s, nach Stunden Laufzeit bis 17/s.
Widerlegt sind: MIPS-Takt, Kopplung Panel/Quelle, Bildrate im VidDec-Deskriptor, TNR und die übrigen Bildverbesserer,
Bus- und Speichereinstellungen. Die Ursache ist offen. Paket `arbeit/aufnahme-takt-20261011/` (BERICHT §1-10, Skripte,
IDA-Skripte, Stock-Messprogramm).

## 1 Messweg

Alles am G-EU nur gelesen über `/dev/mem`: Flip-Zeiger AFBD `+0x320` (alle 0,25 ms), Vsync der Anzeige (IRQ `h713-afbd`),
und **`INCAP 0x06940104` = (Bildnummer der Quelle << 16) | Zeile** - damit sind Quellbilder und Quellzeile direkt sichtbar.
Skripte `phase.py` (Wechsel, Ringschritte, Vsync), `phase6.py` (Quellbild/-zeile je Wechsel), `phase7.py` (Quellzeile bei den
Zeitstempeln `0x0514FE64/68`). Ein Sprung ist ein Zeigervorschub um zwei Ringplätze. An der Stock-HY350 dasselbe über
`/sys/class/sunxi_dump/dump` mit `hy350/zeiger350` (statisch, armv7, ohne libc).

## 2 Was gemessen wurde

| G-EU, Quelle | gezeigt/s | Quellbilder/s | Sprünge/s |
|---|---|---|---|
| 1280×720 @ 60 (ohne Skalierung, `doku/196`) | 59,8 | 60 | ~0 |
| 1920×1080 @ 30 → 720 | 30,00 | 30,00 | **0** |
| 3840×2160 @ 30 → 720 | 30,00 | 30,00 | **0** |
| 1600×1200 @ 60 → 960×720 | 55,6 | 59,3 | 3,7 |
| 1920×1080 @ 60, direkt nach Moduswechsel (5 Läufe) | 55,5-59,3 | 58,5-61,5 | 1-4 |
| 1920×1080 @ 60, nach Stunden bzw. nach Kabel-Umstecken | 38,6-47 | 58-60 | 11-17 |
| 1920×1080 @ 50 → 720 (Panel schneller als die Quelle) | 36,4 | 51,4 | 15 |

- Der Sprung-Ablauf ist starr (z. B. 4 Quellbilder: +1, wiederholen, +1, +2) und hängt **nicht** von der Zeile ab, in der
  die Quelle beim Panel-Vsync steht (flach über 0-1124).
- Der Zeiger springt im Takt des **Panels** (59,71 Hz, Ordnung 0,975), nicht der Quelle; kein Firmware-Code schreibt ihn
  (IDA: alle Zugriffe der Firmware auf AFBD `0xBA60xxxx` liegen in +0x00..+0x68) - er ist ein Hardware-Register.

| Stock-HY350 (Panel 1920×1080), Quelle | gezeigt/s | Quellbilder/s | Sprünge/s |
|---|---|---|---|
| 1920×1080 @ 60 (ohne Skalierung) | 59,46 | 60,06 | 0,6 (Taktunterschied) |
| 3840×2160 @ 30 → 1080 | 27,86 | 30,06 | 2,2 |

60 Hz mit Verkleinern an der HY350 nicht gemessen (1920×1200 rastete nicht ein; 1600×1200 nicht mehr versucht).

## 3 Was es nicht ist

- **MIPS-Takt:** `0x02001600 = 0x80000002`, Quelle 0 ist laut Herstellertabelle `pll-periph0-2x` (1200 MHz) → **400 MHz wie
  Stock**. Die Mai-Notiz "8 MHz" las die geratene Quellenliste unseres CCU-Treibers.
- **Kopplung Panel/Quelle:** Die Firmware hat sie (`freerun_lock.cpp`, `swpll/swpll.c`, Register `0x0514FE30` Bits 30:28),
  aber der Regler ist bei uns **und bei Stock** aus (`0x104`); die Stock-HY350 läuft mit 59,46 Hz neben 60,05 Hz frei. Stock
  `panel_config.ini`: `PanelTimingWorkMode = 2` (feste Totale). Außerdem verliert eine 50-Hz-Quelle an unserem schnelleren Panel
  genauso. Unser Panel: 1360×760 bei 61,71 MHz = 59,71 Hz (`h713_mips.c`), Stock will 62 MHz - eigener, kleiner Punkt.
- **Bildrate im VidDec-Deskriptor** (Wort 13/14 = `frame_rate_before/after_frame_rate_change`, fest 30000 = 30 Bilder/s): die
  "Stock-Vorlage" war der Satz von Androids Videodecoder (Startbild, 30 fps), nicht HDMI. Versuch mit 60000 (Kopie,
  Modulparameter, Sicherung `/root/sicherung-viddec-bildrate/`): kommt bei der Firmware an, aber dieselben Sprünge wie das
  Original nach ebenso frischem Neustart (46,9 gegen 47,0/47,9). Zurückgebaut. Nebenwirkung des Versuchs: hdmirx erkennt "unseren"
  Signalsatz nur an 30,00 Hz (Patch 0129) und meldete mit 60000 "not locked".
- **TNR und Bildverbesserer:** TNR aus allein ohne Wirkung; DCI, Schwarzerweiterung, SNR und TNR zusammen aus ~2 Bilder/s.
- **Puffer, Bus, Speicher gegen Stock:** INCAP/NR-Puffertabelle (6 Plätze `[A,B,C,C,C,C]`, Anzahl 3), AFBD `+0x10`, NSI
  `0x05700000` (1024 Wörter) und DRAM-Controller `0x04810000` (bis auf das Größenwort) an G-EU und HY350 identisch; DRAM 792 MHz
  wie die Variante.
- **Freilaufende interne 60-Hz-Zeitbasis:** `0x0514FE64` ist der Eingangs-Vsync (springt immer in Quellzeile 4-32), keine eigene
  Zeitbasis - die Hypothese hat dort keinen Beleg.

## 4 Offen

- Was im Pfad "Verkleinern bei 60 Hz" ein Bild zu spät freigibt, und warum die Menge über Stunden wächst und ein Moduswechsel
  sie zurücksetzt. Ein Langzeit-Mitschnitt läuft seit 09:24 UTC am G-EU (`h713-ratelog`, alle 5 min 10 s, `/root/ratelog.txt`).
- Ob Stock bei 60 Hz mit Verkleinern genauso verliert - an der HY350 nicht gemessen.
- Die Firmware-Shell (`crtc dump_cfg`, `start_frl`, doku/98) ist auf der G-EU-Firmware nicht eingerichtet (Adressen des
  RTT-Blocks und des elog stammen vom HY310).
