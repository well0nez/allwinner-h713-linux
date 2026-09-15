# Sackgassen

Ausgeschlossene Erklärungen für das dunkle Bild, mit dem Beleg. Alle am
31.08.2026 auf der eigenen Hardware geprüft. Wer eine davon neu aufgreifen
will, braucht ein Argument gegen die Messung, nicht gegen die Vermutung.

## Gelöst - und wodurch

**Die Helligkeit war kein fehlender Regler.** Sie war Takt und Timing: die PLL
lief auf N+1 = 43 statt 41 und ohne Spread Spectrum, die Mixer-Totale standen
auf 2200 × 1125 statt 2128 × 1120 minus eins, und die Porches waren falsch
hergeleitet. Das Panel bekam ein Raster, mit dem es nicht sauber arbeiten
konnte, und hat entsprechend wenig Licht durchgelassen.

Gefunden wurde das nicht durch Nachdenken, sondern durch den Registervergleich
gegen ein laufendes Stock-System - siehe [90-stock-referenz.md](90-stock-referenz.md).
Die vier Erklärungen unten waren alle falsch, und jede einzelne hat Stunden
gekostet, weil keine davon messbar war.

**Der Balken am rechten Bildrand** war ein Nachspiel derselben Sorte:
`h713_disp_clear_layer_xoff()` erzwang eine literale Null auf `0x0528008c`, dem
X-Ursprung des Layers. Das ist Board Bs Wert; unserer ist 55. Der Tabellen-Patch
setzte 55, und das Sicherheitsnetz zog es nach jedem DE-Replay wieder auf null.

## PWM2 auf PB4 - der „Stock-Dimmer"

**Nicht die Helligkeitssteuerung.** Zweimal gemessen, das zweite Mal mit
korrekt versorgtem Panel:

```
PWM2 100% duty (960/960 cycles at 25000 Hz), PB4 mux=3,
BGR=00010001 CTL=00000100 PERIOD=03bf03c0 GATE=00000004 EN=00000004
CNT=00000000->000000b0
```

Der Zähler läuft (zwei Lesungen 7 µs auseinander unterscheiden sich), das
Enable-Bit steht, `PERIOD` steppt sauber von `03bf03c0` auf `03bf0000`. Über
alle sechs Stufen 100 → 75 → 50 → 25 → 0 → 100 ändert sich die Helligkeit
nicht.

Pin und Mux sind bestätigt: der eigene Vendor-U-Boot-Devicetree hat
`pwm2@0 { pins = "PB4"; muxsel = <0x03> }`, dieselbe Kombination, die
cstenger am 05.08. für sein Board korrigiert hat. Auf **seinem** Board
ebenfalls wirkungslos - sein Kommentar: *„the counter runs, the duty steps,
and brightness does not change"*.

## PH17 und PH18 - die anderen zwei PWM-Kanäle

Der Vendor-U-Boot-Devicetree hat drei PWMs auf `status = "okay"`: pwm0 auf
PH17, pwm1 auf PH18, pwm2 auf PB4. Naheliegend als Lichtregler, ist es aber
nicht.

**PH17 ist der Lüfter-Tachometer**, also ein Eingang. Steht in den eigenen
Notizen vom 01.04.2026 (`re/notes/session-2026-04-01.md`):

> Stock kernel uses real GPIO IRQ (gpiod_to_irq + request_threaded_irq) for PH17
> Fan tachometer IRQ: debug why EINT doesn't fire on PH17
> Removed pwm0_pins DTS conflict on PH17

Ihn auf high zu ziehen würde gegen den Tacho-Ausgang arbeiten. PH18 taucht
ausschließlich im Bootloader-Devicetree auf, in keinem Kernel-Baum und in
keiner Notiz; zusammen mit dem Tacho daneben ist der Lüfterantrieb die
naheliegende Deutung.

## CPU_COMM-Backlight-Calls

`re/notes/HANDOFF-HDMI-RX-SESSION-20260501-V.md` listet zwölf Init-Calls, die
das Stock-System an die Firmware schickt, und die ersten beiden sind
`BacklightLevel` und `BacklightWorkMode`. Dazu die Routinen-IDs in
`re/notes/cpu-comm-protocol.md`:

| Routine | ID |
|---|---|
| `THal_Vp_SetBrightness_1_000` | `0x7221d017` |
| `Thal_Vp_SetBacklightPwmInfo` | `0xb46ce545` |

**Trotzdem nicht die Erklärung.** Beim Stock-Boot und beim Bootlogo ist das
Bild ohne diese Calls bereits hell. Der Default der Firmware ist hell; sie
wartet nicht darauf, dass ihr jemand einen Pegel mitteilt.

## DLPC3435 an I²C 0x1b

Der stärkste Kandidat, und der Kopfkommentar von
`legacy/drivers/display/ge2d/sunxi_ge2d_dlpc3435.c` liest sich wie die
Lösung - aus dem IDA-RE der Stock-`ge2d_dev.ko`:

> It is NEVER called during initial probe -- **U-Boot initializes the DLPC3435**

Die vollständige Init-Sequenz ist dort rekonstruiert (IDA `0x11af0..0x11b64`):
Register 46 und 18 mit `{w_lo, w_hi, h_lo, h_hi}`, Register 16 mit acht Byte,
dann 26 ← 1, 5 ← 0, 20 ms, 26 ← 0.

**Der Chip antwortet nicht.** `h713_i2c scan` auf PH2/PH3, den TWI1-Pins des
Vendor-Devicetrees:

```
H713 i2c: scanning PH2/PH3
  0x18 ACK   <-- stk8ba58 (bus works)
H713 i2c: 1 device(s) responded
```

Der Bus funktioniert nachweislich (0x18 quittiert), 0x1b bleibt still. Bei
cstenger genauso: *„Hardware now proves that it does not answer on the live
panel boot"*.

**Offener Rest an dieser Stelle:** gescannt wurde nur PH2/PH3. An welchem
I²C-Controller die eigene Kernel-DTS den `dlpc3435@1b`-Knoten hängt, ist nicht
nachgesehen. Falls das ein anderer Bus ist, war der Test unvollständig.

## `h713_disp scanrate`

**Auf diesem Panel unbrauchbar.** Das Werkzeug meldet selbst
`high half max 1023` - der Zähler ist zehn Bit breit, und weder HT = 2200 noch
VT = 1125 passen hinein. Die Ausgabe

```
line rate 35995 Hz -> DCLK 79.18 MHz (panel_config asks 62.00)
frame rate 35990 Hz (line/VT would be 31 Hz)
```

ist Aliasing: die „frame rate" gleich der „line rate" ist für sich schon
unmöglich, und die 62,00 MHz im Vergleich sind cstengers Panel, fest im
Format-String. Auf seinem Board passte VT = 760 noch in zehn Bit.

Die 79 MHz haben mich fast dazu gebracht, die PLL auf N+1 = 83 zu stellen,
also 1992 MHz. Der Takt war die ganze Zeit in Ordnung.

## Firmware laufen lassen statt parken

`h713_disp init 0x30` ohne `quiesce` lässt die MIPS weiterlaufen. Das Bild
bleibt schwarz - aber das ist **kein Befund**: dieser Pfad veröffentlicht
keinen Inhalt, es gibt weder Quelle noch OSD-Ebene. Schwarz ist dort das
korrekte Ergebnis, und der Test unterscheidet nichts.
