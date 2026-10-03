# SPDX-License-Identifier: GPL-2.0
"""FB-INSTALL item 3 (doku/61 row 100, A1): the PC tools stay within Python 3.9. The check is
tools/check-py39.py; here it runs over the installer directory, and against controls that it
must catch or let through -- on whatever interpreter runs the tests, since none of them is 3.9."""

import importlib.machinery
import importlib.util
import os
import subprocess
import sys
import unittest

import support                 # imported first: it puts the tests directory on sys.path

CHECK = os.path.normpath(os.path.join(support.TOOLS, "..", "tools", "check-py39.py"))
FUTURE = "from __future__ import annotations\n"
# (source, findings expected, a word the first finding must carry)
CONTROLS = [
    ("def f(x: int | None) -> str | None:\n    return None\n", 2, "PEP 604"),
    (FUTURE + "def f(x: int | None) -> str | None:\n    return None\n", 0, ""),
    ("x: int | None = None\n", 1, "PEP 604"),
    ("class C:\n    x: int | None = None\n", 1, "PEP 604"),
    ("def f():\n    x: int | None = None\n    return x\n", 0, ""),          # never evaluated
    ("def f(x: 'int | None'):\n    return x\n", 0, ""),                      # a string is fine
    ("def f(x: list[int]) -> dict[str, int]:\n    return {}\n", 0, ""),    # PEP 585 is 3.9
    ("def g():\n    def f(x: int | None):\n        return x\n", 1, "PEP 604"),
    ("match x:\n    case 1:\n        pass\n", 1, "3.10"),
    ("try:\n    pass\nexcept* ValueError:\n    pass\n", 1, "3.11"),
    ("with (open('a') as f, open('b') as g):\n    pass\n", 1, "parenthesised"),
    ("with open('a') as f, open('b') as g:\n    pass\n", 0, ""),
    ("import itertools\nfor a, b in itertools.pairwise(x):\n    pass\n", 1, "pairwise"),
    ("n = (7).bit_count()\n", 1, "bit_count"),
    ("pairs = list(zip(a, b, strict=True))\n", 1, "zip(strict=)"),
    ("from dataclasses import dataclass\n@dataclass(slots=True)\nclass C:\n    pass\n", 1, "slots"),
    ("import tomllib\n", 1, "tomllib"),
    ("from typing import TypeAlias\n", 1, "TypeAlias"),
    ("if (n := len(x)):\n    pass\n", 0, ""),                                # walrus is 3.8
]


def _checker():
    support.need([CHECK])
    spec = importlib.util.spec_from_loader(
        "check_py39", importlib.machinery.SourceFileLoader("check_py39", CHECK))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class TheInstallerIsClean(unittest.TestCase):
    def test_the_installer_directory_has_no_finding(self):
        support.need([CHECK])
        proc = subprocess.run([sys.executable, CHECK, support.TOOLS],
                              capture_output=True, text=True)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertRegex(proc.stdout, r"check-py39: \d+ file\(s\), 0 finding\(s\)")

    def test_the_suffix_less_scripts_are_among_the_files(self):
        files = [os.path.basename(f) for f in _checker().python_files([support.TOOLS])]
        for name in ("h713-install", "h713-extract", "h713-mkimage", "install.py", "fakedisk.py"):
            self.assertIn(name, files)
        self.assertNotIn("metadata-leer-16m.ext4.gz", files)


class Controls(unittest.TestCase):
    def test_each_control_is_caught_or_let_through(self):
        check = _checker().check_source
        for source, count, word in CONTROLS:
            found = check("control.py", source)
            self.assertEqual(len(found), count, (source, found))
            if word:
                self.assertIn(word, found[0][1], (source, found))

    def test_a_finding_is_exit_1_with_the_file_and_the_line(self):
        support.need([CHECK])
        tmp = support.workdir(self)
        with open(os.path.join(tmp, "bad.py"), "w") as fh:
            fh.write("import os\n\ndef f(x: int | None):\n    return x\n")
        proc = subprocess.run([sys.executable, CHECK, tmp], capture_output=True, text=True)
        self.assertEqual(proc.returncode, 1, proc.stdout)
        self.assertIn("bad.py:3: PEP 604", proc.stdout)
        self.assertIn("1 file(s), 1 finding(s)", proc.stdout)


if __name__ == "__main__":
    unittest.main()
