#!/bin/bash
# VA1 — does libva-v4l2-request decode H.264 on the VE, bit-exact? RUNS ON THE TARGET.
#
# This is the gate for docs/vaapi-scope.md step 5, and it is deliberately run
# with NO DISPLAY INVOLVED. The display path is a separate and larger risk; if
# both are in play at once, a failure lands in neither half cleanly.
#
# The instrument is the M1 ladder's references — the same vectors and the same
# whole-file md5s that scored the GStreamer path bit-exact — so a PASS here
# means the shim drives cedrus exactly as well as GStreamer already does, and a
# MISMATCH means it decoded something, but not the same pixels.
#
# WHY THE SOFTWARE CONTROL RUNS FIRST: ffmpeg's CPU decoder writing the same
# rawvideo through the same filter chain must reproduce the reference md5. If
# it does not, the harness is wrong (pixel format, frame count, cropping) and
# every hardware result below is unreadable. Diagnosing the shim against a
# broken yardstick is how a session disappears.
#
#   usage: ./va-decode-test.sh [vector-name ...]     (default: the whole ladder)

set -u

DIR=$(cd "$(dirname "$0")" && pwd)
# NOT /tmp: it is a 467 MB tmpfs on this image, and one 1080p vector is 186 MB
# of raw NV12. The ladder's last rung failed as a MISMATCH the first time this
# ran, because ffmpeg reported ENOSPC and the truncated file still had an md5.
OUT=${OUT:-/var/tmp/va-out}
DRIVER=${LIBVA_DRIVER_NAME:-v4l2_request}
mkdir -p "$OUT"

export LIBVA_DRIVER_NAME=$DRIVER

hr() { printf '\n=== %s ===\n' "$1"; }

want_md5() { grep "^$1 WHOLE" "$DIR/reference-md5.txt" 2>/dev/null | awk '{print $NF}'; }
want_frames() { grep "^$1 WHOLE" "$DIR/reference-md5.txt" 2>/dev/null | awk '{print $3}'; }

# hwdownload needs the frame to stay on the "GPU" until the filter graph pulls
# it, hence -hwaccel_output_format vaapi. Asking ffmpeg for nv12 output format
# directly also works but hides where the copy happens.
decode_hw() {
  ffmpeg -hide_banner -v error -hwaccel vaapi -hwaccel_output_format vaapi \
    -i "$1" -vf 'hwdownload,format=nv12' -f rawvideo -pix_fmt nv12 -y "$2"
}

decode_sw() {
  ffmpeg -hide_banner -v error -i "$1" -f rawvideo -pix_fmt nv12 -y "$2"
}

score() {   # vector, file, label
  local v=$1 dst=$2 label=$3 md5 want frames
  if [ ! -s "$dst" ]; then
    echo "     FAIL ($label) — no output produced"
    return 1
  fi
  md5=$(md5sum "$dst" | cut -d' ' -f1)
  want=$(want_md5 "$v")
  frames=$(want_frames "$v")
  printf '     %-8s %s bytes, md5 %s\n' "$label" "$(stat -c%s "$dst")" "$md5"
  if [ -z "$want" ]; then
    echo "     no reference on file; size only"
    return 0
  fi
  if [ "$md5" = "$want" ]; then
    echo "     PASS ($label) — bit-exact against the host reference ($frames frames)"
    return 0
  fi
  echo "     MISMATCH ($label) — decoded, but not bit-exact (want $want)"
  return 1
}

hr "driver"
echo "  LIBVA_DRIVER_NAME=$LIBVA_DRIVER_NAME"
ls -l /usr/lib/aarch64-linux-gnu/dri/${DRIVER}_drv_video.so 2>&1 | sed 's/^/  /'
vainfo --display drm --device /dev/dri/renderD128 2>&1 | sed 's/^/  /'

hr "software control (the yardstick, not the subject)"
ctl=v04-1280x720-high
if [ -f "$DIR/$ctl.h264" ]; then
  decode_sw "$DIR/$ctl.h264" "$OUT/$ctl.sw.nv12" 2>&1 | sed 's/^/     /'
  if score "$ctl" "$OUT/$ctl.sw.nv12" "sw"; then
    echo "     harness is sound — hardware results below are readable"
  else
    echo "     STOP: the CPU decoder does not reproduce the reference either."
    echo "     Fix the harness before reading anything into the hardware runs."
  fi
else
  echo "  SKIP — $ctl.h264 not present"
fi

hr "hardware decode runs"
pass=0; fail=0
vectors=${*:-"v01-320x240-baseline v02-1280x720-baseline v03-1280x720-main v04-1280x720-high v05-1920x1080-high"}

for v in $vectors; do
  src="$DIR/$v.h264"
  [ -f "$src" ] || { echo "  SKIP $v (no stream)"; continue; }
  dst="$OUT/$v.nv12"
  rm -f "$dst"

  printf '\n-- %s\n' "$v"
  decode_hw "$src" "$dst" 2>&1 | sed 's/^/     /'
  if score "$v" "$dst" "hw"; then pass=$((pass+1)); else fail=$((fail+1)); fi
done

hr "kernel messages from this run"
dmesg | grep -iE "cedrus|video-codec|request" | tail -20 | sed 's/^/  /'

printf '\nVA1: %d pass, %d fail\n' "$pass" "$fail"
[ "$fail" -eq 0 ]
