# h713-keystone - the projector's own auto keystone, rebuilt

`h713-keystone` reads the accelerometer, turns the tilt into the vendor's two angles, runs the vendor's own corner
geometry and pushes eight per-mille insets into `h713-warp`. One dependency-free Python 3 script in
`userspace/h713-keystone/`, with four reference models beside it in `model/`: 1091 lines and 87 tests taken over
byte-identical from AP2c, AP2f, AP2g and AP2h.

```
h713-keystone reference             # once, with the projector standing level
h713-keystone read                  # raw counts, the g vector, pitch and roll
h713-keystone once [--apply]        # the eight insets for the tilt it has now
h713-keystone run [--dry-run]       # the loop; SIGTERM puts the manual set back
h713-keystone status                # configuration, sensor, reference, warp
h713-keystone watch                 # after a move, run the automatic once (the unit's verb)
```

`h713-keystone-auto.service` runs `watch`; it is enabled from the first boot and does nothing while `after_move = off` (the settings page's "After a move" buttons write that key and restart the unit). `-C PATH` names
another configuration file, `--reference PATH` another reference file, `--device PATH` an IIO node instead of the one
found by name, `--warp PATH` another warp tool, `-q` drops the warnings.

Exit codes: `0` done, `2` a usage, configuration or file error, `3` no readable accelerometer, `4` the pose is more than
45 degrees off flat and may not become a reference, `5` `h713-warp` refused, `130` SIGTERM or Ctrl-C.

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
degree. A reading therefore costs about 0.3 s at 100 Hz and the loop runs at roughly three readings a second, not ten -
and the threshold is sized from that averaged degree, not from AP2h 4a's 0.1146 degree ADC digit or the vendor's 0.3
degree dead band, which would fire on noise. `hysteresis_degrees = 1.0` held for `hold_seconds = 1.0`, on *either* angle
- the vendor leaves GsY without any. The first reading of a run is applied at once: a projector that waits before it
corrects looks broken.

**The throw ratio** is the one number nobody has measured. AP2c's optics imply 0.8176 (2079 mm of image at 1700 mm,
section 5) and `throw_ratio = ini` uses those `camprjspe.ini` constants untouched; a tape measure replaces it, and
`throw_ratio = 1.2` then scales `Whalf` and `Hhalf` so the half-field tangents match, leaving the panel aspect alone.
The default is the word `ini`, not `0.82`: that is a rounding of 0.8176, and writing it back would move the vendor
optics by 0.3 % for nothing.

## The configuration: `/etc/h713/keystone.conf`

```
# /etc/h713/keystone.conf -- "key = value", # comment
iio_name           = sc7a20    # the IIO device's own name, not iio:deviceN
axis_pitch         = +y        # which raw axis and sign is the pitch (GsY),
axis_roll          = -x        # the roll (GsX), and the vertical one
axis_vertical      = +z
throw_ratio        = ini       # ini = camprjspe.ini (0.8176), or a measured number
zoom_scale         = 0         # 0/1/2 -> target width 1920/1728/1440 (16:9, 16:10, 4:3)
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

`h713-keystone reference` stores the pose the projector is corrected *against* in `/etc/h713/keystone-ref`, in the
vendor's units (the IIO digit times 16, AP2g 5), with the axis map it was taken under. It refuses a pose more than 45
degrees off flat (`checkGsensorDataOk`, LocalService.java:582, the vendor's own gate) and one from another axis map,
whose numbers describe a different pose. Measure it again after a move.

Each correction is eight `h713-warp ctl keystone set CORNER AXIS VALUE` calls, `CORNER` in `tl tr bl br`, `VALUE` an
integer per-mille inward. `run` reads `h713-warp ctl status` at the start, keeps whatever manual set it finds and writes
it back when it stops, so switching the automatic off leaves the picture as the user had set it. That status is parsed
tolerantly (`tl_x = 12`, `tl x 12`, `tl-x: 12`), the daemon being written in parallel; one without all eight values
counts as no answer.

`python3 -m unittest discover -s tests -v` from `userspace/h713-keystone/` runs 130 tests: the 87 that came with the
models, unchanged, and 39 for this tool - the IIO reader against a fake sysfs directory, the reference file, the
hysteresis, the poses table above, the configuration parser, the h713-warp verbs against a recorder. `run
--dry-run` does the whole loop on the real node and only prints.

## Limits, honestly

- **It has run on the projector once** (HY310, 22.09.2026): the sensor reads, the reference is taken, a 25-degree
  nose-up tilt pulls the top edge in and a lifted side leaves the picture level. That is one evening, with a PC as
  the source and no long run behind it.
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
