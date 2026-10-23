# h713-settings - the settings of the box, as one page on the wall

The page Android calls "Settings", in the style of the overlays: the areas on the left, the rows of the open area on the
right, white lines on an **opaque**, calm, dark ground (over a picture a translucent page cannot be read), driven by the remote.
Everything is inside a safe margin of 5 % on each side (96 px left and right, 54 px top and bottom at 1080p; a test measures
every page against it). While a value that is judged on the picture is adjusted - Brightness, Contrast, Colour, Tint, Sharpness, Gamma,
the colour temperature, the white balance and the colour of a primary, Zoom, Turn to wall, the corners by hand - the page is **one pill at the foot over the real picture** (the mockup v1's S2), so that the effect can be seen. The launcher's entry "Settings" opens it
(`/etc/h713/launcher.d/50-settings.conf`, which starts it as the transient unit `h713-settings` - its journal is kept and a second OK
cannot start a second page), Back at the top level closes it and **the launcher opens again, Settings chosen** (Home closes everything: the mode is on the wall). Everything the box can do from a shell with
`h713-... ctl` is reachable here, and **every row is one existing command or one `key = value` of a file in `/etc/h713`**:
a tool that cannot do something has no row for it. Texts on the wall are English. The look is the owner's choice S1 of
the launcher mock-up (areas left, rows right).

```
h713-settings [--area NAME] [--idle SECONDS] [--font FILE]   the page on the wall (what the launcher runs)
h713-settings --test [--size WxH] [--area NAME]              the page for the host (a build with -DH713_TEST, testsink.c): keys as lines on stdin
```

`--test` reads lines (`up down left right ok back home power volup voldown mute focusup focusdown`) and the commands `dump`
(the model as text, ending with `--`), `snap FILE` (the canvas as PAM) and `sleep MS`; it is how the host tests drive it.

## How it ends: the exit status

How the page ends is its exit status, and [h713-keys](h713-keys.md) reads it (the launcher entry `50-settings.conf` runs `systemd-run --wait` and says `return = launcher`): **Back at the top level is 0 and
the launcher opens again** with Settings chosen - Back goes one level back, and the page is one level above the launcher. Every other end leaves the wall to the mode below, so none of them is 0:

| Status | End |
|---|---|
| 0 | Back at the top level (a test run that ends at the end of its input is 0 too) |
| 10 | Home: everything closes |
| 11 | Power: the page closes, h713-power has the press |
| 12 | no key for `--idle` seconds (120) |
| 13 | the picture did not come back in time (`H713_SETTINGS_PATIENCE`, 10 s) |
| 14 | h713-osd does not answer |
| 15 | SIGTERM or SIGINT |
| 2 to 5 | the page did not open: usage, h713-osd cannot show it, no remote to hold, no font |

## How it reaches the wall and the remote

**The wall.** h713-osd is the one program that holds h713-tv's overlay channel and knows how to put a picture over the HDMI
picture - straight, or pre-distorted by the keystone's matrix - so the page claims nothing itself. It connects to h713-osd's
[page channel](h713-osd.md) (`/run/h713-osd/ctl`, `page open`): the answer carries one memfd the size of the panel (ARGB8888)
that the page maps and draws into, and `page show X Y W H` names the rows that are new. h713-osd copies or pre-distorts them
before it answers. The connection is the page's life: it ends, and the page is gone. The text is libh713osd's `osd_text`; the face
(Quicksand Medium, the `desktop` profile's `fonts-quicksand`) must be there - a page without words is not opened. The page is opened **before** it takes the
remote: when h713-osd cannot show it (no signal, not running) it does not open - nobody is deaf to a page nobody sees.
A row that changed is drawn alone and only its rectangle is shown.

**The remote.** The launcher starts its entries detached and lets go of the remote's devices, so the page opens them
itself - the Bluetooth remote (`1d5a:c081`) and the IR receiver (`sunxi-ir`), as h713-keys finds them - and holds them
alone (`EVIOCGRAB`) while it is open: Kodi under cage gets nothing from the navigation. h713-keys and h713-power see nothing
meanwhile, so the keys that matter are done here: volume (`volume_step` of `keys.conf`; louder and quieter lift a mute),
mute and the focus keys by the same commands as the rows, and a Power press goes to h713-power as the datagram h713-keys
sends (`/run/h713-power.sock`, `down`) after the remote is given back; h713-power then starts the press itself, so a 3 s hold still powers off. Home and Back at the top close the page; so does
`--idle` seconds (default 120) without a key, and a signal that goes (the page cannot be seen any more). A device that cannot
be held means no page: a page whose keys Kodi shares is worse than none.

## The keys

| Key | In the areas | In the rows | In a choice | Adjusting corners |
|---|---|---|---|---|
| Up / Down | change the area | change the row | change the option | move the corner |
| Left / Right | (Right: into the rows) | slider and switch: change the value at once; a slider judged on the picture: the first press moves it and shrinks the page to its pill | | move the corner |
| OK | into the rows | switch: flip; choice: open its options; action: run it; corners: start; a slider judged on the picture: open its pill | take the option | next corner |
| Back | close the page (exit 0: the launcher opens again) | back to the areas | cancel | done |

**The pill** (a slider judged on the picture): the label, the track and the number over the real picture, the keys under it;
Left/Right change the value, Up/Down go to the next such slider of the area (Brightness, Contrast, ...), OK or Back bring the
opaque page back. Gamma and Colour temperature are sliders with **named stops**: the track has a dot at each stop, the pill names them under
the track and says in a sentence (one line, or two when it is longer) what the stop it stands on means; the row on the page shows the word of the stop. The volume is not judged on the picture: it stays on the page. The remote's OK arrives as `KEY_ENTER` since `70-h713-remote.rules` (`KEY_OK`/`KEY_SELECT` are read the same, and so is `BTN_LEFT`, OK in the remote's mouse mode); Menu has no meaning here.
A held Left/Right arrives as a burst and goes out as **one** command. Every value acts at once; what is kept for the next boot is written as the owner of the value does it (below).

## What each row is

| Area | Row | Reads | Sends | Kept for the next boot by |
|---|---|---|---|---|
| Picture | Brightness, Contrast, Colour, Tint, Sharpness | `h713-tv ctl list` (value and range; no row if the device lacks the control) | `ctl set CONTROL N` (steps of 5) | `ctl save` once the hand has rested for 1.5 s and when the page closes, and `preset = last` in `tv.conf` (the kept values apply at the start only for the preset kept) |
| | Gamma (1.8, 2.0, 2.1, 2.2, 2.4) | `ctl get gamma` (`ok gamma = 3 (2.2)`; no row where h713-tv says the curves are not available) | `ctl set gamma N` (N = 0..4, one step per press, a held key is one command; the row shows h713-tv's answer, so a refusal shows what it holds) | `ctl save`, as above |
| | Picture mode | `ctl preset` without a name lists this device's presets; `ctl status` says the current one | `ctl preset NAME`, then the sliders are read again | as above |
| | Aspect ratio | `ctl aspect` (the list without `zoom`, which the firmware refuses) | `ctl aspect NAME` | `ctl save` |
| | Reset picture | | `ctl preset standard`, `ctl aspect auto`, `ctl set gamma 3` (2.2), `ctl save`. The colour temperature has its own Reset, on White balance | |
| White balance | Colour temperature (Auto, Warm, Normal, Cool) | `ctl get colour_temperature` (`ok colour_temperature = auto (normal)`: the row says `Auto: Normal`; for a curve the board does not have, `Warm: Normal`) | `ctl set colour_temperature NAME`; Auto follows the picture mode (Cinema and HDR warm, Vivid cool, the others normal), the other three stay when the mode changes | `ctl save`, as above |
| | Warm - Cool, Green - Magenta (-50..+50, steps of 2) | `ctl wb`: the six values; where they are not the ones the two sliders make, both show 0 | `ctl wb R G B 512 512 512`, all six in one call (the offsets as `h713-tv` holds them) | `ctl save` once the hand has rested for 1.5 s and when the page closes |
| | Reset | | `ctl wb reset` and `ctl set colour_temperature auto` (not sent when it is on Auto already), `ctl save`: Reset gives back everything this page holds | |
| Colour (not offered since 20.10.2026, see below) | Primary colour (Red, Yellow, Green, Cyan, Blue, Purple), Hue, Saturation (-100..+100, steps of 5) | `ctl cm AXIS` | `ctl set cm_AXIS_hue N` / `cm_AXIS_sat N`: a step on the picture mode's own value | as above |
| | Reset | | `ctl cm reset` (every colour), `ctl save` | |
| Keystone | Auto keystone | `after_move` in `keystone.conf` | `after_move = keystone \| off`, then `systemctl restart h713-keystone-auto` | the file |
| | Measure again now | | `h713-keystone once --apply` | |
| | Turn to wall (-30..+30 degrees) | `turn_to_wall` in `keystone.conf` | the key, then `h713-keystone once --apply`; one run at a time, a press during a run only changes the key and the run after it takes the last value | the file |
| | Adjust corners by hand | `warp.conf` | `h713-warp ctl keystone nudge CORNER AXIS ±10`, `ctl test mask CORNER` while it is open | h713-warp itself (it rewrites `warp.conf` at every change) |
| | Zoom (50-100 %) | `h713-warp ctl zoom` | `ctl zoom N` (and `ctl on` below 100, as the web page does) | h713-warp |
| | Projection | `ctl mode` | `ctl mode front \| rear \| ceiling \| rear-ceiling` | h713-warp |
| | Reset keystone | | `ctl keystone reset`, `ctl zoom 100`, `turn_to_wall = 0` | h713-warp, the file |
| Sound | Volume, Mute | `h713-tv ctl volume`, `ctl mute` | `ctl volume N` (steps of 5), `ctl mute on \| off` | the sound card's own state; the volume survives a restart, mute does not (by decision: the box is audible after a start; `doku/212` §2) |
| Focus | Autofocus now | | `h713-autofocus -q run` (the panel is the autofocus's for the length of the run) | |
| | Autofocus after a move | `after_move` | `after_move = keystone+focus` (turns the automatic keystone on too) | the file |
| | Focus by hand | | `h713-focus up \| down N` (N = `focus_steps` of `keys.conf` per press; presses during a run are counted and run next) | |
| Input | On start | `on_start` in `keys.conf` (not in the file: Launcher); no row where the image has no `/etc/h713/launcher.d` | `on_start = launcher \| hdmi \| last \| ID` | the file; h713-keys reads it at the next start of the box (`doku/213` §4). The options are Launcher, HDMI input, every `/etc/h713/launcher.d/*.conf` entry that names a `unit` (a mode: Kodi, Browser, Desktop - a new one appears with no change here; ID is the file name without its number and suffix, `20-kodi.conf` is `kodi`) and Last used (what ran when the box went off, `/var/lib/h713-keys/last-mode`). Each has its sentence under the page |
| | On the wall now | `h713-tv ctl source`, and `systemctl is-active` of each mode unit: the mode that runs by its own name; with none running, "No HDMI signal" when `h713-tv ctl status brief` has the line `nosignal        page` (h713-osd's page "No signal on HDMI" is on the wall), else "HDMI picture" | | |
| Power | Power key | `default` of `power.conf`; "Standby" only where `h713-power status` offers it | `h713-power set default standby \| poweroff` | the file |
| | Remote power key | `remote` of `power.conf` | `h713-power set remote on \| off` | the file |
| Wi-Fi | Mode, Network, Signal, Address | `wifi.env` (never the password), `iw dev wlan0 link`, `ip -4 addr` | nothing: shown only | |

**The Colour area is left out (since 20.10.2026).** The display firmware's colour manager - hue and saturation of the primaries - has no visible effect on the HY310 in any state, measured with the camera (the registers are written and read back, the picture does not change). Under the vendor's system (HY350) the value step of the same block has no effect either; hue and saturation could not be judged there, its camera sees no colour - whether they work under the vendor's system is open. The page shows eight areas; `H713_SETTINGS_COLOUR=1` brings the area back (the host tests use it), and `h713-tv ctl set cm_*` stays. White balance and colour temperature work.

Rows of hardware the board does not have (`h713-features status`: camera, accelerometer, focus motor) are hidden, not
greyed out. So are Gamma and Colour temperature where `ctl get gamma` says `is not available` (a board whose curves h713-tv could not read; the two go
together), and the White balance and Colour rows where `ctl wb` says `[not available: ...]` (another display firmware, or no
`/dev/mem`): the area then shows one line, "Not available". There are nine areas since 18.10.2026; the left column keeps the pitch
of the rows (94 design pixels) and the key hint at the foot stands under the note, so that the last area's pill stays clear of it.
Picture has nine rows with Gamma: above eight rows the pitch of the rows is 82 design pixels (73 at ten, the page's limit) and the lit pill a little lower,
so that the last row still clears the note; a page of up to eight rows is drawn exactly as before (a test compares nine areas, 234 states, picture for picture with the
build without Gamma). Warm, Normal and Cool are curves the maker measured for this panel (they come from the board's own data); the Warm - Cool and Green - Magenta
sliders are the white balance set on top of the curve. Colour temperature has no row of its own in Picture: the Picture mode row says that the mode also sets it while it is on Auto.
The white balance sliders only ever lower a gain (cool lowers red, warm lowers blue, magenta lowers green, green lowers red and
blue), 0.4 % per step, so white never clips; at one end that is 20 % off, with both sliders at the same end up to 36 %.

## Turn to wall

The sensor cannot see how far the projector stands turned to the side of the wall, so the row is a number set by eye: Right if the right side of the picture is the higher one, Left if the left side is (the pill shows L and R at the ends of its track, the middle is 0, and the number is the angle without a sign); one press is one degree, up to 30 each way. Every change writes `turn_to_wall` and runs `h713-keystone once --apply`, which takes the tilt from the sensor and the turn from the file and writes all eight corners, so the picture follows the keys, and the corners set by hand are replaced; it works with "Auto keystone" off as well, and with it on the automatic uses the value after every move. A run takes about 0.75 s on the HY310 (it took 1.9 s until the sensor was read through its IIO buffer, [h713-keystone](h713-keystone.md); measured 19.10.2026), so there is never more than one: a press while one runs only changes the key, and the run after it takes the last value; when the page ends the last value is still applied (whatever job is under way, a run of the turn, Measure again now or the autofocus, is waited for first, 3 s at most). A run that fails is a line in the journal; "Reset keystone" sets the turn to 0, and the row is hidden on a board without an accelerometer. Not measured on the HY300PRO-G-EU.

## What is not here, and why

| Wanted | Why not |
|---|---|
| Colour temperature, Gamma | Superseded 19.10.2026: both are rows now (Picture: Gamma; White balance: Colour temperature), h713-tv computes the curve at run time. Before that: `h713-tv` had no runtime control for either, the curve was loaded once at the start. The white balance rows remain the firmware's own gains on top of the colour temperature curve |
| The 33 points of the factory gamma menu | h713-tv has no command for them (they are all 0 on these boards); a row of 33 numbers is not judged on a picture, five named stops are |
| Sound output | the box has one sound path; `h713-tv ctl audio auto \| on \| off` is a policy, not an output |
| Autofocus after switching on | nothing runs the autofocus at power-on; "after a move" is what exists |
| Source (Automatic / HDMI only) | no row since 17.10.2026 (the owner): which of the two is on the wall is not a thing to choose - a program that runs is on the wall, with none it is the HDMI input. "HDMI only" undid itself with the next Kodi start, and "Automatic" read as if it had to do with the start. `h713-tv ctl source` stays a tool for tests and the web page |
| Picture to console / "HDMI auto-switch" off | `h713-tv ctl off` would put the console under the page, and the page has no picture there: nobody could switch it back |
| Wi-Fi: choose among saved networks, join a new one | `wifi.env` holds one network; a password needs an on-screen keyboard (open, not in this package) |

## Limits

- A password needs an on-screen keyboard: the Wi-Fi area shows the connection and does not change it (open).
- The corner pattern of "Adjust corners by hand" (`h713-warp ctl test mask`) is the warp's: while it is up, the page is only
  its hint line, so that the pattern is whole.
- During "Autofocus now" the panel is the autofocus's (it takes it over from h713-tv and h713-warp, chessboard on the
  console); the page is away for the length of the run (h713-osd has no overlay over the console) and comes back by itself.
- `h713-tv ctl aspect` rebuilds the picture: about half a second of console after a change of the aspect ratio.
- Measured on the HY310 on 15./16.10.2026 (`doku/212` §2): every row set and set back, a warm start keeps 14 of 15 fields, a key to a visible change takes 66.2 ms on average
  (gate 120 ms), 26 key/state cells without a double effect, the HDMI check after the whole session without a differing row. Not measured on the HY300PRO-G-EU.

Source and host tests: `userspace/h713-settings/`.
