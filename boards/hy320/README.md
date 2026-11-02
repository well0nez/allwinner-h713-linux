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
  `stk,stk83xx` (STK8BA58) at 0x18 on twi1 (PH2/PH3), irq PC1; `pwm-fan` on PWM0 with a 40000 ns period, its
  tacho `fan1-fg-gpio` PH17, temperature from the GPADC; `motor_ctr` (PH4..PH7, limiter PH14) **disabled**;
  power key PL4; `standby_param` LEDs red PL0 / blue PL1; the IR receiver on PL9.
- **The two boot0 copies** - LBA 16 carries `para2 0` / `tpr13 0x34010100`, LBA 256 `0x04000000` /
  `0xb4016103`; the rest is equal. `uboot.config` takes the second pair, the one every working base in the
  fork runs.

## The first TEST image on the unit (31.10.2026)

Installed with `h713-install install --test-image --full` from a host on the USB-A port; FEL was reached
without the reset button, by `adb reboot efex` from the stock Android. No serial console: the evidence is
the wall (the owner's eyes), the Wi-Fi access point and SSH, and U-Boot's own console recorded to the
eMMC (below).

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
The owner first heard the sound as crackling; with music playing it was fine, at volume 40.

### U-Boot's console without a UART

`hy320_defconfig` sets `CONFIG_CONSOLE_RECORD`; `h713_conlog <addr>` (U-Boot fork,
`arch/arm/mach-sunxi/h713_conlog.c`) copies the record behind a header `H713CLOG`, u32 length, u32 flags.
On the unit the environment carries

```
bootcmd=h713_disp init ${h713_project} logo; h713_conlog 0x45000000; mmc dev 1; mmc write 0x45000000 0x2800 0x400; run boot_${h713_boot}; run boot_net
```

so every boot leaves the log in the unused tail of `hy310-uboot` (LBA 10240..11263, well clear of
`hy310-keys` at 12288). Read it from Linux with
`dd if=/dev/mmcblk0 bs=512 skip=10240 count=1024 | tail -c +17 | head -c <length>`.

## What we do not know

- whether the other ADT-3 family boards (HY350, HY300 T08) need the same three words (`0x058c0000`,
  `0x051c0014`, `0x051c0028`) - the fix is scoped to this board until one of them is measured;
- whether the HDCP-protected parts of a source (streaming apps on the Xbox) authenticate on port 1;
- which pad PWM channel 5 leaves the SoC on, and whether the PWM words change the lamp;
- whether the STK8BA58 is driven by anything in mainline;
- the silkscreen of the board.
