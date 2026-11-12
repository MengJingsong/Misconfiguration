#!/usr/bin/env bash
# Cluster tier (B3) of permissions_cache_max_entries-initcache-entrycount--autonomous, procedure B3e with AM1/AM2/AM5.
# usage: bash cluster-run.sh <run-name> [shakedown]
# Node runs from /mydata/jingsong-cass-s4/o03/src (built tree); node data per arm in <run>/cluster/node (removed after each arm),
# readings per arm in <run>/cluster/<arm>/. Arms: M1000, M5000, M100000 (+ shrink to 1000), off (validity 0, M=100000).
# "shakedown": one arm M100000 with N = 50 and the shrink (instrument check, not a reading).
set -uo pipefail
H=$(cd "$(dirname "$0")" && pwd); B=/mydata/jingsong-cass-s4/o03; C=$B/src; RUN=${1:?run name}; MODE=${2:-}
R=$B/$RUN/cluster; ND=$R/node; mkdir -p "$R"; S=$R/session.txt; : > "$S"
NT="$C/bin/nodetool -p 7499"; L=4000
say() { echo "[$(date -u +%FT%TZ) $(date +%s%3N)] $*" | tee -a "$S"; }
run() { say "+ $*"; "$@" 2>&1 | tee -a "$S"; return ${PIPESTATUS[0]}; }
PID=
stop_node() {
  [ -n "$PID" ] || return 0
  if kill -0 "$PID" 2>/dev/null; then
    say "stopping node pid $PID"; $NT stopdaemon >> "$S" 2>&1
    for i in $(seq 60); do kill -0 "$PID" 2>/dev/null || break; sleep 1; done
    kill -0 "$PID" 2>/dev/null && { say "stopdaemon did not stop it; kill"; kill "$PID"; sleep 10; }
    kill -0 "$PID" 2>/dev/null && { say "kill -9"; kill -9 "$PID"; sleep 2; }
  fi
  say "pid $PID alive after stop: $(kill -0 "$PID" 2>/dev/null && echo yes || echo no); our daemons: $(ps -eo args | grep '[C]assandraDaemon' | grep -c "$C")"
  PID=
}
trap 'stop_node' EXIT
cd "$C" || exit 1
ulimit -n "$(ulimit -Hn)" 2>/dev/null; say "ulimit -n $(ulimit -n)"
[ -f conf/cassandra.yaml.orig ] || cp conf/cassandra.yaml conf/cassandra.yaml.orig
grep -q '^JMX_PORT="7499"' conf/cassandra-env.sh || sed -i 's/^JMX_PORT="7199"/JMX_PORT="7499"/' conf/cassandra-env.sh
say "cluster-run host $(hostname -s) tree $(git describe --tags) java $(java -version 2>&1 | head -1) python $(python3 --version 2>&1)"
say "harness md5 $(cd "$H" && md5sum cluster-run.sh mkconf.py drop_roles.py | awk '{printf "%s=%s ", $2, substr($1,1,12)}')"
say "JMX_PORT line: $(grep '^JMX_PORT=' conf/cassandra-env.sh)"
for p in 7300 7301 7499 9342; do ss -ltn | awk '{print $4}' | grep -q ":$p\$" && { say "port $p busy, abort"; exit 2; }; done
say "ports 7300 7301 7499 9342 free"
if [ "$MODE" = shakedown ]; then N=50; ARMS="M100000"; else N=20000; ARMS="M1000 M5000 M100000 off"; fi

es() { $NT sjk mx -b org.apache.cassandra.auth:type=PermissionsCache -f EstimatedSize -mg 2>&1 | tail -1; }
cq() { "$C/bin/cqlsh" -u cassandra -p cassandra 127.0.0.1 9342 -e "$1" 2>&1; }
readings() {  # $1 = prefix, $2 = arm dir
  local p=$1 A=$2
  say "$p EstimatedSize=$(es)"
  jcmd "$PID" GC.class_histogram > "$A/$p.hist" 2>&1
  jcmd "$PID" GC.run > /dev/null 2>&1; jcmd "$PID" GC.heap_info > "$A/$p.heap" 2>&1
  say "$p hist: $(grep -E 'org\.apache\.cassandra\.auth\.RoleResource( |$)' "$A/$p.hist" | head -1 | tr -s ' ') | [B: $(grep -E ' \[B( |$)' "$A/$p.hist" | head -1 | tr -s ' ') | $(grep '^Total' "$A/$p.hist" | tr -s ' ')"
  say "$p heap_info: $(grep -m1 'garbage-first heap' "$A/$p.heap" | tr -s ' ')"
}
for ARM in $ARMS; do
  A=$R/$ARM; mkdir -p "$A"
  case $ARM in M1000) M=1000; V=3600000;; M5000) M=5000; V=3600000;; M100000) M=100000; V=3600000;; off) M=100000; V=0;; esac
  say "=== arm $ARM M=$M validity=${V}ms N=$N"
  rm -rf "$ND"; mkdir -p "$ND/logs"                                                   # B3e.1
  python3 "$H/mkconf.py" conf/cassandra.yaml.orig conf/cassandra.yaml "$ND" $M $V || exit 3
  diff conf/cassandra.yaml.orig conf/cassandra.yaml > "$A/yaml.diff"; cp conf/cassandra.yaml "$A/cassandra.yaml"
  MAX_HEAP_SIZE=1G HEAP_NEWSIZE=200M CASSANDRA_LOG_DIR="$ND/logs" bin/cassandra -p "$ND/pid" > "$ND/logs/stdout.txt" 2>&1   # B3e.2
  for i in $(seq 30); do [ -s "$ND/pid" ] && break; sleep 1; done
  PID=$(cat "$ND/pid" 2>/dev/null); say "started pid $PID"
  [ -n "$PID" ] || { say "no pid"; exit 4; }
  ok=; for i in $(seq 180); do                                                         # B3e.3 + AM2
    kill -0 "$PID" 2>/dev/null || { say "daemon died during start"; tail -30 "$ND/logs/system.log" >> "$S"; exit 5; }
    [ "$($NT statusbinary 2>/dev/null)" = running ] && { ok=1; break; }; sleep 2; done
  [ -n "$ok" ] || { say "statusbinary never running"; exit 6; }
  ok=; for i in $(seq 60); do cq "LIST ROLES" > "$A/listroles.txt" && grep -q cassandra "$A/listroles.txt" && { ok=1; break; }; sleep 3; done
  [ -n "$ok" ] || { say "LIST ROLES never succeeded"; exit 7; }
  say "node up; LIST ROLES ok"
  say "log: $(grep -h 'initializing PermissionsCache' "$ND/logs/system.log" | sed 's/^.*(Re)/(Re)/' | tr '\n' ' ')"
  readings base "$A"                                                                     # B3e.4
  say "workload start N=$N L=$L"                                                         # B3e.5
  python3 "$H/drop_roles.py" "$C" $N $L > "$A/driver.txt" 2>&1; say "driver exit=$? $(tail -1 "$A/driver.txt")"
  sleep 10                                                                               # B3e.6
  readings after "$A"
  say "after vtable: $(cq 'SELECT count(*) FROM system_views.permissions_cache_keys' | grep -E '^ +[0-9]+' | tr -d ' ')"
  if [ "$ARM" = M100000 ]; then                                                          # B3e.7
    run $NT setauthcacheconfig --cache-name PermissionsCache --max-entries 1000
    sleep 10
    readings shrink "$A"
    say "shrink vtable: $(cq 'SELECT count(*) FROM system_views.permissions_cache_keys' | grep -E '^ +[0-9]+' | tr -d ' ')"
  fi
  stop_node                                                                              # B3e.8
  cp "$ND/logs/system.log" "$A/system.log" 2>/dev/null; cp "$ND"/logs/gc.log* "$A/" 2>/dev/null
  say "$ARM: ERROR lines $(grep -c '^ERROR' "$A/system.log"), OutOfMemoryError $(grep -c 'java.lang.OutOfMemoryError' "$A/system.log")"
  rm -rf "$ND"
done
cp conf/cassandra.yaml.orig conf/cassandra.yaml
say "cluster-run done; our daemons left: $(ps -eo args | grep '[C]assandraDaemon' | grep -c "$C"); drop_roles left: $(ps -eo args | grep -c '[d]rop_roles.py')"
