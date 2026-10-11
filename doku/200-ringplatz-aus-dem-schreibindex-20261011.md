# 200 - Der Ringplatz kommt aus dem Schreibindex der Aufnahme, nicht aus dem Firmware-Zeiger (11.10.2026, nachmittags)

**Kurz:** Fortsetzung von `doku/197`-`199`. Mit einem **bewegten** Bild ist am Pufferinhalt zu sehen, was der Schreiber tut: er
rotiert strikt A→B→C, jedes Bild landet vollständig in seinem Platz und bleibt dort zwei Bildzeiten liegen, bevor er wiederkommt.
Nur der Veröffentlicher (Zeiger `AFBD +0x320`) hält und überspringt. Und die Aufnahme sagt selbst, wo sie schreibt: **`INCAP
+0xa0c` ist der Schreibindex** (0 = A, 1 = B, 2 = C), er springt an jeder Quell-Bildgrenze zusammen mit dem Zähler `+0x104`.
Der afbd-Treiber wählt den Platz jetzt aus diesem Index (Modulparameter `ring_select`, Vorgabe 1) - für die Ebene den Platz, der
gerade beschrieben wird (fertig bis zum nächsten Vsync, an dem die Hardware die Adresse übernimmt), für den Notifier (Warp) den
zuletzt fertigen. Ergebnis am G-EU mit bewegter 1080p60-Quelle: **59,70 von 60 gezeigt, 0,30 Sprünge/s** (vorher 32,9 / 25,2),
Warp 59,7 fps ohne Verlust; 1080p30, 1080p50, 720p60 jedes Bild einmal; Bild sauber (Marco). Kernel-Patch `0255`. Paket `arbeit/aufnahme-takt-20261011/` (BERICHT §14, `scan60.py`, `zeitleiste2.py`,
`anzeige.py`, `patches/versuch-ring-select.diff`).

## 1 Was der Schreiber tut (gemessen am Inhalt)

`zeitleiste.py`/`zeitleiste2.py` lesen je Platz drei Zeilen (50, 400, 700; CRC über 128 Bytes) alle ~0,3 ms zusammen mit `INCAP
+0x104`, `+0xa0c`, Zeiger `+0x320` und dem Panel-Vsync-Stempel `0x0514fe68`. Quelle: ThinkPad 1080p60, Helligkeit im Wechsel
0,9/1,0 (jedes Bild anders). Auszug (ms):

```
F34@9.6 I2@9.7 wC0@11.2 PA@20.5 F35@26.3 I0@26.3 wA0@27.9 PB@37.2 F36@42.9 I1@43.0 wB0@44.6 F37@59.6 I2@59.6 wC0@61.2 PC@70.7 ...
```

- `F` = Quell-Bildgrenze (Zähler springt), `I` = `+0xa0c`, `wX0` = erste Zeile von Platz X ändert sich, `P` = Zeiger.
- An jeder Grenze springt der Index um eins in Tabellenreihenfolge, 1,6 ms später beginnt der Schreiber oben in genau diesem
  Platz (Zeile 400 nach ~9 ms, Zeile 700 nach ~16 ms) und ist vor der nächsten Grenze fertig. **A, B, C, A, B, C - nie zweimal
  derselbe Platz** (die Doppelschreibung aus `doku/198` §1 war aus dem Zeiger zurückgerechnet, nicht am Inhalt gemessen; sie gibt
  es nicht).
- Der Zeiger dagegen (Spur vom selben Lauf, `zeitleiste.py`): zeigt beim Panel-Vsync mal den Platz, der gerade beschrieben wird
  (2 ms hinter dem Schreiber, wie bei 720p), mal einen vor ein bis drei Bildern fertigen; hält alle 4-5 Vsyncs und überspringt
  dann eins. Beispiel gezeigte Quellbilder: 194 195 196 **196** 197 198 **200** 201 **201** 202 203 **205** ...

## 2 Der Schreibindex

`scan60.py` (alle Wörter von INCAP 0x06940000 und NR 0x05000000 bei ~280 Durchläufen/s): im Bildtakt ändern sich `+0x104`
(Zähler), `+0x600..60c` und `+0xa00..a28` (Statistik), und **`+0xa0c` mit genau den Werten 0, 1, 2**, 59,9 Wechsel/s. Die
Zeitleiste ordnet zu: `I2` → Schreiber in C, `I0` → A, `I1` → B. Die Puffertabelle steht in `+0x8f0` (Luma) / `+0x930` (Chroma),
Adresse >> 4, Einträge 0..2 = A, B, C. Keine Kalibrierung nötig: Platz = Index, zuletzt fertig = Index − 1.

## 3 Die Treiberänderung (afbd)

- `ring_select` (Modulparameter, 0644): 0 = Firmware-Zeiger wie bisher, 1 = Schreibindex (Vorgabe, wenn der INCAP-Syscon da ist;
  Phandle `allwinner,incap` am afbd-Knoten, sonst Suche nach dem `compatible`).
- Im Vsync-IRQ: Index und Zähler lesen; **Notifier** (hdmirx → Warp, liest sofort per GPU) bekommt den Platz Index − 1 (fertig,
  bleibt zwei Bildzeiten unberührt); **Ebene** bekommt den Platz Index (gerade in Arbeit): Adressen, die während eines Bildes in
  die Warteschlange `+0x70..` geschrieben werden, holt die Hardware ab dem nächsten Vsync, und bis dahin ist der Platz fertig;
  der Schreiber kommt zwei Bildzeiten später zurück, wenn die Anzeige unten ist. Der fertige Platz wäre für die Ebene falsch: in
  jeder Schwebung der beiden Takte gäbe es eine Strecke von Vsyncs, in der das Lesen genau dann oben beginnt, wenn der Schreiber
  oben anfängt - und der ist schneller.
- Langsame Quellen (30 Hz in ein 60-Hz-Panel): dort wäre der Platz in Arbeit zum nächsten Vsync **nicht** fertig; die Ebene
  bekommt dann ebenfalls Index − 1 (bleibt drei seiner Bildzeiten ganz). Entscheidung über das Verhältnis Quellbilder/Vsyncs
  über 32 Vsyncs, Schwelle 0,8.

## 4 Messung G-EU

Modul im Worktree gebaut (`build.sh kernel`, Baum `linux-6.18.38-a8ae276b…`, unverändertes Modul bitgleich mit dem am Gerät
`764ca830`; geändert `10806bf3`), 14:29 UTC getauscht (`/root/tausch-afbd.sh`, Sicherung `/root/sicherung-viddec-bildrate/`),
Neustart. `anzeige.py` liest **unsere** Ebenenadresse `AFBD +0x70` alle 0,25 ms (im Bypass der Ringplatz, im Warp der GPU-Puffer),
dazu `INCAP +0x104` (Quellbilder), den Zeiger und die Vsyncs; Quelle ThinkPad mit Helligkeitswechsel je Bild.

| Quelle, Pfad | gezeigt/s | Sprünge/s | Quellbilder/s | Firmware-Zeiger/s |
|---|---|---|---|---|
| 1080p60, Bypass, **Original-Modul** (Boot 25 min) | 32,9 | 25,2 | 60,1 | 32,9 |
| 1080p60, Warp, Original-Modul | 57,9 fps | - | 60,0 | 56,8 |
| 1080p60, Bypass, **neu** (10 s) | 59,70 | 0,30 | 60,0 | 43,6 |
| 1080p60, Bypass, neu, **60 s** | 59,70 | 0,30 | 60,0 | 47,4 |
| 1080p60, Warp, neu | 59,7 fps, 0 verworfen | - | 60,0 | 41,8 |
| 1080p30 → 720, neu | 30,00 | 0 | 30,0 | 29,9 |
| 1080p50 → 720, neu | 50,00 | 0 | 50,0 | 26,1 |
| 720p60, neu | 59,75 | 0,25 | 60,0 | 59,75 |

Die 0,25-0,37 Sprünge/s bei 60-Hz-Quellen sind der Taktunterschied (Panel 59,71 Hz, Quelle 60,00: ein Bild in 200 kann nicht
gezeigt werden); Stock-HY350 hat dasselbe (0,6/s, `doku/197`). Zeitlage (`zeitleiste3.py`): unser IRQ setzt die Adresse 2,8 ms
nach dem Panel-Vsync-Stempel auf den Platz, der gerade beschrieben wird; der ist bis zum nächsten Vsync fertig (8 ms Reserve in
dieser Phase, im ungünstigsten Fall startet das Lesen 2,8 ms vor dem Ende, 120 Zeilen hinter dem Schreiber und langsamer als er).
Marco: nichts aufgefallen, Bild sauber. Keine neuen Kernelzeilen.

## 5 Gerätestand, offen

G-EU: afbd-Modul `10806bf3` (`ring_select=1`), sonst wie `doku/199` §4 (Original-`display_cfg.xml`, TSE, EDID-Datei;
`h713-tv d6134496`). Rückweg: `sh /root/tausch-afbd.sh zurueck`. Offen: dasselbe am HY310 prüfen (1080p-Panel, dort skaliert
nichts - der Index-Weg gilt trotzdem, Messung mit `anzeige.py`); Panel-Pixeltakt näher an 60 Hz (Stock nennt 62 MHz = 59,98 Hz;
unsere PLL 24 MHz × N / 14 kann 61,71 oder 63,43), um den letzten Sprung in 3,4 s loszuwerden.
