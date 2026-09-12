# D+E — Vsync-Notifier: eine Eigentümerschaft für `0x05600320/324`

**Nacht 07.09.2026, ab ~06:00, abgeschlossen 06:27.** Auftrag: die Doppel-Eigentümerschaft an den AFBD-Flip-Zeigern
beseitigen. Der Anzeigetreiber (Paket D, Patch `0093`) exportiert einen Vsync-Notifier, der
V4L2-Treiber (Paket E, Patch `0094`) hängt sich daran, statt sich das Registerfenster selbst
abzubilden.

Grundlage: [78-nachtplan-hdmi-switch.md](../78-nachtplan-hdmi-switch.md) §0 Regel 1 (keine
Workarounds, saubere Kernel-Schnittstellen), §2 und Anhang A.4 (der Kernel besitzt die
Orchestrierung), [nachtlog/E-v4l2.md](E-v4l2.md) §8 („Anfrage an Paket D"),
[nachtlog/K1-K3-re.md](K1-K3-re.md) (kein ARM-seitiger Capture-Interrupt; der AFBD-Vsync ist GIC 142).

**Kein Board angefasst.** Alles offline: Quelltext, Patches, Prüfbau, Dokumentation.

Ergebnisdateien:

* `mainline/patches/kernel/0093-drm-h713-afbd-nv16-hdmi-ring.patch` (Erzeuger + neuer Header)
* `mainline/patches/kernel/0094-media-sun50i-h713-hdmirx.patch` (Verbraucher, zweite Abbildung raus)
* [86-video-plane-nv16.md](../86-video-plane-nv16.md) §2.2 und neuer §5.1
* [88-v4l2-hdmirx.md](../88-v4l2-hdmirx.md) §5, §7, §8 („DV-Timings" und „Offen" Punkt 7)

`patches/kernel/series` blieb unangetastet (71 Zeilen, Reihenfolge `0093` vor `0094` vor `0095`).

---

## 1. Der Befund, der das ausgelöst hat

`0094` hatte einen eigenen DT-Knoten mit `reg = <0x05600320 0x8>` und darüber:

```c
	/*
	 * The flip pointer window. Mapped, not claimed: ...
	 */
	rx->flip = devm_of_iomap(dev, dev->of_node, 0, NULL);
```

`devm_of_iomap()` ruft intern `devm_ioremap_resource()` und **beansprucht** die Region. Der Kommentar
beschrieb also eine Absicht, die der Aufruf nicht einlöst. Da `display@5600000` (`0093`,
`reg = <0x05600000 0x400>`) die Region schon hält — `/proc/iomem`:
`05600000-056003ff : 5600000.display afbd` — liefert der Aufruf `-EBUSY` und der Probe scheitert hart.

Und selbst wenn er ginge, wäre er die falsche Form: zwei Treiber, die dasselbe rotierende Zeigerpaar
abtasten, jeder mit eigener Zerrissen-Behandlung, einer davon aus einem Timer, der vom Vsync nichts
weiß. Der Anzeigetreiber liest `0x320/0x324` ohnehin in **jedem** Vsync für seine Ring-Folge.

---

## 2. Die Entwurfsentscheidung

### 2.1 `notifier_block`-Kette, nicht Callback-Registrierung

Gewählt: eine **atomare Notifier-Kette** (`ATOMIC_NOTIFIER_HEAD`), `include/linux/soc/sunxi/h713-afbd.h`.

```c
#define H713_AFBD_EVENT_FLIP	1

struct h713_afbd_flip { u32 y; u32 c; };

int h713_afbd_register_flip_notifier(struct notifier_block *nb);
int h713_afbd_unregister_flip_notifier(struct notifier_block *nb);
int h713_afbd_read_flip(struct h713_afbd_flip *flip);
```

Gründe:

* Es ist der übliche Kernel-Weg und genau das, was E selbst angefragt hatte (E-v4l2 §8).
* `atomic_notifier_call_chain()` ist aus dem harten Interrupt heraus erlaubt und **alloziert nicht**;
  `atomic_notifier_chain_unregister()` wartet auf einen gerade laufenden Handler, damit „nach `stop()`
  kommt kein Ereignis mehr" ohne eigenes Sperrgeflecht gilt.
* Kette und Verbraucherzähler sind **statisch**, nicht am Gerät. Damit kann sich ein Verbraucher auch
  abmelden, nachdem `display@5600000` entbunden wurde, und der Vsync-Handler kann „schaut überhaupt
  jemand zu?" beantworten, ohne das Gerät anzufassen.

### 2.2 Die Nutzlast: das rohe Paar, kein Slot-Index

Der Auftrag ließ „Index 0..2 **und/oder** die rohen Werte" offen. Es sind die rohen Werte. Die
Slot-Tabelle (`0x4c3ef000`/`0x4c5ee000`/`0x4c7ed000` …) ist **gemessenes Wissen der Capture**; der
Anzeigetreiber kennt nur die Grenzen von `mips_framebuf`. Ein Index in der Nutzlast hieße, diese
Tabelle in den Anzeigetreiber zu kopieren — zwei Wahrheiten statt einer. Das Paar nennt den fertigen
Slot ohnehin über seine Adresse; E hat mit `h713_hdmirx_slot_of()` die Umrechnung schon.

### 2.3 Die Zerrissen-Logik bleibt beim Erzeuger — und wird zur Änderungsmeldung

`h713_afbd_follow_ring()` heißt jetzt `h713_afbd_vsync_flip()` und liest das Paar **einmal** pro
Vsync für zwei Abnehmer:

1. Y lesen, C lesen, Y noch einmal lesen; hat Y sich bewegt, Probe verwerfen.
2. Beide Adressen gegen die Ring-Grenzen prüfen.
3. Ist Y gleich dem letzten Wert: nichts.
4. Sonst: Plane bedienen (wenn `hdmi-ring` an) **und** die Kette rufen.

Der Verbraucher bekommt also nur echte Wechsel und braucht weder das dreifache Lesen noch ein eigenes
„hat sich was getan". Die Logik existiert genau einmal, im Treiber, dem das Fenster gehört.

### 2.4 `h713_afbd_read_flip()` — die dritte Funktion, und warum sie nötig ist

`ENUM_INPUT` und `QUERY_DV_TIMINGS` fragen „liegt ein Signal an?", **während nicht gestreamt wird** —
also ohne angemeldeten Notifier. Ohne diese Funktion müsste E dafür doch wieder selbst lesen, und die
zweite Abbildung wäre durch die Hintertür zurück. Rückgaben:

| Rückgabe | Bedeutung |
|---|---|
| `0` | Paar gültig |
| `-EAGAIN` | zerrissen oder außerhalb des Rings (= kein Signal) |
| `-EPROBE_DEFER` | Treiber da, `display@5600000` noch nicht gebunden |
| `-ENODEV` | Anzeigetreiber gar nicht im Kernel (Stub im Header) |

Genau diese Unterscheidung ist auch die Antwort auf die Auftragsforderung „sauber melden": E ruft die
Funktion **einmal im Probe** und reicht `-EPROBE_DEFER` bzw. `-ENODEV` per `dev_err_probe()` weiter.

### 2.5 Die Vsync-Maske bekommt zwei Nutzer statt einer Vblank-Referenz

Der Vsync-Interrupt war bisher maskiert, bis DRM eine Vblank-Referenz nahm. Ein
`drm_crtc_vblank_get()` beim Anmelden wäre die kürzeste Lösung gewesen — aber es scheitert mit
`-EINVAL`, sobald der CRTC aus ist (`drm_crtc_vblank_off()` hält eine interne Sperr-Referenz). Dann
würde `STREAMON` an einem Zustand der Anzeige scheitern, den der Verbraucher weder kennt noch
beeinflusst.

Stattdessen leitet `h713_afbd_vsync_irq_update()` das Maskenbit `+0x0C4` Bit 0 aus **beiden** Nutzern
ab: `h->vblank_on` (aus `enable_vblank`/`disable_vblank`) **oder** `h713_afbd_flip_users > 0`.
`drm_crtc_handle_vblank()` verträgt es, wenn der Interrupt läuft, während DRM den Vblank für
abgeschaltet hält — es kehrt einfach zurück. Sperrreihenfolge: `vbl_lock` → `h713_afbd_flip_lock`; die
umgekehrte Reihenfolge kommt nirgends vor.

**Kein Verbraucher = kein Mehraufwand:** ohne angemeldeten Notifier und ohne Ring-Folge liest der
Handler das Zeigerpaar nicht einmal, und die Maske steht wie vorher.

### 2.6 Der 120-Hz-`hrtimer` fliegt ersatzlos raus

Nicht als Rückfall hinter einem Modulparameter, auch nicht mit Vorgabe „aus":

* Er tastete mit einer Rate ab, die mit dem gesuchten Ereignis nichts zu tun hat: die Hälfte der
  Weckrufe fand nichts, die andere fand einen Slot, der bis zu 8 ms vorher fertig war.
* Es gibt **keine** Lage, in der er die bessere Wahl wäre. Ohne `0093` gibt es keine Plane, keinen
  VidDec-Descriptor und keine Ring-Grenzen — es ist nichts da, worauf man zurückfallen könnte.
* Ein Abtasttakt, der still neben dem echten Ereignis herläuft, ist genau der Quirk, den §0 Regel 1
  verbietet.

Die Abstraktion `struct h713_hdmirx_slot_source` **bleibt**: sie ist die Naht, an der ein echter
Capture-Interrupt (falls K2 je einen findet) einsteigen könnte, ohne die Warteschlangenbehandlung zu
berühren. Sie hat jetzt genau eine Implementierung, `h713_hdmirx_vsync`.

### 2.7 Der DT-Knoten verliert `reg` — und zieht um

Ohne Registerfenster hat der Knoten keine Einheitsadresse mehr: aus `hdmi-rx@5600320` wird `hdmi-rx`.
Er kann dann aber nicht in `soc { compatible = "simple-bus"; }` bleiben — nachgestellt im Prüfbau:

```
sun50i-h713.dtsi:1888.32-1890.5: Warning (simple_bus_reg): /soc/hdmi-rx-probe:
    missing or empty reg/ranges property
```

Er steht deshalb auf der Wurzelebene neben `sound`, wo `of_platform_default_populate()` genauso ein
Plattformgerät anlegt. `memory-region`/`memory-region-names` (`hdmi-ring`, `cpu-comm-shmem`) bleiben
unangetastet.

---

## 3. Was in `0094` entfallen ist

| Entfallen | Ersatz |
|---|---|
| `void __iomem *flip` im Gerätezustand | — |
| `devm_of_iomap(dev, dev->of_node, 0, NULL)` + der Kommentar „Mapped, not claimed" | Probe-Prüfung über `h713_afbd_read_flip()` |
| `#define H713_FLIP_Y/H713_FLIP_C` | `struct h713_afbd_flip` |
| `h713_hdmirx_read_flip()` (dreifaches Lesen, Ring-Prüfung) | steht beim Erzeuger |
| `hrtimer sample_timer`, `H713_SAMPLE_NS`, `h713_hdmirx_sample()`, `…_sampler_start/stop`, `h713_hdmirx_sampler` | `h713_hdmirx_vsync` (Notifier an-/abmelden) |
| Zähler `stat.torn` | verworfene Proben zählt der Erzeuger nicht mehr weiter; neu: `stat.events` |
| `reg` am DT-Knoten, Einheitsadresse `@5600320` | keiner |
| `#include <linux/hrtimer.h>` | `<linux/notifier.h>`, `<linux/soc/sunxi/h713-afbd.h>` |
| `H713_HDMIRX_FPS` (nur noch vom Abtasttakt benutzt) | — |

Neu dazu: `struct notifier_block flip_nb`, `h713_hdmirx_flip_notify()`,
`depends on DRM_SUN50I_H713_AFBD` in Kconfig, `stat.events` und die debugfs-Zeile `vsync:`.

`h713_hdmirx_slot_event()` bekommt das Paar jetzt als Argument (`const struct h713_afbd_flip *`) statt
es zu lesen; die Warteschlangenlogik darin ist **Zeile für Zeile unverändert**.

---

## 4. Prüfbau — **ausdrücklich ein Prüfbau, kein Endstand**

`build/build.sh` wurde **nicht** aufgerufen; der Originalbaum wurde nicht verändert. Stattdessen ein
frischer Baum aus dem gepinnten Tarball, die `series` darauf angewandt, gebaut im Container
`h713-build` mit denselben Variablen wie `build/build.sh` (`ARCH=arm64 LLVM=1`, clang 20.1.8), dazu
`W=1`:

```bash
tar -C s0 --strip-components=1 -xf mainline/build/cache/linux-6.18.38.tar.xz
# alle 71 Zeilen der series, in Reihenfolge
podman exec h713-build bash -lc 'cd /work/mainline/build/pruefbau-de-vsync && \
  make ARCH=arm64 LLVM=1 hy200_qz713df_a1_defconfig && \
  make ARCH=arm64 LLVM=1 -j24 W=1 drivers/gpu/drm/tiny/ \
       drivers/media/platform/sunxi/sun50i-h713-hdmirx/ && \
  make ARCH=arm64 LLVM=1 -j24 Image dtbs modules'
```

Ergebnis:

| Prüfung | Ergebnis |
|---|---|
| `0093` und `0094` auf frischen Baum | sauber, **kein Offset, kein Fuzz** |
| `0095` danach | wie vorher: 9 Hunks mit Offset/Fuzz — **identisch zum Zustand ohne diese Änderung** (gegengeprüft), also nicht verschlimmert |
| `W=1` auf `drivers/gpu/drm/tiny/` und `.../sun50i-h713-hdmirx/` | **keine Warnung** |
| Voller Bau `Image dtbs modules` | grün, keine Warnung, kein Fehler |
| Symbole des Erzeugers | `Module.symvers`: `h713_afbd_register_flip_notifier`, `h713_afbd_unregister_flip_notifier`, `h713_afbd_read_flip` — alle `EXPORT_SYMBOL_GPL` aus `sun50i-h713-afbd` |
| Auflösung beim Verbraucher | `llvm-nm -u …hdmirx.ko` zeigt die drei als `U`; `depends=hy310-cpu-comm,sun50i-h713-afbd,sun50i-h713-arisc` |
| Kconfig | `CONFIG_VIDEO_SUN50I_H713_HDMIRX=m` überlebt die neue `depends on` |
| DTB, `W=1 dtbs` | beide H713-DTBs **ohne jede Warnung** (die übrigen Warnungen stammen aus `sun50i-h616.dtsi`/`sun55i-a523.dtsi`, unverändert) |

DTB zurückgelesen (`scripts/dtc/dtc -I dtb -O dts`):

```dts
	hdmi-rx {
		compatible = "allwinner,sun50i-h713-hdmirx";
		memory-region = <0x24 0x26>;
		memory-region-names = "hdmi-ring", "cpu-comm-shmem";
		status = "okay";
	};
```

Kein `reg`, keine Einheitsadresse, auf der Wurzelebene, Phandles aufgelöst.

Die Baumkopie (`mainline/build/pruefbau-de-vsync`) ist **nach dem Lauf gelöscht**.

---

## 5. Abnahmevorschrift (kopierbar)

Sie ergänzt [E-v4l2.md §6](E-v4l2.md); alles dort Beschriebene gilt weiter. Neu ist nur, **woran man
sieht, dass der Notifier trägt**. Auf dem Board gibt es **kein `v4l2-ctl` und kein `modetest`** —
gebraucht wird beides auch nicht. (`gamma_test` gehört zu `0095` und braucht
`--karte /dev/dri/card1`; für diese Abnahme ist es nicht nötig.)

**Voraussetzungen:** `0091`–`0095` in der `series`, `build/build.sh kernel` grün, FIT in `tftp/`,
Module und `hy310-hdcp22.bin`/`hy310-edid.bin` auf dem Board, `depmod -a` gelaufen.

```bash
# --- 0. Vorbedingungen (Arbeitsrechner) -------------------------------------
ss -ulnp | grep -w :69 || { echo "TFTP laeuft nicht -- STOPP, Nachtlog, nicht reparieren"; exit 1; }

# --- 1. Kaltstart, KEIN prep_after_boot.sh ----------------------------------
sonoff_ctl restart --host 192.168.8.179
for i in $(seq 30); do ssh -o BatchMode=yes -o ConnectTimeout=3 root@192.168.8.141 uptime && break; sleep 4; done

# --- 2. Haengt der Verbraucher am Erzeuger? ---------------------------------
ssh root@192.168.8.141 'lsmod | grep -E "sun50i-h713-(afbd|hdmirx)"'
# erwartet: sun50i_h713_afbd ... 1 sun50i_h713_hdmirx     <- Benutzerzahl 1, nicht 0
ssh root@192.168.8.141 'dmesg | grep hdmirx | tail -5'
# erwartet: sun50i-h713-hdmirx ...: /dev/video0, Slot-Quelle: AFBD vsync notifier (GIC 142)
# NICHT erwartet: "kein AFBD-Vsync-Notifier ..."  und NICHT "-EBUSY"

# --- 3. Der eigentliche Beleg: zaehlt der Notifier? -------------------------
ssh root@192.168.8.141 'cat /sys/kernel/debug/sun50i-h713-hdmirx/status'
```

Erwartet, mit Signal am Eingang:

```
slot-quelle:  AFBD vsync notifier (GIC 142)
flip:         y=0x4c5ee000 c=0x4cbeb000 slot=1
signal:       vorhanden (Flip-Zeiger wandern)
streaming:    nein
vsync:        0 Ereignisse, zuletzt y=0x00000000 c=0x00000000 slot=-1
frames:       0 geliefert, ...
```

`vsync:` steht auf 0, solange nicht gestreamt wird — **das ist richtig so**: erst `STREAMON` meldet
den Notifier an. Der Beweis ist der Lauf:

```bash
# --- 4. 300 Bilder holen, danach die Zaehler lesen --------------------------
ssh root@192.168.8.141 '/root/hdmirx_test /dev/video0 300 /root/hdmi300.nv16m; echo rc=$?'
ssh root@192.168.8.141 'cat /sys/kernel/debug/sun50i-h713-hdmirx/status | grep -E "^vsync|^frames"'
```

**Die Abnahme ist bestanden, wenn:**

1. `vsync:` ist nach dem Lauf **≈ 300 + wenige**, nicht 0 und nicht ein Vielfaches davon. Bei 60 Hz
   Bildrate und 60 Hz Vsync ist ein Ereignis pro Bild die Erwartung. `vsync: 0` heißt: der Notifier
   trägt nicht (siehe Tabelle unten).
2. `zuletzt y=…` nennt eine der drei Slot-Adressen und `slot=` liegt in 0..2.
3. `frames:` zeigt `300 geliefert` und `uebersprungen` **klein** (< 10). Der 120-Hz-Abtasttakt hatte
   hier strukturell Verluste; mit dem Vsync darf es keine mehr geben. Ein großer `uebersprungen`-Wert
   gehört ins Log, **nicht** in eine Nachbesserung am Takt.
4. `unveraendert` ist **0**. Zählt es, melden Erzeuger und Verbraucher unterschiedliche Vorstellungen
   davon, was „geändert" heißt — ein Fehler, kein Rauschen.

```bash
# --- 5. Gegenprobe "kein Verbraucher = kein Mehraufwand" --------------------
ssh root@192.168.8.141 'grep h713-afbd /proc/interrupts; sleep 5; grep h713-afbd /proc/interrupts'
```

Im Ruhezustand (kein Streaming, keine Plane im Passthrough, kein KMS-Client) darf der Zähler
**stehen bleiben**. Während `hdmirx_test` läuft, muss er um ~60/s steigen — dieselbe Messung, zwei
Aussagen.

```bash
# --- 6. Signalverlust ------------------------------------------------------
ssh user@192.168.8.162 'DISPLAY=:0 xrandr --output HDMI-2 --off'; sleep 3
ssh root@192.168.8.141 'cat /sys/kernel/debug/sun50i-h713-hdmirx/status | grep -E "^flip|^signal"'
ssh user@192.168.8.162 'DISPLAY=:0 xrandr --output HDMI-2 --auto'
```

Erwartet ohne Signal: `signal: kein Signal (Flip-Zeiger stehen)`. Die `flip:`-Zeile kommt weiterhin —
sie geht jetzt über `h713_afbd_read_flip()` an den Anzeigetreiber, nicht mehr über ein eigenes
Fenster.

### Wenn etwas schiefgeht

| Beobachtung | Deutung | Nächster Schritt |
|---|---|---|
| `dmesg`: `kein AFBD-Vsync-Notifier …` mit `-517` | `-EPROBE_DEFER`: `display@5600000` war noch nicht gebunden | normal beim Booten, muss sich von selbst auflösen; bleibt es stehen, ist `0093` gar nicht gebunden (`dmesg \| grep afbd`) |
| `dmesg`: `kein AFBD-Vsync-Notifier …` mit `-19` | `-ENODEV`: `CONFIG_DRM_SUN50I_H713_AFBD` nicht gesetzt | Kernelkonfiguration, kein Treiberfehler |
| `insmod`: `Unknown symbol h713_afbd_read_flip` | Anzeigetreiber nicht geladen | `modprobe` statt `insmod`, `depmod -a` |
| `vsync: 0 Ereignisse`, aber `flip:` wandert | Interrupt kommt nicht an: Maske oder IRQ | `grep h713-afbd /proc/interrupts` — steht der Zähler, ist es die Maske; steigt er, ist es die Kette |
| `frames: … uebersprungen` groß, `vsync:` passt | Puffer werden nicht schnell genug zurückgegeben | Userspace, nicht der Notifier |
| `flip: nicht lesbar (-11)` | `-EAGAIN`: Capture nie scharfgemacht oder kein Signal | Anhang A.5, **Kaltstart** |
| `flip: nicht lesbar (-517)` | Anzeigetreiber weg (entbunden) | `dmesg \| grep afbd` |

---

## 6. Offen

1. **Alles davon ist ungefahren.** Der Notifier ist gebaut, geprüft und nie gelaufen. Punkt 3 und 5
   der Abnahme sind die zwei Messungen, die ihn belegen.
2. **Ein Vsync = ein Bild?** Erwartet ja (Capture 60 Hz, Panel 60 Hz), aber ungemessen. Weichen die
   beiden Takte voneinander ab, zeigt sich das an `uebersprungen` — und dann ist die Frage, ob die
   Firmware zwei Slots pro Vsync fertigstellt, keine Frage des Notifiers.
3. **`0095` sitzt weiter mit Fuzz auf `0093`.** Nicht durch diese Änderung entstanden und nicht
   angefasst; wer `0095` das nächste Mal anfasst, sollte die Hunks nachziehen.
4. **Paket F** (`hy310-tv`) bekommt die Slots weiter über `MMAP`, nicht als dma-buf; A.4 verlangt
   irgendwann `VIDIOC_EXPBUF` und einen Plane-Import. Davon ist hier nichts vorweggenommen: die
   Plane-Eigenschaft `hdmi-ring` bleibt der Übergangsweg, und der Notifier ist von ihr unabhängig.
