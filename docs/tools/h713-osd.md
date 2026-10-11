# h713-osd - the overlays over the picture

When the volume, the mute, the focus or the input changes, a small overlay appears over the HDMI picture for a
moment - a dark translucent pill with round ends at the bottom centre, as the stock firmware shows its volume.
While muted, a small crossed-out speaker stays in the top right corner. At the end of the focus travel the
arrow of the pressed direction turns red. With a keystone the overlay is distorted like the picture, so it sits
in the picture, not on the panel's straight edges.

`h713-keys` sends the events after each key of the remote; by hand:

```
h713-osd ctl volume 40
h713-osd ctl mute on 40          # ... mute off 40
h713-osd ctl focus up edge
h713-osd ctl input console
h713-osd ctl status              # what is shown, the channel to h713-tv, the matrix, the last refresh's times
```

## /etc/h713/osd.conf

Read again when it changes, no restart:

| Key | Default | Values |
|---|---|---|
| `place` | `bottom` | `bottom`, `top-right`, `center` |
| `look` | `pill` | `pill` (dark translucent panel), `bare` (lines with a soft shadow) |
| `scale` | 1.0 | 0.5..2 - 720p and 1080p panels get the same proportions at 1.0 |
| `seconds` | 2.5 | 0.5..10 - how long an overlay stays after the last event |

The look was chosen on mock-ups on 11.10.2026: the pill at the bottom; a square card in the middle was rejected.

## How it reaches the panel

`h713-tv` stays the only program that owns the display. It hands two ARGB8888 buffers the size of the panel to
h713-osd (`osd claim`), lays the one h713-osd names over the picture (`osd show N`, the primary plane at zpos 2,
kernel 0251) and puts the console back before it lets the display go - a signal lost, `h713-tv ctl off` - so the
console never comes back under an overlay. Over the warp the change goes with the warp's next frame. Details:
`userspace/h713-osd/README.md`, `userspace/h713-tv/README.md` 6h.

A refresh takes 7-15 ms on the HY310 over a strong keystone (measured 11.10.2026).

## Not yet

- No overlay on the console (no signal): it waits for the picture (TODO 2.46).
- No fade-out.
- Not in the image yet (`rootfs/install-projekt.sh`).
