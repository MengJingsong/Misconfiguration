#!/usr/bin/env bash
# Cluster tier (B3e), one knob value per invocation:
#   bash 20-cluster.sh <pct> <tag> [nchunks]
#   e.g. bash 20-cluster.sh 1.0 pct1.0          (loads chunks until data dir >= 1.5 GiB, records the count)
#        bash 20-cluster.sh 0.5 pct0.5 <N>      (loads exactly N chunks: same dataset as the first run)
#
# Mapping from the design (runbook defects R1-R3 in the results file):
#   /local/disk/cass-data (2G loop-mounted ext4, `sudo mount`) -> $C/mnt, a 2 GiB tmpfs mounted in a private
#     user+mount namespace (unshare -rm), no sudo; the mount disappears when this script exits.
#   "wipe data dir, keep the mount, restart"                  -> each knob value gets a fresh 2 GiB tmpfs and a fresh node.
#   table "ks.tbl"                                              -> ks.standard1 (the table cassandra-stress writes).
#   /tmp anything                                               -> $C/tmp (java.io.tmpdir), $C/home (HOME for nodetool/cqlsh history).
# Everything else (commitlog, hints, saved caches, cdc, node logs) is on local disk under $C.
# Logs every command and its output (set -x) to $C/run.log; stops at the first failed check;
# stops the node it started and checks that no CassandraDaemon is left.
set -euo pipefail
PCT=${1:?pct}
TAG=${2:?tag}
NCHUNKS=${3:-}
RUN=~/short-run/max_space_usable_for_compactions_in_percentage-hasDiskSpaceForCompactionsAndStreams-availableForCompaction
SRC=$RUN/cassandra
C=$RUN/cluster/$TAG
SELF=$RUN/harness/20-cluster.sh

if [ -z "${IN_NS:-}" ]; then
  # host side: refuse to start if a node already runs or the ports are taken
  # match java processes only: a plain grep also matches any shell whose command line names the daemon (attempt 1, H2)
  if ps -eo comm,args | awk '$1=="java" && /CassandraDaemon/' | grep .; then echo "a Cassandra node is already running: abort"; exit 1; fi
  if ss -ltn | grep -E ':(7000|7199|9042) '; then echo "port busy: abort"; exit 1; fi
  if [ -e "$C" ]; then echo "$C exists: abort (use a new tag)"; exit 1; fi
  mkdir -p "$C"
  IN_NS=1 exec unshare -rm --propagation private bash "$SELF" "$@"
fi

exec > >(tee -a "$C/run.log") 2>&1
set -x
date -u +%FT%TZ; date +%s%3N
id -u
MNT=$C/mnt
mkdir -p "$MNT" "$C/conf" "$C/logs" "$C/commitlog" "$C/hints" "$C/saved_caches" "$C/cdc_raw" "$C/tmp" "$C/home"
mount -t tmpfs -o size=2G tmpfs "$MNT"
df -B1 "$MNT"
mkdir -p "$MNT/data"
# known-answer check of the disk instrument: 100 MiB written must show in du and in df's used/avail
a0=$(df -B1 --output=avail "$MNT" | tail -1)
dd if=/dev/zero of="$MNT/data/ka.bin" bs=1M count=100 status=none
ka_du=$(du -sb "$MNT/data/ka.bin" | cut -f1); a1=$(df -B1 --output=avail "$MNT" | tail -1)
echo "KNOWN_ANSWER du=$ka_du df_avail_drop=$((a0 - a1)) expected=$((100 * 1024 * 1024))"
[ "$ka_du" -eq $((100 * 1024 * 1024)) ] && [ $((a0 - a1)) -eq $((100 * 1024 * 1024)) ] || { echo "disk instrument check failed"; exit 1; }
rm "$MNT/data/ka.bin"
df -B1 "$MNT"
export HOME=$C/home
export JAVA_TOOL_OPTIONS="-XX:-UsePerfData -Djava.io.tmpdir=$C/tmp"
export CASSANDRA_CONF=$C/conf
export CASSANDRA_LOG_DIR=$C/logs
cd "$SRC"
NT=bin/nodetool
TARGET=$((1536 * 1024 * 1024))   # B3c: ~1.5 GiB on disk
CHUNK=500000                      # rows per cassandra-stress call
MAXCHUNKS=20

# ---- B3a: config ----
cp -r conf/. "$C/conf/"
python3 - "$C/conf/cassandra.yaml" "$MNT/data" "$C" "$PCT" <<'EOF'
import sys
path, data, c, pct = sys.argv[1:]
s = open(path).read()
s += f"""
# --- stage-4 short path, case max_space_usable_for_compactions_in_percentage (B3a) ---
data_file_directories:
    - {data}
commitlog_directory: {c}/commitlog
hints_directory: {c}/hints
saved_caches_directory: {c}/saved_caches
cdc_raw_directory: {c}/cdc_raw
max_space_usable_for_compactions_in_percentage: {pct}
min_free_space_per_drive: 10MiB
skip_stream_disk_space_check: false
"""
open(path, "w").write(s)
EOF
tail -14 "$C/conf/cassandra.yaml"
diff <(grep -v '^\s*#' conf/cassandra.yaml | grep -v '^\s*$') <(grep -v '^\s*#' "$C/conf/cassandra.yaml" | grep -v '^\s*$') || true

PID=
stop_node() {
  set +e
  if [ -n "$PID" ] && kill -0 "$PID" 2>/dev/null; then
    kill "$PID"
    for i in $(seq 1 60); do kill -0 "$PID" 2>/dev/null || break; sleep 1; done
    kill -0 "$PID" 2>/dev/null && kill -9 "$PID"
  fi
  sleep 1
  ps -eo comm,pid,args | awk '$1=="java" && /CassandraDaemon/' | grep . && echo "LEFTOVER node" || echo "NODE_STOPPED none left"
  for p in $SAMPLER_PIDS; do kill "$p" 2>/dev/null; done
  df -B1 "$MNT"
  date -u +%FT%TZ
}
SAMPLER_PIDS=
trap stop_node EXIT

# ---- B3e step 1: start (bin/cassandra -f, in the background; -R because the namespace maps us to uid 0) ----
bin/cassandra -f -R -p "$C/cassandra.pid" > "$C/logs/stdout.log" 2>&1 &
PID=$!
echo "cassandra pid $PID"
ok=
for i in $(seq 1 180); do
  if ! kill -0 "$PID" 2>/dev/null; then echo "node died during start"; tail -50 "$C/logs/stdout.log"; exit 1; fi
  if $NT status 2>/dev/null | grep -q '^UN' && [ "$($NT statusbinary 2>/dev/null | tail -1)" = running ]; then ok=1; break; fi
  sleep 2
done
[ -n "$ok" ] || { echo "node not up in time"; exit 1; }
$NT status
grep -o -E 'max_space_usable_for_compactions_in_percentage=[^;]*|min_free_space_per_drive=[^;]*|skip_stream_disk_space_check=[^;]*|data_file_directories=[^;]*' "$C/logs/system.log" | sort -u

# ---- B3e step 2: schema, disable autocompaction, load, verify size ----
STRESS="tools/bin/cassandra-stress"
$STRESS write n=1 no-warmup -pop seq=1..1 -schema keyspace=ks "replication(factor=1)" -node 127.0.0.1 -rate threads=1 > "$C/stress-schema.log" 2>&1
grep -E 'Total errors|Total partitions|Op rate' "$C/stress-schema.log"
$NT disableautocompaction ks standard1
$NT statusautocompaction ks standard1
$NT describecluster | head -5
i=0
while :; do
  if [ -n "$NCHUNKS" ]; then [ "$i" -ge "$NCHUNKS" ] && break
  else
    used=$(du -sb "$MNT/data" | cut -f1)
    [ "$used" -ge "$TARGET" ] && break
    [ "$i" -ge "$MAXCHUNKS" ] && { echo "target not reached in $MAXCHUNKS chunks"; exit 1; }
  fi
  avail=$(df -B1 --output=avail "$MNT" | tail -1)
  [ "$avail" -ge $((300 * 1024 * 1024)) ] || { echo "less than 300 MiB left on the data fs: abort load"; exit 1; }
  start=$((i * CHUNK + 1)); end=$(((i + 1) * CHUNK))
  $STRESS write n=$CHUNK no-warmup -pop seq=$start..$end -schema keyspace=ks "replication(factor=1)" -node 127.0.0.1 -rate threads=50 > "$C/stress-$i.log" 2>&1
  grep -E 'Total errors|Total partitions|Op rate|Total operation time' "$C/stress-$i.log"
  $NT flush ks standard1
  i=$((i + 1))
  echo "LOAD chunk=$i rows=$end du_data=$(du -sb "$MNT/data" | cut -f1) df_avail=$(df -B1 --output=avail "$MNT" | tail -1)"
done
echo "LOAD_DONE nchunks=$i rows=$((i * CHUNK))"
$NT statusautocompaction ks standard1
$NT compactionstats
du -sb "$MNT/data" "$MNT"/data/ks/standard1-*
df -B1 "$MNT"
ls -l "$MNT"/data/ks/standard1-*/*Data.db
$NT tablestats ks.standard1 | grep -E 'SSTable count|Space used|Number of partitions'
avail=$(df -B1 --output=avail "$MNT" | tail -1)
input=$(ls -l "$MNT"/data/ks/standard1-*/*Data.db | awk '{s+=$5} END {print s}')
echo "PRECOMPACT df_avail=$avail budget_expected=$(python3 -c "print(round(($avail - 10*1024*1024) * $PCT))") data_db_bytes=$input"

# ---- B3e step 3: disk sampler (2 s) and compactionstats/tpstats poller ----
( while :; do echo "$(date +%s%3N) du_data=$(du -sb "$MNT/data" | cut -f1) df_used=$(df -B1 --output=used "$MNT" | tail -1) df_avail=$(df -B1 --output=avail "$MNT" | tail -1)"; sleep 2; done ) > "$C/sample-disk.log" 2>&1 &
SAMPLER_PIDS="$!"
( while :; do echo "=== $(date +%s%3N)"; $NT compactionstats 2>&1 | grep -v JAVA_TOOL; $NT tpstats 2>&1 | grep -E 'CompactionExecutor'; sleep 2; done ) > "$C/sample-compactionstats.log" 2>&1 &
SAMPLER_PIDS="$SAMPLER_PIDS $!"
sleep 4

# ---- B3e step 4: the compaction ----
echo "COMPACT_START $(date +%s%3N)"
rc=0
$NT compact ks standard1 > "$C/nodetool-compact.out" 2>&1 || rc=$?
echo "COMPACT_END $(date +%s%3N) rc=$rc"
cat "$C/nodetool-compact.out" | head -40
for i in $(seq 1 60); do
  if $NT compactionstats | grep -q 'pending tasks: 0' && ! $NT compactionstats | grep -q -i 'compaction  *ks'; then break; fi
  sleep 2
done
sleep 4
for p in $SAMPLER_PIDS; do kill "$p" || true; done
SAMPLER_PIDS=
$NT compactionstats
du -sb "$MNT/data" "$MNT"/data/ks/standard1-*
df -B1 "$MNT"
ls -l "$MNT"/data/ks/standard1-*/*Data.db
$NT tablestats ks.standard1 | grep -E 'SSTable count|Space used|Number of partitions'
$NT compactionhistory | grep -E 'keyspace_name|ks ' || true
echo "PEAK du_data=$(awk '{split($2,a,"="); if (a[2]>m) m=a[2]} END {print m}' "$C/sample-disk.log") df_used=$(awk '{split($3,a,"="); if (a[2]>m) m=a[2]} END {print m}' "$C/sample-disk.log") samples=$(wc -l < "$C/sample-disk.log")"

# grep the logs (B3d pattern, verbatim; then the other lines the same code path writes)
grep -E "Not enough space for compaction|Reducing scope|FileStore .* has only" "$C/logs/system.log" || echo "B3d pattern: no match"
grep -E "insufficient space to compact" "$C/logs/system.log" || echo "no 'insufficient space' line"
grep -E "bytes available, checking if we can write" "$C/logs/debug.log" || echo "no Directories DEBUG line"
grep -E "Compaction space check is disabled" "$C/logs/system.log" "$C/logs/debug.log" || echo "space check not disabled"
grep -E "Compacted \(|Compacting \(" "$C/logs/debug.log" | cut -c1-400 || true
grep -E '^(ERROR|WARN)' "$C/logs/system.log" | cut -c1-400 || true

# ---- stop (trap) ----
echo CLUSTER_DONE
