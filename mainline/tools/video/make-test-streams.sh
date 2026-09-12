#!/usr/bin/env bash
# Generate the H.264 test-vector ladder for H713 video-decode bring-up, plus a
# host-decoded reference frame set for each vector.
#
# The ladder exists because "the decoder produced output" and "the decoder
# produced the RIGHT output" are different claims, and this project has been
# burned by the gap before. Each step adds exactly one coding feature, so a
# failure names the feature that broke it instead of just failing.
#
#   v01  320x240   Constrained Baseline   I+P, CAVLC, no B      minimum viable
#   v02  1280x720  Constrained Baseline   I+P, CAVLC, no B      panel-native
#   v03  1280x720  Main                   + B-frames, CABAC     reference reorder
#   v04  1280x720  High                   + 8x8 transform       what real files use
#   v05  1920x1080 High                   real-world clip       integration test
#   h01  640x480   HEVC Main              8-bit                 HEVC minimum
#   h02  1280x720  HEVC Main              8-bit                 HEVC panel-native
#
# Streams are Annex-B elementary (.h264/.h265) because the target has no
# container demuxer in the decode path -- keep the test about the decoder.
#
# References are NV12, which is what cedrus emits, so a target-side capture can
# be compared byte-for-byte rather than eyeballed.
set -euo pipefail

PROJECT_ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)
OUT_DIR=${1:-$PROJECT_ROOT/local/video-test}
REAL_CLIP=${REAL_CLIP:-$PROJECT_ROOT/local/Madame Leota Complete Audio Loop - Edit.mp4}

command -v ffmpeg >/dev/null || { echo "error: ffmpeg not found on host" >&2; exit 1; }

mkdir -p "$OUT_DIR"
cd "$OUT_DIR"

# Deterministic synthetic source: testsrc2 is reproducible frame-for-frame, so
# the reference YUV is a fixed artifact rather than something that drifts
# between runs. Motion matters -- a static scene never exercises inter
# prediction, which is most of what a decoder does.
gen() {
  local name=$1 w=$2 h=$3 frames=$4 profile=$5
  shift 5

  echo "==> $name  (${w}x${h}, $frames frames, $profile)"
  ffmpeg -hide_banner -loglevel error -y \
    -f lavfi -i "testsrc2=size=${w}x${h}:rate=30" -frames:v "$frames" \
    -pix_fmt yuv420p -c:v libx264 -profile:v "$profile" "$@" \
    -f h264 "$name.h264"

  # Host software decode -> NV12 reference. This is the ground truth the
  # target's output is scored against.
  ffmpeg -hide_banner -loglevel error -y \
    -i "$name.h264" -pix_fmt nv12 -f rawvideo "$name.nv12"

  printf '    stream %s bytes, reference %s bytes (%s frames of %d)\n' \
    "$(stat -c%s "$name.h264")" "$(stat -c%s "$name.nv12")" \
    "$(( $(stat -c%s "$name.nv12") / (w * h * 3 / 2) ))" "$frames"
}

# HEVC, same shape: deterministic source, Annex-B elementary stream, NV12
# reference decoded on the host. The VE decodes H.265 as well as H.264 -- both
# bit-exact -- and these are the vectors that established it.
#
# 10-bit is deliberately absent. Main10 does not decode: mainline cedrus (6.18)
# exposes no 10-bit capture format at all, so nothing can negotiate one, and the
# pipeline reaches EOS having produced zero frames. See docs/vaapi-scope.md.
gen_hevc() {
  local name=$1 w=$2 h=$3 frames=$4 profile=$5
  shift 5

  echo "==> $name  (${w}x${h}, $frames frames, $profile)"
  ffmpeg -hide_banner -loglevel error -y \
    -f lavfi -i "testsrc2=size=${w}x${h}:rate=25" -frames:v "$frames" \
    -pix_fmt yuv420p -c:v libx265 -profile:v "$profile" \
    -x265-params "log-level=error:keyint=10" "$@" \
    -f hevc "$name.h265"

  ffmpeg -hide_banner -loglevel error -y \
    -i "$name.h265" -pix_fmt nv12 -f rawvideo "$name.nv12"

  printf '    stream %s bytes, reference %s bytes (%s frames of %d)\n' \
    "$(stat -c%s "$name.h265")" "$(stat -c%s "$name.nv12")" \
    "$(( $(stat -c%s "$name.nv12") / (w * h * 3 / 2) ))" "$frames"
}

# v01 -- the minimum. Constrained Baseline: no B-frames, no CABAC, no 8x8.
# If this does not decode, nothing else will, and the fault is fundamental.
gen v01-320x240-baseline 320 240 8 baseline \
  -x264-params "bframes=0:cabac=0:ref=1:weightp=0:8x8dct=0"

# v02 -- same coding tools at panel resolution. Separates "does not decode" from
# "does not decode at this size" (stride, buffer sizing, IOMMU mapping).
gen v02-1280x720-baseline 1280 720 60 baseline \
  -x264-params "bframes=0:cabac=0:ref=1:weightp=0:8x8dct=0"

# v03 -- adds B-frames and CABAC. Exercises reference list construction and
# output reordering, the part a stateless decoder's userspace gets wrong first.
gen v03-1280x720-main 1280 720 60 main \
  -x264-params "bframes=2:cabac=1:ref=3:8x8dct=0"

# v04 -- adds the 8x8 transform. This is what real-world High-profile files use.
gen v04-1280x720-high 1280 720 60 high \
  -x264-params "bframes=2:cabac=1:ref=3:8x8dct=1"

# h01/h02 -- HEVC Main, 8-bit. Both verified bit-exact against these references
# on the bench board (2026-08-16), through gst v4l2slh265dec with no driver
# changes, at ~550 fps for 720p.
gen_hevc h01-640x480-main   640 480 25 main
gen_hevc h02-1280x720-main 1280 720 25 main

# v05 -- the real clip, first 60 frames, as the integration test. Not synthetic,
# so no exact reference; scored by eye on the panel and by PSNR against a host
# software decode of the same stream.
if [ -f "$REAL_CLIP" ]; then
  echo "==> v05-1920x1080-high  (real clip, first 60 frames)"
  ffmpeg -hide_banner -loglevel error -y -i "$REAL_CLIP" \
    -frames:v 60 -c:v copy -bsf:v h264_mp4toannexb -f h264 v05-1920x1080-high.h264
  ffmpeg -hide_banner -loglevel error -y -i v05-1920x1080-high.h264 \
    -pix_fmt nv12 -f rawvideo v05-1920x1080-high.nv12
  printf '    stream %s bytes, reference %s bytes\n' \
    "$(stat -c%s v05-1920x1080-high.h264)" "$(stat -c%s v05-1920x1080-high.nv12)"
else
  echo "==> v05 skipped: real clip not found at $REAL_CLIP"
fi

echo
echo "Test vectors in $OUT_DIR:"
ls -la "$OUT_DIR"
