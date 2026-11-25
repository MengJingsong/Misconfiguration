#!/usr/bin/env bash
# Stage-4 cluster tier (B3e with A6, A8, A9), order 9 PriorityQueue_maxSize-insert-maxSize--autonomous, Jingsong, pc75.
# Usage (on the node): cluster-run.sh <run-folder> <harness-dir> [<output-subdir>, default cluster]
# v2 (2026-11-25, A10): reducer container found by its attempt id; merge lines counted in syslog + syslog.shuffle;
# every application's container logs copied when it ends; state dirs of an earlier attempt removed before format.
# Pseudo-distributed NameNode + DataNode + ResourceManager + NodeManager from a copy of the node's base distribution.
# Logs every command and its output to <run>/cluster/cluster-run.log; stops (and tears down) at the first failed step.
set -u
R=${1:?run folder}; H=${2:?harness dir}
C=$R/${3:-cluster}; mkdir -p "$C"
exec > >(tee -a "$C/cluster-run.log") 2>&1
export JAVA_HOME=/usr/lib/jvm/java-8-openjdk-amd64 PATH=/usr/lib/jvm/java-8-openjdk-amd64/bin:$PATH
BASE=/mydata/jingsong-s4/hadoop-base/hadoop-dist/target/hadoop-3.4.2
export HADOOP_HOME=$R/hadoop HADOOP_CONF_DIR=$R/conf HADOOP_LOG_DIR=$R/logs/daemons HADOOP_PID_DIR=$R/pids
export PATH=$HADOOP_HOME/bin:$PATH
ulimit -n 65536 2>/dev/null || ulimit -n 4096 2>/dev/null || true
step() { echo; echo "=== $(date '+%F %T %Z') STEP: $*"; }
teardown() {
  step "teardown"
  pkill -f "jdwp=transport=dt_socket,server=y,suspend=y,address=500[56]" 2>/dev/null
  for a in $(yarn application -list 2>/dev/null | awk '/^application_/{print $1}'); do yarn application -kill "$a"; done
  yarn --daemon stop nodemanager; yarn --daemon stop resourcemanager
  hdfs --daemon stop datanode; hdfs --daemon stop namenode
  sleep 5
  ps -eo pid,cmd | grep -E "[N]ameNode|[D]ataNode|[R]esourceManager|[N]odeManager|[Y]arnChild|[M]RAppMaster|[j]db -attach|[D]istCp" | cut -c1-150 || true
}
die() { echo "=== STOP: $*"; teardown; exit 1; }
prop() { echo "  <property><name>$1</name><value>$2</value></property>"; }
site() { local f=$1; shift; { echo '<?xml version="1.0"?>'; echo '<configuration>'; while [ $# -gt 0 ]; do prop "$1" "$2"; shift 2; done; echo '</configuration>'; } > "$HADOOP_CONF_DIR/$f"; }

step "environment"; date; hostname; uname -r; java -version; df -h /mydata | tail -1; ulimit -n
ss -ltn | grep -E ":(5005|5006|9000|9870|9864|9866|9867|8088|8030|8031|8032|8033|8040|8042|13562) " && die "ports busy"
step "distribution copy and configuration (B3a, A6)"
[ -e "$HADOOP_HOME" ] || cp -a "$BASE" "$HADOOP_HOME" || die "copy dist"
hadoop version | head -1
rm -rf "$HADOOP_CONF_DIR"; cp -r "$HADOOP_HOME/etc/hadoop" "$HADOOP_CONF_DIR"
cat >> "$HADOOP_CONF_DIR/hadoop-env.sh" <<EOF
export JAVA_HOME=$JAVA_HOME
export HADOOP_HEAPSIZE_MAX=1g
export HADOOP_LOG_DIR=$HADOOP_LOG_DIR
export HADOOP_PID_DIR=$HADOOP_PID_DIR
EOF
site core-site.xml fs.defaultFS hdfs://localhost:9000 hadoop.tmp.dir "$R/tmp"
site hdfs-site.xml dfs.replication 1 dfs.namenode.name.dir "$R/nn" dfs.datanode.data.dir "$R/dn"
site yarn-site.xml yarn.nodemanager.aux-services mapreduce_shuffle yarn.nodemanager.resource.memory-mb 6144 \
  yarn.scheduler.maximum-allocation-mb 2048 yarn.nodemanager.resource.cpu-vcores 16 \
  yarn.nodemanager.local-dirs "$R/nm-local" yarn.nodemanager.log-dirs "$R/nm-logs" yarn.nodemanager.vmem-check-enabled false
site mapred-site.xml mapreduce.framework.name yarn yarn.app.mapreduce.am.env "HADOOP_MAPRED_HOME=$HADOOP_HOME" \
  mapreduce.map.env "HADOOP_MAPRED_HOME=$HADOOP_HOME" mapreduce.reduce.env "HADOOP_MAPRED_HOME=$HADOOP_HOME"
for f in core-site hdfs-site yarn-site mapred-site; do echo "--- $f.xml"; cat "$HADOOP_CONF_DIR/$f.xml"; done

step "static scan of every jar in the distribution (B2e step 5, B3d)"
python3 -I "$H/scan_insert.py" "$HADOOP_HOME/share" > "$C/scan-dist.txt"; grep -E "SUBCLASS|HIT|SUMMARY|WARN" "$C/scan-dist.txt" | head -40

step "format and start daemons (B3e step 1, A6)"
rm -rf "$R/nn" "$R/dn" "$R/tmp" "$R/nm-local" "$R/nm-logs" "$R/pids"
hdfs namenode -format -nonInteractive > "$C/format.log" 2>&1 || die format
hdfs --daemon start namenode; hdfs --daemon start datanode
yarn --daemon start resourcemanager; yarn --daemon start nodemanager
sleep 10; hdfs dfsadmin -safemode wait || die safemode
for i in $(seq 60); do yarn node -list 2>/dev/null | grep -q RUNNING && break; sleep 2; done
yarn node -list 2>/dev/null | grep RUNNING || die "no NodeManager"
jps

EX=$HADOOP_HOME/share/hadoop/mapreduce/hadoop-mapreduce-examples-3.4.2.jar
step "teragen (B3e step 3)"
hadoop jar "$EX" teragen -Dmapreduce.job.maps=4 2000000 /tg > "$C/teragen.log" 2>&1 || die teragen
grep -E "completed successfully|Bytes Written" "$C/teragen.log"; hdfs dfs -du -s /tg

for f in 2 10 100; do
  step "terasort f=$f with the reducer under jdb on 5005 (B3e step 4)"
  hadoop jar "$EX" terasort -Dmapreduce.job.reduces=1 -Dmapreduce.input.fileinputformat.split.maxsize=8388608 \
    -Dmapreduce.task.io.sort.mb=4 -Dmapreduce.task.io.sort.factor=$f -Dmapreduce.reduce.shuffle.input.buffer.percent=0.05 \
    -Dmapreduce.job.reduce.slowstart.completedmaps=1.0 -Dmapreduce.reduce.speculative=false -Dmapreduce.reduce.maxattempts=1 \
    -Dmapreduce.task.timeout=1800000 -Dmapreduce.reduce.memory.mb=1024 \
    "-Dmapreduce.reduce.java.opts=-Xmx768m -agentlib:jdwp=transport=dt_socket,server=y,suspend=y,address=5005" \
    /tg /ts-$f > "$C/terasort-f$f.log" 2>&1 &
  jp=$!
  bash "$H/jdbcount.sh" 5005 "$C/jdb-terasort-f$f.log" 1500 | tee "$C/count-terasort-f$f.txt"
  wait $jp; echo "terasort exit $?"
  grep -E "Submitted application|completed successfully|failed|Launched (map|reduce) tasks" "$C/terasort-f$f.log"
  app=$(grep -o "application_[0-9]*_[0-9]*" "$C/terasort-f$f.log" | head -1)
  cp -r "$R/nm-logs/$app" "$C/applogs-terasort-f$f"
  rdir=""; nr=0
  for d in "$C/applogs-terasort-f$f"/container_*; do
    grep -qE "Task:attempt_[0-9]+_[0-9]+_r_000000_0 is done" "$d/syslog" 2>/dev/null && { rdir=$d; nr=$((nr+1)); }
  done
  [ "$nr" = 1 ] || die "reducer container not unique ($nr)"
  cat "$rdir/syslog" "$rdir/syslog.shuffle" 2>/dev/null > "$C/reducer-syslog-f$f.txt"
  s=$(grep -cE "Merger: Merging [0-9]+ sorted segments" "$C/reducer-syslog-f$f.txt")
  m=$(grep -cE "Merger: Merging [0-9]+ intermediate segments out of a total of [0-9]+" "$C/reducer-syslog-f$f.txt")
  mp=$(grep -lE "Task:attempt_[0-9]+_[0-9]+_m_[0-9]+_0 is done" "$C/applogs-terasort-f$f"/container_*/syslog | wc -l)
  echo "PASSCOUNT f=$f app=$app reducerContainer=$(basename "$rdir") sortedLines=$s intermediateLines=$m total=$((s+m)) mapContainers=$mp"
  grep -E "Merger: |MergeManagerImpl: (MergerManager|finalMerge)" "$C/reducer-syslog-f$f.txt" | cut -c1-200 | head -60
  grep -q "completed successfully" "$C/terasort-f$f.log" || die "terasort f=$f failed"
  hdfs dfs -rm -r -skipTrash /ts-$f
done

step "file tree for workload B (B3e step 5, A6): 100 dirs x 200 empty files"
rm -rf "$R/manytree"; mkdir -p "$R/manytree/many"
for d in $(seq -f "d%03g" 0 99); do mkdir "$R/manytree/many/$d"; (cd "$R/manytree/many/$d" && touch $(seq -f "f%03g" 0 199)); done
find "$R/manytree/many" -type f | wc -l
hdfs dfs -put -t 16 "$R/manytree/many" /many || die "put"
hdfs dfs -count /many

for f in 2 100; do
  step "distcp f=$f with the client under jdb on 5006 (B3c B, A8)"
  HADOOP_CLIENT_OPTS="-agentlib:jdwp=transport=dt_socket,server=y,suspend=y,address=5006" hadoop distcp \
    -Dseq.io.sort.mb=1 -Dseq.io.sort.factor=$f -Dmapreduce.task.io.sort.mb=1 -Dmapreduce.task.io.sort.factor=$f \
    /many /many-copy-$f > "$C/distcp-f$f.log" 2>&1 &
  jp=$!
  bash "$H/jdbcount.sh" 5006 "$C/jdb-distcp-f$f.log" 600 | tee "$C/count-distcp-f$f.txt"
  wait $jp; echo "distcp exit $?"
  grep -E "Submitted application|completed successfully|failed|Exception" "$C/distcp-f$f.log" | head -5
  app=$(grep -o "application_[0-9]*_[0-9]*" "$C/distcp-f$f.log" | head -1); cp -r "$R/nm-logs/$app" "$C/applogs-distcp-f$f" 2>/dev/null
  hdfs dfs -count /many-copy-$f
  grep -q "completed successfully" "$C/distcp-f$f.log" || die "distcp f=$f failed"
  hdfs dfs -rm -r -skipTrash /many-copy-$f > /dev/null
done

step "cleanup (B4)"
hdfs dfs -rm -r -skipTrash /tg /many > /dev/null
teardown
du -sh "$R"/* 2>/dev/null
step "done"
