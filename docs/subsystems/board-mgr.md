# Board manager: fan and temperature

`hy310-board-mgr` reports the fan speed through Linux `hwmon`; on the HY310 it also owns the fan's power
rail, PB5, across a standby (below; a standby exists only in an image built with `--standby`). The fan itself is a plain 3-wire on/off load - red +V, black GND,
yellow tachometer - established on the bench (patch `0030`): there is no PWM on this board, so `fan1_input`
is all there is, no speed control.

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
driver used to override this - a comment called it "tolerant parsing" - and computed a temperature
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
`orderly_poweroff(true)` - userspace gets its shutdown, and the force flag covers a wedged userspace.

A projector whose fan has stopped must not keep running; the lamp and the imager produce heat either
way, so an outage is the cheap outcome. The trigger is the one signal on this board that has been
switched off and on deliberately and answered correctly both times.

`fan_stall_shutdown=0` disarms it at runtime (`/sys/module/hy310_board_mgr/parameters/`) - do that before
deliberately cutting the fan rail on a bench, or the measurement ends in a poweroff eight seconds later.
`thermal_shutdown` stays off: there is no sensor to trigger it.

## The L018: an NTC, a lamp, a thermal mode

The L018 (`boards/l018`, kernel `0331`-`0333`) is the board where the same driver does more, because its tree asks for it
(`doku/220`):

- **An NTC.** Its stock tree has `ntc_num = 1` (GPADC channel 1) and its own table (38 pairs, 0..55 °C, `gpadc-table`) and
  thresholds: warn 41, power off 51, resume 34 °C. `temp1_input` reads 21-28 °C at room temperature; the conversion is the
  stock vmlinux's, recomputed by hand. No thermometer was held against it (the owner has none).
- **A lamp and a fan with speed control.** PWM0 on PH17 is the fan's speed, PWM2 on PB4 the lamp's dimmer (it dims as the
  duty rises), the tachometer is PH13. A `bl0` subnode with `duty-array` and `lamp-mode-names` gives the driver the lamp: one
  mode index sets the fans' `duty-array-policy1` and the lamp together, the stock tables std 50/70 %, low 75/60 %, high
  30/95 % - the registers the stock firmware wrote, measured. sysfs `lamp_mode`, `lamp_modes`, `thermal_mode`
  ([h713-lamp](../tools/h713-lamp.md)); without a `bl0` node (every other board) none of these paths runs and none of the
  attributes exists - read on the HY310 and the HY300PRO-G-EU after a boot with the code: the probe lines are the same.
- **A thermal mode.** `thermal-mode = <3>` with `temp_resume`: after 30 cycles above `temp_warn` the driver sets mode 3 (lamp
  75 %, fan 70 %) instead of forcing every fan to 100 %, keeps the chosen mode and sets it again at `temp_resume`. Not
  measured: the NTC never came near 41 °C.
- **The power-off at 51 °C, per board.** The boolean property `thermal-shutdown` in the board manager's node arms it for that
  board alone (kernel `0333`); the module parameter `thermal_shutdown` still arms it everywhere. The power-off goes the way
  of the fan stall, `orderly_poweroff(true)`, once. The L018's tree sets it, as its stock firmware powers off at the same
  51 °C. The power-off itself is not measured.

The fan stall shutdown is measured on the L018: PWM0 at 0 % read 0 RPM after 3.5 s, the verdict came after 8 cycles and the
box was off 6.2 s later. On the owner's unit it has also fired in use - that fan stops at times, a defect of the unit.

## The fan rail in a standby

PB5 is one line with three jobs on the HY310: the fan's +V rail, the enable of the LED boost (the lamp), and the
status LED, which follows it (red when low, measured in the power-on gate, [hardware.md](../hardware.md)). It
used to be a `gpio-hog`, held high for good, so a sleep would have left fan and very probably lamp powered; the
board manager's own switch was dead code, because its fan node named no `fan-power-gpio`, and its "fan power
off" line claimed a switch that never happened (found in review).

Since patches 0207, 0211 and 0222 the HY310 hands PB5 to the board manager: the hog is disabled, `fan0` names
PB5 as `fan-power-gpio`, and the driver requests it high at probe (until then PB5 keeps U-Boot's level) and
switches it directly - low in `suspend_late`, after the display and capture drivers have quiesced, high again in
`resume_early`, before they resume - so lamp and fan go off and on as one. The journal says which case a board is
in: `suspended: fan power rail off`, or `... not ours, left as it is` where a hog holds the line. The tachometer
poll stops for the sleep; after a wake the stall counter starts from zero and for 5 s the tachometer is read
but not judged, so a fan still running up cannot end in `orderly_poweroff()` through `fan_stall_shutdown`.
Unloading the module leaves the rail alone.

The HY300 Pro and the HY200 QZ713DF A1 get the hog back and `fan-power-gpio` deleted: PB5 must never go low on
the HY300 Pro, and neither board has a measurement of it switched. Switching the rail was suspected of the DMA
fault after a wake on the HY310 and ruled out on 08.10.2026; the cause was the display pipeline (`doku/171` section 2).

## A generic bug found here first

Enabling this driver's PH17 interrupt was the first thing on this board to request a GPIO interrupt on
the main PIO controller rather than the R_PIO, and it hung the whole system - `crng init done` never
happened, RCU stalled on CPU 0. The cause was in `pinctrl-sunxi`, not in `board-mgr`: a bank-interrupt
lookup indexed by hardware-bank number instead of position in the interrupt list, invisible until a
chip whose bank list has a gap (H713 has no bank PE) shifted every later interrupt one GIC line off -
PH17's real line landed on the SPI number that was still labelled PG, whose handler read status zero
and cleared nothing, leaving the interrupt permanently pending. Fixed generically in patches `0143` and
`0144`; any future GPIO interrupt on that controller past the gap would have hit the same wall.

## Limits, honestly

- The absolute RPM figure is plausible and reproducible, but **unverified** against a reference
  tachometer - nobody has cross-checked it with an independent instrument.
- Nothing acts on temperature, because nothing measures it on this unit. A device that overheats with a
  *turning* fan gets no protection at all - the stall poweroff cannot see that case.
- The lamp, the tachometer and the supply current in a standby are not measured (stage L of the R2 test plan,
  open), nor how long the fan takes to run up after a wake; the 5 s hold-off is a design value.

Details: `doku/60-offen.md` (§board-mgr, §Aufhänger, §NTC), `doku/00-STATUS.md`; for the standby `doku/171`,
[standby.md](standby.md).
