#!/usr/bin/env bash
# Cluster tier (B3, as amended 2026-10-26) of hints_buffer_size-allocateBytes-prev--autonomous.
# usage: source ~/Library/Caches/stage4/env.sh; cluster-run.sh
#   run 1:     no variables (ARMS="i ii iii", NW=200000 writes per phase)
#   shakedown: ARMS=i NW=20000 OUT=$W/logs/<stem>/shakedown-cluster cluster-run.sh
# Two nodes from the one built clone (never built while a node runs), each with its own conf, data, logs:
#   node 1 = 127.0.0.1, JMX 7199, Byteman agent (hb.btm, observation only) — the hint writer, the knob is set here
#   node 2 = 127.0.0.2, JMX 7299, defaults
# Per arm: wipe, yaml, start node 1 then node 2 (UN/UN, statusbinary running), JMX sampler every 1 s on node 1,
#   phase U (stress write, node 2 up), wait 60 s, drain + kill node 2, wait for DN, 15 s quiet window (S0),
#   phase D (the same stress command), 30 s tail (S1 = its last 15 s), stop sampler, drain + stop node 1.
# Phase boundaries are recorded as epoch ms and as byte offsets of node 1's node.out (the Byteman lines).
# Env: C (clone, default $W/cassandra-run36), OUT (log dir), HB (compiled HbJmx dir), ARMS, NW.
set -uo pipefail
ARMS=${ARMS:-"i ii iii"}; NW=${NW:-200000}
H=$(cd "$(dirname "$0")" && pwd); C=${C:-$W/cassandra-run36}; HB=${HB:-$W/harness-bin-hb}
N1=$W/node-hb1; N2=$W/node-hb2
OUT=${OUT:-$W/logs/hints_buffer_size-allocateBytes-prev--autonomous/cluster}
mkdir -p "$OUT"; rm -rf "${OUT:?}"/*
export CASSANDRA_HOME=$C
DPAT='cassandra.service.Cassandra''Daemon'      # split so this script's own command line never matches
BMJAR=$C/build/lib/jars/byteman-4.0.20.jar
L=$OUT
log() { echo "[$(date '+%F %T')] $*" | tee -a "$OUT/commands.log"; }
note() { echo "$*" >> "$OUT/summary.txt"; log "$*"; }
nowms() { python3 -c 'import time; print(int(time.time()*1000))'; }
pgrep -f "$DPAT" >/dev/null && { log "ABORT: a Cassandra daemon is already running"; exit 1; }
for p in 7000 7199 7299 9042; do lsof -nP -iTCP:$p -sTCP:LISTEN >/dev/null 2>&1 && { log "ABORT: port $p busy"; exit 1; }; done
ifconfig lo0 | grep -q 'inet 127.0.0.2 ' || { log "ABORT: no loopback alias 127.0.0.2"; exit 1; }
[ -f "$BMJAR" ] || { log "ABORT: no $BMJAR"; exit 1; }
note "RUN ARMS=[$ARMS] NW=$NW clone=$(git -C "$C" rev-parse HEAD) status_entries=$(git -C "$C" status --short | wc -l | tr -d ' ') btm_sha256=$(shasum -a 256 "$H/hb.btm" | cut -c1-16) start_epoch=$(date +%s)"
mkdir -p "$HB"; javac -d "$HB" "$H/HbJmx.java" >> "$OUT/commands.log" 2>&1 || { log "ABORT: javac HbJmx"; exit 1; }
NT() { local port=$1; shift; (cd "$C" && bin/nodetool -p "$port" "$@"); }
NPID1=; NPID2=; SPID=
stop_sampler() { [ -n "$SPID" ] || return 0; touch "$L/sampler.stop"; sleep 2; kill "$SPID" 2>/dev/null; SPID=; log "sampler stopped"; }
stop_one() { # $1 pid var name, $2 jmx port, $3 label
  local pid=${!1}; [ -z "$pid" ] && return 0
  log "stopping $3 (pid $pid)"
  if kill -0 "$pid" 2>/dev/null; then
    NT "$2" drain >> "$OUT/commands.log" 2>&1 & local dp=$!
    for i in $(seq 1 60); do kill -0 "$dp" 2>/dev/null || break; sleep 1; done
    kill "$dp" 2>/dev/null
    kill "$pid" 2>/dev/null
    for i in $(seq 1 60); do kill -0 "$pid" 2>/dev/null || break; sleep 1; done
    kill -0 "$pid" 2>/dev/null && { log "$3 still alive after 60 s: kill -9"; kill -9 "$pid"; sleep 2; }
  fi
  eval "$1="; }
stop_all() {
  stop_sampler; stop_one NPID2 7299 node2; stop_one NPID1 7199 node1
  sleep 2; local left; left=$(pgrep -f "$DPAT")
  if [ -n "$left" ]; then log "WARNING: daemon still running ($left): kill -9"; kill -9 $left; sleep 2; fi
  pgrep -f "$DPAT" >/dev/null && log "WARNING: daemon still running" || log "no Cassandra daemon left"; }
trap 'stop_all; rm -rf "$N1" "$N2"; log "node dirs wiped (trap)"' EXIT

mknode() { # $1 dir, $2 address, $3 jmx port, $4 arm (node 1 only gets the knob)
  local N=$1 Y=$1/conf/cassandra.yaml
  rm -rf "$N"; mkdir -p "$N"/{data,commitlog,hints,saved_caches,cdc_raw,logs}; cp -R "$C/conf" "$N/conf"
  grep -v -E '^(cluster_name|auto_bootstrap|num_tokens|hinted_handoff_enabled|max_hint_window|hints_directory|data_file_directories|commitlog_directory|saved_caches_directory|cdc_raw_directory|listen_address|rpc_address|file_cache_size|commitlog_segment_size|max_mutation_size):' "$C/conf/cassandra.yaml" > "$Y"
  { echo; echo "# stage-4 overrides (hints_buffer_size)"
    echo "cluster_name: hbcap"; echo "auto_bootstrap: false"; echo "num_tokens: 16"; echo "hinted_handoff_enabled: true"; echo "max_hint_window: 3h"
    echo "data_file_directories:"; echo "    - $N/data"
    echo "commitlog_directory: $N/commitlog"; echo "hints_directory: $N/hints"
    echo "saved_caches_directory: $N/saved_caches"; echo "cdc_raw_directory: $N/cdc_raw"
    echo "listen_address: $2"; echo "rpc_address: $2"; echo "file_cache_size: 32MiB"
    case "$4" in
      ii)  echo "commitlog_segment_size: 64MiB";  echo "max_mutation_size: 32MiB" ;;
      iii) echo "commitlog_segment_size: 128MiB"; echo "max_mutation_size: 64MiB" ;;
      *)   echo "commitlog_segment_size: 32MiB" ;;
    esac; } >> "$Y"
  sed -i '' -e "s/^JMX_PORT=\"7199\"/JMX_PORT=\"$3\"/" "$N/conf/cassandra-env.sh"
  grep '^JMX_PORT=' "$N/conf/cassandra-env.sh" | head -1; }

start_node() { # $1 dir, $2 address, $3 jmx port, $4 extra opts, $5 out file, $6 pid var
  log "+ MAX_HEAP_SIZE=2G HEAP_NEWSIZE=400M CASSANDRA_CONF=$1/conf CASSANDRA_LOG_DIR=$1/logs JVM_EXTRA_OPTS=\"$4\" bin/cassandra -f  ($2)"
  ( cd "$C" && MAX_HEAP_SIZE=2G HEAP_NEWSIZE=400M CASSANDRA_CONF="$1/conf" CASSANDRA_LOG_DIR="$1/logs" JVM_EXTRA_OPTS="$4" exec bin/cassandra -f ) >> "$5" 2>&1 < /dev/null &
  local pid=$!; eval "$6=$pid"; log "$2 launcher pid $pid"
  local ok=0
  for i in $(seq 1 120); do
    kill -0 "$pid" 2>/dev/null || { log "ABORT: $2 died during start"; exit 1; }
    if NT 7199 status 2>/dev/null | grep -q "^UN  $2" && [ "$(NT "$3" statusbinary 2>/dev/null)" = running ]; then ok=1; break; fi
    sleep 3
  done
  [ $ok = 1 ] || { log "ABORT: $2 not UN/running within 360 s"; exit 1; }
  log "$2 UN, statusbinary running"; }

stress() { # $1 label, $2 out file
  log "+ tools/bin/cassandra-stress write n=$NW cl=ONE -col 'size=FIXED(1024)' 'n=FIXED(1)' -schema 'replication(factor=2)' keyspace=hb -rate threads=50 -node 127.0.0.1   ($1)" >&2
  ( cd "$C" && tools/bin/cassandra-stress write n="$NW" cl=ONE -col 'size=FIXED(1024)' 'n=FIXED(1)' -schema 'replication(factor=2)' keyspace=hb -rate threads=50 -node 127.0.0.1 ) > "$2" 2>&1 < /dev/null
  local rc=$?
  echo "rc=$rc | $(grep -E '^(Op rate|Partition rate|Total partitions|Total errors|Total operation time)' "$2" | sed 's/  */ /g' | tr '\n' ';')"; }

for A in $ARMS; do
  case "$A" in i) B=33554432;; ii) B=67108864;; iii) B=134217728;; *) log "ABORT: arm $A"; exit 1;; esac
  L=$OUT/arm-$A; mkdir -p "$L"; NO=$L/node1.out
  note "ARM $A B_arm=$B start_ms=$(nowms)"
  note "JMX $A node1 $(mknode "$N1" 127.0.0.1 7199 "$A") node2 $(mknode "$N2" 127.0.0.2 7299 x)"
  tail -17 "$N1/conf/cassandra.yaml" > "$L/yaml-overrides-node1.txt"; tail -17 "$N2/conf/cassandra.yaml" > "$L/yaml-overrides-node2.txt"
  : > "$NO"
  start_node "$N1" 127.0.0.1 7199 "-XX:MaxDirectMemorySize=2g -javaagent:$BMJAR=script:$H/hb.btm,boot:$BMJAR" "$NO" NPID1
  start_node "$N2" 127.0.0.2 7299 "-XX:MaxDirectMemorySize=2g" "$L/node2.out" NPID2
  NT 7199 status > "$L/status-start.txt" 2>&1
  note "STATUS $A start | $(grep -E '^(UN|DN|UJ)' "$L/status-start.txt" | awk '{print $1, $2}' | tr '\n' ' ')"
  note "READBACK $A node1 | $(grep -m1 'Node configuration' "$N1/logs/system.log" | grep -o -E '(commitlog_segment_size|max_mutation_size|hinted_handoff_enabled|max_hint_window|file_cache_size|cluster_name|hints_flush_period|max_hints_size_per_host)=[^;]*' | tr '\n' ' ')"
  note "JVMARGS $A node1 | $(grep -m1 -o 'JVM Arguments: .*' "$N1/logs/system.log" | grep -o -E -- '-Xm[sxn][0-9]*[GM]|-XX:MaxDirectMemorySize=[0-9a-z]*|-javaagent:[^ ,]*byteman[^ ,]*' | tr '\n' ' ')"
  note "BM-AGENT $A | HBCAP lines so far $(grep -c '^HBCAP' "$NO"); agent errors $(grep -c -E 'Rule\.execute called for|org\.jboss\.byteman.*(Exception|Error)|TypeException' "$NO")"
  # sampler
  rm -f "$L/sampler.stop"
  java -cp "$HB" HbJmx poll 7199 "$N1/hints" "$L/samples.tsv" "$L/sampler.stop" 1000 >> "$OUT/commands.log" 2>&1 &
  SPID=$!; log "sampler pid $SPID (1 s)"; sleep 5
  # phase U
  note "MARK $A U-start ms=$(nowms) off=$(wc -c < "$NO" | tr -d ' ')"
  note "STRESS $A U | $(stress U "$L/stress-U.log")"
  note "MARK $A U-end ms=$(nowms) off=$(wc -c < "$NO" | tr -d ' ')"
  log "+ sleep 60"; sleep 60
  # node 2 down
  log "+ nodetool -p 7299 drain; kill node 2"
  NT 7299 drain >> "$OUT/commands.log" 2>&1; note "DRAIN-RC $A node2 $?"
  kill "$NPID2" 2>/dev/null; for i in $(seq 1 60); do kill -0 "$NPID2" 2>/dev/null || break; sleep 1; done
  kill -0 "$NPID2" 2>/dev/null && { log "node2 still alive: kill -9"; kill -9 "$NPID2"; }
  NPID2=
  dn=0; for i in $(seq 1 30); do NT 7199 status 2>/dev/null | grep -q '^DN  127.0.0.2' && { dn=1; break; }; sleep 2; done
  NT 7199 status > "$L/status-down.txt" 2>&1
  note "STATUS $A node2-down dn=$dn | $(grep -E '^(UN|DN)' "$L/status-down.txt" | awk '{print $1, $2}' | tr '\n' ' ')"
  [ $dn = 1 ] || { log "ABORT: node 2 not DN on node 1"; exit 1; }
  note "MARK $A quiet-start ms=$(nowms) off=$(wc -c < "$NO" | tr -d ' ')"
  log "+ sleep 15 (quiet window, S0)"; sleep 15
  # phase D
  note "MARK $A D-start ms=$(nowms) off=$(wc -c < "$NO" | tr -d ' ')"
  note "STRESS $A D | $(stress D "$L/stress-D.log")"
  note "MARK $A D-end ms=$(nowms) off=$(wc -c < "$NO" | tr -d ' ')"
  log "+ sleep 30 (tail; S1 = last 15 s)"; sleep 30
  note "MARK $A tail-end ms=$(nowms) off=$(wc -c < "$NO" | tr -d ' ')"
  ls -l "$N1/hints" > "$L/hints-dir-listing.txt" 2>&1
  stop_sampler
  grep '^HBCAP' "$NO" > "$L/hbcap.txt"
  note "HBCAP $A | lines $(wc -l < "$L/hbcap.txt" | tr -d ' ') create $(grep -c 'HBCAP create' "$L/hbcap.txt") full $(grep -c 'HBCAP full' "$L/hbcap.txt") allocated $(grep -o 'allocatedBuffers=[0-9]*' "$L/hbcap.txt" | tr '\n' ' ') agent_errors $(grep -c -E 'Rule\.execute called for|org\.jboss\.byteman.*(Exception|Error)|TypeException' "$NO")"
  note "ERRORS $A node1 ERROR=$(grep -c '^ERROR' "$N1/logs/system.log") OOM=$(cat "$N1/logs/system.log" "$NO" | grep -v -E 'CompileCommand|JVM Arguments' | grep -c 'java.lang.OutOfMemoryError') node1_alive=$(kill -0 "$NPID1" 2>/dev/null && echo yes || echo no)"
  grep -E '^(ERROR|WARN)' "$N1/logs/system.log" | cut -c1-300 > "$L/node1-error-warn.txt"
  stop_one NPID1 7199 node1
  cp "$N1/logs/system.log" "$L/node1-system.log"; cp "$N2/logs/system.log" "$L/node2-system.log" 2>/dev/null
  sleep 2; left=$(pgrep -f "$DPAT" | wc -l | tr -d ' ')
  note "ARM-END $A end_ms=$(nowms) daemons_left=$left"
  [ "$left" = 0 ] || { log "ABORT: daemon left after arm $A"; exit 1; }
  rm -rf "$N1" "$N2"
done
trap - EXIT; stop_all; rm -rf "$N1" "$N2"
note "END end_epoch=$(date +%s) daemons_left=$(pgrep -f "$DPAT" | wc -l | tr -d ' ') clone_status_entries=$(git -C "$C" status --short | wc -l | tr -d ' ')"
python3 -I "$H/summarize.py" cluster "$OUT" > "$OUT/readings.txt" 2>> "$OUT/commands.log"; log "readings.txt written ($(wc -l < "$OUT/readings.txt" | tr -d ' ') lines)"
