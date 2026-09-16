#!/usr/bin/env python3
"""Build a synthetic tvconfig directory for the h713-pq tests.

No vendor file is read. Every value here is reconstructed from what the
repository itself already states in the open:

  * the nine preset values per picture mode   -> userspace/h713-tv/main.c,
    struct preset presets[] (standard/cinema/vivid/game/computer/hdr)
  * the factory curves, the gamma levels, the row counts of tvpq.db, the
    portmap entry and the neutral white balance
                                              -> userspace/h713-pq/tests/
                                                 test_h713_pq.py and README.md
  * the INI dialect and the column order      -> h713_pq/sources.py

Usage:  python3 make_fixture.py <directory>
"""

import sqlite3
import sys
from pathlib import Path

# brightness contrast saturation hue sharpness tnr snr colortemperature
# gamma dci blackextenstion backlight dynamic_backlight
MODES = {
    "standard":      (50, 50, 50, 50, 50, 2, 1, 0, 3, 2, 1, 100, 0),
    "cinema":        (50, 45, 45, 50, 40, 2, 1, 0, 3, 0, 0, 100, 0),
    "vivid":         (50, 55, 60, 50, 60, 2, 1, 0, 3, 3, 1, 100, 0),
    "game":          (50, 50, 50, 50, 50, 1, 0, 0, 3, 0, 0, 100, 0),
    "computer":      (50, 50, 50, 50,  0, 0, 0, 0, 3, 0, 0, 100, 0),
    "hdr":           (50, 50, 50, 50, 50, 1, 1, 0, 3, 0, 0, 100, 0),
    "energy_saving": (50, 50, 50, 50, 50, 2, 1, 0, 3, 2, 1,  80, 0),
    "custom":        (50, 50, 50, 50, 50, 2, 1, 0, 3, 2, 1, 100, 0),
}

FULL = ["standard", "cinema", "vivid", "game", "computer", "hdr", "energy_saving"]
FOUR = ["standard", "cinema", "vivid", "game"]
FIVE = ["standard", "cinema", "vivid", "game", "computer"]

SECTIONS = [
    ("HDMI1", FULL), ("HDMI2", FULL), ("HDMI3", FULL),
    ("VGA1", FULL), ("VGA2", FULL), ("VGA3", FULL),
    ("ATV", FOUR), ("CVBS", FOUR),
    ("DTV", FIVE), ("VIDEODEC", FIVE),
]

# 25 Picture_Mode rows over five tvin, arranged so that the ambiguity the tests
# describe comes out: tvin 0 -> the HDMI/VGA sections, tvin 1 and 4 -> ATV/CVBS,
# tvin 2 and 3 -> DTV/VIDEODEC.
DB_ROWS = [
    (0, ["standard", "cinema", "vivid", "game", "computer", "hdr", "custom"]),
    (1, FOUR),
    (2, FIVE),
    (3, FIVE),
    (4, FOUR),
]

CURVES = {
    1: ("BRIGHTNESS", [0, 256, 512, 775, 1023]),
    2: ("CONTRAST", [1196, 1794, 2392, 3010, 3588]),
    3: ("SATURATION", [0, 48, 96, 145, 192]),
    4: ("HUE", [0, 256, 512, 775, 1023]),
    5: ("SHARPNESS", [0, 64, 128, 193, 255]),
}

CURVE_GROUPS = ("HDMI", "CVBS", "ATV", "DTV", "VIDEODEC")
PORTMAP = [(1, 1, "HDMI1"), (2, 2, "HDMI2"), (3, 3, "HDMI3"),
           (4, 4, "CVBS"), (5, 5, "VIDEODEC"), (6, 6, "ATV")]


def write_picturemode(p):
    out = ["#brightness,contrast,saturation,hue,sharpness,tnr,snr,"
           "colortemperature,gamma,dci,blackextenstion,backlight,"
           "dynamic_backlight",
           "#gamma :0-1.8,1-2.0,2-2.1,3-2.2,4-2.4",
           "#colortemperature :0-standard,1-cool,2-warm",
           "[CONFIG]",
           "picture_mode = standard,cinema,vivid,game,computer,hdr,energy_saving",
           "special_mode = custom",
           ""]
    for name, modes in SECTIONS:
        out.append("[%s]" % name)
        for m in modes:
            out.append("%s = %s,\\" % (m, ",".join(str(v) for v in MODES[m])))
        out.append("")
    p.write_text("\n".join(out), encoding="utf-8")


def write_factory(p):
    out = ["[PQ_ENABLE]", "pq_enable = 1,\\", "dci_enable = 1,\\", ""]
    for group in CURVE_GROUPS:
        out.append("[PICTURE_CURVE_%s]" % group)
        for idx in sorted(CURVES):
            label, values = CURVES[idx]
            out.append("#%s" % label)
            out.append("PICTURE_CURVE_SETTINGS[%d] = %s,\\"
                       % (idx, ",".join(str(v) for v in values)))
        out.append("")
    p.write_text("\n".join(out), encoding="utf-8")


def write_colortemp(p):
    out = []
    for group in CURVE_GROUPS:
        out.append("[COLOR_TEMP_%s]" % group)
        for name in ("STANDARD", "COOL", "WARM", "USER"):
            out.append("%s = 0,0,0,512,512,512,\\" % name)
        out.append("")
    p.write_text("\n".join(out), encoding="utf-8")


def write_config_xml(p):
    p.write_text(
        '<?xml version="1.0" encoding="utf-8"?>\n'
        '<pqcontrol>\n'
        '  <default brightness="50" contrast="50" saturation="50"/>\n'
        '  <transform>\n'
        '    <item name="gamma" level0="1.8" level1="2.0" level2="2.1"'
        ' level3="2.2" level4="2.4"/>\n'
        '  </transform>\n'
        '</pqcontrol>\n', encoding="utf-8")


def write_custom_xml(p):
    p.write_text(
        '<?xml version="1.0" encoding="utf-8"?>\n'
        '<pqcontrol>\n'
        '  <current_source_type tvin="0"/>\n'
        '  <current_mode picture_mode="standard"/>\n'
        '  <current_data brightness="50" contrast="50" saturation="50"/>\n'
        '</pqcontrol>\n', encoding="utf-8")


def write_portmap(p):
    lines = ["# port source name"]
    lines += ["%d %d %s" % row for row in PORTMAP]
    p.write_text("\n".join(lines) + "\n", encoding="utf-8")


DB_COLUMNS = ("brightness", "contrast", "saturation", "hue", "sharpness",
              "tnr", "snr", "backlight", "colortemperature", "gamma", "dci",
              "blackextenstion", "dynamic_backlight")
# position of each db column inside the INI tuple above
INI_ORDER = ("brightness", "contrast", "saturation", "hue", "sharpness",
             "tnr", "snr", "colortemperature", "gamma", "dci",
             "blackextenstion", "backlight", "dynamic_backlight")


def write_db(p):
    if p.exists():
        p.unlink()
    con = sqlite3.connect(str(p))
    try:
        cols = ", ".join("%s INTEGER" % c for c in DB_COLUMNS)
        con.execute("CREATE TABLE Picture_Mode (tvin INTEGER, mode INTEGER, "
                    "name TEXT, %s)" % cols)
        con.execute("CREATE TABLE White_Balance_Mode (tvin INTEGER, mode INTEGER,"
                    " RGain INTEGER, GGain INTEGER, BGain INTEGER,"
                    " ROffset INTEGER, GOffset INTEGER, BOffset INTEGER)")
        con.execute("CREATE TABLE Gamma_Point (id INTEGER, value INTEGER)")
        for tvin, modes in DB_ROWS:
            for mode_no, name in enumerate(modes):
                values = dict(zip(INI_ORDER, MODES[name]))
                row = [tvin, mode_no, name] + [values[c] for c in DB_COLUMNS]
                con.execute("INSERT INTO Picture_Mode VALUES (%s)"
                            % ",".join("?" * len(row)), row)
        for tvin in range(5):
            for mode_no in range(4):
                con.execute("INSERT INTO White_Balance_Mode VALUES "
                            "(?,?,512,512,512,0,0,0)", (tvin, mode_no))
        for i in range(33):
            con.execute("INSERT INTO Gamma_Point VALUES (?,0)", (i,))
        con.commit()
    finally:
        con.close()


def build(directory):
    d = Path(directory)
    d.mkdir(parents=True, exist_ok=True)
    write_picturemode(d / "pq_picturemode.ini")
    write_factory(d / "pq_factory_extern.ini")
    write_colortemp(d / "pq_colortemp.ini")
    write_config_xml(d / "pqcontrol_config_setting.xml")
    write_custom_xml(d / "pqcontrol_custom_setting.xml")
    write_portmap(d / "portmap.cfg")
    write_db(d / "tvpq.db")
    return d


if __name__ == "__main__":
    print(build(sys.argv[1]))
