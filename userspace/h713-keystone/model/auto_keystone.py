#!/usr/bin/env python3
"""The vendor auto-keystone end to end: IIO raw counts -> the 4x4 warp matrix.

Three reference models do all the work; each of them is copied into this
directory unchanged, with its own header and its own addresses (sha256 of the
copies in REPORT.txt section 0):

    gsensor_angles.py     AP2g   raw counts + factory reference -> GsX, GsY
    keystone_geometry.py  AP2c   GsX, GsY -> eight panel-pixel insets
    keystone_matrix.py    AP2f   eight per-mille insets -> the 4x4 matrix

Nothing is re-derived here.  This module only wires the three together in the
order the vendor app runs them - LocalService.optKeystoneFun (LocalService.java
:1099) -> duRYXtp.getRYXRatiomapDate -> draw_ret_map_point @ 0x0002EC28 ->
efect_tp_correct (PropertiesUtils.java:38) -> binder transaction 1050 ->
getKeyStoneMatrix @ 0x000031E8 - and names the one place where the order of the
eight values changes.

Two orders, eight values each:
    APP     LT.x LT.y RT.x RT.y LB.x LB.y RB.x RB.y  - draw_ret_map_point's own
            log order ("CPP:OUT:LT(%4d,%4d) ..."), and what efect_tp_correct
            writes into persist.htc.keystone.*; every value an inward inset
            from its own edge.
    PARCEL  lb_x lb_y lt_x lt_y rt_x rt_y rb_x rb_y  - androidN_tp_correct
            (TpCorrectUtils.java:19-41) and libkeystone slots 0..3.
PARCEL_FROM_APP is the permutation between them; it pairs x with x and y with
y, so the per-mille conversion may be done on either side of it.

The axis convention comes from AP2g: in_accel_y_raw is the vendor's X (GsX, the
roll about the optical axis), in_accel_x_raw its Y (GsY, the pitch), vendor
counts are the IIO raw values times 16.  Positive GsY is nose-up in the sense of
gvector_for_tilt; which physical direction that is on the real device is AP2g
open question 2 and needs a measurement, not a model.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import gsensor_angles as gsa                                  # noqa: E402
import keystone_geometry as kge                                # noqa: E402
import keystone_matrix as kma                                  # noqa: E402

APP_ORDER = ("LT.x", "LT.y", "RT.x", "RT.y", "LB.x", "LB.y", "RB.x", "RB.y")
PARCEL_ORDER = ("lb_x", "lb_y", "lt_x", "lt_y", "rt_x", "rt_y", "rb_x", "rb_y")
PARCEL_FROM_APP = (4, 5, 0, 1, 2, 3, 6, 7)
# st_accel serves the SC7A20 with a 12-bit channel (shift 4), so one g is 500
# IIO digits where the vendor driver counts 8000 (AP2g sections 2a and 5).
IIO_COUNTS_PER_G = gsa.SC7A20_COUNTS_PER_G >> gsa.SC7A20_IIO_SHIFT
LEVEL_REFERENCE = (0, 0, gsa.SC7A20_COUNTS_PER_G)


def reference_from_iio(accel_xyz):
    """The stored factory vector, in the units xyz_data prints.

    VajzActivity (:303-305) writes the xyz_data triple under SecureStorage /
    Settings.Global key GsInitXYZ, but only after checkGsensorDataOk
    (LocalService.java:582) accepted it; that gate is raised here instead of
    being logged, because a model that silently uses a rejected reference hides
    the one input the whole chain is measured against.
    """
    counts = gsa.iio_to_vendor_counts(*accel_xyz)
    if not gsa.check_gsensor_data_ok(*counts):
        raise ValueError("reference %r fails checkGsensorDataOk" % (counts,))
    return counts


def iio_from_tilt(pitch_deg, roll_deg=0.0, counts_per_g=IIO_COUNTS_PER_G):
    """Synthetic in_accel_{x,y,z}_raw for a pose, the inverse of AP2g's
    iio_to_vendor_counts: IIO x is the vendor Y, IIO y the vendor X.  The
    rounding to whole digits is the real ADC's, and it is why a pitch of 10
    degrees reads back as 10.0233 and not as 10."""
    vendor = gsa.counts_from_gvector(*gsa.gvector_for_tilt(pitch_deg, roll_deg),
                                     counts_per_g=counts_per_g)
    return (vendor[1], vendor[0], vendor[2])


def to_parcel_order(app8):
    """APP order -> PARCEL order, the reordering androidN_tp_correct does."""
    return tuple(app8[i] for i in PARCEL_FROM_APP)


def auto_keystone(accel_xyz, reference=LEVEL_REFERENCE, zoom_scale=0, ini=None,
                  lcd_w=1920, lcd_h=1080, sensor_type=1, hsavetype=0,
                  tpwithgsy=True, du_r=0.0, du_y=0.0, clamp=True):
    """One IIO sample plus the stored reference -> every stage of the chain.

    accel_xyz are in_accel_{x,y,z}_raw, reference is the GsInitXYZ triple in
    vendor counts (reference_from_iio builds one).  du_r / du_y are the camera
    angles; the HY310 auto path has no camera, and as long as -60 < GsY < 60 the
    sensor overrides du_y anyway (AP2c section 1).  clamp runs AP2f's
    clamp_permille, the app-side gate of the MANUAL path - the auto path never
    calls it, so a difference between parcel and clamped is a finding, not a
    correction, and the tests assert there is none.

    Returns a dict: iio, counts, gs_x, gs_y, pixels (APP order, panel pixels),
    permille (APP order), parcel (PARCEL order), clamped, matrix (16 floats,
    column major).  keystone_matrix raises KeystoneRejected if a corner leaves
    NDC; the auto path cannot reach that, because px < 1920 keeps every value
    below 1000 per-mille.
    """
    counts = gsa.iio_to_vendor_counts(*accel_xyz)
    gs_x, gs_y = gsa.opt_keystone_angles(counts, list(reference), sensor_type,
                                         hsavetype, tpwithgsy)
    pixels = kge.draw_ret_map_point(du_r, du_y, gs_x, gs_y, zoom_scale, ini,
                                    lcd_w, lcd_h)
    permille = tuple(kge.to_permille(pixels))
    parcel = to_parcel_order(permille)
    clamped = kma.clamp_permille(parcel) if clamp else parcel
    return {"iio": tuple(accel_xyz), "counts": tuple(counts),
            "gs_x": gs_x, "gs_y": gs_y, "pixels": list(pixels),
            "permille": permille, "parcel": parcel, "clamped": clamped,
            "matrix": kma.keystone_matrix(clamped)}


def sweep(pitches, roll_deg=0.0, **kwargs):
    """One auto_keystone() result per pitch, with the pitch kept in the row."""
    rows = []
    for pitch in pitches:
        row = auto_keystone(iio_from_tilt(pitch, roll_deg), **kwargs)
        row["pitch"] = float(pitch)
        row["roll"] = float(roll_deg)
        rows.append(row)
    return rows


def format_sweep(rows):
    """The sweep table of REPORT.txt section 3, per-mille in APP order."""
    head = ("pitch  in_x in_y in_z      GsX      GsY  "
            + " ".join("%4s" % name for name in APP_ORDER))
    out = [head, "-" * len(head)]
    for row in rows:
        out.append("%5.1f %5d %4d %4d %8.4f %8.4f  %s"
                   % (row["pitch"], row["iio"][0], row["iio"][1], row["iio"][2],
                      row["gs_x"], row["gs_y"],
                      " ".join("%4d" % v for v in row["permille"])))
    return "\n".join(out)


if __name__ == "__main__":
    print(format_sweep(sweep(range(-15, 16, 5))))
