#!/usr/bin/env bash
# R11 arm controller, runs on pc96 and drives V ms0611, R1 ms0625, R2 ms0617 (+ client on ms0617) over ssh.
# From S2 run-2 harness-run2/arm.sh + collect.sh and R8 arm.sh; procedure = case file §2.5 steps 1-12.
#   arm.sh <name> <T|P|E> <G|0>
#     T: V build orig, caches kept;  P: V build patched (+104 B/entry weigher), caches kept;  E: V orig, caches invalidated
#   env: VX / RX (V / replica heaps, default 2G), SESS (sessions x 256 in flight, default 8), LOADCAP (s, default 120),
#        FILL_SMALL=1 (shakedown: 20k fill, no validity check)
set -uo pipefail
NAME=$1 TYPE=$2 G=$3; VX=${VX:-2G}; RX=${RX:-2G}; SESS=${SESS:-8}; LOADCAP=${LOADCAP:-120}
W=/mydata/r11; H=$W/h; C=$H/ctl.sh; R=$W/runs/$NAME; E=/mydata/r11-evidence; L=$E/runs/$NAME; PH=$E/h
NT="$W/run-orig/bin/nodetool -h 127.0.0.1 -p 7199"
declare -A HOST=([V]=ms0611 [R1]=ms0625 [R2]=ms0617)
case $TYPE in T|E) BUILD=orig;; P) BUILD=patched;; *) echo "type?"; exit 2;; esac
rm -rf $L; mkdir -p $L
log(){ echo "[$(TZ=America/New_York date +%T)] $*" | tee -a $L/arm.log; }
v(){ ssh ms0611 "$@"; }
cachemib(){ v "$NT info 2>/dev/null" | grep "^$1 Cache" | sed -E 's/.*size ([0-9.]+) ([A-Za-z]+),.*/\1 \2/' | \
  awk '{x=$1; u=$2; if(u=="KiB")x/=1024; else if(u=="GiB")x*=1024; else if(u=="bytes"||u=="B")x/=1048576; printf "%.2f\n", x}'; }
killh(){ # kill harness JVMs/scripts by PID on host $1
  ssh $1 'for p in $(pgrep -u jason92 -f "[S]2Load|[S]2CacheFill|[S]2Poll|[R]11Gate|[s]ample.sh /mydata/r11"); do kill $p 2>/dev/null; done; sleep 1; for p in $(pgrep -u jason92 -f "[S]2Load|[S]2CacheFill|[S]2Poll|[R]11Gate|[s]ample.sh /mydata/r11"); do kill -9 $p 2>/dev/null; done'; }
stopall(){ for n in V R1 R2; do killh ${HOST[$n]}; ssh ${HOST[$n]} "$C stop $n" >> $L/arm.log; done; }
log "args: name=$NAME type=$TYPE V-build=$BUILD G=$G VX=$VX RX=$RX sess=$SESS loadcap=$LOADCAP fill_small=${FILL_SMALL:-0} platform=aarch64"
# 1. clean slate
stopall
for n in V R1 R2; do
  ssh ${HOST[$n]} "pgrep -u jason92 -f [C]assandraDaemon >/dev/null && echo LEFT" | grep -q LEFT && { log "CassandraDaemon still running on ${HOST[$n]}"; exit 1; }
  ssh ${HOST[$n]} "rm -rf $W/inst/$n $R; mkdir -p $R"
done
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
  echo "V cgroup: $(v "cg=\$(cat $W/inst/V/cgroup); echo \$cg swap.max=\$(cat \$cg/memory.swap.max) memory.max=\$(cat \$cg/memory.max)")"
  v "grep -E 'cache with capacity' $W/inst/V/logs/system.log | sed 's/^.*\] //' | head -4"
  echo "V start info:"; v "$NT info 2>/dev/null | grep -E 'Key Cache|Counter Cache'"; } >> $L/arm.log 2>&1
v "cp $W/inst/V/yaml.diff $R/V-yaml.diff"
# 4. samplers on the three nodes, gate on V
for n in V R1 R2; do ssh ${HOST[$n]} "( setsid nohup nice -n 10 bash $H/sample.sh $R $n < /dev/null > /dev/null 2>&1 & )"; done
v "( setsid nohup bash $H/client.sh gate $G 7401 $R/gate.log < /dev/null > $R/gate.out 2>&1 & )"
# 5. cache fill (V only; every arm type)
RD=1500000; CT=550000; [ "${FILL_SMALL:-0}" = 1 ] && { RD=20000; CT=20000; }
log "fill: read $RD kv"; ssh ms0617 "bash $H/client.sh fill read kv 8 0 $RD 256 2>&1" | grep -E '^DONE|^RANGE|last error' | tee -a $L/arm.log | grep -q '^RANGEFAIL' && { log RANGEFAIL; stopall; exit 1; }
log "fill: counter $CT ctr"; ssh ms0617 "bash $H/client.sh fill counter ctr 8 0 $CT 256 2>&1" | grep -E '^DONE|^RANGE|last error' >> $L/arm.log
v "$NT flush s2c"
# 6. fill validity
KC=$(cachemib Key); CC=$(cachemib Counter); log "after fill: key cache ${KC} MiB, counter cache ${CC} MiB"
if [ "${FILL_SMALL:-0}" != 1 ]; then
  if awk -v k=$KC -v c=$CC 'BEGIN{exit !(k<99.0 || c<49.5)}'; then
    log "fill short: read 1,500,000..1,600,000 again"; ssh ms0617 "bash $H/client.sh fill read kv 8 1500000 100000 256 2>&1" | grep -E '^DONE' >> $L/arm.log
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
# 9. burst from ms0617, gated by V's MutationStage pending
HOSTS=$(for i in $(seq $SESS); do printf '10.10.1.4,'; done | sed 's/,$//')
log "burst start G=$G sess=$SESS"
ssh ms0617 "cd $R; ( GATE=10.10.1.4:7401 setsid nohup bash $H/client.sh load run blob 11000 256 $LOADCAP 0 $HOSTS < /dev/null > $R/load.log 2>&1 & echo \$! > $R/load.pid )"
CP=$(ssh ms0617 "cat $R/load.pid")
for _ in $(seq 100); do ssh ms0617 "kill -0 $CP 2>/dev/null" || break; sleep 3; done
ssh ms0617 "kill $CP 2>/dev/null; sleep 1; kill -9 $CP 2>/dev/null"
TC=$(date +%s); echo $TC > $L/TC
log "client exited: $(ssh ms0617 "grep -E '^GATE|^STOP_RECEIVED|^FINAL' $R/load.log" | tr '\n' ' ')"
log "gate: $(v "grep -E '^GATE' $R/gate.log")"
# 10. observation from the client's exit: dead | drained (pending <= 1000 for 30 s) | 480 s (+240 s once if pending > 1000)
obs(){ local lim=$1 t0=$(date +%s) s
  while [ $(( $(date +%s) - t0 )) -lt $lim ]; do
    s=$(v "bash $H/vstate.sh $R/gate.log"); echo "$(date +%s) $s" >> $L/obs.log
    case "$s" in DEAD*) echo DEAD; return;; esac
    m=$(echo "$s" | sed -E 's/.*max30=([0-9]+).*/\1/'); k=$(echo "$s" | sed -E 's/.*n30=([0-9]+).*/\1/')
    [ "$m" -le 1000 ] && [ "$k" -ge 100 ] && { echo DRAINED; return; }
    sleep 5
  done; echo WINDOW; }
st=$(obs 480); log "observation: $st ($(tail -1 $L/obs.log))"
if [ "$st" = WINDOW ]; then
  lp=$(tail -1 $L/obs.log | sed -E 's/.*last=([0-9-]+).*/\1/')
  if [ "${lp:-0}" -gt 1000 ] 2>/dev/null; then log "extend window 240 s"; st=$(obs 240); log "observation (extended): $st ($(tail -1 $L/obs.log))"; [ "$st" = WINDOW ] && st=UNRESOLVED; fi
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
    echo \"$NAME $n: type=$TYPE G=$G xmx=$hx \$(cat system.log launch.log 2>/dev/null | grep -v CompileCommand | grep -c 'java\.lang\.OutOfMemoryError') OOMError lines | \$(bash $H/gcpeak.sh . $hm) | \$(python3 $H/gcwin.py .)\" > $R/outcome.txt; \
    for d in \$I/dumps/*.hprof; do [ -f \"\$d\" ] || continue; ls -l \$d > $R/dump.ls; mkdir -p $W/dumps; mv \$d $W/dumps/$NAME-$n.hprof; done"
done
stopall
for n in V R1 R2; do rsync -a ${HOST[$n]}:$R/ $L/$n/; done
rsync -a --include='load.*' --exclude='*' ms0617:$R/ $L/client/
log "$(cat $L/V/outcome.txt) | obs=$st | client: $(grep FINAL $L/client/load.log) | R1: $(cut -d'|' -f1-2 $L/R1/outcome.txt) | R2: $(cut -d'|' -f1-2 $L/R2/outcome.txt)"
for n in V R1 R2; do ssh ${HOST[$n]} "pgrep -u jason92 -f [C]assandraDaemon >/dev/null && echo LEFT" | grep -q LEFT && log "WARN CassandraDaemon left on ${HOST[$n]}"; done
# dump parse in the background on pc96
[ -f $L/V/dump.ls ] && ( setsid nohup bash $PH/dumpparse.sh $NAME V ms0611 < /dev/null > /dev/null 2>&1 & )
# 12. table row
python3 $PH/table.py $NAME | tee -a $E/batch.log
