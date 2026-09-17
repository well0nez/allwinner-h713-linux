# `release/` - from a clean clone to a flashable image

| File | What it is |
|---|---|
| `build-all.sh` | the one entry point. `release/build-all.sh --version vX.Y [--board hy310] [--vendor DIR]` runs eleven steps in order: BL31, U-Boot (release, installer, probe) and `sunxi-fel`, the kernel with the patch series, the AIC8800 modules, the pinned Debian keyring, a sysroot with `h713-tv` cross-built against it, the rootfs, the ext4 inputs, the image, the check, and the build stamp. It drives the container `h713-build`; nothing is built on the host |
| `sperr-scan.py` | the push gate. It walks an export for the things that must never leave a private disk - `re/`, dumps, backups, keys, the proprietary firmware file names, anything that looks like a device image - and fails before a push if one of them reached the tree |
| `sysroot-fix.py` | makes a sysroot unpacked with `mmdebstrap --variant=extract` usable for `clang --sysroot`; called from step 6 |
| `repo-skelett.sh` | out of service since v0.5-beta. The published repository is a clone now, and changes are copied into it, committed and pushed. Kept as the record of how the skeleton came about; do not run it |

`--board <id>` reads `boards/<id>/board.env` and enforces the honesty rule: no release image for a
board nobody has tested. `--test-image` is the one named way past it - a board in test gets a
`-TEST` image marked for its own profile, for its own owner to try, and `h713-install` writes it on
that board alone.

What the steps do, what you need installed and how long it takes: [BUILDING.md](../BUILDING.md).
What a release consists of, and what the build stamp means: [RELEASES.md](../RELEASES.md).
