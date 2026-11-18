#!/usr/bin/env bash
# C4 stage 2 arm script (2026-11-17). Usage:
#   arm.sh <arm> <heap_MiB> <L_MiB|none> <set list, e.g. DCBA> [<src dir, default data/pristine>] [node|helper] [extra yaml file]
# victim: node/ (ports 27040/29040/JMX 27099), scope MemoryMax=L, MemorySwapMax=0; helper: helper/ (27041/29041/27098), no limit.
# Steps per design §2.5: stage (hardlinks + real copies of Summary.db/Statistics.db), start in a fresh scope, read back,
# create table, idle 60 s, import -q in order D C B A, observe 120 s, stop, save dmesg block and log excerpts, clean.
set -uo pipefail
R=/mydata/s4/c4-w1; ARM=$1; HEAP=$2; L=$3; SETS=$4; SRC=${5:-$R/data/pristine}; ROLE=${6:-node}; EXTRA=${7:-}
QUICK=${QUICK--q}; OBS=${OBS:-120}; IDLE=${IDLE:-60}; KEEP=${KEEP:-0}
if [ "$ROLE" = node ]; then SP=27040; NP=29040; JP=27099; CPUS=0,2,4,6,8,10,12,14,16,18,20,22,24,26,28,30; else SP=27041; NP=29041; JP=27098; CPUS=17,19,21,23,25,27,29,31; fi
C=$R/$ROLE; A=$R/arms/$ARM; G=$R/gen; CP="$G:$C/build/apache-cassandra-5.0.9-SNAPSHOT.jar:$C/build/lib/jars/*"
[ -e "$A" ] && mv "$A" "$A.old-$(date +%s)"; mkdir -p $A/{data,commitlog,saved_caches,hints,logs}; S=$A/summary.txt
# amendment 5: nodetool import keeps its source paths in a hash set, so the load order follows the path strings; stage at a
# fixed path per role so every arm with the same sets loads them in the same order (order recorded from system.log).
STG=$R/stage_$ROLE; [ -e $STG ] && { echo "INVALID: $STG exists (previous arm not cleaned)"; exit 2; }; mkdir -p $STG; ln -s $STG $A/stage
exec > >(tee -a $A/session.log) 2>&1
note() { echo "[$(date '+%F %T.%3N')] $*" | tee -a $S; }
ms() { date +%s%3N; }
note "arm $ARM heap $HEAP L $L sets $SETS src $SRC role $ROLE quick '$QUICK' extra '$EXTRA' script $(sha256sum $0 | cut -c1-12)"
note "pre: load $(cut -d' ' -f1-3 /proc/loadavg); mem $(free -m | awk '/Mem/{print "used="$3" avail="$7}'); disk $(df -h /mydata | awk 'NR==2{print $4}') free; daemons: $(pgrep -fc '[C]assandraDaemon')"
ss -ltn | grep -E ":($SP|$NP|$JP)\b" && { note "INVALID: ports in use"; exit 2; }
pgrep -f "java .*$C/.*CassandraDaemon" && { note "INVALID: daemon already running in $C"; exit 2; }
# staging
for x in $(echo $SETS | grep -o .); do
  cp -al $SRC/$x $A/stage/$x; for f in $A/stage/$x/*-Summary.db $A/stage/$x/*-Statistics.db; do cp --remove-destination $SRC/$x/$(basename $f) $f; done
  chmod u+w $A/stage/$x/*-Summary.db $A/stage/$x/*-Statistics.db
done
ls -l $A/stage/*/ > $A/stage-listing.txt
note "staged: $(for x in $(echo $SETS | grep -o .); do echo -n "$x summary=$(stat -c %s $A/stage/$x/*-Summary.db) filter=$(stat -c %s $A/stage/$x/*-Filter.db) cinfo=$(stat -c %s $A/stage/$x/*-CompressionInfo.db); "; done)"
# yaml (environment edits only; EXTRA sed script only for the helper's intervention-set run)
# NOTE: install new versions with cp to a temp file + mv (bash reads a running script by offset)
Y=$C/conf/cassandra.yaml; cp $R/logs/cassandra.yaml.shipped $Y
sed -i -e "s/^cluster_name: 'Test Cluster'/cluster_name: 'c4w1'/" -e "s/^listen_address: localhost/listen_address: 127.0.0.1/" -e "s/^rpc_address: localhost/rpc_address: 127.0.0.1/" \
  -e "s/- seeds: \"127.0.0.1:7000\"/- seeds: \"127.0.0.1:$SP\"/" -e "s/^storage_port: 7000/storage_port: $SP/" -e "s/^native_transport_port: 9042/native_transport_port: $NP/" \
  -e "s|^# data_file_directories:|data_file_directories:|" -e "s|^#     - /var/lib/cassandra/data|     - $A/data|" \
  -e "s|^# commitlog_directory: /var/lib/cassandra/commitlog|commitlog_directory: $A/commitlog|" \
  -e "s|^# saved_caches_directory: /var/lib/cassandra/saved_caches|saved_caches_directory: $A/saved_caches|" \
  -e "s|^# hints_directory: /var/lib/cassandra/hints|hints_directory: $A/hints|" $Y
[ -n "$EXTRA" ] && sed -i -f $EXTRA $Y   # EXTRA = a sed script (helper only: intervention-set yaml)
diff $R/logs/cassandra.yaml.shipped $Y > $A/cassandra.yaml.diff; nd=$(grep -c '^>' $A/cassandra.yaml.diff)
bad=$(grep '^>' $A/cassandra.yaml.diff | grep -vE "cluster_name|listen_address|rpc_address|seeds|storage_port|native_transport_port|data_file_directories|$A/" )
if [ -n "$bad" ] && [ -z "$EXTRA" ]; then note "INVALID: non-environment yaml line: $bad"; exit 2; fi
note "yaml diff lines: $nd (extra: $(cat ${EXTRA:-/dev/null} | tr '\n' ' '))"
# start
export MAX_HEAP_SIZE=${HEAP}M CASSANDRA_LOG_DIR=$A/logs; unset HEAP_NEWSIZE
[ "$L" != none ] && export MAX_DIRECT_MEMORY_SIZE=$((L/4))M || export MAX_DIRECT_MEMORY_SIZE=$((HEAP/2))M
export JVM_EXTRA_OPTS="-XX:NativeMemoryTracking=summary -XX:ParallelGCThreads=$(echo $CPUS | tr , '\n' | wc -l) -XX:ConcGCThreads=$(echo $CPUS | tr , '\n' | wc -l) -Dcassandra.jmx.local.port=$JP"
UNIT="c4w1-$ARM-$(date +%s)"; echo $UNIT > $A/unit.txt
if [ "$L" = none ]; then
  ( setsid nohup systemd-run --user --scope --unit=$UNIT -- taskset -c $CPUS $C/bin/cassandra -f < /dev/null > $A/stdout.txt 2>&1 & )
else
  ( setsid nohup systemd-run --user --scope --unit=$UNIT -p MemoryMax=${L}M -p MemorySwapMax=0 -- taskset -c $CPUS $C/bin/cassandra -f < /dev/null > $A/stdout.txt 2>&1 & )
fi
T0=$(ms); PID=""
for i in $(seq 180); do
  [ -z "$PID" ] && PID=$(pgrep -f "java .*-Dcassandra.jmx.local.port=$JP.*CassandraDaemon" | head -1)
  grep -q 'Starting listening for CQL clients' $A/logs/system.log 2>/dev/null && break; sleep 1
done
grep -q 'Starting listening for CQL clients' $A/logs/system.log 2>/dev/null || { note "INVALID: CQL not up in 180 s"; [ -n "$PID" ] && kill -9 $PID; systemctl --user stop $UNIT.scope 2>/dev/null; exit 2; }
CG=$(find /sys/fs/cgroup/user.slice/user-$(id -u).slice/user@$(id -u).service -maxdepth 3 -type d -name "$UNIT.scope" | head -1)
note "up after $(( ($(ms)-T0)/1000 )) s: pid $PID unit $UNIT cg $CG memory.max $(cat $CG/memory.max) swap.max $(cat $CG/memory.swap.max)"
setsid nohup $R/gen/sampler.sh $PID $CG $A/sampler.csv < /dev/null > /dev/null 2>&1 & SAMP=$!
tr '\0' '\n' < /proc/$PID/cmdline > $A/jvm-args.txt
note "readback: $(grep -E '^-Xm[xs]|MaxDirectMemorySize|GCThreads|AlwaysPreTouch|jmx.local.port|UseG1' $A/jvm-args.txt | tr '\n' ' ')"
note "readback log: $(grep -hoE 'memory pool size of [0-9]+ MB and a resize interval of [0-9]+ minutes|Global buffer pool limit is [^ ]+ |networking_cache_size=[^;,]*|file_cache_enabled=[^;,]*|index_summary_capacity=[^;,]*|index_summary_resize_interval=[^;,]*|disk_access_mode=[^;,]*|memtable_allocation_type=[^;,]*' $A/logs/system.log | sort -u | tr '\n' '|')"
POOL=$(grep -hoE 'memory pool size of [0-9]+ MB' $A/logs/system.log | grep -oE '[0-9]+' | head -1); echo "$POOL" > $A/pool-mb.txt
note "affinity: $(taskset -pc $PID | sed 's/.*: //')"
for i in 1 2 3 4 5; do $C/bin/cqlsh --connect-timeout=30 --request-timeout=60 127.0.0.1 $NP -e "CREATE KEYSPACE IF NOT EXISTS c4 WITH replication = {'class':'SimpleStrategy','replication_factor':1}; CREATE TABLE IF NOT EXISTS c4.isx (pk text PRIMARY KEY, v int);" >> $A/cqlsh.txt 2>&1 && break; sleep 3; done; note "cqlsh attempts $i"
grep -q "Table: isx" <(timeout 60 $C/bin/nodetool -p $JP tablestats c4.isx 2>&1) || { note "INVALID: table c4.isx not created"; kill -9 $PID; systemctl --user stop $UNIT.scope; exit 2; }
snap() { local t=$1
  if kill -0 $PID 2>/dev/null; then
    note "rss $t: $(grep -E '^(RssAnon|VmRSS|RssFile|VmHWM)' /proc/$PID/status 2>/dev/null | tr -s '\t ' ' ' | tr '\n' ' ') cg: cur=$(cat $CG/memory.current 2>/dev/null) $(grep -E '^(anon|file) ' $CG/memory.stat 2>/dev/null | tr '\n' ' ') ev: $(grep -E '^(max|oom|oom_kill) ' $CG/memory.events 2>/dev/null | tr '\n' ' ')"
    timeout 30 $C/bin/nodetool -p $JP tablestats c4.isx > $A/tablestats-$t.txt 2>&1
    note "tablestats $t: $(grep -E 'SSTable count|Off heap memory used|Bloom filter off heap|Index summary off heap|Compression metadata off heap' $A/tablestats-$t.txt | tr -s ' \t' ' ' | tr '\n' '|')"
    timeout 30 java -cp $CP ISSampler attrs $JP > $A/is-$t.txt 2>&1; note "is $t: $(grep ATTRS $A/is-$t.txt)"
    timeout 30 jcmd $PID VM.native_memory summary scale=MB > $A/nmt-$t.txt 2>&1
    note "nmt $t: $(grep -E '^Total:|^-  *(Java Heap|Class|Thread|Code|GC|Internal|Other|Symbol|Arena Chunk|Native Memory Tracking) ' $A/nmt-$t.txt | sed -E 's/\(reserved=[0-9]+MB, //; s/^- +//; s/ +/ /g' | tr '\n' '|')"
  else note "$t: process gone"; fi; }
sleep $IDLE; snap idle
I0=$(awk -F, -v t=$(( $(ms) - 30000 )) 'NR>1 && $1>=t && $2!="" {print $2}' $A/sampler.csv | sort -n | awk '{a[NR]=$1}END{print a[int((NR+1)/2)]}'); note "I0 (median RssAnon last 30 s) = $I0 kB"
# import (order D C B A)
DIRS=""; for x in D C B A; do [[ "$SETS" == *$x* ]] && DIRS="$DIRS $STG/$x"; done
TI0=$(ms); note "import start $TI0: nodetool import $QUICK c4 isx$DIRS"
timeout 1800 $C/bin/nodetool -p $JP import $QUICK c4 isx $DIRS > $A/import.txt 2>&1; RC=$?; TI1=$(ms)
note "import end $TI1 rc $RC dur $(( (TI1-TI0)/1000 )) s: $(tr '\n' ' ' < $A/import.txt | cut -c1-400)"
if [ -n "${POSTIMPORT:-}" ] && kill -0 $PID 2>/dev/null; then note "post-import: $POSTIMPORT"; ( export A JP CP PID; eval "$POSTIMPORT" ) > $A/postimport.txt 2>&1; note "post-import rc $?: $(tr '\n' ' ' < $A/postimport.txt | cut -c1-900)"; fi
for t in 10 60 $OBS; do
  kill -0 $PID 2>/dev/null || break
  while [ $(( $(ms) - TI1 )) -lt $((t*1000)) ]; do sleep 1; kill -0 $PID 2>/dev/null || break; done
  snap +$t
done
PEAK=$(awk -F, 'NR>1 && $2!="" {if ($2>m) m=$2} END{print m}' $A/sampler.csv); note "peak RssAnon $PEAK kB; dRssAnon(peak - I0) = $(( (PEAK - I0)/1024 )) MiB"
note "cgroup last rows: $(tail -2 $A/sampler.csv | tr '\n' ' ')"
ALIVE=0; kill -0 $PID 2>/dev/null && ALIVE=1; note "alive at end: $ALIVE"
# stop
if [ $ALIVE = 1 ]; then timeout 60 $C/bin/nodetool -p $JP stopdaemon > /dev/null 2>&1; for i in $(seq 60); do kill -0 $PID 2>/dev/null || break; sleep 1; done; kill -0 $PID 2>/dev/null && { note "kill -9 $PID"; kill -9 $PID; }; fi
sleep 2; kill $SAMP 2>/dev/null; systemctl --user stop $UNIT.scope 2>/dev/null
note "scope gone: $(systemctl --user is-active $UNIT.scope 2>&1)"
sudo -n dmesg | awk -v u="$UNIT" '/invoked oom-killer/{buf=""; on=1} on{buf=buf $0 "\n"} /Killed process/ && on{ if (index(buf,u)) printf "%s", buf; on=0 }' > $A/dmesg-block.txt
note "dmesg: $(grep -E 'oom-kill:|Killed process' $A/dmesg-block.txt | tr '\n' ' ' | cut -c1-600)"
grep -hE 'Loading new SSTables|Done loading|Initializing index summary manager|Redistributing index summaries|Completed resizing|ERROR|OutOfMemory|Opening .*isx' $A/logs/system.log $A/logs/debug.log 2>/dev/null | cut -c1-300 > $A/log-excerpt.txt
note "log: last isx open: $(grep -h 'Opening .*isx' $A/logs/debug.log 2>/dev/null | tail -1 | cut -c1-250); redistributions: $(grep -hc 'Redistributing index summaries' $A/logs/debug.log $A/logs/system.log 2>/dev/null | paste -sd+); errors: $(grep -hc ERROR $A/logs/system.log)"
note "import order: $(grep -h "Opening .*/stage_$ROLE/" $A/logs/debug.log 2>/dev/null | grep -oE "stage_$ROLE/[A-D]" | tr "\n" " ")"
[ $KEEP = 0 ] && rm -rf $STG $A/stage $A/data $A/commitlog $A/saved_caches $A/hints
note "done arm $ARM"
