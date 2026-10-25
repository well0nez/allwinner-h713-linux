"""TODO 1.2b: a reinstall over our own layout keeps what the owner and the device set.

Until 25.10.2026 the new rootfs came down with the image's defaults: the device opened the
public access point (wifi.env), the corners were neutral, the SSH host key was new and the
remote unpaired -- put back by hand after every install ("step F" of the supervisor). Now the
installer reads it out of the old rootfs before it writes and puts it into the new one. What
the image owns stays the image's. All values here are made up for the test.
"""

import os
import shutil
import subprocess
import sys
import unittest

import support                 # imported first: it puts the tests directory on sys.path
import fakedisk
from test_install_readback import Driven, Release, extraction, root_or_skip   # noqa: F401

sys.path.insert(0, support.TOOLS)
from h713 import mountfs                                       # noqa: E402
from h713.blockdev import Disk                                 # noqa: E402
from h713.install import (BOARD_FILE, carried_state, device_state,        # noqa: E402
                          ROOTFS_PARTITION)

SECT = 512
Entry = mountfs.Entry
ADAPTER = "00:11:22:33:44:55"          # the dummies release/sperr-scan.py knows (MAC_ATTRAPPEN)
REMOTE = "AA:BB:CC:DD:EE:01"


class Recorder(support.Recorder):
    def error(self, t):
        self.lines.append("ERROR " + t)


def etc(name, data, mode=0o644):
    return Entry("/etc/h713/" + name, data, None, mode, 0, 0, 0o755)


IMAGE = {
    "/etc/h713/*": [etc("wifi.env", b"mode=ap\nssid=h713\n", 0o600),
                    etc("warp.conf", b"warp = on\n"),
                    etc("keystone.conf", b"after_move = off\n"),
                    etc("tv.conf", b"start = last\npreset = last\nsource = auto\n"),
                    etc("osd.conf", b"place = bottom\nseconds = 2.5\n"),
                    etc("keys.conf", b"volume_step = 5\n"),
                    etc("power.conf", b"default = poweroff\n"),
                    etc("features", b"board = hy310\n")],
    "/etc/hostname": [Entry("/etc/hostname", b"hy310\n", None, 0o644, 0, 0, 0o755)],
    "/etc/hosts": [Entry("/etc/hosts", b"127.0.0.1\tlocalhost\n127.0.1.1\thy310\n::1\t\tlocalhost\n",
                         None, 0o644, 0, 0, 0o755)],
}


def device(**over):
    d = {
        "/etc/h713/*": [etc("wifi.env", b"mode=sta\nssid=test-net\npassword=test-password\n", 0o600),
                        etc("warp.conf", b"warp = on\ncorners = 1 2 3 4\n"),
                        etc("keystone.conf", b"after_move = off\n"),         # as the image's
                        etc("keystone-ref", b"counts -1 2 3\n"),
                        etc("panel.env", b"password=test\n", 0o600),
                        etc("lamp.conf", b"mode = low\n"),
                        etc("tv.conf", b"start = manual\npreset = last\n"),
                        etc("osd.conf", b"place = top-right\nseconds = 2.5\n"),
                        etc("keys.conf", b"volume_step = 5\n"),
                        etc("power.conf", b"default = standby\n"),
                        etc("features", b"board = old\n"),
                        etc("board", b"board = hy310\nproject_id = 0x30\n")],
        "/etc/hostname": [Entry("/etc/hostname", b"kino\n", None, 0o644, 0, 0, 0o755)],
        "/etc/ssh/ssh_host_*": [Entry("/etc/ssh/ssh_host_ed25519_key", b"test host key\n", None,
                                      0o600, 0, 0, 0o755),
                                Entry("/etc/ssh/ssh_host_ed25519_key.pub", b"test host key pub\n",
                                      None, 0o644, 0, 0, 0o755)],
        "/var/lib/bluetooth": [Entry("/var/lib/bluetooth/%s/settings" % ADAPTER, b"[General]\n",
                                     None, 0o600, 0, 0, 0o700),
                               Entry("/var/lib/bluetooth/%s/%s/info" % (ADAPTER, REMOTE),
                                     b"[LinkKey]\nKey=00\n", None, 0o600, 0, 0, 0o700)],
        "/var/lib/h713-tv": [Entry("/var/lib/h713-tv/modus", b"hdmi\n", None, 0o644, 0, 0, 0o755)],
    }
    d.update(over)
    return d


class CarriedState(unittest.TestCase):
    """The plan: pure Python on what was read off the device and out of the image."""

    def setUp(self):
        self.log = Recorder()

    def carried(self, dev=None, image=IMAGE, taken=()):
        return dict((e.path, e) for e in carried_state(device() if dev is None else dev, image, taken, self.log))

    def test_the_owners_files_come_along_with_their_modes(self):
        got = self.carried()
        for name in ("wifi.env", "warp.conf", "keystone-ref", "panel.env", "lamp.conf"):
            self.assertIn("/etc/h713/" + name, got, self.log.text)
        self.assertEqual(got["/etc/h713/wifi.env"].data, device()["/etc/h713/*"][0].data)
        self.assertEqual(got["/etc/h713/wifi.env"].mode, 0o600)
        self.assertEqual(got["/etc/h713/panel.env"].mode, 0o600)

    def test_what_equals_the_image_is_not_copied_again(self):
        self.assertNotIn("/etc/h713/keystone.conf", self.carried())

    def test_what_the_image_owns_stays_the_images_and_the_difference_is_said(self):
        got = self.carried()
        for name in ("tv.conf", "osd.conf", "keys.conf", "power.conf", "features"):
            self.assertNotIn("/etc/h713/" + name, got)
        self.assertNotIn(BOARD_FILE, got)
        self.assertIn("/etc/h713/tv.conf stays the image's; the device's differs: "
                      "start = manual (image: last)", self.log.text)
        self.assertIn("place = top-right (image: bottom)", self.log.text)
        self.assertIn("default = standby (image: poweroff)", self.log.text)
        self.assertNotIn("keys.conf stays", self.log.text, "no difference, nothing said")
        self.assertNotIn("seconds", self.log.text)

    def test_host_keys_pairings_and_h713_tv_come_along(self):
        got = self.carried()
        self.assertEqual(got["/etc/ssh/ssh_host_ed25519_key"].mode, 0o600)
        self.assertIn("/etc/ssh/ssh_host_ed25519_key.pub", got)
        info = got["/var/lib/bluetooth/%s/%s/info" % (ADAPTER, REMOTE)]
        self.assertEqual((info.mode, info.dir_mode), (0o600, 0o700))
        self.assertIn("/var/lib/h713-tv/modus", got)

    def test_the_summary_names_files_and_counts_but_no_secret_and_no_address(self):
        self.carried()
        summary = [l for l in self.log.lines if l.startswith("OK carried over from the device: ")]
        self.assertEqual(len(summary), 1, self.log.text)
        for part in ("/etc/h713/wifi.env", "SSH host keys (2 file(s))",
                     "Bluetooth pairings (2 file(s))", "h713-tv's state (1 file(s))",
                     "hostname kino (image: hy310)"):
            self.assertIn(part, summary[0])
        for secret in ("test-net", "test-password", ADAPTER, REMOTE, "LinkKey"):
            self.assertNotIn(secret, self.log.text)

    def test_a_chosen_hostname_comes_along_and_the_hosts_line_follows(self):
        got = self.carried()
        self.assertEqual(got["/etc/hostname"].data, b"kino\n")
        self.assertEqual(got["/etc/hosts"].data,
                         b"127.0.0.1\tlocalhost\n127.0.1.1\tkino\n::1\t\tlocalhost\n")

    def test_the_old_shared_name_and_the_images_own_name_are_not_carried(self):
        for name in (b"hy310\n", b""):
            got = self.carried(device(**{"/etc/hostname": [Entry("/etc/hostname", name)]}),
                               dict(IMAGE, **{"/etc/hostname": [Entry("/etc/hostname", b"hy300pro\n")]}))
            self.assertNotIn("/etc/hostname", got, name)
            self.assertNotIn("/etc/hosts", got, name)
        got = self.carried(device(**{"/etc/hostname": [Entry("/etc/hostname", b"hy310\n")]}))
        self.assertNotIn("/etc/hostname", got)

    def test_an_invalid_hostname_is_said_and_not_carried(self):
        got = self.carried(device(**{"/etc/hostname": [Entry("/etc/hostname", b"no_such name\n")]}))
        self.assertNotIn("/etc/hostname", got)
        self.assertIn("not a valid name", self.log.text)

    def test_a_tree_too_big_is_said_and_left(self):
        got = self.carried(device(**{"/var/lib/bluetooth": None}))
        self.assertFalse([p for p in got if p.startswith("/var/lib/bluetooth/")])
        self.assertIn("WARN Bluetooth pairings: more than 16 MiB on the device - not carried over",
                      self.log.lines)

    def test_an_etc_too_big_is_said_too(self):
        got = self.carried(device(**{"/etc/h713/*": None}))
        self.assertFalse([p for p in got if p.startswith("/etc/h713/")])
        self.assertIn("WARN /etc/h713: more than 16 MiB in its files on the device - none of them "
                      "carried over", self.log.lines)
        self.assertIn("/etc/ssh/ssh_host_ed25519_key", got, "the rest still comes along")

    def test_what_this_run_writes_itself_is_never_overwritten(self):
        got = self.carried(taken={"/etc/h713/lamp.conf"})
        self.assertNotIn("/etc/h713/lamp.conf", got)

    def test_a_device_with_nothing_of_it_says_so(self):
        got = self.carried({}, IMAGE)
        self.assertEqual(got, {})
        self.assertIn("INFO nothing of the owner's settings to carry over from the device",
                      self.log.lines)


class NotOurLayout(unittest.TestCase):
    """A device that does not run our layout has no old rootfs of ours: nothing is read."""

    def test_a_stock_table_gives_nothing_and_mounts_nothing(self):
        support.need(fakedisk.NEEDS_STOCK_GPT)
        tmp = support.workdir(self)
        path = fakedisk.make_stock_gpt_disk(os.path.join(tmp, "stock.img"))
        log = Recorder()
        disk = Disk(path, writable=False)
        try:
            self.assertEqual(device_state(disk, os.path.join(tmp, "work.img"), (None, 0, 0),
                                          (), log), [])
        finally:
            disk.close()
        self.assertEqual(log.lines, [])


class Rehearsal(Driven):
    """h713-install --no-write over our layout says it would carry the settings over."""

    def test_our_layout_says_what_it_would_carry(self):
        code, out = self.install("--no-write")
        self.assertEqual(code, 0, out)
        self.assertIn("WOULD: carry over from the device's hy310-rootfs: /etc/h713, SSH host keys, "
                      "Bluetooth pairings, h713-tv's state, the hostname", out)
        self.untouched(out)


class StockRehearsal(Driven):
    """... and over a stock device it does not: there is no old rootfs of ours."""

    DISK = "stock"

    def test_a_stock_device_carries_nothing(self):
        vendor = extraction(os.path.join(self.tmp, "vendor"), self.release.table()["dateien"])
        code, out = self.install("--skip-identify", "--no-write", "--small", "--vendor", vendor)
        self.assertEqual(code, 0, out)
        self.assertIn("WOULD: copy", out)
        self.assertNotIn("carry over", out)


# ------------------------------------------------------------------ with root: real ext4

class WithRoot(unittest.TestCase):
    """read_tree() and device_state() against real file systems: the device's rootfs in a
    disk of our layout, the image's in a working copy. Root only (H713_ROOT_TESTS=1)."""

    PARTS = [("hy310-spl", 16, 64), ("hy310-uboot", 2048, 10240), ("hy310-keys", 12288, 2048),
             ("hy310-env", 14336, 2048), ("hy310-boot", 16384, 16384),
             ("hy310-rootfs", 32768, 32768)]
    DISK_SECTORS = 131072
    SIZE = 32768 * SECT

    def setUp(self):
        root_or_skip()
        self.tmp = support.workdir(self)
        self.log = Recorder()
        self.disk = os.path.join(self.tmp, "emmc-v4.img")
        fakedisk.make_our_layout_disk(self.disk, self.PARTS, self.DISK_SECTORS)
        blank = os.path.join(self.tmp, "fs.ext4")
        if not fakedisk.make_ext4(blank, self.SIZE):
            raise unittest.SkipTest("no mke2fs for a %d byte file system" % self.SIZE)
        with open(self.disk, "r+b") as f, open(blank, "rb") as src:
            f.seek(32768 * SECT)
            shutil.copyfileobj(src, f)
        self.work = os.path.join(self.tmp, "work.img")      # the rootfs at offset 1 MiB in it
        with open(self.work, "wb") as f, open(blank, "rb") as src:
            f.write(b"\x5a" * (1 << 20))
            shutil.copyfileobj(src, f)
        os.remove(blank)
        self.window = ("work.img", 1 << 20, self.SIZE)
        dev = device()
        self.put(self.disk, 32768 * SECT, [e for v in dev.values() for e in v] +
                 [Entry("/etc/h713/tvconfig/portmap.cfg", b"[ports]\n")])
        self.put(self.work, 1 << 20, [e for v in IMAGE.values() for e in v])
        point = os.path.join(self.tmp, "m")             # a link in the tree is not followed
        os.makedirs(point)
        subprocess.run(["mount", "-o", "loop,offset=%d,sizelimit=%d" % (32768 * SECT, self.SIZE),
                        self.disk, point], check=True)
        try:
            os.symlink("/etc/shadow", os.path.join(point, "var/lib/h713-tv/link"))
        finally:
            subprocess.run(["umount", point], check=True)

    def put(self, path, offset, entries):
        mountfs.copy_in(path, offset, self.SIZE, entries, Recorder())

    def test_read_tree_brings_bytes_modes_and_owners_and_follows_no_link(self):
        got = mountfs.read_tree(self.disk, 32768 * SECT, self.SIZE,
                                ["/etc/h713/*", "/var/lib/bluetooth", "/var/lib/h713-tv",
                                 "/etc/ssh/ssh_host_*", "/nothing/here"], self.log)
        names = [e.path for e in got["/etc/h713/*"]]
        self.assertIn("/etc/h713/wifi.env", names)
        self.assertNotIn("/etc/h713/tvconfig/portmap.cfg", names, "the pattern does not go below")
        info = [e for e in got["/var/lib/bluetooth"] if e.path.endswith("/info")][0]
        self.assertEqual((info.mode, info.uid, info.gid, info.dir_mode), (0o600, 0, 0, 0o700))
        self.assertEqual([e.path for e in got["/var/lib/h713-tv"]], ["/var/lib/h713-tv/modus"])
        self.assertEqual(len(got["/etc/ssh/ssh_host_*"]), 2)
        self.assertEqual(got["/nothing/here"], [])
        self.assertIsNone(mountfs.read_tree(self.disk, 32768 * SECT, self.SIZE,
                                            ["/var/lib/bluetooth"], self.log, limit=8)["/var/lib/bluetooth"])
        self.assertEqual(mountfs._leftovers(self.disk), [])

    def test_the_settings_arrive_in_the_new_rootfs_as_they_were(self):
        disk = Disk(self.disk, writable=False)
        try:
            entries = device_state(disk, self.work, self.window, (), self.log)
        finally:
            disk.close()
        self.assertIn("OK carried over from the device: ", self.log.text)
        self.put(self.work, 1 << 20, entries)
        back = mountfs.read_tree(self.work, 1 << 20, self.SIZE,
                                 ["/etc/h713/*", "/etc/hostname", "/etc/hosts",
                                  "/var/lib/bluetooth", "/etc/ssh/ssh_host_*"], self.log)
        now = dict((e.path, e) for v in back.values() for e in v)
        old = dict((e.path, e) for v in device().values() for e in v)
        for path in ("/etc/h713/wifi.env", "/etc/h713/panel.env", "/etc/ssh/ssh_host_ed25519_key",
                     "/var/lib/bluetooth/%s/%s/info" % (ADAPTER, REMOTE)):
            self.assertEqual((now[path].data, now[path].mode), (old[path].data, old[path].mode), path)
        self.assertEqual(now["/etc/h713/tv.conf"].data, IMAGE["/etc/h713/*"][3].data)
        self.assertEqual(now["/etc/hostname"].data, b"kino\n")
        self.assertIn(b"127.0.1.1\tkino\n", now["/etc/hosts"].data)


if __name__ == "__main__":
    unittest.main()
