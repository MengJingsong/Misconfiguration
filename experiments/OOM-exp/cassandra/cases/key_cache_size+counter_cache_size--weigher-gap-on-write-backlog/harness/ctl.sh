#!/usr/bin/env bash
# R8 per-instance Cassandra controller, runs ON pc91 (single host; adapted from S2 run-2 ctl.sh, 2026-11-17).
#   V  127.0.0.2 dc c  token -2^63  JMX 7199  CPUs 0-30:2 (NUMA node0)  build $W/run-$BUILD (orig|patched)  dirs $W/inst/V (disk)
#   R  127.0.0.3 dc r  token 0      JMX 7299  CPUs 1-31:2 (NUMA node1)  build $W/run-orig always             data on tmpfs $W/rtmp/R
# Only environment settings change (as S2 ctl.sh gen); every capacity/timeout/cache/hints setting stays at the shipped default.
# Each JVM runs in a user scope with MemorySwapMax=0 (no memory limit; the budget is the Java heap).
#   ctl.sh gen <V|R> <xmx> | start <V|R> | stop <V|R> | pid <V|R>      env BUILD=orig|patched (V only)
set -uo pipefail
W=/mydata/s4/r8-w1; ROOT=$W/inst
declare -A IP=([V]=127.0.0.2 [R]=127.0.0.3) DC=([V]=c [R]=r) JMX=([V]=7199 [R]=7299) CPUS=([V]=0-30:2 [R]=1-31:2)
declare -A TOK=([V]=-9223372036854775808 [R]=0)
log(){ echo "[$(TZ=America/New_York date '+%T')] $*"; }
gen(){
  local n=$1 xmx=$2 b d dd ip; b=$W/run-${BUILD:-orig}; [ "$n" = R ] && b=$W/run-orig
  d=$ROOT/$n; dd=$d; [ "$n" = R ] && dd=$W/rtmp/R; ip=${IP[$n]}
  rm -rf "$d" "$dd"; mkdir -p "$d"/{logs,dumps} "$dd"/{data,commitlog,hints,saved_caches}
  cp -r "$b/conf" "$d/conf"; local y=$d/conf/cassandra.yaml
  sed -i -e "s/^cluster_name: 'Test Cluster'/cluster_name: 'r8ring'/" -e "s/^num_tokens: 16/num_tokens: 1/" \
    -e "s/^listen_address: localhost/listen_address: $ip/" -e "s/^rpc_address: localhost/rpc_address: $ip/" \
    -e "s|seeds: \"127.0.0.1:7000\"|seeds: \"127.0.0.2:7000\"|" \
    -e "s/^endpoint_snitch: SimpleSnitch/endpoint_snitch: GossipingPropertyFileSnitch/" \
    -e "s|^# data_file_directories:|data_file_directories:|" -e "s|^#     - /var/lib/cassandra/data|    - $dd/data|" \
    -e "s|^# commitlog_directory: /var/lib/cassandra/commitlog|commitlog_directory: $dd/commitlog|" \
    -e "s|^# hints_directory: /var/lib/cassandra/hints|hints_directory: $dd/hints|" \
    -e "s|^# saved_caches_directory: /var/lib/cassandra/saved_caches|saved_caches_directory: $dd/saved_caches|" "$y"
  { echo "auto_bootstrap: false"; echo "initial_token: ${TOK[$n]}"; } >> "$y"
  sed -i "s/^JMX_PORT=\"7199\"/JMX_PORT=\"${JMX[$n]}\"/" "$d/conf/cassandra-env.sh"
  printf 'dc=%s\nrack=r1\n' "${DC[$n]}" > "$d/conf/cassandra-rackdc.properties"
  echo "$xmx" > "$d/xmx"; echo "$b" > "$d/build"
  { diff "$b/conf/cassandra.yaml" "$y"; diff "$b/conf/cassandra-env.sh" "$d/conf/cassandra-env.sh"; } > "$d/yaml.diff"
  grep -q "^listen_address: $ip" "$y" || { log "GEN FAIL $n"; return 1; }; log "gen $n xmx=$xmx build=$b"
}
start(){
  local n=$1 d=$ROOT/$1 b u p cg; b=$(cat $d/build); u="r8-$1-$(date +%s)"; echo "$u" > "$d/unit"
  ( ulimit -n 100000; cd "$b"; CASSANDRA_CONF="$d/conf" CASSANDRA_LOG_DIR="$d/logs" CASSANDRA_HEAPDUMP_DIR="$d/dumps" \
    MAX_HEAP_SIZE="$(cat $d/xmx)" HEAP_NEWSIZE="256M" \
    taskset -c "${CPUS[$n]}" systemd-run --user --scope --quiet --unit="$u" -p MemorySwapMax=0 -- "$b/bin/cassandra" -p "$d/cass.pid" >"$d/logs/launch.log" 2>&1 )
  sleep 2; p=$(cat $d/cass.pid 2>/dev/null); cg=/sys/fs/cgroup$(cut -d: -f3 /proc/$p/cgroup 2>/dev/null); echo "$cg" > "$d/cgroup"
  log "launched $n pid=$p unit=$u cpus=$(taskset -cp $p 2>/dev/null | awk '{print $NF}') swap.max=$(cat $cg/memory.swap.max 2>/dev/null) memory.max=$(cat $cg/memory.max 2>/dev/null)"
}
stop(){
  local p u; p=$(cat $ROOT/$1/cass.pid 2>/dev/null); u=$(cat $ROOT/$1/unit 2>/dev/null)
  if [ -n "$p" ]; then kill "$p" 2>/dev/null; for _ in $(seq 30); do kill -0 "$p" 2>/dev/null || break; sleep 1; done; kill -9 "$p" 2>/dev/null; fi
  [ -n "$u" ] && systemctl --user stop "$u.scope" 2>/dev/null
  log "stopped $1 (${p:-none})"
}
case "${1:-}" in gen) shift; gen "$@";; start) start "$2";; stop) stop "$2";; pid) cat $ROOT/$2/cass.pid;; *) exit 2;; esac
