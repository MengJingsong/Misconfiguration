#!/usr/bin/env bash
# Type-check the Byteman rules against the built classes (B3d instrument) and compile the helper. usage: instrument-check.sh <tree>
set -eu
H=$(cd "$(dirname "$0")" && pwd); T=${1:?}; W=$(mktemp -d)
javac -d "$W" "$H/SrHelper.java"
BM=$T/build/lib/jars/byteman-4.0.20.jar
java -cp "$BM:$T/build/lib/jars/byteman-submit-4.0.20.jar:$T/build/apache-cassandra-5.0.9-SNAPSHOT.jar:$T/build/lib/jars/*:$W" org.jboss.byteman.check.TestScript -p stage4 "$H/sr.btm"
rm -rf "$W"
