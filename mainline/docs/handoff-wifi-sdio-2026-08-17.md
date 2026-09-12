# Handoff — WiFi / SDIO

Updated: **2026-08-21**

Branch: **`h713-aic8800-vendor-rebase`**

Full chronological evidence: [wifi-failure-2026-08-17.md](wifi-failure-2026-08-17.md)

This is the orientation document. The evidence log is intentionally long and
contains the commands, register values, failed hypotheses, and raw outcomes.

## Bottom line

**The SDIO link is done.** It runs at the stock configuration — four-bit
UHS-SDR104 with a 50 MHz ceiling — and the device tree number now means what it
says. Bulk transfer passes both directions with zero faults.

Two separate problems had to be fixed to get here, and they are easy to
conflate:

1. **Bulk RX failed** (2026-08-18). Cause: the v5p3x IDMA descriptor encoding
   for an exact maximum-size segment. Fixed by patch 0046.
2. **The reported clock was ~4x lower than the physical one** (2026-08-19), so
   every rate ever configured was four times what it claimed. Fixed by patch
   0048 and validated on hardware 2026-08-21 — see
   [The 50 MHz question](#the-50-mhz-question--2026-08-19-the-reported-clock-is-not-the-real-one).

The original acceptance test now passes in both directions on a RAM-loaded
kernel:

| direction | result |
|---|---|
| workstation → board (board RX), 8 MiB | **PASS**, SHA-256 exact |
| board → workstation (board TX), 8 MiB | **PASS**, SHA-256 exact |
| SDIO errors/retries during boot and both copies | **zero** |
| `ksdioirqd/mmc1` afterward | healthy, `S` in `sdio_irq_thread` |

Test payload SHA-256:
`4896f3533e373a1f4b8e898750461c9f837d303178fa6b03bf3dc3b31fec4269`.

The root cause was the v5p3x IDMA descriptor encoding for an exact maximum-size
segment. Linux splits a large SDIO transfer into 4096-byte SG entries because
the v5p3x host advertises `max_seg_size = 4096`. Our descriptor builder encoded
an exact 4096-byte entry as zero, inherited from older sunxi controllers. The
Allwinner v5p3x driver writes **4096 explicitly**. Making that distinction for
`host->cfg->v5p3x` eliminates the board-RX FIFO/hardware-lock failure.

## What is committed

Four hardware-tested changes were committed during this session:

- `df1738e mmc: sunxi: add H713 v5p3x UHS negotiation`
  - per-speed v5p3x delay programming
  - v5p3x CMD11/update-clock semantics
  - v5p3x card-read threshold support
  - stock FIFO trigger value
  - UHS capability declarations
  - AIC V3 clock override changed to `0`, preserving the MMC core's negotiated
    clock
- `977244c mmc: sunxi: restore bus state before CMD53 retry`
  - restores `CLKCR` and `WIDTH` after the controller reset
  - keeps retry bounded and mechanically functional
  - also carries the one-character hunk-count repair found by applying the
    complete patch series from scratch
- `9d7054c mmc: sunxi: use validated SDR25 timing for H713 WiFi`
  - selects UHS-SDR25 at 25 MHz and programs the cold-start phase state that
    avoids the first two CRC errors
- `7ac0845 mmc: sunxi: encode v5p3x max IDMA segment explicitly`
  - applies the Allwinner v5p3x 4096-byte descriptor contract
  - makes the original inbound WiFi acceptance test pass

The important boundary on `df1738e`: our code successfully negotiates and
enumerates 4-bit UHS-SDR104 at 50 MHz, but the first 512-byte CMD53 at that rate
still fails with data CRC/end-bit errors. The commit is a UHS-negotiation
milestone, not a claim that 50 MHz payload transfer works.

That boundary was resolved on 2026-08-19, and not the way it first looked: the
reported SDIO clock was about 4x lower than the physical one, so "50 MHz" was
asking the link for ~200 MHz. The accounting was corrected on 2026-08-21 by
patch 0048, so `max-frequency = <50000000>` is now genuinely 50 MHz and it
passes. See [The 50 MHz question](#the-50-mhz-question--2026-08-19-the-reported-clock-is-not-the-real-one).

## Working configuration

**Current (2026-08-21, hardware-validated):** `patches/kernel/0048-mmc-sunxi-h713-run-sdio-at-stock-sdr104-50mhz.patch`,
on top of 0043–0046. Four-bit UHS-SDR104, `max-frequency = <50000000>`, honest
clock accounting. This is stock parity and it is what the series ships.

The 25 MHz configuration below is the previous state, kept because the evidence
for 0045/0046 was gathered against it. Note that its "25 MHz" was physically
~100 MHz; see the correction section.

- `patches/kernel/0045-mmc-sunxi-use-validated-sdr25-for-h713-wifi.patch`
  - limits the SDIO node to UHS-SDR25 at 25 MHz — **superseded by 0048**, which
    restores the UHS modes and the 50 MHz ceiling
  - programs the validated cold-start state before the first CMD53:
    `DRV=00030000`, `NTSR=81710010`. **Still live**; 0048 does not touch it, and
    the per-speed table selects the 104M entry (`NTSR=81710110`) at 50 MHz
  - avoids the two initial data-CRC errors rather than relying on recovery
- `patches/kernel/0046-mmc-sunxi-use-v5p3x-max-idma-descriptor-size.patch`
  - encodes an exact 4096-byte v5p3x IDMA buffer as `4096`, not `0`
  - this is the change that made the original inbound copy pass
  - **still required**; 0048 deliberately keeps it

`patches/kernel/series` includes 0045, 0046 and 0048 in the tested order.

Still untracked:

- `patches/kernel/board/sysrq.config` — debug/test configuration only
- `.backup/` — user-owned; **do not touch or add it**

## Decisive evidence

### Clean cold initialization

With 0045 and 0046 applied, the board logged:

```text
v5p3x delay: rate=400000 timing=4 width=4 DRV=00030000 NTSR=81710010
v5p3x delay: rate=25000000 timing=4 width=4 DRV=00030000 NTSR=81710010
mmc1: new UHS-I speed SDR25 SDIO card at address 85e2
```

The firmware loaded and `wlan0`/the hotspot came up with no `cmd53`, CRC,
FIFO, hardware-lock, phase-retry, or timeout messages.

### Failure immediately before the descriptor fix

At the same SDR25 rate and phase state, but with the old zero encoding, startup
was clean and the 8 MiB inbound copy later failed under load. Its first fault
was:

```text
RINT=0x00000800 IDST=0x0000a000
```

`RINT=0x800` is `HARD_WARE_LOCKED`; `IDST=0xa000` is the IDMA
`WRITE_REQUEST_WAIT` state. Retries then showed response timeouts
(`RINT=0x200`) interleaved with IDMA receive completion (`IDST=0x2`). The
kernel remained responsive and `ksdioirqd` returned to `S`, proving the earlier
deadlock fix still held, but the AIC command channel was dead.

### Success with explicit 4096-byte descriptor lengths

FIT boot and both subimage hashes were verified by U-Boot. The board mounted
the normal Debian root and negotiated:

```text
clock:          25000000 Hz
actual clock:   25000000 Hz
bus width:      4 bits
timing spec:    sd uhs SDR25
signal voltage: 3.30 V
```

Then:

1. workstation `192.168.4.78` copied 8 MiB to board `192.168.4.1`
2. board file size was 8,388,608 bytes and SHA-256 matched
3. the same file was copied back to the workstation
4. workstation size and SHA-256 matched
5. final `dmesg` contained no SDIO error/retry messages

This isolates the bulk-RX fix from the earlier phase work: 0045 removed the two
startup CRC errors; 0046 removed the later inbound-load failure.

## What was learned about the controller

- The SD/MMC command path, four-bit setup, UHS negotiation, firmware transfers,
  and bidirectional bulk transfer all work with the correct v5p3x contracts.
- The eMMC on the separate controller continues to enumerate at HS400.
- The CRC/end-bit checks are performed by the MMC controller/card protocol.
  The cryptography engine (CE) is not involved.
- A generic “controller is broken” explanation is now refuted. The remaining
  50 MHz error is a high-speed timing/signal-integrity problem, separate from
  the fixed 4096-byte IDMA descriptor bug — and, per the 2026-08-19 section, it
  was a signal-integrity problem at ~200 MHz, because the reported clock is ~4x
  lower than the physical one.
- Recovery remains valuable containment, but the passing run generated no
  errors for recovery to handle.

## Current hardware state

Updated 2026-08-21: the board is running the **production** patch-0048 FIT — no
`sysrq` fragment — cold-booted after a physical power cycle and `ext4load`ed
from its own rootfs, at a genuine 50 MHz, four-bit UHS-SDR104, stock parity.
8 MiB and 128 MiB both directions with zero faults. Its rootfs carries
`/root/fits/`: `prod.fit` (the production image below), `test.fit` (the same
change with `sysrq`), `good-25mhz.fit` (the previous known-good), `timing2.fit`
(CMD53 timing instrumentation) and `knobs2.fit`, so any of these is one
`ext4load` away.

**Nothing has ever been flashed for this work.** An unattended power-on still
runs the previously flashed kernel, which does **not** contain 0045/0046/0048
and should still be treated as broken for board RX. Keep `good-25mhz.fit` in
place so a failed experiment is one reboot away from a working link. The extra
board USB/OTG cable is not required; the UART cable is the only cable used.

Production artifact (patch 0048, no config fragment):

```text
build/out/h713-kernel.fit
size   7741216 bytes
sha256 51044da6e73441420d81d4fb6e387e6d351efb6b1574e7527e35016d14f5b0a1
tree   build/linux-6.18.38-577fb0d96df8c37211b6d8c0da6fdc2f7f2937eb365032bfa6307ac117bb2cf6
```

Its `.config` differs from the validated `sysrq` kernel by exactly four symbols
(`CONFIG_MAGIC_SYSRQ`, `_SERIAL`, `_SERIAL_SEQUENCE`, `_DEFAULT_ENABLE`) and
nothing else. Confirmed on the running board by the absence of
`/proc/sys/kernel/sysrq`. Note the consequence: **there is no sysrq escape on
this kernel**, so a wedge needs a physical power cycle.

Earlier artifacts, for reference: the `sysrq` 0048 build was
`b82642aedf10f54a1ef9e47cde217e62471f3b987011a4abda51248128884b22` (7745700
bytes, tree `…-36796f34b125…`); the 25 MHz reference was
`b057085e8f61d079806d0f9fb31b41e1dffcebbdef9948da6f48eb72351d06fe` (7745528
bytes, tree `…-7fe9c8012b42…`).

## Recommended next steps

1. ~~Build the normal production FIT and re-run the acceptance test~~ — **done
   2026-08-21**, see [Cold boot, production kernel](#cold-boot-production-kernel-2026-08-21).
2. ~~Repeat the round trips from a true cold boot~~ — **done 2026-08-21**.
3. ~~Flashing~~ — **done 2026-08-21**. The FAT geometry was reconciled and the
   production FIT written; `bootcmd` now boots it unattended. See
   [the FAT section](#the-fat-on-mmc-12-was-larger-than-its-partition--fixed-2026-08-21).
4. Optional, and no longer blocking: confirm by measurement that the eMMC's
   retained POSTDIV is doing the work the register values suggest (see
   [What happened to the eMMC](#what-happened-to-the-emmc)). Nothing depends on
   the answer unless someone wants to change mmc0/mmc2.

Items 4 and 5 of the previous list — fixing the clock accounting and then
choosing the rate deliberately — are **done**; that is patch 0048.

Do **not** begin with stock Android/vendor boot anymore; the original failure
now has a locally verified cause and fix. Do not spend time on CE, TCP ACK
filtering, RF strength, skb allocation, or generic retry-count increases; those
paths were tested or rendered irrelevant by the zero-error passing run.

### Upstream: an AIC8800 FullMAC driver is in review (noted 2026-08-21)

AIC Semiconductor has posted an RFC to `wireless-next` adding a mainline SDIO
FullMAC driver for **AIC8801, AIC8800DC and AIC8800D80** — our exact chip, our
exact interface. Four patches, 132 files, 67k+ insertions, authored by Zhirun
Liu.

- v2: <https://lwn.net/Articles/1084468/> (2026-07-23)
- v1: <https://lwn.net/Articles/1083998/>

If it lands it replaces the out-of-tree vendor `aic8800_fdrv` that
`patches/aic8800/` patches. Three things follow, and the first is the reassuring
one:

1. **The SDIO transport work survives it.** Patches 0046 (v5p3x IDMA descriptor)
   and 0048 (clock accounting) live in `drivers/mmc/host/sunxi-mmc.c` and
   `ccu-sun50i-h713.c` — the MMC host controller and clock tree, not the WiFi
   driver. They are independent of whatever sits on top of the SDIO bus.
2. **The regulatory patch would be obsoleted, and the problem is open upstream
   too.** `aic8800-0006` exists only because the vendor driver self-manages
   regulatory with a compiled-in `"00"`. The RFC's own stated limitations list
   "the regulatory database" as requiring follow-up work, so this is not solved
   there yet either. If a mainline driver moves to standard cfg80211 regulatory,
   the `regulatory.db` load-ordering bug recorded in
   [evidence log section 11](wifi-failure-2026-08-17.md) stops being academic —
   cfg80211 is built in and requests the database ~373 ms before the rootfs
   mounts, so it would need `CONFIG_EXTRA_FIRMWARE`, a modular cfg80211, or an
   initramfs.
3. **It does not help Bluetooth.** The series carries `aic_btsdio.c`, which is
   BT over *SDIO*. This board wires BT over *UART* (`ttyS1`, H4), so our attach
   path is untouched by it.

**Do not reorient around this yet.** It is an RFC at v2, unmerged, and its own
limitations note that "firmware redistribution permission and the corresponding
linux-firmware submission are not yet available" — which blocks it regardless of
code review, since the driver is inert without firmware. DT power and wake
bindings are also absent. A 67k-line vendor contribution usually takes several
rounds or a substantial rewrite. Worth tracking; not worth planning against.


## The 50 MHz question — 2026-08-19: the reported clock is not the real one

**Corrected conclusion.** An earlier version of this section said 50 MHz was
unreachable on this board. That was wrong, and the reason is worth stating
plainly: **the SDIO clock this stack reports is about 4x lower than the clock on
the wire.** Asking for "50 MHz" was asking the link for roughly 200 MHz, which
is why it failed in every mode, at every phase, and with every card-side pad
setting. Stock is proven to transfer both directions at 4-bit UHS-SDR104 /
50 MHz; so does this board, and in our current accounting that is spelled
`max-frequency = <12500000>`.

### How the factor arises

Two independent doublings compound:

- `sunxi_mmc_clk_set_rate()` doubles the module clock for the v5p3x 2X timing
  mode (`clock <<= 1`, guarded by `cfg->no_wait_pre_over`), ported from the
  vendor driver, and halves the rate it reports back.
- mainline's H616 CCU declares the MMC clocks with
  `SUNXI_CCU_MP_WITH_MUX_GATE_POSTDIV(..., 2, 0)` — a fixed /2 post-divider — so
  `clk_set_rate(R)` programs the divider chain to `2R`.

Nothing then halves the result the way both layers assume, so the card sees
about `4 x ios.clock`.

### The measurements

`patches/kernel/0047` (untracked, debug) times individual CMD53 payloads.
Per-request software overhead is ~4 us against milliseconds of bus time, so the
slope of duration against transfer size reads the bus rate directly:

| reported `ios.clock` | measured slope | implied bus clock |
|---|---|---|
| 12.5 MHz | 41.1 ns/byte (24.3 MB/s) | **48.6 MHz** |
| 25 MHz | 20.6 ns/byte (48.5 MB/s) | **96.9 MHz** |

Both fits are clean — constant ~4.4 us intercept, 957 and 645 samples, sizes
512 B to 32,256 B — and scale exactly 2x with the requested rate.

Independent of that instrumentation, an ordinary `scp` settles it: at a reported
1 MHz the board received 8 MiB at **568 KB/s**, and a genuine 1 MHz 4-bit bus
cannot exceed 500 KB/s. Nothing moves data faster than its own bus.

### What each configuration really was

These are the numbers **in the old, 4x accounting** — before patch 0048. Read
the left column as "what the device tree said at the time", not as anything you
would write today.

| `max-frequency` | physical clock | result |
|---|---|---|
| 12.5 MHz | ~50 MHz | **PASS** — 4 x 8 MiB both directions, 0 faults. This is stock's configuration |
| 25 MHz (committed) | ~100 MHz | PASS, plus a 128 MiB soak — roughly double stock |
| 30 / 35 MHz | ~120 / ~133 MHz | PASS, 128 MiB soak at ~133 MHz |
| 40 MHz | ~150 MHz | fail — start-bit and CRC errors at every phase |
| 50 MHz | ~200 MHz | fail — data CRC on the first CMD53, every mode and phase |

The "wall between 33 and 37.5 MHz" recorded earlier is a real analog wall, but
it sits at roughly **133–150 MHz on the wire**, not at 33–37.5.

Everything eliminated during the sweeps still stands as fact — mode, host phase
space, stock's re-latch, the AIC8800 iopad registers — those runs simply took
place at ~200 MHz, where no timing setting was going to help.

### What this means for the tree

The committed configuration (`max-frequency = <25000000>`, patch 0045) has been
running the AIC8800 at about 100 MHz — twice stock — for the whole bring-up. It
passes acceptance and soaks, but it was never a deliberate choice, and it leaves
modest margin below a wall that starts near 133 MHz.

Two things follow, in this order:

1. **Fix the accounting, not the rate.** The link speed should be whatever the
   device tree says. That means removing one of the two doublings on the SDIO
   path; the candidate is the driver's `clock <<= 1` / `rate >>= 1` pair, which
   `patches/kernel/0047` already makes switchable via
   `sunxi_mmc.h713_nodouble=1`. Before committing that, instrument the eMMC
   (`mmc@4022000`, a different cfg with no doubling — one gate change in 0047):
   if its clock is also 2x its label, the post-divider assumption is wrong for
   the whole SoC and the fix belongs in `ccu-sun50i-h616.c` instead.
2. **Then choose the rate deliberately.** With honest numbers, stock parity is
   `max-frequency = <50000000>`, and the measured headroom above it is real but
   modest (~133 MHz passes, ~150 MHz does not).

The 33.33 MHz patch drafted earlier was withdrawn: it was an unintentional
~133 MHz overclock premised on the wrong reading.

### 2026-08-21 — resolved: patch 0048, validated on hardware

`patches/kernel/0048-mmc-sunxi-h713-run-sdio-at-stock-sdr104-50mhz.patch`
removes **both** compensations, for MMC1 only, and restores the vendor device
tree's modes and ceiling:

- drops the driver's `clock <<= 1` / `rate >>= 1` pair in
  `sunxi_mmc_clk_set_rate()`. That pair is gated on `cfg->no_wait_pre_over`,
  which only `sun50i_h713_cfg` sets — and only `mmc@4021000` uses that
  compatible — so the eMMC cfg is untouched by construction, not by luck.
- changes `mmc1_clk` from `SUNXI_CCU_MP_WITH_MUX_GATE_POSTDIV(…, 2, 0)` to plain
  `SUNXI_CCU_MP_WITH_MUX_GATE(…)` in `ccu-sun50i-h713.c`. `mmc0_clk`/`mmc2_clk`
  keep the post-divider.
- restores `sd-uhs-sdr50` / `sd-uhs-sdr104` / `sd-uhs-ddr50` and
  `max-frequency = <50000000>`.
- keeps 0046's explicit 4096-byte IDMA descriptor encoding.

The remaining `clock <<= 1` in that function is mainline's `MMC_TIMING_MMC_DDR52`
block and is deliberately left alone.

**Hardware result.** RAM/rootfs-loaded FIT, nothing flashed:

```text
v5p3x delay: rate=50000000 timing=6 width=4 DRV=00030000 NTSR=81710110
mmc1: new UHS-I speed SDR104 SDIO card at address 6721
```

| check | result |
|---|---|
| mmc1 negotiated | 4-bit UHS-SDR104, clock and actual clock both 50000000 Hz |
| 8 MiB workstation → board | PASS, SHA-256 exact |
| 8 MiB board → workstation | PASS, SHA-256 exact |
| 128 MiB both directions | PASS, SHA-256 exact (1:49 in, 1:00 out) |
| SDIO faults | **zero** — no cmd53, CRC, FIFO, hardware-lock, phase-retry or timeout lines |
| `ksdioirqd/mmc1` | healthy, `S` in `sdio_irq_thread` |
| eMMC | unchanged: HS400, 8-bit, 200 MHz; rootfs healthy |

### Cold boot, production kernel (2026-08-21)

Everything above was a `sysrq` debug kernel booted by `bootm` without an
intervening power cycle. Repeated on the production kernel from a genuine
power-on reset — mains cycled by hand, autoboot interrupted, FIT `ext4load`ed
from p26:

```text
v5p3x delay: rate=50000000 timing=6 width=4 DRV=00030000 NTSR=81710110
mmc1: new UHS-I speed SDR104 SDIO card at address 6721
```

| check | result |
|---|---|
| mmc1 negotiated | 4-bit UHS-SDR104, clock and actual clock 50000000 Hz |
| CCU `0x02001834` | `0x8100000B`, unchanged after the soak |
| 8 MiB both directions | PASS, SHA-256 exact |
| 128 MiB both directions | PASS, SHA-256 exact (1:41 in, 0:57 out) |
| SDIO faults | **zero** |
| `ksdioirqd/mmc1` | `S` in `sdio_irq_thread` |
| eMMC | HS400, 8-bit, 200 MHz; rootfs `rw` |

Cold init is clean on the first CMD53 — the single `v5p3x delay` line at
50 MHz, with no 400 kHz retry storm and no phase rotation before it.

### The FAT on `mmc 1:2` was larger than its partition — fixed 2026-08-21

**Resolved.** The filesystem was oversized; the GPT was right. `mmcblk0p2`
(`bootloader_b`) is 65536 sectors = 32 MiB, and its FAT16 `total_sectors_32`
said 262144 = 128 MiB. That window runs through `env_a`, `env_b`, `boot_a` and
half of `boot_b`, all occupied, so growing the partition was never an option.

Only our six `h713-kernel*.fit` files were beyond the boundary; all 45 vendor
artifacts were already inside it. The fix deleted those six, patched
`total_sectors_32` to 65536, and put the validated production FIT back —
verified on a copy first, all 45 vendor files bit-identical.

The board now autoboots the 0048 production kernel unattended from the FAT.
Full account, including the cluster arithmetic and the exact commands, in
[the evidence log](wifi-failure-2026-08-17.md) section 9.

Two things to carry forward:

- **Never run `fsck.vfat -a` on this volume.** It would rename
  `mips/ProjectID_0x0014.TSE` to `FSCK0000.000` and rewrite the volume label.
  Read-only checks (`-n`) only.
- **3.4 MB free.** One kernel FIT fits and no more — parking several
  experimental FITs there is what caused the overflow. Stage experiments on the
  ext4 rootfs and `ext4load` them.

Note for anyone re-deriving this: Linux writes to that filesystem failed
*safely* (the block layer clamps to the partition), so Linux could never have
corrupted `boot_a`. U-Boot's `fatwrite` does not clamp and was the real hazard.

### Reading the clock without instrumenting anything

This is the part worth reusing. Do not trust `/sys/kernel/debug/clk/mmc1/clk_rate`
to check a change to the clock model — it is computed *by* the model you just
edited. Read the CCU register instead.

**The H713 CCU is at `0x02001000`, not H616's `0x03001000`.** MMC0/1/2 clock
registers are `0x02001830` / `0x834` / `0x838`.

```sh
busybox devmem 0x02001834        # -> 0x8100000B
```

Decoding `0x8100000B` against `SUNXI_CCU_MP_WITH_MUX_GATE(…, 0, 4, 8, 2, 24, 2, BIT(31), 0)`:
bit 31 = gate on; mux `[25:24]` = 1 = `pll-periph0-2x`; P `[9:8]` = 0 → 1;
M `[3:0]` = 11 → 12. `clk_summary` gives `pll-periph0-2x` = 600 MHz (and
`pll-periph0-4x` = 1200 MHz, so the naming is internally consistent). Therefore
**600 / 12 = 50 MHz at the pin**.

The decisive part: that is the *same divider* the old nominal-12.5 MHz
configuration programmed — doubled to 25 MHz by the driver, then multiplied by
the modelled post-divider to a 50 MHz chain target, giving M=12 — and patch
0047's CMD53 timing instrumentation measured that configuration at **48.6 MHz on
the wire**. Same register value, same physical rate. So the current setting is
confirmed against a prior physical measurement, with no need to re-instrument.

### What happened to the eMMC

Patch 0048 leaves `mmc0_clk`/`mmc2_clk` on the post-divider model, and the
register values suggest that is not merely cautious but necessary:

`0x02001838` reads `0x02000002` → mux 2 = `pll-periph1-2x` (1200 MHz), M = 3,
P = 1, so the divider chain emits **400 MHz**, which the model reports as
200 MHz. HS400 is a DDR mode and needs the module clock at twice the card clock,
but mainline's `sunxi_mmc_clk_set_rate()` only applies that doubling for
`MMC_TIMING_MMC_DDR52`. So the "wrong" post-divider appears to be supplying
exactly the doubling HS400 requires, and removing it SoC-wide would break the
eMMC rather than fix it.

**This is inference from register values, not a measurement**, and an attempt
to measure it on 2026-08-21 **failed to settle it** — see
[evidence log section 10](wifi-failure-2026-08-17.md). Short version: the eMMC
is media-limited at ~118 MB/s, far below either candidate bus rate, so payload
timing only yields a lower bound (card clock ≥ 59 MHz). Capping the eMMC to
25 MHz does make it bus-limited, but the resulting figure matches neither
hypothesis, so there is an unidentified ~1.7x factor in the eMMC data path and
throughput cannot be converted to a card clock there the way it can on SDIO.

Register evidence actually leans the *other* way: both controllers run
`CLKCR` divider 1 with `SDXC_2X_TIMING_MODE` set, and on mmc1 — the measurable
one — the card clock equals the CCU chain output. Applied to mmc0 that would
mean 400 MHz, i.e. HS400 at twice its rated maximum. Against that, this eMMC has
never produced an error. The likely reconciler is that the controller halves for
DDR modes and mmc1 is SDR, which would make the label honest — unconfirmed.

Still true: confirm before anyone touches mmc0/mmc2, and nothing else depends on
it. What is new is that the cheap method has been tried and does not work, so
do not start there again.

(The gate bit reads 0 for `mmc2` when the eMMC is idle — sunxi-mmc drops the
module clock on runtime suspend. The divider fields still show the last
programmed value.)

## The AP configuration was the throughput limit, not SDIO (2026-08-21)

Worth reading before anyone optimises the SDIO path further. With 0048 the SDIO
bus measures **24.4 MB/s**, but the hotspot was emitting plain 802.11g — `hw_mode=g`
with no `ieee80211n`, which `iw` confirmed as `width: 20 MHz (no HT)` at
48/54 Mbit/s. So the validated bus was being fed through an 11g straw, and every
"WiFi is slow" observation in this project may have been this rather than SDIO.

The radio is a 1x1 dual-band part: `HT supp 1, VHT supp 1, HE supp 1`, HT20/HT40
on both bands, VHT 1-stream MCS 0-9 with 80 MHz short GI.

Measured on hardware, 128 MiB each direction, SHA-256 exact and **zero SDIO
faults** in every case:

| AP configuration | negotiated | board RX | board TX |
|---|---|---|---|
| 2.4 GHz, no HT (as shipped) | 48 / 54 Mbit/s | 1.33 MB/s | 2.37 MB/s |
| 2.4 GHz HT40 | 150 / 135 Mbit/s MCS7 | 4.85 MB/s | 7.65 MB/s |
| 5 GHz VHT80 ch36 | 180 / 292 Mbit/s VHT | **13.25 MB/s** | **14.41 MB/s** |

5 GHz is about 10x the shipped configuration and, notably, **removes the
long-standing RX/TX asymmetry** — the two directions come out within 9% of each
other, where 11g differed by 1.8x. At 14 MB/s the link finally uses a
substantial fraction of the 24.4 MB/s bus, so the SDIO work now actually matters.

`tools/rootfs/customize.sh` generates the AP config, and it now enables HT
always and takes `HOTSPOT_BAND=2.4|5`.

**Decided 2026-08-21: 2.4 GHz HT40 is the default**, chosen for client
compatibility and range rather than accepted as a fallback. 5 GHz VHT80 is about
3x faster and removes the RX/TX asymmetry, but it drops 2.4-only clients, has
shorter range, and carries stricter regulatory obligations — pointed here
because `regulatory.db` is absent and the stack runs under permissive rules.
Running both at once is worse than either alone (see below), so this is a real
choice, not a compromise between two things you can have.

The bench board runs this configuration and it survives a reboot: channel 6,
40 MHz, MCS7, ~6.5–7.7 MB/s each way with zero SDIO faults. Deployments that
want 5 GHz set `HOTSPOT_BAND=5` in the hotspot config.

One trap: `vht_capab=[MAX-MPDU-11454]` makes hostapd die with `Unable to setup
interface`. This driver reports a max MPDU length mask of 1, so the highest
valid value is `[MAX-MPDU-7991]`. The failure message names the capability, but
only in the first few lines of the attempt.

### Simultaneous 2.4 + 5 GHz: possible, and a bad trade

Tested 2026-08-21 because "let the client pick the band" is the obvious thing to
want. It works, and you should still not do it.

`iw phy` advertises `#{ AP } <= 1`, but that is not enforced — a second AP vif
can be created with `iw dev wlan0 interface add ap2 type __ap`, and a second
hostapd on it comes up fine. Both really do beacon: a scan from the workstation
saw the same SSID on **2437 MHz (ch 6) and 5180 MHz (ch 36) at once**, both at
full signal, with the interfaces reporting 40 MHz and 80 MHz respectively.

The cost is the problem. This is a **1x1 part with a single RF chain**, so it
time-slices between the two channels, and the 5 GHz link pays for it:

| configuration | board RX | board TX | 5 GHz rx rate |
|---|---|---|---|
| 5 GHz alone | 13.25 MB/s | 14.41 MB/s | 433 Mbit/s VHT-MCS9 80 MHz |
| 5 GHz **+ 2.4 GHz concurrent** | **3.82 MB/s** | **6.85 MB/s** | 86.7 Mbit/s |
| 5 GHz alone (control, after teardown) | 13.21 MB/s | 14.58 MB/s | 433 Mbit/s |

The control rules out drift: tearing the second AP down restores the original
numbers exactly, so the loss is attributable to concurrency.

Two details that make it worse than the table looks:

- **The 2.4 GHz AP had no clients at all.** That 71% RX loss is the cost of
  beaconing on a second channel, before any second-band traffic exists.
- **Dual-band 5 GHz (3.82/6.85) is slower than single-band 2.4 GHz HT40
  (4.85/7.65).** If the goal is reaching the widest set of clients, plain
  2.4 GHz HT40 beats dual-band on both compatibility *and* speed.

So the choice is one band, and it is a genuine trade rather than a default:
2.4 GHz HT40 for compatibility and range, 5 GHz VHT80 for roughly 3x the
throughput and no RX/TX asymmetry. True simultaneous dual-band needs a second
radio — a USB adapter running its own hostapd — not this chip.

Not tested, and it would be needed before anyone deploys the dual setup anyway:
no client ever associated to the second AP, and `dnsmasq` only serves `wlan0`,
so a usable version needs both APs bridged with DHCP on the bridge.

## Running another rate experiment

The old recipe (remove 0045, rebuild, YMODEM the FIT) works but costs an
11-minute UART upload per boot. Use this loop instead — it is what produced the
table above, at roughly 2.5 minutes per configuration.

**1. Deliver FITs over the working WiFi link, boot them from eMMC.** With a
good kernel running, copy the FIT into the board's own rootfs, then have U-Boot
read it back:

```sh
scp build/out/h713-kernel-sysrq.fit root@192.168.4.1:/root/fits/test.fit
python3 tools/serial/reboot-to-uboot.py /dev/ttyUSB0 45
python3 tools/serial/boot_kernel.py --load /root/fits/test.fit --secs 60
```

`boot_kernel.py` now defaults to the Debian root args and takes `--load`
(pass `--rdinit` for an initramfs smoke FIT). **U-Boot parses the partition
index as hex**: p26 is `mmc 1:1a`, and `mmc 1:26` silently means partition 38.
Keep a known-good FIT there (`/root/fits/good-25mhz.fit`) so a failed
experiment is one reboot away from a working link, with no UART upload.

**2. Sweep from the kernel command line, not from rebuilds.**
`patches/kernel/0047-mmc-sunxi-h713-sdio-tuning-knobs.patch` (untracked, debug
only, inert by default) adds:

| parameter | effect |
|---|---|
| `sunxi_mmc.h713_fmax=<Hz>` | override `f_max` — the rate ladder |
| `sunxi_mmc.h713_uhs=<0\|25\|50\|104>` | lower the advertised UHS ceiling |
| `sunxi_mmc.h713_dly=<cmd_drv,dat_drv,cmd_ph,dat_ph>` | force the delay state above 26 MHz |
| `sunxi_mmc.h713_sampdl=<raw>` | raw `SAMP_DL`/`DS_DL` value |
| `sunxi_mmc.h713_relatch=1` | stock's 2X-timing re-latch after a phase change |

`patches/aic8800/aic8800-0005-D80-card-side-SDIO-iopad-controls.patch` (also
untracked) does the same for the card: `aic8800_bsp.aic_iopad_ctrl`,
`aic_iopad_dly1`, `aic_iopad_dly2`, all `-1` (untouched) by default. Module
parameters on the kernel command line reach modules loaded later, so both sets
are settable through `--extra`.

**3. Judge the run correctly.** Enumeration is not a pass — every failing 50 MHz
configuration enumerated. A pass needs `rwnx_load_firmware` lines, the hotspot
up, 8 MiB copied both ways with matching SHA-256, and:

```sh
dmesg | grep -E 'cmd53|fifo error|phase error|data error|HARD|timed-out'
```

empty. Then soak it before believing it.

## Boot-test gotcha

**Fixed in the tool.** `tools/serial/boot_kernel.py` used to install
initramfs-only bootargs (`rdinit=/init`) unconditionally, which is wrong for
this Debian-root FIT: one RAM boot panicked before WiFi, and U-Boot then
overwrote the uploaded image on restart, costing a second 11-minute UART upload.
It now defaults to the Debian root arguments and takes `--rdinit` for the
initramfs smoke FIT.

The equivalent by hand, if you are driving U-Boot directly:

```text
setenv fdt_high 0x4f000000
setenv initrd_high 0x4f000000
setenv bootargs 'console=ttyS0,115200 earlycon loglevel=8 root=/dev/mmcblk0p26 rootwait rootfstype=ext4 rw net.ifnames=0 panic=10 clk_ignore_unused pd_ignore_unused cma=128M'
iminfo 0x50000000
bootm 0x50000000
```

The workstation also prints a changed-host-key warning for `192.168.4.1`
(offending entry currently reported at `~/.ssh/known_hosts:16`), although the
key-based copies completed. Do not modify the user's known-hosts file silently.
The 2026-08-21 run sidestepped it with a throwaway known-hosts for the duration:

```sh
scp -o UserKnownHostsFile=/dev/null -o StrictHostKeyChecking=no build/out/h713-kernel-sysrq.fit root@192.168.4.1:/root/fits/test.fit
```

The workstation joins the board's hotspot with a saved NetworkManager profile
(SSID `spirits`, DHCP) and lands on `192.168.4.78`.
