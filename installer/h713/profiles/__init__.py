"""Board profiles: one module per board, one dict PROFILE each.

    from profiles import PROFILES, get
    PROFILES["hy310"]["layout"]["entries"]
    get("hy350")

Shape and rules: umbau/plan/profil-schema.md. The modules are data only -- every number and hash
carries the source it came from. A profile with status != "verified" never produces an image.
"""

from . import hy300_pro, hy300_t08, hy310, hy350, l018

#: board id -> profile dict. The id is also the module name.
PROFILES = {
    "hy310": hy310.PROFILE,
    "l018": l018.PROFILE,
    "hy300_t08": hy300_t08.PROFILE,
    "hy350": hy350.PROFILE,
    "hy300_pro": hy300_pro.PROFILE,
}

#: the values "status" may take. Only "verified" may produce an image (doku/121 section 5).
STATUS_VALUES = ("verified", "profile-only", "partial")


def get(board_id):
    """Return the profile of `board_id`, or None if there is none."""
    return PROFILES.get(board_id)
