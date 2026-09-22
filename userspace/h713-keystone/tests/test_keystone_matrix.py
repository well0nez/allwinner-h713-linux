"""Unit tests for the vendor keystone reference (AP2f).

Run from the package directory: python3 -m unittest discover -s tests -v
Every expectation is the vendor's behaviour as read out of libkeystone (addresses in
model/keystone_matrix.py), not a wish of this model.
"""

import os
import random
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "model"))

import keystone_matrix as km    # noqa: E402

TOL = 1e-6


def random_insets(rng, limit=400):
    """Eight per-mille values that survive both the app clamp and the native range check."""
    return tuple(rng.randint(0, limit) for _ in range(8))


class TestIdentity(unittest.TestCase):
    def test_boot_path_is_exactly_identity(self):
        """gLastTran is zero in .bss, so eight zeros are a cache HIT: the identity, no solve."""
        state = km.KeystoneState()
        self.assertEqual(state.update((0,) * 8), km.IDENTITY)
        self.assertEqual(state.vertices, ((0.0, 0.0, 0.0),) * 4)   # solve never ran

    def test_zero_insets_through_the_solve(self):
        """The solve itself returns the identity in x, y and w - and z translated by 1.

        NOT the identity in m[14]: the third stack matrix at sp+0x110 (0x00003208..0x00003278)
        is translate(1, 1, 1), so the z row carries a +1 the vendor never cancels.  The brief
        expects "matrix == I"; that is true for the 12 elements of the x/y/w part and for the
        cached boot path above, and false for m[14].  Reported, not papered over.
        """
        m = km.keystone_matrix((0,) * 8)
        expected = list(km.IDENTITY)
        expected[14] = 1.0
        self.assertEqual(list(m), expected)
        for i in (0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 15):
            self.assertEqual(m[i], km.IDENTITY[i], "element %d" % i)

    def test_zero_insets_move_no_point(self):
        m = km.keystone_matrix((0,) * 8)
        for x, y in ((-1.0, 1.0), (0.0, 0.0), (0.25, -0.75), (1.0, 1.0)):
            out = km.apply_matrix(m, x, y)
            self.assertAlmostEqual(out[0], x, delta=TOL)
            self.assertAlmostEqual(out[1], y, delta=TOL)


class TestCorners(unittest.TestCase):
    def test_one_corner_lands_on_its_target(self):
        """100 per-mille on slot 0 x: the NDC corner (-1, 1) must land on (2*0.1-1, 1)."""
        permille = (100, 0, 0, 0, 0, 0, 0, 0)
        m = km.keystone_matrix(permille)
        target = km.corners_from_ndc_fractions(km.fractions_from_permille(permille))[0]
        out = km.apply_matrix(m, -1.0, 1.0)
        self.assertAlmostEqual(out[0], target[0], delta=TOL)
        self.assertAlmostEqual(out[1], target[1], delta=TOL)
        self.assertAlmostEqual(target[0], -0.8, delta=1e-7)
        for slot, corner in enumerate(km.DEFAULT_CORNERS[1:], start=1):
            out = km.apply_matrix(m, corner[0], corner[1])
            self.assertAlmostEqual(out[0], corner[0], delta=TOL)
            self.assertAlmostEqual(out[1], corner[1], delta=TOL, msg="slot %d" % slot)

    def test_panel_corners_map_onto_the_inset_corners(self):
        """The four NDC panel corners, in slot order, are the four targets - random insets."""
        rng = random.Random(20260921)
        for _ in range(200):
            permille = random_insets(rng)
            m = km.keystone_matrix(permille)
            targets = km.corners_from_ndc_fractions(km.fractions_from_permille(permille))
            for slot in range(4):
                px, py = km.DEFAULT_CORNERS[slot]
                out = km.apply_matrix(m, px, py)
                self.assertAlmostEqual(out[0], targets[slot][0], delta=TOL,
                                       msg="x, slot %d, %s" % (slot, permille))
                self.assertAlmostEqual(out[1], targets[slot][1], delta=TOL,
                                       msg="y, slot %d, %s" % (slot, permille))

    def test_straight_lines_stay_straight(self):
        """A projective map keeps collinearity - this is what the dead mesh path would break."""
        m = km.keystone_matrix((200, 60, 0, 0, 150, 0, 0, 90))
        a = km.apply_matrix(m, -1.0, 0.3)
        b = km.apply_matrix(m, 0.0, 0.3)
        c = km.apply_matrix(m, 1.0, 0.3)
        cross = (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])
        self.assertAlmostEqual(cross, 0.0, delta=TOL)


class TestMirrorSymmetry(unittest.TestCase):
    def test_horizontal_mirror(self):
        """Mirroring the panel swaps slot 0 with slot 3 and slot 1 with slot 2.

        The matrices themselves agree only up to a common scale factor (a homography is
        projective), so the contract is on the mapped points, which is what the GPU sees.
        """
        rng = random.Random(4711)
        for _ in range(100):
            permille = random_insets(rng)
            mirrored = permille[6:8] + permille[4:6] + permille[2:4] + permille[0:2]
            m = km.keystone_matrix(permille)
            mm = km.keystone_matrix(mirrored)
            for x, y in ((-1.0, 1.0), (-1.0, -1.0), (1.0, -1.0), (1.0, 1.0),
                         (0.3, -0.7), (0.0, 0.0)):
                a = km.apply_matrix(m, x, y)
                b = km.apply_matrix(mm, -x, y)
                self.assertAlmostEqual(-a[0], b[0], delta=TOL, msg=str(permille))
                self.assertAlmostEqual(a[1], b[1], delta=TOL, msg=str(permille))


class TestClampsAndRejection(unittest.TestCase):
    def test_app_clamp_pairs_opposite_corners(self):
        self.assertEqual(km.clamp_permille((900, 0, 0, 0, 0, 0, 300, 0)),
                         (700, 0, 0, 0, 0, 0, 300, 0))          # lb_x + rb_x <= 1000
        self.assertEqual(km.clamp_permille((0, 900, 0, 300, 0, 0, 0, 0)),
                         (0, 700, 0, 300, 0, 0, 0, 0))          # lb_y + lt_y <= 1000
        self.assertEqual(km.clamp_permille((-5, -5, 0, 0, 0, 0, 0, 0))[:2], (0, 0))
        self.assertEqual(km.clamp_permille((0, 0, 0, 0, 0, 0, 0, 0)), (0,) * 8)

    def test_app_clamp_honours_a_smaller_config_window(self):
        """minH_size / minV_size come from Config.manualKeystoneWidth/Height, not from 1000."""
        self.assertEqual(km.clamp_permille((500, 500, 0, 0, 0, 0, 0, 0), min_h=300, min_v=200),
                         (300, 200, 0, 0, 0, 0, 0, 0))

    def test_native_rejects_out_of_range(self):
        for permille, slot in (((1200, 0, 0, 0, 0, 0, 0, 0), 0),
                               ((0, 1001, 0, 0, 0, 0, 0, 0), 0),
                               ((0, 0, -1, 0, 0, 0, 0, 0), 1),
                               ((0, 0, 0, 0, 2000, 0, 0, 0), 2),
                               ((0, 0, 0, 0, 0, 0, 0, 1500), 3)):
            with self.assertRaises(km.KeystoneRejected) as caught:
                km.keystone_matrix(permille)
            self.assertEqual(caught.exception.slot, slot)
            self.assertIn("wrong input trans", str(caught.exception))

    def test_native_check_is_weaker_than_the_app_clamp(self):
        """Two opposite corners at 1000 break the app clamp but pass the native check."""
        self.assertNotEqual(km.clamp_permille((1000, 0, 0, 0, 0, 0, 1000, 0)),
                            (1000, 0, 0, 0, 0, 0, 1000, 0))
        km.keystone_matrix((1000, 0, 0, 0, 0, 0, 1000, 0))      # must not raise

    def test_rejection_keeps_the_previous_matrix_and_partly_updates_the_vertices(self):
        state = km.KeystoneState()
        good = state.update((100, 0, 0, 0, 0, 0, 0, 0))
        after = state.update((200, 0, 0, 0, 0, 0, 0, 1500))     # slot 3 out of range
        self.assertEqual(after, good)                           # gKeyStoneMatrix untouched
        self.assertAlmostEqual(state.vertices[0][0], -0.6, delta=1e-6)   # slot 0 taken
        self.assertEqual(state.vertices[1:], ((-1.0, -1.0, 0.2), (1.0, -1.0, 0.2),
                                              (1.0, 1.0, 0.2)))          # rest back to default

    def test_cache_short_circuits_on_an_unchanged_tran(self):
        state = km.KeystoneState()
        first = state.update((50, 0, 0, 0, 0, 0, 0, 0))
        state.vertices = ((9.0, 9.0, 9.0),) * 4                 # poison, must not be touched
        self.assertEqual(state.update((50, 0, 0, 0, 0, 0, 0, 0)), first)
        self.assertEqual(state.vertices, ((9.0, 9.0, 9.0),) * 4)


class TestEdgeQuad(unittest.TestCase):
    def test_vertices_for_a_known_inset(self):
        permille = (100, 0, 0, 0, 0, 0, 0, 0)
        state = km.KeystoneState()
        state.update(permille)
        quad = km.edge_quad(1920, 1080, state.vertices)
        self.assertEqual(quad["positions"],
                         ((-0.7999999970197678, 1.0, 0.2), (-1.0, -1.0, 0.2),
                          (1.0, -1.0, 0.2), (1.0, 1.0, 0.2)))
        self.assertEqual(quad["tex_coords"], ((0.0, 1.0, 0.2), (0.0, 0.0, 0.2),
                                              (1.0, 0.0, 0.2), (1.0, 1.0, 0.2)))
        self.assertEqual(quad["draw_mode"], "GL_TRIANGLE_FAN")
        self.assertEqual(quad["vertex_count"], 4)
        self.assertEqual(quad["texture_unit"], 5)

    def test_mask_geometry_and_border(self):
        quad = km.edge_quad(1920, 1080)
        self.assertEqual((quad["mask_width"], quad["mask_height"]), (480, 272))
        self.assertEqual(quad["border_value"], 235)             # 255 - alias.edge (20)
        mask = km.edge_mask(quad["mask_width"], quad["mask_height"], quad["border_value"])
        self.assertEqual(len(mask), quad["mask_texels"])
        w, h = quad["mask_width"], quad["mask_height"]
        self.assertEqual(mask[0], 235)
        self.assertEqual(mask[w - 1], 235)
        self.assertEqual(mask[(h - 1) * w], 235)
        self.assertEqual(mask[h * w - 1], 235)
        self.assertEqual(mask[w + 1], 0)                        # interior
        self.assertEqual(mask[w * 2 - 1], 235)                  # right edge of row 1
        self.assertEqual(set(mask[w + 1:w * 2 - 1]), set([0]))

    def test_properties_switch_the_pass_off_and_resize_the_mask(self):
        self.assertIsNone(km.edge_quad(1920, 1080, enable=0))
        self.assertEqual(km.edge_quad(1920, 1080, scale=0)["mask_width"], 480)   # 0 -> 4
        self.assertEqual(km.edge_quad(1280, 720, scale=8)["mask_width"], 160)
        self.assertEqual(km.edge_quad(1280, 720, scale=8)["mask_height"], 96)
        self.assertEqual(km.edge_quad(1920, 1080, edge=0)["border_value"], 255)


class TestShadersAndHelpers(unittest.TestCase):
    def test_shader_sources_are_the_vendor_bytes(self):
        self.assertEqual(len(km.EDGE_VERTEX_SHADER.encode("ascii")), 178)    # at 0x00001484
        self.assertEqual(len(km.EDGE_FRAGMENT_SHADER.encode("ascii")), 180)  # at 0x000012B4
        for name in km.EDGE_ATTRIBUTES:
            self.assertIn(name, km.EDGE_VERTEX_SHADER)
        self.assertIn(km.EDGE_UNIFORMS[0], km.EDGE_FRAGMENT_SHADER)
        self.assertTrue(km.EDGE_VERTEX_SHADER.startswith("#version 320 es\n"))

    def test_mat_mul_is_column_major(self):
        self.assertEqual(km.mat_mul(km.IDENTITY, km.NDC_SCALE), km.NDC_SCALE)
        moved = km.mat_mul(km.NDC_SCALE, km.NDC_TRANSLATE)      # scale after translate
        self.assertEqual(moved[12:], (0.5, 0.5, 1.0, 1.0))

    def test_float32_rounding_matches_the_parcel(self):
        self.assertEqual(km.fractions_from_permille((1,) * 8)[0], 0.0010000000474974513)
        self.assertEqual(km.to_float32(km.IDENTITY), km.IDENTITY)


if __name__ == "__main__":
    unittest.main()
