# The power-on gate

Plug the projector in and it waits: dark, red LED lit, until the power key on the projector is pressed - the gate polls
that key alone (PL4), so the remote cannot start the box from here; it can only where crust holds the off state (below). U-Boot
waits itself, 2.4-2.9 W (09.10.2026, `doku/181`) - below; that is what an image does since 22.10.2026, which runs the
vendor's ARISC firmware and whose boot chain starts no crust ([arisc](../subsystems/arisc.md#crust-experimental)). Where
the boot chain starts a crust that can power off (an image built with the standby), it waits in crust's off state
instead, 0.3-0.6 W at the wall (FEL, HY300PRO-G-EU, `doku/191`), and the power supply hums there (TODO 2.42). That is how the device behaves with the stock firmware, and reproducing it is what this gate is
for (measured 09.09.2026, `doku/103-plan-einschaltgate.md` §3 M5). Without it, our boot chain would start
Linux the moment the socket is switched on - convenient on a bench, wrong for something that stands in a
living room.

## Why it needs code at all

The board has no PMIC and no power-hold line, so "off" can only ever mean "the SoC is running and
nothing else is powered." Everything visible or audible - fan, backlight, the USB-A socket's VBUS -
hangs off two GPIOs (PB5, PL3) that U-Boot itself drives; holding that step back *is* the gate, nothing
more. The status LED needs no code of its own: it wires straight to PB5, so it reads red for free while
the gate holds that pin low, and blue the instant the gate lets go.

## How it decides

Before touching PB5/PL3, `board_late_init` reads RTC general-purpose register 5 (`0x07090114`, guarded
by `CONFIG_H713_POWER_GATE`) - the one RTC word nothing between SPL and Linux otherwise writes, and the
only state that survives a reset without surviving a loss of mains power:

| GP5 reads | Meaning | U-Boot does |
|---|---|---|
| `0` | mains just came on (cold start) | a crust that can power off holds the board off ([below](#a-cold-start-through-crust-since-10102026)); otherwise the gate waits for the power key |
| any word not listed here | unknown | gate: wait for the power key |
| `"RUN1"` | a warm restart - `reboot`, a crash, a watchdog reset | boot straight through |
| `"GATE"` | TF-A wrote this on `poweroff` (PSCI `SYSTEM_OFF`) | gate: wait for the power key |
| `"STBY"` | Linux wrote this at the start of a standby, and the display core did not run again before the reset: the standby did not finish | gate: wait for the power key |

U-Boot writes `RUN1` back on every path, before anything else is powered - so a crash or a watchdog
reset, from inside the gate or from Linux, always finds its way back to a normal boot instead of a dead
device waiting for a key nobody is there to press. The key itself is PL4, active-low against an external
pull-up, debounced 50 ms in software to match the stock firmware; the gate waits for a full
press-and-release rather than just a press, so a key already down when the wait starts cannot fire it
the instant the loop begins. A key that cannot even be read - GPIO lookup or request failing - boots
straight through, since there is no way to leave a wait loop keyed on a line that does not answer.

Holding the key down through all of a cold boot (three seconds or more) skips the gate for that one boot
without touching the environment - a way in with no serial console and no saved `h713_gate=0`. the maintainer
later judged it redundant for a user, since pressing the key at any point already starts the boot anyway,
and left the code in rather than removing it (`doku/103-plan-einschaltgate.md` §5.1).

## How a power-off gets here

`poweroff` ends in PSCI `SYSTEM_OFF`, and BL31 cannot cut the supply on a board without a PMIC. So it writes
`"GATE"` into GP5 and reads it back - if the word does not stick it prints `cannot arm the boot gate, not
resetting` and leaves the cores parked, since a reset without the word would turn the power-off into a reboot -
then prints `PSCI: power off, resetting into the boot gate` and resets the SoC through its watchdog
([hardware.md](../hardware.md); TF-A patches `0005` and `0011`). The reset is a fed sequence: reload on CTRL,
CFG and MODE with the key for an interval of 0.5 s, reload again; if the reset does not come, BL31 prints MODE
and CFG as read back and tries again with the word left in place. Measured on the HY310 on 08.10.2026: the reset
follows the `reboot:` or `Power down` line by 0.58-0.60 s, 6 of 6 times in a FEL image and again on the installed
image (`doku/170`). The feed is there because on 07.10.2026 a watchdog that was already running swallowed the
older, unfed sequence: BL31 printed `system reset failed, board stays powered` and the box stood until the power
was cut (mechanism inferred, `doku/164`).

### Through crust instead (the HY300PRO-G-EU, since 10.10.2026)

A crust that says it can take the power-off (BUILD2 bit 24, `H713_POWER_OFF`) gets it from BL31 instead of the
reset: BL31 still writes `"GATE"` first, then sends crust the vendor's "fake poweroff" request (type 0x19 on msgbox
port 3) and parks the cores once crust confirms with its phase POWEROFF; without the confirmation it resets into
the gate as above and leaves TF-A event 5 for the kernel. crust holds the cluster in reset, puts the DRAM into
self-refresh, holds VDD_SYS in reset and gates it off the R domain (the vendor's `0xdea8` - without it the SoC reset
itself a few milliseconds later and came up here) and drops the one enable of the board's rails, PL6. The box then
draws **0.3 W**, as stock Android off, against 2.4 W in this gate on the same unit. The power key or the remote's IR
code wakes: PL6 back, VDD_SYS out of reset, `"GATE"` turned into `"RUN1"`, an R_WDOG reset - so the gate boots straight
through. A reset while off still finds `"GATE"` and waits here. Measured over FEL on the HY300PRO-G-EU (`doku/188`)
and on the HY310 (`doku/190`): timer, remote and power key, a fresh boot each time.

### A cold start through crust (since 10.10.2026)

A cold start does not wait in the loop either, when crust can take it (U-Boot fork patch `0101`, `doku/191`). With GP5 at
`0`, after the three-second check of the key, U-Boot reads crust's contract page in SRAM A2 (`0x00123800`): the magic
`"H713"`, contract version 5 or later and BUILD2 bit 24. If all three are there, it prints `gate: crust holds the board off,
the power key or the remote wakes it` and asks for PSCI `SYSTEM_OFF` - the same call as Linux's `poweroff`, so BL31 writes
`"GATE"`, checks that crust runs and is outside a standby, and hands it the power off as above. The key or the remote wakes
into a warm start and the gate boots through. Without such a crust - the vendor's ARISC firmware, an older crust - it
prints `gate: no crust on the ARISC` or `... cannot hold the board off` and waits in the loop, without a reset.

There is at most one `SYSTEM_OFF` per mains-on: should BL31 not get crust to take it, it resets with `"GATE"`, and that
waits in the loop. `"GATE"` and `"STBY"` always wait in the loop - after a standby that did not finish, a power off through
crust would overwrite crust's record of the failure that the next boot reports (the owner's decision, 10.10.2026).
`h713_gate=0` and the key held at mains-on work as before and come first; the key held at mains-on is also the way out
should crust's off state ever not wake. Measured over FEL with the cold start set up by hand (GP5 cleared from Linux) on
the HY300PRO-G-EU: dark, 0.3-0.6 W with the USB cable plugged in, the remote woke it, crust's record of the run showed
phase poweroff for 97 s (`doku/191`). Not measured yet: a real mains-on (needs the new U-Boot on the eMMC), the HY310.

*Superseded (10.10.2026):* "The gate itself is unchanged: a cold start waits here as before."


## With crust and the standby

Apart from the cold start above, the gate's code does not change for crust. On an image built with the standby BL31 starts crust from
the FIT before U-Boot proper runs ([README](README.md)), so the ARISC firmware is already up while the gate waits; on an image without
it (since 22.10.2026) the FIT carries no crust, a cold start prints `gate: no crust on the ARISC` and waits in the loop, and a
power-off under the vendor's firmware resets into it as before. On an image with the standby the gate draws 2.9 W with it, the
standby 2.4 W (`doku/181`). A standby ([standby.md](../subsystems/standby.md)) never passes through here: crust
releases CPU0 straight into BL31, which resumes Linux. Nothing in crust writes GP5, and the RTC general-purpose
words, GP5 among them, were unchanged after every standby cycle read back (`doku/165` - `doku/167`). Since
kernel `0245` Linux marks the standby in GP5 itself (below); a standby that finishes neither enters the gate nor
leaves it. The two share the power key, PL4 - U-Boot polls it in the gate, crust
takes it as a wake source in a standby - and on an image with standby ([h713-power](../tools/h713-power.md))
a short press suspends while only a long press, or `poweroff`, ends in the gate (the long press measured on
09.10.2026, `doku/174`).

**A standby that does not finish ends in the gate, dark** (the owner's decision of 09.10.2026, kernel `0245`,
`doku/179`). The driver of the display core, `sun50i-h713-mips`, turns `RUN1` into `STBY` at the start of a
standby (PM_SUSPEND_PREPARE, before the window where the rare hang going to sleep stood) and back into `RUN1`
once the core runs again after the wake - or at the end of a sleep that parked nothing. A reset in between -
crust's budget going to sleep (15 s) or waking up (60 s), the watchdog, a core that stalls the bus at its start -
finds `STBY`, and U-Boot waits for the power key exactly as after a power-off. A `reboot` from Linux writes
`RUN1` first, so a reboot that was asked for still boots. Measured on the HY310 with `h713_gate=1`: a hang in
syscore suspend, crust's reset after 15000 ms, `gate: cold start (GP5 53544259)`, dark until the key; the same
for a hang in syscore resume after 60000 ms; a normal standby back to `RUN1`; a reboot with `STBY` in place
booting through. The U-Boot on the board then still called the word a cold start; its own line ("a standby did
not finish") comes with the next U-Boot. Not caught: crust itself hanging asleep, which only R_WDOG could reset.
With `h713_gate=0` a failed standby boots straight through, as everything else.

*Superseded (09.10.2026, `doku/179`):* "A watchdog reset out of a failed standby comes back through the gate as a
warm restart and boots straight through, lamp on (from the code). [...] Whether the box should instead go dark
into the gate is the owner's decision, and until it is taken nothing here is changed."

## Turning it off

```
fw_setenv h713_gate 0
```

from a running Linux, or `setenv h713_gate 0; saveenv` at the U-Boot prompt, overrides the gate without a
rebuild; `1`, the shipped default, turns it back on. With the gate off a power-off is a reboot: BL31 still
writes `GATE` and resets, U-Boot prints `gate: off (h713_gate=0, ...)`, writes `RUN1` and boots straight through.
Measured on 09.10.2026 with the long press on a standby image: `poweroff`, BL31's `resetting into the boot
gate`, U-Boot's `gate: off` line, and the board boots (`doku/174`). So there is no software "off" with the gate
off; only the mains is. The gate is otherwise a build-time option,
`CONFIG_H713_POWER_GATE` - the FEL restore SPL and the `h713-install` (installer role) build never compile it in at all,
so those always start straight through no matter what the environment says (the defconfig matrix in
`README.md`).

Details: `board/sunxi/board.c` (`h713_power_gate` and the helpers above it), `board/sunxi/hy310.env`,
`doku/103-plan-einschaltgate.md`, `doku/164`, `doku/170`, `doku/174`.
