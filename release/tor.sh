#!/usr/bin/env bash
# release/tor.sh -- alle Tore vor einem Commit, mit ehrlichem Exit-Status.
# `python3 release/sperr-scan.py . | tail -1 && git commit` schluckt den Status des Tors
# (die Pipeline liefert den von tail): am 05./06.10. gingen so dreimal Commits mit harten
# Funden durch. Deshalb hier: jedes Tor einzeln, Exit != 0 beim ersten Fehler.
#   release/tor.sh            # sperr-scan + doku-index --pruefen
#   release/tor.sh --tests    # dazu installer/tests/run.sh (412 Tests, ~1 min) und die Tests von h713-power
set -uo pipefail
cd "$(dirname "$0")/.."
rc=0
python3 release/sperr-scan.py . > /tmp/tor-sperr.$$ 2>&1 || { rc=1; grep -E "FUND|harte" /tmp/tor-sperr.$$; }
tail -1 /tmp/tor-sperr.$$; rm -f /tmp/tor-sperr.$$
python3 release/doku-index.py --pruefen || rc=1
if [[ "${1:-}" == "--tests" ]]; then bash installer/tests/run.sh > /tmp/tor-tests.$$ 2>&1 || { rc=1; tail -5 /tmp/tor-tests.$$; }; grep -E "^Ran|^OK|^FAILED" /tmp/tor-tests.$$; rm -f /tmp/tor-tests.$$
  # h713-power entscheidet zwischen Standby und Ausschalten: seine Tests gehoeren ins Tor (nur stdlib, ~2 s)
  python3 -m unittest discover -s userspace/h713-power/tests > /tmp/tor-tests.$$ 2>&1 || { rc=1; tail -5 /tmp/tor-tests.$$; }; grep -E "^Ran|^OK|^FAILED" /tmp/tor-tests.$$ | sed 's/^/h713-power: /'; rm -f /tmp/tor-tests.$$
  # h713-keys gibt den Tasten ihre Bedeutung (Lautstärke, Stumm, Fokus): auch nur stdlib, ~1 s
  python3 -m unittest discover -s userspace/h713-keys/tests > /tmp/tor-tests.$$ 2>&1 || { rc=1; tail -5 /tmp/tor-tests.$$; }; grep -E "^Ran|^OK|^FAILED" /tmp/tor-tests.$$ | sed 's/^/h713-keys: /'; rm -f /tmp/tor-tests.$$
  # h713-lamp setzt die Lampenstufe (L018: Lampe und Lüfter zusammen): auch nur stdlib, ~1 s
  python3 -m unittest discover -s userspace/h713-lamp/tests > /tmp/tor-tests.$$ 2>&1 || { rc=1; tail -5 /tmp/tor-tests.$$; }; grep -E "^Ran|^OK|^FAILED" /tmp/tor-tests.$$ | sed 's/^/h713-lamp: /'; rm -f /tmp/tor-tests.$$; fi
[[ $rc -eq 0 ]] && echo "Tore: alle gruen" || echo "Tore: ROT -- nicht committen"
exit $rc
