# The power-on gate

Plug the projector in and it waits: dark, about 4 W at the wall, red LED lit, until the power key is
pressed. That is how the device behaves with the stock firmware, and reproducing it is what this gate is
for (measured 09.09.2026, `doku/103-plan-einschaltgate.md` §3 M5). Without it, our boot chain would start
Linux the moment the socket is switched on — convenient on a bench, wrong for something that stands in a
living room.

## Why it needs code at all

The board has no PMIC and no power-hold line, so "off" can only ever mean "the SoC is running and
nothing else is powered." Everything visible or audible — fan, backlight, the USB-A socket's VBUS —
hangs off two GPIOs (PB5, PL3) that U-Boot itself drives; holding that step back *is* the gate, nothing
more. The status LED needs no code of its own: it wires straight to PB5, so it reads red for free while
the gate holds that pin low, and blue the instant the gate lets go.

## How it decides

Before touching PB5/PL3, `board_late_init` reads RTC general-purpose register 5 (`0x07090114`, guarded
by `CONFIG_H713_POWER_GATE`) — the one RTC word nothing between SPL and Linux otherwise writes, and the
only state that survives a reset without surviving a loss of mains power:

| GP5 reads | Meaning | U-Boot does |
|---|---|---|
| `0` | mains just came on (cold start) | gate: wait for the power key |
| `"RUN1"` | a warm restart — `reboot`, a crash, a watchdog reset | boot straight through |
| `"GATE"` | TF-A wrote this on `poweroff` (PSCI `SYSTEM_OFF`) | gate: wait for the power key |

U-Boot writes `RUN1` back on every path, before anything else is powered — so a crash or a watchdog
reset, from inside the gate or from Linux, always finds its way back to a normal boot instead of a dead
device waiting for a key nobody is there to press. The key itself is PL4, active-low against an external
pull-up, debounced 50 ms in software to match the stock firmware; the gate waits for a full
press-and-release rather than just a press, so a key already down when the wait starts cannot fire it
the instant the loop begins. A key that cannot even be read — GPIO lookup or request failing — boots
straight through, since there is no way to leave a wait loop keyed on a line that does not answer.

Holding the key down through all of a cold boot (three seconds or more) skips the gate for that one boot
without touching the environment — a way in with no serial console and no saved `h713_gate=0`. the maintainer
later judged it redundant for a user, since pressing the key at any point already starts the boot anyway,
and left the code in rather than removing it (`doku/103-plan-einschaltgate.md` §5.1).

## Turning it off

```
fw_setenv h713_gate 0
```

from a running Linux, or `setenv h713_gate 0; saveenv` at the U-Boot prompt, overrides the gate without a
rebuild; `1`, the shipped default, turns it back on. The gate is otherwise a build-time option,
`CONFIG_H713_POWER_GATE` — the FEL restore SPL and the `h713-install` (installer role) build never compile it in at all,
so those always start straight through no matter what the environment says (the defconfig matrix in
`README.md`).

Details: `board/sunxi/board.c` (`h713_power_gate` and the helpers above it), `board/sunxi/hy310.env`,
`doku/103-plan-einschaltgate.md`.
