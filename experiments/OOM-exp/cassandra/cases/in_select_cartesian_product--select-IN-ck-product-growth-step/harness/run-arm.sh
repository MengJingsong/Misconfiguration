#!/usr/bin/env bash
# R14 one clean lifetime on pc91 (victim + client on the same node, loopback). Adapted from U5 run-arm.sh with the
# changes listed in the R14 design §2 "Changes to run-arm.sh" (1-5):
#   (1) ROOT /mydata/s4/r14; arm I -Du5.max_in_product=2000000; HeapDumpOnOutOfMemoryError kept on at every heap;
#   (2) stdout.ts watcher (wall-clock prefix on every stdout.log line); outcome reports thrown_at, dump_done_at,
#       jvm_exit_at separately; (3) lifetime end: no throw -> client exit + 15 s or W after t_send; after a throw ->
#       wait for JVM exit up to G after the throw, then SIGTERM, 30 s, SIGKILL; (4) one jcmd Thread.print at the first
#       "Pause Full (G1 Humongous Allocation)" (threads-hum.txt); (5) excerpts ntr-hum.txt, stdout.ts excerpt.
#   run-arm.sh <label> <A|I|LOAD> <heap e.g. 2G|8192M> <CK|PK|-> <k1> <k2> <W_s> <G_s>
# Launch detached; poll runs/<label>.driver.log for "END".
set -uo pipefail
L=$1 ARM=$2 HEAP=$3 COND=$4 K1=$5 K2=$6 WIN=$7 GRACE=${8:-600}
ROOT=/mydata/s4/r14; H=$ROOT/h; R=$ROOT/runs/$L
log(){ echo "[$(TZ=America/New_York date '+%F %T %Z')] $*"; }
mib(){ local v=$1; case $v in *G) echo $(( ${v%G} * 1024 ));; *M) echo "${v%M}";; esac; }
UCG=/sys/fs/cgroup/user.slice/user-$(id -u).slice/user@$(id -u).service
log "BEGIN $L arm=$ARM heap=$HEAP cond=$COND k1=$K1 k2=$K2 N=$(( K1 * K2 )) W=${WIN}s G=${GRACE}s"
if pgrep -f 'java.*CassandraDaemon' >/dev/null; then log "REFUSE: a CassandraDaemon is already running"; log "END $L REFUSED"; exit 1; fi
HM=$(mib "$HEAP")
FREE=$(( $(df --output=avail -k /mydata | tail -1) / 1024 ))
log "free /mydata ${FREE} MiB"
if [ $FREE -lt $(( HM + 20480 )) ]; then log "REFUSE: free ${FREE} MiB < heap + 20 GiB"; log "END $L REFUSED-disk"; exit 1; fi
rm -rf "$ROOT/node" "$R"; mkdir -p "$R/logs"
case $ARM in
  LOAD) mkdir -p "$ROOT/node"/{data,commitlog,hints,saved_caches,cdc_raw};;
  A|I) cp -a "$ROOT/template-A" "$ROOT/node";;
  *) log "bad arm"; exit 1;;
esac
TREE=$ROOT/tree; [ "$ARM" = I ] && TREE=$ROOT/tree-I
cp -r "$ROOT/conf-pristine" "$R/conf"; Y=$R/conf/cassandra.yaml
sed -i \
  -e "s|^# data_file_directories:|data_file_directories:|" \
  -e "s|^#     - /var/lib/cassandra/data|    - $ROOT/node/data|" \
  -e "s|^# commitlog_directory: /var/lib/cassandra/commitlog|commitlog_directory: $ROOT/node/commitlog|" \
  -e "s|^# hints_directory: /var/lib/cassandra/hints|hints_directory: $ROOT/node/hints|" \
  -e "s|^# saved_caches_directory: /var/lib/cassandra/saved_caches|saved_caches_directory: $ROOT/node/saved_caches|" \
  -e "s|^# cdc_raw_directory: /var/lib/cassandra/cdc_raw|cdc_raw_directory: $ROOT/node/cdc_raw|" "$Y"
diff "$ROOT/conf-pristine/cassandra.yaml" "$Y" > "$R/yaml.diff"
EX="-Xlog:gc*,safepoint:file=$R/gc.log:time,uptime,level,tags:filecount=10,filesize=50m"
[ "$ARM" = I ] && EX="$EX -Du5.max_in_product=2000000"
MM=$(( HM + 6144 ))
cat > "$R/run.meta" <<EOF
label=$L arm=$ARM heap=$HEAP cond=$COND k1=$K1 k2=$K2 N=$(( K1 * K2 )) W_s=$WIN G_s=$GRACE scopeMemoryMax=${MM}M tree=$TREE
start_est=$(TZ=America/New_York date '+%F %T %Z') node=$(hostname -s) arch=$(uname -m)
EOF
sha256sum "$TREE"/build/apache-cassandra-5.0.9-SNAPSHOT.jar >> "$R/run.meta"
cat "$UCG/memory.events" > "$R/parent.memory.events.before" 2>/dev/null
: > "$R/stdout.log"
( cd "$R" && CASSANDRA_CONF=$R/conf CASSANDRA_LOG_DIR=$R/logs MAX_HEAP_SIZE=$HEAP MAX_DIRECT_MEMORY_SIZE= \
  CASSANDRA_HEAPDUMP_DIR=$R JVM_EXTRA_OPTS="$EX" \
  setsid nohup systemd-run --user --scope --unit="r14-$L-$(date +%s)" -p MemoryMax=${MM}M -p MemorySwapMax=0 \
    "$TREE/bin/cassandra" -f < /dev/null > "$R/stdout.log" 2>&1 & )
# (2) wall-clock prefix for stdout.log lines
( setsid nohup bash -c "tail -n +1 -F '$R/stdout.log' 2>/dev/null | python3 -u '$H/ts.py' '$R/stdout.ts'" < /dev/null > /dev/null 2>&1 & echo $! > "$R/ts.pid" )
P=""; for i in $(seq 1 30); do sleep 1; P=$(pgrep -f "Dcassandra.logdir=$R/logs " | head -1); [ -n "$P" ] && break; done
stopts(){ kill -- -"$(cat "$R/ts.pid")" 2>/dev/null; }
[ -z "$P" ] && { log "no java pid"; stopts; log "END $L INVALID-nopid"; exit 1; }
echo "$P" > "$R/cass.pid"; CGP=$(sed -n 's/^0:://p' /proc/"$P"/cgroup); echo "$CGP" > "$R/cgroup.path"
alive(){ kill -0 "$P" 2>/dev/null; }
log "started pid $P cgroup $CGP"
ok=0; for i in $(seq 1 90); do
  grep -q "Starting listening for CQL clients" "$R/logs/system.log" 2>/dev/null && { ok=1; break; }
  alive || break; sleep 2; done
if [ $ok = 0 ]; then log "not ready in 180 s"; kill -9 "$P" 2>/dev/null; stopts; echo "INVALID not-ready" > "$R/outcome"; log "END $L INVALID-notready"; exit 1; fi
log "ready"
ps -o args= -p "$P" | tr ' ' '\n' | grep -E '^-Xm[sx]|MaxDirect|HeapDump|OnOutOfMemory|UseG1|G1HeapRegion|MaxGCPause|u5\.max|AlwaysPreTouch' | tr '\n' ' ' | tee -a "$R/run.meta"; echo | tee -a "$R/run.meta"
( setsid nohup java -Xmx64m -cp "$ROOT/cls" C2Sampler "$R/samples.csv" "$R/sampler.stop" 1000 < /dev/null > "$R/sampler.out" 2>&1 & echo $! > "$R/jstat.pid" )
( setsid nohup bash -c "while kill -0 $P 2>/dev/null; do echo \"\$(date +%s) \$(awk '/RssAnon/{print \$2}' /proc/$P/status 2>/dev/null)\" >> $R/rss.txt; cat /sys/fs/cgroup$CGP/memory.events > $R/memory.events.last 2>/dev/null; sleep 5; done" < /dev/null > /dev/null 2>&1 & echo $! > "$R/rss.pid" )
# (4) one Thread.print at the first humongous-allocation full GC
( setsid nohup bash -c "while kill -0 $P 2>/dev/null; do if grep -q -m1 'Pause Full (G1 Humongous Allocation)' $R/gc.log 2>/dev/null; then date +%s.%N > $R/threads-hum.at; timeout 120 jcmd $P Thread.print > $R/threads-hum.txt 2>&1; date +%s.%N >> $R/threads-hum.at; break; fi; sleep 1; done" < /dev/null > /dev/null 2>&1 & echo $! > "$R/hum.pid" )
stopsamplers(){ touch "$R/sampler.stop"; sleep 1; kill "$(cat "$R/jstat.pid")" "$(cat "$R/rss.pid")" 2>/dev/null; kill -- -"$(cat "$R/hum.pid")" 2>/dev/null; stopts; }
stopnode(){ if alive; then kill "$P"; for i in $(seq 1 30); do alive || break; sleep 1; done; alive && { kill -9 "$P"; log "SIGKILL after 30 s"; }; fi; }
NT="$TREE/bin/nodetool -h 127.0.0.1"
if [ "$ARM" = LOAD ]; then
  python3 "$H/u5client.py" ddl
  $NT flush u5; $NT drain; stopnode; stopsamplers
  T=$ROOT/template-A; rm -rf "$T"; cp -a "$ROOT/node" "$T"; rm -rf "$T/saved_caches"/*; du -sh "$T"
  echo "LOADED $T" > "$R/outcome"; log "END $L $(cat "$R/outcome")"; exit 0
fi
if [ "$L" = IC ]; then
  for spec in "CK 4 4" "CK 1 1000" "CK 160 1000" "PK 4 4" "PK 1 1000"; do set -- $spec
    python3 "$H/u5client.py" run --cond "$1" --k1 "$2" --k2 "$3" --window 60 --out "$R/client.jsonl"; done
  # body-size check for T, T18, T28, M and PK (no connection; the client's own encoders, 16-byte prepared id as v4)
  python3 - "$H" <<'EOF' | tee "$R/bodysize.txt"
import sys, struct; sys.path.insert(0, sys.argv[1]); import u5client as u
sid = b'\0' * 16
for lab, cond, k1, k2 in (('T', 'CK', 160, 1600000), ('T18', 'CK', 240, 1800000), ('T28', 'CK', 300, 1800000),
                          ('M', 'CK', 1, 1600159), ('PK', 'PK', 16, 500000), ('M-PK', 'PK', 1, 500015)):
    vals = ([u.int_value(0)] if cond == 'CK' else []) + [u.list_value(k1), u.list_value(k2)]
    body = (struct.pack('>H', len(sid)) + sid + struct.pack('>HB', 1, 0x07) + struct.pack('>H', len(vals)) + b''.join(vals) + struct.pack('>i', 5000))
    print(f'{lab} {cond} {k1} x {k2} = {k1*k2:,} body_bytes={len(body):,} < 16,777,216: {len(body) < u.MAXFRAME}')
EOF
  sleep 3; timeout 120 jcmd "$P" GC.class_histogram > "$R/histo-baseline.txt" 2>&1
  head -5 "$R/histo-baseline.txt"; tail -1 "$R/histo-baseline.txt"
  cat "$R/client.jsonl"
  stopnode; stopsamplers; cat "$R/memory.events.last" > "$R/memory.events" 2>/dev/null
  S=$R/small; mkdir -p "$S"; cp "$R"/{run.meta,yaml.diff,client.jsonl,memory.events,bodysize.txt} "$S"/ 2>/dev/null
  head -40 "$R/histo-baseline.txt" > "$S/histo-baseline-head.txt"; tail -1 "$R/histo-baseline.txt" >> "$S/histo-baseline-head.txt"
  echo "IC done" > "$R/outcome"; cp "$R/outcome" "$S/"; log "END $L IC done"; exit 0
fi
sleep 5
( setsid nohup python3 "$H/u5client.py" run --cond "$COND" --k1 "$K1" --k2 "$K2" --window "$WIN" --out "$R/client.jsonl" < /dev/null > "$R/client.err" 2>&1 & echo $! > "$R/client.pid" )
CP=$(cat "$R/client.pid")
for i in $(seq 1 240); do grep -q '"ev": "sent"' "$R/client.jsonl" 2>/dev/null && break; kill -0 "$CP" 2>/dev/null || break; sleep 0.5; done
if ! grep -q '"ev": "sent"' "$R/client.jsonl" 2>/dev/null; then log "client did not send"; cat "$R/client.jsonl" "$R/client.err"; stopnode; stopsamplers; echo "INVALID no-send" > "$R/outcome"; log "END $L INVALID-nosend"; exit 1; fi
TSMS=$(python3 -c "import json,sys; print([json.loads(l) for l in open(sys.argv[1]) if '\"sent\"' in l][0]['t_send_ms'])" "$R/client.jsonl")
TS=$(( TSMS / 1000 )); echo "$TSMS" > "$R/t_send_ms"
log "sent: $(grep '"ev": "sent"' "$R/client.jsonl")"
( sleep 2; alive && timeout 30 jcmd "$P" Thread.print > "$R/threads-t2.txt" 2>&1; sleep 4; alive && timeout 30 jcmd "$P" Thread.print > "$R/threads-t6.txt" 2>&1 ) &
dead=0; cend=""; thrown=""; dumpd=""; why=""
# fix 2026-11-20 10:48 EST (after CAL-X-8G): fixed-string match; the regex matched a startup CompileCommand line (Ljava/lang/OutOfMemoryError)
ooml(){ grep -F -m1 'java.lang.OutOfMemoryError: ' "$R/stdout.ts" 2>/dev/null; }
while true; do
  sleep 2; el=$(( $(date +%s) - TS ))
  if [ -z "$thrown" ] && ooml >/dev/null; then thrown=$el; log "THROWN seen at +${el}s: $(ooml | cut -c1-200)"; fi
  if [ -n "$thrown" ] && [ -z "$dumpd" ] && grep -q 'Heap dump file created' "$R/stdout.ts" 2>/dev/null; then dumpd=$el; log "dump done seen at +${el}s"; fi
  if ! alive; then dead=1; log "VICTIM DEAD at +${el}s"; break; fi
  if [ -n "$thrown" ]; then
    [ $(( el - thrown )) -ge "$GRACE" ] && { why="grace over after throw"; log "$why"; break; }
  else
    if ! kill -0 "$CP" 2>/dev/null; then
      [ -z "$cend" ] && { cend=$el; log "client ended at +${el}s: $(tail -1 "$R/client.jsonl")"; }
      [ $(( el - cend )) -ge 15 ] && { why="client end + 15 s"; break; }
    fi
    [ $el -ge "$WIN" ] && { why="window W over (no throw)"; log "$why"; break; }
  fi
  [ $(( el % 20 )) -lt 2 ] && log "+${el}s jmx: $(tail -1 "$R/samples.csv" | cut -c1-120)"
done
wait 2>/dev/null
sleep 2; kill "$CP" 2>/dev/null
cp "$R/memory.events.last" "$R/memory.events" 2>/dev/null
stopnode; JEXIT=$(date +%s.%N); stopsamplers
cat "$UCG/memory.events" > "$R/parent.memory.events.after" 2>/dev/null
OOMT=$(grep -h -o -m1 "java.lang.OutOfMemoryError: [A-Za-z ]*" "$R/stdout.log" "$R/logs/system.log" 2>/dev/null | head -1)
CL=$(grep -v '"ev": "prepared"\|"ev": "sent"' "$R/client.jsonl" | tail -1)
# exact times relative to t_send from stdout.ts (wall clock of the line), s with 1 decimal
REL=$(python3 - "$R" "$TSMS" "$dead" "$JEXIT" <<'EOF'
import sys
R, ts, dead, jexit = sys.argv[1], int(sys.argv[2]) / 1000, sys.argv[3] == '1', float(sys.argv[4])
def first(pat):
    try:
        for l in open(R + '/stdout.ts', errors='replace'):
            if pat in l: return '%+.1fs' % (float(l.split(' ', 1)[0]) - ts)
    except FileNotFoundError: pass
    return '-'
print('thrown_at=%s dump_done_at=%s kill9_at=%s' % (first('java.lang.OutOfMemoryError'), first('Heap dump file created'), first('Executing /bin/sh -c "kill -9')))
EOF
)
EXITTXT=$([ $dead = 1 ] && echo "jvm_exit_at=+${el}s(poll)" || echo "jvm_exit=stopped-by-harness(${why})")
if [ -n "$OOMT" ]; then echo "OOM type=\"$OOMT\" $REL $EXITTXT client=$CL" > "$R/outcome"
elif [ $dead = 1 ]; then echo "DEAD-noOOM $REL $EXITTXT client=$CL" > "$R/outcome"
else echo "SURVIVED $REL end=\"$why\" client=$CL" > "$R/outcome"; fi
S=$R/small; mkdir -p "$S"
cp "$R"/{run.meta,yaml.diff,outcome,client.jsonl,memory.events,parent.memory.events.before,parent.memory.events.after,rss.txt,t_send_ms,threads-hum.at} "$S"/ 2>/dev/null
cp "$R/samples.csv" "$S/samples.csv" 2>/dev/null
grep -h -m3 -B2 -A30 'java\.lang\.OutOfMemoryError' "$R/stdout.log" "$R/logs/system.log" 2>/dev/null | head -150 > "$S/oom-excerpt.txt"
grep -h 'Dumping heap\|Heap dump file\|kill -9\|OnOutOfMemoryError' "$R/stdout.log" >> "$S/oom-excerpt.txt" 2>/dev/null
[ -s "$S/oom-excerpt.txt" ] || rm -f "$S/oom-excerpt.txt"
grep -h 'OutOfMemoryError\|Dumping heap\|Heap dump file\|kill -9\|ERROR\|WARN' "$R/stdout.ts" 2>/dev/null | cut -c1-400 | head -60 > "$S/stdout-ts-excerpt.txt"
[ -s "$S/stdout-ts-excerpt.txt" ] || rm -f "$S/stdout-ts-excerpt.txt"
grep -h -i 'operations were slow\|timed out\|cartesian\|guardrail\|InvalidRequest\|u5: IN' "$R/logs/system.log" "$R/logs/debug.log" 2>/dev/null | cut -c1-600 | head -20 > "$S/monitor-guard-excerpt.txt"
[ -s "$S/monitor-guard-excerpt.txt" ] || rm -f "$S/monitor-guard-excerpt.txt"
for t in t2 t6 hum; do [ -f "$R/threads-$t.txt" ] && grep -A40 '"Native-Transport-Requests' "$R/threads-$t.txt" | grep -B3 -A30 'MultiCBuilder\|SelectStatement\|PartitionKeySingle\|BTree\|CBuilder' | head -80 > "$S/ntr-$t.txt"; done
grep -h 'Pause\|Humongous\|humongous' "$R"/gc.log* 2>/dev/null | grep -v 'safepoint' | tail -40 > "$S/gc-tail.txt"
python3 "$H/gcwin.py" "$R" > "$S/gcwin.txt" 2>&1
ls -la "$R" | grep -i 'hprof\|hs_err' > "$S/hprof.ls" || rm -f "$S/hprof.ls"
log "END $L $(cat "$R/outcome")"
