#!/usr/bin/env bash
# Cluster tier (B3, as amended 2026-10-26) of denylist_max_keys_per_table-setDenylistMaxKeysPerTable-value--autonomous.
# usage: cluster-run.sh <outdir-name> <M> <P list...>
#   cluster-run.sh run1 20000 1000 5000 20000 1000     the run (B3c/B3e)
#   cluster-run.sh shake 2000 100 500 2000 100         harness shakedown with a small load (not judged)
# One node on 127.0.0.1 from $W/cassandra-run25, 2 GiB heap (G1), partition_denylist_enabled true, denylist_consistency_level ONE,
# denylist_max_keys_total 1000000; data under $W/node-dlmk (wiped at start and end).
# Instruments: Jmx.java (B3b verbatim) for set and load; read-back of the stored value from system_views.settings (cqlsh);
# after each load: 5 s, jcmd GC.run x2, GC.heap_info (recorded), GC.class_histogram (Total = used heap after GC, runbook fix
# 2026-10-26 defect 2; [B bytes); system.log segment after each load
# (byte offset) for 'has exceeded the', 'Loaded partition denylist cache', 'Error reading partition_denylist'.
# Logs: $W/logs/denylist_max_keys_per_table-setDenylistMaxKeysPerTable/cluster-<outdir-name>/
# Changed 2026-10-27 for the user-authorised cluster re-run (case-file amendments of 2026-10-27, B3d/B3e): H1 the clone and node root
# are read from DLMK_C and DLMK_NODE (defaults reproduce run 1); H2 with DLMK_B2=1 a null label 'B2' follows the post-ingest
# measurement: Jmx set DenylistMaxKeysPerTable 1000 (no load), read-back, then the same measure() -> used_b. Unset: as in run 1.
set -uo pipefail
source ~/Library/Caches/stage4/env.sh
H=$(cd "$(dirname "$0")" && pwd)
RUN=${1:?outdir}; M=${2:?M}; shift 2; PLIST="$*"
L=$W/logs/denylist_max_keys_per_table-setDenylistMaxKeysPerTable/cluster-$RUN
rm -rf "$L"; mkdir -p "$L"; CL=$L/commands.log; S=$L/summary.txt; : > "$CL"; : > "$S"
C=${DLMK_C:-$W/cassandra-run25}; N=${DLMK_NODE:-$W/node-dlmk}
T=$W/tools-dlmk; mkdir -p "$T"; cp "$H/Jmx.java" "$T/Jmx.java"
PID=""
now() { date '+%Y-%m-%dT%H:%M:%S%z'; }
log() { echo "[$(now)] $*" >> "$CL"; }
say() { echo "$*" >> "$S"; log "SUMMARY $*"; }
tmo() { perl -e '$t=shift; $p=fork; if(!$p){exec @ARGV; exit 127} $SIG{ALRM}=sub{kill 9,$p; waitpid $p,0; exit 124}; alarm $t; waitpid $p,0; exit($?>>8)' "$@"; }
nt()  { tmo 300 "$C/bin/nodetool" -h 127.0.0.1 -p 7199 "$@"; }
cq()  { tmo 1800 "$C/bin/cqlsh" 127.0.0.1 --request-timeout=120 "$@"; }
jmx() { ( cd "$W" && tmo 300 java "$T/Jmx.java" 127.0.0.1:7199 "$@" 2>&1 ); }
run() { log "+ $*"; "$@" >> "$CL" 2>&1; local rc=$?; log "  exit=$rc"; return $rc; }
die() { say "ABORT: $*"; stop_node; final_check; exit 1; }
readback() { cq -e "SELECT value FROM system_views.settings WHERE name='denylist_max_keys_per_table'" > "$1" 2>&1; sed -n '4p' "$1" | tr -d ' \r'; }
stop_node() {
  [ -z "$PID" ] && return 0
  kill -0 $PID 2>/dev/null || { PID=""; return 0; }
  run tmo 120 "$C/bin/nodetool" -h 127.0.0.1 -p 7199 drain
  kill $PID 2>/dev/null; for i in $(seq 1 30); do kill -0 $PID 2>/dev/null || break; sleep 1; done
  kill -0 $PID 2>/dev/null && { log "kill -9 $PID"; kill -9 $PID; sleep 1; }
  PID=""; log "node stopped"
}
final_check() {
  local d; d=$(ps -eo command | grep '[C]assandraDaemon'); say "final CassandraDaemon processes: ${d:-none}"
  pgrep -f 'Jmx.java' >/dev/null && say "WARNING: Jmx client still running" || say "no Jmx client left"
  pgrep -f cqlsh >/dev/null && say "WARNING: cqlsh still running" || say "no cqlsh left"
  pgrep jcmd >/dev/null && say "WARNING: jcmd still running" || say "no jcmd left"
  run rm -rf "$N"; say "node dir $N wiped (incl. the CSV): $([ -e "$N" ] && echo no || echo yes)"
}
heap_used_k() { jcmd $PID GC.heap_info 2>&1 | tee -a "$1" | grep -o 'used [0-9]*K' | head -1 | tr -dc '0-9'; }
measure() {   # measure <label>: 5 s, GC.run x2, heap_info, class histogram
  local lab=$1 D=$L/$1; mkdir -p "$D"; sleep 5
  run jcmd $PID GC.run; run jcmd $PID GC.run
  local u; u=$(heap_used_k "$D/heap_info.txt")
  jcmd $PID GC.class_histogram > "$D/histogram.txt" 2>&1
  local b; b=$(awk '$4=="[B"{print $3; exit}' "$D/histogram.txt")
  local bi; bi=$(awk '$4=="[B"{print $2; exit}' "$D/histogram.txt")
  local tot; tot=$(awk '$1=="Total"{print $3}' "$D/histogram.txt")
  # Runbook fix 2026-10-26 (defect 2): "used heap after GC" is the histogram's Total (live bytes after the full GC that
  # GC.class_histogram forces); heap_info's "used" also counts young regions allocated after the GC (16 MiB regions) and is recorded only.
  say "HEAP $lab live_Total_B=$tot heap_info_used_K=$u byteArray_bytes=$b byteArray_instances=$bi"
}
seg_from() { tail -c +$(( $1 + 1 )) "$L/node/system.log"; }
load_label() {   # load_label <label> <P>
  local lab=$1 p=$2 D=$L/$1; mkdir -p "$D"
  say "== $lab: P=$p"
  jmx set DenylistMaxKeysPerTable $p > "$D/set.txt"
  say "SET $lab jmx=[$(tr '\n' ' ' < "$D/set.txt")] readback=$(readback "$D/readback.txt")"
  local off; off=$(stat -f %z "$L/node/system.log")
  local t0; t0=$(perl -MTime::HiRes=time -e 'printf("%d",time()*1000)')
  jmx load > "$D/load.txt"; local t1; t1=$(perl -MTime::HiRes=time -e 'printf("%d",time()*1000)')
  sleep 1; seg_from $off > "$D/system-segment.log"
  grep 'has exceeded the [a-z-]* allowance' "$D/system-segment.log" > "$D/error-exceeded.txt"
  say "LOAD $lab jmx=[$(tr '\n' ' ' < "$D/load.txt")] ms=$(( t1 - t0 )) loaded_lines=[$(grep -o 'Loaded partition denylist cache in [0-9]*ms' "$D/system-segment.log" | tr '\n' ';')] exceeded_lines=$(grep -c . "$D/error-exceeded.txt") allowances=[$(grep -o 'exceeded the [a-z-]* allowance of ([0-9]*)' "$D/error-exceeded.txt" | tr '\n' ';')] read_errors=$(grep -c 'Error reading partition_denylist\|Error reading full partition denylist' "$D/system-segment.log") other_ERROR=$(grep '^ERROR' "$D/system-segment.log" | grep -vc 'has exceeded the [a-z-]* allowance')"
  measure $lab
}

# ------------------------------------------------------------------ pre-checks
say "cluster-run $RUN start $(now) M=$M P=[$PLIST] clone=$C node=$N B2=${DLMK_B2:-unset} harness sha256 $(shasum -a 256 "$0" | cut -c1-12) md5 $(md5 -q "$0" | cut -c1-12) Jmx md5 $(md5 -q "$H/Jmx.java" | cut -c1-12)"
say "clone: $(git -C $C rev-parse --short HEAD)"
d=$(ps -eo command | grep '[C]assandraDaemon'); [ -n "$d" ] && { say "ABORT: a CassandraDaemon is running"; exit 1; }
for p in 7000 7199 9042; do lsof -nP -iTCP:$p -sTCP:LISTEN >/dev/null 2>&1 && { say "ABORT: port $p busy"; exit 1; }; done
say "pre-checks: no CassandraDaemon; ports 7000 7199 9042 free; free disk $(df -h $W | tail -1 | awk '{print $4}')"
rm -rf "$N"
run env DLMK_C="$C" DLMK_NODE="$N" "$H/make-node-conf.sh" partition_denylist_enabled=true denylist_consistency_level=ONE denylist_max_keys_total=1000000
say "YAML $(sed -n '/^# ---- stage4 dlmk lines/,$p' $N/conf/cassandra.yaml | grep -v '^#' | tr '\n' ';')"

# ------------------------------------------------------------------ start (B3e step 1)
mkdir -p "$L/node"
log "+ start node (clone $C, conf $N/conf) MAX_HEAP_SIZE=2G HEAP_NEWSIZE=400M"
CASSANDRA_CONF=$N/conf CASSANDRA_LOG_DIR=$L/node MAX_HEAP_SIZE=2G HEAP_NEWSIZE=400M nohup "$C/bin/cassandra" -f > "$L/node/node.out" 2>&1 < /dev/null &
PID=$!; disown; log "pid $PID"
t0=$(date +%s)
while :; do
  kill -0 $PID 2>/dev/null || die "node died during start"
  if nt status 2>/dev/null | grep -q '^UN  127.0.0.1 ' && [ "$(nt statusbinary 2>/dev/null)" = running ]; then log "up after $(( $(date +%s) - t0 )) s"; break; fi
  [ $(( $(date +%s) - t0 )) -ge 360 ] && die "node not up in 360 s"
  sleep 3
done
say "JVM $(grep -m1 -o 'JVM Arguments: .*' $L/node/system.log | grep -o -- '-Xm[sxn][0-9]*[GM]\|-XX:+UseG1GC' | tr '\n' ' ') initialLoad: $(grep -c 'Loaded partition denylist cache' $L/node/system.log) Loaded lines at start"
cq -e "SELECT name, value FROM system_views.settings WHERE name IN ('partition_denylist_enabled','denylist_reads_enabled','denylist_writes_enabled','denylist_range_reads_enabled','denylist_consistency_level','denylist_max_keys_per_table','denylist_max_keys_total','denylist_refresh')" > "$L/settings.txt" 2>&1
say "SETTINGS $(grep '|' "$L/settings.txt" | grep -v ' name ' | tr -s ' ' | tr '\n' ';')"
run cq -e "CREATE KEYSPACE dl WITH replication={'class':'SimpleStrategy','replication_factor':1}; CREATE TABLE dl.t1 (k blob PRIMARY KEY, v int);"

# ------------------------------------------------------------------ B3e step 2: baseline after an empty load
off=$(stat -f %z "$L/node/system.log"); jmx load > "$L/base-load.txt"; sleep 1
say "BASE load jmx=[$(tr '\n' ' ' < "$L/base-load.txt")] loaded_lines=[$(seg_from $off | grep -o 'Loaded partition denylist cache in [0-9]*ms' | tr '\n' ';')]"
measure base

# ------------------------------------------------------------------ B3e step 3: rejection
jmx set DenylistMaxKeysPerTable 0 > "$L/set0.txt"
say "SET0 jmx=[$(tr '\n' ' ' < "$L/set0.txt")] readback=$(readback "$L/set0-readback.txt")"

# ------------------------------------------------------------------ B3e step 4: insert and flush (B3c)
log "+ generate $M keys of 8192 random bytes -> $N/dl.csv"
python3 -I -c "import os,sys;f=open(sys.argv[1],'w');[f.write('dl,t1,0x'+os.urandom(8192).hex()+'\n') for _ in range(int(sys.argv[2]))]" "$N/dl.csv" "$M"
say "CSV lines=$(wc -l < "$N/dl.csv" | tr -d ' ') bytes=$(stat -f %z "$N/dl.csv")"
log "+ cqlsh COPY system_distributed.partition_denylist FROM $N/dl.csv WITH MAXBATCHSIZE=1 AND CHUNKSIZE=50"
cq -e "COPY system_distributed.partition_denylist (ks_name, table_name, key) FROM '$N/dl.csv' WITH MAXBATCHSIZE=1 AND CHUNKSIZE=50" > "$L/copy.log" 2>&1
say "COPY exit=$? $(grep -E 'rows imported|Processed:|Failed' "$L/copy.log" | tail -2 | tr '\n' ';')"
run nt flush system_distributed
cq -e "SELECT count(*) FROM system_distributed.partition_denylist WHERE ks_name='dl' AND table_name='t1'" > "$L/rows.txt" 2>&1
say "ROWS $(sed -n '4p' "$L/rows.txt" | tr -d ' ')"
measure ingest
if [ "${DLMK_B2:-}" = 1 ]; then   # H2: null label (B3d/B3e amendments 2026-10-27): every label step except the load
  mkdir -p "$L/B2"; say "== B2: null label (set 1000, read-back, no load)"
  jmx set DenylistMaxKeysPerTable 1000 > "$L/B2/set.txt"
  say "SET B2 jmx=[$(tr '\n' ' ' < "$L/B2/set.txt")] readback=$(readback "$L/B2/readback.txt")"
  measure B2
fi

# ------------------------------------------------------------------ B3e step 5
i=0; for p in $PLIST; do i=$((i+1)); load_label "L$i-P$p" $p; done

# ------------------------------------------------------------------ cleanup (B3e step 6, B4)
stop_node
final_check
say "cluster-run $RUN end $(now)"
