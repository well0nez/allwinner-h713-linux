#!/bin/sh
# The control this investigation never ran with adequate exposure: the display
# path hot for an hour with the video engine never opened.
#
#     MINUTES=60 sh soak-display-only.sh
#
# WHY. Every long run that crashed had cedrus decoding in it -- but so did
# nearly every long run, so that correlation is far weaker than it looked, and
# the one display-only run on record lasted 48 seconds against a bug whose crash
# latency ranges 113-848 s. This is the other arm: same kernel, same clip, same
# KMS/GBM scanout out of CMA, mpv doing *software* decode. If it crashes,
# cedrus is largely exonerated and the display path becomes the suspect.
#
# /proc/interrupts is both the guard and the exposure meter, which is why the
# heartbeat is built on it rather than on parsing mpv:
#
#   ve=  must not move.   A flat count is positive proof that no frame ever
#        reached the VE -- stronger than "we did not ask it to", because the
#        driver is built in on this kernel and cannot be removed.
#   gpu= must keep rising. If mpv dies into a still frame the run looks calm and
#        means nothing, and a soak that silently stopped exercising the thing
#        under test is exactly how you get a false "survived".
#
# Requires the panel to be up: `h713_disp auto 0x34 logo` at the U-Boot prompt
# before boot, or there is no KMS device at all.
set -u

CLIP=${CLIP:-/var/tmp/long.mp4}
MINUTES=${MINUTES:-60}
PERIOD=${PERIOD:-30}
MPVLOG=${MPVLOG:-/var/tmp/soak-display-only.mpv.log}

# Sum the per-CPU columns of every /proc/interrupts line matching a pattern.
# The column count comes from the header row rather than from "looks like a
# number": a GIC line is `32: 1234 0 0 0  GICv3  55 Level  1c0e000.video-codec`,
# and that hwirq 55 is a bare integer that would otherwise be summed in.
irqsum() {
	awk -v p="$1" 'NR == 1 { ncpu = NF; next }
	               $0 ~ p { for (i = 2; i <= ncpu + 1; i++) s += $i }
	               END { print s + 0 }' /proc/interrupts
}

# Card numbers swap between the module and built-in kernels, so ask the driver
# rather than hardcoding a minor.
CARD=${CARD:-}
if [ -z "$CARD" ]; then
	for c in /sys/class/drm/card[0-9]; do
		[ -e "$c/device/uevent" ] || continue
		if grep -q '^DRIVER=sun50i-h713-afbd' "$c/device/uevent"; then
			CARD=/dev/dri/$(basename "$c")
		fi
	done
fi
if [ -z "$CARD" ]; then
	echo "SOAK FATAL: no sun50i-h713-afbd DRM node."
	echo "SOAK        the panel was not brought up in U-Boot (h713_disp auto 0x34 logo)."
	exit 1
fi
[ -r "$CLIP" ] || { echo "SOAK FATAL: no clip at $CLIP"; exit 1; }

echo "SOAK start kernel=$(uname -r) card=$CARD clip=$CLIP minutes=$MINUTES"
echo "SOAK cmdline: $(cat /proc/cmdline)"
grep -E 'video-codec|panfrost|h713-afbd|decd' /proc/interrupts | sed 's/^/SOAK irq0 /'

VE0=$(irqsum 'video-codec')
GPU0=$(irqsum 'panfrost')
PREVGPU=$GPU0

# The first run of this control died here and told us almost nothing: mpv
# vanished at ~250 s and the script stopped, so an hour's exposure became four
# minutes. Worse, `dmesg` was silent and that reads as exoneration -- but
# exception-trace defaults to 0 on this rootfs, so the kernel would not have
# printed a SIGSEGV even if one happened. Turn it on and say so in the log,
# because "no fault reported" is only evidence when faults would be reported.
echo 1 > /proc/sys/debug/exception-trace 2>/dev/null
echo "SOAK exception-trace=$(cat /proc/sys/debug/exception-trace 2>/dev/null)"

start_mpv() {
	mpv --hwdec=no --vo=gpu --gpu-context=drm --drm-device="$CARD" \
	    --loop-file=inf --no-audio --input-terminal=no \
	    "$CLIP" >> "$MPVLOG" 2>&1 < /dev/null &
	MPID=$!
}

# 139 = 128 + SIGSEGV. mpv prints `Exiting... (reason)` on every ordinary
# termination including errors, so a status with no such line is a signal.
signame() {
	case "$1" in
	139) echo "SIGSEGV" ;;
	135) echo "SIGBUS" ;;
	134) echo "SIGABRT" ;;
	137) echo "SIGKILL" ;;
	136) echo "SIGFPE" ;;
	0)   echo "clean-exit" ;;
	*)   echo "status-$1" ;;
	esac
}

: > "$MPVLOG"
start_mpv

T0=$(date +%s)
END=$((T0 + MINUTES * 60))
DEATHS=0

# mpv dying must not end the run. The point of this control is an hour of
# *display* exposure; restarting keeps that accumulating, and each death is
# recorded with its signal, which turns one anecdote into a rate.
while [ "$(date +%s)" -lt "$END" ]; do
	sleep "$PERIOD"
	t=$(($(date +%s) - T0))
	if ! kill -0 "$MPID" 2>/dev/null; then
		wait "$MPID"
		rc=$?
		DEATHS=$((DEATHS + 1))
		echo "SOAK MPV-DIED #${DEATHS} by t=${t}s rc=${rc} $(signame $rc)"
		tr '\r' '\n' < "$MPVLOG" | grep -av '^[[:space:]]*$' | tail -1 | sed 's/^/SOAK   last: /'
		start_mpv
	fi
	ve=$(irqsum 'video-codec')
	gpu=$(irqsum 'panfrost')
	cma=$(awk '/CmaFree/ { print $2 }' /proc/meminfo)
	echo "SOAK t=${t}s ve=${ve} ve_delta=$((ve - VE0)) gpu=${gpu} gpu_rate=$(((gpu - PREVGPU) / PERIOD))/s cma=${cma}kB deaths=${DEATHS}"
	PREVGPU=$gpu
done

kill "$MPID" 2>/dev/null
sleep 2
ve=$(irqsum 'video-codec')
gpu=$(irqsum 'panfrost')
echo "SOAK DONE t=$(($(date +%s) - T0))s deaths=${DEATHS} ve_delta=$((ve - VE0)) gpu_delta=$((gpu - GPU0))"
