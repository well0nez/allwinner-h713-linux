# Video: hardware decode, IOMMU, and the GPU path to the panel

The Video Engine ("cedrus" in mainline) decodes H.264 and HEVC in hardware; an IOMMU gives the codec its own
address space instead of raw physical memory; and the Mali-G31 GPU (Panfrost) can take the decoded frame
straight onto the display plane without the CPU ever touching a pixel. Together they are the difference
between playing a 1080p file and burning every core on colour-space conversion.

**Everything in this file comes from cstenger's `h713-display-video-path` branch and is proven only there.**
The measurements below predate this repository's current boot chain (layout v3, 10.09.2026, and the release
kernel series finalised 12.09.2026) and have not been repeated since. Treat hardware video decode, the
IOMMU and the GPU path as **unverified in this image** — this matches STATUS.md, not just this page.

## The pieces

| Block | Role |
|---|---|
| VE / cedrus | Hardware H.264 and HEVC decode via the mainline stateless `v4l2-mem2mem` API |
| IOMMU (`sun50i-iommu`) | Own address space for the video codec's two DMA masters only; every other master bypasses it, including the display plane (doku/76) |
| Panfrost (Mali-G31) | Imports the decoder's output as a `dma-buf` and converts NV12 to RGB |
| `misc/decd` | Kernel-side frame submission and fence handling between cedrus and userspace |
| DRM NV12 overlay (`0078`) | A plane that accepts the decoder's native NV12 buffer directly, so a fullscreen video does not need the GPU at all |

## Why the CPU can't do this

Decoding alone runs at 33 fps for 1080p on the A53 cores. Add a software NV12→BGRx conversion and it drops
to 3 fps: **97% of the time goes into colour-space conversion, not decoding** (doku/62, measured against a
`fakesink`/`fbdevsink` GStreamer pipeline). That is why the pipeline hands the decoded buffer to the GPU or
straight to the NV12 overlay instead of converting on the CPU — the conversion, not the decode, is what a
software path cannot afford.

## What was measured, and when

doku/62 (01.09.2026) found H.264 bit-exact through 1920×1080 and HEVC bit-exact at two sizes, checked
against an independently built host reference. With the GPU doing the colour conversion, zero-copy playback
reached **59.41 fps at 1920×1080** across 2,411 frames with zero commit timeouts — cstenger's own reported
figure was 59.71 fps, but at 720p. doku/64, the same night, traced a frame sitting in the decoder's own DRAM
through AFBD's planar channel (channel 0, the one the NV12 overlay would drive) onto the panel, closing
cstenger's open question about what makes a channel "serviced" rather than merely "configured". Both results
were real, on this board — but they describe a development state, not a boot chain that exists today, and
open questions from doku/64 §8 (which register supplies channel 0's live buffer address) were never closed
into a driver.

## Patches (`mainline/patches/kernel/series`, section 3 — 17 patches, byte-identical to the branch)

| Patch(es) | What it does |
|---|---|
| `0051` | Rate-limits IOMMU fault reporting instead of flooding the log |
| `0053`, `0079` | Panfrost/DRM: don't map or vmap imported buffers cacheable — required for zero-copy import |
| `0055` | Drops the 1416 MHz CPU OPP: it corrupts memory under load |
| `0059` | cedrus: claim the IRQ before disarming the watchdog |
| `0063` | AFBD: report a well-formed size range to userspace |
| `0064` | Puts the kernel console on the panel too |
| `0067`, `0071`–`0073` | `misc/decd`: match the stock frame-submit ABI; fix a release-fence lifetime bug; refuse non-contiguous `dma-buf` imports; declare the single-mapping DMA constraint |
| `0078` | Adds the fullscreen NV12 overlay plane |
| `0078a` | Our own addendum: the AFBD probe no longer asserts a 1280×720 default |

Not carried over: cstenger's `0080` attaches the video plane to the IOMMU. Our display node deliberately has
no `iommus` property and keeps reading the capture ring physically (doku/76, doku/78) — taking `0080` would
have reopened that.

## Limits, honestly

- **No AV1.** The H713 has AV1 decode hardware — the first Allwinner SoC that does — but whether the existing
  reverse-engineering is a working driver or a research note is not established; not scheduled before v0.1.
- The 17 patches above ship in this repository's kernel series, but the decode, IOMMU and GPU behaviour they
  enable has not been re-tested end to end against this image's kernel, rootfs and `cpu_comm` stack.

Details: `doku/62-video.md`, `doku/64-afbd-quelle0.md`, `mainline/patches/kernel/series` §3, `doku/76-plan-ch0-de.md` (IOMMU bypass on the display node).
