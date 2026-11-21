#!/usr/bin/env bash
# R19 fallback (design §2.3/§2.5: golden-ring.sh failed, R1/R2 refused to join a V that remembers their R11 host IDs): R11 golden.sh with /mydata/r19 paths and the client on ms0604. Runs on pc96:  golden.sh <full|small>
# clean ring (all heaps 2G, V build orig), schema, insert kept kv keys 0..F (F 1,600,000 or 20,000 for the shakedown),
# nodetool flush s2c + compact s2c kv (on V), drain all three, stop, tar data commitlog hints to /mydata/r19/golden-<role>.tgz.
set -uo pipefail
MODE=$1; F=1600000; [ "$MODE" = small ] && F=20000
W=/mydata/r19; H=$W/h; C=$H/ctl.sh; E=/mydata/r19-evidence; L=$E/golden-$MODE.log
NT="$W/run-orig/bin/nodetool -h 127.0.0.1 -p 7199"
declare -A HOST=([V]=ms0611 [R1]=ms0625 [R2]=ms0617)
log(){ echo "[$(TZ=America/New_York date +%T)] $*" | tee -a $L; }
log "golden $MODE F=$F"
for n in V R1 R2; do ssh ${HOST[$n]} "$C stop $n; rm -rf $W/inst/$n $W/golden-$n.tgz" >> $L; done
for n in V R1 R2; do ssh ${HOST[$n]} "BUILD=orig $C gen $n 2G" >> $L || { log GENFAIL; exit 1; }; done
ssh ms0611 "$C start V" >> $L
for _ in $(seq 90); do ssh ms0611 "(exec 3<>/dev/tcp/10.10.1.4/9042) 2>/dev/null" && break; sleep 2; done
ssh ms0625 "$C start R1" >> $L & ssh ms0617 "$C start R2" >> $L & wait
for _ in $(seq 100); do nu=$(ssh ms0611 "$NT status 2>/dev/null | grep -c '^UN'"); [ "$nu" = 3 ] && break; sleep 3; done
log "ring UN=$nu"; [ "$nu" = 3 ] || { log RINGFAIL; exit 1; }
ssh ms0604 "bash $H/client.sh load schema 10.10.1.4" >> $L 2>&1
ssh ms0611 "$NT describering s2c | head -6" >> $L 2>&1
T0=$(date +%s); log "insert $F kept kv keys"
ssh ms0604 "bash $H/client.sh fill insert kv 8 0 $F 256 2>&1" | grep -E '^DONE|^RANGE|last error' | tee -a $L
log "insert took $(( $(date +%s) - T0 )) s"
ssh ms0611 "$NT flush s2c && $NT compact s2c kv && $NT tablestats s2c.kv | grep -E 'SSTable count|Number of partitions|Space used \(live\)'" >> $L 2>&1
for n in R1 R2 V; do ssh ${HOST[$n]} "$NT drain" >> $L 2>&1; done
for n in V R1 R2; do ssh ${HOST[$n]} "$C stop $n" >> $L; done
for n in V R1 R2; do ssh ${HOST[$n]} "cd $W/inst/$n && rm -f saved_caches/* && tar -czf $W/golden-$n.tgz data commitlog hints && ls -l $W/golden-$n.tgz && du -sh data" >> $L 2>&1; done
log "golden $MODE done (total $(( $(date +%s) - T0 )) s after insert start)"
