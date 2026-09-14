# Building

One command turns a clean clone into a flashable image:

```bash
release/build-all.sh --version v0.5-beta --vendor <output of h713-extract>
```

Eleven steps: TF-A BL31 · U-Boot (release, installer, and `sunxi-fel`) · kernel with the patch series ·
AIC8800 modules · a pinned Debian keyring · an arm64 sysroot and `h713-tv` cross-built against it ·
the Debian 13 root filesystem · the ext4 inputs · the image · verification · a build stamp. With
`--vendor` it ends in `ALL GREEN` — the self-test compared every extracted file against the image —
or it stops. Without `--vendor` it ends after the structural check, which is a weaker statement.

Roughly 20 minutes from cold (including the kernel tarball download), about 10 with a kernel tree already
built. Everything runs in a container; **nothing is built on your host**.

## Prerequisites

- `podman`, `python3`, `curl`, `ar`, `tar`, `sha256sum` on the host
- the build container `h713-build` — **[docs/build-container.md](docs/build-container.md) is the recipe**,
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
without it — `uboot-h713/` is a mirror for reading, not a source tree. Take a release image instead, or
wait for the tag.

TF-A carries submodules of its own (`contrib/*`). They are not needed for `sun50i_h713`: with and without
them the build compiles the same 119 objects. Only measured boot or TPM support would need them.

## Building parts by hand

```bash
mainline/build/build.sh bl31          # TF-A
mainline/build/build.sh uboot         # U-Boot for the default board
mainline/build/build.sh kernel        # kernel + modules + FIT
```

`build.sh` names its kernel tree after a digest of the inputs (`build/linux-6.18.38-<digest>/`), so
changing the series or the defconfig gives you a new tree instead of a confusing half-rebuild.
How the series is organised, and how to add a patch: [docs/kernel-patches.md](docs/kernel-patches.md).

Details: `doku/50-befehle.md` (the full command collection, German), `doku/116-plan-release-repo.md` §4a.
