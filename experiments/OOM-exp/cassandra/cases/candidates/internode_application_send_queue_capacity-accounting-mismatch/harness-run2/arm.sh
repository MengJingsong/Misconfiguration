#!/usr/bin/env bash
# One run-2 arm from a clean start: 4 coordinators, Java client, replica disk stall mid-load.
#   arm.sh <name> <map|blob> <size> <V_xmx> <S_xmx> <stall_ms> [yaml key=value ... for all instances]
# Timeline: load 150 s on S1-S4; at t=20 s V's disk write delay := stall_ms; at t=150 s delay := 0;
# then observe V for 60 s. Outcome: OOM (ReportJavaOutOfMemory) | GC spiral (Full GCs > 95% heap still
# running at the end) | survived. Default timeouts unless passed.
set -uo pipefail
H=$(cd "$(dirname "$0")" && pwd)
NAME=$1 KIND=$2 SIZE=$3 VX=$4 SX=$5 STALL=$6; shift 6
R=/mydata/b6/runs2/$NAME; rm -rf "$R"; mkdir -p "$R"; echo "args: $KIND $SIZE V=$VX S=$SX stall=$STALL extra=[$*]" > "$R/args.txt"
"$H/ring-up.sh" "$VX" "$SX" "$@" > "$R/ring-up.log" 2>&1
grep -q "schema ok" "$R/ring-up.log" || { echo "$NAME: RING FAIL"; "$H/ctl.sh" stop all >/dev/null; exit 1; }
VPID=$(cat /mydata/b6/ring2/V/cass.pid)
"$H/sample.sh" "$R" 3 2>/dev/null & SMP=$!
"$H/load.sh" run "$KIND" "$SIZE" 256 150 0 127.0.0.13,127.0.0.14,127.0.0.15,127.0.0.16 > "$R/load.log" 2>&1 & LP=$!
sleep 20; [ "$STALL" -gt 0 ] && "$H/slowdisk.sh" set "$STALL" >> "$R/stall.log"
wait $LP; "$H/slowdisk.sh" set 0 >> "$R/stall.log"
sleep 60; kill $SMP 2>/dev/null; wait $SMP 2>/dev/null
mkdir -p "$R/V-logs"; cp -p /mydata/b6/ring2/V/logs/system.log /mydata/b6/ring2/V/logs/gc.log* "$R/V-logs/" 2>/dev/null
if kill -0 $VPID 2>/dev/null; then st=alive; else st=DEAD; fi
VM=$(( ${VX%G} * 1024 ))
G=$("$H/gcsum.sh" "$R/V-logs" $VM)
END=$(date +%s); LASTF=$(echo "$G" | sed 's/.*last_full=\([^ ]*\).*/\1/')
LF=$(date -d "${LASTF/T/ }" +%s 2>/dev/null || echo 0)
spiral=no; [ $((END - LF)) -lt 30 ] && echo "$G" | grep -q "first_full_gt95=2" && spiral=yes
echo "V $st spiral_at_end=$spiral | $G" > "$R/outcome.txt"
"$H/ctl.sh" stop all > "$R/stop.log" 2>&1
echo "$NAME ($KIND $SIZE V=$VX stall=$STALL $*): $(cat "$R/outcome.txt") | client: $(grep FINAL "$R/load.log")"
