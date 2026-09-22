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

**What the firmware does with them: it scales into the ring.** Measured on the HY310 on 22.09.2026 with a
1080p60 source and a window of 192,108 1536x864: the DE picture scaler's window `0x05180034` went
`0x07800438` -> `0x06000360` (1536x864) and the processing node `0x05140124/28` to 1536/864, while INCAP's
active geometry `0x06940874` stayed 1920x1080 and its rowbyte `0x06940924` stayed `0x00780078`, 1920 bytes a
line. The firmware sizes its picture down by the window's share of the panel and writes it into a capture
ring it does **not** re-lay-out: the fresh picture lies in the ring's top left corner and the rest of the
ring still holds the last frame that filled it - which is why the first run, with the plane still reading
the whole ring, put a shrunken picture and a band of stale pixels on the wall instead of four fifths. The
placement on the panel is the plane's, and the plane reads only that part of the ring (`SRC_W`/`SRC_H`
follow the window, kernel 0133c).

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

**On a 1920x1080 panel the two agree exactly.** The vendor scales the rectangle into a fixed 30720x17280
space (`30720 * x / panel_width`); this driver writes 1/16 pixel of the real panel (`x * 16`), which is the
reading measured through our own record. For 1920x1080 they are the same number. On a panel of another size
they are not, and the 1/16-pixel reading is the one that was measured here.

**The stale-window caveat.** The scaler's own window register, `0x05180034`, is rewritten only when the
firmware rebuilds its window chain. It has been found standing at an old geometry on the HY310 (dev17,
20.09.2026: 1280x720 left there after a switch to 1080p), which is why the HDMI receiver reads it as a
cross-check and never as a source of truth. After a window change it did follow our republish at once
(22.09.2026, above), but it says what the firmware **did**, not what was asked for, and it can lag by one
change. What a window change is worth is decided on the wall, not in that register.

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
