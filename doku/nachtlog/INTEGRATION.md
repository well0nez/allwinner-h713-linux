# Integrationsplan der fünf neuen Patches

Zusammenführung der fünf Prüfberichte (B/0091, C/0092, D/0093, E/0094, H/0095) zu einer
Schrittfolge für die Hauptsitzung. Konfliktberichte lagen bei Planschluss keine vor.

Ich habe das Board nicht angefasst, `mainline/` nicht verändert, `series` nicht verändert und
`build/build.sh` nicht aufgerufen. Alles unten Behauptete ist in einem Wegwerfbaum gemessen:
`/tmp/claude-1000/wf-integration/plan/`.

---

## 0. Stand bei Planschluss - die Hauptsitzung war schneller als der Plan

Wichtig vorweg, sonst wird Erledigtes doppelt gemacht: die Hauptsitzung hat zwischen 23:28 und
00:07 den größten Teil dieser Integration **bereits ausgeführt** (siehe `INTEGRATION-hauptsitzung.md`
und `B-abnahme-board.md`). Der Auftragstext dieses Plans („series hat 67 Zeilen, 0090 muss raus,
0092 wendet nicht an") beschreibt den Stand von 22:35 und ist überholt.

**Nachgemessen, nicht geglaubt** (frischer Tarball aus `build/cache/linux-6.18.38.tar.xz`, dann alle
71 Zeilen der heutigen `series` mit `patch -p1`, Verfahren wie `build/build.sh` Z. 148-155):

| Prüfung | Ergebnis |
|---|---|
| Serie anwendbar | **71/71, kein FAILED, kein einziges `.rej`** |
| Fuzz | nur `0001` (Hunk 1+2, Fuzz 1 - Altbestand) und `0095` (5 von 9 Hunks, Fuzz 1-2) |
| `0092` gegen `0097` | **wendet an** - die Datei trägt jetzt sha256 `8bdd6528…`, also die rebasierte Fassung des C-Prüfers |
| `0090` in `series` | **nicht mehr enthalten** (`grep` leer), Datei liegt nur noch als Archiv im Verzeichnis |
| defconfig Z. 197-199 | `CONFIG_HY310_CPU_COMM=m`, `CONFIG_SUN50I_H713_ARISC=m`, `CONFIG_VIDEO_SUN50I_H713_HDMIRX=m` - **beide neuen Zeilen da**, das tote `CONFIG_HY310_ARISC_HDMI` ist weg |
| `0094` Blocker 1 (`max_num_buffers`) | **behoben** - Zeile ist raus, ersetzt durch den begründenden Kommentar |
| `0094` Blocker 2 (`v4l2_event_queue` vor `register`) | **behoben** - `if (!video_is_registered(&rx->vdev)) return;` steht in Z. 577 |
| `0094` `-ENODEV → -EPROBE_DEFER` | **behoben**, an beiden Stellen (Z. 1626 und Z. 1639) |
| `0091` Befund „falscher Scratch-Erwartungswert" | **behoben** - `arisc_expected_scratch()` mit Fallunterscheidung nach `sub_cmd_hi` ist im Treiber, und am Gerät bestätigt (`B-abnahme-board.md`: `hi == 1` kopiert **65** statt 64 Bytes, der Prüfer lag dort daneben, das Gerät hat korrigiert) |

**Damit blockiert derzeit nichts den Bau.** Alles, was unten noch steht, ist entweder Formsache,
Nacharbeit an einem Patch oder eine Entscheidung, die vor der jeweiligen **Board-Abnahme** fällt.

Ein Nebenergebnis, das die Fuzz-Sorge aus den Berichten D, E und H schließt: ich habe den
`0095`-Merge zeilengenau nachgerechnet. Der Patch fügt im `.c`-Teil 326 Zeilen ein und löscht eine;
der Unterschied zwischen dem Baum ohne und mit `0095` ist **genau 326 hinzugefügte und 1 gelöschte
Zeile**. Der Fuzz hat also nichts verschluckt. Zusätzlich stichprobenweise nachgesehen: Includes
stehen alphabetisch richtig zwischen `iopoll.h` und `mm.h` bzw. `math64.h`, die drei Gammafelder
liegen innerhalb von `struct h713_afbd`, die `probe`-Zeilen sitzen vor `drm_mode_config_reset()`.
`patch -s -p1` in `build.sh` läuft mit Vorgabe-Fuzz 2 - die Serie ist also **grün, aber spröde**
(siehe 2.3).

---

## 1. Die `series` ab Zeile 60 bis zum Ende

So steht sie heute, und so ist sie oben gemessen. **Keine Änderung nötig** - die Liste dient der
Kontrolle (`sed -n '60,71p' mainline/patches/kernel/series`):

```
0082-arm64-dts-h713-enable-the-internal-audio-codec.patch
0083-arm64-dts-h713-route-lineout-to-the-speaker.patch
0084-asoc-sun4i-codec-add-the-h713-variant.patch
0085-asoc-h713-drive-the-speaker-from-the-hp-amp.patch
0086-asoc-h713-fix-the-audio-clock.patch
0091-soc-sunxi-h713-arisc.patch
0096-arm64-dts-h713-add-the-tvcap-bringup-node.patch
0097-soc-sunxi-cpu-comm-fix-the-call-argument-abi-and-the-callwq-pointer.patch
0092-soc-sunxi-h713-cpu-comm-kernel-api.patch
0093-drm-h713-afbd-nv16-hdmi-ring.patch
0094-media-sun50i-h713-hdmirx.patch
0095-drm-h713-afbd-color-mgmt.patch
```

**Warum diese und keine numerische Reihenfolge** (alle vier Bedingungen gemessen, nicht vermutet):

1. `0090` fällt ersatzlos weg. Gegenprobe des B-Prüfers: mit `0090` **und** `0091` in der Serie
   scheitern genau die zwei Ein-Zeilen-Hunks in `drivers/soc/sunxi/Kconfig` und `.../Makefile`.
   `0090` legte nur neue Dateien an, verschwindet also rückstandsfrei; `0091` bringt alles davon
   plus API-Header plus DT-Knoten `arisc@100000`.
2. `0092` **muss hinter `0097`**: sein Hunk 7 löscht den Block, in den `0097`s Hunk 4 einsetzt.
   Die umgekehrte Reihenfolge hilft nicht - dann scheitert `0097`. Es ging nur über den Rebase.
3. `0094` **muss hinter `0091` und `0092`**: es bindet `include/linux/soc/sunxi/h713-arisc.h` und
   `…/h713-cpu-comm.h` ein und hängt in Kconfig an `SUN50I_H713_ARISC` und `HY310_CPU_COMM`.
4. `0095` **muss hinter `0093`**: umgekehrt scheitert `0093` hart (3 von 20 Hunks FAILED in
   `sun50i-h713-afbd.c`). Im dtsi kollidieren die beiden dagegen nicht - der Knoten
   `display@5600000` trägt jetzt sauber beides:
   `reg` vier Fenster inkl. `gamma` (H) und `memory-region = <&mips_framebuf>, <&viddec_info>` (D).

`0091` gegenüber `0093/0094/0095` ist unabhängig (disjunkte Dateien, dtsi an anderer Stelle);
`0092` ebenso (nur `drivers/soc/sunxi/cpu_comm/*` und ein Header).

Wenn jemand die Serie später numerisch sortieren will, ist der Weg `0092`→`0098`, `0093`→`0099`,
`0094`→`0100`, `0095`→`0101`. Heute Nacht ist das Bewegung ohne Nutzen und kostet einen weiteren
grünen Bau.

---

## 2. Änderungen außerhalb der `series`

### 2.1 Board-defconfig - **erledigt, bitte nur gegenprüfen**

`mainline/patches/kernel/board/hy200_qz713df_a1_defconfig`, Z. 197-199 lauten jetzt:

```
CONFIG_HY310_CPU_COMM=m
CONFIG_SUN50I_H713_ARISC=m
CONFIG_VIDEO_SUN50I_H713_HDMIRX=m
```

Das war der klassische Fall aus Nachtplan Abschnitt 0a: `build.sh` Z. 156 **kopiert** diese Datei,
kein Patch fasst sie an, das neue Kconfig-Symbol hat bewusst kein `default` - ohne diese Zeilen
wäre die Serie grün durchgelaufen und die zwei Module wären schlicht nicht entstanden.
`=m` ist zwingend: `HY310_CPU_COMM` ist `=m`, `SUN50I_H713_ARISC` ist als Modul entworfen (das
Abbild kommt aus `/lib/firmware`), also kann kein davon abhängiges Symbol `=y` sein.

**Gegenprobe nach dem Bau** (der Bau meldet den Unterschied nicht):

```
ls mainline/build/out/modules/**/sun50i-h713-arisc.ko
ls mainline/build/out/modules/**/sun50i-h713-hdmirx.ko
ls mainline/build/out/modules/**/hy310-cpu-comm.ko
```

Weitere Fragmente sind nicht betroffen: `netboot.config`, `builtin-drivers.config`, `iommu.config`
und `kasan.config` enthalten keines der Symbole. `CONFIG_DRM_SUN50I_H713_AFBD=m` (Z. 131) und
`CONFIG_DEBUG_FS=y` stehen bereits - `0093` und `0095` brauchen keine Zeile.

### 2.2 Korrekturen, die in die Patchdateien eingearbeitet wurden - **erledigt**

| Patch | Eingriff | Grund |
|---|---|---|
| `0092` | vollständig rebasiert (Hunk 7 gegen den `0097`-Stand neu geschnitten) | sonst `Hunk #7 FAILED at 1041`, Serie rot |
| `0094` | `q->max_num_buffers` gestrichen | `vb2_core_queue_init()` weist jeden Wert `< VB2_MAX_FRAME` (=32) per `WARN_ON` ab → `-EINVAL` → Probe scheitert bei **jedem** Boot; für den Compile-Check unsichtbar |
| `0094` | `if (!video_is_registered(&rx->vdev)) return;` in `h713_hdmirx_src_change()` | die Callbacks werden ~10 s vor `video_register_device()` scharf gemacht und die EDID/HPD-Sequenz löst in genau diesem Fenster beide Ereignisse aus → `list_for_each_entry` über `fh_list.next == NULL` → Oops |
| `0094` | `-ENODEV` wird wie `-EAGAIN` zu `-EPROBE_DEFER` | nichts ordnet die drei Probes: der DT-Knoten `hdmi-rx@5600320` hat kein Phandle auf `cpu-comm@3003000` oder `arisc@100000`, `fw_devlink` kann also nichts erzwingen |
| `0091` | `arisc_expected_scratch()` statt „Handler kopiert immer 65 Byte" | am Gerät bestätigt und in einem Punkt korrigiert (`hi == 1` kopiert 65) |

### 2.3 Nacharbeit an den Patchdateien - **offen, nicht bau-blockierend**

1. **`0095` fehlt die `Signed-off-by:`-Zeile** vor dem `---`-Trenner (heute Z. 55). `0049`, `0093`,
   `0096`, `0097` haben sie. Damit ist `form_ok` für `0095` als einzigem Patch der Nacht **nein**,
   Maßstab 3 des Nachtplans ist verletzt. Eine Zeile.
2. **`0095` sollte gegen den `0093`-Stand neu erzeugt werden.** Es geht heute nur durch, weil
   `patch` mit Vorgabe-Fuzz 2 läuft; fünf Hunks landen mit Fuzz 1-2. Das Ergebnis ist nachweislich
   korrekt (oben nachgerechnet), aber jede künftige Änderung an `0093` kann `0095` still
   verschieben. Zusammen mit Punkt 1 in einem Zug erledigen: Kopf ergänzen, im gepatchten Baum
   `diff -ruN` neu ziehen.
3. **`0093` trägt als einziger Patch keine Zeitstempel** in den `--- a/` / `+++ b/`-Zeilen. Rein
   kosmetisch, `patch(1)` stört es nicht. Beim nächsten Anfassen mit `diff -ruN` erzeugen.

### 2.4 Hunk-Streichungen aus den Prüfberichten

Es gibt genau **eine ausgeführte** und **eine vorgeschlagene**:

- **Ausgeführt (gehört so protokolliert):** `0092`s Hunk 7 macht `0097`s `cpu_comm_rpc.c`-Hunk `@@ -1011,6 +1043,19 @@` rückgängig -
  der `pr_warn`-Druck und der Riegel `if (!callwq_kernel_cb || cpu_comm_is_mips_va(…)) callback = NULL;`
  verschwinden mit dem ganzen Block. Das ist **inhaltlich richtig** (der Zeigersprung ist danach
  weg, nicht nur abgeschaltet - Verhalten identisch mit dem Modul, das am 06.09. lief), aber es ist
  eine **Rücknahme**, kein additiver Merge. Sie steht damit hier im Nachtlog und ist nicht mehr still.
- **Vorgeschlagen, noch offen:** `0097`s `cpu_comm_rpc.c`-Hunk `@@ -19,6 +19,20 @@` (Include `moduleparam.h`, `static bool
  callwq_kernel_cb`, `module_param`, `MODULE_PARM_DESC`) sollte mit weg. Nachgeprüft im gepatchten
  Baum: der Parameter steht weiterhin in `cpu_comm_rpc.c` Z. 33-35 und erscheint als
  `/sys/module/hy310_cpu_comm/parameters/callwq_kernel_cb` - **er steuert nach `0092` aber nichts
  mehr**, und seine `MODULE_PARM_DESC` beschreibt Verhalten, das der Code nicht hat. Ein Schalter,
  der nichts tut, ist ein Quirk mit Ansage (Regel 1). Zwei saubere Wege:
  (a) den Block als weiteren Hunk in `0092` mit entfernen, oder
  (b) `0097` auf seine zwei bleibenden Fixes eindampfen (tgid-ABI + RX-CALL-Druck) und die beiden
  `rpc.c`-Hunks `@@ -19 @@` und `@@ -1011 @@` ganz herausnehmen. (b) ist der klarere Schnitt: `0097` = reiner ABI-Fix, `0092` = Mechanismus-
  wechsel, keiner der beiden trägt Testschalter. Beides erzwingt einen neuen Bau - deshalb: **erst
  nach der C-Abnahme**, nicht mittendrin.
  Der `memset(routine_info, 0, …)` aus `0097` bleibt in jedem Fall: er ist billige Defensive und
  wird durch `0092` nicht gegenstandslos (Offsets 2 und 40 werden weiterhin gelesen).

### 2.5 Dateien, die aufs Board müssen (nicht Teil eines Patches)

Aus `B-abnahme-board.md` bereits bezahlt gelernt - der erste Fehlschlag war genau das:

- `/lib/firmware/h713-arisc.bin` ← `analyse/arisc/scp.bin`
- `/lib/firmware/hy310-edid.bin` ← `analyse/arisc/hy310-edid.bin` (**512 Byte**; die 256-Byte-Fassung
  wird vom Treiber mit Warnung verworfen, und `arisc_hdmi_edid_init(0, NULL, 0)` liefert dann
  `-ENOENT` → **`0094`s Probe scheitert endgültig**)
- `/lib/firmware/hy310-hdcp22.bin` (912 B) ← `analyse/hdcp-keys/hdcp22-key-912.bin`; fehlt sie, wird
  der Schritt nur übersprungen, das ist kein Abbruch
- die drei `.ko` ins NFS-Root plus `depmod -a`
- `prep_after_boot.sh` Z. 11 (`arisc_load.py load …`) und Z. 19 (altes `/root/hy310-arisc-hdmi.ko`)
  müssen für jeden Abnahmelauf herausgeschnitten bleiben - sonst lädt der Blob zweimal und eine
  zweite Quittung geht raus.

---

## 3. Bau- und Abnahmereihenfolge

Ein Bau, dann fünf Abnahmen in dieser Folge. Die Reihenfolge ist nicht beliebig: **B trägt C, C
trägt E, D muss vor E scharf sein, H ist unabhängig und deshalb der billigste Puffer am Ende.**

### Schritt 0 - Bau

```
build/build.sh   (Hauptsitzung)
```

Erwartet: `applied 71 series patches + arm64 defconfig`, danach ein grüner Kernel. Fuzz-Meldungen
erwartet: `0001` (Altbestand) und `0095` (5 Hunks, Fuzz 1-2). **Kein `.rej`, kein FAILED.**
Direkt danach die drei `.ko` aus 2.1 gegenprüfen - der Bau meldet ein fehlendes Modul nicht.

### Schritt 1 - Paket B (ARISC), läuft bereits

Erwartet: `startup_notify: acked`, `arisc: running`, `edid_firmware: hy310-edid.bin loaded`, und
`echo edid > /sys/kernel/debug/h713-arisc/cmd` führt die Sequenz durch. **Stand 00:07: bis
einschließlich der acht `UpdateEDID`-Fragmente grün, `CheckEDIDUpdateStatus` rot (`-EPROTO`,
Antwort `a5 00 01 08 …`).** Nächster Schritt dort ist der Rahmenversatz (Kopf `a5 .. 01 ..` vs.
Nutzlast ab Wort 2) und die Frage, ob die Firmware das EDID überhaupt übernommen hat -
`[0x1723E]`/`[0x1723F]` lesen. Nicht Gegenstand dieses Plans.

### Schritt 2 - Paket C (cpu_comm-Kernel-API)

`modprobe hy310-cpu-comm`, debugfs prüfen, `watch` beobachten.
Erwartet: die drei debugfs-Dateien da; `watch` druckt bei einem SignalChange
`0x3e7fbc46      0 MipsHalCallback_SignalChange`; `/dev/cpu_comm` bekommt dasselbe Ereignis
(Userspace-Zustellung läuft **vor** dem Kernel-Handler und bleibt erhalten).

**Vor dem Slot die Abnahmevorschrift korrigieren** (`C-cpu-comm.md` §6, Schritte 4 und 6): dort ist
`error -110` als Durchfallkriterium ausgewiesen. Nach der Board-Datenlage ist das falsch kalibriert
- in `analyse/hdmi-seq/kmsg-udp-run*.txt` kamen **45 von 69** `THal_Vp_GetSource`- und **7 von 21**
`THal_Vp_SetSource`-Aufrufen ohne RETURN zurück, und Nachtplan Anhang A.5 nennt genau das
ausdrücklich „normal, kein Fehler" (Nullwechsel). Bestehenskriterium muss sein: kein Absturz,
Kernel-Callback erreicht, `/dev/cpu_comm` bekommt das Ereignis, `elog` zeigt `SetActivePort`.
Der Rückgabewert von Schritt 4/6 wird **protokolliert, nicht bewertet.**

### Schritt 3 - Paket D (NV16-Plane) **vor** Paket E

Erwartet: `hdmi_plane_test`, die Wand zeigt das HDMI-Bild, die Uhr des Zuspielers **läuft**.

**Reihenfolge am Gerät ist hier das Entscheidende** (Nachtplan Stufe 7a, Korrektur 07.09. 22:35 -
`D-plane.md` §5 ist um 22:21 geschrieben und kennt sie noch nicht): der Descriptor-Schreibvorgang
setzt MemoryAgent `+8` auf 1 und löscht damit die INCAP-Freigabe `0x06940928/0968` Bit 31. Wer erst
`arisc_edid_init` fährt und dann die Plane einschaltet, sieht danach ein **Standbild** - `+0x104`
zählt weiter 60/s, geschrieben wird nichts. Zwei zulässige Wege, beide Stock-Befehle:

- **(a) empfohlen:** beim ersten Enable eines Boots die Plane **vor** der EDID/HPD-Sequenz
  aktivieren; deren `PullHotPlug UP` macht die Capture ohnehin wieder scharf.
- **(b)** unmittelbar nach dem ersten Enable einen HPD-Zyklus fahren:
  `echo "hpd 0 down" > /sys/kernel/debug/h713-arisc/cmd`, 8-10 s warten, `echo "hpd 0 up" > …`.
  Der Parser von `0091` kann `hpd <port> up|down|reset` - kein Poke nötig.

Ab dem zweiten Enable im selben Boot ist nichts mehr nötig; der Treiber veröffentlicht den
Descriptor nicht erneut. **Und:** die Zeile „Bild steht (Uhr friert) → Dirty-Latch reicht pro Vsync
nicht" in `D-plane.md`s Fehlertabelle und in `doku/86` §8 gehört korrigiert - erste Verdächtige
sind die Descriptor-bedingte Capture-Abschaltung und die fehlende Vblank-Referenz, erst danach der
Latch.

### Schritt 4 - Paket E (V4L2)

Erwartet: `/dev/videoN` erscheint, `v4l2-ctl --all` zeigt NV16 1920x1080, Streaming liefert
Rahmen aus den drei Slots.
Erwartet **werden darf auch** ein `-EPROBE_DEFER`-Durchlauf beim Modul-Laden (nichts ordnet die
Probes). Was **nicht** kommen darf: `Schritt 0 THal_Vp_Init … fehlgeschlagen: -19` als Endzustand.

Zu klären, **bevor** der Slot läuft, siehe 4.B Punkt 1: `VIDIOC_S_INPUT` kann im gemessenen
Normalfall `-ETIMEDOUT` liefern.

### Schritt 5 - Paket H (Gamma/CTM)

Erwartet: `gamma_test` setzt GAMMA_LUT, das Bild ändert die Kurve; ein CTM mit Nebendiagonale
ungleich 0 wird mit `-EINVAL` und einer `drm_dbg_kms`-Begründung abgewiesen (kein stilles
Verwerfen). `gamma_test` macht keinen Modeset, die zwei Doppelschreib-Befunde (4.C) greifen dabei
nicht.

---

## 4. Fachliche Befunde, nach Schwere

### A) Vor dem Bau zu beheben

**Keine.** Alle vier Blocker der Prüfung (`0092`-Rebase, `0094`×2, `0091`-Scratch) sind eingearbeitet;
die Serie wendet 71/71 sauber an, das defconfig trägt beide Symbole. Das ist gemessen, nicht
angenommen (Abschnitt 0).

### B) Vor der jeweiligen Board-Abnahme zu entscheiden oder zu beheben

1. **hoch - `VIDIOC_S_INPUT` kann im Normalfall scheitern (C ↔ E).** `h713_hdmirx_set_source()`
   ruft `cpu_comm_call(…, NULL, 0, 0)`; `cpu_comm_call()` setzt intern `strict = true`, ein
   fehlendes RETURN wird also zu `-ETIMEDOUT` bzw. `-ENODATA` - und „kein RETURN" ist für
   `THal_Vp_SetSource` **gemessener Normalzustand** (7 von 21 Läufen). Der Fehler reicht bis
   `VIDIOC_S_INPUT` durch, also genau in den Weg, den Anhang A.4 als den normalen Umschaltweg
   beschreibt. Die Strenge darf **nicht** gestrichen werden - sie deckt echte Blindheit auf
   (`doku/67` Z. 378: kein RETURN heißt, die Routine lief nie). Entscheidung nötig, siehe 5.1.
2. **hoch - `0091`, zwei Regelverstöße, im Baum weiterhin offen** (nachgesehen, nicht aus dem
   Bericht übernommen): der Treiber mappt sich das Fenster `cpus-clk` = `0x07010110 0xc` selbst
   (`h713_arisc_map(pdev, "cpus-clk", …)`, Z. 1289) und setzt dort drei Gatterbits, obwohl das
   mitten in der Registerdatei des `r_ccu`-Knotens liegt; und er schreibt R_CPUCFG `0x07000400`
   Bit 0, ohne `CLK_BUS_R_CPUCFG`/`RST_BUS_R_CPUCFG` anzufordern - er verlässt sich also darauf,
   dass der Bootloader das Busgate offen gelassen hat. Für Taktgatter ist die Standardschnittstelle
   der CCU-Treiber. **Serienpatch `0027` macht genau das für R_PWM schon vor.** Regel 1 lässt hier
   keinen Ermessensspielraum, der Umfang aber schon (siehe 5.2).
3. **mittel - `0091`: `PullHotPlug UP` meldet Erfolg ohne Beobachtung.** In `arisc_hpd_locked()`
   steht heute `if (cur == 0 && (action != RESET || peak >= HPD_RESET_PEAK_MIN)) return 0;` - für
   UP wird also **kein** Peak verlangt, und der Ausgangswert des Zählers ist ebenfalls 0. Der erste
   Lesezugriff liegt in derselben Größenordnung wie der 0→1→0-Durchlauf der Firmware-Hauptschleife.
   Fix: für UP `peak >= 1` verlangen (drei Zeilen). Ohne das ist der HPD-Zyklus aus Schritt 3(b)
   nicht beweisbar gelaufen - und genau darauf stützt sich die D-Abnahme.
4. **mittel - `0093`: Descriptor-Seite wird nicht genullt.** `memcpy(h->video_info, rec, sizeof(rec))`
   schreibt 144 Byte in eine `no-map`-Reservierung, die Linux nie nullt; der Vendor-`decd` nullt
   vorher eine ganze PAGE und kopiert dann 0x104 Byte. In Byte 144…8191 stehen also Reste. Kein
   Rückschritt gegenüber `viddec_descriptor.py` (das schreibt auch nur 144 B), aber eine unnötige
   Unbekannte im Hardwarelauf. `memset(h->video_info, 0, min(size, PAGE_SIZE))` vor dem `memcpy`.
5. **mittel - `0093`: Rückgabewert von `drm_crtc_vblank_get()` verworfen** (Z. 655-657, kein
   `else`). In einem Commit, der CRTC und Plane zusammen einschaltet, läuft `commit_planes` **vor**
   `commit_modeset_enables`; `drm_crtc_vblank_off()` hält derweil eine Referenz und setzt
   `inmodeset=1`, `drm_crtc_vblank_get()` liefert dort `-EINVAL`. `ring_follow` steht dann auf true
   ohne Referenz, und niemand merkt es. Für `hdmi_plane_test` unkritisch (kein Modeset), für
   `modetest -s` und jeden echten Client nicht. Ein `drm_warn` genügt für heute Nacht.

### C) Offene Punkte fürs Nachtlog / die Pflichtliste (`J-pflichtliste.md`)

1. **`0097`s toter Modulparameter `callwq_kernel_cb`** - siehe 2.4. Regel-1-Punkt, aber er kostet
   einen Bau; deshalb nach der C-Abnahme.
2. **Der 100-ms-Semaphor-Bypass in `cpu_comm_proto.c` Z. 297-304** (`„bypass after 100ms"`, `ret = 0`)
   ist „Timeout als Heilmittel" in Reinform. Er kommt aus `0014`, nicht aus `0092` - aber `0092`
   **zementiert** ihn: mit der neuen `cpu_comm_call_mutex` gibt es keine zwei Aufrufer mehr, die ihn
   auslösen, also fällt er nicht mehr auf. Entweder Stock-Beleg nachreichen, dass Stock den
   Sende-Semaphor ebenso umgeht, oder den Fehlschlag als echten Fehler nach oben geben.
3. **`0092`: `IOCTL_CALL` nimmt die Mutex nicht unterbrechbar** (`mutex_lock`, `cpu_comm_dev.c`
   Z. 203). Haltedauer = volle Aufrufdauer, Obergrenze für `timeout_ms` gibt es im API-Vertrag
   keine → ein Userspace-Prozess kann unbegrenzt im D-State hängen und ist nicht per Strg-C
   abbrechbar. `mutex_lock_interruptible()` + `-ERESTARTSYS`.
4. **`0092`: `-ENODATA` fehlt in der Rückgabeliste des öffentlichen Headers**
   (`h713-cpu-comm.h` Z. 117-120 nennt `-ETIMEDOUT/-ENODEV/-EAGAIN/-EBUSY/-EINVAL`). Die interne
   Deklaration nennt es korrekt. `0094` und Paket F schreiben sonst Fehlerbehandlung gegen eine
   unvollständige Liste.
5. **`0092`: `wait_ret == -EINVAL` (gar kein Wait-Semaphor) wird als `-ETIMEDOUT` gemeldet**
   (`cpu_comm_rpc.c` Z. 780-782, Text „wait timed out"). Zwei verschiedene Befunde, eine Diagnose -
   genau die Verwechslung, die `0092` sonst beseitigt.
6. **`0093`: das Flip-Zeigerpaar wird nur halb auf Zerrissenheit geprüft.** `h713_afbd_read_ring()`
   liest Y zweimal um C herum; schreibt die Firmware erst C und dann Y, besteht ein Y_alt/C_neu-Paar
   die Prüfung → ein Einzelbild mit Chroma aus dem Nachbarslot. C ebenfalls zweimal lesen.
7. **`0093`: stiller Ausstieg im idempotenten Zweig** (`if (!memcmp(...)) { published = true; return; }`,
   Z. 324-327, ohne Logzeile). Nach einem **warmen** Neustart bleibt DRAM erhalten, die MIPS startet
   aber in Zustand 0 - dann schreibt der Treiber nichts, protokolliert nichts, und es gibt kein Bild
   ohne Spur. Ein `drm_dbg_kms` trennt „schon veröffentlicht" von „stiller Ausfall". (Board-Regel
   bleibt: Kaltstart ist der Normalfall.)
8. **`0093`: `atomic_check` überspringt im Ring-Betrieb die Adressprüfung**, `atomic_update` fällt
   bei nicht lesbarem Ring aber stillschweigend auf den (uninitialisierten) Dummy-Framebuffer zurück.
9. **`0094`: alle Firmware-Rückgabewerte werden verworfen** (`cpu_comm_call(…, NULL, 0, …)` an beiden
   Stellen). Ausgerechnet `SetHDCP22Key`, von dem `hdmi_seq.py` Z. 771-777 ausdrücklich sagt, dass
   er scheitern kann, fällt damit stumm durch. `u32 res[2]` mitgeben und mindestens für
   `THal_Vp_Init` und `SetHDCP22Key` protokollieren.
10. **`0094`: Slot-Quelle ist ein freilaufender 120-Hz-`hrtimer`**, nicht der AFBD-Vsync, den
    Nachtplan §3 E nennt. **Kein Regel-1-Verstoß** - `doku/84` Z. 18/23 belegt, dass es auf dem ARM
    kein Capture-Ereignis gibt und Stock auch keines hat; die Abstraktion
    `struct h713_hdmirx_slot_source` ist vorhanden. Aber: `0093` exportiert seinen Vsync nicht
    (`grep EXPORT_SYMBOL` in `0093`: null Treffer), E **kann** ihn heute Nacht gar nicht abonnieren.
    Sobald D einen Notifier exportiert, zweite Quelle einhängen und den Timer entfernen. Beim
    Abnahmelauf die debugfs-Zähler `skipped`/`unchanged`/`torn` mitschreiben - dafür sind sie da.
    Nebeneffekt heute: D und E lesen `0x05600320/324` unabhängig voneinander (bewusst, D mappt das
    Fenster ohne die Region zu beanspruchen).
11. **`0094`: `cap->driver` wird abgeschnitten** (`"sun50i-h713-hdmirx"` = 18 Zeichen in `__u8[16]`)
    und `cap->bus_info` bleibt leer - beides moniert `v4l2-compliance`. Nachgesehen: im Baum steht
    weiterhin nur `strscpy(cap->driver, H713_HDMIRX_NAME, …)`, kein `bus_info`.
12. **`0094`: Kconfig wählt `VIDEOBUF2_V4L2` nicht selbst** (nur `_CORE` und `_MEMOPS`); es kommt
    heute nur über den Umweg `VIDEO_DEV … select VIDEOBUF2_V4L2 if VIDEOBUF2_CORE`.
13. **`0094`: die Shmem-Größenprüfung deckt den `Vp_Init`-Stagingpuffer nicht ab**
    (`if (rx->shm_size < H713_SHM_VP_INIT)` - nur der Anfang des Puffers muss in die Region passen,
    nicht seine 55296 Byte). Heute harmlos: `cpu_comm_reserved` hat 1 MiB Luft.
14. **`0094`: `H713_CALL_SLOW_MS = 2000` ist nicht belegt** - im Referenzskript gibt es keine
    entsprechende Größe. Kein Regel-1-Verstoß (der Wert ist ein Fehlerdetektor, es wird nichts
    wiederholt), aber eine geratene Zahl; beim ersten Board-Lauf messen.
15. **`0094`: `VIDIOC_S_EDID` blockiert `vdev->lock` > 10 s** (`msleep(HPD_DOWN_MS)` im ioctl-Pfad);
    `vdev.lock == q->lock`, also stehen DQBUF/STREAMOFF/mmap währenddessen. Nur dokumentieren, damit
    Paket F das nicht als Hänger missversteht.
16. **`0095`: `crtc->state->color_mgmt_changed` ist klebrig.** Es wird nur beim Duplizieren des
    CRTC-Zustands zurückgesetzt; ein Commit mit Plane **ohne** CRTC dupliziert ihn nicht, das Flag
    steht dann seit dem letzten Farb-Commit auf true → die elfschrittige Sequenz mit bis zu 40 ms
    Warten und 1536 MMIO-Schreibvorgängen läuft erneut. Heute nicht auslösbar (`drm_gem_fb_funcs`
    hat kein `.dirty`, DIRTYFB gibt `-ENOSYS`), aber eine gestellte Falle für Paket F: sobald
    `hy310-tv` die Video-Plane ohne CRTC flippt, läuft das 60×/s im `commit_tail`. Fix: den **neuen**
    CRTC-Zustand aus `old_state->state` holen statt das klebrige Flag zu lesen.
17. **`0095`: doppelter Schreibvorgang**, wenn ein Commit den CRTC einschaltet **und** die Farbe
    ändert (`pipe_update` läuft vor `pipe_enable`, beide sehen dasselbe Flag). Kein falsches Bild,
    aber die Sequenz, die exakt stock sein soll, läuft zweimal.
18. **`0095`: stiller Ausstieg im Commit-Pfad** (`if (h713_afbd_ctm_gains(…)) return;`, Z. 988-990).
    Unerreichbar heute, aber im Fehlerfall fällt **der ganze** Farbschreibvorgang inklusive
    GAMMA_LUT aus, ohne eine Zeile Log - genau das Bild „gesetzt, aber nichts passiert". `WARN_ON`.
19. **`0095`: Belegweiche bei Bit 22.** Patch und `doku/87` erklären `CHAN_LATCH` für selbstlöschend;
    die Quelle (`hy310-pqd/BACKGROUND.md` §5.2) sagt das nur für Bit 23. Ohne Wirkung aufs Verhalten
- aber Regel 1 verlangt Beleg: nachreichen oder den Zusatz streichen.
20. **Doku-Korrekturen:** (a) `D-plane.md` §3 begründet das Verkleinern von `decd_reserved` damit,
    `dec@5600000` sei der einzige Nutzer - `av1-decoder@1c0d000` zeigt ebenfalls auf `decd_reserved`
    und steht auf `status = "okay"` (praktisch harmlos, kein Treiber bindet `allwinner,sunxi-google-ve`).
    (b) Nachtplan A.5 widerspricht sich bei `0x48/0x4C` („Stock-Werte (…0780 Höhe) gesetzt" →
    „Firmware-Werte lassen: 0x04380780"); `doku/76` §11.1 (19:40) ist gegenüber §13 (21:10) überholt,
    der Patch folgt korrekt der Messung. (c) `H-gamma.md`s Abnahmevorschrift Punkt 0 trägt `0095`
    per `sed` an einem `0090`-Anker in die `series` ein - den es nicht mehr gibt, und `sed` meldet
    nichts, wenn das Muster nicht trifft. Ist erledigt, aber die Zeile gehört korrigiert, bevor sie
    jemand kopiert. (d) `0091`s `PARA_POOL_PHYS`-Kommentar formuliert als Befund, was
    `arisc_load.py` Z. 145-146 ausdrücklich als ANNAHME markiert (die Werte sind byteidentisch mit
    dem, was `prep_after_boot.sh` erprobt fährt).

---

## 5. Was ich **nicht** entschieden habe, und warum

1. **Ob `VIDIOC_S_INPUT` auf `-ETIMEDOUT` hart scheitern soll (4.B Punkt 1).** Das ist keine
   Geschmacksfrage und auch nicht offline zu klären: es hängt daran, **welche** der 24 Routinen der
   Bring-up-Sequenz überhaupt antworten. Bekannt ist nur die Statistik für zwei davon
   (`GetSource` 24×RETURN / 45×keins, `SetSource` 14/7) und dass beide Ursachen - Nullwechsel
   (Anhang A.5, „normal") und unbekannter Kanaltabellen-Schlüssel (`doku/67` Z. 378, „lief nie") -
   **dasselbe** Symptom erzeugen. Der saubere Weg ist Messung statt Politik: einen Board-Slot dafür
   verwenden, die Antwort-Matrix der 24 Routinen einmal aufzunehmen
   (`dmesg | grep 'null return'` während Phase 2+3), sie in `doku/83` als Tabelle festzuhalten und
   `strict` dort anzuwenden, wo ein RETURN belegt ist. Bis dahin: Rückgabewert protokollieren,
   nicht bewerten.
2. **Ob `0091`s zwei Regelverstöße heute Nacht behoben werden (4.B Punkt 2).** Dass sie Verstöße
   sind, ist eindeutig, und der saubere Weg ist bekannt und in der Serie vorgezeichnet (`0027`).
   Was ich nicht entscheiden kann, ist der **Preis**: die drei Gatter müssen in
   `drivers/clk/sunxi-ng/ccu-sun20i-d1-r.c` aufgenommen werden, das ändert den CCU-Treiber, verwirft
   das `cpus-clk`-Fenster und den R_CPUCFG-Direktzugriff - also genau den Pfad, der gerade am Gerät
   in Abnahme ist und dort zum ersten Mal funktioniert. Ein Umbau **während** einer laufenden
   Abnahme wirft die bisherigen Messungen weg. Meine Empfehlung ohne Entscheidungsbefugnis: erst
   Paket B zu Ende abnehmen (`CheckEDIDUpdateStatus` klären), dann in einem eigenen Patch
   `009x-clk-sunxi-ng-d1-r-add-the-cpus-clock-gates` nachziehen und `0091` darauf umstellen. Auf
   die Pflichtliste gehört es in **jedem** Fall, nicht in eine Fußnote.
3. **Ob `0097` eingedampft oder `0092` erweitert wird (2.4).** Beides ist sauber, beides ist eine
   Rücknahme von `0097`-Inhalt, beides kostet einen Bau. Die Wahl hängt daran, wie die Hauptsitzung
   die Nummernhistorie lesbar halten will - das ist ihre Entscheidung, nicht meine.
4. **Ob `0095` heute Nacht neu erzeugt wird (2.3).** Fachlich ist der gefuzzte Merge nachweislich
   korrekt (zeilengenau nachgerechnet), formal fehlt die `Signed-off-by:`-Zeile. Ob das den
   Neuaufwand plus einen weiteren Bau rechtfertigt, hängt davon ab, wie viele Board-Slots heute
   Nacht noch übrig sind - das weiß ich nicht.
5. **Nicht geprüft: ob der zusammengeführte Baum wirklich kompiliert.** `build.sh` und der
   Baubaum sind für mich gesperrt, und auf dem Host fehlen `flex`/`bison`/`m4`; das Bau-Image
   `h713-build` läuft gerade nicht. Ich habe stattdessen alle Schnittstellen gegen den
   6.18.38-Quelltext im Testbaum nachgeschlagen (dort kamen `VB2_MAX_FRAME`,
   `vdev->fh_list`-Initialisierung und `commit_tail`-Reihenfolge her). **Ein grüner `patch`-Lauf
   ist kein grüner Bau** - der Compile-Check bleibt Schritt 0.
