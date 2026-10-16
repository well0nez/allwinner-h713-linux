# h713-keys - the stock remote's keys

One script, `h713-keys`, Python 3, without dependencies; a daemon run by `h713-keys.service`. It gives the
stock remote's keys their meaning on our image - over Bluetooth (the BLE remote 1d5a:c081, kernel 0169) and
over IR (the `sunxi-ir` receiver with the keymap `rc-h713-fd02`, kernel 0254):

| Key | Does |
|---|---|
| louder / quieter | `h713-tv ctl volume N`, `volume_step` per press (default 5 of 0..100); both lift a mute first |
| mute | toggles `h713-tv ctl mute on/off` |
| focus up / down (`KEY_F4` / `KEY_F5`) | `h713-focus up/down N`, `focus_steps` per press (default 20, about 0.3 s of travel); one run at a time, presses during a run wait for the next (at most two), a held key keeps it going; at the end of the travel the overlay says so and nothing more is queued that way; the edge picture is the other direction's (a run up ends with `focus down edge`, a run down with `focus up edge`: Marco's eye at the wall, 16.10.2026) |
| `input_keys` (none by default) | switches `h713-tv` between the HDMI picture (`auto`) and the console (`off`) - the way back after someone forced the console; which key does it is still open, the remote has no record key |
| power | nothing here: logind, or `h713-power` on an image with standby, powers off |
| Home | opens the **launcher** (below); with it open Up, Down, OK, Back, Home and Power are the launcher's |
| Menu, Back, arrows, OK | recognised and logged once with the launcher closed (they are Kodi's); OK arrives as `KEY_ENTER` and Menu as `KEY_COMPOSE`, see `70-h713-remote.rules` (below), and `KEY_ENTER` is read as `KEY_OK` |
| mouse, microphone over IR (`KEY_F6`) | both send the same code `0x0266` - over IR they only ask for the Bluetooth pairing; logged once. Their own functions work over Bluetooth only |

After each action it sends one line to the overlay daemon `h713-osd` (`/run/h713-osd/ctl`), if that runs:
`volume N`, `mute on|off N`, `focus up|down [edge]`, `input console|hdmi`. Without it nothing is shown and
nothing fails; the action never waits for the overlay.

```
h713-keys status         # the configuration, the remote's devices, whether h713-tv and h713-osd answer
h713-keys run            # what the unit runs
```

## The launcher (Home)

Home opens a page with a ground over the whole panel and the list on the left, drawn by `h713-osd` (its `launcher`
command), Up and Down move, OK does what the entry says, Back and Home close, volume, mute and focus work as always. The entries are
the files `/etc/h713/launcher.d/NN-name.conf` (`label`, `icon`, `unit` or `exec`, `show`, `active`, `now`, `group`, `fallback`;
`rootfs/overlay-desktop/etc/h713/launcher.d/` has the three: HDMI input, Kodi, Standby; the format is in
[docs/tools/h713-keys.md](../../docs/tools/h713-keys.md)). While it is open the remote's two devices are **grabbed**
(`EVIOCGRAB`, taken at the release of Home: grabbed earlier, cage would hold Home down and Kodi repeat it), so Kodi, which reads them through cage, gets no key; it opens only where `h713-osd` can show it and closes by
itself after 90 s. A Power press with it open closes it and goes on to `h713-power` (a datagram `down`: h713-power starts the press, so a 3 s hold still powers off).

At the start of the box the launcher opens by itself (`on_start = launcher` in `keys.conf`, the default; `hdmi` keeps the HDMI picture): once per boot (`/run/h713-keys.booted`), as soon as `h713-osd` can show it
(tried every 5 s for 180 s), with the devices held at once, and it waits for the first key. A standby brings back the mode from before, not the launcher. The settings page writes the line (Input > On start).

## Only the remote

It opens only the BLE remote (by its USB ids) and the IR receiver (by its input name), never a keyboard that
happens to have F4 or a volume key. It does not grab the devices (`EVIOCGRAB`) except for the launcher: `h713-power` and logind
read the power key from the same nodes. A remote that connects later is found within 5 s.

## Configuration

`/etc/h713/keys.conf`, read again when it changes (checked every 5 s), no restart:

```
volume_step = 5          # 1..20
focus_steps = 20         # 1..100
input_keys =             # kernel key names, separated by spaces; empty = none
on_start = launcher      # launcher | hdmi: what the projector shows when it has started
```

A line it does not understand is logged as a warning and ignored; the rest keeps working. On a board without a
focus motor `h713-focus` ends with exit 7; from then on the focus keys do nothing, and the journal says so once.

A key without a meaning here is logged once with its name and code (`journalctl -u h713-keys`) - that is how
a key's code is read on the device, no `evtest` needed.

## Tests

`make test` runs the host tests (`tests/test_keys.py`, stdlib only, about 3 s): a fake `/sys` and `/dev/input`,
fake `h713-tv` and `h713-osd` sockets, a fake `h713-focus` and `systemctl`, a datagram socket for h713-power; the launcher's
tests replace `grab` (a plain file cannot be grabbed). The environment variables `H713_KEYS_ROOT`, `H713_KEYS_TV`,
`H713_KEYS_OSD`, `H713_KEYS_FOCUS`, `H713_KEYS_SYSTEMCTL` and `H713_KEYS_POWER` point the script at them;
`H713_KEYS_TRACE=1` adds a journal line per key with the kernel's stamp and the read time (measured 15.10.2026: Home to the page 52.7 ms with HDMI, 81.8 ms with Kodi, doku/212).

## State

Measured on the HY310 on 11.10.2026 over IR (kernel 0252-0254): all 14 keys arrive and act - volume, mute,
focus, OK, Home, Menu, Back, the arrows; mouse and microphone both `0x0266`. On the HY300PRO-G-EU (11.10.,
`doku/195`): 13/13 over IR, all keys over Bluetooth, where a held key repeated every ~40 ms - the daemon now sets the
Bluetooth remote to the IR receiver's 500/125 ms (`EVIOCSREP`; host tests, not yet felt on the device). Not measured
yet: which way `KEY_F4` turns the focus on the wall, and which key should switch the input.

Installation: `make install DESTDIR=<rootfs>` (script to `/usr/local/sbin`, unit, `keys.conf`, this README).
More: [docs/tools/h713-keys.md](../../docs/tools/h713-keys.md).
