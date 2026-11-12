#!/usr/bin/env bash
# Cluster tier (B3, amended S4-A5..A9) of streaming_state_size-streammanager-states--autonomous.
# usage: bash cluster-run.sh <run> <label> <size> <stats_enabled true|false> <rebuilds> <sample-every>
#   e.g.  bash cluster-run.sh run1 s16k 16KiB true 150 25 ;  shakedown: bash cluster-run.sh shakedown shake 40MiB true 3 1
# Node trees /mydata/jingsong-cass-s4/o53/n1, n2 (cp -a of the built src; prepared by prepare-nodes.sh).
# Node 1 = 127.0.0.21 (seed, JMX 7499), node 2 = 127.0.0.22 (JMX 7498); storage 7300, ssl 7301, native 9342.
# Data and logs per label under /mydata/jingsong-cass-s4/o53/<run>/cluster/<label>/; both nodes stopped on any exit.
set -uo pipefail
H=$(cd "$(dirname "$0")" && pwd); B=/mydata/jingsong-cass-s4/o53
RUN=$1; LBL=$2; SIZE=$3; STATS=$4; NREB=$5; EVERY=$6
L=$B/$RUN/cluster/$LBL; mkdir -p "$L"; S=$L/summary.txt; : > "$S"; CSV=$L/samples.csv
say() { echo "$(date -u +%FT%TZ) $*" | tee -a "$S"; }
IP=(x 127.0.0.21 127.0.0.22); JMX=(x 7499 7498)
nt() { local k=$1; shift; "$B/n$k/bin/nodetool" -h 127.0.0.1 -p ${JMX[$k]} "$@"; }
# Cassandra deletes its -p pid file at shutdown, so the pid is saved once the node is up (n<k>.pidsave).
pidof_node() { cat "$L/n$1.pidsave" 2>/dev/null || cat "$L/n$1.pid" 2>/dev/null; }
stop_nodes() {
  for k in 2 1; do p=$(pidof_node $k); [ -n "$p" ] && kill "$p" 2>/dev/null && say "kill node $k pid $p"; done
  for k in 2 1; do p=$(pidof_node $k); [ -z "$p" ] && continue
    for t in $(seq 90); do kill -0 "$p" 2>/dev/null || break; sleep 1; done
    kill -0 "$p" 2>/dev/null && { kill -9 "$p"; say "kill -9 node $k pid $p"; }
  done
  say "after stop: java procs in $B: $(ps -eo pid,args | grep '[C]assandraDaemon' | grep -c "$B/")"
}
trap stop_nodes EXIT
fail() { say "STOP: $*"; exit 1; }
say "cluster-run $RUN $LBL size=$SIZE stats=$STATS rebuilds=$NREB every=$EVERY host $(hostname -s)"
say "harness md5 $(cd "$H" && md5sum cluster-run.sh set-yaml.py cluster-analyze.py 2>/dev/null | awk '{printf "%s=%s ", $2, substr($1,1,12)}')"
for p in 7300 7301 9342 7499 7498; do ss -ltn | awk '{print $4}' | grep -Eq "^(127\.0\.0\.2[12]|127\.0\.0\.1|0\.0\.0\.0|\*|\[::\]):$p$" && fail "port $p busy"; done
for k in 1 2; do
  D=$L/n$k; mkdir -p $D/{data,commitlog,hints,saved_caches,cdc_raw,logs}
  extra=""; [ $k = 2 ] && extra="auto_bootstrap=false"
  python3 "$H/set-yaml.py" "$B/n$k/conf/cassandra.yaml.orig" "$B/n$k/conf/cassandra.yaml" \
    "cluster_name='o53'" num_tokens=16 "seeds=\"127.0.0.21:7300\"" listen_address=${IP[$k]} rpc_address=${IP[$k]} \
    storage_port=7300 ssl_storage_port=7301 native_transport_port=9342 endpoint_snitch=SimpleSnitch \
    "data_file_directories=[$D/data]" commitlog_directory=$D/commitlog hints_directory=$D/hints \
    saved_caches_directory=$D/saved_caches cdc_raw_directory=$D/cdc_raw skip_paxos_repair_on_topology_change=true \
    streaming_state_size=$SIZE streaming_stats_enabled=$STATS $extra || fail "yaml n$k"
  sed "s/^JMX_PORT=\"7199\"/JMX_PORT=\"${JMX[$k]}\"/" "$B/n$k/conf/cassandra-env.sh.orig" > "$B/n$k/conf/cassandra-env.sh"
  cp "$B/n$k/conf/cassandra.yaml" "$L/n$k-cassandra.yaml"
done
start_node() {
  local k=$1 x="-Dcassandra.consistent.rangemovement=false"
  [ $k = 2 ] && x="$x -Dcassandra.reset_bootstrap_progress=true"
  ( cd "$B/n$k" && CASSANDRA_LOG_DIR=$L/n$k/logs MAX_HEAP_SIZE=1G HEAP_NEWSIZE=256M JVM_EXTRA_OPTS="$x" \
      setsid nohup bin/cassandra -p "$L/n$k.pid" < /dev/null > "$L/n$k/logs/stdout.txt" 2>&1 )
  for t in $(seq 180); do
    sleep 1; p=$(pidof_node $k)
    [ -n "$p" ] && ! kill -0 "$p" 2>/dev/null && fail "node $k died during start"
    [ -n "$p" ] && nt $k statusbinary 2>/dev/null | grep -qx running && \
      nt $k status 2>/dev/null | grep -q "^UN  ${IP[$k]} " && { echo "$p" > "$L/n$k.pidsave"; say "node $k up pid $p after ${t}s"; return 0; }
  done
  fail "node $k not up in 180 s"
}
start_node 1; start_node 2
for t in $(seq 60); do [ "$(nt 1 status | grep -c '^UN ')" = 2 ] && break; sleep 1; done
say "ring: $(nt 1 status | grep -E '^(UN|DN|UJ)' | awk '{print $1, $2}' | tr '\n' ' ')"
[ "$(nt 1 status | grep -c '^UN ')" = 2 ] || fail "ring not 2 x UN"
want=$(python3 -c "import re;s='$SIZE';m=re.match(r'(\d+)(KiB|MiB)',s);print(int(m[1])*(1024 if m[2]=='KiB' else 1048576))")
for k in 1 2; do
  line=$(grep -m1 'Storing streaming state for' "$L/n$k/logs/system.log"); say "n$k: ${line##*StreamManager.java:*- }"
  echo "$line" | grep -q "for size $want\$" || fail "n$k size line is not $want"
done
CQ() { "$B/n1/bin/cqlsh" "$1" 9342 -e "$2" 2>&1; }
CQ 127.0.0.21 "CREATE KEYSPACE o53 WITH replication = {'class':'SimpleStrategy','replication_factor':2}; CREATE TABLE o53.t (k int PRIMARY KEY, v text);" >> "$L/cqlsh.txt"
python3 -c "print('CONSISTENCY ALL;'); [print(f\"INSERT INTO o53.t (k, v) VALUES ({i}, 'v{i}');\") for i in range(100)]" > "$L/insert.cql"
"$B/n1/bin/cqlsh" 127.0.0.21 9342 -f "$L/insert.cql" >> "$L/cqlsh.txt" 2>&1 || fail "insert"
for k in 1 2; do nt $k flush o53; done
for k in 1 2; do say "n$k rows: $(CQ ${IP[$k]} "CONSISTENCY ONE; SELECT count(*) FROM o53.t;" | grep -E '^ +[0-9]+$' | tr -d ' ')"; done
echo "i,node,vtable,live,live_bytes,heap_used_mb" > "$CSV"
sample() {
  local i=$1
  for k in 1 2; do
    c=$(CQ ${IP[$k]} "SELECT count(*) FROM system_views.streaming;" | grep -E '^ +[0-9]+$' | tr -d ' ')
    h=$(jcmd "$(pidof_node $k)" GC.class_histogram 2>/dev/null | awk '$4=="org.apache.cassandra.streaming.StreamingState"{print $2, $3; f=1} END{if(!f) print 0, 0}')
    u=$(nt $k info 2>/dev/null | awk -F: '/^Heap Memory/{split($2,a,"/"); gsub(/ /,"",a[1]); print a[1]}')
    echo "$i,$k,${c:-NA},${h% *},${h#* },${u:-NA}" >> "$CSV"
  done
  say "sample i=$i $(grep "^$i," "$CSV" | tr '\n' ' ')"
}
fails=0; t0=$(date +%s)
for i in $(seq "$NREB"); do
  nt 2 rebuild -ks o53 -- datacenter1 > "$L/rebuild-$i.txt" 2>&1; rc=$?
  echo "$i,$rc,$(date +%s%3N)" >> "$L/rebuilds.csv"
  [ $rc != 0 ] && { fails=$((fails+1)); say "rebuild $i rc=$rc: $(head -c 300 "$L/rebuild-$i.txt")"; }
  [ $((i % EVERY)) = 0 ] && sample $i
done
say "rebuilds: $NREB, failed: $fails, $(( $(date +%s) - t0 )) s"
for k in 1 2; do
  CQ ${IP[$k]} "SELECT operation, status, follower, peers FROM system_views.streaming;" > "$L/n$k-vtable-final.txt"
  say "n$k vtable by operation/status: $(grep -E '^ +[A-Za-z]' "$L/n$k-vtable-final.txt" | grep -v operation | awk -F'|' '{gsub(/ /,"",$1);gsub(/ /,"",$2);print $1"/"$2}' | sort | uniq -c | tr '\n' ' ')"
  jcmd "$(pidof_node $k)" GC.class_histogram > "$L/n$k-histo-final.txt" 2>&1
  say "n$k histogram: $(grep -E 'streaming\.StreamingState|StreamResultFuture|StreamSession ' "$L/n$k-histo-final.txt" | awk '{print $4"="$2}' | tr '\n' ' ')"
  say "n$k ERROR lines: $(grep -c '^ERROR' "$L/n$k/logs/system.log")"
done
say "done"
