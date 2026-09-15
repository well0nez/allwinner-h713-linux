# S28 (Paket A) - CCU: `pll-periph0`-Modell und die Audio-/TVFE-Takte

Auftrag [`../101-plan-audio-treiber.md`](../101-plan-audio-treiber.md) §1 Zeile A,
Arbeitsauftrag `analyse/audio/arbeit/t-a-ccu/AUFTRAG.md`. Reine Quelltextarbeit, **kein Board, kein
Bau** (Regel §4). Basisbaum `mainline/build/linux-6.18.38-a3097ce7…` nur lesend, Arbeitskopien
`analyse/audio/arbeit/t-a-ccu/{a,b}/`.

**Ergebnis:** `patches/0134-clk-sunxi-ng-h713-model-pll-periph0-and-the-audio-clocks.patch`
(2 Dateien, `ccu-sun50i-h713.c` + `ccu-sun50i-h713.h`; ersetzt den A1-Entwurf). Der Patch läuft
sauber gegen den Basisbaum (`patch -p1`, Probelauf und Echtlauf, Ergebnis Byte-gleich mit `b/`) und
ist `checkpatch.pl`-sauber (0 errors, 0 warnings, 474 Zeilen).

## 1. Was geändert wurde

| Takt | Register | Modell vorher | Modell nachher | physisch (S17/S27) |
|---|---|---|---|---|
| `pll-periph0` | `0x020` = `b8003100` | `nkmp` ohne `.m`/`.p`, `post 4` → **300 MHz** | `.m` Bit 1, `.p` Bit 0, `post 2` → **600 MHz** | 600 MHz, unverändert |
| `pll-periph1` | `0x028` = `b8006301` | dito → 600 MHz (zufällig richtig) | dito → 600 MHz | 600 MHz, unverändert |
| `-2x` / `-4x` | - | 600 / 1200 | **1200 / 2400** | 1200 / 2400, unverändert |
| `pll-periph0/1-800M` | - | **fehlte** | neu, `-4x`/3 = **800 MHz** | vorhanden (Vendor `hw_clks` 137/138) |
| `ahb` | `0x510` = `03000002` | 100 MHz | **200 MHz** | 200 MHz, unverändert |
| `apb0` | `0x520` = `03000102` | 50 MHz | **100 MHz** | 100 MHz, unverändert |
| `mbus` | `0x540` = `c3000002` | Eltern `{24M, p0-2x, ddr, p0-4x}`, M 3 bit → 400 MHz | Eltern `{24M, ddr, p0, p0-2x}`, M 5 bit → 400 MHz | 400 MHz, unverändert |
| `mips` | `0x600` = `80000002` | Eltern `{24M, p0-2x, p1-2x, cpux}`, M 4 bit → **8 MHz** | Eltern `{p0-2x, video0-4x, 24M}`, M 3 bit → **400 MHz** | 400 MHz, unverändert |
| `ce` | `0x680` = `81000002` | 100 MHz | **200 MHz** | 200 MHz, unverändert |
| `mmc1` | `0x834` = `8100000b` | 25 MHz | **50 MHz** | 50 MHz, unverändert (aber s. §2) |
| **`mmc2`** | **`0x838` = `02000002`** | Eltern `{24M, p0-2x, p1-2x}`, Mux 2 bit; Mux 2 = „`p1-2x`" → 200 MHz | Eltern `{24M, p0-800M, p1-800M, p0-2x, p1-2x}`, Mux 3 bit; Mux 2 = `p1-800M` → 133 MHz | **133 → 100 MHz, Register wird umprogrammiert** (§2) |
| `adc` | `0xd10` = `01000005` | Gate an `ahb`, 100 MHz | `mp`+Mux → **54 MHz** | unverändert (Gate aus) |
| `dtmb-120m` | `0xd18` = `01000004` | Gate an `ahb` | `mp`+Mux → 120 MHz | unverändert |
| `tvfe-1296m` | `0xd20` = `80000000` | Gate an `ahb`, 100 MHz | `mp`+Mux → **1296 MHz** | unverändert (an) |
| `i2h` | `0xd24` = `00000007` | Gate an `ahb` | `div`+Mux 3 bit → 162 MHz | unverändert |
| `cip-tsx/-mcx/-tsp`, `tsa-tsp`, `tsa432` | `0xd28…0xd58` | Gates an `ahb` | `div`+Mux nach Vendor | unverändert |
| `cip27`, `cip-mts0`, `mpg0/1` | `0xd38…0xd60` | Gates an `ahb` | `mp`+Mux nach Vendor | unverändert |
| **`audio-cpu`** | **`0xd48` = `00000002`** | Gate `[31]` an `ahb`, 100 MHz | `div` M[2:0] Mux[24] `{p0-2x, p1-2x}` → **400 MHz** | unverändert (Gate aus) |
| **`audio-umac`** | **`0xd4c` = `00000002`** | Gate `[31]` an `ahb`, 100 MHz | `div` M[2:0] Mux[24] `{p0, p1}` → **200 MHz** | unverändert |
| **`audio-ihb`** | **`0xd50` = `00000007`** | Gate `[31]` an `ahb`, 100 MHz | `div` M[3:0] Mux[26:24] `{video0-4x, p0, p1}` → **162 MHz** | unverändert; Stock will 200 MHz aus `p0` (`0x81000002`) |
| **`bus-demod`** | **`0xd64` = `00000000`** | Gate `[0]` an **`ahb`** | Gate `[0]` an **`pll-video0-4x`** → 1296 MHz | unverändert; Reset `[16]` war schon richtig |
| `tcd3` | `0xd6c` = `80000305` | Gate an `ahb` | `mp`+Mux → 27 MHz | unverändert (an) |
| `vincap-dma` | `0xd74` = `81000001` | Gate an `ahb`, 100 MHz | `div`+Mux → **300 MHz** | unverändert (an) |
| **`bus-hdmi-audio`** | **`0xd80` = `c0000000`** | Gate **`BIT(0)`** → meldet „aus" | Gate **`BIT(31)`** → meldet „an" | Hardware war immer an; `clk_prepare_enable` schreibt **kein** Bit 0 mehr |
| **`bus-cap-300m`** | **`0xd80`** | Gate **`BIT(1)`** | Gate **`BIT(30)`** | dito |
| **`hdmi-audio`** | **`0xd84` = `80000000`** | Gate an `ahb`, 100 MHz | `div` M[4:0] Mux[24] `{video3-4x, p0-2x}` → **2400 MHz** | unverändert; Stock 1152 MHz (S17 §5.4) |

Belege durchgehend: Vendor-Takttabelle `sun50iw12_ccu_clks @0xc1460d70`
(`analyse/hdmi-seq/vendor-ccu-table.txt`, Einträge [18], [19], [55], [102] - [124]) gegen den
Boot-Wortdump des Boards (`analyse/hdmi-seq/ccu-dump-after-prep-20260907.txt`); Herleitung des
PLL-Modells S27 §5/§6/§6.1, Registerkarte `0xd10…0xd90` S17 §1, `bus-demod` S17 §0/§2c.

## 2. `assigned-clock-rates` an `periph0`-Abkömmlingen - die eine physische Änderung

Vollständige Suche über beide Board-DTs und die `dtsi` des Basisbaums (`grep assigned-clock`):
**genau ein Treffer**, `sun50i-h713.dtsi:973` am eMMC-Knoten `mmc@4022000`:

```dts
assigned-clocks = <&ccu CLK_MMC2>;
assigned-clock-rates = <100000000>;
```

Das ist die einzige Stelle, an der das korrigierte Modell beim Boot ein Register anders programmiert:

| | Modell-Elternrate | programmierter Teiler | Register `0x838` | **physisch** |
|---|---|---|---|---|
| heute | 600 MHz („`p1-2x`") | M+1 = 3, P = 0 | `02000002` | 800/3/2 = **133 MHz** |
| nur PLL korrigiert | 1200 MHz | M+1 = 3, P = 1 | `02000102` | 800/3/2/2 = **67 MHz** |
| **PLL + `mmc2`-Eltern korrigiert** | 800 MHz (richtig) | M+1 = 4, P = 0 | `0?000003` | **100 MHz** = DT-Wunsch |

Deshalb ist die `mmc2`-Elternliste in denselben Patch gewandert; S27 §7 hatte sie als „Folgeauftrag"
notiert (Vendor-Eintrag [55]: 3-bit-Mux über `{dcxo24M, p0-800M, p1-800M, p0-2x, p1-2x}`, unsere
Liste kannte die 800-MHz-Abgriffe gar nicht). Der Mux bleibt bewusst **umhängbar** (kein
`CLK_SET_RATE_NO_REPARENT`, anders als der Vendor): der MMC-Kern verlangt bei der Kartenerkennung
400 kHz, und die erreicht nur `osc24M`. Er kann dabei von `p1-800M` auf `p0-800M` wandern - beide
800 MHz, physisch gleichwertig.

Alle übrigen Takte: **kein** `assigned-clock-*`, also beim Boot kein anderer Registerzugriff.

## 3. Risiken

1. **eMMC zuerst.** Das Bootmedium ist der einzige Takt, dessen Register sich durch den Patch beim
   Boot ändert (§2). Er wird **langsamer und richtiger** (133 → 100 MHz), aber er ändert sich. Erste
   Abnahme: Kaltstart und Blick auf `dmesg | grep mmc`, danach ein großes `dd`/`fsck` auf der
   Rootpartition. Rückfall wäre, allein den `mmc2`-Hunk zurückzunehmen (dann 67 MHz - auch lauffähig,
   nur unnötig langsam).
2. **Jeder `clk_set_rate()` unterhalb `pll-periph0` liefert ab jetzt die angeforderte statt der
   doppelten Rate** (S27 §8.1): `mmc0/1` (SD, SDIO/AIC8800), `spi0/1`, `nand0/1`. Die SDIO-WLAN-Karte
   lief bisher mit doppeltem Bustakt und muss neu geprüft werden. Nichts davon ist ein
   Boot-Registerzugriff - die Änderung tritt erst auf, wenn der jeweilige Treiber eine Rate setzt.
3. **`clk_disable_unused` sieht `0xd80` jetzt.** Mit den richtigen Bits 31/30 meldet der Taktbaum die
   beiden Gates als eingeschaltet; ein Kernel **ohne** `clk_ignore_unused` würde sie abschalten und
   damit `bus-cap-300m` unter dem laufenden Capture wegziehen. Beide Board-DTs übergeben
   `clk_ignore_unused` (geprüft: `…qz713-v2.dts:10`, `…qz713df-a1.dts:10`) - bleibt aber eine
   Fußangel, sobald jemand die `bootargs` kürzt. Dasselbe gilt für `tvfe-1296m`, `tcd3` und
   `vincap-dma`, die beim Boot an sind.
4. **Die TVFE-Takte haben jetzt Teiler, also Zähne.** Ein `clk_set_rate()` auf ihnen war bisher
   folgenlos und würde jetzt Register schreiben. Geprüft: **kein** H713-Treiber im Basisbaum ruft
   `clk_set_rate()`/`clk_round_rate()` auf einem davon (`drivers/media/platform/sunxi/sun50i-h713-hdmirx/`
   und die übrigen `sunxi`-Treiber durchsucht). Für Paket B gilt weiter S27 §8.3: die drei
   Audio-Register direkt schreiben, **nicht** über `clk_set_rate`, und **nie** eine TV-PLL setzen
   (Freeze KNOW-20260413-031149-493). Kein Takt hat `CLK_SET_RATE_PARENT` bekommen.
5. **`audio-ihb` steht weiter auf 162 MHz** (Mux 0 = `pll-video0-4x`), Stock nimmt 200 MHz aus
   `pll-periph0`. Der Patch macht das nur *sichtbar und setzbar* (`clk_set_parent`), er ändert es
   nicht. Ob die Insel den Unterschied merkt, ist offen (S17 §5.5).
6. **Nicht gebaut.** Ersatzweise geprüft: alle Elternnamen existieren im Treiber (Skript über die
   `*_parents[]`-Listen und alle `CLK_HW_INIT*`-Namen, 0 Fehlstellen); keine doppelten
   `hw_clks`-Indizes; `.num` deckt den größten Index; Klammernbilanz; und für **jeden** Takt mit Mux
   der Boot-Registerwert gegen die Länge der Elternliste - 44 Takte, alle Mux-Indizes in Reichweite,
   also kein verwaister Takt beim `probe`. Dabei ist ein echter Fehler aufgefallen und behoben: die
   neuen IDs lagen zuerst auf 139/140, und **139 ist bereits `CLK_PLL_AUDIO`** aus dem exportierten
   Binding - sie hätten den Codec-Takt aus der Provider-Tabelle verdrängt.

## 4. Was bewusst **nicht** angefasst wurde

Kein neues `include/dt-bindings/clock/sun50i-h713-ccu.h` nötig: die beiden 800-MHz-Abgriffe sind
treiberintern und stehen in `ccu-sun50i-h713.h` als 143/144, `CLK_NUMBER_INTERNAL` 143 → 145
(Loch bei 140 bleibt, `sunxi_ccu_probe` überspringt `NULL`).

Weitere Abweichungen von der Vendor-Tabelle, die beim Prüfen aufgefallen sind, aber weder Audio noch
`pll-periph0` betreffen - Kandidaten für einen eigenen Patch, hier absichtlich ausgelassen, damit
0134 prüfbar bleibt:

* `timer0…5` (`0x730…0x744`): Vendor Mux `[5:4]`, Teiler `[3:1]`, Eltern `{24M, iosc, osc32k, ahb}` -
  Mainline hat Mux `[25:24]`, M `[2:0]`, P `[9:8]` und drei Eltern. Registerwerte alle 0, darum heute
  folgenlos.
* `ve-core` (`0x690`): zweiter Elternteil `pll-periph0-2x` fehlt (Mux steht auf 0).
* `gpu` (`0x670`): Vendor ist ein 5-bit-Teiler ohne Mux, Mainline ein Mux ohne Teiler.
* `dram` (`0x800`): zweiter Elternteil `pll-periph1-2x` fehlt (Mux steht auf 0).
* `mmc0/mmc1`: Mux ist real 3 bit breit, Mainline nutzt 2 - bei drei Eltern heute ohne Wirkung.
* `i2s2`/Codec tragen laut S17 §4b `CLK_HDMI_AUDIO` unter dem Namen `pll_tvfe`; richtig wäre
  `CLK_TVFE_1296M`. Das ist eine DT-Änderung und gehört zu Paket C/F.

## 5. Wie zu testen (Hauptsitzung)

1. Bau im `h713-build`-Container (doku/50), Kaltstart. **Zuerst** eMMC: `dmesg | grep -i mmc`,
   Rootpartition lesen und schreiben.
2. `cat /sys/kernel/debug/clk/clk_summary` - erwartet: `pll-periph0` 600 MHz, `pll-periph0-2x` 1200,
   `ahb` 200, `apb0` 100, `mbus` 400, `mips` 400, `mmc2` 100, `audio-cpu` 400, `audio-umac` 200,
   `audio-ihb` 162, `bus-demod` 1296 (Gate aus), `bus-hdmi-audio`/`bus-cap-300m` **enabled**,
   `hdmi-audio` 2400. Weicht eine dieser Zahlen ab, stimmt das Modell noch nicht.
3. Gegenprobe am Register: `0x02001d80` muss `c0000000` bleiben (kein Bit 0/1 mehr), `0x02001d48/4c/50`
   unverändert `2/2/7`, `0x02001838` neu mit M-Feld 3.
4. Bild und Capture müssen unverändert laufen (`vincap-dma`, `tcd3`, `tvfe-1296m` sind jetzt
   Teiler-Takte, dürfen aber kein Register bekommen haben).
5. Erst danach Paket B darauf aufsetzen.
