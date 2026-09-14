"""HY300 Pro -- board profile. Data only, no vendor bytes: numbers, hashes and strings.

Shape: umbau/plan/profil-schema.md. Source tags used in the comments below:
  P  = analyse/issues/issue-1-hy300pro-20260913.md and doku/120-plan-hy300pro.md section 1
  A0 = umbau/work/A0/REPORT.md, sections 4 and 5 (what the vendor U-Boot loads, and from where)
  F  = umbau/fixtures/firmware-revisions.json (display.bin revisions + HDCP wait site, package A5)
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
    "dram": {                                # P: UART log lines 127-133 (doku/120 section 1)
        "clk": 636, "type": 3, "zq": 0x7b7bfb, "odt_en": None,
        "para1": None, "para2": None,
        "mr0": None, "mr1": None, "mr2": None, "mr3": None,
        "tpr0": None, "tpr1": None, "tpr2": None, "tpr3": None,
        "tpr4": None, "tpr5": None, "tpr6": None, "tpr7": None,
        "tpr8": None, "tpr9": None, "tpr10": None, "tpr11": None,
        "tpr12": None, "tpr13": None,
        "source": "UART log in issue #1 (DRAM CLK = 636 MHz, Type = 3, ZQ 0x7b7bfb, SIZE = 1024 M)",
    },
    "layout": {
        "disk_sectors": 15269888,            # P: same eMMC size as the HY310, 7.28 GiB (I:45)
        "first_usable": None,                # not posted
        "entries": 25,                       # P: his GPT line, 25 entries
        "partitions": None,                  # only the two rows below were posted, not the whole table
        # P: his UART log -- two eGON.BT0 copies and two sunxi-package copies, as on the HY310 (I:1652).
        "raw": [("boot0_sdcard.fex", 16), ("boot0_sdcard.fex", 256),
                ("boot_package.fex", 24576), ("boot_package.fex", 32800)],
        "sunxi_gpt_disagrees": None,         # unknown: no sys_partition.fex of this device
    },
    # P defect 2: his GPT has a single Reserve0@5358592+32768 and media_data@4932608+425984 -- the
    # HY310 constants pointed the small dump into his UDISK. secure-storage is fixed for every H713.
    "unique_regions": [
        ("secure-storage", 12288, 2048, "HDCP keys, WLAN/BT MAC addresses, serial number"),
        ("private", "by-name", None, "Android secure storage partition; LBA not posted"),
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
             "name": "HY300 Pro", "hdcp_wait_va": None},
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
        "source": "issue #1 UART log, project id only; no panel_config.ini was posted",
    },
    "reference": None,                       # his extraction output was not posted file by file
    "expected": None,                        # nothing to compare a device against yet
    "board_dt": None,                        # no board DTS of ours yet (legacy/dts/sun50i-h713-hy310.dts
                                             # is the vendor DTS, not ours)
    "uboot_fragment": None,                  # boards/<id>/uboot.config does not exist yet
}
