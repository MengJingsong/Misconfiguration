#!/usr/bin/env bash
# R14 setup on pc91 (stage 2), adapted from U5 setup.sh: ROOT = /mydata/s4/r14 (design §2).
# Copies the built 5.0.9 tree out of /mydata/s4/cassandra-base (read only), keeps a pristine conf, builds the
# intervention tree tree-I (MultiCBuilder pre-allocation check, compiled against the stock jar; no ant).
# The harness itself is copied to $ROOT/h by scp before this runs.
set -euo pipefail
ROOT=/mydata/s4/r14; H=$ROOT/h
mkdir -p "$ROOT/runs"
[ -d "$ROOT/tree" ] || cp -a /mydata/s4/cassandra-base "$ROOT/tree"
[ -d "$ROOT/conf-pristine" ] || cp -a "$ROOT/tree/conf" "$ROOT/conf-pristine"
JAR=build/apache-cassandra-5.0.9-SNAPSHOT.jar
if [ ! -d "$ROOT/tree-I" ]; then
  W=$ROOT/patchwork; rm -rf "$W"; mkdir -p "$W/src" "$W/patchcls"
  ORIG=$ROOT/tree/src/java/org/apache/cassandra/db/MultiCBuilder.java
  cp "$ORIG" "$W/src/MultiCBuilder.java.orig"
  python3 - "$W/src/MultiCBuilder.java.orig" "$W/src/MultiCBuilder.java" <<'EOF'
import sys
src = open(sys.argv[1]).read()
chk = ('            checkUpdateable();\n'
       '            long u5Limit = Long.getLong("u5.max_in_product", -1L);\n'
       '            if (u5Limit > 0 && (long) Math.max(1, elementsList.size()) * values.size() > u5Limit)\n'
       '                throw new org.apache.cassandra.exceptions.InvalidRequestException(\n'
       '                    "u5: IN cartesian product " + Math.max(1, elementsList.size()) + " x " + values.size() + " exceeds " + u5Limit);\n')
out = []; n = 0
lines = src.split('\n'); i = 0
while i < len(lines):
    l = lines[i]; out.append(l)
    if ('public MultiCBuilder addEachElementToAll(List<ByteBuffer> values)' in l or
            'public MultiCBuilder addAllElementsToAll(List<List<ByteBuffer>> values)' in l) and 'abstract' not in l:
        # expect "{" then "checkUpdateable();"
        if lines[i + 1].strip() == '{' and lines[i + 2].strip() == 'checkUpdateable();':
            out.append(lines[i + 1]); out.append(chk.rstrip('\n')); i += 3; n += 1; continue
    i += 1
assert n == 2, n
open(sys.argv[2], 'w').write('\n'.join(out))
print('patched', n, 'methods')
EOF
  ( cd "$W/src" && diff -u MultiCBuilder.java.orig MultiCBuilder.java > "$W/u5-pre-allocation-check.patch" || true )
  javac -nowarn -d "$W/patchcls" -cp "$ROOT/tree/$JAR:$ROOT/tree/lib/*" "$W/src/MultiCBuilder.java"
  cp -a "$ROOT/tree" "$ROOT/tree-I"
  ( cd "$W/patchcls" && jar uf "$ROOT/tree-I/$JAR" org/apache/cassandra/db/MultiCBuilder*.class )
  ls "$W/patchcls/org/apache/cassandra/db/"
fi
mkdir -p "$ROOT/cls"; javac -d "$ROOT/cls" "$H/C2Sampler.java"
sha256sum "$ROOT/tree/$JAR" "$ROOT/tree-I/$JAR" | tee "$ROOT/jars.sha256"
echo setup ok
