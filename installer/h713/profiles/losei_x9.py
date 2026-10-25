"""LOSEI X9 -- board profile. Data only, no vendor bytes: numbers, hashes and strings.

Shape: installer/h713/profiles/SCHEMA.md. One source, reported by the owner, nothing of it
measured on this host. Source tags used in the comments below:
  I3 = issue #3 (owner GitHub cosmonet-fr, 25.10.2026): pin map, the `h713-install identify` row
       and the `u-boot-h713-probe.bin` log over FEL (GPT, boot0 at LBA 16)
  R  = REPORT.txt attached there -- h713-extract 0.4, run 2026-10-25 17:08 on his own partition
       backups (eMMC head 36 MiB, bootloader.img, super.img)
  P  = panel.env attached there -- the panel row h713-extract derived from his panel_config.ini
Both attachments live outside the repository, in arbeit/losei-x9-20261025/anhaenge/.

What this board is NOT: a verified one. Nothing of ours has run on it beyond a read-only probe
(his log: SPL trained the DRAM at the default clock, U-Boot came up, coprocessor in reset, panel
dark). "partial" because the description itself has holes -- see the three `None`s below and
boards/losei-x9/README.md section "What we do not know".
"""

PROFILE = {
    "id": "losei_x9",
    "name": "LOSEI X9",
    "description": "LOSEI X9 -- Allwinner H713, PCB MTL-H713-Z10-V1.0, reported in issue #3 "
                   "(25.10.2026); no stock image and no dump on this host",
    # His own read-only probe is not a run of our firmware, and values are missing (I3, R).
    "status": "partial",
    "verified_by": None,
    "soc": "H713 (sun50iw12)",               # R dtb root: compatible 'allwinner,tv303 arm,sun50iw12p1'
    "stock": {
        "android": "10",                     # R vendor build.prop fingerprint ":10/" (ADT-3 build 6245789)
        # R has no sunxi_version: his input is a partition backup, not a stock image, and the
        # identify row prints "sunxi_version -". Not in strong_features for the same reason.
        "sunxi_version": None,
        "build_fingerprint": "ADT-3/adt3/adt3:10/QTT1.200116.002.B6/6245789:user/release-keys",
        # I3 identify row, cut before " Allwinner Technology" resp. " Time:" (profile convention).
        "uboot_version": "U-Boot 2018.05 (Sep 21 2024 - 06:22:17 +0000)",
        "arisc_version": "TV-303  ARISC  00.00.00.09 Date:Sep 21 2024",
        # R dump LBA 24576: sunxi-package, 5 items. monitor (66060 B) and optee (275328 B) are
        # left out although their size is known: R prints their sha256 as a 16-hex prefix only
        # ('017d32e1f283686f...', '58d8a6a5c6c1ad14...'), and a package item needs a full digest.
        # They come with the owner's next report (TODO 4.13).
        "package_items": {
            "u-boot":  (638976, "f839d8050f6519abc36426070caf12e1ad3422d2bef8c2edc2d6c4b0267dbd1a"),
            "scp":     (176132, "3cf4065e77001953e9a0273d488d66cdf0581003d090e00272c40eede29c682b"),
            "dtb":     ( 74240, "335f00df8d564b30db7f11f3d2eefd842e8939053430e43e0d8c604fe88ba7c5"),
        },
        "vendor_size": 125927424,            # R LP metadata: vendor 125927424 B
        # As for hy300_t08: build_fingerprint is not strong, every ADT-3 image carries the same one,
        # and mips_database_sha256 is not either -- his database.TSE is byte-identical with the
        # HY300 T08's (6d43b85a...), so it does not tell the two boards apart. sunxi_version is
        # unknown here, so what is left are the three digests and the two version strings.
        "strong_features": ("scp_sha256", "uboot_sha256", "dtb_sha256", "uboot_version",
                            "arisc_version"),
    },
    # I3: the 24 u32 of the vendor boot0 at LBA 16 + 0x38, read off his device by h713_probe and
    # printed a second time by identify from his dump -- both agree. A device read, not an image:
    # para2 = 0 is what his eMMC carries (the HY310 runs 0x04000000 there).
    # Word for word the HY300 T08's block except clk (744 vs 640), tpr11 and tpr12.
    "dram": {
        "clk": 744, "type": 3, "zq": 0x7b7bfb, "odt_en": 1,
        "para1": 0x10f4, "para2": 0,
        "mr0": 0x1c70, "mr1": 0x40, "mr2": 0x18, "mr3": 0,
        "tpr0": 0x4a2195, "tpr1": 0x2423190, "tpr2": 0x8b061, "tpr3": 0xb4787896,
        "tpr4": 0, "tpr5": 0x48484848, "tpr6": 0x48, "tpr7": 0x1620121e,
        "tpr8": 0, "tpr9": 0, "tpr10": 0, "tpr11": 0x44340000,
        "tpr12": 0x6666, "tpr13": 0x34010100,
        "source": "eMMC LBA 16, vendor boot0 header + 0x38, read on the device by h713_probe "
                  "over FEL (issue #3, 25.10.2026); identify prints the same block from his dump",
    },
    "layout": {                              # I3 identify "partitions:" and the GPT the probe printed
        "disk_sectors": 15269888,            # GPT last_usable 15269854 + 34
        "first_usable": 73728,
        "entries": 21,
        # name, start LBA, sectors, downloadfile. No A/B pair anywhere, a single Reserve0, and a
        # recovery, cache and swap no other board of ours has. The download names are unknown:
        # his input is a device, so there is no sys_partition.fex to read them from.
        "partitions": [
            ("factorydata",      73728,   16384, None),
            ("bootloader",       90112,   65536, None),
            ("env",             155648,     512, None),
            ("boot",            156160,  131072, None),
            ("vendor_boot",     287232,   65536, None),
            ("super",           352768, 4194304, None),
            ("misc",           4547072,   32768, None),
            ("recovery",       4579840,  131072, None),
            ("cache",          4710912, 3145728, None),
            ("vbmeta",         7856640,     256, None),
            ("vbmeta_system",  7856896,     128, None),
            ("vbmeta_vendor",  7857024,     128, None),
            ("frp",            7857152,    1024, None),
            ("empty",          7858176,   30720, None),
            ("metadata",       7888896,   32768, None),
            ("private",        7921664,   32768, None),
            ("dtbo",           7954432,    4096, None),
            ("media_data",     7958528,   32768, None),
            ("Reserve0",       7991296,   32768, None),
            ("swap",           8024064, 1048576, None),
            ("UDISK",          9072640, 6197215, None),
        ],
        # R: eGON.BT0 at LBA 16 and 256, a sunxi-package at LBA 24576 and 32800 (both identical).
        # The file names are the conventional download names; what was measured are the headers.
        "raw": [("boot0_sdcard.fex", 16), ("boot0_sdcard.fex", 256),
                ("boot_package.fex", 24576), ("boot_package.fex", 32800)],
        # no sys_partition.fex to compare the GPT against, so nothing can disagree yet
        "sunxi_gpt_disagrees": None,
    },
    # secure-storage sits where it sits on every H713; private and Reserve0 are found by name in
    # the device's own GPT (the LBA is this board's expectation, I3).
    "unique_regions": [
        ("secure-storage", 12288, 2048, "HDCP keys, WLAN/BT MAC addresses, serial number"),
        ("private", "by-name", 32768, "Android secure storage partition; I3 private@7921664"),
        ("Reserve0", "by-name", 32768, "panel_config.ini and calibration; I3 Reserve0@7991296"),
    ],
    # A single "bootloader" partition on this board, hence the glob: no stock image supplies it,
    # and media_data is /oem, where the vendor looks for TSE overrides first.
    "preserve_on_restore": ("private", "Reserve0*", "bootloader*", "media_data"),
    "mips": {
        # R, measured on his backup: the bootloader FAT16 has no mips/ directory (its root holds
        # LogoRegData.bin, bootlogo.bmp, the fonts, magic.bin, wavefile), and all 20 files our
        # chain wants sit in vendor:/etc/display/mips/ -- as on the two other ADT-3 boards.
        "sources": ("vendor:/etc/display/mips",),
        "revisions": [
            # R: a fifth display.bin revision, 16 B smaller than the HY300 T08's 0x131b20, and the
            # HDCP wait site was found by the search (h713.hdcpsite, one hit with context at file
            # offset 0x3d140), not pinned. No row of h713_mips_fw_revs[] declares the size 0x131b10,
            # so our U-Boot refuses to load it outside probe mode (TODO 4.11).
            {"size": 1252112, "sha256": "49f698af43ce714a70e04390a9a81015faa5b228dbffc2d73cc384722f0b307b",
             "name": "ADT-3 2024-09", "hdcp_wait_va": 0x4b13d140},
        ],
    },
    # P: derived from vendor:/etc/tvconfig/panel_config/panel_config.ini, 10 checks OK, 1 WARN.
    # ProjectID 0x33 is new -- h713_disp_panels[] knows 0x30 and 0x34 only (TODO 4.10). The WARN
    # is C8: this panel dims on PWM channel 0 at 480 Hz, while our dimmer is pinned to PWM2/PB4 --
    # and PB4 is this board's fan line (I3), so nothing of ours may drive it here.
    "panel": {
        "declared_project_id": 0x33,         # ProjectID 51
        "width": 1280, "height": 720, "dual_port": False,
        "htotal": 1600, "vtotal": 755, "dclk_hz": 72480000,
        "hsync": 100, "vsync": 10, "hbp": 100, "vbp": 10,
        "hsync_pol": 0, "vsync_pol": 0,
        "pwm_channel": 0, "pwm_freq": 480,
        "source": "vendor:/etc/tvconfig/panel_config/panel_config.ini (panel.env of issue #3)",
    },
    # R "Files:" -- what his h713-extract run produced, every digest as that report prints it.
    # This is the yardstick for the next X9 dump, nothing more: one device, one firmware.
    "reference": {
        "lib/firmware/h713-arisc.bin": (176132, "3cf4065e77001953e9a0273d488d66cdf0581003d090e00272c40eede29c682b"),
        "lib/firmware/hy310-edid.bin": (512, "70d10294e3f1f1ba3aceaf684c90d2dcdcafc9ba4ed265956520bdf4adfb60ef"),
        "lib/firmware/h713/msp-patch.bin": (2896, "8e31db199e0078d142f622436ff0b7249b333dbb6df8ec3fbabc0d8fea6ea0c5"),
        "pq/panel_config.ini": (2482, "4486f85a95fde91a82cdda30406211b2406f6102ec88de32f2bcc514f8773be1"),
        "boot/mips/display.bin": (1252112, "49f698af43ce714a70e04390a9a81015faa5b228dbffc2d73cc384722f0b307b"),
        "boot/mips/display_cfg.xml": (4758, "a271b11d6105c983c7602d8ad21608c0ba9186b996d5e7ec98aafa7eee0b5b07"),
        "boot/mips/LogoRegData.bin": (13620, "d5b4000c8640f8a026cf4310d033406594ce9d47148d58f664402c591a4aba68"),
        "boot/mips/database.TSE": (251184, "6d43b85a5880d34df0428f234c0c713ac1ca7ec28e551554137d967f60c380e4"),
        "boot/mips/pq_custom.TSE": (15088, "1c264bb5b275604c37b99eb82e116aaedb4b6a84368c504853c984252c6fb485"),
        "boot/mips/projecttable.TSE": (1576, "d36ff9d17a16ae0a01db3e8e619c880163af540fd2459bef6414c745b50c35eb"),
        "boot/mips/ProjectID_0x0001.TSE": (19992, "0d7dfa3546ffc0d18f26d126f5bff2dc4b5b513ae70c18c32f1f4f994994f061"),
        "boot/mips/ProjectID_0x0012.TSE": (48952, "8077c4465ff09d72817a36b32c00f4cec36b5d54f9bb6073b64480b039a4f39d"),
        "boot/mips/ProjectID_0x0013.TSE": (47880, "56ab808d776c063101d8e93be277a7802f07a4acc03fb99b678d78aba5e6431b"),
        "boot/mips/ProjectID_0x0014.TSE": (47880, "f87c1d990bcd4543c1d8a11254316d18390ef39d3412d650a53e542b53da2d91"),
        "boot/mips/ProjectID_0x0015.TSE": (47880, "be1622babeada99b8ccf79d361b4565752d30ede8cf0368e062b2ae8acfe3ba9"),
        "boot/mips/ProjectID_0x0016.TSE": (47880, "9acba93639323d35d1b9360ac6758b2b7b4619ae04c45fc4fa0ccd04decee55a"),
        "boot/mips/ProjectID_0x0020.TSE": (19992, "e8090e174ecb5d150248f78e00033482f3778d6100a7701b8f0364dfc8dec342"),
        "boot/mips/ProjectID_0x0030.TSE": (19992, "1b8478fb6886ae8b3953733e385fec0917970958c472c1d13dd8ebda3842c340"),
        "boot/mips/ProjectID_0x0031.TSE": (19992, "a152f6da9d883a2a83c55f12f1778c0f92040900128c8f4a95119e20fa13d8d4"),
        "boot/mips/ProjectID_0x0032.TSE": (19992, "3129551510a9bb126aa239fe65d9e086f6569de843ae400bfa192bf3acece7e4"),
        # the board's own id, 0x33: present as a descriptor, and identical with the HY310's copy
        "boot/mips/ProjectID_0x0033.TSE": (19992, "32bbb023bd37534b5a0622e23c78f47f7a5d3e2060e77d72106b2d517720185c"),
        "boot/mips/ProjectID_0x0034.TSE": (19992, "222d4b0e759ad0936a33a8d488613e5d6965148ff5adf7c074f41bfa46d56084"),
        "boot/mips/ProjectID_0x0035.TSE": (19992, "0a93397d0a1bf741fc06ab37e1de8680905e4c7cd1e72cb095bd9fadba8e89e2"),
        # 0x51: a descriptor no other board of ours carries
        "boot/mips/ProjectID_0x0051.TSE": (20192, "fd898d737aad34d17d3225edd40b69ed3787d6f11622344b9080ae22e6d3df5c"),
        "lib/firmware/aic8800_fw/SDIO/aic8800D80/aic_userconfig_8800d80.txt":
            (2685, "21c8241e15bd1f06c06fc6547c924a644db5e029d00fd9ea6c01172d3c143f77"),
        "lib/firmware/aic8800_fw/SDIO/aic8800D80/fmacfw_8800d80.bin":
            (261352, "a0f372c19b47e4a3f4703240d9d5c3780a42f27497f3b81d3c719058052d2fba"),
        "lib/firmware/aic8800_fw/SDIO/aic8800D80/fmacfw_8800d80_h_u02.bin":
            (331884, "42c3b25ed3c919be22f8515f335d9eff17230fbe6223f9b626691732ce12727f"),
        "lib/firmware/aic8800_fw/SDIO/aic8800D80/fmacfw_8800d80_u02.bin":
            (335648, "f6ce59e0f2f6a3ffebd9751725fa0d22e3dea2bd423ac46e4d3232b3a7c591c9"),
        "lib/firmware/aic8800_fw/SDIO/aic8800D80/fmacfwbt_8800d80_u02.bin":
            (340636, "9d096bbd651da75c6346137ed6cf98553160f57f5ae468d13297aa8e1ba0d33e"),
        "lib/firmware/aic8800_fw/SDIO/aic8800D80/fw_adid_8800d80_u02.bin":
            (1708, "a526cbd02fcdc495f049f3ad6b5933cb08cd984b16790c716a060d582fee1a56"),
        "lib/firmware/aic8800_fw/SDIO/aic8800D80/fw_patch_8800d80_u02.bin":
            (22736, "4fd002603cc490f83c8c3b82aefcc3dda2cc9607dbb347b3794d7585cb99d82f"),
        "lib/firmware/aic8800_fw/SDIO/aic8800D80/fw_patch_table_8800d80_u02.bin":
            (23264, "6397273cb3f7c46a531f4e753ede452dfea62cdf32bf942a678f8ecbc40f1e71"),
        "lib/firmware/aic8800_fw/SDIO/aic8800D80/lmacfw_rf_8800d80.bin":
            (302105, "3f35b01e9364ea8ecad4005a470a5d737d2321c57fe4c84de97952280eb9f247"),
        "lib/firmware/aic8800_fw/SDIO/aic8800D80/lmacfw_rf_8800d80_u02.bin":
            (240662, "7668dffaab5de8f8589cd589cd11869c64559d4abde7f5be3c04487eeeaf32f3"),
    },
    "expected": {
        # The same facts as "stock", in the shape identify compares a device against.
        "package_items": {"u-boot": 638976, "scp": 176132, "dtb": 74240},
        "package_item_sha256": {
            "u-boot": "f839d8050f6519abc36426070caf12e1ad3422d2bef8c2edc2d6c4b0267dbd1a",
            "scp": "3cf4065e77001953e9a0273d488d66cdf0581003d090e00272c40eede29c682b",
            "dtb": "335f00df8d564b30db7f11f3d2eefd842e8939053430e43e0d8c604fe88ba7c5",
        },
        "uboot_version": "U-Boot 2018.05 (Sep 21 2024 - 06:22:17 +0000)",
        "dtb_compatible": "allwinner,tv303",  # R dtb root, first entry
        "arisc_version": "TV-303  ARISC  00.00.00.09 Date:Sep 21 2024",
        "vendor_size": 125927424,
        "libmspsound_sha256": "3fb7f5377efb936e316a40b4f7243eb68f9ce2ddb02b2b614c0c3e73bc708f02",
        "build_fingerprint": "ADT-3/adt3/adt3:10/QTT1.200116.002.B6/6245789:user/release-keys",
        "sunxi_version": None,               # not in his input, see "stock" above
        "mips_database_sha256": "6d43b85a5880d34df0428f234c0c713ac1ca7ec28e551554137d967f60c380e4",
    },
    "board_dt": None,                        # no device tree of ours has booted on this board
    "uboot_board": None,                     # no U-Boot base defconfig of ours for this board
}
