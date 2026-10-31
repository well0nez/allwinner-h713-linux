"""HY320 -- board profile. Data only, no vendor bytes: numbers, hashes and strings.

Shape: installer/h713/profiles/SCHEMA.md. Source tags used in the comments below:
  D  = the owner's full eMMC dump of his own unit (7818182656 B, sha256 d09c3347..., taken over ADB on
       31.10.2026 in 64 MiB chunks, each compared against a device-side sha256 before it was kept)
  E  = h713-extract 0.4 over D (REPORT.txt/MANIFEST.json of 31.10.2026; exit 1 "unknown image", as expected)
  A  = the running stock system over ADB (getprop, /sys, dumpsys; 30.10.2026)
  T  = the stock device trees in D: U-Boot's (sunxi-package at LBA 24576, item dtb) and the kernel's
       (vendor_boot_a); they differ only in reserved-memory and two status lines
  F  = installer/tests/fixtures/firmware-revisions.json (display.bin revisions + HDCP wait site)
"""

PROFILE = {
    "id": "hy320",
    "name": "HY320",
    "description": "MagCubic HY320 -- Allwinner H713, ADT-3 vendor build 6245789 with an Android 11 system, "
                   "1920x1080 dual-port panel (project 0x30); one unit, dumped in full by its owner",
    # D/E: read in full, nothing of ours has run on it yet. Below "verified": TEST images for its owner
    # only (boards/README.md honesty rule, doku/121 section 5).
    "status": "partial",
    "verified_by": None,
    "soc": "H713 (sun50iw12)",               # T: compatible "allwinner,tv303", "arm,sun50iw12p1"
    "stock": {
        # A: ro.build.version.release 11, ro.product.cpu.abi armeabi-v7a, uname 5.4.99 armv7l; the
        # system fingerprint is ADT-3 :11/RP1A.201005.006/eng.projector.20241024.162050, the vendor
        # partition's (what identify reads) ADT-3 :10 build 6245789.
        "android": "11 system on an ADT-3 Android 10 vendor (32-bit, ARMv7 kernel 5.4.99)",
        "sunxi_version": None,               # a device does not carry it
        "build_fingerprint": "ADT-3/adt3/adt3:10/QTT1.200116.002.B6/6245789:user/release-keys",   # E
        # E features.uboot_version / arisc_version, cut before " Allwinner Technology" resp. " Time:".
        "uboot_version": "U-Boot 2018.05-00018-gd7a124a-dirty (Apr 19 2024 - 17:05:37 +0800)",
        "arisc_version": "TV-303  ARISC  00.00.00.09 Date:Apr 19 2024",
        "package_items": {                   # E: sunxi-package at LBA 24576, checksum ok
            "u-boot":  (622592, "82a06309fcfadf430e940651d4cff24a5e3133410ce21e93f602d851c5f2836e"),
            "monitor": ( 65996, "2dc43c309aeadf010353ac4fda0b91367eb25e9694cadbf6277874fb92be5e43"),
            "scp":     (176132, "6e06b1177f1318f9ada8d3a4d4a9f97cbcbff927add596092bf9e0ec1dd8c4bf"),
            "optee":   (267136, "c391dde39995529ab70b883ec4499a7f44954d439d1d6d0f9ccfa3ae01ea762a"),
            "dtb":     ( 71168, "21abff74dd91a8aa72d7ee4f817c6256381cb26314aef77b4e7ef57f0f78ea50"),
        },
        "vendor_size": 115204096,            # E
        # The fingerprint and the MIPS database are the ADT-3 family's (shared with the HY300 T08 and
        # HY350 images and the HY300 Pro), so they are not strong; the boot package hashes and the two
        # version strings are.
        "strong_features": ("scp_sha256", "uboot_sha256", "dtb_sha256", "uboot_version",
                            "arisc_version"),
    },
    "dram": {                                # D: the 24 words of the vendor boot0 at LBA 16, +0x38
        "clk": 792, "type": 3, "zq": 0x7b7bfb, "odt_en": 1,
        "para1": 0x10f4, "para2": 0,
        "mr0": 0x1c70, "mr1": 0x40, "mr2": 0x18, "mr3": 0,
        "tpr0": 0x4a2195, "tpr1": 0x2423190, "tpr2": 0x8b061, "tpr3": 0xb4787896,
        "tpr4": 0, "tpr5": 0x48484848, "tpr6": 0x48, "tpr7": 0x1620121e,
        "tpr8": 0, "tpr9": 0, "tpr10": 0, "tpr11": 0x44440000,
        "tpr12": 0x5555, "tpr13": 0x34010100,
        # The whole block equals the HY350 image's word for word. The second boot0 copy at LBA 256 of
        # the same eMMC differs in exactly para2 0x04000000 and tpr13 0xb4016103 -- the pair every
        # working base defconfig in the fork runs; LBA 16 carries the pair a vendor image carries, as
        # the HY310's own LBA 16 does (docs/tools/h713-probe.md, "About the DRAM block").
        "source": "the owner's eMMC dump, vendor boot0 at LBA 16 (LBA 256: para2 0x04000000, tpr13 0xb4016103)",
    },
    "layout": {
        "disk_sectors": 15269888,            # D: GPT, /sys/block/mmcblk0/size on the unit (A)
        "first_usable": 73728,
        "entries": 25,
        # D: name, start LBA, sectors -- the device's own GPT. The HY350's table with a larger super
        # (6291456 sectors instead of 5242880), so everything from misc on sits 1048576 sectors later.
        "partitions": [
            ("bootloader_a",      73728,   65536, None), ("bootloader_b",     139264,   65536, None),
            ("env_a",            204800,     512, None), ("env_b",            205312,     512, None),
            ("boot_a",           205824,  131072, None), ("boot_b",           336896,  131072, None),
            ("vendor_boot_a",    467968,   65536, None), ("vendor_boot_b",    533504,   65536, None),
            ("super",            599040, 6291456, None), ("misc",            6890496,   32768, None),
            ("vbmeta_a",        6923264,     256, None), ("vbmeta_b",        6923520,     256, None),
            ("vbmeta_system_a", 6923776,     128, None), ("vbmeta_system_b", 6923904,     128, None),
            ("vbmeta_vendor_a", 6924032,     128, None), ("vbmeta_vendor_b", 6924160,     128, None),
            ("frp",             6924288,    1024, None), ("empty",           6925312,   30720, None),
            ("metadata",        6956032,   32768, None), ("private",         6988800,   32768, None),
            ("dtbo_a",          7021568,    4096, None), ("dtbo_b",          7025664,    4096, None),
            ("media_data",      7029760,   32768, None), ("Reserve0",        7062528,   32768, None),
            ("UDISK",           7095296, 8174559, None),
        ],
        # D: eGON.BT0 at LBA 16 and 256 (the two copies differ in para2/tpr13, see "dram"), a
        # sunxi-package at LBA 24576 and 32800 (the two copies are not byte-identical).
        "raw": [("boot0_sdcard.fex", 16), ("boot0_sdcard.fex", 256),
                ("boot_package.fex", 24576), ("boot_package.fex", 32800)],
        "sunxi_gpt_disagrees": None,         # no sys_partition.fex of this firmware here
    },
    # secure-storage is fixed for every H713; private and Reserve0 are found by name in the device's
    # own GPT (their LBAs here are the expectation, from D).
    "unique_regions": [
        ("secure-storage", 12288, 2048, "HDCP keys, WLAN/BT MAC addresses, serial number"),
        ("private", "by-name", 32768, "Android secure storage partition; D private@6988800"),
        ("Reserve0", "by-name", 32768, "panel_config.ini and calibration; D Reserve0@7062528 (single)"),
    ],
    "preserve_on_restore": ("private", "Reserve0*", "bootloader_a", "bootloader_b", "media_data"),
    "mips": {
        # D/E: bootloader_a/_b are FAT16 without a mips/ directory (boot logo, fonts, battery
        # pictures only); the 19 display files live in the vendor partition only, as on the HY350.
        "sources": ("vendor:/etc/display/mips",),
        "revisions": [                       # E, F row "ADT-3 2024": the HY350's and HY300 T08's image
            {"size": 1252128, "sha256": "22a7df113fce3fa182926268de8c7551a107f0c3bc2932f0940bd58b8f424835",
             "name": "ADT-3 2024", "hdcp_wait_va": 0x4b13d1f0},   # the fork's h713_mips_fw_revs[] row
        ],
    },
    "panel": {                               # D: Reserve0 panel_config.ini (= vendor:/etc/tvconfig copy, E)
        "declared_project_id": 0x30,         # ProjectID 48
        "width": 1920, "height": 1080, "dual_port": True,
        # The HY350's raster (2200x1125) with this board's own clock and sync widths: PanelDCLK
        # 164000000 with min = max, PanelHsync 2, PanelVsync 8, HBP 148, VBP 12, PanelInvHSync 2.
        "htotal": 2200, "vtotal": 1125, "dclk_hz": 164000000,
        "hsync": 2, "vsync": 8, "hbp": 148, "vbp": 12,
        "hsync_pol": 1, "vsync_pol": 1,
        "pwm_channel": 5, "pwm_freq": 40000,   # [PWMSetting]: polarity 1, vs_lock 1, duty 1..100, default 50
        "source": "Reserve0:panel_config.ini of the owner's unit",
    },
    "reference": None,                       # no extraction of this board is checked into a reference
    "expected": {                            # E features: the identity row of the device itself
        "package_items": {"u-boot": 622592, "monitor": 65996, "scp": 176132, "optee": 267136, "dtb": 71168},
        "package_item_sha256": {
            "u-boot": "82a06309fcfadf430e940651d4cff24a5e3133410ce21e93f602d851c5f2836e",
            "monitor": "2dc43c309aeadf010353ac4fda0b91367eb25e9694cadbf6277874fb92be5e43",
            "scp": "6e06b1177f1318f9ada8d3a4d4a9f97cbcbff927add596092bf9e0ec1dd8c4bf",
            "optee": "c391dde39995529ab70b883ec4499a7f44954d439d1d6d0f9ccfa3ae01ea762a",
            "dtb": "21abff74dd91a8aa72d7ee4f817c6256381cb26314aef77b4e7ef57f0f78ea50",
        },
        "uboot_version": "U-Boot 2018.05-00018-gd7a124a-dirty (Apr 19 2024 - 17:05:37 +0800)",
        "dtb_compatible": "allwinner,tv303",
        "arisc_version": "TV-303  ARISC  00.00.00.09 Date:Apr 19 2024",
        "vendor_size": 115204096,
        "libmspsound_sha256": "c6e9cffcb6af8df7cd0aa544dd69f4ff12f0473ad423d8008e1c11ae45423db6",
        "build_fingerprint": "ADT-3/adt3/adt3:10/QTT1.200116.002.B6/6245789:user/release-keys",
        "sunxi_version": None,               # a device does not carry it
        "mips_database_sha256": "6d43b85a5880d34df0428f234c0c713ac1ca7ec28e551554137d967f60c380e4",
    },
    "board_dt": "sun50i-h713-hy320",         # boards/hy320/board.env KERNEL_DTB (TEST image)
    "uboot_board": "hy320",                  # boards/hy320/board.env UBOOT_BOARD: base hy320_defconfig
}
