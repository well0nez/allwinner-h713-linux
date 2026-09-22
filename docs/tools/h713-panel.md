# h713-panel - the projector's settings page

`h713-panel` is the projector's own web page: opened on a phone over the projector's Wi-Fi or in a browser
over the LAN, it carries the entries of the vendor's "Projection Settings" and "Display settings" - in our
own style, not a copy. One dependency-free Python 3 script plus the page beside it, no framework, no build
step, nothing fetched from the internet.

**Nothing is decided in the page.** Every button is one command this project already has, and the first
`ok`/`error` line of that command's answer is what appears at the bottom of the screen. The browser never
names a command: it names a verb out of a fixed table, the arguments are checked against their ranges, and
the argument vector goes to `subprocess` without a shell.

```
h713-panel [--port 8080] [--address ADDR] [--tools DIR] [--page PATH]
```

## How to reach it

After `systemctl enable --now h713-panel`: `http://<the projector>:8080/`, over the access point `h713` or
over the projector's LAN address (`ip -4 addr`). The page reads its state every three seconds - three
`ctl status` calls per interval, and nothing else while it sits open.

## What is on it

**Status**: one dense strip at the top - signal, whether the picture is the console, the video plane or the
warp, warp on/off, whether the mask is up, whether the keystone standing in the warp is the automatic's or a
hand's, the GPU's frames per second and every thermal zone. The eight values are in the diagram below it.

**Projection.** The keystone is a **diagram**, not a list of numbers: the panel as a dashed rectangle with
the quadrilateral the eight values make inside it, and the four corners as round handles carrying
`x VALUE/MAX  y VALUE/MAX`. Tap a handle to pick it (it turns amber and, if the mask is up, is marked on the
wall with `h713-warp ctl test mask CORNER`); **drag** it and the corner follows the finger, clamped the way
`h713-warp` clamps it and sent as `ctl keystone set CORNER AXIS VALUE` - at most ten times a second while
the drag runs, and once more when it ends. Beside it a pad of four arrows for the picked corner with a step
of 1, 10 or 50 per-mille (`ctl keystone nudge`). Under it: mask on/off, auto keystone now
(`h713-keystone once --apply`), reset, screen zoom 50..100 % in steps of 5 (`h713-warp ctl zoom`), after a
move - off, keystone or keystone+focus (written into `/etc/h713/keystone.conf`, then `h713-keystone-auto`
restarted), focus by 5 and 20 msteps, level reference, autofocus now, warp on/off.

**Picture.** The vendor presets, brightness, contrast, saturation, hue and sharpness as sliders over the
range `h713-tv ctl list` reports, the aspect fit, the firmware zoom (`ctl zoom in F | out P | off`, refused
while the warp draws - the refusal is shown as it comes), and save.

**Sound.** Volume 0..100, mute on/off, audio auto/on/off.

## On a phone and on a desktop

The same page. Below 900 px it is one column with three group buttons and one group on the screen at a
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

- **No authentication.** Whoever reaches port 8080 can set the picture: the Wi-Fi password is the door, and
  on a LAN there is no door at all. It belongs on a network you own.
- **No colour calibration.** Gamma curves, the picture-mode tables and the per-board PQ data stay `h713-pq`'s.
- **No installer, no updates, no file upload, no shell.** The verb table is the whole surface.
- **It decides nothing itself.** If a tool is missing or refuses, the page says which one and why, in that
  tool's own words, and changes nothing. The menu control `mode` is not a slider; presets set it.

`python3 -m unittest discover -s tests -v` runs the tests: the verb table, the ranges, the refusals, the
status parsing and the page's own verb list, against shell scripts that stand in for the five tools.

Details: docs/tools/h713-warp.md, h713-keystone.md, h713-tv.md, h713-focus.md, h713-autofocus.md.
