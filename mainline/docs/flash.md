# Flashing

How to write images to the H713 eMMC. Neither board has an SD slot — boot media
is **eMMC or FEL only**. There is a hardware **FEL button** (recovery vector),
so a bad first stage is recoverable.

## ⚠ State of the bench board as of 2026-08-09

Read this before assuming anything about what is on the eMMC. The board is
**not** in the state older docs describe.

| | |
| --- | --- |
| first stage at LBA `0x10` | ours — the board boots our U-Boot (`2026.07-rc5`, banner confirmed 2026-08-09). `boot-switch.sh status` tells you for certain |
| our U-Boot proper / env / SPL stash | `empty` partition, LBA `0x49ac00` / `0x49ec00` / `0x49cc00` |
| our kernel FIT | a **file** in the FAT on `mmc 1:2`, `h713-kernel.fit`; `bootcmd` is `fatload mmc 1:2 0x50000000 h713-kernel.fit; bootm`. **Carries the 8 MiB `uboot-scanout` reservation** as of 2026-08-09; the previous 4 MiB build is kept at `local/h713-kernel-prev-20260809.fit` |
| `boot_a` | **the vendor's stock Android boot image**, restored from the capture — no longer ours. Not on our boot path; `bootcmd` reads the FAT |
| `UDISK` (p26) | **ext4, our Debian** — 4.6 GiB partition. The 2026-08-06 "f2fs Android userdata" claim was **stale**: it was verified ext4 and healthy on 2026-08-09, and has since been rewritten with the video-decode bring-up rootfs |
| `bootloader_a` | the vendor's FAT16 (its `mips/` display artifacts), restored |
| `Reserve0_a` | vendor's, **with one byte modified by us**: `panel_config.ini` `pwm_channel` is `2`, stock is `5`. LBA `0x53c51f` offset `0x89`, write `0x35` to revert |
| `super` | repaired — see the warning in Safety |

**Backups.** `local/h713-lab/captures/board-b/` holds four factory captures from
2026-07-05 plus `board-b-mmcblk0-20260806-preandroid.img`, which is the only
copy of the board carrying *our* stack after the layout migration. Restore the
Debian rootfs from the latter with:

```
sudo dd if=<preandroid.img> of=/dev/sda bs=512 skip=5555200 seek=5555200 count=9714655 conv=fsync
```

## eMMC layout (what goes where)

The board carries **two complete boot chains**. Only the 32 KiB first stage is
shared ground: the BROM reads it from LBA `0x10` and nowhere else, so that is
what gets swapped to change stacks. Android's A/B slots cover kernel and OS
only — they do not slot the bootloader — so the rest of each chain is given a
permanent home that the other chain never reads.

| LBA | Offset | Contents | Chain |
|-----|--------|----------|-------|
| `0x10` | 8 KiB | **first stage — our SPL *or* the vendor's boot0** | contended |
| `0x100` | 128 KiB | vendor boot0, second copy (the vendor's own location) | vendor |
| `0x6000`, `0x8020` | 12 MiB, 16.4 MiB | vendor boot package (TOC1: U-Boot, BL31, SCP, OP-TEE, DTB) — two copies, byte-identical to the OTA's `boot_package.fex` | vendor |
| `0x3000` | 6 MiB | vendor secure storage (`hdcpkey`, `wifiBleDatas`) — per-unit, irreplaceable | vendor |
| `0x49ac00` | 2.30 GiB | our U-Boot proper, at the start of the `empty` partition | ours |
| `0x49cc00` | +4 MiB | our SPL, stashed so the vendor side can switch back | ours |
| `0x49ec00` | +8 MiB | our U-Boot environment | ours |
| `bootloader_a` | 36 MiB | **the vendor's FAT16** — `mips/display.bin`, `mips/LogoRegData.bin`, `bootlogo` | vendor |
| `boot_a` | — | our kernel FIT | ours |
| `boot_b`, `vendor_boot_b`, `dtbo_b`, `vbmeta*_b`, `super` | — | vendor Android | vendor |
| `UDISK` (p26) | last | Debian root filesystem | ours |

Everything of ours except LBA `0x10` sits in the `empty` partition or in slot A,
clear of both the reserved region the vendor's boot0 reads and every partition
the vendor's U-Boot touches. Two bench findings drove that, in order:

- U-Boot proper used to live at LBA `0x50`, inside the reserved region, which is
  why restoring the vendor's boot0 alone failed.
- It then lived at LBA `0x12000`, the first sector of `bootloader_a` — which
  looked like OTA staging and is **not**. It is a live FAT16 holding the
  vendor's `mips/display.bin`, `mips/LogoRegData.bin` and `bootlogo`, and our
  image over its boot sector made the vendor's U-Boot print
  `** Unrecognized filesystem type **` and fail every display artifact load
  (bench 2026-08-06). Restore it from `local/stock-boot/bootloader_a-board-b.bin`.

`empty` (LBA `0x49ac00`, 15 MiB) is all zeros in the factory image and is named
in nothing the vendor boots — the only partition on this eMMC that is genuinely
free.

`bootloader_b` is the one remaining exception to the A/B split — this project
repurposed it to hold our copies of the MIPS display artifacts (`mmc 1:2`). It
is OTA staging, not part of the vendor's runtime chain, so the vendor still
boots without it.

`mmc1` is the eMMC in U-Boot; `mmc0` is disabled (no SD slot).

## Method 1 — from a running U-Boot over serial (`loady`)

No host root needed; works on the soldered UART. ~80 s for a 768 KiB image.

The image is written in two pieces now (see the layout above): the first 32 KiB
to LBA `0x10`, the remainder to LBA `0x12000`.

```
# in U-Boot:
loady 0x42000000
# host: send the file via YMODEM
tools/serial/ymodem_send.py u-boot-sunxi-with-spl-ddr3.bin --port /dev/ttyUSB0
# back in U-Boot — U-Boot proper first, then the first stage, so that an
# interrupted sequence leaves the old working first stage in place.
# Block counts must ROUND UP (907521 B = 0x6ed blocks).
mmc dev 1
mmc write 0x42008000 0x12000 0x6ed
mmc write 0x42000000 0x10 0x40
mmc read 0x43000000 0x10 0x40
cmp.b 0x42000000 0x43000000 0x8000
```

Prefer the CDC gadget (`tools/serial/load_fit.py`, ~171 KB/s) over the UART
(~11 KB/s) for anything large.

## Method 2 — expose the whole eMMC to the host (UMS)

```
# in U-Boot; if entered over ACM, keep this on one line because ACM disconnects:
run serial_mode; ums 0 mmc 1
# host: the eMMC appears as /dev/sdX with all 26 partitions
tools/boot-switch.sh install --dev /dev/sdX      # splits the image, verifies both halves
```

`boot-switch.sh` refuses to write a device whose partition table is not this
board's, and refuses any first stage that fails its own eGON checksum.

Rootless host I/O is possible via udisks2 `OpenForRestore` (D-Bus) if you can't
`dd` as root. Stop UMS with Ctrl-C on UART; the console remains serial-only.

### The USB gadget only works if Linux has not run since power-on (2026-08-09)

**Cold power-on → interrupt at `=>` → gadget mode works. Anything after a Linux
boot does not, and a warm `reboot bootloader` does not clear it.**

Observed repeatedly in one session. Every gadget success (a UMS session, a
fastboot rootfs flash) came from a cold boot stopped at the U-Boot prompt before
Linux ran. Every failure — UMS *and* fastboot, so it is not mode-specific — came
after Linux had booted, including immediately after a power cycle where the board
was allowed to autoboot into Linux first. The board sits spinning its `|/-\`
waiting for a host that never appears; the host logs no USB events at all.

Linux binds musb and leaves the controller in a state U-Boot's warm-reset path
does not reinitialise. The board prints `musb-hdrc: peripheral reset irq lost!`
when it is in this state.

**So to flash over USB: power-cycle and press a key during the boot delay.**
Letting it autoboot to Linux and then issuing `reboot bootloader` puts you right
back in the broken state — the RTC reboot-mode handoff is a *warm* reset.

**The wire-free fallback needs no USB at all** and is fully scriptable:

```
# host, ~12 min for a 7.7 MB FIT at 10.8 KB/s
tools/serial/load_fit.py build/out/h713-kernel.fit --port /dev/ttyUSB0 --addr 0x50000000
# then in U-Boot, persist it into the FAT:
fatwrite mmc 1:2 0x50000000 h713-kernel.fit ${filesize}
```

`loady` sets `filesize`, so use it rather than a hand-computed length. This is
slow but it is the path that always works, and it does not care what Linux did to
the USB controller.

### UMS is for small, targeted writes — not for flashing a rootfs (2026-08-09)

**A 4 GB `dd` to `UDISK` over UMS failed at ~1 GB and reported success.** Use
**fastboot (Method 3)** for anything rootfs-sized; it is the path with a hardware
precedent. Two independent faults, both worth knowing:

- **The desktop auto-mounted `sda26` read/write** the moment the gadget
  enumerated, so the raw `dd` was writing sectors underneath a live, journalling
  ext4 on the same device. `udisksctl unmount -b /dev/sdaN` **before** any raw
  partition write, and check `lsblk` rather than assuming.
- **The gadget dropped under a sustained stream.** The board printed
  `musb-hdrc: peripheral reset irq lost!`; the host logged `usb 5-1: USB
  disconnect` followed by `device offline error ... op 0x1:(WRITE)` and
  `EXT4-fs (sda26): Aborting journal`. It needed a power cycle, not another
  gadget mode.

**`dd` reported "4.3 GB copied, 1.0 GB/s" and exited 0.** That rate is ~30x what
USB 2.0 can carry, which is the tell: the write went to the page cache, the
device went offline, and `conv=fsync` had nothing left to flush to. **Score a
bulk write by its throughput, not its exit status** — any figure that beats the
transport is a measurement of RAM. `oflag=direct` makes the rate honest and
surfaces the error where it happens.

## Method 3 — fastboot

```
# in U-Boot (safe to issue from UART or as one line from ACM):
run fastboot_mode
# host:
tools/boot-switch.sh install --via fastboot   # ubootp @ 0x12000, then uboot @ 0x10
fastboot flash UDISK rootfs.simg          # rootfs (Android-sparse, see below)
```

The H713-specific raw targets are `uboot`/`bootloader` (LBA `0x10`, `0x40`
sectors — **the first stage only**), `ubootp` (LBA `0x12000`, U-Boot proper),
`vboot0` (LBA `0x100`, the vendor's boot0) and `splstash` (LBA `0x14000`). The
first-stage guard is deliberately exactly 32 KiB, so flashing the whole
concatenated image to `uboot` is rejected rather than quietly recreating the
old layout that overlapped the vendor's region. **Prefer the
`uboot` alias** — a slot-aware fastboot host silently rewrites `bootloader`
into the A/B slot name `bootloader_a` and writes that GPT partition instead of
the LBA-0x10 first stage. That used to be merely useless (a flash that
"succeeds" but changes nothing that boots); now that `bootloader_a` holds our
U-Boot proper, **it corrupts the running chain**. `uboot` is not a GPT
partition name, so the host passes it through verbatim.

All the aliases are in U-Boot's default env, and U-Boot injects any that an
older saved environment lacks. It also narrows a first-stage guard still left
at the pre-split `0x10 0x1ff0`, since that value is wide enough to write the
whole concatenated image back over the vendor's boot region; a value someone
set deliberately is left alone.

- The fastboot **download buffer is 32 MiB** → images larger than that must be
  **Android-sparse** (`img2simg in.img out.simg`); the host tool chunks them
  (e.g. a ~220 MiB sparse rootfs uploads in ~7 chunks / ~155 s).
- `fastboot usb 0` fails `g_dnl -22` if ACM still owns the USB controller.
  `run fastboot_mode` selects serial-only consoles before registering fastboot
  and returns to serial-only mode if fastboot exits. The helper is also injected
  when an older saved environment does not contain it.
- U-Boot's current `g_dnl` gadget layer registers one USB function at a time,
  so ACM and fastboot intentionally appear as two successive USB devices rather
  than simultaneous interfaces in one composite device.
- Close the old ACM/fastboot/UMS handle before switching. Resolve each new
  device by VID/serial rather than a fixed path; if the host retains a stale
  `1f3a:1010` identity across a board reset, use a full power cycle.

### Fastboot RAM staging and lifecycle commands

U-Boot can point its fastboot download buffer at a bounded RAM window. This is
useful for repeatedly loading the display coprocessor firmware without writing
eMMC:

```
# in U-Boot: exact display.bin address and size
run serial_mode; fastboot -l 0x4b100000 -s 0x132b18 usb 0; run serial_mode

# host: download directly to 0x4b100000, then leave fastboot WITHOUT resetting
fastboot stage display.bin
fastboot continue
```

**Exit staging with `fastboot continue`, never `fastboot reboot bootloader`.**
`continue` trips `g_dnl_detach()`, so `do_fastboot` returns, the rest of the
`;` sequence runs, and the board lands at the prompt with DRAM untouched.
Ctrl-C on UART breaks the same loop and is an equally clean escape.

A warm reset does **not** preserve staged RAM on H713, contrary to what this
section previously claimed: SPL re-runs DDR3 init and training, and
`0x4b100000` comes back as uninitialized DRAM. Bench-verified 2026-07-28 —
after `fastboot reboot bootloader` the window read `a41ef7f5 effffeff …` and
`h713_mips verify` reported SHA-256 `991c1364…`, the hash of noise. The same
stage exited with `fastboot continue` verified as the pinned `16c74a28…`.

This failure is quiet and dangerous: the staged region hashes to a plausible
value rather than reading back empty, so any experiment that skips
verification silently runs against garbage. Always `h713_mips verify` after
staging and before `start`, `probe-ready`, or `probe-trace`.

The lifecycle verbs below still reset by design. `fastboot reboot bootloader`
writes the same one-shot `0xb007c0de` marker to RTC GP7 (`0x0709011c`) as Linux
`reboot bootloader`; preboot consumes and clears the marker, disables autoboot,
and leaves the board at the U-Boot prompt. Use it to *reach* a prompt, not to
preserve anything in DRAM.

Power the board down through the same PSCI path used by Linux:

```
fastboot oem poweroff
```

The command acknowledges the host before powering off. A physical power cycle
is required afterward.

## Method 4 — cold recovery via FEL

Hold the **FEL button** at power-on to enter the BROM's USB FEL mode, then use
`sunxi-fel` (from the `external/sunxi-tools` build).

**The H713 FEL BROM does not stall on large bulk transfers** (corrected
2026-07-29). That earlier conclusion was a misdiagnosis, and the chunking
workarounds built on it have been removed. Measured on hardware: 48 KiB in a
single bulk request, 92.4 ms, ~530 KB/s, read back byte-identical. The link is
full-speed USB 1.1 with **64-byte** bulk packets, not high-speed 512.

What actually caused the "stalls": a raw `sunxi-fel write` bypasses the
swap-buffer relocation the SPL loader does, so a write based at `0x104000` runs
through the BROM's own IRQ stack (`0x105000`) and BSS (`0x10b300`). That kills
the BROM's USB stack mid-transfer and looks exactly like a bulk stall — timeout,
device still in `lsusb`, every later command hangs. `sunxi-fel` now refuses such
writes with an explicit error (see [reference/h713-fel-notes.md](reference/h713-fel-notes.md)).

### Recovering a clobbered first stage (verified 2026-07-29)

This is the procedure that works. It needs only a 64 KiB FEL transfer and no
host-side U-Boot upload.

1. Regenerate the payload — our own SPL, the first 32 KiB of the image whose
   U-Boot proper is already on eMMC:

   ```
   python3 - <<'EOF'
   d = open('build/out/u-boot-sunxi-with-spl-ddr3.bin','rb').read()[:32768]
   with open('external/u-boot/arch/arm/mach-sunxi/h713_spl_payload.h','w') as f:
       f.write("static const unsigned char h713_spl_payload[] = {\n")
       for i in range(0, len(d), 12):
           f.write("\t" + " ".join(f"0x{b:02x}," for b in d[i:i+12]) + "\n")
       f.write("};\n")
   EOF
   ```

2. Build the restore SPL:

   ```
   build/uboot-build.sh "$PWD/build/uboot-felmmc" hy200_h713_felmmc_defconfig spl/sunxi-spl.bin
   cp build/uboot-felmmc/spl/sunxi-spl.bin build/out/h713-restore-spl.bin
   ```

3. Power on holding the **FEL button**, then:

   ```
   external/sunxi-tools/sunxi-fel version
   external/sunxi-tools/sunxi-fel -p spl build/out/h713-restore-spl.bin
   ```

   UART should show `=== H713 SPL RESTORE ===`, the mmc scan, and
   `wrote 64/64 RESTORED-OK`.

4. Power-cycle. The board boots from eMMC again. Nothing else needs reflashing
   in the split layout: this writes sectors 16..79, and U-Boot proper at LBA
   `0x12000` was never in the contended range. Under the old layout it had to be
   followed by a full reflash, because U-Boot proper sat at LBA `0x50`.

Why it works: sectors 16..79 are the only range a first stage occupies, and
U-Boot proper survives at LBA `0x12000`, so restoring the SPL reconnects an
intact chain. The hook runs after the SPL framework has already brought eMMC up, and
picks the device by scanning for a non-zero `lba` — **mmc0 is the absent SD
slot here**, and using it fails with "Card did not respond to voltage select".

The 64 KiB upload goes through the SPL loader, which relocates around the
BROM-reserved regions, so it is unaffected by the raw-write hazard above.

**Known gap — `sunxi-fel uboot` does not work on H713.** Loading the SPL alone
is reliable (`sunxi-fel spl ...` returns and FEL still responds afterwards), but
transferring U-Boot proper fails, and the transfer completes yet the SPL still
sits at "Trying to boot from FEL" — so the **post-SPL handoff itself is broken**,
not just the transfer. `exe` and `reset64` at `CONFIG_TEXT_BASE` do not start it
either. Use the restore SPL above instead. Worth revisiting if anyone wants
`uboot` working: the `fel_stash` continuation path, which is what should resume
the SPL after the host writes U-Boot.

Two of the symptoms once cited here have since been explained and should not be
read as evidence about the handoff (2026-07-29): the `usb_bulk_recv() ERROR -8:
Overflow` was an undersized bulk IN buffer, now fixed; and the
`usb_bulk_send() ERROR -7` timeouts came from the raw-write hazard above.
**This gap has not been retested since those fixes landed** — do that first
before investigating `fel_stash`, because the transfer half of the problem may
already be gone. U-Boot proper also lands in DRAM, which is its own unresolved
issue on this board.

**Un-bricking a clobbered first stage:** the local-only recovery SPL
(`local/0001-...LOCAL-ONLY.patch`, embeds the vendor boot0 — never published)
FEL-loads once, rewrites the vendor boot0 to eMMC sector 16, and halts; power
cycle to boot the stock firmware. `git am` that patch into `external/u-boot` to
build it.

The same tool recovers **our** first stage instead, which is usually what you
want: replace `board/sunxi/h713_vendor_boot0.h` with an `xxd -i`-style array of
the first 32 KiB of `u-boot-sunxi-with-spl-ddr3.bin` and build
`hy200_h713_recovery_defconfig`. That range is sectors 16..79, and U-Boot proper
lives at LBA `0x12000` (`CONFIG_SYS_MMCSD_RAW_MODE_U_BOOT_SECTOR=0x12000` with
`DATA_PART_OFFSET=0x0`), so restoring only the SPL reconnects an otherwise
intact chain. Apply the patch with `git apply`, not `git am`, so the vendor blob
never reaches a commit.

The blob it embeds is board B's own boot0, byte-identical to LBA 16 of the
2026-07-05 capture and checksum-valid — not the OTA's `boot0_sdcard.fex`.

**Restoring the vendor's boot0 alone failed under the old layout.** It came up
and inited DRAM correctly, then reported `bad magic` / `Loading boot-pkg
fail(error=4)` and `region magic is not right`. Both strings live in boot0
itself. The most likely cause is that our U-Boot proper then occupied LBA
`0x50`, inside the reserved region boot0 reads and which is all zeros on a
stock board; the split layout above moves it out. Retest before assuming
either way.

## Standalone boot (power-on → Debian)

To boot the kernel from eMMC with no host attached — flash the FIT to `boot_a`
and set a U-Boot `bootcmd` — see [standalone-boot.md](standalone-boot.md)
(`tools/flash-standalone.sh`).

## Method 5 — switching between our stack and the vendor's

Rewritten 2026-08-06. The immediate goal is the two seconds of vendor U-Boot
output that say whether the vendor's own backlight setup succeeds (`Display
fastlogo finish!`) or fails (`Pwm enable fail:%d`, `backlight enable fail:%d`,
`Create backlight instance fail!`) — but the mechanism below is general, and
leaves both chains permanently installed so the board can be moved either way.

### What the earlier version of this section got wrong

It said stock's boot package was gone from every sector `boot0` references, so
restoring stock would mean writing an inferred sector over unidentified data
with no backup in existence. Three of those premises are false:

- **The backups exist.** `local/h713-lab/captures/board-b/` holds four full
  7.8 GB images of this board taken 2026-07-05, before anything of ours was
  written. All four agree byte-for-byte over the first 36 MiB, the boot0 in
  them has a valid eGON checksum, and their boot package is byte-identical to
  the OTA's `boot_package.fex`. `bench_bt0.img` matches their LBA-16 boot0
  exactly, which is what identifies the bench board as board B.
- **The boot package is in the capture** at LBA 24576 *and* 32800, byte-identical
  to the OTA's `boot_package.fex`. It is **not on the live board**: re-read
  2026-08-06 with `mmc dev 1;` on the same line, LBA 24576 holds high-entropy
  data and LBA 32800 holds the big-endian records `1,3,4,0x202` / `1,3,4,0x7d`,
  exactly as first reported. The vendor's own boot0 independently agrees —
  chainloaded on a working eMMC it reads both locations and prints
  `error:bad magic.` twice, then `Loading boot-pkg fail(error=4)`.
  A guess that this was a stale-DRAM misread is **refuted**; the original bench
  finding was correct. `mmc partconf 1` also rules out the boot hardware
  partitions: `BOOT_PARTITION_ENABLE 0x0`, `PARTITION_ACCESS 0x0 (user)`, so
  boot0 is reading the user area, which is what the captures cover.
  **The live board diverged from its own 2026-07-05 capture in this region and
  we do not yet know what wrote it.**
- **The OTA's `boot0_sdcard.fex` is the wrong file for this board.** It differs
  from board B's own boot0 in 18 bytes: the checksum plus four fields inside
  the header's `dram_para` block. Feeding one board's DRAM parameters to
  another is the documented way to make training "succeed" and reads hang. Use
  `local/stock-boot/boot0-board-b-emmc-sector16.bin`, extracted from the
  capture (sha256 `b769a415…`), which `tools/boot-switch.sh` checksums before
  every write.

What *was* right is that restoring the vendor's boot0 alone does not work: it
comes up, inits DRAM, then reports `bad magic` / `Loading boot-pkg
fail(error=4)` and `region magic is not right`. Both messages are strings in
boot0 itself. In the capture, the reserved region is zeros everywhere except
boot0 (16–79), its second copy (256–319), the secure-storage block at 6 MiB and
the boot packages — so the only thing that could have looked "damaged" to it
was our U-Boot proper, which used to sit at LBA `0x50`. **This is a hypothesis,
not a proven diagnosis**; it is the reason for the layout change above, and the
first switch attempt is also its test.

### One-time migration to the split layout

Do this in order, from our U-Boot, with the FEL button within reach. Until step
3 completes the board still boots the old way, so an interruption is survivable.

1. Rebuild. `CONFIG_SYS_MMCSD_RAW_MODE_U_BOOT_SECTOR=0x12000`,
   `CONFIG_SYS_MMCSD_RAW_MODE_U_BOOT_DATA_PART_OFFSET=0x0` and
   `CONFIG_ENV_OFFSET=0x3400000` in `hy200_qz713df_a1_defconfig` move U-Boot
   proper and the environment out of the vendor's reserved region. Verified in
   the artifact, not just the config: `spl_mmc_load_image` passes `0x12000`.
2. **Regenerate the FEL restore SPL from the new build** before writing
   anything (the procedure in Method 4). The one on disk embeds an SPL that
   looks for U-Boot proper at the old LBA `0x50`, and step 6 zeroes that — so a
   stale restore SPL would "recover" the board into something that cannot boot.
3. **Teach the running (old) U-Boot the new fastboot targets.** It predates
   them, and its runtime injection only knows the old set:

   ```
   setenv fastboot_raw_partition_ubootp 0x12000 0x2000
   setenv fastboot_raw_partition_vboot0 0x100 0x40
   setenv fastboot_raw_partition_splstash 0x14000 0x40
   saveenv
   ```
4. Write both halves. `install` flashes U-Boot proper **first**, so a
   half-finished run leaves the old working first stage rather than a new one
   pointing at nothing:

   ```
   tools/boot-switch.sh install --via fastboot
   ```
5. Power cycle. The new chain boots. Re-apply any saved settings and `saveenv`:
   the environment moved to LBA `0x1a000`, so the old one at 4 MiB is gone,
   including the standalone `bootcmd`.
6. Zero what we abandoned in the vendor's region — the old U-Boot proper at
   LBA `0x50` onwards and the old environment at `0x2000`. In the capture that
   whole range is zeros, and it is the prime suspect for `region magic is not
   right`. **This must come before step 7**, because the old U-Boot proper
   covers LBA `0x100`, where the vendor's boot0 is about to go.
7. Make both chains resident: the vendor's boot0 to LBA `0x100`, its own
   second-copy location, and our SPL stashed at LBA `0x14000`:

   ```
   tools/boot-switch.sh stage --via fastboot
   ```

### Switching, once migrated

**To the vendor for one boot** — the normal way. Ours stays installed at LBA
`0x10` and stays the default; nothing is written to eMMC at all:

```
run boot_vendor          # from our U-Boot: arms the RTC marker and resets
reboot vendor            # from Debian: same marker, via nvmem-reboot-mode
```

The SPL sees marker `0x001db007` in RTC GP7 (`0x0709011c`, the same word that
already carries the fastboot and prompt markers), **consumes it before doing
anything else**, reads the vendor's boot0 from LBA `0x100`, verifies its eGON
checksum, and enters it in AArch32. Because the marker is one-shot:

- the next reset after the excursion comes back to ours, with nothing to undo;
- a vendor chain that hangs costs a power cycle, not the FEL button;
- any failure in the SPL — no marker, bad checksum, eMMC not there — prints why
  and boots ours normally.

`tools/boot-switch.sh stage` is what puts the vendor's boot0 at LBA `0x100`; the
chainload prints `no valid vendor boot0` and carries on booting ours if it is
missing.

**To the vendor persistently**, when you want it to survive resets — this one
does write LBA `0x10`, and then ours is not running any more:

```
run switch_vendor
```

It copies LBA `0x100` → `0x10`, refusing to write unless what it read carries
the `eGON` magic. Power cycle to boot it. **Back to ours** after that, either
the FEL button:

```
tools/boot-switch.sh ours --via fel
```

or, if the vendor's U-Boot gives you a prompt, the stash — no host at all:

```
mmc dev 1; mmc read 0x48000000 0x14000 0x40; mmc write 0x48000000 0x10 0x40
```

The vendor's U-Boot does contain `fastboot`, `sunxi_flash` and `dump_boot0`
(strings in `u-boot-stock.bin`), and rooted `adb` + `dd` on vendor Android is
proven — that is how the 2026-07-05 captures were taken. **Whether the vendor
gives an interruptible prompt at all is untested**, so do not treat the stash
as the primary return path until someone has seen it work. FEL is the one that
has been verified.

**Reading which is installed** needs the eMMC visible to the host
(`run serial_mode; ums 0 mmc 1`):

```
tools/boot-switch.sh status --dev /dev/sdX
```

### Always put `mmc dev 1;` on the same line

The current MMC device resets to slot 0 between commands, and slot 0 is disabled
on this board (no SD). A bare `mmc read` then fails with `MMC Device 0 not
found` — but `md` afterwards happily prints whatever was already in DRAM, which
looks like plausible data. This wrecked three separate results on 2026-08-05,
including a `cmp.b` verify and, worse, a **backup**:

```
mmc read 0x48000000 0x8020 0x980     <- failed, device 0 not found
fatwrite mmc 1:2 0x48000000 backup_8020.bin 0x130000
1245184 bytes written in 95 ms       <- wrote 1.2 MB of uninitialised DRAM
```

That file is not a backup and restoring from it would destroy the region it
claims to protect. Always:

```
mmc dev 1; mmc read <addr> <lba> <cnt>; md.b <addr> 0x20
```

and confirm the `MMC read: ... blocks read: OK` line before trusting the dump.

### Do this first

Confirm the Android partitions really are intact — read-only, costs nothing:

```
part list mmc 1
```

**Verified 2026-08-05:** all 26 partitions present and matching
`sys_partition.fex` exactly (`bootloader_a` at LBA `0x12000`, `boot_a` 131072
sectors, `super` 4194304 sectors, `UDISK` last). Note `mmc 1:2` is
`bootloader_b`, which this project has repurposed to hold the MIPS artifacts, so
the stock B-slot resource is already gone.

Expect `boot_a`, `super`, `vendor_boot_a`, `misc`, `UDISK` and friends. If they
are gone, stop; stock will not boot and this method does not apply.

### Capturing the vendor console

Power cycle after `run switch_vendor` — **not** `fastboot reboot bootloader`,
whose RTC marker is consumed by *our* preboot, which will no longer be running.
**Capture the UART from the first byte:** the interesting lines appear within
about two seconds, before Android starts.

Once `Display fastlogo finish!` or a `Pwm enable fail` has been printed, cut the
power. Letting vendor Android boot to completion risks it reformatting `UDISK` —
where the Debian rootfs lives — and touching `misc`/`metadata`. Nothing in this
test needs userspace.

The vendor's Android is in **slot B** (`boot_b`, `vendor_boot_b`, `dtbo_b`,
`vbmeta*_b`, plus the shared `super`); slot A's `boot_a` holds our kernel FIT,
so with `misc` still selecting slot A the vendor will fail AVB and may retry or
sit there. That is harmless for reading the U-Boot console, and is the reason
the A/B split is worth keeping tidy.

### Risks, stated plainly

- Android booting to completion is the one outcome that can lose real data. Pull
  power early. Worst case is a rootfs rebuild, not a lost board: the boot region
  is reproducible from source and the 2026-07-05 captures cover everything else.
- If the vendor's boot0 does not find its boot package it will hang. FEL
  recovers it.
- With a valid vendor boot0 at LBA `0x100`, a corrupt first stage at `0x10` may
  now boot **the vendor** instead of dropping to FEL. Whether the BROM really
  falls back to 128 KiB is inferred from the vendor keeping a copy there, not
  tested. Run `tools/boot-switch.sh status` before concluding what is installed.
- Never write the OTA's `boot0_sdcard.fex` to this board — wrong DRAM
  parameters, see above.

### What the chainload assumes — bench results, 2026-08-06

The three assumptions the design rested on all **held on the first run**:

1. **The vendor's boot0 tolerates a live DRAM controller.** This was the
   biggest unknown: the handoff happens after `sunxi_dram_init()`, because the
   SPL's BSS lives in DRAM (`CONFIG_SPL_BSS_START_ADDR=0x4ff80000`) and the MMC
   stack needs it. boot0 re-inits DRAM unconditionally and did so happily —
   `DRAM CLK = 624 MHz`, `Type = 3 (DDR3)`, `DRAM simple test OK`, 1024 MiB.
2. **`eret` with `SCR_EL3.RW=0` lands boot0 somewhere it can work** — for
   everything boot0 does under its own power. It runs at Secure EL1 rather than
   AArch32 Secure PL1 and does not care while setting PLLs, initialising DRAM
   and the eMMC, or loading and enumerating its boot package. **It does care at
   the very last step.** boot0's `monitor` entry is an AArch64 BL31, so
   entering it means writing `RMR` — EL3-only. From EL1 that faults to a vector
   nobody set up, and the console goes silent immediately after
   `Jump to second Boot.`

   **The RVBAR route does not fix this (bench 2026-08-06, negative result).**
   Pointing Allwinner's writable RVBAR alias at `0x104000` and warm-resetting
   this core into AArch32 via `RMR_EL3` (`RR=1`, `AA64=0`) does not enter boot0
   at EL3: the core lands at the AArch32 reset vector, the BROM re-runs, reads
   LBA `0x10`, and boots **our** first stage instead. The SPL banner simply
   appears twice. So on this SoC RVBAR governs the AArch64 reset address only,
   as the Cortex-A53 TRM implies, and there is no way to hand boot0 a real EL3
   from inside a running AArch64 SPL.

   Consequences: a *complete* vendor boot needs the BROM to load boot0 itself,
   which means the persistent swap (`run switch_vendor`). The one-shot
   chainload remains valuable as a diagnostic — it is how the destroyed boot
   package was found — and could be made to boot the vendor fully only by
   having our SPL do boot0's second half itself: parse the TOC1 package and
   enter BL31 in AArch64 EL3 directly, never entering AArch32 at all.
3. **`0x00104000` is where boot0 wants to be.** Independently confirmed by
   `CONFIG_SUNXI_SRAM_ADDRESS=0x104000` — the same address the BROM loads our
   own first stage to.

What the first run *did* find is a handoff detail with no counterpart in the
BROM-less path:

**`boot_media` is written by the BROM into the header of the copy in SRAM, and
is not part of the image on disk.** A pristine boot0 therefore reads it as 0,
concludes it was booted from MMC0 — the absent SD slot — and fails:

```
[333][mmc]: Wrong media type 0x0
[337][mmc]: ***Try SD card 0***
[390][mmc]: ***SD/MMC 0 init error!!!***
[543]Loading boot-pkg fail(error=2)
```

The chainloader now copies that byte (header offset `0x28`, which mainline
calls `boot_media` and the vendor layout calls `platform[0]`) out of our own
BROM-patched header into the staged image, after the checksum check and before
the handoff — the same order the BROM itself uses. No media code is hardcoded.

The trampoline is copied to DRAM and run from there, because the copy
overwrites the SPL's own text at `0x104000`. It is position-independent with no
literal pool — check the disassembly if you change it.

The trampoline is copied to DRAM and run from there, because the copy
overwrites the SPL's own text at `0x104000`. It is position-independent with no
literal pool — check the disassembly if you change it.

## Method 6 — boot the vendor's Android

Reaching the projector app (and its brightness control, and anything else only
the UI exposes) needs three things beyond a vendor bootloader. Verified
2026-08-06: Android boots to the launcher.

**1. `boot_a` must hold the vendor's boot image.** This project had been using
it for our kernel FIT, which makes the vendor's U-Boot data-abort immediately
after `update bootcmd`. Restore it, and put our kernel somewhere else first —
a file in the FAT on `mmc 1:2` works and needs no layout change:

```
fatwrite mmc 1:2 0x50000000 h713-kernel.fit 0x758238
setenv bootcmd 'fatload mmc 1:2 0x50000000 h713-kernel.fit; bootm 0x50000000'
```

Prove Debian still boots that way **before** giving up `boot_a`. Then, over UMS
(`sda5` is `boot_a`):

```
sudo dd if=local/stock-boot/boot_a-board-b.img of=/dev/sda5 bs=1M conv=fsync
```

**2. `UDISK` must be f2fs.** Android's `userdata` is `by-name/userdata` =
`mmcblk0p26` = `UDISK`, the same partition our Debian rootfs lives on. `fs_mgr`
checks the magic, finds ext4, and refuses:

```
mount_with_alternatives(): skipping mount due to invalid magic, ... rec[3].fs_type=f2fs
vdc: Command: cryptfs init_user0 Failed
init: Failure (reboot suppressed): init_user0_failed
```

It does **not** format for you — the rootfs survives that failure untouched, it
just never reaches the launcher. There is no free 4 GiB elsewhere on this eMMC,
so the two stacks genuinely contend for it. Back up `UDISK` first, then:

```
sudo make_f2fs -g android /dev/sda26
```

The retail image is a `user` build with no `su` and no `sudo`, so this cannot be
done from the Android console shell — `make_f2fs` exists at `/system/bin/` but
fails with `Failed to open the device!`. Do it from the host over UMS.

**3. `super` must be intact** — see Safety.

Everything else in slot A (`vendor_boot_a`, `dtbo_a`, `vbmeta*`, `misc`) was
never touched by this project and verified byte-identical to the capture.

### Vendor-derived artifacts

All extracted from `board-b-mmcblk0-20260705T075628Z.img`, all in the ignored
`local/stock-boot/`, none committed.

| file | goes to | size |
| --- | --- | --- |
| `boot0-board-b-emmc-sector16.bin` | LBA `0x10` / `0x100` | 32 KiB |
| `boot-package-board-b.bin` | LBA 24576 and 32800 | 1.2 MiB |
| `reserved-8-18MiB-board-b.bin` | LBA `0x4000` (8–18 MiB) | 10 MiB |
| `bootloader_a-board-b.bin` | LBA `0x12000` = `bootloader_a` = `sda1` | 32 MiB |
| `boot_a-board-b.img` | `boot_a` / `sda5` | 64 MiB |
| `super-repair-1MiB.bin` | LBA 3337216 | 1 MiB |

## Safety

- Always name the board a flash ran on — feeding the projector's HY200 QZ713_V2 (LPDDR3) params to the
  HY200 (DDR3) board trains "OK" but reads hang.
- **Read a region back and diff it against the capture after flashing to any new
  offset.** This project has written somewhere it did not intend three separate
  times, each invisible until something read the region back:
  - a 32-bit smoke-test FIT at raw LBA `0x4000`, on top of both vendor
    boot-package copies and the `sdmmc_arg` timing region;
  - U-Boot proper at LBA `0x12000`, over `bootloader_a`'s FAT16 boot sector;
  - **64 KiB of U-Boot environment inside `super`** at LBA 3337216
    (`0x65d80000`), from a `saveenv` under some earlier `CONFIG_ENV_OFFSET`.
    `super` carries dm-verity-protected images and `vbmeta_*` still expects the
    original, so this would have presented as "Android just doesn't boot".
    Repaired from `local/stock-boot/super-repair-1MiB.bin`.

  All three were found by diffing a full read against the 2026-07-05 captures.
  None would have been found by verifying the write itself.
- **Full eMMC backups do exist**, contrary to what this document said between
  2026-08-05 and 2026-08-06: `local/h713-lab/captures/board-b/` (four images of
  the bench board, 2026-07-05, pre-modification) and
  `local/h713-lab/captures/board-a/` (two, 2026-06-22). They are 7.8 GB each and
  carry per-unit secrets — the secure-storage block at 6 MiB holds `hdcpkey` and
  `wifiBleDatas` — so they stay in the ignored `local/` tree and are never
  committed. The retail OTA package at
  `~/Documents/projector_firmware/H713 Magcubic projector.20250922.093247/update.img`
  is a *different board's* firmware build; prefer the captures.
- Take a fresh capture before the next destructive operation anyway. The
  existing ones predate every write this project has made.
