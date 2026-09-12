#!/usr/bin/env bash
# Capture a WiFi baseline ON THE BOARD, in a form two runs can be diffed.
#
# This exists because the AIC8800 driver + firmware are about to be rebased from
# the 2024_0109 vendor snapshot onto 2026_0123, and without a before-picture
# there is no way to tell a regression from ordinary RF variation. The
# 2026-07-22 bench (384 MB sustained, zero SDIO errors) is the result this is
# built to reproduce and extend -- note that bench recorded that the outcome
# depended on where the board was sitting: the original FIFO_RUN_ERROR only
# appeared at a marginal -71...-80 dBm spot. So signal strength is captured as a
# first-class field. An A/B that does not record RSSI measures furniture.
#
# Two fault modes are tracked separately because only one of them can move when
# the driver/firmware changes:
#
#   sunxi-mmc FIFO bug   "cmd53 fifo error" in the log (the FIFO_RUN_ERROR /
#                        HARD_WARE_LOCKED register bits). Kernel-side,
#                        addressed by patches/kernel/0006. A CONTROL here -- if
#                        this moves after a driver swap, something is wrong with
#                        the experiment, not the driver.
#   AIC8800 fw handshake cmd timed-out -> wlan error reset flow -> DHDISDOWN=1.
#                        Driver/firmware-side. This is the one under test. Per
#                        docs/roadmap.md it only reproduces under pathological
#                        CPU/bus starvation, so absence in a normal run is
#                        expected and is NOT evidence of a fix.
#
# Output is sorted key=value, one per line, so `diff` between two runs is the
# whole comparison. Read-only by default; --load adds a sustained transfer.
#
#   usage: wifi-baseline.sh [--load] [--out FILE] [--iface wlan0]
#
#   env:   WIFI_BASELINE_URL        RX source for --load (required for --load).
#                                   Lands on real storage, not /dev/null.
#          WIFI_BASELINE_TX_TARGET  optional scp destination (user@host:/path)
#                                   for the TX leg -- the direction nothing has
#                                   measured. Needs working key-based auth.
#          WIFI_BASELINE_BYTES      transfer size, default 402653184 (384 MB,
#                                   to match the 2026-07-22 bench)
#          WIFI_BASELINE_WORKDIR    where the RX file lands, default /var/tmp.
#                                   Needs room for WIFI_BASELINE_BYTES.
#
# Run it twice -- once now, once after the rebase -- and diff the two files.
set -uo pipefail

IFACE=wlan0
DO_LOAD=0
FORCE=0
OUT=
while [ $# -gt 0 ]; do
  case "$1" in
    --load)  DO_LOAD=1 ;;
    --force) FORCE=1 ;;
    --out)   OUT=${2:?--out needs a path}; shift ;;
    --iface) IFACE=${2:?--iface needs a name}; shift ;;
    # Print the header comment block, however long it grows, rather than a
    # hardcoded line range that silently truncates when the docs are edited.
    -h|--help) awk 'NR>1{ if (/^#/) { sub(/^# ?/,""); print } else exit }' "$0"; exit 0 ;;
    *) echo "error: unknown argument: $1" >&2; exit 2 ;;
  esac
  shift
done

# Refuse to run anywhere but the target. This script degrades gracefully on a
# machine with no AIC8800 -- which means run from a dev workstation by mistake it
# exits 0 and writes a file that LOOKS like a baseline and is worthless. A
# baseline that silently describes the wrong machine is worse than no baseline,
# because the later A/B diff will be confidently meaningless.
if [ "$FORCE" != 1 ]; then
  is_target=0
  if grep -aq 'sun50i-h713' /proc/device-tree/compatible 2>/dev/null; then
    is_target=1
  else
    for m in aic8800_bsp aic8800_fdrv aic8800_btlpm; do
      [ -d "/sys/module/$m" ] && is_target=1
    done
  fi
  if [ "$is_target" != 1 ]; then
    {
      echo "error: this does not look like the H713 board."
      echo "       no 'sun50i-h713' in /proc/device-tree/compatible, and no aic8800"
      echo "       module is loaded. Refusing, because a baseline captured on the"
      echo "       wrong machine is worse than none -- it makes the later diff"
      echo "       confidently wrong."
      echo "       host=$(uname -n) kernel=$(uname -r)"
      echo "       Run this ON the board. Use --force only if you know better."
    } >&2
    exit 3
  fi
fi

BYTES=${WIFI_BASELINE_BYTES:-402653184}
WORKDIR=${WIFI_BASELINE_WORKDIR:-/var/tmp}
FW_DIR=/usr/lib/firmware/aic8800_sdio/aic8800
emit() { printf '%s=%s\n' "$1" "${2:-}"; }
# Re-read the ring buffer each call: counts are sampled before and after each
# transfer phase so a fault can be attributed to RX or TX rather than the run.
fault_count() { (dmesg 2>/dev/null || journalctl -k -b 2>/dev/null) | grep -c "$1" || true; }

# Everything is collected into a temp file first, then sorted on the way out, so
# the report is order-stable regardless of how the probes are sequenced.
TMP=$(mktemp) || { echo "error: mktemp failed" >&2; exit 1; }
trap 'rm -f "$TMP"' EXIT

{
  # --- identity: what is actually loaded right now -------------------------
  emit meta.timestamp "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  emit meta.host "$(uname -n)"
  emit id.kernel "$(uname -r)"
  for m in aic8800_bsp aic8800_fdrv aic8800_btlpm; do
    if [ -d "/sys/module/$m" ]; then
      emit "id.mod.$m" loaded
      ko=$(modinfo -n "$m" 2>/dev/null)
      [ -n "$ko" ] && [ -r "$ko" ] && \
        emit "id.mod.$m.sha256" "$(sha256sum "$ko" 2>/dev/null | cut -d' ' -f1)"
    else
      emit "id.mod.$m" ABSENT
    fi
  done

  # --- firmware: pin what the chip was actually fed -------------------------
  # The build stamp is a literal inside fmacfw; it is the only reliable way to
  # tell 2024 firmware from 2026 firmware on a running board.
  if [ -d "$FW_DIR" ]; then
    for f in "$FW_DIR"/*; do
      [ -f "$f" ] || continue
      emit "fw.$(basename "$f").sha256" "$(sha256sum "$f" | cut -d' ' -f1)"
    done
    fmac=$(ls "$FW_DIR"/fmacfw*8800d80*.bin 2>/dev/null | head -1)
    if [ -n "${fmac:-}" ] && command -v strings >/dev/null 2>&1; then
      emit fw.fmacfw.build "$(strings -n 5 "$fmac" \
        | grep -oE '(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec) [ 0-9][0-9] 20[0-9]{2}' \
        | head -1)"
    fi
  else
    emit fw.dir MISSING
  fi

  # --- link state -----------------------------------------------------------
  if [ -e "/sys/class/net/$IFACE" ]; then
    emit link.iface "$IFACE"
    emit link.present 1
    emit link.operstate "$(cat "/sys/class/net/$IFACE/operstate" 2>/dev/null)"
    emit link.mac "$(cat "/sys/class/net/$IFACE/address" 2>/dev/null)"
    emit link.mode "$(iw dev "$IFACE" info 2>/dev/null | awk '/type/{print $2; exit}')"
  else
    emit link.present 0
  fi
  command -v rfkill >/dev/null 2>&1 && \
    emit link.rfkill "$(rfkill list wifi 2>/dev/null | grep -c 'yes')"

  # --- RF conditions: without these an A/B is meaningless -------------------
  if command -v iw >/dev/null 2>&1 && [ -e "/sys/class/net/$IFACE" ]; then
    linkinfo=$(iw dev "$IFACE" link 2>/dev/null)
    if printf '%s' "$linkinfo" | grep -q 'Connected to'; then
      emit rf.associated 1
      emit rf.ssid    "$(printf '%s' "$linkinfo" | awk -F': ' '/SSID/{print $2; exit}')"
      emit rf.bssid   "$(printf '%s' "$linkinfo" | awk '/Connected to/{print $3; exit}')"
      emit rf.freq    "$(printf '%s' "$linkinfo" | awk '/freq/{print $2; exit}')"
      emit rf.signal_dbm "$(printf '%s' "$linkinfo" | awk '/signal/{print $2; exit}')"
      emit rf.rx_bitrate "$(printf '%s' "$linkinfo" | awk -F': ' '/rx bitrate/{print $2; exit}')"
      emit rf.tx_bitrate "$(printf '%s' "$linkinfo" | awk -F': ' '/tx bitrate/{print $2; exit}')"
    else
      emit rf.associated 0
    fi
    emit rf.txpower "$(iw dev "$IFACE" info 2>/dev/null | awk '/txpower/{print $2; exit}')"
    emit rf.scan_ok "$(iw dev "$IFACE" scan 2>/dev/null | grep -c '^BSS')"
  fi

  # --- AP mode: the hotspot is the shipped WiFi feature ---------------------
  if pgrep -x hostapd >/dev/null 2>&1; then
    emit ap.hostapd running
    emit ap.stations "$(iw dev "$IFACE" station dump 2>/dev/null | grep -c '^Station')"
  else
    emit ap.hostapd stopped
  fi

  # --- fault counters, since boot -------------------------------------------
  # Counted, not just present/absent, so a rate change is visible. Needs root
  # for the kernel ring buffer; a zero here with logs.readable=0 means nothing.
  logs=$(dmesg 2>/dev/null || journalctl -k -b 2>/dev/null)
  if [ -n "$logs" ]; then
    emit logs.readable 1
    # Control group -- kernel-side sunxi-mmc (patches/kernel/0006), must not
    # move on a driver swap.
    #
    # These strings are the literal dev_warn/dev_err text from patch 0006.
    # FIFO_RUN_ERROR and HARD_WARE_LOCKED -- the names used in docs/roadmap.md
    # -- are register-bit MACROS in the C source (SDXC_FIFO_RUN_ERROR) and never
    # reach the kernel log at all. Grepping for them reported 0 through a run
    # that demonstrably had a FIFO error, i.e. it silently under-reported the
    # one fault class that matters most. Real formats:
    #   "cmd53 %s error (RINT=... IDST=...), retry %d/%d"   %s = fifo | phase
    #   "cmd53 %s retry limit reached (RINT=...)"
    #   "DMA reset timeout" / "FIFO reset timeout" / "IDMA soft reset timeout"
    #
    # The error line is dev_warn_RATELIMITED, so under a storm these counts are
    # a lower bound, not an exact tally. Treat a jump from 0 as significant and
    # the absolute magnitude as approximate.
    emit fault.cmd53_fifo_error      "$(printf '%s' "$logs" | grep -c 'cmd53 fifo error')"
    emit fault.cmd53_phase_error     "$(printf '%s' "$logs" | grep -c 'cmd53 phase error')"
    emit fault.cmd53_retry_limit     "$(printf '%s' "$logs" | grep -c 'retry limit reached')"
    emit fault.mmc_reset_timeout     "$(printf '%s' "$logs" | grep -cE '(DMA|FIFO|IDMA soft) reset timeout')"
    emit fault.sched_while_atomic    "$(printf '%s' "$logs" | grep -c 'scheduling while atomic')"
    # under test -- AIC8800 firmware command handshake
    emit fault.cmd_timed_out         "$(printf '%s' "$logs" | grep -c 'cmd timed-out')"
    emit fault.wlan_error_reset      "$(printf '%s' "$logs" | grep -ci 'wlan error reset flow')"
    emit fault.cmdqueue_drain_timeout "$(printf '%s' "$logs" | grep -ci 'cmdqueue drain timeout')"
    emit fault.dhdisdown             "$(printf '%s' "$logs" | grep -c 'DHDISDOWN')"
  else
    emit logs.readable 0
  fi

  # --- optional sustained load ---------------------------------------------
  if [ "$DO_LOAD" = 1 ]; then
    if [ -z "${WIFI_BASELINE_URL:-}" ]; then
      emit load.status SKIPPED_NO_URL
    else
      emit load.url "$WIFI_BASELINE_URL"
      emit load.bytes_requested "$BYTES"
      # RX lands on real storage, not /dev/null. The documented crash recipe
      # (docs/roadmap.md) includes eMMC contention, and the reported real-world
      # failure is scp -- which writes to disk. A transfer piped to wc -c
      # exercises the radio but not the contention, i.e. the easy case.
      pre_dhd=$(fault_count 'DHDISDOWN'); pre_fifo=$(fault_count 'cmd53 fifo error')
      pre_cmd=$(fault_count 'cmd timed-out')
      mkdir -p "$WORKDIR" 2>/dev/null || true
      dst="$WORKDIR/wifi-baseline-rx.bin"
      rm -f "$dst"
      # Refuse rather than fill the storage: a wedged board with no free space
      # is a worse outcome than a skipped measurement. 64 MB headroom.
      avail=$(df -k "$WORKDIR" 2>/dev/null | awk 'NR==2{print $4*1024}')
      case "$avail" in ''|*[!0-9]*) avail=0 ;; esac
      if [ "$avail" -lt "$((BYTES + 67108864))" ]; then
      emit load.rx.status SKIPPED_LOW_SPACE
      emit load.rx.avail_bytes "$avail"
      emit load.tx.status SKIPPED_NO_RX_FILE
      else
      # The minimal rootfs ships neither curl nor wget -- only busybox, and
      # without the applet symlinks. Falling through to a missing binary yields
      # "0 bytes in 1 second", which reads exactly like a WiFi failure and is
      # not one. Name the tool, or say plainly that there isn't one.
      if command -v curl >/dev/null 2>&1; then fetch=curl
      elif command -v wget >/dev/null 2>&1; then fetch=wget
      elif command -v busybox >/dev/null 2>&1 && busybox wget --help >/dev/null 2>&1; then fetch=busybox
      else fetch=none
      fi
      emit load.rx.fetch_tool "$fetch"
      if [ "$fetch" = none ]; then
        emit load.rx.status SKIPPED_NO_FETCH_TOOL
        emit load.tx.status SKIPPED_NO_RX_FILE
        rm -f "$dst"
        got=0; secs=1
      else
      start=$(date +%s)
      case "$fetch" in
        curl)    curl -sS --max-time 3600 -r "0-$((BYTES - 1))" -o "$dst" "$WIFI_BASELINE_URL" 2>/dev/null || true ;;
        wget)    wget -q -O "$dst" "$WIFI_BASELINE_URL" 2>/dev/null || true ;;
        busybox) busybox wget -q -O "$dst" "$WIFI_BASELINE_URL" 2>/dev/null || true ;;
      esac
      sync 2>/dev/null || true
      end=$(date +%s)
      got=$(stat -c %s "$dst" 2>/dev/null || echo 0)
      secs=$((end - start)); [ "$secs" -gt 0 ] || secs=1
      case "$got" in ''|*[!0-9]*) got=0 ;; esac
      emit load.rx.bytes "$got"
      emit load.rx.seconds "$secs"
      emit load.rx.mbps "$(awk -v b="$got" -v s="$secs" 'BEGIN{printf "%.2f", (b/1048576)/s}')"
      emit load.rx.status "$([ "$got" -ge "$BYTES" ] && echo COMPLETE || echo SHORT)"
      emit load.rx.dhdisdown  "$(( $(fault_count 'DHDISDOWN') - pre_dhd ))"
      emit load.rx.cmd53_fifo_error "$(( $(fault_count 'cmd53 fifo error') - pre_fifo ))"
      emit load.rx.cmd_timeout "$(( $(fault_count 'cmd timed-out') - pre_cmd ))"
      # Re-read RF after the transfer: a big RSSI drift between start and end
      # invalidates the comparison just as surely as moving the board.
      emit load.rx.signal_dbm_after "$(iw dev "$IFACE" link 2>/dev/null | awk '/signal/{print $2; exit}')"

      # TX: the direction nothing has ever measured. Uses scp deliberately --
      # it is the exact operation reported to wedge the board, so it carries
      # the SSH crypto and the same access pattern rather than approximating
      # them. Needs key-based auth already working to WIFI_BASELINE_TX_TARGET.
      if [ -n "${WIFI_BASELINE_TX_TARGET:-}" ] && [ "$got" -gt 0 ]; then
        pre_dhd=$(fault_count 'DHDISDOWN'); pre_cmd=$(fault_count 'cmd timed-out')
        start=$(date +%s)
        scp -q -o BatchMode=yes -o StrictHostKeyChecking=no \
          "$dst" "$WIFI_BASELINE_TX_TARGET" 2>/dev/null && txok=COMPLETE || txok=FAILED
        end=$(date +%s)
        secs=$((end - start)); [ "$secs" -gt 0 ] || secs=1
        emit load.tx.bytes "$got"
        emit load.tx.seconds "$secs"
        emit load.tx.mbps "$(awk -v b="$got" -v s="$secs" 'BEGIN{printf "%.2f", (b/1048576)/s}')"
        emit load.tx.status "$txok"
        emit load.tx.dhdisdown   "$(( $(fault_count 'DHDISDOWN') - pre_dhd ))"
        emit load.tx.cmd_timeout "$(( $(fault_count 'cmd timed-out') - pre_cmd ))"
        emit load.tx.signal_dbm_after "$(iw dev "$IFACE" link 2>/dev/null | awk '/signal/{print $2; exit}')"
      else
        emit load.tx.status "$([ -n "${WIFI_BASELINE_TX_TARGET:-}" ] && echo SKIPPED_NO_RX_FILE || echo SKIPPED_NO_TARGET)"
      fi
      rm -f "$dst"
      fi
      fi
    fi
  else
    emit load.status NOT_RUN
  fi
} > "$TMP" 2>/dev/null

if [ -n "$OUT" ]; then
  sort "$TMP" > "$OUT"
  echo "wrote $OUT ($(wc -l < "$OUT") fields)" >&2
  sort "$TMP"
else
  sort "$TMP"
fi
