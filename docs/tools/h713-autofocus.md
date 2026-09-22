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

The metric itself is C when `h713-afmetric` is beside the tool or on `PATH`, and Python otherwise; every run
says which of the two it used. `--no-helper` forces Python, `--helper PATH` names another binary. Both give
the same integer - that is a golden test, not a hope. Cross-build and install it with
`make -C userspace/h713-autofocus cross` and `make install-cross DESTDIR=/srv/h713-rootfs`;
`rootfs/install-projekt.sh` picks it up if it is there and warns if it is not.

Options: `--profile hy310|vafo8|hy300-pro` picks the board table, `--window full|band|crect|nocen` and
`--stride N` pick the measuring window and the subsampling (default `crect` at stride 3, see below), `--sysfs PATH` and `--dev NODE` skip the searches,
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

`h713-cam grab --raw /data/af-frames/step-0012.gray` writes one such frame; one per motor position, walked with
`h713-focus down 2`, is the fixture. Nobody has recorded it yet. `tests/make_fixture.py` builds a synthetic one -
the same chessboard, blurred by an amount that grows with the distance from a chosen position, so the sharpest
step is known and "does the search converge" has an answer. On it the search lands 4 msteps either side of the
true peak, from both directions, in 28 passes.

```
python3 -m unittest discover -s tests -v      # from userspace/h713-autofocus/
python3 tests/make_fixture.py /tmp/frames --span 200 --peak 100
```

## How long it takes

One 640x480 frame through `measure --metric-only`, in seconds - the projector's A53 measured on 22.09.2026,
the host an i7-11390H with Python 3.12 and with `h713-afmetric` built by `cc -O2`:

| window, stride | A53, Python | host, Python | host, C |
|---|---|---|---|
| `full` 1 | 1.00 | 0.0731 | 0.0016 |
| `full` 2 | 0.25 | 0.0190 | 0.0007 |
| `full` 3 | 0.11 | 0.0085 | 0.0008 |
| `crect` 2 | 0.09 | 0.0070 | 0.0006 |
| `crect` 3 | - | 0.0032 | 0.0005 |

The A53 is about **13x** slower than that host on the same Python work, and the C helper is 7x to 45x faster
than the Python on the same frame; the host C figures include the pipe the tool feeds the frame through, so
they are the whole cost and not just the arithmetic. Hence the two defaults, `crect` at stride 3: on the
board that turned a search from about a minute into 14 s, and from -49 to +43 into 5.7 s. None of it moves a
threshold - the normalising divisor takes the scale out, and all nine window/stride pairs measured on the
board normalised to 5046..5151.

A pass costs roughly 100 ms for the move (6 msteps at 16 ms each), 66 ms for the two frames, and the metric.
The first two are the stock's own cost and cannot be argued away; the metric is ours, which is why it is in C.

## The range watcher will stop a bench run

The search obeys `h713-focus`'s rules, and the strongest of them is the travel-range watcher: when the
mechanism reaches the end of its range the driver latches an edge, the run stops and the tool exits **5**.
On the bench that is the normal outcome and not a fault. A projector pointed at objects about 30 cm away has
its sharp point **beyond** the lens's design range, so every run climbs, keeps getting sharper, and then hits
the edge with the metric still rising (measured twice on 22.09.2026, at counter +31 and +46). **Point it at a
wall** for a run that converges; a bench run tells you the climb works, not where the peak is.

`motor_ctrl_no_limit` is a **0/1 flag**, not a command word. Writing a command word into it - 258, say -
switches the range check off, and then nothing stops the mechanism at its end. `h713-focus` and this tool both
refuse to move while it reads 1, and neither of them ever writes it; if a run stops with
"`motor_ctrl_no_limit=1`", write a plain `0` back yourself and look at what set it.

## Limits, honestly

- It has run on the projector (22.09.2026): the pattern reaches the wall, the camera delivers, the motor moves
  on `cmd 1/2` and the metric climbs monotonically over a 60-mstep sweep. What is still **unproven** is
  convergence - every bench run so far ended at the range watcher's edge, see above. Run it at a wall.
- The vendor's exposure re-check inside the search (`check_gray_level`, every fifth pass) is **not** built:
  AP1's section 8 says that function was summarised, not reconstructed. The gain flag it would set is a profile
  value instead, and it defaults to 1, the sensitive `+-11/+-5` threshold pair.
- Which cells of the vendor's chessboard stay white is only in its PNG, so the generated board is plain.
- `step` is a counter, not a position: at every edge event counter and mechanism drift apart by about six
  msteps. Two runs from opposite sides landing on the same counter value is the best check there is.
