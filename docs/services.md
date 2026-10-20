# What runs on the device

The image is a plain Debian 13 with a handful of additions. This page lists them, because a system you
cannot enumerate is a system you cannot trust.

## Services

| Unit | What it does |
|---|---|
| `h713-tv@videoN` | the HDMI input service, one instance per capture device, started by udev when it appears - the number varies with probe order ([h713-tv](tools/h713-tv.md)) |
| `h713-wifi` | reads `/etc/h713/wifi.env` once at boot and brings the radio up as an access point, a station, or not at all ([h713-wifi](tools/h713-wifi.md)) |
| `h713-bluetooth` | brings the AIC8800's Bluetooth up once `h713-wifi` has loaded the chip: `hciattach` on UART1 (1.5 MBd, RTS/CTS) with `h713-bt-reset` before and after it, and the start counts only once `hci0` is UP; bluez (`bluetooth.service`) runs on top. Off with `mode=off` in `wifi.env` ([Bluetooth](subsystems/wifi.md#bluetooth)) |
| `h713-remote-pair` | `h713-remote-pair watch`: reconnects the bonded stock BLE remote, and scans for a remote in pairing mode only while none is bonded - hold Left+Right on the remote to pair. A remote paired with another box since never reconnects here (it remembers one box): `h713-remote-pair forget`, then Left+Right (a button in the panel is TODO 2.54). *Superseded 11.10.2026:* "scans for it while none is connected" - it never scanned while a bond existed |
| `h713-hdcp-key` | reads the 912-byte HDCP 2.2 key out of *your* device's secure storage and hands it to the display firmware. Nothing is shipped, nothing is written back. `--bind hdmi-rx` does it after the display firmware was restarted; the key lies in a tmpfs only for that bind |
| *(none - HDCP 1.4 happens earlier)* | the 288-byte HDCP 1.4 key set is handed over by the **boot loader**, not by a service: the display firmware polls the sink's "key loaded" bit and gives up before userspace could act. See [`subsystems/hdcp.md`](subsystems/hdcp.md) |
| `hy310-zram-swap` | compressed swap in RAM: zstd, half of the 1 GiB, one device. This board has no swap partition and no room for one |
| `hy310-ssh-host-keys` | generates the SSH host keys on first boot, so two devices from the same image are not twins |
| `h713-warp` | the keystone warp on the GPU ([h713-warp](tools/h713-warp.md)); in bypass, with the GPU closed, until a corner or the zoom is set |
| `h713-keystone-auto` | `h713-keystone watch`: the automatic keystone once after a move; does nothing while `after_move = off` in `/etc/h713/keystone.conf`, which is the shipped default. Skipped on a board without an accelerometer; started by udev (`99-h713-keystone.rules`) when one probes late. Exit 3 (the sensor does not answer) and 5 (`h713-warp` refused) are retried with a delay growing from 5 s to 60 s, never given up |
| `h713-features` | once per boot: the camera, the accelerometer and the focus motor against `/etc/h713/features`, one journal line each and a warning for one the board should have and does not show ([h713-features](tools/h713-features.md)) |
| `h713-panel` | the settings page on port 8080, one password (`h713-panel --show-password`; [guide](guides/settings-page.md)) |
| `h713-power` | only on an image built with `release/build-all.sh --standby`: decides the power key under `systemd-inhibit` (a dead service gives the key back to logind). Short press: suspend to RAM through crust; held 3 s: power-off; `/etc/h713/power.conf`. After a wake it runs `h713-mips-restart` ([h713-power](tools/h713-power.md)) |
| `h713-keys` | the stock remote's keys: volume, mute, focus, the HDMI input; Home opens the launcher, and while it is open Kodi gets no key ([h713-keys](tools/h713-keys.md)) |
| `h713-osd` | draws the overlays over the picture - volume, mute, focus, input - and the launcher and settings pages ([h713-osd](tools/h713-osd.md)) |
| `h713-cpufreq` | the CPU clock under the warp's load: the schedutil rate limit and the policy of the GPU's interrupt threads |
| `h713-tv-rescue` | `OnFailure=` of `h713-tv@`: reloads the display MIPS once when `h713-tv` gave up, restarts `h713-warp`, and brings the mode that ran (Kodi, desktop, browser) back (`h713-mode rescue`) |
| `h713-sleep-pre`, `h713-sleep-post` | only on an image built with `--standby`: `-pre` (`Before=sleep.target`) remembers the running mode in `/run/h713-mode.resume` and ends it; `-post` (`After=suspend.target`) brings the picture path back when the display MIPS is parked (`h713-mips-restart`) and starts the remembered mode again ([h713-power](tools/h713-power.md)) |

`hostapd` and `wpa_supplicant` are installed but their own units are masked: `h713-wifi` generates their
configuration and starts them itself, so editing their files by hand and restarting them does nothing
lasting.

`/etc/udev/rules.d/70-h713-remote.rules` (every image) moves the stock remote's OK to `KEY_ENTER` and its Menu to `KEY_COMPOSE`: a Wayland client gets
no key code above 247, and OK and Menu are above it. `h713-keys` and `h713-power` read the new codes.

## The profile images (media, desktop)

An image built with `--profile media,desktop` has players and clients on top of that list. None of these units is wanted by anything: the panel shows the
HDMI input until the launcher starts one of them.

| Unit | What it does |
|---|---|
| `h713-kodi.service` | cage with Kodi in it, drawn by `h713-warp` as a Wayland client, as the system user `h713-kodi` (not root) ([rootfs README](../rootfs/README.md), [h713-warp](tools/h713-warp.md)) |
| `h713-desktop.service`, `h713-browser.service` | labwc with a terminal, and Firefox in a labwc of its own, as the system user `h713-desktop`; they exclude each other and Kodi (`Conflicts=`) ([h713-desktop](tools/h713-desktop.md)) |
| `seatd` | seat management for cage and labwc, without a VT (`SEATD_VTBOUND=0`: the panel is h713-tv's, the console's keyboard too; measured 16.10.2026, `doku/213` §1) |
| `polkitd` | with `/etc/polkit-1/rules.d/50-h713-kodi.rules`: lets the user `h713-kodi` suspend, power off and reboot through logind - Kodi's own power menu - and nothing else |
| `pipewire.service`, `pipewire.socket`, `wireplumber.service`, `filter-chain.service` (user units) | **masked** in `/etc/systemd/user/` (profile `media`): nothing starts PipeWire by itself; a player that wants it starts it by hand |
| `h713-settings` | not a service: the settings page, a program the launcher's entry starts ([h713-settings](tools/h713-settings.md)); the binary is in every image, the entry in the profile `desktop` |

The two system users, `h713-kodi` and `h713-desktop`, have a home under `/var/lib` (the units' state directory), no login shell and only the groups their devices ask for.

## Commands worth knowing

Beyond the tools in [docs/tools/](tools/):

| Command | For |
|---|---|
| `h713-logs volatile\|persistent\|status` | the journal lives in RAM by default, so a projector left running for weeks does not chew through eMMC write cycles. `persistent` bind-mounts `/var/log` onto `/data/log` when you need logs to survive a crash. The old name `hy310-logs` is still there as a symlink |
| `h713-fel` | put the running system into FEL from Linux ([details](tools/h713-fel.md)) |
| `fw_printenv` / `fw_setenv` | read and change the U-Boot environment from Linux ([environment](uboot/environment.md)) |
| `h713-arisc status\|set vendor\|crust` | which firmware the ARISC runs (crust or the vendor's from the dump), where the choice came from, and the switch for the next boot through `/etc/modprobe.d/h713-arisc.conf` ([h713-arisc](tools/h713-arisc.md)) |
| `h713-mips-restart [FIRMWARE]` | restart the display MIPS and bring the HDMI picture back; `h713-power` runs it after a standby, by hand it also reloads a running MIPS. It starts `h713-tv --hold-wall` (transient unit `h713-wall-hold`: the wall black, not the console, until h713-tv's next picture or page), stops `h713-tv@*` and `h713-warp`, unbinds and binds the receiver around the restart, starts both again and rebuilds the audio DSP; it refuses while a process holds the receiver's video node ([h713-power](tools/h713-power.md)) |
| `h713-mode status\|hdmi\|sleep-pre\|sleep-post` | what the panel shows besides the HDMI picture (the mode units a launcher entry names), `hdmi` brings the HDMI picture back, ends every mode and leaves `h713-tv`'s source on `auto`; the last two are what the sleep units call ([h713-power](tools/h713-power.md)) |
| `h713-bt-reset` | sends HCI_Reset to the Bluetooth controller on the bare UART; `h713-bluetooth` runs it before and after `hciattach`; by hand only while that unit is stopped, because it needs the bare UART |

## The watchdog, and which sleep is allowed

`/etc/systemd/system.conf.d/10-h713-watchdog.conf` sets `RuntimeWatchdogSec=16s` and `RebootWatchdogSec=16s` (16 s is the SoC watchdog's maximum): PID 1 feeds it, and a hung kernel or a stalled reboot resets the box within 16 s, also with a USB cable plugged in. Measured 08.10.2026 (`doku/170`, W2, 12 of 12): feeding stopped - reset after 16.5 s; `sysrq-c` 14 - 16 s; `reboot`/`poweroff` 0.6 s. Before that the image set neither and the tree named a register layout the block lacks (kernel `0187`). It needs a BL31 whose reset feeds the running watchdog first; `release/check-crust.py` refuses an image without.

`/etc/systemd/sleep.conf.d/10-h713.conf` says `AllowSuspend=no`: without crust a suspend would fall back to s2idle, which powers the display domains down under the running display MIPS. An image built with `--standby` replaces it with `AllowSuspend=yes`, `SuspendState=mem`, `MemorySleepMode=deep`: suspend to RAM through crust and nothing else.

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
| `/etc/h713/` | our configuration: `wifi.env`, `tv.conf`, `warp.conf`, `keystone.conf`, `power.conf` (standby images), `keystone-ref`, `board`, `features`, and the `tvconfig` directory the picture tools use |
| `/run/log/journal` | the journal, in RAM, unless you switched it |

Details: `doku/107-plan-rootfs.md` (the whole rootfs recipe and the reasoning behind each of these).
