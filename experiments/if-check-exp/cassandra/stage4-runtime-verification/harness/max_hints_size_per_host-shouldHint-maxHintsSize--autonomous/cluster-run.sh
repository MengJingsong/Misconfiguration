#!/usr/bin/env bash
# Cluster tier (B3, amended 2026-10-27) of max_hints_size_per_host-shouldHint-maxHintsSize--autonomous.
# usage: source ~/Library/Caches/stage4/env.sh; cluster-run.sh <label> <n_writes> "<C values in MiB>"
#   r1:    cluster-run.sh r1 1000000 "0 32 128 512"   (as frozen)
#   shake: e.g. cluster-run.sh shake 60000 "0 16"
# Two nodes from one clone C (default $W/cassandra-run48): n1 127.0.0.1 (JMX 7199), n2 127.0.0.2 (JMX 7299),
# node files under $W/node-mhs48/{n1,n2}, fresh for every round. Logs: $W/logs/max_hints_size_per_host-shouldHint/cluster-<label>/
# (node start/stop functions adapted from harness/maxHintsInProgress-checkHintOverload-totalHintsInProgress--autonomous/cluster-run.sh)
set -uo pipefail
LABEL=$1; NW=$2; CLIST=$3
H=$(cd "$(dirname "$0")" && pwd); C=${C:-$W/cassandra-run48}
N=$W/node-mhs48; BIN=$W/harness-bin-mhs
L=$W/logs/max_hints_size_per_host-shouldHint/cluster-$LABEL; mkdir -p "$L"; rm -rf "$L"/*
log() { echo "[$(date '+%F %T')] $*" | tee -a "$L/commands.log"; }
run() { log "+ $*"; "$@" >> "$L/commands.log" 2>&1; local rc=$?; log "  rc=$rc"; return $rc; }
die() { log "ABORT: $*"; stop_all; exit 1; }
NT() { "$C/bin/nodetool" -h 127.0.0.1 -p "$1" "${@:2}"; }
P1=""; P2=""

stop_node() { # $1 = jmx port, $2 = pid
  [ -z "$2" ] && return 0
  kill -0 "$2" 2>/dev/null || return 0
  NT "$1" stopdaemon >> "$L/commands.log" 2>&1
  for i in $(seq 1 60); do kill -0 "$2" 2>/dev/null || return 0; sleep 1; done
  kill "$2" 2>/dev/null; sleep 5; kill -9 "$2" 2>/dev/null; log "node pid $2 killed"
}
stop_all() { pkill -f 'org.apache.cassandra.stress.Stress' 2>/dev/null; stop_node 7299 "$P2"; P2=""; stop_node 7199 "$P1"; P1=""; }

log "cluster-run $LABEL n=$NW C=[$CLIST] clone=$C $(git -C "$C" rev-parse HEAD) sampler_sha=$(shasum -a 256 "$H/HintsSizeSampler.java" | cut -c1-16) script_sha=$(shasum -a 256 "$0" | cut -c1-16)"
pgrep -f 'org.apache.cassandra.service.Cassandra[D]aemon' >/dev/null && { log "ABORT: a node is already running"; exit 1; }
ifconfig lo0 | grep -q "inet 127.0.0.2 " || { log "ABORT: loopback 127.0.0.2 missing"; exit 1; }
for p in 7000 7199 7299 9042; do lsof -nP -iTCP:$p -sTCP:LISTEN >/dev/null 2>&1 && { log "ABORT: port $p busy"; exit 1; }; done
mkdir -p "$BIN"; javac -d "$BIN" "$H/HintsSizeSampler.java" >> "$L/commands.log" 2>&1 || { log "ABORT: sampler compile"; exit 1; }
SAMP() { java -cp "$BIN" HintsSizeSampler "$@"; }

make_nodes() { # $1 = C MiB
  rm -rf "$N"; mkdir -p "$N"
  for n in 1 2; do
    D=$N/n$n; mkdir -p $D/data $D/commitlog $D/hints $D/saved_caches $D/cdc_raw $D/logs
    cp -R "$C/conf" $D/conf
    Y=$D/conf/cassandra.yaml
    grep -v -E '^(cluster_name|listen_address|rpc_address|hinted_handoff_enabled|max_hint_window|hints_flush_period|max_hints_file_size|auto_hints_cleanup_enabled|hints_directory|commitlog_directory|saved_caches_directory|cdc_raw_directory|auto_bootstrap|max_hints_size_per_host):' "$C/conf/cassandra.yaml" > $Y
    cat >> $Y <<YAML
# --- stage-4 overrides (B3a/B3b amended 2026-10-27) ---
cluster_name: 'mhs48'
listen_address: 127.0.0.$n
rpc_address: 127.0.0.$n
auto_bootstrap: false
data_file_directories:
    - $D/data
commitlog_directory: $D/commitlog
hints_directory: $D/hints
saved_caches_directory: $D/saved_caches
cdc_raw_directory: $D/cdc_raw
hinted_handoff_enabled: true
hints_flush_period: 1000ms
max_hints_file_size: 8MiB
max_hint_window: 3h
auto_hints_cleanup_enabled: false
YAML
    [ $n = 1 ] && echo "max_hints_size_per_host: ${1}MiB" >> $Y
    [ $n = 2 ] && sed -i '' 's/^JMX_PORT="7199"/JMX_PORT="7299"/' $D/conf/cassandra-env.sh
  done
}
start_node() { # $1 = n
  local n=$1 D=$N/n$1
  ( cd "$C" && CASSANDRA_CONF=$D/conf CASSANDRA_LOG_DIR=$D/logs MAX_HEAP_SIZE=2G HEAP_NEWSIZE=400M \
    exec bin/cassandra -f > $D/logs/stdout.log 2>&1 < /dev/null ) &
  if [ $n = 1 ]; then P1=$!; else P2=$!; fi
  log "started n$n pid=$!"
}
wait_up() { # $1 = n, $2 = jmx port, $3 = pid
  for i in $(seq 1 120); do
    kill -0 "$3" 2>/dev/null || { log "n$1 died during start"; return 1; }
    if [ "$(NT "$2" statusbinary 2>/dev/null)" = "running" ]; then log "n$1 up (binary running) after ~$((i*2)) s"; return 0; fi
    sleep 2
  done
  return 1
}

for CV in $CLIST; do
  T=$L/C$CV; mkdir -p $T
  log "===== C=$CV MiB ====="
  make_nodes $CV
  diff "$C/conf/cassandra.yaml" $N/n1/conf/cassandra.yaml > $T/n1-yaml.diff; diff "$C/conf/cassandra.yaml" $N/n2/conf/cassandra.yaml > $T/n2-yaml.diff
  grep -n 'JMX_PORT=' $N/n2/conf/cassandra-env.sh >> $T/n2-yaml.diff
  start_node 1; wait_up 1 7199 $P1 || die "n1 did not start"
  start_node 2; wait_up 2 7299 $P2 || die "n2 did not start"
  for i in $(seq 1 30); do [ "$(NT 7199 status 2>/dev/null | grep -c '^UN')" = 2 ] && break; sleep 2; done
  NT 7199 status > $T/status-both.txt 2>&1
  [ "$(grep -c '^UN' $T/status-both.txt)" = 2 ] || die "ring not UN UN"
  HID=$(grep '127.0.0.2' $T/status-both.txt | grep -oE '[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}')
  log "UN UN; n2 host id=$HID"
  run "$C/bin/cqlsh" 127.0.0.1 -e "CREATE KEYSPACE ks WITH replication={'class':'SimpleStrategy','replication_factor':2}" || die "create keyspace failed"
  "$C/bin/cqlsh" 127.0.0.1 -e "DESCRIBE KEYSPACE ks" > $T/ks.txt 2>&1
  log "stop n2 (stopdaemon)"; stop_node 7299 "$P2"; P2=""
  for i in $(seq 1 30); do NT 7199 status 2>/dev/null | grep -q '^DN *127.0.0.2' && break; sleep 2; done
  NT 7199 status > $T/status-pre.txt 2>&1
  grep -q '^DN *127.0.0.2' $T/status-pre.txt || die "n2 not DN"
  log "n2 DN: $(grep '127.0.0.2' $T/status-pre.txt | cut -c1-60)"
  run NT 7199 truncatehints
  SAMP get 127.0.0.1 7199 $N/n1/hints $HID > $T/pre.txt 2>&1; log "pre (epoch,dir_bytes,files,total_hints,created_n2,MiB): $(cat $T/pre.txt)"
  [ "$(cut -d, -f2 $T/pre.txt)" = 0 ] || die "hints dir not empty for n2"
  [ "$(cut -d, -f6 $T/pre.txt)" = "$CV" ] || die "MaxHintsSizePerHostInMiB readback != $CV"
  run NT 7199 settraceprobability 0.001
  NT 7199 gettraceprobability > $T/traceprob.txt 2>&1
  NT 7199 listpendinghints > $T/pending-pre.txt 2>&1; df -k $N > $T/df-pre.txt
  JP=$(pgrep -f "cassandra.logdir=$N/n1/logs" | head -1); log "n1 java pid=$JP"
  LOGOFF=$(stat -f %z $N/n1/logs/system.log)
  rm -f $T/stop
  SAMP loop 127.0.0.1 7199 $N/n1/hints $HID $T/sampler.csv $T/stop 5000 2> $T/sampler.err &
  SP=$!
  sleep 1
  log "+ cassandra-stress write n=$NW no-warmup cl=ONE -schema keyspace=ks -col size=FIXED(1024) n=FIXED(1) -rate threads=32 -node 127.0.0.1"
  echo "stress_start_ms=$(($(date +%s)*1000))" > $T/times.txt
  "$C/tools/bin/cassandra-stress" write n=$NW no-warmup cl=ONE -schema "keyspace=ks" -col "size=FIXED(1024)" "n=FIXED(1)" -rate threads=32 -node 127.0.0.1 > $T/stress.out 2> $T/stress.err
  src=$?; echo "stress_end_ms=$(($(date +%s)*1000))" >> $T/times.txt
  log "stress rc=$src; $(grep -E 'Total errors|Total partitions|Op rate' $T/stress.out | tr -s ' ' | tr '\n' ';')"
  sleep 5
  SAMP get 127.0.0.1 7199 $N/n1/hints $HID > $T/final.txt 2>&1; echo "final_ms=$(cut -d, -f1 $T/final.txt)" >> $T/times.txt
  log "final (epoch,dir_bytes,files,total_hints,created_n2,MiB): $(cat $T/final.txt)"
  touch $T/stop; wait $SP
  NT 7199 status > $T/status-post.txt 2>&1
  grep -q '^DN *127.0.0.2' $T/status-post.txt && log "n2 still DN" || log "WARNING: n2 not DN after the run"
  NT 7199 listpendinghints > $T/pending-post.txt 2>&1; df -k $N > $T/df-post.txt
  ls -l $N/n1/hints > $T/hints-ls.txt 2>&1
  run NT 7199 settraceprobability 0
  sleep 3
  run "$C/bin/cqlsh" 127.0.0.1 --request-timeout=120 -e "COPY system_traces.events (session_id, event_id, activity) TO '$T/trace-events.csv'"
  log "trace events: rows=$(wc -l < $T/trace-events.csv 2>/dev/null) size_msg=$(grep -c 'reached to the max hints size' $T/trace-events.csv 2>/dev/null)"
  tail -c +$((LOGOFF+1)) $N/n1/logs/system.log > $T/system-window.log
  log "system.log window: ERROR=$(grep -c '^ERROR' $T/system-window.log) WARN=$(grep -c '^WARN' $T/system-window.log)"
  run NT 7199 truncatehints
  log "stop n1"; stop_node 7199 "$P1"; P1=""
  cp $N/n1/logs/system.log $T/n1-system.log 2>/dev/null; cp $N/n2/logs/system.log $T/n2-system.log 2>/dev/null
  du -sk $N >> "$L/commands.log" 2>&1
  rm -rf "$N"; log "node directories removed"
done
stop_all
pgrep -f 'org.apache.cassandra.service.Cassandra[D]aemon' >/dev/null && log "WARNING: node still running" || log "no node running"
pgrep -f 'org.apache.cassandra.stress.Stress' >/dev/null && log "WARNING: stress still running" || log "no stress running"
log "cluster-run $LABEL done"
