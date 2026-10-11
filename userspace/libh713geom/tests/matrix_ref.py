"""T2 (AP2d test plan): the reference side of the matrix test.

This script does not test anything by itself. It writes the test vectors and
the expected numbers to stdout, computed by the AP2f reference
userspace/h713-keystone/model/keystone_matrix.py (AP2f) -- the tested port of the vendor's
getKeyStoneMatrix -- and the C driver test_matrix.c reads them and compares
them with what libh713geom/matrix.c (used by h713-warp) computes.

    python3 matrix_ref.py > vectors.txt && ./test_matrix < vectors.txt

Three kinds of line, all in OUR key order (tl_x tl_y tr_x tr_y bl_x bl_y br_x
br_y), because that mapping onto the vendor's parcel order is itself part of
what is being tested:

    m V0..V7  M0..M15  X0 Y0 .. X3 Y3   the sixteen floats and the four panel
                                        corners after the map, in the corner
                                        order tl tr bl br
    c V0..V7  W0..W7                    the vendor's clamp, in and out
    r V0..V7                            a set the native range check refuses
    f MODE V0..V7  X0 Y0 .. X5 Y5       the projection mode MODE (0 front, 1
                                        rear, 2 ceiling, 3 rear-ceiling): six
                                        source points (the four corners tl tr
                                        bl br, the centre, one off-centre) as
                                        the VENDOR's way lands them on the
                                        panel - the eight insets permuted into
                                        the slots of the mounted picture as
                                        LocalService does before every auto
                                        send, the matrix solved on them, the
                                        source flipped underneath as the
                                        firmware flips the composed frame.
                                        h713-warp goes the other way round (the
                                        wall keystone first, the flip after) and
                                        must land the same points

19 fixed vectors (the identity, one corner at a time in both axes, an opposite
pair, the "straight lines" set of AP2f, two uniform pulls -- which is what the
vendor's digital zoom is -- two sets near the clamp's limit, a trapezoid and the
nose-up correction), then 200 random ones with a fixed seed, as AP2d T2 asks.

Standard library only, Python 3.9 compatible.
"""

import os
import random
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
# the same file as work/AP2f/model, moved into the tree with h713-keystone
sys.path.insert(0, os.path.join(HERE, "..", "..", "h713-keystone", "model"))

import keystone_matrix as km    # noqa: E402

# our corner order tl tr bl br -> the vendor's slot order lb lt rt rb
# (matrix.c CORNER_OF_SLOT; the derivation is in that file's head comment)
CORNER_OF_SLOT = (2, 0, 1, 3)
# the NDC corner each of our names stands for: y = -1 is the top of the panel,
# because the first row in memory is what the scanout shows at the top
CORNER_NDC = ((-1.0, -1.0), (1.0, -1.0), (-1.0, 1.0), (1.0, 1.0))

FIXED = [
    (0, 0, 0, 0, 0, 0, 0, 0),                    # the identity
    (100, 0, 0, 0, 0, 0, 0, 0),                  # one corner, one axis ...
    (0, 100, 0, 0, 0, 0, 0, 0),
    (0, 0, 100, 0, 0, 0, 0, 0),
    (0, 0, 0, 100, 0, 0, 0, 0),
    (0, 0, 0, 0, 100, 0, 0, 0),
    (0, 0, 0, 0, 0, 100, 0, 0),
    (0, 0, 0, 0, 0, 0, 100, 0),
    (0, 0, 0, 0, 0, 0, 0, 100),
    (100, 100, 0, 0, 0, 0, 100, 100),            # two opposite corners
    (200, 60, 150, 0, 0, 0, 0, 90),              # AP2f "straight lines"
    (125, 125, 125, 125, 125, 125, 125, 125),    # uniform: the vendor's zoom
    (250, 250, 250, 250, 250, 250, 250, 250),
    (450, 0, 450, 0, 0, 0, 0, 0),                # a row near the limit: at
    (0, 450, 0, 0, 0, 450, 0, 0),                # 500 + 500 the edge would
                                                 # collapse to a point and the
                                                 # vendor's solve divides by 0
    (80, 40, 120, 40, 0, 0, 0, 0),               # a trapezoid
    (150, 0, 150, 0, 0, 0, 0, 0),                # nose-up: the top edge in
    (0, 0, 0, 0, 150, 0, 150, 0),                # nose-down
    (400, 300, 20, 0, 0, 200, 60, 10),           # nothing symmetric about it
]

CLAMPS = [
    (900, 0, 0, 0, 0, 0, 300, 0),                # x against the row partner
    (0, 900, 0, 0, 0, 300, 0, 0),                # y against the column partner
    (1000, 0, 1000, 0, 0, 0, 0, 0),              # both ends of one row
    (0, 0, 0, 0, 0, 0, 0, 0),
    (600, 600, 600, 600, 600, 600, 600, 600),
    (1000, 1000, 1000, 1000, 1000, 1000, 1000, 1000),
]

REJECTS = [
    (1200, 0, 0, 0, 0, 0, 0, 0),
    (0, 0, 0, 0, 0, 0, 0, 1500),
    (0, 0, -1, 0, 0, 0, 0, 0),
]

# The vendor's corner permutation per projection mode, transcribed from
# tpjz_allwinner LocalService.java:1154-1200 (the auto path; persist.sys.
# panelvalue 0..3 = the UI index front, rear front, front ceiling, rear
# ceiling): for each of OUR corners (tl tr bl br), which wall corner's inset
# the slot takes. 1: lt<->rt, lb<->rb; 2: lt<->rb, rt<->lb; 3: lt<->lb, rt<->rb.
MODE_PERM = ((0, 1, 2, 3), (1, 0, 3, 2), (3, 2, 1, 0), (2, 3, 0, 1))
# and the flip the firmware applies to the composed frame for that mode
# (AP2i 2.2: the RPC word is 0, 1, 3, 2 = bit 0 H, bit 1 V)
MODE_FLIP = ((1.0, 1.0), (-1.0, 1.0), (-1.0, -1.0), (1.0, -1.0))
FLIP_POINTS = CORNER_NDC + ((0.0, 0.0), (0.3, -0.7))


def permuted(v, mode):
    """The eight insets as the vendor's auto path sends them in MODE."""
    out = []
    for corner in range(4):
        source = MODE_PERM[mode][corner]
        out.extend([v[2 * source], v[2 * source + 1]])
    return tuple(out)


def emit_flip(v, mode):
    m = km.keystone_matrix(vendor_order(permuted(v, mode)))
    sx, sy = MODE_FLIP[mode]
    points = []
    for x, y in FLIP_POINTS:
        p = km.apply_matrix(m, sx * x, sy * y)
        points.extend([p[0], p[1]])
    print("f %d %s %s" % (mode, " ".join("%d" % t for t in v),
                          " ".join("%.17g" % x for x in points)))


def vendor_order(v):
    """Our eight -> the eight floats the vendor's parcel carries."""
    out = []
    for slot in range(4):
        corner = CORNER_OF_SLOT[slot]
        out.extend([v[2 * corner], v[2 * corner + 1]])
    return tuple(out)


def emit(v):
    m = km.keystone_matrix(vendor_order(v))
    points = []
    for x, y in CORNER_NDC:
        p = km.apply_matrix(m, x, y)
        points.extend([p[0], p[1]])
    print("m %s %s %s" % (" ".join("%d" % t for t in v),
                          " ".join("%.17g" % x for x in m),
                          " ".join("%.17g" % x for x in points)))


def main():
    for v in FIXED:
        emit(v)
    rng = random.Random(20260922)
    for _ in range(200):
        emit(tuple(rng.randint(0, 400) for _ in range(8)))
    rng = random.Random(20260926)
    for mode in range(4):
        for v in FIXED:
            emit_flip(v, mode)
        for _ in range(50):
            emit_flip(tuple(rng.randint(0, 400) for _ in range(8)), mode)
    for v in CLAMPS:
        out = km.clamp_permille(vendor_order(v))
        ours = [0] * 8
        for slot in range(4):
            corner = CORNER_OF_SLOT[slot]
            ours[2 * corner] = out[2 * slot]
            ours[2 * corner + 1] = out[2 * slot + 1]
        print("c %s %s" % (" ".join("%d" % t for t in v),
                           " ".join("%d" % t for t in ours)))
    for v in REJECTS:
        try:
            km.keystone_matrix(vendor_order(v))
        except km.KeystoneRejected:
            print("r %s" % " ".join("%d" % t for t in v))
        else:
            raise SystemExit("the reference accepted %s -- the test vector is wrong" % (v,))


if __name__ == "__main__":
    main()
