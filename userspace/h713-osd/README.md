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

## Building and testing

In the container `h713-build`: `make cross SYSROOT=...` for the board (clang, as h713-tv is built), `make host`
and `make test` for the host tests (`tests/test_osd.py`, 11 tests, ~11 s): a fake h713-tv on a Unix socket that
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
