# The power-on gate

Plug the projector in and it waits: dark, about 4 W at the wall, red LED lit, until the power key is
pressed. That is how the device behaves with the stock firmware, and reproducing it is what this gate is
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
| `0`, or any word not listed here | mains just came on (cold start) | gate: wait for the power key |
| `"RUN1"` | a warm restart - `reboot`, a crash, a watchdog reset | boot straight through |
| `"GATE"` | TF-A wrote this on `poweroff` (PSCI `SYSTEM_OFF`) | gate: wait for the power key |

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

## With crust and the standby

The gate's code does not change for crust. BL31 starts crust from the FIT before U-Boot proper runs
([README](README.md)), so on the HY310 the ARISC firmware is already up while the gate waits; what that does to
the 4 W is not measured. A standby ([standby.md](../subsystems/standby.md)) never passes through here: crust
releases CPU0 straight into BL31, which resumes Linux. Nothing in crust writes GP5, and the RTC general-purpose
words, GP5 among them, were unchanged after every standby cycle read back (`doku/165` - `doku/167`): a standby
neither enters the gate nor leaves it. The two share the power key, PL4 - U-Boot polls it in the gate, crust
takes it as a wake source in a standby - and on an image with standby ([h713-power](../tools/h713-power.md))
a short press suspends while only a long press, or `poweroff`, ends in the gate (the long press measured on
09.10.2026, `doku/174`).

A watchdog reset out of a failed standby comes back through the gate as a warm restart and boots straight
through, lamp on (from the code). The hang going to sleep does end that way - crust resets the board after 15 s
and it boots again (`doku/172`) - but the box of those runs has `h713_gate=0` in its saved environment
(`doku/170`, `doku/174`), so what the gate itself would do was not exercised. Whether the box should instead go
dark into the gate is the owner's decision, and until it is taken nothing here is changed.

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
