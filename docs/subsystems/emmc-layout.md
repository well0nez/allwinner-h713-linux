# eMMC layout

Layout v3 puts the entire boot chain - SPL, U-Boot, environment, and the one block that must never be
touched - into the eMMC's first 8 MiB, and gives every one of those raw regions its own GPT entry so that
`lsblk`, `gparted` or a stray `dd` see them as occupied instead of guessing. Two ext4 partitions,
`hy310-boot` and `hy310-rootfs`, hold everything else.

## The six partitions

| # | `PARTLABEL` | Start LBA | Size | Contents |
|---|---|---|---|---|
| 1 | `hy310-spl` | 16 | 32 KiB | Raw SPL. Fixed by the BootROM, which looks for `eGON.BT0` at exactly this offset |
| 2 | `hy310-uboot` | 2,048 | 5 MiB | Raw U-Boot proper - 5.9× today's 890 KiB, room to grow without another layout change |
| 3 | `hy310-keys` | 12,288 | 1 MiB | Secure storage: HDCP 1.4/2.2 keys, Wi-Fi/BT MAC addresses, serial number - **never written, ever** |
| 4 | `hy310-env` | 14,336 | 1 MiB | U-Boot environment (64 KiB) plus a fastboot SPL-parking slot |
| 5 | `hy310-boot` | 16,384 | 128 MiB | ext4: kernel FIT, `mips/` (MIPS display firmware and tables) and `bootlogo.bmp` |
| 6 | `hy310-rootfs` | 278,528 | 7.15 GiB | ext4: Debian root filesystem, including a `/data` directory |

`hy310-boot` holds three things, and U-Boot reads all three off it before Linux starts: the kernel FIT,
`mips/` with the 19 display artifacts the MIPS co-processor is handed, and `bootlogo.bmp` at the
partition root. The logo has to sit at the root, not in `mips/`, because that is where
`h713_disp init <id> logo` looks - on a stock device it lies at the root of the bootloader FAT, next to
`mips/`, and our layout keeps that relationship.

Only LBA 16 is prescribed, by the BootROM; everything else is free. U-Boot moved here from a leftover
Android partition 2.3 GiB into the disk, and the old, mostly-empty `hy310-data` partition is gone - a
growing `/data` directory inside the 7.15 GiB rootfs does the same job without a second partition for it.

## The hole nothing may touch

`hy310-keys` is the sunxi Secure Storage, found occupying LBA 12,288…12,399 (56 KiB in fourteen 4 KiB
blocks) when this region was first measured. It holds the HDCP 1.4 and 2.2 keys and their hashes, plus two
things with no HDCP connection at all: the device's Wi-Fi/Bluetooth MAC addresses and its serial number.
None of it exists in any firmware image, and none of it can be regenerated - it is unique to this chip. The
partition is sized at 1 MiB on purpose, room for roughly eighteen times the seven item types it currently
holds, because an unfamiliar device's Secure Storage may define more of them and the installer refuses to
guess rather than assume this device's layout is universal. The lock is enforced twice: once as an ordinary
GPT partition nobody is told to format, and once as a hard-coded sector range in the installer that not
even `--force` lifts.

Because LBA 12,288…14,335 must never appear in a flashable file, the release image itself is not one
contiguous file but three, built around the gap - the split, its table, and the placeholders it leaves for
proprietary files are covered in [`h713-mkimage.md`](../tools/h713-mkimage.md), not here.

## Restoring to stock

Installing overwrites the SPL, U-Boot, the Android partition table and everything that used to be Android -
all of it recoverable from the manufacturer's firmware image alone. The installer therefore insists on a
full 7.3 GB device dump, or the matching vendor firmware, **before** the first write (`doku/110`). Checked
against that firmware image and the stock partition table, every overwritten region has a source there with
one exception: the Android `private` partition, which appears in no firmware image - but it is also not
where the real key material lives, and that stays untouched in `hy310-keys` no matter which system is
installed. Reflashing the vendor firmware therefore restores a working stock device, HDCP included, without
depending on anything this project could not put back itself.

Details: `doku/109-plan-layout-v3.md`, `doku/108-plan-vendordaten.md`, `doku/110-plan-installationsweg.md`.
