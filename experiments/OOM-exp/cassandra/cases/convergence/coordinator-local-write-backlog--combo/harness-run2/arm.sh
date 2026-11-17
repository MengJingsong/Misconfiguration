#!/usr/bin/env bash
# S2 run 2 arm controller (runs on pc96; drives ms0640 = V, ms0604 = R1, ms0611 = R2, ms0617 = client over ssh).
# Clean start every arm (all instances regenerated from the build's conf, data wiped, schema re-created).
#   arm.sh <name> <A|G> <V_xmx>
#     A = run 1's topology: V dc c + R1 dc r, keyspace b6 NTS {c:1, r:1} (RF=2, one replica per DC); R2 not started
#     G = RF=3 single DC: V, R1, R2 all dc c, keyspace b6 NTS {c:3}
# env: RX1 (R1 heap, default 8G), RX2 (R2 heap, default = RX1; G only), CL (default ONE), RATE (total writes/s cap,
#      default none), SESS (client sessions x 256 in flight to V, default 8), LOAD (s, default 90), OBS (s after the
#      client ends, default 60)
# Same client shape as run 1: blob 11 000 B, 8 x 256 in flight, all requests to V only (whitelist), CL=ONE.
set -uo pipefail
NAME=$1 TOPO=$2 VX=$3; RX1=${RX1:-8G}; RX2=${RX2:-$RX1}; SESS=${SESS:-8} LOAD=${LOAD:-90} OBS=${OBS:-60}
R=/mydata/s2r2/runs/$NAME; L=/mydata/s2r2-evidence/runs/$NAME; mkdir -p $L
C=/mydata/s2r2/h/ctl.sh; NT="/mydata/s2r2/cassandra/bin/nodetool -h 127.0.0.1"; H=/mydata/s2r2/h
if [ "$TOPO" = A ]; then SRV="V R1"; NSRV=2; DCR1=r; DCR2=-; REPL="{'class':'NetworkTopologyStrategy','c':1,'r':1}"
else SRV="V R1 R2"; NSRV=3; DCR1=c; DCR2=c; REPL="{'class':'NetworkTopologyStrategy','c':3}"; fi
declare -A HOST=([V]=ms0640 [R1]=ms0604 [R2]=ms0611) IPS=([V]=10.10.1.2 [R1]=10.10.1.3 [R2]=10.10.1.4)
log(){ echo "[$(TZ=America/New_York date +%T)] $*" | tee -a $L/arm.log; }
log "args: topo=$TOPO repl=$REPL V=$VX R1=$RX1 R2=$([ $TOPO = G ] && echo $RX2 || echo off) cl=${CL:-ONE} rate=${RATE:-none} sess=$SESS load=$LOAD obs=$OBS platform=aarch64"
# clean slate on all four nodes
ssh ms0617 "pkill -f [S]2Load; rm -rf $R; mkdir -p $R"
for n in V R1 R2; do ssh ${HOST[$n]} "pkill -f [s]ample.sh; pkill -f [S]2Poll; $C stop $n >/dev/null; pkill -f [C]assandraDaemon; rm -rf $R; mkdir -p $R"; done
ssh ms0640 "$C gen V $VX c" >> $L/arm.log && ssh ms0604 "$C gen R1 $RX1 $DCR1" >> $L/arm.log || { log GENFAIL; exit 1; }
[ $TOPO = G ] && { ssh ms0611 "$C gen R2 $RX2 $DCR2" >> $L/arm.log || { log GENFAIL; exit 1; }; }
ssh ms0640 "$C start V" >> $L/arm.log
for _ in $(seq 90); do ssh ms0640 "(exec 3<>/dev/tcp/10.10.1.2/9042) 2>/dev/null" && break; sleep 2; done
ssh ms0604 "$C start R1" >> $L/arm.log & [ $TOPO = G ] && ssh ms0611 "$C start R2" >> $L/arm.log & wait
for _ in $(seq 80); do n=$(ssh ms0640 "$NT status 2>/dev/null | grep -c '^UN'"); [ "$n" = $NSRV ] && break; sleep 3; done
log "ring UN=$n"; [ "$n" = $NSRV ] || { log RINGFAIL; exit 1; }
ssh ms0617 "REPL=\"$REPL\" $H/client.sh load schema 10.10.1.2" >> $L/arm.log 2>&1
ssh ms0640 "$NT describering b6 | head -4 | tail -2" >> $L/arm.log 2>&1
for n in $SRV; do ssh ${HOST[$n]} "nohup nice -n 10 $H/sample.sh $R $n > /dev/null 2>&1 &"; done
log "load start"
ssh ms0617 "CL=${CL:-ONE} nohup $H/client.sh load run blob 11000 256 $LOAD 0 $(for i in $(seq $SESS); do printf '10.10.1.2,'; done | sed 's/,$//') ${RATE:-} > $R/load.log 2>&1 &"
T0=$(date +%s)
sleep $((LOAD + 5)); for _ in $(seq 30); do ssh ms0617 "pgrep -f [S]2Load >/dev/null" || break; sleep 5; done
log "load end (client exited $(( $(date +%s) - T0 )) s after start)"
sleep $OBS
$(dirname $0)/collect.sh "$NAME" "$TOPO" "$VX" "$RX1" "$RX2"
