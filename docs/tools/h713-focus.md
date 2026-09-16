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

Since patch 0157 the `motor_ctr` sysfs node is loaded automatically at boot and, since 0156, `homing` defaults
to off - the module sets up the pads and exposes sysfs without moving anything. `h713-focus status` says
whether it is present; if not, `modprobe hy310_focus_motor` loads it. On a kernel **before** 0156, that
`modprobe` needs `homing=0` explicitly, because the homing sequence otherwise drives up to 100 msteps *toward
the mechanical stop* on load, and only the lower edge has ever been confirmed to have a watcher at all. That
risk is exactly why this tool never loads the module itself.

## What the range watcher actually is

The pin (`PH14`) is a **range watcher**, not a limit switch: it reads high while the mechanism is inside its
allowed range, and the edge is reached when that level *drops*. The driver reverses and latches the edge by
itself; the script does not reproduce that logic, it recognizes that it happened and stops. Measured
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
autofocus measures noise and drives the focus into it. Producing or checking for such an image is a separate
tool's job, not a subcommand here. **Homing** - there is no reference point besides the two edges, and driving
to an edge just to find it is the exact blind write this tool exists to avoid.

Details: doku/94-fokusmotor-endschalter.md, analyse/boot/motor-bereichswaechter-20260912.txt
