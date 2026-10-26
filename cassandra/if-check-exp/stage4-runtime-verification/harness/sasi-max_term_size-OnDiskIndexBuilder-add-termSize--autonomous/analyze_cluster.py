#!/usr/bin/env python3
"""PASS/FAIL per frozen cluster prediction (B3f as amended B5). Usage: analyze_cluster.py <run dir containing one dir per label: v1000 v1023 v1024 v2000 c1 c64>"""
import csv, json, math, sys, os
base = sys.argv[1]
ROWS = 200000
res = []
def chk(name, expected, got, ok):
    res.append(ok); print('%s  %s  EXPECTED: %s  GOT: %s' % ('PASS' if ok else 'FAIL', name, expected, got))
def load(l):
    return json.load(open('%s/%s/summary.json' % (base, l)))
def peak(l, a, b):
    m = 0
    for r in csv.DictReader(open('%s/%s/heap.csv' % (base, l))):
        try:
            t = int(r['epoch_ms']); u = int(r['heap_used'])
        except Exception:
            continue
        if a <= t <= b: m = max(m, u)
    return m
S = {}
for l in ('v1000', 'v1023', 'v1024', 'v2000', 'c1', 'c64'):
    try: S[l] = load(l)
    except Exception as e: print('MISSING', l, e)
tot = lambda lst: sum(x[1] for x in lst)
for l, size in (('v1000', 1000), ('v1023', 1023), ('v1024', 1024), ('v2000', 2000)):
    if l not in S: continue
    s = S[l]
    chk('%s no error/OOM' % l, 'no error key, 0 OOM, 0 ERROR-rejecting', (s.get('error'), s['log_load_plus_flush']['OutOfMemoryError'], s['log_load_plus_flush']['Rejecting value (value size']),
        'error' not in s and s['log_load_plus_flush']['OutOfMemoryError'] == 0 and s['log_load_plus_flush']['Rejecting value (value size'] == 0)
    si = tot(s['si_after_flush']); sic = tot(s['si_after_compact']); dat = tot(s['data_after_flush'])
    rej = s['log_load_plus_flush']['Rejecting value (size']; cant = s['log_load']['Can\'t add term'] + s['log_flush']['Can\'t add term']
    if size < 1024:
        chk('%s index bytes >= rows*size after flush and after compaction' % l, '>= %d' % (ROWS * size), '%d / %d (ratio %.2f / %.2f per row-size)' % (si, sic, si / ROWS / size, sic / ROWS / size), si >= ROWS * size and sic >= ROWS * size)
        chk('%s no rejection logs' % l, '0 / 0', '%d / %d' % (rej, cant), rej == 0 and cant == 0)
    else:
        chk('%s rejection logs (flush path) == rows' % l, ROWS, rej, rej == ROWS)
        chk('%s memtable-path "Can\'t add term" == rows' % l, ROWS, cant, cant == ROWS)
        chk('%s index component total 0 bytes after flush and compaction' % l, '0 / 0', '%d / %d' % (si, sic), si == 0 and sic == 0)
        # REVISED after run 1 (run 1 printed FAIL for the line here that compared compressed Data.db bytes with rows*size; the table uses the default LZ4 compression
        # and the generated values repeat a pad string, so that expectation was an analyzer mistake, not a frozen B3f row): the base table still grows and does not depend on index acceptance
        chk('%s base table Data.db after flush within +-5%% of v1023 per 1 byte size step (v1024) / larger than v1024 (v2000)' % l, 'see text', dat,
            (abs(dat - tot(S['v1023']['data_after_flush'])) <= 0.05 * tot(S['v1023']['data_after_flush'])) if size == 1024 else dat > tot(S['v1024']['data_after_flush']))
    print('   %s heap peaks (indicative): load %d  flush %d  compact %d' % (l, peak(l, s['t_load_start'], s['t_load_end']), peak(l, s['t_flush_start'], s['t_flush_end']), peak(l, s['t_compact_start'], s['t_compact_end'])))
if 'v1023' in S and 'v1000' in S:
    a, b = tot(S['v1000']['si_after_flush']), tot(S['v1023']['si_after_flush'])
    chk('index bytes grow with value size below 1024 (1000 -> 1023)', 'v1023 > v1000', '%d -> %d' % (a, b), b > a)
for l, cap in (('c1', 1), ('c64', 64)):
    if l not in S: continue
    s = S[l]; per = math.ceil(cap * 1048576 / 1243); exp = ROWS // per + 1
    n = s['log_compact']['Flushed index segment']
    chk('%s (cap %d MB) compaction segments = floor(rows/%d)+1' % (l, cap, per), '%d (+-1)' % exp, n, abs(n - exp) <= 1)
    print('   %s heap peaks (indicative): load %d  flush %d  compact %d; index bytes after compaction %d' % (l, peak(l, s['t_load_start'], s['t_load_end']), peak(l, s['t_flush_start'], s['t_flush_end']), peak(l, s['t_compact_start'], s['t_compact_end']), tot(s['si_after_compact'])))
if 'c1' in S and 'c64' in S:
    a, b = S['c1']['log_compact']['Flushed index segment'], S['c64']['log_compact']['Flushed index segment']
    chk('control moves: segments cap 1 MB >> cap 64 MB', 'c1 > c64', '%d vs %d' % (a, b), a > b)
print('SUMMARY cluster predictions: %d/%d PASS' % (sum(res), len(res)))
