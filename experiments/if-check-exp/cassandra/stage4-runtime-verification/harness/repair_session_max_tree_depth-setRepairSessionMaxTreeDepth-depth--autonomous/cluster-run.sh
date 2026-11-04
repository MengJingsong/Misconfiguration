#!/usr/bin/env bash
# Cluster tier (B3, as amended 2026-10-25) of repair_session_max_tree_depth-setRepairSessionMaxTreeDepth-depth--autonomous.
# usage: cluster-run.sh <outdir-name> [stress_n]
#   cluster-run.sh run1             the run: stress n=2500000, labels d10 d16 d20 d16r, set 9 first
#   cluster-run.sh shake 30000      harness shakedown with a small load (not judged)
# Two nodes on this host (127.0.0.1 token -2^63 JMX 7199, 127.0.0.2 token 0 JMX 7200), one clone each,
# repair_session_space 1024MiB, 4 GiB heaps, data under $W/node-rsmtds/nN (wiped at start and end).
# Instruments: Jmx.java (B3b, verbatim) for set/read-back and the n1 direct-memory poller; jcmd GC.class_histogram every 1 s
# on n1 and n2; debug.log segments for 'Allocating direct buffer', 'Prepared AEService trees', 'Created N merkle trees'.
# Logs: $W/logs/repair_session_max_tree_depth-setRepairSessionMaxTreeDepth/cluster-<outdir-name>/
# Changed 2026-10-27 for the cluster re-run (Amendment 2026-10-27 (after run 1, authorised by the user) — B3d, B3e):
#   - paths from the environment, defaults = run 1: RSMTD_C1 (n1 clone), RSMTD_C2 (n2 clone), RSMTD_NODE (node root);
#   - RSMTD_BM=1: TestScript check of rsmtd.btm, n1 started with the Byteman agent (rsmtd.btm, observe only), agent check
#     after start, and per label the RSMTD lines n1 wrote to node.out after the label's offsets -> n1-rsmtd.txt, plus an
#     EVENT summary line. With RSMTD_BM unset the script does what run 1's did.
set -uo pipefail
source ~/Library/Caches/stage4/env.sh
H=$(cd "$(dirname "$0")" && pwd)
RUN=${1:?outdir}; STRESS_N=${2:-2500000}
SPACE=1024
L=$W/logs/repair_session_max_tree_depth-setRepairSessionMaxTreeDepth/cluster-$RUN
rm -rf "$L"; mkdir -p "$L"; CL=$L/commands.log; S=$L/summary.txt; : > "$CL"; : > "$S"
C1=${RSMTD_C1:-$W/cassandra-run24}; C2=${RSMTD_C2:-$W/cassandra-run24-n2}; NB=${RSMTD_NODE:-$W/node-rsmtds}
BM=${RSMTD_BM:-0}; BMJAR=$C1/build/lib/jars/byteman-4.0.20.jar
export RSMTD_C1=$C1 RSMTD_C2=$C2 RSMTD_NODE=$NB
T=$W/tools-rsmtds; mkdir -p "$T"; cp "$H/Jmx.java" "$T/Jmx.java"
addr()  { case $1 in n1) echo 127.0.0.1;; n2) echo 127.0.0.2;; esac; }
port()  { case $1 in n1) echo 7199;; n2) echo 7200;; esac; }
clone() { case $1 in n1) echo $C1;; n2) echo $C2;; esac; }
getpid() { eval echo "\${PID_$1:-}"; }
setpid() { eval "PID_$1=$2"; }
NODES="n1 n2"
RS=org.apache.cassandra.db:type=RepairService

ms()  { perl -MTime::HiRes=time -e 'printf("%d\n", time()*1000)'; }
now() { date '+%Y-%m-%dT%H:%M:%S%z'; }
log() { echo "[$(now)] $*" >> "$CL"; }
say() { echo "$*" >> "$S"; log "SUMMARY $*"; }
tmo() { perl -e '$t=shift; $p=fork; if(!$p){exec @ARGV; exit 127} $SIG{ALRM}=sub{kill 9,$p; waitpid $p,0; exit 124}; alarm $t; waitpid $p,0; exit($?>>8)' "$@"; }
nt()  { local n=$1; shift; tmo 120 "$C1/bin/nodetool" -h 127.0.0.1 -p $(port $n) "$@"; }
jmx() { local n=$1; shift; ( cd "$W" && tmo 60 java "$T/Jmx.java" 127.0.0.1:$(port $n) "$@" 2>&1 ); }
run() { log "+ $*"; "$@" >> "$CL" 2>&1; local rc=$?; log "  exit=$rc"; return $rc; }
die() { say "ABORT: $*"; stop_all; final_check; exit 1; }

start_node() {
  local n=$1 ld=$2; mkdir -p "$ld"
  local xo=""; [ "$BM" = 1 ] && [ $n = n1 ] && xo="-javaagent:$BMJAR=script:$H/rsmtd.btm,boot:$BMJAR"
  log "+ start $n (clone $(clone $n), conf $NB/$n/conf, logs $ld) MAX_HEAP_SIZE=4G HEAP_NEWSIZE=800M JVM_EXTRA_OPTS=[$xo]"
  CASSANDRA_CONF=$NB/$n/conf CASSANDRA_LOG_DIR=$ld MAX_HEAP_SIZE=4G HEAP_NEWSIZE=800M JVM_EXTRA_OPTS="$xo" \
    nohup "$(clone $n)/bin/cassandra" -f > "$ld/node.out" 2>&1 < /dev/null &
  setpid $n $!; disown; log "  $n pid $(getpid $n)"
}
wait_up() {
  local n=$1 lim=$2 t0=$(date +%s)
  while :; do
    kill -0 $(getpid $n) 2>/dev/null || { log "$n pid $(getpid $n) died"; return 2; }
    if nt $n status 2>/dev/null | grep -q "^UN  $(addr $n) " && [ "$(nt $n statusbinary 2>/dev/null)" = running ]; then
      log "$n up after $(( $(date +%s) - t0 )) s"; return 0; fi
    [ $(( $(date +%s) - t0 )) -ge $lim ] && { log "$n not up in $lim s"; return 1; }
    sleep 3
  done
}
stop_node() {
  local n=$1; local p; p=$(getpid $n)
  [ -z "$p" ] && return 0
  kill -0 $p 2>/dev/null || { setpid $n ""; return 0; }
  run tmo 60 "$C1/bin/nodetool" -h 127.0.0.1 -p $(port $n) drain
  kill $p 2>/dev/null; for i in $(seq 1 30); do kill -0 $p 2>/dev/null || break; sleep 1; done
  kill -0 $p 2>/dev/null && { log "kill -9 $n $p"; kill -9 $p; sleep 1; }
  setpid $n ""; log "$n stopped"
}
stop_all() { for n in $NODES; do stop_node $n; done; pkill -9 -f cassandra-stress 2>/dev/null; pkill -f 'Jmx.java' 2>/dev/null; }
final_check() {
  local d; d=$(ps -eo command | grep '[C]assandraDaemon'); say "final CassandraDaemon processes: ${d:-none}"
  pgrep -f cassandra-stress >/dev/null && say "WARNING: cassandra-stress still running" || say "no cassandra-stress left"
  pgrep -f 'Jmx.java' >/dev/null && say "WARNING: Jmx poller still running" || say "no Jmx poller left"
  pgrep jcmd >/dev/null && say "WARNING: jcmd still running" || say "no jcmd left"
  run rm -rf "$NB"; say "$(basename $NB) wiped: $([ -e "$NB" ] && echo no || echo yes)"
}
space_read() { nt $1 sjk mx -b $RS -mg -f RepairSessionSpaceInMiB 2>&1 | tr -d '\r' | grep -v '^$' | tail -1; }
leaf_count() { awk '/MerkleTree\$OnHeapLeaf( |$)/{li=$2} END{printf "%d\n", li}' "$1"; }

repair_label() {   # repair_label <label> <depth>
  local lab=$1 d=$2 D=$L/$1; mkdir -p "$D/hist"
  say "== $lab: depth=$d"
  for n in $NODES; do
    jmx $n set $d > "$D/$n-set.txt"; log "jmx $n set $d -> $(tr '\n' ' ' < "$D/$n-set.txt")"
    say "KNOB $lab $n set=$d jmx=[$(tr '\n' ' ' < "$D/$n-set.txt")] RepairSessionSpaceInMiB=$(space_read $n)"
  done
  for n in $NODES; do eval "OFF_$n=$(stat -f %z "$L/$n/debug.log")"; done
  local OFF_OUT=$(stat -f %z "$L/n1/node.out")
  ( cd "$W" && exec java "$T/Jmx.java" 127.0.0.1:7199 poll 1200 > "$D/n1-direct.csv" 2> "$D/n1-direct.err" ) &
  local ppid=$!
  sleep 4
  local flag=$D/sampling; touch "$flag"; local spids=""
  for n in $NODES; do
    ( p=$(getpid $n); while [ -e "$flag" ]; do t=$(ms); jcmd $p GC.class_histogram > "$D/hist/$n-$t.txt" 2>&1; sleep 1; done ) &
    spids="$spids $!"
  done
  sleep 2
  local t0=$(ms)
  log "+ nodetool -h 127.0.0.1 -p 7199 repair --full keyspace1 standard1  (label $lab)"
  tmo 900 "$C1/bin/nodetool" -h 127.0.0.1 -p 7199 repair --full keyspace1 standard1 > "$D/repair.log" 2>&1; local rc=$?
  local t1=$(ms); sleep 3; rm -f "$flag"; wait $spids 2>/dev/null; sleep 2
  kill $ppid 2>/dev/null; wait $ppid 2>/dev/null
  say "REPAIR $lab exit=$rc ms=$(( t1 - t0 )) start_ms=$t0 end_ms=$t1 completed=$(grep -c 'Repair completed successfully' "$D/repair.log")"
  echo "node,ts_ms,leaf_inst" > "$D/samples.csv"
  for n in $NODES; do
    for f in "$D"/hist/$n-[0-9]*.txt; do [ -e "$f" ] || continue; t=$(basename "$f" .txt); t=${t#$n-}
      echo "$n,$t,$(leaf_count "$f")" >> "$D/samples.csv"; done
    off=$(eval echo "\$OFF_$n"); tail -c +$(( off + 1 )) "$L/$n/debug.log" > "$D/$n-debug-segment.log"
    grep 'Allocating direct buffer of size' "$D/$n-debug-segment.log" > "$D/$n-alloc.txt"
    grep 'Prepared AEService trees of size' "$D/$n-debug-segment.log" > "$D/$n-prepared.txt"
    grep 'Created .* merkle trees with merkle trees size' "$D/$n-debug-segment.log" > "$D/$n-created.txt"
    say "ALLOC $lab $n lines=$(wc -l < "$D/$n-alloc.txt" | tr -d ' ') sizes=$(sed -E 's/.*buffer of size ([0-9]+) for.*/\1/' "$D/$n-alloc.txt" | tr '\n' ' ')"
    say "PREPARED $lab $n lines=$(wc -l < "$D/$n-prepared.txt" | tr -d ' ') S=$(sed -E 's/.*trees of size ([0-9]+) for.*/\1/' "$D/$n-prepared.txt" | tr '\n' ' ')"
    say "CREATED $lab $n $(sed -E 's/.*(Created [0-9]+ merkle trees with merkle trees size [0-9]+, [0-9]+ partitions, [0-9]+ bytes).*/\1/' "$D/$n-created.txt" | tr '\n' ';')"
    say "HIST $lab $n $(awk -F, -v n=$n '$1==n{c++; if($3+0>m)m=$3+0; if($3+0>0)w++} END{printf "samples=%d samples_with_leaves=%d Lmax=%d", c, w, m}' "$D/samples.csv")"
  done
  if [ "$BM" = 1 ]; then
    tail -c +$(( OFF_OUT + 1 )) "$L/n1/node.out" | grep '^RSMTD ' > "$D/n1-rsmtd.txt"
    say "EVENT $lab n1 $(python3 -c '
import sys, re, statistics
t0 = int(sys.argv[3]); base = []
for l in open(sys.argv[2]):
    p = l.strip().split(",")
    if len(p) == 2 and p[0].isdigit() and int(p[0]) < t0: base.append(int(p[1]))
med = int(statistics.median(base)) if base else 0
ev = [dict(re.findall(r"(\w+)=(\S+)", l), k=l.split()[1]) for l in open(sys.argv[1])]
a = [e for e in ev if e["k"] == "alloc"]; r = [e for e in ev if e["k"] == "release"]
mt0 = (int(ev[0]["mt"]) - (int(ev[0]["cap"]) if ev[0]["k"] == "alloc" else -int(ev[0]["cap"]))) if ev else 0
first_rel = next((i for i, e in enumerate(ev) if e["k"] == "release"), len(ev))
umax = max((int(e["used"]) for e in ev), default=0)
print("alloc=%d release=%d allocs_before_first_release=%d caps=%s mt_start=%d mt_peak=%d mt_end=%s used_peak=%d baseline_median=%d event_rise=%d" % (
    len(a), len(r), sum(1 for e in ev[:first_rel] if e["k"] == "alloc"), ",".join(sorted(set(e["cap"] for e in ev))) or "-",
    mt0, max((int(e["mt"]) for e in ev), default=0), ev[-1]["mt"] if ev else "-", umax, med, umax - med))
' "$D/n1-rsmtd.txt" "$D/n1-direct.csv" $t0)"
  fi
  say "DIRECT $lab n1 $(python3 -c '
import sys, statistics
t0, t1 = int(sys.argv[2]), int(sys.argv[3]); base, dur = [], []
for l in open(sys.argv[1]):
    p = l.strip().split(",")
    if len(p) != 2 or not p[0].isdigit(): continue
    t, v = int(p[0]), int(p[1])
    if t < t0: base.append(v)
    elif t <= t1 + 3000: dur.append(v)
med = int(statistics.median(base)) if base else 0; pk = max(dur) if dur else 0
print("baseline_samples=%d baseline_median=%d during_samples=%d peak=%d rise=%d" % (len(base), med, len(dur), pk, pk - med))
' "$D/n1-direct.csv" $t0 $t1)"
}

# ------------------------------------------------------------------ pre-checks
say "cluster-run $RUN start $(now) stress_n=$STRESS_N space=${SPACE}MiB harness md5 $(md5 -q "$0" | cut -c1-12) Jmx md5 $(md5 -q "$H/Jmx.java" | cut -c1-12)"
say "clones: $(for n in $NODES; do echo -n "$n=$(git -C $(clone $n) rev-parse --short HEAD) "; done)"
d=$(ps -eo command | grep '[C]assandraDaemon'); [ -n "$d" ] && { say "ABORT: a CassandraDaemon is running"; exit 1; }
for p in 7000 7199 7200 9042; do lsof -nP -iTCP:$p -sTCP:LISTEN >/dev/null 2>&1 && { say "ABORT: port $p busy"; exit 1; }; done
ifconfig lo0 | grep -q "inet 127.0.0.2 " || { say "ABORT: loopback alias 127.0.0.2 missing"; exit 1; }
if [ "$BM" = 1 ]; then
  say "BYTEMAN rules $H/rsmtd.btm md5 $(md5 -q "$H/rsmtd.btm" | cut -c1-12) jar $BMJAR"
  ( cd "$C1" && java -classpath "$BMJAR:build/classes/main:build/lib/jars/*" org.jboss.byteman.check.TestScript "$H/rsmtd.btm" ) > "$L/testscript.txt" 2>&1
  say "TESTSCRIPT $(grep -E 'TestScript:|ERROR|Type checked|WARN' "$L/testscript.txt" | tr '\n' ' ')"
  grep -q 'TestScript: no errors' "$L/testscript.txt" || { say "ABORT: TestScript reports errors"; exit 1; }
fi
say "pre-checks: no CassandraDaemon; ports 7000 7199 7200 9042 free; lo0 has 127.0.0.2; free disk $(df -h $W | tail -1 | awk '{print $4}')"
rm -rf "$NB"
for n in $NODES; do run "$H/make-node-conf.sh" $n repair_session_space=${SPACE}MiB; done
for n in $NODES; do say "YAML $n $(sed -n '/^# ---- stage4 rsmtds lines/,$p' $NB/$n/conf/cassandra.yaml | grep -v '^#' | tr '\n' ';') JMX $(grep '^JMX_PORT=' $NB/$n/conf/cassandra-env.sh)"; done

# ------------------------------------------------------------------ ring (B3e step 1)
for n in $NODES; do start_node $n "$L/$n"; wait_up $n 360 || die "$n did not start"; done
say "RING $(nt n1 status 2>&1 | grep -E '^(UN|DN|UJ)' | awk '{print $1, $2}' | tr '\n' ';')"
if [ "$BM" = 1 ]; then
  say "BM-AGENT n1 javaagent_in_jvm_args=$(grep -m1 -o 'JVM Arguments: .*' $L/n1/system.log | grep -c -o -- '-javaagent:[^ ,]*byteman' ) agent_errors=$(grep -c -E 'TypeException|Rule\.execute called for|org\.jboss\.byteman.*(Exception|Error)' $L/n1/node.out) RSMTD_lines_so_far=$(grep -c '^RSMTD ' $L/n1/node.out)"
fi
for n in $NODES; do say "HEAP $n $(grep -m1 -o 'Heap size: [^,]*, [^ ]*' $L/$n/system.log) $(grep -m1 -o 'JVM Arguments: .*' $L/$n/system.log | grep -o -- '-Xm[sx][0-9]*[GM]' | tr '\n' ' ')"; done

# ------------------------------------------------------------------ load (B3c)
log "+ cassandra-stress write n=$STRESS_N cl=ALL no-warmup -schema 'replication(factor=2)' -rate threads=64 -node 127.0.0.1"
tmo 1800 "$C1/tools/bin/cassandra-stress" write n=$STRESS_N cl=ALL no-warmup -schema "replication(factor=2)" -rate threads=64 -node 127.0.0.1 > "$L/stress.log" 2>&1
say "STRESS exit=$? $(grep -E '^(Total partitions|Total errors|Op rate|Total operation time)' "$L/stress.log" | tr -s ' ' | tr '\n' ';')"
for n in $NODES; do run nt $n flush keyspace1 standard1; done
for n in $NODES; do t0=$(date +%s)
  until nt $n compactionstats 2>/dev/null | grep -Eq '^pending tasks: *0 *$|^pending tasks +0 *$'; do [ $(( $(date +%s) - t0 )) -ge 600 ] && { say "WARNING $n compactions pending after 600 s"; break; }; sleep 5; done
  run nt $n disableautocompaction keyspace1 standard1
  say "SSTABLES $n $(nt $n tablestats keyspace1.standard1 2>&1 | grep -E 'SSTable count|Number of partitions \(estimate\)|Space used \(live\)' | tr -s ' ' | tr '\n' ';')"
done

# ------------------------------------------------------------------ B3e steps 3-5
run nt n1 setlogginglevel org.apache.cassandra.utils.MerkleTree DEBUG
jmx n1 set 9 > "$L/set9-n1.txt"; jmx n2 get > "$L/get-n2.txt"
say "SET9 n1 jmx=[$(tr '\n' ' ' < "$L/set9-n1.txt")] n2 read=[$(tr '\n' ' ' < "$L/get-n2.txt")]"
repair_label d10 10
repair_label d16 16
repair_label d20 20
repair_label d16r 16

# ------------------------------------------------------------------ cleanup (B3e step 6, B4)
run nt n1 setlogginglevel org.apache.cassandra.utils.MerkleTree INFO
stop_all
final_check
say "cluster-run $RUN end $(now)"
