# The shipped environment

U-Boot ships with a compiled-in default environment (`board/sunxi/hy310.env`). Once `saveenv` has run
once, the saved copy on eMMC wins outright - U-Boot does not merge the two - and this file no longer
applies until that saved copy is erased. Everything below is the shipped default; check `printenv` on a
device that has ever been touched before trusting it.

## Variables

| Variable | Default | What it does | When to touch it |
|---|---|---|---|
| `h713_boot` | `emmc` | which of `boot_emmc`/`boot_net` `bootcmd` runs | `net` forces the network path |
| `h713_gate` | `1` | the power-on gate, on or off (`power-gate.md`) | `0` disables the gate without a rebuild |
| `h713_project` | `0x30` | the vendor project/panel ID `h713_disp init` loads | only if the display firmware ever needs to target different hardware |
| `h713_mips_dev` | `1#hy310-boot` | partition the display-firmware artifacts load from, by name | `1:2` on a device that still has the vendor FAT partition |
| `h713_mips_path` | `mips` | directory on that partition | rarely - only if the artifacts move |
| `bootfile` | `h713-kernel-netboot.fit` | FIT image `boot_net` fetches over TFTP | development only |
| `serverip` | `192.168.8.123` | TFTP/NFS server `boot_net` talks to | development only |
| `nfsroot` | `/srv/h713-rootfs` | NFS export `boot_net` mounts as root | development only |
| `bootargs_base` | `console=ttyS0,115200 rootwait clk_ignore_unused pd_ignore_unused cma=128M net.ifnames=0` | kernel command line shared by both boot paths | rarely |

**`serverip`, `nfsroot` and `bootfile` are development defaults, not a general feature:** they point at
the bench network this project was built on and resolve to nothing anywhere else. A device shipped to a
reader has no reason to reach them and should stay on `h713_boot=emmc`; point them at your own server if
you want the network path at all.

## `boot_emmc` against `boot_net`

Both start from `bootargs_base` and add different things on top. `boot_emmc` - the shipping path - reads
`h713-kernel.fit` from the eMMC (`ext4load mmc 1:5`), boots at `loglevel=4`, roots from
`PARTLABEL=hy310-rootfs`, and deliberately drops `earlycon`: a production console does not need to see
the decompressor run. `boot_net` instead fetches `bootfile` from `serverip` over TFTP and mounts
`nfsroot` over NFS as root, and keeps `earlycon` - the whole point of the bench path is that a kernel
dying before its own console driver comes up still says where. `bootcmd` tries `boot_emmc` first and
only falls through to `boot_net` if that does not find a kernel to boot.

## `run fel`

Reboots into FEL without touching the reset button. It writes the vendor's `efex` magic (`0x5aa5a55a`)
into RTC GP2 (`0x07090108`) and resets; the BootROM itself ignores that flag on this SoC - tested by
writing it and resetting, which just rebooted normally - so the check is carried in our own SPL instead:
a short ARM32 stub in `arch-sunxi/boot0.h`, placed before the PLLs, MMU or caches are touched, reads GP2
twice (both reads must agree, because the RTC block sits on a slow clock), clears it, and jumps straight
into the BootROM's FEL entry. `run fel`'s own write-until-it-reads-back loop exists for the same
slow-clock reason. Without that SPL patch, or with a first stage that has not been rebuilt to include it,
`run fel` does nothing but reboot (`doku/nachtlog/S48-fel-aus-uboot.md`).

## Where it lives, and changing it from Linux

The saved environment is a single, non-redundant 64 KiB block at byte offset `0x700000` (LBA 14336) on
the eMMC (`doku/109-plan-layout-v3.md`). From a running Debian, read and change it with
`fw_printenv`/`fw_setenv` (package `libubootenv-tool`, in the shipped image) against `/etc/fw_env.config`:

```
/dev/mmcblk0	0x700000	0x10000
```

A device flashed before the eMMC layout moved to this offset (layout v3, 10.09.2026) carries its saved
environment at the older location instead; `h713-install` finds and migrates it by scanning for a valid
CRC rather than assuming the offset (`doku/30-uboot-aenderungen.md` §16, `doku/nachtlog/S41-r1-installer.md`).

Details: `mainline/external/u-boot/board/sunxi/hy310.env`, `doku/105-plan-release.md`,
`doku/109-plan-layout-v3.md`.
