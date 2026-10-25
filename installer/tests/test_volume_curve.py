#!/usr/bin/env python3
"""check_volume_curve() (h713.vendorfiles): whether h713-tv can take the curve of an audio_config.ini.

The files here are made up in the vendor's shape (a line "volume_curve[NN]=a,b,...," ends at index NN; the curve is in
[Volume]); no vendor file is carried. h713-tv's own reader (main.c audio_curve_load) is tested by tests/test_curve.c of
userspace/h713-tv against the same rules.
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from h713.vendorfiles import check_volume_curve  # noqa: E402


def ini(values, before=""):
    lines = ["[AudioMode]", before, "[Volume]", "speaker_max = 0", "volume_curve[00]=%d," % values[0]]
    for last in range(10, 101, 10):
        lines.append("volume_curve[%d]=%s," % (last, ",".join(str(v) for v in values[last - 9:last + 1])))
    return ("\n".join(lines + ["", "[Peq]", "peq1_freq = 1,10"]) + "\n").encode()


RISING = [-512] + [n - 98 for n in range(1, 101)]


class VolumeCurve(unittest.TestCase):
    def test_a_rising_curve_is_taken(self):
        self.assertEqual(check_volume_curve(ini(RISING)), [])

    def test_a_curve_line_outside_volume_counts_for_nothing(self):
        self.assertEqual(check_volume_curve(ini(RISING, "volume_curve[50]=1,1,1,1,1,1,1,1,1,1,")), [])

    def test_a_value_below_the_one_before_is_named(self):
        values = list(RISING)
        values[60] = values[59] - 1
        self.assertIn("value 60", check_volume_curve(ini(values))[0])

    def test_a_value_above_120_is_named(self):
        values = list(RISING)
        values[100] = 121
        self.assertIn("value 100", check_volume_curve(ini(values))[0])

    def test_a_short_file_names_the_first_value_missing(self):
        self.assertEqual(check_volume_curve(b"[Volume]\nvolume_curve[00]=-512,\nvolume_curve[10]=-200,-191,\n"),
                         ["[Volume] volume_curve value 1 missing"])


if __name__ == "__main__":
    unittest.main()
