#!/usr/bin/env bash
# Compile B19Client / B19Sample (client side only; lz4-java from the 5.0.9 build's lib).
B=/mydata/s4/cassandra-base; H=$(cd "$(dirname "$0")" && pwd)
mkdir -p /mydata/s4/B19/cls /mydata/s4/B19/cls2 && javac -cp "$B/lib/lz4-java-1.10.1.jar" -d /mydata/s4/B19/cls2 "$H/B19Client.java" && javac -cp "$B/lib/lz4-java-1.10.1.jar" -d /mydata/s4/B19/cls "$H/B19Client.java" "$H/B19Sample.java" && echo built
