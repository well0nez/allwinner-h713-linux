# `rootfs/` - the Debian 13 recipe

The root filesystem the image carries, built from a package list and an overlay rather than
captured from a running machine: same inputs, same tree, every time.

| File | What it is |
|---|---|
| `build-rootfs.sh` | the build. `mmdebstrap --variant=minbase` for Debian 13 (trixie, arm64), the packages of `packages.txt` on top, then `install-projekt.sh`. Writes `hy310-rootfs.tar` (what the installer unpacks and what the NFS root is made of), a manifest and checksums, and with `--image-size` an `.ext4` as well |
| `packages.txt` | one package per line, `#` comments. The rule of the file: every line has to trace back to a need written down in the project, no package "just in case". Among them `ping`, `curl`, `wget` and `nc`, so a device can answer "is the network up" from its own end of the cable |
| `install-projekt.sh` | everything of ours that goes into an unpacked tree: the overlay, the kernel modules, `h713-tv` and the other device tools, the units. Usable on its own against an existing tree (`./install-projekt.sh /srv/h713-rootfs`), which is how the NFS root on the bench is refreshed |
| `overlay/` | the files that are simply copied in: `etc/fstab`, `etc/network/interfaces`, the zram and journald settings, the sshd drop-in, `etc/h713/`, the udev rules, and the device scripts under `usr/local/sbin` |
| `tests/` | checks that run on the device, not here: `h713-wifi-check.sh` |

It is built inside the container `h713-build` like everything else - nothing is built on the host -
and `release/build-all.sh` calls it as step 7. Building it by hand is only useful for a bench root;
for an image, take [BUILDING.md](../BUILDING.md).

The result is about 242 MiB, journal in RAM by default, SSH key-only, and it carries no proprietary
file at all: the display, ARISC and Wi-Fi firmware come off your own device while installing
([PROVENANCE.md](../PROVENANCE.md)).
