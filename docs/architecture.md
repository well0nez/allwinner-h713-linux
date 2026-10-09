# Architecture

The H713 runs three processors at once - an ARM cluster, a MIPS core, and a small OR1K core - and by
the time Linux prints its first line, the other two are already doing real work. Most things that look
strange on this SoC (a register that reads back garbage, an SoC that hangs on a plain load, an RPC that
times out instead of erroring) come from not knowing which of the three owns the address you just
touched.

## Who owns what

| Processor | Runs | Owns |
|---|---|---|
| ARM Cortex-A53 ×4 | Linux; BL31 (EL3) on the same cores | AFBD scanout block (`0x05600000`), everything in `cpu_comm`'s shared memory it writes itself; BL31: PSCI, starts crust |
| MIPS32 LE | `display.bin`, started by U-Boot; Linux can park and restart it (`sun50i-h713-mips`) | HDMI capture (INCAP), the window/scaler chain, the panel output block - the whole display pipeline behind the AFBD |
| OR1K "ARISC" | crust, our own (HY310), or the vendor's `h713-arisc.bin` | the R_-peripherals: PMU sequencing, the HDMI hot-plug pin, EDID/DDC RAM. crust serves them as the HDMI front end in normal operation (`doku/163`) and also takes the standby |

Reading a MIPS or ARISC register from the ARM core is possible; writing one is not the same as changing
what it controls. The MIPS firmware recomputes its own window geometry from a small descriptor Linux
publishes - writing the scaler registers directly measurably does nothing, and can leave the display
firmware wedged until the next boot. The one documented exception where a raw read is actively
dangerous is the ARISC's port-status block at `0x0709xxxx`: reading it before the ARISC's EDID module
has finished initializing hangs the SoC outright, no fault, no console (`doku/82-arisc-treiber.md`).
The same holds for the display firmware's blocks once it is gone: with the MIPS parked and the TV domains off, a read of the receiver's LINK window or of INCAP does not return zero, it stops the bus (after a LINK read the watchdog reset the box 16 s later, `doku/176` §2; INCAP, `doku/173`).
Both firmwares are treated as black boxes you talk to over RPC, never as memory you edit.

## How they talk

**ARM ↔ MIPS - `cpu_comm`.** A shared-memory RPC channel: a 5 MiB region at ARM-phys `0x4E300000`, a
hardware msgbox at `0x03003000` for the doorbell, and spinlocks at `0x03004000` guarding the ring. Calls
address a routine by a 32-bit id, not a name or a table - the id is a seeded CRC-32 over the routine
name (`<name>_<cpu>_<pid>`), which the kernel computes itself with `crc32_le()`. As of the current
driver, kernel code gets a direct, blocking API (`cpu_comm_call()`, `cpu_comm_register_callback()`)
alongside the older `/dev/cpu_comm` path that userspace tools still use; both see every message, and a
failed round trip now returns a real error instead of userspace's old "0 results, no error" outcome.
Detail: `doku/83-cpu-comm-api.md`.

**ARM ↔ ARISC.** Same msgbox hardware, a different channel. The ARISC firmware polls for work rather
than waiting on an interrupt, so nothing needs to "wake" it - an earlier doorbell-pulse workaround
turned out to be unnecessary once the actual wait loop was found, and is gone from the current driver.
The kernel exposes this as `include/linux/soc/sunxi/h713-arisc.h` (`arisc_hdmi_reset_edid()`,
`_set_edid()`, `_hpd()`, …), which the HDMI-input driver builds on for `VIDIOC_S_EDID`/hot-plug.
Detail: `doku/82-arisc-treiber.md`.
With crust the driver also watches the contract page in SRAM (heartbeat and error counters, every 10 s) and hands the standby over on the same message box: a round trip before the sleep, a "restore finished" frame after it ([arisc.md](subsystems/arisc.md)).

**RTC general-purpose registers as a flag, not a channel.** A third, much smaller mechanism: the RTC's
`GP0` - `GP7` words at `0x07090114` survive a warm reset (not a full power cycle) and cost nothing to read
or write. U-Boot's power-on gate uses `GP5` to mark "just did a warm reboot from Linux" so it can skip
waiting for the power key; the vendor's ARISC firmware separately leaves a `0xb00f` liveness mark in
`GP3` once its main loop is running (crust keeps its state in its contract page instead,
[arisc.md](subsystems/arisc.md)). Neither is an RPC - they are notes left for whichever side looks next.

## Boot order

```
BROM -> SPL (DRAM init) -> BL31 (EL3) -> U-Boot proper -> Linux
                                |                |
                        loads display.bin   binds sun50i-h713-arisc:
                        into MIPS RAM,      loads h713-arisc.bin via
                        releases MIPS       request_firmware(), resets
                        reset (MIPS runs    the core, runs the startup
                        before Linux does)  handshake (ARISC starts
                                             *after* Linux is already up)
```

This is the opposite of stock Android, where the vendor BL31 loads the ARISC firmware before anything
else runs. Mainline TF-A does not do that, so the job moved into a Linux driver instead - one more
reason the ARISC is unreachable, by design, until that driver has bound and its firmware request has
resolved. With crust (the HY310) our BL31 starts the ARISC again, from the FIT's `scp` image before
U-Boot proper, and the driver keeps that running image when it is the one its device tree names
([arisc.md](subsystems/arisc.md)). `cpu_comm` needs no such handoff: the MIPS core is already running display.bin by the time
Linux starts, so its first RPC call can succeed immediately.

Neither vendor firmware file, nor the HDMI EDID blob, nor the panel/picture tables ship in this
repository or on the built image; crust is built from source with the image. All of them are pulled from **your own** device's dump by `h713-extract` during
install and placed under `/lib/firmware`; a driver whose firmware is missing fails loudly
(`-ENOENT`/`-ENODEV`) rather than booting with something that isn't yours to redistribute.

## The standby: who does what

A suspend to RAM ([standby.md](subsystems/standby.md)) hands the box over between four places where code runs.

- **Linux** prepares: `h713-power` turns the key into `systemctl suspend`, and the drivers quiesce - hdmirx stops the capture and its LINK poll, `cpu_comm` parks the MIPS and gates the five display clocks, afbd idles the scanout, the board manager switches PB5 (LED boost, fan rail) off, msp marks the audio DSP lost, the arisc driver makes a round trip to crust.
- **BL31** takes PSCI `SYSTEM_SUSPEND` and sends crust the "cpu op" request; after the wake it moves the system counter forward by the time crust counted asleep.
- **crust** does the sleep: ARM cluster off, DRAM in self-refresh, wait for a wake source (power key, IR code, its timer); on a wake it brings the DRAM back and releases CPU0 into BL31. Each phase has a budget; in the hang C1 it reset the board after 15 s (`doku/172`).
- **The display MIPS** does nothing from the park on; the wall keeps its last picture. After the wake `h713-mips-restart` has a driver set the TV-top words the sleep reset and start `display.bin` as U-Boot does, binds the receiver with the HDCP 2.2 key, starts `h713-tv` and `h713-warp`, and rebuilds the audio DSP, which lost its power.

Measured on the HY310: the picture back 3.9 - 5.3 s after the wake (`doku/172`, `doku/177`), wake by power key and by IR (`doku/174`); the power draw in standby is not measured.

## What this means for software

A driver for MIPS- or ARISC-owned hardware is an RPC client, not a register driver: it calls a named
routine and waits for a real answer (or a timeout), the same shape whether the call goes over
`/dev/cpu_comm`, the in-kernel `cpu_comm` API, or the ARISC's `h713-arisc.h`. Code that instead maps
one of those blocks with `ioremap()` and pokes it is either redundant with what the RPC already does,
or - for the ARISC's `0x0709xxxx` range before its EDID module is up - a way to hang the board. The
display pipeline specifically, including the KMS device Linux exposes for it, is covered in
[docs/subsystems/display.md](subsystems/display.md); it is not repeated here.

Details: `doku/96-anzeigekette.md`, `doku/82-arisc-treiber.md`, `doku/83-cpu-comm-api.md`,
`doku/103-plan-einschaltgate.md` (the `GP5`/`GP3` measurements).
