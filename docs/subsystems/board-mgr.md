# Board manager: fan and temperature

`hy310-board-mgr` reports the fan speed through Linux `hwmon`. The fan itself is a plain 3-wire
on/off load — red +V, black GND, yellow tachometer — established on the bench (patch `0030`): there is
no PWM on this board, so `fan1_input` is all there is, no speed control.

## Tachometer

The tachometer pulses are counted by a real GPIO interrupt on PH17, the way the vendor driver does it,
not by the 10,000-wakeups-a-second polling hrtimer the previous version used. The vendor counts both
edges and divides accordingly; our previous code counted only rising edges but kept the same division,
so it reported half the true speed. Counting rising edges with `pulses-per-revolution = 2` now gives
the same result as the vendor's own formula. **4860 RPM measured and proven on 11.09.2026**
(`doku/00-STATUS.md`): turning PB5 off drops the reading to 0 RPM, turning it back on brings it back
up, so the reading tracks the physical fan rather than a stuck register.

## This device has no NTC

`ntc_num = 0` in every device tree decompiled from this unit's own firmware, and the vendor's own code
treats that as binding, not decorative: its temperature read loop exits immediately at `ntc_num = 0`,
and the functions that would report a sensor value return a fixed 99 ("no sensor") instead. Our
driver used to override this — a comment called it "tolerant parsing" — and computed a temperature
from the GPADC channel behind it anyway. That channel is not wired to anything: left alone, it free-runs
toward full scale as its sampling time grows, and under load it tracks the CPU's own DVFS voltage, not
any thermal mass. The result was 0 °C, 60 °C and 71 °C at different times, all fabricated. Patch `0152`
makes `ntc_num` binding again: at zero, `temp1_input` is not created at all. A unit whose device tree
carries `ntc_num > 0` gets real temperature reporting from the same driver, unchanged.

Overheating protection was never really about that sensor. The vendor's own code only emits a uevent
when the NTC path crosses its warning threshold; the action that actually powers the device off sits
behind a prolonged **fan stall**, read from the same tachometer this driver proves is live. We do the
same: since patch `0159` the driver warns when the fan drops below `fg-warn-speed` (1000 RPM by default)
and, if it stays there for `fg-warn-cnt` consecutive one-second samples (8 by default), calls
`orderly_poweroff(true)` — userspace gets its shutdown, and the force flag covers a wedged userspace.

A projector whose fan has stopped must not keep running; the lamp and the imager produce heat either
way, so an outage is the cheap outcome. The trigger is the one signal on this board that has been
switched off and on deliberately and answered correctly both times.

`fan_stall_shutdown=0` disarms it at runtime (`/sys/module/hy310_board_mgr/parameters/`) — do that before
deliberately cutting the fan rail on a bench, or the measurement ends in a poweroff eight seconds later.
`thermal_shutdown` stays off: there is no sensor to trigger it.

## A generic bug found here first

Enabling this driver's PH17 interrupt was the first thing on this board to request a GPIO interrupt on
the main PIO controller rather than the R_PIO, and it hung the whole system — `crng init done` never
happened, RCU stalled on CPU 0. The cause was in `pinctrl-sunxi`, not in `board-mgr`: a bank-interrupt
lookup indexed by hardware-bank number instead of position in the interrupt list, invisible until a
chip whose bank list has a gap (H713 has no bank PE) shifted every later interrupt one GIC line off —
PH17's real line landed on the SPI number that was still labelled PG, whose handler read status zero
and cleared nothing, leaving the interrupt permanently pending. Fixed generically in patches `0143` and
`0144`; any future GPIO interrupt on that controller past the gap would have hit the same wall.

## Limits, honestly

- The absolute RPM figure is plausible and reproducible, but **unverified** against a reference
  tachometer — nobody has cross-checked it with an independent instrument.
- Nothing acts on temperature, because nothing measures it on this unit. A device that overheats with a
  *turning* fan gets no protection at all — the stall poweroff cannot see that case.

Details: `doku/60-offen.md` (§board-mgr, §Aufhänger, §NTC), `doku/00-STATUS.md`.
