#!/usr/bin/env python3
"""Check the Markdown links of this repository's English documentation.

Two questions, both answered against the working tree, nothing fetched:

  1. Does every relative link point at a file that exists?
  2. Is every page under docs/ linked from somewhere, or is it an orphan
     that only its own directory listing would reveal?

Usage:  python3 tools/check-links.py [ROOT]

ROOT defaults to the repository root (the parent of this script's directory).
Exit code 0 when both questions come out clean, 1 otherwise.
"""

import os
import re
import sys

# [text](target) - the target is everything up to the closing bracket that is
# not a space; an optional "title" after a space is ignored, as Markdown does.
LINK = re.compile(r"\[[^\]]*\]\(\s*([^)\s]+)(?:\s+[^)]*)?\)")
EXTERNAL = ("http://", "https://", "mailto:", "ftp://")

# Pages to read: the top-level English files plus everything under docs/.
TOP_LEVEL = ("README.md", "STATUS.md", "PROVENANCE.md", "ROADMAP.md",
             "RELEASES.md", "BUILDING.md", "FLASHING.md")


def markdown_files(root):
    """Every page the check reads, as paths relative to root, sorted."""
    found = list(f for f in TOP_LEVEL if os.path.isfile(os.path.join(root, f)))
    docs = os.path.join(root, "docs")
    for dirpath, dirnames, filenames in os.walk(docs):
        dirnames.sort()
        for name in sorted(filenames):
            if name.endswith(".md"):
                full = os.path.join(dirpath, name)
                found.append(os.path.relpath(full, root).replace(os.sep, "/"))
    return sorted(found)


def targets_of(root, page):
    """The relative link targets of one page, as (line number, raw, resolved)."""
    with open(os.path.join(root, page), "rb") as handle:
        text = handle.read().decode("utf-8")
    base = os.path.dirname(page)
    out = []
    for number, line in enumerate(text.splitlines(), 1):
        for raw in LINK.findall(line):
            if raw.startswith(EXTERNAL) or raw.startswith("#"):
                continue
            target = raw.split("#", 1)[0].replace("%20", " ")
            if not target:
                continue          # a pure anchor into the page itself
            resolved = os.path.normpath(os.path.join(base, target))
            out.append((number, raw, resolved.replace(os.sep, "/")))
    return out


def main(argv):
    root = argv[1] if len(argv) > 1 else os.path.dirname(
        os.path.dirname(os.path.abspath(__file__)))
    pages = markdown_files(root)
    if not pages:
        sys.stderr.write("no Markdown pages under %s\n" % root)
        return 1

    dead = []
    linked = set()
    for page in pages:
        for number, raw, resolved in targets_of(root, page):
            if not os.path.exists(os.path.join(root, resolved)):
                dead.append((page, number, raw))
            linked.add(resolved)

    orphans = [p for p in pages
               if p.startswith("docs/") and p not in linked
               and os.path.basename(p) != "README.md"]

    print("%d pages read, %d link targets seen" % (len(pages), len(linked)))
    for page, number, raw in dead:
        print("dead link  %s:%d  ->  %s" % (page, number, raw))
    for page in orphans:
        print("orphan     %s  (no page links to it)" % page)
    if not dead and not orphans:
        print("no dead links, no orphans")
        return 0
    print("%d dead links, %d orphans" % (len(dead), len(orphans)))
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
