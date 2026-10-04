"""HY200 QZ713DF A1 -- board profile with two stock firmwares. Data only, no vendor bytes.

One printed circuit board, silkscreen HY200 QZ713DF A1: cstenger's bench board, the "HY300 Pro+"
of 2025 (DDR3) and the maintainer's HY300PRO-G-EU. What differs between units is the firmware they
left the factory with, so the board's keys are here and each firmware is a variant, named after its
stock build (boards/hy200-qz713df-a1/README.md has the comparison, row by row, with its sources):

  projector05061226  HY300PRO-G-EU, Android 11 of 2025-05-06 - the maintainer's own unit
  projector09220931  HY300 Pro+ (2025, DDR3), Android 11 of 2025-09-22 - no unit of ours

Shape: installer/h713/profiles/SCHEMA.md ("variants"). Source tags used in the comments below:
  D  = the HY300PRO-G-EU's own eMMC dump of 2026-10-02 (kept private) and h713-extract 0.4 over it
  B  = ADB getprop of its running stock system (read only)
  J  = installer/tests/fixtures/images/hy300-pro-plus-ddr3-0922.json (image facts of the 2025-09-22
       update.img in the local firmware archive, firmware/hy200-qz713df-a1/2025-09-22_projector09220931/)
  A0 = docs/subsystems/mips.md ("vendor boot path")
  F  = installer/tests/fixtures/firmware-revisions.json (display.bin revisions + HDCP wait site)
"""

# The stock table of both firmwares, entry for entry (D: the GPT of the dump; J: sys_partition[]).
# Only UDISK differs: on a device it runs to the end of its eMMC, in an image it is 0 (= the rest).
_PARTITIONS = [
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
]
_MIPS_SOURCES = ("bootloader_b", "bootloader_a", "vendor:/etc/display/mips")   # A0 section 4
_STRONG = ("scp_sha256", "uboot_sha256", "dtb_sha256", "uboot_version", "arisc_version",
           "build_fingerprint")

# D: the 24 words of the vendor boot0 at LBA 16. J boot0.dram (boot0_sdcard.fex+0x38) carries the
# same 23 words and clk 624; its para2/tpr13 are the unpatched pair every image boot0 has (0 /
# 0x34010100), which the flashing tool patches (boards/README.md, "Two conventions").
_DRAM = {"type": 3, "zq": 0x7b7bfb, "odt_en": 1, "para1": 0x10f4,
         "mr0": 0x1c70, "mr1": 0x40, "mr2": 0x18, "mr3": 0,
         "tpr0": 0x4a2195, "tpr1": 0x2423190, "tpr2": 0x8b061, "tpr3": 0xb4787896,
         "tpr4": 0, "tpr5": 0x48484848, "tpr6": 0x48, "tpr7": 0x1620121e,
         "tpr8": 0, "tpr9": 0, "tpr10": 0, "tpr11": 0x44340000, "tpr12": 0x6666}


def _expected(stock, compatible, libmspsound, database):
    """The "expected" block identify() compares, built from a variant's "stock" (same values)."""
    items = stock["package_items"]
    return {"package_items": dict((n, size) for n, (size, _h) in items.items()),
            "package_item_sha256": dict((n, h) for n, (_s, h) in items.items()),
            "uboot_version": stock["uboot_version"], "dtb_compatible": compatible,
            "arisc_version": stock["arisc_version"], "vendor_size": stock["vendor_size"],
            "libmspsound_sha256": libmspsound, "build_fingerprint": stock["build_fingerprint"],
            "sunxi_version": stock["sunxi_version"], "mips_database_sha256": database}


_GEU_STOCK = {
    "android": "11 (ARMv7 userland, kernel 5.4.99)",   # B: ro.build.version.release, uname armv7l
    "sunxi_version": None,                   # a device does not carry it
    "build_fingerprint": "Allwinner/h713_tuna_p3/h713-tuna_p3:11/RP1A.201005.006/projector05061226:user/release-keys",
    "uboot_version": "U-Boot 2018.05-00025-g4176897-dirty (May 06 2025 - 12:24:19 +0800)",
    "arisc_version": "TV-303  ARISC  00.00.00.09 Date:May  6 2025",
    "package_items": {                       # D: sunxi-package at LBA 24576 (32800 identical)
        "u-boot":  ( 638976, "d98fd80398b01b2ea2937e217a827e1d3d543f91681ef97e776c72bcf06310bd"),
        "monitor": (  66060, "95596d11aa6d10c0f3c8ef2c0d6fa01446be320c412decc201a5b547d6475ed7"),
        "scp":     ( 176132, "07487858659df9e8d4d3aba576b155e48c22076d4c1fff89cda6fa8ccde80e2f"),
        "optee":   ( 275328, "9b3addd56be7b1fe8d5fbcaafed191239ed77bde5190f91e6725b7ffa8916b61"),
        "dtb":     (  73728, "e34fc69b1d245199fd5e20367a4db43cebda7f042d5943310b37117de4dbf93a"),
    },
    "vendor_size": 114479104,                # D: vendor_a in the super LP metadata
    # The MIPS database is the L018's, so it does not pin this firmware down.
    "strong_features": _STRONG,
}

_PLUS_STOCK = {
    "android": "11",                         # J fingerprint ":11/"; J says nothing about the bitness
    "sunxi_version": "2025-09-22 09:49:41",  # J sunxi_version
    "build_fingerprint": "Allwinner/h713_tuna_p3/h713-tuna_p3:11/RP1A.201005.006/projector09220931:user/release-keys",
    # J boot_package.uboot_version / arisc_version, cut before " Allwinner Technology" resp. " Time:"
    "uboot_version": "U-Boot 2018.05-00027-ge159793 (Aug 15 2025 - 10:07:31 +0000)",
    "arisc_version": "TV-303  ARISC  00.00.00.09 Date:Sep 22 2025",
    "package_items": {                       # J boot_package.items
        "u-boot":  ( 638976, "22c9afa98503d4ce0b2b929cf8109af034d841560fbd11baf4ad851197134440"),
        "monitor": (  66060, "95596d11aa6d10c0f3c8ef2c0d6fa01446be320c412decc201a5b547d6475ed7"),
        "scp":     ( 176132, "3efebd9a537711864661f4af6687397f75e7c444b400dcfbc8f81bf387ba6129"),
        "optee":   ( 275328, "9b3addd56be7b1fe8d5fbcaafed191239ed77bde5190f91e6725b7ffa8916b61"),
        "dtb":     (  73728, "06e5279ce3d29ec22e269a076d43890e950eef45473d8952c9f6c18d24ced775"),
    },
    "vendor_size": 114384896,                # J super.partitions vendor_a
    # What tells this image apart from its LPDDR3 sibling (0710), from the 2025-05 firmware and from
    # every other profile. Not mips_database_sha256: both HY300 Pro+ images carry 27e2abad...
    "strong_features": _STRONG + ("sunxi_version",),
}

PROFILE = {
    "id": "hy200_qz713df_a1",
    "name": "HY200 QZ713DF A1",
    "description": "HY200 QZ713DF A1 -- Allwinner H713, reference design h713_tuna_p3, DDR3; sold as "
                   "HY300 Pro (box label HY300PRO-G-EU) and HY300 Pro+ (2025)",
    "soc": "H713 (sun50iw12)",               # D, J: dtb_compatible "allwinner,tv303 arm,sun50iw12p1"
    # Same LBAs in both tables (D GPT, J sys_partition); found by name in the device's own GPT.
    "unique_regions": [
        ("secure-storage", 12288, 2048, "HDCP keys, WLAN/BT MAC addresses, serial number"),
        ("private", "by-name", 32768, "Android secure storage partition; private@4891648 in D and J"),
        ("Reserve0_a", "by-name", 32768, "panel_config.ini and calibration; Reserve0_a@5489664 in D and J"),
        ("Reserve0_b", "by-name", 32768, "Reserve0, slot B; Reserve0_b@5522432 in D and J"),
    ],
    # A0 section 5: partitions no stock image supplies (or supplies wrongly).
    "preserve_on_restore": ("private", "Reserve0*", "bootloader_a", "bootloader_b", "media_data"),
    # panel_config.ini of both firmwares (D vendor copy; J Reserve0 and vendor copy): equal in every
    # field, [PWMSetting] 5 / low active / 40 kHz / vs_lock 1 / 1..100 and ColorDepth 8 in both.
    "panel": {
        "declared_project_id": 0x34,         # ProjectID 52
        "width": 1280, "height": 720, "dual_port": False,
        "htotal": 1360, "vtotal": 760, "dclk_hz": 62000000,
        "hsync": 20, "vsync": 2, "hbp": 40, "vbp": 20,
        "hsync_pol": 0, "vsync_pol": 0,
        "pwm_channel": 5, "pwm_freq": 40000,
        "source": "panel_config.ini of both firmwares (D vendor partition, J Reserve0.fex)",
    },
    # boards/hy200-qz713df-a1/board.env KERNEL_DTB / UBOOT_BOARD: one tree and one U-Boot base for
    # the board; the DRAM clock is the variant's (variants/<name>/variant.env DRAM_CLK).
    "board_dt": "sun50i-h713-hy200-qz713df-a1",
    "uboot_board": "hy200_qz713df_a1",
    "variants": {
        "projector05061226": {
            "name": "HY300PRO-G-EU (HY200 QZ713DF A1, stock 2025-05-06)",
            "description": "HY300PRO-G-EU -- HY200 QZ713DF A1, DDR3 792 MHz, stock build 2025-05-06 "
                           "(projector05061226); not the board of issue #1",
            # D: a dump of a real device lies on this host, and a TEST image of ours has booted on
            # it (doku/136), but its owner has not reported a green run.
            "status": "profile-only",
            "verified_by": None,
            "stock": _GEU_STOCK,
            "dram": dict(_DRAM, clk=792, para2=0x04000000, tpr13=0xb4016103,
                         source="dump 2026-10-02, vendor boot0 at LBA 16 (h713-install dump, probe row)"),
            "layout": {
                "disk_sectors": 15273600,    # D: 3712 sectors more than the HY310's eMMC (15269888)
                "first_usable": 73728,
                "entries": 26,
                "partitions": _PARTITIONS + [("UDISK", 5555200, 9718367, None)],
                "raw": [("boot0_sdcard.fex", 16), ("boot0_sdcard.fex", 256),
                        ("boot_package.fex", 24576), ("boot_package.fex", 32800)],
                "sunxi_gpt_disagrees": None,  # unknown: no sys_partition.fex of this firmware
            },
            "mips": {
                "sources": _MIPS_SOURCES,
                # D: the HY310 revision, byte for byte, so the wait site is the HY310's. The project id
                # does NOT come from this hash: U-Boot takes env h713_project, else panel_config.ini.
                "revisions": [
                    {"size": 1256216, "sha256": "16c74a28187f342de657828fab65145b140ac9411c40cccc02eed25047472ee9",
                     "name": "HY310 (QZ713 V3.1)", "hdcp_wait_va": 0x4b13d0a4},
                ],
            },
            # D: h713-extract output. Of the L018 reference set every file is byte-identical except
            # this build's own ARISC, display_cfg.xml and ProjectID_0x0034.TSE.
            "reference": {
                "boot/mips/LogoRegData.bin":      (15652, "0d00bcdd1fcfb185fe61525c9afa4bf3ec9982d605f137c593e8323766cfa4e3"),
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
                "boot/mips/ProjectID_0x0034.TSE": (17328, "14807e7ff4a35baf8c29f8dfb3035444c3e69299e6dbaeb84c0186fcc62d72fe"),
                "boot/mips/ProjectID_0x0035.TSE": (19992, "0a93397d0a1bf741fc06ab37e1de8680905e4c7cd1e72cb095bd9fadba8e89e2"),
                "boot/mips/database.TSE":         (282464, "002ad401d581a293d56106c8faf361eb9919f234562a6d7c316c1de1438a2aac"),
                "boot/mips/display.bin":          (1256216, "16c74a28187f342de657828fab65145b140ac9411c40cccc02eed25047472ee9"),
                "boot/mips/display_cfg.xml":      (4743, "b3e6e8f60d6f96ff458046af655f4b51e8e36ffc70f5107b0fef91badeca192a"),
                "boot/mips/pq_custom.TSE":        (15016, "bf3d8110c38570e1ba28973e3cee2d3401a428510be0dab3b978474d7dd5a394"),
                "boot/mips/projecttable.TSE":     (1384, "12f568f0f0d9e6269aa2e8bf918117e997264f47e642b1c3984acb04abd26e65"),
                "lib/firmware/h713-arisc.bin":    (176132, "07487858659df9e8d4d3aba576b155e48c22076d4c1fff89cda6fa8ccde80e2f"),
                "lib/firmware/h713/msp-patch.bin": (2896, "8e31db199e0078d142f622436ff0b7249b333dbb6df8ec3fbabc0d8fea6ea0c5"),
                "lib/firmware/hy310-edid.bin":    (512, "70d10294e3f1f1ba3aceaf684c90d2dcdcafc9ba4ed265956520bdf4adfb60ef"),
            },
            "expected": _expected(_GEU_STOCK, "allwinner,tv303",
                                  "61f349440c08dd28ef1289f463a7934b3213b15518113ff1044f881bf237e8c4",
                                  "002ad401d581a293d56106c8faf361eb9919f234562a6d7c316c1de1438a2aac"),
        },
        "projector09220931": {
            "name": "HY300 Pro+ (HY200 QZ713DF A1, stock 2025-09-22)",
            "description": "HY300 Pro+ -- HY200 QZ713DF A1, DDR3 624 MHz, stock build 2025-09-22 "
                           "(projector09220931)",   # J vendor_build_prop, J boot0.dram
            # An image, but no device: nobody has run OUR firmware on a unit with this firmware
            # (doku/121 section 5). cstenger booted his own tree on his bench; his run, not ours.
            "status": "profile-only",
            "verified_by": None,
            "stock": _PLUS_STOCK,
            "dram": dict(_DRAM, clk=624, para2=0, tpr13=0x34010100,
                         source="boot0_sdcard.fex offset 0x38, hy300-pro-downloads/mega/update.img "
                                "(sha256 ced372b4..., J input)"),
            "layout": {                      # J sys_partition[] -- the stock table of this image
                # J sunxi_gpt.header.last_usable 15269854 + 34: the vendor's template, not a chip
                # anybody has read; a unit's own identify row gives its eMMC's real size.
                "disk_sectors": 15269888,
                "first_usable": 73728,
                "entries": 26,
                "partitions": _PARTITIONS + [("UDISK", 5555200, 0, None)],
                "raw": None,                 # J records no raw targets for this image (as hy350)
                # J layout_consistency[0]: the HY310 image's disagreement (doku/121 section 2, finding 6)
                "sunxi_gpt_disagrees": {"media_data": (557056, 524288)},
            },
            "mips": {
                "sources": _MIPS_SOURCES,
                "revisions": [               # F, row "HY200 QZ713DF_A1"; size/sha256 = J mips_files
                    # hdcp_wait_va from h713.hdcpsite.search() over this display.bin: one hit with
                    # context at offset 0x3d6f8, the value h713_mips_fw_revs[] pins for the revision.
                    {"size": 1255696, "sha256": "4380f1b3ed7b62aa50582e7cb16a87bdface1b4300578fe3631a416354da30ce",
                     "name": "HY200 QZ713DF_A1", "hdcp_wait_va": 0x4b13d6f8},
                ],
            },
            "reference": None,               # no device with this firmware has been extracted
            # J: libmspsound is not in its firmware_hints; database.TSE is recorded, not strong.
            "expected": _expected(_PLUS_STOCK, "allwinner,tv303", None,
                                  "27e2abad947f319b7b5da229f1b078a6a986592718f98dcd745215338fcd4f81"),
        },
    },
}
