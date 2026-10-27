#!/usr/bin/env bash
# Cluster tier for local_system_data_file_directory-applySimpleConfig-freeBytes--autonomous (stage 4, set A batch 8, tag ls, port slot 6).
# Usage: bash cluster-run.sh <run> <arm>
#   A  sysdata tmpfs (3 GiB) filled to leave 0.5 GiB at start        (B3 step 1-3)
#   B  sysdata tmpfs filled to leave 1.5 GiB at start                (step 5)
#   C  1.5 GiB at start, filler grown after phase 1 to leave 100 MiB (step 6)
#   D  directory unset (default), same tmpfs mounted at 0.5 GiB      (B3h control)
#   P  commit-log control, no sysdata dir: commitlog_total_space 64MiB, 1M x 1 KiB rows (amended B3c/B3e step 7)
#   U  same as P with commitlog_total_space 16384MiB (contrast)
# Tree ~/s4-b8-ls-n (copy-source.sh + ant jar). Node 127.0.6.1, JMX 7160, native 9042 on 127.0.6.1 only.
# Output ~/s4-b8-ls-logs/cluster-<run>/<arm>/. First-trigger check: the startup WARN count (A=1, others 0); stops there on a mismatch. Node always stopped on exit.
set -u
RUN=${1:?run}; ARM=${2:?arm}
HERE=$(cd "$(dirname "$0")" && pwd)
T=$HOME/s4-b8-ls-n; MB=$HOME/s4-b8-ls-mnt; SYS=$MB/sys; ND=$MB/node; W=$HOME/s4-b8-ls-nodework/$ARM
L=$HOME/s4-b8-ls-logs/cluster-$RUN/$ARM
IP=127.0.6.1; JMX=7160
MIB=$((1<<20)); GIB=$((1<<30))
case $ARM in
  A) LEAVE=$((GIB/2)); USESYS=1; CL=64MiB; HEAP=1G;;
  B) LEAVE=$((GIB*3/2)); USESYS=1; CL=64MiB; HEAP=1G;;
  C) LEAVE=$((GIB*3/2)); USESYS=1; CL=64MiB; HEAP=1G; SHRINK=1;;
  D) LEAVE=$((GIB/2)); USESYS=0; CL=64MiB; HEAP=1G;;
  P) USESYS=0; CL=64MiB; HEAP=8G; CTRL=1;;
  U) USESYS=0; CL=16384MiB; HEAP=8G; CTRL=1;;
  *) echo bad arm; exit 2;;
esac
SHRINK=${SHRINK:-0}; CTRL=${CTRL:-0}
rm -rf "$L" "$W"; mkdir -p "$L/logs" "$W/conf" "$MB"
SUM=$L/summary.txt; : > "$SUM"
say(){ echo "$@" | tee -a "$SUM"; }
FAIL=0; NODEPID=""; SAMPPID=""; CHURNPID=""
cleanup(){
  [ -n "$SAMPPID" ] && kill "$SAMPPID" 2>/dev/null
  [ -n "$CHURNPID" ] && kill "$CHURNPID" 2>/dev/null
  if [ -n "$NODEPID" ] && kill -0 "$NODEPID" 2>/dev/null; then kill "$NODEPID" 2>/dev/null; for i in $(seq 1 40); do kill -0 "$NODEPID" 2>/dev/null || break; sleep 1; done; kill -0 "$NODEPID" 2>/dev/null && kill -9 "$NODEPID"; fi
  for m in "$SYS" "$ND"; do mountpoint -q "$m" && { sync; sudo umount "$m" || { sleep 2; sudo umount -l "$m"; }; }; done
  say "cleanup: node pid ${NODEPID:-none} alive=$( [ -n "$NODEPID" ] && kill -0 "$NODEPID" 2>/dev/null && echo yes || echo no); mounts left=$(mount | grep -c "$MB"); daemons(mine)=$(ps -eo pid,cmd | grep '[j]ava.*CassandraDaemon' | grep -c "$T")"
}
trap cleanup EXIT
ulimit -n 100000
say "run=$RUN arm=$ARM sysdata_dir=$USESYS commitlog_total_space=$CL heap=$HEAP start=$(date -u +%FT%TZ)"
ps -eo pid,cmd | grep '[j]ava.*CassandraDaemon' | grep -q "$T" && { say "STOP: a daemon of my tree is already running"; exit 1; }
ss -ltn | grep -q "$IP:" && { say "STOP: $IP already has listeners"; exit 1; }

sudo mkdir -p "$SYS" "$ND"
sudo mount -t tmpfs -o size=24G tmpfs "$ND" && sudo chown "$(id -u)" "$ND" || { say "mount node failed"; exit 1; }
mkdir -p "$ND"/{data,commitlog,hints,saved_caches,cdc_raw}
if [ "$ARM" != P ] && [ "$ARM" != U ]; then
  sudo mount -t tmpfs -o size=3G tmpfs "$SYS" && sudo chown "$(id -u)" "$SYS" || { say "mount sys failed"; exit 1; }
  mkdir -p "$SYS/system"
  FILL=$((3*GIB - LEAVE)); fallocate -l $FILL "$SYS/filler" || { say "fallocate failed"; exit 1; }
  say "sysdata volume avail at start: $(df -B1 --output=avail "$SYS" | tail -1) bytes (target $LEAVE)"
  [ "$(df -B1 --output=avail "$SYS" | tail -1 | tr -d ' ')" = "$LEAVE" ] || { say "STOP: sysdata free space is not the target"; exit 1; }
fi

cp -r "$T/conf/." "$W/conf/"
python3 - "$W/conf/cassandra.yaml" "$ND" "$IP" "$CL" "$USESYS" "$SYS/system" "$CTRL" <<'PY'
import sys,re
f,m,ip,cl,usesys,sysdir,ctrl=sys.argv[1:]
s=open(f).read()
def setk(k,v):
    global s
    if re.search(r"^%s:"%k,s,flags=re.M): s=re.sub(r"^%s:.*$"%k,"%s: %s"%(k,v),s,count=1,flags=re.M)
    elif re.search(r"^# %s:"%k,s,flags=re.M): s=re.sub(r"^# %s:.*$"%k,"%s: %s"%(k,v),s,count=1,flags=re.M)
    else: s+="\n%s: %s\n"%(k,v)
setk("cluster_name","'s4-b8-ls'")
setk("listen_address",ip); setk("rpc_address",ip)
setk("commitlog_directory",m+"/commitlog"); setk("hints_directory",m+"/hints"); setk("saved_caches_directory",m+"/saved_caches"); setk("cdc_raw_directory",m+"/cdc_raw")
setk("auto_snapshot","false"); setk("commitlog_total_space",cl)
if usesys=="1": setk("local_system_data_file_directory",sysdir)
if ctrl=="1":
    setk("memtable_allocation_type","offheap_objects"); setk("memtable_heap_space","2048MiB"); setk("memtable_offheap_space","4096MiB"); setk("memtable_cleanup_threshold","0.9")
s=re.sub(r"^data_file_directories:\n(#?\s*- .*\n)+","data_file_directories:\n    - %s/data\n"%m,s,flags=re.M)
if "data_file_directories:\n    - "+m not in s: s+="\ndata_file_directories:\n    - %s/data\n"%m
s=re.sub(r"(seeds:\s*)\"[^\"]*\"",r'\1"%s:7000"'%ip,s)
open(f,"w").write(s)
PY
sed -i "s/^JMX_PORT=\"7199\"/JMX_PORT=\"$JMX\"/" "$W/conf/cassandra-env.sh"
grep -E '^(cluster_name|listen_address|rpc_address|commitlog_directory|data_file_directories|auto_snapshot|commitlog_total_space|local_system_data_file_directory|disk_failure_policy|memtable_[a-z_]*|commitlog_segment_size):|^    - |seeds:' "$W/conf/cassandra.yaml" > "$L/yaml-effective.txt"
say "yaml: $(tr '\n' ' ' < "$L/yaml-effective.txt")"
if [ $USESYS = 1 ]; then grep -q "^local_system_data_file_directory: $SYS/system" "$L/yaml-effective.txt" || { say "STOP: yaml sysdata dir not set"; exit 1; }
else grep -q '^local_system_data_file_directory' "$L/yaml-effective.txt" && { say "STOP: yaml has a sysdata dir in an unset arm"; exit 1; }; fi

export CASSANDRA_CONF=$W/conf MAX_HEAP_SIZE=$HEAP HEAP_NEWSIZE=$([ $HEAP = 8G ] && echo 800M || echo 256M)
cd "$T"
( setsid nohup env CASSANDRA_LOG_DIR="$L/logs" bash -c 'echo $$ > "$0"; exec bin/cassandra -f' "$W/pid" < /dev/null > "$L/node.out" 2>&1 & )
for i in $(seq 1 20); do [ -s "$W/pid" ] && break; sleep 1; done
NODEPID=$(cat "$W/pid" 2>/dev/null); say "node pid=$NODEPID"
UP=0
for i in $(seq 1 120); do
  kill -0 "$NODEPID" 2>/dev/null || { say "STOP: node died during start"; tail -n 8 "$L/node.out" | tee -a "$SUM"; exit 1; }
  if bin/nodetool -h 127.0.0.1 -p $JMX statusbinary 2>/dev/null | grep -q running && bin/nodetool -h 127.0.0.1 -p $JMX status 2>/dev/null | grep -q '^UN'; then UP=1; sleep 3; break; fi
  sleep 3
done
[ $UP = 1 ] || { say "STOP: node not UN/running after 360 s"; exit 1; }
say "node up at $(date -u +%FT%TZ) (UN, statusbinary running)"
grep -o 'local_system_data_file_directory=[^;,]*\|commitlog_total_space=[^;,]*' "$L/logs/system.log" | sort -u | head -3 | sed 's/^/CONFIG /' | tee -a "$SUM"

# first-trigger check: startup WARN
S="$L/logs/system.log"
SW=$(grep -c 'free in the system data volume' "$S"); say "startup sys WARN lines: $SW: $(grep 'free in the system data volume' "$S" | sed 's/.*WARN *//' | cut -c1-140 | head -2 | tr '\n' '|')"
if [ $ARM = A ]; then
  [ "$SW" = 1 ] && grep -q 'Only 512.000MiB free in the system data volume' "$S" && say "EXPECTED OK: [A] one sys WARN 'Only 512.000MiB free ...' at start" || { say "EXPECTED FAIL: [A] sys WARN count $SW (want 1, 512.000MiB)"; exit 1; }
else
  [ "$SW" = 0 ] && say "EXPECTED OK: [$ARM] no sys WARN at start" || { say "EXPECTED FAIL: [$ARM] sys WARN count $SW (want 0)"; exit 1; }
fi
SYSOFF=$(stat -c %s "$S")
# the native port can lag behind statusbinary: wait until it accepts (shakedown 1 found stress and cqlsh refused)
NP=0; for i in $(seq 1 40); do (exec 3<>/dev/tcp/$IP/9042) 2>/dev/null && { NP=1; break; }; sleep 3; done
[ $NP = 1 ] && say "native port $IP:9042 accepts" || { say "STOP: native port not accepting"; exit 1; }
sleep 5

# sampler
echo "epoch_ms,sys_avail,sys_dir_bytes,node_data_bytes,commitlog_bytes,node_alive" > "$L/samples.csv"
INT=$([ $CTRL = 1 ] && echo 1 || echo 5)
( while true; do
    if [ $USESYS = 1 ] || [ $ARM = D ]; then sa=$(df -B1 --output=avail "$SYS" | tail -1 | tr -d ' '); sd=$(du -sb "$SYS/system" 2>/dev/null | cut -f1); else sa=; sd=; fi
    echo "$(date +%s%3N),$sa,$sd,$(du -sb $ND/data 2>/dev/null | cut -f1),$(du -sb $ND/commitlog 2>/dev/null | cut -f1),$(kill -0 $NODEPID 2>/dev/null && echo 1 || echo 0)" >> "$L/samples.csv"
    sleep $INT
  done ) &
SAMPPID=$!

stress(){ # tag args...
  local tag=$1; shift
  say "stress $tag start $(date -u +%FT%TZ): $*"
  tools/bin/cassandra-stress "$@" -node $IP > "$L/stress-$tag.out" 2>&1 < /dev/null; say "stress $tag end $(date -u +%FT%TZ) rc=$?"
}
if [ $CTRL = 1 ]; then
  timeout 600 bash -c "$(declare -f say stress); SUM='$SUM'; L='$L'; IP=$IP; cd '$T'; stress p1 write n=1000000 no-warmup cl=ONE -col 'n=FIXED(1)' 'size=FIXED(1024)' -schema 'replication(factor=1)' -rate threads=64"
  sleep 20
else
  STOPFLAG=$L/churn.stop; rm -f "$STOPFLAG"
  ( setsid bash "$HERE/churn.cql.sh" "$T" $IP "$L/churn" "$STOPFLAG" 420 < /dev/null > /dev/null 2>&1 & echo $! > "$W/churn.pid" )
  sleep 1; CHURNPID=$(cat "$W/churn.pid" 2>/dev/null)
  timeout 600 bash -c "$(declare -f say stress); SUM='$SUM'; L='$L'; IP=$IP; cd '$T'; stress ph1 write n=200000 no-warmup cl=ONE -rate threads=16"
  if [ $SHRINK = 1 ]; then
    NOW=$(df -B1 --output=avail "$SYS" | tail -1 | tr -d ' '); EXTRA=$((NOW - 100*MIB))
    CUR=$(stat -c %s "$SYS/filler"); fallocate -l $((CUR + EXTRA)) "$SYS/filler"
    say "SHRINK at $(date -u +%FT%TZ) epoch_ms=$(date +%s%3N): sysdata avail $NOW -> $(df -B1 --output=avail "$SYS" | tail -1 | tr -d ' ') bytes"
  fi
  timeout 600 bash -c "$(declare -f say stress); SUM='$SUM'; L='$L'; IP=$IP; cd '$T'; stress ph2 write n=200000 no-warmup cl=ONE -pop seq=200001..400000 -rate threads=16"
  sleep 30
  touch "$STOPFLAG"
  for i in $(seq 1 60); do grep -q 'churn done' "$L/churn/churn.log" 2>/dev/null && break; sleep 5; done
fi
kill $SAMPPID 2>/dev/null; SAMPPID=""
say "workload end $(date -u +%FT%TZ); node alive=$(kill -0 $NODEPID 2>/dev/null && echo yes || echo no)"
bin/nodetool -h 127.0.0.1 -p $JMX status 2>&1 | grep -E '^(UN|DN)' | tee -a "$SUM"
tail -c +$((SYSOFF+1)) "$S" > "$L/system-run.log"
python3 - "$L" "$ARM" <<'PY' | tee -a "$SUM"
import sys,csv,re,glob
L,arm=sys.argv[1:]
r=list(csv.DictReader(open(L+"/samples.csv")))
f=lambda k:[float(x[k]) for x in r if x[k] not in ("","None")]
out="samples=%d node_alive_last=%s commitlog_bytes_max=%.0f node_data_bytes_max=%.0f"%(len(r),r[-1]["node_alive"],max(f("commitlog_bytes")),max(f("node_data_bytes")))
if f("sys_avail"): out+=" sys_avail_min=%.0f sys_dir_bytes_max=%.0f"%(min(f("sys_avail")),max(f("sys_dir_bytes")))
print(out)
for t in sorted(glob.glob(L+"/stress-*.out")):
    s=open(t,errors="ignore").read()
    g=lambda k:(re.findall(r"^%s\s*:\s*(.*)$"%k,s,flags=re.M) or ["(absent)"])[-1]
    print(t.split("/")[-1],"Total partitions:",g("Total partitions"),"| Total errors:",g("Total errors"),"| Op rate:",g("Op rate"))
sl=open(L+"/system-run.log",errors="ignore").read().splitlines()
print("system-run.log: sys WARN after start=%d, data-volume WARN=%d, ERROR lines=%d, FSWriteError/NoSpace=%d, stop-transports=%d"%(
  sum('free in the system data volume' in x for x in sl),sum('free across all data volumes' in x for x in sl),sum(x.startswith('ERROR') for x in sl),
  sum(bool(re.search('FSWriteError|No space left|FSDiskFull',x)) for x in sl),sum(bool(re.search('Stopping transports|stop transport|Stopping gossiper',x,re.I)) for x in sl)))
try:
    cl=open(L+"/churn/churn.log").read().splitlines(); print("churn:",cl[-1],"| passes with errors:",sum(1 for x in cl if 'pass=' in x and not re.search('create_err_lines=0 drop_err_lines=0',x)),"of",sum(1 for x in cl if 'pass=' in x))
except Exception as e: print("churn: n/a")
PY
echo "$(date -u +%FT%TZ) done" | tee -a "$SUM"
exit 0
