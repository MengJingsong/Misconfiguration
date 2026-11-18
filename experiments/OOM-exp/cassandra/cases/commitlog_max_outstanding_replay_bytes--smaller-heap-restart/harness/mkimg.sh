#!/usr/bin/env bash
# B15 writer phase (design 2.5 S0.3): mkimg.sh <img> <heapMiB>. Empty vol/data, start at <heapMiB>, schema, P64 load
# (map 5900, 64 in flight, no cap); every 5 s log t, AllMemtablesHeapSize (sjk mx), tpstats, commit-log MiB.
# Kill -9 at the first sample with t >= 60 s and AllMemtablesHeapSize >= 0.75*heap/4, or at t = CAP (270 s).
# Then copy vol/data -> img/<img>. Leaves nothing running.
set -uo pipefail
IMG=$1 HEAP=$2 CAP=${CAP:-270}
source /mydata/s4/b15-w3/harness/common.sh
O=$W/runs/mk-$IMG; mkdir -p $O/dumps; LOG=$O/arm.log
[ -n "$(dpid)" ] && { log "ABORT: a daemon is running"; exit 1; }
THR=$(( HEAP*3/16 ))   # 0.75 * heap/4 in MiB
log "== mkimg $IMG writer heap=${HEAP}M kill at t>=60s and AllMemtablesHeapSize>=${THR}MiB or t=${CAP}s; arch=$(uname -m); /mydata free $(df -BG --output=avail /mydata | tail -1)"
$W/harness/slowdisk.sh set 0 >> $LOG
rm -rf $W/vol/data/*; rm -rf $C/logs; mkdir -p $C/logs
start_node $O $HEAP b15-mk-$IMG
for i in $(seq 1 300); do grep -q 'Starting listening for CQL clients' $C/logs/system.log 2>/dev/null && break; sleep 1; done
log "node up after ${i}s; $(grep -m1 -o 'commitlog_total_space=[^;]*' $C/logs/system.log); $(grep -m1 -o 'memtable_heap_space=[^;]*' $C/logs/system.log)"
grep -m1 -o 'MaxDirectMemorySize=[0-9A-Za-z]*' $O/stdout.txt $C/logs/system.log | head -1 | sed 's/^/jvm: /' >> $LOG
$H/load.sh schema 127.0.0.1 >> $O/client.txt 2>&1
$H/load.sh run map 5900 64 400 0 127.0.0.1 >> $O/client.txt 2>&1 &
CLI=$!
T0=$(date +%s); KV=-1; FB=0
while :; do
  sleep 5; t=$(( $(date +%s) - T0 ))
  [ -z "$(dpid)" ] && { log "NODE DIED during load at t=$t"; break; }
  V=$($C/bin/nodetool sjk mx -mg -b 'org.apache.cassandra.metrics:type=Table,keyspace=b8,scope=t_map,name=AllMemtablesHeapSize' -f Value 2>/dev/null | grep -Eo '^[0-9]+' | tail -1)
  [ -z "$V" ] && { FB=1; V=-1; }
  MV=$(( V>=0 ? V/1048576 : -1 ))
  TS=$($C/bin/nodetool tpstats 2>/dev/null | grep -E 'MemtableFlushWriter|MutationStage' | awk '{print $1"="$2"/"$3"/"$4}' | tr '\n' ' ')
  TB=$($C/bin/nodetool tablestats b8.t_map 2>/dev/null | grep -E 'Memtable data size|SSTable count' | awk -F: '{gsub(/ /,"",$2); printf "%s=%s ", $1, $2}')
  echo "t=$t AllMemtablesHeapSize=${MV}MiB $TS $TB commitlog_MiB=$(du -sm $C/data/commitlog | cut -f1) client=$(tail -1 $O/client.txt | cut -c1-80)" >> $O/stats.txt
  if [ $t -ge 60 ] && [ $MV -ge $THR ]; then KV=$MV; break; fi
  [ $t -ge $CAP ] && { KV=$MV; break; }
done
P=$(dpid); log "kill -9 $P at t=$(( $(date +%s) - T0 ))s; AllMemtablesHeapSize=${KV}MiB (sjk fallback=$FB); commitlog $(du -sm $C/data/commitlog | cut -f1) MiB, $(ls $C/data/commitlog | wc -l) files"
tail -1 $O/stats.txt >> $LOG
[ -n "$P" ] && kill -9 $P; sleep 3; kill $CLI 2>/dev/null; wait $CLI 2>/dev/null
tail -2 $O/client.txt | tee -a $LOG
cp $C/logs/system.log $C/logs/gc.log* $O/ 2>/dev/null
ls -l $C/data/commitlog > $O/commitlog-ls.txt
python3 $H/gcsum.py $O/gc.log > $O/gcsum.txt 2>&1; log "load gc: $(tail -1 $O/gcsum.txt)"
rm -rf $W/img/$IMG; mkdir -p $W/img; cp -a --sparse=always $W/vol/data $W/img/$IMG
log "image $IMG: $(du -sm $W/img/$IMG | cut -f1) MiB; /mydata free $(df -BG --output=avail /mydata | tail -1)"
rm -rf $O/dumps/*.hprof
log "left: daemon=$(pgrep -fc '[o]rg.apache.cassandra.service.CassandraDaemon') client=$(pgrep -fc '[B]8Load')"
log "== RESULT mk-$IMG heap=$HEAP kill_value=${KV}MiB"
