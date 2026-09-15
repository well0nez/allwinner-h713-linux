# Paket D - Video-Plane auf den HDMI-Capture-Ring (NV16)

Agent: D. Kein Board angefasst (Board-Agent = Hauptsitzung, Koordination Punkt 1). Uhrzeiten vom
Arbeitsrechner (`date '+%H:%M'`).

---

## 1. Ergebnis in einem Absatz

`mainline/patches/kernel/0093-drm-h713-afbd-nv16-hdmi-ring.patch` (35 594 B) macht aus cstengers
1280×720-NV12-Plane eine benutzbare Plane: Geometrie aus dem Framebuffer, zusätzlich **NV16** über einen
verdoppelten Chroma-Zeilenabstand statt eines Formatwechsels, Adressen wahlweise aus dem Capture-Ring
(Plane-Eigenschaft `hdmi-ring`), VidDec-Descriptor **einmal pro Boot** beim Enable und beim Disable nicht
zurückgenommen, Chroma-Gain als Plane-Eigenschaft `saturation`. Prüfbau grün, `W=1` warnungsfrei, DTB baut
ohne DTC-Meldung, Modul linkt. Testprogramm `analyse/kms/hdmi_plane_test.c` übersetzt sauber gegen das
libdrm des Boards. **Nicht** in `series` eingetragen (Koordination Punkt 3).

---

## 2. Zeitleiste

| Zeit | Schritt |
|---|---|
| 22:05 | Nachtplan §0/§0b/§1/§3D/§7, doku/76 §§10-13, `nachtlog/00-koordination.md`, `nachtlog/A-patches.md` gelesen |
| 22:07 | Registerabzüge `ours-20260906-source0/01_lock … 05_after_hpd` ausgewertet (Geometrie-Formeln, Flip-Zeiger-Paare) |
| 22:08 | Prüfbau-Kopie des A-Baums angelegt (`cp -a`, 2,1 GB) |
| 22:09-22:13 | Treiber und `sun50i-h713.dtsi` in einer Arbeitskopie geändert |
| 22:14 | Prüfbau: `sun50i-h713-afbd.o` **grün**, `dtbs` **grün**, `modules` **grün** (MODPOST ohne fehlende Symbole) |
| 22:15 | `W=1` auf der Treiberdatei: **keine Warnung** |
| 22:16 | Patch 0093 erzeugt und gegen einen frisch entpackten Baum + komplette `series` (67 Patches) **dry-run geprüft: sauber** |
| 22:18 | `analyse/kms/hdmi_plane_test.c` geschrieben, quer übersetzt (clang → aarch64, libdrm des Boards): **grün, `-Wall -Wextra` warnungsfrei** |
| 22:21 | `doku/86-video-plane-nv16.md` geschrieben |
| 22:22 | `analyse/kms/README.md` → `README-hdmi-plane.md` umbenannt (siehe §7 Punkt 3) |

---

## 3. Was NV16 konkret anders macht

Source 0 hat genau **einen** linearen Leser, und der ist ein NV12-Leser: für Ausgabezeile *r* holt er
Chromazeile ⌊r/2⌋. NV16 hat pro Bildzeile eine Chromazeile - mit einfachem Zeilenabstand liegt die Farbe
deshalb vertikal 2× gedehnt über dem Bild. Verdoppelt man den Chroma-Zeilenabstand, ist die Chroma-Adresse für
Zeile *r* gleich ⌊r/2⌋ × 2 × pitch = Zeile *r* des NV16-Puffers. Damit:

```
+0x010  Bits [14:8] = 0        Formatcode 0 - für NV12 und NV16 gleich
+0x040  = fb->pitches[0]       Y-Stride    (1920 = 0x780)
+0x044  = 2 × pitch bei NV16   C-Stride    (3840 = 0xF00)   <-- der einzige Unterschied
+0x048  = (h << 16) | w        Luma-Crop   (0x04380780)
+0x04C  = ((h/2) << 16) | w    Chroma-Crop (0x021C0780) - halbe Höhe AUCH bei NV16
```

Der Formatcode-Weg (`0x03000213`) ist gemessen und falsch (Luma-Geometrie zerfällt, Bild grün,
`fotos/f422.jpg`). Vollständige Herleitung und Registertabelle: `doku/86-video-plane-nv16.md`.

**Geometrie.** Die beiden Wörter werden jetzt gerechnet statt verdrahtet:

```
+0x020 = ((align16(h) − 1) << 16) | (w − 1)
+0x024 = ((h/16 − 1)      << 16) | (w/16 − 1)
```

Beide Formeln treffen **beide** bekannten Registersätze exakt: 1280×720 → `0x02cf04ff` / `0x002c004f`
(cstengers Konstanten) und 1920×1080 → `0x043f077f` / `0x00420077` (was die Firmware für die Capture setzt,
`03_source0.txt`). Bei 1080 rundet `+0x024` ab (67 Blockzeilen), `+0x020` auf (1088) - genau so steht es im
Abzug.

**Ring-Folge.** Im Vsync: `+0x320` / `+0x324` / `+0x320` lesen (zerrissenes Paar verwerfen), gegen die Grenzen
von `mips_framebuf` prüfen, bei neuem Y die vier Y- und C-Slots schreiben und `+0x06C = 1`. Neun
Schreibzugriffe, keine INCAP, kein `+0x300/+0x304/+0x310`. Die Plane hält dafür eine Vblank-Referenz.

**Descriptor.** Inhalt byteweise wie `analyse/hdmi-seq/viddec_descriptor.py` (Magic `0x61770000`, Typ 2,
1920×1080, Stride 1920, `color_format` 0, HDR-Zeiger NULL). Er wird beim **ersten** Enable veröffentlicht, und
nur, wenn die Seite nicht ohnehin schon genau diesen Inhalt hat - der Vergleich macht auch ein Modul-Neuladen
ungefährlich. Beim Disable bleiben `+0x098…+0x0A4` stehen.

**Descriptor-Seite.** Neu und wichtig: die Seite kommt aus dem DT, nicht aus dem DMA-Pool. Begründung im
Klartext - der Descriptor hat einen zweiten Leser, der kein Busmaster ist. Die MIPS liest ihn durch ihr eigenes
DRAM-Fenster (ARM `0x4Bxxxxxx` = MIPS `0x8Bxxxxxx`); der System-CMA-Pool liegt auf diesem Board bei
`0x7DC00000` (`re/captures/nfsboot.log`: „cma: Reserved 16 MiB at 0x000000007dc00000") und **kommt in diesem
Fenster nicht vor**. Deshalb:

```
decd_reserved  decoder@4d941000      0x4d941000 + 0x1e000   (120 KB statt 128 KB)
viddec_info    viddec-info@4d95f000  0x4d95f000 + 0x2000    (die Stock-Adresse)
```

Die Gesamtausdehnung der Reservierung ändert sich nicht (`4d941000…4d960fff`, wie `/proc/iomem` sie zeigt);
`dec@5600000` ist bei uns `disabled`, der Knoten hat sonst keinen Nutzer. Der Display-Knoten bekommt

```
memory-region       = <&mips_framebuf>, <&viddec_info>;
memory-region-names = "hdmi-ring", "viddec-info";
```

Weil damit `memory-region[0]` belegt ist, sucht der Treiber den Scanout-Pool jetzt **über den Namen**
(`of_reserved_mem_device_init_by_name(..., "scanout")`). Es gibt keinen solchen Eintrag → Framebuffer kommen
weiter aus dem System-CMA, exakt wie bisher. Im DTB geprüft: `memory-region = <0x24 0x25>` mit `0x24` =
`framebuf@4bf41000`, kein `iommus` am Display.

---

## 4. Prüfbau (ausdrücklich Prüfbau, kein Serienbau)

Baum: **Kopie** des A-Baums, `mainline/build/pruefbau-D-linux-6.18.38`. Der Originalbaum
`linux-6.18.38-7dff124db0ddefd2bef7f9028ad2bbeaac2f7af7ad50a8fcfbc4226df6088d55` ist **nachweislich
unverändert** (`cmp` gegen eine vor der Arbeit gezogene Kopie beider Dateien: identisch; DTB-Zeitstempel
weiterhin 21:48). `build/build.sh` wurde nicht aufgerufen, `series` nicht angefasst.

```bash
podman exec h713-build bash -lc 'cd /work/mainline/build/pruefbau-D-linux-6.18.38 && \
    make ARCH=arm64 LLVM=1 -j"$(nproc)" drivers/gpu/drm/tiny/ dtbs modules'
```

| Prüfung | Ergebnis |
|---|---|
| `CC [M] drivers/gpu/drm/tiny/sun50i-h713-afbd.o` | grün, keine Warnung |
| dasselbe mit `W=1` | grün, **keine Warnung** |
| `DTC sun50i-h713-hy200-qz713df-a1.dtb` + `…-v2.dtb` | grün, keine DTC-Meldung |
| `MODPOST` + `LD [M] sun50i-h713-afbd.ko` | grün - alle benutzten Symbole exportiert (`devm_memremap`, `of_reserved_mem_device_init_by_name`, `of_address_to_resource`, `drm_property_create_range`, `__drm_atomic_helper_plane_*`, `drm_crtc_vblank_get/put`) |
| Modul | 28 632 B |
| `patch -p1 --dry-run` gegen frischen Tarball + volle `series` (67 Patches) | sauber; dtsi-Hunk 2 mit Offset +26 (0096 hat davor Zeilen eingefügt), sonst ohne Fuzz |

Die Kopie darf gelöscht werden (`mainline/build/pruefbau-D-linux-6.18.38`, ~2,1 GB); `build/build.sh` findet
sie nicht, weil sie nicht `linux-<version>-<digest>` heißt.

---

## 5. Abnahmevorschrift (kopierbar, für die Hauptsitzung)

> **Nachtrag 07.09., 06:25 - diese Vorschrift ist an zwei Stellen überholt.** Sie stammt von vor zwei
> Erkenntnissen der Nacht; wer sie wörtlich fährt, bekommt kein Bild.
>
> 1. **`prep_after_boot.sh` → `prep_clean.sh`.** Mit Patch `0091` im Kernel lädt und quittiert der
>    ARISC-Treiber selbst. Das alte Rezept lädt den Blob ein zweites Mal und schickt eine zweite Quittung.
>    `prep_clean.sh` erkennt den Kerneltreiber inzwischen selbst und lässt die Alt-Schritte weg.
> 2. **Nach dem Plane-Enable fehlt die Freigabe.** Der Descriptor - den die Plane beim Enable schreibt -
>    schaltet die Capture ab (`0x06940928` Bit 31 → 0). Ohne Freigabe steht der Ring und die Plane zeigt
>    einen Standrahmen. Zwei belegte Wege, beides Stock-RPCs: **Quellenwechsel** (`SetSource` weg und
>    zurück, `B2-quellenwechsel.md`) oder **HPD-Zyklus** (0,3 s genügen, `M4-hpd-dauer.md`).
>
> Der durchgeführte, grüne Ablauf steht in [`D-abnahme-board.md`](D-abnahme-board.md).
> Dort steht auch der dabei gefundene Fehler: beim **ersten** Enable nach einem Kaltstart schreibt der
> Treiber den NV16-C-Stride `0x05600044` **nicht** (bleibt `0x0780` statt `0x0F00`) - die Farbe quillt dann
> aus ihren Kanten.

**Voraussetzung:** 0093 in `series` (nach 0090 bzw. hinter dem, was B/C/H liefern - Reihenfolge siehe §7
Punkt 1), Netboot-FIT gebaut und ausgerollt, Modul auf dem Board. Sperre halten.

```bash
# --- 0. Werkzeug bauen (einmalig; Board-Root hat gcc-14 + libdrm-Header) -----
cp /opt/Projekte/h713/analyse/kms/hdmi_plane_test.c /srv/h713-rootfs/root/
ssh root@192.168.8.141 'gcc -O2 -Wall -o /root/hdmi_plane_test /root/hdmi_plane_test.c \
    $(pkg-config --cflags --libs libdrm)'

# --- 1. Kaltstart -----------------------------------------------------------
ss -ulnp | grep -w :69                                   # TFTP muss lauschen, sonst STOPP
sonoff_ctl restart --host 192.168.8.179                  # ~40 s bis SSH
for i in $(seq 30); do ssh -o BatchMode=yes -o ConnectTimeout=3 root@192.168.8.141 uptime && break; sleep 4; done

# --- 2. Prep, SetSource, EDID  (Nachtplan Abschnitt 1, woertlich) -----------
ssh root@192.168.8.141 'bash /root/prep_after_boot.sh'
ssh root@192.168.8.141 'taskset -c 1 python3 /root/hdmi_seq.py run --phase 4 --i-mean-it --only setsource \
     --source 3 --portmap stock --gap 500 --pre-source-wait 1 --listen-after 3'
ssh root@192.168.8.141 'bash /root/arisc_edid_init.sh'   # ~30 s, enthaelt HPD down 10 s
sleep 6                                                   # Signal-Lock; INCAP 0x06940104 zaehlt 60/s

# --- 3. AB HIER OHNE viddec_descriptor.py UND OHNE afbd_source0.py ----------
ssh root@192.168.8.141 'dmesg | grep -i afbd'            # erwartet: "adopting 1920x1080, stride 7680"
ssh root@192.168.8.141 'python3 /root/dump_state.py D_vor'
ssh root@192.168.8.141 'timeout 60 /root/hdmi_plane_test -t 45' &   # haelt das Bild 45 s
sleep 8
python3 /opt/Projekte/h713/analyse/hdmi-seq/wandcheck.py shot D-plane-ring
ssh root@192.168.8.141 'python3 /root/dump_state.py D_an'
wait
```

**Erwartet:**

* `hdmi_plane_test` druckt `device /dev/dri/card0 (sun50i-h713-afbd)`, `plane <ID>, format NV16, mode
  hdmi-ring (capture)`, dann `plane is up. Holding.`
* Auf der Wand: das Zuspielerbild **in Farbe**, richtige Geometrie, **die Uhr läuft**.
  Foto gegen `re/captures/weltneuheit/ours-20260906-source0/fotos/cstride.jpg` halten - Spirale
  deckungsgleich im Rahmen, Regenbogenfarben voll, Weiß neutral, Rot rot.
* In `D_an` gegen `03_source0.txt`: `0x05600010 = 0x03000013`, `0x05600040 = 0x00000780`,
  **`0x05600044 = 0x00000f00`**, `0x05600048 = 0x04380780`, `0x0560004c = 0x021c0780`,
  `0x05600020 = 0x043f077f`, `0x05600024 = 0x00420077`, `0x05600068 = 0x00000122`,
  `0x05600098 = 0x4d95f000`, `0x05140508 = 0x144c0000`, `0x051c006c = 0x39000000`.
  `0x05600070` und `0x05600084` zeigen jetzt auf **einen wechselnden** Ring-Slot (nicht mehr fest
  `0x4c3ef000`/`0x4c9ec000`) - das ist die Ring-Folge und der sichtbare Unterschied zu `afbd_source0.py`.
* Nach dem Programmende: `plane is off, console restored.` und die Konsole steht wieder auf der Wand.

**Robustheit (Marcos Anforderung aus doku/76 §11.7):**

```bash
ssh root@192.168.8.141 'timeout 120 /root/hdmi_plane_test -t 110' &
sleep 10
ssh user@192.168.8.162 'DISPLAY=:0 xrandr --output HDMI-2 --off'; sleep 6
python3 /opt/Projekte/h713/analyse/hdmi-seq/wandcheck.py shot D-quelle-aus
ssh user@192.168.8.162 'DISPLAY=:0 xrandr --output HDMI-2 --auto'; sleep 10
python3 /opt/Projekte/h713/analyse/hdmi-seq/wandcheck.py shot D-quelle-an
wait
```

Erwartet: Bild kommt von selbst zurück, gleiche Qualität wie vorher.

**Positivkontrolle, falls kein Bild kommt** (vor jeder Negativaussage, Memory
`messung-instrument-erst-pruefen`):

```bash
ssh root@192.168.8.141 'timeout 40 /root/hdmi_plane_test --pattern -t 30' &
sleep 8
python3 /opt/Projekte/h713/analyse/hdmi-seq/wandcheck.py shot D-farbbalken
wait
```

Acht Farbbalken auf der Wand ⇒ Plane, Mux, Chroma-Weg und Panel sind in Ordnung, der Fehler liegt auf der
Capture-Seite. Keine Balken ⇒ der Fehler liegt in der Plane.

**Sättigung** (Paket G rechnet die Bytes, `hy310-pq saturation HDMI1 <modus>`):

```bash
ssh root@192.168.8.141 'timeout 40 /root/hdmi_plane_test -s 92 -t 30'    # 0x5C = vivid
```

**Wenn etwas schiefgeht - was welche Meldung bedeutet:**

| Meldung | Bedeutung |
|---|---|
| `no overlay plane on this CRTC advertises NV16` | 0093 ist nicht im laufenden Kernel |
| commit `EOPNOTSUPP` | `memory-region-names` fehlt am Display-Knoten (DTB prüfen) |
| commit `EINVAL` | Framebuffer-Geometrie ≠ Modus, oder Breite nicht durch 16 teilbar |
| dmesg `refusing to rewrite the VidDec descriptor` | Zweiter Enable mit anderer Geometrie - genau die Bremse, die eingebaut ist. Kaltstart. |
| Bild steht (Uhr friert), Geometrie richtig | Der Dirty-Latch reicht pro Vsync nicht; siehe doku/86 §8 Punkt 2. **Nicht mit `msleep` oder Wiederholungen zudecken**, sondern melden. |

**Was in dieser Vorschrift bewusst NICHT vorkommt:** `viddec_descriptor.py` (macht der Treiber),
`afbd_source0.py` (macht der Treiber), INCAP-Schreibzugriffe (nie), Kamera-Belichtung (bleibt `auto`).

---

## 6. Board-Anfrage

Ein Board-Slot, Slot 4 der Nachtreihenfolge, ~20 Minuten inkl. Kaltstart. Abnahme wörtlich wie §5.
Ergebnisse nach `re/captures/weltneuheit/ours-20260907-nacht/D/`.

---

## 7. Offene Punkte und Warnungen an die Hauptsitzung

1. **0093 und 0095 kollidieren in `drivers/gpu/drm/tiny/sun50i-h713-afbd.c`.** Beide sind gegen denselben
   A-Baum erzeugt. Überlappende Stellen (Zeilennummern im A-Stand):
   * ~363-383 - `h713_afbd_video_funcs` (ich ersetze reset/duplicate/destroy und hänge die
     Property-Callbacks an) gegen 0095s Einschub direkt dahinter;
   * ~557-573 - Kopf von `h713_afbd_probe` (ich: `spin_lock_init`, zwei Deklarationen; 0095: `gamma`-ioremap);
   * ~714-720 - nach `drm_plane_helper_add` (ich: `create_properties`; 0095: Color-Management-Init).

   Alle drei sind rein additiv und von Hand in Minuten zusammenzuführen. Im **dtsi** kollidieren die beiden
   *nicht*: 0095 ändert `reg`/`reg-names`, ich hänge `memory-region`/`memory-region-names` hinter
   `clock-names` - nur Kontextüberlappung. Vorschlag: **0093 zuerst** (sichtbarer Meilenstein), 0095 danach
   nachziehen.
2. **`series`:** 0093 ist **nicht** eingetragen (Koordination Punkt 3). Nummer laut Nummernvertrag korrekt.
   Als die dry-run-Probe lief, hatte `series` 67 Zeilen (0096/0097 waren dazugekommen); 0093 wendet darauf
   sauber an.
3. **`analyse/kms/README.md`:** Ich habe um 22:19 eine `README.md` in dieses Verzeichnis geschrieben und sie
   um 22:22 nach `README-hdmi-plane.md` umbenannt, weil Paket H dasselbe Verzeichnis benutzt
   (`gamma_test.c`, `pruefbau-H/`). Falls H dort vorher schon eine `README.md` abgelegt hatte, ist sie durch
   meinen Schreibvorgang überschrieben worden - bitte gegebenenfalls von H neu anlegen lassen. Meine Datei
   heißt jetzt eindeutig nach dem Programm und steht keinem mehr im Weg.
4. **`+0x030`** wird nicht geschrieben (Firmware-eigen, auf unserem Board richtig). Für einen Framebuffer
   anderer Größe wäre zu klären, ob er mitgezogen werden muss.
5. **K3 bleibt die Grenze.** Der Treiber weicht dem Problem aus (Descriptor einmal pro Boot), löst es nicht.
   Solange K3 offen ist, kann eine Plane, die einmal mit 1920×1080 lief, in demselben Boot keine andere
   Quellgeometrie annehmen - sie sagt das dann per `drm_warn`, statt heimlich umzuschalten.
6. **`hdmi-ring` ist ein Übergang.** Die Eigenschaft verschwindet, sobald Paket E die drei Ring-Slots als
   dma-bufs herausgibt; dann ist die Plane eine ganz gewöhnliche NV16-Plane.

---

## 8. Dateien

| Datei | Was |
|---|---|
| `mainline/patches/kernel/0093-drm-h713-afbd-nv16-hdmi-ring.patch` | Treiber + `sun50i-h713.dtsi`, `diff -ruN`-Form |
| `analyse/kms/hdmi_plane_test.c` | libdrm-Testprogramm |
| `analyse/kms/README-hdmi-plane.md` | Bauanleitung (Board nativ und quer) + Fehlermeldungstabelle |
| `doku/86-video-plane-nv16.md` | Registersatz mit Begründung je Wert, Ablauf, Ring-Folge, Latch/W1C/Firmware-Bits, Verhältnis zu 0078 |
| `mainline/build/pruefbau-D-linux-6.18.38/` | Prüfbau-Kopie, löschbar |
