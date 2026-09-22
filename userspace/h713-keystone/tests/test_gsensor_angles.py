#!/usr/bin/env python3
"""Golden tests for model/gsensor_angles.py (package AP2g)."""

import math
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                os.pardir, "model"))

import gsensor_angles as g                                    # noqa: E402

LEVEL = g.counts_from_gvector(0.0, 0.0, 1.0)                  # (0, 0, 8000)


class KernelSide(unittest.TestCase):
    """stk_read_accel_rawdata 0xC06BC5F4, stk_work_queue 0xC06BD1D4,
    shake_for_vafocus 0xC06BEAE0, sensor_xyz_mode_show 0xC06BB6E4."""

    def test_decode_block_sc7a20_is_left_justified(self):
        # 12-bit digit 500 = one g at +-4 g, HR mode -> 0x1F40 in the pair.
        self.assertEqual(g.decode_block(bytes([0, 0, 0, 0, 0x40, 0x1F])),
                         (0, 0, 8000))
        self.assertEqual(g.SC7A20_COUNTS_PER_G, 8000)

    def test_decode_block_sign_and_shift(self):
        blk = bytes([0x00, 0xF0, 0x00, 0x10, 0x00, 0x80])
        self.assertEqual(g.decode_block(blk), (-4096, 4096, -32768))
        self.assertEqual(g.decode_block(blk, g.STK_DATA_SHIFT[0x23]),
                         (-256, 256, -2048))
        self.assertEqual(g.decode_block(blk, g.STK_DATA_SHIFT[0x86]),
                         (-64, 64, -512))

    def test_remap_is_a_swap_and_its_own_inverse(self):
        chip = (11, -22, 33)
        self.assertEqual(g.kernel_axis_remap(chip), (-22, 11, 33))
        self.assertEqual(g.kernel_axis_remap(g.kernel_axis_remap(chip)), chip)

    def test_direction_and_swipe_change_nothing(self):
        chip = (7, -8, 9)
        for d in sorted(g.DIRECTION_REMAP):
            self.assertEqual(g.kernel_axis_remap(chip, g.DIRECTION_REMAP[d]),
                             g.kernel_axis_remap(chip),
                             "stk,direction = %d must not move an axis" % d)

    def test_xyz_data_text_and_the_apps_parser(self):
        txt = g.xyz_data_text(g.kernel_axis_remap((-1234, 56, 7890)))
        self.assertEqual(txt, "56,-1234,7890\n")
        self.assertEqual(g.parse_xyz_data(txt), [56, -1234, 7890])
        self.assertEqual(g.parse_xyz_data("0,0,0\n"), [0, 0, 0])


class AppSide(unittest.TestCase):
    """get_gsensor_du 0x00026A60, setgsensorInit 0x00026A38,
    LocalService.optKeystoneFun LocalService.java:1099."""

    def setUp(self):
        g.set_gsensor_init(*LEVEL)

    def test_level_device_gives_zero_zero(self):
        self.assertEqual(g.opt_keystone_angles(LEVEL), (0.0, 0.0))
        self.assertEqual(g.get_gsensor_du(*LEVEL)[:2], (0.0, 0.0))

    def test_pure_pitch_ten_degrees_reads_back_as_gsy(self):
        counts = g.counts_from_gvector(*g.gvector_for_tilt(10.0))
        gs_x, gs_y = g.opt_keystone_angles(counts)
        self.assertEqual(counts, (0, 1389, 7878))
        self.assertAlmostEqual(gs_y, 10.0, delta=0.02)
        self.assertEqual(gs_x, 0.0)

    def test_pitch_is_exact_under_roll_but_roll_is_not(self):
        g.set_gsensor_init(*LEVEL)
        counts = g.counts_from_gvector(*g.gvector_for_tilt(10.0, 20.0))
        du = g.get_gsensor_du(*counts)
        self.assertAlmostEqual(du[1], 10.0, delta=0.02)
        self.assertLess(du[0], 20.0)
        self.assertAlmostEqual(du[0], 19.70, delta=0.05)

    def test_reference_subtraction_cancels_a_tilted_factory_attitude(self):
        ref = g.counts_from_gvector(*g.gvector_for_tilt(3.0, -2.0))
        self.assertTrue(g.check_gsensor_data_ok(*ref))
        g.set_gsensor_init(*ref)
        self.assertEqual(g.opt_keystone_angles(ref), (0.0, 0.0))

    def test_all_zero_sample_and_reference_are_guarded(self):
        g.set_gsensor_init(0, 0, 0)
        self.assertEqual(g.get_gsensor_du(0, 0, 0), (0.0, 0.0, 0.0))
        self.assertFalse(g.check_gsensor_data_ok(0, 0, 0))
        self.assertFalse(g.check_gsensor_data_ok(9000, 0, 8000))
        self.assertFalse(g.check_gsensor_data_ok(0, 0, -8000))

    def test_dead_band_on_gsx_only(self):
        for roll, want_zero in ((0.2, True), (0.29, True), (0.4, False)):
            counts = g.counts_from_gvector(*g.gvector_for_tilt(0.0, roll))
            gs_x, _ = g.opt_keystone_angles(counts)
            self.assertEqual(gs_x == 0.0, want_zero, "roll %s" % roll)
        counts = g.counts_from_gvector(*g.gvector_for_tilt(0.2))
        gs_x, gs_y = g.opt_keystone_angles(counts)
        self.assertEqual(gs_x, 0.0)
        self.assertNotEqual(gs_y, 0.0)          # GsY has no dead band
        self.assertAlmostEqual(gs_y, 0.2, delta=0.02)

    def test_dead_band_of_the_dead_sc7a20_branch(self):
        counts = g.counts_from_gvector(*g.gvector_for_tilt(0.0, 4.0))
        self.assertEqual(g.opt_keystone_angles(counts, sensor_type=2)[0], 0.0)
        self.assertNotEqual(g.opt_keystone_angles(counts, sensor_type=1)[0],
                            0.0)
        self.assertEqual(
            g.opt_keystone_angles(counts, sensor_type=2, hsavetype=1)[1],
            g.GSY_IGNORE)

    def test_upside_down_flips_both_angles(self):
        counts = g.counts_from_gvector(*g.gvector_for_tilt(10.0, 5.0))
        up = g.opt_keystone_angles(counts)
        down = g.opt_keystone_angles((counts[0], counts[1], -counts[2]))
        self.assertLess(down[1], 0.0)
        self.assertAlmostEqual(abs(down[1]), abs(up[1]), delta=0.3)

    def test_tpwithgsy_zero_replaces_gsy_by_the_sentinel(self):
        counts = g.counts_from_gvector(*g.gvector_for_tilt(10.0))
        self.assertEqual(g.opt_keystone_angles(counts, tpwithgsy=False)[1],
                         g.GSY_IGNORE)


class MainlineIIO(unittest.TestCase):
    """st_accel 12-bit channels vs the vendor's left-justified counts."""

    SAMPLES = ((0, 0, 500), (87, -15, 492), (-250, 100, 430))

    def test_iio_axis_map(self):
        self.assertEqual(g.IIO_TO_VENDOR_AXIS, {"y": 0, "x": 1, "z": 2})
        self.assertEqual(g.iio_to_vendor_counts(1, 2, 3), (32, 16, 48))

    def test_three_synthetic_samples_give_the_same_angles(self):
        ref_iio = (0, 0, 500)
        rows = []
        for ax, ay, az in self.SAMPLES:
            g.set_gsensor_init(*g.iio_to_vendor_counts(*ref_iio))
            vendor = g.get_gsensor_du(*g.iio_to_vendor_counts(ax, ay, az))
            g.set_gsensor_init(*g.iio_to_vendor_counts(*ref_iio, factor=1))
            plain = g.get_gsensor_du(
                *g.iio_to_vendor_counts(ax, ay, az, factor=1))
            self.assertEqual(vendor, plain)     # bit for bit, not just close
            rows.append((ax, ay, az, vendor[0], vendor[1]))
        self.assertEqual(len(rows), 3)
        for ax, ay, az, gx, gy in rows:
            self.assertAlmostEqual(
                gx, math.degrees(math.atan2(ay, math.hypot(ax, az))),
                delta=0.01)
            self.assertAlmostEqual(
                gy, math.degrees(math.atan2(ax, math.hypot(ay, az))),
                delta=0.01)

    def test_scale_invariance_holds_for_any_common_power_of_four(self):
        g.set_gsensor_init(0, 0, 500)
        base = g.get_gsensor_du(87, -15, 492)
        for k in (4, 16, 64):
            g.set_gsensor_init(0, 0, 500 * k)
            self.assertEqual(g.get_gsensor_du(87 * k, -15 * k, 492 * k), base)

    def test_the_sums_of_squares_wrap_like_the_binary(self):
        # MUL/MADD are 32 bit.  Two axes at -32768 sum to exactly 2**31, one
        # count past INT_MAX, so the square root sees a negative operand.  No
        # real s16 sample reaches it; the model wraps rather than hide it.
        g.set_gsensor_init(0, 0, 500)
        self.assertNotEqual(g.get_gsensor_du(1, -32768, -32768)[0],
                            g.get_gsensor_du(1, -32768, -32768)[0])
        self.assertEqual(g.i32(32768 * 32768 + 32768 * 32768), -(2 ** 31))


if __name__ == "__main__":
    unittest.main(verbosity=2)
