"""HY350 -- board profile. Data only, no vendor bytes: numbers, hashes and strings.

Shape: umbau/plan/profil-schema.md. Source tags used in the comments below:
  J  = umbau/fixtures/images/hy350.json (board facts of the stock image, package A1)
  X  = analyse/release/arbeit/r2-extract/h713-extract (line numbers are lines 52-275)
  A0 = umbau/work/A0/REPORT.md, sections 4 and 5 (what the vendor U-Boot loads, and from where)
  F  = umbau/fixtures/firmware-revisions.json (display.bin revisions + HDCP wait site, package A5)
"""

PROFILE = {
    "id": "hy350",
    "name": "HY350",
    "description": "HY350 -- Allwinner H713, ADT-3 Android 10 stock, OTA image 2024-10-25",
    # An image, but no device: nobody has run this profile against the hardware (doku/121 section 5).
    "status": "profile-only",
    "verified_by": None,
    "soc": "H713 (sun50iw12)",               # J boot_package.dtb_model / dtb_compatible
    "stock": {
        "android": "10",                     # J vendor_build_prop fingerprint ":10/" (ADT-3 build 6245789)
        "sunxi_version": "2024-10-25 17:15:54",   # J sunxi_version
        "build_fingerprint": "ADT-3/adt3/adt3:10/QTT1.200116.002.B6/6245789:user/release-keys",
        # J boot_package.uboot_version / arisc_version, cut before " Allwinner Technology" resp. " Time:".
        "uboot_version": "U-Boot 2018.05-00023-gea35390-dirty (Oct 25 2024 - 17:02:31 +0800)",
        "arisc_version": "TV-303  ARISC  00.00.00.09 Date:Oct 25 2024",
        "package_items": {                   # J boot_package.items
            "u-boot":  ( 638976, "ec4df2f7e1847fc4436e615f63f1797b71f039c6e1b5cfb24527adf0f03291bb"),
            "monitor": (  66060, "95596d11aa6d10c0f3c8ef2c0d6fa01446be320c412decc201a5b547d6475ed7"),
            "scp":     ( 176132, "667da19bb74b3d376c80ce0502ce79fc708b8fe88c247b7f590488ae940d14bd"),
            "optee":   ( 267136, "c391dde39995529ab70b883ec4499a7f44954d439d1d6d0f9ccfa3ae01ea762a"),
            "dtb":     (  71168, "681fe8f955e5dcc68a4f0446cfa6e55dce803592108c18994a21de8d798dad8f"),
        },
        "vendor_size": 115826688,            # J super.partitions vendor_a
        # X:181 STARKE_MERKMALE minus build_fingerprint and mips_database_sha256: both
        # ADT-3 images carry the SAME fingerprint (J vendor_build_prop) and the SAME
        # database.TSE (J mips_files), so neither tells HY300 T08 and HY350 apart.
        "strong_features": ("scp_sha256", "uboot_sha256", "dtb_sha256", "uboot_version",
                            "arisc_version", "sunxi_version"),
    },
    "dram": {                                # J boot0.dram -- the 24 u32 at boot0_sdcard.fex+0x38
        "clk": 792, "type": 3, "zq": 0x7b7bfb, "odt_en": 1,
        "para1": 0x10f4, "para2": 0,
        "mr0": 0x1c70, "mr1": 0x40, "mr2": 0x18, "mr3": 0,
        "tpr0": 0x4a2195, "tpr1": 0x2423190, "tpr2": 0x8b061, "tpr3": 0xb4787896,
        "tpr4": 0, "tpr5": 0x48484848, "tpr6": 0x48, "tpr7": 0x1620121e,
        "tpr8": 0, "tpr9": 0, "tpr10": 0, "tpr11": 0x44440000,
        "tpr12": 0x5555, "tpr13": 0x34010100,
        "source": "boot0_sdcard.fex offset 0x38, HY350_user_public_en_F_chuangyihui_OTA_2024-10-25-1715_.img",
    },
    "layout": {                              # J sys_partition[] -- the stock table of this image
        "disk_sectors": 15269888,            # J sunxi_gpt.header.last_usable 15269854 + 34
        "first_usable": 73728,               # J sunxi_gpt.header.first_usable
        "entries": 25,                       # len(J sys_partition) = J sunxi_gpt.header.entries
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
            ("super",             599040,  5242880, "super.fex"),
            ("misc",             5841920,    32768, "misc.fex"),
            ("vbmeta_a",         5874688,      256, "vbmeta.fex"),
            ("vbmeta_b",         5874944,      256, None),
            ("vbmeta_system_a",  5875200,      128, "vbmeta_system.fex"),
            ("vbmeta_system_b",  5875328,      128, None),
            ("vbmeta_vendor_a",  5875456,      128, "vbmeta_vendor.fex"),
            ("vbmeta_vendor_b",  5875584,      128, None),
            ("frp",              5875712,     1024, None),
            ("empty",            5876736,    30720, None),
            ("metadata",         5907456,    32768, None),
            ("private",          5940224,    32768, None),
            ("dtbo_a",           5972992,     4096, "dtbo.fex"),
            ("dtbo_b",           5977088,     4096, None),
            ("media_data",       5981184,    32768, None),
            ("Reserve0",         6013952,    32768, "Reserve0.fex"),
            ("UDISK",            6046720,        0, None),
        ],
        "raw": None,                         # the A1 facts record no raw targets for this image
        "sunxi_gpt_disagrees": None,         # J layout_consistency is empty: both tables agree
    },
    # I:95 EINMALIG only for secure-storage, whose position is fixed for every H713; private and
    # Reserve0 have to be found by name in the device's own GPT (A0 section 5, issue #1 defect 2).
    "unique_regions": [
        ("secure-storage", 12288, 2048, "HDCP keys, WLAN/BT MAC addresses, serial number"),
        ("private", "by-name", 32768, "Android secure storage partition; J sys_partition private@5940224"),
        ("Reserve0", "by-name", 32768, "panel_config.ini and calibration; J sys_partition Reserve0@6013952"),
    ],
    # A0 section 5: partitions no stock image supplies (or supplies wrongly). "Reserve0*" matches the
    # single Reserve0 as well as the Reserve0_a/_b pair; media_data is /oem, where the vendor looks for
    # TSE overrides before it looks in the bootloader partition.
    "preserve_on_restore": ("private", "Reserve0*", "bootloader_a", "bootloader_b", "media_data"),
    "mips": {
        # A0 section 4: the U-Boot of the two ADT-3 images has no MIPS loader, and J
        # boot_resource_fat.has_mips_dir is false -- display.bin lives in the vendor partition only.
        "sources": ("vendor:/etc/display/mips",),
        "revisions": [                       # F, row "ADT-3 2024"; size/sha256 = J mips_files.display_bin
            {"size": 1252128, "sha256": "22a7df113fce3fa182926268de8c7551a107f0c3bc2932f0940bd58b8f424835",
             "name": "ADT-3 2024", "hdcp_wait_va": 0x4b13d1f0},
        ],
    },
    "panel": {                               # J panel_config[*].reserve0 -- vendor copy identical
        "declared_project_id": 0x30,         # ProjectID 48
        "width": 1920, "height": 1080, "dual_port": True,
        "htotal": 2200, "vtotal": 1125, "dclk_hz": 148500000,
        "hsync": 44, "vsync": 5, "hbp": 148, "vbp": 12,
        "hsync_pol": 1, "vsync_pol": 1,
        "pwm_channel": 5, "pwm_freq": 40000,
        "source": "Reserve0.fex:panel_config.ini",
    },
    "reference": None,                       # no device of this board has been extracted
    "expected": {
        # Same facts as "stock" above, in the shape the extractor's GERAETE[...]["erwartung"] uses, so
        # that identify can compare a device against this profile. Values from J, keys translated.
        "package_items": {"u-boot": 638976, "monitor": 66060, "scp": 176132, "optee": 267136, "dtb": 71168},
        "package_item_sha256": {
            "u-boot": "ec4df2f7e1847fc4436e615f63f1797b71f039c6e1b5cfb24527adf0f03291bb",
            "monitor": "95596d11aa6d10c0f3c8ef2c0d6fa01446be320c412decc201a5b547d6475ed7",
            "scp": "667da19bb74b3d376c80ce0502ce79fc708b8fe88c247b7f590488ae940d14bd",
            "optee": "c391dde39995529ab70b883ec4499a7f44954d439d1d6d0f9ccfa3ae01ea762a",
            "dtb": "681fe8f955e5dcc68a4f0446cfa6e55dce803592108c18994a21de8d798dad8f",
        },
        "uboot_version": "U-Boot 2018.05-00023-gea35390-dirty (Oct 25 2024 - 17:02:31 +0800)",
        "dtb_compatible": "allwinner,tv303", # J boot_package.dtb_compatible, first entry (as X:134)
        "arisc_version": "TV-303  ARISC  00.00.00.09 Date:Oct 25 2024",
        "vendor_size": 115826688,
        "libmspsound_sha256": None,          # not in J firmware_hints for this image
        "build_fingerprint": "ADT-3/adt3/adt3:10/QTT1.200116.002.B6/6245789:user/release-keys",
        "sunxi_version": "2024-10-25 17:15:54",
        "mips_database_sha256": "6d43b85a5880d34df0428f234c0c713ac1ca7ec28e551554137d967f60c380e4",
    },
    "board_dt": None,                        # no board DTS of ours yet (legacy/dts/sun50i-h713-hy310.dts
                                             # is the vendor DTS, not ours)
    "uboot_fragment": None,                  # boards/<id>/uboot.config does not exist yet
}
