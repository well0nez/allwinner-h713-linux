# S35 - ARISC-Standby: LEDs, Power-Key, R_PIO-Register (statisches RE)

Stand 08.09.2026. Rein statisch aus `analyse/arisc/scp-wordswapped.bin`,
`analyse/arisc-frame/full-disasm.txt` und dem Stock-DTB. Kein Board, kein Bau.
**Adressregel:** Blob-Offset = AR100-Adresse = Adresse im Disassemblat
(BEFUND.md), `:N` = Zeile in `full-disasm.txt`. Den DTB-Zeiger holt die Firmware
aus **RTC-GP `0x0709010c`** (`0x51c8`, :5235) nach `0x17164` (`0x00c30c`,
:12484) - genau das Wort, das der Vendor-BL31 vor dem Reset-Release schreibt.

---

## 1. Der DTB-Parser für `standby_param` - `0x00cf4c` (:13268)

* `0x00cf58` (:13271): wenn `*(0x16afc) != 0` -> sofort zurück (Einmal-Flag);
  am Ende `*(0x16afc) = 1` (`0x00d69c`, :13736).
* `0x00cf88`: `node = fdt_path_offset(*(0x17164), "standby_param")` (`0xae90`).
  Bei `node < 0` -> Rücksprung, **kein einziges Global wird gesetzt**.
* u32 über `0xaba4`, Zielzeiger als Argument: `power_down` -> `0x16ab4`
  (`0x00cfa8`, :13291, Vorgabe 0), `key_debounce` -> `0x16ab8`
  (`0x00cfe8`, :13307, Vorgabe 0).
* Pin-Properties über `0xb714` (`getprop_string`), dann `strncmp(str,"PL"/"PM",2)`
  (`0x9848`; Strings `0x14878`/`0x1487b`), `memcpy(buf,str+2,2)` (`0x973c`),
  `str2dec(buf,2)` (`0x967c`) -> **Bank** (1=PL, 2=PM) und **Pin** in zwei
  benachbarten Globals:

| Property | Code | Bank | Pin |  | Property | Code | Bank | Pin |
|---|---|---|---|---|---|---|---|---|
| `vdd-cpu` | `0x00d010` :13317 | `0x16abc` | `0x16ac0` | | `power_key` | `0x00d320` :13513 | `0x16adc` | `0x16ae0` |
| `vdd-sys` | `0x00d0d4` | `0x16ac4` | `0x16ac8` | | `bt_powerkey` | `0x00d3e4` | `0x16ae4` | `0x16ae8` |
| `vcc-pll` | `0x00d198` | `0x16acc` | `0x16ad0` | | `led_red` | `0x00d4a4` :13610 | `0x16aec` | `0x16af0` |
| `vcc-dram`| `0x00d25c` | `0x16ad4` | `0x16ad8` | | `led_blue` | `0x00d5a4` :13674 | `0x16af4` | `0x16af8` |

* `led_red_vol` (`0x00d564`, :13658) und `led_blue_vol` (`0x00d664`, :13722)
  laufen anders: `getprop_string` -> direkt `str2dec(ptr, 1)` -> `0x15c04` bzw.
  `0x15c08`. **Ohne jede Fehlerprüfung.**

### Befund A - die `_vol`-Properties fehlen im echten Stock-DTB

Der ausgelieferte DTB (`analyse/arisc/dtb.bin`, Knoten `/standby_param`;
deckungsgleich in `re/vendor/HY310/extracted/dtb_extracted/hy310-board.dts:2548`,
`.../bootpkg-full.dts:2816`, `re/vendor/HY310/hy310_factory.dts:2548`) enthält
**kein `led_red_vol` und kein `led_blue_vol`**. Die Werte `"1"`/`"0"` stehen nur
in *unserer eigenen* Rekonstruktion
`re/vendor/HY310/extracted/sun50i-h713-hy310.dts:1766-1769` - keine
Herstellerangabe; ebenso der „prj"-Knoten mit `led0`/`led1` (nur dort,
:1555-1556). Codefolge: `0xb714` gibt bei fehlender Property **0** zurück
(`0x00b7e0`, :11769), `str2dec(NULL,1)` liest das Byte an AR100-Adresse 0
(`0x00`, keine Ziffer) und liefert **0** (`0x967c`, :9632). Auf dem Stock-Gerät
gilt also **`led_red_vol = 0` und `led_blue_vol = 0`.**

---

## 2. Die GPIO-Zugriffsschicht

Sechs kleine Funktionen, alle auf **R_PIO 0x07022000**, Bankabstand **0x30**,
Bank 1 = PL:

| Funktion | Zeile | Adressformel | Feld |
|---|---|---|---|
| `set_cfg(bank,pin,fn)` | :6296 `0x625c` | `0x07021FD0 + 0x30*bank + 4*(pin>>3)` | 4 bit @ `(pin&7)*4` |
| `set_drive(bank,pin,v)`| :6358 `0x6354` | `0x07021FE4 + 0x30*bank + 4*(pin>>4)` | 2 bit @ `(pin&15)*2` |
| `set_pull(bank,pin,v)` | :6327 `0x62d8` | `0x07021FEC + 0x30*bank + 4*(pin>>4)` | 2 bit @ `(pin&15)*2` |
| `write(bank,pin,v)`    | :6389 `0x63d0` | `0x07021FE0 + 0x30*bank`, Bit `pin` | |
| `read(bank,pin)`       | :6416 `0x643c` | dito, `>>pin & 1` | |
| `eint_trigger(b,p,m)`  | :6445 `0x64b0` | `0x07021FE0 + 0x20*bank + 0x200 + 4*(pin>>3)` | 4 bit @ `(pin&7)*4` |
| `eint_status(b,msk)`   | :6432 `0x647c` | `0x070221F4 + 0x20*bank` | |

### Befund B - Registerkarte (korrigiert gegenüber der Auftragsannahme)

```
0x07022000  PL_CFG0  (4-bit-Felder, Pin 0..7)   0x07022004/8/C  CFG1..3
0x07022010  PL_DATA
0x07022014  PL_DRV0  (2-bit-Felder, Pin 0..15)  0x07022018  DRV1 (Pin 16..31)
0x0702201C  PL_PULL0 (2-bit-Felder, Pin 0..15)  0x07022020  PULL1
0x07022200  PL_EINT_CFG0   0x07022210 PL_EINT_CTL   0x07022214 PL_EINT_STATUS
```

Also **0x30-Abstand, aber PULL bei 0x1C statt 0x24 und DRV 2-bittig statt
4-bittig** (H616-artige Karte). Unabhängig belegt durch die CIR-Init:
`set_cfg(1,9,3)` (:9295), `set_pull(1,9,1)` (:9299), `set_drive(1,9,0)` (:9304)
- das Stock-DTS sagt für PL9 exakt `function="s_cir"` (=3), `bias-pull-up` (=1),
`drive-strength=<0xA>` = 10 mA = Stufe 0 (`hy310-board.dts:1832-1838`). Marcos
Dump „0x14/0x18 = 0x11111111" heißt damit: alle Pins Treiberstufe 1 (20 mA).

---

## 3. Der Standby-Ablauf

Einstieg `0x00e518` (:14663); Fortschrittsmarker per `0x51a0` (:5225) nach
RTC-GP `0x0709010c`:

```
0xf3f31000 -> standby_param_parse (0xcf4c)      0xf3f34000 -> "wait wakeup\n"
0xf3f31001 -> Wakeup-Maske nach 0x16b6c         0xf3f37001 -> 0xd6cc (Schienen)
0xf3f32000 -> 0xdef0   <-- gesamter LED-Code    0xf3f37004 -> 0x4cc4 (Schlaf)
```

### 3a. LEDs - `0x00def0` (:14269), die einzige LED-Stelle der Firmware

```
0x00df44  set_cfg(blue_bank, blue_pin, 1)          -> PL1 als Ausgang
0x00df4c  vol = led_blue_vol
          vol==1 -> 0x00df70: *(0x07022010) &= ~(1<<pin)
          sonst  -> 0x00dfac: *(0x07022010) |=  (1<<pin)
0x00dff4  set_cfg(red_bank, red_pin, 1)            -> PL0 als Ausgang
0x00dffc  vol = led_red_vol
          vol==1 -> 0x00e03c: *(0x07022010) |=  (1<<pin)
          sonst  -> 0x00e09c: *(0x07022010) &= ~(1<<pin)
```

Semantik: **Rot bekommt seinen Aktivpegel (an), Blau den Gegenpegel (aus).**
Mit den echten DTB-Werten (beide `vol` = 0, Befund A) schreibt die Firmware:
`PL_CFG0 (0x07022000)` Feld[3:0] = 1 **und** Feld[7:4] = 1; dann
`PL_DATA (0x07022010)`: **Bit 1 setzen (PL1=1), Bit 0 löschen (PL0=0)**.
Mit den „gewünschten" Werten unserer DTS wäre es `PL0=1, PL1=1`.
Drive und Pull werden für PL0/PL1 **nie** angefasst.

### 3b. Schienen - `0x00d6cc` (:13748) und der Zweig ab `0x00e234`

Bedingung: `RTC-GP 0x07090108 == 2` **oder** `power_down != 0`. Dann viermal
(vdd-cpu, vdd-sys, vcc-pll, vcc-dram - auf der HY310 alle „PL6"):
`set_cfg(bank,pin,1)` und `*(0x07022010) |= (1<<pin)` -> **PL6 = 1**, danach
`delay(10)`. Im Stock-DTB ist `power_down = 0`, die Sequenz läuft also nur im
Modus 2.

### 3c. Power-Key - `0x00daac` (:13996)

```
set_cfg(pk_bank, pk_pin, 0x0e)              -> PL4 auf Funktion 14 = EINT
*(0x07022200) &= ~(0xF << (pin*4))          -> Triggerfeld löschen
delay(1)
*(0x07022200) |=  (1   << (pin*4))          -> Trigger 1 = FALLENDE Flanke
*(0x07022214) &= ~(1<<pin) ; |= (1<<pin)    -> Pending löschen (EINT_STATUS)
*(0x07022210) &= ~(1<<pin) ; |= (1<<pin)    -> EINT freigeben (EINT_CTL)
```

Für PL4: `0x07022200 |= 0x00010000`, danach `0x07022214`/`0x07022210` Bit 4.
`bt_powerkey` (`0x00dc04`, :14082) identisch, aber Trigger **2 = High-Pegel**.
Es wird **kein Pull** gesetzt - passt zu Marcos „externer Pull-up".
`PL_EINT_DEB (0x07022218)` wird nie beschrieben.
`0xda6c` (:13980) registriert `0xd9c0` als Rückruf für Wakeup-Quelle **14**,
`0xdbc4` (:14066) registriert `0xd92c` für Quelle **16**. Der Handler
`0x00d9c0` (:13937) wartet `key_debounce*1000` (`0x6d9c`), liest `PL_DATA` und
wertet **Bit == 0 als „gedrückt"** (`0x00da20`) - deckt sich mit der Messung
(PL4 im Ruhezustand 1). IR läuft über `cir_param` (`0x008f6c`), Pin PL9
Funktion 3, mit den `ir_power_key_code*` aus dem DTB.
R_PRCM-Zweig `0x00dea8` (:14251): `*(0x07010260) &= ~1`, `*(0x07010250) |=
0x004`, dann `|= 0x100`; Gegenstück `0x00e3a8` (:14571) rückwärts. Bits offen.

---

## 4. Schlussfolgerung zur blauen LED

1. **PL0/PL1 werden in der gesamten ARISC-Firmware an genau einer Stelle
   angefasst**: `0x00def0`, und nur beim *Eintritt* in Standby. Eine
   vollständige Suche über alle Referenzen auf
   `0x16aec/0x16af0/0x16af4/0x16af8/0x15c04/0x15c08` liefert außer dem Parser
   nur diese Funktion; beim Aufwachen setzt die ARISC die LEDs **nie** zurück.
   Sie benutzt dabei **exakt denselben Mechanismus wie Marco** (CFG = 1 =
   Ausgang, Bit in `0x07022010`) - kein PWM, kein I2C/RSB, kein Portexpander,
   keine Sonderfunktion für PL0/PL1.
2. Umkehrschluss: **auf diesem Board hängen die LEDs nicht (nur) an PL0/PL1.**
   Die `standby_param`-Einträge sind Referenzdesign-Bausteine - dafür spricht
   auch, dass alle vier Versorgungsschienen auf denselben Pin „PL6" zeigen und
   die `_vol`-Angaben ganz fehlen.
3. **Starker Verdacht: PWM.** Das Vendor-U-Boot enthält einen PWM-LED-Treiber
   mit `pwm_led`, `device_type`, `led_r_pwm`, `led_g_pwm`, `led_b_pwm`,
   `led_r/g/b`, `led_red/green/blue` und der Meldung „unable to find pwm led
   node in device tree." (`analyse/arisc/u_boot.bin`, Byte-Offsets `0x69343`
   „pwm_led", `0x69357` Meldung, `0x69384` `led_r_pwm`, `0x693c6` `led_blue`).
   Passend führt das Stock-DTS **drei S_PWM-Kanäle auf PL6/PL7/PL8**
   (`hy310-board.dts:1463-1497`, `s_pwm@7020c00`, `pwm-base = <0x10>`,
   `s_pwm0@0`=PL6, `s_pwm1@0`=PL7, `s_pwm2@0`=PL8, je `drive-strength=<0xA>`,
   `bias-pull-up`). Der `pwm_led`-Knoten selbst fehlt im Stock-DTB - U-Boot
   bricht also ab; und Linux hat gar keinen LED-Knoten (kein `gpio-leds` im
   DTB, kein LED-Klassentreiber in einem der 13 Stock-Module unter
   `re/vendor/HY310-DEV/stock_modules/`). **Im Normalbetrieb treibt auf Stock
   niemand die LEDs per Software.** Das erklärt „rot leuchtet von Anfang an
   durchgehend" zwanglos als Hardware-Grundzustand.

---

## 5. Offene Punkte und wie man sie klärt

1. **Reagiert PL0/PL1 überhaupt?** Aus U-Boot `0x07022000` auf `0x00000011`
   setzen, `0x07022010` schreiben und **zurücklesen**. Folgt das Datenregister
   dem Schreibwert nicht, ist der Pin nicht als Ausgang aktiv oder nicht
   gebondet - Positivkontrolle, bevor wieder auf die LED geschaut wird.
2. **S_PWM-Hypothese prüfen** (wichtigster Schritt): PL6/PL7/PL8 einzeln als
   GPIO-Ausgang schalten (`0x07022000` Feld[27:24] für PL6, Feld[31:28] für
   PL7, `0x07022004` Feld[3:0] für PL8) und in `0x07022010` Bit 6/7/8 toggeln.
   Reagiert eine Farbe, ist die Verdrahtung gefunden; reagiert erst mit
   laufendem S_PWM etwas, ist es echt PWM (Block `0x07020C00`, Kanäle
   0x10/0x11/0x12). Achtung: PL6 ist laut `standby_param` gleichzeitig
   „Versorgungsschiene" - erst messen, dann dauerhaft treiben.
3. **Registerkarte gegenprüfen:** `0x0702201C`/`0x07022020` aus U-Boot lesen.
   Plausibles Pull-Muster (PL4 = 0 kein Bias, PL9 = 1 Pull-up) bestätigt
   Befund B; unsere Notizen mit „PULL bei 0x24" wären dann zu korrigieren.
4. **Marker-Register nutzen:** `0x0709010c` ist Fortschrittszähler
   (`0xf3f3xxxx`) *und* DTB-Zeiger-Übergabe. Wenn wir je eigene ARISC-Firmware
   laden, muss dort **vor** dem Reset-Release die DTB-Adresse stehen, sonst
   überspringt `0xcf4c` das Parsen komplett und alle Bank/Pin-Globals bleiben 0
   (= Bank 0, Pin 0 - ein ganz anderer Port).
5. **Weiter offen:** Bedeutung von `0x07010250` Bit 2/8 und `0x07010260` Bit 0
   (R_PRCM); und ob der MIPS-Displayprozessor eine Frontplatinen-LED bedient.
   Dafür gibt es bisher keinen Beleg in DTB, Modulen oder ARISC.

**Korrektur (S39, 09.09. 23:20):** Die in §3 als „Schlaf“ bezeichnete Routine `0x4cc4` läuft nicht beim Standby-Eintritt, sondern **nach dem Wecken**
und bereitet CPU0 vor (Resume-Adresse aus `paras[1]` nach `ALT_RVBAR_LO/HI`, Freigabe über `0x07000470 |= 1` und `0x09010060`). Standby-Eintritt,
Nachrichtenformat (Port 3, Typ 0x22) und Weckgrund siehe S39.
