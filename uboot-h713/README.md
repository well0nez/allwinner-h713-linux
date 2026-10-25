# U-Boot changes for HY260_QZ713_V3.1

**The patch files here are generated, not maintained** (since 12.09.2026, P3):
`git format-patch --no-signature 8fe568cdfc46..<head>` in the submodule checkout
`mainline/external/u-boot` (branch `h713-hy310`, base is cstenger's `h713`),
last regenerated on 25.10.2026 at the head `c97e5c6bb78d` (105 patches; on the fork's `h713-hy310` since 26.10.2026). Verified the
way a mirror should be: applying all 105 from the base produces a tree with the same
hash as the head (`1d0b87cde693`; before: 102 patches, head `daa35622b0bf`, tree `ca817b83e490`; before that: 101 patches, head `61ea018712c8`, tree `595b6941482e`). `0095` is the HDCP 1.4 key path, `0096` stages scp.bin (crust) in DRAM for BL31,
`0097` names the gate word of a standby that did not finish (`doku/179`), `0098` - `0100` are the HDCP
hardening (no `h713_hdcp14_wait`, the record staged where EL3 says and one write per boot, the guard
through the watchdog driver; measured over FEL, `doku/180`). `0101` hands a cold start's wait to crust, when crust can power off (`doku/191`). `0102` lets the remote's power key (both stock remotes, NEC) start the board from the gate, where no crust runs (22.10.2026, tested over FEL on the HY300PRO-G-EU). `0103` (local branch `versuch/l018`, 25.10.2026) is the L018's `CONFIG_H713_BOARD_L018` and `l018_defconfig`: the gate holds lamp and fan off (PB5 low, PB4 high), the board comes up at the stock std mode (lamp PWM2 50 %, fan PWM0 70 %), and the panel sequence sets PH9 low before the reset pulse and leaves PF6 alone - measured on the unit (dark gate, picture the right way round); without the option the HY310's code and data are byte-identical. `0104` (same branch) holds lamp and fan off from the SPL on, so the lamp no longer lights for a second before U-Boot and no white picture comes before the logo; `0105` lights the power key red in the gate and blue once the board starts (PL0 red, PL1 blue, both active low) - both seen on the unit by its owner (25.10.2026). `SERIES.txt` names base,
head and count, and is the only thing that says which fork commit this mirror stands
on. Whoever wants to change something changes the fork and has the mirror generated
again. This page explains *why* the changes look the way they do - the original text
of 31.08. is below.

All four findings are verified on hardware and backed by the vendor U-Boot
(`re/vendor/HY310/extracted/u-boot.fex`, Thumb-2, base `0x4a000000`).

## What is in it

**`drivers/clk/sunxi/clk_h713.c`** - CCU tables of its own instead of reusing the
D1's. On the H713 the USB registers lie **8 bytes** apart, on the D1 only 4:
port 1 is `0xa78`, not `0xa74`, and there is a third port at `0xa80`. With the D1
values OHCI1 never gets its clock and the first register access hangs the board.
Backed by the vendor binary at `0x4a045e12`: `cmp r0, #1` followed by
`ldr r2, =0x02001a78`. Agrees with the H713 CCU driver from the well0nez kernel
(patch 0001).

**`drivers/phy/allwinner/phy-sun4i-usb.c`** - an H713 entry, which U-Boot did not
have at all:

- `pmu_enable_bit0`, ported from well0nez' kernel patch 0005. Without BIT(0) at the
  PMU base the PHY stays off.
- `hci_phy_ctl_clear = PHY_CTL_SIDDQ`. The HCI PHYs start with SIDDQ (bit 3 at
  PMU+0x10) set, that is in power-down. The vendor clears it with `bic r3, r3, #8`
  at `0x4a045ee8`. The kernel may leave that out **because the vendor U-Boot ran
  before it** - see `usb.md` in the well0nez tree: "the kernel doesn't re-init from
  scratch". Where U-Boot is itself the first stage, it has to do the job.
- `num_phys = 2`, not 3: U-Boot's H713 CCU only reaches port 1.

**`sun50i-h713-hy200-qz713df-a1.dts`** - `r_pio` added at `0x07022000` (the PL/PM
banks were missing entirely, and without them every `gpio_request` on PL fails with
`-ENOENT`), plus `ehci0`/`ohci0` and `ehci1`/`ohci1`.

**`board/sunxi/board.c`** - PB5 and PL3 are now set in `board_late_init` instead of
`board_init`, and **by pin name instead of by legacy number**. In `board_init` the
GPIO uclass is not up yet and `gpio_request` fails silently. And the linear
numbering (32 pins from PA=0) does not match the banks registered from the DT:
`SUNXI_GPB(5)` hit a different pin (call successful, fan stayed off) and
`SUNXI_GPL(3)` did not resolve at all. The return values are checked and reported now.

## Defconfigs

One base defconfig per board plus one role fragment - see
[`docs/uboot/README.md`](../docs/uboot/README.md), which is the page that describes
them. The old per-role names (`hy310_qz713_v3_1_defconfig`, `hy310_host_defconfig`,
`hy310_felmmc_defconfig`) are gone since stage 4.

## What hangs where on this board

| Port | | |
|---|---|---|
| 0 | external USB-A socket | OTG. FEL and `ums` run over it. As a host only with the host role |
| 1 | internal | Realtek `0bda:5803` "Generic HD camera", 480 Mb/s, connector `CAM`. Powered over **PL3**, in the stock GPIO map as `cam-usb-power-gpio` - the name is meant literally |
| 2 | | registered by the kernel, nothing attached |

`PB5` switches fan **and** lamp together. Never set it LOW.

## State on 2026-08-31

Flashed with the host defconfig of the time, the arm64 kernel 6.18.38 boots through:
four cores at EL2, all six USB controllers, a high-speed hub with four ports on
bus 1, eMMC at HS400 with all 26 partitions. The panic at the end is expected -
`root=/dev/mmcblk0p26` is `UDISK` and empty.

## Playing them back

The series lies next to this file as 105 `git format-patch` files on `8fe568cdfc4`.
How many of them are upstream as PR #1, and what the rest is, is stated once in
[`docs/uboot/README.md`](../docs/uboot/README.md).

```
cd mainline/external/u-boot
git am ../../../uboot-h713/00*.patch
```

The working tree is on branch `h713-hy310` (22.10.2026: head `daa35622b0bf`, 102 commits
on `8fe568c`); the patches are the mirror, not the source. A board still in test can
have a branch of its own next to it (`hy300-pro-ab`), which this mirror does not carry.

`0017`-`0021` are the gate, the SMM heap, the elog option, the GP5 messages and the
default environment (`doku/30` §15, `doku/105` §1.2). **`0022`** is the only generic
patch of the series: `env/mmc.c` passed a `CONFIG_ENV_OFFSET` of 2 GiB or more through
an `int`, so the environment on the HY310 ended up at `0x65d80000` instead of
`0x93d80000` (`doku/30` §16). A candidate for a PR to cstenger/upstream.
