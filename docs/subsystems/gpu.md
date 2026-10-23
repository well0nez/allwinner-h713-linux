# GPU: Mali-G31 with Panfrost

The H713's GPU is a one-core Mali-G31 (Bifrost). Mainline's Panfrost drives it, and the image carries
its own mesa (25.0.7, the panfrost driver only, no LLVM, no X11, 14 MiB under `/usr/local`;
`rootfs/mesa/`) with EGL as a glvnd vendor library, GLES 3.1, GBM and the Wayland platform. Debian's
own mesa is kept out by stand-in packages, so that Debian's compositors and Kodi link against ours
([rootfs](../../rootfs/README.md)).

## What runs on it

- **The keystone warp.** `h713-warp` imports the HDMI capture slots as dma-bufs (the NV16 ring as
  `R8` + `GR88`), draws the warped frame as NV12 into three target buffers and hands them to `h713-tv`
  with a fence: 1.78 ms of GPU time per 1080p frame since the soft border became its own small draw
  (11.10.2026). The picture passes are bare texture fetches on purpose - this GPU hides no texture
  latency behind arithmetic, one `mix` after the fetch cost 2.2 ms instead of 1.65
  ([h713-warp](../tools/h713-warp.md)).
- **Kodi, the desktop and the browser**, Wayland clients of `h713-warp`'s server: their pictures
  arrive as dma-bufs (Kodi's AR30 with AFBC among them) and go through the same two passes, RGB to
  NV12 inside them ([h713-desktop](../tools/h713-desktop.md)).
- **Decoded video.** The VA-API driver hands cedrus's NV12 output to Kodi and mpv as dma-bufs, which
  they import on the GPU with no copy ([video](video.md)).

## Clocks and thermal

`pll-gpu` is pinned at 600 MHz and the GPU clock's M divider makes the four operating points
**150, 200, 300 and 600 MHz**, all at the fixed 960 mV - stock's own table for this die (kernel
`0268`, `0269`, 12.10.2026). Until then the clock model was off by two: it reported 864 MHz for a GPU
running at 432, and the first table's 288/432/600/696 ran at half their names, so measurements before
12.10.2026 carry the old labels. devfreq runs `simple_ondemand`; `gpu-thermal` has a passive trip at
85 C and a critical one at 105 C with the GPU as its own cooling device. With the warp on the governor
parks at the lower points.

The GPU's job interrupts are real-time threads (SCHED_FIFO 50) that fire four times a frame with the
warp on, and schedutil asked for the maximum CPU clock whenever one was runnable; `h713-cpufreq`
takes that minimum away ([h713-cpufreq](../tools/h713-cpufreq.md)).

## Import rules worth knowing

Panfrost imports a linear dma-buf as a texture only with a pitch that is a multiple of 64 bytes. The
display firmware lays the capture ring out with a pitch of the width rounded up to 16, so rings of
800, 720 and 912 bytes a line (800x600, 720x576, 720x480, 1280x1024) are refused and stay without a
keystone, by decision; 1080p, 720p, 1366x768, 1360x768, 1024x768, 1280x800, 1440x900, 1600x1200 and
640x480 are warped. Imported buffers are not mapped cacheable (kernel `0053`), which keeps a
write-combining buffer safe between the GPU and the scanout engine.

## Measured

On the HY310 (22.09.2026): `h713-gpu-probe render 3000`, 3000 textured 1080p frames, every hundredth
read back and checked, 0 mismatches; ten minutes of load, 16089 frames, 0 mismatches, at most 58 C in
the GPU zone; 3600 live capture frames on the panel in 60 s, 0 dropped flips, 59.4 fps. With the
warp: 59.7 of 60 frames shown and none dropped; the three targets cost 9.3 MB of CMA and the warp
about 0.6 GB/s of memory bandwidth. Not measured: the probe on the HY300PRO-G-EU, the GPU's own power
draw.

Details: [video](video.md), [h713-warp](../tools/h713-warp.md), `doku/201`, `userspace/h713-gpu-probe/`.
