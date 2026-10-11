# libh713osd - the overlay pictures

A small C library that draws the projector's overlays - volume, mute, focus, input - into an ARGB8888 buffer.
It knows nothing about DRM, sockets or time: the caller says what to show, the library draws it, and returns the
rectangle it touched. Planned users: the overlay daemon `h713-osd` (TODO 2.43-2.46, `doku/192`), later a desktop
compositor (the rule of 2.45: drawing and the place it goes are separate). State: **draft for choosing the place**
(P0b of `arbeit/einblendungen-20261011/PLAN.md`); nothing on a device yet.

```
osd.h          the interface: osd_canvas, osd_style (place, look, scale), osd_item (kind, value, flags, alpha)
osd.c          the drawing
osd-mockup.c   a host tool: every place, look and case as one PAM picture, to lay over photos
```

## How it draws

Every shape is a signed distance field evaluated per pixel - round-capped strokes, circular arcs, rounded
rectangles - with one pixel and a fifth of anti-aliasing. No font file, no images: the digits are drawn for this
library with arcs and strokes (a box 6 wide, 10 high). Everything scales with the panel height (`u` = height /
1080 times `style.scale`), so 720p and 1080p panels get the same layout.

Each line has a **tone**: bright white, dim white (the bar's track, the waves above the level, the volume kept
under a mute, the direction not pressed) or **red** - the end of the focus travel. Items are mixed "over" what the
canvas holds (straight alpha), so a later item stacks over an earlier one.

| Kind | Picture |
|---|---|
| `OSD_VOLUME` | speaker with up to three waves (bright up to the level), a thin bar, the number |
| `OSD_MUTE` | the speaker crossed out; bar and number stay, dim - the volume is kept, not heard |
| `OSD_MUTE_BADGE` | the crossed-out speaker, small, while muted - in a faint disc with the pill, with a shadow in the bare look (top right; top left when the overlays sit top right) |
| `OSD_FOCUS` | a viewfinder and both directions stacked: the pressed one bright, the other dim; with `OSD_EDGE` the pressed one is **red** with a red bar across its tip (the owner's choice, 11.10.2026: a symbol alone would not tell a user that the end is reached) |
| `OSD_INPUT` | the HDMI plug and the console prompt side by side, the active one bright |

Every item is one strip of white lines. Looks: `OSD_PILL` - a dark translucent panel with fully rounded ends
behind the strip, the owner's preference - and `OSD_BARE` - no panel, a soft dark shadow around each line keeps it
legible on a bright picture. A square card in the middle was tried and rejected on 11.10.2026 ("rounded backgrounds
that are completely rectangular do not work"). Places: `OSD_BOTTOM` (centred above the lower edge, where the stock
firmware shows its volume), `OSD_TOP_RIGHT`, `OSD_CENTER` (the same strip in the middle).

## Speed

Measured on the HY310 (11.10.2026, `-DOSD_PROFILE` splits `osd_draw` into the work buffer's fill, the
primitives and the mixing): the volume strip 568 x 104 px took 209 ms in the first draft; now 5.2 ms (fill 0.4,
primitives 1.2, mixing 3.5), focus 1.6 ms, the badge 1.2 ms. Each primitive is evaluated only within its own
rectangle (beyond its reach it adds nothing); the layers are mixed premultiplied in one pass; `sqrt` instead of
`hypot`, two cross products instead of `atan2` for arcs; per row the stretch where a pill covers fully or not at
all is known from its shape, and a pixel with nothing but the pill over a clear canvas gets its value directly.
Every step was compared with the pictures before it (`osd-mockup`): bit for bit, or - the one-pass mixing - at
most one level of rounding. `osd_clear_box()` clears a rectangle (what `osd_draw` returned) instead of the whole
canvas. `osd_draw` keeps one static work buffer: not reentrant.

## Building

In the container `h713-build`: `make host` builds `osd-mockup`; `make mockup DIR=...` renders every case as PAM
(60 pictures at 1080p). `make cross` builds `libh713osd.aarch64-linux-gnu.a` for the board, with clang
against the board root, as `h713-warp` is built (not tried yet).

## Not decided, not measured

Which place (the owner chooses on the mock-ups); whether the display's channel 2 wants premultiplied
alpha (measured in 2.48 - the library writes straight alpha); text (a font comes with the power-off message,
TODO 2.38). The time to draw one item on the board is not measured.
