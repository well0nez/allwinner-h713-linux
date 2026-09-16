# -*- coding: utf-8 -*-
"""Layout v4 of the HY310/H713 eMMC as data (doku/109 §2).

Everything the image builder and the installer have to agree on: the partition
table, the three pieces of the image, the locked range in the middle, and the
list of files that do not travel with the image because they belong to the
manufacturer -- the installer copies them out of the user's own device.
Numbers only -- who writes them where is in `h713.mkimage` and `h713.install`.

Moved from hy310-mkimage.py (M:77-204, M:261-293), stage 1 (doku/121).
Layout v4 (16.09.2026, plan/briefs/P-layout-v4.md) dropped the placeholders:
no file in this list has a size any more, because none of them is written into
the image at a fixed offset. The image carries the two ext4 file systems with
the target DIRECTORIES only; `h713-install` mounts them and copies the files in
with their real length. What a file is called, where it goes, which group it
belongs to and whether a device may be without it is all that is left here.
"""

from __future__ import annotations

import posixpath
from collections import namedtuple

# The locked range. Identical to LOCK_FIRST/LOCK_LAST in h713.blockdev --
# the two values belong together and are checked here.
from h713.blockdev import LOCK_FIRST, LOCK_LAST

# ---------------------------------------------------------------- Layout v3/v4
# The partition layout is the one of v3 and does not change with v4.
# All numbers from doku/109 §2.1/§2.2, the GUIDs read off the device
# (10.09.2026, /dev/sda after the run from doku/109 §12) -- so that the image
# carries, byte for byte, the table the device is known to boot from.

from h713.gpt import GPT_ENTRIES as GPT_ENTRY_COUNT, GPT_ENTRY_SIZE, SECTOR   # 26 entries: more would reach into the SPL (M:81)

DISK_SECTORS = 15269888               # 7.28 GiB -- the eMMC of the HY310
FIRST_USABLE = 16                     # doku/109 §2.2: the raw areas as well
LAST_USABLE = DISK_SECTORS - 34
GPT_ARRAY_SECTORS = (GPT_ENTRY_COUNT * GPT_ENTRY_SIZE + SECTOR - 1) // SECTOR   # 7
TYPE_GUID = "0fc63daf-8483-4772-8e79-3d69d8477de4"    # Linux filesystem data
DISK_GUID = "ab6f3888-569a-4926-9668-80941dcb40bc"

# name, start-lba, sectors, unique-guid
PARTITIONS = [
    ("hy310-spl",    16,      64,       "cf5e1195-48e8-41bf-9394-1afdeff2bf01"),
    ("hy310-uboot",  2048,    10240,    "3c05da4e-39e8-4472-bd09-17f0433da668"),
    ("hy310-keys",   12288,   2048,     "404b1401-5772-4781-88ab-1b56c4682a97"),
    ("hy310-env",    14336,   2048,     "0a175557-ceb7-4ce5-b247-45e28a588dfd"),
    ("hy310-boot",   16384,   262144,   "f6d66c6c-2079-4e06-b550-4f37e6c5ab84"),
    ("hy310-rootfs", 278528,  14991327, "45f95906-692a-4dcf-94e5-10bf1672909d"),
]

LBA_SPL = 16
LBA_UBOOT = 2048
LBA_ENV = 14336
ENV_BYTES = 0x10000     # CONFIG_ENV_SIZE, one copy (109 §7)
LBA_BOOT = 16384
LBA_ROOTFS = 278528

# The three pieces of the image.
PART_A_LBA, PART_A_SECTORS = 0, LOCK_FIRST            # 0..12287, 6 MiB
PART_B_LBA = LOCK_LAST + 1                            # 14336 = 7 MiB
PART_C_LBA = DISK_SECTORS - 33                        # 15269855, 33 sectors
PART_C_SECTORS = 33

# ---------------------------------------------------------------- The files
# The groups, in the order the table and the README list them. The text is what
# a user is told the group is good for.
GROUPS = {
    "mips": "display firmware and tables",
    "logo": "boot logo",
    "wlan": "WLAN firmware",
    "pq": "picture presets",
    "firmware": "ARISC, EDID, MSP",
}

# name      the path below the output of h713-extract (its name in the dump)
# partition where it goes
# path      the absolute path inside that partition -- what U-Boot and the kernel see
# group     one of GROUPS
# optional  True: a firmware may be without it. The device then runs without that
#           group, and h713-install says so once per group instead of stopping.
#           Which ones are optional was h713.install's OPTIONAL_GROUPS/OPTIONAL_FILES
#           until v4; the truth is here now, so the table carries it and the
#           installer reads it out of the table.
File = namedtuple("File", "name partition path group optional")

FILES = [File(*row) for row in (
    # 19 display artefacts -> hy310-boot:/mips/
    ("boot/mips/database.TSE",           "hy310-boot",   "/mips/database.TSE",           "mips", False),
    ("boot/mips/display.bin",            "hy310-boot",   "/mips/display.bin",            "mips", False),
    ("boot/mips/display_cfg.xml",        "hy310-boot",   "/mips/display_cfg.xml",        "mips", False),
    ("boot/mips/LogoRegData.bin",        "hy310-boot",   "/mips/LogoRegData.bin",        "mips", False),
    ("boot/mips/pq_custom.TSE",          "hy310-boot",   "/mips/pq_custom.TSE",          "mips", False),
    ("boot/mips/ProjectID_0x0001.TSE",   "hy310-boot",   "/mips/ProjectID_0x0001.TSE",   "mips", False),
    ("boot/mips/ProjectID_0x0012.TSE",   "hy310-boot",   "/mips/ProjectID_0x0012.TSE",   "mips", False),
    ("boot/mips/ProjectID_0x0013.TSE",   "hy310-boot",   "/mips/ProjectID_0x0013.TSE",   "mips", False),
    ("boot/mips/ProjectID_0x0014.TSE",   "hy310-boot",   "/mips/ProjectID_0x0014.TSE",   "mips", False),
    ("boot/mips/ProjectID_0x0015.TSE",   "hy310-boot",   "/mips/ProjectID_0x0015.TSE",   "mips", False),
    ("boot/mips/ProjectID_0x0016.TSE",   "hy310-boot",   "/mips/ProjectID_0x0016.TSE",   "mips", False),
    ("boot/mips/ProjectID_0x0020.TSE",   "hy310-boot",   "/mips/ProjectID_0x0020.TSE",   "mips", False),
    ("boot/mips/ProjectID_0x0030.TSE",   "hy310-boot",   "/mips/ProjectID_0x0030.TSE",   "mips", False),
    ("boot/mips/ProjectID_0x0031.TSE",   "hy310-boot",   "/mips/ProjectID_0x0031.TSE",   "mips", False),
    ("boot/mips/ProjectID_0x0032.TSE",   "hy310-boot",   "/mips/ProjectID_0x0032.TSE",   "mips", False),
    ("boot/mips/ProjectID_0x0033.TSE",   "hy310-boot",   "/mips/ProjectID_0x0033.TSE",   "mips", False),
    ("boot/mips/ProjectID_0x0034.TSE",   "hy310-boot",   "/mips/ProjectID_0x0034.TSE",   "mips", False),
    ("boot/mips/ProjectID_0x0035.TSE",   "hy310-boot",   "/mips/ProjectID_0x0035.TSE",   "mips", False),
    ("boot/mips/projecttable.TSE",       "hy310-boot",   "/mips/projecttable.TSE",       "mips", False),
    # 1 boot logo -> hy310-boot:/ (the ROOT of the partition, where `h713_disp init <id> logo`
    # looks for it). Optional per file: a dump without a logo still installs, U-Boot then
    # boots without one (doku/40, last section). Every size is taken from the BMP header,
    # so a 720p logo is as good as a 1080p one.
    ("boot/bootlogo.bmp",                "hy310-boot",   "/bootlogo.bmp",                "logo", True),
    # 3 firmware files -> hy310-rootfs:/lib/firmware/
    ("lib/firmware/h713-arisc.bin",      "hy310-rootfs", "/lib/firmware/h713-arisc.bin",     "firmware", False),
    ("lib/firmware/h713/msp-patch.bin",  "hy310-rootfs", "/lib/firmware/h713/msp-patch.bin", "firmware", False),
    ("lib/firmware/hy310-edid.bin",      "hy310-rootfs", "/lib/firmware/hy310-edid.bin",     "firmware", False),
    # 8 PQ files -> hy310-rootfs:/etc/h713/tvconfig/. Optional: a firmware may ship only
    # part of the set (HY300 Pro, issue #1) -- h713-pq then has fewer presets, the picture
    # itself does not depend on them.
    ("pq/portmap.cfg",                   "hy310-rootfs", "/etc/h713/tvconfig/portmap.cfg",                  "pq", True),
    ("pq/pq_colortemp.ini",              "hy310-rootfs", "/etc/h713/tvconfig/pq_colortemp.ini",             "pq", True),
    ("pq/pq_factory_extern.ini",         "hy310-rootfs", "/etc/h713/tvconfig/pq_factory_extern.ini",        "pq", True),
    ("pq/pq_overscan_config.ini",        "hy310-rootfs", "/etc/h713/tvconfig/pq_overscan_config.ini",       "pq", True),
    ("pq/pq_picturemode.ini",            "hy310-rootfs", "/etc/h713/tvconfig/pq_picturemode.ini",           "pq", True),
    ("pq/pqcontrol_config_setting.xml",  "hy310-rootfs", "/etc/h713/tvconfig/pqcontrol_config_setting.xml", "pq", True),
    ("pq/pqcontrol_custom_setting.xml",  "hy310-rootfs", "/etc/h713/tvconfig/pqcontrol_custom_setting.xml", "pq", True),
    ("pq/tvpq.db",                       "hy310-rootfs", "/etc/h713/tvconfig/tvpq.db",                      "pq", True),
    # 13 WLAN firmware files -> hy310-rootfs:/lib/firmware/aic8800_fw/SDIO/aic8800D80/
    # (12.09.2026, the set that brought wlan0 up the same day.) The target path is the
    # driver's CONFIG_AIC_FW_PATH -- if it differs, fdrv silently loads nothing.
    # Optional: a firmware without the set means the device has no such chip, and
    # h713-wifi says the firmware is missing instead of loading the driver.
    ("lib/firmware/aic8800_fw/SDIO/aic8800D80/aic_userconfig_8800d80.txt",      "hy310-rootfs", "/lib/firmware/aic8800_fw/SDIO/aic8800D80/aic_userconfig_8800d80.txt",      "wlan", True),
    ("lib/firmware/aic8800_fw/SDIO/aic8800D80/fmacfw_8800d80.bin",              "hy310-rootfs", "/lib/firmware/aic8800_fw/SDIO/aic8800D80/fmacfw_8800d80.bin",              "wlan", True),
    ("lib/firmware/aic8800_fw/SDIO/aic8800D80/fmacfw_8800d80_h_u02.bin",        "hy310-rootfs", "/lib/firmware/aic8800_fw/SDIO/aic8800D80/fmacfw_8800d80_h_u02.bin",        "wlan", True),
    ("lib/firmware/aic8800_fw/SDIO/aic8800D80/fmacfw_8800d80_u02.bin",          "hy310-rootfs", "/lib/firmware/aic8800_fw/SDIO/aic8800D80/fmacfw_8800d80_u02.bin",          "wlan", True),
    ("lib/firmware/aic8800_fw/SDIO/aic8800D80/fw_adid_8800d80.bin",             "hy310-rootfs", "/lib/firmware/aic8800_fw/SDIO/aic8800D80/fw_adid_8800d80.bin",             "wlan", True),
    ("lib/firmware/aic8800_fw/SDIO/aic8800D80/fw_adid_8800d80_u02.bin",         "hy310-rootfs", "/lib/firmware/aic8800_fw/SDIO/aic8800D80/fw_adid_8800d80_u02.bin",         "wlan", True),
    ("lib/firmware/aic8800_fw/SDIO/aic8800D80/fw_patch_8800d80.bin",            "hy310-rootfs", "/lib/firmware/aic8800_fw/SDIO/aic8800D80/fw_patch_8800d80.bin",            "wlan", True),
    ("lib/firmware/aic8800_fw/SDIO/aic8800D80/fw_patch_8800d80_u02.bin",        "hy310-rootfs", "/lib/firmware/aic8800_fw/SDIO/aic8800D80/fw_patch_8800d80_u02.bin",        "wlan", True),
    ("lib/firmware/aic8800_fw/SDIO/aic8800D80/fw_patch_8800d80_u02_ext0.bin",   "hy310-rootfs", "/lib/firmware/aic8800_fw/SDIO/aic8800D80/fw_patch_8800d80_u02_ext0.bin",   "wlan", True),
    ("lib/firmware/aic8800_fw/SDIO/aic8800D80/fw_patch_table_8800d80.bin",      "hy310-rootfs", "/lib/firmware/aic8800_fw/SDIO/aic8800D80/fw_patch_table_8800d80.bin",      "wlan", True),
    ("lib/firmware/aic8800_fw/SDIO/aic8800D80/fw_patch_table_8800d80_u02.bin",  "hy310-rootfs", "/lib/firmware/aic8800_fw/SDIO/aic8800D80/fw_patch_table_8800d80_u02.bin",  "wlan", True),
    ("lib/firmware/aic8800_fw/SDIO/aic8800D80/lmacfw_rf_8800d80.bin",           "hy310-rootfs", "/lib/firmware/aic8800_fw/SDIO/aic8800D80/lmacfw_rf_8800d80.bin",           "wlan", True),
    ("lib/firmware/aic8800_fw/SDIO/aic8800D80/lmacfw_rf_8800d80_u02.bin",       "hy310-rootfs", "/lib/firmware/aic8800_fw/SDIO/aic8800D80/lmacfw_rf_8800d80_u02.bin",       "wlan", True),
)]

# What a copied-in file is owned by and how it is allowed to be read. The device
# runs everything in FILES as root; nothing in there is secret, nothing is a program.
FILE_OWNER = "root"
FILE_MODE = 0o644
DIRECTORY_MODE = 0o755

# The one file that does NOT come from the device but from the user: the public
# SSH key. Same mechanics, different source, and sshd's StrictModes decides the
# modes -- /root/.ssh 0700, the file 0600, both root. Without --ssh-key the file
# is never created, and only the serial console is left.
UserFile = namedtuple("UserFile", "name partition path mode owner directory_mode")

USER_FILES = [
    UserFile("authorized_keys", "hy310-rootfs", "/root/.ssh/authorized_keys", 0o600, "root", 0o700),
]

# Directories the ext4 trees carry with a fixed mode (path, mode) -- the user's
# ones out of USER_FILES, so there is one truth.
USER_DIRECTORIES = [(posixpath.dirname(u.path), u.directory_mode) for u in USER_FILES]

# What has to be right in the finished ext4, otherwise sshd will not take the
# key (StrictModes): owner root, and these modes. /etc/passwd is in the list
# because a tree unpacked as a user gives EVERY file uid 1000 -- that is how it
# was in image v0.5 on 11.09. (mkimage-inputs.sh did not run as root).
# (path, expected mode or None, uid, gid)
# v4: /root/.ssh/authorized_keys left this list -- the image does not carry the
# file any more, h713-install creates it from --ssh-key. The directory is here,
# and that is what sshd looks at before it reads a key.
ROOTFS_PERMISSIONS = [
    ("/etc/passwd", 0o644, 0, 0),
    ("/etc/shadow", 0o640, 0, 42),          # root:shadow
    ("/usr/sbin/unix_chkpwd", 0o2755, 0, 42),   # setgid shadow -- lost when unpacked as a user
    ("/root", 0o700, 0, 0),
    ("/root/.ssh", 0o700, 0, 0),
    ("/usr/local/sbin/h713-tv", 0o755, 0, 0),
]

KERNEL_FIT = "h713-kernel.fit"        # real, ours, and the only file the image brings


# ---------------------------------------------------------------- Directories

def target_directories(partition=None):
    """The directories the ext4 file systems have to carry, as (path, mode).

    Derived from FILES and USER_FILES: every directory a file goes into, and no
    other. The image ships them empty -- that is the whole difference to v3 --
    so that the installer creates files and never a directory, and so that
    `h713-mkimage check` can say from the finished ext4 alone whether a build is
    installable.

    Only the directory a file lies in is listed, not the ones above it: /root
    (0700) and /lib/firmware come out of the rootfs tar with their own modes and
    are none of our business.
    """
    out = {}
    for f in FILES:
        directory = posixpath.dirname(f.path)
        if directory and directory != "/":
            out.setdefault((f.partition, directory), DIRECTORY_MODE)
    for u in USER_FILES:
        out[(u.partition, posixpath.dirname(u.path))] = u.directory_mode
    return [(path, mode) for (part, path), mode in sorted(out.items())
            if partition is None or part == partition]
