# h713-mkimage

`h713-mkimage` assembles the flashable image from the built pieces - SPL, U-Boot proper, the kernel FIT,
and the two ext4 filesystems - laid out to Layout v4, together with the table, checksums and a
readme. Users normally never run it themselves; it produces the image that
[`h713-install`](h713-install.md) writes.

```
installer/h713-mkimage build -o out/hy310-v0.1.img            # image (three pieces) + table + checksums + README
installer/h713-mkimage check out/hy310-v0.1.tabelle.json      # validate a finished image; writes nothing
installer/h713-mkimage tree-boot DIR [--fit FILE]             # only the file tree for hy310-boot
installer/h713-mkimage tree-rootfs DIR                        # only the rootfs target directories (an overlay)
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

## How the vendor files get in

44 files that must not ship in this repository - 19 display artifacts, the boot logo, 3 firmware blobs,
8 picture-quality tables, 13 Wi-Fi firmware files - are simply not in the image. What the image carries
is their target *directories*, empty: `/mips` on `hy310-boot`, `/lib/firmware/h713`, the aic8800 path
and `/etc/h713/tvconfig` on `hy310-rootfs`. The table lists each file under `dateien` with its name in
an `h713-extract` output, the partition it belongs to, the absolute path inside that partition, its
group, and whether a device may be without it.

`h713-install` mounts the two filesystems of its working copy (it runs as root anyway), copies the files
in as ordinary files with their real length, and unmounts before it writes. Nothing is padded, nothing
has a fixed size, and no table has to be maintained per firmware. The SSH `authorized_keys` is one more
file of the same kind, listed under `nutzer` with its mode (0600), its owner and the mode of `/root/.ssh`
(0700) - without `--ssh-key` it is never created.

This is Layout v4, and it replaced fixed-size placeholders on 16.09.2026. Layout v3 wrote each file into
a placeholder of exactly the size measured on one HY310; the first foreign firmware with bigger files
stopped the install (issue #1, HY300 Pro: `ProjectID_0x0034.TSE` 19,992 > 17,328). Files smaller than
their placeholder were zero-padded before that.

The boot logo (`bootlogo.bmp`, at the ROOT of `hy310-boot` rather than in `mips/`) is the one single file
marked optional: a dump without a logo costs a warning, and U-Boot then boots without a logo instead of
not booting. Its size no longer matters at all - a 720p board's 2,764,854 bytes are as good as a 1080p
board's 6,220,854, because U-Boot takes every size from the BMP header. Two whole groups are optional as
well: the Wi-Fi firmware (no chip, no files) and the PQ tables (a firmware may ship only part of the set).

## v3 and v4 do not mix

The table says which it is: `"format": "hy310-abbild-tabelle-v4"` instead of v3's
`"hy310-abbild-tabelle"`. For anyone holding a v0.7-beta image that means two things. The new
`h713-install` refuses that old table with a message instead of writing half an image, and the new
`h713-mkimage check` refuses it too, naming the tool that can read it. The other way round, a v4 table
read by the v0.7-beta installer is not recognised as an image table at all, so it stops as well. Take
the release as one piece - image, table and the tools next to it - and neither case comes up.

## Self-test

`mkimage-selftest.py` runs the whole path without hardware: it checks the locked region against the
table, compares the table's file list against `h713.layout` entry by entry, opens both filesystems
**through the ext4 reader** at the offsets the installer derives from the table and confirms that the
target directories are there with their modes and that not one vendor file is - then `dd`s the three
pieces onto a sparse disk image and checks that the locked region is still untouched and the GPT shows
the expected six partitions. It prints `ALL GREEN` when nothing is red. With root
(`H713_ROOT_TESTS=1` and a password-less `sudo -n true`) it additionally plays the real copy through
`h713.mountfs` onto a scratch copy of piece B and reads every file back byte for byte; without root it
says so and runs everything else.
The two ext4 filesystems it needs are built by `mkimage-inputs.sh` (in the build container, as root -
`mke2fs -d` takes owner and mode from the tree). Both helpers kept their old names,
`mkimage-selbsttest.py` and `mkimage-eingaben.sh`, as forwarders for one release.

## Limits

The partition layout and the reference hashes are fixed once measured on the HY310 (10.09.2026) and are
not recomputed per build; the *file sizes* are not fixed any more, which is the whole point of v4.
`check` validates sizes, checksums, GPT, the file list and the target directories in the finished ext4,
but not that the proprietary content someone copies in is actually correct for their device - that check
belongs to `h713-extract`.

Details: doku/109-plan-layout-v3.md, doku/nachtlog/S47-abbild-bauer.md.
