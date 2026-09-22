"""Q7 item 3: `h713-extract --profile <board>` - the panel row a board's own panel_config.ini gives.

The contract of AP3g section 5: run over a board's own file, the generator has to reproduce what we
already know about that board. Here that is the "panel" dict of its installer profile, which is what
`boards/<id>/README.md` points at - so the HY310 row and the row of the archived HY300 Pro+ (DDR3)
image, cstenger's HY200 QZ713DF_A1, are compared field for field against committed numbers.

No vendor file is read: the two inis below are written from those very profile dicts plus the ten
further values AP3g 4.2 records, so nothing here is a copy of anything.
"""

import os
import sys
import unittest

import support                 # imported first: it puts the work dir on sys.path

sys.path.insert(0, support.TOOLS)
from h713 import panelrow                                       # noqa: E402
from h713.profiles import PROFILES                              # noqa: E402

# The ten row fields no board profile carries. Both archived boards state the same ten (AP3g 4.2).
COMMON = {"Mapping": 0, "ColorDepth": 8, "OddEven": 0, "MirrorMode": 0, "PanelInvDCLK": 1,
          "PanelInvDE": 0, "PanelInvHSync": 0, "PanelInvVSync": 0, "PanelDECurrent": 47,
          "PanelODDDataCurrent": 7, "PanelEvenDataCurrent": 7}


def ini_for(board_id, ssc=0, **override):
    """A panel_config.ini in the vendor's shape, built from that board's profile numbers."""
    panel = PROFILES[board_id]["panel"]
    keys = dict(COMMON, SpreadSpectrumEnable=ssc, SpreadSpectrumStep=10, SpreadSpectrumSpan=0)
    keys.update({"ProjectID": panel["declared_project_id"], "PanelWidth": panel["width"],
                 "PanelHeight": panel["height"], "PanelDualPort": int(panel["dual_port"]),
                 "PanelHTotal": panel["htotal"], "PanelVTotal": panel["vtotal"],
                 "PanelDCLK": panel["dclk_hz"], "PanelHsync": panel["hsync"],
                 "PanelVsync": panel["vsync"], "PanelHBP": panel["hbp"], "PanelVBP": panel["vbp"],
                 "PanelHsyncPol": panel["hsync_pol"], "PanelVsyncPol": panel["vsync_pol"]})
    keys.update(override)
    text = "[PanelSetting]\n#a vendor comment\n"
    text += "".join("%s = %s\n" % (k, v) for k, v in keys.items() if v is not None)
    text += "[PWMSetting]\npwm_channel = %s\npwm_freq = %s\npwm_polarity = 1\n" % (
        panel["pwm_channel"], panel["pwm_freq"])
    return text.encode("utf-8")


def levels(checks):
    return dict((level, len([c for c in checks if c[0] == level])) for level in ("OK", "WARN", "FAIL"))


class TheTwoArchivedBoards(unittest.TestCase):
    """AP3g section 5, reproduced against what the repository already states about each board."""

    def run_for(self, board_id, **kw):
        text, checks, values = panelrow.profile_from_ini(board_id, ini_for(board_id, **kw), "test")
        return text, checks, values

    def test_the_hy310_row_equals_the_one_already_in_boards(self):
        _text, checks, values = self.run_for("hy310", ssc=1)
        self.assertEqual(panelrow.compare_with_profile(values, PROFILES["hy310"]["panel"]), [])
        self.assertEqual(values["PLL_N_PLUS_1"], 41)       # the "n:41" of the stock boot log
        self.assertEqual(levels(checks), {"OK": 9, "WARN": 2, "FAIL": 0})

    def test_the_archived_hy300_pro_plus_row_equals_what_ap3g_derived(self):
        """cstenger's HY200 QZ713DF_A1 - the image the identifier calls HY300 Pro+ (2025, DDR3).

        Its panel_config.ini is byte-identical to the T08's (sha256 7bffff88...), so this is the
        0x34 row of AP3g section 5: pll 36, 8 OK, 2 WARN (project id already mapped, pwm_channel 5).
        """
        _text, checks, values = self.run_for("hy200_qz713df_a1")
        self.assertEqual(panelrow.compare_with_profile(values, PROFILES["hy200_qz713df_a1"]["panel"]), [])
        self.assertEqual(values["PLL_N_PLUS_1"], 36)       # A10's PLL sweep on board B
        self.assertEqual(levels(checks), {"OK": 8, "WARN": 2, "FAIL": 0})

    def test_a_row_from_another_board_is_reported_as_a_difference(self):
        _text, _checks, values = self.run_for("hy350")
        differences = panelrow.compare_with_profile(values, PROFILES["hy310"]["panel"])
        self.assertIn("htotal: profile 2128, ini 2200", differences)

    def test_a_profile_with_nothing_measured_gets_every_field_answered(self):
        """The HY300 Pro of issue #1: its profile has only the project id, and nothing else."""
        _text, _checks, values = self.run_for("hy310")
        notes = panelrow.compare_with_profile(values, PROFILES["hy300_pro"]["panel"])
        self.assertTrue(all("the profile has nothing" in n for n in notes if "declared" not in n))


class ThePll(unittest.TestCase):
    """AP3g section 3: three independent boards, three hits, and floor - not round."""

    def test_the_three_known_points(self):
        self.assertEqual(panelrow.derive_pll(62000000, 0)[0], 36)
        self.assertEqual(panelrow.derive_pll(143001600, 1)[0], 41)
        self.assertEqual(panelrow.derive_pll(148500000, 1)[0], 43)

    def test_rounding_to_nearest_would_contradict_the_hy310_boot_log(self):
        self.assertEqual(round(143001600 * 7 * 2 / 2 / 24000000), 42)

    def test_without_a_clock_or_a_port_count_nothing_is_derived(self):
        self.assertEqual(panelrow.derive_pll(None, 1)[0], None)
        self.assertEqual(panelrow.derive_pll(62000000, 2)[0], None)


class TheFiveRegisterReads(unittest.TestCase):

    def test_they_are_unknown_and_name_the_register(self):
        ini = panelrow.read_ini(ini_for("hy310"))
        values, traces = panelrow.build_row(ini)
        for key, register in panelrow.FROM_REGISTER:
            self.assertEqual(values[key], panelrow.UNKNOWN)
            self.assertEqual(traces[key], "unknown, read on the device: " + register)

    def test_the_two_plane_words_carry_the_ap3m_names(self):
        registers = dict(panelrow.FROM_REGISTER)
        self.assertIn("0x0528008c", registers["LAYER_X"])
        self.assertIn("0x05280084[31:16]", registers["LAYER_H_MASK"])

    def test_the_generated_file_says_unknown_in_the_value(self):
        text, _checks, _values = panelrow.profile_from_ini("hy310", ini_for("hy310"), "test")
        self.assertIn("PANEL_LAYER_X=unknown", text)
        self.assertIn("# unknown, read on the device: 0x0528008c", text)


class TheChecks(unittest.TestCase):
    """Negative controls: every FAIL has to be produced by a file that really is wrong."""

    def failures(self, **override):
        _t, checks, _v = panelrow.profile_from_ini("hy310", ini_for("hy310", **override), "test")
        return [(c[1], c[2]) for c in checks if c[0] == "FAIL"]

    def test_a_total_that_does_not_cover_the_active_area_fails_c1(self):
        self.assertTrue(any(c[0] == "C1" for c in self.failures(PanelHTotal=1900)))

    def test_a_decremented_total_warns_in_c2(self):
        _t, checks, _v = panelrow.profile_from_ini(
            "hy310", ini_for("hy310", PanelHTotal=2127, PanelMinHTotal=2128, PanelMaxHTotal=2208), "test")
        self.assertTrue(any(c[0] == "WARN" and c[1] == "C2" for c in checks))

    def test_a_colour_depth_the_vendor_refuses_fails_c6(self):
        self.assertTrue(any(c[0] == "C6" for c in self.failures(ColorDepth=7)))

    def test_a_three_bit_current_at_eight_fails_c6(self):
        self.assertTrue(any(c[0] == "C6" for c in self.failures(PanelODDDataCurrent=8)))

    def test_a_missing_clock_fails_c4(self):
        self.assertTrue(any(c[0] == "C4" for c in self.failures(PanelDCLK=None)))

    def test_quad_port_fails_c5(self):
        self.assertTrue(any(c[0] == "C5" for c in self.failures(PanelDualPort=2)))

    def test_an_odd_width_on_two_ports_fails_c5(self):
        self.assertTrue(any(c[0] == "C5" for c in self.failures(PanelWidth=1919)))

    def test_a_clock_that_gives_no_sane_refresh_fails_c4(self):
        self.assertTrue(any(c[0] == "C4" for c in self.failures(PanelDCLK=286003200)))

    def test_a_sound_file_fails_nothing(self):
        self.assertEqual(self.failures(), [])


class TheGeneratedFile(unittest.TestCase):

    def parsed(self, text):
        out = {}
        for line in text.splitlines():
            if line and not line.startswith("#") and "=" in line:
                key, value = line.split("=", 1)
                out[key] = value.strip('"')
        return out

    def test_it_is_shell_key_value_like_board_env(self):
        text, _c, values = panelrow.profile_from_ini("hy310", ini_for("hy310", ssc=1), "test")
        keys = self.parsed(text)
        self.assertEqual(keys["BOARD_ID"], "hy310")
        self.assertEqual(keys["PANEL_PROJECT_ID"], "0x30")
        self.assertEqual(keys["PANEL_HTOTAL"], str(values["HTOTAL"]))
        self.assertEqual(keys["PANEL_CHECKS"], "9 OK, 2 WARN, 0 FAIL")

    def test_every_field_carries_the_ini_line_it_came_from(self):
        text, _c, _v = panelrow.profile_from_ini("hy310", ini_for("hy310"), "vendor:/x/panel_config.ini")
        self.assertIn("# Source: vendor:/x/panel_config.ini", text)
        self.assertIn("[PanelSetting] PanelHTotal = 2128 (line", text)

    def test_a_missing_key_is_named_in_the_file_and_not_defaulted_quietly(self):
        blank = b"[PanelSetting]\nProjectID = 48\nPanelDCLK = 143001600\nPanelDualPort = 1\n"
        text, _c, values = panelrow.profile_from_ini("newboard", blank, "test")
        self.assertIn("MISSING KEY PanelHTotal", text)
        self.assertEqual(values["HTOTAL"], 0)


class TheDocumentation(unittest.TestCase):
    """Item 4: the two places a foreign owner is sent to have to name the command."""

    def read(self, *parts):
        path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), *parts)
        if not os.path.exists(path):
            self.skipTest("not next to this checkout: %s" % path)
        with open(path, "rb") as handle:
            return handle.read().decode("utf-8")

    def test_the_tool_doc_explains_the_flag(self):
        text = self.read("docs", "tools", "h713-extract.md")
        self.assertIn("--profile", text)
        self.assertIn("panel.env", text)
        self.assertIn("PANEL_PIPELINE_COM", text)

    def test_the_boards_readme_gives_the_three_commands(self):
        text = self.read("boards", "README.md")
        self.assertIn("--profile", text)
        self.assertIn("out/boards/<your-board-id>/panel.env", text)


if __name__ == "__main__":
    unittest.main()
