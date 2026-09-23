# Keystone

A projector that does not stand square to the wall throws a trapezoid. The vendor's firmware corrects that
by warping the picture before it is projected, and so does this: `h713-warp` bends the HDMI picture into a
quadrilateral on the Mali-G31, and `h713-keystone` can drive that quadrilateral from the projector's own
tilt sensor. This page is the whole chain - the first half for whoever wants a rectangle on the wall, the
second for whoever wants to know what it costs. The comfortable way to set it is the
[settings page](settings-page.md); everything below is what the page sends.

## The four corners

Eight numbers, two per corner, in per-mille of the panel, **positive inward**. 0 leaves a corner where it
is; 150 pulls it a seventh of the way towards the middle of the picture.

```
h713-warp ctl keystone set tl x 150     # absolute, 0..1000
h713-warp ctl keystone nudge tl x -10   # relative, -1000..1000
h713-warp ctl keystone reset            # all eight back to 0
h713-warp ctl status                    # the eight values and where the corners land
```

`tl tr bl br` are the corners of the projected picture **as you see it on the wall** - verified on the
HY310 on 22.09.2026 by pulling `tl` in and looking at which corner moved. `x` and `y` are the two
directions. Every change is clamped and written to `/etc/h713/warp.conf` at once, whole and atomically, so
it survives a reboot.

**The clamp** is the vendor's own: the `x` of a corner is limited by the corner at the other end of its row
(`tl` by `tr`, `bl` by `br`), the `y` by the one at the other end of its column, and the two together may
not exceed 1000. So the picture can never be pulled past its own width or height. When a value runs into
that limit, **the value being set gives way and the partner keeps what it has** - which is how a key press
behaves on the vendor's remote, and what `h713-warp ctl keystone set` answers with
`(clamped against the corner at the other end)`.

## The matrix

The eight insets become a projective homography - the vendor's own `getKeyStoneMatrix`, ported function by
function and tested against it. The four panel corners are mapped onto the four inset corners, in the
vendor's slot order, and every intermediate value is rounded through float32 exactly where the vendor's is,
so the same eight numbers give the same matrix bit for bit. Two refusals are the vendor's too, and both
keep the picture that is on the wall: a solve that would put a corner outside the panel leaves the previous
matrix standing, and so does a degenerate quadrilateral - two corners in the same place - which would
otherwise divide by zero. Each is one line in the journal.

## By hand, or by itself

**By hand** is the four corners above, or the drawing on the settings page. Nothing moves them afterwards.

**By itself** is `h713-keystone`. It reads the SC7A20 accelerometer on `twi1` (kernel patch `0162`, the
node probes as `iio:device2` named `sc7a20`), turns the tilt into the vendor's two angles, runs the
vendor's own corner geometry and pushes the eight values in. Three poses on the bench on 22.09.2026 decided
the axis map, which is why it is a configuration key and not a device-tree claim: pitch is raw `+y`, roll
raw `-x`, vertical `+z`. It needs to be shown what level is, once:

```
h713-keystone reference      # with the projector standing the way it is meant to throw
h713-keystone once --apply   # the eight insets for the tilt it has right now
h713-keystone status         # configuration, sensor, reference, and whose values the warp carries
```

The reference is stored in `/etc/h713/keystone-ref` in the vendor's units, with the axis map it was taken
under. A pose more than 45 degrees off flat is refused - that is the vendor's own gate - and so is a
reference from another axis map, because its numbers describe a different pose.

### After a move, once - and the gate

`h713-keystone watch` is what the unit `h713-keystone-auto.service` runs, and it is **not a control loop**.
Nothing happens while the projector stands still, whatever a hand has set. When the tilt changes by more
than `move_degrees` (3) and the readings have then been still within `settle_degrees` (1) for
`settle_seconds` (2), the automatic runs **once**:

| `after_move` | what happens after a move |
|---|---|
| `off` (the shipped default) | the move is logged, nothing is applied |
| `keystone` | the automatic runs once |
| `keystone+focus` | the automatic runs once, then `focus_command` (`h713-autofocus run`) |

That is the gate: a keystone set by hand stays until the projector is moved again. `h713-keystone status`
says whose values are standing - `keystone by  auto` when they are the last automatic set untouched,
`manual` when a hand has changed them since. The comparison is against `/var/lib/h713-keystone/last-auto`,
which is what the automatic wrote last.

The key lives in `/etc/h713/keystone.conf`; the settings page's "After a move" buttons write it and restart
the unit.

### The calibration mask

```
h713-warp ctl test mask tl      # the mask with tl marked
h713-warp ctl test off          # back to the picture
```

A grey field with a white frame, a circle with a crosshair and a centre dot, the marked corner ringed, and
four labels reading `tl x 210/740  y 312/1000` - value and the most that corner may still take - plus the
zoom. It needs no source plugged in, which is the point. While the mask is up, `keystone set` and
`keystone nudge` mark the corner they touch.

## The zoom is part of the same matrix

`h713-warp ctl zoom PERCENT` (10 to 100, 100 = none) pulls **every** corner in by `(100 - percent) * 5`
per-mille on top of the eight values, and the result is clamped the vendor's way and solved as one matrix.
There is no second pass and no second cost: at 60 per cent the picture is smaller on the wall, sharp, and
nothing is cut off.

The display firmware's own "zoom out" was retired on 24.09.2026. Measured at the DE's picture scaler, a
destination window smaller than the frame left the ratio at unity and the firmware put the top left crop
into it: that scaler only enlarges. The vendor shrinks with the GPU inside the keystone matrix, and so do
we. What is left of the firmware's is the magnifier, `h713-tv ctl zoom in F`, and it is refused while the
warp draws, because then the plane does not show the ring at all.

## What it costs

Since 24.09.2026 the warp renders **NV12 onto the video plane**, not RGB onto the primary one: two passes,
luma at full size and chroma at half, through the same matrix and with no colour arithmetic at all. That is
the channel the firmware runs its nine picture controls on, so brightness, contrast and the rest act on the
warped picture exactly as on the ring. Measured on the HY310, same stream, one minute each:

| | RGB on the primary plane | NV12 on the video plane |
|---|---|---|
| `h713-warp` CPU | 9.5 % | 12.9 % |
| `h713-tv` CPU | 4.3 % | 2.1 % |
| system busy (four cores) | 35.2 % | 39.9 % |
| GPU clock | 600 MHz 83 %, 696 MHz 17 % | 432 MHz 73 %, 600 MHz 8 %, 696 MHz 17 % |
| SoC / GPU zone over the minute | 57.6 to 58.6 C, rising | 57.7 to 55.6 C, falling |
| frames | 59.4 fps, 0 dropped | 59.4 fps, 0 dropped |
| bytes per frame, read + write + scanout | 4.15 + 8.29 + 8.29 = 20.7 MB | 4.15 + 3.1 + 3.1 = 10.4 MB |
| the nine picture controls | do not act | act |

The three target buffers cost 24.9 MB of CMA. With all eight values 0 and the zoom at 100 none of this
happens: the daemon does not open the render node, and the picture path is the one a fresh image has.

## The latency, and why

The warp adds **one frame, 16.8 ms**, on purpose. The display firmware hands a ring slot on before it has
finished writing it: measured through `/dev/mem` on 23./24.09.2026, the bottom line of a published slot
still changed up to 11.5 ms after the publish and the middle up to 8.5 ms. A raster display never notices,
because it reaches those lines later than the writer does; the GPU reads the whole slot in a millisecond
and mixed the previous frame's bottom under the new frame's top - vertical lines on fast motion. A fixed
wait of 4 ms covered the median and not the tail. So the warp keeps a slot back and draws the one from the
previous vsync: by then the write is over, and the next write into that slot begins no earlier than 33 ms
after its publish (5 % at 34.4 ms, median 39.6). A held slot older than 28 ms is given back undrawn - a
dropped frame, never a torn one - which is what happens when something stalls the loop.
`h713-warp ctl hold off` is the old timing; it is the self-check's control, not a setting.

## The self-check

```
h713-warp ctl check 900      # then wait 20 s
h713-warp ctl status         # "check   900 frames, 0 with differing rows"
```

Every third slot is drawn a second time into a scratch buffer 4 ms after the first draw and compared in 32
sampled rows. A row that differs was read out of a slot the firmware had not finished writing. Zero
differing rows over a few hundred frames of motion is the pass; a band of differing rows at the bottom is
the source race. Measured with the settings page polling: 900 frames, 0 differing, 0 late samples, worst
frame 4.5 ms. The control run with `hold off`: 106 of 212 frames differed. On the `v0.95-beta` image as
installed, twice: 300 frames, 0 differing.

The check costs frames while it runs: the second draw and its readback hold the loop long enough that
the next held slot is often past the 28 ms and is skipped - `stale slots skipped` on the status line grows
by about 1.6 per checked frame and the rate drops to about 30 fps for those seconds. Skipped is dropped,
not torn. It is a diagnostic; it ends by itself.

This is the way to check tearing without standing in front of the wall. `ctl trace N` logs the next N
dequeues with their timestamps, the gaps between pumps and any slow phase.

## Without a signal

`h713-tv` refuses `warp claim` while there is no signal, and releases the warp when the signal goes: the
ring would keep handing out its last frame and the warp would go on drawing it, so the wall would freeze.
The console comes up instead, the daemon falls back to bypass and asks again once a second, and the picture
is back under a second after the signal is.

## Open points

**Edge blending.** The vendor softens the edges of the warped quadrilateral (its `draw_edge` pass). We do
not. On a dark wall the boundary of the corrected picture is a hard line rather than a fading one. It is
cosmetic, it is understood, and it is left out.

**The throw ratio.** The automatic computes with 0.8176, the ratio implied by the optics constants in the
device's own `camprjspe.ini`, because nobody has measured this projector with a tape. If the real ratio
differs, every automatic correction is too strong or too weak by that factor. `throw_ratio` in `/etc/h713/keystone.conf` takes a
measured number - image width divided by distance - and the correction scales with it. Setting corners by
hand is unaffected.

Details: [h713-warp](../tools/h713-warp.md), [h713-keystone](../tools/h713-keystone.md),
[settings-page.md](settings-page.md), and the device readings behind every number above.
