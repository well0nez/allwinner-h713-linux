"""A reinstall over our own layout keeps the board: /etc/h713/board is read back out of the
installed rootfs (h713.install.board_from_device), written again, and h713_project follows
it. Before 04.10.2026 such a run wrote no board file and left U-Boot on the image's default
project - the HY310 lost its board record in the v0.96-beta device test, and the HY300 Pro of
issue #1 ran project 0x30 in test9 the same way."""

import argparse
import importlib.machinery
import importlib.util
import os
import sys
import unittest
from unittest import mock

import support                 # puts the work dir on sys.path

sys.path.insert(0, support.TOOLS)
from h713 import install as inst                                             # noqa: E402
from h713.log import Quiet                                                   # noqa: E402


def _cli():
    path = os.path.join(support.TOOLS, "h713-install")
    spec = importlib.util.spec_from_loader("h713_install_cli",
                                           importlib.machinery.SourceFileLoader("h713_install_cli", path))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


WRITTEN = inst.board_entry("hy310", {"panel": {"declared_project_id": 0x30}}).data


class ParseBoardFile(unittest.TestCase):
    def test_what_board_entry_writes_reads_back(self):
        self.assertEqual(inst.parse_board_file(WRITTEN), ("hy310", 0x30, None))

    def test_variant_board_and_its_project(self):
        from h713.profiles import get
        profile = get("hy200_qz713df_a1/projector05061226")
        data = inst.board_entry(profile["id"], profile).data
        self.assertIn(b"board = hy200-qz713df-a1\n", data)
        self.assertIn(b"variant = projector05061226\n", data)
        self.assertEqual(inst.parse_board_file(data), ("hy200-qz713df-a1", 0x34, "projector05061226"))

    def test_what_is_not_in_its_shape_is_dropped(self):
        for text, want in ((b"", (None, None, None)),
                           (b"# board = hy310\n", (None, None, None)),
                           (b"board = ../etc\nproject_id = 0x30\n", (None, 0x30, None)),
                           (b"board = hy310\nproject_id = 48\n", ("hy310", None, None)),
                           (b"board = hy310\nproject_id = 0x1234\n", ("hy310", None, None)),
                           (b"board = hy310\nproject_id = 0xzz\n", ("hy310", None, None)),
                           (b"board = x\nvariant = ../v\n", ("x", None, None)),
                           (b"\xff\xfe board = hy310", (None, None, None))):
            self.assertEqual(inst.parse_board_file(text), want, text)

    def test_the_profile_project_is_the_default_and_the_device_one_wins(self):
        profile = {"panel": {"declared_project_id": 0x30}}
        self.assertIn(b"project_id = 0x30", inst.board_entry("hy310", profile).data)
        self.assertIn(b"project_id = 0x34", inst.board_entry("hy310", profile, 0x34).data)
        self.assertIsNone(inst.board_entry("hy200_qz713df_a1", {"panel": {}}))
        self.assertIsNone(inst.board_entry(None, profile, 0x30))


class FakeDisk:
    path = "/dev/fake"


class BoardFromDevice(unittest.TestCase):
    PARTS = {"hy310-boot": (5, 16384, 262144), "hy310-rootfs": (6, 278528, 14991327)}

    def test_read_through_the_rootfs_window_read_only(self):
        with mock.patch.object(inst, "gpt_partitions", return_value=self.PARTS), \
                mock.patch.object(inst.mountfs, "copy_out",
                                  return_value={inst.BOARD_FILE: WRITTEN}) as copy_out:
            self.assertEqual(inst.board_from_device(FakeDisk(), Quiet()), ("hy310", 0x30, None))
        source, offset, size, paths = copy_out.call_args[0][:4]
        self.assertEqual((source, offset, size, paths),
                         ("/dev/fake", 278528 * 512, 14991327 * 512, [inst.BOARD_FILE]))

    def test_nothing_there_is_none(self):
        with mock.patch.object(inst, "gpt_partitions", return_value={}):
            self.assertEqual(inst.board_from_device(FakeDisk(), Quiet()), (None, None, None))
        with mock.patch.object(inst, "gpt_partitions", return_value=self.PARTS), \
                mock.patch.object(inst.mountfs, "copy_out", return_value={}):
            self.assertEqual(inst.board_from_device(FakeDisk(), Quiet()), (None, None, None))

    def test_a_mount_that_fails_is_said_and_does_not_stop_the_run(self):
        with mock.patch.object(inst, "gpt_partitions", return_value=self.PARTS), \
                mock.patch.object(inst.mountfs, "copy_out", side_effect=RuntimeError("no mount")):
            self.assertEqual(inst.board_from_device(FakeDisk(), Quiet()), (None, None, None))


class TheInstallTakesIt(unittest.TestCase):
    def _args(self):
        return argparse.Namespace(command="install", _profile=None, _board=None, _env_keys={})

    def test_board_profile_project_and_env(self):
        cli = _cli()
        args = self._args()
        with mock.patch.object(cli, "board_from_device", return_value=("hy310", 0x30, None)), \
                support.quiet():
            cli._board_from_device(args, FakeDisk())
        self.assertEqual((args._board, args._board_project), ("hy310", 0x30))
        self.assertEqual(args._env_keys, {"h713_project": "0x30"})
        entry = inst.board_entry(args._board, args._profile, args._board_project)
        self.assertEqual(entry.data, WRITTEN)

    def test_a_board_without_a_profile_is_not_taken(self):
        cli = _cli()
        args = self._args()
        with mock.patch.object(cli, "board_from_device", return_value=("not-a-board", 0x30, None)), \
                support.quiet():
            cli._board_from_device(args, FakeDisk())
        self.assertEqual((args._profile, args._board, args._env_keys), (None, None, {}))

    def test_a_variant_board_resolves_to_its_firmware(self):
        cli = _cli()
        args = self._args()
        with mock.patch.object(cli, "board_from_device",
                               return_value=("hy200-qz713df-a1", 0x34, "projector05061226")), \
                support.quiet():
            key = cli._board_from_device(args, FakeDisk())
        self.assertEqual(key, "hy200_qz713df_a1/projector05061226")
        self.assertEqual((args._profile["variant"], args._env_keys), ("projector05061226", {"h713_project": "0x34"}))
        with mock.patch.object(cli, "board_from_device",
                               return_value=("hy200-qz713df-a1", 0x34, "no-such-firmware")), \
                support.quiet():
            self.assertIsNone(cli._board_from_device(self._args(), FakeDisk()))

    def test_no_board_file_leaves_the_run_as_it_was(self):
        cli = _cli()
        args = self._args()
        with mock.patch.object(cli, "board_from_device", return_value=(None, None, None)), \
                support.quiet():
            cli._board_from_device(args, FakeDisk())
        self.assertEqual((args._profile, args._board, args._env_keys), (None, None, {}))


if __name__ == "__main__":
    unittest.main()
