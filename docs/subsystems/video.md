# Video: hardware decode, IOMMU, and the GPU path to the panel

The Video Engine ("cedrus" in mainline) decodes H.264 and HEVC in hardware; an IOMMU gives the codec its own
address space instead of raw physical memory; and the Mali-G31 GPU (Panfrost) can take the decoded frame
straight onto the display plane without the CPU ever touching a pixel. Together they are the difference
between playing a 1080p file and burning every core on colour-space conversion.

**The decode and IOMMU half of this file comes from cstenger's `h713-display-video-path` branch and is proven
only there.** Those measurements predate this repository's current boot chain (layout v3, 10.09.2026, and the
release kernel series finalised 12.09.2026) and have not been repeated since, so treat hardware video decode
and the IOMMU as **unverified in this image** - this matches STATUS.md, not just this page.

**The GPU is out of that group since 22.09.2026.** Panfrost was brought up, measured and put to work in this
image that night, and the section *The GPU, verified in this image* below says with which numbers. It is in the
source, not in a release.

## The pieces

| Block | Role |
|---|---|
| VE / cedrus | Hardware H.264 and HEVC decode via the mainline stateless `v4l2-mem2mem` API |
| IOMMU (`sun50i-iommu`) | Own address space for the video codec's two DMA masters only; every other master bypasses it, including the display plane (doku/76) |
| Panfrost (Mali-G31) | Imports the decoder's output as a `dma-buf` and converts NV12 to RGB - and, since 22.09.2026, the HDMI capture for the keystone warp |
| `misc/decd` | Kernel-side frame submission and fence handling between cedrus and userspace |
| DRM NV12 overlay (`0078`) | A plane that accepts the decoder's native NV12 buffer directly, so a fullscreen video does not need the GPU at all |

## Why the CPU can't do this

Decoding alone runs at 33 fps for 1080p on the A53 cores. Add a software NV12→BGRx conversion and it drops
to 3 fps: **97% of the time goes into colour-space conversion, not decoding** (doku/62, measured against a
`fakesink`/`fbdevsink` GStreamer pipeline). That is why the pipeline hands the decoded buffer to the GPU or
straight to the NV12 overlay instead of converting on the CPU - the conversion, not the decode, is what a
software path cannot afford.

## What was measured, and when

doku/62 (01.09.2026) found H.264 bit-exact through 1920×1080 and HEVC bit-exact at two sizes, checked
against an independently built host reference. With the GPU doing the colour conversion, zero-copy playback
reached **59.41 fps at 1920×1080** across 2,411 frames with zero commit timeouts - cstenger's own reported
figure was 59.71 fps, but at 720p. doku/64, the same night, traced a frame sitting in the decoder's own DRAM
through AFBD's planar channel (channel 0, the one the NV12 overlay would drive) onto the panel, closing
cstenger's open question about what makes a channel "serviced" rather than merely "configured". Both results
were real, on this board - but they describe a development state, not a boot chain that exists today, and
open questions from doku/64 §8 (which register supplies channel 0's live buffer address) were never closed
into a driver.

## The GPU, verified in this image (22.09.2026)

Before that night Panfrost had never rendered anything in an image of ours - the module probed on a second
board and that was all. It renders now, on the HY310, with our own mesa beside it (25.0.7, the panfrost driver
only, no LLVM, 15 MiB under `/usr/local`; `rootfs/mesa/`), and the keystone warp is built on top of it
([h713-warp](../tools/h713-warp.md)). Every number here is a device reading out of
`umbau/test-20260915/keystone-20260922.md`.

| | |
|---|---|
| What it reports | Mali-G31 (Panfrost), OpenGL ES 3.1 Mesa 25.0.7 over EGL 1.5, with `EGL_EXT_image_dma_buf_import`, `EGL_KHR_surfaceless_context`, `EGL_ANDROID_native_fence_sync` and `GL_OES_EGL_image` all present |
| Correctness | `h713-gpu-probe render 3000`: 3,000 textured 1080p frames, every hundredth read back and CRC-checked against a CPU rule - **0 mismatches** - at 236 fps, GPU zone 58 C |
| Ten minutes of load | 16,089 frames at 26.8 fps (26.6 to 27.1), 0 CRC mismatches, 201 devfreq transitions with 588 s of them at 696 MHz, at most 58.4 C in the GPU zone and 54.6 C in the CPU's, `dmesg` clean, and the GPU back at 288 MHz and runtime-suspended afterwards |
| Live, through the display | 3,600 capture frames onto the primary plane in 60 s: 0 `DQBUF` timeouts, 0 dropped flips, 1 late frame, 59.4 fps, 62 C at 696 MHz ([display.md](display.md)) |

**The operating points are new** (kernel `0024e`). Our device tree gave the GPU no `operating-points-v2`, so
`panfrost_devfreq_init` returned `-ENODEV`: no devfreq, no cooling device, and the GPU at the PLL's boot rate of
**864 MHz**, fixed - 23 per cent above the stock table's ceiling of 700 MHz, which the vendor drives with DVFS
off. `0024e` adds the four points PLL-GPU reaches with M = 1, **288, 432, 600 and 696 MHz**, at the fixed 0.96 V
rail, with a passive trip at 85 C and a critical one at 105 C on `gpu-thermal` and the GPU as its own cooling
device. What that costs is measured too: the same shader runs 33.3 fps at 864 MHz and 26.8 fps at 696.

**What was switched off around it.** `CONFIG_DRM_LIMA` bound nothing - Lima is for Utgard (Mali-400/450) and
this is a Bifrost G31 - and is gone. `CONFIG_SUN50I_IOMMU` was `y` while the tree's own comment said not to
enable it: the node is disabled, no node carries an `iommus` property, and Panfrost maps its buffers through the
Mali MMU in any case, so the symbol was dead and is off now. `CONFIG_DEVFREQ_THERMAL` came in, because
`panfrost.ko` needs it at build time for the cooling device. On the device afterwards: no `lima` driver, an
empty `/sys/class/iommu`, `panfrost` probed, the four frequencies listed with `simple_ondemand` - read, not
assumed.

**The three dma-buf patches.** `0053` (imported buffers are not mapped cacheable) is what makes a
write-combining CMA buffer safe between the GPU and the scanout engine, and it stays. `0036` (the `misc`
scanout exporter) and the exporter half of `0049` are **not** on this path - `h713-tv` allocates its three
targets as ordinary dumb buffers and exports them with PRIME - but they are still in the series and still
built; they are the first candidates to retire when the warp ships.

## Patches (`mainline/patches/kernel/series`, section 3 - 17 patches, byte-identical to the branch)

| Patch(es) | What it does |
|---|---|
| `0051` | Rate-limits IOMMU fault reporting instead of flooding the log |
| `0053`, `0079` | Panfrost/DRM: don't map or vmap imported buffers cacheable - required for zero-copy import |
| `0055` | Drops the 1416 MHz CPU OPP: it corrupts memory under load |
| `0059` | cedrus: claim the IRQ before disarming the watchdog |
| `0063` | AFBD: report a well-formed size range to userspace |
| `0064` | Puts the kernel console on the panel too |
| `0067`, `0071` - `0073` | `misc/decd`: match the stock frame-submit ABI; fix a release-fence lifetime bug; refuse non-contiguous `dma-buf` imports; declare the single-mapping DMA constraint |
| `0078` | Adds the fullscreen NV12 overlay plane |
| `0078a` | Our own addendum: the AFBD probe no longer asserts a 1280×720 default |

Not carried over: cstenger's `0080` attaches the video plane to the IOMMU. Our display node deliberately has
no `iommus` property and keeps reading the capture ring physically (doku/76, doku/78) - taking `0080` would
have reopened that.

## Limits, honestly

- **No AV1.** The H713 has AV1 decode hardware - the first Allwinner SoC that does - but whether the existing
  reverse-engineering is a working driver or a research note is not established; not scheduled.
- The 17 patches above ship in this repository's kernel series, but the decode and IOMMU behaviour they enable
  has not been re-tested end to end against this image's kernel, rootfs and `cpu_comm` stack. The GPU has been,
  as far as rendering and scanout go; nothing was played through cedrus in those runs.

Details: `doku/62-video.md`, `doku/64-afbd-quelle0.md`, `mainline/patches/kernel/series` §3, `doku/76-plan-ch0-de.md` (IOMMU bypass on the display node).
For the GPU section: `umbau/plan/keystone/PLAN.md` (stages S0 to S2) and the device readings in
`umbau/test-20260915/keystone-20260922.md`.
