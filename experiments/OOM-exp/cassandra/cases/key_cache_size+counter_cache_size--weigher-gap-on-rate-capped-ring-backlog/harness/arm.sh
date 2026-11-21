#!/usr/bin/env bash
# R19 arm controller (from R11 arm.sh), runs on pc96 and drives V ms0611, R1 ms0625, R2 ms0617 and the client ms0604
# over ssh. Procedure = R11 §2.5 steps 1-12 with R19's burst (case file §2.5): rate cap r and fixed total N.
#   arm.sh <name> <T|P|E> <N>      (N = 0: no total, the burst runs to LOADCAP)
#     T: V build orig, caches kept;  P: V build patched (+104 B/entry weigher), caches kept;  E: V orig, caches invalidated
#   env: RATE (r writes/s, empty = uncapped), CL (default ONE), LOADCAP (s, default ceil(N/RATE)+60, or 120),
#        VX / RX (V / replica heaps, default 2G), SESS (sessions x 256 in flight, default 8),
#        FILL_SMALL=1 (shakedown: 20k fill, no validity check)
set -uo pipefail
NAME=$1 TYPE=$2 N=$3; VX=${VX:-2G}; RX=${RX:-2G}; SESS=${SESS:-8}; RATE=${RATE:-}; CL=${CL:-ONE}
if [ -z "${LOADCAP:-}" ]; then
  if [ -n "$RATE" ] && [ "$N" -gt 0 ]; then LOADCAP=$(( (N + RATE - 1) / RATE + 60 )); else LOADCAP=120; fi
fi
W=/mydata/r19; H=$W/h; C=$H/ctl.sh; R=$W/runs/$NAME; E=/mydata/r19-evidence; L=$E/runs/$NAME; PH=$E/h
NT="$W/run-orig/bin/nodetool -h 127.0.0.1 -p 7199"
CLI=ms0604
declare -A HOST=([V]=ms0611 [R1]=ms0625 [R2]=ms0617)
case $TYPE in T|E) BUILD=orig;; P) BUILD=patched;; *) echo "type?"; exit 2;; esac
rm -rf $L; mkdir -p $L
log(){ echo "[$(TZ=America/New_York date +%T)] $*" | tee -a $L/arm.log; }
v(){ ssh ms0611 "$@"; }
cachemib(){ v "$NT info 2>/dev/null" | grep "^$1 Cache" | sed -E 's/.*size ([0-9.]+) ([A-Za-z]+),.*/\1 \2/' | \
  awk '{x=$1; u=$2; if(u=="KiB")x/=1024; else if(u=="GiB")x*=1024; else if(u=="bytes"||u=="B")x/=1048576; printf "%.2f\n", x}'; }
killh(){ # kill this case's harness JVMs/scripts by PID on host $1 (all run from /mydata/r19/cls or /mydata/r19/h/)
  ssh $1 'for p in $(pgrep -u jason92 -f "[/]mydata/r19/(cls|h/)"); do kill $p 2>/dev/null; done; sleep 1; for p in $(pgrep -u jason92 -f "[/]mydata/r19/(cls|h/)"); do kill -9 $p 2>/dev/null; done'; }
stopall(){ killh $CLI; for n in V R1 R2; do killh ${HOST[$n]}; ssh ${HOST[$n]} "$C stop $n" >> $L/arm.log; done; }
log "args: name=$NAME type=$TYPE V-build=$BUILD N=$N rate=${RATE:-uncapped} CL=$CL VX=$VX RX=$RX sess=$SESS loadcap=$LOADCAP fill_small=${FILL_SMALL:-0} platform=aarch64 client=$CLI"
# 1. clean slate
stopall
for n in V R1 R2; do
  ssh ${HOST[$n]} "pgrep -u jason92 -f [C]assandraDaemon >/dev/null && echo LEFT" | grep -q LEFT && { log "CassandraDaemon still running on ${HOST[$n]}"; exit 1; }
  ssh ${HOST[$n]} "rm -rf $W/inst/$n $R; mkdir -p $R"
done
ssh $CLI "rm -rf $R; mkdir -p $R"
# 2. restore golden state, start V, then R1 and R2, wait for UN=3
v "BUILD=$BUILD $C restore V $VX" >> $L/arm.log && ssh ms0625 "$C restore R1 $RX" >> $L/arm.log && ssh ms0617 "$C restore R2 $RX" >> $L/arm.log || { log GENFAIL; exit 1; }
v "$C start V" >> $L/arm.log
for _ in $(seq 90); do v "(exec 3<>/dev/tcp/10.10.1.4/9042) 2>/dev/null" && break; sleep 2; done
ssh ms0625 "$C start R1" >> $L/arm.log & ssh ms0617 "$C start R2" >> $L/arm.log & wait
for _ in $(seq 100); do nu=$(v "$NT status 2>/dev/null | grep -c '^UN'"); [ "$nu" = 3 ] && break; sleep 3; done
log "ring UN=$nu"; [ "$nu" = 3 ] || { log RINGFAIL; echo "$NAME: RINGFAIL (void)" > $L/outcome.txt; stopall; exit 1; }
# 3. record command line, resolved budgets, cache capacities, cache entries at start
VP=$(v "cat $W/inst/V/cass.pid")
v "ps -o args= -p $VP" > $L/V-cmdline.txt
{ echo "V pid $VP build $(v "cat $W/inst/V/build") jar md5 $(v "md5sum \$(cat $W/inst/V/build)/build/apache-cassandra-5.0.9-SNAPSHOT.jar | cut -c1-12")"
  echo "V resolved: $(tr ' ' '\n' < $L/V-cmdline.txt | grep -E '^-Xm[sx]|MaxDirectMemorySize|^-XX:\+Use.*GC$' | tr '\n' ' ')"
  echo "V VM.flags: $(v "jcmd $VP VM.flags -all 2>/dev/null" | grep -E ' MaxDirectMemorySize | MaxHeapSize ' | awk '{print $2"="$4}' | tr '\n' ' ')"
  echo "V VM.uptime at $(date +%s%3N): $(v "jcmd $VP VM.uptime 2>/dev/null | tail -1")"
  echo "V cgroup: $(v "cg=\$(cat $W/inst/V/cgroup); echo \$cg swap.max=\$(cat \$cg/memory.swap.max) memory.max=\$(cat \$cg/memory.max)")"
  v "grep -E 'cache with capacity' $W/inst/V/logs/system.log | sed 's/^.*\] //' | head -4"
  echo "V start info:"; v "$NT info 2>/dev/null | grep -E 'Key Cache|Counter Cache'"; } >> $L/arm.log 2>&1
v "cp $W/inst/V/yaml.diff $R/V-yaml.diff"
# 4. samplers on the three nodes, gate on V as a pending logger only (G = 0: never sends STOP)
for n in V R1 R2; do ssh ${HOST[$n]} "( setsid nohup nice -n 10 bash $H/sample.sh $R $n < /dev/null > /dev/null 2>&1 & )"; done
v "( setsid nohup bash $H/client.sh gate 0 7401 $R/gate.log < /dev/null > $R/gate.out 2>&1 & )"
# 5. cache fill (V only; every arm type), from the client node
RD=1500000; CT=550000; [ "${FILL_SMALL:-0}" = 1 ] && { RD=20000; CT=20000; }
log "fill: read $RD kv"; ssh $CLI "bash $H/client.sh fill read kv 8 0 $RD 256 2>&1" | grep -E '^DONE|^RANGE|last error' | tee -a $L/arm.log | grep -q '^RANGEFAIL' && { log RANGEFAIL; stopall; exit 1; }
log "fill: counter $CT ctr"; ssh $CLI "bash $H/client.sh fill counter ctr 8 0 $CT 256 2>&1" | grep -E '^DONE|^RANGE|last error' >> $L/arm.log
v "$NT flush s2c"
# 6. fill validity
KC=$(cachemib Key); CC=$(cachemib Counter); log "after fill: key cache ${KC} MiB, counter cache ${CC} MiB"
if [ "${FILL_SMALL:-0}" != 1 ]; then
  if awk -v k=$KC -v c=$CC 'BEGIN{exit !(k<99.0 || c<49.5)}'; then
    log "fill short: read 1,500,000..1,600,000 again"; ssh $CLI "bash $H/client.sh fill read kv 8 1500000 100000 256 2>&1" | grep -E '^DONE' >> $L/arm.log
    KC=$(cachemib Key); CC=$(cachemib Counter); log "after refill: key ${KC} MiB, counter ${CC} MiB"
    if awk -v k=$KC -v c=$CC 'BEGIN{exit !(k<99.0 || c<49.5)}'; then log FILLFAIL; echo "$NAME: FILLFAIL (void)" > $L/outcome.txt; stopall; exit 1; fi
  fi
fi
# 7. E: invalidate both caches
if [ "$TYPE" = E ]; then v "$NT invalidatekeycache; $NT invalidatecountercache"; log "invalidated: key $(cachemib Key) MiB, counter $(cachemib Counter) MiB"; fi
# 8. pre-burst reading (forced full GC: the component-alone live heap)
{ echo "== pre-burst nodetool info"; v "$NT info" | grep -E 'Key Cache|Counter Cache|Heap Memory'
  echo "== tablestats"; v "$NT tablestats s2c b6" | grep -E 'Table: |Memtable data size|Memtable cell count|Memtable off heap|Memtable on heap'; } >> $L/arm.log 2>&1
v "timeout 180 jcmd $VP GC.class_histogram > $R/hist-pre.txt 2>&1"
log "pre-burst live heap (histogram total): $(v "tail -1 $R/hist-pre.txt")"
sleep 10
# 9. burst from the client: rate cap RATE, total N (TOTAL_REACHED = STOP), time cap LOADCAP
HOSTS=$(for i in $(seq $SESS); do printf '10.10.1.4,'; done | sed 's/,$//')
TOT=""; [ "$N" -gt 0 ] && TOT="TOTAL=$N"
log "burst start N=$N rate=${RATE:-uncapped} CL=$CL loadcap=$LOADCAP sess=$SESS"
ssh $CLI "cd $R; ( CL=$CL $TOT setsid nohup bash $H/client.sh load run blob 11000 256 $LOADCAP 0 $HOSTS $RATE < /dev/null > $R/load.log 2>&1 & echo \$! > $R/load.pid )"
CP=$(ssh $CLI "cat $R/load.pid")
for _ in $(seq 120); do ssh $CLI "kill -0 $CP 2>/dev/null" || break; sleep 3; done
ssh $CLI "kill $CP 2>/dev/null; sleep 1; kill -9 $CP 2>/dev/null"
TC=$(date +%s); echo $TC > $L/TC
log "client exited: $(ssh $CLI "grep -E '^TOTAL_REACHED|^FIRST_SEND|^FINAL' $R/load.log" | tr '\n' ' ')"
# 10. observation from the client's exit: dead | drained (pending <= 1000 for 30 s) | 300 s (+180 s once if pending > 1000)
obs(){ local lim=$1 t0=$(date +%s) s
  while [ $(( $(date +%s) - t0 )) -lt $lim ]; do
    s=$(v "bash $H/vstate.sh $R/gate.log"); echo "$(date +%s) $s" >> $L/obs.log
    case "$s" in DEAD*) echo DEAD; return;; esac
    m=$(echo "$s" | sed -E 's/.*max30=([0-9]+).*/\1/'); k=$(echo "$s" | sed -E 's/.*n30=([0-9]+).*/\1/')
    [ "$m" -le 1000 ] && [ "$k" -ge 100 ] && { echo DRAINED; return; }
    sleep 5
  done; echo WINDOW; }
st=$(obs 300); log "observation: $st ($(tail -1 $L/obs.log))"
if [ "$st" = WINDOW ]; then
  lp=$(tail -1 $L/obs.log | sed -E 's/.*last=([0-9-]+).*/\1/')
  if [ "${lp:-0}" -gt 1000 ] 2>/dev/null; then log "extend window 180 s"; st=$(obs 180); log "observation (extended): $st ($(tail -1 $L/obs.log))"; [ "$st" = WINDOW ] && st=UNRESOLVED; fi
fi
echo "$st" > $L/obs-result
# 11. collect
for _ in $(seq 72); do v "kill -0 $VP 2>/dev/null && ls $W/inst/V/dumps/*.hprof >/dev/null 2>&1 && ! grep -q 'Heap dump file created' $W/inst/V/logs/launch.log $W/inst/V/logs/system.log 2>/dev/null" || break; sleep 5; done
for n in V R1 R2; do
  hx=$([ $n = V ] && echo $VX || echo $RX); hm=$(( $(echo $hx | tr -d G) * 1024 ))
  ssh ${HOST[$n]} "I=$W/inst/$n; kill -0 \$(cat \$I/cass.pid) 2>/dev/null && echo ${n}_ALIVE || echo ${n}_DEAD" | tee -a $L/arm.log
  [ $n = V ] && v "kill -0 $VP 2>/dev/null && { grep VmSwap /proc/$VP/status; $NT info 2>/dev/null | grep -E 'Key Cache|Counter Cache|Heap Memory'; }" >> $L/arm.log 2>&1
  ssh ${HOST[$n]} "I=$W/inst/$n; cd \$I/logs; cp -p gc.log* system.log launch.log ../yaml.diff ../cgroup $R/ 2>/dev/null; \
    cat launch.log system.log 2>/dev/null | grep -v CompileCommand | grep -m3 -B2 -A25 'java\.lang\.OutOfMemoryError' > $R/oom-excerpt.txt; \
    echo \"$NAME $n: type=$TYPE N=$N rate=${RATE:-uncapped} xmx=$hx \$(cat system.log launch.log 2>/dev/null | grep -v CompileCommand | grep -c 'java\.lang\.OutOfMemoryError') OOMError lines | \$(bash $H/gcpeak.sh . $hm) | \$(python3 $H/gcwin.py .)\" > $R/outcome.txt; \
    for d in \$I/dumps/*.hprof; do [ -f \"\$d\" ] || continue; ls -l \$d > $R/dump.ls; mkdir -p $W/dumps; mv \$d $W/dumps/$NAME-$n.hprof; done"
done
stopall
for n in V R1 R2; do rsync -a ${HOST[$n]}:$R/ $L/$n/; done
rsync -a --include='load.*' --exclude='*' $CLI:$R/ $L/client/
python3 $PH/hstop.py $L > $L/hstop.txt 2>&1
log "$(cat $L/V/outcome.txt) | obs=$st | client: $(grep -E '^TOTAL_REACHED|^FINAL' $L/client/load.log | tr '\n' ' ') | hstop: $(cat $L/hstop.txt) | R1: $(cut -d'|' -f1-2 $L/R1/outcome.txt) | R2: $(cut -d'|' -f1-2 $L/R2/outcome.txt)"
for n in V R1 R2; do ssh ${HOST[$n]} "pgrep -u jason92 -f [C]assandraDaemon >/dev/null && echo LEFT" | grep -q LEFT && log "WARN CassandraDaemon left on ${HOST[$n]}"; done
# dump parse in the background on pc96
[ -f $L/V/dump.ls ] && ( setsid nohup bash $PH/dumpparse.sh $NAME V ms0611 < /dev/null > /dev/null 2>&1 & )
# 12. table row
python3 $PH/table.py $NAME | tee -a $E/batch.log
