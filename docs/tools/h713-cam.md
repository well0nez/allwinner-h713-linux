# h713-cam — talking to the internal camera

`h713-cam` reads and grabs from the projector's built-in camera — a Realtek `0bda:5803` "Generic HD camera"
on USB, UVC class, one format (YUYV 4:2:2, 640×480). Stock firmware uses it for autofocus (`doku/94`); this
tool is the manual equivalent, for probing controls and pulling a still image.

```
h713-cam probe                    # driver, formats, frame sizes
h713-cam controls                 # every control, with range and current value
h713-cam get exposure             # read one control (name or 0x-ID)
h713-cam set brightness 100       # write one control
h713-cam grab                     # single frame to /data/cam.png
h713-cam grab /tmp/x.ppm --warm 30
```

Control names for `get`/`set` may be abbreviated (`exposure`, `bright`); an ambiguous match is reported with
the candidates instead of guessed.

## Why it searches for the node instead of assuming `/dev/video2`

`/dev/video2` is only the camera's node *today* because Cedrus (`video0`) and the HDMI receiver (`video1`)
happen to load first — a probe order, not a guarantee. `h713-cam` instead walks
`/sys/class/video4linux/*/name` for a match and picks the entry that reports `VIDEO_CAPTURE`, since the same
camera also exposes a second, metadata-only node under the identical name. `--dev` overrides the search.

## Why `grab` writes back the exposure before it reads a frame

Freshly loaded, the camera's first frames are black (Y ≈ 5, plain sensor noise) — even after 90 discarded
frames, even with a bright picture already on the wall. The moment *any* control is written, the very next
frame is normally exposed (Y ≈ 187) and the exposure automatic runs on its own from there. `grab` therefore
writes the current exposure value back unchanged before it streams, and warns explicitly if the result still
comes back darker than that. Measured 11.09.2026 (`analyse/beamer-cam/README.md`, `foto-e313.png`).

## Honestly, where this stands

On the device (2026-09-12): the node is found by name — it was `/dev/video1` that day, with the HDMI receiver
pushed to `video3` — the controls read back, and `grab` of the lit wall came back properly exposed, mean
brightness Y = 88.7, in 3.2 s (`analyse/beamer-cam/p6-wand-20260912.png`).

No PIL, no `v4l2-ctl`, no `ffmpeg`: the release rootfs carries none of them, so PNG encoding uses the standard
library's `zlib` and the YUYV→RGB conversion is plain-Python BT.601 — slow on the A53 (seconds, not
milliseconds) but it runs wherever `python3` does.

Details: doku/94-fokusmotor-endschalter.md, analyse/beamer-cam/README.md, doku/61-todo.md
