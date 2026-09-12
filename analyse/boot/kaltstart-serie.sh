#!/usr/bin/env bash
# 20 Kaltstarts vom eMMC (Paket R5). Jeder Lauf: Steckdose aus/an, UART mitlesen,
# auf "login:" warten, dann per ssh die Kernpunkte abfragen.
set -u
S=/tmp/claude-1000/-opt-Projekte-h713/ab4c2901-1922-498d-8a11-939de2cf8014/scratchpad
D=root@192.168.8.143
SSH="ssh -o BatchMode=yes -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -o ConnectTimeout=5"
N=${1:-20}
ok=0; fail=0
printf '%-4s %-7s %-9s %-7s %-8s %-9s %s\n' "#" "Boot" "Quelle" "MIPS" "Panel" "h713-tv" "Bemerkung"
for i in $(seq 1 "$N"); do
  L=$S/r5-$i.txt
  sudo -n timeout 200 python3 tools/uart-passiv.py "$L" 180 --bis "login:" >/dev/null 2>&1 &
  UP=$!
  sleep 2
  ~/.local/bin/sonoff_ctl restart --host 192.168.8.179 --wait 8 --timeout 25 >/dev/null 2>&1
  wait $UP
  T=$(sudo cat "$L" 2>/dev/null | tr -d '\r' | tr -d '\000')
  boot=$(grep -qa 'login:' <<<"$T" && echo ok || echo NEIN)
  quelle=$(grep -qa 'root=PARTLABEL=hy310-rootfs' <<<"$T" && echo emmc || (grep -qa 'root=/dev/nfs' <<<"$T" && echo NETZ || echo "?"))
  mips=$(grep -qa 'firmware identity accepted' <<<"$T" && echo ok || echo NEIN)
  panel=$(grep -qa 'timing latched' <<<"$T" && echo ok || echo NEIN)
  tv="?"
  for t in $(seq 1 12); do $SSH $D true 2>/dev/null && break; sleep 5; done
  for t in $(seq 1 10); do tv=$($SSH $D 'systemctl is-active h713-tv@video1' 2>/dev/null || echo "?"); [ "$tv" = active ] && break; sleep 4; done
  bem=""
  grep -qa 'Kernel panic\|Unable to mount root' <<<"$T" && bem="PANIC"
  grep -qa 'data error cmd' <<<"$T" && bem="$bem eMMC-Datenfehler"
  if [ "$boot$quelle$mips$panel$tv" = "okemmcokokactive" ]; then ok=$((ok+1)); else fail=$((fail+1)); bem="$bem <-- ABWEICHUNG"; fi
  printf '%-4s %-7s %-9s %-7s %-8s %-9s %s\n' "$i" "$boot" "$quelle" "$mips" "$panel" "$tv" "$bem"
done
echo "---"
echo "Ergebnis: $ok von $N sauber, $fail Abweichungen"
