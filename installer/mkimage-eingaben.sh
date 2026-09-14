#!/bin/bash
# Forwarder: this script is called mkimage-inputs.sh since stage 3 (doku/121).
# Kept for one release for anyone who typed the old name; the build calls the new one.
echo "mkimage-eingaben.sh is now \`mkimage-inputs.sh\` -- forwarding" >&2
exec bash "$(cd "$(dirname "$0")" && pwd)/mkimage-inputs.sh" "$@"
