# "WiFi cannot carry a file" -- reproduced, characterised, and A/B'd

> ## READ THIS FIRST: every measurement below was taken with NO ANTENNA ATTACHED
>
> Established after the fact (2026-08-17). The WiFi chip's antenna was not
> connected for any run in this document. Everything here was measured at
> -63...-71 dBm, which is **not** a property of the board, the driver or the
> firmware -- it is a disconnected antenna.
>
> This is not a footnote, it is the leading candidate explanation. The chain is
> the one `roadmap.md` already describes: weak RF -> low MCS -> retransmits ->
> more SDIO traffic per useful byte -> FIFO pressure -> `cmd53 fifo error`. Link
> rates observed were 18-54 Mbit/s on WiFi-6-capable silicon, which should have
> been a tell.
>
> **What this costs each finding:**
> - the transfer failure -- may be substantially or entirely RF, not driver/firmware
> - the -71 dBm "marginal window" from `roadmap.md` -- may itself describe an
>   antenna-less board rather than placement
> - the A/B throughput row -- already discounted, now worthless
> - the station-churn row (16 -> 0) -- **also confounded**, contrary to how it is
>   framed further down. A was measured near -71 dBm and B near -64. A client
>   reassociating at marginal signal is an ordinary explanation for 16/min. The
>   "less RF-sensitive, therefore solid" reasoning in the Comparison section does
>   not survive this.
>
> **Nothing here is retracted** -- the observations are real and the fault chain
> was genuinely captured. But no conclusion about *cause* should be drawn until
> all of it is repeated with the antenna connected. Treat this document as a
> record of what a no-antenna board does.
>
> ### RESOLVED: the antenna was NOT the cause (2026-08-17, later same day)
>
> Antenna reattached, signal went **-63/-71 dBm -> -31 dBm** (~10,000x more
> received power). The 8 MB `scp` **still fails**, on the 2026 driver, with the
> identical fault chain (one `cmd53 fifo error`, recovered, then `cmd timed-out`,
> then the data path dies while the AP keeps beaconing).
>
> And the decisive detail: it stalled at **1,827,840 bytes at -31 dBm -- the
> exact same byte count as the -63 dBm run**. Two runs 32 dB apart landing on the
> same number is not a marginal-link failure. **The stall is deterministic.**
>
> So the antenna caveat above is discharged, and it discharges *upward*: RF is
> ruled out as the cause, which makes the driver/firmware/SDIO path the live
> suspect after all. The confounder warnings on the A/B numbers still stand
> (those runs really were taken at weak signal), but the underlying failure is
> real and reproducible at excellent signal.

> **Result of the vendor rebase (added after the A/B, see "Comparison" below):**
> the 2026_0123 driver **eliminates the station churn** (16 -> 0 events/min) but
> **does not fix the file-transfer failure**. Same stall, same fault signature,
> same terminal wedge. Both halves of that sentence are now subject to the
> antenna caveat above.


2026-08-17, on the 2024_0109 driver + Mar 07 2024 firmware, kernel 6.18.38.
This is the Phase 0 baseline the vendor rebase (2026_0123) gets measured
against. **No fixes were attempted** -- the point here is only to say precisely
what happens. Raw capture: `reference/wifi-baseline-2024-driver.txt`.

## What was run

The board runs the baked-in hotspot: `hostapd` AP `spirits` on channel 6,
`192.168.4.1/24`, no uplink, `wpa_supplicant` masked. So the failing path is a
client pushing a file **to the board over the board's own AP** -- not STA mode.
A workstation joined that AP (`192.168.4.78`) and ran:

```
scp 8mb.bin root@192.168.4.1:/var/tmp/
```

## Result

**261,120 of 8,388,608 bytes (3.1%) in 300 s**, then killed by timeout. That is
~870 B/s effective. It matches the earlier field report ("10.8 MB scp moved 0
bytes in 6 min") closely enough to call it the same failure.

The kernel log gives a clean chain, with nothing else in between:

```
t=6306.619  sunxi-mmc 4021000.mmc: cmd53 fifo error (RINT=0x00000800 IDST=0x0000a000), retry 1/15
t=6306.619  sunxi-mmc 4021000.mmc: cmd53 fifo retry 1/15 (RINT=0x00000800 IDST=0x00000000)
t=6390.634  cmd timed-out
```

## What that chain says

1. **The FIFO recovery in kernel patch 0006 fired, and worked.** `IDST` goes
   `0x0000a000 -> 0x00000000` on retry 1 of 15. `docs/roadmap.md` recorded that
   this path had never been provoked and predicted it would need the
   -71...-80 dBm spot to fire. Signal here was **-71 dBm**. That prediction was
   exactly right.
2. **`cmd timed-out` followed 84 s later.** Not immediate, and only one FIFO
   error occurred -- so this is not a storm of SDIO errors dragging the command
   channel down. Either the single recovery left the transport in a state that
   only showed up later, or the two are independent and merely co-triggered by
   the same marginal RF.
3. **No `DHDISDOWN`, no `wlan error reset flow`.** The firmware did *not* enter
   its documented crash path. This is a quieter failure than the one the rootfs
   crash notifier was built for -- that notifier would not have fired here.

## End state -- the interesting part

After the stall:

- serial console: **wedged** (echoes characters, no prompt; Ctrl-C recovered it
  once earlier, then stopped working)
- SysRq: silent, but **inconclusive** -- `MAGIC_SYSRQ` is only in the
  `kasan`/`builtin-drivers` configs, not the shipping defconfig this board runs
- the AP is **still beaconing**, and the workstation is still associated at
  -65 dBm
- ping and TCP to `192.168.4.1`: **100% loss**

So the firmware is alive enough to beacon and hold an association autonomously,
while the SDIO data path between host and firmware is dead and the host side is
blocked. Recovery is a power cycle.

## What this does and does not establish

**Established.** The failure is reproducible on demand with an 8 MB scp. It is
in the AP-mode datapath. It involves the SDIO transport (`cmd53 fifo error`),
not just the firmware command channel. The board does not panic -- it wedges.

**Not established.** Whether the marginal RF is *causal* or merely a trigger.
-71 dBm is inside the window `roadmap.md` flagged as marginal, so RF placement
is a live confounder: a run at strong signal might not reproduce this at all.
Any A/B against the rebase must hold placement constant or it measures furniture.

**Also worth noting.** The 2026-07-22 bench recorded 384 MB clean with zero SDIO
errors, which is wildly better than 261 KB. `roadmap.md` does not say whether
that bench was AP or STA mode. If it was STA, then AP-mode bulk transfer has
never actually been benchmarked, and this is a previously unmeasured path rather
than a regression.

## Second, separate observation: station churn

Independently of the transfer, the client re-associates constantly --
**16 `del_station` events per minute**, measured over a clean 60 s window.
Each cycle completes fully (`associated` -> WPA 4-way -> `DHCPACK`) and then
repeats ~10 s later. `hostapd` logs no deauth reason. The driver leaks a station
slot each time: index climbed 15 -> 27, with `debugfs: '<mac>' already exists in
'rc'` and `Error while (un)registering debug entry for sta N` on every re-add.

Client-side WiFi power-save was **ruled out** -- disabling it left the rate
unchanged at 16/min.

Whether this churn causes the transfer failure or is a second bug sharing a root
cause is open. It is a strong candidate to check first after the rebase, because
a station torn down mid-transfer would produce exactly the observed stall.

## Measurement bug found along the way -- fixed

`tools/wifi/wifi-baseline.sh` counted SDIO faults by grepping `FIFO_RUN_ERROR`,
the name used throughout `roadmap.md`. That name is a **register-bit macro**
(`SDXC_FIFO_RUN_ERROR`) in the C source of `patches/kernel/0006` and never
reaches the kernel log. So `fault.fifo_run_error` read `0` through a run that
demonstrably had one -- it under-reported precisely the fault class that matters
most here.

Corrected against the literal format strings in patch 0006:

| field | matches |
|-------|---------|
| `fault.cmd53_fifo_error` | `cmd53 fifo error` -- FIFO/data-path stall |
| `fault.cmd53_phase_error` | `cmd53 phase error` -- CRC/timing class, separate retry budget |
| `fault.cmd53_retry_limit` | `retry limit reached` -- recovery exhausted, request failed |
| `fault.mmc_reset_timeout` | `DMA` / `FIFO` / `IDMA soft` `reset timeout` -- recovery itself failed |

**Counts are a lower bound.** The error line is `dev_warn_ratelimited`, so under
a storm the kernel drops repeats. Treat a jump from 0 as significant and the
absolute magnitude as approximate.

The `load.rx.*` per-phase counters were fixed the same way. The board still runs
the old copy at `/usr/local/sbin/wifi-baseline` -- it needs re-transferring
after the power cycle, or picking up from a rootfs rebuild.

---

# Comparison: 2024_0109 vs 2026_0123 (A/B, same board, same session)

Both arms: same kernel 6.18.38, same rootfs, same AP config, same 8 MB `scp`
from the same workstation, board unmoved.

| metric | A: 2024_0109 + Mar-2024 fw | B: 2026_0123 + `_h_` fw |
|--------|---------------------------|-------------------------|
| station churn (`del_station`/60 s) | **16** | **0** |
| 8 MB scp, best run | 0 B in 300 s | 1,827,840 B in 300 s |
| RF during that run | -71 dBm | -63 dBm |
| `cmd53 fifo error` | 1 | 1 |
| `cmd timed-out` | 1 | 1 |
| `DHDISDOWN` | 0 | 0 |
| terminal state | wedged; AP still beaconing | wedged; AP still beaconing |

## What is solid

**The station churn is fixed.** 16 events/min -> 0 over a clean 60 s window,
with `NetworkManager` logging 0 disconnects in 10 minutes where the old driver
produced 23 in 3. This is the strongest result in the A/B because it is a count
of discrete events rather than a throughput number, so it is far less sensitive
to the RF variation that contaminates everything else here. The station-slot
leak (index climbing, `debugfs: already exists`) is gone with it.

## What is not fixed

**Bulk transfer still fails.** Neither driver moved 8 MB in 300 s. The fault
signature is byte-for-byte the same shape -- one `cmd53 fifo error`, one
`cmd timed-out`, no `DHDISDOWN` -- and the terminal state is identical: the
firmware keeps beaconing and holding the association autonomously while the SDIO
data path is dead and userspace is blocked. Power cycle required either way.

## Limits of this comparison -- read before trusting the numbers

- **Two variables, not one.** The 2026 driver *cannot* run on the 2024 firmware
  set (see the `_h_` finding above), so "driver only" was not achievable. B is
  driver **and** `fmacfw` together.
- **RF was not held constant.** -71 dBm in A vs -63 dBm in B. `roadmap.md`
  identifies -71...-80 dBm as the marginal window, so A ran in it and B did not.
  The throughput difference (0 -> 1.8 MB) is therefore **not attributable to the
  driver** on this evidence.
- **One usable throughput sample per arm.** Later B runs failed at connect time
  ("No route to host", "Connection closed") rather than stalling mid-transfer,
  which is a different failure and not comparable.
- The churn result does **not** share these problems and stands on its own.

## What would sharpen it

Repeat both arms at matched RF, several runs each, with the board unmoved --
old modules are backed up on the board at `/root/oldmods/`, so swapping back is
a copy plus a reboot. Until then: churn fixed, transfer not fixed, cause of the
transfer failure still open.

---

# ROOT-CAUSE NARROWING: the failure is direction-specific (2026-08-17)

The clock experiments were a dead end (below). This was the test that mattered:
**run the same transfer in the opposite direction.**

| direction | what | size | result |
|-----------|------|------|--------|
| board **RX** (`scp` push *to* board) | WiFi -> SDIO -> host | 8 MB | **0-1,827,840 B in 300 s**, 1 `cmd53 fifo error`, 1 `cmd timed-out`, data path dies |
| board **TX** (`scp` pull *from* board) | host -> SDIO -> WiFi | 8 MB | **complete in 6 s**, md5 exact |
| board **TX** | same | 64 MB | **complete in 67 s (0.96 MB/s)**, md5 exact |

Same link, same session, same -32 dBm, same 25 MHz SDIO clock, minutes apart.
After **72 MB** of board TX: `cmd53 fifo error` **0**, `cmd53 phase error` **0**,
`cmd timed-out` **0**, `DHDISDOWN` **0**. A clean run in one direction and a
wedge in the other, at a 35x size ratio.

**So this is not the radio, not the link, not RF, and not the SDIO clock.** It is
the SDIO **receive** path -- card -> host -- under sustained load.

## Why this was missed for so long

The 2026-07-22 bench in `roadmap.md` that "proved" 384 MB clean was a **client
scp-pull over the AP** -- board TX. Sustained board **RX** appears never to have
been benchmarked. The bench was real; it just exercised the working direction.

## Why "buffer/descriptor exhaustion" is the leading hypothesis

- **The stall point is deterministic**: 1,827,840 bytes at -63 dBm and again at
  -31 dBm. A marginal link does not fail at a repeatable byte count; a finite
  resource does.
- **Exactly one `cmd53 fifo error`**, never a storm, and the retry *succeeds*
  (`IDST 0xa000 -> 0`). One hiccup, then the pipe never recovers -- that is a
  leak, not damage.
- **`cmd timed-out` arrives 84-160 s later**, not immediately: the command
  channel starves behind a dead RX path rather than failing with it.
- **Low-rate RX keeps working throughout** -- ssh, ping, DHCP, hostapd are all
  fine. Only *sustained* RX dies.
- The 2026 firmware carries RX exhaustion diagnostics the 2024 one does not:
  `rep: no rxmsg buffer, %d`, `rep: rxmsg no desc`, `rep: no buffer, %d`,
  `rep: no desc`. The vendor was chasing this class of bug.
- The driver preallocates RX buffers (`aic8800_fdrv/aicwf_rx_prealloc.c`), which
  is where a finite pool would live.

## Dead end, recorded so it is not repeated: the SDIO clock

`FEATURE_SDIO_CLOCK_V3`, board TX unaffected throughout:

| clock | inbound 8 MB result |
|-------|--------------------|
| 25 MHz (shipped) | 1,827,840 B, twice, identical |
| 150 MHz (vendor default) | 0 B |

Raising it did not help and plausibly hurt. **25 MHz stays.** No lower value was
tested: 12.5 MHz is not a value the vendor ever shipped, and testing invented
speeds is fishing rather than hypothesis-driven.

## Next test

Instrument the RX path rather than the link. Concretely: watch
`aicwf_rx_prealloc` pool occupancy and the firmware's `rep: no *` messages
(raise `aicwf_dbg_level` from `0x1` to include firmware logs, `0x403`) across an
inbound transfer, and see whether the pool is empty at the moment the stall
begins. If it is, this is a leak in RX buffer recycling and the byte count will
be a function of pool size.

---

# Two hypotheses tested and REFUTED (2026-08-17)

Both were tested on hardware, single-variable, and both were wrong. Recorded so
nobody spends the time again.

## 1. RX skb allocation failure -- REFUTED

**Hypothesis.** `aicwf_sdio_readframes()` (the `#else`, non-prealloc branch, which
is the one built: `CONFIG_PREALLOC_RX_SKB ?= n`) does:

```c
skb = __dev_alloc_skb(size, GFP_KERNEL);
if (!skb) return NULL;              /* silent -- no log, no counter */
ret = aicwf_sdio_recv_pkt(sdiodev, skb, size);
```

On alloc failure it returns **before** `recv_pkt`, so the card's pending data is
never drained and its FIFO would stay full -- which would produce
`FIFO_RUN_ERROR` on the next CMD53. The path is completely silent upstream.

**Test.** Rebuilt `aic8800_fdrv` with `pr_err_ratelimited` on both the alloc
failure and the `recv_pkt` failure branches; ran the 8 MB inbound transfer.

**Result.** **Zero** `aicwf-instr` hits, while `cmd53 fifo error` = 1 and
`cmd timed-out` = 1 as usual. Allocation is not failing and `recv_pkt` is not
returning an error. In hindsight this is consistent: patch 0006 *recovers* the
FIFO error, so `recv_pkt` returns success -- the data is read.

Note the `aicwf_rx_prealloc.c` pool (30 buffers x 32 KB) is **not compiled in**
at all, so it was never a suspect either.

## 2. Driver TCP-ACK filtering -- REFUTED

**Hypothesis.** The driver ships `CONFIG_FILTER_TCP_ACK = y` (both 2024 and 2026)
and implements `is_drop_tcp_ack()` / `intf_tcp_drop_msg()` -- it deliberately
drops TCP ACKs. That logic engages **only when the board is receiving**, which is
exactly the failing direction, and over-dropping would close the sender's window
and stall the stream with no SDIO error at all. Being identical in both drivers
would also explain why the rebase did not fix it.

**Test.** Rebuilt with `CONFIG_FILTER_TCP_ACK=n`, confirmed `is_drop_tcp_ack` was
absent from the module, retested.

**Result.** Identical failure -- 0 bytes, 1 `cmd53 fifo error`, 1 `cmd timed-out`.

Incidental finding while doing it: disabling that flag **breaks the build**.
`aic_priv_cmd.c` reaches `vmalloc` only via
`rwnx_defs.h -> #ifdef CONFIG_FILTER_TCP_ACK -> aicwf_tcp_ack.h -> net/tcp.h`.
Latent fragility in the vendor tree; worth an explicit include if that flag is
ever turned off for real.

## What survives: a perfect correlation

| run | direction | `cmd53 fifo error` | outcome |
|-----|-----------|--------------------|---------|
| A, B, C, E, H, I | RX inbound | **1** | fails |
| F (8 MB), G (64 MB) | TX outbound | **0** | completes, md5 exact |

Every failing run has exactly one FIFO error; every successful run has none.
Never any other combination, across driver versions, SDIO clocks, RF levels and
two instrumented builds.

## Refined hypothesis (untested): patch 0006's recovery is incomplete

The FIFO error is on the SDIO **read** path (card -> host), which only carries
load in the RX direction. `patches/kernel/0006` retries it and the *MMC layer*
reports success (`IDST 0xa000 -> 0`), so the aic8800 driver sees no error -- both
refutations above are consistent with that.

But the aic8800 SDIO protocol is framed: read `intstatus` to get a block count,
then read exactly that many blocks. If the retried CMD53 does not restore the
card's read pointer to precisely where the host thinks it is, host and card
desynchronise. From then on every read is misframed, RX is dead, and the command
channel eventually times out -- which is the 84-160 s gap we keep seeing.

That would mean **the trigger is a sunxi-mmc/SoC FIFO underrun and the fatal part
is our own recovery**, not the vendor driver at all. It also fits TX being clean:
writes do not use that path.

Next step if pursued: log around the patch-0006 retry (`error_rint`,
`idma_int_sum`, block count, and the aic8800's `intstatus` before/after) and
check whether the post-retry read length matches what the card advertised.

---

# ROOT CAUSE FOUND: patch 0006's FIFO recovery disables the SDIO interrupt

**The bug is ours, in `patches/kernel/0006`, not in the vendor driver.**

## The evidence that ended it

After a failed inbound transfer, with the board still alive and `wlan0` UP:

```
256:  3168 -> 3168    GICv2 73  sunxi-mmc
257:  8663 -> 8663    GICv2 72  sunxi-mmc     (30 seconds apart)
```

**Zero SDIO interrupts in 30 s.** The controller has stopped interrupting
entirely. That single fact explains every earlier negative result: no RX frames
arrive because the interrupt that would fetch them never fires -- so there are no
skb allocation failures, no `recv_pkt` errors, and no framing desync. Nothing is
read at all.

## The mechanism

`sunxi_mmc_init_host()` arms the controller:

```c
rval = mmc_readl(host, REG_GCTRL);
rval |= SDXC_INTERRUPT_ENABLE_BIT;      /* BIT(4) -- global interrupt enable */
rval &= ~SDXC_ACCESS_DONE_DIRECT;
mmc_writel(host, REG_GCTRL, rval);
```

and also programs `REG_DLBA` (the IDMA descriptor list base), `REG_FUNS`,
`REG_DBGC`, `REG_RINTR`.

Patch 0006's CMD53 recovery does a **full controller reset**:

```c
clk_disable_unprepare(host->clk_mmc);
if (!IS_ERR(host->reset))
        reset_control_reset(host->reset);     /* clears GCTRL, DLBA, ... */
ret = clk_prepare_enable(host->clk_mmc);
...
mmc_writel(host, REG_SD_NTSR, ntsr_saved);            /* restored */
writel(drv_dl_saved, host->reg_base + SDXC_REG_DRV_DL); /* restored */
```

It restores **only** the two timing registers. It never restores `REG_GCTRL`
(grep for `REG_GCTRL` inside the retry block: **0 hits**), never restores
`REG_DLBA`, and never re-runs the init sequence.

So `SDXC_INTERRUPT_ENABLE_BIT` is cleared and never set again. The retried CMD53
itself still completes -- which is why the MMC layer reports success
(`IDST 0xa000 -> 0`) and why every driver-level hypothesis came back clean -- but
from that moment the host is deaf.

## Why this fits every observation

| observation | explanation |
|---|---|
| direction-specific (RX fails, TX fine) | the FIFO error only occurs on CMD53 **reads**, which only carry load inbound. TX never triggers the recovery, so TX never disarms the interrupt. 72 MB of TX ran with **0** FIFO errors. |
| exactly one `cmd53 fifo error`, never a storm | after the first one the controller is deaf, so no further transfers happen to fail |
| the retry "succeeds" | it does -- the data transfer completes; only the interrupt enable is lost |
| `cmd timed-out` 84-250 s later | the aic8800 command channel also waits on completion interrupts |
| RX dies but the AP keeps beaconing | the firmware runs autonomously; it is the host link that is deaf |
| survives 32 dB of RF improvement | nothing to do with the radio |
| unaffected by SDIO clock (25 vs 150 MHz) | nothing to do with bus speed |
| identical on 2024 and 2026 drivers | the bug is in the kernel patch both share |

## Status

**Mechanism confirmed by structure and by the frozen interrupt counters;
causality not yet proven by experiment.** The proof is to restore `GCTRL` (and
`DLBA`) after the reset -- or simply re-run the init sequence -- and check
whether inbound transfers then complete. That is a small change to patch 0006
and it is the next thing to do.

Historical note: `roadmap.md` records that this recovery path had **never been
provoked** when patch 0006 was benchmarked -- the 2026-07-22 bench was a
scp-*pull* (TX), which never triggers it. So the recovery code shipped having
never once executed. The first time it ran was this session.

---

# ACTUAL ROOT CAUSE: the CMD53 retry never completes the request,
# deadlocking the SDIO IRQ thread

**Supersedes the GCTRL section above.** That section identified a real defect but
was wrong about it being the cause -- see "correction" below.

## The evidence

With the board wedged after a failed inbound transfer:

```
PID  STAT  WCHAN                   COMMAND
152  D     mmc_wait_for_req_done   ksdioirqd/mmc1

[<0>] mmc_wait_for_req_done+0x2c/0x10c
[<0>] mmc_wait_for_req+0xb8/0xcc
[<0>] mmc_io_rw_extended+0x198/0x2e8
[<0>] sdio_io_rw_ext_helper+0xf4/0x1c8
[<0>] sdio_readsb+0x20/0x2c
[<0>] aicwf_sdio_readframes+0x68/0xc0 [aic8800_fdrv]
[<0>] aicwf_sdio_hal_irqhandler+0x268/0x34c [aic8800_fdrv]
[<0>] process_sdio_pending_irqs+0x5c/0x1e0
[<0>] sdio_irq_thread+0x78/0x1a0
```

and the controller registers:

```
GCTRL = 0x20000330   BIT(4) interrupt-enable SET
IMASK = 0x0000BBCA   BIT(16) SDXC_SDIO_INTERRUPT *not* set
RINTR = 0x00000000   nothing pending
```

## The chain

`CONFIG_OOB = n`, and the driver calls `sdio_claim_irq()` -- so it depends
entirely on the **in-band SDIO card interrupt**. The Linux SDIO core handles that
by masking the card IRQ, waking `ksdioirqd`, running the card's handler, and
re-enabling the IRQ *after the handler returns*.

1. Card raises its IRQ. Core masks `SDXC_SDIO_INTERRUPT`, wakes `ksdioirqd`.
2. `ksdioirqd` -> `aicwf_sdio_hal_irqhandler` -> `readframes` -> `sdio_readsb`
   issues the CMD53 **read**.
3. That CMD53 hits the FIFO underrun. Patch 0006's retry runs.
4. **The re-issued request never completes.** `mmc_wait_for_req_done()` has no
   timeout, so `ksdioirqd` blocks in D state forever.
5. Because the handler never returns, the core **never re-enables**
   `SDXC_SDIO_INTERRUPT` -- hence `IMASK` bit 16 = 0.
6. No further card interrupts -> inbound data is never fetched -> RX is dead.
7. `cmd timed-out` follows minutes later: the aic8800 command channel needs the
   same thread.
8. Everything else keeps running -- board alive, AP beaconing, TX fine.

## Why this explains every observation

- **Direction-specific**: only inbound traffic drives the card-interrupt path
  through `ksdioirqd`. TX never touches it -- 72 MB of outbound ran with zero
  faults.
- **Deterministic**: the first FIFO error on a read deadlocks the thread. There
  is no second one because nothing else is ever issued.
- **Survives RF and clock changes**: neither affects whether the request is
  completed.
- **Identical on 2024 and 2026 drivers**: the defect is in the kernel patch both
  share.
- **Silent**: no driver-level error, because from the driver's point of view the
  read simply never returns.

## Correction: GCTRL was a real defect, but not the cause

The earlier section is right that `reset_control_reset()` clears
`SDXC_INTERRUPT_ENABLE_BIT` and the retry never restored it -- with interrupts
globally off, the re-issued CMD53 could never complete, which would produce this
same deadlock. That fix was applied and verified in-register
(`GCTRL = 0x20000330`, BIT(4) set).

**But the deadlock persists with GCTRL restored.** So the reset clears more state
than GCTRL alone (or the manual-stop leaves the card unable to answer), and the
re-issued request still never completes. The GCTRL restore is necessary but not
sufficient, and should be kept.

## Two fixes, and the second matters more

1. **Make the retry actually work** -- restore the full controller state after
   `reset_control_reset()`. Started (GCTRL/DLBA/IMASK/FTRGL/TMOUT/RINTR/DBGC/
   FUNS); evidently still incomplete. Calling `sunxi_mmc_init_host()` and then
   re-applying the saved timing may be the more reliable route than enumerating
   registers by hand.

2. **Guarantee the request is always completed.** Whatever else happens, the
   retry path must never leave an mrq outstanding -- on any failure it must call
   `mmc_request_done()` with an error. That converts a permanent, power-cycle-only
   wedge into a recoverable I/O error that the aic8800 driver can report. This is
   the more important of the two: it removes the *class* of failure rather than
   one instance of it, and it is what makes the difference between "WiFi drops a
   frame" and "the board needs unplugging".

Note the reference trees `local/linux-6.16.7` and `local/h713-arm64/linux-6.16.7`
carry the identical retry code, so both have this latent deadlock too.

---

# Bottom-up verification: healthy baseline, and what the watchdog fixed

Run bottom-up as suggested: establish what "working" looks like *before*
provoking anything, instead of reasoning about register values from source.

## Healthy vs stuck, observed

Sampled six times on an idle, working link (mmc1 = SDIO, base 0x04021000):

```
HEALTHY (idle):   GCTRL=0x20000010   IMASK=0x00010000   RINTR=0   IDIE=0
STUCK (old bug):  GCTRL=0x20000330   IMASK=0x0000BBCA   RINTR=0
```

`IMASK=0x00010000` is exactly `SDXC_SDIO_INTERRUPT` (BIT 16) and it is **stable**
-- it does not oscillate between the core masking and re-enabling it, so
`bit16 = 0` in the stuck state really is anomalous, not a sampling artifact.
The stuck value `0xBBCA` is the per-request mask (error + data-over bits) with
the card IRQ masked: the controller sitting mid-transfer, waiting for a
completion that never arrives.

## Phase 2 result: inbound fails at 256 KB

**A 256 KB inbound transfer fails**, with the same `cmd53 fifo error` signature.

This kills the "sustained load" framing that has been carried through this whole
document. It is not a throughput or contention problem: the SDIO **read** path
hits `FIFO_RUN_ERROR` almost immediately on any inbound bulk transfer, while
72 MB of outbound produced zero errors. Earlier runs that moved 1.8 MB before
stalling were the lucky end of the distribution, not the typical case.

## The retry watchdog works, and fixes a real bug

Added `retry_timer` to the host: armed when the retried CMD53 is handed to
hardware, and on expiry it fails the request with `-ETIMEDOUT` and calls
`mmc_request_done()`.

Verified on hardware:

| | before watchdog | after watchdog |
|---|---|---|
| `ksdioirqd/mmc1` | **D** at `mmc_wait_for_req_done` (forever) | **S** at `sdio_irq_thread` |
| `IMASK` bit 16 | 0 -- card IRQ never re-enabled | **set** (0x0001BBC6) |
| watchdog log | -- | `cmd53 retry did not complete within 2000 ms - failing the request` |

So the **kernel-side deadlock is fixed**: the SDIO IRQ thread is no longer
wedged in uninterruptible sleep, and the core re-arms the card interrupt.

## But WiFi still does not survive

After the watchdog fires, the link is still unusable -- no ssh, outbound pull
fails, and the SDIO IRQ counter freezes again. `cmd timed-out` follows ~56 s
later. So the aic8800 driver does not recover from the failed read: its firmware
command channel dies and the interface stays down until reboot.

**Net position.** Two separable problems:

1. **Kernel thread deadlock** -- real, serious (an uninterruptible kernel thread
   is worse than an I/O error), and now **fixed and verified**. Worth keeping on
   its own merits regardless of the rest.
2. **SDIO reads fail on this board** -- unfixed. `FIFO_RUN_ERROR` on inbound
   CMD53 at sizes as small as 256 KB, the controller cannot recover the
   transfer, and the aic8800 driver cannot recover from the resulting error.

The second is the actual "WiFi cannot carry a file" bug and it remains open.

---

# Ground truth from the stock kernel: what its MMC driver does that ours does not

Rather than keep guessing at register values, the stock Android kernel was
extracted and inspected.

## Extraction

`local/stock-boot/boot_a-board-b.img` is an **Android boot image header v3**
(the version field is at offset 40; offset 12 is `ramdisk_size`, *not*
`kernel_addr` -- parsing it as v0/v2 yields garbage). Kernel payload starts at
4096, uncompressed:

```
Linux version 5.4.99-00049-g34f0974adef4-dirty
  (arm-linux-gnueabi-gcc ... Linaro GCC 5.3)  #1006 SMP  Mon Sep 22 09:29:12 CST 2025
```

Note stock runs a **32-bit ARM** kernel; our port is arm64. Extracted copy:
`scratchpad/stock-kernel.bin` (not committed).

## FTRGL is NOT the difference -- speculation closed

The literal `0x20070008` appears **exactly once** in the stock kernel, in a
literal pool immediately after a function that accesses register offset `0x40`
(`ldr r3, [r2, #64]` -- FTRGL). **Stock programs the same FTRGL value we do.**

So the earlier "RX trigger 7 vs burst 8" idea is dead, and it deserved to be:
mainline uses this value too, and on the usual Allwinner convention `RX_TL=7`
means "trigger at >7", which matches burst 8 correctly. Changing it would have
been the same unfounded move as testing an invented SDIO clock.

Corroborating: the **eMMC** controller (mmc0) runs with `FTRGL = 0x00000000` and
works fine, while the SDIO controller (mmc1) has `0x20070008` and fails reads.
FTRGL is not what separates them.

## What stock actually has that we lack

Stock supports six controller revisions and carries **five v5p3x-specific
routines** -- v5p3x is our controller:

```
sunxi_mmc_clk_set_rate_for_sdmmc_v5p3x
sunxi_mmc_init_priv_v5p3x
sunxi_mmc_judge_retry_v5p3x
sunxi_mmc_restore_spec_reg_v5p3x
sunxi_mmc_thld_ctl_for_sdmmc_v5p3x
```

Our mainline-derived driver has **no equivalent of any of them**. Three matter
directly to what we have been chasing:

| stock routine | what we do instead | relevance |
|---|---|---|
| `thld_ctl_for_sdmmc_v5p3x` | **nothing** -- we only *read* THLD (0x100) for error dumps, never program it. Live on the board: `THLD = 0x00000000`. | The card **read** threshold. It gates when the controller will start a read against available FIFO space -- i.e. exactly the read-side overflow protection whose absence produces `FIFO_RUN_ERROR` on inbound CMD53 while writes stay clean. |
| `restore_spec_reg_v5p3x` | hand-rolled: restore `NTSR` + `DRV_DL` only | Stock has a dedicated "restore special registers" step for this controller. We found empirically that our reset loses `GCTRL`/`DLBA`/`IMASK`; stock treats register restoration as a first-class, version-specific operation. |
| `judge_retry_v5p3x` | hand-rolled CMD53 retry with fixed budgets | Stock makes the retry decision version-aware. Ours is a generic phase/FIFO split invented for patch 0006. |

Also present and absent from ours: `sunxi_mmc_set_rdtmout_reg_v4p6x` (read
timeout register), `sunxi_mmc_reg_ex_res_inter`.

## Assessment

The read-threshold gap is the strongest lead yet, and unlike every previous
hypothesis it is **not speculative**: stock has a dedicated routine for it on
this exact controller revision, ours has none, and the register reads zero on
the running board. It is also read-specific, which matches the one hard fact
that has survived every test -- inbound fails, outbound is clean.

Next step would be to implement a `thld_ctl` equivalent for v5p3x. That needs
the values stock writes, which means disassembling
`sunxi_mmc_thld_ctl_for_sdmmc_v5p3x` from the extracted kernel, or recovering
the Allwinner BSP source for it -- not inventing them.

## Disassembly of `sunxi_mmc_thld_ctl_for_sdmmc_v5p3x` -- and why the lead died

Located by scanning for ARM32 `STR Rd,[Rn,#0x100]` near the MMC code (anchored on
the FTRGL literal). File offset 7773612 in `stock-kernel.bin`. Recovered
semantics:

```asm
ldr   r3, [r2, #8]          ; data->blksz          (mmc_data offset 8, Linux 5.4)
ldr   ip, [r2, #24]         ; data->flags
cmp   r3, #4096             ; blksz < 4096
ands  r0, r0, ip, lsr #9    ; AND (flags >> 9) = MMC_DATA_READ    <-- read-only
ldrb  ip, [r5, #70]
add   r3, r3, ip, lsl #2
cmp   r3, #1024             ; blksz + (x<<2) <= 1024
ldrb  r3, [r1, #16]         ; ios->timing
cmp   r3, #9                ; timing == 9  (HS200)
cmpne r1, #1                ;   or timing-5 <= 1  -> 5 (SDR50) / 6 (SDR104)
bhi   <disable>
; enable:
ldr   r3, [r0, #0x100]
bic   r3, r3, #0x0FF00000   ; \ clear bits [27:16] = threshold size
bic   r3, r3, #0x000F0000   ; /
orr   r3, r3, r4, lsl #16   ; size = blksz << 16
orr   r4, r3, #1            ; bit 0 = read-threshold enable
; disable:
bic   r4, r4, #1
str   r4, [r3, #0x100]
```

So the register contract is now known exactly: **THLD bits [27:16] = read
threshold size, bit 0 = enable**, applied only to reads.

**But it does not apply to us.** Our SDIO link runs at
`timing spec: 2 (sd high-speed)` (`/sys/kernel/debug/mmc1/ios`), and stock only
enables the threshold for timing 5/6/9. **Stock would leave `THLD = 0` on this
link too** -- exactly what we observe. It is not a difference, and implementing
it would change nothing at this bus speed.

## Score so far on stock-vs-ours

| candidate difference | verdict |
|---|---|
| `FTRGL` value | **same as stock** (`0x20070008`, one literal, beside FTRGL-offset code) |
| card read threshold (`THLD`) | **same as stock** at our timing -- stock disables it below SDR50 |
| `GCTRL` BIT(4) semantics | confirmed from stock's own code (`orr r5,#16`), and our restore is correct |
| `restore_spec_reg_v5p3x` | **stock has it, we do not** -- still an unexamined difference |
| `judge_retry_v5p3x` | **stock has it, we do not** -- still an unexamined difference |

Two speculative register leads are now closed with evidence rather than opinion.

## The obvious next move

We have been comparing our *driver* against stock's *source*, but never against
stock's *running configuration*. Per `memory: vendor-stack-is-bootable`,
`run switch_vendor` boots the full vendor Android stack on this board. Booting it
and reading `/sys/kernel/debug/mmc1/ios` plus the live `GCTRL/FTRGL/THLD/TMOUT`
registers would answer, with no inference at all:

- what **timing and clock** stock actually runs the AIC8800 SDIO link at (if it
  uses SDR50, the read threshold *is* live for stock and dead for us -- a real,
  concrete difference)
- what the controller registers hold during healthy sustained RX
- whether stock can do a large inbound transfer over the same link

That converts the entire remaining question from code archaeology into a direct
A/B against a known-good system.

---

# THE CONFIGURATION DIFFERENCE: our DT never enables the UHS modes

Found by comparing the stock device tree against ours, after booting the vendor
U-Boot proved awkward (see below). This is the first difference between stock and
our stack that is **unambiguous and not speculative**.

## Stock's SDIO node vs ours

Stock (`local/h713-lab/analysis/board-a-stock-20260622/vendor_boot_a-unpack/dtb.dts`,
the `sunxi-mmc-v5p3x` node carrying `cap-sdio-irq`):

```dts
compatible = "allwinner,sunxi-mmc-v5p3x";
max-frequency = <0x2faf080>;   /* 50 MHz */
cap-sd-highspeed;
keep-power-in-suspend;
sd-uhs-sdr25;
sd-uhs-sdr50;                  /* timing 5 */
sd-uhs-ddr50;
sd-uhs-sdr104;                 /* timing 6 */
cap-sdio-irq;
```

Ours (`patches/kernel/0024`, `mmc@4021000`):

```dts
compatible = "allwinner,sun50i-h713-mmc";
bus-width = <4>;
cap-sd-highspeed;
cap-sdio-irq;
no-mmc;
no-sd;
/* no max-frequency, no sd-uhs-* of any kind */
```

| property | stock | ours |
|---|---|---|
| `max-frequency` | 50 MHz | **absent** |
| `sd-uhs-sdr25` / `sdr50` / `ddr50` / `sdr104` | **all four** | **none** |
| `keep-power-in-suspend` | yes | absent |

Consequence, measured on the running board: `/sys/kernel/debug/mmc1/ios` reports
`timing spec: 2 (sd high-speed)` at 25 MHz. Without the `sd-uhs-*` properties the
core cannot negotiate anything faster, so the link is capped at SD-HS.

## Why this reconnects to the read threshold

`sunxi_mmc_thld_ctl_for_sdmmc_v5p3x` enables the card read threshold **only** for
timing 5 / 6 / 9. Stock declares SDR50 and SDR104, so on stock the link runs at
timing 5 and the read threshold **is active**. On ours the link is stuck at
timing 2, where the threshold is never enabled -- and our driver has no threshold
support at all.

So the earlier conclusion ("the threshold is a no-op for us, therefore not a
difference") was correct as far as it went, but it had the causality backwards:
**the threshold is inert for us because our DT keeps the link in a mode where it
does not apply.** The DT omission is upstream of it.

**Stated carefully:** this is a confirmed configuration divergence with a
plausible mechanism, not a proven cause. It is odd on its face that the *slower*
mode is the one that overflows the read FIFO, and that wrinkle is unexplained --
at SD-HS stock would not enable the threshold either. What can be said without
overreach is that stock runs a mode we have never run, with a read-path
protection we have never had, and that this is the only unambiguous
configuration difference found in the whole investigation.

## Next test (non-speculative)

Add stock's declared capabilities to our `mmc@4021000` node -- `max-frequency`,
`sd-uhs-sdr25/sdr50/ddr50/sdr104`, `keep-power-in-suspend` -- rebuild, and check:

1. does `/sys/kernel/debug/mmc1/ios` then report `timing spec: 5` (SDR50)?
2. does an inbound transfer work?

We are not inventing values here: they are copied from the vendor's own device
tree for this exact board and controller.

If the link comes up at SDR50 but reads still fail, the next step is implementing
`thld_ctl` -- whose register contract is now fully recovered (THLD bits [27:16] =
`blksz`, bit 0 = enable, reads only).

## Note on the vendor-boot detour

`boot_vendor` (magic to an RTC scratch register + reset) is a **no-op** while our
boot0 is installed -- it simply reboots into our stack.

`switch_vendor` works and installs the vendor first stage (verified: it writes
64 blocks from sector 0x100 to sector 0x10). After a cold boot the board comes up
in the **vendor U-Boot 2018.05** (Allwinner, arm-linux-gnueabi-gcc) rather than
ours. But its environment is the generic default (`bootcmd=run distro_bootcmd`,
which is undefined) and `BOOTMODE=standby`, so Android does not auto-boot;
`sunxi_flash read 0x48000000 boot_a` also returned no valid Android header. Full
vendor Android boot was not achieved this session.

**The board is currently left in vendor-boot mode.** Restoring our stack means
putting our boot0 back at sector 0x10 (FEL, per `memory: vendor-stack-is-bootable`).

## Test: enabling stock's UHS modes -- FAILS, and says why

Added stock's declared capabilities to `mmc@4021000` (`sd-uhs-sdr25/sdr50/ddr50/
sdr104`, `max-frequency` 25 -> 50 MHz), rebuilt, RAM-booted.

**Result: SDIO init hangs.** `systemd-modules-load.service` ran to its 6-minute
timeout, retried, timed out again at 3 minutes, and **FAILED**. The board reached
`multi-user.target` but with no aic8800 modules, no `wlan0`, no hotspot, no ssh --
and the serial console went silent (getty never became usable).

This is not outcome 1, 2 or 3 from the plan; it is a fourth: the link does not
merely stay at timing 2, it **cannot initialise at all**.

## Why -- the missing piece is the per-speed delay tuning

Stock's SDIO node carries delay tables our DT and driver have no equivalent of:

```dts
sunxi-dly-52M-ddr4 = <0x01 0x00 0x00 0x00 0x02>;
sunxi-dly-104M     = <0x01 0x01 0x00 0x00 0x01>;
sunxi-dly-208M     = <0x01 0x00 0x00 0x00 0x01>;
ctl-spec-caps      = <0x08>;
```

These feed `sunxi_mmc_clk_set_rate_for_sdmmc_v5p3x` / `sunxi_mmc_set_clk_dly` --
stock **retunes the sampling delays for every speed mode**. Our driver hardcodes
a single `NTSR = 0x81710110` chosen for 25 MHz and never changes it.

So declaring SDR50 asks the controller to sample at a rate its delay
configuration was never tuned for. That also retro-explains the DT comment
recorded during the original bring-up -- *"the AIC8800 port hits CMD53 DMA errors
on large transfers at 50 MHz"* -- as the same problem, hit from the other side.

Also confirmed from the stock DT: it has **no `vqmmc-supply`** (and no
`vmmc-supply` either), so the 1.8 V-signalling concern was not the blocker.

## Ordering for whoever picks this up

The UHS modes cannot be enabled on their own. The dependency chain is:

1. implement per-speed delay tuning (`set_clk_dly` equivalent) using the values
   in the stock DT above -- **not invented**, read from the vendor's own tree
2. *then* declare the `sd-uhs-*` capabilities
3. *then* the link can reach timing 5, where `thld_ctl` becomes applicable
4. *then* implement `thld_ctl` (register contract already recovered: THLD
   bits [27:16] = `blksz`, bit 0 = enable, reads only)

Each step is a prerequisite for the next. Attempting step 2 alone -- which is
what this test did -- breaks SDIO init outright.

**Board state:** the change was RAM-loaded only. A power cycle returns the board
to the flashed 25 MHz kernel, which works. `patches/kernel/0024` was never
modified; the edit lives only in `build/linux-debug-mmcinstr`.

---

# 2026-08-18 continuation — UHS works, startup CRCs removed, board RX fixed

This section supersedes the old “ordered next steps” above. The investigation
continued from repeated cold boots at the U-Boot prompt and ended with the
original acceptance test passing in both directions. No image was flashed.

## 1. Recovered and implemented the v5p3x controller contracts

The mainline host was extended with the pieces recovered from Allwinner's
v5p3x driver:

- separate per-speed command/data drive and sample phases
- the v5p3x CMD11 and update-clock voltage-switch bits
- v5p3x `WAIT_PRE_OVER` behavior
- v5p3x read-threshold register programming
- the stock v5p3x FIFO trigger value (`FTRGL=0x200700f8`)
- UHS declarations in the H713 SDIO node
- AIC `FEATURE_SDIO_CLOCK_V3=0`, so the vendor module no longer overwrites the
  rate negotiated by the MMC core

This became `patches/kernel/0043-mmc-sunxi-v5p3x-delays-threshold-and-uhs.patch`
and was committed as:

```text
df1738e mmc: sunxi: add H713 v5p3x UHS negotiation
```

### Hardware result at 50 MHz

The board successfully negotiated and enumerated:

```text
4-bit UHS-SDR104
clock/actual: 50000000 Hz
DRV=00030000
NTSR=81710110
mmc1: new UHS-I speed SDR104 SDIO card
```

Therefore the UHS transition and controller command path work. The boundary is
equally important: the first 512-byte CMD53 failed at 50 MHz. A bounded sweep
of seven command/data sample and data-drive combinations produced data-CRC or
end-bit errors (`RINT=0x80` or `0x8000`), always with `IDST=0`. UHS negotiation
works; 50 MHz UHS payload transfer is not yet reliable.

## 2. Repaired the retry mechanism without treating it as the solution

`reset_control_reset()` erases the SDIO bus clock and width. The old retry path
restored timing registers but then reissued CMD53 with no card clock and in
one-bit mode, so it could never complete. The repair saves/restores `CLKCR` and
`WIDTH`, turns the output clock back on, cancels a retry watchdog when a retried
request reaches IRQ, and makes the phase sweep match the v5p3x fields.

This became:

```text
patches/kernel/0044-mmc-sunxi-restore-bus-state-for-cmd53-phase-retry.patch
977244c mmc: sunxi: restore bus state before CMD53 retry
```

The seven-state 50 MHz run completed every attempt and then failed cleanly;
`ksdioirqd/mmc1` did not wedge. This proved that recovery mechanics were fixed,
not that recovery could make an invalid sampling state reliable.

## 3. CRC is MMC/SDIO, not the cryptography engine

The CRC and end-bit status comes from the SD/MMC controller/card protocol. The
CE is not on the CMD53 data path and does not generate or validate these CRCs.
Nothing in this session enabled or depended on the CE. The errors at 50 MHz
were genuine MMC sampling/data-integrity errors, not malformed output from a
disabled crypto engine.

## 4. SDR25 isolated and removed the first two errors

For the next diagnostic, the DT advertised only `sd-uhs-sdr25` and capped the
host at 25 MHz. The first run negotiated 4-bit SDR25 at 25 MHz but began at the
v5p3x 26 MHz default:

```text
DRV=00010000 NTSR=81710000
```

The first CMD53 produced two data-CRC errors. The retry sweep reached:

```text
DRV=00030000 NTSR=81710010
```

and firmware loading then succeeded. This was an empirical, reproducible
known-good SDR25 state, not a reason to accept two startup failures.

`patches/kernel/0045-mmc-sunxi-use-validated-sdr25-for-h713-wifi.patch`
programs that state before the first CMD53 by separating command and data
sample phases:

- command drive = 1
- data drive = 1
- command sample phase = 1
- data sample phase = 0

On the next cold initialization, the same state was present before enumeration,
firmware loaded, the hotspot started, and there were **zero startup CRCs or
retries**. This directly satisfies the requirement to avoid the errors rather
than rely on recovery.

## 5. SDR25 still failed under board-RX load before the IDMA fix

With clean startup and the known-good SDR25 phase, the original 8 MiB
workstation-to-board copy still failed later under load. This was a different
failure from the immediate 50 MHz sampling errors.

The first fault was:

```text
cmd53 fifo error (RINT=0x00000800 IDST=0x0000a000)
```

- `RINT=0x800` = `HARD_WARE_LOCKED`
- `IDST=0xa000` = IDMA state `WRITE_REQUEST_WAIT`

Retries then alternated FIFO/hardware-lock errors with response timeouts:

```text
RINT=0x00000200 IDST=0x00000002
```

where `IDST=0x2` is the IDMA receive-interrupt bit. After the bounded retries,
the AIC command queue died, but the console remained responsive and
`ksdioirqd/mmc1` was `S` in `sdio_irq_thread`. The deadlock fix still held.

This changed the diagnosis: UHS-SDR25 and phase selection solved initialization
but did not solve the original receive-path failure. The first under-load state
pointed at the controller's IDMA destination path.

## 6. Root cause: v5p3x maximum descriptor size is explicit, not zero

The decisive comparison was between:

- our `sunxi_mmc_init_idma_des()` in `drivers/mmc/host/sunxi-mmc.c`
- Allwinner's `/tmp/linux-orangepi-v5p3x/drivers/mmc/host/sunxi-mmc.c`
- v5p3x limits in `sunxi-mmc-v5p3x.c`
- Linux SDIO request construction in `drivers/mmc/core/sdio_ops.c`

The v5p3x host advertises `max_seg_size = 1 << 12 = 4096`. Linux therefore
splits a large CMD53 buffer into exact 4096-byte SG entries. Our descriptor
builder inherited this rule from older sunxi controllers:

```c
if (chunk_len == max_len)
        pdes[n].buf_size = 0;
```

Allwinner's v5p3x driver does not use the zero shorthand. It writes the actual
length, including `4096`, into every descriptor. This aligns exactly with the
observed receive failure: IDMA had no valid destination progress while the card
continued filling the receive FIFO, ending in `HARD_WARE_LOCKED`.

The diagnostic fix is intentionally variant-specific:

```c
if (chunk_len == max_len && !host->cfg->v5p3x)
        pdes[n].buf_size = 0;
else
        pdes[n].buf_size = cpu_to_le32(chunk_len);
```

It is stored as:

```text
patches/kernel/0046-mmc-sunxi-use-v5p3x-max-idma-descriptor-size.patch
```

## 7. Decisive passing run

The complete 45-patch series (through 0046) applied cleanly to a fresh
Linux 6.18.38 tree and built with the `sysrq` debug fragment:

```text
tree: build/linux-6.18.38-7fe9c8012b420d50f3c780e37beb11572244602694ea9576cd633d7e33501105
FIT:  build/out/h713-kernel-sysrq.fit
size: 7745528 bytes
FIT sha256: b057085e8f61d079806d0f9fb31b41e1dffcebbdef9948da6f48eb72351d06fe
kernel sha256: 1ff4ccbd087a04e588bec929186b4024bc2d37fdf224c362d18b5f57c2500516
DTB sha256:    04b36cda64e51dbbe87ee9c398dcb7e2c8b5ac26a80122a12dcad5ee97ddb80c
```

U-Boot `iminfo` verified both FIT subimage hashes before execution.

### Boot result

Cold SDIO initialization selected the validated state directly:

```text
v5p3x delay: rate=400000 timing=4 width=4 DRV=00030000 NTSR=81710010
v5p3x delay: rate=25000000 timing=4 width=4 DRV=00030000 NTSR=81710010
mmc1: new UHS-I speed SDR25 SDIO card at address 85e2
```

The AIC firmware loaded and the AP started without any CMD53 error or retry.
The workstation associated as `192.168.4.78`; the board was `192.168.4.1`.

### Board RX: workstation → board

Source:

```text
/tmp/h713-sdr25-8m.bin
8388608 bytes
sha256 4896f3533e373a1f4b8e898750461c9f837d303178fa6b03bf3dc3b31fec4269
```

Destination `/tmp/h713-idma-8m.bin` on the board was 8,388,608 bytes and had
the identical SHA-256. This is the direction that had failed in every prior
acceptance run.

### Board TX: board → workstation

The board file was copied back to `/tmp/h713-idma-back.bin`. It was 8,388,608
bytes and had the identical SHA-256.

### Final controller state

```text
clock:          25000000 Hz
actual clock:   25000000 Hz
bus width:      4 bits
timing spec:    4 (sd uhs SDR25)
signal voltage: 0 (3.30 V)
ksdioirqd/mmc1: S in sdio_irq_thread
```

Final `dmesg` grep for `cmd53|fifo error|phase error|CRC|HARD|timed-out`
contained only the CPU's “CRC32 instructions” feature line: **zero SDIO faults
or retries across boot and both transfers**.

## 8. Harness mistake during the passing build (do not repeat)

`tools/serial/boot_kernel.py` sets:

```text
rdinit=/init
```

but this FIT has no initramfs and must mount Debian from eMMC. The first launch
therefore panicked at `VFS: Unable to mount root fs`, rebooted, and U-Boot
overwrote the RAM address while attempting its default boot. The FIT itself had
already passed hash verification; no SDIO conclusion was drawn from this run.

After a second UART upload, the successful boot used:

```text
setenv fdt_high 0x4f000000
setenv initrd_high 0x4f000000
setenv bootargs 'console=ttyS0,115200 earlycon loglevel=8 root=/dev/mmcblk0p26 rootwait rootfstype=ext4 rw net.ifnames=0 panic=10 clk_ignore_unused pd_ignore_unused cma=128M'
iminfo 0x50000000
bootm 0x50000000
```

Update the helper before using it for this Debian-root workflow.

## 9. Repository and board handoff state

Committed:

```text
df1738e mmc: sunxi: add H713 v5p3x UHS negotiation
977244c mmc: sunxi: restore bus state before CMD53 retry
9d7054c mmc: sunxi: use validated SDR25 timing for H713 WiFi
7ac0845 mmc: sunxi: encode v5p3x max IDMA segment explicitly
```

The two hardware-passing patches and their `series` entries are committed.
Remaining intentionally untracked state at handoff:

```text
?? patches/kernel/board/sysrq.config     # debug only
?? .backup/                              # user-owned; do not touch
```

The board is left running the successful kernel from RAM, hotspot up, after
both passing transfers. Nothing was flashed. A power cycle returns to the
previously flashed kernel, which lacks 0045/0046 and must still be considered
broken for board RX.

Next: build a normal non-sysrq FIT, repeat a cold-boot two-direction 8 MiB test
plus a longer soak, then ask before flashing. The extra board USB/OTG cable is
not used; UART is the only required cable.

## 10. Quick 25 MHz vs 50 MHz comparison recipe

The committed `patches/kernel/series` is the known-good 25 MHz control. Leave
it unchanged for baseline tests: 0045 selects SDR25 at 25 MHz and initializes
the validated delay state, while 0046 fixes exact-4096-byte v5p3x IDMA
descriptors.

To make a temporary **RAM-only** 50 MHz comparison build, remove only the 0045
line from `patches/kernel/series`; keep 0043, 0044, and 0046. This re-exposes
0043's all-UHS, 50 MHz configuration without losing the bidirectional IDMA
fix. Keep AIC `FEATURE_SDIO_CLOCK_V3=0`, record the resulting FIT hash, and do
not flash the experiment.

Confirm the selected rate and mode in `/sys/kernel/debug/mmc1/ios`, then repeat
the two-direction 8 MiB hash test and the final SDIO error grep. The expected
control is 25,000,000 Hz/SDR25. A previous 50,000,000 Hz/SDR104 build
enumerated successfully but failed its first 512-byte CMD53 data transfer with
CRC/end-bit errors, so enumeration alone is not acceptance. Restore the 0045
line after the A/B run; any later 50 MHz tuning should change only timing/delay
variables while retaining 0046 and comparing against the unchanged 25 MHz
control.

---

# 2026-08-18 — the 50 MHz question, answered: the wall is between 33.33 and 37.5 MHz

The A/B above was executed, then extended until the 50 MHz failure was either
fixed or bounded. It is bounded. Every run below was a cold SDIO init on
hardware with a RAM-loaded FIT; nothing was flashed.

## 1. The documented A/B reproduces exactly

`series` minus 0045 (keeping 0043/0044/0046), `KERNEL_CONFIG=sysrq`,
FIT `45962fd0895265cf5d32b6a57428be07ad43ea893c03c7a8998874ab4fe5f33c`:

```text
v5p3x delay: rate=50000000 timing=6 width=4 DRV=00030000 NTSR=81710110
mmc1: new UHS-I speed SDR104 SDIO card at address 85e2
cmd53 phase error (RINT=0x00000080 IDST=0x00000000), retry 1/7
...
data error cmd53 RINT=0x00000000 ... clk=50000000Hz ... THLD=0x00000000
aicwf_sdio_send_pkt fail-110
```

`RINT=0x80` is `SDXC_DATA_CRC_ERROR`, `0x8000` is `SDXC_END_BIT_ERROR`, and
`IDST=0` throughout: the IDMA never faults, so this is not the 0046 class of
bug. `THLD=0` identifies the failing transfer as a **write** (our read
threshold only arms for reads), i.e. the firmware download's first CMD53.

## 2. A debug kernel replaced rebuild-per-state with boot-arg-per-state

`patches/kernel/0047-mmc-sunxi-h713-sdio-tuning-knobs.patch` (untracked) adds
`sunxi_mmc.h713_fmax`, `h713_uhs`, `h713_dly=cmd_drv,dat_drv,cmd_ph,dat_ph`,
`h713_sampdl` and `h713_relatch`, all inert by default. FIT
`dbc6a12f0c20c05b8e0eaf60de06b9336c87a3c715bc2db8d50fd50c56253680`.

Delivery stopped using UART: the FIT is copied to the board's own rootfs over
the working 25 MHz WiFi link (7.7 MiB in ~7 s) and U-Boot reads it back with
`ext4load mmc 1:1a`. **The partition index is hex** — `mmc 1:26` asks for
partition 38 and fails with `** Invalid partition 38 **`.

## 3. Host-side sweep at 50 MHz — 16 states, one outcome

| state (`h713_dly` / mode) | registers | first error |
|---|---|---|
| stock 52M default (1,1,1,1) | `DRV=00030000 NTSR=81710110` | `0x80` |
| data sample 0 (1,1,1,0) | `NTSR=81710010` | `0x80` |
| command drive 90° (0,1,1,1) | `DRV=00020000` | `0x80` |
| data drive 90° (1,0,1,1) | `DRV=00010000` | `0x80` |
| both phases 0 (1,1,0,0) | `NTSR=81710000` | `0x80` |
| stock pair (0,0)/(0,0) | `DRV=00000000` | `0x80` |
| stock pair (0,0)/(2,2) | `NTSR=81710220` | `0x80` |
| `h713_relatch=1` | stock 2X re-latch | `0x80` |
| `h713_uhs=50` → SDR50 | — | `0x80` |
| `h713_uhs=50` + data sample 0 | — | `0x80` |
| `h713_uhs=25` → SDR25 at 50 MHz | — | `0x80` |
| `h713_uhs=0` → SD high-speed at 50 MHz | — | `0x80` |

The last four matter most: **the mode is irrelevant**. Plain SD high-speed at
50 MHz — 3.3 V legal, no bus-speed switch, no tuning — fails identically to
SDR104. The 7-state in-driver retry sweep (0044) also fails, so this is not an
artifact of the retry path's controller reset.

## 4. Card-side sweep — the AIC8800's own iopad controls

The vendor driver carries, under `#if 0` for the D80 (v3) path, writes to
function-0 registers `0xF0` (iopad control, with `SDIOCLK_FREE_RUNNING_BIT`),
`0xF1` and `0xF8` (iopad delays), followed by its `FEATURE_SDIO_CLOCK_V3`
clock raise. `patches/aic8800/aic8800-0005-D80-card-side-SDIO-iopad-controls.patch`
(untracked) exposes them as module parameters.

Applied and verified live (`iopad: ctrl=65 dly1=64 dly2=0`), with the vendor's
values and with `dly1` swept `0x00/0x20/0x40/0x60`, and with the free-running
clock bit off: **all fail with `RINT=0x80`.** Both halves of the timing budget
are therefore exhausted.

Because that block is `#if 0` for the D80, stock never raises the SDIO clock
from the driver either — stock's link speed comes purely from its device tree
ceiling of 50 MHz.

## 5. The rate ladder — where the wall actually is

The v5p3x runs its module clock at 2x the card clock, so the CCU can only
produce a few rates here. Walking them with `h713_fmax`:

| requested | negotiated | result |
|---|---|---|
| 50 MHz | 50 MHz | fail, `RINT=0x80` (data CRC) |
| 40 MHz | 37.5 MHz | fail, `RINT=0x2000` (start bit) and `0x80` |
| 37.5 MHz + 4 phase states | 37.5 MHz | fail in every state |
| 35 MHz | **33.33 MHz** | **pass** |
| 33 MHz | 30 MHz | pass |
| 30 MHz | 30 MHz | pass |

The error signature changes at 37.5 MHz (start-bit rather than CRC), which is
what a link degrading through its margin looks like rather than a mode fault.

## 6. Acceptance at the new ceiling

`patches/kernel/0048-arm64-dts-h713-sdio-uhs-sdr104-at-33mhz.patch` declares
`sd-uhs-sdr50`/`sd-uhs-sdr104` and `max-frequency = <35000000>`. No driver
change: the existing 26–52 MHz delay entry already programs
`DRV=00030000 NTSR=81710110`, the state the passing runs used.

Built as FIT `dd7a38493605f034c8fd91bbdbf960e1a3b861feb666311a8db99a7bd30a28ae`
and booted with **no module parameters**:

```text
v5p3x delay: rate=33333333 timing=6 width=4 DRV=00030000 NTSR=81710110
mmc1: new UHS-I speed SDR104 SDIO card at address 85e2
clock: 35000000 Hz / actual clock: 33333333 Hz / 4 bits / 3.30 V
```

Payload `139080a55d26beca1bb94e58780a6ebd9f7048a1b5e79024e41682f0ba5d8a6b`
(8,388,608 bytes):

- 8 MiB workstation → board and board → workstation, SHA-256 exact
- soak: 8 iterations of both directions, 64 MiB each way, all exact
- `dmesg | grep -E 'cmd53|fifo error|phase error|data error|HARD|timed-out'`
  → 0 matches, at 30 MHz and at 33.33 MHz

Transfer times were 3–10 s per 8 MiB at both 25 and 33.33 MHz: the WiFi link,
not the SDIO bus, sets throughput. The case for 33.33 MHz is proximity to the
vendor configuration, not speed.

## 7. What would still be worth knowing

Stock's device tree asks for 50 MHz and its `ctl-spec-caps = <0x08>`
(`SUNXI_SC_EN_RETRY`) says stock expects data errors on this link and rotates
phases to recover. Since every phase fails here at 50 MHz, retries cannot be
the difference. Whether stock Android actually sustains 50 MHz on this board
has still never been observed; the vendor BSP prints its negotiated rate as
`sdc1 set ios: clk ...`, so a vendor boot capture would settle it. That needs
`tools/boot-switch.sh` to swap the first stage, so it is a deliberate step.

---

# 2026-08-19 — CORRECTION: the SDIO clock is ~4x higher than reported

The section above concluded that 50 MHz is unreachable on this board and that
33.33 MHz is the ceiling. **That conclusion is wrong**, and the sweeps it rests
on were all run at roughly four times the clock they claimed. The prompt for
re-opening it was a hard external fact: stock transfers correctly in both
directions at 4-bit UHS-SDR104 / 50 MHz on this hardware. If stock can, this
board can, so the fault had to be ours.

## 1. What is doubled, twice

- `sunxi_mmc_clk_set_rate()` (patch 0006) doubles the module clock for the
  v5p3x 2X timing mode — `if (host->cfg->no_wait_pre_over) clock <<= 1;` — and
  halves the rate it reports back. This mirrors the vendor driver, which does
  `mod_clk = ios->clock << 1` and reports `ios->clock = rate >> 1`.
- mainline's H616 CCU declares the MMC clocks with
  `SUNXI_CCU_MP_WITH_MUX_GATE_POSTDIV(mmc0_clk, "mmc0", mmc_parents, 0x830,
  ..., 2, 0)` — a fixed /2 post-divider — so `clk_set_rate(R)` programs the
  divider chain to `2R` and reports `R`.

Neither layer's assumed halving materialises, so the card is clocked at about
`4 x ios.clock`. The H713 SDIO cfg (`sun50i_h713_cfg`) is the only one carrying
`no_wait_pre_over`; the eMMC cfg does not, so the eMMC is off by at most 2x and
possibly not at all — untested.

## 2. Direct measurement (patches/kernel/0047, untracked)

The debug patch times each CMD53 payload: `ktime_get()` before `REG_BLKSZ` is
written, read again where `bytes_xfered` is set. Per-request software overhead
is ~4.4 us against milliseconds of bus time, so duration-vs-size has a slope
that is the bus rate and an intercept that is the overhead.

Enabled at runtime (`/sys/module/sunxi_mmc/parameters/h713_timing`) during an
8 MiB inbound scp:

```text
reported 12.5 MHz:  957 samples, 512 B .. 32,256 B
  512 B read   min  25 us      32,256 B read  min 1333 us
  slope 41.1 ns/byte -> 24.3 MB/s -> 48.6 MHz on 4 bits

reported 25 MHz:    645 samples, 512 B .. 32,256 B
  512 B read   min  14 us      32,256 B read  min  669 us
  slope 20.6 ns/byte -> 48.5 MB/s -> 96.9 MHz on 4 bits
```

The implied clock scales exactly 2x with the requested rate (48.6 -> 96.9), and
the intercept stays at ~4.4 us, which is what a real bus measurement looks like.
A 4-bit bus at a true 25 MHz cannot move 32,256 bytes in 669 us; it needs
2580 us.

## 3. Instrument-independent confirmation

At a reported 1 MHz the board received 8 MiB by `scp` in 14.42 s = **568 KB/s**.
A genuine 1 MHz 4-bit SDIO bus carries at most 500 KB/s, and that is before TCP,
WiFi and SDIO framing overhead. Nothing moves data faster than its own bus, so
the physical clock is provably higher than the reported one, with no reference
to the kernel instrumentation at all.

## 4. Re-reading the earlier ladder

| `max-frequency` | physical | earlier verdict | actual meaning |
|---|---|---|---|
| 12.5 MHz | ~50 MHz | not tested then | stock parity — passes, 4 x 8 MiB both ways, 0 faults |
| 25 MHz | ~100 MHz | "the safe baseline" | ~2x stock, passes + 128 MiB soak |
| 30 MHz | ~120 MHz | pass | pass |
| 35 MHz | ~133 MHz | "the new ceiling" | pass, 128 MiB soak — but ~2.7x stock |
| 40 MHz | ~150 MHz | fail (start-bit) | the analog wall is here |
| 50 MHz | ~200 MHz | "50 MHz impossible" | ~200 MHz impossible; says nothing about 50 |

The sweeps themselves remain valid observations — mode, 16 host delay states,
stock's 2X re-latch, and the AIC8800 iopad registers all failed identically —
but they were run at ~200 MHz, where no timing knob was ever going to help.

## 5. Consequences

- `patches/kernel/0048` (the 33.33 MHz "ceiling" patch) was **withdrawn**: it
  was an unintentional ~133 MHz overclock resting on the wrong reading.
- The committed `max-frequency = <25000000>` has been running the AIC8800 at
  about 100 MHz for the whole bring-up. It passes acceptance and soaks, but it
  was never a deliberate choice.
- The fix is to make the number honest, not to chase a rate. Removing the
  driver-side doubling (`sunxi_mmc.h713_nodouble=1` in 0047) halves the error;
  whether the remaining 2x belongs to the CCU post-divider needs the eMMC
  measured the same way — one gate change in 0047, since its timing hook is
  currently restricted to `cfg->v5p3x`.
- Only after that should the rate be chosen: stock parity is 50 MHz physical,
  and the wall is ~133–150 MHz physical.

---

# 2026-08-21 — the accounting is fixed, and the link runs stock 50 MHz

`patches/kernel/0048-mmc-sunxi-h713-run-sdio-at-stock-sdr104-50mhz.patch`.

> **Do not confuse this with the earlier withdrawn 0048.** The number was
> reused. The withdrawn one asked for 33.33 MHz and was an accidental ~133 MHz
> overclock. This one removes the 4x error itself, so the device tree number is
> the physical number.

## 1. What the patch does

For MMC1 only, both compensations are removed:

- `sunxi_mmc_clk_set_rate()` loses the `clock <<= 1` / `rate >>= 1` pair. That
  pair is gated on `cfg->no_wait_pre_over`, set only by `sun50i_h713_cfg`, which
  is used only by `mmc@4021000` (`allwinner,sun50i-h713-mmc`). The eMMC at
  `mmc@4022000` binds `allwinner,sun50i-h713-emmc` → `sun50i_h713_emmc_cfg`,
  which does not set the flag. So the eMMC is out of scope by construction.
  Mainline's `MMC_TIMING_MMC_DDR52` doubling in the same function is untouched.
- `mmc1_clk` in `ccu-sun50i-h713.c` moves from
  `SUNXI_CCU_MP_WITH_MUX_GATE_POSTDIV(…, 2, 0)` to `SUNXI_CCU_MP_WITH_MUX_GATE(…)`.
  `mmc0_clk` and `mmc2_clk` keep the post-divider.

The device tree regains `sd-uhs-sdr50`, `sd-uhs-sdr104`, `sd-uhs-ddr50` and
`max-frequency = <50000000>`. 0046's explicit 4096-byte IDMA descriptor encoding
is retained; 0045's cold-start phase programming is retained.

Build: `KERNEL_CONFIG=sysrq build/build.sh kernel` →
`build/out/h713-kernel-sysrq.fit`, 7745700 bytes,
`b82642aedf10f54a1ef9e47cde217e62471f3b987011a4abda51248128884b22`, tree
`build/linux-6.18.38-36796f34b1250048e9800380d365e7c660fb3b3f534b5ea0fd3ba6262f3e4194`.

## 2. Cold init

```text
v5p3x delay: rate=400000    timing=0 width=1 DRV=00010000 NTSR=81710000
v5p3x delay: rate=400000    timing=6 width=4 DRV=00010000 NTSR=81710000
v5p3x delay: rate=50000000  timing=6 width=4 DRV=00030000 NTSR=81710110
mmc1: new UHS-I speed SDR104 SDIO card at address 6721
```

`NTSR=81710110` is the 104M delay entry, selected by the existing per-speed
programming — no new table was needed at this rate.

```text
clock:          50000000 Hz
actual clock:   50000000 Hz
bus width:      2 (4 bits)
timing spec:    6 (sd uhs SDR104)
signal voltage: 0 (3.30 V)
```

## 3. Proving the physical rate without re-instrumenting

`clk_rate` in debugfs is computed by the very model the patch edits, so it
cannot confirm the patch. The CCU register can.

**The H713 CCU base is `0x02001000`.** It is *not* H616's `0x03001000` — reading
that address returns `0x00000000` and looks like a dead clock. MMC0/1/2 are
`0x02001830` / `0x834` / `0x838`.

```text
0x02001830 = 0x80000000     mmc0
0x02001834 = 0x8100000B     mmc1
0x02001838 = 0x02000002     mmc2 (eMMC)
```

`0x8100000B`: gate (bit 31) on; mux `[25:24]` = 1 = `pll-periph0-2x`; P `[9:8]`
= 0 → 1; M `[3:0]` = 11 → 12.

`clk_summary` gives the parent tree, which is internally consistent:

```text
pll-periph0        300000000
  pll-periph0-4x  1200000000
  pll-periph0-2x   600000000
    mmc1            50000000
```

600 / 12 = **50 MHz at the pin**.

The confirmation is that M=12 is *the same divider* the old nominal-12.5 MHz
configuration programmed: 12.5 doubled by the driver to 25, multiplied by the
modelled post-divider to a 50 MHz chain target, giving M=12. Section 3 of the
2026-08-19 entry measured that exact configuration at **48.6 MHz** with CMD53
payload timing. Same register, same wire rate — the new setting inherits a
physical measurement instead of needing a fresh one.

## 4. Acceptance and soak

Delivery used the established loop: boot `good-25mhz.fit` from the board rootfs,
`scp` the new FIT in over the working link, `reboot-to-uboot.py`, then
`boot_kernel.py --load /root/fits/test.fit`. Nothing flashed.

| test | result |
|---|---|
| 8 MiB workstation → board | 8,388,608 B, SHA-256 exact |
| 8 MiB board → workstation | SHA-256 exact |
| 128 MiB workstation → board | 134,217,728 B, SHA-256 exact, 1 m 49 s |
| 128 MiB board → workstation | SHA-256 exact, 1 m 00 s |

```sh
dmesg | grep -iE 'cmd53|fifo error|phase error|data error|HARD|timed-out|end-bit|start-bit|crc error'
```

empty after the soak. `ksdioirqd/mmc1` is `S` in `sdio_irq_thread`. The only
`retry` hit anywhere in the log is a WiFi association line
(`done=1 retry_required=0 …`).

The nine `error|fail` lines in `dmesg` are all pre-existing and unrelated:
pinctrl supplier device-link, missing `regulatory.db`, the `rdinit=/init` access
check (expected — we boot with `root=`), two `AICWFDBG` `invalid cmd` lines, the
AFBD "display is not running" notice (no `h713_disp` run in U-Boot), and two
Bluetooth `Opcode 0x1003` timeouts. All present in the 25 MHz control boot too.

eMMC after the soak: HS400, 8-bit, 200 MHz, `/dev/mmcblk0p26` mounted `rw`.

## 5. Why the eMMC keeps its post-divider

The 2026-08-19 entry recommended measuring the eMMC to decide whether the
post-divider assumption was wrong SoC-wide. The register values argue it is not,
and that removing it there would *break* HS400 rather than fix it:

`0x02001838` = `0x02000002` → mux 2 = `pll-periph1-2x` (1200 MHz per
`clk_summary`), M = 3, P = 1. The divider chain therefore emits **400 MHz**,
which the model reports as 200 MHz. HS400 is DDR and wants the module clock at
twice the card clock — and mainline's `sunxi_mmc_clk_set_rate()` only applies
that doubling for `MMC_TIMING_MMC_DDR52`, never for HS400. The post-divider
appears to be supplying precisely that missing 2x.

**This is inference from register values, not a measurement**, and it is
recorded as such. It is worth confirming with the 0047 timing hook before anyone
edits mmc0/mmc2, but nothing in the current tree depends on the answer.

(`mmc2`'s gate bit reads 0 while the eMMC is idle — sunxi-mmc drops the module
clock on runtime suspend. The divider fields still hold the last programmed
value, which is what is decoded above.)

## 6. What is now closed

- The 4x accounting error: **fixed**, MMC1 only, validated.
- The rate: **chosen deliberately** at stock parity, four-bit UHS-SDR104 /
  50 MHz, rather than inherited.
- The physical ladder from 2026-08-19 (~50 / ~100 / ~120 / ~133 MHz pass;
  ~150 and ~200 MHz fail) now maps onto honest device tree numbers. Headroom
  above stock is real but modest, and taking it would be a new decision with new
  evidence, not a continuation of this one.

Still open, and unchanged by this work: whether stock Android actually sustains
50 MHz here (its device tree asks for it; it has never been observed), and the
mismatched `is_chip_id_h` firmware variant.

## 7. Production kernel, cold boot (2026-08-21)

Sections 1–6 used a `sysrq` debug kernel started by `bootm` with no intervening
power cycle. Both gaps are now closed.

Production FIT — `build/build.sh kernel` with no `KERNEL_CONFIG`:

```text
build/out/h713-kernel.fit
size   7741216 bytes
sha256 51044da6e73441420d81d4fb6e387e6d351efb6b1574e7527e35016d14f5b0a1
tree   build/linux-6.18.38-577fb0d96df8c37211b6d8c0da6fdc2f7f2937eb365032bfa6307ac117bb2cf6
```

`diff` of the two `.config` files is exactly four symbols and nothing else:

```text
< CONFIG_MAGIC_SYSRQ=y
< CONFIG_MAGIC_SYSRQ_SERIAL=y
< CONFIG_MAGIC_SYSRQ_SERIAL_SEQUENCE=""
< CONFIG_MAGIC_SYSRQ_DEFAULT_ENABLE=0x1
```

Confirmed on the running board by the absence of `/proc/sys/kernel/sysrq`. The
0048 changes were re-verified in the fresh tree rather than assumed: `mmc1_clk`
on the non-POSTDIV macro, no `H713 v5p3x: 2X timing` doubling, mmc1
`max-frequency = <50000000>` with the eMMC node still at `<200000000>`.

Boot was a real power-on reset: mains cycled by hand, autoboot interrupted at
the U-Boot prompt, then `ext4load mmc 1:1a` + `bootm` of `/root/fits/prod.fit`.
Nothing flashed.

```text
v5p3x delay: rate=50000000 timing=6 width=4 DRV=00030000 NTSR=81710110
mmc1: new UHS-I speed SDR104 SDIO card at address 6721
```

| test | result |
|---|---|
| 8 MiB workstation → board | SHA-256 exact |
| 8 MiB board → workstation | SHA-256 exact |
| 128 MiB workstation → board | SHA-256 exact, 1 m 41 s |
| 128 MiB board → workstation | SHA-256 exact, 0 m 57 s |

Fault grep empty; `ksdioirqd/mmc1` `S` in `sdio_irq_thread`; CCU `0x02001834`
still `0x8100000B` after the soak; eMMC HS400 8-bit 200 MHz, rootfs `rw`.

Cold SDIO init is clean on the first CMD53 — one `v5p3x delay` line at 50 MHz,
no 400 kHz retry storm, no phase rotation ahead of it.

## 8. Blocker for flashing: the FAT on `mmc 1:2` overruns its partition

Pre-existing, unrelated to 0048, found while checking whether the production FIT
could be flashed for an unattended cold boot.

`bootcmd` is `fatload mmc 1:2 0x50000000 h713-kernel.fit; bootm 0x50000000`.

- `/dev/mmcblk0p2` is **32 MiB**: `blockdev --getsize64` 33554432, `--getsz`
  65536.
- Its vfat superblock describes **128 MiB**; `df` says 128M total / 69M used,
  and it catalogues ~57 MB of files.
- Linux errors on anything past the partition end:
  `attempt to access beyond end of device, mmcblk0p2: sector=140701,
  limit=65536`. `sha256sum /mnt/fat/h713-kernel.fit` → `Input/output error`.

**U-Boot is unaffected** and this is the correction that matters: `fatload
mmc 1:2 0x50000000 h713-kernel.fit` returns all 7739580 bytes in 496 ms
(14.9 MiB/s). U-Boot does not clamp to the partition-table entry, and the FAT's
clusters physically exist on the eMMC past it. The board's boot path has never
been broken by this; only Linux-side access is.

Consequence for this work: writing the FIT there — from Linux or via `fatwrite`
— could place data outside the partition, over whatever the GPT assigns to that
region. So flashing stays blocked, and `mmc 1:2` should not be mounted `rw`,
until it is established whether the GPT entry is undersized or the filesystem
was built oversized, and what the upper ~96 MiB overlaps.

## 9. The FAT geometry, reconciled (2026-08-21)

The section 8 blocker is fixed. **The filesystem was oversized; the GPT was
right.**

### Diagnosis

| | |
|---|---|
| `mmcblk0p2` (`bootloader_b`) | LBA 139264–204799, 65536 sectors = **32 MiB** |
| FAT16 `total_sectors_32`, boot-sector offset 32 | `0x00040000` = 262144 sectors = **128 MiB** |

The partition table cannot be the error. A 128 MiB volume starting at LBA
139264 ends at 401407, running through `env_a` (204800), `env_b` (205312),
`boot_a` (205824–336895) and half of `boot_b` — and those are occupied:
`boot_a` begins with an `ANDROID!` header, `env_a` with a live U-Boot
environment (`BOOTMODE=standby…`). There is nowhere to grow into.

`fsck.vfat -n` names it exactly: `Failed to read sector 262143.`

**Correction to section 8:** it said a write "from either side" was unsafe.
Linux writes fail *safely* — the block layer clamps to the partition and
returns `attempt to access beyond end of device`, so Linux physically cannot
reach `boot_a` through this filesystem. The hazard is U-Boot's `fatwrite`,
which does not clamp. That is why the repair was done from Linux.

### What was actually at risk: none of the vendor data

Testing every file for readability partitions the set cleanly:

- **All 45 vendor artifacts are inside 32 MiB** — `mips/*`, `wavefile/*`,
  `bat/*`, `bootlogo.bmp`, `boot-logo.bmp`, `fastbootlogo.bmp`, `font24.sft`,
  `font32.sft`, `magic.bin`, `backup_8020.bin`.
- **Only the six `h713-kernel*.fit` files were out of range** — all ours.

### The repair

Proven on a copy of the backup before the board was touched:

1. `mdel` the six out-of-range kernel FITs. Deletion only rewrites the FAT
   table and root directory, both inside the first 545 sectors.
2. Patch `total_sectors_32` at offset 32: 262144 → 65536
   (`printf '\x00\x00\x01\x00' | dd of=IMG bs=1 seek=32 count=4 conv=notrunc`).
3. `mcopy` the validated production FIT in as `h713-kernel.fit`.

Cluster arithmetic stays valid: 65536 − 545 reserved/FAT/root = 64991 data
sectors ÷ 4 = **16247 clusters**, comfortably inside FAT16's 4085–65524 range,
and the existing 256-sector FAT indexes far more than that. Nothing needs
reformatting — the FAT table and directories are untouched.

Verification on the copy: `fsck.vfat -n` clean, no unreachable sector, and all
45 vendor files extracted bit-identical against the original
(`checked=45 mismatches=0`).

**Never run `fsck.vfat -a` on this volume.** The read-only pass shows it would
rename `mips/ProjectID_0x0014.TSE` to `FSCK0000.000` (a pre-existing bad short
name) and rewrite the volume label. Both were previously invisible because fsck
aborted at the unreachable-sector check.

### Result on hardware

Written with `dd of=/dev/mmcblk0p2 bs=1M conv=fsync`; read-back SHA-256 matches
the prepared image exactly. From Linux: 32M volume on a 32M partition, 46 files,
**0 unreadable**, 0 `beyond end of device` messages, 3.4M free, and
`sha256sum h713-kernel.fit` — previously an `Input/output error` — now returns
`51044da6…`, the validated production build.

Then `bootcmd` was allowed to run untouched:

```text
Hit any key to stop autoboot: 2  1  0
7741216 bytes read in 497 ms (14.9 MiB/s)
## Loading kernel (any) from FIT Image at 50000000 ... sha256+ OK
## Loading fdt (any) from FIT Image at 50000000 ...    sha256+ OK
v5p3x delay: rate=50000000 timing=6 width=4 DRV=00030000 NTSR=81710110
mmc1: new UHS-I speed SDR104 SDIO card at address 6721
```

The board now boots the validated 0048 production kernel unattended from its
own eMMC, at stock 4-bit SDR104/50 MHz, and an 8 MiB round trip afterwards is
SHA-256 exact with zero SDIO faults.

### Images kept

```text
local/stock-boot/bootloader_b-p2-32MiB-20260821.img           dfa4ad99…  pre-repair, verified against a re-read of p2
local/stock-boot/bootloader_b-p2-REPAIRED-32MiB-20260821.img  64c700e2…  what was written
```

Restoring is the same `dd` with the pre-repair image. The one thing not
preserved is the previously flashed `h713-kernel.fit`: it lived beyond 32 MiB,
so it is not in the backup. It predates 0045/0046/0048 and was already
documented as broken for board RX.

### Remaining constraint

3.4 MB free. One kernel FIT fits; the old habit of parking five or six
experimental FITs there is what created the overflow in the first place, and
there is no longer room for it. A larger debug image — the 10.8 MB KASAN build,
for instance — will not fit alongside the production one. Stage experiments on
the ext4 rootfs and `ext4load` them instead.

## 10. Measuring the eMMC clock (2026-08-21) — attempted, NOT settled

The open question from section 7: `mmc2`'s CCU divider chain physically emits
400 MHz while the driver labels the card clock 200 MHz. Is the eMMC running at
its label, or at twice it?

**The payload-timing method cannot answer it.** That is the result. What follows
is why, and what it did establish, because the negative is reusable.

### The probe

`patches/kernel/0049-mmc-sunxi-h713-payload-timing-probe.patch` (untracked,
debug). Unlike 0047 it is *not* gated on `cfg->v5p3x`, so it sees both
controllers, and it logs raw `bytes`/`ns` plus bus geometry rather than baking
in a 4-bit-SDR conversion — 0047's formula is hardcoded for SDIO and would be
wrong by 4x on an 8-bit DDR link. Inert unless `sunxi_mmc.h713_probe=1`;
`h713_probe_min` sets a size floor to keep rootfs chatter out.

### The method is sound — the SDIO control proves it

| host | samples | fitted slope | implied card clock | label |
|---|---|---|---|---|
| mmc1 SDIO | 201 | 41.03 ns/B → 24.4 MB/s | **48.7 MHz** | 50 MHz |
| mmc0 eMMC | 147 | 8.47 ns/B → 118.0 MB/s | 59.0 MHz | 200 MHz |

mmc1 reads 48.7 MHz against a known 50 — 2.6% low, and independently equal to
the 48.6 MHz the 2026-08-19 CMD53 instrumentation measured. The arithmetic is
right.

### Why the eMMC number is meaningless

The shapes differ, and that is the whole story:

- **mmc1 is flat**: 22.9 MB/s at 2 KiB, 24.2 MB/s at 32 KiB. Bus-limited
  throughout, so throughput reads the clock.
- **mmc0 climbs**: 46.9 → 75.3 → 91.7 → 103.0 → 109.7 → 112.4 MB/s from 16 KiB
  to 512 KiB, still rising. That is a fixed per-transfer cost amortised over
  larger reads — the NAND — not a bus ceiling.

Re-reading the *same* 512 KiB region 60 times does not help: min 4.682 ms,
median 4.689 ms, max 4.760 ms, a 1.6% spread. There is no device read cache to
hide behind. The media caps at ~118 MB/s, far below either candidate bus rate
(400 MB/s at 200 MHz, 800 MB/s at 400 MHz), so the probe only ever sees flash.

**All it establishes is a lower bound: the eMMC card clock is at least 59 MHz.**

### Forcing a bus-limited regime still did not settle it

`patches/kernel/0050-arm64-dts-h713-debug-cap-emmc-to-25mhz.patch` (untracked,
debug) caps `mmc@4022000` to 25 MHz and drops the HS200/HS400/DDR flags. The
card enumerated 8-bit DDR52 at 25 MHz, rootfs mounted clean, and the registers
read `CLKCR=0x00010001` (divider 2), CCU `0x81000005` (mux 1 =
`pll-periph0-2x` 600 MHz, M=6, P=1 → 100 MHz chain).

That makes the two hypotheses concrete and far apart:

| | chain | ÷CLKCR | card clock | expected |
|---|---|---|---|---|
| post-divider real | 50 MHz | 2 | 25 MHz | 50 MB/s |
| no post-divider | 100 MHz | 2 | 50 MHz | 100 MB/s |

Measured: **29.5 MB/s**, implying 14.8 MHz at the 2 bytes/card-clock that 8-bit
DDR requires. That is neither 25 nor 50.

The regime change is real — an 8x label cut (200 → 25 MHz) produced only a
3.85x slowdown (112.4 → 29.2 MB/s on the same 512 KiB read), which independently
confirms the 200 MHz case was media-limited and the 25 MHz case is not. But the
bus-limited number lands where it should only if bytes-per-card-clock were about
1.17, and no bus geometry gives that.

**So there is an unexplained ~1.7x factor in the eMMC data path**, and until it
is identified, eMMC throughput cannot be converted into a card clock the way
SDIO throughput can. Reporting 14.8 MHz — or forcing it to the nearer
hypothesis — would be reading a number the method has not earned.

### The competing signal, unresolved

Register evidence leans the *other* way from the section-7 inference. Both
controllers are configured identically: `CLKCR = 0x00010000` (divider 1) and
`NTSR` bit 31 (`SDXC_2X_TIMING_MODE`) set on each, at their normal settings. On
mmc1 — the one that can be measured — the card clock equals the CCU chain
output (50 MHz chain, 48.7 MHz measured, ratio 1.0). If mmc0 behaved the same
way its 400 MHz chain would mean a 400 MHz card clock, i.e. HS400 at twice its
rated maximum.

Against that: HS400 is specified to 200 MHz, and this eMMC has run at 112 MB/s
with zero errors throughout the project. A silent 2x overclock that never fails
is possible on a short point-to-point bus with a data strobe, but it is not the
way to bet.

The difference between the two controllers that could explain it is that mmc1 is
SDR and mmc0 is DDR, and the controller may halve the module clock for DDR modes
— which is exactly what `SDXC_2X_TIMING_MODE` is named for. That would make the
label honest and the section-7 inference right. Nothing measured here confirms
or refutes it.

### Where this leaves it

Unchanged from section 7 in substance: **the eMMC clock is not established**,
the section-7 explanation remains an inference, and nothing in the tree depends
on the answer. What is new is that the cheap way of answering it has been tried
and does not work, so the next attempt should not repeat it.

What would actually settle it, in rough order of cost:

1. Identify the ~1.7x factor — instrument block-gap/CRC overhead, or time a
   single multi-block read against its theoretical duration at a known-good
   mode. If eMMC throughput can be calibrated the way SDIO was, the capped-clock
   experiment becomes decisive immediately.
2. Read the controller's DDR handling out of the vendor `sunxi-mmc` source or
   the H713 manual to settle whether `SDXC_2X_TIMING_MODE` halves for DDR.
3. Scope the eMMC clock pin. Definitive, and the only method with no model in
   the middle.

Board was returned to the flashed production kernel afterwards: HS400 200 MHz,
SDR104 50 MHz, zero faults.

## 11. The regulatory domain (2026-08-21) — fixed, and not where it looked

`regulatory.db failed to load` is the visible symptom, and fixing it would not
have changed the radio's behaviour at all. Worth reading before anyone chases
the log line.

### The wiphy is self-managed, so regulatory.db is irrelevant to it

`aic8800_fdrv` sets `REGULATORY_WIPHY_SELF_MANAGED` and installs its own domain
in `rwnx_custregd()` (`rwnx_mod_params.c`), gated on the `custregd` module
parameter, which defaults to `Y`. cfg80211's database never applies to that
wiphy. `iw reg get` confirms it: `phy#0 (self-managed)`.

What was actually in force:

```text
phy#0 (self-managed)
country 00: DFS-UNSET
	(2380 - 2520 @ 40), (N/A, 20), (N/A)
	(5140 - 5980 @ 80), (N/A, 20), (N/A)
```

`DFS-UNSET`, no `NO_IR`, no passive-scan: transmit permitted across the whole
5 GHz range including DFS and weather-radar spectrum (5600-5650), and past the
2.4 GHz ISM edges.

### The driver's own database is fine; only the selector was stuck

`regdb.c` holds **185 countries with 98 distinct rule sets**, with correct DFS
regions, `NO_IR`/`NO_OUTDOOR` flags and per-subband power. It is selected by
`default_ccode` — a compiled-in `char[4] = "00"`, not a module parameter, so
there was no way to change it without editing the source.

> A first pass at this concluded the table was 189 identical permissive entries.
> That was a bad regex: the real entries use `REG_RULE_EXT` with `.dfs_region`,
> and only the `"00"` fallback uses the wide `REG_RULE` form. The table is real.

`patches/aic8800/aic8800-0006-make-the-regulatory-domain-settable.patch` exposes
the selector as a module parameter. `tools/rootfs/customize.sh` writes
`/etc/modprobe.d/aic8800-regdomain.conf` with `WIFI_REGDOMAIN` (default `US`).

Result on hardware:

```text
phy#0 (self-managed)
country US: DFS-FCC
	(2400 - 2472 @ 40), (N/A, 30), (N/A)
	(5150 - 5250 @ 80), (N/A, 23), (N/A), AUTO-BW
	(5250 - 5350 @ 80), (N/A, 24), (0 ms), DFS, AUTO-BW
	(5470 - 5730 @ 160), (N/A, 24), (0 ms), DFS
	(5730 - 5850 @ 80), (N/A, 30), (N/A), AUTO-BW
	(5850 - 5895 @ 40), (N/A, 27), (N/A), NO-OUTDOOR, AUTO-BW
	(5925 - 7125 @ 320), (N/A, 12), (N/A), NO-OUTDOOR, PASSIVE-SCAN
```

The AP kept working: 2.4 GHz HT40, 5.13/7.39 MB/s each way, SHA-256 exact, zero
SDIO faults.

**The `CAUTION: USING PERMISSIVE CUSTOM REGULATORY RULES` banner still prints.**
It is on the *success* branch of `regulatory_set_wiphy_regd_sync()` in
`rwnx_custregd()`, so it fires whatever domain was applied. Judge the domain
with `iw reg get`, never with that message.

### regulatory.db itself: two separate bugs, one still open

Both were found while chasing the log line. Neither affects the self-managed
wiphy, but both matter if `custregd=0` is ever used.

1. **Broken alternatives, fixed.** `wireless-regdb` is installed and the variant
   files exist, but `/lib/firmware/regulatory.db` — the master alternatives
   symlink — was missing, and alternatives pointed at the Debian variant anyway.
   Our mainline kernel carries only the upstream certs
   (`net/wireless/certs/{sforshee,wens}.hex`) and cannot verify Debian's
   `benh@debian.org` signature, so the Debian pair could never validate.
   `update-alternatives --set regulatory.db /lib/firmware/regulatory.db-upstream`
   selects the wens-signed pair; `customize.sh` now does this at image build.

2. **Load ordering, still unfixed.** cfg80211 is built into the kernel and
   requests the database before the root filesystem is mounted:

   ```text
   [    1.045334] faux_driver regulatory: Direct firmware load for regulatory.db failed with error -2
   [    1.418365] EXT4-fs (mmcblk0p26): mounted filesystem ... r/w
   ```

   373 ms too early. No amount of fixing the file helps. The options are
   `CONFIG_EXTRA_FIRMWARE="regulatory.db regulatory.db.p7s"` to embed it in the
   kernel image, building cfg80211 as a module so the request happens after
   `/` is up, or an initramfs. Not done, because with a self-managed wiphy it
   changes nothing observable — do it only alongside `custregd=0`.

## 12. Firmware-crash recovery (2026-08-21) — the reboot made reliable

The 2026-07-23 conclusion stands: **there is no safe in-place recovery.**
Unbinding and reloading the SDIO stack races the mmc/driver core into a
NULL-deref Oops (`__device_attach_driver` via `mmc_rescan` -> `mmc_attach_sdio`).
Do not try it again. Only a full boot revives the chip.

What was wrong was not that conclusion but what followed from it. The fallback
reboot itself hung — roughly three minutes on `h713-bt-attach` stop — and left
the board needing a physical power cycle, so the project gave up on automatic
recovery entirely and shipped a log-only notifier. The fix is to make the reboot
reliable rather than to keep avoiding it.

### Three changes

1. **The handler reboots.** `/usr/local/sbin/h713-wifi-recover` (was
   `h713-wifi-crashlog`) logs the fault, waits `GRACE_SECONDS`, then
   `systemctl reboot`. Policy lives in `/etc/default/h713-wifi-recovery`:
   `AUTO_REBOOT=yes|no`, `GRACE_SECONDS`. Editable on a deployed unit.

2. **BT cannot stall the shutdown.** `h713-bt-attach.service` gets
   `TimeoutStopSec=10s`. After a firmware crash `hciattach` blocks in the
   HCI/UART path where SIGTERM does not reach it, and systemd was waiting out
   the full default timeout on a chip that cannot tear down. Nothing useful
   happens in that window.

3. **Hardware backstop.** `/etc/systemd/system.conf.d/h713-watchdog.conf` sets
   `RebootWatchdogSec=16s`, so systemd arms the sunxi watchdog across the
   shutdown transition. A stuck unit now costs 16 seconds and a SoC reset
   instead of a trip to the board. Confirmed on hardware:

   ```text
   systemd-shutdown[1]: Using hardware watchdog 'sunxi-wdt', version 0, device /dev/watchdog0
   systemd-shutdown[1]: Watchdog running with a hardware timeout of 16s.
   ```

   This opens `/dev/watchdog` only for the shutdown, so it does **not** arm a
   runtime watchdog and cannot reset a healthy but busy system. `RuntimeWatchdogSec`
   would add that, but 16 s is the sunxi hardware maximum and is tight under
   load, so it is left off deliberately.

### What was verified, and what was not

Verified on hardware:

- `AUTO_REBOOT=no` logs to journal and `/dev/kmsg` and does not reboot.
- `AUTO_REBOOT=yes` reboots, the watchdog arms as quoted above, and the board
  is back in about 30 s with the AP up, US regdomain restored and zero SDIO
  faults.

**Not verified: recovery from a real firmware crash.** The trigger was
synthetic — the unit was started directly, not by a `DHDISDOWN` uevent from a
genuinely dead chip. That matters, because the dead chip is exactly the state
that makes `hciattach` unkillable, and a healthy `hciattach` sits in `S`/
`do_sys_poll` where SIGTERM works fine. The watchdog bounds the shutdown either
way, which is why this is worth shipping despite the gap, but it is a gap.

An attempt to provoke a real crash failed: 4 minutes of the documented
starvation recipe (performance governor, 4x `yes`, a large memcpy `dd`,
continuous eMMC-write `dd`, load average 7.97) with six concurrent 64 MiB WiFi
round-trips produced **zero** `DHDISDOWN`, zero `cmd timed-out`, zero SDIO
faults, and every hash exact. The crash may simply be less reachable now — the
vendor rebase, the 0046 IDMA fix and the 0048 clock fix all landed since it was
last seen — or this load was not pathological enough. Either way it is no longer
reproducible on demand, so the recovery path stays untested against the real
fault.

### Policy note

`AUTO_REBOOT=yes` is the default because an unattended unit that reboots itself
beats one that sits dead until someone notices. For a projector that must never
interrupt playback for a network fault, set `AUTO_REBOOT=no` and keep the older
log-and-wait behaviour; the handler is one config line either way.

## 13. STA mode retested (2026-08-21) — the standing rule is refuted

STA mode was the last untested path, and historically *the* failing one: two
attempts out of two on 2026-08-16 wedged the board, and the project adopted the
rule "WiFi for an interactive shell and log reading only; serial or a baked
image for anything file-sized."

**That rule is dead.** STA mode carries files, and faster than the shipped AP.

### Method

No credentials were needed and the control path never depended on the link under
test. Roles were inverted: the **workstation** hosted a throwaway AP
(`nmcli device wifi hotspot`, generated passphrase, 10.42.0.1) and the **board**
joined it as a station via `/root/sta-connect.sh`. Serial stayed as the control
channel throughout, which is the only reason the mode switch was safe to make
remotely.

DHCP did not complete, so the board was given `10.42.0.50/24` statically. Not
investigated — it was in the way, not the subject.

### Results

| transfer | board RX | board TX | hash |
|---|---|---|---|
| 8 MiB | 4.46 MB/s | — | exact |
| 64 MiB | 8.11 MB/s | 9.20 MB/s | exact |
| 128 MiB | **8.90 MB/s** | **9.62 MB/s** | exact |

Zero `cmd53`, `cmd timed-out`, `DHDISDOWN`, FIFO or CRC messages throughout, and
the board stayed up continuously across all of it. The 8 MiB board-RX case is
the exact shape of the 2026-08-16 failure — a ~10 MB inbound scp — and it
completed in 1.9 s.

STA throughput (8.9/9.6 MB/s) **beats** the shipped 2.4 GHz HT40 hotspot
(5.1-7.7 MB/s), because the workstation's AP is 802.11ax and the link negotiated
HE rates (`rx bitrate: 143.3 MBit/s HE-MCS 11`). Nothing about the board changed
between the two measurements, so this is a property of the peer, not of STA mode.

### Why the old result was real but misattributed

The 2026-08-16 failures were genuine. They were the SDIO bulk-RX defect — the
v5p3x IDMA descriptor encoding for an exact maximum-size segment — which
**patch 0046** fixed on 2026-08-18. That defect was never STA-specific; section
"three corrections" already recorded that it reproduced in AP mode too. STA mode
simply got the blame because it was where the transfers happened.

`tools/wifi/sta-connect.sh` carried the warning in its header, where it would be
read by exactly the person about to do this. It has been replaced with the
measurements above.

### One thing that looks like a wedge and is not

After `sta-connect.sh` associates, it runs `dhclient` in the **foreground**. The
serial console then echoes typed characters but produces no command output —
which is precisely the signature the old notes describe as "tty echo alive,
shell dead, recoverable only by pulling power". It is not. **Ctrl-C returns the
shell.** Check that before concluding the board is wedged.

## 14. The BT `Opcode 0x1003` timeout (2026-08-21) — fixed

Two lines on every cold boot:

```text
Bluetooth: hci0: command 0x1003 tx timeout
Bluetooth: hci0: Opcode 0x1003 failed: -110
```

`0x1003` is OGF 0x04 / OCF 0x03 = **HCI_Read_Local_Supported_Features**, and
`-110` is `ETIMEDOUT`. It cost two 2-second stalls and pushed `MGMT ver` out to
~13.9 s.

### It was never a functional fault

BT works. `hciconfig` shows `UP RUNNING` with valid features
(`0xbf 0x2e 0x4d 0xfe 0xd8 0x3f 0x7b 0x87`), HCI 5.4, `errors:0`, and a
`bluetoothctl` scan discovers real devices (12 unique in 10 s). The retry loop
in `h713-bt-attach` was absorbing the failure.

Note `hcitool lescan` returns `Set scan parameters failed: Input/output error`
on this system and that is **not** evidence of a fault: it is the deprecated raw
HCI path conflicting with `bluetoothd`, which owns the adapter. Test through
`bluetoothctl`.

### What it actually was

Four hypotheses, measured on cold boots:

| change | result |
|---|---|
| baseline | 2 timeouts, up on attempt 2, MGMT at 13.9 s |
| +5 s settle before attaching | 2 timeouts, just 5 s later — **not a timing race** |
| 115200 instead of 1.5 Mbaud | **fails completely**: 10 attempts, 30 timeouts, hci0 never up |
| + drain `ttyS1` before attach | 0 timeouts, then 1 on the next boot — helps, not deterministic |
| + drain + prime attach/detach | **0 timeouts, attempt 1, on 3 cold boots out of 3** |

Two things fall out of that table.

**The chip is at 1.5 Mbaud from power-on.** The RE port notes
(`local/allwinner-h713-linux/docs/subsystems/wifi-bt.md`) say "the BT chip is at
default 115200 baud at startup, hciattach negotiates up to 1500000, but the
cold-boot timing is off" and recommend baud-rate negotiation as the real fix.
That is wrong for this firmware: attaching at 115200 does not work at all. The
retry loop they and we both shipped was masking a different problem.

**The retry never worked because of elapsed time — it worked because it was the
second attach.** The 5 s settle test is what proves this: waiting longer moved
the timeouts later without removing them. The first `N_HCI` attach after power-on
leaves the controller unable to answer the first HCI command; a detach/re-attach
cycle clears it.

The mechanism is that the BT core emits bytes on `ttyS1` as it boots, and if
`N_HCI` attaches while those are still buffered the H4 parser locks onto the
wrong offset, so the response to the first command is never recognised.

### The fix

`h713-bt-attach` now drains `ttyS1` (`stty` + a 1 s `cat`) and then primes with a
throwaway attach/detach before the real attach. Priming sends no HCI commands, so
a desynced controller costs nothing rather than two 2-second timeouts. Tunable
via `/etc/default/h713-bt-attach` (`BT_BAUD`, `BT_DRAIN`, `BT_PRIME`); the retry
loop stays as the backstop.

Result: zero timeouts, `hci0` up on attempt 1, `MGMT ver` at ~9.0 s instead of
~13.9 s — about 5 seconds off every boot — and scanning still works.

### Cross-check against the vendor binaries (2026-08-21)

The fix above was derived empirically. Checked afterwards against the factory
Android capture (`local/h713-lab/captures/board-b/board-b-mmcblk0-20260705T075628Z.img`,
`super` extracted from LBA 599040). Confirmed by `ANDROID!` at `boot_a`, so it is
a stock image and not our stack.

**Baud and flow control match exactly.** From the AIC BT config in the vendor
image:

```text
# RELEASE NAME: AIC_BT_BLUEDROID
# UART hci commnication bandrate
Uartbandrate=1500000
```

and from the HAL's own option help:

```text
bt uart baud rate, default 1500000
enable ap uart flow control, default disable
bt uart parity, default none
```

So the vendor runs `/dev/ttyS1` at **1.5 Mbaud with flow control disabled** —
which is what this project already used (`hciattach ... 1500000 noflow`), and
independent confirmation that the RE port notes' "default 115200 baud, hciattach
negotiates up" is wrong. The cold-boot experiment and the vendor binary agree.

**Flushing has a vendor analogue.** `tcflush` is referenced five times inside the
BT HAL region, interleaved with `bt_userial_vendor`, `/dev/ttyS1`,
`userial_vendor_open` and `BT_VND_OP_USERIAL_OPEN`. That is a symbol reference,
not proof of the call site — the binaries were not disassembled — but flushing
the port is clearly part of the vendor's serial handling, as it is now part of
ours.

**The mechanism does not match, and cannot.** The vendor image contains **zero**
occurrences of `hciattach` and **zero** of `hci_uart`. Stock Android drives BT
through the Bluedroid vendor HAL (`libbt-vendor`, `bluetooth.default`,
`BLUETOOTH_VENDOR_LIB_INTERFACE`, `userial_vendor_open`), which opens
`/dev/ttyS1` from userspace and feeds HCI to the stack itself. It never attaches
the `N_HCI` line discipline, so the desync that the prime step works around
cannot arise there. Related vendor init, for reference:

```text
setprop persist.vendor.bluetooth_port /dev/ttyS1
setprop ro.bt.bdaddr_path /sys/class/addr_mgt/addr_bt
/dev/ttyS1  u:object_r:hci_attach_dev:s0
```

So the prime/attach-detach step is specific to the mainline `hci_uart` path and
has no stock counterpart — but the two settings that could plausibly have been
wrong, baud and flow control, are confirmed correct against the vendor's own
configuration.
