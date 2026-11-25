#!/usr/bin/env bash
# Unit tier (B2, A1-A4) for order 31 on pc91. Usage: unit-run.sh   (logs everything to $R/logs/unit/unit-run.log)
set -uo pipefail
R=/mydata/jingsong-s4/dfs.datanode.pmem.cache.dirs-chooseVolume-availableBytes-run1
L=$R/logs/unit; mkdir -p $L
exec > >(tee -a $L/unit-run.log) 2>&1
export JAVA_HOME=/usr/lib/jvm/java-8-openjdk-amd64 PATH=/usr/lib/jvm/java-8-openjdk-amd64/bin:$PATH
M=$R/src/hadoop-hdfs-project/hadoop-hdfs
T=$M/src/test/java/org/apache/hadoop/hdfs/server/datanode/fsdataset/impl/TestPmemCapO31.java
echo "== $(date) unit-run start; host $(hostname)"; java -version 2>&1; mvn -v | head -1
set -x
cp $R/harness/TestPmemCapO31.java $T
git -C $R/src status --short
cd $M
mvn -B test -Dtest=TestPmemCapO31 -Dsurefire.failIfNoSpecifiedTests=false > $L/mvn-test.log 2>&1
echo "mvn exit $?"
set +x
grep -E "Tests run:|BUILD|ERROR\]" $L/mvn-test.log | tail -15
cp $M/target/surefire-reports/*TestPmemCapO31* $L/ 2>/dev/null; ls -la $L
grep -h "^O31," $L/*TestPmemCapO31-output.txt | grep -v U2POLL
echo "loader lines:"; grep -h "Initializing cache loader" $L/*TestPmemCapO31-output.txt | sort | uniq -c
ps -u $(id -un) -o pid=,args= | awk '/surefire/ && !/awk/' ; echo "(no surefire JVM if empty)"
du -sh $M/target/test/data/dfs/o31 2>/dev/null; rm -rf $M/target/test/data/dfs/o31 $M/target/test/data/o31
echo "== $(date) unit-run end"
