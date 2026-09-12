# S44 — U-Boot über FEL starten (H713 / HY310)

Stand: 10.09.2026, Messungen am Gerät (QZ713DF_A1) über `mainline/external/sunxi-tools/sunxi-fel`.
Es wurde **nichts auf die eMMC geschrieben**; alle Eingriffe sind flüchtig (SRAM/DRAM/Register).

## Kurzfassung

Beide im Auftrag genannten Verdächtigen sind **widerlegt**. Die RVBAR-Auswahl ist korrekt, der
Kratzbereich kollidiert nicht mit dem SPL-Stapel, das DRAM ist einwandfrei und BL31 liegt
byteidentisch an der richtigen Stelle. Übrig bleibt genau ein ungeklärter Schritt: der **zweite**
RMR-Sprung, den `sunxi-fel` ausführt, nachdem der SPL nach FEL zurückgekehrt ist.

Zusätzlich gefunden: ein **Bus-Hänger** — ein Lesezugriff auf `0x05000000` (H616-UART-Basis) friert
den SoC ein. Der H713 hat dort kein Peripheriegerät.

## 1. Verdächtiger 1 — RVBAR-Auswahl: widerlegt

`soc_info.c` kennt für den H713 `rvbar_reg = 0x09010040` und `rvbar_reg_alt = 0x08100040`,
`fel.c:1105` wählt anhand von `ver_reg & 0xff`.

Gemessen im frischen FEL-Zustand:

```
readl 0x03000024  (SRAM_VER_REG) -> 0x00000101      -> & 0xff = 1, also ALTERNATIVE
readl 0x09010040                 -> 0x00000000
readl 0x08100040                 -> 0x00000000
```

Schreib-Rücklese-Test:

| Adresse | geschrieben | zurückgelesen | Befund |
|---|---|---|---|
| `0x09010040` (rvbar_reg) | `0x40000000` | `0x00000000` | Schreiben verpufft |
| `0x08100040` (rvbar_reg_alt) | `0x4a000000` | `0x4a000000` | **hält** |

Drei unabhängige Belege stimmen überein:

1. U-Boot macht es identisch — `arch/arm/mach-sunxi/rmr_switch.S:69` liest `SUNXI_SRAMC_BASE + 36`
   (= `0x03000024`), `ands r0, r0, #0xff`, und nimmt bei ungleich null
   `CONFIG_SUNXI_RVBAR_ALTERNATIVE`. Kconfig setzt das für `MACH_SUN50I_H713` auf `0x08100040`.
2. Der Rücklesetest oben.
3. **Der SPL-Banner selbst.** Der SPL trägt im `boot0.h`-Kopf einen ARM32-Stub, der genau diese
   RVBAR/RMR-Sequenz ausführt, um nach AArch64 zu wechseln. Dass „U-Boot SPL 2026.07-rc5 / DRAM:
   1024 MiB" auf der Konsole erscheint, **beweist, dass RVBAR `0x08100040` stimmt und RMR auf
   diesem Chip funktioniert.**

→ Hier liegt der Fehler nicht.

## 2. Verdächtiger 2 — Kratzbereich kollidiert mit SPL-Stapel: widerlegt

`hexdump 0x121500` vor und nach dem SPL-Lauf, in einer FEL-Sitzung:

```
vor  dem SPL:  00121500: cc cc cc cc ... (durchgehend, unbenutztes SRAM)
nach dem SPL:  00121500: 10 0f 11 ee 00 00 8f e5 1e ff 2f e1 38 08 c5 00
               00121510: 0d 10 a0 e1 00 f0 21 e1 04 10 8f e5 04 d0 8f e5
               00121520: 1e ff 2f e1 00 54 10 00 00 03 12 00 cc cc cc cc
               00121530: cc cc ... (ab hier unberührt)
```

Das ist **sunxi-fels eigener** Stackinfo-Thunk, kein SPL-Inhalt — gut erkennbar an den
zurückgeschriebenen Ergebnissen `00 54 10 00` (= `sp_irq=0x105400`) und `00 03 12 00` (= `sp=0x120300`).
Ab `0x121530` steht weiterhin `cc`. Der SPL fasst `0x121500` nicht an; sein Stapel (`CONFIG_SPL_STACK=0x120000`)
und der BROM-Stapel (`sp=0x120300`) wachsen nach unten und erreichen die Adresse nie.

Unabhängig davon wäre eine Verschmutzung ohnehin folgenlos: `aw_rmr_request()` schreibt den
Thunk unmittelbar vor `aw_fel_execute()` frisch dorthin.

→ Hier liegt der Fehler nicht.

## 3. DRAM und Nutzlast: einwandfrei

Nach `sunxi-fel spl u-boot-sunxi-with-spl.bin` aus dem DRAM zurückgelesen und mit den aus dem FIT
extrahierten Referenzen verglichen:

| Bereich | Größe | Ergebnis |
|---|---|---|
| BL31 @ `0x40000000` | 45.164 B | **byteidentisch** |
| U-Boot-Kopf @ `0x4a000000` | 4.096 B | **byteidentisch** |

Der DRAM-Controller arbeitet also korrekt, und die Images stehen vollständig und fehlerfrei da,
wo sie hingehören.

## 4. Einsprungpunkt: korrekt

Aus dem FIT (`dumpimage`/`fdtget`):

```
/images/atf   : load = 0x40000000, entry = 0x40000000, os = arm-trusted-firmware, arch = arm64
/images/uboot : load = 0x4a000000, KEIN entry,          os = u-boot,               arch = arm64
config-1      : firmware = "atf", loadables = "uboot", fdt = "fdt-1"
```

`fit_load_image()` übernimmt einen Einsprungpunkt nur bei vorhandener `entry`-Eigenschaft. Da
`uboot` keine hat, überschreibt die `loadables`-Schleife den Wert **nicht**. Ergebnis:
`uboot_entry = 0x40000000`, `entry_arch = ARM64` → `enter_in_aarch64 = true`.
`sunxi-fel uboot` ruft also korrekt `aw_rmr_request(0x40000000, aarch64=true)` mit RVBAR `0x08100040`.

## 5. BL31: für die richtige Plattform gebaut

```
plat/allwinner/sun50i_h713/include/sunxi_mmap.h:34:  SUNXI_UART0_BASE  0x02500000
```

Einzige gebaute TF-A-Plattform ist `sun50i_h713`; `build/out/bl31.bin` ist byteidentisch mit dem
BL31 im FIT. BL31 spricht also die richtige UART an (siehe §6).

## 6. Nebenbefund: `0x05000000` hängt den Bus auf — Vorsicht

Der H713 folgt beim Peripherie-Layout **nicht** dem H616, sondern eher D1/R329:

```
UART0 = 0x02500000   (H713, laut DTS und TF-A-Plattform)
UART0 = 0x05000000   (H616 — auf dem H713 NICHT vorhanden)
```

Am Gerät gemessen, `hexdump 0x02500000 0x40` nach dem SPL-Lauf:

```
02500000: 00 00 00 00 00 00 00 00 c1 00 00 00 03 00 00 00
02500010: 03 00 00 00 60 00 00 00 00 00 00 00 00 00 00 00
```

Also FIFO aktiv (`0xc1`), `LCR = 0x03` (8N1), `MCR = 0x03`, **`LSR = 0x60` (THRE|TEMT)** — eine
lebende, konfigurierte UART. Das ist die Konsole.

Ein `hexdump 0x05000000` im selben Aufruf endete dagegen mit `usb_bulk_recv() ERROR -7` und der
SoC war anschließend tot (FEL antwortet nicht mehr, Gerät weiter am USB sichtbar). **Ein Zugriff
auf `0x05000000` friert den H713 ein und erfordert einen Stromzyklus.** Das erklärt vermutlich auch
einen Teil der früher beobachteten „Gerät hängt"-Fälle.

## 7. Was übrig bleibt

Alles auf dem Weg bis zum Sprung ist nachgewiesen korrekt. Der einzige ungemessene Schritt ist der
**zweite RMR**: Der erste (im SPL-`boot0`-Stub, aus dem BROM-Zustand heraus) funktioniert
beweisbar. Der zweite wird von `sunxi-fel` ausgelöst, **nachdem** der SPL über `return_to_fel()`
aus AArch64 nach AArch32 zurückgekehrt ist — also aus einem anderen Prozessorzustand heraus.

Nächster Schritt: den RMR von BL31 trennen. Ein 54-Byte-AArch64-Payload
(`analyse/release/arbeit/r0-fel/rmr-uart-probe.S`) gibt nichts weiter als endlos
`H713-AARCH64-RMR-OK` auf UART0 aus. Wird er nach `reset64` sichtbar, funktioniert der zweite RMR
und der Fehler sitzt in der BL31-Übergabe; bleibt die Konsole still, ist der zweite RMR selbst
das Problem.

## 8. Messung: der zweite RMR springt nicht (10.09., abends)

Isoliertest mit einem 54-Byte-AArch64-Payload (`rmr-uart-probe.S`), der nichts tut als endlos
`H713-AARCH64-RMR-OK` auf UART0 auszugeben — kein DRAM-, kein eMMC-, kein Peripheriezugriff:

```
sunxi-fel -v spl u-boot-sunxi-with-spl.bin  write 0x46000000 rmr-uart-probe.bin  reset64 0x46000000
  -> 47000000-Rücklesung byteidentisch
  -> "Store entry point 0x46000000 to RVBAR 0x08100040, and request warm reset with RMR mode 3... done."
  -> Konsole: nach "Trying to boot from FEL" nichts
  -> FEL danach tot (Timeout), Gerät weiter am USB sichtbar
```

Der Kern **verlässt** die FEL-Schleife, kommt aber nicht am Einsprungpunkt an. Damit ist BL31 als
Ursache endgültig ausgeschlossen: der Payload enthält keinerlei BL31-Code.

## 9. Der Grund liegt im H713-Sonderweg von `return_to_fel`

`arch/arm/cpu/armv8/fel_utils.S`:

```c
#if defined(CONFIG_MACH_SUN50I_H713)
	/*
	 * H713 cannot return via the H616/H6 RMR hotplug mailbox; it
	 * exception-returns directly into the AArch32 FEL restore stub.
	 */
	b	return_to_fel_eret
#else
	... CPU-Hotplug-Mailbox ...
	mov	x0, #2			// RMR reset into AArch32
	msr	RMR_EL3, x0
#endif
```

Alle anderen SoCs kehren per **echtem RMR-Warmreset** nach AArch32 zurück; das stellt die
Ausführungsart von EL3 wieder auf AArch32. Der H713-Zweig macht stattdessen nur ein `eret` nach
unten (`return_to_fel_eret`) — **EL3 bleibt AArch64**. Ob genau das den zweiten RMR unmöglich
macht, wird in §11 geprüft.

## 10. Nebenbefund: der I-Cache-Notbehelf greift auf dem H713 nicht zuverlässig

`aw_disable_icache()` (`fel_lib.c:273`) schreibt seinen Abschalt-Thunk **selbst nach
`scratch_addr` (0x121500)** und führt ihn genau dort aus:

```c
	aw_fel_write_raw(dev, arm_code, soc_info->scratch_addr, sizeof(arm_code));
	aw_fel_execute(dev, soc_info->scratch_addr);
```

Liegt für diese Adresse bereits eine I-Cache-Zeile vor, führt der Kern den **alten** Code aus und
die Abschaltung verpufft — ohne Fehlermeldung. Der Schutz `dev->usb->icache_hacked` gilt zudem nur
je USB-Sitzung, nicht je Zustandswechsel.

Gemessen mit einer eigenen ARM32-Sonde (`cpsr-probe.bin`, liest CPSR und SCTLR):

```
CPSR  = 0x60000153   -> Mode-Bits 0x13 = SVC
SCTLR = 0x00c51838   -> Bit 12 (I) gesetzt: I-Cache AN
```

und das, **obwohl der unmittelbar vorangegangene `write`-Aufruf `aw_disable_icache()` ausgelöst
hatte**. Sichtbare Folgeschäden im selben Zustand:

```
$ sunxi-fel spl u-boot-sunxi-with-spl.bin
Unexpected SCTLR (E121F001)
Stack pointers: sp_irq=0xCCCCCCCC, sp=0xCCCCCCCC
```

`0xCCCCCCCC` ist das Füllmuster des unbenutzten SRAM — sunxi-fels eigene Thunks laufen nicht mehr,
während eine frisch geschriebene eigene Sonde an derselben Adresse einwandfrei läuft. Nach einem
Stromzyklus ist alles wieder normal (`sp_irq=0x00105400, sp=0x00120300`).

**Praktische Folge:** Nach jedem eigenen `exe` auf `0x121500` ist ein Stromzyklus nötig, sonst
liefert `sunxi-fel spl` stillen Unsinn. Das erklärt vermutlich einen Teil der bisherigen
„mal geht es, mal nicht"-Erfahrungen.

## 11. Laufender Test: RMR-Befehl oder Kratzbereich?

Zwei Hypothesen bleiben, und sie verlangen völlig verschiedene Reparaturen:

| | Hypothese | Reparatur |
|---|---|---|
| H1 | Der RMR-Befehl ist in Ordnung; die Adresse `0x121500` liefert wegen abgestandener I-Cache-Zeilen alten Code | klein, nur `sunxi-tools` |
| H2 | Der RMR-Befehl selbst scheitert nach der SPL-Rückkehr (EL3 ist AArch64, siehe §9) | groß, `return_to_fel` in U-Boot |

Trennscharfer Test: dieselbe RMR-Folge wie `aw_rmr_request()`, aber PC-relativ übersetzt
(`rmr-thunk-probe.bin`, 60 B) und von einer **jungfräulichen DRAM-Adresse** ausgeführt, die nie
zuvor im I-Cache lag:

```
sunxi-fel spl  u-boot-sunxi-with-spl.bin      # eigener Aufruf, lief sauber
sunxi-fel write 0x46000000 rmr-uart-probe.bin  # AArch64-Payload
sunxi-fel write 0x47000000 rmr-thunk-probe.bin # ARM32-RMR-Thunk, rvbar=0x08100040, entry=0x46000000, mode=3
sunxi-fel exe   0x47000000
  -> EXIT 0, FEL danach tot
  -> Konsole: nach "Trying to boot from FEL" nichts
  -> FEL danach tot
```

**Ergebnis: H2.** Auch von einer nie zuvor ausgeführten DRAM-Adresse springt der RMR nicht. Der
I-Cache ist damit als Ursache des Boot-Fehlers ausgeschlossen (bleibt aber der eigenständige
Fehler aus §10).

## 12. Ursache

In AArch32 mit **AArch32-EL3** laufen die sicheren PL1-Modi — also auch Secure SVC — auf **EL3**.
Deshalb funktioniert der RMR im `boot0`-Stub des SPL aus genau dem SVC-Modus, der gemessen wurde
(`CPSR = 0x60000153`, Modusbits `0x13`).

Nach dem SPL ist die Lage eine andere: der `boot0`-Stub hat per RMR nach AArch64 gewechselt, damit
ist **EL3 jetzt AArch64**. `return_to_fel_eret` kehrt anschließend nur per `eret` nach unten zurück:

```c
3:	mrs	x4, SCR_EL3
	bic	x4, x4, #0xf		// NS/IRQ/FIQ/EA loeschen
	bic	x4, x4, #(1 << 10)	// RW=0: niedrigere EL laufen AArch32
	msr	SCR_EL3, x4
	msr	SPSR_EL3, x0		// gespeicherter BROM-CPSR, Modus SVC
	msr	ELR_EL3, x3
	eret
```

`SPSR.M = 0b10011` (SVC) bedeutet bei AArch64-EL3 ein Ziel von **EL1**, nicht EL3. Die FEL-Schleife
läuft danach also in AArch32 auf Secure **EL1**. Dort ist das RMR-Register architektonisch nicht
zugänglich: `mrc/mcr p15,0,rX,c12,c0,2` ist undefiniert, die Ausnahme läuft ins Leere, der Kern
verlässt die FEL-Schleife und hängt.

**Die Modusbits verraten das nicht** — sie lauten vorher wie nachher `0x13`. Nur die Ausnahmestufe
darunter ist eine andere. Das erklärt, warum die Sache so schwer zu fassen war.

Die Notizen in `mainline/docs/reference/h713-fel-notes.md` dokumentieren, dass alle RMR-basierten
Rückwege erfolglos blieben (H616-Mailbox `0x070005c0`, H6-RTC-Mailbox `0x070901b8`, direktes RVBAR
`0x08100040`, CurrentEL-abhängiges RMR). Der `eret`-Weg war die funktionierende Notlösung — sein
Preis ist genau dieser: **der zweite RMR wird unmöglich.**

Nebenbei erklärt §10 rückwirkend eine wiederkehrende Beobachtung aus jenen Notizen
(„second-SPL uploads can be misleading"): nach einem SPL-Lauf liefern sunxi-fels Thunks im
Kratzbereich wegen abgestandener I-Cache-Zeilen stillen Unsinn.

## 13. Vorgeschlagene Reparatur: SMC-Falltür statt RMR

Der Ausweg nutzt genau den Zustand, der das Problem verursacht. Weil EL3 nach dem SPL **AArch64**
ist, ist ein `smc` aus AArch32-EL1 eine Falltür **zurück nach AArch64-EL3** — kein RMR, kein
Warmreset, keine BROM-Mitarbeit nötig.

Nötig sind zwei kleine Änderungen:

1. **U-Boot (nur H713).** `return_to_fel_eret` legt vor dem `eret` eine minimale
   AArch64-EL3-Vektortabelle an (2 KiB ausgerichtet, im DRAM, z. B. `0x48000000`) und setzt
   `VBAR_EL3` darauf. Der Eintrag „Synchronous, Lower EL, AArch32" bei Offset `0x600` liest ein
   Zielwort aus einem festen Postfach und springt dorthin.
   Heute geht das nicht von selbst: `CONFIG_ARMV8_SPL_EXCEPTION_VECTORS is not set`, der SPL setzt
   `VBAR_EL3` also gar nicht (`arch/arm/cpu/armv8/start.S:107-121`).
2. **sunxi-tools (nur H713).** `aw_rmr_request()` wird für den H713 zu: Einsprungpunkt ins Postfach
   schreiben, dann einen `smc #0`-Thunk ausführen.

`SCR_EL3.SMD` wird weder vom SPL noch vom Rückkehrpfad gesetzt, `smc` sollte also durchschlagen.

### Offene Vorprüfung

Bevor gebaut wird, ist eine Annahme zu bestätigen: **schlägt `smc` überhaupt nach EL3 durch?**
Billiger Test mit `smc-thunk.bin` (`smc #0; bx lr`, 8 B) nach einem SPL-Lauf:

| FEL danach | Bedeutung |
|---|---|
| tot | `smc` ist nach EL3 gesprungen, `VBAR_EL3` ist ungesetzt → Falltür existiert, Plan trägt |
| lebt | `smc` wurde ignoriert (`bx lr` lief durch) → anderer Weg nötig |


## Dateien

| Pfad (unter `analyse/release/arbeit/r0-fel/`) | Inhalt |
|---|---|
| `s44-baseline-vor-spl.txt` | Registerlage im frischen FEL |
| `s44-spl-und-rueckleser.txt` | SPL-Lauf mit Scratch-Vergleich vorher/nachher |
| `s44-cpsr-vor-nach-spl.txt` | CPSR/SCTLR-Messung |
| `s44-rmr-probe.txt` | `reset64` auf den UART-Payload |
| `s44-eigener-rmr-vorbereitung.txt` | Aufbau für den Test aus §11 |
| `bl31-readback.bin` / `bl31-ref.bin` | BL31 aus dem DRAM bzw. aus dem FIT |
| `rmr-uart-probe.S` / `.bin` | AArch64-UART-Payload (54 B) |
| `rmr-thunk-probe.bin` / `rmr-thunk-bl31.bin` | PC-relative ARM32-RMR-Thunks (60 B) |
| `cpsr-probe.bin` | ARM32-Sonde für CPSR und SCTLR |

## 14. Vorprüfung bestanden: `smc` schlägt nach EL3 durch

```
sunxi-fel spl u-boot-sunxi-with-spl.bin
sunxi-fel version              -> AWUSBFEX ... (FEL lebt)
sunxi-fel write 0x47000000 smc-thunk.bin
sunxi-fel exe   0x47000000     -> EXIT 0
sunxi-fel version              -> TOT
```

FEL lebte unmittelbar vor dem `smc` und war direkt danach tot. Der `smc` ist also nach EL3
gesprungen und dort ins ungesetzte `VBAR_EL3` gelaufen. Die Falltür existiert.

## 15. Umsetzung

### U-Boot: `arch/arm/cpu/armv8/fel_utils.S` (nur H713)

Im H713-Zweig von `return_to_fel()`, vor dem `b return_to_fel_eret`: eine minimale
AArch64-EL3-Vektortabelle wird nach `0x48000000` gelegt (DRAM, frei von BL31 bei `0x40000000` und
U-Boot bei `0x4a000000`, 2 KiB ausgerichtet), `VBAR_EL3` zeigt darauf. Der Eintrag
„Synchronous, Lower EL, AArch32" bei `+0x600` liest ein 64-Bit-Postfach bei `+0x700`:

```
	ldr  x0, [pc, #0x100]   ; Postfach
	cbz  x0, .+8            ; leer: parken statt ins Leere springen
	br   x0
	wfi
	b    .-4
```

Der Stub ist von Hand kodiert, weil er nach `0x48000600` kopiert wird und seine Literal-Abstände
sich deshalb auf das *Ziel* beziehen müssen, nicht auf den Ort im Abbild. Davor stehen
`CurrentEL`-Prüfung (nur EL3 besitzt `VBAR_EL3`) und Cache-Pflege (`dc cvau` / `ic ivau`), damit
der frisch geschriebene Code auf der Befehlsseite sichtbar ist.

Gebaut im Container nach `mainline/build/uboot-v4-feldoor`.

### Bedienung von der PC-Seite

```
sunxi-fel spl   u-boot-sunxi-with-spl.bin       # DRAM hoch, Tuer eingebaut, BL31+U-Boot geladen
sunxi-fel write 0x48000700 <8 Byte Ziel>        # Postfach, little endian, 64 Bit
sunxi-fel write 0x47000000 smc-thunk.bin        # "smc #0 ; bx lr"
sunxi-fel exe   0x47000000
```

### Nachweis am Gerät

```
$ sunxi-fel hexdump 0x48000600 0x20            # nach dem SPL-Lauf
48000600: 00 08 00 58 40 00 00 b4 00 00 1f d6 7f 20 03 d5
48000610: ff ff ff 17 7f 20 03 d5 00 00 00 00 00 00 00 00
$ sunxi-fel hexdump 0x48000700 0x10            # vom SPL genullt
48000700: 00 00 00 00 00 00 00 00 ...
```

Der Stub steht Byte für Byte an Ort und Stelle — der Einbaucode des SPL ist also gelaufen.
Mit Postfach `0x46000000` (54-Byte-UART-Payload) und anschließendem `smc #0` **lief der Payload
los**: die Konsole füllte sich mit `H713-AARCH64-RMR-OK`.

Damit ist die vollständige Kette bewiesen: `smc` aus AArch32-EL1 → EL3/AArch64 → `VBAR_EL3+0x600`
→ Postfach → Sprung. Genau der Schritt, den der zweite RMR nicht leisten konnte.

## 16. Wie weit der FEL-Boot jetzt trägt

Mit der Falltür und Postfach `0x40000000` läuft BL31 vollständig durch. Mit einem Diagnose-BL31
(`LOG_LEVEL=40`, `build/out/bl31-info.bin`, Release bleibt unangetastet):

```
Trying to boot from FEL
NOTICE:  BL31: v2.15.0(release)
NOTICE:  BL31: Detected Allwinner H713 SoC (1860)
NOTICE:  BL31: Found U-Boot DTB at 0x4a0c9f38, model: HY200 QZ713DF_A1 (Allwinner H713)
INFO:    ARM GICv2 driver initialized
INFO:    Configuring SPC Controller
INFO:    PMIC: No known PMIC in DT, skipping setup.
INFO:    BL31: Platform setup done
INFO:    BL31: Initializing runtime services
INFO:    PSCI: Suspend is unavailable
INFO:    BL31: Preparing for EL3 exit to normal world
INFO:    Entry point address = 0x4a000000
INFO:    SPSR = 0x3c9
INFO:    Changed devicetree.
```

`SPSR = 0x3c9` ist EL2h mit maskierten Ausnahmen — korrekt. **BL31 ist damit vollständig
entlastet**: Plattform-Setup fertig, Einsprung richtig, Übergabe eingeleitet. Danach schweigt
U-Boot proper.

### Was dabei ausgeschlossen wurde

| Verdacht | Befund |
|---|---|
| DTB an der falschen Stelle | **Nein.** `_end = 0x4a0c9f38` (aus dem U-Boot-ELF) ist exakt die Adresse, an die sunxi-fel das DTB legt. Die 827192 B im FIT sind `u-boot-nodtb.bin`; das DTB kommt separat genau ans Ende. |
| x0–x3 beim BL31-Einsprung mit Müll belegt (der Stub springt per `br x0`) | **Egal.** `bl31_early_platform_setup2()` ignoriert `arg0`–`arg3`; BL33 kommt aus `PRELOADED_BL33_BASE`. |
| U-Boot gibt gar nicht auf der seriellen Konsole aus | **Nein.** Referenzstart von der eMMC (gleicher Stand, Zeitstempel `12:09:36`) zeigt `In: serial / Out: serial / Err: serial` und ein vollständiges Banner. |

### Warum man nichts sieht, selbst wenn U-Boot liefe

`CONFIG_PRE_CONSOLE_BUFFER=y` mit `CONFIG_PRE_CON_BUF_ADDR=0x4f000000`: **alle** Ausgaben vor
`console_init_r` wandern erst in den Puffer. Hängt U-Boot davor, erscheint kein einziges Zeichen —
auch kein Banner. Auslesen lässt sich der Puffer nicht, weil FEL nach dem Sprung tot ist.

### Sackgasse: `CONFIG_DEBUG_UART`

Ein Diagnosebau mit früher Debug-UART (`DEBUG_UART_BASE=0x02500000`, `SHIFT=2`, `ANNOUNCE`,
`SKIP_INIT`) sollte am Puffer vorbei direkt ausgeben — `debug_uart_init()` steht in
`arch/arm/lib/crt0_64.S:94`, also vor `board_init_f`. Das Abbild ist aber **reproduzierbar
unbrauchbar**: zweimal hintereinander riss der Upload nach dem SPL-Lauf mit
`usb_bulk_send() ERROR -7`, jeweils nach ~20 s, während das sonst identische Abbild ohne
DEBUG_UART fünfmal sauber durchlief.

Größe ist es nicht (SPL 31080 vs. 30744 B, Grenze `CONFIG_SPL_MAX_SIZE=0xbfa0`). Wahrscheinlich
schreibt `debug_uart_init()` im SPL auf `0x02500000`, bevor die UART-Takte frei sind — und genau
solche Zugriffe hängen auf dem H713 den Bus auf (siehe §6). Ansatz verworfen.

## 17. Nebenstrang: FEL ohne Stromziehen auslösen

Jeder Fehlversuch kostet bisher „Reset-Taste halten und Strom einstecken". Zwei Wege geprüft:

- **efex-Flag.** `mw.l 0x0709011c 0x5aa5a55a` (RTC-GP7, im Projekt als „Reboot-Marke" geführt)
  gefolgt von `reset` am U-Boot-Prompt: das Gerät bootet normal durch, **kein** FEL. Flag wieder
  auf 0 gesetzt.
- **BROM auslesen.** Über FEL ist `0x0` nicht lesbar (hängt den Bus auf, §6), **aus einem
  laufenden U-Boot heraus aber schon** — `sunxi_mem_map` bildet `0x0`–`0x40000000` als
  Device-Speicher ab (`arch/arm/mach-sunxi/board.c:48`). `md.l 0 0x10` liefert echten BROM-Code:

```
00000000: ea00000f   b    +0x44          Reset-Vektor
00000004..1c: eafffffe                   die sieben Ausnahmevektoren, je Endlosschleife
00000024: e3a00941   mov  r0, #0x104000
00000028: e3a01949   mov  r1, #0x124000
0000002c: e3a02000   mov  r2, #0
00000030: e8a00004   stmia r0!, {r2}
00000034: e1500001   cmp  r0, r1
00000038: bafffffc   blt  -0x10
```

  Der BROM nullt beim Start SRAM von `0x104000` bis `0x124000` — unabhängige Bestätigung, dass
  SRAM A2 genau dieser 128-KiB-Bereich ist (passend zu `spl_addr = 0x104000` und
  `thunk_addr = 0x123a00`).

  **Damit ist BROM-Reverse-Engineering machbar**: `md.l 0 0x2000` in ein `tio`-Mitschnitt
  (`CONFIG_CMD_TFTPPUT` fehlt im Bau, Netzausgabe geht also nicht). Dort steht die
  FEL-Einstiegsbedingung — und dort stünde auch die Hotplug-Mailbox, an der die vier früheren
  RMR-Rückwege scheiterten. Für den FEL-Boot brauchen wir sie dank der Falltür nicht mehr;
  aufgehoben als Weg, das Stromziehen loszuwerden.

## 18. Der Rest: `env_init()` scheitert im FEL-Boot — und U-Boot warnt davor selbst

Ab hier lief BL31 vollständig durch und übergab korrekt an `0x4a000000`, U-Boot proper blieb aber
stumm. Nachgewiesen wurde das mit einem 54-Byte-UART-Payload **anstelle** von U-Boots erstem
Befehl: er lief los, die Übergabe kommt also an.

Da `CONFIG_PRE_CONSOLE_BUFFER` alle Ausgaben bis `console_init_r` in den Puffer bei `0x4f000000`
umleitet, war der Frühpfad blind. Also wurde er per Halbierung vermessen — die Sonde
(`precon-dump.bin`, 154 B) gibt zwei Marken und den Pufferinhalt auf UART0 aus und wurde jeweils
über den Einsprung der zu prüfenden Funktion geschrieben:

| Prüfpunkt | Adresse | erreicht |
|---|---|---|
| `board_init_f` | `0x4a02edb8` | **ja** |
| `timer_init` (#18) | `0x4a0816f8` | **ja** |
| `env_init` (#20) | `0x4a054358` | **ja** |
| `serial_init` (#22) | `0x4a049ddc` | nein |
| `checkcpu` (#26) | `0x4a02eda8` | nein |
| `dram_init` (#34) | `0x4a01020c` | nein |
| `relocate_code` | `0x4a00382c` | nein |

Ein Haken in allen Ausnahmevektoren (`0x4a003000` + `0x600` usw., Sprung auf die Sonde) blieb
stumm: **kein Absturz, sondern ein Hänger.**

Damit blieb genau ein Aufruf übrig, und der Maschinencode von `board_init_f` zeigt, warum:

```
4a02ee60: bl    env_init
4a02ee64: cbnz  w0, 0x4a02f3ec      <-- Rueckgabewert != 0 -> INITCALL-Fehlerzweig
4a02ee68..7c:   init_baud_rate (eingebettet)
4a02ee88: bl    serial_init
```

`env_init()` kehrt mit Fehler zurück; `INITCALL` druckt in den unsichtbaren Vorabpuffer und bleibt
stehen. Die Ursache steht in `board/sunxi/board.c` in `env_get_location()`:

```c
	switch (sunxi_get_boot_device()) {
	case BOOT_DEVICE_MMC1: ... case BOOT_DEVICE_MMC2: ... return ENVL_MMC;
	case BOOT_DEVICE_BOARD:      /* FEL */
		break;                   /* faellt durch */
	}
	/*
	 * If we come here for the first time, we *must* return a valid
	 * environment location other than ENVL_UNKNOWN, or the setup sequence
	 * in board_f() will silently hang. ...
	 * For all defconfigs this is either FAT or UBI, or NOWHERE ...
	 */
	if (prio == 0) {
		if (IS_ENABLED(CONFIG_ENV_IS_IN_FAT)) return ENVL_FAT;
		if (IS_ENABLED(CONFIG_ENV_IS_IN_UBI)) return ENVL_UBI;
	}
	return ENVL_UNKNOWN;
```

Unser Bau hat **nur** `CONFIG_ENV_IS_IN_MMC=y` — weder FAT noch UBI noch NOWHERE. Beim FEL-Boot ist
das Bootgerät `BOOT_DEVICE_BOARD`, der `switch` fällt durch, der Rückfall greift nicht,
`ENVL_UNKNOWN` kommt heraus. Der Kommentar benennt das Symptom wörtlich („will silently hang"); die
Lücke ist upstream und trifft jede Konfiguration, die ihre Umgebung ausschließlich in MMC hält.

Zweiter, gleichartiger Punkt: `mmc_get_env_dev()` leitet die Gerätenummer ebenfalls aus dem
Bootgerät ab und fällt sonst auf `CONFIG_ENV_MMC_DEVICE_INDEX` zurück — das stand auf `0`, die eMMC
ist aber Gerät `1` (`mmc@4022000`). Ohne Korrektur lädt der FEL-Boot die Default-Umgebung statt der
echten, und das Einschaltgate verlangt dann jedes Mal einen Tastendruck.

## 19. Die Reparatur

Drei Änderungen in U-Boot, drei in sunxi-tools. Patches liegen in
`analyse/release/arbeit/r0-fel/patches/`.

### U-Boot (`0001-uboot-h713-fel-boot.patch`)

| Datei | Änderung |
|---|---|
| `arch/arm/cpu/armv8/fel_utils.S` | H713-Zweig von `return_to_fel()` legt vor dem `eret` eine minimale AArch64-EL3-Vektortabelle nach `0x48000000` und setzt `VBAR_EL3`. Slot `+0x600` liest ein 64-Bit-Postfach bei `+0x700` und springt dorthin; leeres Postfach parkt. |
| `board/sunxi/board.c` | `env_get_location()` fällt zusätzlich auf `ENVL_MMC` zurück. |
| `configs/hy310_netboot_gate_defconfig` | `CONFIG_ENV_MMC_DEVICE_INDEX=1`. Wirkt nur im Rückfall, der normale eMMC-Start liefert die 1 ohnehin explizit. |

### sunxi-tools (`0002-sunxi-tools-h713-fel-door.patch`)

| Datei | Änderung |
|---|---|
| `soc_info.h` | Neues Feld `fel_door_addr` samt Begründung. |
| `soc_info.c` | H713 bekommt `.fel_door_addr = 0x48000000`. |
| `fel.c` | Neues `aw_fel_door_request()`; `aw_rmr_request()` nimmt bei gesetztem `fel_door_addr` die Tür statt des RMR. Fehlt die Tür (zu altes U-Boot), gibt es eine Klartextmeldung **statt** eines RMR-Versuchs — der würde das Gerät aufhängen. |

## 20. Ergebnis

```
$ sudo ./sunxi-fel -v uboot u-boot-fel-final.bin
found DT name in SPL header: allwinner/sun50i-h713-hy200-qz713df-a1
=> Executing the SPL... done.
loading image "ARM Trusted Firmware" (45164 bytes) to 0x40000000
loading image "U-Boot" (827192 bytes) to 0x4a000000
loading DTB "allwinner/sun50i-h713-hy200-qz713df-a1" (11744 bytes)
Starting U-Boot (0x40000000).
Store entry point 0x40000000 in the FEL trap door at 0x48000000, and enter AArch64 via smc... done.
```

Ein Befehl, drei Sekunden, Exit 0. Auf der Konsole:

```
U-Boot 2026.07-rc5-g0cab64cb95fc-dirty  Allwinner Technology
CPU:   Allwinner H713 (SUN50I)
Model: HY200 QZ713DF_A1 (Allwinner H713)
DRAM:  1 GiB
Core:  43 devices, 19 uclasses, devicetree: separate
MMC:   mmc@4022000: 1
Loading Environment from MMC... Reading from MMC(1)... OK
In:    serial / Out: serial / Err: serial
gate: off (h713_gate=0, GP5 00000000)
...
Hit any key to stop autoboot: 0
```

Der FEL-Start ist damit vom eMMC-Start nicht mehr zu unterscheiden — inklusive echter Umgebung von
der eMMC. **Auf die eMMC wurde nichts geschrieben**; alles ist flüchtig und nach einem Stromzyklus
verschwunden.

Abschlussabbild: `analyse/release/arbeit/r0-fel/u-boot-fel-final.bin` (918.857 B, Release-BL31 —
das Diagnose-BL31 mit `LOG_LEVEL=40` steckt nur in `bl31-info.bin` und in den
`uboot-v4-*`-Bauverzeichnissen, nicht im Quellbaum).

## 21. Was noch offen ist

- **`doku/20-flashen-und-recovery.md` §Recovery ist überholt.** Dort steht „Nicht `sunxi-fel uboot`
  benutzen." Das galt für den alten Stand; mit den Patches ist genau das der empfohlene Weg. Sollte
  jemand mit Schreibrecht auf `doku/20` korrigieren.
- **`CONFIG_ENV_MMC_DEVICE_INDEX=1` steht nur in `hy310_netboot_gate_defconfig`.** Die anderen
  H713-Defconfigs (`hy310_qz713_v3_1`, `hy310_netboot`, `hy310_host`) brauchen dieselbe Zeile,
  sonst laden sie im FEL-Boot die Default-Umgebung.
- **Der Bus-Hänger bei `0x05000000` (§6) verdient einen Platz in der Doku** — er kostet einen
  Stromzyklus und ist leicht versehentlich auszulösen, weil H616-Adressen für den H713 naheliegen.
- **BROM-Auszug** (§17) wäre der Weg, FEL ohne Stromziehen auszulösen. `md.l 0 0x2000` am
  U-Boot-Prompt in einen `tio`-Mitschnitt, dann die FEL-Einstiegsbedingung suchen.
- **Nächster Schritt laut Auftrag:** das PC-Skript `hy310-fel-install` (Paket R0). Die dafür
  nötige Sequenz ist jetzt ein einziger `sunxi-fel uboot`-Aufruf.
