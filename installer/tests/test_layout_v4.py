"""Layout v4: the image carries directories, not placeholders (plan/briefs/P-layout-v4.md).

The three things that have to hold for an image built by this tool to be installable at all:

  1. the table says exactly what `h713.layout` says -- the installer reads the table and
     never the module, so a difference between the two is the one bug nobody would see;
  2. neither of the two file trees carries a vendor file, and the target directories are
     there with the modes the installer needs;
  3. a table of layout v3 (v0.7-beta and older, placeholders at fixed offsets) is refused
     with a sentence that says what to do, instead of being read half way.

Nothing here freezes a digest: every value is derived from `h713.layout`, which is the
truth this package moved.
"""

import json
import os
import sys
import unittest

import support                 # imported first: it puts the tests directory on sys.path
import fakedisk

sys.path.insert(0, support.TOOLS)
from h713 import layout                                              # noqa: E402
from h713.mkimage import (LAYOUT, TABLE_FORMAT, TABLE_FORMAT_V3,     # noqa: E402
                          check, file_table, partition_slices, tree_boot, tree_rootfs)

PLACEHOLDER_KEYS = ("platzhalter", "platzhalter_nutzer", "platzhalter_datei", "platzhalter_info")


class TheTableIsTheFileList(unittest.TestCase):
    def test_dateien_is_layout_FILES(self):
        rows = file_table()["dateien"]
        self.assertEqual(len(rows), len(layout.FILES))
        self.assertEqual(rows, [{"name": f.name, "partition": f.partition, "pfad": f.path,
                                 "gruppe": f.group, "optional": f.optional}
                                for f in layout.FILES])

    def test_every_file_has_a_group_that_the_table_explains(self):
        groups = file_table()["gruppen"]
        self.assertEqual(sorted(groups), sorted({f.group for f in layout.FILES}))
        for group, what in groups.items():
            self.assertTrue(what and what == what.strip(), group)

    def test_the_user_file_carries_its_modes_as_modes(self):
        self.assertEqual(file_table()["nutzer"],
                         [{"name": "authorized_keys", "partition": "hy310-rootfs",
                           "pfad": "/root/.ssh/authorized_keys", "modus": "0600",
                           "besitzer": "root", "verzeichnis_modus": "0700"}])

    def test_no_entry_carries_a_size_any_more(self):
        for row in file_table()["dateien"]:
            self.assertEqual(sorted(row), ["gruppe", "name", "optional", "partition", "pfad"])

    def test_the_table_is_json_and_nothing_in_it_is_a_placeholder(self):
        text = json.dumps(file_table())
        for key in PLACEHOLDER_KEYS:
            self.assertNotIn(key, text)

    def test_44_files_22_of_them_optional(self):
        """The number is not a golden value but the count of a firmware's parts; it moves
        only when a file joins or leaves, and then this line says so."""
        self.assertEqual(len(layout.FILES), 44)
        self.assertEqual(sum(1 for f in layout.FILES if f.optional), 22)


class TheTreesCarryNoFile(unittest.TestCase):
    def setUp(self):
        self.tmp = support.workdir(self)

    def _tree(self, which, **kw):
        directory = os.path.join(self.tmp, which)
        os.makedirs(directory)
        (tree_boot if which == "boot" else tree_rootfs)(directory, log=support.Recorder(), **kw)
        return directory

    def _files_below(self, directory):
        out = []
        for here, _dirs, names in os.walk(directory):
            out += [os.path.relpath(os.path.join(here, n), directory) for n in names]
        return sorted(out)

    def test_the_boot_tree_holds_the_kernel_and_nothing_else(self):
        fit = os.path.join(self.tmp, "fake.fit")
        with open(fit, "wb") as fh:
            fh.write(b"\xd0\x0d\xfe\xed" + b"\0" * 1020)
        directory = self._tree("boot", fit=fit)
        self.assertEqual(self._files_below(directory), [layout.KERNEL_FIT])

    def test_the_rootfs_tree_holds_no_file_at_all(self):
        self.assertEqual(self._files_below(self._tree("rootfs")), [])

    def test_the_target_directories_are_there_with_their_modes(self):
        for which, partition in (("boot", "hy310-boot"), ("rootfs", "hy310-rootfs")):
            directory = self._tree(which)
            for path, mode in layout.target_directories(partition):
                full = os.path.join(directory, path.lstrip("/"))
                self.assertTrue(os.path.isdir(full), full)
                self.assertEqual(os.stat(full).st_mode & 0o7777, mode, full)

    def test_not_one_of_the_44_files_is_written(self):
        for which, partition in (("boot", "hy310-boot"), ("rootfs", "hy310-rootfs")):
            directory = self._tree(which)
            for f in layout.FILES:
                if f.partition != partition:
                    continue
                self.assertFalse(os.path.exists(os.path.join(directory, f.path.lstrip("/"))),
                                 f.name)

    def test_authorized_keys_is_not_written_either(self):
        directory = self._tree("rootfs")
        self.assertTrue(os.path.isdir(os.path.join(directory, "root/.ssh")))
        self.assertFalse(os.path.exists(os.path.join(directory, "root/.ssh/authorized_keys")))


class WhereThePartitionsSit(unittest.TestCase):
    """What the installer mounts: the derivation out of `partitionen` and `teile` alone."""

    def _table(self):
        return {"partitionen": [{"name": n, "lba": l, "sektoren": s, "guid": g}
                                for n, l, s, g in layout.PARTITIONS],
                "teile": [{"datei": "x-a-bootkette.img", "lba": 0, "bytes": 12288 * 512},
                          {"datei": "x-b-system.img", "lba": layout.PART_B_LBA,
                           "bytes": (layout.LBA_ROOTFS - layout.PART_B_LBA) * 512 + (1 << 30)}]}

    def test_the_two_file_systems_are_found_in_piece_b(self):
        where = partition_slices(self._table())
        self.assertEqual(where["hy310-boot"],
                         ("x-b-system.img", (layout.LBA_BOOT - layout.PART_B_LBA) * 512,
                          262144 * 512))
        self.assertEqual(where["hy310-rootfs"][:2],
                         ("x-b-system.img", (layout.LBA_ROOTFS - layout.PART_B_LBA) * 512))

    def test_a_partition_never_reaches_past_the_piece(self):
        """hy310-rootfs is 7.15 GiB on the device and 1 GiB in the image -- the shorter
        of the two is what may be mounted."""
        self.assertEqual(partition_slices(self._table())["hy310-rootfs"][2], 1 << 30)

    def test_the_boot_chain_is_found_in_piece_a(self):
        where = partition_slices(self._table())
        self.assertEqual(where["hy310-spl"], ("x-a-bootkette.img", 16 * 512, 64 * 512))
        self.assertEqual(where["hy310-env"], ("x-b-system.img", 0, 2048 * 512))

    def test_the_locked_partition_lies_in_no_piece_at_all(self):
        """hy310-keys is the secure storage: piece A ends one sector before it and piece B
        starts after it. Nothing can be derived for it, which is the point."""
        self.assertNotIn("hy310-keys", partition_slices(self._table()))


class AV3TableIsRefused(unittest.TestCase):
    def _v3(self, directory, name="old.tabelle.json"):
        os.makedirs(directory, exist_ok=True)
        path = os.path.join(directory, name)
        with open(path, "w", encoding="utf-8") as fh:
            json.dump({"format": TABLE_FORMAT_V3, "version": 1, "layout": "v3 (doku/109 §2.2)",
                       "platzhalter_datei": "x-b-system.img", "platzhalter": {},
                       "teile": []}, fh)
        return path

    def test_check_says_what_it_is_and_what_to_do(self):
        with self.assertRaises(SystemExit) as caught:
            check(self._v3(support.workdir(self)))
        text = str(caught.exception)
        self.assertIn("layout v3", text)
        self.assertIn("layout v4", text)
        self.assertIn("v0.7-beta", text)

    def test_the_released_v05_beta_table_is_refused_the_same_way(self):
        released = os.path.join(fakedisk.FIXTURES, "release",
                                "h713-hy310-v0.5-beta.tabelle.json")
        support.need([released])
        with self.assertRaises(SystemExit) as caught:
            check(released)
        self.assertIn("layout v3", str(caught.exception))

    def test_something_that_is_no_table_at_all_is_still_refused(self):
        path = os.path.join(support.workdir(self), "other.json")
        with open(path, "w", encoding="utf-8") as fh:
            json.dump({"format": "something-else"}, fh)
        with self.assertRaises(SystemExit) as caught:
            check(path)
        self.assertIn("is not an image table", str(caught.exception))

    def test_the_two_format_strings_differ(self):
        self.assertNotEqual(TABLE_FORMAT, TABLE_FORMAT_V3)
        self.assertTrue(TABLE_FORMAT.startswith(TABLE_FORMAT_V3))
        self.assertIn("v4", LAYOUT)


if __name__ == "__main__":
    unittest.main()
