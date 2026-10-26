# Known issues

What still gets in your way in **v0.97-beta**, and what to do about it. "open" means nobody has fixed it yet; "by design"
means it will not change because something else depends on it; "decided" means the owner weighed it and chose. Every
line names the journal entry or the `TODO.md` line the measurement is in.

## The problems of this release

| Issue | What is measured, and what is not | Workaround |
|---|---|---|
| **No standby, and off draws 2.9 W** | The release runs the vendor's ARISC firmware and offers no suspend; a power-off ends in U-Boot's gate at 2.9 W, silent, LED red. Our own ARISC firmware, crust, has a standby (2.0 W HY300PRO-G-EU, 2.4 W HY310, picture back about 5 s after the wake) and a 0.3 W power-off - and with it the power supply hums or whines, in standby and when off. A night with a microphone at the supply moved neither tone with any crust change at the same power; stock Android is silent at 0.3 W (`doku/218`). **Decided 22.10.2026** by the owner. | crust stays in the image as an experiment: `h713-arisc set crust` and a reboot bring its 0.3 W power-off ([h713-arisc](tools/h713-arisc.md)); the standby needs an image built with `--standby` ([standby](subsystems/standby.md)) |
| **The picture flickers faintly** at key presses and when a program starts (HY310) | Measured on the HY310 with the box's camera as a light meter (16.10.2026, `doku/213` §3): the lamp's light follows the current the SoC draws - a burst of computing on four cores lifts it by 1.2 % for 0.2 to 0.3 s at 1296 MHz, the picture chain and the lamp control are ruled out, a clock cap in a blind test changed nothing. That this coupling is the cause of the flicker Marco and a tester see during output is a **hypothesis, not proven** (`TODO.md` 2.99, 9.3n). The HY300PRO-G-EU has an LCD backlight and was not measured this way. | none; the oscilloscope measurement at the lamp's supply is open |
| **The HY300 (Pro) of issue #1 does not react to its infrared remote** | The tester's older model runs our test images with the vendor's ARISC firmware, whose start switches the infrared pin off (below); his `test11` of 22.10.2026 carries a retrofit that applies the pin again and loads his remote's key table, checked on the HY300PRO-G-EU in his state (`doku/219` §4). His report is outstanding (`TODO.md` 2.134). | the next test image carries kernel `0328`/`0329` instead of the retrofit |
| **The remote's power key starts both boxes in a room** | Both stock remotes send one NEC code for Power, the gate decodes it (U-Boot `0102`) and Linux takes it (`0329`): one press starts every box waiting in the gate within reach and sends every running one into the countdown (`TODO.md` 2.35, 2.140). The same holds on stock. | `fw_setenv h713_gate_ir 0` is **not** built yet; keep the second box out of the remote's sight, or switch the gate's infrared off per build (`CONFIG_H713_POWER_GATE_IR=n`) |
| **A remote of another device can press keys** | The HY300's stock remote sends NEC address 0x00, and so do many cheap remotes; any of them that reaches the receiver with one of the 15 mapped commands acts like the projector's remote (`0329`, 22.10.2026). As on stock, whose own table starts with that address. | by design, as on stock |
| **A thin stripe at the left edge under the launcher and the pages (HY300PRO-G-EU)** | The overlay plane starts two pixels to the right of the picture, so the first two panel columns show the video plane: under a page the image puts a black picture there since 20.10.2026 (the stripe is covered); under the console, and on the "No signal" page before any picture came, the still video plane shows as a thin green or old-picture stripe. Why the plane starts two pixels late is not known (`TODO.md` 2.126, `arbeit` package launcher-rand). | none |
| **A black block at the foot of the launcher, now and then (HY300PRO-G-EU)** | Seen by the owner at every second move over the emulated remote on 20.10.2026, where the volume pill would be; two measured runs showed both launcher buffers without a hole and the owner saw no block in them. Not reproduced since (`TODO.md` 2.131). **Decided 22.10.2026:** known, not before the release. | reopen the launcher (Back, Home) |
| **After a crash of `h713-tv` on the way out the wall can stay without a picture** | If `h713-tv`'s last commit fails when it leaves, or it is killed with its own frame on the primary plane (the warp, Kodi), the kernel switches the CRTC off with that frame, and while another file holds the card no `h713-tv` starts again until something unblanks the console (`no CRTC drives a mode`); a second crash in the same boot gets no rescue (`TODO.md` 2.125, package wach-wand §5.1). **Decided 22.10.2026:** known, not before the release. Seen in tests, not in normal use. **After v0.97-beta** the start of `h713-tv` restores the console itself when no CRTC drives a mode ([h713-tv](tools/h713-tv.md#a-start-after-a-run-that-took-the-mode-with-it-todo-2125)); host-tested, not yet measured on a device. | `echo 0 > /sys/class/graphics/fb0/blank`, then start `h713-tv@*` again (`systemctl reset-failed` first if it hit its start limit); or a reboot |
| **The browser starts in 7 s on the HY300PRO-G-EU, 5.6 s on the HY310** | Firefox to its first picture: 6.9 s in 29 starts on the HY300PRO-G-EU; 1.3 s of it sits in Firefox's own start, the rest is the box's (`TODO.md` 2.121, package ff-start). | none needed |
| **Five ALSA error lines at every Kodi start** | `sun4i-codec ... ASoC error (-16)` on the codec, Kodi's device scan hitting a busy device; no audible effect (`TODO.md` 2.123). | ignore |
| **`pcm.codec` in `/etc/asound.conf` names a card that does not exist** | The shipped file says `H713AudioCodec`, the card is called `Codec`; nothing in the image uses the name (`TODO.md` 2.73). | `aplay -D hw:Codec` if you need the codec directly |
| **The installer carried `h713_gate=0` over from a dump** | `--keep-env` took the U-Boot environment out of the dump directory instead of the device: both boards came up with the gate off after the `v0.97-beta` install, where the device had 1 (`doku/219` §5, `TODO.md` 2.137). **Fixed after `v0.97-beta` (25.10.2026):** the installer takes the device's environment and names a dump that disagrees; checked in the installer's tests, not yet in an install on a device. | with the `v0.97-beta` installer: `fw_setenv h713_gate 1` after the install, or `--fresh-env` |
| **A crackle from the speakers at power-on (HY300PRO-G-EU)** | Heard once by the owner on 21.10.2026 at a cold start after crust's power-off; not investigated, the moment in the boot not found (`TODO.md` 2.132). | none |
| **The focus motor can stay outside its range at the lower stop** | Driven to the lower stop, the driver does not walk back into the range and refuses both directions until a warm start; the upper edge behaves (`doku/213` §6, 16.10.2026). | reboot, or `modprobe -r hy310_focus_motor && modprobe hy310_focus_motor` |
| **A reinstall resets your settings and the remote's pairing** | A reinstall over our layout carries the vendor files and the U-Boot keys over, but writes a fresh root file system: `/etc/h713`, `/var/lib/h713-tv` and the remote's bond start from the defaults (`TODO.md` 1.2b). **Changed after `v0.97-beta` (25.10.2026):** the installer carries `wifi.env`, `warp.conf`, `keystone.conf` and the other files of `/etc/h713` the image does not bring, the SSH host keys, the pairings, `h713-tv`'s state and a chosen hostname over; `tv.conf`, `osd.conf`, `keys.conf` and `power.conf` stay the image's and a difference is named ([`h713-install`](tools/h713-install.md)). Checked in the installer's tests, not yet in an install on a device. | with the `v0.97-beta` installer: copy `/etc/h713` and `/var/lib/bluetooth` off beforehand; pair again |
| **The web page has no authentication beyond its password; the page's password travels over plain HTTP** | Whoever reaches port 8080 with the password can move the focus motor and change the picture. | change the shipped Wi-Fi password; keep the projector off networks you do not own |
| **No AV1 decode** | cstenger's AV1 driver decoded bit-exact (`doku/211` §5) and is switched off since `0310`: next to a decoding AV1 core the video engine cannot recover from a damaged H.265 stream, and the engine would run at 432 MHz (`TODO.md` 9.3b). | none |
| **Firefox decodes 1080p60 in software** | With the sandbox of its decoder process on, the VA-API device cannot be created: 47 frames a second, 1884 of 2103 frames not painted (`doku/212` §3). With `MOZ_DISABLE_RDD_SANDBOX=1` the engine decodes at 60 and a third of the frames are still not painted. | the commented line in `h713-browser.service`, at the price of the sandbox |
| **Firefox's content sandbox runs on seccomp only** | The kernel has no user namespaces (`TODO.md` 9.3h). | do not browse sites you do not trust on this box |
| **1080p100/120, and the modes the table lacks** | The display firmware's own mode table is the list of what locks; a PC that picks 1600x1200 or 640x360 gets the console and a named refusal. 1080p100/120 lock once EDID block 1 is published (`h713-tv ctl edid block1`); under the warp a 120 Hz source draws about 19 frames a second, not explained. | pick a mode of the table |

## What the vendor's ARISC firmware changes

Since 22.10.2026 an image runs the vendor's ARISC firmware from the owner's dump ([arisc](subsystems/arisc.md)). What
that costs against crust, measured in `doku/219` and the audit of 22.10.2026 (`TODO.md` 1.0, crust-audit):

- the standby and the 0.3 W power-off (above);
- the firmware's start switches the infrared pin PL9 off; kernel `0328` applies it again a second after the firmware has
  bound, so the remote works over infrared (`PL_CFG1` `0x2222223f` after every start, both boards);
- the gate had to learn the remote itself: U-Boot `0102` decodes NEC in the gate loop, so the power key of either stock
  remote starts the board from off (both boards, `doku/219` §3). Everything else that was built for crust - the standby
  paths in the kernel, BL31's suspend, the sleep units - is switched off by the build and does nothing on this image.

## Fixed in the release, kept for the record

| Was | Fixed |
|---|---|
| No infrared key arrived under the vendor's ARISC firmware (`v0.97-beta`'s first build, 22.10.2026) | kernel `0328` (the pin), `0329` (the HY300 remote's table); measured on both boards (`doku/219` §2) |
| From the gate only the projector's key started the box | U-Boot `0102` (`doku/219` §3) |
| A 1080p60 source on a 720p panel showed only 43 to 57 of its frames | `0255`: the display driver takes the capture's own write index (`doku/200`) |
| After a standby the capture handed the warp no picture until a warm start (HY310, HY300PRO-G-EU) | `0314`: the capture index is the field [2:0] of its word (`doku/211` §11, `doku/213`) |
| RTC alarms within 174 s lost, the clock 26 % slow | `0320`: the 32 kHz from the 24 MHz crystal (`doku/213` §5) |
| An eMMC read error under 4K playback hung the box | `0312`, `0313` (`doku/211` §8) |
| A damaged H.265 stream left the decoder dead until a reboot | `0308`, `0309` (`doku/211` §6) |
| The console lay over the picture after a switch between two clients; white flashes at every hand-over | seatd without a VT, one-step hand-overs (16.10.2026, `doku/213` §1) |
| After a wake the console stood on the wall for 7 to 9 s | the wall stays black while the picture path restarts (`doku/215`) |
| The Bluetooth remote did not reconnect after a stale bond | `h713-remote-pair watch` pairs a bonded remote in pairing mode afresh (`doku/214`, 20.10.2026) |
| A source renegotiating to 12 bit on the HY310 lost its picture | the published EDID offers no deep colour (17.10.2026) |
| Vertical lines on fast motion under the warp; a frame of latency | `0255`: the warp draws the finished slot at once (`doku/200`, `doku/201`) |
| Bluetooth after a warm reboot | `h713-bt-reset` before and after the attach (`doku/156`) |
| No HDCP 1.4 | the key sink needs the DMA source inside the protected window; our EL3 service (`doku/147`, `doku/180`) |
| No picture after plugging a source in | `0136a`, `0136c` (16.09.2026) |
| The sound dropped out while the warp was drawing | the audio automaton asks for "plane on or warped" (`v0.95-beta`) |

## By design

| Behaviour | Reason |
|---|---|
| The projector waits for the power key after being plugged in | As with the stock firmware: U-Boot waits in its gate at 2.9 W ([power-gate](uboot/power-gate.md)). `fw_setenv h713_gate 0` makes it boot the moment it gets power |
| The launcher is what the projector shows when it has started | the owner's choice of 16.10.2026; `on_start = hdmi` in `/etc/h713/keys.conf` shows the HDMI picture instead, `last` what ran when it went off ([h713-keys](tools/h713-keys.md)) |
| The warp and the ring are mutually exclusive on the video plane | while `h713-warp` draws, the display firmware's magnifier (`h713-tv ctl zoom in`) has nothing to scale and is refused; the picture controls act on the warped frame |
| The console keyboard is off while a picture stands | seatd runs without a VT, so `h713-tv` switches tty1's keyboard off while the ring, a client or a page is on the panel (`doku/213` §1) |
| No temperature reading on the HY310 | the unit has no NTC (`ntc_num = 0`); the fan tachometer is the protection, a stalled fan powers the device off (`doku/60`) |
| `brightness` moves the black level, not the lamp | the vendor's own meaning of the control; the lamp is not adjustable on the HY310 (`backlight_level` and `dynamic_backlight` do nothing, 22.09.2026) |
| A source the firmware's table does not carry gets the "No signal" page | the display firmware's mode table is the list of what locks (`0171`); the page names nothing, `h713-tv ctl status` does |
| The GPU userspace is 15 MiB and panfrost only | mesa cross-built for this image instead of Debian's 187 MiB; no Vulkan, no second driver |
| Setting the EDID block mask publishes nothing by itself | the firmware applies it at the next EDID upload ([arisc](subsystems/arisc.md)) |
| The serial console logs in as root without a password | the only way into a device installed without an SSH key ([services](services.md)) |

## Untested paths

| Path | State |
|---|---|
| Installer on Windows | written to run there, never run; `install` is Linux-only in any case (it mounts the image's file systems) |
| A release image built from `main` | the `v0.97-beta` images came from the `medien` branch at the commit `main` now carries; the last build before the tag repeats it from `main` (`TODO.md` 1.0 (5b)) |
| The HY300 Pro+ variant `projector09220931`, the HY200 QZ713_V2, the HY300 T08, the HY350, the L018 | nothing of ours has run on them; see [boards](../boards/README.md) |
