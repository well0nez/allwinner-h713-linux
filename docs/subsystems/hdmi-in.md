# HDMI input: the V4L2 side

The HDMI port is a capture-only V4L2 device (`sun50i-h713-hdmirx`) driven by the MIPS
display firmware, not by a receiver the ARM cores talk to directly. It hands a source's picture to
whatever reads it - normally `h713-tv`, which puts it on the projector's plane (that path, and the
picture geometry it ends up with, is [display.md](display.md)'s subject). This page covers what the
device tells userspace, what you can adjust, and the one quirk worth knowing before you script against it.

## Bring-up

Opening the device is fast; the first probe after a cold start is not. It runs 22 sequenced remote
calls into the firmware - noise reduction, picture mode, HDCP key, port map, and so on - over the
`cpu_comm` link, then brings up EDID and hot-plug through the ARISC co-processor. Measured on the
09:02 boot: the whole sequence, including EDID, finished **17.65 s** after power-on (`doku/88`,
07.09.2026). The EDID the device advertises is fixed: HDMI 1.4 + HDMI 2.0 blocks concatenated into one
512-byte image, of which a source is served one 256-byte block. The firmware rewrites exactly two
bytes of it - the HDMI vendor block's physical-address byte and the extension checksum that follows
from it - so a read-back is not byte-identical to what was written, and `VIDIOC_S/G_EDID` treat the
image as four blocks, not one. Which of the two blocks a port gets is a per-port bitmask inside the
ARISC firmware and not a version number; this board serves the HDMI 1.4 block on purpose, because the
2.0 block advertises four 4K50/60 modes the display firmware's own mode table cannot lock and lowers
the TMDS ceiling while doing it ([arisc.md](arisc.md)).

## Signal, timings, source switch

`QUERY_DV_TIMINGS` reports the geometry the firmware has actually locked onto - read from its capture
descriptor register together with the flip pointers the video plane already tracks - not a compiled-in
guess; no lock gives `-ENOLINK`, and `ENUM_INPUT` flags `V4L2_IN_ST_NO_SIGNAL` accordingly.
`V4L2_EVENT_SOURCE_CHANGE` fires from the firmware's own signal and hot-plug callbacks, delivered over
`cpu_comm`. `VIDIOC_S_INPUT` issues the firmware's own source-select call.

The list of what the device can lock onto is the display firmware's own mode table, read out of
`database.TSE` at probe (the TFD module `THDMI_ModeList`, 152 records). A geometry that is in it and not
yet settled answers `-ENOLCK`, "the signal is unstable"; a geometry that is in none of the records
answers `-ERANGE` **with the measured timing filled in**, because the timing was found and it is outside
what this receiver can do. The two used to be one answer, and a 1600x900 source therefore read "change in
flight" for as long as it was plugged in. `h713-tv` stops retrying on the second and says so.

One quirk shapes how the picture behaves around a mode change: writing the video plane's descriptor
(once per boot, see `display.md`) silently stops the firmware's capture engine as a side effect. The
display driver publishes that event, and this driver answers on its own with a source switch away and
back - settling roughly half a second after the firmware's acknowledgement. That is why the console can
flash briefly right after a resolution change even though nothing asked for it; no userspace action is
needed to recover.

## Picture controls

Fourteen picture controls are exposed as ordinary V4L2 controls. Five are sliders 0..100 (brightness, contrast, saturation, hue, sharpness); four are four-step menus (temporal and spatial noise reduction, dynamic contrast, black extension); video range has three entries and picture mode fourteen; backlight level is a slider 0..100, dynamic backlight and low latency are two-entry menus. `h713-tv ctl list` prints each with its real range, which is the thing to script against. Setting one issues the matching
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
| Backlight level, dynamic backlight | vendor switches | the bring-up sequence has sent both since this driver existed (100 and "manual"); on the HY310 the same dimmer is also a Linux `pwm-backlight` on PWM2/PB4 |
| Low latency | vendor switch | the routine and its id are the vendor's; the vendor's own userspace never calls it, so the firmware has never been asked to leave the state it boots in |

Video range defaults to *auto*, and that is right rather than merely convenient: the firmware resolves
*auto* out of the AVI InfoFrame's quantisation field with the HDMI default rule, so *auto* is the source's
own answer.

Where these numbers come from - vendor preset files, gamma curves, how `h713-tv` persists a change - is
[pq.md](pq.md); this is only the interface they arrive through.

## What the record carries, and what we report from it

Every half second of a locked signal the firmware keeps a 44 byte record in shared memory: the matched
signal id, the frame rate to 1/100 Hz, the scan type, the colour format and colour space, the active size,
an HDR scheme, a full-range flag and a DVI flag. Four of those decide what `G_FMT` and `QUERY_DV_TIMINGS`
report, and each is the firmware's own reading of the source rather than anything this driver measures:

| Record field | What it is | What we report |
|---|---|---|
| `color_space` | the firmware's verdict on the AVI InfoFrame's colorimetry (C and EC), with its own fallback where the source sends none | `colorspace` and `ycbcr_enc`: BT.601 → `SMPTE170M`, BT.709 → `REC709`, BT.2020 → `BT2020` (with constant luminance where the record says so) |
| `b_full_range` | the HDMI default rule: YCbCr limited unless the source says otherwise, RGB full only on a PC timing | `quantization` |
| `b_interlace` | **not** a register and not an AVI bit: a set lookup on the matched signal id inside `database.TSE` | `bt.interlaced` |
| `b_dvi_mode` | the firmware's own "this is not HDMI video" verdict - the port's mode, fourteen XGA timings, and the vendor's PC-mode config | `V4L2_DV_FL_IS_CE_VIDEO` |

Where the source sends no colorimetry at all the firmware has already decided, and predictably: BT.2020 for
a source that really sends HDR signalling, BT.709 on a PC timing, BT.601 for exactly eleven standard-
definition signal ids, BT.709 for everything else. So on the six verified modes the reported colour is what
it always was; SD sources and sources that do send colorimetry are what this corrects.

`hdr_mode` is printed in the debugfs status file and used for nothing, which is deliberate. V4L2 has no HDR
metadata for a capture device, and an HDR transfer function in the format would be wrong in the other
direction: the firmware tone maps an HDR source onto the panel *before* the capture sees it, so what lands
in the ring is already mapped. Two of its values mislead and the status file says so: `Sdr` can also be
plain HDR10 (the firmware has no entry for that case and mislabels it towards the ARM, while tone mapping
it correctly all the same), and `DbVision` here means the Dolby Vision low-latency VSIF, because the other
route to that value is never taken on this firmware.

Nothing else in the AVI belongs here. Of the ten fields the firmware parses it reads four; the VIC, the
picture aspect, the active-format bits, the content type and the bar info are stored and never looked at,
and pixel repetition acts on the capture *before* INCAP, so reporting it would count it twice.

## The capture ring, and how it reaches the plane

The firmware writes each captured frame as NV16 into one of three fixed slot pairs inside its own
reserved memory - it cannot be told to allocate elsewhere. There is no ARM-visible "slot ready"
interrupt for it; the completion signal that does exist on this SoC is local to the MIPS's own interrupt
controller and never reaches Linux (`doku/84`, static RE, K1-K3). The driver instead treats the video
plane's own vsync as its clock: on every frame it reads the same flip-pointer pair the plane already
reads, delivered by the display driver over a shared notifier instead of mapping the register a second
time. Buffer *i* **is** slot *i* - `VIDIOC_REQBUFS` always hands back exactly three buffers, backed by
custom `vb2_mem_ops` and mapped write-combined, and there is no copy anywhere in the path. `VIDIOC_EXPBUF`
does not exist yet; nothing needs the ring as a dma-buf today.

## Verified

Six modes are verified on hardware - the list is in [STATUS.md](../../STATUS.md) - each at 60 Hz and
colour-correct, across arbitrarily many source switches, HDMI unplug/replug, and a cold start with no
operator. They come out BT.709 because that is what the sources send and what the firmware reads; a
standard-definition source now comes out `SMPTE170M`, which is the correction, not a regression.
1280×1024 is pillarboxed by the `aspect` property described in [display.md](display.md). A source geometry
the firmware itself does not lock onto is its own answer since the mode table is read (`-ERANGE`, above),
not the same one as no signal at all.

## Limits

**HDMI here is an input, never an output** - the projector has no HDMI-out; the imager is the only
display. Unencrypted and HDCP 2.2 sources work: the 2.2 key is read from *your* device's own extraction
at boot (`h713-hdcp-key.service`) and handed to the firmware during the probe; if it is missing, that one
step is skipped and unencrypted sources are unaffected. **HDCP 1.4 is not supported** - a protected 1.4
source will not decrypt (`doku/112`). Power and clock setup for the capture engine itself (TVFE/TVCAP,
fabric routing) happens once, in U-Boot and the firmware, before Linux starts; this driver assumes it and
does not manage it, which is also why the mainline `tvtop` driver is not needed here (`doku/71`).

Details: doku/88-v4l2-hdmirx.md, doku/84-re-capture-ring.md, doku/86-video-plane-nv16.md,
doku/96-anzeigekette.md, doku/71-tvtop-noetig.md
