#!/usr/bin/env bash
# 3-b U17 confirm, one clean lifetime on pc75 (2026-11-24). From the case's run-arm.sh + victim-ctl.sh (start, ready,
# threads, stop, watch rule) with: the auth conf (PasswordAuthenticator + CassandraAuthorizer, nothing else changed),
# superuser setup, a victim role from 127.0.0.2 (60 s before the attack, until 60 s after node death or attack end), the
# attack as role `attacker` (LOGIN, no GRANT) with u17b.py.
#   run3b.sh <label> shake <D_s>                                  (shakedown lifetime: setup with u17.t, auth checks)
#   run3b.sh <label> attack <VEC|HEX> <target> <N> <R> <D> <with_u17: 0|D>
set -uo pipefail
L=$1 MODE=$2
W=/mydata/s4/3b-U17; H=$W/harness; BUILD=$W/tree; R=$W/runs/$L; NODE=$W/node; HEAP=2G
log(){ echo "[$(date '+%F %T %Z')] $*" | tee -a "$R/driver.txt"; }
pid(){ pgrep -f "Dcassandra.logdir=$R/logs " | head -1; }
alive(){ local p; p=$(cat "$R/cass.pid" 2>/dev/null); if [ -n "$p" ] && kill -0 "$p" 2>/dev/null; then echo ALIVE; else echo DEAD; fi; }
threads(){ timeout 20 jcmd "$(pid)" Thread.print 2>/dev/null | awk -v t="$1" -v ts="$(date +%s)" '
    /^"/ { if (n) tot++; if (n && hit) h++; n = ($0 ~ /Native-Transport-Requests/); hit = 0; next }
    n && /org\.antlr\.runtime|Cql_Parser|CqlParser|Vectors\$Literal|ByteBufferUtil\.bytes|CQLFragmentParser/ { hit = 1 }
    END { if (n) tot++; if (n && hit) h++; printf "%s,%s,ntr=%d,in_parse_prepare=%d\n", t, ts, tot+0, h+0 }' >> "$R/threads.csv"; }
stopnode(){
  local p; p=$(pid); touch "$R/sampler.stop"; sleep 2; kill "$(cat "$R/sampler.pid" 2>/dev/null)" 2>/dev/null
  if [ -n "$p" ] && kill -0 "$p" 2>/dev/null; then
    timeout 120 "$BUILD/bin/nodetool" -h 127.0.0.1 drain > "$R/drain.out" 2>&1
    kill "$p"; for i in $(seq 1 60); do kill -0 "$p" 2>/dev/null || break; sleep 1; done; kill -0 "$p" 2>/dev/null && kill -9 "$p"
  fi; log "node stopped"; }

if pgrep -f 'java.*CassandraDaemon' >/dev/null; then echo "REFUSE: a CassandraDaemon runs"; exit 1; fi
rm -rf "$NODE" "$R"; mkdir -p "$R/logs" "$NODE"/{data,commitlog,hints,saved_caches,cdc_raw}
cp -r "$W/conf-auth" "$R/conf"; y=$R/conf/cassandra.yaml
sed -i -e "s|^# data_file_directories:|data_file_directories:|" -e "s|^#     - /var/lib/cassandra/data|    - $NODE/data|" \
  -e "s|^# commitlog_directory: /var/lib/cassandra/commitlog|commitlog_directory: $NODE/commitlog|" \
  -e "s|^# hints_directory: /var/lib/cassandra/hints|hints_directory: $NODE/hints|" \
  -e "s|^# saved_caches_directory: /var/lib/cassandra/saved_caches|saved_caches_directory: $NODE/saved_caches|" \
  -e "s|^# cdc_raw_directory: /var/lib/cassandra/cdc_raw|cdc_raw_directory: $NODE/cdc_raw|" "$y"
diff "$W/conf-pristine/cassandra.yaml" "$y" > "$R/yaml.diff"
XO="-Xlog:gc*=info:file=$R/gc.log:time,uptime,level,tags:filecount=5,filesize=20m"
echo "label=$L mode=$* heap=$HEAP start=$(date -u +%FT%TZ) host=$(hostname -s)" > "$R/run.meta"
sha256sum "$BUILD"/build/apache-cassandra-*.jar >> "$R/run.meta"; md5sum "$W/conf-auth/cassandra.yaml" "$W/conf-pristine/cassandra.yaml" >> "$R/run.meta"
( cd "$R" && CASSANDRA_CONF=$R/conf CASSANDRA_LOG_DIR=$R/logs MAX_HEAP_SIZE=$HEAP CASSANDRA_HEAPDUMP_DIR=$R JVM_EXTRA_OPTS="$XO" \
  setsid nohup systemd-run --user --scope --unit="u17-3b-$L-$(date +%s)" -p MemoryMax=$((2048+15872+8192))M -p MemorySwapMax=0 \
  "$BUILD/bin/cassandra" -f < /dev/null > "$R/stdout.log" 2>&1 & )
p=""; for i in $(seq 1 20); do sleep 1; p=$(pid); [ -n "$p" ] && break; done
[ -z "$p" ] && { log "no java pid"; exit 1; }; echo "$p" > "$R/cass.pid"; log "started pid $p"
ok=0; for i in $(seq 1 90); do grep -q "Starting listening for CQL clients" "$R/logs/system.log" 2>/dev/null && { ok=1; break; }; sleep 2; done
[ $ok = 1 ] || { log "not ready"; stopnode; echo "INVALID not-ready" > "$R/outcome"; exit 1; }
ps -o args= -p "$p" | tr ' ' '\n' | grep -E '^-Xm[sx]|MaxDirect|HeapDump|OnOutOfMemory|UseG1|G1HeapRegion' | tr '\n' ' ' >> "$R/run.meta"; echo >> "$R/run.meta"
grep -o -E "(authenticator|authorizer|role_manager|network_authorizer|native_transport_max_request_data_in_flight[a-z_]*|native_transport_max_frame_size|native_transport_max_threads|native_transport_rate_limiting_enabled|native_transport_max_concurrent_connections[a-z_]*|vector_dimensions_[a-z_]*)=[^;]*" "$R/logs/system.log" | head -20 > "$R/resolved.txt"
( setsid nohup java -Xmx64m -cp "$W/cls" C2Sampler "$R/samples.csv" "$R/sampler.stop" 1000 > "$R/sampler.out" 2>&1 < /dev/null & echo $! > "$R/sampler.pid" )
log "ready"
if [ "$MODE" = shake ]; then
  python3 -I "$H/u17b.py" --setup --with-u17 6500000 > "$R/auth-setup.txt" 2>&1; tail -1 "$R/auth-setup.txt"
  python3 -I "$H/u17b.py" --shake --d "$3" > "$R/auth-shake.txt" 2>&1; cat "$R/auth-shake.txt"
  stopnode; echo "SHAKE done" > "$R/outcome"; rm -rf "$NODE"; exit 0
fi
PAY=$3 TGT=$4 N=$5 RR=$6 D=$7 WU=$8
python3 -I "$H/u17b.py" --setup --with-u17 "$WU" > "$R/auth-setup.txt" 2>&1; tail -1 "$R/auth-setup.txt"
grep -q "setup ok" "$R/auth-setup.txt" || { log "setup failed"; stopnode; echo "INVALID setup" > "$R/outcome"; exit 1; }
( setsid nohup python3 -I "$H/u17b.py" --victim --out "$R" --stopfile "$R/victim.stop" --rate 20 > "$R/victim.out" 2>&1 < /dev/null & echo $! > "$R/victim.pid" )
log "victim started pid $(cat "$R/victim.pid"); 60 s baseline"; sleep 60
threads base
( cd "$R" && setsid nohup python3 -I "$H/u17b.py" --payload "$PAY" --target "$TGT" --d "$D" --n "$N" --rounds "$RR" --out "$R" > client.out 2> client.err < /dev/null & echo $! > "$R/client.pid" )
CP=$(cat "$R/client.pid"); t0=$(date +%s); echo "$t0" > "$R/attack.start"; log "attack started client pid $CP ($PAY $TGT N=$N R=$RR D=$D)"
dead=0; lastthr=-10
while true; do
  el=$(( $(date +%s) - t0 ))
  if [ "$(alive)" != ALIVE ]; then log "NODE DEAD at +${el}s"; dead=1; break; fi
  if ! kill -0 "$CP" 2>/dev/null; then grep -q "down=true" "$R/client.csv" 2>/dev/null || break; fi
  [ $el -ge 600 ] && { log "600 s stop"; break; }
  [ $(( el - lastthr )) -ge 10 ] && { threads "t+$el"; lastthr=$el; }
  sleep 2
done
echo "$(date +%s) dead=$dead el=$el" > "$R/attack.end"
for i in $(seq 1 30); do kill -0 "$CP" 2>/dev/null || break; sleep 1; done; kill "$CP" 2>/dev/null; sleep 1; kill -9 "$CP" 2>/dev/null
if [ $dead = 1 ]; then
  # the shipped kill -9 runs after the dump; victim keeps measuring until 60 s after the process is gone
  for i in $(seq 1 300); do [ -n "$(pid)" ] || break; sleep 1; done; log "process gone; victim 60 s more"; sleep 60
else
  log "alive; victim 60 s after the attack end"; sleep 60
fi
touch "$R/victim.stop"; sleep 7; kill "$(cat "$R/victim.pid")" 2>/dev/null
stopnode
oomtype=$(grep -h -o -m1 "java.lang.OutOfMemoryError: [A-Za-z ]*" "$R/logs/system.log" "$R/stdout.log" 2>/dev/null | head -1)
codes=$(grep -E '^[0-9]+,[0-9]+,' "$R/client.csv" 2>/dev/null | cut -d, -f6,7,8 | cut -c1-90 | sort | uniq -c | tr '\n' ' ')
if [ $dead = 1 ] && [ -n "$oomtype" ]; then echo "OOM type=\"$oomtype\" at+${el}s codes=[$codes]" > "$R/outcome"
elif [ $dead = 1 ]; then echo "DEAD-noOOM at+${el}s codes=[$codes]" > "$R/outcome"
else echo "SURVIVED wall=${el}s codes=[$codes]" > "$R/outcome"; fi
cat "$R/outcome"
python3 "$H/gcwin.py" "$R" > "$R/gcwin.txt" 2>&1
grep -h -m3 -B2 -A30 'java\.lang\.OutOfMemoryError' "$R/stdout.log" 2>/dev/null | head -80 > "$R/stdout-oom.txt"
grep -E 'GCInspector|WARN|ERROR' "$R/logs/system.log" | cut -c1-300 | head -40 > "$R/system-warn.txt"
HP=$(ls "$R"/*.hprof 2>/dev/null | head -1)
if [ -n "$HP" ]; then
  { ls -l "$HP"; sha256sum "$HP" | cut -c1-16; } > "$R/dump.txt"
  timeout 900 nice -n 19 python3 -I "$H/hprof_oome_thread.py" "$HP" 40 > "$R/oome-thread.txt" 2>&1; echo "oome-thread rc=$?" >> "$R/dump.txt"
  timeout 900 nice -n 19 python3 -I "$H/hprofstacks.py" "$HP" Cql_Parser > "$R/stacks-parser.txt" 2>&1; echo "stacks rc=$?" >> "$R/dump.txt"
  timeout 1200 nice -n 19 python3 -I "$H/hprof-histo.py" "$HP" --len-range 1 1 --top 30 > "$R/histo.txt" 2>&1; echo "histo rc=$?" >> "$R/dump.txt"
  rm -f "$HP"; echo "deleted after analysis $(date '+%F %T %Z')" >> "$R/dump.txt"
fi
rm -rf "$NODE"
log "END $L $(cat "$R/outcome")"
