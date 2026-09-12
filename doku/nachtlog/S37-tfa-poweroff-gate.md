# S37 — TF-A: `poweroff` führt ins Einschalt-Gate (Paket G2 aus Plan 103)

**Stand 09.09.2026, Agent in der Kopie `analyse/boot/arbeit/g2-tfa/`.** Auftrag
[`g2-tfa/AUFTRAG.md`](../../analyse/boot/arbeit/g2-tfa/AUFTRAG.md), Regeln
[`REGELN.md`](../../analyse/boot/arbeit/REGELN.md), Plan [`103`](../103-plan-einschaltgate.md) §2.3.
Geliefert: `analyse/boot/arbeit/g2-tfa/patches/0001-tfa-h713-poweroff-enters-the-boot-gate.patch`
(unified diff, `-p1`, Pfade `a/plat/allwinner/…` `b/…`), erzeugt mit `diff -u` gegen
`mainline/external/arm-trusted-firmware` (HEAD `47ee829f7`). **Eine Datei**, `plat/allwinner/sun50i_h713/sunxi_power.c`,
+82 Zeilen. Der Originalbaum wurde nur gelesen (byteweise nachgeprüft), **nicht gebaut**, **kein Board**.

Gegenproben: `patch -p1 --dry-run` gegen den echten Baum — sauber, kein Fuzz; Anwendung auf eine Wegwerfkopie ergibt
byteidentisch die geänderte Kopie. Syntax und Typen mit `gcc -fsyntax-only -nostdinc` gegen die **echten** TF-A-Header
(`include/`, `include/lib/libc`, `include/arch/aarch64`, `plat/allwinner/*/include`, `lib/libfdt`) geprüft, einmal mit
`-Wall -Wextra -Wmissing-prototypes` und `LOG_LEVEL=40`, einmal mit `LOG_LEVEL=20` (Release): keine Meldung aus unserer
Datei, dieselbe Ausgabe wie beim unveränderten Original. Das ersetzt keinen Querbau mit clang, prüft aber alles außer
Zielarchitektur und Linkerei.

## 1. Die beiden Fragen aus dem Auftrag — beantwortet

### 1.1 Welcher Reset-Pfad resettet auf H713 wirklich?

**Der schlüsselgeschützte Haupt-Watchdog bei `0x02051000` — also genau der Pfad, den `sunxi_system_reset()` in
`plat/allwinner/common/sunxi_native_pm.c:108-132` heute schon nimmt.** Er ist doppelt am Gerät belegt:

| Beleg | Was er zeigt |
|---|---|
| U-Boot baut mit `CONFIG_SYSRESET=y`/`CONFIG_SYSRESET_PSCI=y` (beide Defconfigs) und hat einen `psci`-Knoten (`arm,psci-1.0`) im Kontroll-DTB (`dts/upstream/src/arm64/allwinner/sun50i-h713-hy200-qz713df-a1.dts:87`). **`reset` am U-Boot-Prompt ist damit ein PSCI-`SYSTEM_RESET`-SMC in unser BL31** und läuft durch genau diese Watchdog-Sequenz. Messung M3 (Plan 103 §3): `reset` resettet, und GP5 überlebt ihn. | Der TF-A-Reset funktioniert, **und** RTC-GP überlebt ihn. |
| Messung M6: `reboot` aus Linux → U-Boot-Prompt nach 11 s. Der PSCI-Restart-Handler hat Priorität 129 (`drivers/firmware/psci/psci.c:329`), der Watchdog-Treiber nur 128 (`drivers/watchdog/sunxi_wdt.c:285`) — PSCI gewinnt. Der Kernel-Watchdog trifft ohnehin nichts (falsches Layout, siehe unten). | Derselbe Pfad, aus Linux. |

`sunxi_mmap.h` der Plattform setzt `SUNXI_R_WDOG_BASE = SUNXI_WDOG_BASE = 0x02051000` und `SUNXI_WDOG_KEY = 0x16aa0000`;
`sunxi_native_pm.c` schreibt damit `+0x10 = 0x16aa0001` (CFG, Bit 0 = Systemreset) und `+0x14 = 0x16aa0001` (MODE,
Bit 0 = EN, Bits 7:4 = Intervall = 0 = 0,5 s). Das deckt sich Register für Register mit dem am 07.09. am Gerät
verifizierten Vendor-Layout (CTRL 0x0C Ping 0x14AF, CFG 0x10, MODE 0x14, Intervall 0xB = 16 s). Der
**U-Boot-eigene** `reset_cpu()` (`arch/arm/mach-sunxi/board.c:585-620`) zielt dagegen auf den Timer-Block-Watchdog
ohne Schlüssel und wäre wirkungslos — er ist hier toter Code, weil `CONFIG_SYSRESET` gesetzt ist. Wer den Reset je
umbaut, sollte das wissen.

Weil `sunxi_system_reset()` in `sunxi_native_pm.c` **`static`** ist, kann `sunxi_power.c` sie nicht rufen. Der Patch
wiederholt deshalb die vier Zeilen in der Plattformdatei, mit Verweis auf das Original im Kommentar. Die Alternative
(Sichtbarkeit in `sunxi_private.h` aufbohren) hätte gemeinsamen Code für alle sechs Allwinner-Plattformen angefasst —
gegen die Regel „im Zweifel klein und klar".

### 1.2 Kann BL31 die RTC-GP-Register schreiben?

**Ja, ohne Vorbereitung, ohne Schlüssel, ohne Taktfreigabe.** Vier unabhängige Belege:

1. **Abbildung:** `plat/allwinner/common/sunxi_common.c:22` bildet `SUNXI_DEV_BASE`…`+SUNXI_DEV_SIZE`, auf H713
   `0x01000000`–`0x0A000000`, flach als `MT_DEVICE | MT_RW | MT_SECURE` ab. Die RTC bei `0x07090000` liegt darin.
   BL31 braucht also keine zusätzliche `mmap_add_region()`.
2. **Der Block lebt lange vor BL31:** der SPL-DRAM-Code liest und schreibt `0x07090160`/`0x070901f4`
   (`arch/arm/mach-sunxi/dram_sun50iw12.c:81-82`); der Dateikopf hält fest, dass ein FEL-Lesen von `0x07090160`
   nach BROM `0x883f10f7` ergab, der Block also schon zur BROM-Zeit wach ist.
3. **U-Boot proper schreibt dort roh:** `writel(H713_REBOOT_BOOTLOADER_MAGIC, 0x0709011c)` (`board/sunxi/board.c:59-74`)
   und `h713_vendor_chain.c:39-92` liest/löscht dasselbe Wort — beides ohne Zugriffsschlüssel.
4. **Messungen M3/M6** am Gerät haben GP-Wörter aus U-Boot und aus Linux (`/dev/mem`) geschrieben und wiedergelesen.

**Wichtige Entwarnung zu einer scheinbaren Falle:** der ARISC-Treiber (`mainline/patches/kernel/0091-…`) warnt an
mehreren Stellen, das Lesen von „irgendetwas in `0x0709xxxx`" vor `ResetEDIDModule` hänge den SoC hart auf („drei tote
Boards"). Der gemessene Fall ist aber der **Aux-/HDMI-Block bei `0x07091xxx`** (namentlich `0x07091014`,
Hotplug-Register, und die DDC-RAM bei `0x07091c00`), nicht die RTC bei `0x070900xx`. Der Wortlaut „0x0709xxxx" ist zu
weit gefasst; SPL, U-Boot und Linux beweisen täglich das Gegenteil für den RTC-Block. **Regel für BL31 trotzdem:
ausschließlich `0x07090100`+ anfassen, nie `0x07091xxx`.** Der Patch hält sich daran (eine Adresse, `0x07090114`).

### 1.3 Wer schreibt GP3 = `0xb00f`? — nicht wir

Gesucht in allen drei Bäumen: **TF-A fasst die RTC überhaupt nicht an** (kein `0x0709`/`RTC` in
`plat/allwinner/`, außer `SUNXI_RTC_BASE` für A64), `sunxi_h713_dtb.c` macht nur die L2-Cache-Korrektur am DTB.
**U-Boot** schreibt nur GP7 (Fastboot-Marke). **Der ARISC-Kerneltreiber** (`0090`, `0091`) bildet nach eigener Aussage
keinerlei Register in dem Bereich ab, und `0xb00f` kommt in `mainline/patches/` und `uboot-h713/` nirgends vor.
Da GP3 nach Kaltstart 0 ist und erst **nach einem Linux-Lauf** `0xb00f` trägt (M6), bleibt als Schreiber praktisch nur
die **auf der ARISC laufende Vendor-Firmware** (`scp.bin`), die der Treiber startet. Ein Rohscan des Blobs nach dem
Literal `0x0709010c` blieb ohne verwertbaren Treffer (die ARISC sieht die Peripherie unter eigener Abbildung), deshalb
steht das als **offene Annahme**, nicht als Befund. Für das Gate ist es folgenlos: GP5 ist nachweislich frei, und
GP3 liegt vier Wörter daneben.

## 2. Was der Patch ändert

Vorher besteht `plat/allwinner/sun50i_h713/sunxi_power.c` aus Lizenzkopf und einer Zeile:
`#include "../sun50i_h616/sunxi_power.c"`. Damit erbt H713 auch `sunxi_power_down()`, und die kehrt wegen
`pmic == UNKNOWN` sofort zurück (`sun50i_h616/sunxi_power.c:243-249`) — `sunxi_system_off()` parkt danach nur die
Kerne, Lüfter, Backlight und USB-VBUS bleiben an.

Der Patch behält den `#include`, **benennt aber die geerbte Funktion beim Einlesen um**:

```c
#define sunxi_power_down	sunxi_pmic_power_down
#include "../sun50i_h616/sunxi_power.c"
#undef sunxi_power_down
```

und definiert danach die eigene `sunxi_power_down()`. Begründung für den Haken statt einer vollständig eigenen Datei:
Die H616-Datei liefert außer der Ausschaltroutine auch `sunxi_pmic_setup()` (aus `sunxi_bl31_setup.c` gerufen) und die
globalen `axp_read()`/`axp_write()`, gegen die `drivers/allwinner/axp/axp805.c` linkt — der steht in unserer
`platform.mk`. Eine eigenständige Datei müsste rund 240 Zeilen PMIC-Code kopieren, die wir nie pflegen wollen. Weil der
`#define` textuell vor dem Einlesen greift, wird auch der Prototyp in `sunxi_private.h` mit umbenannt; nach dem `#undef`
deklariert die Datei `void sunxi_power_down(void);` selbst, damit auch `W=2` (`-Wmissing-prototypes`) still bleibt
(geprüft). Vor allem aber: unsere Funktion ist der **Einstiegspunkt** und liegt damit garantiert **vor** der
`pmic == UNKNOWN`-Rückkehr — genau die Forderung aus dem Auftrag.

Ablauf der neuen `sunxi_power_down()`:

1. `sunxi_pmic_power_down()` rufen. Auf diesem Board ein No-op (kein AXP im DT, `pmic == UNKNOWN`); säße je ein PMIC
   drin, wäre ein echtes Ausschalten besser als das Gate und die Funktion käme nicht zurück.
2. `mmio_write_32(0x07090114, 0x47415445)` („GATE"), dann `dsbsy()`.
3. **Rücklesen.** Stimmt der Wert nicht, wird **nicht** resettet: `ERROR(…)` und `return`. Ohne Flag würde der Reset
   direkt in den nächsten Systemstart laufen, das Ausschalten wäre also ein Neustart — das Parken der Kerne (das der
   Aufrufer dann tut) ist das kleinere Übel und entspricht dem heutigen Verhalten.
4. `NOTICE("PSCI: power off, resetting into the boot gate")`. Bewusst `NOTICE` und nicht `INFO`: der Auslieferungsbau
   ist `DEBUG=0` (`mainline/build/build.sh:84`), da endet `LOG_LEVEL` bei 20 und `INFO` fiele weg — die Abnahme
   braucht die Zeile aber auf dem UART.
5. Watchdog scharf: `CFG (+0x10) = 0x16aa0001`, `MODE (+0x14) = 0x16aa0001` (0,5 s).
6. `mdelay(1000)` (doppelte Auslösezeit). Kommt der Reset wider Erwarten nicht, `ERROR("system reset failed")` und
   **`return`** statt `panic()` — der Aufrufer parkt die Kerne, das Gerät verhält sich wie heute. Das GATE-Flag bleibt
   dabei stehen: der Ausschaltwunsch besteht fort, und der einzige Ausweg aus dem geparkten Zustand ist ohnehin ein
   Netz-aus, das GP5 löscht (und 0 heißt für das Gate ebenfalls „Gate").

`SYSTEM_RESET` (`reboot`) ist **nicht angefasst**: `sunxi_system_reset()` bleibt, wie sie ist, und schreibt kein Flag.
Damit gilt weiter, was M6 gemessen hat — nach `reboot` steht in GP5 das, was U-Boot vor `bootm` hineingeschrieben hat
(RUN1, Paket G1), und das Gerät kommt ohne Taste wieder.

## 3. Bauen

Nur im Container, nie am Host (Regel, [`doku/50`](../50-befehle.md) §Bauen):

```bash
cd /opt/Projekte/h713/mainline/external/arm-trusted-firmware
patch -p1 < ../../../analyse/boot/arbeit/g2-tfa/patches/0001-tfa-h713-poweroff-enters-the-boot-gate.patch
podman exec h713-build bash -lc 'cd /work/mainline && build/build.sh bl31'
podman exec h713-build bash -lc 'cd /work/mainline && build/build.sh uboot'   # bettet bl31.bin ein
```

`build.sh bl31` baut mit `PLAT=sun50i_h713 DEBUG=0 BL31_IN_DRAM=1` und clang/lld und legt `build/out/bl31.bin` ab;
`uboot_make` reicht es als `BL31=` weiter, das FIT in `u-boot.itb` trägt es. **BL31 allein neu zu bauen genügt nicht** —
das U-Boot-Abbild muss danach ebenfalls neu erzeugt und geflasht werden (Rückweg [`doku/20`](../20-flashen-und-recovery.md):
Zweitkopie ab LBA 256, USB-Stick, Dump). Das Gate aus Paket G1 (S36) gehört in denselben Flashvorgang; einzeln
eingespielt ergibt dieser Patch ein Gerät, das nach `poweroff` durchbootet — unschön, aber nicht gefährlich.

## 4. Testrezept

Voraussetzung: G1 (S36) ist mit im Bau, `CONFIG_H713_POWER_GATE=y`, UART mitlaufend (`tio`, gehört Marco).

1. **Vorprobe ohne Linux, am U-Boot-Prompt:** `mw.l 0x07090114 0x47415445` dann `reset`. U-Boot muss nach dem Reset
   `gate: power-off requested` melden und warten. Das prüft Flag und Reset getrennt von TF-A.
2. **Der eigentliche Test:** Board bis Linux booten, dann `poweroff`. Erwartet auf dem UART, in dieser Reihenfolge:
   `PSCI: power off, resetting into the boot gate` aus BL31 → nach ~0,5 s der Neustart (SPL-Banner) → aus U-Boot
   `gate: power-off requested`. Lüfter und Backlight müssen dabei ausgehen (PB5 fällt mit dem Reset auf 0), die LED
   wird rot. Kein weiterer Bootvorgang.
3. **Taste drücken:** blau, Lüfter/Backlight an, normaler Boot.
4. **Gegenprobe `reboot`:** kein `PSCI: power off…` auf dem UART, U-Boot meldet `gate: warm start, booting`, Gerät
   kommt ohne Taste wieder (wie M6, ~11 s bis Prompt).
5. **Fehlerfall sichtbar machen:** bleibt nach `poweroff` die Zeile `PSCI: cannot arm the boot gate` stehen, ist der
   GP5-Schreibzugriff aus BL31 gescheitert — dann §1.2 neu aufrollen (und **nicht** blind resetten lassen).
6. Zählen für §5 des Plans: 20 × `poweroff`/Taste.

## 5. Offene Annahmen

1. **Nicht gebaut und nicht auf dem Board gelaufen** (Regel). Die Syntaxprobe lief mit Host-gcc gegen echte
   TF-A-Header, nicht mit clang für aarch64.
2. **Der Umbenennungs-Haken** (`#define sunxi_power_down …` vor dem `#include` einer `.c`) ist ungewöhnlich. Er ist
   bewusst gewählt und begründet (§2); wer ihn nicht mag, kopiert stattdessen die H616-Datei vollständig — dann muss
   sie aber bei jedem TF-A-Update nachgezogen werden.
3. **GP3 = `0xb00f`**: Schreiber nicht positiv identifiziert, Vermutung ARISC-Firmware (§1.3). Für GP5 unerheblich.
4. **Der Rücklese-Test** in Schritt 3 prüft, dass das Wort im Register steht — nicht, dass es den Reset überlebt.
   Dass es das tut, ist gemessen (M3), aber über den PSCI-Weg aus Linux erst mit Testschritt 2 belegt.
5. **Zusammenspiel mit G1 — geprüft, keine Annahme:** dieser Patch schreibt GATE und löscht nie. S36 §1 Schritt 6
   schreibt RUN1 „immer, auf jedem Pfad" vor der Rückkehr aus `h713_power_gate()`, also auch nach einem Gate-Durchlauf.
   Damit hebt der Tastendruck das GATE wieder auf. Ohne G1 im selben Abbild bootet das Gerät nach `poweroff` durch.
6. **`sunxi_system_off()` nach unserem `return`** parkt die Kerne mit `sunxi_cpu_power_off_others()`. Das ist der
   heutige Zustand und wurde nicht angerührt; ob das Board danach noch per UART erreichbar ist, ist unverändert offen.
