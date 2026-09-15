# Koordination (Hauptsitzung = Board-Agent)

**21:45** Umgebung geprüft: `h713-build` läuft (11 h), TFTP lauscht (`ss -ulnp | grep -w :69` → `[::]:69`),
Board erreichbar (`uptime` 31 min, Kaltstart 21:08), keine Board-Sperre vorhanden.

## Vereinbarungen für die Nacht

1. **Board-Agent ist ausschließlich die Hauptsitzung.** Kein Unteragent fasst `ssh root@192.168.8.141`,
   `sonoff_ctl`, `ssh user@192.168.8.162`, `wandcheck.py`, `/dev/ttyACM0` oder `sudo` an. Board-Bedarf wird im
   eigenen Teillog unter „Board-Anfrage" notiert.
2. **Teillogs statt gemeinsamer Datei.** Jeder Agent schreibt ausschließlich
   `doku/nachtlog/<paket>.md` (z. B. `A-patches.md`). Die Hauptsitzung führt sie in
   `doku/79-nachtlog-20260907.md` zusammen. So kann niemand die Datei eines anderen überschreiben.
3. **`patches/kernel/series` gehört in Welle 1 allein Paket A.** Nur A ruft `build/build.sh kernel` auf.
   B/C/D/H legen ihre Patchdatei ab und prüfen den Code out-of-tree gegen einen bestehenden Baum
   (`make -C build/linux-… M=…`, ausdrücklich als Prüfbau gekennzeichnet); die Aufnahme in `series` und den
   Gesamtbau macht die Hauptsitzung nach A.
4. **Nummernvertrag** (damit keine zwei Pakete dieselbe Nummer belegen):
   | Nummer | Paket |
   |---|---|
   | cstengers Nummern (0051, 0053, 0055, 0059, 0063, 0064, 0067, 0071-0073, 0078-0080, 0082-0086) | A, unverändert übernommen |
   | 0090 | unser bisheriges `0051-soc-sunxi-add-arisc-hdmi-hpd` nach der Umnummerierung (A) |
   | 0091 | B - `0091-soc-sunxi-h713-arisc.patch` (ersetzt 0090, das dann aus `series` fällt) |
   | 0092 | C - `0092-soc-sunxi-h713-cpu-comm-kernel-api.patch` |
   | 0093 | D - `0093-drm-h713-afbd-nv16-hdmi-ring.patch` |
   | 0094 | E - `0094-media-sun50i-h713-hdmirx.patch` |
   | 0095 | H - `0095-drm-h713-afbd-color-mgmt.patch` |
5. **Kein `git commit`, kein `push`, kein Anfassen der Memory-Dateien.** Patches und Dokumente sind Dateien.

## Nachtrag 22:15 - zwei Zustände, die nur in einem Baubaum lebten

Beim Ausrollen des A-Kernels blieb die Wand grün (leerer Ring). Die Ursache war **nicht** Paket A, sondern
dass der funktionierende Stand vom 05./06.09. an drei Stellen **nur als Handänderung im Baubaum**
`build/linux-6.18.38-d9f9ca8b…` existierte und in **keinem** Patch der Serie stand. Gefunden über die
Zeitstempel: in einem frisch gepatchten Baum tragen alle Quelldateien die Uhrzeit des Patchlaufs; von Hand
geänderte Dateien sind später.

| Datei | Zeitstempel | jetzt gesichert als |
|---|---|---|
| `arch/arm64/boot/dts/allwinner/sun50i-h713.dtsi` (Knoten `tvcap@50c0000`) | 05.09. 03:04 | **0096** |
| `drivers/soc/sunxi/cpu_comm/cpu_comm_rpc.c` | 05.09. 14:27 | **0097** |
| `drivers/soc/sunxi/cpu_comm/cpu_comm_proto.c` | 05.09. 14:32 | **0097** |

`series` hat damit 67 Zeilen.

### Was das für Paket C bedeutet (beim Zusammenführen beachten)

Paket C arbeitet gegen den Baum `linux-6.18.38-d9f9ca8b…`, der die Handänderungen **enthält** - sein Patch
0092 kann sie deshalb versehentlich mit-diffen oder mit 0097 kollidieren. Beim Einordnen von 0092 also:
1. prüfen, ob 0092 Hunks enthält, die inhaltlich schon in 0097 stehen (tgid bei `+0x34`, `memset(routine_info)`,
   die `callwq_kernel_cb`-Absicherung, die RX-CALL-Druckoffsets) - diese Hunks gehören **nicht** in 0092;
2. **0097 vor 0092** in der `series` lassen.

Ebenfalls zu korrigieren: die Aussage aus Paket J, der callwq-Fix sei „im Serienbaum", stimmt nicht - er war
eine Handänderung. J hat den alten Baubaum gelesen. Der Befund von J bleibt richtig, nur die Herkunft war es nicht.

## Nachtrag 22:57 - was die Board-Messungen für die Patches bedeuten

Diese drei Befunde sind **nach** dem Bau der Patches entstanden. Sie sind kein Grund, heute Nacht noch etwas
umzubauen, aber sie gehören in die Abnahme und in die nächste Fassung:

1. **Der Descriptor schaltet die Capture ab** (`0x06940928` Bit 31 → 0). Paket **D** schreibt den Descriptor
   beim Plane-Enable - die Plane wäre danach also aktiv, aber der Ring stünde still. **D braucht nach dem
   Descriptor eine Freigabe.** Zwei belegte Wege stehen zur Wahl:
   - **Quellenwechsel** (`SetSource` weg und zurück) - `B2-quellenwechsel.md`, null strukturelle
     Registerunterschiede, Bild kehrt auf 0,00 % genau zurück. **Das ist der sauberere Weg für D/E**, weil
     `VIDIOC_S_INPUT` ohnehin ein Quellenwechsel ist und kein Hot-Plug erfunden werden muss.
   - **HPD-Zyklus**, 0,3 s genügen - `M4-hpd-dauer.md`.
   Beides sind Stock-RPCs, kein Poke und kein Quirk.
2. **`0x06940824` Bit 31 und `0x06940400 = 0x61` sind für den Betrieb nicht nötig** (B2). Wer sie in einer
   Abnahme als Gutkriterium prüft, prüft das Falsche.
3. **Die PQ-RPCs erreichen unseren Source-0-Pfad** (`K5-board-verifikation.md`): Kontrast wirkt messbar
   (12,16 % der Wand), Helligkeit schreibt ihr Register, wirkt aber **nicht**. Paket **I** darf `BRIGHTNESS`
   deshalb noch nicht als Control anbieten.

## Nachtrag 23:00 - Defconfig: zwei Zeilen bringt kein Patch mit

`patches/kernel/board/hy200_qz713df_a1_defconfig` muss von Hand nachgezogen werden, keiner der fünf neuen
Patches fasst die Datei an:

| Zeile | jetzt | soll | Grund |
|---|---|---|---|
| 198 | `CONFIG_HY310_ARISC_HDMI=m` | `CONFIG_SUN50I_H713_ARISC=m` | 0091 benennt das Symbol um (0090 fällt weg). **Bewusst `=m`, nicht `=y`:** eingebaut probt der Treiber vor dem NFS-Root, und `request_firmware()` fände nichts. |
| neu | - | `CONFIG_VIDEO_SUN50I_H713_HDMIRX=m` | 0094 bringt das Symbol mit, aktiviert es aber nicht |

**Konfliktfläche im Devicetree:** `arch/arm64/boot/dts/allwinner/sun50i-h713.dtsi` wird von **vier** neuen
Patches angefasst - 0091 (Knoten `arisc@100000`), 0093 (`decd_reserved` verkleinern + `viddec-info@4d95f000`),
0094 (`hdmi-rx@5600320`), 0095 (lvds-Fenster `0x100 → 0x200` + `gamma`-Fenster) - dazu das bereits
eingereihte 0096 (`tvcap@50c0000`). Die Reihenfolge in `series` entscheidet, ob das aufgeht.

## Nachtrag 23:05 - Stolperstein für die Abnahmen von D und H

`gamma_test` (Paket H) spricht standardmäßig `/dev/dri/card0` an. Auf unserem Board ist das **Panfrost**
(nur Render-Knoten); der AFBD-Anzeigetreiber ist **`card1`**. `hdmi_plane_test` (Paket D) sucht die Karten
dagegen selbst ab (Z. 145) und braucht den Schalter nicht - der Stolperstein betrifft nur `gamma_test` (`card1-LVDS-1`, CRTC-ID **36**, Primary-Plane 34,
Video-Plane **38**). Ohne `--karte /dev/dri/card1` meldet `gamma_test` nur
`kein Atomic-Modeset auf /dev/dri/card0: Operation not supported`.

Beide Programme sind bereits auf dem Board gebaut und liegen unter `/root/` (`hdmi_plane_test`, `gamma_test`,
dazu Paket Es statisches `hdmirx_test`). Der Eigenschaftstest von `gamma_test` läuft und meldet korrekt
`CRTC 36 hat kein GAMMA_LUT` - 0095 ist ja noch nicht im Kernel. Das Werkzeug ist damit vor der Abnahme geprüft.

## Nachtrag 23:12 - Richtigstellung: `v4l2-ctl` ist auf dem Board vorhanden

Ich habe den Paketen **E** und **F** mitgegeben, `v4l2-ctl` sei auf dem Board nicht installiert, und beide
haben daraufhin Ersatzwege gebaut. **Die Aussage war falsch.** Ursache: ich habe `which v4l2-ctl` auf dem
**Arbeitsrechner** ausgeführt (dort fehlt es tatsächlich) und das Ergebnis dem Board zugeschrieben.

Nachgeprüft im exportierten Board-Root:

```
/srv/h713-rootfs/usr/bin/v4l2-ctl        vorhanden
/srv/h713-rootfs/usr/bin/gst-launch-1.0  vorhanden
/srv/h713-rootfs/usr/bin/modetest        FEHLT
```

Nur **`modetest` fehlt wirklich** - das war korrekt und ist am Board geprüft (`which modetest` dort).

**Folgen, die beim Zusammenführen zu berichtigen sind:**
- `doku/nachtlog/E-v4l2.md` §6 und `doku/88-v4l2-hdmirx.md`: die Begründung „ohne `v4l2-ctl`" streichen.
  Das mitgelieferte statische `hdmirx_test` und die debugfs-Zeilen bleiben trotzdem wertvoll (sie messen
  Dinge, die `v4l2-ctl` nicht zeigt) - nur ihre **Notwendigkeit** war falsch begründet.
- `doku/nachtlog/F-hy310-tv.md`: Paket F hat den Fehler selbst bemerkt und richtiggestellt; seine
  Entscheidung für ein C-Programm steht auf vier anderen Gründen (kein `VIDIOC_EXPBUF` in 0094, die
  Treiber-Property `hdmi-ring`, die Zustandsmaschine, sauberes Beenden) und bleibt davon unberührt.

Für die Abnahme heißt das: `v4l2-ctl -d /dev/videoN --query-dv-timings` und
`v4l2-ctl --stream-mmap --stream-count=60` aus dem Nachtplan sind **direkt ausführbar**.

## Nachtrag 23:16 - die dtsi-Konfliktfläche, von Hand geprüft

Die Konfliktprüfung des Workflows deckt 0093 gegen 0095 ab, aber **vier** Patches ändern das dtsi. Die Anker:

| Patch | Hunk(s) im dtsi | was |
|---|---|---|
| 0091 | `@@ -1387,6 +1387,63` | Knoten `arisc@100000` |
| 0093 | `@@ -80,9 +80,27` und `@@ -1730,6 +1748,18` | `decd_reserved`/`viddec_info`; `memory-region` im afbd-Knoten |
| 0094 | `@@ -1797,6 +1797,54` | Knoten `hdmi-rx@5600320` |
| 0095 | `@@ -1724,8 +1724,9` | `reg`/`reg-names` des afbd-Knotens (lvds `0x100 → 0x200`, neues `gamma`-Fenster) |
| 0096 | `@@ -1469,6 +1469,32` | bereits in `series` |

**Einzige enge Stelle:** 0095 (1724) und 0093s zweiter Hunk (1730) liegen im **selben Knoten**
`display@5600000`. Nachgesehen: 0095 ändert `reg` und `reg-names`, 0093 hängt `memory-region` /
`memory-region-names` hinter `clock-names`. Die beiden überlappen ausschließlich in **Kontextzeilen**
(`clocks = <&ccu CLK_AFBD>,` und die Folgezeile), die **keiner von beiden ändert**. `patch` findet den
zweiten Hunk mit Versatz; die Reihenfolge ist hier gleichgültig.

Die übrigen drei Anker liegen weit auseinander. **Im dtsi ist damit keine Handarbeit nötig** - die eigentliche
Konfliktfläche ist `drivers/gpu/drm/tiny/sun50i-h713-afbd.c` (0093 gegen 0095) und
`drivers/soc/sunxi/cpu_comm/` (0092 gegen das eingereihte 0097).

## Nachtrag 07.09., 10:06 - Agenten schreiben nicht mehr in die Patch-Serie

**Anlass, von Marco angemahnt:** Bis hierher durften Unteragenten `mainline/patches/kernel/*.patch`
direkt ändern (nur `series` und `build/build.sh` waren tabu). Das hat uns beim Callback-Fix den
Rückweg gekostet: der Agent überschrieb `0092` und `0094`, sein Stand fiel am Gerät durch, und die
Fassung, mit der A-H grün waren, existierte als Patch nicht mehr. Nur weil der **Baubaum**
`linux-6.18.38-e39777bf…` noch dalag, ließ sich daraus eine bootfähige FIT rekonstruieren. Darauf
darf man sich nicht verlassen.

### Regel

**Ein Agent ändert keine Datei unter `mainline/patches/kernel/`.** Er legt seinen Vorschlag unter

    mainline/patches/vorschlaege/<paket>/<patchname>.patch

ab und beschreibt in seinem Teillog, was daran anders ist. Die Aufnahme in die Serie macht
ausschließlich die Hauptsitzung - und zwar erst, nachdem sie

1. eine **Momentaufnahme** des Ist-Standes gezogen hat (`patches-snapshots/<zeitstempel>/`,
   enthält alle `*.patch`, `series` und `board/`),
2. den Vorschlag gegen den Ist-Stand **gelesen** hat (`diff -u`), und
3. geprüft hat, dass die Serie danach anwendbar bleibt (71/71, kein `.rej`).

**Ausnahme:** ein ausdrücklicher Implementierungsauftrag, in dem die Hauptsitzung den Agenten
namentlich für eine bestimmte Patchdatei freigibt - und auch dann erst nach einer Momentaufnahme.

### Warum nicht einfach „vorsichtiger sein"

Weil der Schaden nicht beim Schreiben auffällt, sondern erst, wenn man zurück will. Ein Agent, der
seinen eigenen Prüfbau grün sieht, hat keinen Anlass zur Vorsicht - die Prüfung, die zählt, ist die
am Gerät, und die kommt später. Die Trennung „Agent schlägt vor, Hauptsitzung nimmt auf" macht den
Rückweg zu einer Eigenschaft des Verfahrens statt zu einer Frage der Sorgfalt.

### Bestand

- `patches-snapshots/20260907-100635/` - 73 Patchdateien, der Stand vor dem Ergebnis des
  laufenden Regressions-Agenten.
- `tftp/h713-kernel-netboot.fit.GUT-e39777bf` + `mainline/build/modroot.GUT/` - der letzte
  vollständig grüne Stand, fertig gebaut. Rollback = `cp` nach `tftp/`, Module entpacken, Kaltstart.
