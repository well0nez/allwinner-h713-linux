#!/bin/bash
# M1 — does the H713 VE actually decode? Runs ON THE TARGET.
#
# Cedrus binding proves nothing about the silicon: it binds on a DT compatible
# and clock handles, and nothing in a successful probe touches a codec register.
# This script is the actual gate.
#
# STATUS 2026-08-09: all five vectors PASS bit-exact on the bench board. Keep
# this as the regression test -- the failure it originally caught (the ve node's
# `iommus` naming an IOMMU that does not exist at that address) corrupted kernel
# memory and panicked the board rather than reporting an error.
#
# Scoring is per-vector, and the ladder is the instrument: v01 failing and v03
# failing mean completely different things. See docs/video-decode.md.
#
#   usage: ./m1-decode-test.sh [vector-name ...]     (default: all)

set -u

DIR=$(cd "$(dirname "$0")" && pwd)
OUT=${OUT:-/tmp/m1-out}
DEV=${DEV:-/dev/video0}
mkdir -p "$OUT"

hr() { printf '\n=== %s ===\n' "$1"; }

hr "device"
if [ ! -e "$DEV" ]; then
  echo "FAIL: $DEV does not exist -- cedrus did not register"
  exit 1
fi
cat "/sys/class/video4linux/$(basename "$DEV")/name" 2>/dev/null
v4l2-ctl -d "$DEV" --info 2>&1 | sed 's/^/  /'

hr "output formats (what the decoder ACCEPTS -- the codecs)"
v4l2-ctl -d "$DEV" --list-formats-out 2>&1 | sed 's/^/  /'

hr "capture formats (what the decoder EMITS -- the pixel layouts)"
v4l2-ctl -d "$DEV" --list-formats 2>&1 | sed 's/^/  /'

hr "gstreamer stateless decoder elements"
# The stateless decoders register at runtime only when a compatible device
# exists, so an empty list here is itself the result -- it means GStreamer
# looked at this driver and declined.
gst-inspect-1.0 2>/dev/null | grep -iE "v4l2sl|v4l2.*dec" | sed 's/^/  /' \
  || echo "  (none found)"

hr "decode runs"
pass=0; fail=0
vectors=${*:-"v01-320x240-baseline v02-1280x720-baseline v03-1280x720-main v04-1280x720-high v05-1920x1080-high"}

for v in $vectors; do
  src="$DIR/$v.h264"
  [ -f "$src" ] || { echo "  SKIP $v (no stream)"; continue; }
  dst="$OUT/$v.nv12"
  rm -f "$dst"

  printf '\n-- %s\n' "$v"
  # Forcing NV12 is REQUIRED, not just tidy. Left unconstrained the decoder
  # negotiates NV12_32L32 -- Allwinner's 32x32 tiled layout -- and emits
  # ALIGN(height,32) rows (320x240 becomes 122880 bytes/frame, not 115200).
  # That output is correct but tiled, so it can never match a linear reference
  # and reads as a failure if scored naively.
  GST_DEBUG=${GST_DEBUG:-1} timeout 120 gst-launch-1.0 -q \
      filesrc location="$src" ! h264parse ! v4l2slh264dec \
      ! video/x-raw,format=NV12 ! filesink location="$dst" 2>&1 \
    | sed 's/^/     /'

  if [ -s "$dst" ]; then
    md5=$(md5sum "$dst" | cut -d' ' -f1)
    want=$(grep "^$v WHOLE" "$DIR/reference-md5.txt" 2>/dev/null | awk '{print $NF}')
    nframes=$(grep "^$v WHOLE" "$DIR/reference-md5.txt" 2>/dev/null | awk '{print $3}')
    printf '     output %s bytes, md5 %s\n' "$(stat -c%s "$dst")" "$md5"
    if [ -n "$want" ] && [ "$md5" = "$want" ]; then
      echo "     PASS -- bit-exact against the host reference ($nframes frames)"
      pass=$((pass+1))
    elif [ -n "$want" ]; then
      echo "     MISMATCH -- decoded, but not bit-exact (want $want)"
      echo "     Decoded output exists, so the engine ran. Could be stride"
      echo "     padding, frame count, or genuinely wrong pixels -- pull the"
      echo "     file to the host and compare with ffmpeg PSNR before judging."
      fail=$((fail+1))
    else
      echo "     no reference on file; size only"
    fi
  else
    echo "     FAIL -- no output produced"
    fail=$((fail+1))
  fi
done

hr "kernel messages from this run"
dmesg | grep -iE "cedrus|video-codec" | tail -20 | sed 's/^/  /'

printf '\nM1: %d pass, %d fail\n' "$pass" "$fail"
