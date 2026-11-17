#!/usr/bin/env bash
# U1 run 2 node-side helpers (copied to /mydata/u1r2/h/ on every node).
#   node.sh build                                   compile U1R2Load / U1R2Sample into /mydata/u1r2/cls
#   node.sh schema <host> <replication-map>
#   node.sh client <run> <blob> <inflight> <secs> <rate|0> <host> [writers]   (coordinator nodes; background)
#   node.sh vsamp <run> [jstack 0|1]                (V: JMX/CQL sampler 1 s, cgroup sampler 1 s, optional jcmd 5 s)
#   node.sh vstop <run>                             (V: stop samplers)
#   node.sh vcollect <run>                          (V: wait for dump, copy logs, outcome line)
#   node.sh wipe                                    (stop everything of this run on this node, delete instance dirs)
set -uo pipefail
H=/mydata/u1r2/h; RUNS=/mydata/u1r2/runs; B=/mydata/u1r2/cassandra; J=$B/build/lib/jars; INST=/mydata/u1r2/inst
CP="/mydata/u1r2/cls:$J/cassandra-driver-core-3.12.1-shaded.jar:$J/guava-32.0.1-jre.jar:$J/metrics-core-4.2.28.jar:$B/lib/*"
cmd=$1; shift
case $cmd in
  build) mkdir -p /mydata/u1r2/cls && javac -cp "$CP" -d /mydata/u1r2/cls $H/U1R2Load.java $H/U1R2Sample.java && echo built ;;
  schema) java -Xmx512m -cp "$CP" -Dlogback.configurationFile=$H/logback-quiet.xml U1R2Load schema "$1" "$2" ;;
  client)
    R=$RUNS/$1; mkdir -p $R; W=${7:-1}
    nohup java -Xmx6g -Dkeys=${KEYS:-200} -Dwriters=$W -cp "$CP" -Dlogback.configurationFile=$H/logback-quiet.xml \
      U1R2Load run "$2" "$3" "$4" "$5" "$6" > $R/load-$6.log 2>&1 < /dev/null &
    echo "client pid $!" ;;
  vsamp)
    R=$RUNS/$1; mkdir -p $R; JS=${2:-0}
    VPID=$($H/ctl.sh pid V); CG=$($H/ctl.sh cg V)
    echo "vpid=$VPID cg=$CG" >> $R/args.txt
    nohup java -Xmx256m -cp "$CP" -Dlogback.configurationFile=$H/logback-quiet.xml U1R2Sample 10.10.1.1 7199 1000 $R > $R/sampler.err 2>&1 < /dev/null &
    echo $! > $R/.samp.pid
    nohup bash -c "echo epoch_ms,mem_current,anon,file,oom,oom_kill > $R/cg.csv; while kill -0 $VPID 2>/dev/null; do echo \$(date +%s%3N),\$(cat $CG/memory.current 2>/dev/null),\$(awk '/^anon /{print \$2}' $CG/memory.stat 2>/dev/null),\$(awk '/^file /{print \$2}' $CG/memory.stat 2>/dev/null),\$(awk '/^oom /{print \$2}' $CG/memory.events 2>/dev/null),\$(awk '/^oom_kill /{print \$2}' $CG/memory.events 2>/dev/null) >> $R/cg.csv; cp $CG/memory.events $R/memory.events.final 2>/dev/null; sleep 1; done" > /dev/null 2>&1 < /dev/null &
    echo $! > $R/.cg.pid
    if [ "$JS" = 1 ]; then
      nohup bash -c "echo epoch_ms,mut,cl_add,expand,serialize,seg_wait,sync_wait,other_in_add,memtable_wait,idle > $R/jstack.csv; i=0; while kill -0 $VPID 2>/dev/null; do i=\$((i+1)); jcmd $VPID Thread.print > $R/.td 2>/dev/null && python3 $H/jstk.py < $R/.td >> $R/jstack.csv; [ \$((i % 6)) = 3 ] && cp $R/.td $R/threads-\$i.txt; sleep 5; done" > /dev/null 2>&1 < /dev/null &
      echo $! > $R/.js.pid
    fi
    jcmd $VPID VM.flags 2>/dev/null | tr ' ' '\n' | grep -E "MaxDirectMemorySize|MaxHeapSize|UseG1GC" > $R/V-flags.txt
    tr '\0' '\n' < /proc/$VPID/cmdline > $R/V-cmdline.txt
    cp $INST/V/yaml.diff $R/V-yaml.diff ;;
  vstop)
    R=$RUNS/$1; for f in .samp.pid .js.pid; do [ -f $R/$f ] && { kill $(cat $R/$f) 2>/dev/null; rm -f $R/$f; }; done; rm -f $R/.td ;;
  vcollect)
    R=$RUNS/$1; VPID=$(grep -o 'vpid=[0-9]*' $R/args.txt | head -1 | cut -d= -f2)
    if ls $INST/V/dumps/*.hprof >/dev/null 2>&1; then
      for _ in $(seq 100); do kill -0 $VPID 2>/dev/null || break; sleep 3; done
      mv $INST/V/dumps/*.hprof $R/ 2>/dev/null; ls -la $R/*.hprof >> $R/args.txt
    fi
    if kill -0 $VPID 2>/dev/null; then st=alive; else st=DEAD; fi
    mkdir -p $R/V-logs; cp -p $INST/V/logs/system.log $INST/V/logs/debug.log $INST/V/logs/gc.log* $INST/V/logs/launch.log $INST/V/logs/hs_err* $R/V-logs/ 2>/dev/null
    [ -f $R/.cg.pid ] && { kill $(cat $R/.cg.pid) 2>/dev/null; rm -f $R/.cg.pid; }
    oomd=$(grep -c "OutOfMemoryError: Direct buffer memory" $R/V-logs/system.log 2>/dev/null)
    oomh=$(grep -c "OutOfMemoryError: Java heap" $R/V-logs/system.log 2>/dev/null)
    oomn=$(grep -c "OutOfDirectMemoryError" $R/V-logs/system.log 2>/dev/null)
    grep -v "JVM Arguments" $R/V-logs/system.log | grep -n -m1 -B3 -A40 "OutOfMemoryError\|OutOfDirectMemoryError" > $R/first-oom.txt 2>/dev/null
    peaks=$(python3 $H/peaks.py $R 2>&1)
    mmd=$(grep -o "MaxDirectMemorySize *= *[0-9]*\|MaxDirectMemorySize=[0-9]*" $R/V-flags.txt | grep -o "[0-9]*$" | head -1)
    echo "$1 $(cat $R/argline 2>/dev/null) | resolved_direct=$((${mmd:-0}/1048576))MiB | V=$st directOOM=$oomd heapOOM=$oomh nettyOOM=$oomn oom_kill=$(awk '/^oom_kill /{print $2}' $R/memory.events.final 2>/dev/null) | $peaks" > $R/outcome.txt
    cat $R/outcome.txt >> $RUNS/summary.txt; cat $R/outcome.txt ;;
  wipe)
    pkill -f "[U]1R2Load" ; pkill -f "[U]1R2Sample"
    for r in V C1 C2 C3 C4 C5 C6 C7 C8; do [ -d $INST/$r ] && $H/ctl.sh stop $r > /dev/null 2>&1; done
    pkill -9 -f "cassandra.logdir=$INST" 2>/dev/null
    for u in $(systemctl --user list-units --type=scope --no-legend 2>/dev/null | awk '/u1r2-/{print $1}'); do systemctl --user stop $u; done
    rm -rf $INST/* ;;
esac
