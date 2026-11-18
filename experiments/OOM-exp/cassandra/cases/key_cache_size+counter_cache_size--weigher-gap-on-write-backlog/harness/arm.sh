#!/usr/bin/env bash
# R8 arm controller, runs ON pc91 (S2 run-1 arm.sh + run-2 collect.sh, single host; procedure = case file §2.5 steps 1-12).
#   arm.sh <name> <T|P|E> <N>
#     T: build orig, caches kept;  P: build patched (+104 B/entry weigher), caches kept;  E: build orig, caches invalidated
#   env: VX (V heap, default 2G), SESS (client sessions x 256 in flight, default 8), FILL_SMALL=1 (shakedown: 20k fill)
set -uo pipefail
NAME=$1 TYPE=$2 N=$3; VX=${VX:-2G}; SESS=${SESS:-8}
W=/mydata/s4/r8-w1; H=$W/h; C=$H/ctl.sh; O=$W/runs/$NAME; DV=$W/inst/V
NTV="$W/run-orig/bin/nodetool -h 127.0.0.1 -p 7199"
case $TYPE in T|E) export BUILD=orig;; P) export BUILD=patched;; *) echo "type?"; exit 2;; esac
mkdir -p $O
log(){ echo "[$(TZ=America/New_York date +%T)] $*" | tee -a $O/arm.log; }
cachemib(){ $NTV info 2>/dev/null | grep "^$1 Cache" | sed -E 's/.*size ([0-9.]+) ([A-Za-z]+),.*/\1 \2/' | \
  awk '{v=$1; u=$2; if(u=="KiB")v/=1024; else if(u=="GiB")v*=1024; else if(u=="bytes"||u=="B")v/=1048576; printf "%.2f\n", v}'; }
vpid(){ cat $DV/cass.pid 2>/dev/null; }
# 1. clean slate
pkill -f '[S]2Load'; pkill -f '[S]2CacheFill'; pkill -f '[s]ample.sh'; pkill -f '[S]2Poll'
$C stop V >/dev/null; $C stop R >/dev/null
pgrep -f CassandraDaemon >/dev/null && { echo "CassandraDaemon still running"; exit 1; }
rm -rf $DV $W/rtmp/R; rm -rf $O; mkdir -p $O
log "args: name=$NAME type=$TYPE build=$BUILD N=$N VX=$VX sess=$SESS fill_small=${FILL_SMALL:-0}"
# 2. generate, start V, then R, wait for the ring
$C gen V $VX >> $O/arm.log && $C gen R 8G >> $O/arm.log || { log GENFAIL; exit 1; }
$C start V >> $O/arm.log
for _ in $(seq 90); do (exec 3<>/dev/tcp/127.0.0.2/9042) 2>/dev/null && break; sleep 2; done
$C start R >> $O/arm.log
for _ in $(seq 80); do n=$($NTV status 2>/dev/null | grep -c '^UN'); [ "$n" = 2 ] && break; sleep 3; done
log "ring UN=$n"; [ "$n" = 2 ] || { log RINGFAIL; echo "$NAME: RINGFAIL (void)" > $O/outcome.txt; $C stop V; $C stop R; exit 1; }
# 3. record command line, affinity, resolved budgets, cache capacities
VP=$(vpid); RP=$($C pid R)
ps -o args= -p $VP > $O/V-cmdline.txt
{ echo "V pid $VP $(taskset -cp $VP)"; echo "R pid $RP $(taskset -cp $RP)"
  echo "V resolved: $(tr ' ' '\n' < $O/V-cmdline.txt | grep -E '^-Xm[sx]|MaxDirectMemorySize|^-XX:\+Use.*GC$' | tr '\n' ' ')"
  echo "V VM.flags: $(jcmd $VP VM.flags -all 2>/dev/null | grep -E ' MaxDirectMemorySize | MaxHeapSize ' | awk '{print $2"="$4}' | tr '\n' ' ')"
  echo "V cgroup: $(cat $DV/cgroup) swap.max=$(cat $(cat $DV/cgroup)/memory.swap.max) memory.max=$(cat $(cat $DV/cgroup)/memory.max)"
  grep -E 'cache with capacity' $DV/logs/system.log | sed 's/^.*\] //' | head -4; } >> $O/arm.log 2>&1
cp $DV/yaml.diff $O/V-yaml.diff; cp $W/inst/R/yaml.diff $O/R-yaml.diff
# 4. sampler
( setsid nohup nice -n 10 taskset -c 1-31:2 $H/sample.sh $O < /dev/null > /dev/null 2>&1 & )
# 5. schema + cache fill
$H/client.sh load schema 127.0.0.2 >> $O/arm.log 2>&1
F=1600000; RD=1500000; CT=550000; [ "${FILL_SMALL:-0}" = 1 ] && { F=20000; RD=20000; CT=20000; }
log "fill: insert $F kv"; $H/client.sh fill insert kv 8 0 $F 256 2>&1 | grep -E '^DONE|last error' >> $O/arm.log
$NTV flush s2c; $NTV compact s2c kv
log "fill: read $RD kv"; $H/client.sh fill read kv 8 0 $RD 256 2>&1 | grep -E '^DONE|last error' >> $O/arm.log
log "fill: counter $CT ctr"; $H/client.sh fill counter ctr 8 0 $CT 256 2>&1 | grep -E '^DONE|last error' >> $O/arm.log
$NTV flush s2c
# 6. fill validity
KC=$(cachemib Key); CC=$(cachemib Counter); log "after fill: key cache ${KC} MiB, counter cache ${CC} MiB"
if [ "${FILL_SMALL:-0}" != 1 ]; then
  if awk -v k=$KC -v c=$CC 'BEGIN{exit !(k<99.0 || c<49.5)}'; then
    log "fill short: read 1,500,000..1,600,000 again"; $H/client.sh fill read kv 8 1500000 100000 256 2>&1 | grep -E '^DONE' >> $O/arm.log
    KC=$(cachemib Key); CC=$(cachemib Counter); log "after refill: key ${KC} MiB, counter ${CC} MiB"
    if awk -v k=$KC -v c=$CC 'BEGIN{exit !(k<99.0 || c<49.5)}'; then log FILLFAIL; echo "$NAME: FILLFAIL (void)" > $O/outcome.txt; pkill -f '[s]ample.sh'; pkill -f '[S]2Poll'; $C stop V >> $O/arm.log; $C stop R >> $O/arm.log; exit 1; fi
  fi
fi
# 7. E: invalidate both caches
if [ "$TYPE" = E ]; then $NTV invalidatekeycache; $NTV invalidatecountercache; log "invalidated: key $(cachemib Key) MiB, counter $(cachemib Counter) MiB"; fi
# 8. pre-burst reading (forced full GC: post-fill live heap)
{ echo "== pre-burst nodetool info"; $NTV info | grep -E 'Key Cache|Counter Cache|Heap Memory'
  echo "== tablestats"; $NTV tablestats s2c b6 | grep -E 'Table: |Memtable data size|Memtable cell count|Memtable off heap|Memtable on heap'; } >> $O/arm.log 2>&1
timeout 120 jcmd $VP GC.class_histogram > $O/hist-pre.txt 2>&1
log "pre-burst live heap (histogram total): $(tail -1 $O/hist-pre.txt)"
sleep 10
# 9. burst of exactly N writes
log "burst start N=$N sess=$SESS"; T0=$(date +%s.%N); echo "$T0" > $O/T0
N=$N $H/client.sh load run blob 11000 256 120 0 $(for i in $(seq $SESS); do printf '127.0.0.2,'; done | sed 's/,$//') > $O/load.log 2>&1 &
CPID=$!
for _ in $(seq 150); do kill -0 $CPID 2>/dev/null || break; sleep 1; done
kill $CPID 2>/dev/null; sleep 1; kill -9 $CPID 2>/dev/null
TC=$(date +%s.%N); log "client exited $(awk -v a=$T0 -v b=$TC 'BEGIN{printf "%.0f", b-a}') s after start: $(grep FINAL $O/load.log)"
# 10. observation window 180 s (+180 s once if alive with mut_pending > 1000)
obs(){ for _ in $(seq $1); do kill -0 $VP 2>/dev/null || break; sleep 1; done; }
obs 180
if kill -0 $VP 2>/dev/null; then
  lp=$(tail -1 $O/poll.log | grep -o 'mut_pending=[0-9]*' | cut -d= -f2); log "end of window: V alive, last mut_pending=${lp:-?}"
  [ "${lp:-0}" -gt 1000 ] 2>/dev/null && { log "extend window 180 s"; obs 180; }
fi
# 11. collect
for _ in $(seq 72); do kill -0 $VP 2>/dev/null && ls $DV/dumps/*.hprof >/dev/null 2>&1 || break; sleep 5; done
if kill -0 $VP 2>/dev/null; then
  log V_ALIVE; echo "VmSwap: $(grep VmSwap /proc/$VP/status)" >> $O/arm.log
  timeout 120 jcmd $VP GC.class_histogram > $O/hist-post.txt 2>&1
  $NTV info 2>/dev/null | grep -E 'Key Cache|Counter Cache|Heap Memory' >> $O/arm.log
else log V_DEAD; fi
pkill -f '[s]ample.sh'; pkill -f '[S]2Poll'
cd $DV/logs; cp -p gc.log* system.log launch.log $O/ 2>/dev/null
grep -v CompileCommand launch.log | grep -m3 -B2 -A25 'java\.lang\.OutOfMemoryError' - system.log > $O/oom-excerpt.txt 2>/dev/null
VH=$(( $(echo $VX | tr -d G) * 1024 ))
echo "$NAME: type=$TYPE N=$N V xmx=$VX $(cat system.log launch.log 2>/dev/null | grep -v CompileCommand | grep -c 'java\.lang\.OutOfMemoryError') OOMError lines | $($H/gcpeak.sh . $VH) | $(python3 $H/gcwin.py .)" > $O/outcome.txt
for d in $DV/dumps/*.hprof; do [ -f "$d" ] || continue; ls -l $d > $O/dump.ls; mkdir -p $W/dumps; mv $d $W/dumps/$NAME.hprof; done
cd $W
echo "R: $($H/gcpeak.sh $W/inst/R/logs 8192)" > $O/R-outcome.txt
$C stop V >> $O/arm.log; $C stop R >> $O/arm.log
pgrep -f CassandraDaemon >/dev/null && log "WARN CassandraDaemon left"
log "$(cat $O/outcome.txt) | client: $(grep FINAL $O/load.log) | $(cat $O/R-outcome.txt)"
# 12. table row
python3 $H/table.py $NAME | tee -a $W/runs/batch.log
