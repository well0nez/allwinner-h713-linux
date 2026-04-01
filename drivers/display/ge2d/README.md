# HY310 GE2D Display Engine Driver

## Overview

The GE2D (Graphics Engine 2D) driver provides framebuffer access and display
pipeline control for the HY310 projector. It manages the OSD layer, backlight,
panel initialization, and DLPC3435 DLP controller.

## Loading

```bash
# Requires tvtop module (in-tree, loaded automatically)
modprobe sunxi-ge2d
```

## Verification

```bash
# Check framebuffer
cat /sys/class/graphics/fb0/virtual_size
# Expected: 1920,1080

# Test framebuffer output (noise on projector)
dd if=/dev/urandom of=/dev/fb0 bs=4096 count=1000

# Check chardev
ls -la /dev/ge2d

# Check IRQs
grep -E 'vblender|afbd' /proc/interrupts
```

## Framebuffer Usage

The framebuffer is at /dev/fb0 (1920x1080 ARGB8888, 26MB).
Write directly or use fbterm for a text console:

```bash
apt install fbterm
TERM=linux fbterm --font-size=36 -- bash
```

## Module Parameters

| Parameter | Default | Description |
|-----------|---------|-------------|
| enable_dlpc3435 | 0 | Enable DLPC3435 I2C init (deferred, optional) |
| enable_irqs | 0 | Enable IRQ request (vblender + AFBD) |

## Current Limitations

- No OSD scanout programming (VBlender block at 0x05200000 is dead)
- Display works via U-Boot MIPS scanout preservation only
- DLPC3435 I2C address unknown
- afbd clock is 150MHz instead of required 200MHz
- PB5 is shared between panel backlight and fan power — never set LOW

See [docs/DISPLAY.md](../../docs/DISPLAY.md) for full analysis.
