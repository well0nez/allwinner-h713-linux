#!/usr/bin/env python3
"""Tests against the real vendor files.

The vendor files are read at run time and never copied. If the tvconfig
directory (or the legacy tree) is missing, the test in question is skipped
cleanly instead of failing.

Run:  python3 -m unittest discover -s tests -v
  or  python3 tests/test_h713_pq.py
"""

from __future__ import annotations

import contextlib
import io
import math
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]            # userspace/h713-pq
sys.path.insert(0, str(ROOT))

from h713_pq import cli, model, output, sources, tse  # noqa: E402

sys.path.insert(0, str(ROOT / "tests"))
import make_fixture  # noqa: E402
import make_tse_fixture  # noqa: E402

PROJECT = ROOT.parents[1]                              # /opt/Projekte/h713
PQD = PROJECT / "legacy/userspace/hy310-pqd"


def _data() -> sources.DataSet | None:
    try:
        return sources.load(None)
    except FileNotFoundError:
        return None


DATA = _data()
needs_data = unittest.skipIf(DATA is None, "tvconfig directory not found")


# ---------------------------------------------------------------------------
# Sources
# ---------------------------------------------------------------------------

@needs_data
class TestSources(unittest.TestCase):
    def test_tvpq_db_row_counts(self):
        # Night plan section 3 G: Picture_Mode 25, White_Balance_Mode 20,
        # Gamma_Point 33.
        self.assertEqual(len(DATA.db_picture_mode), 25)
        self.assertEqual(len(DATA.db_white_balance), 20)
        self.assertEqual(len(DATA.db_gamma_points), 33)

    def test_gamma_points_are_empty(self):
        # The shipped table is zero throughout -- unusable as a curve.
        # Stock computes the points at run time (BACKGROUND.md 6.2).
        self.assertEqual(set(DATA.db_gamma_points), {0})

    def test_white_balance_neutral(self):
        for z in DATA.db_white_balance:
            self.assertEqual((z.rgain, z.ggain, z.bgain), (512, 512, 512))
            self.assertEqual((z.roffset, z.goffset, z.boffset), (0, 0, 0))

    def test_factory_curve_hdmi(self):
        k = DATA.factory_curves["HDMI"]
        self.assertEqual(k["saturation"], [0, 48, 96, 145, 192])
        self.assertEqual(k["brightness"], [0, 256, 512, 775, 1023])
        self.assertEqual(k["contrast"], [1196, 1794, 2392, 3010, 3588])
        self.assertEqual(k["hue"], [0, 256, 512, 775, 1023])
        self.assertEqual(k["sharpness"], [0, 64, 128, 193, 255])

    def test_gamma_levels_from_xml(self):
        # pqcontrol_config_setting.xml <transform name="gamma">
        self.assertEqual(DATA.gamma_levels, [1.8, 2.0, 2.1, 2.2, 2.4])

    def test_presets_hdmi1(self):
        vivid = DATA.presets["HDMI1"]["vivid"].values
        self.assertEqual(vivid["saturation"], 60)
        self.assertEqual(vivid["contrast"], 55)
        self.assertEqual(vivid["gamma"], 3)
        cinema = DATA.presets["HDMI1"]["cinema"].values
        self.assertEqual(cinema["saturation"], 45)

    def test_portmap(self):
        self.assertIn((1, 1, "HDMI1"), DATA.portmap)
        self.assertEqual(len(DATA.portmap), 6)

    def test_colortemp_neutral(self):
        for name in model.COLOR_TEMP_NAMES:
            ct = DATA.color_temps["HDMI"][name]
            self.assertEqual((ct.rgain, ct.ggain, ct.bgain), (512, 512, 512))


# ---------------------------------------------------------------------------
# Model: saturation
#
# Correction 07.09.2026 (doku/nachtlog/G-korrektur-saettigung.md). The expected
# values of this section have been changed, not the computation: the
# measurement on the device (doku/nachtlog/K5-board-verifikation.md section f)
# has refuted the old assumption "gain 0x4C belongs to user value 50".
# Proven instead is: SetSaturation(N) -> 0x05001238[15:0] = N and
# 0x05140508[23:16] = floor(N * 1.28), measured at N = 0/50/59/60/100.
# ---------------------------------------------------------------------------

@needs_data
class TestSaturation(unittest.TestCase):
    def _chain(self, input_name: str, mode: str):
        return model.chain(DATA, input_name, mode)

    def test_measured_table_k5_section_f(self):
        """The five points measured on the device, without any intermediate step.

        This used to hold the table from doku/77 section 4 (cinema 0x44,
        standard 0x4C, vivid 0x5C). It came from the curve computation, not
        from a measurement of the RPC, and is refuted: 0x4C belongs to
        SetSaturation 60, not to 50.
        """
        measured = {0: 0x00, 50: 0x40, 59: 0x4B, 60: 0x4C, 100: 0x80}
        for argument, gain in measured.items():
            self.assertEqual(model.chroma_gain(argument), gain,
                             f"SetSaturation {argument}")

    def test_floor_not_round(self):
        """59 and 60 are the two points that decide the kind of rounding.

        59 * 1.28 = 75.52. Rounded half up that would be 76 (0x4C); measured
        was 75 (0x4B). So round down.
        """
        self.assertEqual(model.chroma_gain(59), 0x4B)
        self.assertEqual(model.chroma_gain(60), 0x4C)
        self.assertNotEqual(model.chroma_gain(59), round(59 * 1.28))

    def test_firmware_default_equals_argument_60(self):
        # The firmware starts with 0x144C0000 without prep_after_boot.sh
        # calling SetSaturation (K5 acceptance f).
        gain = (model.REG_CHROMA_GAIN_STOCK & model.CHROMA_GAIN_MASK) >> \
            model.CHROMA_GAIN_SHIFT
        self.assertEqual(gain, 0x4C)
        self.assertEqual(model.chroma_gain(model.FIRMWARE_DEFAULT_ARGUMENT),
                         gain)

    def test_picture_modes_deliver_rpc_arguments(self):
        """The result of h713-pq is the RPC argument now.

        Expected is the user value of the vendor presets (cinema 45,
        standard 50, vivid 60) -- this used to be register values.
        """
        self.assertEqual(self._chain("HDMI1", "cinema").saturation_argument, 45)
        self.assertEqual(self._chain("HDMI1", "standard").saturation_argument, 50)
        self.assertEqual(self._chain("HDMI1", "vivid").saturation_argument, 60)

    def test_control_values_gain_and_register_word(self):
        """The gain stays as a control output, but as floor(argument*1.28).

        Before: standard -> 0x4C / 0x144C0000, vivid -> 0x5C / 0x145C0000.
        Now: standard -> 0x40 / 0x14400000, vivid -> 0x4C / 0x144C0000 --
        vivid thus hits the firmware default exactly.
        """
        standard = self._chain("HDMI1", "standard")
        self.assertEqual(standard.gain, 0x40)
        self.assertEqual(standard.gain_register, 0x14400000)
        vivid = self._chain("HDMI1", "vivid")
        self.assertEqual(vivid.gain, 0x4C)
        self.assertEqual(vivid.gain_register, model.REG_CHROMA_GAIN_STOCK)
        self.assertEqual(self._chain("HDMI1", "cinema").gain, 0x39)
        # A pure bit function, untouched by the correction.
        self.assertEqual(model.chroma_gain_register(0x5C), 0x145C0000)

    def test_gain_from_the_argument_only_not_from_the_curve(self):
        # For every argument 0..100 the firmware formula holds, no matter
        # whether the input has a factory curve at all.
        for a in range(0, 101):
            self.assertEqual(model.chroma_gain(a), (a * 128) // 100)
        self.assertEqual(model.chroma_gain(-5), 0)
        self.assertEqual(model.chroma_gain(500), 128)

    def test_rpc_argument_is_passed_through_and_clamped(self):
        for u in (0, 45, 50, 60, 100):
            self.assertEqual(model.rpc_argument(u), u)
        self.assertEqual(model.rpc_argument(-1), 0)
        self.assertEqual(model.rpc_argument(101), 100)

    def test_open_step_changes_nothing_today(self):
        """Proves the reason why the unmeasured step may stay open.

        If the factory curve did sit between user value and RPC argument
        (normalized onto 0..100), the result would be identical for every
        saturation value occurring in the vendor data. Deviation at all:
        exactly at user value 75, and there by 1.
        """
        curve = DATA.factory_curves["HDMI"]["saturation"]
        deviating = {u: model.curve_as_argument(curve, u)
                     for u in range(0, 101)
                     if model.curve_as_argument(curve, u) != u}
        self.assertEqual(deviating, {75: 76})
        occurring = {pm.values["saturation"]
                     for modes in DATA.presets.values() for pm in modes.values()}
        self.assertEqual(occurring, {45, 50, 60})
        self.assertNotIn(75, occurring)

    def test_curve_sample_points(self):
        # The factory curve itself is unchanged -- it stays in the output as a
        # vendor datum, only no longer as a computation path.
        curve = DATA.factory_curves["HDMI"]["saturation"]
        for u, y in ((0, 0), (25, 48), (50, 96), (75, 145), (100, 192)):
            self.assertAlmostEqual(model.curve_value(curve, u), y)
        self.assertAlmostEqual(model.curve_value(curve, 45), 86.4)
        self.assertAlmostEqual(model.curve_value(curve, 60), 115.6)

    def test_curve_is_no_rpc_scale(self):
        # The argument of the PQ RPCs demonstrably runs up to 100 (SetContrast
        # 100 -> 0x64). The curve values run far beyond that -- therefore the
        # curve cannot be the step user value -> argument.
        k = DATA.factory_curves["HDMI"]
        self.assertGreater(k["saturation"][-1], model.USER_VALUE_MAX)
        self.assertGreater(k["contrast"][-1], model.USER_VALUE_MAX)


# ---------------------------------------------------------------------------
# Model: chain and data state
# ---------------------------------------------------------------------------

@needs_data
class TestChain(unittest.TestCase):
    def test_db_crosscheck_agrees(self):
        k = model.chain(DATA, "HDMI1", "vivid")
        self.assertIn("agrees value for value", k.db_crosscheck)

    def test_gamma_index_to_exponent(self):
        k = model.chain(DATA, "HDMI1", "standard")
        self.assertEqual(k.gamma_index, 3)
        self.assertEqual(k.gamma_exponent, 2.2)

    def test_all_curve_controls_now_have_a_register(self):
        """State 11.09.2026 -- all five controls are measured on the device.

        This used to say: brightness/contrast/hue/sharpness -> target "-",
        state "open (K5)"; then "RE proven, unmeasured" for hue and sharpness.
        Both are out of date. doku/85 section A.1 resolved the UIMapping table
        statically, the board acceptance K5 c/e measured contrast and
        brightness, and on 11.09.2026 hue and sharpness were read back over
        /dev/mem -- 1:1 at 0/25/50/75/100 (doku/81 section 7.3, plan 113
        section A.6).
        """
        k = model.chain(DATA, "HDMI1", "vivid")
        by_control = {z.control: z for z in k.target_values}
        expected = {
            "brightness": (0x05001234, "[15:0]", "measured, effective"),
            "contrast": (0x05001234, "[31:16]", "measured, effective"),
            "saturation": (0x05001238, "[15:0]", "measured, effective"),
            "hue": (0x05001238, "[31:16]", "measured, effective"),
            "sharpness": (0x05001228, "[23:8]", "measured (register)"),
        }
        for control, (reg, field, status) in expected.items():
            z = by_control[control]
            self.assertIn(f"0x{reg:08X}", z.target, control)
            self.assertIn(field, z.target, control)
            self.assertEqual(z.status, status, control)
            # The result is the RPC argument, not a register value.
            self.assertEqual(z.argument, z.user_value, control)

    def test_brightness_is_not_called_ineffective(self):
        """doku/61 section D: the column "ohne Wirkung" at brightness was
        refuted on 07.09. (nachtlog/I0, dark material: std 12.6 -> 22.7) and
        confirmed by eye on 11.09. No output of this program may claim the
        opposite any more, and the state it does print is the one the table
        can stand behind: the register was read back on the device."""
        target = model.PQ_TARGETS["brightness"]
        self.assertTrue(target.argument_1to1)
        self.assertEqual(target.status, "measured, effective")
        for text in (target.status, target.effect, target.evidence):
            self.assertNotIn("no effect", text.lower())
            self.assertNotIn("ohne wirkung", text.lower())
        k = model.chain(DATA, "HDMI1", "standard")
        z = [t for t in k.target_values if t.control == "brightness"][0]
        self.assertNotIn("unmeasured", z.target)

    def test_no_field_unmeasured_any_more(self):
        """The other side: since 11.09. none of the five controls carries the
        note "(value unmeasured)" in the target column any more, because every
        one of them was found on the device with its argument in the
        register."""
        k = model.chain(DATA, "HDMI1", "vivid")
        for z in k.target_values:
            if z.control in model.CURVE_CONTROLS:
                self.assertNotIn("unmeasured", z.target, z.control)
                self.assertTrue(model.PQ_TARGETS[z.control].argument_1to1,
                                z.control)

    def test_index_controls_without_register_write(self):
        # doku/85 A.1/A.5: SetTNR and SetBlackExtension have an item ID but
        # address 0 -- they demonstrably write no register.
        k = model.chain(DATA, "HDMI1", "vivid")
        by_control = {z.control: z for z in k.target_values}
        for control in ("tnr", "blackextension"):
            self.assertEqual(by_control[control].target, "no register")
        # DCI and SNR on the other hand are proven on the device (K5 acceptance b).
        self.assertIn("0x0500123C", by_control["dci"].target)
        self.assertIn("0x05001248", by_control["snr"].target)

    def test_custom_comes_from_its_own_xml_node(self):
        """Changed 22.09.2026, AP3d 3.

        Before: "custom" was looked up in tvpq.db::Picture_Mode by name. That
        is the factory-reset source. The live one is a node of its own per
        source in pqcontrol_custom_setting.xml -- parseFileTagBySourceType
        @0x2EC14 plus TvFileTagToHdmi@0x30214 for the ported sources. The
        database stays as the fallback for a source that has no node yet.
        """
        self.assertEqual(model.custom_node("HDMI1"), "custom_hdmi1")
        self.assertEqual(model.custom_node("VGA3"), "custom_vga3")
        self.assertEqual(model.custom_node("CVBS"), "custom_cvbs")
        self.assertEqual(model.custom_node("VIDEODEC"), "custom_videodec")
        pm = model.preset(DATA, "HDMI1", "custom")
        self.assertIn("custom_hdmi1", pm.origin)
        self.assertIn(sources.FILE_CUSTOM_XML, pm.origin)
        # ATV has no node in this file, so the database still answers.
        self.assertIn("tvpq.db", model.preset(DATA, "ATV", "custom").origin)

    def test_vga_has_no_factory_curve_but_an_rpc_argument(self):
        """Before: without a factory curve no gain (assertIsNone).

        That was a consequence of the old computation path. Since the
        correction the RPC argument no longer hangs on the curve but on the
        user value -- so an input without a curve group delivers a valid
        argument too. That VGA1..3 have no group in pq_factory_extern.ini
        stays true and is still reported.
        """
        self.assertIsNone(model.INPUT_GROUP["VGA1"])
        self.assertNotIn("VGA1", DATA.factory_curves)
        k = model.chain(DATA, "VGA1", "standard")
        self.assertEqual(k.saturation_argument, 50)
        self.assertEqual(k.gain, 0x40)
        sat = [z for z in k.target_values if z.control == "saturation"][0]
        self.assertIsNone(sat.curve_value)
        self.assertIn("no curve group", sat.note)

    def test_tvin_is_tvsourcetype(self):
        """Changed 22.09.2026, AP3d 2 (the question of AP3d 8a).

        Before: the mapping was called unresolvable and the test asserted the
        ambiguity. AP3d resolves it -- UpdateDataManager@0x2D99C builds
        map<SourceType,string> {0 mode_hdmi, 1 mode_cvbs, 2 mode_atv,
        3 mode_dtv, 4 mode_videodec, 5 mode_vga} and the device's own XML has
        current_source_type tvin="4" beside current_mode mode_videodec.
        """
        rows = {tvin: (source, sections, gap)
                for tvin, source, _names, sections, gap in model.tvin_mapping(DATA)}
        self.assertEqual(set(rows), {0, 1, 2, 3, 4})
        self.assertEqual([rows[t][0] for t in range(5)],
                         ["HDMI", "CVBS", "ATV", "DTV", "VIDEODEC"])
        self.assertEqual(rows[0][1], ["HDMI1", "HDMI2", "HDMI3"])
        self.assertEqual(rows[4][1], ["VIDEODEC"])
        for tvin in range(5):
            self.assertEqual(rows[tvin][2], [], f"tvin {tvin} disagrees")
        self.assertEqual(model.source_of("HDMI2"), "HDMI")
        self.assertIsNone(model.source_of("NOSUCH"))

    def test_the_two_picture_mode_numberings_stay_apart(self):
        # AP3d 3/8e: libtvpq's own enum is not the firmware's argument.
        self.assertEqual(model.firmware_mode("standard"), (1, True))
        self.assertEqual(model.PQ_PICTURE_MODE["standard"], 0)
        self.assertEqual(model.PQ_PICTURE_MODE["custom"], 21)
        self.assertNotIn("custom", model.FIRMWARE_MODE)


# ---------------------------------------------------------------------------
# Model: the machine readable record (plan 113 section A.3)
# ---------------------------------------------------------------------------

@needs_data
class TestRecord(unittest.TestCase):
    """The record h713-tv reads at start.

    It is an interface between two programs, so this does not only check that
    something comes out but what exactly: field names, number of fields and
    the numbers h713-tv hangs on.
    """

    def _record(self, mode="standard"):
        return model.record(DATA, "HDMI1", mode)

    def test_mandatory_fields(self):
        s = self._record()
        for field in ("version", "eingang", "preset", "modus", "regler",
                      "gamma_exponent", "presets"):
            self.assertIn(field, s, field)
        self.assertEqual(s["version"], model.RECORD_VERSION)
        self.assertEqual(s["eingang"], "HDMI1")
        self.assertEqual(s["preset"], "standard")

    def test_nine_controls_with_the_names_of_the_vendor_file(self):
        # Exactly these nine names h713-tv looks for (preset_pq_key[] in main.c).
        self.assertEqual(set(self._record()["regler"]),
                         set(model.PRESET_CONTROLS))
        self.assertEqual(len(model.PRESET_CONTROLS), 9)

    def test_values_agree_with_pq_picturemode_ini(self):
        # vivid, the line [HDMI1] of the INI, column by column.
        r = self._record("vivid")["regler"]
        self.assertEqual(r, {"brightness": 50, "contrast": 55, "saturation": 60,
                             "hue": 50, "sharpness": 60, "tnr": 2, "snr": 1,
                             "dci": 3, "blackextension": 1})

    def test_firmware_mode_numbers(self):
        """The numbers of the MIPS firmware, not those of the database.

        doku/nachtlog/S14 section 1.2 -- tvpq.db counts differently (there
        standard is 0 and vivid 2), and whoever confuses the two sends the
        firmware the wrong mode.
        """
        expected = {"standard": 1, "cinema": 7, "vivid": 0, "game": 3,
                    "computer": 6, "hdr": 12}
        for name, number in expected.items():
            with self.subTest(name):
                s = self._record(name)
                self.assertEqual(s["modus"], number)
                self.assertTrue(s["modus_eigen"])

    def test_energy_saving_and_custom_without_an_own_number(self):
        # S14 section 4: for both there is no firmware mode. They run under
        # standard and say so.
        for name in ("energy_saving", "custom"):
            with self.subTest(name):
                s = self._record(name)
                self.assertEqual(s["modus"], model.FIRMWARE_MODE_FALLBACK)
                self.assertFalse(s["modus_eigen"])

    def test_energy_saving_differs_only_in_the_backlight(self):
        # That is why its nine controls are those of standard -- not a fault
        # but the vendor row.
        self.assertEqual(self._record("energy_saving")["regler"],
                         self._record("standard")["regler"])
        self.assertEqual(self._record("energy_saving")["weitere"]["backlight"], 80)
        self.assertEqual(self._record("standard")["weitere"]["backlight"], 100)

    def test_all_picture_modes_of_the_input_come_along(self):
        # A.5: energy_saving and custom are offered as soon as the data are
        # there -- without a second call of h713-pq.
        names = [p["name"] for p in self._record()["presets"]]
        self.assertEqual(names, ["standard", "cinema", "vivid", "game",
                                 "computer", "hdr", "energy_saving", "custom"])
        for p in self._record()["presets"]:
            self.assertEqual(len(p["regler"]), 9, p["name"])

    def test_flat_fields_and_list_are_the_same(self):
        # The record names the requested preset twice: flat and in the list.
        # They come out of the same function and must not drift apart.
        s = self._record("cinema")
        from_list = [p for p in s["presets"] if p["name"] == "cinema"][0]
        self.assertEqual(s["regler"], from_list["regler"])
        self.assertEqual(s["modus"], from_list["modus"])
        self.assertEqual(s["gamma_exponent"], from_list["gamma_exponent"])

    def test_record_is_json_and_one_line(self):
        import io as _io
        import json as _json
        from contextlib import redirect_stdout

        buffer = _io.StringIO()
        with redirect_stdout(buffer):
            output.print_record(self._record())
        text = buffer.getvalue()
        self.assertEqual(text.count("\n"), 1)
        self.assertEqual(_json.loads(text)["preset"], "standard")

    def test_only_the_needed_files(self):
        """The fast load path delivers the same record as the full one.

        h713-tv reads with sources.FILES_FOR_RECORD at start, because
        pq_factory_extern.ini alone costs 85 ms of picture. If that ever made
        a difference to the record, it would be a fault.
        """
        lean = sources.load(str(DATA.directory), sources.FILES_FOR_RECORD)
        a = model.record(lean, "HDMI1", "vivid")
        b = model.record(DATA, "HDMI1", "vivid")
        for field in ("modus", "regler", "weitere", "gamma_exponent"):
            self.assertEqual(a[field], b[field], field)
        self.assertEqual([p["name"] for p in a["presets"]],
                         [p["name"] for p in b["presets"]])

    def test_a_broken_file_is_not_fatal(self):
        """An unreadable tvpq.db costs the cross-check, not the presets.

        Plan 113 section A.5: h713-tv calls this program at start. An abort
        while reading would be one picture less.
        """
        import shutil
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp)
            for name in sources.FILES_FOR_RECORD:
                source = DATA.directory / name
                if source.is_file():
                    shutil.copy2(source, target / name)
            (target / sources.FILE_DB).write_bytes(b"this is not a database")
            data = sources.load(str(target))
            self.assertTrue(any("unreadable" in x for x in data.missing_files))
            s = model.record(data, "HDMI1", "standard")
            self.assertEqual(s["regler"]["contrast"], 50)
            # without the database "custom" drops out -- the rest stays
            self.assertNotIn("custom", [p["name"] for p in s["presets"]])


# ---------------------------------------------------------------------------
# Model: gamma
# ---------------------------------------------------------------------------

class TestGamma(unittest.TestCase):
    def test_sanity_from_re_guide_identity(self):
        # CALCULATEGAMMA_RE_GUIDE.md section 11:
        #   identity -> lut[0] = 0, lut[512] ~ 2048, lut[1023] = 4095
        lut = model.interpolate(model.points_identity())
        self.assertEqual(lut[0], 0)
        self.assertEqual(lut[1023], 4095)
        self.assertAlmostEqual(lut[512], 2048, delta=8)

    def test_sanity_from_re_guide_gamma22(self):
        #   gamma 2.2 -> lut[0] = 0, middle ~ 891, lut[1023] = 4095
        result = model.gamma_compute(2.2)
        self.assertEqual(result.lut[0], 0)
        self.assertEqual(result.lut[1023], 4095)
        # The guide value 891 is the sample point at t = 0.5 (point 16).
        self.assertEqual(result.points[16], 891)
        # LUT index 512 sits at t = 512/1023 = 0.5005 -> minimally higher.
        self.assertAlmostEqual(result.lut[512], 891, delta=5)
        self.assertLess(result.lut[512], 1500)   # darker than identity

    def test_gamma_factor_order(self):
        # Larger exponent -> darker midtones.
        a = model.gamma_compute(1.8).lut[512]
        b = model.gamma_compute(2.4).lut[512]
        self.assertGreater(a, b)

    def test_pack_format(self):
        lut = [i & model.LUT_MAX for i in range(model.LUT_ENTRIES)]
        packed = model.pack(lut)
        self.assertEqual(len(packed), 512)
        self.assertEqual(packed[0], (1 << 12) | 0)
        self.assertEqual(packed[5], (11 << 12) | 10)

    def test_lut_file_sizes(self):
        result = model.gamma_compute(2.2)
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "lut.bin"
            self.assertEqual(output.write_lut(p, result, "r"), 2048)
            self.assertEqual(output.write_lut(p, result, "all"), 3 * 2048)
            raw = p.read_bytes()
            self.assertEqual(raw[:2048], raw[2048:4096])   # banks equal (WB neutral)

    def test_no_value_outside_12_bit(self):
        for exp in (1.0, 1.8, 2.2, 2.4, 3.0):
            for v in model.gamma_compute(exp).lut:
                self.assertGreaterEqual(v, 0)
                self.assertLessEqual(v, model.LUT_MAX)


# ---------------------------------------------------------------------------
# Model: the gamma curve out of the vendor's own TSE (Q2 item 1)
# ---------------------------------------------------------------------------
# The TSE file these tests read is built by make_tse_fixture.py and contains no
# vendor byte. The expected LUT is not taken from the program under test: it is
# written out here from AP3t 2.2 -- with the stored gamma factor out of
# dword_4A50 (180, 200, 210, 220, 240, i.e. the XML level times 100),
#     g = (factor / 100.0) / 2.2
#     out[c][x] = (unsigned)(pow(in[c][x] / end[c], g) * end[c])
# and the C cast truncating towards zero.

class TestTseGamma(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.dir = tempfile.TemporaryDirectory()
        cls.path = Path(cls.dir.name) / "ProjectID_0x0030.TSE"
        cls.banks = make_tse_fixture.build(cls.path, 0x0030)
        cls.states = tse.gamma_states(cls.path)
        # cli.main reads the tvconfig directory before it dispatches, even for
        # `gamma`, which touches none of it -- see REPORT.txt.
        cls.tvconfig = str(make_fixture.build(Path(cls.dir.name) / "tvconfig"))

    @classmethod
    def tearDownClass(cls):
        cls.dir.cleanup()

    @staticmethod
    def expected(samples, level):
        """AP3t 2.2, written out here and not imported from the model."""
        end = float(samples[1023])
        factor = level * 100.0                    # the dword_4A50 entry
        g = (factor / 100.0) / 2.2
        return [int(math.pow(float(v) / end, g) * end) for v in samples]

    def test_container_round_trip(self):
        # Three states, in the vendor's own file order warm, cool, normal, and
        # the slot each maps to (AP3r 1.1 and 1.2).
        self.assertEqual([s.name for s in self.states],
                         ["warm", "cool", "normal"])
        self.assertEqual([s.slots for s in self.states], [(2,), (1,), (0,)])
        for i, s in enumerate(self.states):
            for c in range(3):
                self.assertEqual(list(s.samples[c]), self.banks[i][c])

    def test_formula_is_ap3t(self):
        for level in (1.8, 2.0, 2.1, 2.2, 2.4):
            for s in self.states:
                got = model.gamma_from_tse(s, level)
                for c in range(3):
                    self.assertEqual(got.luts[c],
                                     self.expected(s.samples[c], level),
                                     f"state {s.index} channel {c} level {level}")

    def test_endpoint_survives_every_level(self):
        # x = 1023 maps to itself, so the white balance the board baked into
        # the LUT cannot be disturbed by the gamma control (AP3t 2.2).
        for level in (1.8, 2.0, 2.1, 2.2, 2.4):
            for s in self.states:
                self.assertEqual(model.gamma_from_tse(s, level).endpoints,
                                 s.endpoints)

    def test_neutral_level_gives_the_raw_curve_back(self):
        # Level 2.2 is exponent 1.0. The only deviation allowed is the vendor's
        # own truncation artefact, one count low (AP3t 2.4).
        for s in self.states:
            got = model.gamma_from_tse(s, model.GAMMA_LEVEL_NEUTRAL)
            for c in range(3):
                delta = [got.luts[c][x] - s.samples[c][x] for x in range(1024)]
                self.assertGreaterEqual(min(delta), -1)
                self.assertLessEqual(max(delta), 0)

    def test_exponent_is_the_level_over_2_2(self):
        self.assertEqual(model.GAMMA_FACTOR_TABLE, (180, 200, 210, 220, 240))
        self.assertAlmostEqual(model.tse_exponent(1.8), 0.818182, places=6)
        self.assertAlmostEqual(model.tse_exponent(2.2), 1.0, places=9)

    def test_banks_differ_and_the_file_is_three_of_them(self):
        got = model.gamma_from_tse(self.states[0], 2.2)
        self.assertEqual(got.packed[0][0],
                         (got.luts[0][1] << 12) | got.luts[0][0])
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "lut.bin"
            self.assertEqual(output.write_lut(p, got, "r"), 2048)
            self.assertEqual(output.write_lut(p, got, "all"), 3 * 2048)
            raw = p.read_bytes()
            # Unlike the synthetic curve the three banks are NOT equal -- that
            # difference is the board's white balance.
            self.assertNotEqual(raw[:2048], raw[2048:4096])
            self.assertNotEqual(raw[2048:4096], raw[4096:])
            self.assertEqual(raw[:2048], got.bank_bytes("r"))
            self.assertEqual(raw[4096:], got.bank_bytes("b"))

    def test_state_selection_and_its_negative_controls(self):
        self.assertEqual(tse.state_for(self.states, "standard").index, 2)
        self.assertEqual(tse.state_for(self.states, "0").index, 2)
        self.assertEqual(tse.state_for(self.states, "warm").index, 0)
        with self.assertRaises(KeyError):
            tse.state_for(self.states, "lukewarm")
        with self.assertRaises(KeyError):
            tse.state_for(self.states, "computer")     # slot 8, not in the file
        with self.assertRaises(ValueError):
            model.tse_bank([0] * 1023, 2.2)            # wrong sample count

    def test_default_stays_synthetic(self):
        # The behaviour change is off unless it is asked for: the same call as
        # before this package writes the same bytes.
        with tempfile.TemporaryDirectory() as d:
            a, b = Path(d) / "a.bin", Path(d) / "b.bin"
            output.write_lut(a, model.gamma_compute(2.2), "all")
            with contextlib.redirect_stdout(io.StringIO()):
                code = cli.main(["--data", self.tvconfig, "gamma", "2.2",
                                 "--channel", "all", "--lut", str(b)])
            self.assertEqual(code, 0)
            self.assertEqual(a.read_bytes(), b.read_bytes())
            self.assertEqual(len(b.read_bytes()), 3 * 2048)

    def test_cli_from_tse(self):
        with tempfile.TemporaryDirectory() as d:
            out = Path(d) / "tse.bin"
            with contextlib.redirect_stdout(io.StringIO()):
                code = cli.main(["--data", self.tvconfig, "gamma",
                                 "--from-tse", "cool", "--tse", str(self.path),
                                 "--channel", "all", "--lut", str(out)])
            self.assertEqual(code, 0)
            want = model.gamma_from_tse(tse.state_for(self.states, "cool"),
                                        model.GAMMA_LEVEL_NEUTRAL)
            self.assertEqual(out.read_bytes(), want.bank_bytes("all"))
        with contextlib.redirect_stderr(io.StringIO()):
            code = cli.main(["--data", self.tvconfig, "gamma",
                             "--from-tse", "cool",
                             "--tse", str(self.path.parent / "no.TSE")])
        self.assertEqual(code, 2)


# ---------------------------------------------------------------------------
# The OSD-to-register step out of pq_custom.TSE (Q2 item 2)
# ---------------------------------------------------------------------------

class TestTseCurves(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.dir = tempfile.TemporaryDirectory()
        cls.path = Path(cls.dir.name) / "pq_custom.TSE"
        make_tse_fixture.build_custom(cls.path)
        cls.features = {f.name: f for f in tse.picture_features(cls.path)}
        cls.tvconfig = str(make_fixture.build(Path(cls.dir.name) / "tvconfig"))

    @classmethod
    def tearDownClass(cls):
        cls.dir.cleanup()

    def test_round_trip(self):
        self.assertEqual(sorted(self.features),
                         ["mp_brightness", "mp_saturation_1", "mp_tint_1"])
        f = self.features["mp_saturation_1"]
        self.assertEqual(f.id, 0x00EE0000)          # 0x00EE0000 + index, AP3f 1.5
        points, registers = f.sets[0]
        self.assertEqual(points, ((0.0, 50.0, 0.0, 64.0), (50.0, 75.0, 64.0, 96.0),
                                  (75.0, 100.0, 96.0, 128.0)))
        self.assertEqual(registers, ((0x05140508, 32, 0x00FF0000),))

    def test_the_device_measurement_of_07_09(self):
        # AP3f 1.5a: the three segments all have slope 1.28, so the TSE is
        # where h713-pq's measured floor(argument * 1.28) comes from. 60 ->
        # 64 + 10 * 32/25 = 76.8 -> 76 = 0x4C, which is what the board showed.
        points = self.features["mp_saturation_1"].sets[0][0]
        self.assertAlmostEqual(model.feature_value(points, 60), 76.8, places=6)
        self.assertEqual(model.feature_field(0x00FF0000, 76.8) >> 16, 0x4C)
        for u in (0, 50, 59, 60, 100):
            self.assertEqual(model.feature_field(0x00FF0000,
                                                 model.feature_value(points, u))
                             >> 16, model.chroma_gain(u))

    def test_curve_edges_and_outside(self):
        points = self.features["mp_tint_1"].sets[0][0]
        self.assertEqual(model.feature_value(points, 0), 256.0)
        self.assertEqual(model.feature_value(points, 50), 0.0)
        self.assertEqual(model.feature_value(points, 100), -256.0)
        self.assertEqual(model.feature_value(points, 500), -256.0)   # clamped
        self.assertEqual(model.feature_value(points, -5), 256.0)

    def test_negative_value_is_twos_complement_in_its_field(self):
        # mp_brightness is 10 bits at [17:8]: ui 0 -> 923, which the field
        # holds as -101 (AP3f 1.5). The shift comes from the mask.
        self.assertEqual(model.feature_field(0x0003FF00, -101) >> 8, 923)
        self.assertEqual(model.feature_field(0x000003FF, -51.2), 1024 - 51)

    def test_ini_path_is_the_four_segment_roundf(self):
        # AP3 3.3a. The HY310's contrast points; the 75 % point of the ini
        # (3010) is NOT on the TSE's line (2990) -- AP3f 1.5d.
        points = [1196, 1794, 2392, 3010, 3588]
        self.assertEqual(model.nlc_value(points, 0), 1196)
        self.assertEqual(model.nlc_value(points, 50), 2392)
        self.assertEqual(model.nlc_value(points, 75), 3010)
        self.assertEqual(model.nlc_value(points, 100), 3588)
        self.assertEqual(model.nlc_value(points, 60), 2639)
        self.assertNotEqual(model.nlc_value(points, 75), 2990)

    def test_cli(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = cli.main(["--data", self.tvconfig, "curves", "60",
                             "--source", "tse", "--tse", str(self.path)])
        self.assertEqual(code, 0)
        self.assertIn("0x05140508 [23:16] = 0x4C", out.getvalue())
        self.assertIn("mp_saturation_1", out.getvalue())
        # Default: the ini only, no TSE read at all.
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.assertEqual(cli.main(["--data", self.tvconfig, "curves"]), 0)
        self.assertNotIn("mp_saturation_1", out.getvalue())
        with contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(cli.main(["--data", self.tvconfig, "curves",
                                       "--source", "tse", "--tse",
                                       str(self.path.parent / "no.TSE")]), 2)


# Command line: --data and --channel are the names, --daten and --kanal the
# aliases kept for v0.8-beta (cli.py, the lines marked GERMAN ALIAS).

class TestOptionNames(unittest.TestCase):
    def _help(self, argv) -> str:
        out = io.StringIO()
        with contextlib.redirect_stdout(out), self.assertRaises(SystemExit):
            cli._parser().parse_args(argv + ["--help"])
        return out.getvalue()

    def test_data_directory(self):
        for flag in ("--data", "--daten"):
            args = cli._parser().parse_args([flag, "/etc/h713/tvconfig", "list"])
            self.assertEqual(args.data_dir, "/etc/h713/tvconfig", flag)

    def test_channel(self):
        for sub in (["show", "HDMI1", "standard"], ["gamma", "2.2"]):
            self.assertEqual(cli._parser().parse_args(sub).channel, "r")
            for flag in ("--channel", "--kanal"):
                self.assertEqual(cli._parser().parse_args(sub + [flag, "all"]).channel,
                                 "all", flag)

    def test_german_aliases_are_not_documented(self):
        for argv, shown in (([], "--data"), (["show"], "--channel"),
                            (["gamma"], "--channel")):
            text = self._help(argv)
            self.assertIn(shown, text)
            self.assertNotIn("--daten", text)
            self.assertNotIn("--kanal", text)


# ---------------------------------------------------------------------------
# Bit comparison against the legacy calculator
# ---------------------------------------------------------------------------

def _legacy_buildable() -> bool:
    return ((PQD / "src/pqgamma.cpp").is_file()
            and (PQD / "include/pqgamma.h").is_file()
            and subprocess.run(["which", "g++"], capture_output=True).returncode == 0)


@unittest.skipUnless(_legacy_buildable(), "legacy tree or g++ not present")
class TestAgainstLegacy(unittest.TestCase):
    def test_bit_identical(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            bin_ = d / "legacy_ref"
            build = subprocess.run(
                ["g++", "-O2", "-std=c++17", "-I", str(PQD / "include"),
                 str(PQD / "src/pqgamma.cpp"),
                 str(ROOT / "tests/legacy_ref.cpp"), "-o", str(bin_)],
                capture_output=True, text=True)
            self.assertEqual(build.returncode, 0, build.stderr)
            for exp in ("1.8", "2.0", "2.1", "2.2", "2.4", "1.0"):
                ref = d / f"legacy-{exp}.bin"
                run = subprocess.run([str(bin_), exp, str(ref)],
                                     capture_output=True, text=True)
                self.assertEqual(run.returncode, 0, run.stderr)
                own = d / f"own-{exp}.bin"
                result = model.gamma_compute(float(exp))
                output.write_lut(own, result, "r")
                self.assertEqual(ref.read_bytes(), own.read_bytes(),
                                 f"exponent {exp} not bit-identical")


if __name__ == "__main__":
    unittest.main(verbosity=2)
