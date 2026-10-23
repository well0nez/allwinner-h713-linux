# The settings as a web page

The projector has two settings surfaces. The page on the wall, driven by the remote, is the everyday one
([the settings guide](settings.md)). This one is the web page `h713-panel` serves for a phone or a PC browser:
it carries more - the keystone as a drawing with corners you drag, the colour sliders, the warp switch - and
it is the way without the remote. Everything on it is one command this project already has; the page starts
that command and shows you the first `ok` or `error` line it answers.

![The web panel, section Projection: the keystone as a drawing, the arrows and step sizes, zoom](../images/panel/panel-projection.png)

## Getting to it

The service is enabled from the first boot (`rootfs/install-projekt.sh` step 5e), listens on every
interface and asks the browser for a password once:

```
http://<the projector>:8080/
```

The projector joins the Wi-Fi named in `/etc/h713/wifi.env` or takes a wired address; ask the device with
`ip -4 addr`. The browser asks for a user name and a password: the user name does not matter, the
password is the one the projector made at its first start - read it over SSH with
`h713-panel --show-password` (or in the journal of the first start). Without it nobody who merely
reaches port 8080 can move the focus motor or change the picture. Still change the shipped Wi-Fi
password before the projector leaves your desk; the page's password travels over plain HTTP inside
that network.

The page is one HTML file served from the device; every button is a `POST /api` with a verb out of a fixed
table in `h713-panel`. The browser never names a command, its arguments are checked against their ranges,
and the argument vector goes to the tool without a shell.

## What you are looking at

Across the top, a status strip that is re-read every three seconds: signal, what the picture is (console,
plane or warped), warp on or off, whether the mask is up, whether the keystone standing in the warp is the
automatic's or a hand's, the thermal zones, and the GPU's frames per second.

Not every board has a camera, an accelerometer and a focus motor (the HY300PRO-G-EU has the accelerometer
only). What the board lacks has no controls: the page asks `h713-features` once when it loads, hides the
buttons that would only answer "not present on this board", and says in one line what is missing.

Below it, four groups: **Projection**, **Picture**, **Colour**, **Sound**. On a phone they are tabs; from 900 px
of width on they stand side by side and the tab buttons disappear.

## Projection

### The keystone drawing

The dashed rectangle is the panel. The quadrilateral inside it is where the four corners of the picture sit
on the wall. `tl` is the top left corner **as you see it on the wall**, `tr` top right, `bl` bottom left,
`br` bottom right - verified on the HY310 on 22.09.2026 by pulling `tl` in by 150 per-mille and looking.

- **Drag a handle** and the corner follows the finger or the mouse. A drag is absolute: the page works out
  the per-mille value, clamps it, and sends `h713-warp ctl keystone set CORNER AXIS VALUE` at most ten
  times a second, and once more when you let go.
- **The pad of four arrows** moves the picked corner by the chosen step. The arrows are wall directions:
  "right" on a right-hand corner means a smaller inset, and the page flips the sign for you
 . It sends `ctl keystone nudge`.
- **The step** is 1, 10 or 50 per-mille.
- **Under the drawing** there is one button per corner reading `tl x 210/740  y 312/1000`: the value and the
  most that corner may still take. Pressing it picks that corner. The maximum is the vendor's own clamp -
  the x of a corner is limited by the corner at the other end of its row, the y by the one at the other end
  of its column, so the picture can never be pulled past its own width or height.
- **With a keyboard**, Tab walks onto the handles and the arrow keys nudge; the first arrow after the focus
  has moved picks that corner instead of moving it.

### Mask on / Mask off

`h713-warp ctl test mask CORNER` puts a calibration picture on the wall instead of the HDMI source: a grey
field with a white frame, a circle with a crosshair, and the picked corner marked with a ring. Each corner
carries its value and its maximum, so a corner can be aimed with nothing plugged in. While the mask is up,
picking a corner on the page marks it on the wall as well. **Mask off** goes back to the picture.

### Auto now

`h713-keystone once --apply`: read the accelerometer, work out the eight values for the tilt the projector
has right now, and push them into the warp. Without a level reference (below) the tilt is measured against the
ideal level pose and the strip says `ref ideal`; it runs once - it is not a loop.

### Reset

`h713-warp ctl keystone reset`, all eight corners to 0. That is the identity, and at the identity with the
zoom at 100 the daemon does not start the GPU at all.

### Zoom (the projection area)

The slider is 50 to 100 per cent in steps of 5 and sends `h713-warp ctl zoom PERCENT`. It makes the
projected rectangle smaller on the wall without cutting anything off: the picture shrinks about its own
centre inside the keystone, in the same matrix, so the GPU shrinks it the way the vendor's "Digital
scaling" does and it stays square with the keystone. Only the GPU can do that, so below 100 the slider
switches the warp on if it is off; at 100 it leaves the warp as it is.

The display firmware's own zoom used to be on this page as a second slider and is gone since 23.09.2026.
Measured at the DE's picture scaler: asking it to shrink left the ratio at 1:1 and showed the top left crop
of the picture. That scaler only enlarges. What is left of it is the magnifier, `h713-tv ctl zoom in F`,
which is not on the page because it does something else - it enlarges a part of the source - and because it
is refused anyway while the warp draws.

### After a move

Three buttons, `off`, `keystone` and `keystone+focus`. They write the `after_move` key into
`/etc/h713/keystone.conf` and restart `h713-keystone-auto`.

- **off** (the shipped default): the projector logs that it was moved and changes nothing.
- **keystone**: after the projector has been tilted by more than 3 degrees and has then stood still for
  2 seconds, the automatic runs **once**.
- **keystone+focus**: the same, and the autofocus afterwards.

Nothing runs while the projector stands still, whatever a hand has set. That is deliberate: a value you set
by hand stays until the next move.

### Focus

`-20`, `-5`, `+5`, `+20` are `h713-focus down|up N` in microsteps, each one read against the driver's range
watcher before and after. **Level reference** is `h713-keystone reference`, and it is optional: the automatic
already corrects against the ideal level pose (0, 0, 1 g). Pressed with the projector on a surface a spirit
level has passed, it stores the pose the sensor reads there, which refines the ideal by the sensor's own
mounting offset; the strip then says `ref set` instead of `ref ideal`. `ref refused` means the stored file no
longer matches the axis map in `keystone.conf`: the automatic corrects against the ideal meanwhile, and the
button replaces the file. The help line under the button says the same.

**Autofocus now** is `h713-autofocus run`, and the page gives it up to 120 seconds. It
takes the panel over, puts a chessboard on the wall, walks the motor and gives the picture back. The line at
the bottom of the page is the tool's own verdict, for instance
`stopped: peak   position 51   best 14328   38 passes, 444 msteps` - `peak` is the good one. What the other
endings mean is in [autofocus.md](autofocus.md).

### Warp on / Warp off

The master switch for the GPU path (`h713-warp ctl on|off`), and it is saved, so the projector comes up the
way you left it. With the warp **on** and nothing to warp - all eight corners 0 and the zoom at 100 - the
daemon runs in bypass: it does not open the GPU, and `h713-tv` shows the capture ring exactly as it does
without the service. Keystone, mask and zoom all need the warp on.

## Picture

The presets are the vendor's own (`standard cinema vivid game computer hdr energy_saving custom`) and each
one sets the firmware's picture mode plus nine values. Under them, five sliders - brightness, contrast,
saturation, hue, sharpness - drawn over the ranges `h713-tv ctl list` reports, not over a range invented
here. Choosing a preset moves the sliders with it.

`brightness` is the black level on this hardware, not a lamp control, so on bright content you will see
nothing move. The lamp is not adjustable on the HY310.

**Aspect** is how the source is fitted into the panel: `auto proportional full 16:9 4:3`. The display
firmware also has a `zoom` aspect; it stops the picture for good and is not offered (06.10.2026).
**Save picture settings** writes the nine values, the preset, the aspect and the zoom to the device, so they
come back after a reboot. Nothing else on this tab is written until you press it.

Since 23.09.2026 these controls reach the warped picture too: the warp draws NV12 onto the video plane, and
that is the channel the firmware runs its picture controls on. On the older RGB path they did nothing while
the warp was drawing.

## Colour

The white balance as two sliders, Warm - Cool and Green - Magenta (each only ever lowers a gain, so white never clips),
and, in the Picture group, the colour temperature (Auto, Warm, Normal, Cool - the panel's own measured curves) and the
gamma level (1.8 to 2.4); **Save picture settings** keeps them. The six colour axes (hue and saturation per primary) are
not offered since 20.10.2026: the display firmware's colour manager has no visible effect on the HY310, measured with the
camera ([h713-tv](../tools/h713-tv.md)). What each control does, measured: [h713-panel](../tools/h713-panel.md).

## Sound

Volume 0 to 100, mute on/off, and the audio policy: `auto` follows the picture, `on` forces it, `off` keeps the speaker quiet while the picture stays.

## Limits worth knowing

- **One command at a time.** A second button pressed while the first is still running waits up to five
  seconds for its turn and then says so. The autofocus can hold that lock for a minute or more.
- **The status never waits.** While a command runs, the three-second poll answers "busy" and the page keeps
  the numbers it had; nothing on the strip goes stale silently.
- **Three status calls every three seconds**: `h713-warp ctl status`, `h713-tv ctl status brief` and
  `h713-keystone status`. The `brief` is not cosmetic - the full status asks the firmware over sysfs and
  costs about 55 ms, long enough to hold a warp frame, which is how a tearing report was traced on
  23.09.2026.
- **One password, no upload, no shell.** The verb table is the whole surface: a verb that is not in it,
  or an argument outside its range, is refused before a tool is started.
- **The page decides nothing.** If a tool is missing or refuses, the page repeats that tool's own sentence
  and changes nothing.

Details: [h713-panel](../tools/h713-panel.md), [h713-warp](../tools/h713-warp.md),
[h713-keystone](../tools/h713-keystone.md), [keystone.md](keystone.md), [autofocus.md](autofocus.md).
