"""Layout v4: the vendor files are copied into the image's own file systems, and read back
out of the device's file systems -- no placeholders, no offsets, no sizes (P-layout-v4).

Two fixtures carry this. `fixtures/release/h713-hy310-v4-example.tabelle.json` is the complete
v4 table: the real v0.7-beta table of 16.09.2026 with the placeholder keys replaced by
`dateien`/`gruppen`/`nutzer` for all 44 files and the SSH key. The parts it names are not in
the repository, so its `sha256` fields are null and nothing runs `check_package` on it -- it is
there for the plan, which is pure Python. `Release` below is a miniature release the tool can
really be run against: a part B of under half a megabyte with two small partitions behind the
environment block, which is enough for every decision a rehearsal makes, because a rehearsal
mounts nothing.

The tests that do mount are marked: they need `H713_ROOT_TESTS=1` and the suite started as
root -- the executor runs `mount` itself and never calls sudo. Without both they skip and say
which of the two is missing.
"""

import hashlib
import json
import os
import shutil
import subprocess
import sys
import unittest

import support                 # imported first: it puts the tests directory on sys.path
import fakedisk

sys.path.insert(0, support.TOOLS)
from h713 import mountfs                                       # noqa: E402
from h713.blockdev import Disk                                 # noqa: E402
from h713.env import ENV_BYTES, env_write                      # noqa: E402
from h713.install import (copy_entries, device_sources, gpt_partitions,     # noqa: E402
                          partition_node, partition_window, read_public_key,
                          readback_plan, say_optional, table_layout, user_entries,
                          vendor_sources)

SECT = 512
TOOL = os.path.join(support.TOOLS, "h713-install")
V4_TABLE = os.path.join(fakedisk.FIXTURES, "release", "h713-hy310-v4-example.tabelle.json")

# The miniature release: part B carries the environment and two small partitions behind it.
PART = "test-b-system.img"
PART_LBA = 14336
ENV_SECTORS = ENV_BYTES // SECT
BOOT = ("hy310-boot", PART_LBA + ENV_SECTORS, 256)
ROOTFS = ("hy310-rootfs", BOOT[1] + BOOT[2], 512)
PART_SECTORS = ENV_SECTORS + BOOT[2] + ROOTFS[2]

# One file of every kind the installer knows: mandatory, the optional boot logo on its own,
# and two optional groups. name, partition, path in it, group, optional.
FILES = (
    ("boot/mips/database.TSE", BOOT[0], "/mips/database.TSE", "mips", False),
    ("boot/mips/display.bin", BOOT[0], "/mips/display.bin", "mips", False),
    ("boot/bootlogo.bmp", BOOT[0], "/bootlogo.bmp", "logo", True),
    ("lib/firmware/h713-arisc.bin", ROOTFS[0], "/lib/firmware/h713-arisc.bin", "firmware", False),
    ("pq/portmap.cfg", ROOTFS[0], "/etc/h713/tvconfig/portmap.cfg", "pq", True),
    ("lib/firmware/aic8800_fw/SDIO/aic8800D80/fw_adid_8800d80.bin", ROOTFS[0],
     "/lib/firmware/aic8800_fw/SDIO/aic8800D80/fw_adid_8800d80.bin", "wlan", True),
    ("lib/firmware/aic8800_fw/SDIO/aic8800D80/fw_patch_8800d80.bin", ROOTFS[0],
     "/lib/firmware/aic8800_fw/SDIO/aic8800D80/fw_patch_8800d80.bin", "wlan", True),
)
GROUPS = {"mips": "display firmware and tables", "logo": "boot logo",
          "firmware": "ARISC, EDID, MSP", "pq": "picture presets", "wlan": "WLAN firmware"}
USER = [{"name": "authorized_keys", "partition": ROOTFS[0], "pfad": "/root/.ssh/authorized_keys",
         "modus": "0600", "besitzer": "root", "verzeichnis_modus": "0700"}]
WLAN = tuple(n for n, _p, _t, g, _o in FILES if g == "wlan")
KEY = b"ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIB1t marco@pc\n"
NEW_ENV = {"bootcmd": "run boot_emmc", "h713_gate": "0", "h713_boot": "net", "loglevel": "4"}


class Recorder(support.Recorder):
    """support.Recorder plus the error level -- the installer's console has four."""

    def error(self, t):
        self.lines.append("ERROR " + t)


def v4_table():
    support.need([V4_TABLE])
    with open(V4_TABLE, encoding="utf-8") as f:
        return json.load(f)


def content(name):
    """What the fake extraction puts in a file: recognisable, and of its own length."""
    return ("this is %s of this very device\n" % name).encode() * (3 + len(name) % 7)


def extraction(directory, files, leave_out=()):
    """A directory as h713-extract leaves it, with the names the table uses."""
    for f in files:
        if f["name"] in leave_out:
            continue
        path = os.path.join(directory, f["name"].replace("/", os.sep))
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "wb") as fh:
            fh.write(content(f["name"]))
    return directory


class TheHandWrittenTable(unittest.TestCase):
    """The v4 fixture itself: what a release table has to say so that the installer needs
    nothing but the table to find every file and every mount."""

    def setUp(self):
        self.tab = v4_table()

    def test_it_is_a_v4_table_and_carries_no_placeholder_key(self):
        self.assertEqual(table_layout(self.tab), "v4")
        for gone in ("platzhalter", "platzhalter_nutzer", "platzhalter_datei", "platzhalter_info"):
            self.assertNotIn(gone, self.tab)

    def test_all_forty_four_files_with_their_group_and_target(self):
        files = self.tab["dateien"]
        self.assertEqual(len(files), 44)
        self.assertEqual(len(set(f["name"] for f in files)), 44)
        groups = {}
        for f in files:
            self.assertTrue(f["pfad"].startswith("/"), f["name"])
            self.assertIn(f["partition"], (BOOT[0], ROOTFS[0]), f["name"])
            self.assertIn(f["gruppe"], self.tab["gruppen"], f["name"])
            self.assertEqual(f["optional"], f["gruppe"] in ("logo", "pq", "wlan"), f["name"])
            groups[f["gruppe"]] = groups.get(f["gruppe"], 0) + 1
        self.assertEqual(groups, {"mips": 19, "logo": 1, "firmware": 3, "pq": 8, "wlan": 13})
        self.assertEqual(len([f for f in files if f["partition"] == BOOT[0]]), 20)

    def test_the_mount_window_of_a_partition_comes_out_of_the_table_alone(self):
        part = self.tab["teile"][1]
        self.assertEqual(partition_window(self.tab, "hy310-boot"),
                         (part["datei"], (16384 - 14336) * SECT, 262144 * SECT))
        # hy310-rootfs is 7.1 GiB on the device, but the image carries 1 GiB of it: the
        # window stops where part B stops, and that is exactly the ext4 the builder made.
        self.assertEqual(partition_window(self.tab, "hy310-rootfs"),
                         (part["datei"], (278528 - 14336) * SECT, 1 << 30))
        self.assertEqual(part["bytes"] - (278528 - 14336) * SECT, 1 << 30)

    def test_a_partition_no_part_covers_has_no_window(self):
        """hy310-keys is the hole: it lies between part A and part B, in neither of them."""
        self.assertIsNone(partition_window(self.tab, "hy310-keys"))
        with self.assertRaises(RuntimeError):
            partition_window(self.tab, "hy310-nonsense")

    def test_a_run_that_writes_only_the_boot_chain_has_no_file_system_to_fill(self):
        """Whoever writes part A alone -- to renew the bootloader -- touches neither file
        system, and then there is nothing to copy and no working copy to make."""
        only_a = dict(self.tab, teile=[self.tab["teile"][0]])
        for name in ("hy310-boot", "hy310-rootfs"):
            self.assertIsNone(partition_window(only_a, name), name)

    def test_the_user_file_says_its_modes_and_its_owner(self):
        self.assertEqual(self.tab["nutzer"], USER)


class ThePlan(unittest.TestCase):
    """What goes where, and what a firmware is allowed not to have -- all of it without root,
    on the complete 44-file table."""

    def setUp(self):
        self.tab = v4_table()
        self.files = self.tab["dateien"]
        self.tmp = support.workdir(self)
        self.out = os.path.join(self.tmp, "extract")
        self.log = Recorder()

    def sources(self, leave_out=()):
        extraction(self.out, self.files, leave_out)
        return vendor_sources(self.out, self.tab, self.files, self.log)

    def test_every_file_lands_in_its_partition_as_roots_own(self):
        plan = copy_entries(self.files, self.sources())
        self.assertEqual(self.log.lines, [])
        self.assertEqual(sorted(plan), [BOOT[0], ROOTFS[0]])
        self.assertEqual(len(plan[BOOT[0]]), 20)
        self.assertEqual(len(plan[ROOTFS[0]]), 24)
        by_path = dict((e.path, e) for e in plan[BOOT[0]] + plan[ROOTFS[0]])
        for f in self.files:
            e = by_path[f["pfad"]]
            self.assertEqual(e.data, content(f["name"]), f["name"])
            self.assertEqual((e.mode, e.uid, e.gid, e.dir_mode), (0o644, 0, 0, 0o755), f["name"])
            self.assertIsNone(e.source, f["name"])

    def test_a_whole_optional_group_missing_is_one_line_and_no_abort(self):
        wlan = [f["name"] for f in self.files if f["gruppe"] == "wlan"]
        sources = self.sources(leave_out=wlan)
        self.assertEqual(len(sources), 31)
        self.assertEqual(len(self.log.lines), 1, self.log.text)
        self.assertIn("none of the 13 files in the dump", self.log.text)
        self.assertIn("this firmware has no WLAN firmware", self.log.text)
        self.assertIn("WLAN stays off", self.log.text)
        for name in wlan:                      # nothing is ever written empty
            self.assertNotIn(name, sources)

    def test_part_of_an_optional_group_missing_is_one_line_too(self):
        """Issue #1, 16.09.2026: the HY300 Pro's Android 10 firmware ships another WLAN set and
        no pq_picturemode.ini -- one file of a group missing must not abort the install."""
        gone = [f["name"] for f in self.files if f["gruppe"] == "wlan"][:3]
        sources = self.sources(leave_out=gone)
        self.assertEqual(len(sources), 41)
        self.assertIn("3 of 13 files not in %s" % self.out, self.log.text)
        self.assertIn("another WLAN firmware set", self.log.text)

    def test_the_boot_logo_is_optional_on_its_own(self):
        sources = self.sources(leave_out=("boot/bootlogo.bmp",))
        self.assertEqual(len(sources), 43)
        self.assertEqual(len(self.log.lines), 1, self.log.text)
        self.assertIn("boot/bootlogo.bmp: not in %s -- no boot logo. U-Boot boots without a "
                      "logo." % self.out, self.log.text)

    def test_a_mandatory_file_missing_stops_the_run(self):
        with self.assertRaises(RuntimeError) as caught:
            self.sources(leave_out=("boot/mips/database.TSE",))
        self.assertIn("1 file(s) are missing", str(caught.exception))
        self.assertIn("boot/mips/database.TSE", str(caught.exception))

    def test_a_missing_file_of_a_group_that_is_not_optional_is_not_talked_away(self):
        left = say_optional(self.tab, self.files, ["lib/firmware/hy310-edid.bin"],
                            "in the dump", "not there", self.log)
        self.assertEqual(left, ["lib/firmware/hy310-edid.bin"])
        self.assertEqual(self.log.lines, [])


class _Args(object):
    """The one field of the command line that user_entries() looks at."""

    def __init__(self, ssh_key):
        self.ssh_key = ssh_key


class TheUserKey(unittest.TestCase):
    """--ssh-key: the file arrives with the length it has, and with the modes sshd needs."""

    def setUp(self):
        self.tmp = support.workdir(self)
        self.log = Recorder()

    def key(self, text=KEY, name="id_ed25519.pub"):
        path = os.path.join(self.tmp, name)
        with open(path, "wb") as f:
            f.write(text)
        return _Args(path)

    def test_the_key_arrives_as_it_is_and_nothing_is_padded(self):
        plan = user_entries(self.key(), USER, self.log)
        entry = plan[ROOTFS[0]][0]
        self.assertEqual(entry.data, KEY)
        self.assertEqual(entry.path, "/root/.ssh/authorized_keys")
        self.assertEqual((entry.mode, entry.dir_mode, entry.uid, entry.gid),
                         (0o600, 0o700, 0, 0))
        self.assertIn("1 key(s)", self.log.text)

    def test_a_private_key_is_refused_before_anything_is_written(self):
        with self.assertRaises(RuntimeError) as caught:
            user_entries(self.key(b"-----BEGIN OPENSSH PRIVATE KEY-----\nxx\n"), USER, self.log)
        self.assertIn("is a PRIVATE key", str(caught.exception))

    def test_a_file_that_holds_no_key_is_refused(self):
        with self.assertRaises(RuntimeError) as caught:
            user_entries(self.key(b"# just a comment\n"), USER, self.log)
        self.assertIn("no line looks like a public", str(caught.exception))

    def test_several_keys_and_crlf_come_out_as_lines(self):
        data, n = read_public_key(self.key(KEY.replace(b"\n", b"\r\n") + KEY).ssh_key)
        self.assertEqual(n, 2)
        self.assertEqual(data, KEY + KEY)

    def test_without_the_flag_nothing_is_written_and_it_is_said(self):
        plan = user_entries(_Args(None), USER, self.log)
        self.assertEqual(plan, {})
        self.assertIn("no --ssh-key: /root/.ssh/authorized_keys is not written", self.log.text)

    def test_a_file_of_the_user_this_installer_does_not_know_is_refused(self):
        with self.assertRaises(RuntimeError) as caught:
            user_entries(self.key(), [dict(USER[0], name="wpa_supplicant.conf")], self.log)
        self.assertIn("a newer h713-install is needed", str(caught.exception))


class TheReadBackPlan(unittest.TestCase):
    """Reading the files back off a device that runs our layout: where they are comes out of
    the device's own GPT, not out of a constant."""

    def setUp(self):
        support.need(fakedisk.NEEDS_V3)
        self.tmp = support.workdir(self)
        self.disk = fakedisk.make_v3_disk(os.path.join(self.tmp, "emmc-v3.img"))
        self.tab = v4_table()

    def open(self, path=None):
        disk = Disk(path or self.disk, writable=False)
        self.addCleanup(disk.close)
        return disk

    def test_the_partition_numbers_are_read_out_of_the_gpt(self):
        found = gpt_partitions(self.open())
        self.assertEqual(found["hy310-boot"], (5, 16384, 262144))
        self.assertEqual(found["hy310-rootfs"][0], 6)
        self.assertEqual(found["hy310-spl"], (1, 16, 64))

    def test_the_node_is_spelled_the_way_linux_spells_it(self):
        self.assertEqual(partition_node("/dev/sdb", 5), "/dev/sdb5")
        self.assertEqual(partition_node("/dev/mmcblk0", 5), "/dev/mmcblk0p5")
        self.assertEqual(partition_node("/dev/nvme0n1", 6), "/dev/nvme0n1p6")

    def test_the_plan_names_the_window_and_every_path_it_wants(self):
        plan = readback_plan(self.open(), self.tab["dateien"])
        self.assertEqual([row[0] for row in plan], ["hy310-boot", "hy310-rootfs"])
        name, node, offset, size, wanted = plan[0]
        self.assertEqual(node, self.disk + "5")          # a regular file takes the same rule
        self.assertEqual((offset, size), (16384 * SECT, 262144 * SECT))
        self.assertEqual(len(wanted), 20)
        self.assertEqual(wanted["/mips/database.TSE"], "boot/mips/database.TSE")
        self.assertEqual(len(plan[1][4]), 24)

    def test_a_device_without_our_partitions_says_so_instead_of_guessing(self):
        support.need(fakedisk.NEEDS_STOCK_GPT)
        stock = fakedisk.make_stock_gpt_disk(os.path.join(self.tmp, "emmc-stock.img"))
        with self.assertRaises(RuntimeError) as caught:
            readback_plan(self.open(stock), self.tab["dateien"])
        self.assertIn("the device has no partition hy310-boot -- give --vendor",
                      str(caught.exception))


class Release(object):
    """The miniature release folder: part B as an image would ship it (the environment at its
    start, two small partitions behind it) plus the v4 table that describes it."""

    def __init__(self, directory, env=None):
        self.directory = directory
        self.path = os.path.join(directory, PART)
        part = bytearray(b"\x5a" * (PART_SECTORS * SECT))
        part[0:ENV_BYTES] = env_write(env or NEW_ENV)
        with open(self.path, "wb") as f:
            f.write(part)
        self.table_path = os.path.join(directory, "h713-test.tabelle.json")
        self.write_table()

    def table(self, files=FILES, user=USER, v3=False):
        with open(self.path, "rb") as f:
            blob = f.read()
        d = {
            "format": "hy310-abbild-tabelle-v4", "version": 1, "werkzeug": "the P2 tests",
            "abbild": "h713-test",
            "layout": "v4 (doku/109 section 2.2, files copied through a mount)",
            "sektorgroesse": SECT, "disk_sektoren": fakedisk.DISK_SECTORS,
            "loch": {"lba": fakedisk.LOCK_FIRST, "sektoren": fakedisk.LOCK_SECTORS,
                     "partition": "hy310-keys"},
            "partitionen": [{"name": n, "lba": lba, "sektoren": s} for n, lba, s in (BOOT, ROOTFS)],
            "teile": [{"datei": PART, "lba": PART_LBA, "sektoren": PART_SECTORS,
                       "bytes": len(blob), "sha256": hashlib.sha256(blob).hexdigest()}],
            "bausteine": {"env": {"lba": PART_LBA, "bytes": ENV_BYTES}},
            "dateien": [{"name": n, "partition": p, "pfad": t, "gruppe": g, "optional": o}
                        for n, p, t, g, o in files],
            "gruppen": GROUPS,
            "nutzer": list(user),
        }
        if v3:      # what an image of v0.7-beta and older brings: offsets instead of paths
            d["format"] = "hy310-abbild-tabelle"
            d["layout"] = "v3 (doku/109 §2.2)"
            d["platzhalter_datei"] = PART
            d["platzhalter"] = dict((n, [ENV_BYTES + i * 4096, 4096])
                                    for i, (n, _p, _t, _g, _o) in enumerate(files))
            d["platzhalter_nutzer"] = {}
            for key in ("dateien", "gruppen", "nutzer"):
                del d[key]
        return d

    def write_table(self, **kw):
        d = self.table(**kw)
        with open(self.table_path, "w", encoding="utf-8") as f:
            json.dump(d, f, indent=1)
        return d


class Driven(unittest.TestCase):
    """h713-install as a user drives it. Nothing here writes and nothing here mounts."""

    DISK = "v3"

    def setUp(self):
        support.need((fakedisk.NEEDS_V3 if self.DISK == "v3"
                      else fakedisk.NEEDS_STOCK_GPT) + (TOOL,))
        self.tmp = support.workdir(self)
        name = os.path.join(self.tmp, "emmc-%s.img" % self.DISK)
        self.disk = (fakedisk.make_v3_disk(name) if self.DISK == "v3"
                     else fakedisk.make_stock_gpt_disk(name))
        self.release = Release(self.tmp)
        self.before = fakedisk.journal(self.disk)

    def run_tool(self, *args):
        proc = subprocess.Popen(
            [sys.executable, TOOL] + list(args), stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, cwd=self.tmp,
            env=dict(os.environ, TERM="dumb", LC_ALL="C.UTF-8"))
        return proc.wait(), proc.communicate()[0].decode("utf-8", "replace")

    def install(self, *extra):
        return self.run_tool("install", self.release.table_path, "--device", self.disk, *extra)

    def untouched(self, out):
        self.assertEqual(fakedisk.journal(self.disk), self.before, out)


class OurLayout(Driven):
    """N2 under layout v4: the second install on the same device asks for nothing."""

    def test_it_needs_neither_dump_nor_vendor_and_says_what_it_would_read(self):
        code, out = self.install("--no-write")
        self.assertEqual(code, 0, out)
        self.assertIn("our layout on the device -- nothing stock to save; "
                      "--dump takes one anyway", out)
        self.assertIn("WOULD: read 3 file(s) back from hy310-boot (%s5, LBA 16384)"
                      % self.disk, out)
        self.assertIn("WOULD: read 4 file(s) back from hy310-rootfs", out)
        self.assertIn("WOULD: copy %s to" % PART, out)
        self.assertIn("WOULD: hy310-boot     3 file(s), mounted at offset %d"
                      % ((BOOT[1] - PART_LBA) * SECT), out)
        self.assertNotIn("There is neither --vendor nor a full dump", out)
        self.assertFalse(os.path.exists(os.path.join(self.tmp, "h713-dump")), out)
        self.untouched(out)

    def test_a_rehearsal_mounts_nothing(self):
        _code, out = self.install("--no-write")
        self.assertNotIn("mount -t ext4", out)
        self.assertNotIn("needs root", out)

    def test_a_run_that_means_it_says_in_one_sentence_that_it_needs_root(self):
        """The files go in through a mount, so a run that cannot mount stops at step 4 --
        before the extraction has cost anybody ten minutes and before anything is written."""
        if mountfs.unusable() is None:
            raise unittest.SkipTest("this run can mount (root), so the refusal cannot happen")
        code, out = self.install()                  # no --no-write: this one means it
        self.assertEqual(code, 2, out)
        self.assertIn("mounting the image needs root -- start h713-install with sudo", out)
        self.assertNotIn("Type YES to continue", out)
        self.untouched(out)

    def test_vendor_still_wins_over_the_device(self):
        out_dir = extraction(os.path.join(self.tmp, "vendor"),
                             self.release.table()["dateien"])
        code, out = self.install("--no-write", "--vendor", out_dir)
        self.assertEqual(code, 0, out)
        self.assertIn("7 files from %s" % out_dir, out)
        self.assertNotIn("WOULD: read", out)
        self.assertIn("WOULD: copy %s to" % PART, out)

    def test_the_ssh_key_is_planned_without_any_vendor_file(self):
        key = os.path.join(self.tmp, "id.pub")
        with open(key, "wb") as f:
            f.write(KEY)
        out_dir = extraction(os.path.join(self.tmp, "vendor"),
                             self.release.table()["dateien"])
        code, out = self.install("--no-write", "--vendor", out_dir, "--ssh-key", key)
        self.assertEqual(code, 0, out)
        self.assertIn("authorized_keys: 1 key(s) from %s, %d bytes -> "
                      "/root/.ssh/authorized_keys (mode 0600, root)" % (key, len(KEY)), out)
        self.assertIn("WOULD: hy310-rootfs   5 file(s)", out)      # 4 vendor files plus the key

    def test_a_v3_table_is_refused_with_one_sentence(self):
        self.release.write_table(v3=True)
        code, out = self.install("--no-write")
        self.assertEqual(code, 2, out)
        self.assertIn("this image was built for the placeholder layout v3 - use the installer "
                      "of its release, or a v4 image", out)
        self.assertNotIn("Traceback", out)
        self.untouched(out)


class StockIsUntouched(Driven):
    """A stock device decides exactly as before: the dump is mandatory, and without it and
    without --vendor the run stops with exit 8 and the message it has always printed."""

    DISK = "stock"

    def test_without_a_dump_and_without_vendor_it_is_still_exit_8(self):
        code, out = self.install("--skip-identify", "--no-write", "--small")
        self.assertEqual(code, 8, out)
        self.assertIn("There is neither --vendor nor a full dump in h713-dump.", out)
        self.assertIn("The 7 files (display artefacts, boot logo, firmware, PQ, WLAN) "
                      "stand only", out)
        self.assertNotIn("WOULD: read", out)
        self.assertNotIn("the device has no", out)
        self.untouched(out)

    def test_the_small_dump_is_still_taken_before_anything_else(self):
        code, out = self.install("--skip-identify", "--no-write", "--small")
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
        self.untouched(out)


# ------------------------------------------------------------------ the executor, with root

def root_or_skip():
    """The mounting tests. Two conditions, both named when they are missing: the switch that
    says somebody meant it, and root -- `h713.mountfs` runs `mount` itself and never sudo."""
    if os.environ.get("H713_ROOT_TESTS") != "1":
        raise unittest.SkipTest("mounts: set H713_ROOT_TESTS=1 to run it")
    why = mountfs.unusable()
    if why:
        raise unittest.SkipTest("mounts: %s (start the suite as root)" % why)


class Executor(unittest.TestCase):
    """copy_in/copy_out against a real ext4 that lies at an offset inside a bigger file --
    exactly the way part B carries hy310-boot. Root only."""

    OFFSET, SIZE = 1 << 20, 16 << 20
    ENTRIES = (
        mountfs.Entry("/mips/database.TSE", b"TSE\x01" + b"\x11" * 5000),
        mountfs.Entry("/bootlogo.bmp", b"BM" + b"\x22" * 200000),
        mountfs.Entry("/etc/h713/tvconfig/portmap.cfg", b"[ports]\nhdmi=1\n"),
        mountfs.Entry("/root/.ssh/authorized_keys", KEY, None, 0o600, 0, 0, 0o700),
    )

    def setUp(self):
        root_or_skip()
        self.tmp = support.workdir(self)
        blank = os.path.join(self.tmp, "fs.ext4")
        self.made_with = fakedisk.make_ext4(blank, self.SIZE)
        if not self.made_with:
            raise unittest.SkipTest("neither mke2fs nor the blank ext4 the installer ships")
        self.image = os.path.join(self.tmp, "part-b.img")
        with open(self.image, "wb") as f:      # the file system with something in front of it
            f.write(b"\x5a" * self.OFFSET)
            with open(blank, "rb") as src:
                shutil.copyfileobj(src, f)
            f.write(b"\x5a" * (1 << 20))
        os.remove(blank)
        self.log = Recorder()

    def test_the_files_go_in_and_come_back_byte_for_byte(self):
        mountfs.copy_in(self.image, self.OFFSET, self.SIZE, self.ENTRIES, self.log)
        back = mountfs.copy_out(self.image, self.OFFSET, self.SIZE,
                                [e.path for e in self.ENTRIES], self.log)
        self.assertEqual(sorted(back), sorted(e.path for e in self.ENTRIES))
        for e in self.ENTRIES:
            self.assertEqual(back[e.path], e.data, e.path)
        self.assertIn("mount -t ext4 -o loop,offset=%d,sizelimit=%d" % (self.OFFSET, self.SIZE),
                      self.log.text)
        self.assertEqual(mountfs._leftovers(self.image), [], "a mount was left behind")

    def test_the_projects_own_ext4_reader_sees_the_same_bytes_modes_and_owners(self):
        import pathlib
        from h713.fs.ext4 import Ext4
        from h713.log import Log
        from h713.source import FileSource
        mountfs.copy_in(self.image, self.OFFSET, self.SIZE, self.ENTRIES, self.log)
        source = FileSource(pathlib.Path(self.image))
        try:
            fs = Ext4(source.sub(self.OFFSET, self.SIZE, "part"), None, "part", Log(quiet=True))
            for e in self.ENTRIES:
                self.assertEqual(fs.read(e.path), e.data, e.path)
                inode = fs.inode(fs.path_inode(e.path))
                self.assertEqual(inode["mode"] & 0o7777, e.mode, e.path)
                self.assertEqual((inode["uid"], inode["gid"]), (e.uid, e.gid), e.path)
            directory = fs.inode(fs.path_inode("/root/.ssh"))
            self.assertEqual(directory["mode"] & 0o7777, 0o700)     # sshd's StrictModes
        finally:
            source.fh.close()

    def test_a_mount_left_over_from_an_aborted_run_is_not_taken_over(self):
        with mountfs.mounted(self.image, self.OFFSET, self.SIZE, False, self.log):
            with self.assertRaises(RuntimeError) as caught:
                mountfs.copy_out(self.image, self.OFFSET, self.SIZE, ["/x"], self.log)
        self.assertIn("is still mounted", str(caught.exception))
        self.assertIn("umount", str(caught.exception))


class ReadBackWithRoot(unittest.TestCase):
    """The whole read-back against a device that runs our layout -- small partitions, real
    ext4, the plan and the executor together. Root only."""

    PARTS = [("hy310-spl", 16, 64), ("hy310-uboot", 2048, 10240), ("hy310-keys", 12288, 2048),
             ("hy310-env", 14336, 2048), ("hy310-boot", 16384, 16384),
             ("hy310-rootfs", 32768, 32768)]
    DISK_SECTORS = 131072

    def setUp(self):
        root_or_skip()
        self.tmp = support.workdir(self)
        self.path = os.path.join(self.tmp, "emmc-v4.img")
        fakedisk.make_our_layout_disk(self.path, self.PARTS, self.DISK_SECTORS)
        self.log = Recorder()
        self.tab = {"partitionen": [{"name": n, "lba": lba, "sektoren": s}
                                    for n, lba, s in self.PARTS],
                    "gruppen": GROUPS, "dateien": [
                        {"name": n, "partition": p, "pfad": t, "gruppe": g, "optional": o}
                        for n, p, t, g, o in FILES]}
        for name, lba, sectors in self.PARTS[4:]:
            blank = os.path.join(self.tmp, name + ".ext4")
            if not fakedisk.make_ext4(blank, sectors * SECT):
                raise unittest.SkipTest("no mke2fs for a %d byte file system" % (sectors * SECT))
            with open(self.path, "r+b") as f, open(blank, "rb") as src:
                f.seek(lba * SECT)
                shutil.copyfileobj(src, f)
            os.remove(blank)

    def put(self, leave_out=()):
        """Put the device into the state a finished install leaves behind."""
        want = {}
        for name, part, path, _g, _o in FILES:
            if name in leave_out:
                continue
            want[name] = content(name)
            lba, sectors = [(l, s) for n, l, s in self.PARTS if n == part][0]
            mountfs.copy_in(self.path, lba * SECT, sectors * SECT,
                            [mountfs.Entry(path, want[name])], self.log)
        return want

    def sources(self, leave_out=()):
        want = self.put(leave_out)
        disk = Disk(self.path, writable=False)
        try:
            return want, device_sources(disk, self.tab, self.tab["dateien"], self.log)
        finally:
            disk.close()

    def test_the_bytes_come_back_exactly_as_they_lie_on_the_device(self):
        want, (sources, problem) = self.sources()
        self.assertIsNone(problem, self.log.text)
        self.assertEqual(sources, want)
        self.assertIn("OK 7 files read back from the device", self.log.lines)
        self.assertIn("hy310-boot = %s5" % self.path, self.log.text)
        self.assertEqual(mountfs._leftovers(self.path), [])

    def test_a_missing_optional_file_is_skipped_and_the_run_goes_on(self):
        _want, (sources, problem) = self.sources(leave_out=("boot/bootlogo.bmp",))
        self.assertIsNone(problem, self.log.text)
        self.assertNotIn("boot/bootlogo.bmp", sources)
        self.assertIn("no boot logo", self.log.text)

    def test_a_missing_mandatory_file_names_itself(self):
        _want, (sources, problem) = self.sources(leave_out=("boot/mips/database.TSE",))
        self.assertEqual(sources, {})
        self.assertEqual(problem, "the device has no boot/mips/database.TSE -- give --vendor")

    def test_a_whole_optional_group_missing_is_no_abort(self):
        _want, (sources, problem) = self.sources(leave_out=WLAN)
        self.assertIsNone(problem, self.log.text)
        for name in WLAN:
            self.assertNotIn(name, sources)
        self.assertIn("this firmware has no WLAN firmware", self.log.text)
