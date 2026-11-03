#!/usr/bin/env bash
# Cluster tier (B3, as amended 2026-10-24) of cdc_total_space-applySimpleConfig-cdc_total_space--autonomous.
# usage: cluster-run.sh <outdir-name> [arm ...]
#   arms (label  cdc_total_space  cdc_block_writes  profile  N  cdc_enabled):
#     b256 256MiB true cdc 200000 true    n256 256MiB false cdc 200000 true
#     b1024 1024MiB true cdc 200000 true  n1024 1024MiB false cdc 200000 true
#     bdef 0MiB true cdc 320000 true      ndef 0MiB false cdc 320000 true
#     ctl-plain 256MiB true plain 200000 true      ctl-cdcoff 256MiB true cdc 200000 false
#     startup-cdcoff-0  (start-up read-back only: cdc_enabled false, 0MiB)
#     shake  (harness shakedown: 64MiB blocking, N=8000; not a reading)
#   default arm list: b256 b1024 bdef n256 n1024 ndef ctl-plain ctl-cdcoff startup-cdcoff-0
# One node, 127.0.0.1, clone $W/cassandra-run6, node directories under $W/node-cdc (wiped before and after every arm).
# Re-run (cluster run 2, case re-frozen 2026-10-24 after the B3h (a) amendment): CDC_CLONE=$W/cassandra-run9 CDC_NODE=$W/node-cdc2
#   CDC_CTL_FLUSH=all -> ctl-plain runs `nodetool flush` (all keyspaces) instead of `nodetool flush ks` and writes <arm>/flush.txt
#   (flush start/end ms, exit). Defaults reproduce run 1.
# Logs: $W/logs/cdc_total_space-applySimpleConfig/cluster-<outdir>/ : commands.log, summary.txt, <arm>/ (node logs, settings.txt,
#       sampler.csv/.events, stress.log, count.txt, logscan.txt, statvfs.txt)
set -uo pipefail
source ~/Library/Caches/stage4/env.sh
H=$(cd "$(dirname "$0")" && pwd)
RUN=${1:?outdir}; shift
ARMS=${*:-b256 b1024 bdef n256 n1024 ndef ctl-plain ctl-cdcoff startup-cdcoff-0}
L=$W/logs/cdc_total_space-applySimpleConfig/cluster-$RUN
[ -e "$L" ] && mv "$L" "$L.attempt-$(date +%s)"
mkdir -p "$L"; CL=$L/commands.log; S=$L/summary.txt; : > "$CL"; : > "$S"
C=${CDC_CLONE:-$W/cassandra-run6}; N=${CDC_NODE:-$W/node-cdc}; CTLF=${CDC_CTL_FLUSH:-ks}; PID=""
ms()  { perl -MTime::HiRes=time -e 'printf("%d\n", time()*1000)'; }
now() { date '+%Y-%m-%dT%H:%M:%S%z'; }
log() { echo "[$(now)] $*" >> "$CL"; }
say() { echo "$*" >> "$S"; log "SUMMARY $*"; }
tmo() { perl -e '$t=shift; $p=fork; if(!$p){exec @ARGV; exit 127} $SIG{ALRM}=sub{kill 9,$p; waitpid $p,0; exit 124}; alarm $t; waitpid $p,0; exit($?>>8)' "$@"; }
nt()  { tmo 120 "$C/bin/nodetool" -h 127.0.0.1 -p 7199 "$@"; }
cq()  { tmo 700 "$C/bin/cqlsh" 127.0.0.1 9042 --request-timeout=600 "$@"; }
run() { log "+ $*"; "$@" >> "$CL" 2>&1; local rc=$?; log "  exit=$rc"; return $rc; }

make_conf() {   # make_conf key=value ...
  rm -rf "$N"; mkdir -p "$N/data" "$N/commitlog" "$N/hints" "$N/saved_caches" "$N/cdc_raw"
  cp -R "$C/conf" "$N/conf"
  git -C "$C" show HEAD:conf/cassandra.yaml > "$N/shipped.yaml"
  { echo "cluster_name: stage4-cdc6"; echo "num_tokens: 1"; echo "initial_token: 0"; echo "auto_bootstrap: false"
    echo "listen_address: 127.0.0.1"; echo "rpc_address: 127.0.0.1"
    echo "data_file_directories:"; echo "    - $N/data"
    echo "commitlog_directory: $N/commitlog"; echo "hints_directory: $N/hints"; echo "saved_caches_directory: $N/saved_caches"
    echo "cdc_raw_directory: $N/cdc_raw"; echo "commitlog_segment_size: 32MiB"; echo "cdc_free_space_check_interval: 250ms"
    for kv in "$@"; do echo "${kv%%=*}: ${kv#*=}"; done; } > "$N/lines.yaml"
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
open(n + '/conf/cassandra.yaml', 'w').write('\n'.join(out) + '\n# ---- stage4 cdc6 lines ----\n' + '\n'.join(add) + '\n')
PY
}
start_node() {  # start_node <logdir>
  local ld=$1; mkdir -p "$ld"
  log "+ start node (conf $N/conf, logs $ld)"
  CASSANDRA_CONF=$N/conf CASSANDRA_LOG_DIR=$ld MAX_HEAP_SIZE=2G HEAP_NEWSIZE=400M \
    nohup "$C/bin/cassandra" -f > "$ld/node.out" 2>&1 < /dev/null &
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
    run tmo 300 "$C/bin/nodetool" -h 127.0.0.1 -p 7199 drain
    kill $PID 2>/dev/null; for i in $(seq 1 60); do kill -0 $PID 2>/dev/null || break; sleep 1; done
    kill -0 $PID 2>/dev/null && { log "kill -9 $PID"; kill -9 $PID; sleep 1; }
  fi
  PID=""; log "node stopped"
}
final_check() {
  pkill -9 -f cassandra-stress 2>/dev/null
  local d; d=$(ps -eo command | grep '[C]assandraDaemon'); say "final CassandraDaemon processes: ${d:-none}"
  pgrep -f cassandra-stress >/dev/null && say "WARNING: cassandra-stress still running" || say "no cassandra-stress left"
  rm -rf "$N"; say "node-cdc wiped: $([ -e "$N" ] && echo no || echo yes)"
}
die() { say "ABORT: $*"; stop_node; final_check; exit 1; }
trap 'die "interrupted"' INT TERM
settings() {    # settings <file>
  cq -e "SELECT name, value FROM system_views.settings WHERE name IN ('cdc_enabled','cdc_total_space','cdc_block_writes','commitlog_segment_size','cdc_raw_directory','cdc_free_space_check_interval','commitlog_directory');" > "$1" 2>&1
}
statvfs() { python3 -c "import os,sys; s=os.statvfs(sys.argv[1]); t=s.f_blocks*s.f_frsize; print('path=%s total_bytes=%d frsize=%d free_bytes=%d expected_default_MiB=%d' % (sys.argv[1], t, s.f_frsize, s.f_bavail*s.f_frsize, min(4096, (t//1048576)//8)))" "$1"; }

arm() {   # arm <label> <total> <block> <profile> <N> <cdc_enabled>
  local lab=$1 tot=$2 blk=$3 prof=$4 n=$5 en=$6 D=$L/$1
  mkdir -p "$D"
  say "== $lab cdc_total_space=$tot cdc_block_writes=$blk profile=$prof N=$n cdc_enabled=$en start $(now)"
  make_conf cdc_enabled=$en cdc_total_space=$tot cdc_block_writes=$blk
  say "YAML $lab $(sed -n '/^# ---- stage4 cdc6 lines/,$p' $N/conf/cassandra.yaml | grep -v '^#' | tr '\n' ';')"
  start_node "$D"; wait_up || die "$lab: node did not start"
  settings "$D/settings.txt"; statvfs "$N/cdc_raw" > "$D/statvfs.txt"
  say "SETTINGS $lab $(grep -E '^ *(cdc_|commitlog_)' "$D/settings.txt" | tr -s ' ' | tr '\n' ';')"
  say "STATVFS $lab $(cat "$D/statvfs.txt")"
  if [ "$prof" = none ]; then python3 "$H/logscan.py" "$D" > "$D/logscan.txt"; say "LOGSCAN $lab $(cat "$D/logscan.txt")"; stop_node; rm -rf "$N"; return 0; fi
  run cq -e "CREATE KEYSPACE IF NOT EXISTS ks WITH replication = {'class':'SimpleStrategy','replication_factor':1}; CREATE TABLE IF NOT EXISTS ks.c (k uuid PRIMARY KEY, v blob) WITH cdc=true; CREATE TABLE IF NOT EXISTS ks.p (k uuid PRIMARY KEY, v blob) WITH cdc=false;"
  local flag=$D/sampling; touch "$flag"
  python3 "$H/cdc-sampler.py" "$N/cdc_raw" "$D/sampler" 0.25 "$flag" &
  local spid=$!
  sleep 3
  local t0=$(ms); local tbl=c; [ "$prof" = plain ] && tbl=p
  log "+ cassandra-stress user profile=$H/$prof.yaml ops(insert=1) n=$n no-warmup -rate threads=16 throttle=2000/s -errors retries=0 ignore -node 127.0.0.1"
  tmo 1800 "$C/tools/bin/cassandra-stress" user profile="$H/$prof.yaml" "ops(insert=1)" n=$n no-warmup -rate threads=16 throttle=2000/s -errors retries=0 ignore -node 127.0.0.1 > "$D/stress.log" 2>&1
  local rc=$? t1=$(ms)
  say "STRESS $lab exit=$rc start_ms=$t0 end_ms=$t1 $(grep -E '^(Op rate|Partition rate|Row rate|Total partitions|Total errors|Total operation time)' "$D/stress.log" | tr -s ' ' | tr '\n' ';')"
  sleep 5
  if [ "$lab" = ctl-plain ]; then
    if [ "$CTLF" = all ]; then local f0=$(ms); run nt flush; local frc=$?; local f1=$(ms)
      echo "flush=all command=nodetool_flush start_ms=$f0 end_ms=$f1 exit=$frc" > "$D/flush.txt"; say "FLUSH $lab $(cat "$D/flush.txt")"
    else run nt flush ks; fi
    sleep 30
  fi
  local t2=$(ms)
  cq -e "SELECT count(*) FROM ks.$tbl;" > "$D/count.txt" 2>&1
  say "COUNT $lab ks.$tbl $(grep -E '^ *[0-9]+ *$' "$D/count.txt" | tr -d ' ') (after_ms=$t2)"
  sleep 2; rm -f "$flag"; wait $spid 2>/dev/null
  python3 "$H/logscan.py" "$D" > "$D/logscan.txt"; say "LOGSCAN $lab $(cat "$D/logscan.txt")"
  say "SAMPLER $lab $(python3 -c "
import csv,sys
r=list(csv.DictReader(open(sys.argv[1]))); t0=int(sys.argv[2]); t1=int(sys.argv[3]); t2=int(sys.argv[4])
mx=max(r,key=lambda x:int(x['link_bytes'])); g=max(int(x['gap_ms']) for x in r)
d=sum(1 for l in open(sys.argv[5]) if ' - ' in l)
w=[x for x in r if t0<=int(x['ts_ms'])<=t1]; last=[x for x in r if int(x['ts_ms'])>=t2]
print('samples=%d max_link_bytes=%s max_links=%s max_idx_bytes=%d max_alloc=%d max_gap_ms=%d links_deleted_events=%d end_of_stress_links=%s final_links=%s final_link_bytes=%s' % (len(r), mx['link_bytes'], mx['links'], max(int(x['idx_bytes']) for x in r), max(int(x['link_alloc_bytes']) for x in r), g, d, w[-1]['links'] if w else '-', r[-1]['links'], r[-1]['link_bytes']))
" "$D/sampler.csv" $t0 $t1 $t2 "$D/sampler.events")"
  stop_node; rm -rf "$N"
  say "== $lab end $(now)"
}

say "cluster-run $RUN start $(now) arms: $ARMS; runner sha256 $(shasum -a 256 "$0" | cut -c1-16); clone $C; node $N; ctl-plain flush $CTLF"
say "clone $(git -C $C describe --tags) $(git -C $C rev-parse --short HEAD)"
d=$(ps -eo command | grep '[C]assandraDaemon'); [ -n "$d" ] && { say "ABORT: a CassandraDaemon is running"; exit 1; }
for p in 7000 7199 9042 9091; do lsof -nP -iTCP:$p -sTCP:LISTEN >/dev/null 2>&1 && { say "ABORT: port $p busy"; exit 1; }; done
say "pre-checks: no CassandraDaemon; ports 7000 7199 9042 9091 free; free disk $(df -h $W | tail -1 | awk '{print $4}')"
for a in $ARMS; do
  case $a in
    b256) arm b256 256MiB true cdc 200000 true ;;
    b1024) arm b1024 1024MiB true cdc 200000 true ;;
    bdef) arm bdef 0MiB true cdc 320000 true ;;
    n256) arm n256 256MiB false cdc 200000 true ;;
    n1024) arm n1024 1024MiB false cdc 200000 true ;;
    ndef) arm ndef 0MiB false cdc 320000 true ;;
    ctl-plain) arm ctl-plain 256MiB true plain 200000 true ;;
    ctl-cdcoff) arm ctl-cdcoff 256MiB true cdc 200000 false ;;
    startup-cdcoff-0) arm startup-cdcoff-0 0MiB true none 0 false ;;
    shake) arm shake 64MiB true cdc 8000 true ;;
    *) say "unknown arm $a" ;;
  esac
  say "free disk after $a: $(df -h $W | tail -1 | awk '{print $4}')"
done
stop_node; final_check
say "cluster-run $RUN end $(now)"
