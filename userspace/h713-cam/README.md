# h713-cam - talk to the internal camera

One script, Python 3, without dependencies. Realtek `0bda:5803` "Generic HD
camera", UVC, on USB port 1 (VBUS over PL3). One format: **YUYV 4:2:2,
640x480**. Stock uses it for the autofocus (`doku/94`).

```
h713-cam probe                    # driver, formats, frame sizes
h713-cam controls                 # every control with range and current value
h713-cam get exposure             # read one control (name or 0x ID)
h713-cam set brightness 100       # write one control
h713-cam grab                     # still image to /data/cam.png
h713-cam grab /tmp/x.ppm --warm 30
```

The device node is **searched for**, not guessed: `/dev/video2` is the camera
only because Cedrus (`video0`) and HDMI-RX (`video1`) were loaded before it. The
script walks `/sys/class/video4linux/*/name` and takes the node with
`VIDEO_CAPTURE` - the second one with the same name is the metadata node of the
same camera, not a second device. `--dev` overrides that.

Names for `get`/`set` may be abbreviated (`exposure`, `bright`); if the match is
not unambiguous, the script says which ones fit.

## The quirk

Freshly loaded the camera delivers **black** (Y about 5, pure noise), even after
90 discarded frames and with a bright HDMI picture on the wall. As soon as **any
control has been written**, the next frame is exposed normally (Y about 187) and
the automatic runs. That is why `grab` writes the exposure back unchanged once
before the stream. If Y < 16 still comes out, the script says so.

Measured 11.09.2026, evidence `analyse/beamer-cam/README.md` and `foto-e313.png`.

## Why without PIL, v4l2-ctl, ffmpeg

The release rootfs carries none of them (`packages.txt`: "no package for every
eventuality"). PNG comes out of `zlib` in the standard library, the YUYV->RGB
computation is BT.601 in plain Python - a few seconds for 640x480 on the A53, but
it runs wherever `python3` is.

## Origin

Merged on 12.09.2026 out of `analyse/beamer-cam/{camprobe,camset,camgrab}.py`.
The originals stay there as evidence of the measurement. New against those three:
the device search, `controls`, names instead of IDs only, PNG.

What the camera should **do** (autofocus like stock, only with a test image - see
`h713-focus/README.md`) is a task of its own after the release.
