"""sources.py -- reading the stock PQ data (SQLite, INI, XML).

This module only reads. It computes nothing and prints nothing. Every data
structure here is a plain image of the vendor files from ``/vendor/etc/tvconfig``
(in the tree: ``re/vendor/HY310/extracted/vendor_a/etc/tvconfig``).

The vendor files are read at run time and never copied.
"""

from __future__ import annotations

import os
import sqlite3
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path

# --------------------------------------------------------------------------
# File names inside the tvconfig directory
# --------------------------------------------------------------------------
FILE_DB = "tvpq.db"
FILE_PICTUREMODE = "pq_picturemode.ini"
FILE_FACTORY = "pq_factory_extern.ini"
FILE_COLORTEMP = "pq_colortemp.ini"
FILE_OVERSCAN = "pq_overscan_config.ini"
FILE_CONFIG_XML = "pqcontrol_config_setting.xml"
FILE_CUSTOM_XML = "pqcontrol_custom_setting.xml"
FILE_PORTMAP = "portmap.cfg"

# Search order for the data directory when none was given.
SEARCH_PATHS = (
    # H713_TVCONFIG is the name since the rename; HY310_TVCONFIG is still
    # accepted so that existing instructions and test runs keep working.
    os.environ.get("H713_TVCONFIG", "") or os.environ.get("HY310_TVCONFIG", ""),
    "/etc/h713/tvconfig",
    # In the work tree: userspace/h713-pq/h713_pq/sources.py -> root = ../../..
    str(Path(__file__).resolve().parents[3]
        / "re/vendor/HY310/extracted/vendor_a/etc/tvconfig"),
)


def find_data_dir(given: str | None = None) -> Path:
    """Return the tvconfig directory or raise FileNotFoundError."""
    candidates = [given] if given else list(SEARCH_PATHS)
    for c in candidates:
        if not c:
            continue
        p = Path(c)
        if (p / FILE_PICTUREMODE).is_file() or (p / FILE_DB).is_file():
            return p
    raise FileNotFoundError(
        "tvconfig directory not found. Expected one of: "
        + ", ".join(x for x in candidates if x)
    )


# --------------------------------------------------------------------------
# INI: our own parser
# --------------------------------------------------------------------------
# The vendor INIs are not in configparser format:
#   * values end on ",\" (the continuation character of the vendor tool),
#   * keys carry indices such as ``PICTURE_CURVE_SETTINGS[3]`` or
#     ``ResolutionType[0/1]``,
#   * inside one section a key may appear twice
#     (configparser would stop with DuplicateOptionError).
# Hence a deliberately very simple reader of our own.

def read_ini(path: Path) -> dict[str, list[tuple[str, str]]]:
    """INI -> {section: [(key, raw value), ...]} in file order."""
    sections: dict[str, list[tuple[str, str]]] = {}
    current: list[tuple[str, str]] = []
    sections["__before_first_section__"] = current
    with path.open("r", encoding="utf-8", errors="replace") as f:
        for line in f:
            z = line.strip()
            if not z or z.startswith("#") or z.startswith(";"):
                continue
            if z.startswith("[") and z.endswith("]"):
                name = z[1:-1].strip()
                current = sections.setdefault(name, [])
                continue
            if "=" not in z:
                continue
            key, value = z.split("=", 1)
            current.append((key.strip(), value.strip()))
    return sections


def number_list(raw: str) -> list[int]:
    """``"0,48,96,145,192,\\"`` -> ``[0, 48, 96, 145, 192]``"""
    w = raw.rstrip("\\").strip()
    parts = [t.strip() for t in w.split(",")]
    return [int(t) for t in parts if t != ""]


# --------------------------------------------------------------------------
# Records
# --------------------------------------------------------------------------

# Column order of the values in pq_picturemode.ini, taken from the comment
# header of the file itself:
#   brightness,contrast,saturation,hue,sharpness,tnr,snr,colortemperature,
#   gamma,dci,blackextenstion,backlight,dynamic_backlight
INI_COLUMNS = (
    "brightness", "contrast", "saturation", "hue", "sharpness",
    "tnr", "snr", "colortemperature", "gamma", "dci", "blackextension",
    "backlight", "dynamic_backlight",
)


@dataclass(frozen=True)
class PictureMode:
    """One picture-mode preset for exactly one input."""
    input_name: str       # section name of the INI, or a name derived from it
    name: str             # standard / cinema / vivid / game / computer / hdr / ...
    values: dict[str, int]
    origin: str           # which file delivered the record


@dataclass(frozen=True)
class PictureModeRow:
    """One row of tvpq.db::Picture_Mode."""
    tvin: int
    mode: int
    name: str
    values: dict[str, int]


@dataclass(frozen=True)
class WhiteBalanceRow:
    """One row of tvpq.db::White_Balance_Mode."""
    tvin: int
    mode: int
    rgain: int
    ggain: int
    bgain: int
    roffset: int
    goffset: int
    boffset: int


@dataclass(frozen=True)
class ColorTemp:
    """One entry of pq_colortemp.ini."""
    group: str            # HDMI / CVBS / ATV / DTV / VIDEODEC
    name: str             # STANDARD / COOL / WARM / USER
    roffset: int
    goffset: int
    boffset: int
    rgain: int
    ggain: int
    bgain: int


@dataclass
class DataSet:
    """Everything that was read out of the vendor files."""
    directory: Path
    # pq_picturemode.ini
    presets: dict[str, dict[str, PictureMode]] = field(default_factory=dict)
    preset_order: dict[str, list[str]] = field(default_factory=dict)
    picture_mode_list: list[str] = field(default_factory=list)
    special_mode_list: list[str] = field(default_factory=list)
    # pq_factory_extern.ini
    factory_curves: dict[str, dict[str, list[int]]] = field(default_factory=dict)
    pq_enable: dict[str, int] = field(default_factory=dict)
    # pq_colortemp.ini
    color_temps: dict[str, dict[str, ColorTemp]] = field(default_factory=dict)
    # tvpq.db
    db_picture_mode: list[PictureModeRow] = field(default_factory=list)
    db_white_balance: list[WhiteBalanceRow] = field(default_factory=list)
    db_gamma_points: list[int] = field(default_factory=list)
    # XML
    gamma_levels: list[float] = field(default_factory=list)
    xml_defaults: dict[str, str] = field(default_factory=dict)
    xml_current: dict[str, str] = field(default_factory=dict)
    xml_current_mode: dict[str, str] = field(default_factory=dict)
    #: The stored picture mode "custom", one node per source (AP3d 3).
    xml_custom: dict[str, dict[str, str]] = field(default_factory=dict)
    xml_source_tvin: int | None = None
    # portmap.cfg
    portmap: list[tuple[int, int, str]] = field(default_factory=list)
    # What was not found
    missing_files: list[str] = field(default_factory=list)


# --------------------------------------------------------------------------
# One reader per file
# --------------------------------------------------------------------------

def read_picturemode(path: Path, data: DataSet) -> None:
    sect = read_ini(path)
    cfg = dict(sect.get("CONFIG", []))
    if "picture_mode" in cfg:
        data.picture_mode_list = [t.strip() for t in cfg["picture_mode"].split(",") if t.strip()]
    if "special_mode" in cfg:
        data.special_mode_list = [t.strip() for t in cfg["special_mode"].split(",") if t.strip()]

    for name, entries in sect.items():
        if name in ("CONFIG", "__before_first_section__"):
            continue
        modes: dict[str, PictureMode] = {}
        order: list[str] = []
        for key, raw in entries:
            numbers = number_list(raw)
            if len(numbers) != len(INI_COLUMNS):
                continue
            values = dict(zip(INI_COLUMNS, numbers))
            modes[key] = PictureMode(name, key, values, path.name)
            order.append(key)
        if modes:
            data.presets[name] = modes
            data.preset_order[name] = order


def read_factory(path: Path, data: DataSet) -> None:
    sect = read_ini(path)
    for key, value in sect.get("PQ_ENABLE", []):
        try:
            data.pq_enable[key] = int(value.rstrip("\\").strip())
        except ValueError:
            pass
    # [PICTURE_CURVE_<GROUP>]: PICTURE_CURVE_SETTINGS[1..5]
    # Which index is which control is written as a comment above each line in
    # the file itself (#BRIGHTNESS, #CONTRAST, #SATURATION, #HUE, #SHARPNESS).
    index_control = {1: "brightness", 2: "contrast", 3: "saturation",
                     4: "hue", 5: "sharpness"}
    for name, entries in sect.items():
        if not name.startswith("PICTURE_CURVE_"):
            continue
        group = name[len("PICTURE_CURVE_"):]
        curves: dict[str, list[int]] = {}
        for key, raw in entries:
            if not key.startswith("PICTURE_CURVE_SETTINGS["):
                continue
            try:
                idx = int(key.split("[", 1)[1].rstrip("]"))
            except (IndexError, ValueError):
                continue
            control = index_control.get(idx)
            if control:
                curves[control] = number_list(raw)
        if curves:
            data.factory_curves[group] = curves


def read_colortemp(path: Path, data: DataSet) -> None:
    sect = read_ini(path)
    for name, entries in sect.items():
        if not name.startswith("COLOR_TEMP_"):
            continue
        group = name[len("COLOR_TEMP_"):]
        entry: dict[str, ColorTemp] = {}
        for key, raw in entries:
            z = number_list(raw)
            if len(z) != 6:
                continue
            entry[key] = ColorTemp(group, key, *z)
        if entry:
            data.color_temps[group] = entry


DB_COLUMNS = ("brightness", "contrast", "saturation", "hue", "sharpness",
              "tnr", "snr", "backlight", "colortemperature", "gamma", "dci",
              "blackextenstion", "dynamic_backlight")


def read_db(path: Path, data: DataSet) -> None:
    # Opened read-only -- the vendor file is never touched.
    con = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    try:
        con.row_factory = sqlite3.Row
        for r in con.execute("SELECT * FROM Picture_Mode ORDER BY tvin, mode"):
            values = {}
            for column in DB_COLUMNS:
                target = "blackextension" if column == "blackextenstion" else column
                values[target] = r[column]
            data.db_picture_mode.append(
                PictureModeRow(r["tvin"], r["mode"], r["name"] or "", values))
        for r in con.execute("SELECT * FROM White_Balance_Mode ORDER BY tvin, mode"):
            data.db_white_balance.append(WhiteBalanceRow(
                r["tvin"], r["mode"], r["RGain"], r["GGain"], r["BGain"],
                r["ROffset"], r["GOffset"], r["BOffset"]))
        data.db_gamma_points = [
            int(r["value"] or 0)
            for r in con.execute("SELECT id, value FROM Gamma_Point ORDER BY id")
        ]
    finally:
        con.close()


def read_config_xml(path: Path, data: DataSet) -> None:
    root = ET.parse(path).getroot()
    default = root.find("default")
    if default is not None:
        data.xml_defaults = dict(default.attrib)
    # <transform><item name="gamma" level0="1.8" ... level4="2.4"/></transform>
    for item in root.iterfind("./transform/item"):
        if item.get("name") != "gamma":
            continue
        levels: list[float] = []
        i = 0
        while f"level{i}" in item.attrib:
            levels.append(float(item.attrib[f"level{i}"]))
            i += 1
        data.gamma_levels = levels


def read_custom_xml(path: Path, data: DataSet) -> None:
    root = ET.parse(path).getroot()
    source = root.find("current_source_type")
    if source is not None and source.get("tvin") is not None:
        data.xml_source_tvin = int(source.get("tvin"))
    current = root.find("current_data")
    if current is not None:
        data.xml_current = dict(current.attrib)
    mode = root.find("current_mode")
    if mode is not None:
        data.xml_current_mode = dict(mode.attrib)
    # custom_<source> / custom_hdmi<n> / custom_vga<n>: the "custom" picture
    # mode, stored per source -- AP3d 3 and AP3d 8c, which names this as one
    # of the gaps of this reader.
    for node in root:
        if node.tag.startswith("custom_"):
            data.xml_custom[node.tag] = dict(node.attrib)


def read_portmap(path: Path, data: DataSet) -> None:
    with path.open("r", encoding="utf-8", errors="replace") as f:
        for line in f:
            z = line.strip()
            if not z or z.startswith("#"):
                continue
            parts = z.split()
            if len(parts) >= 3 and parts[0].isdigit() and parts[1].isdigit():
                data.portmap.append((int(parts[0]), int(parts[1]), parts[2]))


# --------------------------------------------------------------------------
# The reader over all files
# --------------------------------------------------------------------------

_READERS = (
    (FILE_PICTUREMODE, read_picturemode),
    (FILE_FACTORY, read_factory),
    (FILE_COLORTEMP, read_colortemp),
    (FILE_DB, read_db),
    (FILE_CONFIG_XML, read_config_xml),
    (FILE_CUSTOM_XML, read_custom_xml),
    (FILE_PORTMAP, read_portmap),
)


#: The files a ``record`` needs -- and only those. Meant for the call h713-tv
#: makes at start (``--json``), where every millisecond costs picture:
#: pq_factory_extern.ini is 592 kB and worth 85 ms on its own (measured on the
#: device, 11.09.), but since the correction of 07.09. it is no longer on the
#: computation path -- the factory curve is a side note of the display.
#: pq_colortemp.ini, pqcontrol_custom_setting.xml and portmap.cfg are not read
#: by the record either.
#:
#: Needed are: pq_picturemode.ini (the presets), tvpq.db (the mode "custom" and
#: the cross-check) and pqcontrol_config_setting.xml (the five gamma levels).
FILES_FOR_RECORD = (FILE_PICTUREMODE, FILE_DB, FILE_CONFIG_XML)


def load(directory: str | None = None,
         only: tuple[str, ...] | None = None) -> DataSet:
    """Read all known PQ files.

    ``only`` restricts the read to a selection of file names (see
    ``FILES_FOR_RECORD``); whatever was not read is listed afterwards under
    ``missing_files`` with the note "not requested", so that no output can
    pretend it had seen the file.

    Neither a missing nor an unreadable file is fatal: both end up in
    ``missing_files`` and the rest is read anyway. Since 11.09. that is no
    longer a convenience but a condition -- h713-tv calls this program at start
    and has to get a picture even from a half broken extraction (plan 113
    section A.5). A wrecked tvpq.db then costs the cross-check, not the presets.

    What is really missing after that -- inputs, picture modes -- shows up
    while computing, not here: there the name in question is known, and a
    KeyError carrying a name is a better message than an abort while reading.
    """
    path = find_data_dir(directory)
    data = DataSet(directory=path)
    for name, reader in _READERS:
        if only is not None and name not in only:
            data.missing_files.append(f"{name} (not requested)")
            continue
        p = path / name
        if not p.is_file():
            data.missing_files.append(name)
            continue
        try:
            reader(p, data)
        except Exception as e:               # noqa: BLE001 -- see the docstring
            data.missing_files.append(f"{name} (unreadable: {e})")
    return data
