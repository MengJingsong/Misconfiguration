#!/usr/bin/env bash
# B16 setup on ms0611 (stage 2). The build was copied from ms0617:/mydata/s4/cassandra-base by tar over ssh through the
# controller (ms0611 cannot ssh to ms0617) and its jar checked; this copies it to the work root (the base stays read
# only), keeps a pristine conf, and compiles the client and the sampler. The harness is rsynced to $ROOT/harness first.
set -euo pipefail
ROOT=/mydata/s4/b16-w4
mkdir -p "$ROOT"/{runs,cls,repo-logs}
[ -d "$ROOT/tree" ] || cp -a /mydata/s4/cassandra-base "$ROOT/tree"
[ -d "$ROOT/conf-pristine" ] || cp -a "$ROOT/tree/conf" "$ROOT/conf-pristine"
J=$ROOT/tree/build/lib/jars
CP="$J/cassandra-driver-core-3.12.1-shaded.jar:$J/guava-32.0.1-jre.jar:$J/metrics-core-4.2.28.jar:$ROOT/tree/lib/*"
javac -cp "$CP" -d "$ROOT/cls" "$ROOT/harness/B16Load.java" "$ROOT/harness/C2Sampler.java"
sha256sum "$ROOT"/tree/build/apache-cassandra-*.jar
echo setup ok
