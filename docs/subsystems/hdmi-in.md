# HDMI input: the V4L2 side

The HDMI port is a capture-only V4L2 device (`sun50i-h713-hdmirx`) driven by the MIPS
display firmware, not by a receiver the ARM cores talk to directly. It hands a source's picture to
whatever reads it — normally `h713-tv`, which puts it on the projector's plane (that path, and the
picture geometry it ends up with, is [display.md](display.md)'s subject). This page covers what the
device tells userspace, what you can adjust, and the one quirk worth knowing before you script against it.

## Bring-up

Opening the device is fast; the first probe after a cold start is not. It runs 22 sequenced remote
calls into the firmware — noise reduction, picture mode, HDCP key, port map, and so on — over the
`cpu_comm` link, then brings up EDID and hot-plug through the ARISC co-processor. Measured on the
09:02 boot: the whole sequence, including EDID, finished **17.65 s** after power-on (`doku/88`,
07.09.2026). The EDID the device advertises is fixed: HDMI 1.4 + HDMI 2.0 blocks concatenated into one
512-byte image, patched by the firmware itself (physical address, checksum) — a read-back is therefore
not byte-identical to what was written, and `VIDIOC_S/G_EDID` treat it as four blocks, not one.

## Signal, timings, source switch

`QUERY_DV_TIMINGS` reports the geometry the firmware has actually locked onto — read from its capture
descriptor register together with the flip pointers the video plane already tracks — not a compiled-in
guess; no lock gives `-ENOLINK`, and `ENUM_INPUT` flags `V4L2_IN_ST_NO_SIGNAL` accordingly.
`V4L2_EVENT_SOURCE_CHANGE` fires from the firmware's own signal and hot-plug callbacks, delivered over
`cpu_comm`. `VIDIOC_S_INPUT` issues the firmware's own source-select call.

One quirk shapes how the picture behaves around a mode change: writing the video plane's descriptor
(once per boot, see `display.md`) silently stops the firmware's capture engine as a side effect. The
display driver publishes that event, and this driver answers on its own with a source switch away and
back — settling roughly half a second after the firmware's acknowledgement. That is why the console can
flash briefly right after a resolution change even though nothing asked for it; no userspace action is
needed to recover.

## Picture controls

Eleven picture controls are exposed as ordinary V4L2 controls. Five are sliders 0..100 (brightness, contrast, saturation, hue, sharpness); four are four-step menus (temporal and spatial noise reduction, dynamic contrast, black extension); video range has three entries and picture mode fourteen. `h713-tv ctl list` prints each with its real range, which is the thing to script against. Setting one issues the matching
remote call to the firmware; there is no way to read any of them back from the hardware, so whatever last
set a control is the only record of its value.

| Control | Interface | Confirmed |
|---|---|---|
| Brightness | `V4L2_CID_BRIGHTNESS` | 07.09.2026, against dark material (a near-white test image hid the effect at first) |
| Contrast | `V4L2_CID_CONTRAST` | 07.09.2026, 12.16 % of the wall changed at full swing |
| Saturation | `V4L2_CID_SATURATION` | 07.09.2026; also scales a second, downstream chroma-gain register |
| Hue | `V4L2_CID_HUE` | 11.09.2026, magenta at 0, green at 100 |
| Sharpness | `V4L2_CID_SHARPNESS` | 11.09.2026 |
| Noise reduction, dynamic contrast, black-level extension | vendor switches, no V4L2 standard CID | write no readable register; effect confirmed only in the firmware's own log |

Where these numbers come from — vendor preset files, gamma curves, how `h713-tv` persists a change — is
[pq.md](pq.md); this is only the interface they arrive through.

## The capture ring, and how it reaches the plane

The firmware writes each captured frame as NV16 into one of three fixed slot pairs inside its own
reserved memory — it cannot be told to allocate elsewhere. There is no ARM-visible "slot ready"
interrupt for it; the completion signal that does exist on this SoC is local to the MIPS's own interrupt
controller and never reaches Linux (`doku/84`, static RE, K1–K3). The driver instead treats the video
plane's own vsync as its clock: on every frame it reads the same flip-pointer pair the plane already
reads, delivered by the display driver over a shared notifier instead of mapping the register a second
time. Buffer *i* **is** slot *i* — `VIDIOC_REQBUFS` always hands back exactly three buffers, backed by
custom `vb2_mem_ops` and mapped write-combined, and there is no copy anywhere in the path. `VIDIOC_EXPBUF`
does not exist yet; nothing needs the ring as a dma-buf today.

## Verified

Six modes are verified on hardware — the list is in [STATUS.md](../../STATUS.md) — each at 60 Hz and
colour-correct (BT.709), across arbitrarily many source switches, HDMI unplug/replug, and a cold start
with no operator. 1280×1024 is pillarboxed by the `aspect` property described in [display.md](display.md).
A source geometry the firmware itself does not lock onto is reported the same way as no signal at all,
not as a distinct error.

## Limits

**HDMI here is an input, never an output** — the projector has no HDMI-out; the imager is the only
display. Unencrypted and HDCP 2.2 sources work: the 2.2 key is read from *your* device's own extraction
at boot (`h713-hdcp-key.service`) and handed to the firmware during the probe; if it is missing, that one
step is skipped and unencrypted sources are unaffected. **HDCP 1.4 is not supported** — a protected 1.4
source will not decrypt (`doku/112`). Power and clock setup for the capture engine itself (TVFE/TVCAP,
fabric routing) happens once, in U-Boot and the firmware, before Linux starts; this driver assumes it and
does not manage it, which is also why the mainline `tvtop` driver is not needed here (`doku/71`).

Details: doku/88-v4l2-hdmirx.md, doku/84-re-capture-ring.md, doku/86-video-plane-nv16.md,
doku/96-anzeigekette.md, doku/71-tvtop-noetig.md
