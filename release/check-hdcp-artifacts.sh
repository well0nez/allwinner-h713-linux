#!/usr/bin/env bash
# release/check-hdcp-artifacts.sh -- does a built image really carry the HDCP path,
# and does it carry nothing it must not?
#
# boards/check.sh judges the sources. This one judges the ARTEFACTS, because that is
# where the mistake actually happens: a piece that is not in the effective defconfig
# compiles away silently and the release boots without protected playback. It also
# refuses an image built with the workbench probes, and any image that has key
# material in it.
#
# Usage: bash release/check-hdcp-artifacts.sh <u-boot image> [bl31 binary]
#   exit 0 = may be released, 1 = do not release

set -uo pipefail

UBOOT=${1:-}
BL31=${2:-}
[ -n "$UBOOT" ] && [ -r "$UBOOT" ] || { echo "usage: $0 <u-boot image> [bl31]"; exit 1; }

fails=0
ok()   { printf '  ok    %s\n' "$*"; }
fail() { printf '  FAIL  %s\n' "$*"; fails=$((fails + 1)); }

# Note the -c instead of -q: with `set -o pipefail`, `grep -q` exits at the first
# match, `strings` then dies of SIGPIPE with 141, and that becomes the status of the
# whole pipeline - so a string that IS there was reported as missing, and this gate
# refused every image. Counting consumes all input and has no such edge.
has()  { [ "$(strings -a "$1" | grep -cF "$2")" -gt 0 ]; }
count(){ strings -a "$1" | grep -cF "$2"; }

echo "U-Boot: $UBOOT"
# 1. The HDCP path has to be linked in. These strings only exist in h713_hdcp14.c,
#    so their absence means CONFIG_H713_MIPS_BOOT did not reach this build.
for s in "H713 HDCP: 1.4 key set handed to the receiver" \
         "H713 HDCP: no '%s' item in the secure storage" \
         "H713 HDCP: the two stored copies differ"; do
  if has "$UBOOT" "$s"; then ok "carries: ${s:11:46}"
  else fail "missing: $s  (is CONFIG_H713_MIPS_BOOT set for this board?)"; fi
done

# 2. The firmware wait loop must not be forced on by a stored environment: without a
#    key it waits forever and the board hangs at the logo (measured 05.10. 04:xx).
# -x, an exact line: a stored environment entry stands alone between two NUL bytes
# and `strings` prints it as its own line, while a diagnostic message that merely
# names the variable appears embedded in a longer line. Without -x this matched
# h713_mips.c's own "... (h713_hdcp14_wait=1) -- can hang" message and refused a
# perfectly good image.
if [ "$(strings -a "$UBOOT" | grep -cxF "h713_hdcp14_wait=1")" -gt 0 ]; then
  fail "the image has h713_hdcp14_wait=1 baked into its environment"
else
  ok "no h713_hdcp14_wait=1 in the built-in environment"
fi

if [ -n "$BL31" ] && [ -r "$BL31" ]; then
  echo "BL31: $BL31"
  # 3. Our own chain, no vendor Trusted OS dispatcher.
  if [ "$(count "$BL31" opteed)" -eq 0 ]; then ok "no opteed dispatcher (our own chain)"
  else fail "BL31 contains an opteed dispatcher - that is the vendor path"; fi

  # 4. The service that does the work has to be there.
  if has "$BL31" "key set from"; then ok "the key-sink service is present"
  else fail "BL31 has no key-sink service - U-Boot will get SMC_UNK"; fi

  # 5. ... and the workbench probes must not be.
  for s in SIDscan "re-ran the vendor" CEscan "sweep"; do
    if has "$BL31" "$s"; then fail "built with H713_HDCP_RESEARCH - do not ship ($s)"
    else ok "no workbench probe: $s"; fi
  done
fi

# 6. No key material in either artefact.
for f in "$UBOOT" "$BL31"; do
  [ -n "$f" ] && [ -r "$f" ] || continue
  if python3 "$(dirname "${BASH_SOURCE[0]}")/../installer/tests/no_key_material.py" "$f" >/dev/null 2>&1; then
    ok "no key material in $(basename "$f")"
  else
    fail "KEY MATERIAL in $(basename "$f") - this must never be distributed"
  fi
done

echo
if [ "$fails" -eq 0 ]; then echo "green: may be released"; else echo "$fails problem(s): do NOT release"; fi
exit $((fails > 0))
