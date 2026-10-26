# L018

The maintainer's own L018 (2025), still on its stock Android 11 when this directory was written. Its stock
update.img is in the local firmware archive; on 24.10.2026 the image was held against a running unit (read
only, over ADB) and its own device tree and pin state were held against the HY310's. The board turned out to
be the HY310's twin in everything the boot chain depends on, and different in what hangs on the pins around
it.

| | |
|---|---|
| Status | **profile-only** - a TEST image (`--test-image`) runs on its owner's unit since 25.10.2026; not verified |
| Verified by | nobody |
| Profile | `installer/h713/profiles/l018.py` |
| Kernel DTB | `sun50i-h713-l018` (patch 0331): `sun50i-h713-hy310.dts` plus the differences below |
| U-Boot base | `l018_defconfig` = `hy310_defconfig` (the DRAM block is this board's boot0 word for word) + `CONFIG_H713_BOARD_L018` (fork `0103`): dark gate, stock std mode, PH9 low, PF6 untouched |
| DRAM | DDR3 (type 3), 792 MHz, 1 GiB: the 24 boot0 words of the stock image, equal to the HY310's |
| Panel | project id `0x30`, 1920x1080 dual port, 2128x1120, 143.0016 MHz - the HY310's; its `panel_config.ini` differs in `pwm_channel` (3, HY310 2) and `default_backlight` (50, HY310 100) only |
| display.bin | 1 256 216 B, `16c74a28...`, the HY310's revision; of the 19 files in `mips/` only `database.TSE` differs |
| eMMC | 15 269 888 sectors, 26 partitions, `Reserve0_a/_b` - the HY310's GPT, the same table on the image and on the unit |
| Stock | Android 11, `Projector05141211` (built 2025-05-14), ARMv7 32-bit kernel 5.4.99; vendor U-Boot 2018.05-00025 |
| Wi-Fi | AIC8800D80 on SDIO (`c8a1:0082`), as on the HY310 |
| Remote | the HY310's: NEC customer code `0xfd02`, every key captured under stock is in `rc-h713-fd02` (24.10.2026) |
| Secure storage | HDCP 1.4/2.2, MAC addresses, serial number, and the factory calibration of camera and tilt sensor (`JbCamX/Y`, `PoCamX/Y`, `GsInitXYZ`); item names read on the unit, contents not read. Layout v4 never writes it |

## Where it differs from the HY310

From the board's stock device tree (`vendor_boot`; the sunxi package's tree decompiles to the same text), the
HY310's stock tree beside it, and the pin controller of a running unit under stock (configuration registers
and `pinmux-pins`, 24.10.2026). "fn" is the pin function number of our pinctrl table.

| What | HY310 | L018 | In patch 0331 |
|---|---|---|---|
| PH4/PH5 | focus motor phases | **twi2** (fn 5), the accelerometer's bus | `twi2` described (stock: SPI 9, 100 kHz) |
| PH6/PH7 | focus motor phases | fn 2 (uart4) | not used |
| Accelerometer | SC7A20 at 0x18 on twi1 (PH2/PH3) | `lsm6dsv` at 0x6a on twi2, driver bound under stock; PH2/PH3 disabled | `twi1` off; `st,lsm6dsv` at 0x6a on twi2, no interrupt (`st_lsm6dsx`, a module; h713-keystone reads it through sysfs); IIO name `lsm6dsv_accel`, axes and the board's throw ratio in `board.env` `KEYSTONE`, measured in the stand 25.10.2026 (roll's sign not measured). *Superseded (25.10.2026):* "its IIO name and axes are not measured" |
| Fan tacho | PH17 | PH13 (stock `fg-gpio`, EINT under stock) | `fg-gpio` PH13 |
| Fan speed | on/off on PB5 | PWM0 on **PH17** (fn 3): 95/70/60 % with the lamp at high/std/low; PB5 the rail as on the HY310 | the board manager's `fan0` (`duty-array-policy1 <70 60 95 70>`, kernel 0332), set with the lamp; U-Boot sets the stock std before (2880/3210 rpm at low/std, 25.10.2026) |
| Lamp | not dimmable | PWM2 on **PB4** (fn 2), 25 kHz; **dims as the duty rises**: the three stock modes switched on the unit read high 30 %, std 50 %, low 75 % (the stock fan node's `bl0` duty-array 50/75/30/75), PWM3 stays off | the board manager's `bl0` (stock duty-array, `lamp-mode-names` std/low/high, thermal mode 3), pwm-backlight off; `h713-lamp status \| set MODE`, kept in `/etc/h713/lamp.conf` |
| Focus motor | PH4..PH7, end switch PH14 | PF0..PF3 (outputs under stock), end switch PB1, `motor-cycle` 3; app `com.hysd.vafocus` | `motor_ctr` with PF0..PF3, PB1, cycle 3. On the one unit measured PB1 reads 0 everywhere (dead, a defect of that unit, `doku/220`): the image does no reference run (`board.env` `FOCUS_HOMING=0`), a focus key moves 13 msteps (`FOCUS_STEPS=13`, the travel is ~110). That unit runs an experimental counted range ([h713-focus](../../docs/tools/h713-focus.md)). *Superseded (25.10.2026):* "homing and the end switch's pull-up [...] not measured here" |
| Camera | Realtek `0bda:5803` | `4098:a425` "HYSD-VAF02-ZH04", UVC, with a HID button | nothing needed (USB) |
| Panel keys | 6 | none but the power key (owner, 24.10.2026); the seven LRADC keys of the stock tree are its template | - |
| NTC | none (stock `ntc_num 0`) | GPADC channel 1, its own table 0..55 °C; warn 41, power off 51, resume 34 °C | `ntc_num 1`, the stock table and thresholds (21.4 °C read at a CPU of 49 °C, 25.10.2026; not held against a thermometer yet) |
| LEDs | - | power PL0 (red, `standby_param`), status PL1 (blue, active low); the stock fan driver sets PL0 high, PL1 low at probe | `gpio-leds` `red:power`/`blue:power`, both active low: running, blue on and red off (the stock levels). U-Boot `0105`: red in the gate, blue once started - seen by the owner, 25.10.2026. *Superseded (25.10.2026):* "the colour seen is not measured" |
| Audio | - | headphone jack and SPDIF pins enabled in the stock tree; its own volume curve in `audio_config.ini` (100 = +0.5 dB, the HY310's -9.5 dB) | the speaker plays HDMI and the device's sounds (25.10.2026); h713-tv takes the board's own curve (`board.env` `VOLUME_CURVE=vendor`), 0 dB in the DSP heard clean by the owner; headphones not tested. *Superseded (25.10.2026):* "not described yet" |

## What the first install showed (25.10.2026)

test2 with the HY310's U-Boot base: the picture was **mirrored left-right**, and in the gate **lamp (full) and
fan ran** - the L018's PB5 is ON at its reset level and an undriven PB4 is full light (the HY310's PB5 is off).
Live tests on the running unit: PB5 low switches lamp and fan off, PWM2 at 100 % darkens the lamp, PH9 low at
run time changed nothing. With `l018_defconfig` (fork `0103`) the gate is dark and quiet, the board comes up at
the stock std mode, and PH9 is low before the panel's reset pulse: **the picture is the right way round** and
the PH bank reads `0x0009a100`, the stock value (owner's eyes plus the registers over ssh).

## Known deviations of the TEST image

- The thermal mode (lamp dimmed above 41 °C) is not measured: the NTC has not been near 41 °C. The power off at
  51 °C is armed since 25.10.2026 (`thermal-shutdown` in the tree, as under stock, without a thermometer - its owner has
  none); the power-off itself is not measured.
- *Superseded (25.10.2026):* "From power-on until U-Boot proper runs (SPL, about 1 s) PB5 and PB4 are at their reset
  level: lamp and fan come on briefly" - U-Boot `0104` keeps them off from the SPL on (seen by the owner), and
  "the power off at 51 °C stays disarmed until the NTC is held against a thermometer".
- At boot the lamp starts at std (U-Boot) and changes to the kept mode when `h713-lamp.service` runs, about 3 s
  after the kernel.

## Not measured

Measured on the owner's unit 24.-26.10.2026 (`doku/220`): the lamp modes (registers and by eye), the fan stall shutdown,
the NTC at room temperature, the accelerometer's axes and the keystone with the board's own optics (straight from in front
at 18.6°), the camera and the chessboard autofocus, the Bluetooth remote, HDMI 1080p60 with sound, HDCP 1.4 (the pair of
the measuring rule), video in hardware, its own volume curve (hearing test up to 0 dB). **Not measured:** headphones,
HDCP 2.2, the thermal mode, the power-off at 51 °C; no release image. *Superseded (26.10.2026):* "The accelerometer's
axes, the camera's formats and the motor are unmeasured under our system; the lamp modes' brightness is not judged by eye
yet."
