#!/usr/bin/env bash
# One U12 run (design §2.5 "One run" / arm N). Runs ON ms0611; launch detached:
#   ( setsid nohup bash /mydata/s4/u12/h/run.sh <arm> <run> <golden|N> <base|patched> <heapMiB> <directMiB> [extra JVM opts] < /dev/null > /dev/null 2>&1 & )
#   env VERIFY=1: after a completed compaction, restart and run `nodetool verify -e -f u12 t` (amendment A1: 5.0.9 needs -f)
# Instruments: O1 JMX sampler 250 ms (samples.csv), O2 RssAnon/VmHWM 1 s (rss.csv), O3 gc.log (cassandra-env.sh default
# -Xlog:gc...), O4 system/debug.log, O5 heap dump (HeapDumpOnOutOfMemoryError into <run>/dumps), O6 compactionstats 2 s,
# O7 Data.db before/after. Endpoint: node exits (OOM) / "Compacted" for u12.t / 300 s after compaction start.
set -uo pipefail
ARM=$1; RUN=$2; G=$3; BLD=$4; HEAP=$5; DIRECT=$6; shift 6; EXTRA="${*:-}"
U=/mydata/s4/u12; H=$U/h; D=$U/inst/node; R=$U/runs/$RUN
B=$U/cassandra; [ "$BLD" = patched ] && B=$U/cassandra-patched
J=$U/cassandra/build/lib/jars; CP="$U/cls:$J/cassandra-driver-core-3.12.1-shaded.jar:$U/cassandra/lib/*"
log(){ echo "[$(TZ=America/New_York date '+%F %T')] $(date +%s%3N) $*"; }
rm -rf "$R"; mkdir -p "$R"; exec >> "$R/progress.txt" 2>&1
echo "$ARM $RUN golden=$G build=$BLD heap=$HEAP direct=$DIRECT extra=[$EXTRA] verify=${VERIFY:-0}" > "$R/argline"
log "RUN $(cat $R/argline)"
bash $H/ctl.sh stop; bash $H/ctl.sh wipe-data
if [ "$G" != N ]; then
  tar -xf $U/golden/$G.tar -C $D || { log "INVALID: untar"; exit 1; }
  ls -l $D/data/u12/t-*/*Data.db > "$R/datadb-before.txt"; log "restored $G: $(wc -l < $R/datadb-before.txt) Data.db"
fi
bash $H/ctl.sh start $B $HEAP $DIRECT "$R" $EXTRA
P=$(cat $R/node.pid); log "node pid $P"
# samplers
( setsid nohup java -Xmx128m -cp "$U/cls" U12Sample 7199 250 "$R" > "$R/sampler.err" 2>&1 < /dev/null & )
( setsid nohup bash -c "echo epoch_ms,rss_anon_kb,vmhwm_kb > $R/rss.csv; while kill -0 $P 2>/dev/null; do echo \$(date +%s%3N),\$(awk '/^RssAnon/{print \$2}' /proc/$P/status 2>/dev/null),\$(awk '/^VmHWM/{print \$2}' /proc/$P/status 2>/dev/null) >> $R/rss.csv; sleep 1; done" < /dev/null > /dev/null 2>&1 & )
( setsid nohup bash -c "while kill -0 $P 2>/dev/null; do echo \"@ \$(date +%s%3N)\"; $B/bin/nodetool -h 127.0.0.1 compactionstats 2>&1 | grep -v '^\$'; sleep 2; done > $R/compactionstats.txt" < /dev/null > /dev/null 2>&1 & )
alive(){ kill -0 $P 2>/dev/null; }
SL=$R/logs/system.log
for i in $(seq 240); do grep -q "Startup complete" $SL 2>/dev/null && break; alive || break; sleep 1; done
if ! grep -q "Startup complete" $SL 2>/dev/null; then log "INVALID: no startup"; fi
TSU=$(date +%s); log "startup complete"
cmpstart(){ grep -q "Compacting (.*/data/u12/t-" $R/logs/debug.log 2>/dev/null || grep -q "u12 *t " $R/compactionstats.txt 2>/dev/null; }
compacted(){ grep -q "Compacted (.*/data/u12/t-" $SL 2>/dev/null; }
MANUAL=0
if [ "$G" = N ]; then
  java -Xmx256m -cp "$CP" -Dlogback.configurationFile=$H/logback-quiet.xml U12Load schema 127.0.0.1 > "$R/schema.log" 2>&1
  log "schema done; N writes 700 start"
  ( setsid nohup java -Xmx512m -Dstop_on_error=false -cp "$CP" -Dlogback.configurationFile=$H/logback-quiet.xml U12Load write 127.0.0.1 0 0 700 > "$R/load.log" 2>&1 < /dev/null & )
  # wait for a compaction of u12.t (writes continue) or node death; give up 600 s after writes start
  for i in $(seq 600); do cmpstart && break; alive || break; sleep 1; done
else
  for i in $(seq 90); do cmpstart && break; alive || break; sleep 1; done
  if alive && ! cmpstart; then
    MANUAL=1; log "no background compaction 90 s after startup: nodetool compact u12 t"
    ( setsid nohup $B/bin/nodetool -h 127.0.0.1 compact u12 t > "$R/nodetool-compact.log" 2>&1 < /dev/null & )
    for i in $(seq 60); do cmpstart && break; alive || break; sleep 1; done
  fi
fi
if cmpstart; then TC=$(date +%s); log "compaction started (manual=$MANUAL)"; else TC=$(date +%s); log "NO COMPACTION seen (alive=$(alive && echo 1 || echo 0))"; fi
END=none
for i in $(seq 300); do
  alive || { END=exit; break; }
  if compacted; then
    if [ "$G" = N ]; then grep -q "acked=[0-9]* failed=" $R/load.log 2>/dev/null && { END=compacted; break; }
    else END=compacted; break; fi
  fi
  sleep 1
done
[ "$END" = none ] && END=timeout300
log "endpoint $END ($(( $(date +%s) - TC )) s after compaction start)"
if [ "$END" = exit ]; then
  log "node exited"
elif [ "$END" = compacted ]; then
  sleep 5; ls -l $D/data/u12/t-*/*Data.db > "$R/datadb-after.txt" 2>/dev/null
  if [ "${VERIFY:-0}" = 1 ]; then
    bash $H/ctl.sh stop; log "restart for verify"
    mkdir -p $R/verify; bash $H/ctl.sh start $B $HEAP $DIRECT "$R/verify" $EXTRA
    for i in $(seq 240); do grep -q "Startup complete" $R/verify/logs/system.log 2>/dev/null && break; sleep 1; done
    $B/bin/nodetool -h 127.0.0.1 disableautocompaction u12 t
    $B/bin/nodetool -h 127.0.0.1 verify -e -f u12 t > $R/verify/verify.out 2>&1; echo "verify_exit=$?" >> $R/verify/verify.out
    log "verify: $(tail -1 $R/verify/verify.out)"
  fi
fi
bash $H/ctl.sh stop
sleep 2
pkill -f "U12Sample 7199 250 $R" ; pkill -f "U12Load write 127.0.0.1" 2>/dev/null
ls -l $D/data/u12/t-*/*Data.db > "$R/datadb-final.txt" 2>/dev/null
grep -n -m1 -B2 -A45 "OutOfMemoryError" $SL > $R/first-oom.txt 2>/dev/null
ls -la $R/dumps > $R/dumps.txt
python3 $H/analyze.py $R > $R/outcome.txt 2>&1; echo "END=$END manual_compact=$MANUAL" >> $R/outcome.txt
echo "$RUN $(cat $R/argline) | $(head -1 $R/outcome.txt) | END=$END manual=$MANUAL" >> $U/runs/summary.txt
bash $H/ctl.sh wipe-data
log "DONE"
