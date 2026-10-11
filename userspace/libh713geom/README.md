# libh713geom - the keystone geometry

The map that puts the picture on the wall: the eight per-mille corner values, the vendor's keystone matrix, the
projection modes (front, rear, ceiling, rear-ceiling), the screen zoom, and the file `/etc/h713/warp.conf` that
holds them. Taken out of `h713-warp` on 11.10.2026 (TODO 2.44) so that a second program can use the very same
map: the overlay daemon `h713-osd` draws its overlays on their own display plane, outside the warp, and has to
pre-distort them with this matrix so they stand in the picture like the picture itself.

A source library: a program compiles the files it needs into itself (no `.a`, no `.so`) and provides `warn()`
for its journal.

```
geom.h       the interface
matrix.c     the eight values -> the 4 x 4 column-major matrix (a port of the vendor's getKeyStoneMatrix),
             clamping, projection modes (warp_mirror), zoom (warp_effective), warp_point()
config.c     /etc/h713/warp.conf: read (conf_read), written whole and renamed over (conf_write)
inverse.c    the way back: warp_inverse() turns the map into a 3 x 3 homography and inverts it,
             warp_unpoint() takes a panel point back to its source point
tests/       T2 matrix against the reference model in ../h713-keystone/model (matrix_ref.py),
             T3 warp.conf, T4 the way back
```

| Who | Uses |
|---|---|
| `h713-warp` | `matrix.c`, `config.c` - compiled in at the place of the old files; code and data of the binary are bit-identical to the build before the move (only the build ID differs, which hashes the source paths) |
| `h713-osd` (planned) | all three: reads `warp.conf` (and watches it with inotify), builds the same matrix, walks its overlay's outline on the panel with `warp_unpoint()` |

## The way back

The warp draws the source point (x, y) at `warp_point(m, x, y)`. With the quad's z = -1 folded in, that is a
plane homography; `warp_inverse()` inverts it (false for a degenerate quad, determinant below 1e-12), and
`warp_unpoint()` answers: which source point belongs at this panel point? An overlay drawn straight in source
space and sampled through this map lands on the wall as if the warp had drawn it, keystone, zoom and mirror
included. T4 checks the round trip on a 9 x 9 grid for the identity, seven fixed pulls and 200 random clamped
keystones in all four modes: 67 068 points, worst error 8.9e-16 (11.10.2026).

## Tests

`make test` in the container `h713-build`: T2 507 vectors, 0 deviations; T3 the mode survives the file; T4 as
above. The shader test T1 stays in `h713-warp/tests` (it needs GLES).
