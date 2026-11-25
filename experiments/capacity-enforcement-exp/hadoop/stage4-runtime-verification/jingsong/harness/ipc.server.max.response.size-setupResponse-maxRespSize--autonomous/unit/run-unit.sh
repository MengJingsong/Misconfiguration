#!/usr/bin/env bash
# Unit tier (B2e) for ipc.server.max.response.size-setupResponse-maxRespSize--autonomous.
# Runs ON pc91. Usage: run-unit.sh <RUN dir> <harness dir>
set -euo pipefail
RUN=${1:?RUN}; H=${2:?harness}
export JAVA_HOME=/usr/lib/jvm/java-8-openjdk-amd64 PATH=/usr/lib/jvm/java-8-openjdk-amd64/bin:$PATH YARN_IGNORE_ENGINES=true
OUT=$RUN/unit-out; mkdir -p $OUT
exec > >(tee -a $OUT/run-unit.log) 2>&1
echo "== $(date) host $(hostname)"; java -version 2>&1; mvn -v | head -1
M=$RUN/src/hadoop-common-project/hadoop-common
cp -v $H/TestMaxRespSizeVerification.java $M/src/test/java/org/apache/hadoop/ipc/
git -C $RUN/src status --short
rm -f $M/target/maxresp-*.csv
for rep in ${REPS:-1 2 3}; do
  echo "== rep $rep $(date)"
  ( cd $RUN/src && set -x && mvn -B -pl hadoop-common-project/hadoop-common test \
      -Dtest=TestMaxRespSizeVerification -DfailIfNoTests=false -Dmaxresp.rep=$rep \
      -Dmaven.javadoc.skip=true ) > $OUT/mvn-rep$rep.log 2>&1 || echo "mvn exit $? (rep $rep)"
  grep -E "Tests run:|BUILD|ERROR" $OUT/mvn-rep$rep.log | tail -5
  cp $M/target/surefire-reports/*TestMaxRespSizeVerification-output.txt $OUT/output-rep$rep.txt 2>/dev/null || true
  cp $M/target/surefire-reports/*TestMaxRespSizeVerification.txt $OUT/report-rep$rep.txt 2>/dev/null || true
done
cp $M/target/maxresp-*.csv $OUT/
echo "== leftover surefire JVMs:"; jps -l | grep -i surefire || echo none
# remove the added test file from the local copy (B4)
rm -v $M/src/test/java/org/apache/hadoop/ipc/TestMaxRespSizeVerification.java
git -C $RUN/src status --short
echo "== done $(date)"
