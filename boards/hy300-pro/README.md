# HY300 Pro

The first foreign device this project met: reported in
[issue #1](https://github.com/well0nez/allwinner-h713-linux/issues/1) on 13.09.2026 by its owner
(GitHub `fightforlife`). He ran the installer in dump-only mode and `h713-extract` over his dump, and from
16.09.2026 on flashed TEST images built for this board, with his full dump as the way back. No image of his
firmware exists here; everything below comes from what he posted.

| | |
|---|---|
| Status | **partial** - in test by its owner, no green run |
| Verified by | nobody |
| Profile | `installer/h713/profiles/hy300_pro.py` |
| Image | **TEST images** for its owner only (`--test-image`): `hy300-pro-test9` (25.09.) is the last; `test10` follows after the v0.96-beta release. No release image until a green report |
| Kernel DTB | `sun50i-h713-hy300-pro` (patch 0161): `sun50i-h713-hy310.dts` included under this board's own name (0181), plus the lamp's PWM words (0166a), no pwm-backlight (0161a), its display firmware's elog addresses (0161b) and its own focus motor tables (0182) |
| U-Boot base | `hy300_pro_defconfig` (his DRAM block at 636 MHz, U-Boot tree `sun50i-h713-hy300-pro`) |
| DRAM | DDR3 (type 3), **636 MHz**, 1 GiB - the 24 boot0 words of his probe run of 2026-09-14 (`uboot.config`) |
| Panel | project id `0x34`, 1280x720 single port, 1360x760, 62 MHz - his `panel_config.ini` (posted 15.09.) and U-Boot on his unit (test8: "firmware left 1280x720 active, 1360x760 total") |
| Lamp | `[PWMSetting]` channel 5, polarity 1 (low active), 40 kHz, vsync lock 1, duty 1..100 (his ini) |
| eMMC | 15 269 888 sectors, 25 partitions, a single `Reserve0` |
| Stock | Android 10 (32-bit, ARMv7 kernel 5.4.99), ADT-3 build 6245789, vendor U-Boot of Dec 2024 |
| display.bin | 1 253 136 B, `cf9649bc...` - his own revision, U-Boot's row "HY300 Pro", HDCP wait site `0x4b13d1b0` |

## Not the HY200 QZ713DF A1

The maintainer's HY300PRO-G-EU is a HY200 QZ713DF A1 (`boards/hy200-qz713df-a1`); this board is not, on
the evidence. Where both are measured, the hardware differs: the fan tacho is **PH17** here (his stock
`fan_ctrl`, and our tacho counted on his unit) and PH13 on the A1 (its stock trees, 5520-5610 rpm on the
GEU); the DRAM PHY tuning `tpr11/tpr12` is `0x44440000/0x5555` here and `0x44340000/0x6666` on the A1,
equal in both A1 firmwares - here it is the HY300 T08's and the HY350's. His firmware is the T08's family
(ADT-3 build 6245789, project 0x34), not the A1's Android 11. The rest does not separate them: panel and
lamp words are equal, `tpr0..tpr2` are a boot0's own computation at its clock (`hy200-qz713-v2` README),
the partition table and display.bin are firmware. His motor tables are neither A1 firmware's. The
measurement that would settle it is the silkscreen; the photos in the issue's "Device data" are not in our
text copy, and the owner can read it off the board.

## The test images

| Image | What happened |
|---|---|
| `test1`, `test2` | deleted. `test2` hung in the display bring-up: the HY310's fixed LogoRegData offsets ran past his 13-descriptor file; U-Boot reads the groups out of the file since |
| `test3` | kernel up, Wi-Fi, HDCP 2.2; no boot logo, no HDMI input (the ARISC's SRAM addresses are not the HY310's) |
| `test4` | `0091a` resolves those addresses from the loaded ARISC image; first A/B for the 0x34 panel |
| `test5`, `test6` | 19./20.09.: HDMI input detected (0136), then the picture at every resolution, skewed |
| `test7` | 23.09.: geometry (`0133d`), gamma from his own TSE, presets from his `tvpq.db`; 720p/1080p right, the picture dark against stock |
| `test8` | 23.09.: the lamp's six PWM words plus a PA12 pin group; "unsupported function pwm5 on pin PA12", the receiver never probed, no login |
| `test9` | 25.09.: the group gone, the words kept. 27.09.: both boots stop at different places, `/dev/video1` never appears |

**What test9's failure was.** 0166 sent the six PWM words as six call parameters; the display firmware
takes one, the address of a 24-byte structure, and read the channel number 5 as an address. On the
HY300PRO-G-EU the same words killed two boots 0.6-0.9 s after that step and the board booted without
them; kernel 0168 sends the address and fixed it there (03.10.). test8 never reached the step (its
receiver did not probe). Not the cause: `of_pwm_get(): can't parse "pwms" property` is the board
manager's fan0 without a PWM, in every boot of his since test3. A second fault shows in both test9 logs:
U-Boot ran **project 0x30** ("panel 1920x1080 dual-port", `ProjectID_0x0030.TSE`, the boot logo refused)
where test8 ran 0x34 - the environment's `h713_project` was the image default, not his board's.

## What test10 must contain

- kernel **0168** (the words by address) and **0182** (his motor tables);
- U-Boot `2de0cc8` - LVDS 8 bit for project 0x34; his own LogoRegData record says 8 bit (`05800000 =
  01e0a40c`), which test8's U-Boot rewrote to 6 bit (`01e0a404`);
- `h713-tv` with the three-channel gamma of his own TSE;
- `h713_project=0x34` in the environment: the install must print "Environment: stored what the board
  declares: h713_project=0x34" and U-Boot "project 0x34, panel 1280x720 single-port". Today's installer
  takes the panel facts from his first install's dump when the device carries our layout; why test9's
  install left the default 0x30 is not in his logs (his install output was not posted).

Unchanged and his own: display.bin `cf9649bc`, the 25-entry table with one `Reserve0`, 636 MHz. 0168's
handler was read in the HY310's display.bin revision, not in his; that his boots broke the same way since
the property arrived is the evidence that his firmware takes the same argument.

## Optional hardware (`FEATURES`)

Unset - nothing of it was seen working under our firmware on his unit:

- **accelerometer**: something answers at 0x18 on twi1 (his stock log: an `stk83xx` input device at
  `1-0018`); our tree drives an SC7A20 there, so which chip it is decides whether ours drives it;
- **focus motor**: his stock tree enables `motor_ctr` with tables of its own (0182 carries them); nobody
  has seen it move under our firmware;
- **camera**: nothing in his logs or stock tree shows one.

## What we do not know

- whether 636 MHz holds under sustained load with our SPL (his own boot0's clock; boots so far are short);
- which pad PWM channel 5 leaves the SoC on, and whether the PWM words brighten his picture at all;
- the limiter's active level of his focus motor (his tree names the pin only);
- the silkscreen of the board.

The honesty rule (`boards/README.md`) holds: until he reports a green run, this board stays `partial`.
