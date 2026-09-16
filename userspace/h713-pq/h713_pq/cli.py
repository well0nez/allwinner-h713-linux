"""cli.py -- command line of h713-pq.

h713-pq computes and prints. It touches no register, opens no /dev/mem and
talks to no board. A write path is printed as a command line or written as a
file.

The option names are the interface to h713-tv, which starts this program at
every boot as `h713-pq --daten VERZ show INPUT PRESET --json --lut FILE`
(main.c, pq_start()). `--daten` and `--kanal` therefore keep their German
spelling; they are renamed in one later step, with both sides at once.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import model, output, sources

DESCRIPTION = """\
Read the stock PQ data of the HY310 and convert it into kernel interfaces.

Data sources (vendor, read only):
  tvpq.db, pq_picturemode.ini, pq_factory_extern.ini, pq_colortemp.ini,
  pqcontrol_config_setting.xml, pqcontrol_custom_setting.xml, portmap.cfg
"""

EXAMPLES = """\
Examples:
  h713-pq list
  h713-pq show HDMI1 vivid
  h713-pq show HDMI1 standard --lut gamma-standard.bin
  h713-pq saturation HDMI1 cinema
  h713-pq saturation HDMI1 72
  h713-pq gamma 2.2 --lut out.bin
  h713-pq gamma 2.2 --kanal all --lut gamma-rgb.bin
"""


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="h713-pq",
        description=DESCRIPTION,
        epilog=EXAMPLES,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("--daten", metavar="DIRECTORY", dest="data_dir", default=None,
                   help="tvconfig directory (otherwise $H713_TVCONFIG, "
                        "/etc/h713/tvconfig, then re/vendor/... in the tree)")
    sub = p.add_subparsers(dest="command", required=True)

    sub.add_parser("list", help="inputs, picture modes, factory curves, data state")

    s = sub.add_parser("show", help="chain input x picture mode -> target values")
    s.add_argument("input")
    s.add_argument("mode")
    s.add_argument("--lut", metavar="FILE", type=Path, default=None,
                   help="write the gamma LUT of this picture mode into FILE")
    s.add_argument("--kanal", choices=("r", "g", "b", "all"), dest="channel",
                   default="r",
                   help="LUT bank (default r; all three banks are equal here)")
    s.add_argument("--json", action="store_true",
                   help="instead of the table a machine readable record on "
                        "stdout: picture mode number, the nine controls, "
                        "gamma exponent, LUT path and checksum, the picture "
                        "modes of this input (see README)")

    t = sub.add_parser("saturation",
                       help="saturation -> RPC argument (plus the control values "
                            "0x05001238 and chroma gain 0x05140508)")
    t.add_argument("input")
    t.add_argument("value", help="picture mode or user value 0..100")

    g = sub.add_parser("gamma", help="gamma exponent -> DE2 LUT")
    g.add_argument("exponent", type=float)
    g.add_argument("--lut", metavar="FILE", type=Path, default=None)
    g.add_argument("--kanal", choices=("r", "g", "b", "all"), dest="channel",
                   default="r")
    return p


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    # With --json h713-tv reads along at start. Then only what goes into the
    # record is read -- that saves about 90 ms of picture on the device (see
    # sources.FILES_FOR_RECORD). Every other output shows everything and
    # therefore reads everything.
    only = sources.FILES_FOR_RECORD if getattr(args, "json", False) else None
    try:
        data = sources.load(args.data_dir, only)
    except FileNotFoundError as e:
        print(f"h713-pq: {e}", file=sys.stderr)
        return 2

    if args.command == "list":
        output.print_list(data)
        return 0

    if args.command == "show":
        try:
            k = model.chain(data, args.input, args.mode)
        except KeyError as e:
            print(f"h713-pq: {e.args[0] if e.args else e}", file=sys.stderr)
            if args.input in data.presets:
                print("Known picture modes: "
                      + ", ".join(model.modes(data, args.input)), file=sys.stderr)
            else:
                print("Known inputs: " + ", ".join(model.inputs(data)),
                      file=sys.stderr)
            return 2

        # The LUT is written the same way in both cases; only the message
        # beside it differs. With --json it goes to stderr, so that nothing
        # stands on stdout but the record itself.
        lut_path = lut_sum = None
        lut_bytes = 0
        if args.lut is not None:
            if k.gamma_exponent is None:
                print("h713-pq: no gamma exponent for this mode "
                      "(pqcontrol_config_setting.xml missing?)", file=sys.stderr)
                return 2
            result = model.gamma_compute(k.gamma_exponent)
            try:
                lut_bytes = output.write_lut(args.lut, result, args.channel)
            except OSError as e:
                print(f"h713-pq: {args.lut}: {e.strerror}", file=sys.stderr)
                return 2
            lut_path = str(args.lut)
            lut_sum = output.sha256_file(args.lut)

        if args.json:
            output.print_record(model.record(data, args.input, args.mode,
                                             lut_path, lut_bytes, lut_sum))
            if lut_path:
                print(f"h713-pq: LUT written: {lut_path} ({lut_bytes} byte, "
                      f"channel {args.channel}, exponent {k.gamma_exponent})",
                      file=sys.stderr)
            return 0

        output.print_chain(data, k)
        if lut_path:
            print()
            print(f"LUT written: {lut_path} ({lut_bytes} byte, "
                  f"channel {args.channel}, exponent {k.gamma_exponent})")
            print(f"  sha256     : {lut_sum}")
        return 0

    if args.command == "saturation":
        if args.input not in data.presets:
            print(f"h713-pq: unknown input: {args.input}", file=sys.stderr)
            print("Known inputs: " + ", ".join(model.inputs(data)),
                  file=sys.stderr)
            return 2
        group = model.INPUT_GROUP.get(args.input)
        # The factory curve is only shown as a side note now. Since the
        # correction of 07.09. it no longer sits on the computation path, so
        # its absence (VGA1..3) is no reason to stop any more.
        points = data.factory_curves.get(group or "", {}).get("saturation")
        if args.value.lstrip("+-").isdigit():
            u = int(args.value)
            label = f"user value {u}"
        else:
            try:
                pm = model.preset(data, args.input, args.value)
            except KeyError as e:
                print(f"h713-pq: {e.args[0] if e.args else e}", file=sys.stderr)
                return 2
            u = pm.values["saturation"]
            label = f"picture mode {args.value}"
        arg = model.rpc_argument(u)
        gain = model.chroma_gain(arg)
        cv = model.curve_value(points, u) if points else None
        cv_norm = model.curve_as_argument(points, u) if points else None
        output.print_saturation(args.input, group, label, u, cv, arg,
                                gain, model.chroma_gain_register(gain), cv_norm)
        return 0

    if args.command == "gamma":
        result = model.gamma_compute(args.exponent)
        output.print_gamma(result, args.channel)
        if args.lut is not None:
            n = output.write_lut(args.lut, result, args.channel)
            print(f"  File         : {args.lut} ({n} byte)")
        return 0

    return 2
