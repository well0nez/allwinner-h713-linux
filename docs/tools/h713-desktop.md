# h713-desktop - the desktop and the browser

Profile `desktop` only (media side project, package H2). Next to Kodi the projector has two more ways to fill the
panel with a program: a small desktop (labwc with a terminal and a menu) and Firefox, maximized. Each is a systemd
unit that nothing wants - the panel shows the HDMI input until the launcher (or you) starts one.

| Mode | Unit | What runs | Launcher entry |
|---|---|---|---|
| Kodi | `h713-kodi.service` | cage with Kodi | `20-kodi.conf` (package H) |
| Browser | `h713-browser.service` | labwc with Firefox as its session client | `/etc/h713/launcher.d/25-browser.conf` |
| Desktop | `h713-desktop.service` | labwc, a terminal (foot) | `/etc/h713/launcher.d/30-desktop.conf` |

```
systemctl start h713-desktop.service     # the desktop on the wall, the keystone applies; HDMI comes back when it stops
systemctl stop h713-desktop.service
```

## Not root

Kodi runs as the system user `h713-kodi`; the desktop and the browser run as **`h713-desktop`** (`usr/lib/sysusers.d/h713-desktop.conf`,
made by systemd-sysusers at the first boot; one user for both modes, they never run together and share the Firefox profile). Groups:
`video` (seatd's socket, h713-warp's Wayland socket, the decoders' `/dev/video*` and `/dev/media*`), `render` (the GPU's render
node), `audio` (ALSA, the DSP bridge). The home is the units' StateDirectory `/var/lib/h713-desktop`; `/tmp` is private. The hardening is
`h713-warp.service`'s (`NoNewPrivileges`, `ProtectSystem=strict`, `ProtectHome`, `PrivateTmp`, `RestrictSUIDSGID`) **without**
`MemoryDenyWriteExecute`, which Firefox's JavaScript compiler cannot live with. Only the start command needs root: `ExecStartPre=+h713-kodi-switch source`
tells h713-tv `source auto` (its socket is root's) and does nothing while h713-tv is not there yet. A program of the user cannot stop a unit, so the
desktop menu's "HDMI input" ends labwc (the `Exit` action), which ends the unit.

## How they reach the wall

All three are clients of `h713-warp`'s Wayland server (`docs/tools/h713-warp.md`, "A Wayland client"): cage and labwc are
wlroots compositors, `WLR_BACKENDS=wayland,libinput` makes their output one fullscreen window of that server, `h713-warp`
draws it through the keystone and `h713-tv` stays the DRM master. Each unit starts with `h713-tv ctl source auto` (through `h713-kodi-switch source`): the
client goes before the HDMI ring, and however it ends - a stop, a crash, a SIGKILL of the unit - the ring is back two
seconds after the compositor is gone. The server keeps one fullscreen window, so the units exclude each other
(`Conflicts=`); the launcher stops the old mode before it starts the new one. A standby is package H's: `h713-mode`
ends every mode unit that a launcher entry names (`unit =`) before the sleep and starts it again after the wake, so
these units carry no `Conflicts=sleep.target`.

## The desktop

labwc reads `/etc/h713/labwc/` only: `rc.xml`, `menu.xml`, `autostart`, `environment` (the pointer size). The autostart
opens a terminal (foot, text size 14 from `/etc/xdg/foot/foot.ini`); there is no panel and no background program. A click
on the empty desktop (the remote's OK in its mouse mode is a left click) opens the menu: Terminal, Web browser (Firefox in
a window, the same profile as the browser mode), HDMI input (ends labwc, so the unit ends). The remote's Menu key opens the same menu.
The pointer is drawn by labwc itself (`WLR_NO_HARDWARE_CURSORS=1`; the warp's server has no seat to show a hardware
cursor). Text sizes are set for a wall seen from a distance.

## The browser

Firefox ESR from Debian in a labwc of its own (`/etc/h713/labwc-browser/`): labwc starts it as its session client
(`-S`), maximizes the window without a frame, and ends with it, so the unit ends and the HDMI ring returns when Firefox is
closed. Why a compositor and not cage alone, which would pass the buffers through without a copy (as for Kodi): the press
of Home that opens the launcher reaches the client like any other, and Firefox would go to its home page under the
launcher; the remote's focus keys are `KEY_F4`/`KEY_F5` and F5 reloads a page. Only a compositor can bind those keys to
nothing, which `labwc-browser/rc.xml` does. The price is a second GPU
pass over the window; the control arm with cage is `laeufe/box/h2.sh h4 cage` of the package.
The profile is `/var/lib/h713-desktop/firefox` (shared with the desktop's Firefox window), its `user.js` sets the few things that matter here: the VA-API blocklist
off (`media.hardware-video-decoding.force-enabled`), fewer content processes (the box has 1 GiB), no first-run pages, no
update checks. Decoding is software by default: Firefox loads foreign web content, so its decoder process stays in its sandbox, and inside it the VA-API driver
of `rootfs/libva` (drop-in as Kodi's: `LIBVA_DRIVER_NAME`, `LIBVA_DRIVERS_PATH`) cannot be used. The hardware path is a commented line in the unit
(`#Environment=MOZ_DISABLE_RDD_SANDBOX=1`): with it the decoder process runs without its sandbox, as the unprivileged user `h713-desktop` under the
unit's hardening. Firefox has no pref that opens the decoder sandbox to the device nodes (its path whitelists are the content process's).

## Sound

No sound server runs on this image: the media profile masks the PipeWire user units and leaves `pipewire-alsa` out, so ALSA
`default` is the DSP bridge (a `plug` over `hw:hy310hdmi,0`), the path Kodi uses. Firefox is told to use its ALSA backend
(`media.cubeb.backend` in `user.js`; ESR 140 has it, and a sound server is not tried first). mpv's automatic output choice tries
PipeWire and PulseAudio first, finds no daemon and ends on ALSA. The bridge is one hardware PCM: one stream at a time. Two tabs
playing together need a mixer in front of it (PipeWire started by hand, which mpv then uses natively); nothing here does that.

## Keys

Volume, mute and focus are `h713-keys`' in every mode, as with HDMI; Home belongs to the launcher; the power key to
`h713-power`. The remote's OK arrives as `KEY_ENTER` and its Menu as `KEY_COMPOSE` (package H's
`70-h713-remote.rules`; xkb gives a client no key code above 247), so labwc and Firefox see them like a keyboard's Return and
context-menu key. The launcher's grab (`EVIOCGRAB`) waits for the release of Home: the press of Home still reaches the program under it.
So labwc, in the desktop and in the browser, binds Home, the volume and mute keys, the power key and the focus keys (`KEY_F4`/`KEY_F5`)
to nothing: no window sees them, the focus keys stay focus keys (F5 would reload a page), Home does not send Firefox to its home page,
labwc's own defaults would run `amixer`, and mpv has volume keys of its own. A USB keyboard's F4/F5 do nothing there. The arrows and
Back reach the programs as they are; Back is "history back" in Firefox. On the desktop Menu opens the menu, the arrows and OK work it.
The remote's mouse mode (`REL_X`/`REL_Y`, OK as the left button) is the pointer.

## State

Measured on the HY310 on 15.10.2026 (kernel 600 MHz, Firefox ESR 153.5, labwc 0.8.3, the units of this package; `arbeit/medien/H2-desktop/BERICHT.md`):

- **Switching** from the HDMI input to the desktop or to the browser and back, 10 times each: the first client picture after 1.0 to 1.2 s, the ring
  back after 2.5 to 2.7 s, `h713-warp` and `h713-tv` untouched (same PIDs), no driver events.
- **Firefox, decoding:** `about:support` shows WebRender on Wayland, the content sandbox on level 6 (the kernel has no user namespaces, `hasUserNamespaces`
  false; the sandbox runs on seccomp). With the sandbox of the decoder process on, the VA-API device context cannot be created and Firefox decodes in
  software: 47 fps of a 1080p60 clip decoded, VE interrupts 0/s, 1884 of 2103 frames not painted; not measured at 30 fps. With
  `MOZ_DISABLE_RDD_SANDBOX=1` "VA-API FFmpeg init successful": 60 fps decoded by the video engine, 60 VE interrupts/s, and about a third of the frames
  are still not painted (883 of 2748 over 40 s; with cage instead of labwc just the same, 887 of 2765): the limit is Firefox's painting of a 1080p60
  video on this GPU, not the second compositor. A 720p30 clip with the switch: 30 fps, 22 of 555 frames not painted.
- **Memory** with one video tab playing: Firefox's processes add up to about 900 MiB of resident pages (shared ones counted twice) and the system had
  330 to 350 MiB left of 924 MiB.
