# SPDX-License-Identifier: GPL-2.0
"""FB-INSTALL item 4: FLASHING.md's command lines are real ones -- every `h713-install ...` in
a code block parses with the installer's own parser, so a flag the page shows exists -- and the
page says how a test image installs a second time (26.09.2026, _board_from_dump)."""

import contextlib
import importlib.machinery
import importlib.util
import io
import os
import shlex
import sys
import unittest

import support                 # imported first: it puts the tests directory on sys.path

sys.path.insert(0, support.TOOLS)
from h713.install import COMMANDS                    # noqa: E402

FLASHING = os.path.normpath(os.path.join(support.TOOLS, "..", "FLASHING.md"))
TOOL = os.path.join(support.TOOLS, "h713-install")
SECTION = "## Reinstalling a test image"


def command_lines(text):
    """[(line, argv)] for every h713-install command in a fenced code block: continuation
    lines joined, `sudo`, `cd ... &&` and the path in front of the tool dropped. Only a line
    whose first word after the tool is a subcommand counts -- the recorded run starts with
    `h713-install 0.1 (...)`, which is no command."""
    found, block = [], None
    for line in text.splitlines():
        if line.startswith("```"):
            block = [] if block is None else None
        elif block is not None:
            if block and block[-1].endswith("\\"):
                block[-1] = block[-1][:-1].rstrip() + " " + line.strip()
            else:
                block.append(line)
            for line in block[-1:] if "h713-install" in block[-1] else ():
                try:
                    words = shlex.split(line, comments=True)
                except ValueError:
                    continue
                at = [i for i, w in enumerate(words) if os.path.basename(w) == "h713-install"]
                if at and words[at[0] + 1:at[0] + 2] and words[at[0] + 1] in COMMANDS:
                    found.append((line, words[at[0] + 1:]))
    # a joined line was seen twice, once cut at the backslash: keep the whole one
    return [(line, argv) for line, argv in found if not line.endswith("\\")]


def _page():
    support.need([FLASHING])
    with open(FLASHING, encoding="utf-8") as fh:
        return fh.read()


class TheCommandLinesParse(unittest.TestCase):
    def test_every_h713_install_line_in_a_code_block_parses(self):
        support.need([TOOL])
        lines = command_lines(_page())
        self.assertGreaterEqual(len(lines), 3, lines)
        spec = importlib.util.spec_from_loader(
            "h713_install_flashing", importlib.machinery.SourceFileLoader("h713_install_flashing", TOOL))
        tool = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(tool)
        parser = tool.parser()
        for line, argv in lines:
            with contextlib.redirect_stderr(io.StringIO()):
                try:
                    parser.parse_args(argv)
                except SystemExit:
                    self.fail("does not parse: %s" % line)

    def test_the_reader_finds_what_it_should_and_nothing_else(self):
        text = ("```bash\nsudo x/h713-install install ~/rel \\\n    --full --dump ~/d\n```\n"
                "```\nh713-install 0.1 (draft)   (Linux)\n  h713-extract emmc-full.img -> x\n```\n"
                "h713-install identify FILE  (prose, not a block)\n")
        self.assertEqual(command_lines(text),
                         [("sudo x/h713-install install ~/rel --full --dump ~/d",
                           ["install", "~/rel", "--full", "--dump", "~/d"])])


class TheSecondInstallOfATestImage(unittest.TestCase):
    def _section(self):
        text = _page()
        self.assertIn(SECTION, text)
        start = text.index(SECTION)
        return text[start:text.index("\n## ", start + 1)]

    def test_the_page_names_what_the_run_needs(self):
        section = self._section()
        for needle in ("--test-image", "--dump", "emmc-full.img", "exit 1", "--skip-identify",
                       "the board is known from the dump of the first install",
                       "no board we know", "its files are kept"):
            self.assertIn(needle, section, needle)
        lines = command_lines(section)
        self.assertEqual(len(lines), 1, lines)
        self.assertEqual(lines[0][1][0], "install")
        self.assertTrue({"--test-image", "--dump"} <= set(lines[0][1]), lines)

    def test_the_lines_it_quotes_are_the_installers_own(self):
        """The quoted run comes from h713-install and h713.install; a rewording there would
        leave the page quoting a run nobody sees."""
        import h713.install
        sources = ""
        for path in (TOOL, h713.install.__file__):
            with open(path, encoding="utf-8") as fh:
                sources += fh.read()
        for needle in ("the board is known from the dump of the first", "its files are kept",
                       "this device is that board, and --test-image was given", "no board we know"):
            self.assertIn(needle, sources, needle)


if __name__ == "__main__":
    unittest.main()
