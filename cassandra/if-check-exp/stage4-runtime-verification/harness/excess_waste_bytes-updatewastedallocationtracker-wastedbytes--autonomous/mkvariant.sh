#!/usr/bin/env bash
# usage: mkvariant.sh <name> <literal-for-EXCESS_WASTE_BYTES | stock> [instrument=1]      (run copy: $C, default ~/s4-ew; output: ~/s4-ew-var/<name>/)
# Compiles a patched AtomicBTreePartition (+ inner classes, + S4Waste) into a class directory that is put BEFORE build/classes/main on the
# class path. Only line 63 (the literal) changes, plus the S4Waste counter calls (instrument=1); the run copy's source tree is not edited
# (the patched source is a temp file). "stock" with instrument=0 produces nothing (the unpatched build classes are used).
set -euo pipefail
name=$1; lit=$2; ins=${3:-1}
C=${C:-$HOME/s4-ew}; H=$(cd "$(dirname "$0")" && pwd); O=$HOME/s4-ew-var/$name; W=$HOME/s4-ew-var/_src/$name
rm -rf "$O" "$W"; mkdir -p "$O" "$W/org/apache/cassandra/db/partitions"
S=$C/src/java/org/apache/cassandra/db/partitions/AtomicBTreePartition.java
python3 - "$S" "$W/org/apache/cassandra/db/partitions/AtomicBTreePartition.java" "$lit" "$ins" <<'PY'
import sys
src, dst, lit, ins = sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4] == '1'
t = open(src).read()
def rep(a, b):
    global t
    assert t.count(a) == 1, a
    t = t.replace(a, b)
if lit != 'stock':
    rep('EXCESS_WASTE_BYTES = 10 * 1024 * 1024L;', 'EXCESS_WASTE_BYTES = %s;' % lit)
if ins:
    rep('            return refUpdater.compareAndSet(AtomicBTreePartition.this, current, result);',
        '            boolean s4ok = refUpdater.compareAndSet(AtomicBTreePartition.this, current, result);\n            S4Waste.attempt(s4ok, heapSize, Thread.holdsLock(this));\n            return s4ok;')
    rep('    private boolean updateWastedAllocationTracker(long wastedBytes)\n    {', '    private boolean updateWastedAllocationTracker(long wastedBytes)\n    {\n        S4Waste.tracker(wastedBytes);')
    rep('        wasteTrackerUpdater.set(this, TRACKER_PESSIMISTIC_LOCKING);', '        if (wasteTrackerUpdater.getAndSet(this, TRACKER_PESSIMISTIC_LOCKING) != TRACKER_PESSIMISTIC_LOCKING) S4Waste.flip();')
open(dst, 'w').write(t)
PY
cp "$H/S4Waste.java" "$W/org/apache/cassandra/db/partitions/"
CP="$C/build/classes/main:$C/build/lib/jars/*"
FILES=("$W/org/apache/cassandra/db/partitions/AtomicBTreePartition.java")
[ "$ins" = 1 ] && FILES+=("$W/org/apache/cassandra/db/partitions/S4Waste.java")
javac -nowarn -proc:none -cp "$CP" -d "$O" "${FILES[@]}" 2>&1 | grep -v '^Note:' || true
diff <(sed -n '1,400p' "$S") "$W/org/apache/cassandra/db/partitions/AtomicBTreePartition.java" > "$O/patch.diff" || true
echo "variant $name literal=$lit instrument=$ins classes: $(find $O -name '*.class' | wc -l); diff lines $(wc -l < $O/patch.diff)"
