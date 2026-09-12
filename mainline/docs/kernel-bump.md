# Kernel bump: 6.16.7 → 6.18.38 LTS

The kernel is carried as a patch series (`patches/kernel/`) on a pinned
mainline tarball, so a version bump is a **rebase**, not a merge. This is the
move off `6.16.7` onto the newer **6.18.38 longterm** kernel.

## Status: rebased and building (2026-07-18)

`config/versions.env` is pinned to **6.18.38**; `build/build.sh kernel` applies
all 24 patches cleanly and builds `Image.gz`. Of the 22 driver patches, 18
applied clean; the rebase needed five small fixes, all captured in the series:

| Patch | 6.18 change | Fix |
|-------|-------------|-----|
| 0004 pinctrl | `of_fwnode_handle(node)` → `dev_fwnode(&pdev->dev)` shifted the hunk | re-derived hunk #2 (`if (pctl->irq)` wrap + `-ENXIO` grace) on current code |
| 0005 usb-phy | `struct sun4i_usb_phy_cfg.num_phys` → `missing_phys` bitmask | `.num_phys = 3` → `.missing_phys = BIT(3)` (MAX_PHYS=4) |
| 0008/0009 hy310 | legacy `devm_gpio_request` removed | → `devm_gpio_request_one(..., 0, ...)` (direction set separately) |
| 0015 misc | Kconfig/Makefile neighbours added (`rp1`) | re-derived the registration hunks |
| 0020 pmdomain | Kconfig/Makefile neighbours added (`pck600`) | re-derived the registration hunks |

The `SUN20I_D1_R_CCU` arm64 enable is now a proper patch (**0023**), replacing
the earlier scripted sed (which was too broad — it also hit `SUN20I_D1_CCU`).

The arm64 board **DTS** is now reconstructed and in the series (**patch 0024**),
so `build/build.sh kernel` emits the DTB and a bootable FIT
(`build/out/h713-kernel.fit`: gzip Image + DTB, load/entry `0x48000000`).

**Boot-verified (2026-07-18):** `h713-kernel.fit` was booted on the HY200 bench
board — `uname -r` = `6.18.38`, `nproc` = 4, root on eMMC `mmcblk0p26`, Debian
13 to a root login. Also verified booting **standalone** from the `boot_a`
partition (see [standalone-boot.md](standalone-boot.md)). 6.18.38 is the
boot-good kernel.

## Why 6.18.38 (longterm), not 7.1.3 (stable)

- **Support window** — 6.18 is a longterm branch (multi-year fixes); 7.1.3 is a
  regular stable that is superseded within weeks.
- **Smaller rebase** — 6.16 → 6.18 touches far less of the conflict-prone glue
  (CCU, pinctrl, Panfrost/Mali DRM, cedrus, IOMMU) than 6.16 → 7.1.
- It is the first LTS that is *newer* than our 6.16.7 (earlier LTS ~6.12 was
  numerically older — a downgrade).

## Procedure

1. Bump the pin: `KERNEL_VERSION=6.18.38` in `config/versions.env` (keep
   `KERNEL_TARGET` pointing at the next candidate).
2. `build/build.sh kernel` fetches the new tarball and tries the series. Expect
   fuzz/rejects — resolve per subsystem, in `series` order. The arch-neutral
   0001–0022 are the most likely to need touch-ups in CCU/pinctrl/cedrus.
3. Re-derive the two arm64 additions against the new tree:
   - refresh `board/hy200_qz713df_a1_defconfig` (new/renamed symbols),
   - re-confirm the `SUN20I_D1_R_CCU` `|| ARM64` Kconfig enable still applies.
4. **Land the board DTS** (the piece missing today): reconstruct
   `sun50i-h713-hy200-qz713df-a1` for arm64 from the 32-bit board DTS in
   `allwinner-h713-linux/dts/` plus `arm,armv8-timer` and the
   `secure-bl31@40000000 reg=<0x40000000 0x100000> no-map` reservation. Add it
   as a board patch so `build/build.sh kernel` can emit a DTB + bootable FIT.
5. Build `Image` + DTB, wrap as a FIT (`arch=arm64`, load/entry
   `KERNEL_LOAD=0x48000000`), boot on the **HY200 bench board** (never the
   projector first). Confirm 4-core SMP + HS400 eMMC as on 6.16.7.

## Watch items

- The 22 patches were authored against 6.16.7; treat every hunk that fuzzes as a
  review point, not an auto-accept.
- Keep BL31 / U-Boot pins unchanged across the kernel bump — isolate variables.
- Re-run the full boot-to-root-login check (see docs/status.md) before pinning
  6.18.38 as the new `KERNEL_VERSION`.
