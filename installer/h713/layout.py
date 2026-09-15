# -*- coding: utf-8 -*-
"""Layout v3 of the HY310/H713 eMMC as data (doku/109 §2).

Everything the image builder and the installer have to agree on: the partition
table, the three pieces of the image, the locked range in the middle, and the
list of placeholders that stand in for the files we may not redistribute.
Numbers only -- who writes them where is in `h713.mkimage` and `h713.install`.

Moved from hy310-mkimage.py (M:77-204, M:261-293), stage 1 (doku/121). Stage 3
changed no value here: the fill pattern of `pattern()` is image content, not a
printed line -- see the note there.
"""

from __future__ import annotations

# The locked range. Identical to LOCK_FIRST/LOCK_LAST in h713.blockdev --
# the two values belong together and are checked here.
from h713.blockdev import LOCK_FIRST, LOCK_LAST

# ---------------------------------------------------------------- Layout v3
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

# ---------------------------------------------------------------- Placeholders
# name (the file is called that in the output of h713-extract too)
#   -> (size in bytes, target partition, path in the file system)
# The sizes are measured on the HY310 (r2-extract/out-hy310, 10.09.2026) and
# written down here: the image is built once and then distributed.

PLACEHOLDERS = [
    # 19 display artefacts -> hy310-boot:/mips/
    ("boot/mips/database.TSE",           282464,  "hy310-boot",   "/mips/database.TSE"),
    ("boot/mips/display.bin",            1256216, "hy310-boot",   "/mips/display.bin"),
    ("boot/mips/display_cfg.xml",        4766,    "hy310-boot",   "/mips/display_cfg.xml"),
    ("boot/mips/LogoRegData.bin",        15652,   "hy310-boot",   "/mips/LogoRegData.bin"),
    ("boot/mips/pq_custom.TSE",          15016,   "hy310-boot",   "/mips/pq_custom.TSE"),
    ("boot/mips/ProjectID_0x0001.TSE",   19992,   "hy310-boot",   "/mips/ProjectID_0x0001.TSE"),
    ("boot/mips/ProjectID_0x0012.TSE",   48952,   "hy310-boot",   "/mips/ProjectID_0x0012.TSE"),
    ("boot/mips/ProjectID_0x0013.TSE",   47880,   "hy310-boot",   "/mips/ProjectID_0x0013.TSE"),
    ("boot/mips/ProjectID_0x0014.TSE",   47880,   "hy310-boot",   "/mips/ProjectID_0x0014.TSE"),
    ("boot/mips/ProjectID_0x0015.TSE",   47880,   "hy310-boot",   "/mips/ProjectID_0x0015.TSE"),
    ("boot/mips/ProjectID_0x0016.TSE",   47880,   "hy310-boot",   "/mips/ProjectID_0x0016.TSE"),
    ("boot/mips/ProjectID_0x0020.TSE",   19992,   "hy310-boot",   "/mips/ProjectID_0x0020.TSE"),
    ("boot/mips/ProjectID_0x0030.TSE",   19992,   "hy310-boot",   "/mips/ProjectID_0x0030.TSE"),
    ("boot/mips/ProjectID_0x0031.TSE",   19992,   "hy310-boot",   "/mips/ProjectID_0x0031.TSE"),
    ("boot/mips/ProjectID_0x0032.TSE",   19992,   "hy310-boot",   "/mips/ProjectID_0x0032.TSE"),
    ("boot/mips/ProjectID_0x0033.TSE",   19992,   "hy310-boot",   "/mips/ProjectID_0x0033.TSE"),
    ("boot/mips/ProjectID_0x0034.TSE",   17328,   "hy310-boot",   "/mips/ProjectID_0x0034.TSE"),
    ("boot/mips/ProjectID_0x0035.TSE",   19992,   "hy310-boot",   "/mips/ProjectID_0x0035.TSE"),
    ("boot/mips/projecttable.TSE",       1384,    "hy310-boot",   "/mips/projecttable.TSE"),
    # 1 boot logo -> hy310-boot:/ (the ROOT of the partition, where `h713_disp init <id> logo`
    # looks for it). Sized for a 1080p logo; a 720p one (2764854 B) fits and the rest of the
    # placeholder stays zero, which is harmless -- U-Boot takes every size from the BMP header,
    # not from the file length.
    ("boot/bootlogo.bmp",                6220854, "hy310-boot",   "/bootlogo.bmp"),
    # 3 firmware files -> hy310-rootfs:/lib/firmware/
    ("lib/firmware/h713-arisc.bin",      176132,  "hy310-rootfs", "/lib/firmware/h713-arisc.bin"),
    ("lib/firmware/h713/msp-patch.bin",  2896,    "hy310-rootfs", "/lib/firmware/h713/msp-patch.bin"),
    ("lib/firmware/hy310-edid.bin",      512,     "hy310-rootfs", "/lib/firmware/hy310-edid.bin"),
    # 8 PQ files -> hy310-rootfs:/etc/h713/tvconfig/
    ("pq/portmap.cfg",                   312,     "hy310-rootfs", "/etc/h713/tvconfig/portmap.cfg"),
    ("pq/pq_colortemp.ini",              865,     "hy310-rootfs", "/etc/h713/tvconfig/pq_colortemp.ini"),
    ("pq/pq_factory_extern.ini",         592528,  "hy310-rootfs", "/etc/h713/tvconfig/pq_factory_extern.ini"),
    ("pq/pq_overscan_config.ini",        10877,   "hy310-rootfs", "/etc/h713/tvconfig/pq_overscan_config.ini"),
    ("pq/pq_picturemode.ini",            10216,   "hy310-rootfs", "/etc/h713/tvconfig/pq_picturemode.ini"),
    ("pq/pqcontrol_config_setting.xml",  1055,    "hy310-rootfs", "/etc/h713/tvconfig/pqcontrol_config_setting.xml"),
    ("pq/pqcontrol_custom_setting.xml",  1326,    "hy310-rootfs", "/etc/h713/tvconfig/pqcontrol_custom_setting.xml"),
    ("pq/tvpq.db",                       36864,   "hy310-rootfs", "/etc/h713/tvconfig/tvpq.db"),
    # 13 WLAN firmware files -> hy310-rootfs:/lib/firmware/aic8800_fw/SDIO/aic8800D80/
    # (12.09.2026, sizes from h713-extract, profile hy310: byte-identical with
    # the set that brought wlan0 up the same day.) The target path is the
    # driver's CONFIG_AIC_FW_PATH -- if it differs, fdrv silently loads nothing.
    # OPTIONAL for the installer: if the whole set is missing from the dump the
    # device has no chip, and the placeholders stay zeroed (h713-wifi then says
    # "Firmware fehlt" instead of loading the driver).
    ("lib/firmware/aic8800_fw/SDIO/aic8800D80/aic_userconfig_8800d80.txt",      2807,   "hy310-rootfs", "/lib/firmware/aic8800_fw/SDIO/aic8800D80/aic_userconfig_8800d80.txt"),
    ("lib/firmware/aic8800_fw/SDIO/aic8800D80/fmacfw_8800d80.bin",              261352, "hy310-rootfs", "/lib/firmware/aic8800_fw/SDIO/aic8800D80/fmacfw_8800d80.bin"),
    ("lib/firmware/aic8800_fw/SDIO/aic8800D80/fmacfw_8800d80_h_u02.bin",        328912, "hy310-rootfs", "/lib/firmware/aic8800_fw/SDIO/aic8800D80/fmacfw_8800d80_h_u02.bin"),
    ("lib/firmware/aic8800_fw/SDIO/aic8800D80/fmacfw_8800d80_u02.bin",          328720, "hy310-rootfs", "/lib/firmware/aic8800_fw/SDIO/aic8800D80/fmacfw_8800d80_u02.bin"),
    ("lib/firmware/aic8800_fw/SDIO/aic8800D80/fw_adid_8800d80.bin",             1680,   "hy310-rootfs", "/lib/firmware/aic8800_fw/SDIO/aic8800D80/fw_adid_8800d80.bin"),
    ("lib/firmware/aic8800_fw/SDIO/aic8800D80/fw_adid_8800d80_u02.bin",         1708,   "hy310-rootfs", "/lib/firmware/aic8800_fw/SDIO/aic8800D80/fw_adid_8800d80_u02.bin"),
    ("lib/firmware/aic8800_fw/SDIO/aic8800D80/fw_patch_8800d80.bin",            8348,   "hy310-rootfs", "/lib/firmware/aic8800_fw/SDIO/aic8800D80/fw_patch_8800d80.bin"),
    ("lib/firmware/aic8800_fw/SDIO/aic8800D80/fw_patch_8800d80_u02.bin",        31592,  "hy310-rootfs", "/lib/firmware/aic8800_fw/SDIO/aic8800D80/fw_patch_8800d80_u02.bin"),
    ("lib/firmware/aic8800_fw/SDIO/aic8800D80/fw_patch_8800d80_u02_ext0.bin",   10956,  "hy310-rootfs", "/lib/firmware/aic8800_fw/SDIO/aic8800D80/fw_patch_8800d80_u02_ext0.bin"),
    ("lib/firmware/aic8800_fw/SDIO/aic8800D80/fw_patch_table_8800d80.bin",      648,    "hy310-rootfs", "/lib/firmware/aic8800_fw/SDIO/aic8800D80/fw_patch_table_8800d80.bin"),
    ("lib/firmware/aic8800_fw/SDIO/aic8800D80/fw_patch_table_8800d80_u02.bin",  23472,  "hy310-rootfs", "/lib/firmware/aic8800_fw/SDIO/aic8800D80/fw_patch_table_8800d80_u02.bin"),
    ("lib/firmware/aic8800_fw/SDIO/aic8800D80/lmacfw_rf_8800d80.bin",           302105, "hy310-rootfs", "/lib/firmware/aic8800_fw/SDIO/aic8800D80/lmacfw_rf_8800d80.bin"),
    ("lib/firmware/aic8800_fw/SDIO/aic8800D80/lmacfw_rf_8800d80_u02.bin",       256810, "hy310-rootfs", "/lib/firmware/aic8800_fw/SDIO/aic8800D80/lmacfw_rf_8800d80_u02.bin"),
]

# Placeholders that do NOT come from h713-extract but from the user:
# same mechanics (fixed size, offset out of the ext4), different source and
# different filling. h713-install lists them under "platzhalter_nutzer" in the
# table; an older installer does not know the key and leaves the file as it is
# -- and as it is, it is valid (line breaks only).
#   name -> (size, target partition, path, mode)
USER_PLACEHOLDERS = [
    ("authorized_keys", 4096, "hy310-rootfs", "/root/.ssh/authorized_keys", 0o600),
]
# Directories the tree creates for that, with a fixed mode (path, mode).
USER_DIRECTORIES = [
    ("/root/.ssh", 0o700),
]
# What has to be right in the finished ext4, otherwise sshd will not take the
# key (StrictModes): owner root, and these modes. /etc/passwd is in the list
# because a tree unpacked as a user gives EVERY file uid 1000 -- that is how it
# was in image v0.5 on 11.09. (mkimage-inputs.sh did not run as root).
# (path, expected mode or None, uid, gid)
ROOTFS_PERMISSIONS = [
    ("/etc/passwd", 0o644, 0, 0),
    ("/etc/shadow", 0o640, 0, 42),          # root:shadow
    ("/usr/sbin/unix_chkpwd", 0o2755, 0, 42),   # setgid shadow -- lost when unpacked as a user
    ("/root", 0o700, 0, 0),
    ("/root/.ssh", 0o700, 0, 0),
    ("/root/.ssh/authorized_keys", 0o600, 0, 0),
    ("/usr/local/sbin/h713-tv", 0o755, 0, 0),
]

KERNEL_FIT = "h713-kernel.fit"        # real, ours, not a placeholder


# ---------------------------------------------------------------- Filling

def pattern(name, length):
    """The content of an unfilled placeholder.

    Deliberately not a block of zeros: (1) in a hexdump you see at once that
    the file is not filled yet and which one it is, (2) for nothing but zeros
    mke2fs may create a hole (sparse) -- then there would be no physical
    blocks for the installer to write into.

    Stage 3 does NOT translate this string. It is not a printed line but the
    content of the image: it stands in every built image, its sha256 is in the
    table under "sha256_muster", and `h713-mkimage check` decides from it
    whether a placeholder is still unfilled. Translating it would make every
    image built before stage 3 read as "already filled". It goes when the
    release format changes (stage 4).
    """
    core = ("HY310-PLATZHALTER %s -- hy310-install fuellt das. " % name).encode("ascii", "replace")
    n = -(-length // len(core))
    return (core * n)[:length]


def is_user_placeholder(name):
    return any(name == n for n, _s, _t, _p, _m in USER_PLACEHOLDERS)


def filling(name, length):
    """The content of an unfilled placeholder, depending on its kind.

    Vendor files carry the pattern (see pattern()). authorized_keys consists
    of line breaks: sshd skips over empty lines, so the file is valid and
    empty whether an installer fills it or not. Zero bytes or the pattern
    would sit in authorized_keys as garbage. No block of zeros -- mke2fs -d
    would otherwise create a hole instead of a data block.
    """
    if is_user_placeholder(name):
        return b"\n" * length
    return pattern(name, length)
