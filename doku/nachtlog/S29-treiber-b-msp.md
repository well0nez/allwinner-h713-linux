# S29 (Paket B) - Treiber `sun50i-h713-msp`: Insel, Patch, Graph, ALSA-Controls

**Auftrag:** [`doku/101-plan-audio-treiber.md`](../101-plan-audio-treiber.md) §1 B, §2, §3, §4;
Arbeitskopien `analyse/audio/arbeit/t-b-msp/{a,b}`, Basisbaum `linux-6.18.38-a3097ce7…`.
**Ergebnis:** `analyse/audio/arbeit/t-b-msp/patches/0137-ASoC-sunxi-add-the-h713-msp-audio-dsp-driver.patch`
(neu `sound/soc/sunxi/sun50i-h713-msp.c` 1563 Zeilen, Kconfig `SND_SUN50I_H713_MSP`, Makefile,
Bindung `Documentation/devicetree/bindings/sound/allwinner,sun50i-h713-msp.yaml`) und
`…/patches/0138-fragment-dts.txt` (dtsi-Knoten + Lösung der `tvtop`-Überschneidung).
**Nicht gebaut** (Auftrag §4: kein Bau des aktiven Baums). `patch -p1 --dry-run` gegen
Kopien der Originaldateien läuft sauber; `checkpatch.pl --strict` meldet 0 Fehler und die
eine erwartete Warnung „DT binding docs should be a separate patch" (die Serie wird als
Einheit eingespielt, Begründung steht im Commit-Text).

## 1. Zustandsautomat

```
                      probe                       jeder Mailbox-Timeout
   off ──────────► booting ──► patched ──► running ─────────────────► error
                      │           │           │                         │
                      └───────────┴───────────┴──► error                │
                                                     │  Insel-Reset     │
                                                     └──► booting … ◄───┘
                                                        (max. 3 Versuche)
```

| Zustand | Bedeutung | sysfs `state` |
|---|---|---|
| `off` | vor der ersten Inbetriebnahme und nach `remove` (Reset angelegt, `bus-demod` aus) | `off` |
| `booting` | Insel-Sequenz, Selbsttest, Download laufen | `booting` |
| `patched` | `0x80FF = 1` **und** `0x0001 = 0x0C19` gelesen; Graph noch nicht gesetzt | `patched` |
| `running` | Graph `0xC1` gesetzt, Controls angewandt | `running` |
| `error` | eine Stufe ist gescheitert; Selbstheilung eingeplant bzw. aufgegeben | `error` |

**Ablauf einer Inbetriebnahme** (`msp_bringup()`, immer unter `msp->lock`):
`msp_island_down()` → `msp_island_up()` → `msp_selftest()` (Lesung `0x00EE`) →
`msp_download()` → *patched* → `msp_build_graph()` (22 RMW) → `msp_apply_controls()` → *running*.

**Selbstheilung** (`msp_heal_work`, eigener Worker): läuft nur an, wenn der Zustand `error` ist.
Schleife mit höchstens `MSP_HEAL_MAX = 3` Durchläufen; ein Erfolg setzt den Zähler zurück.
Danach bleibt `error` stehen und wird nicht mehr selbst neu angestoßen - `echo 1 > reset`
setzt den Zähler auf 0 und baut **synchron** neu auf (damit „Ton kommt zurück" direkt am
Rückgabewert des `write` hängt). Ausgelöst wird die Heilung von `msp_mailbox_failed()`, das
jeder Nicht-Inbetriebnahme-Pfad (Controls, `levels`, `compressed`) bei `-ETIMEDOUT` aufruft;
im Probe selbst wird nach einem Fehlschlag einmal `schedule_work()` gerufen. Schlimmster Fall
also 1 Probe-Versuch + 3 Heilungen.

**`remove`**: `cancel_work_sync`, debugfs weg, Insel wieder in den Kaltstart-Zustand
(Reset angelegt, Gate aus), Takte aus, `pm_runtime_put`. Ein Wiederladen fährt damit exakt
die gemessene Sequenz statt einen halb konfigurierten DSP vorzufinden (Abnahme §4: 20 ×
Modul entladen/laden).

## 2. Timeouts und Wartezeiten (alle mit Quelle im Code)

| Größe | Wert | Herkunft |
|---|---|---|
| Mailbox schreiben: Busy-Bit 4 | 50 ms | Plan §3.1 |
| Mailbox lesen: Ready-Bit 5 + Bit 31 | 50 ms | Plan §3.2 |
| Weckruf `0x00EE == 0x0180` | 500 ms, **nicht** tödlich (Warnung, weiter) | `mbx.c -K` |
| Reset gehalten | 10 ms | `dsp_island2.py` |
| nach `bus-demod` an | 20 ms | `dsp_island2.py` |
| nach Router `0x003003FF` | 12 ms | S17 Schritt 9 |
| nach Audio-Top-Freigabe | 50 ms | `dsp_island2.py` |
| ROM-Boot vor der ersten Mailbox-Nutzung | **300 ms** | Plan §3.5 |
| nach `0xFFF7 := 0`, `0x0000 := 0` | 200 ms | Plan §3.3 |
| nach dem letzten Block vor der Erfolgsprüfung | 300 ms | `mbx.c dl` |
| QPEAK-Einschwingen in `levels` | 50 ms | `dsp_qpeak.py` |

Eine vollständige Inbetriebnahme dauert damit ≈ 0,95 s Wartezeit + ≈ 20 ms Download.
Die Polling-Schleifen drehen die ersten ~100 µs mit `cpu_relax()` und schlafen danach
(`usleep_range(20, 50)`); nie aus Interruptkontext, nie mit Spinlock.

## 3. Was der Treiber am Gerät anfasst - und was bewusst nicht

**Angefasst:** `bus-demod` Gate/Reset, 16 TVFE-Gates, `pd_tvfe`, Router `0x06700000`,
Audio-Top `0x0614A000/0x0614A00C`, Mailbox `0x06144000 +0x00/+0x0C/+0x10`, DSP-Register
laut Plan §3.3/§3.6.

**Nicht angefasst, mit Absicht:**
* **AUDIF/ABPO1** (`0x06146000` +0x00/+0x04/+0x08/+0x18). `dsp_graph_only.py` öffnet dort
  vier Register; S25 §6 korrigiert S23 §6.2 und zeigt, dass ABPO1 **nicht** die Senke von
  I2SOUT1 ist (`+0x08` = SCC-Fehlerstatus W1C, `+0x1C` = Rahmenlänge). Plan §3.6 listet die
  Schreibzugriffe nicht. Der Treiber bildet AUDIF nur ab und **liest** es für debugfs.
  → **Annahme 1**, siehe §5.
* **`0x06142044`** (High-Addr-Ctl). S17 Schritt 14 schlägt eine 0x5a-Schreib-Lese-Probe vor;
  dieselben Nibbles wählen das DRAM-Fenster des **laufenden** Capture-Rings. Der Treiber
  liest nur; der Lebensnachweis ist der Mailbox-Selbsttest.
* **DSP2.** S27: Klangeffekt-Kern, für PCM nicht nötig. Die Typ-0102-Blöcke werden trotzdem
  mitgeschrieben - der volle Strom ist die Variante mit 20/20 Erfolgen (S16 20:20).
* **DELAY1.** `0x0036` wird wie im Stock gesetzt, der Ausgang läuft aber über `0x0020 := 0x6263`
  an DELAY1 vorbei (S16 18:00). Kosten: die 2 ms Lippensynchronität, die Stock verwendet (S26).
* **Codec, HDMI-RX, `0x068B0000`, INCAP.** Pakete C/D bzw. gesperrt.

## 4. Schnittstellen wie in Plan §2 gefordert

ALSA-Karte `snd_card_new`-Familie, kein PCM: Kurzname `hy310hdmi`, Langname `HY310 HDMI Audio`,
`driver` = `H713-MSP`.

| Control | Typ | Wirkung |
|---|---|---|
| `HDMI Audio Switch` | bool | `0x0012` Bit 15 (I2SIN1-Freigabe) |
| `HDMI Playback Volume` | integer 0…400, TLV `DECLARE_TLV_DB_SCALE(-10000, 25, 0)` | `0x0052/0x0053` Maske `0xFFC0`, Viertel-dB als Zweierkomplement in Bits 15:6 |
| `HDMI Mute Switch` | bool | `0x0050/0x0051` Maske `0xFFC0`, Wert `0x8000` bzw. 0 |

Umrechnung: Registerwert = `((ctl − 400) & 0x3FF) << 6`. Probe: `ctl = 320` → −20 qdB →
`0xFB00` - genau der Wert, der am 08.09. mit −4,9 dB gemessen wurde.

sysfs am Platform-Gerät (`driver.dev_groups`, erscheinen also erst nach erfolgreichem Bind):
`state` (r), `levels` (r, „`links rechts`" aus `0x00B2/0x00B3`, QPEAK-Eingänge werden bei
jeder Lesung auf `0x16/0x17` gesetzt), `compressed` (r, 1 nur wenn `0x800A` Bit 7 **und**
Bit 5), `reset` (w, synchron). debugfs `h713-msp/status`: Zustand, Heilungszähler,
Timeout-Zähler, Firmwaregröße/Blockzahl, Router, Audio-Top, `0x06142044`, vier AUDIF-Wörter,
Mailbox-Status und - ab `patched` - `0x80FF`, `0x0001`, `0x00FC`, `0x00EE`, `0x0012`, `0x001E`,
`0x0020`, `0x0050`, `0x0052` (mit Rückrechnung in Control-Einheiten) und die volle
Nicht-PCM-Auswertung von `0x800A`.

## 5. Annahmen, die am Gerät fallen können

1. **AUDIF/ABPO1 bleibt zu.** Der Lauf, der 75,9 dB lieferte, hatte die vier ABPO1-Schreibungen
   drin (aus einer inzwischen widerlegten Annahme). Der Treiber lässt sie weg, weil Plan §3.6
   sie nicht führt und S25 §6 sie als wirkungslos ausweist. **Wenn kein Ton kommt, obwohl
   `state = running`, `levels` ≠ 0 und der Codec (Paket C) steht: das ist der erste Verdacht.**
   Gegenprobe von Hand: `devmem2`-Äquivalent auf `0x06146000 := 0x40000`, `+0x08 := 3`,
   `+0x18 := 0x1A5E0000`, `+0x04 |= 0x40000` - kommt der Ton dann, gehören die vier Zeilen in
   `msp_build_graph()` nachgezogen, und S25 §6 ist zu korrigieren.
2. **`0x0012` als RMW mit Maske `0xA3FF`.** Plan §3.6 schreibt „`0x0012 := 0x8180`",
   `dsp_graph_only.py` schreibt RMW mit `0xA3FF`. Der Treiber folgt dem Skript (Bits 14 und
   13:10 bleiben stehen). Unterschied ist nur sichtbar, wenn der ROM/Patch dort etwas gesetzt hat.
3. **Exklusiver Reset.** `devm_reset_control_get_exclusive("bus-demod")` statt des von S17 §4a
   empfohlenen `_shared`: ein geteilter Reset lehnt ein `assert` ohne vorheriges `deassert` ab
   und feuert `reset_control_reset()` nur einmal je Control - beides unbrauchbar für eine
   Heilung, die den Puls wiederholen muss. Das geht, weil `CONFIG_SUNXI_TVTOP` aus ist.
   Wird tvtop je eingeschaltet, siehe 0138 §2c.
4. **`clk_set_rate` auf `audio-cpu/umac/ihb`** ist heute folgenlos (reine Gates). Erst mit
   Paket A (0134) greift es. Fehler werden geloggt, nicht behandelt; die Boot-Raten haben den
   Download bereits getragen. Wenn 0134 vor 0137 landet, ist die Zeile
   `audio-cpu laesst sich nicht auf 400000000 Hz setzen` im `dmesg` das Zeichen, dass die
   Modellierung noch fehlt.
5. **Weckruf-Timeout ist nicht tödlich.** Bleibt `0x00EE` 500 ms lang ≠ `0x0180`, gibt es eine
   Warnung und der Download läuft weiter - genau wie `mbx dl -K`. Über Erfolg entscheidet
   `0x80FF`/`0x0001`.
6. **`power-domains = <&ppu 1>` ist eine Referenz, kein Einschalten.** pd_tvfe ist seit U-Boot an.
   Wäre sie es nicht, hinge jeder Zugriff auf `0x0614xxxx` den Bus - der Treiber prüft das
   indirekt über „Router liest 0".
7. **Firmwaregröße.** Nur „Vielfaches von 4" und der Kopf `4D53 504D` sind hart; 2896 Byte
   werden erwartet und eine Abweichung nur gewarnt. Kontrolliert: 724 Paare, 8 MSPM-Blöcke,
   Magic bei Paar 0/4/8/32/39/324/681/707 - deckungsgleich mit `bounds` in `dsp_island2.py`.
8. **`maintainers:` in der Bindung** trägt einen Platzhalter (`hy310@example.invalid`). Vor
   einer Einsendung nach außen ersetzen.

## 6. Testrezept (Hauptsitzung, am Gerät)

```
# 0. Vorbereitung
cp re/work/audio/patch_msp.bin /srv/h713-rootfs/lib/firmware/h713/msp-patch.bin
#    Kernelkonfiguration: CONFIG_SND_SUN50I_H713_MSP=m; dtsi-Fragment aus 0138 einspielen.

# 1. Bind
modprobe sun50i-h713-msp
dmesg | grep h713-msp
#    erwartet: "Patch geladen: 724 Paare, 8 Bloecke, 0x80FF = 1, 0x0001 = 0x0c19"
#              "MSP laeuft: HDMI -> I2SIN1 -> VOLUME -> I2SOUT1"
#    NICHT erwartet: "Mailbox-Timeout", "Selbstheilung", "TVFE-Top liest 0"

D=/sys/devices/platform/soc/6144000.audio-dsp
cat $D/state                  # running
cat /sys/kernel/debug/h713-msp/status

# 2. Signalprobe (Zuspieler: Dauerton 48 kHz, xrandr mit --rate!)
cat $D/levels                 # zwei Zahlen, deutlich > 0 und schwankend; Ton aus -> 0 0
cat $D/compressed             # 0 bei PCM

# 3. Controls
amixer -c hy310hdmi controls
amixer -c hy310hdmi cset name='HDMI Playback Volume' 320   # -20 qdB = -5 dB, Mikro: -4,9 dB
amixer -c hy310hdmi cset name='HDMI Mute Switch' 1         # Mikro: Grundrauschen
amixer -c hy310hdmi cset name='HDMI Mute Switch' 0
amixer -c hy310hdmi cset name='HDMI Audio Switch' 0        # Ton weg (I2SIN1 aus)
amixer -c hy310hdmi cset name='HDMI Audio Switch' 1

# 4. Selbstheilung
echo 1 > $D/reset             # blockiert ~1 s, danach state=running und Ton zurueck
cat /sys/kernel/debug/h713-msp/status | grep -E 'heal_count|mbox_timeouts'

# 5. Dauer- und Wiederholtests (Plan §5)
for i in $(seq 20); do rmmod sun50i-h713-msp; modprobe sun50i-h713-msp; sleep 2; \
  cat $D/state; done          # 20 x running
#    32 kHz / 44,1 kHz / 48 kHz am Zuspieler: Tonhoehe folgt (Codec-Rate = Paket C/E)
#    30 min Dauerton: keine "Mailbox-Timeout"-Zeile, levels plausibel
```

**Schrittweise fahren** (Board-Regel): jeder Aufruf einzeln, 20-30 s Zeitfenster, nach jedem
Schritt `state` lesen. Bleibt `state` auf `error`, sagt `dmesg` welche Stufe (Router,
Audio-Top, Selbsttest, Download, Graph) und `status` liefert die Registerlage dazu.

## 7. Dateien

* `analyse/audio/arbeit/t-b-msp/a|b/…` - Arbeitskopien (Original / geändert)
* `analyse/audio/arbeit/t-b-msp/patches/0137-ASoC-sunxi-add-the-h713-msp-audio-dsp-driver.patch`
* `analyse/audio/arbeit/t-b-msp/patches/0138-fragment-dts.txt`
