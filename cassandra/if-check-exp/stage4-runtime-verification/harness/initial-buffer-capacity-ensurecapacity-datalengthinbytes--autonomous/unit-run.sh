#!/usr/bin/env bash
# Unit tier (B2) of initial-buffer-capacity-ensurecapacity-datalengthinbytes--autonomous. usage: bash unit-run.sh <run>
# Compiles EnsureCapacityProbe against ~/s4-b7-ie/build/classes/main and the build's jars (no file is added to the tree), then runs it:
# -Xmx128m (set small), -Xmx1g (set full), -Xmx4g (set big, N = 1<<30 and (1<<30)+1). Output ~/s4-b7-ie-logs/<run>/unit/
# Exit code 1 if any "STAGE4 check ... MISMATCH". EXPECTED lines state what the case predicts; a NO is recorded, not hidden.
set -uo pipefail
H=$(cd "$(dirname "$0")" && pwd); C=${CASSANDRA_HOME:-$HOME/s4-b7-ie}
RUN=${1:?run name}; L=$HOME/s4-b7-ie-logs/$RUN/unit; mkdir -p "$L/classes"; S=$L/summary.txt; : > "$S"
say() { echo "$*" | tee -a "$S"; }
CP="$C/build/classes/main:$C/build/lib/jars/*:$C/lib/*"
say "unit-run $RUN $(date -Is) host $(hostname -s) tree $C $(git -C $C describe --tags) java $(java -version 2>&1 | head -1)"
say "harness md5 $(md5sum "$H/EnsureCapacityProbe.java" | cut -c1-32)"
javac -d "$L/classes" -cp "$CP" "$H/EnsureCapacityProbe.java" > "$L/javac.log" 2>&1 || { say "javac failed"; cat "$L/javac.log"; exit 2; }
runp() { local tag=$1 xmx=$2 set=$3
  : > "${L:?}/${tag:?}.out"
  java -Xmx$xmx -XX:+UseSerialGC -cp "$L/classes:$CP" EnsureCapacityProbe $set "$L/$tag.out" > "$L/$tag.stdout" 2>&1; local rc=$?
  say "$tag xmx=$xmx set=$set exit=$rc checks=$(grep -c '^STAGE4 check' $L/$tag.out) ok=$(grep -c '^STAGE4 check.* ok ' $L/$tag.out) MISMATCH=$(grep -c '^STAGE4 check.* MISMATCH ' $L/$tag.out)"
  grep ' MISMATCH ' "$L/$tag.out" | tee -a "$S"; }
runp x128 128m small
runp x1g 1g full
runp x4g 4g big
python3 -I - "$L" <<'PY' | tee -a "$S"
import sys
L = sys.argv[1]
def meas(tag):
    d = {}
    for l in open(f'{L}/{tag}.out'):
        if l.startswith('STAGE4 m ') and ' retained ' not in l and 'path=' not in l:
            kv = dict(x.split('=', 1) for x in l.split()[3:] if '=' in x)
            d[(int(kv['n']), int(kv['init']))] = kv
    return d
a, b = meas('x128'), meas('x1g')
common = sorted(set(a) & set(b))
bad = [k for k in common if a[k]['alloc'] != b[k]['alloc'] or a[k]['len'] != b[k]['len']]
print(f"EXPECTED: allocation and result length identical at -Xmx128m and -Xmx1g for all {len(common)} common (n, init) points — {'yes' if not bad else 'NO'} {bad[:10]}")
ratios = {n: float(b[(n, 32)]['ratio']) for (n, i) in b if i == 32 and n >= 1000}
print('EXPECTED: ratio alloc/N at init 32 is about 3.0 (1000, 65535) and 2.0 (1<<20, 16<<20, 64<<20) —', dict(sorted(ratios.items())))
print('EXPECTED: no exception for any N <= 64<<20 —', 'yes' if all(v['exc'] == 'null' for v in b.values()) else 'NO')
PY
if grep -q ' MISMATCH ' "$L"/x128.out "$L"/x1g.out "$L"/x4g.out; then say "unit-run end with MISMATCH lines $(date -Is)"; exit 1; fi
say "unit-run end $(date -Is)"
