#!/usr/bin/env bash
# B29 one clean lifetime on pc72 (two instances + client on one host, loopback), adapted from B22's run-arm.sh.
#   [TREE=tree-I] [EXTRA_YAML=...] [TRACEK=k] run-arm.sh <label> <TA|TB> <Q> <victim heap> <victim direct|auto> [diag] [k0] [k1]
# 1 refuse if a CassandraDaemon runs; fresh clone of the template; start node 1 (victim) then node 2 (peer, 4G); ready + 2 UN
#   (one retry if not)
# 2 thresholds read back by JMX (RfpJmx), K histogram; CL ONE traced read of s at k=k1-1 (informational); sampler; GC + baseline
# 3 client: 20 s warm-up (Q=1, k=1000..1009), then Q workers over k0..k1-1 (default 0..95), each once, until exhausted or 160 s;
#   readings every 5 s; one GC.class_histogram 10 s into the test step if alive
# 4 30 s idle, outcome (OOM lines, hprof), stop survivors, copy small files to the repo (logs/<label>/).
set -uo pipefail
L=$1 TPL=$2 Q=$3 HEAP=$4 DIRECT=$5 DIAG=${6:-} K0=${7:-0} K1=${8:-96}
ROOT=/mydata/s4/b29; H=$ROOT/harness; R=$ROOT/runs/$L
REPO=/proj/misconfiguration-PG0/git-repos/Misconfiguration/experiments/OOM-exp/cassandra/cases/cached_rows_fail_threshold--rfp-static-fetch-whole-partition
V="bash $H/ctl.sh"; C="bash $H/client.sh"
log(){ echo "[$(TZ=America/New_York date '+%F %T %Z')] $*"; }
log "ARM $L template=$TPL tree=${TREE:-tree} Q=$Q heap=$HEAP direct=$DIRECT diag=${DIAG:-no} k=$K0..$((K1-1)) extra_yaml=${EXTRA_YAML:-none}"
ok=0
for try in 1 2; do
  $V prep "$L" "$TPL" || exit 1
  if $V start "$L" 1 "$HEAP" "$DIRECT" "$DIAG" && $V ready "$L" 1 && $V start "$L" 2 4G auto && $V ready "$L" 2 && $V ring "$L"; then ok=1; break; fi
  log "invalid start (try $try)"; $V stop "$L"; [ -d "$R" ] && mv "$R" "$R.badstart$try"
done
[ $ok = 1 ] || { mkdir -p "$R"; echo "INVALID not-ready" > "$R/outcome"; exit 1; }
echo "arm template=$TPL Q=$Q k=$K0..$((K1-1)) tree=${TREE:-tree}" >> "$R/run.meta"
$V rfpk "$L" start > /dev/null
( cd "$R" && $C "$L" stat 127.0.0.1 $((K1-1)) ONE trace > precheck.txt 2>&1 ); head -1 "$R/precheck.txt"
$V sampler "$L"
sleep 5; $V gc "$L"; sleep 3; $V read "$L" base | cut -c1-260
( cd "$R" && setsid nohup bash "$H/client.sh" "$L" run 127.0.0.1 "$Q" "$K0" "$K1" 20 160 > client.csv 2> client.err < /dev/null & )
sleep 3; CP=$(pgrep -f "B29Load run 127.0.0.1 $Q $K0 $K1" | head -1); echo "$CP" > "$R/client.pid"
log "client pid $CP"
t0=$(date +%s); dead=0; histd=0; el=0
while true; do
  sleep 5
  el=$(( $(date +%s) - t0 ))
  if [ "$($V alive "$L" 1)" != ALIVE ]; then log "VICTIM DEAD at +${el}s"; dead=1; break; fi
  [ "$($V alive "$L" 2)" != ALIVE ] && log "PEER n2 DEAD at +${el}s"
  $V read "$L" "t+$el" | cut -c1-300
  tail -1 "$R/client.csv" | cut -c1-200
  if [ $histd = 0 ] && [ $el -ge 30 ]; then $V hist "$L" test10; histd=1; fi
  kill -0 "$CP" 2>/dev/null || break
done
for i in $(seq 1 60); do kill -0 "$CP" 2>/dev/null || break; sleep 1; done
kill "$CP" 2>/dev/null; sleep 1; kill -9 "$CP" 2>/dev/null
grep SUMMARY "$R/client.csv"; tail -3 "$R/client.err"
if [ -n "${TRACEK:-}" ] && [ "$($V alive "$L" 1)" = ALIVE ]; then   # DIAG: one traced test query at k=$TRACEK
  ( cd "$R" && $C "$L" one 127.0.0.1 "$TRACEK" QUORUM trace > trace.txt 2>&1 ); head -1 "$R/trace.txt"; grep -i "replica filtering" "$R/trace.txt"
fi
if [ $dead = 0 ] && [ "$($V alive "$L" 1)" = ALIVE ]; then
  sleep 30; $V read "$L" end-idle | cut -c1-260; $V rfpk "$L" end > /dev/null
  $V gc "$L"; sleep 3; $V read "$L" end-postgc | cut -c1-260
fi
[ "$($V alive "$L" 1)" != ALIVE ] && [ $dead = 0 ] && { dead=1; log "victim dead after the load"; }
peer=$($V alive "$L" 2)
$V stop "$L"
N1=$R/n1
oomtype=$(grep -h -o -m1 "java.lang.OutOfMemoryError: [A-Za-z ]*" "$N1/logs/system.log" "$N1/stdout.log" 2>/dev/null | head -1)
if [ $dead = 1 ] && [ -n "$oomtype" ]; then echo "OOM type=\"$oomtype\" at+${el}s peer=$peer" > "$R/outcome"
elif [ $dead = 1 ]; then echo "DEAD-noOOM at+${el}s (scope events: $(cat $R/memory.events.last 2>/dev/null | tr '\n' ' ')) peer=$peer" > "$R/outcome"
else echo "SURVIVED peer=$peer" > "$R/outcome"; fi
cat "$R/outcome"
D=$REPO/logs/$L; mkdir -p "$D"
cp "$R"/{readings.csv,samples.csv,run.meta,outcome,rfpk.txt,ring.txt,precheck.txt,trace.txt} "$D"/ 2>/dev/null
cp "$N1/yaml.diff" "$D/yaml-n1.diff"; cp "$R/n2/yaml.diff" "$D/yaml-n2.diff"; cp "$R/n2/env.diff" "$D/env-n2.diff"
cp "$R/memory.events.last" "$D/memory.events" 2>/dev/null
grep -E '^(t,|[0-9]{13},|SUMMARY)' "$R/client.csv" > "$D/client.csv"
cp "$R/queries.csv" "$D/queries.csv" 2>/dev/null
tail -20 "$R/client.err" > "$D/client.err.tail" 2>/dev/null; [ -s "$D/client.err.tail" ] || rm -f "$D/client.err.tail"
grep -h -m3 -B2 -A40 'java\.lang\.OutOfMemoryError' "$N1/logs/system.log" "$N1/stdout.log" 2>/dev/null | head -200 > "$D/oom-excerpt.txt"
[ -s "$D/oom-excerpt.txt" ] || rm -f "$D/oom-excerpt.txt"
grep -h 'Replica filtering protection\|cached over\|ReadSizeAbort\|read_size\|Query cancelled\|exceeded' "$N1/logs/system.log" "$N1/logs/debug.log" 2>/dev/null | cut -c1-400 | head -20 > "$D/rfp-excerpt.txt"
echo "rfp-cached-over lines n1: $(grep -c 'Replica filtering protection has cached over' "$N1/logs/system.log")" >> "$D/rfp-excerpt.txt"
[ -f "$R/histo-test10.txt" ] && head -30 "$R/histo-test10.txt" > "$D/histo-test10-top.txt"
[ -f "$R/probe.txt" ] && cp "$R/probe.txt" "$D/probe.txt"
python3 "$H/gcwin.py" "$N1/logs" > "$D/gcwin.txt"
grep -h 'Pause Full\|Humongous regions:' "$N1/logs"/gc.log* 2>/dev/null | tail -12 > "$D/gc-tail.txt"
ls -la "$N1" "$R/n2" | grep -i 'hprof\|hs_err' > "$D/hprof.ls" || rm -f "$D/hprof.ls"
log "END $L $(cat "$R/outcome")"
