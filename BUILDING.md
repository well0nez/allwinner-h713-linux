# Building

One command turns a clean clone into a flashable image:

```bash
release/build-all.sh --version v0.5-beta --vendor <output of h713-extract>
```

Eleven steps: TF-A BL31 · U-Boot (release, installer, and `sunxi-fel`) · kernel with the patch series ·
AIC8800 modules · a pinned Debian keyring · an arm64 sysroot and `h713-tv` cross-built against it ·
the Debian 13 root filesystem · the ext4 inputs · the image · verification · a build stamp. With
`--vendor` it ends in `ALL GREEN` - the self-test compared every extracted file against the image -
or it stops. Without `--vendor` it ends after the structural check, which is a weaker statement.

Roughly 20 minutes from cold (including the kernel tarball download), about 10 with a kernel tree already
built. Everything runs in a container; **nothing is built on your host**.

## Prerequisites

- `podman`, `python3`, `curl`, `ar`, `tar`, `sha256sum` on the host
- the build container `h713-build` - **[docs/build-container.md](docs/build-container.md) is the recipe**,
  one `podman run` plus two `apt-get` lines. Skipping the LLVM 20 step there makes U-Boot fail at
  `u-boot.srec`, which does not look like a missing toolchain at all
- the submodules checked out: `git submodule update --init` (see below)
- roughly 15 GB free

`--vendor` is optional. Without it the image is still built and structurally checked, but the vendor
placeholders stay empty and the full self-test cannot run. With it, the self-test compares every
extracted file against the image.

## Useful switches

| Switch | Effect |
|---|---|
| `--dry-run` | say what would be built, build nothing |
| `--skip-bl31`, `--skip-uboot`, `--skip-kernel`, `--skip-rootfs` | reuse what is already there |
| `--wifi-env FILE` | put your own `/etc/h713/wifi.env` into the image instead of the public default |
| `--jobs N` | parallelism (default: all cores) |

The skips are for iterating. A release build should run without them: since 2026-09-12 the script wipes
the TF-A and U-Boot build directories first, because a stale BL31 from an earlier build silently shipped
in three images before anyone noticed ([STATUS.md](STATUS.md), *Boot chain*).

## Boards

`--board <id>` (default `hy310`) builds for one board. Everything that differs between devices is in
`boards/<id>/board.env`: the installer profile, the kernel DTB the FIT carries, the U-Boot base
defconfig, and the image name (`<IMAGE_NAME>-<version>`). What a board directory is, and how to add
one from a probe log, is [`boards/README.md`](boards/README.md); `bash boards/check.sh` holds every
one of them against its installer profile. The same ids work for the parts:
`BOARD=<id> mainline/build/build.sh kernel`, with `ddr3` and `lpddr3` still accepted as aliases for
the two HY200 boards.

**An image is built only for a board somebody has run.** A board that is not `STATUS=verified` is
refused with the rule it comes from:

```
no image for a board nobody has tested (doku/121 §5): boards/hy300-t08 is STATUS=profile-only.
```

A verified board that names no installer profile is refused as well, because `h713-install`
identifies the device before it writes and would have nothing to identify it against. Today that
leaves exactly one board: `hy310`. The other five are `profile-only` or `partial` - including the
HY200 bench board, which cstenger has booted in his own tree but on which no build of ours has ever
run. Four of the five now carry an installer profile read out of a stock image; that describes the
board, it does not test it, and `--board` still refuses them. The table is in
[STATUS.md](STATUS.md), *Boards*.

There is one named way past that refusal, and it does not weaken it: `--test-image`. A board that is
`partial` or `profile-only` but has a `PROFILE`, a `KERNEL_DTB` and a U-Boot base can be built for on
purpose, as a **test image** - `<IMAGE_NAME>-<version>-TEST`, marked `test_for: "<profile>"` in its
table, saying so in its banner, its stamp and its README. `h713-install` writes it only on that very
board and only with its own `--test-image` ([docs/tools/h713-install.md](docs/tools/h713-install.md)).
It is a build for one person - the board's owner, who holds a full dump as the way back - not a
release, and it changes nothing we claim: the board's line stays `partial` or `profile-only` until
that owner reports a green run.

What a board below `verified` does get is everything that reads and nothing that writes: an installer
profile wherever a stock image or a dump exists for it, its DRAM block written down in
`boards/<id>/uboot.config`, and the read-only probe, which runs from FEL on any H713 without touching
the eMMC ([docs/tools/h713-probe.md](docs/tools/h713-probe.md)). It gets no FIT either: `board.env`
leaves `KERNEL_DTB` empty for a board we have no device tree for, and `build.sh kernel` refuses
rather than ship one written for a different board.

## What comes out

```
mainline/build/out/     bl31.bin, spl-release.bin, uboot-proper-release.bin, hy310-env-release.bin,
                        u-boot-installer.bin, sunxi-fel, h713-kernel.fit, modules/
installer/out/          <name>-{a-bootkette,b-system,c-gptkopie}.img, .tabelle.json,
                        .sha256, -README.txt, .BUILD.txt
```

The `.BUILD.txt` stamp records the series hash, the defconfig hash, the kernel tree digest, the three
submodule commits and a sha256 for each component. Quote it when you report a problem.

Two builds of the same source are **not** byte-identical: TF-A, U-Boot and the FIT embed a build time,
and the AIC8800 module embeds kernel header paths. The tree digest, the series hash and the submodule
commits in the stamp are what actually identify a build.

## Pinned inputs

`mainline/config/versions.env` is the single source of truth: kernel 6.18.38 from kernel.org with a
pinned sha256, the AIC8800 vendor tarball, and the upstream bases the three curated series sit on. The
Debian keyring is pinned by sha256 in `release/build-all.sh`, so a rootfs built today and one built next
year trust the same keys.

## Submodules

Three: U-Boot, TF-A and sunxi-tools, pinned to our forks. Relative URLs, so they resolve next to whatever
account this repo lives under.

If `git submodule update --init` fails on U-Boot, you have a copy of this repository from before the
first release: the fork went public with the release, and there is no way to build the boot chain
without it - `uboot-h713/` is a mirror for reading, not a source tree. Take a release image instead, or
wait for the tag.

TF-A carries submodules of its own (`contrib/*`). They are not needed for `sun50i_h713`: with and without
them the build compiles the same 119 objects. Only measured boot or TPM support would need them.

## Building parts by hand

```bash
mainline/build/build.sh bl31                  # TF-A
BOARD=hy310 mainline/build/build.sh uboot     # U-Boot for one board
BOARD=hy310 mainline/build/build.sh kernel    # kernel + modules + FIT
```

`BOARD` defaults to `ddr3`, the HY200 bench board this port was brought up on - name the board you
mean. `release/build-all.sh` always passes one.

`build.sh` names its kernel tree after a digest of the inputs (`build/linux-6.18.38-<digest>/`), so
changing the series or the defconfig gives you a new tree instead of a confusing half-rebuild.
How the series is organised, and how to add a patch: [docs/kernel-patches.md](docs/kernel-patches.md).

Details: `doku/50-befehle.md` (the full command collection, German), `doku/116-plan-release-repo.md` §4a.
