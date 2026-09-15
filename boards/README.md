# `boards/` — one directory per board

This repository builds firmware for more than one H713 device. Everything that differs between
devices lives here, in one directory per board; everything else in the tree is shared.

A board directory is **description, not permission**. Having a directory here means we have written
down what we know about that board. It does not mean anyone has ever booted it.

## What a board directory contains

```
boards/<id>/
  README.md        what this board is, who verified it, where every number came from
  board.env        machine-readable facts, sourced by build/build.sh and release/build-all.sh
  uboot.config     the board fragment for U-Boot: DRAM settings, device tree, board name
  kernel.config    optional kernel config fragment (empty for every board today)
```

The `<id>` is the directory name and is also `BOARD_ID` inside `board.env`; it is what you pass as
`BOARD=<id>` to `mainline/build/build.sh` and as `--board <id>` to `release/build-all.sh`.

### `board.env`

Sourced as shell, so `KEY=value`, no spaces around `=`. Keys:

| Key | Meaning |
|---|---|
| `BOARD_ID` | the directory name, repeated so a stray copy is caught |
| `STATUS` | `verified`, `profile-only` or `partial` — see the honesty rule below |
| `PROFILE` | the installer profile module in `installer/h713/profiles/<name>.py`, empty if there is none |
| `IMAGE_NAME` | base name of a release image: `<IMAGE_NAME>-<version>-a-bootkette.img` and so on |
| `KERNEL_DTB` | the DTB that goes into the FIT, without `.dtb`; **empty** when we have no DTS for the board |
| `UBOOT_BOARD` | the U-Boot base defconfig for this board, without the `_defconfig` suffix |
| `VERIFIED_BY` | who ran it on which device, with the date — empty unless `STATUS=verified` |
| `KERNEL_DEFCONFIG` | optional: overrides the kernel defconfig from `mainline/config/versions.env` |
| `UBOOT_DEFCONFIG` | optional: overrides the `<UBOOT_BOARD>_defconfig` derived from `UBOOT_BOARD` |

`STATUS` follows the vocabulary of the installer profiles
(`installer/h713/profiles/__init__.py`, `STATUS_VALUES`):

- **verified** — an owner has run this firmware on this board and reported it green. `VERIFIED_BY`
  names the person, the board and the date.
- **profile-only** — we have a complete description (a stock image, or somebody else's defconfig),
  but nobody has run our firmware on the hardware.
- **partial** — the description itself is incomplete: some values are unknown or borrowed.

### `uboot.config`

The board's U-Boot facts as a Kconfig fragment: the DRAM settings (`CONFIG_DRAM_*` plus the DRAM type
selector), `CONFIG_DEFAULT_DEVICE_TREE`, and the board name in `CONFIG_IDENT_STRING`. **No build reads
it.** The U-Boot fork carries a base defconfig per board that has one (`configs/<UBOOT_BOARD>_defconfig`,
e.g. `hy310_defconfig`), and `mainline/build/uboot-build.sh <O> <base> [role]` merges a *role* fragment
from the fork (`configs/fragments/h713_<role>.config`) over that base — see `docs/uboot/README.md`. This
file is the record of what the base defconfig says about the board, in one place next to the profile:
`boards/check.sh` compares its `CONFIG_DRAM_CLK` and DRAM type with the installer profile, and a new
board's DRAM words are written here first, from the probe log, before anyone builds a defconfig from them.

Two conventions keep the DRAM block honest:

1. **A value that is not this board's own is marked `# not this board's`** in the line above it,
   together with where it came from. A board fragment full of unmarked values reads as measurement.
2. **`PARA2` and `TPR13` are never taken from an image.** The vendor flashing tool patches those two
   words on the way onto the eMMC, so a `boot0` out of an `update.img` carries the *unpatched* pair
   and a dump from a running device carries the real one (`docs/tools/h713-probe.md`). Where we only
   have an image, the patched pair of the HY310 is used and marked.

Useful when reading a DDR3 fragment: the sun50iw12 DRAM driver computes the DDR3 timing registers
from `CONFIG_DRAM_CLK` and ignores `TPR0`–`TPR2`, `MR0` and `MR2` on that path
(`arch/arm/mach-sunxi/dram_sun50iw12.c`, `iw12_set_timing()`). They are kept in the fragment because
they are what the board's own boot0 contains, but they do not reach the hardware. On the LPDDR3 path
they do.

## The honesty rule

> **No image for a board nobody has tested** (`doku/121` §5).

`release/build-all.sh` refuses to build an image unless `STATUS=verified`. That is not a safety
interlock, it is a truthfulness one: an image is a promise that the thing boots, and we can only make
that promise for a board whose owner has booted it and said so.

What follows from the rule:

- A board may have a `uboot.config` without ever getting an image. The probe (`h713_probe_defconfig`,
  its own 624 MHz base, no role) is read-only and is exactly what an untested board is for.
- `STATUS=verified` needs `VERIFIED_BY` filled in with a person, a board and a date. "It compiles" is
  not verification, and neither is "it booted in somebody else's tree" unless that somebody is named.
- We hand strangers a finished file, not an instruction list, and we never claim their device is
  supported before they have reported a green run. Until then their board's line reads
  `profile-only`.
- Nothing here restricts what an owner does with their own device. The rule limits *our* claims.

## From `partial` to `verified`: the test image

A board cannot become `verified` without somebody running a build of ours on it, and until now there
was nothing for that somebody to run. `release/build-all.sh --test-image` closes that circle:

1. **`partial` / `profile-only`** — the board has a directory, a `PROFILE`, and (for a test image)
   a `KERNEL_DTB` and a U-Boot base of its own. No release image is built for it.
2. **Test image** — `release/build-all.sh --board <id> --test-image --version vX.Y` builds
   `<IMAGE_NAME>-vX.Y-TEST` and has `h713-mkimage` write `test_for: "<profile>"` into its table.
   The name, the banner, the `.BUILD.txt` stamp and the image README all say TEST. `h713-install`
   accepts it only on that board and only with `--test-image`; on any other board it refuses and
   names the board it was built for. It goes to the board's owner, who takes a full dump first —
   that dump is the way back — and it is not a release for anybody else.
3. **`verified`** — the owner reports a green run: `STATUS=verified`, `VERIFIED_BY` gets their name,
   their board and the date, and from then on the board gets ordinary images.

Between 2 and 3 nothing about our claims changes. A board that has only been handed a test image is
still `partial` or `profile-only` in `board.env`, in STATUS.md and in every sentence we write.

## Adding a board from a probe log

A board that nobody here has held can still get a directory. The whole input is one
[`h713_probe`](../docs/tools/h713-probe.md) log, which the owner produces over FEL without writing a
single byte to their device:

```
sunxi-fel uboot u-boot-h713-probe.bin      # from the release; the probe never writes
```

1. **Pick an id** — lower case, hyphens, the name on the silkscreen if there is one
   (`hy300-t08`, `hy200-qz713df-a1`). Create `boards/<id>/` with the four files.
2. **DRAM** — the probe prints the 24 words of the vendor boot0 header. Copy them into
   `uboot.config` as `CONFIG_DRAM_CLK` (decimal MHz, from `dram_clk`) and `CONFIG_DRAM_SUNXI_*`
   (hex, one line each), and select the type: `CONFIG_SUNXI_DRAM_H713_DDR3_STOCK=y` for
   `dram_type 3`, `CONFIG_SUNXI_DRAM_H713_LPDDR3_STOCK=y` for type 7. A log read off the device
   already has the patched `para2`/`tpr13`, so nothing has to be borrowed.
3. **Device tree** — a new board has no DTS of ours. Point `CONFIG_DEFAULT_DEVICE_TREE` at
   `allwinner/sun50i-h713-hy200-qz713df-a1`, mark the line `# not this board's`, and leave
   `KERNEL_DTB=` empty in `board.env`. A probe build does not drive the panel, so a foreign DT is
   harmless there; a release is not built from it, because `STATUS` is not `verified`.
4. **Profile** — if the owner also posted a dump or a stock image, add
   `installer/h713/profiles/<id>.py` and name it in `PROFILE=`. Without one, leave `PROFILE=` empty.
5. **`board.env`** — `STATUS=profile-only` if the description is complete, `partial` if values are
   still missing or borrowed; `VERIFIED_BY=` stays empty either way.
6. **README.md** — one table of facts, each row with its source (issue number, image name, log line).
   Anything you could not measure goes under "What we do not know" rather than being left implied.
7. **`bash boards/check.sh`** — it must stay green.

When the owner reports a green run on a build of ours, and only then, `STATUS` becomes `verified`,
`VERIFIED_BY` gets their name, their board and the date, and the board can have an image. What they
run to get there is a test image (above), not a release.

## Checking the directory

```
bash boards/check.sh
```

It syntax-checks the scripts, verifies that every `board.env` carries the required keys with sane
values, that `STATUS=verified` is backed by a `VERIFIED_BY` and a `KERNEL_DTB`, and that every
`CONFIG_DRAM_CLK` matches the DRAM clock of the board's installer profile — the fragment and the
profile cannot drift apart without the check going red.
