#!/usr/bin/env python3
"""Independent self-check for none-compose-buffer_remaining--autonomous (does not import analyze.py). usage: selfcheck.py <run dir>.
Re-parses test-A.out / test-B.out with its own regexes and re-evaluates the frozen predictions R1-R6; scans the JVM logs."""
import glob, os, re, sys

d = sys.argv[1]
MiB = 1 << 20
res = []


def rec(name, ok, note=''):
    res.append((name, ok))
    print(('PASS ' if ok else 'FAIL ') + name + (' :: ' + note if note else ''))


def fields(l):
    return {m.group(1): m.group(2) for m in re.finditer(r'(\w+)=(\S+)', l)}


raw = {p: open(os.path.join(d, f'test-{p}.out')).read().splitlines() for p in 'AB'}
cell = {}
for p, lines in raw.items():
    for l in lines:
        if l.startswith('STAGE4 cell '):
            f = fields(l)
            f['cellname'] = re.search(r'cell=(\S+)', l).group(1)
            cell.setdefault((p, f['cellname'], int(f['L'])), []).append(f)
rec('every cell appears exactly once per pass (18 cells)', all(len(v) == 1 for v in cell.values()) and len(cell) == 36, str(len(cell)))
g = lambda p, c, L: cell[(p, c, L)][0]
al = lambda c, L: int(g('A', c, L)['repmedian'])
# R1: pass B hit counts
viol = []
for (p, c, L), v in cell.items():
    if p != 'B':
        continue
    f = v[0]
    skip = c == 'null' or (L == 0 and f['type'] in ('IntegerType', 'Int32Type'))
    if (skip and f['hits'] != '0') or (not skip and f['hits'] != f['calls']):
        viol.append((c, L, f['hits'], f['calls']))
rec('R1 line 180 reached exactly where predicted', not viol, str(viol))
rec('R2 L=0: null for null/IntegerType/Int32Type (<=256), BytesType non-null (<=1024)',
    all(g('A', c, 0)['resultNull'] == 'true' and al(c, 0) <= 256 for c in ('null', 'integer', 'int32')) and g('A', 'bytes', 0)['resultNull'] == 'false' and al('bytes', 0) <= 1024,
    f"null {al('null', 0)} integer {al('integer', 0)} int32 {al('int32', 0)} bytes {al('bytes', 0)}")
rec('R2 branch-flip difference at L=0 <= 1024', abs(al('bytes', 0) - al('integer', 0)) <= 1024, str(al('bytes', 0) - al('integer', 0)))
rec('R3 IntegerType alloc/L in [1,4] for L>=1MiB', all(1.0 <= al('integer', L) / L <= 4.0 for L in (MiB, 16 * MiB, 64 * MiB)), str([round(al('integer', L) / L, 6) for L in (MiB, 16 * MiB, 64 * MiB)]))
rec('R3 BytesType alloc <= 4L+1024 at every L', all(al('bytes', L) <= 4 * L + 1024 for L in (0, 1, 1024, MiB, 16 * MiB, 64 * MiB)), str([al('bytes', L) for L in (0, 1, 1024, MiB, 16 * MiB, 64 * MiB)]))
rec('R3 note: BytesType allocation is independent of L (a view)', len({al('bytes', L) for L in (0, 1, 1024, MiB, 16 * MiB, 64 * MiB)}) == 1)
rec('R4 noise', abs(al('bytes-rep', 0) - al('bytes', 0)) <= 64 and abs(al('integer-rep', 0) - al('integer', 0)) <= 64 and abs(al('integer-rep', MiB) - al('integer', MiB)) <= MiB // 100)
e = [fields(l) for l in raw['A'] if l.startswith('STAGE4 empty ')][0]
rec('R4 EMPTY window <= 16', int(e['e1']) <= 16 and int(e['e2']) <= 16, str(e))
c1 = {int(fields(l)['L']): int(fields(l)['median']) for l in raw['A'] if l.startswith('STAGE4 c1 ')}
rec('R5 C1 in [L+16, L+32]', all(L + 16 <= v <= L + 32 for L, v in c1.items()) and len(c1) == 3, str(c1))
ctl = [l for l in raw['A'] if l.startswith('STAGE4 control ')][0]
rec('R5 the 2048-length read throws IOException naming max 1024', 'class=IOException' in ctl and 'exceeds_the_maximum_of_1024' in ctl)
rec('R6 Int32Type L=4 non-null, <= 1024', g('A', 'int32', 4)['resultNull'] == 'false' and al('int32', 4) <= 1024)
rec('no MISMATCH lines', not any(l.endswith('MISMATCH') for p in raw for l in raw[p]))
errs = []
for fn in glob.glob(os.path.join(d, 'jvm-*.log')):
    for l in open(fn, errors='replace'):
        if re.search(r'Exception|Error|SEVERE|FATAL', l) and 'Byteman' not in l and 'WARN' not in l and 'STAGE4' not in l:
            errs.append((os.path.basename(fn), l.strip()[:120]))
rec('JVM logs contain no exception/error lines', not errs, str(errs[:3]))
print('SUMMARY', sum(1 for _, o in res if o), 'PASS,', sum(1 for _, o in res if not o), 'FAIL')
