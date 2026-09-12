# hy310-mkimage

`hy310-mkimage` assembles the flashable image from the built pieces — SPL, U-Boot proper, the kernel FIT,
and the two ext4 filesystems — laid out to Layout v3, together with an offset table, a manifest, and
checksums. Users normally never run it themselves; it produces the image that `hy310-install` writes.

```
installer/hy310-mkimage.py --out out/hy310-v0.1.img              # image (three pieces) + table + manifest + LIESMICH
installer/hy310-mkimage.py --pruefen out/hy310-v0.1.tabelle.json  # validate a finished image against its table
```

## Three files, not one

The image is `<name>-a-bootkette.img`, `<name>-b-system.img`, `<name>-c-gptkopie.img`, and a
`<name>.tabelle.json` describing where each piece goes — not one continuous `.img`. The reason is a
1 MiB region at LBA 12288–14335 that this SoC's Secure Storage occupies: HDCP keys, the Wi-Fi/Bluetooth
MAC addresses, and the device's serial number. Nothing generates these values and no firmware image
carries them, so overwriting that region is not recoverable.

`hy310-install` guards it in software, but the plan for this project always allowed writing the image
with a plain `dd`, the way one flashes a single-board computer — and a user doing that has no such guard.
Measured directly: a continuous image written by hand replaces those bytes with zeroes; splitting the
image into three pieces with a gap where the fourth would go means the bytes simply are not in the file,
so there is nothing for a plain `dd` sequence to overwrite even by mistake. The failure mode changes from
silent data loss on the ordinary path to a deliberate `seek` error on the safety net doing something
unusual — worth one extra command in the instructions and an `--abbild` that names a table instead of a
single file.

## Placeholders

43 files that must not ship in this repository — 19 display artifacts, 3 firmware blobs, 8 picture-quality
tables, 13 Wi-Fi firmware files — sit in the image as placeholders of the exact right size. The offset
table records where each one lives; `hy310-install` overwrites them with what `h713-extract` pulled from
the user's own device. The SSH `authorized_keys` placeholder works the same way but is found through the
finished ext4 filesystem rather than a fixed raw offset, since its location depends on the filesystem
layout, not on the partition table.

## Self-test

`mkimage-selbsttest.py` runs the whole path without hardware: it checks the locked region against the
offset table, fills the placeholders with real extracted files, confirms the ext4 reader finds them back
**through the filesystem** — proving the offsets hit the right blocks, not just that a raw write
succeeded — then `dd`s the three pieces onto a sparse disk image and checks that the locked region is
still empty and the GPT shows the expected six partitions.

## Limits

The layout, sizes and reference hashes are fixed once measured on the HY310 (10.09.2026) and are not
recomputed per build; a device with different placeholder sizes needs its own table. `--pruefen` validates
sizes, checksums, GPT and placeholder locations, but not that the proprietary content someone fills in is
actually correct for their device — that check belongs to `h713-extract`.

Details: doku/109-plan-layout-v3.md, doku/nachtlog/S47-abbild-bauer.md.
