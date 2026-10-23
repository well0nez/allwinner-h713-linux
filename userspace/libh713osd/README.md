# libh713osd - the overlay pictures

A small C library that draws the projector's overlays - volume, mute, focus, input - into an ARGB8888 buffer.
It knows nothing about DRM, sockets or time: the caller says what to show, the library draws it, and returns the
rectangle it touched. Planned users: the overlay daemon `h713-osd` (TODO 2.43-2.46, `doku/192`), later a desktop
compositor (the rule of 2.45: drawing and the place it goes are separate). State: **draft for choosing the place**
(P0b of `arbeit/einblendungen-20261011/PLAN.md`); nothing on a device yet.

```
osd.h          the interface: osd_canvas, osd_style (place, look, scale), osd_item (kind, value, flags, alpha), and the text
osd.c          the drawing
text.c         text: osd_font_open, osd_text, osd_text_width (FreeType)
osd-mockup.c   a host tool: every place, look and case as one PAM picture, to lay over photos
test-text.c    the host test of the text (`make test`), test-menu.c the host test of the launcher's drawing
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

## The menu and the launcher

The launcher of the Kodi image and the settings page draw menus
in the overlays' look, so the library has the pieces, in "1080-line units" (the mock-up's numbers, scaled by canvas
height / 1080):

| Function | What it draws |
|---|---|
| `osd_icon_by_name()`, `enum osd_icon` | the Strichsymbole of the mock-up: `hdmi`, `film`, `globe`, `desk`, `sliders`, `power` (48-unit boxes, round-capped strokes, the mock-up's paths; the globe's meridians are Beziers as chains of segments) |
| `osd_draw_row()` | one row: a symbol, a label, and - when selected - the pill (fill 72 % and a white outline) around them; everything scales with the pill's height; the label is clipped to the pill |
| `osd_draw_hint()` | a dim hint line, the arrows for up and down drawn as shapes (the face has no U+25B2) |
| `osd_launcher_bands()`, `osd_launcher_draw()` | the launcher's **opaque page**: the ground (`OSD_PAGE_GROUND` 0xff0b0e0d) over the whole canvas, the mock-up's "Launcher C" list in the column on the left (header, up to six rows, Standby set apart at the foot, hint line), the rest calm. Cut into **tiles**: the page's bands (header, one per row of 124 units, foot, and the gap between the rows at the top and those at the foot) each in a left part (the column, 700 units) and a right part (the ground alone); `osd_launcher_draw(c, l, tile)` repaints one tile, so moving the selection repaints two row tiles of the column and not the page |

The page is **opaque** (Marco, 15.10.2026: "launcher and settings must have a ground - that is not the same as the overlays"): a
translucent list over a picture is unreadable over some pictures. The ground and the lit pill (`OSD_PAGE_PILL` 0x1c2321) are the
colours of `h713-settings`' `ui.c`, so that launcher and settings are one line. Everything but the ground stays inside a **safe
margin of 5 %** on each side (`OSD_SAFE_PERCENT`: 96 px left and right, 54 px top and bottom at 1080p, 64 and 36 at 720p); `test-menu`
measures it at 1080p, 720p and 540p for every selection, with six rows and with the Kodi image's three - together with the page
being opaque everywhere, the tiles covering the canvas exactly once, the lit pill's exact colour, and the invariant h713-osd's
incremental redraw lives on: a tile repainted alone is bit for bit what a full draw gives, a move of the selection changes two tiles
and no other. `osd-mockup` draws the page in the states of the launcher as `launcher-*.pam`. (The first design, a gradient over the
running picture, is in the history of this file's commit: `0ad4e98`.)

## Text

`osd_text(canvas, "Kodi", x, baseline, px, 0xfafafa, alpha, max_w)` draws a UTF-8 string in one colour with FreeType
(`text.c`), mixed over the canvas in straight alpha like the shapes; `osd_text_width()` measures it, `osd_font_open()`
opens the one face (the first call wins; without a face nothing is drawn and the width is 0). Layout is the simplest
that is right for a menu: left to right, unhinted fractional advances, the font's kerning table if it has one, no
wrapping, no alignment (measure, then place), no cache. The face on the image is **Quicksand Medium**
(`fonts-quicksand`, SIL OFL 1.1, Debian trixie `0.2016-2.1`); it has no U+25B2/25BC, so arrows are drawn as shapes,
not typed. The library links FreeType; `h713-osd` links it **statically** (`libfreetype.a` and its png, bz2, brotli and
zlib from the sysroot's `libfreetype-dev`) so that the base image needs no FreeType package - only the font file, which the
`desktop` profile brings. `make test` runs `test-text` (widths, where the pixels land, clipping, the straight-alpha
mix, malformed UTF-8) against `OSD_TEST_FONT` or the image's font path and says "skipped" without one.

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
alpha (measured in 2.48 - the library writes straight alpha). The time to draw one item on the board is not
measured; text: the cost of a label on the board is not measured either.
