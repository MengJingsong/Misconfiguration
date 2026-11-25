#!/usr/bin/env bash
# R23 restore arm (design 2.5 "Restore arm"): restore.sh <run> <img> <heapMiB> <D ms> <T|C> [JVM opts]
# D = 0; refill vol/data, commitlog, archive from img/<img>; operator restore of b8.t_map from snapshot r23base;
# restore properties with PIT_T (T) or PIT_C (C); drop caches; write delay D; start at <heapMiB>.
# T_r = first 'CommitLog.java:206 - Replaying'. Thread dumps at T_r+8/12/20/30/60/90 s, class histograms at T_r+5/15/45 s.
# Amendment A1 (2026-11-24 09:35 EST, after K100): jcmd pre-attach at JVM start; extra thread dumps at T_r+1..6 s and
# extra histograms at T_r+2/3 s (K100 died at ~T_r+5 s; its Attach Listener could not start in the full heap).
# Outcome started / died / timeout (900 s from JVM start). D back to 0 only after the JVM is gone (also on EXIT).
# First OOM dump of a T* or U* run kept in dumps-keep/; other dumps deleted unread.
set -uo pipefail
RUN=$1 IMG=$2 HEAP=$3 DMS=$4 KIND=$5; shift 5; ROPTS="$*"
source /mydata/s4/r23/harness/common.sh
O=$W/runs/$RUN; rm -rf $O; mkdir -p $O/dumps; LOG=$O/arm.log
[ -n "$(dpid)" ] && { log "ABORT: a daemon is running"; exit 1; }
trap 'stop_node; $H/slowdisk.sh set 0 >> $LOG 2>&1' EXIT
log "== restore $RUN img=$IMG heap=${HEAP}M D=${DMS}ms PIT=$KIND opts='$ROPTS' arch=$(uname -m); /mydata free $(df -BG --output=avail /mydata | tail -1)"
$H/slowdisk.sh set 0 >> $LOG
rm -rf $W/vol/data/* $C/data/commitlog/* $C/data/hints/* $C/data/saved_caches/* $W/archive/*
cp -a --sparse=always $W/img/$IMG/data/. $W/vol/data/; cp -a $W/img/$IMG/commitlog/. $C/data/commitlog/; cp -a $W/img/$IMG/archive/. $W/archive/
source $W/img/$IMG/pit.env
log "refilled from img/$IMG: data $(du -sm $W/vol/data | cut -f1) MiB; commitlog $(ls $C/data/commitlog | wc -l) files; archive $(ls $W/archive | wc -l) files $(du -sm $W/archive | cut -f1) MiB"
# operator restore of the table from its snapshot (documented snapshot restore)
TD=$(ls -d $W/vol/data/b8/t_map-*)
ls -la $TD > $O/table-before.txt
find $TD -maxdepth 1 -type f -delete
for f in $TD/snapshots/r23base/*; do case $(basename $f) in manifest.json|schema.cql) ;; *) cp -a $f $TD/ ;; esac; done
ls -la $TD > $O/table-after.txt
log "table restored from snapshot: $(ls $TD/*-Data.db 2>/dev/null | wc -l) sstables ($(du -cm $TD/*-Data.db | tail -1 | cut -f1) MiB Data.db)"
if [ $KIND = T ]; then PIT=$PIT_T; else PIT=$PIT_C; fi
sed "s|@PIT@|$PIT|" $H/archiving-restore.properties.in > $C/conf/commitlog_archiving.properties
log "commitlog_archiving.properties: $(grep -v '^#' $C/conf/commitlog_archiving.properties | tr '\n' ' ')"
sync; sudo sh -c 'echo 3 > /proc/sys/vm/drop_caches'
$H/slowdisk.sh set $DMS >> $LOG
rm -rf $C/logs; mkdir -p $C/logs
start_node $O $HEAP r23-$RUN $ROPTS
PID=$P
# amendment A1 (2026-11-24): attach once right after JVM start so the Attach Listener exists before the heap fills
# amendment A2 (2026-11-24 09:55 EST): attach only after CassandraDaemon logged 'JVM Arguments' (signal handlers installed);
# an earlier SIGQUIT from jcmd during JVM init (heap pre-touch) killed T3/I3/U1536/U2048a within 1 s (invalid arms).
( for i in $(seq 1 120); do grep -q 'JVM Arguments' $C/logs/system.log 2>/dev/null && break; sleep 0.25; done
  for i in $(seq 1 40); do timeout 15 jcmd $PID VM.uptime > $O/preattach.txt 2>&1 && { log "pre-attach ok after ${i} tries"; break; }; sleep 0.5; done ) &
T1=$(date +%s); OUT=timeout; TREP=
while [ $(( $(date +%s) - T1 )) -lt 900 ]; do
  if grep -q 'Starting listening for CQL clients' $C/logs/system.log 2>/dev/null; then OUT=started; break; fi
  if [ -z "$TREP" ] && grep -q 'CommitLog.java:206 - Replaying' $C/logs/system.log 2>/dev/null; then
    TREP=$(date +%s); log "Replaying seen (T_r) at +$((TREP-T1))s after JVM start"
  fi
  if [ -n "$TREP" ]; then
    e=$(( $(date +%s) - TREP ))
    for s in 1 2 3 4 5 6 8 12 20 30 60 90; do if [ $e -ge $s ] && [ ! -f $O/threads-$s.txt ]; then ( timeout 60 jcmd $PID Thread.print > $O/threads-$s.txt 2>&1 ) & sleep 0.2; fi; done
    for s in 2 3 5 15 45; do if [ $e -ge $s ] && [ ! -f $O/histo-$s.txt ]; then ( timeout 180 jcmd $PID GC.class_histogram > $O/histo-$s.txt 2>&1; log "histogram +${s}s: total $(awk '/^Total/{printf "%.0f MiB", $3/1048576}' $O/histo-$s.txt) live; Mutation n=$(awk '$4=="org.apache.cassandra.db.Mutation"{print $2}' $O/histo-$s.txt) ArrayCell n=$(awk '$4=="org.apache.cassandra.db.rows.ArrayCell"{print $2}' $O/histo-$s.txt) BufferCell n=$(awk '$4=="org.apache.cassandra.db.rows.BufferCell"{print $2}' $O/histo-$s.txt) byte[]=$(awk '$4=="[B"{printf "%.0f MiB", $3/1048576}' $O/histo-$s.txt)" ) & sleep 0.2; fi; done
  fi
  if ! kill -0 $PID 2>/dev/null; then OUT=died; break; fi
  sleep 0.5
done
log "outcome=$OUT after $(( $(date +%s) - T1 ))s from JVM start${TREP:+ ($(( $(date +%s) - TREP ))s from T_r)}"
sleep 2
grep -hE 'Replaying|Log replay complete|Skipping restore|OutOfMemory|Dumping heap|Heap dump file|ERROR' $C/logs/system.log $O/stdout.txt 2>/dev/null | grep -v CompileCommand | cut -c1-300 | head -14 | tee -a $LOG
grep -h . $O/memevents.txt 2>/dev/null | tail -1 | sed 's/^/memory.events (last sample): /' | tee -a $LOG
[ $OUT = started ] && $C/bin/nodetool tablestats b8.t_map 2>/dev/null | grep -E 'Memtable (cell count|data size)|SSTable count|Write Count' > $O/stats.txt
stop_node; sleep 1
$H/slowdisk.sh set 0 >> $LOG
cp $C/logs/system.log $C/logs/debug.log $C/logs/gc.log* $O/ 2>/dev/null
python3 $H/gcsum.py $O/gc.log > $O/gcsum.txt 2>&1
log "restore gc: $(tail -1 $O/gcsum.txt)"
log "mem.current max: $(sort -k2 -n $O/memcur.txt | tail -1 | cut -d' ' -f2) B"
log "segments in Replaying list: $(grep -m1 'CommitLog.java:206 - Replaying' $O/system.log | grep -o 'CommitLog-[0-9]*-[0-9]*.log' | wc -l)"
for f in 1 2 3 4 5 6 8 12 20 30 60 90; do [ -f $O/threads-$f.txt ] && log "threads +${f}s: $(python3 $H/g2.py $O/threads-$f.txt)"; done
mkdir -p $W/dumps-keep
for f in $O/dumps/*.hprof; do [ -f "$f" ] || continue
  if [ ! -e $W/dumps-keep/FIRST ] && [[ $RUN == T* || $RUN == U* ]]; then mv "$f" $W/dumps-keep/$RUN.hprof; echo $RUN > $W/dumps-keep/FIRST; log "dump kept as dumps-keep/$RUN.hprof ($(du -m $W/dumps-keep/$RUN.hprof | cut -f1) MiB)"
  else log "dump $(du -m $f | cut -f1) MiB deleted unread"; rm -f "$f"; fi
done
python3 $H/summ.py $O >> $LOG 2>&1
log "left: daemon=$(pgrep -fc '[o]rg.apache.cassandra.service.CassandraDaemon') client=$(pgrep -fc '[B]8Load')"
log "== RESULT $RUN img=$IMG heap=$HEAP D=$DMS PIT=$KIND opts='$ROPTS' outcome=$OUT"
