# Hardware

The H713 is a quad-core SoC with two extra processors hidden inside it, and the HY310 wires it to a
DLP optical engine instead of a screen. Before you flash or debug anything, work out which of the
board variants below you are holding - the wrong DRAM parameters train "OK" and then hang on reads.

## Board variants

| Board | Silkscreen | DRAM | Source |
|---|---|---|---|
| Bench | `HY200_QZ713DF_A1` | DDR3, 1 GiB | cstenger's bring-up board (`mainline/README.md`) |
| "Projector", fork naming | `HY200_QZ713_V2` | LPDDR3, 1 GiB - **assumed, never booted** | `mainline/README.md` |
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

Two more processors run on the same die and are already alive by the time Linux boots:

| Core | Firmware | Owns |
|---|---|---|
| MIPS32 LE co-processor | `display.bin`, ~1.25 MB | display engine, HDMI-RX state machine, picture-quality pipeline |
| OR1K BE "ARISC" | `h713-arisc.bin`, ~172 KB | PMU power sequencing, HDMI hot-plug pin, EDID/DDC RAM |

Neither firmware ships in this repo or on the built image; both come out of **your own** device dump
via `h713-extract` at install time. How the three processors talk to each other, and why you cannot
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
this projector has no HDMI output. Verified modes and signal handling: [docs/subsystems/hdmi-in.md](subsystems/hdmi-in.md)
and `STATUS.md`.

## GPU

Mali-G31, driven by the mainline Panfrost driver, with our own mesa (panfrost only) under `/usr/local`.
Since `v0.95-beta` the keystone renders on it - `h713-warp` warps the HDMI picture into NV12 for the video
plane, measured on the HY310 (`docs/guides/keystone.md`).

## Wi-Fi and Bluetooth

Both live on one chip, **AIC8800D80**: Wi-Fi over SDIO, Bluetooth over UART1 at 1.5 Mbaud. Wi-Fi runs
today (AP or station, out-of-tree modules plus `h713-wifi`); Bluetooth does not ship because its
firmware has not been split out of the vendor dump yet. Details: [docs/subsystems/wifi.md](subsystems/wifi.md).

## Audio

An internal codec drives the speaker for device sounds. HDMI audio is a separate path - a codec-I2S
link plus an MSP DSP block tied to the HDMI-RX capture clock - and is what plays back the source's
sound today. Details: [docs/subsystems/audio.md](subsystems/audio.md).

## eMMC and USB

eMMC is 7.3 GB, HS400. Three USB controllers exist on the board:

| Port | Wired to | Notes |
|---|---|---|
| 0 | external USB-A socket, OTG | FEL and USB-gadget modes run over this port |
| 1 | internal camera, Realtek `0bda:5803` "Generic HD camera" | UVC, YUYV 640×480, works since 2026-09-11 |
| 2 | nothing | registers, unpopulated |

## Power draw

Measured: **about 4 W** in standby, meaning the SoC runs and everything else is dark - that is what the
power gate leaves behind (09.09.2026). The draw with a picture on the wall has **not been measured**; the
lamp and the imager dominate it, and the vendor's own rating is the only number available. If you measure
it, the figure is worth having here.

## Fan, focus motor, power key, LEDs, UART

| Component | Pin / bus | What it does |
|---|---|---|
| Fan | PWM on PH18, tachometer on PH17 (GPIO interrupt) | speed fixed today; 4860 RPM measured. `PB5` gates the fan **and** the panel backlight together - never drive it low |
| Temperature | - | this unit's board-management firmware reports `ntc_num = 0`: **no NTC is fitted**, and overheat protection relies on the fan tachometer alone. An earlier assumption of a fitted thermistor was wrong (`doku/00-STATUS.md`, 2026-09-11) |
| Focus motor | 4-phase stepper, GPIO-driven; PH14 sense pin | PH14 is a **range sensor** - it reads high while the mechanism is inside its travel window and drops at either end - not a one-directional end-stop |
| Camera | see USB port 1 above | |
| Power key | `PL4` (R_PIO), `KEY_POWER`, edge IRQ | short press starts the device from standby; under Linux, `systemd` maps it to `poweroff`. Governs the power-on gate: [docs/uboot/power-gate.md](uboot/power-gate.md) |
| Status LEDs | `PL0`/`PL1` per the vendor device tree | tied to the power rails, not individually GPIO-driven; the gate additionally drives a red/blue indicator for standby vs. running |
| UART pads | UART0, **115200 8N1**, 3.3 V | the boot and kernel console, and the way in when there is no SSH key in the image. The pads are on the mainboard and unlabelled; the thread that found them on several units is linked from the README's issue reference - no photograph in this repository yet |

Details: `doku/10-hardware.md`, `doku/00-STATUS.md`, `mainline/README.md`, `doku/103-plan-einschaltgate.md`
(power key), `doku/94-fokusmotor-endschalter.md` (focus-motor sensor).
