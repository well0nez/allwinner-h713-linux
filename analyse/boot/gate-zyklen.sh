#!/usr/bin/env bash
# gate-zyklen.sh N -- N Kaltstarts ueber die Steckdose, jeder mit Tastendruck.
# Prueft zweierlei: das Gate haelt (Geraet kommt NICHT von allein hoch) und die
# Taste startet es. Voraussetzung: A-auf-A-Kabel ab (sonst speist USB weiter).
set -u
N=${1:-20}; HOST=${HOST:-192.168.8.179}; ZIEL=${ZIEL:-192.168.8.142}
LOG=${LOG:-/opt/Projekte/h713/analyse/boot/p6-gate-zyklen-$(date +%Y%m%d-%H%M).txt}
echo "Gate-Zyklen, $(date '+%Y-%m-%d %H:%M'), Ziel $ZIEL, Steckdose $HOST" | tee "$LOG"
echo "# Zyklus | Bereitschaft gehalten | Sekunden bis SSH nach Tastendruck" | tee -a "$LOG"
gut=0
for i in $(seq 1 "$N"); do
	sonoff_ctl restart --host "$HOST" --wait 5 >/dev/null 2>&1 || { echo "$i FEHLER Steckdose" | tee -a "$LOG"; break; }
	sleep 25
	if ping -c1 -W2 "$ZIEL" >/dev/null 2>&1; then
		echo "$i  GATE HAT NICHT GEHALTEN -- Geraet kam ohne Taste hoch" | tee -a "$LOG"; break
	fi
	t0=$(date +%s); auf=0
	for _ in $(seq 1 150); do
		sleep 2
		if ping -c1 -W1 "$ZIEL" >/dev/null 2>&1; then auf=1; break; fi
	done
	t=$(( $(date +%s) - t0 ))
	if ((auf)); then printf '%2d  ja  %3d s\n' "$i" "$t" | tee -a "$LOG"; gut=$((gut+1))
	else echo "$i  keine Antwort binnen 300 s -- abgebrochen" | tee -a "$LOG"; break; fi
done
echo "Ergebnis: $gut von $N Zyklen sauber" | tee -a "$LOG"
