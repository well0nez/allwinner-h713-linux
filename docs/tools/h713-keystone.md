# h713-keystone - the projector's own auto keystone, rebuilt

`h713-keystone` reads the accelerometer, turns the tilt into the vendor's two angles, runs the vendor's own corner
geometry and pushes eight per-mille insets into `h713-warp`. One dependency-free Python 3 script in
`userspace/h713-keystone/`, with four reference models beside it in `model/`: 1091 lines and 87 tests taken over
byte-identical from AP2c, AP2f, AP2g and AP2h.

```
h713-keystone reference             # optional: refine the ideal with a pose taken on a level surface
h713-keystone read                  # raw counts, the g vector, pitch and roll
h713-keystone once [--apply]        # the eight insets for the tilt it has now
h713-keystone run [--dry-run]       # the loop; SIGTERM puts the manual set back
h713-keystone status                # configuration, sensor, reference, warp
h713-keystone watch                 # after a move, run the automatic once (the unit's verb)
```

`h713-keystone-auto.service` runs `watch`; it is enabled from the first boot, watches against the ideal level pose while there is no reference file (a fresh image has none; until 26.09.2026 it waited for the file, and until 23.09.2026 it exited and systemd restarted it every five seconds), and does nothing while `after_move = off` (the settings page's "After a move" buttons write that key and restart the unit). Without an accelerometer the unit is skipped (a condition on `in_accel_x_raw`), and `99-h713-keystone.rules` starts it when one appears after the boot. `-C PATH` names
another configuration file, `--reference PATH` another reference file, `--device PATH` an IIO node instead of the one
found by name, `--warp PATH` another warp tool, `--last-auto PATH` where the automatic notes what it applied
last, `-q` drops the warnings.

Exit codes: `0` done, `2` a usage, configuration or file error, `3` no readable accelerometer, `4` the pose is more than
45 degrees off flat and may not become a reference, `5` `h713-warp` refused, `7` no accelerometer on this board at all ("not present on this board", [h713-features](h713-features.md)), `130` Ctrl-C. SIGTERM, which is how systemd stops the unit, ends with `0` (until 03.10.2026 it was 130, and every stop left the unit "failed").

## Where the numbers come from

**The axis map** is the one thing a reading of the vendor binaries got wrong. AP2g found that the vendor driver
swaps the chip's x and y on the way to the app and AP2h's NOTE listed three candidates for our mainline path; three
poses on the HY310 (22.09.2026, raw LSB, about 1000 per g, six-second averages) decide:

| pose | raw x | raw y | raw z | what moved |
|---|---|---|---|---|
| standing on the bench | 26 | 172 | 1068 | the reference pose |
| nose up, a book under the front feet | 37 | 531 | 929 | **y**, by 20.6 degrees |
| left side lifted by a book | -292 | 161 | 1020 | **x**, by -17.2 degrees |

So `z` is vertical, **`y` is the pitch** and **`x` is the roll** - the identity, the third of AP2h NOTE 5's candidates,
not the vendor's swap, under which the same nose-up pose would read as a 20 degree *roll* and the correction would
rotate the picture instead of trapezoiding it. Hence the three axis defaults, and hence no `mount-matrix` in the device
tree (AP2h NOTE 4a): the transform lives here, where it is a configuration key and not a claim about the hardware.
Lifting the **left** side (seen from behind the projector) makes raw x negative. The wall settled the sign on
22.09.2026: with `axis_roll = +x` the correction tilted the picture further, with `-x` it stayed level, so `-x` is the
default. A reference taken under one sign is refused under the other (`h713-keystone reference` again).

**The sampling rate, the averaging and the hysteresis.** A sysfs read of `in_accel_*_raw` waits for the device's
*next* sample and `st_accel` starts the SC7A20 at 1 Hz, so one reading would cost three seconds: the tool writes
`sampling_rate` into `sampling_frequency` at the start (offered: 1, 10, 25, 50, 100, 200, 400, 1600). One raw triple at
rest spreads 77/102/85 LSB peak to peak, five degrees of nothing; ten averaged triples spread 16/12/11, about one
degree. A reading through sysfs therefore costs about 0.3 s at 100 Hz (*superseded 19.10.2026: measured on the HY310 it is 0.7 s with nothing else reading and 1.4 s while the watch unit reads too; the IIO buffer below brings it to 0.14 s*) and the loop of `run` runs at roughly three readings a second, not ten -
and the threshold is sized from that averaged degree, not from AP2h 4a's 0.1146 degree ADC digit or the vendor's 0.3
degree dead band, which would fire on noise. `hysteresis_degrees = 1.0` held for `hold_seconds = 1.0`, on *either* angle
- the vendor leaves GsY without any. The first reading of a run is applied at once: a projector that waits before it
corrects looks broken.

**The throw ratio** is the one number nobody has measured. AP2c's optics imply 0.8176 (2079 mm of image at 1700 mm,
section 5) and `throw_ratio = ini` uses those `camprjspe.ini` constants untouched; a tape measure replaces it, and
`throw_ratio = 1.2` then scales `Whalf` and `Hhalf` so the half-field tangents match, leaving the panel aspect alone.
The default is the word `ini`, not `0.82`: that is a rounding of 0.8176, and writing it back would move the vendor
optics by 0.3 % for nothing.

## Reading the sensor: the IIO buffer

`st_accel` switches the SC7A20 on for every sysfs value, waits for it to boot (`bootime` sample periods) and switches it off
again. Measured on the HY310 on 19.10.2026: about 24 ms a value when nothing else reads (on the new kernel, with the sysfs path that is now the fall back), so 0.72 s for the thirty values of one
averaged reading; the watch unit read the sensor all the time and the two serialised on the driver, so every other reading took
1.4 s, `h713-keystone read` 1.8 s and `once --apply` 1.9 s. The settings page's "Turn to wall" followed the keys 2 to 4 s late.

Since 19.10.2026 a reading is one burst through the IIO buffer. The kernel needs `CONFIG_IIO_BUFFER`, `CONFIG_IIO_SW_TRIGGER` and
`CONFIG_IIO_HRTIMER_TRIGGER` (all three in the board defconfig; the sensor has no interrupt line in the device tree, so a timer
trigger clocks the buffer). The tool makes the trigger `h713-keystone` through configfs the first time
(`/sys/kernel/config/iio/triggers/hrtimer/h713-keystone`; systemd mounts configfs, the tool mounts it if nobody did) and sets its rate
to `sampling_rate`. A burst then

1. opens `/dev/iio:deviceN` first: the kernel lets one process have it, so a second reader (the unit and the settings page) waits for the
   burst of the first, 3 s at most, instead of disturbing its switches;
2. clears a `buffer/enable` that a killed run left on, selects the trigger, enables the three channels, sets the buffer length;
3. enables the buffer, reads `average_samples` plus 3 scans (the format comes from `scan_elements/*_type`, `le:s12/16>>4` here;
   the first 3 are thrown away, because the driver itself waits two sample periods after the switch-on), and disables the buffer.

So the sensor is on only while it is read: 0.14 s for ten triples at 100 Hz, and `watch` takes a burst, then pauses 0.5 s. Without a
buffer (a kernel without `CONFIG_IIO_BUFFER`, no node in `/dev`, no timer trigger) or when a burst fails, the reading goes through
sysfs as before and the journal says why, once per cause (`warning: no IIO buffer (...) - reading through sysfs, about 2.0 s a reading`;
`-q` keeps it quiet); the buffer is tried again at the next reading. The start line of `watch` says which way the readings go and what
they cost (`a reading every ~0.66 s through the IIO buffer`). While a burst has the buffer on, the kernel refuses sysfs reads of
`in_accel_*_raw` (`Device or resource busy`): anything that reads them by hand has to stop `h713-keystone-auto.service` first.

Measured on the HY310 on 19.10.2026 (one warm start after the deploy, the unit running all the time as in use):

| | sysfs, before | IIO buffer, after |
|---|---|---|
| the 10 triples of one reading (in the process, median of 12) | 1.43 s | 0.14 s |
| `h713-keystone read`, whole call (median of 12) | 1.83 s | 0.51 s |
| `h713-keystone once --apply`, whole call (median of 12) | 1.94 s | 0.74 s |
| twelve presses of Right through the settings page, 0.12 s apart: the last corners are written | 4.0 s after the first press (2 runs) | 2.3 s after the first press (3 runs) |
| the unit `h713-keystone-auto` (60 s) | 2.3 % of a core (0.1 s pause) | 1.2 % of a core (0.5 s pause) |
| all four cores, not idle (60 s) / load average (the whole box, 8.5 h after a boot against 11 min after one) | 4.1 % / 2.0 | 0.6 % / 0.2 |

The rest of `once --apply` is the start of Python, the model's search for the rectangle and the eight `h713-warp` calls. The averages
of ten contiguous triples scatter a little more than those of ten sysfs triples taken over 0.7 s (30 averages, alternating, standard
deviation 5.7/4.3/8.0 LSB against 4.9/4.4/4.0; single triples scatter alike, 14 to 17 LSB, and no two consecutive triples were equal);
twenty triples (0.24 s) give 4.6/3.3/5.9, which `average_samples = 20` would use. Not measured: the current the sensor and the CPU
draw (only the CPU shares above), whether the first triples after a switch-on are stale after a pose change (at rest they are
indistinguishable from the later ones in 80 cold starts, which cannot show it), and the HY300PRO-G-EU.

## The configuration: `/etc/h713/keystone.conf`

```
# /etc/h713/keystone.conf -- "key = value", # comment
iio_name           = sc7a20    # the IIO device's own name, not iio:deviceN
axis_pitch         = +y        # which raw axis and sign is the pitch (GsY),
axis_roll          = -x        # the roll (GsX), and the vertical one
axis_vertical      = +z
throw_ratio        = ini       # ini = camprjspe.ini (0.8176), or a measured number
zoom_scale         = 0         # 0/1/2 -> target width 1920/1728/1440 (16:9, 16:10, 4:3)
turn_to_wall       = 0         # degrees, -30..30: + when the RIGHT side of the picture is the higher one (the settings page writes it)
sampling_rate      = 100       # Hz written into sampling_frequency at the start
average_samples    = 10        # raw triples averaged per reading
hysteresis_degrees = 1.0       # a change this big applies ...
hold_seconds       = 1.0       # ... after it has stood this long
after_move         = off       # watch: off | keystone | keystone+focus (the settings page writes it)
move_degrees       = 3.0       # a tilt change this big counts as a move ...
settle_seconds     = 2.0       # ... once the readings have then stood still this long
settle_degrees     = 1.0       # ... within this much
focus_command      = h713-autofocus run   # what keystone+focus runs afterwards
```

Without the file the defaults above apply. An unknown key or an unreadable value goes into the journal by name
(`warning: /etc/h713/keystone.conf:7: wobble is not a key of this file -- dropped`) and is dropped, not guessed.

## The reference pose, and how it talks to `h713-warp`

**Without a reference file the automatic corrects against the ideal level pose** `(0, 0, 1 g)`, and every result
line of `read`, `once`, `watch` and `run` ends in `reference ideal (0, 0, 1 g) - h713-keystone reference refines it`;
`status` prints `reference  ideal ...` or `reference  file (DATE): PATH, counts X Y Z`. The ideal is not a guess: the
vendor's chain computes "current attitude minus factory attitude" (`get_gsensor_du`), the factory attitude is the jig
value `GsInitXYZ`, this HY310 carries none (AP2e), and against all zeros `get_gsensor_du` gives the same GsX and GsY as
against `(0, 0, 1 g)` - only the unused GsZ differs. Since 26.09.2026; before, `once` warned and used the ideal
anyway, `watch` waited for the file and `run` refused.

`h713-keystone reference` refines that ideal: it stores the pose the sensor reads in `/etc/h713/keystone-ref`, in the
vendor's units (the IIO digit times 16, AP2g 5), with the axis map it was taken under and the date, and prints the
pose's offset against the ideal (`ok offset  pitch 9.15  roll -1.38 degrees, ...`). Taken with the projector on a
surface a spirit level has passed, that offset is the sensor's mounting offset. It refuses a pose more than 45 degrees
off flat (`checkGsensorDataOk`, LocalService.java:582, the vendor's own gate); a file from another axis map is refused
when it is read, because its numbers describe a different pose. A refused file is said once - a `warning:` line on
stderr, the journal under the unit - and the automatic corrects against the ideal meanwhile: every result line ends in
`reference refused - ideal (0, 0, 1 g) applies, h713-keystone status says why`, `status` prints `reference  refused
(why)`, and `reference` taken again replaces the file. Nothing is replaced behind the user's back, and nothing exits:
`v0.95-beta` exited with 2 over such a file, and systemd restarted the unit every five seconds. (The exits that
remain under the unit - 3, a sensor that is there and does not answer, and 5, `h713-warp` refused - are retried with a
delay that grows from 5 s to 60 s over five restarts and stays there, so a late sensor is picked up and a dead one costs
one journal line a minute.) A reference taken where
the projector happens to stand at first boot would be wrong - it rarely stands where it throws (Marco, 23.09.2026) -
so nothing asks for one.

Each correction is eight `h713-warp ctl keystone set CORNER AXIS VALUE` calls, `CORNER` in `tl tr bl br`, `VALUE` an
integer per-mille inward. `run` reads `h713-warp ctl status` at the start, keeps whatever manual set it finds and writes
it back when it stops, so switching the automatic off leaves the picture as the user had set it. That status is parsed
tolerantly (`tl_x = 12`, `tl x 12`, `tl-x: 12`), the daemon being written in parallel; one without all eight values
counts as no answer.

`python3 -m unittest discover -s tests -v` from `userspace/h713-keystone/` runs 227 tests: the 87 that came with the
models, unchanged, and 140 for this tool (29 of them for the turn to the wall, below, and 22 for the IIO buffer, with a fake kernel: a directory with the buffer's files and a FIFO for the node) - the IIO reader against a fake sysfs directory, the reference file and the
ideal, the hysteresis, the poses table above, the configuration parser, the h713-warp verbs against a recorder. `run
--dry-run` does the whole loop on the real node and only prints.

## The turn to the wall

An accelerometer sees how the projector is tilted and rolled, not how far it stands turned to the side of the wall; the vendor takes that from its camera, which this firmware path does not use. `turn_to_wall` in `keystone.conf` is that number, set by hand: degrees from -30 to 30, positive when the RIGHT side of the picture is the higher (the farther) one and negative for the left, as the viewer sees it; the settings page's "Turn to wall" writes it. It goes into the vendor's chain as `du_r` together with the tilt, in `once`, `watch` and `run`, and nothing in the tool ever changes it, so it stays after a move until it is changed; the unit reads the key again at every apply, so a value set while it runs counts at the next move. The sign of `du_r` depends on the mount - minus the turn for front and rear-ceiling, plus for rear and ceiling, where the viewer's right is the panel's left - and `MODE_PERM` then carries the pulled-in corners to the viewer's side; `tests/test_turn.py` settles both against a ray model of the wall in which a corrected picture is right only if its four corners are a rectangle on the wall (12 degrees to the right, level, front mount: 214 px across and 110 px at top and bottom on the right edge, 25 px and 1 px on the left, the mirror image for the left; with a tilt as well, and in all four mounts). The value is applied whenever the automatic runs: `once --apply` (which the page runs at every change) and `watch` after a move; with `after_move = off` nothing runs on a move, so the value waits for the next `once --apply`. Every application replaces the eight corners, those set by hand included, and a result line ends in `wall turn +12 degrees` while a turn is set. Measured on the HY310 on 19.10.2026: `once --apply` took 1.9 s, of which the reading of the sensor was 1.8 s (not the 0.3 s given above), with a turn as without; the settings page therefore never runs two at once, and the run that follows a press takes the last value. *Superseded the same day by the IIO buffer (above): `once --apply` takes 0.74 s and the last corners of twelve presses are written 2.3 s after the first.* Not measured: the mounts other than front on a projector (the ray model only), whether a step of one degree is what the eye wants (one degree is about 2 % of height between the two sides), and the HY300PRO-G-EU.

## Limits, honestly

- **It has run on the projector on two days** (HY310): on 22.09.2026 the sensor read, the reference was taken, a
  25-degree nose-up tilt pulled the top edge in and a lifted side left the picture level; on 02.10.2026 the ideal
  reference, a reference taken from the settings page and "Auto now" passed (`doku/134` A1). Both with a PC as
  the source and no long run behind them.
- At rest the eight values still scatter by about half a degree, some 14 per-mille, even with thirty samples
  averaged. The one-degree hysteresis holds that back; it does not remove it.
- The throw ratio is derived, not measured (AP2c question 1): if it is nearer 1.2, every correction is too strong.
- It needs `model/` beside the real file: install under `/usr/local/lib/h713-keystone/`, symlink in `/usr/local/bin`.

## After a move, once: `watch` and the gate

The vendor's automatic is not a control loop, and neither is ours: `h713-keystone watch` (what the unit
`h713-keystone-auto.service` runs) does nothing while the projector stands still, whatever a hand has set. When
the tilt changes by more than `move_degrees` (3) and the readings have then been still for `settle_seconds` (2),
it runs the automatic ONCE and, with `after_move = keystone+focus`, the autofocus after it (`focus_command`,
default `h713-autofocus run`). `after_move = off` (the default) only logs the move; the unit is enabled and running from the first boot, so the choice is the key in `/etc/h713/keystone.conf` alone - the settings page's "after move" buttons write it and restart the unit (Marco, 23.09.2026: the automatic stays off until it is asked for, and the choice is stored like every other setting). So a keystone set by hand
stays until the projector is moved again - that is the gate - and `h713-keystone status` says whose values the
warp carries: `keystone by  auto` when they are the last automatic set untouched, `manual` when a hand changed
them since. `once --apply` is the automatic on demand; `run` (the old loop) stays for experiments only.
