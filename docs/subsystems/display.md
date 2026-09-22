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
in the firmware's own coordinate space (below), and its window chain reads them as `m_dst_cfg` and
recomputes capture, noise reduction, processing window, scaler and panel output from it. Words 27..30 next
to it are `m_src_cfg` and stay the whole picture unless somebody says otherwise (below); the frame's own
geometry lives in words 2..5, separately. Setting `CRTC_W` to 80 % of the
panel is what the vendor's Android stack calls a digital zoom, and it reaches the same firmware code by the
same numbers.

**The two windows, and what each one moves.** Words 27..30 (`m_src_cfg`) are the window the firmware reads
out of its capture; words 31..34 (`m_dst_cfg`) are the window it puts the result into. The vendor pins the
first to the whole space and writes its video layer's display frame into the second, and its own
"zoom 80 %" is the other way round: a shrunk capture window with the display window left whole, which the
scaler then blows back up to the full panel (`AP3` section 2.2). So a smaller source window is a zoom
**in** and a smaller destination window a zoom **out**. Both can be driven without touching the plane at
all - the AFBD module takes `src_window` and `dst_window` as `x,y,w,h` in panel pixels, empty means the
whole picture and the whole panel, and a write republishes the record on the spot (kernel `0133e`). Every
publication logs the eight words.

**What was measured on 22.09.2026, and what it corrected.** With the destination window at 192,108
1536x864 the DE picture scaler's window `0x05180034` went `0x07800438` -> `0x06000360` and the processing
node `0x05140124/28` to 1536/864, while INCAP's active geometry `0x06940874` stayed 1920x1080 and its
rowbyte `0x06940924` stayed `0x00780078`. So the firmware does re-run its window chain for these words.
What it does **not** do is scale into the capture ring, which an earlier reading of that run assumed: with
a window of 480,270 960x540 the wall carried the source's top-left quarter at 1:1, and after the test
pattern was closed the live desktop's top-left corner at 1:1, so the ring goes on receiving the whole
picture and the registers that followed belong to the display side of the chain. The other direction is
closed too: with the plane's own rectangle at 192,108 1536x864 and the full ring as its source the wall was
smeared, and stayed smeared after the DE window had been written back to 1920x1080 by hand - this
composition block does not downscale a 1920x1080 NV16 ring. The plane may still be given a source rectangle
smaller than its framebuffer (kernel `0133c`), but that is a crop of the ring, not a zoom. Whether the
descriptor's windows alone put four fifths of the picture on a black panel is open; nothing on the wall has
answered it yet.

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
