# h713-autofocus - the projector's own autofocus, rebuilt

`h713-autofocus` is the stock autofocus procedure without Android and without the vendor library: it draws a
chessboard on the wall, films it with the internal USB camera, measures how sharp the picture is and walks the
focus motor until the measurement stops growing. One dependency-free Python 3 script in
`userspace/h713-autofocus/`.

```
h713-autofocus pattern on           # chessboard on the panel (h713-tv ctl off first)
h713-autofocus measure              # one sharpness value for the current position
h713-autofocus run                  # the whole search
h713-autofocus pattern off          # clear it again

h713-autofocus run --dry-run DIR    # replay recorded frames, no device at all
h713-autofocus measure --metric-only FRAME    # time the metric on one frame
```

Options: `--profile hy310|vafo8|hy300-pro` picks the board table, `--window full|band|crect|nocen` and
`--stride N` pick the measuring window and the subsampling, `--sysfs PATH` and `--dev NODE` skip the searches,
`--cell PX` changes the chessboard's cell size, `-q` silences the per-pass log. `run` also takes
`--direction 0|1` (up/down), `--timeout S` (default 22, the vendor's own watchdog; `0` removes it),
`--start STEP` for a replay, and `--no-pattern` to leave the framebuffer alone.

Exit codes: `0` a peak was found, `2` a usage or setup error, `3` the camera streams but the picture is flat,
`4` the motor may not move (no range watcher, `motor_ctrl_no_limit=1`, an edge already latched), `5` an edge
was reached during the run or the run's mstep cap was hit, `6` the budget or the deadline ran out without a
peak, `130` Ctrl-C.

## Where the numbers come from

Everything here is read out of the vendor stack, not invented: `umbau/re-apps/AP1/REPORT.txt` sections 2, 3, 6
and 7 with the full pseudo-code in its `tables/focus-loop.txt`, and `umbau/re-apps/AP1b/REPORT.txt` sections 4,
9, 10 and 11. The search is `thread_fun_LCD_vafo10_HY260` (0x0002EA90 in `libduRYXtp.so`), which the HY310's
`camprjspe.ini` selects with `VaFocus = 10`.

**The metric.** For every pixel of the window, two 3-tap gradients, each halved, **cubed** and shifted right by
two - separately, which is not the same as cubing, adding and shifting once. The cube, not the square, is what
makes the peak sharp. The sum is then divided by a divisor that the *first* measurement of a run fixes:
`10` below 12001, else `sum // ((sum & 0xFB) + 5012)`. That is why every threshold in the search is a plain
number: whatever window and stride are measured, the first reading lands near 5012. Measured on one 640x480
synthetic frame, all nine combinations normalise to 5060..5231.

**The board table.** `PROFILES` in the script carries per board what `camprjspe.ini` and the compiled-in
constants say: the move sizes `(coarse, confirm, fine)`, the four exposure values of the ini's `l*` block, the
camera's USB pair, the window, the stride and the gain flag. `hy310` is the verified one: moves 8/6/2,
exposures 60/25/140/6, `0bda:5803`. `vafo8` is the same thresholds with 2/2/1 moves - `vafo8_HY350`, the
fallback for a drive that overshoots with 8-step moves. `hy300-pro` is **not verified**: nobody has read that
board's `camprjspe.ini`, so it carries the HY310's numbers and the tool says so on every run (AP1b 11 and its
follow-ups 3 and 5). Doubt the step sizes first.

## The pattern

The vendor ships `bg_auto_focus.png`, a 1920x1080 chessboard of 69 px cells from (97, 92), with some cells left
white so the black squares form a centre block and four corner blocks. That file is vendor material and is not
carried here; the tool **generates** a plain chessboard of the same cell size and origin instead, which has more
edges than the vendor's - the metric can only like that.

It goes onto the panel through `/dev/fb0`, the console's own surface (`CONFIG_DRM_FBDEV_EMULATION=y` in the
board defconfig). That is the first of the three routes AP1 section 7 lists, and it was chosen because it needs
no DRM master and so cannot collide with `h713-tv`, which holds one whenever its plane is on. Hand the panel
over first:

```
h713-tv ctl off             # console instead of the capture plane
h713-autofocus run
h713-tv ctl auto            # picture follows the signal again
```

`run` saves the framebuffer's contents before it draws and writes them back when it ends, including on
Ctrl-C and SIGTERM. `pattern on` leaves the board standing on purpose; `pattern off` clears it, and
`h713-tv ctl console` draws the console back.

## The camera

YUYV 640x480, two MMAP buffers, `select` with a 2 s timeout, and the even bytes of a buffer are the luma plane -
the same path `h713-cam` uses, and the same the vendor uses. The exposure is written before the first frame
(`EXPOSURE_AUTO = 1`, then `EXPOSURE_ABSOLUTE`), which is also what wakes this camera out of the black-frame
state `h713-cam`'s README describes. `uvcvideo` is a module in the board defconfig
(`CONFIG_USB_VIDEO_CLASS=m`, `mainline/patches/kernel/board/hy200_qz713df_a1_defconfig`), loaded on demand.

The node is found by the name `uvcvideo` takes from the device. The vendor instead reads `idProduct`/`idVendor`
of the USB port behind the node and matches the ini's pair; that stricter route is **not** built in - these
boards carry one camera, and the pair is in the profile, so it can be added without moving anything.

## The motor

The search writes the stock autofocus commands `1`/`2` to `motor_ctrl`, not `h713-focus`'s manual `8`/`9`: same
movement, the driver's busy-wait timing instead of the sleeping one, which is what the vendor's search uses
(AP1 6). It reads `motor_limit` - our own format, with the fields patch `0154` added - before and after every
move, and it keeps `h713-focus`'s four rules: never blind, an edge stops the run, `motor_ctrl_no_limit` is
never written, and there is a hard cap of 400 msteps per run.

The packed read-back the *vendor* parser wants is a separate attribute, `motor_state` (patch `0154a`,
[`docs/subsystems/focus-motor.md`](../subsystems/focus-motor.md)). This tool does not use it; it exists so a
vendor-side script can read the motor at all.

## Running it without a device

`run --dry-run DIR` replays a directory of raw 640x480 luma frames, one file per motor position, through the
real search with a simulated motor whose position indexes the directory. The step number is the last run of
digits in the file name, with a leading minus only when no letter or digit comes before it - so
`step-0012.gray` is 12 and `step_-0012.gray` is -12 (this motor's counter really does go negative).

Nobody has recorded the real fixture yet; it needs the device. `tests/make_fixture.py` builds a synthetic one -
the same chessboard, blurred by an amount that grows with the distance from a chosen position, so the sharpest
step is known and "does the search converge" has an answer. On it the search lands 4 msteps either side of the
true peak, from both directions, in 28 passes.

```
python3 -m unittest discover -s tests -v      # from userspace/h713-autofocus/
python3 tests/make_fixture.py /tmp/frames --span 200 --peak 100
```

## How slow the metric is

Pure Python, on one 640x480 frame, measured with `measure --metric-only` on an i7-11390H (Python 3.12):

| window | stride 1 | stride 2 | stride 3 |
|---|---|---|---|
| `full` (rows 8..471, cols 8..631) | 0.077 s | 0.021 s | 0.010 s |
| `band` (a 320 px band, centre) | 0.038 s | 0.010 s | 0.005 s |
| `crect` (rows 120..359, 424 cols) | 0.027 s | 0.007 s | 0.003 s |

The A53 in this projector is several times slower than that host, and a pass costs two frames, so the full
window at stride 1 would be roughly a second per pass - too slow for a search with a 280-pass budget. The
default is therefore the vendor's own window at **stride 2**, a quarter of the work for a peak in the same
place, and the narrower windows are there for a board that needs them. None of this changes the thresholds:
the normalising divisor takes the scale out.

## Limits, honestly

- Nothing here has run on the projector yet. The metric, the state machine, the thresholds and the failure
  paths are proven against recorded and synthetic frames only.
- The vendor's exposure re-check inside the search (`check_gray_level`, every fifth pass) is **not** built:
  AP1's section 8 says that function was summarised, not reconstructed. The gain flag it would set is a profile
  value instead, and it defaults to 1, the sensitive `+-11/+-5` threshold pair.
- Which cells of the vendor's chessboard stay white is only in its PNG, so the generated board is plain.
- `step` is a counter, not a position: at every edge event counter and mechanism drift apart by about six
  msteps. Two runs from opposite sides landing on the same counter value is the best check there is.
