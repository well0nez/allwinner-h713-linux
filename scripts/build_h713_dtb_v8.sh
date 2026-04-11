#!/bin/bash
# Build H713 HY310 DTB from canonical source DTS.
# Source of truth: /opt/hy310/repo/dts/sun50i-h713-hy310.dts
# Output: /opt/hy310/build-output/sun50i-h713-hy310-v7.dtb
#
# Replaces build_h713_dtb_v7.sh which embedded a 1600-line heredoc that
# drifted from the canonical source. Always compile the canonical file.
set -e

KDIR=${KDIR:-/opt/hy310/kernels/working}
OUTDIR=${OUTDIR:-/opt/hy310/build-output}
DTS_SRC=${DTS_SRC:-/opt/hy310/repo/dts/sun50i-h713-hy310.dts}

if [ ! -f "$DTS_SRC" ]; then
    echo "ERROR: canonical DTS not found: $DTS_SRC" >&2
    exit 1
fi

mkdir -p "$OUTDIR"

echo "=== HY310 DTB build ==="
echo "Source: $DTS_SRC"
echo "Output: $OUTDIR/sun50i-h713-hy310-v7.dtb"

cpp -nostdinc \
    -I "$KDIR/include" \
    -I "$KDIR/scripts/dtc/include-prefixes" \
    -undef -x assembler-with-cpp \
    "$DTS_SRC" | \
"$KDIR/scripts/dtc/dtc" -I dts -O dtb \
    -W no-unit_address_vs_reg \
    -o "$OUTDIR/sun50i-h713-hy310-v7.dtb" -

echo "Done."
ls -lh "$OUTDIR/sun50i-h713-hy310-v7.dtb"
