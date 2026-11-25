#!/usr/bin/env bash
# 3-b confirm B29 (pc82, 2026-11-24): phase driver. Run detached (setsid nohup); PID in /mydata/s4/DRIVER-3bB29.pid.
#   drive.sh setup   copy tree, pristine conf, compile clients, make confs
#   drive.sh load    LOAD lifetime (both 8G): auth bootstrap (system_auth RF 2 + repair), roles/schema/GRANTs, victim preload,
#                    attacker load (k 0..15 and 100..115: s='a' + 4,000 x 65,536 B rows; k 1000..1009: s='x' + 10 rows; CL ALL
#                    via node 1), probes, flush both (harness mechanics)
#   drive.sh divA    events monitor (attacker via node 2); operator: node 1 drained + stopped (outage); attacker via node 2 at
#                    CL ONE: DELETE k + UPDATE s='x' for k 0..15; operator: truncatehints on node 2 (stands for an outage past
#                    max_hint_window 3 h with no repair: F1 as in the verified arm)
#   drive.sh arm <label> <Q> <k0> <k1> <warm> [same]   node 1 restarted at 2 GiB (the outage ends); checks; victim 60 s; attack
#   drive.sh divB    node 1 down (killed by the previous arm's OOM); attacker via node 2 at CL ONE: filler (5 x 1,000 x 64 KiB rows),
#                    then DELETE + UPDATE s='x' for k 100..115; hints kept
#   drive.sh armB <label>   node 1 restarted at 2 GiB; attacker waits for the driver's UP event, attacks k 100..115 at once (no warm-up)
set -uo pipefail
ROOT=/mydata/s4/3b-B29; H=$ROOT/harness; V="bash $H/ctl.sh"; C="bash $H/client.sh"; EV=$ROOT/ev
log(){ echo "[$(TZ=America/New_York date '+%F %T %Z')] $*"; }
mkdir -p $ROOT/runs $EV
ts(){ for i in 1 2; do echo "== n$i"; $V nt $i tablestats b29.t | grep -E "SSTable count|Space used \(live\)|Number of partitions|Compacted partition maximum|Memtable cell count|Memtable data size"; done; }
hints(){ echo "n2 listpendinghints: $($V nt 2 listpendinghints | tr '\n' ' ')"; echo "n2 hints dir: $(ls -la $ROOT/n2/hints | grep -c '\.hints$') files, $(du -sb $ROOT/n2/hints | cut -f1) B"; }

case $1 in
setup)
  cp -a /mydata/s4/cassandra-base $ROOT/tree
  cp -a $ROOT/tree/conf $ROOT/conf-pristine
  mkdir -p $ROOT/cls; J=$ROOT/tree/build/lib/jars
  javac -nowarn -cp "$J/cassandra-driver-core-3.12.1-shaded.jar:$J/guava-32.0.1-jre.jar:$J/metrics-core-4.2.28.jar:$ROOT/tree/lib/*" -d $ROOT/cls \
    $H/B29Auth.java $H/B29Victim.java $H/B29Sampler.java 2>&1 | grep -v '^Note'
  $V conf; sha256sum $ROOT/tree/build/apache-cassandra-*.jar | tee $EV/jar.sha256
  log "SETUP-END";;
load)
  L=LOAD; D=$EV/LOAD; mkdir -p $D
  $V start $L 1 8G && $V ready $L 1 || exit 1
  $V start $L 2 8G && $V ready $L 2 || exit 1
  $V ring 1 2 || exit 1
  for k in $(seq 1 60); do grep -q "Created default superuser role" $ROOT/runs/$L/n*/logs/system.log && break; sleep 2; done
  grep -h "Created default superuser role" $ROOT/runs/$L/n*/logs/system.log | head -2
  sleep 5
  log "admin1"; $C cassandra B29Auth cql 127.0.0.1 $H/admin1.cql | tee $D/admin.txt
  for i in 1 2; do log "repair system_auth n$i"; $V nt $i repair -full system_auth | tail -2; done
  log "admin2"; $C cassandra B29Auth cql 127.0.0.1 $H/admin2.cql | tee -a $D/admin.txt
  sleep 5
  log "victim preload"; $C victim B29Victim preload 127.0.0.1 10000 | tee $D/victim-preload.txt
  log "attacker load (data role)"
  $C attacker B29Auth load 127.0.0.1 1000 1010 10 65536 x ALL | tail -1 | tee $D/attacker-load.txt
  ( $C attacker B29Auth load 127.0.0.1 0 16 4000 65536 a ALL; $C attacker B29Auth load 127.0.0.1 100 116 4000 65536 a ALL ) > $D/attacker-load-full.txt 2>&1
  grep -E "^load ok|^err" $D/attacker-load-full.txt | head -30 | tee -a $D/attacker-load.txt
  log "probes"
  $C attacker B29Auth cql 127.0.0.1 $H/probe-attacker.cql > $D/probes.txt 2>&1
  $C nogrant B29Auth cql 127.0.0.1 $H/probe-nogrant.cql >> $D/probes.txt 2>&1
  $C none B29Auth cql 127.0.0.1 $H/probe-nogrant.cql >> $D/probes.txt 2>&1
  echo "# attacker with a wrong password" >> $D/probes.txt; python3 $H/events.py 127.0.0.1 attacker wrong-password 1 /nonexistent >> $D/probes.txt 2>&1
  echo "# pre-auth hand-made frames" >> $D/probes.txt; python3 $H/preauth.py 127.0.0.1 >> $D/probes.txt 2>&1
  $C cassandra B29Auth cql 127.0.0.1 $H/admin3.cql >> $D/probes.txt 2>&1
  cat $D/probes.txt
  for i in 1 2; do $V nt $i flush b29; done; ts | tee $D/tablestats.txt
  $V nt 1 getendpoints b29 t 0 | tee -a $D/tablestats.txt; $V nt 1 getendpoints b29 t 100 | tee -a $D/tablestats.txt
  log "LOAD-END";;
divA)
  L=LOAD; D=$EV/divA; mkdir -p $D
  rm -f $ROOT/events.stop
  ( setsid nohup python3 $H/events.py 127.0.0.2 attacker att-pw 14400 $ROOT/events.stop > $ROOT/events.log 2>&1 < /dev/null & ); sleep 3
  pgrep -f "events.py 127.0.0.2" | head -1 > $ROOT/events.pid; head -5 $ROOT/events.log
  log "operator: node 1 down (drain, stop)"; $V stopn $L 1
  for k in $(seq 1 30); do $V nt 2 status | grep -q '^DN  127.0.0.1' && break; sleep 2; done; $V nt 2 status | grep -E '^(UN|DN)' | tee $D/status-n2.txt
  log "attacker: f1 via node 2 at CL ONE, k 0..15"; $C attacker B29Auth f1 127.0.0.2 0 16 ONE | tee $D/f1.txt
  hints | tee -a $D/hints.txt
  sleep 30; hints | tee -a $D/hints.txt
  log "operator: truncatehints on node 2 (stands for > 3 h outage)"; $V nt 2 truncatehints; sleep 15; $V nt 2 truncatehints; hints | tee -a $D/hints.txt
  tail -5 $ROOT/events.log | tee $D/events-tail.txt
  log "DIVA-END";;
boot)   # added 23:30 EST: node 1 (seed) first at 2 GiB, then node 2 (4 GiB as the stage-2 peer); node 2's auth read CL by JMX;
        # the attacker's event monitor (re)started through node 2
  L=$2; D=$EV/$L; mkdir -p $D
  $V start $L 1 2G && $V ready $L 1 || exit 1
  $V start $L 2 4G && $V ready $L 2 || exit 1
  $V ring 1 2 || exit 1
  java -cp $ROOT/cls AuthJmx 7299 LOCAL_ONE 2>&1 | tee $D/authjmx-n2.txt
  rm -f $ROOT/events.stop; cp $ROOT/events.log $EV/divA/events-2.log 2>/dev/null
  ( setsid nohup python3 $H/events.py 127.0.0.2 attacker att-pw 14400 $ROOT/events.stop > $ROOT/events.log 2>&1 < /dev/null & ); sleep 3; cat $ROOT/events.log
  log "BOOT-END";;
arm|armB)
  MODE=$1; L=$2; D=$EV/$L; R=$ROOT/runs/$L; mkdir -p $D $R
  if [ $MODE = arm ]; then Q=$3; K0=$4; K1=$5; WARM=$6; SAME=${7:-}; VW=60; else Q=8; K0=100; K1=116; WARM=0; SAME=; VW=0; fi
  log "ARM $L mode=$MODE Q=$Q k=$K0..$((K1-1)) warm=$WARM same=${SAME:-no}"
  echo "arm $L mode=$MODE Q=$Q k=$K0..$((K1-1)) warm=$WARM same=${SAME:-no}" >> $R/run.meta
  $V nt 2 status | grep -E '^(UN|DN)' | tee $D/status-before.txt; hints | tee $D/hints.txt
  if [ $MODE = armB ]; then
    ( cd $R && setsid nohup python3 $H/events.py 127.0.0.2 attacker att-pw 600 $R/waitup.stop --waitup 127.0.0.1 > waitup.log 2>&1 < /dev/null & ); sleep 2; cat $R/waitup.log
  fi
  [ "$($V alive $L 1)" = ALIVE ] || { $V start $L 1 2G || exit 1; }
  if [ $MODE = armB ]; then
    while pgrep -f "events.py 127.0.0.2 attacker att-pw 600" > /dev/null; do sleep 0.1; done
    date +%s%3N > $R/attack.start; log "attacker saw UP: $(tail -1 $R/waitup.log)"
    ( cd $R && setsid nohup bash $H/client.sh attacker B29Auth run 127.0.0.1 $Q $K0 $K1 $WARM 160 > client.csv 2> client.err < /dev/null & )
    $V ready $L 1; $V sampler $L
    ( cd $R && setsid nohup bash $H/client.sh victim B29Victim run 10 600 $R/victim.stop > victim.csv 2> victim.err < /dev/null & )
    hints | tee -a $D/hints.txt
  else
    $V ready $L 1 || exit 1; $V ring 1 2 || exit 1
    sleep 15
    echo "n1 b29.t memtable after restart:"; $V nt 1 tablestats b29.t | grep -E "Memtable cell count|SSTable count|Space used \(live\)" | tee $D/n1-tablestats.txt
    hints | tee -a $D/hints.txt
    $C attacker B29Auth stat 127.0.0.1 $((K1-1)) ONE trace > $D/precheck.txt 2>&1; $C attacker B29Auth stat 127.0.0.2 $((K1-1)) ONE >> $D/precheck.txt 2>&1
    grep -E "^stat|trace.*(Read|Merged|sstable|Executing)" $D/precheck.txt | head -12
    $V sampler $L
    ( cd $R && setsid nohup bash $H/client.sh victim B29Victim run 10 600 $R/victim.stop > victim.csv 2> victim.err < /dev/null & )
    sleep $VW
    date +%s%3N > $R/attack.start
    ( cd $R && setsid nohup bash $H/client.sh attacker B29Auth run 127.0.0.1 $Q $K0 $K1 $WARM 160 $SAME > client.csv 2> client.err < /dev/null & )
  fi
  sleep 3; CP=$(pgrep -f "B29Auth run 127.0.0.1" | head -1); log "attack client pid $CP"
  t0=$(date +%s); dead=0
  while true; do
    sleep 1; el=$(( $(date +%s) - t0 ))
    if [ "$($V alive $L 1)" != ALIVE ]; then log "NODE 1 DEAD at +${el}s"; dead=1; break; fi
    [ $((el % 5)) = 0 ] && { tail -1 $R/client.csv | cut -c1-160; [ $MODE = armB ] && hints; }
    kill -0 "$CP" 2>/dev/null || break
    [ $el -gt 240 ] && break
  done
  for i in $(seq 1 60); do kill -0 "$CP" 2>/dev/null || break; sleep 1; done
  kill "$CP" 2>/dev/null; sleep 1; pkill -9 -f "B29Auth run 127.0.0.1" 2>/dev/null
  date +%s%3N > $R/attack.end
  grep SUMMARY $R/client.csv; hints | tee -a $D/hints.txt
  sleep 60; touch $R/victim.stop; sleep 3; pkill -f "B29Victim run" 2>/dev/null
  $V samplerstop $L
  [ "$($V alive $L 1)" = ALIVE ] && [ $dead = 0 ] && log "node 1 survived"
  N1=$R/n1
  oomtype=$(grep -h -o -m1 "java.lang.OutOfMemoryError: [A-Za-z ]*" $N1/logs/system.log $N1/stdout.log 2>/dev/null | head -1)
  if [ $dead = 1 ] && [ -n "$oomtype" ]; then echo "OOM type=\"$oomtype\" at+${el}s (driver poll)" > $R/outcome
  elif [ $dead = 1 ]; then echo "DEAD-noOOM at+${el}s" > $R/outcome; else echo "SURVIVED" > $R/outcome; fi
  cat $R/outcome | tee $D/outcome
  cp $R/{run.meta,attack.start,attack.end,victim.csv,samples.csv,waitup.log} $D/ 2>/dev/null
  grep -E '^(#|t,|[0-9]{13},|SUMMARY)' $R/client.csv > $D/client.csv; cp $R/queries.csv $D/ 2>/dev/null; tail -20 $R/client.err > $D/client.err.tail
  grep -h -m3 -B2 -A30 'java\.lang\.OutOfMemoryError' $N1/logs/system.log $N1/stdout.log 2>/dev/null | head -120 > $D/oom-excerpt.txt
  grep -h 'Replica filtering protection\|slow\|Query cancelled\|exceeded\|Unauthorized\|hint' $N1/logs/system.log $N1/logs/debug.log 2>/dev/null | cut -c1-300 | head -30 > $D/n1-log-excerpt.txt
  grep -h -i 'hint' $(ls -t $ROOT/runs/*/n2/logs/system.log | head -1) | tail -20 > $D/n2-hint-lines.txt
  python3 $H/gcwin.py $N1/logs > $D/gcwin.txt 2>&1
  grep -h 'Pause Full\|Humongous regions:\|HeapDumper' $N1/logs/gc.log* 2>/dev/null | tail -12 > $D/gc-tail.txt
  cat $N1/../memory.events.last 2>/dev/null; cat /sys/fs/cgroup$(cat $N1/cgroup.path)/memory.events > $D/memory.events 2>/dev/null
  F=$(ls $N1/*.hprof 2>/dev/null | head -1)
  if [ -n "$F" ]; then
    ls -la $F > $D/hprof.ls
    nice -n 19 python3 $H/hprofhist.py $F 20 > $D/hprofhist.txt 2>&1
    nice -n 19 python3 $H/hprofstacks.py $F OutOfMemoryError > $D/oom-stack-from-hprof.txt 2>&1
    echo "threads with fetchFromSource in stack: $(nice -n 19 python3 $H/hprofstacks.py $F fetchFromSource 2>/dev/null | grep -c '^--- thread')" >> $D/hprof.ls
    rm -f $F
  fi
  python3 $H/victimsum.py $D > $D/victim-summary.txt 2>&1; cat $D/victim-summary.txt | head -30
  log "END $L $(cat $R/outcome)";;
divB)
  D=$EV/divB; mkdir -p $D
  $V nt 2 status | grep -E '^(UN|DN)' | tee $D/status-n2.txt; hints | tee $D/hints.txt
  log "attacker: filler via node 2 at CL ONE (k 5000..5004 x 1000 x 64 KiB)"; $C attacker B29Auth filler 127.0.0.2 5000 5005 1000 65536 ONE | tail -1 | tee $D/filler.txt
  log "attacker: f1 via node 2 at CL ONE, k 100..115"; $C attacker B29Auth f1 127.0.0.2 100 116 ONE | tee $D/f1.txt
  sleep 15; hints | tee -a $D/hints.txt; ls -la $ROOT/n2/hints | tee -a $D/hints.txt
  log "DIVB-END";;
esac
