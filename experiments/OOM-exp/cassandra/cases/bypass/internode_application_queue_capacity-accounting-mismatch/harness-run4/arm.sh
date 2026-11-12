#!/usr/bin/env bash
# One run-4 arm from a clean start: measured coordinator S, two slow replicas V1/V2 (distinct ranges,
# both on the dm-delay disk), fast replica F, Java client to S only.
#   arm.sh <name> <map|blob> <size> <S_xmx> <stall_ms> [yaml key=value ... for all instances]
# env: SESS (client sessions to S, 256 in flight each; default 8), LOAD (s, default 150),
#      STALL_AT (s, default 20), HEAPDUMP (1/0), BUILD (patched build), HIST_AT (s; if set, one
#      GC.class_histogram of S at that time -- intrusive, diagnostic arms only), RATE (total client
#      writes/s cap, run-4 B6Load; unset = uncapped run-2 client)
# Timeline: load LOAD s; at t=STALL_AT disk write delay := stall_ms; at end of load := 0; observe 60 s.
set -uo pipefail
H=$(cd "$(dirname "$0")" && pwd); H2=$H/../harness-run2; H3=$H/../harness-run3
NAME=$1 KIND=$2 SIZE=$3 SX=$4 STALL=$5; shift 5
SESS=${SESS:-8} LOAD=${LOAD:-150} STALL_AT=${STALL_AT:-20}
R=/mydata/b6/runs4/$NAME; rm -rf "$R"; mkdir -p "$R"
foreign(){ echo "$(date +%T) $1 loadavg=$(cut -d" " -f1-3 /proc/loadavg) foreign_java=$(pgrep -f java | while read p; do tr "\\0" " " < /proc/$p/cmdline 2>/dev/null | grep -q "ring4\\|B6Load" || echo -n "$p "; done)" >> "$R/foreign.txt"; }
foreign start
echo "args: $KIND $SIZE S=$SX stall=$STALL rate=${RATE:-none} sess=$SESS load=$LOAD stall_at=$STALL_AT build=${BUILD:-default} heapdump=${HEAPDUMP:-1} extra=[$*]" > "$R/args.txt"
"$H/ring-up.sh" "$SX" "$@" > "$R/ring-up.log" 2>&1
grep -q "schema ok" "$R/ring-up.log" || { echo "$NAME: RING FAIL"; "$H/ctl.sh" stop all >/dev/null; exit 1; }
SPID=$(cat /mydata/b6/ring4/S/cass.pid)
HOSTS=$(for i in $(seq "$SESS"); do printf '127.0.0.13,'; done); HOSTS=${HOSTS%,}
"$H/sample.sh" "$R" 3 2>/dev/null & SMP=$!
if [ -n "${RATE:-}" ]; then "$H/load4.sh" run "$KIND" "$SIZE" 256 "$LOAD" 0 "$HOSTS" "$RATE" > "$R/load.log" 2>&1 & LP=$!
else "$H2/load.sh" run "$KIND" "$SIZE" 256 "$LOAD" 0 "$HOSTS" > "$R/load.log" 2>&1 & LP=$!; fi
T0=$(date +%s)
sleep "$STALL_AT"; [ "$STALL" -gt 0 ] && "$H2/slowdisk.sh" set "$STALL" >> "$R/stall.log"
if [ -n "${HIST_AT:-}" ]; then
  sleep $(( HIST_AT - STALL_AT )); kill -0 $SPID 2>/dev/null && { date +%s > "$R/hist.ts"; timeout 120 jcmd $SPID GC.class_histogram > "$R/S-histogram.txt" 2>&1; }
fi
wait $LP; "$H2/slowdisk.sh" set 0 >> "$R/stall.log"
sleep 60
# a JVM that hit OOM may still be writing its heap dump before OnOutOfMemoryError kills it
for _ in $(seq 100); do
  kill -0 $SPID 2>/dev/null || break
  grep -q ReportJavaOutOfMemory /mydata/b6/ring4/S/logs/gc.log* 2>/dev/null || break; sleep 3
done
kill $SMP 2>/dev/null; wait $SMP 2>/dev/null
mkdir -p "$R/S-logs"; cp -p /mydata/b6/ring4/S/logs/system.log /mydata/b6/ring4/S/logs/debug.log /mydata/b6/ring4/S/logs/launch.log /mydata/b6/ring4/S/logs/gc.log* "$R/S-logs/" 2>/dev/null
for v in V1 V2 F; do mkdir -p "$R/$v-logs"; cp -p /mydata/b6/ring4/$v/logs/gc.log* "$R/$v-logs/" 2>/dev/null; done
if kill -0 $SPID 2>/dev/null; then st=alive; else st=DEAD; fi
oom=$(grep -c "java.lang.OutOfMemoryError" "$R/S-logs/system.log" 2>/dev/null)
mv /mydata/b6/ring4/S/dumps/*.hprof "$R/" 2>/dev/null && dump=kept || dump=none
SM=$(awk -v x="$SX" 'BEGIN{u=substr(x,length(x)); v=substr(x,1,length(x)-1); print (u=="G"? v*1024 : v)}')
echo "S $st OOMError_in_system.log=$oom dump=$dump | $("$H3/gcpeak.sh" "$R/S-logs" "$SM")" > "$R/outcome.txt"
foreign end
"$H/ctl.sh" stop all > "$R/stop.log" 2>&1
echo "$NAME ($KIND $SIZE S=$SX stall=$STALL $*): $(cat "$R/outcome.txt") | client: $(grep FINAL "$R/load.log")"
