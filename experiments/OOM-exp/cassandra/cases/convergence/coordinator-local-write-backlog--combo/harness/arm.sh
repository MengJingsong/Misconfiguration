#!/usr/bin/env bash
# S2 arm controller (runs on pc96; drives apt140 = V, apt149 = R, apt138 = client over ssh). Clean start every arm.
#   arm.sh <name> <map|blob> <V_xmx>
# env: FILL=1 (fill key+counter caches to their default caps before the load), FLUSH=1 (nodetool flush b6 at t=FLUSH_AT, default 85 s),
#      STALL=30000 (R write delay ms from t=20 s to end of load; 0 = no stall), SESS=8 (client sessions x 256 in flight),
#      LOAD=150 (s), HIST_AT (s; one jcmd GC.class_histogram of V at that time: forces a full GC, diagnostic only)
set -uo pipefail
NAME=$1 KIND=$2 VX=$3; FILL=${FILL:-1} FLUSH=${FLUSH:-1} FLUSH_AT=${FLUSH_AT:-85} STALL=${STALL:-30000} SESS=${SESS:-8} LOAD=${LOAD:-150}
R=/mydata/s2/runs/$NAME; L=/mydata/s2-evidence/runs/$NAME; mkdir -p $L
C=/mydata/s2/h/ctl.sh; NT=/users/jason92/cassandra-b1/bin/nodetool
log(){ echo "[$(TZ=America/New_York date +%T)] $*" | tee -a $L/arm.log; }
log "args: cl=${CL:-ONE} rate=${RATE:-none} kind=$KIND V=$VX fill=$FILL flush=$FLUSH@$FLUSH_AT stall=$STALL sess=$SESS load=$LOAD hist=${HIST_AT:-none}"
ssh apt138 "pkill -f [S]2Load; pkill -f [S]2CacheFill; mkdir -p $R"; ssh apt140 "pkill -f [s]ample.sh; $C stop V; rm -rf $R; mkdir -p $R"; ssh apt149 "$C stop R; /mydata/s2/h/slowdisk.sh set 0 >/dev/null"
ssh apt140 "$C gen V $VX" >> $L/arm.log && ssh apt149 "$C gen R 8G" >> $L/arm.log || { log GENFAIL; exit 1; }
ssh apt140 "$C start V" >> $L/arm.log
for _ in $(seq 60); do ssh apt140 "(exec 3<>/dev/tcp/10.10.1.1/9042) 2>/dev/null" && break; sleep 2; done
ssh apt149 "$C start R" >> $L/arm.log
for _ in $(seq 60); do n=$(ssh apt140 "$NT status 2>/dev/null | grep -c '^UN'"); [ "$n" = 2 ] && break; sleep 3; done
log "ring UN=$n"; [ "$n" = 2 ] || { log RINGFAIL; exit 1; }
ssh apt138 "/mydata/s2/h/client.sh load schema 10.10.1.1" >> $L/arm.log 2>&1
ssh apt140 "/users/jason92/cassandra-b1/bin/cqlsh 10.10.1.1 -e \"CREATE KEYSPACE s2c WITH replication={'class':'NetworkTopologyStrategy','c':1}; CREATE TABLE s2c.kv (k blob PRIMARY KEY, v int); CREATE TABLE s2c.ctr (k blob PRIMARY KEY, c counter);\"" >> $L/arm.log 2>&1
if [ "$FILL" = 1 ]; then
  log "fill: insert 1.6M kv"; ssh apt138 "/mydata/s2/h/client.sh fill insert kv 8 0 1600000 256 2>&1 | tail -1" >> $L/arm.log
  ssh apt140 "$NT flush s2c" ; log "fill: read 1.5M kv"; ssh apt138 "/mydata/s2/h/client.sh fill read kv 8 0 1500000 256 2>&1 | tail -1" >> $L/arm.log
  log "fill: counter 550k"; ssh apt138 "/mydata/s2/h/client.sh fill counter ctr 8 0 550000 256 2>&1 | tail -1" >> $L/arm.log
  ssh apt140 "$NT flush s2c"
fi
ssh apt140 "$NT info | grep -E 'Key Cache|Counter Cache'; $NT tablestats b6 s2c | grep -E 'Table: |Memtable data size'" >> $L/arm.log 2>&1
ssh apt140 "nohup /mydata/s2/h/sample.sh $R > /dev/null 2>&1 &"
log "load start"; ssh apt138 "CL=${CL:-ONE} nohup /mydata/s2/h/client.sh load run $KIND $([ $KIND = map ] && echo 1000 || echo 11000) 256 $LOAD 0 $(for i in $(seq $SESS); do printf '10.10.1.1,'; done | sed 's/,$//') ${RATE:-} > $R/load.log 2>&1 &"
T0=$(date +%s)
sleep 20; [ "$STALL" -gt 0 ] && { ssh apt149 "/mydata/s2/h/slowdisk.sh set $STALL" >> $L/arm.log; log "stall on"; }
if [ "$FLUSH" = 1 ]; then sleep $((FLUSH_AT-20)); log "flush b6"; ssh apt140 "nohup timeout 120 $NT flush b6 > $R/flush.log 2>&1 &"; fi
if [ -n "${HIST_AT:-}" ]; then sleep $((HIST_AT - $(date +%s) + T0)); log "hist"; ssh apt140 "timeout 100 jcmd \$(cat /mydata/s2/inst/V/cass.pid) GC.class_histogram > $R/V-histogram.txt 2>&1"; fi
sleep $((LOAD + 5 - $(date +%s) + T0)); for _ in $(seq 30); do ssh apt138 "pgrep -f [S]2Load >/dev/null" || break; sleep 5; done
ssh apt149 "/mydata/s2/h/slowdisk.sh set 0" >> $L/arm.log; log "load end, stall off"
sleep 60
for _ in $(seq 60); do ssh apt140 "kill -0 \$(cat /mydata/s2/inst/V/cass.pid) 2>/dev/null && ls /mydata/s2/inst/V/dumps/*.hprof >/dev/null 2>&1 && ! grep -q 'Heap dump file created' /mydata/s2/inst/V/logs/launch.log /mydata/s2/inst/V/logs/system.log 2>/dev/null" || break; sleep 5; done
ssh apt140 "kill -0 \$(cat /mydata/s2/inst/V/cass.pid) 2>/dev/null && echo V_ALIVE || echo V_DEAD" | tee -a $L/arm.log
ssh apt140 "pkill -f [s]ample.sh; cd /mydata/s2/inst/V/logs; cp -p gc.log* system.log launch.log $R/ 2>/dev/null; grep -m3 -B2 -A25 'java.lang.OutOfMemoryError' system.log > $R/oom-excerpt.txt; \
  echo \"$NAME: V xmx=$VX \$(grep -c java.lang.OutOfMemoryError system.log) OOMError lines | \$(/mydata/s2/h/gcpeak.sh . \$(( \$(echo $VX | tr -d G) * 1024 ))) | \$(python3 /mydata/s2/h/gcwin.py .)\" > $R/outcome.txt; \
  for d in /mydata/s2/inst/V/dumps/*.hprof; do [ -f \"\$d\" ] || continue; ls -l \$d > $R/dump.ls; if [ \$(stat -c %s \$d) -lt 3000000000 ]; then timeout 600 python3 /mydata/s2/h/hprofhist.py \$d > $R/dump-hist.txt 2>&1; rm -f \$d; else mkdir -p /mydata/s2/dumps; mv \$d /mydata/s2/dumps/$NAME.hprof; fi; done"
ssh apt149 "mkdir -p $R; cp -p /mydata/s2/inst/R/logs/gc.log* $R/ 2>/dev/null; echo R: \$(/mydata/s2/h/gcpeak.sh $R 8192) > $R/R-outcome.txt; $C stop R"
ssh apt140 "$C stop V"
rsync -a apt140:$R/ $L/V/ ; rsync -a apt138:$R/ $L/client/ ; rsync -a apt149:$R/R-outcome.txt $L/
log "$(cat $L/V/outcome.txt) | client: $(grep FINAL $L/client/load.log) | $(cat $L/R-outcome.txt)"
