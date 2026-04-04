# HY310 Display Subsystem

## Status: WORKING — DRM/KMS driver with GEM scanout, Weston launches

## Architecture

The H713 uses a **custom display pipeline** that is NOT standard Allwinner
DE2/DE3/TCON. The pipeline looks like:

```
CCU clocks → TVTOP (bus fabric) → VBlender (timing) → OSD (plane) → AFBD → LVDS → DLPC3435 → DLP
```

The MIPS co-processor (loaded from display.bin by U-Boot) initializes VBlender
timing and LVDS PHY at boot. Our DRM driver programs TVTOP bus routing, enables
clocks, and handles framebuffer scanout via the AFBD controller.

## Hardware Map

| Block    | Address      | Size  | Notes                                    |
|----------|-------------|-------|------------------------------------------|
| TVTOP    | 0x05700000  | 0xA0  | Bus fabric routing — MUST program first  |
| VBlender | 0x05200000  | 0x100 | Timing controller (MIPS-initialized)     |
| OSD      | 0x05248000  | 0x200 | Plane control, commit bit                |
| AFBD     | 0x05600000  | 0x200 | Framebuffer controller, scanout addr     |
| GE2D     | 0x05240000  | 0x20  | Graphics engine core (minimal init)      |
| LVDS     | 0x051C0000  | 0x100 | LVDS PHY (MIPS-initialized)              |
| DLPC3435 | I2C @ 0x1B  | —     | TI DLP controller (optional I2C init)    |

- Scanout address register: AFBD_CTRL + 0x78 (physical 0x05600178)
- IRQ: VBlender = GIC SPI 101, AFBD = GIC SPI 112

## Root Cause: VBlender Reads Zero

The initial bringup problem was that all display sub-blocks read zeros. Root
cause: **TVTOP bus fabric routing registers** at 0x05700000 must be programmed
with a specific 7-register sequence before any display sub-block responds to
MMIO reads. See [DISPLAY_BRINGUP.md](DISPLAY_BRINGUP.md) for the full analysis.

## DRM/KMS Driver

The new DRM driver (`drivers/display/drm/h713_drm.c`) replaces the legacy
ge2d framebuffer path:

- Out-of-tree module (`h713_drm.ko`)
- Binds to `trix,ge2d` compatible string in DTS
- Uses `drm_simple_display_pipe` (single CRTC + plane + encoder)
- Fixed mode: 1920x1080@60Hz LVDS (148.5 MHz pixel clock)
- GEM DMA buffer management with DRM_GEM_DMA_DRIVER_OPS_VMAP
- PRIME buffer sharing (dma-buf export/import) for Panfrost GPU
- Warm-disable strategy: clocks/reset kept alive during disable/reopen cycles

### Enable Sequence

1. Enable display clocks (svp_dtl, deint, panel, bus_disp, afbd)
2. Deassert reset (rst_bus_disp)
3. Program TVTOP 7-register routing sequence
4. Verify VBlender is alive (read ctrl/hact/vact)
5. Program scanout address to AFBD_CTRL + 0x78
6. Latch: AFBD_CTRL + 0x44 = 1, OSD_CTRL |= BIT(0)

### Module Parameters

- `use_safe_scanout` — Point scanout at known-good U-Boot buffer (debug)
- `fill_test_pattern` — Draw gradient+checkerboard test pattern (debug)
- `enable_dlpc3435` — Experimental DLPC3435 I2C init sequence

## DRM Device Layout

| Device       | Card    | Function              |
|-------------|---------|------------------------|
| Panfrost    | card0   | GPU render (renderD128)|
| h713_drm    | card1   | Display scanout (KMS)  |

PRIME buffer sharing between card0 and card1 is verified and working.

## Weston Compositor

Weston launches with GL renderer (Panfrost) and recognizes the LVDS output.
Current blocker: CMA pool too small for Weston's buffer allocation needs
(EGL_BAD_ALLOC on CREATE_DUMB). Needs CMA pool increase or reserved-memory
cleanup.

## Legacy GE2D Path

The old ge2d framebuffer driver is kept in `drivers/display/ge2d/` for
reference but is superseded by the DRM driver. Both bind to the same
`trix,ge2d` compatible — only one should be loaded at a time.

## Critical GPIO Warning

**PB5 = panel backlight enable AND fan power (shared hardware line)**
**NEVER set PB5 LOW** — doing so will cut fan power AND disable the backlight.
