#!/usr/bin/env bash
# U5 one clean lifetime on ms0617 (victim + client on the same node, loopback).
#   run-arm.sh <label> <A|I|G|LOAD|LOADG> <heap e.g. 2G|4096M|auto> <CK|PK|-> <k1> <k2> <window_s>
# A: stock tree, template-A, shipped config (dirs only). I: tree-I (patched jar) + -Du5.max_in_product=1100000.
# G: stock tree, template-G, PasswordAuthenticator + in_select_cartesian_product_fail_threshold 1000000, client as u5.
# LOAD / LOADG: empty node dir; schema + 1 row each; flush, drain, SIGTERM; saved as template-A / template-G.
# label IC: small requests (4x4, 1x1000, 64x1000 CK; 4x4, 1x1000 PK) + one GC.class_histogram (baseline).
# Launch as ( setsid nohup bash run-arm.sh ... < /dev/null > $ROOT/runs/<label>.driver.log 2>&1 & ); poll the
# driver log for "END".
set -uo pipefail
L=$1 ARM=$2 HEAP=$3 COND=$4 K1=$5 K2=$6 WIN=$7
ROOT=/mydata/s4/u5-w4; H=$ROOT/h; R=$ROOT/runs/$L
log(){ echo "[$(TZ=America/New_York date '+%F %T %Z')] $*"; }
mib(){ local v=$1; case $v in *G) echo $(( ${v%G} * 1024 ));; *M) echo "${v%M}";; esac; }
UCG=/sys/fs/cgroup/user.slice/user-$(id -u).slice/user@$(id -u).service
log "BEGIN $L arm=$ARM heap=$HEAP cond=$COND k1=$K1 k2=$K2 N=$(( K1 * K2 )) window=${WIN}s"
if pgrep -f 'java.*CassandraDaemon' >/dev/null; then log "REFUSE: a CassandraDaemon is already running"; log "END $L REFUSED"; exit 1; fi
HM=$([ "$HEAP" = auto ] && echo 31744 || mib "$HEAP")
FREE=$(( $(df --output=avail -k /mydata | tail -1) / 1024 ))
if [ $FREE -lt $(( HM + 8192 )) ]; then log "WARN free ${FREE} MiB < heap + 8 GiB"; fi
rm -rf "$ROOT/node" "$R"; mkdir -p "$R/logs"
case $ARM in
  LOAD|LOADG) mkdir -p "$ROOT/node"/{data,commitlog,hints,saved_caches,cdc_raw};;
  A|I) cp -a "$ROOT/template-A" "$ROOT/node";;
  G) cp -a "$ROOT/template-G" "$ROOT/node";;
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
if [ "$ARM" = G ] || [ "$ARM" = LOADG ]; then
  sed -i -e 's|^authenticator: AllowAllAuthenticator|authenticator: PasswordAuthenticator|' "$Y"
  [ "$ARM" = G ] && printf '# U5 arm G (diagnostic): the shipped-off guardrail switched on (fail only)\nin_select_cartesian_product_warn_threshold: -1\nin_select_cartesian_product_fail_threshold: 1000000\n' >> "$Y"
fi
diff "$ROOT/conf-pristine/cassandra.yaml" "$Y" > "$R/yaml.diff"
EX="-Xlog:gc*,safepoint:file=$R/gc.log:time,uptime,level,tags:filecount=10,filesize=50m"
[ "$ARM" = I ] && EX="$EX -Du5.max_in_product=1100000"
[ "$HM" -gt 4096 ] && EX="$EX -XX:-HeapDumpOnOutOfMemoryError"
MM=$(( HM + 6144 ))
HENV=$HEAP; [ "$HEAP" = auto ] && HENV=""
cat > "$R/run.meta" <<EOF
label=$L arm=$ARM heap=$HEAP cond=$COND k1=$K1 k2=$K2 N=$(( K1 * K2 )) window_s=$WIN scopeMemoryMax=${MM}M tree=$TREE
start_est=$(TZ=America/New_York date '+%F %T %Z') node=$(hostname -s) arch=$(uname -m)
EOF
sha256sum "$TREE"/build/apache-cassandra-5.0.9-SNAPSHOT.jar >> "$R/run.meta"
cat "$UCG/memory.events" > "$R/parent.memory.events.before" 2>/dev/null
( cd "$R" && CASSANDRA_CONF=$R/conf CASSANDRA_LOG_DIR=$R/logs MAX_HEAP_SIZE=$HENV MAX_DIRECT_MEMORY_SIZE= \
  CASSANDRA_HEAPDUMP_DIR=$R JVM_EXTRA_OPTS="$EX" \
  setsid nohup systemd-run --user --scope --unit="u5-$L-$(date +%s)" -p MemoryMax=${MM}M -p MemorySwapMax=0 \
    "$TREE/bin/cassandra" -f < /dev/null > "$R/stdout.log" 2>&1 & )
P=""; for i in $(seq 1 30); do sleep 1; P=$(pgrep -f "Dcassandra.logdir=$R/logs " | head -1); [ -n "$P" ] && break; done
[ -z "$P" ] && { log "no java pid"; log "END $L INVALID-nopid"; exit 1; }
echo "$P" > "$R/cass.pid"; CGP=$(sed -n 's/^0:://p' /proc/"$P"/cgroup); echo "$CGP" > "$R/cgroup.path"
alive(){ kill -0 "$P" 2>/dev/null; }
log "started pid $P cgroup $CGP"
ok=0; for i in $(seq 1 90); do
  grep -q "Starting listening for CQL clients" "$R/logs/system.log" 2>/dev/null && { ok=1; break; }
  alive || break; sleep 2; done
if [ $ok = 0 ]; then log "not ready in 180 s"; kill -9 "$P" 2>/dev/null; echo "INVALID not-ready" > "$R/outcome"; log "END $L INVALID-notready"; exit 1; fi
log "ready"
ps -o args= -p "$P" | tr ' ' '\n' | grep -E '^-Xm[sx]|MaxDirect|HeapDump|OnOutOfMemory|UseG1|G1HeapRegion|MaxGCPause|u5\.max' | tr '\n' ' ' | tee -a "$R/run.meta"; echo | tee -a "$R/run.meta"
# samplers: jstat 1 s, RssAnon + scope memory.events every 5 s
# amendment 2 (2026-11-18): jstat cannot attach (-XX:+PerfDisableSharedMem in jvm-server.options); JMX sampler C2Sampler
# (U4's, unchanged) at 1 s instead: heap_used, old_used, old_postgc, NTR active/pending/completed, GC times.
( setsid nohup java -Xmx64m -cp "$ROOT/cls" C2Sampler "$R/samples.csv" "$R/sampler.stop" 1000 < /dev/null > "$R/sampler.out" 2>&1 & echo $! > "$R/jstat.pid" )
( setsid nohup bash -c "while kill -0 $P 2>/dev/null; do echo \"\$(date +%s) \$(awk '/RssAnon/{print \$2}' /proc/$P/status 2>/dev/null)\" >> $R/rss.txt; cat /sys/fs/cgroup$CGP/memory.events > $R/memory.events.last 2>/dev/null; sleep 5; done" < /dev/null > /dev/null 2>&1 & echo $! > "$R/rss.pid" )
stopsamplers(){ touch "$R/sampler.stop"; sleep 1; kill "$(cat "$R/jstat.pid")" "$(cat "$R/rss.pid")" 2>/dev/null; }
stopnode(){ if alive; then kill "$P"; for i in $(seq 1 30); do alive || break; sleep 1; done; alive && { kill -9 "$P"; log "SIGKILL after 30 s"; }; fi; }
NT="$TREE/bin/nodetool -h 127.0.0.1"
case $ARM in
  LOAD|LOADG)
    AU=""
    if [ "$ARM" = LOADG ]; then
      for i in $(seq 1 60); do grep -q "Created default superuser role" "$R/logs/system.log" && break; sleep 2; done
      grep -m1 "Created default superuser role" "$R/logs/system.log"
      python3 "$H/u5client.py" mkrole --user cassandra --pw cassandra; AU="--user u5 --pw u5"
    fi
    python3 "$H/u5client.py" ddl $AU
    $NT flush u5; $NT drain; stopnode; stopsamplers
    T=$ROOT/template-A; [ "$ARM" = LOADG ] && T=$ROOT/template-G
    rm -rf "$T"; cp -a "$ROOT/node" "$T"; rm -rf "$T/saved_caches"/*; du -sh "$T"
    echo "LOADED $T" > "$R/outcome"; log "END $L $(cat "$R/outcome")"; exit 0;;
esac
AU=""; [ "$ARM" = G ] && AU="--user u5 --pw u5"
if [ "$L" = IC ]; then
  for spec in "CK 4 4" "CK 1 1000" "CK 64 1000" "PK 4 4" "PK 1 1000"; do set -- $spec
    python3 "$H/u5client.py" run --cond "$1" --k1 "$2" --k2 "$3" --window 60 --out "$R/client.jsonl"; done
  sleep 3; timeout 120 jcmd "$P" GC.class_histogram > "$R/histo-baseline.txt" 2>&1
  head -5 "$R/histo-baseline.txt"; tail -1 "$R/histo-baseline.txt"
  cat "$R/client.jsonl"
  stopnode; stopsamplers; cat "$R/memory.events.last" > "$R/memory.events" 2>/dev/null
  echo "IC done" > "$R/outcome"; log "END $L IC done"; exit 0
fi
sleep 5
( setsid nohup python3 "$H/u5client.py" run --cond "$COND" --k1 "$K1" --k2 "$K2" --window "$WIN" $AU --out "$R/client.jsonl" < /dev/null > "$R/client.err" 2>&1 & echo $! > "$R/client.pid" )
CP=$(cat "$R/client.pid")
for i in $(seq 1 240); do grep -q '"ev": "sent"' "$R/client.jsonl" 2>/dev/null && break; kill -0 "$CP" 2>/dev/null || break; sleep 0.5; done
if ! grep -q '"ev": "sent"' "$R/client.jsonl" 2>/dev/null; then log "client did not send"; cat "$R/client.jsonl" "$R/client.err"; stopnode; stopsamplers; echo "INVALID no-send" > "$R/outcome"; log "END $L INVALID-nosend"; exit 1; fi
TS=$(date +%s); log "sent: $(grep '"ev": "sent"' "$R/client.jsonl")"
( sleep 2; alive && timeout 30 jcmd "$P" Thread.print > "$R/threads-t2.txt" 2>&1; sleep 4; alive && timeout 30 jcmd "$P" Thread.print > "$R/threads-t6.txt" 2>&1 ) &
dead=0; cend=""
while true; do
  sleep 2; el=$(( $(date +%s) - TS ))
  if ! alive; then dead=1; log "VICTIM DEAD at +${el}s"; break; fi
  if ! kill -0 "$CP" 2>/dev/null; then
    [ -z "$cend" ] && { cend=$el; log "client ended at +${el}s: $(tail -1 "$R/client.jsonl")"; }
    [ $(( el - cend )) -ge 15 ] && break
  fi
  [ $el -ge $(( WIN + 20 )) ] && { log "window over"; break; }
  [ $(( el % 20 )) -lt 2 ] && log "+${el}s jmx: $(tail -1 "$R/samples.csv" | cut -c1-120)"
done
wait 2>/dev/null
sleep 2; kill "$CP" 2>/dev/null
cp "$R/memory.events.last" "$R/memory.events" 2>/dev/null
stopnode; stopsamplers
cat "$UCG/memory.events" > "$R/parent.memory.events.after" 2>/dev/null
OOMT=$(grep -h -o -m1 "java.lang.OutOfMemoryError: [A-Za-z ]*" "$R/stdout.log" "$R/logs/system.log" 2>/dev/null | head -1)
CL=$(grep -v '"ev": "prepared"\|"ev": "sent"' "$R/client.jsonl" | tail -1)
if [ $dead = 1 ] && [ -n "$OOMT" ]; then echo "OOM type=\"$OOMT\" at+${el}s client=$CL" > "$R/outcome"
elif [ $dead = 1 ]; then echo "DEAD-noOOM at+${el}s client=$CL" > "$R/outcome"
else echo "SURVIVED client=$CL" > "$R/outcome"; fi
# small evidence copy (pulled to the repo by scp)
S=$R/small; mkdir -p "$S"
cp "$R"/{run.meta,yaml.diff,outcome,client.jsonl,memory.events,parent.memory.events.before,parent.memory.events.after,rss.txt} "$S"/ 2>/dev/null
cp "$R/samples.csv" "$S/samples.csv" 2>/dev/null
grep -h -m3 -B2 -A30 'java\.lang\.OutOfMemoryError' "$R/stdout.log" "$R/logs/system.log" 2>/dev/null | head -150 > "$S/oom-excerpt.txt"
grep -h 'Dumping heap\|Heap dump file\|kill -9\|OnOutOfMemoryError' "$R/stdout.log" >> "$S/oom-excerpt.txt" 2>/dev/null
[ -s "$S/oom-excerpt.txt" ] || rm -f "$S/oom-excerpt.txt"
grep -h -i 'operations were slow\|timed out\|cartesian\|guardrail\|InvalidRequest\|u5: IN' "$R/logs/system.log" "$R/logs/debug.log" 2>/dev/null | cut -c1-600 | head -20 > "$S/monitor-guard-excerpt.txt"
[ -s "$S/monitor-guard-excerpt.txt" ] || rm -f "$S/monitor-guard-excerpt.txt"
for t in t2 t6; do [ -f "$R/threads-$t.txt" ] && grep -A25 '"Native-Transport-Requests' "$R/threads-$t.txt" | grep -B3 -A22 'MultiCBuilder\|SelectStatement\|PartitionKeySingle\|BTree\|CBuilder' | head -60 > "$S/ntr-$t.txt"; done
grep -h 'Pause\|Humongous\|humongous' "$R"/gc.log* 2>/dev/null | grep -v 'safepoint' | tail -40 > "$S/gc-tail.txt"
python3 "$H/gcwin.py" "$R" > "$S/gcwin.txt" 2>&1
ls -la "$R" | grep -i 'hprof\|hs_err' > "$S/hprof.ls" || rm -f "$S/hprof.ls"
log "END $L $(cat "$R/outcome")"
