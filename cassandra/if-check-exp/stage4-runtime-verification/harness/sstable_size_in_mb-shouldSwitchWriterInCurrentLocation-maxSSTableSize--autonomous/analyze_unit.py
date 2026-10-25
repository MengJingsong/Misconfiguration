#!/usr/bin/env python3 -I
"""Unit-tier analyzer for sstable_size_in_mb-shouldSwitchWriterInCurrentLocation-maxSSTableSize--autonomous (B2f, as amended B2i).
Usage: analyze_unit.py <raw-dir>. Prints one RESULT line per check, then a table. Reads only calls-*.csv, files-*.csv, arms.txt."""
import csv, sys, re, os
raw = sys.argv[1]
arms = {}
for line in open(os.path.join(raw, 'arms.txt')):
    m = re.match(r'ARM (\S+) (.*)', line)
    kv = dict(x.split('=', 1) for x in m.group(2).split() if '=' in x)
    arms[m.group(1)] = kv
def rd(p): return list(csv.DictReader(open(p)))
res = []
def check(name, ok, detail): res.append(ok); print(('RESULT PASS ' if ok else 'RESULT FAIL ') + name + ' :: ' + detail)
CH = 16 * 1024
for tag in sorted(arms):
    kv = arms[tag]
    S = int(kv['maxSize']); comp = kv.get('compressed') == 'true'
    calls = rd(f'{raw}/calls-{tag}.csv'); files = rd(f'{raw}/files-{tag}.csv')
    n = len(files); sizes = [int(f['data_file_bytes']) for f in files]; levels = [int(f['level']) for f in files]
    ops = [int(c['operand']) for c in calls]; ret = [int(c['returned']) for c in calls]
    parts = [ops[i+1] - ops[i] for i in range(len(ops) - 1) if ret[i] == 0 and ret[i+1] in (0, 1)]
    parts_sorted = sorted(parts)
    maxpart = (parts_sorted[-2] if tag == 'wide' and len(parts_sorted) > 1 else parts_sorted[-1]) if parts else 0  # wide arm: the largest diff is the wide partition itself
    gran = (2 * CH + 64) if comp else 0
    total = int(kv['total']) if 'total' in kv else int(kv['inputBytes'])
    print(f'ARM {tag}: S={S} total={total} outputs={n} maxPartition={maxpart} calls={len(calls)} switches={sum(ret)} levels={ {l: levels.count(l) for l in sorted(set(levels))} }')
    check(f'{tag}: rows preserved', int(kv['outputRows']) == int(files and sum(int(f['rows']) for f in files)) and int(kv['partitionsAppended']) > 0, f"outputRows={kv['outputRows']} partitionsAppended={kv['partitionsAppended']}")
    check(f'{tag}: operand at every true return > S, at every false return <= S', all((o > S) == (r == 1) for o, r in zip(ops, ret)), f'min true={min([o for o,r in zip(ops,ret) if r==1], default=None)} max false={max([o for o,r in zip(ops,ret) if r==0], default=None)}')
    if tag == 'smax':
        check('smax: exactly one output', n == 1, f'outputs={n}'); continue
    if tag == 'wide':
        big = [s for s in sizes if s > S + maxpart + gran]
        check('wide: exactly one output above S + maxSmallPartition', len(big) == 1, f'outputs above: {big} (S={S}, maxPartition={maxpart})')
        if big: check('wide: that output >= 12 MiB and <= 12 MiB + S + one small partition', 12 * 2**20 <= big[0] <= 12 * 2**20 + S + maxpart + 2**20, f'size={big[0]}')
        continue
    nonfinal = sizes[:-1]
    check(f'{tag}: every non-final output in (S, S + maxPartition + granularity]', all(S < s <= S + maxpart + gran for s in nonfinal), f'min={min(nonfinal)} max={max(nonfinal)} S={S} maxPart={maxpart} gran={gran} excess_max={max(nonfinal)-S}')
    check(f'{tag}: final output <= S + maxPartition + granularity', sizes[-1] <= S + maxpart + gran, f'final={sizes[-1]}')
    exp = {'s10': 10, 's50': 50, 's200': 200}.get(tag)
    if exp: check(f'{tag}: output count ~ {exp} (+-10%)', abs(n - exp) <= max(1, 0.1 * exp), f'outputs={n}')
    if not comp:
        sw = [o for o, r in zip(ops, ret) if r == 1]
        check(f'{tag}: instrument: non-final Data.db length == operand at its switch (uncompressed)', sw[:len(nonfinal)] == nonfinal or len(sw) >= len(nonfinal) and sw[:len(nonfinal)] == nonfinal, f'first mismatch: {[(a,b) for a,b in zip(sw,nonfinal) if a!=b][:2]}')
    hist = {l: levels.count(l) for l in sorted(set(levels))}
    def fill(F, k):
        h, l, rem = {}, 1, k
        while rem > 0: h[l] = min(F ** l, rem); rem -= h[l]; l += 1
        return h
    print(f'INFO {tag}: fill-rule histogram for {n} files at F=10: {fill(10, n)}; observed {hist}')
    if tag == 's50': check('s50: levels 10 in L1, 40 in L2, none else (as predicted for exactly 50 files)', hist == {1: 10, 2: 40}, f'{hist} (outputs={n})')
    if tag == 's10': check('s10: all outputs in L1', hist == {1: n}, str(hist))
    if tag == 's200': check('s200: ~10 / 100 / rest in L1 / L2 / L3', hist.get(1) == 10 and hist.get(2) == 100 and set(hist) <= {1, 2, 3}, str(hist))
    if tag == 's50z': print('INFO s50z levels', hist)
print('SUMMARY', 'ALL PASS' if all(res) else f'{res.count(False)} FAIL of {len(res)}')
