"""HY300PRO-G-EU -- board profile. Data only, no vendor bytes: numbers, hashes and strings.

Shape: installer/h713/profiles/SCHEMA.md. Source tags used in the comments below:
  D  = well0nez's own device, boxed "HY300PRO-G-EU", bought 2026-10; full eMMC dump of 2026-10-02
       (kept private) and h713-extract 0.4 over it
  B  = ADB getprop of the running stock system (read only)
  Q  = the sibling profiles hy310.py / l018.py (same reference design h713_tuna_p3)
"""

PROFILE = {
    "id": "hy300pro_g_eu",
    "name": "HY300PRO-G-EU",
    "description": "HY300PRO-G-EU -- Allwinner H713, reference design h713_tuna_p3, "
                   "stock build 2025-05-06 (projector.20250506.122807); not the board of issue #1 "
                   "(that one: Android 10, DRAM 636 MHz, 25 partitions)",
    # D: a dump of a real device lies on this host, but no image of ours has ever run on it.
    "status": "profile-only",
    "verified_by": None,
    "soc": "H713 (sun50iw12)",               # D: dtb_compatible "allwinner,tv303 arm,sun50iw12p1"
    "stock": {
        "android": "11 (ARMv7 userland, kernel 5.4.99)",   # B: ro.build.version.release, uname armv7l
        "sunxi_version": None,               # a device does not carry it
        "build_fingerprint": "Allwinner/h713_tuna_p3/h713-tuna_p3:11/RP1A.201005.006/projector05061226:user/release-keys",
        "uboot_version": "U-Boot 2018.05-00025-g4176897-dirty (May 06 2025 - 12:24:19 +0800)",
        "arisc_version": "TV-303  ARISC  00.00.00.09 Date:May  6 2025",
        "package_items": {                   # D: sunxi-package at LBA 24576 (32800 identical)
            "u-boot":  ( 638976, "d98fd80398b01b2ea2937e217a827e1d3d543f91681ef97e776c72bcf06310bd"),
            "monitor": (  66060, "95596d11aa6d10c0f3c8ef2c0d6fa01446be320c412decc201a5b547d6475ed7"),
            "scp":     ( 176132, "07487858659df9e8d4d3aba576b155e48c22076d4c1fff89cda6fa8ccde80e2f"),
            "optee":   ( 275328, "9b3addd56be7b1fe8d5fbcaafed191239ed77bde5190f91e6725b7ffa8916b61"),
            "dtb":     (  73728, "e34fc69b1d245199fd5e20367a4db43cebda7f042d5943310b37117de4dbf93a"),
        },
        "vendor_size": 114479104,            # D: vendor_a in the super LP metadata
        # The MIPS database is the L018's, so it does not pin this board down.
        "strong_features": ("scp_sha256", "uboot_sha256", "dtb_sha256", "uboot_version",
                            "arisc_version", "build_fingerprint"),
    },
    "dram": {                                # D: the 24 words of the vendor boot0 at LBA 16 (probe row)
        "clk": 792, "type": 3, "zq": 0x7b7bfb, "odt_en": 1,
        "para1": 0x10f4, "para2": 0x04000000,
        "mr0": 0x1c70, "mr1": 0x40, "mr2": 0x18, "mr3": 0,
        "tpr0": 0x4a2195, "tpr1": 0x2423190, "tpr2": 0x8b061, "tpr3": 0xb4787896,
        "tpr4": 0, "tpr5": 0x48484848, "tpr6": 0x48, "tpr7": 0x1620121e,
        "tpr8": 0, "tpr9": 0, "tpr10": 0, "tpr11": 0x44340000,
        "tpr12": 0x6666, "tpr13": 0xb4016103,
        # Q: against hy310.py (the boot0 of an update.img) only para2 and tpr13 differ (0 / 0x34010100
        # there): the two words the flash tool patches, read here off a running eMMC. Against
        # hy310_defconfig only tpr0..tpr2 differ (the bench board's there; unread on the DDR3 path).
        "source": "dump 2026-10-02, vendor boot0 at LBA 16 (h713-install dump, probe row)",
    },
    "layout": {
        "disk_sectors": 15273600,            # D: 3712 sectors more than the HY310's eMMC (15269888)
        "first_usable": 73728,
        "entries": 26,
        # D: the stock table of this device -- the HY310's, entry for entry; only UDISK runs to the
        # end of the larger eMMC (9718367 sectors). Download file names are the HY310's.
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
            ("UDISK",            5555200,  9718367, None),
        ],
        "raw": [("boot0_sdcard.fex", 16), ("boot0_sdcard.fex", 256),
                ("boot_package.fex", 24576), ("boot_package.fex", 32800)],
        "sunxi_gpt_disagrees": None,         # unknown: no sys_partition.fex of this device
    },
    "unique_regions": [
        ("secure-storage", 12288, 2048, "HDCP keys, WLAN/BT MAC addresses, serial number"),
        ("private", 4891648, 32768, "Android secure storage partition"),
        ("reserve0-a", 5489664, 32768, "Reserve0, slot A"),
        ("reserve0-b", 5522432, 32768, "Reserve0, slot B"),
    ],
    "preserve_on_restore": ("private", "Reserve0*", "bootloader_a", "bootloader_b", "media_data"),
    "mips": {
        "sources": ("bootloader_b", "bootloader_a", "vendor:/etc/display/mips"),
        # D: this board's display.bin is the HY310 revision (byte-identical), so the wait site is the
        # HY310's. The project id does NOT come from this hash: h713-extract's report prints
        # "used 0x30" from the hash, but U-Boot takes env h713_project, else panel_config.ini
        # (h713_mips.c, h713_disp_declared_project), and h713-install writes h713_project from
        # the device's panel_config.ini -- 0x34 here (GEU1 REPORT, section "project id").
        "revisions": [
            {"size": 1256216, "sha256": "16c74a28187f342de657828fab65145b140ac9411c40cccc02eed25047472ee9",
             "name": "HY310 (QZ713 V3.1)", "hdcp_wait_va": 0x4b13d0a4},
        ],
    },
    "panel": {                               # D: vendor:/etc/tvconfig/panel_config/panel_config.ini
        "declared_project_id": 0x34,         # ProjectID 52
        "width": 1280, "height": 720, "dual_port": False,
        "htotal": 1360, "vtotal": 760, "dclk_hz": 62000000,
        "hsync": 20, "vsync": 2, "hbp": 40, "vbp": 20,
        "hsync_pol": 0, "vsync_pol": 0,
        "pwm_channel": 5, "pwm_freq": 40000,  # [PWMSetting]: channel 5, low active, vs_lock 1, min 1, max 100
        "source": "panel_config.ini of the vendor partition in the dump",
    },
    # D: h713-extract output. Of the L018 reference set every file is byte-identical except this
    # build's own ARISC, display_cfg.xml and ProjectID_0x0034.TSE.
    "reference": {
        "boot/mips/LogoRegData.bin":               (15652, "0d00bcdd1fcfb185fe61525c9afa4bf3ec9982d605f137c593e8323766cfa4e3"),
        "boot/mips/ProjectID_0x0001.TSE":          (19992, "93258b453b8cf4d33ef49df24a9413aa2d6263367057d53dd7b907330b9aca85"),
        "boot/mips/ProjectID_0x0012.TSE":          (48952, "8077c4465ff09d72817a36b32c00f4cec36b5d54f9bb6073b64480b039a4f39d"),
        "boot/mips/ProjectID_0x0013.TSE":          (47880, "56ab808d776c063101d8e93be277a7802f07a4acc03fb99b678d78aba5e6431b"),
        "boot/mips/ProjectID_0x0014.TSE":          (47880, "f87c1d990bcd4543c1d8a11254316d18390ef39d3412d650a53e542b53da2d91"),
        "boot/mips/ProjectID_0x0015.TSE":          (47880, "be1622babeada99b8ccf79d361b4565752d30ede8cf0368e062b2ae8acfe3ba9"),
        "boot/mips/ProjectID_0x0016.TSE":          (47880, "9acba93639323d35d1b9360ac6758b2b7b4619ae04c45fc4fa0ccd04decee55a"),
        "boot/mips/ProjectID_0x0020.TSE":          (19992, "e8090e174ecb5d150248f78e00033482f3778d6100a7701b8f0364dfc8dec342"),
        "boot/mips/ProjectID_0x0030.TSE":          (19992, "0b53eabb6be1ac215de97813379d1b44400f0319e74ba9c25648523022785a33"),
        "boot/mips/ProjectID_0x0031.TSE":          (19992, "a152f6da9d883a2a83c55f12f1778c0f92040900128c8f4a95119e20fa13d8d4"),
        "boot/mips/ProjectID_0x0032.TSE":          (19992, "3129551510a9bb126aa239fe65d9e086f6569de843ae400bfa192bf3acece7e4"),
        "boot/mips/ProjectID_0x0033.TSE":          (19992, "32bbb023bd37534b5a0622e23c78f47f7a5d3e2060e77d72106b2d517720185c"),
        "boot/mips/ProjectID_0x0034.TSE":          (17328, "14807e7ff4a35baf8c29f8dfb3035444c3e69299e6dbaeb84c0186fcc62d72fe"),
        "boot/mips/ProjectID_0x0035.TSE":          (19992, "0a93397d0a1bf741fc06ab37e1de8680905e4c7cd1e72cb095bd9fadba8e89e2"),
        "boot/mips/database.TSE":                  (282464, "002ad401d581a293d56106c8faf361eb9919f234562a6d7c316c1de1438a2aac"),
        "boot/mips/display.bin":                   (1256216, "16c74a28187f342de657828fab65145b140ac9411c40cccc02eed25047472ee9"),
        "boot/mips/display_cfg.xml":               (4743, "b3e6e8f60d6f96ff458046af655f4b51e8e36ffc70f5107b0fef91badeca192a"),
        "boot/mips/pq_custom.TSE":                 (15016, "bf3d8110c38570e1ba28973e3cee2d3401a428510be0dab3b978474d7dd5a394"),
        "boot/mips/projecttable.TSE":              (1384, "12f568f0f0d9e6269aa2e8bf918117e997264f47e642b1c3984acb04abd26e65"),
        "lib/firmware/h713-arisc.bin":             (176132, "07487858659df9e8d4d3aba576b155e48c22076d4c1fff89cda6fa8ccde80e2f"),
        "lib/firmware/h713/msp-patch.bin":         (2896, "8e31db199e0078d142f622436ff0b7249b333dbb6df8ec3fbabc0d8fea6ea0c5"),
        "lib/firmware/hy310-edid.bin":             (512, "70d10294e3f1f1ba3aceaf684c90d2dcdcafc9ba4ed265956520bdf4adfb60ef"),
    },
    "expected": {
        "package_items": {"u-boot": 638976, "monitor": 66060, "scp": 176132, "optee": 275328, "dtb": 73728},
        "package_item_sha256": {
            "u-boot": "d98fd80398b01b2ea2937e217a827e1d3d543f91681ef97e776c72bcf06310bd",
            "monitor": "95596d11aa6d10c0f3c8ef2c0d6fa01446be320c412decc201a5b547d6475ed7",
            "scp": "07487858659df9e8d4d3aba576b155e48c22076d4c1fff89cda6fa8ccde80e2f",
            "optee": "9b3addd56be7b1fe8d5fbcaafed191239ed77bde5190f91e6725b7ffa8916b61",
            "dtb": "e34fc69b1d245199fd5e20367a4db43cebda7f042d5943310b37117de4dbf93a",
        },
        "uboot_version": "U-Boot 2018.05-00025-g4176897-dirty (May 06 2025 - 12:24:19 +0800)",
        "dtb_compatible": "allwinner,tv303",
        "arisc_version": "TV-303  ARISC  00.00.00.09 Date:May  6 2025",
        "vendor_size": 114479104,
        "libmspsound_sha256": "61f349440c08dd28ef1289f463a7934b3213b15518113ff1044f881bf237e8c4",
        "build_fingerprint": "Allwinner/h713_tuna_p3/h713-tuna_p3:11/RP1A.201005.006/projector05061226:user/release-keys",
        "sunxi_version": None,
        "mips_database_sha256": "002ad401d581a293d56106c8faf361eb9919f234562a6d7c316c1de1438a2aac",
    },
    # boards/hy300pro-g-eu/board.env KERNEL_DTB / UBOOT_BOARD (package GEU1): the HY310's tree
    # plus this board's lamp PWM words, and hy300pro_g_eu_defconfig. Neither has booted here.
    "board_dt": "sun50i-h713-hy300pro-g-eu",
    "uboot_board": "hy300pro_g_eu",
}
