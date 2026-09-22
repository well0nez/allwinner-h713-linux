"""tse.py -- the vendor's own firmware database (TSE) as a data source.

A reader like ``sources.py``: it opens files and computes nothing. It contains
**no TFD parser** -- the walk lives once, in the project's ``tools/tse_dump.py``,
and is loaded from there by path; package Q2 added the three plugin decoders it
lacked (``plugin_states``, ``decode_gamma``, ``decode_feature``).

On a device the files are at ``/boot/mips/`` (see docs/tools/h713-pq.md).
Evidence: AP3r 1.1/1.2 (the selectors and the slot order), AP3p 1.5 (the gamma
record), AP3f 1.3/1.4 (the picture parameters).
"""

from __future__ import annotations

import importlib.util
import os
from dataclasses import dataclass
from pathlib import Path

PLUGIN_GAMMA = 0x00090009        # TTFDGammaFW
PLUGIN_FEATURE = 0x0009101F      # TTFDFeatureFW
UI_COLOR_TEMP = 0x3003           # the attribute that picks a gamma state, AP3r 1.1

#: UI_ColorTemp value -> slot of ``factory_gamma_curve_table``. The firmware
#: registers its nine LUTs as 0x30030002, 0x30030000, 0x30030001, then 3..8
#: (sub_8B152A5C, AP3r 1.2), so the slot order is Normal, Cool, Warm, User --
#: which is Android's ColorTempMode and ``model.COLOR_TEMP_NAMES``.
COLOUR_TEMP_SLOT = {0x30030002: 0, 0x30030000: 1, 0x30030001: 2,
                    0x30030003: 3, 0x30030004: 4, 0x30030005: 5,
                    0x30030006: 6, 0x30030007: 7, 0x30030008: 8}
#: The nine value names in slot order; "standard" is what pq_picturemode.ini
#: calls slot 0 and the TSE calls UI_ColourTemp_Normal.
SLOT_NAMES = ("normal", "cool", "warm", "user", "warmer", "cooler",
              "expert_1", "expert_2", "computer")
SLOT_ALIAS = {"standard": 0}

#: Board-specific, so a parameter with the HY310 value as the default; the
#: HY300 Pro's own tuning is 0x0034 (AP3p 1.7).
DEFAULT_PROJECT = 0x0030

TSE_DUMP_PATHS = (
    os.environ.get("H713_TSE_DUMP", ""),
    str(Path(__file__).resolve().parents[3] / "tools" / "tse_dump.py"),
    str(Path(__file__).resolve().parent / "tse_dump.py"),
    "/usr/lib/h713/tse_dump.py",
)
SEARCH_DIRS = (os.environ.get("H713_TSE_DIR", ""), "/boot/mips")

_parser = None


def parser():
    """Load ``tools/tse_dump.py`` once and hand it back."""
    global _parser
    if _parser is None:
        for candidate in TSE_DUMP_PATHS:
            if candidate and Path(candidate).is_file():
                spec = importlib.util.spec_from_file_location(
                    "h713_pq_tse_dump", candidate)
                _parser = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(_parser)
                break
        else:
            raise FileNotFoundError(
                "tools/tse_dump.py not found. Set $H713_TSE_DUMP. Looked at: "
                + ", ".join(x for x in TSE_DUMP_PATHS if x))
    return _parser


def find_file(given: str | None = None, project: int = DEFAULT_PROJECT,
              name: str | None = None) -> Path:
    """A TSE file: the one given, or ``name`` in the first directory found."""
    name = name or ("ProjectID_0x%04x.TSE" % project)
    candidates = [given] if given else [c for c in SEARCH_DIRS if c]
    for candidate in candidates:
        p = Path(candidate)
        if p.is_file():
            return p
        if (p / name).is_file():
            return p / name
    raise FileNotFoundError(
        "%s not found. Give --tse FILE or --tse DIRECTORY; on a device the "
        "display artifacts are in /boot/mips. Looked at: %s"
        % (name, ", ".join(str(x) for x in candidates if x)))


def modules(path, plugin_id: int):
    """Every module of one TSE file that carries the wanted plugin."""
    with open(str(path), "rb") as f:
        blocks = parser().parse_all(f.read())
    for block in blocks:
        for group in block.get("groups", []):
            for module in group["mods"]:
                if module["plugin_id"] == plugin_id:
                    yield block, module


@dataclass(frozen=True)
class GammaState:
    """One TTFDGammaFW state: three banks of 1024 samples of 12 bit."""
    path: str
    project_id: int
    module: str
    index: int
    colour_temps: tuple        # UI_ColorTemp values of the state's selector
    slots: tuple               # the factory_gamma_curve_table slots they map to
    samples: tuple             # three tuples of 1024 samples

    @property
    def endpoints(self) -> tuple:
        """Per-channel end point -- the board's white balance (AP3r 1.4)."""
        return tuple(bank[-1] for bank in self.samples)

    @property
    def name(self) -> str:
        if self.slots and self.slots[0] < len(SLOT_NAMES):
            return SLOT_NAMES[self.slots[0]]
        return "state %d" % self.index


def gamma_states(path) -> list:
    """Every gamma state of one TSE file, in file order."""
    d = parser()
    out = []
    for block, module in modules(path, PLUGIN_GAMMA):
        for _kind, payload in module["blobs"]:
            for index, (_off, blob) in enumerate(d.plugin_states(payload)):
                samples, _words = d.decode_gamma(blob)
                temps = tuple(
                    v for tag, values in module["states"][index]["attrs"]
                    if tag == UI_COLOR_TEMP for v in values
                ) if index < len(module["states"]) else ()
                out.append(GammaState(
                    str(path), block.get("project_id", 0), module["name"],
                    index, temps,
                    tuple(s for s in (COLOUR_TEMP_SLOT.get(t) for t in temps)
                          if s is not None),
                    tuple(tuple(bank) for bank in samples)))
    return out


# --------------------------------------------------------------------------
# Picture parameters (pq_custom.TSE, group UI_Feature) -- AP3f 1.3 to 1.5
# --------------------------------------------------------------------------

@dataclass(frozen=True)
class Feature:
    """One picture parameter: piecewise-linear curves and their registers."""
    name: str
    id: int
    sets: tuple                # ((points, registers), ...), AP3f 1.4


def picture_features(path) -> list:
    """The UI_Feature module of pq_custom.TSE, in file order."""
    d = parser()
    out = []
    for _block, module in modules(path, PLUGIN_FEATURE):
        for _kind, payload in module["blobs"]:
            for e in d.decode_feature(payload):
                out.append(Feature(e["name"], e["id"], tuple(
                    (tuple(s["points"]), tuple(
                        (r["address"], r["width"], r["mask"]) for r in s["registers"]))
                    for s in e["sets"])))
    return out


def slot_of(selector: str) -> int:
    """Colour-temperature name or slot number -> slot index 0..8."""
    key = str(selector).strip().lower()
    if key in SLOT_ALIAS:
        return SLOT_ALIAS[key]
    if key in SLOT_NAMES:
        return SLOT_NAMES.index(key)
    if key.isdigit() and 0 <= int(key) <= 8:
        return int(key)
    raise KeyError("unknown gamma state: %s. Known: %s, or a slot 0..8"
                   % (selector, ", ".join(SLOT_NAMES + tuple(SLOT_ALIAS))))


def state_for(states: list, selector: str) -> GammaState:
    """The state whose selector carries the wanted colour temperature."""
    slot = slot_of(selector)
    for state in states:
        if slot in state.slots:
            return state
    raise KeyError("no gamma state for slot %d (%s) in this file; it has %s"
                   % (slot, selector,
                      ", ".join(s.name for s in states) or "no gamma module"))
