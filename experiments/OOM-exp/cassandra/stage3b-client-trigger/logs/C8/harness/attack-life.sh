#!/usr/bin/env bash
# C8 stage 3-b confirm (2026-11-24): attack lifetime (the verified BW arm as the attacker role). Usage: attack-life.sh <run-id> [cap-s]
# Fresh data/ from $TPL (the attacker's own CQL-loaded table, no flush/compact by an admin), node at 1,536 / 768 MiB with
# auth on -> monitors -> victim role (10 ops/s on victim.kv) -> 60 s baseline -> attack start: cassandra-stress write as
# `attacker` (unthrottled, 32 threads, 4 x 1 KiB columns, CL ONE, into its own keyspace1.standard1) -> +60 s
# `CREATE INDEX v_idx ON c8.big (v) USING 'sai'` as `attacker` -> endpoint: daemon gone, initial build complete
# ("became queryable"), disk guard (< 5 GiB free) or cap -> stress stopped -> 30 s victim "after" -> node stopped.
set -u
. $(dirname "$0")/common.sh
RID=$1; CAP=${2:-1200}; R=$W/runs/$RID; VSTOP=$R/VSTOP; mkdir -p $R; exec >> $R/driver.txt 2>&1
log "ATTACK lifetime $RID heap=$HEAP direct=$DIRECT cap=${CAP}s"
precheck
rm -rf $T/data $T/logs; mkdir -p $T/data; cp -a $TPL/. $T/data/
ls -l $T/data/data/c8/big-*/*-Data.db > $R/sstables-start.txt 2>&1
start_node $RID $R
T0=$(date +%s)
monitors $PID $R $R/STOP
{ echo "== attacker permissions"; CQ -u cassandra -p cassandra -e "LIST ALL PERMISSIONS OF attacker"; echo "== attacker sees c8.big"; CQ -u attacker -p $APW -e "SELECT pk, v FROM c8.big LIMIT 1"; } > $R/auth-check.txt 2>&1
setsid nohup python3 -I $H/victim.py --user victim --pw $VPW --rate 10 --out $R/victim.txt --stop $VSTOP --src 127.0.0.1 < /dev/null > $R/victim.err 2>&1 &
VP=$!; echo $VP > $R/victim.pid
sleep 60
log "baseline done; attack start at_ms $(ems)"
setsid nohup $T/tools/bin/cassandra-stress write duration=900s cl=ONE no-warmup -col 'size=fixed(1024)' 'n=fixed(4)' \
  -rate threads=32 -node 127.0.0.1 -mode native cql3 user=attacker password=$APW -log interval=1 file=$R/stress.log \
  < /dev/null > $R/stress.out 2>&1 &
SP=$!; echo $SP > $R/stress.pid
log "stress pid $SP"
sleep 60
log "CREATE INDEX (as attacker) issued at_ms $(ems)"
( t=$(date +%s%3N); CQT=900 CQ -u attacker -p $APW --request-timeout=900 -e "CREATE INDEX v_idx ON c8.big (v) USING 'sai'" > $R/create-index.out 2>&1; echo "rc=$? after_ms=$(( $(date +%s%3N) - t ))" >> $R/create-index.out ) &
CIP=$!
END=""
while :; do
  sleep 1
  if ! kill -0 $PID 2>/dev/null; then END=daemon-exit; log "daemon gone while attack running at_ms $(ems)"; break; fi
  if grep -q "Index \[v_idx\] became queryable" $T/logs/system.log 2>/dev/null; then END=build-complete; break; fi
  f=$(df -BM --output=avail /mydata | tail -1 | tr -dc 0-9)
  if [ "$f" -lt 5120 ]; then END="disk-guard(${f}M)"; break; fi
  if [ $(( $(date +%s) - T0 )) -ge $CAP ]; then END=cap; break; fi
  kill -0 $SP 2>/dev/null || { END=stress-ended; break; }
done
log "endpoint $END"
# stop the attacker's load
pkill -TERM -f "cassandra-stress.*user=attacker" 2>/dev/null; kill $SP 2>/dev/null; sleep 3
pkill -KILL -f "org.apache.cassandra.stress.Stress" 2>/dev/null
if [ "$END" != daemon-exit ]; then
  log "attack clients ended; daemon alive (hold end) at_ms $(ems) $END"
  log "victim after-phase (30 s, node alive)"; sleep 30; touch $VSTOP
  if grep -q "Dumping heap to" $R/stdout.txt && ! grep -q "Heap dump file created" $R/stdout.txt; then
    for i in $(seq 1 600); do grep -q "Heap dump file created" $R/stdout.txt && break; kill -0 $PID 2>/dev/null || break; sleep 1; done
  fi
  stop_node $RID
else
  log "victim after-phase (30 s, node down)"; sleep 30; touch $VSTOP
  for i in $(seq 1 120); do grep -q "Heap dump file created" $R/stdout.txt && break; sleep 1; done
  stop_node $RID
fi
sleep 2; kill $VP 2>/dev/null; kill $CIP 2>/dev/null
stop_monitors $R
grep -qF "java.lang.OutOfMemoryError" $R/stdout.txt && END="$END oom:$(grep -m1 -F "java.lang.OutOfMemoryError" $R/stdout.txt | head -c 160)"
log "END $END"
cp $T/logs/system.log* $T/logs/debug.log* $T/logs/gc.log* $R/ 2>/dev/null
ls -l $T/data/data/c8/big-*/ > $R/c8-big-dir-end.txt 2>&1
python3 -I $H/victim_summary.py $R > $R/victim-summary.txt 2>&1
log "done; leftovers: daemon='$(dpid)' stress='$(pgrep -f org.apache.cassandra.stress.Stress)' victim='$(pgrep -f "victim.py.*$R")' sampler='$(pgrep -f "C8Sampler 7199 $R/")'"
