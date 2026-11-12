#!/usr/bin/env bash
# B1 controller (runs on the session host; ssh to apt140 victim and apt138 client). One lifetime per call.
#   run-arm.sh <label> <unmod|patched> <proto> <bytes> <cycles> <R> <heap> <direct> [window=4] [idle=20]
# Cycle k: R requests (one connection, <window> in flight), idle, reading "c<k>-pre", jcmd GC.run, 5 s, "c<k>-post".
# Output: victim /mydata/b1/runs/<label>/ (samples.csv, readings.csv, logs/), client /mydata/b1/runs/<label>/client.log.
set -uo pipefail
L=$1 B=$2 P=$3 BYTES=$4 K=$5 R=$6 HEAP=$7 DIRECT=$8 W=${9:-4} IDLE=${10:-20}
V="ssh apt140 bash /mydata/b1/harness/victim-ctl.sh"
CL="ssh apt138 python3 /mydata/b1/harness/b1client.py"
log(){ echo "[$(date -u '+%FT%TZ')] $*"; }
log "ARM $L build=$B proto=$P bytes=$BYTES cycles=$K R=$R heap=$HEAP direct=$DIRECT window=$W idle=$IDLE"
ssh apt138 "mkdir -p /mydata/b1/runs/$L"
$V start "$L" "$B" "$HEAP" "$DIRECT" || exit 1
$V ready "$L" || { $V stop "$L"; exit 1; }
$CL schema
sleep "$IDLE"
$V read "$L" c0-pre; $V gc "$L"; sleep 5; $V read "$L" c0-post
for k in $(seq 1 "$K"); do
  out=$($CL cycle "$P" "$BYTES" "$R" "$W" "$k" 2>&1 | tail -1)
  echo "c$k $out" | ssh apt138 "cat >> /mydata/b1/runs/$L/client.log"
  log "c$k $out"
  if [ "$($V alive "$L")" != ALIVE ]; then log "VICTIM DEAD after cycle $k"; break; fi
  sleep "$IDLE"
  $V read "$L" "c$k-pre"; $V gc "$L"; sleep 5; $V read "$L" "c$k-post"
done
ssh apt140 "grep -c 'java.lang.OutOfMemoryError\|failed to allocate' /mydata/b1/runs/$L/logs/system.log /mydata/b1/runs/$L/stdout.log; grep -m3 'LEAK' /mydata/b1/runs/$L/logs/system.log"
$V stop "$L"
log "END $L"
