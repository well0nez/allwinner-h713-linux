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
| `h713-tv` | `/dev/dri/card1`, the DRM master, the panel | allocates the three target buffers, and commits them on the **primary** plane with `IN_FENCE_FD` |
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
| `test grid\|border\|off` | draw a pattern instead of the capture, to aim a corner with no source plugged in |

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
warp  = off                 # the state to come up in
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
second - which is also what it does when `h713-tv` is restarted under it.

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
and `h713-tv ctl zoom` is refused with a pointer to `h713-warp ctl zoom`. The added latency is zero frames
when the render finishes inside a vsync interval and one frame when it does not; a frame that arrives while
the previous commit is still in flight is dropped rather than queued. The warp costs about 1.0 GB/s of memory
bandwidth (read 4.15 MB of NV16, write 8.29 MB of XRGB, scanout reads 8.29 MB instead of 4.15 MB per frame)
and 24.9 MB of CMA for the three targets. The optional edge-blend pass of the vendor is not implemented. Which
physical corner the vendor's slot 0 is has been derived from the framebuffer's orientation and is confirmed on
the wall with one nudge and one photo; if top and bottom ever come out exchanged, it is two lines in
`matrix.c`.

Details: umbau/plan/keystone/PLAN.md (stage S5), umbau/re-apps/AP2d/design-h713-warp.txt (modules M1-M11),
umbau/re-apps/AP2f/REPORT.txt (the matrix and its z trap), umbau/re-apps/AP2/REPORT.txt (the vendor's units
and clamp), docs/tools/h713-tv.md.
