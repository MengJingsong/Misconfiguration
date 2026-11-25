# C8 stage 3-b confirm (2026-11-24): shared functions, sourced by load-life.sh and attack-life.sh.
# Layout: $W/cassandra (cp -a of /mydata/s4/cassandra-base; node data under $W/cassandra/data, logs $W/cassandra/logs),
# $W/conf-auth (shipped conf/ with authenticator: PasswordAuthenticator, authorizer: CassandraAuthorizer),
# $W/harness, $W/template (the attacker-loaded data, see load-life.sh), $W/runs/<run-id>.
# Budget (V7, as the verified BW arm): heap 1,536 MiB, direct 768 MiB (cassandra-env.sh on a 3 GiB node), G1 shipped,
# no container limit, swap 0 for the daemon (systemd-run --user --scope -p MemorySwapMax=0). Default ports, 127.0.0.1.
W=/mydata/s4/3b-C8; H=$W/harness; T=$W/cassandra; CONF=$W/conf-auth; TPL=$W/template
HEAP=1536M; DIRECT=768M
APW=attacker-pw-3b; VPW=victim-pw-3b
log(){ echo "$(date +%FT%T%z) $*"; }
ems(){ date +%s%3N; }
dpid(){ ps -eo pid=,comm=,args= | awk '$2=="java" && /CassandraDaemon/ {print $1}' | head -1; }
CQ(){ timeout ${CQT:-120} $T/bin/cqlsh 127.0.0.1 9042 "$@"; }
NT(){ timeout ${NTT:-120} $T/bin/nodetool -h 127.0.0.1 -p 7199 "$@"; }

precheck(){
  [ -n "$(dpid)" ] && { log "ABORT: a CassandraDaemon runs"; exit 1; }
  for p in 7000 7199 9042; do ss -ltn | grep -q ":$p " && { log "ABORT: port $p busy"; exit 1; }; done
  local free; free=$(df -BG --output=avail /mydata | tail -1 | tr -dc 0-9)
  [ "$free" -ge 15 ] || { log "ABORT: /mydata free ${free}G < 15G"; exit 1; }
  log "precheck ok; /mydata free ${free}G; load $(cut -d' ' -f1-3 /proc/loadavg)"
}

start_node(){   # $1 unit suffix, $2 run dir
  local U=$1 R=$2
  md5sum $T/conf/cassandra.yaml $CONF/cassandra.yaml $CONF/jvm11-server.options $CONF/cassandra-env.sh > $R/conf-md5.txt
  diff $T/conf/cassandra.yaml $CONF/cassandra.yaml > $R/conf-diff.txt
  ( ulimit -n 100000; cd $T; exec env -u HEAP_NEWSIZE CASSANDRA_CONF=$CONF MAX_HEAP_SIZE=$HEAP MAX_DIRECT_MEMORY_SIZE=$DIRECT \
      CASSANDRA_HEAPDUMP_DIR=$R setsid nohup systemd-run --user --scope -p MemorySwapMax=0 --unit=3b-c8-$U -- \
      bin/cassandra -f > $R/stdout.txt 2>&1 < /dev/null ) &
  PID=
  for i in $(seq 1 150); do
    sleep 2
    [ -z "$PID" ] && PID=$(dpid)
    grep -q "Starting listening for CQL clients" $R/stdout.txt 2>/dev/null && break
    if [ -n "$PID" ] && ! kill -0 $PID 2>/dev/null; then log "INVALID: daemon died during start"; exit 1; fi
  done
  [ -z "$PID" ] && PID=$(dpid)
  grep -q "Starting listening for CQL clients" $R/stdout.txt || { log "INVALID: no CQL in 300 s"; [ -n "$PID" ] && kill -9 $PID; exit 1; }
  log "daemon pid $PID up"
  echo $PID > $R/pid
  jcmd $PID VM.command_line > $R/vm-cmdline.txt 2>&1
  jcmd $PID VM.flags > $R/vm-flags.txt 2>&1
  grep -o -E "authenticator=[^;]*;|authorizer=[^;]*;|role_manager=[^;]*;|network_authorizer=[^;]*;|sai_options=[^;]*;|memtable_heap_space=[^;]*;|memtable_allocation_type=[^;]*;|memtable_cleanup_threshold=[^;]*;|key_cache_size=[^;]*;|concurrent_index_builders=[^;]*;|concurrent_compactors=[^;]*;|secondary_indexes_enabled=[^;]*;|sai_sstable_indexes_per_query[a-z_]*=[^;]*;|secondary_indexes_per_table[a-z_]*=[^;]*;|maximum_replication_factor[a-z_]*=[^;]*;|native_transport_max_concurrent_connections[a-z_]*=[^;]*;|native_transport_rate_limiting_enabled=[^;]*;" $T/logs/system.log | sort -u > $R/resolved.txt
  grep -E "Global memtable on-heap threshold|key cache with capacity|Heap size:" $T/logs/system.log | head -5 >> $R/resolved.txt
}

stop_node(){    # $1 unit suffix
  local U=$1 p; p=$(dpid)
  if [ -n "$p" ]; then
    kill $p; for i in $(seq 1 60); do kill -0 $p 2>/dev/null || break; sleep 1; done
    kill -0 $p 2>/dev/null && { log "kill -9 $p"; kill -9 $p; sleep 2; }
  fi
  systemctl --user stop 3b-c8-$U.scope 2>/dev/null
  log "node stopped (daemon: '$(dpid)')"
}

monitors(){     # $1 pid, $2 run dir, $3 stop file. Sampler (C8Sampler, JMX 500 ms), heap_info + RssAnon 3 s, df 5 s.
  local P=$1 R=$2 STOP=$3
  setsid nohup java -cp $H C8Sampler 7199 $R/gauges.csv 500 < /dev/null > $R/sampler.err 2>&1 &
  echo $! > $R/sampler.pid
  setsid nohup bash -c "while kill -0 $P 2>/dev/null && [ ! -e $STOP ]; do echo \"\$(date +%s.%N | cut -c1-14) rssanon_kb=\$(awk '/RssAnon/{print \$2}' /proc/$P/status 2>/dev/null) \$(timeout 10 jcmd $P GC.heap_info 2>/dev/null | tr '\n' '|')\" >> $R/heapinfo.txt; sleep 3; done" < /dev/null > /dev/null 2>&1 &
  echo $! > $R/heapmon.pid
  setsid nohup bash -c "while [ ! -e $STOP ]; do echo \"\$(date +%s) \$(df -BM --output=avail /mydata | tail -1 | tr -dc 0-9)\" >> $R/df.txt; sleep 5; done" < /dev/null > /dev/null 2>&1 &
  echo $! > $R/dfmon.pid
}

stop_monitors(){ # $1 run dir
  local R=$1
  touch $R/STOP; sleep 1
  for f in sampler heapmon dfmon; do [ -f $R/$f.pid ] && kill $(cat $R/$f.pid) 2>/dev/null; done
  pkill -f "C8Sampler 7199 $R/" 2>/dev/null; true
}
