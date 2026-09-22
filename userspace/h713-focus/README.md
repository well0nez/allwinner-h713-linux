# h713-focus - drive the focus motor by hand

One script, `h713-focus`, Python 3, without dependencies. A replacement for
`legacy/tools/focus` (63 lines of `sh`) with the same subcommands - only that it
looks before and after every move instead of writing blind.

```
h713-focus status          # watcher, edges, counter, and what is free right now
h713-focus up 20           # 20 msteps upwards, in chunks of 2
h713-focus down 20         # downwards
h713-focus flush           # drain the queue (emergency stop)
h713-focus unlatch         # clear latched edges
```

In addition: `-n` / `--trocken` (check and show, write nothing),
`--schritt N` (msteps per write, default 2, at most 18),
`--sysfs PATH` or `$H713_FOCUS_SYSFS` (give the node instead of searching).

**The two German switch names stay.** Messages, help texts and comments are
English since the O4 pass, but `--trocken` and `--schritt` are the command line
itself: a device in the field is driven from a written note, and a note that
stops working is worse than a switch in the wrong language. They are renamed
when the notes are, not before.

Return values: `0` done - `2` misuse or no node - `3` blocked or stopped at an
edge - `4` deadline over / command dropped - `130` Ctrl-C.

## First: the module

Since patch **0157** the node `motor_ctr` is active and since **0156** `homing`
is **off** by default - the driver is loaded at boot (`=m`, over modalias), sets
up the pads, exposes sysfs and moves nothing while doing so. So normally there
is nothing to do; `h713-focus status` says whether it is there.

If it is missing (blacklisted, or a kernel without 0157):

```bash
modprobe hy310_focus_motor
```

On a kernel **before 0156** `homing=0` is mandatory with it: otherwise the
homing sequence runs at load time, and it drives up to 100 msteps **upwards** -
towards the mechanical stop. Whether there is a watcher edge there at all is
unchecked; only the lower one has been measured. That is exactly why
`h713-focus` does **not** load the driver itself.

## What PH14 is - and what it is not

A **range watcher**, not a limit switch. The pin reads `active_level` (here
HIGH) *while* the mechanism stands inside the permitted range; the edge is
recognized when that level **drops**. Measured on 12.09.2026
(`analyse/boot/motor-bereichswaechter-20260912.txt`):

```
raw=1 ... step=-204
raw=0 ... step=-206            <== edge
raw=1 ... edge_dn=1 step=-207  (the driver reverses, latches the edge, holds)
```

Reversing and latching the edge is done by the driver itself. The script does
not rebuild that - it recognizes that it happened and then stops.

`step` is a **counter, not a position.** At an edge event the mechanism
physically moves `1 + k + back_step` msteps, the counter only one. After the
first edge the two drift apart by about 6 msteps, and every further event
increases the offset.

## When it does not drive

| Finding | why it counts |
|---|---|
| `num=0` | No watcher requested -> `motor_limiter_status()` reports "in range" unconditionally, the driver **never** reverses. The first field of the line looks healthy while it does - so it is worthless exactly when it would matter. |
| `motor_ctrl_no_limit = 1` | The range check is switched off. The script **never writes this attribute**, but somebody else may have set it. |
| no `raw=`, or `raw=-1` | Without a raw level there is no way to see whether the watcher delivers anything at all. Exactly this gap produced an invented temperature out of an open input on the NTC. Showing yes, driving no. |
| `raw != act` | The mechanism stands outside the permitted range. |
| `edge_up`/`edge_dn` in the direction of travel | The driver drops such commands **silently** - silently is the wrong thing here. |

On top of that a hard cap of 400 msteps per run, even when the watcher stays
silent: a watcher that reports nothing is no proof that there is still room. And
Ctrl-C is caught - the queue is drained instead of leaving the process in the
middle of a chunk. The mstep that is running runs to its end; the driver cannot
abort it.

## The protocol

`motor_ctrl` takes `(cmd << 8) | (steps & 0x7f) | (full_limit ? 0x80 : 0)`.

| cmd | meaning |
|---|---|
| 1 / 2 | up/down, **sets** the autofocus flag -> busy-wait timing (`mdelay`). The path of the stock autofocus; the old `focus` script took this one. |
| 3 | drain the queue |
| 4 | set the step counter |
| 6 | set `step_low` |
| 7 | drive to a step - **not implemented in the driver**, returns `-EOPNOTSUPP` |
| **8 / 9** | up/down, **clears** the autofocus flag -> sleeping timing. The path for manual operation - **this script takes that one.** |

The driver silently clamps msteps per write to 18 (`MOVE_CLAMP_MAX`). Whoever
writes 30 gets 18 and does not notice; that is why the script checks itself and
breaks longer runs into chunks. The bit `0x80` (`full_limit`) is described in
the driver header but has never been checked - it is not used.

## What is deliberately missing here

**Autofocus.** An autofocus measures the sharpness of whatever is being
projected. On a dark scene or a black picture it measures nonsense and drives
the focus into the void; it belongs on a test image with hard edges. An
automatic control would therefore have to either demand that a suitable test
image is present, or produce one itself (`h713-tv`) and restore the previous
state afterwards. That tool exists since v0.9-beta: `h713-autofocus` (`../h713-autofocus/`) puts a
chessboard up through `h713-tv` and restores the picture afterwards. Not a subcommand here.

**Homing.** There is no reference point besides the two edges, and driving to an
edge in order to find it is exactly what this script avoids.

## `test-stub.py`

Plays the driver in a directory (edge at step -206, as measured), so that the
script runs through without a device: `python3 test-stub.py DIR &` and then
`H713_FOCUS_SYSFS=DIR ./h713-focus down 20`. Reproduces the measurement of
12.09. exactly; writes `motor_limit` atomically, otherwise `h713-focus` rightly
stops on an empty line.

## `_entwurf-agent/`

An earlier draft as a Python package, 2545 lines, still in German. Put aside,
not thrown away - the safety logic written out in full and the test instructions
are worth reading if somebody extends the tool. It is a draft and not shipped
(`install-projekt.sh` installs `h713-focus` and this README, nothing else), so
the English pass has left it as it was. See `_entwurf-agent/LIESMICH.md`.
