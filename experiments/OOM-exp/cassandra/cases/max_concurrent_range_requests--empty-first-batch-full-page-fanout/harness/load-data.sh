#!/usr/bin/env bash
# C10 LOAD lifetime (not a reading): bootstrap the empty 3-node ring (8G heaps), ring -> T_hot, schema, 1,000,000 rows,
# flush, tablestats, drain + stop, templates (saved_caches removed).   load-data.sh
set -uo pipefail
ROOT=/mydata/s4/c10; H=$ROOT/harness; R=$ROOT/runs/LOAD; SHM=/dev/shm/c10
NT="$ROOT/tree/bin/nodetool -h 127.0.0.1"
C="bash $H/ring-ctl.sh"
log(){ echo "[$(TZ=America/New_York date '+%F %T %Z')] $*"; }
$C start LOAD LOAD 8G || { log "LOAD start failed"; exit 1; }
$NT -p 7199 status > "$R/status.txt" 2>&1; cat "$R/status.txt"
$NT -p 7199 ring > "$R/ring.txt" 2>&1
python3 "$H/ringcalc.py" "$R/ring.txt" "$R" | tee "$R/ringcalc.txt"
THOT=$(cat "$R/T_hot")
bash "$H/client.sh" LOAD-schema schema 127.0.0.1
bash "$H/client.sh" LOAD-load load 127.0.0.1 1000000 "$THOT" 64 | tee "$R/load.out"
bash "$H/client.sh" LOAD-tok tokcheck 127.0.0.1 | tee "$R/tokcheck.out"
for p in 7199 7299 7399; do $NT -p $p flush c10; done
for p in 7199 7299 7399; do echo "== $p"; $NT -p $p tablestats c10.t | grep -E 'SSTable count|Space used \(live\)|Number of partitions|Local read count'; done | tee "$R/tablestats.txt"
$C stop LOAD
for i in 1 2 3; do rm -rf "$SHM/template$i"; cp -a "$SHM/node$i" "$SHM/template$i"; rm -rf "$SHM/template$i"/saved_caches/*; done
du -sh "$SHM"/template* | tee -a "$R/tablestats.txt"
log "LOAD done"
