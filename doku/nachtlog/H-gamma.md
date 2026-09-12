# Paket H — Gamma und CTM im KMS

Agent: Paket H (offline auf Paket A). **Kein Board angefasst** — kein `ssh root@192.168.8.141`, kein
`ssh user@192.168.8.162`, kein `sonoff_ctl`, kein `wandcheck.py`, kein `tio`, kein `scp`, nichts nach
`tftp/`, kein `sudo`, kein `git commit`, kein Aufruf von `build/build.sh`, keine Änderung an
`mainline/patches/kernel/series`. INCAP (`0x0694xxxx`) nicht gelesen und nicht geschrieben, Descriptor nicht
angefasst.

---

## Verlauf

**21:59** Nachtplan `doku/78` (Abschnitt 0, 0b, 3 „H", 3 „G", 7) und `nachtlog/00-koordination.md` gelesen.

**22:00–22:06** Eingaben gelesen, in dieser Reihenfolge: `nachtlog/G-pq.md` und `doku/81-pq-datenmodell.md`
(Datenmodell und LUT-Format — **nicht** selbst hergeleitet), `legacy/userspace/hy310-pqd/BACKGROUND.md` §5
inklusive §5.3 und §5.5, `include/pqgamma.h` und `src/pqgamma.cpp` (die Sequenz im Quelltext, nicht nur in
Prosa), `CALCULATEGAMMA_RE_GUIDE.md` §4.5/§4.7, `re/.../tvconfig/pq_colortemp.ini`,
`nachtlog/A-patches.md` (Baumhash, DTB-Kontrollen), der Treiber
`drivers/gpu/drm/tiny/sun50i-h713-afbd.c` nach 0078/0079, `drivers/gpu/drm/drm_simple_kms_helper.c`
(wer den CRTC-`atomic_check` besitzt), `include/drm/drm_color_mgmt.h`,
`drivers/gpu/drm/drm_atomic_state_helper.c` (`color_mgmt_changed` wird beim `duplicate_state` zurückgesetzt),
Patch `0038` und `0078` (Herkunft der `reg`-Fenster), `analyse/hdmi-seq/wandcheck.py` (welche Kennzahlen es
überhaupt gibt).

**22:06** Zwei Befunde, die den Entwurf bestimmt haben:

1. **Zwei Register fehlten im Devicetree.** Das Fenster `lvds` ist `0x051c0000 + 0x100` (aus 0078). Das
   Zustandswort der Gamma-Stufe liegt bei `0x051c0174` — vier Byte hinter dem Fensterende. Die drei LUT-Bänke
   ab `0x05208000` waren gar nicht abgebildet. Ohne DT-Änderung ist Schritt 1 und sind die Schritte 4–6 der
   Stock-Sequenz nicht ausführbar. Das Fenster wächst deshalb auf `0x200` und `0x05208000 + 0x2000` kommt als
   `gamma` dazu. Keine Überschneidung mit `ge2d` (`0x05200000 + 0x1000`), `route` oder `afbd`.
2. **Die LUT-Größe ist 1024, nicht 512.** Paket G liefert 2048 Byte je Bank = 512 u32, und jedes u32 trägt
   **zwei** 12-Bit-Abtastwerte (doku/81 §4). `GAMMA_LUT_SIZE` ist die Zahl der Abtastwerte, also 1024. Aus dem
   Format abgeleitet, nicht geraten.

**22:08** Arbeitskopie der beiden Dateien im Scratchpad (`a/` unverändert, `b/` bearbeitet), damit Paket D
parallel an derselben Datei arbeiten kann, ohne dass wir uns überschreiben. Geändert wurden ausschließlich:
Includes, ein Block Register-Definitionen, drei neue Felder in `struct h713_afbd`, ein neuer
Funktionsblock zwischen den Plane-Funktionen und `h713_afbd_pipe_enable()`, je zwei Zeilen in
`pipe_enable`/`pipe_update`, eine Zeile in `drm_mode_config_funcs`, eine Hilfsfunktion vor `probe` und fünf
Zeilen in `probe`. **Keine** Änderung an `init_video_info`, `video_stop`, `video_atomic_check`,
`video_atomic_update`, den Formatlisten, der Ring-/Slot-Logik oder dem IRQ-Handler — das ist Paket D.

**22:11–22:12** Prüfbau, siehe unten. Grün.

**22:15** `analyse/kms/gamma_test.c` geschrieben (libdrm, Atomic-Property-Blob) und kreuzweise gegen das
Board-Rootfs übersetzt. `modetest` kommt für die Abnahme nicht in Frage: es setzt Eigenschaften nur als
Ganzzahl und kann keinen Property-Blob anlegen — und `/srv/h713-rootfs/usr/bin/modetest` gibt es gar nicht.
libdrm-Header, `libdrm.so.2` und `gcc` liegen im Board-Rootfs, das Programm ist dort also auch nativ baubar.
(Nur gelesen im NFS-Root, nichts hineingeschrieben.)

**22:17–22:19** Zweiter Prüfbau nach `checkpatch`-Korrektur, Artefakte gesichert.

**22:19–22:21** `doku/87-gamma-ctm-kms.md` und dieses Teillog geschrieben.

**22:21** Zwei Nachbesserungen aus der eigenen Durchsicht, beide wieder gebaut und geprüft:

* Der Argumentparser von `gamma_test` nahm Optionen nur **vor** dem Befehl an — die Abnahmevorschrift schreibt
  sie aber dahinter (`gamma_test invertiert --sekunden 90`). Jetzt gehen beide Stellungen.
* Die CTM-Umrechnung S31.32 → 16.16 macht jetzt der Kern-Helfer `drm_color_ctm_s31_32_to_qm_n()` statt einer
  eigenen Schiebeoperation. Er begrenzt zusätzlich sauber; die Vorzeichen- und Bereichsprüfungen bleiben davor.

**22:22** Zahlenprobe der Umrechnungen (rein rechnerisch, kein Gerät): die Rundreise 12 Bit → 16 Bit
(`gamma_test`) → 12 Bit (`drm_color_lut_extract`) ist für **alle 4096** Werte exakt. Eine LUT aus Paket G kommt
also bitgenau in der Bank an. Identitätsrampe: `h[0]=0`, `h[1023]=4095`, monoton; invertiert: `h[0]=4095`,
`h[1023]=0`.

**22:24** Letzter Prüfbau grün, Artefakte gesichert, Baumkopie gelöscht.

---

## Was der Patch tut

`mainline/patches/kernel/0095-drm-h713-afbd-color-mgmt.patch`, `diff -ruN`-Form wie die bestehenden,
zwei Dateien: `sun50i-h713.dtsi` (9 Zeilen) und `sun50i-h713-afbd.c`.

* **`GAMMA_LUT`** (1024 Einträge je Kanal): der Treiber packt je zwei benachbarte 12-Bit-Abtastwerte in ein u32
  (`(lut[2i+1] << 12) | lut[2i]`) und schreibt 512 Wörter nach `0x05208000` (R), `0x05208800` (G),
  `0x05209000` (B). Danach die **vollständige Aktivierungssequenz** auf `0x051C00E8`. Eine gelöschte
  Eigenschaft schreibt die Identitätsrampe (= Bypass dieser Stufe).
* **Schreibsequenz** exakt nach `BACKGROUND.md` §5.3, elf Schritte: Bildzähler `0x051C0174` abwarten (max.
  40 ms, Timeout ist kein Fehler) → Steuerwort sichern → `WRITE_EN`, `CHAN_LATCH`, `COMMIT` in **drei
  getrennten** Read-Modify-Writes (Bit 23 und 22 löschen sich selbst) → R, G, B schreiben → `COMMIT` löschen →
  Bit 28 relativ zum gesicherten Wort kippen → Bit 21 → Bit 20 → Bit 26. Ohne die letzten fünf Schritte bleibt
  die neue Kurve im Staging-Puffer stehen; das ist die Falle, auf die der Nachtplan hinweist.
* **`CTM`** → Weißabgleich-Gains: die Diagonale wird als Gain je Farbkanal auf die LUT gerechnet (so, wie der
  Stock-PQ-Kern den Weißabgleich in die Kurve rechnet, `CALCULATEGAMMA_RE_GUIDE.md` §4.5 — das ist der einzige
  Grund, warum die drei Bänke sich je unterscheiden). Nebendiagonale ungleich 0 oder negative Diagonale werden
  im `atomic_check` mit `-EINVAL` abgelehnt: diese Stufe kann Kanäle nicht mischen, und stilles Fallenlassen
  wäre gelogen. Einträge sind S31.32 Vorzeichen-Betrag; die Umrechnung nach 16.16 macht der Kern-Helfer
  `drm_color_ctm_s31_32_to_qm_n(wert, 16, 16)`, nicht selbstgeschriebene Schieberei.
* **Devicetree:** `lvds` `0x100 → 0x200`, neues Fenster `gamma = <0x05208000 0x2000>`. Beides ist im Treiber
  **optional** — fehlt es, gibt es keine Farbeigenschaften und eine `drm_info`-Zeile, aber der Probe scheitert
  nicht (dieser Treiber ist das Einzige, was auf diesem Panel etwas anzeigen kann).

Registersatz, Bankaufbau, Begründung jedes Schritts und die Belegt/Ungetestet-Liste stehen in
[doku/87-gamma-ctm-kms.md](../87-gamma-ctm-kms.md).

---

## Prüfbau (kein `build/build.sh`, keine Änderung an `series`)

Kopie des A-Baums nach `mainline/build/pruefbau-H-color-mgmt`, Patch dort mit `patch -p1` angewandt, im
Container `h713-build` mit den Variablen aus `build/build.sh` gebaut, danach die Kopie wieder gelöscht.

| | |
|---|---|
| **Quelle** | `mainline/build/linux-6.18.38-7dff124db0ddefd2bef7f9028ad2bbeaac2f7af7ad50a8fcfbc4226df6088d55` (Paket A) |
| **Befehl (Treiber)** | `podman exec h713-build bash -lc 'cd /work/mainline/build/pruefbau-H-color-mgmt && make ARCH=arm64 LLVM=1 W=1 modules'` |
| **Befehl (DT)** | `… && make ARCH=arm64 LLVM=1 dtbs` |
| **Ergebnis** | **grün.** `CC [M] drivers/gpu/drm/tiny/sun50i-h713-afbd.o`, `LD [M] … .ko`, `DTC …-qz713df-a1.dtb`. Auch mit `W=1` **keine** Warnung aus dieser Datei (die zwei Warnungen im Lauf stammen aus `sound/soc/sunxi/sun4i-spdif.c` und `drivers/soc/sunxi/cpu_comm/cpu_comm_rpc.c` und sind vorbestehend) |
| **Patch-Anwendung** | `patch -p1` sauber, kein Fuzz, keine `.rej`/`.orig` |
| **checkpatch** | `--strict`: **0 errors, 0 warnings, 1 check** — der Check ist „Prefer using the BIT macro" für `H713_GAIN_ONE`; das ist ein Skalenfaktor 1,0 in 16.16, keine Bitmaske, und bleibt bewusst so |
| **Symbolprobe** | `llvm-nm -u …ko` zeigt genau zwei neue undefinierte Symbole: `drm_crtc_enable_color_mgmt` und `drm_color_ctm_s31_32_to_qm_n` (beide `EXPORT_SYMBOL` im DRM-Kern) |
| **DTB-Kontrolle** | `reg = <0x5600000 0x400 0x5140000 0x1000 0x51c0000 0x200 0x5208000 0x2000>`, `reg-names = "afbd\0route\0lvds\0gamma"` |
| **Artefakte** | `analyse/kms/pruefbau-H/` — `sun50i-h713-afbd.o`, `.ko`, `.sun50i-h713-afbd.o.cmd`, `sun50i-h713-hy200-qz713df-a1.dtb`. **Prüfbau, kein Auslieferstand** |

Testprogramm, Übersetzungsprobe am Arbeitsrechner gegen das Board-Rootfs (nur lesend):

```
clang -O2 -Wall -Wextra -fuse-ld=lld --target=aarch64-linux-gnu --sysroot=/srv/h713-rootfs \
      -I/srv/h713-rootfs/usr/include/libdrm -o gamma_test analyse/kms/gamma_test.c \
      -L/srv/h713-rootfs/usr/lib/aarch64-linux-gnu -ldrm -lm
```
→ `ELF 64-bit LSB pie executable, ARM aarch64`, keine Warnung. Die Binärdatei liegt im Scratchpad und **nicht**
im Repo; gebaut wird sie für die Abnahme am Board.

---

## Abnahmevorschrift (kopierbar, für die Hauptsitzung)

Die Abnahme braucht **nur die Konsole auf der Wand** — kein HDMI, kein `arisc_edid_init.sh`, kein Descriptor,
kein `afbd_source0.py`. Kurzer Board-Slot.

### 0. Vorbereitung (Arbeitsrechner)

```bash
cd /opt/Projekte/h713
# 0095 in NUMERISCHER Ordnung in die Serie (die Datei gehört der Hauptsitzung).
# Stand 22:25 enthält sie schon 0096/0097 von anderen Paketen, also nicht anhängen,
# sondern einsortieren -- und ein 0093 (Paket D) muss VOR 0095 stehen:
sed -i '/^0090-soc-sunxi-add-arisc-hdmi-hpd\.patch$/a 0095-drm-h713-afbd-color-mgmt.patch' \
    mainline/patches/kernel/series
grep -n -E '009[0-9]' mainline/patches/kernel/series      # Reihenfolge kontrollieren

podman exec h713-build bash -lc 'cd /work/mainline && KERNEL_CONFIG=netboot build/build.sh kernel'
ss -ulnp | grep -w :69                       # laeuft TFTP? sonst STOPP
cp tftp/h713-kernel-netboot.fit tftp/h713-kernel-netboot.fit.bak-20260907-H
cp mainline/build/out/h713-kernel-netboot.fit tftp/
```

### 1. Kaltstart und Testprogramm bauen

```bash
sonoff_ctl restart --host 192.168.8.179
for i in $(seq 30); do ssh -o BatchMode=yes -o ConnectTimeout=3 root@192.168.8.141 uptime && break; sleep 4; done

scp /opt/Projekte/h713/analyse/kms/gamma_test.c root@192.168.8.141:/root/
ssh root@192.168.8.141 'gcc -O2 -Wall -o /root/gamma_test /root/gamma_test.c -I/usr/include/libdrm -ldrm -lm && ls -l /root/gamma_test'
ssh root@192.168.8.141 'dmesg | grep -iE "afbd|gamma" | tail -5'
```

**Erwartet:** `adopting 1920x1080, …` wie bisher und **keine** Zeile
`no gamma window in the device tree -- colour management off`. Kommt diese Zeile, passt DTB und Kernel nicht
zusammen (altes DTB) — dann Punkt 0 wiederholen, nicht weitermessen.

### 2. Eigenschaften prüfen (ersetzt `modetest`, das es hier nicht gibt)

```bash
ssh root@192.168.8.141 '/root/gamma_test identitaet --sekunden 0'
```

**Erwartet, wörtlich:**

```
CRTC <id>: GAMMA_LUT_SIZE 1024, CTM vorhanden
identitaet: LUT[0]=0 LUT[1023]=65535
gesetzt.
halte 0 s, danach zuruecksetzen.
zurueckgesetzt.
```

Fehlt `GAMMA_LUT`, meldet das Programm das ausdrücklich und bricht ab.

### 3. Der eigentliche Test: invertierte LUT

```bash
cd /opt/Projekte/h713
python3 analyse/hdmi-seq/wandcheck.py shot H-vorher
```

```bash
ssh root@192.168.8.141 'setsid nohup /root/gamma_test invertiert --sekunden 90 >/root/gamma_test.log 2>&1 </dev/null & echo gestartet'
```

```bash
sleep 5
ssh root@192.168.8.141 'cat /root/gamma_test.log'
python3 analyse/hdmi-seq/wandcheck.py shot H-invertiert
```

Nach Ablauf der 90 s (das Programm setzt selbst zurück):

```bash
sleep 90
python3 analyse/hdmi-seq/wandcheck.py shot H-nachher
python3 analyse/hdmi-seq/wandcheck.py diff H-vorher H-invertiert
python3 analyse/hdmi-seq/wandcheck.py diff H-vorher H-nachher
```

Falls es früher zurück soll (Prozessname exakt, **nicht** `-f`, sonst trifft das Muster die eigene Shell):

```bash
ssh root@192.168.8.141 'pkill -TERM -x gamma_test; sleep 2; /root/gamma_test aus --sekunden 0'
```

### 4. Optional im selben Slot: CTM sichtbar machen

```bash
ssh root@192.168.8.141 'setsid nohup /root/gamma_test ctm 1.0 0.4 0.4 --sekunden 60 >/root/gamma_ctm.log 2>&1 </dev/null & echo gestartet'
sleep 5; python3 analyse/hdmi-seq/wandcheck.py shot H-ctm-rot
```
Erwartung: sichtbarer Rotstich (Grün und Blau auf 40 %). Das prüft nur, **dass** die Schnittstelle wirkt —
nicht, dass sie mit Stock übereinstimmt (in den Stock-Daten ist der Weißabgleich überall neutral).

### 5. Optional: eine echte Stock-Kurve aus Paket G

```bash
userspace/hy310-pq/hy310-pq gamma 2.2 --lut /tmp/gamma-2.2.bin
scp /tmp/gamma-2.2.bin root@192.168.8.141:/root/
ssh root@192.168.8.141 'setsid nohup /root/gamma_test datei /root/gamma-2.2.bin --sekunden 60 >/root/gamma_datei.log 2>&1 </dev/null & echo gestartet'
sleep 5; python3 analyse/hdmi-seq/wandcheck.py shot H-gamma22
```
Erwartung: das Bild wird **dunkler** (2.2 auf ein Signal, das schon gammakorrigiert ist, drückt die Mitteltöne),
aber nicht invertiert. Das ist der Beweis, dass der Weg G → Datei → Bank durchgängig ist.

---

## Erwartete Änderung der `wandcheck`-Kennzahlen (Entscheidungsregel)

ROI ist `220 40 1090 560` = **452 400 Pixel**. Auf der Wand steht die Kernel-Konsole: helle Schrift auf dunklem
Feld, das Schwarz des Beamers ist im Foto grau. Als Größenordnung für „vorher": die Aufnahme
`wand-aktuell/plancheck.json` vom 06.09. hatte `mean 36.7`, `hell 2826`, `dunkel 406257` (90 % des ROI).

**Grün, wenn alle drei zutreffen:**

1. **Bild ansehen** (das ist die Hauptkennzahl, nicht die Zahlen): `H-invertiert.jpg` zeigt ein **Negativ** —
   dunkle Schrift auf hellem Feld statt umgekehrt.
2. `diff H-vorher H-invertiert`: Anteil der Pixel mit Unterschied > 25 **über 50 %** des ROI.
3. `H-invertiert.json` gegen `H-vorher.json`: `mean` **steigt** deutlich (Richtung ist entscheidend, nicht der
   Betrag), `dunkel` **fällt** mindestens auf die Hälfte, `hell` **steigt** um ein Vielfaches.

**Zurücksetzen ist grün, wenn:**

4. `diff H-vorher H-nachher`: Anteil > 25 **unter 10 %** — also nur Kamerarauschen und Belichtungsnachführung;
   und `H-nachher.jpg` sieht aus wie `H-vorher.jpg`.

**Warum die Beträge weich formuliert sind:** die Webcam steht auf Belichtungsautomatik (die laut Regel 7 nicht
angefasst wird). Wird die Wand hell, regelt sie ab und drückt den `mean`-Sprung zusammen. Deshalb zählt die
**Richtung** von `mean`/`hell`/`dunkel` und der `diff`-Anteil, nicht ein absoluter Schwellwert — und deshalb
steht „Bild ansehen" an erster Stelle.

**Rot und was es bedeutet:**

* `gamma_test` meldet `CRTC … hat kein GAMMA_LUT` → Kernel/DTB passen nicht zusammen (Punkt 1 oben).
* `gamma_test` meldet `AtomicCommit: Invalid argument` → der `atomic_check` hat abgelehnt; mit
  `echo 0x04 > /sys/module/drm/parameters/debug` und `dmesg | tail` steht der Grund als `drm_dbg_kms`-Zeile da
  (LUT-Länge oder CTM-Form).
* `gamma_test` meldet `AtomicCommit: Permission denied` → ein anderer DRM-Master läuft (Compositor?).
* `gamma_test` sagt `gesetzt.`, aber das Bild ändert sich **gar nicht** (`diff` unter 10 %): dann sind die
  Bänke geschrieben, aber nicht aktiviert worden. Das ist der interessante Fehlerfall — bitte
  `dmesg | grep -i gamma` mit `drm.debug=0x04` mitnehmen (Zeile `gamma: frame state stuck at …`?) und den
  Ist-Wert von `0x051C00E8` **vor und nach** dem Setzen notieren
  (`python3 /root/dump_state.py H-gamma` oder ein gezieltes Lesen). Nicht raten und nichts umbauen — dann
  stimmt entweder die Annahme über das Zustandswort oder die Bit-Belegung nicht, und das ist eine RE-Frage.
* Das Bild wird **schwarz** statt invertiert: die Bänke sind mit Nullen beschrieben worden. Dann stimmt die
  Packung nicht (`BACKGROUND.md` §5.3 nennt Nullen ausdrücklich als „schwarzer Schirm").

---

## Board-Anfrage

**Was ich brauche:** einen kurzen Board-Slot mit dem Kernel aus Paket A **plus 0095**, Konsole auf der Wand.
Kein HDMI, kein Descriptor, keine Capture. Die Vorschrift oben ist vollständig kopierbar; Punkt 3 ist die
Abnahme, Punkt 4 und 5 sind Zugaben, wenn Zeit bleibt.

**Was ich zurückbekommen möchte, damit ich ohne Rückfrage weiterarbeiten kann:**

1. Die Ausgabe von `/root/gamma_test identitaet --sekunden 0` (Punkt 2) — insbesondere die Zeile
   `GAMMA_LUT_SIZE 1024, CTM vorhanden`.
2. Die drei Aufnahmen `H-vorher`, `H-invertiert`, `H-nachher` (JPG **und** JSON) und die beiden `diff`-Zeilen.
3. `dmesg | grep -iE "afbd|gamma"` nach dem Kaltstart.
4. Falls Punkt 4/5 gefahren wurden: `H-ctm-rot.jpg` und `H-gamma22.jpg`.

Ergebnisse bitte nach `re/captures/weltneuheit/ours-20260907-nacht/H/`.

---

## Abhängigkeiten und Reibung mit Paket D

Wir bearbeiten dieselbe Datei. Ich habe in einer eigenen Kopie gearbeitet und nur Farbverwaltung angefasst;
trotzdem gibt es drei Berührungspunkte, die die Hauptsitzung beim Zusammenführen kennen sollte:

1. **`sun50i-h713.dtsi`, Knoten `display@5600000`.** Ich ändere die Zeilen `reg` und `reg-names`. Falls Paket D
   demselben Knoten ein `memory-region` gibt (Nachtplan 3 „D" Schritt 2), liegt das vier Zeilen weiter unten —
   außerhalb meines Kontexts, sollte also sauber koexistieren. Reihenfolge in `series`: **0093 vor 0095**. Gibt
   es doch einen Konflikt, ist meine Änderung die triviale: zwei Adressen in der `reg`-Liste und ein Name mehr.
2. **`probe()`.** Meine fünf Zeilen (`h713_afbd_map_gamma()` + `drm_crtc_enable_color_mgmt()`) sitzen direkt vor
   `drm_mode_config_reset(drm);`. Fasst D die Plane-Initialisierung darüber an, kann sich der Kontext
   überschneiden. Der Einbau ist reihenfolgeunkritisch — er muss nur nach `drm_simple_display_pipe_init()`
   (der CRTC muss existieren) und vor `drm_dev_register()` stehen.
3. **Ein Farb-Commit ruft die Plane-Updates mit auf.** `drm_simple_kms_crtc_check()` zieht über
   `drm_atomic_add_affected_planes()` **alle aktiven** Planes in den Zustand. Ist die Video-Plane an, läuft bei
   einem reinen `GAMMA_LUT`-Commit auch `h713_afbd_video_atomic_update()` noch einmal — mit unverändertem
   Plane-Zustand. **Für Paket D heißt das:** der Descriptor darf dort nicht bei jedem `atomic_update`
   geschrieben werden, sondern nur beim Übergang „Plane aus → an" (Nachtplan 3 „D": „beim Enable **einmal**").
   Ich habe das nicht selbst geändert — das ist Ds Code.

Zwei Register, die D vermutlich auch anfasst, habe ich **nicht** verändert: den Selektor `0x051C006C` und den
Chroma-Gain `0x05140508`. Beide liegen in Fenstern, die ich nur lese bzw. gar nicht anfasse.

---

## Offen

* Die Abnahme selbst (siehe oben). Bis dahin ist der ganze Pfad an **dieser** Wand ungemessen.
* **`CTM` bleibt ungetestet gegen Stock**, weil `pq_colortemp.ini` und `White_Balance_Mode` durchgängig neutral
  sind (Gain 512/512/512, Offset 0 — Befund aus Paket G, doku/81 §1). Es gibt keinen Vendor-Fall, gegen den man
  vergleichen könnte. Die Schnittstelle ist implementiert und sichtbar prüfbar (Punkt 4 oben), aber
  „sichtbar" ist nicht „stock-gleich". Der **Offset** des Stock-Weißabgleichs hat in `CTM` überhaupt keinen
  Platz (doku/87 §4).
* Ob die Gamma-Stufe auch den Video-Pfad (Source 0) einfärbt oder nur den RGB-Pfad, ist ungemessen. Sie sitzt
  hinter dem Mux `0x051C006C`, sollte also beide betreffen — zu prüfen, sobald Paket D ein Bild liefert.
* `DEGAMMA_LUT` ist nicht angemeldet; eine Eingangs-LUT ist in dieser Stufe nirgends belegt.
* Der Stock-Rechenweg für Gain/Offset ist nicht bitgenau zurückgewonnen (`CALCULATEGAMMA_RE_GUIDE.md` §4.5
  nennt die Reihenfolge als *erwartet*). Unsere Wahl — Gain auf den fertigen 12-Bit-Wert, dann begrenzen — ist
  als Entscheidung dokumentiert, nicht als Übernahme.

## Ergebnisdateien

* `mainline/patches/kernel/0095-drm-h713-afbd-color-mgmt.patch` (**nicht** in `series` eingetragen)
* `analyse/kms/gamma_test.c`
* `analyse/kms/pruefbau-H/` — Prüfbau-Artefakte (`.o`, `.ko`, `.cmd`, DTB), kein Auslieferstand
* `doku/87-gamma-ctm-kms.md`
* dieses Teillog
