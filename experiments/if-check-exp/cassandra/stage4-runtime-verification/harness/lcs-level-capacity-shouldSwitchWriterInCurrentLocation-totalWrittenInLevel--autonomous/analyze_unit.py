#!/usr/bin/env python3 -I
"""Unit-tier analyzer for lcs-level-capacity-shouldSwitchWriterInCurrentLocation-totalWrittenInLevel--autonomous (B2f, as amended B2i).
Usage: analyze_unit.py <raw-dir>."""
import csv, sys, re, os
raw = sys.argv[1]
arms = {}
for line in open(os.path.join(raw, 'arms.txt')):
    m = re.match(r'ARM (\S+) (.*)', line)
    arms[m.group(1)] = dict(x.split('=', 1) for x in m.group(2).split() if '=' in x)
def rd(p): return list(csv.DictReader(open(p)))
res = []
def check(name, ok, detail): res.append(ok); print(('RESULT PASS ' if ok else 'RESULT FAIL ') + name + ' :: ' + detail)
def expected_hist(F, n):
    h, lvl, rem = {}, 1, n
    while rem > 0:
        k = min(F ** lvl, rem); h[lvl] = k; rem -= k; lvl += 1
    return h
rows_all = {}
for tag in sorted(arms):
    kv = arms[tag]; S = int(kv['maxSize']); F = int(kv['F']); total = int(kv['total'])
    calls = rd(f'{raw}/calls-{tag}.csv'); files = rd(f'{raw}/files-{tag}.csv')
    n = len(files); sizes = [int(f['data_file_bytes']) for f in files]; levels = [int(f['level']) for f in files]
    ops = [int(c['operand']) for c in calls]; ret = [int(c['returned']) for c in calls]
    parts = [ops[i+1] - ops[i] for i in range(len(ops) - 1) if ret[i] == 0]
    maxpart = max(parts) if parts else 0
    hist = {l: levels.count(l) for l in sorted(set(levels))}
    B = sum(sizes); rows = sum(int(f['rows']) for f in files)
    rows_all[tag] = (n, B, rows, hist, int(kv['partitionsAppended']), S, F, maxpart)
    print(f'ARM {tag}: F={F} S={S} total={total} outputs={n} bytes={B} rows={rows} partitions={kv["partitionsAppended"]} maxPartition={maxpart} hist={hist}')
    check(f'{tag}: no rows lost, no exception', rows == 200000 * int(kv['partitionsAppended']) // 20000 and int(kv['partitionsAppended']) > 0, f'rows={rows} partitions={kv["partitionsAppended"]}')
    check(f'{tag}: no level-0 output', 0 not in hist, str(hist))
    check(f'{tag}: every non-final file in (S, S + maxPartition]', all(S < s <= S + maxpart for s in sizes[:-1]), f'min={min(sizes[:-1])} max={max(sizes[:-1])}')
    check(f'{tag}: level histogram = fill by F^n', hist == expected_hist(F, n), f'observed {hist} expected {expected_hist(F, n)}')
    check(f'{tag}: level-increment events at the cumulative bytes > capacity', all((int(c['level_after']) > int(c['level_before'])) == (int(c['twil_after']) == 0 and int(c['returned']) == 1) for c in calls), 'currentLevel steps coincide with twil reset')
sweep = [t for t in ('f2', 'f4', 'f10', 'f41') if t in rows_all]
if sweep:
    ns = [rows_all[t][0] for t in sweep]; bs = [rows_all[t][1] for t in sweep]; one = max(rows_all[t][5] for t in sweep) + max(rows_all[t][7] for t in sweep)
    check('F sweep: file count N the same (+-1) across F', max(ns) - min(ns) <= 1 and all(abs(n - 50) <= 1 for n in ns), f'N={dict(zip(sweep, ns))}')
    check('F sweep: total bytes B the same within one file', max(bs) - min(bs) <= one, f'B={dict(zip(sweep, bs))} spread={max(bs)-min(bs)} oneFile={one}')
    exp = {'f2': {1: 2, 2: 4, 3: 8, 4: 16, 5: 20}, 'f4': {1: 4, 2: 16, 3: 30}, 'f10': {1: 10, 2: 40}, 'f41': {1: 41, 2: 9}}
    for t in sweep:
        if rows_all[t][0] == 50: check(f'{t}: histogram as predicted for 50 files', rows_all[t][3] == exp[t], f'observed {rows_all[t][3]} predicted {exp[t]}')
ctl = [t for t in ('f10s20', 'f10s100', 'f10') if t in rows_all]
if len(ctl) == 3:
    d = {t: rows_all[t] for t in ctl}
    check('control: N ~ 20 / 50 / 100 for total/20, /50, /100', all(abs(d[t][0] - e) <= max(1, 0.1 * e) for t, e in zip(('f10s20', 'f10', 'f10s100'), (20, 50, 100))), str({t: d[t][0] for t in ctl}))
    check('control: total bytes unchanged (within one file)', max(d[t][1] for t in ctl) - min(d[t][1] for t in ctl) <= max(d[t][5] for t in ctl) + 20000, str({t: d[t][1] for t in ctl}))
    check('control: per-file bytes track S', all(abs(sum(int(f["data_file_bytes"]) for f in rd(f"{raw}/files-{t}.csv")[:-1]) / max(1, d[t][0] - 1) - d[t][5]) <= 0.01 * d[t][5] for t in ctl), 'mean non-final file within 1% of S')
print('SUMMARY', 'ALL PASS' if all(res) else f'{res.count(False)} FAIL of {len(res)}')
