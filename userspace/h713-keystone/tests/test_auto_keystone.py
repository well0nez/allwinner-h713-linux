#!/usr/bin/env python3
"""Golden tests for model/auto_keystone.py (package AP2h).

Run from the package directory:  python3 -m unittest discover -s tests -v
Every expectation is behaviour of AP2g, AP2c or AP2f, not a wish of this
package; the three models are used unchanged and none of their own tests is
repeated here.  What is tested is the JOIN: the axis order, the two value
orders, the sign of the correction and the clamps.
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                os.pardir, "model"))

import auto_keystone as ak                                    # noqa: E402
import gsensor_angles as gsa                                  # noqa: E402
import keystone_geometry as kge                               # noqa: E402
import keystone_matrix as kma                                 # noqa: E402

TOL = 1e-6
LEVEL = ak.iio_from_tilt(0.0)                                 # (0, 0, 500)


def widths(permille):
    """Width of the corrected picture at the top and at the bottom edge, in
    per-mille of the panel: 1000 minus the two insets that eat into that edge.
    APP order is LT.x LT.y RT.x RT.y LB.x LB.y RB.x RB.y."""
    return (1000 - permille[0] - permille[2], 1000 - permille[4] - permille[6])


class Level(unittest.TestCase):
    """A level device must cost nothing at all."""

    def test_level_sample_gives_zero_angles_and_zero_insets(self):
        r = ak.auto_keystone(LEVEL)
        self.assertEqual(r["counts"], (0, 0, 8000))
        self.assertEqual((r["gs_x"], r["gs_y"]), (0.0, 0.0))
        # draw_ret_map_point still spends one pixel of width (AP2c section 5),
        # and 1/1920*1000 truncates to zero, so the wire value is the identity.
        self.assertEqual(r["pixels"], [1, 0, 1, 0, 1, 0, 1, 0])
        self.assertEqual(r["permille"], (0,) * 8)
        self.assertEqual(r["parcel"], (0,) * 8)

    def test_level_takes_the_identity_path_of_ap2f(self):
        r = ak.auto_keystone(LEVEL)
        state = kma.KeystoneState()
        # gLastTran is zero in .bss, so the boot sample is a memcmp HIT: the
        # true identity, and getKeyStoneMatrix never runs the solve.
        self.assertEqual(state.update(r["parcel"]), kma.IDENTITY)
        self.assertEqual(state.vertices, ((0.0, 0.0, 0.0),) * 4)
        # Forced through the solve the same eight zeros give the identity in
        # x, y and w, with m[14] = 1 from the z part of NDC_TRANSLATE.
        forced = r["matrix"]
        self.assertAlmostEqual(forced[14], 1.0, delta=TOL)
        for k in range(16):
            if k != 14:
                self.assertAlmostEqual(forced[k], kma.IDENTITY[k], delta=TOL)

    def test_a_tilted_factory_reference_cancels_itself(self):
        # The reference is subtracted, so a device provisioned out of level reports zero
        # at that same pose (get_gsensor_du @ 0x00026A60).
        pose = ak.iio_from_tilt(3.0, -2.0)
        r = ak.auto_keystone(pose, reference=ak.reference_from_iio(pose))
        self.assertEqual((r["gs_x"], r["gs_y"]), (0.0, 0.0))
        self.assertEqual(r["permille"], (0,) * 8)

    def test_the_factory_gate_rejects_a_reference_beyond_45_degrees(self):
        # checkGsensorDataOk (LocalService.java:582) wants |x| and |y| <= |z|.
        self.assertRaises(ValueError, ak.reference_from_iio,
                          ak.iio_from_tilt(60.0))


class Pitch(unittest.TestCase):
    """Nose-up must shrink the TOP edge, nose-down the BOTTOM one.

    The sign chain is: GsY is the pitch (AP2g section 4), draw_ret_map_point
    @ 0x0002EC28 uses du_y_eff = -GsY, and the largest inscribed rectangle of
    the resulting quad loses width where the picture is thrown wider.
    """

    def test_nose_up_narrows_the_top_edge(self):
        for pitch in (5.0, 10.0):
            r = ak.auto_keystone(ak.iio_from_tilt(pitch))
            top, bottom = widths(r["permille"])
            self.assertGreater(r["gs_y"], pitch - 0.1, "GsY at %g" % pitch)
            self.assertLess(top, bottom, "top width at +%g" % pitch)
            self.assertEqual(r["permille"][4], 0)      # LB.x, bottom left
            self.assertEqual(r["permille"][6], 0)      # RB.x, bottom right
            self.assertGreater(r["permille"][0], 0)    # LT.x
            self.assertEqual(r["permille"][0], r["permille"][2])

    def test_nose_down_narrows_the_bottom_edge(self):
        for pitch in (-5.0, -10.0):
            r = ak.auto_keystone(ak.iio_from_tilt(pitch))
            top, bottom = widths(r["permille"])
            self.assertLess(r["gs_y"], pitch + 0.1, "GsY at %g" % pitch)
            self.assertLess(bottom, top, "bottom width at %g" % pitch)
            self.assertEqual(r["permille"][0], 0)      # LT.x
            self.assertEqual(r["permille"][2], 0)      # RT.x
            self.assertGreater(r["permille"][4], 0)    # LB.x
            self.assertEqual(r["permille"][4], r["permille"][6])

    def test_the_two_signs_cost_nearly_the_same_width(self):
        # AP2c section 3: the two-pass integer search is NOT symmetric - it anchors on
        # the bottom row and its grid origin is abs(min) + 20 - so +a and -a give the
        # same rectangle only to within a couple of pixels. At +-5 degrees the narrowed
        # edge comes out 944 against 942 per-mille, one panel pixel per corner; the test
        # pins that and does not hide it.
        for pitch in (5.0, 10.0, 15.0):
            up = widths(ak.auto_keystone(ak.iio_from_tilt(pitch))["permille"])
            down = widths(ak.auto_keystone(ak.iio_from_tilt(-pitch))["permille"])
            self.assertAlmostEqual(up[0], down[1], delta=3)
            self.assertAlmostEqual(up[1], down[0], delta=3)

    def test_more_pitch_costs_more_picture(self):
        last = 1000
        for pitch in (0.0, 5.0, 10.0, 15.0):
            top = widths(ak.auto_keystone(ak.iio_from_tilt(pitch))["permille"])[0]
            self.assertLessEqual(top, last)
            last = top

    def test_every_pitch_of_the_sweep_stays_inside_the_app_clamps(self):
        # AP2f's clamp_permille is the MANUAL path; the auto result must pass it
        # untouched, and stay inside the native 0..1000 range check as well.
        for row in ak.sweep(range(-15, 16, 5)):
            self.assertEqual(row["clamped"], row["parcel"])
            for value in row["parcel"]:
                self.assertTrue(0 <= value <= 1000, row["parcel"])
            kma.corners_from_ndc_fractions(
                kma.fractions_from_permille(row["parcel"]))   # no rejection


class Roll(unittest.TestCase):
    """GsX enters AP2c only as the z rotation of the two rotation builders."""

    def test_roll_reads_back_as_gsx_and_leaves_gsy_alone(self):
        for roll in (5.0, -5.0):
            r = ak.auto_keystone(ak.iio_from_tilt(0.0, roll))
            self.assertAlmostEqual(r["gs_x"], roll, delta=0.06)
            self.assertEqual(r["gs_y"], 0.0)

    def test_roll_is_exactly_the_z_rotation_term(self):
        # With both camera angles and GsY at zero, set_rotate_yxz(0, 0, -GsX) @
        # 0x0002842C degenerates to Rz(-GsX) and the wall quad is the level frustum
        # turned by that angle - the vendor's pi, not math.pi.
        gs_x = ak.auto_keystone(ak.iio_from_tilt(0.0, 5.0))["gs_x"]
        m = kge.set_rotate_yxz(0.0, 0.0, -gs_x)
        z_only = kge._rot("z", -gs_x)
        for i in range(3):
            for j in range(3):
                self.assertAlmostEqual(m[i][j], z_only[i][j], delta=1e-15)
        fdd = kge.f32(kge.HY310_INI["fdd"])
        opt = kge.reset_tou_she_bi(kge.HY310_INI, kge.itrunc(fdd))
        hx = kge.f32(fdd * opt["tan_lr_v"])
        hy = kge.f32(fdd * opt["tan_hp_v"])
        s, c = kge.sin_call(-gs_x), kge.cos_call(-gs_x)
        for px, py in ((-hx, -hy), (hx, -hy), (-hx, hy), (hx, hy)):
            got = kge._project(m, px, py, fdd)
            self.assertAlmostEqual(got[0], c * px - s * py, delta=1e-3)
            self.assertAlmostEqual(got[1], s * px + c * py, delta=1e-3)

    def test_the_two_roll_signs_mirror_left_and_right(self):
        plus = ak.auto_keystone(ak.iio_from_tilt(0.0, 5.0))["permille"]
        minus = ak.auto_keystone(ak.iio_from_tilt(0.0, -5.0))["permille"]
        mirrored = (plus[2], plus[3], plus[0], plus[1],
                    plus[6], plus[7], plus[4], plus[5])
        self.assertEqual(mirrored, minus)
        self.assertNotEqual(plus, (0,) * 8)

    def test_the_dead_band_swallows_a_fifth_of_a_degree(self):
        # LocalService.java:1121, 0.3 degrees, and on GsX only.
        small = ak.auto_keystone(ak.iio_from_tilt(0.0, 0.2))
        self.assertEqual(small["gs_x"], 0.0)
        self.assertEqual(small["permille"], (0,) * 8)
        self.assertNotEqual(ak.auto_keystone(ak.iio_from_tilt(0.0, 1.0))["gs_x"],
                            0.0)
        # the same angle as a PITCH is passed through at full resolution
        self.assertNotEqual(ak.auto_keystone(ak.iio_from_tilt(0.2))["gs_y"], 0.0)


class Matrix(unittest.TestCase):
    def test_round_trip_property_of_ap2f_for_ten_degrees_nose_up(self):
        # AP2f section 2: K maps the four NDC panel corners onto the four inset corners,
        # in slot order lb, lt, rt, rb.
        r = ak.auto_keystone(ak.iio_from_tilt(10.0))
        targets = kma.corners_from_ndc_fractions(
            kma.fractions_from_permille(r["parcel"]))
        for slot in range(4):
            px, py = kma.DEFAULT_CORNERS[slot]
            out = kma.apply_matrix(r["matrix"], px, py)
            self.assertAlmostEqual(out[0], targets[slot][0], delta=TOL,
                                   msg="x, slot %d" % slot)
            self.assertAlmostEqual(out[1], targets[slot][1], delta=TOL,
                                   msg="y, slot %d" % slot)
        self.assertNotEqual(r["matrix"], kma.IDENTITY)


class Chain(unittest.TestCase):
    """The joins themselves: axis order, value order, units."""

    def test_the_iio_axis_map_is_ap2g_section_5(self):
        r = ak.auto_keystone((87, -15, 492))
        self.assertEqual(r["counts"], (-240, 1392, 7872))
        self.assertAlmostEqual(r["gs_x"], -1.7196, delta=5e-5)
        self.assertAlmostEqual(r["gs_y"], 10.0233, delta=5e-5)

    def test_iio_from_tilt_is_the_inverse_of_iio_to_vendor_counts(self):
        for pitch, roll in ((0.0, 0.0), (7.0, -3.0), (-12.0, 9.0)):
            iio = ak.iio_from_tilt(pitch, roll)
            counts = gsa.iio_to_vendor_counts(*iio)
            self.assertEqual(iio, (counts[1] // 16, counts[0] // 16,
                                   counts[2] // 16))

    def test_the_parcel_permutation(self):
        app = (10, 11, 20, 21, 30, 31, 40, 41)     # LT RT LB RB
        self.assertEqual(ak.to_parcel_order(app),
                         (30, 31, 10, 11, 20, 21, 40, 41))   # lb lt rt rb
        self.assertEqual(ak.to_parcel_order(ak.APP_ORDER),
                         ("LB.x", "LB.y", "LT.x", "LT.y",
                          "RT.x", "RT.y", "RB.x", "RB.y"))
        self.assertEqual(len(ak.PARCEL_ORDER), 8)

    def test_the_permille_conversion_commutes_with_the_permutation(self):
        # x is divided by 1920 and y by 1080, and the permutation moves pairs, so
        # efect_tp_correct may run on either side of androidN_tp_correct.
        pixels = ak.auto_keystone(ak.iio_from_tilt(12.0, 4.0))["pixels"]
        a = ak.to_parcel_order(tuple(kge.to_permille(pixels)))
        b = tuple(kge.to_permille(ak.to_parcel_order(pixels)))
        self.assertEqual(a, b)

    def test_the_sentinel_hands_the_pitch_back_to_the_camera(self):
        # persist.sys.tpwithgsy == "0" replaces GsY by 360.0, which is outside the
        # -60..60 window, so du_y survives and the picture follows the camera pitch
        # instead (AP2g section 3c, AP2c section 1).
        r = ak.auto_keystone(ak.iio_from_tilt(10.0), tpwithgsy=False, du_y=5.0)
        self.assertEqual(r["gs_y"], gsa.GSY_IGNORE)
        camera = ak.auto_keystone(LEVEL, tpwithgsy=False, du_y=5.0)
        self.assertEqual(r["permille"], camera["permille"])


if __name__ == "__main__":
    unittest.main()
