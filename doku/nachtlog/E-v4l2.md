# Paket E — V4L2-Treiber `sun50i-h713-hdmirx` (offline: Gerüst + Probe-Sequenz)

**Agent:** Unteragent E (offline). **Kein Board angefasst:** kein `ssh root@192.168.8.141`, kein
`ssh user@192.168.8.162`, kein `sonoff_ctl`, kein `wandcheck.py`, kein `tio`, kein `scp`, nichts nach
`tftp/`. Kein `sudo`, kein `git commit`/`push`. **`patches/kernel/series` nicht angefasst**,
`build/build.sh` nicht aufgerufen. **Kein INCAP-Register geschrieben — und auch keines gelesen**
(siehe §5). Uhrzeiten vom Arbeitsrechner (`date '+%H:%M'`), 06./07.09.2026.

> **Überholt am 07.09.2026, 06:27 — [DE-vsync-notifier.md](DE-vsync-notifier.md).** Die Anfrage aus §8
> ist erledigt: Paket D exportiert den Vsync-Notifier, E hängt daran. Damit sind der 120-Hz-`hrtimer`
> aus §4, die eigene Abbildung der Flip-Zeiger und das `reg` am DT-Knoten weg. In der
> Abnahmevorschrift §6 heißt die Zeile jetzt `slot-quelle:  AFBD vsync notifier (GIC 142)`, es gibt
> keinen Zähler `zerrissen` mehr und dafür eine Zeile `vsync:`; §3d ist gegenstandslos. Alles Übrige
> gilt unverändert.

## Ergebnisdateien

| Datei | sha256 |
|---|---|
| `mainline/patches/kernel/0094-media-sun50i-h713-hdmirx.patch` | `8e0234a306b7404fa8116473026be6eb9decfc379175463fff0d0dfd5967f529` |
| `doku/88-v4l2-hdmirx.md` | Probe-Sequenz, Callback-Layouts, Puffermodell, Zustände, offene Punkte |
| `analyse/hdmirx-drv/` | Arbeitskopie der Quelle + Prüfbau-Makefile (kein Endstand) |
| `analyse/v4l2/hdmirx_test.c` + `hdmirx_test` (arm64, statisch) | `7816179f09ccd92465e48b81f48fb1f1374ae2d69b24d2e44f3fc682c590fc93` |
| `analyse/v4l2/build.sh`, `analyse/v4l2/compat/` | Bauskript und Ersatzköpfe für den freistehenden Bau |

**Nicht** in `series` eingetragen — das macht die Hauptsitzung (Nummernvertrag: 0094 = E).

---

## 1. Ablauf

| Zeit | Schritt |
|---|---|
| 22:15 | Nachtplan 78 **vollständig** gelesen, insbesondere §0, §0b, §3 „E" und **Anhang A** (A.1 sieben Stufen, A.2 Stufen 3/5/6, A.4 Zielbild, A.5 Fehlerbilder, A.6 offene Punkte); `nachtlog/00-koordination.md` inkl. Nachtrag 22:15; `nachtlog/K4-hotplug.md` |
| 22:18 | `analyse/hdmi-seq/hdmi_seq.py` Z. 640–880 (Step-Tabelle, `name2id`, WCE-/HDCP-Aufbau, Empfänger), `signal_info_buf.py`, `mainline/docs/reference/cpu-comm-call-table.md` |
| 22:20 | **Wichtiger Fund:** B und C sind schon fertig — `0091`/`0092` liegen in `patches/kernel/`, die Kopfdateien in `analyse/arisc-drv/include/` und `analyse/cpu-comm-api-pruefbau/include/`. Also **nicht gegen angenommene, sondern gegen die echten Signaturen** programmiert (§2) |
| 22:22 | `nachtlog/K1-K3-re.md` und `doku/84`: **K2 ist beantwortet** — es gibt auf dem ARM keinen Capture-Interrupt. Das entscheidet den Entwurf der Slot-Quelle |
| 22:24 | `0093` (Paket D) gelesen: Ring-Bindung über `memory-region-names`, Lesemuster für das Flip-Paar. Beides übernommen, damit E und D dieselbe Sprache sprechen |
| 22:26–22:32 | Treiber geschrieben (`analyse/hdmirx-drv/sun50i-h713-hdmirx.c`, 1716 Zeilen mit Kommentaren) |
| 22:33–22:36 | Prüfbau 1 out-of-tree; zwei Fehler behoben (`<linux/v4l2-dv-timings.h>` fehlte; `wait_prepare`/`wait_finish` sind seit 6.9 überflüssig, vb2 fällt auf `q->lock` zurück) |
| 22:37 | DT-Knoten gesetzt, Kconfig/Makefile verdrahtet, Patch erzeugt, gegen vier Bäume trocken geprüft |
| 22:38 | DTS-Übersetzung mit dem neuen Knoten, gegen Baseline verglichen |
| 22:39–22:41 | Abnahmeprogramm `hdmirx_test` freistehend für arm64 gebaut und unter `qemu-aarch64-static` angetestet |
| 22:43–22:47 | `doku/88-v4l2-hdmirx.md` und dieses Teillog |
| 22:46 | Nachlese: `VIDIOC_CREATE_BUFS` wieder entfernt — bei einem festen Ring gibt es nichts, worauf ein vierter Puffer zeigen könnte, und ein Aufruf, der nur mit `-EINVAL` enden kann, gehört nicht in die Schnittstelle. Patch neu erzeugt und alle Prüfungen wiederholt |

---

## 2. Angenommene Signaturen aus B und C — **es sind die echten**

Der Auftrag sagte, gegen die vom Nachtplan festgelegten Köpfe zu programmieren und die Annahmen zu
protokollieren. Beide Köpfe existierten zu diesem Zeitpunkt bereits als Ergebnis von B und C. Der
Treiber ist deshalb gegen **diese Dateien** übersetzt worden, nicht gegen Platzhalter:

* `analyse/cpu-comm-api-pruefbau/include/linux/soc/sunxi/h713-cpu-comm.h` (aus Patch **0092**)
* `analyse/arisc-drv/include/linux/soc/sunxi/h713-arisc.h` (aus Patch **0091**)

Kopien liegen für den Prüfbau unter `analyse/hdmirx-drv/include/linux/soc/sunxi/`. **Beim
Zusammenführen abgleichen:** ändern B oder C noch etwas, sind das die Berührungspunkte.

### Aus Paket C benutzt

```c
int cpu_comm_call(u32 comp_id, const u32 *args, unsigned int nargs,
                  u32 *ret, unsigned int nret, unsigned int timeout_ms);
int cpu_comm_register_callback(u32 comp_id, cpu_comm_cb_t fn, void *ctx);
int cpu_comm_unregister_callback(u32 comp_id, cpu_comm_cb_t fn);
u32 cpu_comm_name2id(const char *base_name, unsigned int target_cpu);

typedef void (*cpu_comm_cb_t)(u32 comp_id, const u32 *args,
                              unsigned int nargs, void *ctx);
```

Verlassen wird sich außerdem auf drei **zugesicherte Eigenschaften** aus dem Kopf:

1. `cpu_comm_call()` meldet **nie** Erfolg ohne Antwort; `-ETIMEDOUT` bei Fristablauf,
   **`-EAGAIN`**, solange der Coprozessor die Anwendungsbereitschaft nicht erreicht hat. Der Probe
   macht daraus `-EPROBE_DEFER` — das ist der einzige Ort, an dem ein Fehler nicht sofort tödlich ist.
2. `-EBUSY`, wenn die Aufrufslots erschöpft sind. Der Treiber **drosselt nicht** und **wiederholt
   nicht**, er scheitert mit dieser Meldung (Pflichtliste: kein `--gap`).
3. Callbacks laufen im Prozesskontext auf der Empfangs-Workqueue, dürfen schlafen, verzögern dabei
   aber die Quittung, und dürfen **nicht** `cpu_comm_call()` rufen. Beide Handler halten sich daran:
   Rohwörter unter Spinlock ablegen, V4L2-Ereignis einreihen, fertig.
4. `CPU_COMM_MAX_ARGS` = 10, `CPU_COMM_CPU_MIPS` = 1, `CPU_COMM_CPU_ARM` = 0.

### Aus Paket B benutzt

```c
int arisc_hdmi_edid_init(unsigned int port, const void *edid, size_t len);
int arisc_hdmi_get_edid(unsigned int port, void *buf, size_t len);   /* liefert Byteanzahl */
int arisc_hdmi_hpd(unsigned int port, enum arisc_hdmi_hpd_action action);
```

Zugesicherte Eigenschaften, auf die sich der Treiber stützt:

* `arisc_hdmi_edid_init(port, NULL, 0)` nimmt das Vorgabe-EDID des ARISC-Treibers
  (`hy310-edid.bin`) und fährt die **komplette** belegte Reihenfolge inklusive HPD DOWN → 10 s → UP.
  Der Kommentar in 0091 sagt ausdrücklich, der HDMI-RX-Treiber solle genau das im Probe tun — genau
  so ist es gebaut. Wegen der zehn Sekunden hat der Treiber
  `.probe_type = PROBE_PREFER_ASYNCHRONOUS`.
* `ARISC_HDMI_EDID_SIZE` = 512 (1.4-Block + 2.0-Block), `ARISC_HDMI_PORTS` = 3, unsere Buchse ist
  Port 0.
* Die Aux-Reihenfolge-Sperre (`0x0709xxxx` erst nach `ResetEDIDModule`) wird **im ARISC-Treiber**
  durchgesetzt; E bildet keine Adresse in diesem Bereich ab und ruft `arisc_hdmi_reset_edid()` nicht
  selbst — `edid_init()` tut es als ersten Schritt.
* `arisc_hdmi_get_edid()` liefert die Byteanzahl und darf **kürzer** antworten. Der Treiber wertet das
  aus und fällt auf die zuletzt geschriebene Fassung zurück, statt einen halben Datensatz zu liefern.

**Nicht benutzt** (bewusst): `arisc_hdmi_reset_edid`, `arisc_hdmi_set_portmap`, `arisc_hdmi_set_edid`,
`arisc_hdmi_audio_mode`, `arisc_hdmi_5v` — alles Teilschritte, die `edid_init()` in der richtigen
Reihenfolge selbst macht. Sie einzeln zu rufen hieße, die Reihenfolge zu verdoppeln.

---

## 3. Prüfbau — **ausdrücklich ein Prüfbau, kein Endstand**

Endstand ist `build/build.sh kernel` durch die Hauptsitzung, nachdem 0091/0092/0093/0094 in der
`series` stehen. Hier nur Compile-Checks, **out-of-tree gegen einen fertigen Serienbaum**; kein
Baubaum wurde verändert.

```bash
podman exec h713-build bash -lc '
T=/work/mainline/build/linux-6.18.38-a9eb6d695f4b8840a12c89267e7af05bbb7d37fbfe76358cd7063e5fee539ca4
make -C $T M=/work/analyse/hdmirx-drv ARCH=arm64 LLVM=1 W=1 \
     KBUILD_MODPOST_WARN=1 KCFLAGS="-DCONFIG_SUN50I_H713_ARISC=1" modules'
```

| Prüfung | Ergebnis |
|---|---|
| Übersetzen, `W=1`, clang 20 (dieselbe Version, mit der der Baum gebaut wurde) | **grün, keine einzige Warnung**; `sun50i-h713-hdmirx.ko`, AArch64 |
| dasselbe mit clang 18 | grün, keine Warnung (nur der übliche „compiler differs"-Hinweis) |
| Übersetzen **ohne** `-DCONFIG_SUN50I_H713_ARISC` (also gegen die Stub-Zweige des B-Kopfes) | grün — der Treiber baut auch, wenn 0091 nicht konfiguriert ist |
| `modinfo` | `alias of:N*T*Callwinner,sun50i-h713-hdmirx`, `firmware: hy310-hdcp22.bin`, `vermagic 6.18.38 … aarch64` |
| `patch -p1 --dry-run -F0` gegen die Bäume `a9eb6d69`, `e62e8ee3`, `102233d4`, `7dff124d` | **sauber, ohne Fuzz, in allen vieren** |
| dasselbe auf einem Stapel **0091 + 0093 + 0094** | sauber, ohne Fuzz (dtsi-Hunk mit 87 Zeilen Versatz — erwartet, 0091 und 0093 fügen davor ein) |
| DTS: `clang -E` + `scripts/dtc` auf `sun50i-h713-hy200-qz713df-a1.dts` mit dem neuen `dtsi` | **keine neue Warnung**. Die eine Warnung (`dec@5600000` doppelte unit-address) steht auch im Baseline-Lauf ohne unsere Änderung. Knoten aus dem DTB zurückgelesen und geprüft |

**Erwartete offene Enden im Prüfbau** (deshalb `KBUILD_MODPOST_WARN=1`), weil 0091/0092 noch nicht in
der `series` stehen:

```
WARNING: modpost: "cpu_comm_call"                [sun50i-h713-hdmirx.ko] undefined!
WARNING: modpost: "cpu_comm_name2id"             [sun50i-h713-hdmirx.ko] undefined!
WARNING: modpost: "cpu_comm_register_callback"   [sun50i-h713-hdmirx.ko] undefined!
WARNING: modpost: "cpu_comm_unregister_callback" [sun50i-h713-hdmirx.ko] undefined!
WARNING: modpost: "arisc_hdmi_edid_init"         [sun50i-h713-hdmirx.ko] undefined!
WARNING: modpost: "arisc_hdmi_get_edid"          [sun50i-h713-hdmirx.ko] undefined!
WARNING: modpost: "arisc_hdmi_hpd"               [sun50i-h713-hdmirx.ko] undefined!
```

Das sind **genau** die sieben Symbole aus §2 und keines mehr. Sobald 0091 und 0092 in der `series`
stehen, verschwinden sie; die Liste ist gleichzeitig die Prüfliste beim Zusammenführen.

Build-Artefakte sind aufgeräumt (`make … clean`), die Quelle bleibt in `analyse/hdmirx-drv/`.

---

## 4. Was gebaut wurde, in fünf Sätzen

1. `platform_driver` auf `allwinner,sun50i-h713-hdmirx`, ein DT-Knoten mit **acht Byte `reg`**
   (das Flip-Zeigerpaar AFBD `+0x320/+0x324`, lesend, ohne die Region zu beanspruchen) und zwei
   `memory-region`s (`hdmi-ring`, `cpu-comm-shmem`) — keine geratenen Adressen.
2. Der Probe fährt die **22 Stock-Aufrufe als Array** (`h713_hdmirx_init_seq[]`, mit
   Stock-Sessionnummer und Begründung pro Zeile) und danach die EDID/HPD-Sequenz über Paket B.
3. `VIDIOC_ENUM_INPUT`/`S_INPUT` (→ `SetSource(3)`), `S_EDID`/`G_EDID` (→ Paket B),
   `QUERY/G/S/ENUM_DV_TIMINGS`, `DV_TIMINGS_CAP`, `SUBSCRIBE_EVENT(SOURCE_CHANGE)`.
4. `vb2` mit **eigenen `mem_ops`**: Puffer *i* **ist** Slot *i*, `mmap()` reicht den Slot
   write-combining an den Nutzer, `DQBUF` liefert den fertigen Slot — **keine Kopie**. Format
   `V4L2_PIX_FMT_NV16M`, zwei Ebenen, weil Y und C `0x5FD000` auseinanderliegen.
5. `SOURCE_CHANGE` hängt direkt am `SignalChange`-Callback der Firmware; **kein Polling** auf ein
   Signal.

Begründung der Entwurfsentscheidungen (MMAP statt dma-buf, NV16M statt NV16, festverdrahtete Timings)
steht in [doku/88-v4l2-hdmirx.md](../88-v4l2-hdmirx.md) §4 und §6.

### Die kleine Schnittstelle für die Slot-Erkennung (Auftragspunkt 3)

```c
struct h713_hdmirx_slot_source {
        const char *name;                        /* steht im Log und in debugfs */
        int  (*start)(struct h713_hdmirx *rx);   /* aus start_streaming() */
        void (*stop)(struct h713_hdmirx *rx);    /* aus stop_streaming() */
};

static void h713_hdmirx_slot_event(struct h713_hdmirx *rx);  /* der eine Trichter */
```

`h713_hdmirx_slot_event()` enthält **die ganze** Logik: Flip-Paar zerrissen-sicher lesen, Slot
bestimmen, Puffer abschließen, Ausfälle zählen. Eine `slot_source` ist nur der Takt. Heute gibt es
`h713_hdmirx_sampler` — ein `hrtimer` mit 120 Hz, also doppelter Bildrate.

**Der Umstieg besteht aus einer zweiten `slot_source` und sonst nichts.** K2/K1-K3 empfehlen den
AFBD-Vsync (GIC 142), den der KMS-Treiber ohnehin hält: eine `slot_source`, die sich dort als
Notifier anmeldet und in `start()`/`stop()` an-/abmeldet, ruft im Vsync `h713_hdmirx_slot_event()`.
Dafür muss Paket D einen Notifier exportieren — **Board-unabhängige Anfrage an D**, kein Blocker für
heute. An der Warteschlangenbehandlung ändert sich dabei keine Zeile.

---

## 5. Zwei bewusste Nicht-Entscheidungen

**INCAP wird nicht einmal gelesen.** Der Zähler `0x06940104` wäre eine bequeme Lebendigkeitsanzeige.
Er ist trotzdem nicht drin: ohne Strom auf TVFE/TVCAP hängt **jeder** Zugriff auf ein HDMI-RX-Fenster
den Bus — ohne Abort, ohne Watchdog (so steht es in 0096, und so hat es der Nachtagent gemessen). Die
Reihenfolge zwischen `h713-tvcap` und diesem Treiber zu garantieren wäre eine Zusage, die der Treiber
nicht halten kann. Die Flip-Zeiger sagen dasselbe gefahrlos, weil der Anzeigetreiber ihren Block
ohnehin taktet. Schreiben ist ohnehin verboten (Regel 6).

**Der VidDec-Descriptor wird nicht geschrieben.** Er gehört laut A.4 in den Plane-Enable von Paket D
und wird genau einmal pro Boot geschrieben. E fasst weder `0x4D95F000` noch AFBD `+0x098` an.

---

## 6. Abnahmevorschrift (kopierbar)

**Voraussetzungen:** 0091 (B), 0092 (C), 0093 (D, nur für das Bild) und 0094 (E) stehen in der
`series`, `build/build.sh kernel` ist grün, die Netboot-FIT liegt in `tftp/`. Die Module
`sun50i-h713-arisc`, `hy310-cpu-comm`, `h713-tvcap` und `sun50i-h713-hdmirx` sind auf dem Board unter
`/lib/modules/$(uname -r)/`, `depmod -a` ist gelaufen. `hy310-hdcp22.bin` (= `analyse/hdcp-keys/hdcp22-key-912.bin`,
912 B) und `hy310-edid.bin` liegen in `/lib/firmware/` — **beide Dateien bleiben außerhalb des Repos.**

**Kaltstart ohne Prep-Schritte 1–3** ist der Punkt: ARISC-Laden, `cpu_comm` und die RPC-Sequenz macht
jetzt der Kernel.

```bash
# --- 0. Vorbedingungen (Arbeitsrechner) -------------------------------------
ss -ulnp | grep -w :69 || { echo "TFTP laeuft nicht -- STOPP, Nachtlog, nicht reparieren"; exit 1; }

# --- 1. Kaltstart, KEIN prep_after_boot.sh ----------------------------------
sonoff_ctl restart --host 192.168.8.179
for i in $(seq 30); do ssh -o BatchMode=yes -o ConnectTimeout=3 root@192.168.8.141 uptime && break; sleep 4; done

# --- 2. Kam der Treiber hoch? ------------------------------------------------
ssh root@192.168.8.141 'dmesg | grep -E "h713-arisc|cpu_comm|hdmirx" | tail -30'
# erwartet u.a.:  sun50i-h713-hdmirx ...: Init-Sequenz vollstaendig (22 Aufrufe)
#                 sun50i-h713-hdmirx ...: EDID/HPD-Sequenz auf Port 0 abgeschlossen
#                 sun50i-h713-hdmirx ...: /dev/video0, Slot-Quelle: flip-pointer sampling timer
ssh root@192.168.8.141 'ls -l /dev/video*'

# --- 3. Zuspieler haengt am EDID? -------------------------------------------
ssh user@192.168.8.162 'cat /sys/class/drm/card0-HDMI-A-2/status; DISPLAY=:0 xrandr | grep -A1 "^HDMI-2"'
# erwartet: connected, 1920x1080 60,00
```

### 3a. Abnahme **ohne** `v4l2-ctl` und **ohne** `modetest` — debugfs

Auf dem Board sind beide Werkzeuge nicht installiert. Der Treiber bringt deshalb eine Statusseite mit:

```bash
ssh root@192.168.8.141 'cat /sys/kernel/debug/sun50i-h713-hdmirx/status'
```

Erwartet bei stehendem Signal:

```
input:        HDMI-1 (SetSource 3)
format:       NV16M 1920x1080, 2 Ebenen a 2073600 Byte
slot-quelle:  flip-pointer sampling timer
flip:         y=0x4c5ee000 c=0x4cbeb000 slot=1        <- slot wechselt zwischen 0,1,2
signal:       vorhanden (Flip-Zeiger wandern)          <- das ist die Timing-Aussage
timings:      1920x1080p
streaming:    nein
frames:       0 geliefert, ...
SignalChange: 2 mal, Para[] 0x00000003 ...             <- Firmware hat sich gemeldet
HotPlug:      1 mal, Para[] 0x00000000
signal-info 0x4e332000: 000007800 ...                  <- ROHWOERTER, siehe unten
slot 0:       y=0x4c3ef000 c=0x4c9ec000
slot 1:       y=0x4c5ee000 c=0x4cbeb000
slot 2:       y=0x4c7ed000 c=0x4cdea000
```

Zeile `signal:` **ist** die Antwort auf „`--query-dv-timings` → 1920x1080p60": der Treiber liefert die
Timings genau dann, wenn die Flip-Zeiger wandern.

**Bitte die Zeile `signal-info …` mitschreiben** — die elf Rohwörter sind der einzige noch fehlende
Baustein, um das 44-Byte-Layout festzuschreiben (doku/88 §8 Punkt 1). Einmal bei stehendem Signal,
einmal bei abgeschaltetem Zuspieler genügt.

### 3b. Abnahme **mit** dem mitgelieferten Testprogramm

`analyse/v4l2/hdmirx_test` ist ein statisches arm64-Programm **ohne libc** — es braucht auf dem Board
nichts außer sich selbst. Es liegt gebaut bereit; neu bauen geht mit
`podman exec h713-build bash -lc '/work/analyse/v4l2/build.sh'`.

```bash
scp /opt/Projekte/h713/analyse/v4l2/hdmirx_test root@192.168.8.141:/root/
ssh root@192.168.8.141 'chmod +x /root/hdmirx_test'

# 60 Bilder NV16 holen und wegschreiben (2 x 2073600 Byte je Bild)
ssh root@192.168.8.141 '/root/hdmirx_test /dev/video0 60 /root/hdmi60.nv16m; echo rc=$?'
```

Erwartete Ausgabe (gekürzt):

```
Geraet: /dev/video0
  Treiber: sun50i-h713-hdmirx, Karte: H713 HDMI receiver
  Eingang 0: HDMI-1  Signal steht
  S_INPUT(0) = SetSource(3) angenommen
  QUERY_DV_TIMINGS: 1920x1080p, 148 MHz Pixeltakt
  Format: 1920x1080, Ebenen 2, je 2073600 Byte
  REQBUFS: 3 Puffer
  STREAMON
  Bild 1 aus Slot 0, Sequenz 0
  Bild 60 aus Slot 2, Sequenz 59
Ergebnis: 60 von 60 Bildern, 0 SOURCE_CHANGE
Datei geschrieben: /root/hdmi60.nv16m
rc=0
```

**`rc=0` genau dann, wenn alle 60 Bilder kamen.** Die Datei ist 248 832 000 Byte groß; für die
Sichtprüfung reicht ein Bild:

```bash
ssh root@192.168.8.141 '/root/hdmirx_test /dev/video0 1 /root/hdmi1.nv16m'
scp root@192.168.8.141:/root/hdmi1.nv16m /opt/Projekte/h713/re/captures/weltneuheit/ours-20260907-nacht/E/
# Rekonstruktion am Arbeitsrechner, NV16M = Ebene Y (1920x1080) + Ebene CbCr (1920x1080):
#   ffmpeg -f rawvideo -pix_fmt nv16 -s 1920x1080 -i hdmi1.nv16m -frames:v 1 rekon.png
# und das Bild ANSEHEN (Read), nicht nur die Kennzahlen.
```

### 3c. `SOURCE_CHANGE` (Zuspieler aus/an)

Das Testprogramm meldet Ereignisse während des Laufs mit. Also einen langen Lauf starten und in einem
zweiten Terminal die Quelle wackeln lassen:

```bash
# Terminal A -- laeuft ~30 s
ssh root@192.168.8.141 '/root/hdmirx_test /dev/video0 1800' &

# Terminal B, nach ein paar Sekunden
ssh user@192.168.8.162 'DISPLAY=:0 xrandr --output HDMI-2 --off'; sleep 8
ssh user@192.168.8.162 'DISPLAY=:0 xrandr --output HDMI-2 --auto'
```

Erwartet: mindestens **zwei** `SOURCE_CHANGE #…`-Zeilen (aus und wieder an) und in der Schlusszeile
`… , 2 SOURCE_CHANGE` oder mehr. Ohne das Programm geht es auch: der Zähler `SignalChange:` in
debugfs muss sich bei jedem Wackeln erhöhen.

Beim Ausschalten friert der Ring ein — das Testprogramm meldet dann
`Zeitueberschreitung: 2 s ohne Bild` und bricht ab; das ist **erwartetes** Verhalten und deckt sich
mit der Messung in K4, nicht ein Fehler des Treibers.

### 3d. Zählwerte gegenprüfen

Nach einem Lauf:

```bash
ssh root@192.168.8.141 'cat /sys/kernel/debug/sun50i-h713-hdmirx/status | grep ^frames'
```

`skipped` sollte klein sein. Ist es groß, hat der 120-Hz-Abtasttakt nicht gereicht — das ist der
Befund, der den Umstieg auf den AFBD-Vsync (§4) begründet, und gehört ins Log, **nicht** in eine
höhere Abtastrate.

### Wenn etwas schiefgeht

| Beobachtung | Deutung | Nächster Schritt |
|---|---|---|
| kein `/dev/video0`, `dmesg` zeigt `-EPROBE_DEFER` in Schleife | MIPS hat die Anwendungsbereitschaft nie erreicht (`-EAGAIN`) | Stufe 1 prüfen: `dmesg \| grep -c elog:` > 0; sonst Kaltstart |
| `Schritt N … fehlgeschlagen: -110` | `-ETIMEDOUT`, Firmware antwortet nicht | Schritt-Nummer und Stock-Session ins Log; **nicht** wiederholen |
| `Schritt N … fehlgeschlagen: -16` | `-EBUSY`, FreeCall-FIFO leer | Befund über `cpu_comm` (Paket C), **keine** Wartezeit im Treiber ergänzen |
| `hy310-hdcp22.bin nicht ladbar` | Schlüsseldatei fehlt in `/lib/firmware` | Schritt 21 wird übersprungen; für eine unverschlüsselte Quelle in Ordnung |
| `EDID/HPD-Sequenz fehlgeschlagen` | Paket B | dessen debugfs `status` lesen, nicht hier suchen |
| `flip: nicht lesbar oder ausserhalb des Rings` | Firmware hat die Capture nie scharfgemacht | Anhang A.5; **Kaltstart**, Sequenz von vorn |
| Bild vierfach gekachelt / eingefroren | Descriptor mehrfach bzw. INCAP von Hand | **Kaltstart** (A.5). Dieser Treiber schreibt beides nicht |

---

## 7. Board-Anfrage

Keine, die blockiert. Für die Abnahme ist ein Board-Slot nötig, aber **erst nach B, C und D**
(Nachtplan §4: „danach: E-Abnahme"). Drei Bitten an den Board-Agenten, wenn der Slot kommt:

1. Die Zeile `signal-info …` aus debugfs **einmal mit** und **einmal ohne** Signal mitschreiben —
   damit ist das 44-Byte-Layout entschlüsselt und die DV-Timings hören auf, festverdrahtet zu sein.
2. Die `frames:`-Zeile nach einem 60-Bilder-Lauf mitschreiben (Abtastrate gegen Vsync).
3. Ein rekonstruiertes Bild **ansehen**, nicht nur `rc=0` glauben.

## 8. Anfrage an Paket D

Für den Umstieg der Slot-Quelle vom Abtasttakt auf den Vsync (K2-Empfehlung) braucht E einen
Notifier aus `sun50i-h713-afbd` — etwas in der Art von
`h713_afbd_register_vblank_notifier(struct notifier_block *)`, gerufen im vorhandenen
Vsync-Handler (GIC 142). E meldet sich in `start_streaming()` an und in `stop_streaming()` ab.
Solange es den nicht gibt, tastet E selbst ab; funktional ist beides gleich, der Vsync ist nur
sparsamer und phasenrichtig.
