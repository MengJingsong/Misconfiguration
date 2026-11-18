#!/usr/bin/env bash
# One measured U3 run (design §2.5): clean start from the golden data, c reader processes, window 180 s.
# usage: bash run.sh <run-id> <heap|unset> <guard MemoryMax> <table> <set|blob|rows> <c> [extra-yaml|-] [window-s]
set -uo pipefail
RUNID=$1; HEAP=$2; GUARD=$3; TABLE=$4; MODE=$5; CC=$6; XY=${7:--}; WIN=${8:-180}
source /mydata/s4/u3-w1/harness/lib.sh
RUN=$R/runs/$RUNID; N=$RUN/node; L=$RUN/logs
[ -e "$RUN" ] && { echo "run dir exists: $RUN"; exit 2; }
mkdir -p "$N"/{data,commitlog,hints,saved_caches,cdc_raw,conf} "$L/clients"
preflight
note "RUN $RUNID heap=$HEAP guard=$GUARD table=$TABLE mode=$MODE c=$CC extra=$XY window=$WIN start_epoch=$(date +%s)"
( cd "$H" && sha256sum *.sh *.py ) > "$L/harness-sha256.txt"
cp -R "$C/conf/." "$N/conf/"
[ "$XY" = - ] && XY=""
write_yaml "$N" "$XY"
cp -a "$R/golden/data/." "$N/data/"
ulimit -n 100000
finish() {
  [ -n "${RDPID:-}" ] && kill -- -"$RDPID" 2>/dev/null; pkill -P "${RDPID:-0}" 2>/dev/null
  stop_node
  for f in "$L"/*.hprof; do [ -e "$f" ] && note "HPROF $f $(stat -c %s "$f")"; done
  rm -rf "$N/data" "$N/commitlog" "$N/hints" "$N/saved_caches" "$N/cdc_raw"
  note "END end_epoch=$(date +%s) daemons_left=$(my_daemons | wc -l)"
}
trap finish EXIT
start_node "$N" "$HEAP" "$GUARD" "u3w1-$RUNID"
start_tpstats
sleep 10
note "CLIENTS start epoch=$(date +%s.%N) table=$TABLE mode=$MODE c=$CC"
( setsid python3 -I "$H/u3client.py" readers "$TABLE" "$MODE" "$CC" "$WIN" "$L/clients/r" > "$L/readers.out" 2>&1 ) &
sleep 0.5
RDPID=$(pgrep -f "u3client.py readers $TABLE $MODE $CC $WIN $L/clients/r" | head -1)
T0=$(date +%s); OUTCOME=survived
while :; do
  sleep 1
  if ! kill -0 "$DPID" 2>/dev/null; then OUTCOME=died; note "DAEMON DIED at epoch=$(date +%s.%N) t=$(( $(date +%s) - T0 ))s"; break; fi
  [ $(( $(date +%s) - T0 )) -ge "$WIN" ] && break
done
# stop clients
for p in $(pgrep -f "u3client.py readers $TABLE $MODE $CC $WIN $L/clients/r"); do kill "$p" 2>/dev/null; done
sleep 1
for p in $(pgrep -f "u3client.py readers $TABLE $MODE $CC $WIN $L/clients/r"); do kill -9 "$p" 2>/dev/null; done
note "CLIENTS stopped epoch=$(date +%s.%N)"
if [ $OUTCOME = survived ]; then
  timeout 120 jcmd "$DPID" GC.class_histogram > "$L/histo-end.txt" 2>&1
  note "HISTO end | $(grep -E '^Total' "$L/histo-end.txt") | cells $(grep -E 'org\.apache\.cassandra\.db\.rows\.ArrayCell$' "$L/histo-end.txt" | awk '{print $2, $3}')"
else
  sleep 5
fi
note "OOMKILL $(tail -1 "$L/memory.txt")"
note "STDOUT-OOM $(grep -c 'OutOfMemoryError' "$L/node.out") | $(grep -m3 -E 'OutOfMemoryError|Dumping heap|Heap dump file created|kill -9' "$L/node.out" | tr '\n' ' ' | cut -c1-400)"
grep -n -E '^(ERROR|WARN)' "$L/system.log" | cut -c1-300 > "$L/error-warn.txt"
note "SYSLOG ERROR=$(grep -c ':ERROR' "$L/error-warn.txt") WARN=$(grep -c ':WARN' "$L/error-warn.txt") first_error=$(grep -m1 ':ERROR' "$L/error-warn.txt" | cut -c1-250)"
note "OUTCOME-RAW $OUTCOME"
