#!/usr/bin/env bash
# S2 run 2 end-of-arm collection (runs on pc96; called by arm.sh, or by hand for an arm whose controller died).
#   collect.sh <name> <A|G> <V_xmx> <R1_xmx> <R2_xmx>
# Waits while a heap dump is being written, records alive/dead, copies GC/system logs, computes gcpeak/gcwin per
# node, moves any dump to the node's /mydata/s2r2/dumps/<name>-<role>.hprof, stops everything, copies back.
set -uo pipefail
NAME=$1 TOPO=$2 VX=$3 RX1=$4 RX2=$5
R=/mydata/s2r2/runs/$NAME; L=/mydata/s2r2-evidence/runs/$NAME; mkdir -p $L
C=/mydata/s2r2/h/ctl.sh; H=/mydata/s2r2/h
if [ "$TOPO" = A ]; then SRV="V R1"; else SRV="V R1 R2"; fi
declare -A HOST=([V]=ms0640 [R1]=ms0604 [R2]=ms0611)
log(){ echo "[$(TZ=America/New_York date +%T)] $*" | tee -a $L/arm.log; }
# wait while a dump is being written (V or replicas)
for n in $SRV; do
  for _ in $(seq 60); do ssh ${HOST[$n]} "I=/mydata/s2r2/inst/$n; kill -0 \$(cat \$I/cass.pid) 2>/dev/null && ls \$I/dumps/*.hprof >/dev/null 2>&1 && ! grep -q 'Heap dump file created' \$I/logs/launch.log \$I/logs/system.log 2>/dev/null" || break; sleep 5; done
done
for n in $SRV; do
  hx=$([ $n = V ] && echo $VX || { [ $n = R1 ] && echo $RX1 || echo $RX2; })
  ssh ${HOST[$n]} "I=/mydata/s2r2/inst/$n; kill -0 \$(cat \$I/cass.pid) 2>/dev/null && echo ${n}_ALIVE || echo ${n}_DEAD" | tee -a $L/arm.log
  ssh ${HOST[$n]} "pkill -f [s]ample.sh; pkill -f [S]2Poll; I=/mydata/s2r2/inst/$n; cd \$I/logs; cp -p gc.log* system.log launch.log ../yaml.diff ../cgroup $R/ 2>/dev/null; grep -m3 -B2 -A25 'java.lang.OutOfMemoryError' system.log > $R/oom-excerpt.txt; \
    echo \"$NAME $n: xmx=$hx \$(grep -c java.lang.OutOfMemoryError system.log) OOMError lines | \$($H/gcpeak.sh . \$(( \$(echo $hx | tr -d G) * 1024 ))) | \$(python3 $H/gcwin.py .)\" > $R/outcome.txt; \
    for d in \$I/dumps/*.hprof; do [ -f \"\$d\" ] || continue; ls -l \$d > $R/dump.ls; mkdir -p /mydata/s2r2/dumps; mv \$d /mydata/s2r2/dumps/$NAME-$n.hprof; done"
done
for n in $SRV; do ssh ${HOST[$n]} "$C stop $n" >> $L/arm.log; done
ssh ms0617 "pkill -f [S]2Load"
for n in $SRV; do rsync -a ${HOST[$n]}:$R/ $L/$n/; done; rsync -a ms0617:$R/ $L/client/
log "$(cat $L/V/outcome.txt) | client: $(grep FINAL $L/client/load.log) | R1: $(cut -d'|' -f1-2 $L/R1/outcome.txt) $([ $TOPO = G ] && echo "| R2: $(cut -d'|' -f1-2 $L/R2/outcome.txt)")"
