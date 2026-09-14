# Profile schema (profiles are data, one module per board; validate.py enforces this shape)

```python
PROFILE = {
    "id": "hy300_t08",                       # stable key, [a-z0-9_]
    "name": "HY300 T08",                     # human name
    "status": "profile-only",                # "verified" | "profile-only" | "partial"
    "verified_by": None,                     # owner report (issue/PR link) when status == "verified"
    "soc": "H713 (sun50iw12)",
    "stock": {
        "android": "10 (32-bit, kernel 5.4.99)",
        "sunxi_version": "2024-04-19 20:28:23",
        "build_fingerprint": "ADT-3/adt3/adt3:10/QTT1.200116.002.B6/6245789:user/release-keys",
        "uboot_version": "U-Boot 2018.05-00019-gbba611f (Apr 15 2024 - 11:04:17 +0000)",
        "arisc_version": "TV-303  ARISC  00.00.00.09 Date:Apr 19 2024",
        "package_items": {"u-boot": (638976, "20171bc9…"), "monitor": (65996, "2dc43c30…"),
                          "scp": (176132, "e79e1b9c…"), "optee": (267136, "c391dde3…"), "dtb": (71168, "fb6f39ee…")},
        "vendor_size": 114851840,
        "strong_features": ("scp_sha256", "uboot_sha256", "dtb_sha256", "uboot_version", "arisc_version",
                            "sunxi_version"),   # build_fingerprint is NOT strong for the ADT-3 family
    },
    "dram": {"clk": 640, "type": 3, "zq": 0x7b7bfb, "odt_en": 1, "para1": 0x10f4, "para2": 0,
             "mr0": 0x1c70, "mr1": 0x40, "mr2": 0x18, "mr3": 0, "tpr0": 0x4a2195, ..., "tpr13": 0x34010100,
             "source": "boot0_sdcard.fex offset 0x38, HY300_T08_OTA_2024-04-19-2028.img"},
    "layout": {                              # stock partition table, from sys_partition.fex
        "disk_sectors": 15269888,
        "first_usable": 73728,
        "entries": 25,
        "partitions": [("bootloader_a", 73728, 65536, "boot-resource.fex"), ("bootloader_b", 139264, 65536, None), ...],
        "raw": [("boot0_sdcard.fex", 16), ("boot0_sdcard.fex", 256), ("boot_package.fex", 24576), ("boot_package.fex", 32800)],
        "sunxi_gpt_disagrees": None,         # hy310: {"media_data": (557056, 524288)}
    },
    "unique_regions": [                      # exists only on this device; always dumped, never written
        ("secure-storage", 12288, 2048, "HDCP keys, MAC addresses, serial"),   # fixed for every H713
        ("private", "by-name", None, "Android secure storage partition"),
        ("Reserve0", "by-name", None, "panel_config.ini and calibration"),
    ],
    "preserve_on_restore": ("private", "Reserve0", "bootloader_b"),   # partitions the stock image does not supply
    "mips": {
        "sources": ("bootloader_b", "bootloader_a", "vendor:/etc/display/mips"),   # in order of trust
        "revisions": [
            {"size": 1252128, "sha256": "22a7df11…", "name": "ADT-3 2024-04/2024-10", "hdcp_wait_va": None},
        ],
    },
    "panel": {"declared_project_id": 0x34, "width": 1280, "height": 720, "dual_port": False,
              "htotal": 1360, "vtotal": 760, "dclk_hz": 62000000, "hsync": 20, "vsync": 2, "hbp": 40, "vbp": 20,
              "hsync_pol": 0, "vsync_pol": 0, "pwm_channel": 5, "pwm_freq": 40000,
              "source": "Reserve0.fex:panel_config.ini"},
    "board_dt": None,                        # kernel DTS name once one exists ("sun50i-h713-hy310")
    "uboot_fragment": None,                  # boards/<id>/uboot.config once one exists
}
```

Rules: every number carries a `source` or a comment naming the file it came from. `by-name` means "find it
in the device's GPT by partition name" (the LBA in the profile is only the expectation used to warn on
mismatch). Nothing in a profile is a vendor byte. A profile with `status != "verified"` never produces an
image; `h713-install install` refuses it with the sentence from doku/121 §5.
