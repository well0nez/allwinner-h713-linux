# 199 - Die Panel-Kopplung der Firmware läuft: Frequenz ja, Phase zufällig (11.10.2026, nachmittags)

**Kurz:** Fortsetzung von `doku/198` für Quellen, die auf 1080p60 bestehen. Die Firmware hat eine Kopplung des Panels an die
Quelle (`swpll`, VTotal-Nachführung); sie war aus, weil die Panel-Konfiguration feste Zeilenzahlen vorgibt, und sie kann auf
diesem Panel von Werk aus nie einrasten, weil der Code das Taktverhältnis Eingang/Panel **ganzzahlig** teilt (148 500/62 000 = 2
statt 2,395) und an zwei weiteren Stellen 74,25 MHz als Panel-Takt annimmt. Mit drei Werten in unserer `display_cfg.xml`
(`work_mode 0`, `vtotal 755..765`, `pclk 74250000` - nur Rechengröße, keine PLL) **rastet die Frequenz ein** (Panel-Periode =
Eingangsperiode, Phase fest). Die Phase ergibt sich beim Einrasten zufällig, und an ihr hängt der Rest des Verlusts:
beste Lage 1,3 Sprünge/s (59 von 60), schlechte 9/s. Ein eigenes Phasen-Stellglied scheiterte am ersten Versuch (VTotal unter
742 hält den Panel-Taktgeber an). Paket `arbeit/aufnahme-takt-20261011/` §12; Skripte `frlstand.py`, `phasereg.py`, `phasenudge.py`.

## 1 Warum die Kopplung aus war und nicht einrasten konnte

- `display_cfg.xml` (vom Installer aus `panel_config.ini`): `work_mode 2` (feste H- und V-Totale, `PanelTimingWorkMode = 2`) →
  `_calc_main` setzt swpll-Modus 0. Mit `work_mode 0` (V nachführbar) und einem VTotal-Spielraum wird Modus 1 gesetzt
  (Register `0x0514fe30` Bits 30:28).
- Das Prüffenster für "Eingang stabil" (`swpll +8/+12`) war 1503..1535 Panelzeilen × 1359 = das Eingangsintervall in
  **2 ×** Panel-Takten (`_calc_main`: `v12 = pclk_main / pclk_panel` = 148500/62000 → 2). Der Hardware-Stempel zählt in
  **Eingangs**-Takten (2 474 980 = 2200 × 1125 bei 148,5 MHz), also 2,395 ×. Mit `pclk 74250000` geht die Division exakt auf,
  das Fenster wird [2 446 200..2 499 201] und trifft den Messwert. Die Firmware programmiert aus `pclk` keine PLL (`+0x18 = 0`,
  `+0x24` Bit 0 = 0 in beiden CRTC-Blöcken), der Panel-Pixeltakt bleibt 61,71 MHz aus U-Boot.
- Gemessen danach: VTotal pendelt 756/757, Panel-Vsync-Periode 3 333 302..309 Takte = Eingangsperiode, Phase über 10 s fest.

## 2 Die Phase

| Quellzeile beim Panel-Vsync | Sprünge/s | gezeigt/s |
|---|---|---|
| ~815 | **1,3** | 59,0 |
| ~345, ~540 | 1,8-2,6 | 57,6-59,0 |
| ~1049, ~728 | 5,0-5,6 | 55-57 |
| ~70-250, ~8 | 7-9,5 | 52-54 |

Elf Einrastungen landeten bei 352, 816, 728, 70, 160, 249, 1098, 530, 894, 337, 811 - zufällig. Grund: der schnelle Lock
(`try_fast_lock`, der die Phase setzt) läuft nie; davor steht `is_input_off` (`sub_8B126144`), das die Uhr mit festen
Konstanten (×1485/2000 = 74,25 MHz) in Pixeltakte umrechnet und gegen Stempel in 148,5-MHz-Takten vergleicht → immer "signal
off" → Zustand 1 (nur Frequenznachführung). `phase_delay` (`0x0514fe8c[31:20]`, TSE-Zeile) und das Verhältnis `dwRatioN/M`
(TSE `CRTC_MAIN_PROJECTOR`, 2/1 → 77/32 probiert) ändern daran nichts.

## 3 Eigenes Stellglied - erster Versuch, Lehre

Zustand 1 reagiert nicht auf Phasensprünge, also kann die ARM-Seite die Phase stellen: ein Bild lang ein anderes VTotal
(Register `0x0514fe08`, das die Firmware jedes Vsync neu schreibt). Erster Versuch mit Untergrenze 739: **Panel-Taktgeber
steht** (0 Vsync/s), weil 739 < 742 (720 + 20 + 2); die Firmware-Nachführung läuft nur im Vsync und kam nicht zurück;
Register auf 760 half nicht, nur der Neustart. Regel in `referenz/irrwege.md`. Der Spielraum 740..780 in `display_cfg.xml`
ist aus demselben Grund gefährlich (zurück auf 755..765).

## 4 Gerätestand G-EU (Ende)

`/boot/mips/display_cfg.xml` mit Kopplung (`work_mode 0`, `vtotal 755..765`, `pclk 74250000`; Original als
`/root/sicherung-viddec-bildrate/display_cfg.xml.orig`); TSE, EDID-Datei, afbd Original; h713-tv `d6134496` (EDID
Panel-zuerst, `main`). 1080p60 gekoppelt mit Zufallsphase: 53-59 von 60 (vorher 43-52); 720p60: 59,7.

## 5 Offen (TODO 2.57)

- Phasen-Stellglied richtig bauen: VTotal nur innerhalb 755..765, Schreibzugriff direkt nach dem eigenen Vsync-IRQ (afbd), ein
  Bild je Schritt, Phase aus INCAP `+0x104` beim Panel-Vsync messen, Ziel ~Quellzeile 800; dann die Verlustkurve über die
  Phase sauber aufnehmen (erwartet: ein Fenster mit 0 Sprüngen).
- Ob die Kopplungs-Werte in den Installer sollen (720p-Boards: `work_mode 0`, `vtotal ±5`, `pclk 74250000`) - Entscheidung Marco;
  `pclk` ist dort eine Rechengröße der Firmware, kein Takt.

## 6 Nachtrag 12:1x UTC - die Kopplung flackert

Marco (zurück am Gerät): "es flackert". Mit der Kopplung wechselt die Firmware VTotal **jedes Bild** zwischen 755 und 756
(Frequenz-Dither der Nachführung in Zustand 1), und die Hintergrundbeleuchtung ist an den Vsync gekoppelt (`display_cfg.xml`:
`pwm vs_lock='1'`) - die PWM-Periode springt mit. Original-`display_cfg.xml` zurück (`work_mode 2`, `vtotal 760` fest,
`pclk 62000000`), Neustart 12:0x UTC, Kopplung aus (Modus 0, VTotal 760 fest). **Die Kopplung ist damit so nicht produktreif:**
vor einem weiteren Versuch müsste entweder die PWM von der Vsync-Kopplung gelöst werden (`vs_lock='0'`, unsere Datei) oder das
Dithern aufhören (Zustand 3 der Firmware, der nie erreicht wird) - beides offen, beides nur mit Marco am Gerät zu beurteilen.
Die EDID-Regel (`doku/198`) bleibt die einzige produktreife Verbesserung; für Quellen, die auf 1080p60 bestehen, ist der Weg
offen (TODO 2.57).
