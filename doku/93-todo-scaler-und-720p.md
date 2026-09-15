# TODO - Scaler und 720p

> **Erledigt (Stand 08.09.2026):** dieser Plan ist abgearbeitet und am Gerät abgenommen; was davon abweicht und was übrig blieb, steht in [`00-STATUS.md`](00-STATUS.md) §4 und [`60-offen.md`](60-offen.md). Das Dokument bleibt als Planungsstand und Begründung.

> **08.09., 01:30 - die Skalierung läuft.** 720p wird korrekt aufs Panel hochskaliert
> (`0x3200AAAA`, PROC 1280x720 -> 1920x1080), mit Bildbeleg. Offen sind zwei Dinge: ein
> **Grünstich** ab dem ersten Wechsel und ein **Kippen nach vier bis fünf Wechseln**. Beides in
> [`nachtlog/S8`](nachtlog/S8-skalierung-laeuft-und-der-gruenstich.md), Einstieg über
> [`97-handoff-20260908.md`](97-handoff-20260908.md).

> **08.09., 00:20 - entschlüsselt.** Die Firmware rechnet und schreibt die Kette
> 1280×720 → 1920×1080 vollständig korrekt (`ratio [43690 x 43690]`, Aufnahme 1:1, rowbyte 80).
> Ein **zweiter** Durchlauf, ausgelöst durch unseren eigenen `SetSource`-Wiederanlauf aus `0099`,
> staucht die Aufnahme um 2/3 und überschreibt das Ergebnis. Der Scaler war nie das Problem.
> Fix: Aufnahme ohne Quellenwechsel freigeben (`memory_agent en`). Vollständig in
> [`nachtlog/S7-scaler-entschluesselt.md`](nachtlog/S7-scaler-entschluesselt.md).

> **07.09., 23:10 - der Blocker ist gefallen.** Die Firmware programmiert den Scaler selbst,
> sobald der VidDec-Descriptor die neue Geometrie trägt (`0117`). Gemessen: `0x05180008` von
> `0x43010000` auf `0x3200AA66`, Bit 27 gelöscht. Offen ist nur noch **K3**: die Aufnahme kommt
> nach der Neu-Veröffentlichung nicht zurück. Vollständig in
> [`nachtlog/S6-scaler-blocker-gefallen.md`](nachtlog/S6-scaler-blocker-gefallen.md).

Stand 07.09.2026, 22:30. Kurzfassung zum Wiedereinstieg; die Belege stehen in
[`nachtlog/S1`](nachtlog/S1-scaler-gefunden.md), [`S2`](nachtlog/S2-scaler-anwenden-versuche.md),
[`S3`](nachtlog/S3-scaler-gefunden-und-bewiesen.md), der Plan in [`92`](92-plan-de-scaler.md).

---

## TODO 1 - Der DE-Scaler

**Erledigt:** Register gefunden und Formel hergeleitet, bitgenau gegen den laufenden 1080p-Zustand
geprüft (5 von 5 Registern, inklusive der Modusfelder).

| Register | Bedeutung |
|---|---|
| `0x05180008` [21:0] | waagerechtes Verhältnis, 16.16-Festkomma |
| `0x05180008` [30:28] / [26:24] | Modusfeld waagerecht / senkrecht |
| `0x0518003C` [21:0] | senkrechtes Verhältnis |
| `0x05180014` Bit 27 | „keine Skalierung", gesetzt wenn beide genau 1:1 |
| `0x05180000` / `0x05180038` [15:0] | Anfangsphase waagerecht / senkrecht |

```c
/* sub_8B1A56B8, im elog "CalcScaleRatio" */
ratio = in < out ? (in << 16) / out : (out << 16) / in;     /* stets klein/gross */
mode_h = 3; mode_v = 2;
phase_h = (ratio_h + 0x10000) >> 2;
phase_v = (ratio_v + 0x10000) >> 1;
if (phase_h >= 0x8000)  { mode_h++; if (phase_h >= 0x10000) phase_h = 0; }
if (phase_v >= 0x10000) { mode_v++; phase_v = 0; }
```

Für 1280x720 -> 1920x1080: `0x05180008 = 0x3200AAAA`, `0x0518003C = 0x0000AAAA`, Bit 27 = 0,
Phasen `0x6AAA` / `0xD555`. Schreiben **wirkt** (Bild wurde sichtbar vergrößert).

**Bestätigt gegen Stock (S4):** `re/ida/IDA_hy310/elog_after_hdmird.txt` enthält einen echten
Stock-Auflösungswechsel - `in_win_size [720,480]`, `out_win_size [1920,1080]`,
`ratio [24576 x 29127]`. Genau die Formel oben. Ebenfalls dort: Stock übergibt in `Wce_SetWindow`
das Sentinel **7680x4320** („kein Ausschnitt"), wir sendeten 1920x1080 und nagelten damit Quelle und
Ziel auf 1:1 - behoben in `0108`. Der Patch allein ändert das Verhalten aber **nicht** (gemessen).

**Nachtrag (S5):** Der Stock-Mitschnitt läuft über sechs Minuten und enthält `UpdateWce`
**genau zweimal, beide bei Zeitstempel `[0]`** - Stock baut die Fensterkette bei der Initialisierung
und danach nie wieder. Die daraus folgende Gegenprobe (720p-Quelle anliegend, *dann* Probe, mit
Sentinel) wurde gefahren: Sentinel kommt an, Quelle wird erkannt, **Scaler bleibt 1:1**. Damit ist
auch `0108` als alleinige Lösung ausgeschlossen.

**Offen - der eine Blocker:** `UpdateWce` läuft bei uns nicht, und ohne ihn programmiert niemand
die Knotenkette (`Cap -> NR -> DETN -> Proc -> Panel`, alle in *einem* `WCETop::SetWindow`) um.
Einzelne Register von außen zu setzen ersetzt das nachweislich nicht. Nebenfrage, ebenfalls offen:
woher nimmt der aktive Scaler seine **Eingangsgeometrie**? Die
PROC-Fensterregister (`0x05140104/0108/0124/0128`) sind es nicht: sie bewirken nichts, auch nicht
ein Zielfenster von 960x540 bei 1080p, das hätte vierteln müssen. Diese Stufe ist in unserer Kette
umgangen. Kandidaten im aktiven Block, noch ungeklärt: `0x05180050` (`0x001E0438`), `0x0518002C`
(`0x006C0780`), `0x05180044` (`0x68`).

**Nächster Schritt:** offline in `display.bin` klären, welches Feld von `sub_8B1A5DF0` die
Eingangsbreite trägt (Objektfelder `a1+28/32/44/48/56` sind noch nicht zugeordnet; `a1+64/72/80/88`
tragen nachweislich die Panelmaße). Erst mit dieser Antwort einen Treiberpatch schreiben.

**Betriebsregel:** kein devmem-Probieren mehr. Es hat die Firmware zweimal hängen lassen (INCAP
weiter korrekt, aber leerer Signalsatz, RPCs von <10 ms auf 537 ms); nur ein Netboot-Neustart half.
Der nächste Versuch gehört in **einen** Patch, geprüft direkt nach einem Neustart.

---

## TODO 2 - 720p (und die übrigen Auflösungen)

**Erledigt:** Die Erkennung ist vollständig und ehrlich (`0107`) - `QUERY_DV_TIMINGS` aus
Signal-Info + INCAP, Plane folgt der Quellgeometrie, Y/C-Stride bei 720p korrekt, der
`mode_config.min_width`-Fehler (AddFB2-EINVAL) behoben.

**Der Kern des Problems, gemessen:** beim Auflösungswechsel ändern sich **genau vier Register**,
alle im AFBD-Block (`0x05600020/40/48/4C`) - also unser eigener Treiber. Der gesamte Rest der Kette
(PROC, Composition, Panel) bleibt auf 1920x1080 stehen. Wir stellen den Erzeuger um, niemand den
Abnehmer.

**Warum die Firmware nicht einspringt:** unser Treiber sendet `Wce_SetWindow` mit
`src == dst == 1920x1080`, fest verdrahtet, einmal beim Probe
(`0094-media-sun50i-h713-hdmirx.patch`, `h713_hdmirx_wce_args`). Ein erneuter Aufruf mit richtiger
Geometrie **gelingt, ändert aber nichts** - die Registerprogrammierung hängt hinter `UpdateWce`.
**M6 ist beantwortet:** die komplette Stock-Quellwechselfolge (`Wce_SetWindow` -> `SetSource(1)` ->
`SetSource(3)` -> `DisableBlackScreen`) läuft fehlerfrei durch und bewegt nichts. Deckt sich mit
`re/notes/DEAD-ENDS.md` §81 (HW-IRQ-getaktete Zustandsmaschine).

**Zustand heute:** `h713-tv` zeigt Panel-Quellen voll und fällt bei jeder anderen Auflösung
definiert auf die Konsole zurück, mit klarer Logzeile. Kein verzerrtes Bild. 1080p -> 720p -> 1080p
am Gerät: Bild / Konsole / Bild, `0 ohne Antwort` durchweg.

**Nächster Schritt:** hängt vollständig an TODO 1. Sobald der Scaler programmierbar ist:
1. `h713_hdmirx_wce_args` von der festen Panelgeometrie auf die gemessene Quellgeometrie umstellen
   (Quelle = Signal, Ziel = Panel).
2. Scaler im Treiber setzen, wenn Quelle != Panel.
3. Konsolen-Sperre in `userspace/h713-tv/main.c` entfernen.
4. Danach die übrigen Auflösungen: `timings_cap` und `match_preset` aus der `kHalSignalID_*`-Tabelle
   in `display.bin` füllen statt aus dem, was zufällig getestet wurde. Zeilensprung (1080i) und
   Downscale (4K) bleiben eigene Aufgaben.

---

## Prüfstand - nicht vergessen

Vor **jedem** Bildurteil die Quelle prüfen. Der Zuspieler stand versehentlich auf einem X-Schirm
von 1920x1080, während HDMI mit 1280x720 nur den linken oberen Ausschnitt zeigte; ein Teil der
vermeintlichen Projektorfehler war die Quelle selbst. Sauber ist:

```
xrandr --output eDP-1 --mode 1280x720 --output HDMI-2 --mode 1280x720 --same-as eDP-1
xrandr | grep -E "^Screen|connected"      # Screen muss exakt die Testaufloesung sein
```

## Rückfallpunkte

Kernel `tftp/h713-kernel-netboot.fit.GUT-56ef014a` (Serie 80, alle drei Punkte aus `doku/91`),
dazu `mainline/build/modroot.GUT-56ef014a`.
