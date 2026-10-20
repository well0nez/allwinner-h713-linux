# `mainline/patches/aic8800/` - the Wi-Fi and Bluetooth driver as a patch series

The AIC8800 driver is carried like the kernel: a pinned vendor tarball and a series of our own on top of it, no
fork and no driver source in this repository. The files are named `aic8800-*.patch` so that nobody takes them for
kernel patches; they never touch the kernel tree.

## How it is built

The base is [radxa-pkg/aic8800](https://github.com/radxa-pkg/aic8800) at `df4c783b`, the vendor's driver release
`2026_0123_5f7be68d`; commit, URL and sha256 are pinned in `mainline/config/versions.env`. `build.sh aic8800`

1. applies Radxa's own series (`debian/patches/series`) to the **whole** tarball, because those patches change the
   PCIe, SDIO and USB copies of the driver together;
2. takes the SDIO driver out of it (`src/SDIO/driver_fw/driver/aic8800`);
3. applies `series` of this directory with `git am -3`, so a patch meets its base with a three-way merge;
4. builds the modules against the kernel tree of the same build.

Two of Radxa's patches do not apply at this commit, and that is expected: `fix-usb-firmware-path` (USB only) and
`fix-Lower-the-debugging-log-level` (already in the source). They are named in `AIC8800_VENDOR_PATCH_SKIP`, so
that any other one that stops applying still stops the build.

## The series

| Patch | What it does |
|---|---|
| `0001` | a build target `CONFIG_PLATFORM_MAINLINE_SUNXI` next to the vendor's platforms |
| `0002` | the bring-up on the H713: power through `wlan_regon`, finding the host `4021000.mmc`, `mmc_detect_change()`, the host wake line, DDR50 off - all behind `CONFIG_PLATFORM_MAINLINE_SUNXI` |
| `0003` | the SDIO clock and the time the driver waits for the chip (below) |
| `0004` | the firmware array (a 1.9 MB blob in a C file) is included only with `CONFIG_FIRMWARE_ARRAY`, so it stays out |
| `0006` | the self-managed regulatory domain can be set (module parameter `default_ccode`); `h713-wifi` sets the country and checks it with `iw reg get` |
| `0007` | the power line comes from the device tree (kernel `0155`) |
| `0008` | the association messages go through `aicwf_dbg_level` (cstenger's `0007`) |
| `0009` | the `rc_stat` queue is drained completely instead of one entry per run, and two arrays sized for 32 stations, while indexes up to 36 are accepted, are sized for 36 (the broadcast and multicast pseudo-stations wrote past their end); his `0008` |
| `0010` | the debugfs unregistration in AP mode is really compiled (his `0009`; the switch `CONFIG_DEBUG_FS_AIC` it waited for exists nowhere) |

There is no `0005`.

`0003` changes two constants outside the platform switches, easy to miss when reading the diff:
`FEATURE_SDIO_CLOCK_V3` from 150 MHz to 0, which makes the driver keep the rate the MMC core negotiated instead of
setting its own (it applies to `PRODUCT_ID_AIC8800D80`, our chip; the bus speed is then the host's, kernel `0045`
and `0048`), and the wait for the chip from 2 to 20 s. Where they come from is not proven: there is no untouched
vendor release `2024_0109` to compare with. They are carried on because leaving them out is the larger risk. The
clock is most likely a way around the earlier FIFO and CMD53 errors and an open question, not a settled value:
change it only against a measured baseline, one step at a time.

Not taken over on purpose: compatibility changes of our own for newer kernels (Radxa's series covers them, per
kernel version), a hard-wired `KDIR` (the build passes it), and the old driver copy that had missed two years of
the vendor's development - which is why the base was changed.

## Firmware

The firmware is not in this repository and not in the image: the installer copies it from the owner's own
device. Two facts about it, measured on the device on 17.08.2026:

- With Radxa's `fix-sdio-firmware-path` the driver looks in `/lib/firmware/aic8800_fw/SDIO/aic8800D80` (before it
  was `aic8800_sdio/aic8800`). `installer/h713/layout.py` and `installer/h713-extract` put it there; if the path
  differs, the driver finds the chip and then no firmware.
- The board needs the `_h_` firmware: the chip reports `is_chip_id_h` from register `0x40500000` (bits 22 and 23
  of the word read both set), and only the driver of 2026 has a D80 list for it and loads
  `fmacfw_8800d80_h_u02.bin`. That is why the driver of 2026 and the firmware of 2024 do not go together, although
  their message interface is the same.

## After a version bump

Apply the series again with a three-way merge. A vendor patch that no longer applies goes into
`AIC8800_VENDOR_PATCH_SKIP` only after deciding that it may be skipped.
