# h713-settings - the settings of the box, as one page on the wall

The page Android calls "Settings", in the style of the overlays: the areas on the left, the rows of the open area on the
right, white lines on a dark translucent ground, driven by the remote. The launcher's entry "Settings" opens it
(`/etc/h713/launcher.d/50-settings.conf`, which starts it as the transient unit `h713-settings` - its journal is kept and a second OK
cannot start a second page), Back at the top level closes it. Everything the box can do from a shell with
`h713-... ctl` is reachable here, and **every row is one existing command or one `key = value` of a file in `/etc/h713`**:
a tool that cannot do something has no row for it. Texts on the wall are English. The look is the owner's choice S1 of
the mockup `arbeit/medien/H-desktop/mockups/launcher-einstellungen.html` (areas left, rows right).

```
h713-settings [--area NAME] [--idle SECONDS] [--font FILE]   the page on the wall (what the launcher runs)
h713-settings --test [--size WxH] [--area NAME]              the page for the host: keys as lines on stdin
```

`--test` reads lines (`up down left right ok back home power volup voldown mute focusup focusdown`) and the commands `dump`
(the model as text, ending with `--`), `snap FILE` (the canvas as PAM) and `sleep MS`; it is how the host tests drive it.

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
sends (`/run/h713-power.sock`, `short`) after the remote is given back. Home and Back at the top close the page; so does
`--idle` seconds (default 120) without a key, and a signal that goes (the page cannot be seen any more). A device that cannot
be held means no page: a page whose keys Kodi shares is worse than none.

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

## Limits

- A password needs an on-screen keyboard: the Wi-Fi area shows the connection and does not change it (open).
- The corner pattern of "Adjust corners by hand" (`h713-warp ctl test mask`) is the warp's: while it is up, the page is only
  its hint line, so that the pattern is whole.
- During "Autofocus now" the panel is the autofocus's (it takes it over from h713-tv and h713-warp, chessboard on the
  console); the page is away for the length of the run (h713-osd has no overlay over the console) and comes back by itself.
- `h713-tv ctl aspect` rebuilds the picture: about half a second of console after a change of the aspect ratio.
- Not measured on a device: see the report (`arbeit/medien/S-einstellungen/BERICHT.md`).

Source and host tests: `userspace/h713-settings/`.
