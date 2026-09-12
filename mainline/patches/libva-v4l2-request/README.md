# libva-v4l2-request patches

The VA-API driver that lets **stock** mpv and ffmpeg decode on the H713's VE.
It is a translator, not a decoder: ffmpeg parses the bitstream and hands over
picture and slice parameters, and this shim converts them into V4L2 Request API
controls for cedrus. Nothing upstream of it is patched — that is the whole
point of choosing this route (see [../../docs/vaapi-scope.md](../../docs/vaapi-scope.md)).

## Base

| | |
|---|---|
| upstream | <https://github.com/bootlin/libva-v4l2-request> |
| branch | **PR #38**, `refs/pull/38/head` — *not* `master` |
| pinned base | `1c5f2cad21dff3b56d35355082867c24e4f191c6` ("Don't advertise broken profiles") |
| license | MIT |

`master` is a red herring: its last commit is 2019-05-17 and it uses the
pre-stabilization `V4L2_CID_MPEG_VIDEO_H264_*` controls, whose structs no
longer match the 6.18 uAPI. **PR #38 already did that port** — it uses all
eight `V4L2_CID_STATELESS_H264_*` controls, precisely the set cedrus registers,
and assumes slice-based decode, which is the only mode cedrus offers.

Getting the tree:

```
git clone https://github.com/bootlin/libva-v4l2-request
git -C libva-v4l2-request fetch origin refs/pull/38/head:pr38
git -C libva-v4l2-request checkout pr38
git -C libva-v4l2-request am ../patches/libva-v4l2-request/*.patch
```

Build it **on the board**, not on the host. The driver's entry-point symbol is
`__vaDriverInit_<major>_<minor>` derived from the *libva pkg-config version* at
build time, so a host build against libva 1.24 produces a `.so` that the
board's libva 1.22 loader will not call.

## The patches

| # | What | Why |
|---|------|-----|
| 0001 | `#include "utils.h"` in `h264.c` | `request_log()` is called but never declared; implicit declarations have been an error since GCC 14 |
| 0002 | Build H.264 only; advertise only what `RequestCreateConfig` accepts | see below |
| 0003 | Create the bitstream buffer with the surface, not with the context | the one that actually blocked decoding — see below |

Patch 0002 does two things that look separate and are not:

- **The bundled `include/hevc-ctrls.h` is deleted.** It is a 2019 snapshot of
  HEVC controls that have since been stabilized into `linux/v4l2-controls.h`,
  so every file including it redefines five structs the kernel headers already
  define — 5 errors across three files. `h265.c` cannot simply use the new
  definitions either: PR #38 ported H.264 and left HEVC on the old uAPI, using
  3 of the 8 controls cedrus registers. So `h265.c` drops out of the build and
  stays in the tree as the starting point for that port, which
  `docs/vaapi-scope.md` costs at ~400 lines with a reference-picture-set
  restructure.
- **`RequestQueryConfigProfiles` no longer advertises MPEG-2 or HEVC.**
  `RequestCreateConfig` already refuses both, so advertising them made `vainfo`
  report profiles that fail at `vaCreateConfig` — and `vainfo` is exactly the
  tool used to decide whether this driver works at all.

Patch 0003 is the one that mattered, and it is a good example of a failure that
points at the wrong half of the system. The symptom was

```
v4l2-request: Unable to enable stream: Invalid argument
[h264] Failed to create decode context: 1 (operation failed).
```

which reads as a codec problem. `strace` says otherwise:

```
VIDIOC_CREATE_BUFS {count=0, type=VIDEO_OUTPUT} = 0 ({count=0})
VIDIOC_STREAMON [V4L2_BUF_TYPE_VIDEO_OUTPUT] = -1 EINVAL
```

The shim sized the bitstream queue from the render targets handed to
`vaCreateContext`. ffmpeg allocates VA surfaces on demand and hands over none,
so the queue was created empty and `STREAMON` was correctly refused. The buffer
now belongs to the surface, which is where the OUTPUT format was already being
set for the same underlying reason.

## Status — validated on hardware 2026-08-16

`vainfo` loads the driver (`__vaDriverInit_1_22`) and advertises the five H.264
profiles with `VAEntrypointVLD`. All five vectors of the M1 ladder decode
**bit-exact** against the host-generated references, through stock ffmpeg with
no patches to it:

| vector | result |
|---|---|
| `v01-320x240-baseline` (8 frames) | bit-exact |
| `v02-1280x720-baseline` (60) | bit-exact |
| `v03-1280x720-main` (60) | bit-exact |
| `v04-1280x720-high` (60) | bit-exact |
| `v05-1920x1080-high` (60) | bit-exact |

The VE's interrupt count rose by exactly 60 across a 60-frame decode, so the
hardware did the work — decode-only cost **1.233 s wall / 0.637 s CPU** for
60 frames of 1080p, against 2.72 s of CPU for the software decoder.

One measurement worth carrying forward: adding `hwdownload` to copy those
frames back to system memory costs *more* than the decode does (1.8 s extra for
186 MB), because V4L2 MMAP buffers are uncached. That is a cost of
decode-to-file validation, not of playback — a display path that maps the
surface as a dma-buf never pays it.

Reproduce with [`tools/video/va-decode-test.sh`](../../tools/video/va-decode-test.sh),
which scores a software control first so a hardware mismatch cannot be confused
with a broken yardstick.
