# Display: how a picture reaches the imager

The projector's optics are fed by a **MIPS32 co-processor**, not by the ARM cores. Linux owns one block
of the chain and asks the co-processor for the rest. Knowing where that line runs explains most of what
looks strange about this SoC.

## Who owns what

| Owner | Block | What it does |
|---|---|---|
| ARM (Linux) | AFBD at `0x05600000` | feeds the video plane from the capture ring, writes the VidDec descriptor, and scans the primary plane out of DRAM - the console, or a frame the GPU rendered |
| MIPS (`display.bin`) | capture (INCAP `0x06940000`), window chain, scaler, panel output | everything between the source and the imager |

The ARM *can* read and even write the MIPS-owned registers. It does not help: without the firmware's own
recalculation the write is either ignored or harmful. Measured - a 960×540 processing window at 1080p
changes nothing on screen, and hand-resetting the scaler after a firmware rebuild does not bring back a
doubled image. The only lever that works is making the firmware recompute.

## Bring-up order

1. **U-Boot** loads `display.bin` plus the panel tables, reserves the SMM heap the firmware allocates
   from, and starts the MIPS (`h713_disp init`). Without the heap, the firmware's `SetSource` dereferences
   a null pointer and takes the ARM down with it - that cost three sessions to find.
2. **Linux** binds `sun50i-h713-afbd`, which registers a KMS device (`card1`): one CRTC with `GAMMA_LUT`
   and `CTM`, one plane that scans out the HDMI capture ring, an `aspect` property for letter- and
   pillarboxing, and the two window properties the zoom is made of (below).
3. **`h713-tv`** puts the capture ring on the plane, and the framebuffer console back when the signal
   disappears.

The panel timings live in the vendor tables, not in a device tree: `h713_project` selects the
`ProjectID_0x*.TSE` group, and the artifacts come from the `hy310-boot` partition by name, so renumbering
partitions cannot break them.

## What the KMS device gives you

Anything that can draw on DRM/KMS works - `modetest`, a compositor, mpv. The shipped image runs `h713-tv`
instead of a desktop because the projector's job here is the HDMI input, but nothing prevents a
compositor from taking `card1`.

Gamma and white balance are ordinary CRTC properties, computed from the vendor picture tables by
[`h713-pq`](../tools/h713-pq.md); they are not baked into the driver.

## The window words: one transform into the capture ring

The eight window words of the VidDec descriptor describe **one transform into the capture ring**, and
nothing else in the chain does. Words 27..30 (`m_src_cfg`) are the part of the source the firmware reads,
words 31..34 (`m_dst_cfg`) the part of the ring it writes the result into, both as fractions of the
firmware's own coordinate space (below); the frame's own geometry lives in words 2..5, separately. The
firmware **skips its scaler entirely while the source window is the whole frame**, which is why a
destination window on its own does nothing. The plane always shows (part of) the ring and its
`CRTC_X/Y/W/H` is the placement on the panel - it reaches no descriptor word. So there are exactly two
zooms:

- **in**: source window = the centre 1/f of the frame, destination absent, plane over the whole panel. The
  firmware blows that window up into the whole ring.
- **out**: source window = the frame less two pixels (any crop at all, to defeat the skip), destination
  window = W x H at the **ring's origin**, and the plane crops that region out of the ring (`SRC 0,0 WxH`,
  kernel `0133c`, which crops from the first byte and no other) and places it where it belongs
  (`CRTC x,y WxH`). Outside the plane the panel shows the primary plane: console or black.

Both windows are plane properties - `src-window` and `dst-window`, a blob of `x, y, w, h` in **panel
pixels**, absent meaning the whole thing and publishing the record of before word for word (kernel
`0133f`). Every publication logs the eight words.

**The measurement this rests on** (HY310, 1080p60, test pattern and camera, 22.09.2026, `dev21`
"Q15 bench"): destination 192,108 1536x864 with a full source window - the DE picture scaler's window
`0x05180034` followed to `0x06000360` and the processing node `0x05140124/28` to 1536/864, and the wall did
not change at all (cell pitch 63 px, as at the baseline). Source 480,270 960x540 with no destination - DE
960x540, processing node still 1920/1080, and the centre quarter filled the panel at twice the cell pitch.
Source 1918x1078 with destination 0,0 1536x864 and the plane cropping and placing it - the whole picture at
four fifths, centred, with a black band where it ends. Source at exactly full, or at 1918x1078 with a
destination but the plane left over the whole panel: the baseline again. INCAP's active geometry
`0x06940874` and its rowbyte `0x06940924` never moved in any of it - the ring's layout is not what changes.

**What the plane cannot do.** With the full ring as its source and a smaller rectangle as its destination
the wall was smeared, and stayed smeared after the DE window had been written back to 1920x1080 by hand:
this composition block does not downscale an NV16 ring. A zoom out is therefore a 1:1 crop placed on the
panel, never a plane downscale, and the driver refuses a request that would need one.

**The V4L2 format does not move with a window.** The ring geometry (`0136f`) comes from the rowbyte and
INCAP active, and neither moves: the ring is still 1920x1080 with a 1920-byte pitch, which is what it really
is. A window is not a property of the signal; it is what a client asked for, and that client knows it.

**Why the descriptor and not an RPC.** The vendor has a second route for this, the co-processor call
`THal_Vp_Wce_SetWindow` (capture, display and aspect windows in a 30720x17280 space). We do not use it. The
record is already published on every geometry change, the words are already there and already read, and the
call would need three physically addressed shared buffers for something the descriptor carries for free.
The vendor's own hardware composer takes the descriptor route for its video layer and tears nothing down
for a window change; the RPC is the fallback if a board ever turns out not to re-run its window manager on
a republished record. Source (reverse engineering of the stock firmware): `umbau/re-apps/AP3c` sections 3-5,
`AP3e` section 2, `AP3` section 2.

**The space the words live in.** They are fractions of the firmware's fixed 30720x17280 space, not 1/16 of
a pixel: `30720 * x / panel_width` and `17280 * y / panel_height` (`AP3c` 3.4). On a 1920x1080 panel the two
readings are the same number, which is why this driver could not tell them apart for a long time; on a
1280x720 panel they are not, and "the panel in 1/16 pixel" reads there as two thirds of the space - the
853x480 ring the HY300 Pro's owner measured (kernel `0133d`).

**The stale-window caveat.** The scaler's own window register, `0x05180034`, is rewritten only when the
firmware rebuilds its window chain. It has been found standing at an old geometry on the HY310 (dev17,
20.09.2026: 1280x720 left there after a switch to 1080p), which is why the HDMI receiver reads it as a
cross-check and never as a source of truth. After a window change it did follow our republish at once
(22.09.2026, above), but it says what the firmware **did**, not what was asked for, and it can lag by one
change. What a window change is worth is decided on the wall, not in that register.

## The other channel: the primary plane, and the GPU on it

The AFBD block has two channels, and only one of them reads the capture ring. The **video** plane is the ring
path described above and nothing about it changed. The **primary** plane scans an ordinary DRM framebuffer out
of DRAM - normally the framebuffer console - and it takes an imported dma-buf as readily as its own. The
framebuffer has to be the mode's size and sit at the CRTC's origin, which the simple-pipe helper enforces
without any check of ours; there is no scaling and no positioning on this plane. That was where the keystone lived until 23.09.2026; since then the warped frame is NV12 on the **video** plane with
`hdmi-ring` 0, because that is the channel the firmware's nine picture controls act on. That is where the keystone
lives ([h713-warp](../tools/h713-warp.md)): the GPU reads the capture, draws the warped frame into a target
buffer and `h713-tv` commits that buffer on the primary plane.

**Measured on the HY310 on 22.09.2026** (`umbau/test-20260915/keystone-20260922.md`, stages S3 and S4), before a
line of the daemon existed: two `XRGB8888` dumb buffers of `card1`, handed to the render node through PRIME,
imported into EGL, drawn by the GPU and committed on the primary plane with the render's own fence as
`IN_FENCE_FD` - 600 and 900 commits, one page flip each, 0 errors, 59.4 fps, and the gradient with its moving
bar on the wall. With the live HDMI capture in front of it (`0136y`, `VIDIOC_EXPBUF`) the same loop ran 3,600
frames in 60 seconds with 0 `DQBUF` timeouts, 0 dropped flips and one late frame. Every fence was readable at
the first poll - the render of a 1080p frame finishes inside the commit path and adds no frame of latency.

**What the registers do while that runs**, read at 10 Hz through `/dev/mem` in the `0x0560xxxx` block:
`AFBD_SRC` (`0x05600178`) alternates between the two CMA buffers, 8 MiB apart; `AFBD_STRIDE` (`0x05600170`)
stands at 7680, the panel's 1920 pixels of four bytes; `AFBD_CTRL` (`0x05600140`) reads `0x03001901`; and the
encoder's selector (`0x051c006c`) reads `0x29000000`, RGB. Idle, with the console up, `AFBD_SRC` is the
`fbcon`'s own buffer.

**Nothing else writes that channel.** Over a 60-second watch with `h713-tv` going `auto`, `off`, `auto` and the
source unplugged and replugged, the RGB channel's address and stride never moved; `AFBD_CTRL` and the selector
toggled between console (`0x03001901` / `0x29000000`) and video plane on (`0x83001900` / `0x39000000`), which is
our own driver's channel switch and nothing else. The display firmware is not a co-writer here, so the warp does
not have to re-arm anything behind its back - and when the video plane goes off, the selector returns to RGB by
itself (`afbd.c:864-867`). The two planes are mutually exclusive by this route, which is why `h713-tv ctl zoom`
is refused while the warp is on.

**What imports.** 52 dma-buf formats are offered, and the ring's `NV16` layout imports both ways: as a single
external image, and as two planes, `R8` plus `GR88`. Both sampled a known grey and a saturated red back within
2 of the expected values, so either route would have worked and the choice is ours to make. The
daemon takes the two-plane form with its own BT.709 limited-range shader, so nothing depends on Mesa's internal
lowering table.

## Limits, honestly

- The **video** plane reads the capture ring **directly** rather than importing a dma-buf - functionally
  equivalent for this use, and the reason the display path and the HDMI input are more coupled than they should
  be. It is not a limit of the block: the **primary** plane imports and scans out an ordinary dma-buf (above),
  and since 22.09.2026 the HDMI receiver hands its capture slots out as dma-bufs too (kernel `0136y`).
- The picture geometry is whatever the firmware decides. We can ask for a different aspect handling and for
  the two windows above; we do not scale anything ourselves, and a window is a request the firmware
  may answer late or not at all.
- There is **no HDMI output** on this device. The imager is the only display.

Details: `doku/96-anzeigekette.md` (the whole chain, measured), `doku/86` (video plane), `doku/87`
(gamma/CTM), `doku/40-display.md` (bring-up history), `doku/74` (the null-pointer crash). For the primary
plane and the GPU on it: `umbau/plan/keystone/PLAN.md` (stages S3 to S5) and the device readings in
`umbau/test-20260915/keystone-20260922.md`.
