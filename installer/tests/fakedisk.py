#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0
"""A fake eMMC the real tools accept: a sparse regular file of 15269888 sectors.

`Platte` opens its device with `os.open()` and takes the size from
`lseek(fd, 0, SEEK_END)` -- a regular file answers both exactly like a block
device, `eingehaengt()` finds nothing for a regular path, and O_EXCL without
O_CREAT is a no-op on a regular file.  So no monkeypatching is needed:
`hy310-install.py --device <file>` reads and writes this file.  ftruncate keeps
it sparse (~130 MiB on disk for the stock build, ~1 MiB for layout v3).

Regions a test must be able to call "untouched" -- misc, private, Reserve0 and
the locked block at LBA 12288..14335 -- are filled by `pattern()`: every sector
carries its own LBA and the region name in ASCII.  The vendor's own misc.fex and
Reserve0.fex are 99.98 % zeros and could not tell "untouched" from "zeroed".
"""

import collections
import hashlib
import os
import struct
import zlib

SECT = 512
DISK_SECTORS = 15269888                  # 7.28 GiB -- the eMMC of the HY310
GPT_BACKUP_SECTORS = 33
# Fixtures that may live in the repository (partition tables, environment, JSON facts) sit next to
# the tests. Vendor bytes (a stock bootloader partition, .fex files, the firmware images) never do:
# point H713_FIXTURES_LOCAL and H713_IMAGE_DIR at them, otherwise the tests that need them skip.
_HERE = os.path.dirname(os.path.abspath(__file__))
FIXTURES = os.environ.get("H713_FIXTURES", os.path.join(_HERE, "fixtures"))
FIXTURES_LOCAL = os.environ.get("H713_FIXTURES_LOCAL", os.path.join(_HERE, "fixtures-local"))
IMAGE_DIR = os.environ.get("H713_IMAGE_DIR", os.path.expanduser("~/Downloads"))

STOCK_GPT = os.path.join(FIXTURES, "device", "hy310-stock-gpt-primary-20260831.bin")
V3_GPT_PRIMARY = os.path.join(FIXTURES, "device", "hy310-layout-v3-gpt-primary-v0.5-beta.bin")
V3_GPT_BACKUP = os.path.join(FIXTURES, "device", "hy310-layout-v3-gpt-backup-v0.5-beta.bin")
V3_ENV = os.path.join(FIXTURES, "device", "hy310-uboot-env-20260913-release.bin")
STOCK_BOOTLOADER = os.path.join(FIXTURES_LOCAL, "device", "hy310-stock-bootloader_b-20260831.fat")
STOCK_ENV_A = os.path.join(FIXTURES_LOCAL, "device", "hy310-stock-env_a-20260831.bin")

IMAGES = {
    "hy310": os.path.join(IMAGE_DIR, "update.img"),
    "hy300-t08": os.path.join(IMAGE_DIR, "HY300_T08_OTA_2024-04-19-2028.img"),
    "hy350": os.path.join(IMAGE_DIR, "HY350_user_public_en_F_chuangyihui_OTA_2024-10-25-1715_.img"),
    # The two HY300 Pro+ (2025) vendor images, package F1. They are not in ~/Downloads but under
    # umbau/fixtures-local, so they exist only with run.sh --local; without it every test that asks
    # for them skips (support.need).
    "hy300-pro-plus-ddr3": os.path.join(FIXTURES_LOCAL, "images", "hy300-pro-downloads",
                                        "mega", "update.img"),
    "hy300-pro-plus-lpddr3": os.path.join(FIXTURES_LOCAL, "images", "hy300-pro-downloads",
                                          "gdrive", "HY300pro+ 0710", "update.img"),
}

# Raw targets outside every partition, plus the locked block -- the same numbers
# as `stock_plan()`s `roh` list and SPERRE_ERSTER/LETZTER in hy310-install.py.
BOOT0_LBA = (16, 256)
BOOT_PACKAGE_LBA = (24576, 32800)
LOCK_FIRST, LOCK_SECTORS = 12288, 2048

# Fixed windows the journal always hashes, whatever the partition table says.
FIXED_REGIONS = (
    ("gpt-primary", 0, 34),
    ("boot0-a", BOOT0_LBA[0], 64),
    ("boot0-b", BOOT0_LBA[1], 64),
    ("boot-package-a", BOOT_PACKAGE_LBA[0], 2432),
    ("boot-package-b", BOOT_PACKAGE_LBA[1], 2432),
    ("secure-storage", LOCK_FIRST, LOCK_SECTORS),
)
JOURNAL_CAP = 8192                       # sectors (4 MiB) hashed per region max

# What each builder needs.  A test asks `missing()` and skips with a real reason.
NEEDS_STOCK = (STOCK_GPT, STOCK_BOOTLOADER, STOCK_ENV_A,
               os.path.join(FIXTURES_LOCAL, "images", "hy310", "boot0_sdcard.fex"),
               os.path.join(FIXTURES_LOCAL, "images", "hy310", "boot_package.fex"))
NEEDS_V3 = (V3_GPT_PRIMARY, V3_GPT_BACKUP, V3_ENV)


def image_files(board):
    """Where the small .fex files of one board live."""
    return os.path.join(FIXTURES_LOCAL, "images", board)


def needs_adt3(board):
    return tuple(os.path.join(image_files(board), n) for n in ("sunxi_gpt.fex",
                 "boot0_sdcard.fex", "boot_package.fex", "boot-resource.fex"))


def missing(paths):
    """Which of these fixtures are not on this machine?"""
    return [p for p in paths if not os.path.isfile(p)]


# ------------------------------------------------------------------ pattern

def pattern(tag, lba, sectors):
    """Recognisable, non-zero filler; every sector names its region and its LBA."""
    out = bytearray()
    for i in range(sectors):
        line = ("H713-FAKE-DISK %s LBA %d " % (tag, lba + i)).encode("ascii")
        out += (line * (SECT // len(line) + 1))[:SECT]
    return bytes(out)


# ------------------------------------------------------------------ helpers

def _read(path, limit=None):
    with open(path, "rb") as fh:
        return fh.read() if limit is None else fh.read(limit)


def _put(fh, lba, data):
    fh.seek(lba * SECT)
    fh.write(data)


def _put_file(fh, lba, path, max_sectors=None):
    data = _read(path, None if max_sectors is None else max_sectors * SECT)
    _put(fh, lba, data)
    return len(data)


def gpt_parts(head):
    """(name, lba, sectors) of every used entry of a GPT read from `head`."""
    out = []
    if head[SECT:SECT + 8] != b"EFI PART":
        return out
    pe_lba, pe_n, pe_sz = struct.unpack_from("<QII", head, SECT + 72)
    tab = head[pe_lba * SECT:pe_lba * SECT + pe_n * pe_sz]
    for i in range(pe_n):
        e = tab[i * pe_sz:(i + 1) * pe_sz]
        if len(e) < 128 or e[:16] == b"\0" * 16:
            continue
        start, end = struct.unpack_from("<QQ", e, 32)
        out.append((e[56:128].decode("utf-16-le", "replace").rstrip("\0"),
                    start, end - start + 1))
    return out


def _put_backup_gpt(fh, primary, disk_sectors=DISK_SECTORS):
    """The backup table and header at the end of the disk, derived from the
    primary exactly as the vendor tool (and `stock_gpt_bauen`) build them."""
    hdr = bytearray(primary[SECT:SECT + 92])
    hsz = struct.unpack_from("<I", hdr, 12)[0]
    pe_lba, pe_n, pe_sz = struct.unpack_from("<QII", hdr, 72)
    arr_sect = (pe_n * pe_sz + SECT - 1) // SECT
    tab = primary[pe_lba * SECT:pe_lba * SECT + pe_n * pe_sz]
    back_arr = disk_sectors - 1 - arr_sect
    struct.pack_into("<QQ", hdr, 24, disk_sectors - 1, 1)      # MyLBA, AlternateLBA
    struct.pack_into("<Q", hdr, 72, back_arr)                  # entry array LBA
    struct.pack_into("<I", hdr, 16, 0)
    struct.pack_into("<I", hdr, 16, zlib.crc32(bytes(hdr[:hsz])) & 0xFFFFFFFF)
    _put(fh, back_arr, tab.ljust(arr_sect * SECT, b"\0"))
    _put(fh, disk_sectors - 1, bytes(hdr).ljust(SECT, b"\0"))


def _blank(path, disk_sectors=DISK_SECTORS):
    with open(path, "wb") as fh:
        fh.truncate(disk_sectors * SECT)


# ------------------------------------------------------------------ builders

def make_stock_disk(path):
    """The HY310 as it left the factory: stock GPT, vendor boot chain, pattern in
    the four device-only regions.  `super` stays zero -- no test needs its 2 GiB,
    and `geraet_erkennen()` is expected to give up there."""
    img = image_files("hy310")
    primary = _read(STOCK_GPT)
    parts = dict((n, (l, s)) for n, l, s in gpt_parts(primary))
    _blank(path)
    with open(path, "r+b") as fh:
        _put(fh, 0, primary)
        _put_backup_gpt(fh, primary)
        for lba in BOOT0_LBA:
            _put_file(fh, lba, os.path.join(img, "boot0_sdcard.fex"))
        for lba in BOOT_PACKAGE_LBA:
            _put_file(fh, lba, os.path.join(img, "boot_package.fex"))
        _put(fh, LOCK_FIRST, pattern("secure-storage", LOCK_FIRST, LOCK_SECTORS))
        for name in ("bootloader_a", "bootloader_b"):
            _put_file(fh, parts[name][0], STOCK_BOOTLOADER, parts[name][1])
        _put_file(fh, parts["env_a"][0], STOCK_ENV_A, parts["env_a"][1])
        for name in ("misc", "private", "Reserve0_a", "Reserve0_b"):
            _put(fh, parts[name][0], pattern(name, *parts[name]))
    return path


def make_v3_disk(path):
    """Our layout v3 after a release install: both GPTs from the release
    fixtures, a valid U-Boot environment at LBA 14336, pattern in the locked
    block.  private/Reserve0 stay zero -- layout v3 has no such partitions, and
    `abzug_klein()` is meant to report them as empty."""
    primary = _read(V3_GPT_PRIMARY)
    backup = _read(V3_GPT_BACKUP)
    _blank(path)
    with open(path, "r+b") as fh:
        _put(fh, 0, primary)
        _put(fh, DISK_SECTORS - GPT_BACKUP_SECTORS, backup)
        _put(fh, LOCK_FIRST, pattern("secure-storage", LOCK_FIRST, LOCK_SECTORS))
        _put_file(fh, 14336, V3_ENV)
    return path


def make_adt3_disk(path, board):
    """A board we have never held: GPT from the image's own sunxi_gpt.fex (25
    entries), boot chain from the image, bootloader_a from boot-resource.fex --
    which carries no mips/ directory.  That absence is the point of this disk."""
    img = image_files(board)
    primary = _read(os.path.join(img, "sunxi_gpt.fex"))
    parts = dict((n, (l, s)) for n, l, s in gpt_parts(primary))
    _blank(path)
    with open(path, "r+b") as fh:
        _put(fh, 0, primary)
        _put_backup_gpt(fh, primary)
        for lba in BOOT0_LBA:
            _put_file(fh, lba, os.path.join(img, "boot0_sdcard.fex"))
        for lba in BOOT_PACKAGE_LBA:
            _put_file(fh, lba, os.path.join(img, "boot_package.fex"))
        _put(fh, LOCK_FIRST, pattern("secure-storage", LOCK_FIRST, LOCK_SECTORS))
        lba, sectors = parts["bootloader_a"]
        _put_file(fh, lba, os.path.join(img, "boot-resource.fex"), sectors)
        for name in ("misc", "private", "Reserve0"):
            _put(fh, parts[name][0], pattern(name, *parts[name]))
    return path


# ------------------------------------------------------------------ journal

def _sha_region(fh, lba, sectors):
    h = hashlib.sha256()
    left = sectors * SECT
    fh.seek(lba * SECT)
    while left > 0:
        b = fh.read(min(left, 4 << 20))
        if not b:
            break
        h.update(b)
        left -= len(b)
    return h.hexdigest()


def journal(path, cap=JOURNAL_CAP):
    """name -> (lba, sectors, hashed_sectors, sha256) for every partition of the
    disk plus the fixed raw windows, so a test can assert "nothing moved".

    Regions longer than `cap` sectors are hashed only up to `cap` (4 MiB): the
    fake disk is sparse, and hashing 7 GiB of holes would cost more than the
    whole test run.  `hashed_sectors` says what the hash covers.
    """
    out = collections.OrderedDict()
    disk_sectors = os.path.getsize(path) // SECT
    with open(path, "rb") as fh:
        head = fh.read(34 * SECT)
        regions = list(FIXED_REGIONS)
        regions.append(("gpt-backup", disk_sectors - GPT_BACKUP_SECTORS, GPT_BACKUP_SECTORS))
        regions.extend(gpt_parts(head))
        for name, lba, sectors in regions:
            n = min(sectors, cap) if sectors else cap
            out[name] = (lba, sectors, n, _sha_region(fh, lba, n))
    return out
