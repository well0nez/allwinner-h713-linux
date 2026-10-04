"""A board whose eMMC is not the HY310's size (the HY300PRO-G-EU: 15273600 sectors) is found and dumped.

No device and no vendor file: the drive search is fed a fake /sys/block, and the profile is compared
with the sector counts the installer accepts.
"""

import os
import sys
import unittest
from unittest import mock

import support                 # imported first: it puts the work dir on sys.path

sys.path.insert(0, support.TOOLS)
from h713 import blockdev                                       # noqa: E402
from h713.profiles import units                                 # noqa: E402


class DriveSizes(unittest.TestCase):

    def test_every_profile_size_is_known(self):
        for board_id, profile in units().items():           # a variant's size is its own
            sectors = (profile.get("layout") or {}).get("disk_sectors")
            if sectors:
                self.assertIn(sectors, blockdev.SECTORS_KNOWN, board_id)

    def test_the_writing_size_stays_the_hy310_one(self):
        self.assertEqual(blockdev.SECTORS_EXPECTED, 15269888)
        self.assertIn(blockdev.SECTORS_EXPECTED, blockdev.SECTORS_KNOWN)

    def _sys_block(self, sectors):
        files = {"/sys/block/sdz/size": "%d\n" % sectors, "/sys/block/sdz/removable": "1\n"}

        def fake_open(path, *a, **kw):
            if path in files:
                return mock.mock_open(read_data=files[path])()
            raise OSError(path)
        return mock.patch.object(blockdev, "open", fake_open, create=True), \
            mock.patch.object(os, "listdir", lambda p: ["sdz"] if p == "/sys/block" else [])

    def test_find_drive_takes_the_larger_emmc(self):
        for sectors in (15269888, 15273600):
            a, b = self._sys_block(sectors)
            with a, b, mock.patch("platform.system", return_value="Linux"):
                self.assertEqual(blockdev.find_drive(), [("/dev/sdz", sectors, True)])

    def test_find_drive_refuses_a_foreign_size(self):
        a, b = self._sys_block(15273601)
        with a, b, mock.patch("platform.system", return_value="Linux"):
            self.assertEqual(blockdev.find_drive(), [])

    def test_find_drive_still_takes_one_number(self):
        a, b = self._sys_block(15273600)
        with a, b, mock.patch("platform.system", return_value="Linux"):
            self.assertEqual(blockdev.find_drive(15269888), [])
            self.assertEqual(len(blockdev.find_drive(15273600)), 1)


if __name__ == "__main__":
    unittest.main()
