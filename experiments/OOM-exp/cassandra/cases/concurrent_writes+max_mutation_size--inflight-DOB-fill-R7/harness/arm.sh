#!/usr/bin/env bash
# R7: one arm from a clean 9-instance ring (runs on the driver host, drives the two Utah m400s over ssh).
# From U1 run 2's arm.sh; R7 changes (design §2.5): V on ms0625; C1..C8 and their clients all on ms0640 (C1 10.10.1.2,
# C2..C8 alias IPs 10.10.1.71..77, alias.sh up); always N = 8; coordinator heap CX default 5G; LOAD default 180 s;
# coordinators get hinted_handoff_enabled=false; V-dead poll every 2 s during the load (dead -> wait 5 s, kill clients,
# go to observation; real load end recorded); host sampler on ms0640 (node.sh csamp).
#   arm.sh <name> <direct MiB|auto> <blobBytes> <inflight per writer> [load s, default 180]
# env: VEXTRA ("k=v ..." victim yaml; control/intervention arms only), VJVM (victim JVM options; intervention only),
#      CX (coordinator heap, default 5G), WRITERS (connections per client, default 2), RATE (0), KEYS (200), OBS (20)
set -uo pipefail
exec < /dev/null
NAME=$1 DIRECT=$2 BLOB=$3 INFL=$4 LOAD=${5:-180}
CX=${CX:-5G} WRITERS=${WRITERS:-2} RATE=${RATE:-0} KEYS=${KEYS:-200} JSTACK=${JSTACK:-0} OBS=${OBS:-20}
VEXTRA=${VEXTRA:-} VJVM=${VJVM:-}
W=/mydata/s4/r7-w1; H=$W/h; RUNS=$W/runs; R=$RUNS/$NAME
MIR=$W/mirror/$NAME; mkdir -p $MIR      # driver-host local mirror of the small files
declare -A HOST=([V]=ms0625 [C1]=ms0640 [C2]=ms0640 [C3]=ms0640 [C4]=ms0640 [C5]=ms0640 [C6]=ms0640 [C7]=ms0640 [C8]=ms0640)
declare -A IPS=([V]=10.10.1.1 [C1]=10.10.1.2 [C2]=10.10.1.71 [C3]=10.10.1.72 [C4]=10.10.1.73 [C5]=10.10.1.74 [C6]=10.10.1.75 [C7]=10.10.1.76 [C8]=10.10.1.77)
ALLC="C1 C2 C3 C4 C5 C6 C7 C8"; CS=$ALLC; NN=9; NODES="ms0625 ms0640"
log(){ echo "[$(TZ=America/New_York date +%T)] $*" | tee -a $MIR/arm.log; }
ARGL="direct=$DIRECT blob=$BLOB ncoord=8 infl/writer=$INFL writers/client=$WRITERS rate/client=$RATE load=${LOAD}s keys=$KEYS cx=$CX vextra=[$VEXTRA] vjvm=[$VJVM] platform=aarch64"
log "$NAME: $ARGL"
[ -f $W/STOP ] && { log "STOP file present, skipping"; exit 1; }
# 1. clean slate on both nodes
for h in $NODES; do ssh $h "$H/node.sh wipe; rm -rf $R; mkdir -p $R" & done; wait
# amendment A2 (2026-11-17 23:03, before readings): drop ms0640's page cache so the co-location swap check can hold
ssh ms0640 "sync; echo 1 | sudo -n tee /proc/sys/vm/drop_caches > /dev/null; free -m | awk '/^Mem:/{print \"ms0640 MemAvailable before arm MiB:\", \$7}; /^Swap:/{print \"ms0640 swap used MiB:\", \$3}'" >> $MIR/arm.log
ssh ms0625 "echo '$ARGL' > $R/argline; echo 'args: $ARGL' > $R/args.txt; df -h /mydata | tail -1 >> $R/args.txt"
# 2. generate
ssh ms0625 "$H/ctl.sh gen V 2048M v $VEXTRA" >> $MIR/arm.log || { log GENFAIL; exit 1; }
ssh ms0640 "for c in $ALLC; do $H/ctl.sh gen \$c $CX c hinted_handoff_enabled=false; done" >> $MIR/arm.log
# 3. start V, then the coordinators in parallel
ssh ms0625 "DIRECT=$DIRECT VJVM='$VJVM' $H/ctl.sh start V" >> $MIR/arm.log
up=0; for _ in $(seq 90); do ssh ms0625 "(exec 3<>/dev/tcp/10.10.1.1/9042) 2>/dev/null" && { up=1; break; }; sleep 2; done
[ $up = 1 ] || { log "V START FAIL"; exit 1; }
for c in $ALLC; do ssh ms0640 "$H/ctl.sh start $c" >> $MIR/arm.log & done; wait
n=0; for _ in $(seq 100); do n=$(ssh ms0625 "$W/cassandra/bin/nodetool status 2>/dev/null | grep -c '^UN'"); [ "$n" = $NN ] && break; sleep 3; done
log "ring UN=$n"; [ "$n" = $NN ] || { log RINGFAIL; exit 1; }
for c in $ALLC; do for _ in $(seq 40); do ssh ms0640 "(exec 3<>/dev/tcp/${IPS[$c]}/9042) 2>/dev/null" && break; sleep 2; done; done
ssh ms0640 "$H/node.sh schema 10.10.1.2 \"{'class':'NetworkTopologyStrategy','v':1}\"" >> $MIR/arm.log 2>&1
grep -q "schema ok" $MIR/arm.log || { log SCHEMAFAIL; exit 1; }
ssh ms0625 "$W/cassandra/bin/nodetool status > $R/status-before-load.txt 2>&1; $W/cassandra/bin/nodetool getendpoints u1r2 t 1 >> $R/status-before-load.txt 2>&1"
ssh ms0640 "cp $W/inst/C1/yaml.diff $R/C1-yaml.diff; cat $W/inst/C*/jmxport > $R/C-jmxports.txt"
# 4. samplers on V and on ms0640, 5 s idle, load
ssh ms0625 "$H/node.sh vsamp $NAME $JSTACK" >> $MIR/arm.log
ssh ms0640 "$H/node.sh csamp $NAME"
sleep 5
VPID=$(ssh ms0625 "grep -o 'vpid=[0-9]*' $R/args.txt | head -1 | cut -d= -f2")
ssh ms0625 "echo \$(date +%s%3N) load start >> $R/args.txt"
CIPS=$(for c in $CS; do printf '%s ' ${IPS[$c]}; done)
ssh ms0640 "for ip in $CIPS; do KEYS=$KEYS $H/node.sh client $NAME $BLOB $INFL $LOAD $RATE \$ip $WRITERS; done" >> $MIR/arm.log 2>&1
log "load start ($CS) vpid=$VPID"
# V-dead poll (on V, every 2 s, until LOAD+3 s)
st=$(ssh ms0625 "for i in \$(seq $(( (LOAD + 3) / 2 ))); do kill -0 $VPID 2>/dev/null || { echo dead \$(date +%s%3N); exit; }; sleep 2; done; echo alive")
if [ "${st%% *}" = dead ]; then
  log "V dead at ${st#dead } ; waiting 5 s, killing clients"
  sleep 5; ssh ms0640 "pkill -f [U]1R2Load"
  ssh ms0625 "echo ${st#dead } V dead >> $R/args.txt"
else
  for _ in $(seq 40); do ssh ms0640 "pgrep -f [U]1R2Load >/dev/null" || break; sleep 2; done
  ssh ms0640 "pkill -f [U]1R2Load"
fi
ssh ms0625 "echo \$(date +%s%3N) load end >> $R/args.txt"
log "load end ($st)"
sleep $OBS
# 5. collect
ssh ms0640 "$H/node.sh cstop $NAME"
ssh ms0625 "$H/node.sh vstop $NAME; $H/node.sh vcollect $NAME" | tee -a $MIR/arm.log
ssh ms0640 "cd $W/inst; for c in $ALLC; do cp \$c/logs/system.log $R/\$c-system.log 2>/dev/null; du -sk \$c/hints | cut -f1 > $R/\$c-hints-kb.txt; grep -c 'Java heap space' $R/\$c-system.log > $R/\$c-heapoom.txt; done"
ssh ms0625 "du -sk $W/inst/V/commitlog $W/inst/V/data | tr '\n' ' ' >> $R/args.txt; echo >> $R/args.txt"
# 6. stop everything (clean slate for the next arm), mirror small files to the driver
for h in $NODES; do ssh $h "$H/node.sh wipe" & done; wait
ssh ms0625 "cd $R && tar c --exclude='*.hprof' --exclude='gc.log*' --exclude='debug.log' --exclude='threads-*' ." | tar x -C $MIR
ssh ms0640 "cd $R && tar c load-*.log C*-hints-kb.txt C*-heapoom.txt C1-yaml.diff C-jmxports.txt vmstat.txt free.txt 2>/dev/null" | tar x -C $MIR
for c in $ALLC; do ssh ms0640 "grep -E 'WARN|ERROR' $R/$c-system.log | grep -v -i 'gc' | tail -5" > $MIR/$c-warn-tail.txt 2>/dev/null; done
python3 $(dirname "$0")/cvalid.py $MIR >> $MIR/outcome.txt 2>&1
log "done $(cat $MIR/outcome.txt 2>/dev/null | cut -c1-600)"
