# HY300 (2023 firmware)

The MagCubic HY300 of [issue #8](https://github.com/well0nez/allwinner-h713-linux/issues/8): the classic HY300 cylinder on a
rotating stand, a 720p panel, and the oldest ADT-3 firmware reported so far. Nobody working on this repository has one in
hand; nothing of ours has run on it. Its owner cannot open the unit, so the silkscreen is unknown and the board is named
after its firmware.

| | |
|---|---|
| Status | **profile-only** - a complete description from the owner's reads, no device run; a TEST image can be built |
| Verified by | nobody |
| Profile | `installer/h713/profiles/hy300_2023.py` |
| Image | TEST only: `release/build-all.sh --board hy300-2023 --test-image --version vX.Y`; nothing is published |
| Kernel DTB | `sun50i-h713-hy300-2023` (kernel 0350): the HY300 Pro's tree with the focus motor off; built with dtc, never booted |
| U-Boot base | `hy300_2023_defconfig` (fork `h713-hy310`, mirror `uboot-h713/0112`, 05.11.2026): `hy300_pro_defconfig` with the HY350 family's DRAM block at 792 MHz, this tree and its identification string |
| DRAM | DDR3 (type 3), 792 MHz; the HY350 profile's block word for word (`tpr0..tpr2` 0x4a2195 / 0x2423190 / 0x8b061, `tpr11/12` 0x44440000 / 0x5555) |
| Panel | 1280×720, declared project id `0x34`; timings not posted |
| Display firmware | a revision of its own: 1 251 856 B, `1e3e518f...`, HDCP wait site `0x4b13cf00` (row "ADT-3 2023-06" in `h713_mips_fw_revs[]`, the four firmware addresses at zero) |
| Wi-Fi | **AIC8801** (SDIO `5449:0145`), read by the owner; the vendor partition also ships an `aic8800dc/` set and no D80 set |
| Stock | ADT-3 build 6245789, U-Boot `2018.05-00005-g6d2f0a5-dirty` (2023-06-25), ARISC 2023-06-25, Android 11 userland `UI_Veng.projector.20230625` |

## Where the facts come from

- **`h713-install identify`** on the device (02.11.2026): the strong features (three package hashes, U-Boot and ARISC
  strings), the DRAM block, project id, 25 partitions on 15 269 888 sectors, `database.TSE` `921c4653...`, vendor 110 755 840 B.
- **`h713-extract` over his partition files** (04.11.2026): the `display.bin` revision with its wait site (by search), 18
  display files in `vendor:/etc/display/mips/` (no `0x0035`), `LogoRegData.bin` 13 572 B, `libmspsound.so` `c6e9cffc...`,
  `panel_config.ini` present (2513 B), `HDMI_EDID_14.bin` block 1 with a wrong checksum (our chain serves its own EDID).
- **The raw eMMC head**, LBA 0..73727, read by the owner (05.11.2026): boot0 at LBA 16 and 256, the two `sunxi-package`
  copies at 24576 and 32800 identical, checksum ok, items u-boot 638 976 / monitor 65 996 / scp 176 132 / optee 267 136 /
  dtb 69 632 B, ARISC `50e8725e...`. Not attached (secure storage); the `monitor` and `optee` hashes are not read yet.
- **The case** (owner): power button, HDMI, 3.5 mm headphone jack, USB; manual focus ring, no motor; no camera; a remote.
- **DRAM in practice**: our HY300 Pro U-Boot from `hy300-pro-test12` (SPL at 636 MHz with the HY300 Pro's block) trained
  his DRAM and exposed the eMMC over UMS for a full partition dump with consistent hashes (04.11.2026). His measurement.
- **Assumed, not read**: the partition table in the profile is the HY300 T08's (the same family: 25 entries, `super`
  6 291 456 sectors, a single `Reserve0`); the owner's GPT has not been posted row by row.

## What we do not know

- the board itself: silkscreen, the stock device tree (`a84bfbd5...`, 69 632 B, not posted), whether its pins are the
  HY300 Pro's - the tree assumes so, as the HY300 Pro's own tree once assumed the HY310's
- the display firmware's elog addresses and AFBD handoff words: a revision nobody has run; the tree keeps the HY300 Pro's
  (a wrong elog pair only empties the elog dump; wrong handoff words make the AFBD driver refuse and the wall black after
  the logo - that is the known failure signature)
- the panel timings, the lamp's PWM words (the HY300 Pro's are inherited), the HDMI socket's port
- the eMMC's real size (the profile carries the family's 15 269 888)

## What it would take to move this board forward

A TEST image over FEL: the owner has done step 0 already, with another board's U-Boot. With this board's own U-Boot the
same step (`sunxi-fel uboot`, a USB drive appears) proves the DRAM block; the install needs a full dump as the way back,
which his partition backup is not (the boot chain lies before the first partition). Without a serial console the
evidence is the wall and, if the AIC8801 comes up, ssh.
