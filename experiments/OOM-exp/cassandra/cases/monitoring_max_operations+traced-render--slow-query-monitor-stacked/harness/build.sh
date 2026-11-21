#!/usr/bin/env bash
# R12 (copied from B11) stage 2 build on the node. Base tree already made by copy-source.sh + `ant jar` (see §3).
# This script makes the intervention tree from the built base, applies iv.patch, rebuilds, checks javap.
# Usage: build.sh <workdir>   (e.g. /mydata/s4/r12-w5; expects <workdir>/cassandra-base built and <workdir>/harness/iv.patch)
set -euo pipefail
W=${1:?workdir}
cd "$W"
[ -e cassandra-iv ] && { echo "cassandra-iv exists" >&2; exit 1; }
cp -a cassandra-base cassandra-iv
cd cassandra-iv
git apply --recount "$W/harness/iv.patch"
git diff --stat
rm -f build/classes/main/org/apache/cassandra/transport/messages/ExecuteMessage*.class
ant jar
J=build/apache-cassandra-5.0.9-SNAPSHOT.jar
echo "iv duplicate count:   $(javap -p -c -classpath $J org.apache.cassandra.transport.messages.ExecuteMessage | grep -c ByteBuffer.duplicate || true)"
echo "base duplicate count: $(javap -p -c -classpath $W/cassandra-base/$J org.apache.cassandra.transport.messages.ExecuteMessage | grep -c ByteBuffer.duplicate || true)"
