# Roadmap

Where the project goes after the foundation (open boot chain + Debian 6.18.38 +
standalone boot, all hardware-verified on the bench). Ordered by dependency, not
just priority. See [status.md](status.md) for what already works.

## Guiding constraints

- **Bench (`HY200_QZ713DF_A1`, DDR3) is the safe dev board.** The projector
  (`HY200_QZ713_V2`, LPDDR3) lives inside a projector and is untested — bring it
  up carefully, FEL-first, brick-avoidance paramount.
- **The kernel is a patch series, and that's its home by design.**
  `patches/kernel/` applied to a pinned mainline tarball is deliberate (the tree
  is too big to fork, and this keeps our delta reviewable + rebasable). Driver
  work = edit the series + `build/build.sh kernel`. No "kernel fork" is needed;
  what *is* worth adding is a hackable persistent tree for iteration (Phase 1).
- **UART is the recovery anchor.** It is now the reliable U-Boot default, while
  ACM is an explicit faster mode. Networking/SSH still removes the throughput
  bottleneck for Linux-side iteration.

## Phase 1 — Build & OS polish (bench, near-term)

- **Rootfs workflow — complete and hardware-verified.** The rootless
  `tools/rootfs/build.sh` verifies signed Debian metadata, requires an SSH key,
  disables password SSH, installs all 24 Linux 6.18.38 modules, builds
  raw+sparse ext4 images, and validates growfs plus filesystem integrity. On
  the bench it boots repeatedly with a 4.5 GiB root filesystem, serial
  autologin, stable per-device identity, Cedrus/Panfrost modules, and active
  public-key-only sshd. A remote SSH login remains gated on networking.
- **Boot cleanup — complete and hardware-verified:** removed the CCU
  `MIPS_DIAG` residue, enabled autofs, modeled the Mali supply, installed clean
  U-Boot `g8a601c1`, and verified UART, ACM, fastboot, and normal Debian boot.
- **Dev workflow**: a persistent, hackable kernel worktree (separate from the
  ephemeral `build/linux-*`) + a fast "rebuild module → load on target" path.
- **Reboot → fastboot / U-Boot — done, both modes HW-validated (2026-07-23).**
  `RTC_DRV_SUN6I` is enabled (real RTC driver, the
  previously-orphaned osc32k/iosc clocks, GP registers as nvmem), and reboot-mode
  moved off the overlapping `syscon-reboot-mode` onto **`nvmem-reboot-mode`** over
  a fixed nvmem cell (`reboot-mode-magic@1c`) under the rtc node — no `sun6i-rtc`
  patch needed (`add_legacy_fixed_of_cells` makes the DT cell
  phandle-referenceable). The nvmem→GP7→`preboot`→fastboot chain was proven
  console-free on the bench. A follow-on split gives the two reboot verbs
  distinct meanings: `reboot fastboot` (`0xfa57b007`) → fastboot;
  `reboot bootloader` (`0xb007c0de`) → `preboot` runs `setenv bootdelay -1` →
  U-Boot prompt. DTS carries both modes; the U-Boot side is the runtime `preboot`
  env. Both verbs were confirmed console-free on the bench. Minor loose end: RTC
  timekeeping (set/read) unexercised on the minimal rootfs (no `hwclock`).
- **WiFi SDIO stability — fixed for load; bench-validated (no regression).**
  The AIC8800 `mmc1` link wedged under sustained load: `FIFO_RUN_ERROR` on CMD53
  that the phase-rotation retry can't recover (phase fixes CRC, not underruns) →
  CMD53 timeout → `aic8800_fdrv` `cmdqueue drain timeout` leaks an atomic context
  → `scheduling while atomic`. Patch 0006 now **classifies the CMD53 error**: FIFO
  underruns (`FIFO_RUN_ERROR`/`HARD_WARE_LOCKED`) get FIFO/DMA-reset recovery with
  a short AHB back-off and *no* phase rotation (which would only knock a good link
  off its stock sampling phase); CRC/timing errors keep the phase-rotation path.
  Independent retry budgets (7 phase / 15 FIFO) keep a burst of load-induced
  underruns from exhausting the CRC budget and surfacing as a hard `-ETIMEDOUT`.
  **Bench (2026-07-22):** 384 MB of sustained WiFi transfer completed with zero
  SDIO errors and no wedge (previously ~12 MB wedged it); the old failure is gone.
  The FIFO recovery path itself was **not provoked** — the SDIO data path never
  underran this session (the marginal weak-RF placement that produced the original
  `FIFO_RUN_ERROR` didn't reproduce), so it stands as defense-in-depth; to observe
  it firing, retest from the −71…−80 dBm spot. DVFS was ruled out (wedged even
  pinned at 1416 MHz).
  **Superseded 2026-08-18/21 — the link is now done.** Patch 0046 fixed the real
  bulk-RX defect (the v5p3x IDMA descriptor encoding for an exact 4096-byte
  segment), and 0048 fixed a 4x clock-accounting error that had every rate
  meaning four times its label. The link runs stock four-bit UHS-SDR104 at a
  register-verified 50 MHz, passing 128 MiB both directions with SHA-256 exact
  and zero faults, in AP and STA mode alike. The 384 MB bench above was a
  scp-*pull* — the working direction — which is why it looked healthy while
  inbound transfer was broken.
- **AIC8800 firmware-command crash — detected, and since 2026-08-21 recovered
  automatically.** Under *pathological* CPU/bus starvation (perf-pinned +
  memcpy/eMMC contention), the vendor driver's firmware command→confirm handshake
  times out (`cmd timed-out` → `wlan error reset flow`, `rwnx_cmds.c`), marking the
  cmd queue `CRASHED` and firing a `DHDISDOWN=1` uevent → WiFi/BT stay down (kernel
  survives; no atomic wedge). Distinct from the sunxi-mmc FIFO bug (no CMD53 error
  occurs). **Auto-recovery was attempted and abandoned as unsafe:** an
  unbind+reload of the SDIO stack races the mmc/driver core into a NULL-deref Oops
  (`__device_attach_driver` via `mmc_rescan`), and a graceful reboot fallback hung
  on BT teardown — bench-observed, board needed a power-cycle. The chip only comes
  back cleanly on a full boot. So the rootfs *shipped* a **log-only notifier**
  (`h713-wifi-crashlog`, udev on `DHDISDOWN=1` → journal + console line) and the
  operator rebooted. Only reproduces under unrealistic load.
  **Resolved 2026-08-21 — recovery now happens automatically.** The "no safe
  in-place recovery" finding stands and should not be retried; what was broken
  was the *fallback*, and that is fixed. `h713-wifi-recover` reboots on
  `DHDISDOWN` (policy in `/etc/default/h713-wifi-recovery`), the
  `TimeoutStopSec` follow-up noted here is done (10 s), and — the piece the 2026-07-23
  attempt lacked — `RebootWatchdogSec=16s` arms the sunxi hardware watchdog
  across the shutdown, so a stuck unit costs a SoC reset instead of a trip to the
  board. Recovery takes ~30 s. **Caveat: verified with a synthetic trigger
  only** — the real crash would not reproduce under 4 minutes of the documented
  starvation recipe, so recovery under the actual fault is still unproven.

## Phase 2 — Bench subsystem bring-up

On the bench board. Most items are SoC-general and mutually independent; the
**display path** is the exception and the linchpin — the whole *visible* stack
(GPU-on-screen, a compositor, even confirming the backlight brightness fix) hangs
off it. Because the bench board is itself a projector variant with the panel
attached, the display path can be brought up here, not only on the projector
(Phase 3/4). Ordered by dependency, not just priority.

1. **Networking (WiFi + BT) — DONE 2026-08-21.** AIC8800D80 combo: WiFi on SDIO
   (`mmc1`), BT on UART1 (`ttyS1`, H4, 1.5 Mbaud, no flow control — confirmed
   against the vendor Android binaries). WiFi runs stock four-bit UHS-SDR104 at a
   verified 50 MHz with 128 MiB clean both directions in AP and STA mode, under a
   real `US`/FCC regulatory domain, with automatic recovery from a firmware crash.
   BT attaches with no HCI timeouts. It did unlock SSH and end the UART pain, as
   predicted. Remaining gaps are evidence rather than code: crash recovery is
   untested against a real crash, and coverage is one client at close range on one
   board. See [status.md](status.md) and
   [handoff-wifi-sdio-2026-08-17.md](handoff-wifi-sdio-2026-08-17.md).
2. **Thermal / cpufreq / DVFS — done; safety + real performance.**
   - **Bench cooling fan (0030) — DONE.** The fan is a 3-wire (VCC/GND/tach)
     on/off part, not PWM-speed-controlled (DMM: tach at its 3.3 V pull-up, +V
     floating/unpowered). It stayed dead because the PB5 backlight/fan
     power-enable hog was malformed (`<37>` on a 3-cell sunxi controller →
     skipped). 0030 fixes the hog to `<1 5>`; the earlier `pwm-fan`-on-PWM0 model
     was dropped once PH17 proved to be the tach line, not a control output
     (main-PWM output itself *was* validated in the process). **Bench-confirmed:
     the fan spins.** Both the fan and the LED backlight now come up **at
     power-on from U-Boot** (`board_init` drives the shared PB5 enable under
     `CONFIG_H713_POWERON_LIGHT_FAN`, bench-only), so the panel is lit and cooled
     from reset like a monitor showing the boot process; PB5 being the shared
     enable makes the fan a hard interlock for the light.
   - **Backlight brightness** is a display-path task, not a thermal one — tracked
     under item 3.
3. **Display path (LVDS panel + MIPS pipeline) — DONE 2026-08-07; backlight
   understood, dimmer hardware pending.** The projector's LVDS panel renders
   correctly through the MIPS coprocessor path from U-Boot, and the frame
   survives the handoff into Linux. Vendor and custom boot logos display
   (`h713_disp auto <id> logo [file.bmp]`), double-buffered animation is
   tear-free, and teardown cleans up on failure. This was the linchpin for
   every *visible* thing, and it is no longer blocking.
   - **Backlight.** The refuted PB4/serial-init theory in earlier revisions
     of this item was wrong. The light is an on-board 36→52.6 V boost whose
     PB5 enable dims on PWM (`h713_disp bl-gpio`), but that starves the
     shared fan; the shipped software never dims at all. The chosen fix is an
     inline low-side MOSFET on the LED return driven from PB4/PWM2, hardware
     not yet fitted. Full case in [backlight-investigation.md](backlight-investigation.md).
   - **A MIPS-side register shell is confirmed reachable** for DECD, via a
     memory-mapped debug terminal — see the display docs.
   - Detail: [claude-display-handoff.md](claude-display-handoff.md),
     [mips-display-recovery.md](mips-display-recovery.md).
4. **GPU (Mali-G31 / Panfrost).** Driver is mainline and binds now; Panfrost can
   render offscreen/headless (EGL/GBM, PRIME buffer sharing) for validation, but
   anything *visible* is gated on the display path (item 3), so it is downstream
   of that work, not a standalone bench item.
5. **Video decode (Cedrus / VE3) — DONE 2026-08-15. Zero-copy playback at
   59.71 fps, vsync-limited, no tearing.** VE decodes into a CMA buffer,
   GStreamer hands over its dma-buf FD, the Mali-G31 samples it as an NV12
   EGLImage and renders into the scanout carveout, AFBD scans it out. The CPU
   never touches a pixel. Getting there needed a fix to the H713 PPU driver
   (its register base was a transposition landing in R_CCU, so no power domain
   could be sequenced and the GPU could not run jobs) and a new dma-buf
   exporter for the `no-map` scanout carveout (patch 0036).

   **Retracted along the way:** "direct YUV scanout via the vendor's
   plane-address path" did not reproduce — those registers are not in the
   scanout fetch path — and the "28 fps cross-process handoff ceiling" was
   really the ~44 MB/s uncached read of the decoder's output buffer.

   **Read the HANDOFF section at the top of
   [video-decode.md](video-decode.md)**, which also carries the loose ends to
   tidy before starting audio. Earlier framing follows.

   **Superseded detail (2026-08-09):** Mainline `cedrus` decodes H.264 on the H713 **bit-exact**
   against host software references — Constrained Baseline, Main (B-frames +
   CABAC) and High (8x8 transform), 320x240 through 1920x1080 — with **no driver
   changes**. The blocker was a single device-tree property: `iommus` on the `ve`
   node named an IOMMU that does not exist at `0x030f0000` (the H6 address; the
   stock DTB puts it at `0x2010000` with a different binding and 2 cells), so the
   VE was handed untranslated IOVAs, corrupted kernel memory and panicked before
   emitting a frame. Removing it fixed the crash and the decode together.
   Remaining: get frames onto the panel (reuse the proven AFBD scanout +
   `0x05600178` flip), then sustained playback. Full account in
   [video-decode.md](video-decode.md). Original framing follows.

   Genuinely
   headless-testable (patch 0022 in series), and independent of the display path
   for *decoding*, but the display path (now done) gives it what it needs to be
   *seen* and debugged: a tear-free double-buffered scanout to present frames, a
   proven frame→Linux handoff, the AFBD flip lever (`0x05600178`), and a
   confirmed MIPS-side register shell. The shared fact is the address window:
   MIPS-side buffers convert to the ARM side by kseg0/1 physical `+0x40000000`.
   See "Starting point for video decode" in
   [claude-display-handoff.md](claude-display-handoff.md).
6. **Audio (I2S / codec / HDMI-in audio off the HDMI-RX) — NEXT.** Starting
   position gathered 2026-08-15, not yet acted on. The stock DTB
   (`local/stock-boot/sunxi.fex`, and it is the authority — see the PPU lesson)
   carries `codec@2030000` compatible `allwinner,sunxi-internal-codec` with
   `pll_audio`/`pll_tvfe`/`codec_dac`/`codec_adc`/`codec_bus` clocks,
   `sndcodec@2030330` compatible `allwinner,sunxi-codec-machine`, `daudio2`
   pins on function `d_i2s2`, a `vs,trid-audio-bridge`, and a
   `sunxi,simple-audio-card`. Vendor driver sources exist in
   `local/allwinner-h713-linux/drivers/audio/`
   (`snd-soc-sunxi-h713-{codec,cpudai,machine}.c`) — unverified RE like the rest
   of that tree, but they name registers. **First question is what is actually
   populated**: it is a projector with speakers, so a codec and amp should be
   there, but that is an assumption until someone looks at the board or gets a
   sound out of it.
7. **IR receiver (sunxi-cir)** — patch 0021; needs the receiver populated.
8. **Crypto (sun8i-ce) + RNG — CLOSED: investigated to a definitive dead end;
   disabled.** Mainline `sun8i-ce` cannot drive the H713 CE, bench-proven step by
   step: the A53s already have ARMv8 AES/SHA (software crypto ~2 GB/s, faster than
   this CE, so no performance case); enabling the CE registers every algorithm
   then fails each self-test; wiring the stock's second interrupt (SPI 74) fixes
   task completion, but the CE then rejects mainline's task descriptors (`address
   invalid` for ciphers, `algorithm not supported` for standard AES/SHA) — a
   different descriptor **format** (the vendor two-bank block), not an
   IRQ/clock/addressing gap. No CE TRNG. Reopening means descriptor-level RE of
   the vendor `allwinner,sunxi-ce` driver (source unavailable) for no gain — left
   disabled; software crypto is fast and correct.

## Phase 3 — Projector board bring-up (`HY200_QZ713_V2`, LPDDR3)

- Build U-Boot with `hy200_qz713_v2_defconfig` — the **LPDDR3 params are
  replay-verified only, never run on hardware**.
- **FEL-boot first**, verify DRAM + console, *before* writing anything to its
  eMMC. Confirm the recovery vector exists on this board.
- Audit the existing projector DTS against the physical board, enable its
  vendor-only drivers in a separate config, and port `cpu-comm` away from its
  inherited 32-bit virtual-pointer ABI before enabling it on arm64. Then
  validate boot to Debian (rootfs auto-grows).

## Phase 4 — Projector-specific subsystems (needs Phase 3)

- **Display path (LCD panel + backlight + MIPS pipeline)** — the *same* hardware
  as the bench board, so bring-up starts in Phase 2 (item 3), not here. Phase 4's
  only display job is re-validating that path on the LPDDR3 projector board once
  Phase 3 boots.
- **Keystone motor** (GPIO stepper, patch 0009).
- **Fans + NTC** (board-mgr, patch 0008).

## Phase 5 — Upstreaming (long-term)

Clean the H713 driver series (CCU, pinctrl, PPU, LRADC, USB-PHY, MMC, …) + DT
bindings for mainline submission; upstream the board DTS once stable. The forks
were curated with this in mind (see [../PROVENANCE.md](../PROVENANCE.md)).

**Watch the AIC8800 FullMAC RFC.** AIC Semiconductor has posted an SDIO FullMAC
WiFi driver to `wireless-next` covering AIC8801/8800DC/**8800D80** — our chip on
our bus (<https://lwn.net/Articles/1084468/>, RFC v2, 2026-07-23). If it lands it
replaces the out-of-tree vendor driver that `patches/aic8800/` patches. Our SDIO
*host* work (0046, 0048) is in `sunxi-mmc` and the H713 CCU and survives it
either way; the `aic8800-0006` regulatory patch would be obsoleted, though the
RFC lists the regulatory database as follow-up work so it is unsolved there too.
It does nothing for Bluetooth — its `aic_btsdio` is BT over SDIO and this board
is BT over UART. Not worth planning against yet: RFC v2, unmerged, and firmware
redistribution permission is not granted, which blocks it independently of
review. Detail under future work in
[handoff-wifi-sdio-2026-08-17.md](handoff-wifi-sdio-2026-08-17.md).

## Open questions — verify before committing effort

- **Board population**: what's actually fitted on each board — HDMI, audio codec,
  IR receiver, fans, panel connector? The **WiFi/BT part is answered**: an
  AIC8800D80 combo, WiFi on SDIO (`mmc1` @ `0x04021000`, PG0–PG5, power via PM1
  `wlan_regon` on R_PIO) and BT on UART1 (`ttyS1`, H4, 1.5 Mbaud, no flow
  control). Both are working — see [status.md](status.md).
- **Projector safety**: can `HY200_QZ713_V2` be FEL-recovered (button / BROM
  fallback) if a flash goes wrong?
- **Display output on the bench — RESOLVED.** The only display *output* is the
  projector's LVDS/LCD panel; the HDMI connector is an HDMI-RX **input** (DW-HDMI-RX,
  no HDMI-TX on this SoC, no output/encoder node in the stock DTB), so it cannot
  be a monitor output. Consequence: all *visible* GPU/display bring-up is gated on
  the LVDS panel + MIPS display path (Phase 3/4) — there is no HDMI-monitor
  shortcut. Panfrost/Cedrus stay headless-testable meanwhile.
- **Status-LED source — RESOLVED (hardware rail indicator; bench-probed
  2026-07-23).** The power LED goes red → blue at main power-on and it is **not**
  software-driven. Probed live at the U-Boot prompt (via `reboot bootloader`):
  blue is already lit pre-Linux, so it is no Linux consumer. U-Boot configures
  only PL6 (the vdd-cpu/sys enable from `standby_param`) and leaves PL0/PL1
  **disabled** (`R_PIO CFG0 @0x07022000 = 0xf1ffffff`). Muxing PL1 (blue) then
  PL0 (red) as outputs and driving each high *and* low (`mw.l 0x07022010` /
  `0x07022000`) moved neither LED. So the status LED is a bi-colour power
  indicator wired to the rails (red = standby rail, blue = main rails up); it
  flips at the same instant PB5 enables the lamp/fan — hence the apparent PB5
  correlation, but there is no shared line and no GPIO involved. The vendor
  `led0/led1 = PL0/PL1` + `standby_param` mapping is not honoured at runtime on
  this revision (ARISC-only during real standby entry, or a different board rev).
