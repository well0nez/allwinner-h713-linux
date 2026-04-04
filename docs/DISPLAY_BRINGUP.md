# H713 Display Subsystem Bringup — Analysis & Findings

## Root Cause: Why VBlender Reads All Zeros

**TVTOP (0x05700000) is a bus fabric controller.** Without programming its
routing registers, ALL display sub-blocks are bus-gated:

- VBlender/OSD_B (0x05200000) → reads 0x00000000
- GE2D core (0x05240000) → reads 0x00000000  
- LVDS controller (0x051C0000) → reads 0x00000000
- AFBD (0x05600000) → reads 0x00000000

### What we tested and ruled out:

| Hypothesis | Result | Evidence |
|---|---|---|
| PPU DE power domain off | **RULED OUT** | PPU @ 0x07001000 (not 0x07010000!), domain 4 pwr_ctrl=0x01, status=0x00010000 = ON |
| Display clocks not enabled | **RULED OUT** | Test module: bus-disp enable_count=1, afbd enable_count=1, correct rates |
| RST_BUS_DISP still asserted | **RULED OUT** | Test module: reset_control_deassert() returned 0 |
| Wrong CCU register offsets | **RULED OUT** | Stock vmlinux IDA confirms RST_BUS_DISP @ 0xDD8 BIT(16), matches our CCU |
| **TVTOP bus routing not configured** | **ROOT CAUSE** | Stock tvtop_tvdisp_enable writes 7 routing registers to 0x05700000 |

### The Fix — TVTOP Routing Register Sequence

From stock `tvtop_tvdisp_enable` (offset 0x029c in sunxi_tvtop.ko):

```
// Full tvdisp enable sequence:
1. clk_prepare_enable(svp_dtl_clk)     // 200MHz from pll-periph0-2x
2. clk_prepare_enable(deint_clk)       // 1032MHz from pll-video2-4x
3. clk_prepare_enable(panel_clk)       // 1032MHz from pll-video2-4x  
4. clk_prepare_enable(clk_bus_disp)    // 150MHz from ahb
5. reset_control_deassert(rst_bus_disp)
6. Write TVTOP routing registers:      // 0x05700000 base
   TVTOP+0x04 = 0x00000001
   TVTOP+0x44 = 0x11111111  
   TVTOP+0x88 = 0xFFFFFFFF
   TVTOP+0x00 = 0x00011111
   TVTOP+0x40 = 0x00011111
   TVTOP+0x80 = 0x00001111
   TVTOP+0x84 = 0xFFF000EF    // 1080p-specific
```

After step 6, display sub-blocks should respond to MMIO reads.

## Hardware Topology — Corrected Understanding

```
              CCU (0x02001000)
                |
                +-- bus-disp (0xDD8 BIT0 gate, BIT16 reset)
                +-- afbd (0xDC0 BIT31 gate, M/MUX/GATE)
                +-- svp-dtl, deint, panel
                |
              TVTOP (0x05700000) ← BUS FABRIC CONTROLLER
                |                   Routing regs gate sub-blocks
                |
    +-----------+-----------+-----------+
    |           |           |           |
 VBlender    GE2D core    LVDS PHY    AFBD
 0x05200000  0x05240000   0x051C0000  0x05600000
```

## PPU Power Domain — Corrected Base Address

**Base: 0x07001000** (NOT 0x07010000 as previously assumed)

| Domain | Index | Base | Status on our kernel |
|---|---|---|---|
| pd_gpu | 0 | 0x07001000 | ON (pwr_ctrl=1, status=0x10000) |
| pd_tvfe | 1 | 0x07001080 | ON |
| pd_tvcap | 2 | 0x07001100 | ON |
| pd_ve | 3 | 0x07001180 | ON |
| pd_de (?) | 4 | 0x07001200 | ON |
| (unused) | 5 | 0x07001280 | all zeros |

All power domains are ON from U-Boot. No power domain driver needed
for initial bringup (but should be implemented for proper PM).

## Next Steps

1. **HY310 is currently down** — needs physical power cycle
2. Test module ready: `/tmp/disp_test/h713_disp_test.ko` on build server
3. Once device is back:
   ```
   scp /tmp/disp_test/h713_disp_test.ko root@192.168.8.141:/tmp/
   ssh root@192.168.8.141 'insmod /tmp/h713_disp_test.ko; dmesg | tail -60'
   ```
4. Expected result: VBlender registers show non-zero values
5. Then proceed with DRM/KMS driver implementation

## DRM/KMS Driver Architecture

The new DRM driver replaces ge2d/tvtop with a clean mainline implementation:

```
drivers/gpu/drm/h713/
  h713_drm_drv.c       — DRM device, clocks, reset, TVTOP routing
  h713_drm_crtc.c      — CRTC wrapping VBlender/OSD scanout
  h713_drm_plane.c     — Primary plane (OSD layer 0, ARGB8888)
  h713_drm_lvds.c      — LVDS encoder (0x051C0000)
  h713_drm_connector.c — Fixed 1920x1080 connector
  h713_drm_bridge.c    — DLPC3435 DLP controller (I2C 0x1B)
  Kconfig + Makefile
```

The DRM driver itself manages:
- Clock enables (bus-disp, afbd, svp-dtl, deint, panel)
- Reset deassert (rst_bus_disp)
- TVTOP routing register programming
- VBlender/OSD register programming for scanout
- LVDS PHY configuration

No dependency on tvtop/ge2d modules.

## Register Map — From Live Dump + IDA RE

### VBlender 0x05200000 (Timing/Sync Generator)
```
+0x004 = 0x40210000  ← Control (bit30=enable?)
+0x00C = 0x07800068  ← H active=1920 (0x780), porch=104 (0x68)
+0x010 = 0x04380019  ← V active=1080 (0x438), porch=25 (0x19)
+0x014 = 0x0020802D  ← Sync timing
+0x018 = 0x00210022  ← Blanking
+0x020 = 0x07800068  ← H timing (layer 1 / duplicate)
+0x024 = 0x04380019  ← V timing (layer 1 / duplicate)
```

### OSD Plane Config 0x05248000 (GE2D Block3)
From IDA `tgd_put_plane_info` (ge2d_dev+48 base):
```
+0x00  Control/Format  — bits[15:8]=format code, bit31=?, bit0=COMMIT
+0x10  Size A          — packed macro-block geometry (16px units)
+0x14  Size B          — (height-1) | ((width-1)<<16)
+0x1C  Crop/offset A   — window positioning
+0x20  Crop/offset B
+0x30  Stride          — bytes per line
+0x34  Alt offset
+0x38  **SCANOUT ADDRESS** — framebuffer physical address ← CRITICAL
```
Commit sequence: write addr to +0x38, then set bit0 of +0x00.

### LVDS Controller 0x051C0000
```
+0x000 = 0x707F0000  ← LVDS control (dual-port, 8-bit)
+0x004 = 0x00050005  ← Data format
+0x008 = 0x01000000  ← Clock config
+0x00C = 0x00000003  ← Channel config
+0x010 = 0x00000045  ← Bit mapping
+0x014 = 0x18000005  ← Drive strength / timing
+0x020-0x030          ← LVDS PLL / lane config
+0x038 = 0x02000000  ← ?
+0x03C = 0x07800000  ← H pixels = 1920
+0x040 = 0x04380000  ← V pixels = 1080
+0x0A0 = 0x80000000  ← LVDS enable (bit31)
+0x0A4 = 0x07800000  ← H active
+0x0A8 = 0x04380000  ← V active
+0x0BC = 0x07800067  ← H total = 1920 + 103
+0x0C0 = 0x04380019  ← V total = 1080 + 25
+0x0C4 = 0xC0000000  ← Output enable
```

### TVTOP 0x05700000 (Bus Fabric)
```
+0x000 = 0x00011111  ← Display bus routing
+0x004 = 0x00000001  ← Enable
+0x040 = 0x00011111  ← Routing group 2
+0x044 = 0x11111111  ← Cross-connect
+0x080 = 0x00001111  ← Routing group 3
+0x084 = 0xFFF000EF  ← Config (1080p)
+0x088 = 0x11111111  ← Global enable
```

### AFBD Controller 0x05600000
```
Base +0x000 = 0x80000020  ← AFBD enable + config
Base +0x010 = 0x03000010  ← DMA config
Ctrl +0x040 = 0x03001901  ← Channel 0 config
Ctrl +0x050 = 0x043F077F  ← Size: 1087×1919 (height-1, width-1)
Ctrl +0x060 = 0x04380780  ← Active: 1080×1920
Ctrl +0x078 = 0x78541000  ← DMA address? / stride
IRQ  +0x168 = status, +0x16C = enable (from ge2d_osd.c)
```
