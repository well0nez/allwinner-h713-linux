# The first hour with the projector

You have installed the image ([FLASHING.md](../../FLASHING.md)). This page is the walk-through: switch
it on, get a picture, set it up, and know where to look when something is off. Commands run on the
projector over SSH unless they say otherwise.

## 1. Switch it on

Plug in power and press the power key: the projector waits in the dark until you do, as with the
stock firmware. About 8 s later the launcher stands on the wall, a second later the HDMI input is
ready ([the launcher](../guides/launcher.md)). The stock remote works from the first press over
infrared; pair it over Bluetooth once with Left + Right for the air mouse
([the remote](../guides/remote.md)).

![The launcher after a start](../images/launcher/launcher.png)

## 2. Get in

```bash
ssh root@hy310          # the HY300PRO-G-EU is called hy300pro; over the access point or your network
```

Key-only: the key you passed as `--ssh-key` during installation is the only way in over the network.
Without it, the serial console on the UART pads logs in as root without a password
([why, and how to turn it off](../services.md)).

**Change the Wi-Fi password now.** The shipped default (access point `h713`, password `magcubic`) is
in this repository, so everyone has it:

```bash
nano /etc/h713/wifi.env        # ssid, password, country, mode=ap|sta|off
systemctl restart h713-wifi
```

`country` decides channels and transmit power; set the one the projector stands in
([h713-wifi](../tools/h713-wifi.md)).

## 3. Get a picture

Plug an HDMI source in and choose **HDMI input** in the launcher. Without a signal the wall says
"No signal on HDMI"; with one the picture is there within a second. If it stays dark:

| Check | Command | What it means |
|---|---|---|
| Does the receiver see a signal? | `h713-tv ctl status` | "no signal" is also what a mode the display firmware does not lock looks like; a refused mode is named with its size and rate |
| Is the source in a mode that locks? | | 1080p at 60, 50 and 24 Hz, 720p50, 576p50, 1366x768, 1024x768 and 4K30 are verified ([STATUS.md](../../STATUS.md)) |
| Anything in the log? | `journalctl -u 'h713-tv@*' -b` | |

## 4. Make it look right

**Settings** in the launcher, area **Picture**: the vendor's picture modes, brightness, contrast,
colour, tint, sharpness, gamma; **White balance**: the colour temperature and two sliders. A value you
judge on the picture shrinks the page to one pill over the real picture
([the settings page](../guides/settings.md)). Everything is kept for the next boot. The same, with the
keystone as a drawing, is the web page at `http://<the projector>:8080/`
([the settings as a web page](../guides/settings-page.md); the password is
`h713-panel --show-password`).

## 5. Square it up and focus

**Keystone** in the settings: the corners by hand, the zoom, the projection mode, or the automatic
after a move ([keystone](../guides/keystone.md)). The two focus keys on the remote move the focus in
steps of 20, and the arrow turns red at the end of the travel; **Focus, Autofocus now** does the
search with the camera on a board that has one ([autofocus](../guides/autofocus.md)).

## 6. Kodi, the desktop, the browser

The three other entries of the launcher. Kodi plays with hardware decoding up to 4K HEVC; the desktop
is a terminal and a menu; the browser is Firefox. Home brings the launcher back over any of them, and a
program that ends brings it back by itself ([h713-desktop](../tools/h713-desktop.md)).

## 7. Switching off

A short press of the power key shows the 15 s countdown, a long press switches off at once. Off is the
dark gate at 2.9 W; the key or either remote's power key starts the projector again. There is no
standby in this release ([switching off and on](../guides/power.md)).

## 8. Keeping it up to date

The root filesystem is an ordinary Debian 13: `apt update && apt upgrade` works once the projector can
reach the internet (`mode=sta` in `wifi.env`). Everything this project ships - kernel, U-Boot, the
`h713-*` tools - comes with a new image: install it over the old one with `h713-install`, which reuses
your device's own files and carries `h713_gate` and `h713_boot` over. Check `fw_printenv h713_gate`
afterwards and set it to `1` if a `0` came along (`TODO.md` 2.137). `/etc/h713/wifi.env` is the one
file worth copying off before.

## 9. When something is wrong

```bash
journalctl -b
dmesg | grep -iE 'h713|hy310|aic8800'
```

For a bug report: the failing command with its output, `journalctl -b` around it, and the
`.BUILD.txt` stamp of your image. The known problems of this release: [known issues](../known-issues.md).

## 10. Know your way out

Keep the dump you made during installation; it is the only copy of your device's own firmware.
Recovery: hold reset, plug in power, and the device is in FEL. The BootROM cannot be overwritten, so a
broken image is always repairable from the PC ([FLASHING.md](../../FLASHING.md)).
