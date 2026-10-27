#!/usr/bin/env bash
# Cluster tier for data-free-space-warn-threshold--autonomous (stage 4, set A batch 8, tag fs, port slot 3).
# Usage: bash cluster-run.sh <run> <arm>      arm: S (4 GiB tmpfs, commitlog_total_space 256MiB)
#                                                  L (100 GiB tmpfs, 256MiB)
#                                                  C (100 GiB tmpfs, commitlog_total_space 64MiB: positive control)
# Env: N (stress rows, default 6000000), STRESS_MAX (seconds, default 900).
# Tree: ~/s4-b8-fs-n (ant jar). Node 127.0.3.1, JMX 7130, native 9042 on 127.0.3.1 only.
# Output: ~/s4-b8-fs-logs/cluster-<run>/<arm>/ {summary.txt, samples.csv, stress.out, logs/system.log, ...}
# Stops at the first failed first-trigger check (node not up, or WARN missing/ present against EXPECTED). Node always stopped on exit.
set -u
RUN=${1:?run}; ARM=${2:?arm}
N=${N:-6000000}; STRESS_MAX=${STRESS_MAX:-900}
T=$HOME/s4-b8-fs-n; M=$HOME/s4-b8-fs-mnt/node; W=$HOME/s4-b8-fs-nodework/$ARM
L=$HOME/s4-b8-fs-logs/cluster-$RUN/$ARM
IP=127.0.3.1; JMX=7130
case $ARM in S) SIZE=4G; CL=256MiB;; L) SIZE=100G; CL=256MiB;; C) SIZE=100G; CL=64MiB;; *) echo bad arm; exit 2;; esac
rm -rf "$L" "$W"; mkdir -p "$L/logs" "$W/conf" "$M"
SUM=$L/summary.txt; : > "$SUM"
say(){ echo "$@" | tee -a "$SUM"; }
FAIL=0; NODEPID=""; SAMPPID=""
cleanup(){
  [ -n "$SAMPPID" ] && kill "$SAMPPID" 2>/dev/null
  if [ -n "$NODEPID" ] && kill -0 "$NODEPID" 2>/dev/null; then kill "$NODEPID" 2>/dev/null; for i in $(seq 1 30); do kill -0 "$NODEPID" 2>/dev/null || break; sleep 1; done; kill -0 "$NODEPID" 2>/dev/null && kill -9 "$NODEPID"; fi
  mountpoint -q "$M" && { sync; sudo umount "$M" || { sleep 2; sudo umount -l "$M"; }; }
  say "cleanup: node pid ${NODEPID:-none} alive=$( [ -n "$NODEPID" ] && kill -0 "$NODEPID" 2>/dev/null && echo yes || echo no); mount left=$(mount | grep -c "$M")"
}
trap cleanup EXIT
ulimit -n 100000
say "run=$RUN arm=$ARM size=$SIZE commitlog_total_space=$CL N=$N start=$(date -u +%FT%TZ)"
sudo mount -t tmpfs -o size=$SIZE tmpfs "$M" && sudo chown "$(id -u)" "$M" || { say "mount failed"; exit 1; }
mkdir -p "$M"/{data,commitlog,hints,saved_caches,cdc_raw}
say "volume avail at start: $(df -B1 --output=avail "$M" | tail -1) bytes"

# conf copy
cp -r "$T/conf/." "$W/conf/"
python3 - "$W/conf/cassandra.yaml" "$M" "$IP" "$CL" <<'PY'
import sys,re
f,m,ip,cl=sys.argv[1:]
s=open(f).read()
def setk(k,v):
    global s
    if re.search(r"^%s:"%k,s,flags=re.M): s=re.sub(r"^%s:.*$"%k,"%s: %s"%(k,v),s,count=1,flags=re.M)
    elif re.search(r"^# %s:"%k,s,flags=re.M): s=re.sub(r"^# %s:.*$"%k,"%s: %s"%(k,v),s,count=1,flags=re.M)
    else: s+="\n%s: %s\n"%(k,v)
setk("cluster_name","'s4-b8-fs'")
setk("listen_address",ip); setk("rpc_address",ip)
setk("commitlog_directory",m+"/commitlog"); setk("hints_directory",m+"/hints"); setk("saved_caches_directory",m+"/saved_caches"); setk("cdc_raw_directory",m+"/cdc_raw")
setk("auto_snapshot","false"); setk("commitlog_total_space",cl); setk("disk_failure_policy","stop")
s=re.sub(r"^data_file_directories:\n(#?\s*- .*\n)+","data_file_directories:\n    - %s/data\n"%m,s,flags=re.M)
if "data_file_directories:\n    - "+m not in s: s+="\ndata_file_directories:\n    - %s/data\n"%m
s=re.sub(r"(seeds:\s*)\"[^\"]*\"",r'\1"%s:7000"'%ip,s)
open(f,"w").write(s)
PY
sed -i "s/^JMX_PORT=\"7199\"/JMX_PORT=\"$JMX\"/" "$W/conf/cassandra-env.sh"
grep -E '^(cluster_name|listen_address|rpc_address|commitlog_directory|data_file_directories|auto_snapshot|commitlog_total_space|disk_failure_policy)|^    - |seeds:' "$W/conf/cassandra.yaml" | tee "$L/yaml-effective.txt" >/dev/null
cp "$L/yaml-effective.txt" "$SUM.yaml" 2>/dev/null
say "yaml: $(tr '\n' ' ' < "$L/yaml-effective.txt")"
grep -q "data_file_directories" "$L/yaml-effective.txt" && grep -q "$M/data" "$L/yaml-effective.txt" || { say "STOP: yaml data dir not set"; exit 1; }

# start node
export CASSANDRA_CONF=$W/conf MAX_HEAP_SIZE=1G HEAP_NEWSIZE=256M
cd "$T"
( setsid nohup env CASSANDRA_LOG_DIR="$L/logs" bash -c 'echo $$ > "$0"; exec bin/cassandra -f' "$W/pid" < /dev/null > "$L/node.out" 2>&1 & )
for i in $(seq 1 20); do [ -s "$W/pid" ] && break; sleep 1; done
NODEPID=$(cat "$W/pid" 2>/dev/null)
say "node pid=$NODEPID"
UP=0
for i in $(seq 1 120); do
  kill -0 "$NODEPID" 2>/dev/null || { say "STOP: node died during start"; tail -5 "$L/node.out" | tee -a "$SUM"; exit 1; }
  if bin/nodetool -h 127.0.0.1 -p $JMX statusbinary 2>/dev/null | grep -q running && bin/nodetool -h 127.0.0.1 -p $JMX status 2>/dev/null | grep -q '^UN' && (exec 3<>/dev/tcp/$IP/9042) 2>/dev/null; then UP=1; sleep 5; break; fi
  sleep 3
done
[ $UP = 1 ] || { say "STOP: node not serving native port after 360 s"; exit 1; }
say "node up at $(date -u +%FT%TZ); ps java RSS check: $(ps -o rss= -p $NODEPID) KiB"

# first-trigger check: the startup WARN
WARNS=$(grep -c 'free across all data volumes' "$L/logs/system.log")
say "startup WARN lines: $WARNS: $(grep 'free across all data volumes' "$L/logs/system.log" | sed 's/.*WARN *//' | head -2 | tr '\n' '|')"
if [ $ARM = S ]; then
  [ "$WARNS" = 1 ] && say "EXPECTED OK: [S] exactly one 'free across all data volumes' WARN at start" || { say "EXPECTED FAIL: [S] WARN count $WARNS (want 1)"; exit 1; }
else
  [ "$WARNS" = 0 ] && say "EXPECTED OK: [$ARM] no WARN at start (100 GiB volume)" || { say "EXPECTED FAIL: [$ARM] WARN count $WARNS (want 0)"; exit 1; }
fi

# sampler (every 5 s): epoch_ms,used,avail,data_bytes,commitlog_bytes
echo "epoch_ms,vol_used,vol_avail,data_bytes,commitlog_bytes,node_alive" > "$L/samples.csv"
( while true; do
    u=$(df -B1 --output=used,avail "$M" | tail -1)
    echo "$(date +%s%3N),$(echo $u | awk '{print $1","$2}'),$(du -sb $M/data 2>/dev/null | cut -f1),$(du -sb $M/commitlog 2>/dev/null | cut -f1),$(kill -0 $NODEPID 2>/dev/null && echo 1 || echo 0)" >> "$L/samples.csv"
    sleep 5
  done ) &
SAMPPID=$!

# workload
say "stress start $(date -u +%FT%TZ): n=$N col n=5 size=200 threads=32 (max ${STRESS_MAX}s)"
( setsid timeout $STRESS_MAX tools/bin/cassandra-stress write n=$N -col size=FIXED\(200\) n=FIXED\(5\) -rate threads=32 -errors ignore -node $IP > "$L/stress.out" 2>&1 < /dev/null; echo "stress_exit=$?" >> "$L/stress.exit" ) &
for i in $(seq 1 $((STRESS_MAX/5+12))); do [ -s "$L/stress.exit" ] && break; sleep 5; done
say "stress end $(date -u +%FT%TZ): $(cat "$L/stress.exit" 2>/dev/null)"
sleep 20
kill $SAMPPID 2>/dev/null; SAMPPID=""

# summary
python3 - "$L" <<'PY' | tee -a "$SUM"
import sys,csv,re
L=sys.argv[1]
r=list(csv.DictReader(open(L+"/samples.csv")))
f=lambda k:[float(x[k]) for x in r if x[k] not in ("","None")]
print("samples=%d vol_used_max=%.0f vol_avail_min=%.0f data_bytes_max=%.0f commitlog_bytes_max=%.0f node_alive_last=%s"%(len(r),max(f("vol_used")),min(f("vol_avail")),max(f("data_bytes")),max(f("commitlog_bytes")),r[-1]["node_alive"]))
t=open(L+"/stress.out",errors="ignore").read()
for k in ("Total partitions","Total errors","Op rate","Total operation time"):
    m=re.findall(r"^%s\s*:.*$"%k,t,flags=re.M)
    print("stress",m[-1] if m else k+": (absent)")
PY
grep -c . "$L/stress.out" | sed 's/^/stress.out lines: /' | tee -a "$SUM"
S="$L/logs/system.log"
say "system.log: ERROR lines=$(grep -c '^ERROR' $S) FSWriteError/No space=$(grep -ci 'no space left\|FSWriteError\|FSDiskFull' $S) disk_failure_policy/stop=$(grep -ci 'stopping transports\|Stopping gossiper\|Stop transport' $S)"
grep -m3 -i 'no space left\|FSWriteError\|FSDiskFull\|Stopping' $S | cut -c1-220 | tee -a "$SUM"
say "free-space WARN lines total: $(grep -c 'free across all data volumes' $S) (re-read at end)"
echo "$(date -u +%FT%TZ) done"| tee -a "$SUM"
exit 0
