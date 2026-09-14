# SPDX-License-Identifier: GPL-2.0
"""Writing an image onto the eMMC and reading it back in samples.

Stage 1 of plan doku/121: moved from hy310-install.py (I:575-612, 627-655).
Every printed string and every exception text is unchanged.
"""

from __future__ import annotations

import os
import random
import time

from .blockdev import LOCK_FIRST, LOCK_LAST, SECT, _around_lock
from .log import console
from .util import duration, mib


def write_image(disk, file, log=console, lba0=0):
    """Our image onto the eMMC. The lock in Disk.write() keeps the secure
    storage free -- the image is built so that it leaves it out.

    'lba0' is the sector at which the file begins. Our image comes in three
    pieces (hy310-mkimage): one from 0, one from 14336, one at the end of the
    disk. A full dump is one piece from 0 -- the default."""
    total = os.path.getsize(file)
    if lba0 * SECT + total > disk.sectors * SECT:
        raise RuntimeError("image (%.1f MiB from LBA %d) is bigger than the eMMC"
                           % (mib(total), lba0))
    chunk = 4 << 20
    done = 0
    t0 = time.time()
    with open(file, "rb") as f:
        while True:
            b = f.read(chunk)
            if not b:
                break
            lba = lba0 + done // SECT
            end = lba + (len(b) + SECT - 1) // SECT - 1
            if lba <= LOCK_LAST and end >= LOCK_FIRST:
                # The piece overlaps the protected block: split it into three
                # parts and leave the middle one out.
                for part_lba, part in _around_lock(lba, b):
                    disk.write(part_lba, part)
            else:
                disk.write(lba, b)
            done += len(b)
            if done % (128 << 20) == 0 or done == total:
                speed = done / max(time.time() - t0, 0.001)
                log.info("  %5.1f%%  %6.1f MiB/s  %s left" %
                         (100.0 * done / total, mib(speed),
                          duration((total - done) / max(speed, 1))))
    disk.sync()
    return time.time() - t0


def verify_image(disk, file, samples=6, log=console, lba0=0):
    """Compare back in samples after writing."""
    total = os.path.getsize(file)
    errors = 0
    with open(file, "rb") as f:
        places = [0, total - (1 << 20)]
        places += [random.randrange(0, max(total - (1 << 20), 1))
                   for _ in range(samples - 2)]
        for off in places:
            off -= off % SECT
            if off < 0:
                continue
            lba = lba0 + off // SECT
            if lba <= LOCK_LAST and lba + 2048 >= LOCK_FIRST:
                continue                       # the locked block, different on purpose
            f.seek(off)
            want = f.read(1 << 20)
            if not want:
                continue
            got = disk.read(lba, len(want) // SECT)
            if got != want:
                log.warn("mismatch at LBA %d" % lba)
                errors += 1
    return errors
