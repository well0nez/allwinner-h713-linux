# HY320

A MagCubic HY320 (sold on AliExpress as "HY320, Android 11, 390 ANSI, 4K native 1080p, an upgraded
HY300"). One unit, its owner's: read in full on 31.10.2026, and the first TEST image of this board
installed on it the same day.

| | |
|---|---|
| Status | **partial** - a TEST image boots on the owner's unit (31.10.2026); the video plane shows since the U-Boot fix of 01.11.2026 (below) |
| Verified by | nobody |
| Profile | `installer/h713/profiles/hy320.py` (`h713-install identify` on the dump: "HY320 matches this dump", on `arisc_version`, `dtb_sha256`, `scp_sha256`, `uboot_sha256`, `uboot_version`) |
| Image | **TEST images** for its owner only (`--test-image`) |
| Kernel DTB | `sun50i-h713-hy320` |
| U-Boot base | `hy320_defconfig` |
| DRAM | DDR3 (type 3), **792 MHz**, 1 GiB - the 24 words of its boot0 at LBA 16, the HY350 image's block word for word (tpr11/tpr12 `0x44440000`/`0x5555`) |
| Panel | project id `0x30`, 1920x1080 **dual port**, HTotal 2200, VTotal 1125, **164 MHz**, Hsync 2, Vsync 8, HBP 148, VBP 12, InvDCLK 1, InvHSync 2 - its `panel_config.ini` (Reserve0, and the identical copy in vendor) |
| Lamp | `[PWMSetting]` channel 5, polarity 1 (low active), 40 kHz, vsync lock 1, duty 1..100, default 50 - the HY300 Pro's words with another default |
| Display firmware | `display.bin` 1 252 128 B, `22a7df11...` ("ADT-3 2024", the HY350's and HY300 T08's); only in `vendor:/etc/display/mips` - `bootloader_a/_b` are FAT16 without `mips/` |
| Display stack | **vendor** (`display.bin`) by default; the **clean** one (`h713_drm`, no display firmware) per boot with `h713-display set clean`. Since 05.11.2026 the unit's normal boot (`boot_emmc` -> `h713-kernel-7.3.fit`) is the 7.3.1 release kernel with `CONFIG_RUST` and `h713_drm` (=m, kernel `0356`-`0359`, its device tree node disabled, so `bench=1`); the previous 7.3.1 stays as `h713-kernel-7.3-prev.fit` (one-shot `boot_73prev`). Both stacks proven on that boot, vendor -> clean -> vendor and the safety net (`doku/229`); the HDMI picture on this kernel still unseen (no source signal then). Its image `bootcmd` logs U-Boot's console (below) and reads the key. Before: device-tested 04.11.2026 end to end on the 7.3.1-rustbench kernel (`doku/228` §34/§34a; [display stacks](../../docs/subsystems/display-stacks.md)) |
| eMMC | 15 269 888 sectors, 25 partitions, a single `Reserve0` at LBA 7062528; `super` 6291456 sectors (the HY350's 5242880), so everything from `misc` on sits 1048576 sectors later than there |
| Stock | an Android 11 system (`eng.projector.20241024.162050`, ARMv7 kernel 5.4.99) on the ADT-3 Android 10 vendor build 6245789; vendor U-Boot 2018.05-00018 of 19.04.2024, ARISC of the same day |
| Wi-Fi | AIC8800D80 on SDIO (its firmware set is the HY310's, some `_u02` files differ) |

## Where the facts come from

- **The dump** - the owner's eMMC, 7 818 182 656 B, read over ADB (`dd` of `/dev/block/mmcblk0`, which
  is world-readable under this stock) in 64 MiB pieces, each compared with a sha256 computed on the device
  before it was kept; no piece changed between the two reads. sha256 `d09c3347...`. It stays with the owner.
- **The running stock system** (ADB, 30.10.2026) - `getprop`, `/sys/class/input`, `/sys/bus/usb`, `dumpsys
  media.camera`: no V4L2 device, `Number of camera devices: 0`; input devices `stk83xx` (accelerometer),
  `sunxi-ir-uinput`, `sunxi-keyboard`, `HYSD-VATOUCH368`, `htc_prj`.
- **The stock device trees** - U-Boot's (sunxi-package at LBA 24576, item `dtb`) and the kernel's
  (`vendor_boot_a`); they differ only in reserved memory and two status lines. Board-specific nodes: an
  `stk,stk83xx` (STK8BA58) at 0x18 on twi1 (PH2/PH3), irq PB0 (`<&pio 1 0 1>`, three GPIO cells; *superseded
  (01.11.2026):* "irq PC1"); `pwm-fan` on PWM0 with a 40000 ns period, its
  tacho `fan1-fg-gpio` PH17, temperature from the GPADC; `motor_ctr` (PH4..PH7, limiter PH14) **disabled**;
  power key PL4; `standby_param` LEDs red PL0 / blue PL1; the IR receiver on PL9.
- **The two boot0 copies** - LBA 16 carries `para2 0` / `tpr13 0x34010100`, LBA 256 `0x04000000` /
  `0xb4016103`; the rest is equal. `uboot.config` takes the second pair, the one every working base in the
  fork runs.

## The first TEST image on the unit (31.10.2026)

Installed with `h713-install install --test-image --full` from a host on the USB-A port; FEL was reached
without the reset button, by `adb reboot efex` from the stock Android. No serial console: the evidence is
the wall (the owner's eyes), the Wi-Fi access point and SSH, and U-Boot's own console handed to Linux
(`h713_conlog`, below).

| | |
|---|---|
| DRAM | our SPL trains it at 792 MHz; U-Boot, Linux and a 7 GiB rootfs run |
| Power gate | red LED, the power key starts the board; a warm `reboot` boots straight through |
| U-Boot display | the whole `h713_disp init 0x30 logo` with this board's row: firmware "ADT-3 2024" accepted, HDCP 1.4 wait site found at `0x4b13d1f0`, PLL n 47, SSC `0xca1026d3`, "firmware left 1920x1080 active, 2200x1125 total", the vendor boot logo on the wall |
| Fan | `fan0: 3900 RPM at boot` - the tacho on PH17 counts, the stall check has its input |
| Wi-Fi | the access point comes up with the 12 of 13 firmware files this vendor image has (no `fw_patch_8800d80_u02_ext0.bin`, as on the HY300 Pro) |
| Display firmware log | `cpu_comm`'s elog dump at `0x4b48ae00`/`0x4b271d9c` shows the firmware's own lines |
| AFBD handoff | the firmware leaves CTRL `0x03001901`, VIDEO_CTRL `0x03000200`, selector `0`; with the HY310's defaults the driver refused (`-ENODEV`) and the wall went black after the logo. The board's tree states its own words (`allwinner,handoff-state`), the driver probes, `h713-tv` runs |
| RGB plane | the no-signal page, the launcher and a frame written to `/dev/fb0` show correctly |
| **Video plane** | dark on the first image (a Wayland client through `h713-warp` left the wall black); **shown since 01.11.2026** - see the next section |
| **HDMI input** | the socket is the receiver's **port 1**; an Xbox One X at 1920x1080p60 with 48 kHz PCM sound since 01.11.2026 - see below |
| Boot logo | the vendor's `bootlogo.bmp` sits at the root of `bootloader_a/_b` beside no `mips/`; `h713-extract` now takes it from there (it only looked beside `mips/` before) |

### The video plane and the RGB channel over it (01.11.2026)

The board's `LogoRegData.bin` leaves `0x058c0000` (mirrored at `0x058c1000`) at `0x10000040` from its
prologue, and its DE group ends without writing it again. The L018's file, the same 1920x1080 dual-port
panel class, closes its DE group with `0x058c0000 = 0` and six panel words besides. With bit 28 of that
word set the output takes the RGB channel alone, so the video never reached the wall while everything
upstream looked healthy:

| What was seen with bit 28 set | |
|---|---|
| `h713-warp`'s NV12 frame | luma 235 for a white client (`h713-warp ctl dump`) |
| PROC statistics `0x05140600` | `0x3ac` white, `0x040` black - the frame reaches PROC |
| panel-block probes `0x051c0144`, `0x051c0304` and the histogram `0x051c0380..03fc` | white for a white client - the frame reaches the panel block |
| RGB channel, per-pixel alpha (`0x051c006c = 0x21000000`) | an opaque half shows; where it is transparent the video is black (bit 28: the RGB channel alone) |
| lamp | on (the black is the LCD's grey glow); `PB5` and the PWM blocks unchanged between console and video |

Bisected by eye at the wall: the HY310's display firmware (`16c74a28...`) is just as black with the
board's `LogoRegData.bin`, the "ADT-3 2024" firmware shows the video with the L018's file, and in a
running picture `0x10000040` -> black, `0x00000040` -> shown, `0x10000000` -> black. The first fix was one
write in the U-Boot fork after the DE group (commit `94d1a5c7042`): colour bars and motion showed on the
video plane - and the boot logo stood with trailing copies for as long as it was up. So the bit is now
the kernel's (`0339`, `0340`): U-Boot leaves `0x10000040` (the RGB channel alone, a clean logo), and the
AFBD driver, which maps `0x058c0000` as its "mix" window, sets bit 28 at probe, clears it when the video
plane comes on and sets it again when it stops (U-Boot `fc66272cec5`). Checked after a reboot: the logo
clean by eye, `0x00000040` under the Xbox picture, `0x10000040` on the console.

With bit 28 clear the RGB channel reaches the wall only through the panel block's mixer, and there it
showed nothing over the video - no `h713-osd` overlay, not even an opaque test frame in `/dev/fb0` - until
two more words of the L018's tail were set: `0x051c0014` bit 27 and `0x051c0028[5:4]` (`0x18000000` and
`0x30`; neither alone does it; `0x051c0024`, `0x05140054` and `0x051c0070` are not needed). The
firmware's TSE leaves those bits alone, so U-Boot writes them (commit `ca8263484e1`, console line
"HY320 - the L018's DE tail ..."). Checked after a boot with only that change: the power
countdown seen over colour bars at the wall, the volume pill through the panel histogram
(`0x051c0380..03fc` - post-mixer: it moves by ~55000 pixels while the pill is up), and straight
per-pixel alpha through the same histogram (alpha `0x80` and `0x40` land between the picture's
distribution and the opaque colour's). The pill itself is a dark translucent shape with no fully
opaque pixel (alpha 117 ground, 247 at most); over bright colour bars it was not noticed by eye.

Dead ends on the way, so that nobody repeats them: the frame-rate word of the VidDec record (30000, 33131,
66262), the panel totals in `display_cfg.xml` (filled from `panel_config.ini` the way stock `libmips.so`
does: `hde_size`, porches, `work_mode 2`, 164 MHz), the selector values `0x29/0x21/0x10/0x00`, the
blue-screen stages, the border overlay, the gamma stage and the panel's vertical scaler - none of them
changes the black.

### The HDMI input: port 1, and the EDID port 1 never had (01.11.2026)

With an Xbox One X plugged in, the first image saw no signal at all. The display firmware's hot-plug
callback said why: `RX-CALL ... comp_id=0x38d780e2 ... p[1..4]=[00000001 00000004 ...]` - source 4,
HDMI-2, which the init sequence's port map puts on hardware port 1. The driver had the HY310's port 0
wired in (EDID, hot-plug, SetSource 3). With port 1 and source 4 the Xbox locked at once - at 640x480,
without sound, and it stayed there over a replug and over EDID block 1. Reading the three DDC RAMs
(`0x07091c00/1d00/1e00`, the gate `0x07091b04` closed for the read) showed EDID, random bytes, EDID:
port 1's was never written. Copying port 0's EDID into it by hand and a replug brought 1920x1080p60 and
sound. The cause is in the vendor ARISC firmware's DDC writer, which reads its mask-to-port table with
byte loads that see the table byte-reversed under our boot chain's little-endian window - ports 0 and 2
swap and port 1 is skipped ([arisc.md](../../docs/subsystems/arisc.md#the-port-table-the-ddc-writer-reads-01112026)).

Kernel `0336` writes that table in the order the firmware reads it, `0337` makes the socket's port the
device tree's `allwinner,hdmi-port`, `0338` sets it to 1 here. Checked after a reboot with the ARISC
fix and nothing written by hand: all three DDC RAMs hold the EDID, the Xbox comes up at 1920x1080p60,
`audio source present=1 rate=48000`, the converter back on BT.709 (no "picture is green" warning).
The owner first heard the sound as crackling; with music playing it was fine, at volume 40. Since kernel
`0343` the codec runs the stock analog words (below), and the owner heard it clean.

**`0336` in `main` since 03.11.2026.** From 02.11. to 03.11. the patch was held out of `series`, because it changes the
vendor ARISC firmware on every board that runs it and had been measured on this board only. The before/after measurement on
the HY310 and the HY300PRO-G-EU (`doku/228`) showed the same picture as here: before, the DDC RAMs held EDID, random bytes,
EDID; after, EDID three times, the table found at `0x15b6c` and `0x15b7c` in those firmwares; 1080p60, sound and the HDCP 2.2
session unchanged. `h713-tv`'s white balance table and `h713-mode`'s Wi-Fi restart went in with it (the table recognises
the HY310's firmware on both boards; the Wi-Fi restart runs only after a sleep, which those images do not offer: not measured
there).

### Tuned against the stock firmware (01.11.2026)

| | |
|---|---|
| Speaker | our line out was **muted** (`0x02030310` LMUTE/RMUTE 0) and the speaker played over the HP stage; stock runs the line out unmuted, mono differential, at −7.5 dB (`speaker_vol 0x1a`) with HP bits `0x80808f8c`. Kernel `0343` (`allwinner,vendor-analog-init`) writes those words at probe: `0x02030310 = 0x0b15fc7a`, `0x02030324 = 0x80808f8c`; `asound.state` stored with Line Out 26 / Mono Differential. With the HP amp off for 5 s the sound stayed: the speaker hangs off the line out. `dacdrc_used 1` is read and never used by the stock driver - nothing to port. The stock volume curve (0 dB from index 30 on) is not taken: h713-tv keeps its own |
| White balance | `h713-tv` knows the "ADT-3 2024" firmware's four name strings (`wb_r_gain` at `0x4b1ff424`, ...); `ctl set wb_r_gain 400/700` turned the wall cyan, then pink, and `wb reset` back - the owner's eyes |
| Accelerometer | an STK8BA58 (chip ID 0x87, 12 bit) at 0x18 on twi1, interrupt pin PB0 (not PC1); no answer at 0x0e (the stock tree's kxtj3). Kernel `0341`/`0342`; `h713-keystone read` gives 1 g. The axes are the HY310's defaults until three poses are measured, so `h713-keystone-auto` is **disabled on the unit** |
| Thermal | the stock fan driver reads GPADC channel 1 only while LRADC_DATA0 ≤ 5; here it reads 63, so stock never evaluated an NTC on this board, and channel 1 scatters 1313..1526 like the HY310's open input. Kernel `0344` binds that channel, `ntc_num` stays 0; the power-off stays with the SoC zones (orderly at 105 °C, stock 115 °C) and the fan stall. The fan has one speed (PB5's rail) as under stock |
| Lamp | on while PB5 is high (stock `panel_bl_en`); the firmware's PWM channel 5 is `d_pwm5`, whose only pad is PG7 - this board's Bluetooth UART RX - and the ARM PWM block stays 0. Stock's backlight path (ARM PWM 3) reaches no pad either. No dimmer found; kernel `0345` corrects the comments. PB4 as PWM2 at 0/50/100 % moved neither the fan nor anything reported (the owner did not watch) |
| HDCP | a streaming app on the Xbox played at first with HDCP 1.4 (no 2.2 session); with Netflix the Xbox opened an **HDCP 2.2 session** (`h713-tv ctl hdcp`: "2.2 (session stands)", LINK `0x422 = 0x01`, the firmware's `port2 HDCP_base:0x6840000 HDCP Process cost tick:676`), 01.11.2026 |
| 4K | the firmware's table locks 3840/4096x2160 at 24/25/30 Hz and has 50/60 Hz disabled. With 4K30 as the EDID's first timing the Xbox offered "4K UHD" and sent 3840x2160p24 (297 MHz): locked, scaled to the 1080p ring, sound at 48 kHz - and every time the Xbox went back to 1080p60 by itself after 2..4 s, "keep" pressed or not. The 50/60 Hz records switched on in the loaded TSE plus a Y420 block (VIC 96/97) and an HF-VSDB: the Xbox sent, INCAP never settled ("no geometry", totals drifting). Both put back; 1080p60 is this board's mode |
| Keystone | the GPU warp on the 1080p60 HDMI picture: 60 fps, 2 ms a frame, `check` 0 differing rows; 45 % bottom / 15 % top inward seen smooth on the wall |
| Power | no standby (the vendor ARISC firmware); `poweroff` -> red LED -> power key -> logo -> HDMI picture back, 01.11.2026 |
| RGB over video | the panel block mixes the RGB channel over the video plane at an **arbitrary vertical phase**: the launcher over the Xbox picture stood rolled (the top fifth at the bottom; after a reboot two fifths), while the RGB channel alone (`0x058c0000` bit 28) showed it straight. Measured by line counters: the AFBD's video vsync lands at panel-block line ~110, the RGB channel's commit at ~328, the difference changes with every boot; shortening the video plane block's totals (`0x0525c000`) moves it (one line a frame), the OSD block's (`0x0524c010`) does not, and no phase both aligns the RGB rows and keeps them intact (a band sweep against the post-mixer histogram: the rows that fall into blanking sit at 975 - d). The L018's remaining tail words (`0x05140054` bit 30, `0x051c0024`, `0x051c0070`) and the HY310's OSD start words change nothing. So opaque pages go out on the RGB channel alone: `UNDER_PAGE=off` (h713-tv `under_page = off`), the launcher straight by the owner's eyes. Translucent overlays over the picture (the volume pill, the countdown) still go through the mix and stand rolled |

### U-Boot's console without a UART

`hy320_defconfig` sets `CONFIG_CONSOLE_RECORD`; `h713_conlog <addr>` (U-Boot fork,
`arch/arm/mach-sunxi/h713_conlog.c`) copies the record to `<addr>` in RAM behind a header `H713CLOG`,
u32 length, u32 flags. The copy writes nothing else. Where the log goes from there is not settled yet:
the unused tail of `hy310-uboot` (LBA 10240..11263) is no place for it, because the image checks allow a
U-Boot of the partition's full 10240 sectors (LBA 2048..12287) and it would be an eMMC write on every
boot. Its owner read the log that way on 31.10.2026 while bringing the board up (an `mmc write` in his
`bootcmd`, back to the plain `bootcmd` since 01.11.2026); it is not a recipe.

Since 04.11.2026 the board environment (`board/sunxi/hy310.env`) carries `h713_conlog 0x45000000; mmc dev 1;
mmc write 0x45000000 0x2800 0x400` under `CONFIG_CONSOLE_RECORD`, which only this base sets, after the `fi;` of its
`h713_display` branch: an HY320 image's `bootcmd` logs every boot to that tail and reads the key, with no hand edit.
That is the per-boot eMMC write the paragraph above rules out; whether it stays or goes back to RAM only is open.
The other boards' `bootcmd` has no `h713_conlog`. `h713-display set clean` refuses a hand-set `bootcmd` that ignores
the key ([display stacks](../../docs/subsystems/display-stacks.md)); `fw_setenv bootcmd` with the image's line (its
`u-boot-initial-env`) replaces it. The unit's saved environment carries the image's
line since 05.11.2026 (`doku/229` §2).

## What we do not know

- whether the other ADT-3 family boards (HY350, HY300 T08) need the same three words (`0x058c0000`,
  `0x051c0014`, `0x051c0028`) - the fix is scoped to this board until one of them is measured;
- whether an NTC is fitted at all (a cold-start series of GPADC channel 1 would tell: about 2050..2200 from cold,
  falling as the box warms, scatter within ±5);
- whether PB4 or PB5 as a PWM dims the lamp with someone watching the wall;
- the STK8BA58's axes and signs on this board (stk8ba50 drives it as `sensortek,stk8ba58` since kernel 0341: chip ID
  0x87 read on the unit 01.11.2026; *superseded (01.11.2026):* "whether the STK8BA58 is driven by anything in mainline");
- other source modes than 1080p60 (720p, 50 Hz, 4K30) on this panel;
- the silkscreen of the board.
