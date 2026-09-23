# h713-install

`h713-install` turns a stock HY310/L018 into this system, entirely from the user's PC - nothing
proprietary is downloaded, and nothing runs on the device beyond U-Boot. It talks to the eMMC as a plain
USB block device, so it needs Python 3.9+ and no other package. `install` also mounts the image's own file
systems to copy those parts in, which needs a Linux kernel and root; `identify`, `dump` and `extract` mount
nothing and run on Windows as well. It replaces `hy310-install.py`, which stays one release as a
forwarder.

## The path

1. **FEL.** Hold reset, plug in power. No case to open, no pads, no soldering.
2. **`h713-install` loads U-Boot over USB** (`sunxi-fel uboot`, a few seconds, no byte written to the
   eMMC yet) and has it export the eMMC as a USB mass-storage drive. From here on the only way back to
   FEL is cutting power - which is the end of the procedure anyway.
3. **The device is identified and dumped**, before anything is written. A board without a **verified**
   profile is refused rather than guessed at - that includes a board we hold a profile for but nobody has
   reported a green run on. There is no flag to skip the dump: the choice is which size, not whether. Only
   a device that already runs this system is spared - nothing stock-specific is left on it.
4. **The proprietary parts are extracted from that dump** with [`h713-extract`](h713-extract.md) and
   copied into the image on the PC, together with the user's SSH public key if one was given. How they get
   in: the installer makes a working copy of the part that carries the two file systems, mounts
   `hy310-boot` and `hy310-rootfs` inside it (`mount -o loop,offset=,sizelimit=`, the offset and the size
   out of the table alone), writes each file as an ordinary file with its real length and the mode it must
   have, and unmounts. Sizes therefore never have to match anything - the layout before this one wrote
   into placeholders of a measured size, and a firmware whose files are bigger had nowhere to go. Every
   file is read back out of the working copy and compared byte for byte before anything goes onto the
   eMMC, in one pass.
5. **Verified**: a full dump is sampled against the device before extraction starts; after writing, every
   part is spot-checked and the secure storage compared byte for byte against the dump. A mismatch is
   reported as a clear failure - "do not reboot, ask" - never as a quiet success.
6. **Power off and back on**, then press the power key: the device no longer boots by itself on power-up,
   by design ([docs/uboot/power-gate.md](../uboot/power-gate.md)).

## The subcommands

```
h713-install identify [DEVICE|DUMP|IMAGE] [--json]
h713-install dump [--full|--small] [-o DIR] [--with-vendor]
h713-install install RELEASE-DIR|TABLE.json [--ssh-key FILE] [--dump DIR] [--vendor DIR] [--fresh-env]
                                            [--test-image]
h713-install restore DUMP.img
h713-install restore-stock UPDATE.img
h713-install extract INPUT -o DIR
common: --device PATH  --sunxi-fel PATH  --uboot PATH  --no-write  --skip-identify  --yes
```

| Subcommand | What it does | eMMC |
|---|---|---|
| `identify` | prints the profile row of a device, a dump or a vendor firmware image; given a release table (`*.tabelle.json`), lists the pieces and whether they lie next to it | writes nothing |
| `dump` | saves what exists only on this device; `--with-vendor` also runs the extractor | writes nothing |
| `install` | dump, extract, copy in, write, compare back; `--test-image` accepts an image built for one untested board, on that board only | writes. Linux and root |
| `restore` | writes a previous full dump back | writes |
| `restore-stock` | rebuilds the stock partition table and writes the vendor firmware back | writes |
| `extract` | hands everything behind it to [`h713-extract`](h713-extract.md) | writes nothing |

`install` takes a whole release folder: it finds the `*.tabelle.json`, `u-boot-installer.bin` and
`sunxi-fel` lying next to each other, and unpacks `*.img.zst` parts itself when `zstd` is on the PC
(`--uboot` and `--sunxi-fel` override). `--no-write` is the one word for "rehearse": everything is read,
nothing is written. `--yes` answers the confirmation in advance, for scripted runs without a terminal.
Both belong to the common set, which every subcommand but `extract` takes - `extract` hands its whole
tail on. Exit codes are listed in `h713-install --help`.

## Test images

A board nobody has run gets no release image - that rule has not moved. What it does get, once it
is described well enough to build for, is a **test image**: built on purpose with
`release/build-all.sh --test-image`, named `…-TEST`, and marked in its table with
`test_for: "<profile>"`. It is meant for one person, the owner of that board.

`install` writes such an image only when both hold:

- `--test-image` is on the command line, and
- the device in front of it identifies as exactly that profile.

Either one missing and the run stops before the eMMC is touched, naming which board the image was
built for, which board was found, and that a full dump (`dump --full`) is the way back. `--no-write`
shows the same decision and writes nothing; `--skip-identify` does not open the door, because the
whole point is that the board must be identified. A normal image is unaffected: its table carries no
`test_for`, and everything about it behaves as before.

**The second test image on the same board.** Once a test image is on the device, the device carries our
layout, and our layout has nothing a profile could match on - no Android, no vendor U-Boot. So the board is
taken from the full dump of the first install instead: point `--dump` at that directory (the one with
`emmc-full.img`) and the installer identifies the clone the way `identify <clone>` does, says "the board is
known from the dump of the first install", and accepts the image. The files in that directory are left as
they are - a small dump of our own layout would otherwise overwrite the stock environment - and the
vendor files come out of the clone as before. Without the clone the board stays unknown and the run stops
(23.09.2026: the HY300 Pro's owner, test7 on the device, test8 refused).

Passing `--test-image` to an image that is not marked does nothing, and says so in one line. A green
report from the owner is what turns the board `verified` and its next build into a real release.

## The two dump sizes

Both land in one directory - `h713-dump` unless `-o`/`--dump` says otherwise - with `MANIFEST.json`
and a `README.txt` naming every file and the command that puts it back. A dump made by v0.5-beta keeps
working: where `emmc-full.img` or `extract/` is missing, the tool reads the old `emmc-voll.img` / `extrakt/`
and says so. Only the full dump is a way back to Android.

| Size | What it holds | Cost |
|---|---|---|
| `--small` | secure storage, `private` and `Reserve0*` as the device's own partition table spells them; the display firmware from both bootloader slots, from the vendor partition, from `Reserve0` and from `media_data`; the U-Boot environment on our own layout. Enough for a later run on the **same** device | 49 MiB, about 10 seconds |
| `--full` | `emmc-full.img`, the whole eMMC, with the small dump alongside it | 7.3 GB, about 17 minutes |

A complete `emmc-full.img` in the dump directory is never overwritten by accident. `install --full`
reuses it instead of dumping 7.3 GB a second time, and `dump --full` keeps it and says so in one line;
`dump --full --force` takes a new one. Complete means: `MANIFEST.json` names `emmc-full`, its sector
count is the count of the device in front of the tool, and the file is exactly that many bytes. A clone
that an aborted run left short is named with both sizes and taken again.

Where each region of the small dump was found stands in its `MANIFEST.json` row as `source`: `gpt` for
the device's own partition table, `fixed` for the secure storage (raw at LBA 12288 - no partition entry
points at it on any H713 seen so far), and `hy310-constant` for the last resort. A table that names no
`private` and no `Reserve0*` at all falls back to the HY310's own LBAs for that group, and the run says
on screen which region it guessed rather than read.

## Reinstalling over our own layout

A device whose GPT names begin `hy310-` already runs this system, and then `install` demands neither a
dump nor `--vendor`. The 44 proprietary files are on it, in its own `hy310-boot` and `hy310-rootfs`, under
exactly the paths the image's table names. The installer mounts those two partitions read-only and copies
the files out (about 12 MiB), then puts them into the new image the same way it would put an extraction
in, and logs `44 files read back from the device`. Where the two partitions are comes out of the device's
own GPT: the entry slot is what Linux calls `/dev/sdX5` and `/dev/sdX6`, and both the node and the window
are named in the log. The window is what is mounted, not the node - the installer holds the whole drive
open exclusively while it works, and the kernel will not mount a partition of a drive somebody holds like
that.

`--vendor` and a full dump in the dump directory keep precedence, in that order. The mandatory small dump
is skipped as well (`our layout on the device -- nothing stock to save; --dump takes one anyway`); what
the later steps took out of it is read into memory before the write instead, so step 7 still compares the
secure storage byte for byte and the intent keys `h713_gate` / `h713_boot` are still carried over from the
old environment. A file that is not on the device counts exactly as one a dump could not supply: an
optional one (the boot logo, the Wi-Fi firmware, the picture tables) is skipped with one line per group,
anything else stops the run with the usual exit 8 plus the line `the device has no <name> -- give
--vendor`. `--no-write` mounts nothing at all - it prints which files it would read back from which
partition and where they would go, and that plan is the same code that does the work. On a stock device
none of this applies: the dump is mandatory and it is what the vendor files come out of.

## Safety nets

Before the first byte is written the tool prints the beta warning and requires **`YES` typed out** - not a
`[y/N]` prompt - because a fast keypress is exactly the failure mode a full write should not allow. `JA`
is accepted alongside `YES` until the German aliases go out after `v0.9`.

GPT partition names starting `hy310-` mean the device already runs this system; a stock layout is matched
against the board profiles by several features at once, not by one fingerprint string. On a reinstall over
our own layout the intent keys `h713_gate` and `h713_boot` are carried over from the old U-Boot
environment and the declared project id is written as `h713_project`; everything else comes from the image,
so a stale setting cannot silently survive an upgrade. `--fresh-env` carries nothing over.

The secure storage region is never written, whatever you pass - the image itself has a gap there, so even
a raw `dd` from someone bypassing this tool cannot reach it (see [`h713-mkimage`](h713-mkimage.md)).

`restore-stock` rebuilds the original GPT from the image's own `sys_partition.fex`. Partitions the image
brings no file for are left alone rather than zeroed where the board profile lists them under
`preserve_on_restore` - `private`, `Reserve0*`, `media_data` and both bootloader slots on the HY310. An
image without a `mips/` directory does not get to write over a bootloader partition that has one: the
stock U-Boot reads the display firmware from the slot `misc` selects.

## What is proven and what is not

The steps above have run on hardware with the English command line since 15.09.2026, and layout v4 - the
copy through a mount - was installed and cold-started on the HY310 on 16.09.2026
([STATUS.md](../../STATUS.md)). What stays unverified is the Windows path: `identify`, `dump` and
`extract` are written for it and refuse nothing, `install` says in one sentence that it needs Linux, and
nobody has run any of it there. Every German switch of v0.5-beta
(`--abbild`, `--abzug`, `--nur-abzug`, `--dry-run` and the rest) is still accepted until after `v0.9` and
prints one line with its new name.

Details: doku/110-plan-installationsweg.md, doku/121-plan-werkzeug-umbau.md.
