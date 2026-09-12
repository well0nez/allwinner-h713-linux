# H713 projector backlight: the case so far

**Status: SOLVED 2026-08-06 (late) — the light dims, from PB5.**

```
h713_disp bl-gpio 500 10 3     -> noticeable drop in brightness
```

`panel_bl_en` (PB5) is the enable of the on-board boost converter that lifts
36 V to the 52.6 V the `LED` header delivers, and **that converter dims on
PWM-of-enable** — the standard technique for LED boost drivers. 500 Hz at 10 %
duty is visibly dimmer, with no flicker at that rate. Brightness has been
controllable from the SoC the entire time, on a pin this project has been
holding statically high since the fan work.

**Not on PB4/PWM2.** Every stock source points there — the shipping DTB's
`panel_pwm_ch = 2`, our patch 0032 `pwm-backlight`, `bl-sweep` — and it does
nothing, because it is not what gates the converter. The vendor's own firmware
never dims either (section 0), so this is a capability of the hardware that the
shipping software does not use.

**The blocker for a real feature is the fan, not the light.** PB5 is shared with
fan power, so modulating it modulates cooling in lockstep: at 10 % duty the fan
gets 10 % too. Fine for a three-second test, not for use. **Section 7 has the
chosen path** — an inline chopper downstream of the converter, which leaves PB5
static and the fan untouched — and why enable-PWM will not be the
implementation.

The question this document set out to answer was narrow: **can the brightness of
this projector's light engine be controlled from the SoC, and if so how?**
Answered: yes, and the how is above. Everything else about the display — panel
init, timing, framebuffer, the MIPS coprocessor — works and was always out of
scope.

**PB5 has no PWM function** in this SoC's pinmux (`gpio_in`/`gpio_out` only,
confirmed against `pinctrl-sun50i-h616.c`), so the SoC cannot drive it with
hardware PWM as wired. Either bit-bang it, or move the converter's enable to a
pin that has a PWM function — PB4 being the obvious candidate, already routed
for exactly this role and already carrying a correct 25 kHz waveform.

Written 2026-08-05 for external review; the section-0 result arrived when the
vendor stack was booted on the bench, and the boost measurement the same
evening. This consolidates a thread that runs across
`docs/mips-display-recovery.md` (300 KB, chronological) and
`docs/claude-display-handoff.md`. Read this instead of reconstructing it from
those.

---

## 0. The answer, from the vendor's own U-Boot

Booted via the persistent first-stage swap (`docs/flash.md` Method 5), with the
vendor's `bootloader_a` FAT restored so its display path could run for real:

```
[01.863]LogRegData.bin version is 25-4-10-157
[01.868]Project id:0x34 version:25-1-6-3
[01.872]pwm_request: err: get reg-base err.
[01.876]pwm5 request for fastlogo fail!
...
[03.334]Display fastlogo finish!
```

Four findings, all direct runtime observations rather than inference:

1. **Stock asks for PWM channel 5**, not channel 2. `panel_config.ini` is read
   at runtime — from `Reserve0`, after `/oem` misses — and `pwm_channel = 5` is
   what reaches `pwm_request`.
2. **That request fails on this hardware**, with `get reg-base err`: pwm5 has a
   controller node but no pin group, exactly as the static analysis predicted.
   So the vendor never obtains a PWM for the backlight.
3. **`Display fastlogo finish!` prints anyway.** It is *not* a backlight
   success indicator, and no `Pwm enable fail` is emitted. The plan of using
   one message versus the other to discriminate was based on a false dichotomy.
4. **The panel lit and the light engine came on regardless** (operator
   observation, same boot). The vendor firmware reaches full brightness with no
   working PWM request at any point.

### The kernel and the app say the same thing

Vendor Android was then booted end to end on the same board (its `userdata`
had to be reformatted f2fs first — `UDISK` held our ext4 Debian rootfs, which
`fs_mgr` refused with `invalid magic`). Linux 5.4.99, launcher up, projector
app running. From its boot log:

```
[  0.098] sunxi_pwm_probe: can't get pwm  bus clk
[  3.932] sunxi_pwm_enable_dual: can't parse pwm device
[  6.330] __switch_pwm_state: can't parse pwm device
[199.039] sunxi_pwm_enable_dual: can't parse pwm device     <- runtime
[202.364] init: ... Received control message after shutdown <- operator powered down
```

**The vendor kernel's PWM driver never probes** (`can't get pwm bus clk` at
0.098 s), so every later request fails. The entry at 199 s is not boot-time
probing — it is a *runtime* attempt, three seconds before the operator shut the
board down, i.e. while they were moving the brightness slider in the projector
app. The UI control does reach a PWM path, and that path fails.

Operator observation across the slider's full range, same session: **some
change on screen, no change in the light spilling from the panel cable.**
Unaided visual, not instrumented — the one claim here still resting on an
eyeball. It is, however, exactly what the log predicts: the on-screen change is
digital (picture-quality gain in the DE/MIPS path, the `pq_custom.TSE` side)
while the light engine is never addressed.

**What this section establishes, and what it does not.** Every layer of the
shipping firmware — boot0's U-Boot, the Linux PWM driver, and the projector
app's own brightness control — fails to acquire a PWM, and the light runs at
full brightness throughout. That is a complete account of the *vendor's
software*.

It is **not** a statement about the hardware, and this document spent a while
treating it as one. The conclusion originally drawn here — that the only
surviving hypothesis was an off-board driver, leaving a purely physical question
about where the light's two wires terminate — was wrong in both halves. The
driver is on the mainboard (section 1), and the light dims from PB5 (status,
top). Stock not using a capability is weak evidence that the capability is
absent, and it was being read as strong.

---

## 1. The hardware, as far as it is known

- Board `HY200_QZ713DF_A1 20250304`, Allwinner **H713** (`QA206DA`), sun50iw12.
- Panel: 1280x720 LVDS, driven via a MIPS coprocessor running vendor
  `display.bin`. **This all works** — the panel renders correct images.
- The light engine is a separate module. **Its cable has only two conductors,
  power and ground** (operator observation). It runs at **36 V** — corrected
  2026-08-06; earlier text throughout said ~48 V, which was a guess. The AC/DC
  brick has two outputs: **12 V feeds the board, 36 V feeds the light**, and the
  36 V passes through the mainboard, arriving and leaving via the 2-pin `LED`
  header next to `IR` (see section 3, inference 3).
- ~~**53 photographs of the mainboard show no LED driver and no boost
  converter.** Every inductor is a 2R2 (2.2 µH) buck for the SoC rails,
  clustered near the DC jack. There is no high-voltage electrolytic, no power
  FET pair, no current shunt. Photos in `local/board_images/`.~~

  **REFUTED 2026-08-06 by direct measurement.** The `LED` output connector reads
  **52.6 V** against a **36 V** input. Nothing passive produces that: **there is
  a boost converter on this mainboard**, and the photographic survey missed it.
  Fifty-three photographs and a component-by-component reading were not enough
  to see a power stage that a single DMM probe found immediately.
- ~~The board has a 2-pin connector silkscreened `LED`, next to a 3-pin `IR`. It
  has thin signal-width traces and no adjacent power stage, so it is very
  unlikely to be the light engine feed; it matches the DT's indicator LEDs
  (`led0` on PL0 red, `led1` on PL1 blue).~~
  **REFUTED 2026-08-06** — that header *is* the light's feed, and the indicator
  LEDs are board-mounted with no connector at all. See section 3, inference 3.
- `PB5` is `panel_bl_en` and is **shared with fan power**. It is the enable of
  the boost converter feeding the light, and `h713_disp bl-gpio` modulates it
  deliberately.

  **The old warning here — "never drive it low, thermal risk" — had the
  reasoning backwards.** Driving PB5 low turns the light *and* the fan off
  together, which is the safe combination. The real hazard is the opposite end:
  **sustained low duty**, where the light still emits while the fan runs at the
  same fraction of power. Short runs are fine; leaving it modulated is not, and
  that is exactly why enable-PWM is not the shipping plan (section 7).

~~**Implication, and the current leading hypothesis:** if the light is 2-wire and
no driver exists on the mainboard, the supply is generated off-board, and no SoC
PWM can affect it unless a control wire physically reaches that off-board
driver.~~

**Dead, 2026-08-06.** Its premise was "no driver exists on the mainboard", and
the 36 V -> 52.6 V measurement refutes exactly that. The driver is *on the
board*, so a control wire does not have to leave it, and the argument that no SoC
PWM could ever reach the light collapses with the premise. **This reopens the
backlight question rather than closing it.**

What survives independently of this paragraph: stock requests pwm5, that request
fails, and the light still comes up at full brightness. So stock has no working
PWM path either -- but "stock does not dim it" is a much weaker claim than "it
cannot be dimmed", and only the second one was resting on the missing driver.

---

## 2. What is proven, and how

| fact | evidence |
| --- | --- |
| PWM channel 2 on PB4 is configured correctly and **actually running** | `CNT` register advances +176 per 7 µs and wraps at exactly **960**, giving 24 MHz and 25.0 kHz; duty steps 960/720/480/240/0 against a fixed entire of 960; `GATE=0x4`, `EN=0x4` |
| the PWM register map is mainline `pwm-sun20i-d1` | the counter wrap at 960 confirms `PERIOD[31:16]` is *entire − 1*, not an active count |
| PB4's `pwm2` function is **mux 3** | shipping DTB `muxsel = <0x03>`, upstream mainline H616 table, and patch 0018 all agree |
| driving that correct, running PWM changes brightness **not at all** | bench run 2026-08-05, full-white field, panel initialised and rendering |
| the MIPS firmware cannot drive a PWM | exhaustive effective-address scan of all 240,266 instructions in `display.bin`: **zero** accesses to `0x02000000`–`0x02002000` (PIO/PWM/CCU). Run twice, second time preserving callee-saved registers across `jal` |
| `Thal_Vp_SetBacklightLevel` is a non-blocking post that reports success unconditionally | worker `0x8b148ca4` has no conditional branch and ends `addiu $v0,$zero,1`; it queues `{opcode 2, level}` to the `app_bottom` thread via `IThread` vtable slot 3 with timeout 0 |
| the vendor kernel has **no backlight support at all** | vendor `vmlinux` (ARM 32-bit 5.4.99, full DWARF): zero backlight-class symbols, zero references to any `panel_*` property, no `Thal_Vp`/`SetBacklight` strings |
| stock sets the backlight once, in U-Boot fastlogo | stock U-Boot contains `pwm_request`, `sunxi_pwm_pin_set_state`, `Display fastlogo finish!`, and reads the `panel_pwm_*` / `[PWMSetting]` keys |
| the shipping DTB's backlight config is ch2 / 25 kHz / active-high / 75 | `sunxi.fex` from the retail OTA: `panel_pwm_ch=2`, `panel_pwm_freq=0x61a8`, `panel_pwm_pol=0`, `panel_backlight=0x4b` |
| **`pwm5` cannot be muxed on this product** | `sunxi.fex` has a `pwm5@2000c15` controller node but **no pwm5 pin group**; pin groups exist only for pwm0–pwm4. Stock calls `sunxi_pwm_pin_set_state`, which needs one |

**Net:** the only backlight configuration stock can successfully apply is
channel 2 / PB4 / 25 kHz / active high — which is exactly what we now run, with
the PWM verified live, and it does nothing.

**Why it does nothing, established 2026-08-06:** PB4 is not connected to
anything that reaches the light. The converter's control is PB5, and PB4's
waveform — correct in every respect the rows above measure — has no path to the
hardware. Every row in this table stands; the inference drawn from the fourth
one, that a running PWM with no optical effect means the light cannot be
dimmed, does not. It means *that pin* does not reach it.

---

## 3. What is inferred, not proven

A reviewer should attack these first.

1. ~~**That `panel_config.ini` is not a runtime input.**~~ **REFUTED
   2026-08-06.** It is a runtime input: the vendor's U-Boot reads it from
   `Reserve0` (after trying `/oem`), and its `pwm_channel = 5` is what reaches
   `pwm_request` — which then fails, because channel 5 has no pin group. Both
   halves of the old argument were wrong in the same direction: the file *is*
   loaded, and "channel 5 could not work anyway" was true but irrelevant, since
   stock asks for it regardless and simply fails. The shipping DTB's
   `panel_pwm_ch=2` is not what the fastlogo path uses.
2. **That the light has no dimming path at all.** Based on the 2-wire cable plus
   the absence of a driver on the mainboard. Nobody has traced the cable to its
   other end or identified an off-board driver.
3. ~~**That the `LED` 2-pin connector is the indicator, not the light.**~~
   **REFUTED 2026-08-06, by two independent facts from the operator:** that
   connector *is* the light engine's feed, and the indicator LEDs are mounted on
   the board itself with no connector at all. The reasoning that produced the
   wrong answer — thin traces, no adjacent power stage — was a correct
   *observation*: photo `IMG_0362` shows the `LED` header beside `IR` with only
   chip passives around it. A 2-pin JST at ~1 A does not need wide traces, and
   the absence of a driver beside it means something else: the rail arrives
   already regulated.

   **The supply is a dual-output AC/DC brick: 12 V for the board, 36 V for the
   light** (not the ~48 V assumed throughout this document), and the 36 V enters
   the mainboard and leaves again through this connector. That is why no boost
   converter or LED driver was ever found — none is needed.

   **There is a high-side switch in the 36 V path** (continuity, board
   unpowered, 2026-08-06): the return pin is uninterrupted to board ground, and
   **the positive is not** — something sits between the 36 V input and the
   connector's `+`. That is almost certainly what `panel_bl_en` on PB5 drives.

   This separates two claims that had been running together. *The shipping
   firmware never dims this light* is established (section 0). *The hardware
   cannot dim it* is *not* — there is a switching element in the light's supply,
   and if it is a MOSFET its gate is a dimming lever the vendor never used.

   Open, and the next thing to chase:
   - **What the part is.** Probe from the `LED` `+` pin to neighbouring pads to
     find its output, then read the package and marking.
   - **What drives its gate.** A 3.3 V GPIO cannot drive a gate referenced to a
     36 V source directly, so expect a small NPN or N-FET level-shifting stage.
     *That stage's input is what to PWM*, not the power device itself.
   - **Whether that gate drive is fast enough to modulate.** A stage sized for
     on/off with a large pull-up resistor will have slow edges and dissipate
     badly at 25 kHz. Measure the rise/fall before committing to a frequency;
     an inline module with a proper gate driver remains the fallback.
   - **Whether its input is shared with fan power.** If PB5 drives both, the
     vendor interlocked them, and dimming means separating the nets: fan enable
     stays on PB5, the light's gate stage moves to PB4.
4. **That the waveform physically reaches the PB4 pad.** The counter proves the
   channel generates internally. Nothing has measured the pin. The PIO data
   register cannot answer this — it reports the output latch, not the pad
   (proof: PC's data register reads `0x00000000` while the eMMC bank on PC is
   actively in use).

---

## 4. Conclusions that were reached and then reversed

Recorded so a reviewer does not re-tread them, and because the pattern is
informative.

- **"The PWM register map was wrong in four places."** False. The original map
  (mainline `pwm-sun20i-d1`) was correct; it was changed to match
  `pwm-sun8i.c`/patch 0007 and that broke it — a block dump then showed
  `0x02000c40 = 0`, `0x02000c80 = 0` and a static counter. Reverted. The
  evidence cited for patch 0007, a live capture of `PERIOD2 = 0x03BF03C0`, is
  **degenerate**: 959 vs 960 reads as 25 kHz at ~100% duty under *either* field
  order, so it cannot discriminate between the layouts.
- **"Stock uses PWM channel 5."** Overstated, then withdrawn — **and then
  confirmed on hardware 2026-08-06**: `pwm5 request for fastlogo fail!`. The
  original claim was right and the withdrawal was wrong. The withdrawal rested
  on the shipping DTB's `panel_pwm_ch=2` being "stronger evidence", but the DTB
  is not what the fastlogo path reads; `panel_config.ini` is. This question
  flipped three times across two sessions, and only running the code settled
  it. **Static evidence about which of two config sources wins is not evidence
  at all — only the runtime knows.**
- **"PWM2/PB4 verifiably does not dim this panel" (commit `ec1d759`).** The
  observation was real but the conclusion was not earned — at the time PB4 was
  muxed to 2 instead of 3, so the waveform never reached the pad. The result
  only became meaningful after the mux fix.
- **"`0x8b253570` is never written, so the backlight service is NULL."** Static
  scan found only loads; a runtime read showed a live pointer. A static write
  map is a lower bound, never an inventory.

**The recurring methodological failure:** a read-back checked against the same
source that produced the value cannot detect an error in that source. `PB4
mux=2` was printed, read and approved three separate times before anyone
compared it against the vendor's own pin table.

---

## 5. What would actually settle it

**All four items are now moot** — kept only to show what the question looked
like before it was answered, and how far off the shortlist the answer sat. None
of these four is what settled it; a three-second GPIO toggle did. Section 7 has
the work that actually remains.

In rough order of cost.

1. ~~**Trace the light's two wires to their other end.** If they reach a
   separate driver PCB, that board's control input is the real dimming path. If
   they reach the PSU directly, brightness is not electronically controllable
   and this thread is over.~~ **Obsolete** — both branches were wrong. The
   driver is neither on a separate PCB nor absent: it is on this mainboard, and
   the light dims.
2. ~~**DMM on PB4, DC mode, during `bl-sweep`.**~~ **Obsolete for this
   question.** Whether PB4's waveform reaches its pad no longer matters, because
   the pad reaches nothing. Still worth ten minutes *if* the inline dimmer of
   section 7 is fitted, since that design depends on PB4 driving a module input.
3. **Trace `pwm_channel` into the backlight-create call in stock U-Boot**
   (`u-boot.fex`, Thumb, base `0x4a000000`, create call at `0x4a0255a0`,
   selector at `0x4a0239e0`). Settles inference #1. *Static, no hardware.*
4. ~~**Boot stock and read its U-Boot console**~~ — **DONE 2026-08-06, see
   section 0.** The blocker was real but misdiagnosed: the vendor's boot package
   had been destroyed by this project's own 32-bit smoke-test FIT, flashed to
   raw LBA `0x4000` during early bring-up, which sat on top of both package
   copies and the `sdmmc_arg` timing region. Restored from the 2026-07-05
   capture (`docs/flash.md` Method 5), after which the vendor stack boots
   end to end.

---

## 6. Artifacts and where they are

| what | where |
| --- | --- |
| bench command | `h713_disp panel-test 0x33 bl-sweep` — 6 steps, 100/75/50/25/0/100, white field, prints `CNT` twice per step and warns if static |
| our implementation | `external/u-boot/arch/arm/mach-sunxi/h713_mips.c`, `h713_disp_backlight_set()` |
| board photographs | `local/board_images/` (53) |
| retail OTA firmware | `~/Documents/projector_firmware/H713 Magcubic projector.20250922.093247/update.img` |
| extracted stock boot parts | `local/stock-boot/` (`boot0_sdcard.fex`, `u-boot.fex`, `boot_package.fex`, `sunxi.fex`, `env.fex`) |
| stock U-Boot (identical copy) | `local/mips-display/board-b-stock/u-boot-stock.bin` — sha256 matches `u-boot.fex` |
| MIPS firmware | `local/mips-display/board-b-mips/display.bin` (MIPS32LE, VA `0x8b100000` = file offset 0 = ARM `0x4b100000`) |
| chronological detail | `docs/mips-display-recovery.md`, top sections |

**Warnings for anyone continuing.** There is **no eMMC backup on this machine**
(`docs/flash.md` claimed one; it does not exist). `mmc dev 1;` must be on the
same line as any `mmc read`/`write`, because a failed read leaves plausible
looking stale DRAM and this has corrupted three results including a "backup".
`backup_8020.bin` currently on `mmc 1:2` is 1.2 MB of uninitialised DRAM — not a
backup. And never drive PB5 low.

---

## 7. The chosen path (deferred 2026-08-06, hardware not yet fitted)

Dimming via PWM-of-enable on PB5 **works but will not be used**: it dims by
starving the boost converter, so the LED runs below its designed forward
voltage, the usable window is a narrow 7–14 % duty that will drift with
temperature and input rail, and — decisively — PB5 also powers the fan, so the
whole usable band starves cooling. `h713_disp bl-gpio` stays as a diagnostic,
not an implementation.

**The plan is an inline low-side MOSFET module in the LED's negative return**,
chopping the current downstream of the converter's output capacitor. The
converter then runs undisturbed at a steady 52.6 V, PB5 stays statically high,
and the fan is unaffected. That is the isolation the enable-PWM approach cannot
give.

Module on hand: dual parallel MOSFETs, DC 4–60 V, 10 A / 600 W, trigger input
3.0–24 V high-level or 0–0.6 V low-level. Comfortably over-specced for ~1 A at
52.6 V, and 3.3 V drives it directly with no level shifter.

**Constraints to honour when it is fitted:**

- **Its PWM input is rated 0–2.5 kHz.** `H713_BL_PWM_HZ` is 25 kHz and DT patch
  0032 uses `pwms = <&pwm 2 40000 0>` (40000 ns). Both must drop to ≤ 2.5 kHz —
  1 kHz gives 2.5x margin and stays above flicker fusion. Driving the module's
  gate stage at 25 kHz would hold its FETs in the linear region for much of
  each cycle. Left at 25 kHz for now so the constant keeps matching the
  measurement documenting it (counter wraps at 960).
- **Establish whether the converter is CV or CC first**, by measuring the `LED`
  header with the light unplugged. Still ~52.6 V means constant-voltage and
  chopping the load is straightforward. Climbing or hiccuping means constant
  current with the LED in the feedback path — and at ≤ 2.5 kHz the off-time is
  long enough for that loop to respond. The output capacitor then charges while
  the LED is disconnected (`dV = I·t/C`: at 0.7 A and 500 µs, a 10 µF cap rises
  ~35 V, a 100 µF cap ~3.5 V), and reconnecting drives an inrush through the
  LED. Watch the header voltage while chopping before trusting it.
- **Check polarity on first light.** `panel_config.ini` says
  `pwm_polarity = 1` (active low) while our DT uses normal. If 100 % duty gives
  darkness, invert: `pwms = <&pwm 2 <period> 1>`. The module supports both
  trigger senses, so either side can be the fix.

**Everything else already exists.** `h713_disp panel-test 0x33 bl-sweep` and
patch 0032's `pwm-backlight` (`/sys/class/backlight/backlight/brightness`,
0..100) both drive PWM2/PB4 with a waveform verified correct on the pin. The
only thing ever missing was hardware between that pin and the light.
