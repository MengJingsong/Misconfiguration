#!/usr/bin/env bash
# R19 golden ring state (design §2.5), runs on pc96, once:  golden-ring.sh
# V is restored from R11's golden-V.tgz (orig build); R1, R2 are generated fresh (orig, 2 GiB); start V, then R1, R2;
# wait UN = 3 and one schema version; check V tablestats s2c.kv and describering s2c; drain R1, R2, V; stop;
# tar R1/R2 data commitlog hints to /mydata/r19/golden-<role>.tgz (saved_caches emptied).
set -uo pipefail
W=/mydata/r19; H=$W/h; C=$H/ctl.sh; E=/mydata/r19-evidence; L=$E/golden-ring.log
NT="$W/run-orig/bin/nodetool -h 127.0.0.1 -p 7199"
declare -A HOST=([V]=ms0611 [R1]=ms0625 [R2]=ms0617)
log(){ echo "[$(TZ=America/New_York date +%T)] $*" | tee -a $L; }
log "golden-ring start"
for n in V R1 R2; do ssh ${HOST[$n]} "$C stop $n; rm -rf $W/inst/$n" >> $L; done
for n in R1 R2; do ssh ${HOST[$n]} "rm -f $W/golden-$n.tgz; BUILD=orig $C gen $n 2G" >> $L || { log GENFAIL; exit 1; }; done
ssh ms0611 "BUILD=orig $C restore V 2G" >> $L || { log RESTOREFAIL; exit 1; }
ssh ms0611 "$C start V" >> $L
for _ in $(seq 90); do ssh ms0611 "(exec 3<>/dev/tcp/10.10.1.4/9042) 2>/dev/null" && break; sleep 2; done
ssh ms0625 "$C start R1" >> $L & ssh ms0617 "$C start R2" >> $L & wait
for _ in $(seq 100); do nu=$(ssh ms0611 "$NT status 2>/dev/null | grep -c '^UN'"); [ "$nu" = 3 ] && break; sleep 3; done
log "ring UN=$nu"; [ "$nu" = 3 ] || { log RINGFAIL; exit 1; }
for _ in $(seq 60); do sv=$(ssh ms0611 "$NT describecluster 2>/dev/null" | awk '/Schema versions:/{f=1;next} f&&/: \[/{c++} END{print c+0}'); [ "$sv" = 1 ] && break; sleep 5; done
log "schema versions=$sv"; ssh ms0611 "$NT describecluster; $NT status" >> $L 2>&1
ssh ms0611 "$NT tablestats s2c.kv | grep -E 'SSTable count|Number of partitions|Space used \(live\)'; $NT describering s2c | head -6; $NT describering b6 | head -6" 2>&1 | tee -a $L
for n in R1 R2 V; do ssh ${HOST[$n]} "$NT drain" >> $L 2>&1; done
for n in V R1 R2; do ssh ${HOST[$n]} "$C stop $n" >> $L; done
for n in R1 R2; do ssh ${HOST[$n]} "cd $W/inst/$n && rm -f saved_caches/* && tar -czf $W/golden-$n.tgz data commitlog hints && ls -l $W/golden-$n.tgz && du -sh data" >> $L 2>&1; done
log "golden-ring done"
