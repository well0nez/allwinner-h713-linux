# Installing on a device

From a Linux PC, over one USB cable. The projector never has to be opened, and nothing is written to it
until you have a dump of what was there before.

> **Before anything else.** Installing replaces Android. The display firmware, the ARISC firmware, the
> Wi-Fi firmware and the picture tables are proprietary — the same files on every device of this model, but
> ours to neither ship nor pass on, so the installer reads them out of your own dump. Your device's secure
> storage is the part that really exists only once: HDCP keys, MAC addresses, serial number. If you skip
> the dump and the install fails, nobody can give you any of it back. Take the **full** dump (7.3 GB) the first time and keep it somewhere safe. The small
> dump (49 MiB) is enough for every *later* run on the **same** device, because it carries the parts that
> differ per unit — secure storage, `private`, `Reserve0`. It is not enough to put Android back, and it is
> not enough for a device you have never dumped in full.

## What you need

- The projector, its power supply, and a **USB A-to-A cable** to the PC.
- Linux with Python 3.9+. No extra packages. (Windows works in principle — the installer is written for
  it and refuses nothing — but **nobody has run the Windows path**. Treat it as untested.)
- An image: from a release tag if there is one for your version, otherwise built yourself with
  `release/build-all.sh` ([BUILDING.md](BUILDING.md); the first time also
  [docs/build-container.md](docs/build-container.md)). Building takes about 20 minutes and needs no device.
- Your public SSH key. Without it the installed system has **no** SSH access, only the serial console:
  the image deliberately ships no key.

## The four steps

```bash
# 1. put the device into FEL: hold the reset button, then plug in power
# 2. run the installer (it loads U-Boot over USB — nothing is written yet)
installer/hy310-install.py \
    --abbild out/h713-hy310-v0.5-beta.tabelle.json \
    --authorized-key ~/.ssh/id_ed25519.pub \
    --abzug voll --sicherung ~/hy310-dump
# 3. it dumps, extracts your device's own files, fills the image, writes it, verifies
# 4. power off, power on — and press the power key
```

U-Boot exposes the eMMC as a normal USB drive; that is how the PC reads and writes it. The only way out
of that mode is a power cycle, which is also the end of the procedure.

The installer types nothing for you: before it writes, it asks you to type `JA`. It also refuses to run
if it does not recognise the device, so a stranger's firmware cannot be guessed at (`--ohne-erkennung`
exists for development and is exactly as dangerous as it sounds).

## After the first boot

Plug in power, then press the power key — the same as with the stock firmware. Until you press it the
device waits at about 4 W with a red LED. Reproducing that behaviour took work
([docs/uboot/power-gate.md](docs/uboot/power-gate.md)); if you would rather have the device boot the
moment it gets power, `fw_setenv h713_gate 0` gives you that.

Then, over the network:

```bash
ssh root@h713           # key-only; the Wi-Fi access point is up by default
h713-tv ctl status      # HDMI input service
```

The default access point is **published in this repo** — its SSID and password are the same on every
device that installs the image unchanged. Change them in `/etc/h713/wifi.env` before the device stands
anywhere but on your own desk ([docs/tools/h713-wifi.md](docs/tools/h713-wifi.md)).

## Useful variants

| Task | Command |
|---|---|
| Only make a dump, write nothing | `--nur-abzug --abzug voll` |
| Reinstall, keeping your U-Boot settings | (default: `h713_gate` and `h713_boot` are carried over) |
| Reinstall, discarding them | `--env-neu` |
| Reuse an extraction you already have | `--vendor <dir from h713-extract>` |
| Go back to your own dump | `--restore <full dump>` |
| Go back to stock Android | `--restore-stock UPDATE.IMG` |
| Rehearse without writing | `--dry-run` |

`--restore-stock` rebuilds the vendor partition table byte-for-byte, so the device comes back as a normal
Android projector. It has been used on hardware; it is the way back.

## If something goes wrong

- **The device is not found in FEL.** Hold reset *before* applying power and keep holding it. Check with
  `sunxi-fel version`. Note that with the A-to-A cable plugged in, the device is powered from USB, so a
  switched socket will not restart it — unplug the cable first.
- **You already wrote a broken image.** FEL is in the BROM and cannot be bricked from software. Put the
  device back into FEL and run the installer again, or `--restore` your dump.
- **The device stays dark after installing.** Press the power key (see above) before assuming the worst.
- **No SSH.** You did not pass `--authorized-key`, or the key file was the private one. The serial console
  on the UART pads still works — and it logs in as root without a password, which is the point
  ([docs/services.md](docs/services.md)).
- **SSH warns that the host key changed.** Expected after every install: the new system generates its own
  host keys on first boot, so two devices from one image are not twins. Remove the old entry
  (`ssh-keygen -R <address>`) and reconnect.

## What is written where

The image is three files with a **gap** in the middle. The gap sits exactly over the secure storage area
(LBA 12288–14335), which holds per-device material including the HDCP keys. Nothing in this project ever
writes there — not even a hand-typed `dd`, because there is no file to write. Layout:
[docs/subsystems/emmc-layout.md](docs/subsystems/emmc-layout.md).

Details: `doku/110-plan-installationsweg.md`, `doku/109-plan-layout-v3.md`.
