# SPDX-License-Identifier: GPL-2.0
"""A board's panel row, derived from its own vendor panel_config.ini.

Source: AP3g section 2 (23 fields one to one out of the ini), section 3 (pll_n_plus_1), section 4
(the nine checks C1..C9), section 5 (the archived boards through the generator), AP3m part B and
the device run of 22.09.2026 (layer_x). Two fields are derived from the ini rather than copied out
of it. The four remaining members of `struct h713_panel_cfg` stand in no ini anywhere - they are
register reads off a running stock bootloader - so they come out as "unknown" with the register to
read named. A row with an unknown or a MISSING KEY in it describes the panel but is not a
measurement.

Nothing here writes to a device and nothing here runs on one: this is host-side description.
Standard library, Python 3.9, Windows-safe.
"""

from __future__ import annotations

from collections import OrderedDict
from typing import Dict, List, Optional, Tuple

XTAL_HZ = 24000000                # the PLL reference of every H713 board seen so far
LVDS_BITS = 7                     # 7:1 serialiser, both in 6 bit and in 8 bit mode
LVDS_LINK_LIMIT_BPS = 1000000000  # one LVDS link; above this a panel needs two
REFRESH_MIN_HZ, REFRESH_MAX_HZ = 50.0, 75.0
LAYER_X_BIAS = 77                 # __update_panel_setting's SUBS R3, R3, #0x4D at 0xFAA8 (AP3m B)
OUR_PWM_CHANNEL = 2               # h713_disp_backlight_set() is pinned to PWM2 on PB4
KNOWN_PROJECT_IDS = {0x30: "the HY310 row", 0x34: "the board B row"}
UNKNOWN = "unknown"
#: The one further per-board fact besides the panel row (AP3t 1.5; its REVIEW confirms it is per
#: board). It is not in panel_config.ini, so the writer can only name it - see the Q7 follow-ups.
PIPELINE_NOTE = [
    "", "# The only per-board pipeline difference besides this row (AP3t section 1.5): the",
    "# compression tag in column 12 of this board's projecttable.TSE row - COM2 on the HY310,",
    "# COM1 on the HY300 Pro, which decides whether its HDMI path runs uncompressed. Not in",
    "# panel_config.ini; boot/mips/projecttable.TSE and boot/mips/database.TSE hold it and the",
    "# reader for them is not written yet.",
    "PANEL_PIPELINE_COM=" + UNKNOWN,
]

#: (env key, ini key) - AP3g section 2: 23 members of struct h713_panel_cfg, one to one.
FROM_INI = (
    ("MAPPING", "Mapping"), ("COLOR_DEPTH", "ColorDepth"), ("ODD_EVEN", "OddEven"),
    ("DUAL_PORT", "PanelDualPort"), ("MIRROR_MODE", "MirrorMode"),
    ("INV_DE", "PanelInvDE"), ("INV_HSYNC", "PanelInvHSync"),
    ("INV_VSYNC", "PanelInvVSync"), ("INV_DCLK", "PanelInvDCLK"),
    ("DE_CURRENT", "PanelDECurrent"), ("ODD_CURRENT", "PanelODDDataCurrent"),
    ("EVEN_CURRENT", "PanelEvenDataCurrent"), ("SSC_EN", "SpreadSpectrumEnable"),
    ("HTOTAL", "PanelHTotal"), ("VTOTAL", "PanelVTotal"), ("HSYNC", "PanelHsync"),
    ("VSYNC", "PanelVsync"), ("HBP", "PanelHBP"), ("VBP", "PanelVBP"),
    ("WIDTH", "PanelWidth"), ("HEIGHT", "PanelHeight"),
    ("HSYNC_POL", "PanelHsyncPol"), ("VSYNC_POL", "PanelVsyncPol"),
)
#: (env key, register to read) - the four the ini never states and nothing derives (AP3g section 2).
FROM_REGISTER = (
    ("LVDS_BITSEL", "0x05800000[4:3], LVDS port/bit selector"),
    ("SSC_MASK", "0x058c0018, which bits of the spread-spectrum word this board owns"),
    ("SSC_REG", "0x058c0018, the spread-spectrum word (Step and Span do not give it, AP3g 4.3)"),
    ("LAYER_H_MASK", "0x05280084[31:16], plane 1 geometry +0x04 (AP3m part B)"),
)
#: env key -> the key of a board profile's "panel" dict that must hold the same number.
PROFILE_FIELDS = {"PROJECT_ID": "declared_project_id", "WIDTH": "width", "HEIGHT": "height",
                  "DUAL_PORT": "dual_port", "HTOTAL": "htotal", "VTOTAL": "vtotal",
                  "DCLK_HZ": "dclk_hz", "HSYNC": "hsync", "VSYNC": "vsync", "HBP": "hbp",
                  "VBP": "vbp", "HSYNC_POL": "hsync_pol", "VSYNC_POL": "vsync_pol",
                  "PWM_CHANNEL": "pwm_channel", "PWM_FREQ": "pwm_freq"}
#: C6, AP3g 4 / AP3d 7.1: (env key, allowed set or (0..top), the register bits that force it).
C6_BOUNDS = (("COLOR_DEPTH", (6, 8, 10), "lvds_set_bitwidth@0x387C takes only these"),
             ("MAPPING", (0, 1, 2, 3), "0x05800000[7:6]"), ("MIRROR_MODE", (0, 1, 2, 3), "four modes"),
             ("ODD_EVEN", (0, 1), "0x05800000 bit 14"), ("SSC_EN", (0, 1), "one bit"),
             ("INV_DE", (0, 1), "one bit"), ("INV_HSYNC", (0, 1), "one bit"),
             ("INV_VSYNC", (0, 1), "one bit"), ("INV_DCLK", (0, 1), "one bit"),
             ("DE_CURRENT", tuple(range(64)), "0x058C0020/24[29:24], 6 bits"),
             ("ODD_CURRENT", (0, 1, 2, 3, 4, 5, 6, 7), "0x058C0020[2:0], 3 bits"),
             ("EVEN_CURRENT", (0, 1, 2, 3, 4, 5, 6, 7), "0x058C0024[2:0], 3 bits"))


def read_ini(data: bytes) -> "OrderedDict[str, Tuple[str, str, int]]":
    """key (lower case) -> (value, section, line). Cut at '#' and ';' as the vendor readers cut."""
    out: "OrderedDict[str, Tuple[str, str, int]]" = OrderedDict()
    section = ""
    for lineno, raw in enumerate(data.decode("utf-8", "replace").splitlines(), 1):
        line = raw.split("#", 1)[0].split(";", 1)[0].strip()
        if line.startswith("[") and line.endswith("]"):
            section = line[1:-1].strip()
        elif "=" in line:
            key, value = line.split("=", 1)
            out.setdefault(key.strip().lower(), (value.strip(), section, lineno))
    return out


def number(ini, key: str) -> Optional[int]:
    hit = ini.get(key.lower())
    try:
        return None if hit is None else int(hit[0], 0)
    except ValueError:
        return None


def derive_pll(dclk: Optional[int], dual_port: Optional[int]) -> Tuple[Optional[int], str]:
    """pll_n_plus_1 = floor(DCLK * 7 * 2 / links / 24 MHz) - AP3g section 3.

    The display PLL runs at 24 MHz * (N+1) and is divided by K = 14 down to one LVDS link's pixel
    clock (A10's PLL sweep on board B established K); a dual-port panel carries half the pixels per
    link. Reproduces all three values anybody has measured: 62.0000 MHz single -> 36 (board B bench
    sweep), 143.0016 MHz dual -> 41 (the HY310's stock boot log), 148.5 MHz dual -> 43 (the vendor
    table's default, which is why board B ran 18.9 % fast on it). Rounding to nearest would give the
    HY310 42 and contradict its boot log, so this floors.
    """
    if dclk is None or dual_port not in (0, 1):
        return None, "PanelDCLK or PanelDualPort missing or not 0/1"
    links = 2 if dual_port == 1 else 1
    exact = float(dclk) * LVDS_BITS * 2.0 / links / XTAL_HZ
    return int(exact), "floor(%d Hz * %d * 2 / %d link(s) / %d Hz) = floor(%.3f)" % (
        dclk, LVDS_BITS, links, XTAL_HZ, exact)


def derive_layer_x(hsync: Optional[int], hbp: Optional[int]) -> Tuple[Optional[int], str]:
    """layer_x = max(hsync + hbp - 77, 0) - AP3m part B, confirmed at the U-Boot prompt 22.09.2026.

    0x0528008c is a LogoRegData entry, so the vendor file carries a number (115 in the HY310's file,
    123 in board B's) rather than a formula; the stock bootloader's __update_panel_setting overwrites
    it from the raster it just programmed, and that is where the 77 comes from (SUBS R3, R3, #0x4D at
    0xFAA8). `md 0x0528008c 1` at the U-Boot prompt gave 0x37 = 55 on the HY310, which is 44 + 88 - 77
    (dev20 22.09.2026 Q7 F3, umbau/reviews/Q7.md open point c); board B's 20 + 40 - 77 clamps to 0.
    So this is derived, not read: AP3m's "live 115" was the file's number, not a bootloader's leaving.
    """
    if hsync is None or hbp is None:
        return None, "PanelHsync or PanelHBP missing"
    return max(hsync + hbp - LAYER_X_BIAS, 0), "max(%d + %d - %d, 0)" % (hsync, hbp, LAYER_X_BIAS)


def build_row(ini) -> Tuple["OrderedDict[str, object]", "OrderedDict[str, str]"]:
    """(values, traces). A missing key is written as 0 and named; it is never defaulted quietly."""
    values: "OrderedDict[str, object]" = OrderedDict()
    traces: "OrderedDict[str, str]" = OrderedDict()
    pid = number(ini, "ProjectID")
    values["PROJECT_ID"] = pid
    traces["PROJECT_ID"] = "ProjectID = %s" % ("MISSING" if pid is None else pid)
    for env_key, ini_key in FROM_INI:
        hit, value = ini.get(ini_key.lower()), number(ini, ini_key)
        values[env_key] = 0 if value is None else value
        traces[env_key] = ("MISSING KEY %s - wrote 0; this row is not a measurement" % ini_key
                           if value is None else
                           "[%s] %s = %s (line %d)" % (hit[1], ini_key, hit[0], hit[2]))
    dclk = number(ini, "PanelDCLK")
    values["DCLK_HZ"] = 0 if dclk is None else dclk
    traces["DCLK_HZ"] = "PanelDCLK = %s; not a row field, pll_n_plus_1 is derived from it" % dclk
    pll, note = derive_pll(dclk, number(ini, "PanelDualPort"))
    values["PLL_N_PLUS_1"] = 0 if pll is None else pll
    traces["PLL_N_PLUS_1"] = ("NOT DERIVED - " + note) if pll is None else ("derived: " + note)
    layer_x, note = derive_layer_x(number(ini, "PanelHsync"), number(ini, "PanelHBP"))
    values["LAYER_X"] = 0 if layer_x is None else layer_x
    traces["LAYER_X"] = ("NOT DERIVED - " + note) if layer_x is None else (
        "derived: " + note + " -> 0x0528008c, plane 1 geometry +0x0C (AP3m part B; the HY310 read "
        "back 0x37 = 55 at the U-Boot prompt, dev20 22.09.2026)")
    for env_key, register in FROM_REGISTER:
        values[env_key] = UNKNOWN
        traces[env_key] = "unknown, read on the device: " + register
    for ini_key in ("pwm_channel", "pwm_freq", "pwm_polarity"):
        values[ini_key.upper()] = number(ini, ini_key)
        traces[ini_key.upper()] = "[PWMSetting] %s; not a row field, see check C8" % ini_key
    return values, traces


def run_checks(ini, v) -> List[Tuple[str, str, str]]:
    """AP3g section 4, C1..C9: (level, id, text). A FAIL means: do not build from this row."""
    out: List[Tuple[str, str, str]] = []

    def say(level, ident, text):
        out.append((level, ident, text))

    htotal, vtotal, dclk, port = v["HTOTAL"], v["VTOTAL"], v["DCLK_HZ"], v["DUAL_PORT"]
    for tag, front, total in (("h", htotal - v["WIDTH"] - v["HBP"] - v["HSYNC"], htotal),
                              ("v", vtotal - v["HEIGHT"] - v["VBP"] - v["VSYNC"], vtotal)):
        say("OK" if front > 0 else "FAIL", "C1", "%stotal %d, front porch %d" % (tag, total, front))
    say("OK", "C2", "raw ini totals %dx%d; 0x0525c000/0x0524c010 take %d/%d, 0x05880020 the raw pair"
        % (htotal, vtotal, htotal - 1, vtotal - 1))
    say("OK", "C2", "layer_x %d = max(hsync %d + hbp %d - %d, 0) -> 0x0528008c; the HY310 reads back "
        "0x37 = 55 there (dev20 22.09.2026), its vendor file record holds 115"
        % (v["LAYER_X"], v["HSYNC"], v["HBP"], LAYER_X_BIAS))
    for key, total, tag in (("HTotal", htotal, "h"), ("VTotal", vtotal, "v")):
        lo, hi = number(ini, "PanelMin" + key), number(ini, "PanelMax" + key)
        if lo is not None and hi is not None and not lo <= total <= hi:
            say("WARN", "C2", "%stotal %d outside the file's own PanelMin/Max%s %d..%d - the mark "
                "of a value decremented somewhere" % (tag, total, key, lo, hi))
    hp, vp = v["HSYNC_POL"], v["VSYNC_POL"]
    if hp in (0, 1) and vp in (0, 1):
        say("WARN" if hp != vp else "OK", "C3", "polarities h%d v%d -> bit 31 of 0x0588002c/0x05880030"
            "%s" % (hp, vp, "; both boards read so far state 1/1 or 0/0" if hp != vp else ""))
    else:
        say("FAIL", "C3", "PanelHsyncPol %s / PanelVsyncPol %s are not 0 or 1" % (hp, vp))
    if not dclk:
        say("FAIL", "C4", "PanelDCLK missing; pll_n_plus_1 cannot be derived")
    else:
        refresh = float(dclk) / (htotal * vtotal) if htotal and vtotal else 0.0
        say("OK" if REFRESH_MIN_HZ <= refresh <= REFRESH_MAX_HZ else "FAIL", "C4",
            "PanelDCLK %d Hz over %dx%d = %.2f Hz refresh" % (dclk, htotal, vtotal, refresh))
        lo, hi = number(ini, "PanelMinDCLK"), number(ini, "PanelMaxDCLK")
        if lo is not None and hi is not None and not lo <= dclk <= hi:
            say("WARN", "C4", "PanelDCLK %d outside the file's own %d..%d" % (dclk, lo, hi))
        if v["PLL_N_PLUS_1"]:
            back = XTAL_HZ * v["PLL_N_PLUS_1"] * (2 if port == 1 else 1) / (LVDS_BITS * 2.0)
            say("OK", "C4", "pll_n_plus_1 %d gives %.0f Hz, %.2f %% off the requested clock"
                % (v["PLL_N_PLUS_1"], back, 100.0 * (back - dclk) / dclk))
    if port not in (0, 1):
        say("FAIL", "C5", "PanelDualPort %s is neither 0 (single) nor 1 (dual); quad is not modelled" % port)
    elif dclk:
        bits = dclk * LVDS_BITS // (2 if port else 1)
        say("OK" if bits <= LVDS_LINK_LIMIT_BPS else "FAIL", "C5", "%d link(s), %.0f of %.0f Mbit/s "
            "per lane" % (2 if port else 1, bits / 1e6, LVDS_LINK_LIMIT_BPS / 1e6))
        if port == 1 and v["WIDTH"] % 2:
            say("FAIL", "C5", "width %d is odd and cannot be split over two ports" % v["WIDTH"])
    bad = ["%s %s not allowed (%s)" % (key.lower(), v[key], why)
           for key, allowed, why in C6_BOUNDS if v[key] not in allowed]
    for text in bad:
        say("FAIL", "C6", text)
    if not bad:
        say("OK", "C6", "every field fits its register bits (the bounds setLvdsConfig@0x1DB38 enforces)")
    pid = v["PROJECT_ID"]
    if pid is None:
        say("WARN", "C7", "no ProjectID - h713_disp_panels[] has no key for this row")
    elif pid in KNOWN_PROJECT_IDS:
        say("WARN", "C7", "ProjectID %d (0x%02x) already selects %s, and an id does not fix the "
            "raster across boards (the HY350 declares 0x30 with 2200x1125) - this board needs its own "
            "row" % (pid, pid, KNOWN_PROJECT_IDS[pid]))
    else:
        say("OK", "C7", "ProjectID %d (0x%02x) is new to h713_disp_panels[]" % (pid, pid))
    channel, freq = v["PWM_CHANNEL"], v["PWM_FREQ"]
    if channel is None:
        say("WARN", "C8", "no [PWMSetting] pwm_channel in this file")
    elif channel != OUR_PWM_CHANNEL:
        say("WARN", "C8", "pwm_channel %s at %s Hz: our dimmer is pinned to PWM%d on PB4 and the row "
            "has no PWM field; on a HY300 Pro class board the vendor's own pwm node is disabled and PB5 "
            "is GPIO only, so that channel dims nothing there either" % (channel, freq, OUR_PWM_CHANNEL))
    else:
        say("OK", "C8", "pwm_channel %d at %s Hz, the PWM2 on PB4 our dimmer drives" % (channel, freq))
    if v["SSC_EN"] and v["SSC_MASK"] == UNKNOWN:
        say("WARN", "C9", "SpreadSpectrumEnable 1, waveform word unknown: 0x058c0018 keeps what the "
            "vendor table has; Step %s per mille and Span %s do not give it (AP3g 4.3)"
            % (number(ini, "SpreadSpectrumStep"), number(ini, "SpreadSpectrumSpan")))
    return out


def compare_with_profile(values, panel: Dict[str, object]) -> List[str]:
    """The generated row against a board profile's "panel" dict; empty list = equal, field for field.

    This is the proof of AP3g section 5: over a board's own image the generator has to reproduce
    what the profile already records. A profile field that is None (nothing measured yet) is not a
    difference - it is reported as newly answered.
    """
    out = []
    for env_key, profile_key in sorted(PROFILE_FIELDS.items()):
        want, got = panel.get(profile_key), values.get(env_key)
        want = int(want) if isinstance(want, bool) else want
        if want is None:
            out.append("%s: the profile has nothing, the ini says %s" % (profile_key, got))
        elif want != got:
            out.append("%s: profile %r, ini %r" % (profile_key, want, got))
    return out


def emit_env(board_id: str, values, traces, checks, origin: str) -> str:
    """The panel row in the boards/ profile format: shell KEY=value, one fact per line, sourced."""
    lines = ["# Panel row of %s, written by h713-extract --profile." % board_id,
             "# Source: %s" % origin,
             "# 23 values come out of that file one to one, two are derived from it",
             "# (PANEL_PLL_N_PLUS_1 from PanelDCLK and PanelDualPort, PANEL_LAYER_X from PanelHsync",
             "# and PanelHBP), four are register reads no ini carries and say 'unknown' with the",
             "# register to read. A row with an unknown or a MISSING KEY in it describes the",
             "# panel but is not a measurement: do not commit it as one.",
             "BOARD_ID=%s" % board_id, ""]
    for key, value in values.items():
        text = "" if value is None else str(value)
        if key == "PROJECT_ID" and isinstance(value, int):
            text = "0x%02x" % value
        lines += ["# " + traces[key], "PANEL_%s=%s" % (key, text)]
    lines += PIPELINE_NOTE
    counted = dict((level, len([c for c in checks if c[0] == level])) for level in ("OK", "WARN", "FAIL"))
    lines += ["", "# Checks (AP3g section 4). A FAIL means the row is not self-consistent."]
    lines += ["# %-4s %s %s" % (level, ident, text) for level, ident, text in checks]
    lines.append('PANEL_CHECKS="%d OK, %d WARN, %d FAIL"' % (counted["OK"], counted["WARN"], counted["FAIL"]))
    return "\n".join(lines) + "\n"


def profile_from_ini(board_id: str, data: bytes, origin: str):
    """(text, checks, values) - everything `h713-extract --profile` needs, in one call."""
    ini = read_ini(data)
    values, traces = build_row(ini)
    checks = run_checks(ini, values)
    return emit_env(board_id, values, traces, checks, origin), checks, values
