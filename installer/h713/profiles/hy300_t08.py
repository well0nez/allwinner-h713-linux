"""HY300 T08 -- board profile. Data only, no vendor bytes: numbers, hashes and strings.

Shape: installer/h713/profiles/SCHEMA.md. Source tags used in the comments below:
  J  = installer/tests/fixtures/images/hy300-t08.json (board facts of the stock image, package A1)
  X  = analyse/release/arbeit/r2-extract/h713-extract (line numbers are lines 52-275)
  A0 = docs/subsystems/mips.md ("vendor boot path") (what the vendor U-Boot loads, and from where)
  F  = installer/tests/fixtures/firmware-revisions.json (display.bin revisions + HDCP wait site, package A5)
"""

PROFILE = {
    "id": "hy300_t08",
    "name": "HY300 T08",
    "description": "HY300 T08 -- Allwinner H713, ADT-3 Android 10 stock, OTA image 2024-04-19",
    # An image, but no device: nobody has run this profile against the hardware (doku/121 section 5).
    "status": "profile-only",
    "verified_by": None,
    "soc": "H713 (sun50iw12)",               # J boot_package.dtb_model / dtb_compatible
    "stock": {
        "android": "10",                     # J vendor_build_prop fingerprint ":10/" (ADT-3 build 6245789)
        "sunxi_version": "2024-04-19 20:28:23",   # J sunxi_version
        "build_fingerprint": "ADT-3/adt3/adt3:10/QTT1.200116.002.B6/6245789:user/release-keys",
        # J boot_package.uboot_version / arisc_version, cut before " Allwinner Technology" resp. " Time:".
        "uboot_version": "U-Boot 2018.05-00019-gbba611f (Apr 15 2024 - 11:04:17 +0000)",
        "arisc_version": "TV-303  ARISC  00.00.00.09 Date:Apr 19 2024",
        "package_items": {                   # J boot_package.items
            "u-boot":  ( 638976, "20171bc98d34929955ae3fae29be14ce3d430dd6d421c43ad4f81c2d47e6fe40"),
            "monitor": (  65996, "2dc43c309aeadf010353ac4fda0b91367eb25e9694cadbf6277874fb92be5e43"),
            "scp":     ( 176132, "e79e1b9ccedad3ac79cfcdaea8c4e46b5ce8d275b7601edbe3fb3b454a92c4aa"),
            "optee":   ( 267136, "c391dde39995529ab70b883ec4499a7f44954d439d1d6d0f9ccfa3ae01ea762a"),
            "dtb":     (  71168, "fb6f39ee4b0ba91a5bd47f06cf57110cd2d195a558a090213405282fe0c2d596"),
        },
        "vendor_size": 114851840,            # J super.partitions vendor_a
        # X:181 STARKE_MERKMALE minus build_fingerprint and mips_database_sha256: both
        # ADT-3 images carry the SAME fingerprint (J vendor_build_prop) and the SAME
        # database.TSE (J mips_files), so neither tells HY300 T08 and HY350 apart.
        "strong_features": ("scp_sha256", "uboot_sha256", "dtb_sha256", "uboot_version",
                            "arisc_version", "sunxi_version"),
    },
    "dram": {                                # J boot0.dram -- the 24 u32 at boot0_sdcard.fex+0x38
        "clk": 640, "type": 3, "zq": 0x7b7bfb, "odt_en": 1,
        "para1": 0x10f4, "para2": 0,
        "mr0": 0x1c70, "mr1": 0x40, "mr2": 0x18, "mr3": 0,
        "tpr0": 0x4a2195, "tpr1": 0x2423190, "tpr2": 0x8b061, "tpr3": 0xb4787896,
        "tpr4": 0, "tpr5": 0x48484848, "tpr6": 0x48, "tpr7": 0x1620121e,
        "tpr8": 0, "tpr9": 0, "tpr10": 0, "tpr11": 0x44440000,
        "tpr12": 0x5555, "tpr13": 0x34010100,
        "source": "boot0_sdcard.fex offset 0x38, HY300_T08_OTA_2024-04-19-2028.img",
    },
    "layout": {                              # J sys_partition[] -- the stock table of this image
        "disk_sectors": 15269888,            # J sunxi_gpt.header.last_usable 15269854 + 34
        "first_usable": 73728,               # J sunxi_gpt.header.first_usable
        "entries": 25,                       # len(J sys_partition) = J sunxi_gpt.header.entries
        # name, start LBA, sectors, downloadfile -- rows of J sys_partition in table order.
        "partitions": [
            ("bootloader_a",       73728,    65536, "boot-resource.fex"),
            ("bootloader_b",      139264,    65536, None),
            ("env_a",             204800,      512, "env.fex"),
            ("env_b",             205312,      512, None),
            ("boot_a",            205824,   131072, "boot.fex"),
            ("boot_b",            336896,   131072, None),
            ("vendor_boot_a",     467968,    65536, "vendor_boot.fex"),
            ("vendor_boot_b",     533504,    65536, None),
            ("super",             599040,  6291456, "super.fex"),
            ("misc",             6890496,    32768, "misc.fex"),
            ("vbmeta_a",         6923264,      256, "vbmeta.fex"),
            ("vbmeta_b",         6923520,      256, None),
            ("vbmeta_system_a",  6923776,      128, "vbmeta_system.fex"),
            ("vbmeta_system_b",  6923904,      128, None),
            ("vbmeta_vendor_a",  6924032,      128, "vbmeta_vendor.fex"),
            ("vbmeta_vendor_b",  6924160,      128, None),
            ("frp",              6924288,     1024, None),
            ("empty",            6925312,    30720, None),
            ("metadata",         6956032,    32768, None),
            ("private",          6988800,    32768, None),
            ("dtbo_a",           7021568,     4096, "dtbo.fex"),
            ("dtbo_b",           7025664,     4096, None),
            ("media_data",       7029760,    32768, None),
            ("Reserve0",         7062528,    32768, "Reserve0.fex"),
            ("UDISK",            7095296,        0, None),
        ],
        "raw": None,                         # the A1 facts record no raw targets for this image
        "sunxi_gpt_disagrees": None,         # J layout_consistency is empty: both tables agree
    },
    # I:95 EINMALIG only for secure-storage, whose position is fixed for every H713; private and
    # Reserve0 have to be found by name in the device's own GPT (A0 section 5, issue #1 defect 2).
    "unique_regions": [
        ("secure-storage", 12288, 2048, "HDCP keys, WLAN/BT MAC addresses, serial number"),
        ("private", "by-name", 32768, "Android secure storage partition; J sys_partition private@6988800"),
        ("Reserve0", "by-name", 32768, "panel_config.ini and calibration; J sys_partition Reserve0@7062528"),
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
        # Same facts as "stock" above, in the shape the extractor's GERAETE[...]["erwartung"] uses, so
        # that identify can compare a device against this profile. Values from J, keys translated.
        "package_items": {"u-boot": 638976, "monitor": 65996, "scp": 176132, "optee": 267136, "dtb": 71168},
        "package_item_sha256": {
            "u-boot": "20171bc98d34929955ae3fae29be14ce3d430dd6d421c43ad4f81c2d47e6fe40",
            "monitor": "2dc43c309aeadf010353ac4fda0b91367eb25e9694cadbf6277874fb92be5e43",
            "scp": "e79e1b9ccedad3ac79cfcdaea8c4e46b5ce8d275b7601edbe3fb3b454a92c4aa",
            "optee": "c391dde39995529ab70b883ec4499a7f44954d439d1d6d0f9ccfa3ae01ea762a",
            "dtb": "fb6f39ee4b0ba91a5bd47f06cf57110cd2d195a558a090213405282fe0c2d596",
        },
        "uboot_version": "U-Boot 2018.05-00019-gbba611f (Apr 15 2024 - 11:04:17 +0000)",
        "dtb_compatible": "allwinner,tv303", # J boot_package.dtb_compatible, first entry (as X:134)
        "arisc_version": "TV-303  ARISC  00.00.00.09 Date:Apr 19 2024",
        "vendor_size": 114851840,
        "libmspsound_sha256": None,          # not in J firmware_hints for this image
        "build_fingerprint": "ADT-3/adt3/adt3:10/QTT1.200116.002.B6/6245789:user/release-keys",
        "sunxi_version": "2024-04-19 20:28:23",
        "mips_database_sha256": "6d43b85a5880d34df0428f234c0c713ac1ca7ec28e551554137d967f60c380e4",
    },
    "board_dt": None,                        # no device tree of ours has booted on this board
                                             # (boards/<id>/board.env leaves KERNEL_DTB empty)
    "uboot_board": None,                     # no U-Boot base defconfig of ours for this board
}
