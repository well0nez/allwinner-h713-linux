#!/usr/bin/env python3
"""Schema check for the board profiles -- installer/h713/profiles/SCHEMA.md is the contract.

    python3 validate.py                 # check all five, print problems, exit 1 if there are any
    python3 -m unittest validate -v     # the same check as a test
Reads nothing but the profile modules; the checks against the sources live in tests/test_profiles.py.
"""

import re
import sys
import unittest

from profiles import PROFILES, STATUS_VALUES

HASH = re.compile(r"^[0-9a-f]{64}$")
BOARD_ID = re.compile(r"^[a-z0-9_]+$")
NONE = type(None)

TOP = (("id", str), ("name", str), ("description", str), ("status", str), ("verified_by", (str, NONE)),
       ("soc", str), ("stock", dict), ("dram", (dict, NONE)), ("layout", (dict, NONE)), ("mips", dict),
       ("unique_regions", list), ("preserve_on_restore", tuple), ("panel", (dict, NONE)),
       ("board_dt", (str, NONE)), ("uboot_board", (str, NONE)), ("reference", (dict, NONE)),
       ("expected", (dict, NONE)))
STOCK = sorted("android arisc_version build_fingerprint package_items strong_features sunxi_version"
               " uboot_version vendor_size".split())
DRAM = sorted("clk type zq odt_en para1 para2 mr0 mr1 mr2 mr3 source".split() + ["tpr%d" % i for i in range(14)])
LAYOUT = sorted("disk_sectors entries first_usable partitions raw sunxi_gpt_disagrees".split())
PANEL = sorted("declared_project_id width height dual_port htotal vtotal dclk_hz hsync vsync hbp vbp"
               " hsync_pol vsync_pol pwm_channel pwm_freq source".split())
EXPECTED = sorted("package_items package_item_sha256 uboot_version dtb_compatible arisc_version vendor_size"
                  " libmspsound_sha256 build_fingerprint sunxi_version mips_database_sha256".split())
# X:178 KENNUNGS_MERKMALE -- the only names "strong_features" may use.
FEATURES = sorted("scp_sha256 uboot_sha256 dtb_sha256 uboot_version arisc_version build_fingerprint"
                  " mips_database_sha256 sunxi_version vendor_size".split())


def validate(board_id, p):
    """Return a list of problems with profile `p`; an empty list means it matches the schema."""
    bad = []

    def want(cond, text):
        if not cond:
            bad.append(text)

    def _pos(v):                               # a size or a sector count; never a bool
        return isinstance(v, int) and not isinstance(v, bool) and v > 0

    def _num(v):                               # a number the profile may leave open
        return v is None or (isinstance(v, int) and not isinstance(v, bool) and v >= 0)
    def _hash(v):
        return isinstance(v, str) and HASH.match(v) is not None

    for key, typ in TOP:                       # every key of the schema, with the type it must have
        want(isinstance(p.get(key), typ), "%s: missing or wrong type (%s)" % (key, type(p.get(key)).__name__))
    if bad:
        return bad
    want(p["id"] == board_id and BOARD_ID.match(p["id"]), "id %r does not match its registry key" % p["id"])
    want(p["status"] in STATUS_VALUES, "status %r not in %s" % (p["status"], STATUS_VALUES))
    want((p["status"] == "verified") == bool(p["verified_by"]),
         "verified_by is set exactly when status is 'verified' (status=%s)" % p["status"])
    s = p["stock"]
    want(sorted(s) == STOCK, "stock keys: %s" % sorted(s))
    want(s.get("vendor_size") is None or _pos(s["vendor_size"]), "stock.vendor_size: positive int or None")
    want(isinstance(s.get("strong_features"), tuple), "stock.strong_features: tuple")
    for label, table in (("stock.package_items", s.get("package_items")), ("reference", p["reference"])):
        for name, item in (table or {}).items():
            want(isinstance(item, tuple) and len(item) == 2 and _pos(item[0]) and _hash(item[1]),
                 "%s[%r] must be (size > 0, sha256)" % (label, name))
    want(all(f in FEATURES for f in s.get("strong_features") or ()),
         "stock.strong_features %s: not all of them are identification features" % (s.get("strong_features"),))
    d = p["dram"] or {}
    if d:
        want(sorted(d) == DRAM, "dram keys: %s" % sorted(d))
        want(_pos(d.get("clk")) and isinstance(d.get("source"), str) and d["source"],
             "dram needs a positive clk and a source saying where the block came from")
        want(all(_num(d.get(k)) for k in DRAM if k != "source"), "dram: every value is an int >= 0 or None")
    lay = p["layout"] or {}
    if lay:
        want(sorted(lay) == LAYOUT, "layout keys: %s" % sorted(lay))
        want(all(lay.get(k) is None or _pos(lay[k]) for k in ("disk_sectors", "entries", "first_usable")),
             "layout: disk_sectors, entries and first_usable are positive ints or None")
        want(lay.get("partitions") is None or len(lay["partitions"]) == lay["entries"],
             "layout: %s rows, entries says %s" % (len(lay.get("partitions") or ()), lay.get("entries")))
        for row in lay.get("partitions") or ():
            want(isinstance(row, tuple) and len(row) == 4 and isinstance(row[0], str) and _num(row[1])
                 and _num(row[2]) and isinstance(row[3], (str, NONE)),
                 "layout.partitions %r: (name, start_lba, sectors, downloadfile)" % (row,))
        for row in lay.get("raw") or ():
            want(isinstance(row, tuple) and len(row) == 2 and isinstance(row[0], str) and _num(row[1]),
                 "layout.raw %r: (file, lba)" % (row,))
        for n, pair in (lay.get("sunxi_gpt_disagrees") or {}).items():
            want(isinstance(pair, tuple) and len(pair) == 2 and all(_pos(v) for v in pair),
                 "layout.sunxi_gpt_disagrees[%r]: (sys_partition, sunxi_gpt) sectors" % n)
    for r in p["unique_regions"]:
        if not (isinstance(r, tuple) and len(r) == 4):
            bad.append("unique_regions row %r must have four fields" % (r,))
            continue
        want(isinstance(r[0], str) and r[0] and isinstance(r[3], str) and r[3],
             "unique_regions %r: needs a name and a note" % (r,))
        want((r[1] == "by-name" and _num(r[2])) or (_num(r[1]) and _pos(r[2])),
             "unique_regions[%s]: either a fixed LBA with a sector count, or 'by-name'" % r[0])
    want(all(isinstance(n, str) and n for n in p["preserve_on_restore"]), "preserve_on_restore: partition names")
    m = p["mips"]
    want(sorted(m) == ["revisions", "sources"], "mips keys: %s" % sorted(m))
    want(isinstance(m.get("sources"), tuple) and m["sources"], "mips.sources: non-empty tuple")
    for rev in m.get("revisions") or ():
        want(sorted(rev) == ["hdcp_wait_va", "name", "sha256", "size"] and _pos(rev.get("size"))
             and _hash(rev.get("sha256")) and _num(rev.get("hdcp_wait_va")),
             "mips revision %r: size > 0, sha256, wait site or None" % rev.get("name"))
    pan = p["panel"] or {}
    if pan:
        want(sorted(pan) == PANEL and isinstance(pan.get("source"), str),
             "panel: the schema keys, and a source saying where the values came from")
        want(all(pan.get(k) is None or isinstance(pan[k], (int, bool)) for k in PANEL if k != "source"),
             "panel: every value is a number, a bool or None")
    e = p["expected"] or {}
    if e:
        want(sorted(e) == EXPECTED, "expected keys: %s" % sorted(e))
        want(_pos(e.get("vendor_size")) and _hash(e.get("mips_database_sha256"))
             and (e.get("libmspsound_sha256") is None or _hash(e["libmspsound_sha256"])),
             "expected: vendor_size > 0, mips_database_sha256 and libmspsound_sha256 sha256 or None")
        for name, size in (e.get("package_items") or {}).items():
            want(_pos(size) and _hash((e.get("package_item_sha256") or {}).get(name)),
                 "expected: %r needs a size > 0 and a sha256" % name)
    return bad


def validate_all():             # board id -> list of problems, for every profile in the registry
    return {board_id: validate(board_id, p) for board_id, p in sorted(PROFILES.items())}


class ProfileSchema(unittest.TestCase):
    def test_every_profile_matches_the_schema(self):
        for board_id, problems in sorted(validate_all().items()):
            with self.subTest(board=board_id):
                self.assertEqual([], problems)


def main():
    problems = validate_all()
    for board_id, found in problems.items():
        print("%-10s %s" % (board_id, "ok" if not found else "%d problem(s)" % len(found))
              + "".join("\n           - %s" % line for line in found))
    return 1 if any(problems.values()) else 0


if __name__ == "__main__":
    sys.exit(main())
