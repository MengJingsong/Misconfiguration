#!/usr/bin/env bash
# B1 OOM probe (arm P): sustained v5 large requests, no forced GC during the load.
#   run-probe.sh <label> <unmod|patched> <proto> <bytes> <procs> <window> <seconds> <heap> <direct>
# <procs> client processes (one connection each) for <seconds>; readings every 60 s (no GC); at the end
# idle 20 s, reading "end-pre", GC.run, reading "end-post". The victim dies -> "VICTIM DEAD".
set -uo pipefail
L=$1 B=$2 P=$3 BYTES=$4 N=$5 W=$6 S=$7 HEAP=$8 DIRECT=$9
V="ssh apt140 bash /mydata/b1/harness/victim-ctl.sh"
log(){ echo "[$(date -u '+%FT%TZ')] $*"; }
log "PROBE $L build=$B proto=$P bytes=$BYTES procs=$N window=$W secs=$S heap=$HEAP direct=$DIRECT"
ssh apt138 "mkdir -p /mydata/b1/runs/$L"
$V start "$L" "$B" "$HEAP" "$DIRECT" || exit 1
$V ready "$L" || { $V stop "$L"; exit 1; }
ssh apt138 python3 /mydata/b1/harness/b1client.py schema
sleep 20
$V read "$L" p0-pre; $V gc "$L"; sleep 5; $V read "$L" p0-post
ssh apt138 "cd /mydata/b1/runs/$L && for i in \$(seq 1 $N); do (python3 /mydata/b1/harness/b1client.py cycle $P $BYTES 100000000 $W \$i $S > client-\$i.log 2>&1 &); done"
t0=$(date +%s); m=0
while [ $(( $(date +%s) - t0 )) -lt $((S + 30)) ]; do
  sleep 60; m=$((m+1))
  if [ "$($V alive "$L")" != ALIVE ]; then log "VICTIM DEAD at minute $m"; break; fi
  $V read "$L" "m$m" | cut -d, -f1-4,9,12,14,17
done
ssh apt138 "pgrep -f 'b1client[.]py cycle' >/dev/null && { sleep 30; pkill -f 'b1client[.]py cycle'; }; cat /mydata/b1/runs/$L/client-*.log | grep -v '^$' | tail -n $N"
if [ "$($V alive "$L")" = ALIVE ]; then
  sleep 20; $V read "$L" end-pre; $V gc "$L"; sleep 5; $V read "$L" end-post
  # allocator retention check: glibc trim (JDK diagnostic command), then one more reading
  ssh apt140 "jcmd \$(cat /mydata/b1/runs/$L/cass.pid) System.trim_native_heap 2>&1 | tail -2"; sleep 3; $V read "$L" end-trim
fi
ssh apt140 "grep -h 'java.lang.OutOfMemoryError\|failed to allocate' /mydata/b1/runs/$L/logs/system.log /mydata/b1/runs/$L/stdout.log | head -5; dmesg 2>/dev/null | tail -3; ls /mydata/b1/runs/$L | grep -i 'hprof\|hs_err'"
$V stop "$L"
log "END $L"
