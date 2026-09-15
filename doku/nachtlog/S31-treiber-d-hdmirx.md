# S31 - Paket D: Audiostatus des HDMI-Empfängers als V4L2-Controls (Patch 0136)

**08.09.2026. Reine Schreibtischarbeit - kein Board, kein Bau.** Auftrag
`t-d-hdmirx/AUFTRAG.md`, Plan
[`101`](../101-plan-audio-treiber.md) §1 D, §2, §4. Belege: [`S18`](S18-re-mips-hdmi-audio.md)
§3.4, §4.1, §4.4, §6, [`S16`](S16-hdmi-audio.md) 13:15-13:45, 18:10, 20:30, 20:45. Basisbaum
`mainline/build/linux-6.18.38-a3097ce7…`; Arbeitskopien `analyse/audio/arbeit/t-d-hdmirx/{a,b}/`.

## 1. Was geliefert wird

`analyse/audio/arbeit/t-d-hdmirx/patches/0136-media-h713-hdmirx-expose-the-audio-status.patch`
(eine Datei, zwei Bäume):

| Datei | Inhalt |
|---|---|
| `drivers/media/platform/sunxi/sun50i-h713-hdmirx/sun50i-h713-hdmirx.c` | LINK-Regmap (nur lesend), drei Controls, 100-ms-Poll, debugfs-Zeile |
| `arch/arm64/boot/dts/allwinner/sun50i-h713.dtsi` | neuer Knoten `hdmirx_link: syscon@6840000` mit `reg-io-width = <1>`, Eigenschaft `allwinner,hdmirx-link` am Empfängerknoten |

Geprüft: `patch -p1` auf den unberührten Basisbaum läuft durch und erzeugt `b/` byteweise;
`checkpatch.pl --strict` meldet nur zwei Fundstellen, die das Haus schon hat - den
„diff content in the commit message" (dieselbe Meldung bei `0133`, weil die Hauspatches keine
`---`-Trennlinie führen; `patch(1)` läuft trotzdem, oben nachgestellt) und die Balkenkommentare
`* ---- */`, von denen `a/` bereits neun trägt. **Nicht gebaut** (kein Container in dieser Sitzung),
nicht am Board.

## 2. Die drei Controls

| Name | CID | Typ | Wert |
|---|---|---|---|
| `H713 Audio Present` | `0x00981b36` | bool | Ausgang an ∧ N ≠ 0 ∧ Fs-Code gültig |
| `H713 Audio Rate` | `0x00981b37` | integer 0…192000 | gemessene Abtastrate in Hz, 0 = unbekannt |
| `H713 Audio Compressed` | `0x00981b38` | bool | **vermutet** nicht-PCM, Vorgabe 0 |

Alle `V4L2_CTRL_FLAG_READ_ONLY`, ohne `.ops`, geschrieben allein aus dem Poll.

**Zwei Abweichungen vom Plan §2, beide im Quelltext begründet:**

1. **CIDs nicht bei `V4L2_CID_USER_BASE + 0x1090`.** Der Block ist belegt: er ist
   `V4L2_CID_USER_MAX217X_BASE` (`include/uapi/linux/v4l2-controls.h:160` im Basisbaum). Der
   Treiber hat einen eigenen reservierten Block von sechzehn bei `+ 0x1230`
   (`V4L2_CID_USER_SUN50I_H713_BASE`, Zeile 235), davon waren sechs benutzt - die drei neuen sind
   `+6 … +8`. Die **Namen** sind die des Plans, und die sind es, worauf Userspace zugreift.
2. **`READ_ONLY`, aber nicht `VOLATILE`.** Beides zusammen schließt das geforderte Ereignis aus:
   `cluster_changed()` in `drivers/media/v4l2-core/v4l2-ctrls-core.c:2454` löscht `has_changed` für
   jedes flüchtige Control ausdrücklich, „to avoid generating the event V4L2_EVENT_CTRL_CH_VALUE" -
   ein flüchtiges Control sendet also nie eines, und `v4l2_ctrl_s_ctrl()` darauf wäre wirkungslos.
   Das Ereignis ist die Hälfte, die Userspace nicht nachbauen kann; die Frische nicht, und sie
   fehlt auch nicht: der Wert ist höchstens 100 ms alt. `tc358743` gibt seinem „Audio present"
   dieselbe Form.

## 3. Fs-Code-Tabelle (Beleg)

**Gemessener Code, `0x0684015F[6:4]`** - Kodierung aus der Sprungtabelle der Firmware
(`sub_8B13C1D8`, S18 §3.4 und §4.1 Zeile `0x0684015F`), Messwerte aus S16:

| Byte `+0x15F` | Code | Treiber meldet | Beleg |
|---|---|---|---|
| `0x00` | 0 | **0 (kein Ton)** | S16 13:15-13:30 und 13:31: Signal eingerastet, `+0x40 = 0x07`, N = 6144 bzw. Reset - **kein Ton** |
| `0x10` | 1 | 32000 | S16 20:30: 32-kHz-Quelle, N = 4096 |
| `0x20` | 2 | 44100 | S16 16:40-17:00: Wechsel `0x30 → 0x20` am Zuspieler; 18:10: 44,1-kHz-Quelle, N = 6272 |
| `0x30` | 3 | 48000 | S16 13:45: `+0x40 = 0x17`, `+0x56 = 2`, N = 6144, elog `audio param:148500 6144 48000 48 16` |
| `0x40` | 4 | 88200 | nur Firmware-Tabelle |
| `0x50` | 5 | 96000 | nur Firmware-Tabelle |
| `0x60` | 6 | 176400 | nur Firmware-Tabelle |
| `0x70` | 7 | 192000 | nur Firmware-Tabelle |

**Bewusste Abweichung bei Code 0.** Die Firmware bildet 0 **und** 1 auf 32 kHz ab. Am Board heißt
0 aber „nichts gemessen": mit `IEC958 Playback Switch` der Quelle auf *off* stand das Bild, der
Audioausgang war an (`+0x40 = 0x07`) und N war die ganz gewöhnliche 6144 - `+0x15F` las trotzdem 0
und es gab nirgends Ton (S16 13:15-13:30). Echte 32 kHz lasen 0x10. 32000 für Code 0 zu melden
hieße, eine Rate für Stille zu behaupten; deshalb ist Code 0 hier 0, und genau das macht
`Present` falsch.

**Gemeldeter Code, `0x06840056[3:0]`** - nur für debugfs, mit der IEC-Tabelle aus
`include/sound/asoundef.h` dekodiert und **nicht** mit der der Firmware (die hat `0xA → 88200` und
ein `82000` als Tippfehler für 88 200, S18 §3.4, ausdrücklich auch §9). 0 = 44100, 2 = 48000,
3 = 32000, 8 = 88200, 10 = 96000, 12 = 176400, 14 = 192000; 1 („not indicated"), 11 (128 kHz, nur
mit Bit 7 des Bytes) sowie 7 und 15 (in `asoundef.h` gar nicht vergeben) melden 0. Gemessen ist
genau **eine** Übereinstimmung: 48 kHz, `+0x56 = 2` neben `+0x15F = 0x30` (S16 13:45). Der für
44,1 kHz erwartete Wert `+0x56 = 0` steht in S18 §8 als Messplan, nicht als Messung - bei den
44,1-kHz-Läufen wurde nur N und der gemessene Code mitgeschrieben.

Die Dekodierung ist gegen alle fünf Messfälle aus S16 durchgerechnet (eigenständiges Testprogramm
im Scratchpad, `gcc -Wall -Wextra -Wformat=2` sauber): 48 kHz → present 1 / 48000, Quelle ohne
Audiopakete → present 0, 44,1 → 44100, 32 → 32000, Reset nach Rebind → present 0.

## 4. Warum ein eigenes Werk und ein Syscon

- **Byteweise.** Das LINK-Fenster beantwortet Byteregister; eine 32-Bit-Lesung liefert das Byte der
  ausgerichteten Adresse viermal (S18 §4.4), N bei `+0x45..0x47` ist wortweise gar nicht
  erreichbar. Der Syscon-Knoten trägt `reg-io-width = <1>`; `drivers/mfd/syscon.c` setzt daraus
  `reg_stride = 1`, `val_bits = 8`, und `regmap-mmio` liest mit `readb()`
  (`regmap_mmio_noinc_read`, `readsb(ctx->regs + reg, …)` - `reg` ist der Byte-Offset).
- **Nur lesend.** Die Firmware schreibt diese Register nach eigenem Fahrplan alle 10 ms; ein
  Schreiben von der ARM aus liefe dagegen. Wie beim INCAP-Fenster: Syscon, kein Treiber, kein
  Schreiber.
- **Optional.** `syscon_regmap_lookup_by_phandle_optional()`; ohne `allwinner,hdmirx-link` probt der
  Knoten wie bisher, die drei Controls stehen auf 0 (`dev_warn` einmal), das Werk wird nicht
  angeworfen. Ein alter Devicetree bleibt also lauffähig.
- **Eigenes `delayed_work`.** Der Treiber hat kein Werk, das durchläuft: das Wiederanwerfen kommt
  aus einem Fehler, der Vsync-Melder tickt nur im Strom - der Audiostatus muss aber auch stimmen,
  wenn nichts läuft. Zehn Bytelesungen je 100 ms. Ein abgeschalteter TVFE liest 0, das dekodiert zu
  „kein Ton". Gestartet ganz am Ende von `probe()`, in `remove()` **vor** dem Freigeben des
  Control-Handlers mit `cancel_delayed_work_sync()` beendet (das Werk wirft sich selbst neu an).
- **Schreiben nur bei Änderung.** Das Rahmenwerk würde ohnehin filtern (`new_to_cur()` in
  `v4l2-ctrls-api.c` vergleicht und sendet `V4L2_EVENT_CTRL_CH_VALUE` nur bei Unterschied), aber es
  gibt keinen Grund, dreißigmal je Sekunde die Handler-Mutex zu nehmen. Derselbe Vergleich trägt
  die Logzeile.

## 5. debugfs

`/sys/kernel/debug/sun50i-h713-hdmirx/status` bekommt zwei Zeilen, frisch gelesen (nicht aus dem
Poll), damit eine Messung an den Rohbytes geprüft werden kann:

```
audio:        present=1 rate=48000 compressed=0 n=6144 cts=148500
              0x40=0x17 (Ausgang an, Nibble 1) 0x15f=0x30 0x56=0x02 (48000 Hz gemeldet) 0x160=0x00
```

Ohne LINK-Fenster: `audio:        kein LINK-Fenster (allwinner,hdmirx-link fehlt)`.

## 6. Testrezept (Hauptsitzung, am Board)

Voraussetzung: Patch eingespielt, Kernel + DTB gebaut, Kaltstart, Zuspieler mit `xrandr --rate`
gesetzt und `amixer -c0 cset numid=… on` (der `IEC958 Playback Switch` der Quelle - genau der hat
in S16 einen Tag gekostet).

1. **Controls vorhanden.**
   `v4l2-ctl -d /dev/video0 --list-ctrls | grep h713_audio`
   Erwartet drei Zeilen mit `flags=read-only`, z. B.
   `h713_audio_rate 0x00981b37 (int) : min=0 max=192000 step=1 default=0 value=48000 flags=read-only`.
   Zeigt `value=0` bei laufendem Ton, ist entweder der DT-Knoten nicht da (dann sagt es
   `dmesg | grep hdmirx-link`) oder die Quelle sendet keine Audiopakete (dann sagt es die
   debugfs-Zeile: `+0x40 = 0x07` statt `0x17`, `0x15f=0x00`).
2. **Werte gegen die Rohbytes.** `cat /sys/kernel/debug/sun50i-h713-hdmirx/status` - die zweite
   Zeile muss zur ersten passen und zu §3. Positivkontrolle: Zuspielerrate wechseln
   (`speaker-test -D hw:0,3 -r 44100`), `0x15f` muss `0x30 → 0x20` springen und N `6144 → 6272`.
3. **Ereignis.** In einem Fenster
   `v4l2-ctl -d /dev/video0 --poll-for-event=ctrl=h713_audio_rate` (das ist die Schreibweise, die
   `v4l2-ctl` für „subscribe" hat; der Name ist der Control-Name klein mit Unterstrichen), im
   anderen die Zuspielerrate wechseln oder `amixer` den `IEC958`-Schalter aus- und einschalten.
   Erwartet eine `ctrl` -Ereigniszeile je Wechsel, **keine** im Ruhezustand. Dasselbe für
   `ctrl=h713_audio_present` beim Stecker ziehen/stecken.
4. **Kein Ton, kein Present.** Quelle `IEC958` aus → `present=0`, `rate=0` binnen 100 ms; `dmesg`
   zeigt genau eine Zeile `Audio: keins (+0x40 = 0x07, …)` je Wechsel, nicht zehn je Sekunde.
5. **Alter Devicetree.** DTB ohne den Knoten booten: Treiber probt, `dmesg` bringt einmal
   `kein allwinner,hdmirx-link …`, die drei Controls stehen auf 0, Bild unverändert.
6. **Aus- und Einhängen.** `modprobe -r` / `modprobe` fünfmal, danach `dmesg | grep -i warn` leer -
   das prüft das Abstellen des sich selbst neu anwerfenden Werks.

## 7. Offene Annahmen

- **`Compressed` ist vermutet**, beide Hälften. Die Firmware liest `+0x40[7]` und schreibt dann
  `+0x160 := 0xFF` und `+0x15E[6:4] := 1` (`sub_8B13C5B0`, S18 §3.4) - ein Roh- gegen einen
  PCM-Weg; der Name des Bits steht nirgends im Abbild, und es lief noch nie ein komprimierter Strom
  über dieses Board. Die eine Messung passt (lineares PCM 48 kHz ließ beide auf 0). Falsch wäre es
  in die sichere Richtung: `hy310-tv` stummt auf „compressed", es entstummt nicht. **Fällig, sobald
  ein AC-3/DTS-Zuspieler da ist:** debugfs-Zeile mitschreiben und `0x40[7]`/`0x160` gegen den
  bekannten Strom prüfen.
- **Codes 4…7** (88,2 bis 192 kHz) stehen nur aus der Firmware-Tabelle, nie gemessen. Für Paket E
  ohne Belang, solange der Codec nur 32/44,1/48 kHz kann - die höheren Raten sollten `present=1`
  mit einer Rate melden, die `hy310-tv` dann ablehnen muss.
- **Statusnibble `+0x40[7:4]`.** Nur `1` (Ton da) und `0` (kein Ton) sind gesehen; der Treiber
  wertet den Nibble nicht aus, er zeigt ihn nur in debugfs. Ändert sich das Bild, wäre er der erste
  Ort zum Nachsehen.
- **Nicht gebaut.** Der Quelltext ist gegen den Basisbaum geprüft (Include, `regmap`-Semantik,
  `syscon_regmap_lookup_by_phandle_optional`, `call_op()` bei `.ops == NULL`, `set_ctrl()`-Weg),
  die Dekodierlogik eigenständig übersetzt und durchgerechnet - aber ein Übersetzungslauf des
  Moduls fehlt und gehört an den Anfang der Abnahme.
