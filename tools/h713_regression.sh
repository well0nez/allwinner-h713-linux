#!/bin/sh
set -eu

LOG=/tmp/h713_regression.log
: > "$LOG"

run() {
  echo "== $*" | tee -a "$LOG"
  "$@" >>"$LOG" 2>&1
}

echo "[INFO] Starting H713 regression" | tee -a "$LOG"
run pkill -x modetest || true
run pkill -x h713_kms_test || true
run rmmod h713_drm || true
run insmod /tmp/h713_drm.ko

# Gate 1: reopen stability
run /tmp/h713_kms_test /dev/dri/card1 --hold-seconds 2
run /tmp/h713_kms_test /dev/dri/card1 --hold-seconds 2

# Gate 2: module reload stability
run rmmod h713_drm
run insmod /tmp/h713_drm.ko
run /tmp/h713_kms_test /dev/dri/card1 --hold-seconds 2

# Gate 3: modetest resource visibility
run modetest -M h713 -c
run modetest -M h713 -p

# Gate 4: bidirectional PRIME roundtrip + scanout
run /tmp/h713_kms_test /dev/dri/card1 --prime /dev/dri/card0 --hold-seconds 2

echo "[PASS] H713 regression gates passed" | tee -a "$LOG"
