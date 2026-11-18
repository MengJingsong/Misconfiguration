#!/usr/bin/env bash
# Compile B13Sample / B13Load against the jars of the read-only 5.0.9 build.
B=/mydata/s4/cassandra-base; J=$B/build/lib/jars
H=$(cd "$(dirname "$0")" && pwd)
mkdir -p /mydata/s4/b13-w3/cls && javac -cp "$J/*:$B/lib/*" -d /mydata/s4/b13-w3/cls "$H/B13Load.java" "$H/B13Sample.java" && echo built
