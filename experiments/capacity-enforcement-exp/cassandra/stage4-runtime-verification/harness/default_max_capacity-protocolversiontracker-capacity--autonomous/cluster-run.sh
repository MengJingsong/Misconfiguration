#!/usr/bin/env bash
# o134 cluster tier (B3e as amended S4-A1/S4-A3), one build per invocation: bash cluster-run.sh stock|uncapped
# Only the node whose PID this script recorded is signalled. All paths are literal under /mydata/jingsong-cass-s4/o134.
set -uo pipefail
B=$1; R=/mydata/jingsong-cass-s4/o134; C=$R/c509-$B; D=$R/s3data; OUT=$R/cluster/$B; CL=$R/s3client
mkdir -p $OUT; exec > >(tee -a $OUT/session.log) 2>&1
log() { echo "+ $(date -u +%FT%TZ) [$(date +%s%3N)] $*"; }
NT="$C/bin/nodetool -h 127.0.0.1 -p 7199"
export MAX_HEAP_SIZE=1G HEAP_NEWSIZE=200M CASSANDRA_LOG_DIR=$D/logs
stopnode() {
  [ -s $D/pid ] || return 0; local p; p=$(cat $D/pid)
  if [ -d /proc/$p ] && grep -q CassandraDaemon /proc/$p/cmdline 2>/dev/null; then
    log "kill $p"; kill $p; for i in $(seq 1 30); do [ -d /proc/$p ] || break; sleep 1; done
    [ -d /proc/$p ] && { log "kill -9 $p"; kill -9 $p; sleep 2; }
  fi
  [ -d /proc/$p ] && log "WARNING $p alive" || log "node $p gone"
}
die() { log "FAIL: $*"; stopnode; exit 1; }
rows() {  # $1 label: by-protocol rows per version
  $NT clientstats --by-protocol > $OUT/r-$1.txt 2>&1
  local s; s=$(grep -E '^[0-9]+/v' $OUT/r-$1.txt | awk '{print $1}' | sort | uniq -c | awk '{printf "%s=%s ", $2, $1}')
  log "ROWS $1: ${s:-none} total=$(grep -cE '^[0-9]+/v' $OUT/r-$1.txt)"
}
hist() { jcmd $P GC.class_histogram > $OUT/h-$1.txt 2>&1; log "histogram $1: $(wc -l < $OUT/h-$1.txt) lines"; }
flood() {  # version first count label
  local t0=$(date +%s%3N)
  java -cp $CL StartupFlood $1 $2 $3 > $OUT/flood-$4.out 2> $OUT/flood-$4.err; local rc=$?
  log "FLOOD $4: v$1 first=$2 count=$3 exit=$rc in $(( $(date +%s%3N) - t0 )) ms; non-READY lines: $(wc -l < $OUT/flood-$4.err)"
  head -3 $OUT/flood-$4.err
}
log "build $B: $C"
ulimit -n 100000; log "ulimit -n $(ulimit -n)"
if ss -ltn | grep -E ':(7000|7199|9042|9091)\b'; then die "ports busy"; fi; log "ports 7000/7199/9042/9091 free"
ps -eo cmd | grep -q '[C]assandraDaemon' && die "a CassandraDaemon is already running"
# B3a configuration
Y=$C/conf/cassandra.yaml
grep -q 'o134 stage-4 settings' $Y || {
  sed -i -e "s/^cluster_name: .*/cluster_name: 's3probe'/" -e 's/^listen_address: .*/listen_address: 127.0.0.1/' \
         -e 's/^rpc_address: .*/rpc_address: 127.0.0.1/' $Y
  cat >> $Y <<EOF
# o134 stage-4 settings
data_file_directories: [$D/data]
commitlog_directory: $D/commitlog
hints_directory: $D/hints
saved_caches_directory: $D/saved_caches
cdc_raw_directory: $D/cdc_raw
EOF
}
grep -nE '^(cluster_name|listen_address|rpc_address|native_transport_port|native_transport_allow_older_protocols|authenticator|data_file_directories|commitlog_directory|hints_directory|saved_caches_directory|cdc_raw_directory):|seeds:' $Y
# B3e step 1
rm -rf /mydata/jingsong-cass-s4/o134/s3data && mkdir -p $D/logs
log "start: MAX_HEAP_SIZE=$MAX_HEAP_SIZE HEAP_NEWSIZE=$HEAP_NEWSIZE bin/cassandra -R -p $D/pid"
( cd $C && setsid nohup bin/cassandra -R -p $D/pid </dev/null > $OUT/cassandra.out 2>&1 & )
for i in $(seq 1 30); do [ -s $D/pid ] && break; sleep 1; done; [ -s $D/pid ] || die "no pid"; P=$(cat $D/pid); log "pid $P"
for i in $(seq 1 150); do
  [ -d /proc/$P ] || die "daemon died during start"
  [ "$($NT statusbinary 2>/dev/null | tr -d '[:space:]')" = running ] && $NT status 2>/dev/null | grep -q '^UN' && break; sleep 2
done
$NT status | grep '^UN' || die "node not UN"; log "statusbinary: $($NT statusbinary)"
ps -o args= -p $P | tr ' ' '\n' | grep -E '^-Xm|^-Xmn|cassandra.*jar$' > $OUT/jvm-args.txt; cat $OUT/jvm-args.txt
# B3e step 2
log "clear-history"; $NT clientstats --clear-history; log "wait 30 s"; sleep 30
hist 0; rows 0
# B3e step 3: cumulative V4 targets, fresh addresses each step
prev=0
for N in 50 100 150 1000 20000; do flood 4 $prev $((N - prev)) v4-$N; sleep 10; rows v4-$N; hist v4-$N; prev=$N; done
# B3e step 4
flood 3 100000 1000 v3; flood 5 200000 1000 v5; flood 6 300000 1000 v6; sleep 10; rows all; hist all
# B3e step 5: same first 20 000 addresses on V4 again
flood 4 0 20000 v4-repeat; sleep 10; rows repeat; hist repeat
# B3e step 6
log "clear-history"; $NT clientstats --clear-history; sleep 10; rows clear; hist clear
# B3e step 7
grep -c '^ERROR' $D/logs/system.log | sed 's/^/system.log ERROR lines: /'; grep -c '^WARN' $D/logs/system.log | sed 's/^/system.log WARN lines: /'
cp $D/logs/system.log $OUT/system.log
stopnode
ps -eo cmd | grep -q '[C]assandraDaemon' && log "LEFTOVER CassandraDaemon" || log "no CassandraDaemon"
ps -eo cmd | grep -q '[S]tartupFlood' && log "LEFTOVER StartupFlood" || log "no StartupFlood"
log "CLUSTER $B done"
