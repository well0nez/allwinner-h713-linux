# Standalone boot (power-on → Debian, no host)

By default the board reaches a U-Boot prompt and its `bootcmd` runs the distro
boot (which just spams BOOTP/PXE). To make **power-on boot straight into
Debian** with nothing attached, write the kernel FIT to the `boot_a` partition
and point `bootcmd` at it.

> **Validated on hardware (2026-07-18):** on the HY200 bench board this flow
> boots Debian 6.18.38 from `boot_a` after a plain `reset`, with no host
> attached (verified byte-exact `mmc write`, then autonomous boot to a root
> login on all 4 cores).

## The plan

- `build/build.sh kernel` produces `build/out/h713-kernel.fit` (gzip Image +
  `sun50i-h713-hy200-qz713df-a1` DTB, load/entry `0x48000000`).
- `boot_a` is **GPT partition 5**, start LBA `0x32400` (205824), **64 MiB** —
  the factory Android boot slot, unused by our stack, so we repurpose it as a
  raw FIT blob (7.7 MiB fits with room to spare).
- `bootcmd` reads `boot_a` into DRAM and `bootm`s it. The rootfs is already on
  `UDISK` (p26) per [rootfs.md](rootfs.md); the DTB's bootargs point root there.

Full chain, no host: `BROM → SPL (DRAM) → BL31 → U-Boot → read boot_a → bootm → Debian`.

## Steps

**1. Build the FIT** (host):

```
build/build.sh kernel        # -> build/out/h713-kernel.fit
```

**2. Flash it to `boot_a`.** Put the board in fastboot mode from the default
UART console, or issue the helper as one line from the opt-in ACM console:

```
run fastboot_mode
```

Then from the host (the FIT is 7.7 MiB < the 32 MiB fastboot buffer, so **no
sparse needed**):

```
tools/flash-standalone.sh                 # wraps: fastboot flash boot_a <fit>
```

**3. Set `bootcmd`** at the `=>` prompt (after a `reset` restores the console):

```
setenv bootcmd 'mmc dev 1; part start mmc 1 5 bootstart; part size mmc 1 5 bootsize; mmc read 0x50000000 ${bootstart} ${bootsize}; bootm 0x50000000'
setenv bootdelay 2
saveenv
reset
```

That's it — the board now boots to a Debian root login on its own.

## Why these values

- **`0x50000000`** is the FIT scratch load address: clear of BL31 (`0x40000000`),
  the kernel's own load/entry (`0x48000000`, decompressed ~17 MiB), and every
  `reserved-memory` region in the DTS (all at `0x4b…`/`0x78…`). U-Boot reads
  the FIT here, `bootm` decompresses the kernel down to `0x48000000` and hands
  over — arm64 needs no `fdt_high`/`initrd_high` juggling.
- **`part start/size … 5`** reads `boot_a` by partition number (robust to the
  exact LBA); the raw sectors are `0x32400` + `0x20000` if you prefer to
  hardcode `mmc read 0x50000000 0x32400 0x20000`.
- **`bootdelay 2`** leaves a 2 s window to interrupt into U-Boot for recovery.

## Reverting / recovery

- Interrupt the 2 s `bootdelay` to get the `=>` prompt.
- Restore the old behaviour: `setenv bootcmd 'run distro_bootcmd'; saveenv`.
- The kernel FIT can be rebuilt and re-flashed to `boot_a` any time; the rootfs
  on `UDISK` is independent. A full eMMC backup exists (see [flash.md](flash.md)).
