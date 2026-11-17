#!/bin/bash
# Setup of the recheck run on pc75 (design S1, S5 step 1). Not upstream code. Logged to /mydata/s4/rowlim-rc/logs/setup.log.
# Usage (on pc75): bash <repo>/.../setup.sh <repo-harness-dir>
set -euo pipefail
RUN=/mydata/s4/rowlim-rc; SRC_H="$1"
mkdir -p $RUN/logs
exec > >(tee -a $RUN/logs/setup.log) 2>&1
set -x
date +%s%3N; hostname; uname -r; java -version 2>&1 | head -1; ant -version
ps -eo cmd | grep '[C]assandraDaemon' || echo "no CassandraDaemon"
ss -ltn | grep -E ':(7000|7199|9042) ' || echo "ports 7000 7199 9042 free"
test ! -e $RUN/tree
cp -a /mydata/s4/cassandra-base $RUN/tree
git -C $RUN/tree describe --tags; git -C $RUN/tree status --short | head -5
ls $RUN/tree/build/apache-cassandra-5.0.9*.jar $RUN/tree/build/lib/jars/byteman-4.0.20.jar
mkdir -p $RUN/drv && unzip -q -o $RUN/tree/lib/cassandra-driver-internal-only-3.29.0.zip -d $RUN/drv && ls $RUN/drv
rm -rf $RUN/harness && cp -a "$SRC_H" $RUN/harness && (cd $RUN/harness && md5sum * | tee $RUN/logs/harness.md5)
python3 -I -c "import sys; sys.path.insert(0, '$RUN/drv/cassandra-driver-3.29.0'); import cassandra; print('driver', cassandra.__version__)"
df -h /mydata | tail -1; free -g | head -2; swapon --show
date +%s%3N
