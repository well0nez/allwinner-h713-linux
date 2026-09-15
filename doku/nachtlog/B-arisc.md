# B - ARISC-Treiber: Firmware-Laden, Handshake, HDMI-API

Agent: Paket B. Board **nicht** angefasst (kein `ssh`, kein `sonoff_ctl`, kein `tftp/`).
`series` und `build/build.sh` **nicht** angefasst - die gehören in dieser Welle Paket A.

---

## Zeitleiste

| Uhrzeit | Was |
|---|---|
| 21:45 | Nachtplan (0, 0b, 1, 3B, 7), `nachtlog/00-koordination.md`, doku/75/77 gelesen; Eingaben `analyse/arisc-hdmi-drv/arisc_hdmi.c`, `analyse/arisc-msg/arisc_hdmi.py`, `analyse/hdmi-seq/arisc_edid_init.sh`, `analyse/arisc-loader/arisc_load.py`, `prep_after_boot.sh` |
| 21:50 | Patch `0051-…-arisc-hdmi-hpd` war zu Beginn noch unter der alten Nummer, beim zweiten Zugriff schon `0090-…` - Paket A hat währenddessen umbenannt. Format von `0090` und `0037` als Vorlage genommen |
| 21:52 | RE-Rückfrage geklärt: Antwortrahmen auf ARM-RX ch1 kommt aus dem Sender `0x118e4` (`0x11984`: Byte 0 = `0xff`, Prüfsumme + `0xfe` am Ende); Nutzlast von `CheckEDIDUpdateStatus` wird bei `0x125a0..0x125b8` gebaut: `f8 01 01 <[0x117246]>` |
| 21:54 | `analyse/arisc/hy310-edid.bin` erzeugt (512 B, `HDMI_EDID_14.bin` + `HDMI_EDID_20.bin`) |
| 21:55-22:01 | Kopf `include/linux/soc/sunxi/h713-arisc.h` und Treiber `sun50i-h713-arisc.c` geschrieben |
| 22:01 | **Prüfbau 1** (out-of-tree) grün |
| 22:03 | DT-Knoten ins `sun50i-h713.dtsi`; DTB-Übersetzung geprüft (siehe unten) |
| 22:05 | Patch `0091-soc-sunxi-h713-arisc.patch` erzeugt, `patch -p1 --dry-run` sauber |
| 22:06 | **Prüfbau 2** (in-tree, an der Stelle, an die der Patch legt) grün; Baum danach in den Vorzustand zurückgesetzt |
| 22:08 | Zwei eigene Fehler beim Nachlesen gefunden und behoben (siehe „Zwei Korrekturen") |
| 22:09 | Patch neu erzeugt, Prüfbau 1 wiederholt, grün |
| 22:15 | `doku/82-arisc-treiber.md` geschrieben |
| 22:16 | Prüfbau 2 mit dem **endgültigen** Quelltext wiederholt, grün; Baum danach wieder in den Vorzustand (`Kconfig`, `Makefile`, `.config`, `auto.conf`, `modules.order`, kopierte Dateien) |

---

## Was gebaut wurde

**`mainline/patches/kernel/0091-soc-sunxi-h713-arisc.patch`** (`diff -ruN`-Form wie `0090`),
fünf Dateien:

| Datei | |
|---|---|
| `drivers/soc/sunxi/sun50i-h713-arisc.c` | neu, 1291 Zeilen |
| `include/linux/soc/sunxi/h713-arisc.h` | neu, Kernel-API + Inline-Attrappen ohne `CONFIG_` |
| `drivers/soc/sunxi/Kconfig` | `config SUN50I_H713_ARISC` (tristate, kein `default` - siehe Übergabe 2) |
| `drivers/soc/sunxi/Makefile` | `obj-$(CONFIG_SUN50I_H713_ARISC) += sun50i-h713-arisc.o` |
| `arch/arm64/boot/dts/allwinner/sun50i-h713.dtsi` | Knoten `arisc@100000` inkl. Binding-Beschreibung im Kommentar |

Der Patch **ersetzt** `0090-soc-sunxi-add-arisc-hdmi-hpd.patch`. Die `a/`-Seite ist deshalb
der Baumstand **ohne** 0090 (die beiden `arisc_hdmi/`-Zeilen in `drivers/soc/sunxi/Kconfig`
und `…/Makefile` sind darin nicht enthalten). Wird 0090 nicht aus der `series` genommen,
kollidieren die beiden Hunks.

Der Treiber tut, was doku/78 §3 B verlangt:

* `request_firmware("h713-arisc.bin")` → Takt, Reset anlegen, RX-FIFOs leeren, Abbild
  wortweise nach `0x00100000` (140 KiB, **ohne** DRAM-Schwanz - `--skip-tail` ist damit
  konstruktiv abgebildet: das Vendor-Ziel `0x48100000` ist bei uns Kernel-Text),
  Zurückvergleich, `arisc_para`, Reset lösen;
* Startup-Notify auf ch3 lesen und auf user1 Port 3 quittieren - **nur** bei
  `type == 0x90`, `result == 0` **und** `count > 0`;
* acht exportierte Funktionen als Kernel-API (Tabelle in doku/82 §6);
* debugfs `/sys/kernel/debug/h713-arisc/{status,cmd}`; `status` zeigt
  `startup_notify: acked`, `cmd` nimmt `edid`, `reset-edid`, `portmap`, `hpd`, `5v`,
  `get-edid`;
* **kein** Doorbell-Puls, **kein** `unstick`, **kein** `main_loop_alive`, **kein**
  `hpd_delay`, keine Retry-Schleife. Jede Frist endet in einem Fehlercode.

**Reihenfolge-Garantie für `0x0709xxxx`** (doku/78 §3 B, Falle): der Treiber bildet keine
Adresse in diesem Bereich ab, und `arisc_get()` liefert `-EAGAIN` für *jeden* Dienst außer
`arisc_hdmi_reset_edid()`, solange `edid_module_ready` nicht durch einen erfolgreichen
`ResetEDIDModule` gesetzt ist. Paket E kommt an den Aux-Block also nur über einen Reset,
dessen Rückgabewert es auswerten muss.

**Firmware-Datei erzeugt:** `analyse/arisc/hy310-edid.bin`, 512 B,
SHA-256 `70d10294e3f1f1ba3aceaf684c90d2dcdcafc9ba4ed265956520bdf4adfb60ef`.
Beide EDID-Blöcke haben Prüfsumme 0, Block 0 trägt `SGD SX8`, Byte 168 ist `0x10`
(die Firmware patcht es auf `0x00`). Bleibt außerhalb des öffentlichen Repos.

---

## Zwei Korrekturen an der eigenen Arbeit (beide vor dem letzten Prüfbau behoben)

1. **Kurzer Befehl nach einem EDID-Fragment wäre falsch als „nicht angekommen" gewertet
   worden.** Der 0x11-Handler kopiert *immer* 65 Byte ab Nutzlast[2]; hätte der Treiber nur
   die vier Bytes eines kurzen Befehls geschrieben, hätte der Handler den Schwanz des
   vorigen Fragments mitkopiert und der Vergleich hätte nie gepasst. Der Treiber schreibt
   jetzt immer alle 67 Puffer-Bytes, nullaufgefüllt.
2. **`RequestEDID` hätte an einer erfundenen Prüfung scheitern können.** Erste Fassung
   verlangte auch bei `0x0315` den Rahmenmarker `0xff`. Belegt ist aber nur, dass die
   *Statusantwort* (`0x0215`) gerahmt ist; die Rücklese liefert den DDC-Inhalt (doku/75,
   13:35: `ff ff ff 00 00 ff ff ff …` war der wortgedrehte ROM-Default, nicht ein Marker).
   Die Prüfung ist raus, die Bytes gehen unverändert an den Aufrufer.

---

## Prüfbau - ausdrücklich Prüfbau, **nicht** Endstand

Endstand ist `build/build.sh kernel` durch die Hauptsitzung nach Paket A. Hier nur
Compile-Checks gegen den fertigen Baum
`mainline/build/linux-6.18.38-102233d4db25e25ede21c6dbdc3d7ef6da4cdf64e65ae4372da5658b0f3dbd49`,
mit derselben Toolchain, die `build/build.sh` für den Kernel benutzt (`ARCH=arm64 LLVM=1`,
LLVM 18 wie der Baum gebaut wurde - der Container hat per Vorgabe clang 20, das erzeugt
sonst „the compiler differs from the one used to build the kernel").

```bash
podman exec h713-build bash -lc '
S=/tmp/llvm18; mkdir -p $S/bin
for t in ar nm objcopy objdump readelf strip; do ln -sf /usr/bin/llvm-$t-18 $S/bin/llvm-$t; done
ln -sf /usr/bin/clang-18 $S/bin/clang; ln -sf /usr/bin/ld.lld-18 $S/bin/ld.lld
export PATH=$S/bin:$PATH
make -C /work/mainline/build/linux-6.18.38-102233d4db25e25ede21c6dbdc3d7ef6da4cdf64e65ae4372da5658b0f3dbd49 \
     M=/work/analyse/arisc-drv ARCH=arm64 LLVM=1 W=1 modules'
```

| Prüfbau | Ergebnis |
|---|---|
| 1 - out-of-tree, `M=/work/analyse/arisc-drv` (Kopf über `-I$(src)/include`) | **grün**, `W=1`, clang 18, keine Warnung. `sun50i-h713-arisc.ko`, alle acht Symbole in `__ksymtab`, `modinfo` nennt beide Firmware-Dateien und den `of`-Alias |
| 2 - in-tree, Quelle nach `drivers/soc/sunxi/`, Kopf nach `include/linux/soc/sunxi/`, Kconfig/Makefile verdrahtet, `CONFIG_SUN50I_H713_ARISC=m`, `make M=drivers/soc/sunxi modules` | **grün**, `W=1`, keine Warnung. Prüft zusätzlich den Include-Pfad `<linux/soc/sunxi/h713-arisc.h>` und die Kconfig-Verdrahtung. Der Baum wurde danach vollständig zurückgesetzt (`Kconfig`, `Makefile`, `.config`, `syncconfig`, kopierte Dateien entfernt) |
| DTB | `sun50i-h713-hy200-qz713df-a1.dts` mit dem neuen `dtsi` übersetzt (clang -E + `scripts/dtc`): **eine** Warnung, `dec@5600000` doppelte unit-address - die steht auch ohne unsere Änderung im Baseline-Lauf. Knoten `arisc@100000` im DTB nachgelesen, `reg`/`reg-names`/`firmware-name` korrekt |
| `patch -p1 --dry-run` | sauber gegen die `a/`-Seite; der `dtsi`-Hunk zusätzlich sauber gegen die **echte** Datei im Baum geprüft |

Arbeitskopie der Quellen für spätere Prüfbauten: `analyse/arisc-drv/`
(`sun50i-h713-arisc.c`, `include/linux/soc/sunxi/h713-arisc.h`, `Makefile`).
Build-Artefakte sind aufgeräumt. **Das ist nicht der Endstand** - der Endstand ist der Patch.

Nicht geprüft, weil es nicht ohne `build.sh`/Board geht: Gesamtbau der Serie, Laufverhalten.

---

## Übergabe an die Hauptsitzung (fünf Punkte, ohne die die Abnahme nicht laufen kann)

1. **`series`:** Zeile 65 lautet (Stand 22:20, nach A's Umnummerierung)
   `0090-soc-sunxi-add-arisc-hdmi-hpd.patch`. Diese Zeile **entfernen** und dafür
   `0091-soc-sunxi-h713-arisc.patch` aufnehmen. Ich habe `series` auftragsgemäß **nicht**
   angefasst. Die Datei `0090-…` kann als Archiv liegen bleiben - sie darf nur nicht mehr
   in `series` stehen, sonst kollidieren die Kconfig-/Makefile-Hunks (0091 erwartet den
   Stand *ohne* die beiden `arisc_hdmi/`-Zeilen).
   *Restrisiko:* die `a/`-Seite von 0091 stammt aus dem Baum von 22:00. Sollte ein
   cstenger-Patch aus Paket A `drivers/soc/sunxi/Kconfig` oder `…/Makefile` anfassen
   (unwahrscheinlich, sie betreffen drm/media/audio), müssen die beiden Ein-Zeilen-Hunks
   nachgezogen werden.
2. **Kernel-Konfiguration:** in `mainline/patches/kernel/board/hy200_qz713df_a1_defconfig`
   Zeile 198 `CONFIG_HY310_ARISC_HDMI=m` → **`CONFIG_SUN50I_H713_ARISC=m`**. Der neue
   Kconfig-Eintrag hat bewusst kein `default`, damit er nicht als `=y` in den Kernel wandert:
   ein eingebauter Treiber probt, bevor das NFS-Root steht, und `request_firmware()` hätte
   dann nichts zu holen. **Modul, nicht eingebaut.**
3. **Firmware aufs Board-Root** (`/srv/h713-rootfs`, braucht `sudo` - deshalb nicht von mir):
   * `analyse/arisc/scp.bin` → `/srv/h713-rootfs/lib/firmware/h713-arisc.bin`
     (176 132 B, SHA-256 `d41731fa783dace3070264397064b28e2359a27b9e4708f3f7d40f1c3d876b7e`)
   * `analyse/arisc/hy310-edid.bin` → `/srv/h713-rootfs/lib/firmware/hy310-edid.bin`
     **ersetzt die dort liegende Datei**: die ist 256 B (nur der 1.4-Block,
     SHA-256 `4a5b6210…`) und wird vom Treiber mit einer Warnung verworfen.
4. **Modul aufs Board-Root:** `sun50i-h713-arisc.ko` aus `mainline/build/out/modules/`
   nach `/srv/h713-rootfs/lib/modules/6.18.38/kernel/drivers/soc/sunxi/`, danach
   `depmod -a -b /srv/h713-rootfs 6.18.38` (oder `depmod -a` am Board).
5. **Altes Modul stilllegen:** `/root/hy310-arisc-hdmi.ko` darf beim Abnahmelauf **nicht**
   geladen werden (es würde eine zweite Quittung senden). Die Abnahmevorschrift unten
   schneidet es zusammen mit `arisc_load.py` aus dem Prep heraus.

---

## Abnahmevorschrift (Board-Slot 2 des Nachtplans)

Voraussetzung: Punkte 1-5 oben erledigt, neuer Netboot-FIT in `tftp/`, Board-Sperre gesetzt.
Erwartete Gesamtdauer ab Kaltstart: ~2 min, davon 10 s HPD-low.

```bash
# ---- 0. Vorbedingungen -------------------------------------------------------
ss -ulnp | grep -w :69                       # TFTP muss lauschen; sonst STOPP + Log
echo "$(date +%F_%T) hauptsitzung B" > /tmp/claude-1000/h713-board.lock

# Positivkontrolle am Zuspieler VOR dem Lauf (Memory: messung-instrument-erst-pruefen)
ssh user@192.168.8.162 'cat /sys/class/drm/card0-HDMI-A-2/status'    # erwartet: disconnected

# ---- 1. Kaltstart ------------------------------------------------------------
sonoff_ctl restart --host 192.168.8.179
for i in $(seq 30); do ssh -o BatchMode=yes -o ConnectTimeout=3 root@192.168.8.141 uptime && break; sleep 4; done

# ---- 2. Der Treiber, OHNE Prep-Schritt 1 ------------------------------------
# Falls das Modul nicht schon per Modalias geladen wurde:
ssh root@192.168.8.141 'modprobe sun50i-h713-arisc; lsmod | grep -c sun50i_h713_arisc'

ssh root@192.168.8.141 'dmesg | grep -i "h713-arisc"'
#   ERWARTET:  h713-arisc ...: ARISC-Startup-Notify quittiert: projector-tv303-android11-v1.3-3-g293ff69
#   NICHT ok:  "... nicht gesehen (-110)" oder "... fehlerhaft (-71)"

ssh root@192.168.8.141 'cat /sys/kernel/debug/h713-arisc/status'
#   ERWARTET (die ersten fünf Zeilen):
#     startup_notify: acked
#     firmware_version: projector-tv303-android11-...
#     arisc: running
#     edid_module: not reset
#     edid_firmware: hy310-edid.bin loaded

# ---- 3. Rest des Prep (Schritt 1 und das alte Modul herausgeschnitten) -------
ssh root@192.168.8.141 "sed -e '/arisc_load.py/d' \
    -e 's#; insmod /root/hy310-arisc-hdmi.ko 2>/dev/null##' \
    /root/prep_after_boot.sh > /root/prep_ohne_arisc.sh && sh /root/prep_ohne_arisc.sh"

# ---- 4. SetSource wie in Abschnitt 1 des Nachtplans --------------------------
ssh root@192.168.8.141 'taskset -c 1 python3 /root/hdmi_seq.py run --phase 4 --i-mean-it \
     --only setsource --source 3 --portmap stock --gap 500 --pre-source-wait 1 --listen-after 3'

# ---- 5. Die EDID-/HPD-Folge AUS DEM KERNEL ----------------------------------
ssh root@192.168.8.141 'time sh -c "echo edid > /sys/kernel/debug/h713-arisc/cmd"'
#   dauert ~11-13 s (10 s davon ist der HPD-low-Teil des Protokolls)
#   Rueckgabe 0 = alle elf Schritte quittiert. Ein Fehlercode nennt den Schritt im dmesg.

# ---- 6. Abnahme -------------------------------------------------------------
ssh user@192.168.8.162 'cat /sys/class/drm/card0-HDMI-A-2/status'
#   ERWARTET: connected      (Zeit ab Schritt 5 <= 60 s)
ssh user@192.168.8.162 'strings /sys/class/drm/card0-HDMI-A-2/edid | head'
#   ERWARTET: SGD SX8
ssh root@192.168.8.141 'cat /sys/kernel/debug/h713-arisc/status'
#   ERWARTET jetzt zusaetzlich: edid_module: ready
#                               edid_status: ff f8 01 01 ...
#                               last_command: ...
ssh root@192.168.8.141 'dmesg | grep -i "h713-arisc"'
#   ERWARTET: "EDID uebernommen, Status ff f8 01 01 ..",
#             "EDID zurueckgelesen (n B): ..",
#             "EDID/HPD-Sequenz auf Port 0 abgeschlossen"

rm -f /tmp/claude-1000/h713-board.lock
```

**Wenn es schiefgeht - was es bedeutet:**

| Befund | Bedeutung | nächster Schritt |
|---|---|---|
| `startup_notify: not seen`, `fifo_rx: ch3` ungleich 0 | die Notify liegt da, wurde aber nicht gelesen → Fensteradressen/Mapping | `status` mitschneiden, `busybox devmem 0x0300306c` |
| `startup_notify: not seen`, `fifo_rx: ch3 = 0`, `R_CPUCFG` = 1 | Kern läuft, aber es kam nie eine Notify → Abbild/Para | `dmesg` auf „Firmware-Abbild stimmt nicht"; `busybox devmem 0x00100100` gegen `scp.bin` |
| `startup_notify: acked`, aber `echo edid` liefert `-ETIMEDOUT` bei ResetEDIDModule | die Firmware nimmt Port-0-Rahmen nicht an. **Erster Verdacht: der weggelassene Doorbell** (doku/82 §12.2 - „3/3 belegt" steht in doku/77/78, eine Messreihe mit Lauf-Nummern habe ich in doku/ nicht gefunden). Das ist dann eine **Messung**, kein wieder eingebauter Puls | `status` vor/nach dem Versuch; `fifo_tx: port0` beobachten |
| `-EBUSY` | Msgbox-FIFO Port 0 läuft voll → die Pumpe holt nicht ab, meist eine hängende Hauptschleife | Kaltstart, Log; **nicht** mit Nullwörtern „befreien" |
| ThinkPad bleibt `disconnected`, aber alle Schritte quittiert | HPD kam, EDID nicht angenommen | `get-edid 0` und die ersten 16 Byte im Log ansehen: `00 ff ff ff` = plain (gut), `ff ff ff 00` = wortgedreht (Upload hat nicht gegriffen) |

**Nicht anfassen** während der Abnahme: `0x0709xxxx` von Hand lesen (SoC-Hänger, solange
`edid_module: not reset` steht), INCAP-Register, Descriptor zweimal.

---

## Board-Anfrage

1. **Board-Slot 2 (Hauptaufgabe):** die Abnahmevorschrift oben, ein Durchlauf nach
   Kaltstart. Ergebnis bitte mit `status`-Abzug vor und nach Schritt 5 und dem
   `dmesg | grep h713-arisc` in
   `re/captures/weltneuheit/ours-20260907-nacht/B/` ablegen.
2. **Falls Slot-Zeit übrig ist, zwei kleine Messungen, die Doku-Lücken schließen:**
   * *HPD-low-Dauer:* nach erfolgreicher Abnahme `hpd 0 down`, 200 ms warten, `hpd 0 up`,
     und sehen, ob der ThinkPad trotzdem neu erkennt. Damit wäre belegt, ob die 10 s des
     Stock-Skripts nötig sind oder ob die HDMI-Mindestzeit von 100 ms reicht
     (doku/82 §8). **Nur mit Zeitpuffer** - die 10 s sind der belegte Wert und bleiben
     im Code, bis eine Messung etwas anderes zeigt.
   * *5-V-Detect (K4):* bei laufendem Treiber am ThinkPad `xrandr --output HDMI-2 --off`
     und wieder `--auto`, dann `cat /sys/kernel/debug/h713-arisc/status` - ändern sich die
     `hpd_counter`, ohne dass der Kernel etwas geschickt hat? Das beantwortet doku/77 §2.1
     („Offen und zu belegen") für Paket E.
3. **Kein weiterer Board-Bedarf für Paket B.**
