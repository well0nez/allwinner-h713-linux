# mainline/tools/

## The OpenRISC compiler

`or1k-toolchain/build-or1k-toolchain.sh` builds the bare-metal `or1k-elf` compiler (binutils and GCC, C only,
libgcc, no libc) that crust, the firmware for the SoC's small OR1K core, is compiled with. The sources are GNU
tarballs pinned by SHA-256. It runs in the `h713-build` container and `release/build-all.sh` calls it when the
compiler is missing; see [docs/build-container.md](../../docs/build-container.md).

## Programs for the device

Nine small C programs, each with a GPL-2.0 SPDX line, written to answer one question about the display or the
GPU on the board itself. They run on the target; the header of each file gives its build line. Nothing under
`release/` builds them and no test covers them, so no build or test recipe beyond those headers lives in the tree.

| File | What it checks or does |
|---|---|
| `display/drm-flip.c` | Lists the DRM cards, connectors and modes, then sets a mode and flips pages with a dumb buffer, through raw ioctls and no libdrm |
| `video/decd-client.c` | Drives the vendor decoder's `/dev/decd` from user space and submits a frame by physical address |
| `video/gputest.c` | Runs a shader whose output depends on the pixel position and reads it back: does panfrost execute a job at all |
| `video/gles-probe.c` | Reports which of the EGL and GLES extensions the zero-copy video pass needs the stack offers |
| `video/gles-nv12.c` | Imports a decoder output buffer as a dma-buf and samples it as NV12 on the Mali |
| `video/gles-scanout.c` | Renders on the GPU straight into the scanout region and reads the same memory back through `/dev/mem` to confirm it |
| `video/gles-play.c` | Shows decoded H.264 from GStreamer on the panel through the GPU path, with the CPU touching no pixel |
| `video/gles-tear.c` | Draws a stepping bar on the GPU path and publishes it as the video path does, to score tearing in a capture |
| `video/h713-present.c` | Puts frames on the panel from Linux through the AFBD scanout path, committing in the order recovered from the vendor driver |

`gles-tear.c` names a scoring script that is no longer in this tree (see [PROVENANCE.md](../../PROVENANCE.md));
`h713-warp ctl check` is the tearing check the project uses now ([docs/tools/h713-warp.md](../../docs/tools/h713-warp.md)).
