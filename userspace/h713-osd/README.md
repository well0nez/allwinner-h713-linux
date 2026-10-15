# h713-osd - the overlays over the picture

A small C daemon: volume, mute, focus and input appear over the HDMI picture when something happens. Whoever
knows that something happened says so in one line on `/run/h713-osd/ctl`; `h713-keys` does it after every key of
the remote. The overlay is drawn with `../libh713osd`, pre-distorted with the warp's own matrix when the picture
under it is warped (`../libh713geom`), and handed to `h713-tv`, which lays it over the picture on the display's
primary plane (`h713-tv` README 6h). TODO 2.43-2.46, plan and measurements in `arbeit/einblendungen-20261011/`.

```
h713-osd run                         what the unit runs
h713-osd ctl volume 40               the volume overlay, 40 of 100
h713-osd ctl mute on 40 | mute off 40   mute: the overlay, and the badge that stays while muted
h713-osd ctl focus up|down [edge]    the focus; "edge": the end of the travel, the arrow turns red
h713-osd ctl input console|hdmi      which input the picture comes from
h713-osd ctl launcher 1;HDMI 1080p60;hdmi:HDMI input;film:Kodi;>power:Standby    the launcher (below); "launcher 2" moves, "launcher close" closes
h713-osd ctl hide                    the overlay away now (a mute badge stays)
h713-osd ctl status                  state, channel, matrix, style, and where the last refresh spent its time
```

## How a refresh goes

1. **Compose** (libh713osd): the overlay (region 0) and, while muted, the badge (region 1) are drawn into a
   canvas the size of the panel - straight, as on an unwarped picture. Two regions, never one rectangle around
   both: together they span most of the panel, and the pre-distortion would walk all of it.
2. **Ask** h713-tv "osd picture": `warped`, `ring` or `none`. Only over the warp is the overlay pre-distorted.
3. **Put** each region into the buffer that is not on the panel: straight (a copy), or pre-distorted - the
   region's corners through the matrix give its rectangle on the panel, every pixel there goes back through the
   inverse (`warp_unpoint`) to the canvas and takes what lies there (bilinear). Keystone, zoom and the projection
   mode (rear, ceiling: mirrored) are in that one matrix, so the overlay sits in the picture like the picture.
4. **Show**: "osd show N" to h713-tv; over the warp it goes with the warp's next frame.

What lies under a shown overlay can change without an event: the signal comes back over the ring and the warp
takes over a second later, or the warp is switched off and on. So while something is to be seen over a keystone
(a non-identity matrix), h713-osd asks "osd picture" again every 250 ms and draws anew when the answer no longer
fits the way it was drawn - one journal line, "the picture under the overlay is warped now -- drawn again".
Without a keystone nothing is asked. Found on the HY300PRO-G-EU on 11.10.2026: the badge, set while the signal
was away, stayed straight over the warped picture once the warp was back.

The mute badge follows h713-tv's own mute: h713-osd asks it ("mute") at its start and before every claim, so the
badge survives a restart of either daemon - an update, a standby (measured 11.10.2026: h713-tv muted, h713-osd
restarted, the badge there without a key). Between claims the events from h713-keys keep it (h713-keys mutes
h713-tv first, then tells h713-osd).

The matrix comes from `/etc/h713/warp.conf`, solved exactly as h713-warp solves it (`warp_effective`,
`warp_matrix`, `warp_mirror`); every `h713-warp ctl` change rewrites that file, and an inotify watch on its
directory reloads it. `osd.conf` (place, look, scale, seconds) is watched the same way.

## Timing (measured on the HY310, 11.10.2026, over the warp with a strong keystone)

| Overlay | first draft | now | where the time goes now |
|---|---|---|---|
| volume | 209 ms (draw alone), 49 ms with the first pre-distortion | **13 ms** | draw 6.5, pre-distort 6.4 |
| mute + badge | 220 ms | **15 ms** | draw 8.0, pre-distort 7.1 |
| focus at the edge | 61 ms | **8 ms** | draw 5.2, pre-distort 2.5 |
| input | - | **7 ms** | draw 4.7, pre-distort 2.6 |

What brought it down, each step checked against the pictures before (pixel for pixel, or at most one level of
rounding): each shape evaluated only within its own rectangle (libh713osd); one premultiplied mixing pass instead
of three divisions per layer, `sqrt` instead of `hypot`, two cross products instead of `atan2`, and per row the
stretch where a pill is plainly full or empty known from its shape; the badge apart from the overlay; the
homography stepped along the row with the exact stretch of pixels that can show anything; integer bilinear
sampling of a premultiplied copy with a table of reciprocals, and a short way for four equal neighbours. The
compiler's `-O3 -mcpu=cortex-a53` made no measurable difference, so the build stays `-O2`. A GPU path (the Mali
draws the warp) would add an EGL dependency and share the GPU with the warp's 60 frames a second for work that
happens a few times per key press; not worth it at these times - a later desktop compositor draws there anyway.
`ctl status` shows the split of the last refresh: draw, ask, clear, pre-distort or copy, show.

## The launcher

`launcher SEL;NOW;[>]icon:label;...` (package H of the media side project, [docs/tools/h713-osd.md](../../docs/tools/h713-osd.md)):
the launcher is an **opaque page** over the whole panel - a ground, the mock-up's "Launcher C" list in the column on the left (header
and hint line, up to six rows, Standby set apart at the foot), the rest calm, everything inside the 5 % safe margin - that stays
until it is closed. h713-keys is its controller; this daemon only draws and shows it. It is cut into **tiles** (libh713osd: the page's
bands - the header, one per row of 124 units, the foot, the gap - each in a left part, the column, and a right part, the ground).
A tile is drawn again in the canvas when it changes and put into a buffer when that buffer does not hold its current version
(`gen[]`, `cgen[]`, `ver[]`, `held[][]` in `main.c`): moving the selection costs two row tiles of the column, not the page. Over a
keystone the put is the pre-distortion, which walks every pixel it writes: the page is two million pixels, two row tiles are
about 170 000. So the buffer that is **not shown is filled in the idle time** after a refresh (`prefill_at`, 0.12 s): the next key
finds the page in it and puts two tiles. The volume strip, the mute badge and the power countdown are drawn into the page's
canvas and ride in the tiles they touch (the tiles under the last strip are repainted to take it off).
What makes the tiles meet on the panel: each tile's source has two rows and columns of its neighbours around it, so the bilinear
sample at its edge is right; it writes only the panel pixels whose source lies in the tile itself, so two tiles never overwrite each
other's edge with a half-transparent one; and only the pixels that count are written - the margin pixels of a run, which the
range test turned down, belong to a neighbouring tile (the tiles meet along slanted lines through the matrix) and a zero written
there is a hole in an opaque page (found by the move-equals-fresh test when the tiles were split left and right). When the matrix
changes, the picture under the page turns warped or straight, h713-tv comes back or the launcher closes, the buffers are cleared
(the page covers all of a buffer) and the tiles are put again. `H713_OSD_FONT` names the font (the image's Quicksand by default),
`H713_OSD_CLOCK` a fixed header time and `H713_OSD_TRACE=1` a journal line per refresh and per prefill with wall-clock times (the
tests; gate HL).

## Building and testing

In the container `h713-build`: `make cross SYSROOT=...` for the board (clang, as h713-tv is built), `make host`
and `make test` for the host tests (`tests/test_osd.py`, 11 tests, ~11 s; `tests/test_launcher.py`, 10 tests with a font: `OSD_TEST_FONT`): a fake h713-tv on a Unix socket that
hands memfds over instead of dma-bufs; the tests read where the overlay landed in the buffer - bottom centre,
pre-distorted inward over a keystone, mirrored in rear mode, following a new warp.conf, the badge staying and
coming back after h713-tv restarts, the badge drawn again when the picture under it turns warped or straight, and
no questions to h713-tv without a keystone. The environment variables `H713_OSD_SOCKET`, `H713_OSD_TV`,
`H713_OSD_WARP_CONF` and `H713_OSD_CONF` point the daemon at them.

## Limits

- No overlay without a picture yet: on the console (no signal, `h713-tv ctl off`) "osd show" waits; the overlay
  over the console is the next step (TODO 2.46, P5).
- No fade: an overlay goes after `seconds` at once.
- The badge and the overlay never overlap in any place; the pre-distortion relies on it.
- Not measured: the warp's frame rate while overlays change quickly (P6), the colours on the wall against the
  mock-ups, premultiplied or straight alpha in the display's mixing (the buffers carry straight alpha).
