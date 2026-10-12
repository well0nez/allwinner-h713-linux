# h713-panel - the projector's settings page

`h713-panel` is the projector's own web page: opened on a phone over the projector's Wi-Fi or in a browser
over the LAN, it carries the entries of the vendor's "Projection Settings" and "Display settings" - in our
own style, not a copy - and, since 11.10.2026, everything else that was only a command line or a configuration
file: the remote, the picture's start behaviour, the overlays, the power key, the Wi-Fi and the host name. One
dependency-free Python 3 script plus the page beside it, no framework, no build step, nothing fetched from the
internet.

**Nothing is decided in the page.** Every button is one command this project already has (or one `key = value` line
of a configuration file in `/etc/h713`, written the way `h713-warp` writes `warp.conf`), and the first
`ok`/`error` line of that command's answer is what appears at the bottom of the screen. The browser never
names a command: it names a verb out of a fixed table, the arguments are checked against their ranges, and
the argument vector goes to `subprocess` without a shell.

```
h713-panel [--port 8080] [--address ADDR] [--tools DIR] [--page PATH] [--keystone-conf PATH]
           [--password-file /etc/h713/panel.env] [--no-auth] [--show-password] [--etc /etc/h713]
h713-panel --rollback-wifi [--etc DIR]       # what the Wi-Fi fall-back timer runs
```

## How to reach it

After `systemctl enable --now h713-panel`: `http://<the projector>:8080/`, over the access point `h713` or
over the projector's LAN address (`ip -4 addr`). The page reads its state every three seconds (`h713-warp ctl status`, `h713-tv ctl status brief`, `h713-keystone status`; the `brief` matters, the full status asks the firmware and would hold the warp's frames) - three
`ctl status` calls per interval and the age of one file (a Wi-Fi change waiting for its confirmation). The
standing settings are read once and again after the verbs that change them; the Remote tab asks bluez every 10 s
while it is on the screen (every 3 s while it waits for a remote).

## What is on it

**Status**: one dense strip at the top - signal, whether the picture is the console, the video plane or the
warp, warp on/off, whether the mask is up, whether the keystone standing in the warp is the automatic's or a
hand's, which reference the automatic corrects against (`ref ideal`, `ref set` or `ref refused`), the GPU's
frames per second and every thermal zone. The eight values are in the diagram below it.

**Projection.** The keystone is a **diagram**, not a list of numbers: the panel as a dashed rectangle with
the quadrilateral the eight values make inside it, and the four corners as round handles with their names, and under the drawing one button per corner carrying
`x VALUE/MAX  y VALUE/MAX`. Tap a handle to pick it (it turns amber and, if the mask is up, is marked on the
wall with `h713-warp ctl test mask CORNER`); **drag** it and the corner follows the finger, clamped the way
`h713-warp` clamps it and sent as `ctl keystone set CORNER AXIS VALUE` - at most ten times a second while
the drag runs, and once more when it ends. Beside it a pad of four arrows for the picked corner with a step
of 1, 10 or 50 per-mille (`ctl keystone nudge`). Under it: mask on/off, auto keystone now
(`h713-keystone once --apply`), reset, screen zoom 50..100 % in steps of 5 (`h713-warp ctl zoom`, below 100 with `ctl on` if the warp is off), the
projection mode - front, rear, ceiling or rear-ceiling (`h713-warp ctl mode`; the corners keep their wall
names in every mode, the warp flips underneath and re-sorts the values so the correction stays with the housing), after a
move - off, keystone or keystone+focus (written into `/etc/h713/keystone.conf`, then `h713-keystone-auto`
restarted), focus by 5 and 20 msteps, level reference, autofocus now, warp on/off. A control whose hardware the
board does not have (`h713-features status`: camera, accelerometer, focus motor) is hidden, one line says
which, and `after_move` refuses a choice that needs it; without an answer from `h713-features` all stay.

**Picture.** The vendor presets, brightness, contrast, saturation, hue and sharpness as sliders over the
range `h713-tv ctl list` reports, the aspect fit, the firmware's zoom is not on the page any more (23.09.: `out` cropped, the DE only enlarges; the projection area is the warp's zoom under Keystone), and save.

**Projection, added.** The soft edge of the warped picture, 0..64 px (`h713-warp ctl edge`), and the test patterns
grid and border (`ctl test`; *Mask off* clears them).

**Picture, added.** Noise reduction (`tnr`, `snr`), dynamic contrast (`dci`) and black extension (`black`), each Off
to High (`h713-tv ctl set`); *Forget saved* (`ctl save off`, with a question first); under *Picture missing?* *Resync
source* and *Replug HDMI* (`ctl resync`, `ctl replug`); and *At start*, the keys `start`, `preset` and `edid_prefer` of
`tv.conf`. h713-tv reads that file once, so a change restarts the running instance (`h713-tv@videoN`, the number is
looked up with `systemctl list-units`) and asks first, because the picture is gone for a few seconds. Not on the
page: the EDID half (`block1`) and `rpc`.

**Sound.** Volume 0..100, mute on/off, audio auto/on/off. The volume is **not** kept through a restart, and nothing on
the page changes that.

**Remote.** The state of the Bluetooth remote (`h713-remote-pair status`; the name, never the address) and *Re-pair
remote*, in the four states of the mock-up: normal; a question (*Forget and re-pair* - the remote stops working over
Bluetooth, IR keeps working); waiting (*Hold LEFT + RIGHT on the remote*, the seconds left, asking bluez every 3 s
until it says connected); done (`ok paired NAME - connected`). The button runs `h713-remote-pair forget` and
`h713-osd ctl pair`, which is meant to show the same hint on the wall for 10 s; the running
`h713-remote-pair.service` then scans by itself while no remote is bonded ([TODO 2.54](../../TODO.md)). `forget` ends
with exit 1 and no output when nothing is paired: the page says so in a sentence and waits all the same. *Stop waiting*
only stops the page; the projector keeps looking. Below it `keys.conf` (`volume_step` 1..20, `focus_steps` 1..100; the
daemon reads it again by itself) and, as *Overlays*, `osd.conf` (`place`, `look`, `scale` 0.5..2, `seconds` 0.5..10; read
again too).

**Network.** The Wi-Fi form for `/etc/h713/wifi.env`: mode ap, sta or off, name, password, country, band, channel
and the access point's three addresses. **The password is never sent to the page**: the field is empty, the placeholder
says whether one is set, and an empty field keeps it (an open network therefore cannot be chosen from the page). Every
value is checked in the page's tool, then `h713-wifi check` reads the new file, and only then:

1. the old file is kept as `wifi.env.prev`;
2. a timer is set with `systemd-run --on-active=120`: it runs `h713-panel --rollback-wifi`, which puts the old file back
   and restarts `h713-wifi`. It lives in the manager, not in the panel's unit, so it survives the panel and the loss
   of the connection;
3. the new file is written and `h713-wifi` restarts. If that fails, the old file is back at once.

On the access point the phone loses the network for this, so the page cannot count on an answer: it shows a banner
on every tab, from the status, as long as a change waits - *Keep these settings* cancels the timer
(`systemctl stop h713-panel-wifi-rollback.timer`) and drops the old file. A second change is refused while one
waits. Below the form the host name (RFC 1123, 1..63 letters, digits and hyphens, one label): `hostnamectl
set-hostname` and the `127.0.1.1` line of `/etc/hosts`.

**System.** `h713-power status` as it is, the keys of `power.conf` (what the power key's 15 s countdown starts on, standby or power off, the seconds of
the long press, the remote's power key, what a refused standby does - `h713-power set`), *Restart* and *Power off*
(`systemctl`, each with a question first). The page's own password (the current one is asked for again; `panel.env`
and the running door change together). The journal in RAM or on `/data` (`h713-logs volatile|persistent`, due at the
next restart). Diagnostics, read only: `h713-tv ctl hdcp`, `h713-features status`, `h713-keys status`,
`h713-osd ctl status`, `h713-power status`, `h713-logs status`, `h713-wifi status` - the tool's own text; the
temperatures are in the strip at the top.

## On a phone and on a desktop

The same page. Below 900 px it is one column with six group buttons and one group on the screen at a
time; from 900 px on the groups stand side by side under the status strip and the group buttons disappear.
Every control is a real `<button>` or `<input>` - Tab walks the page, Enter presses, and the corner handles
are in the tab order too: with the keyboard on one of them the arrow keys nudge that corner by the chosen
step (the first arrow after the focus has moved picks the corner instead).

## Installing it

```
install -d /usr/local/lib/h713-panel
install -m 755 h713-panel /usr/local/lib/h713-panel/h713-panel
install -m 644 page.html  /usr/local/lib/h713-panel/page.html
ln -sf /usr/local/lib/h713-panel/h713-panel /usr/local/bin/h713-panel
install -m 644 h713-panel.service /etc/systemd/system/h713-panel.service
systemctl daemon-reload && systemctl enable --now h713-panel
```

The page has to stay beside the real file (the tool follows its own symlink to find it), the same rule
`h713-keystone` has for its `model/`.

## What it does not do

- **One password (since 05.10.2026).** HTTP Basic Auth, any user name; the password is made at the
  first start and kept in `/etc/h713/panel.env` (root, 0600). `h713-panel --show-password` prints it,
  the journal shows it once when it was made. `--no-auth` serves an open page for a bench and says so.
  Plain HTTP: the password crosses the home network unencrypted, which is the level of the Wi-Fi
  password itself. A reinstall of the system makes a new one (TODO 1.2b).
- **No colour calibration.** Gamma curves, the picture-mode tables and the per-board PQ data stay `h713-pq`'s.
- **No installer, no updates, no file upload, no shell.** The verb table is the whole surface.
- **Never on the page:** SSH keys, `focus_command`, `rpc`, the EDID half. A request has to carry the header
  `X-Requested-With: h713-panel` (the page sends it): the browser attaches the password to a form posted from any other
  site, and a header of its own is the one thing such a form cannot set.
- **It decides nothing itself.** If a tool is missing or refuses, the page says which one and why, in that
  tool's own words, and changes nothing. The menu control `mode` is not a slider; presets set it.

`python3 -m unittest discover -s tests -v` (or the file itself) runs the tests: the verb table, the ranges, the
refusals, the status parsing, the configuration writers, the Wi-Fi apply, confirm and fall-back, the password and the
page's own verb list, against shell scripts that stand in for the tools.

The unit's `ReadWritePaths` are `/etc/h713` and `/etc/hosts`, plus (with a leading `-`) the three places `h713-logs` writes;
the comments in `h713-panel.service` say whose write each one is.

Details: docs/tools/h713-warp.md, h713-keystone.md, h713-tv.md, h713-focus.md, h713-autofocus.md, h713-power.md,
h713-keys.md, h713-osd.md, h713-wifi.md.
