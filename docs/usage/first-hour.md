# The first hour with the device

You have installed the image ([FLASHING.md](../../FLASHING.md)) and the projector booted. This page is
the walk-through: get in, get a picture, set it up the way you want it, and know where to look when
something is off. Every command runs on the device unless it says otherwise.

## 1. Get in

Plug in power, press the power key - as with the stock firmware ([power-gate](../uboot/power-gate.md)).
Give it a moment: the display firmware and the HDMI hot-plug sequence take about 18 s from the key press
before the input is ready.

```bash
ssh root@h713          # over the access point, or over the network if you set mode=sta
```

Key-only: the key you passed as `--ssh-key` during installation is the only way in over the
network. If you skipped it, the serial console on the UART pads is your way back - it **logs in as root
without a password**, by design and by necessity ([why, and how to turn it off](../services.md)).

**Change the Wi-Fi password now**, before the device sits anywhere but on your desk. The shipped default
is in this repository, which means everyone has it:

```bash
nano /etc/h713/wifi.env        # ssid, password, country, and mode=ap|sta|off
systemctl restart h713-wifi
h713-wifi status
```

`country` is not a formality - it decides channels and transmit power. Set the country the device is
actually in ([`h713-wifi`](../tools/h713-wifi.md)).

## 2. Get a picture

Plug an HDMI source in. `h713-tv` runs as a service and switches by itself: signal → picture on the
wall, no signal → Linux console.

```bash
h713-tv ctl status             # signal, mode, plane or console, audio
h713-tv ctl list               # every picture control with its range
```

If the wall stays dark, work down this list:

| Check | Command | What it means |
|---|---|---|
| Is the service running? | `systemctl status 'h713-tv@*'` | udev starts one instance per capture device; the node number varies |
| Does the receiver see a signal? | `h713-tv ctl status` | "no signal" is also what an unsupported mode looks like |
| Is the source in a supported mode? | on the source | six modes are verified, all at 60 Hz - [STATUS.md](../../STATUS.md) |
| Just plugged the cable in and it stays dark? | `h713-tv ctl replug` | fixed since 16.09.2026 (kernel `0136a`/`0136c`); on an older image this command brings the picture back ([known-issues](../known-issues.md)) |
| Anything in the log? | `journalctl -u 'h713-tv@*' -b` | |

## 3. Make it look right

```bash
h713-tv ctl preset cinema      # standard cinema vivid game computer hdr energy_saving custom
h713-tv ctl set brightness 55  # single control, range from `ctl list`
h713-tv ctl aspect proportional
h713-tv ctl save               # remember all of it across reboots
```

Presets come from the vendor's own picture tables, computed by [`h713-pq`](../tools/h713-pq.md), not
invented by us. `save` writes your deviations to `/var/lib/h713-tv/`; `save off` forgets them again.

Sound follows the picture by default. `h713-tv ctl volume 60`, `ctl mute on`, and `ctl audio off` if you
want the speaker quiet while the picture stays.

## 4. Focus

```bash
h713-focus status              # watcher, edges, counter
h713-focus up 20               # 20 microsteps, in chunks, checked each time
h713-focus down 20
```

The motor has no position sensor, only a **range watcher**: the driver notices when the mechanism leaves
the permitted range and stops. Small steps, look at the wall, repeat - that is the whole method. There is
no autofocus ([why not](../subsystems/focus-motor.md)).

## 5. The camera

```bash
h713-cam probe                 # find the node, list formats
h713-cam grab /tmp/wall.png    # single frame
```

Useful for looking at the wall from the device itself - for instance while focusing over SSH with the
projector in another room.

## 6. Turning it off, and on again

A short press of the power key while the system runs asks systemd for a `poweroff`; the device ends up
back where it started - dark, about 4 W, waiting for the next press. `poweroff` over SSH does the same.
`reboot` skips the gate and comes straight back up, which is why a remote reboot never leaves you with a
device that needs a finger.

## 7. Keeping it up to date

The root filesystem is an ordinary Debian 13 with sources configured but no package lists baked in, so
`apt update && apt upgrade` works for Debian's own packages - over a network the device can reach, which
by default it cannot: the shipped configuration is an access point, not a client. Set `mode=sta` in
`/etc/h713/wifi.env` first.

Everything *this project* ships - kernel, U-Boot, the `h713-*` tools, the firmware placed from your dump -
is not packaged and does not come from apt. Updating those means writing a new image with the installer;
your U-Boot settings (`h713_gate`, `h713_boot`) are carried over, your dump is reused, and
`/etc/h713/wifi.env` is the one file worth copying off beforehand.

## 8. When something is wrong

```bash
journalctl -b            # this boot, everything
journalctl -u 'h713-tv@*' -b
dmesg | grep -iE 'h713|hy310|aic8800'
```

For a bug report, the useful three are: the failing command with its output, `journalctl -b` around it,
and the `.BUILD.txt` stamp of the image you installed (it names the patch series, the kernel tree and
every component hash). Report it as an issue on this repository.

## 9. Know your way out

Two things are worth doing **once, now, while everything works**:

```bash
fw_printenv                    # your U-Boot environment, on the PC side of a rescue this matters
```

and keeping the dump you made during installation. It is the only copy of your device's own firmware.
Recovery in one line: hold reset, plug in power, and the device is in FEL - the BROM cannot be
overwritten, so a broken image is always repairable from the PC ([FLASHING.md](../../FLASHING.md)).

## Where to go next

- [ROADMAP.md](../../ROADMAP.md) - what does not work yet, honestly
- [docs/known-issues.md](../known-issues.md) - what to expect and what to work around
- [docs/subsystems/](../subsystems/) - how each part actually works
