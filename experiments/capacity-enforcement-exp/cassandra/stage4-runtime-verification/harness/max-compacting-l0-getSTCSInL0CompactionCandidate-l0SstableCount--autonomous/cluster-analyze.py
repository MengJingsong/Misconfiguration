#!/usr/bin/env python3
"""Cluster tier analysis, max-compacting-l0-getSTCSInL0CompactionCandidate-l0SstableCount--autonomous (B3f/B3g as amended 2026-10-26).
usage: cluster-analyze.py <outdir with A B C D>   (a FAIL is a reading, not a harness error)"""
import sys, json, os, re, glob
D = sys.argv[1]; MIB = 2**20
def load(lb):
    d = os.path.join(D, lb); o = {}
    for t in ('lag-end', 'settled-write', 'truncated'):
        p = f'{d}/snapshot-{t}.json'
        if os.path.exists(p): o[t] = json.load(open(p))
    o['samples'] = [json.loads(l) for l in open(f'{d}/samples.jsonl')]
    st = open(f'{d}/stress-write.txt').read()
    o['errors'] = int(re.search(r'Total errors\s*:\s*(\d+)', st).group(1))
    o['rows'] = int(re.search(r'Total partitions\s*:\s*([\d,]+)', st).group(1).replace(',', ''))
    o['flushes'] = sum(1 for _ in open(f'{d}/flushes.log'))
    o['stcs'] = sum(1 for _ in open(f'{d}/stcs-lines.txt')) if os.path.exists(f'{d}/stcs-lines.txt') else -1
    o['drain'] = json.load(open(f'{d}/drain-write.json')) if os.path.exists(f'{d}/drain-write.json') else None
    return o
R = {lb: load(lb) for lb in 'ABCD' if os.path.isdir(os.path.join(D, lb))}
def peak(o):
    v = [x['parsed']['count'][0] for x in o['samples'] if x.get('parsed') and x['parsed']['count']]
    v.append(o['lag-end']['parsed']['count'][0]); return max(v)
res = []
def chk(name, ok, detail): res.append(ok); print(('PASS ' if ok else 'FAIL ') + name + ' :: ' + detail)
print('label rows errors flushes peakL0 lagL0 lagLive(MiB) lagFiles(MiB) settledL0 stcsLines drainSettled')
for lb, o in R.items():
    s = o.get('settled-write')
    print(lb, o['rows'], o['errors'], o['flushes'], peak(o), o['lag-end']['parsed']['count'][0], round(o['lag-end']['parsed']['live'] / MIB), round(o['lag-end']['bytes'] / MIB),
          s['parsed']['count'][0] if s else '-', o['stcs'], o['drain']['settled'] if o['drain'] else '-')
chk('no write error; 1.5 M rows in every run', all(o['errors'] == 0 and o['rows'] == 1500000 for o in R.values()), str({k: (o['errors'], o['rows']) for k, o in R.items()}))
written = 1500000 * 1050 / MIB
for lb in 'ABC':
    if lb in R:
        o = R[lb]; live = o['lag-end']['parsed']['live'] / MIB; fb = o['lag-end']['bytes'] / MIB
        chk(f'{lb}: file bytes and live bytes within 15% of each other and of rows x 1050 B', abs(fb / live - 1) < 0.15 and 0.8 < live / written < 1.3, f'files {fb:.0f}, live {live:.0f}, written ~{written:.0f} MiB')
        chk(f'{lb}: peak L0 >= 100', peak(o) >= 100, str(peak(o)))
if 'B' in R:
    chk('B: L0 count at lag-end >= 100, equal to the Data.db files on disk, at most the flush calls', R['B']['lag-end']['parsed']['count'][0] >= 100 and R['B']['lag-end']['parsed']['count'][0] == len(R['B']['lag-end']['datafiles']) and R['B']['lag-end']['parsed']['count'][0] <= R['B']['flushes'], f"L0 {R['B']['lag-end']['parsed']['count'][0]}, files {len(R['B']['lag-end']['datafiles'])}, flush calls {R['B']['flushes']}")
    chk('B: no debug line (no candidate is ever requested)', R['B']['stcs'] == 0, str(R['B']['stcs']))
if 'A' in R: chk('A: at least one "L0 is too far behind" debug line', R['A']['stcs'] >= 1, str(R['A']['stcs']))
if 'C' in R: chk('C (flag true): zero debug lines', R['C']['stcs'] == 0, str(R['C']['stcs']))
if 'D' in R and 'A' in R: chk('D (positive control): peak L0 below half of A', peak(R['D']) < 0.5 * peak(R['A']), f"D {peak(R['D'])} vs A {peak(R['A'])}")
for lb in 'ACD':
    if lb not in R or 'settled-write' not in R[lb]: continue
    s = R[lb]['settled-write']; by = s['parsed']['bytes']; top = max(i for i, x in enumerate(by) if x)
    nominal = lambda i: (10 ** i) * 10 * MIB
    rat = [by[i] / nominal(i) for i in range(1, top)]
    chk(f'{lb}: after the drain every level below the top <= 1.05 x nominal, total live within 5%, L0 <= {4 if lb == "D" else 32}', all(r <= 1.05 for r in rat) and abs(s['parsed']['live'] / R[lb]['lag-end']['parsed']['live'] - 1) < 0.05 and s['parsed']['count'][0] <= (4 if lb == 'D' else 32),
        f"bytes/level {by}, below-top ratios {[round(r, 3) for r in rat]}, L0 {s['parsed']['count'][0]}, drain {R[lb]['drain']}")
chk('every drain settled', all(o['drain']['settled'] for o in R.values() if o['drain']), 'ok')
chk('TRUNCATE control: file bytes after truncate < 1% of the last pre-truncate bytes', all(o['truncated']['bytes'] < 0.01 * (o.get('settled-write') or o['lag-end'])['bytes'] for o in R.values()), str({k: o['truncated']['bytes'] for k, o in R.items()}))
print('ALL PASS' if all(res) else f'{res.count(False)} FAIL')
