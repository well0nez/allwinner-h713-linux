# Autofocus

The projector focuses itself the way the vendor's firmware does: it puts a chessboard on the wall, films it
with the camera built into the case, measures how sharp that picture is and walks the focus motor until the
measurement stops growing. `h713-autofocus` is that procedure without Android and without the vendor
library.

```
h713-autofocus run
```

or **Autofocus now** on the [settings page](settings-page.md), which runs the same command.

## What happens during a run

1. **The panel is taken over.** The chessboard goes through the console's framebuffer, and the console is
   only on the wall when nothing else is: so the tool switches `h713-warp` off if it was on, switches
   `h713-tv` off, and puts both back in reverse when it ends. It does that itself since 23.09.2026 - an
   autofocus that does not put its own picture up is worth nothing. `--no-handover` leaves it to you.
2. **The chessboard is drawn**, 69 px cells from (97, 92), generated here rather than taken from the
   vendor's PNG. The framebuffer's contents are saved first and written back at the end, including on
   Ctrl-C and SIGTERM.
3. **The camera starts**: YUYV 640x480 over the internal USB camera, the exposure written before the first
   frame because that is what wakes this camera out of its black-frame state.
4. **The search runs**: settle, wait for a quiet picture, coarse hill climb, peak confirmation, fine
   return. Two frames per pass, averaged, through the vendor's cubed-gradient metric.
5. **The panel comes back**, whatever the outcome.

A run takes seconds, not minutes: the metric is a C helper (`h713-afmetric`), a move of six microsteps
costs about 100 ms and two frames about 66 ms, and a full search from clearly out of focus takes a few seconds on
the HY310 (11 s with the handover and the chessboard on 23.09.). The page allows it up to 120 seconds.

## When it runs

- when you ask it to, on the page or on the command line;
- after the projector has been moved, if `after_move = keystone+focus` is set in
  `/etc/h713/keystone.conf`: the automatic keystone runs once when the projector has settled, and the
  autofocus after it (`focus_command`, default `h713-autofocus run`). The three choices are three buttons
  on the settings page, and the shipped default is `off`.

It never runs on its own otherwise. There is no loop and no watchdog that re-focuses a picture you are
looking at.

## The edges, and why the search turns round

The focus motor has no position sensor. What it has is a range watcher in the driver: when the mechanism
reaches the end of its travel, the driver reverses it by a few microsteps, latches an edge flag, and drops
every further command in that direction.

Until 23.09.2026 an edge ended the run. It does not any more, because the vendor's own search does not stop
there either: when the edge in the direction of travel is latched, the search **flips direction and writes
the same number of steps the other way**. An edge is a turning point, not a fault. A latched edge from an
earlier run only decides which way this run starts, and costs no microsteps.

Three of our own limits remain, because a flat or black picture could otherwise bounce between the two
stops until the budget ran out:

- **both edges latched at once** - the range watcher has nothing left to give;
- **more than four turn-arounds in one run**;
- **the hard cap of 1000 microsteps per run.** That is one sweep from edge to edge (about 800) plus the
  fine return. The vendor has no cap at all, only a 22 second watchdog; ours is a cap because nothing else
  would stop a run that never finds a peak. The cap used to be 400, and on 23.09.2026 it ended a run one
  pass before the peak, which is how it was found.

Beside those, the safety rules of `h713-focus` hold unchanged: the range watcher is read before and after
every move, `motor_ctrl_no_limit` is never written, and a run refuses to start while it reads 1.

## How a run ends

The last line names it:

```
stopped: peak   position 51   best 14328   38 passes, 444 msteps
```

| Line | Exit | What it means |
|---|---|---|
| `stopped: peak` | 0 | the fine return found the peak and stayed on it. This is the good one |
| `stopped: budget` | 6 | 280 passes without a peak |
| `stopped: deadline` | 6 | the 22 second clock ran out (`--timeout S`, `0` removes it) |
| `stopped: the hard cap of 1000 msteps per run` | 5 | the travel is used up |
| `stopped: both edges are latched at once` | 5 | the range watcher gives nothing in either direction |
| `stopped: turned round at an edge more than 4 times` | 5 | a picture the metric cannot climb |
| `the motor cannot start: ...` | 4 | a guard refused before anything moved; the sentence names which |
| `no picture: the camera streams but the frame is flat` | 3 | no chessboard, or no lamp |
| a usage or setup error | 2 | the message says what is missing |
| Ctrl-C or SIGTERM | 130 | the panel and the framebuffer are restored first |

`position` is the motor's own counter, not a distance, and it drifts by about six microsteps at every edge
event. Two runs from opposite sides landing on the same counter value is the best check there is.

## When it stops short of sharp

The commonest reason is that the sharp point is not inside the motor's range: a surface too close has its
focus beyond the lens's design range, so every run climbs, keeps getting sharper, turns round at the far
edge, climbs back and ends at the cap with the metric still rising. That is not a fault of the search. On the
HY310 at its usual distance the runs of 23.09.2026 ended at a peak (`stopped: peak`, positions -2 to +31).

If a run against a wall at one to three metres still ends at the cap, the step size or the metric is wrong,
not the mechanism. Focus by hand with `h713-focus up 20` / `down 20` meanwhile, in small steps, looking at
the wall.

Two more things to rule out before doubting the search:

- **the pattern has to be on the wall.** Run it with the handover, or check with `h713-autofocus pattern
  on` that the chessboard is really projected. Exit 3 is the tool saying it filmed a flat frame.
- **the board profile.** `--profile hy310` is the verified one. `hy300-pro` carries the HY310's numbers
  because nobody has read that board's own optics file; if a run overshoots there, doubt the step sizes
  first and try `--profile vafo8`, which is the same thresholds with smaller moves.

## The handover in detail

`run` reads `h713-warp ctl status`; if the warp is on it sends `h713-warp ctl off` and remembers that. It
reads `h713-tv ctl status`; if it is on automatic it remembers that too and sends `h713-tv ctl off`. Then
it waits four tenths of a second for the console to come through the display commit, saves the framebuffer
and draws.

Afterwards it restores the framebuffer, sends `h713-tv ctl auto`, waits half a second and sends
`h713-warp ctl on`. A tool that is not installed, or one that answers `error`, is noted and skipped: the
run still happens, the pattern may then not be seen.

So the picture goes away for the length of a run and comes back by itself. The warp coming back is a
separate step from the picture coming back, which is why there is a visible moment of unwarped picture at
the end.

Details: [h713-autofocus](../tools/h713-autofocus.md), [h713-focus](../tools/h713-focus.md),
[the focus motor](../subsystems/focus-motor.md), [settings-page.md](settings-page.md).
