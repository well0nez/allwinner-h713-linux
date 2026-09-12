# Der Stock-Vergleich

Das Werkzeug, das den Display-Pfad zum Laufen gebracht hat. Vier Hypothesen
zur Helligkeit waren vorher an der Hardware gescheitert; der Vergleich gegen
ein laufendes Stock-System hat die Frage in zwanzig Minuten beantwortet.

## Der A/B-Umschalter

Beide Bootloader liegen **parallel** auf der eMMC:

| | liegt bei | lädt weiter bei |
|---|---|---|
| Stock | boot0 LBA 16 | `sunxi-package` LBA 24576 |
| unser | SPL LBA 16 | U-Boot proper LBA `0x49ac00` |

Nur LBA 16 ist umkämpft. Ein Schreibvorgang über 64 Sektoren schaltet um, in
beide Richtungen, und der jeweils andere Stand bleibt unangetastet:

```
fatload usb 0:1 0x50000000 stock-boot0.bin     → Stock
fatload usb 0:1 0x50000000 spl.bin             → unser
mmc write 0x50000000 0x10 0x40
```

`stock-boot0.bin` ist `re/device-dumps/lba16.bin`, aufgenommen vor dem ersten
eigenen Flash und byte-identisch mit Sektor 16 **und** 256 des Dumps.

**Die eMMC hat verschiedene Nummern:** im Stock-U-Boot `mmc dev 2`, in unserem
`mmc dev 1`. `mmc dev 0` gibt es in beiden nicht — `sunxi_card0_probe` ist der
SD-Slot und schlägt fehl.

## Auslesen und vergleichen

```bash
tools/uart-capture.py -o re/captures/ours.txt      # Standardsatz Display-Register
tools/regdiff.py re/captures/stock-reference.txt re/captures/ours.txt
```

`uart-capture.py` spricht den ESP32-Proxy direkt an, ohne pyserial. Eine
laufende `tio`-Sitzung muss vorher zu sein, sonst teilen sich beide die
Leitung und die Ausgabe landet im falschen Fenster.

`regdiff.py` liest beide Mitschnitte, legt sie adressweise übereinander und
meldet jede Abweichung. Das war der Punkt: vorher habe ich einzelne Register
verglichen, die ich mir **vorher ausgesucht** hatte — so findet man nur, was
man ohnehin vermutet.

Die Referenz liegt in `re/captures/stock-reference.txt`.

## Was der Vergleich gefunden hat

| Register | Stock | wir, vorher | |
|---|---|---|---|
| `058c0014` | `b9002800` | `b8002a00` | N+1 = 41 statt 43, **ssc_en gesetzt** |
| `058c0018` | `c8d0362f` | ungepatcht | SSC-Wellenform |
| `0525c000` | `045f084f` | `04650898` | **Feld hält total−1**: 2128 × 1120 |
| `0525c004` | `00002c05` | `00003e07` | hsync 44, vsync 5 |
| `0525c01c` | `07800084` | `07800114` | 132 = 44 + 88 |
| `0528008c` | `00000037` | `00000000` | Layer-X-Ursprung, 55 |
| `05280084` | `04380780` | high16 leer | trägt die aktive Höhe |
| `05800000` | `01e0a40c` | `01e0a404` | Bit 3, ein Enum statt `color_depth` |

Der Boot-Log des Stock-U-Boot bestätigt die PLL im Klartext:

```
ssc percent:10 wave bottom:0x362f, wave step:0x8d, n:41,
ssc_freq:31500 reg_value:0xc8d0362f
Project id:0x30 version:21-12-14-0
```

Und nebenbei, gegen unsere eigene Vermutung: `Failed to get bl id property`,
`Failed to get pwm_id property` — **auch der Stock-Bootloader macht keine
Backlight-PWM.**

## Was danach noch offen ist

Der AFBD-Block, und dort nur Konfiguration, die wir nicht setzen:

```
05600058   98   wir 0
0560005c   73   wir 0
05600300   00804218   wir 00800210
05600304   00804000   wir 00800000
052800c0   00000a50   wir 00000250
```

`05600178` unterscheidet sich zu Recht — das ist unsere eigene
Framebuffer-Adresse. `05600184` und `05880000` sind laufende Zähler.

## Flash-Regel, teuer gelernt

**Erst laden, den RAM prüfen, dann schreiben.** Ein `fatload` kann fehlschlagen
(Stick nicht am Board, EHCI-Timeout) und `mmc write` schreibt trotzdem — dann
landet uninitialisierter Speicher im Bootsektor:

```
fatload usb 0:1 0x50000000 spl.bin
md.l 0x50000000 4        → muss ea000016 4e4f4765 3054422e ... zeigen
mmc write 0x50000000 0x10 0x40
```

Danach zurücklesen und vergleichen, **bevor** neu gestartet wird.

Passiert es doch: **boot0 liegt doppelt**, bei LBA 16 und LBA 256. Das BROM
weicht auf die zweite Kopie aus, und das Gerät bootet weiter — auf dem Stand,
der dort liegt. Genau das ist am 31.08. passiert und hat die Sitzung gerettet.
