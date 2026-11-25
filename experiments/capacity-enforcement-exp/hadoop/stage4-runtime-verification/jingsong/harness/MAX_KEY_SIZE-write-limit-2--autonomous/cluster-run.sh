#!/usr/bin/env bash
# Cluster tier (case-file B3, with the 2026-11-25 audit amendments) for MAX_KEY_SIZE-write-limit-2--autonomous.
# Runs ON THE NODE. Usage: cluster-run.sh <run-dir>
# Pseudo-distributed HDFS+YARN from a copy of /mydata/jingsong-s4/hadoop-base's distribution, all state under <run-dir>.
# Daemons are started/stopped with --daemon (no ssh to localhost on these nodes). Every command and its output go to
# <run-dir>/logs/cluster/cluster-run.log. The EXIT trap clears the quota and stops every daemon of this run.
set -uo pipefail
RUN=${1:?usage: cluster-run.sh <run-dir>}
S4=$RUN
DIST=/mydata/jingsong-s4/hadoop-base/hadoop-dist/target/hadoop-3.4.2
export JAVA_HOME=/usr/lib/jvm/java-8-openjdk-amd64
export HADOOP_HOME=$S4/hadoop HADOOP_CONF_DIR=$S4/conf HADOOP_LOG_DIR=$S4/logs/daemons HADOOP_PID_DIR=$S4/pids
export PATH=$HADOOP_HOME/bin:$JAVA_HOME/bin:$PATH
OUT=$S4/logs/cluster
mkdir -p "$OUT" "$HADOOP_LOG_DIR" "$HADOOP_PID_DIR"
LOG=$OUT/cluster-run.log
exec > >(tee -a "$LOG") 2>&1
step(){ echo "+ [$(date '+%F %T')] $*"; "$@"; }
die(){ echo "STOP: $*"; exit 9; }
U=$(whoami)
MIB=1048576

daemons(){ ps -eo pid,cmd | grep -E '[N]ameNode|[D]ataNode|[R]esourceManager|[N]odeManager|[D]istributedShell|[Y]arnChild|[M]RAppMaster' | grep -F "$S4" || true; }
stop_all(){
  echo "=== stop_all $(date '+%F %T')"
  hdfs dfsadmin -clrSpaceQuota /tmp/logs 2>/dev/null || true
  yarn --daemon stop nodemanager || true
  yarn --daemon stop resourcemanager || true
  hdfs --daemon stop datanode || true
  hdfs --daemon stop namenode || true
  sleep 5
  left=$(daemons)
  if [ -n "$left" ]; then echo "leftover, killing:"; echo "$left"; echo "$left" | awk '{print $1}' | xargs -r kill; sleep 5; left=$(daemons); fi
  if [ -n "$left" ]; then echo "$left" | awk '{print $1}' | xargs -r kill -9; fi
  echo "after stop, processes of this run:"; daemons; echo "(end)"
}
trap 'rc=$?; echo "EXIT rc=$rc at $(date "+%F %T")"; stop_all' EXIT

echo "=== cluster-run.sh $(date '+%F %T') on $(hostname)"
step java -version
# --- B3a setup ---
[ -x "$DIST/bin/hadoop" ] || die "no distribution at $DIST"
busy=$(ss -ltn | awk '{print $4}' | grep -E ':(9000|9870|9864|9866|9867|9868|8088|8030|8031|8032|8033|8040|8042|13562)$' || true)
[ -z "$busy" ] || die "ports in use: $busy"
step cp -a "$DIST" "$HADOOP_HOME"
step cp -r "$HADOOP_HOME/etc/hadoop" "$HADOOP_CONF_DIR"
cat >> "$HADOOP_CONF_DIR/hadoop-env.sh" <<EOF
export JAVA_HOME=$JAVA_HOME
export HADOOP_HEAPSIZE_MAX=1g
export HADOOP_LOG_DIR=$HADOOP_LOG_DIR
export HADOOP_PID_DIR=$HADOOP_PID_DIR
EOF
prop(){ echo "  <property><name>$1</name><value>$2</value></property>"; }
site(){ echo '<?xml version="1.0"?>'; echo '<configuration>'; while [ $# -gt 0 ]; do prop "$1" "$2"; shift 2; done; echo '</configuration>'; }
site fs.defaultFS hdfs://localhost:9000 hadoop.tmp.dir "$S4/tmp" > "$HADOOP_CONF_DIR/core-site.xml"
site dfs.replication 1 dfs.namenode.name.dir "$S4/nn" dfs.datanode.data.dir "$S4/dn" dfs.blocksize 1048576 \
  > "$HADOOP_CONF_DIR/hdfs-site.xml"
site yarn.nodemanager.aux-services mapreduce_shuffle \
  yarn.nodemanager.env-whitelist JAVA_HOME,HADOOP_COMMON_HOME,HADOOP_HDFS_HOME,HADOOP_CONF_DIR,CLASSPATH_PREPEND_DISTCACHE,HADOOP_YARN_HOME,HADOOP_HOME,PATH,LANG,TZ,HADOOP_MAPRED_HOME \
  yarn.log-aggregation-enable true yarn.nodemanager.remote-app-log-dir /tmp/logs \
  yarn.nodemanager.local-dirs "$S4/nm-local" yarn.nodemanager.log-dirs "$S4/nm-logs" \
  yarn.nodemanager.resource.memory-mb 4096 yarn.scheduler.minimum-allocation-mb 256 \
  yarn.nodemanager.vmem-check-enabled false yarn.nodemanager.delete.debug-delay-sec 600 \
  > "$HADOOP_CONF_DIR/yarn-site.xml"
site mapreduce.framework.name yarn \
  mapreduce.application.classpath '$HADOOP_MAPRED_HOME/share/hadoop/mapreduce/*:$HADOOP_MAPRED_HOME/share/hadoop/mapreduce/lib/*' \
  yarn.app.mapreduce.am.env "HADOOP_MAPRED_HOME=$HADOOP_HOME" mapreduce.map.env "HADOOP_MAPRED_HOME=$HADOOP_HOME" \
  mapreduce.reduce.env "HADOOP_MAPRED_HOME=$HADOOP_HOME" > "$HADOOP_CONF_DIR/mapred-site.xml"
for f in core-site hdfs-site yarn-site mapred-site; do echo "--- $f.xml"; cat "$HADOOP_CONF_DIR/$f.xml"; done
tail -4 "$HADOOP_CONF_DIR/hadoop-env.sh"

# --- B3e step 1-2: format, start ---
step hdfs namenode -format -nonInteractive > "$OUT/format.log" 2>&1 || die "format failed"
grep -E "successfully formatted" "$OUT/format.log"
step hdfs --daemon start namenode
step hdfs --daemon start datanode
step yarn --daemon start resourcemanager
step yarn --daemon start nodemanager
for i in $(seq 1 60); do
  hdfs dfsadmin -safemode get 2>/dev/null | grep -q OFF && yarn node -list 2>/dev/null | grep -q RUNNING && break; sleep 3
done
step jps
step yarn node -list
step hdfs dfsadmin -report | head -20
step hdfs dfs -mkdir -p /tmp/logs /user/$U || die mkdir
step hdfs dfs -chmod 1777 /tmp/logs
NMPID=$(cat "$HADOOP_PID_DIR"/hadoop-$U-nodemanager.pid)
NMLOG=$(ls "$HADOOP_LOG_DIR"/hadoop-$U-nodemanager-*.log)
echo "NM pid $NMPID log $NMLOG"

DSJAR=$HADOOP_HOME/share/hadoop/yarn/hadoop-yarn-applications-distributedshell-3.4.2.jar
appdir(){ hdfs dfs -ls -R /tmp/logs 2>/dev/null | awk '{print $NF}' | grep -E "/$1\$" | head -1; }
wait_agg(){ # $1 app
  local s=""
  for i in $(seq 1 120); do
    s=$(yarn application -status "$1" 2>/dev/null | sed -n 's/.*Log Aggregation Status : *//p')
    case "$s" in SUCCEEDED|FAILED|TIME_OUT|DISABLED|NOT_START) [ "$s" != NOT_START ] && break;; esac
    sleep 5
  done
  echo "$s"
}
ds(){ # $1 label  $2 N bytes
  local label=$1 n=$2
  echo "=== DS run $label N=$n $(date '+%F %T')"
  step yarn jar "$DSJAR" -jar "$DSJAR" -shell_command "head -c $n /dev/zero" -num_containers 2 \
    -container_memory 256 > "$OUT/ds-$label.client.log" 2>&1
  echo "client rc=$?"
  local app
  app=$(grep -oE 'application_[0-9]+_[0-9]+' "$OUT/ds-$label.client.log" | head -1)
  [ -n "$app" ] || { tail -30 "$OUT/ds-$label.client.log"; die "no appId for $label"; }
  grep -E "Application completed|failed|Final State|FinalStatus" "$OUT/ds-$label.client.log" | tail -3
  local st; st=$(wait_agg "$app")
  yarn application -status "$app" > "$OUT/ds-$label.status.txt" 2>&1
  local fin; fin=$(sed -n 's/.*Final-State : *//p' "$OUT/ds-$label.status.txt")
  local d; d=$(appdir "$app")
  local agg=-1
  if [ -n "$d" ]; then
    hdfs dfs -ls -R "$d" > "$OUT/ds-$label.hdfs-ls.txt" 2>&1
    agg=$(hdfs dfs -du -s "$d" | awk '{print $1}')
  fi
  local loc; loc=$(du -sb "$S4/nm-logs/$app" 2>/dev/null | awk '{print $1}')
  ls -lR "$S4/nm-logs/$app" > "$OUT/ds-$label.local-ls.txt" 2>&1
  local hits; hits=$(grep -c "Reach the limit of the buffer" "$NMLOG")
  local c2=container_${app#application_}_01_000002 c3=container_${app#application_}_01_000003
  yarn logs -applicationId "$app" > "$OUT/ds-$label.yarnlogs-all.bin" 2>"$OUT/ds-$label.yarnlogs.err"
  local rb2 rb3 allhits
  rb2=$(yarn logs -applicationId "$app" -containerId "$c2" -log_files stdout 2>/dev/null | tr -cd '\000' | wc -c)
  rb3=$(yarn logs -applicationId "$app" -containerId "$c3" -log_files stdout 2>/dev/null | tr -cd '\000' | wc -c)
  allhits=$(grep -ac "Reach the limit of the buffer" "$OUT/ds-$label.yarnlogs-all.bin")
  grep -a -E '^(Container|LogAggregationType|LogType|LogLength)' "$OUT/ds-$label.yarnlogs-all.bin" > "$OUT/ds-$label.yarnlogs-headers.txt"
  rm -f "$OUT/ds-$label.yarnlogs-all.bin"
  echo "IFCHK,cluster,$label,N=$n,app=$app,final=$fin,aggStatus=$st,aggDir=$d,aggBytes=$agg,localBytes=$loc,readBack2=$rb2,readBack3=$rb3,limitMsgNM=$hits,limitMsgYarnLogs=$allhits" | tee -a "$OUT/ifchk-cluster.csv"
}

# --- B3e step 3: workload A ---
ds A1M $((1*MIB))
ds A16M $((16*MIB))
( "$JAVA_HOME/bin/jstat" -gc "$NMPID" 1000 > "$OUT/jstat-nm-A64M.txt" 2>&1 & echo $! > "$OUT/jstat.pid" )
ds A64M $((64*MIB))
sleep 3; kill "$(cat "$OUT/jstat.pid")" 2>/dev/null; rm -f "$OUT/jstat.pid"

# --- B3e step 4: positive control (amendment: earlier A-run aggregated dirs removed first, so the quota binds on this app) ---
step hdfs dfs -count -q /tmp/logs
step hdfs dfs -rm -r -skipTrash "/tmp/logs/$U" || true
step hdfs dfs -count -q /tmp/logs
step hdfs dfsadmin -setSpaceQuota 32m /tmp/logs
step hdfs dfs -count -q /tmp/logs
NMLINES0=$(wc -l < "$NMLOG")
ds CTRL64M $((64*MIB))
step hdfs dfs -count -q /tmp/logs
tail -n +"$NMLINES0" "$NMLOG" | grep -E "DSQuotaExceeded|QuotaExceeded|quota" | head -20 > "$OUT/ctrl-nm-quota-lines.txt"
echo "IFCHK,ctrlquota,quotaLinesNM=$(tail -n +"$NMLINES0" "$NMLOG" | grep -cE 'DSQuotaExceeded')"
cat "$OUT/ctrl-nm-quota-lines.txt" | cut -c1-600
step hdfs dfsadmin -clrSpaceQuota /tmp/logs
step hdfs dfs -count -q /tmp/logs

# --- B3e step 5: workload B (memory-to-memory merge) ---
mkdir -p "$S4/in"
for i in $(seq -w 1 20); do head -c $MIB /dev/urandom | base64 > "$S4/in/in-$i.txt"; done
step du -sb "$S4/in"
step hdfs dfs -mkdir /in
step hdfs dfs -put "$S4"/in/in-*.txt /in
step yarn jar "$HADOOP_HOME/share/hadoop/mapreduce/hadoop-mapreduce-examples-3.4.2.jar" wordcount \
  -D mapreduce.job.reduces=1 -D mapreduce.reduce.merge.memtomem.enabled=true \
  -D mapreduce.reduce.merge.memtomem.threshold=5 /in /out-b > "$OUT/B.client.log" 2>&1
echo "job rc=$?"
grep -E "completed successfully|failed|Job job_" "$OUT/B.client.log" | tail -3
BAPP=$(grep -oE 'application_[0-9]+_[0-9]+' "$OUT/B.client.log" | head -1)
BST=$(wait_agg "$BAPP")
yarn application -status "$BAPP" > "$OUT/B.status.txt" 2>&1
yarn logs -applicationId "$BAPP" -log_files syslog > "$OUT/B.syslog-all.txt" 2>"$OUT/B.yarnlogs.err"
# A11 (runbook defect 1): the shuffle/merge loggers write to syslog.shuffle (container-log4j.properties:16, 47-56)
yarn logs -applicationId "$BAPP" -log_files syslog.shuffle >> "$OUT/B.syslog-all.txt" 2>>"$OUT/B.yarnlogs.err"
echo "B syslog+syslog.shuffle: $(grep -ac '^LogType:syslog.shuffle' "$OUT/B.syslog-all.txt") syslog.shuffle sections, $(grep -ac '^LogType:syslog$' "$OUT/B.syslog-all.txt") syslog sections"
grep -aE "Initiating Memory-to-Memory merge|Memory-to-Memory merge of the|memToMemMergeOutputsThreshold|MergerManager: memoryLimit" "$OUT/B.syslog-all.txt" > "$OUT/B.merge-lines.txt"
BSUCC=$(hdfs dfs -test -e /out-b/_SUCCESS && echo yes || echo no)
echo "IFCHK,clusterB,app=$BAPP,final=$(sed -n 's/.*Final-State : *//p' "$OUT/B.status.txt"),aggStatus=$BST,success=$BSUCC,initMerges=$(grep -c 'Initiating Memory-to-Memory merge' "$OUT/B.merge-lines.txt"),doneMerges=$(grep -c 'Memory-to-Memory merge of the' "$OUT/B.merge-lines.txt"),limitMsgSyslog=$(grep -ac 'Reach the limit of the buffer' "$OUT/B.syslog-all.txt"),limitMsgNM=$(grep -c 'Reach the limit of the buffer' "$NMLOG")" | tee -a "$OUT/ifchk-cluster.csv"
cat "$OUT/B.merge-lines.txt" | cut -c1-300
gzip -f "$OUT/B.syslog-all.txt"
step hdfs dfs -du -s /in /out-b /tmp/logs
echo "=== workloads done $(date '+%F %T')"
# --- B4: stop (EXIT trap) ---
