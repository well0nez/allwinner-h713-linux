# h713-mkimage

`h713-mkimage` assembles the flashable image from the built pieces - SPL, U-Boot proper, the kernel FIT,
and the two ext4 filesystems - laid out to Layout v3, together with an offset table, checksums and a
readme. Users normally never run it themselves; it produces the image that
[`h713-install`](h713-install.md) writes.

```
installer/h713-mkimage build -o out/hy310-v0.1.img            # image (three pieces) + table + checksums + README
installer/h713-mkimage check out/hy310-v0.1.tabelle.json      # validate a finished image; writes nothing
installer/h713-mkimage tree-boot DIR [--fit FILE]             # only the file tree for hy310-boot
installer/h713-mkimage tree-rootfs DIR                        # only the rootfs placeholders (an overlay)
```

`build` takes `--spl`, `--uboot`, `--env`, `--boot-ext4` and `--rootfs-ext4` to override what it would
otherwise pick up from `mainline/build/out/` and `installer/tmp/`. Next to the image it writes
`<name>.tabelle.json`, `<name>.sha256` and `<name>-README.txt` (the German `-LIESMICH.txt` is gone). The
keys *inside* the table are still the German ones - `h713-install` reads them, and they change only when
the release file names do.

The switches of the old `hy310-mkimage.py` - `--out`, `--pruefen`, `--baum-boot`, `--baum-rootfs` - are
still accepted for one release and print one line saying what they are called now; `hy310-mkimage.py`
itself stays as a forwarder because `release/build-all.sh` still calls that name.

## Three files, not one

The image is `<name>-a-bootkette.img`, `<name>-b-system.img`, `<name>-c-gptkopie.img`, and a
`<name>.tabelle.json` describing where each piece goes - not one continuous `.img`. The reason is a
1 MiB region at LBA 12288-14335 that this SoC's Secure Storage occupies: HDCP keys, the Wi-Fi/Bluetooth
MAC addresses, and the device's serial number. Nothing generates these values and no firmware image
carries them, so overwriting that region is not recoverable.

`h713-install` guards it in software, but the plan for this project always allowed writing the image
with a plain `dd`, the way one flashes a single-board computer - and a user doing that has no such guard.
Measured directly: a continuous image written by hand replaces those bytes with zeroes; splitting the
image into three pieces with a gap where the fourth would go means the bytes simply are not in the file,
so there is nothing for a plain `dd` sequence to overwrite even by mistake. The failure mode changes from
silent data loss on the ordinary path to a deliberate `seek` error on the safety net doing something
unusual - worth one extra command in the instructions and an `h713-install install` that names a table
instead of a single file.

## Placeholders

44 files that must not ship in this repository - 19 display artifacts, the boot logo, 3 firmware blobs,
8 picture-quality tables, 13 Wi-Fi firmware files - sit in the image as placeholders of the exact right
size. The offset
table records where each one lives; `h713-install` overwrites them with what `h713-extract` pulled from
the user's own device. The SSH `authorized_keys` placeholder works the same way but is found through the
finished ext4 filesystem rather than a fixed raw offset, since its location depends on the filesystem
layout, not on the partition table.

The boot logo (`bootlogo.bmp`, 6,220,854 bytes, at the ROOT of `hy310-boot` rather than in `mips/`) is
the one placeholder that may stay unfilled: a dump without a logo, or one too big for the placeholder,
costs a warning and the fill pattern stays where it is - U-Boot then boots without a logo instead of
not booting. A smaller logo (a 720p board's is 2,764,854 bytes) fits and the rest of the placeholder
stays zero, which is harmless because U-Boot takes every size from the BMP header, not from the file
length.

## Self-test

`mkimage-selftest.py` runs the whole path without hardware: it checks the locked region against the
offset table, fills the placeholders with real extracted files, confirms the ext4 reader finds them back
**through the filesystem** - proving the offsets hit the right blocks, not just that a raw write
succeeded - then `dd`s the three pieces onto a sparse disk image and checks that the locked region is
still empty and the GPT shows the expected six partitions. It prints `ALL GREEN` when nothing is red.
The two ext4 filesystems it needs are built by `mkimage-inputs.sh` (in the build container, as root -
`mke2fs -d` takes owner and mode from the tree). Both helpers kept their old names,
`mkimage-selbsttest.py` and `mkimage-eingaben.sh`, as forwarders for one release.

## Limits

The layout, sizes and reference hashes are fixed once measured on the HY310 (10.09.2026) and are not
recomputed per build; a device with different placeholder sizes needs its own table. `check` validates
sizes, checksums, GPT and placeholder locations, but not that the proprietary content someone fills in is
actually correct for their device - that check belongs to `h713-extract`.

Details: doku/109-plan-layout-v3.md, doku/nachtlog/S47-abbild-bauer.md.
