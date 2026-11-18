#!/usr/bin/env bash
# C5 stage 2, step P2: build the 1 + 64 ring once, kill dc2, create the schema, drain A, save the template.
# Runs on ms0604 under setsid nohup; log to $ROOT/ring.log.
set -uo pipefail
. /mydata/s4/c5-w1/h/env.sh
FIRST=${FIRST:-0}; LAST=${LAST:-63}; BATCH=${BATCH:-8}
ups(){ $NT status 2>/dev/null > $ROOT/.st; }
state_of(){ awk -v ip="$1" '$2==ip{print $1}' $ROOT/.st; }
if [ "${SKIP_A:-0}" != 1 ]; then
  $H/ctl.sh gen A 2048 || exit 1
  $H/ctl.sh start A
  for _ in $(seq 150); do (exec 3<>/dev/tcp/127.0.5.1/9042) 2>/dev/null && break; sleep 2; done
  (exec 3<>/dev/tcp/127.0.5.1/9042) 2>/dev/null || { log "A START FAIL"; exit 1; }
  log "A up"
fi
j=$FIRST; first=1
while [ $j -le $LAST ]; do
  e=$((j + BATCH - 1)); [ $e -gt $LAST ] && e=$LAST
  t0=$(date +%s)
  for i in $(seq $j $e); do $H/ctl.sh gen $i 0 > /dev/null && $H/ctl.sh start $i; done
  ok=0
  while [ $(( $(date +%s) - t0 )) -lt 360 ]; do
    sleep 10; ups; n=0; for i in $(seq $j $e); do [ "$(state_of 127.0.5.$((100+i)))" = UN ] && n=$((n+1)); done
    [ $n -eq $((e - j + 1)) ] && { ok=1; break; }
  done
  el=$(( $(date +%s) - t0 ))
  log "batch $j-$e: UN=$n/$((e-j+1)) after ${el}s"
  [ $ok = 1 ] || { log "BATCH CAP; see inst/<j>/logs"; for i in $(seq $j $e); do $H/ctl.sh kill9 $i; done; exit 1; }
  for i in $(seq $j $e); do $H/ctl.sh kill9 $i; done
  t1=$(date +%s)
  while [ $(( $(date +%s) - t1 )) -lt 180 ]; do
    sleep 5; ups; n=0; for i in $(seq $j $e); do [ "$(state_of 127.0.5.$((100+i)))" = DN ] && n=$((n+1)); done
    [ $n -eq $((e - j + 1)) ] && break
  done
  log "batch $j-$e: DN=$n/$((e-j+1)) after $(( $(date +%s) - t1 ))s"
  for i in $(seq $j $e); do rm -rf $INST/$i/data $INST/$i/commitlog $INST/$i/hints $INST/$i/saved_caches; done
  if [ $first = 1 ] && [ $el -le 180 ] && [ "${NOGROW:-0}" != 1 ]; then BATCH=16; fi; first=0
  j=$((e + 1))
done
ups; cp $ROOT/.st $ROOT/ring-status-before-schema.txt
log "dc2 DN=$(grep -c '^DN' $ROOT/.st) UN=$(grep -c '^UN' $ROOT/.st)"
[ "${NOSCHEMA:-0}" = 1 ] && exit 0
java -Xmx512m -cp "$CP" -Dlogback.configurationFile=$H/logback-quiet.xml C5Load schema || { log SCHEMA FAIL; exit 1; }
$NT describecluster > $ROOT/ring-describecluster.txt 2>&1
$NT status c5 > $ROOT/ring-status-final.txt 2>&1
$NT drain; log "drained"; $H/ctl.sh stop A
rm -rf $TPL; mkdir -p $TPL
cp -a $INST/A/data $INST/A/commitlog $INST/A/saved_caches $TPL/; ls $INST/A/hints | wc -l > $TPL/hints-count.txt
du -sh $TPL >> $ROOT/ring.log
log "RING DONE"
