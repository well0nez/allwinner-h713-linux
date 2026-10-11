# h713-warp - the keystone, on the GPU

`h713-warp` bends the HDMI picture into a quadrilateral so that a projector standing off-axis still throws a
rectangle on the wall. It is the Linux replacement for the vendor's keystone, and it is the same warp: a
projective homography built from eight per-mille corner insets, ported function by function from
`getKeyStoneMatrix` in the stock `system_a_libkeystone.so` and tested against that reference.

Nothing about the ordinary picture path changes. With all eight values at 0 - the state a fresh image comes up
in - the daemon does not open the render node at all, and `h713-tv` shows the capture ring exactly as it does
without this service.

## Who does what

| | owns | does |
|---|---|---|
| `h713-warp` | `/dev/dri/renderD128` (panfrost), the capture buffers, the shader, the matrix | reads the HDMI capture as dma-bufs, draws one warped frame per capture frame, hands it over with a fence |
| `h713-tv` | `/dev/dri/card1`, the DRM master, the panel | allocates the three NV12 target buffers, and commits them on the **video** plane with `IN_FENCE_FD` and `hdmi-ring` 0 |
| the kernel | the console | paints the console whenever neither of the two holds the master |

There is exactly one DRM master, and it stays `h713-tv`'s: two masters on one card cannot coexist, and a
handover dance on every `warp on` would be a race with a dark projector as its failure mode. The two speak
over `h713-tv`'s control socket, with the file descriptors in `SCM_RIGHTS` (README of h713-tv, section 6e).

Per frame: `DQBUF` a capture slot, draw it through the matrix into the next of three targets, make a native
fence, send `warp frame N` with that fence, and give the slot back only after `h713-tv` has answered - a slot
is overwritten every third frame and nothing in the dma-buf says so.

## `h713-warp ctl` - the control channel

The daemon listens on `/run/h713-warp/ctl`; a command is one line, the answer's first word is `ok` or `error`,
so the exit code is decided without parsing further.

| Command | Does |
|---|---|
| `status` | the state, the eight values, where the four panel corners land, the source, the panel, the renderer and the last hundred frames |
| `on` / `off` | run the warp or leave it. Run time only: what the next start does is the `warp =` line in the configuration |
| `keystone set CORNER AXIS VALUE` | absolute, 0..1000 per-mille, positive inward |
| `keystone nudge CORNER AXIS DELTA` | relative, -1000..1000 - the command a remote control sends |
| `keystone reset` | all eight corners to 0, which is the identity |
| `zoom [PERCENT]` | the screen zoom, 10..100 (100 = none): the picture smaller about its own centre, inside the keystone - the vendor's "Digital scaling"; saved as `zoom =` in the file |
| `edge [N]` | the soft border of the warped picture in panel pixels, 0..64: 0 = a hard edge, 4 = the vendor's (the default). The outer half of that width keeps 20/255 of the picture, then a linear ramp over one width reaches the picture - the stock's `draw_edge` (libkeystone), folded into the two passes as a per-fragment factor, no third pass and no extra texture; takes effect with the next frame and is saved as `edge =` |
| `mode [front\|rear\|ceiling\|rear-ceiling]` | the projection mode, the vendor's "Installation mode": `rear` mirrors the picture left-right for a screen lit from behind, `ceiling` turns it over, `rear-ceiling` flips it top-bottom only. Saved as `mode =` in the file. The flip is one sign change in the matrix after the keystone, so the corner names stay the wall's in every mode and the mask's labels land where they belong. A change of mode re-sorts the eight values the vendor's way (`setKeystoneNormalXY`): the correction stays with the housing, the quad on the panel stays where it was and the picture turns inside it - `ctl mode` prints the new values (06.10.2026); any mode but `front` keeps the GPU running even with all eight corners 0, and it mirrors nothing while the warp is off (the plain ring path is the firmware's) |
| `test grid\|border\|mask [CORNER]\|off` | draw a pattern instead of the capture, to aim a corner with no source plugged in; `mask` is the calibration picture of the manual keystone with the named corner marked and every corner's value and maximum printed |
| `dump PATH` | the last drawn frame's luma plane as a binary PGM - eyes for a test without a wall |
| `hold on\|off` | draw a slot one vsync late (on, the default): the firmware hands a slot on before it is written to the end, measured 23.09.2026; off is the old timing, kept as the self-check's control |
| `check [FRAMES]` | the self-check, no eyes needed: every third slot drawn a second time 4 ms later into a scratch buffer and compared in 32 rows; "N frames, 0 with differing rows" on the status line is the pass, one journal line per differing frame. While it runs the loop skips about every second held slot as stale (dropped, not torn) and the rate falls to about 30 fps; it ends by itself |
| `trace [N]` | log the next N dequeues with their timestamps, gaps between pumps and slow phases (draw, the peer's answer) |

`CORNER` is `tl tr bl br` **as the picture stands on the wall**, `AXIS` is `x` or `y`. Every change is clamped
and saved at once. The clamp is the vendor's: the x of a corner is limited by the corner at the other end of
its row and the y by the one at the other end of its column, so the picture can never be pulled past its own
width or height. The value that gives way is the one being set, never the one already there.

## `/etc/h713/warp.conf`

```
tl_x = 0    tl_y = 0        # eight inward offsets in per-mille of the panel
tr_x = 0    tr_y = 0        # 0 = the corner untouched, larger pulls it inward
bl_x = 0    bl_y = 0
br_x = 0    br_y = 0
zoom  = 100                 # the screen zoom in percent, 10..100 (100 = none)
edge  = 4                   # the soft border in panel pixels, 0 = a hard edge, 4 = the vendor's
mode  = front               # front, rear, ceiling or rear-ceiling; the corners stay the wall's
warp  = on                  # the state to come up in; `ctl on` and `ctl off` write it
```

The file is also what `ctl keystone` writes - whole, into `warp.conf.new`, `fsync`ed and renamed over, so a
power cut leaves either the old file or the new one and a keystone set with the remote survives a reboot.
`systemctl reload h713-warp` (SIGHUP) reads it again. Editing it by hand is allowed; a value that is not a
number 0..1000 is dropped with its line number in the journal.

## Starting it

```
systemctl enable --now h713-warp        # one instance, no template
h713-warp ctl status
```

The unit has **no ordering against `h713-tv`**, on purpose: `h713-tv` runs as the template instance
`h713-tv@videoN.service` started by udev, and `After=` cannot name "whichever instance udev starts". Instead
the daemon tolerates a peer that is not there: it stays in bypass, says so in `ctl status` and retries once a
second - which is also what it does when `h713-tv` is restarted under it. It carries no `After=` at all:
the unit is wanted by `multi-user.target`, and a unit ordered after the target that wants it is an ordering
cycle, which systemd breaks by dropping a job - on 23.09.2026 the warp's, so the warp was not running after
boot (fixed the same day, `h713-panel` had the same line).

## What happens when something is missing

Every one of these leaves a picture on the wall; that is the rule.

| | |
|---|---|
| all eight values 0 | the render node is never opened, `h713-tv` stays on the ring - no latency, no memory, the shipped behaviour bit for bit |
| no GPU, no mesa, a missing EGL extension | `ctl on` is refused by name (`ctl status` says which piece), the ring stays |
| no signal | nothing to warp; the daemon idles and `h713-tv`'s own console handback covers the wall |
| no `h713-tv` | nothing is claimed; the daemon retries once a second |
| five failed renders in a row, or a lost EGL context | released back to bypass, once in the journal |
| the source changes resolution | the six capture images are rebuilt from what V4L2 reports, not from the picture |

## Limits

The warp and the video plane are **mutually exclusive** - while the warp is on, the picture comes from the GPU
and `h713-tv ctl zoom` is refused with a pointer to `h713-warp ctl zoom`. The added latency is one frame
(16.8 ms): a slot is drawn one vsync after it was handed on, because the firmware publishes a slot anywhere
between the start and the end of its write (the bottom line still changed up to 11.5 ms after the publish, the
top is rewritten no earlier than 33 ms after it - working journal `keystone-20260922`). A held slot older
than 28 ms is given back undrawn, a dropped frame instead of a torn one; a frame that arrives while the
previous commit is still in flight is dropped rather than queued. `ctl check` proves the timing on any device.

**Since 23.09.2026 the warp writes NV12 onto the video plane**, not RGB onto the primary: Y is resampled into
the luma plane at full size and CbCr into the chroma plane at half size, both through the same matrix and
without any colour maths, and `h713-tv` commits the three buffers on the video plane with `hdmi-ring` 0. That
is the channel the firmware runs its nine picture controls on, so brightness, contrast and the rest act on the
warped picture exactly as on the ring (they did not reach the primary plane at all - the RGB channel joins
behind that block, re-apps AP2j). Measured against the RGB path on the HY310, same stream, a minute each: the
GPU governor settles at 432 instead of 600 MHz, the die cools instead of warming, the bytes per frame halve
(10.4 MB instead of 20.7), the warp's CPU rises by about three points for the second pass. NV16 on that plane
shows with every other chroma line dropped, so NV12 loses nothing. Without a signal `h713-tv` releases the
warp and shows the console; the warp asks again once a second and is back within a second of the signal. The warp costs about 0.6 GB/s of memory
bandwidth (read 4.15 MB of NV16, write 3.1 MB of NV12, scanout reads 3.1 MB instead of 4.15 MB per frame)
and 9.3 MB of CMA for the three targets. The vendor's edge blend is in (`edge`, since 27.09.2026): the same
darkening ring the stock draws as a blended alpha quad over its warped frame, computed here from the quad
coordinate in the luma and chroma shaders - luma towards Y 16, chroma towards 128 by the same factor, so
the band meets the border without a step and leaves no colour fringe; a few arithmetic instructions per
fragment on top of the texture fetch, no extra pass, no extra bytes. The band follows the quad (the vendor's
mask is stretched over it too), so a foreshortened edge gets a proportionally narrower band - within a pixel
of the stock's at a 200 per-mille correction, which interpolates its mask affinely per triangle. Which
physical corner the vendor's slot 0 is has been derived from the framebuffer's orientation and is confirmed on
the wall with one nudge and one photo; if top and bottom ever come out exchanged, it is two lines in
`matrix.c`.

The matrix (`matrix.c`) and `warp.conf` (`config.c`) live in `userspace/libh713geom/` since 11.10.2026, shared
with the overlay daemon `h713-osd`, which pre-distorts its overlays with the very same map so they stand in the
picture like the picture (TODO 2.44). h713-warp compiles both files in as before; its code and data are
bit-identical to the build before the move (only the build ID differs; compared section by section on 11.10.2026).

Details: working journal `keystone/PLAN` (stage S5), working journal `AP2d/design-h713-warp` (modules M1-M11),
working journal `AP2f/REPORT` (the matrix and its z trap), working journal `AP2/REPORT` (the vendor's units
and clamp), docs/tools/h713-tv.md.

## What a frame costs (measured 11.10.2026, HY300PRO-G-EU, 720p)

CPU time of the warp's thread per frame at a fixed 1296 MHz, from a measuring build (`arbeit/warp-sparsam-20261011/`):
dequeue 12 µs, **drawing 490 µs**, the fence 180 µs (the `glFlush` that submits the GPU jobs, and the sync file), the
round trip to `h713-tv` 64 µs, queueing the slot back 25 µs - about 0.77 ms. The drawing is two passes (luma at full
size, chroma at half size), and each pass costs Mesa/Panfrost about 125 µs to set up a GPU batch whatever the first
call is: without the `glClear` the draw call takes that time instead. Compiler flags make no difference (`-O3
-mcpu=cortex-a53 -flto` against `-O2`, A/B/A/B at a fixed clock: the same CPU per frame) - the time is in Mesa and the
kernel, not in this code. One pass per frame was tried and measured (branch `versuch/warp-einpass`): the NV12 buffer
as one R8 image of width × 1.5 height, the chroma rows a fragment per byte with the pair centre through the inverse
map (host test T1e: equal to the two passes within 2 LSB). It saved 14 % of the warp's CPU, but the chroma then had
twice the fragments, the GPU ran at its top clock 66-87 % of the time instead of 21-25 %, and about one frame a second
came back busy and was dropped - the two passes stay. *Superseded 11.10.2026:* "the next real step would be one pass
per frame ... not done yet".

The warp draws every slot the capture hands on: it wakes 0.1 ms after the slot's timestamp and is done 1.5 ms later.
How many slots there are is decided before it, in the firmware's capture: read straight from the flip pointer pair
(AFBD +0x320 through `/dev/mem`), the pair moved 30-35 times a second with the warp on, with it off and with either
afbd module (11.10.2026, HY300PRO-G-EU, 720p panel, 1080p60 source). With the source switched to 720p60 it moved 59.8
times, every gap one frame, still or moving: the firmware loses frames when the capture scales 1080p down to the 720p
panel, not the warp and not the content (TODO 2.56). The HY310's 1080p panel needs no scaling and gets 59.5. *Superseded
11.10.2026:* "Whether the capture leaves out only repeated frames there is still to be measured with a moving picture".

Where the CPU went besides the warp, and what changed: the kernel let schedutil change the clock every 462 µs, and
under the warp's 60 Hz load the `sugov:0` thread that carries out each change (a PWM regulator ramp, then the PLL)
cost as much as the warp itself; `/etc/tmpfiles.d/h713-cpufreq.conf` sets 20 ms (docs/hardware.md). And `h713-tv`
wrote one journal line per late warp frame; it now counts them (docs/tools/h713-tv.md). Together: all four cores
5.9 % busy with the warp on before, 2.9-3.1 % after.

## Corner names, verified

`tl`, `tr`, `bl`, `br` are the corners of the projected picture as the audience sees it. Verified on the
HY310 on 22.09.2026: `ctl keystone set tl x 150` and `tl y 150` moved the top left corner of the picture
inward (plan/keystone T21). The vendor's own slot names contradict each other; ours do not inherit them.
