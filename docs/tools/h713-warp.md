# h713-warp - the keystone, on the GPU

`h713-warp` bends the HDMI picture into a quadrilateral so that a projector standing off-axis still throws a
rectangle on the wall. It is the Linux replacement for the vendor's keystone, and it is the same warp: a
projective homography built from eight per-mille corner insets, ported function by function from
`getKeyStoneMatrix` in the stock `system_a_libkeystone.so` and tested against that reference.

Nothing about the ordinary picture path changes. With all eight values at 0 - the state a fresh image comes up
in - the daemon does not open the render node at all (after the format query at its start), and `h713-tv` shows
the capture ring exactly as it does without this service. A Wayland client is the second source next to the ring:
see "A Wayland client" below.

## Who does what

| | owns | does |
|---|---|---|
| `h713-warp` | `/dev/dri/renderD128` (panfrost), the capture buffers, the shader, the matrix | reads the HDMI capture as dma-bufs, draws one warped frame per capture frame, hands it over with a fence |
| `h713-tv` | `/dev/dri/card1`, the DRM master, the panel | allocates the three NV12 target buffers, and commits them on the **video** plane with `IN_FENCE_FD` and `hdmi-ring` 0 |
| a Wayland client (cage) | `renderD128` for its own drawing, evdev through libinput | connects to `/run/h713-warp/wayland`, hands its pictures over as dma-bufs; never opens a card node |
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
| `edge [N]` | the soft border of the warped picture in panel pixels, 0..64: 0 = a hard edge, 4 = the vendor's (the default). The outer half of that width keeps 20/255 of the picture, then a linear ramp over one width reaches the picture - the stock's `draw_edge` (libkeystone), drawn as the stock draws it: a ring of ten vertices along the quad's edge, 1.5 mask texels wide, blended over each plane after the picture (no extra texture; since 11.10.2026 evening - folded into the picture shaders it cost the GPU 4 ms of its 6 a frame, see below); takes effect with the next frame and is saved as `edge =` |
| `mode [front\|rear\|ceiling\|rear-ceiling]` | the projection mode, the vendor's "Installation mode": `rear` mirrors the picture left-right for a screen lit from behind, `ceiling` turns it over, `rear-ceiling` flips it top-bottom only. Saved as `mode =` in the file. The flip is one sign change in the matrix after the keystone, so the corner names stay the wall's in every mode and the mask's labels land where they belong. A change of mode re-sorts the eight values the vendor's way (`setKeystoneNormalXY`): the correction stays with the housing, the quad on the panel stays where it was and the picture turns inside it - `ctl mode` prints the new values (06.10.2026); any mode but `front` keeps the GPU running even with all eight corners 0, and it mirrors nothing while the warp is off (the plain ring path is the firmware's) |
| `test grid\|border\|mask [CORNER]\|off` | draw a pattern instead of the capture, to aim a corner with no source plugged in; `mask` is the calibration picture of the manual keystone with the named corner marked and every corner's value and maximum printed |
| `dump PATH` | the last drawn frame's luma plane as a binary PGM - eyes for a test without a wall |
| `hold on\|off` | draw a slot one vsync late. **Off** is the default since 11.10.2026 (kernel 0255): the slot handed on at a vsync is the one the capture finished at the last frame boundary, whole for two more frame periods, so it is drawn at once - one frame of latency less, and `on` would now read it up to 36 ms after that boundary, when the capture is back writing it. `on` was the answer of 23.09.2026 to the firmware's pointers, which handed a slot on before it was written to the end; it stays as the control for a kernel from before 0255 |
| `check [FRAMES]` | the self-check, no eyes needed: every third slot drawn a second time 4 ms later into a scratch buffer and compared in 32 rows; "N frames, 0 with differing rows" on the status line is the pass, one journal line per differing frame. While it runs the readback stalls the loop and frames are dropped (`busy`); it ends by itself. 11.10.2026, `hold off`, a moving 1080p60 source: 300 frames, 0 differing rows |
| `trace [N] [gpu]` | log the next N frames with what they cost: this thread's CPU microseconds per step (dequeue, the two passes, the fence, h713-tv's answer) and, with `gpu`, the GPU's time from the submit to the out-fence - the only honest GPU clock here, Panfrost answers `GL_EXT_disjoint_timer_query` from the CPU clock |
| `trace [N]` | log the next N dequeues with their timestamps, gaps between pumps and slow phases (draw, the peer's answer) |

`CORNER` is `tl tr bl br` **as the picture stands on the wall**, `AXIS` is `x` or `y`. Every change is clamped
and saved at once. The clamp is the vendor's: the x of a corner is limited by the corner at the other end of
its row and the y by the one at the other end of its column, so the picture can never be pulled past its own
width or height. The value that gives way is the one being set, never the one already there.

## A Wayland client

The daemon is also a minimal Wayland server on `/run/h713-warp/wayland` (0660; `-w PATH` for another place),
so that Kodi under cage reaches the wall through the warp - with the keystone, the overlays and h713-tv as the one
master (measured on the HY310 on 15.10.2026, `doku/211` §10).

- **Protocols:** `wl_compositor`, `wl_shm`, `xdg_wm_base` (one fullscreen toplevel in the panel's size, a second one
  is asked to close at once - if it stays, it takes the panel over when the first one goes; popups are dismissed), `zwp_linux_dmabuf_v1` v4 with a format table out of EGL (every RGB
  format and modifier the render node imports, Kodi's AR30 + AFBC `0x0800000000000062` among them - without it cage
  copies every picture), `wl_output`, `wp_presentation` (CLOCK_MONOTONIC). No `wl_seat`: cage reads the remote
  through libinput itself.
- **What h713-tv shows** is `h713-tv ctl source hdmi|client|auto` (`source =` in `tv.conf` at the start, default
  `hdmi`; the image of the profile `desktop` sets `auto`, because h713-tv does not keep a source across its own
  restart). The warp claims the panel with `warp claim client` once a toplevel has its first picture; the claim
  needs no signal, and the capture stays closed. A change of `source` gives a standing claim back only when the
  new policy forbids it (a ring claim under `client`, a client claim under `hdmi`), and the warp claims again at
  once - the answer to a claim names the policy (`... source auto`). A claim the new policy allows stands, and the
  `ok` of the next frame names the policy (`ok source auto`): `hdmi` <-> `auto` no longer takes the ring off the
  panel. A client that waits behind a ring claim does not rely on that frame - a stalled ring sends none - the warp
  asks h713-tv's `source` when the client comes and once a second while it waits. Under `auto` a client goes before the ring. Under `client` without a client the warp asks `source` alone
  once a second instead of starting the capture for a ring claim that would be refused (M4, 15.10.2026).
- **A buffer's life:** pending when committed (a newer commit releases an untaken one at once), taken when its
  dma-buf is readable and the previous frame is on the panel (h713-tv's flip fence, sent with the `ok`), the frame
  callbacks done right then, released when the render fence of the frame that read it signals, presented with the
  flip fence's timestamp. At most one client frame per vsync; `--client-rate half` takes every second vsync.
- **Colour:** BT.709 limited range computed inside the two keystone passes from the client's RGB; a picture smaller
  than the panel sits in the middle (letterbox), never scaled, and gets the configure once more - cage misses the
  first one and would stay at 1280x720 (measured 15.10.2026). With `warp = off` the client is shown without
  keystone. The client is drawn through the GPU even at the identity: the video plane takes NV12 only.
- **Limits:** four connections (a fifth gets an error and is closed), eight surfaces and eight imported dma-bufs per client, a buffer
  larger than the panel is refused, a buffer before the first configure is a protocol error; a client that goes
  away keeps the panel for two seconds (a cage restart), then the warp gives it back. A dma-buf shorter than the
  layout the GPU reads for its modifier fails before the import - LINEAR offset + pitch x height, u-interleaved in
  lines of 16, AFBC a 16-byte header per superblock plus the whole body, as mesa's panfrost lays it out; M4 had a
  20-KB buffer described as 1920x1080 AFBC fault the GPU. A `wl_shm` line shorter than 4 x width is a protocol
  error (libwayland checks only stride >= width), and a `wl_shm` picture goes up in one call (M4, 15.10.2026).
- **Status:** `ctl status` has two more lines, `wayland` (clients, toplevel, formats) and `client` (taken,
  presented, discarded, busy, released, imports).

Kodi sees 0 Hz under cage (wlroots' nested output has no rate) and picks the presentation protocol for its video
sync: leave Kodi's "Sync playback to display" off (the default) - with it on, 1080p60 played at 18 fps and Kodi hung
on stopping the video (measured 15.10.2026).

Kodi's unit (`h713-kodi.service`, profile `desktop`) sets `WAYLAND_DISPLAY=/run/h713-warp/wayland` and
`WLR_BACKENDS=wayland,libinput`, binds itself to `h713-warp.service`, and sets `h713-tv ctl source auto` at its
start (without a running h713-tv there is nothing to set: it comes up on `auto`); there is no way back to run at
its end - however Kodi ends (Quit, a crash, a SIGKILL of the whole unit), the
warp gives the panel back two seconds after cage is gone and the ring is there again (M4, 15.10.2026: a SIGKILL of the
unit's cgroup skipped the old `ExecStopPost=... source hdmi` and left the console). Measured: the host test (`make
test`, a client against the server with the GPU stubbed); on the device see `doku/211` §10.

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
| the source changes resolution | on every `SOURCE_CHANGE` the queue is stopped, the driver asked (`QUERY_DV_TIMINGS`, then `G_FMT` - a streaming queue keeps its format, so `G_FMT` alone could only repeat the old ring, which it did until 12.10.2026) and the six capture images are rebuilt; the driver also reports a ring that moved without a firmware callback since kernel 0260 (`doku/206`) |

## Limits

**Modes whose ring the GPU cannot import stay without keystone - by decision (12.10.2026).** The display
firmware lays the capture ring out with a line pitch of the ring's width rounded up to 16 bytes, and sets it
again at every rebuild of its capture chain (`VIncap_ConfigDownScaler`; overwriting the INCAP rowbyte from our
side changes nothing, measured 12.10.2026 in `arbeit/wurzeln-20261012`); panfrost imports a linear dma-buf
as a 2D texture only with a pitch that is a multiple of 64. Rings whose width is not a multiple of 64 are
therefore refused at the import: 800x600 (pitch 800), 720x576 and 720x480 (720), 1280x1024 (912, the
firmware scales it to 900 wide). In those modes the warp stays in bypass, `ctl status` says so (`R8 + GR88
import of a capture slot: egl 0x3003`), and `h713-tv` shows the plain picture - nothing is cropped or
guessed. The one way around it on our side would be importing the slot as a flat buffer and addressing it
in the shader (a second render path, about a millisecond more GPU per frame); it was not built, because
nobody runs a projector at these modes - a source at 1080p, 720p, 1366x768, 1360x768, 1024x768, 1280x800,
1440x900, 1600x1200 or 640x480 is warped. If the need comes, TODO 2.4f holds the design.

The warp and the video plane are **mutually exclusive** - while the warp is on, the picture comes from the GPU
and `h713-tv ctl zoom` is refused with a pointer to `h713-warp ctl zoom`. The warp adds no frame of latency
since 11.10.2026 (kernel 0255, `hold off`): the slot handed on at a vsync is finished and is drawn at once;
the picture then reaches the panel at the next vsync, like the plane's. A frame that arrives while the
previous commit is still in flight is dropped rather than queued. `ctl check` proves the timing on any
device. *Superseded 11.10.2026:* "the added latency is one frame (16.8 ms): a slot is drawn one vsync after
it was handed on, because the firmware publishes a slot anywhere between the start and the end of its write
... a held slot older than 28 ms is given back undrawn" - that was the firmware's pointer; `hold on` keeps it.

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
darkening ring the stock draws as a blended alpha quad over its warped frame - luma towards Y 16, chroma
towards 128 by the same factor, so the band meets the border without a step and leaves no colour fringe.
Since 11.10.2026 (evening) it is drawn as the stock draws it, blended, but only where it changes anything:
a ring of ten vertices along the quad's edge, 1.5 mask texels wide, one triangle strip per plane after the
picture. Folded into the picture shaders (27.09.-11.10.) the few arithmetic instructions after the texture
fetch cost the Mali-G31 4 ms of its 6 ms a frame - this GPU hides no texture latency behind arithmetic
(`doku/201`). The band follows the quad (the vendor's
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

`h713-warp ctl trace 30 gpu` says it for any device. CPU time of the warp's thread per frame at a fixed 1296 MHz:
dequeue 20 µs, **drawing 470-600 µs** (luma pass 220-290, chroma pass 230-270, the border's two ring draws about 60
of that), the fence 180-200 µs (the `glFlush` that submits the GPU jobs, and the sync file), the round trip to
`h713-tv` 60 µs - about 0.8 ms; at 480 MHz 2.7 times that. The drawing is two passes (luma at full size, chroma at
half size), and each pass costs Mesa/Panfrost about 125 µs to set up a GPU batch whatever the first call is: without
the `glClear` the draw call takes that time instead. Caching the uniform locations and the matrix, a VBO for the
quad and one texture bind a frame took about 30 µs off (11.10. evening) - the time is in Mesa and the kernel, not
in this code; compiler flags make no difference (`-O3 -mcpu=cortex-a53 -flto` against `-O2`, A/B/A/B at a fixed
clock: the same CPU per frame). **The GPU's time per frame**, submit to out-fence: 6.05 ms at 696 MHz until
11.10.2026 evening, **1.78 ms** since (1.68 with the border off); it scales with the clock (4.3 ms at 288 MHz), so the
GPU governor now parks at 288-432 MHz with the warp on, where it sat at 600-696 before. What cost the 4.3 ms was
not the border's arithmetic as such but *any* arithmetic after the texture fetch in the picture shaders: a bare
fetch 1.65 ms, one constant `mix` after it 2.2 ms, the border's dozen operations 6.0 ms - the one-core Mali-G31
hides no texture latency behind ALU work. So the picture passes are a bare fetch and the border is its own small
blended draw. A compute dispatch instead of the two passes was tried on the device (`bau/gles31-probe.c`): it works
(GLES 3.1, imageStore into the imported buffer), costs Mesa 357 µs of CPU against 130 for a fragment pass and the
GPU 2.1 ms against 1.6 for a copy - no. One pass per frame was tried and measured (branch `versuch/warp-einpass`): the NV12 buffer
as one R8 image of width × 1.5 height, the chroma rows a fragment per byte with the pair centre through the inverse
map (host test T1e: equal to the two passes within 2 LSB). It saved 14 % of the warp's CPU, but the chroma then had
twice the fragments, the GPU ran at its top clock 66-87 % of the time instead of 21-25 %, and about one frame a second
came back busy and was dropped - the two passes stay. *Superseded 11.10.2026:* "the next real step would be one pass
per frame ... not done yet".

The warp draws every slot the capture hands on: it wakes 0.1 ms after the slot's timestamp and is done 1.5 ms later.
Since 11.10.2026 (evening, kernel patch 0255, `doku/200`) the slot it is handed comes from the capture's own write
index and not from the firmware's flip pointers: on the HY300PRO-G-EU with a moving 1080p60 source the warp draws
59.7 fps with none dropped, where the pointers gave it 30-58. The paragraph below is the measurement that led there.
How many slots there are *was* decided before it, in the firmware's publisher: read straight from the flip pointer pair
(AFBD +0x320 through `/dev/mem`), the pair moved 30-35 times a second with the warp on, with it off and with either
afbd module (11.10.2026, HY300PRO-G-EU, 720p panel, 1080p60 source). With the source switched to 720p60 it moved 59.8
times, every gap one frame, still or moving. The capture itself writes every frame (`INCAP 0x06940104` counts source frames
and lines): what fails is the hand-over to the panel, which repeats one frame and skips the next, and only at 60 Hz with
downscaling - 1080p30 and 4K30 scaled to 720 show every frame, 1080p60 shows 1-4 skips a second right after a mode change
and up to 17 after hours. Not the MIPS clock, the panel coupling, the VidDec frame rate, TNR or the bus settings; the cause
is open (`doku/197`, TODO 2.57). The HY310's 1080p panel needs no scaling and gets 59.5. *Superseded 11.10.2026 (midday):*
"the firmware loses frames when the capture scales 1080p down to the 720p panel"; *(early):* "Whether the capture leaves out
only repeated frames there is still to be measured with a moving picture".

Where the CPU went besides the warp, and what changed: the kernel let schedutil change the clock every 462 µs, and
under the warp's 60 Hz load the `sugov:0` thread that carries out each change (a PWM regulator ramp, then the PLL)
cost as much as the warp itself; `/etc/tmpfiles.d/h713-cpufreq.conf` sets 20 ms (docs/hardware.md). And `h713-tv`
wrote one journal line per late warp frame; it now counts them (docs/tools/h713-tv.md). Together: all four cores
5.9 % busy with the warp on before, 2.9-3.1 % after.

## Corner names, verified

`tl`, `tr`, `bl`, `br` are the corners of the projected picture as the audience sees it. Verified on the
HY310 on 22.09.2026: `ctl keystone set tl x 150` and `tl y 150` moved the top left corner of the picture
inward (plan/keystone T21). The vendor's own slot names contradict each other; ours do not inherit them.
