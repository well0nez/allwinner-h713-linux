# U-Boot-Änderungen für HY260_QZ713_V3.1

**Die Patchdateien hier werden erzeugt, nicht gepflegt** (seit 12.09.2026, P3):
`git format-patch --no-signature 8fe568cdfc46..<Kopf>` im Submodul-Checkout
`mainline/external/u-boot` (Zweig `h713-hy310`, Basis ist cstengers `h713`),
zuletzt am 16.09.2026 bis 4c7e49b. `SERIES.txt` nennt Basis, Kopf und Anzahl. Wer etwas ändern
will, ändert den Fork und lässt neu erzeugen. Diese Seite erklärt, *warum* die
Änderungen so aussehen - der ursprüngliche Text vom 31.08. steht unten.

Alle vier Befunde sind auf Hardware verifiziert und aus dem Vendor-U-Boot
(`re/vendor/HY310/extracted/u-boot.fex`, Thumb-2, Basis `0x4a000000`) belegt.

## Was drin ist

**`drivers/clk/sunxi/clk_h713.c`** - eigene CCU-Tabellen statt der
D1-Wiederverwendung. Auf dem H713 liegen die USB-Register **8 Byte**
auseinander, auf dem D1 nur 4: Port 1 ist `0xa78`, nicht `0xa74`, und es gibt
einen dritten Port bei `0xa80`. Mit der D1-Vorgabe bekommt OHCI1 seinen Takt
nie und der erste Registerzugriff hängt das Board auf.
Belegt im Vendor-Binary bei `0x4a045e12`: `cmp r0, #1` gefolgt von
`ldr r2, =0x02001a78`. Deckt sich mit dem H713-CCU-Treiber aus dem
well0nez-Kernel (Patch 0001).

**`drivers/phy/allwinner/phy-sun4i-usb.c`** - H713-Eintrag, den U-Boot gar
nicht hatte:

- `pmu_enable_bit0`, portiert aus well0nez' Kernel-Patch 0005. Ohne das
  BIT(0) an der PMU-Basis bleibt die PHY aus.
- `hci_phy_ctl_clear = PHY_CTL_SIDDQ`. Die HCI-PHYs starten mit SIDDQ
  (Bit 3 bei PMU+0x10) gesetzt, also im Power-Down. Der Vendor löscht es
  mit `bic r3, r3, #8` bei `0x4a045ee8`. Der Kernel darf das weglassen,
  **weil dort vorher das Vendor-U-Boot lief** - siehe `usb.md` im
  well0nez-Baum: „the kernel doesn't re-init from scratch". Ist U-Boot
  selbst die erste Stufe, muss es das übernehmen.
- `num_phys = 2`, nicht 3: U-Boots H713-CCU reicht nur bis Port 1.

**`sun50i-h713-hy200-qz713df-a1.dts`** - `r_pio` bei `0x07022000` ergänzt
(die PL/PM-Bänke fehlten komplett, ohne sie schlägt jedes `gpio_request` auf
PL mit `-ENOENT` fehl), dazu `ehci0`/`ohci0` und `ehci1`/`ohci1`.

**`board/sunxi/board.c`** - PB5 und PL3 werden jetzt in `board_late_init`
gesetzt statt in `board_init`, und **über Pin-Namen statt Legacy-Nummern**.
In `board_init` ist die GPIO-Uclass noch nicht oben, `gpio_request` scheitert
still. Und die lineare Nummerierung (32 Pins ab PA=0) passt nicht zu den aus
dem DT registrierten Bänken: `SUNXI_GPB(5)` traf einen anderen Pin (Aufruf
erfolgreich, Lüfter blieb aus), `SUNXI_GPL(3)` löste gar nicht auf. Die
Rückgabewerte werden jetzt geprüft und gemeldet.

## Defconfigs

| | |
|---|---|
| `hy310_qz713_v3_1_defconfig` | wie sein Bench-Config, nur `CONFIG_DRAM_CLK=792`. Gadget-Modus, also `ums` und Fastboot nutzbar |
| `hy310_host_defconfig` | dasselbe ohne MUSB und Gadget. Nur so geht die USB-A-Buchse als **Host** - die Weiche `phy0_dual_route` hängt in `phy-sun4i-usb.c` an `#ifdef CONFIG_USB_MUSB_SUNXI`, nicht an einer Laufzeit-Entscheidung |
| `hy310_felmmc_defconfig` | Restore-SPL für FEL, mit `h713_spl_payload.h` |

## Was auf diesem Board wo hängt

| Port | | |
|---|---|---|
| 0 | externe USB-A-Buchse | OTG. FEL und `ums` laufen darüber. Als Host nur mit `hy310_host_defconfig` |
| 1 | intern | Realtek `0bda:5803` „Generic HD camera", 480 Mb/s, Anschluss `CAM`. Versorgt über **PL3**, im Stock-GPIO-Map als `cam-usb-power-gpio` - der Name ist wörtlich gemeint |
| 2 | | vom Kernel registriert, nichts dran |

`PB5` schaltet Lüfter **und** Lampe gemeinsam. Niemals auf LOW.

## Stand 2026-08-31

Mit `hy310_host_defconfig` geflasht bootet der arm64-Kernel 6.18.38 durch:
vier Kerne bei EL2, alle sechs USB-Controller, an Bus 1 ein High-Speed-Hub
mit vier Ports, eMMC bei HS400 mit allen 26 Partitionen. Die Panik am Ende
ist erwartet - `root=/dev/mmcblk0p26` ist `UDISK` und leer.

## Zurückspielen

Die Serie liegt als `git format-patch`-Dateien daneben, fünfzehn Stück auf
`8fe568cdfc4`. Sechs davon sind PR #1, neun sind die Display-Arbeit.

```
cd mainline/external/u-boot
git am ../../../uboot-h713/00*.patch
```

Der Arbeitsbaum steht auf dem Branch `h713-display` (Stand 10.09.2026: Commits bis `0022`, Arbeitsbaum sauber, 6 Commits vor `fork/h713-display`);
die Patches sind nur die Sicherung, falls das Submodul zurückgesetzt wird.

`0017`-`0021` sind Gate, SMM-Heap, elog-Option, GP5-Meldungen und die Default-Env (`doku/30` §15, `doku/105` §1.2). **`0022`** ist der
einzige generische Patch der Serie: `env/mmc.c` reichte einen `CONFIG_ENV_OFFSET` ≥ 2 GiB durch ein `int`, wodurch die Env am HY310 bei
`0x65d80000` statt `0x93d80000` landete (`doku/30` §16). Kandidat für einen PR an cstenger/upstream.
