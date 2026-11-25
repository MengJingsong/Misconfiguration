#!/usr/bin/env bash
# 3-b confirm C4 (pc99, 2026-11-24): node control and one lifetime per call. Single node as in stage 2: container
# MemoryMax=2048M / swap 0, heap 1024, direct 512, NMT summary, GC threads 16, even CPUs 0-30 (stage-2 settings);
# yaml = shipped + environment lines + authenticator PasswordAuthenticator / authorizer CassandraAuthorizer.
# Clients (attacker, victim, admin, JMX monitor) on odd CPUs, each in its own scope (isolation only).
#   c4.sh tpl                       fresh node: roles, victim keyspace, victim preload, probes (nogrant, pre-auth); drain -> template
#   c4.sh attack <label> <min_index_interval> <maxRows> [max_index_interval]
#   c4.sh restart <label> <src label> [watch secs]   start on <src>'s data in place (admin restart), victim on, watch
#   c4.sh redist <label>            diagnostic (admin JMX): attacker tables at min 1 / max 2048 and min 1 / max 1, flush, redistribute
#   c4.sh stop <label>
set -uo pipefail
ROOT=/mydata/s4/3b-C4; T=$ROOT/tree; H=$ROOT/harness
SP=27050; NP=29050; JP=27199; L=2048; HEAP=1024
NCPUS=0,2,4,6,8,10,12,14,16,18,20,22,24,26,28,30; CCPUS=1,3,5,7,9,11,13,15
J=$T/build/lib/jars
CP="$ROOT/cls:$J/cassandra-driver-core-3.12.1-shaded.jar:$J/guava-32.0.1-jre.jar:$J/metrics-core-4.2.28.jar:$T/build/apache-cassandra-5.0.9-SNAPSHOT.jar:$T/lib/*"
log(){ echo "[$(TZ=America/New_York date '+%F %T.%3N %Z')] $*" | tee -a "$R/run.log"; }
ms(){ date +%s%3N; }
cli(){ # <unit tag> <user> <pass> <args...>   (foreground)
  local tag=$1 u=$2 p=$3; shift 3
  taskset -c $CCPUS systemd-run --user --scope --quiet --unit="3bc4-cli-$tag-$(date +%s%N | cut -c1-13)" -p MemoryMax=8G -p MemorySwapMax=0 \
    java -Xmx2g -Dc4.port=$NP -Dc4.user="$u" -Dc4.pass="$p" -Dlogback.configurationFile=$H/logback.xml -cp "$CP" C4Client "$@"
}
nodepid(){ pgrep -f "java .*-Dcassandra.jmx.local.port=$JP.*CassandraDaemon" | head -1; }

mkconf(){ # <R> <node root>
  local R=$1 N=$2; rm -rf "$R/conf"; cp -r "$ROOT/conf-pristine" "$R/conf"; local y=$R/conf/cassandra.yaml
  sed -i -e "s/^cluster_name: 'Test Cluster'/cluster_name: 'c4b3'/" -e "s/^listen_address: localhost/listen_address: 127.0.0.1/" \
    -e "s/^rpc_address: localhost/rpc_address: 127.0.0.1/" -e "s/- seeds: \"127.0.0.1:7000\"/- seeds: \"127.0.0.1:$SP\"/" \
    -e "s/^storage_port: 7000/storage_port: $SP/" -e "s/^native_transport_port: 9042/native_transport_port: $NP/" \
    -e "s|^# data_file_directories:|data_file_directories:|" -e "s|^#     - /var/lib/cassandra/data|     - $N/data|" \
    -e "s|^# commitlog_directory: /var/lib/cassandra/commitlog|commitlog_directory: $N/commitlog|" \
    -e "s|^# saved_caches_directory: /var/lib/cassandra/saved_caches|saved_caches_directory: $N/saved_caches|" \
    -e "s|^# hints_directory: /var/lib/cassandra/hints|hints_directory: $N/hints|" \
    -e "s|^authenticator: AllowAllAuthenticator|authenticator: PasswordAuthenticator|" \
    -e "s|^authorizer: AllowAllAuthorizer|authorizer: CassandraAuthorizer|" "$y"
  diff "$ROOT/conf-pristine/cassandra.yaml" "$y" > "$R/yaml.diff"
  local bad; bad=$(grep '^>' "$R/yaml.diff" | grep -vE "cluster_name|listen_address|rpc_address|seeds|storage_port|native_transport_port|data_file_directories|$N/|authenticator: PasswordAuthenticator|authorizer: CassandraAuthorizer")
  [ -n "$bad" ] && { echo "INVALID yaml line: $bad"; return 1; }
  return 0
}

start(){ # <R> <node root>   -> prints UP / DIED
  local R=$1 N=$2
  [ -n "$(nodepid)" ] && { log "INVALID: a C4 daemon already runs"; return 2; }
  ss -ltn | grep -qE ":($SP|$NP|$JP)\b" && { log "INVALID: ports in use"; return 2; }
  mkdir -p "$N"/{data,commitlog,saved_caches,hints} "$R/logs"
  mkconf "$R" "$N" || return 2
  export CASSANDRA_CONF=$R/conf CASSANDRA_LOG_DIR=$R/logs MAX_HEAP_SIZE=${HEAP}M MAX_DIRECT_MEMORY_SIZE=$((L/4))M; unset HEAP_NEWSIZE
  export JVM_EXTRA_OPTS="-XX:NativeMemoryTracking=summary -XX:ParallelGCThreads=16 -XX:ConcGCThreads=16 -Dcassandra.jmx.local.port=$JP"
  UNIT="3bc4-$(basename $R)-$(date +%s)"; echo "$UNIT" > "$R/unit.txt"
  log "pre: load $(cut -d' ' -f1-3 /proc/loadavg); mem $(free -m | awk '/Mem/{print "avail="$7}'); daemons $(pgrep -fc '[C]assandraDaemon'); unit $UNIT node root $N ($(du -sh $N | cut -f1))"
  ( setsid nohup systemd-run --user --scope --unit=$UNIT -p MemoryMax=${L}M -p MemorySwapMax=0 -- taskset -c $NCPUS $T/bin/cassandra -f < /dev/null > $R/stdout.txt 2>&1 & )
  local T0; T0=$(ms); PID=""
  for i in $(seq 40); do PID=$(nodepid); [ -n "$PID" ] && break; sleep 0.5; done
  echo "$PID" > "$R/node.pid"; date +%s%3N > "$R/node.start"
  CG=$(find /sys/fs/cgroup/user.slice/user-$(id -u).slice/user@$(id -u).service -maxdepth 3 -type d -name "$UNIT.scope" | head -1)
  echo "$CG" > "$R/cg.txt"
  ( setsid nohup bash $H/sampler.sh "$PID" "$CG" "$R/sampler.csv" 0.2 < /dev/null > /dev/null 2>&1 & )
  rm -f "$R/mon.stop"
  ( setsid nohup taskset -c $CCPUS java -Xmx256m -cp "$CP" C4Client mon $JP "$R/mon.csv" "$R/mon.stop" atk t < /dev/null > "$R/mon.err" 2>&1 & )
  log "node pid $PID cg $CG memory.max $(cat $CG/memory.max 2>/dev/null) swap.max $(cat $CG/memory.swap.max 2>/dev/null)"
  for i in $(seq 360); do
    grep -q 'Starting listening for CQL clients' "$R/logs/system.log" 2>/dev/null && { log "UP (CQL) after $(( ($(ms)-T0)/1000 )) s"; break; }
    kill -0 "$PID" 2>/dev/null || { log "DIED before CQL after $(( ($(ms)-T0)/1000 )) s"; echo DIED > "$R/start.state"; return 1; }
    sleep 0.5
  done
  grep -q 'Starting listening for CQL clients' "$R/logs/system.log" || { log "not up in 180 s"; echo SLOW > "$R/start.state"; return 1; }
  echo UP > "$R/start.state"
  tr '\0' '\n' < /proc/$PID/cmdline > "$R/jvm-args.txt"
  log "readback: $(grep -E '^-Xm[xs]|MaxDirectMemorySize|GCThreads|AlwaysPreTouch|jmx.local.port' $R/jvm-args.txt | tr '\n' ' ')"
  log "readback log: $(grep -hoE 'memory pool size of [0-9]+ MB and a resize interval of [0-9]+ minutes|authenticator=[^;,]*|authorizer=[^;,]*|index_summary_capacity=[^;,]*|index_summary_resize_interval=[^;,]*|disk_access_mode=[^;,]*|memtable_allocation_type=[^;,]*|table_properties_disallowed=[^;,]*|table_properties_warned=[^;,]*|table_properties_ignored=[^;,]*' $R/logs/system.log | sort -u | tr '\n' '|')"
  log "affinity: $(taskset -pc $PID | sed 's/.*: //')"
  return 0
}

snap(){ # <R> <tag>
  local R=$1 t=$2 PID; PID=$(cat "$R/node.pid"); local CG; CG=$(cat "$R/cg.txt")
  if kill -0 "$PID" 2>/dev/null; then
    log "rss $t: $(grep -E '^(RssAnon|VmRSS|RssFile|VmHWM)' /proc/$PID/status | tr -s '\t ' ' ' | tr '\n' ' ') cg: cur=$(cat $CG/memory.current) $(grep -E '^(anon|file|file_mapped) ' $CG/memory.stat | tr '\n' ' ') ev: $(grep -E '^(max|oom|oom_kill) ' $CG/memory.events | tr '\n' ' ')"
    timeout 60 $T/bin/nodetool -p $JP tablestats atk > "$R/tablestats-$t.txt" 2>&1
    log "tablestats $t: $(grep -E 'Table:|SSTable count|Off heap memory used|Bloom filter off heap|Index summary off heap|Compression metadata off heap|Number of partitions' $R/tablestats-$t.txt | tr -s ' \t' ' ' | tr '\n' '|')"
    timeout 30 jcmd $PID VM.native_memory summary scale=MB > "$R/nmt-$t.txt" 2>&1
    log "nmt $t: $(grep -E '^Total:|^-  *(Java Heap|Internal|Other|Arena Chunk) ' $R/nmt-$t.txt | sed -E 's/\(reserved=[0-9]+MB, //; s/^- +//; s/ +/ /g' | tr '\n' '|')"
  else log "$t: node gone"; fi
}

stopnode(){ # <R>
  local R=$1 PID; PID=$(cat "$R/node.pid" 2>/dev/null)
  if [ -n "$PID" ] && kill -0 "$PID" 2>/dev/null; then
    timeout 60 $T/bin/nodetool -p $JP stopdaemon > /dev/null 2>&1
    for i in $(seq 60); do kill -0 "$PID" 2>/dev/null || break; sleep 1; done
    kill -0 "$PID" 2>/dev/null && { log "kill -9 $PID"; kill -9 "$PID"; }
  fi
  touch "$R/mon.stop"; sleep 2
  pkill -f "sampler.sh $PID " 2>/dev/null; pkill -f "C4Client mon $JP $R/" 2>/dev/null
  local UNIT; UNIT=$(cat "$R/unit.txt" 2>/dev/null)
  [ -n "$UNIT" ] && { CG=$(cat "$R/cg.txt"); cat "$CG/memory.events" > "$R/memory.events.last" 2>/dev/null; systemctl --user stop "$UNIT.scope" 2>/dev/null; }
  log "scope $UNIT: $(systemctl --user is-active $UNIT.scope 2>&1); memory.events.last: $(tr '\n' ' ' < $R/memory.events.last 2>/dev/null)"
  sudo -n dmesg | awk -v u="$UNIT" '/invoked oom-killer/{buf=""; on=1} on{buf=buf $0 "\n"} /Killed process/ && on{ if (index(buf,u)) printf "%s", buf; on=0 }' > "$R/dmesg-block.txt"
  log "dmesg: $(grep -E 'oom-kill:|Killed process' $R/dmesg-block.txt | tr '\n' ' ' | cut -c1-700)"
  grep -hE 'Initializing index summary manager|Redistributing index summaries|Completed resizing|Enqueuing flush of .*\b(t|tmax|t1)\b|Writing Memtable|Completed flushing .*atk|Compacting .*atk|Compacted .*atk|ERROR|WARN .*min_index_interval|OutOfMemory|Replaying|Log replay complete|Opening .*atk|Starting listening for CQL' "$R/logs/system.log" "$R/logs/debug.log" 2>/dev/null | cut -c1-320 > "$R/log-excerpt.txt"
}

victim_start(){ # <R>
  local R=$1; rm -f "$R/victim.stop"
  ( cd "$R" && setsid nohup taskset -c $CCPUS systemd-run --user --scope --quiet --unit="3bc4-victim-$(date +%s)" -p MemoryMax=8G -p MemorySwapMax=0 \
      java -Xmx1g -Dc4.port=$NP -Dc4.user=victim -Dc4.pass=vic-pw -Dlogback.configurationFile=$H/logback.xml -cp "$CP" C4Client victim 40 3600 "$R/victim.stop" \
      > victim.csv 2> victim.err < /dev/null & )
  sleep 2; VP=$(pgrep -f "C4Client victim 40 3600 $R/victim.stop" | head -1); echo "$VP" > "$R/victim.pid"; log "victim pid $VP"
}
victim_stop(){ local R=$1 VP; VP=$(cat "$R/victim.pid"); touch "$R/victim.stop"
  for i in $(seq 20); do kill -0 "$VP" 2>/dev/null || break; sleep 1; done; kill "$VP" 2>/dev/null; sleep 1; kill -9 "$VP" 2>/dev/null
  grep SUMMARY "$R/victim.csv" | tee -a "$R/run.log"; }

MODE=$1; shift
case $MODE in
tpl)
  R=$ROOT/runs/TPL; rm -rf "$R"; mkdir -p "$R"; N=$ROOT/templates/TPL; rm -rf "$N"
  start "$R" "$N" || exit 1
  for i in $(seq 30); do cli adm cassandra cassandra cql $H/ping.cql > "$R/ping.txt" 2>&1; grep -q '^OK' "$R/ping.txt" && break; sleep 2; done
  log "superuser ready after $i tries"
  cli adm cassandra cassandra cql $H/admin.cql > "$R/admin.txt" 2>&1; log "admin: $(grep -c '^OK' $R/admin.txt) OK, $(grep -c '^ERR' $R/admin.txt) ERR"
  cli vic victim vic-pw vpreload 10000 > "$R/vpreload.txt" 2>&1; log "$(tail -1 $R/vpreload.txt)"
  cli ng nogrant ng-pw cql $H/probe-nogrant.cql > "$R/probe-nogrant.txt" 2>&1
  cli vic victim vic-pw cql $H/probe-victim.cql > "$R/probe-victim.txt" 2>&1
  cli no "" "" cql $H/ping.cql > "$R/probe-nocreds.txt" 2>&1
  python3 $H/preauth.py 127.0.0.1 $NP > "$R/probe-preauth.txt" 2>&1
  log "probes done"
  timeout 120 $T/bin/nodetool -p $JP drain; stopnode "$R"
  log "template: $(du -sh $N | cut -f1)"
  ;;
attack)
  LB=$1 MINI=$2 MAXR=$3 MAXI=${4:-2048}
  R=$ROOT/runs/$LB; [ -e "$R" ] && { echo "exists: $R"; exit 2; }; mkdir -p "$R"; N=$R/node
  cp -a $ROOT/templates/TPL "$N"
  log "ATTACK lifetime $LB min_index_interval=$MINI max_index_interval=$MAXI maxRows=$MAXR"
  start "$R" "$N" || { stopnode "$R"; exit 1; }
  sleep 30; snap "$R" idle
  victim_start "$R"; sleep 60
  sed -e "s/@MINI@/$MINI/g" -e "s/@MAXI@/$MAXI/g" $H/attacker.cql.tmpl > "$R/attacker.cql"
  log "ATTACK START (attacker schema)"; date +%s%3N > "$R/attack.start"
  cli atk attacker att-pw cql "$R/attacker.cql" > "$R/attacker-schema.txt" 2>&1
  log "attacker schema: $(grep -c '^OK' $R/attacker-schema.txt) OK, $(grep -c '^ERR' $R/attacker-schema.txt) ERR"
  ( cd "$R" && setsid nohup taskset -c $CCPUS systemd-run --user --scope --quiet --unit="3bc4-load-$(date +%s)" -p MemoryMax=8G -p MemorySwapMax=0 \
      java -Xmx2g -Dc4.port=$NP -Dc4.user=attacker -Dc4.pass=att-pw -Dlogback.configurationFile=$H/logback.xml -cp "$CP" C4Client load atk.t 0 $MAXR 64 \
      > load.csv 2> load.err < /dev/null & )
  sleep 2; LP=$(pgrep -f "C4Client load atk.t 0 $MAXR 64" | head -1); echo "$LP" > "$R/load.pid"; log "load pid $LP"
  PID=$(cat "$R/node.pid"); t0=$(date +%s); dead=0; lastsnap=0
  while true; do
    sleep 2; el=$(( $(date +%s) - t0 ))
    if ! kill -0 "$PID" 2>/dev/null; then log "NODE DEAD at +${el}s (load: $(grep -E '^[0-9]{13},' $R/load.csv | tail -1))"; dead=1; date +%s%3N > "$R/node.end"; break; fi
    if [ $(( el - lastsnap )) -ge 20 ]; then log "t+$el load: $(grep -E '^[0-9]{13},' $R/load.csv | tail -1 | cut -c1-120) | sampler: $(tail -1 $R/sampler.csv) | mon: $(tail -1 $R/mon.csv)"; lastsnap=$el; fi
    kill -0 "$LP" 2>/dev/null || { log "load ended at +${el}s"; break; }
    [ $el -gt 2400 ] && { log "attack window cap 40 min"; break; }
  done
  for i in $(seq 40); do kill -0 "$LP" 2>/dev/null || break; sleep 1; done; kill "$LP" 2>/dev/null; sleep 1; kill -9 "$LP" 2>/dev/null
  grep SUMMARY "$R/load.csv" | tee -a "$R/run.log"; date +%s%3N > "$R/attack.end"
  if [ $dead = 0 ]; then
    for t in 10 60 120; do sleep $([ $t = 10 ] && echo 10 || echo $(( t == 60 ? 50 : 60 ))); kill -0 "$PID" 2>/dev/null || { log "NODE DEAD during observation"; dead=1; date +%s%3N > "$R/node.end"; break; }; snap "$R" "+$t"; done
  fi
  log "victim continues 60 s"; sleep 60; victim_stop "$R"
  [ $dead = 0 ] && snap "$R" end
  stopnode "$R"
  if [ $dead = 1 ]; then
    k=$(grep -c 'Killed process' "$R/dmesg-block.txt"); jo=$(grep -h -c 'OutOfMemoryError' "$R/logs/system.log" "$R/stdout.txt" 2>/dev/null | paste -sd+ | bc)
    echo "DEAD kernel_kill=$k java_oom_lines=$jo" > "$R/outcome"
  else echo "SURVIVED" > "$R/outcome"; fi
  log "OUTCOME $(cat $R/outcome)"
  ;;
restart)
  LB=$1 SRC=$2 W=${3:-300}
  R=$ROOT/runs/$LB; [ -e "$R" ] && { echo "exists: $R"; exit 2; }; mkdir -p "$R"; N=$ROOT/runs/$SRC/node
  log "RESTART lifetime $LB on $SRC's data in place ($(du -sh $N/data/atk 2>/dev/null | cut -f1) atk, commitlog $(du -sh $N/commitlog | cut -f1)); listing:"
  ls -l $N/data/atk/*/ > "$R/atk-listing-before.txt" 2>&1; ls -l $N/commitlog > "$R/commitlog-listing-before.txt"
  victim_start "$R"; date +%s%3N > "$R/attack.start"
  start "$R" "$N"; st=$?
  PID=$(cat "$R/node.pid"); t0=$(date +%s); dead=0
  if [ $st = 0 ]; then
    snap "$R" up
    while [ $(( $(date +%s) - t0 )) -lt $W ]; do sleep 2; kill -0 "$PID" 2>/dev/null || { dead=1; log "NODE DEAD at +$(( $(date +%s) - t0 ))s after CQL up"; break; }; done
    [ $dead = 0 ] && snap "$R" "+$W"
  else dead=1; fi
  [ $dead = 1 ] && date +%s%3N > "$R/node.end"
  log "victim continues 30 s"; sleep 30; victim_stop "$R"; date +%s%3N > "$R/attack.end"
  stopnode "$R"
  k=$(grep -c 'Killed process' "$R/dmesg-block.txt")
  [ $dead = 1 ] && echo "DEAD start_state=$(cat $R/start.state 2>/dev/null) kernel_kill=$k" > "$R/outcome" || echo "SURVIVED ${W}s after CQL up" > "$R/outcome"
  log "OUTCOME $(cat $R/outcome)"
  ;;
redist)
  LB=$1; R=$ROOT/runs/$LB; [ -e "$R" ] && { echo "exists: $R"; exit 2; }; mkdir -p "$R"; N=$R/node
  cp -a $ROOT/templates/TPL "$N"; log "REDIST diagnostic lifetime $LB"
  start "$R" "$N" || { stopnode "$R"; exit 1; }
  cli atk attacker att-pw cql $H/attacker-redist.cql > "$R/attacker-schema.txt" 2>&1; log "schema: $(grep -c '^OK' $R/attacker-schema.txt) OK $(grep -c '^ERR' $R/attacker-schema.txt) ERR"
  cli atk attacker att-pw load atk.t1 0 100000 64 > "$R/load-t1.csv" 2> "$R/load-t1.err"; grep SUMMARY "$R/load-t1.csv" | tee -a "$R/run.log"
  cli atk attacker att-pw load atk.tmax 0 100000 64 > "$R/load-tmax.csv" 2> "$R/load-tmax.err"; grep SUMMARY "$R/load-tmax.csv" | tee -a "$R/run.log"
  timeout 120 $T/bin/nodetool -p $JP flush atk; sleep 5
  timeout 300 $T/bin/nodetool -p $JP compactionstats > /dev/null; sleep 20; snap "$R" before
  timeout 120 java -cp "$CP" ISRedist $JP > "$R/redistribute.txt" 2>&1; log "redistribute: $(tr '\n' ' ' < $R/redistribute.txt | cut -c1-900)"
  sleep 5; snap "$R" after
  stopnode "$R"; echo "DIAG done" > "$R/outcome"
  ;;
stop) R=$ROOT/runs/$1; stopnode "$R" ;;
esac
