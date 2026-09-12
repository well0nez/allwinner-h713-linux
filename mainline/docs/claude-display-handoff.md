# H713 display handoff

Last updated 2026-08-07. Operational companion to `docs/mips-display-recovery.md`
(detailed evidence log) and `docs/board-bringup-sequence.md` (boot chain and
state machines).

> **Display bring-up is COMPLETE as of 2026-08-07.** Every item in "Open work"
> below is closed and hardware-verified: the panel renders, double buffering
> removes the tear, the frame survives into Linux, teardown cleans up on
> failure, `0x05280084` is settled, the pre-run FAT-read rule was refuted, the
> `auto` boot logo works (vendor and custom), and the firmware's MIPS-side debug
> shell is confirmed reachable. **The next work is video decode (DECD)**, and it
> starts well-provisioned -- see "Starting point for video decode" at the end.
> Two spent probes from this session (`fb-vsize`, `preread-*`) were removed after
> answering their questions; their findings are recorded and stand.

## Executive state

**The panel works.** It renders a correct red/blue checkerboard, correct solid
primaries, and correct colour bands, all through the ordinary panel init with no
per-test hardware manipulation.

The entire display fault was **one register**: the display PLL at `0x058c0014`.
The vendor table leaves N+1 = 43 (1032 MHz, DCLK 73.71 MHz); the panel needs
N+1 = 36 (864 MHz, DCLK 61.71 MHz against the 62.00 MHz `panel_config.ini` asks
for, 0.46% low, 59.71 Hz). At 43 every pattern arrives carrying colour but no
spatial information at all. Carried as
`h713_panel_cfg_board_b.pll_n_plus_1 = 36`, patched into the LogoRegData record
for `0x058c0014`, so it applies to every path that runs the display sequence.

**The framebuffer path is fixed** as of 2026-08-04, and it was **one register**,
not the two this page spent a day describing:

> `0x0528008c`, the layer's pixel X origin, came up holding **123**. Written to
> **0**, content starts at column 0, fills all 1280, and renders with **zero
> shear**: `fb-fix`'s stock-stride step is one dead-vertical red/blue edge
> drifting 0.0 px per row.

**The root cause was an omission in our own patch table.** `h713_disp_panel_patch`
transcribes stock's panel-patch sites, and left two out on the grounds that
stock's literal zero at `0x05280084[31:16]` and `0x0528008c[15:0]` "may be a
decode artefact rather than a real store; writing a zero we cannot justify is
worse than leaving the vendor default in place." The vendor default is another
panel's, and it is 123. The static analysis was right; the caution was wrong;
what it lacked was hardware.

Restored 2026-08-04 and confirmed (test_35): the record at blob `+0x3584` patches
`0000007b -> 00000000`, the count goes 21 -> 22, and `0x0528008c` reads
`00000000` in **both** dumps -- including after the DE replay, which used to
restore 123. Fixed at source, so no path can miss it.

`0x05280084[31:16]` stayed omitted on the same reasoning, and **that turned out
to be correct** -- settled 2026-08-07 by `fb-vsize`. It is the layer's display
height: writing stock's apparent zero blanks the panel. Same sentence, same
argument, opposite verdicts, and only a measurement per site could tell them
apart.

Both symptoms came from it. The pale left band was the origin directly. The
stride deficit -- the source pointer advancing ~1238 words per row instead of
1280 -- was a *consequence* of it, and disappeared when it was zeroed.
`0x05600170` turns out to be a plain byte stride that was correct all along:
with the origin at 0, `fb-fix` measures **`S = V`** across 1300..1340.

**This is worth reading as a method failure, not just a fix.** The stride was
measured twice, by unrelated experiments, and both agreed on 1237-1238. Neither
was wrong about what it measured -- `S` really was 1238 while the origin was 123
-- and both were wrong about what it *meant*, because a number measured
downstream of a fault got modelled as a fault of its own. That is exactly what
the old log did when it read the pale band as a stride. The same mistake, one
level up, made by the page correcting it.

Applied as a write after the DE replay, for every mode except `fb-band`. Whatever
sets 123 does so before that point and survives the replay, so it is LogoRegData
or the firmware, and a patched record would not be the last word.

**Confirmed on real content, 2026-08-04.** The stock vendor asset renders as
legible red "SMART PROJECTOR" text on a blue field. Legible means unsheared, so
the framebuffer path is correct end to end on the actual file, not just on
synthetic patterns.

**The load-ordering rule was an artifact. REFUTED on hardware 2026-08-07.**

This page said, from 2026-08-04 until now: *"the logo must be loaded after the
display sequence, not before it"*, and that loading before it *"is why
`vendor-logo` never showed anything across five runs"*. `vendor-logo-early` was
kept as a reproducer.

**It does not reproduce.** Run as the first command after a power cycle, with
the 2.7 MB FAT read, the SHA-256 and the BMP conversion all before
`h713_disp_run()`, it renders the logo correctly -- chroma markers, `fbcheck`
bounds, committed frame. Before that, three probes isolating the read (178 ms),
the hash (42 ms) and 3000 ms of pure delay each lit the panel too.

**The best explanation for the original five blank runs is the missing
teardown.** Its documented signature is *"the panel stayed dark while the
console looked perfect"*, costing *"at least four results"* -- and teardown did
not exist when those runs were taken. The bisection that produced the ordering
rule changed the ordering *and* the starting state together, so it never
separated them. That is inference, not proof: what is proven is that the rule is
false today.

`vendor-logo-late` stays the default. It works, nothing prefers early, and
changing it would only churn. But it is **not load-bearing**, and no future
sequencing decision should cite it.

Consequences, for anyone reading older notes: horizontal variation in a
framebuffer image used to become vertical stripes and the bootlogo arrived as a
sheared streak. The TCON pattern generator bypasses this path entirely, which is
why its output was always perfect.

## What is proven, and how

| fact | evidence |
| --- | --- |
| display PLL is `0x058c0014` | `clkfind 0`: N+1 43->42 moved the clock witness -2.28% against -2.326% predicted |
| the PLL runs at 24 MHz x (N+1) | same, plus the counter tracking N to 0.1% across a six-step sweep |
| DCLK = PLL/14 | the panel decodes at 864 MHz and 864/14 = 61.71 vs the 62.00 requested |
| the free-running counter is PLL/56 | 18432 kHz measured against 18428.6 computed |
| the framebuffer conversion is correct | `fbcheck` reads the framebuffer back: bootlogo content in rows 343..378, columns 368..912, exactly matching the file |
| the stride was 1237-1238 px/row **while the origin was 123** | test_30: five `fb-edge` steps give 34.1/31.9/29.9/25.3/22.9 stripes; `S mod P` from five pitches leaves one candidate in 2..4000. test_31 gets 1238 from the register fit, sharing no assumption with it. Both correct, and both were about a symptom |
| `S = V`, once the origin is 0 | test_33: registers 1300..1340 give S = 1300.1/1309.8/1319.4/1329.1/1338.7, and the stock 0x1400 renders a vertical edge |
| the framebuffer path is correct | test_33: red/blue boundary drifts **0.0 display px per row** at the stock stride, full width, no band |
| `0x05600170` controls the stride | test_31: counts track the register 2.96/5.24/7.58/10.01 against 2.3/4.7/7.0/9.3 predicted, and the below-default step leans the other way |
| `0x0528008c` is the layer X origin | test_32: 123 -> band 119.4, **0 -> 0.0**, 400 -> 406.2. Four other candidates screened in the same run moved it by 1 px |
| the band was never framebuffer content | test_32 step 1: it stays pale against a saturated red fill, so a geometry fault, not addressing |
| stride and width are different numbers | test_31 sweeps the stride 1230..1254 and the band holds at 1158 +- 4; test_30 sweeps the pattern and it holds at 1152 +- 2. Neither knob touches it |
| the real vendor asset renders correctly | test_34: legible red "SMART PROJECTOR" on blue -- a sheared frame smears those glyphs into diagonals |
| the band was at the **head** of the line, not the tail | ~120 px blank on the left, content running to the right edge, in all eleven photographs before the fix |
| the photographs are not mirrored | the stripe lean matches the model in absolute sign across five steps of test_31, including the flip at the one step below default; so left is left |
| the band belongs to the framebuffer path | operator observation: TCON generator patterns fill the whole screen, framebuffer patterns are truncated |
| `0x05280084[31:16]` and `0x05280080[31:16]` are layer heights | test_38 `fb-vsize`: 0 blanks the layer (contrast 195->21), 360 crops to the top half with blank below, 1080 reads as baseline because the panel is 720 tall. So stock's apparent zero cannot be a real store, and the omission was correct |
| the U-Boot frame survives into Linux | 2026-08-07: logo still on the panel at the login prompt, and all 12 display registers read back their U-Boot values from the target (`devmem32`). Depends on `clk_ignore_unused`/`pd_ignore_unused` |
| sustained commits work | fb-anim 2026-08-07: 600 frames committed, **0 timeouts**; the manual write-one-to-clear suffices without an ARM IRQ handler |
| completion is **vsync-locked** | same run: 600 frames in 10042 ms = 59.749 Hz vs the panel's computed 59.71 Hz (0.07%), and fill mean + wait max = 16.754 ms vs a 16.747 ms frame period (0.04%) |
| the framebuffer path is single-buffered, and AFBD does not latch the surface | same run: the bar tears during motion and is whole when static -- rewriting the buffer after commit could not tear it if the commit had snapshotted it |
| double buffering removes the tear, and `0x05600178` is latched at the ready write | test_37: rows with no bar go from a **5.97%** median (single-buffered, predicted 11.7% from the 1.95 ms fill in a 16.75 ms frame) to **0.00%** median; a mid-scan re-read of the address could not have cleared it |
| project 0x34 drives the same display path as 0x33 | 2026-08-06 A/B: both select prologue 3 + timing 6, both patch 22/12, `fbcheck` bounds identical, panel indistinguishable; the only surviving register difference is `0x0525c038` (`0x100` vs `0x40`) |

## Ready to run

Artifact hashes move on every rebuild -- U-Boot embeds a build timestamp -- so
the commit is the source identity, not the hash. Rebuild with
`./build/build.sh uboot`.

**The banner names the last commit, not the code.** A build made with
uncommitted edits reports `g<previous-commit>-dirty`, so a log can truthfully
show an older hash while running newer behaviour -- test_35 did exactly that.
Trust `-dirty` and the behaviour, not the hash.

**The display bring-up is done.** Both deferred-load vendor modes render the
stock asset correctly:

```
h713_disp panel-test 0x34 vendor-logo-chroma
```

**Use `0x34`.** It is what this board declares in `panel_config.ini`
(`ProjectID = 52`) and what stock's own log selects. `0x33` renders identically
-- proven, see below -- so no earlier result is invalidated, but new work should
not keep using a value nothing supports. `h713_disp` now prints a note whenever
it is given anything else.

Expect one blink, then two, then a **red "SMART PROJECTOR" on blue** filling the
frame -- rows 343..378 of 720, columns 368..912 of 1280, so about 5% of the
height a third of the way up. `vendor-logo-late` is an alias and behaves
identically.

A brief wrong-looking frame before the logo is normal: the framebuffer is seeded
with `fill_pattern(0)` so that the pre-run FAT read can be avoided, and that seed
is on the panel from the end of init until the logo is published and committed.

**`vendor-logo` works too, and renders the real asset visibly** -- confirmed
2026-08-04. The stock `bootlogo.bmp` is 99% black with pure grey lit pixels
(chroma `|R-B|` exactly 0), and it shows up fine: a light-grey bar on black.

That corrects something this page asserted for most of a day. The repeated blank
results from `vendor-logo` were the **load ordering**, not the palette -- the
2.7 MB FAT read before the display sequence left the panel dark, and every one of
those failures predates the fix. "This path cannot show luminance content" was a
plausible reading of a null that had a different cause, and it was wrong.

The older rule it leaned on is narrower than it was stated. What the old log
established is that *full-field* black/white and greyscale tests read blank --
a uniformly grey screen against a uniformly white one is genuinely hard to
judge. Structured, high-contrast luminance content like a grey bar on black is
not that, and it is perfectly visible.

`vendor-logo-chroma` is still the better instrument when a result must survive a
photograph, since it keeps the same file, hash check, geometry and `fbcheck`
bounds and swaps only the palette -- lit to red, unlit to blue. Use it for
measurement. Use `vendor-logo` when the question is what the product actually
shows.

**Read `fbcheck` before you read the panel.** It runs against the framebuffer in
memory, so it says whether the frame is even worth photographing. Its first
outing caught a broken build the rest of the console cheerfully denied:
`content rows 720..0, columns 1280..0` are untouched initial bounds, meaning *no
pixel matched at all*.

**A dark panel is not evidence about the framebuffer.** Every mode emits a TCON
chroma marker, which reaches the panel without touching the framebuffer path. No
blinks means the panel is not lit and nothing downstream is being tested. Five
runs were spent before that control existed.

To re-measure the framebuffer path itself:

```
h713_disp panel-test 0x34 fb-fix
```

Six steps at registers 1300/1310/1320/1330/1340/**1280**, predicting
11.3/16.9/22.5/28.1/33.8 stripes and, at the stock 1280, **one vertical edge**.

`fb-edge`, `fb-edge-fine`, `fb-stride` and `fb-band` measured the faults and are
superseded by the fixes. `fb-band` alone still skips the origin correction, since
it needs the untouched value for its control step.

### Scoring any of these

**Count the diagonal red/blue stripes.** Row Y starts at source word `Y*S`, so
the boundary slides `S mod P` pixels per row and wraps every `P/|D|` rows. A
720-row frame shows `N = 720*|D|/P` stripes, so every step measures the stride
independently and they must all agree -- much stronger than picking out the
vertical one, and it survives a blurry photograph, since counting a few coarse
diagonals is easy.

Feed the photographs straight to the analyser rather than counting by hand:

```bash
tools/display/edge-measure.py --pitches 1232,1234,1236,1237,1238,1240 IMG_*.jpeg
```

It counts by FFT and by autocorrelation (two methods, because one has no way to
report that it locked onto moire), then searches every stride for the one that
fits all steps. Photographs must be in step order, and **any step that was not
photographed must be dropped from `--pitches` too** -- test_30 has five photos
for six steps and a silently wrong mapping shifts the answer by 4 px.

Do **not** read a multi-stripe step as a failed step, or as moire. It is the
measurement. (An earlier version of this page promised "one boundary per step",
which is true only within ~1.6 px of the answer, and would have made every step
but one look broken.)

Do **not** score any of this on the pale band. The band measures `W`, not the
stride, and cannot respond to the pattern at all; that criterion was wrong and
wasted a run.

## Open work, in value order

Session of 2026-08-04/05 closed the display path. What follows is everything
still outstanding, with the exact next step for each.

### 1. Animated test signal -- RUN 2026-08-07; commits pass, the path tears

**Answered.** 600 frames, zero timeouts, and two facts that were not previously
established.

```
H713 anim: committed 600, timeouts 0 -- sustained commits OK
H713 anim: complete after 600 frame(s) in 10042 ms
H713 anim: commit wait min/mean/max 6800/14620/14800 us; fill min/mean/max 1949/1954/1969 us
```

- **Sustained commits work.** The worry was that `h713_disp_commit_osd_frame`
  hand-manages what stock does in an IRQ handler, and that the old completion
  would remain pending forever without one. 600/600 committed. The manual
  write-one-to-clear before each submission is sufficient; the missing ARM IRQ
  handler is not a blocker for single-buffer output.
- **Completion is vsync-locked -- now measured, not inferred.** 600 frames in
  10042 ms is 16.7367 ms/frame = **59.749 Hz** against the panel's computed
  **59.71 Hz**, a 0.07 % match; and fill mean + wait max = 1.954 + 14.800 =
  **16.754 ms** against a **16.747 ms** frame period, 0.04 %. The commit returns
  when the raster reaches its completion point, so the wait is exactly the rest
  of the frame after the fill. This page previously said 16400 us "suggests"
  this; 600 samples settle it.
- **The path is single-buffered and tears.** Operator: the bar is broken during
  motion and whole once it stops. AFBD streams live from `0x6c100000` while the
  CPU rewrites it -- so the commit does **not** latch the surface, or rewriting
  it afterwards could not tear it. Harmless for a static boot logo, fatal for
  anything animated. See item 1b.

### 1b. Double buffering -- DONE 2026-08-07, confirmed on hardware

**It works.** `fb-anim` against `fb-anim-db` on one boot, filmed and measured
(`local/lcd-photos/test_37/`, `tools/display/tear-measure.py`):

| | rows with **no bar** |
| --- | --- |
| single-buffered | median **5.97 %**, worst 11.12 % |
| double-buffered | median **0.00 %**, mean 0.15 % |

More than half the double-buffered frames are perfectly clean, against a
single-buffered fault predicted at 11.7 % from the fill occupying 1.95 ms of a
16.75 ms frame.

**This also settles the open question about the flip.** The AFBD source address
*is* shadowed and latched at the ready write -- had it been re-read mid-scan the
flip would have torn at least as badly, not cleared. The vblank-write fallback
below is not needed.

**Do not score this on the size of the step in the bar.** A 30 fps
rolling-shutter camera against a 59.75 Hz panel puts about one panel-frame
boundary across the sensor per readout, so a 16 px step is in every camera frame
regardless. Measured that way the two runs are indistinguishable. Use
`tear-measure.py`, which counts rows carrying no bar at all -- something rolling
shutter cannot cause.

The original plan follows.

### 1b-orig. Double buffering -- BUILT 2026-08-07, needs the A/B run

```
h713_disp panel-test 0x34 fb-anim        <- single-buffered, tears (the baseline)
h713_disp panel-test 0x34 fb-anim-db     <- double-buffered, should not
```

**Run both on one boot; the A/B is the measurement.** `fb-anim` deliberately
keeps the single-buffered behaviour rather than being upgraded in place, so the
comparison is one variable on the same instrument instead of a comparison
against a remembered result.

Two surfaces, 4 MiB apart: front `0x6c100000`, back `0x6c500000` (each is
3.74 MiB, so they do not overlap, and both sit below the vendor BMP staging at
`0x6d000000`). Each frame draws into the buffer the hardware is *not* reading,
writes its address to **`0x05600178`**, then commits.

**patches/kernel/0024's `uboot-scanout@6c100000` reservation went from
`0x400000` to `0x800000`** to cover both. Both are live scanout targets now, so
keep the DT and `H713_DISP_OSD_FB_ADDR_B` in step.

A double-buffered run restores the front buffer to `0x6c100000` before it
returns, re-rendering the same frame so the picture does not change while the
state does. Every other mode writes that address and none of them touch the
source register, so finishing on the back buffer would silently break the next
command in the session.

**The way this can still fail, and what it would mean.** The flip assumes the
source register is shadowed in hardware and latched at the frame boundary when
the ready bit is set -- which the existence of a ready register plus a
completion bit strongly suggests. If `fb-anim-db` *still* tears, that assumption
is wrong: AFBD is re-reading the address mid-scan, and the write must instead be
placed inside vblank. That is a different fix, not a broken idea, and the run
distinguishes them.

**Built 2026-08-07, not yet run on hardware.**

```
h713_disp panel-test 0x34 fb-anim
```

A 64 px red bar on blue, stepping 16 px/frame, 600 frames by default (an
optional decimal frame count is argv[5]; Ctrl-C stops it). Scoring:

- **smooth motion** -> sustained commits work
- **a stall** -> the console names the frame it first failed at, then keeps
  going, so "wedged" and "recovered" are distinguishable
- **tearing** -> a *horizontal* discontinuity in the bar. Note the bar also
  *wraps*, appearing at both edges at once -- that is a full-height vertical
  split and is not tearing
- **the position is the frame number.** `x = (frame * 16) mod 1280`, so a
  photograph gives frame mod 80 and the console prints the committed count. If
  the predicted and photographed `x` disagree, the panel is not showing the
  frame the ARM believes it committed -- which no static frame can detect

The summary reports commit wait and fill time separately (min/mean/max), so if
the frame rate is low it is visible *which* half is the limit rather than being
confounded. `h713_disp_commit_osd_frame()` was split for this: its per-frame
printf is ~130 bytes, which at 115200 baud is ~11 ms, comparable to a whole
frame -- printing per commit would have measured the UART. The animation uses a
silent variant and aggregates.

Do **not** combine it with a stride override; the bar would shear and the
position would stop meaning the frame number. The command enforces this by
reading argv[5] as a frame count in this mode.

Deliberately **not** decoded video -- keep DECD separate so a decoder fault
cannot present as a display fault. This becomes the reference for DECD later.

If sustained commits do break, the likely cause is the missing ARM IRQ handler,
which is real work rather than a tweak. Better found now than under a
compositor.

### 2. Teardown on failure -- DONE 2026-08-07, needs one bench check

Every error path in `h713_disp_panel_test`, `h713_disp_init_only` and
`h713_disp_test` now goes through **`h713_disp_fail()`**, which tears down
instead of leaving the panel powered and the MIPS live. Nine error paths
converted; the four success returns deliberately bypass it.

The deferral reason was stale -- nothing was refactoring that signature, and it
has since grown to 28 parameters.

**It is a shared failure handler, not the single exit the plan asked for, and
that is deliberate: success must NOT tear down.** `panel-test` leaving the
display up is load-bearing -- it is what lets `panel-test ... ; boot` hand a live
frame to Linux, which is how item 4 was verified. A single exit covering both
paths would have silently broken that. `init_only` is the same: its whole
purpose is to leave the display up for `scanrate`/`regscan`/`clkfind`.

**Teardown now acquires the display clocks first, which is what the vendor
does.** Its shutdown log reads `ge2d 5240000.ge2d: acquire tvdisp clock on
emergency shutdown` -- it turns the display clock *on* in order to turn the
display off.

That solves a real problem. `h713_disp_teardown()` opens by *reading* the AFBD
control register, and those blocks wedge the interconnect when read gated, so it
could only ever run after a completed sequence. The first version of this item
guarded on `h713_disp_configured` and simply refused otherwise -- leaving the
exact case it was meant to fix (a failure part-way through the sequence, panel
powered, MIPS live) uncleaned. Ungating is the fix; refusing was not.

`h713_display_clocks_on()` is the clock half of `h713_display_prepare()`, split
out so both use it. Every register in it is CCU (`0x02001xxx`), which is always
clocked, and `setbits` is idempotent -- so it is safe from any state and costs
two delays on the common path.

**Consequence:** `h713_disp teardown` from the prompt now works on a cold boot
too. It previously would have hung the board, and briefly refused instead.

**Cold-boot teardown is VERIFIED on hardware, 2026-08-07:**

```
H713 teardown: requested from the prompt
H713 MIPS: display clocks/routing prepared
H713 teardown: panel down (PF_DAT=00000000 PH_DAT=00000000), PHY 18000000/00000030, route 40000000, MIPS reset=00000000
```

The middle line only appears on the cold path, so it marks which branch ran.

It took two attempts. The first ungated only the module clocks and their video2
parent, and hung on the next AFBD read -- **clocks do not open the fabric on
their own.** `h713_display_prepare()`'s own comment says so: *"the initial SPL
values open only part of the display fabric"*. Teardown now calls the whole of
`prepare()` on the cold path, which is the primitive every normal run already
uses cold.

**Also fixed after it wedged the board during this test:** `h713_disp scanrate`,
`regscan` and `clkfind` all read display blocks unguarded and hang on a cold
boot. They now refuse -- a refusal rather than an ungate, because they only
measure, and everything they measure is driven by the display PLL.

**All four checks passed on hardware, 2026-08-07:**

| check | result |
| --- | --- |
| `teardown` cold | works; prints `display clocks/routing prepared` (cold branch) |
| `scanrate` cold | **refuses** instead of hanging |
| `panel-test 0x99` | `cannot read mips/ProjectID_0x0099.TSE` -> `run failed, tearing down` -> panel down. Previously returned silently and left the panel powered |
| `panel-test 0x34` after that | renders, `fbcheck` rows 343..378 / cols 367..912 |
| `teardown` twice, warm | both clean, and **no** `prepare()` line either time |

That last row is the cold/warm branch proving itself: `prepare()` runs only when
`h713_disp_configured` is false, so its absence on the warm path is the
behaviour working, not a missing step.

Incidental: the run after a teardown now reports `FIFO status clear; reset
skipped` where it used to say `status 0x00000002; reset applied`. Teardown is
leaving the FIFO clean, which is a small independent confirmation that it does
real work rather than just dropping rails.

**Still untested**, and only as a combination: an error return *after* the
sequence completes, which would take the warm teardown path. Both halves are
now proven separately -- failure-triggered teardown (cold, via 0x99) and warm
teardown (twice, plus the automatic one at the head of a second run) -- so this
is a missing trigger rather than an untested path.

Remaining to check:

```
h713_disp panel-test 0x99 vendor-logo-chroma
```

fails in `h713_disp_load` before the sequence, so it exercises teardown from a
partly-cold state. Then a normal `panel-test 0x34 vendor-logo-chroma` to confirm
the common path still renders after the extra ungate.

**Untested:** a failure *after* the sequence, which has no easy trigger short of
corrupting `bootlogo.bmp`.

### 3. The backlight -- SOLVED; implementation deferred on hardware

**The light dims, and the control is PB5.**

```
h713_disp bl-gpio 500 10 3
```

`panel_bl_en` (PB5) is the enable of an **on-board boost converter** lifting 36 V
to the 52.6 V the `LED` header delivers, and that converter **dims on
PWM-of-enable** -- the standard technique for LED boost drivers. 500 Hz at 10 %
duty is visibly dimmer with no flicker. Brightness was reachable from the SoC the
whole time, on a pin this project had been holding statically high since the fan
work.

**Not PB4/PWM2**, where every stock source points. Our waveform there was correct
all along; it simply is not what gates the converter.

**But enable-PWM will not be the implementation**, and `bl-gpio` stays a
diagnostic. It dims by starving the converter, so the LED runs below its designed
forward voltage, the usable window is a narrow 7-14 % duty that drifts with
temperature and input rail, and PB5 also powers the fan -- so the whole usable
band starves cooling. **The chosen path is an inline low-side MOSFET in the LED's
negative return**, chopping downstream of the converter's output capacitor: the
converter runs undisturbed, PB5 stays statically high, the fan is untouched.
Module is on hand, hardware not yet fitted. Constraints, the CV-vs-CC check to
run first, and the polarity trap are in
**[backlight-investigation.md](backlight-investigation.md)** section 7.

**One constraint reaches into this tree already:** the module's PWM input is
rated 0-2.5 kHz, so `H713_BL_PWM_HZ` (25 kHz) and patch 0032's
`pwms = <&pwm 2 40000 0>` must both drop to <= 2.5 kHz when it is fitted. 1 kHz
gives 2.5x margin and stays above flicker fusion. Both are deliberately left
alone until then, so the constant keeps matching the measurement that documents
it.

The rest of this item is the historical trail, kept because the reasoning
pattern matters. **Both of its original premises were wrong**, and both were
corrected on 2026-08-05. See the evidence log's top section.

- The firmware HAL route is **closed**. `Thal_Vp_SetBacklightLevel` is a
  non-blocking post to the `app_bottom` thread that returns a hardcoded `1`
  before the message is dequeued, and the firmware makes **zero** MMIO accesses
  to PIO, PWM or CCU. It cannot dim the panel and cannot report that it didn't.
  Do not spend bench time on `commcall` for backlight.
- "PWM2/PB4 does not dim this panel" was a **test artifact**. The stock DTB is
  explicit that PB4/channel 2 *is* the backlight (`panel_pwm_ch = 2`,
  `pwm2_pin_a = PB4`, default brightness 75) and has no pwm5 pin group at all,
  so `panel_config.ini`'s `pwm_channel = 5` is not a SoC channel. Our PWM
  register map was wrong in four places and the channel was never enabled.

`h713_disp_backlight_set()` is fixed against patch 0007's validated map and
builds. **The next step is one bench run:**

```
h713_disp panel-test 0x34 bl-sweep
```

Six steps, 100/75/50/25/0/100 at four seconds each against a full-white field.

**A third fault was found after that sweep, and it is the big one.** The sweep
ran with a verifiably correct PWM and still did nothing, because **PB4's `pwm2`
function is mux 3 and we were driving mux 2**. Patch 0002 -- our own pin table,
and the one the kernel binds -- has it wrong; board B's stock DTB, upstream
H616 and patch 0018 all say 3. That single error also explains the Linux
negative of 2026-07-24, so both prior nulls were one bug in our pin table.
`H713_BL_PWM_MUX` is now 3, rebuilt and verified.

**Run and result, 2026-08-05.** Everything correct at once for the first time:
mux 3, `GATE=00000004`, `EN=00000004`, `PCCR=0` (HOSC/1), duty stepping
960/720/480/240/0, and the counter **proven running** -- +176 counts per 7 us,
wrapping at exactly 960, so 24 MHz and 25.0 kHz confirmed from hardware. Panel
initialised and rendering a full-white field. **No brightness change.**

That is the first clean negative in this investigation. Every earlier null had
the register map or the mux wrong.

**The one remaining unverified link is the pad**, and it needs the DMM, not more
`md`: PB4 in DC mode during the sweep should read ~3.3 V / ~1.65 V / ~0 V at
100/50/0% if the waveform reaches the pin. The PIO data register cannot answer
it -- it reports the output latch, not the pin.

- **tracks duty** -> the panel genuinely ignores a correct PWM, the ARM-side
  route is exhausted, and the 2026-07-24 serial-panel-init hypothesis is what
  remains: the LED driver ignores PWM until its own init has run, which stock
  fastlogo does before Linux. That is the PH10/11/12 logic-analyser capture.
- **flat** -> the waveform is not reaching the pad, and mux 3 vs 2 becomes an
  A/B with the DMM as judge.

**This once read "STILL OPEN", and the caution that kept it open was right.**
The claim was that no software experiment could change the outcome; the question
was held open anyway because the conclusion rested partly on inference. The
inference was that no driver stage existed on the board, and it was false. Had
the item been closed when the software case looked airtight, the answer would
still be undiscovered.

The software case below holds on its own terms -- our PWM is verified live on
PB4 and nothing dims. What it never established is that nothing *could*. The
full consolidated case is in
**[backlight-investigation.md](backlight-investigation.md)** — read that rather
than reconstructing it from this file or the evidence log.

The shipping device tree (`sunxi.fex`, extracted from the OTA package) carries a
complete backlight config -- `panel_pwm_ch = 2`, `panel_pwm_freq = 25000`,
`panel_pwm_pol = 0`, `panel_backlight = 75`, `panel_bl_en` -> PB5 -- and pin
groups for **pwm0..pwm4 only**. `pwm5` has a controller node and **no pin group**,
so it can never be muxed. `panel_config.ini`'s `pwm_channel = 5` is a vendor
build artifact; nothing loads that file at runtime.

So the only configuration stock can successfully apply is **channel 2 / PB4 /
25 kHz / active high** -- exactly what we have now run with a hardware-verified
counter (CNT advancing, wrapping at 960), and it does not change brightness.

And the **vendor kernel has no backlight class at all** and never reads a single
`panel_*` property, so stock has no runtime brightness control either. Booting
stock would add nothing; `docs/flash.md` "Method 5" is documented but its
premise proved false and it should not be run.

**Three claims this page carried were load-bearing and all three were wrong:**

| was | is |
| --- | --- |
| the rail is ~48 V | **36 V** in, dual-output brick (12 V board / 36 V light) |
| the `LED` header is the indicator | it is **the light engine's feed** |
| no LED driver or boost converter on the board | **there is a boost**, 36 -> 52.6 V |

The third was the one that mattered. The argument that closed this question ran:
the light is 2-wire, no driver exists on the mainboard, therefore the supply is
made off-board and no SoC PWM can reach it. The middle premise is false, so the
conclusion never followed -- and the driver being on the board is exactly why
PB5 could reach it.

That premise came from **53 photographs and a component-by-component survey**.
One DMM probe on the output connector refuted it in a second. A photographic
survey is a **lower bound** on what a board contains, the same way a static write
map is a lower bound on register access -- a lesson this project had already
learned once and did not transfer.

What survives, and is narrower than it was read as: **stock does not dim this
panel.** It requests pwm5, the request fails, and the light comes up full anyway.
That is a fact about the vendor's software, not a limit on the hardware, and the
two were being conflated.

**Follow-up regardless of the outcome:** patch 0002 needs the same mux fix for
Linux, and the rest of that table is now suspect. It is a transcription, and
this is the second load-bearing error found in it (after `0x0528008c`).

**Do not drive PB5 low.** The DT calls it `panel_bl_en` and it is shared with
fan power. On a projector with an LED light engine that is a thermal risk.

This blocks finishing the teardown, which should turn the backlight off first
and currently cannot.

### 4. Linux handoff -- PASSED 2026-08-07, visually and by register

**The frame survives.** `panel-test 0x34 vendor-logo-chroma` then `boot`: the
logo stayed on the panel through the whole Linux boot, was still there at the
login prompt, and remained after it. And all twelve registers that would have to
survive for that to be true still hold their U-Boot values:

```
0x058c0014 b8002300 PLL   0x0525c000 02f80550 mixer   0x0524c000 00fc0202 DE/OSD
0x0528008c 00000000 X org 0x05280084 02d00500 size    0x05600140 03001901 AFBD
0x05600170 00001400 stride 0x05600178 6c100000 source 0x05140054 40000080 route
0x051c0014 18000005 PHY   0x051c0028 1f300030 PHY mid 0x05700000 fff11111 TVTOP
                                                          0 of 12 changed
```

Milestone 2b only ever established that Linux *reaches userspace*, and it passed
before any of the framebuffer fixes existed. This is the first time the picture
itself has been checked.

**One dependency is load-bearing and easy to break:** `clk_ignore_unused` and
`pd_ignore_unused` are on the kernel command line, and the boot log confirms
`clk: Not disabling unused clocks` / `PM: genpd: Not disabling unused power
domains`. Without them the clock framework would gate the display PLL as an
unclaimed clock and the panel would go dark. Anyone tidying the command line
needs to know that.

Panfrost probed, Cedrus registered, the DRM module loaded and
`systemd-backlight@backlight` ran, and none of them disturbed the image.
`Console: colour dummy device` -- nothing claimed a console framebuffer.

**Caveat on scope.** This ran on the kernel with the **4 MiB** reservation, so it
validates the front buffer at `0x6c100000` -- which is what a boot logo uses, so
the result stands. The 8 MiB reservation covering the `fb-anim-db` back buffer at
`0x6c500000` is built but was not the kernel under test; until it is flashed,
that region is ordinary allocatable memory and a handoff after a double-buffered
run would be allocated over.

**Reading MMIO on the target needs `mmap`, not `od`.** On arm64 `read()` on
`/dev/mem` is gated by `valid_phys_addr_range()` -> `memblock_is_map_memory()`,
and registers are not memory, so `od` and `dd` return `-EFAULT` on a healthy
board. Use `tools/display/devmem32.c` (freestanding, ~3 KB, small enough to
base64 over serial) or `busybox devmem`, which is now in the rootfs package list.

### 5. `auto` -- DECIDED 2026-08-07: opt-in boot logo, prep stays default

The call: **the product should show the vendor boot logo, `auto` is the command
that does it, and it is opt-in (`auto <id> logo`), not the `auto` default.**

Why opt-in rather than a default flip. `auto` is **not on the boot path** -- the
standalone bootcmd is `mmc read; bootm`, and `auto` is only ever a manual
diagnostic. So making render the default would change no boot behaviour while
adding a `bootlogo.bmp` dependency and ~1.5 s to a command the diagnostics use.
The capability belongs in `auto`; forcing it on does not.

Why a logo at all. It is a projector -- a dark panel through ~10 s of Linux boot
reads as broken, and the vendor shows one. And it is nearly free: item 4 proved
Linux preserves the U-Boot frame, so a logo `auto` publishes **persists through
boot with no Linux display driver**. Cheapest possible boot logo.

**Implemented** as `h713_disp_auto_logo()`: the `panel-test <id> vendor-logo`
sequence (run with the panel powered, quiesce, latch timing, DE reassert with
the PHY/routing saved across it, X-origin fix, publish, commit) with the
diagnostics stripped -- no dumps, no markers, no `fbcheck`, and crucially no
15 s dwell. It replicates the exact state item 4's handoff was verified in
(MIPS quiesced, logo up), so the logo it leaves should survive into Linux the
same way.

```
h713_disp auto 0x34 logo              # hashed vendor bootlogo.bmp
h713_disp auto 0x34 logo <file.bmp>   # custom 1280x720 24-bit BMP on mmc 1:2, no hash
```

**VERIFIED on hardware 2026-08-07, both the vendor and a custom logo.** A custom
`boot-logo.bmp` (converted to 1280x720 24-bit via `tools/display/`... a plain
PIL `convert("RGB").save(...,"BMP")`) published cleanly and **survived `boot` to
the Linux login prompt**, same as the vendor logo in item 4. The teardown-on-
failure path also fired for real when the file was first missing from the FAT --
an unplanned confirmation of item 2.

The custom BMP must be **exactly 1280x720, 24-bit, uncompressed (BI_RGB)**; the
parser refuses anything else rather than mangle it. A standard 24-bit BMP is
2,764,854 bytes, the same as the vendor asset. It goes on **`mmc 1:2`**, which is
`bootloader_b` -- GPT partition 2, host `sda2` under `ums 0 mmc 1`, **not**
`bootloader_a`/`sda1`. The firmware hardcodes `1:2` regardless of the Android A/B
active slot.

To ship it, a product image puts `h713_disp auto 0x34 logo [file]` in `bootcmd`
before `bootm`; the dev standalone boot in `docs/standalone-boot.md` is
deliberately left unchanged.

### 6. Smaller, opportunistic

- **`0x05280084[31:16]`** -- *CLOSED 2026-08-07 by `fb-vsize` (test_38); the
  `fb-vsize` diagnostic has since been removed, the finding stands. It is
  the layer's display height, and the omission was **correct**.*

  | step | write | result |
  | --- | --- | --- |
  | 1 | control | 4 stripes at 26.3 / 50.8 / 74.1 % |
  | 2 | **0** | **layer gone** -- white field, contrast 195 -> 21 |
  | 3 | **360** | **cropped to the top half**, blank below |
  | 4 | **1080** | identical to baseline; the panel is only 720 tall |
  | 5 | neighbour `0x05280080[31:16]` = 360 | identical to step 3 |

  Writing stock's apparent zero **blanks the display**, so it cannot be a real
  store at this point -- either the static read is the decode artefact the
  original caution suspected, or stock writes it where the value is replaced
  before it matters. Restoring it by analogy with `0x0528008c`, which this page
  had been inviting since 2026-08-04, would have blanked the panel.

  **The framing this page carried was wrong.** The justification was not
  "discredited" by having failed at `0x0528008c`; it was *unreliable*, which is
  different, and it turned out to be right here. Two adjacent sites, omitted in
  one sentence for one reason: one a catastrophe, one correct. Only measuring
  each separated them. `h713_disp_panel_patch` needs no change.
- **Why a pre-run FAT read kills the display** -- *CLOSED 2026-08-07; the
  `preread-*` probes have since been removed. It does
  not, and the evidence says it never did.*

  Three probes, each isolating one candidate and each followed by the identical
  `fill_pattern(0)` and run a working path uses: the FAT read (**178 ms**), the
  SHA-256 (**42 ms**), and 3000 ms of pure delay. **All three lit the panel.**
  Then the control: `vendor-logo-early`, first command after a power cycle,
  everything before `h713_disp_run()` -- **it renders correctly.**

  Two things this page had wrong. The pre-run work is **220 ms**, not the
  "seconds of work" claimed since 2026-08-04 -- an estimate written down as a
  characteristic, which made a timing story plausible for three days. And the
  five blank runs carry the missing-teardown signature exactly: "panel dark,
  console perfect", which cost "at least four results" elsewhere on this page.
  Teardown did not exist when they were taken, and the bisection changed the
  ordering *and* the starting state together.

  So the reproducer reproduces nothing, and `vendor-logo-late` is a default
  rather than a requirement. What is proven is that the rule is false today;
  that the teardown explains the original runs is the best available inference,
  not a demonstration.

- **The firmware's UART shell** -- *static analysis done 2026-08-07. It starts
  unconditionally, it is on UART4, and it is a register interface.*

  **The threads start with no gate.** `shell_thread_uart` and
  `shell_thread_monitor` are spawned by a straight-line function at
  `0x8b1834c4` -- no branch, no flag, no config test -- whose single caller sits
  in the main startup path just after the config at `0xabe01000` (the uncached
  alias of the `display_cfg.xml` window we load). **So it is already running in
  our configuration**, whenever the MIPS reaches readiness.

  **It is UART instance 4, not our console.** Input and output both resolve to
  one block: `0xb7501000` (RBR/THR), `+0x7c` (USR, polled per byte), `+0xa4`
  (HALT). USR at `0x7c` and HALT at `0xa4` are DesignWare-specific, matching the
  `snps,dw-apb-uart` the H713 DTs use. H713 UARTs are `0x400` apart, so window
  `+0x1000` is instance 4 -- ARM `0x02501000`. *Inference, not proof:* the
  MIPS-to-ARM window base register has not been found. But it is definitely not
  UART0, which is why three days of logs never showed a byte of it.

  Our pin table routes UART4 to **PH6/PH7/PH8/PH9 at mux 2**, or PD8..PD11 at
  mux 3.

  **It is a register interface, not a log stream.** Command/var/user/key lists,
  `help [cmd]`, line editing, a `Please input password:` gate -- and from
  `./reg_access.c`, **`regr` and `regw`**, register read and write with an
  address validator. That is the coprocessor's own view of the fabric; every
  register result in this project so far is the ARM's.

  **The item's premise was wrong.** It said `display_cfg.xml` references "How to
  use elog command.md". No `display_cfg.xml` on this system contains `elog` at
  all. That text is in `display.bin`, which also carries
  `-r, --route  set elog output route: uart/net`.

  **The password derives statically to `default user`, but is UNCONFIRMED.**
  The gate at `0x8b1831dc` is a plaintext `strcmp(entered, record+8)` -- so you
  type whatever is at `record+8`. The only `"default user"` in the binary is the
  `+8` field of the one `flags=0x2000` entry at `0x8b20dee0`, so that is the
  derived answer. Two gaps stop it being fact: the runtime user list is inferred
  to point at this static entry (not traced), and `+4` is an empty string, so if
  the layout is `{user, password, display}` the password could be empty and
  `"default user"` a label. Only typing it settles it, and the shell cannot be
  reached from the ARM side (it reads UART4's RX pin, not an MMIO-writable
  register).

  **No pin to reach, but a memory mailbox already exists.** UART4's only routes
  are `PH6/PH7` or `PD8/PD9`, nothing broken out on this board (no ethernet, no
  serial pads beyond the console -- operator confirmed), so a wire means
  microsoldering the SoC. **But feasibility for DECD, checked 2026-08-07,
  upgraded this:** there are *two* shell threads, and `shell_thread_monitor` is
  memory-driven, not UART -- it reads a DRAM ring via a device object at
  `*(0x8b232c20)` = system `0x4b232c20` (the `+0x40000000` kseg0 window), inside
  the image the ARM stages. So the wire-free route likely needs **no firmware
  patch**, just writes to a pre-built mailbox. **Confirmed on hardware 2026-08-07:** the global holds `0xabd01000` ->
  `0x4bd01000`, a registered `Terminal`/`SysView` device in the uncached
  `debug_buffer`. Window measured, no cache problem, no patch, no pin -- the
  wire-free route is real. It is idle (buffers zero), so there is no passive log
  to read for free; driving it (push a command into the input ring, poll the
  output) is DECD-time static work, methods already located. Payoff is a
  MIPS-side `regr`/`regw`. See the evidence log.
- **Two pinctrl patches disagree** -- *resolved 2026-08-05, in 0002's favour.*
  The stock U-Boot DTB gives PH17/pwm0 muxsel 3, PH18/pwm1 muxsel 3, PB5/pwm3
  muxsel 2 and PA12 = `pwm4`, all matching patch 0002. Patch 0018's
  `PA12 = pwm5` and `PB4 = mux 3` are upstream *H616* values that do not apply
  to H713. 0018 is inert, so removing the stale entries is still only tidiness.

## Working tools in `h713_disp`

| command | purpose |
| --- | --- |
| `init <id> [quiesce\|noboot]` | bring-up only, no test phases; `quiesce` parks the MIPS, which is what the register diagnostics want |
| `scanrate` | measures the free-running counter; a clock witness, **not** a raster counter |
| `regscan [base] [words]` | finds which registers move and what they count |
| `clkfind [n]` | lists candidates, or perturbs one and watches the clock witness |
| `panel-test <id> tcon-chroma` | RGB solids and red/blue checkers -- the reference that must render correctly |
| `panel-test <id> fb-edge` | the stride measurement, 1180..1200 -- the range that produced 1237 by extrapolation |
| `panel-test <id> fb-edge-fine` | 1232..1240, closes the stride to the pixel |
| `panel-test <id> fb-stride` | pattern fixed, AFBD `0x05600170` swept -- answered: live, `S = V - 42` |
| `panel-test <id> fb-fix` | pattern at the natural 1280, swept for the register that unshears it |
| `panel-test <id> fb-band` | solid fill, screens offset registers for the ~105 px left band |
| `panel-test <id> <mode> <stride>` | any mode with `0x05600170` forced to `<stride>` bytes, applied after the DE replay |
| `panel-test <id> fb-vprobe` / `fb-hprobe` / `fb-quad` / `fb-grid` | framebuffer geometry probes |
| `panel-test <id> fb-anim [frames]` | moving red bar, **single-buffered** -- the sustained-commit test, and the tearing baseline |
| `panel-test <id> fb-anim-db [frames]` | same bar, **double-buffered** via the AFBD source address; run both on one boot |
| `panel-test <id> vendor-logo` | the vendor bootlogo, with `fbcheck` verifying the conversion |
| `teardown` | stop scanout, park the MIPS, drop the panel rail; run twice to prove it |
| `tools/display/edge-measure.py` | host-side: stripe count -> stride, from the photographs |
| `tools/display/devmem32.c` | target-side: read MMIO from Linux. Freestanding aarch64, no libc, ~3 KB so it base64s over serial. **`od`/`dd` cannot do this on arm64** |
| `tools/display/handoff-check.sh` | target-side: the same registers as a pass/fail table, with a `-w` watch mode; needs busybox/devmem2/python3 |
| `tools/display/tear-measure.py` | host-side: counts rows with no bar in an `fb-anim` video -- the tearing metric that is **not** confounded by the camera's rolling shutter |

**Power-cycling between runs is no longer needed.** `panel-test` tears down
first when it has already run this boot, and the second run renders correctly --
verified on hardware 2026-08-04, both chroma markers and the logo.

The old rule was: each mode ended holding the MIPS in reset, so a second run
initialised into a torn-down state and the panel stayed dark while the console
looked perfect. That cost at least four results. It was never a property of the
hardware -- it was the absence of a teardown.

`h713_disp teardown` also runs it standalone. What it does, in order: stop
scanout, park the MIPS, return the LVDS PHY and display route to their cold
values, then drop PH16 and PF6 with the panel's declared off timings
(20/75/250 ms). Confirmed output:

```
panel down (PF_DAT=00000000 PH_DAT=00000000), PHY 18000000/00000030,
route 40000000, MIPS reset=00000000
```

`0x00000000` on the reset register is the **asserted** state.

The likely reason a second run used to fail is visible in that line: the
bring-up powers the panel by driving PF6 high and pulsing PH16, so with the
panel still powered from the previous run that "power on" was a no-op and the
panel never re-ran its own init.

Two gaps remain, both deliberate and both commented in the source. The backlight
is not touched, because which PWM drives it is unresolved. The PLLs and mod
clocks are left running, because disabling a clock while something still reaches
for the block is the documented way to wedge this interconnect -- and the
bring-up rewrites that state absolutely, so the acceptance test passes without
it.

## Method notes that cost real time

- **Use chroma, never luminance.** The optical path normalises luminance away.
  Every solid black/white and greyscale test in the old log read blank regardless
  of what the link was doing, which invalidated years of results.
- **A pattern is only as good as the photograph it must survive.** Fine features
  photographed handheld alias into moire. Two numbers in this session came from
  moire and had to be withdrawn. Prefer few large features.
- **Never report a property the instrument cannot measure.** A column-only metric
  said "no row alternation" when the rows were fine. A row-luminance profile said
  the logo was correct when it was horizontally sheared. Uniform-width bands
  "proved" a framebuffer path that was 8% wrong.
- **State the premise as a number and check it before crediting the result.** The
  retune guard -- "the clock witness must move by X% or this run means nothing" --
  caught three false conclusions cheaply.
- **Prefer the photograph to the metric when they disagree.** The operator saw a
  checkerboard that the scoring metric ranked below a worse setting.
- **Two symptoms of one fault are still two measurements.** The band and the
  stripes were both called "the pitch", so a number from the band was used to aim
  a sweep at the stride. Six steps, a rebuild and a bench run all missed, and the
  answer was never inside the range. Before a sweep, say which quantity each
  observable measures, and check that the thing being swept is that quantity.
- **Design the sweep so a miss still measures.** Every step of that run was
  wrong, and the run still gave the answer to +-1 px, because the stripe count is
  a slope rather than a match. A sweep scored on "which step looks right" would
  have returned nothing at all.

## Superseded claims

Do not resurrect these; each cost bench time.

- `0x05880000` is **not** a raster position counter. It is one free-running
  10-bit counter presented twice with a fixed offset. Every "scan=... proves the
  raster is live" claim in the old log is void.
- The panel clock does **not** come from the CCU's `PLL_VIDEO2` at `0x02001050`.
  Retuning it moves nothing.
- The Saleae captures cannot decode this LVDS stream: 31.25 kS/s analog against
  434 Mbps, short by a factor of ~14000, with a front end that cannot see the
  signal at any rate.
- A static write map of the firmware is a **lower bound** on register access,
  never an inventory. It resolved 604 of 845 call sites and the answer to the
  contested-register question was among the rest.
- **"The logo must be loaded after the display sequence."** Refuted 2026-08-07:
  `vendor-logo-early` renders correctly, and read, hash and time each lit the
  panel on their own. The five blank runs that produced this rule match the
  missing-teardown signature, which had no fix when they were taken. Do not
  re-derive a sequencing constraint from them.
- The pale edge band is **not** a panel or TCON artefact.
- The bootlogo was never "vertically collapsed" -- the BMP is a black frame with
  text only in rows 343..378, and it rendered faithfully once the PLL was fixed.
- **"The display fetches ~1187 pixels per line" conflated two numbers.** 1187 was
  a content width taken off the band and then used as though it were the source
  stride. The stride is 1237-1238; the width measures 1155 +- 5. Any
  reasoning that treats one figure as both is void, including the sweep ranges it
  produced -- 1180..1200 could not have contained the answer.

## Vendor runtime facts, from booting the stock stack (2026-08-06)

First observation of the vendor display path running on the bench, via the
first-stage swap in `docs/flash.md` Method 5. Two things here contradict
assumptions this project has been building on:

- **The vendor selects project id `0x34` on this board, not `0x33`.**
  `[01.868]Project id:0x34 version:25-1-6-3`, and it then loads
  `mips/ProjectID_0x0034.TSE`. Our own bring-up has been running
  `h713_disp panel-test 0x33` throughout. **Retested 2026-08-06 and settled:
  every 0x33 result stands** -- see below.
- **`panel_config.ini` is a runtime input**, read from `Reserve0` when `/oem`
  misses. It carries the PWM channel the fastlogo path requests. See
  `docs/backlight-investigation.md` section 0.

The vendor's load order, for comparison with `h713_disp_run()`:
`panel_config.ini` -> `LogoRegData.bin` (version 25-4-10-157) -> pwm request ->
`display.bin` (0x132910 to 0x4b100000) -> `display_cfg.xml` (0x1287 to
0x4be01000) -> `database.TSE` (0x44f60 to 0x4be41000) -> `pq_custom.TSE`
(0x3aa8 to 0x4be85f60) -> `projecttable.TSE` (0x568 to 0x4be89a08) ->
`ProjectID_0x0034.TSE` (0x4398 to 0x4be89f70) -> `Display fastlogo finish!`.
The window base and the two big artifacts match ours; the sizes and the project
id are the new information. **The four TSE files do not match** -- see the load
order item under "Smaller, opportunistic".

### The 0x34 retest, 2026-08-06

`panel-test 0x33 vendor-logo-chroma` then `panel-test 0x34 vendor-logo-chroma`,
same boot. Full evidence and the static prediction that preceded it are in the
evidence log's top section.

| observable | 0x33 | 0x34 |
| --- | --- | --- |
| triple | prologue 3, timing 6, de 5 | prologue 3, timing 6, de 6 |
| patched / guarded | 22 / 12 | 22 / 12 |
| DE records applied | 55 | 56 |
| `0x0528008c` | `7b -> 0` at `+0x3584` | `7b -> 0` at `+0x390c` |
| `0x0525c038` | `00000100` | **`00000040`** |
| fbcheck | rows 343..378, cols 367..912 | identical |
| panel | legible logo | no visible difference |

The two ids **share prologue 3 and timing 6 outright**, so the PLL, the LVDS
lane map, the panel timing and every patch site outside the DE block are
bit-identical. Their DE blocks differ in four records, three of which sit at
sites the patch table overwrites and converge on the same value. The only
surviving difference is `0x0525c038` (`H713_DISPLAY_MIXER_CTRL_REG`).

**Consequence: no 0x33 result needs revisiting.** New work should still use
`0x34` -- see "Ready to run". The equivalence above covers the ARM's LogoRegData
replay; the `ProjectID_*.TSE` payloads differ by 2688 bytes, feed the MIPS, and
are exercised by nothing we have.

**Corollary:** our explicit `writel(0x100, 0x0525c038)` before the DE walk is
**not load-bearing**. Under 0x34 the vendor's own table overwrites it with
`0x40` and the panel renders identically.

Two differences went unexplained at the time. **One is now answered**: the
`afbd-mux +0x20` shift was the **TSE load order**, not the project id -- see the
load-order item above. The other, `ready=0` vs `ready=1` on the commit line,
still has one sample per configuration and a third value since, which is what
sampling noise looks like. Neither changed the render.

**Analyse against the right blob.** `LogoRegData.bin` word 1 is a packed version
(`[31:24]` year, `[23:20]` month, `[19:12]` day, `[11:0]` build).
`local/mips-display/board-b-mips/` is `0x1940a09d` -> 25-4-10-157, which is what
the board printed. `research/bootloader_fat/` and the board-A capture are
24-6-3-82 with 13 descriptors, and DE block 6 runs off the end of that file.

## Starting point for video decode (DECD)

Display is done; DECD is next. What this bring-up leaves ready for it:

- **A liveness/tearing reference signal.** `panel-test <id> fb-anim` (single-
  buffered, tears) and `fb-anim-db` (double-buffered, clean) are the moving-bar
  instruments, scored by `tools/display/tear-measure.py`. Video is the
  integration test *after* the decoder works; the bar is the controlled
  reference that a decoder fault cannot masquerade as.
- **Sustained commits and vsync lock are proven.** 600 frames, 0 timeouts,
  59.75 Hz measured against a 59.71 Hz panel. The commit handshake works without
  an ARM IRQ handler.
- **Double buffering, and the flip lever.** `0x05600178` is the AFBD source
  address, shadowed and latched at the ready write. A decoder that produces
  frames drives the same flip.
- **The frame survives into Linux**, depending on `clk_ignore_unused` /
  `pd_ignore_unused` on the command line. Reservations are correct; the 8 MiB
  `uboot-scanout` covers both buffers (flash the current kernel before any
  handoff after a double-buffered run).
- **A MIPS-side debug channel, confirmed reachable.** `shell_thread_monitor` is
  memory-driven: a `Terminal`/`SysView` device at `*(0x4b232c20)` = system
  `0x4bd01000` (the `+0x40000000` kseg0 window, measured), uncached, in the 1 MB
  `debug_buffer`. Driving its ring gives `regr`/`regw` from the coprocessor's own
  side of the fabric -- the register view every result so far has lacked. No
  patch, no wire; see the evidence log. This is exactly the visibility DECD wants
  when the MIPS is moving frames through buffers the ARM must locate.
- **The address window is the shared fact.** DECD frame buffers on the MIPS side
  convert to the ARM side the same way: MIPS kseg0/1 physical `+0x40000000`.

Read `docs/mips-display-recovery.md` top sections for the evidence behind each of
these; this page is the operational summary.
