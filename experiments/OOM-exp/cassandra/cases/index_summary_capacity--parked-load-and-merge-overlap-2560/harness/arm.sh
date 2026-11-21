#!/usr/bin/env bash
# R18 stage 2 arm script (2026-11-21; R10's arm.sh with the design §2.5 changes only). Usage:
#   arm.sh <arm> <heap_MiB> <L_MiB> <P 0|1> <Q -|Q4|Q7> <redistribute 0|1> <alter 0|1>
# Changes from R10: root /mydata/s4/r18, cluster_name r18, ports 27060/29060/27299, unit r18-<arm>-<epoch>; source sets from
# R10's pristine root (P7 P12 P21 Q1-Q4, read only, hardlinked) or R18's (Q7a-Q7d); Q set selectable; ALTER flag (IB: at
# t0 + 300 s `ALTER TABLE r10.isx WITH min_index_interval = 512`, read back, no Compacting line before it); observation after
# "Compacted" + 30 s (snaps +10, +30); no-Q arms observe to t0 + NOQ_END (620 s; Z: 0 = right after the idle snap);
# memory.stat ceiling sampler (memstat.sh, 1 s); stop by SIGTERM to the PID (<= 30 s) then SIGKILL; hard limit 960 s (A) /
# 1320 s (Q7 arms).
set -uo pipefail
R=/mydata/s4/r18; ARM=$1; HEAP=$2; L=$3; P=$4; QS=$5; RED=$6; ALT=$7
NOQ_END=${NOQ_END:-620}; QAT=270; ALTAT=300
case $QS in Q4) QSETS="Q1 Q2 Q3 Q4"; HARD=960;; Q7) QSETS="Q7a Q7b Q7c Q7d"; HARD=1320;; -) QSETS=""; HARD=960;; *) echo "bad Q $QS"; exit 2;; esac
SP=27060; NP=29060; JP=27299; CPUS=0,2,4,6,8,10,12,14,16,18,20,22,24,26,28,30
C=$R/node; A=$R/arms/$ARM; G=$R/gen; CP="$G:$C/build/apache-cassandra-5.0.9-SNAPSHOT.jar:$C/build/lib/jars/*"
srcof() { case $1 in Q7*) echo /mydata/s4/r18/data/pristine;; *) echo /mydata/s4/r10/data/pristine;; esac; }
[ -e "$A" ] && mv "$A" "$A.old-$(date +%s)"; mkdir -p $A/{data,commitlog,saved_caches,hints,logs}; S=$A/summary.txt
STG=$R/stage_node; [ -e $STG ] && { echo "INVALID: $STG exists (previous arm not cleaned)" >> $S; exit 2; }; mkdir -p $STG; ln -s $STG $A/stage
exec > >(tee -a $A/session.log) 2>&1
note() { echo "[$(date '+%F %T.%3N')] $*" | tee -a $S; }
ms() { date +%s%3N; }
SETS=""; [ $P = 1 ] && SETS="P7 P12 P21"; SETS="$SETS $QSETS"
note "arm $ARM heap $HEAP L $L P $P Q $QS redistribute $RED alter $ALT sets '$SETS' hard $HARD noq_end $NOQ_END script $(sha256sum $0 | cut -c1-12)"
note "pre: load $(cut -d' ' -f1-3 /proc/loadavg); mem $(free -m | awk '/Mem/{print "used="$3" avail="$7}'); disk $(df -h /mydata | awk 'NR==2{print $4}') free; daemons: $(pgrep -fc '[C]assandraDaemon'); java procs: $(pgrep -c java); EST $(TZ=America/New_York date '+%T')"
ss -ltn | grep -E ":($SP|$NP|$JP)\b" && { note "INVALID: ports in use"; exit 2; }
pgrep -f "java .*$C/.*CassandraDaemon" && { note "INVALID: daemon already running in $C"; exit 2; }
for x in $SETS; do SRC=$(srcof $x)
  cp -al $SRC/$x $STG/$x; for f in $STG/$x/*-Summary.db $STG/$x/*-Statistics.db; do cp --remove-destination $SRC/$x/$(basename $f) $f; done
  chmod u+w $STG/$x/*-Summary.db $STG/$x/*-Statistics.db
done
ls -l $STG/*/ > $A/stage-listing.txt 2>/dev/null
note "staged: $(for x in $SETS; do echo -n "$x summary=$(stat -c %s $STG/$x/*-Summary.db) cinfo=$(stat -c %s $STG/$x/*-CompressionInfo.db) data=$(stat -c %s $STG/$x/*-Data.db); "; done)"
sync; sudo -n sh -c 'echo 3 > /proc/sys/vm/drop_caches' && note "dropped page cache"
Y=$C/conf/cassandra.yaml; cp $R/logs/cassandra.yaml.shipped $Y
sed -i -e "s/^cluster_name: 'Test Cluster'/cluster_name: 'r18'/" -e "s/^listen_address: localhost/listen_address: 127.0.0.1/" -e "s/^rpc_address: localhost/rpc_address: 127.0.0.1/" \
  -e "s/- seeds: \"127.0.0.1:7000\"/- seeds: \"127.0.0.1:$SP\"/" -e "s/^storage_port: 7000/storage_port: $SP/" -e "s/^native_transport_port: 9042/native_transport_port: $NP/" \
  -e "s|^# data_file_directories:|data_file_directories:|" -e "s|^#     - /var/lib/cassandra/data|     - $A/data|" \
  -e "s|^# commitlog_directory: /var/lib/cassandra/commitlog|commitlog_directory: $A/commitlog|" \
  -e "s|^# saved_caches_directory: /var/lib/cassandra/saved_caches|saved_caches_directory: $A/saved_caches|" \
  -e "s|^# hints_directory: /var/lib/cassandra/hints|hints_directory: $A/hints|" $Y
diff $R/logs/cassandra.yaml.shipped $Y > $A/cassandra.yaml.diff; nd=$(grep -c '^>' $A/cassandra.yaml.diff)
bad=$(grep '^>' $A/cassandra.yaml.diff | grep -vE "cluster_name|listen_address|rpc_address|seeds|storage_port|native_transport_port|data_file_directories|$A/" )
[ -n "$bad" ] && { note "INVALID: non-environment yaml line: $bad"; exit 2; }
note "yaml diff lines: $nd (environment only)"
export MAX_HEAP_SIZE=${HEAP}M CASSANDRA_LOG_DIR=$A/logs MAX_DIRECT_MEMORY_SIZE=$((L/4))M; unset HEAP_NEWSIZE
NC=$(echo $CPUS | tr , '\n' | wc -l)
export JVM_EXTRA_OPTS="-XX:NativeMemoryTracking=summary -XX:ParallelGCThreads=$NC -XX:ConcGCThreads=$NC -Dcassandra.jmx.local.port=$JP"
UNIT="r18-$ARM-$(date +%s)"; echo $UNIT > $A/unit.txt
T0=$(ms); echo $T0 > $A/t0.txt
( setsid nohup systemd-run --user --scope --unit=$UNIT -p MemoryMax=${L}M -p MemorySwapMax=0 -- taskset -c $CPUS $C/bin/cassandra -f < /dev/null > $A/stdout.txt 2>&1 & )
PID=""; SAMP=""; CG=""
for i in $(seq 180); do
  [ -z "$PID" ] && PID=$(pgrep -f "java .*-Dcassandra.jmx.local.port=$JP.*CassandraDaemon" | head -1)
  if [ -n "$PID" ] && [ -z "$SAMP" ]; then
    CG=$(find /sys/fs/cgroup/user.slice/user-$(id -u).slice/user@$(id -u).service -maxdepth 3 -type d -name "$UNIT.scope" | head -1)
    setsid nohup taskset -c 17,19,21,23,25,27,29,31 bash $G/sampler.sh $PID $CG $A/sampler.csv 0.2 < /dev/null > /dev/null 2>&1 & SAMP=$!
    setsid nohup taskset -c 17,19,21,23,25,27,29,31 bash $G/smaps.sh $PID $A/smaps.csv 1 < /dev/null > /dev/null 2>&1 &
    setsid nohup taskset -c 17,19,21,23,25,27,29,31 bash $G/memstat.sh $PID $CG $A/memstat.csv 1 < /dev/null > /dev/null 2>&1 &
  fi
  grep -q 'Starting listening for CQL clients' $A/logs/system.log 2>/dev/null && break; sleep 1
done
grep -q 'Starting listening for CQL clients' $A/logs/system.log 2>/dev/null || { note "INVALID: CQL not up in 180 s"; [ -n "$PID" ] && kill -9 $PID; systemctl --user stop $UNIT.scope 2>/dev/null; exit 2; }
note "up after $(( ($(ms)-T0)/1000 )) s: pid $PID unit $UNIT cg $CG memory.max $(cat $CG/memory.max) swap.max $(cat $CG/memory.swap.max)"
setsid nohup bash $G/cstats.sh $C/bin/nodetool $JP $PID $A/cstats.txt < /dev/null > /dev/null 2>&1 &
tr '\0' '\n' < /proc/$PID/cmdline > $A/jvm-args.txt
note "readback: $(grep -E '^-Xm[xs]|MaxDirectMemorySize|GCThreads|AlwaysPreTouch|jmx.local.port|UseG1' $A/jvm-args.txt | tr '\n' ' ')"
note "readback log: $(grep -hoE 'memory pool size of [0-9]+ MB and a resize interval of [0-9]+ minutes|Global buffer pool limit is [^ ]+ |networking_cache_size=[^;,]*|file_cache_enabled=[^;,]*|index_summary_capacity=[^;,]*|index_summary_resize_interval=[^;,]*|disk_access_mode=[^;,]*|memtable_allocation_type=[^;,]*|compaction_throughput=[^;,]*|concurrent_compactors=[^;,]*|sstable_preemptive_open_interval=[^;,]*|storage_compatibility_mode=[^;,]*|row_cache_size=[^;,]*' $A/logs/system.log | sort -u | tr '\n' '|')"
note "readback compactors: $(timeout 30 $C/bin/nodetool -p $JP getconcurrentcompactors 2>&1 | tr '\n' ' ') throughput: $(timeout 30 $C/bin/nodetool -p $JP getcompactionthroughput 2>&1 | tr '\n' ' ')"
note "affinity: $(taskset -pc $PID | sed 's/.*: //')"
for i in 1 2 3 4 5; do $C/bin/cqlsh --connect-timeout=30 --request-timeout=60 127.0.0.1 $NP -e "CREATE KEYSPACE IF NOT EXISTS r10 WITH replication = {'class':'SimpleStrategy','replication_factor':1}; CREATE TABLE IF NOT EXISTS r10.isx (pk text PRIMARY KEY, v int);" >> $A/cqlsh.txt 2>&1 && break; sleep 3; done; note "cqlsh attempts $i"
grep -q "Table: isx" <(timeout 60 $C/bin/nodetool -p $JP tablestats r10.isx 2>&1) || { note "INVALID: table r10.isx not created"; kill -9 $PID; systemctl --user stop $UNIT.scope; exit 2; }
snap() { local t=$1 full=${2:-1}
  if kill -0 $PID 2>/dev/null; then
    note "rss $t: $(grep -E '^(RssAnon|VmRSS|RssFile|VmHWM)' /proc/$PID/status 2>/dev/null | tr -s '\t ' ' ' | tr '\n' ' ') cg: cur=$(cat $CG/memory.current 2>/dev/null) $(grep -E '^(anon|file|file_mapped|kernel_stack|pagetables|slab|sock) ' $CG/memory.stat 2>/dev/null | tr '\n' ' ') ev: $(grep -E '^(max|oom|oom_kill) ' $CG/memory.events 2>/dev/null | tr '\n' ' ')"
    timeout 30 $C/bin/nodetool -p $JP tablestats r10.isx > $A/tablestats-$t.txt 2>&1
    note "tablestats $t: $(grep -E 'SSTable count|Off heap memory used|Bloom filter off heap|Index summary off heap|Compression metadata off heap' $A/tablestats-$t.txt | tr -s ' \t' ' ' | tr '\n' '|')"
    timeout 30 java -cp $CP ISSampler attrs $JP > $A/is-$t.txt 2>&1; note "is $t: $(grep ATTRS $A/is-$t.txt)"
    if [ $full = 1 ]; then timeout 30 jcmd $PID VM.native_memory summary scale=MB > $A/nmt-$t.txt 2>&1
      note "nmt $t: $(grep -E '^Total:|^-  *(Java Heap|Class|Thread|Code|GC|Internal|Other|Symbol|Arena Chunk|Native Memory Tracking) ' $A/nmt-$t.txt | sed -E 's/\(reserved=[0-9]+MB, //; s/^- +//; s/ +/ /g' | tr '\n' '|')"; fi
  else note "$t: process gone"; fi; }
waituntil() { while [ $(ms) -lt $1 ]; do kill -0 $PID 2>/dev/null || return 1; sleep 1; done; }
deadline() { [ $(( $(ms) - T0 )) -ge $((HARD*1000)) ]; }
# idle
waituntil $(( $(ms) + 60000 )); snap idle
I0=$(awk -F, -v t=$(( $(ms) - 30000 )) 'NR>1 && $1>=t && $2!="" {print $2}' $A/sampler.csv | sort -n | awk '{a[NR]=$1}END{print a[int((NR+1)/2)]}'); note "I0 (median RssAnon last 30 s) = $I0 kB = $((I0/1024)) MiB"
note "memstat idle (last row): $(tail -1 $A/memstat.csv)"
imp() { local tag=$1; shift; local d=""; for x in "$@"; do d="$d $STG/$x"; done
  local a=$(ms); note "import $tag start $a: nodetool import -q r10 isx$d"
  timeout 900 $C/bin/nodetool -p $JP import -q r10 isx $d > $A/import-$tag.txt 2>&1; local rc=$?; local b=$(ms)
  note "import $tag end $b rc $rc dur $(( (b-a)/1000 )) s: $(tr '\n' ' ' < $A/import-$tag.txt | cut -c1-300)"; }
if [ $P = 1 ]; then waituntil $((T0+150000)) && { imp P P7 P12 P21; TP=$(ms); waituntil $((TP+30000)) && snap postP 0; }; fi
if [ $RED = 1 ]; then waituntil $((T0+210000)) && { note "redistribute start"; timeout 300 java -cp $CP ISSampler invoke $JP > $A/redistribute.txt 2>&1; note "redistribute rc $?: $(grep -E 'BEFORE|INVOKED|AFTER' $A/redistribute.txt | tr '\n' ' ')"; TR=$(ms); waituntil $((TR+20000)) && snap postR 0; }; fi
ENDREASON=""
if [ -n "$QSETS" ]; then
  waituntil $((T0+QAT*1000)) && { imp Q $QSETS; TQ=$(ms); }
  if [ $ALT = 1 ]; then waituntil $((T0+ALTAT*1000)) && {
      PRE=$(grep -h 'Compacting (' $A/logs/system.log 2>/dev/null | grep -c isx)
      a=$(ms); $C/bin/cqlsh --connect-timeout=30 --request-timeout=60 127.0.0.1 $NP -e "ALTER TABLE r10.isx WITH min_index_interval = 512;" > $A/alter.txt 2>&1; arc=$?; b=$(ms)
      $C/bin/cqlsh --connect-timeout=30 --request-timeout=60 127.0.0.1 $NP -e "SELECT min_index_interval, max_index_interval FROM system_schema.tables WHERE keyspace_name='r10' AND table_name='isx';" > $A/alter-readback.txt 2>&1
      POST=$(grep -h 'Compacting (' $A/logs/system.log 2>/dev/null | grep -c isx)
      note "alter start $a end $b rc $arc: $(tr '\n' ' ' < $A/alter.txt | cut -c1-200) readback: $(tr -s ' \n' ' ' < $A/alter-readback.txt | cut -c1-200) compacting lines before/after: $PRE/$POST"
      [ "$PRE" != 0 ] && { note "INVALID: merge started before the ALTER"; ENDREASON=alterlate; }; }; fi
  # wait for the background compaction (default backstop; no manual trigger)
  TC=""; while kill -0 $PID 2>/dev/null; do
    TC=$(grep -h 'Compacting (' $A/logs/system.log 2>/dev/null | grep isx | head -1); [ -n "$TC" ] && break
    [ $(( $(ms) - T0 )) -ge 480000 ] && break; sleep 1; done
  if [ -n "$TC" ]; then note "compaction started: $(echo "$TC" | cut -c1-400)"
    while kill -0 $PID 2>/dev/null; do grep -h 'Compacted (' $A/logs/system.log 2>/dev/null | grep -q isx && break; deadline && { ENDREASON=overtime; break; }; sleep 1; done
    TE=$(ms); CD=$(grep -h 'Compacted (' $A/logs/system.log 2>/dev/null | grep isx | head -1)
    [ -n "$CD" ] && note "compaction done: $(echo "$CD" | cut -c1-700)"
  else kill -0 $PID 2>/dev/null && { note "INVALID: no Compacting line by t0+480 s"; ENDREASON=nocompaction; }; TE=$(ms); fi
else
  waituntil $((T0+NOQ_END*1000-30000)); TE=$(ms)
fi
if kill -0 $PID 2>/dev/null; then waituntil $((TE+10000)) && snap +10; waituntil $((TE+30000)) && snap +30 0; fi
note "end reason: ${ENDREASON:-normal}"
PEAK=$(awk -F, 'NR>1 && $2!="" {if ($2>m) m=$2} END{print m}' $A/sampler.csv); note "peak RssAnon $PEAK kB; dRssAnon(peak - I0) = $(( (PEAK - I0)/1024 )) MiB"
note "cgroup last rows: $(tail -2 $A/sampler.csv | tr '\n' ' ')"
note "memstat last live rows: $(awk -F, 'NR>1 && $2!=""' $A/memstat.csv | tail -2 | tr '\n' ' ')"
ALIVE=0; kill -0 $PID 2>/dev/null && ALIVE=1; note "alive at end: $ALIVE"
if [ $ALIVE = 1 ]; then kill $PID; for i in $(seq 30); do kill -0 $PID 2>/dev/null || break; sleep 1; done; kill -0 $PID 2>/dev/null && { note "kill -9 $PID"; kill -9 $PID; }; fi
sleep 2; kill $SAMP 2>/dev/null; systemctl --user stop $UNIT.scope 2>/dev/null
note "scope gone: $(systemctl --user is-active $UNIT.scope 2>&1)"
sudo -n dmesg | awk -v u="$UNIT" '/invoked oom-killer/{buf=""; on=1} on{buf=buf $0 "\n"} /Killed process/ && on{ if (index(buf,u)) printf "%s", buf; on=0 }' > $A/dmesg-block.txt
note "dmesg: $(grep -E 'invoked oom-killer|oom-kill:|Killed process' $A/dmesg-block.txt | tr '\n' ' ' | cut -c1-700)"
grep -hE 'Loading new SSTables|Done loading|Initializing index summary manager|Redistributing index summaries|Completed resizing|Compacting \(|Compacted \(|ERROR|OutOfMemory|Opening .*isx|min_index_interval' $A/logs/system.log $A/logs/debug.log 2>/dev/null | cut -c1-400 > $A/log-excerpt.txt
note "log: redistributions: $(grep -hc 'Redistributing index summaries' $A/logs/debug.log $A/logs/system.log 2>/dev/null | paste -sd+); errors: $(grep -hc ERROR $A/logs/system.log)"
note "import order: $(grep -h "Opening .*/stage_node/" $A/logs/debug.log 2>/dev/null | grep -oE "stage_node/[PQ][0-9a-d]+" | tr "\n" " ")"
note "data dir after: $(find $A/data -name '*-Data.db' -printf '%s ' 2>/dev/null) summaries: $(find $A/data -name '*-Summary.db' -printf '%f=%s ' 2>/dev/null)"
rm -rf $STG $A/stage $A/data $A/commitlog $A/saved_caches $A/hints
note "done arm $ARM"
