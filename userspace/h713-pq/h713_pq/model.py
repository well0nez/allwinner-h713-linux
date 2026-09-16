"""model.py -- computing: stock PQ data into kernel interface values.

This module reads no files and prints nothing. It is handed a
``sources.DataSet`` and computes from it the chain

    input x picture mode  ->  user value (0..100)
                          ->  RPC argument (0..100)
                          ->  register (the firmware computes, not we)

The break with the first version (07.09., doku/nachtlog/G-korrektur-saettigung.md):
this module used to compute the **register value** of the saturation itself
(user value -> factory curve -> gain byte). The measurement on the device
(doku/nachtlog/K5-board-verifikation.md section f) shows that this is the wrong
way. ``THal_Vp_SetSaturation`` takes an argument 0..100 and then writes **two**
registers by itself:

    SetSaturation(N)  ->  0x05001238 [15:0]  = N                (1:1)
                      ->  0x05140508 [23:16] = floor(N * 1.28)  (chroma gain)

Measured at N = 0 / 50 / 59 / 60 / 100 -> 0x00 / 0x40 / 0x4B / 0x4C / 0x80.
N = 59 and N = 60 tell ``floor`` from ``round`` and prove ``floor``.

Therefore this module reports the **RPC argument** for the saturation. The gain
byte stays as a control value -- explicitly as ``floor(argument * 1.28)`` and
not as the result of the factory curve.

What is proven and what is not is recorded per control in ``PQ_TARGETS`` and
passed on all the way to the output. The factory curve stays as a vendor datum,
its consumer is open -- see ``rpc_argument`` and ``curve_as_argument``.

Target values outside the PQ RPCs:
  * gamma -> DE2 gamma LUT 0x05208000 / 0x05208800 / 0x05209000 (package H).
    Unchanged: the LUT does not go through an RPC, it is written by the kernel
    and is bit-identical to the legacy calculator.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from . import sources
from . import __version__

# --------------------------------------------------------------------------
# Register constants -- each with its evidence
# --------------------------------------------------------------------------

#: PQ register block of the MIPS firmware ("NEST SW registers"), ARM 0x05001000..0x050015FC.
#: Evidence: doku/85 section A.1..A.3 (static, UIvalueMapping table) and
#: doku/nachtlog/K5-board-verifikation.md section c/e/f (measured on the device).
REG_PQ_BLOCK = 0x05001000
REG_PQ_SHARPNESS = 0x05001228      # [23:8]  sharpness
REG_PQ_BRIGHT_CONTRAST = 0x05001234  # [15:0] brightness, [31:16] contrast
REG_PQ_SAT_HUE = 0x05001238        # [15:0]  saturation, [31:16] hue
#: Operating mode of the block; the lower four bits == 0xA block every register write.
#: Measured on the device: 0x00000000, so not blocked (K5 acceptance section a).
REG_PQ_MODE = 0x0500121C

#: PROC/"route" block, chroma gain, gain field in [23:16].
#: Firmware value after start: 0x144C0000, gain 0x4C.
#: Evidence: doku/76 section 10 + 13, doku/77 section 4,
#: cstenger commit 5718e4c (0x00/0x01 grey, 0x26 pale, 0x4C right, 0xFF oversaturated).
REG_CHROMA_GAIN = 0x05140508
REG_CHROMA_GAIN_STOCK = 0x144C0000
CHROMA_GAIN_SHIFT = 16
CHROMA_GAIN_MASK = 0x00FF0000

#: Mapping RPC argument -> gain field, carried out by the **firmware**:
#: gain = floor(argument * 128 / 100) = floor(argument * 1.28).
#: Measured on the device (K5 acceptance section f, 07.09.):
#:   SetSaturation 0 -> 0x00, 50 -> 0x40, 59 -> 0x4B, 60 -> 0x4C, 100 -> 0x80.
#: The two neighbouring points 59/60 decide between rounding down and rounding
#: half up: 59 * 1.28 = 75.52; measured is 75 (0x4B), not 76. So floor.
#: For arguments 0..100 the firmware therefore uses only the field range
#: 0x00..0x80; 0xFF can be held by the field (cstenger: oversaturated) but
#: cannot be reached through the RPC.
CHROMA_GAIN_NUMERATOR = 128
CHROMA_GAIN_DENOMINATOR = 100

#: The firmware value 0x4C is exactly ``SetSaturation 60`` -- prep_after_boot.sh
#: does not call SetSaturation at all (K5 acceptance section f).
FIRMWARE_DEFAULT_ARGUMENT = 60

#: Largest user value / largest RPC argument of the PQ scale.
USER_VALUE_MAX = 100

#: DE2 gamma LUT, three banks of 512 u32.
#: Evidence: legacy/userspace/hy310-pqd/BACKGROUND.md section 5.1
#: (RE from libhaldisplay.so::WriteGammaLUTByColor, sub_0xB881).
REG_LUT_R = 0x05208000
REG_LUT_G = 0x05208800
REG_LUT_B = 0x05209000
#: Control registers of the write sequence (BACKGROUND.md section 5.2/5.3).
REG_DISPLAY_CTRL = 0x051C00E8
REG_DISPLAY_STAT = 0x051C0174

LUT_ENTRIES = 1024          # samples per colour channel
LUT_DWORDS = 512            # u32 words per bank (two samples per word)
LUT_BITS = 12
LUT_MAX = (1 << LUT_BITS) - 1   # 4095
CURVE_POINTS = 33           # tvpq.db::Gamma_Point has 33 rows

# --------------------------------------------------------------------------
# Inputs
# --------------------------------------------------------------------------
# The input names come from the sections of pq_picturemode.ini. The factory
# curve and colour temperature groups come from the section names of
# pq_factory_extern.ini ([PICTURE_CURVE_*]) and pq_colortemp.ini
# ([COLOR_TEMP_*]). HDMI1..3 share the HDMI group -- there is no curve of its
# own per HDMI port in the vendor files.
# For VGA1..3 there is NO factory curve; that is reported, not guessed.
INPUT_GROUP = {
    "HDMI1": "HDMI", "HDMI2": "HDMI", "HDMI3": "HDMI",
    "CVBS": "CVBS",
    "ATV": "ATV",
    "DTV": "DTV",
    "VIDEODEC": "VIDEODEC",
    "VGA1": None, "VGA2": None, "VGA3": None,
}

#: The five controls for which pq_factory_extern.ini keeps a factory curve
#: (PICTURE_CURVE_SETTINGS[1..5]) and for each of which there is a PQ RPC of
#: its own. The name is historical -- since the correction of 07.09. the curve
#: is no longer on the computation path (see rpc_argument), it is only shown.
CURVE_CONTROLS = ("brightness", "contrast", "saturation", "hue", "sharpness")

#: Controls that go into the MIPS PQ as an index/switch (RPCs, package I),
#: not through a factory curve.
INDEX_CONTROLS = ("tnr", "snr", "colortemperature", "gamma", "dci",
                  "blackextension", "backlight", "dynamic_backlight")

#: The nine controls that make up a preset, in the order in which h713-tv
#: sends them (picture mode first, then these nine -- doku/nachtlog/S14
#: section 4). Exactly these nine stand in the JSON record under "regler".
PRESET_CONTROLS = ("brightness", "contrast", "saturation", "hue", "sharpness",
                   "tnr", "snr", "dci", "blackextension")

#: The remaining four columns of pq_picturemode.ini. Today they reach no
#: control of the driver (there is neither a backlight nor a colortemperature
#: control, doku/nachtlog/S14 section 4), but they are shipped along so that
#: the record maps the INI line completely.
EXTRA_CONTROLS = ("colortemperature", "gamma", "backlight", "dynamic_backlight")

# --------------------------------------------------------------------------
# Picture mode number of the firmware
# --------------------------------------------------------------------------
# This number stands in NONE of the eight vendor files: tvpq.db keeps its own
# counting in Picture_Mode.mode (0 standard, 1 cinema, 2 vivid, 3 game,
# 4 computer, 5 hdr, 6 custom), and the ARM library libvideo.so a third one.
# For THal_Vp_SetPictureMode -- and thus for the driver's control
# "picture_mode" -- only the MIPS firmware counts:
#
#   0 Vivid, 1 Standard, 2 Mild, 3 Game, 4 Calibrated, 5 Calibrated_Dark,
#   6 Computer, 7 Cinema, 8 Home, 9 Sports, 10 Shop, 11 Animation, 12 HDR,
#   13 Graphic
#
# Evidence: doku/nachtlog/S14-re-picture-mode.md section 1.2 (table
# dword_8B1F2120 + TSE group names; for standard -> 1 additionally elog and
# XML). INI name -> TSE name goes by equality of the names.
#
# The number belongs here and not into a second table in h713-tv: it is the
# last quantity the sentence "input x picture mode -> what has to be sent" was
# still missing (plan 113 section A.3, "one source of truth").
FIRMWARE_MODE = {
    "vivid": 0,
    "standard": 1,
    "game": 3,
    "computer": 6,
    "cinema": 7,
    "hdr": 12,
}

#: energy_saving and custom have **no** firmware mode of their own (S14
#: section 4): energy_saving differs from standard only in the backlight 80,
#: custom is only a row in tvpq.db. Both therefore run under the standard
#: number -- their nine controls still come from their own row.
FIRMWARE_MODE_FALLBACK = 1


def firmware_mode(name: str) -> tuple[int, bool]:
    """Picture mode name -> (number for THal_Vp_SetPictureMode, own number?).

    The second field is False when the firmware keeps no mode of its own for
    this name and the standard number is used instead.
    """
    n = FIRMWARE_MODE.get(name.lower())
    if n is None:
        return FIRMWARE_MODE_FALLBACK, False
    return n, True


# --------------------------------------------------------------------------
# Where the five curve controls land -- state per step, with nothing guessed
# --------------------------------------------------------------------------

@dataclass(frozen=True)
class PqTarget:
    """One PQ RPC and the register it serves in the PQ block."""
    control: str
    rpc: str              # without the prefix THal_Vp_
    item_id: int          # UIvalueMapping item, doku/85 A.1
    register: int
    mask: int
    shift: int
    status: str           # state of the register mapping
    argument_1to1: bool   # register == RPC argument, read back on the device?
    evidence: str
    effect: str           # what the wall says about it

    @property
    def field(self) -> str:
        hi = self.mask.bit_length() - 1
        lo = self.shift
        return f"[{hi}:{lo}]"

    def register_expr(self, argument: int | None = None) -> str:
        t = f"0x{self.register:08X} {self.field}"
        if argument is not None:
            t += f" = {argument}"
        return t


#: Source: doku/85 section A.1 (static RE of the UIvalueMapping table) and
#: doku/nachtlog/K5-board-verifikation.md section c/e/f (measurement on the
#: device). Important: **every** field of this block that was measured on the
#: device holds the RPC argument unchanged. The factor 1.28 of the saturation
#: does not sit here but on the additional write into the PROC block.
#:
#: State 11.09.2026 (plan 113 section A.6): the table was out of date in three
#: places and is brought up to date here.
#:   * ``brightness`` said "measured, no effect". Refuted: the 0.00 % of the
#:     first measurement ran against an almost white source, on which
#:     brightness cannot show. Measured again against dark material on
#:     07.09. (doku/nachtlog/I0-helligkeit-nachgemessen.md): std 12.6 -> 22.7,
#:     p95 151 -> 185, monotonic up to 100. Confirmed by eye on 11.09.
#:     (doku/81 section 7 point 4).
#:   * ``hue`` and ``sharpness`` said "RE proven, unmeasured". On 11.09. they
#:     were set with a 1080p signal present and read back over /dev/mem, one
#:     to one over 0..100 at 0/25/50/75/100 (doku/81 section 7 point 3). For
#:     ``hue`` the effect on the picture is confirmed (0 magenta, 100 green);
#:     for ``sharpness`` the register is proven, the effect on the picture was
#:     not measured separately.
#:
#: What the ``status`` field says is what this table knows, and nothing more:
#: "measured" means the register was read back on the device (that is the
#: ``argument_1to1`` flag this program computes with), "effective" means the
#: change was seen on the picture as well. Both are recorded facts here, not
#: something the program checks while it runs.
PQ_TARGETS = {
    "brightness": PqTarget(
        "brightness", "SetBrightness", 3, REG_PQ_BRIGHT_CONTRAST, 0x0000FFFF, 0,
        "measured, effective", True,
        "K5 acceptance e: 100 -> 0x64; effect nachtlog/I0 (07.09.)",
        "proven -- against dark material std 12.6->22.7, p95 151->185, "
        "monotonic up to 100 (nachtlog/I0); confirmed by eye on 11.09."),
    "contrast": PqTarget(
        "contrast", "SetContrast", 4, REG_PQ_BRIGHT_CONTRAST, 0xFFFF0000, 16,
        "measured, effective", True,
        "K5 acceptance c: 20/80/100 -> 0x14/0x50/0x64",
        "proven -- 0->100 changes 12.16 % of the pixels (K5 acceptance d)"),
    "saturation": PqTarget(
        "saturation", "SetSaturation", 5, REG_PQ_SAT_HUE, 0x0000FFFF, 0,
        "measured, effective", True,
        "K5 acceptance f: 0/50/100 -> 0x00/0x32/0x64",
        "proven -- 60->100 changes 0.56 % (source mostly white)"),
    "hue": PqTarget(
        "hue", "SetHue", 6, REG_PQ_SAT_HUE, 0xFFFF0000, 16,
        "measured, effective", True,
        "doku/81 section 7.3 (11.09.): 0/25/50/75/100 -> 1:1 in [31:16]",
        "proven -- 0 magenta, 100 green, confirmed on the picture (11.09.)"),
    "sharpness": PqTarget(
        "sharpness", "SetSharpness", 7, REG_PQ_SHARPNESS, 0x00FFFF00, 8,
        "measured (register)", True,
        "doku/81 section 7.3 (11.09.): 0/25/50/75/100 -> 1:1 in [23:8]",
        "register proven; effect on the picture not measured separately"),
}

#: The same question for the index/switch controls. Here too the register
#: content is the RPC argument, not a converted value. Controls whose RPC
#: writes no register at all are further down in PQ_WITHOUT_REGISTER.
REG_PQ_DCI = 0x0500123C            # [7:0]
REG_PQ_SNR = 0x05001248            # [7:0]

PQ_TARGETS_INDEX = {
    "dci": PqTarget(
        "dci", "SetDCI", 9, REG_PQ_DCI, 0x000000FF, 0,
        "measured", True,
        "K5 acceptance b: prep SetDCI 2, read 2",
        "not measured separately"),
    "snr": PqTarget(
        "snr", "SetSNR", 12, REG_PQ_SNR, 0x000000FF, 0,
        "measured", True,
        "K5 acceptance b: prep SetSNR 1, read 1",
        "not measured separately"),
}

#: RPCs with an item ID but without a register address in the UIMapping table
#: (doku/85 A.1/A.5) -- they demonstrably write no register of this block.
PQ_WITHOUT_REGISTER = {
    "tnr": ("SetTNR", 13),
    "blackextension": ("SetBlackExtension", 8),
}


# --------------------------------------------------------------------------
# Factory curve
# --------------------------------------------------------------------------

def curve_value(points: list[int], user_value: float) -> float:
    """Evaluate the factory curve.

    The five sample points sit at user value 0 / 25 / 50 / 75 / 100
    (doku/77 section 4); in between it is interpolated linearly.
    """
    if not points:
        raise ValueError("empty factory curve")
    n = len(points)
    step = 100.0 / (n - 1)
    x = [i * step for i in range(n)]
    u = max(0.0, min(100.0, float(user_value)))
    for i in range(n - 1):
        if x[i] <= u <= x[i + 1]:
            y0, y1 = points[i], points[i + 1]
            return y0 + (u - x[i]) * (y1 - y0) / (x[i + 1] - x[i])
    return float(points[-1])


def curve_as_argument(points: list[int], user_value: float) -> int:
    """Control computation: the factory curve normalized onto the RPC scale 0..100.

    This function is **not** the computation path of ``h713-pq`` -- it only
    answers the question whether it would make a difference if the factory
    curve did sit between user value and RPC argument after all (see
    ``rpc_argument``). Normalized onto the last sample point, because the RPC
    scale and the curve would have to share their end point.

    For the HDMI saturation curve (0,48,96,145,192) the result differs from the
    user value at **exactly one** place: user value 75 -> 76. No picture mode of
    these vendor data uses 75 (values that occur: 45, 50, 60). So the open step
    has no effect on today's output -- that is why it may stay open instead of
    being guessed.
    """
    if not points or points[-1] == 0:
        raise ValueError("factory curve without a usable end point")
    y = curve_value(points, user_value)
    return int(round(USER_VALUE_MAX * y / points[-1]))


def rpc_argument(user_value: int) -> int:
    """User value from pq_picturemode.ini -> argument of the PQ RPC.

    **This step is not measured.** Proven is only what stands left and right
    of it:

    * The user value of the vendor presets runs from 0 to 100
      (pq_picturemode.ini, comment header).
    * The RPC also takes 0..100 and the PQ block mirrors the argument 1:1 --
      measured for SetContrast (20/80/100), SetBrightness (100) and
      SetSaturation (0/50/100), see ``PQ_TARGETS``.

    The factory curve **cannot** be this step: its values run up to 192
    (saturation) and 3588 (contrast), the argument demonstrably only up to 100,
    and the register content is the argument, not the curve value. What the
    factory curve serves instead is open (doku/81 section 3.2).

    ``h713-pq`` therefore passes the user value through unchanged and writes at
    every point of output that this step is unmeasured. ``curve_as_argument``
    shows that the only serious alternative delivers the same result for all
    preset values of these vendor data.
    """
    return max(0, min(USER_VALUE_MAX, int(user_value)))


def chroma_gain(argument: int) -> int:
    """RPC argument -> gain field 0x05140508 [23:16], **as the firmware computes it**.

    ``floor(argument * 1.28)``, measured on the device at five points
    (K5 acceptance section f). Computed in integers so that no floating point
    rounding error misses the measured points.

    This is a **control computation**: the register is written by the firmware,
    not by us. Whoever writes the value into the register himself bypasses the
    PQ block 0x05001238 and with it everything that hangs on it.
    """
    a = max(0, min(USER_VALUE_MAX, int(argument)))
    return (a * CHROMA_GAIN_NUMERATOR) // CHROMA_GAIN_DENOMINATOR


def chroma_gain_register(gain: int, base: int = REG_CHROMA_GAIN_STOCK) -> int:
    """Put the gain byte into the register word (the other bits stay)."""
    return (base & ~CHROMA_GAIN_MASK) | ((gain & 0xFF) << CHROMA_GAIN_SHIFT)


# --------------------------------------------------------------------------
# Gamma
# --------------------------------------------------------------------------

def _lround(x: float) -> int:
    """C ``lround``: round half away from zero."""
    return int(math.floor(x + 0.5)) if x >= 0 else -int(math.floor(-x + 0.5))


def _idiv(a: int, b: int) -> int:
    """C integer division: truncate towards zero."""
    q = abs(a) // abs(b)
    return -q if (a < 0) != (b < 0) else q


def points_from_exponent(exponent: float) -> list[int]:
    """33 sample points of a power curve, 12 bit.

    1:1 as ``GammaCurve::from_exponent`` in
    legacy/userspace/hy310-pqd/src/pqgamma.cpp:
        points[i] = lround(pow(i / 32, exponent) * 4095)
    """
    n = CURVE_POINTS
    return [_lround(math.pow(i / (n - 1), exponent) * LUT_MAX) for i in range(n)]


def points_identity() -> list[int]:
    """Straight ramp, as ``GammaCurve::identity()``."""
    n = CURVE_POINTS
    return [_lround(i / (n - 1) * LUT_MAX) for i in range(n)]


def interpolate(points: list[int]) -> list[int]:
    """33 sample points -> 1024 LUT entries, piecewise linear.

    Bit-exact rebuild of ``hy310::pqgamma::interpolate`` (pqgamma.cpp):
    Q16 fixed point for the segment bounds, C integer division for the
    fraction, end points set hard.
    """
    if len(points) != CURVE_POINTS:
        raise ValueError(f"{CURVE_POINTS} sample points expected, got {len(points)}")
    lut = [0] * LUT_ENTRIES
    segments = CURVE_POINTS - 1                     # 32
    step_q16 = ((LUT_ENTRIES - 1) << 16) // segments
    for seg in range(segments):
        x0 = (step_q16 * seg) >> 16
        x1 = (step_q16 * (seg + 1)) >> 16
        y0, y1 = points[seg], points[seg + 1]
        dx, dy = x1 - x0, y1 - y0
        x = x0
        while x <= x1 and x < LUT_ENTRIES:
            fraction = _idiv((x - x0) * dy, dx) if dx > 0 else 0
            v = y0 + fraction
            v = 0 if v < 0 else (LUT_MAX if v > LUT_MAX else v)
            lut[x] = v
            x += 1
    lut[0] = points[0]
    lut[LUT_ENTRIES - 1] = points[segments]
    return lut


def pack(lut: list[int]) -> list[int]:
    """1024 samples -> 512 u32 in the DE2 bulk format.

    ``u32[i] = (lut[2i+1] << 12) | lut[2i]`` -- BACKGROUND.md section 5.4,
    from the NEON loop of WriteGammaLUTByColor.
    """
    if len(lut) != LUT_ENTRIES:
        raise ValueError(f"{LUT_ENTRIES} entries expected, got {len(lut)}")
    return [((lut[2 * i + 1] & LUT_MAX) << LUT_BITS) | (lut[2 * i] & LUT_MAX)
            for i in range(LUT_DWORDS)]


def lut_bytes(packed: list[int]) -> bytes:
    """512 u32 -> 2048 byte, little endian (the write order of the bank)."""
    out = bytearray()
    for w in packed:
        out += int(w & 0xFFFFFFFF).to_bytes(4, "little")
    return bytes(out)


@dataclass(frozen=True)
class GammaResult:
    exponent: float
    points: list[int]
    lut: list[int]
    packed: list[int]

    @property
    def bytes_one_bank(self) -> bytes:
        return lut_bytes(self.packed)


def gamma_compute(exponent: float) -> GammaResult:
    points = points_from_exponent(exponent)
    lut = interpolate(points)
    return GammaResult(exponent, points, lut, pack(lut))


def gamma_exponent(data: sources.DataSet, index: int) -> float | None:
    """Gamma index from the presets -> exponent.

    Source: pqcontrol_config_setting.xml, ``<transform><item name="gamma"
    level0..level4>`` = 1.8 / 2.0 / 2.1 / 2.2 / 2.4. The same five values stand
    as a comment in pq_picturemode.ini
    ("#gamma :0-1.8,1-2.0,2-2.1,3-2.2,4-2.4") and as the table dword_4A50
    (180/200/210/220/240) in libhaldisplay.so -- three independent proofs.
    """
    if 0 <= index < len(data.gamma_levels):
        return data.gamma_levels[index]
    return None


# --------------------------------------------------------------------------
# Chain input x picture mode -> target values
# --------------------------------------------------------------------------

@dataclass(frozen=True)
class TargetValue:
    control: str
    user_value: int
    curve_value: float | None  # vendor datum, consumer open (see rpc_argument)
    argument: int | None       # what the RPC gets -- or None without an RPC
    target: str                # register expression or "-"
    status: str                # "measured on the device" / "RE, unmeasured" / ...
    note: str = ""


@dataclass(frozen=True)
class Chain:
    input_name: str
    mode: str
    group: str | None
    preset_source: str
    target_values: list[TargetValue]
    #: RPC argument of the saturation -- the result that is worked with.
    saturation_argument: int | None
    #: Control values: what the firmware makes of it in the chroma gain.
    gain: int | None
    gain_register: int | None
    gamma_index: int | None
    gamma_exponent: float | None
    db_crosscheck: str


def inputs(data: sources.DataSet) -> list[str]:
    return sorted(data.presets.keys())


def modes(data: sources.DataSet, input_name: str) -> list[str]:
    """Picture modes of one input.

    The basis is the INI section of the input. Appended are only modes that
    occur in *no* INI section but which the database carries -- that is exactly
    "custom", which pq_picturemode.ini names in [CONFIG] as a special_mode but
    does not list per input.
    """
    out = list(data.preset_order.get(input_name, []))
    all_ini = {m for lst in data.preset_order.values() for m in lst}
    db_only = sorted({z.name for z in data.db_picture_mode} - all_ini)
    return out + [m for m in db_only if m not in out]


def preset(data: sources.DataSet, input_name: str, mode: str) -> sources.PictureMode:
    """User values of one picture mode.

    The first source is pq_picturemode.ini -- only there are the inputs named.
    If the INI does not know the mode (e.g. "custom"), tvpq.db::Picture_Mode is
    used instead, over the column ``name``.
    """
    if input_name not in data.presets:
        raise KeyError(f"unknown input: {input_name}")
    ini_modes = data.presets[input_name]
    if mode in ini_modes:
        return ini_modes[mode]
    hits = [z for z in data.db_picture_mode if z.name == mode]
    if hits:
        values = dict(hits[0].values)
        return sources.PictureMode(input_name, mode, values,
                                   f"{sources.FILE_DB} (Picture_Mode, name='{mode}')")
    raise KeyError(f"unknown picture mode for {input_name}: {mode}")


def db_crosscheck(data: sources.DataSet, pm: sources.PictureMode) -> str:
    """Cross-check INI against tvpq.db over the mode name.

    The database numbers the inputs (column ``tvin``), the INI names them. The
    numbering cannot be resolved from the shipped files (see tvin_mapping),
    therefore the comparison goes over the mode name -- and checks whether the
    database carries the same values for that name across all tvin at all.
    """
    rows = [z for z in data.db_picture_mode if z.name == pm.name]
    if not rows:
        return f"tvpq.db does not know the mode '{pm.name}'"
    disagreeing = [z for z in rows[1:] if z.values != rows[0].values]
    if disagreeing:
        return (f"tvpq.db carries '{pm.name}' differently per tvin "
                f"({len(rows)} rows) -- no unambiguous comparison possible")
    deviations = []
    for k, v in rows[0].values.items():
        if k in pm.values and pm.values[k] != v:
            deviations.append(f"{k}: INI {pm.values[k]} != db {v}")
    if deviations:
        return ("tvpq.db deviates: " + ", ".join(deviations))
    return (f"tvpq.db Picture_Mode (name='{pm.name}', {len(rows)} rows, "
            f"tvin {min(z.tvin for z in rows)}..{max(z.tvin for z in rows)}) "
            f"agrees value for value")


def chain(data: sources.DataSet, input_name: str, mode: str) -> Chain:
    pm = preset(data, input_name, mode)
    group = INPUT_GROUP.get(input_name)
    curves = data.factory_curves.get(group or "", {})

    target_values: list[TargetValue] = []
    sat_arg = None
    gain = None
    gain_reg = None

    for control in CURVE_CONTROLS:
        if control not in pm.values:
            continue
        u = pm.values[control]
        points = curves.get(control)
        cv = curve_value(points, u) if points else None
        target = PQ_TARGETS[control]
        arg = rpc_argument(u)

        note = f"{target.rpc}/item {target.item_id}; {target.evidence}"
        if not points:
            note += ("; no factory curve for " + group) if group else \
                    "; no curve group"

        if control == "saturation":
            sat_arg = arg
            gain = chroma_gain(arg)
            gain_reg = chroma_gain_register(gain)
            target_values.append(TargetValue(
                control, u, cv, arg,
                f"{target.register_expr(arg)}  + 0x{REG_CHROMA_GAIN:08X} "
                f"[23:16] = 0x{gain:02X}",
                target.status, note))
        else:
            target_values.append(TargetValue(
                control, u, cv, arg,
                target.register_expr(arg) if target.argument_1to1
                else target.register_expr() + " (value unmeasured)",
                target.status, note))

    for control in INDEX_CONTROLS:
        if control not in pm.values:
            continue
        u = pm.values[control]
        if control == "gamma":
            exp = gamma_exponent(data, u)
            target_values.append(TargetValue(
                control, u, exp, None,
                f"DE2 LUT 0x{REG_LUT_R:08X}/0x{REG_LUT_G:08X}/0x{REG_LUT_B:08X}",
                "proven (no RPC)",
                f"exponent {exp} (pqcontrol_config_setting.xml); "
                f"write sequence BACKGROUND.md 5.3, package H"))
        elif control == "colortemperature":
            target_values.append(TargetValue(
                control, u, None, None, "white balance (CTM, package H)",
                "neutral in the data", _color_temp_note(data, group, u)))
        elif control in PQ_TARGETS_INDEX:
            ti = PQ_TARGETS_INDEX[control]
            target_values.append(TargetValue(
                control, u, None, u, ti.register_expr(u), ti.status,
                f"{ti.rpc}/item {ti.item_id}; {ti.evidence}"))
        elif control in PQ_WITHOUT_REGISTER:
            rpc, item = PQ_WITHOUT_REGISTER[control]
            target_values.append(TargetValue(
                control, u, None, u, "no register", "no register write",
                f"{rpc}/item {item}; doku/85 A.1/A.5: address 0, works only "
                f"through the PQ driver object"))
        else:
            target_values.append(TargetValue(control, u, None, u, "-",
                                             "no RPC target known",
                                             "doku/85 A.1 names no item ID -- "
                                             "not guessed"))

    gamma_index = pm.values.get("gamma")
    exp = gamma_exponent(data, gamma_index) if gamma_index is not None else None

    return Chain(input_name, mode, group, pm.origin, target_values,
                 sat_arg, gain, gain_reg, gamma_index, exp, db_crosscheck(data, pm))


# --------------------------------------------------------------------------
# The machine readable record (plan 113 section A.3)
# --------------------------------------------------------------------------
# What h713-tv needs at start, in one piece: the picture mode number, the nine
# controls, the gamma exponent and the path of the written LUT.
#
# Plus **all** picture modes these data hold for this input, each with its nine
# values. Reason: h713-tv shall be able to answer `ctl preset energy_saving`
# whenever the extraction brings that mode along, without calling h713-pq a
# second time while running (plan 113 section A.5, "it is offered as soon as
# the data are there"). Eight modes are a few hundred bytes; a second process
# start would cost more than the whole list.
#
# The requested row stands in the record flat as well (``modus``, ``regler``,
# ``weitere``), so that a reader who only wants this one answer does not have
# to search a list first. Both come out of the same function and therefore
# cannot drift apart.
#
# This function computes and reads nothing from disk; the serializing is done
# by output.print_record, the writing of the LUT by output.write_lut.
#
# The key names of the record are the interface to h713-tv (main.c,
# pq_deuten()/preset_pq_key[]) and are therefore kept exactly as they are,
# German words included: "daten", "modus", "modus_eigen", "regler", "weitere",
# "erzeuger", "eingang", "quelle", "fehlende_dateien". They are renamed in one
# later step, with both sides at once.

#: Version of the record. Raised when meaning or mandatory fields change;
#: h713-tv checks it and discards what it does not know.
RECORD_VERSION = 1


def _preset_record(data: sources.DataSet, input_name: str, mode: str) -> dict:
    """One preset row, the way h713-tv has to send it."""
    pm = preset(data, input_name, mode)
    number, own = firmware_mode(mode)
    index = pm.values.get("gamma")
    return {
        "name": mode,
        "modus": number,
        "modus_eigen": own,
        "quelle": pm.origin,
        "regler": {c: rpc_argument(pm.values[c]) for c in PRESET_CONTROLS
                   if c in pm.values},
        "weitere": {c: pm.values[c] for c in EXTRA_CONTROLS if c in pm.values},
        "gamma_index": index,
        "gamma_exponent": gamma_exponent(data, index) if index is not None else None,
    }


def record(data: sources.DataSet, input_name: str, mode: str,
           lut_path: str | None = None, lut_bytes: int = 0,
           lut_sha256: str | None = None) -> dict:
    """Input x picture mode -> a record as h713-tv reads it at start."""
    this = _preset_record(data, input_name, mode)

    every = []
    for name in modes(data, input_name):
        try:
            every.append(_preset_record(data, input_name, name))
        except KeyError:
            # A mode that modes() knows from the database but for which no
            # values resolve. It is left out and not guessed -- h713-tv then
            # simply offers the others.
            continue

    return {
        "version": RECORD_VERSION,
        "erzeuger": f"h713-pq {__version__}",
        "daten": str(data.directory),
        "eingang": input_name,
        "preset": mode,
        "quelle": this["quelle"],
        "modus": this["modus"],
        "modus_eigen": this["modus_eigen"],
        "regler": this["regler"],
        "weitere": this["weitere"],
        "gamma_index": this["gamma_index"],
        "gamma_exponent": this["gamma_exponent"],
        "lut": lut_path,
        "lut_bytes": lut_bytes,
        "lut_sha256": lut_sha256,
        "presets": every,
        "fehlende_dateien": list(data.missing_files),
    }


#: Order of the colour temperature names as they stand in pq_colortemp.ini and
#: as pq_picturemode.ini comments them
#: ("#colortemperature :0-standard,1-cool,2-warm").
COLOR_TEMP_NAMES = ("STANDARD", "COOL", "WARM", "USER")


def _color_temp_note(data: sources.DataSet, group: str | None, index: int) -> str:
    if group is None:
        return ""
    entries = data.color_temps.get(group, {})
    if index < 0 or index >= len(COLOR_TEMP_NAMES):
        return f"index {index} outside {COLOR_TEMP_NAMES}"
    name = COLOR_TEMP_NAMES[index]
    ct = entries.get(name)
    if not ct:
        return f"{name}: no entry in pq_colortemp.ini"
    return (f"{name}: gain {ct.rgain}/{ct.ggain}/{ct.bgain}, "
            f"offset {ct.roffset}/{ct.goffset}/{ct.boffset}")


# --------------------------------------------------------------------------
# tvin numbering: what the data give and what they do not
# --------------------------------------------------------------------------

def tvin_mapping(data: sources.DataSet) -> list[tuple[int, list[str], list[str]]]:
    """Which inputs can a tvin number stand for?

    The only thing that can be evaluated is the set of picture modes: the
    database carries per ``tvin`` only the modes that input has. The mode name
    stands in the column ``name``, so the set of modes per tvin can be compared
    with the sections of pq_picturemode.ini. Ambiguities stay -- they are not
    guessed.
    """
    out: list[tuple[int, list[str], list[str]]] = []
    ini_sets = {sect: set(m) for sect, m in data.preset_order.items()}
    tvins = sorted({z.tvin for z in data.db_picture_mode})
    for tvin in tvins:
        names = sorted({z.name for z in data.db_picture_mode if z.tvin == tvin})
        candidates = []
        for sect, members in sorted(ini_sets.items()):
            # energy_saving is missing from the database throughout; likewise
            # the database knows "custom", which has no INI section. So the
            # comparison uses both sets of mode names.
            common = members | set(names)
            missing_in_ini = set(names) - members - {"custom"}
            missing_in_db = members - set(names) - {"energy_saving"}
            if not missing_in_ini and not missing_in_db and common:
                candidates.append(sect)
        out.append((tvin, names, candidates))
    return out
