# Kernel patches

The H713 has no mainline kernel support, and this repo does not carry a kernel fork to work around that.
Instead `mainline/build/build.sh kernel` fetches a **pinned upstream tarball** (Linux 6.18.38, checksum in
`mainline/config/versions.env`) and applies a **patch series** to it, in order, with `patch -p1`. Every
patch is a plain file under `mainline/patches/kernel/`, readable and diffable on its own - there is no
history to clone, and adding one is a file, not a rebase.

## The series file

`mainline/patches/kernel/series` lists one patch per line, applied top to bottom; blank lines and lines
starting with `#` are skipped, which is also how the section banners below are written. It has grown from
two projects landing on the same chip and is grouped by **origin and topic**, not by patch number:

| # | Section | What it is |
|---|---|---|
| 1 | Base | the 53 patches that come through cstenger's `main`: well0nez's H713 driver series `0001` - `0022` (carried there with attribution), cstenger's arm64 side `0023` - `0048`, and our lettered follow-ups behind their originals. `0011` was withdrawn on 22.09.2026 - the file stays where it is and `series` carries the reason |
| 2 | Bridge | one patch of ours between his main branch and his display branch |
| 3 | Video-path branch | 18 patches: 17 from cstenger's `h713-display-video-path` (scanout/DECD/IOMMU/MMC/HDMI) plus our follow-up `0078a` |
| 4 | ARISC + cpu_comm | the second co-processor, the ARM↔MIPS IPC kernel API, HDMI-RX callbacks; `0091c` names the EDID version byte what it is, a per-port block mask, and lets a board state it; `0092a` takes the display firmware's two elog addresses from the board instead of from the driver |
| 5 | Focus motor, first pass | limit-switch read path, manual move commands |
| 6 | Display path | geometry, republish-on-change, capture, picture controls, aspect; `0133a` turns the AFBD's three hardcoded handoff words into an optional device-tree property, `0133b` makes the video plane's CRTC rectangle the destination window in the descriptor the firmware scales into; `0136h` - `0136k` make the display firmware's own mode table (`THDMI_ModeDetect` in `database.TSE`) the list the receiver matches against, keep a lock through our own descriptor republish, withhold a timing the firmware's picture window contradicts, and let the source cap follow that table |
| 7 | HDMI audio | clocks, codec-I2S, the MSP DSP driver |
| 8 | pinctrl | EINT mux for the power key |
| 9 | board-mgr | fan tacho by IRQ, an unrelated pinctrl IRQ-bank fix, the NTC-phantom fix |
| 10 | Crypto Engine | binding, devicetree, a vendor-format measurement module |
| 11 | Focus motor, second pass | the limit switch is a range watcher, not an end stop |
| 12 | Wi-Fi | the power-enable line in the devicetree |
| 13 | Release | strips debug facilities from the shipping defconfig |
| 14 | Protection | the fan-stall poweroff, armed again (`0159`); `0159a` holds the fan rail HIGH from the GPIO request on and logs the first RPM reading of a boot |
| 15 | Boards | one DTB name per board: `0160` HY310, `0161` HY300 Pro - each an include of the bench DTS plus model and compatible; `0161a` disables the backlight device on the HY300 Pro, whose PB5 is the LED-boost and fan-rail enable as a plain GPIO; `0161b` gives that board its firmware's elog addresses |

Sections 1 and 3 come through cstenger's tree and are proven byte-identical against it (`doku/116` §4a P1,
`diff -rq` against two independently patched trees: zero differences) - the arm64 side is his, the driver
series `0001` - `0022` in section 1 is well0nez's, carried in his tree with attribution
([PROVENANCE.md](../PROVENANCE.md)). Everything else, the lettered follow-ups included, is this project's
own projector work, dated in `doku/` by section.

## Why the numbers are history, not order

A patch keeps the number it was given when it was written. When a later fix targets an already-numbered
patch, it becomes a lettered addendum - `0005a`, `0013a`, `0014a` - `0014f`, `0024a` - `0024d`, `0078a`,
`0091a` - `0091c`, `0093a`, `0096a`, `0092a`, `0133a`, `0133b`, `0135b`, `0136a` - `0136k`, `0159a`, `0161a`, `0161b` - placed **directly behind its original**, not at the end of the
series, because the patches after it were written against the state the
original plus its addenda leaves behind: `0024a` fixes a register and IRQ number `0024` got wrong, `0024b`
renames the driver it introduced, and everything from `0025` on assumes both are already applied. Moving an
addendum to the end would change what every later patch applies against. The two exceptions in section 9,
`0143`/`0144`, are a generic fix to base patches `0004`/base-defconfig rather than an addendum to one
projector patch, and are numbered on their own merit; `0152` and `0155` were deliberately re-sorted into
their topical sections after being written, with tree identity re-proven each time. A third kind of
exception is `0014d` - `0014f`: they are addenda to `0014`/`0014a` and belong behind `0014c`, but a later
patch, `0106`, rewrites the very lines `0014d` deletes, so behind `0014c` they would break it. They sit
behind `0125` instead, the last patch in the series that touches `cpu_comm` at all, and everything in
between stays byte-identical. The rule is the reason, not the position: an addendum goes wherever the
patches that were written against the old state have already had their say.

## Building it, and adding to it

`build.sh` extracts the tarball into a scratch directory, applies the series with `patch -p1` in file order,
copies `board/hy200_qz713df_a1_defconfig` into `arch/arm64/configs/`, and builds. To add a patch: generate it
against the tree the way the existing ones were made (a `diff -ruN` of two patched trees, not hand-edited),
give it the next free number - or an `NNNNa` suffix if it corrects a specific earlier patch and must sit
behind it - and insert the line in `series` at that position, under the right section banner. Nothing else
needs updating; the next build notices the new file on its own.

That "on its own" is the **tree digest**: `kernel_inputs_digest()` hashes the `KERNEL_*` lines of
`versions.env` (a prefix match, so an unrelated pin bump elsewhere in that shared file does not invalidate
the kernel cache), the `series` file, the board defconfig, any `KERNEL_CONFIG` fragment in use, and every
patch file `series` names - one SHA-256 over all of it. `prepare_kernel` names the extracted, patched source
tree `build/linux-6.18.38-<digest>`, so editing a single patch byte gets you a fresh tree automatically,
never a stale one silently reused, and two different patch sets never collide in the same directory.

`board/hy200_qz713df_a1_defconfig` is the shipping state - `CONFIG_DEBUG_FS` and `CONFIG_DYNAMIC_DEBUG` are
off in it. `board/debug.config` is a fragment for developers only: `KERNEL_CONFIG=debug build.sh kernel`
merges it back on to reach `/sys/kernel/debug/cpu_comm/call` and similar, and writes its output to a
suffixed `h713-kernel-debug.fit` so it can never be mistaken for the release image.

## Next door, not part of any build

`patches/zurueckgenommen/` keeps patches that were dropped from the series, each with the reason - they
are history, not a fallback. `patches/vorschlaege/` holds work in progress by topic: a finding, a test
plan, sometimes a patch that was never applied. Neither directory is read by `build.sh`; both are there
so a decision can be re-read instead of re-argued. `patches/aic8800/` is the Wi-Fi driver's own series
and `patches/libva-v4l2-request/` the VA-API backend's, applied by their own build steps.

Details: `doku/116-plan-release-repo.md` §4a P1, `doku/80-vergleich-baeume.md`.
