#!/usr/bin/env bash
# B20 data preparation (design §2.5 steps 1-4), ms0640. Loader heap 8G / direct 4096M; not a reading.
#   prep.sh wide    -> pristine-C (W hard-linked)      prep.sh small  -> pristine-T      prep.sh k  -> offline K
set -uo pipefail
ROOT=/mydata/s4/b20; H=$ROOT/harness; BUILD=$ROOT/tree
export CASSANDRA_HOME=$BUILD
NT="$BUILD/bin/nodetool -h 127.0.0.1"
P=$ROOT/runs/prep; mkdir -p "$P"
log(){ echo "[$(TZ=America/New_York date '+%F %T %Z')] $*" | tee -a "$P/prep.log"; }
W(){ ls "$ROOT"/work/data/ks/t-*/*-Data.db 2>/dev/null; }

case $1 in
wide)
  rm -rf "$ROOT/work"; mkdir -p "$ROOT/work"/{data,commitlog,hints,saved_caches,cdc_raw}
  bash "$H/victim-ctl.sh" start PREP-W 8G 4096M >> "$P/prep.log" 2>&1 || exit 1
  bash "$H/victim-ctl.sh" ready PREP-W >> "$P/prep.log" 2>&1 || exit 1
  python3 "$H/writer.py" schema >> "$P/load.log" 2>&1
  $NT disableautocompaction ks t; $NT setcompactionthroughput 0
  log "schema done; autocompaction off; throughput 0"
  for c in $(seq 0 7); do
    python3 "$H/writer.py" wide $((c*500)) $(((c+1)*500)) >> "$P/load.log" 2>&1
    log "wide chunk $c: $(tail -1 "$P/load.log" | cut -c1-200); disk $(df -h /mydata | tail -1 | awk '{print $4}') free"
  done
  timeout 900 $NT flush ks t; log "flushed: $(W | xargs -r ls -l | awk '{s+=$5;n++} END{print n" sstables "s" B"}')"
  timeout 1800 $NT compact ks t; log "compacted: $(W | xargs -r ls -l | awk '{print $5, $9}')"
  python3 "$H/writer.py" cql "SELECT count(*) FROM ks.t WHERE pk = 0" 300 >> "$P/load.log" 2>&1
  log "count pk=0: $(tail -1 "$P/load.log")"
  bash "$H/victim-ctl.sh" stop PREP-W >> "$P/prep.log" 2>&1
  rm -rf "$ROOT/pristine-C"; bash "$H/clone.sh" "$ROOT/work" "$ROOT/pristine-C"
  log "pristine-C: $(du -sh "$ROOT/pristine-C" | cut -f1); W $(W)"
  ;;
small)
  bash "$H/victim-ctl.sh" start PREP-S 8G 4096M >> "$P/prep.log" 2>&1 || exit 1
  bash "$H/victim-ctl.sh" ready PREP-S >> "$P/prep.log" 2>&1 || exit 1
  $NT disableautocompaction ks t; $NT setcompactionthroughput 0
  log "small load start"
  for i in 0 1 2 3; do
    python3 "$H/writer.py" small $((1 + i*250000)) $((1 + (i+1)*250000)) 25 > "$P/small-$i.log" 2>&1 &
  done
  wait
  for i in 0 1 2 3; do log "small part $i: $(tail -1 "$P/small-$i.log" | cut -c1-200)"; done
  timeout 900 $NT flush ks t
  log "flushed: $(W | xargs -r ls -l | awk '{print $5, $9}')"
  timeout 120 $NT tablestats ks.t > "$P/tablestats-T.txt" 2>&1
  python3 "$H/writer.py" cql "SELECT token(pk) FROM ks.t WHERE pk = 0" 60 >> "$P/load.log" 2>&1
  log "token(0): $(tail -1 "$P/load.log")"
  python3 "$H/writer.py" cql "SELECT count(*) FROM ks.t WHERE token(pk) < token(0)" 900 >> "$P/load.log" 2>&1
  log "rank of pk=0: $(tail -1 "$P/load.log")"
  bash "$H/victim-ctl.sh" stop PREP-S >> "$P/prep.log" 2>&1
  rm -rf "$ROOT/pristine-T"; mv "$ROOT/work" "$ROOT/pristine-T"
  log "pristine-T: $(du -sh "$ROOT/pristine-T" | cut -f1)"
  ;;
k)
  for set in C T; do
    for d in "$ROOT"/pristine-$set/data/ks/t-*/*-Data.db; do
      "$BUILD/tools/bin/sstablemetadata" "$d" > "$P/meta-$set-$(basename "$d" .db).txt" 2>&1
    done
    python3 "$H/kcalc.py" "$P"/meta-$set-*.txt > "$P/kcalc-$set.txt" 2>&1
    log "K_$set: $(grep RESULT "$P/kcalc-$set.txt")"
  done
  ;;
esac
