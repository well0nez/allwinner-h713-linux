# Focus motor

A stepper motor drives the lens focus, controlled through the `hy310-focus-motor` driver
(`motor_ctrl`, four phase lines plus one sensor) and moved by hand with
[`h713-focus`](../tools/h713-focus.md). There is no autofocus, and — since 12.09.2026 — the driver
loads and enables the node by default, but touches nothing until told to move.

## PH14 is a range watcher, not an end switch

That distinction is the whole story of this subsystem. PH14 reads HIGH for as long as the mechanism
is inside its allowed travel; a mechanical stop is not signalled by hitting a contact, it is signalled
by that level **dropping**. The driver does not even look at which direction it is moving in — the
same pin answers for both. Measured 12.09.2026, driving downward in 2-mstep increments
(`analyse/boot/motor-bereichswaechter-20260912.txt`):

```
raw=1 ... step=-204
raw=0 ... step=-206   <- edge: the driver reverses one mstep and latches edge_dn
raw=1 ... edge_dn=1, further downward commands rejected
```

For a while the line looked dead — every position, over 440 msteps, read HIGH. The cause was our own
patch: it forced a pull-down bias with a rule that does not exist in the vendor driver, so the pin
read "out of range" everywhere except where the watcher itself was actively driving it. Removing that
forced bias (patch `0153`) and exposing the raw level in `motor_limit` (patch `0154`) is what
uncovered the real behaviour, and the node is active again since patch `0157`.

## Homing is off by default

Only the lower edge has ever been observed. Homing starts by driving up to 100 msteps **upward**
first, straight at the mechanical stop; if that direction's watcher edge turns out not to exist or not
to fire, the driver never reverses and the run ends by driving into the stop. Until the upper edge is
measured, `homing=0` is the shipped default (patch `0156`) — the module still loads and exposes sysfs
on every boot, it just never drives the mechanism on its own.

## `step` is a counter, not a position

At every edge event the mechanism physically travels `1 + k + back_step` msteps while the step counter
only advances by one, so counter and mechanism drift apart by roughly six msteps the first time this
happens, and further with every following edge. `step` tells you whether and which way the motor
turned; it is not a coordinate, and nothing recalibrates it — there is no absolute reference besides
the two travel-range edges themselves, and only one of them is known.

## Using it

Move it by hand — `h713-focus status|up|down|flush|unlatch` — which checks `motor_limit` before and
after every move and never touches homing. See [`docs/tools/h713-focus.md`](../tools/h713-focus.md).

## Limits, honestly

- The upper travel edge is **unverified** — nobody has driven the mechanism there to look.
- Whether the 800-mstep travel figure in the device tree matches the real range is **unverified**;
  only the lower end, at `step = -206` from an arbitrary power-on position, is measured.
- Autofocus through the camera is a plausible replacement for the dead idea of a hard end switch, but
  is unbuilt: a separate project, not a mode of this driver.

Details: `doku/94-fokusmotor-endschalter.md`.
