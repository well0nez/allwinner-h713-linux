# Gamma und Weißabgleich als KMS-Eigenschaften am H713-AFBD-CRTC

**Stand 07.09.2026 - am Gerät abgenommen (Abschnitt 0).** Diese Seite beschreibt, was der Patch
`mainline/patches/kernel/0095-drm-h713-afbd-color-mgmt.patch` tut: er meldet am CRTC des Treibers
`sun50i-h713-afbd` die Standard-Farbverwaltung von KMS an - **`GAMMA_LUT`** auf die drei DE2-Bänke und
**`CTM`** auf die Weißabgleich-Gains - und schreibt die Bänke in genau der Reihenfolge, die die Stock-Firmware
benutzt. Vorlage: Nachtplan [doku/78](78-nachtplan-hdmi-switch.md) Abschnitt 3 „H",
[doku/77](77-plan-hdmi-integration.md) §4, [doku/76](76-plan-ch0-de.md) §13,
`legacy/userspace/hy310-pqd/BACKGROUND.md` §5. Die Kurve selbst rechnet **Paket G**
(`userspace/h713-pq/`, [doku/81](81-pq-datenmodell.md)); dieser Patch rechnet keine Kurve, er transportiert sie.

---

## 0. Stand am Gerät

**Abgenommen am 07.09.2026, 06:12-06:14** ([nachtlog/H-abnahme-board.md](nachtlog/H-abnahme-board.md)):
Kaltstart, nur die Konsole auf der Wand - kein HDMI, kein Descriptor, keine Capture.

```
CRTC 36: GAMMA_LUT_SIZE 1024, CTM vorhanden
```

| Aufnahme | mean | std | hell | dunkel |
|---|---|---|---|---|
| `H-vorher` (Konsole, schwarz) | 18,8 | 9,4 | 108 | 451 271 |
| `H-invertiert` | **197,4** | 47,3 | **420 780** | **280** |
| `H-nachher` | 18,9 | 9,5 | 146 | 451 270 |

| Vergleich | Ergebnis | Kriterium aus `H-gamma.md` |
|---|---|---|
| vorher → invertiert | **100,00 %** der Bildpunkte > 25 (mean 178,61) | > 50 % |
| vorher → nachher | **0,00 %** (mean 0,99) | < 10 % |

Beide Kriterien konnten scheitern: die Rückkehr auf 0,00 % ist die Gegenprobe dazu, dass nicht irgendetwas
anderes das Bild verändert hat.

### Die wichtigste Änderung an dieser Seite: die Stufe färbt **beide** Pfade

Bis zum 07.09. stand hier (§9 und §10) als ungetestet, „ob die Gamma-Stufe auch den Video-Pfad (Source 0)
einfärbt oder nur den RGB-Pfad". **Sie färbt beide.** Gemessen um 06:20, Selektor während der ganzen
Messung auf `0x39000000` = Video:

| Aufnahme | mean | std | hell | dunkel |
|---|---|---|---|---|
| `HV-03` Video, normale LUT | 131,1 | 48,8 | 252 100 | 41 827 |
| `HV-04` Video, **invertierte LUT** | 88,5 | 69,4 | 103 286 | 254 773 |

**86,56 % der Bildpunkte > 25** (mean 68,33); auf dem Foto ist es eindeutig dasselbe Bild als Negativ
(weiße Seite → schwarz, rote Felder → türkis). Dass es 86,56 % und nicht 100,00 % sind, ist Bildinhalt und
kein Effekt: die Konsole ist fast einfarbig schwarz und invertiert vollflächig, das Videobild hat helle wie
dunkle Anteile.

**Für Paket I heißt das:** Gamma und Weißabgleich sind für den HDMI-Eingang nutzbar, ohne dass am Mux
`0x051C006C` etwas geändert werden muss.

### Zwei Instrumentenfallen, beide beim ersten Versuch zugeschnappt

1. **`gamma_test` braucht den DRM-Master.** Läuft die KMS-Video-Plane (`hdmi_plane_test` hält den Master),
   meldet es `kein DRM-Master (laeuft ein Compositor?): Permission denied`. Die dabei gemessenen
   **0,00 %** sind **keine Aussage** - das Werkzeug ist gar nicht gelaufen. Die gültige Messung lief
   deshalb über den Skriptpfad (`afbd_source0.py on` schreibt die Register direkt und braucht keinen
   Master). **Folge, die bleibt:** Farbe und KMS-Video-Plane sind mit den heutigen Werkzeugen nicht
   gleichzeitig zu bedienen; wer beides zugleich will, braucht ein Programm, das Plane und Farbe im selben
   DRM-Master setzt.
2. **Nach dem Zurücksetzen ein paar Sekunden warten.** Die Aufnahme unmittelbar nach der Meldung
   `zurueckgesetzt.` wich um 96,93 % ab - sie fiel mitten in den Rücksetzvorgang. Drei Sekunden später
   stand das Ausgangsbild wieder. Wer direkt danach misst, misst den Übergang.

**Unverändert ungeprüft:** `CTM` gegen Stock (§9) - daran hat die Abnahme nichts geändert, und es gibt
weiterhin keinen Vendor-Fall, gegen den man vergleichen könnte.

---

## 1. Registersatz

Alles physische ARM-Adressen. Die ersten beiden liegen im LVDS-/PQ-Block, die drei Bänke in der DE.

| Adresse | Im Treiber | Bedeutung |
|---|---|---|
| `0x051C00E8` | `lvds` + `0x0E8` | Steuerwort der Gamma-Stufe (Schreibpfad + Doppelpuffer) |
| `0x051C0174` | `lvds` + `0x174` | Zustandswort; die **oberen 16 Bit** sind der Bildzähler |
| `0x05208000` | `gamma` + `0x0000` | LUT-Bank **R**, 512 × u32 |
| `0x05208800` | `gamma` + `0x0800` | LUT-Bank **G**, 512 × u32 |
| `0x05209000` | `gamma` + `0x1000` | LUT-Bank **B**, 512 × u32 |

Bits im Steuerwort `0x051C00E8`:

| Bit | Maske | Name im Treiber | Wirkung |
|---|---|---|---|
| 23 | `0x00800000` | `H713_GAMMA_WRITE_EN` | schaltet den Schreibport frei - **löscht sich selbst** |
| 22 | `0x00400000` | `H713_GAMMA_CHAN_LATCH` | Kanal-Schreiblatch - **löscht sich selbst** |
| 30 | `0x40000000` | `H713_GAMMA_COMMIT` | Schreibtransaktion offen |
| 28 | `0x10000000` | `H713_GAMMA_DBUF_FLIP` | Doppelpuffer der Gamma-Stufe umschalten |
| 21 | `0x00200000` | `H713_GAMMA_LATCH_A` | Latch A übernehmen |
| 20 | `0x00100000` | `H713_GAMMA_LATCH_B` | Latch B übernehmen |
| 26 | `0x04000000` | `H713_GAMMA_SCAN_KICK` | Scanout neu abtasten lassen |

Herkunft: `libhaldisplay.so::WriteGammaLUTByColor` (`sub_0xB881`, 604 Byte), aufgeschrieben in
`BACKGROUND.md` §5.1/§5.2. Der Stock-PQ-HAL schreibt diese Register **direkt**, nicht über den MIPS -
deshalb ist dieser Pfad auch dann benutzbar, wenn die MIPS-PQ-Routinen (die auf diesem Gerät ohnehin nicht
vollständig registriert werden, `BACKGROUND.md` §6) schweigen.

**Kein INCAP.** Dieser Patch fasst `0x0694xxxx` nicht an, schreibt keinen Descriptor und rührt die
Plane-/Ring-Register nicht an (das ist Paket D).

---

## 2. Bankaufbau und Packung

Eine Bank ist ein Schreibport von 512 u32. Jedes Wort trägt **zwei benachbarte 12-Bit-Abtastwerte**:

```
u32[i] = (Abtastwert[2i+1] << 12) | Abtastwert[2i]      little-endian
```

512 Wörter × 2 = **1024 Abtastwerte je Kanal**. Genau das ist die Größe, die der Treiber an KMS meldet:

```c
drm_crtc_enable_color_mgmt(&h->pipe.crtc, 0 /* kein DEGAMMA */, true /* CTM */,
			   H713_GAMMA_LUT_SIZE /* 1024 */);
```

Die Zahl ist **nicht geraten**, sondern aus dem Format abgeleitet, das Paket G ausgibt: `h713-pq gamma 2.2
--lut out.bin` liefert 2048 Byte = 512 u32 = eine Bank ([doku/81](81-pq-datenmodell.md) §4). `GAMMA_LUT_SIZE`
muss deshalb 1024 sein, nicht 512.

Userspace liefert je Eintrag 16 Bit (`struct drm_color_lut`), die Hardware nimmt 12. Die Umrechnung macht der
Kernel-Helfer `drm_color_lut_extract(wert, 12)` (rundend, nicht abschneidend). Umgekehrt rechnet
`analyse/kms/gamma_test.c` beim Einlesen einer G-Datei `12 → 16 Bit` so, dass der Rückweg im Treiber wieder
denselben 12-Bit-Wert ergibt (`(v * 65535 + 2047) / 4095`) - eine G-LUT kommt also **bitgenau** in der Bank an.
Rechnerisch geprüft für alle 4096 Werte (Rundreise fehlerfrei).

Ein **gelöschtes** `GAMMA_LUT` schreibt die **Identitätsrampe**. Das ist die KMS-Bedeutung von „keine LUT"
(Bypass) und deckt sich mit dem, was `BACKGROUND.md` §5.3 als am Gerät geprüft festhält: Nullen ergeben ein
schwarzes Bild, die Identität stellt die normale Ausgabe wieder her. Der Treiber liest die Bänke **nicht**
zurück, um einen „Originalzustand" zu sichern - es sind Schreibports, und ein Rücklesen ist nirgends belegt.

---

## 3. Die Schreibsequenz - und warum sie so und nicht anders ist

Das ist die ausdrückliche Falle des Nachtplans. `h713_afbd_gamma_write()` hält die elf Schritte aus
`BACKGROUND.md` §5.3 ein:

| # | Was | Warum |
|---|---|---|
| 1 | Zustandswort `0x051C0174` lesen, bis sich die oberen 16 Bit ändern, höchstens 40 ms | Bildgrenze abwarten, damit die Bänke nicht mitten im Bild umgeschrieben werden. Das ist **kein** Ready-Flag: ein Zähler, der stillsteht, ist kein Fehler - Stock gibt nach denselben 40 ms auf und schreibt trotzdem. Der Treiber merkt sich den zuletzt gesehenen Stand in `h->gamma_stat_frame` (Stock: `dword_11CDC`). **Nachtrag 07.09.:** die 40 ms sind gegen Regel 1 geprüft und **belegt** (`BACKGROUND.md` §5.3 Schritt 1 - Stock spinnt dieselbe Frist und schreibt danach ebenfalls); geändert wurde nur die Protokollstufe des Ablaufs, `drm_dbg_kms` → **`drm_warn_once`** ([REGEL1-0093-0095.md](nachtlog/REGEL1-0093-0095.md) §3.2). Siehe §9 |
| 2 | Steuerwort `0x051C00E8` sichern | Schritt 8 kippt Bit 28 **relativ** zu diesem Wert |
| 3 | `WRITE_EN` setzen, dann `CHAN_LATCH`, dann `COMMIT` - drei getrennte Read-Modify-Writes | Bit 23 und 22 löschen sich selbst. Wer die drei Bits in **einem** Wort schreibt, setzt Bits neu, die die Hardware schon zurückgenommen hat, und verliert die, die noch stehen sollen. Stock macht drei Schreibvorgänge; der Treiber auch |
| 4-6 | 512 Wörter nach R, dann G, dann B | Reihenfolge wie Stock; jede Bank hat ihren eigenen Port |
| 7 | `COMMIT` löschen | schließt die Transaktion |
| 8 | Bit 28 = `orig ^ 0x10000000` | Doppelpuffer der Gamma-Stufe auf die neu geschriebene Seite kippen |
| 9 | `LATCH_A` (Bit 21) setzen | Übernahme |
| 10 | `LATCH_B` (Bit 20) setzen | Übernahme |
| 11 | `SCAN_KICK` (Bit 26) setzen | Scanout tastet die Bänke neu ab |

**Die Schritte 7-11 sind der eigentliche Punkt.** Ohne sie stehen die Abtastwerte im Staging-Puffer und die
Wand zeigt weiter die alte Kurve - das ist genau der Fehler, der wie „die LUT wirkt nicht" aussieht und der in
den Legacy-Unterlagen ausdrücklich vermerkt ist.

Latches und selbstlöschende Bits werden behandelt wie im Rest des Treibers: jeder Schritt ist ein eigenes
`readl`/`writel`-Paar mit Maske (`h713_afbd_gamma_rmw()`), niemand komponiert ein Wort aus mehreren Absichten.
Das Zustandswort `0x051C0174` wird **nur gelesen**.

---

## 4. `CTM` - Weißabgleich als Diagonale

Die DE2-Farbstufe ist drei **unabhängige** Kurven, eine je Kanal, und nichts, was Kanäle mischt. Genau diese
Form hat der Stock-Weißabgleich: `CALCULATEGAMMA_RE_GUIDE.md` §4.5 beschreibt den Kurvenkern als
„Basiskurve aus `ucGammaFactor`, danach **Gain und Offset je Farbkanal aus `ucColorTemp`**" - der Weißabgleich
wird also in die Kurve hineingerechnet, **bevor** die drei Bänke geschrieben werden. Das ist auch der einzige
Grund, warum die drei Bänke sich überhaupt jemals unterscheiden.

Deshalb bildet der Treiber `CTM` so ab:

* **Diagonale** (`matrix[0]`, `[4]`, `[8]`) → Gain für R, G, B. Der Gain wird auf jeden Abtastwert der jeweiligen
  Bank angewandt und bei 4095 begrenzt.
* **Nebendiagonale** ungleich 0 → `-EINVAL` im `atomic_check`. Diese Stufe kann Kanäle nicht mischen; die
  Anforderung abzulehnen ist ehrlicher, als sie stillschweigend fallenzulassen.
* **Negative Diagonale** → `-EINVAL`.
* Format: `CTM`-Einträge sind **S31.32 Vorzeichen-Betrag**, nicht Zweierkomplement (Bit 63 = Vorzeichen). Die
  Umrechnung nach 16.16 macht der Kern-Helfer `drm_color_ctm_s31_32_to_qm_n(wert, 16, 16)`; Vorzeichen- und
  Bereichsprüfung stehen davor.

Ein gelöschtes `CTM` heißt Gain 1,0 auf allen drei Kanälen.

**Was fehlt:** Der Stock-Weißabgleich hat neben dem Gain auch einen **Offset** je Kanal (`pq_colortemp.ini`:
`ROffset,GOffset,BOffset,RGain,GGain,BGain`). Die KMS-Eigenschaft `CTM` ist eine reine 3×3-Matrix ohne
Offsetterm - dafür gibt es in dieser Schnittstelle keinen Platz. Auf diesem Gerät fällt das nicht auf, weil
alle Offsets 0 sind; wer den Offset braucht, muss ihn in die LUT rechnen (das kann `h713-pq`, sobald es dafür
Daten gibt) oder eine eigene Eigenschaft einführen.

---

## 5. Verhältnis zu Paket G

Klare Arbeitsteilung, kein doppelter Rechenweg:

| | Paket G (`userspace/h713-pq`) | Paket H (dieser Patch) |
|---|---|---|
| rechnet die Kurve | ja (33 Stützpunkte → 1024 Einträge, bitgleich zum Legacy-Rechner) | nein |
| kennt die Stock-Presets | ja (`pq_picturemode.ini`, `tvpq.db`, XML) | nein |
| packt in 512 u32 | ja, als Dateiformat | ja, aus der KMS-LUT |
| fasst Register an | **nein** | ja, und nur die aus §1 |

Der Weg von G nach H führt über die Datei:

```bash
# auf dem Arbeitsrechner
userspace/h713-pq/h713-pq gamma 2.2 --lut gamma-2.2.bin        # 2048 Byte = eine Bank
userspace/h713-pq/h713-pq gamma 2.2 --kanal all --lut rgb.bin  # 6144 Byte = R,G,B

# am Board (Datei vorher hinkopieren) -- --karte ist Pflicht, siehe §8
./gamma_test --karte /dev/dri/card1 datei gamma-2.2.bin --sekunden 30
```

`gamma_test` nimmt beide Größen: 2048 Byte werden auf alle drei Kanäle gelegt, 6144 Byte als R, G, B gelesen.
Weil der Weißabgleich in den Stock-Daten neutral ist, sind die drei Bänke heute ohnehin identisch
([doku/81](81-pq-datenmodell.md) §1).

---

## 6. Devicetree

Der Patch erweitert den Knoten `display@5600000` um zwei Fenster:

```
reg = <0x05600000 0x400>,     /* afbd  */
      <0x05140000 0x1000>,    /* route */
      <0x051c0000 0x200>,     /* lvds - war 0x100 */
      <0x05208000 0x2000>;    /* gamma - neu       */
reg-names = "afbd", "route", "lvds", "gamma";
```

* **`lvds` von `0x100` auf `0x200`:** das Zustandswort liegt bei `+0x174` und lag damit vier Byte hinter dem
  bisherigen Fensterende. Der LVDS-Block ist laut Stock-DTS 64 KB groß (`ge2d`-Knoten), `0x200` ist also
  reichlich konservativ.
* **`gamma` = `0x05208000` + `0x2000`:** deckt R (`+0x0000`), G (`+0x0800`) und B (`+0x1000` … `+0x17FF`) ab.
  Keine Überschneidung mit `ge2d` (`0x05200000` + `0x1000`) oder mit `route`/`afbd`.

**Beide Fenster sind im Treiber optional.** Fehlt `gamma`, oder ist `lvds` zu kurz, dann bekommt der CRTC keine
Farbeigenschaften und der Treiber sagt das per `drm_info`:

```
no gamma window in the device tree -- colour management off
```

Er verweigert **nicht** den Probe. Begründung: dieser Treiber ist das Einzige, was auf diesem Panel überhaupt
etwas anzeigen kann, und ein dunkler Beamer ist keine akzeptable Art, eine fehlende Eigenschaft zu melden.

---

## 7. Wo die Farbe im Commit landet

Der Treiber benutzt `drm_simple_display_pipe`. Dessen CRTC-Helfer sind `static const` im Kern und lassen sich
nicht um ein `atomic_flush` ergänzen - deshalb hängt die Farbübernahme an zwei Stellen, die es schon gibt:

* `h713_afbd_pipe_enable()` und `h713_afbd_pipe_update()` rufen `h713_afbd_color_commit()`, wenn
  `crtc_state->color_mgmt_changed` gesetzt ist.
* Das reicht, weil `drm_simple_kms_crtc_check()` bei **jedem** Commit, der den CRTC berührt,
  `drm_atomic_add_affected_planes()` aufruft. Ein Commit, der nur `GAMMA_LUT` setzt, zieht die Primary-Plane
  also mit in den Zustand, und `pipe_update` läuft - mit unverändertem Plane-Zustand und der Farbe als einziger
  Arbeit.
* Die CRTC-Prüfungen (LUT-Länge, CTM-Form) sitzen in `h713_afbd_atomic_check()`, einem Wrapper um
  `drm_atomic_helper_check()` in `drm_mode_config_funcs` - aus demselben Grund: der Simple-Pipe-Helfer besitzt
  den CRTC-`atomic_check` bereits.
* `color_mgmt_changed` wird vom Kern bei jedem `duplicate_state` zurückgesetzt. Ein gewöhnlicher Pageflip
  schreibt die Bänke also **nicht** neu; nur eine echte Änderung der Eigenschaft tut das.

Beim Entladen (`remove`/`shutdown`) bleibt die zuletzt geschriebene Kurve stehen - aus demselben Grund, aus dem
der Treiber auch das letzte Bild stehen lässt: er kann dieses Display nicht wieder hochfahren und räumt deshalb
beim Gehen nichts ab.

**Legacy-Gamma (`DRM_IOCTL_MODE_SETGAMMA`, `xrandr --gamma`) gibt es nicht.** `drm_crtc_enable_color_mgmt()`
setzt `crtc->gamma_size` nicht, und ein eigener `gamma_set`-Callback ginge nur über ein Ersetzen der
Simple-Pipe-CRTC-Funktionen. Der Weg ist ausschließlich die Atomic-Eigenschaft.

---

## 8. Testprogramm `analyse/kms/gamma_test.c`

`modetest` kann hier nicht helfen: es setzt Eigenschaften nur als Ganzzahl und kann keinen Property-Blob
anlegen - und auf dem Board-Rootfs liegt es ohnehin nicht (`/srv/h713-rootfs/usr/bin` hat kein `modetest`,
libdrm und `gcc` aber schon). Deshalb ein kleines libdrm-Programm.

```
gamma_test [--karte /dev/dri/card0] [--crtc ID] [--sekunden N] BEFEHL [ARG]

  identitaet     lineare Rampe = Bypass
  invertiert     LUT[i] = 65535 - i*65535/1023   -> Negativbild
  gamma EXP      Potenzkurve (2.2, 0.45, …)
  datei PFAD     DE2-Bank(en) aus h713-pq: 2048 Byte oder 6144 Byte
  ctm R G B      Weißabgleich-Gains, 1.0 = neutral (löscht dabei GAMMA_LUT)
  aus            GAMMA_LUT und CTM löschen

  --sekunden N   N Sekunden halten, dann zurücksetzen und beenden
                 ohne Angabe: halten bis Enter oder SIGINT/SIGTERM
```

**`--karte /dev/dri/card1` ist auf diesem Board Pflicht** (Abnahme 07.09.): der AFBD ist `card1`, `card0`
ist Panfrost und hat nur einen Render-Knoten. Die ursprüngliche Abnahmevorschrift in `H-gamma.md` ließ den
Schalter weg - einer der drei Punkte, die [79-nachtlog](79-nachtlog-20260907.md) als „so nicht ausführbar"
führt.

**Es gibt nur einen DRM-Master.** Läuft `hdmi_plane_test` (oder ein Compositor), scheitert `gamma_test` mit
`kein DRM-Master … Permission denied` und misst **nichts** - siehe Abschnitt 0, Instrumentenfalle 1. Wer
Farbe **und** Video-Plane zugleich braucht, muss beides in einem Programm setzen.

**Bauanleitung, nativ am Board** (dort liegen `gcc` und `libdrm-dev`):

```bash
gcc -O2 -Wall -o /root/gamma_test /root/gamma_test.c -I/usr/include/libdrm -ldrm -lm
```

**Bauanleitung, kreuzweise am Arbeitsrechner** (nur Lesen im NFS-Root, nichts hineinschreiben):

```bash
clang -O2 -Wall -Wextra -fuse-ld=lld --target=aarch64-linux-gnu \
      --sysroot=/srv/h713-rootfs -I/srv/h713-rootfs/usr/include/libdrm \
      -o gamma_test analyse/kms/gamma_test.c \
      -L/srv/h713-rootfs/usr/lib/aarch64-linux-gnu -ldrm -lm
```

**Warum das Programm laufen bleiben muss:** die LUT hängt am DRM-Master. Beendet es sich, fällt der Master an
den fbdev-Client des Kernels zurück; der stellt seine Modeset-Konfiguration wieder her, fasst die
Farbeigenschaften aber nicht an - die LUT bliebe also stehen. Deshalb löscht das Programm sie selbst, bevor es
geht, auch bei `SIGINT`/`SIGTERM`. Nur ein `SIGKILL` lässt sie stehen; dann hilft ein zweiter Aufruf mit `aus`.

---

## 9. Was belegt ist und was nicht

**Belegt** (Quelle in Klammern):

* Registeradressen, Bitbedeutungen und die elf Schritte der Schreibsequenz - RE aus
  `libhaldisplay.so::WriteGammaLUTByColor` (`BACKGROUND.md` §5.1-5.3), am Legacy-Gerät live geprüft: Nullen →
  schwarzes Bild, Identität → normale Ausgabe (§5.3).
* Bankaufbau und Packung `(lut[2i+1] << 12) | lut[2i]`, 512 u32 je Bank (`BACKGROUND.md` §5.4, doku/81 §4,
  Paket G bitgleich gegen den Legacy-Rechner).
* Dass der Stock-Weißabgleich als **Gain je Farbkanal in die Kurve** einfließt und nicht als Kanalmischung
  (`CALCULATEGAMMA_RE_GUIDE.md` §4.5) - daraus folgt die Diagonal-Abbildung von `CTM`.
* Dass die DE2-Stufe nur wirkt, wenn die DE getaktet läuft (`BACKGROUND.md` §5.5) - bei uns hält der Treiber
  `clk_afbd`/`clk_bus_disp`, und die Konsole liegt auf dem Panel (Patch 0064).

**Seit dem 07.09. zusätzlich belegt** (Abschnitt 0):

* **Der Pfad auf unserem Board.** `GAMMA_LUT_SIZE 1024` und `CTM` sind am CRTC 36 angemeldet, die invertierte
  LUT ändert 100,00 % der Konsole, die Rückkehr 0,00 %.
* **Die Stufe wirkt auf beiden Pfaden**, Konsole und Video (86,56 % auf dem Video-Bild, Selektor durchgehend
  `0x39000000`). Damit ist die frühere Erwartung „sie sitzt hinter dem Mux, sollte also für beide gelten"
  gemessen und nicht mehr bloß plausibel.

**Nicht belegt / ungetestet:**

* **`CTM` ist ungetestet, weil Stock hier neutral ist.** Alle Bänke in `pq_colortemp.ini` und
  `White_Balance_Mode` stehen auf Gain 512/512/512, Offset 0 (doku/81 §1). Es gibt in den Vendor-Daten also
  keinen einzigen Fall, an dem sich ein nicht-neutraler Weißabgleich gegen Stock prüfen ließe. Die
  Schnittstelle ist sauber implementiert und über `gamma_test ctm 1.0 0.6 0.6` an der Wand *sichtbar* prüfbar
- aber „sichtbar" ist hier nicht dasselbe wie „stimmt mit Stock überein". **Die Abnahme hat daran nichts
  geändert:** sie hat `CTM` nicht gefahren.
* **Der genaue Stock-Rechenweg für Gain und Offset** (vor oder nach der Begrenzung, mit welcher Rundung) ist
  nicht bitgenau zurückgewonnen; `CALCULATEGAMMA_RE_GUIDE.md` §4.5 nennt die Reihenfolge als *erwartet*, nicht
  als disassembliert. Unser Weg (Gain auf den fertigen 12-Bit-Wert, dann begrenzen) ist eine Entscheidung, keine
  Übernahme.
* **Das Zustandswort `0x051C0174`** ist als „oberes Halbwort = Bildzähler" aus dem Legacy-Code übernommen. Ob
  es auf unserem Board wirklich zählt, ist **weiterhin nicht direkt gemessen** - die Abnahme sagt dazu nichts,
  weil die Kurve auch bei stehendem Zähler geschrieben wird (wie bei Stock). Seit dem 07.09. ist die Frage
  aber **falsifizierbar ohne Zusatzaufwand**: läuft die 40-ms-Frist ab, steht
  `gamma: frame counter stuck at …` als `drm_warn_once` im gewöhnlichen `dmesg`
  ([REGEL1-0093-0095.md](nachtlog/REGEL1-0093-0095.md) §3.2). **Steht die Zeile nach einem Abnahmelauf nicht
  im Log, trägt die Annahme; steht sie da, ist entweder `0x051C0174` nicht der Bildzähler oder die Stufe
  scannt nicht** (`BACKGROUND.md` §5.5 - der Zustand, in dem ein Gamma-Schreibvorgang die Register erreicht
  und den Schirm nie). Aus dem Abnahmelauf vom 06:12 ist ein solcher `grep` nicht protokolliert.
  **Was die Abnahme immerhin ausschließt, ist die zweite Erklärung:** die Stufe **scannt** - sonst hätte die
  invertierte LUT die Konsole nicht vollflächig umgedreht. Erscheint die Warnzeile also je in einem Lauf, in
  dem die LUT sichtbar wirkt, dann ist `0x051C0174` nicht der Bildzähler.
* **Wechselwirkung mit der KMS-Video-Plane (Paket D) im selben Prozess.** Gemessen ist der Video-Pfad über
  den Skriptweg; mit laufender Plane hält `hdmi_plane_test` den DRM-Master, und `gamma_test` kommt gar nicht
  zum Zug (Abschnitt 0). Dass die Farbe auch über einen KMS-Commit **bei aktiver Video-Plane** ankommt, ist
  damit nicht gezeigt.

---

## 10. Offene Punkte

* ~~Abnahme an der Wand~~ - **erledigt am 07.09., 06:12-06:14** (Abschnitt 0).
* ~~Ob die Gamma-Stufe auch den Video-Pfad (Source 0) einfärbt oder nur den RGB-Pfad~~ - **beantwortet am
  07.09., 06:20: beide Pfade**, 86,56 % auf dem Video-Bild (Abschnitt 0).
* **`CTM` gegen Stock** - unverändert offen, und ohne Vendor-Daten auch nicht entscheidbar (§9).
* **Läuft der Bildzähler `0x051C0174` auf diesem Board?** Offen, aber ab sofort mit einer `grep`-Zeile aus
  jedem gewöhnlichen Lauf zu beantworten (§9).
* **Farbe und Video-Plane im selben DRM-Master** - heute nicht möglich, weil `gamma_test` und
  `hdmi_plane_test` beide Master sein wollen (Abschnitt 0). Für Paket I/F ist das die Stelle, an der ein
  Programm beides setzen muss.
* Offset des Weißabgleichs hat in `CTM` keinen Platz (§4). Erst relevant, wenn irgendeine Datenquelle einen
  Offset ungleich 0 liefert.
* `DEGAMMA_LUT` ist nicht angemeldet; eine Eingangs-LUT ist in dieser Stufe nicht belegt.
