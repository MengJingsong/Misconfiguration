#!/usr/bin/env bash
# B16 3-b confirm (ms0611, 2026-11-23): stage-2 victim-ctl.sh with ROOT=/mydata/s4/3b-B16 and the arms AUTH / LOAD-AUTH
# (authentication + authorization on; every capacity constraint at its default); scope units named b3b16-*.
#   arm AUTH: A + authenticator: PasswordAuthenticator, authorizer: CassandraAuthorizer, role_manager: CassandraRoleManager
#   arm LOAD-AUTH: empty node dir, same auth lines (the setup + load lifetime; not a reading)
# Stage-2 header:
# B16 victim controller (ms0611, aarch64), adapted from U4's victim-ctl.sh. One single-node Cassandra 5.0.9 per lifetime,
# unmodified build copied from ms0617:/mydata/s4/cassandra-base (arm I2: the patched copy $ROOT/tree-i2).
#   arm LOAD / A: shipped defaults (only directories change: environment)
#   arm I : A + tombstone_failure_threshold: 10000 (intervention, count bound tightened 10x)
#   arm R : A + read_thresholds_enabled: true + local_read_size_fail_threshold: 64MiB (byte control switched on)
#   arm I2: arm R on the diagnostic build (marker unsharedHeapSize counts its bound)
#   victim-ctl.sh start <label> <LOAD|A|I|R|I2> <heap e.g. 2G|16384M>     direct always auto (MAX_DIRECT_MEMORY_SIZE unset)
#   victim-ctl.sh ready|read <label> [tag]|gc|hist <label> <tag>|tblm <label> <tag>|stop|alive|oom|pid <label>
set -uo pipefail
ROOT=/mydata/s4/3b-B16
H=$ROOT/harness
log(){ echo "[$(TZ=America/New_York date '+%F %T %Z')] $*"; }
rd(){ echo "$ROOT/runs/$1"; }
pid(){ pgrep -f "Dcassandra.logdir=$(rd "$1")/logs " | head -1; }
mib(){ local v=$1; case $v in *G) echo $(( ${v%G} * 1024 ));; *M) echo "${v%M}";; esac; }
build(){ [ "$(cat "$(rd "$1")/arm" 2>/dev/null)" = I2 ] && echo "$ROOT/tree-i2" || echo "$ROOT/tree"; }

start(){
  local L=$1 ARM=$2 HEAP=$3 R; R=$(rd "$L")
  if pgrep -f 'java.*CassandraDaemon' >/dev/null; then log "REFUSE: a CassandraDaemon is already running"; pgrep -af 'java.*CassandraDaemon' | cut -c1-150; return 1; fi
  local hm; hm=$(mib "$HEAP"); local need=6144; [ "$hm" -lt 8192 ] && need=$(( hm + 6144 ))
  local free; free=$(df -m --output=avail /mydata | tail -1 | tr -d ' ')
  [ "${ARM#LOAD}" = "$ARM" ] && [ "$free" -lt "$need" ] && { log "REFUSE: /mydata free ${free} MiB < ${need} MiB"; return 1; }
  rm -rf "$ROOT/node" "$R"; mkdir -p "$R/logs"; echo "$ARM" > "$R/arm"
  if [ "$ARM" = LOAD ] || [ "$ARM" = LOAD-AUTH ]; then mkdir -p "$ROOT/node"/{data,commitlog,hints,saved_caches,cdc_raw}
  else cp -a "$ROOT/template" "$ROOT/node" || { log "clone failed"; return 1; }; fi
  cp -r "$ROOT/conf-pristine" "$R/conf"
  local y=$R/conf/cassandra.yaml
  sed -i \
    -e "s|^# data_file_directories:|data_file_directories:|" \
    -e "s|^#     - /var/lib/cassandra/data|    - $ROOT/node/data|" \
    -e "s|^# commitlog_directory: /var/lib/cassandra/commitlog|commitlog_directory: $ROOT/node/commitlog|" \
    -e "s|^# hints_directory: /var/lib/cassandra/hints|hints_directory: $ROOT/node/hints|" \
    -e "s|^# saved_caches_directory: /var/lib/cassandra/saved_caches|saved_caches_directory: $ROOT/node/saved_caches|" \
    -e "s|^# cdc_raw_directory: /var/lib/cassandra/cdc_raw|cdc_raw_directory: $ROOT/node/cdc_raw|" \
    "$y"
  case $ARM in
    A|LOAD) ;;
    AUTH|LOAD-AUTH) sed -i -e 's|^authenticator: AllowAllAuthenticator$|authenticator: PasswordAuthenticator|' \
                          -e 's|^authorizer: AllowAllAuthorizer$|authorizer: CassandraAuthorizer|' \
                          -e 's|^role_manager: .*$|role_manager: CassandraRoleManager|' "$y";;
    I) printf '# B16 arm I (intervention): count bound tightened 10x\ntombstone_failure_threshold: 10000\n' >> "$y";;
    R|I2) printf '# B16 arm %s: the byte control that is off by default, switched on\nread_thresholds_enabled: true\nlocal_read_size_fail_threshold: 64MiB\n' "$ARM" >> "$y";;
    *) log "bad arm $ARM"; return 1;;
  esac
  diff "$ROOT/conf-pristine/cassandra.yaml" "$y" > "$R/yaml.diff"
  local MM=$(( hm + 15872 + 8192 ))
  local XO=""; [ "$hm" -ge 8192 ] && XO="-XX:-HeapDumpOnOutOfMemoryError"
  local B; B=$(build "$L")
  echo "label=$L arm=$ARM heap=$HEAP direct=auto scopeMemoryMax=${MM}M build=$B start=$(date -u +%FT%TZ)" > "$R/run.meta"
  sha256sum "$B"/build/apache-cassandra-*.jar >> "$R/run.meta" 2>&1
  ( cd "$R" && CASSANDRA_CONF=$R/conf CASSANDRA_LOG_DIR=$R/logs MAX_HEAP_SIZE=$HEAP MAX_DIRECT_MEMORY_SIZE= \
    CASSANDRA_HEAPDUMP_DIR=$R \
    JVM_EXTRA_OPTS="-XX:NativeMemoryTracking=summary -Xlog:gc=info,safepoint=info:file=$R/gc.log:time,uptime,level,tags:filecount=20,filesize=20m $XO" \
    setsid nohup systemd-run --user --scope --unit="b3b16-$L-$(date +%s)" -p MemoryMax=${MM}M -p MemorySwapMax=0 \
      "$B/bin/cassandra" -f < /dev/null > "$R/stdout.log" 2>&1 & )
  local i p=""; for i in $(seq 1 30); do sleep 1; p=$(pid "$L"); [ -n "$p" ] && break; done
  [ -z "$p" ] && { log "no java pid for $L"; return 1; }
  echo "$p" > "$R/cass.pid"
  sed -n 's/^0:://p' /proc/"$p"/cgroup > "$R/cgroup.path"
  log "started $L pid $p cgroup $(cat "$R/cgroup.path")"
}

ready(){
  local L=$1 i R; R=$(rd "$L")
  for i in $(seq 1 60); do
    if grep -q "Starting listening for CQL clients" "$R/logs/system.log" 2>/dev/null; then
      log "ready $L"
      local p; p=$(pid "$L")
      ps -o args= -p "$p" | tr ' ' '\n' | grep -E '^-Xm[sx]|MaxDirect|NativeMemory|HeapDump|OnOutOfMemory|UseG1|G1HeapRegion|MaxGCPause|G1NewSize|AlwaysPreTouch' | tr '\n' ' ' | tee -a "$R/run.meta"; echo | tee -a "$R/run.meta"
      echo "resolved: $(timeout 20 jinfo -flag MaxDirectMemorySize "$p" 2>&1) $(timeout 20 jinfo -flag MaxHeapSize "$p" 2>&1)" | tee -a "$R/run.meta"
      ( setsid nohup java -Xmx64m -cp "$ROOT/cls" C2Sampler "$R/samples.csv" "$R/sampler.stop" 1000 > "$R/sampler.out" 2>&1 < /dev/null & echo $! > "$R/sampler.pid" )
      return 0
    fi
    [ "$(alive "$L")" = DEAD ] && { log "died during start"; return 1; }
    sleep 2
  done
  log "not ready in 120 s"; return 1
}

read_(){
  local L=$1 T=$2 R p; R=$(rd "$L"); p=$(pid "$L")
  local nm; nm=$(timeout 20 jcmd "$p" VM.native_memory summary 2>/dev/null)
  local oth tot
  oth=$(echo "$nm" | awk '/^-  *Other \(reserved=/{gsub(/[^0-9 ]/," ",$0); split($0,a," "); print a[2]; exit}')
  tot=$(echo "$nm" | awk '/^Total: reserved=/{gsub(/[^0-9 ]/," ",$0); split($0,a," "); print a[2]; exit}')
  local rss ra; rss=$(awk '/VmRSS/{print $2}' /proc/"$p"/status 2>/dev/null); ra=$(awk '/RssAnon/{print $2}' /proc/"$p"/status 2>/dev/null)
  local cg=/sys/fs/cgroup$(cat "$R/cgroup.path" 2>/dev/null) mc ok
  mc=$(cat "$cg/memory.current" 2>/dev/null); ok=$(awk '/^oom_kill /{print $2}' "$cg/memory.events" 2>/dev/null)
  [ -f "$cg/memory.events" ] && { rm -f "$R/memory.events.last"; cat "$cg/memory.events" > "$R/memory.events.last"; }
  local last; last=$(grep -v ERR "$R/samples.csv" 2>/dev/null | tail -1)
  echo "$(date -u +%s),$T,nmtOtherKB=${oth:-NA},nmtTotalKB=${tot:-NA},rssKB=${rss:-NA},rssAnonKB=${ra:-NA},scopeCurB=${mc:-NA},scopeOomKill=${ok:-NA},$last" | tee -a "$R/readings.csv"
}

gc(){ timeout 60 jcmd "$(pid "$1")" GC.run > /dev/null 2>&1; log "GC.run $1"; }
hist(){ timeout 120 jcmd "$(pid "$1")" GC.class_histogram > "$(rd "$1")/histo-$2.txt" 2>&1; log "histogram $1 $2"; }

# table metrics (K): TombstoneScannedHistogram Max/Count, TombstoneFailures, LocalReadSize Max/Count, LocalReadSizeAborts
tblm(){
  local L=$1 T=$2 R B; R=$(rd "$L"); B=$(build "$L")
  for tb in t m; do
    for x in TombstoneScannedHistogram:Max TombstoneScannedHistogram:Count TombstoneFailures:Count LocalReadSize:Max LocalReadSize:Count LocalReadSizeAborts:Count; do
      local n=${x%%:*} at=${x##*:} v
      v=$(timeout 60 "$B/bin/nodetool" -h 127.0.0.1 sjk mx -b "org.apache.cassandra.metrics:type=Table,keyspace=b16,scope=$tb,name=$n" -mg -f "$at" 2>&1 | grep -v '^$' | tail -1)
      echo "$T $tb $n.$at=$v"
    done
  done | tee -a "$R/tblmetrics.txt"
}

stop(){
  local L=$1 R p sp; R=$(rd "$L"); p=$(pid "$L"); sp=$(cat "$R/sampler.pid" 2>/dev/null)
  touch "$R/sampler.stop"; sleep 2
  [ -n "$sp" ] && kill "$sp" 2>/dev/null
  if [ -n "$p" ] && kill -0 "$p" 2>/dev/null; then
    timeout 120 "$(build "$L")/bin/nodetool" -h 127.0.0.1 drain > "$R/drain.out" 2>&1
    kill "$p"; for i in $(seq 1 60); do kill -0 "$p" 2>/dev/null || break; sleep 1; done
    kill -0 "$p" 2>/dev/null && kill -9 "$p"
  fi
  log "stopped $L"
}

alive(){ local p; p=$(cat "$(rd "$1")/cass.pid" 2>/dev/null); if [ -n "$p" ] && kill -0 "$p" 2>/dev/null; then echo ALIVE; else echo DEAD; fi; }

oom(){
  local R; R=$(rd "$1")
  grep -h -m3 -B1 -A14 "java.lang.OutOfMemoryError\|OutOfDirectMemoryError" "$R/logs/system.log" "$R/stdout.log" 2>/dev/null | head -60
  ls -la "$R" | grep -i "hprof\|hs_err" || true
  python3 "$H/gcwin.py" "$R"
}

cmd=$1; shift
case $cmd in
  start) start "$@";; ready) ready "$@";; read) read_ "$@";; gc) gc "$@";; hist) hist "$@";; tblm) tblm "$@";;
  stop) stop "$@";; alive) alive "$@";; oom) oom "$@";; pid) pid "$@";;
  *) echo "unknown $cmd"; exit 2;;
esac
