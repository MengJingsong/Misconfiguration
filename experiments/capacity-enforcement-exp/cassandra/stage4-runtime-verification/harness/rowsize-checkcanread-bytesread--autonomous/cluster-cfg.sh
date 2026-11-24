#!/bin/bash
# Stage-4 cluster tier (B3e steps 1-10 as amended by B3i), one configuration. Runs on ms0640.
# usage: cluster-cfg.sh <cfg> <S_MiB> <V_MiB> <max_value_size_MiB>
set -u
CFG=$1; S_MiB=$2; V_MiB=$3; MAXV=$4
O=/mydata/jingsong-cass-s4/o122
RUN=$O/cluster
T=$RUN/node-tree
R=$RUN/results-$CFG
mkdir -p $R
exec > >(tee -a $R/session.log) 2>&1
ms(){ date +%s%3N; }
log(){ echo "[$(date -u +%FT%T.%3NZ) $(ms)] $*"; }
die(){ log "FAIL: $*"; stop_node; exit 1; }
S=$((S_MiB*1048576)); V=$((V_MiB*1048576))
vint(){ python3 -c "import sys;n=int(sys.argv[1]);assert (1<<21)<=n<(1<<28);print('%08x'%(0xe0000000|n))" $1; }
VS=$(vint $S); VV=$(vint $V)
log "cfg=$CFG S=$S ($VS) V=$V ($VV) max_value_size=${MAXV}MiB host=$(hostname) arch=$(uname -m)"
ulimit -n 100000
NT="$T/bin/nodetool -p 17299"
CQ="$T/bin/cqlsh 127.0.0.1 19142 --request-timeout=60"

NODEPID=""
stop_node(){
  # the daemon deletes its pid file before it has exited, so wait on the pid saved at start
  local p=${NODEPID:-$(cat $RUN/pid 2>/dev/null)}
  if [ -n "$p" ] && kill -0 $p 2>/dev/null; then
    log "kill $p"; kill $p
    for i in $(seq 1 120); do kill -0 $p 2>/dev/null || break; sleep 1; done
    kill -0 $p 2>/dev/null && { log "kill -9 $p"; kill -9 $p; sleep 2; }
  fi
  for i in $(seq 1 60); do ss -ltn | grep -qE ":(17100|19142|17299)\b" || break; sleep 1; done
  log "CassandraDaemon left: $(ps -eo cmd | grep '[C]assandraDaemon' | grep -c "$T"); ports listening: $(ss -ltn | grep -cE ':(17100|19142|17299)\b')"
}

start_node(){ # $1 = phase (write|read)
  local ph=$1
  log "start node phase=$ph"
  ( cd $T && MAX_HEAP_SIZE=1G HEAP_NEWSIZE=200M CASSANDRA_LOG_DIR=$RUN/logs \
    JVM_EXTRA_OPTS="-Xlog:gc*:file=$RUN/gc-$CFG-$ph.log:time,uptime -XX:StartFlightRecording=name=s4,settings=profile,filename=$RUN/rec-$CFG-$ph.jfr,dumponexit=true" \
    bin/cassandra -p $RUN/pid > $R/start-$ph.out 2>&1 )
  sleep 3
  for i in $(seq 1 100); do
    [ -f $RUN/pid ] && kill -0 $(cat $RUN/pid) 2>/dev/null || die "daemon died during start ($ph)"
    if $NT status 2>/dev/null | grep -q '^UN' && [ "$($NT statusbinary 2>/dev/null)" = running ]; then
      NODEPID=$(cat $RUN/pid)
      log "node UN and binary running (phase=$ph, pid $NODEPID)"; return 0; fi
    sleep 3
  done
  die "node did not come up ($ph)"
}

# step 1: clean start
rm -rf $RUN/{data,commitlog,hints,saved_caches,cdc_raw,logs,pid} $RUN/gc-$CFG-*.log $RUN/rec-$CFG*.jfr
sed -i "s/^max_value_size: .*# S4-MAXVALUE$/max_value_size: ${MAXV}MiB  # S4-MAXVALUE/" $T/conf/cassandra.yaml
grep -n 'S4-MAXVALUE' $T/conf/cassandra.yaml
for p in 17100 19142 17299; do ss -ltn | grep -q ":$p\b" && die "port $p busy"; done
start_node write
ps -o args= -p $(cat $RUN/pid) | tr ' ' '\n' | grep -E '^-Xm[sx]|^-Xlog:gc\*:file|StartFlightRecording|^-XX:\+Use.*GC' > $R/cmdline-write.txt
cat $R/cmdline-write.txt
# step 2: schema
$CQ -e "CREATE KEYSPACE s4 WITH replication = {'class':'SimpleStrategy','replication_factor':1}; CREATE TABLE s4.t (k int PRIMARY KEY, v blob) WITH compression = {'enabled': false};" || die schema
$NT disableautocompaction s4 || die disableautocompaction
$CQ -e "DESCRIBE TABLE s4.t" > $R/schema.txt; grep -n "compression" $R/schema.txt
# step 3: insert
python3 -c "import sys;S=int(sys.argv[1]);v=b'S4MARKER-TDIPLIM'+b'\0'*(S-16);open('$RUN/ins.cql','w').write('INSERT INTO s4.t (k,v) VALUES (1,0x%s);\n'%v.hex())" $S
log "ins.cql bytes=$(stat -c %s $RUN/ins.cql)"
t0=$(ms); timeout 600 $CQ -f $RUN/ins.cql; rc=$?; log "cqlsh -f rc=$rc in $(( $(ms)-t0 )) ms"
[ $rc -eq 0 ] || die "insert failed (B3i.3 fallback needed)"
# step 4: sanity read
$CQ -e "SELECT k FROM s4.t WHERE k=1;" | tee $R/sanity-k.txt
grep -q "(1 rows)" $R/sanity-k.txt || die "sanity SELECT k"
$NT flush s4 t || die flush
SAN0=$(ms); $CQ -e "SELECT v FROM s4.t WHERE k=1;" > $R/sanity-v.out 2>&1; rc=$?; SAN1=$(ms)
log "SANITY_READ start=$SAN0 end=$SAN1 rc=$rc outbytes=$(stat -c %s $R/sanity-v.out) rows=$(grep -c '(1 rows)' $R/sanity-v.out)"
[ $rc -eq 0 ] && grep -q '(1 rows)' $R/sanity-v.out || die "sanity SELECT v"
rm -f $R/sanity-v.out
# step 5: flush, drain, stop
$NT flush s4 t && $NT drain || die drain
stop_node
ls -l $RUN/data/s4/t-*/ > $R/sstables.txt; cat $R/sstables.txt
# step 6: patch
python3 - <<EOF || die patch
import glob; f=glob.glob('$RUN/data/s4/t-*/*-Data.db'); assert len(f)==1, f
b=bytearray(open(f[0],'rb').read()); m=b.find(b'S4MARKER-TDIPLIM'); assert m>=4 and b.count(b'S4MARKER-TDIPLIM')==1
assert b[m-4:m].hex()=='$VS', b[m-4:m].hex()
n=len(b); b[m-4:m]=bytes.fromhex('$VV'); open(f[0],'wb').write(b); assert len(open(f[0],'rb').read())==n
print('PATCH file', f[0], 'size', n, 'at', m-4, '$VS', '->', '$VV')
EOF
# step 7: restart
start_node read
ps -o args= -p $(cat $RUN/pid) | tr ' ' '\n' | grep -E '^-Xm[sx]|^-Xlog:gc\*:file|StartFlightRecording|^-XX:\+Use.*GC' > $R/cmdline-read.txt
grep -i "replay" $RUN/logs/system.log | tail -5 > $R/replay.txt; cat $R/replay.txt
# step 8: three reads, 10 s apart
for i in 1 2 3; do
  a=$(ms); $CQ -e "SELECT v FROM s4.t WHERE k=1;" > $R/read$i.out 2>&1; rc=$?; b=$(ms)
  log "READ$i start=$a end=$b rc=$rc out=$(head -c 300 $R/read$i.out | tr '\n' ' ')"
  sleep 10
done
# optional extra row (B3h): SELECT k (value may be skipped)
a=$(ms); $CQ -e "SELECT k FROM s4.t WHERE k=1;" > $R/readk.out 2>&1; rc=$?; b=$(ms)
log "READK start=$a end=$b rc=$rc out=$(head -c 300 $R/readk.out | tr '\n' ' ')"
sleep 3
kill -0 $NODEPID 2>/dev/null && log "node still up after reads" || log "NODE DOWN after reads"
# step 9: dump JFR, logs
jcmd $NODEPID JFR.dump name=s4 filename=$RUN/rec-$CFG.jfr
jfr print --json --events jdk.ObjectAllocationOutsideTLAB $RUN/rec-$CFG.jfr > $R/alloc-read.json
grep -A5 "EOF after\|Corrupt value length" $RUN/logs/system.log > $R/systemlog-excerpt.txt
grep -c "EOF after" $RUN/logs/system.log | sed 's/^/EOF_LINES=/'; grep -c "Corrupt value length" $RUN/logs/system.log | sed 's/^/CORRUPT_LEN_LINES=/'
grep -o "max_value_size=[^;]*;\|disk_failure_policy=[^;]*;" $RUN/logs/system.log | sort | uniq -c > $R/config-dump.txt; cat $R/config-dump.txt
# step 10: stop, archive
stop_node
jfr print --json --events jdk.ObjectAllocationOutsideTLAB $RUN/rec-$CFG-write.jfr > $R/alloc-write.json
cp $RUN/logs/system.log $R/system.log; cp $RUN/gc-$CFG-*.log $R/ 2>/dev/null
grep -c "Humongous" $R/gc-$CFG-read.log | sed 's/^/HUMONGOUS_LINES_READ=/'
ls -l $RUN/rec-$CFG*.jfr
log "cfg $CFG done"
