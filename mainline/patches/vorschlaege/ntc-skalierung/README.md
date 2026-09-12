# NTC-Skalierung: aus dem Rohwert eine Temperatur machen

Stand 11.09.2026. Grundlage: Serie bis 0145, Baum
`mainline/build/linux-6.18.38-996a79d2…` (Linux 6.18.38, arm64).
Kein Zugriff auf das Geraet — alles hier ist aus dem Stock-`vmlinux` und aus
Marcos Messprotokoll `analyse/boot/ntc-gpadc-messung-20260911.txt` abgeleitet.

## Kurzfassung

| | |
|---|---|
| Einheit der `gpadc-table` | **Millivolt** |
| Umrechnung | `mv = raw * 439 / 1000` (439 = 1800000/4095 µV je LSB bei 12 Bit an 1,8 V) |
| Rohwert 1766 | 775 mV → **52,9 °C** (der Hersteller selbst wuerde 52 °C sagen) |
| Leseverfahren | Median aus 5 Abtastungen im board-mgr; im GPADC-Treiber 12-Bit-Maske und Verwerfen der ersten Wandlung nach einem Kanalwechsel |
| Wenn nichts passt | `temp1_input` wird gar nicht erst angelegt bzw. meldet `-ENODATA`, mit Grund im Log |

Die Dateien:

- `0146-misc-hy310-board-mgr-den-ntc-rohwert-in-millivolt-umrechnen.patch`
- `0147-iio-adc-sun20i-gpadc-zwoelf-bit-maskieren-und-nach-kanalwechsel-verwerfen.patch`

Beide sind gegen den oben genannten Baum erzeugt und lassen sich mit
`patch -p1` sauber anwenden (geprueft, siehe „Nachweis, dass es uebersetzt“).

---

## A. Die Umrechnung

### Die Einheit ist Millivolt — und das ist belegt, nicht geraten

Die Kette im Stock-`vmlinux` (ARM32, mit DWARF, Quelldatei `pwm_fan.c`),
Adressen wie im Messprotokoll:

```
ntc_read                        c05db9a0
  get_adc_data(priv, src, ch)   c05db32c
    src==1 -> sunxi_gpadc_read_channel_data   c06b93f8
                sunxi_gpadc_read_data         c06b9090
  get_temp_data(src, wert)      c05db970
    src==1 -> search_table_gpadc              c05db898
```

**1. Der Rohwert ist die 12-Bit-Zahl aus dem Datenregister.**
`sunxi_gpadc_read_data` springt ueber eine Sprungtabelle auf den Kanal und
maskiert:

```
c06b90d0  ldr   r0, [r0, #0x84]     ; Kanal 1, also 0x80 + 4*1
c06b90d8  ubfx  r0, r0, #0, #0xc    ; 12 Bit
```

Das ist genau das Register, das Marco am Geraet mit 1766 gelesen hat.

**2. Der Rohwert wird durch 1000 geteilt, nachdem er mit 439 malgenommen
wurde.** `sunxi_gpadc_read_channel_data`:

```
c06b9434  movw  r3, #0x1b7          ; 439
c06b9438  mul   r0, r3, r0
c06b943c  ldr   r3, [pc, #0x14]     ; 0x10624dd3 = 274877907
c06b9440  umull r0, r1, r0, r3
c06b9444  lsr   r0, r1, #6          ; umull-Hochwort ist >>32, mit lsr #6 -> >>38
```

`umull` mit 274877907 und Schieben um 38 ist die uebliche Division durch 1000
(2^38/1000 = 274877906,944 → aufgerundet 274877907). Es bleibt

```
mv = raw * 439 / 1000
```

439 ist 1800000/4095, also die **Mikrovolt je LSB**. Durch 1000 sind das
**Millivolt**.

**3. Die Tabelle wird unveraendert aus dem DTS uebernommen.**
Das war der offene Punkt: ob `gpadc_table_init` (c05d8f84) die DTS-Werte noch
umrechnet. Tut es nicht. Die Funktion zaehlt die Eintraege, belegt ein Feld aus
8-Byte-Paaren und kopiert Wort fuer Wort:

```
c05d8fbc  bl    of_property_count_elems_of_size
c05d8fe4  asr   r1, r6, #1              ; Paare = Elemente/2
c05d8ff8  bl    devm_kmalloc_array…     ; Paare * 8 Byte
c05d901c  bl    of_property_read_u32_array
c05d9038  add   r2, r8, r4             ; r8 = Rohfeld, r4 = i*8
c05d903c  ldr   r2, [r2, #4]            ; Element 2i+1 = Wert
c05d9048  str   r2, [r3, #4]            ;   -> Eintrag[i].wert
c05d904c  ldr   r2, [r8, r6, lsl #3]    ; Element 2i   = Temperatur
c05d9058  str   r2, [r3, r4]            ;   -> Eintrag[i].temp
```

Keine Multiplikation, keine Division, kein Faktor 1000. Die Literale der
Funktion sind nur `"gpadc-table"` und drei Debug-Formate
(`"gpadc-table = {\n"`, `"%d,%d\n"`, `"}\n"`) — keine Einheitenangabe, aber
auch nichts, was rechnet.

**4. Verglichen wird genau gegen diese Werte.** `search_table_gpadc` nimmt das
Ergebnis aus Schritt 2 und vergleicht es mit `Eintrag[i].wert`. Damit steht die
Tabelle in derselben Einheit wie das Ergebnis: Millivolt.

### Zwei unabhaengige Gegenproben

- **Die Schranke.** `search_table_gpadc` verwirft die 0 und alles ueber
  `0x6cc = 1740` (`c05db8a4 movw r3, #0x6cc`). Der Vollausschlag waere
  `4095*439/1000 = 1797`. Eine Schranke bei 1740 ergibt in Millivolt Sinn
  (knapp unter Vollausschlag: „Fuehler fehlt / Vorwiderstand offen“); in
  Mikrovolt waere sie sinnlos.
- **Der LRADC-Zweig.** Fuer `source==0` rechnet `get_adc_data`
  `mov r0, #0x15 ; mul r0, r0, r4`, also **21 mV je LSB** des 6-bittigen LRADC.
  Der groesste Eintrag der `lradc-table` ist `0x41A = 1050 = 50 * 21`, und 50
  ist ein glatter 6-Bit-Rohwert. Beide Tabellen desselben Knotens stehen in
  derselben Einheit — Millivolt.

### Was bei 1766 herauskommt

```
1766 * 439 / 1000 = 775 mV
```

Nachbarschaft in der Tabelle:

| °C | mV |
|---:|---:|
| 51 | 803 |
| **52** | **788** |
| **53** | **774** |
| 54 | 760 |
| 55 | 745 |

775 mV liegt zwischen 774 und 788. Der Hersteller liefert das ganze Grad des
unteren Randes des Intervalls, also **52 °C**. Der Patch rechnet zwischen den
Stuetzstellen linear weiter und liefert **52,929 °C** (`temp1_input = 52929`).
An den Stuetzstellen selbst kommt bei beiden dasselbe heraus.

Warum das plausibel ist:

- CPU und GPU lagen bei derselben Messung bei **53 bis 54 °C**, der Beamer lief
  mit Bild, der Luefter bei etwa 4800 U/min. Ein Board-NTC in der Naehe liegt
  erwartbar dort.
- `temp_warn` ist 55, `temp_poweroff` ist 60. 52,9 liegt darunter — das Geraet
  soll im Normalbetrieb genau dort liegen.
- Es ist weder 0 noch 99, die beiden Zahlen, an denen die Sache bisher zweimal
  gescheitert ist.

Die Empfindlichkeit: ein Grad sind hier rund 14 mV, also etwa 33 LSB. Der
gemessene Rohwert 1766 liegt dicht am Rand — 1765 ergaebe glatt 53,000 °C.
Genau deshalb rechnet der Patch in Milligrad und interpoliert, statt bei jedem
LSB um ein ganzes Grad zu springen.

### Umrechnungstabelle zum Nachrechnen am Geraet

| °C | mV | Rohwert |
|---:|---:|--------:|
| 0 | 1510 | 3440 |
| 20 | 1272 | 2898 |
| 25 | 1200 | 2734 |
| 30 | 1124 | 2561 |
| 40 | 970 | 2210 |
| 50 | 817 | 1862 |
| 52 | 788 | 1795 |
| 53 | 774 | 1764 |
| 55 | 745 | 1698 |
| 60 | 676 | 1540 |
| 70 | 551 | 1256 |
| 80 | 443 | 1010 |

Randverhalten (wie beim Hersteller): Rohwert ≥ 3440 (≥ 1510 mV) → 0 °C;
Rohwert ≤ 1011 (≤ 443 mV) → 80 °C; Rohwert ≥ 3966 (> 1740 mV) oder ≤ 2
(0 mV) → **ungueltig**, keine Temperatur. Die Rohwerte in der Tabelle oben sind
jeweils der kleinste, der genau diesen Millivoltwert ergibt.

Die Fehlerrichtung stimmt: der NTC ist der untere Zweig des Teilers (die
Spannung faellt mit steigender Temperatur), also ergibt ein offener oder
kurzgeschlossener Fuehler wenig Spannung und damit **80 °C** — Alarm, nicht
Entwarnung.

---

## B. Das Leseverfahren

### Was die Messung wirklich sagt

Im Auftrag stand als Ursache der Kanalwechsel in `sun20i_gpadc_adc_read()`.
**Die Zahlen vom 11.09. stuetzen das nicht.** Aus dem Messprotokoll:

```
in_voltage1_raw, 120x nur ch1              : min=680 max=1777 stdabw=115,35
in_voltage1_raw, 120x mit ch0 abwechselnd  : min=680 max=1772 stdabw=115
```

Beim reinen Kanal-1-Lesen findet gar kein Umschalten statt — `last_channel`
bleibt nach der ersten Messung stehen —, und die Streuung ist trotzdem
dieselbe. Die Ausreisser kommen also **nicht** vom Kanalwechsel. Der Mittelwert
1747,6 bei einem Maximum von 1777 und einem Minimum von 680 heisst ausserdem:
das sind ein bis zwei Ausreisser unter 120, keine Streuung.

Woher sie kommen, ist **offen**. Ohne Geraet laesst sich das nicht klaeren, und
ich habe keine Erklaerung, die ich belegen koennte. Was sich sagen laesst: ein
Ausreisser nach unten bedeutet nach der Tabelle *mehr* Temperatur — 680 sind
298 mV und damit die 80 °C am unteren Tabellenrand. Das ist die Richtung, in
der die Abschaltschwelle haengt.

### Die Entscheidung

**Im board-mgr (Patch 0146): Median aus fuenf Abtastungen.**
Das ist die einzige Massnahme, die einzelne Ausreisser wegnimmt, ohne zu wissen,
woher sie kommen. Fuenf Abtastungen vertragen bis zu zwei Ausreisser. Kosten:
fuenf Wandlungen alle 2,5 s, je unter 3 ms. Hier gehoert es hin, weil hier die
Schwelle haengt.

**Im GPADC-Treiber (Patch 0147): zwei Dinge, sauber getrennt.**

1. *Belegt:* `*val = readl(CH_DATA(ch))` maskiert nicht. Der Wandler hat zwoelf
   Bit; der Hersteller maskiert (`ubfx r0, r0, #0, #0xc`). Am H713 aendert das
   heute nichts (die oberen Bits waren null), es nimmt aber eine ganze
   Fehlerklasse weg.
2. *Begruendet, nicht belegt:* nach einem Kanalwechsel wird die erste Wandlung
   verworfen. Begruendung ist das Herstellerverhalten — `sunxi_gpadc_read_channel_data`
   schaltet **ueberhaupt nicht** um, sondern prueft nur die Freigabemaske und
   liest das Datenregister; die Kanaele werden einmal beim Einrichten
   freigegeben. Der Mainline-Treiber schaltet je Messung um und misst sofort.
   Das ist bei einem gemultiplexten Eingang die klassische Stelle fuer einen
   Fehlwert. **Es erklaert die oben genannten Ausreisser nicht** und ist nicht
   der Grund, aus dem der Median existiert. Es schuetzt den board-mgr in dem
   Fall, den Marco benannt hat: sobald jemand `in_voltage0_raw` anfasst, ist die
   naechste board-mgr-Messung eine erste Messung nach einem Umschalten.

**Nicht angefasst:** das Register `SR` (0x00) mit dem Feld TACQ. Der Hersteller
schreibt es (`sunxi_gpadc_sample_rate_set`, c06ba388: `(clk/rate)-1` in Bit
31:16), der Mainline-Treiber nie. Ob der Ruecksetzwert fuer die Quellimpedanz
des NTC-Teilers reicht, laesst sich ohne Datenblatt und ohne Geraet nicht
sagen, und ein geratener Wert wuerde D1 und T113 mit treffen. Das bleibt als
Verdaechtiger fuer die Ausreisser stehen.

---

## Wenn nichts passt: lieber gar keine Temperatur

Bisher lieferte `hy310_ntc_adc_to_temp()` in jedem Fehlerfall seinen
Standardwert 0, und `temp1_input` meldete 0 °C — nicht unterscheidbar von einer
echten Messung. Neu:

- `temp1_input` wird **gar nicht erst angelegt**, wenn NTC aus ist, kein
  IIO-Kanal da ist oder keine brauchbare Tabelle geladen wurde. Im Log steht
  dann `NTC: Auswertung abgeschaltet (…) -- temp1_input wird nicht angelegt`.
- `temp1_input` meldet **`-ENODATA`**, solange die letzte Messung ausserhalb der
  Tabelle lag oder der Wandler nicht lesbar war. Im Log steht der Rohwert, die
  Millivolt und die Tabelle.
- Eine unbrauchbare Messung **setzt die Zaehler** fuer Warnung und Abschaltung
  zurueck, statt sie weiterzuzaehlen.
- Die Tabelle wird auf Sortierung geprueft und sonst verworfen.
- Die Tabelle wird nach `ntc0/source` gewaehlt statt „erst gpadc, dann lradc“.
- Ein Rohwert ausserhalb von 0..4095 gilt als ungueltig, statt in der
  Multiplikation ueberzulaufen — damit 0146 auch ohne 0147 (der die
  12-Bit-Maske nachholt) nichts Unsinniges rechnet.

`thermal_shutdown` bleibt **aus**. Die Umrechnung ist belegt, der Abgleich der
Kurve gegen ein Referenzthermometer am Geraet steht weiter aus.

---

## Was unsicher bleibt

1. **Die Herkunft der Ausreisser** (680 unter sonst ~1770) ist ungeklaert. Der
   Median deckt sie zu; er erklaert sie nicht. Verdaechtig bleibt das nie
   programmierte TACQ-Feld.
2. **Das Verwerfen nach dem Kanalwechsel** ist aus dem Herstellerverhalten
   geschlossen, nicht gemessen. Es kann sein, dass es nichts bringt. Es kostet
   nur eine Wandlung und nur beim Umschalten.
3. **Die Kurve selbst** ist die des Herstellers. Dass die Umrechnung stimmt, ist
   belegt; dass die Tabelle das Bauteil auf *diesem* Board richtig beschreibt,
   ist nur plausibel (sie kommt aus dem Vendor-DTS desselben Geraets, und der
   Wert passt zu CPU/GPU). Ein Abgleich gegen ein Referenzthermometer fehlt.
4. **439 statt 439,56.** Der Hersteller schneidet 1800000/4095 auf 439 ab. Der
   Patch macht es genauso, damit dieselbe Zahl herauskommt wie im Stock. Mit
   der genauen Skala (1800/4096 aus dem Mainline-Treiber) waeren es bei
   Rohwert 1766 statt 775 mV gerundet 776 mV, also 52,86 statt 52,93 °C — unter
   0,1 °C Unterschied, ohne Belang.
5. **Was der Fuehler misst**, wissen wir nicht: ob Lichtmaschine, Netzteil oder
   Luft. Der absolute Wert ist dadurch nicht belegt, nur plausibel.
6. **`pulses-per-revolution` = 2** fuer den Luefter ist weiterhin nicht gegen
   ein Referenzgeraet geprueft — betrifft die RPM, nicht die Temperatur, steht
   hier nur der Vollstaendigkeit halber.

---

## Nachweis, dass es uebersetzt

Wegwerfbaum `mainline/build/pruefbau-ntc-skalierung` (Kopie von
`linux-6.18.38-996a79d2…`), beide Patches angewendet, gebaut im Container
`h713-build`:

```
$ podman exec h713-build bash -lc 'cd /work/mainline/build/pruefbau-ntc-skalierung && \
    make ARCH=arm64 LLVM=1 -j8 Image modules'
  CC [M]  drivers/misc/hy310-board-mgr.o
  CC      drivers/iio/adc/sun20i-gpadc-iio.o
  AR      drivers/iio/adc/built-in.a
  AR      drivers/iio/built-in.a
  AR      drivers/built-in.a
  AR      built-in.a
  AR      vmlinux.a
  LD      vmlinux.o
  MODPOST Module.symvers
  CC      init/version-timestamp.o
  LD [M]  drivers/misc/hy310-board-mgr.ko
  LD      .tmp_vmlinux1
  LD      .tmp_vmlinux2
  LD      vmlinux.unstripped
  OBJCOPY vmlinux
  OBJCOPY arch/arm64/boot/Image
RC=0
-rwxr-xr-x 1 ubuntu ubuntu 18225664 arch/arm64/boot/Image
-rw-r--r-- 1 ubuntu ubuntu    32888 drivers/misc/hy310-board-mgr.ko
```

Keine Warnungen der beiden Dateien. `make … W=1` meldet nur die bereits vorher
vorhandenen kernel-doc-Hinweise zu undokumentierten Feldern von
`struct hy310_board_mgr` (dazu kommen die drei neuen Felder `ntc_source`,
`ntc_channel`, `ntc_table_name` — dieselbe Sorte Hinweis wie bei allen anderen
Feldern der Struktur).

Anwendbarkeit geprueft:

```
$ patch -p1 --dry-run < 0146-…patch     # checking file drivers/misc/hy310-board-mgr.c
$ patch -p1 --dry-run < 0147-…patch     # checking file drivers/iio/adc/sun20i-gpadc-iio.c
```

Beide ohne Fuzz und ohne Offset gegen `linux-6.18.38-996a79d2…`.

Zusaetzlich die Rechnung selbst als Hostprobe uebersetzt und gegen die
DTS-Tabelle laufen lassen (`gcc -O2 -Wall`, derselbe Code wie im Patch):

```
raw  1766 ->   775 mV -> 52.929 Grad
raw  1765 ->   774 mV -> 53.000 Grad
raw  1777 ->   780 mV -> 52.571 Grad
raw   680 ->   298 mV -> 80.000 Grad
raw  4095 ->  1797 mV -> UNGUELTIG
raw     0 ->     0 mV -> UNGUELTIG
monoton ueber alle gueltigen Rohwerte, Bereich 0..80000 mGrad
```

Beide Patches sind **nur** in diesem Verzeichnis. `patches/kernel/series`,
die vorhandenen Patches und die uebrigen Baeume unter `mainline/build/` sind
unberuehrt. Patch 0145 ist unveraendert — die Kanalwahl `<&gpadc 1>` stimmt
und wurde nicht angefasst.

---

## Testanleitung fuer Marco

Es braucht **beides**: ein neues `Image` (der GPADC-Treiber ist `=y`) **und**
das neue `hy310-board-mgr.ko` (`=m`). Das DTB aendert sich nicht.

### 1. Nach dem Booten: sagt der Treiber, was er tut?

```sh
dmesg | grep -i -e ntc -e board_mgr
```

**Erwartet** (Reihenfolge kann abweichen):

```
hy310-board-mgr …: NTC enabled (ntc_num=0, ntc0.enable=1)
hy310-board-mgr …: NTC: IIO-Kanal geholt (DTS: source=1 -> GPADC, 439/1000 mV/LSB, channel=1)
hy310-board-mgr …: NTC: Tabelle 'gpadc-table' mit 63 Paaren geladen, 1510 mV (0 Grad) bis 443 mV (80 Grad)
```

**Misserfolg**, wenn dort steht:

- `NTC: Auswertung abgeschaltet (…) -- temp1_input wird nicht angelegt`
  → der Grund steht in der Klammer (kein IIO-Kanal / keine brauchbare Tabelle).
- `NTC: Tabelle 'gpadc-table' ist bei Paar N nicht sortiert (…)`
  → das DTS-Feld stimmt nicht mit dem ueberein, was der Patch erwartet.
- `NTC: 'gpadc-table' fehlt im DTS` → falsches DTB geflasht.
- `source=0 -> LRADC` statt `source=1 -> GPADC` → falsches DTB.

### 2. Die Zahl

```sh
H=$(grep -l hy310_board_mgr /sys/class/hwmon/hwmon*/name | xargs dirname)
cat $H/temp1_input
```

**Erwartet** im warmen Betrieb (Bild an, Luefter laeuft): eine Zahl in
**Milligrad**, ungefaehr **50000 bis 56000**. Bei dem Zustand, in dem Marco am
11.09. gemessen hat (CPU/GPU 53–54 °C, Luefter ~4800 U/min), muessen es
**52000 bis 54000** sein, also 52 bis 54 °C.

Zum Vergleich daneben:

```sh
for z in /sys/class/thermal/thermal_zone*; do
  printf '%s %s\n' "$(cat $z/type)" "$(cat $z/temp)"
done
```

Der NTC-Wert soll **in derselben Groessenordnung** wie CPU und GPU liegen, ein
paar Grad Abweichung sind normal (anderer Ort auf der Platine).

**Erfolg:** eine Zahl zwischen 40000 und 58000, die sich beim Aufwaermen
langsam nach oben bewegt und nach dem Abschalten des Bildes wieder faellt.

**Misserfolg:**

- `0` → die Umrechnung greift nicht (das war der alte Fehler).
- `80000` → der Rohwert liegt am unteren Tabellenrand: Fuehler offen oder
  kurzgeschlossen, oder die Kanalwahl stimmt nicht.
- `cat: … Invalid argument` bzw. `No data available` (ENODATA) → der Treiber
  sagt „ich habe keine brauchbare Messung“. Der Grund steht im `dmesg`:
  `NTC: Rohwert N = M mV liegt ausserhalb der Tabelle 'gpadc-table' (…)`.
- `temp1_input` existiert gar nicht → siehe Schritt 1, der Treiber hat die
  Auswertung abgeschaltet und den Grund geloggt.

### 3. Gegenrechnen: stimmt die Zahl zum Rohwert?

```sh
for d in /sys/bus/iio/devices/iio:device*; do echo "$d = $(cat $d/name)"; done
G=<der mit sun20i-gpadc>
cat $G/in_voltage1_raw
```

**Erwartet** im warmen Betrieb: ein Rohwert um **1750 bis 1800**. Umrechnung von
Hand:

```sh
R=$(cat $G/in_voltage1_raw); echo $(( R * 439 / 1000 )) mV
```

Bei Rohwert 1766 müssen 775 mV herauskommen, und `temp1_input` muss dann
**52929** sein (±ein paar hundert Milligrad, weil der Median aus fuenf
Abtastungen zu einem anderen Zeitpunkt gezogen wurde). Die Tabelle oben
(„Umrechnungstabelle zum Nachrechnen am Geraet“) deckt den ganzen Bereich ab.

### 4. Kaltstart-Gegenprobe (optional, kostet einen Stromzyklus)

Direkt nach dem Einschalten aus dem kalten Zustand, **bevor** Bild laeuft:

```sh
cat $H/temp1_input
```

**Erwartet:** deutlich niedriger, in der Naehe der Raumtemperatur, also
ungefaehr **22000 bis 35000** (Rohwert um 2500 bis 2800). Wenn dort direkt nach
dem Kaltstart schon 52 °C stehen, ist entweder der falsche Kanal gewaehlt oder
die Kurve passt nicht zum Bauteil — dann bitte den Rohwert aus Schritt 3
mitschicken.

Das ist der **aussagekraeftigste** Einzeltest: er trennt „die Zahl ist zufaellig
plausibel“ von „die Zahl folgt der Temperatur“.

### 5. Das Leseverfahren pruefen (Patch 0147 und der Median)

Erst den Ist-Zustand von Kanal 1 festhalten:

```sh
for i in $(seq 120); do cat $G/in_voltage1_raw; done \
  | sort -n | awk 'NR==1{min=$1} {a[NR]=$1; s+=$1} END{printf "min=%d max=%d mittel=%.1f n=%d\n", min, a[NR], s/NR, NR}'
```

**Erwartet:** min und max duerfen ein paar LSB auseinanderliegen. Wenn dort
weiterhin ein `min=680` bei `max≈1777` steht, sind die Ausreisser **nicht** weg
— das waere kein Fehler dieses Patches (siehe „Was unsicher bleibt“, Punkt 1),
aber bitte melden, dann ist TACQ der naechste Verdaechtige.

Dann der Test, um den es Marco ging — waehrend jemand den anderen Kanal
anfasst, muss die Temperatur ruhig bleiben:

```sh
( while true; do cat $G/in_voltage0_raw >/dev/null; done ) &
STOER=$!
for i in $(seq 20); do cat $H/temp1_input; sleep 3; done
kill $STOER
```

**Erfolg:** die zwanzig Werte liegen innerhalb von etwa **±1000 Milligrad**
(±1 °C) beieinander, und `dmesg` zeigt **keine** neue Zeile
`NTC: Rohwert … liegt ausserhalb der Tabelle`.

**Misserfolg:** einzelne Werte springen auf 80000, oder es kommen
`liegt ausserhalb der Tabelle`-Zeilen dazu. Dann reicht der Median aus fuenf
nicht und muss hoch (`HY310_NTC_SAMPLES`), oder das Verwerfen greift nicht.

### 6. Was nicht getestet werden muss

`thermal_shutdown` bleibt aus und wird in diesen Tests nicht scharf gemacht.
Erst wenn Schritt 4 zeigt, dass die Zahl der Temperatur wirklich folgt, lohnt
das Gespraech darueber, sie scharf zu stellen.
