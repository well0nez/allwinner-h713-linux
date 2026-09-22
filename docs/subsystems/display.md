# Display: how a picture reaches the imager

The projector's optics are fed by a **MIPS32 co-processor**, not by the ARM cores. Linux owns one block
of the chain and asks the co-processor for the rest. Knowing where that line runs explains most of what
looks strange about this SoC.

## Who owns what

| Owner | Block | What it does |
|---|---|---|
| ARM (Linux) | AFBD at `0x05600000` | feeds the video plane from the capture ring, writes the VidDec descriptor |
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
   pillarboxing, and a destination rectangle the firmware scales into (below).
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

## The window words: where the picture is put, and who scales it

The plane's destination rectangle - the ordinary `CRTC_X`, `CRTC_Y`, `CRTC_W`, `CRTC_H` - is not programmed
into any register here. It is written into **words 31..34 of the VidDec descriptor** the driver publishes,
in 1/16 pixel, and the firmware's window chain reads it as its `m_dst_cfg` and recomputes capture, noise
reduction, processing window, scaler and panel output from it. Words 27..30 next to it are `m_src_cfg` and
stay the panel; the frame's own geometry lives in words 2..5, separately. Setting `CRTC_W` to 80 % of the
panel is what the vendor's Android stack calls a digital zoom, and it reaches the same firmware code by the
same numbers.

**Why the descriptor and not an RPC.** The vendor has a second route for this, the co-processor call
`THal_Vp_Wce_SetWindow` (capture, display and aspect windows in a 30720x17280 space). We do not use it. The
record is already published on every geometry change, the words are already there and already read, and the
call would need three physically addressed shared buffers for something the descriptor carries for free.
The vendor's own hardware composer takes the descriptor route for its video layer and tears nothing down
for a window change; the RPC is the fallback if a board ever turns out not to re-run its window manager on
a republished record. Source (reverse engineering of the stock firmware): `umbau/re-apps/AP3c` sections 3-5,
`AP3e` section 2, `AP3` section 2.

**On a 1920x1080 panel the two agree exactly.** The vendor scales the rectangle into a fixed 30720x17280
space (`30720 * x / panel_width`); this driver writes 1/16 pixel of the real panel (`x * 16`), which is the
reading measured through our own record. For 1920x1080 they are the same number. On a panel of another size
they are not, and the 1/16-pixel reading is the one that was measured here.

**The stale-window caveat.** The scaler's own window register, `0x05180034`, is rewritten only when the
firmware rebuilds its window chain. It has been found standing at an old geometry on the HY310 (dev17,
20.09.2026: 1280x720 left there after a switch to 1080p), which is why the HDMI receiver reads it as a
cross-check and never as a source of truth. After a window change the register follows **our** republish, if
it follows at all - so read it to see what the firmware did, not to see what was asked for, and expect a
value that lags by one change. What a window change is worth is decided on the wall, not in that register.

## Limits, honestly

- The plane reads the capture ring **directly** rather than importing a dma-buf. Functionally equivalent
  for this use, marked "transitional" in the driver, and the reason the display path and the HDMI input
  are more coupled than they should be.
- The picture geometry is whatever the firmware decides. We can ask for a different aspect handling and for
  a destination window (above); we do not scale anything ourselves, and a window is a request the firmware
  may answer late or not at all.
- There is **no HDMI output** on this device. The imager is the only display.

Details: `doku/96-anzeigekette.md` (the whole chain, measured), `doku/86` (video plane), `doku/87`
(gamma/CTM), `doku/40-display.md` (bring-up history), `doku/74` (the null-pointer crash).
