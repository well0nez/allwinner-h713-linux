# Installing on a device

From a Linux PC, over one USB cable. The projector never has to be opened, and nothing is written to it
until you have a dump of what was there before.

> **Before anything else.** Installing replaces Android. The display firmware, the ARISC firmware, the
> Wi-Fi firmware and the picture tables are proprietary - the same files on every device of this model, but
> ours to neither ship nor pass on, so the installer reads them out of your own dump. Your device's secure
> storage is the part that really exists only once: HDCP keys, MAC addresses, serial number. If you skip
> the dump and the install fails, nobody can give you any of it back. Take the **full** dump (7.3 GB) the first time and keep it somewhere safe. The small
> dump (49 MiB) is enough for every *later* run on the **same** device, because it carries the parts that
> differ per unit - secure storage, `private`, `Reserve0`, and the display firmware out of every place the
> board keeps it. It is not enough to put Android back, and it is not enough for a device you have never
> dumped in full.

## What you need

- The projector, its power supply, and a **USB A-to-A cable** to the PC.
- Linux with Python 3.9+, and `sudo`. No extra packages. `install` mounts the image's own file systems
  to copy your device's files into them, and that needs a Linux kernel and root; it says so in one
  sentence instead of failing somewhere deeper. `identify`, `dump` and `extract` do not mount anything
  and run on Windows too - but **nobody has run the Windows path**, so treat it as untested.
- An image: from a release tag if there is one for your version, otherwise built yourself with
  `release/build-all.sh` ([BUILDING.md](BUILDING.md); the first time also
  [docs/build-container.md](docs/build-container.md)). Building takes about 20 minutes and needs no device.
- Your public SSH key. Without it the installed system has **no** SSH access, only the serial console:
  the image deliberately ships no key.

## Getting the files together

From a release you need two things: **this repository** (the installer lives in `installer/`) and **the
release files**. Put all release files into one folder; the installer finds the image parts next to the
table.

```bash
git clone https://github.com/well0nez/allwinner-h713-linux.git
mkdir ~/hy310-v0.9-beta && cd ~/hy310-v0.9-beta
#   download every file of the v0.9-beta release into this folder, then:
zstd -d *.img.zst                            # optional, see below - the installer does it too
sha256sum -c h713-hy310-v0.9-beta.sha256     # lists the unpacked .img parts, so unpack first
chmod +x sunxi-fel
```

The folder then holds the three `.img` parts, `h713-hy310-v0.9-beta.tabelle.json`, `u-boot-installer.bin`
(the U-Boot that exposes the eMMC over USB) and `sunxi-fel` (the FEL tool, built with the H713 trap door -
the stock `sunxi-fel` from your distribution does **not** work here). `sunxi-fel` needs `libusb-1.0` on your
PC; on Debian and Ubuntu that is `apt install libusb-1.0-0`.

If you built the image yourself with `release/build-all.sh`, the same files are in `installer/out/` and
`mainline/build/out/`.

## The four steps

```bash
# 1. put the device into FEL: hold the reset button, then plug in power
# 2. run the installer (it loads U-Boot over USB - nothing is written yet)
sudo allwinner-h713-linux/installer/h713-install install ~/hy310-v0.9-beta \
    --ssh-key ~/.ssh/id_ed25519.pub \
    --full --dump ~/hy310-dump
# 3. it dumps, extracts your device's own files, copies them into the image, writes it, verifies
# 4. power off, power on - and press the power key
```

You name the release folder, not six files: the installer finds the offset table, `u-boot-installer.bin`
and `sunxi-fel` inside it, and unpacks `*.img.zst` itself if `zstd` is installed. `--uboot` and
`--sunxi-fel` override that when your copies live elsewhere.

So the `zstd -d` line above is optional: run it if you want to check the `.sha256` file yourself
(it lists the unpacked `.img` parts), or if `zstd` is not on the PC that runs the installer - then
the installer stops and names the packed parts instead of unpacking them, and you unpack them by
hand or on another machine. The installer checks the sha256 of every part before it writes either
way, so `sha256sum -c` is a second pair of eyes, not a requirement.

`sudo` because it writes a block device and mounts the image's file systems. The dump and the filled copy
of the image land in `~/hy310-dump` - about 8.5 GB with the full dump.

U-Boot exposes the eMMC as a normal USB drive; that is how the PC reads and writes it. The only way out
of that mode is a power cycle, which is also the end of the procedure.

The installer types nothing for you: before it writes, it asks you to type `YES`. It also refuses to run
if it does not recognise the device, so a stranger's firmware cannot be guessed at (`--skip-identify`
exists for development and is exactly as dangerous as it sounds).

## What a successful run looks like

The run is a numbered list of steps, with `OK`, `!` and `ERROR:` in front of the lines that matter. Step
`1b` is the check that refuses a device it does not recognise. Step `3` takes the dump, step `5` copies
your device's own files into the image's two file systems on the PC and reads every one of them back,
step `6` is the only one that writes, and step `7` compares the secure storage byte by byte against the
dump from step `3`, so you know it was not touched. Writing takes about three minutes with the full
image; everything else is seconds.

Recorded on 2026-09-15 on an HY310 running the stock firmware, with `h713-install install ~/h713-hy310-v0.6-beta
--ssh-key ~/.ssh/id_ed25519.pub --dump ~/h713-dump-T --small --yes` after a full dump had been taken into the same
directory (17 minutes, not shown). Progress lines are cut. The two regions reported as empty are a trait of this
test device, which had been converted before; an untouched device saves content there.

The numbers in the recording are the ones of v0.6-beta and are left as they were run. Since 15.09.2026 the
boot logo travels with the image: the file set has 44 entries instead of 43, the extraction hands over 44
files, and the dump saves 20 files per bootloader slot (`bootlogo.bmp` lies at the FAT root next to
`mips/`). The `display firmware in bootloader_a 19 files` line of step `1b` still says 19 - that one counts
`mips/` only.

Step `5` also reads differently since layout v4 (16.09.2026). It used to fill placeholders: files of a
measured size, sitting at a known byte offset in the image, which a firmware with bigger files could not
fit into. Now the installer mounts the image's two file systems in its working copy and copies the files
in as ordinary files, so sizes never come into it. The lines of that step are now

```
[5] Put the device's own files in (44 files)
  OK 44 files from h713-dump-T/extract
  OK authorized_keys: 1 key(s) from ~/.ssh/id_ed25519.pub, 104 bytes -> /root/.ssh/authorized_keys (mode 0600, root)
  Working copy: h713-dump-T/image-filled.img (1153 MiB)
  hy310-boot: 20 file(s)
  hy310-rootfs: 25 file(s)
  OK 45 files copied in and read back -- all equal
```

```
h713-install 0.1 (draft, doku/110)   (Linux)
[1] the eMMC is already exposed as a drive
  OK /dev/sda, 15269888 sectors, stock layout, 26 partitions -- FEL and exposure skipped
[1b] Identify the device
  OK HY310 recognised -- device (stock), verified profile
  matched on arisc_version, build_fingerprint, dtb_sha256, mips_database_sha256, scp_sha256, uboot_sha256, uboot_version
  fingerprint Allwinner/h713_tuna_p3/h713-tuna_p3:11/RP1A.201005.006/Projector07241019:user/release-keys
  layout    stock, 26 partitions, 15269888 sectors
  device-only Reserve0_a@5489664+32768, Reserve0_b@5522432+32768, private@4891648+32768, secure-storage@12288+2048
  display firmware in bootloader_a 19 files, bootloader_b 19 files, vendor 19 files
[3] Take the dump (small)
  OK secure-storage   LBA 12288      1.0 MiB  saved (hash in the manifest)
  OK private          LBA 4891648   16.0 MiB  080acf35a507ac98…  (empty)
  OK reserve0-a       LBA 5489664   16.0 MiB  saved (hash in the manifest)
  OK reserve0-b       LBA 5522432   16.0 MiB  080acf35a507ac98…  (empty)
  ! Empty and therefore without content: private, reserve0-b.
    On an untouched device something would stand there. Either this
    device has been converted once already, or this firmware does not
    use the regions. The Secure Storage is independent of that.
  OK bootloader_a     19 files    1.9 MiB  -> mips/bootloader_a/
  OK bootloader_b     19 files    1.9 MiB  -> mips/bootloader_b/
  OK mips/: the two bootloader slots hold the same 19 files
  mips/: active slot unknown (no readable bootloader_control)
  OK vendor           19 files    1.9 MiB  -> mips/vendor/
  OK reserve0          1 files    0.0 MiB  -> mips/reserve0/
  mips/: media_data not readable (media_data: no ext4 superblock (no magic at 0x438) -- erofs/f2fs? Not supported.)
  OK the dump lies in ~/h713-dump-T
[4] Check the image (h713-hy310-v0.9-beta, v4 (doku/109 section 2.2, files copied through a mount))
  OK h713-hy310-v0.9-beta-a-bootkette.img LBA 0             6291456 bytes  sha256 ok
  OK h713-hy310-v0.9-beta-b-system.img  LBA 14336      1209008128 bytes  sha256 ok
  OK h713-hy310-v0.9-beta-c-gptkopie.img LBA 15269855        16896 bytes  sha256 ok
  Hole at LBA 12288..14335 (hy310-keys) -- stays untouched
[5] Put the device's own files in (44 files)
  h713-extract emmc-full.img -> h713-dump-T/extract
  OK extraction complete and checked against the reference
  OK 44 files from h713-dump-T/extract
  OK authorized_keys: 1 key(s) from ~/.ssh/id_ed25519.pub, 104 bytes
  Working copy: h713-dump-T/image-filled.img (1153 MiB)
    mount -t ext4 -o loop,offset=1048576,sizelimit=134217728 h713-dump-T/image-filled.img /tmp/h713-mount-...
  OK 45 files copied in and read back -- all equal
  OK Environment: h713_project=0x30 already set as declared
[6] Write onto the eMMC
    h713-hy310-v0.9-beta-a-bootkette.img from LBA 0             6291456 bytes
    h713-hy310-v0.9-beta-b-system.img  from LBA 14336      1209008128 bytes
    h713-hy310-v0.9-beta-c-gptkopie.img from LBA 15269855        16896 bytes
  ! This overwrites the eMMC.
    This here is a beta. If something goes wrong while it writes:
    do NOT pull the power and reboot. Put the device into FEL mode
    (hold reset, plug the power in) and start from the beginning --
    the boot chain is always reachable from there.
    Type YES to continue: YES   (--yes on the command line)
  OK h713-hy310-v0.9-beta-a-bootkette.img written
  OK h713-hy310-v0.9-beta-b-system.img written
  OK h713-hy310-v0.9-beta-c-gptkopie.img written
  OK everything written in 3 min
[7] Compare back
  OK samples match
  OK Secure Storage unchanged (compared byte for byte against the dump)
  Done. Unplug the power and plug it in again.
```

## After the first boot

Plug in power, then press the power key - the same as with the stock firmware. Until you press it the
device waits at about 4 W with a red LED. Reproducing that behaviour took work
([docs/uboot/power-gate.md](docs/uboot/power-gate.md)); if you would rather have the device boot the
moment it gets power, `fw_setenv h713_gate 0` gives you that.

Then, over the network:

```bash
ssh root@h713           # key-only; the Wi-Fi access point is up by default
h713-tv ctl status      # HDMI input service
```

The default access point is **published in this repo** - its SSID and password are the same on every
device that installs the image unchanged. Change them in `/etc/h713/wifi.env` before the device stands
anywhere but on your own desk ([docs/tools/h713-wifi.md](docs/tools/h713-wifi.md)).

## Reinstalling over our own layout

The second install on the same device asks for nothing: no dump, no `--vendor`. The GPT names say that
this system is already on it (`hy310-*`), and then the 44 proprietary files are not gone - they lie in
its own `hy310-boot` and `hy310-rootfs`, under the paths the image's table names. The installer mounts
those two partitions read-only, copies the files out (about 12 MiB, a couple of seconds), puts them into
the new image and says so: `44 files read back from the device`. Which partitions those are it reads out
of the device's own GPT, not out of a constant. The mandatory small dump falls away too, because nothing
stock-specific is left to save - `--dump DIR` still takes one, and `--vendor` or a full dump in the dump
directory still beat the device. What the dump used to supply for the last two steps is read into memory
instead: the secure storage is still compared byte for byte after writing, and `h713_gate` / `h713_boot`
are still carried over from the old U-Boot environment. A file the device does not have is treated the
way a missing one from a dump is: the boot logo, the Wi-Fi firmware and the picture tables are optional
and are skipped with one line, anything else stops the run with exit 8, naming the file and asking for
`--vendor`. `--no-write` is a rehearsal and mounts nothing at all, so it says which files it *would* read
back and where they would go, instead of reading them. This is for **our** layout only. On a stock device
nothing has changed: the dump is mandatory, it is the only way back to Android, and without it or
`--vendor` the run stops before it writes.

## Useful variants

| Task | Command |
|---|---|
| Ask what a device, a dump or a firmware image is | `h713-install identify [FILE]` - writes nothing |
| Only make a dump, write nothing | `h713-install dump --full -o ~/hy310-dump` |
| Reinstall, keeping your U-Boot settings | (default: `h713_gate` and `h713_boot` are carried over) |
| Reinstall, discarding them | `--fresh-env` |
| Reuse an extraction you already have | `--vendor <dir from h713-extract>` |
| Reinstall over this system, no dump needed | (default: the vendor files come off the device itself) |
| Go back to your own dump | `h713-install restore ~/h713-dump/emmc-full.img` |
| Go back to stock Android | `h713-install restore-stock UPDATE.IMG` |
| Rehearse without writing | `--no-write` on any subcommand |

`restore-stock` rebuilds the vendor partition table byte-for-byte, so the device comes back as a normal
Android projector. The path has been used on hardware; the English command line for it has not, and
neither has the Windows side ([STATUS.md](STATUS.md)). The German switches of v0.5-beta - `--abbild`,
`--abzug`, `--nur-abzug`, `--dry-run` and the rest - still work until after `v0.9` and each print one line
with their new name, so an older recipe does not break.

## If something goes wrong

- **The device is not found in FEL.** Hold reset *before* applying power and keep holding it. Check with
  `sunxi-fel version`. Note that with the A-to-A cable plugged in, the device is powered from USB, so a
  switched socket will not restart it - unplug the cable first.
- **You already wrote a broken image.** FEL is in the BROM and cannot be bricked from software. Put the
  device back into FEL and run the installer again, or `h713-install restore` your dump.
- **The device stays dark after installing.** Press the power key (see above) before assuming the worst.
- **No SSH.** You did not pass `--ssh-key`, or the key file was the private one. The serial console
  on the UART pads still works - and it logs in as root without a password, which is the point
  ([docs/services.md](docs/services.md)).
- **SSH warns that the host key changed.** Expected after every install: the new system generates its own
  host keys on first boot, so two devices from one image are not twins. Remove the old entry
  (`ssh-keygen -R <address>`) and reconnect.

## What is written where

The image is three files with a **gap** in the middle. The gap sits exactly over the secure storage area
(LBA 12288-14335), which holds per-device material including the HDCP keys. Nothing in this project ever
writes there - not even a hand-typed `dd`, because there is no file to write. Layout:
[docs/subsystems/emmc-layout.md](docs/subsystems/emmc-layout.md).

Details: `doku/110-plan-installationsweg.md`, `doku/109-plan-layout-v3.md`.
