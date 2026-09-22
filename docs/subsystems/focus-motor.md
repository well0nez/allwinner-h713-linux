# Focus motor

A stepper motor drives the lens focus, controlled through the `hy310-focus-motor` driver
(`motor_ctrl`, four phase lines plus one sensor) and moved by hand with
[`h713-focus`](../tools/h713-focus.md) or searched by
[`h713-autofocus`](../tools/h713-autofocus.md). Since 12.09.2026 the driver loads and enables the
node by default, but touches nothing until told to move.

## PH14 is a range watcher, not an end switch

That distinction is the whole story of this subsystem. PH14 reads HIGH for as long as the mechanism
is inside its allowed travel; a mechanical stop is not signalled by hitting a contact, it is signalled
by that level **dropping**. The driver does not even look at which direction it is moving in - the
same pin answers for both. Measured 12.09.2026, driving downward in 2-mstep increments
(`analyse/boot/motor-bereichswaechter-20260912.txt`):

```
raw=1 ... step=-204
raw=0 ... step=-206   <- edge: the driver reverses one mstep and latches edge_dn
raw=1 ... edge_dn=1, further downward commands rejected
```

For a while the line looked dead - every position, over 440 msteps, read HIGH. The cause was our own
patch: it forced a pull-down bias with a rule that does not exist in the vendor driver, so the pin
read "out of range" everywhere except where the watcher itself was actively driving it. Removing that
forced bias (patch `0153`) and exposing the raw level in `motor_limit` (patch `0154`) is what
uncovered the real behaviour, and the node is active again since patch `0157`.

`motor_ctrl_no_limit` is a **0/1 flag, not a command register**: any non-zero write switches the range
check off. Writing a `motor_ctrl` command word into it by mistake therefore turns the bypass on instead
of moving anything - which is how it was found on 22.09.2026. `h713-focus` refuses to drive while it
reads 1, so the mistake announces itself rather than running the mechanism into a stop. Clear it with
a zero and read it back:

```
echo 0 > /sys/devices/platform/motor-ctr/motor_ctrl_no_limit   # 0 = watcher on, 1 = bypassed
```

## Homing is off by default

Only the lower edge has ever been observed. Homing starts by driving up to 100 msteps **upward**
first, straight at the mechanical stop; if that direction's watcher edge turns out not to exist or not
to fire, the driver never reverses and the run ends by driving into the stop. Until the upper edge is
measured, `homing=0` is the shipped default (patch `0156`) - the module still loads and exposes sysfs
on every boot, it just never drives the mechanism on its own.

## `step` is a counter, not a position

At every edge event the mechanism physically travels `1 + k + back_step` msteps while the step counter
only advances by one, so counter and mechanism drift apart by roughly six msteps the first time this
happens, and further with every following edge. `step` tells you whether and which way the motor
turned; it is not a coordinate, and nothing recalibrates it - there is no absolute reference besides
the two travel-range edges themselves, and only one of them is known.

## Two read-back layouts, on purpose

`motor_ctrl` reads back `step_cur step_inc%10 in_range`, and `motor_limit` since patch `0154` adds the raw
level, `active_level`, both latched edges and the counter. Both are ours. Stock prints something else: one
packed string out of `motor_ctrl_show` (0xc05d6a48),

```
"%d%d.%02d.%d%d\n"     edge_up edge_dn "." step_cur "." step_inc%10 limiter      e.g.  "00.18.01"
```

and the vendor autofocus parses exactly that - `getMotorValue` (0x0002fee0 in `libduRYXtp.so`) wants seven
bytes and two dots, and on our line it finds no dot, logs "data error" and keeps its old values, so it would
search in an arbitrary direction and never see an edge (AP1 section 6). Patch `0154a` therefore adds a
**read-only** `motor_state` in that layout beside the others; `motor_ctrl` and `motor_limit` are unchanged, so
`h713-focus` and every note written against them stay correct. The last field is the limiter, not a direction:
the app calls it `last_dir`, the driver writes `motor_limiter_status()` there - AP1b section 4 corrected AP1 on
that, off the encoded `sprintf` argument slots at 0xc05d6a58..0xc05d6ac8.

`cmd 7` (goto step) stays refused with `-EOPNOTSUPP` (patch `0112`). Stock's `motor_goto_step` (0xc05d7cbc)
only cleans the queue, stores `g_goto_step` and kicks the work item, and nothing ever consumes or clears it
(AP1b section 6d), so there is no behaviour to copy.

## The search, in one paragraph

The stock autofocus draws a chessboard, films it and hill-climbs: two frames per pass, a cubed-gradient
sharpness sum over a window of the luma plane divided by a divisor the first measurement fixes, then five
states - settle, wait for a quiet picture, coarse climb with 8-mstep moves, a 3-pass peak confirmation with 6,
a fine return with 2 that stops within 50 of the best value seen. 280 passes, and a 22 s watchdog on the Java
side. The full pseudo-code with every constant is `umbau/re-apps/AP1/tables/focus-loop.txt` (AP1 sections 2.6
and 2.7); the twelve board variants differ in the move sizes, not in the rules (AP1b sections 9 and 10).
[`h713-autofocus`](../tools/h713-autofocus.md) is that procedure, and it writes `cmd 1/2` here, the codes that
set the driver's `autofocus` flag and its busy-wait timing.

## Using it

Move it by hand - `h713-focus status|up|down|flush|unlatch` - which checks `motor_limit` before and
after every move and never touches homing. See [`docs/tools/h713-focus.md`](../tools/h713-focus.md).

## Limits, honestly

- The upper travel edge is **unverified** - nobody has driven the mechanism there to look.
- Whether the 800-mstep travel figure in the device tree matches the real range is **unverified**;
  only the lower end, at `step = -206` from an arbitrary power-on position, is measured.
- Autofocus through the camera is built as a tool, not as a mode of this driver, and it is **unverified**:
  `h713-autofocus` has never run on the projector.

Details: `doku/94-fokusmotor-endschalter.md`.
