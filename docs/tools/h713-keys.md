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
| Home, Menu, Back, arrows, OK | logged once as "recognised, no action yet" |
| `KEY_F6` (IR `0x0266`: the mouse **and** the microphone key) | logged once. Over IR both keys send this one code, the vendor's `PRJ_BRC_PAIR`: they ask for the Bluetooth pairing, and a second later the remote offers itself (measured 11.10.2026); their own functions run over Bluetooth only |

Volume and mute work without an HDMI signal: `h713-tv` keeps them as long as its two sound cards are there.

## Why it reads only the remote

A keyboard on the USB port has F4, F5 and volume keys too, and someone typing in the console should not
move the focus motor. The daemon opens only the BLE remote (ids `1d5a:c081`) and the IR receiver (input
name `sunxi-ir`), and finds a remote that connects later at its next look, every 5 s. It does not grab the
devices: the power key on the same nodes stays with logind or `h713-power`.

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
