# S17 (F1) — Warum der Audio-Top `0x0614xxxx` null liest, und wie man ihn einschaltet

Auftrag aus [`../100-plan-hdmi-audio.md`](../100-plan-hdmi-audio.md) §3, Frage **F1**. Reine statische
Analyse (kein Board, kein Zuspieler, nichts unter `mainline/patches/` oder `userspace/`).
Stand 08.09.2026. Skript für die Hauptsitzung: `analyse/hdmi-seq/audio_top_enable.py`.

---

## 0. Antwort zuerst

**Der Audio-Top liegt im Trident-Frontend-Adressraum und hängt am *Demod-Bus*. Auf unserem Board
ist dessen Bus-Gate samt Reset aus: CCU `0x02001d64` liest `0x00000000`. Damit liest jedes
Register zwischen `0x06000000` und `0x067fffff` — CIP, Demux, **Audio (`0x0614xxxx`)**, CI, DTMB und
der TVFE-Router `0x06700000` — als 0.** Die am 08.09. gesetzten Gates `0xd48/0xd4c/0xd50` Bit 31
konnten nichts bewirken, solange der Bus tot ist; `0xd80` Bit 0 war zusätzlich das falsche Bit.

Vier Befunde, jeder für sich belegt:

| # | Befund | Beleg |
|---|---|---|
| **F1a** | `bus-demod` (`0xd64` Bit 0 Gate, Bit 16 Reset) = **0**. Stock schaltet das in `tvtop_tvfe_enable`; bei uns ist `CONFIG_SUNXI_TVTOP` **nicht gesetzt** und kein anderer Treiber fordert es an | CCU-Dump `analyse/hdmi-seq/ccu-dump-after-prep-20260907.txt` Zeile `0x0d64 00000000`; `…/linux-6.18.38-a3097ce7*/.config:1337` |
| **F1b** | `snd_alsa_trid.ko` fordert **überhaupt keine** Takte, Resets oder Domänen an — die undefinierten Symbole enthalten kein einziges `clk_*`, `reset_control_*`, `pm_runtime_*`, `sunxi_tvtop_*`, nur `ioremap`/`iounmap`. Stock verlässt sich vollständig darauf, dass `sunxi_tvtop` den Block vorher angeschaltet hat | `readelf -s snd_alsa_trid.ko`, UND-Liste (unten §2d) |
| **F1c** | Mainline-CCU modelliert `bus-hdmi-audio` als `0xd80` **BIT(0)** und `bus-cap-300M` als **BIT(1)**. In der Vendor-Tabelle sind es **BIT(31)** und **BIT(30)** — und die stehen beim Boot bereits an (`0xd80 = 0xc0000000`). Das Setzen von Bit 0 am 08.09. war ein Schreiben ins Leere | `analyse/hdmi-seq/vendor-ccu-table.txt` [121]/[122] + Stock-`vmlinux`-Strukturen `c14618e0`/`c14618b4`; `ccu-sun50i-h713.c:594-597` (Zeilen 594/596) |
| **F1d** | Mainline-CCU modelliert `audio-cpu/umac/ihb` und `hdmi-audio` als **nackte Gates mit Parent `ahb`**. Real sind es `ccu_div`-Takte mit Mux auf PLLs. Linux' Taktbaum zeigt darum falsche Raten, `clk_set_rate` kann nichts, und der Mux von `audio_ihb` steht auf dem falschen Parent | `vendor-ccu-table.txt` [112]-[114], [123]; `ccu-sun50i-h713.c:576-599` |

Positivkontrolle für die Diagnose ist bereits gemessen (06.09., doku/72 „Neunter/zehnter Lauf"):
**`0x06700000` liest ohne `bus-demod` `0`, mit `bus-demod` an `0x7ff`.** Genau das Symptom der
Audio-Fenster, an einem Register desselben Adressraums. `analyse/hdmi-seq/tvfe_enable.py --do` und
`tvtop_stock_clks.py --do` sind am Board schon gelaufen (Läufe 9–11 und 68) und **haben es nicht
umgebracht** — der erste Rezeptschritt ist weder neu noch riskant.

---

## 1. Registerkarte CCU `0xd10 … 0xd90`

Quellen der Felder: `analyse/hdmi-seq/vendor-ccu-table.txt` (Stock-`vmlinux`,
`sun50iw12_ccu_desc @c0ea1fa4`, 130 Takte / 58 Resets) und, diese Sitzung, die typisierten
Strukturen aus der **DWARF-Info desselben `vmlinux`** (es ist ARM32, Entry `0xc0008000`, Quellbaum
`H713_SDK_V1.3_NEW/longan/kernel/linux-5.4`) — Dump `re/captures/weltneuheit/audio-a02-ccu-tabellen-20260908.log`.
Ist-Werte: Wortdump unseres Boards `analyse/hdmi-seq/ccu-dump-after-prep-20260907.txt` (07.09.,
nach `prep`). Soll-Raten: `legacy/drivers/tvtop/sunxi_tvtop_data.c` (aus `sunxi_tvtop.ko`).

**Zwei Nummernkreise, nicht verwechseln.** *DT-ID* = Index in `sun50iw12_hw_clks` (139 Einträge,
inklusive der Fixed-Factor-PLLs) — das benutzt der **Stock-DTB**. *CLK-ID* = Index in
`sun50iw12_ccu_clks` (130 Einträge) — das benutzt zufälligerweise unser
**Mainline-`dt-bindings/clock/sun50i-h713-ccu.h`**. Beispiel: `audio_cpu` ist DT-ID `0x75` = 117
und zugleich `CLK_AUDIO_CPU` = 112.

Registerformat (belegt; `ccu_gate_helper_enable @c0567048` macht `reg |= enable`, `enable` ist eine
**Bitmaske**; `ccu_div_recalc_rate @c0567004` mit `div.offset = 1` ⇒ Teiler = Feldwert + 1):

* `[31]` Gate — bei `0xd80` sind es **zwei** Gates, `[31]` und `[30]`; bei den Bus-Gates
  `0xd64/0xd88/0xdd8` ist es `[0]`
* `[16]` Reset (nur `0xd64`, `0xd88`, `0xdd8`), 1 = gelöst
* `[26:24]` Mux (3 bit) bzw. `[24]` (1 bit) — Wert = Index in der Parent-Liste
* `[9:8]` P — nur bei `ccu_mp`: zusätzlicher Teiler `× 2^P`
* M — Teiler `M+1`, Feldbreite je Takt verschieden

| Reg | Name (Vendor/DT) | DT-ID | CLK-ID | Typ | M / P / Mux | Parents (Mux 0,1,2,…) | **Ist am Board** | Deutung Ist | Stock-Soll |
|---|---|---|---|---|---|---|---|---|---|
| `0xd10` | `adc` | 0x6b 107 | 102 | mp | M[4:0] P[9:8] Mux[24] | pll-adc, pll-video0 | `01000005` | aus, Mux 1 = 324M/6 = 54 MHz | 54 MHz aus **pll-adc** |
| `0xd18` | `dtmb-120M` | 0x6c 108 | 103 | mp | M[2:0] P[9:8] Mux[24] | pll-adc, pll-periph0 | `01000004` | aus, Mux 1 = 600M/5 = 120 MHz | 120 MHz aus pll-adc |
| `0xd20` | `tvfe_1296M_clk` | 0x6d 109 | 104 | mp | M[4:0] P[9:8] Mux[24] | pll-video0-4x, pll-adc | `80000000` | **an**, 1296 MHz | 1296 MHz ✔ |
| `0xd24` | `i2h` | 0x6e 110 | 105 | div | M[4:0] Mux[26:24] | pll-video0-4x, pll-periph0-2x, pll-periph1-2x | `00000007` | aus, Mux 0 = 1296/8 = 162 MHz | 200 MHz aus pll-periph0-2x |
| `0xd28` | `cip-tsx` | 0x6f 111 | 106 | div | M[2:0] Mux[24] | pll-periph0, pll-periph1 | `00000002` | aus, 600/3 = 200 MHz | 200 MHz |
| `0xd2c` | `cip-mcx` | 0x70 112 | 107 | div | M[2:0] Mux[24] | pll-periph0, pll-periph1 | `00000005` | aus, 600/6 = 100 MHz | 100 MHz |
| `0xd30` | `cip-tsp` | 0x71 113 | 108 | div | M[2:0] Mux[24] | pll-video0-4x, pll-adc | `00000004` | aus, 1296/5 = 259 MHz | 333 MHz |
| `0xd34` | `tsa-tsp` | 0x72 114 | 109 | div | M[2:0] Mux[24] | pll-video0-4x, pll-adc | `00000004` | aus | 333 MHz |
| `0xd38` | `cip27` | 0x73 115 | 110 | mp | M[3:0] P[9:8] Mux[24] | pll-video0, pll-adc | `0000000b` | aus, 324/12 = 27 MHz | 27 MHz |
| `0xd40` | `cip-mts0` | 0x74 116 | 111 | mp | M[4:0] P[9:8] Mux[26:24] | pll-video1-4x, pll-video0-4x, pll-video3-4x, pll-adc, pll-periph0-2x | `0000020a` | aus, Mux 0 → **pll-video1 ist aus** | 27 MHz |
| **`0xd48`** | **`audio_cpu`** | **0x75 117** | **112** | **div** | **M[2:0] Mux[24]** | **pll-periph0-2x (1200M), pll-periph1-2x** | **`00000002`** | **Gate AUS**, Mux 0, M+1 = 3 → **400 MHz** | **400 MHz** ✔ Teiler stimmt schon |
| **`0xd4c`** | **`audio_umac`** | **0x76 118** | **113** | **div** | **M[2:0] Mux[24]** | **pll-periph0 (600M), pll-periph1** | **`00000002`** | **Gate AUS**, Mux 0, M+1 = 3 → **200 MHz** | **200 MHz** ✔ Teiler stimmt schon |
| **`0xd50`** | **`audio_ihb`** | **0x77 119** | **114** | **div** | **M[3:0] Mux[26:24]** | **pll-video0-4x (1296M), pll-periph0 (600M), pll-periph1** | **`00000007`** | **Gate AUS**, Mux 0 (**falscher Parent**), M+1 = 8 → **162 MHz** | **200 MHz aus pll-periph0** ⇒ Sollwert `0x81000002` |
| `0xd58` | `tsa432` | 0x78 120 | 115 | div | M[2:0] Mux[24] | pll-video0-4x, pll-adc | `00000002` | aus, 1296/3 = 432 MHz | 432 MHz |
| `0xd5c` | `mpg0` | 0x79 121 | 116 | mp | M[3:0] P[9:8] Mux[26:24] | pll-video1-4x, dcxo24M, pll-adc | `0000020b` | aus | 27 MHz |
| `0xd60` | `mpg1` | 0x7a 122 | 117 | mp | dito | dito | `0000020b` | aus | 27 MHz |
| **`0xd64`** | **`bus-demod`** | **0x7b 123** | **118** | **gate** | **`[0]` Gate, `[16]` Reset** | **pll-video0-4x (!), nicht `ahb`** | **`00000000`** | **Gate AUS, Reset ANLIEGEND** | **`0x00010001`** |
| `0xd6c` | `tcd3` | 0x7c 124 | 119 | mp | M[2:0] P[9:8] Mux[24] | pll-video0-4x, pll-adc | `80000305` | **an**, 1296/(6·8) = 27 MHz | 27 MHz ✔ |
| `0xd74` | `vincap-dma` | 0x7d 125 | 120 | div | M[4:0] Mux[24] | pll-video2-4x, pll-periph0 | `81000001` | **an**, Mux 1 = 600/2 = 300 MHz | 300 MHz ✔ |
| **`0xd80`** | **`bus-hdmi-audio` `[31]` + `bus-cap-300M` `[30]`** | **0x7e 126 / 0x7f 127** | **121 / 122** | **gate** | **`[31]`, `[30]`; kein Reset** | **ahb** | **`c0000000`** | **beide AN** ✔ | beide an |
| **`0xd84`** | **`hdmi-audio`** | **0x80 128** | **123** | **div** | **M[4:0] Mux[24]** | **pll-video3-4x, pll-periph0-2x** | **`80000000`** | **an**, Mux 0, M+1 = 1 → **pll-video3-4x voll = 2400 MHz** (s. §5.4) | **1152 MHz** |
| `0xd88` | `bus-tvcap` | 0x81 129 | 124 | gate | `[0]` + `[16]` | ahb | `00010001` | **an + Reset gelöst** ✔ | dito |
| `0xdb0/b4/b8/c0` | `deint`/`panel`/`svp-dtl`/`afbd` | 0x82…0x85 | 125-128 | div | — | — | `80000000`/`80000000`/`c4000005`/`80000005` | an | — |
| `0xdd8` | `bus-disp` | 0x86 134 | 129 | gate | `[0]` + `[16]` | ahb | `00010001` | an ✔ | dito |

PLLs aus demselben Dump: `pll-periph0` `0x020 = b8003100` **an** (VCO 24 × 50 = 1200 ⇒
`pll-periph0` 600, `-2x` 1200), `pll-video0` `0x040 = b8003500` **an** (24 × 54 = 1296 ⇒
`pll-video0` 324, `-4x` 1296), `pll-video2` `0x050 = b9002a00` **an** (1032), `pll-video3`
`0x068 = b8006300` **an** (N-Feld 0x63 ⇒ 24 × 100 = **2400**), `pll-video1` `0x048` **aus**,
`pll-adc` `0x060` **aus**. (N = Feldwert + 1, `pll_videoX_4x` = VCO, `pll_videoX` = VCO/4 —
belegt aus `pll_video3_clk`: N `[15:8]` offset 1, `fixed_post_div = 4`.)

**Fürs Rezept wichtig:** alle Parents der drei Audio-Takte (`pll-periph0`, `pll-periph0-2x`,
`pll-video0-4x`) laufen bereits. Es muss **keine PLL** angefasst werden — was gut ist, denn
`clk_set_rate` auf den TV-PLLs ist der dokumentierte SoC-Freeze (KNOW-20260413-031149-493). Die
Teilerfelder von `audio_cpu`/`audio_umac` stehen beim Boot schon exakt auf den Stock-Raten. Es
fehlen nur die Gates — und der Bus.

### Was an unserem CCU-Treiber falsch ist

`mainline/build/linux-6.18.38-a3097ce7*/drivers/clk/sunxi-ng/ccu-sun50i-h713.c`:

```c
static SUNXI_CCU_GATE(audio_cpu_clk,       "audio-cpu",       "ahb", 0xd48, BIT(31), 0);   // 576
static SUNXI_CCU_GATE(audio_umac_clk,      "audio-umac",      "ahb", 0xd4c, BIT(31), 0);   // 578
static SUNXI_CCU_GATE(audio_ihb_clk,       "audio-ihb",       "ahb", 0xd50, BIT(31), 0);   // 580
static SUNXI_CCU_GATE(bus_hdmi_audio_clk,  "bus-hdmi-audio",  "ahb", 0xd80, BIT(0),  0);   // 594  FALSCH
static SUNXI_CCU_GATE(bus_cap_300m_clk,    "bus-cap-300m",    "ahb", 0xd80, BIT(1),  0);   // 596  FALSCH
static SUNXI_CCU_GATE(hdmi_audio_clk,      "hdmi-audio",      "ahb", 0xd84, BIT(31), 0);   // 598
static SUNXI_CCU_GATE(bus_demod_clk,       "bus-demod",       "ahb", 0xd64, BIT(0),  0);   // 588
```

* `0xd80`: Gate-Bits sind **31 und 30**. Solange das so steht, meldet Linux `bus-hdmi-audio` als
  „aus", obwohl die Hardware an ist, und `clk_prepare_enable` schreibt Bit 0 (Bedeutung in der
  Vendor-Tabelle nicht vergeben).
* `audio-cpu/umac/ihb` und `hdmi-audio` (ebenso `adc`, `dtmb-120m`, `tvfe-1296m`, `i2h`, `cip-*`,
  `tsa-*`, `mpg*`, `tcd3`, `vincap-dma`) sind `ccu_div`/`ccu_mp` mit Mux — Parent `"ahb"` ist
  erfunden. Für Audio zählen die vier.
* `bus-demod` (`0xd64`) hat als Parent **`pll-video0-4x`**, nicht `ahb`.
* Richtig ist dagegen die Reset-Karte: `RST_BUS_DEMOD` = 55 = `0xd64` BIT(16) usw.

---

## 2. Reset-, Power- und Bus-Abhängigkeiten

### 2a. Resets

`sun50iw12_ccu_resets @c1460f78`, 58 Einträge, Stride 8; `ccu_reset_deassert @c0566d38` macht
`reg |= bit` (Maske).

| Stock-DT | Name | Register | Bit | Mainline | Ist am Board |
|---|---|---|---|---|---|
| `0x37` = 55 | `reset_bus_demod` | `0xd64` | 16 | `RST_BUS_DEMOD` = 55 | **anliegend (0)** |
| `0x38` = 56 | `reset_bus_tvcap` | `0xd88` | 16 | `RST_BUS_TVCAP` = 56 | gelöst |
| `0x39` = 57 | `reset_bus_disp` | `0xdd8` | 16 | `RST_BUS_DISP` = 57 | gelöst |

**Negativbefund, wichtig:** Für `0xd80` (`bus-hdmi-audio`, `bus-cap-300M`) gibt es **keinen
Reset** — Reset 54 liegt auf `0xbac`, dann folgt direkt 55 auf `0xd64`. Dort ist also nichts
„falsch resettet"; Gates genügen. Und in `0xd64/0xd88/0xdd8` liegt je genau ein Reset — es gibt
keinen versteckten Audio-Reset.

### 2b. Power-Domänen

Stock-Treiber ist **nicht** `sunxi-ppu`, sondern `allwinner,tv303-power-controller`
(`drivers/soc/sunxi/pm_domains.c`, im `vmlinux`); DT `power-management@ff000000`,
`reg = <0x07001000 0x400>`. `tv303_pmu @c0ea3d90`: `wait_mode 0x14`, `pwr_off_delay 0x18`,
`pwr_on_delay 0x1c`, **`pwr 0x20`**, **`status 0x24`**, `num_domains 5`; Registeradresse =
`offset + (domain_id << 7)`; Schreibwert **1 = an, 2 = aus**; „an" = `(status & 0x30000) == 0x10000`.

| Index | Name | PWR | STATUS |
|---|---|---|---|
| 0 | pd_gpu | `0x07001020` | `0x07001024` |
| **1** | **pd_tvfe** | **`0x070010a0`** | **`0x070010a4`** |
| 2 | pd_tvcap | (`0x07001120`) | (`0x07001124`) |
| 3 | pd_ve | `0x070011a0` | `0x070011a4` |
| 4 | pd_av1 | `0x07001220` | `0x07001224` |

Das deckt sich mit unserem `ppu`-Knoten (`power-controller@7001014`, `PWR_CTRL 0x0c`,
`STATUS 0x10`, Stride `0x80`) — dieselben absoluten Adressen. **Eine eigene Audio-Domäne gibt es
nicht.** Audio hängt an **pd_tvfe** (`audio_cpu/umac/ihb` stehen in Stocks `tvfe_clks[]`),
HDMI-Audio an **pd_tvcap** (`hdmi_audio_clk`, `hdmi_audio_bus`, `cap_300m` in `tvcap_clks[]`).
Beide Domänen sind bei uns **an** (U-Boot; `pm_genpd_summary`; dtsi-Kommentar „Verified on
hardware … status=0x00010000 (ON)"). **Power ist nicht die Ursache.**

Kuriosum fürs Protokoll: im Stock ist `tv303_pm_domains[2]` (pd_tvcap) ein **komplett genullter
Eintrag**, und `sunxi_pm_add_one_domain` indiziert per DT-`reg`, nicht per `domain_id`. Stocks
pd_tvcap schaltet damit faktisch nichts (schreibt in pd_gpus Register, `is_on()` immer falsch).
Unser Mainline-PPU behandelt Domäne 2 als echte Domäne — und misst sie als „an". Für Audio ohne
Belang, aber es erklärt, warum Stock ohne funktionierendes pd_tvcap auskommt.

### 2c. Warum der Adressraum am Demod-Bus hängt

Der Stock-DTB ordnet `0x6144000` (MSP-Mailbox-Seite, `0x1000`) demselben
`trix,io-accessor`-Fenster `io-space-n` zu wie `cip@6000000` (`+0x20000`), `demux@6100000`
(`+0x20000`) und `ci@6500000` — die klassischen Trident-Frontend-Blöcke
(`bootpkg-full.dts` Zeilen 2234–2295). `dtmb@6600000` trägt als zweites `reg` **`0x6700000`**
(`0x500`), also genau den TVFE-Top, in den `tvtop_tvfe_enable` `0x003003FF` schreibt.
`0x0614xxxx` liegt mitten in diesem Raum, direkt oberhalb des Demux.

Dazu die zwei Messungen vom 06.09. (doku/72): **`0x06700000` = 0 ohne `bus-demod`, `0x7ff` mit**;
und `0x068B0000` wedgt den Interconnect ohne `bus-demod`. ⇒ **Der ganze Trident-Frontend-Raum
hängt an `bus-demod`.**

### 2d. Was `snd_alsa_trid.ko` tut — und was nicht

Vollständige UND-Symbolliste des Stock-Moduls (`readelf -s`): `ioremap`, `iounmap`,
`platform_get_irq`, `request_threaded_irq`, `__platform_driver_register`, `ion_alloc`/`ion_free`,
`dma_buf_*`, ALSA (`snd_card_*`, `snd_pcm_*`, `snd_ctl_*`), Timer/Mutex/printk. **Kein einziges**
`clk_get`, `clk_prepare_enable`, `clk_set_rate`, `reset_control_*`, `pm_runtime_*`,
`dev_pm_domain_*`, `sunxi_tvtop_clk_get`, `of_iomap`.

Das ist die harte Antwort auf „wie hatte Stock die Takte an": **gar nicht selbst.** Der Audio-Block
wird von `sunxi_tvtop` mitversorgt (TVFE + TVCAP), und `snd_alsa_trid` setzt das voraus. Genau
dieser Vorversorger fehlt bei uns.

`REG_Init @.text+0x7738` mappt: `0x06146000` (0x88), `0x06148000` (0x394), `0x0614a000` (0x0f),
`0x06142044` (4), `0x02031078`, `0x02032078`. **`0x06144000` mappt das Modul nicht** — die
DSP-Mailbox geht im Stock über `io-space-n` an den **Userspace** (`libmspdriver.so`:
`aud_dsp1_write_reg` wartet auf `[0x06144000] & 0x10 == 0` und schreibt `0x0614400c`;
`aud_dsp1_read_reg` schreibt `0x06144010` und wartet auf Bit 5 — bestätigt in
`re/captures/weltneuheit/audio-a42-20260908.log`).

`audio_top_clk_init @.text+0x2d0c` (96 B) macht genau drei Zugriffe:

```
[0x0614a000] |= 0x00000700
[0x0614a00c]  = ([0x0614a00c] & 0xFF000000) | 0x001A5E00
[0x0614a00c] |= 0x01000000
```

identisch zu `re/notes/RE_NOTES.md` „Audio-top clock init" und zum Nachbau in
`legacy/drivers/audio/bridge/audio_bridge_if.c` `trid_audioio_init()`.

### 2e. Stock-Reihenfolge (`sunxi_tvtop.ko`)

`tvtop_tvfe_enable @0x09dc` — hier hängen die Audio-Takte dran:

```
1  reset_control_deassert(reset_bus_demod)          # 0xd64 |= BIT(16)   -- VOR den Takten
2  usleep_range(10000, 15000)
3  sunxi_tvtop_clock_enable(tvfe)                   # 15 Takte inkl. audio_ihb/audio_cpu/audio_umac
   #   je Eintrag: clk_prepare_enable(clk); wenn parent_rate: Parent holen+enable,
   #   clk_set_rate(parent, parent_rate); wenn target_rate: clk_set_rate(clk, target_rate)
   #   (der Legacy-Port ueberspringt beide clk_set_rate -- Freeze-Workaround)
4  clk_prepare_enable(clk_bus_demod)                # 0xd64 |= BIT(0)
5  usleep_range(10000, 15000)
6  reset_control_deassert(reset_bus_demod)          # zweites Mal
7  tvtop_pm_domain_enable(pd_tvfe)                  # genpd perf-state INT_MAX + pm_runtime_resume
8  usleep_range(10000, 15000)
9  writel(0x003003FF, 0x06700000)                   # TVFE-Router
```

`tvtop_tvcap_enable @0x0ac4` — bei uns **schon erledigt**, `0x06e00000` liest
`+0=0x00111111 +4=0x01111117 +8=0x00000504` (doku/71):

```
1  Takte tcd3, vincap_dma, hdmi_audio_clk, cap_300m, hdmi_audio_bus
2  10 ms; clk_bus_tvcap; reset_bus_tvcap deassert; 10 ms; pd_tvcap; 10 ms
3  0x06e00004 = 0x01111117 / 0x06e00008 = 0x00000404 / 0x06e00000 = 0x00111111
4  ioremap(0x06940000); writel(1); iounmap        # INCAP-Power -- bei uns macht das der MIPS
```

---

## 3. Einschaltrezept (`/dev/mem`, Schritt für Schritt)

Fertiges Skript: **`analyse/hdmi-seq/audio_top_enable.py`** — ohne Argument rein lesend,
`--do` = Schritte 1–10, `--do --audio-top` zusätzlich 11–14, `--ihb-stock` setzt zusätzlich den
`audio_ihb`-Mux auf Stock. Marker nach `/dev/kmsg`. **`0x068B0000` wird nirgends angefasst.**

Schritt 0 — Vorbedingungen. Stimmt eine nicht: **abbrechen**.

| Prüfung | Erwartung |
|---|---|
| `pll-periph0` `0x02001020` Bit 31 | 1 |
| `pll-video0` `0x02001040` Bit 31 | 1 |
| PPU TVFE `0x070010a4`, TVCAP `0x07001124` | `& 0x30000 == 0x10000` |
| `0xd88` / `0xdd8` | `0x00010001` |
| `0xd80` | `0xc0000000` |
| `0x06700000` | **0** (= Demod-Bus tot; der zu behebende Zustand) |
| Audio-Fenster (Liste nach Schritt 10) | alle 0 |

| # | Aktion | Register | Wert | Warten | Erwartung danach |
|---|---|---|---|---|---|
| 1 | Reset lösen (1×, wie Stock) | `0x02001d64` | `\|= 0x00010000` | 12 ms | `0x00010000` |
| 2 | `audio_cpu` Gate an, Teiler bleibt | `0x02001d48` | `:= 0x80000002` | — | `0x80000002` = 400 MHz |
| 3 | `audio_umac` Gate an | `0x02001d4c` | `:= 0x80000002` | — | `0x80000002` = 200 MHz |
| 4 | `audio_ihb` Gate an, Boot-Mux behalten | `0x02001d50` | `\|= 0x80000000` | — | `0x80000007` = 162 MHz |
| 4′ | *oder* Stock-Variante (`--ihb-stock`) | `0x02001d50` | `:= 0x81000002` | — | `0x81000002` = 200 MHz |
| 5 | `hdmi-audio`, `bus-hdmi-audio`/`cap-300M` sicherstellen | `0x02001d84`, `0x02001d80` | `\|= 0x80000000`, `\|= 0xc0000000` | — | unverändert `0x80000000` / `0xc0000000` |
| 6 | Bus-Gate an | `0x02001d64` | `\|= 0x00000001` | 12 ms | `0x00010001` |
| 7 | Reset lösen (2×, idempotent) | `0x02001d64` | `\|= 0x00010000` | 12 ms | `0x00010001` |
| **8** | **Kontrolle: TVFE-Top lesen** | `0x06700000` | — | — | **≠ 0** (gemessen `0x7ff`). Bleibt 0 → These falsch, §5.1 |
| 9 | TVFE-Router setzen | `0x06700000` | `:= 0x003003FF` | 12 ms | liest `0x003003FF` |
| **10** | **Kontrolle: Audio-Fenster lesen** | s. u. | — | — | **mindestens eines ≠ 0** |
| 11 | Audio-Top-Takt CTL | `0x0614a000` | `\|= 0x700` | — | Bits 8–10 gesetzt |
| 12 | Audio-Top-Takt CFG | `0x0614a00c` | `:= (alt & 0xff000000) \| 0x001a5e00` | — | `…1a5e00` |
| 13 | Audio-Top-Takt CFG enable | `0x0614a00c` | `\|= 0x01000000` | 5 ms | `0x011a5e00` |
| **14** | **Positivkontrolle: Schreib-Lese-Probe** | `0x06142044` | Bits 7:0 `:= 0x5a`, lesen, zurückschreiben | — | gelesen `…5a` ⇒ Block **lebt**; bleibt 0 ⇒ tot |

Fenster für Schritt 10 (das, was am 08.09. alles 0 las):

```
0x06142044                         high-addr-ctl (ISTREAM-Hochbits 3:0, OSTREAM 7:4)
0x06144000 / +0x0c / +0x10         MSP-DSP-Mailbox (Status Bit4 write-busy, Bit5 read-ready)
0x06146000 +0x00/04/10/38/3c/48/4c AUDIF (IRQ-Status/Maske, SPDS-Status, SPDI1/2 cfg+status)
0x06148384/388/38c/390             AUDBRG global-irq-en / Maske / Status / stream-sync
0x06148100 (+0x08 = ptr)           OSTREAM0 (Capture-Ring)
0x0614a000 / 0x0614a00c            Audio-Top-Clk CTL / CFG
```

**Warum zweistufig:** „≠ 0" allein könnte ein Bus-Artefakt sein. Deshalb erst Schritt 14
(Schreib-Lese-Probe an einem Register, das laut Legacy-Port frei beschreibbare Bits hat), danach
die Fs-Probe aus dem Plan: am Zuspieler zwischen 44,1 und 48 kHz umschalten und
`0x0614603c`/`0x0614604c` (SPDI1/2-Status) beobachten. Erst wenn die sich ändern, ist bewiesen,
dass der HDMI-Audiostrom wirklich am AUDIF ankommt.

**Wenn Schritt 8 fehlschlägt:** `analyse/hdmi-seq/tvfe_enable.py --do` (alle 16 TVFE-Gates +
`bus-demod` + Router) bzw. `tvtop_stock_clks.py --do` (zusätzlich PLLs, Muxe, tvdisp-Tabelle).
Beide sind am Board gelaufen und haben es nicht umgebracht. Danach Schritt 10 wiederholen.

**Trennschärfe zwischen Schritt 7 und 9:** erst Schritt 10 **ohne** Schritt 9 fahren. Kommt der
Block schon dann, ist der TVFE-Router für Audio nicht nötig; kommt er erst nach 9, sitzt die
Freigabe in einem der Bits von `0x003003FF` (Kandidat: die von Stock zusätzlich gesetzten Bits 20/21,
denn `0x7ff` steht schon).

**Rückweg:** `0xd64 := 0`, `0xd48/0xd4c/0xd50` zurück auf `0x2 / 0x2 / 0x7`. Ein Neustart stellt
den Boot-Zustand ohnehin her; nichts davon liegt in einem Flash.

**Warnung.** Mit `bus-demod` an werden Register lebendig, die vorher stumm waren — darunter
`0x068B0000` (Sperrliste doku/69: nur *lesen*, und nur mit `bus-demod`). Der MIPS bedient TVTOP-A
zeigerbasiert; ob gleichzeitige ARM-Aktivität im selben Raum ihn stört, ist offen. Lauf 68 (Takte
+ Router gesetzt, danach normale Bedienung) war unauffällig. Kurze Schritte, nach jedem Schritt
Lebenszeichen prüfen.

---

## 4. Was ein Mainline-Treiber im DT anfordern muss

### 4a. CCU-Treiber zuerst geradeziehen

Ohne diese Korrekturen kann kein Treiber das Richtige anfordern (`ccu-sun50i-h713.c`; die
Umsetzung gehört der Hauptsitzung, `mainline/patches/` fasse ich nicht an):

1. `bus_hdmi_audio_clk` → `0xd80, BIT(31)`; `bus_cap_300m_clk` → `0xd80, BIT(30)`.
2. `audio_cpu_clk` → `SUNXI_CCU_M_WITH_MUX_GATE`, Reg `0xd48`, M `(0,3)`, Mux `(24,1)`,
   Gate `BIT(31)`, Parents `{"pll-periph0-2x","pll-periph1-2x"}`.
   `audio_umac_clk` → `0xd4c`, M `(0,3)`, Mux `(24,1)`, Parents `{"pll-periph0","pll-periph1"}`.
   `audio_ihb_clk` → `0xd50`, M `(0,4)`, Mux `(24,3)`,
   Parents `{"pll-video0-4x","pll-periph0","pll-periph1"}`.
   `hdmi_audio_clk` → `0xd84`, M `(0,5)`, Mux `(24,1)`,
   Parents `{"pll-video3-4x","pll-periph0-2x"}`.
   Alle Parent-Namen existieren im Treiber bereits.
3. `bus_demod_clk` Parent `"pll-video0-4x"` statt `"ahb"`.

`RST_BUS_DEMOD` (`0xd64` BIT(16)) ist schon richtig eingetragen — nicht anfassen.

### 4b. DT-Knoten für den Audio-Bridge-Treiber

Heute (`sun50i-h713.dtsi:935`) hat `audio-bridge@203042c` nur die drei Audio-Takte und **keinen
Reset, keine Domäne, kein `reg` für die MMIO-Fenster** — der Legacy-Port mappt sie hart. Nötig ist:

```dts
audio_bridge: audio-bridge@203042c {
	compatible = "vs,trid-audio-bridge";
	reg = <0x0203042c 0x4>,      /* logic          */
	      <0x06146000 0x88>,     /* audif          */
	      <0x06148000 0x394>,    /* audbrg         */
	      <0x0614a000 0x10>,     /* audio-top-clk  */
	      <0x06142044 0x4>,      /* high-addr-ctl  */
	      <0x06144000 0x20>;     /* msp-mailbox    */
	reg-names = "logic", "audif", "audbrg", "audio-top-clk",
		    "high-addr-ctl", "msp-mailbox";
	interrupts = <GIC_SPI 113 IRQ_TYPE_LEVEL_HIGH>,   /* audbrg */
		     <GIC_SPI 115 IRQ_TYPE_LEVEL_HIGH>;   /* audif  */
	clocks = <&ccu CLK_BUS_DEMOD>,        /* 118 — der entscheidende */
		 <&ccu CLK_AUDIO_CPU>,        /* 112, 400 MHz            */
		 <&ccu CLK_AUDIO_UMAC>,       /* 113, 200 MHz            */
		 <&ccu CLK_AUDIO_IHB>,        /* 114, 200 MHz            */
		 <&ccu CLK_HDMI_AUDIO>,       /* 123                     */
		 <&ccu CLK_BUS_HDMI_AUDIO>;   /* 121                     */
	clock-names = "bus_demod", "audio_cpu", "audio_umac", "audio_ihb",
		      "hdmi_audio", "bus_hdmi_audio";
	assigned-clocks = <&ccu CLK_AUDIO_CPU>, <&ccu CLK_AUDIO_UMAC>,
			  <&ccu CLK_AUDIO_IHB>;
	assigned-clock-parents = <&ccu CLK_PLL_PERIPH0_2X>,   /* 130 */
				 <&ccu CLK_PLL_PERIPH0>,      /*   2 */
				 <&ccu CLK_PLL_PERIPH0>;
	assigned-clock-rates = <400000000>, <200000000>, <200000000>;
	resets = <&ccu RST_BUS_DEMOD>;        /* 55 — shared! */
	reset-names = "bus_demod";
	power-domains = <&ppu 1>;             /* TVFE */
	iommus = <&iommu 6 1>;                /* Stock-DTB audbrg@203042c */
	dma-coherent;
	status = "okay";
};
```

Beim Bauen zu beachten:

* **`reset_control_get_shared`**, nicht `_exclusive`: `RST_BUS_DEMOD` gehört dem ganzen
  TVFE-Frontend (Stock-`tvtop` holt ihn ebenfalls shared). Sonst kollidiert der Treiber mit einem
  später aktivierten `tvtop`/DTMB.
* **Nur eine Domäne pro Knoten** ohne Namen. Wer TVCAP zusätzlich strikt modellieren will, braucht
  `power-domain-names = "tvfe", "tvcap"` + `dev_pm_domain_attach_by_name` (wie `tvcap_bringup`).
  Für den Audio-Block reicht TVFE — TVCAP ist ohnehin an.
* **Reihenfolge im `probe` exakt wie Stock** (§2e): Reset deassert → Modul-Takte → Bus-Takt →
  10 ms → Reset deassert → `pm_runtime_resume_and_get(pd)` → 10 ms → `audio_top_clk_init` → **erst
  danach** der erste Lesezugriff auf AUDIF/AUDBRG. `clk_set_rate` auf die PLL-Eltern **nicht**
  nachbauen (Freeze); die Boot-Raten passen bereits.
* Der TVFE-Router `0x06700000 := 0x003003FF` gehört **nicht** in den Audio-Treiber. Entweder in
  `tvtop` (dann `CONFIG_SUNXI_TVTOP` **mit** vertauschten `reg`-Einträgen, siehe doku/71) oder —
  sauberer — in eine kleine `h713-tvfe`-Inbetriebnahme analog `analyse/tvcap/h713-tvcap.c`. Ob er
  für Audio überhaupt nötig ist, entscheidet Schritt 10 gegen Schritt 9.
* `i2s2@2034000` trägt heute `<&ccu CLK_HDMI_AUDIO>` unter dem Namen `"pll_tvfe"`. Falsch benannt:
  Stock gibt Codec und I2S `pll_tvfe` = DT-ID `0x6d` = **`tvfe_1296M_clk`** (Mainline
  `CLK_TVFE_1296M` = 104), nicht `hdmi_audio`. Beim Anfassen von `i2s2`/`codec` mitkorrigieren.
* Der stock-eigene Weg zur DSP-Mailbox ist **Userspace** (`io-space-n` → `libmspdriver.so`). Wer
  `0x06144000` in den Kernel-Knoten aufnimmt, weicht bewusst davon ab — das ist für Stufe 1
  (Capture ohne DSP) in Ordnung, für Stufe 2 mit F4 abzugleichen.

---

## 5. Offene Punkte

1. **Nicht bewiesen, nur sehr gut gestützt:** dass `bus-demod` das fehlende Stück ist. Bewiesen ist
   (a) der Adressraum gehört zum Trident-Frontend (Stock-DTB `io-space-n` mit `0x6144000` neben
   CIP/Demux/CI), (b) `0x06700000` desselben Raums liest ohne `bus-demod` 0 und mit `bus-demod`
   `0x7ff`, (c) `0xd64 = 0`, (d) `snd_alsa_trid.ko` schaltet selbst nichts an. **Nicht** gemessen
   ist ein `0x0614xxxx`-Lesevorgang mit `bus-demod` an — das ist Schritt 8/10 (Paket A0).
2. **`0x06700000 = 0x003003FF`:** Feldbedeutung unbekannt. Mit `bus-demod` las es `0x7ff`; Stock
   setzt zusätzlich Bits 20/21 und löscht Bit 10. Ob eines davon den Audio-Zweig freigibt: offen,
   aber mit der Trennschärfe-Reihenfolge aus §3 in einem Lauf entscheidbar.
3. **`0xd80` Bit 30/31:** die Vendor-Tabelle nennt beide als Gates (`bus-hdmi-audio` Bit 31,
   `bus-cap-300M` Bit 30) und es gibt dort keinen Reset. Bei `0xa70` (USB-PHY0) ist Bit 30 dagegen
   ein Reset — die Namensgleichheit des Bits über Register hinweg gilt also nicht. Ich folge der
   Vendor-Tabelle.
4. **`hdmi_audio` läuft rechnerisch auf 2400 MHz statt 1152 MHz.** `0xd84 = 0x80000000` = Mux 0
   (`pll-video3-4x`) durch 1, und `pll-video3` steht bei uns auf N-Feld `0x63` ⇒ VCO 2400 MHz.
   Stock erreicht 1152 MHz, indem `tvtop` **`clk_set_rate` auf `pll-video3`** ruft (N-Feld 47).
   `clk_set_rate` auf TV-PLLs ist der dokumentierte Freeze — also **pll-video3 nicht anfassen**.
   Zwei rate-freie Auswege, falls sich der Takt als relevant erweist: `0xd84 := 0x80000001`
   (2400/2 = 1200 MHz) oder `0xd84 := 0x81000000` (Mux 1 = pll-periph0-2x = 1200 MHz). Ob 1152 MHz
   exakt gebraucht wird oder nur „ungefähr 1,2 GHz", ist offen (F2/F3). Für die reine
   Registererreichbarkeit sollte der Takt egal sein — der Registerbus hängt am Bus-Gate.
   Laut Vendor-Tabelle hängt an `pll-video3-4x` sonst nur `cip-mts0` (Mux 2, bei uns Mux 0).
5. **`audio_ihb` Ist 162 MHz statt Soll 200 MHz** (Mux 0 = pll-video0-4x statt Mux 1 =
   pll-periph0). Ob der Registerbus des Audio-Blocks an `audio_ihb` hängt und ob die Rate zählt:
   offen. Das Rezept lässt beide Varianten zu (`--ihb-stock`).
6. **Erwartungswerte der Audio-Register nach dem Einschalten fehlen** — im Baum liegt kein
   Stock-Dump von `0x0614xxxx` (`stock_extended_dump_*.txt` decken nur AFBD/VBlender/OSD/LVDS/
   TVTOP/GE2D ab). Der März-Handoff belegt nur *funktionale* Zugriffe. Daher die Schreib-Lese-Probe
   und die Fs-Probe als Kriterien.
7. **Widerspruch März ↔ heute:** `re/notes/AGENT_HANDOFF_AUDIO_MIPS_DSP.md` meldet, dass die
   DSP-Mailbox `0x0614400c`/`0x06144010` damals *funktionierte* (Write-Read-Roundtrip, Bit 5).
   Unter welcher Boot-Kette (Vendor-Bootloader? `CONFIG_SUNXI_TVTOP=y`?) steht dort nicht. Wäre
   damals `tvtop` gebunden gewesen, wäre das die direkte Bestätigung der These — nachprüfbar nur
   in den März-Artefakten.
8. **Was der MIPS tut**, wenn der Demod-Bus plötzlich lebt (er bedient TVTOP-A zeigerbasiert),
   gehört zu F2. Für A0 gilt das Protokoll aus doku/78: kurze Schritte, 20–30 s Timeout.
9. **Doku-Korrektur nötig:** `re/notes/CURRENT-TRUTH.md` und `re/notes/audio__d6564430.md`
   behaupten „Card 0 physisch nicht mit dem Lautsprecher verbunden" und „Audio braucht MIPS App
   Ready". S16 hat am 08.09. mit `speaker-test -D hw:0,0` und 83 dB am Mikro das **Gegenteil**
   gemessen, und die MIPS-App läuft seit doku/97. Beide Notizen sollten korrigiert werden, sonst
   führen sie F4 in die Irre.
10. **Stock-`pd_tvcap` ist ein Null-Eintrag** (§2b) — Stock schaltet die Domäne nie wirklich.
    Unser PPU-Treiber behandelt sie als echt und misst sie als „an". Kein Handlungsbedarf, aber
    falls TVCAP je Probleme macht, ist das der Ort.

---

## Erzeugte/berührte Dateien

| Datei | Was |
|---|---|
| `analyse/hdmi-seq/audio_top_enable.py` | **neu** — Einschaltrezept aus §3, ohne Argument rein lesend |
| `analyse/ida/db-audio-vmlinux/` | Arbeitskopie der Stock-`vmlinux`-DB (Original in `re/ida/` unberührt) |
| `analyse/ida/db-audio-trid/` | Arbeitskopie/DB für `snd_alsa_trid.ko` |
| `analyse/ida/ida_a0*.py`, `ida_a2*.py`, `ida_a3*.py`, `ida_a4*.py`, `gdb_a0*.gdb`, `scan_a05_fenster.py`, `dis_a07_trid.py` | Abfragen dieser Sitzung |
| `re/captures/weltneuheit/audio-a*-20260908.log` | Rohausgaben dazu (u. a. `a02` = volle CCU-Tabellen, `a05b` = Fensterscan, `a07` = `audio_top_clk_init`, `a42` = DSP-Mailbox) |

Ausgewertet, nicht verändert: `analyse/hdmi-seq/vendor-ccu-table.txt`,
`analyse/hdmi-seq/ccu-dump-after-prep-20260907.txt`, `analyse/hdmi-seq/tvfe_enable.py`,
`analyse/hdmi-seq/tvtop_stock_clks.py`, `legacy/drivers/tvtop/`, `legacy/drivers/audio/bridge/`,
`re/vendor/HY310/extracted/bootpkg-full.dts`.

**Methodischer Nebenbefund für kommende Sitzungen:** `re/vendor/HY310/extracted/vmlinux.elf` ist
ARM 32-bit **mit vollständiger DWARF-Info** (`.debug_info` 164 MB). Tabellen daraus lassen sich mit
`gdb -batch` typisiert und exakt auslesen, statt sie aus Disassembly zu rekonstruieren — deutlich
schneller und sicherer als der IDA-Weg. Die MCP-Server `ida-headless` und `ida-pro-mcp` waren in
dieser Sitzung nicht verbunden (`ida-pro-mcp`: fehlendes venv unter `~/.idapro/mcp-venv/`);
`idalib` direkt per `PYTHONPATH=/opt/ida-pro-9.1/idalib/python` lief einwandfrei.
