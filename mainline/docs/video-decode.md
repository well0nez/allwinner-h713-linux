# H713 video decode (VE / Cedrus → panel)

Started 2026-08-07, immediately after display bring-up completed. Operational
companion to [claude-display-handoff.md](claude-display-handoff.md), which is
what this work builds on.

Goal for this phase: **decoded video visible on the projector panel.**

---

# HANDOFF — state as of 2026-08-15

**Video decode is DONE.** Decoded H.264 reaches the panel through the GPU with
the CPU never touching a pixel, at the vsync ceiling, without tearing.

## What works, hardware-verified

| | |
| --- | --- |
| **ZERO-COPY PLAYBACK** | **59.71 fps** sustained over 2700 frames, 0 timeouts, operator-confirmed moving picture. VE decode -> dma-buf -> GPU convert -> scanout. `tools/video/gles-play.c` |
| **Tearing** | **none.** `db` 0.00% rows-with-no-bar vs a 16.94% positive control. `tools/video/gles-tear.c` |
| **H.264 decode** | **bit-exact** vs host software references, all five ladder vectors, re-verified on the current kernel. 311 fps standalone |
| **GPU** | Mali-G31 via mainline panfrost, GLES 3.1 on mesa 25.0.7 |
| **Presentation ceiling** | **58.93 fps** against a 59.7 Hz panel — the actual limit now |
| **CPU-conversion path** | still works, capped at 28.30 fps by the ~44 MB/s uncached read of the decoder's buffer. Superseded, kept as fallback |

## How to run it

```
reboot bootloader          # from Linux
h713_disp auto 0x34 logo   # REQUIRED every boot; plain autoboot does not do it
boot
```
then, on the target:
```
EGL_PLATFORM=surfaceless ./gles-play video-test/v04-1280x720-high.h264
```
`sunxi-scanout-dmabuf` auto-loads at boot. `gles-play` refuses to run if the
AFBD clock is gated rather than hanging the board on gated registers.

## Three claims in this file were wrong and are retracted

Read these before trusting anything historical here:

- **"Direct YUV scanout WORKS" (2026-08-12) — WITHDRAWN.** Did not reproduce;
  the same command produces the 4x-repeat greyscale it claimed to fix. It rested
  on a photo attributed to the wrong command, the second time that happened.
- **"The 28 fps ceiling is the cross-process handoff" (2026-08-10) — WRONG.**
  The handoff is nearly free; the cost is reading an uncached CMA buffer.
- **"The M1 md5 baseline has drifted" (2026-08-15) — WRONG, and mine.** A
  hand-typed pipeline missing `! video/x-raw,format=NV12 !`. The baseline was
  always intact.

## LOOSE ENDS — start here next session

In priority order. Item 1 is closed; item 2 is the remaining real debt, and the
rest are cheap.

1. **The rootfs can rebuild the video tooling — DONE 2026-08-15.** The video
   *runtime* now ships in the base package set, because this is a projector and a
   build that cannot play video is not a useful build of it; `--profile dev` adds
   the on-target compiler and headers. Details and the package rationale are in
   [rootfs.md](rootfs.md#video-runtime-and-the-dev-profile).

   Measured, not assumed. `tools/rootfs/verify-video-tooling.sh` chroots into a
   built image under qemu and compiles every tool with the image's own gcc:

   | image | result |
   | --- | --- |
   | the previous `build/out/rootfs.tar` (the debt) | **2/8** — `EGL/egl.h: No such file or directory`, and no `gstreamer-1.0.pc` at all. Only the two plain-gcc tools built |
   | `build.sh --profile dev` | **8/8** |

   Four things this turned up, three of them corrections to the note that used to
   be here:
   - `KHR/khrplatform.h` **does** ship in Debian — in `libgl-dev`, which
     `libgles-dev` depends on. Nothing needs to come from the Khronos registry.
   - `libglvnd-core-dev` is not needed; in trixie it ships only glvnd ABI
     headers.
   - **`gles-play.c`'s own documented build command had never linked.** It omits
     `gstreamer-video-1.0`, so `gst_video_info_from_caps`,
     `gst_buffer_get_video_meta` and `gst_video_meta_api_get_type` are undefined
     references. Whatever built the working binary on the board, it was not the
     command in the file. Fixed in the source header.
   - `sunxi_scanout_dmabuf` is a plain misc device with **no DT compatible and no
     module alias**, so udev could never have autoloaded it — the board must have
     been doing it by hand. Every image now carries
     `/etc/modules-load.d/h713-video.conf`.
2. **The display still needs U-Boot every boot.** `h713_disp auto 0x34 logo`
   before `boot`, or the panel stays dark and every tool refuses. Linux cannot
   bring the panel up itself. This is the largest remaining gap between "works on
   the bench" and "works as a product", and it is display work, not video work.
   The KMS driver added on 2026-08-15 does **not** close this: it adopts the
   display U-Boot brought up and deliberately never touches timing, the LVDS PHY
   or the display reset. See [kms-display.md](kms-display.md).
3. **The tearing floor run is flawed.** `gles-tear noflip` paints its static bar
   at the left edge, where keystone and lamp falloff make detection marginal, so
   it scored 16.42% when it should sit at or below `db`. Centre the bar and
   re-capture; one 17 s take. The result does not depend on it (`db` came in
   *below* the broken floor) but the floor is not usable evidence as it stands.
4. **Hypothesis worth one capture:** the CPU path's 23.03% floor used the same
   left-edge static bar and may have been inflated the same way.
5. **Decide what DECD is for — ANSWERED 2026-08-15, and the answer is "its
   registers".** DECD probes and works but has no job, while holding exactly the
   two resources a display driver needs: the AFBD window at `0x05600000` and the
   60 Hz vsync interrupt on SPI 110. Both now belong to the new KMS driver
   (patches 0037/0038) and `dec@5600000` is `status = "disabled"`. It is still
   built as a module and the node is one word from coming back.
   See [kms-display.md](kms-display.md).

## HEVC decodes too — 2026-08-16

The VE decodes H.265 as well as H.264, bit-exact, with no driver changes. Same
method as the M1 gate: deterministic `testsrc2` source, host software decode to
linear NV12 as ground truth, target decode through
`filesrc ! h265parse ! v4l2slh265dec ! video/x-raw,format=NV12`, md5 compared.

| vector | result |
| --- | --- |
| `h01-640x480-main`, 25 frames | **bit-exact** (`9ebd49ec…`) |
| `h02-1280x720-main`, 25 frames | **bit-exact** (`c898a8f0…`) |
| throughput | **~550 fps**, 500 frames of 720p in 0.905 s |

Forcing NV12 is required for the same reason as H.264: unforced it negotiates
the 32x32 tiled `ST12`, which is correct output that can never match a linear
reference. Vectors come from `tools/video/make-test-streams.sh`.

**10-bit does not work**, and the blocker is in the kernel, not this SoC:
mainline cedrus exposes no 10-bit capture format at all, so `Main10` reaches EOS
having decoded zero frames even though the capability bit and the hardware
registers are both present. Full analysis, and what it would take for stock mpv
to use the VE at all, in [vaapi-scope.md](vaapi-scope.md).

## NEXT PHASE — audio

The starting position, gathered but not yet acted on:

- **Stock DTB** (`local/stock-boot/sunxi.fex`, the authority — see the PPU
  lesson) carries `codec@2030000` compatible `allwinner,sunxi-internal-codec`
  with `pll_audio`/`pll_tvfe`/`codec_dac`/`codec_adc`/`codec_bus` clocks;
  `sndcodec@2030330` compatible `allwinner,sunxi-codec-machine`; `daudio2` pins
  on function `d_i2s2`; a `vs,trid-audio-bridge`; and a `sunxi,simple-audio-card`.
- **Third-party RE drivers exist** in
  `local/allwinner-h713-linux/drivers/audio/`: `snd-soc-sunxi-h713-codec.c`,
  `-cpudai.c`, `-machine.c`. **These are not vendor sources** — that tree is
  another project's mainline port ("HY300/HY310 Linux Porting Project",
  Copyright 2026), and the codec file says so in its own header: *"Reverse-
  engineered from stock vmlinux (sun50iw12) via IDA Pro"*. They name registers,
  which is useful, but they carry exactly the authority of an unverified
  decompilation — the same class of claim as
  [h713-inherited-claims-were-wrong]. The vendor's own Android stack is the
  authority; that tree is a peer, and its README still reports the same 4x1
  XRGB greyscale tiling this project diagnosed as a 4-bytes-per-pixel stride
  fault.
- **Mainline has `sun4i`/`sun8i` codec drivers** that may or may not fit; the
  H713 is sun50iw12 and the display work has repeatedly shown it is *not* H616.
- The roadmap entry is item 6, "Audio (I2S / codec / HDMI-in audio captured off
  the HDMI-RX) — depends on what's populated". **What is populated is the first
  question**: this is a projector with speakers, so a codec and amp should be
  there, but that is an assumption until someone looks at the board or gets a
  sound out of it.

**Method that worked all through video decode, and should carry over:** check
the stock DTB before mainline for anything H713-specific; build one instrument
per question; keep a positive control for every measurement; and confirm on
hardware before believing a claim, especially a convenient one.
## Board state right now

- **FAT `mmc 1:2` holds the DECD kernel** (persistent; `fatwrite` done). It has
  `dec@5600000` enabled and `CONFIG_SUNXI_DECD=m`.
- **`CONFIG_MODVERSIONS` is off**, so driver iteration needs only the ~63 KB
  `.ko` over serial (~1 min), not a 12-minute kernel transfer.
- `/root` on the target holds `h713-present`, `decd-client`, `sunxi-decd.ko`,
  `vedump.py`, the NV12 frames (`bars.nv12`, `one.nv12`, `frames30.nv12`) and
  `video-test/` with the H.264 ladder. Plus a lot of `*.log` scratch worth
  deleting. Both tools are current as of the 2026-08-14 simplification: the
  closed-investigation diagnostics (`yuvtry`, `flip-test`, `bar-noflip`,
  `vbprobe`, `leak-test`, `latency-probe`, `yuv-stream`) are gone — git has
  them if an old trail needs re-running — and every surviving command was
  re-verified on hardware after the rebuild.
- **The module is NOT auto-loaded**: `insmod /root/sunxi-decd.ko` after boot.
- **The display must be brought up in U-Boot before booting Linux**, every time:

```
reboot bootloader          # from Linux, lands at the U-Boot prompt
h713_disp auto 0x34 logo   # panel up; plain autoboot does NOT do this
boot
```

`h713-present` refuses to run if this was skipped (it checks the AFBD clock
gate) rather than hanging the board on gated registers.

## Direct YUV refuted, 2026-08-14

Photos in `local/lcd-photos/test_54/`, one camera position, cold boot, logo
reference shot first — the provenance discipline the `test_41` misattribution
forced on this project, applied to the claim that misattribution produced.

| phase | command | photo | result |
| --- | --- | --- | --- |
| 1 reference | logo from U-Boot | `IMG_0690` | logo, clean |
| 2 **control A** | `h713-present yuv2 bars.nv12 3 0` | `IMG_0691` | **4x repeat, greyscale** |
| 3 | DECD `FRAME_SUBMIT`, format untouched | `IMG_0693` | frame over logo (reproduces `test_53`) |
| 3b | + `h713-present fmt 3 1280` | `IMG_0694` | 4x repeat, greyscale |
| 4 | + `h713-present info 0` | `IMG_0695` | 4x repeat, greyscale |

**Control A is the finding.** It is the exact command the 2026-08-12 section
credits with working, run from a cold boot, and it produces the *same* 4x-repeat
greyscale that section says it fixed. Reference: `testsrc2` is 6 colour bars with
**one** diagonal; every failing photo shows ~16 stripes and **four** diagonals.

The arithmetic is the diagnosis, and it is the same one written down on
2026-08-09: 4 bytes/pixel over a 1280-*byte* stride packs four source rows into
each display row, and the greys are the Y plane landing in the RGB components.
The fetch never stopped being 4 bytes/pixel.

**The info page was not the cause.** `dec_frame_submit()`'s linear path sets the
info address to `y_phys + 4096` (`video_info_buffer_init()`), which on hardware
reads `info=6c101000` — 4 KB inside a Y plane that starts at `6c100000`. That is
a real bug, independently found in the research tree's RE notes, and it is worth
fixing. It is not what blocks YUV: `info 0` changed nothing.

### Why the format byte cannot work, from the vendor's own table

`LogoRegData.bin` DE blocks parsed with the record walker from
`h713_logo_walk()` (16-byte records, 4-byte resync). Every one of the 8 blocks
writes exactly this AFBD set and nothing else:

```
05600000 <- 80000020
05600140 <- 03001901   ctrl          05600164 <- 00000808
05600148 <- 008000ff                 05600168 <- 000003b2
0560014c <- 00000080                 0560016c <- 00000021
05600150 <- 02cf04ff   (h-1, w-1)    05600170 <- 00001400   stride
05600154 <- 002c004f                 05600174 <- 02d01400   (h, stride)
05600160 <- 02d00500   (h, w)        05600178 <- 6c100000   source
                                     05600144 <- 00000001   ready
```

| block | geometry | stride | bytes/pixel |
| --- | --- | --- | --- |
| 0 | 1920x1080 | 7680 | 4.0 |
| 1, 2, 5, 6 | 1280x720 | 5120 | 4.0 |
| 3 | 640x360 | 2560 | 4.0 |
| 4 | 864x480 | 3456 | 4.0 |
| 7 | 1024x608 | 4096 | 4.0 |

**Not one write to `0x05600010`–`0x13`, `0x40`, `0x44`, `0x70` or `0x84`.** The
registers this project has spent four sessions poking are not in the vendor's
scanout configuration.

### Which register holds the format — the candidates, narrowed

The vendor's own `sunxi_ge2d.h` gives the structure. AFBD channels are at
`0x05600100` (ch0) and `0x05600140` (ch1), **channel stride `0x40`**, so every
register in the table above is one channel's block at ch1. It also names two of
them outright, from `osd_interrupt_init()`:

```
#define GE2D_OSD_IRQ_CLEAR   0x168   /* WriteRegWord(90177896, -1) */
#define GE2D_OSD_IRQ_ENABLE  0x16C   /* WriteRegWord(90177900, 16) */
```

So `0x0560016c` is an **interrupt enable, not a format field**. That leaves four
registers in the channel block that could carry it:

| offset | reg | value | note |
| --- | --- | --- | --- |
| +0x00 | `0x05600140` | `03001901` | ctrl; bits [3:2] are `mirror_mode` per U-Boot |
| +0x08 | `0x05600148` | `008000ff` | |
| +0x0c | `0x0560014c` | `00000080` | |
| +0x24 | `0x05600164` | `00000808` | **best candidate** — two 8s reads like a per-component bit depth |

All four are constant across all 8 blocks while geometry and stride vary, which
is what a format field should do. **Sweep these before anything expensive:**
`load` puts pixels in place without touching a register, and `poke` changes one
field against an otherwise untouched vendor configuration. Success is the 4x
horizontal repeat collapsing to 1x.

## DECD's runtime suspend resets the display, 2026-08-14

`dec_disable()` calls `reset_control_assert(dec->rst_bus_disp)` on the **shared**
display reset, then drops `clk_bus_disp`. Measured: one `PM_HINT off` -> `on`
cycle took the AFBD window from `ctrl=03001901 stride=00001400 src=6c100000` to
all zeros, and the panel went black. U-Boot's programming does not survive it,
and `dec_enable()` cannot restore what it never wrote.

This is the Milestone 4 resource-ownership warning arriving early: U-Boot owns
these registers and DECD wants them. Consequences for anyone running this:

- `decd-client show` used to end with `PM_HINT off`, so **the panel blanked
  when the dwell expired** — including the 2026-08-12 run, which is why nobody
  could report what it showed. **Fixed 2026-08-14:** `show` now leaves the
  device enabled and says so; `decd-client pm off` still does the reset
  explicitly if wanted. Verified on hardware: the AFBD window survives a full
  `show` cycle intact.
- Any test that needs the display alive must take **one** `pm on` and never
  suspend. Recovery is `reboot bootloader` -> `h713_disp auto 0x34 logo` ->
  `boot`.

## The plane-0 hunt — live-poke campaign, all null, and the map it bought (2026-08-14)

One evening of operator-watched probes, every one register-verified as landing
and every one visually null except the calibrations. The value is the map.

### What was tried, in order

| probe | result |
| --- | --- |
| format sweep: `0x140/0x148/0x14c/0x164` bit variants, `0x000` bit 5 | null; writes verified sticking by pair-poke; `0x164` is 16-bit, holds reset default `0x808` in **both** channels |
| ch0 (`0x05600100`) enabled as a ch1 clone, ARGB source | null; status never leaves 0 |
| ch0 with the **vendor's own** ctrl `0x83000201` (from `ge2d_plane_afbd_writes[]`) + full `ge2d_plane_init()` write set + planar config | null; status never leaves 0 |
| the complete `dec_reg_video_channel_attr_config()` linear recipe incl. plane geometry `0x48/0x4c` | null — and `0x48/0x4c` were **already correct** (`(720,1280)/(360,1280)`, someone programs them every boot) |
| bypass byte `0x69` bit 0 cleared | null |
| mux `0x68` values 0/1/3 | null |
| ch1 ctrl "disabled" (`0x00010000` + ready) | **panel unaffected** — the disable does not latch |
| VBlender window geometry halved/moved | null; its `0x00` reads 0; MIPS-programmed geometry present (two windows `1280x720@(49,22)`) but pokes are not consumed |
| plane 0 DE-layer window (`0x05280040`) opened, cloned from plane 1 | null |
| OSD0 (`0x05248000`) cloned from **live** OSD1 incl. the plane-open bit `+0x1c[0]` | null |
| DE2 subs `0x05288000/0x0529c000` | both read all-zero — not in the live path |
| mixer ctrl `0x0525c038` bit sweep — including **removing** the live bit | null both ways; live value is `0x40`, not the `0x100` U-Boot writes, so something rewrites it post-boot |

Calibrations that DID show, proving the instrument: framebuffer content +
ch1 commit (the white-flash beacon), and the plane-1 layer X origin
`0x0528008c` (picture shifted ~400 px, the band fix's two-sided mover).

### The model this forces

The per-commit latch consumes **addresses, strides and origins** — that is why
flips, the 4x-repeat stride change, and the layer origin all work. It does not
consume **topology**: which planes exist, enables, routing. Removing the mixer's
only live bit and "disabling" ch1 both change nothing, so topology is latched
once at pipeline bring-up and never re-read. Every plane-0 resource accepts
writes that nothing consumes because plane 0 was not in the topology when U-Boot
brought the pipeline up.

Corollary: **no register poke can add a plane to a running pipeline.** The
plane-open ACTION is a bring-up-time sequence, and `tgd_is_plane_open()`
(OSD base `+0x1c` bit 0) is only its status readout — writing the bit does
nothing, confirmed live.

### Where the answer is

`local/h713-lab` holds board B's own `ge2d_dev.ko` — **unstripped, display
symbols intact** (SHA-256 `a79017e5d3bc...`, see mips-display-recovery.md).
The plane-open sequence is in there, statically recoverable: callers of
`ge2d_plane_init`, the tgd plane ioctls, and whatever orders VBlender/OSD0/ch0
enables against a pipeline restart. No more live pokes until that names a
candidate sequence.

## Gotchas that cost real time

- **The USB gadget only enumerates if Linux has not run since power-on.** Cold
  boot, interrupt at `=>`, then UMS/fastboot. Otherwise use YMODEM +
  `fatwrite ... ${filesize}`. See [flash.md](flash.md).
- **Score a bulk write by throughput, not exit status.** `dd` reported
  "4.3 GB, 1.0 GB/s" and exited 0 on a write that never reached the device.
- **A control must match the run in every respect except the variable under
  test.** "Nothing is running" is not the baseline for "something is running" —
  that error produced a phantom tearing defect and five wasted investigations.
- **The vendor is a strong prior, not a rule.** Copying its `reg` order would
  have pointed the driver at the wrong block.
- **`dec_frame_submit()` always returns 0**, even when disabled or when it drops
  the frame. The `fence_fd` is the only real feedback.
- **A register readback is not a picture.** `+0x11` accepts 3, retains 3 across a
  latch, and the panel does not change — because that register is not in the
  fetch path. Twice now a readback has been scored as a visual result. The panel
  is the instrument for a display claim; the register only says the write landed.
- **Re-run the control before believing an old success.** Two claims in this file
  were produced by attributing a photo to the wrong command. A control costs one
  boot and one photo.
- **Use the project's own instrument before writing an ad-hoc command.** The
  "M1 md5 drift" of 2026-08-15 was entirely a hand-typed pipeline missing
  `! video/x-raw,format=NV12 !`, which `m1-decode-test.sh` has always carried
  and whose comment predicts the exact wrong byte count. The script existed and
  I did not run it.
- **A control cannot validate a measurement it shares a defect with.** That same
  false drift survived a control — old kernel vs new kernel, byte-identical —
  because both runs used the same broken command. The control correctly showed
  "not caused by this change" and I over-read it as "the effect is real".
- **Operator watch windows need a panel-side beacon and an explicit go.** A
  probe launched while the operator reads the announcement is a probe nobody
  watched. Flash the panel white twice before the first trial, and never fire
  until the operator says go. A calibration trial must be UNMISSABLE (the
  400 px origin jump), not subtle (a 49 px window nudge that history recorded
  as a ~14 px wiggle).

## Next steps, in order — SUPERSEDED, kept for the trail

**All of the below is historical.** It was the plan while the GPU path was
still unknown; the GPU path then worked and made most of it moot. The live
plan is in LOOSE ENDS at the top of this file.

What actually happened to each item:

1. **Sweep the format registers** — done, all null. Closed by the
   topology-latch model.
2. **Capture the vendor configuring a video plane** — never needed. It was
   correctly costed as expensive (reaching the Android UI destroys the Debian
   rootfs) and the GPU path made it unnecessary.
3. **Decide whether DECD is the right block** — answered: it is not, for this
   purpose. Its registers are not in the scanout fetch path. Still carried; see
   loose end 5.
4. **Fix `video_info_buffer_init()`** — still unfixed and still wrong
   (`y_phys + 4096` lands inside the luma plane). Harmless while DECD is unused.
5. **Give DECD its own display reset** — moot unless DECD gets a job.
6. **The CPU-conversion path as fallback** — measured at 28.30 fps, below the
   30 fps content rate, and superseded by the GPU path at 59.71.
7. **`clock-frequency`** (we run 100 MHz, vendor asks 200) — never revisited;
   nothing depends on it now.

The original text follows.

## Next steps, in order (original, superseded)


1. ~~Sweep the four candidate format registers.~~ **DONE 2026-08-14 — all
   null**, and the whole live-poke approach is closed by the topology-latch
   model above. The next step is **static RE of board B's unstripped
   `ge2d_dev.ko`**: recover the plane-open sequence (callers of
   `ge2d_plane_init`, the tgd plane ioctls). Desk work, no panel time.
1b. **GPU path — UNBLOCKED 2026-08-15.** panfrost runs jobs (`PASS`, 1252
   Mpixel/s) after fixing the PPU base address and domain table from the stock
   DTB. The GLES video pass is now the live next step: import a cedrus CAPTURE
   dma-buf as an NV12 texture and render into the scanout region (wrapped by
   `DECD_IOC_MAP_LINEAR_BUFFER`), which removes all three M3 costs at once.
2. **Only if that dead-ends: capture the vendor configuring a video plane.**
   `LogoRegData.bin` is ARGB8888 only, so the answer is in the running Android
   stack. **This is expensive — do not treat it as a reboot.** Reaching the
   Android UI needs `boot_a` restored to the vendor image, `super` intact, and
   `UDISK` formatted f2fs, **which destroys the Debian rootfs** — they contend
   for the same partition and there is no free 4 GiB elsewhere — see
   [flash.md](flash.md), Methods 5 and 6. `run switch_vendor`
   alone gets the vendor *boot chain*, not the UI. It is also unproven that
   `/dev/mem` at `0x0560xxxx` is readable under stock Android's SELinux, so this
   can cost a rootfs rebuild and still yield nothing. If it is run anyway: a
   1280x720 H.264 clip diffs against DE blocks 1/2/5/6 with identical geometry,
   making the format the only variable; 1080p content diffs against block 0.
3. **Decide whether DECD is even the right block.** Its whole register window
   (`afbd + 0x60` onward) is disjoint from the scanout registers U-Boot drives.
   The research tree independently concluded `decd` drives AFBC-compressed video
   frames, and cedrus emits linear NV12 or Allwinner-tiled, never AFBC. Settle
   this before writing any more driver code against it.
4. **Fix `video_info_buffer_init()` regardless.** `y_phys + 4096` lands inside
   the luma plane. Confirmed on hardware (`info=6c101000`, `Y=6c100000`). It is
   not what blocks YUV, but it is wrong.
5. **Give DECD its own display reset, or none.** `dec_disable()` asserting the
   shared `rst_bus_disp` destroys U-Boot's display setup; see above.
6. ~~The CPU-conversion path is the fallback; measure whether conversion caps
   the frame rate first.~~ **MEASURED 2026-08-14 — it does not ship.** 28.3 fps
   sustained against 30 fps content, and the cap is the ~44 MB/s CPU read of the
   decoder's output buffer, not conversion (which is worth 3.7 ms/frame total).
   See the M3 result. **Try a cached V4L2 CAPTURE mapping before the plane RE**
   — if the buffer can be read at cache speed the existing architecture reaches
   real time with no display work at all.
7. Revisit `clock-frequency` (we run 100 MHz, vendor asks 200) once it works.

---

## Three blocks, and the naming trap

The existing docs use "DECD" and "Cedrus/VE3" interchangeably for "next: video
decode" ([status.md](status.md) says DECD, [roadmap.md](roadmap.md) says
Cedrus/VE3). They are different silicon and only one of them is a codec.

| block | node | what it is | state |
| --- | --- | --- | --- |
| **VE / Cedrus** | `video-codec@1c0e000` | the decoder — H.264/H.265/MPEG-2/VP8, V4L2 stateless M2M | binds, `/dev/video0` (2026-08-07) |
| **AV1** | `av1-decoder@1c0d000` | separate AV1 block | node exists, compatible `allwinner,sunxi-google-ve`, **no driver in our tree binds it** — inert |
| **DECD** | `dec@5600000` | **not a codec** — the AFBD frame-submission path that scans decoded frames out to the panel | patch 0013 present, `CONFIG_SUNXI_DECD` off, node `disabled` |

DECD owns the `0x05600xxx` AFBD window — the same registers
`h713_mips.c` already drives by hand (`0x05600140` ctrl, `0x05600170` stride,
`0x05600178` source). So the display bring-up did not merely leave DECD
"provisioned"; it left us already driving DECD's registers from U-Boot, which is
why the presentation plan below starts there rather than with the vendor driver.

**A research-tree claim to not repeat.**
`local/sun50iw12p1-research/docs/AV1_HARDWARE_DECODER_ANALYSIS.md` presents an
ioctl table as an AV1 decoder API ("MAJOR DISCOVERY"). It is not. That is
`decoder_display.h` — the DECD frame-submit interface — and
`DEC_FORMAT_YUV420P_10BIT_AV1` is a *pixel format the display path accepts*, not
a codec entry point. Same over-read pattern as the six load-bearing false claims
already caught in that tree; treat its video conclusions as unverified.

## Proven on hardware, 2026-08-07

| fact | evidence |
| --- | --- |
| Cedrus binds and registers a node | `cedrus 1c0e000.video-codec: Device registered as /dev/video0`; `/sys/class/video4linux/video0/name` = `cedrus` |
| the VE is behind the IOMMU | `platform 1c0e000.video-codec: Adding to iommu group 0` |
| the flashed kernel has the **4 MiB** scanout reservation | `OF: reserved mem: 0x6c100000..0x6c4fffff (4096 KiB) nomap non-reusable uboot-scanout@6c100000` — the 8 MiB version covering the `0x6c500000` back buffer is built but was never flashed |
| the target had **no** V4L2 userspace | no `v4l2-ctl`, `ffmpeg`, `gcc` or `python3` in the minimal rootfs |

**Binding is not decoding.** Cedrus binds on the strength of a DT compatible
(`allwinner,sun50i-h6-video-engine`) and its clock/reset handles; nothing in a
successful probe touches a codec register. Whether the H713's VE3 answers to the
H6 register map is the open question, and it is the same shape as the Crypto
Engine question that turned out negative after the driver had happily registered
every algorithm. Assume nothing from the probe line.

## Debian's ffmpeg cannot drive this decoder

Checked before building a rootfs around it. Debian 13 ships ffmpeg **7.1.5**,
whose `debian/rules` configures `--enable-libdrm` and **not**
`--enable-v4l2-request` (nor `--enable-libudev`, which the hwaccel needs). So
stock `ffmpeg -hwaccel v4l2request` is unavailable no matter what the version
number suggests.

**Consequence:** the off-the-shelf decode client is **GStreamer's
`v4l2slh264dec`** (gst-plugins-good's V4L2 stateless codec support, registered at
runtime when a compatible `/dev/videoN` exists). ffmpeg stays useful for stream
preparation, demuxing and software reference decodes. A custom ffmpeg build with
`--enable-v4l2-request` remains an option if GStreamer disappoints, but it is not
the starting point.

## The test-vector ladder

`tools/video/make-test-streams.sh` → `local/video-test/` (gitignored).

Each step adds exactly one coding feature, so a failure names the feature rather
than just failing. Annex-B elementary streams, because a container demuxer in the
decode path only adds a way to be wrong about something that is not the decoder.

| vector | size | profile | adds |
| --- | --- | --- | --- |
| `v01-320x240-baseline` | 320x240, 8 frames | Constrained Baseline | nothing — I+P, CAVLC, no B. If this fails the fault is fundamental |
| `v02-1280x720-baseline` | 1280x720, 60 | Constrained Baseline | panel-native size — separates "cannot decode" from "cannot decode at this size" (stride, buffer sizing, IOMMU mapping) |
| `v03-1280x720-main` | 1280x720, 60 | Main | B-frames + CABAC — reference-list construction and output reordering, which is what stateless userspace gets wrong first |
| `v04-1280x720-high` | 1280x720, 60 | High | 8x8 transform — what real-world files actually use |
| `v05-1920x1080-high` | 1920x1080, 60 | High | the real clip; integration test, no exact reference |

Every synthetic vector ships an NV12 **host software-decoded reference**
alongside it (`.nv12`), because "the decoder produced output" and "the decoder
produced the *right* output" are different claims. Source is `testsrc2`, which is
deterministic frame-for-frame, so the reference is a fixed artifact rather than
something that drifts between runs; and it moves, because a static scene never
exercises inter prediction.

## M1 RESULT — PASSED, 2026-08-09. The H713 decodes H.264 in hardware.

**Every vector in the ladder is bit-exact against its host software reference.**

| vector | | bytes |
| --- | --- | --- |
| `v01-320x240-baseline` | **PASS** | 921,600 |
| `v02-1280x720-baseline` | **PASS** | 82,944,000 |
| `v03-1280x720-main` (B-frames, CABAC) | **PASS** | 82,944,000 |
| `v04-1280x720-high` (8x8 transform) | **PASS** | 82,944,000 |
| `v05-1920x1080-high` (real clip) | **PASS** | 186,624,000 |

Mainline cedrus drives the H713 VE correctly, up to 1080p High profile, with no
driver changes at all. The pipeline is:

```
gst-launch-1.0 filesrc location=X.h264 ! h264parse ! v4l2slh264dec \
  ! video/x-raw,format=NV12 ! filesink location=out.nv12
```

### The entire fault was one device-tree property

`iommus = <&iommu 0>` on the `ve` node, pointing at an IOMMU that does not exist
at that address. Removing it fixed **both** symptoms at once — the kernel stopped
being corrupted *and* the decoder started working. No driver patch, no register
RE, no clock or IRQ change.

**Force the output caps.** Without `video/x-raw,format=NV12` the decoder
negotiates `NV12_32L32` — Allwinner's 32x32 tiled layout — and emits
`320x256` frames (122,880 bytes each, `ALIGN(240,32)=256`). That output is
correct but *tiled*, so it will never match a linear reference and looks like a
failure if scored naively. The 983,040-byte tiled result was the first evidence
the hardware was decoding at all.

### What this cost, and the lesson

The first diagnosis — "the inert IOMMU is the cause" — was **right**, and was
then talked out of on two grounds that both looked sound: that IOVAs allocate
top-down near 4 GiB and so should miss a 1 GiB DRAM at `0x40000000`, and that the
crash landed *after* clean pipeline teardown. Neither objection was silly; both
were wrong. The retraction cost more than the original error would have.

**The lesson is about what settles a question.** The IOMMU claim was testable
with a one-line DTS change from the moment it was made. Instead it was argued
about — refined, hedged, re-derived from register dumps and vendor DTBs — while
the deciding experiment went unrun. Worse, when the experiment was finally built
it was **bundled with a second change** (`power-domains`), which broke probe
before decode was reached and destroyed the run's ability to answer anything.

Rules earned here:

- **A one-line change that would settle it beats any amount of reasoning about
  whether it will.** Run it first, then theorise about the residue.
- **One variable per bench run.** The bundled build wasted a full
  build-plus-12-minute-transfer cycle and answered nothing.
- **A retraction needs evidence, not just a counter-argument.** "Here is why
  that mechanism seems implausible" is not the same as "here is a measurement
  showing it is not the cause."

## The diagnostic trail (kept — this is how it was found)

What follows is the failing state as it was investigated, retained because the
refutations are reusable and several are load-bearing for future work.

**The VE decoded nothing, and trying crashed the kernel.** Not "decoded
incorrectly" — zero frames out, on the easiest vector in the ladder.

| observation | evidence |
| --- | --- |
| the decoder advertises the right codecs | `--list-formats-out`: `MG2S` MPEG-2, **`S264` H.264**, `S265` HEVC, `VP8F`. Capture side offers `NV12`, `ST12` (32x32 tiled), `NV21`, `YU12`, `YV12` |
| GStreamer accepts the device | `v4l2slh264dec` + h265/mpeg2/vp8 all register from `libgstv4l2codecs.so` (gst-plugins-bad). `/dev/media0` exists, so the request API is present |
| format negotiation works | `Probed caps: ... format=(string)NV12, width=320, height=240` — `VIDIOC_ENUM_FMT` and `ENUM_FRAMESIZES` return sane values |
| **but nothing decodes** | pipeline goes PREROLLED -> PLAYING -> **EOS in 2.6-25 ms**, exits *cleanly* with no error, and the output file is **0 bytes** |
| **and the kernel dies** | recursive `Unable to handle kernel paging request`, then `Kernel panic - not syncing: kernel stack overflow`. Reproduced on 3 of 4 runs; `panic=5` reboots the board |

**The crash is memory corruption, not a decoder fault.** The faulting context is
`pc : _prb_read_valid+0x10` / `lr : desc_make_final+0x88`, `Comm: systemd-journal`
— the **printk ring buffer**. Something scribbled over kernel memory, and the
crash surfaced when journald next read the log. The infinite recursion follows
mechanically: printing the fault re-enters the ring buffer, which faults again.

**Timing matters and reframes it:** gst-launch reaches EOS, tears down, prints
`Freeing pipeline ...` and *exits* — the fault lands afterwards, at the shell
prompt. So this looks like a late DMA or a use-after-free at teardown, not a
fault while decoding.

### The control that makes this conclusive

```
gst-launch-1.0 filesrc location=v01-320x240-baseline.h264 ! h264parse \
  ! avdec_h264 ! videoconvert ! video/x-raw,format=NV12 ! filesink location=/root/sw.nv12
```

**921600 bytes, md5 `98a4dbc6e165766cbdfa4d8d4cc1238f` — bit-exact against the
host reference.** Software decode of the same file, on the same board, through
the same parse chain and the same NV12 convention, is perfect.

That single run validates the vector, `h264parse`, the pixel convention, and the
whole scoring method at once, and leaves the fault nowhere to hide but
`v4l2slh264dec` / cedrus / the H713 VE. **Run this control before believing any
future hardware-decode result.**

## The IOMMU is inert — and it WAS the cause (confirmed by removing it)

Read back on hardware with the driver bound and `iommu group 0` created:

```
0x030f0000 0x00000000   0x030f0010 0x00000000   0x030f0020 0x00000000  <- ENABLE
0x030f0030 0x00000000   <- TTB      0x030f0080/84/88 all 0x00000000
```

Every register reads zero, including `ENABLE` (+0x20) and `TTB` (+0x30), both of
which an attached domain writes. **Nothing is responding at that address.** The
DTS says so itself, in a comment directly above the node: *"Address 0x02010000 is
the H713 IOMMU MMIO base (unverified)"* — while the node uses `0x030f0000`, the
**H6** base. Its `resets = <&ccu 11>` is a bare index rather than a symbolic
`RST_*`, which is the same kind of transcription this project has been bitten by
twice already.

So cedrus was attached to an IOMMU that does not exist, and the DMA layer handed
it IOVAs believing they would be translated and bounded. **An inert IOMMU is
worse than no IOMMU**, because it removes bounds everything above it assumes are
enforced. Fixed regardless of whether it is this bug: `iommus` removed from the
`ve` node, node set `status = "disabled"`, both with the evidence in-tree.

**Confirmed on hardware.** Removing `iommus` from the `ve` node — with nothing
else changed — stopped the corruption and made the decoder work, all five vectors
bit-exact. The IOMMU was the fault.

Two objections were raised against this diagnosis before it was tested, and both
were wrong: that IOVAs allocate top-down near 4 GiB and so should miss a 1 GiB
DRAM at `0x40000000`, and that the crash landing after clean pipeline teardown
pointed at use-after-free rather than DMA. The IOVA argument presumably fails
because the addresses the VE actually emitted landed in DRAM anyway (aperture
base, or truncation) — but the point is that **neither objection was a
measurement**, and the one-line experiment that settled it was available the
whole time.

## Candidates, after a round of cheap live checks (2026-08-09)

All of these were checked on the running board with no flash cycle. Two of the
four are refuted, and **read the built artifact, not the DTS comment** — the
comments lie about this node twice.

**REFUTED — "the SRAM property is missing."** The DTS comment says *"Testing
without SRAM property first - may be optional on H713"*. The **built DTB has
`allwinner,sram = <0x1a 0x01>`**, and both `1a00000.sram` and `28000.sram` are
bound platform devices. The comment is stale relative to its own node.

**REFUTED — "a foreign interrupt drives cedrus into a freed context."**

```
327:   0  0  0  0   GICv2 107 Level   1c0e000.video-codec
```

hwirq 107 = SPI 75 + 32, so the IRQ is wired exactly as declared, is exclusively
cedrus's, and has fired **zero times**. The handler has never run, so it cannot
be completing work against freed state. *What survives* is the weaker form: a
count of 0 is equally consistent with "SPI 75 is simply not the VE's interrupt on
H713", and the DTS itself flags the divergence (*"IRQ: SPI 75 (H6 uses SPI 89)"*).
Zero is the expected reading either way, so this measurement cannot separate them.

**NARROWED — register-map divergence.** Full window dump with runtime PM forced
on (`echo on > .../power/control`, status `active`), via `tools/video/vedump.py`:

```
0000: c0000007 00000300 00000000 00000000
0010: 00000000 00000000 00000000 00010000
0030: 00000200 ...        0040: 0000000f ...
0080: 00001c55 000fffff 00008000 00000000
00e0: 00033110 00012011 00000000 00000000
00f0: 00000000   <- VE_VERSION
*
1000: c0000007 00000300 ...   <- identical to 0x000
# 12 non-zero rows of 512
```

Three facts:

- **The VE is present and reachable at the H6 base.** `0xC0000007` at `VE_MODE`
  is a plausible value, not a bus-error pattern.
- **The block aliases every 0x1000.** `0x1000` mirrors `0x000` exactly, so the
  decoded region is 4 KB while the DTS declares `reg = <0x01c0e000 0x2000>`.
  Only `0x000..0x0ff` decode while idle, which is expected — the H.264 engine
  bank at `0x200` appears only once `VE_MODE` selects it.
- **`VE_VERSION` (0xf0) is genuinely 0** on live, clocked, de-reset silicon.

**But it is NOT the fault, and an earlier revision of this page was wrong to
imply it.** `VE_VERSION` appears in mainline cedrus **only as a `#define` in
`cedrus_regs.h`** — `grep -rn VE_VERSION drivers/staging/media/sunxi/cedrus/`
returns the definition and its shift, and no reader. The driver never consults
it. So the zero is a real divergence signal about the silicon and a useful
fingerprint, and it explains nothing about the failure.

**Clock and reset management is correct** — worth recording, because it removes a
whole class of suspicion. CCU `0x0200169c` (gates in `[2:0]`, resets in
`[18:16]`) reads `0x00000000` when the VE is runtime-suspended and `0x00050005`
when active: BUS_VE and BUS_VE3 both gated on and out of reset, exactly as
patch 0022 intends.

**Do not read `0x01c0d000` (the AV1 block).** The same word shows AV1 gated
**off** with its reset **asserted** (bit 1 clear, bit 17 clear) — precisely the
condition the reset-before-gate rule says wedges the interconnect. Check
`0x0200169c` before probing anything in the VE family; the CCU is always clocked,
so that read is free.

**CLOSED — buffer sizing.** Not a bug. Cedrus sizes `NV12_32L32` correctly
(`ALIGN(width,32)`, `ALIGN(height,32)`, chroma `ALIGN(height,64)/2`), and the
hardware honours it: the tiled run produced exactly 122,880 bytes/frame for
320x240 (= `320 * ALIGN(240,32) * 3/2`). The 16-row alignment on the plain `NV12`
path is also fine — forcing `format=NV12` yields bit-exact 320x240 output. Both
paths are correct; `a01-320x256`/`a02-1280x736` were generated to test this and
were not needed.

**The zero IRQ count was the real tell, and it was misread.** With the IOMMU
attached the VE never raised SPI 75 — because it never successfully completed a
job, not because the IRQ number was wrong. Once the IOMMU was gone the same SPI
75 worked fine for 60-frame 1080p decodes. A zero interrupt count means "the
device never finished", which is a symptom, and it was briefly treated as
evidence about the interrupt *number*.

**Restore `power/control` to `auto` after any such probe.** Leaving the VE forced
on keeps it clocked indefinitely and changes the state every later test starts
from.

## DECD enabled — probes clean, display untouched (2026-08-12)

The vendor driver (patch 0013) is the only way to reach zero-copy, because
userspace can neither resolve a V4L2 buffer to a physical address nor program
display registers. Enabled and loaded on hardware:

```
decd 5600000.dec: tvtop link unavailable (-19); continuing unordered
decd 5600000.dec: reconstructed decd probed
```

| check | result |
| --- | --- |
| `/dev/decd` | created, char 243:0 |
| AFBD registers after load | `ctrl=03001901 stride=00001400 src=6c100000` — **identical to before** |
| panel | boot logo still displayed (operator-confirmed) |
| IRQ | `GICv2 142` = SPI 110, named `decd`, count 0 (requested then disabled, as probe intends) |

**Built as a module on purpose.** `dec_probe()` calls `pm_runtime_enable()` with
no `get`, so `dec_enable()` — which sets the AFBD clock rate, writes `0xffffffff`
into TVTOP `0x05700008..0x1c` via `dec_reg_top_enable()`, and calls
`dec_reg_mux_select(regs, 2)` — only runs on runtime resume. Loading is therefore
observable and reversible; none of that has fired yet.

### Where our DT deliberately differs from the vendor's

Checked against the stock DTB rather than assumed:

| property | vendor | ours | why |
| --- | --- | --- | --- |
| `reg` order | `0x5700000` then `0x5600000` | `0x5600000` then `0x5700000` | **Copying the vendor here would break it.** The driver does `afbd = of_iomap(node, 0)`. Every measurement says AFBD is at `0x05600000`: the flag bytes at `+0x10/11/13` match the vendor's linear branch, vblank at `+0xc0` ticks at 16.74 ms, and plane addresses at `+0x70/84` rendered colour bars |
| `clock-frequency` | 200 MHz | **100 MHz** | Three figures exist: vendor 200, U-Boot comments 600, `clk_summary` reports the live clock as 100. `dec_enable()` does `clk_set_rate()`; 100 makes it a no-op under a running panel. Raise once it works |
| `iommus` | `<&mmu_aw 2 0>` | absent | our IOMMU node is inert; attaching cedrus to it corrupted kernel memory |
| TVTOP | shipped and enabled | disabled | isolation — see patch 0033 |
| node children | `simple-bus` containing `mipsloader@3061000` | none | `of_platform_populate()` in probe would instantiate it; U-Boot already owns the MIPS side |

### Patch 0033: the TVTOP link, guarded at compile time

`sunxi_tvtop_client_register()` returns `-EPROBE_DEFER` without TVTOP, so DECD
would defer forever. Its whole body is a `device_link_add()` for ordering — no
hardware. **Merely ignoring the return value is not enough:** the symbol is an
`EXPORT_SYMBOL` owned by the tvtop module, so `depmod` records a dependency and
`modprobe sunxi-decd` pulls TVTOP in anyway. The guard has to be
`#if IS_ENABLED(CONFIG_SUNXI_TVTOP)` with a stub. Verified: `depends:` is empty
and no tvtop symbols remain in the `.ko`.

TVTOP is kept off because its probe owns `CLK_PANEL`, `CLK_DEINT`,
`CLK_SVP_DTL`, `CLK_BUS_DISP` and `RST_BUS_DISP` — the display resources U-Boot
programs and that the handoff depends on. A second owner of those clocks in the
same session that first enables DECD would confound any failure between them.

## Milestones

### M1 — the decoder decodes (the gate) — PASSED, see above

Flash the bring-up rootfs, then, in order: confirm `v4l2-ctl --list-formats-out`
advertises the stateless codecs; run `v4l2-compliance`; decode `v01` with
`v4l2slh264dec`; compare the output against the NV12 reference. Then climb the
ladder.

Scoring is per-vector and the ladder is the instrument: v01 failing and v03
failing mean completely different things.

**This is a gate, not a formality.** If VE3 diverges from the H6 register map,
it is found here for the cost of one boot, before anything is built on top.

### M2 — decoded video on the panel — DONE 2026-08-09

**Decoded H.264 plays on the projector panel, with correct colour and geometry,
at roughly real time.** Operator-confirmed on hardware. No kernel driver, no DRM:
plain userspace through `/dev/mem`.

The whole chain, with no intermediate file:

```
mkfifo /tmp/v.fifo
gst-launch-1.0 -q filesrc location=clip.h264 ! h264parse ! v4l2slh264dec \
  ! video/x-raw,format=NV12 ! filesink location=/tmp/v.fifo &
./h713-present nv12 /tmp/v.fifo
```

Confirmed in order, each before the next was believed:

| step | result |
| --- | --- |
| `/dev/mem` mmap of the `no-map` scanout under `STRICT_DEVMEM` | works — the reasoning in the header of `h713-present.c` holds |
| AFBD registers from userspace | `ctrl=03001901 stride=00001400 src=6c100000`, matching the handoff exactly |
| `fill` — solid colour, one commit | 342.8 MB/s, commit ok in 16367 us (one frame at 59.75 Hz) |
| `bar` — synthetic moving bar, double-buffered | **59.40 fps**, 0 timeouts, operator saw a red bar sweeping on blue |
| `nv12` — decoded video | 300 frames, 0 timeouts, **operator confirms the picture is correct** |

**The synthetic bar came first, deliberately.** It is decoder-independent, so a
decoder fault cannot masquerade as a display fault — the same discipline the
display bring-up used with `fb-anim`.

### Performance: the hardware was never the limit

| version | fps | read | convert | blit | commit-wait |
| --- | --- | --- | --- | --- | --- |
| first working | 11.95 | — | 84.0 | — | — |
| staging buffer + 4 threads | 19.65 | 31.71 | 10.99 | 4.12 | 4.06 |
| raw `read()` + bigger pipe | **28.33** | 14.83 | 8.68 | 3.82 | 7.96 |

Against a 30 fps clip. Both bottlenecks were bugs in the presenter, not silicon:

- **A `volatile` destination in the conversion loop.** Writing straight into the
  mmap'd framebuffer through a volatile pointer forbids vectorising or merging
  stores — one scalar store per pixel, 921,600 times, 84 ms/frame. Converting
  into an ordinary cached staging buffer and doing one bulk copy is **7.6x**
  faster, and the bulk copy also beats the per-pixel volatile fill (3.8 ms vs
  12 ms for the same bytes).
- **stdio's 4 KB buffer on a pipe.** `fread()` turned each 1.38 MB frame into
  ~337 blocking reads ping-ponging with the writer: 31.7 ms/frame. Raw `read()`
  in frame-sized gulps plus `F_SETPIPE_SZ` halved it.

**For scale, the actual hardware:** the VE decodes this clip at **268 fps**
(`gst-launch ... ! fakesink`, 300 frames in 1.117 s) with `ve-core` at 600 MHz —
the top rate in the vendor's OPP table. The panel commits at 59.7 Hz. Both have
enormous headroom; every limit hit so far was userspace glue.

### The 28 fps ceiling is the cross-process handoff, not decode or scanout

Measured 2026-08-10. **Fed from a page-cached file instead of a pipe, the same
code runs at the panel's refresh rate:**

```
from page-cached file:  58.93 fps   read 0.13  convert 7.48  blit 5.83  wait 3.53
live through the FIFO:  28.17 fps   read 11.87 convert 11.05 blit 3.80  wait 8.78
```

convert + blit + wait = **16.8 ms**, one frame period at 59.7 Hz. The
presentation path is **vsync-limited**, not compute-limited.

The live figure is not a limit of either end: the VE decodes this clip at
**268 fps** and presentation sustains **59 fps**. What costs ~19 ms/frame is
moving 1.4 MB between two processes and the contention that creates. Note that
*every* stage got faster without GStreamer alongside — conversion 11.05 -> 7.48,
commit-wait 8.78 -> 3.53 — so it is contention, not just the read.

**Two optimisations were tried and neither helped**, which is what located the
real cause:

- **A reader thread** (ring of 3, prefetching during convert/commit):
  28.33 -> 28.14 fps. It moved 2 ms out of `read` and straight into `convert`.
- **Conversion thread count**, swept 2/3/4: **28.35 / 28.16 / 28.17 fps.** As
  threads rise `convert` rises and `read` falls by the same amount, total pinned
  at ~35.3 ms. Stages trading time against a fixed ceiling is the signature of a
  shared resource, not of CPU shortage — and it is why more parallelism did
  nothing.

A memory-bandwidth explanation was proposed for that ceiling and **refuted** by
the page-cached run: if DRAM were the limit, removing the pipe could not have
doubled the frame rate while *also* making conversion faster.

**So do not micro-optimise the conversion.** NEON would attack 7.5 ms of a
16.8 ms budget that is already vsync-bound when fed properly. The win is
architectural: decode and present in **one process**, using V4L2 with dmabuf so
the decoder's own buffer is what gets presented, with no copy between them. That
is also the natural shape of whatever M4 becomes.

Remaining headroom, best first:

1. **Single-process V4L2 + dmabuf** — removes the handoff entirely. The measured
   headroom says this reaches vsync.
2. **Scan out YUV directly** — would kill convert *and* blit (13.3 ms), but see
   the negative result below: not available on this plane.
3. **NEON the conversion** — last, and only if something above changes the
   picture. Currently it optimises a stage that is not the constraint.

### Tearing: RESOLVED 2026-08-11 — double buffering works; the "defect" was a bad baseline

**Read this before the section below, which is kept as the trail and whose
conclusion is wrong.** The workload-matched control settles it:

| run | is the DISPLAYED buffer written? | rows with no bar |
| --- | --- | --- |
| idle panel, nothing running | no | 0.74% |
| **`bar-noflip`: full workload, scanout pinned to a buffer written once** | **no** | **23.03%** |
| double-buffered, no fixes | no | 30.46% |
| + post-flip vblank wait | no | 22.14% |
| + memory barrier | no | 16.91% |
| **single-buffered** | **yes** | **59.38%** |

`bar-noflip` does the identical per-frame work -- same two-phase fill, same
commit, 59.71 fps -- but fills `fb_back` while scanout stays pinned to an
`fb_front` written once. The displayed surface **cannot** be corrupted, and the
metric still reads **23.03%**. So ~23% is this instrument's floor *for a run
doing this workload*, not corruption.

Against that floor every double-buffered variant is at or below it, and only the
single-buffered control clearly exceeds it. **Double buffering works on the Linux
path.** M2's original claim was right; the retraction of it was wrong.

**The mistake, and it was made three times: a baseline that differed in more than
one variable.** The idle panel differs from a real run in motion *and* in whether
the fill/commit cycle runs at all. The motion confound was spotted and
controlled (`BAR_STEP=0`); the workload confound was not, so 0.74% was never the
right floor and every number built on it was misread. Five mechanisms were then
investigated against a phantom.

**What is real:**
- Single-buffered tearing: 59.38% vs a 23.03% floor. Genuine, and the reason
  double buffering exists.
- The metric is only trustworthy for large differences. 25 vs 30 vs 22 vs 17 are
  all inside the floor's variation, which also moves with camera framing
  (interior rows/frame ranged 1227-1758 across these recordings).
- The barrier in `flip_to()` and the vblank work are kept: both are *correct*
  independent of this, and the vblank register is what a DRM driver needs. But
  neither should be credited with fixing a defect that was not there.

**Rule earned:** a control must match the run in every respect except the one
variable under test. "Nothing is running" is not the baseline for "something is
running".

### The original investigation (conclusion WRONG, kept as the trail)

Previously this section said tearing was unmeasured and that double buffering was
"proven". **The proof was from the U-Boot path (test_37) and was carried across
without retesting.** Measured here, the Linux path corrupts a large fraction of
scanned rows.

| run | motion | fill+swap running | rows with no bar |
| --- | --- | --- | --- |
| `bar 1`, program exited | none | **no** | **0.74%** |
| `BAR_STEP=0 bar-vs` | **none** | yes | **30.46%** |
| `bar-vs` (vblank-locked) | yes | yes | 27.84% |
| `bar` + `EXTRA_VSYNC` | yes | yes | 31.30% |
| `bar` (as shipped at M2) | yes | yes | 25.65% |
| `bar-sb` single-buffered | yes | yes | 59.38% |
| `BAR_STEP=0 bar-vs` + `BAR_LATCH_WAIT` | none | yes | **22.14%** |

**The zero-motion control is the one that establishes it.** It differs from the
idle panel *only* in whether the fill/swap cycle runs — identical content every
frame, nothing to tear in the image itself — and it goes 0.74% -> 30.46%. So the
raster genuinely catches surfaces blued but not yet barred: **the displayed
buffer is being written.**

**Getting to a trustworthy number needed three controls, and two were missing at
first:**

- **Positive control** (`bar-sb`, single-buffered): without a run the metric is
  known to flag, a low reading cannot be told from an insensitive metric.
- **Negative control** (`bar 1`, idle): without it, 25.65% cannot be told from
  the metric's own detection floor.
- **Zero-motion control** (`BAR_STEP=0`): the idle control changed *two*
  variables at once — motion and activity. A moving red bar at ~955 px/s smears
  on an LCD and the metric needs `redness > 40` over a contiguous run, so motion
  alone could plausibly have produced the whole effect. It does not, but that
  was an assumption until measured.

**The two-phase fill is load-bearing for the metric.** `fill_bar()` must blue the
whole surface and then draw the bar. A single-pass bar-or-blue fill leaves every
row carrying a bar at some position, so the metric reads 0% whether or not the
panel tears — a meaningless pass. This was originally single-pass and was fixed
before any of these numbers were taken.

### Four mechanisms tested, none sufficient

Each manipulation was verified to have actually taken effect before its result
was credited — the failure mode this project already knows about.

| hypothesis | test | verified by | result |
| --- | --- | --- | --- |
| the flip register does not work | `flip-test`, two solid colours | panel alternates red/green; `src` reads back | **refuted** |
| buffer reused before scanout finished | `EXTRA_VSYNC=1` | frame rate 59.53 -> 29.82, a clean halving | **refuted**, 31.30% |
| swapping at an arbitrary scan phase | `bar-vs`: real vblank + dirty latch | 0 vblank misses, 59.49 fps | **refuted**, 27.84% |
| one-frame flip latency vs two buffers | `BAR_LATCH_WAIT=1` | frame rate 59.46 -> 29.88 | **partial**, 30.46 -> 22.14% |
| the flip lands late | `latency-probe` | panel: red -> green -> red | **refuted**, white never appears |

**`latency-probe` is the one measurement here that needs no metric and no camera
analysis** — it uses the fill as its own probe. Flip to the back buffer, then
immediately repaint the *front* buffer white: if white ever reaches the screen,
the front was still live when written, which is the corruption caught in the act.
It stayed green. Scope: `commit()` waits ~10 ms before the repaint, so this
proves the flip lands within ~10 ms rather than within one 16.74 ms frame — but
`bar-vs` has the same commit between its flip and its next fill, so by identical
reasoning its fills do target a buffer that is no longer live.

It also supersedes `flip-test` as evidence. That showed clean red/green
alternation but across **5-second dwells**, which only proves the flip works on a
long timescale and says nothing about a 16.74 ms frame.

**So the mechanism is still unknown**, and every straightforward explanation is
now eliminated by measurement rather than by argument. What remains untested is
whether the corruption involves our framebuffer writes at all — the DE or panel
may have internal line buffering that the "rows with no bar" metric is reading.
Distinguishing that needs per-buffer content signatures, not another fix attempt.

### What the vendor binaries gave up (and it is worth keeping)

Asked whether the deconstructed board-B binaries could help — they could, and
this is the durable result even though it did not fix the number:

- **The vendor swaps buffers inside the vsync IRQ**, not by polling:
  `dec_vsync_handler` -> `dec_frame_manager_handle_vsync` -> `sync_cb`
  (`dec_sync_frame_to_hardware`).
- **A real vblank register: `0x056000c0` bit 0**, from `dec_irq_query()`
  (`workaround + 96`, `workaround = afbd + 0x60`), acked by writing bit 0 back.
  **Measured: 20/20 events at 16.74 ms** against the panel's computed 16.75 ms
  period, 0.06%. This is a genuine vsync source and is exactly what a DRM driver
  would need.
- The vendor ANDs it with `+0xc4`, which reads **00** on our configuration — an
  interrupt-enable we never set. Transcribing the vendor condition literally gave
  300 vblank misses out of 300; poll `0xc0` alone.
- **Config changes are latched by the dirty bit at `0x0560006c`**, written after
  the address. `flip_to()` never did this.

**`AFBD_STATUS` bit 1 was assumed to be vsync since M2 and never checked.** It
correlates with the frame period — 59.4 fps, 16.75 ms totals — which is why it
went unquestioned. Correlating with the frame period is not the same as being the
frame boundary.

### Where to take it

**Not a fifth hypothesis.** The next step needs a different instrument: mark each
buffer with a distinct signature so a captured frame reports *which* buffer was
on screen and how stale it was, rather than inferring mechanism from an aggregate
percentage.

**And probably not in this tool at all.** `h713-present` is a `/dev/mem` poke;
correct buffer management belongs in the DRM driver where page-flip and vblank
are first-class, which is the M4 decision. The measured vblank register above is
the piece that work will need. A third buffer — the obvious fix if the latency
theory is right — needs a larger `uboot-scanout` reservation and therefore a
kernel change, so it is not a userspace tweak either.

**What this does not undermine:** the throughput results stand. 58.93 fps
vsync-limited presentation, 268 fps decode, bit-exact frames. Those were never
evidence about tearing, and tearing was never evidence against them.

### Direct YUV scanout — RETRACTED. Claimed 2026-08-12, refuted 2026-08-14.

**This section's conclusion is wrong and is kept as trail.** Control A on
2026-08-14 ran the very command below from a cold boot and got the 4x-repeat
greyscale this section says it fixed — see
[the refutation](#direct-yuv-refuted-2026-08-14).

The retraction it performs — of the 2026-08-09 "wrong plane for YUV" inference —
is itself withdrawn. That inference was reinstated by the vendor's register
table, which never programs any of the registers below.

**How this happened is worth more than the result.** The `test_41`
misattribution is described a few paragraphs down, in this same section, as the
reason a whole A/B was re-run from a cold boot. The claim written directly
beneath that warning was then accepted without the control it prescribes. A
register readback (`+0x10=03000310`) was treated as evidence the *picture* had
changed; it only ever showed the register had.

**The original text follows.**

**Confirmed on hardware:** an NV12 frame renders correctly on the panel with no
CPU colour conversion, using the vendor's plane-address path.

```
saved:  Y[0]=00000000  C[0]=00000000          <- both plane registers empty
set:    Y=6c100000  C=6c1e1000  flags=03000310  commit ok
```

`h713-present yuv2 <file.nv12> 3 0` — format code 3 (`fmt_attr_tbl` row index for
8-bit YUV420), plane strides 1280, and crucially:

| register | value | meaning |
| --- | --- | --- |
| `0x05600011` | `3` | format selector (table row index) |
| `0x05600040`/`44` | 1280 | plane strides |
| **`0x05600070`** | **Y address** | `dec_reg_set_address` idx 0, `base = afbd + 0x60`, `+16` |
| **`0x05600084`** | **C address** | same, `+36`; here Y + 1280*720 |
| `0x0560006c` | 1 | dirty latch |

**Why the earlier attempt failed, and it was not the hardware.** The 2026-08-09
attempts set the format byte and the strides but kept feeding the single packed
source at `0x05600178` — the **RGB data path**. A YUV format needs two plane
addresses. Our own register dump showed `0x05600070`/`0x05600084` reading zero,
which was noted at the time and dismissed as "a parallel mechanism we do not
use"; it is precisely what makes YUV work.

The conclusion recorded then — "the plane is an OSD/UI channel and Allwinner UI
channels are RGB-only" — was an **inference invented to explain a null I had
produced myself**. It was labelled as inference, which is something, but it was
still wrong, and it was committed as a reason to stop.

**Found by reading the vendor driver rather than by more experiments**, on the
operator's suggestion to establish the vendor's direction first.
`dec_sync_frame_to_hardware()` -> `dec_reg_set_address()` writes
`item->y_addr`/`item->c_addr` into those registers, and those come straight from
`DECD_IOC_FRAME_SUBMIT`'s `y_phys`/`c_phys`/`image_fd`.

### The vendor never reads the decoded frame on the CPU

This is the important architectural consequence, and it was measured
independently before the YUV result:

```
A  fakesink, never touches the buffer     0.255 s   sys 0.034
B  tmpfs file (real read + copy)          1.079 s   sys 0.901
C  FIFO                                   1.079 s   sys 0.882
   raw pipe bandwidth (dd, 419 MB)        423 MB/s
```

**B and C are identical**, and the pipe on its own runs at 423 MB/s — so the
handoff is nearly free and the cost is the **CPU reading the decoder's output
buffer** at roughly 48 MB/s. Cedrus CAPTURE buffers are CMA/dmabuf and are not
read through the cache.

**That invalidates the plan this section previously implied.** "Single-process
V4L2 + dmabuf to remove the handoff" was aimed at a cost that measurement shows
is small. Merging processes removes a nearly free copy and leaves the expensive
read exactly where it is. The vendor's design avoids the read entirely: decode
into a buffer, submit its physical addresses, let the display consume it.

**So the target pipeline is:** decode to a CMA/dmabuf buffer, write its Y/C
physical addresses to `0x05600070`/`0x05600084` with format 3 and the dirty
latch, commit. That removes the CPU read (~48 MB/s), the conversion (7.5 ms) and
the blit (3.8 ms) together.

### The original attempts (conclusion WRONG, kept as the trail)

The prize was killing the CPU colour conversion (convert 8.7 ms + blit 3.8 ms =
12.5 ms/frame, most of the per-frame budget). **Three variants were tried on
hardware and all fail identically**, `h713-present yuvtry` with the `testsrc2`
colour-bar frame (photos in `local/lcd-photos/test_39/`, `test_40/`):

| attempt | result |
| --- | --- |
| format byte only | picture correct at the bottom, grey band ~1/3 down, black above |
| format + all three strides at 1280 | picture repeats **4x horizontally**, near-greyscale |
| format + strides + config latch | **identical** — no change at all, stable across 60 s |
| the same, re-run from a **clean boot** | **identical again** (`test_42` reference vs `test_43` test, same session, same camera position) |

**The last row exists because provenance matters.** A photo in `test_41` showed
correct colour bars and could not be attributed to a command — it was equally
consistent with `yuvtry` succeeding or with the ARGB restore that follows it.
Rather than publish a negative resting on that, the whole A/B was re-run from a
cold boot with the reference shot first. `test_41` was the restore. Four
attempts, one outcome.

**The 4x repeat is arithmetic, and it is the whole diagnosis.** 4 bytes/pixel
divided by 1 byte/pixel is 4: with the stride at 1280 *bytes*, one display row
consumes 320 ARGB pixels, so four source rows pack into each display row. **The
fetch is still 4 bytes/pixel — the format never changed.** The greys are the Y
plane being read as RGB components.

**And the write was not lost.** The readback prints `+0x10=03000310`, i.e. byte
`0x11` holds `3` after the write and after the latch. The register accepts the
value, retains it, and the fetch does not change. So this is not a shadowing or
sequencing problem, which is what the latch attempt was testing.

**Most likely explanation — inference, not proven.** The plane this path drives
is an **OSD/UI channel**, and on Allwinner display engines UI channels are
RGB-only; YUV formats belong to **VI (video input) channels**. If that holds
here, no value written to an AFBD format byte can produce YUV on this plane, and
the change needed is to route through a VI channel in the mixer — which means
owning the DE configuration that currently arrives wholesale from the vendor's
`LogoRegData` replay. That is M4-scale work, not a poke.

**What was established anyway, and is durable:**

- `0x05600011` is a real format selector: it accepts and retains values.
- The code is the **`fmt_attr_tbl` row index**, not the `DEC_FORMAT_*` id. Three
  independent points fit: row 0 = RGB888 (matching the live ARGB path's `0`),
  row 6 = YUV420 10-bit and row 7 = AV1 10-bit (matching the vendor's writes of
  `6` and `7`). By that mapping 8-bit NV12 is row **3**.
- There are **three** stride registers, not one: the channel stride at
  `0x05600170` plus global plane strides at `0x05600040`/`0x44`. The first
  attempt's grey band was luma read at the wrong pitch through the two that were
  missed.
- `0x0560006c` is the config latch (vendor `dec_reg_set_dirty()`, and
  `dec_reg_bypass_config()` writes 1 there right after changing a config byte).
- `0x05600048`/`0x4c` already hold NV12-shaped plane geometry (1280x720 and
  1280x360), and the vendor's Y/C plane address registers at `0x05600070` /
  `0x05600084` read **zero** on our path — we feed AFBD through the channel
  block's single source at `+0x178` instead.

**Recommendation: do not chase this further as a register experiment.** Take the
cheap software wins first (overlapped read, NEON), which clear 30 fps with
margin, and revisit YUV when M4 decides between DECD and a DRM plane — at which
point the mixer channel type is a design input rather than something to poke.

**Method note.** Both diagnoses came from photographs, not the console. Every one
of these three runs reported success at every step: format written, strides
written, latch written, commit OK, registers restored. The panel said otherwise
each time, and the *specific* defect — band position, repeat count — is what
identified the register. This is the display bring-up's "prefer the photograph to
the metric" rule earning its place again.

### M3 RESULT — 2026-08-14. Sustained 28.3 fps, and the cap is the decoder buffer read.

**The CPU-conversion path cannot sustain 30 fps 720p.** Measured over 2700
frames (90 s of content, `v04-1280x720-high` concatenated 45x), four
independent runs, no thermal degradation (55 -> 71 C, fps flat start to end).

| run | fps | read | convert | blit | commit-wait |
| --- | --- | --- | --- | --- | --- |
| 2700 frames, 4 threads | **28.30** | 12.21 | 10.80 | 3.85 | 8.46 |
| 900 frames, 3 threads | 28.28 | 12.19 | 11.00 | 3.81 | 8.30 |
| 900 frames, 2 threads | 28.41 | 12.94 | 9.73 | 3.61 | 8.85 |
| 900 frames, 1 thread | 28.14 | 5.03 | 18.99 | 3.68 | 7.77 |

**`CONV_THREADS` is irrelevant** — the doc's standing suggestion to sweep it is
now answered. fps is flat within 1% across 1-4 threads; time only moves between
phases (1 thread: `read` 12.2->5.0, `convert` 10.8->19.0, total unchanged). That
is the signature of an external pacer, not a CPU bottleneck.

### What the pacer is

| pipeline | rate | what it proves |
| --- | --- | --- |
| `! fakesink` | **311 fps** | the VE has 10x headroom, sustained |
| `! filesink /dev/null` | **311 fps** | identical — `/dev/null` never copies, so the pixels are never touched |
| same, `sync=false` | 311 fps | GStreamer is **not** clock-pacing; that hypothesis is dead |
| `! filesink fifo` + `cat > /dev/null` | **31.7 fps** | a consumer doing NOTHING but draining. 3.73 GB in 85.1 s = **43.8 MB/s**, and 22.1 s of it is system time |
| full presenter | 28.30 fps | our entire convert+blit+present adds only ~3.7 ms/frame on top |

**The cap is the CPU read of the decoder's CMA output buffer**, at ~44 MB/s —
the same figure the 2026-08-12 A/B/C found (48 MB/s) and the reason `fakesink`
and `/dev/null` look fast: neither ever touches a pixel. It is charged to
whoever first reads the buffer, which is the kernel copying into the pipe,
before our code runs.

The clean A/B on our own side: the identical presenter reading page-cached NV12
runs at **51.62 fps** (`read` 0.52 ms) versus 28.30 fps from the decoder — same
conversion, same blit, same commit. Only the cost of obtaining pixels differs.

### The verdict, and what it decides

- **30 fps content fails by ~6%** (28.3 sustained). Not a stutter to tune away.
- **A perfect zero-cost consumer would still only reach 31.7 fps** — 5% of
  margin over 30, with a 44 MB/s wall behind it. Optimising our presenter
  cannot fix this; it is worth 3.7 ms/frame in total.
- **This justifies the zero-copy work.** Not touching the decoder's output on
  the CPU removes the 44 MB/s bottleneck, the conversion and the blit together,
  leaving the vsync ceiling (58.9 fps) as the limit.
- **Cheaper thing to try first:** the buffer is uncached because of how the V4L2
  CAPTURE buffers are mapped. If a cached mapping is possible, the same
  architecture gets real-time without any plane work. Worth an hour before
  committing to the `ge2d_dev.ko` RE.

### The GPU is bound and nobody noticed (2026-08-14)

Checked because M3 makes the CPU read the thing to eliminate, and the plane RE
is not the only way to eliminate it:

```
panfrost 1800000.gpu: clock rate = 864000000
panfrost 1800000.gpu: mali-g31 id 0x7093 major 0x0 minor 0x0 status 0x0
panfrost 1800000.gpu: shader_present=0x1 l2_present=0x1
[drm] Initialized panfrost 1.4.0 for 1800000.gpu on minor 0
```

**Mali-G31 Bifrost, bound by mainline panfrost, auto-loaded at boot.**
`/dev/dri/card0` and `renderD128` have existed every session. `panfrost_dri.so`,
`libEGL_mesa` and `libgbm` are all in the rootfs. The only missing piece is
`libGLESv2` (Debian `libgles2` / `libgles-dev`, ~100 KB — seconds over serial;
apt's lists do not have it, so send the .deb).

**Why this matters more than the plane RE.** A GLES pass that samples the
decoder's dma-buf as an NV12 texture and renders into the scanout region:

| M3 cost | GPU path |
| --- | --- |
| 44 MB/s uncached CPU read (the actual cap) | gone — the GPU reads over its own DMA path |
| 10.8 ms convert | gone — YUV->RGB in hardware |
| 3.85 ms blit | gone — renders straight into the target |

It targets the **ARGB scanout path that already works at 58.9 fps**, so it needs
no format field, no second plane, and no topology change — precisely the things
the plane hunt proved unreachable. `DECD_IOC_MAP_LINEAR_BUFFER` already wraps a
physical region as a dma_buf, which is the render target.

Capacity is not a concern: 921,600 px at 30 fps is 27.6 Mpixel/s of
sample-and-convert on a core clocked at 864 MHz, and ~153 MB/s of traffic
against a bus that already sustains 350 MB/s of CPU fill.

**Sequencing:** do this before `ge2d_dev.ko`. Its next checkpoint is one
session (send `libgles2`, import a decoder dma-buf, render one frame); the plane
RE's success chain is three stacked unknowns — find the plane-open sequence,
make it work against a U-Boot-initialised pipeline, then discover whether DECD
can feed it at all given its registers are not in the scanout path.

### GLES video pass: the import works, 0.64 ms/frame (2026-08-15)

**`PASS: GPU sampled a cedrus dma-buf and converted it`.** The question M3 left
open — can the GPU read the decoder's output without the CPU touching it — is
answered yes, on a real cedrus buffer.

```
cedrus CAPTURE: 1280x720 NV12 bytesperline=1280 sizeimage=1382400
EXPBUF ok: dmabuf fd=4
EGLImage from cedrus dma-buf: ok
bound as GL_TEXTURE_EXTERNAL_OES: ok
  red   got 255, 24,  0   ok
  green got   0,216,  0   ok
  blue  got   0, 15,255   ok
100 NV12->RGB passes at 1280x720: 63.5 ms (0.64 ms/frame, 1574 fps equivalent)
```

Instrument is `tools/video/gles-nv12.c`. The buffer is obtained with
`VIDIOC_REQBUFS` + `VIDIOC_EXPBUF` on `/dev/video0` — a genuine cedrus CAPTURE
allocation, because a buffer from anywhere else would not answer the question.
Neither ioctl needs streaming, so the import path is testable without also
driving a stateless decoder. The CPU fills it once as a test harness only.

| cost | CPU path (M3) | GPU |
| --- | --- | --- |
| read decoder output | ~31 ms (44 MB/s uncached) | **0** — GPU DMA |
| YUV->RGB convert | 10.8 ms | **0.64 ms** (whole pass) |
| blit to scanout | 3.85 ms | 0 once rendering direct |

`samplerExternalOES` applies the YUV->RGB itself, so the conversion that costs
10.8 ms of CPU is a texture unit's ordinary work.

**Capability probe** (`tools/video/gles-probe.c`), all present:
`EGL_EXT_image_dma_buf_import`, `..._modifiers`, `EGL_KHR_image_base`,
`GL_OES_EGL_image_external` (+`_essl3`), `GL_OES_rgb8_rgba8`, and
`EGL_MESA_image_dma_buf_export`.

**Two traps worth keeping.** `VIDIOC_S_FMT` on CAPTURE alone yields the 16x16
minimum (384 bytes) — a stateless decoder derives CAPTURE geometry from the
coded OUTPUT format, so `V4L2_PIX_FMT_H264_SLICE` must be set first. Writing a
1280x720 pattern into that 384-byte mapping segfaulted, and with stdout
redirected and fully buffered the log was **empty**, hiding every printf up to
the crash. Geometry now comes from the driver's readback, and the tool sets
`setvbuf(_IONBF)`.

### THE ZERO-COPY PATH WORKS — 59.73 fps, 2026-08-15

**Decoded H.264 through the GPU to the panel, with the CPU never touching a
pixel.** `tools/video/gles-play.c`:

```
decoded 1280x720 NV12, planes=2 memories=1 fd=12
2700 frames in 45216 ms (59.71 fps), 0 commit timeouts
  mean gpu 4.01 ms, commit-wait 12.60 ms
```

**Operator-confirmed on the panel: moving colour bars with the sweeping
diagonal**, for the full 45 s. That check is the point — the frame rate is
identical whether the picture is right or garbage, and most of this file's
history is about that distinction.

Against M3's **28.30 fps** on the CPU path. 59.71 fps is the vsync ceiling
(58.93 fps measured independently), so the limit is now the panel rather than
the 44 MB/s uncached read. Flat across three runs of increasing length —
60 frames 59.31, 600 frames 59.73, 2700 frames 59.71 — so no thermal or
buffer-pressure droop.

The chain: VE decodes into a CMA buffer -> GStreamer hands over that buffer's
dma-buf FD -> GPU imports it as an NV12 `EGLImage` and samples through
`samplerExternalOES` -> renders into a scanout slot imported from
`sunxi-scanout-dmabuf` -> `AFBD_SRC` points at the slot the GPU just filled ->
commit. Double buffered across `0x6c100000` / `0x6c500000`.

| stage | CPU path (M3) | zero-copy |
| --- | --- | --- |
| read decoder output | ~31 ms (44 MB/s uncached) | **0** |
| YUV->RGB convert | 10.8 ms | in the 4.1 ms GPU pass |
| blit to scanout | 3.85 ms | **0**, renders in place |
| **result** | **28.30 fps** | **59.73 fps** |

#### The (memory:DMABuf) caps feature is a red herring

Forcing `video/x-raw(memory:DMABuf)` looks like the way to make the decoder
hand out FDs. It is not, and it actively breaks the pipeline:

```
ERROR v4l2codecs-h264dec: DMABuf caps negotiated without the mandatory
                          support of VideoMeta
ERROR v4l2codecs-h264dec: Failed to negotiate with downstream
```

which surfaces to the user as the far less helpful **"No valid frames decoded
before end of stream"** — that is what a `not-negotiated (-4)` looks like from
outside. `fakesink` cannot advertise VideoMeta, so the gst-launch form of this
pipeline could never have worked, and adding the meta via appsink's
`propose-allocation` signal did not fix it either.

**Under plain `video/x-raw` caps the v4l2codecs decoder hands out dma-buf backed
memory anyway.** `gst_is_dmabuf_memory()` is true and the FD is real. So
`gles-play` uses plain caps and **verifies rather than negotiates**: it refuses
any buffer that is not dma-buf backed instead of silently falling back to a
copy, which is exactly the cost this path exists to remove. `GLES_CAPS`
overrides the caps for experiments.

Also note `format=DMA_DRM`, not `format=NV12`, if anyone retries the feature:
since GStreamer 1.24 the DMABuf caps carry a DRM fourcc plus modifier in
`drm-format` and `format` is the literal token `DMA_DRM`.

#### Geometry comes from GstVideoMeta

With dma-buf the real strides and offsets belong to the allocation, not to what
the caps format implies. `gles-play` prefers `gst_buffer_get_video_meta()` and
falls back to `GstVideoInfo` — the same meta the decoder insists downstream
support.

### The other end: the GPU renders into the scanout carveout (2026-08-15)

**`PASS: GPU rendered directly into the scanout carveout`.** Both ends of the
zero-copy path are now proven: GPU DMA in from the decoder, GPU DMA out to the
region AFBD fetches.

```
scanout-dmabuf: carveout 0x000000006c100000 + 8192 KiB
EGLImage over the carveout: ok
carveout is a complete FBO: ok
  phys (  64, 64) = ff0d1780  r= 13 g= 23  want ~13,23  ok
  phys ( 640,360) = ff808080  r=128 g=128  want ~128,128  ok
  phys (1216,656) = fff2e880  r=242 g=232  want ~242,232  ok
100 full-frame renders into the carveout: 62.2 ms (0.62 ms/frame)
```

`patches/kernel/0036` adds `sunxi-scanout-dmabuf`, a misc device whose one
ioctl hands out a dma-buf fd over the carveout. **The design constraint is that
`uboot-scanout@6c100000` is a `no-map` reservation with no `struct page`**, so
an sg_table built with `sg_set_page()` would be a lie; the exporter uses
`dma_map_resource()`, which exists for exactly this. panfrost walks the table
with `for_each_sgtable_dma_sg()` and consumes `sg_dma_address()`, so a
page-less table suits it. `CONFIG_SUNXI_SCANOUT_DMABUF=m`.

Verification is deliberately **not** through GL: `tools/video/gles-scanout.c`
renders a position-dependent gradient, then reads the same physical memory back
through `/dev/mem`. Reading back through GL would only prove GL is
self-consistent; the question is whether the bytes are where AFBD will fetch
them.

**A weak test caught and tightened.** The first revision expected `g=56` at
y=64 — an arithmetic slip, the right answer is 23 — and *passed anyway* on a
±40 tolerance. Tolerances are now ±4 and the expected values are computed
(`x/W*255`, `y/H*255`). The rising gradient in both axes also pins orientation:
a flipped image would read ~232 at y=64.

**What remains: feed it real decoded frames.** Either drive cedrus directly
(request API, H.264 slice controls) or take GStreamer's dma-buf fds from an
`appsink`. That is the last piece; both hard halves are done.

Projected against M3's 28.3 fps: decode is 3.2 ms/frame at 311 fps, the GPU
pass is 0.64 ms, and the vsync commit is ~8.5 ms — leaving the 58.9 fps panel
ceiling as the limit rather than a 44 MB/s memory wall.

**Do not shortcut this**: rendering to an ordinary FBO and reading back would
reintroduce a 3.7 MB/frame CPU read and be *worse* than the current CPU path.
That number would look like progress and would not be.

### GPU checkpoint: SOLVED 2026-08-15 — the PPU base address was wrong

**`PASS: GPU ran the job`.** Mali-G31 executes fragment shaders, 1252 Mpixel/s,
reproduced 3/3 after the fix below. The negative recorded in the next section
stands as the trail.

```
  ( 16, 16) =   0,  0, 51  expect ~16,16   ok
  (128,128) = 119,119, 51  expect ~128,128 ok
  (240,240) = 238,238, 51  expect ~240,240 ok
PASS: GPU ran the job
```

The gradient is computed, not cleared — 119 and 238 are the shader evaluating
`gl_FragCoord`, and the constant 51 is the 0.25 blue channel through RGBA4.

**The fix, in two parts.** Both came from the stock DTB
(`local/stock-boot/sunxi.fex`) after the operator vetoed reasoning from H616
mainline — which had led to the confident and wrong conclusion "the GPU domain
is already on, so power is not the problem".

1. **Patch 0020's register base was `0x07010014`**, a transposition of the PMU
   base `0x07001000` that landed inside R_CCU. Every domain register read zero,
   `h713_ppu_is_on()` reported every domain off, `power_on()` waited forever for
   a DONE bit that could never set, and the init writes went into unused R_CCU
   space. At the corrected base all five domains read `wait=0x8`,
   `delays=0x00080808`, `ctrl=1`, `status=0x00010000` — matching the driver's own
   constants exactly.
2. **The domain table was wrong at four of five positions.** Stock has
   `pd_gpu@0, pd_tvfe@1, pd_tvcap@2, pd_ve@3, pd_av1@4`; ours claimed
   `{CPUS, SYS, GPU, VE, DE}` with the GPU at index 2 mapped to `hw_id -1`. So
   the GPU node aimed at TVCAP *and* resolved to an always-on stub.

**Why "all domains read ON" was a red herring.** They were on because boot0 left
them on, not because Linux managed them. With `hw_id -1` the domain was a stub,
so panfrost's runtime PM could never sequence the GPU. Once the domain is real,
panfrost powers it down when idle and brings it up on demand — and jobs land.

**A prediction I got wrong, recorded because the reasoning was the error:** on
seeing every domain read ON I predicted this fix "probably won't fix the GPU".
Powered-at-boot and powered-by-a-driver-that-can-sequence-it are different
states, and only the second lets runtime PM work.

### The VE regression this exposed, and the loop it closed

Making the domains real broke H.264 decode: `cedrus: frame processing timed
out!`. An unclaimed domain gets powered off, and the `ve` node declared no
`power-domains`. Confirmed by hand — writing `CMD_ON` took VE from
`status=0x00020000` (off) to `0x00010002` (on + done) and decode returned.

`power-domains = <&ppu 3>` on the `ve` node had been **tried and reverted on
2026-08-09**, because cedrus stopped probing entirely. That revert's diagnosis
was correct and is now vindicated: *"the cause is in patch 0020, not here...
Restore this line only after the H713 PPU driver can actually report and control
these domains."* The base-address bug is exactly why `power_on()` deferred
forever. The line is restored and is now mandatory, not optional.

### Verified after the fix, 2026-08-15

| check | result |
| --- | --- |
| `gputest` | **PASS 3/3**, no sched timeout |
| cedrus probe | `Device registered as /dev/video0`, no deferral |
| H.264 decode | works, `VE_RC=0` |
| panel | boot logo displays normally (operator-confirmed) |
| genpd | `GPU, TVFE, TVCAP, VE, AV1`; gpu and video-codec both attached and `suspended` |

**RETRACTED 2026-08-15: the "M1 md5 drift" reported here never existed.**
This paragraph originally claimed all five ladder vectors had stopped matching
`reference-md5.txt` and needed re-baselining. They match. **M1 still passes
bit-exact on the current kernel**, verified across all five vectors:

```
v01-320x240-baseline PASS 921600      v04-1280x720-high  PASS 82944000
v02-1280x720-baseline PASS 82944000   v05-1920x1080-high PASS 186624000
v03-1280x720-main    PASS 82944000
```

The fault was in my ad-hoc test command, which omitted
`! video/x-raw,format=NV12 !`. Unconstrained, the decoder negotiates
**NV12_32L32** — Allwinner's 32x32 tiled layout — and emits `ALIGN(height,32)`
rows, so 320x240 becomes 122880 bytes/frame instead of 115200. That output is
correct but tiled, and can never match a linear reference.
`tools/video/m1-decode-test.sh` has always forced the caps, and its comment
predicts this exact byte count. I did not use the project's own instrument.

**The control failed to catch it, and that is the more useful lesson.** I ran
the old kernel against the new one and got byte-identical results, which is
true and proves the kernel change was not responsible — then I read it as
evidence the drift was real and pre-existing. Both runs carried the *same*
broken command, so the control varied the wrong thing. This file already
warns: *"a control must match the run in every respect except the variable
under test."* A control cannot validate a measurement it shares a defect with.

### The original negative (kept as trail): panfrost does NOT run jobs (2026-08-14)

The checkpoint proposed above was run the same evening. **Negative, with a
specific cause to chase.** The software stack is entirely fine:

```
EGL 1.5, EGL_VENDOR: Mesa Project
GL_RENDERER : Mali-G31 (Panfrost)
GL_VERSION  : OpenGL ES 3.1 Mesa 25.0.7-2+deb13u1
```

EGL initialises surfaceless, mesa targets the real hardware path (not llvmpipe),
shaders compile, the FBO is complete. Then:

```
panfrost 1800000.gpu: gpu sched timeout, js=1, config=0x7b00, status=0x8,
                      head=0xa027300, tail=0xa027300
```

`head == tail`: submitted, never advanced. All pixels read back zero.
Test is `tools/video/gputest.c` — a fragment shader whose output is a function
of `gl_FragCoord`, so a correct image cannot be faked by a clear or a memset.

**Getting there needed `libgles2` from Debian trixie** (`libGLESv2.so.2` +
GLES2/EGL headers, plus `KHR/khrplatform.h` from the Khronos registry — no
Debian package ships it). Sent over serial, ~79 KB tarball. That part is done
and lives on the target.

#### Not the clock

`gpu0` (CCU + 0x670, and **the H713 CCU base is 0x02001000**, not H616's
0x03001000) has a plain 2-bit M divider. Jobs fail identically at 864, 432 and
216 MHz. The draw-loop time scaled ~4x with the divider, so the change took
effect in hardware — this is a real negative, not a no-op.

| register | value | meaning |
| --- | --- | --- |
| `PLL_GPU` 0x02001030 | `b8002301` | enabled, locked, N=35 -> 36 x 24 = 864 MHz |
| `gpu0` 0x02001670 | `80000000` | gated on, mux = pll-gpu, M=0 -> /1 |

#### The live suspect: nothing ever powers the GPU domain

`patches/kernel/0020-pmdomain-add-h713-ppu-driver.patch`:

```c
static const int h713_ppu_hw_ids[5] = { 0, 1, -1, 3, 4 };
                             /* CPUS SYS  GPU  VE  DE */
```

Hardware IDs run 0, 1, **[2 skipped]**, 3, 4. The GPU is `-1` = always-on, so
`h713_ppu_set_power()` is **never called for it** and no code in Linux touches
its power hardware — whether it is on depends entirely on what U-Boot left.
`pm_genpd_summary` confirms the bookkeeping is vacuous: GPU reads `on` purely
from the flag, while VE reads `off-0` while decoding at 311 fps.

The justification for `-1` is an inherited RE claim, quoted in the DT node:
*"domain_info[2] is all-zeros in stock binary, meaning no hardware power
sequencer for GPU"*. That is the same shape as the claims in
[h713-inherited-claims-were-wrong] — an absence in a table read as a positive
fact. An equally consistent reading is that stock populates it elsewhere. The
conspicuous positional gap at hardware ID 2 is the tell.

**Next test:** perform the domain-2 power-on sequence by hand and re-run
`gputest`. Registers are at PPU base `0x07010014` + `id * 0x80`: wait_mode
`+0x00`, pwr_off_delay `+0x04`, pwr_on_delay `+0x08`, pwr_ctrl `+0x0c`
(1 = on), status `+0x10` (bit3 idle, bit1 done, bits[17:16] state, 01 = on).
Write the three init values (`0x8`, `0x00080808`, `0x00080808`), then 1 to
pwr_ctrl, then reload panfrost.

**A caution for whoever does it:** a first attempt read those status registers
at `0x07010014 + id*0x80 + 0x10` and got zeros for all five domains, including
CPUS and SYS, which are unquestionably powered. So either the offset or the
base is not what the driver comment implies, and **that dump is not a valid
diagnostic**. Establish a register view that reports CPUS/SYS as ON before
trusting anything it says about the GPU.

#### The stock DTB says our GPU wiring is wrong in two places

Checked against `local/stock-boot/sunxi.fex` — the DTB from the retail firmware,
not the research tree, and not H616 mainline. **Going to H616 first was a
mistake**; it is the assumption that has repeatedly burned this project, and the
operator called it before it cost anything.

Stock `gpu@0x01800000`:

```
compatible    = "arm,mali-midgard"
interrupts    = <0 0x75 4>, <0 0x76 4>, <0 0x4c 4>   /* SPI 117, 118, 76 */
clock-names   = "clk_parent", "clk_mali", "clk_bus"  /* CCU idx 7, 28, 29 */
power-domains = <&pd 0>
operating-points-v2 = <gpu_opp_table>
gpu-supply    = <&reg_vdd_sys>
```

| property | stock | ours | verdict |
| --- | --- | --- | --- |
| interrupts | SPI 117/118/76 | SPI 117/118/76 | **match** |
| supply | `reg_vdd_sys`, fixed 0.96 V, always-on | same | **match** |
| power domain | **`<&pd 0>`** | `<&ppu 2>` | **WRONG** |
| clocks | **three** (`clk_parent`, `clk_mali`, `clk_bus`) | two (`core`, `bus`) | **missing one** |
| frequency | OPP table, **max 700 MHz** | fixed 864 MHz, no OPP | over the vendor max |

**And the PPU driver's whole domain map is wrong.** Stock's controller is
`allwinner,tv303-power-controller` with children:

```
pd_gpu@0  pd_tvfe@1  pd_tvcap@2  pd_ve@3  pd_av1@4
```

against patch 0020's `{ "CPUS", "SYS", "GPU", "VE", "DE" }` / `{0, 1, -1, 3, 4}`.
Four of five names are wrong: index 0 is **GPU** (not CPUS), 1 is TVFE, 2 is
**TVCAP** (not GPU), 4 is AV1 (not DE). Only VE at 3 is right, by luck. So our
`power-domains = <&ppu 2>` aims the GPU at TVCAP *and* resolves to `hw_id -1`,
which is a no-op — nothing in Linux powers the GPU domain, and the "no hardware
power sequencer" claim in the DT comment is refuted by `pd_gpu@0` existing.

**Audit item beyond the GPU:** every `<&ppu N>` reference in our tree is suspect
until re-checked against this list.

#### Still unexplained

The GPU nonetheless *looks* powered: `GPU_ID` reads `0x70930000`, and
`SHADER_READY`/`TILER_READY`/`L2_READY` are all 1 with no faults raised
(`GPU_IRQ_RAWSTAT = 0x600`, POWER_CHANGED only). Jobs still time out at 864, 432
and 216 MHz, and the rail is fixed at 0.96 V for every vendor OPP, so neither
undervolt nor over-clock explains 216 MHz failing.

Note also that genpd's `off-0` for every domain is an **artifact of the broken
register map**, not a hardware reading — `h713_ppu_is_on()` polls a register
that reads zero, so every domain reports off. Do not treat that summary as
evidence either way.

**Next test:** correct patch 0020's domain table to the vendor's, point the GPU
at domain 0, add the third clock and an OPP table capped at 700 MHz, rebuild,
retest. That is a kernel rebuild rather than a poke, but it is ordinary work
against known-good vendor data.

#### What this does to the plan

The checkpoint was proposed as cheap, and it was — one evening, and it returned
a definite answer. But the answer means the GPU path now needs **its own
bring-up** (power domain, and possibly a supply and an OPP table) before it can
do anything for video. It is no longer obviously cheaper than the
`ge2d_dev.ko` RE. It is still a *known kind* of problem for this project, which
the plane RE is not, and its blocker is one testable hypothesis away.

### Tearing on the GPU path: none. Scored 2026-08-15

**`db` median 0.00% rows-with-no-bar against a positive control at 16.94%.**
The GPU presentation path does not tear.

| mode | interior rows | median | mean | worst |
| --- | --- | --- | --- | --- |
| `sb` single-buffered, positive control | 1260 | **16.94%** | 17.06 | 25.68 |
| `noflip` intended floor | 1465 | 16.42% | 10.85 | 21.74 |
| **`db` the real path** | 1239 | **0.00%** | 0.54 | 3.05 |

Instrument `tools/video/gles-tear.c`, scored with `tear-measure.py`. All three
recorded in **one continuous take** (`local/lcd-photos/test_56/IMG_0707.MOV`)
with 6 s solid-blue gaps between runs, because the metric's floor moves with
camera framing and "roughly the same position" cannot be compared across takes.
Segment boundaries were located from the blue gaps rather than from assumed
offsets — which caught that the recording began ~3 s early and ended ~3 s short.

Workload match across the three runs: 59.7 fps each, render means 3.11 / 3.01 /
3.00 ms. They differ only in which buffer is written and whether the flip
happens.

**The metric works here.** That was the open question: Mali is a tile-based
renderer, so a clear plus a draw resolve together and the two-phase window the
metric depends on would not exist naturally. `gles-tear` forces it with a
`glFinish()` between passes, and the positive control duly reads ~17% against a
predicted ~18% (3.0 ms of a 16.75 ms frame).

#### The floor run is flawed, and it does not change the result

`noflip` shows a **static** bar that cannot change, so it should score at or
below `db`. It read 16.42%. Two tells: the score varies frame to frame
(mean 10.85 vs median 16.42) although the image is pixel-identical, and the
static bar sits at the **left edge**, where keystone and lamp falloff make
detection marginal. That is a detection artifact, not a workload floor.

The conclusion survives because `db` is *below* the broken floor, and there is
no less corruption than "corruption impossible". A floor matters for
interpreting an elevated number; `db` is not elevated.

**Hypothesis, not a finding:** the CPU path's 23.03% floor used the same
left-edge static bar (`fill_bar(fb_front, 0)`), so it may have been inflated the
same way. That would explain why that floor sat so high, and it does not change
the CPU-path conclusion — double buffering worked there too. Testing it costs
one capture with the static bar centred.

### M3 — DONE 2026-08-15, via the GPU rather than the CPU

Sustained playback achieved at 59.71 fps zero-copy, vsync-limited, operator
confirmed. The original plan below (tear-measure against the fb-anim-db
reference) was written for the CPU path; the tearing question it targets is
still worth scoring on the GPU path, but the throughput question M3 existed to
answer is settled.

### M3 — sustained playback (original plan)

Double-buffered flip at the vsync-locked commit, scored with
`tools/display/tear-measure.py` against the `fb-anim-db` reference. Keeping the
synthetic moving bar on the same instrument is deliberate: a decoder fault must
not be able to present as a display fault.

### M4 — productize

DECD (`dec@5600000`) versus a real DRM plane. Deliberately last — both are large,
and the choice is uninformed until M1–M3 have run. Note that cedrus emits linear
NV12 or Allwinner tiled, **not** AFBC, so DECD's compressed path does not match
cedrus output as-is; its "raw" path is the relevant one. The evidence log's
Milestone 4 warning about resource ownership (shared display clocks, resets, IRQs
and overlapping register windows needing one clear owner) applies directly:
U-Boot currently owns the AFBD registers, and DECD would want them.

## Tooling changes made for this phase

- **`tools/rootfs/build.sh --extra-packages LIST`** — appends to the bootstrap
  set. The shipped product image stays minimal; bring-up images opt in. Used
  here for `v4l-utils`, the GStreamer stack, `ffmpeg`, `build-essential`,
  `libdrm-dev`, `libv4l-dev`, `python3` and `strace`.
- **An on-target compiler is deliberate.** M2/M3 are register-poking experiments
  against a framebuffer; cross-compiling and shipping each iteration over an
  11 KB/s UART is how this project has previously spent whole sessions. `gcc` on
  the board turns that into seconds.
- **`tools/video/make-test-streams.sh`** — the ladder above.
- **`tools/video/h713-present.c`** — the Linux-side presenter (`regs`, `fill`,
  `bar`, `nv12`). Build on the target: `gcc -O2 -o h713-present h713-present.c
  -lpthread`. Refuses to run unless the AFBD clock gate is open, because reading
  those blocks while gated hangs the board.
- **`tools/serial/send_file.py`** — copy a file to the target over the Linux
  serial console when the USB gadget is unavailable. Chunks base64 and verifies
  by md5. **The console is a canonical-mode tty, so a single input line is capped
  at ~4 KB by the line discipline** — anything longer is silently truncated,
  which presents as a corrupt file rather than a transfer error.

## Open items

- The `ve` node declares **no `power-domains`**, although the PPU driver defines
  a `"VE"` domain (index 3, patch 0020) and the GPU node uses `<&ppu 2>`. It
  works today only because `pd_ignore_unused` is on the command line — the same
  load-bearing flag the display handoff depends on. Worth wiring properly before
  anything depends on VE runtime PM.
- **AV1 is inert** and should stay that way until H.264 works. A driver exists
  in `local/allwinner-h713-linux/drivers/media/av1/` (never enabled, never
  tested); the DT node's compatible matches nothing in our tree.
- The bench board is a **WiFi AP at 192.168.4.1** with sshd running. Joining it
  from the host would give a fast file path, at the cost of the host's own
  network. `ums` from U-Boot is the transfer route used instead.
