# `h713-tv` - the HDMI picture on the video plane, the console on signal loss, control from userspace

Package **F** out of [doku/78-nachtplan-hdmi-switch.md](../../doku/78-nachtplan-hdmi-switch.md), appendix A.4.
A small program plus a systemd unit: while a signal is present on the HDMI input, the projector shows the
source's picture; when the signal goes away, the panel belongs to the console again. No manual step, in
either direction. On top of that a control channel (`h713-tv ctl …`) through which picture, controls, source
and firmware can be operated from userspace - section 6a. Since package E
([doku/101](../../doku/101-plan-audio-treiber.md)) the **audio** follows the picture as well: HDMI audio runs
through the audio DSP into the codec as soon as a picture stands and the source sends PCM, and is silent
otherwise - section 6b.

**State 08.09.2026:** running on the device with kernel series 95 (`0117` - `0126`): 720p and 1080p are
scaled by the firmware and shown in the right colours, over any number of changes
([doku/nachtlog/S11](../../doku/nachtlog/S11-gruenstich-ursache-und-callback-slots.md)). The earlier console
lock for non-panel resolutions and the test switch `H713_TV_SKALIERTEST` are gone. VESA modes run at 60 Hz
(1024x768 with 4:3 bars, 1440x900, 1280x1024 stretched); the firmware's table does not know the 120 Hz
variants and 1600x900 -> console.
The acceptance procedure is in [doku/nachtlog/F-korrektur.md](../../doku/nachtlog/F-korrektur.md).
---

## 1. What the program does - and what it explicitly does not

Two devices, two roles:

| Device | on this board | driver | role |
|---|---|---|---|
| `/dev/videoN` | **`/dev/video1`** (`video0` is cedrus) | `sun50i-h713-hdmirx` (0094) | says **whether** a signal is present, and reports **when that changes** |
| `/dev/dri/cardN` | **`/dev/dri/card1`** (`card0` is Panfrost) | `sun50i-h713-afbd` (0093) | shows the picture: overlay plane `video-0` = **plane 38** on **CRTC 36**/connector 33, mode `hdmi-ring` |

None of these numbers is in the program. The capture device is searched for through
`/sys/class/video4linux/videoN/name` - the same string the udev rule matches on - and confirmed with
`VIDIOC_QUERYCAP`; the DRM device through `drmGetVersion()->name`, the plane through type + NV16 + the
property `hdmi-ring`. The numbers are here only so that one knows what has to come out when looking.

**NV16 and NV16M are not a contradiction.** The capture offers `V4L2_PIX_FMT_NV16M`: two *separate* planes
of 2 073 600 bytes each, because Y and C sit `0x5FD000` apart in the ring. The KMS framebuffer is
`DRM_FORMAT_NV16` - a two-plane fourcc in **one** buffer object - and in `hdmi-ring` it carries nothing but
format, geometry and line pitch anyway. Nothing is converted.

The pixels do **not** run through this program. The plane reads the capture ring itself: in its vsync it
fetches the firmware's pair of flip pointers and takes the ring slot that was finished last (doku/86 §5).
The program only tells it to do that (plane property `hdmi-ring`), and when to stop.

The state machine is small accordingly:

```
                 SOURCE_CHANGE, no signal
        +--------------------------------------------+
        v                                            |
   STANDBY                                         PICTURE
   plane off, DRM master dropped                   plane on, master held
   (the console has the panel)                     (the mux is exclusive:
        |                                           the console is gone while
        +--------------------------------------------+  the picture stands)
                 SOURCE_CHANGE, signal there
```

`SIGTERM`/`SIGINT` take the same way out as a signal loss: plane off, console back, and only then exit. So a
`systemctl stop` leaves **no still frame** standing on the wall.

Everything is **decided** on an event and on nothing else. There is no time loop, no `sleep` as a remedy and
no retry without a cause: the MIPS firmware fires its `SignalChange` callback by itself both on loss **and**
on return (measured, [doku/nachtlog/K4-hotplug.md](../../doku/nachtlog/K4-hotplug.md)), and 0094 turns that
into `V4L2_EVENT_SOURCE_CHANGE`. The program sits in `poll()`.

The one timer there is asks **again** when the driver reports a change as "not locked yet" (`-ENOLCK`):
every 50 ms, forty times at most; until then the wall stays as it is. After that the current state stands -
with the console up, the question is repeated every 500 ms (§7).

---

## 2. Why a C program and not `gst-launch-1.0 v4l2src ! kmssink`

The night plan allows both. The C program was chosen, and **not** because GStreamer was missing - it is
installed in the board root (`gst-launch-1.0`, `libgstvideo4linux2.so`, `libgstkms.so`; `v4l2-ctl` as well,
only `modetest` is missing). The reasons are about substance:

1. **A GStreamer chain would have to copy every frame.** 0094 hands out the three ring slots as
   `VB2_MEMORY_MMAP` and has **no** `VIDIOC_EXPBUF` (doku/88 §4 and §8 item 2). Without a dma-buf `kmssink`
   imports nothing but copies into a dumb buffer of its own: 4 MiB per frame, 60 times a second, about
   250 MB/s - for data the plane can fetch by itself. The assignment says explicitly: no copying.
2. **The plane cannot be driven properly that way at all.** Running from the capture ring hangs on the plane
   property `hdmi-ring`; `kmssink` knows no driver-private properties.
3. **The real substance of F is the state machine, not the data path.** On signal loss **the ring freezes
   and the wall shows the last frame** - it does not go black (K4). A chain that simply stops delivers
   exactly the failure picture we want to prevent. The loss has to be recognised from the V4L2 event, and
   then somebody has to switch the plane off.
4. **A clean exit** (plane off, console back, DRM master dropped) is not to be had with `gst-launch`.

The decision costs about 1100 lines of C instead of one command line (state 08.09.2026, without comments and
blank lines). A good third of that is the control channel (§6a); the rest is the device search by **name**
(instead of guessing `/dev/video0` - cedrus sits there), KMS property handling and the state machine.

---

## 3. Handing the console back: two things, not one

1. **Plane off.** On disable 0093 puts the RGB channel (`0x05600140`) back into service and sets the encoder
   selector back to RGB (doku/86 §6). The mux behind AFBD source 0 is exclusive - either video **or** RGB
   reaches the encoder - so "plane off" is literally "console on".
2. **Drop the DRM master.** While a userspace master exists, the kernel's own console client stops painting
   (`drm_master_internal_acquire`). The console's picture would stand as it was, and every new line would be
   lost. So the program holds the master **only** while the picture stands, and gives it back in standby.
   The kernel client's full restore (`drm_client_dev_restore`) hangs on the **last close** of the DRM device
   (`drm_lastclose`) - not on the master change; it is not needed, because 0093 puts the hardware back
   itself.

If an X server or a Wayland compositor runs on the board later, the master is taken and `h713-tv` does not
get it (the program says so plainly then). The way there would be a DRM lease, or a start from inside the
session - not needed today, the panel belongs to the console (patch 0064).

---

## 4. A still picture is not a standstill

This line cost an hour in the night of 07.09., which is why it is here:

> A **static screen** at the source produces **no change in the buffer**. Whoever wants to check whether the
> picture is *alive* needs a **forced stimulus** - not a look at an unchanged photo.

The stimulus of choice is a gamma jump at the player:

```bash
ssh user@192.168.8.162 'DISPLAY=:0 xrandr --output HDMI-2 --gamma 1:0.25:0.25'  # stimulus
ssh user@192.168.8.162 'DISPLAY=:0 xrandr --output HDMI-2 --gamma 1:1:1'        # back
```

The order of magnitude, so that one knows what a hit is: the same stimulus changed **38.74 %** of the pixels
in the measured area during the D acceptance (`D-abnahme-board.md`), and **4.65 %** at B2. The return to
`1:1:1` does **not** have to give exactly 0.00 % - the source drifts by itself over minutes (D: 9.84 %;
documented in `M4-hpd-dauer.md`). What is judged is the jump, not the return to the decimal place.

The same holds the other way round for the ring: the flip pointers turn at 60 Hz **independently of the
content**. The signal detection in 0094 rests on exactly that (`QUERY_DV_TIMINGS` measures the pointers for
20 ms and answers `-ENOLINK` when they stand still) - and that is why "the picture looks the same" is **no**
evidence of a signal loss, and "the ring is running" **no** evidence that anything is happening to the
content.

---

## 5. Building

**Dependencies:** `libdrm-dev` (KMS) and, since package E, `libasound2-dev` (the ALSA control API for the
audio, Debian package `libasound2-dev`; at run time `libasound2`, which is there anyway). Both belong into
the board root - `ssh root@192.168.8.141 apt install libasound2-dev` - because the cross-build takes headers
and linker names from there as well. The Makefile asks `pkg-config --cflags --libs libdrm alsa` (native) and
links `-ldrm -lasound` (cross).

**Natively on the board** (the NFS root has `gcc-14`, `pkg-config` and the libdrm headers) - the simplest
way:

```bash
# from the workstation (the main session does this):
cp userspace/h713-tv/main.c userspace/h713-tv/Makefile /srv/h713-rootfs/root/h713-tv/
ssh root@192.168.8.141 'make -C /root/h713-tv'
```

**Cross on the workstation**, against the board root as the sysroot (reading only):

```bash
make -C userspace/h713-tv cross          # -> h713-tv.aarch64-linux-gnu
```

Why not in the container `h713-build`: the container does not see `/srv` (it has only
`/opt/Projekte/h713` -> `/work`) and has neither libdrm nor an arm64 sysroot. Rule 2 of the night plan
("build only in the container, only through `build/build.sh`") is about the **kernel**; for a userspace tool
the way through the host clang is the one package D describes for `analyse/kms/hdmi_plane_test.c`.

**Installing** - from the workstation with `install-cross`, because `install` would put the *x86* program
into the board root here:

```bash
sudo make -C userspace/h713-tv install-cross DESTDIR=/srv/h713-rootfs
# puts down: /usr/local/sbin/h713-tv   (arm64, from `make cross`)
#            /etc/systemd/system/h713-tv@.service   (template; the old h713-tv.service is removed)
#            /etc/udev/rules.d/99-h713-tv.rules
ssh root@192.168.8.141 'systemctl daemon-reload; udevadm control --reload'
```

`/srv/h713-rootfs` belongs to root, hence the `sudo`. Without `sudo` it works through the board, which
writes its own NFS root as root anyway - three `scp` to `root@192.168.8.141`, see
[F-startklar.md](../../doku/nachtlog/F-startklar.md) §5 step 0.

Built on the board itself the target is still `make install`.

---

## 6. Operation

**One template unit, no `systemctl enable`.** The service is called `h713-tv@videoN` - one instance per
capture device; the number varies with probe order (it was `video3` on 12.09., the camera enumerated
first), so never assume one. The unit deliberately has no `[Install]` section: the
capture device appears late and with an unpredictable number, because the probe of 0094 runs asynchronously
and the EDID/HPD sequence alone takes over ten seconds. So it is started from the udev rule, as soon as the
device is there, and the kernel name of the device becomes the instance name:

```
SUBSYSTEM=="video4linux", ACTION=="add", ATTR{name}=="sun50i-h713-hdmirx",
    TAG+="systemd", ENV{SYSTEMD_WANTS}+="h713-tv@%k.service"
```

The unit hangs on the device with `BindsTo=dev-%i.device`, in both directions: when `/dev/video1` goes away
(driver unloaded, `unbind`), systemd stops the instance instead of letting it run into the restart limit
against a missing device; when the device comes back, udev starts it again. Checked 08.09.2026:
`udevadm trigger --action=add /sys/class/video4linux/video1` starts `h713-tv@video1`, `systemctl show`
reports `BindsTo=dev-video1.device` and the device as `plugged`.

That is the alternative to a wait loop, not a disguise for one. If the start fails three times within a
minute, the instance stays in "failed" instead of starting for ever.

By hand works too, of course:

```bash
systemctl start h713-tv@video1     # or
/usr/local/sbin/h713-tv            # in the foreground, Ctrl-C exits cleanly
```

**Startup options**

```
h713-tv [-d /dev/videoN] [-c /dev/dri/cardN] [-s SOCKET] [-p PRESET] [-g LUT] [-a AUDIO] [-t DB] [-C CONFIG] [-n]
h713-tv ctl [-s SOCKET] COMMAND [ARG...]

  -d  capture device (without it: search for the driver "sun50i-h713-hdmirx")
  -c  DRM device     (without it: search for the driver "sun50i-h713-afbd")
  -s  control socket (default /run/h713-tv/ctl; the single-instance lock "lock" sits next to it)
  -p  picture preset at the start (standard cinema vivid game computer hdr | none); default standard
  -g  gamma curve for the CRTC, one DE2 bank out of h713-pq (2048 bytes) | none;
      default /usr/local/share/h713-tv/gamma-standard.bin (stock: exponent 2.2)
  -a  audio at the start: auto (follows the picture, the default) | on (forced on) | off (forced silent) |
      none (touch no ALSA card -- for boards without the audio drivers)
  -t  HDMI level trim in the audio DSP in dB, 0 (default) down to -100, in quarter dB; also --hdmi-trim DB.
      This is NOT the volume (that is `ctl volume`), but the fixed trim of HDMI against the device's tones
  -C  configuration file (default /etc/h713/tv.conf): the start mode and where the saved mode lives,
      section 6c. Without the file: start = auto, the mode saved in /var/lib/h713-tv/modus
  -n  only report what was found and exit -- the display is left untouched, and so is the audio.
      Return code 0 = a signal stands, 1 = no signal / a change in flight.
```

**The picture preset and the gamma belong to the start.** Without them the firmware runs with whatever its
registers hold after the reset - and that is not even "standard": contrast and brightness registers empty,
saturation 60 (measured 08.09.). The kernel sends the four stages and the mode in its init sequence, the
nine values are sent by this program once at the start (`-p`, default `standard` = the `[HDMI1]` line of the
vendor INI). Once is enough: the firmware keeps them across source changes, resolution changes and HDMI
off/on (measured: the PQ registers held the cinema values through all three). One trap in that: a `Set` with
the value the firmware already holds internally (50 at the start) writes no register; the five sliders are
therefore nudged by one step and then set, so that the state is established and not merely assumed (picture
identical, measured). The gamma curve (stock: exponent 2.2 in the DE2 stage, which the MIPS itself never
loads) goes to the CRTC as `GAMMA_LUT` - once at the start with the master taken briefly, and with every
picture build; it colours console and video alike, as on stock. The file `gamma-standard.bin` comes out of
`h713-pq show HDMI1 standard --lut` (package G) and is installed with the rest. Counter-check 08.09.: a dark
background image (median 27/255) stood light grey on the wall without the LUT and dark with the curve - the
identity ramp was the wrong picture.

**What is in the journal** (`journalctl -u 'h713-tv@*' -f`):

```
capture         /dev/video1 (sun50i-h713-hdm, H713 HDMI receiver)
display         /dev/dri/card1 (sun50i-h713-afbd)
crtc            36, mode 1920x1080
plane           38, NV16, mode hdmi-ring, format proportional
gamma           /usr/local/share/h713-tv/gamma-standard.bin -> GAMMA_LUT (1024 entries, middle 14307/65535)
preset          standard: mode=1 brightness=50 contrast=50 saturation=50 hue=50 sharpness=50 tnr=2 snr=1 dci=2 black=1
audio           hy310hdmi (card 1) + H713 Audio Codec (card 0), events, volume 100 (0.0 dB), HDMI trim 0.00 dB, mute switch Line Out Playback Switch, follows the picture
control         /run/h713-tv/ctl (h713-tv ctl help)
signal          1920x1080p, 148500000 Hz pixel clock
buffer          1920x1080 NV16, line pitch 1920 on panel 1920x1080
picture         plane 38 on, 1920x1080 out of the capture ring
audio           source there, 48000 Hz -- path on, 100 ms of debounce
audio           on, 48000 Hz, volume 100 (0.0 dB), HDMI trim 0.00 dB
...
event           SOURCE_CHANGE (changes 0x1, seq 1)
signal          no signal (the flip pointers stand still)
console         plane off, RGB channel and selector back, console unblanked
audio           silent (no picture)
event           SOURCE_CHANGE (changes 0x1, seq 2)
signal          1280x720p, 74250000 Hz pixel clock
buffer          1280x720 NV16, line pitch 1280 on panel 1920x1080
picture         plane 38 on, 1920x1080 out of the capture ring
```

On a resolution change the short console moment is the source's real signal loss. When the driver reports
the change as not locked yet, the journal says `signal          change in flight -- the geometry is not
settled yet, waiting`, and after forty retries a `warning:` that says what stays and that it keeps asking
every 500 ms. `reload          SIGHUP -- the state is evaluated again` is the answer to `systemctl reload`.

The `buffer` line is the capture RING as the driver reports it (`G_FMT`), not the source signal. On a panel
smaller than the source the firmware scales inside its capture path and the ring is smaller than the
source; then a `ring` line precedes it - `ring            852x478, line pitch 864 -- smaller than the
source, the firmware scales` on the HY300 Pro (1280x720 panel) with a 1920x1080 source - and the plane
takes the ring, which the AFBD scales up to the panel. The refusal `the plane does not take the ring
geometry WxH (larger than the panel PxQ, or an odd height); source SxT -- the console stays` compares the
ring with the panel, never the source with the panel (kernel 0136f).

---

## 6a. Control: `h713-tv ctl`

The daemon listens on the UNIX socket `/run/h713-tv/ctl` (option `-s PATH`). A command is one line, the
answer starts with `ok` or `error`; `h713-tv ctl` prints it and returns 0 or 1.

```
h713-tv ctl status              state: mode, signal, plane/console, buffer, audio (audio/audio cards/
                                 audio source/audio msp/audio level), plus the kernel lines
                                 incap/capture/converter/signal/timings and the cpu_comm lines
                                 rx_calls/eingehend
h713-tv ctl auto                the picture follows the signal (the default without tv.conf); `on` is the same
h713-tv ctl off                 force the console (plane off, master gone, console unblanked), until "auto"
                                 auto/off are saved across restarts -- section 6c
h713-tv ctl console             unblank the console and switch the cursor on, without touching the plane
h713-tv ctl list                every picture control of the capture node, with value and range
h713-tv ctl get CONTROL         read one control
h713-tv ctl set CONTROL VALUE   set one control; menus also by text (set range full, set mode cinema)
h713-tv ctl preset NAME         vendor preset: picture mode + nine controls out of pq_picturemode.ini
                                 (standard cinema vivid game computer hdr; with the device data also
                                 energy_saving and custom). Drops the saved deviations in memory
h713-tv ctl save [off]          save the nine controls, the preset, aspect and zoom (`/var/lib/h713-tv/werte`),
                                 `off` deletes the file. Only here is anything written, not on every `set`
h713-tv ctl aspect [NAME]       how the source is fitted into the panel (auto proportional full 16:9 4:3
                                 zoom); without NAME it is shown. A change rebuilds the picture (~0.5 s console)
h713-tv ctl zoom [off|in F]     the magnifier: `in` enlarges the centre of the picture by a factor
                                 1.0..4.0 (default 2), `off` is the baseline (`out` is gone since 24.09.:
                                 the projection area is `h713-warp ctl zoom`); without an
                                 argument it is shown. A change rebuilds the picture, as aspect does
h713-tv ctl audio [on|off|auto] audio forced on / forced silent / following the picture (default); without a
                                 word it is shown
h713-tv ctl volume [0..100]     volume of the codec (`DAC Playback Volume`, acts on HDMI and on the device's
                                 own tones); 0 = the quietest step, 100 = 0 dB; without a number it is shown
                                 (read back from the card)
h713-tv ctl mute [on|off]       mute: the DSP mute (HDMI) and the codec's switch; without a word it is shown
h713-tv ctl resync              select the source again (S_INPUT 0 = THal_Vp_SetSource HDMI-1)
h713-tv ctl replug              play an unplug and a replug to the source: HPD 300 ms low (S_EDID with
                                 blocks=0), load the EDID again (S_EDID, 4 blocks), HPD high -- ~1 s, blocks
h713-tv ctl warp [status]       whether h713-warp has the video plane, with its counters (6e)
h713-tv ctl rpc NAME [ARG…]     any RPC to the firmware through /sys/kernel/debug/cpu_comm/call
```

Controls (short name -> V4L2 control): `brightness contrast saturation hue sharpness` (0…100),
`tnr snr dci black` (0…3: Off/Low/Middle/High), `range` (`auto|limited|full`, `THal_Vp_SetVideoRange`),
`mode` (`THal_Vp_SetPictureMode`, a menu with the firmware's own names: 0 Vivid, 1 Standard, 2 Mild, 3 Game,
4 Calibrated, 5 Calibrated Dark, 6 Computer, 7 Cinema, 8 Home, 9 Sports, 10 Shop, 11 Animation, 12 HDR,
13 Graphic - kernel 0132). The controls belong to the capture node (`0101`, `0126`); `v4l2-ctl
-d /dev/video1 --list-ctrls` shows the same ones.

**Since 11.09.2026 the preset values come out of the device data**, not out of a table in the program any
more - see section 6d. The table has stayed as the fallback.

**Picture mode and preset are two things.** `set mode` only switches the firmware's mode; it changes
**none** of the nine controls (read statically out of the firmware,
[S14](../../doku/nachtlog/S14-re-picture-mode.md)), the firmware's `Get` RPCs are stubs, and `list`
therefore rightly shows the old numbers after a `set mode`. What the vendor UI does for "cinema" - send the
mode **and** the nine values out of `pq_picturemode.ini` - is what `preset NAME` does: first `picture_mode`,
then `brightness … black` out of the `[HDMI1]` line (standard 1, cinema 7, vivid 0, game 3, computer 6,
hdr 12). `energy_saving` and `custom` have no firmware mode of their own. Game and computer additionally
trigger a window rebuild in the firmware (`SetLowLatency`/`Refresh`).

**`aspect`** is descriptor word 35 through the plane property `aspect` (kernel 0133): how the firmware's
window manager fits a source that is not 16:9. `auto` is the firmware's own rule (it knows 1:1, 4:3 and
2.21:1; everything else is stretched onto the panel - 5:4 and 16:10 included), `proportional` (the default)
keeps the aspect ratio (16:9 unchanged, 4:3 with bars as before, 1280x1024 as a window 285…1635 with bars,
measured 08.09.), `full` stretches, `16:9`/`4:3` force, `zoom` crops. The word is read with the next
publication; a change on a running picture takes the plane down briefly and back up
([S15](../../doku/nachtlog/S15-re-aspect-regel.md)).

**`zoom`** is the descriptor's two windows through the plane properties `src-window` and `dst-window`
(kernel 0133f, `x,y,w,h` in panel pixels): the part of the source the firmware reads and the part of the
capture ring it writes its result into. Nothing here scales. `in F` sends the centre 1/F of the frame as
the source window and leaves the plane over the whole panel - the firmware blows that window up into the
ring (measured 22.09.2026: at F = 2 the centre quarter filled the panel and the test pattern's cell pitch
doubled). `out P` (retired, see below) sent a source window of the frame less two pixels - a source window the firmware calls
*full* makes it skip its scaler, and then nothing moves - plus a destination window of P percent at the
ring's origin, and this program crops exactly that region out of the ring (`SRC 0,0 WxH`, kernel 0133c,
which crops from the first byte only) and places it centred (measured: the whole picture at four fifths,
centred, black band at the end). `off` sends neither. A rectangle as an argument is refused: a window
somewhere else in the ring would need `SRC_X/SRC_Y`. Sizes are rounded down to a whole AFBD block and an
even line count. The firmware sizes, we place; `ctl status` shows both windows and the placement. Read with
the next publication, like `aspect`. Whether the firmware follows is decided on the wall: the scaler's own
register `0x05180034` shows what it last did, not what was last asked, and it has been found stale.

`out P` was retired on 24.09.2026: the DE's picture scaler only enlarges, so the destination window cropped
instead of shrinking. Shrinking the projected picture is `h713-warp ctl zoom`, inside the keystone matrix.

**`replug`** is the HPD cycle out of S12 C: the source is to believe that the cable was pulled and plugged
back in - for a mode that does not lock, or a source asleep on a link it believes to be up. The way is the
V4L2 way of doku/88 §3: `VIDIOC_G_EDID` reads the 512 B (the HDMI 1.4 and the HDMI 2.0 block back to back,
for V4L2 one EDID with four blocks) out of the firmware, `VIDIOC_S_EDID` with `blocks = 0` pulls the HPD pin
down (`ARISC_HDMI_HPD_DOWN`), and after 300 ms (the measured lower bound, M4) `VIDIOC_S_EDID` writes the
same EDID back, which runs the complete stock sequence in the ARISC driver (reset the EDID module, upload,
confirm, audio mode, 5 V, HPD 200 ms low, HPD high). The picture is switched off first (otherwise the ring
freezes on the last frame for a second), and **the EDID that was read is checked before the pin is
touched**: both headers (`00 ff ff ff ff ff ff 00` at byte 0 and 256) and the four block checksums. If the
check fails and there is no earlier good read, nothing happens (`error … without an EDID, HPD is not
touched`); if there is one, the copy goes back. The program blocks for the duration (~1 s, like `rpc`).
Afterwards the source comes back through its own `SOURCE_CHANGE` events - with `ctl off` it stays on the
console. If the second `S_EDID` fails, HPD is left low; the answer says so explicitly, and a further
`replug` takes the copy.

**Where the EDID comes from.** `VIDIOC_G_EDID` goes through `arisc_hdmi_get_edid()`, and that delivers
**nothing after the start** (`ENODATA`) - doku/88 §8 listed the read-back as unmeasured, on 11.09.2026 it
was measured. Without an EDID, HPD is not touched, because HPD low with nothing to upload afterwards leaves
the source staring at a dead port. So there are three sources, in this order: the read-back, else the copy
of the last good read in this run, else **`/lib/firmware/hy310-edid.bin`** (the same 512 B the boot chain
uploads, pulled out of the device by `h713-extract`). Every source is checked the same way: header and four
checksums. Once something has been uploaded, **the read-back works** - so the first `replug` after the start
takes the file, every further one the read-back. The answer names the source it used.

`rpc` is raw on purpose: the firmware's rules apply, and a call the drivers are not prepared for (for
instance `THal_Vp_SetSource` in the middle of operation) can cost the picture. The line may be 158
characters long, and the program blocks for the duration of the call. For everything that has a control,
take the control. Further formalities: `status` (also `st`) reports the **last measurement** out of the
event path and so does not measure itself; `on` is an alias for `auto`; control names as in `list`
(underscores instead of spaces, the server splits on spaces); the socket belongs to root (0660), and a
second `h713-tv` does not start (`/run/h713-tv/lock`).

**The console after switching back.** When the panel is handed back (signal loss, `off`, the end of the
program) and at the start, the program unblanks the console (`TIOCL_UNBLANKSCREEN`) and switches the cursor
on (`ESC[?25h`); on 08.09. the console otherwise stood frozen without a cursor (`fb0/blank` = 4, the cursor
hidden by DECTCEM - the culprit was not found, `consoleblank` is 0).

## 6b. Audio: the audio path follows the picture

The samples run through this program as little as the pixels do. The way is
`HDMI-RX -> MSP-DSP1 -> I2SOUT1 -> the codec's I2S input -> DAC -> loudspeaker`, and three drivers own it
([doku/101](../../doku/101-plan-audio-treiber.md) §1): the capture node reports the state of the source as
the read-only V4L2 controls `H713 Audio Present`/`H713 Audio Rate`/`H713 Audio Compressed` (kernel 0136,
with `V4L2_EVENT_CTRL` on a change), the MSP driver provides the ALSA card **`hy310hdmi`** without a PCM,
with the controls `HDMI Audio Switch`, `HDMI Playback Volume` (quarter dB, -100…0), `HDMI Mute Switch` and
the sysfs files `state`/`levels` (0137), the codec on the card **`H713 Audio Codec`** the controls
`DAC Source` {APB, I2S} and `I2S Rate` {32000, 44100, 48000} (0135). This program is the only place that
knows both halves - whether a picture stands and what the source says about its audio - and therefore
decides only **when** the path is switched. Cards are searched for by their name (the numbers depend on the
probe order, as with `/dev/videoN`), for at most 30 s at one attempt a second, because the MSP driver brings
its island and the DSP firmware up on a schedule of its own.

**The automaton** (the rule out of doku/101 §1 E; "picture" = the video plane is on **or** `h713-warp` draws,
see 6e):

| state | condition | what is set | next state |
|---|---|---|---|
| **silent** | picture ∧ Present ∧ ¬Compressed ∧ rate ∈ {32000, 44100, 48000} (or `audio on`) | `HDMI Mute Switch`:=1 (stays), `I2S Rate`:=rate, `DAC Source`:=I2S, `HDMI Audio Switch`:=1, timer 100 ms | **debounce** |
| **debounce** | after 100 ms the condition is true again | `DAC Playback Volume` unchanged, the codec switch on (unless `ctl mute on`), `HDMI Playback Volume`:=0 dB + trim, `HDMI Mute Switch`:=0 | **on** |
| **debounce** | the condition has become false (the source flapped) | `HDMI Mute Switch`:=1, `HDMI Audio Switch`:=0, `DAC Source`:=APB | **silent** |
| **on** | the condition is false (no picture, no audio, a bitstream, `audio off`, the end of the program) | mute:=1, switch:=0, source:=APB - at once, without debounce | **silent** |
| **on** | the source's rate ≠ the programmed rate | mute:=1, `I2S Rate`:=the new one, source:=I2S, switch:=1, timer 100 ms | **debounce** |

Every change of the path happens **behind the DSP mute** (silent -> change -> loud), because the DSP's
master mute is silent within one sample while routing and rate changes are not (S16). The way up is
debounced, because `Present` flaps during a mode change; the way down never is. The codec's rate **has to**
follow the source's - with 48 kHz in the codec a 32 kHz source stayed silent (S16 20:45) - so a rate change
is a short mute and not a rebuild. The codec refuses `I2S Rate` with `-EBUSY` while a PCM with a different
rate is running (S30 §4.3); the program reports the failure once in the journal and then stands as
`ctl status` shows it.

**Volume and mute** (decision 08.09. 22:10): `ctl volume N` sets the **codec's** volume
`DAC Playback Volume` - it sits behind HDMI **and** the device's own tones, and a volume that changed with
the source would be two volumes. 0…100 is mapped linearly onto the control's range (0 = its smallest value,
100 = its largest; on this codec 63 steps of 1.16 dB, so 50 ≈ -36 dB and 0 = -73 dB, quiet but not off). The
answer is **read** from the card, not repeated from memory; an `amixer` from elsewhere therefore shows up in
`ctl status` instead of being overwritten at the next event, and at the start the volume is not touched. The
DSP controls stay with the automaton: `HDMI Playback Volume` is the fixed level trim of HDMI against the
device's tones (0 dB, the S16 reference; `-t`/`--hdmi-trim DB` lowers it), `HDMI Mute Switch` is the
automaton's silence. `ctl mute on` switches the DSP mute (for HDMI) and additionally the codec's switch if
it has one - the H713 codec has no mixer stage and therefore no `DAC Playback Switch`, its
`Line Out Playback Switch` (the LINEOUT enables in `0x02030310`) is the one that exists; order: whatever
goes quiet goes quiet first, whatever opens up opens up last. A `ctl mute` does not outlive the program on
the codec (the switch is reset on exit), or the next `aplay` would be silent for a reason nobody can see any
more.

**Without the drivers** everything runs as before: if one of the two cards or one of their controls is
missing, the audio part is switched off after 30 attempts with a clear sentence
(`audio stays off after 31 attempts in 31 s: missing: the card "hy310hdmi" …`), `ctl status` keeps saying
so, and the picture notices nothing - no ALSA call of this program lies on the way to the wall. If only the
three V4L2 controls are missing (a kernel without 0136), there is no automaton, but `ctl audio on` sets the
path by hand; if `V4L2_EVENT_CTRL` is missing, the question is asked every 250 ms. `-a none` opens no card
at all. `ctl status` shows three lines that have to agree: `audio` (what the program decided),
`audio cards` (what the cards really hold, read back), `audio source` (what the capture node reports), plus
`audio msp state=…` and `audio level …` out of the MSP driver's sysfs.

## 6c. The start mode and saving it: `/etc/h713/tv.conf`

Until 11.09.2026 the service always started in `auto` (doku/60, Marco 09.09.): there was no way to bring the
projector up on the console on purpose and switch to HDMI only when told, and a `ctl off` did not survive a
restart. Both are settings now - in **`/etc/h713/tv.conf`**, not in `/etc/h713/tvconfig` (that is the
directory of the extracted PQ files, doku/107 §8). The file is read once at the start; the option `-C` names
a different one.

```
# /etc/h713/tv.conf -- "key = value", # comment
start = last             # auto | manual | last
#state = /var/lib/h713-tv/modus     # or none
```

| `start =` | at the start | afterwards |
|---|---|---|
| `auto` | as before: if a signal is present it is shown, otherwise the console | `ctl off` / `ctl on` as usual |
| `manual` | **the console**, whether a signal is present or not | `ctl on` (= `ctl auto`) switches to HDMI, from then on the picture follows the signal, until `ctl off` |
| `last` | the mode that was last set with `ctl auto\|on\|off` - like a television that keeps its input; with nothing saved yet: `auto` | like `auto` |

The German words this file used before the tools spoke English, `manuell` and `zuletzt`, still mean exactly
the same and are still accepted without a warning - a device may carry an older `tv.conf`.

**Without the file, `start = auto` applies** - the behaviour before this file. The overlay of the release
rootfs ships it with `start = last`. Unknown keys or values are named in the journal (`warning:
/etc/h713/tv.conf:12: start = "an" unknown …`) and ignored; a typo does not silently become `auto`.

**It is saved in `/var/lib/h713-tv/modus`**, one word, `auto` or `off`. It is written **only when the mode
changes** (the word into a sibling file, `fsync`, `rename` - after a power cut the old word or the new one
stands there, never half a line). `/var/lib`, because this is state and not configuration, and because the
journal is volatile on this device (doku/107 §4). The unit hands the directory over with
`StateDirectory=h713-tv` - under `ProtectSystem=strict` that is the only writable place besides `/run`.
`state = none` switches the saving off, `state = /path` moves it. The mode is written with
`start = auto` and `start = manual` as well; it is only read with `last` - whoever switches to `last` later
gets the state that really was the last one.

What applies is in the journal at the start and in `ctl status`:

```
config          /etc/h713/tv.conf: start = last, saved -> console until "h713-tv ctl on"; the mode is saved in /var/lib/h713-tv/modus
mode            auto -- saved in /var/lib/h713-tv/modus          (after a ctl on that changed something)
```

```
mode            off (console forced)
config          /etc/h713/tv.conf: start=last; saved=off in /var/lib/h713-tv/modus
```

There is only HDMI-1: "switching over" means console <-> HDMI, and `on` does not force a picture without a
signal - the plane needs the source's geometry. `on` is therefore `auto`: show HDMI as soon as there is
something. Binding the manual change to a remote control or a button (doku/60) is prepared for by this, but
is not part of this program.

## 6d. The picture values: computed, chosen, saved

Until 11.09.2026 the six presets stood as a table of numbers in `main.c` and the gamma curve as
`gamma-standard.bin` in the repository - both derived from the vendor data once and frozen ever since. The
values were right (checked again on 11.09.: the curve checked in is byte-identical with the one computed
from *this* device's data, and the presets set every register the way `pq_picturemode.ini` does). What was
wrong was their **origin**: another panel would have had the same table forced on it, two of the eight
presets were missing, and of the five gamma stages there was one. Plan 113 §A turned that around.

**Three layers, applied in this order:**

| # | layer | from where | when |
|---|---|---|---|
| 1 | vendor data | `/etc/h713/tvconfig/`, computed by `h713-pq` | at every start |
| 2 | the user's choice | `preset =` in `/etc/h713/tv.conf` | at every start |
| 3 | the user's deviations | `/var/lib/h713-tv/werte` | at every start, **on top of** layer 1 |

If a layer is missing, the one below it takes over. If everything is missing, the compiled-in table stays -
**a device without the extraction still shows a picture.**

### Who computes: `h713-pq`, once, as a child process

`h713-pq` is Python and reads the eight extracted vendor files. The computation therefore exists **once**
and is not rebuilt in C - maintaining the same computation twice is exactly the trap the saturation
correction of 07.09. came out of (plan 113 §A.3, way (a)).

```
h713-pq --data /etc/h713/tvconfig show HDMI1 standard --json --lut /run/h713-tv/gamma-laufzeit.bin
```

One JSON record on `stdout`, everything else to `stderr` (and thus into the journal). The record carries the
firmware's picture mode number, the nine controls, the gamma exponent, the path of the LUT that was written
- and **all** picture modes of this input with their values, so that `ctl preset energy_saving` needs no
second Python start while it runs. The fields are described in `h713-pq/README.md`.

The child process is started **before** the capture and the DRM device are opened and is only collected when
the curve is needed; the rest of the start runs alongside it. Measured on the device (11.09.): `h713-pq`
needs **430-530 ms**, the devices are open after 25 ms - so the start up to "plane on" goes from
**255-286 ms to 650-680 ms**. That is the price of the origin, and it is far inside the deadline of 2 s
after which it is aborted.

### The gamma curve comes from the board's own TSE

A second `h713-pq` runs beside the first, and it asks for the curve this panel was measured with:

```
h713-pq --data /etc/h713/tvconfig gamma --from-tse normal --project 0x30 \
        --tse /boot/mips/ProjectID_0x0030.TSE --lut /run/h713-tv/gamma-tse.bin
```

The ProjectID is the board's own - `/etc/h713/board` (`project_id = 0x30`), which the installer writes out
of the board profile; without that file the device tree decides (`magcubic,hy310` -> `0x30`,
`magcubic,hy300-pro` -> `0x34`). If anything in that chain is missing, the shipped `gamma-standard.bin`
applies exactly as before and one journal line says which step failed. `-g` still beats all of it, and
`ctl status` names the curve that is up:

```
gamma curve     /run/h713-tv/gamma-tse.bin (this board's own, ProjectID 0x30, state normal)
```

It is **one** bank, loaded on all three channels as before: what this brings is the shape of the panel's
curve, not the per-channel white balance a board may have baked into it (that would need a three-bank
`GAMMA_LUT`).

### When something is missing

Every one of these cases ends in the compiled-in table, one line in the journal and a picture - never in an
abort:

```
warning: picture values  calculator = none -- the compiled-in table applies
warning: picture values  /usr/local/bin/h713-pq: No such file or directory -- ...
warning: picture values  exit code 2 (data directory incomplete?) -- ...
warning: picture values  longer than 2000 ms -- aborted -- ...
warning: picture values  no JSON output (47 bytes) -- ...
warning: preset          "energy_saving" does not exist (standard cinema vivid game computer hdr) -- standard
```

### What is saved, and when

`/var/lib/h713-tv/werte`, next to the `modus` of the same directory, in the format of `tv.conf`:

```
preset      = vivid
brightness  = 50
…
sharpness   = 30
aspect      = proportional
zoom        = in 2.00
```

Written **only by `h713-tv ctl save`**; `ctl save off` deletes the file. Not on every slider movement:
whoever is looking for the right sharpness runs the slider from end to end, and without this rule the device
would remember exactly the intermediate state the power cut happened to catch - and would write to the eMMC
a dozen times for one decision. The mode `auto`/`off` stays the exception and keeps being saved
immediately: it is a decision, not a search.

What is written is what the **driver** holds, not a copy carried along - which also fulfils the rule "a
`ctl preset` discards the saved deviations" without any bookkeeping: after a preset the driver holds the
preset's values, and those are exactly what a later `save` writes. The file goes to its place through a
sibling file with `fsync` and `rename`.

**The line `preset =` is what decides whether the values fit.** Saved values are deviations *from a preset*;
laying `vivid`'s numbers over a start in `cinema` would silently have turned `cinema` into `vivid`. So they
are applied when they belong to the preset being started, and otherwise named in the journal and left alone:

```
warning: saved           saved for preset energy_saving, starting with standard -- not applied
```

With `preset = last` in `tv.conf` - the setting this was built for - the two always agree.

A saved value outside a control's range is dropped **on its own**, with its line number; the other eight
still apply. The range is the driver's (`VIDIOC_QUERY_EXT_CTRL`), not a second table:

```
warning: /var/lib/h713-tv/werte:12: sharpness = 500 is outside 0..100 -- dropped
warning: /var/lib/h713-tv/werte:15: dci = 9 is outside 0..3 -- dropped
warning: /var/lib/h713-tv/werte:17: the plane does not know aspect = "quetschen" (auto proportional full 16:9 4:3 zoom) -- dropped
```

### The keys in `tv.conf`

```
preset     = NAME | last     # NAME out of ctl help; last = the saved preset. Default standard
data       = DIR | none      # default /etc/h713/tvconfig; none = do not use the device data
calculator = PATH | none     # default /usr/local/bin/h713-pq; none = do not compute
```

The German key names of the releases up to v0.8-beta - `zustand`, `daten`, `rechner` - are still accepted
without a warning, so an existing `tv.conf` keeps working; they go out after `v0.9`.

On the command line they are called `-p`, `--data` and `--calculator`; on top of that `--input` (default
`HDMI1`) and `--lut` (default `/run/h713-tv/gamma-laufzeit.bin`). The command line has the last word, the
file is the standing setting. `-g` still counts as an explicit order and beats the curve from `h713-pq`.

What applies is what `ctl status` says:

```
picture values  8 presets from /etc/h713/tvconfig (h713-pq, 433 ms), gamma 2.20, LUT 2048 bytes
preset          vivid (from the device data)
saved           /var/lib/h713-tv/werte: preset=vivid brightness=50 contrast=55 saturation=60 hue=50 sharpness=30 tnr=2 snr=1 dci=3 black=1 aspect=proportional
```

## 6e. The warp: `h713-warp` draws, this program shows

Since the keystone (plan stage S5) there is a **third display mode** beside plane-on and console:
*warped*. `h713-warp` renders the capture through the GPU, this program puts the result as NV12 on the
**video** plane with `hdmi-ring` 0, so the ring is off and the firmware's picture controls act on the warped frame
(24.09.; until then RGB on the primary plane) - which by itself returns the encoder's selector to
RGB (`afbd.c:864-867`). With all eight keystone values at 0 the daemon does not open the render node
at all, so the wall shows exactly what it showed before. The two speak over this program's own
control socket, in its own language, the file descriptors in `SCM_RIGHTS` on the same connection:
`warp claim` answers `ok WIDTH HEIGHT PITCH nv12 CHROMA_OFFSET` and three NV12 dumb buffers of the mode, the chroma
plane below the luma in the same buffer;
`warp frame N` carries the daemon's out-fence and commits buffer N with `IN_FENCE_FD`, answering
`ok` or `ok busy` when the previous commit is still in flight (that frame is dropped);
`warp release` gives the panel back. The connection is the lifetime - a daemon that dies leaves a
hangup and the ring comes back by itself. While the warp is on, `h713-tv ctl zoom` is refused with
`error the warp is on - use h713-warp ctl zoom`, and `h713-tv ctl off` releases the warp. `ctl status` says
`picture warped (h713-warp draws on the video plane)`, and `ctl warp status` gives the plane, the geometry
and the three counters (commits, busy, refused) without claiming anything.

**The audio counts a warped picture as a picture** (fixed on the device, 22.09.2026). `audio_evaluate`,
`audio_settled` and `audio_tick` were given `d->on`, the video plane's state; while the daemon draws, that is
false and `d->warped` is true, so a source event during a warp - a player switching from 48 to 44.1 kHz - was
evaluated as *no picture* and muted the path with a pop. All five call sites pass `d->on || d->warped` now. A
warp must never mute the source.

## 7. The descriptor, the firmware and what the program sees of it

Every switch-on of the plane with a new geometry **publishes the VidDec descriptor anew** (kernel 0117), and
the firmware answers with a complete rebuild of its window chain: scaler, window, colour converter, capture
enable. The capture goes off briefly while that happens, the capture driver puts the colour converter back
and enables it again (0121-0123). All of that happens in the kernel; this program sees it only as
`V4L2_EVENT_SOURCE_CHANGE` and then asks `QUERY_DV_TIMINGS`.

That question has three answers:

| answer | meaning | program |
|---|---|---|
| a timing | the signal stands, the geometry is known | build the buffer, plane on |
| `-ENOLINK` / `-ENODATA` | no signal | plane off, console |
| `-ENOLCK` | a change in flight: the firmware's signal info and the capture block still say different things | ask again (50 ms x 40), leave the wall alone |

After the fortieth retry what stands stays: a picture is real HDMI content and is not switched off because
of an undecided question; with the console up, the question is repeated every 500 ms, because then no event
has to come any more. The earlier ring watch (a sample series after switching on) has been dropped: since
0121 the flip pointers move without a running capture as well, so it measured nothing
([doku/nachtlog/S12](../../doku/nachtlog/S12-hy310-tv-review.md) A4).

**The console being back also means the console being usable.** At the start and at every handback the
program unblanks the console (`TIOCL_UNBLANKSCREEN`, `fb0/blank` = 0) and switches the cursor on
(`ESC[?25h`); since 0127 the kernel keeps the cursor timer alive even when `console_trylock` happens to
fail.

## 8. Limits

- **One signal, one source.** HDMI-1 through `SetSource 3`; the firmware's other inputs are not wired up.
- **Geometry:** at most the panel size, the height divisible by 2. The width may be anything: the ring has
  lines `rowbyte*16` apart (INCAP `0x924`, the width rounded up to 16), the driver reports that as
  `bytesperline` (kernel 0131) and the program builds the buffer with it - 1366x768 runs that way with 1376
  bytes per line (measured 08.09.). What the HDMI firmware locks onto is in its table (`kHalSignalID_*`):
  CEA modes and the usual VESA modes at 60 Hz; not the 120 Hz variants and not 1600x900.
- **`rpc` is raw.** The call blocks the program for its duration, and the firmware checks nothing for us.
- **`preset`** is not a firmware function but a mode plus nine `Set` RPCs; whoever wants other values sets
  them one by one and saves them with `ctl save` (section 6d).
- **The gamma curve is loaded once, at the start.** A `ctl preset` onto a mode with a different gamma stage
  sets the nine controls, not the curve - and says so in its answer. In this device's data the case does not
  arise (all eight modes are on stage 3 = 2.2).
- **`HDMI1` only.** `h713-pq` is asked about exactly this input (`--input`); the INI carries the same
  lines for `HDMI1`, `HDMI2` and `HDMI3` anyway.
- **A resolution change costs ~1 s of console** - that is the source's real signal loss during the mode
  change.
- **Audio only with both cards.** `hy310hdmi` and `H713 Audio Codec` are taken together or not at all - half
  a chain (volume without a route, a route without a mute) is not touched; then there is no `ctl volume`
  either.
- **Non-PCM stays silent.** Bitstreams (Dolby/DTS, `H713 Audio Compressed`) are not decoded; the automaton
  switches the path off for them. Rates outside 32/44.1/48 kHz are unknown to the codec control -> silent,
  with a reason.
- **The codec switch is an analogue switch.** `Line Out Playback Switch` has no ramp control on H713 (0x31c
  is missing); whether the switching clicks is to be heard on the device. If it does, the candidate list
  `audio_codec_mutes[]` in `main.c` is the one place where the switch is taken out again (then `ctl mute` is
  the DSP mute alone).

## 9. References

* [doku/78](../../doku/78-nachtplan-hdmi-switch.md) appendix A - the complete sequence, A.4 the target picture
* [doku/86](../../doku/86-video-plane-nv16.md) - the video plane, register by register
* [doku/88](../../doku/88-v4l2-hdmirx.md) - the V4L2 receiver, buffer model and events
* [doku/101](../../doku/101-plan-audio-treiber.md) - the audio as drivers: packages A-F, the binding control
  and card names
* [doku/nachtlog/S32](../../doku/nachtlog/S32-treiber-e-hy310tv.md) - package E: the automaton as a table,
  the test recipe
* [doku/nachtlog/S16](../../doku/nachtlog/S16-hdmi-audio.md) - the measurements the order
  silent -> change -> loud comes from
* [doku/nachtlog/K4-hotplug.md](../../doku/nachtlog/K4-hotplug.md) - signal loss and return on the device
* [doku/nachtlog/D-abnahme-board.md](../../doku/nachtlog/D-abnahme-board.md) - the plane on the device, and
  the one-second beat that does **not** carry what was ascribed to it
* [doku/nachtlog/D-cstride-fix.md](../../doku/nachtlog/D-cstride-fix.md) - the same table read anew: the
  pointer triggers the firmware event, not the content, and the only measured bound is "< 1 s"
* [doku/nachtlog/A6-4-aufloesungswechsel.md](../../doku/nachtlog/A6-4-aufloesungswechsel.md) - the
  resolution change without an event (§8)
* [doku/nachtlog/F-korrektur.md](../../doku/nachtlog/F-korrektur.md) - **the valid acceptance procedure**,
  the test build, what was wrong about the 3 s constant
* [doku/nachtlog/F-startklar.md](../../doku/nachtlog/F-startklar.md) - the test build and the corrected
  assumptions of the early 07.09.; §2.2, §2.4 and §5 are superseded by `F-korrektur.md`
* `analyse/kms/hdmi_plane_test.c` - the same by hand, for a single attempt
* `legacy/userspace/hy310-hdmird/` - the predecessor out of the legacy world (read, not ported: its job, the
  firmware init, is done by the drivers 0091/0092/0094 now)
