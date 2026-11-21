#!/usr/bin/env bash
# R11 per-node Cassandra controller (runs ON the node; from S2 run-2 harness-run2/ctl.sh, 2026-11-20). Utah m400, aarch64.
#   V   ms0611 10.10.1.4  coordinator for every client write + replica (seed)   build /mydata/r11/run-$BUILD (orig|patched)
#   R1  ms0625 10.10.1.1  replica                                                build /mydata/r11/run-orig always
#   R2  ms0617 10.10.1.5  replica (shares its node with the client)              build /mydata/r11/run-orig always
# Only environment settings change (as S2 ctl.sh gen); every capacity/timeout/cache/hints setting stays at the shipped
# default. Each JVM runs in a user scope with MemorySwapMax=0 (no memory limit; the budget is the Java heap).
#   ctl.sh gen <role> <xmx> | restore <role> <xmx> | start <role> | stop <role> | pid <role> | cg <role>
#   env BUILD=orig|patched (V only)
set -uo pipefail
W=/mydata/r11; ROOT=$W/inst
declare -A IP=([V]=10.10.1.4 [R1]=10.10.1.1 [R2]=10.10.1.5)
declare -A TOK=([V]=-9223372036854775808 [R1]=-3074457345618258603 [R2]=3074457345618258602)
log(){ echo "[$(TZ=America/New_York date '+%T')] $*"; }
gen(){
  local n=$1 xmx=$2 b d ip; b=$W/run-${BUILD:-orig}; [ "$n" = V ] || b=$W/run-orig
  d=$ROOT/$n; ip=${IP[$n]}
  rm -rf "$d"; mkdir -p "$d"/{logs,dumps,data,commitlog,hints,saved_caches}
  cp -r "$b/conf" "$d/conf"; local y=$d/conf/cassandra.yaml
  sed -i -e "s/^cluster_name: 'Test Cluster'/cluster_name: 'r11ring'/" -e "s/^num_tokens: 16/num_tokens: 1/" \
    -e "s/^listen_address: localhost/listen_address: $ip/" -e "s/^rpc_address: localhost/rpc_address: $ip/" \
    -e "s|seeds: \"127.0.0.1:7000\"|seeds: \"10.10.1.4:7000\"|" \
    -e "s/^endpoint_snitch: SimpleSnitch/endpoint_snitch: GossipingPropertyFileSnitch/" \
    -e "s|^# data_file_directories:|data_file_directories:|" -e "s|^#     - /var/lib/cassandra/data|    - $d/data|" \
    -e "s|^# commitlog_directory: /var/lib/cassandra/commitlog|commitlog_directory: $d/commitlog|" \
    -e "s|^# hints_directory: /var/lib/cassandra/hints|hints_directory: $d/hints|" \
    -e "s|^# saved_caches_directory: /var/lib/cassandra/saved_caches|saved_caches_directory: $d/saved_caches|" "$y"
  { echo "auto_bootstrap: false"; echo "initial_token: ${TOK[$n]}"; } >> "$y"
  printf 'dc=c\nrack=r1\n' > "$d/conf/cassandra-rackdc.properties"
  echo "$xmx" > "$d/xmx"; echo "$b" > "$d/build"; diff "$b/conf/cassandra.yaml" "$y" > "$d/yaml.diff"
  grep -q "^listen_address: $ip" "$y" || { log "GEN FAIL $n"; return 1; }; log "gen $n xmx=$xmx build=$b"
}
restore(){
  local n=$1; gen "$@" || return 1
  local g=$W/golden-$n.tgz; [ -f "$g" ] || { log "NO GOLDEN $g"; return 1; }
  tar -xzf "$g" -C "$ROOT/$n" && rm -f "$ROOT/$n"/saved_caches/*
  log "restored $n from $g ($(du -sh $ROOT/$n/data | cut -f1) data, saved_caches: $(ls $ROOT/$n/saved_caches | wc -l) files)"
}
start(){
  local n=$1 d=$ROOT/$1 b u p cg; b=$(cat $d/build); u="r11-$1-$(date +%s)"; echo "$u" > "$d/unit"
  ( ulimit -n 100000; cd "$b"; CASSANDRA_CONF="$d/conf" CASSANDRA_LOG_DIR="$d/logs" CASSANDRA_HEAPDUMP_DIR="$d/dumps" \
    MAX_HEAP_SIZE="$(cat $d/xmx)" HEAP_NEWSIZE="256M" \
    systemd-run --user --scope --quiet --unit="$u" -p MemorySwapMax=0 -- "$b/bin/cassandra" -p "$d/cass.pid" >"$d/logs/launch.log" 2>&1 )
  sleep 2; p=$(cat $d/cass.pid 2>/dev/null); cg=/sys/fs/cgroup$(cut -d: -f3 /proc/$p/cgroup 2>/dev/null); echo "$cg" > "$d/cgroup"
  log "launched $n pid=$p unit=$u build=$b swap.max=$(cat $cg/memory.swap.max 2>/dev/null) memory.max=$(cat $cg/memory.max 2>/dev/null)"
}
stop(){
  local p u; p=$(cat $ROOT/$1/cass.pid 2>/dev/null); u=$(cat $ROOT/$1/unit 2>/dev/null)
  if [ -n "$p" ]; then kill "$p" 2>/dev/null; for _ in $(seq 30); do kill -0 "$p" 2>/dev/null || break; sleep 1; done; kill -9 "$p" 2>/dev/null; fi
  [ -n "$u" ] && systemctl --user stop "$u.scope" 2>/dev/null
  log "stopped $1 (${p:-none})"
}
case "${1:-}" in gen) shift; gen "$@";; restore) shift; restore "$@";; start) start "$2";; stop) stop "$2";;
  pid) cat $ROOT/$2/cass.pid;; cg) cat $ROOT/$2/cgroup;; *) exit 2;; esac
