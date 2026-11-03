#!/usr/bin/env bash
# Cluster tier (B3, as amended 2026-10-26) of hints_PAGE_SIZE-computeNext-position--autonomous.
# usage: source ~/Library/Caches/stage4/env.sh; cluster-run.sh
#   run 1:     no variables (ARMS="16k 64k 1m"; N = 16384 / 4096 / 256 writes of v = 16 KiB / 64 KiB / 1 MiB)
#   shakedown: ARMS=64k NSCALE=8 OUT=$W/logs/<stem>/shakedown-cluster cluster-run.sh   (N divided by NSCALE)
# Two nodes from the one built clone (never built while a node runs), each with its own conf, data, logs (amendment B3a):
#   node 1 = 127.0.0.1, JMX 7199, Byteman hp1.btm (counts sent hints per page; observe-only file and decode-path rules)
#   node 2 = 127.0.0.2, JMX 7299, Byteman hp2.btm (holds each hint 300 ms in HintVerbHandler.doVerb), offheap_buffers memtables
# Per arm (B3e as amended): wipe, yaml, start node 1 then node 2 (UN/UN, statusbinary running); drain + kill node 2, wait DN;
#   stress (no-warmup); flush; 15 s; listpendinghints + JMX counters (before); pausehandoff; start the 2 s class-histogram sampler
#   against node 2 and start node 2; UN + statusbinary; schema agreement; 20 s baseline window; resumehandoff; poll
#   listpendinghints every 5 s until empty (or 600 s); 10 s tail; stop sampler; JMX counters + listpendinghints (after);
#   drain + stop both nodes.
# Marks are epoch ms and byte offsets of node 1's node1.out (the HPCAP lines). Env: C, OUT, HB, ARMS, NSCALE.
set -uo pipefail
S=hints_PAGE_SIZE-computeNext-position--autonomous
ARMS=${ARMS:-"16k 64k 1m"}; NSCALE=${NSCALE:-1}
H=$(cd "$(dirname "$0")" && pwd); C=${C:-$W/cassandra-run37}; HB=${HB:-$W/harness-bin-hp}
N1=$W/node-hp1; N2=$W/node-hp2
OUT=${OUT:-$W/logs/$S/cluster}
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
( cd "$W" && java -cp "$BMJAR:$C/build/classes/main:$C/build/lib/jars/*" org.jboss.byteman.check.TestScript -v "$H/hp1.btm" "$H/hp2.btm" ) > "$OUT/btm-check.txt" 2>&1
grep -q 'TestScript: no errors' "$OUT/btm-check.txt" || { log "ABORT: btm rules do not type-check (btm-check.txt)"; exit 1; }
note "RUN ARMS=[$ARMS] NSCALE=$NSCALE clone=$(git -C "$C" rev-parse HEAD) status_entries=$(git -C "$C" status --short | wc -l | tr -d ' ') hp1_sha256=$(shasum -a 256 "$H/hp1.btm" | cut -c1-16) hp2_sha256=$(shasum -a 256 "$H/hp2.btm" | cut -c1-16) start_epoch=$(date +%s)"
mkdir -p "$HB"; javac -d "$HB" "$H/HpJmx.java" >> "$OUT/commands.log" 2>&1 || { log "ABORT: javac HpJmx"; exit 1; }
NT() { local port=$1; shift; (cd "$C" && bin/nodetool -p "$port" "$@"); }
NPID1=; NPID2=; SPID=
stop_sampler() { [ -n "$SPID" ] || return 0; touch "$L/sampler.stop"; for i in $(seq 1 30); do kill -0 "$SPID" 2>/dev/null || break; sleep 1; done; kill "$SPID" 2>/dev/null; SPID=; log "sampler stopped"; }
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

mknode() { # $1 dir, $2 address, $3 jmx port, $4 node number
  local N=$1 Y=$1/conf/cassandra.yaml
  rm -rf "$N"; mkdir -p "$N"/{data,commitlog,hints,saved_caches,cdc_raw,logs}; cp -R "$C/conf" "$N/conf"
  grep -v -E '^(cluster_name|auto_bootstrap|num_tokens|hinted_handoff_enabled|max_hint_window|hinted_handoff_throttle|max_hints_delivery_threads|concurrent_writes|write_request_timeout|memtable_allocation_type|hints_directory|data_file_directories|commitlog_directory|saved_caches_directory|cdc_raw_directory|listen_address|rpc_address):' "$C/conf/cassandra.yaml" > "$Y"
  { echo; echo "# stage-4 overrides (hints_PAGE_SIZE)"
    echo "cluster_name: hpcap"; echo "auto_bootstrap: false"; echo "num_tokens: 16"
    echo "hinted_handoff_enabled: true"; echo "max_hint_window: 3h"; echo "hinted_handoff_throttle: 0KiB"; echo "max_hints_delivery_threads: 1"
    echo "concurrent_writes: 64"; echo "write_request_timeout: 5000ms"
    echo "data_file_directories:"; echo "    - $N/data"
    echo "commitlog_directory: $N/commitlog"; echo "hints_directory: $N/hints"
    echo "saved_caches_directory: $N/saved_caches"; echo "cdc_raw_directory: $N/cdc_raw"
    echo "listen_address: $2"; echo "rpc_address: $2"
    if [ "$4" = 2 ]; then echo "memtable_allocation_type: offheap_buffers"; else echo "memtable_allocation_type: heap_buffers"; fi
  } >> "$Y"
  sed -i '' -e "s/^JMX_PORT=\"7199\"/JMX_PORT=\"$3\"/" "$N/conf/cassandra-env.sh"
  grep '^JMX_PORT=' "$N/conf/cassandra-env.sh" | head -1; }

launch() { # $1 dir, $2 address, $3 btm, $4 out file, $5 pid var
  log "+ MAX_HEAP_SIZE=2G HEAP_NEWSIZE=400M CASSANDRA_CONF=$1/conf CASSANDRA_LOG_DIR=$1/logs JVM_EXTRA_OPTS=\"-javaagent:$BMJAR=script:$3\" bin/cassandra -f  ($2)"
  ( cd "$C" && MAX_HEAP_SIZE=2G HEAP_NEWSIZE=400M CASSANDRA_CONF="$1/conf" CASSANDRA_LOG_DIR="$1/logs" JVM_EXTRA_OPTS="-javaagent:$BMJAR=script:$3" exec bin/cassandra -f ) >> "$4" 2>&1 < /dev/null &
  local pid=$!; eval "$5=$pid"; log "$2 launcher pid $pid"; }
wait_up() { # $1 address, $2 jmx port, $3 pid
  for i in $(seq 1 120); do
    kill -0 "$3" 2>/dev/null || { log "ABORT: $1 died during start"; exit 1; }
    if NT 7199 status 2>/dev/null | grep -q "^UN  $1" && [ "$(NT "$2" statusbinary 2>/dev/null)" = running ]; then
      log "$1 UN, statusbinary running; process: $(ps -o command= -p "$3" | cut -c1-60)"; return 0; fi
    sleep 3
  done
  log "ABORT: $1 not UN/running within 360 s"; exit 1; }
off() { wc -c < "$NO" | tr -d ' '; }
pending() { NT 7199 listpendinghints 2>&1 | tr -s ' ' | tr '\n' '|'; }

for A in $ARMS; do
  case "$A" in 16k) V=16384; N=16384;; 64k) V=65536; N=4096;; 1m) V=1048576; N=256;; *) log "ABORT: arm $A"; exit 1;; esac
  N=$(( N / NSCALE ))
  L=$OUT/arm-$A; mkdir -p "$L"; NO=$L/node1.out
  note "ARM $A v=$V N=$N start_ms=$(nowms)"
  note "JMX $A node1 $(mknode "$N1" 127.0.0.1 7199 1) node2 $(mknode "$N2" 127.0.0.2 7299 2)"
  tail -20 "$N1/conf/cassandra.yaml" > "$L/yaml-overrides-node1.txt"; tail -20 "$N2/conf/cassandra.yaml" > "$L/yaml-overrides-node2.txt"
  : > "$NO"
  launch "$N1" 127.0.0.1 "$H/hp1.btm" "$NO" NPID1; wait_up 127.0.0.1 7199 "$NPID1"
  launch "$N2" 127.0.0.2 "$H/hp2.btm" "$L/node2-first.out" NPID2; wait_up 127.0.0.2 7299 "$NPID2"
  NT 7199 status > "$L/status-start.txt" 2>&1
  note "STATUS $A start | $(grep -E '^(UN|DN|UJ)' "$L/status-start.txt" | awk '{print $1, $2}' | tr '\n' ' ')"
  note "READBACK $A node1 | $(grep -m1 'Node configuration' "$N1/logs/system.log" | grep -o -E '(hinted_handoff_enabled|hinted_handoff_throttle|max_hints_delivery_threads|max_hint_window|concurrent_writes|write_request_timeout|memtable_allocation_type|hints_flush_period|max_hints_file_size|cluster_name|auto_bootstrap)=[^;]*' | tr '\n' ' ')"
  note "READBACK $A node2 | $(grep -m1 'Node configuration' "$N2/logs/system.log" | grep -o -E '(hinted_handoff_enabled|concurrent_writes|write_request_timeout|memtable_allocation_type|memtable_offheap_space|memtable_heap_space|cluster_name|auto_bootstrap)=[^;]*' | tr '\n' ' ')"
  note "JVMARGS $A node1 | $(grep -m1 -o 'JVM Arguments: .*' "$N1/logs/system.log" | grep -o -E -- '-Xm[sxn][0-9]*[GM]|-javaagent:[^ ,]*byteman[^ ,]*|script:[^ ,\]]*' | tr '\n' ' ')"
  note "JVMARGS $A node2 | $(grep -m1 -o 'JVM Arguments: .*' "$N2/logs/system.log" | grep -o -E -- '-Xm[sxn][0-9]*[GM]|-javaagent:[^ ,]*byteman[^ ,]*|script:[^ ,\]]*' | tr '\n' ' ')"
  # node 2 down
  log "+ nodetool -p 7299 drain; kill node 2"
  NT 7299 drain >> "$OUT/commands.log" 2>&1; note "DRAIN-RC $A node2 $?"
  kill "$NPID2" 2>/dev/null; for i in $(seq 1 60); do kill -0 "$NPID2" 2>/dev/null || break; sleep 1; done
  kill -0 "$NPID2" 2>/dev/null && { log "node2 still alive: kill -9"; kill -9 "$NPID2"; }
  NPID2=
  cp "$N2/logs/system.log" "$L/node2-first-system.log"
  dn=0; for i in $(seq 1 30); do NT 7199 status 2>/dev/null | grep -q '^DN  127.0.0.2' && { dn=1; break; }; sleep 2; done
  NT 7199 status > "$L/status-down.txt" 2>&1
  note "STATUS $A node2-down dn=$dn | $(grep -E '^(UN|DN)' "$L/status-down.txt" | awk '{print $1, $2}' | tr '\n' ' ')"
  [ $dn = 1 ] || { log "ABORT: node 2 not DN on node 1"; exit 1; }
  # stress (B3c as amended: no-warmup)
  note "MARK $A stress-start ms=$(nowms) off=$(off)"
  log "+ tools/bin/cassandra-stress write n=$N no-warmup cl=ONE -col 'size=FIXED($V)' 'n=FIXED(1)' -schema 'replication(factor=2)' keyspace=hp -rate threads=16 -node 127.0.0.1"
  ( cd "$C" && tools/bin/cassandra-stress write n="$N" no-warmup cl=ONE -col "size=FIXED($V)" 'n=FIXED(1)' -schema 'replication(factor=2)' keyspace=hp -rate threads=16 -node 127.0.0.1 ) > "$L/stress.log" 2>&1 < /dev/null
  src=$?
  note "STRESS $A rc=$src | $(grep -E '^(Op rate|Partition rate|Total partitions|Total errors|Total operation time)' "$L/stress.log" | sed 's/  */ /g' | tr '\n' ';')"
  note "MARK $A stress-end ms=$(nowms) off=$(off)"
  NT 7199 flush >> "$OUT/commands.log" 2>&1; note "FLUSH-RC $A node1 $?"
  log "+ sleep 15 (hints flush period 10 s)"; sleep 15
  note "PENDING $A before | $(pending)"
  note "JMXCOUNT $A before | $(java -cp "$HB" HpJmx once 7199)"
  ls -l "$N1/hints" > "$L/hints-dir-before.txt" 2>&1
  note "HINTSDIR $A before | files=$(ls "$N1/hints" | grep -c '\.hints$') bytes=$(find "$N1/hints" -name '*.hints' -exec stat -f %z {} + | awk '{s+=$1} END {print s+0}')"
  NT 7199 pausehandoff >> "$OUT/commands.log" 2>&1; note "PAUSE-RC $A $? ms=$(nowms) off=$(off)"
  # node 2 back, with the sampler
  rm -f "$L/sampler.stop"
  launch "$N2" 127.0.0.2 "$H/hp2.btm" "$L/node2.out" NPID2
  P2=$NPID2
  ( while [ ! -f "$L/sampler.stop" ]; do
      t0=$(nowms); h=$(jcmd "$P2" GC.class_histogram 2>&1); t1=$(nowms)
      echo "#SAMPLE t0=$t0 t1=$t1"
      printf '%s\n' "$h" | grep -E ' org\.apache\.cassandra\.hints\.Hint$| \[B |^Total'
      printf '%s\n' "$h" | grep -v -E '^ *[0-9]+: |^Total|^[0-9]+:$|^$| num +#instances|^-+$' | head -3 | sed 's/^/ERR /'
      el=$(( $(nowms) - t0 )); [ $el -lt 2000 ] && sleep "$(python3 -c "print((2000-$el)/1000)")"
    done ) > "$L/hist.txt" 2>&1 &
  SPID=$!; log "sampler pid $SPID (2 s) on node 2 pid $P2"
  wait_up 127.0.0.2 7299 "$NPID2"
  agree=0; for i in $(seq 1 30); do
    NT 7199 describecluster > "$L/describecluster.txt" 2>&1
    nv=$(awk '/Schema versions:/{f=1;next} f&&/^[[:space:]]*$/{f=0} f&&/: \[/{c++} END{print c+0}' "$L/describecluster.txt")
    [ "$nv" = 1 ] && { agree=1; break; }; sleep 2; done
  note "SCHEMA $A agree=$agree versions=$nv"
  note "MARK $A baseline-start ms=$(nowms) off=$(off)"
  log "+ sleep 20 (baseline window, handoff paused)"; sleep 20
  note "MARK $A baseline-end ms=$(nowms) off=$(off)"
  NT 7199 resumehandoff >> "$OUT/commands.log" 2>&1; note "MARK $A resume rc=$? ms=$(nowms) off=$(off)"
  done_=0; t_start=$(date +%s)
  while [ $(( $(date +%s) - t_start )) -lt 600 ]; do
    sleep 5
    p=$(NT 7199 listpendinghints 2>&1); nf=$(ls "$N1/hints" | grep -c '\.hints$')
    # stop condition (amendment B3e, after shakedown 1): listpendinghints omits the open writer and the file being dispatched
    # (HintsStore.java:108-125), so delivery is complete only when node 1's hints dir also holds no .hints file (HintsDispatchExecutor.java:298-300)
    if [ "$nf" = 0 ] && printf '%s' "$p" | grep -q 'does not have any pending hints'; then done_=1; break; fi
    kill -0 "$NPID1" 2>/dev/null && kill -0 "$NPID2" 2>/dev/null || { log "a node died during delivery"; break; }
  done
  note "MARK $A delivery-end done=$done_ ms=$(nowms) off=$(off) secs=$(( $(date +%s) - t_start ))"
  log "+ sleep 10 (tail)"; sleep 10
  note "MARK $A tail-end ms=$(nowms) off=$(off)"
  stop_sampler
  note "PENDING $A after | $(pending)"
  note "JMXCOUNT $A after | $(java -cp "$HB" HpJmx once 7199)"
  ls -l "$N1/hints" > "$L/hints-dir-after.txt" 2>&1
  grep '^HPCAP' "$NO" > "$L/hpcap.txt"
  note "HPCAP $A | lines $(wc -l < "$L/hpcap.txt" | tr -d ' ') pages $(grep -c '^HPCAP page' "$L/hpcap.txt") files $(grep -c '^HPCAP file start' "$L/hpcap.txt") decoded $(grep -c '^HPCAP decoded' "$L/hpcap.txt") abort $(grep -c 'action=ABORT' "$L/hpcap.txt") agent_errors1 $(grep -c -E 'Rule\.execute called for|org\.jboss\.byteman.*(Exception|Error)|TypeException' "$NO") agent_errors2 $(grep -c -E 'Rule\.execute called for|org\.jboss\.byteman.*(Exception|Error)|TypeException' "$L/node2.out")"
  note "SAMPLES $A | $(grep -c '^#SAMPLE' "$L/hist.txt") samples, $(grep -c '^ERR ' "$L/hist.txt") error lines"
  for n in 1 2; do eval "ND=\$N$n"
    note "ERRORS $A node$n ERROR=$(grep -c '^ERROR' "$ND/logs/system.log") OOM=$(grep -v -E 'CompileCommand|JVM Arguments' "$ND/logs/system.log" | grep -c 'java.lang.OutOfMemoryError') hint_warn=$(grep -c -E 'WARN.*[Hh]int' "$ND/logs/system.log")"
    grep -E '^(ERROR|WARN)' "$ND/logs/system.log" | cut -c1-300 > "$L/node$n-error-warn.txt"; done
  stop_one NPID2 7299 node2; stop_one NPID1 7199 node1
  cp "$N1/logs/system.log" "$L/node1-system.log"; cp "$N2/logs/system.log" "$L/node2-system.log" 2>/dev/null
  sleep 2; left=$(pgrep -f "$DPAT" | wc -l | tr -d ' ')
  note "ARM-END $A end_ms=$(nowms) daemons_left=$left"
  [ "$left" = 0 ] || { log "ABORT: daemon left after arm $A"; exit 1; }
  rm -rf "$N1" "$N2"
done
trap - EXIT; stop_all; rm -rf "$N1" "$N2"
note "END end_epoch=$(date +%s) daemons_left=$(pgrep -f "$DPAT" | wc -l | tr -d ' ') clone_status_entries=$(git -C "$C" status --short | wc -l | tr -d ' ')"
python3 -I "$H/summarize.py" cluster "$OUT" > "$OUT/readings.txt" 2>> "$OUT/commands.log"; log "readings.txt written ($(wc -l < "$OUT/readings.txt" | tr -d ' ') lines)"
