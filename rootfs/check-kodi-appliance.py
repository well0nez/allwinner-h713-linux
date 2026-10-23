#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0
"""check-kodi-appliance.py [TREE] - the image's Kodi defaults are where Kodi reads them.

Kodi 21 reads <kodi>/system/settings/appliance.xml after settings.xml, its platform file and the defaults it works out itself: what the
file names is Kodi's default on this image. A setting is found there by its section, category and group; one that is not found is not
applied - without a word. The file carries only <default>, and the image ships no guisettings.xml of its own: that file is Kodi's, written
at every exit, and a copy of the image's values in it would be the owner's choice to Kodi.

Without TREE the overlay in this checkout is read; with TREE (a built root) the files of that tree, and the settings must also sit where the
tree's own settings.xml and linux.xml have them. Exit 0 and one line when all is well, else the problems, one per line, and exit 1."""
import os
import sys
import xml.etree.ElementTree as ET

HERE = os.path.dirname(os.path.abspath(__file__))
APPLIANCE = "usr/share/kodi/system/settings/appliance.xml"
SEED = "var/lib/h713-kodi/.kodi/userdata/guisettings.xml"


def places(root):
    """setting id -> (section, category, group)"""
    return {s.get("id"): (sec.get("id"), cat.get("id"), g.get("id"))
            for sec in root.iter("section") for cat in sec.iter("category") for g in cat.iter("group") for s in g.iter("setting")}


def problems(appliance, kodi_defs=(), seed_there=False):
    """appliance: the parsed appliance.xml; kodi_defs: parsed settings.xml, linux.xml of the tree (none: the structure only)"""
    out = ["a guisettings.xml of the image's own is laid (Kodi's file, rewritten at every exit)"] if seed_there else []
    known = {}
    for d in kodi_defs:
        known.update(places(d))
    mine = places(appliance)
    if not mine:
        out.append("appliance.xml names no setting")
    for s in appliance.iter("setting"):
        i = s.get("id")
        if [c.tag for c in s] != ["default"]:
            out.append("%s: only <default> belongs here, found %s" % (i, [c.tag for c in s]))
        if known and i not in known:
            out.append("%s: not a setting of this Kodi" % i)
        elif known and known[i] != mine[i]:
            out.append("%s: Kodi has it in %s, appliance.xml in %s" % (i, "/".join(known[i]), "/".join(mine[i])))
    return out


def main(tree=None):
    base = tree or os.path.join(HERE, "overlay-desktop")
    appliance = ET.parse(os.path.join(base, APPLIANCE)).getroot()
    defs = [ET.parse(os.path.join(tree, "usr/share/kodi/system/settings", f)).getroot() for f in ("settings.xml", "linux.xml")] if tree else []
    found = problems(appliance, defs, os.path.exists(os.path.join(base, SEED)))
    print("\n".join(found) or "appliance.xml: %d settings, all where Kodi has them" % len(places(appliance)))
    return 1 if found else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else None))
