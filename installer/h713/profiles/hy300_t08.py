"""HY300 T08 -- board profile. Data only, no vendor bytes: numbers, hashes and strings.

One board, three stock firmwares (SCHEMA.md, "variants"):
  ota20240419  the stock OTA image HY300_T08_OTA_2024-04-19-2028.img - U-Boot 2024-04-15, ARISC 2024-04-19
  unit202311   the first owner's unit (issue #7, 31.10./01.11.2026): an older boot package (U-Boot 2023-11-18,
               ARISC 2023-11-23, its own device tree) under a newer Android 11 userland (eng.projector.20240722);
               the vendor partition, its fingerprint and the display data are the OTA's byte for byte.
  fw20250221   the second owner's unit (issue #10, 05.11.2026): a boot package of 2023-08 (U-Boot 2023-08-08,
               ARISC 2023-08-12, its own device tree) under an Android 11 userland of 2025-02-21 (32-bit), the
               display data the OTA's, and an eMMC of 14 942 208 sectors (T22708) instead of 15 269 888.

Shape: installer/h713/profiles/SCHEMA.md. Source tags used in the comments below:
  J  = installer/tests/fixtures/images/hy300-t08.json (board facts of the stock image, package A1)
  R  = the owner's h713-extract 0.4 report over his full eMMC dump (issue #7, 31.10.2026) and his identify
       output; the device tree item of his boot package (dtb 7db0a4d3...) he attached on 01.11.2026
  X  = analyse/release/arbeit/r2-extract/h713-extract (line numbers are lines 52-275)
  A0 = docs/subsystems/mips.md ("vendor boot path") (what the vendor U-Boot loads, and from where)
  F  = installer/tests/fixtures/firmware-revisions.json (display.bin revisions + HDCP wait site, package A5)
  G  = the second owner's report (issue #10, 05.11.2026): `h713-install identify` over FEL with our T08 installer
       U-Boot (the drive came up with --device only: its size was unknown to find_drive), the boot0 block read from
       Android, his GPT, panel_config.ini, the modules; nothing of ours has run on it
"""

# J sys_partition[] -- the stock table of the OTA image; R: the owner's GPT has the same 25 entries with the single
# Reserve0 (his first report, 31.10.2026).
_PARTITIONS = [
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
]
_LAYOUT = {
    "disk_sectors": 15269888,            # J sunxi_gpt.header.last_usable 15269854 + 34; R: 7 818 182 656 B = the same
    "first_usable": 73728,               # J sunxi_gpt.header.first_usable
    "entries": 25,                       # len(J sys_partition) = J sunxi_gpt.header.entries; R: 25
    "partitions": _PARTITIONS,
    "raw": None,                         # the A1 facts record no raw targets for this image
    "sunxi_gpt_disagrees": None,         # J layout_consistency is empty: both tables agree
}
# G: the same 25 entries at the same LBAs on an eMMC of 14 942 208 sectors (7 650 410 496 B, eMMC T22708, the first
# H713 board seen below 15 269 888): UDISK 7095296+7846879 ends at the last usable sector. The size is in
# blockdev.SECTORS_KNOWN since 10.11.2026; an image for this variant is cut for it (mkimage.disk_sectors_for).
_LAYOUT_T22708 = dict(_LAYOUT, disk_sectors=14942208)
# A0 section 4: the U-Boot of the ADT-3 images has no MIPS loader, and J boot_resource_fat.has_mips_dir is
# false -- display.bin lives in the vendor partition only. R: the same on the owner's unit (bootlogo.bmp at the
# root of bootloader_a/_b, no mips/), and all 19 files byte for byte the OTA's.
_MIPS = {
    "sources": ("vendor:/etc/display/mips",),
    "revisions": [                       # F, row "ADT-3 2024"; size/sha256 = J mips_files.display_bin = R
        {"size": 1252128, "sha256": "22a7df113fce3fa182926268de8c7551a107f0c3bc2932f0940bd58b8f424835",
         "name": "ADT-3 2024", "hdcp_wait_va": 0x4b13d1f0},
    ],
}
# J boot0.dram -- the 24 u32 at boot0_sdcard.fex+0x38. R: the owner's boot0 at LBA 16 carries the very same
# block, para2/tpr13 in the unpatched image form as well (0 / 0x34010100); his LBA 256 copy is the HY350's
# 792 MHz block with the patched pair, which the BROM does not take while LBA 16 is valid (doku/90).
_DRAM = {
    "clk": 640, "type": 3, "zq": 0x7b7bfb, "odt_en": 1,
    "para1": 0x10f4, "para2": 0,
    "mr0": 0x1c70, "mr1": 0x40, "mr2": 0x18, "mr3": 0,
    "tpr0": 0x4a2195, "tpr1": 0x2423190, "tpr2": 0x8b061, "tpr3": 0xb4787896,
    "tpr4": 0, "tpr5": 0x48484848, "tpr6": 0x48, "tpr7": 0x1620121e,
    "tpr8": 0, "tpr9": 0, "tpr10": 0, "tpr11": 0x44440000,
    "tpr12": 0x5555, "tpr13": 0x34010100,
}
_FINGERPRINT = "ADT-3/adt3/adt3:10/QTT1.200116.002.B6/6245789:user/release-keys"
_DATABASE = "6d43b85a5880d34df0428f234c0c713ac1ca7ec28e551554137d967f60c380e4"   # J mips_files = R

_OTA_STOCK = {
    "android": "10",                     # J vendor_build_prop fingerprint ":10/" (ADT-3 build 6245789)
    "sunxi_version": "2024-04-19 20:28:23",   # J sunxi_version
    "build_fingerprint": _FINGERPRINT,
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
    # X:181 STARKE_MERKMALE minus build_fingerprint and mips_database_sha256: all ADT-3 images and units carry the
    # SAME fingerprint (J vendor_build_prop; R) and the SAME database.TSE, so neither tells HY300 T08 and HY350 apart,
    # nor the two T08 firmwares.
    "strong_features": ("scp_sha256", "uboot_sha256", "dtb_sha256", "uboot_version",
                        "arisc_version", "sunxi_version"),
}
# G: identify row. The three package hashes and the two strings are his; monitor and optee were not read (no
# h713-extract over the head yet). Item SIZES are ASSUMED from the family (u-boot 638976 and scp 176132 on every
# ADT-3 package seen; dtb 71168 as the 2023-11 and 2024-04 trees, the 2023-06 tree has 69632) until his
# h713-extract package line says otherwise; identify does not judge by sizes.
_FW2025_STOCK = {
    "android": "11 (userland eng.projector.20250221, 32-bit, kernel 5.4.99, on the ADT-3 vendor build 6245789)",   # G
    "sunxi_version": None,               # a device does not carry it
    "build_fingerprint": _FINGERPRINT,   # G: ro.product.build.fingerprint, the OTA's string (ro.build.fingerprint is the 2025 userland's)
    "uboot_version": "U-Boot 2018.05-00008-gc26a358 (Aug 08 2023 - 02:18:08 +0000)",
    "arisc_version": "TV-303  ARISC  00.00.00.09 Date:Aug 12 2023",
    "package_items": {
        "u-boot":  ( 638976, "f2ee7681c5e082a4f4cdb131699ecad7424eb4b9d01bcd7eca9d7b013cc3390f"),
        "scp":     ( 176132, "631e06bd4f1b009e28b8396076847089d5ad0d3fb31a0586566aa103c2d18a66"),
        "dtb":     (  71168, "e0ee997e54bde61be5078563a0172bde55502dea3c9f307923715d878bdfeb46"),
    },
    "vendor_size": 115920896,            # G: identify vendor_size (not the OTA's 114851840: a vendor build of its own)
    "strong_features": ("scp_sha256", "uboot_sha256", "dtb_sha256", "uboot_version", "arisc_version"),
}
_UNIT_STOCK = {
    "android": "11 (userland eng.projector.20240722 on the ADT-3 vendor build 6245789)",   # R: his first report
    "sunxi_version": None,               # a device does not carry it
    "build_fingerprint": _FINGERPRINT,   # R: build.prop ro.vendor.build.fingerprint, the OTA's string
    # R: package at LBA 24576 of his dump, cut as above
    "uboot_version": "U-Boot 2018.05-00014-gbbed928 (Nov 18 2023 - 11:30:38 +0000)",
    "arisc_version": "TV-303  ARISC  00.00.00.09 Date:Nov 23 2023",
    "package_items": {                   # R: the five items; monitor and optee are the OTA's
        "u-boot":  ( 638976, "b826243b7326e00782b514503dbf8c272d567185d673f6ea04263e18ed081170"),
        "monitor": (  65996, "2dc43c309aeadf010353ac4fda0b91367eb25e9694cadbf6277874fb92be5e43"),
        "scp":     ( 176132, "8cbc0706e5b864cf553a86533d5d399c9645043207439f69a6139fb5fa7c5d2e"),
        "optee":   ( 267136, "c391dde39995529ab70b883ec4499a7f44954d439d1d6d0f9ccfa3ae01ea762a"),
        "dtb":     (  71168, "7db0a4d3598878869367da3812b62b211769bd77414af6bd3d2ea66d4adc186f"),
    },
    "vendor_size": 114851840,            # R: vendor_a 114851840 B, the OTA's
    # No sunxi_version on a device; the three package hashes and the two strings tell this unit apart from the
    # OTA (monitor and optee are shared, so they are not among them).
    "strong_features": ("scp_sha256", "uboot_sha256", "dtb_sha256", "uboot_version", "arisc_version"),
}


def _expected(stock, libmspsound):
    """The "expected" block identify() compares, built from a variant's "stock" (same values)."""
    items = stock["package_items"]
    return {"package_items": dict((n, size) for n, (size, _h) in items.items()),
            "package_item_sha256": dict((n, h) for n, (_s, h) in items.items()),
            "uboot_version": stock["uboot_version"],
            "dtb_compatible": "allwinner,tv303",   # J boot_package.dtb_compatible, first entry (as X:134); R the same
            "arisc_version": stock["arisc_version"], "vendor_size": stock["vendor_size"],
            "libmspsound_sha256": libmspsound, "build_fingerprint": stock["build_fingerprint"],
            "sunxi_version": stock["sunxi_version"], "mips_database_sha256": _DATABASE}


PROFILE = {
    "id": "hy300_t08",
    "name": "HY300 T08",
    "description": "HY300 T08 -- Allwinner H713, ADT-3 Android stock (three firmwares: the 2024-04-19 OTA image, "
                   "the 2023-11 boot package of the issue #7 unit, the 2023-08 package of the issue #10 unit)",
    "soc": "H713 (sun50iw12)",               # J boot_package.dtb_model / dtb_compatible; R the same
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
    "panel": {                               # J panel_config[*].reserve0 -- vendor copy identical; R: 1280x720, 0x34
        "declared_project_id": 0x34,         # ProjectID 52
        "width": 1280, "height": 720, "dual_port": False,
        "htotal": 1360, "vtotal": 760, "dclk_hz": 62000000,
        "hsync": 20, "vsync": 2, "hbp": 40, "vbp": 20,
        "hsync_pol": 0, "vsync_pol": 0,
        "pwm_channel": 5, "pwm_freq": 40000,
        "source": "Reserve0.fex:panel_config.ini",
    },
    # boards/hy300-t08/board.env KERNEL_DTB / UBOOT_BOARD (03.11.2026): kernel 0349, the HY300 Pro's tree with the
    # "ADT-3 2024" firmware's elog and handoff words; U-Boot base hy300_t08_defconfig. Neither has run on the board.
    "board_dt": "sun50i-h713-hy300-t08",
    "uboot_board": "hy300_t08",
    "variants": {
        "ota20240419": {
            "name": "HY300 T08 (stock OTA 2024-04-19)",
            "description": "HY300 T08 -- the stock OTA image of 2024-04-19 (U-Boot 2024-04-15, ARISC 2024-04-19)",
            # An image, but no device with this boot package has been seen (doku/121 section 5).
            "status": "profile-only",
            "verified_by": None,
            "stock": _OTA_STOCK,
            "dram": dict(_DRAM, source="boot0_sdcard.fex offset 0x38, HY300_T08_OTA_2024-04-19-2028.img"),
            "layout": _LAYOUT,
            "mips": _MIPS,
            "reference": None,               # no device of this board has been extracted by us
            "expected": _expected(_OTA_STOCK, None),   # libmspsound is not in J firmware_hints
        },
        "unit202311": {
            "name": "HY300 T08 (the issue #7 unit, boot package 2023-11)",
            "description": "HY300 T08 -- the first owner's unit (issue #7): boot package of 2023-11 (U-Boot "
                           "2023-11-18, ARISC 2023-11-23, its own device tree) under the 2024-07 Android 11 userland",
            # The owner's full dump, identify and extract (31.10./01.11.2026); nothing of ours has run on it.
            # His unit was the reason this profile has variants: identify found no profile for it.
            "status": "profile-only",
            "verified_by": None,
            "stock": _UNIT_STOCK,
            "dram": dict(_DRAM, source="the owner's boot0 at LBA 16 (issue #7, 31.10.2026): the OTA's block"),
            "layout": _LAYOUT,
            "mips": _MIPS,
            "reference": None,               # extracted by its owner, not here
            # R: libmspsound.so c6e9cffc... (not the HY310's); database.TSE the OTA's.
            "expected": _expected(_UNIT_STOCK, "c6e9cffcb6af8df7cd0aa544dd69f4ff12f0473ad423d8008e1c11ae45423db6"),
        },
        "fw20250221": {
            "name": "HY300 T08 (the issue #10 unit, boot package 2023-08, eMMC 14 942 208 sectors)",
            "description": "HY300 T08 -- the second owner's unit (issue #10): boot package of 2023-08 (U-Boot "
                           "2023-08-08, ARISC 2023-08-12, its own device tree) under a 2025-02 Android 11 userland, "
                           "on an eMMC of 14 942 208 sectors",
            # G: identify over FEL with our T08 installer U-Boot (05.11.2026), which trained his DRAM with this
            # block; nothing of ours has booted on it. He has the stock IR remote, ADB and a dd of the whole eMMC.
            "status": "profile-only",
            "verified_by": None,
            "stock": _FW2025_STOCK,
            "dram": dict(_DRAM, source="the owner's boot0 at LBA 16 (issue #10, 05.11.2026): the OTA's block, para2 0, tpr13 0x34010100"),
            "layout": _LAYOUT_T22708,
            "mips": _MIPS,                   # G: display.bin 22a7df11..., database 6d43b85a..., the OTA's
            "reference": None,               # read by its owner, not here
            "expected": _expected(_FW2025_STOCK, None),   # libmspsound not reported
        },
    },
}
