#!/usr/bin/env bash
# Cluster tier (B3, amendments C1-C7 of 2026-10-27) of ExecuteMessage_literal_1000-traceQuery-1000--autonomous.
# Node/conf/start/stop functions adapted from harness/commitlog_segment_size-applySimpleConfig-commitlog_segment_size--autonomous/cluster-run.sh
# (yaml lines, cells, readings and JFR window are new).
# usage: cluster-run.sh <label> [shake]
#   r1:    cells P499 P500 P65536 P1M Q65536 Q1M with N = 200 (S <= 65536) / 20 (1 MiB)   (C2, C4)
#   shake: same cells, N = 5 each (not a reading)
# One node, 127.0.0.1, clone $W/cassandra-run57, node files $W/node-emt (fresh at start, removed at the end).
# Logs: $W/logs/<stem>/cluster-<label>/ : commands.log, summary.txt, node.out, system.log, conf-lines.yaml, <cell>/ (d0-files.txt, cell.out,
#       sess-files.txt, ev-files.txt, pt-files.txt, tablestats-sessions.txt, tablestats-pt.txt, scan.out; P1M also alloc.jfr, jfr-print.txt)
set -uo pipefail
source ~/Library/Caches/stage4/env.sh
STEM=ExecuteMessage_literal_1000-traceQuery-1000--autonomous
H=$(cd "$(dirname "$0")" && pwd)
RUN=${1:?label}; MODE=${2:-r1}
L=$W/logs/$STEM/cluster-$RUN
[ -e "$L" ] && mv "$L" "$L.attempt-$(date +%s)"
mkdir -p "$L"; CL=$L/commands.log; SM=$L/summary.txt; : > "$CL"; : > "$SM"
C=$W/cassandra-run57; N=$W/node-emt; PID=""
DRV=$(ls "$C"/lib/cassandra-driver-internal-only-*.zip | head -1)
now() { date '+%Y-%m-%dT%H:%M:%S%z'; }
log() { echo "[$(now)] $*" >> "$CL"; }
say() { echo "$*" >> "$SM"; log "SUMMARY $*"; }
tmo() { perl -e '$t=shift; $p=fork; if(!$p){exec @ARGV; exit 127} $SIG{ALRM}=sub{kill 9,$p; waitpid $p,0; exit 124}; alarm $t; waitpid $p,0; exit($?>>8)' "$@"; }
nt()  { tmo 300 "$C/bin/nodetool" -h 127.0.0.1 -p 7199 "$@"; }
run() { log "+ $*"; "$@" >> "$CL" 2>&1; local rc=$?; log "  exit=$rc"; return $rc; }
py()  { tmo 1800 python3 -I "$H/probe.py" "$DRV" "$@"; }
MAIN=$$
log "cluster-run $RUN mode=$MODE clone=$C $(git -C "$C" describe --tags) $(git -C "$C" rev-parse HEAD) probe_sha=$(shasum -a 256 "$H/probe.py" | cut -c1-16) script_sha=$(shasum -a 256 "$0" | cut -c1-16)"

make_conf() {
  rm -rf "$N"; mkdir -p "$N/data" "$N/commitlog" "$N/hints" "$N/saved_caches" "$N/cdc_raw" "$N/logs"
  cp -R "$C/conf" "$N/conf"
  git -C "$C" show HEAD:conf/cassandra.yaml > "$N/shipped.yaml"
  { echo "cluster_name: stage4-emt"; echo "num_tokens: 1"; echo "initial_token: 0"
    echo "listen_address: 127.0.0.1"; echo "rpc_address: 127.0.0.1"
    echo "data_file_directories:"; echo "    - $N/data"
    echo "commitlog_directory: $N/commitlog"; echo "hints_directory: $N/hints"; echo "saved_caches_directory: $N/saved_caches"
    echo "cdc_raw_directory: $N/cdc_raw"; echo "auto_snapshot: false"; } > "$N/lines.yaml"
  python3 - "$N" <<'PY'
import re, sys
n = sys.argv[1]
add = open(n + '/lines.yaml').read().splitlines()
keys = {l.split(':', 1)[0] for l in add if re.match(r'^[A-Za-z_]+:', l)}
out, skip = [], False
for l in open(n + '/shipped.yaml').read().splitlines():
    m = re.match(r'^([A-Za-z_]+):', l)
    if m:
        skip = m.group(1) in keys
        if skip:
            continue
    elif skip and (l.startswith((' ', '\t', '-')) or l.strip() == '' or l.lstrip().startswith('#')):
        continue
    else:
        skip = False
    out.append(l)
open(n + '/conf/cassandra.yaml', 'w').write('\n'.join(out) + '\n# ---- stage4 emt lines ----\n' + '\n'.join(add) + '\n')
PY
  cp "$N/lines.yaml" "$L/conf-lines.yaml"
}
start_node() {
  log "+ start node (conf $N/conf, logs $N/logs)"
  CASSANDRA_CONF=$N/conf CASSANDRA_LOG_DIR=$N/logs MAX_HEAP_SIZE=1G HEAP_NEWSIZE=200M \
    nohup "$C/bin/cassandra" -f > "$L/node.out" 2>&1 < /dev/null &
  PID=$!; disown; log "  pid $PID"
}
wait_up() {
  local t0=$(date +%s)
  while :; do
    kill -0 $PID 2>/dev/null || { log "pid $PID died"; return 2; }
    if nt status 2>/dev/null | grep -q '^UN  127.0.0.1 ' && [ "$(nt statusbinary 2>/dev/null)" = running ]; then log "up after $(( $(date +%s) - t0 )) s"; return 0; fi
    [ $(( $(date +%s) - t0 )) -ge 300 ] && { log "not up in 300 s"; return 1; }
    sleep 3
  done
}
stop_node() {
  [ -z "$PID" ] && return 0
  if kill -0 $PID 2>/dev/null; then
    run tmo 120 "$C/bin/nodetool" -h 127.0.0.1 -p 7199 stopdaemon
    for i in $(seq 1 60); do kill -0 $PID 2>/dev/null || break; sleep 1; done
    kill -0 $PID 2>/dev/null && { log "kill $PID"; kill $PID; sleep 10; }
    kill -0 $PID 2>/dev/null && { log "kill -9 $PID"; kill -9 $PID; sleep 1; }
  fi
  PID=""; log "node stopped"
}
final_check() {
  local d; d=$(ps -eo command | grep '[C]assandraDaemon'); say "final Cassandra daemon processes: ${d:-none}"
  pgrep -f "$H/probe.py" >/dev/null && say "WARNING: probe.py still running" || say "no probe.py left"
  rm -rf "$N"; say "node-emt removed: $([ -e "$N" ] && echo no || echo yes)"
}
die() { [ "$$" = "$MAIN" ] || exit 1; say "ABORT: $*"; [ -n "$PID" ] && cp "$N/logs/system.log" "$L/system.log" 2>/dev/null; stop_node; final_check; exit 1; }
trap 'die "interrupted"' INT TERM

bsum() {  # bsum <table dir glob under data> <outfile>  -> prints the byte sum of files outside snapshots/ and backups/
  local out=$2; : > "$out"
  for d in $N/data/$1; do
    [ -d "$d" ] || continue
    find "$d" -type f ! -path '*/snapshots/*' ! -path '*/backups/*' -exec stat -f '%z %N' {} + >> "$out" 2>/dev/null
  done
  awk '{s+=$1} END {printf "%d\n", s+0}' "$out"
}
live() { awk -F': ' '/Space used \(live\)/ {print $2; exit}' "$1"; }

if [ "$MODE" = shake ]; then NS=5; NB=5; else NS=200; NB=20; fi
CELLS="P:499:$NS P:500:$NS P:65536:$NS P:1048576:$NB Q:65536:$NS Q:1048576:$NB"
log "cells: $CELLS"
pgrep -f 'org.apache.cassandra.service.Cassandra[D]aemon' >/dev/null && { say "ABORT: a node is already running"; exit 1; }
make_conf
start_node
wait_up || die "node did not start"
grep -m1 'Node configuration' "$N/logs/system.log" | tr ';' '\n' | grep -E 'auto_snapshot=|trace_type_query_ttl=|rpc_address=|memtable_allocation_type=' > "$L/node-config.txt"
say "node config: $(tr '\n' ' ' < "$L/node-config.txt")"
sleep 30
py schema >> "$CL" 2>&1 || die "schema"
for cell in $CELLS; do
  P=${cell%%:*}; R=${cell#*:}; S=${R%%:*}; NN=${R#*:}
  case $S in 1048576) lab=${P}1M;; *) lab=$P$S;; esac
  D=$L/$lab; mkdir -p "$D"
  log "=== cell $lab path=$P S=$S N=$NN"
  # TRUNCATE is the first step of the cell (probe.py); D0 is taken right after it, before the first request
  if [ "$lab" = P1M ]; then run jcmd $PID JFR.start name=emt settings=profile filename="$D/alloc.jfr"; fi
  ( py cell "$P" "$S" "$NN" > "$D/cell.out" 2>&1; echo "rc=$?" >> "$D/cell.out" ) &
  CP=$!
  for i in $(seq 1 600); do grep -q '^TRUNCATED' "$D/cell.out" 2>/dev/null && break; sleep 0.1; done
  D0=$(bsum 'system_traces/sessions-*' "$D/d0-files.txt"); log "D0=$D0"
  wait $CP
  if [ "$lab" = P1M ]; then run jcmd $PID JFR.stop name=emt; fi
  cline=$(grep '^CELL ' "$D/cell.out" || echo "CELL missing")
  run nt flush system_traces; run nt flush p
  DS=$(bsum 'system_traces/sessions-*' "$D/sess-files.txt")
  DE=$(bsum 'system_traces/events-*' "$D/ev-files.txt")
  DP=$(bsum 'p/t-*' "$D/pt-files.txt")
  nt tablestats system_traces.sessions > "$D/tablestats-sessions.txt" 2>&1
  nt tablestats p.t > "$D/tablestats-pt.txt" 2>&1
  py scan > "$D/scan.out" 2>&1; echo "rc=$?" >> "$D/scan.out"
  sline=$(grep '^SCAN ' "$D/scan.out" || echo "SCAN missing")
  say "CELLSUM cell=$lab D0=$D0 Dsess=$DS LiveSess=$(live "$D/tablestats-sessions.txt") Dev=$DE Dpt=$DP LivePt=$(live "$D/tablestats-pt.txt")"
  say "  $cline"
  say "  $sline"
  grep -c '^REQFAIL' "$D/cell.out" | xargs -I{} log "REQFAIL lines: {}"
done
if [ -f "$L/P1M/alloc.jfr" ]; then
  jfr print --events jdk.ObjectAllocationOutsideTLAB --stack-depth 64 "$L/P1M/alloc.jfr" > "$L/P1M/jfr-print.txt" 2>&1
  T=$(python3 - "$L/P1M/jfr-print.txt" <<'PY'
import re, sys
txt = open(sys.argv[1]).read()
U = {'bytes': 1, 'byte': 1, 'kB': 1024, 'MB': 1024**2, 'GB': 1024**3}
n = 0
for ev in txt.split('jdk.ObjectAllocationOutsideTLAB {')[1:]:
    m = re.search(r'allocationSize = ([\d.]+) (\w+)', ev)
    if m and float(m.group(1)) * U.get(m.group(2), 0) >= 1024**2 and 'toCQLLiteral' in ev:
        n += 1
print(n)
PY
)
  say "JFR T=$T (ObjectAllocationOutsideTLAB >= 1 MiB with a toCQLLiteral frame, P1M cell)"
fi
cp "$N/logs/system.log" "$L/system.log"
say "system.log ERROR lines: $(grep -c '^ERROR' "$L/system.log")"
stop_node
final_check
log "cluster-run $RUN done"
