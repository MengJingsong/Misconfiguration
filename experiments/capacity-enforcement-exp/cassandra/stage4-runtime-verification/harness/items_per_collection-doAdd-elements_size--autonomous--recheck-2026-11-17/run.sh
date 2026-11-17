#!/usr/bin/env bash
# Recheck run (design R8) of items_per_collection-doAdd-elements_size--autonomous, on pc99.
# usage: run.sh <out-dir> <run1|shake>
#   run1:  M = 1e5, 1e6, 1e7 (chunk 1e5), blob 8,000,004 B, positive-control threshold 64MiB, arm G T = 5000 (200 appends)
#   shake: every size / 100 (M = 1e3, 1e4, 1e5, chunk 1e3, blob 80,004 B, 640KiB, T = 50) -- instrument check only
# Run from an ssh session that stays open (the node runs in a systemd --user scope of that session).
set -uo pipefail
OUT=$1; SCALE=${2:-run1}
R=/mydata/s4/ipc-recheck; C=$R/cassandra; N=$R/node; H=$R/harness; FLAG=$R/pause.flag
case $SCALE in
  run1)  M5=100000; M6=1000000; M7=10000000; CH=100000; BLOB=8000004; PTH=64MiB;  GT=5000;;
  shake) M5=1000;   M6=10000;   M7=100000;   CH=1000;   BLOB=80004;   PTH=640KiB; GT=50;;
  *) echo "bad scale"; exit 2;;
esac
GREPS=200; GM=$((GT * GREPS)); BUDGET=14G; HEAP=8G
mkdir -p "$OUT"; L=$OUT
export CASSANDRA_HOME=$C
DPAT='cassandra.service.Cassandra''Daemon'
log()  { echo "[$(date '+%F %T') $(date +%s%3N)] $*" | tee -a "$L/commands.log"; }
note() { echo "$*" >> "$L/summary-raw.txt"; log "$*"; }
die()  { note "STOP: $*"; exit 1; }
NT() { (cd "$C" && bin/nodetool "$@"); }
client() { log "+ s4.py $*"; local r; r=$(python3 -I "$H/s4.py" "$@" 2>>"$L/client.err" | grep '^RESULT'); note "${r:-RESULT missing (see client.err)}"; }
probe() { java -cp "$R/probe" HeapProbe "$@" 2>>"$L/probe.err"; }
snap() { local r; r=$(probe snap "$L/snaps/$1.tsv"); note "SNAP $1 | $r"; }
histo() { jcmd "$DPID" GC.class_histogram > "$L/histo/$1.txt" 2>&1; note "HISTO $1 | $(grep -E '^Total' "$L/histo/$1.txt") | cells $(grep -E 'org\.apache\.cassandra\.db\.rows\.[A-Za-z]*Cell$' "$L/histo/$1.txt" | awk '{n+=$2; b+=$3} END {print n+0, b+0}')"; }
pauses() { local n; n=$(grep -c 'S4PAUSE begin' "$L/node-$LIFE.out" 2>/dev/null); echo "${n:-0}"; }  # shakedown fix S3: grep -c prints 0 and exits 1

# ---- environment
pgrep -f "$DPAT" >/dev/null && die "a Cassandra daemon is already running"
for p in 7000 7199 9042; do ss -ltn | grep -q ":$p " && die "port $p busy"; done
mkdir -p "$L/snaps" "$L/histo"
note "RUN scale=$SCALE M5=$M5 M6=$M6 M7=$M7 chunk=$CH blob=$BLOB pth=$PTH GT=$GT GM=$GM budget=$BUDGET heap=$HEAP start_epoch=$(date +%s)"
{ hostname; uname -r; nproc; free -b; df -B1 /mydata | tail -1; java -version 2>&1; ant -version; python3 --version; swapon --show; } > "$L/env.txt" 2>&1
( cd "$H" && sha256sum HeapProbe.java pause.btm s4.py run.sh analyze.py ) > "$L/harness-sha256.txt"
mkdir -p "$R/probe" && javac -d "$R/probe" "$H/HeapProbe.java" || die "javac HeapProbe"
ulimit -n 100000

# ---- node configuration (shared by L1 and L2)
rm -rf "$N"; mkdir -p "$N"/{data,commitlog,hints,saved_caches,cdc_raw,logs}; cp -R "$C/conf" "$N/conf"
sed "s#@FLAG@#$FLAG#" "$H/pause.btm" > "$R/pause.btm"; rm -f "$FLAG"
write_yaml() { # $1 = L1|L2
  local Y=$N/conf/cassandra.yaml
  grep -v -E '^(data_file_directories|commitlog_directory|hints_directory|saved_caches_directory|cdc_raw_directory|read_request_timeout|native_transport_timeout|authenticator|authorizer):' "$C/conf/cassandra.yaml" | grep -v -E '^    - /var/lib/cassandra/data' > "$Y"
  { echo; echo "# stage-4 recheck overrides ($1)"
    echo "data_file_directories:"; echo "    - $N/data"
    echo "commitlog_directory: $N/commitlog"; echo "hints_directory: $N/hints"
    echo "saved_caches_directory: $N/saved_caches"; echo "cdc_raw_directory: $N/cdc_raw"
    echo "read_request_timeout: 120000ms"; echo "native_transport_timeout: 120s"
    if [ "$1" = L2 ]; then
      echo "authenticator: PasswordAuthenticator"; echo "authorizer: CassandraAuthorizer"
      echo "items_per_collection_warn_threshold: $((GT / 2))"; echo "items_per_collection_fail_threshold: $GT"
    else
      echo "authenticator: AllowAllAuthenticator"; echo "authorizer: AllowAllAuthorizer"
    fi; } >> "$Y"
  diff <(grep -v '^ *#' "$C/conf/cassandra.yaml" | grep -v '^\s*$') <(grep -v '^ *#' "$Y" | grep -v '^\s*$') > "$L/yaml-diff-$1.txt"; }

start_node() { # $1 = L1|L2
  LIFE=$1; write_yaml "$1"
  local BM=$C/build/lib/jars/byteman-4.0.20.jar
  log "+ systemd-run --user --scope -p MemoryMax=$BUDGET -p MemorySwapMax=0 --unit=s4-ipc-recheck-$1 env MAX_HEAP_SIZE=$HEAP JVM_EXTRA_OPTS=-javaagent:$BM=script:$R/pause.btm bin/cassandra -f"
  ( cd "$C" && exec systemd-run --user --scope -p MemoryMax=$BUDGET -p MemorySwapMax=0 --unit="s4-ipc-recheck-$1" \
      env MAX_HEAP_SIZE=$HEAP CASSANDRA_CONF="$N/conf" CASSANDRA_LOG_DIR="$N/logs" \
      JVM_EXTRA_OPTS="-javaagent:$BM=script:$R/pause.btm" bin/cassandra -f ) > "$L/node-$1.out" 2>&1 < /dev/null &
  NPID=$!
  local ok=0
  for i in $(seq 1 180); do
    kill -0 "$NPID" 2>/dev/null || die "node died during start ($1)"
    if NT status 2>/dev/null | grep -q '^UN ' && [ "$(NT statusbinary 2>/dev/null)" = running ]; then ok=1; break; fi
    sleep 2
  done
  [ $ok = 1 ] || die "node not UN/running within 360 s ($1)"
  DPID=$(pgrep -f "$DPAT" | head -1)
  CG=/sys/fs/cgroup$(cut -d: -f3 /proc/$DPID/cgroup)
  note "NODE $1 up daemon_pid=$DPID cgroup=$CG memory.max=$(cat $CG/memory.max) swap.max=$(cat $CG/memory.swap.max)"
  note "JVMARGS $1 $(grep -m1 -o 'JVM Arguments: .*' "$N/logs/system.log" | grep -o -E -- '-Xm[sx][0-9]+[GMgm]|-XX:\+UseG1GC|-javaagent:[^ ,]*' | tr '\n' ' ')"
  grep -E 'Byteman|ERROR|Rule' "$L/node-$1.out" | head -5 > "$L/byteman-$1.txt"
  ( while kill -0 "$DPID" 2>/dev/null; do echo "$(date +%s%3N) $(cat $CG/memory.current 2>/dev/null) $(grep oom_kill $CG/memory.events 2>/dev/null | awk '{print $2}')"; sleep 1; done ) > "$L/memory-$1.txt" 2>/dev/null &
  MSPID=$!; }

stop_node() {
  [ -z "${NPID:-}" ] && return
  log "stopping node $LIFE"
  if kill -0 "$NPID" 2>/dev/null; then
    NT stopdaemon >> "$L/commands.log" 2>&1 & local SDP=$!
    for i in $(seq 1 90); do kill -0 "$NPID" 2>/dev/null || break; sleep 1; done
    kill "$SDP" 2>/dev/null
    if kill -0 "$NPID" 2>/dev/null; then log "still alive after 90 s: kill"; kill "$NPID"; sleep 10; kill -9 "$NPID" 2>/dev/null; fi
  fi
  sleep 2; local left; left=$(pgrep -f "$DPAT")
  [ -n "$left" ] && { log "WARNING: daemon still running ($left): kill -9"; kill -9 $left; sleep 2; }
  pgrep -f "$DPAT" >/dev/null && log "WARNING: daemon still running" || log "no Cassandra daemon left"
  kill "$MSPID" 2>/dev/null
  note "MEMORY $LIFE max_memory_current=$(awk 'BEGIN{m=0} {if ($2+0>m) m=$2+0} END{print m}' "$L/memory-$LIFE.txt") oom_kill_last=$(tail -1 "$L/memory-$LIFE.txt" | awk '{print $3}')"
  cp "$N/logs/system.log" "$L/system-$LIFE.log" 2>/dev/null; cp "$N/logs/gc.log"* "$L/" 2>/dev/null
  for f in "$L"/gc.log*; do [ -e "$f" ] && mv "$f" "$L/$LIFE-$(basename "$f")"; done
  NPID=""; }
finish() { stop_node; rm -f "$FLAG"; rm -rf "$N/data" "$N/commitlog" "$N/hints" "$N/saved_caches" "$N/cdc_raw"; log "node data removed"; note "END end_epoch=$(date +%s)"; }
trap finish EXIT

alive() { kill -0 "$DPID" 2>/dev/null || die "node died"; local o; o=$(tail -1 "$L/memory-$LIFE.txt" | awk '{print $3}'); [ "${o:-0}" = 0 ] || die "oom_kill=$o"; }

compact_check() { # tables...
  log "+ nodetool flush probe"; NT flush probe >> "$L/commands.log" 2>&1 || die "flush"
  for t in "$@"; do
    log "+ nodetool compact probe $t"; NT compact probe "$t" >> "$L/commands.log" 2>&1 || die "compact $t"
  done
  for t in "$@"; do
    local d; d=$(ls -d "$N/data/probe/$t-"* | head -1)
    note "SIZE $t | $(NT tablestats "probe.$t" 2>&1 | grep -E 'SSTable count:|Space used \(live\):|Memtable data size:' | sed 's/^[[:space:]]*//' | tr '\n' ';') du_bytes=$(du -sb --exclude=snapshots --exclude=backups "$d" | cut -f1)"
  done; }

read_arm() { # $1 arm $2 table $3 col [$4 user]
  local arm=$1 t=$2 col=$3
  alive
  snap "$arm-idle0"; sleep 10; snap "$arm-idle1"
  for r in 1 2 3; do
    snap "$arm-r$r-a"; client read "$t" "$col"; snap "$arm-r$r-b"; alive
  done
  histo "$arm-base"
  local p0; p0=$(pauses); touch "$FLAG"
  log "+ s4.py read $t $col (held, flag set)"
  ( python3 -I "$H/s4.py" read "$t" "$col" 2>>"$L/client.err" | grep '^RESULT' > "$L/held-$arm.result" ) &
  local cp=$! got=0
  for i in $(seq 1 1200); do [ "$(pauses)" -gt "$p0" ] && { got=1; break; }; kill -0 $cp 2>/dev/null || break; sleep 0.2; done
  if [ $got = 1 ]; then sleep 0.5; histo "$arm-pause"; note "PAUSE $arm reached | $(grep 'S4PAUSE begin' "$L/node-$LIFE.out" | tail -1)"; else note "PAUSE $arm NOT reached"; fi
  wait $cp; rm -f "$FLAG"; note "HELDREAD $arm | $(cat "$L/held-$arm.result")"; alive; }

# ---- L1: defaults
start_node L1
client setup
client load z 1 1
client load s5 "$M5" "$CH"
client load s6 "$M6" "$CH"
client load s7 "$M7" "$CH"
client loadblob b6 "$BLOB"
alive
compact_check z s5 s6 s7 b6
note "READTHRESHOLDS-DEFAULT $(probe readthresholds false -)"
read_arm Z z v
read_arm S5 s5 v
read_arm S6 s6 v
read_arm S7 s7 v
read_arm B b6 b
# positive control P: the read-size threshold switched on (the knob that binds)
note "READTHRESHOLDS-P $(probe readthresholds true "$PTH")"
touch "$FLAG"
for t in s5 s6 s7; do
  p0=$(pauses); snap "P-$t-a"; client read "$t" v; snap "P-$t-b"; sleep 1
  note "PPAUSE $t new_pause_lines=$(( $(pauses) - p0 ))"
  note "PMETRIC $t $(probe get "org.apache.cassandra.metrics:type=Table,keyspace=probe,scope=$t,name=LocalReadSize" Max) | aborts $(probe get "org.apache.cassandra.metrics:type=Table,keyspace=probe,scope=$t,name=LocalReadSizeAborts" Count)"
  sleep 16; alive
done
rm -f "$FLAG"
note "READTHRESHOLDS-OFF $(probe readthresholds false -)"
grep -n -E '^(ERROR|WARN)' "$N/logs/system.log" | cut -c1-300 > "$L/error-warn-L1.txt"; note "L1 ERROR lines: $(grep -c ':ERROR' "$L/error-warn-L1.txt") WARN lines: $(grep -c ':WARN' "$L/error-warn-L1.txt")"
stop_node

# ---- L2: guardrail on (clause d)
start_node L2
client setupauth g6
S4_USER=app S4_PW=app client guardcheck g6 $((GT + 1))
S4_USER=app S4_PW=app client load g6 "$GM" "$GT"
alive
compact_check g6
S4_USER=app S4_PW=app read_arm G g6 v
grep -n -E '^(ERROR|WARN)' "$N/logs/system.log" | cut -c1-300 > "$L/error-warn-L2.txt"; note "L2 ERROR lines: $(grep -c ':ERROR' "$L/error-warn-L2.txt") WARN lines: $(grep -c ':WARN' "$L/error-warn-L2.txt")"
trap - EXIT; finish
ps -eo cmd | grep '[C]assandraDaemon' > "$L/ps-after.txt"; note "DAEMONS-LEFT $(wc -l < "$L/ps-after.txt")"
python3 -I "$H/analyze.py" "$L" "$SCALE" > "$L/analysis.txt" 2>&1; note "ANALYSIS rc=$?"
