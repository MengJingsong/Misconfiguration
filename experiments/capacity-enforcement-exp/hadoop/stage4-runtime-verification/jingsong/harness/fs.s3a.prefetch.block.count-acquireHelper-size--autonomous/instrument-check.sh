#!/usr/bin/env bash
# Known-answer checks of the cluster instruments before run 1: hprof_count.py and the [B histogram line on a JVM holding
# 3 x 32 MiB byte arrays; throttle.py rate. Usage: instrument-check.sh <run-dir>. Log: <run-dir>/logs/cluster/instrument-check.log
set -euo pipefail
RUN=${1:?}; HERE=$(cd "$(dirname "$0")" && pwd); J8=/usr/lib/jvm/java-8-openjdk-amd64
mkdir -p $RUN/logs/cluster $RUN/classes-ka $RUN/dumps
exec > >(tee -a $RUN/logs/cluster/instrument-check.log) 2>&1
set -x
$J8/bin/javac -d $RUN/classes-ka $HERE/KnownArrays.java
$J8/bin/java -Xmx512m -XX:+UseParallelGC -cp $RUN/classes-ka KnownArrays 3 33554432 20 & P=$!
sleep 3
$J8/bin/jcmd $P GC.class_histogram | grep -E '\[B$' | head -1
$J8/bin/jcmd $P GC.heap_dump $RUN/dumps/ka.hprof
python3 -I $HERE/hprof_count.py $RUN/dumps/ka.hprof 33554432 16777216
rm -f $RUN/dumps/ka.hprof
kill $P; wait $P || true
head -c 52428800 /dev/zero | python3 -I $HERE/throttle.py 20
rm -rf $RUN/classes-ka
