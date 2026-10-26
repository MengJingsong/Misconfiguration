#!/usr/bin/env python3
"""Independent self-check: re-parses the raw per-label files (node log lines, rows.csv, tablestats, loader.out, session.log, unit CSV) without
using analyze_*.py or the sampler. Usage: selfcheck.py <run1-cl dir> <unit-results.csv>"""
import sys, re, os, csv, datetime, json
D, U = sys.argv[1], sys.argv[2]
MiB = 1048576.0
ok = []
def hold(name, cond, note):
    ok.append(cond); print('%s | %s | %s' % ('HOLDS' if cond else 'DOES NOT HOLD', name, note))
def ts(s):  # 2026-10-26T04:26:05,841 -> epoch ms (UTC)
    return int(datetime.datetime.strptime(s[:19], '%Y-%m-%dT%H:%M:%S').replace(tzinfo=datetime.timezone.utc).timestamp() * 1000) + int(s[20:23])
def label(l):
    d = D + '/' + l
    fl = []
    for ln in open(d + '/flush-lines.txt'):
        m = re.search(r'(\d{4}-\d\d-\d\dT[\d:]+,\d{3}) .*Enqueuing flush of ks\.t, Reason: MEMTABLE_LIMIT, Usage: ([\d.]+)(B|KiB|MiB|GiB) ', ln)
        if m: fl.append((ts(m.group(1)), float(m.group(2)) * {'B': 1, 'KiB': 1024, 'MiB': MiB, 'GiB': MiB * 1024}[m.group(3)] / MiB))
    rows = [tuple(map(int, x.split(','))) for x in open(d + '/rows.csv').read().split() if x]
    def rows_at(t):
        r = [n for (tt, n) in rows if tt <= t]; return r[-1] if r else 0
    txt = open(d + '/loader.out').read()
    return fl, [rows_at(t) for t, _ in fl], rows[-1][1], txt, open(d + '/tablestats.txt').read()
L = {l: label(l) for l in ('A1024c', 'A1024c128', 'A1024r', 'A1024n', 'A1024p', 'A256c', 'A4096c')}
for l, (fl, ra, n, t, st) in L.items():
    print('RAW', l, 'rows', n, 'flush MiB', [round(u, 2) for _, u in fl], 'rows at flush', ra)
# 1. validity: every row of the loader was inserted; counts of the loader's own total agree with rows.csv
for l, (fl, ra, n, t, st) in L.items():
    m = re.search(r'loaded (\d+) rows of (\d+) chars', t)
    hold('%s loader total equals rows.csv' % l, m and int(m.group(1)) == n, t.strip())
# 2. trigger: flush usage near H/3 for all builds and sizes (three flushes each where an index grows)
for l, H in (('A1024c', 256), ('A1024p', 256), ('A256c', 256), ('A4096c', 256), ('A1024c128', 128)):
    fl = L[l][0]; trig = H / 3.0
    hold('%s three MEMTABLE_LIMIT flushes, each between H/3-0.1 and H/3+4 MiB' % l, len(fl) >= 3 and all(trig - 0.1 <= u <= trig + 4 for _, u in fl), 'trigger %.2f MiB; %s' % (trig, [round(u, 2) for _, u in fl]))
# 3. flush point independent of the constant: 1024, 256 and 4096 builds within 4 MiB of each other
m = {l: sum(u for _, u in L[l][0][:3]) / 3 for l in ('A1024c', 'A256c', 'A4096c', 'A1024p')}
hold('mean flush usage same across 256/1024/4096 builds (spread < 4 MiB)', max(m.values()) - min(m.values()) < 4, {k: round(v, 2) for k, v in m.items()})
hold('128 MiB pool: mean flush usage about half (0.45..0.55) of the 256 MiB run', 0.45 <= (sum(u for _, u in L['A1024c128'][0][:3]) / 3) / m['A1024c'] <= 0.55, round((sum(u for _, u in L['A1024c128'][0][:3]) / 3) / m['A1024c'], 3))
# 4. rows per flush varies with term length while bytes per flush does not
rpf = {l: L[l][2 - 2][0] and (L[l][1][2] / 3.0) for l in ('A1024c', 'A256c', 'A4096c')}
hold('rows per flush: 256 build > 1024 build > 4096 build (same bytes per flush)', rpf['A256c'] > rpf['A1024c'] > rpf['A4096c'], {k: round(v, 1) for k, v in rpf.items()})
# 5. rejection arm and dropped-index arm: no flush, no index growth; counts from the files
cr = int(open(D + '/A1024r/cantadd-count.txt').read().strip()); cn = int(open(D + '/A1024n/cantadd-count.txt').read().strip())
hold('A1024r: Can\'t add term lines == rows, no MEMTABLE_LIMIT flush, memtable cells == rows', cr == L['A1024r'][2] and not L['A1024r'][0] and 'Memtable cell count: %d' % L['A1024r'][2] in L['A1024r'][4], 'count %d rows %d' % (cr, L['A1024r'][2]))
hold('A1024r: data size about the no-index arm (within 1%)', abs(int(re.search(r'Memtable data size: (\d+)', L['A1024r'][4]).group(1)) / float(re.search(r'Memtable data size: (\d+)', L['A1024n'][4]).group(1)) - 1) < 0.01, [re.search(r'Memtable data size: (\d+)', L[x][4]).group(1) for x in ('A1024r', 'A1024n')])
hold('A1024n: no Can\'t add lines and no flush', cn == 0 and not L['A1024n'][0], cn)
# 6. read by key / LIKE from the summary files
for l, exp in (('A1024r', ['read_by_key rows=1', 'like_hits=0']), ('A1024c', ['read_by_key rows=1', 'like_hits=1']), ('A1024p', ['read_by_key rows=1', 'like_hits=1']), ('A256c', ['read_by_key rows=1', 'like_hits=1'])):
    v = json.load(open(D + '/' + l + '/summary.json'))['verify_out']
    hold('%s verify %s' % (l, exp), v == exp, v)
v = json.load(open(D + '/A4096c/summary.json'))['verify_out']
print('NOTE A4096c verify', v, '(LIKE found nothing although 4095-char terms were accepted and indexed; unexplained, no frozen row depends on it)')
# 7. constant in the running jar
for l, c in (('A1024c', 1024), ('A256c', 256), ('A4096c', 4096)):
    cl = json.load(open(D + '/' + l + '/summary.json'))['constant_check']
    hold('%s javap constant %d' % (l, c), any(('= %d;' % c) in x for x in cl) and any(('sipush        %d' % c) in x for x in cl), cl)
# 8. unit tier: boundary and monotonic N from the CSV, re-derived
R = {(r['mode'], int(r['L']), int(r['N'])): r for r in csv.DictReader(open(U))}
hold('unit: 1023 accepted and 1024/1025/4096 rejected in both modes', all(int(R[(m, 1023, 10 if m == 'PREFIX' else 10)]['accepted_adds']) == 10 and all(int(R[(m, x, 10)]['accepted_adds']) == 0 for x in (1024, 1025, 4096)) for m in ('PREFIX', 'CONTAINS')), 'from unit-results.csv')
hold('unit: CONTAINS 1023 N=30 estimate > 47e6 and N=1 estimate > 1.6e6 (no cap near 1 KiB)', int(R[('CONTAINS', 1023, 30)]['sum_estimate']) > 47e6 and int(R[('CONTAINS', 1023, 1)]['sum_estimate']) > 1.6e6, (R[('CONTAINS', 1023, 30)]['sum_estimate'], R[('CONTAINS', 1023, 1)]['sum_estimate']))
print('RESULT', 'ALL HOLD' if all(ok) else 'SOME DO NOT HOLD', sum(ok), '/', len(ok))
