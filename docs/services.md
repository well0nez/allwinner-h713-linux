# What runs on the device

The image is a plain Debian 13 with a handful of additions. This page lists them, because a system you
cannot enumerate is a system you cannot trust.

## Services

| Unit | What it does |
|---|---|
| `h713-tv@videoN` | the HDMI input service, one instance per capture device, started by udev when it appears - the number varies with probe order ([h713-tv](tools/h713-tv.md)) |
| `h713-wifi` | reads `/etc/h713/wifi.env` once at boot and brings the radio up as an access point, a station, or not at all ([h713-wifi](tools/h713-wifi.md)) |
| `h713-hdcp-key` | reads the 912-byte HDCP 2.2 key out of *your* device's secure storage and hands it to the display firmware. Nothing is shipped, nothing is written back |
| `hy310-zram-swap` | compressed swap in RAM: zstd, half of the 1 GiB, one device. This board has no swap partition and no room for one |
| `hy310-ssh-host-keys` | generates the SSH host keys on first boot, so two devices from the same image are not twins |

`hostapd` and `wpa_supplicant` are installed but their own units are masked: `h713-wifi` generates their
configuration and starts them itself, so editing their files by hand and restarting them does nothing
lasting.

## Commands worth knowing

Beyond the tools in [docs/tools/](tools/):

| Command | For |
|---|---|
| `hy310-logs volatile\|persistent\|status` | the journal lives in RAM by default, so a projector left running for weeks does not chew through eMMC write cycles. `persistent` bind-mounts `/var/log` onto `/data/log` when you need logs to survive a crash |
| `h713-fel` | put the running system into FEL from Linux ([details](tools/h713-fel.md)) |
| `fw_printenv` / `fw_setenv` | read and change the U-Boot environment from Linux ([environment](uboot/environment.md)) |

## The serial console logs you in as root, without a password

`serial-getty@ttyS0` is configured for **autologin as root**. That is deliberate and it is the only way
into a freshly installed device that has no SSH key: the root password is locked, and the image ships no
key of its own.

The consequence is worth saying plainly: **anyone who can reach the UART pads has root.** That is the
same class of access as holding the device in your hands - the pads are inside the case, and someone who
has opened the case can also read the eMMC - but if your threat model includes people with screwdrivers,
remove the drop-in at `/etc/systemd/system/serial-getty@ttyS0.service.d/autologin.conf` and set a root
password before the device leaves your desk.

Over the network there is no such shortcut: SSH is key-only, password authentication is off, and the only
key present is the one you passed to the installer.

## Filesystems

| Path | What |
|---|---|
| `/` | the root filesystem, ext4, grown to the partition on first boot |
| `/data` | a directory in the same filesystem, for things you want out of the way - persistent logs land under `/data/log` |
| `/etc/h713/` | our configuration: `wifi.env`, `tv.conf`, and the `tvconfig` directory the picture tools use |
| `/run/log/journal` | the journal, in RAM, unless you switched it |

Details: `doku/107-plan-rootfs.md` (the whole rootfs recipe and the reasoning behind each of these).
