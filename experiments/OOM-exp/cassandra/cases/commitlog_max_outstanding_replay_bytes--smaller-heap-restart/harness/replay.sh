#!/usr/bin/env bash
# B15 replayer phase (design 2.5 S0.3): replay.sh <run> <img> <heapMiB> <fault 0|1> [JVM opts]
# write delay 0; vol/data := img/<img>; drop caches; start at <heapMiB>; T_r = 'CommitLog.java:206 - Replaying'.
# fault=1: write delay 30000 ms at T_r, back to 0 at T_r+120 s or when the JVM is gone (also on EXIT).
# T_r+12/+30 s: jcmd Thread.print (amendment A2, 2026-11-18 08:30 EST: also +60/+90 s); T_r+15/+45 s: jcmd GC.class_histogram (every arm). Outcome: started / died / timeout (600 s).
# Dumps are moved to $W/dumps-keep/<run>.hprof (analysed with hprofhist.py after the series; only the first kept).
set -uo pipefail
RUN=$1 IMG=$2 HEAP=$3 FAULT=$4; shift 4; ROPTS="$*"
source /mydata/s4/b15-w3/harness/common.sh
O=$W/runs/$RUN; R=$O/replay; mkdir -p $R/dumps; LOG=$O/arm.log
[ -n "$(dpid)" ] && { log "ABORT: a daemon is running"; exit 1; }
trap '$H/slowdisk.sh set 0 >> $LOG 2>&1' EXIT
log "== replay $RUN img=$IMG heap=${HEAP}M fault=$FAULT opts='$ROPTS' arch=$(uname -m); /mydata free $(df -BG --output=avail /mydata | tail -1)"
$H/slowdisk.sh set 0 >> $LOG
rm -rf $W/vol/data/*; cp -a $W/img/$IMG/. $W/vol/data/; sync; sudo sh -c 'echo 3 > /proc/sys/vm/drop_caches'
log "data restored from img/$IMG ($(du -sm $W/vol/data | cut -f1) MiB; commitlog $(ls $W/vol/data/commitlog | wc -l) files)"
rm -rf $C/logs; mkdir -p $C/logs
start_node $R $HEAP b15-$RUN $ROPTS
PID=$P
grep -m1 -oE 'MaxDirectMemorySize=[0-9]+[A-Za-z]*|-XX:MaxDirectMemorySize=[0-9]+[A-Za-z]*' $R/stdout.txt >> $LOG 2>/dev/null
T1=$(date +%s); OUT=timeout; TREP=; FON=0
while [ $(( $(date +%s) - T1 )) -lt 600 ]; do
  if grep -q 'Starting listening for CQL clients' $C/logs/system.log 2>/dev/null; then OUT=started; break; fi
  if [ -z "$TREP" ] && grep -q 'CommitLog.java:206 - Replaying' $C/logs/system.log 2>/dev/null; then
    TREP=$(date +%s); log "Replaying seen (T_r) at +$((TREP-T1))s after JVM start"
    if [ $FAULT = 1 ]; then $H/slowdisk.sh set 30000 >> $LOG; FON=1; fi
  fi
  if [ -n "$TREP" ]; then
    e=$(( $(date +%s) - TREP ))
    for s in 12 30 60 90; do if [ $e -ge $s ] && [ ! -f $R/threads-$s.txt ]; then ( timeout 60 jcmd $PID Thread.print > $R/threads-$s.txt 2>&1 ) & sleep 0.2; fi; done
    for s in 15 45; do if [ $e -ge $s ] && [ ! -f $R/histo-$s.txt ]; then ( timeout 180 jcmd $PID GC.class_histogram > $R/histo-$s.txt 2>&1; log "histogram +${s}s: total $(awk '/^Total/{printf "%.0f MiB", $3/1048576}' $R/histo-$s.txt) live; Mutation n=$(awk '$4=="org.apache.cassandra.db.Mutation"{print $2}' $R/histo-$s.txt)" ) & sleep 0.2; fi; done
    if [ $FON = 1 ] && [ $e -ge 120 ]; then $H/slowdisk.sh set 0 >> $LOG; FON=0; fi
  fi
  if ! kill -0 $PID 2>/dev/null; then OUT=died; break; fi
  sleep 1
done
[ $FON = 1 ] && { $H/slowdisk.sh set 0 >> $LOG; FON=0; }
log "outcome=$OUT after $(( $(date +%s) - T1 ))s from JVM start${TREP:+ ($(( $(date +%s) - TREP ))s from T_r)}"
sleep 2
grep -hE 'Replaying|Log replay complete|OutOfMemory|Dumping heap|Heap dump file|ERROR' $C/logs/system.log $R/stdout.txt 2>/dev/null | grep -v CompileCommand | cut -c1-260 | head -12 | tee -a $LOG
tail -1 $R/memcur.txt >/dev/null 2>&1
grep -h . $R/memevents.txt 2>/dev/null | tail -1 | sed 's/^/memory.events (last sample): /' | tee -a $LOG
[ $OUT = started ] && $C/bin/nodetool tablestats b8.t_map 2>/dev/null | grep -E 'Memtable (cell count|data size)|SSTable count' >> $R/stats.txt
stop_node; sleep 1
cp $C/logs/system.log $C/logs/debug.log $C/logs/gc.log* $R/ 2>/dev/null
python3 $H/gcsum.py $R/gc.log > $R/gcsum.txt 2>&1
log "replay gc: $(tail -1 $R/gcsum.txt)"
log "mem.current max: $(sort -k2 -n $R/memcur.txt | tail -1 | cut -d' ' -f2) B"
for f in 12 30 60 90; do [ -f $R/threads-$f.txt ] && log "threads +${f}s: flushwriter_in_force=$(awk '/^"MemtableFlushWriter/{t=1} /^$/{t=0} t&&/FileChannelImpl.force|fsync|force0/{print; t=0}' $R/threads-$f.txt | wc -l) flushwriters=$(grep -c '^"MemtableFlushWriter' $R/threads-$f.txt) mutstage=$(grep -c '^"MutationStage' $R/threads-$f.txt) mutstage_in_suballoc=$(awk '/^"MutationStage/{t=1} /^$/{t=0} t&&/SubAllocator.allocate/{print; t=0}' $R/threads-$f.txt | wc -l) main=$(awk '/^"main"/{t=1;n=0} t{n++; if(n==3){print $2; t=0}}' $R/threads-$f.txt)"; done
mkdir -p $W/dumps-keep
for f in $R/dumps/*.hprof; do [ -f "$f" ] || continue
  if [ ! -e $W/dumps-keep/FIRST ]; then mv "$f" $W/dumps-keep/$RUN.hprof; echo $RUN > $W/dumps-keep/FIRST; log "dump kept as dumps-keep/$RUN.hprof ($(du -m $W/dumps-keep/$RUN.hprof | cut -f1) MiB)"
  else log "dump $(du -m $f | cut -f1) MiB deleted unread"; rm -f "$f"; fi
done
log "left: daemon=$(pgrep -fc '[o]rg.apache.cassandra.service.CassandraDaemon') client=$(pgrep -fc '[B]8Load')"
log "== RESULT $RUN img=$IMG heap=$HEAP fault=$FAULT opts='$ROPTS' outcome=$OUT"
