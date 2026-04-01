# HY310 Display Subsystem

## Status: PARTIAL — framebuffer working via MIPS scanout, pipeline compositor dead

## Hardware Map

| Block         | Address      | Notes                              |
|---------------|--------------|------------------------------------|
| GE2D          | 0x05240000   | Graphics engine, `trix,ge2d`       |
| TVTOP         | 0x05700000   | Display clock/power management     |
| VBlender      | 0x05200000   | **DEAD** — reads zero, writes ignored |
| DECD          | 0x05600000   | Video decoder (MIPS dependent)     |

- IRQ: VBlender = SPI 101, AFBD = SPI 112

## Framebuffer

- `/dev/ge2d` chardev
- `/dev/fb0` — 1920x1080 ARGB8888
- Framebuffer base: `0x78541000` (FB writes go here directly for MIPS scanout)
- U-Boot initializes the display; MIPS continues scanout after hand-off

## MIPS Scanout Dependency

U-Boot loads `display.bin` to `0x4b100000` before the kernel starts. The MIPS co-processor handles the actual display scanout pipeline. The ARM side only writes to the framebuffer; the MIPS side drives the physical display.

## Known Issues

- **VBlender block** at `0x05200000` is completely dead (zero reads, silent write drops) — ARM-side compositing not possible until this is resolved
- **OSD firmware** (`LogRegData.bin`) not loaded yet
- **DLPC3435** projector I2C address unknown; `0x27` is `mir3da` accelerometer, not DLPC
- **afbd clock**: currently running at 150 MHz, should be 200 MHz
- **PWM dimming**: `sun4i-pwm` has `npwm=2`; H713 needs `npwm=8` to reach channel 2

## Critical GPIO Warning

**PB5 = panel backlight enable AND fan power (shared hardware line)**
**NEVER set PB5 LOW** — doing so will cut fan power in addition to disabling the backlight.

## Next Steps

1. Determine why VBlender registers read as zero (clock gating? power domain? MIPS lock?)
2. Load `LogRegData.bin` OSD firmware
3. Find DLPC3435 I2C address via bus scan on live board
4. Fix afbd clock parent to reach 200 MHz
5. Fix `sun4i-pwm` npwm in DTS for backlight PWM channel 2
