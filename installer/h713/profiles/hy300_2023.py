"""HY300 (2023 firmware) -- board profile. Data only, no vendor bytes: numbers, hashes and strings.

The MagCubic HY300 in the classic case, 720p, with the HY350 family's DRAM block at 792 MHz and a 2023 ADT-3 firmware:
two units, two boot packages, one board. Variant `fw202306` is the issue #8 unit (GitHub `erfrizzera`: U-Boot and ARISC of
2023-06-25, the oldest ADT-3 firmware reported, a display.bin revision of its own); variant `fw202312` is the issue #11
unit (GitHub `Souks`: U-Boot of 2023-12-08, ARISC of 2023-12-27, the "ADT-3 2024-09" display.bin the LOSEI X9 carries too,
the T08 family's database.TSE). Not the HY300 Pro (issue #1: 636 MHz, firmware of 2024-12) and not the HY300 T08 (640 MHz,
2023-08/2023-11/2024-04). The silkscreen is unknown on both: neither owner has opened the unit.

Shape: installer/h713/profiles/SCHEMA.md ("variants"). Source tags used in the comments below:
  I  = the issue #8 owner's `h713-install identify` on the device (02.11.2026): the strong features, DRAM, panel id
  R  = his `h713-extract 0.4` report over his partition files (04.11.2026): display.bin, database, vendor, libmspsound
  H  = his read of the raw eMMC head, LBA 0..73727 (05.11.2026): boot0 at 16 and 256, the two packages, item sizes
  G  = his GPT and the two remaining item hashes, read with h713-extract over the same head (06.11.2026): the table
       row by row (= the T08's), monitor and optee (= the T08 unit's). The u-boot and dtb hashes of his first comment
       were mistyped and stood here until 10.11.2026; the installer refused his unit over them. Now: identify of 06.11.
  S  = the issue #11 owner's `h713-install identify` over FEL with the v0.97-beta G-EU installer U-Boot (11.11.2026):
       the strong features, DRAM (= I word for word), panel id, 15269888 sectors, 25 partitions
  E  = his `h713-extract 0.4` REPORT.txt over his full dump (11.11.2026): the five items with sizes and hashes,
       display.bin, database, vendor_a, libmspsound, 13 ProjectID files, the AIC8801 set
"""

_FINGERPRINT = "ADT-3/adt3/adt3:10/QTT1.200116.002.B6/6245789:user/release-keys"   # I, R, S: the ADT-3 family's string

# The fingerprint is the ADT-3 family's (T08, HY350, HY320, HY300 Pro); the three package hashes and the two strings
# tell a firmware apart. No sunxi_version on a device.
_STRONG = ("scp_sha256", "uboot_sha256", "dtb_sha256", "uboot_version", "arisc_version")

_FW2306_STOCK = {
    "android": "11 (userland UI_Veng.projector.20230625 on the ADT-3 vendor build 6245789)",   # R: his report
    "sunxi_version": None,               # a device does not carry it
    "build_fingerprint": _FINGERPRINT,
    # I: cut before " Allwinner Technology" resp. " Time:"
    "uboot_version": "U-Boot 2018.05-00005-g6d2f0a5-dirty (Jun 25 2023 - 15:41:51 +0800)",
    "arisc_version": "TV-303  ARISC  00.00.00.09 Date:Jun 25 2023",
    "package_items": {                   # H: the item sizes of the package at LBA 24576 (= 32800); G: the five hashes
        "u-boot":  ( 638976, "a8f2bfe87a1c4c46b628b908b978998c8c8c303c879a0f77ec3b02e8e94690e1"),
        "monitor": (  65996, "2dc43c309aeadf010353ac4fda0b91367eb25e9694cadbf6277874fb92be5e43"),
        "scp":     ( 176132, "50e8725e2309397c33e2f2a9beb363184e225cc7f693ab08ec8b0b7627280b81"),
        "optee":   ( 267136, "c391dde39995529ab70b883ec4499a7f44954d439d1d6d0f9ccfa3ae01ea762a"),
        "dtb":     (  69632, "a84bfbd574210aa0065e2fd4441ed5f3a35cffa966855aab0325d9e3bb102c7e"),
    },
    "vendor_size": 110755840,            # I, R: vendor_a
    "strong_features": _STRONG,
}

_FW2312_STOCK = {
    "android": "11 (userland UI_Veng_F.projector.20231227, H713-android11-v1.2rc3, on the ADT-3 vendor build 6245789)",   # S: adb
    "sunxi_version": None,               # a device does not carry it
    "build_fingerprint": _FINGERPRINT,   # S: ro.product.build.fingerprint (ro.build.fingerprint is the 2023-12 userland's, API 11)
    # S: cut before " Allwinner Technology" resp. " Time:"; E the same strings
    "uboot_version": "U-Boot 2018.05-00017-g1e43c6c (Dec 08 2023 - 11:58:22 +0000)",
    "arisc_version": "TV-303  ARISC  00.00.00.09 Date:Dec 27 2023",
    "package_items": {                   # E: the package at LBA 24576, every item with its size and hash
        "u-boot":  ( 638976, "96a07318f6b011531ca53ac1cba5227d78b072743be3a748851292443612fe79"),
        "monitor": (  65996, "2dc43c309aeadf010353ac4fda0b91367eb25e9694cadbf6277874fb92be5e43"),   # = fw202306's, = the T08's
        "scp":     ( 176132, "d818f98a3d3a4077ba5690b6175a0e449e1d1a4de4460684957233ebd797e355"),
        "optee":   ( 267136, "c391dde39995529ab70b883ec4499a7f44954d439d1d6d0f9ccfa3ae01ea762a"),   # = fw202306's, = the T08's
        "dtb":     (  71168, "68011339ae4f381fa302536aa1dc0981178513e8649ef2383117a1827c90fb8a"),   # its own tree, 1536 B over fw202306's
    },
    "vendor_size": 110202880,            # S, E: vendor_a (fw202306: 110755840; a vendor build of its own)
    "strong_features": _STRONG,
}

_DRAM = {                                # I: the 24 words of his boot0 at LBA 16 - the HY350 profile's block, with the
    "clk": 792, "type": 3, "zq": 0x7b7bfb, "odt_en": 1,   # pair the flashing tool writes (H: LBA 16 and 256 the same);
    "para1": 0x10f4, "para2": 0x04000000,                  # S: the issue #11 unit's 24 words are the same, word for word
    "mr0": 0x1c70, "mr1": 0x40, "mr2": 0x18, "mr3": 0,
    "tpr0": 0x4a2195, "tpr1": 0x2423190, "tpr2": 0x8b061, "tpr3": 0xb4787896,
    "tpr4": 0, "tpr5": 0x48484848, "tpr6": 0x48, "tpr7": 0x1620121e,
    "tpr8": 0, "tpr9": 0, "tpr10": 0, "tpr11": 0x44440000,
    "tpr12": 0x5555, "tpr13": 0xb4016103,
}

_LAYOUT = {
    "disk_sectors": 15269888,            # I: 15269888 sectors, 25 partitions - the ADT-3 family's eMMC and count
    "first_usable": 73728,
    "entries": 25,
    # G: his GPT row by row (header and table CRC ok, usable 73728..15269854): 25 entries, super 6 291 456 sectors,
    # a single Reserve0, UDISK 7095296+8174559 - the HY300 T08's table to the sector. Until 06.11.2026 this was
    # the T08's table as an assumption; the installer finds private and Reserve0 by name in the device's own GPT.
    "partitions": [
        ("bootloader_a",       73728,    65536, None), ("bootloader_b",      139264,    65536, None),
        ("env_a",             204800,      512, None), ("env_b",             205312,      512, None),
        ("boot_a",            205824,   131072, None), ("boot_b",            336896,   131072, None),
        ("vendor_boot_a",     467968,    65536, None), ("vendor_boot_b",     533504,    65536, None),
        ("super",             599040,  6291456, None), ("misc",             6890496,    32768, None),
        ("vbmeta_a",         6923264,      256, None), ("vbmeta_b",         6923520,      256, None),
        ("vbmeta_system_a",  6923776,      128, None), ("vbmeta_system_b",  6923904,      128, None),
        ("vbmeta_vendor_a",  6924032,      128, None), ("vbmeta_vendor_b",  6924160,      128, None),
        ("frp",              6924288,     1024, None), ("empty",            6925312,    30720, None),
        ("metadata",         6956032,    32768, None), ("private",          6988800,    32768, None),
        ("dtbo_a",           7021568,     4096, None), ("dtbo_b",           7025664,     4096, None),
        ("media_data",       7029760,    32768, None), ("Reserve0",         7062528,    32768, None),
        ("UDISK",            7095296,        0, None),
    ],
    "raw": None,
    "sunxi_gpt_disagrees": None,
}

_MIPS_SOURCES = ("vendor:/etc/display/mips",)   # R, E: bootloader_a/_b are FAT without mips/ (or no FAT), as on every ADT-3

_MIPS_2306 = {
    # R: 18 files in vendor:/etc/display/mips (no ProjectID_0x0035.TSE; install step [5] asks for the board's own since
    # PR #12), bootlogo.bmp not at the root either (R: "no boot logo in the source").
    "sources": _MIPS_SOURCES,
    "revisions": [
        # R: a sixth display.bin revision, 272 B smaller than "ADT-3 2024" (0x131b20); the HDCP wait site was found by
        # the search (h713.hdcpsite, base 0x4b100000), not pinned by a run. Row in h713_mips_fw_revs[] since the fork
        # branch of 05.11.2026, with the four firmware addresses at zero (readers refuse while they are zero).
        {"size": 1251856, "sha256": "1e3e518fe0a6a250a0011f2dd606cc145d0150b50fc843c587031e3a82af0e34",
         "name": "ADT-3 2023-06", "hdcp_wait_va": 0x4b13cf00},
    ],
}

_MIPS_2312 = {
    # E: 19 files in vendor:/etc/display/mips, all 13 ProjectID files (0x0035 included), no boot logo at the root.
    "sources": _MIPS_SOURCES,
    "revisions": [
        # E: the "ADT-3 2024-09" image (profiles.FIRMWARE_REVISIONS since the LOSEI X9, issue #3), 256 B over
        # fw202306's, 16 B short of "ADT-3 2024"; the wait site found by the search (file offset 0x3d140). Row in
        # h713_mips_fw_revs[] since the fork branch of 13.11.2026, the four firmware addresses at zero.
        {"size": 1252112, "sha256": "49f698af43ce714a70e04390a9a81015faa5b228dbffc2d73cc384722f0b307b",
         "name": "ADT-3 2024-09", "hdcp_wait_va": 0x4b13d140},
    ],
}


def _expected(stock, database):
    """The "expected" block identify() compares, built from a variant's "stock" (same values)."""
    items = stock["package_items"]
    return {"package_items": dict((n, size) for n, (size, _h) in items.items()),
            "package_item_sha256": dict((n, h) for n, (_s, h) in items.items()),
            "uboot_version": stock["uboot_version"],
            "dtb_compatible": "allwinner,tv303",   # I, S: "allwinner,tv303 arm,sun50iw12p1", first entry
            "arisc_version": stock["arisc_version"], "vendor_size": stock["vendor_size"],
            "libmspsound_sha256": "c6e9cffcb6af8df7cd0aa544dd69f4ff12f0473ad423d8008e1c11ae45423db6",   # R, E: the same on both (= the T08 unit's)
            "build_fingerprint": stock["build_fingerprint"],
            "sunxi_version": stock["sunxi_version"], "mips_database_sha256": database}


PROFILE = {
    "id": "hy300_2023",
    "name": "HY300 (2023 firmware)",
    "description": "MagCubic HY300 -- Allwinner H713, 2023 ADT-3 firmware, HY350-family DRAM at 792 MHz, 720p (0x34); "
                   "two firmwares: the issue #8 unit (2023-06) and the issue #11 unit (2023-12)",
    "soc": "H713 (sun50iw12)",               # I, S: dtb_compatible "allwinner,tv303 arm,sun50iw12p1"
    "unique_regions": [
        ("secure-storage", 12288, 2048, "HDCP keys, WLAN/BT MAC addresses, serial number"),
        ("private", "by-name", 32768, "Android secure storage partition; found by name in the device's GPT"),
        ("Reserve0", "by-name", 32768, "panel_config.ini and calibration; single Reserve0 (R: one panel_config.ini)"),
    ],
    "preserve_on_restore": ("private", "Reserve0*", "bootloader_a", "bootloader_b", "media_data"),
    "panel": {                               # I, S: project_id 0x34, panel 1280x720; R, E: panel_config.ini present (2513 B,
        "declared_project_id": 0x34,         # 7bffff88... on both units), its timings not posted - None until they are
        "width": 1280, "height": 720, "dual_port": False,
        "htotal": None, "vtotal": None, "dclk_hz": None,
        "hsync": None, "vsync": None, "hbp": None, "vbp": None,
        "hsync_pol": None, "vsync_pol": None,
        "pwm_channel": None, "pwm_freq": None,
        "source": "issues #8 and #11, identify (project id, size); panel_config.ini (same hash on both) not posted",
    },
    # boards/hy300-2023/board.env (05.11.2026): kernel 0350, the HY300 Pro's tree without the focus motor (both cases have
    # a manual focus ring); U-Boot base hy300_2023_defconfig (the HY350 family's block at 792 MHz). Neither has run on the board.
    "board_dt": "sun50i-h713-hy300-2023",
    "uboot_board": "hy300_2023",
    "variants": {
        "fw202306": {
            "name": "HY300 (2023 firmware, the issue #8 unit, boot package 2023-06)",
            "description": "MagCubic HY300 -- the issue #8 unit: boot package of 2023-06-25 (its own device tree and "
                           "display.bin revision) under the 2023-06 Android 11 userland",
            # A device, but no run: nothing of ours has run on it (doku/121 section 5). The owner booted our HY300 Pro
            # U-Boot from RAM for UMS (H), which trained his DRAM at 636 MHz - his measurement, not a run of an image.
            # Until 13.11.2026 this was the whole profile, "hy300_2023"; the TEST image hy300-2023-test1 carries that name.
            "status": "profile-only",
            "verified_by": None,
            "stock": _FW2306_STOCK,
            "dram": dict(_DRAM, source="issue #8, h713-install identify on the device (02.11.2026), boot0 at LBA 16"),
            "layout": _LAYOUT,
            "mips": _MIPS_2306,
            "reference": None,               # extracted by its owner, not here
            "expected": _expected(_FW2306_STOCK, "921c46537805b569c21d74523f7501e5c4ad96924d53b0b80495f50db58fb73b"),   # I, R: its own database.TSE
        },
        "fw202312": {
            "name": "HY300 (2023 firmware, the issue #11 unit, boot package 2023-12)",
            "description": "MagCubic HY300 -- the issue #11 unit: boot package of 2023-12 (U-Boot 2023-12-08, ARISC "
                           "2023-12-27, its own device tree) under the 2023-12-27 Android 11 userland, the \"ADT-3 "
                           "2024-09\" display.bin",
            # S: identify over FEL with the v0.97-beta G-EU installer U-Boot (636 MHz block), which trained his DRAM for
            # UMS; nothing of ours has booted on it. He has a full dump (dump --full), ADB, no serial console.
            "status": "profile-only",
            "verified_by": None,
            "stock": _FW2312_STOCK,
            "dram": dict(_DRAM, source="issue #11, h713-install identify over FEL (11.11.2026), boot0 at LBA 16: the issue #8 block"),
            "layout": _LAYOUT,               # S: 15269888 sectors, 25 partitions, Reserve0 and private at the LBAs of the table; E: GPT CRCs ok
            "mips": _MIPS_2312,
            "reference": None,               # read by its owner, not here
            "expected": _expected(_FW2312_STOCK, "6d43b85a5880d34df0428f234c0c713ac1ca7ec28e551554137d967f60c380e4"),   # E: database.TSE 251184 B, the T08 family's
        },
    },
}
