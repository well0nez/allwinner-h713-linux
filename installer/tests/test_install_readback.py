"""N2: on a device that already runs our layout, `install` neither demands a dump nor
--vendor -- it reads the vendor files back out of the placeholders the last install filled.

Everything here runs on fake disks (fakedisk.py) and on a miniature release: a table of the
same shape h713-mkimage writes, with a part B of half a megabyte instead of 1.15 GB. That is
what makes a real write affordable in a unit test -- `test_a_real_run_...` below writes the
image onto the fake disk and checks afterwards what the device kept.

The placeholder bytes are put on the disk through a plain byte offset (part B starts at LBA
14336, so the offset of the table is a byte offset on the disk); the installer finds them
through LBA arithmetic of its own. The two derivations are independent on purpose.
"""

import hashlib
import json
import os
import subprocess
import sys
import unittest

import support                 # imported first: it puts the tests directory on sys.path
import fakedisk

sys.path.insert(0, support.TOOLS)
from h713.blockdev import Disk                                 # noqa: E402
from h713.env import ENV_BYTES, env_read, env_write            # noqa: E402
from h713.install import read_placeholders                     # noqa: E402
from h713.layout import PART_B_LBA, pattern                    # noqa: E402

SECT = 512
TOOL = os.path.join(support.TOOLS, "h713-install")
PART = "test-b-system.img"
PART_BYTES = 512 << 10
FIRST = ENV_BYTES + (64 << 10)          # behind the environment block at the start of part B

# One placeholder of every kind the installer knows: mandatory with a magic, mandatory
# without one, the optional boot logo (OPTIONAL_FILES), and a whole optional group
# (OPTIONAL_GROUPS).  name -> (length of the placeholder, what the device carries there)
FILES = (
    ("boot/mips/database.TSE", 4096, b"TSE\x01" + b"display tables of this very device\n" * 40),
    ("boot/mips/display.bin", 8192, b"\x7fELF" + bytes(range(256)) * 12),
    ("boot/bootlogo.bmp", 4096, b"BM" + b"\x99" * 600),
    ("lib/firmware/h713-arisc.bin", 2048, b"arisc" + b"\x11" * 900),
    ("pq/portmap.cfg", 1024, b"[ports]\nhdmi=1\n"),
    ("lib/firmware/aic8800_fw/SDIO/aic8800D80/fw_adid_8800d80.bin", 1024, b"\xa1" * 700),
    ("lib/firmware/aic8800_fw/SDIO/aic8800D80/fw_patch_8800d80.bin", 1024, b"\xa2" * 900),
)
WLAN = tuple(n for n, _l, _d in FILES if "aic8800_fw" in n)
OLD_ENV = {"bootcmd": "run boot_emmc", "h713_gate": "1", "h713_boot": "emmc"}
NEW_ENV = {"bootcmd": "run boot_emmc", "h713_gate": "0", "h713_boot": "net", "loglevel": "4"}


class Recorder(support.Recorder):
    """support.Recorder plus the error level -- the installer's console has four, and
    read_placeholders() names a refusal with the one that belongs to it."""

    def error(self, t):
        self.lines.append("ERROR " + t)


def _offsets():
    """name -> (byte offset in part B, length). One of them deliberately does not start on a
    sector boundary: the reader has to cut, and nothing says an ext4 must be kind to us."""
    out, off = {}, FIRST
    for i, (name, length, _data) in enumerate(FILES):
        out[name] = (off + (13 if i == len(FILES) - 1 else 0), length)
        off += length + 4096
    return out


class Release(object):
    """The miniature release folder: part B as an image would ship it (environment at its
    start, the fill pattern in every placeholder) plus the table that describes it."""

    def __init__(self, directory):
        self.directory = directory
        self.offsets = _offsets()
        part = bytearray(b"\x5a" * PART_BYTES)
        part[0:ENV_BYTES] = env_write(NEW_ENV)
        for name, (off, length) in self.offsets.items():
            part[off:off + length] = pattern(name, length)
        self.path = os.path.join(directory, PART)
        with open(self.path, "wb") as f:
            f.write(part)
        self.table_path = os.path.join(directory, "h713-test.tabelle.json")
        self.write_table()

    def write_table(self, placeholders=None):
        with open(self.path, "rb") as f:
            blob = f.read()
        table = {
            "format": "hy310-abbild-tabelle", "version": 1, "werkzeug": "the N2 tests",
            "abbild": "h713-test", "layout": "v3 (doku/109 §2.2)",
            "sektorgroesse": SECT, "disk_sektoren": fakedisk.DISK_SECTORS,
            "loch": {"lba": fakedisk.LOCK_FIRST, "sektoren": fakedisk.LOCK_SECTORS,
                     "partition": "hy310-keys"},
            "teile": [{"datei": PART, "lba": PART_B_LBA, "sektoren": PART_BYTES // SECT,
                       "bytes": PART_BYTES, "sha256": hashlib.sha256(blob).hexdigest()}],
            "bausteine": {"env": {"lba": PART_B_LBA, "bytes": ENV_BYTES}},
            "platzhalter_datei": PART,
            "platzhalter": dict((n, list(v)) for n, v in
                                (placeholders or self.offsets).items()),
            "platzhalter_nutzer": {},
        }
        with open(self.table_path, "w", encoding="utf-8") as f:
            json.dump(table, f, indent=1)
        return table


def install_state(disk, offsets, files=FILES, leave_out=()):
    """Put the device into the state a finished install leaves behind: every placeholder
    carries its file, zero padded to the placeholder length. `leave_out` names the ones that
    stay as the image builder made them -- a device that never had that file."""
    with open(disk, "r+b") as f:
        for name, length, data in files:
            off, _length = offsets[name]
            if name in leave_out:
                blob = pattern(name, length) if name == "boot/bootlogo.bmp" else bytes(length)
            else:
                blob = data.ljust(length, b"\0")[:length]
            f.seek(PART_B_LBA * SECT + off)
            f.write(blob)
    return dict((name, (data.ljust(length, b"\0")[:length]))
                for name, length, data in files if name not in leave_out)


class ReadBack(unittest.TestCase):
    """read_placeholders(): the reading itself, without the rest of the installer."""

    def setUp(self):
        support.need(fakedisk.NEEDS_V3)
        self.tmp = support.workdir(self)
        self.disk = fakedisk.make_v3_disk(os.path.join(self.tmp, "emmc-v3.img"))
        self.release = Release(self.tmp)
        self.log = Recorder()

    def _read(self, table, leave_out=()):
        want = install_state(self.disk, self.release.offsets, leave_out=leave_out)
        disk = Disk(self.disk, writable=False)
        try:
            return want, read_placeholders(disk, self.tab(), table, self.log)
        finally:
            disk.close()

    def tab(self):
        with open(self.release.table_path, encoding="utf-8") as f:
            return json.load(f)

    def table(self):
        return dict((n, tuple(v)) for n, v in self.tab()["platzhalter"].items())

    def test_the_bytes_come_back_exactly_as_they_lie_on_the_device(self):
        want, (sources, problem) = self._read(self.table())
        self.assertIsNone(problem, self.log.text)
        self.assertEqual(sorted(sources), sorted(want))
        for name in sorted(want):
            self.assertEqual(sources[name], want[name], name)
            self.assertEqual(len(sources[name]), self.release.offsets[name][1], name)
        self.assertIn("OK 7 files read back from the device's own placeholders", self.log.lines)

    def test_a_missing_optional_file_is_skipped_and_leaves_the_table(self):
        table = self.table()
        _want, (sources, problem) = self._read(table, leave_out=("boot/bootlogo.bmp",))
        self.assertIsNone(problem, self.log.text)
        self.assertNotIn("boot/bootlogo.bmp", sources)
        self.assertNotIn("boot/bootlogo.bmp", table)     # the caller neither fills nor counts it
        self.assertIn("no boot logo", self.log.text)

    def test_a_whole_optional_group_missing_stays_zeroed(self):
        table = self.table()
        _want, (sources, problem) = self._read(table, leave_out=WLAN)
        self.assertIsNone(problem, self.log.text)
        for name in WLAN:
            self.assertEqual(sources[name], b"", name)   # fill_placeholders zeroes the rest
        self.assertIn("this device probably does not have the chip", self.log.text)

    def test_a_missing_mandatory_file_names_itself(self):
        _want, (sources, problem) = self._read(self.table(),
                                               leave_out=("boot/mips/database.TSE",))
        self.assertEqual(sources, {})
        self.assertEqual(problem, "the device has no boot/mips/database.TSE -- give --vendor")

    def test_bytes_of_another_file_are_refused_not_installed(self):
        """The case the report is about: a device installed by a build whose placeholders lie
        somewhere else. What is read then is not this file -- here a BMP where a TSE belongs."""
        install_state(self.disk, self.release.offsets)
        off, _length = self.release.offsets["boot/mips/database.TSE"]
        with open(self.disk, "r+b") as f:
            f.seek(PART_B_LBA * SECT + off)
            f.write(b"BM" + b"\x77" * 500)
        disk = Disk(self.disk, writable=False)
        try:
            sources, problem = read_placeholders(disk, self.tab(), self.table(), self.log)
        finally:
            disk.close()
        self.assertEqual(sources, {})
        self.assertIn("placeholders lie elsewhere", problem)
        self.assertIn("boot/mips/database.TSE", self.log.text)

    def test_a_table_without_its_part_says_so_instead_of_reading_nonsense(self):
        tab = self.tab()
        tab["teile"] = [dict(tab["teile"][0], datei="somebody-elses.img")]
        disk = Disk(self.disk, writable=False)
        try:
            sources, problem = read_placeholders(disk, tab, self.table(), self.log)
        finally:
            disk.close()
        self.assertEqual(sources, {})
        self.assertIn("names no part", problem)


class InstallRun(unittest.TestCase):
    """The tool as a user drives it: `install`, on a fake disk, over the miniature release."""

    def setUp(self):
        support.need(fakedisk.NEEDS_V3 + (TOOL,))
        self.tmp = support.workdir(self)
        self.disk = fakedisk.make_v3_disk(os.path.join(self.tmp, "emmc-v3.img"))
        self.release = Release(self.tmp)

    def run_tool(self, *args, **kw):
        proc = subprocess.Popen(
            [sys.executable, TOOL] + list(args), stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, cwd=kw.get("cwd", self.tmp),
            env=dict(os.environ, TERM="dumb", LC_ALL="C.UTF-8"))
        return proc.wait(), proc.communicate()[0].decode("utf-8", "replace")

    def install(self, *extra, **kw):
        install_state(self.disk, self.release.offsets, leave_out=kw.pop("leave_out", ()))
        return self.run_tool("install", self.release.table_path, "--device", self.disk, *extra)

    def test_our_layout_needs_neither_dump_nor_vendor(self):
        code, out = self.install("--no-write")
        self.assertEqual(code, 0, out)
        self.assertIn("our layout on the device -- nothing stock to save; "
                      "--dump takes one anyway", out)
        self.assertIn("7 files read back from the device's own placeholders", out)
        self.assertIn("WOULD: copy %s" % PART, out)
        self.assertNotIn("There is neither --vendor nor a full dump", out)
        self.assertFalse(os.path.exists(os.path.join(self.tmp, "h713-dump")), out)

    def test_dump_takes_one_anyway_and_still_reads_the_placeholders_back(self):
        code, out = self.install("--no-write", "--dump", os.path.join(self.tmp, "keep"))
        self.assertEqual(code, 0, out)
        self.assertIn("Take the dump (small)", out)
        self.assertIn("7 files read back from the device's own placeholders", out)
        self.assertTrue(os.path.isfile(os.path.join(self.tmp, "keep", "secure-storage.bin")))
        self.assertTrue(os.path.isfile(os.path.join(self.tmp, "keep", "uboot-env.bin")))

    def test_vendor_still_wins_over_the_device(self):
        out_dir = os.path.join(self.tmp, "vendor")
        for name, length, data in FILES:
            path = os.path.join(out_dir, name.replace("/", os.sep))
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "wb") as f:
                f.write(data.ljust(length, b"\0")[:length])
        code, out = self.install("--no-write", "--vendor", out_dir)
        self.assertEqual(code, 0, out)
        self.assertIn("7 files from %s" % out_dir, out)
        self.assertNotIn("read back from the device's own placeholders", out)

    def test_a_mandatory_file_the_device_lacks_is_exit_8_with_the_old_message(self):
        code, out = self.install("--no-write", leave_out=("boot/mips/database.TSE",))
        self.assertEqual(code, 8, out)
        self.assertIn("There is neither --vendor nor a full dump in h713-dump.", out)
        self.assertIn("the device has no boot/mips/database.TSE -- give --vendor", out)

    def test_an_optional_file_the_device_lacks_is_a_warning_and_the_run_goes_on(self):
        code, out = self.install("--no-write", leave_out=("boot/bootlogo.bmp",))
        self.assertEqual(code, 0, out)
        self.assertIn("no boot logo", out)
        self.assertIn("6 files read back from the device's own placeholders", out)

    def test_a_real_run_fills_from_the_device_and_keeps_the_secure_storage(self):
        """The whole way with a write: read back, fill, write, compare back -- and the two
        things the skipped dump used to supply, the secure storage for the comparison and
        the old environment for the intent keys, come out of the copy read into memory."""
        before = fakedisk.journal(self.disk)
        with open(self.disk, "r+b") as f:                 # the device's own environment
            f.seek(PART_B_LBA * SECT)
            f.write(env_write(OLD_ENV))
        want = install_state(self.disk, self.release.offsets)
        code, out = self.run_tool("install", self.release.table_path, "--device", self.disk,
                                  "--yes")
        self.assertEqual(code, 0, out)
        self.assertIn("7 files read back from the device's own placeholders", out)
        self.assertIn("OK 7 placeholders filled and read back -- all equal", out)
        self.assertIn("Secure Storage unchanged", out)
        self.assertIn("carried over from the old one", out)
        with open(self.disk, "rb") as f:
            for name, (off, _length) in self.release.offsets.items():
                f.seek(PART_B_LBA * SECT + off)
                self.assertEqual(f.read(len(want[name])), want[name], name)
            f.seek(PART_B_LBA * SECT)
            env = env_read(f.read(ENV_BYTES))
        self.assertEqual(env["h713_gate"], "1")           # the device's, not the image's
        self.assertEqual(env["h713_boot"], "emmc")
        self.assertEqual(env["loglevel"], "4")            # everything else is the image's
        after = fakedisk.journal(self.disk)
        self.assertEqual(after["secure-storage"], before["secure-storage"], out)
        self.assertEqual(after["gpt-primary"], before["gpt-primary"], out)


class AgainstRealVendorFiles(unittest.TestCase):
    """The two judgements read_placeholders() passes on the bytes it finds -- "this was
    never filled" and "this is not that kind of file" -- measured against a real extraction
    of an HY310 (H713_VENDOR_OUT, i.e. run.sh --local). Not one of the real files may be
    mistaken for an empty placeholder, and not one may trip the magic table: that table was
    wrong about display_cfg.xml until this test was written (it starts with a comment, not
    with "<?xml"), and h713-arisc.bin opens with 16 zero bytes."""

    def test_every_extracted_vendor_file_reads_as_filled_and_of_its_kind(self):
        from h713.install import _unfilled, _wrong_kind
        from h713.layout import PLACEHOLDERS
        if not os.path.isdir(support.VENDOR_OUT):
            raise unittest.SkipTest("no extraction in %s (run.sh --local)" % support.VENDOR_OUT)
        checked = 0
        for name, size, _part, _path in PLACEHOLDERS:
            path = os.path.join(support.VENDOR_OUT, name.replace("/", os.sep))
            if not os.path.isfile(path):
                continue                       # an older extraction has no boot logo
            with open(path, "rb") as f:
                data = f.read().ljust(size, b"\0")[:size]
            self.assertFalse(_unfilled(name, data), name)
            self.assertFalse(_wrong_kind(name, data), (name, data[:16]))
            checked += 1
        self.assertGreaterEqual(checked, 40, support.VENDOR_OUT)


class StockIsUntouched(unittest.TestCase):
    """A stock device decides exactly as before: the dump is mandatory, and without it and
    without --vendor the run stops with exit 8 and the message it has always printed."""

    def setUp(self):
        support.need(fakedisk.NEEDS_STOCK_GPT + (TOOL,))
        self.tmp = support.workdir(self)
        self.disk = fakedisk.make_stock_gpt_disk(os.path.join(self.tmp, "emmc-stock.img"))
        self.release = Release(self.tmp)
        self.before = fakedisk.journal(self.disk)

    def run_tool(self, *args):
        proc = subprocess.Popen(
            [sys.executable, TOOL] + list(args), stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, cwd=self.tmp,
            env=dict(os.environ, TERM="dumb", LC_ALL="C.UTF-8"))
        return proc.wait(), proc.communicate()[0].decode("utf-8", "replace")

    def test_without_a_dump_and_without_vendor_it_is_still_exit_8(self):
        code, out = self.run_tool("install", self.release.table_path, "--device", self.disk,
                                  "--skip-identify", "--no-write", "--small")
        self.assertEqual(code, 8, out)
        self.assertIn("There is neither --vendor nor a full dump in h713-dump.", out)
        self.assertIn("The 7 files (display artefacts, boot logo, firmware, PQ, WLAN) "
                      "stand only", out)
        self.assertNotIn("read back from the device's own placeholders", out)
        self.assertNotIn("the device has no", out)
        self.assertEqual(fakedisk.journal(self.disk), self.before, out)

    def test_the_small_dump_is_still_taken_before_anything_else(self):
        code, out = self.run_tool("install", self.release.table_path, "--device", self.disk,
                                  "--skip-identify", "--no-write", "--small")
        self.assertEqual(code, 8, out)
        self.assertIn("Take the dump (small)", out)
        self.assertNotIn("nothing stock to save", out)
        for name in ("secure-storage.bin", "private.bin", "reserve0-a.bin"):
            self.assertTrue(os.path.isfile(os.path.join(self.tmp, "h713-dump", name)), name)

    def test_the_stock_restore_still_takes_its_mandatory_dump(self):
        code, out = self.run_tool("restore", os.path.join(self.tmp, PART), "--device",
                                  self.disk, "--skip-identify")
        self.assertIn("Small dump (mandatory, before a restore too)", out)
        self.assertEqual(code, 1, out)                    # refused at the YES prompt
        self.assertEqual(fakedisk.journal(self.disk), self.before, out)
