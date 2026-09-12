# Entwurf — Punkt 2 des Plans `doku/91`: Auflösungswechsel der Quelle

07.09.2026, Offline-Sitzung (kein Board, kein Bau). Auftrag: `doku/91-plan-drei-punkte.md` Punkt 2,
Unterpunkte 2.1–2.5. Alles hier liegt nur in diesem Ordner:

| Datei | Inhalt |
|---|---|
| `0107-media-drm-h713-follow-source-geometry.patch` | Kernel: `sun50i-h713-hdmirx.c`, `sun50i-h713-afbd.c`, `sun50i-h713.dtsi`, hdmirx-`Kconfig` |
| `hy310-tv.diff` | Userspace: `userspace/hy310-tv/main.c`, `README.md` (mit `-p1` ab Projektwurzel) |
| `ENTWURF.md` | diese Seite |

**Nummer 0107, nicht 0104.** Der Auftrag nennt `0104-…`; während dieser Sitzung sind in der Serie
`0104-drm-media-h713-give-the-chroma-gain-one-owner.patch` (Punkt 3, 17:05),
`0105-soc-sunxi-cpu-comm-stop-reading-the-mips-newcall-ring.patch` (17:36) und
`0106-soc-sunxi-cpu-comm-quiet-the-per-call-log.patch` (17:43) dazugekommen (Serie jetzt 79 Zeilen).
Mein Patch ist gegen den Baum **nach 0104** erzeugt; 0105/0106 berühren nur `drivers/soc/sunxi/cpu_comm/`
und sind auf den Trockenlauf-Baum **mit** meinem Patch sauber angewendet worden — die Dateien sind
disjunkt, die Reihenfolge ist deshalb gleichwertig. Er heißt 0107.

**Trockenlauf:** frischer Tarball `mainline/build/cache/linux-6.18.38.tar.xz`, die Serie aus
`mainline/patches/kernel/series` (Stand 17:25, 77 Zeilen bis 0104) mit `patch -s -d $tmp -p1` (0 Fehler),
danach 0107 — sauber, keine `.rej`; anschließend die neuen 0105/0106 obendrauf — ebenfalls sauber. `hy310-tv.diff` mit `patch --dry-run -d /opt/Projekte/h713 -p1` — sauber. **Nicht kompiliert.**
Gelesen gegen `include/media/v4l2-dv-timings.h`, `v4l2-common.h`, `uapi/linux/videodev2.h`,
`drivers/media/v4l2-core/v4l2-dv-timings.c`, `drivers/media/i2c/tc358743.c`,
`drivers/gpu/drm/drm_atomic_helper.c`, `drivers/mfd/syscon.c` im 6.18.38-Baum.

---

## 0. Drei Befunde, die den Auftrag korrigieren

Der Auftrag sagt: *„Para[1] ist ein phys. Zeiger auf 44 Byte Signal-Info … Stocks elog nennt die
Felder: h_total, v_total, h_active, v_active, hde_start, vde_start"*. Das Disassemblat sagt etwas anderes.

1. **Die 44 Byte enthalten weder Totale noch Synchronlagen.** Die Zeilen `debug_info.c 397–402`
   (`hdmi.timing.h_total … vde_start`) stammen aus dem MIPS-internen **172-Byte**-`VidDec_SignalInfo`
   (`CallbackOfSignalChange`, `re/notes/HANDOFF-VIDEODEC-SCANOUT-RE-COMPLETE-20260612.md` §2). Die
   44-Byte-HAL-Struktur, auf die `Para[1]` zeigt, ist die, die `thal_display_source.cpp 203–214` druckt:
   `signal_id, frame_rate_x100, b_interlace, color_format, color_space, resolution.h_size,
   resolution.v_size, hdr_mode, b_full_range, b_dvi_mode, atv_uid`. Layout in §1. **Stocks ARM kennt
   damit ebenfalls keine Totale** — es arbeitet mit `signal_id`, Größe und Bildrate.
   Für `v4l2_dv_timings` kommen die Totale deshalb aus INCAP (`+0x548`, E4), die Synchronlagen aus
   **keiner** Quelle — siehe §2.

2. **Der Zeiger steht in `args[1]`, nicht `args[2]`.** Die Firmware sendet `ParaCount:2`
   (elog `cpu_comm_core.c 548`); der Adapter `0x8b109fb0` schreibt `Para[0] = source_id`,
   `Para[1] = Zeiger`. `h713_hdmirx_status_show()` las bisher `signal_args[2]` und hat die
   `signal-info`-Zeile deshalb **nie** gezeigt. `doku/83` und `doku/88` schreiben „Para[2]" — das ist
   die 1-basierte Zählung von `hdmi_seq.py` („Para[1..4]"), nicht der 0-basierte `args[]` der API.
   `doku/83` warnt selbst vor genau dieser Verwechslung.

3. **doku/84 „+16 = Descriptor-Farbformat + 1" passt nicht zum Layout.** `+0x10` ist `color_space`;
   der dort gesehene Wert 1 ist `kHalColorSpace_BT709` (Namenstabelle `0x8b1fa1c8`), und BT709 meldet
   die Firmware für diese Quelle (`thal_display_source.cpp 208`). Vermutung, nicht Messung: doku/84 hat
   den Farbraum für ein verschobenes Farbformat gehalten.

---

## 1. Layout der Signal-Info — mit Beleg je Feld

Werkzeug: `display.bin` (`re/ida/HY310-DEV/display.bin`, Basis `0x8B100000`, MIPS32 LE) mit capstone
zerlegt, Skript im Scratchpad (`mdis2.py`). Keine IDA-Brücke, kein Board.

**Drucker `0x8b14b544` (thal_display_source.cpp, `_TSignalChangeCallback`):** legt die HAL-Struktur bei
`sp+0x20` an (Aufruf `0x8b12bbb4(intern, sp+0x20)` wandelt die interne Info in die HAL-Form) und lädt
je elog-Zeile **ein Wort**:

| Offset | Feld | Beleg (Instruktion → elog-Zeile) | Wert im Stock-Mitschnitt (1080p60) |
|---|---|---|---|
| — | `source_id` | `lw a0,(s3)` = **erstes Argument**, nicht Teil der 44 Byte → Zeile 203 | `kHalSourceID_HDMI_1` = 3 = `Para[0]` |
| `+0x00` | `signal_id` | `8b14b5c0: lw a0,0x20(sp)` → Namenstabelle `0x8b14adc0` → Zeile 204 | `kHalSignalID_XGA19201080` |
| `+0x04` | `frame_rate_x100` | `8b14b5f8: lw v0,0x24(sp)` → Zeile 205 | `6000` |
| `+0x08` | `b_interlace` | `8b14b628: lw v0,0x28(sp)` → Zeile 206 | `0` |
| `+0x0c` | `color_format` | `8b14b65c: lw a0,0x2c(sp)` → Tabelle `0x8b14b2c0` → Zeile 207 | `kHalColorFormat_RGB_888` |
| `+0x10` | `color_space` | `8b14b690: lw a0,0x30(sp)` → Tabelle `0x8b14b408` → Zeile 208 | `kHalColorSpace_BT709` |
| `+0x14` | `resolution.h_size` | `8b14b6c0: lw v0,0x34(sp)` → Zeile 209 | `1920` |
| `+0x18` | `resolution.v_size` | `8b14b6f0: lw v0,0x38(sp)` → Zeile 210 | `1080` |
| `+0x1c` | `hdr_mode` | `8b14b724: lw a0,0x3c(sp)` → Tabelle `0x8b14b49c` → Zeile 211 | `kHalHdrScheme_Sdr` |
| `+0x20` | `b_full_range` | `8b14b754: lw v0,0x40(sp)` → Zeile 212 | `1` |
| `+0x24` | `b_dvi_mode` | `8b14b784: lw v0,0x44(sp)` → Zeile 213 | `1` |
| `+0x28` | `atv_uid` | `8b14b7b4: lw v0,0x48(sp)` → Zeile 214 | `-1953898660` |

11 Wörter = **44 Byte**, deckungsgleich mit `hal_adapter_init`s `li a0,0x2c` (doku/74).

**Adapter `0x8b109fb0`** (registriert von `THal_Vp_RegisterSignalChangeCallback`, `0x8b109f94`):
`memcpy(sgp_hal_signal_info, a1, 0x2c)` (`8b109fcc/fd0`), `ParaCount = 2` (`8b109fd8/dc`),
`Para[0] = a0 = source_id` (`8b109fe4`), `Para[1] = ((p & 0x0fffffff) | 0x80000000) + 0xc0000000`
(`8b109fe8–8b10a008`: `0xae332000 → 0x4e332000`), dann `0x8b124580("MipsHalCallback_SignalChange", …)`.
Der Drucker ruft den Adapter mit `jalr a2` bei `8b10a80c` mit `a0 = hal_source_id, a1 = sp+0x20`.

**Enum-Werte, soweit belegt** (Namenstabelle `0x8b14adc0`): `kHalSignalID_NONE = 0`, `_UNKNOWN = 1`,
`_NOCHANGE = 2`, 3–15 analoge Normen. Die XGA-/CE-Werte habe ich nicht aufgelöst (Sprungtabelle) und
brauche sie nicht: der Treiber nimmt die Geometrie aus dem Record, nicht aus der Mode-ID.

**Stock-Mitschnitt bei Signalverlust** (`stock-live-norm.txt:2194–2210`): `signal_id = kHalSignalID_NONE`,
`resolution.h_size = 0`, `b_dvi_mode = 0`. Der Treiber wertet beides als „kein Signal".

**Adresse:** `0x4e332000` liegt im `cpu-comm@4e300000` (`0x4e300000 … 0x4e800000`, `no-map`) — geprüft.
Sie wird von der Firmware **einmal** pro Boot allokiert (`hal_adapter.cpp 257`) und in jedem Mitschnitt
gleich; der Treiber verlässt sich darauf nicht (Mapping folgt `Para[1]`, wird bei Wechsel neu gemacht).

---

## 2. Belegt / erschlossen / Vermutung — was in `v4l2_dv_timings` steht

| Feld | Quelle | Status |
|---|---|---|
| `width`, `height` | Record `+0x14/+0x18` **und** INCAP `+0x874` (E4, zwei Modi exakt); müssen übereinstimmen, sonst `-ENOLCK` | **belegt** |
| `interlaced` | Record `+0x08` | belegt (Feld), **nicht akzeptiert** in der Cap (Ring-Layout bei Halbbildern nie angesehen → `-ERANGE`) |
| `h_total`, `v_total` | INCAP `+0x548` (E4: `0x04650898`/`0x02ee0672`) | **belegt** (zwei Modi) |
| Bildrate | Record `+0x04` (`frame_rate_x100`); **ohne** Record: aus den Flip-Zeigern gemessen (≥ 2 Perioden, ±~2 %) | belegt / gemessen |
| `pixelclock` | `h_total × v_total × Bildrate` | **erschlossen** (Rechnung; Stock misst selbst `148501637` — Abweichung 1637 Hz zu 148,5 MHz) |
| Porches, Sync-Breiten, Polaritäten | **nirgends lesbar**. Treffer in `v4l2_dv_timings_presets[]` bei gleicher aktiver + totaler Geometrie und Takt ±1 % → Preset ganz übernommen (= Stocks Modus-Tabellen-Abgleich, `signal ID=0x20000 index=14`). Kein Treffer → tc358743-Konvention: Austastung ganz in `hsync`/`vsync`, Porches 0 (`v4l2_valid_dv_timings()` nennt genau das) | **erschlossen per Tabelle** bzw. **Konvention**, so benannt |
| `V4L2_DV_FL_REDUCED_FPS` | nur bei Record-Bildrate (5994 gegen 6000) | erschlossen |

Die im Stock-elog gezeigten `hde_start 192`/`vde_start 41` sind genau `hsync+hback` (44+148) und
`vsync+vback` (5+36) von CTA 1080p60 — konsistent mit dem Preset, aber **nicht** vom ARM lesbar. Prüfbar
offline: MIPS-.bss `0x8B253C3C` (= phys `0x4B253C3C`), wohin `CallbackOfSignalChange` die 160 Byte
kopiert — reines Diagnose-Lesen per `/dev/mem`, gehört **nicht** in den Treiber (Firmware-Interna).

---

## 3. Welche Änderung wo

### 3.1 `sun50i-h713-hdmirx.c`

| Stelle | Änderung |
|---|---|
| Kopf, Geometrie-Block | `H713_HDMIRX_PLANE_SIZE` weg; `WIDTH/HEIGHT` bleiben als **Panel** (WCE-Fenster der Init-Sequenz, Anfangsformat). Neu: `struct h713_hdmirx_signal_info` (11 × u32, `static_assert(44)`), `H713_SIGNAL_ID_NONE/UNKNOWN/NOCHANGE`, `H713_INCAP_ACTIVE 0x874`, `H713_INCAP_TOTAL 0x548` |
| `struct h713_hdmirx` | `plane_size` (WRITE_ONCE/READ_ONCE, Vsync-Pfad liest ohne Lock), `incap` (regmap), `sig_lock`, `sig_map`, `sig_map_base`, `sig_phys` (unter `event_lock`) |
| `h713_hdmirx_signal_cb()` | speichert `args[1]` als `sig_phys`; **liest den Record nicht** (Handler bleibt Spinlock-kurz, läuft auf dem cpu_comm-Empfangs-Work und verzögert das ACK) |
| `h713_hdmirx_read_signal_info()` **neu** | `-ENOENT` bis zum ersten Callback des Boots; Bereichsprüfung gegen `shm_base/shm_size`; `ioremap_wc` beim ersten Lesen, 11 × `readl`; MIPS schreibt kseg1 (ungecacht), wir lesen WC → keine Cache-Frage |
| `h713_hdmirx_watch_ring()` **neu**, ersetzt `signal_present()`-Rumpf | zählt Zeigerwechsel (bis `want_flips`, max. `max_ms`), liefert mittlere Periode. `signal_present` = 1 Wechsel in 60 ms (vorher 2 Proben à 20–25 ms) |
| `h713_hdmirx_match_preset()` **neu** | Presets nach (w, h, interlaced, `FRAME_WIDTH`, `FRAME_HEIGHT`, Takt ± Toleranz); Toleranz 1 % (Record) / 5 % (gemessene Rate) |
| `h713_hdmirx_detect_timings()` **neu** | Ablauf §4; Fehlercodes: `-ENOLINK` (keine Frames / Record NONE / Größe 0), `-ENOLCK` (Record ≠ INCAP; INCAP liest 0; ohne Record kein Preset-Treffer), `-ERANGE` (außerhalb Cap), Fehler des regmap |
| `h713_hdmirx_timings_cap` | 640×480 … 1920×1080, 25,175 … 148,5 MHz, `CEA861 | DMT`, `PROGRESSIVE | CUSTOM`; Herleitung im Kommentar (Panel/E3/E4/EDID VIC 1) |
| `h713_hdmirx_set_timings()` **neu** | setzt `timings` + `plane_size` |
| `h713_hdmirx_fill_fmt(rx, pix)` | `v4l2_fill_pixfmt_mp(NV16M, w, h)` aus `rx->timings`; `bytesperline = width` = Ring-Pitch (E4 `+0x924`) |
| `queue_setup`, `buf_prepare`, `slot_event` | Plane-Größe aus `plane_size`; Payload `min(plane_size, vb2_plane_size)` |
| `enum_dv_timings` | `v4l2_enum_dv_timings_cap()` über die Cap |
| `query_dv_timings` | `detect_timings()`; übernimmt das Ergebnis als aktuelles Timing **nur wenn die Queue nicht streamt** (V4L2: Format ändert sich nicht unter laufender Queue; Client stoppt nach SOURCE_CHANGE und fragt neu) |
| `s_dv_timings` | `set_timings()` |
| debugfs | `format:` aus Timings; neu `incap: aktiv WxH, total WxH`; `signal-info` liest den Record (Rohwörter + dekodiert), `-ENOENT` → „noch kein SignalChange in diesem Boot" |
| Probe/Remove | `syscon_regmap_lookup_by_phandle(np, "allwinner,incap")` (Fehler → `dev_err_probe`), `mutex_init(sig_lock)`, `iounmap(sig_map)` in `remove` |
| Includes | `build_bug.h`, `ktime.h`, `math64.h`, `mfd/syscon.h`, `regmap.h` |

### 3.2 `sun50i-h713-afbd.c`

| Stelle | Änderung |
|---|---|
| `h713_afbd_video_atomic_check()` | `ring` vorab lesen; `drm_atomic_helper_check_plane_state(min_scale = ring ? 1 : NO_SCALING, max = NO_SCALING, can_position = false)` → beliebiges Hochskalieren, kein Herunterskalieren, Ziel = ganzer CRTC. Geometrie: `fb ≤ Modus`, `w % 16 == 0`, `h % 2 == 0`, `w,h ≥ 16`, `src = ganzer fb`, `crtc = ganzer Modus`; **ring:** zusätzlich `pitches[0] == width` (Ring-Pitch); **memory-Modus:** weiterhin `fb == Modus`. Die sechs Geometrieregister waren schon immer aus dem fb gerechnet |
| `h713_afbd_publish_video_info(…, bool ring)` | im Ring-Modus wird der Descriptor bei abweichender Geometrie **weder neu geschrieben noch gewarnt** (`refusing to rewrite …` bliebe sonst bei jedem Wechsel im dmesg → Abnahme A6). Begründung: Descriptor = VideoDec-Kanal, Stock-HDMI-Kette ohne Descriptor (doku/91) |

### 3.3 DTS / Kconfig

`incap: syscon@6940000 { compatible = "allwinner,sun50i-h713-incap", "syscon"; reg = <0x06940000 0x1000>; }`
unter `soc` (nach `tvcap@50c0000`); `hdmi-rx` bekommt `allwinner,incap = <&incap>;` — der Knoten bleibt
registerlos, wie sein Kommentar begründet. `syscon_node_to_regmap()` instanziiert bei `"syscon"`
lazy (`drivers/mfd/syscon.c:274`), ohne `request_mem_region`. Kconfig: `depends on MFD_SYSCON` (=y).
**Warum syscon und kein eigenes `reg`:** die Regel „INCAP nie schreiben" (doku/78 §0 Regel 6) ist
mit einem regmap, den niemand beschreibt, Bauform statt Disziplin; und ein späterer INCAP-Treiber
könnte den Block trotzdem beanspruchen.

### 3.4 `hy310-tv` (`hy310-tv.diff`)

| Stelle | Änderung |
|---|---|
| `struct display` | `src_w/src_h` (Puffer = Quelle) neben `width/height` (Panel) |
| `capture_format()` **neu** | `G_FMT` (MPLANE): NV16M, 2 Ebenen, `bytesperline == width` — sonst Warnung, kein Bild |
| `capture_signal()` | `-ENOLCK`/`-ENOLINK`/`-ENODATA` → 0; **`-ERANGE` → 0 mit einmaliger Warnung** („Zeilensprung oder größer als Panel — Konsole bleibt") = Abnahme (c) „definierter Rückfall" |
| `display_create_fb(d, w, h)` | aus der Quellgeometrie; Journal `puffer WxH NV16, Zeilenabstand P` |
| `display_show()` | `SRC_W/H = src`, `CRTC_W/H = Panel`; Journal `bild … WxH aus dem Capture-Ring auf PxQ`; EINVAL-Hinweis angepasst |
| `evaluate()` | QUERY → G_FMT → Plane-Grenzen (`≤ Panel`, `%16`, gerade) → **bei Geometriewechsel: `display_hide` → `destroy_fb` → `create_fb` → `display_show`** (Journal `geometrie A -> B: Plane aus, Puffer neu`) |
| `main()` | kein `display_create_fb` mehr beim Start (baut `evaluate`); die Startzeile `offen …` entfällt, Rest ins README |
| README | Journalbeispiel, Kosten von `QUERY_DV_TIMINGS`, die zwei Absätze zum Auflösungswechsel neu |

---

## 4. Der Ablauf bei einem Wechsel — und das Stummschalten (2.4)

Stock (elog, doku/91): `AV mute:1` bei der **ersten** erkannten Änderung → ~300 ms Erkennung →
Modus-Tabelle → `AV mute:0 1` → `CallbackOfSignalChange` → `WriteModules V_INCAP` → `UpdateWce`
(`rowbyte = Breite/16`) → `AV mute:0 0` → **erst dann** `NotifySignalChange` nach außen.

Unser Gegenstück, in dieser Reihenfolge:

1. Firmware erkennt und baut um — **dieselbe Firmware, ohne unser Zutun** (E4: Register; A6-4-Bild:
   921 600 Byte Neuinhalt = 720 × 1280 **ohne** Quellenwechsel, siehe §7 Nr. 1).
2. `NotifySignalChange` → `MipsHalCallback_SignalChange(3, ptr)` → Kernel: `sig_phys`, `SOURCE_CHANGE`.
3. `hy310-tv`: `QUERY_DV_TIMINGS` → Record ≠ alte Geometrie → `G_FMT` → **Plane aus** (Konsole,
   Mux auf RGB, `video_stop`) → Puffer neu → **Plane an** (Geometrieregister aus dem fb: 1280×720,
   Y-Stride 1280, C-Stride 2560, Crop). Kein Descriptor-Neuschreiben, kein Rearm (Descriptor unverändert
   → `published = false`).
4. Wenn der Record vor der Firmware-Neuprogrammierung mit `NONE` kommt (Stock tut das beim
   Quellenwechsel: `NotifySignalChange` mit `kHalSignalID_NONE`), fällt die Plane schon **vor** dem Umbau
   auf die Konsole — das entspräche Stocks `AV mute:1` am Anfang. **Nicht gemessen** (§5 M1).

Was wir **nicht** tun: eine kernelseitige Stummschaltung bei Geometriewechsel (afbd kennt die
Capture-Geometrie nicht; hdmirx müsste afbd „Ring nicht folgen" sagen). Ich habe das bewusst nicht
gebaut: erst M1 zeigt, ob zwischen Firmware-Umbau und unserem `display_hide` überhaupt zerrissene
Bilder auf die Wand kommen. Falls ja, ist der kleinste Eingriff ein Aufruf `h713_afbd_ring_hold()` aus
`h713_hdmirx_signal_cb()`, wenn `h_size/v_size` im Record von `rx->timings` abweichen.

**Erster Boot-`QUERY` ohne Record:** die Callbacks werden erst beim `open()` angemeldet (0100), die
Firmware schickt den Record nur bei Änderung → der erste Record eines Boots geht strukturell verloren
(die 44 Byte stehen im Shmem, aber `Para[1]` fehlt). Deshalb der Rückfallpfad INCAP-Geometrie +
Flip-Rate, **nur mit Preset-Treffer** (kein Scan-Typ raten). Alternative wäre ein SetSource-weg/zurück
beim ersten `open()` — dass das einen Callback auslöst, ist auf unserem Board **nicht** belegt (§5 M6);
deshalb nicht gebaut.

---

## 5. Ungeklärt — je eine Messung, die scheitern kann

| | Frage | Messung (Board, kein Bau nötig außer wo gesagt) | Scheitert, wenn |
|---|---|---|---|
| **M1** | Feuert `SignalChange` bei **reinem** Geometriewechsel? Kommt zuerst `NONE`? (= 2.2) | heutiger Kernel: `hy310-tv` läuft, debugfs `SignalChange: N mal` notieren, `xrandr --mode 1280x720` **ohne** Quellenwechsel, 3 s, debugfs erneut + elog (`numActiveLines is changed`, `UpdateWce`, `m_psu_rowbyte_y:80`, `NotifySignalChange`) | Zähler unverändert **oder** elog ohne `NotifySignalChange` → dann trägt der ganze ereignisgetriebene Weg nicht |
| **M2** | Folgt die Composition der Quelle? (2.3, Skalierfrage) | `dump_state.py` bei 1080p und nach dem Wechsel auf 720p: `0x05000174` (erwarte ≠ `0x00600060`), `0x05000444/0x05000544` (erwarte `0x02d00500`), `0x05000844` (Pitch ≠ 1920) | Werte bleiben 1080p-1:1 → die Plane zeigt 1280×720 „irgendwo", nicht vollflächig; dann muss die Composition von uns programmiert werden (nicht stock-konform, Beweislast bei uns) |
| **M3** | Schreibt die Firmware bei ihrem HDMI-`UpdateWce` AFBD-Source-0-Register, insbesondere `0x05600044` (C-Stride)? | mit 0105: Plane bei 720p an, `0x05600044` lesen; erwarte `0xA00` (2560, unser NV16-Doppel) | liest `0x500` (1280) → Firmware hat nach uns geschrieben → Chroma 2× gestreckt; dann braucht der Wechsel dasselbe `wait_wce`-Bracket wie D-cstride |
| **M4** | Rückfallpfad ohne Record: liefert `QUERY` nach Kaltstart + `open()` (vor jedem Callback) 1080p60? | `v4l2-ctl --query-dv-timings` als **erster** Aufruf nach Boot; debugfs `signal-info: noch kein SignalChange` muss dabei stehen | `-ENOLCK` obwohl Flip-Zeiger laufen → Flip-Rate zu grob oder INCAP-Wort anders belegt; dann `hy310-tv` beim Start ohne Bild |
| **M5** | Kommen Record-Werte an wie in Stock (`h_size 0` bei NONE, `6000`, `1920×1080`)? (= 2.1 „kann scheitern") | debugfs `signal-info` nach Zuspieler aus/an; Rohwörter gegen §1 | Wort 5/6 ≠ INCAP-Geometrie → Layout falsch, `detect` antwortet dauernd `-ENOLCK` |
| **M6** | Löst SetSource weg/zurück (Rearm) auf **unserem** Board `SignalChange` aus? | debugfs-Zähler vor/nach einem Plane-Einschalten mit neuem Descriptor (Kaltstart, erstes `hy310-tv`) | Zähler +0 → Stock-Kette `hal_source_id: 3 → NotifySignalChange` gilt hier nicht; Startfluss dann nur über M4 |
| **M7** | 1600×1200 (EDID-Std-Timing, Panel überschritten) → definierter Rückfall? (Abnahme c) | `xrandr --mode 1600x1200`; erwarte `-ERANGE`/`-ENOLCK` → Konsole, Journal einmalig „nicht annimmt" | Müll auf der Wand **oder** Plane akzeptiert (dann `atomic_check`-Grenze falsch) |
| **M8** | Stimmen die Preset-Porches? (optional, offline am Board) | `/dev/mem` `0x4B253C3C+0x?` (172-Byte-Struktur, `hdmi.timing.hde_start/vde_start`) bei 720p lesen; erwarte 260 (40+220) / 25 (5+20) | andere Werte → Zuspieler fährt kein CTA → tc358743-Pfad wäre ehrlicher als der Preset |

Gesamtabnahme wie in doku/91: 1080p → 720p → 1080p → 1600×1200, Rekonstruktion bei 720p pixelgenau,
`stray = 0`, Gegenprobe mit deaktiviertem Auslöser (z. B. `hy310-tv` ohne `SOURCE_CHANGE`-Reaktion) muss
das zerrissene Bild wieder erzeugen. Zusätzlich A6: `dmesg` ohne `refusing to rewrite` — dafür sorgt
3.2.

---

## 6. Was ich NICHT belegen konnte

1. **Dass der Callback bei reinem Geometriewechsel kommt** (M1). Das ist die Voraussetzung für den
   ganzen ereignisgetriebenen Weg, und A6-4 hat ohne angemeldeten Callback gemessen.
2. **Dass die Composition mitgeht** (M2). doku/91 sagt „keine Skalierer-Frage" — das folgt aus der
   Stock-Kette (`UpdateWce → CalcWindow je Knoten`), nicht aus einer Messung an `0x0500xxxx` bei 720p.
   E4s Abzüge enthielten den `DE0`-Block (`dump_state.py`), wurden aber nicht ins Repo gelegt; ich
   konnte sie nicht nachlesen.
3. **Dass die Firmware unsere AFBD-Source-0-Register in Ruhe lässt** (M3).
4. **Numerische Werte der CE-`kHalSignalID`s** — nicht aufgelöst, für den Treiber unnötig.
5. **Ob `frame_rate_x100` bei 59,94 Hz `5994` liefert** — nur `6000` und `3000` in den Mitschnitten.
6. **Ob SetSource weg/zurück einen Callback liefert** (M6) — Stock ja (elog 7983–8028), wir ungemessen.
7. **Dass der Rückfallpfad (INCAP + Flip-Rate) am Gerät 1080p60 liefert** (M4) — reine Konstruktion aus
   E4-Registerwerten und der 60-Hz-Rotation (A6-4 `+61/s`).
8. **Kompilierbarkeit.** Nicht gebaut (Regel 3). Zweimal gegen die Header gelesen: `v4l2_fill_pixfmt_mp`,
   `v4l2_enum_dv_timings_cap`, `v4l2_valid_dv_timings`, `v4l2_dv_timings_presets[]`,
   `V4L2_DV_BT_FRAME_WIDTH/HEIGHT` (nehmen Zeiger), `drm_atomic_helper_check_plane_state`
   (min_scale 1 = beliebiges Hochskalieren, `can_position=false` erzwingt „Plane must cover entire
   CRTC"), `syscon_regmap_lookup_by_phandle`, `regmap_read(…, unsigned int *)`, `div_u64/div64_u64`,
   `ktime_ms_delta`. Stellen mit dem höchsten Restrisiko: `static_assert` am Dateiende des
   Deklarationsblocks (kommt über `linux/build_bug.h`), `(void)o` in `evaluate()`.

---

## 7. Nebenbefunde

1. **A6-4s Bild belegt den Firmware-Umbau ohne Quellenwechsel.** `frame720.png` (1920 breit
   rekonstruiert) hat oben **480** Zeilen Neuinhalt = 921 600 Byte = **720 × 1280**; drei versetzte
   Kopien mit Periode 640 sind genau das Muster von 1,5 Quellzeilen je 1920er-Zeile. Damit ist E3s Satz,
   erst der Quellenwechsel bringe „die Firmware auf die neue Geometrie", zu eng: der Ring war schon
   umgebaut, nur `0x928` wurde davor nicht gelesen. Erschlossen aus dem Bild, nicht gemessen.
2. **Unser EDID verspricht mehr, als die Kette liefert:** Std-Timing 1600×1200@60, VICs 93/94/95/98/100
   (2160p24/25/30, 4096×2160), Max-TMDS 340 MHz (`analyse/arisc/hy310-edid.bin`). E3: 1600×1200 und
   1920×1200 rasten nicht ein / Ausgabe aus. Für die Abnahme (c) relevant; für die Cap habe ich das Panel
   genommen, nicht das EDID.
3. **`doku/83`/`doku/88` „Para[2]"** und **debugfs `signal_args[2]`** — siehe §0 Nr. 2; im Patch korrigiert.
4. **`doku/84` „+16"** — siehe §0 Nr. 3.
5. **Plan-Tabelle „Reihenfolge"** zitiert `display_show(d, o->saturation)` bei `main.c:980` — seit 0104
   heißt es `display_show(d)`; die Argumentation (jedes `hide/show` zerstört den Gain) ist mit 0104
   erledigt, der Patch baut darauf auf.
6. **`INCAP` liest 0, wenn TVFE/TVCAP stromlos** (doku/78:53). `detect_timings()` meldet das
   ratelimited und antwortet `-ENOLCK`. Voraussetzung A0 des Plans (`h713-tvcap` in der Serie) bleibt.
7. **Farbmetrik:** der Record trägt `color_space`/`b_full_range` — eine spätere ehrliche Belegung von
   `colorspace/quantization` im Format ist damit möglich; jetzt unverändert `REC709/LIM_RANGE`
   (das ist die INCAP-CSC-Ausgabe, nicht das Eingangsformat).
