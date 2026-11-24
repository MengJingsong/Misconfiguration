#!/usr/bin/env bash
# U12 3-b confirm controller (runs ON ms0617; copied to /mydata/s4/3b-U12/h/). Adapted from the stage-2 ctl.sh:
# paths -> /mydata/s4/3b-U12, scope unit prefix 3bu12-, TZ=UTC for the node JVM (log timestamps as on ms0611),
# and the three security settings of the 3-b threat model (authenticator, authorizer, role_manager). Utah m400, aarch64, one local node (127.0.0.1).
# Instance dir /mydata/s4/3b-U12/inst/node (fixed paths so golden data sets restore into the same directories).
# Environment keys changed in cassandra.yaml: data/commitlog/hints/saved_caches/cdc directories, num_tokens 1;
# security (3-b): authenticator PasswordAuthenticator, authorizer CassandraAuthorizer, role_manager CassandraRoleManager (already the default).
# Every capacity setting stays at the shipped default.
#   ctl.sh gen                                     create inst/node/conf from the unpatched build's conf (once)
#   ctl.sh start <build-dir> <heap MiB> <direct MiB> <run-dir> [extra JVM opts]   (logs + heap dumps go to <run-dir>)
#   ctl.sh stop | pid | wipe-data
#   ctl.sh nt <build-dir> <nodetool args...>
set -uo pipefail
U=/mydata/s4/3b-U12; D=$U/inst/node
log(){ echo "[$(TZ=America/New_York date '+%F %T')] $*"; }
case "${1:-}" in
  gen)
    rm -rf "$D"; mkdir -p "$D"/{data,commitlog,hints,saved_caches,cdc_raw}
    cp -r $U/cassandra/conf "$D/conf"; y=$D/conf/cassandra.yaml
    sed -i -e "s/^num_tokens: 16/num_tokens: 1/" \
      -e "s|^# data_file_directories:|data_file_directories:|" -e "s|^#     - /var/lib/cassandra/data|    - $D/data|" \
      -e "s|^# commitlog_directory: /var/lib/cassandra/commitlog|commitlog_directory: $D/commitlog|" \
      -e "s|^# hints_directory: /var/lib/cassandra/hints|hints_directory: $D/hints|" \
      -e "s|^# saved_caches_directory: /var/lib/cassandra/saved_caches|saved_caches_directory: $D/saved_caches|" \
      -e "s|^# cdc_raw_directory: /var/lib/cassandra/cdc_raw|cdc_raw_directory: $D/cdc_raw|" \
      -e "s|^authenticator: AllowAllAuthenticator|authenticator: PasswordAuthenticator|" \
      -e "s|^authorizer: AllowAllAuthorizer|authorizer: CassandraAuthorizer|" \
      -e "s|^role_manager: .*|role_manager: CassandraRoleManager|" "$y"
    diff <(grep -vE '^\s*#|^\s*$' "$U/cassandra/conf/cassandra.yaml") <(grep -vE '^\s*#|^\s*$' "$y") > "$D/yaml.diff"
    cat "$D/yaml.diff"; log "gen ok" ;;
  start)
    B=$2; HEAP=$3; DIRECT=$4; R=$5; shift 5; EXTRA="${*:-}"
    mkdir -p "$R/logs" "$R/dumps"; un="3bu12-$(date +%s)"
    cat > "$R/launch.sh" <<EOS
#!/usr/bin/env bash
ulimit -n 100000
cd "$D"
export TZ=UTC CASSANDRA_CONF="$D/conf" CASSANDRA_LOG_DIR="$R/logs" CASSANDRA_HEAPDUMP_DIR="$R/dumps"
export MAX_HEAP_SIZE="${HEAP}M" HEAP_NEWSIZE="512M" MAX_DIRECT_MEMORY_SIZE="${DIRECT}M"
export JVM_EXTRA_OPTS="-XX:ErrorFile=$R/logs/hs_err_pid%p.log $EXTRA"
exec "$B/bin/cassandra" -f -p "$D/cass.pid"
EOS
    chmod +x "$R/launch.sh"; echo "$un" > "$D/unit"; rm -f "$D/cass.pid"
    ( setsid nohup systemd-run --user --scope --quiet --unit="$un" -p MemorySwapMax=0 "$R/launch.sh" > "$R/logs/launch.log" 2>&1 < /dev/null & )
    # the java process carries -Dcassandra.logdir=<run>/logs from its first instant (bin/cassandra execs java; the pidfile is written late)
    p=""; for _ in $(seq 100); do sleep 0.2; p=$(pgrep -f "^\S*java .*-Dcassandra.logdir=$R/logs" | head -1); [ -n "$p" ] && break; done
    echo "$p" > "$R/node.pid"; echo "$p" > "$D/node.pid"
    cg=/sys/fs/cgroup$(cut -d: -f3 /proc/$p/cgroup 2>/dev/null)
    tr '\0' '\n' < /proc/$p/cmdline > "$R/cmdline.txt" 2>/dev/null
    log "started pid=$p build=$B heap=${HEAP}M direct=${DIRECT}M extra=[$EXTRA] unit=$un cg=$cg swap.max=$(cat $cg/memory.swap.max 2>/dev/null) memory.max=$(cat $cg/memory.max 2>/dev/null)" ;;
  pid) cat "$D/cass.pid" 2>/dev/null ;;
  stop)
    p=$(cat "$D/node.pid" 2>/dev/null); un=$(cat "$D/unit" 2>/dev/null)
    # only a live java whose command line carries this case's log dir (guards against a reused PID)
    if [ -n "$p" ] && kill -0 "$p" 2>/dev/null && tr '\0' ' ' < /proc/$p/cmdline 2>/dev/null | grep -q -- "-Dcassandra.logdir=$U/"; then kill "$p"; for _ in $(seq 60); do kill -0 "$p" 2>/dev/null || break; sleep 1; done; kill -9 "$p" 2>/dev/null; fi
    [ -n "$un" ] && systemctl --user stop "$un.scope" 2>/dev/null
    log "stopped ${p:-none}" ;;
  wipe-data) rm -rf "$D"/{data,commitlog,hints,saved_caches,cdc_raw}; mkdir -p "$D"/{data,commitlog,hints,saved_caches,cdc_raw} ;;
  nt) B=$2; shift 2; "$B/bin/nodetool" -h 127.0.0.1 "$@" ;;
  *) echo "usage" >&2; exit 2 ;;
esac
