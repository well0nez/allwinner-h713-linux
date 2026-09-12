# Status

What works on the H713 mainline stack, and what's next. All hardware results are
on the **HY200 bench board (DDR3)** unless noted — the HY200 QZ713_V2 projector (LPDDR3)
is not risked for bring-up.

_Last updated: 2026-08-21._

## Summary

A fully open boot chain — U-Boot SPL → TF-A BL31 → U-Boot → Linux **6.18.38
LTS** — boots a **64-bit Debian 13** userland from eMMC to a **root login**, on
all four cores, with HS400 eMMC. It boots **standalone** (power-on → Debian, no
host), replacing the vendor Android stack end to end. All hardware-verified on
the HY200 bench board.

**Display bring-up is complete (2026-08-07).** The 1280×720 LVDS panel renders
correctly through the MIPS coprocessor path: the vendor boot logo and a custom
logo both display, double-buffered animation is tear-free, the frame survives
the handoff into Linux, teardown cleans up on failure, and a boot logo can be
published from U-Boot (`h713_disp auto <id> logo [file.bmp]`). Backlight dimming
is understood (PB5 enable-PWM of an on-board 36→52.6 V boost; the shipped path
never dims) and the fix is an inline MOSFET, hardware not yet fitted. The
firmware's MIPS-side debug shell is confirmed reachable for register access.
Full detail in [claude-display-handoff.md](claude-display-handoff.md) and
[mips-display-recovery.md](mips-display-recovery.md).

**Hardware H.264 decode works (2026-08-09).** Mainline `cedrus` drives the H713
VE with no driver changes: Constrained Baseline, Main (B-frames + CABAC) and High
(8x8 transform) all decode **bit-exact** against host software references, 320x240
through 1920x1080. The whole failure was one device-tree property — `iommus` on
the `ve` node pointed at an IOMMU that does not exist at that address, so the DMA
layer handed the VE untranslated IOVAs; it corrupted the kernel's printk
ringbuffer and panicked before emitting a frame. Removing it fixed both symptoms
at once. **Next: getting decoded frames onto the panel.** See
[video-decode.md](video-decode.md).

**WiFi and Bluetooth are done (2026-08-21).** The AIC8800D80 SDIO link runs at
the stock configuration — four-bit UHS-SDR104 at a **verified** 50 MHz — after
patch 0048 removed two compensating errors that had been driving the bus at 4x
its nominal rate. 128 MiB transfers pass in both directions with SHA-256 exact
and zero SDIO faults, in **both AP and STA mode**; the long-standing "WiFi cannot
carry a file" rule is refuted. The hotspot was silently emitting 802.11g, capping
throughput at a tenth of the bus; with HT enabled it does 5.1–7.7 MB/s on
2.4 GHz HT40 (13.2/14.4 on 5 GHz VHT80, one line away). The radio now runs under
a real regulatory domain instead of a permissive world default, a firmware crash
recovers itself rather than waiting for a human, and Bluetooth attaches cleanly
with no HCI timeouts. Full detail in
[handoff-wifi-sdio-2026-08-17.md](handoff-wifi-sdio-2026-08-17.md).

## Boot chain

```
BROM → U-Boot SPL (DRAM init) → TF-A BL31 (EL3, @0x40000000)
     → U-Boot proper (AArch64 EL2) → FIT (bootm):
         arch=arm64 → EL1 AArch64  — native, 4-core SMP     ✅
         arch=arm   → EL1 AArch32  — via el2_to_aarch32      ✅ (single-core)
```

## Works

| Area | State |
|------|-------|
| DRAM init | ✅ DDR3 (HY200) hardware-proven; LPDDR3 (HY200 QZ713_V2) replay-verified, untested on HW |
| U-Boot proper | ✅ clean `g8a601c1` installed at LBA 16; correct HY200 model, persistent env (raw eMMC @4 MiB), `reset` via PSCI + `wdt` |
| BL31 / PSCI | ✅ `SYSTEM_RESET`, `CPU_ON` (all 4 cores), `CPU_SUSPEND` |
| arm64 Linux | ✅ **mainline 6.18.38 LTS** boots to Debian root login, **4-core SMP** (HW-verified) |
| 32-bit Linux | ✅ boots to userspace, **single-core** (see limitations) |
| eMMC | ✅ HS400, 26-partition Android GPT, read+write verified across reboots |
| Debian 13 rootfs | ✅ signed, key-only image boots from UDISK; growfs, serial autologin, persistent first-boot identity, modules, and sshd HW-verified. Since 2026-08-15 the base set also carries the **video runtime** (mesa/GLES, the GStreamer stack incl. `v4l2slh264dec`, `v4l-utils`, `mpv`) and autoloads `sunxi_scanout_dmabuf`, with `--profile dev` for an on-target compiler — built and compile-verified under qemu, not yet booted on hardware |
| Standalone boot | ✅ power-on/reset → `boot_a` FIT → Debian, **no host attached** (HW-verified) |
| USB gadget | ✅ serial-default console; opt-in CDC ACM, UMS, and fastboot modes; ACM→fastboot transition and bounded raw bootloader target HW-verified |
| CPU frequency/thermal | ✅ PWM DVFS from 480 MHz/0.90 V through 1416 MHz/1.10 V; full-range transitions and peak load HW-verified; cpufreq cooling device backs 75/85 C passive trips |
| Crypto Engine + RNG | ⚠️ **disabled — mainline `sun8i-ce` can't drive the H713 CE** (bench-proven). Enabling it registers every algorithm, then each fails its known-answer self-test. Wiring the stock's 2nd interrupt fixes task completion, but the CE then rejects mainline's descriptors — ciphers `address invalid`, AES/SHA `algorithm not supported` — a different descriptor **format** (vendor two-bank block), not an IRQ/clock/addressing gap. No CE TRNG. The A53's ARMv8 AES/SHA (software ~2 GB/s) is faster anyway. Re-enabling needs descriptor-level RE of the vendor `sunxi-ce` (no source). |
| Reboot → fastboot / U-Boot | ✅ **done, both modes HW-validated (2026-07-23).** Two `nvmem-reboot-mode` modes over RTC GP7: `reboot fastboot` (magic `0xfa57b007`) → U-Boot `preboot` → fastboot, and `reboot bootloader` (magic `0xb007c0de`) → `preboot` sets `bootdelay -1` → U-Boot `=>` prompt — both confirmed console-free on the bench. `RTC_DRV_SUN6I` owns the region and exposes GP7 as an nvmem cell (`nvmem-cells` → `reboot-mode-magic@1c`); the old overlapping `syscon-reboot-mode` is gone. |
| KMS / `/dev/dri/card1` | ✅ **DONE 2026-08-16, HW-verified — `mpv --vo=drm` plays 720p to the panel, 0 dropped frames; 1320 page flips at 59.71 fps, 0 timeouts.** `sun50i-h713-afbd` (patches 0037/0038) is a simple-KMS driver over the AFBD scanout engine: one CRTC, one plane, page flip via the same `0x05600178` + `READY` sequence that measured 0.00% tearing in gles-play, vblank off SPI 110 (bits confirmed by 2254 IRQs and zero stalled flips). Probe reads geometry back from the hardware (`adopting 1280x720, stride 5120`). Framebuffers come from **system CMA** — a reserved dma-pool allocates in power-of-two page orders, so a 16 MiB pool yielded exactly 4 buffers and mpv ran out of them. **card1, not card0** — panfrost holds minor 0 as render-only. It **adopts** the display U-Boot brought up and never touches timing, the LVDS PHY or `rst_bus_disp`, so it does not remove the U-Boot dependency. Took the AFBD window and IRQ from DECD, now `disabled`. Operator-confirmed: a Linux login prompt on the projector. [kms-display.md](kms-display.md) |
| Video on the panel | ✅ **DONE 2026-08-15 — zero-copy playback at 59.71 fps.** Decoded H.264 reaches the panel through the GPU with the CPU never touching a pixel: VE decodes into a CMA buffer, GStreamer hands over its dma-buf FD, the Mali-G31 samples it as an NV12 EGLImage and renders into the scanout carveout (exported by `sunxi-scanout-dmabuf`, patch 0036), and AFBD scans that out. Sustained 2700 frames, 0 timeouts, operator-confirmed moving picture, **no tearing** (0.00% vs a 16.94% positive control). Vsync-limited at 58.93 fps. **RETRACTED:** the previously reported "direct YUV scanout via the vendor plane-address path" did NOT reproduce — those registers are not in the scanout fetch path at all. The CPU-conversion path also works and is capped at 28.30 fps by the ~44 MB/s uncached read of the decoder's buffer. Full state at the top of [video-decode.md](video-decode.md) |
| Video decode (Cedrus / VE) | ✅ **H.264 hardware decode, bit-exact** (2026-08-09). Mainline `cedrus`, unmodified, via GStreamer `v4l2slh264dec`. All five ladder vectors match their host software references byte-for-byte: 320x240 Constrained Baseline, 1280x720 Baseline/Main/High, 1920x1080 High. Force `video/x-raw,format=NV12` — unforced it negotiates `NV12_32L32` (32x32 tiled), which is correct output but will not match a linear reference. **The `iommus` property must stay off the `ve` node** until the real IOMMU (stock DTB: `0x2010000`, `allwinner,sunxi-iommu`, `#iommu-cells = <2>`) is verified live; ours pointed at the H6 address `0x030f0000`, which reads all zeros. Re-verified bit-exact on the current kernel 2026-08-15. On the panel via the GPU path — see the row above. |
| WiFi (AIC8800D80 / SDIO) | ✅ **DONE 2026-08-21.** Four-bit UHS-SDR104 at a register-verified 50 MHz — stock parity. 8 MiB and 128 MiB both directions, SHA-256 exact, **zero** cmd53/CRC/FIFO/hardware-lock/timeout messages, on a production kernel from a cold boot, autobooting unattended from eMMC. Three defects were fixed to get here: the v5p3x IDMA descriptor encoding for an exact 4096-byte segment (0046, the bulk-RX failure); a 4x clock-accounting error — the driver doubled the module clock *and* the CCU carried a fictional /2 post-divider, so `max-frequency` meant a quarter of the real rate (0048); and an AP emitting plain 802.11g, which capped transfers at 1.33/2.37 MB/s against a 24.4 MB/s bus. With HT: **5.1–7.7 MB/s** (2.4 GHz HT40, the shipped default for client compatibility) or **13.2/14.4 MB/s** (5 GHz VHT80, `HOTSPOT_BAND=5`). Running both bands at once works but is *slower* than either alone — 1x1 radio, time-sliced. STA mode retested and equally good (8.9/9.6 MB/s). |
| WiFi regulatory | ✅ **DONE 2026-08-21.** The wiphy is self-managed, so cfg80211's `regulatory.db` never applied to it — the driver installed its own domain from a compiled-in `"00"`, i.e. `DFS-UNSET`, 2380–2520 and 5140–5980 MHz at 20 dBm with no DFS or passive-scan constraint. The driver's own table is fine (185 countries, 98 distinct rule sets); only the selector was stuck. `aic8800-0006` exposes it; the rootfs sets `WIFI_REGDOMAIN` (default `US`) and the radio now reports `country US: DFS-FCC`. ⚠️ The driver still prints `CAUTION: USING PERMISSIVE CUSTOM REGULATORY RULES` afterwards — that line is on the *success* branch, so judge with `iw reg get`, not the log. |
| WiFi crash recovery | ✅ **DONE 2026-08-21.** There is still no safe in-place recovery (unbind/reload Oopses the mmc core), so the recovery *is* the reboot — the job was making it reliable. `h713-wifi-recover` reboots on `DHDISDOWN` (policy in `/etc/default/h713-wifi-recovery`), `h713-bt-attach` gets a 10 s stop timeout so a dead chip cannot stall shutdown, and `RebootWatchdogSec=16s` arms the sunxi watchdog across the transition. Board returns in ~30 s. ⚠️ Verified with a synthetic trigger only — the real firmware crash would not reproduce under 4 minutes of the documented starvation recipe. |
| Bluetooth (AIC8800 / UART) | ✅ **DONE 2026-08-21.** `hci0` UP RUNNING, HCI 5.4, BR/EDR + LE, scanning discovers real devices. The `opcode 0x1003 tx timeout` on every cold boot is gone: it was never a timing race (a 5 s settle moved it without removing it) and never a baud race (115200 fails outright — the chip is at 1.5 Mbaud from power-on, contradicting the RE port notes). The first `N_HCI` attach after power-on leaves the controller unable to answer the first HCI command, so `h713-bt-attach` now drains `ttyS1` and primes with a throwaway attach/detach. 0 timeouts, up on attempt 1, 3 cold boots of 3; MGMT at ~9.0 s instead of ~13.9 s. Baud and flow-control settings confirmed against the vendor Android binaries. |
| Peripherals (drivers probe) | pinctrl, PWM, PPU (5 power domains), both MMC, EHCI/OHCI ×3, LRADC, IR, board-mgr, watchdog, **RTC** (`sun6i-rtc`, enabled — the canonical osc32k/iosc clock provider and the GP-register nvmem device, both HW-confirmed; `rtc0` reads back but the RTC is unset at first boot; set/read timekeeping is now HW-confirmed via the H713 linear-day variant (patch 0031) — `hwclock`/`timedatectl` read the correct date). (Crypto engine deliberately disabled — see above.) |

## Limitations / open items

- **32-bit SMP** — secondaries don't come up for a 32-bit kernel (BL31 brings
  cores up in AArch64; a 32-bit caller needs AArch32 secondaries). arm64 gets
  all four cores, so this is shelved.
- **One peripheral USB controller** — CDC ACM, UMS, and fastboot are deliberate
  successive modes, not a composite gadget. UART remains available throughout.
  Some Linux hosts retain a stale gadget identity across a warm reset; close
  the old device handle and power-cycle the board if re-enumeration is stale.
- **Main-PWM output validated; cooling fan is a power-enable, not PWM.** Patch
  0007's second-generation PWM map (previously proven only indirectly via the
  R_PWM `vdd-cpu` rail, patch 0028) was confirmed on real output during fan
  bring-up: on the bench, main `pwm@2000c00` channel 0 read back `enabled,
  39958/40000 ns` in `/sys/kernel/debug/pwm` with PH17 muxed to `pwm0`. But the
  fan itself is a **3-wire (VCC/GND/tach) on/off part**, not PWM-speed-controlled
  — DMM on the header showed the tach line at its 3.3 V pull-up (sense wired) and
  the +V pin floating (~1.1 V, decaying = unpowered). It stayed dead because the
  `fan_power_hog` for PB5 (shared backlight/fan enable) was malformed (linear
  `<37>` on a 3-cell controller → hog skipped → rail off). Patch 0030 fixes the
  hog to `<1 5>`; the earlier `pwm-fan`-on-PWM0 model was dropped (PH17 is the
  tach). **Bench-confirmed: the fan spins.** The fan and the LED backlight now
  both come up **at power-on from U-Boot** — `board_init` drives the shared PB5
  fan/backlight-enable under a bench-only `CONFIG_H713_POWERON_LIGHT_FAN`, so the
  panel is lit and cooled from reset (projector-as-boot-monitor), with the fan a
  hard interlock for the light. **Backlight brightness is open, PB4/PWM2 now
  re-opened (patch 0032, awaiting bench test).** The earlier "PB4/PWM2 changed
  nothing" result is contradicted by the stock config: the vendor DTB sets
  `panel_pwm_ch = 2` at 25 kHz (`panel_backlight = 75` on a 0..100 scale), stock
  fastlogo drives it via `pwm_request(2, "fastlogo")`, and the vendor Linux port
  dims on PWM ch2. Most likely the bench negative came from the panel's
  serial-init (run by fastlogo, not on mainline) never enabling the PWM-dim path,
  so the un-initialized panel ignores PB4 and holds its power-on-default level.
  Patch 0032 adds a mainline `pwm-backlight` on PWM2/PB4 (25 kHz, 0..100 duty,
  PB5 left hogged so the fan is untouched). **Bench-tested 2026-07-24 — gate
  confirmed panel-side.** With 0032 the PWM is provably correct on PB4:
  `/sys/kernel/debug/pwm` shows channel 2 (`backlight`) duty scaling exactly
  0/20000/40000 ns for brightness 0/50/100 with `actual` matching `requested`,
  and PB4 is muxed to `function pwm2` owned by the backlight — yet the panel's
  light output does not change at any level. So the SoC emits the stock waveform
  and the panel ignores it: brightness is gated on the panel-side init (LED-driver
  PWM-dim enable / LVDS panel serial program) that stock fastlogo runs before
  Linux and mainline does not. That init is part of the Phase-4 MIPS display
  bring-up. 0032 is correct and kept as the foundation — dimming will work through
  this exact node, unchanged, once the panel init lands.

The July 19 cleanup removed the CCU `MIPS_DIAG` mappings, enabled autofs in the
kernel, modeled the fixed 0.96 V `vdd-sys`/Mali supply from the stock DT, and
installed the clean U-Boot build through a bounded backup/write/readback path.
The rebuilt FIT boots with no diagnostic ioremap, autofs, or dummy-regulator
warning; Cedrus and Panfrost still bind and zero systemd units fail.

The July 21 thermal work added safe PLL_CPUX clock transitions, recovered the
R_PWM functional clock from the captured stock kernel, and wired the PL7 PWM
to VDD-CPU. DMM measurements validated 0.909 V for a 0.901 V request, 1.005 V
for a 0.999 V request, and 1.107 V idle for a 1.1005 V request. Every OPP from
480 to 1416 MHz transitions correctly. A two-minute four-core peak-frequency
load held 1416 MHz, raised the measured rail only to 1.127 V (below the 1.16 V
regulator ceiling), stayed below the 75 C passive trip at 68 C, and produced no
thermal, cpufreq, OPP, PWM, clock, or PLL errors. Both 75/85 C passive trips
are bound to the eight-state cpufreq cooling device.

The Crypto Engine was investigated to a definitive dead end (2026-07-23) and is
disabled (`# CONFIG_CRYPTO_DEV_SUN8I_CE is not set`, `HW_RANDOM` off); the CE node
stays in the DTS but inert (H6-compatible `allwinner,sun50i-h6-crypto`). The
investigation, in order:

- **Baseline.** The four A53s carry the ARMv8 crypto extensions (`aes pmull sha1
  sha2`), so software AES/SHA run in-core at ~2 GB/s across the four cores —
  10–50× the device's eMMC/WiFi throughput. The CE offers no performance benefit;
  driving it is a completeness question, not a speed one.
- **Enable + real self-tests.** With `CRYPTO_SELFTESTS=y` the driver binds, sets
  its clocks, registers every algorithm — then each fails its known-answer test.
  (The earlier `/proc/crypto` `selftest: passed` was a vacuous default with
  `CRYPTO_SELFTESTS` off, never a real KAT.)
- **The stock CE has two interrupts** (SPI 73 + 74); mainline requests only the
  first, and the first operation used to hang. Wiring the second (same handler)
  **fixes completion** — operations now return status. But the CE's error status
  is then damning: ciphers report `address invalid` + every error bit, hashes
  report `algorithm not supported` — for *standard* AES and SHA. That only happens
  if the engine reads a bogus algorithm ID and bogus buffer addresses out of the
  descriptor: the H713 uses a different **task-descriptor format** (the vendor
  two-register-bank block), not a different IRQ, clock, or byte-vs-word address.
- **No CE TRNG:** it returns `algorithm not supported`; with `HW_RANDOM` the
  kernel's hwrng core just spam-polls it.

So mainline `sun8i-ce` fundamentally cannot drive this CE. Making it work would
mean reverse-engineering the H713 descriptor format from the vendor
`allwinner,sunxi-ce` driver (whose source we don't have — full BSP or `boot_a`
RE) and adding a new descriptor path: a large effort for zero gain, so it is left
disabled. Software crypto is correct and faster. See [roadmap.md](roadmap.md).

The July 23 reboot→fastboot work finished the mechanism in code. `RTC_DRV_SUN6I`
is now enabled: the H713 RTC (H6-compatible block at `0x07090000`) gets a real
`sun6i-rtc` driver, which registers the previously-orphaned osc32k/iosc clocks,
provides timekeeping, and exposes the eight general-purpose registers as a
battery-backed nvmem device. The reboot handoff moved off the `syscon-reboot-mode`
window (which overlapped the RTC register region) onto **`nvmem-reboot-mode`** over
a fixed nvmem cell (`reboot-mode-magic@1c` → GP7, physical `0x0709011c`) defined
as a child of the rtc node; mainline's `add_legacy_fixed_of_cells` makes the cell
phandle-referenceable with no driver change. The magic (`0xfa57b007`), the
physical address, and the entire U-Boot side are unchanged, so no U-Boot rework
was needed. **Hardware-validated on the bench (2026-07-23):** the new kernel
boots to Debian, `sun6i-rtc` binds as `rtc0`, the RTC nvmem device
(`7090000.rtc/nvmem0`) and the `reboot-mode-magic@1c` cell both register, and the
`nvmem-reboot-mode` consumer binds to that cell; the reboot trigger then landed
the board in U-Boot fastboot with no console interaction (host saw the fastboot
device). One loose end, not blocking: `rtc0` read back as unset at first boot
(hctosys `unable to read` = an invalid, never-set time — expected), and full
set/read timekeeping is now HW-validated: with `hwclock` (`util-linux-extra`)
shipped and the H713 modeled as a linear-day RTC (patch 0031 — the H6 model
read the year as 1970 because the sun50iw12 stores a linear day count),
`date`/`hwclock`/`timedatectl` set and read the correct 2026 date.

A follow-on refinement (2026-07-23) split the single handoff into **two modes**
so the two reboot verbs mean different things: `reboot fastboot` keeps magic
`0xfa57b007` → fastboot, while `reboot bootloader` now uses magic `0xb007c0de`
and, in `preboot`, runs `setenv bootdelay -1` to fall through to the U-Boot
prompt instead of fastboot. The DTS `reboot-mode` node carries both
(`mode-fastboot`/`mode-bootloader`); the U-Boot side is the runtime `preboot` env
(MMC @ `0x400000`):
`if itest.l *0x0709011c == 0xfa57b007; then mw.l 0x0709011c 0; run fastboot_mode; elif itest.l *0x0709011c == 0xb007c0de; then mw.l 0x0709011c 0; setenv bootdelay -1; fi; usb start`.
Both verbs were **hardware-validated on the bench (2026-07-23):** `reboot
fastboot` lands in fastboot and `reboot bootloader` drops to the U-Boot `=>`
prompt, each console-free.

## Board matrix

| Board | Silkscreen | DRAM | Bring-up status |
|-------|-----------|------|-----------------|
| Bench | HY200_QZ713DF_A1 | DDR3 (1 GiB) | primary target — everything above validated here |
| Projector | HY200_QZ713_V2 | LPDDR3 (1 GiB) | DRAM replay-verified only; **do not risk it first** |

See [bringup-notes.md](bringup-notes.md) for the driver-level findings behind
this, and [build.md](build.md) / [flash.md](flash.md) to reproduce it.
