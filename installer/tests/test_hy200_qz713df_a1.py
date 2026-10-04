"""HY200 QZ713DF A1: one board, two stock firmwares (variants); the HY300PRO-G-EU's firmware
(projector05061226, package GEU1) on an eMMC of 15273600 sectors, a test image for that unit alone.

Five things are pinned here:
  1. the layout and its GPT follow the disk size, and for the HY310's size they are the bytes
     of the release fixtures (the golden contract does not move);
  2. a GPT built for 15273600 sectors passes a checker written here from the UEFI layout,
     independent of h713.gpt (header CRC, array CRC, backup header at N-1 and its array where
     that header says, first/last usable, every entry inside them) -- with negative controls;
  3. h713-mkimage cuts a TEST image for the size its board's profile states, and h713-install
     writes an image or a dump only onto a device of that size;
  4. the board is recognised from its own features, and its test image is refused on every
     other board;
  5. the two firmwares of the board are told apart, each test image names its variant, and a
     test image for one variant is refused on the other (ST3-BOARDMERGE).
No vendor bytes: the features below are the hashes and version strings of the board's
identification row (package GEU1, material/identify-row.txt).
"""

import argparse
import contextlib
import importlib.machinery
import importlib.util
import io
import json
import os
import struct
import sys
import unittest
import warnings
import zlib
from unittest import mock

import support                 # imported first: it puts the tests directory on sys.path
import fakedisk

sys.path.insert(0, support.TOOLS)
from h713 import layout, mkimage                                    # noqa: E402
from h713.blockdev import SECTORS_EXPECTED, SECTORS_KNOWN           # noqa: E402
from h713.env import ENV_BYTES                                      # noqa: E402
from h713.gpt import build_layout_gpt, build_stock_gpt, check_gpt   # noqa: E402
from h713.identify import match_profiles                            # noqa: E402
from h713.install import test_image_allowed                         # noqa: E402
from h713.profiles import PROFILES, get, units                      # noqa: E402

SECT = 512
GEU = 15273600                         # HY300PRO-G-EU, the stock GPT of its dump: backup header LBA 15273599
GEU_ID = "hy200_qz713df_a1/projector05061226"     # its firmware, a variant of the HY200 QZ713DF A1
PLUS_ID = "hy200_qz713df_a1/projector09220931"    # the board's other firmware (HY300 Pro+, 2025-09-22)
HY310 = 15269888
TOOL = os.path.join(support.TOOLS, "h713-install")


# ------------------------------------------------------------------ an independent GPT reader

def read_gpt(path, n):
    """(problems, facts) for the GPT on a disk image of `n` sectors. Written from the UEFI
    layout, not from h713.gpt: protective MBR, both headers with their CRCs, both arrays with
    theirs, the backup header at n-1 and its array at the LBA it names, behind the last usable
    LBA, and every entry inside first..last usable without overlap."""
    problems, facts, arrays = [], {}, {}
    with open(path, "rb") as fh:
        def sectors(lba, count=1):
            fh.seek(lba * SECT)
            return fh.read(count * SECT)
        mbr = sectors(0)
        if mbr[510:512] != b"\x55\xaa" or mbr[450] != 0xEE:
            problems.append("protective MBR")
        for which, lba, other in (("primary", 1, n - 1), ("backup", n - 1, 1)):
            h = sectors(lba)
            if h[:8] != b"EFI PART":
                problems.append("%s header: no signature at LBA %d" % (which, lba))
                continue
            size, crc = struct.unpack_from("<II", h, 12)
            raw = bytearray(h[:size])
            raw[16:20] = b"\0\0\0\0"
            if zlib.crc32(bytes(raw)) & 0xFFFFFFFF != crc:
                problems.append("%s header: CRC" % which)
            mine, alt, first, last = struct.unpack_from("<QQQQ", h, 24)
            arr_lba, count, entry, arr_crc = struct.unpack_from("<QIII", h, 72)
            if (mine, alt) != (lba, other):
                problems.append("%s header: MyLBA/AlternateLBA %d/%d" % (which, mine, alt))
            arr_sectors = (count * entry + SECT - 1) // SECT
            arr = sectors(arr_lba, arr_sectors)[:count * entry]
            if zlib.crc32(arr) & 0xFFFFFFFF != arr_crc:
                problems.append("%s array: CRC" % which)
            arrays[which] = arr
            facts[which] = {"first": first, "last": last, "array_lba": arr_lba,
                            "array_sectors": arr_sectors, "count": count, "entry": entry}
    if len(facts) == 2:
        p, b = facts["primary"], facts["backup"]
        if (p["first"], p["last"]) != (b["first"], b["last"]):
            problems.append("the two headers disagree on first/last usable")
        if arrays["primary"] != arrays["backup"]:
            problems.append("the backup array differs from the primary one")
        if p["last"] != n - 34:
            problems.append("last usable %d, not n-34 = %d" % (p["last"], n - 34))
        if p["array_lba"] + p["array_sectors"] > p["first"]:
            problems.append("the primary array reaches into the usable area")
        if not (p["last"] < b["array_lba"] and b["array_lba"] + b["array_sectors"] <= n - 1):
            problems.append("the backup array is not between last usable and the backup header")
        entries, arr = [], arrays["primary"]
        for i in range(p["count"]):
            e = arr[i * p["entry"]:(i + 1) * p["entry"]]
            if not any(e[:16]):
                continue
            start, end = struct.unpack_from("<QQ", e, 32)
            entries.append((e[56:128].decode("utf-16-le").rstrip("\0"), start, end))
        for name, start, end in entries:
            if not p["first"] <= start <= end <= p["last"]:
                problems.append("%s %d..%d outside the usable area" % (name, start, end))
        ordered = sorted(entries, key=lambda x: x[1])
        for (n1, _s1, e1), (n2, s2, _e2) in zip(ordered, ordered[1:]):
            if s2 <= e1:
                problems.append("%s overlaps %s" % (n1, n2))
        facts["entries"] = entries
    return problems, facts


def _disk_with(path, n, blocks):
    """A sparse disk of n sectors with {lba: bytes} written in."""
    with open(path, "wb") as fh:
        fh.truncate(n * SECT)
        for lba, data in blocks.items():
            fh.seek(lba * SECT)
            fh.write(data)
    return path


class LayoutFollowsTheDiskSize(unittest.TestCase):

    def test_the_hy310_values_are_the_constants(self):
        self.assertEqual(layout.partitions_for(HY310), layout.PARTITIONS)
        self.assertEqual(layout.last_usable(HY310), layout.LAST_USABLE)
        self.assertEqual(layout.part_c_lba(HY310), layout.PART_C_LBA)

    def test_the_larger_emmc(self):
        parts = layout.partitions_for(GEU)
        self.assertEqual(parts[:-1], layout.PARTITIONS[:-1])        # only the last one grows
        name, lba, sectors, _guid = parts[-1]
        self.assertEqual((name, lba, sectors), ("hy310-rootfs", 278528, 14991327 + 3712))
        self.assertEqual(lba + sectors - 1, layout.last_usable(GEU))
        self.assertEqual((layout.last_usable(GEU), layout.part_c_lba(GEU)), (15273566, 15273567))

    def test_every_profile_size_is_one_the_layout_can_take(self):
        for board, profile in units().items():
            n = ((profile.get("layout") or {}).get("disk_sectors"))
            if n:
                self.assertIn(n, SECTORS_KNOWN, board)


class IndependentGptCheck(unittest.TestCase):

    def setUp(self):
        self.tmp = support.workdir(self)

    def _ours(self, n, built_for=None):
        return _disk_with(os.path.join(self.tmp, "disk-%d.img" % n), n,
                          build_layout_gpt(built_for or n))

    def test_a_gpt_for_15273600_sectors(self):
        problems, facts = read_gpt(self._ours(GEU), GEU)
        self.assertEqual(problems, [])
        self.assertEqual((facts["primary"]["first"], facts["primary"]["last"]), (16, GEU - 34))
        # The backup array sits where the backup header says, 7 sectors (26 entries) in front
        # of it -- not at n-33, which is where a 128-entry table would put it.
        self.assertEqual(facts["backup"]["array_lba"], GEU - 1 - 7)
        self.assertEqual(facts["entries"][-1], ("hy310-rootfs", 278528, GEU - 34))
        self.assertEqual([e[0] for e in facts["entries"]], [p[0] for p in layout.PARTITIONS])

    def test_h713_check_gpt_agrees(self):
        gpt = build_layout_gpt(GEU)
        part_c = bytearray(33 * SECT)
        for lba in (GEU - 8, GEU - 1):
            off = (lba - layout.part_c_lba(GEU)) * SECT
            part_c[off:off + len(gpt[lba])] = gpt[lba]
        self.assertEqual(check_gpt(gpt[0] + gpt[1] + gpt[2], bytes(part_c), GEU), [])
        self.assertNotEqual(check_gpt(gpt[0] + gpt[1] + gpt[2], bytes(part_c), HY310), [])

    def test_positive_control_the_release_fixtures(self):
        support.need(fakedisk.NEEDS_V3)
        with open(fakedisk.V3_GPT_PRIMARY, "rb") as fh:
            primary = fh.read()
        with open(fakedisk.V3_GPT_BACKUP, "rb") as fh:
            backup = fh.read()
        disk = _disk_with(os.path.join(self.tmp, "release.img"), HY310,
                          {0: primary, HY310 - 33: backup})
        self.assertEqual(read_gpt(disk, HY310)[0], [])

    def test_negative_control_the_hy310_table_on_the_larger_disk(self):
        problems, _facts = read_gpt(self._ours(GEU, built_for=HY310), GEU)
        self.assertIn("backup header: no signature at LBA %d" % (GEU - 1), problems)

    def test_negative_control_a_broken_backup_header(self):
        gpt = build_layout_gpt(GEU)
        bad = bytearray(gpt[GEU - 1])
        bad[40] ^= 1                                           # first usable LBA, CRC not redone
        gpt[GEU - 1] = bytes(bad)
        disk = _disk_with(os.path.join(self.tmp, "bad.img"), GEU, gpt)
        problems = read_gpt(disk, GEU)[0]
        self.assertIn("backup header: CRC", problems)
        self.assertIn("the two headers disagree on first/last usable", problems)

    def test_negative_control_a_broken_backup_array(self):
        gpt = build_layout_gpt(GEU)
        arr = bytearray(gpt[GEU - 8])
        arr[100] ^= 1
        gpt[GEU - 8] = bytes(arr)
        problems = read_gpt(_disk_with(os.path.join(self.tmp, "bad.img"), GEU, gpt), GEU)[0]
        self.assertIn("backup array: CRC", problems)

    def test_negative_control_a_backup_array_not_behind_last_usable(self):
        # The backup header names its array at n-3 (runs into the header and past the disk's
        # end), n+5 (beyond the disk), n-7 (its 7 sectors end on the header itself: one past
        # the bound) or n-34 (the last usable LBA: one short of the bound); its own CRC is
        # redone, so only the place is wrong. At n-34 the array is copied there as well, so
        # its CRC holds and the place is the only problem.
        msg = "the backup array is not between last usable and the backup header"
        for arr_lba in (GEU - 3, GEU + 5, GEU - 7, GEU - 34):
            with self.subTest(array_lba=arr_lba):
                gpt = build_layout_gpt(GEU)
                hdr = bytearray(gpt[GEU - 1])
                struct.pack_into("<Q", hdr, 72, arr_lba)
                size = struct.unpack_from("<I", hdr, 12)[0]
                hdr[16:20] = b"\0\0\0\0"
                struct.pack_into("<I", hdr, 16, zlib.crc32(bytes(hdr[:size])) & 0xFFFFFFFF)
                gpt[GEU - 1] = bytes(hdr)
                if arr_lba == GEU - 34:
                    gpt[arr_lba] = gpt[GEU - 8]
                disk = _disk_with(os.path.join(self.tmp, "arr-%d.img" % arr_lba), GEU, gpt)
                problems = read_gpt(disk, GEU)[0]
                self.assertNotIn("backup header: CRC", problems)
                self.assertIn(msg, problems)
                if arr_lba == GEU - 34:
                    self.assertEqual(problems, [msg])


# ------------------------------------------------------------------ h713-mkimage

def _inputs(directory):
    """The five building blocks, as small as build() lets them be."""
    os.makedirs(directory, exist_ok=True)
    paths = dict((k, os.path.join(directory, k)) for k in ("spl", "uboot", "env", "boot", "root"))
    with open(paths["spl"], "wb") as fh:
        fh.write(b"\0\0\0\0eGON.BT0".ljust(8192, b"\0"))
    with open(paths["uboot"], "wb") as fh:
        fh.write(b"U" * 4096)
    body = b"h713_gate=1\0\0".ljust(ENV_BYTES - 4, b"\0")
    with open(paths["env"], "wb") as fh:
        fh.write(struct.pack("<I", zlib.crc32(body) & 0xFFFFFFFF) + body)
    with open(paths["boot"], "wb") as fh:
        fh.truncate(262144 * SECT)
    with open(paths["root"], "wb") as fh:
        fh.truncate(2048 * SECT)
    return paths


def _sparse_copy(target, source, log=None):
    target.seek(os.path.getsize(source), 1)
    target.truncate()


def _build(directory, test_for=None):
    """h713.mkimage.build() over stub inputs; the ext4 checks are stubbed out (they read the
    two file systems, which a GPT test does not need), piece B is written sparse."""
    p = _inputs(os.path.join(directory, "in"))
    args = argparse.Namespace(out=os.path.join(directory, "out", "img.img"), spl=p["spl"],
                              uboot=p["uboot"], env=p["env"], boot_ext4=p["boot"],
                              rootfs_ext4=p["root"], test_for=test_for)
    with mock.patch.object(mkimage, "Ext4", lambda *a, **k: None), \
            mock.patch.object(mkimage, "ext4_check_tree", lambda *a, **k: []), \
            mock.patch.object(mkimage, "ext4_check_permissions", lambda *a, **k: None), \
            mock.patch.object(mkimage, "_copy", _sparse_copy), \
            contextlib.redirect_stdout(io.StringIO()), warnings.catch_warnings():
        warnings.simplefilter("ignore", ResourceWarning)     # mkimage's own open().read()s
        mkimage.build(args, here=support.TOOLS)
    out = os.path.join(directory, "out")
    with open(os.path.join(out, "img.tabelle.json"), encoding="utf-8") as fh:
        table = json.load(fh)
    return out, table


class MkimageCutsForTheProfileSize(unittest.TestCase):

    def setUp(self):
        self.tmp = support.workdir(self)

    def _piece(self, out, table, lba):
        piece = [t for t in table["teile"] if t["lba"] == lba][0]
        with open(os.path.join(out, piece["datei"]), "rb") as fh:
            return fh.read()

    def test_the_hy310_build_is_the_release_bytes(self):
        support.need(fakedisk.NEEDS_V3)
        with open(fakedisk.V3_GPT_PRIMARY, "rb") as fh:
            primary = fh.read()
        with open(fakedisk.V3_GPT_BACKUP, "rb") as fh:
            backup = fh.read()
        example = os.path.join(fakedisk.FIXTURES, "release", "h713-hy310-v4-example.tabelle.json")
        with open(example, encoding="utf-8") as fh:
            frozen = json.load(fh)
        for test_for in (None, "hy300_pro", "hy300_t08"):      # every other board: HY310 size
            out, table = _build(os.path.join(self.tmp, str(test_for)), test_for)
            self.assertEqual(table["disk_sektoren"], HY310, test_for)
            self.assertEqual(table["partitionen"], frozen["partitionen"], test_for)
            self.assertEqual([t["lba"] for t in table["teile"]], [0, 14336, HY310 - 33], test_for)
            self.assertEqual(self._piece(out, table, 0)[:9 * SECT], primary[:9 * SECT], test_for)
            self.assertEqual(self._piece(out, table, HY310 - 33), backup, test_for)
            self.assertEqual(table.get("test_for"), test_for)

    def test_the_test_image_for_this_board(self):
        out, table = _build(self.tmp, GEU_ID)
        self.assertEqual((table["test_for"], table["disk_sektoren"]), (GEU_ID, GEU))
        self.assertEqual([t["lba"] for t in table["teile"]], [0, 14336, GEU - 33])
        self.assertEqual(table["partitionen"][-1]["sektoren"], 14995039)
        disk = _disk_with(os.path.join(self.tmp, "disk.img"), GEU,
                          {0: self._piece(out, table, 0)[:9 * SECT],
                           GEU - 33: self._piece(out, table, GEU - 33)})
        problems, facts = read_gpt(disk, GEU)
        self.assertEqual(problems, [])
        self.assertEqual(facts["entries"][-1], ("hy310-rootfs", 278528, GEU - 34))
        log = Recorder()
        with contextlib.redirect_stdout(io.StringIO()), warnings.catch_warnings():
            warnings.simplefilter("ignore", ResourceWarning)
            mkimage.check(os.path.join(out, "img.tabelle.json"), log=log)
        text = "\n".join(log.lines)
        self.assertIn("the backup copy at the end of the disk is there and equal", text)

    def test_the_size_comes_from_the_profile(self):
        self.assertEqual(mkimage.disk_sectors_for(None), HY310)
        self.assertEqual(mkimage.disk_sectors_for(GEU_ID), GEU)
        for board in units():
            if board != GEU_ID:
                self.assertEqual(mkimage.disk_sectors_for(board), HY310, board)
        for wrong in ("hy300-pro",                                # the board dir id, not the profile
                      "hy200_qz713df_a1",                         # a board with variants needs one
                      "hy200_qz713df_a1/projector0506",           # no such variant
                      "hy310/projector07241019"):                 # a board without variants
            with self.assertRaises(SystemExit):
                mkimage.disk_sectors_for(wrong)


# ------------------------------------------------------------------ h713-install

def _tool():
    support.need([TOOL])
    spec = importlib.util.spec_from_loader(
        "h713_install_geu1", importlib.machinery.SourceFileLoader("h713_install_geu1", TOOL))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class SizeGate(unittest.TestCase):

    def test_which_sizes_a_run_takes(self):
        m = _tool()

        def allowed(command, profile="none", ident=True):
            args = argparse.Namespace(command=command)
            return m._sizes_allowed(args, {"profile": None if profile == "none" else profile}
                                    if ident else None)
        self.assertEqual(allowed("dump", "hy310"), SECTORS_KNOWN)
        self.assertEqual(allowed("restore-stock", GEU_ID), (HY310,))
        self.assertEqual(allowed("install", GEU_ID), (GEU,))
        self.assertEqual(allowed("restore", GEU_ID), (GEU,))
        self.assertEqual(allowed("install", PLUS_ID), (HY310,))      # its image's table says so
        self.assertEqual(allowed("install", "hy310"), (HY310,))
        self.assertEqual(allowed("install", "hy300_pro"), (HY310,))
        self.assertEqual(allowed("install"), SECTORS_KNOWN)              # our layout: no profile
        self.assertEqual(allowed("install", ident=False), SECTORS_KNOWN)  # --skip-identify


def _table(directory, disk_sectors, test_for=None):
    """A v4 table with one small part B, cut for `disk_sectors`."""
    os.makedirs(directory, exist_ok=True)
    body = b"H713 test image\n" * 256
    with open(os.path.join(directory, "b.img"), "wb") as fh:
        fh.write(body)
    table = {"format": mkimage.TABLE_FORMAT}
    if test_for:
        table["test_for"] = test_for
    table.update({"version": 1, "werkzeug": "h713-mkimage 0.1", "erzeugt": "2026-10-02T00:00:00",
                  "abbild": "geu1", "sektorgroesse": SECT, "disk_sektoren": disk_sectors,
                  "layout": mkimage.LAYOUT,
                  "partitionen": [{"name": n, "lba": l, "sektoren": s, "guid": g}
                                  for n, l, s, g in layout.partitions_for(disk_sectors)],
                  "loch": {"lba": mkimage.LOCK_FIRST, "partition": "hy310-keys", "warum": "-",
                           "sektoren": mkimage.LOCK_LAST - mkimage.LOCK_FIRST + 1},
                  "teile": [{"datei": "b.img", "lba": 14336, "sektoren": len(body) // SECT,
                             "bytes": len(body), "sha256": None}]})
    table.update(mkimage.file_table())
    path = os.path.join(directory, "geu1.tabelle.json")
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(table, fh)
    return path


def _run(m, argv):
    """main() in-process; what goes to stdout and to stderr (the errors) in one text."""
    out = io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(out):
        try:
            code = m.main(argv)
        except SystemExit as e:
            code = e.code
    return code, out.getvalue()


class Recorder(object):
    """The console shape the tools log through, remembering every line."""

    def __init__(self):
        self.lines = []

    def _add(self, text):
        self.lines.append(text)

    ok = info = warn = error = _add

    def step(self, number, what):
        self.lines.append("[%s] %s" % (number, what))


class OurLayoutOfTheOtherSize(unittest.TestCase):
    """Our layout on the device, no profile to go by: the image's table and the dump must have
    the device's size. Both directions, and the matching size as the control."""

    def setUp(self):
        self.tmp = support.workdir(self)
        self.m = _tool()

    def _disk(self, n):
        parts = [(name, lba, sectors) for name, lba, sectors, _g in layout.partitions_for(n)]
        return fakedisk.make_our_layout_disk(os.path.join(self.tmp, "emmc-%d.img" % n), parts, n)

    def _install(self, n_disk, n_table):
        disk = self._disk(n_disk)
        before = fakedisk.journal(disk)
        table = _table(os.path.join(self.tmp, "rel-%d" % n_table), n_table)
        code, out = _run(self.m, ["install", table, "--device", disk, "--small", "--no-write",
                                  "--dump", os.path.join(self.tmp, "dump")])
        self.assertEqual(fakedisk.journal(disk), before, out)
        return code, out

    def test_an_hy310_image_on_the_larger_emmc_is_refused(self):
        code, out = self._install(GEU, HY310)
        self.assertEqual(code, 4, out)
        self.assertIn("cut for an eMMC of %d sectors" % HY310, out)
        self.assertNotIn("Take the dump", out)          # refused before the dump (review nit 8)

    def test_a_larger_emmc_image_on_the_hy310_is_refused(self):
        code, out = self._install(HY310, GEU)
        self.assertEqual(code, 4, out)
        self.assertIn("cut for an eMMC of %d sectors" % GEU, out)

    def test_control_the_matching_size_goes_on(self):
        code, out = self._install(GEU, GEU)
        self.assertEqual(code, 0, out)
        self.assertNotIn("cut for an eMMC", out)
        self.assertIn("No-write run -- nothing written.", out)

    def _raw(self, n_disk, n_image):
        """`install` of a single whole-disk image without a table (review GEU1, bug 3)."""
        disk = self._disk(n_disk)
        before = fakedisk.journal(disk)
        image = os.path.join(self.tmp, "whole-%d.img" % n_image)
        with open(image, "wb") as fh:
            fh.truncate(n_image * SECT)
        code, out = _run(self.m, ["install", image, "--device", disk, "--small", "--no-write",
                                  "--dump", os.path.join(self.tmp, "dump")])
        self.assertEqual(fakedisk.journal(disk), before, out)
        return code, out

    def test_a_raw_whole_disk_image_of_the_other_size_is_refused(self):
        code, out = self._raw(GEU, HY310)
        self.assertEqual(code, 4, out)
        self.assertIn("a whole-disk image of a %d-sector eMMC" % HY310, out)
        self.assertNotIn("Take the dump", out)          # refused before the dump (review nit 8)

    def test_control_a_raw_image_of_the_board_s_size_goes_on(self):
        code, out = self._raw(GEU, GEU)
        self.assertEqual(code, 0, out)
        self.assertIn("WOULD: write", out)

    def _restore(self, n_disk, n_dump):
        disk = self._disk(n_disk)
        before = fakedisk.journal(disk)
        dump = os.path.join(self.tmp, "emmc-full-%d.img" % n_dump)
        with open(dump, "wb") as fh:
            fh.truncate(n_dump * SECT)
        code, out = _run(self.m, ["restore", dump, "--device", disk, "--no-write"])
        self.assertEqual(fakedisk.journal(disk), before, out)
        return code, out

    def test_a_dump_of_the_other_size_is_not_written_back(self):
        code, out = self._restore(GEU, HY310)
        self.assertEqual(code, 4, out)
        self.assertIn("is the full dump of a %d-sector eMMC" % HY310, out)
        self.assertNotIn("Small dump", out)             # refused before the dump (review nit 8)

    def test_control_the_board_s_own_dump(self):
        code, out = self._restore(GEU, GEU)
        self.assertEqual(code, 0, out)
        self.assertIn("No-write run -- nothing written.", out)


# ------------------------------------------------------------------ the test image route

# The identification row of the board (h713-install identify on its stock eMMC, 2026-10-02).
ROW = {
    "scp_sha256": "07487858659df9e8d4d3aba576b155e48c22076d4c1fff89cda6fa8ccde80e2f",
    "uboot_sha256": "d98fd80398b01b2ea2937e217a827e1d3d543f91681ef97e776c72bcf06310bd",
    "dtb_sha256": "e34fc69b1d245199fd5e20367a4db43cebda7f042d5943310b37117de4dbf93a",
    "uboot_version": "U-Boot 2018.05-00025-g4176897-dirty (May 06 2025 - 12:24:19 +0800) "
                     "Allwinner Technology",
    "arisc_version": "TV-303  ARISC  00.00.00.09 Date:May  6 2025 Time: 12:24:17",
    "build_fingerprint": "Allwinner/h713_tuna_p3/h713-tuna_p3:11/RP1A.201005.006/"
                         "projector05061226:user/release-keys",
    "mips_database_sha256": "002ad401d581a293d56106c8faf361eb9919f234562a6d7c316c1de1438a2aac",
}


class TheBoardAndOnlyTheBoard(unittest.TestCase):

    def test_the_row_identifies_this_board_alone(self):
        found, candidates, _matches = match_profiles(ROW)
        self.assertEqual((found, candidates), (GEU_ID, [GEU_ID]))

    def test_the_board_s_other_firmware_is_the_other_variant(self):
        plus = get(PLUS_ID)["stock"]
        row = dict(ROW, scp_sha256=plus["package_items"]["scp"][1],
                   uboot_sha256=plus["package_items"]["u-boot"][1],
                   dtb_sha256=plus["package_items"]["dtb"][1], uboot_version=plus["uboot_version"],
                   arisc_version=plus["arisc_version"], build_fingerprint=plus["build_fingerprint"],
                   sunxi_version=plus["sunxi_version"])
        found, candidates, matches = match_profiles(row)
        self.assertEqual((found, candidates), (PLUS_ID, [PLUS_ID]))
        self.assertFalse(any(matches[GEU_ID].values()))
        # one mixed feature is enough to make it neither: the firmware is the unit
        found, candidates, _matches = match_profiles(dict(row, scp_sha256=ROW["scp_sha256"]))
        self.assertEqual((found, candidates), (None, []))

    def test_the_hy310_is_not_taken_for_it(self):
        hy310 = dict(ROW)
        hy310.update({"scp_sha256": PROFILES["hy310"]["stock"]["package_items"]["scp"][1],
                      "uboot_sha256": PROFILES["hy310"]["stock"]["package_items"]["u-boot"][1],
                      "dtb_sha256": PROFILES["hy310"]["stock"]["package_items"]["dtb"][1],
                      "uboot_version": PROFILES["hy310"]["stock"]["uboot_version"],
                      "arisc_version": PROFILES["hy310"]["stock"]["arisc_version"],
                      "build_fingerprint": PROFILES["hy310"]["stock"]["build_fingerprint"],
                      "mips_database_sha256": PROFILES["hy310"]["expected"]["mips_database_sha256"]})
        self.assertEqual(match_profiles(hy310)[0], "hy310")

    def test_its_test_image_on_every_other_board_is_refused(self):
        for board in list(units()) + list(PROFILES) + [None]:    # the bare board id included
            log = Recorder()
            allowed = test_image_allowed({"profile": board, "_lines": []}, GEU_ID, True, log)
            self.assertEqual(allowed, board == GEU_ID, board)
        self.assertFalse(test_image_allowed({"profile": GEU_ID, "_lines": []},
                                            GEU_ID, False, Recorder()))


class VariantSchema(unittest.TestCase):
    """profiles/validate.py on the variants structure (SCHEMA.md), with negative controls."""

    def setUp(self):
        sys.path.insert(0, os.path.join(support.TOOLS, "h713"))
        try:
            import profiles.validate as validate         # the tool as it runs: top-level "profiles"
        finally:
            sys.path.pop(0)
        self.validate = validate.validate
        self.board = PROFILES["hy200_qz713df_a1"]

    def _problems(self, board=None, variant=None, **keys):
        """validate() on a copy of the board, `keys` set on the board or on one variant."""
        p = dict(self.board, variants=dict(self.board["variants"]))
        if variant:
            p["variants"][variant] = dict(p["variants"][variant], **keys)
        else:
            p.update(keys)
        return self.validate("hy200_qz713df_a1", board or p)

    def test_the_board_and_both_variants_are_clean(self):
        self.assertEqual(self._problems(), [])
        self.assertEqual(sorted(self.board["variants"]), ["projector05061226", "projector09220931"])
        self.assertEqual(get(GEU_ID)["variant"], "projector05061226")
        self.assertEqual(get(GEU_ID)["board_dt"], get(PLUS_ID)["board_dt"])

    def test_negative_controls(self):
        self.assertIn("status belongs to each variant, not to the board",
                      self._problems(status="profile-only"))
        self.assertIn("variant projector09220931: board_dt belongs to the board",
                      self._problems(variant="projector09220931", board_dt="x"))
        p = dict(self.board, variants=dict(self.board["variants"]))
        p["variants"]["projector05061226"] = dict((k, v) for k, v in
                                                  p["variants"]["projector05061226"].items() if k != "dram")
        self.assertIn("variant projector05061226: dram is missing", self._problems(board=p))
        self.assertTrue(any(line.startswith("variant projector09220931: dram needs a positive clk")
                            for line in self._problems(variant="projector09220931",
                                                       dram=dict(get(PLUS_ID)["dram"], clk=0))))
        self.assertIn("variants: a non-empty dict, variant name -> its keys", self._problems(variants={}))


def _stock_disk(path, n, partitions):
    """A stock partition table (no vendor bytes) on a sparse disk of n sectors."""
    return _disk_with(path, n, build_stock_gpt([(p[0], p[1], p[2]) for p in partitions], n))


class TheWholeRunOnAFakeBoard(unittest.TestCase):
    """h713-install main() on a stock-table disk of each size, with identify() answering as it
    does on the real board (the features a fake disk cannot carry: its boot package)."""

    def setUp(self):
        self.tmp = support.workdir(self)
        self.m = _tool()

    def _run_as(self, board, n, partitions, test_for):
        disk = _stock_disk(os.path.join(self.tmp, "stock-%d.img" % n), n, partitions)
        before = fakedisk.journal(disk)
        table = _table(os.path.join(self.tmp, "rel"), GEU, test_for=test_for)
        real = self.m.identify

        def as_board(d):
            ident = real(d)
            ident["profile"], ident["status"] = board, "profile-only"
            return ident
        with mock.patch.object(self.m, "identify", as_board):
            code, out = _run(self.m, ["install", table, "--device", disk, "--small", "--no-write",
                                      "--test-image", "--dump", os.path.join(self.tmp, "dump")])
        self.assertEqual(fakedisk.journal(disk), before, out)
        return code, out

    def test_on_this_board_the_test_image_passes_every_gate(self):
        code, out = self._run_as(GEU_ID, GEU, get(GEU_ID)["layout"]["partitions"], GEU_ID)
        self.assertIn("TEST IMAGE for '%s': this device is that board" % GEU_ID, out)
        self.assertNotIn("wrong drive", out)
        self.assertNotIn("cut for an eMMC", out)
        self.assertEqual(code, 0, out)
        self.assertIn("No-write run -- nothing written.", out)

    def test_the_way_back_on_a_still_stock_table_needs_skip_identify(self):
        """A restore onto this board while it still carries its stock table: identify() would
        find a profile-only board, which report_device() refuses for any write (exit 10 in a
        real run); --skip-identify passes every gate up to the write (review GEU1, question 3)."""
        from h713.identify import report_device
        disk = _stock_disk(os.path.join(self.tmp, "stock-geu.img"), GEU,
                           get(GEU_ID)["layout"]["partitions"])
        with contextlib.redirect_stdout(io.StringIO()):
            ident = self.m.identify(disk)
            ident["profile"], ident["status"] = GEU_ID, "profile-only"
            self.assertFalse(report_device(ident, Recorder(), writing=True))
            self.assertTrue(report_device(ident, Recorder(), writing=False))
        dump = os.path.join(self.tmp, "emmc-full.img")
        with open(dump, "wb") as fh:
            fh.truncate(GEU * SECT)
        code, out = _run(self.m, ["restore", dump, "--device", disk, "--no-write", "--skip-identify"])
        self.assertEqual(code, 0, out)
        self.assertIn("No-write run -- nothing written.", out)

    def test_on_the_hy310_it_is_refused(self):
        code, out = self._run_as("hy310", HY310, PROFILES["hy310"]["layout"]["partitions"], GEU_ID)
        self.assertEqual(code, 1, out)
        self.assertIn("This is a TEST IMAGE for the board '%s'" % GEU_ID, out)
        self.assertIn("This device is 'hy310'", out)

    def test_on_the_board_s_other_firmware_it_is_refused(self):
        code, out = self._run_as(PLUS_ID, GEU, get(GEU_ID)["layout"]["partitions"], GEU_ID)
        self.assertEqual(code, 1, out)
        self.assertIn("This device is '%s'" % PLUS_ID, out)


if __name__ == "__main__":
    unittest.main()
