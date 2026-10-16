# h713-keys - the stock remote's keys

`h713-keys` gives the stock remote's keys their meaning on our image: volume and mute through `h713-tv`, the
focus through [h713-focus](h713-focus.md), and - once a key is chosen for it - one key that switches between the
HDMI picture and the console. It reads the Bluetooth LE remote and the IR receiver alike; a dependency-free
Python 3 daemon, run by `h713-keys.service`. Source and the key table: `userspace/h713-keys/README.md`.

```
h713-keys status         # configuration, the remote's input devices, whether h713-tv and h713-osd answer
h713-keys run            # what the unit runs
```

## Which key does what

| Key (kernel name) | Action |
|---|---|
| `KEY_VOLUMEUP` / `KEY_VOLUMEDOWN` | `h713-tv ctl volume N` in steps of `volume_step`; both lift a mute first (the owner's choice of 11.10.2026) |
| `KEY_MUTE` | toggles `h713-tv ctl mute`; held down it does not repeat |
| `KEY_F4` / `KEY_F5` (the BLE remote's focus keys, kernel 0169; IR 0x0251/0x0250) | `h713-focus up/down` with `focus_steps`; one run at a time, presses during a run wait for the next (at most two presses' worth, so a held key keeps the motor going and it stops one run after the release), a press the other way replaces what was waiting. At the end of the travel (`h713-focus` exit 3) the overlay shows the end stop and nothing more is queued that way |
| `input_keys` (none by default) | `h713-tv ctl off` (console) when the picture is on automatic, `h713-tv ctl auto` otherwise. The remote has no record key; which key gets this is open |
| `KEY_POWER` | left alone: logind powers off, or [h713-power](h713-power.md) decides on an image with standby |
| `KEY_HOMEPAGE` | opens the launcher (below); with it open Up, Down, OK, Back, Home and Power are the launcher's |
| Menu, Back, arrows, OK | with the launcher closed: logged once as "recognised, no action yet" (they are Kodi's); OK arrives as `KEY_ENTER` and Menu as `KEY_COMPOSE` (the udev rule below) and is read as `KEY_OK` |
| `KEY_F6` (IR `0x0266`: the mouse **and** the microphone key) | logged once. Over IR both keys send this one code, the vendor's `PRJ_BRC_PAIR`: they ask for the Bluetooth pairing, and a second later the remote offers itself (measured 11.10.2026); their own functions run over Bluetooth only. Nothing acts on it: `h713-remote-pair` pairs only while no remote is bonded - a remote paired with another box since needs `h713-remote-pair forget`, then Left+Right (TODO 2.54) |

Volume and mute work without an HDMI signal: `h713-tv` keeps them as long as its two sound cards are there.

## The launcher (Home)

Measured on the HY310 on 15.10.2026 (`doku/212` §1): ten switches HDMI -> Kodi -> HDMI, Kodi taking no key while the page is open, the selection
answered in 52.7 ms over HDMI and 81.8 ms over Kodi, 35 of 35 standbys from every way in. `KEY_HOMEPAGE` opens an **opaque page** over the whole panel (Marco, 15.10.2026: it must have a ground, it is not an overlay over the picture; the picture goes on behind it) with the list on the left - the mock-up's "Launcher C":
a header line with the time and what runs (`20:47 - HDMI 1080p60`, `Kodi`), the entries, set apart at the foot Standby, and
`select / OK open / BACK close`. h713-osd draws it (`launcher ...` on its socket, [h713-osd](h713-osd.md)); h713-keys is the
controller. **Up/Down** move (no wrapping), **OK** does what the entry says and closes, **Back** and **Home** close, a
**Power** press closes it and hands the press to [h713-power](h713-power.md) (a datagram `down`, `H713_KEYS_POWER`: h713-power starts the press, so a 3 s hold still powers off), volume,
mute and focus work as always. It closes by itself after 90 s without a key, and at once when h713-osd no longer shows it (a restart
under an open launcher): a move, and OK before it starts a row, must be answered `ok` by h713-osd, else the launcher is closed and the
grab let go, and nothing is started blind.

**Nothing happens twice.** While the launcher is open h713-keys holds the remote's two devices with `EVIOCGRAB`, so Kodi (which
reads them through cage and libinput) gets no key at all; closed, it lets go and everything is as it was. The press of Home
that opens it still reaches Kodi first, so the Kodi keymap maps `homepage` and `browser_home` to nothing
(`rootfs/overlay-desktop/.../keymaps/h713-power.xml`; Kodi names the key `browser_home`). **The grab waits for the release of
Home** (measured at the HY310, 15.10.2026, gate H2): grabbed with Home still down, the release never reached cage, cage held Home
down, and Kodi - which repeats a key it never saw released - got a `browser_home` 30 times a second for as long as the launcher was
open (harmless, mapped to noop, but not "no key"). The page is on the wall at the press; the keys are the launcher's from the release
on (a Down pressed within the ~100 ms in between would reach both). It opens only where h713-osd can show it: without a signal (the console)
or without h713-osd it answers `ok unseen`/nothing and h713-keys does not take the keys from anybody. A remote that connects
while it is open is held at once.

**The entries are files**, `/etc/h713/launcher.d/NN-name.conf`, sorted by name (a package adds its own and touches no code):

```
label    = Kodi                  # English, what is written on the wall
icon     = film                  # hdmi film globe desk sliders power (libh713osd)
unit     = h713-kodi.service     # OK: systemctl start --no-block (a "mode"; h713-mode ends it before a sleep and starts it after)
exec     = /usr/local/sbin/h713-mode hdmi    # or: a command, run detached (no shell)
show     = /usr/local/sbin/h713-power can-standby    # optional: the entry exists only if this exits 0
active   = /usr/bin/systemctl is-active --quiet h713-kodi.service    # optional: exits 0 while this entry is what runs
now      = Kodi                  # the header while it is active (default: the label); {signal} = 1080p60 from h713-tv
group    = end                   # the foot: Standby is set apart, bottom-anchored, and comes last
fallback = yes                   # the current entry when no other `active` check succeeds (the HDMI input)
```

Up to six entries fit the picture (the mock-up's: HDMI input, Kodi, Browser, Desktop, Settings, Standby); the selection starts
on the entry that is active. A file without label, icon and unit or exec is left out with a journal warning. `H713_KEYS_TRACE=1` adds a journal line per key with the kernel's stamp and the read time (gate HL).

## OK and Menu below code 248 (`70-h713-remote.rules`)

The remote's OK is `KEY_OK` (352) over IR and `KEY_SELECT` (353, HID "Menu Pick" `0x0c0041`) over Bluetooth; its Menu is `KEY_MENU` (139, `0x0c0040`).
xkb names evdev codes only up to 247, so cage's libinput hands a Wayland client no key above that, and `KEY_MENU`'s keysym (`XF86MenuKB`) is one Kodi does not know:
with the stock codes OK and Menu never reached Kodi (gate H2, 15.10.2026), and would not reach labwc or Firefox either. The rule
`/etc/udev/rules.d/70-h713-remote.rules` (installed with h713-keys) lets udev's `keyboard` builtin change the codes in the kernel, as hwdb's `KEYBOARD_KEY_` does:
OK becomes `KEY_ENTER` (28, Return to every client) and Menu `KEY_COMPOSE` (127, keysym Menu, the context-menu key). IR matches by the device name `sunxi-ir`
(scancodes `0x20b`, `0x21e` of the keymap `rc-h713-fd02`), Bluetooth by the ids 1d5a:c081. h713-keys reads `KEY_ENTER` as OK (and still `KEY_SELECT`/`KEY_OK`, should the
rule not have run); h713-power took `KEY_ENTER` for OK already. `udevadm trigger --subsystem-match=input --action=change` applies the rule to a running box.

## Why it reads only the remote

A keyboard on the USB port has F4, F5 and volume keys too, and someone typing in the console should not
move the focus motor. The daemon opens only the BLE remote (ids `1d5a:c081`) and the IR receiver (input
name `sunxi-ir`), and finds a remote that connects later at its next look, every 5 s. It does not grab the
devices except while the launcher is open: the power key on the same nodes stays with logind or `h713-power`.

A held key repeats the same way over both: the IR receiver repeats after 500 ms every 125 ms (rc-core), and the
daemon gives the Bluetooth remote those values when it opens it (`EVIOCSREP`; the journal line "listening on ...,
repeat 500/125 ms as over IR"). Left at the input core's 250/33 ms, a held volume key ran from 100 to 15 in 1.6 s
(measured on the HY300PRO-G-EU, `doku/195`).

## The overlay

After each action one line goes to `/run/h713-osd/ctl`, the control socket of the overlay daemon
[h713-osd](h713-osd.md): `volume N`, `mute on N` / `mute off N`, `focus up|down [edge]`,
`input console|hdmi`. When the socket is not there, nothing is sent and nothing is logged; the action never
waits for the overlay.

## IR

The IR receiver (`sunxi-cir`, `r_ir`) decodes with kernel 0252-0254. Before 0252 the device tree gave it
24 MHz, and the driver's integer arithmetic turned the 2.667 us sample into 2 us: every pulse reached rc-core
at 0.75 of its length, and NEC never decoded (measured 02.10.2026, leader 6752/3348 us instead of
9000/4500). Without the property the driver runs at 8 MHz, an exact 8 us. 0253 removes the vendor register
values of 0021, which belonged to the vendor's own sample model. 0254 adds the keymap `rc-h713-fd02`
(NEC customer code 0xfd02, scancode = address << 8 | command), built into the kernel and named in the
HY310 device tree, which the HY300PRO-G-EU's includes. The table comes from the stock firmware; seven
navigation keys were tested on the HY300PRO-G-EU on 03.10.2026 (`doku/138`).

The pin sleep state and the re-apply of PL9 from the IR package of 03.10. are not part of it: they answered
the vendor's ARISC firmware, which disabled PL8/PL9 when it started. crust leaves PL9 to Linux (measured
11.10.2026 on the HY310: PL9 function 3, `s_cir`).

## Configuration

`/etc/h713/keys.conf`, read again when it changes, no restart:

| Key | Default | Range |
|---|---|---|
| `volume_step` | 5 | 1..20 of h713-tv's 0..100 |
| `focus_steps` | 20 | 1..100 msteps; one mstep is about 16 ms of travel (`h713-autofocus`), the sharp range several hundred wide (`doku/94`) - 3 was too little to see (Marco, 11.10.2026) |
| `input_keys` | (none) | kernel key names, separated by spaces |

A line it does not understand is a warning in the journal; the other lines still count. On a board without a
focus motor `h713-focus` ends with exit 7 (the device node decides, as for every tool,
[h713-features](h713-features.md)); after the first such exit the focus keys do nothing.

Every other key - not handled, not power - is logged once with its name and code, `journalctl -u h713-keys`:
that is the measuring tool for a key whose code is not known.

## State

Measured on the HY310 on 11.10.2026 over IR, with kernel 0252-0254: all 14
keys arrive, decode and act - volume, mute, focus, OK, Home, Menu, Back, the arrows; NEC frames clean (leader
9.0/4.4 ms, bits 560-650 us). The noise filter of the vendor (`NTHR` about 100 us instead of mainline's 8 us) was
tried and is not needed: 5/5 with either. Host tests: `make test` in `userspace/h713-keys`.

Not measured separately: the Bluetooth side with this daemon (the owner's presses on 11.10. came over IR, the
remote reconnected over Bluetooth only at the end); which way `KEY_F4` turns the focus on the wall (both
readings were seen, 02.10. and 03.10.), and which key should switch the input. In the image since 11.10.2026 (`rootfs/install-projekt.sh` 5i, enabled).
