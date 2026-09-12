# S39 — Der Stock-Standby-Ablauf (Stufe 2), statisches RE

Stand 09.09.2026. Rein statisch aus `analyse/arisc/scp-wordswapped.bin`,
`analyse/arisc-frame/full-disasm.txt`, dem Stock-DTB, `re/vendor/HY310/extracted/`
und unseren Bäumen. **Kein Board, kein Bau, kein Netz.** Adressregel wie S35:
Blob-Offset = AR100-Adresse = Adresse im Disassemblat, `:N` = Zeile in
`analyse/arisc-frame/full-disasm.txt`. ARM-Adresse = AR100 + `0x100000` (nur SRAM;
Peripherie sieht die AR100 unter denselben Adressen wie der ARM).

## 0. Kurzfassung

| Frage | Antwort | Beleg |
|---|---|---|
| Wie wird Standby ausgelöst? | Eine Nachricht **Typ `0x22`** („cpu op req") an den Standby-Dispatcher auf **msgbox user1 Port 3** (`0x0300347c`) | `doku/68`:1444-1448; Handler `0x00e518` :14663 |
| Nutzlast | **ein** Datenwort: Zeiger auf 5 u32 `{mpidr, entrypoint, cpu_state, cluster_state, system_state}` | `0x00e518`-`0x00e568` :14663-14680; Empfänger `0x007a1c` :8134 |
| Woher die Rücksprungadresse des A53? | `entrypoint` = `paras[1]`; die ARISC schreibt sie nach **`0x08100040`** (`ALT_RVBAR_LO(0)`), `0x08100044` = 0 | `0x004c2c` :4874-4886; TF-A `plat/allwinner/common/include/sunxi_cpucfg_ncat.h:26` |
| DRAM | Selfrefresh; Rückweg über eingebauten „DRAM STANDBY DRIVE" V1.15, Parameter = **`arisc_para`** bei AR100 `0x4008` | `0x0145b0`→`0x014004` :20845/:20429 |
| DTB-Zeiger | **nicht** in `arisc_para`, sondern in **RTC-GP3 `0x0709010c`** | `0x00c30c` :12484, `0x0051c8` :5235 |
| Weckgrund-Meldung | Die ARISC schickt beim Aufwachen **ein** Datenwort = `*(0x17114)` (Weck-IRQ) an den ARM | `0x00e928`-`0x00e938` :14923-14926 |
| Unser Stand | TF-A kennt **kein** `SYSTEM_SUSPEND`, kein SCPI, keinen ARISC-Handoff; Kernel-ARISC-Treiber kennt keine Standby-Nachricht | §4 |

---

## 1. Der Ablauf Ende zu Ende

### 1.1 Android/Kernel → BL31

Der Stock-Kernel ist **arm32** (`re/vendor/HY310/extracted/kallsyms.txt`, Adressen
`c0…`) und hat **keine** eigene Standby-Maschinerie: kein `super_standby`,
`mem_standby`, `arisc_standby`, `standby_para`. Da ist nur `sunxi_standby_class`
(:100289, sysfs), `sunxi_standby_debug_init` (:89319) und — entscheidend —
**`sunxi_smc_copy_arisc_paras`** (:25103): der Kernel reicht die ARISC-Parameter per
SMC an den **sicheren Monitor (BL31)** weiter. Der Standby-Einstieg liegt also nicht im
Kernel, sondern hinter PSCI im Vendor-BL31. (`sunxi_arisc_rpm_send` :26793 ist der
getrennte RPM-Weg, Port 0, HDMI/EDID.)

### 1.2 Was der ARISC-seitige Rahmen verlangt

Empfangsroutine `0x007970` (:8103): `buf[0..3]` = `state|attr|type|result` byteweise,
**`buf[4]` = `count` (ein Byte)**; die `count` Datenwörter landen **nicht** in `buf`,
sondern nach `*(buf+0x1c) + 4*i` (`0x007a1c` :8134) — `buf+0x1c` ist ein
*firmwareseitiger* Zielzeiger auf ein festes Parameterfeld im ARISC-SRAM. Auf der
Leitung liegen also nur Kopfwort, `count` und die Datenwörter (`doku/68`:1437).

### 1.3 Standby betreten — `0x00e518` (:14663)

```
r5 = *(msg+0x1c)                        Zeiger auf die Parameter
printf(2,"mpidr:%x, entrypoint:%x; cpu_state:%x, cluster_state:%x, system_state:%x",
        p[0], p[1], p[2], p[3], p[4])   :14663-14680   (Format 0x14f3d)
if (p[1] == 0) -> 0x00e9b0: 0x4e88(0, p[0])      kein Standby, nur CPU-Op :14966
```
Fortschrittsmarker gehen per `0x0051a0` (:5225) nach **RTC-GP3 `0x0709010c`**
(`0x0051a0`-`0x0051a8` :5225-5227). Reihenfolge beim Einschlafen:

| Marker | Stelle | Was |
|---|---|---|
| `0xf3f31000` | :14684 | `0xcf4c` = `standby_param`-Parser (S35 §1) |
| `0xf3f31001` | :14686 | `0x4f70`; CPUS-Taktquelle `*(0x07010000) & 0x07000000` nach `0x16b70` sichern :14690-14694 |
| — | :14703 | `0x622c(0x12, 0x2000)` → Weckmaske nach `0x16b6c`, Vorgabe `0x2000` |
| `0xf3f32000` | :14713 | `0xdef0` = LEDs (S35 §3a) |
| `0xf3f34000` | :14719 | `printf(2,"wait wakeup")` (`0x14f87`) :14722 |
| `0xf3f35000` | :14727 | `0x103e4` = zwei 0x18-Byte-CEC-Puffer bei `0x172f4`/`0x17214` füllen :16669 |
| — | :14730 | **`0xd87c` = Warteschleife** |

Den A53 schaltet die ARISC hier **nicht** ab — sie muss es nicht: der Kern hat vor
oder nach der Nachricht selbst `WFI` ausgeführt und die CPUIDLE-Hardware
(`0x07000500`/`0x07000504`) hat ihn abgeräumt. Das deckt sich damit, dass in
`0x00e518` vor `0xd87c` kein einziger Schreibzugriff auf `0x09010060`/`0x07000470`
liegt. **Auch DRAM-Selfrefresh stellt die ARISC nicht aktiv ein** — der Rückweg
schaltet „Enable Auto SR" (`0x141ac` :20588, String `0x157b7`), der DRAM-Controller
geht also von selbst in Selfrefresh, sobald niemand mehr zugreift.

### 1.4 Warten — `0x00d87c` (:13851)

```
Marker 0xf3f35001 ; 0xc93c()  ; 0x107cc()
loop: if (*(0x17114) != 0) { printf(2,"wakeup: %d", *(0x17114)); return 0xc978(); }
      *(0x0701033c) |= 0x0f000000
      0x12b04()                       <- OR1K schläft
      *(0x0701033c) &= ~0x0f000000
```
(`:13851`-`:13874`, Format `0x14f1f`.) `0x17114` ist die **Weckquelle**, gesetzt vom
ISR, den `set_wakeup_src` registriert (§3).

### 1.5 Aufwachen — Reihenfolge in `0x00e518`

| Marker | Stelle | Was |
|---|---|---|
| `0xf3f36000` | :14738 | zurück aus `0xd87c`; **`r16 = p[1]` = `entrypoint` neu geladen** :14740 |
| `0xf3f37001` | :14742 | `0xd6cc` = Versorgungsschienen wieder an (PL6, nur wenn GP2==2 oder `power_down`≠0, S35 §3b) |
| `0xf3f37002` | :14745 | wenn `power_down != 0` **oder** Weckmaske-Bit 13 aus: `0xe3a8` (R_PRCM-Gegenstück, S35 §3c) :14747-14756 |
| `0xf3f37003` | :14760 | `0xddec`, `0xe3f4` |
| `0xf3f37004` | :14766 | **`0x4cc4(entrypoint)`** — CPU0 für den Rücksprung vorbereiten (s. u.) |
| `0xf3f37005` | :14770 | `printf(2,"power-up dram")`; MBUS/DRAM-Takt hoch: `*(0x02001540) = *(0x16b68)&7`, `delay 200`, `= &0x03000007`, `delay 20`, `\|= 0x80000000`, `delay 20`, `\|= 0x40000000`, `delay 10000` :14776-14798 |
| — | :14801 | **`0x145b0(0x4008)` → `0x014004(0, 0x4008)`** = DRAM-Standby-Treiber, Parameterblock = `arisc_para` |
| — | :14804 | `0xc714`/`0xc724` = DRAM-CRC; Abweichung gegen `*(0x1711c)` (beim Einschlafen gesetzt, `printf("before_crc: 0x%x")` `0x14f2b` an `0x00e158` :14419-14423) → `printf("ERR:dram crc error…")`, `printf("ERR:---->>>>LOOP<<<<----")`, **Endlosschleife `0xe7b0`** :14806-14828. Konfiguriert über Nachricht **`0x64`** (Handler `0xc6e8`) |
| `0xf3f37006` | :14831 | `0x8da0`, `0x7b4c`; wenn `*(0x030060a0) & 1`: `0x04800004/70/74/78 = 0`, `0x04800080/84/88 = 0xffff`, 8×16 Byte aus `0x16b04`/`0x16b0c` nach `0x04800100/104/108` :14840-14884 |
| `0xf3f37007` | :14888 | **`0x4be4()`** — CPU0 freigeben |
| `0xf3f37008` | :14891 | `printf(15,"wait ac327 resume…")`, dann `receive(buf,0)` in der Schleife :14894-14898 |
| — | :14900 | `buf[2] != 0x11` → `printf(8,"ERR:standby ignore message [%x]")`, weiter warten :14956-14959 |
| — | :14903 | `buf[2] == 0x11` → `printf(2,"cpu0 restore finished")` |
| `0xf3f37009` | :14922 | Antwort an den ARM: `count = 1`, `buf+0x1c = 0x17114`, `send(buf, 100000)` :14920-14926 |
| `0xf3f38000` | :14928 | CPUS-Taktquelle zurück: `*(0x07010000) = (alt & 0xf8ffffff) \| *(0x16b70)`; `0x104e0(1)` :14929-14939 |

`0x11` = `ARISC_SSTANDBY_RESTORE_NOTIFY` in der Vendor-Nummerierung
(`analyse/arisc/vendor-driver/arisc_messages.h:67`) — der ARM muss diese Nachricht
nach dem Wiederanlauf schicken, sonst hängt die ARISC-Hauptschleife.

**Die beiden CPU-Routinen** (Korrektur zu S35 §3, das `0x4cc4` als „Schlaf" führt —
es läuft *nach* dem Aufwachen):

* `0x004cc4(entrypoint)` :4914-4980 — Marker `0xb006`…`0xb00b`; `*(0x070004a0)=1`;
  `*(0x07000440)=0x00010000` (`POWERON_RST_REG(0)`); `0x4768(0,0)` = Bit 0 in
  `0x09010060` (`C0_CPU_CTRL_REG(0)`) löschen = Kern-Reset anlegen; dann
  **`0x4c2c(entrypoint,0)`: `*(0x08100040) = entrypoint`, `*(0x08100044) = 0`**
  (:4874-4886) — das ist `ALT_RVBAR_LO/HI(0)`.
* `0x004be4()` :4858-4866 — Marker `0xb00c`; `*(0x07000470) |= 1`
  (`CPU_UNK_REG(0)`, Gegenstück zu TF-A `sunxi_cpu_ops.c:74-85`); `0x4768(0,3)` =
  Bit 0 in `0x09010060` setzen = **Reset lösen**, Kern startet bei `ALT_RVBAR`;
  Marker `0xb00d`.

Adressbestätigung unabhängig aus unserem TF-A:
`mainline/external/arm-trusted-firmware/plat/allwinner/sun50i_h713/include/sunxi_cpucfg.h:11-17`
nennt exakt `0x09010060+n*4`, `0x07000470+n*4`, `0x07000450+n*4` und
`ALT_RVBAR 0x08100040+n*8`.

### 1.6 „Fake poweroff" — `0x00ea98` (:15015), Typ `0x19`

`*(0x17118)=1`; `r14 = p[0]`; `0x104c0(0)`, `0x104d0(0)`; Marker `0xf4f41000`; wenn
`p[0] & 2`: nochmal `0x104c0/0x104d0`; Marker `0xf4f41002` → `0xcf4c` (Parser),
`0xea70` (= `0xdaac` Power-Key + `0xdc04` bt_powerkey, S35 §3c), `0xdef0` (LEDs),
Marker `0xf4f46000` → `printf("wait wakeup")` → **`0xd87c`** → `0xd6cc` (Schienen).
Also derselbe Schlaf **ohne** DRAM-Wiederanlauf und ohne A53-Resume — das ist das
„Aus" ohne Zustandserhalt.

---

## 2. `arisc_para` und der DTB-Zeiger

* **Der DTB-Zeiger steht nicht in `arisc_para`.** Die Firmware liest ihn **einmal beim
  Start** aus **RTC-GP3 `0x0709010c`** (`0x0051c8` :5235) und legt ihn nach `0x17164`
  (`0x00c30c` :12484). Danach benutzt sie dasselbe Register als Fortschrittsmarker
  (`0x0051a0`). Wer eigene ARISC-Firmware startet, muss den Zeiger also **vor** dem
  Reset-Release dort hinterlegen — sonst überspringt `0xcf4c` das Parsen komplett und
  alle Bank/Pin-Globals bleiben 0 (S35 §5.4).
* **RTC-GP-Karte:** GP2 `0x07090108` (ARISC liest/schreibt über `0x0051f0`/`0x0051dc`
  :5240/:5233; U-Boot setzt GP2 := 2, `doku/103` §1), GP3 `0x0709010c` (DTB-Zeiger +
  Marker), GP5 `0x07090114` (unser Gate, `plat/allwinner/sun50i_h713/sunxi_power.c:34-47`),
  GP7 Fastboot.
* **Korrektur zu `doku/103` §3/M6:** **`GP3 = 0xb00f` ist kein „ARISC-Vorparameter",
  sondern ein Fortschrittsmarker** — `0x00c544` (:12626) schreibt ihn direkt nach dem
  Startup-Handshake `0xc67c` und vor `printf("startup feedback ok")` und der
  Hauptschleife `0x00c5b0`; er heißt schlicht „ARISC läuft". `0xb004`…`0xb00d` =
  CPU-Power-Marker (`0x4be4`/`0x4cc4`), `0xf3f3xxxx` Standby, `0xf4f4xxxx`
  Fake-Poweroff, `0xf1f1900f` DRAM-CRC-Fehler (:14785).
* **Der Block selbst:** 128 Byte, vom Vendor-BL31 aus DRAM `0x48000030` nach ARM
  `0x00104008` = AR100 `0x4008` kopiert (`analyse/arisc/BEFUND.md:36-63`); im Blob
  liegt dort ein genullter Platzhalter hinter dem Kopf `0x4000`
  (`{0x00000003, "sUPC"}`, BEFUND.md:138-142).
* **Neu belegt: der DRAM-Standby-Treiber liest ihn.** `0x145b0` ist ein Thunk auf
  `0x014004(0, 0x4008)` (:20845-20850); `0x014004` benutzt `r4` als **Strukturzeiger**:
  `printf(15,"DRAM STANDBY DRIVE INFO: %s","V1.15")`, dann `*(para+0x5c) & 0x00010000`
  (:20437-20440) und `*(para+0x4c) & 0x00010000` (:20443-20446) als Verzweigungen,
  danach `*(0x07010254)` (:20452-20455). **Damit ist bewiesen, dass `arisc_para` mehr
  als den Message-Pool trägt** — mindestens zwei Flag-Wörter bei `+0x4c` und `+0x5c`.
* Der 3.4-Vendor-Aufbau (`machine, oz_scale_delay, oz_onoff_delay, message_pool_phys,
  message_pool_size, uart_pin_used, services_used, power_regu_tree[15], reserved[10]`,
  zitiert in Patch `0091`) legt `+0x4c` in `power_regu_tree` und `+0x5c` in `reserved` —
  **passt nicht**. Der Aufbau dieser TV-Firmware ist ab `+0x4c` **offen**.
* `standby_param` selbst kommt aus dem DTB, nicht aus `arisc_para`
  (`re/vendor/HY310/extracted/dtb_extracted/hy310-board.dts`, Knoten `/standby_param`:
  `power_key="PL4"`, `vdd-cpu/vdd-sys/vcc-pll/vcc-dram="PL6"`, `led_red="PL0"`,
  `led_blue="PL1"`, `power_down=<0>`, `key_debounce=<0x32>` = 50 ms).

---

## 3. Weckquellen

**Registrierung** über den Standby-Dispatcher, Port 3:
`0x26` = `set wakeup src req` → `0x00c994` (:12902), `0x25` = `clear wakeup src req` →
`0x00cae0` (:12985) (`doku/68`:1447-1448).

`0x00c994` nimmt **ein** Wort `p[0]` und packt drei 10-Bit-Felder plus einen Modus:

```
irq   = p[0] & 0x3ff          printf(2,"wakeup_root_irq: %d", irq)   :12907-12910
mode  = p[0] >> 30
mode == 3 : 0x1330c(p[0] & 0x3fffffff) -> Ergebnis nach *(0x16aa0)   :12913-12920
sonst     : 0xc768(irq); == -1 -> "ERR:%s(%d) irq_no error, root_irq %x"
                                  ("set_wakeup_src" 0x15ab0, Zeile 0x86)  :12921-12933
            wenn *(0x17114) == irq -> *(0x17114) = 0                 :12934-12939
            felder = { irq, (p[0]>>10)&0x3ff, (p[0]>>20)&0x3ff }
            0xc830(felder) -> h ; 0x6058(h, 0xc864, 0) ; 0x5fd0(h) ; 0x6028(h,0)
            *(0x17118) = 1                                            :12940-12976
```
`0xc864` ist der gemeinsame Weck-ISR; er trägt die Quelle in `0x17114` ein — das ist
die Variable, die `0xd87c` pollt und die beim Aufwachen als **einziges Datenwort an den
ARM zurückgeht** (§1.5, `0x00e928`-`0x00e938`). Ein Weckgrund-Register gibt es nicht;
der Rückkanal ist die Antwortnachricht.

**Die Übersetzungstabelle `src → irq_no`** (`0xc768`, liefert −1 bei unbekannter
Quelle) liegt **zweimal identisch** im Blob, je 14 Einträge à 8 Byte big-endian
`{src, irq}` — bei `0x15a40` (direkt hinter dem String `clear_wakeup_src` `0x15a2c`)
und bei `0x15ac0` (hinter `set_wakeup_src` `0x15ab0`). Byteweise nachgeprüft mit
`xxd -s 0x15a40 -l 0x70 analyse/arisc/scp-wordswapped.bin`:

```
0x12→0x3e  0x12→0x3f  0x12→0x40  0x12→0x41  0x12→0x42  0x12→0x43  0x12→0x44
0x00→0xac  0x09→0xb3  0x0f→0xb4  0x0e→0xb5  0x11→0xb6  0x10→0xb7  0x20→0xbb
```

Belegt sind daraus **`src 0x0e` = `power_key`** und **`src 0x10` = `bt_powerkey`** über
die Registrierungen `0xda6c`/`0xdbc4` (S35 §3c). Die `irq_no`-Spalte sind
**ARISC-interne** Nummern, **nicht** die GIC-SPI aus dem Stock-DTB: `s_cir@7040000`
hat dort `interrupts = <0 0x9B 4>` (`hy310-board.dts:1433`), und 0x9b steht nicht in
der Tabelle. Welche Zeile CIR bzw. CEC ist, bleibt damit **offen**.

**Konkrete Quellen auf diesem Board:**

* **Taste PL4** — `0x00daac` (:13996): `set_cfg(PL,4,0x0e)` (Mux **14** = EINT),
  `0x07022200` Triggerfeld auf 1 = fallende Flanke, Pending in `0x07022214` löschen,
  `0x07022210` Bit 4 freigeben; `0xda6c` (:13980) registriert `0xd9c0` als Rückruf für
  **Weckquelle 14**. Der Rückruf wartet `key_debounce*1000` und wertet `PL_DATA` Bit 4
  `== 0` als „gedrückt" (S35 §3c). `bt_powerkey` = `0x00dc04`, Trigger 2 (High-Pegel),
  Weckquelle **16**.
* **CIR PL9** — Parser `0x008f6c`, Strings `cir_param`/`count`/`ir_power_key_code`/
  `ir_addr_code` (`0x149ef`, `0x14a17`, `0x15910`, `0x15930`); Pin-Init
  `set_cfg(1,9,3)`, `set_pull(1,9,1)`, `set_drive(1,9,0)` (:9295-9304). Das Stock-DTB
  liefert `gpio_group="PL"`, `gpio_pin=<9>`, `gpio_function=<3>`, **`count=<0x13>` = 19
  Paare** `ir_power_key_codeN`/`ir_addr_codeN` (`hy310-board.dts`, Knoten `/cir_param`;
  z. B. `0x14`/`0xff00`, `0x45`/`0xff00`, `0xf2`/`0x2992`). Das sind NEC-Adresse und
  ‑Kommando; nur diese Paare wecken.
* **CEC** — Puffer `0x17214`/`0x172f4`, gefüllt in `0x103e4` (:16669) direkt vor dem
  Schlafen; Strings `bCECWakeupEnabled=%d` (`0x15196`), `Backup CEC setting` (`0x15229`).
  Der Modus `p[0]>>30 == 3` (→ `0x1330c`, Ergebnis nach `0x16aa0`) ist der plausibelste
  Kandidat für die Nicht-EINT-Quellen; **nicht belegt**, s. §5 R3.

---

## 4. Was unserem Stack für Stufe 2 fehlt

TF-A-Pfade relativ zu `mainline/external/arm-trusted-firmware` (HEAD `3b3fb35fa`).

| # | Ebene | Lücke | Beleg |
|---|---|---|---|
| 1 | TF-A | **`get_sys_suspend_power_state` fehlt** in `sunxi_native_psci_ops` → `PSCI_SYSTEM_SUSPEND` wird gar nicht angeboten; Linux-`s2ram` scheitert sofort | `plat/allwinner/common/sunxi_native_pm.c:134-145`; `lib/psci/psci_setup.c:275-286` |
| 2 | TF-A | `sunxi_pwr_domain_suspend` behandelt **nur** AFFLVL0 und ist dort identisch mit „CPU aus": kein Cluster-/Systempfad, kein Kontext, kein Selfrefresh, keine Weckquellen. `CPU_SUSPEND` ist seit `47ee829f7` angemeldet, der Powerdown-Fall laut Commit-Text nie geprüft | `sunxi_native_pm.c:79-86` |
| 3 | TF-A | **Kein ARISC-Handoff:** `SUNXI_PSCI_USE_SCPI := 0` plus `$(error)`-Riegel; `sunxi_msgbox.c`, `css_scpi.c`, `sunxi_scpi_pm.c` werden nicht übersetzt. `sunxi_execute_arisc_code()` ist für H713 nur deklariert (implementiert nur für A64) | `plat/allwinner/sun50i_h713/platform.mk:9-11,18-20`; `common/allwinner-common.mk:55-59`; `common/include/sunxi_private.h:51` |
| 4 | TF-A | `sunxi_idle_states.c` ist leer und `fdt_add_cpu_idle_states()` läuft nur im SCPI-Fall → der Kernel bekommt keine Idle-Zustände | `plat/allwinner/sun50i_h713/sunxi_idle_states.c:9-11`; `common/sunxi_prepare_dtb.c:39-44` |
| 5 | TF-A | **Neu zu schreiben:** Suspend-Einstieg, der die 5 Parameter füllt (`entrypoint` = Resume-Adresse in BL31), Typ `0x22` auf Port 3 absetzt, `WFI` macht — und nach dem Wiederanlauf Typ **`0x11`** zurückschickt | §1.3/§1.5 |
| 6 | Kernel | Der ARISC-Treiber kennt Port 3 ausdrücklich **nur für die Startup-Quittung** (`PORT_STANDBY 3`); keine Standby-, Weckquellen- oder Poweroff-Nachricht | `mainline/patches/kernel/0091-soc-sunxi-h713-arisc.patch`:439 |
| 7 | Kernel | **`arisc_para` wird genullt** bis auf `message_pool_phys = 0x00123000` / `_size = 0x1000` — die von `0x014004` gelesenen Flags `+0x4c`/`+0x5c` sind damit 0, ohne dass wir wüssten, was 0 bedeutet | Patch `0091`:495-498; `doku/82`:120-123 |
| 8 | Kernel | **Kein DTB-Zeiger:** weder Treiber noch `analyse/arisc-loader/arisc_load.py` schreiben `0x0709010c`. `standby_param`/`cir_param` stehen in `sun50i-h713.dtsi`, die ARISC sieht sie nie | `doku/82`:125-126 |
| 9 | Kernel | Suspend-Ops, `wakeup-source` an der Taste, IR-Wecken: existiert nichts davon | `doku/103` §1 |
| 10 | ARISC | Die Stock-`scp.bin` ist **unverändert benutzbar** (wir laden sie bereits so, HDMI läuft produktiv). Neu nötig sind nur DTB-Zeiger in GP3 und ein korrektes `arisc_para` | `doku/82` §3 |
| 11 | ARISC | Die Typnummern dieser Firmware sind **nicht** die aus `arisc_messages.h` (dort wäre `0x22` = `CPUX_DVFS_CFG_REQ`, Standby `0x10`). Gültig ist allein die Dispatcher-Tabelle | `doku/68`:1442-1450 |
| 12 | ARISC | **Kein Vendor-C-Quelltext für Standby im Repo** (`sunxi_pm.c`, `super_standby_para`, `extended_standby_t`, `CPUS_WAKEUP_*` gezielt gesucht — nur s390-Fehltreffer). Vendor-C ist nur `analyse/arisc/vendor-driver/`. Daraus brauchen wir `arisc_hwmsgbox_standby_suspend()`: es maskiert vor dem Schlafen **beide ARISC-TX-Interrupts** zum AC327, sonst weckt die Antwort den ARM zur Unzeit | `analyse/arisc/vendor-driver/hwmsgbox.c:498-517` |
| 13 | DRAM | `SUNXI_BL31_IN_DRAM := 1` → BL31 liegt bei `0x40000000`. **Der Resume-Code kommt erst zum Zug, nachdem die ARISC den DRAM hochgefahren hat** — die Reihenfolge in §1.5 (DRAM vor `0x4be4`) passt, ist aber eine harte Abhängigkeit | `platform.mk:7`; `common/include/platform_def.h:16-24` |
| 14 | DRAM | Ob unsere SPL-DRAM-Initialisierung einen Selfrefresh-Wiederanlauf verträgt, ist **irrelevant**: die ARISC macht ihn mit ihrem eigenen Treiber, die SPL läuft im Resume gar nicht | §1.5 |
| 15 | DRAM | Der CRC-Zweig endet bei Abweichung in einer **Endlosschleife** — ohne UART sieht man nichts | :14828 |
| 16 | U-Boot | Resume läuft **nicht** durch U-Boot (Start bei `ALT_RVBAR` in BL31, nicht am Reset-Vektor); die GP5-Gate-Logik muss beim echten Kaltstart weiter greifen. Kein Konflikt mit GP3, **aber**: die ARISC schaltet nach dem Aufwachen die Schienen nur, wenn **GP2 == 2** oder `power_down != 0` — U-Boot muss GP2 := 2 setzen wie der Stock | `board/sunxi/board.c:1174-1236`; `0xd6cc`, S35 §3b |
| 17 | — | Stufe 1 bleibt der Rückfall: 4 W gemessen; Stufe 2 muss deutlich darunter liegen | `doku/103` M5 |

---

## 5. Risiken, Unbekannte, Messung

| # | Offen | Wie messen |
|---|---|---|
| R1 | Aufbau von `arisc_para` ab `+0x4c` (zwei Flags mit Bit 16) | Stock-Speicherabbild von ARM `0x00104008` (128 B) im laufenden Stock-Android per `/dev/mem` ziehen und mit unserem genullten Block vergleichen. Positivkontrolle: `+0x0c/+0x10` müssen den Message-Pool zeigen. Papierquelle für DRAM-Werte: `legacy/reference/sys_config.fex:48-73` (`[dram_para]`, clk 792, type 3, `dram_tpr*`) |
| R2 | Ob der Standby-Rahmen wirklich `count = 1` + Zeiger ist | Am Gerät: Typ `0x22` mit `count = 1` und einem Zeiger auf 5 Wörter in `0x115000`-`0x118000` absetzen und den R_UART der ARISC (`0x07080000`, `doku/68` §„Firmware-Log") abgreifen — die `mpidr:%x, entrypoint:%x…`-Zeile ist die Quittung. **Ohne R_UART-Abgriff blind** |
| R3 | Wo genau `0x1330c`/Modus 3 in `set_wakeup_src` hinführt (CEC? GPIO-Gruppe?) | `0x1330c` disassemblieren (noch nicht getan) |
| R4 | Was `0x030060a0` Bit 0 und der Block `0x04800000` im Resume sind (:14831-14884) | Register aus U-Boot lesen; `0x048…` ist DRAM-Umfeld (`re/notes/H713_DRAM_REVERSE_ENGINEERING.md:14-16` nennt MCTL CTL `0x4820000`, PHY `0x4810000`) |
| R5 | `0x07010250`/`0x07010260`/`0x0701033c`/`0x07010254`-Bits (R_PRCM) | Aus U-Boot vor/nach Stufe-1-Gate lesen; unverändert offen aus S35 §5.5 |
| R6 | Kein Watchdog auf dem Board (`memory:board-kein-watchdog…`) und die DRAM-CRC-Endlosschleife | Jeder Standby-Versuch braucht UART am Gerät und Marcos Hand an der Steckdose; **nie** auf Selbsterholung warten |
| R7 | Zusammenspiel mit der MIPS im gehaltenen DRAM (Marcos Hinweis, `doku/103` §7) | Vor dem ersten Standby-Versuch klären, ob die MIPS-Firmware im DRAM steht und ob sie nach dem Resume neu geladen werden muss |
| R8 | `sunxi-fel` als Rückweg | Bei einem hängenden Resume ist FEL der einzige Weg zurück ohne Flash — vorher prüfen, dass das Gerät ihn erreicht |

## 6. Restliste (statisch, ohne Gerät zu erledigen)

* `0x1330c`, `0xc830`, `0x6058` (IRQ-Registrierung), `0x12b04` (Schlaf) disassemblieren
  und die Felder `(p[0]>>10)&0x3ff` / `(p[0]>>20)&0x3ff` aus `set_wakeup_src` klären.
* **Billigster nächster Beleg:** ob der Stock-BL31 (`analyse/arisc/monitor.asm`) den Typ
  `0x22` tatsächlich baut — im Disassemblat nach `0x0022` zusammen mit `0x0300347c`
  suchen. Das würde §1.1 direkt belegen statt nur aus den kallsyms zu schließen.
