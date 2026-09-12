# S30 — Paket C: Codec-I2S-Fenster, `DAC Source`, `I2S Rate` (Patch 0135)

**08.09.2026. Reine Schreibtischarbeit — kein Board, kein Bau.** Auftrag
[`t-c-codec/AUFTRAG.md`](../../analyse/audio/arbeit/t-c-codec/AUFTRAG.md), Plan
[`101`](../101-plan-audio-treiber.md) §1 C, §2, §4. Belege: [`S25`](S25-re-i2sout-codec.md) §1–§4,
[`S16`](S16-hdmi-audio.md) 17:40–20:45. Basisbaum
`mainline/build/linux-6.18.38-a3097ce7…`; Arbeitskopien `analyse/audio/arbeit/t-c-codec/{a,b}/`.

## 1. Was geliefert wird

| Datei | Inhalt |
|---|---|
| `patches/0135-ASoC-sun4i-codec-h713-add-the-i2s-input-path-for-the-msp-dsp.patch` | `sound/soc/sunxi/sun4i-codec.c`: zweites Regmap, 21er-Init, Controls `DAC Source` und `I2S Rate` |
| `patches/0135b-arm64-dts-h713-describe-the-codec-s-i2s-window.patch` | `sun50i-h713.dtsi`: zweites `reg` `0x02031000 0x7c`, `reg-names = "codec", "i2s"` |

(beide unter `analyse/audio/arbeit/t-c-codec/patches/`). **Reihenfolge egal**, aber ohne 0135b
findet der Treiber das Fenster nicht und lässt die beiden Regler weg (`dev_warn`, sonst alles wie
bisher). Ohne 0135 ist 0135b ein unbenutzter Eintrag. Beide sind gegen `a/` geprüft und erzeugen
byteweise `b/`.

**cstengers H713-Zweig ist unangetastet**: Widgets, Routen, Karte, HP-Verstärker-Event, Regmap
und Quirk bleiben, was sie waren; alles Neue kommt hinzu. Die einzigen Eingriffe außerhalb des
H713-Teils sind (a) `sun4i_codec_get_mod_freq()`/`_get_hw_rate()` nehmen jetzt die Rate statt
`hw_params` (dieselben Tabellen, zwei Aufrufstellen angepasst), (b) `hw_params()` merkt sich die
Stromrate und lehnt eine abweichende ab, solange der I2S-Weg scharf ist, (c) `shutdown()` setzt die
gemerkte Rate zurück. Für alle anderen SoCs ändert sich dadurch nichts: `i2s_armed` kann nur auf
H713 wahr werden.

## 2. Was der Treiber bei `DAC Source = I2S` genau schaltet

In dieser Reihenfolge (Vendor-Reihenfolge aus S25 §4.2 — Takte, Empfänger, Wähler, Analogteil):

1. **Verriegelung.** Läuft schon ein PCM (`snd_soc_component_active()`) mit *anderer* Rate als
   `I2S Rate`, bricht das Setzen mit `-EBUSY` ab. Nichts wird angefasst.
2. **Takt.** `clk_prepare_enable(codec-Modultakt)` — dieselbe Uhr, die `startup()` nimmt, also über
   die Referenzzählung des Taktrahmens; ein gleichzeitig laufender Strom hält sie weiter.
3. **Rate** (`sun50i_h713_codec_i2s_set_rate()`): `clk_set_rate` auf 45 158 400 Hz (44,1-kHz-Familie)
   bzw. 49 152 000 Hz (32/48 kHz) — das ist `sun4i_codec_get_mod_freq()` × `mod_freq_mult` = 2, also
   exakt die Werte aus S16 20:45. Dann `DAC_FIFOC` (`0x02030010`) Bits 31:29 = Ratencode (48/44,1 → 0,
   32 → 1), Bit 28 (FIR) wie `prepare_playback()`, Bit 6 (MONO) gelöscht.
4. **Empfänger** (`0x02031000 INTER_I2S_CTL`): Bit 17 → 0, Bit 18 → 0 (BCLK und LRCK als Ausgänge,
   der Codec ist Takt-Master), Bit 1 → 1 (RXEN). Drei einzelne RMW wie im Stock.
5. **Wähler** (`0x02030000 DAC_DPC`): Bit 30 → 1, dann Bit 29 → 1 (Quelle = I2S).
6. **Analogteil: kein einziger direkter Registerzugriff.** Statt `DAC_EN`, `DAC_REG` Bits 15/14,
   `HP_REG` Bit 15 und das PA-GPIO ein zweites Mal zu schreiben, hängt vor den DAC-Widgets ein
   `SND_SOC_DAPM_SIGGEN("I2S In")`; der Regler ruft `snd_soc_dapm_force_enable_pin()` +
   `snd_soc_dapm_sync()`. DAPM schaltet daraufhin genau dieselbe Kette ein wie für eine Wiedergabe:
   `DAC Enable` (DPC Bit 31) → `Left/Right DAC` (0x310 Bits 15/14) → `Line Out Source Playback
   Route` → `LINEOUT` → `HP Amp` (0x324 Bit 15) → `Speaker` (PA-GPIO PL2 über
   `sun4i_codec_spk_event`).

**Das ist die Referenzzählung.** DAPM zählt, wie viele Gründe ein Widget hat, an zu sein: solange
entweder ein PCM oder der I2S-Weg die Kette braucht, bleibt sie an. `aplay` starten und beenden,
während HDMI-Ton läuft, schaltet nichts ab; `DAC Source APB` während `aplay` läuft, schaltet
ebenfalls nichts ab. Beim Kartenaufbau wird der Erzeuger in `card->late_probe` abgeklemmt — sonst
wäre er, wie jede Quelle, ab dem ersten `dapm_sync` verbunden und hielte den DAC ab dem Booten an.

**Zurück auf `APB`:** nur `DAC_DPC` Bit 29 → 0 (Bit 30 und der ganze Empfänger bleiben stehen, wie
im Stock), dann Pin abklemmen + `sync` (DAPM schaltet den Analogteil ab, *falls* kein PCM läuft),
dann `clk_disable_unprepare`.

**`I2S Rate`** wirkt sofort, wenn der Weg scharf ist (Punkt 3 noch einmal), und wird sonst nur
gemerkt. Auch hier `-EBUSY`, wenn ein laufender Strom eine andere Rate hat.

**Beim Probe** (`sun50i_h713_codec_i2s_probe()`): Fenster `"i2s"` nach Name holen, eigenes MMIO-Regmap
(`max_register = 0x7c`, `name = "i2s"`, kein Cache), dann die 21 RMW aus S25 §2 als Tabelle
(`sun50i_h713_i2s_init_seq[]`, jede Zeile mit Nummer und Bedeutung kommentiert, Felder über
`FIELD_PREP_CONST`). Die beiden Regler kommen erst in `.probe` der Komponente dazu und **nur**,
wenn das Fenster wirklich da ist.

## 3. Wie testen (am Gerät, Hauptsitzung)

Voraussetzung: MSP-Insel läuft und der Graph `0xC1` ohne DELAY1 steht (Paket B bzw. bis dahin
`dsp_graph_only.py`). Karte ist `H713 Audio Codec`.

```sh
# 0) Fenster da?  Ohne 0135b steht hier eine Warnung und die Regler fehlen.
dmesg | grep -i 'i2s'
amixer -c 0 controls | grep -E "DAC Source|I2S Rate"

# 1) Analogweg freigeben — wie für jede Wiedergabe auf diesem Board
amixer -c 0 sset 'Line Out' on
amixer -c 0 sset 'Speaker' on

# 2) Rate der Quelle setzen, dann umschalten
amixer -c 0 cset name='I2S Rate'   48000
amixer -c 0 cset name='DAC Source' I2S
#    -> Ton am Lautsprecher, ohne dass irgendein PCM offen ist

# 3) Registerprobe (S16-Erwartungswerte)
#    0x02031000 CTL    = 0x00000013   (GEN, RXEN, MODE_SEL=I2S, Master)
#    0x02031004 FMT0   = 0x00081F55
#    0x02031024 CLKDIV = 0x00000184
#    0x02030000 DPC    = 0xE00xxxxx   (Bits 31/30/29)
#    /sys/kernel/debug/clk/audio-codec-dac/clk_rate = 49152000
#    (nach dem Probe allein, vor dem Umschalten: CTL = 0x00060011)

# 4) Rate folgt der Quelle
amixer -c 0 cset name='DAC Source' APB
amixer -c 0 cset name='I2S Rate'   32000
amixer -c 0 cset name='DAC Source' I2S     # 32-kHz-Quelle -> Ton; 44100 ebenso

# 5) Referenzzählung
aplay -D hw:0,0 -f S16_LE -r 48000 -c 2 /dev/zero &   # HDMI-Ton darf nicht abreißen
kill %1                                              # ebenso wenig beim Beenden
amixer -c 0 cset name='I2S Rate' 44100               # während 48-kHz-aplay: -EBUSY erwartet
```

Erwartete Messwerte aus S16 zum Vergleich: 48 kHz → 1001 Hz, ~80 dB; 44,1 kHz → ~79,5 dB;
32 kHz → 1002 Hz, ~79,6 dB.

## 4. Offene Annahmen

1. **Die Taktrechnung des Empfängers stimmt weiter nicht** (S25 §2 „[offen]"). LRCK-Periode 32 ×
   BCLK-Teiler 24 ergibt bei 49,152 MHz Modultakt 64 kHz, nicht 48 kHz — trotzdem war der Ton am
   Gerät tonhöhenrichtig, und der Modultakt war messbar 49,152 MHz. Der Treiber bildet **die
   Messung** ab, nicht die Rechnung. Wer das auflöst, kann `I2S Rate` vielleicht ganz abschaffen.
2. **Die Rate muss von außen kommen.** Der Empfänger ist Master mit festen Teilern; es gibt kein
   Register, aus dem der Codec die Quellrate lesen könnte. Paket E setzt `I2S Rate` aus
   `H713 Audio Rate` (Paket D).
3. **`-EBUSY` statt Vorrang.** Läuft ein APB-Strom mit anderer Rate, verweigert der Treiber das
   Umschalten (und umgekehrt `hw_params`). Alternative wäre gewesen, den Strom zu übersteuern; das
   wäre stiller Schaden. Falls `hy310-tv` daran hängen bleibt, ist die Stelle bewusst eine Zeile.
4. **Bit 30 in `DAC_DPC`** bleibt unerklärt; er wird gesetzt und nie gelöscht, wie im Stock.
5. **Binding nicht angefasst.** `Documentation/devicetree/bindings/sound/allwinner,sun4i-a10-codec.yaml`
   kennt `allwinner,sun50i-h713-codec` ohnehin nicht (auch Patch `0084` hat es nicht ergänzt) und
   hat `reg: maxItems: 1`. Für eine Einreichung muss das nachgezogen werden, hier bewusst nicht,
   um dem Patch, der den Compatible einführt, nicht vorzugreifen.
6. **Nicht kompiliert** (Auftrag: kein Bau des aktiven Baums). Alle benutzten APIs einzeln im
   Basisbaum nachgeschlagen: `snd_soc_component_active()`, `snd_soc_kcontrol_component()`,
   `snd_soc_add_component_controls()`, `snd_soc_dapm_{force_enable,disable}_pin()`,
   `snd_soc_dapm_sync()`, `SND_SOC_DAPM_SIGGEN`, `SOC_ENUM_SINGLE_EXT_DECL`, `SOC_ENUM_EXT`,
   `devm_platform_ioremap_resource_byname()`, `FIELD_PREP_CONST` (in `bitfield.h`, statisch
   initialisierbar), `card->late_probe`.

## 5. Warum DAPM und nicht Register (die Entscheidung, die Rückläufe sparen kann)

`soc-dapm.c` 6.18 nachgelesen: `SND_SOC_DAPM_SIGGEN` bekommt `is_ep = EP_SOURCE` und
`connected = 1` (Zeile 3778/3836), ein DAI-Widget wird erst beim Stream-Start zum Endpunkt
(Zeile 4500). `is_connected_input_ep()` zählt beide Wege auf (`con +=`, Zeile 1496) und prüft
`is_ep && connected` — ein abgeklemmter Erzeuger trägt exakt 0 bei, ändert für den APB-Weg also
nichts, und ein erzwungener trägt genau eine Freigabe bei. `w->force` selbst schaltet nur das
Widget an sich ein (Zeile 1690), nicht die Pfade — deshalb ist `late_probe` mit `disable_pin`
nötig und nicht bloß Vorsicht.

## 6. Was geprüft wurde

| Prüfung | Ergebnis |
|---|---|
| `patch -p1` beider Patches gegen `a/` | sauber, erzeugt danach byteweise `b/` |
| `checkpatch.pl --strict --max-line-length=80` | je 1 Fehler, 0 Warnungen, 0 Checks — der Fehler ist die bekannte „diff content in the commit message"-Eigenheit des Formats ohne `diff --git`, identisch mit 0131/0134 |
| DTS: `cpp` + `scripts/dtc/dtc -I dts -O dtb` (nur im Scratchpad) | übersetzt, keine neue Warnung gegenüber `a/` |
| DTB zurückgelesen | `reg = <0x2030000 0x32c 0x2031000 0x7c>`, `reg-names = "codec", "i2s"` |
| 21er-Folge gegen S25 §2 | Zeile für Zeile, Maske und Wert; Erwartung nach dem Probe `CTL 0x00060011`, `FMT0 0x00081F55`, `CLKDIV 0x184` = die Werte, die S16 17:40 am Gerät gesehen hat |
