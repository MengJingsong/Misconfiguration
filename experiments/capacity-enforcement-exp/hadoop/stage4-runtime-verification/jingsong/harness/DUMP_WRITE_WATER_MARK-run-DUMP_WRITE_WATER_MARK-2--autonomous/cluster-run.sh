#!/usr/bin/env bash
# Cluster tier (B3 + amendment 2026-11-25) for DUMP_WRITE_WATER_MARK-run-DUMP_WRITE_WATER_MARK-2--autonomous. Runs ON the node.
# Usage: cluster-run.sh jars | setup | point <P1..P5> | teardown | clean-bulk.   Log: $S4/logs/cluster-run.log
set -uo pipefail
S4=/mydata/jingsong-s4/DUMP_WRITE_WATER_MARK-run-DUMP_WRITE_WATER_MARK-2--autonomous-run1
DIST=/mydata/jingsong-s4/hadoop-base/hadoop-dist/target/hadoop-3.4.2
SRC=$S4/src; MOD=hadoop-hdfs-project/hadoop-hdfs-nfs
OFC=$SRC/$MOD/src/main/java/org/apache/hadoop/hdfs/nfs/nfs3/OpenFileCtx.java
H=$S4/hadoop; CONF=$S4/conf; JARS=$S4/jars; MNT=$S4/mnt; DUMP=$S4/nfsdump; OUT=$S4/logs/cluster; HLOG=$S4/logs/hadoop
U=$(whoami); NFSJAR=$H/share/hadoop/hdfs/hadoop-hdfs-nfs-3.4.2.jar
export JAVA_HOME=/usr/lib/jvm/java-8-openjdk-amd64
export HADOOP_HOME=$H HADOOP_CONF_DIR=$CONF
export PATH=$JAVA_HOME/bin:$H/bin:$PATH
mkdir -p "$OUT" "$HLOG"
exec > >(tee -a "$S4/logs/cluster-run.log") 2>&1
run() { echo "+ [$(date '+%F %T %Z')] $*"; "$@"; }
fail() { echo "STOP: $*"; exit 1; }
prop() { echo "  <property><name>$1</name><value>$2</value></property>"; }
nfspid() { jps 2>/dev/null | awk '$2=="Nfs3"{print $1}'; }
registered() { rpcinfo -p localhost 2>/dev/null | grep -qE '100003 +3 +tcp +2049'; }
gwlog() { ls "$HLOG"/hadoop-$U-nfs3-*.log 2>/dev/null | head -1; }
jarconst() { javap -c -p -constants -classpath "$1" org.apache.hadoop.hdfs.nfs.nfs3.OpenFileCtx | grep -B1 'putstatic.*DUMP_WRITE_WATER_MARK' | head -1; }

do_jars() {
  echo "=== jars $(date '+%F %T %Z')"; mkdir -p "$JARS"; cd "$SRC" || fail "no src"
  [ -z "$(git status --short -- "$MOD/src/main")" ] || fail "main source not clean"
  run cp "$DIST/share/hadoop/hdfs/hadoop-hdfs-nfs-3.4.2.jar" "$JARS/nfs-m1.jar"
  for v in m4 m1g; do
    case $v in m4) val='4 * 1024 * 1024';; m1g) val='1024L * 1024 * 1024';; esac
    run sed -i "73s/private static long DUMP_WRITE_WATER_MARK = 1024 \* 1024;/private static long DUMP_WRITE_WATER_MARK = $val;/" "$OFC"
    run sed -n 73p "$OFC"; run git diff --stat -- "$MOD/src/main"
    run mvn -B -o -q package -pl "$MOD" -Dmaven.test.skip=true -Dmaven.javadoc.skip=true > "$OUT/mvn-jar-$v.log" 2>&1 \
      || { git checkout -- "$OFC"; fail "jar build $v"; }
    run cp "$SRC/$MOD/target/hadoop-hdfs-nfs-3.4.2.jar" "$JARS/nfs-$v.jar"
    run git checkout -- "$OFC"
  done
  run git status --short -- "$MOD/src/main"
  for j in m1 m4 m1g; do echo "javap $j: $(jarconst "$JARS/nfs-$j.jar")" | tee "$OUT/javap-$j.txt"; done
  run ls -l "$JARS"
}

do_setup() {
  echo "=== setup $(date '+%F %T %Z') on $(hostname)"
  ss -ltnu | grep -E ':(2049|4242|9000|9870|9864|9866|9867)\b' && fail "port in use"
  run rpcinfo -p localhost
  run systemctl is-active rpcbind
  [ -d "$H" ] || run cp -a "$DIST" "$H"
  [ -e "$NFSJAR.stock" ] || run cp "$NFSJAR" "$NFSJAR.stock"
  rm -rf "$CONF"; run cp -r "$H/etc/hadoop" "$CONF"
  mkdir -p "$S4/tmp" "$S4/nn" "$S4/dn" "$S4/pids" "$MNT" "$DUMP"
  { echo '<?xml version="1.0"?>'; echo '<configuration>'
    prop fs.defaultFS hdfs://localhost:9000
    prop hadoop.tmp.dir "$S4/tmp"
    prop hadoop.proxyuser.$U.groups '*'
    prop hadoop.proxyuser.$U.hosts '*'
    echo '</configuration>'; } > "$CONF/core-site.xml"
  { echo '<?xml version="1.0"?>'; echo '<configuration>'
    prop dfs.replication 1
    prop dfs.namenode.name.dir "file://$S4/nn"
    prop dfs.datanode.data.dir "file://$S4/dn"
    prop nfs.dump.dir "$DUMP"
    prop nfs.file.dump true
    prop nfs.exports.allowed.hosts '* rw'
    prop nfs.superuser "$U"
    prop dfs.namenode.accesstime.precision 3600000
    prop nfs.wtmax 1048576
    echo '</configuration>'; } > "$CONF/hdfs-site.xml"
  cat >> "$CONF/hadoop-env.sh" <<EOT
export JAVA_HOME=$JAVA_HOME
export HADOOP_LOG_DIR=$HLOG
export HADOOP_PID_DIR=$S4/pids
export HDFS_NFS3_OPTS="-Xmx512m -XX:+UseG1GC"
EOT
  echo 'log4j.logger.org.apache.hadoop.hdfs.nfs.nfs3.OpenFileCtx=DEBUG' >> "$CONF/log4j.properties"
  run cat "$CONF/core-site.xml" "$CONF/hdfs-site.xml"; run tail -4 "$CONF/hadoop-env.sh"; run tail -1 "$CONF/log4j.properties"
  run hdfs namenode -format -nonInteractive > "$OUT/nn-format.log" 2>&1 || fail "format"
  run hdfs --daemon start namenode
  run hdfs --daemon start datanode
  run hdfs dfsadmin -safemode wait
  for i in $(seq 1 30); do hdfs dfsadmin -report 2>/dev/null | grep -q 'Live datanodes (1)' && break; sleep 2; done
  run hdfs dfsadmin -report | head -12
  run hdfs dfs -ls -d /
  run jps
}

stop_gateway() {
  if mountpoint -q "$MNT"; then run sudo umount "$MNT" || run sudo umount -f -l "$MNT"; fi
  if [ -n "$(nfspid)" ]; then run hdfs --daemon stop nfs3; sleep 3
    local p; p=$(nfspid); [ -n "$p" ] && { echo "gateway still alive, kill -9 $p"; kill -9 $p; sleep 1; }; fi
  true
}

# point NAME JAR WSIZE G
do_point() {
  local N=$1 J=$2 W=$3 G=$4 O=$OUT/$1
  rm -rf "$O"; mkdir -p "$O"
  echo "=== point $N jar=$J wsize=$W G=$G $(date '+%F %T %Z')"
  stop_gateway
  hdfs dfs -test -e /o17-file && run hdfs dfs -rm -skipTrash /o17-file
  run cp "$JARS/nfs-$J.jar" "$NFSJAR.new"; run mv -f "$NFSJAR.new" "$NFSJAR"
  echo "jar constant in use: $(jarconst "$NFSJAR")" | tee "$O/jar-const.txt"
  local GL; GL=$(gwlog); local L0=0; [ -n "$GL" ] && L0=$(wc -l < "$GL")
  run hdfs --daemon start nfs3
  for i in $(seq 1 30); do sleep 2; registered && break; done
  registered || { tail -20 "$(gwlog)"; fail "nfs3 not registered with system rpcbind (runbook defect)"; }
  GL=$(gwlog); local PID; PID=$(nfspid); echo "gateway pid $PID log $GL from line $((L0+1))"
  run ps -o pid,args -p "$PID" | cut -c1-400
  run rpcinfo -p localhost
  run ls -la "$DUMP"
  run sudo mount -t nfs -o "vers=3,proto=tcp,nolock,noacl,soft,timeo=600,retrans=2,wsize=$W" localhost:/ "$MNT" || fail "mount"
  run grep " $MNT " /proc/mounts | tee "$O/mount.txt"
  sleep 2
  jcmd "$PID" GC.class_histogram > "$O/histo-baseline.txt" 2>&1
  echo "BASELINE [B=$(awk '$4=="[B"{print $3}' "$O/histo-baseline.txt")" | tee "$O/histo-summary.txt"
  sleep 5; jcmd "$PID" GC.class_histogram > "$O/histo-baseline2.txt" 2>&1
  echo "BASELINE2 [B=$(awk '$4=="[B"{print $3}' "$O/histo-baseline2.txt") (jitter check, amendment D1)" | tee -a "$O/histo-summary.txt"
  jstat -gc "$PID" 1000 > "$O/jstat.log" 2>&1 & local JS=$!
  ( while sleep 1; do echo "$(date +%T),$(stat --format=%s "$DUMP"/* 2>/dev/null | paste -sd+ | bc 2>/dev/null || echo 0),$(ls "$DUMP" | wc -l)"; done ) > "$O/disk.csv" 2>&1 & local DS=$!
  python3 -I "$S4/harness/ooo.py" "$MNT/o17-file" "$G" "$S4/ref" > "$O/ooo.log" 2>&1 & local PY=$!
  echo "samplers jstat=$JS disk=$DS ooo=$PY"
  local t0; t0=$(date +%s)
  while ! grep -q GAP-SENT "$O/ooo.log"; do
    kill -0 $PY 2>/dev/null || break
    [ $(( $(date +%s) - t0 )) -gt 300 ] && { echo "no GAP-SENT after 300 s"; break; }
    sleep 1; done
  run cat "$O/ooo.log"
  if grep -q GAP-SENT "$O/ooo.log"; then
    sleep 10
    jcmd "$PID" GC.class_histogram > "$O/histo-window.txt" 2>&1
    local b0 b1; b0=$(awk '$4=="[B"{print $3}' "$O/histo-baseline.txt"); b1=$(awk '$4=="[B"{print $3}' "$O/histo-window.txt")
    echo "WINDOW [B=$b1 delta=$((b1-b0)) WriteCtx=$(awk '$4 ~ /WriteCtx$/{print $2}' "$O/histo-window.txt")" | tee -a "$O/histo-summary.txt"
    { date +%T; ls -l "$DUMP"; du -b "$DUMP"/* 2>/dev/null; } | tee "$O/dump-window.txt"
    jstat -gc "$PID" | tee "$O/jstat-window.txt"
  fi
  wait $PY; echo "ooo exit $?"; run cat "$O/ooo.log"
  sleep 2
  kill $JS $DS 2>/dev/null; wait $JS $DS 2>/dev/null
  { date +%T; ls -l "$DUMP"; } | tee "$O/dump-after.txt"
  local EXP=$((G + 1048576))
  run sudo umount "$MNT"
  run sudo mount -t nfs -o "vers=3,proto=tcp,nolock,noacl,soft,timeo=600,retrans=2,wsize=$W" localhost:/ "$MNT" || fail "remount"
  echo "nfs-read bytes $(stat --format=%s "$MNT/o17-file") expected $EXP cmp: $(cmp "$MNT/o17-file" "$S4/ref" >/dev/null 2>&1 && echo identical || cmp "$MNT/o17-file" "$S4/ref" 2>&1 | head -1)" | tee "$O/integrity.txt"
  run hdfs dfs -stat '%b %n' /o17-file | tee "$O/hdfs-stat.txt"
  hdfs dfs -cat /o17-file > "$S4/readback" 2>"$O/cat.err"
  echo "hdfs-cat bytes $(stat --format=%s "$S4/readback") expected $EXP cmp: $(cmp "$S4/readback" "$S4/ref" >/dev/null 2>&1 && echo identical || cmp "$S4/readback" "$S4/ref" 2>&1 | head -1)" | tee -a "$O/integrity.txt"
  rm -f "$S4/readback" "$S4/ref"
  tail -n +$((L0 + 1)) "$GL" > "$O/nfs3.log"
  local Lseg; Lseg=$(wc -l < "$O/nfs3.log")
  {
    echo "maxNewValue $(grep -o 'new value: [0-9]*' "$O/nfs3.log" | awk '{print $3}' | sort -n | tail -1)"
    echo "updates $(grep -c 'Update nonSequentialWriteInMemory' "$O/nfs3.log")"
    echo "incrementSizes $(grep -o 'Update nonSequentialWriteInMemory by [0-9]*' "$O/nfs3.log" | awk '{print $4}' | sort -n | uniq -c | tr '\n' ';')"
    echo "createDump $(grep -c 'Create dump file' "$O/nfs3.log")"
    echo "askDumper $(grep -c 'Asking dumper to dump' "$O/nfs3.log")"
    echo "dumpRounds $(grep -c 'Before dump, nonSequentialWriteInMemory' "$O/nfs3.log")"
    echo "beforeValues $(grep -o 'Before dump, nonSequentialWriteInMemory == [0-9]*' "$O/nfs3.log" | awk '{print $NF}' | sort -n | uniq -c | tr '\n' ';')"
    echo "afterValues $(grep -o 'After dump, nonSequentialWriteInMemory == [0-9]*' "$O/nfs3.log" | awk '{print $NF}' | sort -n | uniq -c | tr '\n' ';')"
    echo "dumperWokeUp $(grep -c 'Dumper woke up' "$O/nfs3.log")"
    echo "OOM $(grep -c OutOfMemoryError "$O/nfs3.log")"
    echo "dumpErrors $(grep -cE 'Got failure when creating dump|Dump data failed|Dumper got Throwable' "$O/nfs3.log")"
    echo "logLines $Lseg"
  } | tee "$O/counter-summary.txt"
  grep -E 'Create dump file|Before dump|After dump|Asking dumper|Dumper woke' "$O/nfs3.log" > "$O/nfs3-dump-excerpt.log"
  stop_gateway
  run hdfs dfs -rm -skipTrash /o17-file
  gzip -f "$O/nfs3.log"
  echo "=== point $N end $(date '+%F %T %Z')"
}

do_teardown() {
  echo "=== teardown $(date '+%F %T %Z')"
  stop_gateway
  [ -e "$NFSJAR.stock" ] && run cp "$NFSJAR.stock" "$NFSJAR"
  run hdfs --daemon stop datanode; run hdfs --daemon stop namenode; sleep 3
  for v in 1 2 3; do sudo rpcinfo -d 100005 $v 2>/dev/null; done; sudo rpcinfo -d 100003 3 2>/dev/null
  run rpcinfo -p localhost
  run jps
  ps -eo pid,cmd | grep -E '[N]ameNode|[D]ataNode|[N]fs3|[P]ortmap|[o]oo\.py|[j]stat' | cut -c1-200 || echo "no daemon left"
  mountpoint -q "$MNT" && echo "MOUNT STILL PRESENT" || echo "mount gone"
  run systemctl is-active rpcbind
}

do_clean_bulk() {
  echo "=== clean bulk $(date '+%F %T %Z')"
  run du -sh "$S4"
  run rm -rf "$S4/src" "$S4/hadoop" "$S4/nn" "$S4/dn" "$S4/tmp" "$S4/nfsdump" "$S4/jars" "$S4/unit-dump" "$S4/ref" "$S4/readback" "$S4/conf"
  run rmdir "$MNT"
  run du -sh "$S4"; run ls -la "$S4" "$S4/logs"
}

case ${1:-} in
  jars) do_jars ;; setup) do_setup ;; teardown) do_teardown ;; clean-bulk) do_clean_bulk ;;
  point) case ${2:-} in
      P1) do_point P1 m1 1048576 67108864 ;;
      P2) do_point P2 m1 1048576 524288 ;;
      P3) do_point P3 m1 65536 67108864 ;;
      P4) do_point P4 m4 1048576 67108864 ;;
      P5) do_point P5 m1g 1048576 67108864 ;;
      *) fail "point what?" ;; esac ;;
  *) fail usage ;;
esac
