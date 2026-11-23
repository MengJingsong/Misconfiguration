#!/usr/bin/env bash
# Build one golden data set (design §2.5) on ms0611 at the T configuration (unpatched, 2048M heap / 1024M direct).
#   golden.sh <name> <nblocks> <blocksize> <ckmode: same|perblock>
#   G600: 6 100 same   G6x100: 6 100 perblock   G420: 5 84 same   G1000: 10 100 same   G1500: 15 100 same
# Autocompaction disabled right after CREATE TABLE (runtime only, not persisted); nodetool flush after each block;
# then nodetool drain, stop, tar the node's data + commitlog (+ hints, saved_caches) into /mydata/s4/u12/golden/<name>.tar.
set -uo pipefail
N=$1; NB=$2; BS=$3; CKM=$4
U=/mydata/s4/u12; H=$U/h; B=$U/cassandra; D=$U/inst/node; R=$U/golden/$N-build
J=$B/build/lib/jars; CP="$U/cls:$J/cassandra-driver-core-3.12.1-shaded.jar:$B/lib/*"
log(){ echo "[$(TZ=America/New_York date '+%F %T')] $*"; }
rm -rf "$R"; mkdir -p "$R"; exec >> "$R/progress.txt" 2>&1
log "golden $N nblocks=$NB blocksize=$BS ck=$CKM"
bash $H/ctl.sh stop; bash $H/ctl.sh wipe-data
bash $H/ctl.sh start $B 2048 1024 "$R"
for i in $(seq 180); do grep -q "Startup complete" "$R/logs/system.log" 2>/dev/null && break; sleep 1; done
grep -q "Startup complete" "$R/logs/system.log" || { log "GOLDEN FAIL: no startup"; bash $H/ctl.sh stop; exit 1; }
java -Xmx256m -cp "$CP" -Dlogback.configurationFile=$H/logback-quiet.xml U12Load schema 127.0.0.1 || { log "GOLDEN FAIL schema"; bash $H/ctl.sh stop; exit 1; }
bash $H/ctl.sh nt $B disableautocompaction u12 t; log "autocompaction disabled"
fail=0
for j in $(seq 0 $((NB - 1))); do
  ck=0; [ "$CKM" = perblock ] && ck=$j
  java -Xmx512m -cp "$CP" -Dlogback.configurationFile=$H/logback-quiet.xml U12Load write 127.0.0.1 $ck $((j * BS)) $(((j + 1) * BS)) > "$R/load-$j.log" 2>&1 || fail=1
  tail -1 "$R/load-$j.log"
  [ $fail = 1 ] && { log "GOLDEN FAIL: write failure block $j"; break; }
  bash $H/ctl.sh nt $B flush u12 t; log "block $j ck=$ck flushed"
done
bash $H/ctl.sh nt $B drain; log "drained"
bash $H/ctl.sh nt $B tablestats u12.t > "$R/tablestats.txt" 2>&1
bash $H/ctl.sh stop
ls -l $D/data/u12/t-*/*Data.db > "$R/datadb.txt"; cat "$R/datadb.txt"
[ $fail = 0 ] && tar -cf $U/golden/$N.tar -C $D data commitlog hints saved_caches cdc_raw && log "GOLDEN OK $N $(du -sh $U/golden/$N.tar | cut -f1)"
bash $H/ctl.sh wipe-data
log "done"
