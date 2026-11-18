#!/usr/bin/env bash
# B12 run driver (after B11's run.sh). Usage: run.sh <run-id> <base|iv> <heap e.g. 2G> <K> <SERIAL|ONE> <N_max> <M> [cap0]
# Layout: $W/cassandra-<base|iv>, $W/harness, $W/runs/<run-id>; heap dumps to /dev/shm/b12-w2/<run-id>.
# cap0: use a copy of the shipped yaml with `paxos_cache_size: 0MiB` appended (fallback intervention only).
set -u
W=/mydata/s4/b12-w2; H=$W/harness
RID=$1; BUILD=$2; HEAP=$3; K=$4; CLV=$5; NMAX=$6; M=$7; CAP0=${8:-}
T=$W/cassandra-$BUILD; R=$W/runs/$RID; D=/dev/shm/b12-w2/$RID
mkdir -p $R $D; exec > $R/driver.txt 2>&1
log(){ echo "$(date +%FT%T) $*"; }
NT=$T/bin/nodetool
log "run $RID build=$BUILD heap=$HEAP K=$K cl=$CLV nmax=$NMAX m=$M cap0=$CAP0 arch=$(uname -m)"
# 1. preflight
if ps -eo cmd | grep -q '[C]assandraDaemon'; then log "ABORT: a CassandraDaemon runs"; exit 1; fi
for p in 7000 7199 9042; do ss -ltn | grep -q ":$p " && { log "ABORT: port $p busy"; exit 1; }; done
free=$(df -BG --output=avail /mydata | tail -1 | tr -dc 0-9); shm=$(df -BG --output=avail /dev/shm | tail -1 | tr -dc 0-9)
log "free /mydata ${free}G /dev/shm ${shm}G"
[ "$free" -ge "${NEED_G:-8}" ] || { log "ABORT: /mydata free ${free}G < ${NEED_G:-8}G"; exit 1; }
[ "$shm" -ge $(( ${HEAP%G} + 1 )) ] || { log "ABORT: /dev/shm free ${shm}G"; exit 1; }
# 2. wipe
rm -rf $T/data $T/logs
YAML_OPT=
if [ "$CAP0" = cap0 ]; then
  mkdir -p $R/conf; cp $T/conf/cassandra.yaml $R/conf/cassandra.yaml; printf '\npaxos_cache_size: 0MiB\n' >> $R/conf/cassandra.yaml
  YAML_OPT="-Dcassandra.config=file://$R/conf/cassandra.yaml"
fi
md5sum $T/conf/cassandra.yaml
# 3. start
( ulimit -n 100000; cd $T; MAX_HEAP_SIZE=$HEAP JVM_EXTRA_OPTS="$YAML_OPT" CASSANDRA_HEAPDUMP_DIR=$D exec systemd-run --user --scope -p MemorySwapMax=0 \
    --unit=b12-$RID -- bin/cassandra -f > $R/stdout.txt 2>&1 < /dev/null ) &
PID=
for i in $(seq 1 150); do
  sleep 2
  [ -z "$PID" ] && PID=$(pgrep -f "CassandraDaemon" | head -1)
  grep -q "Starting listening for CQL clients" $R/stdout.txt 2>/dev/null && break
  if [ -n "$PID" ] && ! kill -0 $PID 2>/dev/null; then log "INVALID: daemon died during start"; exit 1; fi
done
grep -q "Starting listening for CQL clients" $R/stdout.txt || { log "INVALID: no CQL in 300 s"; [ -n "$PID" ] && kill -9 $PID; exit 1; }
log "daemon pid $PID up"
echo $PID > $R/pid
# 4. flags and read-back
jcmd $PID VM.flags > $R/vm-flags.txt 2>&1
jcmd $PID VM.command_line > $R/vm-cmdline.txt 2>&1
python3 -I $H/client.py --settings > $R/settings.txt 2>&1
cat $R/settings.txt
# 5. DDL, baseline histogram
python3 -I $H/client.py --ddl || { log "INVALID: ddl failed"; kill $PID; }
sleep 3
timeout 120 jcmd $PID GC.class_histogram > $R/histo-0.txt 2>&1
milestone(){  # $1 = tag
  timeout 120 jcmd $PID GC.class_histogram > $R/histo-$1.txt 2>&1
  { echo "== $(date +%FT%T) $1"
    timeout 60 $NT tablestats system.paxos b12.t 2>&1 | grep -E "Table:|Memtable|SSTable count|Space used \(live\)|Number of partitions"
    for nm in MemtableOnHeapDataSize AllMemtablesOnHeapDataSize; do
      echo "system.paxos $nm $(timeout 30 $NT sjk mx -b org.apache.cassandra.metrics:type=Table,keyspace=system,scope=paxos,name=$nm -f Value --get 2>/dev/null | tail -1)"
    done
    timeout 60 $NT info 2>&1 | grep -iE "key cache|heap memory"
  } >> $R/milestones.txt
}
milestone 0
# 6. monitor + client
( setsid nohup $H/monitor.sh $PID $R $T < /dev/null > $R/monitor.err 2>&1 & )
log "client start"
python3 -I $H/client.py --cl $CLV --K $K --nmax $NMAX --m $M --out $R > $R/client.err 2>&1 &
CPID=$!
# 7. serve milestones
while kill -0 $CPID 2>/dev/null && kill -0 $PID 2>/dev/null; do
  for f in $R/ms-*.req; do
    [ -e "$f" ] || continue
    n=$(basename $f .req); n=${n#ms-}
    [ -e $R/ms-$n.done ] && continue
    log "milestone $n drained=$(cat $f)"
    milestone $n
    touch $R/ms-$n.done
  done
  sleep 1
done
if kill -0 $PID 2>/dev/null; then
  # 8. client ended, daemon alive
  log "client ended; daemon alive; hold 60 s"
  sleep 60
  kill -0 $PID 2>/dev/null && milestone end
  END=alive
  kill $PID
  for i in $(seq 1 60); do kill -0 $PID 2>/dev/null || break; sleep 1; done
  kill -0 $PID 2>/dev/null && { log "kill -9"; kill -9 $PID; }
else
  # 9. daemon died
  log "daemon gone while client running"
  END=daemon-exit
  for i in $(seq 1 40); do kill -0 $CPID 2>/dev/null || break; sleep 1; done
  kill $CPID 2>/dev/null
fi
wait $CPID 2>/dev/null
sleep 3
for i in $(seq 1 30); do systemctl --user is-active b12-$RID.scope >/dev/null 2>&1 || break; sleep 1; done
grep -qF "java.lang.OutOfMemoryError" $R/stdout.txt && END="$END oom:$(grep -m1 -F "java.lang.OutOfMemoryError" $R/stdout.txt | head -c 160)"
log "END $END"
# 10. logs, summary
cp $T/logs/system.log* $T/logs/debug.log* $T/logs/gc.log* $R/ 2>/dev/null
pkill -f "monitor.sh $PID" 2>/dev/null
du -sh $T/data >> $R/driver.txt 2>&1
python3 -I $H/summarize.py $R > $R/summary.txt 2>&1
ls -la $D >> $R/driver.txt
# 11. wipe data
rm -rf $T/data
log "done"
