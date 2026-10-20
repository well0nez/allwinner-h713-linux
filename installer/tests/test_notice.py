# SPDX-License-Identifier: GPL-2.0
"""release/notice.py, the licence notices of an image (TODO 7.20 e), against made-up trees.

A BSD licensed binary must carry the copyright notices of what went into it, a Debian package its copyright file,
and the image's source needs the list of source packages. The three commands are checked here the way a guard has to
be: a file that went into the build is named, a file that did not is not, a licence text's own sentences are no
copyright lines, the head of a file under another licence is printed, a package without its file is a finding and
one with it through a Debian Policy 12.5 link is not, and two runs give the same bytes.
"""

import os
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
NOTICE = os.path.join(HERE, "..", "..", "release", "notice.py")

BSD3 = """/*
 * Copyright (c) 2015-2026, Arm Limited and Contributors. All rights reserved.
 *
 * SPDX-License-Identifier: BSD-3-Clause
 */
int a;
"""
ISC = """/*	$OpenBSD: x.c,v 1.1 $	*/

/*
 * SPDX-License-Identifier: ISC
 *
 * Copyright (c) 1998 Todd C. Miller <Todd.Miller@courtesan.com>
 *
 * Permission to use, copy, modify, and distribute this software for any
 * purpose with or without fee is hereby granted, provided that the above
 * copyright notice and this permission notice appear in all copies.
 */
#include "a.h"
"""


def write(root, files):
    for rel, text in files.items():
        path = os.path.join(root, rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(text)


def run(*args):
    r = subprocess.run([sys.executable, NOTICE] + list(args), capture_output=True, text=True)
    return r.returncode, r.stdout + r.stderr


def status(*pkgs):
    """A dpkg status file: (name, source or None, installed?)."""
    out = []
    for name, src, inst in pkgs:
        out.append("Package: %s\nStatus: install ok %s\n%sVersion: 1.0-1\n" % (
            name, "installed" if inst else "config-files", "Source: %s\n" % src if src else ""))
    return "\n".join(out)


@unittest.skipUnless(os.path.isfile(NOTICE), "release/notice.py is not part of this export")
class TestCopyrights(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.src = os.path.join(self.tmp.name, "src")
        self.build = os.path.join(self.tmp.name, "src", "build")
        write(self.src, {
            "lib/a.c": BSD3, "lib/x.c": ISC, "include/a.h": "/* Copyright (C) 2018 Icenowy Zheng */\nint b;\n",
            "lib/unused.c": "/* Copyright (c) 1999 Nobody */\n",
            # make writes the target as an absolute path, the prerequisites relative to the tree it ran in
            "build/lib/a.d": "/elsewhere/build/lib/a.o: \\\n  lib/a.c include/a.h /usr/include/stdint.h\ninclude/a.h:\n",
            "build/lib/x.d": "/elsewhere/build/lib/x.o: lib/x.c include/a.h\n",
        })

    def tearDown(self):
        self.tmp.cleanup()

    def test_names_what_was_built_and_nothing_else(self):
        rc, out = run("copyrights", self.src, self.build, "--title", "T", "--main", "BSD-3-Clause")
        self.assertEqual(rc, 0, out)
        self.assertIn("3 source files", out)
        self.assertIn("Copyright (c) 2015-2026, Arm Limited and Contributors. All rights reserved.", out)
        self.assertIn("Copyright (C) 2018 Icenowy Zheng", out)
        self.assertNotIn("Nobody", out)                                     # lib/unused.c was not built
        self.assertNotIn("above copyright", out.split("Files without")[0].split("Copyright lines")[1].split("Files under")[0])

    def test_a_file_under_another_licence_brings_its_head(self):
        rc, out = run("copyrights", self.src, self.build, "--main", "BSD-3-Clause")
        self.assertIn("--- lib/x.c (ISC)", out)
        self.assertIn("Permission to use, copy, modify, and distribute this software", out)
        self.assertIn("include/a.h", out.split("Files without an SPDX line")[1])

    def test_the_same_bytes_twice(self):
        self.assertEqual(run("copyrights", self.src, self.build), run("copyrights", self.src, self.build))

    def test_no_dependency_files_is_an_error(self):
        rc, out = run("copyrights", self.src, os.path.join(self.src, "lib"))
        self.assertEqual(rc, 1, out)


@unittest.skipUnless(os.path.isfile(NOTICE), "release/notice.py is not part of this export")
class TestPackages(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.tree = self.tmp.name
        write(self.tree, {
            "var/lib/dpkg/status": status(("gcc-14-base", "gcc-14", True), ("libstdc++6", "gcc-14 (14.2.0-19)", True),
                                          ("zlib1g", None, True), ("gone", None, False), ("libgbm1", None, True)),
            "usr/share/doc/gcc-14-base/copyright": "x\n", "usr/share/doc/zlib1g/copyright": "x\n",
        })
        os.symlink("gcc-14-base", os.path.join(self.tree, "usr/share/doc/libstdc++6"))   # Debian Policy 12.5

    def tearDown(self):
        self.tmp.cleanup()

    def test_every_package_has_its_file_or_is_named(self):
        rc, out = run("copyright-files", self.tree)
        self.assertEqual(rc, 1, out)
        self.assertEqual(out.split(), ["no", "/usr/share/doc/libgbm1/copyright"])
        rc, out = run("copyright-files", self.tree, "--except", "libgbm1")
        self.assertEqual((rc, out), (0, ""))

    def test_source_packages_with_their_versions(self):
        rc, out = run("debian-sources", os.path.join(self.tree, "var/lib/dpkg/status"))
        self.assertEqual(rc, 0, out)
        self.assertEqual(out.splitlines(), ["gcc-14 1.0-1", "gcc-14 14.2.0-19", "libgbm1 1.0-1", "zlib1g 1.0-1"])


if __name__ == "__main__":
    unittest.main()
