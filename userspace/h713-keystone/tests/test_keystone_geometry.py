#!/usr/bin/env python3
"""Unit tests for model/keystone_geometry.py.

Run from the package directory:  python3 -m unittest discover -s tests -v
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                os.pardir, "model"))

import keystone_geometry as kg          # noqa: E402


def quad_of(du_r, du_y, gs_x, gs_y, ini=None):
    """The four wall-plane corners draw_ret_map_point @ 0x0002EC28 builds."""
    ini = kg.HY310_INI if ini is None else ini
    fdd = kg.f32(ini["fdd"])
    opt = kg.reset_tou_she_bi(ini, kg.itrunc(fdd))
    hx = kg.f32(fdd * opt["tan_lr_v"])
    hy = kg.f32(fdd * opt["tan_hp_v"])
    du_y_eff = kg.f32(-gs_y) if -60.0 < gs_y < 60.0 else du_y
    m = kg.set_rotate_zyx(du_y, du_r, gs_x)
    nx, ny, nz = kg.xl_rotate_f(m, 0.0, 0.0, 1.0)
    norm = (nx * nx + ny * ny + nz * nz) ** 0.5
    if not -60.0 < gs_y < 60.0:
        du_y_eff = 90.0 - kg.acos_call(ny / norm)
    du_r_eff = 90.0 - kg.acos_call(nx / norm)
    m = kg.set_rotate_yxz(du_y_eff, du_r_eff, -gs_x)
    return [kg._project(m, -hx, -hy, fdd), kg._project(m, hx, -hy, fdd),
            kg._project(m, -hx, hy, fdd), kg._project(m, hx, hy, fdd)], hx, hy


def inside(quad, point):
    """Is the point inside the convex quad LB, RB, LT, RT?"""
    ring = [quad[0], quad[1], quad[3], quad[2]]
    signs = []
    for i in range(4):
        ax, ay = ring[i]
        bx, by = ring[(i + 1) % 4]
        px, py = point
        signs.append((bx - ax) * (py - ay) - (by - ay) * (px - ax))
    return all(s >= -1.0 for s in signs) or all(s <= 1.0 for s in signs)


class TestOptics(unittest.TestCase):
    """reset_TouSheBi @ 0x0002BE78 and read_ini_flle @ 0x0002ACA8."""

    def test_ini_crc_is_the_one_in_the_vendor_file(self):
        # the only vendor-computed number the library carries for these
        # constants; a mismatch makes read_ini_flle throw the whole ini away
        self.assertEqual(kg.ini_crc(kg.HY310_INI), kg.HY310_INI_CRC)

    def test_half_field_tangents(self):
        opt = kg.reset_tou_she_bi(kg.HY310_INI, 1700)
        # TAN_HW_V is the projected aspect and must be the panel aspect
        self.assertAlmostEqual(opt["tan_hw_v"],
                               kg.HY310_INI["Hhalf"] / kg.HY310_INI["Whalf"],
                               places=5)
        self.assertAlmostEqual(opt["tan_lr_v"], 0.6115390658378601, places=9)
        self.assertAlmostEqual(opt["tan_hp_v"], 0.3430423438549042, places=9)
        # D = v - F, and the image is CELIANF_W wide at that distance
        self.assertAlmostEqual(opt["celianf_w"] / (2 * opt["celianf_d"]),
                               opt["tan_lr_v"], places=6)

    def test_off_axis_lengthens_the_throw(self):
        tilted = dict(kg.HY310_INI, OFF_AXIS=10.0)
        flat = kg.reset_tou_she_bi(kg.HY310_INI, 1700)["celianf_w"]
        self.assertGreater(kg.reset_tou_she_bi(tilted, 1700)["celianf_w"],
                           flat)


class TestRotation(unittest.TestCase):
    """set_rotate_* @ 0x00028140 / 0x0002842C / 0x00028724."""

    def test_zxy_is_the_inverse_of_yxz(self):
        fwd = kg.set_rotate_yxz(7.0, -3.0, -2.0)
        back = kg.set_rotate_zxy(-7.0, 3.0, 2.0)
        prod = kg._mm(back, fwd)
        for i in range(3):
            for j in range(3):
                self.assertAlmostEqual(prod[i][j], 1.0 if i == j else 0.0,
                                       places=9)

    def test_projection_at_rest_is_the_frustum_itself(self):
        m = kg.set_rotate_yxz(0.0, 0.0, 0.0)
        self.assertEqual(kg._project(m, 100.0, -50.0, 1700.0), (100.0, -50.0))


class TestIdentity(unittest.TestCase):
    """Zero angles must leave the picture alone."""

    def test_zero_angles_give_zero_permille(self):
        out = kg.draw_ret_map_point(0.0, 0.0, 0.0, 0.0, 0)
        self.assertEqual(kg.to_permille(out), [0] * 8)
        # at most one panel pixel of slack, from the integer search
        self.assertTrue(all(v <= 1 for v in out), out)

    def test_zero_angles_parcel_is_near_identity(self):
        out = kg.draw_ret_map_point(0.0, 0.0, 0.0, 0.0, 0)
        for value in kg.parcel_floats(out):
            self.assertLess(value, 0.001)

    def test_search_rejects_a_quad_that_is_too_small(self):
        # "CPP:PX  max_lx=... --- error": under 40 by 30 the search gives up
        tiny = [(-15.0, -8.0), (15.0, -8.0), (-15.0, 8.0), (15.0, 8.0)]
        m = kg.set_rotate_yxz(0.0, 0.0, 0.0)
        px2 = kg.make_px2xyr(m, 1700.0, 15.0, 8.0, 0.0, 1920, 1080)
        self.assertIsNone(kg.px_space_find_max_rect(tiny, 0, px2))

    def test_failed_search_zeroes_the_eight_outputs(self):
        saved = kg.px_space_find_max_rect
        kg.px_space_find_max_rect = lambda *a, **k: None
        try:
            self.assertEqual(kg.draw_ret_map_point(0.0, 0.0, 0.0, 7.0, 0),
                             [0] * 8)
        finally:
            kg.px_space_find_max_rect = saved


class TestSymmetry(unittest.TestCase):
    """Pitch +a and -a must mirror top and bottom.

    The quad mirrors exactly.  The rectangle inside it does not: the search
    works on an integer grid whose origin is abs(min) + 20 of the truncated
    corners, which differs between the two signs, and pass two anchors the
    candidate at its BOTTOM row and keeps the first row that reaches the best
    area, which biases the placement downwards.  Both are vendor behaviour, so
    the test pins the size to a quarter of a per cent and the split to two
    pixels instead of demanding an exact mirror.
    """

    def test_quad_mirrors_exactly(self):
        for angle in (2.0, 5.0, 12.0, 25.0):
            up, _, _ = quad_of(0.0, 0.0, 0.0, angle)
            down, _, _ = quad_of(0.0, 0.0, 0.0, -angle)
            self.assertEqual([(x, -y) for x, y in up[:2]], down[2:])
            self.assertEqual([(x, -y) for x, y in up[2:]], down[:2])

    def test_rectangle_has_the_same_size(self):
        for angle in (2.0, 5.0, 12.0, 25.0):
            sizes = []
            for signed in (angle, -angle):
                quad, hx, hy = quad_of(0.0, 0.0, 0.0, signed)
                ini = kg.HY310_INI
                fdd = kg.f32(ini["fdd"])
                m = kg.set_rotate_yxz(kg.f32(-signed), 0.0, -0.0)
                px2 = kg.make_px2xyr(m, fdd, hx, hy, 0.0, 1920, 1080)
                rect = kg.px_space_find_max_rect(quad, 0, px2)
                self.assertIsNotNone(rect)
                sizes.append((rect[1] - rect[0], rect[2] - rect[3]))
            for up, down in zip(sizes[0], sizes[1]):
                self.assertLessEqual(abs(up - down), 0.0025 * up,
                                     (angle, sizes))

    def test_insets_mirror_top_and_bottom(self):
        for angle in (2.0, 5.0, 12.0, 25.0):
            up = kg.draw_ret_map_point(0.0, 0.0, 0.0, angle, 0)
            down = kg.draw_ret_map_point(0.0, 0.0, 0.0, -angle, 0)
            # LT.x <-> LB.x and RT.x <-> RB.x
            self.assertLessEqual(abs(up[0] - down[4]), 2, (up, down))
            self.assertLessEqual(abs(up[2] - down[6]), 2, (up, down))
            self.assertLessEqual(abs(up[4] - down[0]), 2, (up, down))
            # the same total height is given up in both directions
            self.assertLessEqual(abs((up[1] + up[5]) - (down[1] + down[5])), 2)

    def test_roll_keeps_top_and_bottom_equal(self):
        # a rotation about the vertical axis may not tilt the picture
        for angle in (3.0, 9.0, 20.0):
            out = kg.draw_ret_map_point(angle, 0.0, 0.0, 0.0, 0)
            self.assertLessEqual(abs(out[0] - out[4]), 1, out)   # LT.x, LB.x
            self.assertLessEqual(abs(out[2] - out[6]), 1, out)   # RT.x, RB.x

    def test_roll_mirrors_left_and_right(self):
        for angle in (3.0, 9.0, 20.0):
            pos = kg.draw_ret_map_point(angle, 0.0, 0.0, 0.0, 0)
            neg = kg.draw_ret_map_point(-angle, 0.0, 0.0, 0.0, 0)
            self.assertLessEqual(abs(pos[0] - neg[2]), 2, (pos, neg))
            self.assertLessEqual(abs(pos[2] - neg[0]), 2, (pos, neg))


class TestMonotonicity(unittest.TestCase):
    """More tilt has to cost more picture."""

    def test_pitch_costs_more_with_every_degree(self):
        last = -1
        for angle in range(0, 31, 2):
            total = sum(kg.draw_ret_map_point(0.0, 0.0, 0.0, float(angle), 0))
            self.assertGreater(total, last, "gs_y=%d" % angle)
            last = total

    def test_roll_costs_more_with_every_degree(self):
        last = -1
        for angle in range(0, 41, 2):
            total = sum(kg.draw_ret_map_point(float(angle), 0.0, 0.0, 0.0, 0))
            self.assertGreater(total, last, "du_r=%d" % angle)
            last = total

    def test_narrower_zoom_target_costs_width(self):
        # zoom_scale picks the target aspect W : 1080 inside the search
        wide = kg.draw_ret_map_point(0.0, 0.0, 0.0, 0.0, 0)
        mid = kg.draw_ret_map_point(0.0, 0.0, 0.0, 0.0, 1)
        narrow = kg.draw_ret_map_point(0.0, 0.0, 0.0, 0.0, 2)
        self.assertLess(sum(wide), sum(mid))
        self.assertLess(sum(mid), sum(narrow))


class TestSearch(unittest.TestCase):
    """px_space_find_max_rect @ 0x00029B6C is a search, not a formula."""

    def test_rectangle_stays_inside_the_quad(self):
        for du_r, gs_y in ((0.0, 8.0), (0.0, -8.0), (6.0, 0.0), (6.0, 6.0)):
            quad, hx, hy = quad_of(du_r, 0.0, 0.0, gs_y)
            fdd = kg.f32(kg.HY310_INI["fdd"])
            m = kg.set_rotate_zyx(0.0, du_r, 0.0)
            nx, ny, nz = kg.xl_rotate_f(m, 0.0, 0.0, 1.0)
            norm = (nx * nx + ny * ny + nz * nz) ** 0.5
            m = kg.set_rotate_yxz(kg.f32(-gs_y),
                                  90.0 - kg.acos_call(nx / norm), -0.0)
            px2 = kg.make_px2xyr(m, fdd, hx, hy, 0.0, 1920, 1080)
            rect = kg.px_space_find_max_rect(quad, 0, px2)
            self.assertIsNotNone(rect, (du_r, gs_y))
            xl, xr, yt, yb = rect
            for corner in ((xl, yt), (xr, yt), (xl, yb), (xr, yb)):
                self.assertTrue(inside(quad, corner), (du_r, gs_y, corner))

    def test_rectangle_keeps_the_target_aspect(self):
        for zoom, width in ((0, 1920), (1, 1728), (2, 1440)):
            quad, hx, hy = quad_of(0.0, 0.0, 0.0, 7.0)
            fdd = kg.f32(kg.HY310_INI["fdd"])
            m = kg.set_rotate_yxz(kg.f32(-7.0), 0.0, -0.0)
            px2 = kg.make_px2xyr(m, fdd, hx, hy, 0.0, 1920, 1080)
            xl, xr, yt, yb = kg.px_space_find_max_rect(quad, zoom, px2)
            self.assertAlmostEqual((yt - yb) / (xr - xl), 1080.0 / width,
                                   delta=0.01)

    def test_integer_division_truncates_towards_zero(self):
        self.assertEqual(kg.idiv(-7, 2), -3)
        self.assertEqual(kg.idiv(7, -2), -3)
        self.assertEqual(kg.idiv(7, 2), 3)


class TestSensorOverride(unittest.TestCase):
    """The g-sensor beats the camera unless it sends the 360 sentinel."""

    def test_camera_pitch_is_ignored_while_the_sensor_is_valid(self):
        self.assertEqual(kg.draw_ret_map_point(0.0, 12.0, 0.0, 0.0, 0),
                         kg.draw_ret_map_point(0.0, 0.0, 0.0, 0.0, 0))

    def test_sentinel_hands_the_pitch_back_to_the_camera(self):
        cam = kg.draw_ret_map_point(0.0, 5.0, 0.0, 360.0, 0)
        sensor = kg.draw_ret_map_point(0.0, 0.0, 0.0, -5.0, 0)
        self.assertEqual(cam, sensor)

    def test_off_axis_shifts_the_effective_pitch(self):
        ini = dict(kg.HY310_INI, OFF_AXIS=4.0)
        self.assertEqual(kg.draw_ret_map_point(0.0, 0.0, 0.0, -4.0, 0, ini),
                         kg.draw_ret_map_point(0.0, 0.0, 0.0, 0.0, 0))


class TestOutputFormat(unittest.TestCase):
    """The units and the order the app sends."""

    def test_permille_conversion(self):
        self.assertEqual(kg.to_permille([192, 108, 192, 108, 0, 0, 0, 0]),
                         [100, 100, 100, 100, 0, 0, 0, 0])

    def test_parcel_order_is_lb_lt_rt_rb(self):
        px8 = [1, 2, 3, 4, 5, 6, 7, 8]          # LT, RT, LB, RB
        out = kg.parcel_floats(px8)
        self.assertEqual(out[0], kg.f32(5 / 1920.0))    # lb_x
        self.assertEqual(out[1], kg.f32(6 / 1080.0))    # lb_y
        self.assertEqual(out[2], kg.f32(1 / 1920.0))    # lt_x
        self.assertEqual(out[4], kg.f32(3 / 1920.0))    # rt_x
        self.assertEqual(out[6], kg.f32(7 / 1920.0))    # rb_x


class TestClamp(unittest.TestCase):
    """KeystoneUtils.setkeystoneValue, KeystoneUtils.java:146-275."""

    def setUp(self):
        self.corners = {"lt": (0, 0), "lb": (0, 0), "rt": (0, 0), "rb": (0, 0)}

    def test_negative_is_pulled_up_to_zero(self):
        self.assertEqual(kg.clamp_corner(self.corners, "lt", (-5, -7)), (0, 0))

    def test_free_range_is_the_full_thousand(self):
        self.assertEqual(kg.clamp_corner(self.corners, "rb", (1000, 1000)),
                         (1000, 1000))
        self.assertEqual(kg.clamp_corner(self.corners, "rb", (1001, 1001)),
                         (1000, 1000))

    def test_x_is_clamped_against_the_corner_on_the_same_row(self):
        corners = dict(self.corners, rt=(400, 0))
        self.assertEqual(kg.clamp_corner(corners, "lt", (900, 0))[0], 600)

    def test_y_is_clamped_against_the_corner_in_the_same_column(self):
        corners = dict(self.corners, lb=(0, 300))
        self.assertEqual(kg.clamp_corner(corners, "lt", (0, 900))[1], 700)

    def test_a_smaller_minimum_size_tightens_both_axes(self):
        corners = dict(self.corners, rt=(100, 0), lb=(0, 100))
        self.assertEqual(
            kg.clamp_corner(corners, "lt", (900, 900), 500, 400), (400, 300))

    def test_auto_result_survives_the_clamp_unchanged(self):
        out = kg.to_permille(kg.draw_ret_map_point(0.0, 0.0, 0.0, 10.0, 0))
        corners = {"lt": (out[0], out[1]), "rt": (out[2], out[3]),
                   "lb": (out[4], out[5]), "rb": (out[6], out[7])}
        for name in ("lt", "rt", "lb", "rb"):
            self.assertEqual(kg.clamp_corner(corners, name, corners[name]),
                             corners[name])


if __name__ == "__main__":
    unittest.main()
