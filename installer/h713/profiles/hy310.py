"""HY310 -- board profile. Data only, no vendor bytes: numbers, hashes and strings.

Shape: umbau/plan/profil-schema.md. Source tags used in the comments below:
  J  = umbau/fixtures/images/hy310-update.img.json (board facts of the stock image, package A1)
  X  = analyse/release/arbeit/r2-extract/h713-extract (line numbers are lines 52-275)
  I  = analyse/release/arbeit/r0-fel/hy310-install.py (installer constants, lines 42-105)
  A0 = umbau/work/A0/REPORT.md, sections 4 and 5 (what the vendor U-Boot loads, and from where)
  F  = umbau/fixtures/firmware-revisions.json (display.bin revisions + HDCP wait site, package A5)
"""

PROFILE = {
    "id": "hy310",
    "name": "HY310",                         # X:100
    "description": "HY310 -- Allwinner H713, reference design h713_tuna_p3, "
                   "stock build 2025-07-24 (Projector07241019)",   # X:101, translated
    "status": "verified",
    "verified_by": "well0nez, HY310, v0.5-beta, 13.09.2026",
    "soc": "H713 (sun50iw12)",               # J boot_package.dtb_model / dtb_compatible
    "stock": {
        "android": "11 (64-bit)",            # J vendor_build_prop fingerprint ":11/"; doku/120 section 1
        "sunxi_version": "2025-07-24 10:31:23",   # J sunxi_version
        "build_fingerprint": "Allwinner/h713_tuna_p3/h713-tuna_p3:11/RP1A.201005.006/Projector07241019:user/release-keys",
        # J boot_package.uboot_version / arisc_version, cut before " Allwinner Technology" resp. " Time:"
        # -- the extractor compares these two with startswith (X:194).
        "uboot_version": "U-Boot 2018.05-00024-gc128a2c-dirty (Jul 24 2025 - 10:17:21 +0800)",
        "arisc_version": "TV-303  ARISC  00.00.00.09 Date:Jul 24 2025",
        "package_items": {                   # J boot_package.items (= X:125 paket_items, same numbers)
            "u-boot":  ( 638976, "b8f40b86fe726145afbb50c067a3fda6b1ee7898340d48af5c5baf6d647f3a88"),
            "monitor": (  66060, "95596d11aa6d10c0f3c8ef2c0d6fa01446be320c412decc201a5b547d6475ed7"),
            "scp":     ( 176132, "d41731fa783dace3070264397064b28e2359a27b9e4708f3f7d40f1c3d876b7e"),
            "optee":   ( 275328, "9b3addd56be7b1fe8d5fbcaafed191239ed77bde5190f91e6725b7ffa8916b61"),
            "dtb":     (  73728, "001ed69993b2124a76b59e8cda60335af87c98149aadccf5737b9a10d249aff5"),
        },
        "vendor_size": 114372608,            # J super.partitions vendor_a (= X:136)
        # X:181 STARKE_MERKMALE -- the features that alone pin this board down.
        "strong_features": ("scp_sha256", "uboot_sha256", "dtb_sha256", "uboot_version",
                            "arisc_version", "build_fingerprint", "mips_database_sha256"),
    },
    "dram": {                                # J boot0.dram -- the 24 u32 at boot0_sdcard.fex+0x38
        "clk": 792, "type": 3, "zq": 0x7b7bfb, "odt_en": 1,
        "para1": 0x10f4, "para2": 0,
        "mr0": 0x1c70, "mr1": 0x40, "mr2": 0x18, "mr3": 0,
        "tpr0": 0x4a2195, "tpr1": 0x2423190, "tpr2": 0x8b061, "tpr3": 0xb4787896,
        "tpr4": 0, "tpr5": 0x48484848, "tpr6": 0x48, "tpr7": 0x1620121e,
        "tpr8": 0, "tpr9": 0, "tpr10": 0, "tpr11": 0x44340000,
        "tpr12": 0x6666, "tpr13": 0x34010100,
        "source": "boot0_sdcard.fex offset 0x38, update.img",
    },
    "layout": {                              # J sys_partition[] -- the stock table of update.img
        "disk_sectors": 15269888,            # I:45 SECTORS_EXPECTED (= J sunxi_gpt.header.last_usable + 34)
        "first_usable": 73728,               # J sunxi_gpt.header.first_usable
        "entries": 26,                       # len(J sys_partition) = J sunxi_gpt.header.entries
        # name, start LBA, sectors, downloadfile -- rows of J sys_partition in table order.
        "partitions": [
            ("bootloader_a",       73728,    65536, "boot-resource.fex"),
            ("bootloader_b",      139264,    65536, "boot-resource.fex"),
            ("env_a",             204800,      512, "env.fex"),
            ("env_b",             205312,      512, None),
            ("boot_a",            205824,   131072, "boot.fex"),
            ("boot_b",            336896,   131072, None),
            ("vendor_boot_a",     467968,    65536, "vendor_boot.fex"),
            ("vendor_boot_b",     533504,    65536, None),
            ("super",             599040,  4194304, "super.fex"),
            ("misc",             4793344,    32768, "misc.fex"),
            ("vbmeta_a",         4826112,      256, "vbmeta.fex"),
            ("vbmeta_b",         4826368,      256, None),
            ("vbmeta_system_a",  4826624,      128, "vbmeta_system.fex"),
            ("vbmeta_system_b",  4826752,      128, None),
            ("vbmeta_vendor_a",  4826880,      128, "vbmeta_vendor.fex"),
            ("vbmeta_vendor_b",  4827008,      128, None),
            ("frp",              4827136,     1024, None),
            ("empty",            4828160,    30720, None),
            ("metadata",         4858880,    32768, None),
            ("private",          4891648,    32768, None),
            ("dtbo_a",           4924416,     4096, "dtbo.fex"),
            ("dtbo_b",           4928512,     4096, None),
            ("media_data",       4932608,   557056, "mediadata.fex"),
            ("Reserve0_a",       5489664,    32768, "Reserve0.fex"),
            ("Reserve0_b",       5522432,    32768, None),
            ("UDISK",            5555200,        0, None),
        ],
        # I:1652 -- raw targets outside every partition: two eGON.BT0 copies, two sunxi-package copies.
        "raw": [("boot0_sdcard.fex", 16), ("boot0_sdcard.fex", 256),
                ("boot_package.fex", 24576), ("boot_package.fex", 32800)],
        # J layout_consistency[0]: sys_partition.fex says media_data is 557056 sectors, sunxi_gpt.fex says
        # 524288 -- everything behind it shifts by 32768 sectors. (sys_partition sectors, sunxi_gpt sectors).
        "sunxi_gpt_disagrees": {"media_data": (557056, 524288)},
    },
    # I:95 EINMALIG -- exists only on this device, no firmware image brings it back: always dumped,
    # never written (doku/109 section 2.3 and 9.1). Names, LBAs and sector counts verbatim, notes translated.
    "unique_regions": [
        ("secure-storage", 12288, 2048, "HDCP keys, WLAN/BT MAC addresses, serial number"),
        ("private", 4891648, 32768, "Android secure storage partition"),
        ("reserve0-a", 5489664, 32768, "Reserve0, slot A"),
        ("reserve0-b", 5522432, 32768, "Reserve0, slot B"),
    ],
    # A0 section 5: partitions no stock image supplies (or supplies wrongly). "Reserve0*" matches the
    # single Reserve0 as well as the Reserve0_a/_b pair; media_data is /oem, where the vendor looks for
    # TSE overrides before it looks in the bootloader partition.
    "preserve_on_restore": ("private", "Reserve0*", "bootloader_a", "bootloader_b", "media_data"),
    "mips": {
        # A0 section 4: this board's U-Boot loads mips/* from the bootloader partition the slot byte in
        # misc selects, and only then falls back to the vendor copy. J boot_resource_fat.has_mips_dir: true.
        "sources": ("bootloader_b", "bootloader_a", "vendor:/etc/display/mips"),
        "revisions": [                       # F, row "HY310 (QZ713 V3.1)"; size/sha256 = J mips_files
            {"size": 1256216, "sha256": "16c74a28187f342de657828fab65145b140ac9411c40cccc02eed25047472ee9",
             "name": "HY310 (QZ713 V3.1)", "hdcp_wait_va": 0x4b13d0a4},
        ],
    },
    "panel": {                               # J panel_config[*].reserve0 -- vendor copy identical
        "declared_project_id": 0x30,         # ProjectID 48
        "width": 1920, "height": 1080, "dual_port": True,
        "htotal": 2128, "vtotal": 1120, "dclk_hz": 143001600,
        "hsync": 44, "vsync": 5, "hbp": 88, "vbp": 20,
        "hsync_pol": 1, "vsync_pol": 1,
        "pwm_channel": 2, "pwm_freq": 25000,
        "source": "Reserve0.fex:panel_config.ini",
    },
    # X:102 GERAETE["hy310"]["referenz"] -- size and sha256 of every file the extractor must find
    # again; reference = the files of the running netboot root (plan 105 section 1.1). Values verbatim.
    "reference": {
        "lib/firmware/h713-arisc.bin": (176132, "d41731fa783dace3070264397064b28e2359a27b9e4708f3f7d40f1c3d876b7e"),
        "lib/firmware/hy310-edid.bin": (512, "70d10294e3f1f1ba3aceaf684c90d2dcdcafc9ba4ed265956520bdf4adfb60ef"),
        "lib/firmware/h713/msp-patch.bin": (2896, "8e31db199e0078d142f622436ff0b7249b333dbb6df8ec3fbabc0d8fea6ea0c5"),
        # X:74-94 _MIPS_REF -- mips/ of boot-resource.fex, measured 10.09.2026 from
        # update.img and from the eMMC dump of the dev device (LBA 73728 / 139264).
        "boot/mips/display.bin": (1256216, "16c74a28187f342de657828fab65145b140ac9411c40cccc02eed25047472ee9"),
        "boot/mips/display_cfg.xml": (4766, "9dce62c73bf5dea5bd6fecdfdee59f06ed3c3ad13fc4b5415842733f67bd4ca7"),
        "boot/mips/LogoRegData.bin": (15652, "0d00bcdd1fcfb185fe61525c9afa4bf3ec9982d605f137c593e8323766cfa4e3"),
        "boot/mips/database.TSE": (282464, "133bbec3e9a297aa0bd42b294de3ffe0d74235e8683659dfd2dfc1f2f855bdfb"),
        "boot/mips/pq_custom.TSE": (15016, "bf3d8110c38570e1ba28973e3cee2d3401a428510be0dab3b978474d7dd5a394"),
        "boot/mips/projecttable.TSE": (1384, "12f568f0f0d9e6269aa2e8bf918117e997264f47e642b1c3984acb04abd26e65"),
        "boot/mips/ProjectID_0x0001.TSE": (19992, "93258b453b8cf4d33ef49df24a9413aa2d6263367057d53dd7b907330b9aca85"),
        "boot/mips/ProjectID_0x0012.TSE": (48952, "8077c4465ff09d72817a36b32c00f4cec36b5d54f9bb6073b64480b039a4f39d"),
        "boot/mips/ProjectID_0x0013.TSE": (47880, "56ab808d776c063101d8e93be277a7802f07a4acc03fb99b678d78aba5e6431b"),
        "boot/mips/ProjectID_0x0014.TSE": (47880, "f87c1d990bcd4543c1d8a11254316d18390ef39d3412d650a53e542b53da2d91"),
        "boot/mips/ProjectID_0x0015.TSE": (47880, "be1622babeada99b8ccf79d361b4565752d30ede8cf0368e062b2ae8acfe3ba9"),
        "boot/mips/ProjectID_0x0016.TSE": (47880, "9acba93639323d35d1b9360ac6758b2b7b4619ae04c45fc4fa0ccd04decee55a"),
        "boot/mips/ProjectID_0x0020.TSE": (19992, "e8090e174ecb5d150248f78e00033482f3778d6100a7701b8f0364dfc8dec342"),
        "boot/mips/ProjectID_0x0030.TSE": (19992, "0b53eabb6be1ac215de97813379d1b44400f0319e74ba9c25648523022785a33"),
        "boot/mips/ProjectID_0x0031.TSE": (19992, "a152f6da9d883a2a83c55f12f1778c0f92040900128c8f4a95119e20fa13d8d4"),
        "boot/mips/ProjectID_0x0032.TSE": (19992, "3129551510a9bb126aa239fe65d9e086f6569de843ae400bfa192bf3acece7e4"),
        "boot/mips/ProjectID_0x0033.TSE": (19992, "32bbb023bd37534b5a0622e23c78f47f7a5d3e2060e77d72106b2d517720185c"),
        "boot/mips/ProjectID_0x0034.TSE": (17328, "8008ebefb9e6bc320372d89126dcb82532a8dbe28e97512916112843fabcfe1b"),
        "boot/mips/ProjectID_0x0035.TSE": (19992, "0a93397d0a1bf741fc06ab37e1de8680905e4c7cd1e72cb095bd9fadba8e89e2"),
        # X:107-122 AIC8800D80 SDIO WLAN firmware, checked on the device 12.09.2026.
        "lib/firmware/aic8800_fw/SDIO/aic8800D80/aic_userconfig_8800d80.txt": (2807, "11901372e3183c98b2fad24bc730878429428eaf7df514a575fbe44f7be41e4e"),
        "lib/firmware/aic8800_fw/SDIO/aic8800D80/fmacfw_8800d80.bin": (261352, "a0f372c19b47e4a3f4703240d9d5c3780a42f27497f3b81d3c719058052d2fba"),
        "lib/firmware/aic8800_fw/SDIO/aic8800D80/fmacfw_8800d80_h_u02.bin": (328912, "64f5705be73b18874dce85372c973079123ad7c7d1d82c3e99387fe0fa4d6291"),
        "lib/firmware/aic8800_fw/SDIO/aic8800D80/fmacfw_8800d80_u02.bin": (328720, "2ce84b41de107c43656f98899e86bc65c13afda15ca780c629aead20f3bc56ad"),
        "lib/firmware/aic8800_fw/SDIO/aic8800D80/fw_adid_8800d80.bin": (1680, "a8f054eab10d5a3ddc5644fb83bc170f270cc4aa294aaf6971804af263be0ff5"),
        "lib/firmware/aic8800_fw/SDIO/aic8800D80/fw_adid_8800d80_u02.bin": (1708, "a526cbd02fcdc495f049f3ad6b5933cb08cd984b16790c716a060d582fee1a56"),
        "lib/firmware/aic8800_fw/SDIO/aic8800D80/fw_patch_8800d80.bin": (8348, "aaf95c160f4e3a04886b3e2b9a003d201ef16962bb4d4a6fbf1ce483000b3619"),
        "lib/firmware/aic8800_fw/SDIO/aic8800D80/fw_patch_8800d80_u02.bin": (31592, "904b34e1bce27629223b62f6f38c7045a48423661de6c608ade2fff53f7a2a68"),
        "lib/firmware/aic8800_fw/SDIO/aic8800D80/fw_patch_8800d80_u02_ext0.bin": (10956, "f1f5048c094c74103b1a0e11cb6898fc18de9ee532cef90967d80745ee8573a1"),
        "lib/firmware/aic8800_fw/SDIO/aic8800D80/fw_patch_table_8800d80.bin": (648, "f8cd6d348285eb068030f90290554b56662b5f816a62c15651d2f44ad58cdfa7"),
        "lib/firmware/aic8800_fw/SDIO/aic8800D80/fw_patch_table_8800d80_u02.bin": (23472, "2c74a9c701f07ec0282896851964dd09c1d7f58592732b07ea9ce9d4e00b520a"),
        "lib/firmware/aic8800_fw/SDIO/aic8800D80/lmacfw_rf_8800d80.bin": (302105, "3f35b01e9364ea8ecad4005a470a5d737d2321c57fe4c84de97952280eb9f247"),
        "lib/firmware/aic8800_fw/SDIO/aic8800D80/lmacfw_rf_8800d80_u02.bin": (256810, "b3995616480e1f619904c0d9fb4ec2c4097a39902b64a8817a51ff932cca98b3"),
    },
    "expected": {
        # X:124 GERAETE["hy310"]["erwartung"], keys translated (paket_items -> package_items,
        # paket_item_sha256 -> package_item_sha256), values verbatim.
        "package_items": {"u-boot": 638976, "monitor": 66060, "scp": 176132, "optee": 275328, "dtb": 73728},
        "package_item_sha256": {
            "u-boot": "b8f40b86fe726145afbb50c067a3fda6b1ee7898340d48af5c5baf6d647f3a88",
            "monitor": "95596d11aa6d10c0f3c8ef2c0d6fa01446be320c412decc201a5b547d6475ed7",
            "scp": "d41731fa783dace3070264397064b28e2359a27b9e4708f3f7d40f1c3d876b7e",
            "optee": "9b3addd56be7b1fe8d5fbcaafed191239ed77bde5190f91e6725b7ffa8916b61",
            "dtb": "001ed69993b2124a76b59e8cda60335af87c98149aadccf5737b9a10d249aff5",
        },
        "uboot_version": "U-Boot 2018.05-00024-gc128a2c-dirty (Jul 24 2025 - 10:17:21 +0800)",
        "dtb_compatible": "allwinner,tv303",
        "arisc_version": "TV-303  ARISC  00.00.00.09 Date:Jul 24 2025",
        "vendor_size": 114372608,
        "libmspsound_sha256": "61f349440c08dd28ef1289f463a7934b3213b15518113ff1044f881bf237e8c4",
        "build_fingerprint": "Allwinner/h713_tuna_p3/h713-tuna_p3:11/RP1A.201005.006/Projector07241019:user/release-keys",
        "sunxi_version": "2025-07-24 10:31:23",
        "mips_database_sha256": "133bbec3e9a297aa0bd42b294de3ffe0d74235e8683659dfd2dfc1f2f855bdfb",
    },
    "board_dt": "sun50i-h713-hy310",        # boards/hy310/board.env KERNEL_DTB: the hy200 dts under the
                                             # board's own name (mainline/patches/kernel/0160)
    "uboot_board": "hy310",                  # boards/hy310/board.env UBOOT_BOARD: base hy310_defconfig,
                                             # a role fragment on top (docs/uboot/README.md)
}
