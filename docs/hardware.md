# Hardware

The H713 is a quad-core SoC with two extra processors hidden inside it, and the HY310 wires it to a
DLP optical engine instead of a screen. Before you flash or debug anything, work out which of the
board variants below you are holding - the wrong DRAM parameters train "OK" and then hang on reads.

## Board variants

| Board | Silkscreen | DRAM | Source |
|---|---|---|---|
| Bench, HY300PRO-G-EU, "HY300 Pro+" 2025 | `HY200_QZ713DF_A1` | DDR3; 792 or 624 MHz by firmware, 1 GiB on the bench | cstenger's bring-up board ([his README at `8860991`](https://github.com/cstenger/allwinner-h713-mainline/blob/8860991a91ee973a45bb6f198bda896dd1e02c36/README.md)), and the board of two projector firmwares (`boards/hy200-qz713df-a1`) |
| "Projector", fork naming | `HY200_QZ713_V2` | LPDDR3, 1 GiB - **assumed, never booted** | [cstenger's README at `8860991`](https://github.com/cstenger/allwinner-h713-mainline/blob/8860991a91ee973a45bb6f198bda896dd1e02c36/README.md) |
| This project's unit | `HY260_QZ713_V3.1` | DDR3, 792 MHz, 1 GiB - measured | boot0 UART log, SK hynix `H5TQ` part marking, `sys_config.fex`, boot0 header - four independent sources, `doku/10-hardware.md` |

Two names for "the projector board" circulate in the base tree, and neither matches the silkscreen on the unit
this whole repository is built and tested against. `doku/10-hardware.md` calls it a third variant and
measured it as DDR3, not the LPDDR3 the fork assumes for `HY200_QZ713_V2`.
Whether `HY200_QZ713_V2` is a genuinely different board or the same one under a name taken from a
listing is unresolved: nobody working on this repository has one in hand, and the LPDDR3 attribution
was never verified on hardware. Assume nothing from it.
Always say which board a result came from. Neither board has an SD slot: boot media is **eMMC or FEL
only**. FEL is entered by holding the reset button while applying power - no pad, no case opening.

## SoC and the two co-processors

Allwinner **H713** (`sun50iw12p1`), SoC-ID `0x1860` (`jep106:091e:1860`), 4× Cortex-A53. Closer to D1 in
pinctrl, closer to H6 in the clock tree, with quirks of its own on both - do not reuse either sibling's
register layout blind.

The four cores share one clock, 480-1296 MHz through `cpufreq-dt`, and one supply, `vdd-cpu`: a PWM regulator,
0.81-1.16 V, ramping at 2.5 mV/µs (HY300PRO-G-EU device tree). A clock change is a regulator ramp and a PLL relock,
which the kernel declares as 308 µs, and schedutil's thread `sugov:0` carries each one out. Two things made that
thread cost as much CPU as the warp (11.10.2026): the kernel's own `rate_limit_us` (1.5 × that, 462 µs) let the
clock follow every burst, and - the larger part - schedutil asks for the **maximum** clock whenever a real-time
task is runnable, and the GPU's interrupt handlers are real-time threads (SCHED_FIFO 50) that run four times a
frame with the warp on: the clock swung 480 <-> 1296 MHz forty times a second whatever the rate limit.
`h713-cpufreq.service` sets both once per boot - 20 ms, and the three `irq/*-panfrost` threads to SCHED_OTHER -
after which the clock stays at 480 MHz under the warp (0.3-1.6 changes a second, `sugov:0` 0.1 %, 59.7 fps, no
frame dropped; the table with all four combinations is in `userspace/h713-cpufreq/h713-cpufreq`). The kernel's
own way would be `CONFIG_UCLAMP_TASK` with `sched_util_clamp_min_rt_default` (TODO 2.60). *Superseded 11.10.2026
(evening):* "`/etc/tmpfiles.d/h713-cpufreq.conf` sets 20 ms at boot" - it ran before the governor had its sysfs
directory, so three boots in a row came up with 462 µs again.

Two more processors run on the same die and are already alive by the time Linux boots:

| Core | Firmware | Owns |
|---|---|---|
| MIPS32 LE co-processor | `display.bin`, ~1.25 MB | display engine, HDMI-RX state machine, picture-quality pipeline |
| OR1K BE "ARISC" | the vendor's `h713-arisc.bin` from the owner's dump, 172 KiB (176 132 bytes on the HY300PRO-G-EU) - what every image runs since 22.10.2026; **crust**, our own build ([crust-h713/](../crust-h713/README.md)), as the experiment (`h713-arisc set crust`) and in `--standby` images | PMU power sequencing, HDMI hot-plug pin, EDID/DDC RAM; with crust also the standby and a 0.3 W power-off |

The MIPS firmware and the vendor's ARISC firmware ship neither in this repo nor on the built image; both come out of
**your own** device dump via `h713-extract` at install time. crust is built with the image and lies in its rootfs; BL31
starts it at every boot only in an image built with `--standby` ([arisc.md](subsystems/arisc.md),
[U-Boot chain](uboot/README.md)). How the three processors talk to each other, and why you cannot
just poke a MIPS or ARISC register from Linux, is in [architecture.md](architecture.md).

## Display path

The panel is **1920×1080 LVDS, dual-port**, driven through a **DLPC3435** bridge into the DLP imager -
the projector's optics are the only display output this device has, there is no HDMI-out connector
wired up. The timing (2128×1120 total, pixel clock 143 001 600 Hz → exactly 1080p60) comes from the
device's own panel tables and is confirmed four ways: kernel log, a DE2 register dump, an AFBD geometry
register, and the stock driver's resolution switch (`doku/10-hardware.md`). The MIPS firmware owns the
whole chain from HDMI capture to the panel output register block; Linux only feeds it a source buffer
and a plane. Full chain, bring-up order and KMS device: [docs/subsystems/display.md](subsystems/display.md).

## HDMI input

A Synopsys DW-HDMI-RX block, HDMI 1.4, exposed as a V4L2 capture device. It is the device's **only** HDMI port -
this projector has no HDMI output. Its PHY and the capture block INCAP sit in the TVCAP power domain (below).
Verified modes and signal handling: [docs/subsystems/hdmi-in.md](subsystems/hdmi-in.md)
and `STATUS.md`.

## GPU

Mali-G31, driven by the mainline Panfrost driver, with our own mesa (panfrost only) under `/usr/local`.
Since `v0.95-beta` the keystone renders on it - `h713-warp` warps the HDMI picture into NV12 for the video
plane, measured on the HY310 (`docs/guides/keystone.md`).

## Wi-Fi and Bluetooth

Both live on one chip, **AIC8800D80**: Wi-Fi over SDIO, Bluetooth over UART1 at 1.5 Mbaud with RTS/CTS.
Wi-Fi runs (AP or station, out-of-tree modules plus `h713-wifi`); Bluetooth runs on top of it - the
Wi-Fi driver loads the chip's Bluetooth patch from the owner's dump, `hciattach` and bluez do the rest,
and the stock remote pairs over BLE. Details: [docs/subsystems/wifi.md](subsystems/wifi.md).

## Audio

An internal codec drives the speaker. HDMI audio reaches it through a codec-I2S link from an MSP DSP block
tied to the HDMI-RX capture clock, and since `v0.96-beta` the box's own sounds join that path inside the
DSP: a playback PCM, `hw:hy310hdmi,0`, which is ALSA's default, is mixed into HDMI there, so both play at
once. The DSP's island is in the TVFE power domain (below). Details: [docs/subsystems/audio.md](subsystems/audio.md).

## eMMC and USB

eMMC is 7.3 GB, HS400. Three USB controllers exist on the board:

| Port | Wired to | Notes |
|---|---|---|
| 0 | external USB-A socket, OTG | FEL and USB-gadget modes run over this port |
| 1 | internal camera, Realtek `0bda:5803` "Generic HD camera" | UVC, YUYV 640×480, works since 2026-09-11 |
| 2 | nothing | registers, unpopulated |

## Power domains and what a standby resets

The PPU (PMU block, `0x07001000`; layout in kernel patch `0020`) switches five domains, numbered as in the vendor
device tree: GPU 0, TVFE 1, TVCAP 2, VE 3, AV1 4. TVCAP holds the HDMI receiver's PHY and INCAP, the capture
block that writes frames into the DRAM; TVFE holds the audio DSP's island; the journal has no measurement on VE
and AV1. U-Boot switches TVFE and TVCAP on before it releases the display MIPS and a built-in driver holds both,
but in a system sleep genpd switches them off and on again whatever the drivers hold. Read on the HY310 before
and after a standby (09.10.2026, `doku/172`, `doku/173`):

| Register | Before | After |
|---|---|---|
| TV top clock and reset words, `0x06e00000`, `+4`, `+8` | `0x00111111`, `0x01111117`, `0x00000504` | `0x10`, `0`, `0` |
| Audio top word, `0x0614a000` | `0x700` (after the boot) | `0` (after the MIPS restart) |
| CCU, PPU, R_CCU, SYS_CFG, RTC general-purpose words | - | the same (MIPS and GPU registers apart) |
| DRAM-COM `+0x004`, field [21:16] | `0x20` | `0x10`; crust does not restore it, and writing it back by hand did not stop the MIPS-restart stall (first bullet) |

- **TV top.** U-Boot writes these words before it starts the MIPS. Started out of the standby park without them,
  the whole SoC stalled within 200 ms, 3 of 3; the driver `sun50i-h713-mips` now repeats U-Boot's step when they
  are missing: six standbys, six pictures back.
- **Audio island.** It loses its power with TVFE, and its mailbox stays silent until msp's `reset` file rebuilds
  it. `h713-mips-restart` does that once the picture is back; HDMI audio was audible again without a reboot
  (`doku/173`, `doku/174`).
- **INCAP.** The MIPS's park does not stop it, and from the park on its registers no longer answer the CPU (one
  read halted the box). Switching TVCAP off under that DMA is where the rare hang going to sleep (C1) stood; with
  the capture stopped first there was no C1 in 50 sleeps against 5 in 111, a hint and not a proof.

GPU, VE and AV1 in the sleep: not measured. The display clocks, the picture and the wake sources:
[standby.md](subsystems/standby.md).

## Watchdogs

The SoC watchdog (`0x02051000`) and the R_WDOG (`0x07020400`, RTC domain, the net of a standby) share the A523's
register file: CTRL at `+0x0c` (write `0x14af` to reload), CFG at `+0x10`, MODE at `+0x14` (enable in bit 0,
interval in bits 7:4: codes 1-11 are 1-6, 8, 10, 12, 14, 16 s, code 0 is 0.5 s), and **every CFG or MODE write
needs the key `0x16aa` in bits 31:16**; `0x16aa00b1` into MODE reset the HY310 16.4 s later (`doku/164`). The
H6 layout the device tree first gave it hits nothing (`doku/72`); the kernel now binds the A523 string.

- A MODE write into a running watchdog does not restart its count, a CTRL reload does; TF-A and the kernel
  therefore feed before they arm or stop it, and `reboot` and `poweroff` reset 0.58-0.60 s after their last
  console line (`doku/164`, `doku/170`).
- The R_WDOG **stays armed across its own reset**, so a net that fired would reset the box every 16 s; BL31 feeds
  and stops an armed one at every boot (`doku/170`). No journal entry provokes a reset in the middle of a sleep, so
  the sleep net is not measured ([standby.md](subsystems/standby.md)).
- The RTC takes its 32 kHz from the 24 MHz crystal, divided, since kernel `0320` (16.10.2026), as the vendor kernel does;
  on the internal RC oscillator it ran 26 % slow and the kernel's clock sync swallowed every alarm
  ([standby](subsystems/standby.md), `doku/213` §5). *Superseded (16.10.2026):* "The RTC runs from its internal RC
  oscillator; whether a 32 kHz crystal is fitted is unknown (`doku/168`)."

## Power draw

Measured on the HY310 on 09.10.2026 with a plug-in meter at the wall, the PC's USB cable pulled, no HDMI
source (`doku/181`):

| State | Draw |
|---|---|
| standby - suspended to RAM through crust ([standby](subsystems/standby.md)): the ARM cores off, the DRAM in self-refresh | **2.4 W** |
| off - the power gate: U-Boot waits for the key, and since `0102` for either remote's power key, on one ARM core, the rest dark - what every image does since 22.10.2026 ([power-gate](uboot/power-gate.md)); measured before the IR decoder, with it not measured | **2.9 W** |
| off through crust - the rails off (PL6), only crust and the RTC awake; measured on the HY300PRO-G-EU (`doku/188`); on the HY310 the power off and the wake are measured, the draw is not (`doku/190`) | **0.3 W** |
| on, no signal: the console on the wall, lamp and fan on | about 24 W |

So the standby draws less than "off". The power supply whines faintly in standby, and in the off through crust
as well (HY310, 10.10.2026, `doku/190`); stock Android is silent at the same 0.3 W, and the gate is silent (the owner,
21./22.10.2026, `doku/218`) - which is why the release runs the vendor's ARISC firmware (TODO 2.42). On 09.09.2026, before
crust, the same kind of meter read 4 W in the gate and **47 W with a 1080p picture** (`doku/103`); how
much of the 4 W was a smart plug or the USB cable in the path is not recorded, and the draw with a
picture was not measured again. *Superseded (09.10.2026):* "Measured: about 4 W when off [...] The draw
in standby [...] has not been measured either."

## Fan, focus motor, power key, LEDs, UART

| Component | Pin / bus | What it does |
|---|---|---|
| Fan | on/off through `PB5`, tachometer on PH17 (GPIO interrupt) | a plain 3-wire load, no speed control ([board-mgr](subsystems/board-mgr.md), patch `0030`); the vendor boot loader's tree puts pwm1 on PH18, which no kernel tree uses (`doku/70`); 4860 RPM measured. `PB5` gates the fan **and** the panel backlight together - never drive it low while the lamp runs; for a standby the board manager drops it with both off (the journal line on both boards, `doku/185`; the lamp itself not measured) |
| Temperature | - | this unit's board-management firmware reports `ntc_num = 0`: **no NTC is fitted**, and overheat protection relies on the fan tachometer alone. An earlier assumption of a fitted thermistor was wrong (`doku/00-STATUS.md`, 2026-09-11) |
| Focus motor | 4-phase stepper, GPIO-driven; PH14 sense pin | PH14 is a **range sensor** - it reads high while the mechanism is inside its travel window and drops at either end - not a one-directional end-stop |
| Camera | see USB port 1 above | |
| Power key | `PL4` (R_PIO), `KEY_POWER`, edge IRQ | a press starts the device from the gate and wakes it from a standby (key and IR power key measured 09.10.2026, `doku/174`). Under Linux [h713-power](tools/h713-power.md) reads it, and the remotes' power keys with it: a short press the 15 s countdown ending in a power-off (or a standby where the image offers one), held 3 s power-off at once. Governs the power-on gate: [docs/uboot/power-gate.md](uboot/power-gate.md) |
| IR receiver | `PL9` (R_PIO), `sunxi-cir` at its default 8 MHz (kernel `0252`), keymap `rc-h713-fd02` (`0254`, `0329`) | both stock remotes (NEC address `0x02`, and the HY300's `0x00`); the vendor's ARISC firmware switches the pin away at its start and the kernel applies it again (`0328`); in the gate U-Boot decodes the power key itself (`0102`) ([remote](subsystems/remote.md)) |
| Status LED | follows `PB5` | red while PB5 is low (the gate, standby), blue while it is high - measured, so the LED cannot tell those two apart. `PL0`/`PL1`, which the vendor device tree calls the LEDs, have no visible effect on the HY310; the vendor firmware and crust still drive them in standby |
| UART pads | UART0, **115200 8N1**, 3.3 V | the boot and kernel console, and the way in when there is no SSH key in the image. The pads are on the mainboard and unlabelled; the thread that found them on several units is linked from the README's issue reference - no photograph in this repository yet |

Details: `doku/10-hardware.md`, `doku/00-STATUS.md`, [cstenger's README at `8860991`](https://github.com/cstenger/allwinner-h713-mainline/blob/8860991a91ee973a45bb6f198bda896dd1e02c36/README.md), `doku/103-plan-einschaltgate.md`
(power key), `doku/94-fokusmotor-endschalter.md` (focus-motor sensor), `doku/164`, `doku/170` - `doku/174`
(watchdogs, power domains, standby).
