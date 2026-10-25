# LOSEI X9

An LCD projector sold on Amazon EU, reported in
[issue #3](https://github.com/well0nez/allwinner-h713-linux/issues/3) on 25.10.2026 by its owner
(GitHub `cosmonet-fr`). He followed the docs read-only: `h713-install identify` on a dump of the
first 36 MiB of his eMMC, `h713-extract --profile` over his partition backups, and
`u-boot-h713-probe.bin` over FEL with the UART connected. He has a full backup of every partition.
No stock image and no dump of this board exist here; everything below comes from what he posted.

| | |
|---|---|
| Status | **partial** - the description has holes, see the last section |
| Verified by | nobody |
| Profile | `installer/h713/profiles/losei_x9.py` |
| Image | none, and no test image either: nothing of ours drives this board's pins yet |
| Kernel DTB | none (`KERNEL_DTB` empty) - its pin map is not any of our trees |
| U-Boot base | none; `uboot.config` holds its DRAM block, read off the device |
| DRAM | DDR3 (type 3), **744 MHz**, 1 GiB - the 24 boot0 words at LBA 16, from his probe run |
| Panel | project id **`0x33`**, 1280x720 single port LVDS, 1600x755 total, 72.48 MHz, 60.00 Hz |
| Lamp | backlight PWM **channel 0** at 480 Hz, polarity 0 (his `[PWMSetting]`); enable line PB6 |
| eMMC | 8 GB (15 269 888 sectors), **21 partitions, no A/B slots**, a single `Reserve0` |
| Stock | Android 10, ADT-3 build 6245789, vendor U-Boot and ARISC of Sep 21 2024 |
| display.bin | 1 252 112 B, `49f698af...` - a revision of its own, HDCP wait site `0x4b13d140` |
| PCB | silkscreen `MTL-H713-Z10-V1.0`, `VER0001`; Wi-Fi/BT AIC8800D80 (SDIO) |

## Where the facts come from

One source, three outputs of his, all read-only (issue #3, 25.10.2026):

- **DRAM** - the 24 words of the vendor boot0 at LBA 16 + 0x38. `h713_probe` read them on the device
  and `h713-install identify` printed the same block from his dump; both agree. The block is the
  HY300 T08's word for word except the clock (744 against 640 MHz) and the PHY tuning
  `tpr11`/`tpr12`, which is the HY310's pair here. Note `para2` = 0 and `tpr13` = `0x34010100`:
  read off his eMMC, and still bit for bit the HY300 T08 *image's* unpatched pair. Our SPL reads
  bits of both that differ from the pair it has run with (`0x04000000` / `0xb4016103`), so no
  build uses them until a run with the proven pair at his clock has worked.
- **Panel** - `vendor:/etc/tvconfig/panel_config/panel_config.ini`, as `h713-extract --profile`
  derived it into a panel row (`panel.env`, 10 checks OK, 1 WARN). Project id `0x33` is **new**:
  `h713_disp_panels[]` in the U-Boot fork knows `0x30` (1920x1080 dual) and `0x34` (1280x720
  single) only. The WARN is C8: this panel dims on PWM channel 0, our dimmer is pinned to PWM2 on
  PB4 - and PB4 is this board's fan (below).
- **Layout** - 21 GPT entries with no A/B pair anywhere, plus a `recovery`, a `cache` and a `swap`
  no other board of ours has. An installer must not carry another board's constants here.
- **Identification** - the vendor fingerprint is the ADT-3 family's (`6245789`), which the HY300 T08
  and the HY350 share, and his `database.TSE` is byte-identical with the HY300 T08's. Neither tells
  the boards apart, so the profile's `strong_features` rely on the `scp`/`u-boot`/`dtb` digests and
  the two version strings of Sep 21 2024.
- **MIPS artifacts** - only in `vendor:/etc/display/mips/` (ext4 inside `super`). His `bootloader`
  FAT16 has no `mips/` directory at all; the single `bootloader` partition holds the logos, the
  fonts, `magic.bin` and `wavefile`. `h713-extract` handles that source (as for the HY300 T08 and
  the HY350); U-Boot cannot reach it, which is why his probe found no `display.bin`.

## The pin map is not ours

Read by the owner from the stock Android (`/sys/kernel/debug/gpio` plus its device tree). The two
lines that matter are swapped against every tree we ship:

| Function | This board | Ours (HY310 family) |
|---|---|---|
| Fan on/off | **PB4** | **PB5**, shared with the backlight enable |
| Lamp / backlight enable | **PB6** (`timing_bl`) | **PB5** (the same line) |
| Backlight PWM | channel 0, 480 Hz | PWM2 on **PB4** (HY310 tree), channel 5 (0x34 boards) |
| USB-A VBUS | PC2 (USB1) | PL3 |

So none of our trees fits: the HY310 tree puts a 25 kHz `pwm-backlight` on PWM2/PB4 (kernel patch
`0032`; the HY300 Pro and HY200 trees switch it off), which here is the **fan**, and every one of
them treats PB5 as fan and lamp. That is the reason `KERNEL_DTB` is empty and no test image exists:
nothing is driven on this board's pins before its own tree exists (the PB5 incident of 19.09.2026).
The probe built for it (`h713_probe_x9_defconfig` in the U-Boot fork) drives no power line at all.

The rest of his map, for that tree, when someone writes it: panel power/standby/reset PH19/PH13/PH10,
focus motor phases PF0-PF3 (4-phase, 8-step table), keys `key_clk`/`key_vol` PF5/PF6, power key PL4
(active low), speaker amp enable PL2, status LED PL5, USB1 VBUS PC2, WLAN hostwake/reg_on PM0/PM1,
BT wake/hostwake/reset PM2/PM3/PM4, accelerometer LIS3DH on i2c-2 at 0x19, UART0 pads `GND TX RX`
next to the power button at 115200 8N1. FEL: the button at the board edge next to the audio jack,
held while applying power; USB-A port; `1f3a:efe8`, SoC `0x1860`.

## What his probe log does and does not show

It shows our SPL training this RAM and U-Boot coming up with 1 GiB, over FEL, with the coprocessor
in reset and the panel dark. It does **not** show this board's `uboot.config` working: that probe
build (U-Boot `2ba4003276ba`, 14.09.2026) ran the probe's own DRAM set at 624 MHz with the HY200
QZ713DF A1 device tree, not his clock, and its `Model:` line names that board (`TODO.md` 4.13).
He also reports that the HY300 T08's `fes1.fex` (DDR3, 640 MHz) trained this RAM with a write/read
test at `0x40000000`. A run at 744 MHz is still to be done.

That build also raised **PB5 and PL3** on start-up (`CONFIG_H713_POWERON_LIGHT_FAN`, as
`docs/tools/h713-probe.md` describes for our boards). On this board neither is known to be what
it is on ours; he reports nothing broke.

## What we do not know

- **The `monitor` and `optee` digests.** Our own `h713-extract` cut them to sixteen hex in its
  report (fixed since), so the profile leaves both items out instead of carrying half a hash; his
  next extract run prints them whole.
- **`sunxi_version`.** His input is a partition backup, not a stock image, so the string is absent;
  `identify` prints `-` for it and the profile says `None`.
- **Which project id the board actually runs.** Its `panel_config.ini` declares `0x33` and the
  descriptor `ProjectID_0x0033.TSE` is there, but the used id is read out of `display.bin`, and this
  revision is in no table of ours. 14 descriptors are present, `0x51` among them, which no other
  board of ours carries.
- **The four register reads of the panel row** (`PANEL_LVDS_BITSEL`, `PANEL_SSC_MASK`,
  `PANEL_SSC_REG`, `PANEL_LAYER_H_MASK`): no ini carries them, they are read on a running device.
- **Whether the lamp follows a PWM here at all.** On the HY310 it does not (the lamp follows the SoC
  rail); on this board the enable line is PB6 and the backlight PWM is channel 0, both untested.
- **The fan.** Its stock driver fails on this board too (`pwm-fan: probe of fan0 failed with error
  -16`), and we have no tacho pin for it.
- Camera, focus end switch and the keystone sensor's axes: nothing measured.
