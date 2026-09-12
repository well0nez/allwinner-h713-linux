# Paket A — cstengers Display-/Video-Patches übernehmen

**Agent:** Unteragent A (offline, kein Board angefasst).
**Uhrzeiten:** Arbeitsrechner (`date '+%H:%M'`), 06.09.2026.
**Regel eingehalten:** kein `ssh` ans Board, kein `sonoff_ctl`, kein `wandcheck.py`, kein `tio`, nichts nach
`tftp/` kopiert, kein `sudo`, kein `apt`, kein `git commit`/`push`/`checkout`, gebaut nur über
`podman exec h713-build … build/build.sh kernel`. Die Netboot-Variante wurde **nicht** gebaut —
`build/out/h713-kernel-netboot.fit` ist unverändert vom 02.09.

---

## 1. Ablauf mit Uhrzeiten

| Zeit | Schritt |
|---|---|
| 21:42 | Nachtplan 78 (§0, §3 A, §6 letzter Absatz) und `nachtlog/00-koordination.md` gelesen; unsere `series` (49 Zeilen) und cstengers `series` auf `origin/h713-display-video-path` verglichen |
| 21:43–21:45 | Konfliktpatches im Volltext gelesen: unser 0049 und 0050, seine 0052, 0063, 0064, 0078, 0079, 0080, 0082–0086; Board-Registerabzug `re/captures/weltneuheit/ours-20260906-source0/01_lock.txt` und `re/captures/autoboot-display.log` als Beleg herangezogen |
| 21:46 | `0051-soc-sunxi-add-arisc-hdmi-hpd.patch` → `0090-soc-sunxi-add-arisc-hdmi-hpd.patch` umbenannt; 17 Patchdateien mit `git show origin/h713-display-video-path:patches/kernel/<name>` geholt |
| 21:46 | neue `series` geschrieben (65 Zeilen), aufsteigend nach Nummer, unsere 0033–0049 vor cstengers 0051+ |
| 21:47 | Trockenlauf: alle 65 Patches mit `patch -p1` auf einen frisch entpackten 6.18.38-Baum — **fehlerfrei, ohne Fuzz-Meldung**. Damit ist Konfliktpunkt 3 (fehlende Abhängigkeit unter 0078, z. B. 0065/0066/0074/0076) erledigt: **keine** fehlende Abhängigkeit, nichts nachzuziehen |
| 21:48 | 0078 minimal handangepasst (Begründung → §4.4), Trockenlauf wiederholt: wieder fehlerfrei |
| 21:48–21:49 | `podman exec h713-build bash -lc 'cd /work/mainline && build/build.sh kernel'` — **grün** |
| 21:50–21:51 | Gebautes DTB kontrolliert (Display-Knoten ohne `iommus`, Codec `okay`, Carveout 16 MiB, `mips_framebuf` unverändert) |

---

## 2. Übernommene Patches (17 Stück, cstengers Nummern unverändert)

| Nummer | Datei | Was |
|---|---|---|
| 0051 | `0051-iommu-sun50i-rate-limit-fault-reporting.patch` | Fault-Meldungen gedrosselt (macht 0051 der alten Nummerierung frei) |
| 0053 | `0053-drm-panfrost-do-not-map-imported-buffers-cacheable.patch` | Panfrost-Import nicht cacheable |
| 0055 | `0055-arm64-dts-h713-drop-the-1416-mhz-opp-it-corrupts-memory.patch` | 1416-MHz-OPP raus |
| 0059 | `0059-media-cedrus-do-not-disarm-the-watchdog-before-claiming-the-irq.patch` | Cedrus-Watchdog/IRQ-Reihenfolge |
| 0063 | `0063-drm-h713-afbd-give-userspace-a-well-formed-size-range.patch` | `mode_config.max_*` auf 4096, min bleibt Panelgröße (GStreamer-`GstIntRange`) |
| 0064 | `0064-arm64-dts-h713-put-the-kernel-console-on-the-panel-too.patch` | `console=tty0` in den Board-Bootargs (Vorbehalt → §6) |
| 0067 | `0067-misc-decd-match-stock-frame-submit-abi.patch` | decd-Frame-Submit-ABI wie Stock |
| 0071 | `0071-misc-decd-fix-release-fence-lifetime.patch` | decd-Fence-Lebensdauer |
| 0072 | `0072-misc-decd-refuse-a-non-contiguous-dma-buf-import.patch` | decd lehnt nicht-zusammenhängende Importe ab |
| 0073 | `0073-misc-decd-declare-the-single-mapping-dma-constraint.patch` | decd-DMA-Constraint |
| **0078** | `0078-drm-h713-add-fullscreen-nv12-overlay.patch` | **die Video-Plane** — Grundlage für Paket D (handangepasst, §4.4) |
| **0079** | `0079-drm-h713-do-not-vmap-prime-imports.patch` | `DRM_GEM_DMA_DRIVER_OPS` statt `…_VMAP`; ohne das BUGt der PRIME-Import-Close-Pfad |
| 0082 | `0082-arm64-dts-h713-enable-the-internal-audio-codec.patch` | Codec-Knoten auf mainline-Form, Board `okay` |
| 0083 | `0083-arm64-dts-h713-route-lineout-to-the-speaker.patch` | `allwinner,audio-routing = "Speaker", "LINEOUT"` |
| 0084 | `0084-asoc-sun4i-codec-add-the-h713-variant.patch` | H713-Variante in `sun4i-codec` (kein 0x314/0x31c) |
| 0085 | `0085-asoc-h713-drive-the-speaker-from-the-hp-amp.patch` | HP_AMP_EN (Bit 15 in 0x324) als DAPM-Supply |
| 0086 | `0086-asoc-h713-fix-the-audio-clock.patch` | CCU-Gates mit `CLK_SET_RATE_PARENT` + Modultakt-Faktor 1024 statt 512 |

**Umbenannt (Nummernvertrag):** unser `0051-soc-sunxi-add-arisc-hdmi-hpd.patch` → `0090-soc-sunxi-add-arisc-hdmi-hpd.patch`,
in der `series` als letzter Eintrag. 0091–0095 bleiben frei (B/C/D/E/H).

**Unverändert in der `series` geblieben:** unsere 0001–0048 inkl. 0040 (hat cstenger nicht) und **0049**
(Scanout-Carveout 1080p, → §4.2).

---

## 3. Nicht übernommen — mit Begründung

### 3.1 Aus der `series` entfernt

| Patch | Begründung |
|---|---|
| **unser 0050** `0050-asoc-sunxi-add-the-h713-internal-audio-codec.patch` | Konfliktentscheidung 1, → §4.1. **Datei bleibt liegen**, nur aus der `series` genommen |

### 3.2 Von cstenger nicht geholt

| Patch | Begründung |
|---|---|
| **0080** `drm-h713-attach-the-video-plane-to-the-iommu` | Konfliktentscheidung 2, → §4.3. Einziger Patch aus *seiner* `series`, den wir auslassen |
| 0047, 0049, 0050 (seine) mmc/emmc | Debug-/Tuning-Patches (`sdio-tuning-knobs`, `payload-timing-probe`, `debug-cap-emmc-to-25mhz`); stehen auch in **seiner** `series` nicht |
| 0052 `arm64-dts-h713-attach-the-display-to-the-iommu` | Steht nicht auf der Übernahmeliste und nicht in seiner `series`; ausdrücklich als „EXPERIMENT, not a fix" deklariert. Wird von 0080 abgelöst (beide setzen dieselbe Eigenschaft `iommus = <&iommu 2 1>`), und mit 0080 fällt es ohnehin weg |
| 0054, 0066, 0068, 0069, 0070, 0075, 0077, 0087–0094 | `EXPERIMENT` im Namen |
| 0056, 0058, 0060, 0061 | `DEBUG` im Namen |
| 0057, 0062 (cedrus recover/reset), 0065 (`afbd-scan-out-nv12-directly`), 0074 (`cedrus contiguous pool`), 0076 (`decd flip the iommu`), 0081 (`record what the flip timing measured`) | Stehen nicht in seiner `series` und sind **keine** Abhängigkeit von etwas, das wir nehmen — der Trockenlauf um 21:47 hat alle 65 Patches ohne Fuzz angewendet. Insbesondere setzt 0078 **nicht** auf 0065/0066 auf |

---

## 4. Die Konfliktentscheidungen

### 4.1 Konflikt 1 — unser 0050 (Audio-Codec) gegen seine 0082–0086

**Entscheidung: seine 0082–0086 werden übernommen, unser 0050 fällt aus der `series`.**

Die beiden Fassungen schließen einander aus, technisch wie textuell:

* Unser 0050 lässt den DT-Knoten `codec@2030000` in der Vendor-Form (`compatible = "allwinner,sunxi-internal-codec"`,
  zwei reg-Bereiche, `gpio-spk`, `digital_vol`/`speaker_vol`/`pa_*`) und schaltet im Board-DTS zusätzlich
  `&dummy_cpudai` und `&codec_machine` ein. Sein 0082 formt genau diesen Knoten auf die mainline-Form um
  (`sun4i-codec`, ein reg-Bereich, `allwinner,pa-gpios`) — danach fände unser Treiber sein Compatible nicht mehr.
  Beide fassen dieselbe Zeile `&codec { status = "disabled"; }` im Board-DTS an; nur weil unser 0050 draußen ist,
  lässt sich sein 0082 überhaupt anwenden.

**Was seine Serie besser kann** (und was den Ausschlag gibt): sie ist mainline-geformt (erweitert den vorhandenen
`sun4i-codec` statt drei eigene Module danebenzustellen) und sie ist **am Gerät gemessen**, nicht nur aus dem
Stock-Kernel abgeleitet — 0084 belegt, dass H713 kein Register 0x314 hat (Schreibzugriffe verpuffen still, DAPM hält
den Pfad für getrennt), 0085 belegt HP_AMP_EN Bit 15 per A/B-Aufnahme (−0,10 dB gegen das volle Vendor-Wort,
Wiederholbarkeit 0,25 dB), 0086 belegt den Taktfehler zweifach (440 Hz kam bei nominal 44,1 kHz als 418,97 Hz und
bei 48 kHz als 384,93 Hz — beides passt auf 0,01 Hz zu Modultakt/1024). Das ist genau die Belegtiefe, die Regel 1
des Nachtplans verlangt.

**Was unser 0050 kann und seine Serie nicht** (der ehrliche Verlust, damit er nicht untergeht):

1. **Aufnahme.** Unser Treiber hat den ADC-Pfad mit Line-in-PGA. Seine Karte setzt in 0084
   `card->dai_link->playback_only = true`; 0086 sagt es ausdrücklich: „Capture is unimplemented".
   Für die Nacht folgenlos — der HDMI-Ton kommt über ARC/HDMI-RX (Pakete B/E), nicht über den analogen Line-in.
2. **Die Vendor-Klangbausteine** `dacdrc_used` / `adcdrc_used` / `dachpf_used` / `adchpf_used`,
   `dac_swap_en` / `adc_swap_en` und die DT-Vorgabewerte `digital_vol` / `speaker_vol` / `headphone_vol`.
   Bei ihm ersetzt die geerbte H616-Reglerpalette („DAC Playback Volume" als effektiver Master, in 0085 mit
   18,4 dB zwischen Rohwert 16 und 32 nachgemessen) diese Knöpfe.
3. Der I2S-Registersatz (0x02031000), den unser Codec-Treiber mitführt.

Es wurde **kein** neuer Patch erfunden, um 1–3 zurückzuholen — das wäre nicht Paket A. Als offener Punkt notiert (§6).

### 4.2 Konflikt 2a — unser 0049 (Scanout-Carveout 1080p) gegen 0063/0078

**Kein Konflikt; unser 0049 bleibt unverändert in der `series`.**

* 0063 fasst nur `drm->mode_config.max_width/max_height` an (min bleibt die Panelgröße) — das ist orthogonal zur
  Größe des `uboot-scanout`-Carveouts.
* 0078 fasst am `uboot-scanout`-Knoten gar nichts an; sein DTS-Teil erweitert nur `reg`/`reg-names` am
  `display@5600000` (drei Fenster: `afbd` 0x05600000, `route` 0x05140000, `lvds` 0x051c0000).
* Kontrolle am gebauten DTB: `uboot-scanout@6c100000 { reg = <0x6c100000 0x1000000>; }` — die 16 MiB aus unserem
  0049 stehen. `framebuf@4bf41000 { reg = <0x4bf41000 0x1a00000>; }` (26 MB `mips_framebuf`) ist unangetastet.

### 4.3 Konflikt 2b — 0080 (Video-Plane an die IOMMU)

**Entscheidung: 0080 wird NICHT übernommen.** Drei voneinander unabhängige Gründe:

1. **Er ist die IOMMU-Anbindung, er setzt sie nicht voraus.** Die geprüfte Frage „greift 0080 ohne 0052?" hat die
   Antwort: 0080 braucht 0052 nicht, weil **0080 die Eigenschaft selbst mitbringt** — sein DTS-Teil schreibt
   `iommus = <&iommu 2 1>;` plus `memory-region = <&framebuf_reserved>; memory-region-names = "adopted-scanout";`
   an den `display@5600000`. 0052 ist die ältere, ausdrücklich als EXPERIMENT gekennzeichnete Fassung derselben
   Eigenschaft. „0080 so übernehmen, dass ohne `iommus` weiter physisch gelesen wird" ist deshalb nicht möglich:
   ohne diese Eigenschaft bliebe von 0080 nichts Sinnvolles übrig. Sein eigener Commit-Text sagt es unmissverständlich:
   „There is no bypassing phase that works here … Translate from probe." Genau das darf bei uns nicht passieren —
   unsere Capture-Plane liest den Capture-Ring **physisch** (doku/76 §10), die IOMMU ist am Display-Knoten nicht beteiligt.
2. **Er kollidiert textuell mit unserem 0049.** Sein erster DTS-Hunk hängt `iommu-addresses` an den
   `uboot-scanout`-Knoten und führt dabei `reg = <0x6c100000 0x800000>;` als Kontextzeile — bei uns steht dort seit
   0049 `0x1000000`. Der Patch würde also ohnehin nicht sauber anwenden, und ihn dafür von Hand umzuschreiben wäre
   genau das Verbiegen, das Regel 1 verbietet.
3. **Paket D braucht ihn nicht.** D liest den Ring physisch aus `mips_framebuf` (26 MB ab `0x4BF41000`).

Damit einher gehen zwei Dinge, die 0080 gebracht hätte und die jetzt fehlen (→ §6): der `get_resv_regions`-Zusatz
in `sun50i-iommu.c` samt Domain-Bindung, und das Zusammenfassen physisch fragmentierter Cedrus-Capture-Puffer zu
einer zusammenhängenden IOVA. Letzteres bräuchte man nur, wenn irgendwann Cedrus-Ausgabe direkt auf die Plane soll.

**Kontrolle am gebauten DTB:** `display@5600000` hat **keine** `iommus`- und keine `memory-region`-Eigenschaft;
der einzige `iommus`-Eintrag im ganzen DTB ist `video-engine` (Cedrus, aus unserem 0042). Also: physisches Lesen
am Display-Knoten, wie gefordert.

### 4.4 Handanpassung an 0078 — sonst probet der Display-Treiber auf unserem Board nicht

Das ist die einzige Handanpassung der Nacht, und sie ist im Patchkopf von
`0078-drm-h713-add-fullscreen-nv12-overlay.patch` als solche vermerkt.

cstengers 0078 baut ans Ende des Probe eine Zusicherung ein:

```c
if (h->mode.hdisplay != H713_VIDEO_WIDTH ||     /* 1280 */
    h->mode.vdisplay != H713_VIDEO_HEIGHT ||    /*  720 */
    h->video_ctrl_idle != 0x03000010 ||
    h->rgb_ctrl_active != 0x03001901 ||
    h->selector_rgb    != 0x29000000)
        return dev_err_probe(dev, -ENODEV,
                "video handoff state is not the validated 1280x720 configuration\n");
```

Sein Board ist 1280×720, **unseres ist 1920×1080** (`re/captures/autoboot-display.log:610`:
`sun50i-h713-afbd 5600000.display: [drm] adopting 1920x1080, stride 7680, source 6c100000`). Unverändert
übernommen hätte diese Zeile den **gesamten** Display-Treiber mit `-ENODEV` abgewiesen: keine Konsole auf der
Wand, kein DRM-Knoten, kein `modetest`, keine zweite Plane — also keine der drei Abnahmebedingungen von Paket A,
und eine Verschlechterung gegenüber dem heute laufenden Kernel.

**Anpassung:** die beiden Größenvergleiche entfallen, die **drei Registerbedingungen bleiben unverändert**. Sie
sind auf unserem Board exakt erfüllt, belegt durch den Abzug von heute Abend
(`re/captures/weltneuheit/ours-20260906-source0/01_lock.txt`, aufgenommen vor Descriptor und `afbd_source0.py`):

| Register | erwartet (0078) | unser Board |
|---|---|---|
| `0x05600010` (Video-CTRL idle) | `0x03000010` | `0x03000010` |
| `0x05600140` (RGB-CTRL aktiv) | `0x03001901` | `0x03001901` |
| `0x051c006c` (Selektor RGB) | `0x29000000` | `0x29000000` |

Die Fehlermeldung heißt jetzt „… is not the validated register configuration". Sonst wurde an 0078 **nichts**
geändert — die Plane selbst bleibt auf 1280×720 festgenagelt (§5). Wer das anders sieht, macht die Änderung mit
`git -C mainline show origin/h713-display-video-path:patches/kernel/0078-…patch > …` rückgängig; dann bootet der
Kernel aber ohne Display.

---

## 5. Für Paket D: was 0078 im gebauten Baum hinterlässt

**Datei:** `mainline/build/linux-6.18.38-7dff124db0ddefd2bef7f9028ad2bbeaac2f7af7ad50a8fcfbc4226df6088d55/drivers/gpu/drm/tiny/sun50i-h713-afbd.c`

* **Plane-Name:** `"video-0"`, Typ `DRM_PLANE_TYPE_OVERLAY`, auf der CRTC der `drm_simple_display_pipe`
  (`drm_universal_plane_init`, Z. 707–713). Struktur-Feld `h->video_plane`, Zustandsflag `h->video_active`.
* **Angemeldete Formate:** genau eines — `DRM_FORMAT_NV12` (`h713_afbd_video_formats[]`, Z. 522–524).
  Kein NV16. Modifier: nur `DRM_FORMAT_MOD_LINEAR` (im `atomic_check` erzwungen).
* **Neue Registerfenster im DT:** `reg-names = "afbd", "route", "lvds"` →
  `h->regs` 0x05600000/0x400, `h->route_regs` 0x05140000/0x1000, `h->lvds_regs` 0x051c0000/0x100.
  Steht im gebauten DTB.
* **Callbacks:** `h713_afbd_video_atomic_check/_update/_disable`, dazu `h713_afbd_video_stop()` (auch in
  `shutdown`/`remove`) und `h713_afbd_init_video_info()` (VideoInfo-Seite als `dmam_alloc_coherent`, eine Seite).

**Die Falle aus dem Nachtplan — präzisiert.** Der Nachtplan sagt, 0078 „schreibt `+0x4C` mit halber Chroma-Höhe".
Im Code ist es etwas anders und für D genauer so zu lesen:

* 0078 schreibt die AFBD-Crop-Register **`+0x048` und `+0x04C` überhaupt nicht** — sie bleiben stehen, wie die
  Firmware sie hinterlassen hat (auf unserem Board `0x04380780` bzw. `0x021C0780`).
* Die NV12-Annahme steckt in zwei anderen Stellen:
  1. **C-Stride:** `+0x044` wird auf `H713_VIDEO_STRIDE` = **denselben** Wert wie der Y-Stride gesetzt (1280).
     Unsere NV16-Capture braucht dort das Doppelte — `0x05600044 = 0x0F00` bei 1920 Y-Stride (doku/76 §13).
     Das ist der eigentliche „Trick", und der fehlt hier.
  2. **Geometrie:** `+0x020` = `H713_VIDEO_SIZE_M1` = `0x02cf04ff` (720−1 / 1280−1) und `+0x024` =
     `H713_VIDEO_BLOCK_M1` = `0x002c004f`. Unser Board zeigt an denselben Stellen `0x043f077f` und `0x00420077`.
* Weiter geschrieben werden `+0x060` = 1 (Gate), `+0x064` = 0 (Field), `+0x068` = `0x122` (Ring-Mux),
  vier Slots Y/C/Info (`0x070/0x084/0x098` + i·4), Aux-Slots auf 0, `+0x06C` = 1 (Dirty),
  `route +0x508` = `0x144c0000` (Gain), `+0x010` = `0x03000013` (CTRL aktiv), `+0x014` = 1 (Ready),
  `lvds +0x06c` = `0x39000000` (Selektor). Das deckt sich mit `afbd_source0.py` — bis auf Stride und Geometrie.
* **VideoInfo-Seite:** Magic `0x61770000`, Typ 2, Breite/Höhe **1280/720** an `+0x08/+0x0c/+0x10/+0x14`,
  `+0x40 = 0` (`color_format`, bleibt 0 — passt zu doku/76 §11.3), `+0x64/+0x68` = Selbstzeiger +144/+172,
  Fenster `+0x70…+0x88` bereits als 1920/1080 in 1/16 px. D muss die Quellgeometrie auf 1920×1080 ziehen.
* **Harte Grenzen im `atomic_check`**, die D anfassen muss, bevor die Plane auf unserem Board überhaupt
  benutzbar ist: Format NV12, `fb->width/height` == 1280/720, beide Pitches == 1280, `src_*` und `crtc_*`
  exakt 1280×720 bei Offset 0 — sonst `-EINVAL`. **Auf unserem 1920×1080-Board wird die Plane also gelistet,
  ist aber bis Paket D nicht benutzbar.** Das ist gewollt; A liefert die Grundlage, nicht die Anpassung.

---

## 6. Offene Punkte

1. **Plane ist gelistet, aber nicht benutzbar** (1280×720 fest verdrahtet, nur NV12, C-Stride == Y-Stride).
   → Paket D. Kein Handgriff in A.
2. **Kein Line-in-Capture mehr**, seit unser 0050 aus der `series` ist (§4.1). Falls das je gebraucht wird,
   ist der Weg nicht „0050 zurück", sondern ein Capture-Pfad in `sun4i-codec` — der Knoten und der ADC-Registersatz
   sind in unserem 0050 dokumentiert, die Datei bleibt liegen.
3. **Tote Zeilen im Defconfig.** `patches/kernel/board/hy200_qz713df_a1_defconfig` Z. 151–153 nennen noch
   `CONFIG_SND_SOC_SUNXI_H713_CODEC/_CPUDAI/_MACHINE=m`. Die Symbole existieren ohne 0050 nicht mehr; kconfig
   überliest sie stillschweigend, der Bau ist grün, das gebaute `.config` hat sie nicht.
   **Nicht angefasst** (nichts Ungefragtes tun) — die Hauptsitzung entscheidet, ob sie raus sollen.
   Solange sie stehen bleiben, genügt ein Eintrag in der `series`, um 0050 wieder scharfzuschalten.
4. **0064 und der Netboot-Pfad.** 0064 hängt `console=tty0` an die Bootargs **im Board-DTS**. Das Board bootet
   per TFTP-FIT, und die FIT (`h713-kernel-netboot.its`) trägt keine Bootargs — U-Boot schreibt seine eigenen ins
   `/chosen` (das DTS nennt `root=/dev/mmcblk0p26`, das Board fährt NFS-Root, also überschreibt U-Boot ohnehin).
   0064 wirkt auf dem Netboot-Weg also vermutlich **nicht**. Kein Schaden, nur keine Wirkung — nicht angefasst,
   weil dazu die U-Boot-Umgebung geändert werden müsste, und das gehört nicht zu A.
5. **0080-Verzicht, Folgen:** `sun50i-iommu.c` bekommt weder `.get_resv_regions = iommu_dma_get_resv_regions`
   noch die Domain-Bindung in `domain_alloc_paging()`; PRIME-Importe laufen weiter physisch, ein fragmentierter
   Cedrus-Capture-Puffer wird also **nicht** zu einer zusammenhängenden IOVA zusammengefasst. Für D irrelevant
   (physischer Ring), relevant erst, wenn jemand Cedrus-Ausgabe direkt auf die Plane legen will.
6. **Kein Prüflauf der neuen Audio-Kette.** 0082–0086 sind auf cstengers Board gemessen, auf unserem noch nie.
   Sie liegen außerhalb der A-Abnahme; wenn ein Board-Slot übrig ist, wäre `aplay -l` plus ein 440-Hz-Ton der
   billigste Test (Erwartung: eine Karte, Ton hörbar, tonhöhenrichtig).

---

## 7. Baubericht

```
podman exec h713-build bash -lc 'cd /work/mainline && build/build.sh kernel'
```

| | |
|---|---|
| **Ergebnis** | **grün**, Exit 0 |
| **Baumhash** | `7dff124db0ddefd2bef7f9028ad2bbeaac2f7af7ad50a8fcfbc4226df6088d55` |
| **Baum** | `/opt/Projekte/h713/mainline/build/linux-6.18.38-7dff124db0ddefd2bef7f9028ad2bbeaac2f7af7ad50a8fcfbc4226df6088d55` |
| **Dauer** | 21:48 → 21:49:57, rund **90 s** (24 Threads, LLVM, kein ccache; frischer Baum, voller Bau bis `LD vmlinux`) |
| **Artefakte** | `build/out/Image.gz` (7 741 626 B), `build/out/h713-kernel.fit` (7 774 864 B), `build/out/sun50i-h713-hy200-qz713df-a1.dtb` (32 240 B), `…-qz713-v2.dtb` — alle 21:49 |
| **Patches** | 65 Zeilen in `series`, alle sauber angewendet (kein Fuzz, keine `.rej`) |
| **Nicht gebaut** | `KERNEL_CONFIG=netboot` — absichtlich nicht. `build/out/h713-kernel-netboot.fit` ist unverändert vom 02.09.2026, 00:21. Die Netboot-FIT baut und rollt die **Hauptsitzung** aus (Nachtplan §6) |

Kontrollen am gebauten DTB (`sun50i-h713-hy200-qz713df-a1.dtb`):

* `display@5600000`: `reg = <0x5600000 0x400 0x5140000 0x1000 0x51c0000 0x100>`,
  `reg-names = "afbd","route","lvds"`, **kein** `iommus`, **kein** `memory-region`.
* einziger `iommus`-Eintrag im DTB: `video-engine` (Cedrus).
* `codec@2030000`: `compatible = "allwinner,sun50i-h713-codec"`, `status = "okay"`,
  `allwinner,audio-routing = "Speaker","LINEOUT"`, `allwinner,pa-gpios` auf `r_pio` PL2.
* `uboot-scanout@6c100000`: `reg = <0x6c100000 0x1000000>` (unser 0049, 16 MiB).
* `framebuf@4bf41000`: `reg = <0x4bf41000 0x1a00000>` (26 MB, unverändert).

---

## 8. Board-Anfrage (an die Hauptsitzung)

**Voraussetzung:** Netboot-FIT aus dem obigen Baum bauen und ausrollen — das ist ausdrücklich **nicht** von mir
gemacht worden:

```bash
podman exec h713-build bash -lc 'cd /work/mainline && KERNEL_CONFIG=netboot build/build.sh kernel'
cp tftp/h713-kernel-netboot.fit tftp/h713-kernel-netboot.fit.bak-20260906-A
cp mainline/build/out/h713-kernel-netboot.fit tftp/
```
(erst mit gehaltener Sperre; Module aus `mainline/build/out/modules/` per `scp` ins NFS-Root, dann `depmod -a`.)

**Zu prüfen, in dieser Reihenfolge:**

1. **Kaltstart mit dem neuen Kernel** (`sonoff_ctl restart --host 192.168.8.179`), vorher `ss -ulnp | grep -w :69`.
   Erwartung: Board kommt hoch, SSH nach ~40 s.
2. **Konsole auf der Wand wie heute.** *Das ist der kritische Punkt dieses Pakets.* Wenn kein Bild kommt:
   `dmesg | grep -i afbd` ansehen. Zwei mögliche Meldungen:
   * `adopting 1920x1080, stride 7680, source 6c100000` → alles gut, der Treiber ist durch.
   * `video handoff state is not the validated register configuration` → einer der drei Registerwerte aus §4.4
     war beim Probe anders als im Abzug von 19:41. **Bitte den Ist-Wert notieren** (`0x05600010`, `0x05600140`,
     `0x051c006c` direkt nach dem Boot), dann kann die Zusicherung gezielt nachgezogen werden — bitte nicht raten.
3. **`modetest -M sun50i-h713-afbd`** (oder der Name, den `/sys/class/drm/card*/device/…` zeigt).
   Erwartung: die RGB-Primary **plus eine zweite Plane namens `video-0`**, Typ Overlay, in ihrer Formatliste
   genau ein Eintrag: `NV12`. Bitte die `modetest`-Ausgabe abspeichern (Plane-ID + Formatliste) — Paket D
   braucht die Plane-ID.
   *Erwartetes Nicht-Ergebnis:* jeder Versuch, die Plane zu **benutzen**, endet mit `-EINVAL`. Das ist korrekt und
   kein Fehler — 0078 verlangt 1280×720, unser Panel ist 1920×1080 (§5). Bitte nicht als Regression buchen.
4. **Sequenz aus Nachtplan §1 unverändert** (prep → SetSource(3) → `arisc_edid_init.sh` → 6 s →
   `viddec_descriptor.py set` **genau einmal** → `afbd_source0.py on` → `wandcheck.py shot A-nachher`).
   Erwartung: dasselbe Bild wie heute Abend. Der neue Kernel darf daran nichts ändern — die Skripte fassen
   dieselben Register an, und die Plane ist inaktiv.
   Wenn das Bild **nicht** kommt: der wahrscheinlichste Verdächtige ist 0079 (`DRM_GEM_DMA_DRIVER_OPS`) oder
   0063 (`max_width/max_height` 4096) — beide fassen aber nur DRM-Userspace-Pfade an, nicht die Register.
5. **Optional, wenn ein Slot übrig ist** (nicht Teil der A-Abnahme): `aplay -l` sollte jetzt eine Karte zeigen
   (`sun4i-codec`, H713-Variante). Ein 440-Hz-Ton sollte hörbar und tonhöhenrichtig sein (0086). Das ist der
   erste Test dieser Kette auf **unserem** Board.

**Rückweg bei Bootfehler:** `cp tftp/h713-kernel-netboot.fit.bak-20260906-A tftp/h713-kernel-netboot.fit`,
Kaltstart, Log.
