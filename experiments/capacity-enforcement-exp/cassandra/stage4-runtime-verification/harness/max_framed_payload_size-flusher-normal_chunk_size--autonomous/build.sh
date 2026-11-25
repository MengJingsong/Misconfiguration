#!/usr/bin/env bash
# o132 stage 4 (max_framed_payload_size-flusher-normal_chunk_size--autonomous): patch, build, compile probes, instrument checks.
# Runs ON the node. W = run folder; $W/src = copy of /mydata/s4/cassandra-base plus the pinned src/ tree.
set -euo pipefail
W=${W:-/mydata/jingsong-cass-s4/o132}
H=$W/harness
LOG=$W/logs/build.log
exec > >(tee -a "$LOG") 2>&1
run() { echo "+ [$(date +%s%3N)] $*"; "$@"; }
echo "=== build.sh start $(date) on $(hostname) $(uname -m)"
run java -version
run ant -version
cd $W/src
F=src/java/org/apache/cassandra/transport/Flusher.java
run sha256sum $F
# Apply the shared test patch (case file B, "Shared test patch"): replace Flusher.java:46-49.
python3 - "$F" "$H/Flusher-patch.java.txt" <<'EOF'
import sys
f, p = sys.argv[1], sys.argv[2]
t = open(f).read()
old = """    @VisibleForTesting
    public static final int MAX_FRAMED_PAYLOAD_SIZE =
        Math.min(BufferPool.NORMAL_CHUNK_SIZE,
                 FrameEncoder.Payload.MAX_SIZE - Math.max(FrameEncoderCrc.HEADER_AND_TRAILER_LENGTH, FrameEncoderLZ4.HEADER_AND_TRAILER_LENGTH));
"""
new = open(p).read()
if new in t:
    print("patch already applied"); sys.exit(0)
assert t.count(old) == 1, "stock text not found"
open(f, "w").write(t.replace(old, new))
print("patch applied")
EOF
run sed -n 44,53p $F
run sha256sum $F
run ant -Dno-checkstyle=true jar </dev/null
run unzip -l build/apache-cassandra-5.0.9-SNAPSHOT.jar 'org/apache/cassandra/transport/Flusher.class'
export CASSANDRA_HOME=$W/src
set +u; . $W/src/bin/cassandra.in.sh; set -u
echo "$CLASSPATH" > $W/classpath.txt
mkdir -p $W/probe/classes $W/probe/src/org/apache/cassandra/transport
cp $H/FlusherProbe.java $W/probe/src/org/apache/cassandra/transport/
cp $H/ClusterProbe.java $H/pause-proxy.py $W/probe/
run javac -cp "$CLASSPATH" -d $W/probe/classes $W/probe/src/org/apache/cassandra/transport/FlusherProbe.java
run javac -cp "$CLASSPATH" -d $W/probe/classes $W/probe/ClusterProbe.java
run python3 -m py_compile $W/probe/pause-proxy.py
echo "=== build.sh done $(date)"
