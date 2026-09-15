"""Board profiles: one module per board, one dict PROFILE each.

    from profiles import PROFILES, get
    PROFILES["hy310"]["layout"]["entries"]
    get("hy350")

Shape and rules: installer/h713/profiles/SCHEMA.md. The modules are data only -- every number and hash
carries the source it came from. A profile with status != "verified" never produces an image.

This module also carries the two cross-board tables the readers need: FIRMWARE_REVISIONS (every
display.bin revision we know of) and legacy_devices() (the extractor's old GERAETE table, rebuilt
from the profiles so that the moved extractor code keeps behaving byte for byte as before).
"""

from __future__ import annotations

from . import hy200_qz713_v2, hy200_qz713df_a1, hy300_pro, hy300_t08, hy310, hy350, l018

#: board id -> profile dict. The id is also the module name.
PROFILES = {
    "hy310": hy310.PROFILE,
    "l018": l018.PROFILE,
    "hy300_t08": hy300_t08.PROFILE,
    "hy350": hy350.PROFILE,
    "hy300_pro": hy300_pro.PROFILE,
    "hy200_qz713df_a1": hy200_qz713df_a1.PROFILE,
    "hy200_qz713_v2": hy200_qz713_v2.PROFILE,
}

#: the values "status" may take. Only "verified" may produce an image (doku/121 section 5).
STATUS_VALUES = ("verified", "profile-only", "partial")

#: X:178 KENNUNGS_MERKMALE -- the only names a profile's "strong_features" and the readers may use.
#: Order = weight of evidence; the last two only confirm or contradict in the old global reading.
FEATURE_VOCABULARY = ("scp_sha256", "uboot_sha256", "dtb_sha256", "uboot_version", "arisc_version",
                      "build_fingerprint", "mips_database_sha256", "sunxi_version", "vendor_size")


def get(board_id):
    """Return the profile of `board_id`, or None if there is none."""
    return PROFILES.get(board_id)


def strong_features_of(profile):
    """The features that alone pin *this* board down (profile["stock"]["strong_features"]).

    Per board, not globally: the three ADT-3 boards share `build_fingerprint` and
    `mips_database_sha256`, so their profiles do not list them (doku/121 section 2, finding 1).
    A profile that lists none (HY300 Pro -- nothing known about it is unique) can never be
    matched, which is the intended answer, not a bug.
    """
    return tuple((profile.get("stock") or {}).get("strong_features") or ())


def expected_features(profile):
    """The nine identification features a profile declares, as {name: value or None}.

    Two shapes reach this: a row of legacy_devices() ("erwartung"/"paket_item_sha256", what the
    moved extractor hands over) and a board profile ("expected"/"package_item_sha256"). Same
    values, so only the two names are looked up. A profile that declares nothing at all
    (`expected: None`, HY300 Pro) gives every feature as None.
    """
    declared = profile.get("erwartung") if "erwartung" in profile else profile.get("expected")
    if not declared:
        return dict((name, None) for name in FEATURE_VOCABULARY)
    items = declared.get("paket_item_sha256") or declared.get("package_item_sha256") or {}
    return {"scp_sha256": items.get("scp"), "uboot_sha256": items.get("u-boot"),
            "dtb_sha256": items.get("dtb"), "uboot_version": declared.get("uboot_version"),
            "arisc_version": declared.get("arisc_version"),
            "build_fingerprint": declared.get("build_fingerprint"),
            "mips_database_sha256": declared.get("mips_database_sha256"),
            "sunxi_version": declared.get("sunxi_version"),
            "vendor_size": declared.get("vendor_size")}


# --------------------------------------------------------------------------------------------------
# display.bin revisions
# --------------------------------------------------------------------------------------------------

# X:266 H713_MIPS_FW_REVS, widened by the rows of installer/tests/fixtures/firmware-revisions.json (package A5).
# The sha256 of a display.bin names its board, its project id and its panel; "hdcp_wait_va" is the
# address of the wait site inside that revision (A5, .hdcp_wait_va of h713_mips_fw_revs[]).
# Only the first two rows are declared by h713_mips_fw_revs[] in arch/arm/mach-sunxi/h713_mips.c --
# the other two are revisions we have measured but which no row of that table declares, so they carry
# neither a project id nor a panel. UBOOT_FW_REVS below is the part the readers ask.
FIRMWARE_REVISIONS = (
    {"board": "HY200 QZ713DF_A1", "project_id": 0x34, "panel": "1280x720", "size": 0x132910,
     "sha256": "4380f1b3ed7b62aa50582e7cb16a87bdface1b4300578fe3631a416354da30ce",
     "hdcp_wait_va": 0x4b13d6f8},
    {"board": "HY310 (QZ713 V3.1)", "project_id": 0x30, "panel": "1920x1080", "size": 0x132b18,
     "sha256": "16c74a28187f342de657828fab65145b140ac9411c40cccc02eed25047472ee9",
     "hdcp_wait_va": 0x4b13d0a4},
    # F, row "ADT-3 2024": size 0x131b20 is declared by no row of h713_mips_fw_revs[].
    {"board": "ADT-3 2024", "project_id": None, "panel": None, "size": 0x131b20,
     "sha256": "22a7df113fce3fa182926268de8c7551a107f0c3bc2932f0940bd58b8f424835",
     "hdcp_wait_va": 0x4b13d1f0},
    # F, row "HY300 Pro": size and sha256 reported by the owner (issue #1), no image, no wait site.
    {"board": "HY300 Pro", "project_id": None, "panel": None, "size": 0x131f10,
     "sha256": "cf9649bcc84a111ce590fc7acde723c25557fd2332abbb9fd10225905aae13a2",
     "hdcp_wait_va": None},
    # F, row "HY200 QZ713_V2" (package F1): the display.bin of the LPDDR3 HY300 Pro+ image (0710).
    # Size 0x1328f0 is declared by no row of h713_mips_fw_revs[], so it carries neither a project id
    # nor a panel -- the board's panel_config.ini declares ProjectID 0x34, 1280x720. The wait site was
    # searched with h713.hdcpsite over that display.bin (one hit with context, file offset 0x3d538).
    {"board": "HY200 QZ713_V2", "project_id": None, "panel": None, "size": 0x1328f0,
     "sha256": "4628cbaf8c93ea12ec59e871e4250facf0773daae722b251c73f1fad81e80c2c",
     "hdcp_wait_va": 0x4b13d538},
)

#: X:266 verbatim: the rows h713_mips_fw_revs[] declares, with the keys the extractor reads. A row
#: without a project id is not in that table, and the extractor must not find it (stage 1 keeps the
#: old result; whether it should learn the wider table is a stage-2 question).
UBOOT_FW_REVS = tuple({k: r[k] for k in ("board", "project_id", "panel", "size", "sha256")}
                      for r in FIRMWARE_REVISIONS if r["project_id"] is not None)


# --------------------------------------------------------------------------------------------------
# The extractor's old device table
# --------------------------------------------------------------------------------------------------

#: The two boards h713-extract knows (X:98 GERAETE), in that order: it prints the key list and walks
#: it in order, so both matter.
LEGACY_DEVICE_IDS = ("hy310", "l018")

# X:101 and X:145 verbatim. The profiles carry an English "description"; the extractor writes this
# text into MANIFEST.json ("device_beschreibung") and BERICHT.txt, so stage 1 keeps the German one.
# Stage 3 translates the visible layer and this table goes away with it.
LEGACY_DESCRIPTIONS = {
    "hy310": "HY310 — Allwinner H713, Referenzdesign h713_tuna_p3, Stock-Build 2025-07-24 (Projector07241019)",
    "l018": "L018 — Allwinner H713, Referenzdesign h713_tuna_p3, Stock-Build 2025-05-14 (Projector05141211)",
}

#: X:124 "erwartung" key -> profile "expected" key. Only two names differ.
_LEGACY_EXPECTED_KEYS = (
    ("paket_items", "package_items"),
    ("paket_item_sha256", "package_item_sha256"),
    ("uboot_version", "uboot_version"),
    ("dtb_compatible", "dtb_compatible"),
    ("arisc_version", "arisc_version"),
    ("vendor_size", "vendor_size"),
    ("libmspsound_sha256", "libmspsound_sha256"),
    ("build_fingerprint", "build_fingerprint"),
    ("sunxi_version", "sunxi_version"),
    ("mips_database_sha256", "mips_database_sha256"),
)


def legacy_devices():
    """The GERAETE table of h713-extract (X:98-177), rebuilt from the board profiles.

    Same keys, same values, same order: "name", "beschreibung", "referenz", "erwartung". The moved
    extractor and installer code reads it unchanged, which is what keeps its output byte-identical.
    """
    out = {}
    for board_id in LEGACY_DEVICE_IDS:
        profile = PROFILES[board_id]
        expected = profile["expected"]
        out[board_id] = {
            "name": profile["name"],
            "beschreibung": LEGACY_DESCRIPTIONS[board_id],
            "referenz": dict(profile["reference"]),
            "erwartung": {old: dict(expected[new]) if isinstance(expected[new], dict) else expected[new]
                          for old, new in _LEGACY_EXPECTED_KEYS},
        }
    return out
