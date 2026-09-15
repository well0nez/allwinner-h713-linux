# Integration der fünf neuen Patches (Hauptsitzung, 23:30-23:40)

Der Integrationsplan-Agent des Prüf-Workflows ist beim Zusammenfassen hängengeblieben. Die **fünf
Prüfberichte** lagen aber vollständig vor (im Journal des Laufs) und enthielten alles Nötige - ich habe die
Integration daraus selbst ausgeführt. Die zwei Konfliktberichte kamen nicht mehr zurück; ihre Fragen waren
durch die Einzelprüfungen bereits beantwortet.

## Was die Prüfung ergeben hat

| Patch | wendet an | Regelverstöße | Befunde „hoch" |
|---|---|---|---|
| 0091 (B, ARISC) | ja | **2** | **2** |
| 0092 (C, cpu_comm-API) | **nein** - Rebase nötig | 2 | 2 |
| 0093 (D, NV16-Plane) | ja | 0 | 1 |
| 0094 (E, V4L2) | ja | 0 | **2 Blocker** |
| 0095 (H, Gamma/CTM) | ja | 0 | 0 |

Alle Prüfer haben **handfest** getestet: frischer Tarball aus `build/cache/linux-6.18.38.tar.xz`, die
vollständige `series` mit `patch -s -p1` wie in `build/build.sh` Z. 143-155, dann der zu prüfende Patch.

## Die drei Eingriffe, die vor dem Bau nötig waren

### 1. `0094` - zwei echte Blocker eingearbeitet

Beide hätten den Treiber auf **jedem** Board bei **jedem** Boot scheitern lassen:

- `q->max_num_buffers = H713_HDMIRX_SLOTS` (= 3) lässt `vb2_core_queue_init()` immer scheitern; die Funktion
  weist jeden Wert unterhalb von `VB2_MAX_FRAME` ab. Ersetzt durch einen Kommentar - die Zahl der Puffer wird
  ohnehin in `queue_setup()`/`alloc()` auf die drei Slots festgelegt.
- `v4l2_event_queue()` lief auf ein noch **nicht registriertes** `video_device`: die Init-Sequenz scharft
  `SignalChange` und `HotPlugByPort`, lange bevor `video_register_device()` `vdev->fh_list`/`fh_lock`
  angelegt hat - und die EDID/HPD-Sequenz direkt danach provoziert genau diese zwei Ereignisse. Ergebnis wäre
  ein Oops im Probe gewesen. Jetzt Wächter `if (!video_is_registered(&rx->vdev)) return;`.
- Dazu: `-ENODEV` von `cpu_comm`/`arisc` wird nun wie `-EAGAIN` zu `-EPROBE_DEFER` (nichts ordnet die Probes
  der beiden Treiber gegeneinander - der Knoten hat kein Phandle auf `cpu_comm`).

Der Korrekturdiff stammt vom Prüfer (`/tmp/claude-1000/wf-integration/pruefer-E/fix-0094-clean.diff`) und ist
**in den Patch eingearbeitet**, nicht als eigener Patch angehängt: die betroffene Datei ist in 0094 neu, also
war der saubere Weg, den Dateiinhalt aus dem einen `@@ -0,0 +1,1716 @@`-Hunk zu lösen, den Diff darauf
anzuwenden und den Hunk neu zu erzeugen (jetzt 1736 Zeilen). Sicherung: `/tmp/claude-1000/fix0094/0094.orig`.

### 2. `0092` - rebasiert, weil es auf `0097` nicht mehr passt

`0092` entstand gegen den alten Baubaum, der die Handänderungen enthielt, die inzwischen als `0097` in der
Serie stehen. Der Prüfer hat nachgewiesen: **0092 bringt keinen 0097-Hunk doppelt mit** (meine Sorge aus der
Koordinationsnotiz bestätigt sich nicht) - aber sein Hunk 7 **löscht den Block, in den 0097 einsetzt**, und
scheitert deshalb. Übernommen wurde die rebasierte Fassung des Prüfers
(`/tmp/claude-1000/wf-integration/C-review/0092-rebased-on-0097.patch`, 8 Dateien wie das Original).
Sicherung des Originals: `/tmp/claude-1000/fix0094/0092.orig`.

### 3. Defconfig - zwei Zeilen, die kein Patch mitbringt

```
CONFIG_HY310_ARISC_HDMI=m   →   CONFIG_SUN50I_H713_ARISC=m
                          neu:  CONFIG_VIDEO_SUN50I_H713_HDMIRX=m
```

## Die neue `series` - Reihenfolge nach Abhängigkeit, nicht nach Nummer

71 Zeilen. `0090` ist **ersatzlos** gestrichen (0091 ersetzt es). Das Ende lautet:

```
0086-asoc-h713-fix-the-audio-clock.patch
0091-soc-sunxi-h713-arisc.patch
0096-arm64-dts-h713-add-the-tvcap-bringup-node.patch
0097-soc-sunxi-cpu-comm-fix-the-call-argument-abi-and-the-callwq-pointer.patch
0092-soc-sunxi-h713-cpu-comm-kernel-api.patch
0093-drm-h713-afbd-nv16-hdmi-ring.patch
0094-media-sun50i-h713-hdmirx.patch
0095-drm-h713-afbd-color-mgmt.patch
```

**Warum nicht numerisch:** `0092` muss hinter `0097` stehen (Hunk 7 gegen dessen Einsatzstelle), und `0094`
hinter `0091`, `0092` und `0093` (es bindet `h713-arisc.h` und `h713-cpu-comm.h` und setzt auf dem
dtsi-Stand auf). `series` wird von `build/build.sh` in Dateireihenfolge angewandt, Kommentarzeilen sind darin
**nicht** erlaubt (`build.sh` behandelt jede nichtleere Zeile als Dateinamen) - deshalb steht die Begründung
hier und nicht dort. Wer das aufräumen will, benennt `0092`→`0098`, `0093`→`0099`, `0094`→`0100`,
`0095`→`0101` um; heute Nacht wäre das nur Bewegung ohne Nutzen.

## Was NICHT eingearbeitet wurde und offen bleibt

- **`0091` (B): zwei Regelverstöße und ein funktionaler Blocker.** `arisc_wait_handler()` beruht laut Prüfer
  auf einer falschen Annahme über die Firmware und liefe am Gerät im zweiten Schritt der EDID-Sequenz in
  `-ETIMEDOUT`; dazu schreibt der Treiber R_PRCM-Bits (`0x07010110/114/118`) und R_CPUCFG (`0x07000400`) an
  der Takt-/Reset-Schnittstelle vorbei. **Das blockiert den Bau nicht** (der Treiber ist ein Modul und wird
  nicht automatisch geladen), wohl aber die Abnahme von Paket B. Gehört vor der B-Abnahme behoben.
- **`0093` (D): drei Minimalkorrekturen** vom Prüfer vorgeschlagen (Descriptor-Seite vor dem Beschreiben
  nullen, fehlende Vblank-Referenz laut melden statt still hinnehmen, das Flip-Zeigerpaar wirklich als Paar
  auf Zerrissenheit prüfen). Sinnvoll, aber nicht bau- oder bootkritisch.
- **`0093`s Abnahmevorschrift ist falsch herum:** sie veröffentlicht den Descriptor **nach** der EDID/HPD-
  Sequenz - genau das schaltet die Capture ab. Die Vorschrift muss den Freigabeschritt (Quellenwechsel oder
  HPD-Zyklus) enthalten, siehe `B2-quellenwechsel.md` und `M4-hpd-dauer.md`.

---

## Nachtrag 00:35 - der Integrationsplan des Workflows ist doch noch gekommen

Der Plan-Agent hat um 00:27 [`INTEGRATION.md`](INTEGRATION.md) geschrieben und die hier ausgeführte
Integration **unabhängig nachgemessen** (frischer Tarball, alle 71 Serienzeilen mit `patch -p1`):
71/71 sauber, kein `.rej`; `0090` raus; `0092` in der rebasierten Fassung; beide Defconfig-Zeilen da;
alle drei `0094`-Blocker behoben; der Scratch-Fix in `0091` drin. Es blockiert nichts den Bau.

Die zwei Konfliktagenten des Workflows sind in **allen sechs** Versuchen hängengeblieben (jeder legte
dafür einen vollständigen Kernelbaum an). Ihre beiden Fragen hat der Plan-Agent selbst beantwortet;
der Workflow endete mit 6 von 8 Agenten.

### Daraufhin noch erledigt

- **`0095` fehlte die `Signed-off-by:`-Zeile** - als einziger Patch der Nacht, Verstoß gegen Maßstab 3
  des Nachtplans. Ergänzt; Gegenprobe: `0091` - `0097` haben jetzt alle genau eine. Serie danach erneut
  geprüft: **71/71 sauber**.
- **`/lib/firmware/hy310-hdcp22.bin`** (912 B aus `analyse/hdcp-keys/hdcp22-key-912.bin`) aufs Board
  gelegt. Damit liegen alle drei Firmware-Dateien, die `0091` und `0094` erwarten, an ihrem Platz.

### Bewusst **nicht** mehr angefasst: der tote Modulparameter `callwq_kernel_cb`

Der Plan hat einen echten Regel-1-Fund: nach `0092` steuert der Schalter `callwq_kernel_cb` **nichts
mehr** - `0092`s Hunk 7 entfernt den ganzen Block, der ihn auswertete - , seine Beschreibung im
`MODULE_PARM_DESC` beschreibt also Verhalten, das der Code nicht hat. Ein Schalter, der nichts tut,
ist ein Quirk mit Ansage.

**Warum ich das um 00:35 nicht mehr geändert habe:** beide vorgeschlagenen Wege greifen ineinander.
`0092`s Hunk 7 löscht den Block **in der Form, die `0097` erzeugt**. Nimmt man den Deklarationsblock
aus `0097` heraus, referenziert `0097`s zweiter Hunk eine nicht mehr deklarierte Variable - die Serie
wäre an dieser Stelle nicht mehr für sich übersetzbar (schlecht fürs Bisektieren), und der saubere
Schnitt verlangt, `0092` mit zu rebasieren. Das ist eine zwanzigminütige Arbeit mit einem Bau und
einer Abnahme dahinter, und der Nutzen ist kosmetisch: der Parameter ist wirkungslos, nicht schädlich.

**Empfohlener Weg für den Morgen** (Variante (b) des Plans, der klarere Schnitt):
`0097` auf seine zwei bleibenden Korrekturen eindampfen - tgid-ABI und die RX-CALL-Druckoffsets - und
die beiden `cpu_comm_rpc.c`-Hunks `@@ -19 @@` und `@@ -1011 @@` ganz herausnehmen; anschließend `0092`
gegen den so entstandenen Stand neu erzeugen. `0097` ist dann reiner ABI-Fix, `0092` reiner
Mechanismuswechsel, und keiner der beiden trägt einen Testschalter. Der `memset(routine_info, 0, …)`
bleibt in `0097`: er ist billige Defensive und wird durch `0092` nicht gegenstandslos.
