#!/usr/bin/env bash
# U1 run 2: one arm from a clean 5-node ring (runs on pc96, drives the Utah nodes over ssh).
#   arm.sh <name> <direct MiB|auto> <blobBytes> <ncoord 1-4> <inflight per client> [load s, default 90]
# Topology: V ms0625 (dc v, the only replica: keyspace u1r2 = NTS {v:1}); coordinators C1..C4 on ms0640/0604/0611/0617
# (dc c, RF 0). One client per used coordinator node, whitelisted to its local coordinator, CL ONE, <inflight>
# requests outstanding (no rate cap unless RATE). V never sees client request frames: every mutation reaches it as
# an internode MUTATION_REQ.
# env: VEXTRA ("k=v ..." victim yaml; control/intervention arms only), VJVM (victim JVM options; intervention only),
#      CX (coordinator heap, default 8G), WRITERS (connections per client, default 2), RATE (per client, 0 = none),
#      KEYS (200), JSTACK=1 (jcmd Thread.print every 5 s on V; diagnostic arms only), OBS (s after load, 20)
set -uo pipefail
exec < /dev/null   # ssh must not eat the queue file (queue.sh feeds arms on stdin)
NAME=$1 DIRECT=$2 BLOB=$3 NC=$4 INFL=$5 LOAD=${6:-90}
CX=${CX:-8G} WRITERS=${WRITERS:-2} RATE=${RATE:-0} KEYS=${KEYS:-200} JSTACK=${JSTACK:-0} OBS=${OBS:-20}
VEXTRA=${VEXTRA:-} VJVM=${VJVM:-}
H=/mydata/u1r2/h; RUNS=/mydata/u1r2/runs; R=$RUNS/$NAME
MIR=/mydata/u1r2/mirror/$NAME; mkdir -p $MIR      # pc96 local mirror of the small files
declare -A HOST=([V]=ms0625 [C1]=ms0640 [C2]=ms0604 [C3]=ms0611 [C4]=ms0617 [C5]=ms0640 [C6]=ms0604 [C7]=ms0611 [C8]=ms0617)
declare -A IPS=([V]=10.10.1.1 [C1]=10.10.1.2 [C2]=10.10.1.3 [C3]=10.10.1.4 [C4]=10.10.1.5 [C5]=10.10.1.12 [C6]=10.10.1.13 [C7]=10.10.1.14 [C8]=10.10.1.15)
CS=$(for i in $(seq 1 $NC); do printf 'C%d ' $i; done)
ALLC="C1 C2 C3 C4"; [ "$NC" -gt 4 ] && ALLC="C1 C2 C3 C4 C5 C6 C7 C8"   # amendment 2: N = 8 via alias IPs
NN=$(( $(echo $ALLC | wc -w) + 1 )); NODES="ms0625 ms0640 ms0604 ms0611 ms0617"
log(){ echo "[$(TZ=America/New_York date +%T)] $*" | tee -a $MIR/arm.log; }
ARGL="direct=$DIRECT blob=$BLOB ncoord=$NC infl/client=$INFL writers/client=$WRITERS rate/client=$RATE load=${LOAD}s keys=$KEYS cx=$CX vextra=[$VEXTRA] vjvm=[$VJVM] jstack=$JSTACK platform=aarch64"
log "$NAME: $ARGL"
[ -f /mydata/u1r2/STOP ] && { log "STOP file present, skipping"; exit 1; }
# 1. clean slate on all five nodes
for h in $NODES; do ssh $h "$H/node.sh wipe; rm -rf $R; mkdir -p $R" & done; wait
ssh ms0625 "echo '$ARGL' > $R/argline; echo 'args: $ARGL' > $R/args.txt; df -h /mydata | tail -1 >> $R/args.txt"
# 2. generate
ssh ms0625 "$H/ctl.sh gen V 2048M v $VEXTRA" >> $MIR/arm.log || { log GENFAIL; exit 1; }
for c in $ALLC; do ssh ${HOST[$c]} "$H/ctl.sh gen $c $CX c" >> $MIR/arm.log & done; wait
# 3. start V, then the coordinators in parallel
ssh ms0625 "DIRECT=$DIRECT VJVM='$VJVM' $H/ctl.sh start V" >> $MIR/arm.log
up=0; for _ in $(seq 90); do ssh ms0625 "(exec 3<>/dev/tcp/10.10.1.1/9042) 2>/dev/null" && { up=1; break; }; sleep 2; done
[ $up = 1 ] || { log "V START FAIL"; exit 1; }
for c in $ALLC; do ssh ${HOST[$c]} "$H/ctl.sh start $c" >> $MIR/arm.log & done; wait
n=0; for _ in $(seq 80); do n=$(ssh ms0625 "/mydata/u1r2/cassandra/bin/nodetool status 2>/dev/null | grep -c '^UN'"); [ "$n" = $NN ] && break; sleep 3; done
log "ring UN=$n"; [ "$n" = $NN ] || { log RINGFAIL; exit 1; }
for c in $ALLC; do for _ in $(seq 40); do ssh ${HOST[$c]} "(exec 3<>/dev/tcp/${IPS[$c]}/9042) 2>/dev/null" && break; sleep 2; done; done
ssh ms0640 "$H/node.sh schema 10.10.1.2 \"{'class':'NetworkTopologyStrategy','v':1}\"" >> $MIR/arm.log 2>&1
grep -q "schema ok" $MIR/arm.log || { log SCHEMAFAIL; exit 1; }
ssh ms0625 "/mydata/u1r2/cassandra/bin/nodetool status > $R/status-before-load.txt 2>&1; /mydata/u1r2/cassandra/bin/nodetool getendpoints u1r2 t 1 >> $R/status-before-load.txt 2>&1"
# 4. samplers on V, 5 s idle, load
ssh ms0625 "$H/node.sh vsamp $NAME $JSTACK" >> $MIR/arm.log
sleep 5
ssh ms0625 "echo \$(date +%s%3N) load start >> $R/args.txt"
for c in $CS; do ssh ${HOST[$c]} "KEYS=$KEYS $H/node.sh client $NAME $BLOB $INFL $LOAD $RATE ${IPS[$c]} $WRITERS" >> $MIR/arm.log & done; wait
log "load start ($CS)"
sleep $((LOAD + 3))
for c in $CS; do for _ in $(seq 40); do ssh ${HOST[$c]} "pgrep -f [U]1R2Load >/dev/null" || break; sleep 2; done; done
ssh ms0625 "echo \$(date +%s%3N) load end >> $R/args.txt"
log "load end"
sleep $OBS
# 5. collect
ssh ms0625 "$H/node.sh vstop $NAME; $H/node.sh vcollect $NAME" | tee -a $MIR/arm.log
for c in $ALLC; do ssh ${HOST[$c]} "mkdir -p $R; cp /mydata/u1r2/inst/$c/logs/system.log $R/$c-system.log 2>/dev/null; du -sk /mydata/u1r2/inst/$c/hints | cut -f1 > $R/$c-hints-kb.txt; grep -c 'Java heap space' $R/$c-system.log > $R/$c-heapoom.txt" & done; wait
ssh ms0625 "du -sk /mydata/u1r2/inst/V/commitlog /mydata/u1r2/inst/V/data | tr '\n' ' ' >> $R/args.txt; echo >> $R/args.txt"
# 6. stop everything (clean slate for the next arm), mirror small files to pc96
for h in $NODES; do ssh $h "$H/node.sh wipe" & done; wait
ssh ms0625 "cd $R && tar c --exclude='*.hprof' --exclude='gc.log*' --exclude='debug.log' --exclude='threads-*' ." | tar x -C $MIR
for h in ms0640 ms0604 ms0611 ms0617; do ssh $h "cd $R && tar c load-*.log C*-hints-kb.txt C*-heapoom.txt 2>/dev/null" | tar x -C $MIR; done
for c in $ALLC; do ssh ${HOST[$c]} "grep -E 'WARN|ERROR' $R/$c-system.log | grep -v -i 'gc' | tail -5" > $MIR/$c-warn-tail.txt 2>/dev/null; done
log "done $(cat $MIR/outcome.txt 2>/dev/null | cut -c1-400)"
