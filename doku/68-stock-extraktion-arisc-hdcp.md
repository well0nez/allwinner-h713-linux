# Aus den Stock-Daten geholt: HDCP-Keys und ARISC-Firmware

Stand 04.09.2026. Alles hier ist **statisch** aus vorhandenem Stock-Material
gewonnen — kein Hardwarezugriff nötig. Anlass war die Frage, was für HDMI-in
fehlt; die Antwort war: **nichts fehlte, es war nur nicht gesucht worden.**

Vorgänger: [67-cpu-comm-linux.md](67-cpu-comm-linux.md) (der CPU_COMM-Transport,
auf dem das hier aufsetzt).

## Die Lehre zuerst

Zwei Dinge wurden in dieser Sitzung als „fehlt" bzw. „geht nicht" geführt, und
beide waren falsch:

1. **„`hdcp_v22.bin` existiert hier nicht."** Das stützte sich auf ein `find`
   nach dem Dateinamen. Der Key liegt nicht als Datei vor, sondern in Allwinners
   **Secure Storage** im eMMC-Abbild, das wir seit Monaten haben.
2. **„Die ARISC kollidiert mit unserem BL31 im SRAM."** Unser BL31 läuft
   `SUNXI_BL31_IN_DRAM`, liegt also bei `0x40000000` — der SRAM ist frei.

Beide Male war die Prüfung zu flach. Wer in einem Projekt mit 6,9 GB
Vendor-Material „ist nicht da" sagt, muss vorher **im Material** gesucht haben,
nicht im Dateinamen.

## HDCP: die Keys liegen im Secure Storage

### Wie Stock sie behandelt

Zeichenketten aus dem Stock-Bootloader (`update.img`, Offsets 698450 ff.):

```
smc_tee_hdcp_key_encrypt: failed
down hdcp 1.4          down hdcp 2.2
hdcpkeyV22             hdcppkf            hdcpkey
sunxi deal with hdcp key failed / push hdcp key failed
Do secure storage decrypted !!    sunxi_keybox_store
```

Der Stock-Bootloader liest die Keys aus dem Secure Storage, entschlüsselt sie
über TEE und schiebt sie in die Hardware („down hdcp 1.4"). **Unser U-Boot tut
das nicht** — es patcht nur die Warteschleife heraus:

```
H713 MIPS: HDCP key-load wait defeated at 0x4b13d0a4
```

Genau daher der Live-Fehler im MIPS-elog:

```
E/hdmi_driver (THDMIRx_TV303_Driver.cpp 358) HdmiRx_HDCP14_LoadKey(), time out!
```

**Wichtig zur Deutung:** das sind **drei** Zeilen aus der MIPS-Startphase, keine
laufende Schleife. Der elog-Ring steht danach still (`write=1879`); die 10-ms-
Abstände im `dmesg` sind unser Treiber, der den Ring bei jedem `insmod` erneut
ausgibt.

### Wo sie liegen

Secure Storage beginnt bei **`0x600000`** im eMMC (`re/device-dumps/emmc-first-300mb.bin`),
Items je 4 KiB, jeweils mit Sicherungskopie bei `+0x1000`. Item 0 ist die Map:

```
hdcpkey:3176   hdcpkeyV14_hash:3176   hdcpkeyV22:3176
hdcpkeyV22_hash:3176   wifiBleDatas:3176   snum:3176
```

3176 ist exakt `sizeof(store_object_t)` bei sunxi:
`magic(4) + id(4) + name(64) + 6×u32 + actual_len(4) + data(3072) + crc(4)`.
Magic ist `0x17253948`.

| Offset | Item | `actual_len` |
|---|---|---|
| `0x602000` | `hdcpkey` (HDCP 1.4) | 396 |
| `0x604000` | `hdcpkeyV14_hash` | 6 (`"581b62"`) |
| `0x606000` | `hdcpkeyV22` (HDCP 2.2) | 988 |
| `0x608000` | `hdcpkeyV22_hash` | 6 (`"4378ef"`) |
| `0x60a000` | `wifiBleDatas` | 240 |
| `0x60c000` | `snum` | 15 (`HYTY32508181083`) |

### Der innere Aufbau

Die Nutzdaten tragen den Namen nochmal und dann einen Kopf:

```
+0x00  name[64]      "hdcpkeyV22" / "hdcpkey"
+0x40  u32 len       0x390 = 912   bzw.  0x140 = 320
+0x44  u32           0x10000001
+0x48  u32           0x00000001
+0x4C  Nutzdaten
```

Die Rechnung geht exakt auf: `64+4+4+4+912 = 988` und `64+4+4+4+320 = 396`.

**912 ist selbstvalidierend:** genau diese Größe übergibt `hy310-hdmird` an den
MIPS (`HDCP22_STOCK_SIZE`), und genau die steht im Stock-elog
(`HDMIRX_SetHDCP22KeyData!!, size:912`).

Extrahiert nach `analyse/hdcp-keys/`:
`hdcp22-key-912.bin`, `hdcp14-key-320.bin`, dazu die Hashes und `snum`.

### Was damit **nicht** gesagt ist

**Ob die Nutzdaten Klartext oder TEE-Chiffrat sind, ist offen.** Die
Bootloader-Zeichenketten (`smc_tee_hdcp_key_encrypt`, `Do secure storage
decrypted !!`) deuten auf Verschlüsselung. Die Entropie beweist nichts — ein
HDCP-Keyset ist von Natur aus zufällig. Die gespeicherten `*_hash`-Items passen
zu keinem einfachen Digest der Nutzdaten (sha256/sha1/md5 geprüft), was zu
„Hash über den Klartext, gespeichert ist das Chiffrat" passen würde.

Entscheidbar ist das nur am Gerät: `SetHDCP22Key(phys, 912)` mit klarem
Beobachtbaren. Akzeptiert der MIPS, war es Klartext.

## ARISC: die Firmware und ihre Startsequenz

### Wo sie liegt

`re/vendor/HY310/bootloader_a.bin`, sunxi-package bei `0x4000`, fünf Items.
Eintragsabstand `0x170`, 4-Byte-Tag vor jedem 64-Byte-Namen:

| Item | Offset (abs.) | Größe |
|---|---|---|
| u-boot | 0x004800 | 638976 |
| monitor (BL31) | 0x0a0800 | 66060 |
| **scp (ARISC)** | **0x0b0c00** | **176132 = 172 KiB** |
| optee | 0x0dc000 | 275328 |
| dtb | 0x11f400 | 73728 |

Der SCP-Blob ist **wortweise byte-gespiegelt** gespeichert. Entspiegelt steht
bei `+0x100` `00 00 4a 86` = `l.j 0x4a86` — der OR1K-Reset-Vektor. Er wird also
so geladen, dass Blob-Offset 0 auf OR1K-Adresse 0 fällt.

### Wer sie lädt

**Nicht boot0, sondern der Vendor-BL31** (`monitor`), Funktion
`sunxi_arisc_probe`, Meldungen `[SCP] :…`. Das erklärt unmittelbar, warum bei
uns keine ARISC-Firmware läuft: mainline-TF-A ersetzt genau diesen BL31.

**Deshalb ist „ist bei uns keine ARISC-Firmware geladen?" keine Messung wert** —
die Antwort folgt zwingend aus unserem eigenen Aufbau. Sie wurde in dieser
Sitzung trotzdem zweimal gemessen (von cstenger und von hier), was nichts
erbrachte, was nicht vorher feststand.

### Die Sequenz, Schritt für Schritt

Aus `analyse/arisc/monitor.asm`, Lader bei `0x5cb8`, Reset-Freigabe bei `0x5c38`:

```
1.  str  w0, [0x0709010c]                     Parameterwort in RTC-GP-Register
2.  memcpy(0x00100000, 0x48100000, 0x23000)   140 KiB Image  ->  SRAM
3.  cache_flush(0x00100000, 0x23000)
4.  memcpy(0x48100000, 0x48123000, 0x8000)    restliche 32 KiB bleiben im DRAM
5.  cache_flush(0x48100000, 0x8000)
        -> "[SCP] :load arisc image finish"
6.  memcpy(0x00104008, 0x48000030, 0x80)      128 B Parameterblock
        -> "[SCP] :setup arisc para finish"
7.  cache_flush(0x00104008, 0x80) ; isb
8.  Reset an 0x07000400:
        w = readl(0x07000400) & ~1 ; writel(w)      assert
        w = readl(0x07000400) |  1 ; writel(w)      release
        -> "[SCP] :release arisc reset finish"
9.  hwmsgbox init, dann "[SCP] :wait arisc ready...."
```

| | |
|---|---|
| Ladeadresse | **`0x00100000`** |
| in SRAM | **`0x23000` = 140 KiB** |
| Rest | **32 KiB bei `0x48100000` im DRAM** |
| Parameterblock | 128 B nach `0x00104008`, Quelle `0x48000030` |
| Reset | **`0x07000400` Bit 0** (R_CPUCFG) |

Das Image wird also **geteilt**. `0x07000400` ist unabhängig bestätigt: unser
eigenes TF-A definiert `SUNXI_R_CPUCFG_BASE 0x07000400`.

### Der SRAM ist frei — es gibt keine Kollision

Der H713-TF-A-Port definiert:

```
SUNXI_SRAM_A1_BASE  0x00100000   (16 KiB)
SUNXI_SRAM_A2_BASE  0x00104000   (128 KiB)
```

Und `platform.mk` setzt **`SUNXI_BL31_IN_DRAM := 1`**, womit
`BL31_BASE = SUNXI_DRAM_BASE = 0x40000000` gilt (bestätigt durch `/proc/iomem`
`40000000-400fffff : reserved` und den DT-Knoten `secure-bl31@40000000`).

Damit ist `0x00100000 .. 0x00124000` zur Laufzeit ungenutzt; das `eGON.BT0` bei
`0x00104000` sind tote SPL-Reste. Die 140 KiB enden bei `0x00123000` und passen
**exakt** hinein.

### Zwei Korrekturen an cstengers Einschätzung

Seine `docs/arisc-route-scope.md` führt zwei Punkte, die sich damit auflösen:

1. *„The vendor blob is 172 KB and does not fit in TF-A's 16 KiB SCP slot / in
   128 KB SRAM A2."* — Der Vendor lädt bei `0x00100000` (nicht `0x104000`) und
   nur **140** KiB in SRAM; der Rest bleibt im DRAM. Kein Widerspruch.
2. *„Loading vendor ARISC firmware puts a second power manager on the system,
   and TF-A would then detect SCPI and switch to it."* — Bei uns nicht:
   `platform.mk` hat `SUNXI_PSCI_USE_SCPI := 0` **und** einen `$(error)`-Riegel.
   Die Erkennung ist nicht einkompiliert.

Seine Magic-Suche ab `0x00104000` konnte den geladenen Anfang bei `0x00100000`
zudem gar nicht sehen.

## Byte-Ordnung: der Wortswap muss der Lader machen

Der Blob liegt im Paket **wortweise byte-gespiegelt**. Das Speicherabbild ist
die *entspiegelte* Form — statistisch entschieden, nicht geraten:

| | roh (wie gespeichert) | wortweise gespiegelt |
|---|---|---|
| `l.nop` (`0x15000000`), wortausgerichtet | 3 | **445** |
| haeufigste Opcodes `[31:26]` | `0x00`: 7775 (Rauschen) | `0x27` l.addi 2625, `0x2a` l.ori 2492, `0x21` l.lwz 1799, `0x35` l.sw 1779, `0x06` l.movhi 1335 |
| Wort bei `0x100` (Reset-Vektor) | `0x864a0000` = `l.lwz` | **`0x00004a86` = `l.j`** |

Die gespiegelte Form ist Lehrbuch-OR1K; die rohe ist Unsinn. Der Sprung bei
`0x100` zielt auf `0x100 + 0x4a86*4 = 0x12b18`, also innerhalb des Images.

**Wer macht den Swap?** Nicht der BL31: seine Kopierroutine bei `0xa0d4` ist ein
byteweiser `ldrb`/`strb`-Loop, kopiert also unveraendert. Also **boot0**, beim
Auspacken des Paket-Items ins DRAM.

Fuer eine eigene Portierung heisst das: **der Lader muss den 32-Bit-Wortswap
selbst durchfuehren.** Ohne ihn fuehrt die ARISC Rauschen aus, und zwar
lautlos — es gibt keine Fehlermeldung, die das anzeigen wuerde.

## Der Parameterblock

Der Blob traegt bei `0x4008` einen **genullten Platzhalter** von 128 Byte, den
der Vendor zur Laufzeit aus `0x48000030` ueberschreibt. Davor, bei `0x4000`,
steht ein Kopf, den er *nicht* anfasst: `0x00000003` und der u32 `0x73555043`
(roh gelesen als ASCII `"CPUs"`).

Der Inhalt des Parameterblocks ist damit **noch offen**. Was wir wissen:

- Er ist im ausgelieferten Image null, die Firmware muss also mit
  wohldefinierten Vorgaben umgehen koennen (oder der Vendor fuellt ihn immer).
- Er liegt firmware-intern bei Offset `0x4008`, also unmittelbar hinter dem
  Kopf bei `0x4000`.
- Die Vendor-Quelle `0x48000030` liegt in einem DRAM-Bereich, den boot0
  aufsetzt, nicht im BL31-Image selbst.

Naechster Schritt dafuer: die Leser von Offset `0x4008` in der Firmware
disassemblieren, oder den Bereich in einem Stock-Speicherabbild suchen. Fuer
sunxi-Plattformen existiert der `arisc_para`-Aufbau auch in
Vendor-Kernelquellen auf GitHub -- das ist der billigere Weg.

### Was noch offen ist

| Punkt | Stand |
|---|---|
| **Parameterblock** | 128 B, Vendor-Quelle `0x48000030`. Inhalt unbekannt — muss aus BL31 oder Stock-Abbild rekonstruiert werden. |
| **DRAM-Rest** | 32 KiB bei `0x48100000`; liegt bei uns in System-RAM, braucht eine DT-Reservierung wie `mips-firmware` und `cpu-comm`. |
| **Schreibzugriff** | Ob `/dev/mem` nach `0x00100000` und `0x07000400` schreiben darf, ist ungeprüft. Lesen geht (gemessen). |
| **Verhalten der laufenden ARISC** | Ungeprüft. Sie besitzt Energieverwaltungs-Hardware; dass TF-A kein SCPI spricht, heißt nicht, dass sie nichts tut. |

## Nebenbefund: `GIC_SPI 46` steht in der Herstellerquelle

Aus dem `dtb`-Item desselben Pakets:

```
msgbox@3003000  compatible "sunxi,msgbox-amp"
  reg        0x03003000+0x400, 0x03003400+0x400, 0x03003800+0x400
  interrupts GIC_SPI 46, 109, 108
  rpmsg_id   "sunxi,mips-msgbox", "sunxi,cpus-msgbox"
```

Damit ist unsere DTS-Korrektur gegen cstengers `GIC_SPI 21` **aus der
Vendor-Quelle belegt**, nicht nur gemessen (siehe
[66-cpu-comm-arm64-bringup.md](66-cpu-comm-arm64-bringup.md), Fehler 4).

Die drei `0x400`-Blöcke bestätigen außerdem `user1 @0x03003400` als ARISC-Pfad,
wie in `re/notes/arisc-firmware.md` (MSG_DATA `0x0300347c`, TX_IRQ_EN
`0x03003430`).

## Korrekturen an `tools/uboot-hdmi-sequence.txt`

Die Datei warnte selbst, ihre Argumente seien nach der ABI-Korrektur ungeprüft.
Gegen `legacy/userspace/hy310-hdmird` (libhaldisplay-RE + Stock-elog) geprüft:

| Aufruf | stand da | richtig |
|---|---|---|
| `671ceca6` RegisterSignalChangeCallback | `b 3e7fbc46` | `b` — ParaCount 1, die Callback-ID ist **kein** Argument |
| `ba3e5a70` SetHDMIHotPlugByPortCallback | `38d780e2` | `1` — Enable-Flag |
| `9ce74c48` SetPortMap ×3 | `3 0` / `4 0` / `5 0` | `1 0` / `2 1` / `3 2` — (port, port_map) |

Außerdem fehlen der Datei `THal_Vp_Init(0,0,0x4E700000)` ganz vorn und
`Wce_SetWindow` (drei Shmem-Zeiger) — letzteres trägt im hdmird-Quelltext den
Vermerk *„SKIPPING THIS WAS THE LVDS-ROUTING BLOCKER through Z-session"*.

## Dateien

| Pfad | Inhalt |
|---|---|
| `analyse/hdcp-keys/` | `hdcp22-key-912.bin`, `hdcp14-key-320.bin`, Hashes, `snum.bin` |
| `analyse/arisc/scp-wordswapped.bin` | ARISC-Firmware, OR1K-lesbar |
| `analyse/arisc/monitor.bin` / `.asm` | Vendor-BL31 und sein Disassemblat |
| `analyse/arisc/dtb.bin` | Vendor-Devicetree |
| `analyse/arisc/BEFUND.md` | die Langfassung des ARISC-Teils |

Disassemblieren geht ohne Cross-Binutils:

```bash
llvm-objcopy-18 -I binary -O elf64-littleaarch64 \
  --rename-section .data=.text,code monitor.bin monitor.elf
llvm-objdump-18 -d --no-show-raw-insn monitor.elf > monitor.asm
```

## boot0: der zweite Teil der ARISC-Inbetriebnahme

Die Inbetriebnahme ist **auf boot0 und BL31 verteilt**. Fuer eine Portierung
muessen beide Teile nachgebaut werden, nicht nur der BL31-Teil.

**boot0 laeuft bei `0x00104000` und ist Thumb**, nicht ARM. Belegt: das Literal
bei Dateioffset `0x1154` haelt `0x00109EAA` (= die Zeichenkette
`"prcm cpus timer clock enable"`), und genau ein Befehl laedt es —
`ldr r0, [pc, #44]` bei `0x1124`, ein Thumb-T1-Literal-Load. In ARM32 gibt es
keinen passenden Zugriff.

Der Takt-Teil, Datei `0x10d8`..`0x1132`:

```
r2 = 0x07010110                (Literal-Pool 0x1150)
*0x07010110 |= 1
r2 += 4  ->  *0x07010114 |= 1
r2 += 4  ->  *0x07010118 |= 1
printf("prcm cpus timer clock enable")
printf("board init ok")
```

Das `bic #1` vor jedem `orr #1` ist toter Vendor-Code (der Zwischenwert geht
ueber den Stack und wird nie geschrieben) — **netto wird Bit 0 gesetzt**, in drei
aufeinanderfolgenden R_PRCM-Registern.

Weitere Literale derselben Funktion: `0x07090160`, `0x07010340`.

boot0 traegt ausserdem die Zeichenkette `"set arisc reset to de-assert state"`
(Dateioffset `0x5ed7`) — dieselbe Meldung wie im BL31. Ihr Verweis ist noch
nicht aufgeloest (kein direktes Literal auf `0x00109ED7`, vermutlich Basis +
Offset).

### Werkzeug

`tools/or1k-disasm.py` — OpenRISC-Dekoder, weil **weder IDA 9.1 noch Capstone
5.0.7 OR1K koennen** (IDA `procs/` hat kein or1k/openrisc, `CS_ARCH_*` auch
nicht). Selbstvalidierend: `dis 0x100` liefert `l.j 0x12b18`, und dort steht
`l.movhi r1..r16, 0` — das kanonische OR1K-Reset-Stueck.

```bash
tools/or1k-disasm.py analyse/arisc/scp-wordswapped.bin dis 0x12b18 0x40
tools/or1k-disasm.py analyse/arisc/scp-wordswapped.bin refs 0x4008 0x4088
```

### Parameterblock: noch nicht geklaert

Gesucht wurde ueber den Dekoder. Ergebnis:

- **Keine** `r0`-relativen Zugriffe auf `0x4000..0x4100`.
- Zwei `l.ori r3, r3, 0x4008` liegen in Delay-Slots von `l.jal` (`0xe198` ->
  `0x142dc`, `0xe744` -> `0x145b0`), `r3` ist also das erste Argument.
- **Aber** `0x142dc` ueberschreibt `r3` sofort und benutzt das Argument nicht.
  `0x145b0` ist ein Thunk (`r4 = r3`, `r3 = 0`, Sprung nach `0x14004`), und
  direkt dahinter stehen Zeichenketten wie `"WRN:cpu%d power switch enable
  already"` — die Umgebung ist CPU-Power-Switch, nicht offensichtlich der
  Parameterblock.

Wer die 128 Byte tatsaechlich liest, ist damit **offen**. Naechster Ansatz:
boot0 weiter aufarbeiten (wer fuellt `0x48000000`), oder den `l.jal`-Graphen um
`0x14004` verfolgen.

## KORREKTUR (04.09., nach linux-sunxi.org/AR100): niemand swappt

Der Abschnitt „Byte-Ordnung: der Wortswap muss der Lader machen" oben ist in
seiner Schlussfolgerung **falsch**. Richtig ist:

Die AR100 ist big-endian, **aber ihr Datenbus dreht jedes 32-Bit-Wort**. Aus dem
Wiki (linux-sunxi.org/AR100, Abschnitt „Byte swapping/endianness"):

> *„if the instructions are stored in SRAM as-is, they will be read by the CPU as
> little-endian, and they will not run. To solve this, the instructions must be
> reversed before writing them to SRAM; they will be un-reversed when read by the
> AR100."*
> ```
> ${CROSS_COMPILE}objcopy -O binary --reverse-bytes 4 firmware.elf firmware.bin
> ```

Das Paket enthaelt also **bereits die Form, die ins SRAM gehoert**. Der byteweise
`memcpy` im Vendor-BL31 ist genau richtig; boot0 swappt nichts.

**Fuer eine Portierung: den Blob unveraendert kopieren.** Ein zusaetzlicher Swap
im Lader wuerde die Firmware lautlos zerstoeren.

Was weiterhin stimmt: die *logische* Instruktionsfolge ist die entspiegelte Form,
und `tools/or1k-disasm.py` braucht sie so (`scp-wordswapped.bin`). Die Statistik
(445 wortausgerichtete `l.nop`, Reset-Vektor `l.j 0x12b18`) war korrekt — nur die
Folgerung „also muss jemand swappen" war es nicht.

Das erklaert nebenbei auch die Zeichenkette bei `0x4004`: das Wiki zeigt, dass
ASCII zwischen ARM und AR100 verdreht erscheint. `"CPUs"` in Dateireihenfolge ist
das, was **ARM** liest; die AR100 sieht `"sUPC"`.

## Die Adresskarte, aus dem Wiki abgeleitet

Das Wiki gibt fuer A31/H3/A64/H5 die Zuordnung AR100-Adressraum <-> ARM-Adressraum.
Auf unsere gemessenen Ladeadressen angewandt:

| AR100 | ARM (bei uns) | Groesse | Bedeutung |
|---|---|---|---|
| `0x00000000`-`0x00001fff` | `0x00100000`-`0x00101fff` | 8 KiB | **Exception-Vektoren** — nur *ein* schreibbares Wort je `0x100`-Grenze |
| `0x00002000`-`0x00003fff` | `0x00102000`-`0x00103fff` | 8 KiB | reserviert |
| `0x00004000`-… | `0x00104000`-… | | **SRAM A2**, hier liegt der Firmware-Rumpf |

Also: **AR100-Adresse = ARM-Adresse − `0x100000`.**

Das erklaert mehrere Beobachtungen auf einen Schlag:

- Der Reset-Vektor liegt bei Bild-Offset `0x100` = AR100 `0x100` — genau die
  Reset-Exception-Adresse. Dahinter Nullen, weil je `0x100`-Grenze nur ein Wort
  schreibbar ist.
- Der Vendor kopiert **140 KiB ab ARM `0x00100000`** am Stueck, also Vektorbereich
  *und* Rumpf; im Vektorbereich verwirft die Hardware das meiste folgenlos.
- Der Parameterblock landet auf ARM `0x00104008` = AR100 `0x4008` = **8 Byte
  hinter dem SRAM-A2-Anfang**, direkt hinter dem Kopf bei `0x4000`.

crusts `tools/load.c` bestaetigt die Prozedur unabhaengig: Reset anlegen
(`mmio_clr_32(r_cpucfg, BIT(0))`), Exception-Vektoren schreiben, Firmware nach
`FIRMWARE_BASE` kopieren, syncen, Reset loesen (`mmio_set_32(r_cpucfg, BIT(0))`) —
dasselbe Bit 0 in R_CPUCFG, das wir im Vendor-BL31 bei `0x07000400` gefunden haben.

## Wo die offene Frage jetzt am billigsten zu klaeren ist

Das Wiki nennt drei Clients, die alle Lade- und Startcode haben:
*„The API is used by Linux (`drivers/arisc`), U-Boot, and ATF. All three clients
have code for loading and starting the firmware blob."* Und: die API-Definitionen
stehen im ATF-Quelltext unter `plat/sun50iw2p1/include/arisc.h`.

**Der Parameterblock ist damit wahrscheinlich aus Vendor-Quelltext zu holen statt
aus dem Blob** — `drivers/arisc` in einem BSP-Kernelbaum (z. B. tinalinux
linux-3.10) oder `arisc.h` im ATF-Baum.

## GEKLAERT: der Parameterblock ist `struct arisc_para`

Aus dem Vendor-Linux-Treiber (`allwinner-zh/linux-3.4-sunxi`,
`drivers/arisc/include/arisc_para.h`):

```c
typedef struct arisc_para
{
	unsigned int machine;
	unsigned int oz_scale_delay;
	unsigned int oz_onoff_delay;
	unsigned int message_pool_phys;     /* <-- fuer uns das Wichtige */
	unsigned int message_pool_size;     /* <-- dito */
	unsigned int uart_pin_used;
	unsigned int services_used;
	unsigned int power_regu_tree[VCC_MAX_INDEX];
	unsigned int reseved[10];
} arisc_para_t;
```

`ARISC_PARA_SIZE` ist als **128 Byte** dokumentiert. Die Rechnung geht auf:
7 u32 + `VCC_MAX_INDEX`*4 + 10 u32 = 128 => **`VCC_MAX_INDEX` = 15**.

Und derselbe Treiber zeigt Laden und Start:

```c
memcpy((void *)arisc_sram_a2_vbase, image, image_size);
dest = (void *)(arisc_sram_a2_vbase + ARISC_PARA_ADDR_OFFSET);
memcpy(dest, (void *)para, ARISC_PARA_SIZE);
...
value = readl(R_CPUCFG + 0x0); value &= ~1; writel(value, ...);   /* assert  */
value = readl(R_CPUCFG + 0x0); value |=  1; writel(value, ...);   /* release */
```

### Dreifach gegengeprueft

1. **Groesse**: 128 Byte = die `0x80`, die der Vendor-BL31 kopiert.
2. **Offset**: der Treiber schreibt nach `sram_a2_vbase + ARISC_PARA_ADDR_OFFSET`;
   der BL31 schreibt nach ARM `0x00104008` bei Bildbasis `0x00100000`, also
   **`ARISC_PARA_ADDR_OFFSET = 0x4008`**.
3. **Reset**: das Clear-dann-Set von Bit 0 an `R_CPUCFG + 0` ist Instruktion fuer
   Instruktion das, was wir im BL31 bei `0x07000400` disassembliert haben — und
   was crusts `tools/load.c` unabhaengig genauso macht
   (`mmio_clr_32(r_cpucfg, BIT(0))` / `mmio_set_32(r_cpucfg, BIT(0))`).

**Meine frueher geaeusserte Vermutung, es seien DRAM-Parameter, war falsch.**
Es ist ein Konfigurationsblock. Fuer den HPD-Weg zaehlen vor allem
`message_pool_phys` und `message_pool_size` — das ist der geteilte Speicher, ueber
den die BOP-Frames laufen (`PullHotPlug 0x0211` aus `re/notes/edid-protocol.md`).

### Was damit fuer eine Portierung feststeht

| Schritt | Wert |
|---|---|
| Blob **unveraendert** kopieren nach | ARM `0x00100000` |
| Umfang | `0x23000` (140 KiB); die restlichen 32 KiB bleiben im DRAM |
| `struct arisc_para` (128 B) schreiben nach | ARM `0x00104008` |
| Cache flushen, `isb` | ueber beide Bereiche |
| Reset | `0x07000400` Bit 0: loeschen, dann setzen |
| danach | Msgbox initialisieren, auf „arisc ready" warten |
| zusaetzlich (boot0-Teil) | Bit 0 setzen in `0x07010110`, `0x07010114`, `0x07010118` |

Offen bleiben nur noch die **Werte** der Felder — `machine`, `services_used`,
`power_regu_tree` — und wo wir den Message-Pool hinlegen. Letzteres bestimmen wir
selbst (DT-Reservierung), Ersteres steht in der BSP oder faellt beim Ausprobieren
mit Nullen auf.

### Quellen

- linux-sunxi.org/AR100 — Byte-Swapping, Adresskarte, Toolchain
- `allwinner-zh/linux-3.4-sunxi`, `drivers/arisc/` — Lader, Reset, `arisc_para`
- `crust-firmware/crust`, `tools/load.c` — unabhaengige Bestaetigung der Reset-Prozedur
- `smaeul/sunxi-blobs` — RE-Werkzeuge fuer ARISC-Blobs (or1k-Toolchain noetig)

### EINSCHRAENKUNG zum Feldlayout (04.09., am Blob geprueft)

Der Abschnitt oben sagt „GEKLAERT". Das gilt fuer **Groesse und Ort** — 128 Byte
bei AR100 `0x4008` —, **nicht** zwingend fuer die Feldreihenfolge.

Die Firmware liest den Block nachweislich: `0x145b0` ist ein Thunk, der mit
`r4 = 0x4008` nach `0x14004` springt, und dort steht

```
014014  l.ori   r2, r4, 0x0000      r2 = Zeiger auf den Parameterblock
014034  l.lwz   r3, 92(r2)          *(para + 0x5c)
014038  l.movhi r4, 0x0001          0x00010000  -> Bit 16
01403c  l.and   r3, r3, r4
014040  l.sfeqi r3, 0x0000
```

Getestet wird also **Bit 16 von `para + 0x5c`**. In der `struct arisc_para` aus
dem linux-3.4-BSP waere Offset `0x5c` = 92 das Feld `reseved[1]` — ein
Reserve-Feld auf ein Bit zu pruefen ergibt keinen Sinn. (Offset `0x4c` = 76 waere
`power_regu_tree[12]`, ebenso unplausibel.)

**Schluss: das Feldlayout der H713-Firmware weicht vermutlich von der
linux-3.4-Struktur ab.** Diese stammt aus einem BSP von ~2014; unsere Firmware
ist deutlich juenger. Groesse (128) und Offset (`0x4008`) sind dreifach belegt und
bleiben gueltig — die *Bedeutung der einzelnen Woerter* ist es nicht.

Wer Werte einsetzt, sollte das wissen. Der sichere Weg ist, mit Nullen zu starten
und die Leser des Blocks in der Firmware einzeln aufzuarbeiten
(`tools/or1k-disasm.py`, Einstieg `0x14004`).

### Nebenbefund: der DRAM-Anteil ist komplett null

Die 32 KiB ab Blob-Offset `0x23000`, die der Vendor nach `0x48100000` schiebt,
sind **32772 Byte Nullen** — nachgezaehlt. Und die Firmware enthaelt **keinen
einzigen** `l.movhi` mit Immediate `0x4810`/`0x8810`/`0x4812`, referenziert diesen
DRAM-Bereich statisch also nirgends.

Fuer einen ersten Ladeversuch heisst das: **der DRAM-Anteil kann entfallen.** Er
schreibt nur Nullen an eine Stelle, die die Firmware statisch nicht anfasst. Das
nimmt auch die DT-Reservierung aus dem kritischen Pfad — sie waere nur noetig,
wenn sich zeigt, dass die Firmware den Bereich zur Laufzeit dynamisch benutzt.

## GEMESSEN 04.09.: /dev/mem darf schreiben — der Lader kann im Userspace bleiben

Der Kernel hat `CONFIG_STRICT_DEVMEM=y`, aber **nicht** `CONFIG_IO_STRICT_DEVMEM`.
Auf arm64 heisst das: System-RAM gesperrt, Nicht-RAM erlaubt. Das SRAM bei
`0x00100000` taucht in `/proc/iomem` nicht auf, ist also kein System-RAM.

Am Geraet bestaetigt:

```
SRAM 0x00110000  0x8462FFDA -> schreibe 0xA5A5A5A5 -> zurueckgelesen 0xA5A5A5A5
                 -> Originalwert wiederhergestellt und verifiziert
MMIO 0x07010110  idempotenter Rueckschreibvorgang ohne Fehler
```

Testadresse bewusst gewaehlt: `0x00110000` liegt in SRAM A2 hinter dem toten
SPL (`eGON.BT0` bei `0x00104000`, 32 KiB) und weit vor `0x00123E00`, wo TF-A bei
aktivem SCPI seine Mailbox haette (`PLAT_CSS_SCP_COM_SHARED_MEM_BASE`) — bei uns
ist SCPI gar nicht gebaut.

**Folge: die ARISC-Inbetriebnahme braucht keinen Eingriff in die Boot-Kette.**
Ein Fehlversuch kostet einen Neustart, keine FEL-Rettung.

Ausserdem gemessen, direkt aus Linux:

| | |
|---|---|
| `R_CPUCFG 0x07000400` | `0x00000000` — Bit 0 geloescht, **ARISC steht im Reset** |
| `R_PRCM 0x07010110` | `0x00000001` — Bit 0 schon gesetzt, der boot0-Taktschritt ist bereits erledigt |

## Nachtrag: TF-A kennt OR1K bereits

`plat/allwinner/common/sunxi_scpi_pm.c` (bei uns nicht gebaut, `SUNXI_PSCI_USE_SCPI := 0`):

```c
#define SCP_FIRMWARE_MAGIC   0xb4400012
#define OR1K_VEC_ADDR(n)     (0x100 * (n))
...
for (i = OR1K_VEC_FIRST; i <= OR1K_VEC_LAST; ++i) {
    uint32_t vector = SUNXI_SRAM_A2_BASE + OR1K_VEC_ADDR(i);
    uint32_t offset = SUNXI_SCP_BASE - vector;
    mmio_write_32(vector, offset >> 2);        /* das IST ein l.j */
}
mmio_setbits_32(SUNXI_R_CPUCFG_BASE, BIT(0));  /* Reset loesen */
```

Drei Klarstellungen daraus:

1. **Warum `0xb4400012` im Vendor-Blob fehlt:** TF-A erwartet ein crust-artiges
   Image am **Ende** von SRAM A2 und schreibt selbst Sprungvektoren dorthin. Der
   Vendor legt sein Image an den **Anfang**, mit eigenen Vektoren im Bild. Zwei
   verschiedene Lademodelle. `re/notes/arisc-firmware.md` nennt das TF-A-Magic,
   nicht das des Vendor-Blobs.
2. **`mmio_write_32(vector, offset >> 2)` ist ein `l.j`** — Opcode 0, das rohe Wort
   ist genau `offset>>2`. Gegenprobe: Ziel `0x12b18`, Vektor `0x100`, also
   `(0x12b18 - 0x100) >> 2 = 0x4A86`; im Blob steht bei `0x100` exakt `0x00004a86`.
3. **Wir muessen keine Vektoren schreiben** — der Vendor-Blob bringt seine eigenen
   mit, korrekt fuer Ladeadresse `0x00100000`.

## 04.09.2026: die ARISC laeuft — aus dem Linux-Userspace

Werkzeug `analyse/arisc-loader/arisc_load.py`, Blob `analyse/arisc/scp.bin`.
Kein Eingriff in die Boot-Kette, kein TF-A-Umbau, keine DT-Aenderung.

```
scp arisc_load.py scp.bin root@<board>:/root/
python3 /root/arisc_load.py probe  --blob /root/scp.bin
python3 /root/arisc_load.py load   --blob /root/scp.bin --skip-tail --hold-reset --i-mean-it
python3 /root/arisc_load.py reset  --release-only --i-mean-it
```

### Der Ladevorgang verifiziert sich selbst

```
Rumpf    0x00104000..0x00123000 :  0 von 31744 Woertern weichen ab
Vektoren 0x00100000..0x00102000 :  0 Abweichungen auf den 0x100-Grenzen,
                                  18 dazwischen
Parameterblock                  :  0 von 32 Woertern weichen ab
```

Die 18 Abweichungen im Vektorbereich sind **die Bestaetigung, nicht der Fehler**:
die Hardware nimmt dort nur *ein* Wort je `0x100`-Grenze an, genau wie das
AR100-Wiki sagt — und alle Grenzen selbst haben gepasst.

### Der Nachweis, dass sie ausfuehrt

Nach dem Laden waren BSS und Stack **vollstaendig null** (Teil des Bildes).
Nach `reset --release-only`:

| | nach dem Laden | nach dem Loslassen |
|---|---|---|
| BSS `0x115f38..0x1175b0` | 0 von 1438 | **59** von 1438 |
| Stack `0x1175b0..0x1179b0` | 0 von 256 | **35** von 256 |

Der ARM hat dazwischen ausschliesslich gelesen. Ein Vollabgleich des SRAM gegen
das geladene Bild zeigt **102 von der ARISC geschriebene Woerter** (die zwei
weiteren Treffer bei `0x4014`/`0x4018` sind unser eigener Parameterblock), und
sie sind strukturiert:

```
0x16f30 -> 0x07021000    MMIO-Basisadressen aus dem R_-Block
0x16f38 -> 0x07020400
0x15f3c -> 0x00016b84    Zeiger auf eigene BSS-Adressen -> Listenverkettung
0x15f50 -> 0x00016b78
0x16f54..0x170a8         langer Lauf, 8-Byte-Schrittweite -> Array-Init (~50)
0x17880..0x1799c         echter Stackinhalt
```

MMIO-Basen ablegen, verkettete Listen aufbauen, eine Struktur-Tabelle
initialisieren — das ist Treiber-Initialisierung, kein Rauschen.

### Wo sie stehenbleibt

Drei Stichproben im Abstand von 3 s: BSS 59, Stack 35, **unveraendert**. Der
Stack-Boden bewegt sich nicht. Die Firmware laeuft also an, initialisiert einen
substanziellen Teil und erreicht dann einen stabilen Ruhezustand.

Die Msgbox-Register bei `user1 sub0` (`0x0300346c`, `0x03003424`, `0x03003420`,
`0x0300347c`, `0x03003430`) stehen **alle auf null** — ihre Empfangsseite hat sie
nicht geoeffnet. Ob sie wartet, haengt oder unvollstaendig konfiguriert ist, ist
damit **nicht** entschieden.

Das Board bleibt durchgehend gesund: MIPS lebt, uptime laeuft, kein Absturz,
keine Auffaelligkeit im dmesg.

### Was das beweist und was nicht

**Bewiesen:** der Blob ist echt und in der richtigen Form; Ladeadresse, Groesse,
Vektorlage und Reset-Register stimmen; die Firmware fuehrt aus; und der ganze
Vorgang ist aus dem Userspace machbar und per Neustart rueckgaengig.

**Nicht bewiesen:** dass sie *korrekt* laeuft. Der Parameterblock ist mit Nullen
plus geratenem Pool (`0x00123000`/`0x1000`) belegt, und das Feldlayout ist
unsicher (siehe „EINSCHRAENKUNG zum Feldlayout"). Eine Firmware, die einmal
initialisiert und dann haengt, saehe genauso aus wie eine, die korrekt auf eine
Nachricht wartet.

### Naechste Ansaetze

1. **Die 102 geschriebenen Woerter gegen die Firmware halten** — welcher Code
   schreibt `0x16f54..0x170a8`? Damit laesst sich bestimmen, wie weit die Init
   kam und woran sie haengt (`tools/or1k-disasm.py`).
2. **`arisc_para` variieren** — vor allem das Feld, dessen Bit 16 bei `0x14004`
   geprueft wird, und `uart_pin_used` (die ARISC hat eine eigene UART an R_UART
   `0x07080000`; laeuft sie, koennte sie sprechen).
3. **Den Msgbox-Pfad pruefen** — ob die ARISC einen anderen Block als `user1
   sub0` benutzt.

## Was die laufende ARISC tatsaechlich getan hat

Statische Analyse der 102 geschriebenen Woerter (`tools/or1k-disasm.py`) plus
Ruecklesen der Tabelle vom Board.

### Sie hat ihren Interrupt-Controller aufgesetzt

Bei AR100 `0x16f30` liegt eine Tabelle, die die Firmware selbst gefuellt hat:

```
0x16f30:  07021000       R_INTC-Basis
0x16f38:  07020400       zweite MMIO-Basis
--- ab 0x16f40: {arg, handler}, je 8 Byte ---
IRQ 0:    00000000  00005f30     Default
IRQ 1:    00000000  00005f30     Default
IRQ 2:    00000000  00006698     ECHTER Handler
IRQ 3:    00015ba8  00010af0     ECHTER Handler, mit Kontext
IRQ 4..:  00000000  00005f30     alle Default
```

Zwei Handler registriert, der Rest auf dem Default. Das ist kein Absturz — die
Firmware hat ihre Interrupt-Verwaltung fertig aufgebaut und **wartet**.

Der IRQ-2-Handler prueft als Erstes ein Flag bei `0x15b8c` und ueberspringt bei
null; genau dieses Wort hat die ARISC beim Init von `1` auf `0` gesetzt.

### Beide Handler arbeiten im Block, der den ARM haengt

```
IRQ-2 @0x6698:  l.movhi r18, 0x0709 ; l.ori r18, r18, 0x0404 ; l.lwz r3, 0(r18)
IRQ-3-Pfad:     l.movhi r2,  0x0709 ; l.ori r2,  r2,  0x0448 ; l.lwz r5, 0(r2)
```

`0x07090404` und `0x07090448` liegen im selben Block wie `0x07091014`.

**Zaehlung ueber die ganze Firmware:** 42 Stellen bilden Adressen in
`0x07090xxx`, **27 in `0x07091xxx`** — darunter `0x07091014` selbst, dazu
`0x07091008/18/1c/20/30/34/38` und eine Reihe bei `0x07091b00..0x07091f00`.

Damit ist von **beiden** Seiten belegt, was bisher Hypothese war: dieser Block
antwortet der ARISC, nicht dem ARM. cstengers Schluss („`0x07091000` ist nicht
ARM-adressierbar") ist damit unabhaengig bestaetigt — und die Loesung ist nicht,
ihn doch vom ARM zu erreichen, sondern die ARISC zu benutzen.

### Der Msgbox-Pfad ist der aus unserer eigenen RE

Adressen, die die Firmware im Msgbox-Block bildet:

```
0x0300347c   MSG_DATA    user1 sub0 port3    ARM  -> ARISC
0x0300346c   FIFO_STAT   user1 sub0 port3
0x03003424   RX_IRQ_ST   user1 sub0
0x0300307c / 0x03003087                      ARISC -> ARM (user0)
```

Deckungsgleich mit `re/notes/arisc-firmware.md` (Session O, device-verified:
MSG_DATA `0x0300347c`, TX_IRQ_EN `0x03003430`). Die Register lesen null, weil
ihnen noch niemand etwas geschickt hat — nicht, weil der Pfad falsch waere.

### Damit ist der Weg zu HPD benannt

Die Kette ist vollstaendig sichtbar:

```
ARM  --(msgbox user1 sub0 port3, MSG_DATA 0x0300347c + TX_IRQ_EN-Puls)-->
ARISC  --(BOP-Frame, PullHotPlug 0x0211)-->  schreibt 0x07091014
```

Was fehlt, ist der erste Pfeil: ein BOP-Frame in die Msgbox. Das Protokoll steht
in `re/notes/EDID-PROTOCOL.md` (Marker `0xA5`, rotierende Sequenznummer, Typ,
Laenge, dann `sub_cmd_lo/hi, arg1, arg2, data`), und `PullHotPlug` ist
`sub_cmd 0x0211` mit `arg1 = port`, `arg2 = active?`.

**Vorbehalt:** dass die Firmware laeuft und ihre Handler registriert hat, heisst
nicht, dass sie auf eine Nachricht korrekt reagiert. Der Parameterblock ist mit
Nullen plus geratenem Pool belegt, und `message_pool_phys` koennte genau das Feld
sein, das die Msgbox-Bearbeitung braucht.

## Das ARM<->ARISC-Nachrichtenprotokoll, aus dem Vendor-Treiber

Quelle: `allwinner-zh/linux-3.4-sunxi`, `drivers/arisc/`. Kopien der relevanten
Dateien liegen in `analyse/arisc/vendor-driver/`.

**Im Stock verarbeitet das ein Kernel-Treiber, kein Userland-Daemon.** Aufbau:

```
drivers/arisc/
  hwmsgbox/          Transport ueber die Msgbox
  message_manager/   Ein-/Auslieferung, Pool-Verwaltung
  hwspinlock/        Synchronisation
  interfaces/        die API nach oben (arisc_dvfs.c usw.)
```

Userspace (libhalhdmi & Co.) redet mit diesem Treiber, nicht mit der Msgbox.
**Bei uns fehlt er** — deshalb stapeln sich Nachrichten der ARISC ungelesen.

### Die Nachricht

`drivers/arisc/include/arisc_messages.h`, 64 Byte:

```c
typedef struct arisc_message {
    volatile unsigned char  state;       /* +0x00  2=INIT 4=PROCESSING
                                                   5=PROCESSED 6=FEEDBACKED */
    volatile unsigned char  attr;        /* +0x01  SYN / ASYN */
    volatile unsigned char  type;        /* +0x02  ARISC_MESSAGE_BASE(0x10)+n */
    volatile unsigned char  result;      /* +0x03 */
    volatile struct arisc_message *next; /* +0x04 */
    volatile struct arisc_msg_cb   cb;   /* +0x08 */
    volatile void          *private;     /* +0x10 */
    volatile unsigned int   paras[11];   /* +0x14..+0x3f */
} arisc_message_t;
```

### Was ueber die Msgbox geht: ein POOL-OFFSET

`message_manager.c`:

```c
u32 arisc_message_map_to_cpus(struct arisc_message *message)
{
    return (u32)message - arisc_message_pool_base;
}
struct arisc_message *arisc_message_map_to_cpux(u32 addr)
{
    return (struct arisc_message *)(addr + arisc_message_pool_base);
}
```

`hwmsgbox.c`:

```c
value = arisc_message_map_to_cpus(pmessage);
writel(value, IO_ADDRESS(AW_MSGBOX_MSG_REG(...)));
```

**Die Msgbox traegt einen Offset in den Message-Pool**, nicht die Nachricht und
nicht eine absolute Adresse. Der Ablauf ist:

```
1. arisc_message_allocate()   Rahmen aus dem Pool im geteilten Speicher holen
2. Felder fuellen (type, attr, paras[])
3. writel(offset_in_pool, MSG_DATA)
4. Doorbell
5. Gegenseite: map_to_cpux(offset) -> Zeiger -> bearbeiten -> state = FEEDBACKED
```

### Folge fuer uns

`message_pool_phys` im Parameterblock ist damit **die Schluesselgroesse**:
`map_to_cpus` subtrahiert die Pool-Basis, `map_to_cpux` addiert sie — ARM und
ARISC muessen sich ueber sie einig sein, und genau dafuer traegt der
Parameterblock das Feld. **Unsere `0x00123000` ist geraten.**

Ein Versuch, einen Rahmen direkt in MSG_DATA zu schreiben, ist auf
Protokollebene falsch (am 04.09. gemacht, siehe unten) — er landet als
sinnloser Offset.

### Der Versuch vom 04.09. und was er trotzdem zeigte

Ein BOP-Rahmen (`a5 01 00 04 | 00 00 00 00 | 11 02 00 01`, PullHotPlug) wurde
wortweise nach `0x0300347c` geschrieben und der Doorbell an `0x03003430`
(BIT(7), Port 3) gepulst. Beobachtet:

| | vorher | nachher |
|---|---|---|
| user1 FIFO `0x0300346c` | 0 | 15 direkt nach dem Schreiben, dann **7** |
| user1 RX_IRQ_ST `0x03003424` | 0 | **0x40** (BIT(6) = Port 3) |
| ARISC-Stack nicht-null | 108 | **115** |
| user0 FIFO `0x0300306c` | **8** *(schon vorher!)* | 8 |
| user0 RX_IRQ_ST `0x03003024` | **0x40** *(schon vorher!)* | 0x40 |

Drei Dinge daraus, unabhaengig vom falschen Rahmenformat:

1. **Die ARISC arbeitet weiter.** Zwischen zwei Messungen im Abstand von ~8 min:
   BSS 59 -> 132, Stack 35 -> 108 nicht-null.
2. **Sie reagiert auf den Doorbell** — der Stack bewegte sich in den 0,5 s danach,
   und acht FIFO-Eintraege wurden verbraucht.
3. **Sie sendet von sich aus.** user0 hatte *vor* unserem Versuch bereits acht
   Eintraege und gesetzten RX-Status. Ausgelesen ergaben sie einen Kopf
   `0x00900200`, ein Laengenfeld `13` und 24 Byte klar druckbares ASCII — das
   sich in keiner der acht geprueften Byteordnungen zu lesbarem Text fuegt
   (`]ejorrotc3vt-a-30ordn11d` und Varianten).

**Diese acht Woerter sind noch nicht gedeutet.** Sie passen weder auf das
Pool-Offset-Modell oben noch auf das BOP-Empfangsformat aus
`re/notes/EDID-PROTOCOL.md` (dort `buf[0]=0xff`, `buf[1]`=Kanalbyte, `0xf8` =
HDMI/EDID). Moeglich ist, dass diese TV-Firmware neben dem generischen
sunxi-Protokoll eine eigene BOP-Schicht fuer die HDMI-Funktionen fuehrt; belegt
ist das nicht.

### Naechste Schritte

1. `arisc_message_manager_init()` lesen — wie leitet die ARM-Seite die Pool-Basis
   ab, und was ist `ARISC_MESSAGE_POOL_START`? Damit waere `message_pool_phys`
   keine Annahme mehr.
2. Erst dann erneut senden, diesmal mit korrektem Pool-Offset statt Rohrahmen.
3. Die acht empfangenen Woerter gegen die Empfangsseite von
   `message_manager.c` halten.

## KORREKTUR + Durchbruch (05.09.): die Firmware benutzt den Pool NICHT

Der Abschnitt oben schliesst: *„`message_pool_phys` im Parameterblock ist damit
**die Schluesselgroesse**"*. Das gilt fuer den **generischen** sunxi-Treiber, aber
**nicht fuer diese Firmware**.

Nachgezaehlt im Bild: **null** Zugriffe auf `para+0x0c` (`message_pool_phys`)
oder `para+0x10` (`message_pool_size`) — weder r0-relativ noch ueber ein
`movhi`/`ori`-Paar. Diese TV-Firmware ueberträgt den **Rahmen selbst als
Wortstrom** durch die Msgbox: Kopf, count, dann `count` Datenwoerter. Der Pool ist
auf ihr ein totes Feld.

Der Pool-Offset-Mechanismus aus `drivers/arisc/message_manager.c` beschreibt also
den generischen Fall, nicht unseren. Beides steht jetzt nebeneinander — nicht
verwechseln.

## Die ARISC sagt, wer sie ist

Die acht Woerter, die sie unaufgefordert schickte, sind **die ersten acht eines
15-Wort-`STARTUP_NOTIFY`**:

```
0x00900200   Kopf: state 0, attr 2 (HARDSYN), type 0x90, result 0
0x0000000d   count = 13
danach       die Versionszeichenkette
```

Entschluesselt:

```
projector-tv303-android11-v1.3-3-g293ff69
```

**Dreifach belegt.** (a) Der Kopf zerlegt sich sauber nach `struct arisc_message`.
(b) Die Zeichenkette steht im Bild bei `0x14d4b` — und in der **Ladeform**
(`scp.bin`) liest dieselbe Stelle `]ejorrotc3vt-a-30ordn11di.1v--3-3392g96ffnes`,
also byteweise genau das, was aus dem FIFO kam. (c) Der Sendecode bei `0xc4a0`
baut diesen Rahmen (type 0x90, count 13) und traegt die Zeichenketten
„feedback startup result" und „ar100 firmware version : %s"; der Vendor-Treiber
liest ihn in `arisc_wait_ready()`.

**Warum nur 8 von 15:** die Sende-Vorpruefung der ARISC (`0x7504`) bricht ab
FIFO-Fuellstand 8 ab, und ARM-seitig las nie jemand.

Damit ist auch die urspruengliche Deutung bestaetigt: der Vendor-BL31 wartet nach
dem Reset-Loesen auf genau diese Nachricht (`[SCP] :wait arisc ready....`,
`[SCP] :arisc version: [%s]`).

### Warum ich sie zunaechst nicht lesen konnte

Ich hatte Byteordnungen auf den **empfangenen Woertern** durchprobiert, statt die
Zeichenkette **im Bild** zu suchen. Zwei Dinge kamen zusammen: der Datenbus der
AR100 dreht jedes Wort, und der String beginnt bei `0x14d4b`, also `3 mod 4` —
keine meiner Wortgrenzen konnte passen. Die Lehre ist die bekannte: **im Material
suchen, nicht am Symptom rechnen.**

## Der ARM<->ARISC-Rundlauf ist device-verified

Ein einzelnes nachgeschobenes Wort vervollstaendigte einen halb gelesenen Rahmen.
Die ARISC verarbeitete ihn, erkannte den Typ nicht und **antwortete**:

```
0xfd000211 0x00000000        result 0xfd = -3 ("unbekannt")
```

Das `0x0211` darin ist das Ueberbleibsel des PullHotPlug-Versuchs vom Vortag. Der
Weg ARM -> ARISC -> ARM steht damit am Geraet.

## Und ein Absturz, mit Lehre

Ein `send` mit vier Woertern plus Doorbell **haengte den SoC**. Der Watchdog hat
neu gestartet, nach 3-4 Minuten war das Board von selbst zurueck — **kein
Stromzyklus noetig**, und die persistente `bootcmd` brachte den MIPS wieder hoch.
Nach dem Neustart ist die ARISC-Firmware nicht mehr geladen (`R_CPUCFG` = 0,
SRAM-Rauschen); fuer weitere Versuche muss `arisc_load.py` erneut laufen.

Mechanismus **nicht bewiesen**. Zwei plausible Wege, beide zum Watchdog:
der Loopback-Handler `0x72b8` wartet endlos auf die ungetaktete ARISC-UART
`0x07080080`; oder die vier Schreibzugriffe kamen nicht als sauberer Rahmen an
(der Fuellstand sprang 0->5->8->11->12), was zu falschem `count` und
Pufferueberlauf fuehrt.

**Belegt sicher ist nur der Einzelwort-Pfad.** Mehrwort-`send` ist im Werkzeug
hinter zwei Schalter gelegt.

Werkzeug und Protokoll: `analyse/arisc-msg/` (`arisc_msg.py`, `README.md`,
`DEVICE-LOG.md`).

## Das Rahmenformat, aus dem Firmware-Code (05.09.)

### Senden (ARISC -> ARM), Bauer `0xc4a0`, Sender `0x75d4`

Die Nachricht liegt als Struktur im Speicher; die Bytes werden zu Woertern
gepackt und einzeln in MSG_DATA geschrieben:

```
0xc4b8  l.addi r3, r0, 0xff90 ; l.sb 58(r1), r3    Byte +2 = 0x90   type
0xc4c4  l.addi r3, r0, 0x0002 ; l.sb 57(r1), r3    Byte +1 = 0x02   attr
0xc4d0  l.addi r3, r0, 0x0000 ; l.sb 59(r1), r3    Byte +3 = 0x00   result
0xc4dc  l.addi r3, r0, 0x000d ; l.sb 60(r1), r3    Byte +4 = 0x0d   count
0xc4f4  l.addi r3, r1, 0x0038                      r3 = &Struktur
0xc4f8  l.jal  0x75d4                              senden
```

In `0x75d4`:

```
Wort 0 = state | attr<<8 | type<<16 | result<<24
l.movhi r20, 0x0300 ; l.ori r20, r20, 0x307c   ->  MSG_DATA user0 (ARISC->ARM)
l.sw 0(r20), r2
l.jal 0x7504 mit r3 = 3                        ->  VOR JEDEM Wort Platzpruefung
l.lbz r3, 4(r14)                               ->  dann count als Wort 1
```

**Byte +4 ist `count`** — dort, wo `struct arisc_message` aus dem linux-3.4-BSP
`next` hat. Das Layout dieser Firmware weicht also ab, wie schon beim
Parameterblock vermutet.

### Empfangen (ARM -> ARISC), `0x7978`

Exakt spiegelbildlich, aus `0x0300347c` (MSG_DATA) mit Stand aus `0x0300346c`:

```
Wort 0  ->  Byte 0 = w & 0xff          state
            Byte 1 = (w >> 8) & 0xff   attr
            Byte 2 = (w >> 16) & 0xff  type
            Byte 3 = (w >> 24) & 0xff  result
Wort 1  ->  Byte 4 = count
dann        count Datenwoerter
```

### Das Rahmenformat auf der Leitung

```
Wort 0 : state | attr<<8 | type<<16 | result<<24
Wort 1 : count
Wort 2 : Datenwort 1
  ...  : ... insgesamt count Datenwoerter
--------------------------------------------------
gesamt : 2 + count Woerter
```

Gegenprobe am STARTUP_NOTIFY: `0x00900200` (state 0, attr 2, type 0x90,
result 0), dann `0x0000000d` (count 13), dann 13 Datenwoerter = **15 Woerter**.
Empfangen haben wir 8, weil die Platzpruefung `0x7504` ab Fuellstand 8 abbricht.

### Der Absturz ist damit erklaert, nicht mehr vermutet

Die Empfangsschleife **hat kein Zeitlimit**:

```
007a0c  l.lwz  r7, 0(0x0300346c)     Fuellstand
007a10  l.sfeqi r0, r7, 0
007a14  l.bf   0x7a0c                <-- Sprung auf sich selbst
```

Sie dreht, bis das naechste Wort kommt, und fuettert dabei den Watchdog nicht.
**Wer weniger Woerter schickt, als `count` ankuendigt, haengt die ARISC
zwangslaeufig** — Watchdog-Reset des ganzen SoC.

Das war der Absturz vom 04.09.: vier Woerter mit unpassendem `count`.

**Regel fuers Senden, ohne Ausnahme:** genau `2 + count` Woerter schreiben,
`count` muss stimmen, und der Doorbell erst danach. Ein abgebrochener Rahmen ist
kein Fehlversuch, sondern ein Reset.

### Was noch fehlt

- **Welcher `type` fuer PullHotPlug.** Bekannt ist nur `0x90` = STARTUP_NOTIFY.
  Die generische Liste (`ARISC_MESSAGE_BASE 0x10 + n`) gilt fuer den
  BSP-Treiber; diese TV-Firmware hat eigene Typen.
- **Die Bedeutung der Datenwoerter.** Der Empfaenger legt sie ueber einen Zeiger
  bei `msg+28` ab.
- Wie sich der BOP-Unterbefehl (`PullHotPlug 0x0211` aus
  `re/notes/EDID-PROTOCOL.md`) in dieses Format einfuegt — vermutlich als
  Nutzlast innerhalb der Datenwoerter, belegt ist es nicht.

Der Dispatcher mit den neun EDID/HPD-Faellen liegt laut deiner RE bei `0x12490`;
das ist die naechste Stelle zum Lesen.

## Der HDMI-Dispatcher, vollstaendig aufgeschluesselt (05.09.)

### Aufrufkonvention

`0x12490`, aufgerufen als `dispatcher(r3 = fall_index & 0xff, r4 = datenzeiger)`.
Index muss `<= 8` sein, sonst Sprung nach `0x12818`. Sprungtabelle `0x15b48`:

| Fall | Handler | Formatstring | Bedeutung |
|---|---|---|---|
| 0 | `0x124d4` | | |
| 1 | `0x1257c` | | |
| 2 | `0x12818` | | Fehlerzweig / default |
| 3 | `0x125c4` | | |
| 4 | `0x12618` | | |
| 5 | `0x12734` | `0x1554c` | **"Output EDID"** |
| 6 | `0x1275c` | | |
| **7** | **`0x127b8`** | `0x15575` | **"Host pull Hotplug port %d, value = %d"** |
| 8 | `0x127f0` | | |

### KORREKTUR an `re/notes/arisc-firmware.md`

Dort steht: *„only case 5/PullHotPlug writes `0x07091014`"*. **Fuer diese
Firmware-Fassung stimmt das nicht.**

- **Fall 5** ist „Output EDID" und fuehrt ueber `0x11ff4` -> `0x11cac` auf
  **`0x07091b04`** — ein anderes Register.
- **Fall 7** ist „Host pull Hotplug" und fuehrt ueber `0x12330`/`0x12338` auf
  **`0x121e4`**, und *das* schreibt `0x07091014`.

Nachgezaehlt per Aufrufgraph ueber alle neun Faelle: **nur Fall 7** erreicht den
Pin-Treiber. Moeglich, dass die urspruengliche RE an einer anderen Blob-Version
gearbeitet hat; unsere ist `projector-tv303-android11-v1.3-3-g293ff69`.

### Fall 7: die Argumente

```
0127b8  l.lbz r3, 0(r2)      Datenbyte 0 = port
0127bc  l.addi r14, r2, 1
0127c8  l.lbz r3, 0(r14)     Datenbyte 1 = value
0127d4  l.jal 0xbf70         printf("Host pull Hotplug port %d, value = %d")
0127e0  l.jal 0x12330        -> set_hpd(r3 = value, r4 = port)
0127e4  l.lbz r4, 0(r2)      Delay-Slot: port
```

Und die Pruefungen in `0x12338`:

```
01233c  l.andi   r2, r4, 0xff       port
012344  l.sfgtui r2, 2              port > 2 -> Fehler ("Wrong HDMI Port")
01234c  l.andi   r14, r3, 0xff      value
012350  l.sfeqi  r14, 2  -> 0x12398 ─┐
012358  l.sfeqi  r14, 3  -> 0x123b8 ─┼─> rufen 0x121e4 -> schreiben 0x07091014
012360  l.sfeqi  r14, 1  -> Zaehler, dann weiter
012364  sonst            -> "Unknown Hotplug Type"
```

**`port` in {0,1,2}, `value` in {1,2,3}.** Die zugehoerigen Meldungen im Bild:
`hpd %d UP`, `hpd %d DOWN`, `hpd %d RESET` (`0x1543f`/`0x1544a`/`0x15457`).
Welche Zahl welchem Zustand entspricht, ist damit **nicht** endgueltig belegt —
die Zuordnung der drei Zweige zu den drei Meldungen muss noch nachgesehen werden.

### Der Pin-Treiber `0x121e4`

`set_hpd_pin(port, value)`: Port mal 8 als Index in eine Tabelle bei `0x17248`,
dann Read-Modify-Write. Beide Zugriffe auf `0x07091014` liegen in dieser
Funktion — `0x12244` liest, **`0x12314` schreibt**. Das deckt sich mit der
urspruenglichen RE-Angabe „HPD GPIO driver @0x121e4".

### Weitere Zeichenketten, die den Funktionsumfang zeigen

```
0x154e0  Request EDID Status          0x15559  Host Read HDMI port Number
0x154f5  Host Set EDID Version        0x1559c  Host Reset EDID Module
0x15513  Read EDID. MSG= 0x%x, 0x%x   0x155cc  SysResetHotplug-%d
0x1554c  Output EDID                  0x15575  Host pull Hotplug port %d, value = %d
0x153ea  EDID-HPD %d LOW              0x153fb  Chip HPD RX0 %d  (RX1, RX2 folgen)
0x15307  ERR:Unknown DispMips Message type (%x)
0x1549d  ERR:Unknown Mips Command (code %x)
```

Das sind die neun Faelle des Dispatchers. `Chip HPD RX0/1/2` und `EDID-HPD %d LOW`
belegen zusaetzlich, dass die Firmware drei getrennte HDMI-Ports fuehrt.

### Was jetzt noch fehlt

Die Bruecke vom Msgbox-Rahmen zum Dispatcher-Aufruf: **welche Felder des Rahmens
den Fall-Index bestimmen**, und wo der Datenzeiger herkommt. Der Dispatcher wird
von genau einer Stelle angesprungen (`l.j @0x11670`), und der Code davor setzt
den Index aus dem Kontrollfluss — die Zuordnung liegt weiter oben.

## Die HPD-Zustandsmaschine, vollstaendig (05.09.)

Drei Bausteine, alle im Bild belegt. Der Zaehler liegt bei AR100 `0x1722c`,
ein Byte je Port (`0x1722c`..`0x1722e`).

### Fall 7 setzt den Anstoss (`0x12338`)

| `value` | Meldung | `set_hpd_pin`? | zusaetzlich |
|---|---|---|---|
| **1** | `hpd %d UP` (`0x1543f`) | **nein** | `*(0x1722c+port) += 1` |
| **2** | `hpd %d DOWN` (`0x1544a`) | ja, `(port, 0)` | — |
| **3** | `hpd %d RESET` (`0x15457`) | ja, `(port, 0)` | `*(0x1722c+port) := 84` |
| sonst | `ERR:Unknown Hotplug Type %d` (`0x15465`) | | |

`port > 2` faellt vorher auf „Wrong HDMI Port" (`0x1542e`).

### Der Tick zaehlt herunter (`0x10db8`)

```
l.lbz    r2, 0(r3)          Zaehler des Ports
l.sfltui r2, 1              == 0 -> ueberspringen
l.addi   r2, r2, 0xffff     sonst -1
l.sb     0(r3), r2
...                         Schleife bis r3 == 0x1722f (drei Ports)
```

### Der Wecker hebt den Pin (`0x10f3c`)

```
l.lbz   r16, 0(r14)         Zaehler
l.sfnei r16, 1              != 1 -> ueberspringen
l.sb    0(r14), r3          Zaehler := 0
l.ori   r4, r16, 0          r4 = 1
l.jal   0x121e4             set_hpd_pin(port, 1)   -> Pin HIGH
...                         Schleife ueber drei Ports
```

**Er handelt nur, wenn der Zaehler exakt 1 ist** — nicht „<= 1". Damit ergibt sich:

```
RESET (3):  Pin sofort LOW, Zaehler 84
            -> 83 Ticks lang LOW
            -> Zaehler erreicht 1 -> Pin HIGH, steigende Flanke
UP (1):     Zaehler 0 -> 1
            -> naechster Tick: Pin HIGH
DOWN (2):   Pin LOW, kein Zaehler
```

**Das ist der Mechanismus, den `re/notes/edid-hpd.md` als
*„sustained-LOW(8s)+rising edge forces EDID re-read"* beschreibt** — und die 84
Ticks erklaeren die dort genannten acht Sekunden (bei ~100 ms Tick).

### Praktische Folge

Zum blossen Anheben des Pins genuegt **`value = 1` (UP)** — der Pin geht beim
naechsten Tick hoch. Fuer einen vollstaendigen Hotplug-Zyklus, der die Quelle
zum EDID-Neulesen zwingt, ist **`value = 3` (RESET)** der richtige Befehl.

`set_hpd_pin` (`0x121e4`) macht dann Read-Modify-Write auf `0x07091014`
(`0x12244` liest, `0x12314` schreibt), mit einer Port-Tabelle bei `0x17248`,
Schrittweite 8.

## Werkzeuge und der Weg zum Abschluss (05.09.)

### `analyse/arisc-msg/arisc_send.py`

Sender fuer Rahmen an die laufende ARISC. Die Sicherheitseigenschaft ist
**strukturell, nicht per Parameter**: `count` wird immer aus der tatsaechlichen
Nutzlast berechnet (`build_frame`), ein Missverhaeltnis ist nicht darstellbar.
Zusaetzlich wird vor dem Senden geprueft, ob im FIFO Platz fuer den **ganzen**
Rahmen ist — ein Rahmen, der mittendrin am vollen FIFO haengenbleibt, haette
dieselbe Wirkung wie ein zu kurzer. Sperrbereiche `0x07091xxx` und TVTOP sind im
Speicherzugriff selbst blockiert, nicht nur durch Disziplin.

Unterbefehle: `observe`, `drain`, `watch`, `send`, `hotplug`.

### Die Wirkung ist gefahrlos beobachtbar

`0x07091014` duerfen wir nicht lesen. Aber der **HPD-Zaehler der Firmware** liegt
im SRAM: AR100 `0x1722c`..`0x1722e`, ARM `0x0011722c`, ein Byte je Port. Damit
laesst sich belegen, dass ein Hotplug-Befehl angekommen und ausgefuehrt wurde:

```
RESET  -> Zaehler springt auf 84, faellt dann Tick fuer Tick
UP     -> Zaehler 0 -> 1, beim naechsten Tick wieder 0 (Pin gehoben)
```

Nebeneffekt: `watch` **misst** damit auch die Tickrate, die statisch nicht zu
ermitteln war (Tick und Pin-Anheber sind nur ueber Funktionszeiger zur Laufzeit
registriert, ohne direkte Aufrufer im Bild). Ob 84 Ticks tatsaechlich den in
`re/notes/edid-hpd.md` genannten acht Sekunden entsprechen, faellt beim ersten
Test nebenbei ab.

### Der `type` ist auch empirisch bestimmbar

Offen ist, welcher `type` den HDMI-Dispatcher mit Fall-Index 7 erreicht. Das ist
statisch zu klaeren (Rueckverfolgung von `l.j @0x11670`), **aber auch empirisch**,
und zwar gefahrlos:

- `count` stimmt strukturell immer, ein Haenger ist damit ausgeschlossen
- ein unbekannter `type` liefert nur `result = -3`, wie der versehentliche
  Rundlauf vom 04.09. gezeigt hat (`0xfd000211`)

Ein Durchlauf ueber die 256 moeglichen `type`-Werte mit gueltiger Ein-Wort-
Nutzlast ist deshalb ein zulaessiges Verfahren: man sucht die Antwort, die
**nicht** `-3` ist, oder beobachtet den HPD-Zaehler. Das ist Brute Force, aber
es ist sicher, und es bestaetigt ein statisches Ergebnis unabhaengig.

## Zielarchitektur: was aus den Analyse-Skripten werden muss

`arisc_load.py`, `arisc_send.py` und `arisc_msg.py` sind **Instrumente, kein
Produkt.** Ihr Zweck war, das Protokoll zu finden; danach sind sie Referenz und
Testgeschirr — wenn ein Treiber sich anders verhaelt als sie, weiss man, wo man
nachsieht.

### Warum ein Kernel-Treiber noetig ist

Vier Gruende, jeder davon in dieser Sitzung aufgetreten:

1. `/dev/mem` braucht root und eine passende `STRICT_DEVMEM`-Konfiguration.
2. **Keine Synchronisation gegen `cpu_comm`.** Das ist der wichtigste Punkt,
   siehe unten.
3. Die ARISC muss bei **jedem** Boot geladen werden. Nach dem Watchdog-Reset am
   04.09. war sie weg; ein Skript ist dafuer der falsche Ort.
4. **Niemand holt eingehende Nachrichten ab.** Genau das war beobachtbar: acht
   Woerter stapelten sich im ARISC->ARM-FIFO, und die Firmware brach ihr
   `STARTUP_NOTIFY` nach 8 von 15 Woertern ab, weil ihre Sende-Vorpruefung
   (`0x7504`) ab Fuellstand 8 aufgibt.

### Der Besitzkonflikt um die Msgbox

| | |
|---|---|
| `sun6i-msgbox.c` | im Kernelbaum, `CONFIG_SUN6I_MSGBOX=y` |
| unsere DTS | gibt die Msgbox **absichtlich nicht** an ihn: *„IRQ, reg, and clocks are on the cpu-comm node instead"* |
| `cpu_comm_hw.c` | ioremappt `0x03003000` **komplett** und besitzt den Block |

Die ARISC-Pfade (`0x03003000` user0, `0x03003400` user1) liegen **in demselben
Fenster**. Die Analyse-Skripte greifen per `/dev/mem` an `cpu_comm` vorbei darauf
zu. Fuer Bring-up geht das; als Dauerzustand ist es dieselbe Klasse Problem wie
KMS gegen DECD und tvtop gegen KMS — „genau einer darf den Block besitzen".

### Drei Zuschnitte

| | Vorteil | Nachteil |
|---|---|---|
| **A. `cpu_comm` erweitern** | besitzt den Block schon, kennt die Registerkarte, hat den IRQ | der Treiber wird zwei Dinge |
| **B. `sun6i-msgbox` als Besitzer**, `cpu_comm` und ARISC als Mailbox-Clients | idiomatisch mainline | baut `cpu_comm`s Transport um — an etwas, das gerade erst laeuft |
| **C. eigener ARISC-Treiber** mit eigenem Sub-Block | klare Trennung | zwei Treiber auf einem Registerblock ohne Koordination |

**Empfehlung: A jetzt, B als Endziel.** Nicht weil A schoener ist, sondern weil
`cpu_comm` den Block bereits besitzt und dort nichts umgebaut wird, was
funktioniert. B lohnt, wenn der Rest steht.

### Firmware laden

Per **`request_firmware()`** im Probe, Blob als
`/lib/firmware/sunxi-arisc-tv303.bin`. Damit neu ladbar, testbar, kein
Boot-Pfad-Risiko — im Gegensatz zum Vendor, der es im BL31 macht. Der
Ladevorgang selbst ist in `analyse/arisc-loader/arisc_load.py` vollstaendig
beschrieben und am Geraet verifiziert (0 Abweichungen ueber 31744 Woerter).

### Wer den Treiber anspricht — und was das repariert

**`legacy/patches/0023-drm-add-sun50i-h713-hdmi-rx-driver.patch`.** Er mappt
heute `0x07091000` und schreibt `+0x14` direkt, mit dem Kommentar
*„ARISC HPD-pin (already wired via separate path)"*.

**Auf unserem Board ist genau das der harte SoC-Haenger** — zweimal gemessen,
und die Firmware-Analyse erklaert warum: 27 Codestellen der ARISC bilden
Adressen in `0x07091xxx`, der Pin-Zugriff liegt in `0x121e4`. Der Block
antwortet der ARISC, nicht dem ARM.

Der ARISC-Treiber fuegt also nicht nur etwas hinzu, er **repariert patch 0023**:
statt eines `writel` auf ein Register, das dem ARM nicht gehoert, ein Aufruf wie

```c
h713_arisc_hotplug(port, H713_HPD_RESET);   /* port 0..2, value 1/2/3 */
```

Darueber dann optional Userspace (`hy310-hdmird`) fuer die MIPS-Seite — anderer
Strang, gleiche Msgbox.

### Reihenfolge

Den Treiber **erst bauen, wenn der `type` steht** und der Rundlauf einmal am
Geraet gesehen wurde. Vorher wuesste er nicht, was er senden soll.

### KORREKTUR: der `type`-Sweep ist NICHT gefahrlos

Weiter oben steht, ein Durchlauf ueber alle 256 `type`-Werte sei ein zulaessiges,
sicheres Verfahren, weil `count` strukturell stimmt und ein unbekannter Typ nur
`result = -3` liefert. **Das ist nur die halbe Wahrheit.**

Sicher ist der Sweep gegen **Haenger** — ein korrekt gezaehlter Rahmen kann die
Empfangsschleife nicht blockieren. Er ist **nicht** sicher gegen **Nebenwirkungen**:
der generische Typraum enthaelt ausdruecklich Energiebefehle. Aus
`arisc_messages.h`, Basis `ARISC_MESSAGE_BASE = 0x10`:

```
ARISC_SSTANDBY_ENTER_REQ     0x10    Standby betreten
ARISC_NSTANDBY_ENTER_REQ     0x12
ARISC_ESSTANDBY_ENTER_REQ    0x16
ARISC_TSTANDBY_ENTER_REQ     0x17
ARISC_FAKE_POWER_OFF_REQ     0x19    Geraet ausschalten
ARISC_CPUIDLE_ENTER_REQ      0x1a
```

Ein blinder Sweep kann also das Geraet in Standby schicken oder ausschalten. Ob
diese TV-Firmware dieselben Typnummern fuehrt, ist unbelegt — aber das ist kein
Argument dafuer, es auszuprobieren, sondern eines dagegen.

**Der Sweep bleibt moeglich, aber nur ueber einen begruendet eingegrenzten
Bereich**, und erst nachdem die statische Analyse gescheitert ist.

### Ausserdem: kein Antwortrahmen bei unbekanntem Typ

Am Geraet geprueft (05.09.): ein sauberer Rahmen mit `type = 0x00`, `count = 1`
wurde von der ARISC **abgeholt und verarbeitet** (TX-FIFO wieder leer, Stack
bewegte sich 102 -> 107), aber sie hat **nichts zurueckgeschickt**.

Damit faellt „Antwort != -3" als Suchkriterium aus. Das verbleibende, eindeutige
Kriterium fuer Fall 7 ist der **HPD-Zaehler** bei ARM `0x0011722c`: springt er auf
84, ist ein RESET angekommen. Das ist ohnehin das bessere Kriterium, weil es die
Wirkung misst statt einer Quittung.

### Nebenbei bestaetigt: das Startup-Telegramm hat wirklich 15 Woerter

Beim Leeren des Empfangs-FIFO kamen die **restlichen sieben** Woerter, darunter
`0x76312e69` (`"i.1v"`) und `0x32393333`/`0x66363967` (`"3392"`/`"g96f"`) — der
Schwanz von `...-v1.3-3-g293ff69`. 8 + 7 = 15 = `2 + count(13)`. Die Firmware
hatte die fehlenden sieben nachgeliefert, sobald wieder Platz war.

---

# ABGESCHLOSSEN 05.09.2026: HPD läuft, die ganze Kette ist device-verified

`PullHotPlug` erreicht die ARISC, Fall 7 wird ausgeführt, und der HPD-Pin
wird von der Firmware gesetzt. Belegt durch drei voneinander unabhängige
Beobachtungen bei jedem Aufruf:

* die `memset`-Sonde bei `0x17320` wird genullt (Handler `0x11550` lief),
* der HPD-Zähler `[0x11722c + port]` springt auf **exakt 84** und nur beim
  adressierten Port,
* er läuft auf 0 herunter — und auf 0 bringt ihn ausschließlich die Stufe,
  die `pin_write(port, 1)` aufruft.

Werkzeug: [`analyse/arisc-msg/arisc_hdmi.py`](../analyse/arisc-msg/arisc_hdmi.py).

## Es gibt zwei Empfangswege, nicht einen

Beide hängen an derselben Msgbox `0x03003000`, sind aber vollständig getrennt.
**Das war der eigentliche Fehler in allen bisherigen Versuchen** — auch in
meinen: wir haben HDMI-Rahmen an den Standby-Dispatcher geschickt.

| | Standby | **HDMI/RPM** |
|---|---|---|
| MSG_DATA | `0x0300347c` (user1 **Port 3**) | `0x03003470` (user1 **Port 0**) |
| FIFO_STAT | `0x0300346c` | `0x03003460` |
| Empfänger | `0x7970` → Dispatcher `0xbca0` | Pumpe `0x7fd8` → `classify 0x114e8` |
| Format | `state\|attr<<8\|type<<16\|result<<24`, dann `count`, dann Daten | BOP: `0xA5\|seq<<8\|type<<16\|length<<24`, Füllwort, Nutzlast |

Der Standby-Dispatcher kennt genau neun Typen — alles andere endet in
`ERR:imt [%x]` mit `result = -3`, geschrieben nach `byte[3]` (`0xbe4c`):

| type | Name aus der Firmware | Handler |
|---|---|---|
| `0x19` | `fake poweroff req` | `0xea98` |
| `0x22` | `cpu op req` | `0xe518` |
| `0x24` | `sys op req` | `0xe9d8` |
| `0x25` | `clear wakeup src req` | `0xcae0` |
| `0x26` | `set wakeup src req` | `0xc994` |
| `0x60` / `0x62` / `0x64` | (unbenannt) | `0xc27c` / `0x72b8` / `0xc6e8` |
| `0x61` | (unbenannt) | — gibt Status 0 zurück |

Damit ist auch das alte Rätsel „warum antwortet die ARISC mit `-3`" erledigt:
`type = 0` ist dort schlicht ungültig. `re/notes/…` deutete das als „hollow by
design"; richtig ist, dass die Nachricht den HDMI-Weg nie betreten hat.

**Berichtigung zu „Empfangen (ARM → ARISC), `0x7978`" weiter oben:** das ist
der Standby-Weg. Der HDMI-Weg liegt bei `0x7fd8`/`0x8064`.

Die RPM-Adressen sind im Blob nicht als `0x0300…` zu finden, weil `0x7e4c`
sie rechnet — deshalb hat der erste Scan sie übersehen:

```
addr = (0x00c00d1c + chan + rproc*64) << 2      MSG_DATA
addr = (0x00c00d18 + chan + rproc*64) << 2      FIFO_STAT
rproc 0 = ARM, rproc 2 = MIPS;  chan 0 (Poller 0x7bbc setzt r14 = 0)
```

Der Demux `0x7f38` wählt allein über die rproc-id und ruft den registrierten
Handler; beide Slots sind im laufenden System belegt (nachgelesen):
`[0x115bc8] = 0x000114e8` (classify) und `[0x115be0] = 0x0001180c`.

## Die Falle: die Pumpe vergisst `length` zwischen den Worten

`type` und `length` stehen in den Registern `r18`/`r14`, nicht im Kontext, und
`0x804c`/`0x8054` setzen sie bei **jedem** Einsprung auf 0. Der Poller `0x7bbc`
weckt die Pumpe aber schon, sobald das erste Wort im FIFO liegt. Kommen die
Worte nicht in einem Rutsch an, startet die Pumpe zwischendrin neu — `length`
ist wieder 0, und Zustand 1 nimmt bei `0x810c` den `length == 0`-Zweig:
sofortige Ablieferung mit Länge 0. Wortweise gemessen:

```
nach Wort 0 (0x040001a5):  ctx[0]=1   Marker 0xA5 akzeptiert, Kopf geparst
nach Wort 1 (0x00000000):  ctx[0]=0   sofort abgeliefert statt Zustand 2
```

Das erklärt, warum wochenlang „nichts passierte", obwohl der Rahmen formal
stimmte. Der Ausweg nutzt die Eigenheit, statt gegen sie zu kämpfen:
`classify` liest den Unterbefehl aus dem **Puffer**, nicht aus der Länge
(`0x11508: r4 = r5[0]`). Also Nutzlast direkt in den Puffer der Pumpe
schreiben — `ctx+5` = **`0x115f59`** — und einen 2-Wort-Rahmen mit `length = 0`
schicken. Das ist gegen das Rennen immun.

```
[0x115f59] = sub_cmd_lo, sub_cmd_hi, arg1, arg2
MSG_DATA 0x03003470 <- 0x000001a5      Marker A5, seq 1, type 0, length 0
MSG_DATA 0x03003470 <- 0x00000000      Füllwort
TX_IRQ_EN 0x03003430 |= 0x02, ~20 µs, löschen
```

`classify` verlangt `type == 0` (`0x11500`) und `sub_cmd_lo` in `0x10..0x15`
(`0x11528`, Index in Tabelle `0x15b30`). Für `PullHotPlug 0x0211`:
`lo = 0x11` → Handler **`0x11550`**, `hi = 2` → **`0x1164c`**, dort `r3 = 7`
und `arg1`/`arg2` in den Datenpuffer, dann `l.j 0x12490` → **Fall 7**.

## Fall 7 und die zweistufige Zählerlogik

`0x12330`, Meldung `"Host pull Hotplug port %d, value = %d"`:

| value | Wirkung |
|---|---|
| 1 UP | `[0x1722c+port] += 1` |
| 2 DOWN | `0x121e4(port, 0)` — Pin sofort low |
| 3 RESET | `0x121e4(port, 0)`, dann `[0x1722c+port] = 84` |
| sonst | `ERR:Unknown Hotplug Type %d` |
| port > 2 | `ERR:Wrong HDMI Port Number` |

Den Zähler arbeiten **zwei getrennte Stufen** ab — das ist der Schlüssel zur
Fehlersuche:

```
0x10db4   Timer-ISR:       while (z > 1) z--;                  ~100 Hz, Boden bei 1
0x10f30   Hauptschleife:   if (z == 1) { z = 0; 0x121e4(port,1); }   Pin high
```

Gemessen: 84 → 1 in 0,9 s, also 100 Hz. Daraus folgt zweierlei:

1. **HPD geht auch ganz ohne Nachricht.** `[0x11722c+port]` von Linux aus auf
   ≥ 1 schreiben genügt; die ARISC schreibt den Pin. `arisc_hdmi.py pin`.
2. **Der Zähler ist die Lebensanzeige der Hauptschleife.** Bleibt er auf 1
   stehen, läuft nur noch der Timer-ISR — die Hauptschleife hängt.

Port-Tabelle `0x17248` (8 Byte je Port) ist im laufenden System gefüllt,
Freigabe-Byte `[0x1723f] = 1`:

```
Port 0: 01 00 10 01     Port 1: 02 01 20 02     Port 2: 04 02 30 04
        ^Maske ^Index ^Offset
```

## Warum die Hauptschleife hängen bleibt — und wie man sie befreit

`0x7970` prüft `FIFO_STAT[3]` und kehrt bei leerem FIFO sofort zurück. Hat ein
Rahmen aber begonnen, wartet es **ohne Timeout** auf die restlichen Worte
(`0x79a8`, `0x79e0`, `0x7ad0`). Ein halber Rahmen auf Port 3 legt damit die
ganze Hauptschleife lahm:

```
0xc5b4  receive(buf, 0)        Standby, Port 3    <- hier bleibt sie stehen
0xc5c8  handle(buf)
0xc5d0  rpm_poll()             RPM-Poller, Port 0  <- läuft dann nie
0xc664  hpd_fire()             Pin high            <- läuft dann nie
0xc66c  j 0xc5b0
```

Genau das hatten wir uns mit den ersten Versuchen eingehandelt. Befreien:
Nullworte auf Port 3 nachschieben, je zwei ergeben einen Leerrahmen. In
unserem Fall genügten drei — danach lief alles wieder. `arisc_hdmi.py unstick`
macht das und prüft nach jedem Wort über den Zähler, ob die Schleife zurück ist.

**Das ist auch die Erklärung für frühere widersprüchliche Messungen:** eine
hängende Hauptschleife leert Port 0 nicht, der FIFO läuft voll, und
`FIFO_STAT` liefert dann Werte, die ich fälschlich als „geleert" gelesen habe.
`FIFO_STAT` ist kein Wortzähler: 0 = leer, 5 = ein Wort, 15 = voll.

## Das Firmware-Log geht an R_UART

`printf` ist `0xbf70(level, fmt, …)`, Pegel-Variable `[0x115c0c]`, im laufenden
System **3**. Die Ausgabe läuft über `0x7234` → `0x7168` und landet auf
**R_UART `0x07080000`** (Statusregister `0x0708007c`, Bit 1), freigegeben durch
`[0x115bc0]` und `[0x115f48]`. Also ein physischer Port, kein Speicherpuffer —
von Linux aus nicht lesbar. Wer den Log braucht, muss `0x7168` patchen oder
R_UART physisch abgreifen. Deshalb arbeitet `arisc_hdmi.py` mit
Nebenwirkungs-Sonden (`memset` bei `0x17320`, HPD-Zähler) statt mit Meldungen.

## Was das für die Portierung heißt

Ein Kernel-Treiber braucht nichts weiter als:

* Msgbox `0x03003000` mappen, ARISC-SRAM `0x115000`–`0x118000` mappen,
* HPD setzen: `PullHotPlug` wie oben abliefern **oder** direkt
  `[0x11722c+port]` schreiben,
* Lebensprüfung: Zähler auf 3 setzen, muss binnen ~100 ms 0 werden,
* niemals `0x07091014` vom ARM lesen — das hängt den SoC hart.

Offen bleibt bewusst: ob ein Treiber den Puffer-Vorbelegungs-Trick braucht
oder ob drei `writel()` hintereinander schnell genug sind, um der Pumpe
zuvorzukommen. Der Trick funktioniert in jedem Fall und kostet nichts.

### KORREKTUR 05.09.: die SetPortMap-„Korrektur" war selbst falsch

Oben steht in der Tabelle der korrigierten Argumente, `SetPortMap` muesse
`1 0 / 2 1 / 3 2` lauten statt `3 0 / 4 0 / 5 0`. **Das ist zurueckgenommen.**

Der Stock-RPC-Mitschnitt `re/captures/weltneuheit/stock-rpc-LIVE.txt` zeigt auf
der Leitung:

```
sessionID:26 call func:THal_Vp_HDMI_SetPortMap_1_000 Para[0]: 0x4
sessionID:27 call func:THal_Vp_HDMI_SetPortMap_1_000 Para[0]: 0x5
```

Also **Para[0] = 3, 4, 5**. Die Gegenbehauptung stammte aus einem Kommentar in
`hy310-hdmird`, der die elog-Zeilen „Change Port(N) Map, from OLD to NEW"
deutet — eine Herleitung, keine Messung.

**Und der Mitschnitt kann ueber `arg2` nichts sagen:** er druckt in beiden
Dateien *nie* ein `Para[1]` (0 Treffer), auch nicht bei `Wce_SetWindow`, das
nachweislich drei Zeiger nimmt. `ParaCount = 2` aus der libhaldisplay-RE bleibt
also stehen, `arg2` bleibt unbekannt.

Damit war die urspruengliche Fassung von `tools/uboot-hdmi-sequence.txt` richtig,
inklusive ihres eigenen Vorbehalts („arg2 unbekannt, Stock zeigt nur Para[0]").
Die beiden anderen Korrekturen an der Datei — `RegisterSignalChangeCallback` mit
einem statt zwei Argumenten und `SetHDMIHotPlugByPortCallback(1)` — sind davon
nicht betroffen und bleiben.

Nebenbei bestaetigt derselbe Mitschnitt zwei Adressen:
`SetHDCP22Key Para[0]: 0x4e336000` (exakt der Shmem-Offset `0x36000`) und
`Wce_SetWindow Para[0]: 0x4e334fe0` bzw. `0x4e334000` — Stock legt seine
Fensterpuffer also woanders hin als hdmird (`0x37000`).

## 05.09.2026: Phase 2.5 und 3 durch — HDCP-Key angenommen

### 2.5 — TVFE/TVCAP: das HDMI-RX-Fenster ist lesbar

Uebernommen aus cstengers Patch 0087, mit zwei Abweichungen: bei uns ein
**Modul** statt `builtin_platform_driver` (ein Fehlschlag kostet einen Neustart
statt eines Neuflashens) und ein Parameter `probe_read=0` fuer Strom+Takt ohne
den riskanten ersten Lesezugriff. Quelle: `analyse/tvcap/h713-tvcap.c`,
DT-Knoten `tvcap@50c0000` in `sun50i-h713.dtsi`.

```
thdmirx+0x00 = 0x70f80029   +0x0c = 0xfe000115   +0x18 = 0x80000501
thdmirx+0x04 = 0x00000000   +0x10 = 0x03ff00ff   +0x1c = 0x00000000
thdmirx+0x08 = 0x00000000   +0x14 = 0x030000ff
```

**Wort fuer Wort identisch mit cstengers Messung vom 02.09.** auf seinem Board.
Zwei verschiedene Geraete, dieselben Werte — Silizium, das antwortet, kein
floating Bus. Der harte Haenger war ein stromloser Block, nichts Exotischeres.

**Nebenbefund, der Arbeit spart:** die Domains sind schon **an, bevor** das Modul
geladen wird — allein weil der DT-Knoten sie referenziert und `pd_ignore_unused`
in den bootargs steht. Fuer spaetere Treiber genuegt also der Knoten.

**Gegengeprueft:** `CONFIG_SUNXI_TVTOP is not set`, kein Treiber am
`tvtop`-Knoten gebunden (er steht zwar auf `okay`, ist aber inert), und `tvtop`
beansprucht die Power-Domains nicht. Bestaetigt ist dagegen cstengers Warnung:
**`GICv2 142` gehoert `h713-afbd`** (615 Ausloesungen gemessen) — wer je
`CONFIG_SUNXI_TVTOP` einschaltet, reisst dem KMS-Treiber den Interrupt weg.

### 3 — die Init-Sequenz laeuft, und der HDCP-Key wird angenommen

Werkzeug `analyse/hdmi-seq/hdmi_seq.py`, 22 Schritte, alle mit `RETURN`.

**Der Key ist Klartext.** Die 912 Byte aus dem eMMC-Secure-Storage
(`analyse/hdcp-keys/hdcp22-key-912.bin`) wurden nach `0x4e336000` geschrieben und
mit `SetHDCP22Key(0x4e336000, 912)` uebergeben. Der MIPS-elog danach:

```
E/hdmirx      (./THDMIRx.cpp 578)             HDMIRx_SetHDCP22KeyData!!, size:912
E/hdmi_driver (THDMIRx_TV303_Driver.cpp 760)  HdmiRx_HDCP22_LoadKey ok!!
```

Damit ist die Frage aus dem Abschnitt „Was damit nicht gesagt ist" beantwortet:
**kein TEE-Chiffrat, sondern verwendbarer Klartext.** `size:912` stimmt aufs Byte
mit dem Stock-elog. Der elog-Schreibzeiger ging 1879 -> 2068.

**Die HPD-Gate-Flagge kippt bei SetPortMap.** Nach dem ersten
`SetPortMap(3, 0)` liest `0x4b271c2c` **1** statt 0 — genau der Weg, den
`re/notes/edid-hpd.md` als alternative Stock-Kette nennt
(„ARM->MIPS->ARISC HPD via gate-flag MEMORY[0x8B271C2C]=1 (SetPortMap)").
Am Geraet bestaetigt.

### SetPortMap: die Argumente

Gefahren wurde `--portmap stock`, also `Para[0] = 3, 4, 5`. Das ist die
**gemessene** Form aus `re/captures/weltneuheit/stock-rpc-LIVE.txt`. Eine
zwischenzeitliche „Korrektur" auf `(1,0)(2,1)(3,2)` — abgeleitet aus einem
hdmird-Kommentar ueber elog-Text — widersprach der Leitung und ist
zurueckgenommen; siehe den Abschnitt weiter oben. `Para[1]` bleibt unbekannt:
der Mitschnitt druckt grundsaetzlich nur `Para[0]`.

### Was weiterhin offen ist

* **Keine Callbacks.** 5 s Wartezeit, null empfangen. Es gibt aber auch noch kein
  Signal — die Quelle sieht das Board erst, wenn HPD wirklich am Pin liegt.
* **HDCP 1.4** bleibt offen. Der Timeout beim MIPS-Start
  (`HdmiRx_HDCP14_LoadKey(), time out!`, drei Zeilen) ist unveraendert. Neue
  These, jetzt pruefbar: der MIPS startet in U-Boot, **lange bevor** Linux
  TVFE/TVCAP einschaltet — er faehrt seine HDMI-RX-Init also immer mit
  stromlosem Block. Fuer einen Test muessten die Domains schon in U-Boot an sein,
  oder man ruft `ReloadHdcp14Key` nachtraeglich, wenn sie an sind.
* **`SetSource(3)`** (Phase 4) ist nicht gefahren.
