"""L018 -- board profile. Data only, no vendor bytes: numbers, hashes and strings.

Shape: installer/h713/profiles/SCHEMA.md. Source tags used in the comments below:
  X  = analyse/release/arbeit/r2-extract/h713-extract (line numbers are lines 52-275)
  A0 = docs/subsystems/mips.md ("vendor boot path") (what the vendor U-Boot loads, and from where)
  F  = installer/tests/fixtures/firmware-revisions.json (display.bin revisions + HDCP wait site, package A5)
"""

PROFILE = {
    "id": "l018",
    "name": "L018",                          # X:144
    "description": "L018 -- Allwinner H713, reference design h713_tuna_p3, "
                   "stock build 2025-05-14 (Projector05141211)",   # X:145, translated
    # No image and no dump of this board on this host: everything below comes from the extractor tables,
    # which were filled from the first run on a real L018 (X:57-62, S42 section 4). Hence "profile-only".
    "status": "profile-only",
    "verified_by": None,
    "soc": "H713 (sun50iw12)",               # X:162 dtb_compatible "allwinner,tv303"
    "stock": {
        "android": "11",                     # X:166 build_fingerprint ":11/"
        "sunxi_version": "2025-05-14 12:19:36",   # X:167
        "build_fingerprint": "Allwinner/h713_tuna_p3/h713-tuna_p3:11/RP1A.201005.006/Projector05141211:user/release-keys",
        "uboot_version": "U-Boot 2018.05-00025-gf362927-dirty (May 14 2025 - 12:09:44 +0800)",
        "arisc_version": "TV-303  ARISC  00.00.00.09 Date:May 14 2025",
        # X:153/154 paket_items + paket_item_sha256 of GERAETE["l018"]["erwartung"].
        "package_items": {
            "u-boot":   (638976, "8c690dddd2d98eddf0128a46ac64d545b85983303e0eeeb3547859736bbcf073"),
            "monitor":  ( 66060, "95596d11aa6d10c0f3c8ef2c0d6fa01446be320c412decc201a5b547d6475ed7"),
            "scp":      (176132, "d4b4a0b9da4f061a7b5fac1197acf12613813a7750c1f27c3c2d8ae478037006"),
            "optee":    (275328, "9b3addd56be7b1fe8d5fbcaafed191239ed77bde5190f91e6725b7ffa8916b61"),
            "dtb":      ( 73216, "2d05339fa4fe65edc9d7e89fe4be41ee0703f11e3dd87e565c53a2ce3490aa3e"),
        },
        "vendor_size": 114466816,            # X:164
        "strong_features": ("scp_sha256", "uboot_sha256", "dtb_sha256", "uboot_version",
                            "arisc_version", "build_fingerprint", "mips_database_sha256"),
    },
    "dram": None,                            # unknown: no boot0 of this board has been read
    "layout": None,                          # unknown: no image and no GPT of this board has been read
    # I:95 EINMALIG only for secure-storage, the one region whose position is fixed for every H713;
    # private and Reserve0 have to be found by name in the device's own GPT (A0 section 5, issue #1
    # defect 2) -- this board's GPT has never been read.
    "unique_regions": [
        ("secure-storage", 12288, 2048, "HDCP keys, WLAN/BT MAC addresses, serial number"),
        ("private", "by-name", None, "Android secure storage partition"),
        ("Reserve0", "by-name", None, "panel_config.ini and calibration; may be a Reserve0_a/_b pair"),
    ],
    # A0 section 5: partitions no stock image supplies (or supplies wrongly). "Reserve0*" matches the
    # single Reserve0 as well as the Reserve0_a/_b pair; media_data is /oem, where the vendor looks for
    # TSE overrides before it looks in the bootloader partition.
    "preserve_on_restore": ("private", "Reserve0*", "bootloader_a", "bootloader_b", "media_data"),
    "mips": {
        # X:95-96: the mips/ set of this board differs from the HY310 one in database.TSE only
        # (S42 section 9), so it is the same U-Boot family (A0 section 4). No vendor dump of an
        # L018 exists (X:107-109), so the third entry is the family default, not a measurement.
        "sources": ("bootloader_b", "bootloader_a", "vendor:/etc/display/mips"),
        # F, row "HY310 (QZ713 V3.1)": the display.bin of the L018 is byte-identical to the HY310 one
        # (X:95-96 _MIPS_REF_L018 replaces database.TSE only), so it is the same revision and wait site.
        "revisions": [
            {"size": 1256216, "sha256": "16c74a28187f342de657828fab65145b140ac9411c40cccc02eed25047472ee9",
             "name": "HY310 (QZ713 V3.1)", "hdcp_wait_va": 0x4b13d0a4},
        ],
    },
    "panel": None,                           # unknown: no panel_config.ini of this board has been read
    # X:146 GERAETE["l018"]["referenz"] -- values verbatim. EDID and MSP patch are byte-identical
    # with the HY310 (S42 section 4); of the mips/ set only database.TSE differs (S42 section 9).
    "reference": {
        "lib/firmware/h713-arisc.bin": (176132, "d4b4a0b9da4f061a7b5fac1197acf12613813a7750c1f27c3c2d8ae478037006"),
        "lib/firmware/hy310-edid.bin": (512, "70d10294e3f1f1ba3aceaf684c90d2dcdcafc9ba4ed265956520bdf4adfb60ef"),
        "lib/firmware/h713/msp-patch.bin": (2896, "8e31db199e0078d142f622436ff0b7249b333dbb6df8ec3fbabc0d8fea6ea0c5"),
        # X:95-96 _MIPS_REF_L018 -- mips/ of boot-resource.fex, measured 10.09.2026 from
        # update.img and from the eMMC dump of the dev device (LBA 73728 / 139264).
        "boot/mips/display.bin": (1256216, "16c74a28187f342de657828fab65145b140ac9411c40cccc02eed25047472ee9"),
        "boot/mips/display_cfg.xml": (4766, "9dce62c73bf5dea5bd6fecdfdee59f06ed3c3ad13fc4b5415842733f67bd4ca7"),
        "boot/mips/LogoRegData.bin": (15652, "0d00bcdd1fcfb185fe61525c9afa4bf3ec9982d605f137c593e8323766cfa4e3"),
        "boot/mips/database.TSE": (282464, "002ad401d581a293d56106c8faf361eb9919f234562a6d7c316c1de1438a2aac"),
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
    },
    "expected": {
        # X:152 GERAETE["l018"]["erwartung"], keys translated (paket_items -> package_items,
        # paket_item_sha256 -> package_item_sha256), values verbatim.
        "package_items": {"u-boot": 638976, "monitor": 66060, "scp": 176132, "optee": 275328, "dtb": 73216},
        "package_item_sha256": {
            "u-boot": "8c690dddd2d98eddf0128a46ac64d545b85983303e0eeeb3547859736bbcf073",
            "monitor": "95596d11aa6d10c0f3c8ef2c0d6fa01446be320c412decc201a5b547d6475ed7",
            "scp": "d4b4a0b9da4f061a7b5fac1197acf12613813a7750c1f27c3c2d8ae478037006",
            "optee": "9b3addd56be7b1fe8d5fbcaafed191239ed77bde5190f91e6725b7ffa8916b61",
            "dtb": "2d05339fa4fe65edc9d7e89fe4be41ee0703f11e3dd87e565c53a2ce3490aa3e",
        },
        "uboot_version": "U-Boot 2018.05-00025-gf362927-dirty (May 14 2025 - 12:09:44 +0800)",
        "dtb_compatible": "allwinner,tv303",
        "arisc_version": "TV-303  ARISC  00.00.00.09 Date:May 14 2025",
        "vendor_size": 114466816,
        "libmspsound_sha256": "61f349440c08dd28ef1289f463a7934b3213b15518113ff1044f881bf237e8c4",
        "build_fingerprint": "Allwinner/h713_tuna_p3/h713-tuna_p3:11/RP1A.201005.006/Projector05141211:user/release-keys",
        "sunxi_version": "2025-05-14 12:19:36",
        "mips_database_sha256": "002ad401d581a293d56106c8faf361eb9919f234562a6d7c316c1de1438a2aac",
    },
    "board_dt": None,                        # no device tree of ours has booted on this board
                                             # (boards/<id>/board.env leaves KERNEL_DTB empty)
    "uboot_board": None,                     # no U-Boot base defconfig of ours for this board
}
