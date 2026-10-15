# h713-settings - the settings of the box, as one page on the wall

The page Android calls "Settings", in the style of the overlays: the areas on the left, the rows of the open area on the
right, white lines on a dark translucent ground, all of it driven by the remote. It is opened from the launcher's entry
"Settings" (`launcher.d/50-settings.conf`) and closed with Back. Everything the box can already do from a shell with
`h713-... ctl` is reachable here; nothing is decided here - **every row is one existing command or one `key = value` of a
file in `/etc/h713`**, and a tool that cannot do something has no row for it. The mockup (Marco's choice S1) is
`arbeit/medien/H-desktop/mockups/launcher-einstellungen.html`; the texts on the wall are English.

```
h713-settings                  the page, on the device's display and keys (needs package H's path, see "State")
h713-settings --test [--size WxH] [--font FILE] [--area NAME]
                               the page for the host: keys as lines on stdin (up down left right ok back), plus
                               dump (the model as text, ends with "--"), snap FILE (the canvas as PAM), sleep MS
```

## The keys

| Key | In the areas | In the rows | In a choice | Adjusting corners |
|---|---|---|---|---|
| Up / Down | change the area | change the row | change the option | move the corner |
| Left / Right | (Right: into the rows) | slider and switch: change the value at once | | move the corner |
| OK | into the rows | switch: flip; choice: open its options; action: run it; corners: start | take the option | next corner |
| Back | close the page | back to the areas | cancel | done |

A held Left/Right arrives as a burst and goes out as **one** command. Every value acts at once; what is kept for the
next boot is written as the owner of the value does it (below).

## What each row is

| Area | Row | Reads | Sends | Kept for the next boot by |
|---|---|---|---|---|
| Picture | Brightness, Contrast, Colour, Tint, Sharpness | `h713-tv ctl list` (value and range; no row if the device lacks the control) | `ctl set CONTROL N` (steps of 5) | `ctl save` once the hand has rested for 1.5 s and when the page closes, and `preset = last` in `tv.conf` (the kept values apply at the start only for the preset kept) |
| | Picture mode | `ctl preset` without a name lists this device's presets; `ctl status` says the current one | `ctl preset NAME`, then the sliders are read again | as above |
| | Aspect ratio | `ctl aspect` (the list without `zoom`, which the firmware refuses) | `ctl aspect NAME` | `ctl save` |
| | Reset picture | | `ctl preset standard`, `ctl aspect auto`, `ctl save` | |
| Keystone | Auto keystone | `after_move` in `keystone.conf` | `after_move = keystone \| off`, then `systemctl restart h713-keystone-auto` | the file |
| | Measure again now | | `h713-keystone once --apply` | |
| | Adjust corners by hand | `warp.conf` | `h713-warp ctl keystone nudge CORNER AXIS ±10`, `ctl test mask CORNER` while it is open | h713-warp itself (it rewrites `warp.conf` at every change) |
| | Zoom (50-100 %) | `h713-warp ctl zoom` | `ctl zoom N` (and `ctl on` below 100, as the web page does) | h713-warp |
| | Projection | `ctl mode` | `ctl mode front \| rear \| ceiling \| rear-ceiling` | h713-warp |
| | Reset keystone | | `ctl keystone reset`, `ctl zoom 100` | h713-warp |
| Sound | Volume, Mute | `h713-tv ctl volume`, `ctl mute` | `ctl volume N` (steps of 5), `ctl mute on \| off` | the sound card's own state (not measured across a reboot yet) |
| Focus | Autofocus now | | `h713-autofocus run -q` (the panel is the autofocus's for the length of the run) | |
| | Autofocus after a move | `after_move` | `after_move = keystone+focus` (turns the automatic keystone on too) | the file |
| | Focus by hand | | `h713-focus up \| down N` (N = `focus_steps` of `keys.conf` per press; presses during a run are counted and run next) | |
| Input | Source | `h713-tv ctl source` | `ctl source auto \| hdmi` | `source =` in `tv.conf` |
| | On the wall now | the same answer | | |
| Power | Power key | `default` of `power.conf`; "Standby" only where `h713-power status` offers it | `h713-power set default standby \| poweroff` | the file |
| | Remote power key | `remote` of `power.conf` | `h713-power set remote on \| off` | the file |
| Wi-Fi | Mode, Network, Signal, Address | `wifi.env` (never the password), `iw dev wlan0 link`, `ip -4 addr` | nothing: shown only | |

Rows of hardware the board does not have (`h713-features status`: camera, accelerometer, focus motor) are hidden, not
greyed out.

## What is not here, and why

| Wanted | Why not |
|---|---|
| Colour temperature, Gamma | `h713-tv` has no runtime control for either (the curve is loaded once at the start) |
| Sound output | the box has one sound path; `h713-tv ctl audio auto \| on \| off` is a policy, not an output |
| Autofocus after switching on | nothing runs the autofocus at power-on; "after a move" is what exists |
| Picture to console / "HDMI auto-switch" off | `h713-tv ctl off` would put the console under the page, and the page has no picture there: nobody could switch it back |
| Wi-Fi: choose among saved networks, join a new one | `wifi.env` holds one network; a password needs an on-screen keyboard (open, not in this package) |

## Tests

`make host OSD=...` and `make test` (in the container `h713-build`): `tests/test_settings.py` runs the program against a
fake `h713-tv` and `h713-warp` on Unix sockets (their answers copied from the daemons' source), stand-in tools and a
temporary `/etc/h713`. What a row sends is read from the fakes' logs, what it keeps from the files; one test renders the page and
checks where the pill, the outline and the slider land. `H713_TEST_FONT` names a font (default DejaVu Sans if present).

## State

The model, the commands, the files and the drawing are done and tested on the host. The device's own key input and display
path belong to package H (launcher, text, input) and are wired in where H has decided them; until then the program refuses to
start without `--test`.
