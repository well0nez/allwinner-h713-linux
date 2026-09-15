"""HY300 Pro -- board profile. Data only, no vendor bytes: numbers, hashes and strings.

Shape: installer/h713/profiles/SCHEMA.md. Source tags used in the comments below:
  P  = analyse/issues/issue-1-hy300pro-20260913.md and doku/120-plan-hy300pro.md section 1
  Q  = issue #1, the owner's h713_probe run and dd of his dump (comment of 2026-09-14 16:25 UTC)
  A0 = docs/subsystems/mips.md ("vendor boot path") (what the vendor U-Boot loads, and from where)
  F  = installer/tests/fixtures/firmware-revisions.json (display.bin revisions + HDCP wait site, package A5)
  I  = analyse/release/arbeit/r0-fel/hy310-install.py (installer constants, lines 42-105)
"""

PROFILE = {
    "id": "hy300_pro",
    "name": "HY300 Pro",
    "description": "HY300 Pro -- reported in issue #1 (13.09.2026); no image, no dump on this host",
    # P: the owner ran the installer with --nur-abzug and h713-extract over the dump; nothing was
    # written. Most of the profile is still unknown, so it can never produce an image (doku/121 sec. 5).
    "status": "partial",
    "verified_by": None,
    "soc": "H713 (sun50iw12)",               # P: our installer U-Boot ran on it (FEL id 0x1860)
    "stock": {
        "android": "10 (32-bit, ARMv7 kernel 5.4.99)",   # doku/120 section 1
        "sunxi_version": None,               # not quoted in the issue
        "build_fingerprint": None,           # P: ADT-3 family, build 6245789 -- exact string never posted
        "uboot_version": None,
        "arisc_version": None,
        "package_items": None,               # no dump of the boot package was posted
        "vendor_size": None,
        # Nothing known about this board pins it down: its display.bin digest is unique but is not one
        # of the identification features (X:178), and the ADT-3 fingerprint it shares with two images.
        "strong_features": (),
    },
    "dram": {                                # Q: the 24 words of his vendor boot0 at LBA 16, read by the
        "clk": 636, "type": 3, "zq": 0x7b7bfb, "odt_en": 1,   # probe AND by dd from his full dump (identical)
        "para1": 0x10f4, "para2": 0x04000000,
        "mr0": 0x1c70, "mr1": 0x40, "mr2": 0x18, "mr3": 0,
        "tpr0": 0x482151, "tpr1": 0x1b1a94d, "tpr2": 0x7004e, "tpr3": 0xb4787896,
        "tpr4": 0, "tpr5": 0x48484848, "tpr6": 0x48, "tpr7": 0x1620121e,
        "tpr8": 0, "tpr9": 0, "tpr10": 0, "tpr11": 0x44440000,
        "tpr12": 0x5555, "tpr13": 0xb4016103,
        # para2/tpr13 are the flashed-in values here (his boot0 comes off the eMMC, not out of an image);
        # tpr11/tpr12 are the HY350's, not the HY310's (0x44340000/0x6666) -- per-board PHY tuning.
        "source": "issue #1, probe run of 2026-09-14 (h713_probe, vendor boot0 at LBA 16) and his dd of the dump",
    },
    "layout": {
        "disk_sectors": 15269888,            # P: same eMMC size as the HY310, 7.28 GiB (I:45)
        "first_usable": 73728,               # Q: first entry starts there, as on every H713 seen
        "entries": 25,                       # Q: his probe's "partitions (mmc 1)" list, 25 entries
        # Q: name, start LBA, sectors -- the GPT of his device as the probe printed it; no download
        # file names (there is no sys_partition.fex of his firmware here).
        "partitions": [
            ("bootloader_a",      73728,   65536, None), ("bootloader_b",     139264,   65536, None),
            ("env_a",            204800,     512, None), ("env_b",            205312,     512, None),
            ("boot_a",           205824,  131072, None), ("boot_b",           336896,  131072, None),
            ("vendor_boot_a",    467968,   65536, None), ("vendor_boot_b",    533504,   65536, None),
            ("super",            599040, 4194304, None), ("misc",            4793344,   32768, None),
            ("vbmeta_a",        4826112,     256, None), ("vbmeta_b",        4826368,     256, None),
            ("vbmeta_system_a", 4826624,     128, None), ("vbmeta_system_b", 4826752,     128, None),
            ("vbmeta_vendor_a", 4826880,     128, None), ("vbmeta_vendor_b", 4827008,     128, None),
            ("frp",             4827136,    1024, None), ("empty",           4828160,   30720, None),
            ("metadata",        4858880,   32768, None), ("private",         4891648,   32768, None),
            ("dtbo_a",          4924416,    4096, None), ("dtbo_b",          4928512,    4096, None),
            ("media_data",      4932608,  425984, None), ("Reserve0",        5358592,   32768, None),
            ("UDISK",           5391360, 9878495, None),
        ],
        # P: his UART log -- two eGON.BT0 copies and two sunxi-package copies, as on the HY310 (I:1652).
        "raw": [("boot0_sdcard.fex", 16), ("boot0_sdcard.fex", 256),
                ("boot_package.fex", 24576), ("boot_package.fex", 32800)],
        "sunxi_gpt_disagrees": None,         # unknown: no sys_partition.fex of this device
    },
    # P defect 2: his GPT has a single Reserve0@5358592+32768 and media_data@4932608+425984 -- the
    # HY310 constants pointed the small dump into his UDISK. secure-storage is fixed for every H713.
    "unique_regions": [
        ("secure-storage", 12288, 2048, "HDCP keys, WLAN/BT MAC addresses, serial number"),
        ("private", 4891648, 32768, "Android secure storage partition (Q: his GPT)"),
        ("Reserve0", 5358592, 32768, "panel_config.ini and calibration; single, no a/b pair"),
    ],
    # A0 section 5: partitions no stock image supplies (or supplies wrongly). "Reserve0*" matches the
    # single Reserve0 as well as the Reserve0_a/_b pair; media_data is /oem, where the vendor looks for
    # TSE overrides before it looks in the bootloader partition.
    "preserve_on_restore": ("private", "Reserve0*", "bootloader_a", "bootloader_b", "media_data"),
    "mips": {
        # A0 section 4: this board runs the HY310-style U-Boot (the log lines it prints exist only in
        # that build) and carries mips/ with 19 files in both bootloader slots.
        "sources": ("bootloader_b", "bootloader_a", "vendor:/etc/display/mips"),
        "revisions": [                       # F, row "HY300 Pro" (size and sha256 from the owner)
            {"size": 1253136, "sha256": "cf9649bcc84a111ce590fc7acde723c25557fd2332abbb9fd10225905aae13a2",
             "name": "HY300 Pro", "hdcp_wait_va": 0x4b13d1b0},   # Q: found by the probe on his device
        ],
    },
    "panel": {
        # P: "Project id:0x34 version:24-5-7-19" in his UART log. The panel itself is unknown -- the
        # stock system renders 1080p, while the other 0x34 board known to us is 1280x720 (doku/120 s. 1).
        "declared_project_id": 0x34,
        "width": None, "height": None, "dual_port": None,
        "htotal": None, "vtotal": None, "dclk_hz": None,
        "hsync": None, "vsync": None, "hbp": None, "vbp": None,
        "hsync_pol": None, "vsync_pol": None,
        "pwm_channel": None, "pwm_freq": None,
        # Q: his probe lists 13 ProjectID descriptors (0x01..0x35, 0x34 among them); he believes the panel
        # is 720p like the HY200's. Unmeasured: the values stay None until a panel_config.ini or a
        # measurement is posted (the v0.6-beta probe reads the ini off his Reserve0 and prints the id).
        "source": "issue #1 UART log and probe run of 2026-09-14, project id only; panel not measured",
    },
    "reference": None,                       # his extraction output was not posted file by file
    "expected": None,                        # nothing to compare a device against yet
    "board_dt": None,                        # no device tree of ours has booted on this board
                                             # (boards/<id>/board.env leaves KERNEL_DTB empty)
    "uboot_board": None,                     # no U-Boot base defconfig of ours for this board
}
