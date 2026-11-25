# U3 3-b confirm harness library (sourced), 2026-11-24, ms0625 (second session: + evwatch.py event timestamps). From stage 2's lib.sh: R/unit names changed; write_yaml
# also switches authenticator/authorizer (the only non-directory change); CQ = cqlsh helper.
R=/mydata/s4/3b-U3; C=$R/cassandra; H=$R/harness
export CASSANDRA_HOME=$C
DPAT='org.apache.cassandra.service.Cassandra''Daemon'
log()  { echo "[$(date '+%F %T') $(date +%s%3N)] $*" | tee -a "$L/commands.log"; }
note() { echo "$*" >> "$L/summary-raw.txt"; log "$*"; }
drv()  { echo "$(date +%FT%T%z) $*" >> "$L/driver.txt"; log "$*"; }
die()  { note "STOP: $*"; exit 1; }
NT() { (cd "$C" && timeout 30 bin/nodetool "$@"); }
CQ() { timeout 120 "$C/bin/cqlsh" 127.0.0.1 9042 "$@"; }
my_daemons() { for p in $(pgrep -f "$DPAT"); do [ "$(readlink /proc/$p/cwd 2>/dev/null)" = "$C" ] && echo $p; done; }

preflight() {
  [ -n "$(pgrep -f "$DPAT")" ] && die "a Cassandra daemon is already running: $(pgrep -af "$DPAT" | cut -c1-200)"
  for p in 7000 7199 9042; do ss -ltn | grep -q ":$p " && die "port $p busy"; done
  local f; f=$(df -BG --output=avail /mydata | tail -1 | tr -dc 0-9); [ "$f" -ge 10 ] || die "/mydata free ${f}G < 10G"
}

write_yaml() {
  local N=$1; local Y=$N/conf/cassandra.yaml
  sed -e 's/^authenticator: AllowAllAuthenticator$/authenticator: PasswordAuthenticator/' \
      -e 's/^authorizer: AllowAllAuthorizer$/authorizer: CassandraAuthorizer/' "$C/conf/cassandra.yaml" > "$Y"
  { echo; echo "# U3 overrides (directories only)"
    echo "data_file_directories:"; echo "    - $N/data"
    echo "commitlog_directory: $N/commitlog"; echo "hints_directory: $N/hints"
    echo "saved_caches_directory: $N/saved_caches"; echo "cdc_raw_directory: $N/cdc_raw"; } >> "$Y"
  diff "$C/conf/cassandra.yaml" "$Y" > "$L/yaml-diff.txt"
}

start_node() {
  local N=$1 HEAP=$2 GUARD=$3 UNIT=$4
  log "+ systemd-run --user --scope -p MemoryMax=$GUARD -p MemorySwapMax=0 --unit=$UNIT env MAX_HEAP_SIZE=$HEAP bin/cassandra -f"
  ( ulimit -n 100000; cd "$C" && exec systemd-run --user --scope -p MemoryMax=$GUARD -p MemorySwapMax=0 --unit="$UNIT" \
      env MAX_HEAP_SIZE=$HEAP CASSANDRA_CONF="$N/conf" CASSANDRA_LOG_DIR="$L" CASSANDRA_HEAPDUMP_DIR="$L" \
      JVM_EXTRA_OPTS="-Xlog:gc:file=$L/gc-pauses.log:time,uptime:filecount=0" bin/cassandra -f ) > "$L/node.out" 2>&1 < /dev/null &
  NPID=$!
  local ok=0
  for i in $(seq 1 180); do
    kill -0 "$NPID" 2>/dev/null || die "node died during start"
    if NT status 2>/dev/null | grep -q '^UN ' && [ "$(NT statusbinary 2>/dev/null)" = running ]; then ok=1; break; fi
    sleep 2
  done
  [ $ok = 1 ] || die "node not UN/running within 360 s"
  DPID=$(my_daemons | head -1)
  CG=/sys/fs/cgroup$(cut -d: -f3 /proc/$DPID/cgroup)
  note "NODE up daemon_pid=$DPID cgroup=$CG memory.max=$(cat $CG/memory.max) swap.max=$(cat $CG/memory.swap.max)"
  note "JVMARGS $(grep -m1 -o 'JVM Arguments: .*' "$L/system.log" | grep -o -E -- '-Xm[sx][0-9]+[GMgm]|-Xmn[0-9]+[GMgm]|-XX:MaxDirectMemorySize=[0-9]+[GMgm]?|-XX:\+UseG1GC|-XX:G1HeapRegionSize=[0-9a-z]+|-XX:\+HeapDumpOnOutOfMemoryError' | tr '\n' ' ')"
  note "RESOLVED $(grep -o -E 'authenticator=[^;]*;|authorizer=[^;]*;|role_manager=[^;]*;|network_authorizer=[^;]*;|read_thresholds_enabled=[^;]*;|items_per_collection_[a-z_]*=[^;]*;|collection_size_[a-z_]*=[^;]*;|concurrent_reads=[^;]*;|native_transport_max_threads=[^;]*;|read_request_timeout=[^;]*;|roles_validity=[^;]*;|permissions_validity=[^;]*;|native_transport_rate_limiting_enabled=[^;]*;|native_transport_max_concurrent_connections=[^;]*;' "$L/system.log" | sort -u | tr '\n' ' ')"
  ( while kill -0 "$DPID" 2>/dev/null; do echo "$(date +%s%3N) $(cat $CG/memory.current 2>/dev/null) $(grep oom_kill $CG/memory.events 2>/dev/null | awk '{print $2}') $(grep RssAnon /proc/$DPID/status 2>/dev/null | awk '{print $2}')"; sleep 1; done
    echo "$(date +%s%3N) end $(grep oom_kill $CG/memory.events 2>/dev/null | awk '{print $2}')" ) > "$L/memory.txt" 2>/dev/null &
  MSPID=$!
  python3 -I "$H/evwatch.py" "$L/node.out" "$L/node-events.txt" "$DPID" < /dev/null > /dev/null 2>&1 &
  EVPID=$!
}

wait_su() { for i in $(seq 1 60); do CQ -u cassandra -p cassandra -e "LIST ROLES" > /dev/null 2>&1 && return 0; sleep 2; done; die "superuser login not ready"; }

start_tpstats() {
  ( while kill -0 "$DPID" 2>/dev/null; do echo "=== $(date +%s%3N)"; NT tpstats 2>&1 | grep -E '^(ReadStage|Native-Transport-Requests|MutationStage|READ_REQ) '; sleep 5; done ) > "$L/tpstats.txt" 2>&1 &
  TPPID=$!
}

stop_node() {
  [ -z "${NPID:-}" ] && return
  if kill -0 "$NPID" 2>/dev/null && [ -n "$DPID" ] && kill -0 "$DPID" 2>/dev/null; then
    log "stopping node (stopdaemon)"
    NT stopdaemon >> "$L/commands.log" 2>&1 &
    for i in $(seq 1 90); do kill -0 "$DPID" 2>/dev/null || break; sleep 1; done
    if kill -0 "$DPID" 2>/dev/null; then log "alive after 90 s: kill $DPID"; kill "$DPID"; sleep 10; kill -9 "$DPID" 2>/dev/null; fi
  fi
  for i in $(seq 1 20); do kill -0 "$NPID" 2>/dev/null || break; sleep 1; done
  local left; left=$(my_daemons)
  [ -n "$left" ] && { log "WARNING: daemon still running ($left): kill -9"; kill -9 $left; sleep 2; }
  [ -n "$(my_daemons)" ] && log "WARNING: daemon still running" || log "no Cassandra daemon left"
  kill "${MSPID:-}" "${TPPID:-}" 2>/dev/null
  NPID=""
}
