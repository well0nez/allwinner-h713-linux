"""TODO 5.11 (Marco 12.10.2026): under sudo, what h713-install writes belongs to the user who ran it, not to root.

give_back() decides what that is: root's, changed since the run started, and a folder the run was pointed at
only when the run made it. These tests run as anybody: lstat is told the files are root's and chown only
records. The real chown as root is H713_ROOT_TESTS=1 (the last class).
"""

import os
import time
import unittest
from unittest import mock

import support                 # imported first: it puts the tests directory on sys.path

import sys
sys.path.insert(0, support.TOOLS)
from h713 import util                                          # noqa: E402

OWNER = (4242, 4343)


class Selection(unittest.TestCase):
    def setUp(self):
        self.tmp = support.workdir(self)
        self.chowned = []
        self.old = set()          # paths that pretend to be older than the run

    def lstat(self, p):
        st = os.stat(p, follow_symlinks=False)
        values = list(st)
        values[4] = 0                                       # st_uid: root's
        result = os.stat_result(values)
        if p in self.old:
            return os.stat_result(values[:9] + [0.0])       # st_ctime (index 9) far in the past
        return result

    def run_give_back(self, roots, existed, since=None):
        since = time.time() - 60 if since is None else since
        with mock.patch.object(util.os, "lstat", self.lstat), \
                mock.patch.object(util.os, "chown", lambda p, *a, **k: self.chowned.append(p)):
            return util.give_back(roots, since, existed, OWNER)

    def make(self, *names):
        for n in names:
            p = os.path.join(self.tmp, n)
            if n.endswith("/"):
                os.makedirs(p, exist_ok=True)
            else:
                os.makedirs(os.path.dirname(p), exist_ok=True)
                with open(p, "wb") as f:
                    f.write(b"x")
        return [os.path.join(self.tmp, n.rstrip("/")) for n in names]

    def test_a_dump_folder_the_run_made_goes_with_everything_in_it(self):
        dump, ss, extract, f = self.make("dump/", "dump/secure-storage.bin", "dump/extract/", "dump/extract/a.bin")
        given, failed = self.run_give_back([dump], {dump: False})
        self.assertEqual((given, failed), (4, 0))
        self.assertEqual(sorted(self.chowned), sorted([dump, ss, extract, f]))

    def test_a_folder_that_was_there_keeps_its_owner_its_new_files_do_not(self):
        dump, ss = self.make("dump/", "dump/secure-storage.bin")
        self.run_give_back([dump], {dump: True})
        self.assertEqual(self.chowned, [ss])

    def test_nothing_older_than_the_run_is_touched(self):
        root, old, new = self.make("rel/", "rel/old.img", "rel/new.img")
        self.old.add(old)
        self.run_give_back([root], {root: True})
        self.assertEqual(self.chowned, [new])

    def test_a_file_named_by_hand_goes_when_the_run_made_it(self):
        (work,) = self.make("elsewhere/filled.img")
        self.run_give_back([work], {work: False})
        self.assertEqual(self.chowned, [work])
        self.chowned = []
        self.run_give_back([work], {work: True})
        self.assertEqual(self.chowned, [])

    def test_a_symbolic_link_is_neither_followed_nor_changed(self):
        dump, target_dir, target = self.make("dump/", "outside/", "outside/secret")
        os.symlink(target, os.path.join(dump, "link"))
        os.symlink(target_dir, os.path.join(dump, "dirlink"))
        self.run_give_back([dump], {dump: False})
        self.assertEqual(self.chowned, [dump])

    def test_a_root_named_twice_counts_once(self):
        dump, f = self.make("dump/", "dump/a")
        given, _ = self.run_give_back([dump, dump], {dump: False})
        self.assertEqual(given, 2)

    def test_a_missing_root_is_no_error(self):
        self.assertEqual(self.run_give_back([os.path.join(self.tmp, "nope")], {}), (0, 0))

    def test_a_file_system_without_owners_counts_and_stops_nothing(self):
        dump, f = self.make("dump/", "dump/a")
        with mock.patch.object(util.os, "lstat", self.lstat), \
                mock.patch.object(util.os, "chown", mock.Mock(side_effect=PermissionError(1, "x"))):
            self.assertEqual(util.give_back([dump], time.time() - 60, {dump: False}, OWNER), (0, 2))

    def test_without_sudo_nothing_happens(self):
        dump, _f = self.make("dump/", "dump/a")
        with mock.patch.object(util, "sudo_owner", lambda: None):
            self.assertEqual(util.give_back([dump], 0, {dump: False}), (0, 0))


class SudoOwner(unittest.TestCase):
    def owner(self, euid, env):
        with mock.patch.object(util.os, "geteuid", lambda: euid), mock.patch.dict(util.os.environ, env, clear=True):
            return util.sudo_owner()

    def test_only_root_under_sudo_from_somebody_else(self):
        self.assertEqual(self.owner(0, {"SUDO_UID": "1000", "SUDO_GID": "1001"}), (1000, 1001))
        self.assertIsNone(self.owner(1000, {"SUDO_UID": "1000", "SUDO_GID": "1001"}))   # not root
        self.assertIsNone(self.owner(0, {}))                                            # root, no sudo
        self.assertIsNone(self.owner(0, {"SUDO_UID": "0", "SUDO_GID": "0"}))            # sudo from root
        self.assertIsNone(self.owner(0, {"SUDO_UID": "x", "SUDO_GID": "1"}))


class AsRoot(unittest.TestCase):
    """The real chown: H713_ROOT_TESTS=1 and the suite as root."""

    def test_the_run_s_files_change_hands_the_folder_that_was_there_does_not(self):
        if os.environ.get("H713_ROOT_TESTS") != "1" or os.geteuid() != 0:
            raise unittest.SkipTest("chown: set H713_ROOT_TESTS=1 and start the suite as root")
        tmp = support.workdir(self)
        before = os.path.join(tmp, "there")
        os.mkdir(before)
        old = os.path.join(before, "old")
        with open(old, "wb") as f:
            f.write(b"o")
        time.sleep(3)                       # the run's mark lies 2 s back (h713-install main): old is older
        since = time.time() - 2
        made = os.path.join(tmp, "made")
        os.makedirs(os.path.join(made, "extract"))
        for p in (os.path.join(made, "secure-storage.bin"), os.path.join(made, "extract", "x"),
                  os.path.join(before, "new")):
            with open(p, "wb") as f:
                f.write(b"n")
        existed = {before: True, made: False}
        given, failed = util.give_back([before, made], since, existed, OWNER)
        owner = lambda p: (os.lstat(p).st_uid, os.lstat(p).st_gid)
        self.assertEqual(failed, 0)
        for p in (made, os.path.join(made, "secure-storage.bin"), os.path.join(made, "extract"),
                  os.path.join(made, "extract", "x"), os.path.join(before, "new")):
            self.assertEqual(owner(p), OWNER, p)
        self.assertEqual(owner(before), (0, 0))
        self.assertEqual(owner(old), (0, 0))
        self.assertEqual(given, 5)


if __name__ == "__main__":
    unittest.main()
