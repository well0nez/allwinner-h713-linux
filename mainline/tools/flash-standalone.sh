#!/usr/bin/env bash
# Flash the kernel FIT to the boot_a partition for standalone boot, then print
# the U-Boot bootcmd to set. Run with the board already in fastboot mode
# (see docs/standalone-boot.md).
#
# Usage: tools/flash-standalone.sh [path/to/h713-kernel.fit]
set -euo pipefail
ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
FIT=${1:-$ROOT/build/out/h713-kernel.fit}

[ -f "$FIT" ] || { echo "no FIT at $FIT — run: build/build.sh kernel" >&2; exit 1; }
command -v fastboot >/dev/null || { echo "fastboot not found (install android-tools)" >&2; exit 1; }

SZ=$(stat -c%s "$FIT")
MAX=$((64 * 1024 * 1024))   # boot_a is 64 MiB
[ "$SZ" -le "$MAX" ] || { echo "FIT is $SZ B, larger than boot_a ($MAX B)" >&2; exit 1; }

echo "==> flashing $FIT ($SZ bytes) to boot_a"
fastboot flash boot_a "$FIT"

cat <<'EOF'

==> done. Now set the bootcmd at the U-Boot => prompt (reset first to restore
    the console), then reset to boot standalone:

  setenv bootcmd 'mmc dev 1; part start mmc 1 5 bootstart; part size mmc 1 5 bootsize; mmc read 0x50000000 ${bootstart} ${bootsize}; bootm 0x50000000'
  setenv bootdelay 2
  saveenv
  reset

See docs/standalone-boot.md for details and recovery.
EOF
