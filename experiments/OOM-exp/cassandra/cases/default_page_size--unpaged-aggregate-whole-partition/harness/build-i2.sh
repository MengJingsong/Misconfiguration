#!/usr/bin/env bash
# U10 arm I2 diagnostic build: a separate copy of the tree with harness/i2.diff applied, then `ant jar` (never in a tree a node runs from).
set -euo pipefail
ROOT=/mydata/s4/u10-w4
rm -rf $ROOT/tree-i2; cp -a $ROOT/tree $ROOT/tree-i2; cd $ROOT/tree-i2
patch -p1 < $ROOT/harness/i2.diff
rm -f build/classes/main/org/apache/cassandra/service/pager/AggregationQueryPager*.class
ant jar > $ROOT/runs/build-i2.log 2>&1 || { tail -30 $ROOT/runs/build-i2.log; exit 1; }
tail -3 $ROOT/runs/build-i2.log
ls -la build/classes/main/org/apache/cassandra/service/pager/AggregationQueryPager.class
sha256sum $ROOT/tree/build/apache-cassandra-*.jar $ROOT/tree-i2/build/apache-cassandra-*.jar
