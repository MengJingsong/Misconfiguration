#!/bin/bash
# B3 cluster tier (as amended S4-A1, S4-A4). Runs detached on the node. Logs every command and its output.
set -u
RUN=/mydata/jingsong-cass-s4/o119
export CASSANDRA_HOME=$RUN/cassandra
LOG=$RUN/cluster-session.txt
exec >>$LOG 2>&1
x() { echo "+ [$(date -u +%FT%T.%3NZ)] $*"; "$@"; local rc=$?; echo "  rc=$rc"; return $rc; }
ulimit -n 100000
cd $RUN
mkdir -p $RUN/jfr $RUN/logs
x df -h $RUN; x free -g; x ulimit -n
FIRST=1
stop_node() {
  local PID=$1
  x $CASSANDRA_HOME/bin/nodetool drain
  x kill $PID
  for i in $(seq 1 60); do kill -0 $PID 2>/dev/null || break; sleep 1; done
  if kill -0 $PID 2>/dev/null; then echo "  NOTE kill -9 needed"; kill -9 $PID; sleep 2; fi
  echo "  node procs after stop: $(ps -eo cmd | grep -c '[C]assandraDaemon')"
}
record() { # label fetch reps PID
  local L=$1 FS=$2 R=$3 PID=$4
  x jcmd $PID JFR.start name=dob settings=profile
  x jcmd $PID GC.heap_info > $RUN/jfr/$L-heap-before.txt
  echo "+ [$(date -u +%FT%T.%3NZ)] python3 dob.py read $FS $R"; python3 $RUN/harness/dob.py read $FS $R | tee $RUN/jfr/$L-reads.txt; echo "  rc=${PIPESTATUS[0]}"
  x jcmd $PID GC.heap_info > $RUN/jfr/$L-heap-after.txt
  x jcmd $PID JFR.dump name=dob filename=$RUN/jfr/$L.jfr
  x jcmd $PID JFR.stop name=dob
}
for T in unset 0 16 64 128 1024; do
  echo "===== T=$T ====="
  if [ $T = unset ]; then TT=""; else TT=$T; fi
  export MAX_HEAP_SIZE=4G
  unset HEAP_NEWSIZE
  export CASSANDRA_LOG_DIR=$RUN/logs/T$T
  mkdir -p $CASSANDRA_LOG_DIR
  JEO="-XX:FlightRecorderOptions=stackdepth=128 ${TT:+-Dcassandra.DOB_DOUBLING_THRESHOLD_MB=$TT}"
  echo "+ [$(date -u +%FT%T.%3NZ)] JVM_EXTRA_OPTS=\"$JEO\" bin/cassandra -p $RUN/cassandra.pid"
  JVM_EXTRA_OPTS="$JEO" $CASSANDRA_HOME/bin/cassandra -p $RUN/cassandra.pid > $CASSANDRA_LOG_DIR/stdout.txt 2>&1
  sleep 5
  PID=$(cat $RUN/cassandra.pid); echo "  PID=$PID"
  up=0
  for i in $(seq 1 90); do
    kill -0 $PID 2>/dev/null || { echo "  DAEMON DIED"; tail -30 $CASSANDRA_LOG_DIR/system.log; exit 1; }
    if $CASSANDRA_HOME/bin/nodetool status 2>/dev/null | grep -q '^UN' && $CASSANDRA_HOME/bin/nodetool statusbinary 2>/dev/null | grep -q running; then up=1; break; fi
    sleep 2
  done
  [ $up = 1 ] || { echo "  NODE NOT UP in 3 min"; stop_node $PID; exit 1; }
  x $CASSANDRA_HOME/bin/nodetool status
  echo "+ jcmd $PID VM.system_properties | grep -i DOB_DOUBLING"; jcmd $PID VM.system_properties | grep -i DOB_DOUBLING | tee $RUN/jfr/T$T-sysprop.txt; echo "  (empty above = absent)"
  ps -o args= -p $PID | tr ' ' '\n' | grep -E 'DOB_DOUBLING|Xmx|Xms|G1HeapRegionSize|stackdepth' | tee $RUN/jfr/T$T-jvmargs.txt
  if [ $FIRST = 1 ]; then
    echo "+ python3 dob.py load"; python3 $RUN/harness/dob.py load; echo "  rc=$?"
    x $CASSANDRA_HOME/bin/nodetool flush dob
    x du -sh $CASSANDRA_HOME/data $CASSANDRA_HOME/data/data/dob
    x $CASSANDRA_HOME/bin/nodetool tablestats dob.t
    FIRST=0
  fi
  echo "+ warm-up"; python3 $RUN/harness/dob.py read 0 1; echo "  rc=$?"
  record T$T 0 3 $PID
  record T$T-ctl 100 3 $PID
  x jcmd $PID JFR.check
  stop_node $PID
  grep -c '^ERROR' $CASSANDRA_LOG_DIR/system.log | sed 's/^/  ^ERROR lines: /'
done
echo "+ parse"
for f in $RUN/jfr/*.jfr; do java $RUN/harness/JfrDob.java $f > ${f%.jfr}.txt; echo "  $f -> $(wc -l < ${f%.jfr}.txt) lines"; done
echo CLUSTER-DONE
