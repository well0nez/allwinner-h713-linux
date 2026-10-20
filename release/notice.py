#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0
"""notice.py -- the licence notices of an image (TODO 7.20 e).

    release/notice.py copyrights SRC BUILD [--title TEXT] [--main SPDX] [--exclude PREFIX ...]
    release/notice.py debian-sources STATUS
    release/notice.py copyright-files TREE [--except PACKAGE ...]

copyrights      The copyright and licence lines of every source file a build compiled into its
                binary, found through the dependency files (*.d) under BUILD; SRC is the source
                tree the paths in them are relative to. Prints one text: the licences with their
                number of files, every copyright line once, and the head comment (where the
                licence text of such a file stands) of every file under another licence than
                --main. For a BSD licensed binary (TF-A's BL31), whose licence asks that the
                notices travel with the binary.
debian-sources  Every source package of the installed packages of a dpkg status file, with its
                version, one per line, sorted: what to ask deb.debian.org or snapshot.debian.org
                for, and what the image's source archives have to hold.
copyright-files Every installed package of the tree has its /usr/share/doc/<package>/copyright
                (a package whose directory is a link to another package of the same source,
                Debian Policy 12.5, has it through the link). Prints those without; ends with 1
                if there is one (the names after --except are not asked: the build's own
                stand-ins).

The output carries no date and no path of the build machine, and is sorted, so that two
builds of the same sources give the same bytes (release/build-all.sh, "reproducible").
"""
import argparse
import os
import re
import sys

HEAD_LINES = 60          # a licence header sits at the top of a file
SPDX = re.compile(r"SPDX-License-Identifier:\s*(.+?)\s*(\*/)?\s*$")
# a line that states a copyright (not one of a licence text's sentences about "the above copyright notice")
COPYRIGHT_LINE = re.compile(r"^(portions\s+)?(copyright\b|\(c\)\s+(?=[0-9A-Z])|©)(?!\s+(notice|holders?\b|and\b))", re.I)
# the comment leaders and trailers a copyright line comes with
STRIP = re.compile(r"^\s*(/\*+|\*+|//+|#+|;+|--)?\s*|\s*(\*+/)?\s*$")


def dep_files(build):
    for top, dirs, files in os.walk(build):
        dirs.sort()
        for f in sorted(files):
            if f.endswith(".d"):
                yield os.path.join(top, f)


def prerequisites(path):
    """The files a make dependency file names, behind the colon of each rule."""
    text = open(path, encoding="utf-8", errors="replace").read().replace("\\\n", " ")
    out = []
    for line in text.splitlines():
        if ":" not in line:
            continue
        _, rest = line.split(":", 1)
        out += rest.split()
    return out


def header(path):
    lines = []
    with open(path, encoding="utf-8", errors="replace") as f:
        for i, line in enumerate(f):
            if i >= HEAD_LINES:
                break
            lines.append(line.rstrip("\n"))
    return lines


def comment_block(lines):
    """The comments at the head of a file, up to its first line of code: /* ... */ blocks, runs of // or #
    lines (an OpenBSD file puts its licence in the second block, behind the $OpenBSD$ line)."""
    out, inside = [], False
    for line in lines:
        t = line.strip()
        if inside:
            out.append(line)
            inside = "*/" not in t
        elif not t or t.startswith("#!"):
            if out:
                out.append(line)
        elif t.startswith("/*"):
            out.append(line)
            inside = "*/" not in t[2:]
        elif t.startswith(("//", "#")) and not re.match(r"#\s*(include|define|if|ifn?def|pragma)\b", t):
            out.append(line)
        else:
            break
    while out and not out[-1].strip():
        out.pop()
    return out


def cmd_copyrights(a):
    src = os.path.realpath(a.src)
    files = set()
    for d in dep_files(a.build):
        for p in prerequisites(d):
            if p.endswith(".o"):
                continue
            # make writes paths relative to where it ran (the source tree) or absolute; an absolute one that
            # is no part of the source tree (the build's own generated headers, the compiler's) is left out
            full = os.path.realpath(p if os.path.isabs(p) else os.path.join(src, p))
            if not full.startswith(src + os.sep) or not os.path.isfile(full):
                continue
            rel = os.path.relpath(full, src)
            if any(rel.startswith(x) for x in a.exclude):
                continue
            files.add(rel)
    if not files:
        print("notice.py: no source files found through the *.d files under %s" % a.build, file=sys.stderr)
        return 1
    licences, lines, without, other = {}, set(), [], []
    for rel in sorted(files):
        lic = None
        for line in header(os.path.join(src, rel)):
            m = SPDX.search(line)
            if m and lic is None:
                lic = m.group(1)
            c = re.sub(r"\s+", " ", STRIP.sub("", line))
            if COPYRIGHT_LINE.match(c):
                lines.add(c)
        if lic is None:
            without.append(rel)
            lic = "(no SPDX line)"
        elif a.main and lic != a.main:
            other.append((rel, lic))
        licences[lic] = licences.get(lic, 0) + 1
    print(a.title)
    print("%d source files, found through the dependency files of the build." % len(files))
    print()
    print("Licences of those files (SPDX), with the number of files:")
    for lic in sorted(licences):
        print("  %-60s %5d" % (lic, licences[lic]))
    print()
    print("Copyright lines of those files, each once:")
    for c in sorted(lines):
        print("  " + c)
    if without:
        print()
        print("Files without an SPDX line (their licence is the one of the project, see the licence file):")
        for rel in without:
            print("  " + rel)
    if other:
        print()
        print("Files under another licence than %s: the head of each, as it stands in the source" % a.main)
        for rel, lic in other:
            print()
            print("--- %s (%s)" % (rel, lic))
            for line in comment_block(header(os.path.join(src, rel))):
                print(line.rstrip())
    return 0


def packages(status):
    """The installed packages of a dpkg status file: {name: fields}."""
    out = {}
    for block in open(status, encoding="utf-8", errors="replace").read().split("\n\n"):
        f = dict(re.findall(r"^([A-Za-z-]+):[ \t]*(.*)$", block, re.M))
        if "Package" in f and f.get("Status", "").endswith(" installed"):
            out[f["Package"]] = f
    return out


def source_of(f):
    """(source name, source version): the Source field, with a version in brackets if it differs."""
    s = f.get("Source", "").strip()
    if not s:
        return f["Package"], f.get("Version", "")
    m = re.match(r"(\S+)(?:\s+\((\S+)\))?", s)
    return m.group(1), m.group(2) or f.get("Version", "")


def cmd_debian_sources(a):
    pk = packages(a.status)
    for name, ver in sorted({source_of(f) for f in pk.values()}):
        print("%s %s" % (name, ver))
    return 0


def cmd_copyright_files(a):
    doc = os.path.join(a.tree, "usr/share/doc")
    missing = [p for p in sorted(packages(os.path.join(a.tree, "var/lib/dpkg/status")))
               if p not in a.exclude and not os.path.isfile(os.path.join(doc, p, "copyright"))]
    for p in missing:
        print("    no /usr/share/doc/%s/copyright" % p)
    return 1 if missing else 0


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("copyrights")
    c.add_argument("src")
    c.add_argument("build")
    c.add_argument("--title", default="Copyright notices")
    c.add_argument("--exclude", action="append", default=[], help="a path prefix, relative to SRC, to leave out")
    c.add_argument("--main", default="", help="the project's own licence (SPDX); a file under another one gets its head printed")
    d = sub.add_parser("debian-sources")
    d.add_argument("status")
    l = sub.add_parser("copyright-files")
    l.add_argument("tree")
    l.add_argument("--except", dest="exclude", action="append", default=[])
    a = ap.parse_args()
    return {"copyrights": cmd_copyrights, "debian-sources": cmd_debian_sources, "copyright-files": cmd_copyright_files}[a.cmd](a)


if __name__ == "__main__":
    sys.exit(main())
