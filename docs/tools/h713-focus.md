# h713-focus - driving the focus motor by hand

`h713-focus` moves the projector's focus motor in small, watched steps and stops the moment the mechanism
tells it to. It is a dependency-free Python 3 script, the same five subcommands as the old `legacy/tools/focus`
shell script, but it checks before and after every move instead of writing blind.

```
h713-focus status          # watcher, edges, counter, and what is currently free to move
h713-focus up 20           # 20 msteps up, in chunks of 2
h713-focus down 20         # down
h713-focus flush           # clear the queue (emergency stop)
h713-focus unlatch         # clear a remembered edge
```

The script's messages and help texts are English; two of its switches keep their German names, because the
command line is what a note in the field is written from: `-n`/`--trocken` checks and prints without writing;
`--schritt N` sets msteps per write (default 2, capped at 18 by the driver itself); `--sysfs PATH` (or
`$H713_FOCUS_SYSFS`) gives the motor node instead of searching for it. Exit codes: `0` done, `2` misuse or no
node, `3` locked or stopped at an edge, `4` deadline hit or command dropped, `130` Ctrl-C.

## Why it does not load the driver

Since patch 0157 the `motor_ctr` sysfs node is loaded automatically at boot, and since 0165 (23.09.2026)
`homing` is on again, as in stock: if the mechanism stands outside its travel when the module loads, the
driver walks it back - up to 100 msteps up, then down, reading the gate at every step - and says so in the
kernel log. **Homing is not focusing**: it moves nothing while the mechanism is inside its travel ("limiter in
range - nothing to do"), and when it does move, it stops at the first position inside, wherever the sharp
picture may be. Sharpness is the autofocus's or the hand's business. Between 0156 (12.09.) and 0165 it was off, because only the lower edge of the gate had been
observed and homing drives upwards first; on 23.09. the upper edge was measured too. `h713-focus status`
says whether the module is present; if not, `modprobe hy310_focus_motor` loads it (`homing=0` keeps a bench
still). This tool never loads the module itself.

## What the range watcher actually is

The pin (`PH14`) is a **range watcher**, not a limit switch: it reads high while the mechanism is inside its
allowed range, and the edge is reached when that level *drops*. The driver reverses and latches the edge by
itself; the script does not reproduce that logic, it recognizes that it happened and stops. The switch is a
contact to ground that closes outside the travel and is open inside, so the high level inside is the pad's
pull-up - since patch `0164` the driver's default bias (a pinctrl group cannot do it: the sunxi pinctrl is strict and would keep the pin from the driver). Before it the pad floated on our boot chain
and read a stale level: on 23.09.2026 the HY310 came up reading "in range" with the focus 110 msteps above
its travel, nothing was latched, and this tool refused every move (rule 4) until homing walked it back.
Measured through the PIO registers that day: with pull-down the pad reads low everywhere, with pull-up it
reads high over the travel, drops at the edge within 5 msteps and returns 10 msteps back in. Measured
12.09.2026 (`analyse/boot/motor-bereichswaechter-20260912.txt`): the counter and the physical position drift
apart by roughly 6 msteps at every edge event, because a reversal moves the mechanism `1 + k + back_step`
msteps but the counter only one - `step` is a counter, not a position.

The script refuses to drive when the watcher's own signal is not trustworthy: no watcher requested (`num=0`,
where the driver reports "in range" unconditionally and never reverses), the range check disabled
(`motor_ctrl_no_limit`), a missing or `-1` raw level, or an edge already latched in the direction requested.
A hard cap of 400 msteps per run applies even when the watcher stays silent - silence is not proof there is
still room. Ctrl-C drains the queue instead of leaving it mid-chunk; the mstep already in flight finishes,
because the driver cannot abort it.

## What this deliberately does not do

**Autofocus** - judging sharpness needs a test image with hard edges, and on a dark scene or a blank wall an
autofocus measures noise and drives the focus into it. That is [h713-autofocus](h713-autofocus.md)'s job - it
puts the pattern up itself and restores the picture afterwards - not a subcommand here. **Homing** - there is no reference point besides the two edges, and driving
to an edge just to find it is the exact blind write this tool exists to avoid.

Details: doku/94-fokusmotor-endschalter.md, analyse/boot/motor-bereichswaechter-20260912.txt
