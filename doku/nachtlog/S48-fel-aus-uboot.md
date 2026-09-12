# FEL aus dem laufenden U-Boot heraus — was das BROM des H713 liest und was nur Boot0 liest

Stand: 11.09.2026. Rein statische Analyse; das Gerät wurde nicht angefasst, im Projektbaum wurde nichts geschrieben.
Arbeitsverzeichnis des Agenten war ein Kratzverzeichnis; die Disassembler-Ausschnitte liegen jetzt in `analyse/release/arbeit/r0-fel/s48-dis/`, der SPL-Vorschlag in `analyse/release/arbeit/r0-fel/spl-efex-check.S`.
(`bin/` Kopien, `dis/` Disassembler-Ausschnitte, `d.py`/`xref.py` Helfer des Vorgängers, `spl-efex-check.S` Vorschlag).

## Antwort

**Ja, der Mechanismus existiert und ist im Hersteller-Code lückenlos belegt: `0x07090108` (RTC-GP2) := `0x5aa5a55a`, dann Watchdog-Reset; beim nächsten Start springt der Bootloader nach `0x20` in den FEL-Einstieg des BROM.**
**Der Leser dieses Flags ist aber nachweislich der Hersteller-Boot0 (der SPL), nicht nachweislich das BROM — ob das BROM des H713 GP2 selbst auswertet, kann ich ohne BROM-Abbild nicht belegen, und die Indizien sind gemischt.**
**Für unser Gerät heißt das: mit unserem eigenen SPL auf LBA 16 führt `mw.l 0x07090108 0x5aa5a55a; reset` heute höchstwahrscheinlich nur zu einem normalen Neustart (der Versuch aus S44 §17 lief außerdem auf dem falschen Register GP7); sicher wird der Weg erst, wenn unser SPL die zwölf ARM32-Wörter des Boot0-Checks selbst ausführt — das ist unabhängig vom BROM und deckt auch den Fall „LBA 16 kaputt" ab, weil das BROM dann den Hersteller-Boot0 auf LBA 256 lädt, der denselben Check hat.**

Sicherheit: Boot0-Ebene **belegt** (Code gelesen, identisch mit dem Abzug vom Gerät). BROM-Ebene **offen**. Das Register selbst, die Konstante, der Reset-Weg und die Sprungadresse sind belegt.

## 1. Der Mechanismus, wie der Hersteller ihn baut

Drei Stufen, jede mit eigenem Register:

| Stufe | Wer schreibt | Register | Wert | Wer liest |
|---|---|---|---|---|
| Linux `reboot efex` | RTC-Treiber `reboot_callback` (Stock-Kernel) | RTC-GP6 `0x07090118` (DT: `gpr_cur_pos = 6`) | `0x5a` (`str2flag("efex")`) | Hersteller-U-Boot |
| Hersteller-U-Boot | `rtc_get_bootmode_flag()` sieht `0x5a` → löscht GP6 → `sunxi_board_run_fel()` | RTC-GP2 `0x07090108` | `0x5aa5a55a` | Hersteller-Boot0 |
| Hersteller-Boot0 | `rtc_probe_fel_flag()` → `rtc_clear_fel_flag()` → `boot0_jmp(0x20)` | — | — | BROM-FEL-Einstieg |

Reset-Weg des Herstellers: `sunxi_board_restart()` wartet 500 × 1 ms und schreibt `0x16aa0001` nach `0x02051008` (WDT_SOFT_RST, Schlüssel `0x16aa`). Unser `reset` läuft über PSCI in TF-A `sunxi_system_reset()` und schreibt `0x16aa0001` nach `0x02051010` und `0x02051014` (`plat/allwinner/common/sunxi_native_pm.c:112-120`). Beides ist ein Chip-Reset über das Watchdog-Modul; die RTC-Domäne wird davon nicht gelöscht — belegt für GP7 durch den Fastboot-Marker (`board/sunxi/board.c:61-76`) und den Chainload-Marker (`mainline/docs/flash.md:609ff`, Bench 06.08.), die beide genau diesen Reset überstehen. GP2 liegt im selben Registerblock.

Was nach dem Sprung passiert: Boot0 setzt vorher den CPU-Takt auf 24 MHz zurück (`0x02001500 := 0x301`, `0x02001510 := 0`, `0x02001520 := 0`), schaltet MMU/Caches ab, wartet 10 ms und springt mit `bx r0`, r0 = `0x20`, im ARM-Zustand ins BROM. Dort liegt der FEL-Einstieg: dieselbe Adresse, die `sunxi-tools/fel-sdboot.S:46,72-76` seit dem A10 benutzt (`BROM_ENTRY_LOW = 0x00000020`, gewählt bei `SCTLR.V = 0`; S44 hat `SCTLR = 0x00c51838` gemessen, V ist 0). Die von S44 §17 aus U-Boot gelesenen BROM-Wörter passen dazu: `0x00` Reset-Vektor (`b 0x44`), `0x04`–`0x1c` sieben Endlosschleifen-Vektoren, ab `0x24` die Schleife, die SRAM A2 `0x104000`–`0x124000` nullt — das ist Code hinter dem FEL-Einstieg, nicht der Reset-Pfad (der biegt nach `0x44` ab). Das Wort bei `0x20` selbst steht nicht im S44-Bericht.

## 2. Belege

### 2.1 Gelesen und belegt

**(a) Boot0 liest GP2 und springt nach 0x20.** Datei `re/vendor/HY310/extracted/boot0_sdcard.fex` (Kopie `bin/`), Thumb-2, Basis `0x104000`. Der Code ist byteidentisch mit dem Abzug vom Gerät `re/device-dumps/lba256.bin` (= `lba16.bin`, sha256 `af5b0b08…`): Unterschiede nur im Kopf (Prüfsumme `0xc`–`0xf`, Byte `0x4f`, Bytes `0x94`–`0x97`), kein Byte im Code. Vollständige Ausschnitte in `dis/02-vendor-boot0.txt`, `dis/10-boot0-main.txt`, `dis/14-boot0-helpers.txt`.

`main` @`0x109a64` (Datei-Offset `0x5a64`):
```
00109aa2  bl   0x10506c        ; set_pll (schreibt 0x07090160, 0x070901f4, 0x07010340)
00109aa6  cbnz r0, 0x109ab2    ; Fehler -> FEL-Pfad
00109aa8  bl   0x105ac0        ; rtc_probe_fel_flag()
00109aac  cbz  r0, 0x109ad4    ; 0 -> normal weiter (enable_jtag, DRAM, boot-pkg ...)
00109aae  bl   0x105b38        ; rtc_clear_fel_flag()
00109ab2  bl   0x10516e        ; boot0_clear_env() (leer: movs r0,#0; bx lr)
00109ab6  bl   0x105370        ; Takte zurück: [0x02001510]=0 [0x02001520]=0 [0x02001500]=0x301
00109aba  bl   0x104f7a        ; MMU/Caches aus, ICIALLU, BPIALL
00109abe  movs r0, #0xa
00109ac0  bl   0x104ee0        ; mdelay(10)
00109ac4  movs r0, #0x20
00109ac6  bl   0x104fb4        ; boot0_jmp: BPIALL; bx r0   -> BROM 0x20, ARM-Zustand
```
`rtc_probe_fel_flag` @`0x105ac0`: druckt `rtc[0..5]`, dann
```
00105ade  movs r0, #2
00105ae0  bl   0x105aac        ; rtc_read_data(2) = [0x07090100 + 2*4] = [0x07090108]
00105ae4  ldr  r3, =0x5aa5a55a ; Literal bei 0x105b20
00105ae6  cmp  r0, r3
00105ae8  bne  0x105af4
00105aea  ldr  r0, ="eraly jump fel\n"
00105af0  movs r0, #1 ; return 1
00105af4  ldr  r3, =0x5aa55aa5 ; Crashdump-Handshake: GP2:=0x5aa55aa6, warten bis 0x5aa55aa7, "carshdump mode , jump fel"
```
`rtc_clear_fel_flag` @`0x105b38`: `rtc_write_data(2, 0)`; `dsb; isb`; solange rücklesen, bis `[0x07090108] == 0`.
`rtc_write_data`/`rtc_read_data` @`0x105a94`/`0x105aac`: Basis `0x07090100` (Literale `0x105aa8`, `0x105abc`), Index × 4. Alle RTC-Literale der Datei: `0x07090160` (Offset `0x1140`), `0x07090100` (`0x1aa8`, `0x1abc`), `0x5aa5a55a` (`0x1b20`), `0x5aa55aa5`/`aa7`/`aa6` (`0x1b28`–`0x1b30`). Sonst nichts — Boot0 kennt genau diesen einen FEL-Auslöser.

**(b) Hersteller-U-Boot setzt GP2 und resettet.** `re/vendor/HY310/extracted/u-boot.fex` (identisch mit dem `u-boot`-Eintrag in `boot_package.fex`, Offset `0x800`), Thumb-2, Basis `0x4a000000`. Ausschnitte `dis/01-vendor-uboot.txt`, `dis/13-vendor-uboot-bootmode.txt`.

- `rtc_set_fel_flag` @`0x4a001f14`: `[0x07090108] := 0x5aa5a55a` mit `dmb/dsb/isb` und Rücklese-Schleife (Literale `0x4a001f34`, `0x4a001f38`).
- `sunxi_board_run_fel` @`0x4a002bae`: `bl rtc_set_fel_flag; bl 0x4a002b76 (Flash/Board-Exit); bl sunxi_board_restart(0)`.
- `sunxi_board_restart` @`0x4a001a14`: 501 × `udelay(1000)`, dann `[0x02051008] := 0x16aa0001`, Endlosschleife.
- Aufrufer von `sunxi_board_run_fel`: `do_efex` @`0x4a00cc6c` (cmd_tbl-Eintrag `efex`, „run to efex", Datei-Offset `0x84430`), die Bootmode-Auswertung @`0x4a0031e2`, `SUNXI_UPDATE_NEXT_ACTION_REUPDATE` @`0x4a002c04`, und drei weitere (`0x4a00e4e6`, `0x4a042180`, `0x4a044b78`).
- Bootmode-Auswertung @`0x4a003116ff`: `bl 0x4a001f60` (liest GP6 `0x07090118`), `bl 0x4a001f3c` mit r0=0 (löscht GP6), `subs r0,#0x5a; cmp r0,#6; tbb` — Index 0 (= `0x5a`, efex) landet bei `0x4a0031e2: bl sunxi_board_run_fel`.
- U-Boot enthält das Literal `0x07090108` **nur einmal** (im Setzer). Der Hersteller-U-Boot löscht GP2 nie — das Löschen ist Sache von Boot0 (und fes1, siehe (d)).

**(c) Stock-Kernel schreibt bei `reboot efex` nur `0x5a` nach GP6.** `re/vendor/HY310/extracted/vmlinux.elf` (arm32, mit Symbolen), `dis/12-vendor-kernel-reboot-efex.txt`: `reboot_callback` @`0xc06ec1f4` → `str2flag(cmd)` @`0xc06ebef0` (Tabelle @`0xc0ebc624`: `debug=0x59, efex=0x5a, boot-resignature=0x5b, recovery=0x5c, boot-recovery=0x5c, sysrecovery=0x5d, usb-recovery=0x5e, bootloader=0x5f, uboot=0x60`) → `str r5, [*0xc15467c4]`. Ziel laut Stock-DT (`bootpkg-full.dts:2002-2015`, `allwinner,sun50iw12p1-rtc`): `gpr_offset = 0x100, gpr_len = 8, gpr_cur_pos = 6` → `0x07090118`. Meldung: „store flag '%s' (0x%x) in RTC General-Purpose-Register". Der Kernel kennt `0x5aa5a55a` nicht; der Weg Linux → FEL geht zwingend über den Hersteller-U-Boot.

**(d) fes1 — das FEL-Hilfsprogramm — prüft und löscht das Flag ebenfalls.** `re/vendor/HY310/extracted/fes1.fex`, Thumb-2, Lauf-Adresse `0x10c000` (Kopf `0x20`), `dis/11-fes1-main.txt`. `main` @`0x10ee7c`: „fes begin commit", `sunxi_board_init`, „beign to init dram", DRAM-Init, dann
```
0010eeb2  bl   0x10d500        ; rtc_probe_fel_flag()  (gleicher Code wie Boot0, Literale 0x10d560ff)
0010eeb6  cbz  r0, 0x10eebc
0010eeb8  bl   0x10d578        ; rtc_clear_fel_flag()  (GP2 := 0, rücklesen)
```
fes1 läuft **im** FEL-Modus, nachdem `sunxi-fel`/PhoenixSuit es geladen hat. Dass es das Flag löscht, ist nur nötig, wenn man mit gesetztem Flag in FEL ankommen kann — siehe §3.

**(e) Sonstige Fundstellen der Konstante.** In `boot_package.fex` erscheint `0x5aa5a55a` ein zweites Mal im `optee`-Eintrag (Offset `0xd940`, Thumb-2, Basis `0x48600000`). Der umgebende Code ist der HDCP-Schlüsselhandler (`sunxi_deal_hdcp_key`); ich habe ihn nicht weiter angesehen und nichts daraus übernommen. `toc0.fex`/`toc1.fex` sind 8-Byte-Platzhalter (kein Secure Boot), `sunxi.fex` ist ein DTB, `usbtool.fex` ein Windows-PE (Host-Seite), `aultools.fex`/`aultls32.fex`/`cardtool.fex`/`usbtool_crash.fex` enthalten weder `0x5aa5a55a` noch `0x07090108`.

**(f) Unser eigener Code.** `mainline/external/u-boot`: kein Treffer für `efex`, `5aa5a55a` oder einen FEL-Rückkehr-Flag in `arch/arm/mach-sunxi`, `board/sunxi`, `drivers/sysreset`; `sunxi-tools` kennt nur den Watchdog-Reset (`fel.c:1200`, für den H713 ohne Eintrag) und `fel-sdboot.S`. Unser SPL-Stub (`arch/arm/include/asm/arch-sunxi/boot0.h`, ARM32-Wörter aus `rmr_switch.S`) sichert `fel_stash` und geht per RMR nach AArch64 — er liest keine RTC-Register. Unser U-Boot benutzt GP7 (`0x0709011c`) für Fastboot/Prompt/Chainload, GP5 für das Einschaltgate; GP2/GP3/GP6 gelten als „Stock-belegt" (`board.c:1065`, TF-A `sunxi_power.c:30`, `doku/103` §2.1). Kein Code von uns schreibt GP2.

### 2.2 Analogieschluss (andere SoCs, Sekundärquellen)

- Die Adresse `0x20` als BROM-FEL-Einstieg gilt für alle Allwinner-SoCs seit dem A10 (`fel-sdboot.S`); Boot0 des H713 benutzt genau sie.
- Mainline-U-Boot, RFC „sunxi: rework pinctrl and add T113s support" (lists.denx.de, Juni 2023, Seite `2023-June/520523.html`; nur als Suchmaschinen-Auszug lesbar, Abruf schlug fehl): „The magic number 0x5AA5A55A is poked into RTC's GP_DATA_REG[2], and then reset; **SPL clears that magic number and then does an early branch to BROM+0x0020** — exactly what Allwinner's fork does." Also auch dort: eine SPL-Implementierung, keine Aussage über das BROM.
- Allwinner-Foren/Docs beschreiben `reboot efex` und das U-Boot-Kommando `efex` als Standardweg; niemand, den ich finden konnte, behauptet mit Beleg, dass ein BROM das GP2-Flag liest. Die linux-sunxi-Seiten `BROM`/`FEL` waren nicht abrufbar (403).

### 2.3 Vermutung

- **Für BROM-Auswertung spricht:** fes1 löscht das Flag im FEL-Modus (2.1 d). Im Boot0-Pfad ist das Flag schon gelöscht, bevor FEL beginnt; das Löschen in fes1 hat nur Sinn, wenn man mit gesetztem Flag in FEL landen kann — etwa weil das BROM es liest, ohne es zu löschen. Es kann aber ebenso gut generischer spl-pub-Code aus Vorsicht sein.
- **Dagegen oder neutral:** Boot0 trägt den Check selbst, obwohl er beim BROM-Check überflüssig wäre (aber: derselbe Code läuft auf vielen SoCs). Der Hersteller-Kernel geht nicht direkt auf GP2, sondern über den U-Boot — auch das ist neutral, weil der U-Boot ohnehin `sunxi_board_restart` braucht.
- Netto: **nicht entscheidbar ohne BROM-Abbild.** Ich würde eher darauf wetten, dass das BROM des H713 GP2 **nicht** liest, weil alle drei Hersteller-Stufen die Auswertung selbst tragen und die einzige Mainline-Implementierung (T113) ebenfalls im SPL sitzt — aber das ist eine Wette, kein Beleg.

## 3. Was dagegen spricht oder unklar bleibt

1. **Kein BROM-Abbild.** Es gibt nur die 16 Wörter aus S44 §17. Damit ist die Kernfrage „liest das BROM GP2?" offen. Ein Auszug (`md.l 0 0x2000` aus einem laufenden U-Boot in einen `tio`-Mitschnitt, S44 §21) ist die Empfehlung, nicht Teil dieser Analyse. Über FEL ist `0x0` nicht lesbar (Bus-Hänger, S44 §6).
2. **Unser Gerät hat unseren SPL auf LBA 16.** Das BROM lädt ihn, er liest GP2 nicht, das Flag bleibt wirkungslos und stehen. Der Hersteller-Boot0 auf LBA 256 kommt nur zum Zug, wenn LBA 16 ungültig ist. Der Chainload über GP7 = `0x001db007` erreicht Boot0 heute nicht mehr (RMR-Variante landet im BROM-Reset, `flash.md:625-636`); die frühere `eret`-Variante hätte Boot0 in AArch32-EL1 laufen lassen — der GP2-Check und der Sprung nach `0x20` liegen vor dem RMR-Problem, ob das BROM-FEL von EL1 aus sauber initialisiert, ist ungetestet (die FEL-*Schleife* läuft nach S44 §12/§14 in EL1 nachweislich).
3. **Der S44-§17-Versuch war nicht der richtige Test.** `mw.l 0x0709011c 0x5aa5a55a` beschreibt GP7, nicht GP2. Er sagt weder über Boot0 noch über das BROM etwas aus. GP2 = `0x07090108` wurde nie mit dem Flag beschrieben und resettet.
4. **RTC-GP-Register überleben keinen Stromzyklus** (fel-notes: nach Netz-aus/FEL-Taste standen `0x07090100`–`0x108` auf 0). Das macht ein hängengebliebenes Flag ungefährlich, heißt aber auch: Flag setzen und Reset müssen ohne Netzunterbrechung erfolgen.
5. **GP2 ist beim Hersteller mehrfach belegt** (`2` = Standby laut `doku/103`, Crashdump-Handshake `0x5aa55aa5..7`). Boot0 reagiert nur auf exakte Werte; `2` löst nichts aus. Unser Stack schreibt GP2 nie.
6. **Watchdog-Layout.** Hersteller-U-Boot resettet über `+0x08` (SOFT_RST), unser TF-A über `+0x10/+0x14`; fel-notes berichten, dass Schreibversuche ohne Schlüssel `0x16aa` wirkungslos blieben. Unser `reset` funktioniert nachweislich, das reicht.

## 4. Wie man es gefahrlos prüfen würde (beschrieben, nicht ausgeführt)

Voraussetzung: Konsole offen, USB-Kabel für `sunxi-fel` griffbereit, keine Schreibzugriffe auf die eMMC. Jeder Schritt hat einen Rückweg; Stromzyklus löscht im schlimmsten Fall alle GP-Register.

**Schritt 0 — Ausgangslage lesen** (kein Risiko):
`md.l 0x07090100 8` am U-Boot-Prompt. Erwartung GP2 = 0 oder `2`; Wert notieren.

**Schritt 1 — Schreibbarkeit** (kein Risiko, aus FEL schon belegt für `0x07090108`):
`mw.l 0x07090108 0x5aa5a55a; md.l 0x07090108 1` → muss `5aa5a55a` zeigen. Rückweg: `mw.l 0x07090108 0`.

**Schritt 2 — BROM-Test** (Kosten: ein Stromzyklus, falls es in FEL geht und man nicht per USB zurück will):
`reset`. Danach genau eine von zwei Beobachtungen:
- USB-Gerät `1f3a:efe8` erscheint, Konsole schweigt → **das BROM liest GP2.** Dann `sunxi-fel readl 0x07090108` (belegt sicher): steht das Flag noch, löscht das BROM nicht → `sunxi-fel writel 0x07090108 0`, dann Watchdog-Reset oder Stromzyklus. Ab dann ist `mw.l 0x07090108 0x5aa5a55a; reset` der gesuchte Weg — auch bei kaputter eMMC.
- SPL-Banner, normaler Boot → das BROM (oder unser SPL) ignoriert GP2. Am Prompt `md.l 0x07090108 1`: steht `5aa5a55a` noch, hat niemand gelesen → `mw.l 0x07090108 0`. Ergebnis „BROM liest nicht" — sofern der Reset-Weg dem Hersteller-Reset gleichwertig ist (Restunsicherheit: SOFT_RST vs. Timeout-Reset).

**Schritt 3 — Boot0-Ebene ohne BROM-Annahme** (wenn Schritt 2 negativ war):
Den Check in unseren SPL-Stub aufnehmen (§5) und bauen — nichts flashen. Vorprüfung ohne eMMC-Schreibzugriff, aus einer frischen FEL-Sitzung: `sunxi-fel writel 0x07090108 0x5aa5a55a` (belegt sicher), dann `sunxi-fel spl <neuer SPL>`. Erwartung: der Stub sieht das Flag, löscht es und springt nach `0x20`; das BROM nullt SRAM A2, initialisiert USB neu — die Sitzung bricht ab, das Gerät meldet sich erneut als `1f3a:efe8`, `sunxi-fel readl 0x07090108` liefert 0. Das zeigt, dass Sprung und Wiedereinstieg funktionieren, ist aber nicht der Kaltstart-Zustand (Eintritt aus der FEL-Schleife statt aus dem Reset-Pfad). Beweiskräftig wird es erst mit dem Abbild auf LBA 16 und `mw.l 0x07090108 0x5aa5a55a; reset` am Prompt — das ist ein eMMC-Schreibzugriff und Marcos Entscheidung.
Rückweg, falls ein neuer SPL auf LBA 16 in FEL fällt und dort bleibt: `sunxi-fel writel 0x07090108 0` oder Stromzyklus; der SPL löscht das Flag aber selbst vor dem Sprung (Rücklese-Schleife wie Boot0).

**Schritt 4 — Ausdauer:** dreimal hintereinander `mw.l …; reset` → FEL → `sunxi-fel uboot …` → Prompt, ohne Stromzyklus. Erst dann in `doku/20` als Weg aufnehmen.

## 5. Vorschlag für unseren SPL (nicht angewendet)

Zwölf ARM32-Wörter, selbsttragend (eigene Literale, Sprung darüber), einzufügen in `boot0.h` **nach** dem `fel_stash`-Sicherungsblock (`str lr, [r0, #16]`) und **vor** `ldr r1, [pc, #52]`; dort verschieben sie keine fremden PC-relativen Abstände (`adr r0` liegt davor, die RVBAR-Literale danach behalten ihren Abstand). Quelle `spl-efex-check.S`, mit `llvm-mc` assembliert:

```
	.word	0xe59f2028	// ldr r2, =0x07090108      RTC GP2
	.word	0xe5923000	// ldr r3, [r2]
	.word	0xe59f1024	// ldr r1, =0x5aa5a55a      eFEX-Flag
	.word	0xe1530001	// cmp r3, r1
	.word	0x1a000008	// bne skip
	.word	0xe3a03000	// mov r3, #0
	.word	0xe5823000	// 1: str r3, [r2]          loeschen ...
	.word	0xf57ff04f	// dsb sy
	.word	0xe5921000	// ldr r1, [r2]
	.word	0xe1510003	// cmp r1, r3
	.word	0x1afffffa	// bne 1b                   ... bis es ruecklesbar ist (wie boot0)
	.word	0xe3a0f020	// mov pc, #0x20            BROM-FEL-Einstieg, ARM-Zustand
	.word	0x07090108
	.word	0x5aa5a55a
	// skip:
```
Gegenüber Boot0 entfällt das Zurücksetzen der Takte, weil der Stub vor jeder PLL-Änderung läuft — der Zustand ist dann exakt der, in dem auch `fel-sdboot` springt. Der Stub läuft nur bei Kaltstart durch das BROM; beim `sunxi-fel spl`-Weg wird er ebenfalls durchlaufen, dort ist GP2 aber normalerweise 0.

## 6. Nebenbefunde

- **GP2 ist der Hersteller-Kanal U-Boot → Boot0, GP6 der Kanal Kernel → U-Boot.** Die Bootmode-Tabelle des Stock-Kernels (`debug 0x59 … uboot 0x60`) wird vom Hersteller-U-Boot per `tbb` auf sieben Aktionen abgebildet; `0x5f bootloader`/`0x60 uboot` sind Fastboot/Prompt-Äquivalente unseres GP7-Protokolls.
- **fes1 initialisiert DRAM und löscht GP2** — wer je `fes1.fex` per `sunxi-fel` lädt, bekommt ein gelöschtes Flag als Nebeneffekt.
- **Crashdump-Modus:** GP2 = `0x5aa55aa5` lässt Boot0 in einer Handshake-Schleife warten (`0x5aa55aa6` setzen, auf `0x5aa55aa7` warten), dann FEL. Sollte nie versehentlich geschrieben werden — Boot0 hinge ohne Gegenstelle.
- **Hersteller-U-Boot „auto_fel"** (`/soc/target auto_fel = 1` in sys_config) → `do_fel_from_boot`: U-Boot hebt im Normalstart USB0 als Gerät an und wartet auf das PC-Brenntool („probe MP tools from boot"). Ein weiterer FEL-freier Weg des Herstellers, hier nicht weiter verfolgt.
- **BROM-Wörter aus S44 §17 neu gelesen:** die SRAM-Nullschleife bei `0x24`–`0x38` gehört zum FEL-Einstieg `0x20`, nicht zum Reset-Pfad (`0x00: b 0x44`). Sie erklärt, warum Boot0 vor dem Sprung nichts aufräumen muss — das BROM nullt SRAM A2 selbst. Das Wort bei `0x20` fehlt im Bericht; beim nächsten `md.l 0 0x10` darauf achten.
- **Stock-Boot0 und Geräte-Abzug** unterscheiden sich nur im Kopf (Prüfsumme, Byte `0x4f`, `0x94`–`0x97` = vom Flashtool gesetzte Felder), `boot0_nand.fex` ist ein anderer Bau (28 646 Byte Unterschied).
- **Für die Doku:** `doku/20` §Recovery und S44 §17 sollten den GP7-Versuch als „falsches Register" markieren, sonst gilt der Weg fälschlich als widerlegt.

## Dateien in diesem Verzeichnis

| Datei | Inhalt |
|---|---|
| `dis/01-vendor-uboot.txt`, `02-vendor-boot0.txt`, `03-geraetestand.txt` | Vorgänger: efex-Kommando, Boot0-Kernfunktionen, Hashes |
| `dis/10-boot0-main.txt` | Boot0 `main` mit FEL-Entscheidung |
| `dis/11-fes1-main.txt` | fes1 `main` mit Flag-Check |
| `dis/12-vendor-kernel-reboot-efex.txt` | Stock-Kernel `reboot_callback`, `str2flag`, Tabelle |
| `dis/13-vendor-uboot-bootmode.txt` | Hersteller-U-Boot Bootmode-Auswertung GP6 → `sunxi_board_run_fel` |
| `dis/14-boot0-helpers.txt` | `boot0_jmp`, Taktrücksetzung, Barrieren |
| `spl-efex-check.S` / `.o` | Vorschlag §5, assembliert |
| `bin/` | Kopien der Hersteller-Binaries (nichts davon verlässt das Verzeichnis) |

---

## Nachtrag 11.09.2026, 11:20 — umgesetzt und am Gerät bestätigt

**Schritt 2 (BROM-Test):** `mw.l 0x07090108 0x5aa5a55a; reset` am Prompt → normaler Neustart. **Das BROM des H713 liest
GP2 nicht.** Damit ist die offene Kernfrage beantwortet.

**Schritt 3 (FEL-Vortest ohne eMMC-Schreibzugriff):** Flag per `sunxi-fel writel` gesetzt, neuen SPL per `sunxi-fel spl`
gestartet → USB bricht mitten im Aufruf ab (`usb_bulk_send ERROR -4`), das Gerät meldet sich frisch als FEL, `version`
antwortet, GP2 = 0. Gegenprobe mit `0x11111111` → SPL läuft regulär durch (Banner „Trying to boot from FEL"), kehrt nach
FEL zurück, Wert steht noch. **Beide Zweige verhalten sich wie vorhergesagt.**

**Schritt 4 (auf LBA 16):** Teil A des Abbilds v0.4/v0.5 geschrieben. Erster Versuch: 1 von 4 `run fel` bootete
durch. Ursache aus dem Hersteller-Code: `rtc_set_fel_flag` schreibt **in einer Schleife bis der Wert zurücklesbar
ist**, und `sunxi_board_restart` wartet **500 ms** vor dem Watchdog — RTC-Register hängen an einem langsamen Takt, ein
einzelner `mw.l` direkt vor `reset` kann verpuffen. Behoben (Commits `37312bd8ab8`, `799abe93d94` = `uboot-h713/0031`,
`0032`): `fel=while itest.l *0x07090108 != 0x5aa5a55a; do mw.l ...; done; sleep 1; reset`, und der Stub liest das Flag
doppelt. **Danach 5 Durchgänge ohne Stromzyklus, je 8–10 s bis zur frischen USB-Anmeldung, GP2 jedes Mal 0, und
`sunxi-fel uboot` funktioniert aus dem so erzeugten FEL** — dieser Zustand ist sauberer als der, den ein
zurückkehrender `sunxi-fel spl` hinterlässt (dort `ERROR -7` beim zweiten Aufruf, S44).

Der Stub im Release-SPL (16 Wörter + 2 Literale, `arch/arm/include/asm/arch-sunxi/boot0.h`, nur `CONFIG_MACH_SUN50I_H713`):
```
e59f2038 e59f1038 e5923000 e1530001 1a00000c e5923000 e1530001 1a000009
e3a03000 e5823000 f57ff04f e5921000 e1510003 1afffffa e3a00020 e12fff10
07090108 5aa5a55a
```
