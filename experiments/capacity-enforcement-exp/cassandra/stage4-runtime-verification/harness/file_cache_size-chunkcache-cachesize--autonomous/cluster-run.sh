#!/usr/bin/env bash
# Cluster tier (B3, amendments A4-A6) of file_cache_size-chunkcache-cachesize--autonomous.
# usage: bash cluster-run.sh <run-name>       runs load, then C0 C1 C2 C3 on one node at 127.0.0.1 (ports 7300/7301/9342, JMX 7499).
# Tree: $W/src (copy-source.sh, ant build-test; never run ant there while this runs). Conf: $W/<run>/conf (copy of the tree's conf).
# Data: $W/cdata, logs: $W/clogs, output: $W/<run>/cluster/. Every command is logged to cmd.log. Stops at the first failed check.
set -uo pipefail
H=$(cd "$(dirname "$0")" && pwd); W=${W:-/mydata/jingsong-cass-s4/o07}; C=$W/src; RUN=${1:?run name}
O=$W/$RUN/cluster; CF=$W/$RUN/conf; mkdir -p "$O"; CMD=$O/cmd.log; S=$O/summary.txt
export CASSANDRA_CONF=$CF CASSANDRA_LOG_DIR=$W/clogs MAX_HEAP_SIZE=2G HEAP_NEWSIZE=400M MAX_DIRECT_MEMORY_SIZE=2G   # A9
NT="$C/bin/nodetool -h 127.0.0.1 -p 7499"
PIDF=$W/cass.pid; NODEPID=""
say() { echo "$(date -u +%FT%TZ) $*" | tee -a "$S"; }
run() { echo "+ $(date -u +%FT%TZ) $*" >> "$CMD"; "$@" >> "$CMD" 2>&1; local rc=$?; echo "  rc=$rc" >> "$CMD"; return $rc; }
die() { say "STOP: $*"; stop_node; exit 1; }
mypid_alive() { [ -n "$NODEPID" ] && [ -d /proc/$NODEPID ] && tr '\0' ' ' < /proc/$NODEPID/cmdline | grep -q "CassandraDaemon" && [ "$(readlink /proc/$NODEPID/cwd)" != "" ]; }

stop_node() {
  [ -n "$NODEPID" ] || return 0
  if mypid_alive; then
    say "stopping node pid $NODEPID"; run kill "$NODEPID"
    for i in $(seq 1 120); do mypid_alive || break; sleep 1; done
    if mypid_alive; then say "pid $NODEPID still alive after 120 s, SIGKILL"; run kill -9 "$NODEPID"; sleep 2; fi
  fi
  mypid_alive && die "node pid $NODEPID did not exit"
  say "node pid $NODEPID gone"; NODEPID=""
}

set_yaml() { # $1 enabled(true|false) $2 size MiB
  python3 - "$CF/cassandra.yaml" "$1" "$2" <<'PY'
import re, sys
p, en, sz = sys.argv[1:4]
s = open(p).read()
s = re.sub(r'(?m)^#?[ \t]*file_cache_enabled:.*$', 'file_cache_enabled: ' + en, s, count=1)
s = re.sub(r'(?m)^#?[ \t]*file_cache_size:.*$', 'file_cache_size: %sMiB' % sz, s, count=1)
open(p, 'w').write(s)
PY
  echo "+ yaml: $(grep -E '^(file_cache_enabled|file_cache_size):' $CF/cassandra.yaml | tr '\n' ' ')" >> "$CMD"
}

start_node() { # $1 label
  rm -f "$PIDF"
  echo "+ $(date -u +%FT%TZ) bin/cassandra -p $PIDF" >> "$CMD"
  ( cd "$C" && ulimit -n 100000 && setsid nohup bin/cassandra -p "$PIDF" < /dev/null >> "$O/cassandra-stdout-$1.log" 2>&1 & )
  for i in $(seq 1 30); do [ -s "$PIDF" ] && break; sleep 1; done
  NODEPID=$(cat "$PIDF" 2>/dev/null); [ -n "$NODEPID" ] || die "no pid file"
  say "$1 node pid $NODEPID cwd $(readlink /proc/$NODEPID/cwd) heap opts: $(tr '\0' ' ' < /proc/$NODEPID/cmdline | grep -oE -- '-Xm[sx][^ ]*|-XX:NativeMemoryTracking=[^ ]*|-XX:MaxDirectMemorySize=[^ ]*' | tr '\n' ' ')"
  for i in $(seq 1 180); do
    mypid_alive || die "$1 daemon died during start"
    if $NT status 2>/dev/null | grep -q '^UN  127.0.0.1' && [ "$($NT statusbinary 2>/dev/null)" = running ]; then break; fi
    sleep 2
  done
  [ "$($NT statusbinary 2>/dev/null)" = running ] || die "$1 node not up"
  say "$1 node UN and binary running"
  tr '\0' ' ' < /proc/$NODEPID/cmdline | grep -q -- '-XX:MaxDirectMemorySize=2G' || die "$1 MaxDirectMemorySize is not 2G (A9)"
  say "$1 $(grep 'Global buffer pool limit' $W/clogs/system.log | tail -1 | sed 's/.*Global/Global/')"
}

snap() { # $1 label $2 tag
  local f=$O/$1-snap.txt
  { echo "### $2 $(date -u +%FT%TZ) $(date +%s%3N)"
    timeout 60 $C/bin/cqlsh 127.0.0.1 9342 -e "SELECT name,capacity_bytes,size_bytes,entry_count FROM system_views.caches" 2>&1
    echo "rss_kb $(ps -o rss= -p $NODEPID) $(grep -E 'RssAnon' /proc/$NODEPID/status | tr -s ' ')"
    jcmd $NODEPID VM.native_memory summary 2>&1 | grep -E 'Total:|^- +Other|^- +Java Heap'
  } >> "$f"
  java -cp "$O/bin" JmxSampler 7499 "$O/$1-jmx-snap.csv" 0 /nonexistent once >> "$CMD" 2>&1
  sed -i "\$s/\$/,$2/" "$O/$1-jmx-snap.csv"
}

sampler_start() { # $1 label
  rm -f "$O/$1.stop"
  ( setsid nohup java -cp "$O/bin" JmxSampler 7499 "$O/$1-jmx.csv" 10000 "$O/$1.stop" < /dev/null >> "$O/$1-sampler.log" 2>&1 & )
  ( setsid nohup bash -c "while [ ! -e '$O/$1.stop' ]; do echo \"\$(date +%s%3N),\$(ps -o rss= -p $NODEPID | tr -d ' '),\$(awk '/RssAnon/{print \$2}' /proc/$NODEPID/status),\$(jcmd $NODEPID VM.native_memory summary 2>/dev/null | awk '/^- +Other/' | grep -oE 'committed=[0-9]+KB' | head -1)\"; sleep 10; done" < /dev/null >> "$O/$1-proc.csv" 2>&1 & )
}
sampler_stop() { touch "$O/$1.stop"; sleep 12; }

stress() { # $1 label $2 log-suffix, rest: stress args
  local l=$1 sfx=$2; shift 2
  local lf=$O/$l-stress-$sfx.log
  echo "+ $(date -u +%FT%TZ) tools/bin/cassandra-stress $* -node 127.0.0.1 -port native=9342 jmx=7499" >> "$CMD"
  ( cd "$C" && tools/bin/cassandra-stress "$@" -node 127.0.0.1 -port native=9342 jmx=7499 < /dev/null > "$lf" 2>&1 ); local rc=$?
  say "$l stress $sfx rc=$rc $(grep -E '^(Op rate|Total errors|Total partitions|Total operation time)' "$lf" | tr -s ' ' | tr '\n' ';')"
  [ $rc -eq 0 ] || die "$l stress $sfx failed"
}

# ---- setup
: > "$S"; say "cluster-run $RUN host $(hostname -s) tree $C $(git -C $C describe --tags) java $(java -version 2>&1 | head -1)"
say "harness md5 $(cd "$H" && md5sum JmxSampler.java cluster-run.sh cluster-analyze.py | awk '{printf "%s=%s ", $2, substr($1,1,12)}')"
say "df: $(df -h $W | tail -1)"; say "free: $(free -g | awk '/Mem:/{print "avail " $7 " GiB"}')"
for p in 7300 7301 7499 9342; do ss -ltnH | awk '{print $4}' | grep -q ":$p\$" && die "port $p in use"; done
[ -e "$W/cdata" ] && die "$W/cdata exists (stale data)"
mkdir -p "$O/bin" "$W/clogs"; run javac -d "$O/bin" "$H/JmxSampler.java" || die "javac"
rm -rf "$CF"; cp -r "$C/conf" "$CF"
python3 - "$CF/cassandra.yaml" "$W/cdata" <<'PY'
import re, sys
p, d = sys.argv[1:3]
s = open(p).read()
def sub(pat, rep):
    global s
    n = len(re.findall(pat, s, flags=re.M))
    assert n >= 1, pat
    s = re.sub(pat, rep, s, count=1, flags=re.M)
sub(r'^cluster_name:.*$', "cluster_name: 'o07fc'")
sub(r'^listen_address:.*$', 'listen_address: 127.0.0.1')
sub(r'^rpc_address:.*$', 'rpc_address: 127.0.0.1')
sub(r'- seeds:.*$', '- seeds: "127.0.0.1:7300"')
sub(r'^storage_port:.*$', 'storage_port: 7300')
sub(r'^ssl_storage_port:.*$', 'ssl_storage_port: 7301')
sub(r'^native_transport_port:.*$', 'native_transport_port: 9342')
sub(r'^#?[ \t]*data_file_directories:[ \t]*$\n#?[ \t]*-.*$', 'data_file_directories:\n    - %s/data' % d)
sub(r'^#?[ \t]*commitlog_directory:.*$', 'commitlog_directory: %s/commitlog' % d)
sub(r'^#?[ \t]*hints_directory:.*$', 'hints_directory: %s/hints' % d)
sub(r'^#?[ \t]*saved_caches_directory:.*$', 'saved_caches_directory: %s/saved_caches' % d)
sub(r'^#?[ \t]*cdc_raw_directory:.*$', 'cdc_raw_directory: %s/cdc' % d)
open(p, 'w').write(s)
PY
[ $? -eq 0 ] || die "yaml edit"
sed -i 's/^JMX_PORT="7199"/JMX_PORT="7499"/' "$CF/cassandra-env.sh"; grep -q '^JMX_PORT="7499"' "$CF/cassandra-env.sh" || die "JMX_PORT edit"
echo "-XX:NativeMemoryTracking=summary" >> "$CF/jvm11-server.options"
echo "+ conf diff:" >> "$CMD"; diff -r "$C/conf" "$CF" >> "$CMD" 2>&1
grep -nE '^(disk_access_mode|row_cache_size|key_cache_size|listen_address|rpc_address|storage_port|native_transport_port|commitlog_directory|hints_directory)' "$CF/cassandra.yaml" >> "$CMD"

# ---- load (C0 config)
set_yaml false 128
start_node load
stress load write write n=500000 -col 'n=FIXED(1)' 'size=FIXED(1024)' -schema 'compression=LZ4Compressor' -rate threads=16   # A8
run $NT flush keyspace1 || die flush
run $NT compact keyspace1 || die compact
run $NT tablestats keyspace1.standard1
say "load: $(grep -E 'SSTable count|Space used \(live\)|Compression|Number of partitions' $CMD | tail -5 | tr -s ' ' | tr '\n' ';')"
say "data dir: $(du -sh $W/cdata/data/keyspace1 | cut -f1); files: $(ls $W/cdata/data/keyspace1/standard1-*/ | tr '\n' ' ')"
grep -q 'SSTable Compression Ratio: -1' "$CMD" && die "table is uncompressed (A8)"
ls $W/cdata/data/keyspace1/standard1-*/*CompressionInfo.db >/dev/null 2>&1 || die "no CompressionInfo.db (A8)"
stop_node

# ---- runs
for spec in "C0 false 128" "C1 true 128" "C2 true 256" "C3 true 1024"; do
  set -- $spec; L=$1
  if [ "$L" = C3 ]; then
    av=$(free -g | awk '/Mem:/{print $7}'); say "C3 free avail ${av} GiB"; [ "$av" -ge 4 ] || die "less than 4 GiB available"
  fi
  set_yaml $2 $3
  start_node $L
  snap $L baseline
  sampler_start $L
  stress $L read1 read n=2000000 -col 'n=FIXED(1)' 'size=FIXED(1024)' -pop 'dist=UNIFORM(1..500000)' -rate threads=32
  snap $L after-read1
  stress $L read2 read n=2000000 -col 'n=FIXED(1)' 'size=FIXED(1024)' -pop 'dist=UNIFORM(1..500000)' -rate threads=32
  snap $L after-read2
  sleep 60
  snap $L final
  sampler_stop $L
  stop_node
done
say "processes left from this run: $(ps -eo pid,args | grep -E '[J]mxSampler|[c]assandra-stress' | grep -c "$W")  daemon in $C: $(for p in $(pgrep -f CassandraDaemon); do [ "$(readlink /proc/$p/cwd 2>/dev/null)" = "$C" ] && echo $p; done | wc -l)"
python3 "$H/cluster-analyze.py" "$O" | tee -a "$S"
say "done"
