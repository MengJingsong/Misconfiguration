# U3 harness library (sourced). Node: pc99. R = working tree.
R=/mydata/s4/u3-w1; C=$R/cassandra; H=$R/harness
export CASSANDRA_HOME=$C
DPAT='org.apache.cassandra.service.Cassandra''Daemon'
log()  { echo "[$(date '+%F %T') $(date +%s%3N)] $*" | tee -a "$L/commands.log"; }
note() { echo "$*" >> "$L/summary-raw.txt"; log "$*"; }
die()  { note "STOP: $*"; exit 1; }
NT() { (cd "$C" && timeout 30 bin/nodetool "$@"); }
my_daemons() { for p in $(pgrep -f "$DPAT"); do [ "$(readlink /proc/$p/cwd 2>/dev/null)" = "$C" ] && echo $p; done; }

preflight() {
  [ -n "$(pgrep -f "$DPAT")" ] && die "a Cassandra daemon is already running: $(pgrep -af "$DPAT" | cut -c1-200)"
  for p in 7000 7199 9042; do ss -ltn | grep -q ":$p " && die "port $p busy"; done
}

# write_yaml <node dir> [extra yaml file]
write_yaml() {
  local N=$1 X=${2:-}; local Y=$N/conf/cassandra.yaml
  cp "$C/conf/cassandra.yaml" "$Y"
  { echo; echo "# U3 overrides (directories only)"
    echo "data_file_directories:"; echo "    - $N/data"
    echo "commitlog_directory: $N/commitlog"; echo "hints_directory: $N/hints"
    echo "saved_caches_directory: $N/saved_caches"; echo "cdc_raw_directory: $N/cdc_raw"
    if [ -n "$X" ]; then echo "# U3 arm extra ($X)"; cat "$X"; fi; } >> "$Y"
  diff "$C/conf/cassandra.yaml" "$Y" > "$L/yaml-diff.txt"
}

# start_node <node dir> <heap|unset> <guard> <unit>
start_node() {
  local N=$1 HEAP=$2 GUARD=$3 UNIT=$4
  local HEAPENV=""; [ "$HEAP" != unset ] && HEAPENV="MAX_HEAP_SIZE=$HEAP"
  log "+ systemd-run --user --scope -p MemoryMax=$GUARD -p MemorySwapMax=0 --unit=$UNIT env $HEAPENV bin/cassandra -f"
  ( cd "$C" && exec systemd-run --user --scope -p MemoryMax=$GUARD -p MemorySwapMax=0 --unit="$UNIT" \
      env $HEAPENV CASSANDRA_CONF="$N/conf" CASSANDRA_LOG_DIR="$L" CASSANDRA_HEAPDUMP_DIR="$L" \
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
  ( while kill -0 "$DPID" 2>/dev/null; do echo "$(date +%s%3N) $(cat $CG/memory.current 2>/dev/null) $(grep oom_kill $CG/memory.events 2>/dev/null | awk '{print $2}') $(grep RssAnon /proc/$DPID/status 2>/dev/null | awk '{print $2}')"; sleep 1; done
    echo "$(date +%s%3N) end $(grep oom_kill $CG/memory.events 2>/dev/null | awk '{print $2}')" ) > "$L/memory.txt" 2>/dev/null &
  MSPID=$!
}

start_tpstats() {
  ( while kill -0 "$DPID" 2>/dev/null; do echo "=== $(date +%s%3N)"; NT tpstats 2>&1 | grep -E '^(ReadStage|Native-Transport-Requests|READ_REQ|RANGE_SLICE) '; sleep 5; done ) > "$L/tpstats.txt" 2>&1 &
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
