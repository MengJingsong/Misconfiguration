#!/usr/bin/env python3
"""Analysis of none-compose-buffer_remaining--autonomous (unit tier, B2 as amended 2026-10-29). usage: analyze.py <run dir>
Reads test-A.out and test-B.out; prints the cell table and one EXPECTED line per frozen prediction R1-R6."""
import os, sys

d = sys.argv[1]
MiB = 1 << 20


def kv(line):
    return dict(x.split('=', 1) for x in line.split()[2:] if '=' in x)


def load(fn):
    return [l.rstrip('\n') for l in open(os.path.join(d, fn)) if l.startswith('STAGE4 ')]


A, B = load('test-A.out'), load('test-B.out')
ok_all = True


def expect(desc, cond):
    global ok_all
    ok_all &= bool(cond)
    print(f'EXPECTED: {desc} - {"yes" if cond else "NO"}')


def cells(rows):
    out = []
    for l in rows:
        if l.split()[1] == 'cell':
            out.append(kv(l))
    return out


ca, cb = cells(A), cells(B)
print('cell | type | L | resultNull | A alloc median (min..max) | B hits/calls')
for x, y in zip(ca, cb):
    print(f"{x['cell']} | {x['type']} | {x['L']} | {x['resultNull']} | {x['repmedian']} ({x['repmin']}..{x['repmax']}) | {y['hits']}/{y['calls']}")


def find(lst, cell, L):
    for x in lst:
        if x['cell'] == cell and int(x['L']) == L:
            return x
    raise KeyError((cell, L))


# R1
bad = []
for y in cb:
    cell, L = y['cell'], int(y['L'])
    should_skip = cell == 'null' or (L == 0 and y['type'] in ('IntegerType', 'Int32Type'))
    if should_skip and y['hits'] != '0':
        bad.append((cell, L, y['hits']))
    if not should_skip and y['hits'] != y['calls']:
        bad.append((cell, L, y['hits'], y['calls']))
expect(f'R1 pass B: line 180 runs for every call except null and the IntegerType/Int32Type L=0 cells (violations: {bad})', not bad)
# R2
nul = int(find(ca, 'null', 0)['repmedian']); i0 = int(find(ca, 'integer', 0)['repmedian']); n0 = int(find(ca, 'int32', 0)['repmedian'])
b0 = int(find(ca, 'bytes', 0)['repmedian'])
expect(f'R2 null/IntegerType L=0/Int32Type L=0 return null and allocate <= 256 ({nul},{i0},{n0}); BytesType L=0 non-null, <= 1024 ({b0}); difference <= 1024 ({abs(b0 - i0)})',
       (find(ca, 'null', 0)['resultNull'].lower() == 'true' and find(ca, 'integer', 0)['resultNull'].lower() == 'true' and find(ca, 'int32', 0)['resultNull'].lower() == 'true'
        and find(ca, 'bytes', 0)['resultNull'].lower() == 'false' and max(nul, i0, n0) <= 256 and b0 <= 1024 and abs(b0 - i0) <= 1024))
# R3
r3 = True; txt = []
for L in (MiB, 16 * MiB, 64 * MiB):
    r = int(find(ca, 'integer', L)['repmedian']) / L; txt.append(f'integer L={L}: {r:.5f}')
    r3 &= 1.0 <= r <= 4.0
for L in (0, 1, 1024, MiB, 16 * MiB, 64 * MiB):
    v = int(find(ca, 'bytes', L)['repmedian']); txt.append(f'bytes L={L}: {v}')
    r3 &= v <= 4 * L + 1024
expect('R3 IntegerType alloc/L in [1,4] for L>=1MiB; BytesType alloc <= 4L+1024 (' + '; '.join(txt) + ')', r3)
# R4
e = [l for l in A if l.split()[1] == 'empty'][0]; ek = kv(e)
b0r = int(find(ca, 'bytes-rep', 0)['repmedian']); i0r = int(find(ca, 'integer-rep', 0)['repmedian'])
m1 = int(find(ca, 'integer', MiB)['repmedian']); m1r = int(find(ca, 'integer-rep', MiB)['repmedian'])
expect(f'R4 noise: L=0 repeats differ <= 64 (bytes {abs(b0r - b0)}, integer {abs(i0r - i0)}); L=1MiB integer repeats differ <= 1% of L ({abs(m1 - m1r)} vs {MiB // 100}); EMPTY <= 16 ({ek["e1"]},{ek["e2"]})',
       abs(b0r - b0) <= 64 and abs(i0r - i0) <= 64 and abs(m1 - m1r) <= MiB // 100 and int(ek['e1']) <= 16 and int(ek['e2']) <= 16)
# R5
c1 = {int(kv(l)['L']): int(kv(l)['median']) for l in A if l.split()[1] == 'c1'}
ctl = [l for l in A if l.split()[1] == 'control'][0]
expect(f'R5 C1 in [L+16,L+32] ({c1}); control throws IOException with "exceeds_the_maximum_of_1024" ({ctl[:160]})',
       all(L + 16 <= v <= L + 32 for L, v in c1.items()) and 'class=IOException' in ctl and 'exceeds_the_maximum_of_1024' in ctl)
# R6
i4 = find(ca, 'int32', 4)
expect(f'R6 Int32Type L=4 non-null, alloc <= 1024 ({i4["resultNull"]}, {i4["repmedian"]})', i4['resultNull'].lower() == 'false' and int(i4['repmedian']) <= 1024)
mm = sum(1 for l in A + B if l.endswith('MISMATCH'))
expect(f'no MISMATCH check lines ({mm})', mm == 0)
print('ALL EXPECTED HOLD' if ok_all else 'SOME EXPECTED DO NOT HOLD')
