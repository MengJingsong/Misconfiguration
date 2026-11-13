#!/usr/bin/env bash
# C2 resumable batch: runs each line of an arms file through run-arm.sh, skipping labels already done
# (logs/<label>/gcwin.txt exists). Line format: <label> <arm> <heap> <steps> [maxReads] ; optional env prefix
# DIRECT=... before the label is honoured (e.g. "DIRECT=7936M X-S-7936 B 2G slow;64;32:120;180;2048").
#   batch.sh <arms-file>     (stops starting new lifetimes after STOP_AT, default 20:15 UTC)
H=$(cd "$(dirname "$0")" && pwd); C=$(cd "$H/.." && pwd)
STOP_AT=${STOP_AT:-20:15}
while read -r line; do
  [[ -z $line || $line == \#* ]] && continue
  env=(); while [[ $line == *=*' '* && ${line%% *} == *=* ]]; do env+=("${line%% *}"); line=${line#* }; done
  read -r L ARM HEAP STEPS MAXR <<< "$line"
  [ -f "$C/logs/$L/gcwin.txt" ] && { echo "skip $L (done)"; continue; }
  [ "$(date -u +%H:%M)" \> "$STOP_AT" ] && { echo "STOP_AT $STOP_AT reached before $L"; break; }
  env "${env[@]}" bash "$H/run-arm.sh" "$L" "$ARM" "$HEAP" "$STEPS" $MAXR > "$C/logs/controller-$L.out" 2>&1 < /dev/null
  echo "$(date -u +%FT%TZ) $L: $(grep -h 'VICTIM DEAD\|SUMMARY' "$C/logs/controller-$L.out" | head -2 | tr '\n' ' ') $(cat "$C/logs/$L/gcwin.txt" 2>/dev/null)"
  ssh -n apt140 'pgrep -f "[C]assandraDaemon" >/dev/null && echo "WARN: cassandra still running"'; ssh -n apt138 'pgrep -f "[s]lowread|[C]2Load" >/dev/null && echo "WARN: client still running"'
done < "$1"
echo "BATCH DONE $(date -u +%FT%TZ)"
