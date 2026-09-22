"""output.py -- printing: tables, LUT files, board command lines.

This module computes nothing and reads no vendor files. It writes exclusively
what the caller asked for (text on stdout, a LUT file on request). It touches
no register -- a write path is printed as a command line, not carried out.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

from . import model, sources


def table(head: list[str], rows: list[list[str]], indent: str = "") -> str:
    columns = len(head)
    width = [len(k) for k in head]
    for z in rows:
        for i in range(columns):
            width[i] = max(width[i], len(z[i]))
    out = [indent + "  ".join(head[i].ljust(width[i]) for i in range(columns)).rstrip()]
    out.append(indent + "  ".join("-" * width[i] for i in range(columns)))
    for z in rows:
        out.append(indent + "  ".join(z[i].ljust(width[i]) for i in range(columns)).rstrip())
    return "\n".join(out)


def _number(x: float | None) -> str:
    if x is None:
        return "-"
    if abs(x - round(x)) < 1e-9:
        return str(int(round(x)))
    return f"{x:.1f}"


# --------------------------------------------------------------------------
# list
# --------------------------------------------------------------------------

def print_list(data: sources.DataSet) -> None:
    print(f"Data directory: {data.directory}")
    if data.missing_files:
        print("missing files: " + ", ".join(data.missing_files))
    print()

    rows = []
    for e in model.inputs(data):
        group = model.INPUT_GROUP.get(e)
        rows.append([
            e,
            group or "(none)",
            ", ".join(model.modes(data, e)),
        ])
    print("Inputs (sections of pq_picturemode.ini)")
    print(table(["Input", "Curve group", "Picture modes"], rows))
    print()

    print("Gamma levels (pqcontrol_config_setting.xml, <transform name=\"gamma\">)")
    if data.gamma_levels:
        print("  " + ", ".join(f"{i}={v}" for i, v in enumerate(data.gamma_levels)))
    else:
        print("  none found")
    print()

    print("Factory curves (pq_factory_extern.ini, PICTURE_CURVE_SETTINGS[1..5])")
    print("  Vendor datum. These curves do NOT sit between user value and "
          "PQ RPC --")
    print("  their values run up to 192/3588, the RPC argument up to 100. "
          "Consumer open (doku/81 section 3.2).")
    rows = []
    for group in sorted(data.factory_curves):
        for control in model.CURVE_CONTROLS:
            k = data.factory_curves[group].get(control)
            if k:
                rows.append([group, control, ",".join(str(x) for x in k)])
    print(table(["Group", "Control", "Sample points at 0/25/50/75/100"], rows))
    print()

    print("tvpq.db")
    print(f"  Picture_Mode      : {len(data.db_picture_mode)} rows")
    print(f"  White_Balance_Mode: {len(data.db_white_balance)} rows")
    gp = data.db_gamma_points
    if gp:
        print(f"  Gamma_Point       : {len(gp)} rows, "
              f"min {min(gp)} / max {max(gp)}"
              + ("  -- 0 throughout, unusable as a curve" if max(gp) == 0 else ""))
    print()

    print("tvin numbering of the database -- tvin is TvSourceType (AP3d 2)")
    rows = []
    for tvin, source, names, sections, gap in model.tvin_mapping(data):
        rows.append([str(tvin), source, ", ".join(sections) or "-",
                     ", ".join(names),
                     ", ".join(gap) if gap else "agrees"])
    print(table(["tvin", "TvSourceType", "INI sections", "Picture modes of "
                 "the rows", "Difference"], rows))
    print("  0 HDMI, 1 CVBS, 2 ATV, 3 DTV, 4 VIDEODEC, 5 VGA -- "
          "UpdateDataManager@0x2D99C and the")
    print("  device's own XML (current_source_type tvin=4 next to "
          "mode_videodec). h713-pq still")
    print("  computes over the named INI sections: that is the live source, "
          "the database is what")
    print("  a factory reset falls back to (AP3d 3, PQControl::"
          "resetAllSettings@0x22D10).")
    print()

    print("Picture mode \"custom\" per source (AP3d 3 -- NOT a row of tvpq.db)")
    rows = []
    for e in model.inputs(data):
        node = model.custom_node(e)
        if node:
            rows.append([e, model.source_of(e) or "-", node,
                         "present" if node in data.xml_custom else "not in "
                         "this file"])
    print(table(["Input", "TvSourceType", "XML node", "State"], rows))
    print()

    print("Last set on stock (pqcontrol_custom_setting.xml)")
    if data.xml_source_tvin is not None:
        print(f"  current_source_type tvin = {data.xml_source_tvin}")
    if data.xml_current_mode:
        print("  " + ", ".join(f"{k}={v}" for k, v in data.xml_current_mode.items()))
    if data.xml_current:
        print("  " + ", ".join(f"{k}={v}" for k, v in data.xml_current.items()))
    print()

    if data.pq_enable:
        print("Switches (pq_factory_extern.ini, [PQ_ENABLE])")
        rows = [[k, str(v)] for k, v in data.pq_enable.items()]
        print(table(["Switch", "Value"], rows))


# --------------------------------------------------------------------------
# show
# --------------------------------------------------------------------------

def print_chain(data: sources.DataSet, k: model.Chain) -> None:
    print(f"Input {k.input_name}   Picture mode {k.mode}"
          + (f"   Curve group {k.group}" if k.group else "   Curve group: none"))
    print(f"User values from: {k.preset_source}")
    print(f"Cross-check     : {k.db_crosscheck}")
    print()

    rows = []
    for z in k.target_values:
        rows.append([z.control, str(z.user_value),
                     "-" if z.argument is None else str(z.argument),
                     _number(z.curve_value), z.target, z.status, z.note])
    print(table(["Control", "User", "RPC arg", "Curve/exp",
                 "Register -- written by the firmware", "State", "Evidence / note"],
                rows))
    print()
    print("Column 'RPC arg' is the result: the value THal_Vp_Set<Control> gets.")
    print("Column 'Curve' is a vendor datum from pq_factory_extern.ini; it does NOT sit")
    print("  on this path (its values run up to 192 resp. 3588, the argument up to 100).")
    print("The step user value -> RPC argument is NOT measured; h713-pq passes the user")
    print("  value through because both scales are 0..100. See doku/81 section 3.2.")
    print()

    if k.saturation_argument is not None:
        print("Write path saturation -- over the RPC, as stock does "
              "(NOT written from here):")
        print(f"  ssh root@192.168.8.141 'python3 /root/pq_probe.py rpc "
              f"SetSaturation {k.saturation_argument}'")
        print(f"  Check afterwards: 0x{model.REG_PQ_SAT_HUE:08X} [15:0] = "
              f"{k.saturation_argument}  and")
        print(f"                    0x{model.REG_CHROMA_GAIN:08X} [23:16] = "
              f"0x{k.gain:02X} = floor({k.saturation_argument} x 1.28)"
              f"   (word 0x{k.gain_register:08X})")
        print("  Writing the gain byte into the register yourself bypasses the PQ block "
              "and is NOT the way of the firmware.")
    if k.gamma_exponent is not None:
        print("Write path gamma: DE2 LUT, package H (kernel, GAMMA_LUT) -- no RPC.")
        print(f"  Make the LUT: h713-pq gamma {k.gamma_exponent} --lut gamma.bin")
    print()
    print("State 11.09.2026: all five controls are measured on the device and write their")
    print("  register one to one (doku/81 section 7.3). What stays open is the step")
    print("  user value -> RPC argument (section 7.1) and the consumer of the")
    print("  factory curve (section 7.5).")


# --------------------------------------------------------------------------
# saturation
# --------------------------------------------------------------------------

def print_saturation(input_name: str, group: str | None, label: str,
                     user_value: int, curve: float | None, argument: int,
                     gain: int, register: int,
                     curve_normalized: int | None = None) -> None:
    print(f"Input {input_name} (curve group {group or 'none'})   {label}")
    print()
    print("The chain, step by step:")
    print(f"  1. User value    : {user_value}      "
          f"pq_picturemode.ini / input   [proven: vendor file]")
    print(f"  2. RPC argument  : {argument}      "
          f"THal_Vp_SetSaturation({argument})   [step 1->2 NOT measured, "
          f"passed through 1:1]")
    print(f"  3. PQ register   : 0x{model.REG_PQ_SAT_HUE:08X} [15:0] = {argument}"
          f"   [measured: argument 1:1, K5 acceptance f]")
    print(f"  4. Chroma gain   : 0x{model.REG_CHROMA_GAIN:08X} [23:16] = 0x{gain:02X}"
          f" = floor({argument} x 1.28)   [measured at 0/50/59/60/100]")
    print(f"     Register word : 0x{register:08X}   (idle value of the firmware "
          f"0x{model.REG_CHROMA_GAIN_STOCK:08X} = SetSaturation "
          f"{model.FIRMWARE_DEFAULT_ARGUMENT})")
    print()
    print("Side note from the vendor data (does NOT sit on this chain):")
    if curve is None:
        print("  Factory curve: none -- this input has no group in "
              "pq_factory_extern.ini")
    else:
        print(f"  Factory curve: {curve:.1f}   "
              f"(pq_factory_extern.ini, PICTURE_CURVE_SETTINGS[3])")
        if curve_normalized is not None:
            print(f"  normalized to 0..100: {curve_normalized}   "
                  f"-- {'equal to the' if curve_normalized == argument else 'DIFFERENT from the'}"
                  f" user value {user_value}")
    print("  The curve value is no RPC argument: the curve runs up to 192, the "
          "argument up to 100,")
    print("  and the PQ register demonstrably holds the argument. Consumer "
          "of the curve: open.")
    print()
    print("Setting it (on the board, not from here):")
    print(f"  ssh root@192.168.8.141 'python3 /root/pq_probe.py rpc "
          f"SetSaturation {argument}'")
    print("  Do not write 0x{:02X} into the register by hand -- that bypasses the "
          "PQ block.".format(gain))


# --------------------------------------------------------------------------
# gamma
# --------------------------------------------------------------------------

def print_gamma(result: model.GammaResult, channel: str) -> None:
    print(f"Gamma exponent {result.exponent}")
    print(f"  Sample points: {model.CURVE_POINTS} values, 12 bit "
          f"(grid as tvpq.db::Gamma_Point)")
    print("               : " + ", ".join(str(p) for p in result.points[:9]) + ", ...")
    print(f"  LUT          : {model.LUT_ENTRIES} entries, "
          f"lut[0]={result.lut[0]}  lut[512]={result.lut[512]}  "
          f"lut[1023]={result.lut[model.LUT_ENTRIES - 1]}")
    print(f"  DE2 format   : {model.LUT_DWORDS} u32 per bank, "
          f"u32[i] = (lut[2i+1] << 12) | lut[2i]  (BACKGROUND.md 5.4)")
    print("    u32[0..3]: " + ", ".join(f"0x{w:08X}" for w in result.packed[:4]))
    print("  u32[256..]: " + ", ".join(f"0x{w:08X}" for w in result.packed[256:260]))
    print(f"  Banks        : R 0x{model.REG_LUT_R:08X}  "
          f"G 0x{model.REG_LUT_G:08X}  B 0x{model.REG_LUT_B:08X}")
    print(f"  Control      : 0x{model.REG_DISPLAY_CTRL:08X} "
          f"(status 0x{model.REG_DISPLAY_STAT:08X}), "
          f"write sequence BACKGROUND.md 5.3 -- carried out by package H")
    print(f"  Channel      : {channel}")


def _field(register: tuple, value: float) -> str:
    address, _width, mask = register
    hi = mask.bit_length() - 1
    lo = (mask & -mask).bit_length() - 1
    return (f"0x{address:08X} [{hi}:{lo}] = "
            f"0x{model.feature_field(mask, value) >> lo:X}")


def _feature_rows(control, points, ini, f, value):
    """One row per (curve, register list) pair of one feature."""
    out = []
    for segments, registers in f.sets:
        v = model.feature_value(segments, value)
        out.append([control, points, ini,
                    "%s (%g..%g)" % (f.name, segments[0][0], segments[-1][1]),
                    _number(v), ", ".join(_field(r, v) for r in registers)])
    return out


def print_curves(data: sources.DataSet, value: float, features=None,
                 group: str = "HDMI") -> None:
    """The OSD-to-register step out of both sources (Q2 item 2)."""
    print(f"OSD-to-register mapping at user value {value}")
    print(f"  ini: pq_factory_extern.ini [PICTURE_CURVE_{group}], four "
          "segments with roundf -- the")
    print("       direct path libpq writes (UserValueToMappedValue@0x3AEE8, "
          "AP3 3.3a). Identical")
    print("       in all five groups on the HY310 (AP3d 5).")
    if features is None:
        print("  tse: not read. --source tse adds the curves the FIRMWARE "
              "uses (AP3f 1.5).")
    else:
        print("  tse: pq_custom.TSE, group UI_Feature -- the curve and the "
              "register the firmware")
        print("       itself applies (AP3f 1.4/1.5). Where the two differ the "
              "TSE is what the")
        print("       picture shows; the ini is the OSD slider's own curve.")
    curves = data.factory_curves.get(group, {})
    by_control = {}
    for f in features or []:
        by_control.setdefault(model.TSE_FEATURE_CONTROL.get(f.name, f.name),
                              []).append(f)
    rows = []
    for control in model.CURVE_CONTROLS:
        points = curves.get(control)
        ini = str(model.nlc_value(points, value)) if points else "-"
        for f in by_control.pop(control, [None]):
            if f is None:
                rows.append([control, ",".join(str(x) for x in points or []),
                             ini, "-", "-", "-"])
                continue
            rows += _feature_rows(control, ",".join(str(x) for x in points or []),
                                  ini, f, value)
    for control, entries in sorted(by_control.items()):
        for f in entries:
            rows += _feature_rows(control, "-", "-", f, value)
    print(table(["Control", "ini points 0/25/50/75/100", "ini",
                 "TSE feature (its own ui range)", "TSE",
                 "Register -- written by the firmware"], rows))
    print()
    print("h713-pq sends neither of these: our path is the RPC, which takes "
          "0..100 and lets the")
    print("  firmware map it (model.rpc_argument). The table answers which "
          "register a value ends")
    print("  in, so a future direct-write path has one implementation.")


GAMMA_MARKS = (0, 128, 256, 384, 512, 640, 768, 896, 1023)


def print_tse_gamma(result: model.TseGammaResult, channel: str) -> None:
    """The vendor's own curve -- three banks, one per channel."""
    s = result.state
    print(f"Gamma from the TSE: {s.path}")
    print(f"  Module       : {s.module} (project 0x{s.project_id:04X}), "
          f"state {s.index} = {s.name}; selector UI_ColorTemp "
          + ",".join(f"0x{v:08X}" for v in s.colour_temps)
          + " -> slot " + ",".join(str(x) for x in s.slots))
    print(f"  Gamma level  : {result.level} -> exponent {result.exponent:.6f}"
          f" = level / {model.GAMMA_DIVISOR}  (CalculateGamma, AP3t 2.2)")
    print("  End points   : R %d  G %d  B %d%s" % (
        result.endpoints + (
            "   -- per channel: the white balance is in the LUT (AP3r 1.4)"
            if len(set(result.endpoints)) > 1 else "   -- equal everywhere",)))
    print(table(["Sample", "R", "G", "B"],
                [[str(x)] + [str(result.luts[c][x]) for c in range(3)]
                 for x in GAMMA_MARKS], indent="  "))
    print(f"  Banks        : R 0x{model.REG_LUT_R:08X}  "
          f"G 0x{model.REG_LUT_G:08X}  B 0x{model.REG_LUT_B:08X}, "
          f"{model.LUT_DWORDS} u32 each, u32[i] = (lut[2i+1] << 12) | lut[2i]")
    print(f"  Channel      : {channel}")
    print("  Behaviour change: written only with --source tse; the synthetic "
          "curve stays the")
    print("  default until a device test flips it (README, \"Where the gamma "
          "curve comes from\").")


# --------------------------------------------------------------------------
# Machine readable: one JSON record on stdout (plan 113 section A.3)
# --------------------------------------------------------------------------
# One record, one line of a call, no daemon. The consumer is h713-tv, which
# calls `h713-pq --data DIR show INPUT PRESET --json --lut D` once at start and
# applies the answer. Therefore:
#   * **everything on stdout, nothing else.** Messages go to stderr so that the
#     reader can push the record through a parser raw.
#   * **a single JSON object**, with a newline at the end.
#   * **fixed key names** and a `version`; what h713-tv does not know it
#     discards, falling back to its compiled-in table.
# The meaning of the fields stands in README.md, section "Machine readable
# output".

def print_record(record: dict) -> None:
    """Print the record as one JSON line (stdout, nothing else)."""
    print(json.dumps(record, ensure_ascii=False, sort_keys=True))


def sha256_file(path: Path) -> str:
    """Checksum of a written file -- a counter-check for the reader."""
    h = hashlib.sha256()
    with path.open("rb") as f:
        for piece in iter(lambda: f.read(65536), b""):
            h.update(piece)
    return h.hexdigest()


def write_lut(path: Path, result: model.GammaResult, channel: str) -> int:
    """Write the LUT file. channel: r|g|b -> one bank, all -> R,G,B in a row.

    For the synthetic curve the white balance in these vendor data is neutral
    (gain 512/512/512, offset 0), so all three banks are equal and "all"
    exists only so that package H gets a finished RGB file. For a curve out
    of the TSE the three banks differ -- that is the board's own white
    balance (AP3r 1.4) -- so "all" is the only complete file there.

    Written over a neighbouring file with fsync and os.replace, the way h713-tv
    does it for its own state files: since h713-tv makes this call at start and
    aborts it after a deadline (plan 113 section A.5), an aborted run must not
    leave half a LUT behind that looks valid at the next start.

    The suffix of that neighbouring file stays ".neu": it is the same
    convention h713-tv uses for its own atomic writes (main.c, "%s.neu"), and
    a name both programs leave behind on a crash is renamed on both sides at
    once, not here alone.
    """
    data = result.bank_bytes(channel)
    neighbour = path.with_name(path.name + ".neu")
    with neighbour.open("wb") as f:
        f.write(data)
        f.flush()
        os.fsync(f.fileno())
    os.replace(neighbour, path)
    return len(data)
