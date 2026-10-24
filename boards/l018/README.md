# L018

The maintainer's own L018 (2025), still on its stock Android 11 when this directory was written. Its stock
update.img is in the local firmware archive; on 24.10.2026 the image was held against a running unit (read
only, over ADB) and its own device tree and pin state were held against the HY310's. The board turned out to
be the HY310's twin in everything the boot chain depends on, and different in what hangs on the pins around
it.

| | |
|---|---|
| Status | **profile-only** - nothing of ours has run on it; a TEST image is built for its owner (`--test-image`) |
| Verified by | nobody |
| Profile | `installer/h713/profiles/l018.py` |
| Kernel DTB | `sun50i-h713-l018` (patch 0331): `sun50i-h713-hy310.dts` plus the differences below |
| U-Boot base | `hy310_defconfig`, unchanged - the DRAM block is this board's boot0 word for word (`uboot.config`) |
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
| PH4/PH5 | focus motor phases | **twi2** (fn 5), the accelerometer's bus | `motor_ctr` off |
| PH6/PH7 | focus motor phases | fn 2 (uart4) | `motor_ctr` off |
| Accelerometer | SC7A20 at 0x18 on twi1 (PH2/PH3) | `lsm6dsv` at 0x6a on twi2, driver bound under stock; PH2/PH3 disabled | `twi1` off; the sensor is not described yet |
| Fan tacho | PH17 | PH13 (stock `fg-gpio`, EINT under stock) | `fg-gpio` PH13 |
| Fan speed | on/off on PB5 | PWM0 on **PH17** (fn 3): 95/70/60 % with the lamp at high/std/low; PB5 the rail as on the HY310 | PH17 held high (100 %, the top of the stock duty tables) |
| Lamp | not dimmable | PWM2 on **PB4** (fn 2), 25 kHz; **dims as the duty rises**: the three stock modes switched on the unit read high 30 %, std 50 %, low 75 % (the stock fan node's `bl0` duty-array 50/75/30/75), PWM3 stays off | the dtsi's pwm-backlight, `brightness-levels <100 75 50 30>`: 75 = high (the brightest stock drives), 50 = std (start), 25 = low |
| Focus motor | PH4..PH7, end switch PH14 | PF0..PF3 (outputs under stock), end switch PB1; app `com.hysd.vafocus` | not described yet |
| Camera | Realtek `0bda:5803` | `4098:a425` "HYSD-VAF02-ZH04", UVC, with a HID button | nothing needed (USB) |
| Panel keys | 6 | none but the power key (owner, 24.10.2026); the seven LRADC keys of the stock tree are its template | - |
| LEDs | - | power PL0, status PL1 | not described yet |
| Audio | - | headphone jack and SPDIF pins enabled in the stock tree | not described yet |

## Known deviations of the TEST image

- U-Boot (`hy310_defconfig`) runs the HY310's panel sequence for project 0x30 and drives **PF6 high**, which
  this board's stock leaves disabled, and **PH9 high**, which it drives low. Neither pin is named by the board's
  stock tree outside pin groups and the template `battery` node. If the picture comes up mirrored or not at
  all, these two are the first suspects; taking them out needs a U-Boot change of its own.
- Brightness 0 switches PWM2 off (the driver clears the channel's enable and clock gate). What the pin and
  the lamp do then is not measured; nothing of ours writes 0.
- The fan runs at full speed.

## Not measured

Nothing of this directory has booted. The installer has not run on the board. The accelerometer's axes, the
camera's formats and the motor are unmeasured under our system.
