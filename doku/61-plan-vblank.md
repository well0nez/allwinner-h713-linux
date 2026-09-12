# Der Vblank-Interrupt — gelöst

Stand 31.08.2026, **am Gerät verifiziert**. Die frühere Fassung dieses Plans
nahm an, die Interrupt-Bits seien für unser Board falsch. **Das war falsch.**
Die Bits stimmen. Der Fehler lag eine Ebene tiefer.

## Die Antwort in einem Satz

Linux schaltete dem laufenden Panel den Pixeltakt ab: `clk_disable_unused`
nimmt PLL_VIDEO2, drei Display-Modtakte und den MIPS-Coprozessor mit, weil
kein Linux-Treiber sie beansprucht. Ohne MIPS kein Bildaufbau, ohne
Bildaufbau kein Vsync, ohne Vsync kein Vblank — und jeder Atomic-Commit
lief in den Timeout.

Auf der Kommandozeile fehlten **`clk_ignore_unused`** und
**`pd_ignore_unused`**.

## Ergebnis

| | vorher | nachher |
|---|---|---|
| `adopting 1920x1080` | 14,47 s | 14,26 s |
| `Console: switching to colour frame buffer` | 15,53 s | **14,32 s** |
| `fb0` registriert | **47,96 s** | **14,34 s** |
| `vblank wait timed out` | 2× | **keiner** |
| `flip_done timed out` | 3× | **keiner** |
| IRQ `GICv2 142` | 1 (Pending aus U-Boot) | **618** |
| `0x05600144` READY | `1`, hängt | **`0`**, rastet ein |
| `0x05600168` STATUS | `0` | **`2` = DONE** |
| `0x056000c0` IRQ_STATUS | `0` | **`1`**, Vsync liegt an |

Alle AFBD-Werte stehen damit auf den Stock-Werten. Konsole steht auf der Wand,
`login:` kommt durch. Ein 8-Balken-Testbild plus Graukeil per `dd` nach
`/dev/fb0` steht sichtbar; ein Rauschband, das über zwei Durchläufe nach unten
wandert, belegt den Bewegtbild-Pfad. Mitschnitt:
`re/captures/boot-clkignore.log`.

Nebenbefund daraus: AFBD **streamt live** aus `SRC`. Ungebremstes Schreiben
von Vollbildern nach `/dev/fb0` reißt das Bild sichtbar — was genau das
bestätigt, was die U-Boot-Quelle behauptet („fb-anim proved AFBD streams from
it live rather than latching the surface at commit time").

## Der Beweis

### 1. Dieselben Register, U-Boot gegen Linux

Aufnahme aus U-Boot stammt aus `re/captures/ours-reference.txt`, Logo steht
auf der Wand. Die Linux-Werte über `busybox devmem` am laufenden System
gelesen.

| Register | Takt | U-Boot | Linux | |
|---|---|---|---|---|
| `0x02001050` | PLL_VIDEO2 | `b9002a00` | `29002a00` | **Bit 31 weg** |
| `0x02001db0` | deint | `80000000` | `00000000` | **Gate weg** |
| `0x02001db4` | — | `80000000` | `00000000` | **Gate weg** |
| `0x02001db8` | — | `c4000005` | `44000005` | **Bit 31 weg** |
| `0x02001dc0` | afbd | `80000005` | `80000005` | unverändert |
| `0x02001600` | mips | — | `00000002` | Gate aus |
| `0x0200160c` | bus-mips | — | `00000000` | Gate aus |

`afbd` überlebt als einziger, weil der KMS-Treiber ihn per `clk_get` hält.
Alles andere im Display-Pfad hat keinen Halter und fällt.

Dazu `clk_summary` am laufenden System, Spalte `hardware enable`:

```
mips        0 0 0    8000000  ...  N
bus-mips    0 0 0  100000000  ...  N
deint       0 0 0 1032000000  ...  N
pll-video2  0 0 0  258000000  ...  N
afbd        1 1 0  100000000  ...  Y   <- 5600000.display  clk_afbd
bus-disp    1 1 0  100000000  ...  Y   <- 5600000.display  clk_bus_disp
```

Und im CCU-Treiber (Patch 0001) trägt **kein einziger Display-Takt**
`CLK_IS_CRITICAL`; das Flag steht nur auf `pll-periph1`, `cpux`, `mbus`,
`dram` und `bus-dram`.

### 2. `/proc/cmdline` am laufenden Gerät

```
console=ttyS0,115200 earlycon root=/dev/nfs rw
nfsroot=192.168.8.104:/srv/h713-rootfs,vers=3,tcp ip=dhcp rootwait
```

Kein `clk_ignore_unused`, kein `pd_ignore_unused`, kein `cma=128M`.

### 3. Cstenger benutzt beide Schalter — immer

`patches/kernel/0024-…-board.patch`, der `chosen`-Knoten seines Boards:

```
bootargs = "… panic=5 clk_ignore_unused pd_ignore_unused cma=128M";
```

`docs/claude-display-handoff.md`, Zeile 652, seine eigene Formulierung:

> **One dependency is load-bearing and easy to break:** `clk_ignore_unused`
> and `pd_ignore_unused`

und Zeile 132, in seiner Belegtabelle:

> the U-Boot frame survives into Linux … **Depends on
> `clk_ignore_unused`/`pd_ignore_unused`**

**Es ist also kein Board-Unterschied.** Wir haben beim Umstieg auf Netboot
die `bootargs` neu getippt und die zwei Schalter verloren. Die U-Boot-Env
überschreibt das `chosen`-Bootargs aus dem Devicetree, deshalb hilft der
Eintrag im DTS uns nicht.

### 4. Der Zustand der AFBD passt exakt dazu

| Register | Stock (U-Boot) | wir (Linux) | |
|---|---|---|---|
| `0x05600144` READY | `0` | **`1`** | geschrieben, nie eingerastet |
| `0x05600168` STATUS | `2` = `DONE` | **`0`** | Commit nie fertig |
| `0x056000c0` IRQ_STATUS | `0` | `0` | Hardware setzt das Bit nicht |
| `0x056000c4` IRQ_ENABLE | — | `1` | Treiber hat scharfgeschaltet |
| `0x05600060` / `0x05600068` | `01` / `0122` | `01` / `0122` | **identisch** |

Drei Symptome, ein Ereignis: `READY` rastet am Vsync ein, `STATUS` wird am
Vsync fertig, `IRQ_STATUS` wird am Vsync gesetzt. Alle drei bleiben aus.

### 5. Der eine Interrupt ist kein Gegenbeweis

`/proc/interrupts` zeigt `GICv2 142  h713-afbd` auf **genau 1**. Das ist
nicht der Beweis, dass Vsync läuft, sondern eine Folge des Probe-Ablaufs:
der Treiber maskiert erst und fordert dann den Interrupt an, und ein aus
U-Boot stehengebliebenes Pending-Bit feuert beim ersten Demaskieren genau
einmal. Danach nie wieder.

### 6. Die Interrupt-Bits sind gegen die Vendor-Quelle bestätigt

Der Vendor mappt zwei Fenster — `top = reg[0]`, `afbd = reg[1]` — und setzt
`workaround = afbd + 0x60`. Damit ist `workaround + 8` gleich `0x05600068`,
und dort steht am Gerät `0x122`: `mux & 3 = 2` und `(mux >> 4) & 3 = 2`, also
exakt das, was `dec_decoder_display_init()` = `dec_reg_mux_select(regs, 2)`
schreibt. Die Basis 0x05600000 und damit `0x056000c0` / `0x056000c4` sind
daran **verifiziert**, nicht angenommen.

## Der Fix

### Schritt 1 — die Kommandozeile reparieren — **erledigt, `saveenv` durch**

Nur die `bootargs` in der U-Boot-Env, kein Neubau, kein Flashen:

```
setenv bootargs 'console=ttyS0,115200 earlycon root=/dev/nfs rw
  nfsroot=192.168.8.104:/srv/h713-rootfs,vers=3,tcp ip=dhcp rootwait
  clk_ignore_unused pd_ignore_unused cma=128M'
saveenv
```

`cma=128M` kommt mit, weil der KMS-Treiber die Framebuffer aus dem
System-CMA nimmt und die voreingestellten 16 MiB laut Patch 0038 für mpv
nicht reichen. Auf den Vblank hat es keinen Einfluss, es verfälscht das
Ergebnis also nicht.

**Kalt starten, nicht `reboot`.** `h713_disp auto` setzt seine
Ein-Start-pro-Stromzyklus-Marke bei jedem U-Boot-Neustart zurück, überspringt
dann den Teardown und lädt `display.bin` über einen womöglich noch laufenden
MIPS — der schreibt weiter in das Image, während es gehasht wird, und der
Digest passt zu keinem Build (Patch 0016).

Werkzeug dafür: `tools/uart-fixargs.py`. Starten, dann Strom ziehen und
wieder anstecken; es hammert Strg-C, bricht beim `=> `-Prompt ab, setzt die
Env und startet.

Im Kernel-Log erkennbar an zwei Zeilen:

```
clk: Not disabling unused clocks
PM: genpd: Not disabling unused power domains
```

**`bus-mips` (`0x0200160c`) bleibt auch danach aus** und wird offenbar nicht
gebraucht; `mips` (`0x02001600`) dagegen steht wieder auf `0x80000002`.

### Schritt 2 — den Holzhammer durch etwas Sauberes ersetzen

`clk_ignore_unused` hält **alle** ungenutzten Takte an, nicht nur die des
Displays; auf Dauer ist das Strom und Verdeckung echter Fehler. Sauber wäre,
die Takte zu beanspruchen, die der Pfad wirklich braucht — als
`clocks = <&ccu CLK_PLL_VIDEO2>, <&ccu CLK_DEINT>, <&ccu CLK_MIPS>,
<&ccu CLK_BUS_MIPS>, …` am `display@5600000`-Knoten, oder als
`CLK_IS_CRITICAL` im CCU.

**Erst messen, welche es sind.** Mit dem Vergleich oben liegen vier
Kandidaten fest: `0x02001050`, `0x02001db0`, `0x02001db4`, `0x02001db8`,
dazu `mips` und `bus-mips`. Was `0x02001db4` und `0x02001db8` heißen, ist
noch nicht nachgesehen — im CCU-Treiber stehen an `0xdb0` `deint` und an
`0xdc0` `afbd`, die zwei dazwischen sind zuzuordnen.

Das ist der Beitrag, der auch **ihn** betrifft: sein Stack hängt an einem
Kommandozeilenschalter, den seine Doku selbst „load-bearing and easy to
break" nennt. Als Devicetree-Eigenschaft wäre er nicht mehr zu verlieren.

### Schritt 3 — erst danach die offenen AFBD-Abweichungen

```
05600058   Stock 00000062 (98)   wir 0
0560005c   Stock 00000049 (73)   wir 0
05600300   Stock 00804218        wir 00800210
05600304   Stock 00804000        wir 00800000
05600330   Stock 10101010        wir noch nicht gelesen
052800c0   Stock 00000a50        wir 00000250   ← DE-Layer, nicht AFBD
```

Nicht anfassen, solange Schritt 1 nicht durch ist: bei totem Pixeltakt sagt
keine dieser Zahlen etwas aus.

## Achtung: Display-Register aus Linux lesen kann das Board wedgen

Am 31.08. hart erfahren, und in unserer eigenen U-Boot-Quelle stand es
bereits (`h713_mips.c`, `h713_disp_teardown()`):

> those blocks wedge the interconnect when read gated … `h713_display_clocks_on()`
> ran, and the very next AFBD read still took the board

Ein `busybox devmem` auf `0x05200000` hat den SoC lautlos stillgelegt: kein
Ping, ARP `INCOMPLETE`, **keine Ausgabe mehr auf UART**, NFS-Socket noch
offen. Nur Strom ziehen half.

**Regel:** aus Linux nur Blöcke lesen, deren Takt nachweislich steht. Das
sind derzeit die CCU (`0x02001000`, immer erreichbar) und das AFBD-Fenster
`0x05600000..0x056003ff`, weil der KMS-Treiber `clk_afbd` und `clk_bus_disp`
hält. **Nicht** `0x05200000`, `0x0524c000`, `0x0525c000`, `0x05280080`,
`0x05880000` — die haben unter Linux keinen Halter. Der Zustand dieser
Blöcke gehört über UART aus U-Boot gelesen.

Umgekehrt ist der Wedge selbst eine Messung: dass er auftrat, belegt, dass
die Blöcke unter Linux gegatet sind.

## Was sich sonst als überholt herausgestellt hat

- **`sshd` startet doch.** Das Gerät ist im Zustand mit Vblank-Timeouts über
  SSH erreichbar. Es hängt nicht, es kriecht: `fb0` wird nach rund 33 s
  Timeouts doch registriert, danach läuft systemd durch.
- **Die Adresse ist `192.168.8.142`, nicht `.141`.** `CONFIG_NET_RANDOM_ETHADDR`
  gibt bei jedem Start eine neue MAC, also eine neue DHCP-Adresse. Der
  Eintrag `hy310` in `~/.ssh/config` zeigt auf die alte.

## Wo das Material liegt

| | |
|---|---|
| U-Boot-Registeraufnahme | `re/captures/ours-reference.txt`, `stock-reference.txt` |
| Boot mit Timeouts | `re/captures/autoboot-display.log` |
| Vergleichswerkzeug | `tools/regdiff.py a.txt b.txt` |
| UART-Befehle absetzen | `tools/uart-capture.py -c 'md.l …'` |
| bootargs kalt reparieren | `tools/uart-fixargs.py` |
| CCU-Treiber | `mainline/patches/kernel/0001-clk-sunxi-ng-add-h713-ccu-driver.patch` |
| sein KMS-Treiber | `mainline/patches/kernel/0037-…-afbd-scanout-kms-driver.patch` |
| seine Board-Bootargs | `mainline/patches/kernel/0024-…-board.patch`, `chosen` |
| seine Abhängigkeitsnotiz | `mainline/docs/claude-display-handoff.md`, Zeilen 132 und 652 |
| Vendor-DECD-Quelle | `legacy/drivers/decd/` |
| Ein-Start-pro-Stromzyklus | `uboot-h713/0016-…-one-launch-per-power-cycle-…patch` |
