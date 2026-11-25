#!/usr/bin/env bash
# R23 writer image (design 2.5 "Writer image"): mkimg.sh <img> [rate=50]
# D = 0, heap 1024 M, archiving on. Schema; W0 (~300 P64); snapshot r23base; B1 (~150 P64); PIT_C; B2 (~2,250 P64); PIT_T;
# drain; stop. Saves img/<img>/{data,commitlog,archive,pit.env,client-*.txt}. Gate G0 logged. Leaves nothing running.
set -uo pipefail
IMG=$1 RATE=${2:-50}; HEAP=1024
source /mydata/s4/r23/harness/common.sh
O=$W/runs/mk-$IMG; rm -rf $O; mkdir -p $O/dumps; LOG=$O/arm.log
[ -n "$(dpid)" ] && { log "ABORT: a daemon is running"; exit 1; }
S=$(( 50 / RATE )); D0=$(( 6*50/RATE )); D1=$(( 3*50/RATE )); D2=$(( 45*50/RATE ))
log "== mkimg $IMG writer heap=${HEAP}M rate=${RATE}/s W0=${D0}s B1=${D1}s B2=${D2}s arch=$(uname -m); /mydata free $(df -BG --output=avail /mydata | tail -1)"
$H/slowdisk.sh set 0 >> $LOG
rm -rf $W/vol/data/* $C/data/commitlog/* $C/data/hints/* $C/data/saved_caches/* $W/archive/*
cp $H/archiving-writer.properties $C/conf/commitlog_archiving.properties
log "commitlog_archiving.properties: $(grep -v '^#' $C/conf/commitlog_archiving.properties | tr '\n' ' ')"
rm -rf $C/logs; mkdir -p $C/logs
start_node $O $HEAP r23-mk-$IMG
for i in $(seq 1 300); do grep -q 'Starting listening for CQL clients' $C/logs/system.log 2>/dev/null && break; sleep 1; done
log "node up after ${i}s; $(grep -m1 -o 'Global memtable on-heap threshold is enabled at [^ ]*' $C/logs/system.log); $(grep -m1 -o 'commitlog_total_space=[^;,]*' $C/logs/system.log); $(grep -m1 -o 'memtable_flush_writers=[^;,]*' $C/logs/system.log); $(grep -m1 -o 'memtable_cleanup_threshold=[^;,]*' $C/logs/system.log); $(grep -m1 -o 'concurrent_writes=[^;,]*' $C/logs/system.log)"
$H/load.sh schema 127.0.0.1 > $O/client-schema.txt 2>&1; log "schema: $(tail -1 $O/client-schema.txt)"
$H/load.sh run map 5900 16 $D0 0 127.0.0.1 $RATE > $O/client-W0.txt 2>&1
log "W0: $(grep FINAL $O/client-W0.txt)"
$C/bin/nodetool snapshot -t r23base b8 > $O/snapshot.txt 2>&1; SNAP=$(date -u '+%Y:%m:%d %H:%M:%S.%3N')
log "snapshot r23base at $SNAP UTC: $(tr '\n' ' ' < $O/snapshot.txt | cut -c1-200)"
sleep 2
$H/load.sh run map 5900 16 $D1 100000 127.0.0.1 $RATE > $O/client-B1.txt 2>&1
log "B1: $(grep FINAL $O/client-B1.txt)"
sleep 2; PIT_C=$(date -u -d '-1 sec' '+%Y:%m:%d %H:%M:%S.%3N'); sleep 1
$H/load.sh run map 5900 16 $D2 200000 127.0.0.1 $RATE > $O/client-B2.txt 2>&1
log "B2: $(grep FINAL $O/client-B2.txt)"
sleep 2; PIT_T=$(date -u -d '-1 sec' '+%Y:%m:%d %H:%M:%S.%3N')
log "PIT_C='$PIT_C' PIT_T='$PIT_T'"
$C/bin/nodetool tablestats b8.t_map 2>/dev/null | grep -E 'SSTable count|Write Count|Space used \(live' > $O/tablestats.txt
$C/bin/nodetool drain > $O/drain.txt 2>&1; log "drain rc=$? $(tr '\n' ' ' < $O/drain.txt | cut -c1-120)"
DIED=0; [ -z "$(dpid)" ] && DIED=1
stop_node
cp $C/logs/system.log $C/logs/debug.log $C/logs/gc.log* $O/ 2>/dev/null
python3 $H/gcsum.py $O/gc.log > $O/gcsum.txt 2>&1; log "writer gc: $(tail -1 $O/gcsum.txt)"
ls -l $C/data/commitlog > $O/commitlog-ls.txt; ls -l $W/archive > $O/archive-ls.txt
log "commitlog dir: $(ls $C/data/commitlog | wc -l) files $(du -sm $C/data/commitlog | cut -f1) MiB; archive: $(ls $W/archive | wc -l) files $(du -sm $W/archive | cut -f1) MiB"
ls -la $W/vol/data/b8/t_map-*/ $W/vol/data/b8/t_map-*/snapshots/r23base/ > $O/table-ls.txt 2>&1
rm -rf $W/img/$IMG; mkdir -p $W/img/$IMG
cp -a --sparse=always $W/vol/data $W/img/$IMG/data; cp -a $C/data/commitlog $W/img/$IMG/commitlog; cp -a $W/archive $W/img/$IMG/archive
printf "PIT_C='%s'\nPIT_T='%s'\nSNAP='%s'\n" "$PIT_C" "$PIT_T" "$SNAP" > $W/img/$IMG/pit.env; cp $W/img/$IMG/pit.env $O/
cp $O/client-*.txt $W/img/$IMG/
ok() { grep FINAL $O/client-$1.txt | grep -o ' ok=[0-9]*' | cut -d= -f2; }
er() { grep FINAL $O/client-$1.txt | grep -o ' err=[0-9]*' | cut -d= -f2; }
B1=$(ok B1); B2=$(ok B2); E=$(( $(er W0) + $(er B1) + $(er B2) )); T=$(( $(ok W0) + B1 + B2 ))
NA=$(ls $W/archive | wc -l)
G0=pass; [ "$B1" -ge 140 ] && [ "$B1" -le 160 ] || G0=fail; [ "$B2" -ge 2150 ] || G0=fail; [ $(( E*100 )) -lt $T ] || G0=fail; [ $DIED = 0 ] || G0=fail; [ $NA -ge 3 ] || G0=fail
log "G0=$G0 (B1 ok=$B1, B2 ok=$B2, errors=$E of $T, writer died before drain=$DIED, archive segments=$NA)"
rm -rf $O/dumps/*.hprof
log "image $IMG: $(du -sm $W/img/$IMG | cut -f1) MiB; left: daemon=$(pgrep -fc '[o]rg.apache.cassandra.service.CassandraDaemon') client=$(pgrep -fc '[B]8Load')"
log "== RESULT mk-$IMG G0=$G0"
