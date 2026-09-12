# Hardware decode for stock players — VA-API scope

Written 2026-08-16. Answers one question with numbers rather than estimates:
**what would it take for `mpv` (and anything else using ffmpeg) to decode on the
VE instead of the CPU, without patching mpv, ffmpeg or GStreamer?**

The short version: the chain is real, the H.264 half is nearly free, the HEVC
half is a rewrite, and 10-bit is blocked in the kernel rather than in userspace.

---

# RESULT — H.264 decodes on the VE through stock ffmpeg, 2026-08-16

**Done, and validated bit-exact on hardware.** `libva-v4l2-request` (PR #38 plus
[three patches](../patches/libva-v4l2-request/)) drives cedrus from unmodified
ffmpeg. All five vectors of the M1 ladder — 320x240 baseline through 1920x1080
high — decode **bit-exact** against the host-generated references, and the VE's
interrupt count rises by exactly one per frame, so the hardware is doing it.

| | |
| --- | --- |
| `vainfo` | loads `__vaDriverInit_1_22`, advertises 5 H.264 profiles, `VAEntrypointVLD` |
| bit-exactness | 5 of 5 vectors, `tools/video/va-decode-test.sh` |
| decode cost | **1.233 s wall / 0.637 s CPU** for 60 frames of 1080p (software: 2.72 s CPU) |
| what blocked it | *not* the codec — the shim created the bitstream queue with zero buffers, because ffmpeg no longer preallocates a VA surface pool. See patch 0003. |

**The one number to carry into the display work:** copying decoded frames back
to system memory with `hwdownload` costs *more than the decode* (1.8 s extra for
186 MB of 1080p) because V4L2 MMAP buffers are uncached. Decode-to-file pays
that; a display path that maps the surface as a dma-buf does not.

## The display path — plays on the panel, and crashes the kernel intermittently

Step 6 was attempted the same session. It gets **all the way to video on the
panel**: `mpv` hardware-decodes on the VE and renders through EGL-on-GBM against
our KMS driver, and a 1200-frame 720p25 clip has played to completion.

The two things worth knowing before picking this up:

**1. It must be `--hwdec=vaapi-copy`, not `--hwdec=vaapi`.** Plain `vaapi`
fails with `Could not create a VA display`, and the reason is structural rather
than a misconfiguration: mpv's `vo=gpu` DRM path asks for a **render node on the
KMS device** (`drm_params_v2.render_fd`) and our display-only driver has none —
`renderD128` belongs to panfrost on `card0`. `--vaapi-device` is accepted and
*ignored* on this path. Our shim ignores the DRM fd entirely, so any node would
do; mpv just will not offer one. Patching mpv is out of scope by standing
constraint, so `vaapi-copy` — which builds its own VA display and honours
`--vaapi-device` — is the working invocation:

```
LIBVA_DRIVER_NAME=v4l2_request mpv --hwdec=vaapi-copy \
  --vaapi-device=/dev/dri/renderD128 \
  --vo=gpu --gpu-context=drm --drm-device=/dev/dri/card1 clip.mp4
```

That costs the copy-out measured above. Zero-copy would need either a render
node on `card1` or the `drmprime-overlay` path (mpv reports `Failed to find
drmprime plane with idx=-2` today).

**2. It panics intermittently — and it is memory corruption, not a codec bug.**
Two of four runs of the same 48-second clip took the board down. Captured on
serial:

```
Unable to handle kernel NULL pointer dereference at virtual address 0000000000000010
CPU: 3  Comm: kworker/u16:1
Workqueue:  0x0 (pan_js)             <- panfrost job scheduler, work fn is NULL
pc : stmmac_hw_setup+0x844/0xbd4     <- nonsense; this board has no Ethernet
Call trace: dequeue_entities / dequeue_task_fair / __schedule / worker_thread
...
cedrus 1c0e000.video-codec: frame processing timed out!
rcu: INFO: rcu_sched detected stalls on CPUs/tasks: 0-...! 1-...! 3-...!
```

A workqueue whose work function is `0x0` and a PC that resolves to an unrelated
built-in symbol are both signatures of **corrupted kernel memory**, not of a
driver returning an error. It surfaces in panfrost's job scheduler because that
is what runs constantly during playback, which does not mean panfrost is the
culprit. In play: `sun50i_h713_afbd`, `sunxi_cedrus`, `sunxi_scanout_dmabuf`,
`panfrost`.

**The controls say it is the combination, not either half:**

| run | result |
| --- | --- |
| hardware decode, `--vo=null`, 48 s / 1200 frames | **stable** (VE IRQ count exactly 1200) |
| software decode, on the panel, 48 s | **stable**, played to completion |
| hardware decode **on the panel**, 48 s | **2 of 4 runs panicked** |

### The KASAN kernel — built, and how to run it

Make the crash legible rather than guessing at it. The debug kernel exists:

```
KERNEL_CONFIG=kasan build/build.sh kernel     # -> build/out/h713-kernel-kasan.fit
```

`patches/kernel/board/kasan.config` turns on generic KASAN (outline, plus
`KASAN_VMALLOC` because module text and DRM/GEM allocations live there) and
builds cedrus, the AFBD KMS driver, panfrost and scanout-dmabuf **in** rather
than as modules — KASAN only instruments what is compiled in its tree, so as
modules the four suspects would be the only unchecked code. It also sets
`CONFIG_LOCALVERSION="-kasan"`, which is not cosmetic: `uname -r` becomes
`6.18.38-kasan`, so `/lib/modules/6.18.38-kasan` does not exist, udev loads
nothing, and the production kernel's modules cannot be loaded into a KASAN
kernel by accident. (They must not be: KASAN changes core struct layouts, so a
stale `.ko` reads wrong offsets and corrupts memory itself.) `MAGIC_SYSRQ` is on
there too, with serial-BREAK support.

Getting it onto the board **does not go over WiFi** — see the gotcha above; that
link cannot carry a file. One YMODEM transfer at the U-Boot prompt, made
permanent so later boots are instant:

```
python3 tools/serial/load_fit.py build/out/h713-kernel-kasan.fit --port /dev/ttyUSB0 --addr 0x50000000
```

~17 minutes at 10.8 KB/s. Then, at the prompt:

```
fatwrite mmc 1:2 0x50000000 h713-kernel-kasan.fit ${filesize}
h713_disp auto 0x34 logo
bootm 0x50000000
```

and on any later boot, `fatload mmc 1:2 0x50000000 h713-kernel-kasan.fit; bootm
0x50000000`. The production `h713-kernel.fit` is never touched, so the way back
from a bad debug kernel is an ordinary boot.

Two things change when this kernel boots, and both will trip you up:

- **The DRM card numbers swap.** Built-in drivers probe in a different order
  than modules, so on the KASAN kernel `card0` is `sun50i-h713-afbd` and `card1`
  is panfrost — the reverse of the production kernel. mpv wants
  `--drm-device=/dev/dri/card0` here. `renderD128` is panfrost either way.
- **Usable RAM drops to 780 MB** from ~1 GiB; that is the shadow, and it is the
  cheapest confirmation that KASAN is really on, alongside
  `KernelAddressSanitizer initialized (generic)` in dmesg.

### Result of the first KASAN reproduction attempt — the crash did not fire

Decode is still bit-exact under KASAN (`v04` → `a991db21…`), so the kernel is
sound. But **the crash did not reproduce**, across **~24 minutes of continuous
looping 720p playback on the panel — 42,773 frames by the VE's interrupt
count — with zero crashes and zero KASAN reports** (three runs: 240 s, 300 s
and a 900 s soak). The pre-KASAN kernel failed 3 of 4 runs, usually inside 48
seconds.

That kernel changed two things at once, unavoidably — KASAN only instruments
what is compiled in its tree, so covering the four suspect drivers meant
building them in. So the control was run: **the same four drivers built in,
without KASAN** (`patches/kernel/board/builtin-drivers.config`).

### The control settles it — KASAN was hiding the bug

**It crashed at T+198 s**, on the same playback. So built-in versus module is
*not* the variable; KASAN's presence is. And note KASAN produced no report
either — it did not miss a detection, the racing access appears not to have
happened at all, which points at its 2–3x slowdown moving the window rather
than at coverage.

The control's trace is also far better than the original, because with these
drivers built in there are no module offsets to confuse the symbolizer. Where
the first capture said `Workqueue: 0x0 (pan_js)` and a PC in an unrelated
built-in, this says exactly what is happening:

```
Unable to handle kernel NULL pointer dereference at virtual address 0000000000000000
CPU: 3  Comm: kworker/u16:2  Not tainted 6.18.38-builtin
Workqueue: pan_js drm_sched_run_job_work
pc : pwq_tryinc_nr_active+0xfc/0x204
lr : __queue_work+0x520/0x648
Call trace:
 pwq_tryinc_nr_active+0xfc/0x204 (P)
 __queue_work+0x520/0x648
 queue_work_on+0x3c/0xa0
 drm_sched_run_job_work+0x4d8/0x504
 process_scheduled_works+0x170/0x300
 worker_thread+0x2fc/0x45c
```

The DRM GPU scheduler queues its run-job work, and the workqueue core
dereferences NULL doing it — so the workqueue the scheduler is submitting to is
NULL or freed underneath it. That is a **lifetime/teardown race in
drm_sched + panfrost**, provoked by the VE-decode-plus-display combination, and
it is not a VA-API bug: nothing in the shim, cedrus or the AFBD driver appears
in that path.

Decoded further against the `vmlinux` that produced it, so the next session does
not have to. The `Code:` bytes in the Oops match `pwq_tryinc_nr_active+0xfc`
exactly:

```
b5d4: 88e87d6c   casa w8, w12, [x11]      <- raw_spin_lock(&nna->lock)
b5d8: 350006e8   cbnz w8, <slowpath>
b5dc: f9400128   ldr  x8, [x9]            <- FAULTS, x9 = 0
b5e0: eb09011f   cmp  x8, x9
```

`ldr` then `cmp` against the same register is `list_empty()`, so the faulting
line is the `if (list_empty(&pwq->pending_node))` immediately after
`raw_spin_lock(&nna->lock)` in `pwq_tryinc_nr_active()`. Two things follow.
That branch is only reachable for a **`WQ_UNBOUND`** workqueue (`wq_node_nr_active()`
returns NULL otherwise and the function takes the early `!nna` exit), which fits:
`drm_sched_init()` gives each scheduler its own `alloc_ordered_workqueue()`, and
ordered implies unbound. And `+0x4d8/0x504` in `drm_sched_run_job_work` is the
**final** `drm_sched_run_job_queue(sched)`, the requeue at the very end of the
function — not the early no-job path.

So the shape to look for is: the scheduler requeues its own run-job work at the
tail of that function while something concurrently tears the workqueue (or its
`pool_workqueue`) down. `drm_sched_run_job_queue()` only checks
`READ_ONCE(sched->pause_submit)` before `queue_work()`, which is not
synchronised against a teardown running on another CPU. panfrost's reset path
(`panfrost_job_timedout` → `drm_sched_stop`/`drm_sched_start`, `panfrost_job.c`)
is the obvious thing to audit against it — and note the `cedrus: frame
processing timed out!` in the very first capture, which would be exactly the
kind of event that triggers a reset. `kworker … exited with irqs disabled` is why the board then
hard-locks rather than merely oopsing — sysrq gets no response afterwards, so
recovery is the power switch.

### Upstream has not fixed it — checked 2026-08-17

- **The race is still there in current master.** `drm_sched_run_job_queue()` was
  refactored to `if (!drm_sched_is_stopped(sched)) queue_work(...)`, but
  `drm_sched_is_stopped()` is literally `return READ_ONCE(sched->pause_submit);`
  — a rename, not a fix. Queueing is still an unsynchronised check-then-act
  against a teardown that may be running on another CPU.
- **The one panfrost fix that looks relevant is already in our tree.**
  `796a9f55a8d1` ("drm/sched: Use struct for drm_sched_init() params", which
  carried the panfrost `timeout_wq` regression fix) — our `panfrost_job.c` sets
  `args.timeout_wq = pfdev->reset.wq`, so we are not hitting that.
- `panfrost_job.c` has no post-6.18 commits touching reset or scheduler
  lifetime. The newest adjacent work is Philipp Stanner's Feb 2026
  "drm/sched: Remove racy hack from drm_sched_fini()", which targets the
  entity-teardown `FIXME` still present in our `drm_sched_fini()` — a real race,
  but not the one in our trace.

### A better hypothesis than the drm_sched race — rogue VE DMA

Before spending another kernel cycle on drm_sched, weigh the competing
explanation, because it fits *all* the evidence and the scheduler race fits only
some of it. **The VE has no IOMMU** — deliberately, and documented at length in
patch 0024:

> `NO iommus PROPERTY -- deliberate, 2026-08-09.` `iommus = <&iommu 0>` here
> crashed the kernel on the first decode: **rogue VE DMA corrupted the printk
> ringbuffer**, faulting in `_prb_read_valid()` … the iommu node is inert, so
> the DMA layer handed cedrus IOVAs expecting translation, nothing translated
> them, and the VE wrote them as raw physical addresses.

So this board already has a precedent for the VE writing outside its buffers and
corrupting whatever kernel memory happened to be there. And crucially, **KASAN
cannot see device DMA** — it instruments CPU accesses only. That explains the
otherwise-odd result that KASAN was not merely quiet but produced *no report at
all*, while the crash vanished.

It also explains the control matrix better than a scheduler race does:

| | VE DMA active | display/GPU active | result |
|---|---|---|---|
| `--vo=null` | yes | no | stable — a stray write lands in idle memory |
| software decode on panel | **no** | yes | stable — nothing writes out of bounds |
| hardware decode on panel | yes | yes | **crashes** — panfrost's structures are the neighbour |

What I checked and did *not* find: cedrus's own geometry is internally
consistent, `cedrus_video.c` sizing the NV12 buffer with `ALIGN(width,16)` /
`ALIGN(height,16)` and `cedrus_hw.c` programming the same 16-alignment into
`VE_PRIMARY_FB_LINE_STRIDE_*`. So there is no obvious under-allocation to point
at — the hypothesis needs the H713's VE3 to want more than mainline cedrus
assumes, which is unproven.

### Both experiments run, 2026-08-17 — it is memory corruption, and drm_sched is a victim

Run on the control kernel with `oops=panic` added to the command line, which
turns each crash into a 5-second self-reboot and takes the human out of the
loop entirely (`panic=5` was already there). Highly recommended for this work.

| run | clip | `cma=` | outcome |
| --- | --- | --- | --- |
| (first) | 1280x720 | 128M | fatal Oops T+198 s — `pwq_tryinc_nr_active`, workqueue internals |
| **A** | 1280x720 | 128M | fatal Oops T+457 s — `rb_erase` ← `timerqueue_del` ← `__hrtimer_run_queues`, faulting on `0x3fd945c0` |
| **B** | 1280x**736** | 128M | fatal Oops T+113 s — `dma_fence_add_callback` ← `drm_sched_run_job_work` |
| **C** | 1280x720 | **256M** | no fatal Oops in 480 s; **530 ×** `WARNING … enqueue_dl_entity` (deadline scheduler), then rebooted after the window |

**Four different corrupted structures across four runs** — a workqueue's
`pool_workqueue`, the hrtimer red-black tree, a dma_fence, and the deadline
scheduler's runqueue. Three of those have nothing whatever to do with video or
graphics. **A code race faults in the same place; random corruption does not.**
So the drm_sched teardown race is not the bug — `drm_sched_run_job_work` is
simply the hottest code during playback and therefore the most likely thing to
trip over whatever got scribbled on. That also retires the earlier reading of
the first trace.

Note the faulting address in run A: `0x3fd945c0` is not a kernel virtual
address, it is a **physical-looking address inside the 1 GiB of DRAM** — a
pointer field holding something that looks like a DMA address.

**Experiment 2 (height alignment): refuted.** A 32-aligned 1280x736 clip did not
merely fail to help, it crashed *sooner* (113 s vs 457 s). The
16-versus-32-row-overrun mechanism is not what is happening. Good — that
hypothesis was cheap to kill and would have been expensive to chase.

**Experiment 1 (CMA size): the symptom moved.** At `cma=256M` the same clip
produced no fatal fault in the observed window, but a storm of corruption
warnings against a *different* structure. **drm_sched cannot care how big the
CMA pool is; a stray write must.** Layout-dependence is the signature.

Taken with KASAN's silence — no crash *and* no report, from a kernel where all
four suspect drivers were instrumented — the remaining explanation is a write
that the CPU never issues: **DMA from a device**, which KASAN cannot see, into
memory it does not own. The VE has no IOMMU and this board has a documented
precedent for exactly that (patch 0024, quoted above).

### VA-API is ruled out — it reproduces with no VA-API at all (2026-08-17)

| run | decode | scanout buffers | result |
| --- | --- | --- | --- |
| A/B/C | VA-API shim → cedrus | mpv KMS/GBM, **from CMA** | crashes, 113–457 s |
| **D** | **GStreamer** `v4l2slh264dec` → cedrus | `gles-play`, **reserved carveout** `0x6c100000` | **clean** — 480 s, ~28,437 frames |
| **E** | **GStreamer** `v4l2slh264dec` → cedrus (to `fakesink`, no display) + mpv **software** decode to the panel | mpv KMS/GBM, **from CMA** | **crashes** — `stack-protector: Kernel stack is corrupted in: internal_add_timer` |
| **I** | **none at all** — the VE is never opened, `ve=0` interrupts from boot to panic | mpv KMS/GBM, **from CMA** | **crashes** — `kernel stack overflow` at ~940 s. Cedrus is not necessary; see Experiment I below |

Run E is the one that settles it. There is **no VA-API in it anywhere** — the
hardware decode is GStreamer's, going nowhere but `fakesink`, and the picture on
the panel is *software*-decoded. It still corrupts the kernel, this time
tripping the stack protector: a fifth distinct victim, after a
`pool_workqueue`, the hrtimer rbtree, a `dma_fence` and the deadline scheduler.

So the earlier claim in this document that the crash "is not a VA-API bug" was
right, but for the wrong reason and on the wrong evidence — it now rests on a
direct experiment rather than on reading a call trace. **mpv, ffmpeg and the
libva-v4l2-request shim are all exonerated.** The necessary and sufficient
ingredients are:

> ⚠ **The first half of this is now refuted — see "Experiment I" below. Cedrus
> is NOT necessary.** What survives is the second half, the CMA-backed scanout.
>
> ~~cedrus decoding into CMA buffers, concurrently with~~ a KMS/GBM scanout
> buffer that is allocated from CMA.

Run D is the control that shows the second half matters: the *same* hardware
decode, with scanout coming from the reserved carveout instead of CMA, is clean
over 28,000 frames. Which is also why every earlier "decode alone is fine"
result held — with `--vo=null` nothing else was claiming CMA.

### The guard says it is not an overrun (2026-08-17)

`patches/kernel/0039-media-cedrus-add-runtime-dma-guard.patch` pads every cedrus
capture buffer, poisons the padding, and checks it once the VE has completed the
frame — the only way to witness a write that no MMU mediates. Off by default;
arm it with `sunxi_cedrus.dma_guard=65536` on the kernel command line.

First, the IOMMU claim this rests on, verified on the running board rather than
taken from a comment: `/sys/class/iommu/` and `/sys/kernel/iommu_groups/` are
both **empty**, the DT node `iommu@30f0000` has `status = "disabled"`, and the
`video-codec` node carries **no `iommus` property**. Nothing translates VE DMA.
(That proves no IOMMU is *active*, not that the silicon lacks the block — patch
0024 records every register at `0x030f0000` reading zero on this hardware, which
is why it is disabled.)

Results, both informative and both negative for the obvious theory:

- **Decode-only with the guard armed: zero reports**, output still bit-exact
  (`a991db21…`). The VE does not write past the frame it is given.
- **The full crashing workload with the guard armed: 13,391 frames over 450 s,
  no crash and zero reports** — where that exact workload died three times
  before, at 113 s, 198 s and 457 s. The 64 KiB of padding *changed the CMA
  layout*, exactly as `cma=256M` did, and the crash went away without the guard
  ever being touched.

**So it is not a bounded overrun past the capture buffer.** There is a stronger
argument for that conclusion than the guard alone: the victims — a kernel
stack, the hrtimer rbtree, a `pool_workqueue`, a `dma_fence`, the deadline
runqueue — are **slab and stack allocations, which are unmovable and therefore
never placed in CMA**. A write running off the end of a CMA buffer lands in
neighbouring *CMA* pages, which host only movable allocations. To corrupt a
kernel stack, the write has to go somewhere else entirely — a stale or wrong
address, not an off-by-a-bit.

### The concrete candidate: cedrus frees DMA buffers without halting the VE

`cedrus_stop_streaming()` does not reset the engine. For the OUTPUT queue it
calls `ctx->current_codec->stop(ctx)` — which for H.264 **frees
`pic_info_buf` and `neighbor_info_buf`** (`dma_alloc_attrs` with
`DMA_ATTR_NO_KERNEL_MAPPING`) — then `pm_runtime_put()`, then returns the
buffers. Nothing anywhere in that path asserts the VE's reset or waits for it to
go idle. The driver's *only* `reset_control_reset()` is in the watchdog timeout
handler, and `cedrus: frame processing timed out!` appeared in the very first
crash capture.

If the VE is still executing when those pages are freed, it keeps writing into
memory the allocator has since handed to slab or a kernel stack. That mechanism
predicts everything observed: arbitrary victims rather than one, layout
dependence, invisibility to KASAN, and the fact that it takes a second engine
competing for CMA to make the freed pages get reused quickly enough to matter.

### ⚠ RETRACTED — the A/B below was underpowered, and a one-hour soak refutes it

**Read this before the section that follows.** On 2026-08-17 the full
configuration — IOMMU translating both VE ports *and* `stop_reset=Y`, i.e. both
mitigations on — was soaked, and it **crashed after 390 seconds**:

```
Internal error: Oops - Undefined instruction: 0000000002000000 [#1]  SMP
CPU: 3  PID: 3266  Comm: kworker/u16:2
Workqueue:  0x0 (pan_js)          <- work function NULL, as in the very first crash
pc : __schedule+0x284/0x794
Call trace: __schedule / schedule / worker_thread / kthread
```

So kernel memory is still being corrupted, with the same signature this
investigation started from. **`cedrus_stop_streaming()` not halting the engine
is therefore not established as the root cause.** The A/B that appeared to
establish it was one run per arm, and crash latency across this whole
investigation has ranged 113 s to 848 s — a single clean 450 s arm was never
strong enough to carry the conclusion, and I should have said so at the time
rather than after the counterexample.

What survives from that experiment: the *fix-off* arm did crash, and the
IOMMU-on/fix-off arm degraded a kernel panic to an mpv segfault. Both remain
consistent with cedrus contributing. What is now false is "root cause found".

**The control this investigation never ran with adequate exposure** is the one
that would settle it: the display path active for ten-plus minutes with **no
hardware decode at all**. The only such run was 48 seconds. Every long run that
crashed had cedrus decoding in it, but so did nearly every long run, so that
correlation is much weaker than it looked. The display block (`dec@5600000`,
IOMMU master 2) is in **bypass** in our DT, exactly as the vendor has it, so it
can still write anywhere — and `sunxi-scanout-dmabuf` hands physical addresses
to display hardware by design.

### Experiment I — that control ran, and it crashes with the VE at zero (2026-08-17)

**Cedrus is not necessary for the corruption.** The display path alone panicked
the kernel after ~940 seconds with the video engine never once interrupted.

Trace and full heartbeat series:
[`docs/reference/expI-display-only-no-ve-crashes.log`](reference/expI-display-only-no-ve-crashes.log).
Harness: [`tools/video/soak-display-only.sh`](../tools/video/soak-display-only.sh)
and [`tools/serial/soak-capture.py`](../tools/serial/soak-capture.py).

Same kernel as every crashing run (`6.18.38-builtin`), same `cma=128M`, no
IOMMU (verified on the board: `/sys/class/iommu/` empty, zero iommu groups),
`oops=panic`. Workload was `mpv --hwdec=no --vo=gpu --gpu-context=drm` looping
720p to the panel — run E's display half with the GStreamer/cedrus half
subtracted. Thirty-two consecutive 30-second heartbeats, every one of them:

```
SOAK t=931s ve=0 ve_delta=0 gpu=418868 gpu_rate=452/s cma=112544kB deaths=0
[ 1008.405674] Insufficient stack space to handle exception!
[ 1008.405716] CPU: 2 UID: 0 PID: 41 Comm: kworker/u16:1  6.18.38-builtin
[ 1008.405737] Workqueue:  0x0 (pan_js)
[ 1008.405862] Kernel panic - not syncing: kernel stack overflow
```

`ve=0` is a **positive** witness, not an assumption: cedrus is built into this
kernel and cannot be removed, so the `1c0e000.video-codec` interrupt count
staying at zero from boot to panic is direct evidence that no frame ever
reached the engine. `deaths=0` says mpv ran continuously, so the display path
was driven for the whole 940 s rather than quietly idling.

**On the strength of one run.** The retraction above is about an underpowered
*clean* arm, and that caution does not transfer here. This claim is a
refutation of a necessity — "cedrus must be decoding" — and a single
counterexample is logically sufficient to kill one. What one crash does *not*
establish is any positive claim about rate or cause.

`Workqueue: 0x0 (pan_js)` is the same NULL work function as the very first
crash and as the retracted soak, so this is the same bug, not a new one.

**A sharper forensic clue than "random victim".** The panic is a stack
overflow, and the reason is a truncated pointer:

```
sp        : 0000000081350040
Task stack: [0xffff800081350000..0xffff800081354000]
```

The stack pointer should be `ffff8000_81350040`. Its **upper 32 bits have been
zeroed** — the low half is intact and correct. That is the signature of a
32-bit write landing on the high word of a 64-bit pointer, which also fits a
`work_struct` function pointer reading as `0x0`. Previous crashes were recorded
as "a different victim every time"; this one additionally says *what shape* the
write is.

**What that narrows to.** The obvious suspect for a stray 32-bit write
clobbering a `work_struct` would be DECD — patch 0034 fixed exactly that bug,
`jiffies_hist[jpos + 2]` running off a `u32[100]` into the adjacent
`struct work_struct`. **It is not DECD here.** On `-builtin` there is no module
tree at all, DECD is a module, and its `"decd"` interrupt is absent from the
run's `/proc/interrupts` baseline. The live display path was only: the AFBD KMS
driver (0037), panfrost, and `sunxi-scanout-dmabuf` (0036).

Combined with run D — GPU rendering *and* hardware decode, scanout from the
reserved carveout, clean over 480 s — the discriminating variable across every
run in this document is now **where the scanout buffer lives**, not what feeds
it.

#### A second ve=0 failure, weaker but consistent

The first attempt at this control (same file, appended) lost mpv to a signal at
~250 s with `ve=0`, leaving the kernel up. It is weaker evidence because the
signal was not recoverable, and *why* is worth carrying forward:
**`/proc/sys/debug/exception-trace` is 0 on this rootfs**, so the kernel prints
nothing for a userspace fault. An empty `dmesg` after a mysterious process
death is therefore not evidence of anything. The harness now sets it to 1,
records mpv's exit status through `wait()`, and restarts mpv so a single death
no longer ends an hour-long run.

### The A/B that suggested halting the VE stops the corruption (superseded)

`patches/kernel/0040-media-cedrus-halt-ve-before-freeing-dma-buffers.patch`
pulses the engine's reset in `cedrus_stop_streaming()` before `codec->stop()`
frees anything, while the device is still powered. It is behind
`sunxi_cedrus.stop_reset` (default on, **writable at runtime**), which is what
makes the test worth trusting: both arms ran in the **same boot**, with the same
CMA layout and the same workload, so nothing but the reset differs.

Critically, `dma_guard` was left at **0** for this — the padding from patch 0039
masks the crash by itself, and would have invalidated the whole comparison.

| arm | `stop_reset` | result |
| --- | --- | --- |
| **A** | `Y` | 450 s, **13,338 frames, clean** |
| **B** | `0`, flipped via sysfs, same boot | **crash** — NULL deref, `Workqueue: 0x0 (pan_js)`, `pc : dequeue_entities` (the CFS scheduler — a sixth distinct victim) |

So the mechanism is established: **cedrus frees DMA buffers that the VE may
still be writing into, and the page allocator hands those pages to slab or a
kernel stack.** Everything observed follows from that — arbitrary victims rather
than one repeatable site, layout dependence, KASAN blindness (the writer is a
device, and this SoC has no usable IOMMU), and the need for a second CMA
consumer to make the freed pages get reused quickly enough to matter.

**How much this proves, honestly.** One clean 450-second arm against one crash
is not a long baseline, and crash latency has ranged from 113 s to 848 s. What
makes it convincing is the within-boot flip plus the prior record: five earlier
reproductions, four of them inside 457 s. The confirmation still owed is a long
soak with `stop_reset=Y` — an hour, not eight minutes.

**Before this ships as a fix**, the caveat in the patch has to be closed: a
reset is device-wide, so it must not fire while a second m2m context is mid-job.
Either check that no job is running, or perform the reset from the m2m job
context. Upstream cedrus has the same hole on every SoC it supports; it is
merely harmless where an IOMMU contains the engine.

### And the vendor does contain it — checked against board B's binaries

Patch 0024 already documents the vendor's `mmu_aw: iommu@2010000`
(`allwinner,sunxi-iommu`, `#iommu-cells = <2>`, SPI 71, `clocks = <&ccu 0x30>`),
that mainline's `iommu@30f0000` is the H6 base and simply wrong here, and that
`ve@1c0e000` attaches as master 0. Re-derived from `local/stock-boot/sunxi.fex`
and confirmed. Two things that comment does **not** say, and both matter now:

- **The display block is behind the IOMMU too.** `dec@5600000` — the same
  address our AFBD KMS driver binds — is `iommus = <&mmu_aw 2 0>`. So is
  `ge2d@5240000` (master 2), `demux` and `audbrg` (master 6), `ve1` (1),
  `av1@1c0d000` (5). **Both engines in our crashing combination are translated
  in the vendor stack and untranslated in ours.**
- **The vendor kernel genuinely drives it**, rather than merely declaring it in
  DT. `strings` on `boot_a-board-b.img` gives 159 IOMMU symbols including
  `sunxi iommu init tlb failed`, `sunxi iommu: irq = %d`, `sunxi iommu int
  error!!!`, `Attached IOMMU controller to %s device.`, plus
  `arm_iommu_attach_device` and the build path
  `H713_SDK_V1.3_Branch/longan/kernel/linux-5.4/drivers/iommu/`.

That reframes patch 0024's conclusion. "The honest state is no IOMMU, which is
also the safer one" was the right call at the time — being handed IOVAs that
nothing translates is worse than dma-direct. But it is now clear what running
untranslated costs: cedrus's post-free writes reach arbitrary kernel memory, and
this investigation spent a session chasing six different victims that an IOMMU
would have reported as one fault naming the offending master.

So porting the vendor IOMMU stops being a nice-to-have. It is the containment
mechanism for this entire class of bug, and the reason the vendor never had to
notice that `stop_streaming` does not halt the engine. The work it needs is
already scoped in patch 0024: a driver for `allwinner,sunxi-iommu` (the cell
count and register layout both differ from mainline's `sun50i-iommu`, and
register compatibility with the H6 block is untested), and the CCU gate checked
before probing because an ungated block hangs this interconnect.

**Where to point the next session:**

- It is **kernel-side**, in cedrus and/or the AFBD KMS/scanout path — not in
  any userspace video component.
- The question to answer is which side writes out of bounds: does the VE
  overrun its capture buffer into a neighbouring CMA allocation, or does the
  KMS/scanout path overrun its own? Guard/poison pages either side of both
  allocations answer it directly, and they see what KASAN cannot — KASAN
  instruments CPU accesses, and neither of these writes comes from the CPU.
- `CONFIG_DMA_API_DEBUG` is the other cheap instrument.
- Also worth a look while in there: **`kmssink` cannot drive our KMS driver at
  all.** It fails negotiation, and with `videoconvert` in the pipeline it
  produces `GStreamer-CRITICAL … range start is not smaller than end for
  'GstIntRange'` — our driver is advertising a degenerate size range in its
  plane/mode caps. Unrelated to the corruption, but it blocked the cleanest
  version of this experiment and is a real bug.

**Next steps, in order of cost:**

1. `CONFIG_DEBUG_OBJECTS` + `DEBUG_OBJECTS_WORK` — targets exactly this (a work
   item used after free or never initialised) at a fraction of KASAN's overhead,
   so it is far less likely to perturb the window shut the way KASAN did.
2. Read `drm_sched_run_job_work()` against panfrost's scheduler teardown in
   6.18 with the question "who can free `submit_wq` while a job work is still
   queued?", and check whether upstream has already fixed it.
3. Only then reach for KASAN again, and if so with those drivers back as
   *instrumented modules* in `/lib/modules/6.18.38-kasan`, plus
   `CONFIG_PSTORE`/ramoops so a report survives the lockup — nothing reaches the
   journal, because journald cannot flush during a panic.

Note that `CONFIG_MAGIC_SYSRQ` (in both debug fragments, with
`tools/serial/sysrq.py` to drive it over a UART BREAK) did **not** rescue this
particular wedge: with every CPU spinning interrupts-disabled, nothing runs the
handler. It is still worth having for the softer hangs.

**Still open:** the crash above, zero-copy display, HEVC in the shim, and 10-bit.

---

# HANDOFF — start here, 2026-08-16

**The decision already made:** do not patch mpv, ffmpeg or GStreamer. Adapt our
own code to fit them. That is what makes libva-v4l2-request the route — it is a
VA-API *driver*, so stock players use it unmodified.

**The goal for the next session:** ~~get `libva-v4l2-request` decoding H.264 on
the VE, validated to bit-exactness with no display involved~~ — **done, see
RESULT above.** What remains is the display path, and it is deliberately the
next thing rather than something to have done at the same time: with decode
proven bit-exact on its own, a playback failure now has only one place to hide.

## Board state as of this handoff

| | |
| --- | --- |
| Kernel | `6.18.38`, built from the current series, **persisted** to the FAT (`fatwrite mmc 1:2 h713-kernel.fit`) and booting from it via `bootcmd` |
| Rootfs | **reflashed 2026-08-16** with `--profile dev`, which now also carries `vainfo` and `gdb`; `/` is 4.5 G with ~3.1 G free |
| KMS | `sun50i-h713-afbd` autoloads at boot, but **did not probe on this boot** — the panel needs the U-Boot incantation below, which decode work skips. `/dev/dri` therefore has only `card0`/`renderD128` (panfrost) |
| VA-API | driver installed at `/usr/lib/aarch64-linux-gnu/dri/v4l2_request_drv_video.so`, source + build tree in `/root/libva-v4l2-request` |
| `/root` | `video-test/` (the five M1 vectors, `reference-md5.txt`, `m1-decode-test.sh`, `va-decode-test.sh`), `libva-v4l2-request/`, `h713-va-bringup.tar.gz` |
| Missing for this work | nothing |

The vectors and the patched source were put there by injecting a tarball into
`rootfs.ext4` with `debugfs -w -R "write ..."` before `img2simg` — no root
needed, and it beats pushing 2.4 MB over a serial console after every flash.

**The panel needs `h713_disp auto 0x34 logo` at the U-Boot prompt before `boot`,
every single time.** Without it the KMS driver correctly refuses to probe. For
decode-only work you can skip it — nothing about VA-API needs the display.

## Operational gotchas this session cost time on

- **Serial writes must be paced.** Long command lines sent in one burst come
  back with doubled characters (`ddrivers`, `afbbd`) and the *shell runs the
  corrupted line*. `tools/serial/console.py` writes one character at a time and
  is the tool to use. This looks like a display artifact and is not.
- **`modprobe` is a silent no-op if a stale build is already loaded.** udev
  autoloads the module at boot, so after copying a new `.ko` you must `rmmod
  sun50i_h713_afbd` first or you will test the old one and misread the result.
- **Fastboot needs a cold power cycle.** Linux leaves musb in a state U-Boot's
  warm-reset path does not reinitialise, so `reboot bootloader` lands at a
  prompt with `No USB controllers found`. Flashing the rootfs therefore needs a
  human to pull power and press a key during the boot delay.
- **A FIT transfer over serial is ~12 minutes** at 10.8 KB/s. Budget for it.
- **mpv needs `--drm-device=/dev/dri/card1`** — panfrost holds minor 0 as a
  render-only node.
- **WiFi gets you a shell, and it cannot carry a file.**
  `tools/wifi/sta-connect.sh` turns the boot hotspot into a station on a real
  network; ssh then answers in 3.6 ms. But **two of two** sustained transfers
  wedged the board hard — no ssh, no serial, tty echo alive and the shell dead,
  recoverable only by pulling power. The second attempt showed the mechanism: a
  10.8 MB `scp` sat at **zero bytes for six minutes** with the board still
  responsive, then the console printed `cmd timed-out` (the aic8800 firmware
  command/confirm crash path already documented for this chip) and it went down.
  Use it for a shell and log reading; use the serial console or a baked rootfs
  for anything file-sized. This kernel also has no `CONFIG_MAGIC_SYSRQ`, so
  there is no software way back — which is why the KASAN fragment enables it.
- **The board's clock can be months behind**, which makes `meson setup` abort
  with `Clock skew detected` on files newer than "now". `date -u -s` from the
  host, then `hwclock -w`.
- **`/tmp` is a 467 MB tmpfs.** One 1080p vector decodes to 186 MB of raw NV12,
  so a ladder run fills it and ffmpeg's ENOSPC leaves a *truncated file with a
  valid md5* — which scores as a MISMATCH and reads as a decode bug. Write raw
  output to `/var/tmp`.

## The plan, in order

Steps 1–5 are **done** (2026-08-16); they are kept here because they are how you
reproduce the result, not as work outstanding.

1. ~~Rebuild and reflash the rootfs~~ — done. `tools/rootfs/build.sh --ssh-key
   KEY --kernel-tree build/linux-6.18.38-<hash> --profile dev --image-size 4G`,
   then `run fastboot_mode` at the U-Boot prompt and `fastboot flash UDISK
   rootfs.simg`. The 1.4 GB sparse image uploads in 45 chunks / **6 min**.
2. ~~Clone and fix the driver~~ — done, and the fixes are now a tracked series
   in [`patches/libva-v4l2-request/`](../patches/libva-v4l2-request/) on the
   pinned PR #38 head. There were **three**, not two: the missing `#include`,
   the vestigial `hevc-ctrls.h`, and the one that actually blocked decoding
   (patch 0003, the empty bitstream queue).
3. ~~Build on the board~~ — done, ~40 s. Build **on the board** and nowhere
   else: the driver's entry point is `__vaDriverInit_<major>_<minor>` taken from
   the libva version at build time, so a host build against libva 1.24 produces
   a `.so` the board's 1.22 loader will never call.
4. ~~`vainfo`~~ — passes; five H.264 profiles, `VAEntrypointVLD`, nothing else
   advertised.
5. ~~Decode to a file and check it byte-for-byte~~ — **5 of 5 bit-exact**, via
   `tools/video/va-decode-test.sh`.
6. **The display path** — attempted, and it plays; see the section above for the
   `--hwdec=vaapi-copy` requirement and the intermittent kernel panic that is
   now the open problem. Note `card1` only exists if the panel was brought up
   first with `h713_disp auto 0x34 logo` at the U-Boot prompt; on a decode-only
   boot there is no KMS device at all. To get back to that prompt without a
   human at the power switch, `tools/serial/reboot-to-uboot.py` reboots and
   types through the autoboot delay.

## What to expect to go wrong

The prediction below was written before step 5 ran. It was right that the
runtime was the risk and wrong about where: the failure was not in the codec
mapping at all, but in buffer allocation — the shim assumed a VA-API client
contract (a preallocated surface pool) that ffmpeg no longer follows. Worth
remembering as a pattern: *the error message named the codec, and the codec was
fine.* `strace` found it in one run; reading h264.c would not have.

> The compile is measured and safe; the *runtime* is not. PR #38 is unmerged
> third-party work whose own commit message says "POC", developed against H3/A64
> VEs rather than this one. Our cedrus is proven bit-exact through GStreamer, so
> the kernel half is sound — what is unproven is whether this shim drives it
> correctly. If step 5 produces frames that are *close but not identical*,
> suspect the reference-list or DPB mapping before suspecting the hardware.

That last sentence never got tested: the frames were identical on the first run
that reached the decoder. The DPB and reference-list mapping in PR #38 is
correct for H.264 on this VE across all five vectors — and the ladder is built
to exercise exactly that, since `v03` and `v04` are `bframes=2:cabac=1:ref=3`,
so reference list construction and reordering are under test rather than
assumed.

The display path in step 6 wants EGL-on-GBM against a KMS driver that only
scans out physically contiguous memory. GBM's split render/display arrangement
should handle it, but nobody has run it here.

**Fallback that needs none of this:** GStreamer already decodes H.264 *and*
HEVC on this hardware today. If the shim disappoints, a GStreamer sink wrapping
the proven `gles-play` path gets hardware-decoded video to the panel with no
third-party dependency at all.

---

## Why mpv cannot do it today

V4L2 has two decoder APIs and they are not interchangeable:

| | who parses the bitstream | who speaks it |
| --- | --- | --- |
| **Stateful M2M** | the kernel driver | ffmpeg's `h264_v4l2m2m`, i.e. mpv |
| **Stateless / Request API** | *userspace* | GStreamer's `v4l2codecs` |

cedrus is stateless, because the Allwinner VE has no bitstream-parsing firmware
and mainline will not put an H.264 parser in the kernel. Measured on the board:
`libavcodec.so.61` contains `v4l2m2m` symbols and **zero** `v4l2request`
symbols. So there is no configuration that connects mpv to this hardware — the
V4L2 Request hwaccels are an out-of-tree series that LibreELEC has shipped since
2018 and that is [still not merged upstream](https://ffmpeg.org/pipermail/ffmpeg-devel/2024-August/332034.html).

This is also why `gles-play` works: it drives GStreamer, which does implement the
stateless protocol.

## The chain that does work

```
cedrus → V4L2 stateless → libva-v4l2-request → libva → ffmpeg → mpv
```

Everything right of the shim is stock and unpatched. The shim is a *translator*,
not a decoder: by the time VA-API is called, ffmpeg has already parsed the
bitstream and hands over picture and slice parameters, which the shim converts
into Request-API controls. That is the whole job.

[bootlin/libva-v4l2-request](https://github.com/bootlin/libva-v4l2-request) is
that shim. mpv and ffmpeg on our image already have VA-API compiled in
(`mpv --hwdec=help` lists `vaapi (h264-vaapi)`), so only the driver `.so` is
missing.

---

## H.264: nearly free

Master is a red herring — last commit **2019-05-17**, using the pre-stabilization
`V4L2_CID_MPEG_VIDEO_H264_*` controls, and its structs differ from the 6.18 uAPI
exactly as you would expect from that break (12 fields moved out of
`slice_params`, `pred_weights` split into its own control, `v4l2_h264_reference`
introduced).

**But [PR #38](https://github.com/bootlin/libva-v4l2-request/pull/38) already did
that port.** It targets kernel 5.14, uses all eight
`V4L2_CID_STATELESS_H264_*` controls — precisely the set cedrus registers in
6.18 — and assumes slice-based decode, which is the only mode cedrus offers.

Built here against modern kernel headers to measure rather than guess:

| errors | cause | fix |
| --- | --- | --- |
| 5 × struct redefinition, 3 files | vestigial bundled `include/hevc-ctrls.h` colliding with now-upstream HEVC controls | don't compile `h265.c` |
| 1 × `implicit declaration of 'request_log'` | missing `#include` in `h264.c` | one line |

**Zero H.264 uAPI mismatches.** Two supporting checks also came back clean:
`vaExportSurfaceHandle` with `DRM_PRIME_2` is implemented, so decoded surfaces
export as dma-buf — the same path `gles-play` already proved on this hardware —
and the ARM detiling assembly is `#ifdef __arm__`-guarded at both definition and
call site, so aarch64 builds and negotiates linear NV12.

## HEVC: a rewrite, but the hardware earns it

PR #38 ported H.264 and left HEVC on the 2019 API. `h265.c` uses three old
controls; 6.18 and cedrus need **eight**.

| | H.264 (ported) | HEVC (not ported) |
| --- | --- | --- |
| controls | 8 of 8 present | **3 of 8** |
| `sps` | identical | 30 → 26 fields, 9 removed |
| `pps` | identical | 32 → 17, **20 removed** |
| `slice_params` | ported | 38 → 30, 16 removed; `data_bit_offset` → `data_byte_offset` |
| `decode_params` | ported | **entirely new**, 13 fields |
| `scaling_matrix` | identical | **entirely new** |
| `dpb_entry` | +2 fields | `rps`/`pic_order_cnt` → `flags`/`pic_order_cnt_val` |
| effort | one `#include` | ~400 lines of `h265.c` largely rewritten |

Two kinds of work hide in that table. Most is **mechanical**: every individual
boolean (`amp_enabled_flag`, `cabac_init_present_flag`, …) collapsed into a
single `flags` bitfield, so every assignment changes shape. The part needing
thought is the **reference picture set restructure** — per-slice `rps` became
per-frame `decode_params` carrying `poc_st_curr_before/after` and `poc_lt_curr`,
so the shim must map VA-API's `ReferenceFrames` plus
`RefPicSetStCurrBefore/After/LtCurr` into that shape. `entry_point_offsets`
(WPP/tiles) is a new control on top.

The saving grace: GStreamer's `v4l2slh265dec` is a working implementation of
those exact eight controls against this exact kernel. The semantics can be read
off rather than derived.

---

## HEVC decodes on this hardware — measured 2026-08-16

Worth establishing *before* costing a port, because if the VE could not decode
HEVC the whole question would be moot. It can, and with no driver changes:

| vector | result |
| --- | --- |
| `h01-640x480-main` (25 frames) | **bit-exact**, md5 `9ebd49ec…` = host software reference |
| `h02-1280x720-main` (25 frames) | **bit-exact**, md5 `c898a8f0…` = host software reference |
| throughput | **~550 fps** — 500 frames of 720p in 0.905 s including process startup |

Method is the M1 gate's: deterministic `testsrc2` source, Annex-B elementary
stream, decoded on the host to linear NV12 as ground truth, decoded on the
target through `filesrc ! h265parse ! v4l2slh265dec ! video/x-raw,format=NV12`,
md5 compared. Forcing NV12 is required for the same reason as H.264 — unforced
it negotiates the 32x32 tiled `ST12`, which is correct output that can never
match a linear reference. Vectors are generated by
`tools/video/make-test-streams.sh` (`h01`, `h02`).

`gst-inspect-1.0` registers `v4l2slh265dec`, and `/dev/video0` advertises `S265`
(HEVC Parsed Slice Data) alongside `S264`, `MG2S` and `VP8F`.

## 10-bit does not work, and the blocker is in the kernel

`Main10` prerolls, reaches EOS in 40 ms having produced **zero frames**, and
forcing `P010_10LE` fails with `not-negotiated`.

The cause is not the H713. Our VE binds as `allwinner,sun50i-h6-video-engine`,
whose variant declares `CEDRUS_CAPABILITY_H265_10_DEC`, and the hardware
registers are there — `cedrus_regs.h` defines `VE_DEC_H265_SECOND_OUT_FMT_P010`
and `10BIT_4x4_TILED`, and `cedrus_h265.c` writes `VE_DEC_H265_10BIT_CONFIGURE`.
The kernel's uAPI even defines `V4L2_PIX_FMT_P010` and `NV15`.

But **`cedrus_video.c` exposes no 10-bit capture format at all** — its complete
list is `NV12`, `NV12_32L32`, `NV21`, `YUV420`, `YVU420` — and contains no
`bit_depth` handling. The capability bit only relaxes SPS *validation* in
`cedrus.c`; nothing downstream can express a 10-bit buffer, so nothing can
negotiate one.

So 10-bit HEVC needs a **cedrus patch** (add a 10-bit capture format gated on
`ctx->bit_depth`, wire the second-output-format registers), which is kernel work
in a staging driver — plausibly upstreamable, and independent of anything in
this document. Note also that the panel is 8-bit RGB after GPU conversion, so
10-bit buys source compatibility rather than visible quality.

---

## Scope, then

| item | effort | risk |
| --- | --- | --- |
| Build the shim for arm64, H.264 only | ~1 hour | low — measured, it's one `#include` and dropping `h265.c` |
| First decode, validated against the M1 ladder's references | a few hours | moderate — compiling is not decoding; PR #38 is unmerged WIP ("POC" in its own commit) developed against H3/A64-era VEs |
| mpv display path (`--hwdec=vaapi --vo=gpu --gpu-context=drm`) | unknown | **highest** — EGL-on-GBM against our KMS driver, never tried here, and the driver only scans out physically contiguous memory |
| HEVC in the shim | days | moderate — mechanical bulk plus the RPS restructure, with GStreamer as a reference |
| 10-bit HEVC | separate kernel work | unknown — no 10-bit format plumbed in mainline cedrus |

Recommended order: **decode-to-file first, display second.** Validate the shim
against the existing bit-exact references with no display involved, so a failure
lands in one half or the other rather than both.

And the standing alternative, which needs no shim at all: GStreamer already
decodes both H.264 and HEVC on this hardware today. What it lacks is only a sink
that reaches the panel without a CPU copy — see the GStreamer sink option in the
video-decode notes.
