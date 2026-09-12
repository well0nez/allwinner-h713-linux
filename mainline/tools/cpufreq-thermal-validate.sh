#!/bin/sh
# Validate H713 CPU DVFS and the CPU thermal-cooling path.
# Runs on the target as root. It changes VDD-CPU only through cpufreq OPPs and
# never writes a regulator directly or changes thermal trip points.
set -eu

DO_STRESS=0
SECS=300
INTERVAL=5
STOP_C=85

while [ "$#" -gt 0 ]; do
	case "$1" in
	--stress) DO_STRESS=1; shift ;;
	--secs) SECS=$2; shift 2 ;;
	--interval) INTERVAL=$2; shift 2 ;;
	--stop-c) STOP_C=$2; shift 2 ;;
	*) echo "unknown argument: $1" >&2; exit 2 ;;
	esac
done

POL=/sys/devices/system/cpu/cpufreq/policy0
TZ=${THERMAL_ZONE:-/sys/class/thermal/thermal_zone0}

say() { printf '%s\n' "$*"; }
die() { printf 'FAIL: %s\n' "$*" >&2; exit 1; }
read_temp_mc() { cat "$TZ/temp"; }
read_vdd_uv() {
	for r in /sys/class/regulator/regulator.*; do
		[ "$(cat "$r/name" 2>/dev/null)" = vdd-cpu ] || continue
		cat "$r/microvolts"
		return 0
	done
	printf '?\n'
}

[ "$(id -u)" -eq 0 ] || die "run as root"
[ -d "$POL" ] || die "missing cpufreq policy0"
[ -d "$TZ" ] || die "missing $TZ"
[ -r "$POL/scaling_available_frequencies" ] || die "no discrete OPP list"
[ -w "$POL/scaling_governor" ] || die "cpufreq policy is not writable"

ORIG_GOV=$(cat "$POL/scaling_governor")
ORIG_FREQ=$(cat "$POL/scaling_cur_freq")
LOAD_PIDS=""
cleanup() {
	if [ -n "$LOAD_PIDS" ]; then
		for pid in $LOAD_PIDS; do kill "$pid" 2>/dev/null || true; done
		for pid in $LOAD_PIDS; do wait "$pid" 2>/dev/null || true; done
		LOAD_PIDS=""
	fi
	# Restore both state variables; this also handles an original userspace
	# governor without leaving the CPU pinned at the test maximum.
	echo userspace > "$POL/scaling_governor" 2>/dev/null || true
	echo "$ORIG_FREQ" > "$POL/scaling_setspeed" 2>/dev/null || true
	echo "$ORIG_GOV" > "$POL/scaling_governor" 2>/dev/null || true
}
trap cleanup EXIT INT TERM HUP

FREQS=$(cat "$POL/scaling_available_frequencies")
SORTED=$(for f in $FREQS; do echo "$f"; done | sort -n)
MAXF=$(printf '%s\n' "$SORTED" | tail -n 1)

say "driver=$(cat "$POL/scaling_driver")"
say "original_governor=$ORIG_GOV"
say "frequencies_khz=$FREQS"
say "thermal_zone=$(cat "$TZ/type")"

WARM_MC=""
for type_file in "$TZ"/trip_point_*_type; do
	[ -r "$type_file" ] || continue
	n=${type_file%_type}
	type=$(cat "$type_file")
	temp=$(cat "${n}_temp")
	hyst=$(cat "${n}_hyst" 2>/dev/null || echo 0)
	say "trip=$(basename "$n") type=$type temp_mC=$temp hyst_mC=$hyst"
	if [ "$type" = passive ] && { [ -z "$WARM_MC" ] || [ "$temp" -lt "$WARM_MC" ]; }; then
		WARM_MC=$temp
	fi
done
[ -n "$WARM_MC" ] || die "no passive CPU thermal trip"

CPU_CDEV=0
for link in "$TZ"/cdev*; do
	[ -L "$link" ] || continue
	type=$(cat "$link/type" 2>/dev/null || true)
	trip=$(cat "${link}_trip_point" 2>/dev/null || echo '?')
	say "cooling_device=$(basename "$link") type=$type trip=$trip"
	case "$type" in cpufreq-*) CPU_CDEV=1 ;; esac
done
[ "$CPU_CDEV" -eq 1 ] || die "CPU thermal zone has no cpufreq cooling-device binding"

echo userspace > "$POL/scaling_governor" || die "userspace governor unavailable"

say "DVFS sweep (VDD-CPU changes only through cpufreq OPP selection):"
for f in $SORTED $(printf '%s\n' "$SORTED" | sort -nr); do
	echo "$f" > "$POL/scaling_setspeed"
	sleep 1
	actual=$(cat "$POL/scaling_cur_freq")
	temp=$(read_temp_mc)
	uv=$(read_vdd_uv)
	printf '  requested=%-8s actual=%-8s voltage_uV=%-7s temp=%s C\n' \
		"$f" "$actual" "$uv" "$((temp / 1000))"
	[ "$actual" = "$f" ] || die "requested $f kHz but reached $actual kHz"
done
say "PASS: every DVFS OPP was reached in both directions"

if [ "$DO_STRESS" -eq 0 ]; then
	say "PASS: cpufreq cooling device is bound; use --stress for a sustained maximum-frequency thermal run"
	exit 0
fi

echo "$MAXF" > "$POL/scaling_setspeed"
i=0
while [ "$i" -lt "$(nproc)" ]; do
	yes >/dev/null &
	LOAD_PIDS="$LOAD_PIDS $!"
	i=$((i + 1))
done

say "stress: ${SECS}s at requested ${MAXF} kHz; stop threshold ${STOP_C} C"
ELAPSED=0
PEAK_MC=0
THROTTLED=0
REACHED_WARM=0
while [ "$ELAPSED" -lt "$SECS" ]; do
	sleep "$INTERVAL"
	ELAPSED=$((ELAPSED + INTERVAL))
	temp=$(read_temp_mc)
	actual=$(cat "$POL/scaling_cur_freq")
	policy_max=$(cat "$POL/scaling_max_freq")
	uv=$(read_vdd_uv)
	[ "$temp" -gt "$PEAK_MC" ] && PEAK_MC=$temp
	[ "$temp" -ge "$WARM_MC" ] && REACHED_WARM=1
	if [ "$actual" -lt "$MAXF" ] || [ "$policy_max" -lt "$MAXF" ]; then
		THROTTLED=1
	fi
	printf '  elapsed=%-4ss freq=%-8s voltage_uV=%-7s policy_max=%-8s temp=%s C\n' \
		"$ELAPSED" "$actual" "$uv" "$policy_max" "$((temp / 1000))"
	if [ "$temp" -ge $((STOP_C * 1000)) ]; then
		die "temperature reached the ${STOP_C} C stop threshold"
	fi
done

cleanup
LOAD_PIDS=""
say "peak_temperature=$((PEAK_MC / 1000)) C"
if [ "$REACHED_WARM" -eq 1 ]; then
	[ "$THROTTLED" -eq 1 ] || die "crossed the passive trip without observing cpufreq throttling"
	say "PASS: passive trip was crossed and cpufreq throttling was observed"
else
	say "PASS: sustained maximum load remained below the first passive trip"
fi
