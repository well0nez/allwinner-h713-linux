# The settings page

The projector serves its own settings page. It is how the picture is squared up, the zoom set, the focus
moved and the sound turned down without a shell, and until a remote control exists it is the only way to do
any of that from the sofa. Everything on it is one command this project already has; the page starts that
command and shows you the first `ok` or `error` line it answers.

## Getting to it

The service is enabled from the first boot (`rootfs/install-projekt.sh` step 5e), listens on every
interface and needs no login:

```
http://<the projector>:8080/
```

The projector joins the Wi-Fi named in `/etc/h713/wifi.env` or takes a wired address; ask the device with
`ip -4 addr`. **There is no authentication** - whoever reaches port 8080 can set the
picture, move the focus motor and start the autofocus. The Wi-Fi password is the door, and on a LAN there
is none. Change the shipped Wi-Fi password before the projector leaves your desk.

The page is one HTML file served from the device; every button is a `POST /api` with a verb out of a fixed
table in `h713-panel`. The browser never names a command, its arguments are checked against their ranges,
and the argument vector goes to the tool without a shell.

## What you are looking at

Across the top, a status strip that is re-read every three seconds: signal, what the picture is (console,
plane or warped), warp on or off, whether the mask is up, whether the keystone standing in the warp is the
automatic's or a hand's, the thermal zones, and the GPU's frames per second.

Below it, three groups: **Projection**, **Picture**, **Sound**. On a phone they are three tabs; from 900 px
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
has right now, and push them into the warp. It needs a level reference (below) and it runs once - it is not
a loop.

### Reset

`h713-warp ctl keystone reset`, all eight corners to 0. That is the identity, and at the identity with the
zoom at 100 the daemon does not start the GPU at all.

### Zoom (the projection area)

The slider is 50 to 100 per cent in steps of 5 and sends `h713-warp ctl zoom PERCENT`. It makes the
projected rectangle smaller on the wall without cutting anything off: every corner is pulled in by
`(100 - percent) * 5` per-mille on top of the keystone, inside the same matrix, so the GPU shrinks the
picture the way the vendor's "Digital scaling" does.

The display firmware's own zoom used to be on this page as a second slider and is gone since 24.09.2026.
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
watcher before and after. **Level reference** is `h713-keystone reference`: stand the projector the way it
is meant to throw and press it once, so the automatic has a pose to correct against.

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

**Aspect** is how the source is fitted into the panel: `auto proportional full 16:9 4:3 zoom`.
**Save picture settings** writes the nine values, the preset, the aspect and the zoom to the device, so they
come back after a reboot. Nothing else on this tab is written until you press it.

Since 24.09.2026 these controls reach the warped picture too: the warp draws NV12 onto the video plane, and
that is the channel the firmware runs its picture controls on. On the older RGB path they did nothing while
the warp was drawing.

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
  24.09.2026.
- **No authentication, no upload, no shell.** The verb table is the whole surface: a verb that is not in it,
  or an argument outside its range, is refused before a tool is started.
- **The page decides nothing.** If a tool is missing or refuses, the page repeats that tool's own sentence
  and changes nothing.

Details: [h713-panel](../tools/h713-panel.md), [h713-warp](../tools/h713-warp.md),
[h713-keystone](../tools/h713-keystone.md), [keystone.md](keystone.md), [autofocus.md](autofocus.md).
