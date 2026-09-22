"""cli.py -- command line of h713-pq.

h713-pq computes and prints. It touches no register, opens no /dev/mem and
talks to no board. A write path is printed as a command line or written as a
file.

The option names are the interface to h713-tv, which starts this program at
every boot as `h713-pq --data DIR show INPUT PRESET --json --lut FILE`
(main.c, pq_start()). `--daten` and `--kanal` stay accepted, hidden, for
v0.8-beta, so an older script keeps working; the German field names of the
JSON record are a step of their own.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import model, output, sources, tse

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
  h713-pq gamma 2.2 --channel all --lut gamma-rgb.bin
"""

# Lines marked GERMAN ALIAS take the name of v0.8-beta and earlier, hidden
# from --help; they go out together after that release.
CHANNELS = ("r", "g", "b", "all")


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="h713-pq",
        description=DESCRIPTION,
        epilog=EXAMPLES,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("--data", metavar="DIRECTORY", dest="data_dir", default=None,
                   help="tvconfig directory (otherwise $H713_TVCONFIG, "
                        "/etc/h713/tvconfig, then re/vendor/... in the tree)")
    p.add_argument("--daten", dest="data_dir", help=argparse.SUPPRESS)  # GERMAN ALIAS
    sub = p.add_subparsers(dest="command", required=True)

    sub.add_parser("list", help="inputs, picture modes, factory curves, data state")

    s = sub.add_parser("show", help="chain input x picture mode -> target values")
    s.add_argument("input")
    s.add_argument("mode")
    s.add_argument("--lut", metavar="FILE", type=Path, default=None,
                   help="write the gamma LUT of this picture mode into FILE")
    s.add_argument("--channel", choices=CHANNELS, dest="channel",
                   default="r",
                   help="LUT bank (default r; all three banks are equal here)")
    s.add_argument("--kanal", choices=CHANNELS, dest="channel",
                   help=argparse.SUPPRESS)  # GERMAN ALIAS
    _tse_options(s)
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
    g.add_argument("exponent", type=float, nargs="?", default=None,
                   help="gamma level 1.8..2.4; with --source tse the default "
                        "is 2.2, the vendor's neutral factor (raw curve)")
    g.add_argument("--lut", metavar="FILE", type=Path, default=None)
    g.add_argument("--channel", choices=CHANNELS, dest="channel",
                   default="r")
    g.add_argument("--kanal", choices=CHANNELS, dest="channel",
                   help=argparse.SUPPRESS)  # GERMAN ALIAS
    _tse_options(g)
    return p


def _tse_options(p: argparse.ArgumentParser) -> None:
    """Where the gamma curve comes from. Default unchanged: synthetic."""
    p.add_argument("--source", choices=("synthetic", "tse"), default="synthetic",
                   help="synthetic (default, today's computed power curve) or "
                        "tse (the board's own measured curve -- behaviour change)")
    p.add_argument("--from-tse", metavar="STATE", dest="tse_state", default=None,
                   help="gamma state by colour temperature (normal, cool, warm, "
                        "user, ... or a slot 0..8); implies --source tse")
    p.add_argument("--tse", metavar="PATH", dest="tse_path", default=None,
                   help="TSE file or directory (else $H713_TSE_DIR, /boot/mips)")
    p.add_argument("--project", metavar="ID", dest="tse_project", default=None,
                   help=f"board ProjectID when --tse is a directory "
                        f"(default 0x{tse.DEFAULT_PROJECT:04x}, the HY310)")


def _wants_tse(args) -> bool:
    return args.source == "tse" or args.tse_state is not None


def _tse_gamma(args, level: float):
    """Read the board's TSE and lay the gamma level on the picked state."""
    project = (int(str(args.tse_project), 0) if args.tse_project is not None
               else tse.DEFAULT_PROJECT)
    states = tse.gamma_states(tse.find_file(args.tse_path, project))
    return model.gamma_from_tse(tse.state_for(states, args.tse_state or "normal"),
                                level)


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
            if k.gamma_exponent is None and not _wants_tse(args):
                print("h713-pq: no gamma exponent for this mode "
                      "(pqcontrol_config_setting.xml missing?)", file=sys.stderr)
                return 2
            # Behaviour change, only under the flag: the board's own measured
            # curve instead of the computed power law (AP3t 2.5).
            try:
                result = (_tse_gamma(args, k.gamma_exponent
                                     or model.GAMMA_LEVEL_NEUTRAL)
                          if _wants_tse(args)
                          else model.gamma_compute(k.gamma_exponent))
            except (FileNotFoundError, KeyError, ValueError) as e:
                print(f"h713-pq: {e.args[0] if e.args else e}", file=sys.stderr)
                return 2
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
        if not _wants_tse(args):
            if args.exponent is None:
                print("h713-pq: gamma needs an exponent (or --source tse)",
                      file=sys.stderr)
                return 2
            result = model.gamma_compute(args.exponent)
            output.print_gamma(result, args.channel)
        else:
            try:
                result = _tse_gamma(args, args.exponent
                                    or model.GAMMA_LEVEL_NEUTRAL)
            except (FileNotFoundError, KeyError, ValueError) as e:
                print(f"h713-pq: {e.args[0] if e.args else e}", file=sys.stderr)
                return 2
            output.print_tse_gamma(result, args.channel)
        if args.lut is not None:
            n = output.write_lut(args.lut, result, args.channel)
            print(f"  File         : {args.lut} ({n} byte)")
        return 0

    return 2
