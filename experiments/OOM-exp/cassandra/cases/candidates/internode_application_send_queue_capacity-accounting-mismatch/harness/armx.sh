#!/usr/bin/env bash
# Generalised arm (intervention / default-timeout arms), clean start.
#   armx.sh <name> <map|blob> <size> <S_xmx> <V_xmx> <duration> <clients> [yaml key=value ... for all instances]
# Unlike arm.sh, timeouts/capacities are only what is passed (none = shipped defaults).
set -uo pipefail
H=$(cd "$(dirname "$0")" && pwd)
NAME=$1 KIND=$2 SIZE=$3 SX=$4 VX=$5 DUR=$6 NC=$7; shift 7
R=/mydata/b6/runs/$NAME; rm -rf "$R"; mkdir -p "$R"
VXMX=$VX "$H/ring-up.sh" "$SX" "$@" > "$R/ring-up.log" 2>&1
grep -q "schema ok" "$R/ring-up.log" || { echo "$NAME: RING FAIL"; exit 1; }
SPID=$(cat /mydata/b6/ring/S/cass.pid); VPID=$(cat /mydata/b6/ring/V/cass.pid)
"$H/sample.sh" "$R" 2 2>/dev/null & SMP=$!
echo "extra: $*" > "$R/extra.txt"
LPS=""; for c in $(seq "$NC"); do
  python3 "$H/load.py" run --kind "$KIND" --size "$SIZE" --inflight 256 --duration "$DUR" --pk0 $((c*10000000)) > "$R/load$c.log" 2>&1 & LPS="$LPS $!"
done; wait $LPS; cat "$R"/load*.log | grep FINAL > "$R/load.log"
sleep 10
# a JVM that hit OOM may still be writing its heap dump before OnOutOfMemoryError kills it
for p in $SPID $VPID; do for _ in $(seq 60); do
  kill -0 $p 2>/dev/null || break
  ls /mydata/b6/ring/*/dumps/*.hprof >/dev/null 2>&1 || grep -q ReportJavaOutOfMemory /mydata/b6/ring/*/logs/gc.log* 2>/dev/null || break
  sleep 3; done; done
kill $SMP 2>/dev/null; wait $SMP 2>/dev/null
for n in S V; do
  p=$([ $n = S ] && echo $SPID || echo $VPID)
  if kill -0 "$p" 2>/dev/null; then st=alive; else st=DEAD; fi
  oom=$(cat /mydata/b6/ring/$n/logs/gc.log* 2>/dev/null | grep -c "ReportJavaOutOfMemory")
  dump=$(ls /mydata/b6/ring/$n/dumps/*.hprof 2>/dev/null | wc -l)
  echo "$n $st ReportJavaOutOfMemory=$oom heapdumps=$dump" >> "$R/outcome.txt"
  mkdir -p "$R/$n-logs"; cp /mydata/b6/ring/$n/logs/system.log /mydata/b6/ring/$n/logs/gc.log* "$R/$n-logs/" 2>/dev/null
  mv /mydata/b6/ring/$n/dumps/*.hprof "$R/" 2>/dev/null
done
echo "$NAME ($KIND $SIZE S=$SX V=$VX): $(tr '\n' ';' < "$R/outcome.txt") clients: $(awk '{s+=substr($2,6); o+=substr($3,4); e+=substr($4,5)} END{print "sent="s" ok="o" err="e}' "$R/load.log")"
