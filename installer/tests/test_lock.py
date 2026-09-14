"""The write lock as a contract (stage 2 C-B, brief CB §4).

`Disk(path, writable=, exclusive=, locked=)` and `Disk.lock_regions(regions)`: besides
the built-in secure-storage block a caller locks the regions that exist only on this one
device. The numbers here are the HY300 T08's -- private at LBA 6988800 (32768 sectors),
the first sector behind it belongs to dtbo_a. A plain sparse file is enough: the lock is
a property of the Disk, not of a partition table.
"""

import os
import sys
import unittest

import support                 # imported first: it puts the work dir on sys.path
import fakedisk

SECT = fakedisk.SECT
PRIVATE_FIRST, PRIVATE_LAST = 6988800, 7021567      # T08 private, 32768 sectors
BEHIND_IT = PRIVATE_LAST + 1                        # dtbo_a
PAYLOAD = fakedisk.pattern("lock-test", 0, 8)


def _blockdev():
    """h713.blockdev -- the lock contract is package API; the stand-alone script of
    v0.5-beta (run.sh --old) has none, there the test skips."""
    if support.TOOLS not in sys.path:
        sys.path.insert(0, support.TOOLS)
    try:
        import h713.blockdev as blockdev
    except ImportError as e:
        raise unittest.SkipTest("no h713 package in %s (%s)" % (support.TOOLS, e))
    if not hasattr(blockdev.Disk, "lock_regions"):
        raise unittest.SkipTest("Disk.lock_regions(): stage 2 C-B, not in these tools")
    return blockdev


class WriteLock(unittest.TestCase):
    def setUp(self):
        self.blockdev = _blockdev()
        self.path = os.path.join(support.workdir(self), "emmc.img")
        with open(self.path, "wb") as fh:          # sparse: nothing is really allocated
            fh.truncate(fakedisk.DISK_SECTORS * SECT)

    def _disk(self, **kw):
        disk = self.blockdev.Disk(self.path, writable=True, **kw)
        self.addCleanup(disk.close)
        return disk

    def _refused(self, disk, lba):
        with self.assertRaises(RuntimeError) as caught:
            disk.write(lba, PAYLOAD)
        self.assertEqual(disk.read(lba, 8), b"\0" * (8 * SECT))     # nothing was written
        return str(caught.exception)

    def test_a_locked_region_refuses_the_write(self):
        disk = self._disk(locked=[(PRIVATE_FIRST, PRIVATE_LAST)])
        said = self._refused(disk, PRIVATE_FIRST)
        self.assertIn("%d..%d" % (PRIVATE_FIRST, PRIVATE_FIRST + 7), said)
        self.assertIn("LBA %d..%d" % (PRIVATE_FIRST, PRIVATE_LAST), said)
        # a pair without a name cannot name a region -- it says so instead of inventing one
        self.assertIn("a locked region", said)

    def test_a_write_that_only_touches_the_edge_is_refused_too(self):
        disk = self._disk(locked=[(PRIVATE_FIRST, PRIVATE_LAST)])
        self._refused(disk, PRIVATE_FIRST - 4)                      # reaches into it
        self._refused(disk, PRIVATE_LAST - 1)                       # starts inside it

    def test_a_write_next_to_it_still_works(self):
        disk = self._disk(locked=[(PRIVATE_FIRST, PRIVATE_LAST)])
        for lba in (PRIVATE_FIRST - 8, BEHIND_IT):
            disk.write(lba, PAYLOAD)
            self.assertEqual(disk.read(lba, 8), PAYLOAD, lba)

    def test_lock_regions_after_opening_behaves_the_same(self):
        """The installer learns the regions only after it has opened the disk."""
        disk = self._disk()
        disk.write(PRIVATE_FIRST, PAYLOAD)                          # still open
        disk.lock_regions({"private": (PRIVATE_FIRST, 32768)})      # as identify() returns it
        said = self._refused(disk, BEHIND_IT - 4)
        self.assertIn("the locked region 'private'", said)          # the message names it
        self.assertEqual(disk.read(PRIVATE_FIRST, 8), PAYLOAD)      # the old write stands
        disk.write(BEHIND_IT, PAYLOAD)                              # behind it: still free

    def test_the_same_region_twice_stays_one_lock(self):
        disk = self._disk(locked=[(PRIVATE_FIRST, PRIVATE_LAST, "private")])
        disk.lock_regions([(PRIVATE_FIRST, PRIVATE_LAST, "private")])
        self.assertEqual(disk.locked, [(PRIVATE_FIRST, PRIVATE_LAST, "private")])

    def test_the_built_in_secure_storage_lock_is_untouched(self):
        disk = self._disk(locked=[(PRIVATE_FIRST, PRIVATE_LAST)])
        said = self._refused(disk, self.blockdev.LOCK_FIRST)
        self.assertIn("Secure Storage", said)                       # unchanged, still German
        self.assertEqual(disk.locked, [(PRIVATE_FIRST, PRIVATE_LAST, None)])
