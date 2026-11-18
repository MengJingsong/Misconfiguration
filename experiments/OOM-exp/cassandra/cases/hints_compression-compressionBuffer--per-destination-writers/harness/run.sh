#!/usr/bin/env bash
# C5 stage 2: one run from the template (clean start). Runs on ms0604 under setsid nohup.
#   run.sh <run> <D MiB> <k ranges> <lz4|none> <btm 0|1> <patch 0|1> <dump 0|1> [W=62]
# N (destinations) = k + 2. Writes: W x 15,728,640 B random blobs, one in flight, LOCAL_ONE, ranges 0..k-1 cycling.
set -uo pipefail
. /mydata/s4/c5-w1/h/env.sh
RUN=$1 D=$2 K=$3 MODE=$4 BTM=$5 PATCH=$6 DUMP=$7 W=${8:-62}
R=$RUNS/$RUN; rm -rf $R; mkdir -p $R; exec >> $R/run.log 2>&1
log "run $RUN D=${D}MiB k=$K N=$((K+2)) mode=$MODE btm=$BTM patch=$PATCH dump=$DUMP W=$W platform=$(uname -m)"
echo "D=$D k=$K N=$((K+2)) mode=$MODE btm=$BTM patch=$PATCH dump=$DUMP W=$W" > $R/argline
# 1. clean start from the template
$H/ctl.sh stop A > /dev/null 2>&1
EXTRA=(); [ "$MODE" = lz4 ] && EXTRA=("hints_compression=[{class_name: LZ4Compressor}]")
$H/ctl.sh gen A $D "${EXTRA[@]}" || exit 1
rm -rf $INST/A/data $INST/A/commitlog $INST/A/hints $INST/A/saved_caches; mkdir -p $INST/A/hints
cp -a $TPL/data $TPL/commitlog $TPL/saved_caches $INST/A/
if [ "$PATCH" = 1 ]; then cp -r $ROOT/patch/classes/org $INST/A/conf/; javap -p -cp $INST/A/conf org.apache.cassandra.hints.CompressedHintsWriter > $R/javap-patch.txt; fi
cp $INST/A/yaml.diff $R/A-yaml.diff
JX=""; [ "$BTM" = 1 ] && JX="-javaagent:$J/byteman-4.0.20.jar=boot:$J/byteman-4.0.20.jar,script:$H/c5.btm -Dorg.jboss.byteman.transform.all=true -Dc5.trace=$R/c5.trace"
JEXTRA="$JX" DUMPDIR=$R $H/ctl.sh start A
TSTART=$(date +%s); VPID=$($H/ctl.sh pid A); echo "vpid=$VPID tstart=$TSTART" >> $R/argline
# per-run limit: 12 min from the A start
( sleep 720; if [ ! -f $R/.done ] && kill -0 $VPID 2>/dev/null; then echo "OVERRUN: killing A" >> $R/run.log; touch $R/.overrun; kill -9 $VPID; fi ) < /dev/null > /dev/null 2>&1 &
WD=$!
for _ in $(seq 150); do (exec 3<>/dev/tcp/127.0.5.1/9042) 2>/dev/null && break; kill -0 $VPID 2>/dev/null || break; sleep 2; done
(exec 3<>/dev/tcp/127.0.5.1/9042) 2>/dev/null || { log "A START FAIL"; echo "$RUN INVALID start-fail" > $R/outcome.txt; touch $R/.done; $H/ctl.sh stop A; exit 1; }
log "A up after $(( $(date +%s) - TSTART ))s"
jcmd $VPID VM.flags 2>/dev/null | tr ' ' '\n' | grep -E "MaxDirectMemorySize|MaxHeapSize|UseG1GC" > $R/A-flags.txt
tr '\0' '\n' < /proc/$VPID/cmdline > $R/A-cmdline.txt
cat $(cat $INST/A/cgroup)/memory.swap.max > $R/A-swapmax.txt 2>/dev/null
# 2. samplers (1 s): JMX direct/heap/hints, RssAnon
( exec java -Xmx128m -cp "$CP" C5Sample loop 1000 $R/samples.csv ) < /dev/null > $R/sampler.err 2>&1 &
SP=$!
( echo epoch_ms,rss_anon_kb > $R/rss.csv; while kill -0 $VPID 2>/dev/null; do echo $(date +%s%3N),$(awk '/^RssAnon/{print $2}' /proc/$VPID/status 2>/dev/null) >> $R/rss.csv; sleep 1; done ) < /dev/null > /dev/null 2>&1 &
RP=$!
# 3. M0 baseline
$NT status > $R/status-M0.txt 2>&1
DN=$(awk '/Datacenter: dc2/{f=1} /Datacenter: dc1/{f=0} f && /^DN/' $R/status-M0.txt | wc -l)
UN2=$(awk '/Datacenter: dc2/{f=1} /Datacenter: dc1/{f=0} f && /^UN/' $R/status-M0.txt | wc -l)
log "M0 dc2 DN=$DN UN=$UN2"
sleep 30; jcmd $VPID GC.run > /dev/null; sleep 10; jcmd $VPID GC.run > /dev/null; sleep 10
B0=$(java -Xmx64m -cp "$CP" C5Sample once); log "M0 B0 [direct_used count cap heap hints ...] = $B0"
echo "B0 $B0" >> $R/marks.txt; echo "dc2_DN_M0 $DN" >> $R/marks.txt
# 4. load
log "load start"; echo "load_start $(date +%s%3N)" >> $R/marks.txt
java -Xmx512m -cp "$CP" -Dlogback.configurationFile=$H/logback-quiet.xml C5Load run $ROOT/keys.txt $K $W 15728640 5 $R/client.csv > $R/client.log 2>&1
echo "load_end $(date +%s%3N)" >> $R/marks.txt; log "load end: $(tail -1 $R/client.log)"
# 5. M1 plateau (surviving runs)
if kill -0 $VPID 2>/dev/null; then
  sleep 15; jcmd $VPID GC.run > /dev/null; sleep 10; jcmd $VPID GC.run > /dev/null; sleep 2
  echo "m1_ms $(date +%s%3N)" >> $R/marks.txt; M1=$(java -Xmx64m -cp "$CP" C5Sample once); log "M1 [direct_used count cap heap hints ...] = $M1"; echo "M1 $M1" >> $R/marks.txt
  for rr in 0 1 31; do kk=$(awk -v r=$rr '$1==r{print $2}' $ROOT/keys.txt); echo "range $rr key $kk:" $($NT getendpoints c5 t $kk 2>&1) >> $R/getendpoints.txt; done
  [ "$DUMP" = 1 ] && { jcmd $VPID GC.heap_dump $R/plateau.hprof > /dev/null 2>&1; log "dump plateau.hprof"; }
  ls $INST/A/hints | wc -l > $R/hints-files.txt; du -sk $INST/A/hints >> $R/hints-files.txt
else
  log "A is gone (pid $VPID)"
  for _ in $(seq 60); do ls $R/*.hprof > /dev/null 2>&1 && break; sleep 2; done
fi
touch $R/.done; kill $WD 2>/dev/null
# 6. collect, stop
mkdir -p $R/A-logs; cp -p $INST/A/logs/system.log $INST/A/logs/debug.log $INST/A/logs/gc.log* $INST/A/logs/launch.log $INST/A/logs/hs_err* $R/A-logs/ 2>/dev/null
st=DEAD; kill -0 $VPID 2>/dev/null && st=alive; [ -f $R/.overrun ] && st=OVERRUN
$H/ctl.sh stop A; kill $SP $RP 2>/dev/null
grep -q "letting the JVM handle the error" $R/A-logs/system.log 2>/dev/null; jh=$?
oomd=$(grep -c "OutOfMemoryError: Direct buffer memory" $R/A-logs/system.log 2>/dev/null)
oomh=$(grep -c "OutOfMemoryError: Java heap space" $R/A-logs/system.log 2>/dev/null)
oomn=$(grep -c "OutOfDirectMemoryError" $R/A-logs/system.log 2>/dev/null)
fsw=$(grep -c "FSWriteError" $R/A-logs/system.log 2>/dev/null)
grep -v "JVM Arguments" $R/A-logs/system.log | grep -n -m1 -B5 -A45 "OutOfMemoryError\|OutOfDirectMemoryError" > $R/first-oom.txt 2>/dev/null
python3 $H/summary.py $R > $R/summary.txt 2>&1
echo "$RUN | $(cat $R/argline | head -1) | A=$st letting_jvm=$([ $jh = 0 ] && echo yes || echo no) directOOM=$oomd heapOOM=$oomh nettyOOM=$oomn FSWriteError=$fsw | $(grep -E '^(clients|trace|samples|marks):' $R/summary.txt | tr '\n' ' ')" > $R/outcome.txt
cat $R/outcome.txt >> $RUNS/summary-all.txt
rm -rf $INST/A/data $INST/A/commitlog $INST/A/hints $INST/A/saved_caches
log "DONE $(cat $R/outcome.txt)"
