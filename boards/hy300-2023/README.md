# HY300 (2023 firmware)

The MagCubic HY300 in the classic cylinder case on a rotating stand, a 720p panel, with a 2023 ADT-3 firmware: two units,
two boot packages, one board. Variant `fw202306` is the unit of [issue #8](https://github.com/well0nez/allwinner-h713-linux/issues/8)
(the oldest ADT-3 firmware reported so far), variant `fw202312` the unit of
[issue #11](https://github.com/well0nez/allwinner-h713-linux/issues/11) (a boot package of 2023-12 and the LOSEI X9's
display firmware). Nobody working on this repository has one in hand; nothing of ours has run on either. Neither owner can
open the unit, so the silkscreen is unknown and the board is named after its firmware.

| | |
|---|---|
| Status | **profile-only** - a complete description from the owner's reads, no device run; a TEST image can be built |
| Verified by | nobody |
| Profile | `installer/h713/profiles/hy300_2023.py`, two variants: `fw202306` (the issue #8 unit), `fw202312` (the issue #11 unit) |
| Image | TEST only, per variant: `release/build-all.sh --board hy300-2023 --variant fw202306` (or `fw202312`) `--test-image --version vX.Y`; published as pre-releases for their owners (`hy300-2023-test1`, 05.11.2026, built before the variants under the name `hy300_2023`, for the issue #8 unit with the installer of its tag) |
| Kernel DTB | `sun50i-h713-hy300-2023` (kernel 0350): the HY300 Pro's tree with the focus motor off; built with dtc, never booted |
| U-Boot base | `hy300_2023_defconfig` (fork `h713-hy310`, mirror `uboot-h713/0112`, 05.11.2026): `hy300_pro_defconfig` with the HY350 family's DRAM block at 792 MHz, this tree and its identification string |
| DRAM | DDR3 (type 3), 792 MHz; the HY350 profile's block word for word (`tpr0..tpr2` 0x4a2195 / 0x2423190 / 0x8b061, `tpr11/12` 0x44440000 / 0x5555) |
| Panel | 1280×720, declared project id `0x34`; `panel_config.ini` has the same hash on both units (`7bffff88...`), its timings not posted |
| Display firmware | `fw202306`: a revision of its own, 1 251 856 B, `1e3e518f...`, HDCP wait site `0x4b13cf00` (row "ADT-3 2023-06" in `h713_mips_fw_revs[]`, the four firmware addresses at zero); `fw202312`: the LOSEI X9's, 1 252 112 B, `49f698af...`, wait site `0x4b13d140` (row "ADT-3 2024-09" since 13.11.2026, addresses at zero) |
| Wi-Fi | **AIC8801** (SDIO `5449:0145`), read by both owners; the vendor partition ships its ten files in `/etc/firmware`, no D80 set (the issue #8 unit also an `aic8800dc/` set) |
| Stock | ADT-3 build 6245789. `fw202306`: U-Boot `2018.05-00005-g6d2f0a5-dirty` (2023-06-25), ARISC 2023-06-25, Android 11 userland `UI_Veng.projector.20230625`, `database.TSE` of its own, vendor 110 755 840 B. `fw202312`: U-Boot `2018.05-00017-g1e43c6c` (2023-12-08), ARISC 2023-12-27, Android 11 userland `UI_Veng_F.projector.20231227`, the T08 family's `database.TSE`, vendor 110 202 880 B, all 13 ProjectID files |

## Where the facts come from

The issue #8 unit (`fw202306`):

- **`h713-install identify`** on the device (02.11.2026): the strong features (three package hashes, U-Boot and ARISC
  strings), the DRAM block, project id, 25 partitions on 15 269 888 sectors, `database.TSE` `921c4653...`, vendor 110 755 840 B.
- **`h713-extract` over his partition files** (04.11.2026): the `display.bin` revision with its wait site (by search), 18
  display files in `vendor:/etc/display/mips/` (no `0x0035`), `LogoRegData.bin` 13 572 B, `libmspsound.so` `c6e9cffc...`,
  `panel_config.ini` present (2513 B), `HDMI_EDID_14.bin` block 1 with a wrong checksum (our chain serves its own EDID).
- **The raw eMMC head**, LBA 0..73727, read by the owner (05.11.2026): boot0 at LBA 16 and 256, the two `sunxi-package`
  copies at 24576 and 32800 identical, checksum ok, items u-boot 638 976 / monitor 65 996 / scp 176 132 / optee 267 136 /
  dtb 69 632 B, ARISC `50e8725e...`. Not attached (secure storage). `monitor` `2dc43c30...` and `optee` `c391dde3...` (owner, 06.11.2026, h713-extract over the head): the T08 unit's.
- **The case** (owner): power button, HDMI, 3.5 mm headphone jack, USB; manual focus ring, no motor; no camera; a remote.
- **DRAM in practice**: our HY300 Pro U-Boot from `hy300-pro-test12` (SPL at 636 MHz with the HY300 Pro's block) trained
  his DRAM and exposed the eMMC over UMS for a full partition dump with consistent hashes (04.11.2026). His measurement.
- **The partition table** (owner, 06.11.2026, his GPT row by row, both CRCs ok): the HY300 T08's to the sector (25 entries,
  `super` 6 291 456 sectors, a single `Reserve0`, `UDISK` 7095296+8174559). Until then it stood in the profile as an assumption.
- **Lesson** (10.11.2026): the `u-boot` and `dtb` hashes of the owner's first comment were mistyped, the profile carried them,
  and the installer refused his unit ("no board we know"). A hash typed into an issue is checked against a read.

The issue #11 unit (`fw202312`):

- **`h713-install identify` over FEL** with the v0.97-beta HY300PRO-G-EU installer U-Boot (11.11.2026): the strong
  features (U-Boot `00017-g1e43c6c`, ARISC 2023-12-27, `scp` `d818f98a...`, `u-boot` `96a07318...`, `dtb` `68011339...`),
  the 24 DRAM words (the issue #8 unit's, word for word), project id `0x34`, 25 partitions on 15 269 888 sectors with
  `Reserve0` and `private` at the table's LBAs, `database.TSE` `6d43b85a...` (the T08 family's), vendor 110 202 880 B.
  From stock Android over ADB: `ro.build.product` `h713-tuna_p3`, `UI_Veng_F.projector.20231227.113137`, 1024 MB, the
  AIC8801 on `mmc1` (`5449:0145`, `544a:0146`), `motor_control` loaded although the case has a manual ring.
- **`h713-extract` over his full dump** (11.11.2026, `REPORT.txt` in the issue): the package at LBA 24576 with every
  item's size and hash (u-boot 638 976, monitor 65 996 `2dc43c30...`, scp 176 132, optee 267 136 `c391dde3...`, dtb
  71 168), `display.bin` 1 252 112 B `49f698af...` = "ADT-3 2024-09" with the wait site `0x4b13d140` by search, 19 display
  files in `vendor:/etc/display/mips/` (all 13 ProjectID files), `libmspsound.so` `c6e9cffc...` (= the issue #8 unit's),
  `panel_config.ini` `7bffff88...` (= the issue #8 unit's), the ten AIC8801 files, GPT with both CRCs ok. Two warnings as
  on the issue #8 unit (`pq_picturemode.ini`, `pqcontrol_custom_setting.xml` missing) and one check error in
  `audio_config.ini` (volume curve value 21 out of range; the image keeps the HY310's curve).
- **The case** (owner): the classic cylinder on a rotating stand, manual focus ring, HDMI, USB, power button, a remote.
- **The way back**: he holds a full dump (`dump --full`, "the dump agrees with the device").

## What we do not know

- the board itself: silkscreen, the stock device tree (`a84bfbd5...`, 69 632 B, not posted), whether its pins are the
  HY300 Pro's - the tree assumes so, as the HY300 Pro's own tree once assumed the HY310's
- the display firmware's elog addresses and AFBD handoff words: a revision nobody has run; the tree keeps the HY300 Pro's
  (a wrong elog pair only empties the elog dump; wrong handoff words make the AFBD driver refuse and the wall black after
  the logo - that is the known failure signature)
- the panel timings, the lamp's PWM words (the HY300 Pro's are inherited), the HDMI socket's port
- the issue #8 unit's eMMC size beyond `identify`'s 15 269 888 (the issue #11 unit's GPT was read with both CRCs ok)

## What it would take to move this board forward

A TEST image over FEL, per variant: both owners have done step 0 already, with another board's U-Boot. With this board's
own U-Boot the same step (`sunxi-fel uboot`, a USB drive appears) proves the DRAM block; the install needs a full dump as
the way back (the issue #11 owner has one; the issue #8 owner's partition backup is not one, the boot chain lies before
the first partition). Without a serial console the evidence is the wall and, if the AIC8801 comes up, ssh.
