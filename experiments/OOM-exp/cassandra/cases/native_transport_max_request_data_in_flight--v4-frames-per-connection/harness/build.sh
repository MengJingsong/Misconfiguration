#!/usr/bin/env bash
# Compile B9Load / B9Sample against the jars of the read-only 5.0.9 build.
B=/mydata/s4/cassandra-base; J=$B/build/lib/jars
H=$(cd "$(dirname "$0")" && pwd)
mkdir -p /mydata/s4/b9-w1/cls && javac -cp "$J/*:$B/lib/*" -d /mydata/s4/b9-w1/cls "$H/B9Load.java" "$H/B9Sample.java" && echo built
