"""HY300 Pro+ (2025, DDR3) -- board profile. Data only, no vendor bytes: numbers, hashes and strings.

The board this stock image belongs to is cstenger's bench board `HY200 QZ713DF_A1`: its boot0 DRAM
block is his `configs/hy200_qz713df_a1_defconfig` word for word (624 MHz, type 3, zq 0x7b7bfb,
para1 0x10f4, tpr11/12 0x44340000/0x6666), and the firmware table already carries this image's
display.bin under the name "HY200 QZ713DF_A1". Only para2/tpr13 differ (the flashing tool patches
that pair) and tpr0..tpr2, which the sun50iw12 DDR3 path computes from the clock anyway.

Shape: installer/h713/profiles/SCHEMA.md. Source tags used in the comments below:
  J  = installer/tests/fixtures/images/hy300-pro-plus-ddr3-0922.json (image facts of
       umbau/fixtures-local/images/hy300-pro-downloads/mega/update.img, h713.facts.image_facts())
  B  = boards/hy200-qz713df-a1/ (board.env, uboot.config, README.md -- cstenger's numbers)
  A0 = docs/subsystems/mips.md ("vendor boot path") (what the vendor U-Boot loads, and from where)
  F  = installer/tests/fixtures/firmware-revisions.json (display.bin revisions + HDCP wait site)
"""

PROFILE = {
    "id": "hy200_qz713df_a1",
    "name": "HY300 Pro+ (2025, DDR3) -- cstenger's HY200 QZ713DF_A1",
    "description": "HY300 Pro+ -- Allwinner H713, reference design h713_tuna_p3, DDR3 624 MHz, "
                   "stock build 2025-09-22 (projector09220931)",   # J vendor_build_prop, J boot0.dram
    # An image, but no device: nobody has run OUR firmware on this board (doku/121 section 5).
    # cstenger booted his own kernel tree on it; that is his run, not ours -- boards/hy200-qz713df-a1.
    "status": "profile-only",
    "verified_by": None,
    "soc": "H713 (sun50iw12)",               # J boot_package.dtb_model / dtb_compatible
    "stock": {
        # J vendor_build_prop fingerprint ":11/". The facts JSON says nothing about the bitness,
        # so unlike the HY310 row this one does not claim "(64-bit)".
        "android": "11",
        "sunxi_version": "2025-09-22 09:49:41",   # J sunxi_version
        # J vendor_build_prop ro.vendor.build.fingerprint
        "build_fingerprint": "Allwinner/h713_tuna_p3/h713-tuna_p3:11/RP1A.201005.006/"
                             "projector09220931:user/release-keys",
        # J boot_package.uboot_version / arisc_version, cut before " Allwinner Technology" resp.
        # " Time:" -- the extractor compares these two with startswith (X:194).
        "uboot_version": "U-Boot 2018.05-00027-ge159793 (Aug 15 2025 - 10:07:31 +0000)",
        "arisc_version": "TV-303  ARISC  00.00.00.09 Date:Sep 22 2025",
        "package_items": {                   # J boot_package.items
            "u-boot":  ( 638976, "22c9afa98503d4ce0b2b929cf8109af034d841560fbd11baf4ad851197134440"),
            "monitor": (  66060, "95596d11aa6d10c0f3c8ef2c0d6fa01446be320c412decc201a5b547d6475ed7"),
            "scp":     ( 176132, "3efebd9a537711864661f4af6687397f75e7c444b400dcfbc8f81bf387ba6129"),
            "optee":   ( 275328, "9b3addd56be7b1fe8d5fbcaafed191239ed77bde5190f91e6725b7ffa8916b61"),
            "dtb":     (  73728, "06e5279ce3d29ec22e269a076d43890e950eef45473d8952c9f6c18d24ced775"),
        },
        "vendor_size": 114384896,            # J super.partitions vendor_a
        # Every feature that tells this image apart from its LPDDR3 sibling (0710) and from every
        # other profile. Left out on purpose: mips_database_sha256 -- both HY300 Pro+ images carry
        # the same mips/database.TSE (27e2abad...), so it separates nothing here (the reason the
        # ADT-3 profiles leave it out too, doku/121 section 2, finding 1); and vendor_size.
        "strong_features": ("scp_sha256", "uboot_sha256", "dtb_sha256", "uboot_version",
                            "arisc_version", "build_fingerprint", "sunxi_version"),
    },
    "dram": {                                # J boot0.dram -- the 24 u32 at boot0_sdcard.fex+0x38
        "clk": 624, "type": 3, "zq": 0x7b7bfb, "odt_en": 1,
        "para1": 0x10f4, "para2": 0,
        "mr0": 0x1c70, "mr1": 0x40, "mr2": 0x18, "mr3": 0,
        "tpr0": 0x4a2195, "tpr1": 0x2423190, "tpr2": 0x8b061, "tpr3": 0xb4787896,
        "tpr4": 0, "tpr5": 0x48484848, "tpr6": 0x48, "tpr7": 0x1620121e,
        "tpr8": 0, "tpr9": 0, "tpr10": 0, "tpr11": 0x44340000,
        "tpr12": 0x6666, "tpr13": 0x34010100,
        # J sys_config.dram_para carries the same 24 words. para2 and tpr13 are the unpatched pair
        # every image boot0 has; the flashing tool patches them (B uboot.config: 0x04000000 /
        # 0xb4016103, read off the running board). boards/README.md, "Two conventions".
        "source": "boot0_sdcard.fex offset 0x38, hy300-pro-downloads/mega/update.img "
                  "(sha256 ced372b4..., J input)",
    },
    "layout": {                              # J sys_partition[] -- the stock table of this image
        "disk_sectors": 15269888,            # J sunxi_gpt.header.last_usable 15269854 + 34
        "first_usable": 73728,               # J sunxi_gpt.header.first_usable
        "entries": 26,                       # len(J sys_partition) = J sunxi_gpt.header.entries
        # name, start LBA, sectors, downloadfile -- rows of J sys_partition in table order.
        # Same shape as the HY310's: 26 entries, media_data 557056 sectors, Reserve0_a/_b.
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
        "raw": None,                         # J records no raw targets for this image (as hy350)
        # J layout_consistency[0]: sys_partition.fex says media_data is 557056 sectors, sunxi_gpt.fex
        # says 524288 -- the same disagreement the HY310 image has (doku/121 section 2, finding 6).
        "sunxi_gpt_disagrees": {"media_data": (557056, 524288)},
    },
    # I:95 EINMALIG only for secure-storage, whose position is fixed for every H713; private and
    # Reserve0_a/_b are found by name in the device's own GPT (A0 section 5, issue #1 defect 2).
    "unique_regions": [
        ("secure-storage", 12288, 2048, "HDCP keys, WLAN/BT MAC addresses, serial number"),
        ("private", "by-name", 32768, "Android secure storage partition; J sys_partition private@4891648"),
        ("Reserve0_a", "by-name", 32768, "panel_config.ini and calibration; J sys_partition Reserve0_a@5489664"),
        ("Reserve0_b", "by-name", 32768, "Reserve0, slot B; J sys_partition Reserve0_b@5522432"),
    ],
    # A0 section 5: partitions no stock image supplies (or supplies wrongly). "Reserve0*" matches the
    # single Reserve0 as well as the Reserve0_a/_b pair; media_data is /oem, where the vendor looks for
    # TSE overrides before it looks in the bootloader partition.
    "preserve_on_restore": ("private", "Reserve0*", "bootloader_a", "bootloader_b", "media_data"),
    "mips": {
        # A0 section 4: J boot_resource_fat.has_mips_dir is true and J mips_files.display_bin.source
        # is "boot_resource_fat:mips/" -- this board's U-Boot loads mips/* from the bootloader
        # partition the slot byte in misc selects, and falls back to the vendor copy only then.
        "sources": ("bootloader_b", "bootloader_a", "vendor:/etc/display/mips"),
        "revisions": [                       # F, row "HY200 QZ713DF_A1"; size/sha256 = J mips_files
            # hdcp_wait_va recomputed with h713.hdcpsite.search() over the extracted display.bin
            # (fixtures-local/vendor-boot/hy300-pro-plus-ddr3/boot/mips/display.bin): one hit with
            # context at offset 0x3d6f8 -> 0x4b13d6f8 = the value h713_mips_fw_revs[] pins for this
            # revision, which until now nobody had measured.
            {"size": 1255696, "sha256": "4380f1b3ed7b62aa50582e7cb16a87bdface1b4300578fe3631a416354da30ce",
             "name": "HY200 QZ713DF_A1", "hdcp_wait_va": 0x4b13d6f8},
        ],
    },
    "panel": {                               # J panel_config[*].reserve0 -- vendor copy identical
        "declared_project_id": 0x34,         # ProjectID 52
        "width": 1280, "height": 720, "dual_port": False,
        "htotal": 1360, "vtotal": 760, "dclk_hz": 62000000,
        "hsync": 20, "vsync": 2, "hbp": 40, "vbp": 20,
        "hsync_pol": 0, "vsync_pol": 0,
        "pwm_channel": 5, "pwm_freq": 40000,
        "source": "Reserve0.fex:panel_config.ini",
    },
    "reference": None,                       # no device of this board has been extracted
    "expected": {
        # The same facts as "stock" above, in the shape identify() compares a device against.
        # Values from J, keys as the schema names them.
        "package_items": {"u-boot": 638976, "monitor": 66060, "scp": 176132, "optee": 275328, "dtb": 73728},
        "package_item_sha256": {
            "u-boot": "22c9afa98503d4ce0b2b929cf8109af034d841560fbd11baf4ad851197134440",
            "monitor": "95596d11aa6d10c0f3c8ef2c0d6fa01446be320c412decc201a5b547d6475ed7",
            "scp": "3efebd9a537711864661f4af6687397f75e7c444b400dcfbc8f81bf387ba6129",
            "optee": "9b3addd56be7b1fe8d5fbcaafed191239ed77bde5190f91e6725b7ffa8916b61",
            "dtb": "06e5279ce3d29ec22e269a076d43890e950eef45473d8952c9f6c18d24ced775",
        },
        "uboot_version": "U-Boot 2018.05-00027-ge159793 (Aug 15 2025 - 10:07:31 +0000)",
        "dtb_compatible": "allwinner,tv303", # J boot_package.dtb_compatible, first entry (as X:134)
        "arisc_version": "TV-303  ARISC  00.00.00.09 Date:Sep 22 2025",
        "vendor_size": 114384896,
        "libmspsound_sha256": None,          # not in J firmware_hints for this image
        "build_fingerprint": "Allwinner/h713_tuna_p3/h713-tuna_p3:11/RP1A.201005.006/"
                             "projector09220931:user/release-keys",
        "sunxi_version": "2025-09-22 09:49:41",
        # J mips_files.sources[*] database.TSE -- identical in both HY300 Pro+ images, so it is
        # recorded but not listed under strong_features.
        "mips_database_sha256": "27e2abad947f319b7b5da229f1b078a6a986592718f98dcd745215338fcd4f81",
    },
    # B board.env KERNEL_DTB: cstenger's device tree for this board. It has booted in his tree,
    # never in ours -- that is why "status" stays profile-only.
    "board_dt": "sun50i-h713-hy200-qz713df-a1",
    "uboot_board": "hy200-qz713df-a1",       # B board.env UBOOT_BOARD (base hy200_qz713df_a1_defconfig)
}
