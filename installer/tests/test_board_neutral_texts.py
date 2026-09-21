# SPDX-License-Identifier: GPL-2.0
"""R1 item 4: the texts a stranger reads must not name the HY310 unless it is the HY310.

The repository serves several boards (boards/, installer/h713/profiles/, issue #1). Two of the
six user-facing strings that carried the literal named the HY310 where the board is either
irrelevant (the tool's own description) or actually known (the README.txt of a dump). The other
four name the HY310 constants or HY310 files as exactly that and stay.
"""

import argparse
import os
import sys
import unittest

import support                 # imported first: it puts the tests directory on sys.path
import fakedisk

sys.path.insert(0, support.TOOLS)
from h713.dump import DumpResult, board_of, write_manifest                  # noqa: E402
from h713.identify import KNOWN_IMAGES                                      # noqa: E402
from h713.profiles import PROFILES                                          # noqa: E402

TOOL = os.path.join(support.TOOLS, "h713-install")
ROWS = [("secure-storage", 12288, 2048, "0" * 64, "HDCP keys, MAC addresses, serial number")]


class TheDumpReadme(unittest.TestCase):
    def _write(self, board):
        out = support.workdir(self)
        write_manifest(out, DumpResult(ROWS), "/dev/sdb", board)
        with open(os.path.join(out, "README.txt"), encoding="utf-8") as fh:
            return fh.read()

    def test_the_heading_names_the_chip_not_one_board(self):
        text = self._write(None)
        self.assertTrue(text.startswith("Dump of an H713 projector\n"
                                        "=========================\n"), text)
        self.assertNotIn("HY310", text)
        self.assertNotIn("Board:", text)          # nothing identified it, so nothing is claimed

    def test_the_board_is_named_where_the_identification_knew_it(self):
        self.assertIn("Board: HY300 Pro.", self._write("HY300 Pro"))
        self.assertIn("Board: HY310.", self._write("HY310"))

    def test_the_board_comes_out_of_the_profile_identify_settled_on(self):
        args = argparse.Namespace(_profile=PROFILES["hy300_pro"])
        self.assertEqual(board_of(args), "HY300 Pro")
        self.assertIsNone(board_of(argparse.Namespace()))            # --skip-identify
        self.assertIsNone(board_of(argparse.Namespace(_profile=None)))


class TheToolsOwnDescription(unittest.TestCase):
    def test_the_help_text_names_no_single_board(self):
        support.need([TOOL])
        import importlib.machinery
        import importlib.util
        spec = importlib.util.spec_from_loader(
            "h713_install_r1", importlib.machinery.SourceFileLoader("h713_install_r1", TOOL))
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        text = module.parser().format_help()
        self.assertIn("Turn an H713 projector over to Linux", text)
        self.assertNotIn("HY310", text)


class WhatStays(unittest.TestCase):
    """The HY310 belongs in a text that is about the HY310: the fallback LBAs and the image
    digests. A test, so that a later board-neutral sweep does not take the truth with it."""

    def test_the_known_image_digests_still_name_the_board_they_are_of(self):
        named = [what for _profile, what in KNOWN_IMAGES.values() if what.startswith("HY310")]
        self.assertEqual(len(named), 3, KNOWN_IMAGES)

    def test_the_fallback_still_says_whose_lbas_it_borrows(self):
        import h713.dump as dump
        with open(dump.__file__, encoding="utf-8") as fh:
            source = fh.read()
        self.assertIn("Saved from the HY310's own LBAs instead", source)


if __name__ == "__main__":
    unittest.main()
