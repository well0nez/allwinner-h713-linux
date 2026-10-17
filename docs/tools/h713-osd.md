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

## Two commands of other services

- `power TENTHS standby|off [only] [ALPHA%]` - the power key's countdown (h713-power, about ten times a second): large in
  the middle whatever `place` says, a ring with the seconds left (full at 150 tenths), standby left, off right; `only`:
  no standby on this board, the ring alone. Each line keeps it one second. The answer is `ok unseen` when nothing can be
  seen (no signal, the console; no h713-tv) - h713-power then acts at once.
- `pair` - "hold Left + Right" for 10 s after the remote was forgotten (h713-panel, TODO 2.54).
- `launcher SEL;NOW;[>]icon:label;...` - the launcher (h713-keys): an **opaque page** over the whole
  panel, not an overlay over the picture (Marco, 15.10.2026: it must have a ground): the ground `0xff0b0e0d`, the list of "Launcher C" in
  the column on the left, the rest calm, everything inside a safe margin of 5 % on each side (96 / 54 px at 1080p); it stays until
  `launcher close`. `SEL` the chosen row (the lit pill `0x1c2321`, the colours of h713-settings), `NOW` the second half of the header
  (`HDMI 1080p60`; the clock is h713-osd's), then the rows - icon one of `hdmi film globe desk sliders power`, a `>` in front puts a
  row in the group at the foot (Standby), which comes last; up to six. `launcher SEL` alone moves the selection. The answer is
  `ok unseen` when nothing can be seen (then it is not open), `error no font` without the face (`H713_OSD_FONT`, else
  `/usr/share/fonts/truetype/quicksand/Quicksand-Medium.ttf` from the `desktop` profile's `fonts-quicksand`).
  The page is cut into tiles - the header, one per row (124 units), the foot, the gap in between, each in a left part (the column) and a
  right part (the ground) - and only the tiles that changed are drawn again and put into a buffer: a move of the selection costs two
  tiles of the column, not the page, which matters over a keystone (the pre-distortion walks every pixel it puts; the page is two million
  pixels). The buffer that is not shown is filled in the idle time after a refresh. Each tile is put from a source with two rows and
  columns of its neighbours around it, writing only the panel pixels whose source lies in the tile (and only the pixels that count):
  otherwise the bilinear sample at its edge sees nothing outside and a seam or a hole shows at every boundary - in an opaque page a
  hole shows the picture. Volume, mute and the power countdown are drawn into the page and ride in the tiles they touch.
  `H713_OSD_TRACE=1` adds a journal line per refresh and prefill with wall-clock times.

## The page channel (package S)

A program that has a whole page to show - [h713-settings](h713-settings.md) - does not claim h713-tv's overlay channel (there is
one holder, this daemon); it asks for a canvas. The connection **stays** and is the page's life:

```
page open                 -> ok W H PITCH argb8888    plus one memfd (SCM_RIGHTS) of PITCH x H bytes, ARGB8888, straight alpha,
                             the panel's size: the page draws into it. "ok unseen" when nothing can be seen (no signal, no
                             h713-tv): no page, and its program takes the keys from nobody. "error the launcher is open" / "the page is open".
page show X Y W H         -> ok | ok waiting          this rectangle is new (its rows, and its columns X..X+W; W of 0 or less: the full width)
page hide                    the page goes (so does the end of the connection)
```

The daemon copies the new rows into its canvas, puts them into the buffer h713-tv shows - straight, or through the keystone's
matrix as a **band** (two neighbour rows for the sampling, only the panel pixels whose source row lies in the band written: no
seam, the launcher's reasoning, measured by a test that compares a page shown in pieces with the same page shown at once) - and
answers after `osd show`: without an HDMI signal a page is shown over black (`osd show N cover`, pre-distorted with warp.conf's keystone
when that warps; over the straight ring too, which it hides - the second before the warp's claim at every start, so the launcher no longer jumps, `doku/214` §3), and the launcher opens there too (measured 16.10.2026: Home over the console puts the launcher on the wall, Back brings the console back, `doku/213` §1). `ok waiting` means h713-tv has no picture at the moment and keeps the page for its return (the autofocus
has the panel, a source changes its mode). Popups and the mute badge are not drawn while a page is open; the page covers the
panel, and a launcher does not open over it. `page` in `ctl status` says open or closed. Host tests: `tests/test_page.py`.

The new rows are kept as up to four ranges (one that lies within 24 rows of another joins it), so a row and the note at the foot are
two small puts, not the rectangle around both; each is written a half row wider than it tiles, because a panel pixel reads two source
rows. A whole page that was shown is owed to the **other** buffer too: it is put right after the answer, not at the next key.
The ranges keep the columns too (the union of the shows that make one), so a pill in the middle of the panel is not put from edge to edge.

**Pre-distortion cost** (16.10.2026, from the box: the opaque page through the owner's keystone cost 190 ms mean per key, 288 ms for an
area switch before this change and 66.2 ms mean per key, 102 ms for an area switch after it; `doku/212` §2): the source region is premultiplied once per put together with a **flat map** (per block of 8 x 8 texels the colour, if
the block is one colour); a run of 16 panel pixels whose source texels - with the bilinear neighbours - all lie in flat blocks of one
colour is written as that colour without a division per pixel (the ground of a page is most of it; on the settings page 90 % of the
pixels); and the rows of the premultiply and of the put are cut among up to four threads (`H713_OSD_THREADS=1` for none, the tests;
`H713_OSD_NOFLAT=1` for every pixel through the inverse, the tests). Every result is the pixel the plain loop made: the tests
(`tests/test_page.py`) put the same pages with and without both and want the same buffers, bit for bit; the
launcher's tiles use the same function, and its tests pass unchanged. Host bench of the S3 key mix, weighted mean key to answer: 18.0 ms before, 5.6 ms
with four threads (6.7 two, 8.8 one) - `laeufe/skripte/bench-s3.py`; the board's factor to the host is about 10 (measured on the same keys).

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
console never comes back under an overlay. Over the warp the change goes with the warp's next frame. When the
picture under a shown overlay turns warped or straight by itself (the signal back, the warp switched), h713-osd
notices within a quarter second and draws it again. Details: `userspace/h713-osd/README.md`,
`userspace/h713-tv/README.md` 6h.

A refresh takes 7-15 ms on the HY310 (1080p) over a strong keystone and 5-13 ms on the HY300PRO-G-EU (720p) over
a milder one (both measured 11.10.2026).

## Not yet

- No overlay on the console (no signal): it waits for the picture - decided 11.10.2026 (the console cannot be
  distorted, and an overlay over it would freeze it).
- No fade-out.
- The launcher is not an overlay over the picture any more: while it is open the picture is hidden behind its page.
- In the image since 11.10.2026 (`rootfs/install-projekt.sh` 5i, enabled); an image with it is not built and installed yet.
